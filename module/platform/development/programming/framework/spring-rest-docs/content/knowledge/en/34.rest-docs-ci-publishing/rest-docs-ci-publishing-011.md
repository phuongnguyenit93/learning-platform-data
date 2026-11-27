# Distinguishing Preview Documentation and Production Documentation

## 1. Purpose and Context

In a Spring REST Docs workflow, HTTP tests generate snippets for requests, responses, payloads, parameters, and headers. The build then assembles snippets into Asciidoctor/Markdown, renders HTML, and can publish the documentation to a preview URL for review or to a production website for API consumers.

These two environments serve different purposes:

- **Preview documentation** is a preview tied to a specific change, typically a pull request, commit, or build. It helps reviewers check content and layout before release.
- **Production documentation** is the official documentation tied to an approved API version/release. This is the source that developers, partners, or API consumers are directed to access.

Never treat preview as production simply because both render successfully. Previews may contain unreleased endpoints, descriptions under review, experimental fixtures, or internal details. Production must have clear classification, versioning, approvals, access policies, and lifecycle management.

This lesson belongs to the **CI and Publishing** chapter of the **SPRING_REST_DOCS** module. The module creates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured; generates snippets, compiles Asciidoctor/Markdown, and integrates the build/CI.

After this lesson, you can:

- Distinguish the purpose and lifecycle of preview vs. production docs.
- Design URLs, access controls, and retention for each environment.
- Create previews per PR/commit without altering official documentation.
- Publish production docs by API version and release.
- Promote verified artifacts through review stages.
- Control data, secrets, caching, indexing, and links.
- Set up CI/CD, approval gates, rollbacks, and cleanup.

## 2. Comparing Preview and Production

| Criterion | Preview docs | Production docs |
| --- | --- | --- |
| Purpose | Review changes before release | Official guidance for a defined audience |
| Source | PR branch/commit or specific build | Approved release/tag |
| Content | May be incomplete, carries draft labels | Passed technical/security/editorial review |
| URL | Temporary, usually tied to PR/build | Stable URL by product/version |
| Audience | Reviewers, team, or invited partners | Public, partner, or internal per classification |
| Access | Usually restricted | Per release policy |
| Retention | Short, deleted after review/merge | Per release lifecycle and policy |
| Indexing | Should not be publicly indexed | Can be indexed if public docs |
| Cache | Short-lived, easy invalidation | Clear caching policy and versioning |
| Approval | Review/CI checks | Release owner and required approvals |
| Rollback | Delete preview or rebuild PR | Point back to previous release or restore version |
| Contract status | Proposed/changing | Official release contract |

A preview may be shared outside the team if policy allows, but the audience and access permissions must be clearly defined. An obscure URL is not access control.

## 3. Lifecycle of Preview Documentation

Previews are typically generated automatically when a pull request or commit needs review:

~~~mermaid
flowchart TD
    A["Developer opens PR"] --> B["Run REST Docs HTTP tests"]
    B --> C["Generate snippets"]
    C --> D["Assemble and render preview"]
    D --> E["Run link, secret and content checks"]
    E --> F{"Checks pass?"}
    F -->|No| G["Mark preview failed"]
    F -->|Yes| H["Upload isolated preview"]
    H --> I["Reviewer inspects URL"]
    I --> J{"PR merged or closed?"}
    J -->|No| I
    J -->|Yes| K["Promote approved release or delete preview"]
~~~

A preview should have:

- A build/commit identifier showing where content came from.
- A clearly visible banner marking it as preview/draft.
- A dedicated URL that never overwrites production URLs.
- Access control matching its classification.
- Retention period or cleanup when the PR closes.
- Secret scanning and validation before upload.
- Links to the corresponding PR/commit so reviewers can leave feedback.

### 3.1. Preview per PR or per Commit?

You can choose one of these approaches:

