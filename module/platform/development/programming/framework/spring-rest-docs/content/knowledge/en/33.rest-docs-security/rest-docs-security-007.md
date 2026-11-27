# Reviewing Documentation Before Publishing

## 1. Objectives and Context

REST API documentation generated from HTTP tests can accurately reflect the requests and responses that tests executed. However, **passing tests and successfully rendered docs are not sufficient conditions for publishing**. Before release, the team must verify that the content matches the API contract, exposes no sensitive data, targets the right audience, and has been approved by an authorized owner.

With Spring REST Docs, review must cover handwritten sources, generated snippets, assembled pages, and rendered output. A header masked on the main page may still appear in a curl snippet, HTML, or CI artifact. An internal operation may accidentally be included in the public bundle. A relative link may point to an internal page or an unauthorized resource.

This lesson belongs to the **Security** chapter of the **SPRING_REST_DOCS** module. The module creates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured; generates snippets for requests, responses, payloads, parameters, and headers; compiles Asciidoctor/Markdown; and integrates with build/CI pipelines.

After this lesson, you will be able to build a pre-publish review process; distinguish technical, security, privacy, and content-approval checks; verify snippets; classify public, internal, and partner-only docs; inspect secrets, PII, hostnames, links, and artifacts; and clearly assign reviewer and release-owner responsibilities.

## 2. Why Review Before Publishing?

REST Docs increases confidence by generating snippets from HTTP tests, but tests only prove behavior checked within test fixtures and the test environment. They do not automatically verify:

- Whether an operation is authorized for public release or is internal-only.
- Whether examples contain tokens, cookies, emails, or personal data.
- Whether hostnames, IPs, paths, or headers reveal internal architecture.
- Whether handwritten descriptions accurately capture semantics and business constraints.
- Whether links, images, and artifacts are accessible to the intended audience.
- Whether the documentation exposes an unreleased feature or deprecated endpoint.

Review is the content control gate before documentation leaves the workspace/build environment.

## 3. Identifying Audience and Classification

Before detailed review, determine who will read the documentation and where it will be published:

| Classification | Audience | Example |
| --- | --- | --- |
| Public | Any internet user | Public API, sandbox contract, integration guides. |
| Partner-only | Authorized partners | Partner APIs, callback contracts, onboarding. |
| Internal | Employees and internal services | Service-to-service APIs, operational endpoints. |
| Restricted | Groups with specific privileges | Admin APIs, security flows, sensitive operational data. |

Classification must be confirmed by the API owner or organizational policy. Do not assume that an endpoint with path /internal is definitely private, or that a simple endpoint can be public.

### 3.1. The Public Bundle Must Be Allowlisted

For public documentation, explicitly define which pages/operations are permitted for publication. Build the public bundle from a reviewed allowlist rather than copying all generated docs.

Verify that operations have an owner; methods/paths match the release; no admin/internal/test-only routes are included; no links point to internal docs; no private hostnames, IPs, environment names, or service topologies are exposed; and no unreleased features are included.

If classification is unclear, keep the content out of the public bundle until the owner confirms.

## 4. Review Layers

| Layer | Key Question | Appropriate Reviewer |
| --- | --- | --- |
| Technical accuracy | Do snippets and descriptions match API behavior? | API developer/test owner. |
| Security | Are secrets, auth details, or internal info exposed? | Security reviewer/service owner. |
| Privacy/data | Is there PII or real customer data? | Data/privacy owner per policy. |
| Audience/classification | Does content match public/partner/internal scope? | API/product owner. |
| Editorial/usability | Can readers understand and use it? | Documentation reviewer/API consumer. |
| Release approval | Do the artifact version and destination match? | Release owner/publisher. |

One person may hold multiple roles if policy permits. However, the content author should not self-approve restricted content when organizational policy requires independent approval.

## 5. Technical Review: Snippets and Contracts

Verify that generated snippets come from current tests:

- HTTP tests pass on a clean build.
- Operation identifiers are accurate and unique.
- Request methods, paths, and query parameters match.
- Request/response headers match the contract.
- Status codes and response bodies match assertions.
- Field descriptors are not missing or misdescribed.
- Important error scenarios are documented.
- Snippets belong to the right operation/scenario and are not overwritten.
- Final pages include the right files and extensions.

Do not look only at the rendered page. When investigating, compare the test, generated snippet, and assembled content to find where a discrepancy originated.

### 5.1. Test Coverage and API Coverage

A page having snippets does not prove the entire API is documented. Build an operation inventory from the release scope and compare it with the docs:

