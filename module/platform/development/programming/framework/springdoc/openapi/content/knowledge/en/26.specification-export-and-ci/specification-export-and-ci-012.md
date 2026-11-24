# Stopping CI When the Specification Cannot Be Fetched or the Document Is Invalid

## 1. Why must the pipeline stop when OpenAPI is untrustworthy?

OpenAPI documents are commonly used to generate client SDKs, run contract tests, build developer portals, and feed API gateways. If the pipeline fails to fetch the document or mistakes an error response for documentation, downstream steps may continue with an empty file, a stale file, or invalid content.

For example, the Spring Boot application is not ready yet when the pipeline calls /v3/api-docs. The request may fail with connection refused. Another case is Spring Security redirecting the request to an HTML login page and returning status 200; the download step still creates a file, yet its content is not OpenAPI. If the pipeline only checks that the file exists, an invalid document can still be published.

A reliable pipeline must stop when any of these conditions occur:

- Cannot connect to the OpenAPI endpoint.
- The endpoint returns a non-successful HTTP status.
- The request redirects to a login page or error page.
- The response is empty, truncated, or not JSON/YAML.
- The document does not conform to the declared OpenAPI Specification.
- References or schemas are invalid.
- The document violates organizational quality conventions.
- There is an unapproved breaking change.
- The document was generated from the wrong build, wrong profile, or wrong document group.

The principle is never to allow publishing an OpenAPI artifact whose provenance and validity the pipeline has not proven.

## 2. CI flow needs explicit verification gates

A Springdoc pipeline can be divided into stages:

~~~text
Checkout source revision
          |
          v
Build application artifact
          |
          v
Run unit / integration tests
          |
          v
Start the exact artifact
          |
          v
Wait for readiness
          |
          v
Fetch OpenAPI JSON/YAML
          |
          v
Check HTTP result and file content
          |
          v
Parse and validate OpenAPI
          |
          v
Lint and compatibility checks
          |
          v
Create manifest / checksum
          |
          v
Publish immutable artifacts
~~~

Each step is a gate. If any gate fails, the pipeline must return a non-zero exit code and skip the publish step.

Do not cram every operation into one long command that obscures the root cause. Separate steps let logs pinpoint whether an error occurred in build, startup, endpoint, document parser, governance rule, or compatibility diff.

## 3. Identifying the OpenAPI endpoint the pipeline needs to fetch

Under the default Springdoc configuration, common endpoints are:

~~~http
GET /v3/api-docs
GET /v3/api-docs.yaml
~~~

If a custom path is configured, the pipeline must use that exact value:

~~~yaml
springdoc:
  api-docs:
    enabled: true
    path: /openapi
~~~

Then the JSON document is fetched at /openapi and the YAML endpoint depends on the path/extension under the Springdoc configuration in use. Verify the actual URL with an integration test rather than assuming the default endpoint still exists.

If document groups exist:

~~~java
@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner")
        .pathsToMatch("/api/partner/**")
        .build();
}
~~~

The group's document is typically fetched via /v3/api-docs/partner. A pipeline exporting multiple groups must verify each endpoint and write separate files. Do not use the same output filename for public, partner, and internal documents.

Distinguish the OpenAPI endpoint from the Swagger UI URL. Downloading the Swagger UI HTML page does not mean you have downloaded OpenAPI JSON.

## 4. Enabling API docs in the profile used by CI

If the application has profile-specific configuration, ensure the profile used in the pipeline enables document generation:

~~~yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: false
~~~

Swagger UI is not required to export OpenAPI. You can disable the UI in the CI profile while keeping the api-docs endpoint enabled.

A common error is a production or test profile accidentally setting springdoc.api-docs.enabled=false. Then the application starts normally, yet the documentation endpoint returns 404 or is not registered.

The pipeline should log the activated profile explicitly and verify the endpoint after startup. Do not fall back automatically to another profile when the endpoint errors, because a fallback profile may generate a document differing from the expected release configuration.

