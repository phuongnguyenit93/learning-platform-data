# Semantic Comparison of Specifications Before and After Migration

When upgrading Spring Boot, springdoc-openapi, or migrating an OpenAPI document to a new specification version, the generated document can change across many lines even when the runtime API stays unchanged. Conversely, a change of just a few characters in a schema can stop clients from sending valid requests or reading responses.

Therefore, comparing two YAML/JSON files with a text diff is not enough to conclude a migration is safe. You must compare **contract semantics**: which operations exist, what data clients can send, what statuses and representations the server commits to return, how authentication is required, and how SDK generators interpret the document.

In the springdoc-openapi module, this workflow typically starts by fetching OpenAPI documents from the same application before and after migration, validating each document, running a semantic diff, testing sample payloads, and reviewing changes that affect consumers.

## 1. Distinguish text diff, semantic diff, and compatibility diff

Three kinds of comparison answer three different questions:

| Comparison type | Question | Example |
|---|---|---|
| Text diff | Which lines or characters changed? | YAML reordered properties, changed indentation, or replaced nullable with type containing null |
| Semantic diff | How closely do the two documents describe the same behavior and accepted data sets? | Do the before and after schemas accept the exact same request values? |
| Compatibility diff | Can consumers using the old contract continue working with the new contract? | Does adding a required query parameter break existing clients? |

A text diff is useful for reviewing source changes, but it does not understand OpenAPI structure. A semantic diff parses documents according to the OpenAPI model and compares operations, parameters, schemas, responses, security, and related components. A compatibility diff evaluates changes from a consumer/provider perspective to flag breaking risks.

**Semantic equivalence does not imply backward compatibility.** For example, changing a schema from OpenAPI 3.0 nullable to an OpenAPI 3.1 union type including null can preserve the valid value set. Conversely, adding a required property to a request may be valid under the new spec while breaking older clients that cannot send successful requests.

## 2. Ensure the two documents represent the right comparison pair

Before running tools, confirm the two files represent the exact same API contract at two points in time:

- Same service and same API domain.
- Same group, e.g., orders-v1.
- Same Spring Boot profile and properties affecting controller mapping.
- Same context path or public path rules.
- Same data sources and customizer configuration if they influence the document.
- Same authentication scope when fetching the documentation endpoint.
- One file is the pre-migration baseline, and the other is the post-migration candidate.

Do not compare orders-v1 against orders-v2 and conclude the migration altered the contract. Those are two different API versions. Similarly, do not compare a pre-migration default document against a post-migration group if their operation scopes differ.

Store artifacts in a structure that identifies source and stage:

~~~text
artifacts/
└── openapi/
    ├── baseline/
    │   └── orders-v1.json
    └── candidate/
        └── orders-v1.json
~~~

The baseline should come from a published release or approved commit. The candidate should be generated from the exact commit under review. Avoid comparing two files fetched from environments with different configs because environmental differences can be mistaken for migration changes.

## 3. Fetch OpenAPI documents from springdoc before and after migration

springdoc generates OpenAPI documents from Spring-managed controllers, annotations, models, and configuration. For the default document, the endpoint is typically:

~~~text
/v3/api-docs
~~~

For a group, the endpoint typically takes the form:

~~~text
/v3/api-docs/{groupName}
~~~

Example fetching the same orders-v1 group from two independent instances:

~~~bash
curl -fsS http://localhost:8081/v3/api-docs/orders-v1 -o artifacts/openapi/baseline/orders-v1.json
curl -fsS http://localhost:8082/v3/api-docs/orders-v1 -o artifacts/openapi/candidate/orders-v1.json
~~~

On Windows PowerShell, use curl.exe to avoid PowerShell's curl alias:

~~~powershell
curl.exe -fsS http://localhost:8081/v3/api-docs/orders-v1 -o artifacts/openapi/baseline/orders-v1.json
curl.exe -fsS http://localhost:8082/v3/api-docs/orders-v1 -o artifacts/openapi/candidate/orders-v1.json
~~~

