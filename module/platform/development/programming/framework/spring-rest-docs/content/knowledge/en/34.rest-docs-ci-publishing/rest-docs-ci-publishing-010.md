# Versioning Documentation by API Version

## 1. Why Does API Documentation Need Versioning?

APIs evolve over time: new endpoints are added, request/response fields are expanded, validation rules change, or an older operation is deprecated. If documentation only lives at `/docs/latest`, API consumers running an older version may misread the new contract and integrate incorrectly.

In **SPRING_REST_DOCS**, HTTP tests using MockMvc, WebTestClient, or REST Assured generate snippets verifying requests, responses, payloads, parameters, and headers. Snippets are compiled with Asciidoctor/Markdown and integrated into the build/CI. The **CI and Publishing** chapter guides how to manage documentation as a product with a lifecycle, tying documentation to the API version it describes.

This lesson explains how to define documentation versions, preserve older releases, publish versioned paths, maintain a `latest` alias, handle deprecation, and check compatibility in CI.

After this lesson, you can:

- Distinguish API version, docs version, and build artifact version.
- Choose a URL/versioning strategy that matches your API policy.
- Generate documentation from the exact source/ref of an API release.
- Keep older documentation immutable while publishing new versions in parallel.
- Manage deprecation, sunset, and migration guides.
- Configure CI to verify documentation per API version.

## 2. Distinguishing Version Types

Do not use a single version number for every purpose without defining what it means.

| Version type | Meaning | Example |
| --- | --- | --- |
| API version | Contract called by clients | `/api/v1/products` or media type version |
| Documentation version | Documentation release describing a contract/release | `/docs/1.4/`, `/docs/2.0/` |
| Application release | Deployed application version | `catalog-service 2.7.3` |
| Documentation build | A single documentation artifact build | build number or commit SHA |

API version and application release are not necessarily identical. One application release may serve multiple API versions; conversely, multiple patch releases may preserve the same API contract. Documentation versions should tie to published contract milestones or releases, not necessarily increment on every CI build.

Example: `catalog-service 2.7.3` still serves API `v1`, while API `v2` runs in parallel. `/docs/v1/` and `/docs/v2/` must each describe their own contract accurately. Rebuilding `v1` documentation from old source should never silently alter already-published content.

## 3. Choosing an API Versioning Strategy

API versions can be expressed in several places:

| Strategy | Example | Considerations |
| --- | --- | --- |
| URL path | `/api/v1/products` | Easy to recognize, clear route separation |
| Query parameter | `/api/products?version=1` | Easy to overlook and awkward as a primary contract |
| Header | `X-API-Version: 1` | Stable URLs, though clients must send the header |
| Media type | `Accept: application/vnd.example.v1+json` | Clean representation distinction, more complex for clients/caches |

Spring REST Docs does not mandate a versioning strategy. It records the actual requests made in tests. Choose the strategy at the API design level, then ensure tests send the corresponding path/header/media type and snippets reflect that choice.

Example with URL versioning:

```java
mockMvc.perform(get("/api/v1/products/{id}", 42)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("v1-products-get",
        pathParameters(
            parameterWithName("id").description("Product ID")
        ),
        responseFields(
            fieldWithPath("id").description("Product ID"),
            fieldWithPath("name").description("Product name")
        )
    ));
```

Operation IDs can include the version (`v1-products-get`) to avoid snippet collisions across API versions sharing the same output directory. Even if each version has a separate output directory, maintain a consistent naming convention.

## 4. Tying Documentation Source to the Exact API Release

Versioned documentation must be generated from the source code and tests corresponding to that release. You can choose one of these models:

- **Release tag:** CI checks out tag `v1.4.0`, runs documentation tests, and builds docs for the release.
- **Release branch:** maintain a support branch such as `release/1.x`, accepting only bug fixes and corresponding docs updates.
- **Multi-version monorepo:** each API version has its own sources/tests or module; CI builds each module.
- **Contract snapshot:** store published contracts/schemas, then verify new implementations against the snapshot.

Do not build `/docs/1.4/` from the `main` branch developing API `v2` and merely rename the output directory to `1.4`. A directory name does not make the content match that version.

Release metadata should record at minimum:

- API version and corresponding release/tag.
- Commit SHA used to build the documentation.
- Build timestamp and toolchain versions.
- Support status: current, supported, deprecated, or retired.
- Migration guide link if breaking changes exist.

Commit SHA and build metadata can be placed on a version info page or in an artifact manifest. Avoid injecting build timestamps into every snippet if it causes documentation diffs on every build without adding value.

## 5. Organizing Output by Version

An output layout can look like this:

```text
build/site/
└── docs/
    ├── 1.4/
    │   ├── index.html
    │   ├── products.html
    │   └── migration.html
    ├── 2.0/
    │   ├── index.html
    │   ├── products.html
    │   └── migration.html
    └── latest -> 2.0
```

