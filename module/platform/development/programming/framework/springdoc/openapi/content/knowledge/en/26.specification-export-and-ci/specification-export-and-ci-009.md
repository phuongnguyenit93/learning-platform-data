# Exporting Per Group and Verifying the Exact Set of Endpoints

A Spring Boot application can publish multiple OpenAPI documents using `GroupedOpenApi`: public documentation for partners, internal documentation for development teams, or administrative documentation for operations. When bringing documentation into CI, you must export each group's document accurately and verify that the set of operations in the document matches the agreed scope.

Checking only the default `/v3/api-docs` endpoint is not enough. That endpoint may not represent separately published groups. A public group could accidentally include internal endpoints due to overlapping filters; conversely, a new endpoint could be missing from the documentation while the build still passes. A reliable verification approach is storing an expected list per group id, extracting `(HTTP method, path)` pairs from the OpenAPI JSON, and comparing them exactly in CI.

## 1. Creating document groups with stable identifiers

Example application with two groups: `public-v1` and `internal-v1`:

```java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupsConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public-v1")
            .pathsToMatch("/api/public/**")
            .build();
    }

    @Bean
    GroupedOpenApi internalApi() {
        return GroupedOpenApi.builder()
            .group("internal-v1")
            .pathsToMatch("/api/**")
            .pathsToExclude("/api/public/**")
            .build();
    }
}
```

`group(...)` is the identifier used in export URLs. It is neither the Java bean name nor the OpenAPI document's `info.title`. Choose short, stable group ids that are easy to use in artifact names, manifests, and pipelines.

Filters can be based on paths, controller packages, or a combination of conditions. If an operation matches multiple groups, it can appear in multiple documents. That may be intentional, but it must be reflected in each group's manifest. `GroupedOpenApi` partitions documentation content; it does not by itself protect the document download URL.

## 2. JSON and YAML URLs for each group

With the default base path, springdoc serves documents by group id:

| Document | URL |
| --- | --- |
| Default OpenAPI JSON | `/v3/api-docs` |
| Default OpenAPI YAML | `/v3/api-docs.yaml` |
| JSON for `public-v1` | `/v3/api-docs/public-v1` |
| YAML for `public-v1` | `/v3/api-docs/public-v1.yaml` |
| JSON for `internal-v1` | `/v3/api-docs/internal-v1` |
| YAML for `internal-v1` | `/v3/api-docs/internal-v1.yaml` |

JSON and YAML are two representations of the same OpenAPI document. In CI, JSON is convenient for parsing with `jq`; YAML is convenient for review and archival if the project team uses YAML as the published artifact.

If the application changes `springdoc.api-docs.path`, group URLs also use the new base path. For example:

```yaml
springdoc:
  api-docs:
    path: /internal/openapi
```

Then the group's JSON URL is `/internal/openapi/public-v1`, and YAML is `/internal/openapi/public-v1.yaml`. If there is a `server.servlet.context-path` or reverse proxy prefix, use the full public URL reachable by the pipeline.

## 3. Exporting each group into a separate artifact

Name files after the group id to avoid overwriting another group's document:

```text
build/openapi/
  public-v1.json
  public-v1.yaml
  internal-v1.json
  internal-v1.yaml
```

Example using `curl` in Bash:

```bash
#!/usr/bin/env bash
set -euo pipefail

: "${DOCS_BASE_URL:?Set DOCS_BASE_URL to the running application URL}"
BASE_URL="${DOCS_BASE_URL%/}"

auth_args=()
if [[ -n "${DOCS_TOKEN:-}" ]]; then
  auth_args+=(--header "Authorization: Bearer ${DOCS_TOKEN}")
fi

mkdir -p build/openapi

download_document() {
  local url="$1"
  local output="$2"
  local status

  status="$(curl --fail --silent --show-error \
    "${auth_args[@]}" \
    --output "$output" \
    --write-out '%{http_code}' \
    "$url")"

  if [[ "$status" != "200" ]]; then
    printf 'Expected HTTP 200 from %s, received %s\n' "$url" "$status" >&2
    return 1
  fi
}

for group in public-v1 internal-v1; do
  download_document \
    "${BASE_URL}/v3/api-docs/${group}" \
    "build/openapi/${group}.json"

  download_document \
    "${BASE_URL}/v3/api-docs/${group}.yaml" \
    "build/openapi/${group}.yaml"
done
```

