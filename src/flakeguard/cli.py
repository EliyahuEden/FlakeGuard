import argparse
import json
import os
from pathlib import Path

from alembic import command
from alembic.config import Config

from flakeguard.config import get_settings
from flakeguard.db import session_factory
from flakeguard.demo import execute_injected, reset_demo, seed_demo
from flakeguard.github import sync_repository
from flakeguard.ingestion import atomic_ingest, get_repository
from flakeguard.schemas import ImportContext
from flakeguard.summary import quality_summary


def migrate() -> None:
    root = Path.cwd()
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    command.upgrade(config, "head")


def main() -> None:
    parser = argparse.ArgumentParser(description="FlakeGuard ingestion and investigation tools")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="Apply Alembic migrations")
    demo = commands.add_parser("demo", help="Migrate and import seeded synthetic report history")
    demo.add_argument(
        "--with-local", action="store_true", help="Also execute 12 controlled pytest runs"
    )
    commands.add_parser("reset-demo", help="Delete only reserved demo data")
    upload = commands.add_parser("import", help="Import a local JSON/XML report")
    upload.add_argument("report", type=Path)
    upload.add_argument("--repository", required=True)
    upload.add_argument("--run-id", required=True)
    upload.add_argument("--branch", default="unknown")
    upload.add_argument("--commit-sha")
    upload.add_argument("--run-attempt", type=int, default=1)
    upload.add_argument("--environment")
    upload.add_argument("--browser")
    upload.add_argument("--provenance", choices=["real", "injected", "synthetic"], default="real")
    upload.add_argument("--executed-at")
    sync = commands.add_parser("sync", help="Manually sync a server-allowlisted GitHub repository")
    sync.add_argument("repository")
    sync.add_argument("--max-runs", type=int, default=20, choices=range(1, 101), metavar="1..100")
    sync.add_argument("--artifact-pattern", default="*")
    summary = commands.add_parser(
        "summary", help="Generate Markdown (optionally append to Actions job summary)"
    )
    summary.add_argument("run_id", type=int)
    summary.add_argument("--output", type=Path)
    summary.add_argument("--github-summary", action="store_true")
    evaluate = commands.add_parser(
        "evaluate", help="Evaluate synthetic scenarios and classification dataset"
    )
    evaluate.add_argument("--output", type=Path, default=Path("docs/evidence/evaluation.json"))
    args = parser.parse_args()
    if args.command == "migrate":
        migrate()
        print("Migrations complete")
        return
    if args.command == "demo":
        migrate()
    with session_factory()() as session:
        if args.command == "demo":
            print(
                json.dumps(
                    {
                        "synthetic": seed_demo(session),
                        **(
                            {"executed_injected": execute_injected(session)}
                            if args.with_local
                            else {}
                        ),
                    }
                )
            )
        elif args.command == "reset-demo":
            print(json.dumps({"removed_demo_runs": reset_demo(session)}))
        elif args.command == "import":
            context = ImportContext.model_validate(
                {
                    k: v
                    for k, v in vars(args).items()
                    if k not in {"command", "report"} and v is not None
                }
            )
            if args.report.stat().st_size > get_settings().max_report_bytes:
                parser.error("Report exceeds byte limit")
            print(
                atomic_ingest(
                    session, args.report.read_bytes(), args.report.name, context
                ).model_dump_json()
            )
        elif args.command == "sync":
            settings = get_settings()
            if args.repository.lower() not in settings.allowed_repositories:
                parser.error("Repository must be in GITHUB_REPOSITORIES server allowlist")
            repo = get_repository(session, args.repository)
            repo.github_enabled = True
            session.commit()
            print(
                json.dumps(
                    sync_repository(
                        session, settings, args.repository, args.max_runs, args.artifact_pattern
                    )
                )
            )
        elif args.command == "summary":
            report = quality_summary(session, args.run_id)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(report, encoding="utf-8")
            if args.github_summary:
                path = os.environ.get("GITHUB_STEP_SUMMARY")
                if not path:
                    parser.error("GITHUB_STEP_SUMMARY is not set")
                with Path(path).open("a", encoding="utf-8") as stream:
                    stream.write(report)
            print(report)
        elif args.command == "evaluate":
            from flakeguard.evaluation import evaluate_all

            result = evaluate_all(session)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
