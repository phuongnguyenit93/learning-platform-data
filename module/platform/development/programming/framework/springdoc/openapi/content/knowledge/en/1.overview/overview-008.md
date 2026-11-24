# Where API Documentation Fits in Development, Testing, and Integration

API documentation is not just a Swagger UI page opened after controllers are finished. In a product with multiple services and development teams, API documentation is the medium for aligning on how a capability is published, how consumers use it, how behavior is verified, and how changes are managed across releases.

With Spring Boot and springdoc-openapi, an OpenAPI document can be generated from the application's controllers, DTOs, annotations, and configuration. That document becomes an artifact that can be reviewed, validated, diffed, distributed, and used in testing. Swagger UI is one presentation of that artifact; it is neither the contract itself nor the API runtime.

This lesson places API documentation across the entire software lifecycle:

1. **Design**: align on operations, requests, responses, errors, security, and compatibility rules.
2. **Implementation**: turn design into controllers, DTOs, validation, and the OpenAPI document.
3. **Testing**: verify the document against real requests/responses, detecting drift and breaking changes.
4. **Integration**: help consumers discover APIs, generate clients, configure authentication, and handle errors.
5. **Release, operations, and governance**: version, distribute, secure, monitor, and deprecate older contracts.

## 1. Where Does API Documentation Sit in the Architecture?

An API has at least three components to distinguish:

| Component | Role | Example |
|---|---|---|
| API runtime | Executes requests and returns responses over HTTP | Spring MVC controller at `/api/products`. |
| API contract | Describes operations and exchange rules consumers can rely on | OpenAPI JSON/YAML at `/v3/api-docs`. |
| API documentation UI | Presents the contract for humans to explore and try requests | Swagger UI at `/swagger-ui.html`. |

Other related artifacts include source code, test suites, generated clients, API catalogs, gateway configurations, and release artifacts. They may stem from the same contract, yet should not be treated as the same thing.

~~~mermaid
flowchart LR
    A[API design and decisions] --> B[OpenAPI contract]
    B --> C[Spring Boot implementation]
    C --> D[Runtime HTTP behavior]
    C --> E[springdoc-generated OpenAPI]
    E --> F[Swagger UI / API portal]
    E --> G[Contract validation and diff]
    B --> H[Client SDK generation]
    G --> I[CI release gate]
    H --> J[Consumer integration]
    F --> J
    D --> J
~~~

In a code-first model, source code and annotations typically serve as inputs for springdoc to generate the contract. In a design-first model, OpenAPI is reviewed first and the implementation must satisfy the approved contract. Either way, teams must clearly specify which artifact is the authoritative source of the contract at review and release time.

## 2. Why Is API Documentation Needed Across the Entire Lifecycle?

Without a maintained contract, each team ends up guessing:

- Frontend guesses which fields are required and which enum values are valid.
- Mobile teams assume date-time formats or pagination schemes.
- Service consumers guess error responses and retry behavior.
- QA writes tests around incidental implementation rather than agreed behavior.
- Operations does not know which endpoints require credentials, scopes, or which server URLs apply.
- Development teams modify DTOs without realizing existing clients will break.

API documentation clarifies expectations before consumers integrate. It does not replace cross-team communication, yet establishes a shared artifact where decisions can be verified and reused.

### 2.1. Benefits by Role

| Role | How API Documentation Is Used |
|---|---|
| Product owner / analyst | Reviews capabilities, inputs/outputs, and error behavior at the business level. |
| API designer / architect | Standardizes paths, methods, schemas, security, versions, and conventions. |
| Backend developer | Implements controllers, DTOs, validation, and verifies generated OpenAPI. |
| Frontend / mobile developer | Understands requests, responses, enums, pagination, errors, and authentication to integrate. |
| QA / test engineer | Builds test cases, fixtures, and contract tests from operations/schemas. |
| DevOps / platform engineer | Validates artifacts, publishes specs, configures gateways, and controls releases. |
| Security engineer | Reviews authentication schemes, scopes, sensitive data, and documentation access permissions. |
| Consumer team | Discovers APIs, generates clients, and checks compatibility before upgrading versions. |

A solid contract reduces repetitive questions like "can this field be null?", "what schema does 404 return?", or "which scope does the token need?". When answers change, those changes can be reviewed in the same development flow.