If the documentation endpoint is protected, supply authentication per environment policy. Never store access tokens or secrets inside OpenAPI files or pipeline logs.

When an application has multiple groups, repeat the process for each group and store each baseline/candidate pair separately. Do not merge documents before verifying each group's scope.

## 4. Validate each document before comparing

A semantic diff is only meaningful when both inputs parse and validate cleanly. Validate each file independently:

~~~bash
oasdiff validate artifacts/openapi/baseline/orders-v1.json
oasdiff validate artifacts/openapi/candidate/orders-v1.json
~~~

Validation catches syntax errors, OpenAPI structural issues, or schema rule violations before you interpret diff output. If the candidate is invalid, fix document generation or the migration before classifying changes.

Do not use diff results as a substitute for validation. Two documents can look identical on most operations while sharing a broken schema; conversely, both documents can be valid while having incompatible contracts.

If external $ref links are used, ensure references resolve from the same reproducible baseline. Diff tools may need to fetch external resources; allow that only for trusted sources. For untrusted documents, run in a network-restricted environment or disable external reference resolution per tool options to prevent unintended external access.

## 5. Compare equivalent schemas after migrating OpenAPI 3.0 to 3.1

A specification migration can alter how a schema is written without changing the set of valid values. Example of nullability:

OpenAPI 3.0:

~~~yaml
displayName:
  type: string
  nullable: true
~~~

OpenAPI 3.1:

~~~yaml
displayName:
  type:
    - string
    - 'null'
~~~

If the property may be omitted in both versions, is not added to required, and runtime handles null as before, the two schemas represent the same semantics for that property.

Another example is numeric bounds:

OpenAPI 3.0:

~~~yaml
age:
  type: integer
  minimum: 18
  exclusiveMinimum: true
~~~

OpenAPI 3.1:

~~~yaml
age:
  type: integer
  exclusiveMinimum: 18
~~~

Both forms require a value strictly greater than 18. If a migration accidentally produces minimum: 18, the value 18 becomes accepted and the valid data set has changed.

When reviewing, classify each change explicitly as:

1. Representation change due to specification version differences.
2. Metadata or documentation change.
3. Change to the value set accepted by the schema.
4. Change to HTTP behavior or how consumers call the API.

Do not label every schema difference as breaking, yet do not conclude safety merely because property names and types appear similar at a glance.

## 6. Semantic dimensions to compare

An OpenAPI document has multiple parts affecting consumers. Review across every dimension rather than counting diff lines.

| Component | What to check | Example of impactful change |
|---|---|---|
| Paths and methods | URLs, HTTP methods, path templates | Removing GET /orders/{id} |
| Parameters | name, in, required, style, explode, schema | Adding a required query parameter |
| Request body | required, media type, schema | Switching JSON to multipart |
| Schema | type, format, enum, required, bounds, nullability, composition | Narrowing an enum or dropping null |
| Responses | Status codes, media types, headers, body schemas | Removing response 404 |
| Security | Schemes, requirements, OAuth scopes | Requiring a new scope |
| Servers | Base URLs, server variables, protocols | Changing public host or prefix |
| Operation metadata | operationId, deprecated, tags | Renaming operationId changes SDK method names |
| References | $ref, $id, external schemas | Reference points to a different schema |
| Extensions | x-* vendor extensions | Gateways or generators stop picking up policies |
| Webhooks/callbacks | Events, callback URLs, and payloads | Removing an event consumers listen to |

Some changes affect only displayed documentation, yet can still affect SDK generators or portals. Thus, separate impacts on the wire contract from impacts on developer experience and toolchains.

## 7. Classify changes by request and response direction

You cannot evaluate a schema merely by asking whether a type changed. Consider who sends the data and who receives it.

