# Mapping Operations to Tools and Clear Metadata Requirements

OpenAPI describes the operations an API provides. An integration system can convert a subset of those operations into tools so that another application, agent, or orchestration platform can invoke them through a structured interface. However, an HTTP operation does not automatically become a safe and easy-to-use tool. You must select appropriate operations, define inputs/outputs, preserve parameter semantics, add clear metadata, and enforce server-side authentication and authorization policies.

springdoc-openapi helps generate an OpenAPI document from Spring Boot controllers and annotations. That document can serve as an input source for adapters that generate tool definitions, MCP servers, or function-calling integrations. springdoc does not automatically turn every endpoint into a tool, nor does it decide which operations are allowed to execute. The mapping requires an integration layer with its own rules.

This article covers selecting operations, normalizing tool names and descriptions, mapping request/response schemas, declaring extension metadata, preserving security context, handling side effects, and testing the tool contract generated from OpenAPI.

## 1. HTTP Operations and Tools Have Different Purposes

An OpenAPI Operation Object describes an HTTP action at a path, such as `GET /api/orders/{id}`. A tool definition describes an action with a name, purpose, input schema, and sometimes an output schema so another system can select and invoke it.

The two concepts are related but not identical:

| OpenAPI Operation | Tool Definition |
|---|---|
| Identified by path and HTTP method | Identified by tool name in a registry |
| Has `parameters`, `requestBody`, and `responses` | Has an input schema and a return result |
| Uses server URLs, security schemes, and HTTP semantics | Uses a tool runtime, credential context, and invocation policy |
| Has `summary`, `description`, `operationId`, `tags` | Has `name`, `description`, and metadata to aid selection |
| Describes an HTTP contract | Describes a capability a consumer can request to execute |

Example of an order-lookup operation:

~~~yaml
paths:
  /api/orders/{id}:
    get:
      operationId: getOrderById
      summary: Get order details
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Order found
~~~

An integration layer can convert that operation into a tool named `get_order_by_id` taking the order ID as input. When the tool is invoked, the adapter sends an HTTP `GET` to the corresponding endpoint and returns the result to the caller.

Do not treat this as a simple rename. The adapter must understand whether parameters belong in path, query, or header; how the request body is serialized; how credentials are supplied; and how responses/errors are represented.

## 2. Mapping Architecture from Spring Boot to the Tool Runtime

A controllable architecture separates document generation, operation selection, and HTTP execution:

~~~mermaid
flowchart TD
    A[Spring Boot controllers] --> B[springdoc-openapi]
    B --> C[OpenAPI JSON document]
    C --> D[Operation selection and policy]
    D --> E[Tool definition adapter]
    E --> F[Tool registry: MCP or function calling]
    G[Tool invocation] --> H[Input validation]
    H --> I[Authentication and authorization context]
    I --> J[HTTP client adapter]
    J --> K[Spring Boot API]
    K --> L[Response and error mapping]
    L --> M[Tool result]
~~~

Each component has a distinct responsibility:

- **Spring Boot API:** executes business logic and checks access permissions.
- **springdoc-openapi:** generates the OpenAPI document reflecting operations and schemas.
- **Operation selector:** decides which operations may be exposed as tools.
- **Tool definition adapter:** converts OpenAPI metadata and schemas into the target tool format.
- **Tool runtime:** receives invocations, validates inputs, and manages execution sessions.
- **HTTP client adapter:** builds requests with the exact path, query, headers, body, and credentials.
- **Result mapper:** translates status codes, headers, response bodies, and errors into tool results.

Never allow the tool runtime to call arbitrary URLs provided by a model. The adapter must obtain URLs and methods from operations selected in the OpenAPI document or an approved registry. This constrains destinations, methods, and action scope.

## 3. Selecting Suitable Operations to Expose as Tools

Not every endpoint is useful or safe for tool calling. Select operations based on business goals and safe execution capability.

Operations that are usually suitable:
- Looking up information by a clear identifier.
- Bounded, paginated searches.
- Reading the status of a task or resource.
- Creating a business request with a clear input schema and appropriate confirmation workflow.
- Performing a side-effecting action controlled by permissions and policies.