This is a logical structure; how aliases or redirects are implemented depends on hosting. With static hosting, `latest` can be a redirect page or a copy updated after a new release is approved. Never overwrite an older version directory with new content.

Example Gradle configuration accepting a version via property:

```groovy
def docsVersion = providers.gradleProperty('docsVersion')
    .orElse('local')

tasks.named('asciidoctor') {
    attributes 'api-version': docsVersion.get()
    outputDir = layout.buildDirectory.dir("site/docs/${docsVersion.get()}").get().asFile
}
```

This is an illustrative configuration; task names and Asciidoctor attributes must match your project's plugin. The release pipeline must pass `docsVersion` derived from the tag or verified metadata, rather than relying on the default `local` value.

## 6. Keeping Published Documentation Immutable

Once documentation `1.4` is published, consumers may bookmark links or rely on it in integration workflows. Therefore:

- Never automatically replace older version content with documentation from a newer branch.
- Fix errors in older version documentation via a reviewed patch, rebuilt cleanly from the release/maintenance source branch.
- Retain artifacts or source snapshots for reproducibility.
- Clearly note the update date if older version content is amended.
- Maintain a changelog so readers know what was corrected.

"Immutable" does not mean never fixing typos or critical errors. It means every change must be deliberate, traceable, and must not turn an older API's documentation into the newer API's contract.

## 7. Managing Breaking and Non-Breaking Changes

SemVer can be a useful convention if the project clearly defines its scope for the API. However, compatibility cannot always be inferred from the application version alone.

Commonly evaluated changes:

| Change | Compatibility risk |
| --- | --- |
| Adding an optional response field | Usually low risk for clients ignoring unknown fields, though still verify serializers/clients |
| Adding a required request field | Breaking for older clients |
| Removing or renaming a response field | Breaking |
| Changing a field's type | Potentially breaking |
| Changing status/error codes | Can break client logic |
| Changing validation rules | Can cause previously valid requests to be rejected |
| Adding a new endpoint | Usually non-breaking if there are no conflicts |

Spring REST Docs strict field descriptors help detect undocumented payload changes, but do not classify SemVer automatically. Reviewers must assess client impact and update API versions/changelogs according to policy.

## 8. Deprecation and Sunset

When an API version or operation is scheduled for retirement, documentation must clearly announce:

- Deprecated status.
- Version or start date of deprecation.
- Planned sunset/retirement date if decided.
- Replacement API and migration guide.
- Differences in requests, responses, authentication, or error behavior.
- Support channels and how to verify clients have migrated.

Example of authored documentation content:

```adoc
== API v1 — Deprecated

API v1 remains active during the transition period.
Please migrate to API v2 using the migration guide before the sunset date
announced in the service release schedule.

See link:migration-v1-to-v2.html[v1 to v2 Migration Guide].
```

Do not invent sunset dates in snippets or documentation unless approved by your organization. If the server sends deprecation-related headers, you can use `responseHeaders(...)` to document those headers, while prose must still explain their meaning and timeline.

## 9. Creating a Migration Guide from Contract Differences

Migration guides should describe changes by their impact on clients, not merely list technical commits.

| Topic | Questions to answer |
| --- | --- |
| Endpoint | How did the URL or version header change? |
| Request | Which fields were added, removed, retyped, or had validation changed? |
| Response | Which fields/status/error codes changed? |
| Authentication | Which scopes, tokens, or headers need updating? |
| Pagination/filtering | Did defaults, sort order, or cursors change? |
| Retry/idempotency | Do clients need to change retry behavior? |
| Rollout | How long can v1/v2 run concurrently? |

Example:

```markdown
## Migrating from v1 to v2

| v1 | v2 | Client action |
| --- | --- | --- |
| `GET /api/v1/products/{id}` | `GET /api/v2/products/{id}` | Update base path |
| `price` as integer VND | `price.amount` and `price.currency` | Update currency model |
| `status=ACTIVE` | `lifecycle=AVAILABLE` | Update enum mapping |
```

Tables must be cross-checked against snippets from both versions. Avoid copying long request/response examples manually when you can include the corresponding snippets from tests.

## 10. Checking Version Compatibility in CI

A pipeline can run the following check groups:

1. Documentation tests for the API version under active development.
2. Contract tests for supported versions.
3. Compatibility checks between the new contract and published snapshots.
4. Separate documentation builds for each version to be published.
5. Include/link and version metadata checks.
6. Verification that no new output overwrites an old version directory.

Example matrix:

| Job | Source | Output |
| --- | --- | --- |
| `docs-v1` | release branch/tag `v1.x` | `site/docs/1.x/` |
| `docs-v2` | branch/tag `v2.x` | `site/docs/2.x/` |
| `docs-current` | main | preview, does not automatically overwrite releases |
| `docs-compatibility` | contract snapshots | breaking-change report |