| Approach | Advantage | What to control |
| --- | --- | --- |
| One URL per PR | Easy to find and comment on during review | New builds must replace old previews safely |
| One URL per commit | Immutable artifact, exact traceability | Can create many previews and requires cleanup |
| One URL per branch | Easy to track long-lived branches | Content changes continuously; hard to tell which snapshot a reviewer saw |

A practical model is having a PR alias pointing to the latest commit's artifact while retaining artifacts by commit SHA for traceability. Display the commit/build clearly on the preview page.

## 4. Production Documentation Has a Release Lifecycle

Production docs should be published alongside an API release or a managed version milestone:

~~~mermaid
flowchart TD
    A["Release candidate"] --> B["Run tests and generate docs"]
    B --> C["Render versioned documentation"]
    C --> D["Security and contract review"]
    D --> E{"Approvals complete?"}
    E -->|No| X["Block release"]
    E -->|Yes| F["Publish production version"]
    F --> G["Update version navigation"]
    G --> H["Monitor links and feedback"]
~~~

Production docs require:

- Clear API version/release.
- Stable URLs and navigation across versions.
- Reviewed content.
- Access control tailored to public/partner/internal audiences.
- Metadata for commit, build, and release.
- Support/deprecation policy.
- Error-correction and rollback procedures.

Do not let production docs automatically track the `main` branch if the API contract has not been released yet. Builds from `main` can be candidates; production releases require separate triggers and approvals per release policy.

## 5. Separating URLs and Deployment Targets

Use separate URLs or deployment targets for preview and production. Illustrative examples:

| Environment | URL |
| --- | --- |
| PR preview | docs-preview.example.test/pr/482/ |
| Commit snapshot | docs-preview.example.test/commit/ab12cd3/ |
| Production latest | docs.example.test/api/ |
| Specific version | docs.example.test/api/v2/ |
| Internal docs | docs-internal.example.test/services/orders/ |

Domains and paths here are examples only. Choose URLs according to your actual infrastructure, DNS, access policy, and versioning strategy.

### 5.1. Do Not Share the Same Publish Directory

Never allow preview jobs to write into production's directory/bucket. If sharing the same object storage or hosting platform, separate prefixes, buckets, projects, or deployment environments and credentials.

Example artifact structure:

~~~text
artifacts/
├── preview/
│   ├── pr-482/
│   └── pr-483/
└── production/
    ├── v1/
    ├── v2/
    └── latest/
~~~

Separating targets prevents a PR from accidentally overwriting official documentation. Production write permissions are granted only to approved publish jobs.

## 6. Access Control and Audience

Previews are not private by default. Some static hosts create public URLs even when the URL contains a PR number or random token. Verify real access control at the hosting/storage layer.

| Audience | Preview | Production |
| --- | --- | --- |
| Public API | Can use temporary URL, noindex before release | Public site |
| Partner-only | Restrict to authorized reviewers | Partner authentication/authorization |
| Internal | SSO/VPN or access gateway | Internal portal |
| Restricted | Authorized group only | Separately approved system |

Principles:

- Use least privilege for deployment credentials.
- Preview jobs have no write permission to production.
- Fork PRs must not access repository secrets by default.
- Never place credentials in URL queries, page source, or JavaScript bundles.
- Check artifact download permissions, not just repository read permissions.
- Use hosting authentication mechanisms rather than relying on hard-to-guess URLs.

### 6.1. Noindex Is Not Security

You can set headers or metadata asking search engines not to index a preview, but `noindex` does not stop anyone with the URL from accessing it. For internal documentation, enforce authentication/authorization at the server, gateway, or artifact store.

For unreleased public previews, combine `noindex`, access restrictions, and short retention. Never treat robots directives as a security boundary.

## 7. Data and Content Allowed to Appear

Previews may contain unreleased changes, but that never permits secrets or PII. Both preview and production must meet the same security baseline:

- Use synthetic fixtures in HTTP tests.
- Preprocess `Authorization`, `Cookie`, `Set-Cookie`, and body tokens.
- Scan generated snippets, assembled docs, and rendered HTML.
- Avoid uploading raw test logs/traces unnecessarily.
- Strip internal hostnames, private IPs, and test-only routes from public bundles.
- Determine audience/classification before publishing.

