# Checking Documentation in Pull Requests

REST API documentation generated from Spring REST Docs must evolve alongside the code and API contract. A pull request (PR) is the right point to verify that link: documentation tests must run, snippets must be freshly generated, Asciidoctor must render successfully, and reviewers need to inspect changes before merging.

A PR may alter an endpoint, status, header, payload, or field semantics without updating the prose explanation. If CI only verifies that the application builds, these changes can slip past review. Integrating documentation generation and verification into PR CI detects missing snippets, broken includes, outdated examples, and sensitive data before code is merged.

This lesson belongs to the **CI and Publishing** chapter of the `SPRING_REST_DOCS` module. The module creates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured, generates snippets for requests, responses, payloads, parameters, and headers, and then compiles Asciidoctor/Markdown and integrates it into the build and CI.

## 1. Learning Objectives

After this lesson, you can:

1. Design CI checks that run on pull requests.
2. Execute documentation tests and render documentation in a PR pipeline.
3. Detect missing, stale, or no-longer-included snippets.
4. Compare rendered documentation between the base branch and the PR branch.
5. Attach HTML/PDF or previews to the PR for reviewers to inspect.
6. Set up failure gates for tests, rendering, and sensitive-data checks.
7. Distinguish PR documentation checks from official documentation publishing.

## 2. Why Must Documentation Be Checked in Pull Requests?

An API change can affect status codes, response headers, fields, data types, query/path parameters, or snippet identifiers. Without regenerating documentation in the PR, reviewers must guess the impact or wait until the release pipeline.

PR checks provide early evidence that tests, snippets, and documentation pages remain consistent. They also create an opportunity to review contract diffs before merging.

## 3. CI Flow for Pull Requests

```text
Pull request opened / updated
             │
             ▼
Checkout PR revision
             │
             ▼
Clean generated output
             │
             ▼
Run unit + documentation tests
             │
             ├── Failure ──► Fail required check
             │
             ▼
Generate fresh snippets
             │
             ▼
Validate includes and sensitive data
             │
             ▼
Render Asciidoctor / Markdown
             │
             ▼
Compare rendered docs (optional)
             │
             ▼
Upload preview artifact
             │
             ▼
Reviewer inspects changes
             │
             ▼
Merge when required checks pass
```

A PR pipeline usually creates a preview artifact instead of automatically publishing to the production website. Official publishing should be a separate step after merge or after an approved release.

### 3.1. What Should Run on Every PR?

At minimum: relevant documentation tests, Asciidoctor/Markdown rendering, validation of required includes, secret scanning on snippets/output, and saving test reports along with preview artifacts.

For large repositories, you can run all docs tests. Only run a subset by module/path when a reliable dependency-detection mechanism exists; otherwise, shared changes may affect other operations that the pipeline leaves unchecked.

## 4. Running Tests and Rendering from the PR Revision

The PR job must check out the exact commit or merge revision under test. Do not fetch snippets from the main branch or artifacts from a previous build.

Gradle example:

```bash
./gradlew clean test asciidoctor
```

Maven example:

```bash
./mvnw clean verify
```

These commands assume the build has configured tasks/lifecycles so documentation tests run before Asciidoctor. If the project separates a dedicated docs task, invoke the right snippet-generating task and ensure the renderer depends on it.

### 4.1. Cleaning Output Before Generating Snippets

If a test is deleted or its identifier is renamed, stale snippets may remain in the workspace and let Asciidoctor render successfully even though the new operation produced no files. CI should generate output from a clean state or delete the `generated-snippets` directory before documentation tests. Do not restore snippets from a cache of unknown commit provenance.

## 5. Checking Snippets and Includes

After tests, the PR pipeline should verify that the files included by AsciiDoc actually exist. Example:

```asciidoc
=== Request

include::{snippets}/orders-get/http-request.adoc[]

=== Response

include::{snippets}/orders-get/http-response.adoc[]

=== Response fields

include::{snippets}/orders-get/response-fields.adoc[]
```