## 5. Starting the exact artifact before exporting

OpenAPI must be generated from the exact application version the pipeline is testing. Never build an artifact, export documentation from a different local application, and publish both as the same release.

Example with Maven:

~~~bash
./mvnw -B clean verify
~~~

After the build succeeds, run the exact newly created JAR:

~~~bash
java -jar target/catalog-api.jar \
  --spring.profiles.active=contract \
  --server.port=8080
~~~

The JAR path must match the project's actual artifact name. When using Gradle, container images, or Docker Compose, the principle stays the same: launch the exact artifact built from the current source revision.

If the Springdoc Maven Plugin is used to download the document, remember it fetches OpenAPI from an application running at the configured URL; the pipeline must still ensure the server has started and is ready. Do not treat the generate goal as proof that the application started itself successfully.

## 6. Waiting for readiness instead of waiting a fixed duration

A sleep 10 command may work on a fast local machine yet fail in CI when the JVM starts slowly. Conversely, an overly long fixed wait slows down the pipeline even when the application is already ready.

If the application has a Spring Boot Actuator readiness endpoint, wait on that endpoint:

~~~bash
HEALTH_URL="http://localhost:8080/actuator/health/readiness"
READY=false

for attempt in $(seq 1 30); do
  if curl --silent --show-error --fail \
      --connect-timeout 2 --max-time 5 \
      "$HEALTH_URL" >/dev/null; then
    READY=true
    break
  fi

  sleep 2
done

if [ "$READY" != "true" ]; then
  echo "Application did not become ready"
  exit 1
fi
~~~

The example assumes the Actuator readiness endpoint is enabled and accessible in the CI environment. If the project does not use Actuator, wait on another health endpoint or the OpenAPI endpoint itself.

Do not add a fake readiness endpoint just to turn the pipeline green. Readiness should reflect real request-serving capability and the application's required dependencies.

## 7. Bounded retries for transient errors

Right after readiness succeeds, an OpenAPI request may still hit transient errors due to proxies, connection pools, or startup races. Bounded retries help handle transient failures.

Curl example:

~~~bash
curl \
  --silent \
  --show-error \
  --fail \
  --location \
  --connect-timeout 5 \
  --max-time 60 \
  --retry 5 \
  --retry-connrefused \
  --retry-delay 2 \
  --retry-max-time 60 \
  "http://localhost:8080/v3/api-docs" \
  --output target/openapi/openapi.json
~~~

The retry options must be supported by the curl version on the runner. Pipelines should pin or verify the toolchain if relying on newer options.

Retries are only for likely transient errors. Do not retry endlessly on 401, 403, 404, or schema-invalid documents. Those errors usually require fixing configuration or access permissions, not waiting longer.

Set timeouts for both connection and total request time so a hanging endpoint cannot tie up the runner indefinitely.

## 8. Not letting stale files mask fetch failures

A dangerous bug occurs when the output directory already contains openapi.yaml from a previous run. The current export fails, yet downstream steps see the stale file and continue validating/publishing.

Create a clean output directory or delete the exact output files before fetching:

~~~bash
mkdir -p target/openapi
rm -f target/openapi/openapi.json
rm -f target/openapi/openapi.yaml
~~~

Then proceed only if the current fetch command succeeds and the file was created in this run.

An even safer approach is downloading into a temporary file and renaming after the fetch completes:

~~~bash
SPEC_TMP="target/openapi/openapi.yaml.tmp"
SPEC_FILE="target/openapi/openapi.yaml"

rm -f "$SPEC_TMP" "$SPEC_FILE"

curl --silent --show-error --fail --location \
  --connect-timeout 5 --max-time 60 \
  "http://localhost:8080/v3/api-docs.yaml" \
  --output "$SPEC_TMP"

test -s "$SPEC_TMP"
mv "$SPEC_TMP" "$SPEC_FILE"
~~~

If curl fails, the official file is never created. Never use a file from a runner cache or stale workspace as a fallback for the current release.