Previews may contain draft content, but must be labeled clearly so readers do not mistake it for a released contract.

### 7.1. Draft Banners and API Status

A preview banner should state:

- This is a preview, not official documentation.
- Which PR/commit/build is being viewed.
- Creation timestamp.
- Link to the pull request or source change.
- How to submit feedback.

Never use a banner as a substitute for classification/access control. An internal preview must still be protected like internal documentation.

## 8. Artifact Promotion: Build Once, Release Controlled

Whenever possible, promote the exact reviewed artifact rather than rebuilding a separate one for production. This reduces the risk of preview and production diverging due to time, dependencies, or generated inputs.

Workflow:

1. Build a candidate from an identified commit.
2. Run tests, generate snippets, and render docs.
3. Scan and review the artifact.
4. Attach commit/build/version metadata.
5. After approval, promote that exact artifact to the production target.
6. Record the destination and release identifier.

Artifacts should be immutable after review. If source, dependencies, templates, or build configuration change, create a new artifact and re-run checks.

### 8.1. When Must You Rebuild?

Rebuilding may be required if production needs environment-specific configuration, a public base URL, or version metadata. In that case, define what is allowed to differ:

- Contract content and snippets must stay identical.
- Base URL/permalinks may be substituted per environment.
- Secrets/configuration must never be embedded in HTML.
- The production build must re-run validation and scanning.
- The published artifact must have its own commit/build provenance.

Never claim two artifacts are identical if a rebuild actually altered content.

## 9. Versioning and Production Navigation

Production docs should retain supported API versions:

~~~text
/api/
├── latest/
├── v1/
└── v2/
~~~

Principles:

- Versions in URLs must match the API contract.
- `latest` points to the version defined by policy, never automatically to a release candidate.
- Older versions show clear support/deprecated status.
- Links from older versions to migration guides/newer versions must work.
- Unreleased preview versions do not appear in production navigation.
- Do not overwrite older version docs when contract history must be kept.

An API may be versioned by URL, header, or media type. Documentation organization must explain the actual versioning strategy; never assume every project puts `/v1/` in endpoints.

## 10. Caching, Indexing, and Retention

Preview and production need different cache policies:

| Component | Preview | Production |
| --- | --- | --- |
| Browser/CDN cache | Short or `no-store` depending on data | Cached by version/release |
| Search indexing | Typically `noindex` | Indexed if public |
| Artifact retention | Short, tied to PR lifecycle | Per release/audit policy |
| Cleanup | When PR closes or expires | Per deprecation/retention policy |
| URL stability | Temporary | Stable |
| Purge | When preview is replaced/deleted | On incident or release correction |

For versioned production docs, URLs can be immutable and cached long-term. The `latest` alias needs proper caching/invalidation so readers receive new releases. Previews should avoid long caching that causes reviewers to view stale commit content.

## 11. CI/CD Separating Preview and Production

Pipelines can be split into workflows or jobs with distinct permissions:

~~~mermaid
flowchart TD
    A["Pull request"] --> B["Docs build and tests"]
    B --> C["Secret scan and link validation"]
    C --> D["Upload isolated preview"]
    D --> E["Review and PR approval"]

    F["Release tag"] --> G["Build release candidate"]
    G --> H["Tests, scan and render"]
    H --> I["Release approval"]
    I --> J["Promote artifact to production"]
    J --> K["Post-deploy smoke checks"]
~~~

### 11.1. PR Workflow

A PR workflow typically:

- Runs HTTP tests and generates snippets.
- Assembles/renders docs.
- Runs secret scanning, link checks, and Markdown/Asciidoctor validation.
- Uploads a preview artifact or deploys a preview URL.
- Posts the preview link to the PR via an authorized CI mechanism.
- Cleans up the preview when the PR closes/merges or retention expires.

Never allow fork PRs to use deployment secrets or production credentials. If previews are needed for forks, use a secret-free sandbox with synthetic data.