Operations that require careful consideration or should usually be excluded from the tool registry:
- Administrative, debug, actuator, or internal endpoints.
- Endpoints executing SQL, shell commands, URL proxies, or accessing arbitrary resources.
- Bulk deletion endpoints or irreversible operations.
- Endpoints accepting large files, continuous streams, or complex binary payloads if the tool protocol does not support them.
- Endpoints requiring browser-bound sessions/cookies that the adapter cannot manage properly.
- Endpoints with ambiguous inputs, missing limits, or insufficient descriptions for accurate selection.

A tool should represent an action with an easily understood goal. If an operation needs dozens of technical parameters and multi-step orchestration, consider building a dedicated API facade with simpler inputs instead of exposing the complex endpoint directly.

## 4. Required Metadata on Each Operation

An operation can run at HTTP level yet remain difficult to turn into a tool if metadata is missing or vague. At minimum, define:

| Metadata | Role in Tool Mapping |
|---|---|
| `operationId` | Stable identifier linking the operation and the tool |
| `summary` | Short, clear action title |
| `description` | Explains purpose, preconditions, limits, and side effects |
| `tags` | Groups operations by business domain |
| `parameters` | Defines inputs in path/query/header/cookie |
| `requestBody` | Schema and media types of the payload sent |
| `responses` | Result schemas and status codes |
| `security` | Required authentication mechanism and scopes |
| `deprecated` | Signals the operation is being phased out |
| `servers` | Base URLs and target environments |
| `examples` | Input/output examples helping consumers understand usage |
| vendor extensions | Custom metadata such as tool name, enabled flag, read-only status, or confirmation policy |

In OpenAPI, operation metadata fields belong to the Operation Object. springdoc can generate them from annotations or OpenAPI customizer configurations.

Do not use `description` as a substitute for schemas. A sentence like "id is the order ID" cannot replace a parameter with name, location, required flag, and type. Tool adapters need structured data to construct input schemas and requests.

## 5. Writing Stable and Unique operationId Values

`operationId` is a good identifier for linking an operation to a tool because it does not depend directly on the URL. Per OpenAPI, when `operationId` is provided it must be unique within the document.

Example:

~~~yaml
get:
  operationId: getOrderById
  summary: Get order details
~~~

This can be normalized into the tool name `get_order_by_id`. A tool name should:
- Be unique within the registry visible to consumers.
- Stay stable across path refactors.
- Be concise, using a verb and business object.
- Contain no environment details or secrets.
- Obey character restrictions of the target tool protocol.
- Have collision-handling rules across document groups or API versions.

If multiple services have an `operationId` of `getOrderById`, the registry can namespace by service or group, such as `orders_get_order_by_id`. If `x-tool-name` is present, follow an agreed policy; do not silently generate different names on each export.

Changing `operationId` may not alter wire requests, yet it can change function names in generated SDKs or tool registries. Treat `operationId` as stable metadata whose changes require review.

## 6. Summary and Description Must Help Pick the Right Tool

`summary` should state the action in a short phrase, usually verb + object. `description` explains usage conditions and outcomes.

Good example:

~~~yaml
operationId: cancelOrder
summary: Cancel order
description: >
  Cancels an order that has not yet been shipped. Requires orders:cancel scope.
  Cannot cancel orders already completed or handed off to a carrier.
~~~

Poor example:

~~~yaml
operationId: updateStatus
summary: Update
description: Status update API.
~~~

A clear description should answer:
- What is the tool used for?
- When should it be called?
- What do the inputs mean?
- What are the preconditions before execution?
- Does the action create, modify, or delete data?
- How is a successful result represented?
- Which cases will be rejected?
- Is user confirmation required before calling?

Avoid stuffing entire business manuals into `description`. Keep it concise yet sufficient to pick the right tool and prepare inputs. Details on data types, required flags, enums, and constraints belong in the schema.

## 7. Mapping Parameters to the Right HTTP Locations

OpenAPI distinguishes parameters by the `in` field:

- `path`: inside the URL path.
- `query`: inside the query string.
- `header`: inside HTTP headers.
- `cookie`: inside cookies.

Tool protocols usually accept a single JSON object as input. The adapter must preserve location metadata so that at execution time it constructs the right request.

One clear representation groups inputs by location:

~~~json
{
  "path": {
    "id": "order-1001"
  },
  "query": {
    "includeItems": true
  }
}
~~~