`DOCS_BASE_URL` is the URL of the running application in the CI job or export environment. If the documentation endpoint requires a bearer token, supply `DOCS_TOKEN` from the CI secret store. Do not enable shell tracing (`set -x`) while handling tokens and do not print Authorization headers to logs. If public documentation needs no authentication, leave `DOCS_TOKEN` empty.

`curl --fail` makes the job fail when the server returns an HTTP error such as `401`, `403`, or `404`. This prevents the pipeline from saving an HTML login or error page under a `.json` filename and treating it as valid documentation.

The download_document function requires status 200 and does not automatically follow redirects. This helps catch wrong URLs or redirects to a login page while avoiding forwarding the bearer header to another host during a redirect. If the system has an intentional redirect, configure the final target URL in DOCS_BASE_URL instead of blindly enabling redirect following.

## 4. Validating the downloaded document before comparison

After exporting, verify that each JSON file is a structurally valid OpenAPI document at a basic level:

```bash
for group in public-v1 internal-v1; do
  jq -e '
    (.openapi | type == "string") and
    (.paths | type == "object")
  ' "build/openapi/${group}.json" >/dev/null
done
```

This check catches invalid JSON syntax, HTML responses, or documents missing `openapi`/`paths`. It does not replace an OpenAPI validator: JSON with valid basic structure can still contain broken `$ref`s, invalid schemas, or wrong metadata.

If you need to check YAML, use a YAML parser or OpenAPI linter pinned to a specific version in CI. Avoid running a generic `yq` command without confirming it matches the implementation and syntax expected on your project's runner.

## 5. Storing an expected-endpoint manifest per group

The manifest should list one operation per line in the format `HTTP_METHOD path`. For example:

`ci/openapi/expected-public-v1.txt`:

```text
GET /api/public/catalog
GET /api/public/products/{id}
POST /api/public/orders
```

`ci/openapi/expected-internal-v1.txt`:

```text
DELETE /api/admin/orders/{id}
GET /api/admin/audit-events
GET /api/internal/health
```

The manifest describes the exact operations allowed to appear in each document. Use path templates like `{id}` matching OpenAPI; do not substitute concrete ID values. Sort lines in a deterministic order and keep no duplicate lines.

This list acts as the group's contract allowlist. If an endpoint is missing, CI catches the missing line. If an out-of-scope endpoint appears, CI catches the extra line. Both cases require review: either code/filters are wrong, or the manifest needs updating for an approved API change.

## 6. Extracting HTTP methods and paths with `jq`

OpenAPI places endpoints inside the `paths` object. Each path contains one or more operations keyed by HTTP method. You can extract exact method/path pairs with:

```bash
jq -r '
  (.paths // {})
  | to_entries[]
  | . as $path
  | $path.value
  | to_entries[]
  | select(.key | test("^(get|put|post|delete|patch|options|head|trace)$"))
  | "\(.key | ascii_upcase) \($path.key)"
' build/openapi/public-v1.json \
  | LC_ALL=C sort -u
```

The output looks like:

```text
GET /api/public/catalog
GET /api/public/products/{id}
POST /api/public/orders
```

Only HTTP operation keys are counted. Other Path Item properties such as `parameters`, `servers`, `summary`, `description`, or `$ref` are not mistaken for endpoints. Combining both method and path also distinguishes `GET /orders` from `POST /orders`.

## 7. Performing exact comparison in CI

Generate the actual endpoints file from JSON and run `diff` against the manifest:

```bash
for group in public-v1 internal-v1; do
  expected="ci/openapi/expected-${group}.txt"
  actual="build/openapi/${group}.actual.txt"

  test -f "$expected"

  jq -r '
    (.paths // {})
    | to_entries[]
    | . as $path
    | $path.value
    | to_entries[]
    | select(.key | test("^(get|put|post|delete|patch|options|head|trace)$"))
    | "\(.key | ascii_upcase) \($path.key)"
  ' "build/openapi/${group}.json" \
    | LC_ALL=C sort -u > "$actual"

  LC_ALL=C sort -c "$expected"
  diff -u "$expected" "$actual"
done
```

