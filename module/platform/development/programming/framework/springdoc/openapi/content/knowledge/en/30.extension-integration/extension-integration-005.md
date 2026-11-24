# MCP in Springdoc Branches That Provide Integration

Model Context Protocol (MCP) is a protocol that standardizes how AI applications discover and invoke capabilities exposed by a server. With springdoc-openapi's MCP integration, REST operations already described with OpenAPI can be converted into MCP tools for MCP clients or AI agents to discover and invoke. As a result, development teams can reuse controller, parameter, request body, and response metadata instead of maintaining a separate set of tool descriptions.

This integration is only available in Springdoc branches that provide MCP modules. Per current documentation, MCP was added in springdoc 3.0.3 for the Spring Boot 4 branch; the Spring Boot 3 branch using springdoc 2.x does not have the corresponding MCP starters. Starting from 3.1.1, the integration became opt-in and is disabled by default. Because MCP allows AI agents to call business APIs directly, you must choose the right version, filter exposed operations, and protect MCP endpoints with Spring Security before connecting external clients.

## 1. What Is MCP and What Problem Does It Solve?

A REST API is typically designed for applications or users to call directly over HTTP. An AI agent needs an additional descriptive layer to know:

- What actions can be performed?
- Which parameters does each action require?
- Which parameters are required and what are their data types?
- What type of data does the action return?
- Which actions are read-only and which can mutate data?

MCP provides a protocol for clients to discover and invoke tools exposed by a server. Springdoc already has operation metadata in OpenAPI, so it can convert that metadata into tool definitions:

~~~text
Spring @RestController
        |
        v
Springdoc generates OpenAPI operation
        |
        v
OpenAPI operation -> MCP ToolCallback
        |
        v
MCP Server exposes tools
        |
        v
MCP Client / AI Agent discovers and calls tool
        |
        v
Springdoc calls the corresponding REST endpoint
~~~

For example, the `GET /orders/{id}` operation with `operationId` set to `getOrderById` can become the `get_order_by_id` tool. The agent reads the description and input JSON Schema, then calls the tool with appropriate arguments. Springdoc translates that call into an HTTP request to the underlying REST endpoint and returns the result to the MCP client.

## 2. Distinguishing MCP from OpenAPI and Swagger UI

The three components are related but serve different audiences:

| Component | Purpose | Users or Systems |
|---|---|---|
| OpenAPI | Describes HTTP APIs, paths, methods, parameters, requests/responses, and security schemes | Developers, API gateways, validators, code generators |
| Swagger UI | Renders OpenAPI as a documentation UI and request tester | Developers, API integrators |
| MCP | Exposes capabilities as tools for AI clients to discover and invoke via a standard protocol | MCP clients and AI agents |

OpenAPI is the metadata source used by Springdoc's MCP integration. Swagger UI and MCP can coexist in the same application, but Swagger UI is not an MCP client and the `/v3/api-docs` endpoint is not an MCP endpoint.

The MCP specification defines multiple capability types such as tools, resources, and prompts. The Springdoc integration described in this article primarily converts REST operations into tools. It does not automatically turn every REST endpoint into an MCP resource or prompt. If the application needs standalone MCP resources or prompts, native MCP capabilities can be added with Spring AI as needed.

## 3. Identifying Springdoc Branches with MCP Support

Not every version of springdoc-openapi includes MCP:

| Springdoc Branch | Spring Boot Platform | MCP Integration |
|---|---|---|
| 1.x | Spring Boot 1/2 | No MCP module |
| 2.x | Spring Boot 3.x | No Springdoc MCP starter |
| 3.x | Spring Boot 4.x | Includes MCP modules from 3.0.3 |

Key milestones in the 3.x branch:

- 3.0.3: added Springdoc OpenAPI MCP integration.
- 3.1.1: MCP switched to opt-in; merely adding the dependency no longer registers MCP beans, endpoints, or the dashboard. This release also contains security fixes related to MCP.
- 3.2.0: added tool registration with `McpStatelessSyncServer` when using the Spring AI `STATELESS` protocol.

Current Springdoc documentation publishes version 3.2.0 for Spring Boot 4.1.x. This version is used as an illustration in the dependencies below. Check the compatibility matrix and release notes for your specific project before picking a version; do not add 3.x starters to a Spring Boot 3 application running the springdoc 2.x branch.

## 4. Springdoc MCP Modules

Springdoc splits the integration into modules:

