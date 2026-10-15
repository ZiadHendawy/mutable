"""Run the eval: write every persona into the API, run every check, print the report.

    python -m eval.run_eval [--base-url http://localhost:8000] [--require-retrieval]

One module per step, in the order they run:

    read_data.py        read the data files and reject mistakes
    write_data.py       write each persona into the app as a fresh tenant
    check_isolation.py  no persona can reach another persona's records
    check_supersede.py  preference history is stored the way the files describe it
    score_retrieval.py  ask every question, compare the results with the expected answers
    report.py           totals, pass/fail, and the printed table

Exits non-zero when a gate fails: any cross-tenant leak, or any supersede check. Retrieval
metrics are reported against the README's bars but only gate the run with
--require-retrieval, since there is no search endpoint until milestone 4.

Held-out questions are scored exactly like the main set but reported only as totals, never
question by question, so search can't be tuned against them. --require-retrieval holds both
sets to the bars.
"""

import argparse
import sys

import httpx

from eval.check_isolation import check_isolation
from eval.check_supersede import check_supersede
from eval.report import Report, format_report
from eval.score_retrieval import Retriever, no_search, score_all
from eval.write_data import WrittenPersona, write_all


def evaluate(
    client: httpx.Client,
    tenants: list[WrittenPersona],
    retriever: Retriever = no_search,
    k: int = 5,
) -> Report:
    leaks, probes = check_isolation(client, tenants)
    supersede = [f for t in tenants for f in check_supersede(client, t)]
    results, heldout = score_all(client, tenants, retriever, k)
    return Report(
        tenants=tenants,
        retriever=getattr(retriever, "__name__", type(retriever).__name__),
        k=k,
        isolation_leaks=leaks,
        isolation_probes=probes,
        supersede_failures=supersede,
        results=results,
        heldout=heldout,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Mutable eval against a live API.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("-k", type=int, default=5, help="top-k cutoff for retrieval metrics")
    parser.add_argument(
        "--require-retrieval",
        action="store_true",
        help="also fail the run when Recall/MRR are below the README's bars, on the main set "
        "or the held-out set",
    )
    args = parser.parse_args()

    with httpx.Client(base_url=args.base_url) as client:
        report = evaluate(client, write_all(client), k=args.k)
    print(format_report(report, args.require_retrieval))
    sys.exit(0 if report.passed(args.require_retrieval) else 1)


if __name__ == "__main__":
    main()