| Change | Typical impact direction | Initial assessment |
|---|---|---|
| Add optional request property | Clients can continue omitting the property | Usually backward compatible |
| Add request property to required | Older clients omitting the property are rejected | Breaking |
| Remove supported request property | Older clients still send a field the server no longer handles properly | Potentially breaking |
| Narrow request enum | Clients sending old values become invalid | Breaking |
| Expand request enum | Server accepts additional values | Usually backward compatible |
| Remove response property | Consumers reading that property may fail | Breaking |
| Change response property to incompatible type | Consumer deserialization or validation fails | Breaking |
| Add response property | Tolerant consumers usually ignore it | Usually compatible, check additionalProperties and strict clients |
| Remove response status or media type | Consumers stop receiving a branch they relied on | Breaking |
| Add new response status | Consumers may need to handle the new branch | Usually non-breaking, though clients without fallbacks may error |

This is a baseline classification, not an absolute law for every consumer. For instance, adding a response property can break a consumer validating schemas with additionalProperties: false. Conversely, a server might continue accepting an old request property even when the new document no longer describes it; in that case runtime and documentation have drifted out of sync.

## 8. Security and servers are also contract semantics

A migration can keep paths and schemas identical while still changing accessibility:

- Adding an operation-level security requirement rejects unauthenticated legacy requests.
- Changing OAuth scopes can render existing access tokens insufficient.
- Changing security scheme names or types can stop Swagger UI and SDKs from configuring authentication as before.
- Changing servers.url can route clients to the wrong host or prefix.
- Changing header parameters, style, or explode can alter how clients serialize queries/paths.

Do not lump these changes under metadata. Security requirements and server URLs determine whether requests reach the right service and are accepted.

Removing a security requirement might not break old clients, yet it weakens protection. Compatibility reports do not replace security reviews; changes that relax permissions still require approval.

## 9. OperationId and component structure can affect SDKs

operationId is commonly used as the method name in SDK generators. Changing getOrderById to findOrder may not alter HTTP requests/responses, yet regenerated SDKs can rename public methods and break consumer compilation.

Similarly, renaming a component or moving a schema between inline and $ref may only be document restructuring. If the resolved schema remains equivalent, the wire contract may hold. However, some generators use component names for SDK class names; hence component renames can alter the SDK's public API.

When publishing SDKs from OpenAPI, add a verification step:

1. Generate the SDK from the baseline.
2. Generate the SDK from the candidate using the same generator and config.
3. Compare the public APIs of both SDKs or compile consumer fixtures.
4. Review changes in class names, method names, enums, parameters, and packages.

Never declare SDK compatibility based solely on an HTTP contract report.

## 10. Use oasdiff to generate three reporting views

oasdiff offers commands with distinct purposes:

| Command | Contents | When to use |
|---|---|---|
| oasdiff diff | Full diff of definitions, including documentation changes | Investigating all differences between two artifacts |
| oasdiff changelog | Changes that may affect consumers, both breaking and non-breaking | Producing a report for reviewers |
| oasdiff breaking | Only changes classified as risking breakage of existing clients | Blocking incompatible migrations in CI |
| oasdiff validate | Validates a single document | Verifying each input before diffing |

Run:

~~~bash
oasdiff diff artifacts/openapi/baseline/orders-v1.json artifacts/openapi/candidate/orders-v1.json --format markdown
~~~

View consumer-impacting changes:

~~~bash
oasdiff changelog artifacts/openapi/baseline/orders-v1.json artifacts/openapi/candidate/orders-v1.json --format markdown
~~~

Check breaking changes only:

~~~bash
oasdiff breaking artifacts/openapi/baseline/orders-v1.json artifacts/openapi/candidate/orders-v1.json
~~~

To fail CI on high-confidence breaking changes:

~~~bash
oasdiff breaking --fail-on ERR artifacts/openapi/baseline/orders-v1.json artifacts/openapi/candidate/orders-v1.json
~~~