| Module | Responsibility |
|---|---|
| `springdoc-openapi-starter-common-mcp` | Core engine, MCP configuration, tool callbacks, schema converter, customizers, annotations, dashboard controller, and frontend assets |
| `springdoc-openapi-starter-webmvc-mcp` | Spring MVC/Servlet integration, resource configurer, and servlet API version handling |
| `springdoc-openapi-starter-webflux-mcp` | Spring WebFlux integration, resource configurer, and reactive API version handling |

Typically, an application only declares the starter matching its web stack. The `common-mcp` module is pulled in as a transitive dependency; there is no need to assemble internal modules manually unless you have special requirements.

## 5. Choosing the Dependency for Spring MVC or WebFlux

For Spring MVC:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-mcp</artifactId>
    <version>3.2.0</version>
</dependency>
~~~

For Spring WebFlux:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-mcp</artifactId>
    <version>3.2.0</version>
</dependency>
~~~

Choose one starter matching the running web stack. Do not add both MVC and WebFlux just to test MCP. If the project already uses a Springdoc starter with Swagger UI or API-only, inspect the dependency tree and module combination rules in the current version's documentation to avoid pulling in two unnecessary web configurations.

The dependency only places MCP capabilities on the classpath. Starting from version 3.1.1, the integration does not enable itself automatically on application startup.

## 6. Enabling MCP Explicitly

In `application.yml`:

~~~yaml
springdoc:
  ai:
    mcp:
      enabled: true
~~~

Or in `application.properties`:

~~~properties
springdoc.ai.mcp.enabled=true
~~~

When the property is enabled, Springdoc creates the MCP integration and registers eligible REST operations as tools. If you only add the starter without enabling the property, the MCP surface remains disabled in versions 3.1.1 and later.

To disable the integration:

~~~yaml
springdoc:
  ai:
    mcp:
      enabled: false
~~~

You can use a profile to enable MCP in test or agent-integration environments:

~~~yaml
# application-agent.yml
springdoc:
  ai:
    mcp:
      enabled: true
      dashboard-enabled: true
~~~

Only activate that profile when the environment already has an appropriate security policy. Do not treat hiding the dashboard link as an MCP protection mechanism.

## 7. Configuring Endpoints, Base URL, and Startup Timeout

The main properties live under the `springdoc.ai.mcp` prefix:

| Property | Default | Meaning |
|---|---|---|
| `springdoc.ai.mcp.enabled` | `false` | Enables/disables MCP integration |
| `springdoc.ai.mcp.base-url` | `http://localhost:8080`; inferred from `server.port` if unset | Base URL used to call REST operations during tool execution |
| `springdoc.ai.mcp.init-timeout-seconds` | `30` | Time to wait for the OpenAPI spec to be ready at startup |
| `springdoc.ai.mcp.paths-to-exclude` | None | Ant patterns excluded from tool generation |
| `springdoc.ai.mcp.mcp-endpoint` | `/mcp` | Path of the MCP endpoint |
| `springdoc.ai.mcp.dashboard-enabled` | `false` | Enables the developer dashboard |
| `springdoc.ai.mcp.dashboard-path` | `/mcp-ui` | Path of the dashboard |

Configuration example:

~~~yaml
server:
  port: 8080

