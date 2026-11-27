# Comparing URIs, Headers, and Payloads After an Upgrade

## 1. Why Compare Contracts After an Upgrade?

In the **Spring REST Docs (SPRING_REST_DOCS)** module under the **Upgrade** chapter, upgrading Spring Boot, Spring Framework, Spring REST Docs, or HTTP libraries can alter how the application builds requests/responses and how snippets are generated. Even a seemingly minor dependency bump can affect URIs, headers, media types, JSON serialization, or payload data types.

Spring REST Docs generates snippets from HTTP exchanges in tests. As a result, reviewed snippets stored in version control can serve as a baseline to compare contracts before and after an upgrade. Tests verify current behavior; snippet diffs help reviewers spot documentation changes.

Lesson goals:

- Maintain a snippet baseline before upgrading.
- Run the same documentation tests on the new version.
- Compare URIs, request/response headers, status codes, media types, and payloads.
- Classify compatible changes versus breaking changes.
- Update descriptors and documentation once a new contract is confirmed as intentional.
- Bring diffs into code review/CI to prevent unintended API changes.

Examples use **Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter, MockMvc, and Asciidoctor**. The workflow is similar for WebTestClient or REST Assured.

## 2. What Is a Snippet Baseline?

A baseline is the set of snippets generated from an approved API version and committed alongside source code. An operation might have:

```text
build/generated-snippets/
  products-find/
    http-request.adoc
    http-response.adoc
    response-body.adoc
    response-fields.adoc
    response-headers.adoc
```

Not every snippet file represents the same level of contract criticality:

| Snippet | Content to Compare |
| --- | --- |
| http-request.adoc | Method, URI, query string, request headers |
| http-response.adoc | HTTP status and response headers |
| response-body.adoc | Actual JSON/XML payload |
| request-fields.adoc | Documented request fields |
| response-fields.adoc | Documented response fields |
| path-parameters.adoc / query-parameters.adoc | Parameter names and semantics |
| links.adoc | Hypermedia relations and URIs |

A baseline is valuable when generated from deterministic fixtures without timestamps, random IDs, developer machine hostnames, or personal data. If snippets contain varying values, normalize them via fixtures or operation preprocessors before saving the baseline.

## 3. Pre- and Post-Upgrade Comparison Workflow

```text
Current version
      |
      v
Run documentation tests
      |
      v
Save/commit baseline snippets
      |
      v
Upgrade dependency or framework
      |
      v
Re-run the same documentation tests
      |
      v
Compare snippets
      |
      +---- Unchanged ----> Build docs and confirm
      |
      +---- Changed ------> Classify contract change
                                  |
                    +-------------+-------------+
                    |                           |
               Intentional                  Unintended
                    |                           |
             Review and update           Fix implementation/
             docs, baseline              upgrade configuration
```

Keep test data, operation IDs, serializer config, and environment consistent between the two snippet runs. If multiple factors change simultaneously, the diff makes root cause identification difficult.

## 4. Comparing URIs and HTTP Methods

The URI is a core part of the API contract. After upgrading, check:

- Whether the HTTP method remains the same.
- Whether the path changed prefixes, segments, variables, or trailing slashes.
- Whether path parameters kept their names and positions.
- Whether query parameters changed names, defaults, encoding, or semantics.
- Whether URI templates still preserve variables and templated markers.
- Whether host/scheme in snippets changed due to environment configuration.

Baseline:

```http
GET /api/v1/products/42?page=0&size=20 HTTP/1.1
Accept: application/json
```

After upgrading:

```http
GET /api/products/42?page=0&size=20 HTTP/1.1
Accept: application/json
```

Dropping /v1 can be a breaking change for clients calling the legacy URI. Do not accept a diff just because the new route passes in tests; determine your versioning policy and compatibility guarantees.

### Testing Path Parameters with MockMvc

Preserve the URI template when building the request:

```java
mockMvc.perform(
        RestDocumentationRequestBuilders
            .get("/api/v1/products/{id}", 42)
            .accept(MediaType.APPLICATION_JSON)
    )
    .andExpect(status().isOk())
    .andDo(document("products-find",
        pathParameters(
            parameterWithName("id")
                .description("Product ID")
        )
    ));
```

If a framework upgrade alters URI construction or encoding, tests and snippets help detect path parameters that no longer match.