Per the CLI docs, the breaking command exits 0 when no breaking changes are found and 1 when breaking changes are detected. ERR indicates a definite compatibility break; WARN indicates a potentially impactful change that the tool cannot confirm from the spec alone; INFO indicates a non-breaking change. You can pass --fail-on WARN if policy requires blocking items that need investigation.

Do not save only the breaking report. diff reveals expected syntactic shifts from the migration, while changelog helps reviewers see which changes can affect consumers.

## 11. Why semantic diffs still need manual review

Diff tools analyze structure and apply predefined rules. They do not know every detail of how consumers use the API, runtime configurations, or custom behaviors outside the document.

Examples requiring manual review:

- operationId changed while wire requests/responses stayed unchanged; SDK method names may change.
- Server URL varies by environment; verify public URLs and reverse proxies.
- Security requirements relaxed; not technically breaking, yet a security change.
- Vendor extension x-* removed; gateways or internal generators may depend on it.
- Schemas with nested oneOf, anyOf, allOf, or $ref; verify semantics after resolving the entire graph.
- Formats such as date-time, uuid, or email may be interpreted differently by validators and code generators.
- Schemas with readOnly, writeOnly, default, discriminator, or additionalProperties; small changes can affect serializers/deserializers.

oasdiff has defaults to avoid unnecessary noise, such as recognizing equivalent inline schemas and $ref inside anyOf/oneOf branches, or comparing header names case-insensitively. Options such as flattening allOf or flattening parameters alter matching behavior and should not be enabled casually. When output depends on options, commit the diff config to the repository so runs remain reproducible.

## 12. Test the payload set accepted by schemas

A document semantic diff should be complemented by a suite of sample payloads. The goal is to confirm before and after schemas accept or reject the same critical cases.

Example Customer schema with a nullable property:

~~~json
{
  "id": "c-100",
  "displayName": null
}
~~~

Create fixtures:

| Payload | Meaning | Expected before/after if migration preserves semantics |
|---|---|---|
| displayName is a string | Normal value | Both accept |
| displayName is null | Check nullability | Both accept |
| displayName omitted | Check optional/required | Both preserve the same result |
| displayName is a number | Check type | Both reject |
| id missing | Check required | Both preserve the same result |

For numeric bounds, also test boundary values:

| Payload age | Schema requires greater than 18 |
|---:|---|
| 17 | Reject |
| 18 | Reject |
| 19 | Accept |

Run the same fixtures through a validator matching each document's dialect. OpenAPI 3.0 uses its own schema model; OpenAPI 3.1 builds on JSON Schema Draft 2020-12. Configure the validator for the exact dialect rather than using an unspecified default configuration for both.

Beyond schema validators, send fixtures to the application's test endpoints to verify runtime enforces the contract accurately. A document may describe rules accurately while controllers, deserializers, or validation annotations behave differently.

## 13. Example of a semantics-preserving migration

Suppose before migration, springdoc generates OpenAPI 3.0.3:

~~~yaml
openapi: 3.0.3
info:
  title: Customer API
  version: 1.4.0
paths:
  /customers:
    post:
      operationId: createCustomer
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateCustomer'
      responses:
        '201':
          description: Customer created
components:
  schemas:
    CreateCustomer:
      type: object
      required:
        - name
      properties:
        name:
          type: string
        nickname:
          type: string
          nullable: true
        age:
          type: integer
          minimum: 18
          exclusiveMinimum: true
~~~

After migration, OpenAPI 3.1.1 document:

~~~yaml
openapi: 3.1.1
info:
  title: Customer API
  version: 1.4.0
paths:
  /customers:
    post:
      operationId: createCustomer
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateCustomer'
      responses:
        '201':
          description: Customer created
components:
  schemas:
    CreateCustomer:
      type: object
      required:
        - name
      properties:
        name:
          type: string
        nickname:
          type:
            - string
            - 'null'
        age:
          type: integer
          exclusiveMinimum: 18
~~~