## 9. Checking HTTP status and response type

Use curl with --fail so the command fails when the server returns an error HTTP status. You can follow redirects with --location if architecture allows, but watch out for redirects to a login page.

An endpoint can return 200 OK while the body is HTML:

~~~html
<!doctype html>
<html>
  <title>Sign in</title>
</html>
~~~

Thus, HTTP 200 is not enough to prove the response is OpenAPI. Inspect the content or parse the document with a validator.

Example quick check for HTML at the start of the file:

~~~bash
if head -c 512 target/openapi/openapi.json \
    | grep -Eiq '<!doctype html|<html'; then
  echo "Expected OpenAPI JSON but received HTML"
  exit 1
fi
~~~

This is only an early detector. The OpenAPI validator remains the main gate verifying structure and semantics.

If API docs are protected, send CI credentials authorized to read documentation. Never disable Spring Security in the profile just to fetch the document; doing so makes the pipeline test a surface different from the released application.

## 10. Classifying fetch errors for proper handling

| Symptom | Possible cause | Action |
|---|---|---|
| Connection refused | Application not listening yet or wrong port | Check startup/readiness and port |
| Timeout | Slow startup, hung thread, or heavy endpoint | Inspect logs, raise timeout within bounds, and profile |
| HTTP 401 | Missing authentication | Configure CI credentials authorized to read docs |
| HTTP 403 | Credentials lack permission or security matcher blocked | Check roles and filter chain |
| HTTP 404 | Wrong path, docs disabled, or group does not exist | Check springdoc path/profile/group |
| HTTP 5xx | Application or customizer error | Inspect server logs and stack trace |
| HTTP 200 but HTML | Login redirect or proxy error page | Check redirects/auth and content |
| Empty file | Export error or truncated response | Check curl exit code and server logs |
| JSON/YAML parse error | Corrupted document or wrong format | Check response and exporter version |
| OpenAPI validation error | Invalid document | Fix schemas/annotations/customizers |

Do not collapse all failures into a generic "OpenAPI generation failed" message. Preserve the HTTP status, endpoint, curl error, and application logs so the person fixing it can pinpoint the cause.

## 11. Verifying the file was created and is non-empty

After a successful fetch:

~~~bash
SPEC_FILE="target/openapi/openapi.yaml"

if [ ! -f "$SPEC_FILE" ]; then
  echo "OpenAPI file was not created"
  exit 1
fi

if [ ! -s "$SPEC_FILE" ]; then
  echo "OpenAPI file is empty"
  exit 1
fi
~~~

Do not rely solely on checking that the file exists. A zero-byte file can still exist after a failed write.

If both JSON and YAML must be saved, check each file separately. Do not treat a successful JSON download as proof that the YAML endpoint also works.

Output filenames must be deterministic within the job and unique across groups. If exporting partner and public groups, create partner.yaml and public.yaml or a separate directory per group.

## 12. Parsing and validating against the OpenAPI Specification

The document must be parsed with a tool that understands OpenAPI, not just a generic JSON/YAML parser.

A YAML file may parse into a map yet miss required fields or use invalid OpenAPI structure. Syntactically valid JSON can likewise contain operations missing responses or unresolvable references.

You can use Redocly CLI to lint the document:

~~~bash
npx redocly lint target/openapi/openapi.yaml
~~~

In production pipelines, install and pin the Redocly CLI version via package manifest/lockfile or a fixed tool container. Do not fetch the latest version on every run if reproducible CI results are required.

The lint command can apply default rulesets or repository configuration. Distinguish specification/structural errors from warnings per the project's governance policy.

If using OpenAPI 3.1, ensure the validator supports 3.1 and the JSON Schema features used by the document. Older validators may report false errors or ignore newer constructs.

## 13. Checking version and foundational fields

The pipeline can check foundational fields before running deeper steps:

- The openapi field is present and matches a version permitted by the project.
- info has valid title and version.
- paths exists matching the document structure.
- Operations have documented responses.
- components and references are valid.
- Server URLs match the CI profile.
- Document group matches the intended audience.

Example with a JSON document and jq:

~~~bash
jq -e '
  (.openapi | type == "string") and
  (.info.title | type == "string" and length > 0) and
  (.info.version | type == "string" and length > 0) and
  (.paths | type == "object")
' target/openapi/openapi.json >/dev/null
~~~

This check applies only to JSON. For YAML, use an OpenAPI validator or a pinned YAML reader tool. Do not convert YAML to JSON via character replacement or naive text processing.

Additional manual checks do not replace an OpenAPI validator; they catch service-specific required fields enforced by the organization.

## 14. Validating references and schemas

A document may parse cleanly yet contain a non-existent $ref:

~~~yaml
schema:
  $ref: '#/components/schemas/UnknownModel'
~~~

Validators must check local references and external references per policy. If external references are fetched from URLs, the pipeline can become dependent on network availability or changing remote content.

For reproducible builds:

- Prefer local references versioned alongside the contract.
- Pin external reference content by version or commit.
- Restrict external network access during validation if unnecessary.
- Log clearly when the resolver cannot fetch a reference.
- Never ignore unresolved references and let the pipeline continue to publish.

Schema validation must also verify type, format, required, enum, nullable, and compositions like allOf/oneOf/anyOf. With OpenAPI 3.1, understand the declared JSON Schema dialect.

## 15. Separating specification validation from lint policy

There are two distinct kinds of checks:

**OpenAPI Specification validation**

- Correct document structure.
- Objects placed in the right locations.
- References and schemas resolved properly.
- Compatible document version and features.

**Organizational convention linting**

- Operations have summaries and operationIds.
- Tags follow naming conventions.
- Error responses use standard schemas.
- Security requirements appear on operations needing protection.
- No internal hostnames published.
- Schemas have descriptions and examples as required.

A document can be valid OpenAPI yet fail lint because an operationId is missing. Conversely, a document can follow naming conventions yet still fail standard structural validation.

Report the two groups of errors separately so developers know whether to fix the contract or add metadata per governance rules.

## 16. Running contract diff after the document is valid

Run breaking-change diffs only when both candidate and baseline are valid OpenAPI documents.

Example with oasdiff:

~~~bash
oasdiff breaking previous/openapi.yaml target/openapi/openapi.yaml
~~~

If the document could not be fetched or failed validation, do not diff against a leftover stale file. Diff results when one input is missing or stale are meaningless.

The baseline must belong to the same service, API audience, and document group. Do not compare a public API against an internal API or another group simply because filenames look similar.

Breaking changes must be reviewed per policy. If the tool detects a change impacting clients, the pipeline should fail or require recorded approval. Never use || true to swallow validator/diff exit codes in release jobs.

## 17. Sample GitHub Actions pipeline

The example below illustrates a Maven job starting the JAR, waiting for readiness, exporting the document, and linting with Redocly. The repository needs package.json/package-lock.json containing a pinned Redocly version and a matching JAR artifact name.

~~~yaml
name: OpenAPI contract gate

on:
  pull_request:
  push:
    branches: [main]

jobs:
  openapi:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven

      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: npm

      - name: Install pinned OpenAPI tooling
        run: npm ci

      - name: Build and test
        run: ./mvnw -B clean verify

      - name: Start application artifact
        run: |
          nohup java -jar target/catalog-api.jar \
            --spring.profiles.active=contract \
            --server.port=8080 > app.log 2>&1 &
          echo $! > app.pid

      - name: Wait for readiness and export
        run: |
          set -euo pipefail
          ready=false
          for attempt in $(seq 1 30); do
            if curl --silent --show-error --fail \
                http://localhost:8080/actuator/health/readiness \
                >/dev/null; then
              ready=true
              break
            fi
            sleep 2
          done

          if [ "$ready" != "true" ]; then
            cat app.log
            echo "Application did not become ready"
            exit 1
          fi

          mkdir -p target/openapi
          rm -f target/openapi/openapi.yaml

          curl --silent --show-error --fail --location \
            --connect-timeout 5 --max-time 60 \
            --retry 5 --retry-connrefused --retry-delay 2 \
            http://localhost:8080/v3/api-docs.yaml \
            --output target/openapi/openapi.yaml

          test -s target/openapi/openapi.yaml

      - name: Validate and lint OpenAPI
        run: npx redocly lint target/openapi/openapi.yaml

      - name: Upload validated contract
        uses: actions/upload-artifact@v4
        with:
          name: catalog-api-openapi
          path: target/openapi/openapi.yaml
