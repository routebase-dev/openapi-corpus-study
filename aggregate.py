#!/usr/bin/env python3
"""E261: turns the JSONL output of Routebase.Tools.SpecStudy into the Markdown tables of the
corpus study. Stdlib only, deterministic (same input, byte-identical output).

Nutzung:
  python3 scripts/spec-study/aggregate.py \
      --snapshot docs/marketing/openapi-corpus-study/raw/snapshot-2026-09-14.jsonl \
      --history  docs/marketing/openapi-corpus-study/raw/history-2026-09-14.jsonl \
      --refetch  docs/marketing/openapi-corpus-study/raw/refetch-2026-09-14.jsonl \
      --out      docs/marketing/openapi-corpus-study/tables-2026-09-14.md

Jede Datei ist optional; .gz wird transparent gelesen. Jede Kennzahl wird zweimal ausgewiesen:
roh (je Spec bzw. je Paar) und provider-gewichtet (erst je Provider den Anteil bilden, dann das
Mittel ueber die Provider, eine Stimme je Provider), weil vier Provider die Haelfte des Korpus stellen.
"""
import argparse
import gzip
import json
import statistics
from collections import Counter, defaultdict

# --- Rule metadata -----------------------------------------------------------------------------
# Owner decision B (2026-09-14): the headline lint numbers come from a neutral core; casing and
# house-style rules are reported in their own table; the versioning rules need org configuration
# and are not counted at all.
CORE_RULES = {
    "must-have-operation-description", "must-have-parameter-description", "must-have-schema-description",
    "must-have-response-description", "operation-id-must-be-unique", "must-define-security-scheme",
    "must-define-error-responses", "no-dangling-refs", "array-must-have-items",
    "path-params-must-be-declared", "examples-must-validate-against-schema",
    "media-examples-must-validate-against-schema", "no-api-key-in-query-param",
}
STYLE_RULES = {
    "path-must-be-kebab-case", "property-must-be-camel-case", "query-param-must-be-camel-case",
    "schema-name-must-be-pascal-case", "operation-id-must-be-camel-case",
    "enum-values-must-be-upper-snake-case", "path-param-must-be-camel-case", "header-must-be-train-case",
    "should-have-idempotency-key", "should-have-rate-limit-headers", "must-have-pagination-params",
    "must-use-problem-json-for-errors", "must-return-json-object-not-array",
}
EXCLUDED_RULES = {
    "versioning-strategy-defined", "versioning-url-consistency", "versioning-sunset-policy",
    "versioning-alias-defined",
}
def is_mega(r):
    """The four providers that hold half the corpus. The public bundle carries this as the
    megaProvider flag, because its provider names are pseudonyms."""
    return bool(r.get("megaProvider", False))


METADATA_RULES = {"description-changed", "summary-changed", "example-changed"}


def consumer_pair(r):
    """The headline view of a pair: Routebase's rules after path-template normalisation and local
    $ref resolution, and only when neither side leans on references outside the document (the
    parser replaces those with an empty object, which would read as removed fields). Returns None
    when the pair is not comparable that way."""
    if not r.get("pairConsumer"):
        return None
    ext = r.get("olderExternalRefs", r.get("snapshotExternalRefs", 0)) + r.get("newerExternalRefs", r.get("liveExternalRefs", 0))
    return None if ext > 0 else r["pairConsumer"]


def structurally_changed(pair):
    """A contract change a consumer can feel: something added or removed, or any classified change
    that is not purely descriptive text. Filters out the description/summary/example edits and the
    representational differences (content-type spelling, key order) that a snapshot rendered by
    apis.guru shows against the provider's own file."""
    if pair["breaking"] > 0:
        return True
    if pair["endpointsAdded"] or pair["endpointsRemoved"] or pair["schemasAdded"] or pair["schemasRemoved"]:
        return True
    return any(k not in METADATA_RULES for k in pair.get("nonBreakingByRule", {}))


def read_jsonl(path):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def pct(num, den):
    return "–" if not den else f"{100.0 * num / den:.1f} %"


def median(values):
    values = [v for v in values if v is not None]
    return "–" if not values else f"{statistics.median(values):.1f}"


