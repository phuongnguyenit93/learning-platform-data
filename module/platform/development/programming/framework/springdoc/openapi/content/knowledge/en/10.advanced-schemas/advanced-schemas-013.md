# Verifying Output Schemas Before Running Client Code Generators

springdoc-openapi can generate an OpenAPI specification from Spring Boot controllers and DTOs. That specification often serves as input to client SDK code generators, so schema quality directly affects generated data types, method signatures, and how clients invoke the API.

A clean-looking Swagger UI page does not prove the document is ready for code generation. Before releasing a spec to frontend, mobile, or partner teams, check the OpenAPI structure, schema consistency, compatibility with the chosen generator, and whether the generated client code compiles.

This lesson walks through checking the output at `/v3/api-docs`, from saving and validating the spec, reviewing error-prone elements, and test-generating a client to integrating checks into CI.

## 1. Why Must You Verify the Spec Before Code Generation?

Code generators read OpenAPI and translate the API model into target-language constructs: classes, enums, methods, parameters, request models, response models, and authentication setup. If a spec is incomplete or misdescribed, errors can surface in client code even while the Spring Boot application runs normally.

For example:

- A field may actually be absent while the schema marks it `required`, forcing clients to pass unnecessary data.
- A field may accept `null` while the schema documents it as non-null, causing generators to emit incompatible types.
- A response uses a generic wrapper yet the schema drops the concrete data type, leaving clients with a generic object.
- Two operations sharing the same `operationId` can produce colliding method names.
- A `oneOf` lacking a `discriminator` or having indistinguishable branches can cause generators to emit unusable models.
- A broken `$ref` or one pointing to a nonexistent schema can immediately halt validators and generators.

Therefore, treat the spec as a version-controlled artifact. Deliver it to consumers only after validating its structure and testing with the actual generator the team plans to use.

## 2. Exporting the Specification from springdoc-openapi

Under default configuration, springdoc serves OpenAPI JSON at:

~~~text
GET /v3/api-docs
~~~

If the application runs locally on port 8080, download the document with `curl`:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Download the YAML version:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs.yaml -o openapi.yaml
~~~

If the application has a context path or custom `springdoc.api-docs.path`, use the actual URL. When running behind an API gateway or reverse proxy, confirm requests reach the right application and environment.

Export the spec from a deterministic environment configuration. If server URLs, API groups, feature flags, or security settings change per profile, the same source code can produce different documents. Record the profile and application version used to produce the artifact.

For APIs split into groups with `GroupedOpenApi`, download and verify each group document that clients will consume. Do not assume checking the default `/v3/api-docs` document covers all groups.

## 3. Checking OpenAPI Structure and Version

Inspect the top of the JSON file to check the `openapi` field. Example:

~~~json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Shop API",
    "version": "v1"
  }
}
~~~

The `openapi` field indicates the OpenAPI specification version. It differs from the Spring Boot version, springdoc-openapi version, or the API's business version.

Check that:

- The document has valid `openapi` and `info` fields.
- `info.title` and `info.version` have clear values.
- `paths` is an object containing the expected operations.
- `components` has a valid structure.
- `servers` has URLs appropriate for the consumer environment.
- `securitySchemes` and `security` reflect actual authentication mechanisms.
- Media types match requests and responses.

Do not rely solely on the OpenAPI version number to assume generator support. A generator may support OpenAPI 3.0 better than certain 3.1 features, or support 3.1 unevenly across target languages. Check the docs and test with the exact generator version you will run.

## 4. Validating the Spec Before Code Generation

The first step is running a validator to catch syntax, structural, and invalid reference errors. With OpenAPI Generator CLI, you can run:

~~~bash
openapi-generator-cli validate -i openapi.json
~~~

If using YAML:

~~~bash
openapi-generator-cli validate -i openapi.yaml
~~~

Validators detect issues such as malformed structures, invalid fields, or unresolvable references. If the validator reports errors, fix the spec source or springdoc configuration before running code generation.

You can add a linting tool to enforce organizational conventions:

~~~bash
npx @stoplight/spectral-cli lint openapi.yaml --ruleset .spectral.yaml
~~~

A ruleset can check rules such as:

- Every operation has `summary` and `operationId`.
- `operationId` values are unique.
- Paths follow naming conventions.
- Responses document important HTTP status codes.
- Public schemas have `description` on fields needing explanation.
- No server URLs point to `localhost` in production specs.
- Security is declared in line with API policy.