~~~

This template must be adapted to your project's JAR name, Java version, readiness endpoint, port, and Springdoc configuration. If Actuator readiness is not enabled, substitute the actual health endpoint.

GitHub Actions does not automatically know the application is ready just because the Java process was spawned. The readiness loop is an explicit gate before the fetch step.

## 18. Ensuring publish runs only after all gates

In workflows, the publish step must depend on the validation job or step succeeding. Never configure publish with an always-run condition like always() without checking successful outcomes.

A safe structure:

~~~yaml
jobs:
  validate-openapi:
    runs-on: ubuntu-latest
    steps:
      - name: Fetch
        run: ./ci/fetch-openapi.sh
      - name: Validate
        run: ./ci/validate-openapi.sh
      - name: Upload validated contract
        uses: actions/upload-artifact@v4
        with:
          name: catalog-api-openapi
          path: target/openapi/openapi.yaml

  publish-openapi:
    needs: validate-openapi
    if: success()
    runs-on: ubuntu-latest
    steps:
      - name: Download validated artifact
        uses: actions/download-artifact@v4
        with:
          name: catalog-api-openapi
      - name: Publish
        run: ./ci/publish-openapi.sh
~~~

The published artifact must be the exact validated file, not re-fetched from another endpoint in the publish job. Re-fetching could yield content different from the candidate that passed validation.

In multi-job pipelines, artifact upload/download must preserve the exact run ID and artifact name. Never download an artifact of the same name from a prior run or another branch.

## 19. Never falling back to stale documentation when fetch fails

Do not write logic like:

~~~bash
curl ... || cp previous/openapi.yaml target/openapi/openapi.yaml
~~~

This makes the pipeline pass with old documentation while the new application artifact failed to produce a contract. Consumers could wrongly believe the document was verified for the new release.

Old baselines are only for compatibility comparisons, never as a substitute candidate when export fails.

If you want to preserve the last document for diagnostics, clearly separate failure artifacts from release artifacts. Failure artifacts must never be published to the catalog or official contract paths.

## 20. Collecting logs when a gate fails

When fetching or validation fails, retain enough information for debugging:

- Commit SHA and pipeline run ID.
- Active Spring profile.
- Artifact name/version.
- OpenAPI URL and document group.
- HTTP status or curl exit code.
- Response Content-Type.
- Received file size.
- Application startup logs.
- Validator/linter version.
- Specific validation or lint errors.

Never upload files containing tokens, cookies, secrets, or sensitive data. If the response body is a login or error page, you may save a sanitized copy as a diagnostic artifact, but never treat it as an OpenAPI release.

In GitHub Actions, you can upload app.log on job failure using failure() with short retention. Keep only necessary logs and apply your organization's data-protection policies.

## 21. Checking document groups individually

If the application has multiple GroupedOpenApi beans, one group endpoint may work while another is misconfigured.

Example requiring export:

~~~text
/v3/api-docs/public
/v3/api-docs/partner
/v3/api-docs/internal
~~~

The pipeline should declare the expected list of groups and iterate over each one. If a required group returns 404, an empty document, or missing operations, the job must fail.

Do not skip a group simply because it had no changes in a pull request. A filter or security matcher bug can make a group's documentation vanish after a configuration change.

Filenames should preserve group identity:

~~~text
target/openapi/public.yaml
target/openapi/partner.yaml
target/openapi/internal.yaml
~~~

Each file must be validated individually and published to the right audience. Internal documentation must not slip into public artifacts due to an overly broad upload glob.

## 22. Handling authentication when fetching API docs

If the OpenAPI endpoint is protected, the pipeline needs credentials with read-only access to documentation. Example:

~~~bash
curl --silent --show-error --fail \
  --header "Authorization: Bearer $DOCS_TOKEN" \
  "http://localhost:8080/v3/api-docs" \
  --output target/openapi/openapi.json
~~~

DOCS_TOKEN must be supplied from the CI secret store, never stored in source, literal workflow YAML, or logs.

Do not disable security in the CI profile just to avoid 401s. Doing so tests a different access surface than the released application.

If using cookies/sessions or OAuth2 client credentials, configure a dedicated token-issuance flow for CI and restrict audience/scopes. When a token expires or lacks permissions, the pipeline must fail with a clear authentication error message.

## 23. Checking server URLs and environment metadata

A structurally valid document can still target the wrong environment. For example, a contract profile accidentally generates:

~~~yaml
servers:
  - url: https://staging-api.example.com
~~~

when the artifact is intended for production release.

You can add a policy check for the allowed list of hosts per profile. Do not check by searching strings across the entire file if hostnames can appear in descriptions or examples; parse the servers field.

If the pipeline generates an environment-agnostic canonical document, server URLs can be normalized by policy. If documents are generated per environment, profiles and expected base URLs must be declared explicitly.

Never use an arbitrary Host header from a CI request to decide the server URL. Use controlled configuration in profiles or environment variables.

## 24. Common mistakes when CI fails to stop on time

| Symptom | Cause |
|---|---|
| Fetch fails yet job stays green | The curl command is masked by || true or the script does not enable fail-fast |
| Pipeline validates stale file | Output directory was not cleaned before export |
| JSON file contains HTML | Login redirect or proxy returned status 200 error page |
| Empty file gets published | Only checked file existence, did not check size |
| Validator runs on wrong document | Wrong path or group URL |
| Document is invalid yet lint passes | Ruleset too permissive or tool lacks OpenAPI version support |
| 401/403 retried repeatedly | Retry policy does not distinguish transient errors from authorization |
| Random startup timeouts | Used fixed sleep instead of readiness check |
| Published artifact differs from candidate | Publish job re-fetched document or downloaded wrong artifact |
| Breaking changes slip through | Diff exit code swallowed or wrong baseline |
| CI profile differs from production | Metadata, security, or handler mappings differ in config |
| Internal document leaks publicly | Upload glob grabbed all group artifacts |

When adjusting the pipeline, write tests that intentionally force the endpoint to return 404, HTML, an empty file, or invalid schemas to verify the gate actually fails. Do not test only the happy path.

## 25. Fail-fast checklist before publishing

Before allowing OpenAPI artifact publication:

1. Check out the exact source revision.
2. Build and test the application artifact.
3. Launch the exact freshly built artifact.
4. Wait for readiness using a health endpoint with bounded timeout.
5. Fetch the exact JSON/YAML endpoint and exact document group.
6. Use bounded retries for transient errors.
7. Fail when HTTP status is unsuccessful.
8. Fail when the response is HTML, empty, or not freshly created.
9. Parse and validate against the OpenAPI Specification version.
10. Resolve local/external references per policy.
11. Run linting against governance rules.
12. Check server URLs and environment metadata.
13. Compare against the baseline to detect breaking changes.
14. Never use old documentation as a fallback candidate.
15. Publish the exact validated artifact without re-fetching.
16. Preserve safe diagnostic logs when a gate fails.

A pipeline is only trustworthy when it stops at the right time. With Springdoc, treat obtaining the OpenAPI document as a mandatory release precondition: the application must be ready, the endpoint must return the right content, the document must be valid, and every policy gate must pass before the artifact is published.