## 3. API Documentation in Discovery and Design

Documentation should start from consumer needs, not from a list of Java methods. Before implementing, teams should determine:

1. Who are the consumers: browsers, mobile apps, partners, internal services, or administrators?
2. Which capabilities are provided and where are the service's responsibility boundaries?
3. Which resources and operations are needed?
4. How are request parameters, headers, and bodies passed?
5. What structures do success and error responses have?
6. What authentication, authorization, and scopes are required?
7. How are pagination, filtering, sorting, idempotency, and concurrency handled?
8. Which changes count as breaking changes?

For example, instead of writing only "API to create products", the contract should specify method, path, body, status, and schema:

~~~yaml
paths:
  /api/products:
    post:
      operationId: createProduct
      summary: Create product
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/CreateProductRequest"
      responses:
        "201":
          description: Product created
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ProductResponse"
        "400":
          description: Invalid request
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/ApiProblem"
~~~

A contract at design time lets consumers review early before the backend is finished. Issues such as missing fields, confusing enum names, inconsistent error responses, or overly broad scopes can be fixed before creating dependencies across multiple clients.

### 3.1. Design-First vs. Code-First

| Approach | Workflow | Strengths | Risks to Manage |
|---|---|---|---|
| Design-first | Review OpenAPI first, then implement and verify implementation against the contract | Consumers can integrate early; contract is reviewed independently of code | Contract and code can drift without automated testing. |
| Code-first | Write controllers/DTOs/annotations then generate OpenAPI via springdoc | Docs stay close to implementation; fits existing Spring Boot projects | Annotations may under-express business intent or code edits may unintentionally alter the contract. |
| Hybrid | Draft and review contract, implement code, then compare generated document against baseline | Combines early review with runtime verification | Must clearly define source of truth and diff handling workflow. |

Neither approach guarantees an accurate contract on its own. Design-first requires verifying the implementation; code-first requires reviewing generated docs as a release artifact.

## 4. API Documentation During Implementation

When implementing Spring Boot, controllers, DTOs, validation, and serialization configuration create actual HTTP behavior. Springdoc reads information from the application to build the OpenAPI document.

Example:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
class ProductController {

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(
            operationId = "createProduct",
            summary = "Create product",
            description = "Creates a new product in the catalog."
    )
    @ApiResponse(
            responseCode = "201",
            description = "Product created",
            content = @Content(
                    schema = @Schema(implementation = ProductResponse.class)
            )
    )
    ProductResponse create(@Valid @RequestBody CreateProductRequest request) {
        return new ProductResponse("p-100", request.name(), request.price());
    }
}

record CreateProductRequest(
        @NotBlank String name,
        @Positive long price
) {}

record ProductResponse(String id, String name, long price) {}
~~~

The snippet illustrates how controllers and annotations contribute to the OpenAPI document. In a real application, handle business logic, persistence, exceptions, authorization, and proper DTO mapping. Annotations describe the contract, yet do not replace request validation logic or response tests.

### 4.1. Contents That Should Be Reflected in the Contract

| Content | Description Method or Information Source |
|---|---|
| Path and HTTP method | Spring MVC/WebFlux mappings and operation metadata. |
| Path/query/header parameters | `@PathVariable`, `@RequestParam`, `@RequestHeader`, `@Parameter`. |
| Request body | DTOs, `@RequestBody`, `@Schema`, OpenAPI request-body annotations. |
| Field constraints | Bean Validation such as `@NotNull`, `@NotBlank`, `@Size`, `@Min`, `@Max`. |
| Response schemas | Response DTOs and `@ApiResponse`, `@Schema`. |
| Error responses | Exception handlers, `ProblemDetail`, or error DTOs with response annotations. |
| Security | Spring Security runtime and OpenAPI security schemes/requirements. |
| Examples | `@ExampleObject`, schema examples, or OpenAPI customizers. |
| Servers and version | `OpenAPI` bean, configuration, or release process. |

### 4.2. A Contract Is More Than Method Names

An operation can have the right method and path yet still be hard to integrate if missing:

- A stable `operationId` so SDK generators produce friendly method names.
- Summary and description explaining purpose, preconditions, and side effects.
- Required/nullable, formats, enums, and data bounds.
- Content-Type, Accept, and response media types.
- Status codes and error schemas.
- Security requirements and scopes.
- Pagination, filtering, and empty-result semantics.

Never put secrets, real sample tokens, personal data, or production details in descriptions/examples. Examples should use synthetic, representative, non-misleading data.

## 5. How Does Springdoc Generate Artifacts from an Application?

With the appropriate starter for Spring MVC or WebFlux, Springdoc typically provides:

| Default Endpoint | Result |
|---|---|
| `/v3/api-docs` | OpenAPI JSON. |
| `/v3/api-docs.yaml` | OpenAPI YAML. |
| `/v3/api-docs/{group}` | OpenAPI document for the named group. |
| `/swagger-ui.html` | Swagger UI page. |
| `/v3/api-docs/swagger-config` | Configuration loaded by Swagger UI to discover documents and UI options. |

JSON/YAML can be downloaded using:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs \
  -o build/openapi.json

curl -fsS http://localhost:8080/v3/api-docs.yaml \
  -o build/openapi.yaml
~~~

If the application uses a context path, reverse proxy, or custom `springdoc.api-docs.path`, adjust URLs to match the actual deployment.

### 5.1. OpenAPI Document vs. Swagger UI Are Not the Same

- OpenAPI JSON/YAML is the contract artifact that can be stored, validated, diffed, and consumed by tooling.
- Swagger UI is the interface that reads the OpenAPI document.
- Swagger UI config is the JSON telling the UI which documents to load and which options to apply.
- The API runtime is the server executing HTTP requests.

Hiding Swagger UI does not stop the API from running. Disabling the OpenAPI endpoint does not protect controllers. Showing only one URL in a dropdown does not delete other documents. Access permissions must be enforced with Spring Security, a gateway, or network policies.

## 6. API Documentation in Testing

Documentation is only useful if it reflects actual behavior. Testing should verify both directions:

1. **Contract → implementation**: do runtime requests/responses conform to the approved OpenAPI?
2. **Implementation → contract**: do code changes alter the generated document unexpectedly?

Testing levels:

| Test Type | Goal | Example |
|---|---|---|
| Unit test | Business logic in services/controllers | Pricing, order status, business permissions. |
| MVC/WebFlux integration test | Requests flow through framework and serialize to HTTP responses | MockMvc or WebTestClient. |
| OpenAPI conformance test | Requests/responses match operations and schemas in the document | OpenAPI Request Validator. |
| Consumer-driven contract test | Provider satisfies expectations of specific consumers | Pact or Spring Cloud Contract. |
| End-to-end test | Behavior across gateways, networks, identity providers, and dependent services | Calling a deployed integration environment. |

Test types complement each other. Unit tests do not verify Content-Type; OpenAPI conformance tests do not prove business authorization is correct; end-to-end tests should not be the only way to check hundreds of schemas because they are slow and hard to diagnose.

### 6.1. Verifying the Generated Document

You can use MockMvc to confirm key operations and schemas still appear:

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
class OpenApiDocumentTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publishesCreateProductOperation() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.openapi").exists())
                .andExpect(jsonPath("$.paths['/api/products'].post").exists())
                .andExpect(jsonPath(
                        "$.paths['/api/products'].post.operationId"
                ).value("createProduct"));
    }
}
~~~

This test proves the document contains the expected operation; it does not yet prove real requests are handled properly. Separate controller/runtime tests are needed.

### 6.2. Verifying Runtime Responses Against the Contract