def provider_weighted_share(rows, provider_key, predicate, min_rows=1):
    """Share of rows satisfying predicate, computed per provider, then the mean over providers (one vote per provider)."""
    per = defaultdict(lambda: [0, 0])
    for r in rows:
        p = per[r[provider_key]]
        p[1] += 1
        if predicate(r):
            p[0] += 1
    shares = [n / d for n, d in per.values() if d >= min_rows]
    return "–" if not shares else f"{100.0 * statistics.mean(shares):.1f} %"


def table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(out)


def declared_bucket(v):
    if not v:
        return "unbekannt"
    if v.startswith("2."):
        return "Swagger 2.0"
    if v.startswith("3.0"):
        return "OpenAPI 3.0.x"
    if v.startswith("3.1"):
        return "OpenAPI 3.1.x"
    if v.startswith("3.2"):
        return "OpenAPI 3.2.x"
    return "andere (" + v + ")"


def normalize_error(msg):
    if not msg:
        return "(leer)"
    msg = msg.split("\n")[0]
    for marker in (" at line", " (Lin:", ": (Lin"):
        if marker in msg:
            msg = msg.split(marker)[0]
    return msg[:90]


# --- Measurement A -----------------------------------------------------------------------------
def snapshot_section(rows):
    lines = ["## Messung A: Snapshot 2023 (bevorzugte Version je API)", ""]
    n = len(rows)
    read_fail = [r for r in rows if r.get("failure") or r.get("harnessFailure")]
    parsed = [r for r in rows if r.get("parsedOk")]
    strict = [r for r in parsed if r.get("strictValid")]
    providers = {r["provider"] for r in rows}

    lines.append("### Abdeckung")
    lines.append(table(["Schritt", "n", "Anteil"], [
        ["Einträge in list.json mit Datei im Checkout", n, "100 %"],
        ["davon Version aus dem Repo (list.json-Verzeichnis fehlte)", sum(1 for r in rows if r.get("versionFromRepo")), pct(sum(1 for r in rows if r.get("versionFromRepo")), n)],
        ["Provider", len(providers), ""],
        ["Harness-Fehler (Datei nicht lesbar, Exception)", len(read_fail), pct(len(read_fail), n)],
        ["vom Produkt-Parser gelesen (lenient)", len(parsed), pct(len(parsed), n)],
        ["strikt valide (Microsoft.OpenApi-Ruleset)", len(strict), pct(len(strict), len(parsed))],
    ]))
    lines.append("")

    lines.append("### Deklariertes Format")
    buckets = Counter(declared_bucket(r.get("declaredVersion")) for r in rows if not r.get("failure"))
    parsed_buckets = Counter(declared_bucket(r.get("declaredVersion")) for r in parsed)
    lines.append(table(["Format", "Specs", "Anteil", "davon gelesen"], [
        [b, c, pct(c, n - len(read_fail)), pct(parsed_buckets.get(b, 0), c)] for b, c in buckets.most_common()
    ]))
    lines.append("")

    fails = Counter(normalize_error(r.get("firstParseError") or r.get("parseErrorCategory")) for r in rows if not r.get("parsedOk") and not r.get("failure") and not r.get("harnessFailure"))
    if fails:
        lines.append("### Parse-Fehler (lenient), häufigste Meldungen")
        lines.append(table(["Meldung", "Specs"], [[m, c] for m, c in fails.most_common(10)]))
        lines.append("")
    sfails = Counter(normalize_error(r.get("firstStrictError")) for r in parsed if r.get("strictValid") is False)
    if sfails and set(sfails) != {"(leer)"}:
        lines.append("### Strikte Validierung, häufigste erste Meldung")
        lines.append(table(["Meldung", "Specs"], [[m, c] for m, c in sfails.most_common(10)]))
        lines.append("")

    lines.append("### Größe")
    ep = [r["metrics"]["endpoints"] for r in parsed]
    sc = [r["metrics"]["schemas"] for r in parsed]
    lines.append(table(["Kennzahl", "Median", "P90", "Summe"], [
        ["Endpoints je Spec", median(ep), f"{sorted(ep)[int(len(ep) * 0.9)]}" if ep else "–", sum(ep)],
        ["Schemas je Spec", median(sc), f"{sorted(sc)[int(len(sc) * 0.9)]}" if sc else "–", sum(sc)],
    ]))
    lines.append("")

    lines.append("### Strukturmerkmale je Spec (Anteil der gelesenen Specs, roh und provider-gewichtet)")
    def m(r, k):
        return r["metrics"].get(k, 0)
    flags = [
        ("mindestens ein Security-Scheme definiert", lambda r: m(r, "securitySchemes") > 0),
        ("alle Endpoints tragen eine Security-Anforderung", lambda r: m(r, "endpoints") > 0 and m(r, "endpointsWithSecurity") == m(r, "endpoints")),
        ("kein Endpoint trägt eine Security-Anforderung", lambda r: m(r, "endpointsWithSecurity") == 0),
        ("alle Endpoints haben eine Beschreibung", lambda r: m(r, "endpoints") > 0 and m(r, "endpointsWithDescription") == m(r, "endpoints")),
        ("alle Endpoints haben eine operationId", lambda r: m(r, "endpoints") > 0 and m(r, "endpointsWithOperationId") == m(r, "endpoints")),
        ("operationIds eindeutig (wo vorhanden)", lambda r: m(r, "endpointsWithOperationId") == m(r, "distinctOperationIds")),
        ("mindestens ein Endpoint mit 4xx-Antwort", lambda r: m(r, "endpointsWith4xx") > 0),
        ("alle Endpoints mit 4xx-Antwort", lambda r: m(r, "endpoints") > 0 and m(r, "endpointsWith4xx") == m(r, "endpoints")),
        ("Server-URL vorhanden", lambda r: m(r, "serverUrlPresent")),
        ("Server-URL ist HTTPS", lambda r: m(r, "serverHttps")),
        ("Version in Server-URL oder Pfaden (/vN/)", lambda r: m(r, "serverVersioned") or m(r, "endpointsWithVersionedPath") > 0),
        ("info.version vorhanden", lambda r: m(r, "infoVersionPresent")),
        ("info.version semver-förmig (x.y.z)", lambda r: m(r, "infoVersionSemver")),
        ("Kontakt-E-Mail vorhanden", lambda r: m(r, "contactPresent")),
        ("Lizenz vorhanden", lambda r: m(r, "licensePresent")),
        ("mindestens ein Schema mit Beispiel", lambda r: m(r, "schemasWithExample") > 0),
        ("mindestens ein deprecated Endpoint", lambda r: m(r, "endpointsDeprecated") > 0),
    ]
    lines.append(table(["Merkmal", "roh", "provider-gewichtet (Mittel je Provider)"], [
        [label, pct(sum(1 for r in parsed if f(r)), len(parsed)), provider_weighted_share(parsed, "provider", f)]
        for label, f in flags
    ]))
    lines.append("")

    lines.append("### Strukturmerkmale je Element (Anteil aller Endpoints, Parameter, Schemas)")
    def ratio(num_key, den_key):
        num = sum(m(r, num_key) for r in parsed)
        den = sum(m(r, den_key) for r in parsed)
        return pct(num, den)
    def pw_ratio(num_key, den_key):
        per = defaultdict(lambda: [0, 0])
        for r in parsed:
            per[r["provider"]][0] += m(r, num_key)
            per[r["provider"]][1] += m(r, den_key)
        shares = [a / b for a, b in per.values() if b > 0]
        return "–" if not shares else f"{100.0 * statistics.mean(shares):.1f} %"
    items = [
        ("Endpoints mit Beschreibung", "endpointsWithDescription", "endpoints"),
        ("Endpoints mit Summary", "endpointsWithSummary", "endpoints"),
        ("Endpoints mit operationId", "endpointsWithOperationId", "endpoints"),
        ("Endpoints mit Security-Anforderung", "endpointsWithSecurity", "endpoints"),
        ("Endpoints mit 4xx-Antwort", "endpointsWith4xx", "endpoints"),
        ("Endpoints mit 5xx-Antwort", "endpointsWith5xx", "endpoints"),
        ("Endpoints mit Erfolgsantwort (2xx/3xx)", "endpointsWithSuccessResponse", "endpoints"),
        ("Endpoints deprecated", "endpointsDeprecated", "endpoints"),
        ("Parameter mit Beschreibung", "parametersWithDescription", "parameters"),
        ("Parameter mit Beispiel", "parametersWithExample", "parameters"),
        ("Antworten mit Schema", "responsesWithSchema", "responses"),
        ("Schemas mit Beschreibung", "schemasWithDescription", "schemas"),
        ("Schemas mit Beispiel", "schemasWithExample", "schemas"),
        ("Schemas mit required-Liste", "schemasWithRequired", "schemas"),
    ]
    lines.append(table(["Merkmal", "roh", "provider-gewichtet (Mittel je Provider)"], [
        [label, ratio(a, b), pw_ratio(a, b)] for label, a, b in items
    ]))
    lines.append("")

    # --- Lint ---
    lines.append("### Lint gegen die Routebase-Built-in-Regeln (Default-Severity, ohne versioning-*)")
    def counted(r):
        return {k: v for k, v in r.get("lintByRule", {}).items() if k not in EXCLUDED_RULES}
    total_ep = sum(m(r, "endpoints") for r in parsed) or 1
    core_hits = [sum(v for k, v in counted(r).items() if k in CORE_RULES) for r in parsed]
    lines.append(table(["Kennzahl", "Wert"], [
        ["Specs ohne Kern-Befund", pct(sum(1 for h in core_hits if h == 0), len(parsed))],
        ["Median Kern-Befunde je Spec", median(core_hits)],
        ["Kern-Befunde je 100 Endpoints (gesamt)", f"{100.0 * sum(core_hits) / total_ep:.1f}"],
        ["Specs mit mindestens einem Error", pct(sum(1 for r in parsed if r.get("lintErrors", 0) > 0), len(parsed))],
        ["Median Warnungen je Spec", median([r.get("lintWarnings", 0) for r in parsed])],
    ]))
    lines.append("")

    def rule_table(rule_set, title):
        rows_ = []
        for rule in sorted(rule_set):
            affected = [r for r in parsed if counted(r).get(rule, 0) > 0]
            findings = sum(counted(r).get(rule, 0) for r in parsed)
            if findings == 0 and not affected:
                rows_.append([rule, "0.0 %", "–", "0"])
                continue
            rows_.append([
                rule,
                pct(len(affected), len(parsed)),
                provider_weighted_share(parsed, "provider", lambda r, rule=rule: counted(r).get(rule, 0) > 0),
                f"{100.0 * findings / total_ep:.1f}",
            ])
        rows_.sort(key=lambda x: (-float(x[1].split()[0]) if x[1] != "–" else 0, x[0]))
        lines.append(title)
        lines.append(table(["Regel", "Specs betroffen (roh)", "provider-gewichtet (Mittel je Provider)", "Befunde je 100 Endpoints"], rows_))
        lines.append("")

    rule_table(CORE_RULES, "#### Neutraler Kern (Entscheidung B)")
    rule_table(STYLE_RULES, "#### Stil nach Routebase-Konvention (eigene Tabelle, keine Schlagzeile)")
    all_rules = set()
    for r in parsed:
        all_rules.update(counted(r).keys())
    rest = all_rules - CORE_RULES - STYLE_RULES
    if rest:
        rule_table(rest, "#### Übrige Regeln (Struktur, Sicherheit, Vollständigkeit)")

    lines.append("### Provider-Verteilung (intern, nicht für die Veröffentlichung)")
    prov = Counter(r["provider"] for r in rows)
    lines.append(table(["Provider", "Specs", "Anteil"], [[p, c, pct(c, n)] for p, c in prov.most_common(10)]))
    lines.append("")
    return "\n".join(lines)