In this example, path, method, operationId, request body, status, and required properties stay identical. Two schema conversions preserve the valid data set:

- nickname still accepts strings or null; the property remains optional because it is not listed in required.
- age must still be strictly greater than 18.

If a diff flags those schema changes, reviewers should confirm they are OAS-version representation shifts and that boundary test fixtures yield identical results. Do not treat such syntactic conversions as breaking when semantics are genuinely preserved.

## 14. Example of a migration that accidentally alters the contract

Suppose the candidate turns nickname into:

~~~yaml
nickname:
  type: string
~~~

The candidate no longer permits null. Older consumers sending nickname: null may now be rejected by validation.

Or the candidate turns age into:

~~~yaml
age:
  type: integer
  minimum: 18
~~~

The value 18 was previously invalid and is now accepted. That alters the valid data set. It might not break existing clients, yet semantics are no longer equivalent and business logic may be affected.

Another example is adding a required property:

~~~yaml
required:
  - name
  - countryCode
~~~

Older clients sending only name no longer satisfy the schema. That is a request-side breaking change. If countryCode is a new business requirement, put a versioning or transition plan in place rather than merely editing the document.

## 15. Integrate comparison into CI after upgrading springdoc

A pipeline can run in this sequence:

1. Check out the baseline from an approved release or commit.
2. Build both baseline and candidate applications using their respective configs.
3. Start each build in an isolated test environment.
4. Fetch the same OpenAPI group from both builds.
5. Validate both documents.
6. Run oasdiff diff and archive the full report.
7. Run oasdiff changelog so reviewers see consumer-facing changes.
8. Run oasdiff breaking --fail-on ERR to block unapproved breaking changes.
9. Run schema fixtures and integration tests for critical payloads/statuses.
10. Review security, server URLs, operationIds, vendor extensions, and SDKs if applicable.
11. Archive the candidate document and diff reports as release artifacts.

Example PowerShell commands in CI:

~~~powershell
oasdiff validate .\artifacts\openapi\baseline\orders-v1.json
if ($LASTEXITCODE -ne 0) { throw "Baseline OpenAPI document is invalid" }

oasdiff validate .\artifacts\openapi\candidate\orders-v1.json
if ($LASTEXITCODE -ne 0) { throw "Candidate OpenAPI document is invalid" }

oasdiff diff .\artifacts\openapi\baseline\orders-v1.json .\artifacts\openapi\candidate\orders-v1.json --format markdown
if ($LASTEXITCODE -ne 0) { throw "OpenAPI diff failed" }

oasdiff breaking --fail-on ERR .\artifacts\openapi\baseline\orders-v1.json .\artifacts\openapi\candidate\orders-v1.json
if ($LASTEXITCODE -ne 0) { throw "Breaking OpenAPI changes detected" }
~~~

Paths and artifact download steps must match your actual pipeline. If the diff finds an intentionally approved breaking change, record the decision with the report and apply the appropriate versioning policy; never delete the baseline or skip reports just to turn the pipeline green.

## 16. Choose comparison tools matching the specification version

Tools vary in specification coverage:

| Tool | Best suited for | Notes |
|---|---|---|
| oasdiff | Comparing OpenAPI 3.0, 3.1, and 3.2; breaking/non-breaking classification | Provides diff, changelog, breaking, validate commands and multiple report formats |
| OpenAPITools openapi-diff | Projects comparing OpenAPI 3.0 documents | Project README states OAS 3.0 support; check version support before using on 3.1/3.2 documents |
| Git text diff | Reviewing YAML/JSON source edits | Does not analyze semantics or compatibility |

For migrations from OAS 3.0 to 3.1, choose a tool whose parser supports both versions. Per published docs, oasdiff supports 3.0, 3.1, and 3.2; OpenAPITools' openapi-diff currently states OpenAPI 3.0 support. Do not choose a tool based solely on its name or star count; verify which spec versions it actually parses.

