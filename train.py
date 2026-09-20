"""Stage 1: train a LogisticRegression and save it as model.pkl."""
import joblib
from sklearn.linear_model import LogisticRegression

from data import make_dataset


def main():
    (X_train, y_train), _ = make_dataset()
    model = LogisticRegression()
    model.fit(X_train, y_train)
    joblib.dump(model, "model.pkl")
    print(f"trained LogisticRegression on {len(X_train)} samples -> model.pkl")


if __name__ == "__main__":
    main()