# --- Measurement B -----------------------------------------------------------------------------
def history_section(rows):
    lines = ["## Messung B: Git-Historie 2015 bis 2023 (aufeinanderfolgende Commit-Paare je Datei)", ""]
    n = len(rows)
    ok = [r for r in rows if r.get("pair")]
    product_changed = [r for r in ok if structurally_changed(r["pair"])]
    product_breaking = [r for r in product_changed if r["pair"]["breaking"] > 0]
    comparable = [dict(r, pair=consumer_pair(r)) for r in ok if consumer_pair(r)]
    touched = [r for r in comparable if not r["pair"]["modelIdentical"]]
    changed = [r for r in comparable if structurally_changed(r["pair"])]
    breaking = [r for r in changed if r["pair"]["breaking"] > 0]
    lines.append("Schlagzeilen-Zahlen in der **Konsumenten-Sicht**: Routebase-Regeln nach Normalisierung der Pfad-Platzhalter "
                 "und Auflösung lokaler `$ref`s, nur für Paare ohne dokumentexterne Referenzen. Die Produkt-Sicht (was Routebase heute "
                 "meldet) steht am Ende des Abschnitts.")
    lines.append("")
    lines.append("### Abdeckung")
    lines.append(table(["Schritt", "n", "Anteil"], [
        ["Commit-Paare", n, "100 %"],
        ["beide Seiten vom Parser gelesen", len(ok), pct(len(ok), n)],
        ["Dateien", len({r.get("path") or r.get("fileId") for r in rows}), ""],
        ["Provider", len({r["provider"] for r in rows}), ""],
        ["vergleichbar in der Konsumenten-Sicht (keine externen $refs)", len(comparable), pct(len(comparable), len(ok))],
        ["Paare mit irgendeiner sichtbaren Änderung (Modell nicht identisch)", len(touched), pct(len(touched), len(comparable))],
        ["Paare mit struktureller Vertragsänderung (ohne reine Text-Edits)", len(changed), pct(len(changed), len(comparable))],
        ["davon mit mindestens einem Breaking Change", len(breaking), pct(len(breaking), len(changed))],
    ]))
    lines.append("")

    lines.append("### Versionssprung bei Paaren mit Vertragsänderung")
    lines.append("apis.guru legt jede deklarierte Version in ein eigenes Verzeichnis; ein Versionssprung ist dort eine neue "
                 "Datei, kein Commit auf die alte. Diese Messung sieht deshalb fast nur Änderungen **innerhalb** einer "
                 "veröffentlichten Version, und *ohne Versionssprung* ist hier kein Befund, sondern die Definition des Korpus.")
    lines.append("")
    bumps = Counter(r["pair"]["versionBump"] for r in changed)
    bumps_breaking = Counter(r["pair"]["versionBump"] for r in breaking)
    order = ["same", "patch", "minor", "major", "downgrade", "changed-non-semver", "missing"]
    lines.append(table(["info.version", "Paare mit Änderung", "Anteil", "davon mit Breaking Change", "Anteil"], [
        [b, bumps.get(b, 0), pct(bumps.get(b, 0), len(changed)), bumps_breaking.get(b, 0), pct(bumps_breaking.get(b, 0), bumps.get(b, 0))]
        for b in order if bumps.get(b, 0)
    ]))
    lines.append("")
    no_bump = [r for r in breaking if r["pair"]["versionBump"] in ("same", "patch", "missing")]
    lines.append(table(["Kennzahl", "roh", "provider-gewichtet (Mittel je Provider mit ≥ 5 Paaren)"], [
        ["Breaking Change ohne Minor- oder Major-Sprung (same, patch, missing)", pct(len(no_bump), len(breaking)),
         provider_weighted_share(breaking, "provider", lambda r: r["pair"]["versionBump"] in ("same", "patch", "missing"), min_rows=5)],
        ["Breaking Change bei unveränderter info.version", pct(sum(1 for r in breaking if r["pair"]["versionBump"] == "same"), len(breaking)),
         provider_weighted_share(breaking, "provider", lambda r: r["pair"]["versionBump"] == "same", min_rows=5)],
        ["Änderung mit Breaking Change (Anteil aller Änderungen)", pct(len(breaking), len(changed)),
         provider_weighted_share(changed, "provider", lambda r: r["pair"]["breaking"] > 0, min_rows=5)],
        ["Median Tage zwischen zwei Commits derselben Datei", median([r["daysBetween"] for r in ok]), ""],
    ]))
    lines.append("")

    lines.append("### Häufigste Breaking-Change-Klassen (Paare, in denen die Klasse vorkommt)")
    by_rule = Counter()
    for r in breaking:
        for k in r["pair"]["breakingByRule"]:
            by_rule[k] += 1
    lines.append(table(["Regel", "Paare", "Anteil der Breaking-Paare"], [[k, c, pct(c, len(breaking))] for k, c in by_rule.most_common()]))
    lines.append("")

    lines.append("### Paare je Jahr (Datum des neueren Commits, Konsumenten-Sicht)")
    import datetime
    def year(ts):
        return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).year
    years = Counter(year(r["newerTimestamp"]) for r in comparable)
    years_c = Counter(year(r["newerTimestamp"]) for r in changed)
    years_b = Counter(year(r["newerTimestamp"]) for r in breaking)
    lines.append(table(["Jahr", "Paare", "strukturell verändert", "mit Breaking Change", "Anteil an den Änderungen"], [
        [y, years[y], years_c.get(y, 0), years_b.get(y, 0), pct(years_b.get(y, 0), years_c.get(y, 0))] for y in sorted(years)
    ]))
    lines.append("")
    lines.append("### Produkt-Sicht zum Vergleich (Routebase-Regeln ohne Normalisierung, alle gelesenen Paare)")
    lines.append(table(["Kennzahl", "n", "Anteil"], [
        ["strukturell verändert", len(product_changed), pct(len(product_changed), len(ok))],
        ["davon mit Breaking Change", len(product_breaking), pct(len(product_breaking), len(product_changed))],
        ["Breaking Change ohne Minor- oder Major-Sprung", sum(1 for r in product_breaking if r["pair"]["versionBump"] in ("same", "patch", "missing")), pct(sum(1 for r in product_breaking if r["pair"]["versionBump"] in ("same", "patch", "missing")), len(product_breaking))],
    ]))
    lines.append("")
    return "\n".join(lines)