The corresponding tool schema can describe `path` and `query` as nested sub-objects. The adapter uses `path.id` to substitute placeholders and `query.includeItems` to build the query string.

Some systems flatten all fields into a single object. If choosing that approach, establish collision rules for duplicate names and maintain metadata mapping fields back to their HTTP locations. Never guess whether a field belongs in path or query from its name alone.

`path` parameters must always be supplied to build a valid URL. `required` flags on `query`/`header`/`cookie` must match OpenAPI. Defaults should only be applied when the contract and runtime share that default behavior.

## 8. Mapping requestBody and Media Types

The request body is often the largest part of a tool's input. The adapter must determine supported media types and schemas.

Example operation accepting JSON:

~~~yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        type: object
        required: [customerId]
        properties:
          customerId:
            type: string
~~~

The tool input can place the payload inside a `body` field:

~~~json
{
  "body": {
    "customerId": "customer-42",
    "items": [
      {
        "sku": "SKU-100",
        "quantity": 2
      }
    ]
  }
}
~~~

The adapter serializes `body` to JSON and sends `Content-Type: application/json`.

Cases requiring specialized adapters:
- `application/x-www-form-urlencoded`.
- `multipart/form-data` and file uploads.
- `application/octet-stream`.
- XML or custom media types.
- Streaming requests or event streams.

Do not turn every body schema into JSON and send it regardless of media type. If a tool protocol does not support a payload format, exclude the operation from the registry or provide a dedicated adapter. Never expose a tool whose contract the runtime cannot execute faithfully.

If an operation supports multiple media types, select the supported representation and document it clearly in metadata. Never pick a content type arbitrarily when representations have different semantics.

## 9. Preserving required, nullable, enum, and Constraints

When converting an OpenAPI Schema Object into a tool input schema, preserve key rules:

- `required`: fields that must be present.
- `type`: accepted JSON type.
- `enum`: allowed set of values.
- `minimum`/`maximum`: numeric bounds.
- `minLength`/`maxLength`/`pattern`: string constraints.
- `minItems`/`maxItems`/`uniqueItems`: array constraints.
- `nullable` or union with `null`: ability to accept null per OpenAPI version.
- `additionalProperties`: rules for undeclared fields.
- `oneOf`/`anyOf`/`allOf`: schema composition.

Example:

~~~yaml
CreateOrderRequest:
  type: object
  required: [customerId, items]
  properties:
    customerId:
      type: string
      minLength: 1
    items:
      type: array
      minItems: 1
      items:
        type: object
        required: [sku, quantity]
        properties:
          sku:
            type: string
          quantity:
            type: integer
            minimum: 1
~~~

A tool adapter should not strip constraints just to simplify the schema. If the target JSON Schema dialect or tool protocol supports only a subset, detect and handle it explicitly. You can reject incompatible operations, produce a verified equivalent schema, or add runtime validation; never silently widen accepted inputs.

In particular, `required` in a request schema is a provider requirement. If the adapter drops `required`, a model may send payloads missing fields and only discover errors when requests hit the server.

## 10. Do Not Turn Credentials into Model-Controlled Inputs

OpenAPI can describe security schemes such as Bearer authentication, API keys, or OAuth2. When mapping an operation into a tool, do not turn access tokens, API keys, or client secrets into input schema properties for a model to fill in.

Credentials should be supplied from a trusted context:
- User session or identity of the requesting caller.
- Token issued via the application's OAuth flow.
- Scoped service identity dedicated to the integration.
- Secret store or runtime credential provider.

The execution flow should:
1. Identify the caller's principal.
2. Obtain the matching credential from the authentication system.
3. Verify the principal is authorized to invoke the tool.
4. Send the credential through the HTTP client.
5. Let Spring Security or the API gateway re-authenticate and authorize at the provider.

Security requirements in OpenAPI tell the adapter which scheme/scopes an operation requires. They do not replace runtime authorization. The provider must still check permissions on every request, even if the tool registry already hid the operation from unauthorized users.

## 11. Describing Side Effects and Risk Levels

Tools can read data or alter state. Metadata should help the runtime and operators recognize behavior.

Example classification:

| Action | Typical HTTP | Side Effect |
|---|---|---|
| Look up order | `GET` | No intended resource mutation |
| Create order | `POST` | Creates new data |
| Update address | `PUT`/`PATCH` | Modifies data |
| Cancel order | `POST`/`DELETE` | May trigger business consequences |
| Export report | `POST` | May create a job or file |

Do not classify solely by HTTP method. A poorly implemented `GET` might still write business logs, spawn jobs, or mutate state; a `POST` might only execute a query. Inspect the actual semantics of each endpoint.

If a tool protocol supports annotations like read-only, destructive, or idempotent, map them based on verified behavior. Such annotations are hints for consumers to make decisions; they are not authorization mechanisms and do not replace user confirmation.

For side-effecting actions:
- Clearly describe consequences.
- Identify required permissions.
- Use an idempotency key if the API supports it and retries may occur.
- Specify when confirmation is needed.
- Return a resource or operation identifier to check results.
- Never auto-retry non-idempotent actions without knowing whether the previous request succeeded.

## 12. Using Vendor Extensions for Additional Tool Metadata

OpenAPI allows specification extensions starting with `x-`. You can use extensions to describe project-specific integration policies.

Example:

~~~yaml
paths:
  /api/orders/{id}:
    get:
      operationId: getOrderById
      summary: Get order details
      description: Look up a single order by ID.
      x-tool-enabled: true
      x-tool-name: get_order
      x-tool-read-only: true
      x-tool-confirmation-required: false
      x-tool-category: orders
~~~

Another extension can describe a write operation:

~~~yaml
paths:
  /api/orders/{id}/cancel:
    post:
      operationId: cancelOrder
      summary: Cancel order
      description: Cancels an order not yet handed off for shipping.
      x-tool-enabled: true
      x-tool-name: cancel_order
      x-tool-read-only: false
      x-tool-destructive: true
      x-tool-confirmation-required: true
      x-tool-category: orders
~~~

The `x-tool-*` extensions above are project-specific conventions, not standard OpenAPI fields. Define a schema or governance documentation for extensions so all services and adapters interpret them identically.

Extensions should only control tool exposure and description. They must never cause the provider to bypass security, validation, or authorization. If an extension is missing or mistyped, the adapter should fail validation or skip the operation per clear policy, rather than guessing values.

## 13. Declaring Basic Metadata with Swagger Annotations

springdoc reads `swagger-core` annotations to generate operation metadata. Example:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {
    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @Operation(
        operationId = "getOrderById",
        summary = "Get order details",
        description = "Look up an order by ID. "
            + "Requires orders:read permission. "
            + "Returns 404 if the order ID does not exist.",
        tags = {"orders"},
        responses = {
            @ApiResponse(
                responseCode = "200",
                description = "Order found"
            ),
            @ApiResponse(
                responseCode = "404",
                description = "Order not found"
            )
        }
    )
    @GetMapping("/api/orders/{id}")
    OrderResponse getOrderById(
        @Parameter(
            name = "id",
            in = ParameterIn.PATH,
            required = true,
            description = "Order ID",
            schema = @Schema(type = "string", minLength = 1)
        )
        @PathVariable String id
    ) {
        // Call service and return DTO
        return orderService.findById(id);
    }
}
~~~

The example assumes the application has the corresponding service and DTO. Annotations describe the contract; they do not automatically guarantee runtime responses match statuses or schemas. Verify the generated document and test the actual endpoint.

For write operations, describe request bodies and responses clearly:

~~~java
@Operation(
    operationId = "createOrder",
    summary = "Create order",
    description = "Creates a new order for the current customer."
)
@ApiResponse(responseCode = "201", description = "Order created")
@PostMapping("/api/orders")
ResponseEntity<OrderResponse> createOrder(
    @Valid @RequestBody CreateOrderRequest request
) {
    // ...
}
~~~

Use separate DTOs for requests and responses when they have different write/read permissions or fields. Do not expose an internal persistence entity as a public schema if it contains fields that should not leave the server.

## 14. Adding x-tool Extensions with OpenApiCustomizer

You can add extensions to the OpenAPI model using `OpenApiCustomizer`:

~~~java
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ToolMetadataConfiguration {

    @Bean
    OpenApiCustomizer toolMetadata() {
        return openApi -> {
            var paths = openApi.getPaths();
            if (paths == null) {
                return;
            }

            var orderPath = paths.get("/api/orders/{id}");
            if (orderPath == null || orderPath.getGet() == null) {
                return;
            }

            var operation = orderPath.getGet();
            operation.addExtension("x-tool-enabled", true);
            operation.addExtension("x-tool-name", "get_order");
            operation.addExtension("x-tool-read-only", true);
            operation.addExtension("x-tool-confirmation-required", false);
            operation.addExtension("x-tool-category", "orders");
        };
    }
}
~~~

The example above uses `OpenApiCustomizer` to add scalar extensions directly onto an operation. If using multiple document groups, verify which documents the customizer applies to. For metadata applied globally across groups, check `GlobalOpenApiCustomizer` or configure customizers per `GroupedOpenApi` depending on your springdoc version.

Do not rely on operation ordering in a file or map iteration order when attaching metadata. Look up by path and method, then verify `operationId`. If a path changes, the customizer may miss the operation; write tests to detect missing required extensions.

When managing many operations, use a validated configuration registry rather than scattered path/method branches. The registry can declare `operationId`, tool name, enabled flag, side-effect classification, and policy, and the customizer applies them to the OpenAPI model.

## 15. Designing an Intermediate Tool Definition from an OpenAPI Operation

An adapter can transform an operation into an intermediate structure before emitting MCP or function-calling formats.

Example intermediate structure:

~~~json
{
  "name": "get_order",
  "description": "Get details of an order by ID.",
  "source": {
    "group": "public",
    "operationId": "getOrderById",
    "method": "GET",
    "path": "/api/orders/{id}"
  },
  "inputSchema": {
    "type": "object",
    "properties": {
      "path": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string",
            "minLength": 1
          }
        },
        "required": ["id"],
        "additionalProperties": false
      }
    },
    "required": ["path"],
    "additionalProperties": false
  },
  "policy": {
    "readOnly": true,
    "confirmationRequired": false,
    "securityScopes": ["orders:read"]
  }
}
~~~

The structure above is an internal example, not a standard tool protocol. The target adapter converts it into the exact format required by the MCP server, function-calling API, or integration platform.

Keep the source mapping in the registry so the runtime knows which operation corresponds to each tool name. Never accept `method`/`path` from model-supplied input. Input contains only business values; method and path are predetermined metadata.

## 16. Mapping to MCP Tools

MCP tools typically have a name, description, and input schema. The server publishes the tool list and handles calls based on name and arguments. Some protocol versions also support output schemas and annotations.

When creating MCP tools from OpenAPI:
- Use `operationId` or `x-tool-name` as the name source.
- Use `summary`/`description` as the description.
- Convert parameters and `requestBody` into `inputSchema`.
- Convert the result schema if `outputSchema` is supported and appropriate.
- Map read-only/destructive/idempotent to annotations when justified.
- Keep authorization and credentials in the MCP server/runtime.
- Return errors using MCP's tool result structure.

Annotations such as `readOnlyHint` or `destructiveHint` are hints for clients. They do not stop the server from executing actions and cannot replace permission checks.

One MCP tool may orchestrate multiple internal API operations if it represents a cleanly designed business action. Conversely, not every OpenAPI operation must become an MCP tool. The server should expose a small, stable list suited to users.

## 17. Mapping to Function Calling

Some model platforms accept a list of function/tool definitions consisting of name, description, and JSON Schema parameters. An adapter can generate function definitions from OpenAPI operations:

~~~json
{
  "type": "function",
  "name": "get_order",
  "description": "Get details of an order by ID.",
  "parameters": {
    "type": "object",
    "properties": {
      "id": {
        "type": "string",
        "description": "Order ID"
      }
    },
    "required": ["id"],
    "additionalProperties": false
  }
}
~~~

This illustrates one style of function definition; each API/provider may require different structures and JSON Schema subsets. Do not dump a raw OpenAPI Operation Object into `parameters` and expect the model to understand it.

A tool call from a model is only a request to invoke a function. The application must still:
1. Parse arguments.
2. Validate against the schema.
3. Verify the tool is permitted in the current context.
4. Check permissions and confirmation policies.
5. Execute the adapter.
6. Return the tool result to the model per the target protocol.