Not every project needs to maintain multiple branches long-term. If old sources can no longer build, retain the published documentation artifacts and only rebuild when controlled maintenance changes occur.

## 11. Separating Snippet Generation from Publishing

Split the pipeline into two stages:

**Build/verify:** check out the exact source, run tests, generate snippets, render documentation, verify links, and store an immutable artifact.

**Publish:** take the reviewed/approved artifact, deploy to the exact version directory, and update the `latest` alias once the release is confirmed.

This prevents every commit on `main` from automatically replacing the currently published documentation version. For pull requests, publish a preview to a dedicated URL or store artifacts for reviewers to inspect.

Example flow:

```text
Release tag / approved commit
          |
          v
Documentation tests
          |
          v
Generated snippets + Asciidoctor
          |
          v
Link/version/contract checks
          |
          v
Immutable docs artifact
          |
          v
Approval / release gate
          |
          v
Publish /docs/<version>/
          |
          v
Update /docs/latest/ when appropriate
```

## 12. Version Metadata in Documentation Pages

Readers need to know which version they are viewing. The landing page can display:

- The API version being described.
- Corresponding release/tag or commit.
- Release/update date.
- Support status.
- Links to previous/next versions and migration guides.

AsciiDoc example:

```adoc
= Catalog API v2
:api-version: 2.0
:api-release: 2.0.0
:api-status: Current

[NOTE]
This documentation covers API version {api-version}, release {api-release}.
Support status: {api-status}.
```

Attributes must be passed from verified or reviewed release metadata. Never derive `api-version` from a default fallback value and publish by mistake.

## 13. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `/docs/v1/` displays the v2 contract | Built from main and merely renamed output | Build from the exact version tag/branch |
| Old documentation silently changes | Publish overwrites version directory | Use immutable artifacts and reviewed maintenance releases |
| Snippet IDs overwrite each other | Multiple API versions share output directory and operation ID | Separate output directories or add version prefixes |
| `latest` points to a preview build | Alias updated on every build | Update only after the release gate |
| Docs version increments on every CI build | Confusing build number with contract version | Separate documentation build metadata from API version |
| Migration guide misses fields | Read only source code without comparing snippets/contracts | Diff request/response snippets and contract snapshots |
| Inconsistent sunset dates | Hard-coded in multiple places | Manage from owner-approved release metadata |
| Old version no longer builds | Old dependencies/sources lost | Archive published artifacts and maintenance branches as needed |
| Breaking changes go undetected | Ran only docs tests without compatibility checks | Compare new contracts against published snapshots |

## 14. Hands-On Exercise

Assume a service has API v1 and is preparing to release v2:

1. Identify the API versioning approach in use: URL, header, or media type.
2. Create separate tests and operation IDs for v1/v2.
3. Run documentation tests from the corresponding source/tag for each version.
4. Create independent output directories `docs/1.x/` and `docs/2.x/`.
5. Attach API version, release tag, commit SHA, and support status to the landing page.
6. Compare request/response snippets between the two versions.
7. Write a migration guide highlighting changed endpoints, fields, statuses, and validations.
8. Add CI jobs to build each version and a compatibility report.
9. Store versioned artifacts; never overwrite older release docs from main.
10. Update the `latest` alias only after the release is approved.

### Self-Assessment Questions

- How does API version differ from documentation version and build version?
- Why must documentation be built from the exact release tag or branch?
- When should output directories be separated per API version?
- Why should `latest` not automatically update on every main commit?
- How do Spring REST Docs strict descriptors help when comparing contracts?
- Why do docs tests not automatically classify breaking changes?
- Which categories of changes should a migration guide cover?
- What information do deprecation and sunset notices need so clients can plan?
- When should immutable artifacts be retained rather than rebuilding older version docs?

**Key takeaway:** Documentation must tie to the exact verified API contract and release. Build each version from its corresponding source, keep traceable historical artifacts, provide migration guides for changes, and update `latest` only after the release gate. Spring REST Docs supplies request/response evidence; versioning and compatibility policies still need to be defined and reviewed by the API team.

## References

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/reference/getting-started.html): configuring tests and generating snippets.
- [Spring REST Docs — Working with Asciidoctor](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/working-with-asciidoctor.html): authoring and including snippets.
- [Semantic Versioning 2.0.0](https://semver.org/): versioning and compatibility conventions.
- [RFC 8594 — The Sunset HTTP Header Field](https://www.rfc-editor.org/rfc/rfc8594.html): sunset information for HTTP resources.
- [RFC 9745 — The Deprecation HTTP Response Header](https://www.rfc-editor.org/rfc/rfc9745.html): header announcing deprecation.