Pin the diff tool version in CI. Given the exact same document pair, different rule-engine versions can classify changes differently after rule updates or bug fixes.

## 17. Common mistakes when reading reports

| Symptom | Possible cause | Resolution |
|---|---|---|
| Diff shows many changes despite unchanged API | Compared raw text or YAML layout only | Use a parser and semantic diff; separate representation shifts |
| Diff misses runtime behavior changes | OpenAPI document does not express all execution logic | Add integration tests and payload fixtures |
| Reports breaking after OAS version change | Schema migration altered nullability, bounds, or required flags | Compare semantics per schema and test boundary payloads |
| Cannot resolve $ref | Missing referenced file, wrong base URI, or unreachable external resource | Bundle references, fix base URI, and verify access permissions |
| Report shows massive changes from component renames | Schema refactoring or generator renamed models | Verify resolved schemas are equivalent and check SDKs |
| No breaking changes reported yet clients fail | operationId, server URL, auth, or extensions changed | Review toolchain, security, and API call environment |
| CI results differ from local machine | Different oasdiff versions, configs, or external refs | Pin tool version, commit config, and fix input artifacts |
| WARN items ignored | Failing only on ERR | Review WARN items or tighten failure level per team policy |
| Candidate is valid yet contract is broken | Syntax validation does not check compatibility | Run diff, fixtures, and runtime contract tests |
| Diff between two different groups | Baseline/candidate do not share the same group or filters | Verify group names, URLs, and operation scopes before comparing |

## 18. Checklist confirming migration preserves semantics

- [ ] Baseline and candidate belong to the same service, API version, and group.
- [ ] Both documents are generated from reproducible configuration.
- [ ] Both documents parse and validate cleanly.
- [ ] paths and HTTP methods cover the expected scope.
- [ ] Parameters preserve in, required, style, explode, and schema.
- [ ] Request bodies preserve media types and valid value sets.
- [ ] Responses preserve status codes, media types, headers, and schemas.
- [ ] Nullability, enums, bounds, required flags, and composition are compared semantically.
- [ ] $ref, allOf, oneOf, anyOf, and external schemas resolve properly.
- [ ] Security schemes, OAuth scopes, and security requirements are reviewed.
- [ ] Server URLs and context paths point to the right public endpoints.
- [ ] operationIds, component names, and extensions are checked if SDKs/gateways rely on them.
- [ ] Semantic diff and breaking-change reports have been run.
- [ ] Payload fixtures have been validated using dialect-matched validators.
- [ ] Runtime verified with integration/contract tests.
- [ ] Breaking changes have versioning decisions and approval.
- [ ] Diff reports and candidate artifacts are archived with the release.

## 19. Official references

- [oasdiff — CLI Quick Start](https://www.oasdiff.com/docs/getting-started) — installation, validate, diff, changelog, breaking, exit codes, and report formats.
- [oasdiff — Breaking Changes and Changelog](https://github.com/oasdiff/oasdiff/blob/main/docs/BREAKING-CHANGES.md) — ERR/WARN/INFO severity levels and CI failure configuration.
- [oasdiff — Diff](https://github.com/oasdiff/oasdiff/blob/main/docs/DIFF.md) — default comparison behavior, matching inline schemas with $ref, and options affecting diffs.
- [oasdiff — Supported OpenAPI versions](https://www.oasdiff.com/diff) — support scope across OpenAPI 3.0, 3.1, and 3.2.
- [OpenAPITools — openapi-diff](https://github.com/OpenAPITools/openapi-diff) — OpenAPI diff tool; README currently states OpenAPI 3.0 support.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html) — structure and semantics of OpenAPI documents.

Semantic comparison before and after migration verifies whether the API contract retains its intended meaning. Use the same group and a trustworthy baseline, validate each document, run semantic diffs, test sample payloads, and review changes to security, server URLs, and SDKs. Tool reports pinpoint changes; release decisions must still rest on actual contracts and consumer behavior.