Validation checks document validity; linting checks team conventions and quality standards. Both steps complement each other.

## 5. Checking operationId and Generated Method Names

`operationId` identifies an operation in OpenAPI. Many generators use it to name methods in client SDKs. If `operationId` is missing, duplicated, or changes unintentionally, generated method names become unstable.

You can declare it explicitly with `@Operation`:

~~~java
@GetMapping("/{orderId}")
@Operation(
    operationId = "getOrderById",
    summary = "Get order by ID"
)
public OrderResponse getOrder(
    @PathVariable String orderId
) {
    return orderService.getById(orderId);
}
~~~

Another operation:

~~~java
@PostMapping
@Operation(
    operationId = "createOrder",
    summary = "Create a new order"
)
public OrderResponse createOrder(
    @RequestBody CreateOrderRequest request
) {
    return orderService.create(request);
}
~~~

An `operationId` should be:

- Unique across the entire document.
- Readable and expressive of the action and resource.
- Stable across releases if clients already invoke that method.
- Independent of internal controller class or method names that may change frequently.

Changing an `operationId` can rename an SDK method even when the URL and HTTP method remain unchanged. Treat `operationId` as part of the public contract and diff it before releasing.

## 6. Checking Schema Objects and Data Types

Every schema must accurately describe the data type the API accepts or returns. Common types include:

| Java | Common OpenAPI schema | What to verify |
|---|---|---|
| `String` | `type: string` | Length, `pattern`, `enum` |
| `Integer` / `int` | `type: integer` | `format: int32` or numeric bounds |
| `Long` | `type: integer` | `format: int64` |
| `BigDecimal` | `type: number` | Precision, scale, and bounds |
| `Boolean` | `type: boolean` | Ability to distinguish missing vs. `false` |
| `LocalDate` | `type: string`, `format: date` | Date format |
| `Instant` / `OffsetDateTime` | `type: string`, `format: date-time` | Offset and time convention |
| `UUID` | `type: string`, `format: uuid` | Whether generator supports the format |
| `List<T>` | `type: array`, `items` | Concrete item type |
| `Map<String, T>` | object with `additionalProperties` | Map value type |

Do not check `type` alone. A schema with the right `type` but missing `format`, `enum`, or bounds can produce unsafe or awkward client code.

Example:

~~~yaml
quantity:
  type: integer
  format: int32
  minimum: 1
  maximum: 100
~~~

This schema describes `quantity` as an integer between 1 and 100. If the Java DTO uses `Integer` without `@Min` and `@Max` at runtime, the documentation may promise more than actual behavior enforces. Conversely, if the backend enforces bounds without publishing them in the spec, clients cannot know those limits upfront.

## 7. Checking required, nullable, and default

This category often causes mismatches between Java data types and client code.

- **`required`** indicates whether a property must appear in an object.
- **`nullable`** or a null type in the schema indicates whether a property can accept `null`, depending on the OpenAPI version.
- **`default`** describes a default value in the schema; it does not automatically ensure the backend assigns that value when a request omits the field.

Example schema with an optional field:

~~~yaml
type: object
required:
  - name
properties:
  name:
    type: string
  description:
    type: string
~~~

In this example, `name` must be present; `description` is omitted from `required`. That alone does not confirm whether `description` accepts `null`.

OpenAPI 3.0 typically uses `nullable: true`. OpenAPI 3.1 builds on JSON Schema and represents null via `type` or appropriate schema composition. Check the spec version and how your generator interprets it.

In Java, primitives such as `int` and `boolean` cannot represent `null`. If an API needs to distinguish an omitted field from `0` or `false`, request DTOs should consider `Integer` or `Boolean` paired with appropriate validation.

In particular, inspect DTOs shared between create and update. Those two operations often have different `required` rules. If a generator creates a single shared model while the two operations have different contracts, consider separate DTOs or separate schemas per operation.

## 8. Checking Enums and Extensibility

OpenAPI enums are typically translated into client-side enums. This provides type safety, yet carries a risk: the server may add new values in the future that older clients do not yet recognize.

Example:

~~~yaml
status:
  type: string
  enum:
    - PENDING
    - CONFIRMED
    - PAID
    - CANCELLED
~~~

Determine:

- Are enum values stable and consistently cased?
- Are any backend values missing?
- How do older clients handle new values returned by the server?
- Does the generator offer a fallback option for unknown enums?
- Should open values be represented as `string` rather than a closed enum on the client?

For requests, closed enums are often helpful so the server can reject invalid values. For responses, consider extensibility so older clients do not crash when the server introduces a new status.

Do not change enum values merely to adjust display names. Enum values are contract data; renaming `PAID` to `COMPLETED` requires assessing the impact on clients and stored data.

## 9. Checking $ref, Shared Schemas, and Circular References

Every internal `$ref` must point to an existing component. Example:

~~~yaml
components:
  schemas:
    OrderResponse:
      type: object
      properties:
        shippingAddress:
          $ref: '#/components/schemas/Address'

    Address:
      type: object
      properties:
        city:
          type: string
~~~

During review, check:

- Are component names unique?
- Are `$ref` JSON Pointers valid?
- Do referenced components exist?
- Do generic wrappers preserve concrete data types?
- Are there colliding schema names from `@Schema(name = ...)`?
- Are there unnecessary recursive references?

Recursive references can be valid in OpenAPI, yet not all generators handle them identically. Some generators may produce bidirectional reference models or struggle during serialization. Test with the exact target generator and language, especially for DTOs with bidirectional relationships.

Do not expose persistence entities directly in public APIs just to leverage auto-generated schemas. Entities often have lazy relations, circular references, internal fields, or unstable structures. Dedicated DTOs give far better control over schemas and clients.

## 10. Checking allOf, oneOf, anyOf, and discriminator

Schema composition is a frequent source of differences across generators.

- **`allOf`:** data must satisfy all component schemas.
- **`oneOf`:** data must match exactly one schema in the list.
- **`anyOf`:** data matches at least one schema.
- **`discriminator`:** identifies the subschema based on a property, commonly used in polymorphic models.

Example:

~~~yaml
PaymentMethod:
  oneOf:
    - $ref: '#/components/schemas/CardPayment'
    - $ref: '#/components/schemas/BankTransfer'
  discriminator:
    propertyName: type
    mapping:
      CARD: '#/components/schemas/CardPayment'
      BANK_TRANSFER: '#/components/schemas/BankTransfer'
~~~

When using `oneOf`, branches should be clearly distinguishable. `discriminator` helps clients choose the concrete type from the `type` property. Ensure this property exists and mapping values match actual payloads.

Do not assume all generators produce the same class hierarchy for `allOf` or `oneOf`. One generator might emit an interface and subclasses; another might emit wrappers or a different structure. Check your generator's configuration docs and run a small sample before locking down public schemas.

## 11. Checking Parameters and Serialization Style

Parameters have more than just names and types. For arrays or objects in query strings, serialization style also affects clients.

Array parameter example:

~~~yaml
parameters:
  - name: status
    in: query
    required: false
    schema:
      type: array
      items:
        type: string
        enum: [PENDING, PAID]
    style: form
    explode: true
~~~

With `explode: true`, clients can send repeated keys:

~~~text
?status=PENDING&status=PAID
~~~

If the API expects another format such as `status=PENDING,PAID`, declare the appropriate `style`/`explode` and verify actual Spring MVC binding.

Check parameter groups:

- Path parameters must have `required: true`.
- Query parameters have the right names and `required` flags.
- Array/object parameters have matching `style` and `explode`.
- Header parameters have exact names and do not collide with gateway-managed headers.
- Dates, date-times, UUIDs, and enums are described accurately.
- `Pageable` exposes `page`, `size`, and `sort` in the format the backend accepts.

If a generator builds a client sending query strings differently from how Spring binds them, the contract may be syntactically valid yet behaviorally incompatible.

## 12. Checking Request Bodies, Responses, and Media Types

An endpoint must clearly describe request contents and responses.

For request bodies, verify:

- Is `requestBody.required` accurate?
- Do media types match what the controller consumes?
- Does the schema have accurate fields, `required`, `nullable`, and constraints?
- Does `multipart/form-data` describe each part accurately?
- Do file uploads use a schema and encoding compatible with the OpenAPI version?

For responses, verify:

- Are success responses documented?
- Are important error codes such as 400, 401, 403, 404, 409, or 500 published as needed?
- Do response schemas match public DTOs?
- Do 204 responses avoid declaring a content body?
- Do media types and headers match runtime?