Example using MockMvc:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProductHttpTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void createsProductWithJsonResponse() throws Exception {
        mockMvc.perform(post("/api/products")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "name": "Mechanical Keyboard",
                                  "price": 790000
                                }
                                """))
                .andExpect(status().isCreated())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON
                ));
    }
}
~~~

The test above verifies status and media type. To prove the response body conforms to the OpenAPI schema, add JSON assertions or use an OpenAPI validator adapter. A test should not only assert `status().isOk()` and conclude the contract is verified.

### 6.3. Error Testing Is Contract Testing Too

Consumers need to know how to handle cases like:

- `400 Bad Request`: invalid body or parameter.
- `401 Unauthorized`: unauthenticated.
- `403 Forbidden`: insufficient permissions.
- `404 Not Found`: resource does not exist.
- `409 Conflict`: state or version conflict.
- `415 Unsupported Media Type`: request uses an unsupported media type.
- `429 Too Many Requests`: rate limited if the API enforces rate limits.
- `5xx`: server error; public responses must not leak stack traces or secrets.

OpenAPI should describe meaningful responses, content types, and error schemas. Tests must verify that exception handlers actually return the expected status/body. Do not document an error response in docs and let runtime return HTML or a different JSON shape.

## 7. API Documentation and Consumer Integration

When consumers integrate, documentation acts as a structured guide:

1. Discover base URLs and operations.
2. Determine HTTP methods, paths, and parameters.
3. Build request bodies according to schemas.
4. Prepare tokens, API keys, or credentials.
5. Send requests with proper Content-Type/Accept headers.
6. Parse responses into matching models.
7. Handle status codes and error schemas.
8. Implement pagination, retries, or idempotency per published rules.

### 7.1. Generated Clients

The OpenAPI document can serve as input for client generators. SDKs reduce hand-writing models, serialization, and HTTP requests, yet do not eliminate reviews:

- Are `operationId` names stable and intuitive?
- Can schemas be represented in the target language?
- Are nullables, unions, enums, and polymorphism supported by the generator?
- Do security schemes map properly to the consumer's token acquisition flow?
- Do error responses carry enough information for clients to handle?

Do not change `operationId` or schema names arbitrarily when multiple consumers depend on generated SDKs. A seemingly minor change in the document can break public client method or model names.

### 7.2. Mock Servers and Parallel Integration

Consumers can use a mock server built from the OpenAPI contract to develop before the provider finishes. This lets frontend and backend work in parallel, provided the mock reflects a reviewed contract.

Mocks do not prove the provider runtime meets the contract. Once the provider is ready, run contract tests or integration tests against real responses to avoid consumers integrating against mock behavior that does not exist on the server.

### 7.3. Documentation Does Not Replace Integration Processes

An OpenAPI document cannot fully explain on its own:

- How to register clients and obtain credentials.
- Scope approval or permission provisioning workflows.
- Rate limits, quotas, and support escalation if not described.
- SLAs, maintenance windows, or deprecation policies.
- Webhook delivery/retry handling and callback verification.
- Business data conditions or multi-step workflows.

These belong in developer portals, onboarding guides, or operational documentation linked from OpenAPI. Do not cram every process into operation descriptions.

## 8. API Documentation in CI/CD and Releases

The OpenAPI document should be treated as a build artifact:

~~~mermaid
flowchart TD
    A[Commit controller DTO annotations] --> B[Build application]
    B --> C[Start test context]
    C --> D[Export OpenAPI JSON/YAML]
    D --> E[Validate syntax and references]
    E --> F[Lint conventions]
    F --> G[Diff against released baseline]
    G --> H[Run contract and integration tests]
    H --> I[Review and approve changes]
    I --> J[Publish versioned API artifact]
    J --> K[Update API catalog / consumer SDK]
~~~

A pipeline can perform:

1. Build the exact application artifact.
2. Start the application with a test profile and deterministic data.
3. Fetch `/v3/api-docs` or each group document.
4. Validate OpenAPI version, syntax, and `$ref`s.
5. Lint naming, operationId, descriptions, security, and conventions.
6. Compare against the previous release's baseline to detect breaking changes.
7. Run contract tests and integration tests.
8. Store JSON/YAML, validation reports, and dependency/version metadata.
9. Publish artifacts only after required gates pass and changes are reviewed.

Never pick up stale files left in the build folder when export fails. The pipeline must check HTTP status, content type, non-empty file size, and artifact timestamp.

### 8.1. Versioning the Contract

Distinguish:

- The API version, typically expressed via `info.version` or endpoint versioning policy.
- The OpenAPI Specification version, located in the `openapi` field.
- The springdoc-openapi dependency version.
- The version of client SDKs generated from the contract.

These versions do not stay synchronized automatically. Release processes must record the relationship between the API artifact, provider application, and generated SDKs.

### 8.2. Reviewing Breaking Changes

Changes that can break older consumers:

- Deleting a path or HTTP method.
- Changing path parameter or query/header parameter names.
- Adding a required request field.
- Changing field types, enum values, or formats.
- Removing a response field clients rely on.
- Changing status codes or media types.
- Changing security requirements or scopes.
- Changing server URLs, path prefixes, or `operationId`s affecting SDKs.

Not all schema changes carry the same compatibility impact. For example, adding an optional response field is usually less risky than adding a required request field, yet consumers using strict deserialization can still be affected. Consider how clients actually parse data.

## 9. Distributing Documentation Across Multiple Groups and Environments

Springdoc can generate multiple OpenAPI documents via `GroupedOpenApi`. Swagger UI can list those documents using `springdoc.swagger-ui.urls`.

Example:

~~~java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/public/**")
            .build();
}

@Bean
GroupedOpenApi internalApi() {
    return GroupedOpenApi.builder()
            .group("internal")
            .pathsToMatch("/api/internal/**")
            .build();
}
~~~

The corresponding URLs are usually `/v3/api-docs/public` and `/v3/api-docs/internal`. An internal UI can list both; a public portal should only show public documents.

### 9.1. Splitting Documentation by Audience Is Not a Security Measure

Group filters only decide which operations appear in a document. They do not protect documentation URLs or controllers on their own.

- Protect `/v3/api-docs/internal` with proper authorization.
- Protect `/v3/api-docs/swagger-config` and Swagger UI if the portal is internal.
- Enforce permissions to call `/api/internal/**` in Spring Security or a gateway.
- Never include credentials or sensitive data in examples.
- Check both JSON and YAML endpoints if both are exposed.

Hiding a group from a dropdown does not stop users from fetching the OpenAPI URL directly. Protect at the server/network boundary.

### 9.2. Distinguishing Documentation URLs from Server URLs

`springdoc.swagger-ui.urls[].url` is the URL of the OpenAPI document loaded by the UI. `servers[].url` inside OpenAPI is the base URL of the runtime API called by consumers. Both URLs serve different purposes.

If the document is loaded from `/docs/openapi.json` while the runtime API lives at `https://api.example.com/v1`, the contract must declare the right server URL. When running behind a reverse proxy, check forwarded headers and public base paths so `servers` does not point to an internal hostname.

## 10. API Documentation in Operations and Governance

After release, documentation still needs ongoing management:

- Store artifacts by release and keep baselines for diffing.
- Assign owners for each API/group.
- Record lifecycle states: experimental, active, deprecated, or retired per policy.
- Publish deprecation schedules and replacement versions.
- Ensure API catalogs point to the artifact matching the right environment and release.
- Track remaining consumers on older versions before retiring support.
- Retain release notes and contract decisions for incident investigation.

Runtime documentation can shift when deployments change configuration or dependencies. Therefore, store approved artifacts alongside releases rather than relying solely on a live environment's `/v3/api-docs` endpoint.

### 10.1. Documentation and Observability

OpenAPI shows which operations are published; logs, metrics, and traces show which operations are actually used and how they perform. You can link:

- `operationId` with route metrics or tracing spans.
- API versions with error and latency dashboards.
- Deprecation notices with consumer usage.
- Error schemas with log correlation IDs and support workflows.

Never log tokens, passwords, or sensitive request/response bodies just to make docs/traces easier to inspect. API documentation and observability must follow the same data protection policy.

## 11. Choosing the Right Level of Documentation

Not every endpoint needs a lengthy description. The required detail depends on complexity and target consumers.

| API Type | Minimum Documentation Recommended |
|---|---|
| Simple internal CRUD API | Summary, parameters, request/response schemas, statuses, and security. |
| Public partner API | Business descriptions, examples, errors, auth, pagination, rate limits, and version policy. |
| Financial or transactional API | Precision, idempotency, state transitions, concurrency, error semantics, and audit requirements. |
| Webhook | Event schemas, signature verification, retries, ordering, duplicate delivery, and acknowledgements. |
| File upload/download | Media types, size limits, binary responses, filenames, and error handling. |
| Async API | Message/event schemas, delivery guarantees, correlation, and retry semantics. |

A concise yet accurate contract is better than a long page full of claims not enforced by runtime.

## 12. Common Misconceptions

- **"Swagger UI is the API documentation"**: the UI only renders an OpenAPI document; the JSON/YAML artifact is the structured contract.
- **"Generating OpenAPI means the contract is right"**: the document may miss error responses, security, constraints, or describe runtime behavior inaccurately.
- **"Annotations replace tests"**: annotations do not prove serialization and real HTTP responses match schemas.
- **"Docs are only for frontend"**: QA, service consumers, platform, security, and operations all use the contract.
- **"Code-first always keeps docs accurate"**: code edits can drift the contract or introduce unintended breaking changes.
- **"Design-first needs no runtime verification"**: implementations can still diverge from the approved OpenAPI spec.
- **"Hiding Swagger UI equals security"**: JSON/YAML endpoints and the API runtime can still be accessed directly.
- **"OpenAPI is the entire developer portal"**: onboarding, credentials, SLAs, quotas, and support processes require supplementary content.
- **"Publishing once is enough"**: contracts need versioning, deprecation, ownership, and baselines.
- **"Every schema change is breaking"**: analyze semantics and how consumers parse data rather than looking only at text diffs.
- **"A mock server proves the provider is correct"**: mocks only simulate the contract; test provider runtime separately.
- **"The API docs endpoint is an immutable release artifact"**: runtime configs and dependencies can change output; store reviewed snapshots per release.

## 13. Recommended Workflow

1. **Discover consumers and capabilities**: identify who calls the API and what business problem it solves.
2. **Design the contract**: align on paths, methods, parameters, schemas, errors, security, and versioning.
3. **Review the contract**: check clarity, consistency, and consumer compatibility.
4. **Implement Spring Boot**: write controllers, DTOs, validation, serialization, and authorization.
5. **Generate OpenAPI via springdoc**: export JSON/YAML and group documents if needed.
6. **Compare implementation against contract**: detect missing operations, wrong fields, or undocumented responses.
7. **Test**: run unit, MVC/WebFlux, OpenAPI conformance, consumer contract, and E2E tests at appropriate boundaries.
8. **Integrate consumers**: provide artifacts, examples, auth guides, and client SDKs if needed.
9. **CI gates and release**: validate, lint, diff baselines, review breaking changes, and publish artifacts.
10. **Post-release governance**: monitor consumers, deprecations, version lifecycles, and update docs.

## 14. Checklist for Evaluating Integration-Ready API Documentation

- [ ] Consumers and operation goals are clearly identified.
- [ ] Summary, description, and stable operationId are present.
- [ ] Paths, methods, and parameters match HTTP runtime behavior.
- [ ] Request bodies have clear media types and schemas.
- [ ] Required, nullable, enums, formats, and validation constraints are accurately described.
- [ ] Success responses have status codes, content types, and schemas.
- [ ] Key error responses have status codes and error schemas.
- [ ] Security schemes and operation requirements align with runtime.
- [ ] Examples use synthetic data and contain no secrets.
- [ ] OpenAPI JSON/YAML is validated and stored as an artifact.
- [ ] Contract is diffed against baseline before release.
- [ ] Document tests and real HTTP behavior tests exist.
- [ ] Consumers can understand how to authenticate, call APIs, and handle errors.
- [ ] Documentation is distributed to the right audiences and protected appropriately.
- [ ] Owner, version, deprecation, and release policies are defined.

## 15. References

- [springdoc-openapi – Getting Started](https://springdoc.org/getting-started.html)
- [springdoc-openapi – Configuration properties](https://springdoc.org/properties.html)
- [springdoc-openapi – FAQ and multiple OpenAPI definitions](https://springdoc.org/faq.html)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
- [Swagger UI – Usage and configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)
- [Spring Boot – Testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
- [Spring Security – Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html)
- [Pact – Consumer-driven contract testing](https://docs.pact.io/)
- [Spring Cloud Contract – Reference documentation](https://docs.spring.io/spring-cloud-contract/reference/)

API documentation is an artifact spanning the software lifecycle: it aligns design, guides implementation, anchors testing, supports consumer integration, and feeds release/governance processes. Springdoc generates OpenAPI from Spring Boot applications; Swagger UI lets humans explore docs; CI and contract tests verify docs against runtime behavior. When contracts are intentionally reviewed, versioned, tested, and distributed, they become a reliable coordination point between providers and consumers rather than just a UI page added after coding ends.
