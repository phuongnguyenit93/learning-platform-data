# Exporting Specifications in CI and Detecting Breaking Contract Changes

A pull request can still pass the Spring Boot build while breaking existing API clients. Examples include removing an operation, adding a required query parameter, narrowing a request enum, or dropping a response status code that consumers handle. Therefore, CI should check both the OpenAPI document generated from the application and its compatibility with the published contract.

In this hands-on exercise, we build a pipeline for a Spring Boot application using springdoc-openapi. The pipeline will:

1. Build and test the application.
2. Start the application in the CI environment.
3. Download the OpenAPI document from the springdoc endpoint.
4. Validate and lint the document.
5. Compare the candidate against the approved baseline.
6. Block the pull request if breaking changes occur according to policy.
7. Archive the candidate and reports for reviewer inspection.

The example uses Maven, GitHub Actions, and oasdiff. If your project uses Gradle or a different CI system, keep the same check sequence and principles while substituting the corresponding commands.

## 1. Distinguishing a successful build from contract compatibility

Building and testing the application answers: does the source code compile, start up, and pass existing tests? Contract diffing answers a different question: does the new document remain compatible with clients generated from or written against the old document?

These two checks complement each other:

| Check | Good at catching | Does not prove on its own |
|---|---|---|
| Compile/build | Source code, dependency, or build configuration errors | Old clients still work |
| Unit/integration tests | Behavior in scenarios covered by tests | Every contract change is safe |
| OpenAPI validation | Invalid document structure, schemas, and references | New contract is compatible with baseline |
| OpenAPI lint | Design conventions, naming, metadata, and API standards | Runtime executes according to the document |
| Semantic/compatibility diff | Changes that may impact consumers | Every runtime behavior or every real client |

A good pipeline does not pick a single tool to replace everything else. It verifies the document is valid, compares the contract, and runs key runtime tests.

## 2. Designing candidate and baseline sources

Before writing a workflow, clearly define the two inputs:

- **Candidate:** the OpenAPI document generated from the commit under review in the pull request.
- **Baseline:** the approved and published API document, typically stored on the main branch or fetched from a release artifact.

Do not generate both baseline and candidate from the same commit and compare them; the result will almost always be identical and fail to detect pull request changes.

One simple approach is storing the approved contract in the repository:

~~~text
contracts/
└── openapi/
    └── orders-v1.json
~~~

When a pull request runs, CI fetches **origin/main:contracts/openapi/orders-v1.json** as the baseline and generates the candidate from the pull request application. After changes are reviewed and merged, update the baseline file with the release or via a dedicated contract pull request.

You can use an OpenAPI artifact from a release instead of a file in Git. In that case, the pipeline must download the exact artifact of the released version, verify its provenance, and keep that artifact immutable. Do not grab an arbitrary file from a live production environment without recording the commit, configuration, and group used to generate it.

### Rules for the baseline

- The baseline must represent an approved contract, not an arbitrary build.
- Each API version or group needs its own baseline.
- Store accompanying source metadata: commit, release, Spring profile, group, and generator tool version.
- When a breaking change is approved, make a versioning decision and update the baseline per release process.
- For a new API without a baseline, validate and review the initial document; do not fake a compatibility diff when no prior contract exists.

## 3. Identifying the springdoc endpoint to export

With default configuration, springdoc provides:

| Document | Default endpoint |
|---|---|
| OpenAPI JSON | /v3/api-docs |
| OpenAPI YAML | /v3/api-docs.yaml |
| Grouped OpenAPI JSON | /v3/api-docs/{groupName} |

Example for an application with group orders-v1:

~~~bash
curl -fsS http://127.0.0.1:8080/v3/api-docs/orders-v1 \
  -H "Accept: application/json" \
  -o build/openapi/orders-v1.json
~~~

If not using groups, download /v3/api-docs. If you customized springdoc.api-docs.path, server.servlet.context-path, port, or reverse-proxy prefix, use the application's actual URL.

Properties such as springdoc.api-docs.path, springdoc.api-docs.enabled, and springdoc.group-configs are documented on springdoc's configuration properties page. Do not hardcode the default endpoint in the pipeline if the project configures a different endpoint.

### Generating the document from the application in CI

Prefer generating the document from the exact artifact just built, using a profile and configuration close to the deployment environment. This ensures CI checks the output consumers will actually receive from the application.

Example:

~~~bash
./mvnw -B clean verify
java -jar target/orders-api.jar \
  --spring.profiles.active=ci \
  --server.port=8080
~~~

The startup command must run in the background in CI so subsequent steps can download the document. Wait for application readiness via a health endpoint or retry loop on /v3/api-docs; do not assume the process is ready immediately after invoking java -jar.

If the docs endpoint is protected, use a dedicated CI credential with read-only docs permission. Pass tokens via secrets/environment variables, never logging tokens into command logs, artifacts, or OpenAPI files. Another option is configuring a CI profile that opens docs endpoints only inside the isolated runner environment.

## 4. Ensuring the downloaded document is genuinely OpenAPI

A curl command can return HTTP 200 whose body is an HTML login page, reverse proxy error page, or application error JSON. Therefore, after downloading, verify:

- The file exists and is non-empty.
- The body parses cleanly as JSON/YAML.
- It contains openapi, info.title, info.version, and paths.
- It matches the expected group and API scope.
- It does not contain unexpected server URLs, hosts, or environment metadata.

Example JSON check with jq:

~~~bash
test -s build/openapi/orders-v1.json
jq -e '.openapi and .info.title and .info.version and (.paths | type == "object")' \
  build/openapi/orders-v1.json
~~~

If using a JSON endpoint, keep the .json extension. If downloading YAML, use the .yaml extension and a YAML-capable validator. Never rename file extensions to trick tools.

### Checking reproducibility

The candidate should be generated under identical conditions on every run:

- Same Spring profile and properties affecting controller mappings.
- Same groups, package/path filters, and customizers.
- Same server URL configuration variable matching the contract.
- No dependence on random data or timestamps inside the document.
- No calls to production to fetch live schemas or real tokens.

If server URLs vary by environment, consider configuring a stable public server URL for published documents or excluding environment-specific differences from diff policy in a controlled way. Do not strip out servers altogether just to make reports look clean.

## 5. Validating the document before diffing

Always validate the candidate before comparing. If the document fails to parse or contains broken schemas/references, compatibility reports are untrustworthy.

With oasdiff:

~~~bash
oasdiff validate build/openapi/orders-v1.json
~~~

The validate command checks an OpenAPI document against the OpenAPI and JSON Schema rules supported by the tool. It does not compare against a baseline.

You can add Redocly CLI to enforce design conventions:

~~~bash
redocly lint build/openapi/orders-v1.json --config redocly.yaml
~~~

Example redocly.yaml:

~~~yaml
extends:
  - recommended
rules:
  operation-operationId: error
  operation-summary: warn
  no-unused-components: warn
~~~

Choose rulesets and severities matching your team's standards. Linting can report style or governance errors even when the document is valid OpenAPI. Therefore, distinguish schema/parse errors from design-convention violations so reviewers know why the pipeline failed.

## 6. Choosing the right oasdiff comparison command

oasdiff provides commands answering different questions:

| Command | Contents | Purpose in CI |
|---|---|---|
| oasdiff validate spec.json | Validates a single document | Confirms candidate is valid |
| oasdiff diff base revision | Full diff, including documentation changes | Investigates all differences |
| oasdiff changelog base revision | Changes potentially affecting consumers, breaking and non-breaking | Generates report for reviewers |
| oasdiff breaking base revision | Changes classified as potentially breaking clients | Acts as compatibility gate |

Example report generation:

~~~bash
oasdiff diff contracts/openapi/orders-v1.json \
  build/openapi/orders-v1.json \
  --format markdown \
  > build/openapi/full-diff.md

oasdiff changelog contracts/openapi/orders-v1.json \
  build/openapi/orders-v1.json \
  --format markdown \
  > build/openapi/changelog.md

oasdiff breaking contracts/openapi/orders-v1.json \
  build/openapi/orders-v1.json
~~~

diff is helpful when inspecting description, example, or metadata changes as well. changelog focuses on consumer-impacting changes. breaking is used to decide whether to block the pipeline.

## 7. Understanding ERR, WARN, and INFO before setting a gate

oasdiff classifies findings by severity:

| Level | Meaning | Typical handling |
|---|---|---|
| ERR | Definite breaking change against the declared contract | Block merge unless approved |
| WARN | Potentially breaks clients, though tool cannot determine conclusively | Require reviewer investigation |
| INFO | Change not classified as breaking | Include in changelog if helpful |

The breaking command detects ERR and WARN changes. You can adjust which level fails the pipeline:

~~~bash
# Fail only on confirmed breaking changes.
oasdiff breaking base.json revision.json --fail-on ERR

# Fail on potentially client-breaking changes as well.
oasdiff breaking base.json revision.json --fail-on WARN
~~~

Choose ERR when the team wants to block definite breakages automatically and require human review for WARN. Choose WARN when the API carries strict compatibility commitments and every warning must be resolved before merging.

Do not downgrade severity merely to turn CI green. If a rule produces a false positive, read the change details, identify the cause, and record a narrowly scoped exception in reviewed configuration. Exceptions need an owner and a review expiration date.

The command exit code is the signal for CI. Non-zero exit codes from breaking changes must be distinguished from failures to fetch the baseline, corrupted candidate files, missing binaries, or runner misconfiguration. Keep logs so root causes can be identified.

## 8. Changes that commonly break clients

Evaluating breaking changes requires considering data direction. Clients send requests; servers return responses. The same schema change can have opposite impacts in the two directions.

| Change | Common impact | Initial assessment |
|---|---|---|
| Remove path or HTTP method | Clients can no longer invoke the operation | Breaking |
| Add required request parameter | Old clients omitting the parameter fail | Breaking |
| Narrow request enum | Values previously sent by clients become invalid | Breaking |
| Raise request minimum or lower request maximum | Previously valid payloads may be rejected | Potentially breaking |
| Remove response property | Clients reading that property may fail | Breaking |
| Narrow response enum | Clients may no longer receive known values | Potentially breaking |
| Remove response status or media type | Clients lose a response branch they relied on | Breaking |
| Strengthen security requirement or required scope | Existing credentials may lack permission | Breaking |
| Rename operationId | SDK generators may rename generated methods | May break SDK source compatibility |
| Change servers.url | Clients may call the wrong host or prefix | May break connectivity |

Some changes are generally more compatible, yet still require checking how consumers are written:

- Adding an optional request property usually does not force old clients to send new data.
- Adding a response property is usually safe for clients that ignore unknown fields, though it can break clients using strict schemas or additionalProperties: false.
- Editing descriptions or examples usually does not alter the wire contract, though it can affect documentation pipelines or specialized code generators.

Do not substitute this table for tool reports and knowledge of real consumers. A specification cannot capture all server-side business logic.

## 9. Example of a request change that fails CI

Baseline has operation:

~~~yaml
paths:
  /orders:
    get:
      operationId: listOrders
      parameters:
        - name: status
          in: query
          required: false
          schema:
            type: string
            enum: [OPEN, PAID, CANCELLED]
      responses:
        '200':
          description: List of orders
~~~

Candidate makes status required and drops enum value CANCELLED:

~~~yaml
paths:
  /orders:
    get:
      operationId: listOrders
      parameters:
        - name: status
          in: query
          required: true
          schema:
            type: string
            enum: [OPEN, PAID]
      responses:
        '200':
          description: List of orders
~~~

Old clients could call GET /orders without status or send status=CANCELLED. Candidate no longer accepts either call. Semantic diffing flags these changes and the gate can block the pull request.

If business needs truly require the change, the team can preserve the old operation during a transition period, introduce a new endpoint/version, or schedule a timed deprecation. Never remove an old parameter before understanding which clients still rely on it.

## 10. Example of a response change and SDK impact

Baseline:

~~~yaml
components:
  schemas:
    Order:
      type: object
      required: [id, status]
      properties:
        id:
          type: string
        status:
          type: string
        total:
          type: number
~~~

Candidate removes status from the response:

~~~yaml
components:
  schemas:
    Order:
      type: object
      required: [id]
      properties:
        id:
          type: string
        total:
          type: number
~~~

Consumers reading status may stop working properly. SDKs generated from the new document may also remove the corresponding property, breaking consumer compilation.

Renaming operationId or component names sometimes leaves the HTTP wire format unchanged while altering an SDK's public API. If the team publishes SDKs, add a step generating SDKs from baseline and candidate, then diff or compile a sample consumer.

## 11. Configuring compatibility policy in the repository

Keep diff policy in version control so local runs and CI use the same rules. oasdiff supports a .oasdiff.yaml configuration file at the repository root.

Example gate configuration:

~~~yaml
fail-on: ERR
~~~

You can configure additional ignores or severity overrides for investigated cases. Every exception should:

- Target only a specific rule or element.
- Include a rationale and link to the review decision.
- Have an owner.
- Have a review or removal date.

Avoid excluding broad swaths of paths, parameters, or schemas from the diff. Doing so hides the very changes the pipeline exists to catch.

## 12. Incorporating version bumps into release policy

When a breaking change is approved, the API needs a clear versioning plan. Depending on policy, teams can:

- Introduce a new major version in the URL, such as /v2 to /v3.
- Maintain old versioned routes during the deprecation window.
- Publish a migration guide and sunset timeline.
- Generate new SDKs from the new version's document.

info.version is the API/document version per project convention; openapi indicates the OpenAPI Specification version. These two values are not interchangeable.

Since oasdiff v1.38.0, you can use the MISSING-VERSION-BUMP fail level to fail only when a breaking change occurs without incrementing the major part of info.version. For example:

~~~bash
oasdiff breaking base.json revision.json --fail-on MISSING-VERSION-BUMP
~~~

Unlike --fail-on ERR or WARN, this policy allows breaking changes when paired with a SemVer major version bump in info.version. Enable this only when the project strictly follows major/minor/patch rules for info.version and pins a CLI version supporting this fail level. Never treat incrementing a version number as a substitute for compatibility review.

## 13. Complete GitHub Actions pipeline

The example below assumes:

- A Maven project with the mvnw wrapper.
- Spring Boot Maven plugin producing target/orders-api.jar.
- An application exposing group orders-v1.
- Baseline stored at contracts/openapi/orders-v1.json on branch main.
- Runner using Java 21 with access to configured dependency repositories.

Adjust JDK, JAR name, profile, endpoint, group, and action versions to match your project. Pin tool/action versions vetted by your team; update pinned versions via dedicated pull requests.

~~~yaml
name: OpenAPI contract

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  openapi-contract:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven

      - name: Set up Go
        uses: actions/setup-go@v5
        with:
          go-version: '1.24'

      - name: Install pinned oasdiff
        run: |
          go install github.com/oasdiff/oasdiff@v1.39.0
          echo "$(go env GOPATH)/bin" >> "$GITHUB_PATH"

      - name: Build and test
        run: ./mvnw -B clean verify

      - name: Export, validate and compare OpenAPI
        shell: bash
        run: |
          set -euo pipefail
          mkdir -p build/openapi

          java -jar target/orders-api.jar \
            --spring.profiles.active=ci \
            --server.address=127.0.0.1 \
            --server.port=8080 \
            > build/openapi/app.log 2>&1 &
          app_pid=$!
          trap 'kill "$app_pid" 2>/dev/null || true' EXIT

          for attempt in $(seq 1 60); do
            if curl -fsS \
              http://127.0.0.1:8080/v3/api-docs/orders-v1 \
              -H "Accept: application/json" \
              -o build/openapi/orders-v1.json; then
              break
            fi
            sleep 2
          done

          test -s build/openapi/orders-v1.json
          jq -e '.openapi and .info.title and .info.version and (.paths | type == "object")' \
            build/openapi/orders-v1.json

          oasdiff validate build/openapi/orders-v1.json

          if git cat-file -e \
            "origin/main:contracts/openapi/orders-v1.json" 2>/dev/null; then
            oasdiff changelog \
              origin/main:contracts/openapi/orders-v1.json \
              build/openapi/orders-v1.json \
              --format markdown \
              > build/openapi/changelog.md

            oasdiff diff \
              origin/main:contracts/openapi/orders-v1.json \
              build/openapi/orders-v1.json \
              --format markdown \
              > build/openapi/full-diff.md

            oasdiff breaking \
              origin/main:contracts/openapi/orders-v1.json \
              build/openapi/orders-v1.json \
              --fail-on ERR
          else
            echo "No approved baseline exists; review this new API contract."
          fi

      - name: Upload OpenAPI review artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: openapi-contract
          path: |
            build/openapi/orders-v1.json
            build/openapi/changelog.md
            build/openapi/full-diff.md
          if-no-files-found: warn
~~~

actions/checkout uses fetch-depth: 0 so the baseline can be read from origin/main. The syntax origin/main:path/to/spec.json allows oasdiff to read files at a Git ref without copying the baseline into a temporary directory.

In the example, --fail-on ERR blocks only definite breakages. If the team wants to block WARN as well, change it to --fail-on WARN. For a new API without a baseline, the pipeline still validates the candidate and prompts reviewers to approve the initial contract.