- Every published operation has corresponding tests and documentation.
- Operations excluded from the release bundle have a documented reason.
- Important status/error scenarios are described.
- Deprecated operations are appropriately labeled.
- Versioned endpoints reside in the right section/version.

You do not need to publish every internal test. The goal is documentation that suffices for the intended audience and does not give a misleading impression of API coverage.

## 6. Security Review and Secret Scanning

Inspect every output layer, not just source Markdown:

1. Generated snippets directory.
2. Assembled Markdown/Asciidoctor source.
3. Rendered HTML/PDF.
4. Uploaded test reports and logs.
5. CI artifacts and preview deployments.
6. Public site after publishing.

Look for values such as Authorization bearer/basic credentials, Cookie/Set-Cookie, session IDs, CSRF tokens, API keys, client secrets, access/refresh tokens, passwords, private keys, signed URLs, reset codes, internal hostnames, private IPs, file paths, environment names, and stack traces containing connection strings.

Use sentinels in test fixtures to prove preprocessors masked them properly. Secret scanners complement redaction; they do not replace using synthetic data from the very start of tests.

### 6.1. False Positives

An example string might accidentally resemble a valid credential. Do not use real tokens and rely solely on "it was masked on the main page." Scan all outputs and artifacts before upload.

If a scanner reports a false positive, the reviewer verifies the source and records a narrowly scoped exception. Do not add a broad allowlist just to make CI green.

## 7. Privacy and Sample Data Review

Check emails, phone numbers, addresses, real person names, traceable customer/account/order IDs, birth dates, financial details, free-text fields, and URLs/error messages containing identifiers.

Prefer synthetic fixtures with recognizable conventions, such as the example.test domain and test-only identifiers. If you must preserve data shapes to illustrate validation, keep the format and replace values with synthetic data.

Do not include PII in documentation just because endpoint tests currently use fixtures taken from a production snapshot.

## 8. Reviewing Internal Information and Environment Details

HTTP snippets can expose internal hostnames/service discovery names, private IPs/ports, namespace/cluster/cloud resource identifiers, debug headers, trace IDs, gateway/proxy details, file paths, usernames, or unreleased version/build metadata.

Use URI preprocessors to normalize scheme/host/port when appropriate, while verifying API scope. If paths/queries contain sensitive information, handle them separately; changing the host does not mask queries or paths.

Public documentation should use a documentation/sandbox hostname, not an internal address captured from CI.

## 9. Reviewing Links, Assets, and Navigation

Check links in both source and rendered sites:

- Do internal links point to the right page/anchor?
- Does any public page link to an internal site?
- Do external links use the official domain?
- Are images, diagrams, and downloadable files approved for publication?
- Do any links contain signed query values or access tokens?
- Are base URLs and relative paths correct when deployed?
- Does navigation reveal restricted section names?

Run a link checker on the final output. A link that resolves successfully can still lead to content meant for the wrong audience; reviewers must verify the classification of the destination.

## 10. Reviewing Content and Reader Experience

Verify API methods/paths and purpose; authentication/authorization requirements; required/optional fields and constraints; status codes/error semantics; whether example values work in the sandbox; whether placeholders are explained; versioning/deprecation/compatibility; consistency across overview, operation, and schema; and language, headings, tables, and code blocks.

Do not hand-edit generated snippets to make examples look nicer if editing causes snippets to no longer reflect tests. If friendlier presentation is needed, adjust templates or surrounding prose.

## 11. Pull Request Review Workflow

~~~mermaid
flowchart TD
    A["Author updates tests/docs"] --> B["CI generates snippets"]
    B --> C["Redaction and secret scan"]
    C --> D["Assemble and render"]
    D --> E["Technical review"]
    E --> F["Security/privacy review"]
    F --> G["Audience and editorial review"]
    G --> H{"Required approvals complete?"}
    H -->|No| X["Do not publish"]
    H -->|Yes| I["Release approval"]
    I --> J["Publish approved artifact"]
~~~

A PR should show source/test changes, generated snippet diffs, rendered preview artifacts, secret scan/link check results, audience/classification, and reviewer/owner approval status.

Reviewers should inspect the final output, not only Markdown sources. When snippets change due to an API contract change, verify the change is intentional.

## 12. Pre-Publish Checklist

### Content and Technical

- [ ] Clean build runs HTTP tests and generates fresh snippets.
- [ ] Operation identifiers do not collide.
- [ ] Requests/responses/statuses/fields match the contract.
- [ ] Public operations are in the inventory/allowlist.
- [ ] Deprecated/unreleased operations are handled properly.
- [ ] Final pages include the correct snippets and render successfully.