If a generator only sees a 200 response while the backend also returns structured errors, the client SDK may lack useful error types. Document error responses with `@ApiResponse` or an appropriate OpenAPI customization mechanism.

## 13. Checking Security and Servers

Client SDKs need to know where endpoints live and how to authenticate.

Check `servers`:

~~~yaml
servers:
  - url: https://api.example.com/v1
    description: Production API
~~~

Never leave `localhost` or staging URLs in specs released to production partners. If there are multiple servers, verify whether the generator and client pick the expected default server.

Check `securitySchemes` and `security` requirements. Example bearer token:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT

security:
  - bearerAuth: []
~~~

If only some operations require authentication, declare `security` at the operation level rather than root. Verify that the generated documentation matches actual Spring Security and gateway behavior. OpenAPI `security` documents how credentials are sent; it does not configure server-side authorization.

## 14. Test-Running the Chosen Generator

Once the spec passes validation, test generating a client with the exact generator and version the team will use.

List supported generators:

~~~bash
openapi-generator-cli list
~~~

Inspect generator options:

~~~bash
openapi-generator-cli config-help -g java
~~~

Generate a Java client from the spec:

~~~bash
openapi-generator-cli generate \
  -i openapi.json \
  -g java \
  -o ./build/generated-client
~~~

You can test generators for TypeScript, Kotlin, Swift, or other languages depending on client teams. Configuration must be finalized per generator—such as HTTP client library, date representation, enums, nullability, package names, and async types.

Do not use flags that skip validation to hide spec errors. If a generator does not support an OpenAPI feature, decide whether to adjust the schema, pick another generator, or document the compatibility limit. After generating code, compile the resulting project and inspect key operations, models, and auth configuration.

## 15. Pinning Generator Versions and Configuration

The same spec can produce different code when generator versions or config options change. For repeatable builds:

- Pin the OpenAPI Generator CLI or Maven/Gradle plugin version.
- Store config files and custom templates in the repository.
- Record the `generatorName` and target language.
- Record config options affecting data types and HTTP libraries.
- Avoid `latest` tags or floating versions in pipelines.
- Upgrade generators intentionally and review diffs of generated code.

Example command configuration:

~~~bash
openapi-generator-cli generate \
  -i openapi.json \
  -g java \
  -o ./build/generated-client \
  --additional-properties=dateLibrary=java8
~~~

Specific options vary by generator and version. Before using them, check:

~~~bash
openapi-generator-cli config-help -g java
~~~

If the team uses the Maven plugin, declare a fixed version in `pom.xml` and store `configOptions` alongside `inputSpec`. Do not rely on implicit versions on developer machines because local and CI results can diverge.

## 16. Compiling and Testing the Generated Client

Successful code generation only proves the generator wrote files. It does not prove the client compiles or calls the API properly.

Verify:

1. The generated client project builds cleanly.
2. Key models are generated with expected data types.
3. Enums and nullability are represented appropriately.
4. Operation methods have stable, non-colliding names.
5. The client sends the right path, query, headers, and request body.
6. Authentication is attached properly to requests.
7. Response bodies deserialize into the right DTOs.
8. HTTP errors can be read and handled per the contract.
9. Integration tests can call a test server or mock server matching the spec.

Write smoke tests for a critical flow such as creating an order, querying an order, and handling a 400 error response. For APIs with many operations, prioritize representative flows and complex schemas like `oneOf`, generic wrappers, date-time, and file uploads.

If a client generator produces compilable code that serializes requests wrongly, compare the actual request on the wire against OpenAPI parameter serialization and media types. This is behavioral verification, not just Java type checking.

## 17. Diffing Specs Between Releases

Before releasing a new API, diff the new spec against the published one. Diffing reveals changes that can break clients:

- Deleting a path or HTTP method.
- Changing an `operationId`.
- Removing or renaming a property.
- Turning an optional field into required.
- Narrowing an enum or data bounds.
- Changing a data type or format.
- Changing request body media types.
- Removing response codes or altering response schemas.
- Changing security requirements.
- Changing server URLs or path prefixes.

Not every schema change is a breaking change. Adding an optional response field is usually less risky than adding a required request field. However, client generators and target languages can behave differently, so evaluate according to your team's compatibility policy.

Archive released specs or commit snapshots in the repository. When changing controllers or DTOs, generate a new spec and run a diff/compatibility tool. If there is a breaking change, bump the API version or provide a clear migration plan.