springdoc:
  ai:
    mcp:
      enabled: true
      base-url: http://localhost:8080
      init-timeout-seconds: 30
      mcp-endpoint: /mcp
      paths-to-exclude:
        - /internal/**
        - /admin/**
      dashboard-enabled: true
      dashboard-path: /mcp-ui
      guardrails:
        require-approval-for-mutating-tools: true
        safe-methods: GET,HEAD,OPTIONS
      audit:
        redact: true
~~~

`base-url` must point to the application hosting the REST endpoints that tools will invoke. If the application runs under a context path or behind a reverse proxy, check the full URL and how the application routes requests. A wrong base URL can allow tools to be listed while invocations fail with connection errors, 404s, or redirects.

`init-timeout-seconds` limits how long initialization waits for the OpenAPI document. If the application has many groups or heavy OpenAPI generation, inspect startup logs and spec generation time before increasing the timeout.

## 8. Springdoc Needs OpenAPI Ready at Startup

The MCP pipeline relies on OpenAPI operations to create tool definitions. Therefore, when MCP is enabled, Springdoc automatically forces `springdoc.pre-loading-enabled` to `true` via an environment post-processor so the document is preloaded early and ready for tool registration.

Initialization flow:

1. Spring Boot creates the `ApplicationContext` and beans.
2. Springdoc scans `@RestController` endpoints.
3. Springdoc generates the OpenAPI document.
4. OpenAPI operations are converted into tool callbacks.
5. The customizer chain applies names, descriptions, schemas, and exclusion rules.
6. The MCP server registers tools once the required singletons have been created.

Registering after singletons are initialized avoids certain startup deadlocks. If the application fails to generate the OpenAPI document, MCP tools cannot be fully registered either. When startup times out, investigate OpenAPI errors before adjusting the MCP timeout.

## 9. From REST Operation to MCP Tool

Springdoc scans operations described on `@RestController` classes. Each OpenAPI operation is converted into a `ToolCallback` with these parts:

- Tool name: taken from `operationId` and converted to `snake_case`.
- Description: taken from `summary`/`description`, then augmented with return type information.
- Input schema: JSON Schema generated from path parameters, query parameters, header parameters, and request body.
- Group: taken from the controller's first `@Tag`.
- Actual action: the tool callback calls the corresponding REST endpoint via the base URL.

Example:

~~~java
@RestController
@RequestMapping("/orders")
@Tag(name = "Orders", description = "Look up and manage orders")
public class OrderController {

    @GetMapping("/{id}")
    @Operation(
        operationId = "getOrderById",
        summary = "Look up an order by ID"
    )
    public OrderResponse getOrderById(@PathVariable String id) {
        return orderService.findById(id);
    }
}
~~~

Generated tool name:

~~~text
get_order_by_id
~~~

Declare stable, business-meaningful `operationId` values. Avoid letting Java method names accidentally turn into cryptic tool names or change during an internal refactor.

## 10. OpenAPI Quality Determines Tool Quality

MCP tools are generated from OpenAPI, so poor metadata produces hard-to-use tools. Each operation should have:

- A unique, stable `operationId`.
- A `summary` describing the action with a clear verb.
- A `description` stating conditions, scope, and business impact.
- Clear parameter names and descriptions.
- Accurate required markers.
- A complete request body schema with data constraints.
- A response schema representing the actual output.
- A `@Tag` matching the business domain.

Operation example:

~~~java
@PostMapping
@Operation(
    operationId = "createOrder",
    summary = "Create an order",
    description = "Creates a new order for an authenticated customer."
)
public OrderResponse createOrder(
        @Valid @RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

If the description only says "Create order" without stating conditions or effects, an agent may pick the tool in the wrong context. Descriptions should answer what the tool does, when to use it, and what data must be supplied.

## 11. How Springdoc Converts Parameters and Request Bodies

`OpenApiSchemaConverter` transforms operation metadata into JSON Schema for the tool input:

| REST Component | Representation in Tool Input |
|---|---|
| Path parameter | Property with matching type and description |
| Query parameter | Property with matching type, description, and required marker |
| Header parameter | Property corresponding to the header |
| Request body | Property named `body` containing the request schema |

REST endpoint example:

~~~java
@PostMapping("/orders/{id}/notes")
@Operation(operationId = "addOrderNote")
public OrderResponse addNote(
        @PathVariable String id,
        @RequestParam(defaultValue = "false") boolean notifyCustomer,
        @RequestBody AddOrderNoteRequest request) {
    return orderService.addNote(id, notifyCustomer, request);
}
~~~

The tool input may have a structure like:

~~~json
{
  "id": "ORD-1001",
  "notifyCustomer": false,
  "body": {
    "content": "Customer requested delivery after 5 PM"
  }
}
~~~

For multiple media types, the converter supports request bodies and prefers `application/json` when appropriate. Inspect the generated tool schema if an operation accepts `multipart/form-data`, file uploads, or multiple content types; do not assume every body format will be passed by an agent like a JSON object.

If a path template contains `{id}` without a corresponding parameter declared in OpenAPI, the converter can automatically add a required string property for the path variable. This is a fallback; APIs should declare parameters explicitly so descriptions and data types are accurate.

## 12. Advanced Schemas Supported by Conversion

`OpenApiSchemaConverter` supports many common JSON Schema constructs:

- `$ref` and schema reference resolution.
- `allOf`, `anyOf`, and `oneOf`.
- Nested objects and nested properties.
- Recursive schemas with circular reference detection.
- `pattern`.
- `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`.
- `minLength`, `maxLength`.
- `minItems`, `maxItems`.
- `multipleOf`, `enum`, and `default`.

Request DTO example:

~~~java
public class CreateOrderRequest {

    @NotBlank
    private String customerId;

    @NotEmpty
    private List<OrderLineRequest> items;

    @Size(max = 500)
    private String note;
}
~~~

Constraints expressed in OpenAPI can become input JSON Schema constraints so the agent knows limits before calling the tool. However, a tool schema does not replace Bean Validation or server-side business validation. The server must still validate requests just as it does for any regular HTTP request.

## 13. Describing Return Types for AI Agents

Tool descriptions are augmented with return type information. For example, an operation returning `OrderResponse` can be annotated further as:

~~~text
Returns OrderResponse (id, customerId, status, total)
~~~

This information helps the agent understand the expected result and choose how to handle the output. Even so, return type descriptions do not replace response schemas, error handling, or response examples.

If an endpoint returns large payloads, use a concise DTO for tool-facing APIs. The dashboard warns on large response payloads to remind teams to consider trimming data fed into an agent's context window.

## 14. Grouping Tools with @Tag

Tools are grouped by the controller's first `@Tag`. For example:

~~~java
@RestController
@RequestMapping("/customers")
@Tag(name = "Customers")
public class CustomerController {
    // customer operations
}

@RestController
@RequestMapping("/products")
@Tag(name = "Products")
public class ProductController {
    // product operations
}
~~~

The dashboard can display two groups: `Customers` and `Products`. Tools without a tag appear under the `Other` group. Native MCP tools declared with `@McpTool` or `@Tool` are grouped separately under `mcp-tools` in the dashboard.

Tags should reflect business domains or task groups. Avoid putting every operation under a generic tag like `API`, as both agents and developers will have a harder time finding the right tool.

## 15. Excluding Endpoints from the MCP Tool List

Not every REST endpoint is suitable for an AI agent. For example:

- Internal endpoints meant only for health checks or debugging.
- Account and permission management endpoints.
- Endpoints manipulating sensitive data.
- Endpoints intended only for system-to-system callbacks.
- Endpoints with payloads or side effects unsuitable for agents.

You can exclude paths by configuration:

~~~yaml
springdoc:
  ai:
    mcp:
      paths-to-exclude:
        - /internal/**
        - /admin/**
        - /actuator/**
~~~

These are Ant patterns applied to MCP tool generation. At the same time, narrow the documented API surface using `springdoc.packages-to-scan`, `springdoc.paths-to-match`, or `GroupedOpenApi` where appropriate.

Excluding an operation from the tool list does not mean the REST endpoint is protected. Clients can still call the REST URL directly if network and security policies permit. Authorization must be enforced on the server.

## 16. Customizing Name, Description, and Input Schema with McpToolCustomizer

`McpToolCustomizer` is an extension point for adjusting a tool definition after Springdoc generates it from OpenAPI. You can:

- Rename the tool.
- Rewrite the description.
- Adjust the input schema.
- Exclude the tool completely from the list.
- Override the safe/mutating classification for a specific operation.

Example:

~~~java
@Bean
McpToolCustomizer customizeOrderTools() {
    return (context, path, method, operation) -> {
        if ("getOrderById".equals(context.getName())) {
            context.setName("find_order");
            context.setDescription(
                "Find an order by its unique identifier."
            );
        }

        if (path.startsWith("/internal")) {
            context.setExclude(true);
        }

        return context;
    };
}
~~~

`McpToolDefinitionContext` provides the main operations:

| Getter/Setter | Meaning |
|---|---|
| `getName` / `setName` | Read or rename the tool |
| `getDescription` / `setDescription` | Read or change the description |
| `getInputSchema` / `setInputSchema` | Read or replace the input JSON Schema |
| `isExclude` / `setExclude` | Exclude the tool from the list |
| `getSafeEndpoint` / `setSafeEndpoint` | Override the safe/mutating classification |

Returning `null` can exclude a tool, though current documentation prefers calling `context.setExclude(true)` to express intent clearly. If multiple customizers exist, they are applied in registration/order sequence; avoid having separate beans modify the same field in conflicting ways.

## 17. Writing AI-Specific Descriptions with @McpToolDescription

OpenAPI summaries/descriptions are usually written for developers. A more direct description may be needed for AI agents. Placing the `@McpToolDescription` annotation on a controller method allows overriding the description and optionally the tool name:

~~~java
@GetMapping("/orders/{id}")
@Operation(
    summary = "Look up an order",
    operationId = "getOrderById"
)
@McpToolDescription(
    value = "Find an order by its unique ID. Use when the user asks for the status or details of a specific order.",
    name = "find_order"
)
public OrderResponse getOrderById(@PathVariable String id) {
    return orderService.findById(id);
}
~~~

Attributes:

| Attribute | Required | Meaning |
|---|---|---|
| `value` | Yes | Description optimized for AI agents |
| `name` | No | Custom tool name; defaults to `operationId` if omitted |

The default customizer reads this annotation with high priority. Application-registered `McpToolCustomizer` beans can still adjust values afterward.

Descriptions for AI should be concise yet contextual: when to use, required data, and primary effect. Never place secrets, tokens, internal details, or instructions that could lead an agent to bypass business policies inside descriptions.

## 18. Classifying Safe and Mutating Tools

Springdoc classifies tools automatically by HTTP method:

| Group | Default HTTP Methods |
|---|---|
| Safe/read-only | `GET`, `HEAD`, `OPTIONS` |
| Mutating | `POST`, `PUT`, `DELETE`, `PATCH`, and all other methods |

The safe list can be configured with:

~~~yaml
springdoc:
  ai:
    mcp:
      guardrails:
        safe-methods: GET,HEAD,OPTIONS
~~~

Method-based classification is a default rule, not semantic business analysis. For example, `POST /reports/generate` might only produce a read-only preview report, whereas `GET /cache/invalidate` alters state. For special cases, use `McpToolCustomizer` and `context.setSafeEndpoint(Boolean)` to override the classification.

Do not treat an endpoint as safe solely because it uses `GET`. If a `GET` has side effects, reclassify it as mutating and fix the HTTP design if possible.

## 19. Human-in-the-Loop for Data-Mutating Operations

By default:

~~~yaml
springdoc:
  ai:
    mcp:
      guardrails:
        require-approval-for-mutating-tools: true
~~~

When an agent invokes a tool classified as mutating, Springdoc does not execute the HTTP request immediately. Instead, the tool returns a structured response, for example:

~~~json
{
  "requires_human_approval": true,
  "tool_name": "create_order",
  "http_method": "POST",
  "path": "/orders",
  "arguments": {
    "customerId": "CUS-100"
  },
  "message": "This mutating operation requires human approval before execution."
}
~~~

The agent should forward the confirmation request to the user or the application's approval workflow. Only when approved per the supported flow is the operation executed.

The approval requirement can be disabled:

~~~yaml
springdoc:
  ai:
    mcp:
      guardrails:
        require-approval-for-mutating-tools: false
~~~

Only consider this in trusted environments that already have independent authorization and impact controls. Do not disable approval merely for agent convenience.

## 20. Approval Does Not Replace Authentication and Authorization

Human-in-the-Loop is a confirmation step, not a security boundary. Someone who can access the MCP endpoint and admin API could complete an approval request themselves. Therefore:

- Authentication must establish the identity of the client or user.
- Authorization must decide which tools that identity is allowed to call.
- Approval adds a confirmation step for impactful actions.
- Auditing records activity for investigation and monitoring.

Do not use approval to replace roles, scopes, or business permissions. The REST server must still check permissions on every request, since an agent could call the API outside MCP or a tool could be invoked by another client.

## 21. Enabling the MCP Developer Dashboard

The dashboard is disabled by default. To enable it:

~~~yaml
springdoc:
  ai:
    mcp:
      dashboard-enabled: true
      dashboard-path: /mcp-ui
~~~

The dashboard supports:

- Exploring registered tools, grouped by OpenAPI tag.
- Viewing names, descriptions, HTTP methods, paths, and input schemas.
- Testing tool calls with JSON input directly in the browser.
- Inspecting response bodies, status codes, and execution duration.
- Showing warnings for mutating tools awaiting approval.
- Forwarding auth headers such as `Authorization` or API keys to the underlying REST call.
- Configuring Bearer, Basic Auth, or API key credentials for testing.
- Viewing audit events, timestamps, and payload details.
- Copying cURL invocations to reproduce requests.

The dashboard is helpful during tool development and schema checks, but it is also a UI capable of executing operations. Protect it like an admin console, especially when the application connects to real data.

## 22. Dashboard REST API and Audit Logging

The Dashboard REST API is served under `/api/mcp-admin`:

| Method | Endpoint | Function |
|---|---|---|
| `GET` | `/api/mcp-admin/tools` | Lists tools, including groups |
| `POST` | `/api/mcp-admin/tools/execute` | Executes a tool by name and JSON arguments |

Each tool execution emits a structured JSON audit event on the logger:

~~~text
org.springdoc.ai.mcp.audit
~~~

Audit events are logged at `INFO` level. When the dashboard is active, events are also kept in memory for display in the audit tab. In-memory data should not be treated as a durable audit store; for long-term retention, forward logs to a centralized logging system with proper access controls and retention policies.

Since 3.1.1, values under secret-like keys such as `authorization`, `password`, `token`, `api-key`, `secret`, and `cookie` are masked before being logged or stored for the dashboard:

~~~yaml
springdoc:
  ai:
    mcp:
      audit:
        redact: true
~~~

Keep `redact` enabled in most environments. Do not disable data masking if log sinks or the dashboard could be accessed by unauthorized users. Redaction does not replace minimizing sensitive data in tool inputs/outputs.

## 23. Protecting MCP Endpoints with Spring Security

Main integration endpoints:

| Endpoint | Role |
|---|---|
| `/mcp` | MCP protocol endpoint |
| `/mcp-ui/**` | Dashboard UI and static resources |
| `/api/mcp-admin/**` | Admin API and dashboard tool execution |

Springdoc does not apply authentication or authorization to these endpoints automatically. Example security chain configuration:

~~~java
@Bean
SecurityFilterChain mcpSecurity(HttpSecurity http) throws Exception {
    return http
        .securityMatcher(
            "/mcp",
            "/mcp-ui/**",
            "/api/mcp-admin/**"
        )
        .authorizeHttpRequests(requests -> requests
            .anyRequest().hasRole("MCP_ADMIN")
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

The example uses the `MCP_ADMIN` role for illustration. In production, choose OAuth2 Resource Server, sessions, or an authentication mechanism matching your system. If multiple `SecurityFilterChain` beans exist, verify `@Order` and `securityMatcher` so MCP requests are handled by the right chain.

The HTTP MCP endpoint accepts requests according to the configured transport; do not test the transport with a single `GET` if the protocol requires different requests. If the application enables CSRF protection, configure CSRF deliberately for machine-to-machine endpoints and only in the required scope; do not disable CSRF application-wide just so an MCP client can connect.

Beyond Spring Security, place a reverse proxy or gateway with TLS, rate limiting, network policies, and appropriate `Origin` controls. Do not assume `localhost` is a security boundary: a web page running in a browser can attempt requests against `localhost` or private-network services if the server lacks proper protections.

## 24. Restricting the Tool Surface and Per-API Permissions

An operation appearing in OpenAPI can become a tool. Thus, choosing controllers and paths acts as a capability-publishing decision.

Apply multiple layers:

1. Use `packages-to-scan` and `paths-to-match` to scope the OpenAPI document.
2. Use `springdoc.ai.mcp.paths-to-exclude` to exclude endpoints from MCP tool generation.
3. Use `McpToolCustomizer` to exclude tools by operation, method, or path.
4. Use Spring Security to enforce authorization on both MCP endpoints and REST endpoints.
5. Inspect the tool list after the application starts.

Do not merely remove an admin endpoint from the dashboard and assume it cannot be called. If the REST route remains open and another tool or caller can reach it, the server must still check permissions at the business layer.

## 25. Combining Springdoc MCP with Spring AI Native MCP Tools

Springdoc MCP generates tools from OpenAPI operations. Spring AI also provides ways to declare MCP capabilities directly, such as `@McpTool` on methods or `ToolCallbackProvider` beans.

Both sources can coexist in the same application:

- OpenAPI-backed tools: auto-generated from `@RestController` operations.
- Native MCP tools: defined directly by the application using Spring AI APIs or annotations.

The dashboard can discover both `ToolCallbackProvider` beans and native MCP tool specifications. However, manage tool names and responsibilities clearly to avoid name collisions or two tools performing the same task with different permissions.

If you need MCP resources or prompts, define them using Spring AI's corresponding native capabilities. Do not add a REST endpoint expecting Springdoc to turn it into a resource or prompt automatically.

## 26. Using the Spring AI STATELESS Protocol

Starting from springdoc 3.2.0, tools can be registered with `McpStatelessSyncServer` when the application uses the Spring AI `STATELESS` protocol:

~~~yaml
spring:
  ai:
    mcp:
      server:
        protocol: STATELESS
~~~

This is a server protocol selection, not the property that enables Springdoc MCP. You still need:

~~~yaml
springdoc:
  ai:
    mcp:
      enabled: true
~~~

Check the Spring AI version managed by Spring Boot/Springdoc and the transports supported by your MCP clients. Do not enable `STATELESS` just to avoid sessions; verify discovery, context, notifications, and tool invocation behavior for your specific client/server setup.

## 27. Testing the Integration Locally

After adding dependencies and configuration:

1. Start the application with the right profile.
2. Confirm the OpenAPI document is generated.
3. Confirm MCP integration is enabled.
4. Test the `/mcp` endpoint using the protocol and MCP client in use.
5. Verify the tool list has the expected names, descriptions, and input schemas.
6. Invoke a read-only `GET` tool.
7. Invoke a mutating tool and confirm approval is requested per configuration.
8. Test an excluded path and confirm it does not appear.
9. Check the dashboard if enabled.
10. Test security when unauthenticated and with an authorized account.

The dashboard can help inspect tools and run quick tests, but you should also test with a real MCP client. A tool appearing in the dashboard does not prove a production client can initialize a session, discover tools, and invoke them over the right transport.

## 28. Testing Tool Contracts and Behavior

Tests should cover:

| Case | Expectation |
|---|---|
| OpenAPI operation with `operationId` | Stable, readable tool name |
| Path/query/header parameter | Input schema contains the right properties and required markers |
| Request body | Input schema reflects body and nested schemas |
| Operation with `$ref` | Schema converter resolves references |
| Controller with `@Tag` | Tools are grouped accurately |
| Operation matching `paths-to-exclude` | Not exposed as a tool |
| Customizer renames a tool | Client sees the new name |
| Customizer excludes a tool | Tool does not appear in the list |
| Read-only `GET` | Classified as safe by default |
| `POST`/`PUT`/`PATCH`/`DELETE` | Requires approval when guardrail is enabled |
| Unauthorized caller | MCP request is rejected |
| Unauthorized REST endpoint | Tool invocation is still rejected by the server |
| Audit event | Event is emitted and secrets are redacted |

Test both tool discovery and tool execution. Discovery checks metadata; execution checks base URL, HTTP method, path, header forwarding, request body, authorization, and response mapping.

## 29. Integrating MCP into CI

An MCP verification pipeline can include:

~~~text
Build Spring Boot application
          |
          v
Start with MCP-enabled profile
          |
          v
Wait for OpenAPI preloading and MCP registration
          |
          v
Connect MCP test client
          |
          v
List and inspect tools
          |
          v
Verify schemas, tags and exclusions
          |
          v
Invoke read-only test tool
          |
          v
Verify mutation approval and authorization
          |
          v
Check audit redaction
          |
          v
Stop application and publish test results
~~~

Do not let CI invoke mutating tools against shared data. Use a test database or mock services and verify approval before execution. If mutation execution tests are needed, run them only in an isolated environment with resettable data.

When upgrading Springdoc or Spring AI, re-run tool list tests because names, schemas, transports, or server registration may change across versions.

## 30. Common Errors

| Symptom | Cause to Check | Resolution |
|---|---|---|
| MCP artifact not found | Using an unsupported Springdoc branch | Check Spring Boot 4 and Springdoc 3.x |
| Dependency present but `/mcp` missing | MCP not enabled or using version 3.1.1+ | Set `springdoc.ai.mcp.enabled=true` |
| Application hangs during startup | OpenAPI preloading or endpoint not ready | Check OpenAPI generation errors and `init-timeout-seconds` |
| Tool list is empty | No operations scanned or all filtered out | Check controllers, OpenAPI paths, and exclusions |
| Unclear tool names | Missing or unstable `operationId` | Set explicit `operationId` values |
| Tool input missing parameters | OpenAPI operation lacks parameter descriptions | Add `@PathVariable`, `@RequestParam`, or `@Parameter` metadata |
| Body has wrong shape | Client sends wrong body properties or content type | Inspect the input schema generated by the converter |
| Tool calls wrong host/port | Wrong `base-url` or context path | Configure `base-url` to match runtime |
| Tool appears but returns 401/403 | REST endpoint requires permissions | Forward credentials and check permissions on the API |
| Dashboard fails to open | `dashboard-enabled=false` or blocked by security | Enable dashboard intentionally and grant permissions |
| Mutating tool is blocked | Approval is enabled | Complete the confirmation flow or keep the guardrail per policy |
| Sensitive tool still appears | OpenAPI or MCP paths not filtered | Add `paths-to-exclude` or `McpToolCustomizer` |
| Audit logs contain sensitive data | Redaction disabled or key unrecognized | Keep `redact=true` and minimize sensitive payloads |
| WebFlux behaves differently from MVC | Reactive context or version differences | Use the patched WebFlux starter version and test concurrency |
| `STATELESS` does not work | Spring AI server protocol not configured properly | Check version and `spring.ai.mcp.server.protocol` |

When diagnosing, separate three layers: whether OpenAPI describes the operation accurately, whether MCP registers a tool from that operation, and whether the tool callback can invoke the REST endpoint with appropriate permissions. This helps pinpoint whether the bug lies in documentation, MCP registration, or the actual HTTP request.

## 31. Safe MCP Deployment Workflow

Follow these steps in order:

1. Confirm the application uses Spring Boot 4 and a springdoc 3.x branch with MCP modules.
2. Choose the matching WebMVC or WebFlux starter.
3. Declare clear `operationId`, `summary`, `description`, parameters, request bodies, and responses.
4. Enable `springdoc.ai.mcp.enabled` in the required profile.
5. Configure `base-url`, timeout, and endpoint paths.
6. Exclude internal or sensitive endpoints from tool generation.
7. Add `@Tag` by business domain and write agent-friendly descriptions.
8. Add `McpToolCustomizer` or `@McpToolDescription` when needed.
9. Keep approval enabled for mutating tools and verify safe/mutating classification.
10. Protect `/mcp`, `/mcp-ui/**`, and `/api/mcp-admin/**` with Spring Security.
11. Protect underlying REST endpoints with per-resource authorization.
12. Keep audit redaction enabled and control where logs are stored.
13. Test discovery, schemas, execution, approval, and access denial.
14. Follow Springdoc/Spring AI release notes and upgrade to the latest appropriate patch release.

Never expose an MCP endpoint to the Internet before clearly defining who may discover tools, who may call each tool, and who is authorized to perform data-mutating actions.

## 32. Takeaways

- MCP standardizes how AI clients discover and invoke tools.
- Springdoc MCP converts `@RestController` OpenAPI operations into MCP tools.
- Integration starts in springdoc 3.0.3 on the Spring Boot 4 branch; springdoc 2.x for Boot 3 has no MCP starter.
- From 3.1.1, MCP is opt-in and disabled by default; set `springdoc.ai.mcp.enabled=true`.
- Use `springdoc-openapi-starter-webmvc-mcp` or `springdoc-openapi-starter-webflux-mcp` matching your web stack.
- OpenAPI `operationId` produces the tool name; `summary`/`description` produce the description; parameters and request bodies produce the input JSON Schema.
- `@Tag` groups tools; `@McpToolDescription` provides AI-specific descriptions.
- `McpToolCustomizer` can rename, re-describe, adjust schemas, exclude tools, and override safe/mutating status.
- `GET`, `HEAD`, and `OPTIONS` are safe by default; all other methods are mutating by default.
- Mutation approval is a confirmation step, not authorization.
- The dashboard is disabled by default and supports exploration, test execution, and audit viewing.
- `/mcp`, `/mcp-ui`, and `/api/mcp-admin/**` do not enforce authentication/authorization on their own.
- Protect both MCP endpoints and underlying REST endpoints with Spring Security.
- Keep audit redaction enabled and limit sensitive payloads.
- From 3.2.0, tools can register with a stateless MCP server when Spring AI `STATELESS` is configured.
- Test tool discovery, input schemas, authorization, approval, and execution in CI.

MCP in Springdoc branches that provide integration lets you reuse OpenAPI to expose REST APIs to AI agents as tools. Choose the right Spring Boot 4/Springdoc 3.x branch, enable the integration explicitly, design clear operations and descriptions, filter tools by business domain, and protect both MCP and REST endpoints with real permissions. Guardrail approval helps confirm data-mutating actions, but it does not replace authentication, authorization, or auditing.

## References

- Springdoc OpenAPI – MCP Support: https://springdoc.org/#mcp
- Springdoc OpenAPI – Configuration Properties: https://springdoc.org/properties.html
- Springdoc OpenAPI – Modules: https://springdoc.org/modules.html
- Springdoc OpenAPI – Releases: https://github.com/springdoc/springdoc-openapi/releases
- Spring AI – MCP Server Boot Starter: https://docs.spring.io/spring-ai/reference/api/mcp/mcp-server-boot-starter-docs.html
- Spring AI – MCP Overview: https://docs.spring.io/spring-ai/reference/api/mcp/mcp-overview.html
