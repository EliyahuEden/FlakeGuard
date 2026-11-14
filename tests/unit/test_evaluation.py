from flakeguard.evaluation import classification_evaluation, fingerprint_evaluation


def test_evaluation_reports_counts_not_invented_accuracy():
    result = classification_evaluation()
    assert result["cases"] == 32
    matrix = result["confusion_matrix_rows_actual_columns_predicted"]
    assert sum(sum(row.values()) for row in matrix.values()) == 32
    assert 0 <= result["accuracy"] <= 1
    assert result["accuracy"] < 1  # Ambiguous ground truth intentionally tests abstention.


def test_fingerprint_pair_evaluation():
    result = fingerprint_evaluation()
    assert (
        sum(
            result[k]
            for k in ["true_positive", "false_positive", "false_negative", "true_negative"]
        )
        == result["pairs"]
    )