`diff` returns a non-zero exit code if the two sets differ, failing the CI job under `set -e`. The output shows which operations are missing or unexpectedly present. `sort -c` confirms the manifest is sorted under the same locale before comparison.

Keep the manifest in the repository alongside API changes. When adding a new operation, update the manifest in the same pull request so reviewers can verify whether that endpoint belongs in the published group. Do not overwrite the manifest automatically from freshly exported output; doing so renders the allowlist check meaningless.

## 8. Example output when the endpoint set is wrong

Suppose the public manifest expects:

```text
GET /api/public/catalog
GET /api/public/products/{id}
POST /api/public/orders
```

But the actual document includes an extra internal endpoint:

```text
DELETE /api/admin/orders/{id}
GET /api/public/catalog
GET /api/public/products/{id}
POST /api/public/orders
```

`diff -u` reports the `DELETE /api/admin/orders/{id}` line as an addition. This signals a need to investigate `pathsToMatch`, `pathsToExclude`, package filters, or customizers on the public group. Remove the line from the artifact only after fixing the document-generation source and re-running the export.

If `/api/public/products/{id}` is missing, diff reports a deletion. Check controller mappings, path/package filters, hidden annotations, and auto-configuration conditions. Do not edit the manifest to accept a missing endpoint without confirming it is an intentional contract change.

## 9. Handling groups with overlapping filters

An operation can appear in multiple groups if multiple filters match it. For example, `/api/public/catalog` can be included in both `public-v1` and `all-v1`. This is not necessarily an error.

Create a separate manifest for each group:

| Group | Expected manifest | Rule |
| --- | --- | --- |
| `public-v1` | Public endpoints only | Contains no internal or admin routes. |
| `internal-v1` | Allowed internal and admin endpoints | Does not automatically include public routes unless intended. |
| `all-v1` | All APIs selected for publication | May include endpoints belonging to other groups. |

Do not assume groups are disjoint sets. If they must not intersect, add an intersection check across manifests or actual endpoint sets. If overlap is intentional, document it in the manifests and review changes across every affected group.

## 10. Additional checks for operation IDs, schemas, and security

Comparing methods and paths verifies the endpoint set, but it does not check the entire contract. Additional CI steps can be added:

- **Operation ID:** confirm `operationId` values are unique within a document so client generators produce stable method names.
- **Schema:** check types, required fields, enums, formats, and validation metadata.
- **References:** confirm every `$ref` points to a valid component.
- **Security:** confirm public groups do not accidentally publish operations with wrong or missing security requirements.
- **Media types and responses:** inspect `requestBody`, `content`, status codes, and headers.
- **Compatibility:** compare the document with the released version to detect breaking changes.

Use a version-pinned OpenAPI validator/linter and dedicated diff tool. An exact endpoint manifest and an OpenAPI contract diff answer two different questions: which endpoints are present, and whether endpoint contract details changed compatibly.

## 11. Protecting documentation when exporting from a running environment

CI may need to call documentation endpoints on a running application. If a group is internal-only, the pipeline must use credentials authorized to read that specific group. Do not expose all of `/v3/api-docs/**` to the public Internet just so CI can fetch artifacts.

Key points:

- Use a service account or short-lived token with read access to the documentation to export.
- Store tokens in the CI secret store, never committed into scripts or manifests.
- Do not enable shell tracing when tokens are in environment variables.
- Fetch each group via its specific URL; do not assume that hiding a group from Swagger UI secures its endpoint.
- If the API docs path is customized, configure the CI base URL to match the actual path.
- Behind a reverse proxy, use a public URL reachable by the runner and check forwarded prefixes.
- Do not publish internal artifacts to a public artifact store; permissions at storage time matter just as much as permissions on the download endpoint.

If the pipeline runs in the same network as the service, you can export via an internal URL. Even then, verify the document belongs to the right group and build version; being able to reach an internal endpoint does not guarantee the request hit the right instance.

## 12. Testing export with Spring Boot tests

In addition to exporting from a running application, you can verify each group in a test context. Example with MockMvc:

```java
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiGroupExportTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publicGroupContainsOnlyExpectedOperation() throws Exception {
        mockMvc.perform(get("/v3/api-docs/public-v1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.paths['/api/public/catalog'].get").exists())
            .andExpect(jsonPath("$.paths['/api/admin/orders/{id}']").doesNotExist());
    }

    @Test
    void internalGroupContainsAdminOperation() throws Exception {
        mockMvc.perform(get("/v3/api-docs/internal-v1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.paths['/api/admin/orders/{id}'].delete").exists());
    }
}
```