If a provider supports strict schema mode, the adapter must convert schemas to the supported keyword subset and enable strict mode per the provider's documentation. Do not silently drop composition, nullability, or constraints without recording the limitation.

## 18. Mapping Responses and Errors

An OpenAPI operation may define multiple response codes and media types. The tool adapter must decide how to represent outcomes.

A simple convention:

| HTTP Response | Tool Result |
|---|---|
| `2xx` with JSON body | Return structured data matching schema |
| `204 No Content` | Return success result with no body |
| `400`/`422` | Correctable input/validation error |
| `401` | Missing or expired credentials |
| `403` | Insufficient permissions |
| `404` | Resource not found |
| `409` | State or idempotency conflict |
| `429` | Rate limit; may require retry per policy |
| `5xx` | Provider error; return safe message and correlation ID |

Do not turn every HTTP response into tool success. The adapter must distinguish success/error based on status code and the operation contract.

Never include stack traces, SQL, internal hostnames, tokens, or sensitive data in tool results. You can return stable error codes, actionable messages, status, and correlation IDs. Technical details belong in access-controlled server logs.

If an operation defines multiple success schemas, such as `200` and `202`, describe each status clearly. A `202` might only acknowledge that a job was accepted; the tool should not report business completion if the API only queued a background task.

### 18.1. Selecting Output Schema from Success Responses

When a tool protocol supports an output schema, the adapter should take the schema from the policy-selected success response, typically the operation's primary JSON response. Never use an error response schema as the success output. If an operation has multiple success responses with different shapes, you can use a union schema if supported by the protocol or return an envelope with `status` and `data` fields to preserve status clarity.

For example, an operation returning JSON on `200` and no body on `204` needs two separate result branches. For `204`, do not fabricate an empty object and claim it is the API's response body. If the tool runtime requires every result to be structured, the adapter can wrap the outcome in internal metadata such as `{status: 204, body: null}`; this is an adapter format, not the HTTP body.

## 19. Schema Limitations When Converting OpenAPI to Tool JSON Schema

OpenAPI Schema Objects and JSON Schema are related but do not always share the same dialect or keyword set. A tool protocol may only support a subset of JSON Schema.

Areas to check:
- OpenAPI 3.0 `nullable` differs from representing null in JSON Schema 2020-12.
- OpenAPI 3.1 supports more JSON Schema keywords.
- References may need to be resolved or preserved depending on the target format.
- `allOf`, `oneOf`, `anyOf`, and `discriminator` may not be fully supported by the tool runtime.
- `readOnly`/`writeOnly` are directional annotations for requests/responses.
- Formats like `date-time`, `uuid`, `binary` may be informational metadata only for some validators.
- `multipart` and binary payloads require separate transfer mechanisms.
- Recursive schemas can trouble strict tool schemas or UI renderers.

The adapter must know the OpenAPI version and dialect before converting. Maintain test fixtures for complex schemas used in your API rather than assuming every schema can be flattened safely.

If an operation has a schema that cannot be converted accurately, there are three options:
1. Do not expose that operation as a tool.
2. Write a simpler adapter/schema that preserves equivalent validation.
3. Build an API facade with a contract suited to the tool runtime.

Never silently strip constraints just to pass a validator. Doing so lets models send data the provider will reject.

## 20. Protecting the Tool Registry and HTTP Execution

The tool registry is an integration surface capable of triggering actions in the system. Controls are needed at both registration time and execution time.

Principles:
- Only load OpenAPI documents from trusted sources.
- Only permit server URLs on an allowlist.
- Never allow tool inputs to alter host, scheme, or port.
- Only permit registered HTTP methods.
- Restrict redirects to avoid routing requests to another host.
- Never forward arbitrary headers from tool input to the provider.
- Never place `Authorization`, `Cookie`, or API keys in the input schema.
- Apply timeouts, response size limits, and rate limits.
- Verify permissions on every invocation.
- Emit audit events with tool name, principal, `operationId`, and outcome.
- Never log credentials or sensitive payloads.
- Apply separate retry limits for non-idempotent operations.

An OpenAPI document may contain external references or URLs in `servers`, `callbacks`, and `links`. An adapter should never automatically fetch arbitrary URLs just because they appear in the document. Reference resolution and server calls must obey system allowlists and policies.

## 21. Testing the Operation-to-Tool Mapping Layer