java -jar must run with the prepared CI configuration. If the application needs a database, message broker, or other environment variables, provide suitable service containers/fixtures; never point the pipeline at production systems.

Artifact upload uses if: always() so reviewers can still inspect the candidate and reports when the compatibility gate fails. Never upload app.log if logs might contain tokens, personal data, or sensitive configuration.

## 14. Handling multiple groups or multiple documents

Each springdoc group can represent a separate contract. Never compare orders-v1 against orders-v2, or a public document against an internal one.

Example:

| Group | Candidate | Baseline |
|---|---|---|
| orders-v1 | /v3/api-docs/orders-v1 | contracts/openapi/orders-v1.json |
| partners-v1 | /v3/api-docs/partners-v1 | contracts/openapi/partners-v1.json |
| admin-v1 | /v3/api-docs/admin-v1 | contracts/openapi/admin-v1.json |

With multiple files, the easiest approach to control is running an oasdiff breaking pair per group and saving separate reports. You can use oasdiff breaking-files when candidates are saved at stable paths matching the baseline paths in a Git ref; this command infers baselines from the same path in the specified revision. If candidates are exported to a build directory different from baseline locations, run individual breaking pairs with explicit baseline paths.

If a group is newly added, having no baseline is normal. Validate, lint, and review its contents before creating the initial baseline.

## 15. Protecting the pipeline when resolving external references

An OpenAPI document can contain $ref pointers to external files or URLs. When CI resolves references from untrusted pull requests, tools might access unintended external resources.

The oasdiff GitHub Action disables external reference resolution by default to reduce SSRF risk. With the CLI, prefer self-contained documents or local references checked out in the workspace. Enable external ref resolution only when sources are controlled, pinned, and approved by the security team.

Never allow pull requests to arbitrarily modify $ref URLs to make runners probe metadata endpoints, internal networks, or runner-accessible internal services.

## 16. Verifying the runtime contract alongside the diff

Semantic diffing only compares what documents declare. It does not prove controllers actually return the documented statuses, headers, content types, or payloads.

Add integration tests for critical behaviors:

- Public/secured endpoints return the expected statuses.
- Valid and invalid request bodies are handled properly.
- Success/error responses match schemas and media types.
- Required parameters, enums, and boundary validation align with the document.
- /v3/api-docs/{group} contains expected operations and schemas.

Example document test using MockMvc:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OpenApiContractTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void ordersGroupContainsListOperation() throws Exception {
        mockMvc.perform(get("/v3/api-docs/orders-v1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.paths['/orders'].get").exists())
            .andExpect(jsonPath(
                "$.paths['/orders'].get.operationId"
            ).value("listOrders"));
    }
}
~~~

This test verifies the generated document. Pair it with tests invoking /orders with real requests/responses to confirm runtime behavior.

## 17. Reading CI results and handling gate failures

| Outcome | What to check | Action |
|---|---|---|
| Build fails | Compilation, tests, dependencies, profile | Fix application issues before checking compatibility |
| Cannot fetch /v3/api-docs | Port, readiness, context path, auth, group | Inspect app logs and actual URL |
| Candidate empty or unparseable | HTML/error body, serialization, wrong endpoint | Inspect HTTP response and file |
| oasdiff validate fails | Schema, $ref, required fields, OAS structure | Fix the document or generation setup |
| Lint fails | Design conventions or metadata | Fix rule violations or request a justified exception |
| ERR breaking change | Old contract is no longer compatible | Preserve old behavior, design migration, or create a new version |
| WARN only | Tool cannot confirm conclusively | Reviewer checks consumers, schema composition, and runtime |
| Diff shows only description edits | Documentation text changed | Review wording; do not confuse with wire-level breaking |
| Baseline missing | New API/group or release contract not yet saved | Review initial document and create baseline after approval |
| Local and remote CI differ | Different tool versions, profiles, configs, or baselines | Pin tools, record provenance, and reproduce identical conditions |

Never delete a baseline to make a gate pass. Never add blanket ignore rules across entire schemas or paths. Every intentional contract change must be explained in the pull request and tied to a release plan.

## 18. Saving artifacts and updating the baseline after merge

Once a pull request is approved:

1. Reviewers inspect the candidate, changelog, and full diff.
2. Confirm breaking changes have been addressed or have a versioning plan.
3. Merge the code and approved contract changes per repository workflow.
4. Archive the OpenAPI document with release artifacts, tagged with commit/release identifiers.
5. Update the group's baseline when the new contract is approved.
6. Retain old baselines in Git history or release storage so future versions can be compared.