This is an example checking a few critical paths in a test context. Manifest + `jq` + `diff` in CI is what verifies the full method/path set of the exported document. If the docs endpoint is secured in tests, configure appropriate authentication or test security; never disable production security just to test export.

## 13. Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Group export returns `404` | Group id does not exist or wrong base path URL | Check `.group(...)`, `springdoc.api-docs.path`, and context path. |
| Group export returns `401`/`403` | CI lacks credentials or authority to read docs | Supply a properly scoped token/service account via secret store. |
| `.json` file is actually HTML | Server redirected to login or proxy returned error page | Use `curl --fail`, check status and `Content-Type`. |
| JSON downloads but `jq` errors | Response is not valid JSON or file is empty | Inspect response body and request URL before running diff. |
| Public group contains internal endpoint | Overlapping filters, wrong excludes, or customizer added operation | Compare manifests, check filters, and fix group configuration. |
| Group misses newly added endpoint | Controller not scanned or path does not match filter | Check mappings, package/path filters, and hidden annotations. |
| JSON works but YAML fails to download | Wrong YAML URL, or proxy/security does not route `.yaml` suffix | Check `${group}.yaml` and matcher/gateway rules. |
| Diff always fails despite identical endpoints | Manifest unsorted, method casing differs, or path template mismatch | Normalize uppercase methods, exact path templates, and locale sorting. |
| Diff misses schema changes | Manifest only checks method/path | Add an OpenAPI validator and contract diff. |
| Internal group artifact published publicly | Pipeline shares artifact storage location | Split jobs, repositories, or read permissions per documentation group. |
| Document comes from stale instance | CI called wrong URL, pod, or un-updated deployment | Verify build/version and readiness before exporting. |

## 14. Pipeline checklist

Before marking an export successful, verify:

1. Group ids in the export list match `GroupedOpenApi` beans or `springdoc.group-configs`.
2. JSON and YAML are fetched from the exact URL of each group.
3. HTTP errors fail the job; non-document responses are never stored as valid artifacts.
4. JSON is parseable and contains `openapi` along with `paths`.
5. Expected manifests exist, are sorted, and are reviewed in the repository.
6. The actual `HTTP_METHOD path` set matches each group's manifest exactly.
7. Group overlaps are checked and intentionally accepted.
8. An OpenAPI validator/linter checks schemas, `$ref`s, security, and responses.
9. Artifacts are named by group id and build version.
10. Internal documentation is stored only in locations with appropriate access permissions.

## 15. Implementation principles

- Export `/v3/api-docs/{group}` and `/v3/api-docs/{group}.yaml` for every group to publish.
- Use stable group ids for naming artifacts and manifests.
- Use JSON as machine-parseable input; save YAML if review processes need a human-readable format.
- Maintain a separate `HTTP_METHOD path` allowlist for each group.
- Extract operations from `paths` using a JSON parser, never by grepping strings in files.
- Use `diff` to catch both missing endpoints and unexpected extra endpoints.
- Never auto-update manifests from freshly exported documents; require review of contract changes.
- Treat filter overlap as behavior to verify, never assume groups are mutually exclusive.
- Supplement with OpenAPI lint/contract diff to check schemas and compatibility beyond the endpoint set.
- Protect export endpoints, CI tokens, and internal artifacts with proper permissions.

Exporting per group produces OpenAPI artifacts scoped accurately for publication; endpoint manifests let CI verify the exact operations allowed to appear. When the pipeline fetches JSON/YAML per group id, extracts `(method, path)` pairs, and compares them with `diff`, unintended changes are caught before documentation is published. Combining this step with OpenAPI validation and artifact access control keeps each group's documentation stable, reviewable, and aligned with the agreed API scope.

## References

- [Springdoc OpenAPI – Multiple OpenAPI Definitions / GroupedOpenApi](https://springdoc.org/faq.html)
- [Springdoc OpenAPI – API Docs and YAML configuration](https://springdoc.org/)
- [OpenAPI Specification – Paths Object](https://spec.openapis.org/oas/latest.html#paths-object)
- [jq Manual](https://jqlang.org/manual/)