### Security and Privacy

- [ ] Authorization, Cookie, Set-Cookie, and CSRF values have been handled.
- [ ] Bodies contain no passwords, tokens, API keys, or private keys.
- [ ] Query strings and signed URLs contain no secrets.
- [ ] No PII or production data is present.
- [ ] No internal hostnames, IPs, file paths, or debug details are present.
- [ ] Secret scanning ran on snippets, assembled docs, and rendered output.
- [ ] CI logs/artifacts comply with policy.

### Audience and Release

- [ ] Public/partner/internal/restricted classification is confirmed.
- [ ] Public bundle contains only allowlisted operations.
- [ ] Links/assets target the appropriate audience and destination.
- [ ] Authorized owners and reviewers have approved.
- [ ] Artifact version/commit/destination is recorded.
- [ ] Preview artifact retention/access complies with policy.
- [ ] Publish job uses only artifacts that passed every gate.

## 13. Review Evidence and Traceability

| Field | Example |
| --- | --- |
| Documentation version | v2.4 |
| Source commit | Git commit SHA |
| Build ID | CI run identifier |
| API owner | Team/service owner |
| Classification | Public or Internal |
| Test status | Passed |
| Secret scan | Passed, scanner/version |
| Link/render validation | Passed |
| Approvals | Reviewer identities per policy |
| Destination | Approved site/project |
| Published at | Release timestamp |

Manifests must not contain tokens, environment variables, or raw requests/responses. Store only status and required references.

## 14. Post-Publish: Monitoring and Rollback

After release:

- Check actual public/internal URLs.
- Verify access controls and navigation.
- Verify artifacts are not exposed via directory listing or broadly shared links.
- Monitor broken links and API consumer feedback.
- Update docs alongside releases when contracts change.
- When a secret/PII is detected, remove or restrict access per incident policy.
- Rotate/revoke real credentials if exposure is possible.
- Clean up CI artifacts, caches, Git history, and mirrors per each system's procedures.
- Publish the corrected version after re-scanning and re-reviewing.

Do not treat fixing the source and republishing as sufficient if the old version remains in CDNs, artifact stores, or caches.

## 15. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| CI green yet public docs expose internal endpoint | Tested/rendered only, no classification | Public allowlist and owner approval. |
| Token absent on main page yet present in artifact | Scanned only one output location | Scan snippets, reports, HTML, and artifacts. |
| Reviewer sees only Markdown source | No rendered preview | Attach preview artifact in PR. |
| Docs describe wrong status code | Did not cross-check snippet/test | Review contract and assertions. |
| Public link points to internal page | Did not verify destination audience | Link review and classification. |
| Example contains production data | Fixture copied from real snapshot | Replace with synthetic data. |
| Scanner has false positives | Pattern/allowlist too broad | Sentinels and narrowly scoped exceptions. |
| Release cannot be traced | Did not save commit/build/approval | Manifest containing no secrets. |
| Old version still exposed after fix | CDN/artifact/cache not expired | Removal/retention per provider. |
| Nobody takes approval responsibility | Roles/owners unclear | Assign API owner, security reviewer, publisher. |

## 16. Practice Exercise

Prepare a documentation release for an API with public endpoints, partner callbacks, and internal admin operations.

1. Create an inventory of operations intended for publication.
2. Classify each operation as public/partner/internal/restricted.
3. Run clean REST Docs tests and generate snippets.
4. Check contracts, identifiers, error scenarios, and generated diffs.
5. Scan snippets, assembled docs, HTML, reports, and CI artifacts.
6. Check for PII, secrets, hostnames/IPs, and query strings.
7. Render preview, run link checker, and verify navigation.
8. Build the public bundle from an allowlist; confirm it excludes partner/internal pages.
9. Assign API owner, security/privacy reviewer, and release approver.
10. Create a manifest containing commit, build, classification, scan status, and approvals.
11. Publish only after all gates pass.
12. Simulate a post-publish secret leak and practice rollback, rotate/revoke, and artifact cleanup.

**Completion criteria:** clear inventory/classification exists; generated docs match the contract; secret/privacy scans pass; rendered preview is reviewed; public bundle contains only approved content; approvals/manifest are traceable; and a post-publish response plan is in place.

## References

- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html)
- [Spring REST Docs — Preprocessing](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/preprocessors.html)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [OWASP — Privacy by Design](https://owasp.org/www-project-top-10-privacy-risks/)
- [OWASP — CI/CD Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/CI_CD_Security_Cheat_Sheet.html)