Do not test only Spring Boot endpoints. Test the adapter and registry independently.

| Test Layer | What to Verify |
|---|---|
| Document test | Operations have `operationId`, summary, schemas, and security metadata |
| Selection test | Only permitted operations appear in the tool registry |
| Name test | Tool names are stable, unique, and follow conventions |
| Input mapping test | Path/query/header/body are mapped to the right locations |
| Schema test | `required`, `enum`, `nullable`, and constraints are preserved |
| Auth test | Credentials come from trusted context, not model input |
| Policy test | Read/write/destructive/confirmation flags are classified properly |
| Execution test | Method, URL, media type, and body are accurate |
| Result test | Success/error mapping matches statuses and schemas |
| Security test | Non-allowlisted URLs and forbidden operations are rejected |

A test fixture can store a known OpenAPI JSON and its expected tool definitions. When upgrading springdoc or changing annotations, run tests to catch unexpected changes in tool names, descriptions, input schemas, or extensions.

Beyond unit tests, run integration tests against real Spring Boot to confirm the docs endpoint produces expected content and the tool adapter reads the runtime-generated document. If using multiple `GroupedOpenApi` beans, test each group.

## 22. Example Inspecting Metadata in OpenAPI Output

After starting the application, fetch the document:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Use `jq` to inspect the operation and extensions:

~~~bash
jq '.paths["/api/orders/{id}"].get |
  {
    operationId,
    summary,
    description,
    toolEnabled: .["x-tool-enabled"],
    toolName: .["x-tool-name"],
    toolReadOnly: .["x-tool-read-only"]
  }' openapi.json
~~~

The output must reflect the metadata the adapter relies on. If extensions are missing, verify whether the customizer is applied to the right document group and whether the operation path/method match.

Do not inspect extensions alone. Also check `parameters`, `requestBody`, `responses`, and `security`:

~~~bash
jq '.paths["/api/orders/{id}"].get |
  {
    parameters,
    responses,
    security
  }' openapi.json
~~~

If the document output is right yet the tool registry is wrong, the bug lies in the conversion layer or policy rather than necessarily in springdoc.

## 23. Checklist Before Exposing an Operation as a Tool

- [ ] The operation has a clear business purpose.
- [ ] The operation is not an unintended internal or debug endpoint.
- [ ] `operationId` is present, unique, and stable.
- [ ] `summary` is an easily understood action name.
- [ ] `description` states conditions, limits, and side effects.
- [ ] Parameters have accurate names, locations, types, and `required` flags.
- [ ] Request body has a schema and media type supported by the adapter.
- [ ] `required`, `enum`, `nullable`, and constraints are preserved.
- [ ] Success and error responses are clearly described.
- [ ] Security schemes/scopes are mapped to policy.
- [ ] Credentials come from trusted context, not model input.
- [ ] Server URLs and HTTP methods come from a trusted registry.
- [ ] Read-only, idempotent, destructive, and confirmation flags reflect real semantics.
- [ ] Vendor extensions have a schema/convention and are validated.
- [ ] Tool name is unique within the registry.
- [ ] Tool results do not leak secrets or internal details.
- [ ] The adapter enforces timeouts, retries, rate limits, and response size caps.
- [ ] Tests cover selection, schema mapping, execution, and authorization.
- [ ] Each document group is tested individually.
- [ ] A review process exists when an OpenAPI diff changes the tool registry.

## References

- [OpenAPI Specification – Operation Object](https://spec.openapis.org/oas/latest.html#operation-object): `operationId`, `summary`, `description`, `parameters`, `requestBody`, `responses`, and extensions.
- [Swagger Annotations – Operation](https://docs.swagger.io/swagger-core/v2.2.0/apidocs/io/swagger/v3/oas/annotations/Operation.html): annotation describing operations in Java.
- [springdoc-openapi](https://springdoc.org/): generating OpenAPI documents and customizing with customizers.
- [Model Context Protocol – Tools](https://modelcontextprotocol.io/specification/latest/server/tools): tool structure, input schema, output schema, and annotations.
- [JSON Schema](https://json-schema.org/): schema model for JSON data and constraints.
- [OpenAI – Function calling](https://developers.openai.com/api/docs/guides/function-calling): defining tools/functions and handling tool calls in applications.