If a test does not generate response-fields.adoc because the descriptor was not declared, that include will fail. That is a bug to fix in the test or documentation content; do not create empty files just to make CI green.

### 5.1. Checking Identifiers

The identifier passed to document("orders-get", ...) normally creates a snippet directory with the same name. When renaming an identifier, the include must be updated. A validation script/task can read the list of includes and verify file existence before rendering.

## 6. Reviewing Documentation Changes in a PR

There are two types of changes reviewers need to examine:

1. **Source documentation:** updated AsciiDoc/Markdown, descriptors, and tests.
2. **Rendered documentation:** HTML/PDF generated from the PR's sources and snippets.

Source diffs may not show the visual impact of Asciidoctor. Therefore, save HTML/PDF or create a preview so reviewers can inspect headings, code blocks, tables, links, and included snippets.

### 6.1. Comparing Against the Base Branch

You can render documentation from both the base branch and the PR branch and compare the outputs to identify new/removed endpoints, changed status/headers/fields, snippets modified due to contract updates, missing content from broken includes, and noisy diffs caused by timestamps or random IDs.

For diffs to be useful, test fixtures and preprocessors should produce deterministic output. If dynamic data is not normalized, PRs may contain noisy diffs that cause reviewers to overlook real changes.

### 6.2. Do Not Treat Every Diff as an Error

Legitimate API contract changes will change the documentation. PR checks should provide diffs and require review, rather than automatically blocking every snippet change. Failure gates are for test failures, render failures, missing files, or policy violations; intentional correctness is a review decision.

## 7. Attaching Previews to Pull Requests

Depending on the CI provider, you can upload HTML/PDF as artifacts, publish a preview to a temporary environment tied to the PR, attach a preview link, or store generated snippets alongside test reports for debugging.

If using preview deployments, each PR should have a distinct URL/identifier, a cleanup expiration, and must not overwrite production documentation. Preview access permissions should match the sensitivity of the API documentation.

### 7.1. Artifacts Must Be Tied to the Commit

Previews, snippets, and test reports must belong to the same revision. Attach the commit SHA/build ID to metadata or artifact names to prevent reviewers from viewing HTML from a different commit than the source under review.

## 8. Failure Gates for PR Checks

Conditions that should fail a required check:

1. Required unit/documentation tests fail.
2. Documentation tests are unexpectedly skipped.
3. A required snippet identifier or included file is missing.
4. Asciidoctor/Markdown rendering fails.
5. Secret scanning detects tokens, API keys, or forbidden data.
6. Preview artifacts are not produced when required by the pipeline.
7. Test reports or artifacts do not match the revision under check.

Do not use continue-on-error for mandatory verification steps. If an unrelated group of tests is allowed to be skipped, separate the job clearly so documentation tests remain a required check.

### 8.1. A Green Build Does Not Replace Content Review

A green build only proves automated steps passed. It does not prove endpoint descriptions are clear or examples suit integrators. Reviewers still need to read the changed content, especially when status codes, headers, fields, or API semantics change.

## 9. Checking Sensitive Data Before Preview

PR artifacts may be accessible to more people than test environments. Check Authorization, Cookie, Set-Cookie, API keys, access/refresh tokens, authorization codes, callback URLs containing tokens/signatures, emails, phone numbers, real tenant/user IDs, and internal hostnames/IPs that should not be exposed.

Prefer dummy fixtures from the start. Preprocessors can replace/remove values in snippets, but should not be the sole line of defense. Secret scanning must run on generated snippets and rendered HTML/PDF, not only on source code.

If a real secret is found in a PR artifact, stop the pipeline, remove the artifact/preview, and handle the credential per organizational procedures. Do not merely edit the file and leave the old artifact accessible.

## 10. General PR Workflow Example

The example below illustrates logical steps, not runnable configuration as-is for a specific CI provider:

```yaml
pull_request:
  jobs:
    rest-docs-check:
      steps:
        - checkout pull request revision
        - run: ./gradlew clean test asciidoctor
        - run: ./gradlew verifyDocs
        - run: scan generated snippets and rendered docs
        - upload: build/docs and test reports
```

Event names, checkout actions, upload syntax, and the verifyDocs task depend on the CI platform/build script. Ensure the job runs on the PR revision, tests actually generate snippets, the renderer runs after tests, and artifacts are tied to that commit.

### 10.1. Required Status Check

Mark the documentation job as a required status check in branch protection/rulesets if repository policy requires documentation to always be verified before merge. Then a PR cannot merge if documentation tests, rendering, or mandatory validation fail.

Permission to configure branch protection typically belongs to repository administrators. This lesson describes how to structure the checks; enabling the rule must be performed in the corresponding repository settings.

## 11. Distinguishing PR Validation and Publishing

| Stage | Goal | Output |
| --- | --- | --- |
| Pull request | Verify correctness and generate preview for review | Test report, snippets, HTML/PDF preview |
| After merge | Confirm status on main branch | Artifacts built from the merged commit |
| Release/publish | Publish official documentation | Website or versioned documentation |

A PR pipeline should not automatically replace production documentation without an approved publishing process. Previews aid review; publishing is a separate action with version and access control.

## 12. Common Errors and Fixes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| PR green yet snippets are stale | Output not cleaned or old cache used | Generate snippets from a clean state |
| Asciidoctor reports missing include | Tests did not run or identifier mismatch | Check test report and include path |
| Preview does not match PR source | Artifact taken from another commit | Tag commit SHA and pass artifacts within the same run |
| Too many documentation diffs | Random timestamps/IDs | Deterministic fixtures and preprocessors |
| PR fails on valid snippet changes | Treating every diff as an error | Let reviewers evaluate contract diffs |
| Secret appears in preview | Scanned only source or raw requests | Scan generated snippets and rendered output |
| Documentation tests do not run | Filter/profile/skip property | Check test count and required job |
| Preview persists after PR closes | No cleanup lifecycle | Configure expiration and cleanup |
| PR merges despite docs job failure | Job is not a required check | Configure branch protection/rulesets |
| Markdown preview lacks snippets | Using Asciidoctor syntax as default Markdown | Add an explicit insertion/conversion step |

## 13. Hands-On Exercise

Set up a PR check for the orders API. The PR modifies a response field and adds a response header. AsciiDoc documentation includes request, response, headers, and fields.

**Tasks:**

1. Create a job running on the pull request revision.
2. Clean generated output before documentation tests.
3. Run snippet-generating tests and render Asciidoctor after tests.
4. Verify all included identifiers/files exist.
5. Generate HTML/PDF previews and upload them as PR artifacts.
6. Compare documentation diffs with the base branch.
7. Confirm the new response field/header appears properly in snippets and descriptors.
8. Scan tokens, cookies, and fixture data in both snippets and rendered artifacts.
9. Set the job as a required check if repository policy requires it.
10. Separate PR previews from official documentation publishing after merge/release.

**Completion criteria:** the PR pipeline runs on the right revision; tests and rendering succeed; fresh snippets are generated; diffs/previews are ready for review; secret scan passes; mandatory failures block merge; production documentation is never overwritten automatically.

## 14. Key Takeaways

- Pull requests are the place to verify documentation alongside API changes before merging.
- Run documentation tests from the PR revision, generate fresh snippets, then render Asciidoctor/Markdown.
- Clean output so stale snippets do not cause false-green PR checks.
- Verify includes, identifiers, test reports, and artifact provenance.
- Review snippet/rendered doc diffs to spot contract changes and formatting errors.
- Scan generated snippets and HTML/PDF to detect secrets or private data.
- Use preview artifacts or isolated preview deployments for PRs.
- PR validation and official publishing are two distinct stages.