Never overwrite the baseline automatically before review completes. The baseline is the anchor against which subsequent pull requests measure compatibility.

## 19. Common CI integration mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| Pipeline always reports zero breaking changes | Comparing candidate against itself or baseline from PR commit | Fetch baseline from origin/main or a published release |
| Pipeline cannot find baseline | Checkout lacks Git history/refs or wrong path | Use full history and verify file path in main |
| Document differs between local and CI | Different profile, env, group, or server URL | Standardize export configuration |
| /v3/api-docs returns 401/403 | Docs endpoint is secured | Provide a CI token with proper scope or use an isolated CI profile |
| /v3/api-docs returns 404 | Wrong group, path, or context path | Inspect springdoc properties and actual endpoints |
| Candidate is HTML inside a .json file | Login/proxy redirect or unchecked HTTP error | Use curl -f and validate body with jq |
| Diff reports many unrelated changes | Generator/config/tool version changed | Pin tools, stabilize configuration, and review full diff |
| CI fails on WARN only | Gate uses --fail-on WARN | Review severity policy; do not downgrade arbitrarily |
| CI passes despite WARN | Gate uses --fail-on ERR | Switch to WARN if stricter guarantees are required |
| External $ref fails to resolve | Document depends on external files/URLs | Bundle references or allow controlled trusted sources |
| Artifacts missing when gate fails | Upload runs only on job success | Use if: always() and upload only safe files |
| New document has wrong servers | URL came from profile or runner host | Configure a stable public server URL for the contract |

## 20. Pipeline completion checklist

- [ ] Confirm the candidate is generated from the commit under test.
- [ ] Baseline comes from an approved contract or release artifact.
- [ ] Baseline and candidate belong to the same API version and group.
- [ ] Application builds and passes tests prior to export.
- [ ] CI starts the application with a deterministic profile.
- [ ] springdoc endpoint uses the exact path and group.
- [ ] Export request checks HTTP status and non-empty file.
- [ ] Candidate parses and validates cleanly.
- [ ] Linter applies the team's agreed ruleset.
- [ ] oasdiff changelog and oasdiff diff are saved for review.
- [ ] oasdiff breaking uses the right severity gate.
- [ ] Tool versions and configurations are pinned in the repository.
- [ ] External $refs are handled safely.
- [ ] Runtime integration tests verify key contracts.
- [ ] Uploaded artifacts contain no sensitive tokens or logs.
- [ ] Breaking changes have versioning and migration decisions.
- [ ] Baseline is updated only after the new contract is approved.

## 21. Official references

- [springdoc-openapi — Configuration Properties](https://springdoc.org/properties.html) — API docs endpoints, group configs, path filters, and related properties.
- [oasdiff — CLI Quick Start](https://www.oasdiff.com/docs/getting-started) — installation, validate, diff, changelog, breaking, output formats, and exit codes.
- [oasdiff — Breaking Changes and Changelog](https://github.com/oasdiff/oasdiff/blob/main/docs/BREAKING-CHANGES.md) — ERR, WARN, INFO classification and --fail-on.
- [oasdiff — Diff](https://github.com/oasdiff/oasdiff/blob/main/docs/DIFF.md) — comparison behavior and semantic diff options.
- [oasdiff — Checking Many Specs Against a Git Ref](https://github.com/oasdiff/oasdiff/blob/main/docs/BREAKING-FILES.md) — comparing baselines from a Git ref and checking multiple specs.
- [oasdiff — GitHub Action](https://www.oasdiff.com/docs/github-action) — integrating compatibility gates, artifact reports, and external reference protection.
- [oasdiff — Releases](https://github.com/oasdiff/oasdiff/releases) — release notes, including the MISSING-VERSION-BUMP fail level from v1.38.0.
- [Redocly CLI — lint](https://redocly.com/docs/cli/commands/lint) — OpenAPI linting and ruleset configuration.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html) — document structure and contract semantics.

CI can only protect an API when it compares the candidate against an actually published baseline. Generate the document from the springdoc application, validate before diffing, apply an intentional severity gate, archive reports, and verify runtime behavior with integration tests. When a breaking change is approved, update versions and baselines according to the release process so subsequent comparisons always have a reliable anchor.