# --- Measurement C -----------------------------------------------------------------------------
def refetch_section(rows):
    lines = ["## Messung C: Re-Fetch 2026 (Ursprungs-URL heute gegen den Snapshot 2023)", ""]
    n = len(rows)
    def status_bucket(r):
        s = r.get("httpStatus", 0)
        if s == 200:
            return "200"
        if s == 0:
            return "keine Antwort / Netzfehler"
        if s in (401, 403):
            return "401/403"
        if s == 404 or s == 410:
            return "404/410"
        if 300 <= s < 400:
            return "3xx (nicht aufgelöst)"
        if s >= 500:
            return "5xx"
        return str(s)
    st = Counter(status_bucket(r) for r in rows)
    lines.append("### Erreichbarkeit der Ursprungs-URLs")
    lines.append(table(["Antwort", "URLs", "Anteil", "provider-gewichtet (Mittel je Provider)"], [
        [b, c, pct(c, n), provider_weighted_share(rows, "provider", lambda r, b=b: status_bucket(r) == b)] for b, c in st.most_common()
    ]))
    lines.append("")

    live = [r for r in rows if r.get("httpStatus") == 200]
    parsed = [r for r in live if r.get("liveParsedOk") and r.get("snapshotParsedOk")]
    lines.append(table(["Schritt", "n", "Anteil"], [
        ["Kandidaten (Swagger 2.0 / OpenAPI 3.x als Ursprungsformat)", n, "100 %"],
        ["Provider", len({r["provider"] for r in rows}), ""],
        ["HTTP 200", len(live), pct(len(live), n)],
        ["Antwort als OpenAPI lesbar und Snapshot lesbar", len(parsed), pct(len(parsed), len(live))],
        ["Antwort nicht lesbar (HTML, anderes Format, kaputt)", sum(1 for r in live if not r.get("liveParsedOk")), pct(sum(1 for r in live if not r.get("liveParsedOk")), len(live))],
    ]))
    lines.append("")

    unreadable = [r for r in live if not r.get("liveParsedOk")]
    if unreadable:
        lines.append("### Antworten mit HTTP 200, die kein lesbares OpenAPI-Dokument sind")
        ct = Counter((r.get("contentType") or "(kein Content-Type)").split(";")[0].strip() for r in unreadable)
        lines.append(table(["Content-Type", "Antworten", "Anteil"], [[c, k, pct(k, len(unreadable))] for c, k in ct.most_common(8)]))
        lines.append("")
        errs = Counter(normalize_error(r.get("liveFirstParseError") or r.get("liveParseErrorCategory") or r.get("failure")) for r in unreadable)
        lines.append(table(["Erste Parser-Meldung", "Antworten"], [[m, k] for m, k in errs.most_common(8)]))
        lines.append("")

    lines.append("### Was sich seit dem Snapshot geändert hat (lesbare Paare)")
    lines.append("Der Snapshot ist apis.gurus YAML-Fassung mit deren Korrekturen, die Antwort die Datei des Anbieters. "
                 "Byteidentisch ist deshalb nichts, und *Modell identisch* ist die untere Schranke für *unverändert*. "
                 "*Strukturell verändert* zählt nur, was ein Konsument spüren kann. Endpoints oder Schemas kommen oder gehen, "
                 "oder eine klassifizierte Änderung ist kein reiner Text-Edit.")
    lines.append("")
    product_changed = [r for r in parsed if structurally_changed(r["pair"])]
    product_breaking = [r for r in product_changed if r["pair"]["breaking"] > 0]
    excluded_ext = [r for r in parsed if not consumer_pair(r)]
    parsed = [dict(r, pair=consumer_pair(r)) for r in parsed if consumer_pair(r)]
    lines.append("Schlagzeilen-Zahlen in der **Konsumenten-Sicht** (Pfad-Platzhalter normalisiert, lokale `$ref`s aufgelöst, "
                 f"nur Paare ohne dokumentexterne Referenzen: {len(parsed)} von {len(parsed) + len(excluded_ext)} lesbaren Paaren, "
                 f"{len(excluded_ext)} beiseite gelegt, davon {sum(1 for r in excluded_ext if is_mega(r))} von den vier Großanbietern).")
    lines.append("")
    identical_model = [r for r in parsed if r["pair"]["modelIdentical"]]
    touched = [r for r in parsed if not r["pair"]["modelIdentical"]]
    changed = [r for r in parsed if structurally_changed(r["pair"])]
    breaking = [r for r in changed if r["pair"]["breaking"] > 0]
    no_major = [r for r in breaking if r["pair"]["versionBump"] != "major"]
    lines.append(table(["Kennzahl", "n", "roh", "provider-gewichtet (Mittel je Provider)"], [
        ["Modell identisch", len(identical_model), pct(len(identical_model), len(parsed)), provider_weighted_share(parsed, "provider", lambda r: r["pair"]["modelIdentical"])],
        ["irgendeine Änderung (auch Texte, Beispiele)", len(touched), pct(len(touched), len(parsed)), provider_weighted_share(parsed, "provider", lambda r: not r["pair"]["modelIdentical"])],
        ["strukturell verändert", len(changed), pct(len(changed), len(parsed)), provider_weighted_share(parsed, "provider", lambda r: structurally_changed(r["pair"]))],
        ["davon mit Breaking Change", len(breaking), pct(len(breaking), len(changed)), provider_weighted_share(changed, "provider", lambda r: r["pair"]["breaking"] > 0)],
        ["Breaking Change ohne Major-Sprung", len(no_major), pct(len(no_major), len(breaking)), provider_weighted_share(breaking, "provider", lambda r: r["pair"]["versionBump"] != "major")],
        ["Breaking Change bei unveränderter info.version", sum(1 for r in breaking if r["pair"]["versionBump"] == "same"), pct(sum(1 for r in breaking if r["pair"]["versionBump"] == "same"), len(breaking)), provider_weighted_share(breaking, "provider", lambda r: r["pair"]["versionBump"] == "same")],
    ]))
    lines.append("")

    lines.append("### Versionssprung bei verändertem Vertrag")
    bumps = Counter(r["pair"]["versionBump"] for r in changed)
    bumps_b = Counter(r["pair"]["versionBump"] for r in breaking)
    order = ["same", "patch", "minor", "major", "downgrade", "changed-non-semver", "missing"]
    lines.append(table(["info.version", "verändert", "Anteil", "davon Breaking", "Anteil"], [
        [b, bumps.get(b, 0), pct(bumps.get(b, 0), len(changed)), bumps_b.get(b, 0), pct(bumps_b.get(b, 0), bumps.get(b, 0))] for b in order if bumps.get(b, 0)
    ]))
    lines.append("")

    lines.append("### Formatwechsel (deklarierte Version Snapshot → heute)")
    fmt = Counter((declared_bucket(r.get("snapshotDeclared")), declared_bucket(r.get("liveDeclared"))) for r in parsed)
    lines.append(table(["Snapshot", "heute", "Specs"], [[a, b, c] for (a, b), c in fmt.most_common()]))
    lines.append("")

    lines.append("### Häufigste Breaking-Change-Klassen (Specs, in denen die Klasse vorkommt)")
    by_rule = Counter()
    for r in breaking:
        for k in r["pair"]["breakingByRule"]:
            by_rule[k] += 1
    lines.append(table(["Regel", "Specs", "Anteil der Breaking-Specs"], [[k, c, pct(c, len(breaking))] for k, c in by_rule.most_common()]))
    lines.append("")

    lines.append("### Umfang: Endpoints heute gegenüber dem Snapshot")
    deltas = [r["pair"]["newEndpoints"] - r["pair"]["oldEndpoints"] for r in changed]
    lines.append(table(["Kennzahl", "Wert"], [
        ["Median Endpoints hinzugekommen je veränderter Spec", median([r["pair"]["endpointsAdded"] for r in changed])],
        ["Median Endpoints entfernt je veränderter Spec", median([r["pair"]["endpointsRemoved"] for r in changed])],
        ["Specs, die Endpoints verloren haben", pct(sum(1 for r in changed if r["pair"]["endpointsRemoved"] > 0), len(changed))],
        ["Median Netto-Änderung der Endpoint-Zahl", median(deltas)],
    ]))
    lines.append("")

    lines.append("### Produkt-Sicht zum Vergleich (Routebase-Regeln ohne Normalisierung, alle lesbaren Paare)")
    all_parsed_n = len(parsed) + len(excluded_ext)
    lines.append(table(["Kennzahl", "n", "Anteil"], [
        ["lesbare Paare", all_parsed_n, ""],
        ["strukturell verändert", len(product_changed), pct(len(product_changed), all_parsed_n)],
        ["davon mit Breaking Change", len(product_breaking), pct(len(product_breaking), len(product_changed))],
        ["Breaking Change ohne Major-Sprung", sum(1 for r in product_breaking if r["pair"]["versionBump"] != "major"), pct(sum(1 for r in product_breaking if r["pair"]["versionBump"] != "major"), len(product_breaking))],
    ]))
    lines.append("")

    lines.append("### Ohne die vier Großanbieter (megaProvider), Konsumenten-Sicht")
    rest = [r for r in parsed if not is_mega(r)]
    rest_changed = [r for r in rest if structurally_changed(r["pair"])]
    rest_breaking = [r for r in rest_changed if r["pair"]["breaking"] > 0]
    lines.append(table(["Kennzahl", "n", "Anteil"], [
        ["lesbare Paare", len(rest), ""],
        ["strukturell verändert", len(rest_changed), pct(len(rest_changed), len(rest))],
        ["davon mit Breaking Change", len(rest_breaking), pct(len(rest_breaking), len(rest_changed))],
        ["Breaking Change ohne Major-Sprung", sum(1 for r in rest_breaking if r["pair"]["versionBump"] != "major"), pct(sum(1 for r in rest_breaking if r["pair"]["versionBump"] != "major"), len(rest_breaking))],
    ]))
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshot")
    ap.add_argument("--history")
    ap.add_argument("--refetch")
    ap.add_argument("--out")
    args = ap.parse_args()

    parts = ["# Kennzahlen (generiert von scripts/spec-study/aggregate.py)", ""]
    if args.snapshot:
        parts.append(snapshot_section(read_jsonl(args.snapshot)))
    if args.history:
        parts.append(history_section(read_jsonl(args.history)))
    if args.refetch:
        parts.append(refetch_section(read_jsonl(args.refetch)))
    text = "\n".join(parts) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