## 5. Comparing Request and Response Headers

| Header | What to Check |
| --- | --- |
| Content-Type | Media type, charset, and representation |
| Accept | Representation requested by client |
| Location | URI of created resource |
| ETag | Validator and conditional requests |
| Cache-Control | Caching policy |
| Vary | Headers affecting representation selection |
| Retry-After | Wait rule before retrying |
| WWW-Authenticate | Authentication challenge |

Baseline response:

```http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/v1/products/42
```

After upgrading, the response might switch to application/hal+json or Location might change its URI. These are contract changes requiring review because clients may deserialize or navigate differently.

Header descriptors:

```java
responseHeaders(
    headerWithName("Content-Type")
        .description("Media type of the response body"),
    headerWithName("Location")
        .description("URI of the newly created product")
)
```

Required descriptors ensure tests fail if a header is no longer returned. If a header is genuinely optional, mark it optional according to the contract; do not use optional to hide regressions.

## 6. Comparing JSON Payloads

Compare both structure and semantics:

- Added or removed fields.
- Renamed fields or changed paths.
- Changed data types, such as number becoming string.
- Changed nullability or optionality.
- Changed default values or date/time formats.
- Restructured nested objects or arrays.
- Added/removed enum values.
- Changed escaping rules, decimal precision, or timezones.

Baseline:

```json
{
  "id": 42,
  "name": "Keyboard",
  "price": 89.5,
  "active": true
}
```

Post-upgrade response:

```json
{
  "id": "42",
  "name": "Keyboard",
  "price": 89.5,
  "active": true,
  "currency": "USD"
}
```

Here, id changing from number to string is a type change that can break clients; adding currency may be compatible with tolerant clients yet still requires documentation updates and consumer schema evaluation.

### Using responseFields to Enforce the Contract

```java
responseFields(
    fieldWithPath("id").description("Product ID"),
    fieldWithPath("name").description("Product name"),
    fieldWithPath("price").description("Selling price"),
    fieldWithPath("active").description("Whether the product is active")
)
```

Strict mode catches new undocumented fields. If the post-upgrade payload includes currency, the test prompts the team to decide whether to include that field in the public contract. Once approved, update descriptors and documentation alongside the code change.

Do not switch everything to relaxedResponseFields(...) just to make tests pass. Relaxed mode is suitable when an operation intentionally documents only part of a payload, but it weakens field drift detection.

## 7. Classifying Compatible vs. Breaking Changes

Not every diff is a breaking change. Evaluate based on semantics and how clients consume the API:

| Change | Common Risk | Action |
| --- | --- | --- |
| Add optional response field | Usually compatible with tolerant clients | Update descriptors/docs and check consumers |
| Remove response field | Breaking if clients use the field | Keep field, version API, or follow deprecation plan |
| Rename field | Breaking | Do not change silently; version or support alias |
| Change field type | Usually breaking | Keep old type or version contract |
| Add optional request field | Potentially compatible | Document and define default |
| Add required request field | Breaking for older clients | Version or provide default/transition |
| Change HTTP status | Can alter client flows | Evaluate semantics and retry/error handling |
| Change URI/method | Usually breaking | Maintain old route during transition period |
| Add link relation | Usually compatible if clients ignore unknown relations | Update links snippet and explain capability |
| Remove required link relation | Potentially breaking for hypermedia clients | Keep relation or version contract |
| Change Content-Type | Potentially breaking for deserializers | Check Accept negotiation and clients |

Compatibility depends on clients. Adding a response field may be safe for JSON clients that ignore unknown fields, but unsafe for clients using strict schema validation. Never judge solely from text diffs; consider contract policies and consumer behavior.

## 8. Normalizing Data for Meaningful Diffs

Unstable snippets create noisy diffs. Before comparing:

- Use fixtures with fixed IDs, timestamps, and dummy emails.
- Use modifyUris() to standardize host/scheme/port.
- Use replacePattern() to mask request IDs or random values.
- Use removeHeaders() for internal headers outside the contract.
- Use modifyHeaders() to keep headers while replacing environment-specific values.
- Never put real tokens or production data into fixtures.

Example:

```java
document("products-find",
    preprocessRequest(
        modifyUris()
            .scheme("https")
            .host("api.example.test")
            .removePort()
    ),
    preprocessResponse(
        replacePattern(
            Pattern.compile("req-[A-Za-z0-9-]+"),
            "REQUEST_ID"
        ),
        removeHeaders("X-Internal-Node", "Server")
    ),
    ...
)
```

Do not normalize away values that are part of the contract you need to verify. If detecting Location changes matters, do not replace the entire header with a placeholder prior to comparison.

## 9. Comparing Snippets in Git and CI

Workflow:

1. Commit reviewed baseline snippets from the current version.
2. Upgrade dependencies/frameworks on a dedicated branch.
3. Run clean tests to generate new snippets from the same documentation tests.
4. Compare the new snippet directory against the baseline.
5. Review diffs by operation ID and classify changes.
6. Update descriptors, Asciidoctor includes, and the baseline if changes are approved.
7. Build documentation and store artifacts in CI.

PowerShell example to compare two directories:

```powershell
$baseline = "docs-baseline/generated-snippets"
$current = "build/generated-snippets"

git diff --no-index -- "$baseline" "$current"
```

git diff --no-index returns a non-zero exit code whenever differences exist; in CI, treat that exit code as a diff signal rather than automatically failing the build on every diff. You can save the diff as an artifact for reviewers to inspect.

If the baseline is committed in the repository, store it in a dedicated directory such as src/docs/snippets-baseline, and generate new snippets into the build directory. Never let test tasks overwrite the baseline before reviewers inspect the diff.

## 10. Syncing Descriptors and Asciidoctor After Upgrading

When a contract change is approved:

- Update descriptors to reflect new payloads/headers/parameters/links.
- Update operation IDs or include paths if operations were intentionally renamed.
- Add tests for new response variants.
- Review optional/ignored/relaxed settings so strict validation is not lost.
- Update Asciidoctor prose if semantics changed.
- Regenerate baseline snippets using the exact reviewed version.

Include example:

```asciidoc
== Find Product

=== Response headers
include::{snippets}/products-find/response-headers.adoc[]

=== Response fields
include::{snippets}/products-find/response-fields.adoc[]
```

The build must ensure tests run before Asciidoctor so snippets reflect the current implementation. Configure task dependencies and input/output directories appropriately for your project.

## 11. Common Mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Diff shows varying URI hosts | Snippets depend on runtime environment | Normalize URIs using a preprocessor |
| Payload diff on timestamps/random IDs | Unstable fixtures | Use fixed data or replacePattern |
| Tests miss new fields | Overly broad relaxedResponseFields | Keep strict mode on operations representing full contracts |
| Header disappears after upgrade | Framework/security config changed | Verify whether header remains in contract and fix implementation |
| Client fails after Content-Type change | Incompatible representation | Inspect media type negotiation and clients |
| Baseline overwritten automatically | Tests write snippets into the baseline folder | Separate baseline from generated output |
| Every diff treated as breaking | No semantic classification | Review URI, status, headers, payload, and consumer impact |
| Asciidoctor include fails | Operation ID or snippet file name changed | Sync include paths with actual output |

## 12. Hands-On Exercise

Assume a Catalog API has the following contract:

1. GET /api/v1/products/{id} returns numeric id, name, price, and Content-Type application/json.
2. POST /api/v1/products returns 201 Created and Location pointing to the newly created resource.
3. Search endpoint uses page and size query parameters.

Tasks:

1. Run documentation tests and save reviewed baseline snippets.
2. Upgrade Spring Boot/Spring REST Docs on an experimental branch.
3. Re-run the exact same tests with unchanged fixtures.
4. Compare URI, method, status, Content-Type, Location, query parameters, and response fields.
5. Simulate changing id from number to string and adding currency; classify the risk of each change.
6. Intentionally remove a response field descriptor or alter a header to observe strict test failures.
7. Generate a diff artifact in CI and review it before updating the baseline.
8. Update descriptors and Asciidoctor includes once the new contract is approved.

**Completion criteria:** produce a stable snippet baseline; compare URIs/headers/payloads; identify breaking and compatible changes; maintain strict validation; review diffs before updating documentation and baseline.

## 13. References

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [Spring REST Docs — Request and Response Fields](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring REST Docs — HTTP Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/http-headers.html)
- [Spring REST Docs — Preprocessing](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/preprocessors.html)
- [Semantic Versioning 2.0.0](https://semver.org/)
