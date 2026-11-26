"""Run the financial reconciliation engine on the three source CSVs."""

import argparse
import sys
from pathlib import Path

from src.data_loader import DataLoadError, load_data
from src.reconciliation import reconcile
from src.reporting import write_reports


PROJECT_ROOT = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=PROJECT_ROOT / "data" / "sample")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "outputs")
    args = parser.parse_args(argv)
    try:
        run = reconcile(load_data(args.input_dir))
        summary = write_reports(run, args.output_dir)
    except (DataLoadError, OSError) as error:
        print(f"Reconciliation failed: {error}", file=sys.stderr)
        return 1

    print(
        f"{summary['run_status']}: {summary['settlement_group_count']} settlement groups, "
        f"{summary['anomalous_group_count']} with anomalies. Reports: {args.output_dir}"
    )
    if run.unassigned_anomalies:
        print(
            f"{len(run.unassigned_anomalies)} issues could not be assigned to a settlement group. "
            "Review anomaly_details.csv before using the provisional totals.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
