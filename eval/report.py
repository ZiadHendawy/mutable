"""The eval's result: what every check found, whether the run passes, and the printed table."""

from dataclasses import dataclass

from eval.check_supersede import evolution_questions
from eval.score_retrieval import QuestionResult
from eval.write_data import WrittenPersona

RECALL_BAR = 0.9
MRR_BAR = 0.8


@dataclass
class Report:
    tenants: list[WrittenPersona]
    retriever: str
    k: int
    isolation_leaks: list[str]
    isolation_probes: int
    supersede_failures: list[str]
    results: list[QuestionResult]
    heldout: list[QuestionResult]  # reported only in aggregate

    @property
    def retrieval_leaks(self) -> int:
        return sum(len(r.leaked) for r in [*self.results, *self.heldout])

    @property
    def leaks(self) -> int:
        return len(self.isolation_leaks) + self.retrieval_leaks

    @property
    def recall(self) -> float:
        return _mean(r.recall for r in self.results)

    @property
    def mrr(self) -> float:
        return _mean(r.reciprocal_rank for r in self.results)

    @property
    def heldout_meets_bars(self) -> bool:
        if not self.heldout:
            return True
        return (
            _mean(r.recall for r in self.heldout) >= RECALL_BAR
            and _mean(r.reciprocal_rank for r in self.heldout) >= MRR_BAR
        )

    def passed(self, require_retrieval: bool = False) -> bool:
        gates = self.leaks == 0 and not self.supersede_failures
        if require_retrieval:
            gates = (
                gates
                and self.recall >= RECALL_BAR
                and self.mrr >= MRR_BAR
                and self.heldout_meets_bars
            )
        return gates


def format_report(report: Report, require_retrieval: bool = False) -> str:
    k = report.k
    written = ", ".join(f"{t.name}: {len(t.ids)} records" for t in report.tenants)
    links = sum(len(t.persona.records.successor_of()) for t in report.tenants)
    evolution = sum(len(evolution_questions(t.persona)) for t in report.tenants)
    lines = [
        f"Mutable eval -- wrote {written}; retriever: {report.retriever}",
        "",
        "Gates",
        f"  Cross-tenant leaks   {report.leaks:>4}   {_mark(report.leaks == 0)}"
        f"   ({report.isolation_probes} isolation probes + retrieval results)",
        f"  Supersede failures   {len(report.supersede_failures):>4}"
        f"   {_mark(not report.supersede_failures)}"
        f"   ({links} supersede links, {evolution} preference-evolution questions)",
        "",
        f"Retrieval (k={k})              n   Recall@{k}     MRR   excluded hits",
    ]
    categories = sorted({r.question.category for r in report.results})
    for category in [*categories, "all"]:
        rows = [r for r in report.results if category in ("all", r.question.category)]
        lines.append(_metrics_row(category, rows))
    if report.heldout:
        lines.append(_metrics_row("held-out", report.heldout))
    heldout = f"; held-out {_mark(report.heldout_meets_bars)}" if report.heldout else ""
    gating = "" if require_retrieval else "  (not gating; pass --require-retrieval)"
    lines.append(
        f"  Bars: Recall@{k} >= {RECALL_BAR} {_mark(report.recall >= RECALL_BAR)},"
        f" MRR >= {MRR_BAR} {_mark(report.mrr >= MRR_BAR)}{heldout}{gating}"
    )
    routed = [r.route_ok for r in report.results if r.route_ok is not None]
    routing = f"{_mean(routed):.2f}" if routed else "n/a (retriever reports no route)"
    lines.append(f"  Routing accuracy: {routing}")

    if report.isolation_leaks or report.supersede_failures:
        lines += ["", "Gate failures"]
        lines += [f"  leak: {leak}" for leak in report.isolation_leaks]
        lines += [f"  supersede: {failure}" for failure in report.supersede_failures]

    failed = [r for r in report.results if not r.passed]
    if failed:
        lines += ["", f"Failed questions ({len(failed)}/{len(report.results)})"]
        for r in failed:
            q = r.question
            lines.append(f"  {q.id} [{q.category}] {q.question}")
            if r.missing:
                lines.append(f"       missing:  {', '.join(r.missing)}")
            if r.excluded_hits:
                lines.append(f"       excluded but returned:  {', '.join(r.excluded_hits)}")
            if r.leaked:
                lines.append(f"       LEAKED:   {', '.join(r.leaked)}")

    # A leak is a security failure, not a ranking miss, so it's named even here -- by id
    # only. Anything else about a held-out question stays out of the report.
    heldout_leaks = [r for r in report.heldout if r.leaked]
    if heldout_leaks:
        lines += ["", f"Held-out leaks ({len(heldout_leaks)}/{len(report.heldout)})"]
        lines += [f"  {r.question.id}  LEAKED:   {', '.join(r.leaked)}" for r in heldout_leaks]

    lines += ["", "PASS" if report.passed(require_retrieval) else "FAIL"]
    return "\n".join(lines)


def _metrics_row(label: str, rows: list[QuestionResult]) -> str:
    return (
        f"  {label:<24}{len(rows):>5}{_mean(r.recall for r in rows):>11.2f}"
        f"{_mean(r.reciprocal_rank for r in rows):>8.2f}"
        f"{sum(len(r.excluded_hits) for r in rows):>16}"
    )


def _mean(values) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def _mark(ok: bool) -> str:
    return "ok  " if ok else "FAIL"