## 18. Integrating the Workflow into CI

A basic pipeline can execute in this order:

~~~mermaid
flowchart TD
    A["Start test application"] --> B["Download /v3/api-docs"]
    B --> C["Validate OpenAPI"]
    C --> D["Lint against team conventions"]
    D --> E["Diff against released spec"]
    E --> F["Generate client with pinned generator"]
    F --> G["Build client"]
    G --> H["Run contract smoke tests"]
    H --> I["Archive spec and reports"]
~~~

Example pipeline commands:

~~~bash
curl -fsS "$API_BASE_URL/v3/api-docs" -o openapi.json
openapi-generator-cli validate -i openapi.json
npx @stoplight/spectral-cli lint openapi.json --ruleset .spectral.yaml
openapi-generator-cli generate -i openapi.json -g java -o build/generated-client
~~~

After generation, the pipeline must run the client's build. Depending on the project, you can publish the generated client as an artifact or use it solely for compatibility verification.

If the spec is fetched from a running application, make sure the test application is ready before running `curl`. Do not generate specs from a server with randomized data or settings that change across builds. Use stable profiles and fixtures.

## 19. Common Pitfalls During Client Generation

| Symptom | Cause to check |
|---|---|
| Validator rejects spec | Malformed structure, invalid `$ref`, or invalid OpenAPI syntax |
| Generator fails to understand 3.1 schema | Generator or version in use does not yet fully support emitted features |
| Duplicate client methods | Missing or duplicate `operationId` |
| Nullable emitted as non-null type | `required`/`nullable` in spec or generator mapping mismatch |
| Response enum breaks older clients | Server added a new enum value while client uses a closed enum |
| `allOf` creates awkward models | Generator interprets composition differently than expected |
| `oneOf` fails to deserialize properly | Missing discriminator or indistinguishable branches |
| Date/time has wrong timezone | Unclear format or timezone convention |
| Query array sent in wrong format | `style`/`explode` mismatch with backend binding |
| Client calls wrong host | `servers` has wrong URL or default server |
| Client omits bearer token | `securitySchemes`/`security` requirement missing or misconfigured |
| Client build fails after updating spec | Schema, `operationId`, or generator config change altered generated code |

When errors occur, identify which layer caused them: invalid spec, unsupported generator feature, misconfigured generator, uncompilable generated code, or incompatible runtime request. Proper triage fixes the root cause instead of manually editing generated files.

## 20. Pre-Release Checklist for Client Specs

- [ ] Exported spec from the right profile and API group.
- [ ] `openapi`, `info`, `paths`, `servers`, and `components` are valid.
- [ ] OpenAPI validator passed.
- [ ] Linter reports zero errors under mandatory conventions.
- [ ] `operationId` values are complete, unique, and stable.
- [ ] Schemas have accurate `type`, `format`, `required`, `nullable`, and `enum`.
- [ ] All `$ref` entries point to valid components.
- [ ] `allOf`/`oneOf`/`anyOf` and `discriminator` are supported by the generator.
- [ ] Parameter serialization matches how Spring MVC binds requests.
- [ ] Request bodies, responses, media types, and error codes are documented accurately.
- [ ] Security schemes and `servers` match the consumer environment.
- [ ] Generator and config versions are pinned.
- [ ] Client generated and compiled cleanly.
- [ ] Smoke tests cover critical flows and schemas.
- [ ] New spec diffed against the previous release.
- [ ] Spec artifact and verification reports archived for traceability.

## 21. References

- [springdoc-openapi – official documentation](https://springdoc.org/)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
- [OpenAPI Generator – Usage](https://openapi-generator.tech/docs/usage/)
- [OpenAPI Generator – Validators](https://openapi-generator.tech/docs/usage/#validate)
- [OpenAPI Generator – Configuration](https://openapi-generator.tech/docs/configuration/)
- [Spectral – OpenAPI linting](https://docs.stoplight.io/docs/spectral/)
- [Swagger – OpenAPI Specification overview](https://swagger.io/specification/)

The spec generated by springdoc-openapi serves as input to API-consuming tools. Before handing it to a client generator, validate its structure, review schemas and `operationId` values, test-generate code using the exact generator version, and then compile and test real requests. This workflow catches mismatches between documentation and the running API early.