### 11.2. Release Workflow

A release workflow should:

- Run only from a tag/release event or protected trigger.
- Verify commit and version.
- Run tests from a clean build.
- Create and scan the candidate artifact.
- Require approvals per policy.
- Promote the approved artifact.
- Run smoke checks on production URLs.
- Record release metadata and rollback target.

Preview success does not automatically equal production approval.

## 12. Post-Deploy Checks and Rollback

After publishing production docs:

- Open public/internal URLs as the intended audience.
- Verify version, navigation, and canonical links.
- Check assets, anchors, and search.
- Verify access controls for internal/partner docs.
- Run smoke checks on the landing page and key operations.
- Confirm cache/CDN serves the right release.
- Monitor broken links and feedback.

If released docs are wrong:

1. Halt further rollout.
2. Identify affected artifacts/versions.
3. Point the alias back to the previous release or redeploy a known-good artifact.
4. Purge cache/CDN if necessary.
5. Remove any preview/artifact containing unauthorized content.
6. If a secret was exposed, revoke/rotate per incident response procedures.
7. Create a fix, re-run scanning/review, and publish.
8. Document the incident, impact scope, and corrective actions.

Rolling back docs does not necessarily roll back the API service. However, if wrong docs could cause consumers to call the API incorrectly, coordinate with the API owner and release manager.

## 13. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Preview overwrites production | Shared target or credentials | Separate targets and write permissions. |
| Preview URL accessed by outsiders | Assumed hard-to-guess URL is private | Enable real access control on hosting. |
| Reviewers see stale commit content | Preview cached too long or wrong alias update | Tag commit ID and purge/invalidate. |
| Draft mistaken for official contract | Missing clear banner/status | Add preview label and PR/build provenance. |
| Production contains unreleased endpoints | Copied entire preview bundle | Build production allowlist from release scope. |
| Preview contains secrets | Scanned only production | Scan every preview and artifact. |
| Fork PR uses deployment secret | Workflow granted overly broad permissions | Never expose secrets to untrusted PRs. |
| Production `latest` points to release candidate | Missing version/release gate | Update alias only after approval. |
| Old version disappears | Overwrote same output path | Keep immutable versioned outputs. |
| Rollback cannot restore docs | Previous artifact not saved | Store release artifacts/provenance. |
| Preview content differs from production | Rebuilt with different inputs | Promote the same artifact or document rebuild and re-verify. |

## 14. Hands-On Exercise

Set up a pipeline for an API module with pull request previews and versioned production docs:

1. Run REST Docs tests to generate snippets from MockMvc or WebTestClient.
2. Render docs into an isolated artifact for the PR.
3. Add a preview banner, PR number, commit SHA, and build timestamp.
4. Restrict preview access by audience; verify `noindex` is not treated as access control.
5. Configure retention/cleanup when the PR closes.
6. Build a release candidate from a tag and run tests, secret scanning, and link validation.
7. Build the versioned production bundle and check the allowlist.
8. Require release approval before publishing.
9. Promote the approved artifact or clearly record if a rebuild is needed.
10. Update the `latest` alias after a successful release.
11. Run post-deploy smoke checks and verify CDN/cache.
12. Simulate rolling back to the previous artifact and cleaning up the preview.

**Completion criteria:** previews have separate URL/access/retention; production contains only approved, properly versioned content; CI/CD separates PR and release permissions; artifacts carry provenance; promotion and rollback are reproducible.

## References

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [GitHub Actions — Deploying with GitHub Actions](https://docs.github.com/en/actions/deployment/about-deployments)
- [GitHub Actions — Workflow Artifacts](https://docs.github.com/en/actions/using-workflows/storing-workflow-data-as-artifacts)
- [GitHub — Managing Environments for Deployment](https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-deployments/managing-environments-for-deployment)
- [OWASP — CI/CD Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/CI_CD_Security_Cheat_Sheet.html)
- [Google Search Central — Block Search Indexing](https://developers.google.com/search/docs/crawling-indexing/block-indexing)
