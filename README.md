# OpenAPI corpus study — how public API contracts change

Companion data for the Routebase article
[*Three Years Later: What Happened to 1,927 Public API Specs*](https://routebase.dev/blog/public-api-specs-three-years-later/). Everything here can be recomputed from the files in this
repository with one script and no network access.

## What was measured

Three measurements over the [apis.guru OpenAPI directory](https://github.com/APIs-guru/openapi-directory)
at commit `f04b8d0bcd39c52e1cf3ad7a5fe744709832ae49` (2026-04-20), plus the directory's `list.json`
as served on 2026-09-14. The directory's own update job last changed a spec on 2023-04-21, so its
contents are a snapshot of spring 2023.

- **A · Snapshot** — the preferred version of every API in the directory (2,523 documents): parsed,
  validated, measured structurally, and linted.
- **B · History** — every consecutive commit pair of every spec file in the directory's git history
  (106,083 pairs, 2015 to 2024), diffed for breaking changes.
- **C · Re-fetch** — the origin URL of every preferred Swagger 2.0 or OpenAPI 3.x spec (1,927 URLs)
  fetched once on 2026-09-14 and diffed against its 2023 copy.

The parser, the style-guide linter and the breaking-change detection are the ones built into
[Routebase](https://routebase.dev). Lint findings are therefore measured against Routebase's
built-in rules, which are a convention, not a standard; the tables label them as such. Breaking
changes are what those rules classify as breaking (endpoint or parameter removed, type changed,
required field added on the request side, response field removed, enum value removed, and so on).

## Headline numbers (measurement C, consumer view, 493 comparable pairs)

| Metric | raw | one vote per provider |
|---|---:|---:|
| Origin URL still answers with HTTP 200 | 63.8 % | 60.3 % |
| Contract changed structurally since 2023 | 48.9 % | 42.0 % |
| … of which with at least one breaking change | 66.8 % | 70.8 % |
| Breaking changes without a major version bump | 88.8 % | 87.7 % |
| Breaking changes with the version number unchanged | 53.4 % | 57.5 % |

Measurement B: 26.7 % of in-place updates to a published version changed the contract
structurally, and 30.8 % of those broke a client. The directory stores each declared version in
its own directory, so an unchanged version number there is the layout, not a finding.

Every table is in [`tables/tables-2026-09-14.md`](tables/tables-2026-09-14.md).

## Two views of every pair

The *product view* is the verdict Routebase's diff gave on the day of the run. The *consumer view*
carries the headline: the same rules after removing what a consumer cannot observe on the wire —
path placeholders compared positionally (`{scope}` renamed to `{resourceScope}` is the same
route), local `$ref`s inlined before the field-level diff, and pairs set aside when either side
references another document (the parser reads such references as an empty object). Both views are
in the data; the tables report both.

## Provider weighting

Four providers hold about half of all APIs in the directory. Every share is therefore reported
twice: raw per spec or pair, and with one vote per provider (the share per provider first, then
the mean across providers). The `megaProvider` flag marks the four.

## Data

`data/` holds one JSON line per document or pair with the provider replaced by a pseudonym
(`p0001` …) and every key, path, URL, commit hash, version string and parser message removed.
The aggregates do not depend on any of those fields. The corpus itself is public; this bundle
simply does not name anyone.

| File | Rows | One row per |
|---|---:|---|
| `data/snapshot.jsonl.gz` | 2,523 | preferred spec version (measurement A) |
| `data/history.jsonl.gz` | 106,083 | consecutive commit pair of one spec file (measurement B) |
| `data/refetch.jsonl.gz` | 1,927 | fetched origin URL (measurement C) |

`data/MANIFEST.sha256` lists the checksums; the export is deterministic.

## Reproduce the tables

```bash
python3 aggregate.py \
  --snapshot data/snapshot.jsonl.gz \
  --history  data/history.jsonl.gz \
  --refetch  data/refetch.jsonl.gz \
  --out      tables/tables-2026-09-14.md
```

Python 3.10 or newer, standard library only. The output is byte-identical across runs.

## Limits

- The directory is frozen since April 2023; the re-fetch is what makes the 2026 side current.
- The 2023 side of every pair is the directory's own YAML rendering with its fixes applied, not
  the provider's original file, so byte identity is not measurable; the tables define "changed"
  structurally.
- Documents the parser rejects are counted as not parsed and excluded from lint and diff numbers;
  the categories of rejection are tabulated. Documents above 30 MB are skipped (two of them).
- Google discovery, Postman, WADL and Swagger 1.2 origins were converted by the directory and are
  not re-fetched.

## Licence

Data and tables: [CC BY 4.0](data/LICENSE). Script: MIT (see `LICENSE`). The underlying
definitions in the apis.guru directory are CC0 where contributed by their authors and "fair use"
where acquired from public sources, per that project's README.
