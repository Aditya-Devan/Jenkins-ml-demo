"""Stage 2: measure model accuracy on 200 held-out samples.

Writes metrics.json (archived by Jenkins on EVERY build) and, with
--print-accuracy, prints the bare number so the Jenkinsfile can read it
via returnStdout and apply the quality gate in Groovy.
"""
import argparse
import json

import joblib

from data import make_dataset


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--print-accuracy",
        action="store_true",
        help="print only the bare accuracy number (for Jenkins returnStdout)",
    )
    args = parser.parse_args()

    model = joblib.load("model.pkl")
    _, (X_test, y_test) = make_dataset()

    accuracy = float(model.score(X_test, y_test))

    metrics = {"accuracy": round(accuracy, 4), "n_test_samples": int(len(X_test))}
    with open("metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    if args.print_accuracy:
        print(f"{accuracy:.4f}")
    else:
        print(f"accuracy on {len(X_test)} held-out samples: {accuracy:.2f}")


if __name__ == "__main__":
    main()
