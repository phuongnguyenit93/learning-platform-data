# Compatibility Boundaries Between Springdoc, Spring AI, and Protocol Versions

When bringing AI agents into a Spring Boot application, teams often want both to expose REST APIs with OpenAPI and to let agents invoke those capabilities via the Model Context Protocol (MCP). `springdoc-openapi` and Spring AI can work together in this architecture, yet each component addresses a different layer. Picking the newest version numbers without checking the Spring Boot baseline, MCP Java SDK, and protocol revision can prevent the application from starting, break tool registration, or prevent clients from handshaking with the server.

It is essential to distinguish five axes:

1. **Spring Boot / Spring Framework:** the runtime and auto-configuration platform that libraries must match.
2. **springdoc-openapi:** inspects Spring controllers and metadata to generate OpenAPI Descriptions, Swagger UI, or optional MCP integration modules.
3. **Spring AI:** provides abstractions for models, tool calling, and MCP clients/servers in Spring.
4. **MCP Java SDK:** implements the Java APIs for MCP clients, servers, transports, and messages.
5. **MCP protocol revision:** defines the wire format and communication lifecycle between MCP clients and servers.

The OpenAPI version in the document's `openapi` field is also an independent axis. An OpenAPI version is neither a Spring AI version nor an MCP protocol version.

## 1. Distinguishing REST/OpenAPI from MCP

OpenAPI describes HTTP APIs: paths, methods, parameters, request bodies, responses, schemas, and security requirements. springdoc reads Spring application metadata to generate an OpenAPI document for humans, API gateways, validators, or client generators.

MCP is a protocol for an AI application to discover and invoke tools, read resources, fetch prompts, and exchange capabilities with an MCP server. MCP uses JSON-RPC over transports such as STDIO, HTTP with SSE, or Streamable HTTP.

~~~mermaid
flowchart TD
    A["Spring Boot application"] --> B["REST controllers and DTOs"]
    B --> C["springdoc-openapi"]
    C --> D["OpenAPI Description"]
    D --> E["Swagger UI / API clients"]
    D --> F["springdoc MCP bridge"]
    G["Spring AI native tools"] --> H["MCP Java SDK"]
    F --> H
    H --> I["MCP transport and protocol"]
    I --> J["AI agent / MCP client"]
~~~

Two common integration approaches:

| Approach | How It Works | When It Fits |
|---|---|---|
| REST APIs converted into MCP tools | springdoc reads OpenAPI operations and creates tool definitions for MCP clients to discover and invoke | Existing REST controllers where you want to reuse the existing contract |
| MCP tools declared directly in Spring AI | Uses annotations such as `@McpTool`, `@McpResource`, or `ToolCallback` to register capabilities | Tools with dedicated logic where not every REST endpoint should be exposed to agents |

Both approaches can be used in the same application. However, you must control tool names, input schemas, access permissions, and exposed endpoint scope.

## 2. Responsibilities of Each Component

| Component | Responsibility | What It Does Not Decide |
|---|---|---|
| Spring Boot | Creates the application context, web stack, configuration, and security filters | Does not decide the MCP protocol revision |
| springdoc-openapi | Generates OpenAPI from controllers, annotations, validation, and configuration; provides an optional MCP bridge module | Does not replace MCP Java SDK or Spring AI |
| Spring AI | Provides AI model integrations, tool calling, MCP client/server support, and Boot starters | Does not decide the OpenAPI schema version of REST documents |
| MCP Java SDK | Provides client/server, JSON-RPC messages, sessions, and transport implementations | Does not select the Spring Boot or springdoc version |
| MCP specification | Defines wire protocol, capabilities, methods, negotiation, and transport behavior | Does not dictate Spring Boot dependency versions |

For example, upgrading springdoc from 2.x to 3.x may require upgrading Spring Boot from 3.x to 4.x. That does not automatically mean MCP clients switched from revision `2025-11-25` to `2026-07-28`. Protocol revision depends on the MCP server/client implementations and their compatible configuration.

## 3. Spring Boot, springdoc, and Spring AI Compatibility Matrix

Official branches currently divide by Spring Boot major version:

| Spring Boot | Spring Framework | springdoc-openapi | Spring AI |
|---|---|---|---|
| 3.5.x | 6.2.x | 2.8.x–2.10.x | 1.1.x |
| 4.0.x | 7.x | 3.0.x | 2.0.x |
| 4.1.x | 7.x | 3.1.x–3.2.x | 2.0.x |
| 4.2.0-RC2 | 7.x prerelease | No springdoc matrix confirmed in current documentation | 2.1.0-RC2 |

These are published compatible branches, not a guarantee that arbitrary patch releases within those branches can be mixed freely. Always check specific releases, dependency management, and Java requirements for your chosen Spring Boot version.

Key milestones:

- springdoc 2.x targets Spring Boot 3.x; springdoc 3.x targets Spring Boot 4.x.
- Spring AI 1.1.x currently targets Spring Boot 3.5.x.
- Spring AI 2.0.x is designed for Spring Boot 4.0.x and 4.1.x, based on Spring Framework 7.
- Spring AI 2.0 moves to Jackson 3 with corresponding API and package changes.

Do not bring Spring AI 2.x into a Spring Boot 3 application just because both artifacts exist on Maven Central. Successful dependency resolution does not prove auto-configuration, Spring Framework APIs, and the serialization stack are compatible.

### Stable Releases vs. Prereleases

As of 2026-11-20, Spring AI 2.0.2 is the latest published stable release; Spring AI 2.1.0-RC2 is available but remains a release candidate. When building for production, prefer stable releases unless there is a specific reason to test features available only in prereleases.

Spring AI 2.1.0-RC2 supports MCP revision `2026-07-28`, based on MCP Java SDK 2.2.0-M2 and built against Spring Boot 4.2.0-RC2. Keep this in mind if you want to use the `MODERN` protocol. Because both Spring AI 2.1.0-RC2 and Boot 4.2.0-RC2 are prereleases, do not assume Spring AI 2.0.2 or springdoc 3.2.0 shares the same tested baseline.

## 4. Distinguishing MCP Version Layers

MCP has multiple protocol revisions. Handshake revisions such as `2025-11-25` and earlier use the `initialize` method to negotiate version and capabilities. Revision `2026-07-28` introduces the `MODERN` lifecycle with per-request stateless communication.

| Axis | Example | Meaning |
|---|---|---|
| Spring AI | 2.0.2 or 2.1.0-RC2 | Spring AI framework version |
| MCP Java SDK | 2.0.0 or 2.2.0 | Java library version implementing MCP |
| MCP protocol revision | `2025-11-25` or `2026-07-28` | Wire communication rules between client and server |
| Transport | STDIO, SSE, Streamable HTTP | How messages are transmitted |
| Server execution model | `SYNC` or `ASYNC` | Synchronous or reactive handler style |
| Spring AI server protocol setting | `SSE`, `STREAMABLE`, `STATELESS`, or `MODERN` | Server implementation/transport behavior choice in Spring AI |

Do not conflate transport with protocol revision. Streamable HTTP is a transport; `MODERN` is a protocol revision/lifecycle. An application can share the same transport family while having to obey the lifecycle and message format of the selected revision.

## 5. Legacy Handshake vs. MODERN Protocol

### Handshake era: up to 2025-11-25

Handshake revisions begin with:

1. Client sends `initialize` with protocol version and capabilities.
2. Server returns the negotiated protocol version and server capabilities.
3. Client sends `notifications/initialized`.
4. Client and server continue exchanging requests/responses within the session.

With HTTP transport, the server may use session identifiers and notifications or streams per revision rules. Client and server must agree on a mutually supported revision.

### MODERN: 2026-07-28

The `MODERN` revision changes the lifecycle:

- Removes the legacy `initialize` handshake and session model.
- Clients discover the server via `server/discover`.
- Each request carries the protocol version and client capabilities in metadata.
- HTTP servers use `POST`; responses can be JSON or short-lived `text/event-stream` when progress updates are needed.
- Server-initiated inputs such as elicitation, sampling, and roots are handled via multi-round-trip requests rather than callbacks over an old session.
- List-changed and resource-updated notifications are delivered via `subscriptions/listen`.

Therefore, an older client that only knows `initialize` cannot be treated as `MODERN`-compatible. A server supporting `MODERN` should not assume every handshake client automatically uses the new lifecycle either.

## 6. STATELESS Does Not Mean MODERN

A common source of confusion is the Spring AI property:

~~~yaml
spring:
  ai:
    mcp:
      server:
        protocol: STATELESS
~~~

`STATELESS` is a server mode in Spring AI for handling requests without maintaining session state between requests. It belongs to the server/transport model provided by Spring AI.

`MODERN` is the protocol option corresponding to MCP revision `2026-07-28`:

~~~yaml
spring:
  ai:
    mcp:
      server:
        protocol: MODERN
~~~

Both reduce or remove stateful sessions, but they are not two names for the same mode. `MODERN` defines specific rules for `server/discover`, per-request metadata, multi-round-trip flows, and `subscriptions/listen`. Spring AI documentation describes `STATELESS` as a server that keeps no session state between requests and does not support server-to-client requests such as elicitation, sampling, or ping. Determine the protocol revision independently from MCP Java SDK and client capabilities; never infer revision from the name `STATELESS` alone.

When reading configuration, identify explicitly:

- Which transport is selected?
- Is the server running `SYNC` or `ASYNC`?
- Is `STATELESS` server mode enabled?
- Is the `MODERN` protocol revision actually implemented?
- Does the client support the same revision?

Do not use the word "stateless" in an architecture diagram to conclude that client and server are compatible with the `MODERN` revision.

## 7. MCP Java SDK Compatibility by Spring AI Line

Spring AI manages the MCP Java SDK via dependency management. Major upgrade milestones include significant changes:

| Spring AI Line | MCP Java SDK Line | Notes |
|---|---|---|
| Spring AI 1.1.8 | 0.18.3 | Dependency baseline published for release 1.1.8 on Boot 3.5.x |
| Spring AI 2.0.x | 2.0.x | Major SDK upgrade; Spring transports moved into the Spring AI project |
| Spring AI 2.1.0-RC2 | 2.2.0-M2 | Supports `MODERN` revision `2026-07-28` in prerelease |

These are baselines per published release. If a project declares the MCP SDK directly instead of using the Spring AI BOM, check the dependency tree to make sure it does not force a different version than the one tested with the Spring AI starter.

### Package and Artifact Changes Since Spring AI 2.0

Before Spring AI 2.0, some Spring transports were published under the MCP Java SDK group:

~~~xml
<dependency>
    <groupId>io.modelcontextprotocol.sdk</groupId>
    <artifactId>mcp-spring-webmvc</artifactId>
</dependency>
~~~

Starting with Spring AI 2.0, Spring transports moved to the `org.springframework.ai` group:

~~~xml
<dependency>
    <groupId>org.springframework.ai</groupId>
    <artifactId>mcp-spring-webmvc</artifactId>
</dependency>
~~~

Transport Java packages also moved from `io.modelcontextprotocol` to `org.springframework.ai.mcp`. If code instantiates transport providers directly, update imports. If using only Spring Boot starters and auto-configuration, most package changes are handled inside the starter.

Spring AI 2.0 also upgraded MCP Java SDK from 1.1.x to 2.0.0. This change affects code referencing MCP types directly, so read upgrade notes if the application has custom client/server builders.

## 8. How the Springdoc MCP Bridge Works

springdoc has an optional MCP module that turns REST endpoints already described with OpenAPI into MCP tools. The idea is reusing existing metadata:

1. Springdoc scans controllers and generates the OpenAPI document.
2. Each OpenAPI operation is converted into a tool definition.
3. Tool names typically come from `operationId`.
4. Tool descriptions come from `summary`/`description`.
5. Input JSON Schemas are generated from parameters and request bodies.
6. MCP clients discover tools and invoke them through the MCP server.

Example controller:

~~~java
@RestController
@RequestMapping("/api/products")
@Tag(name = "Products")
class ProductController {

    @GetMapping("/{id}")
    @Operation(
        operationId = "getProductById",
        summary = "Get product by ID"
    )
    ProductResponse getById(@PathVariable String id) {
        // ...
    }
}
~~~

This operation retains its REST contract via `GET /api/products/{id}`. When the bridge is enabled, it can appear as an MCP tool with a name derived from `operationId` and an input schema containing `id`.

An MCP tool is not a new REST route. It is a way for agents to invoke an existing operation through the MCP protocol.

The bridge typically converts `operationId` into a `snake_case` tool name, such as `getProductById` becoming `get_product_by_id`; pulls descriptions from `summary`/`description`; and groups tools by controller tag. You can use `@McpToolDescription` to supply a name or description tailored specifically for AI agents, or `McpToolCustomizer` to rename, adjust descriptions/schemas, or exclude endpoints from the tool list.

## 9. Choosing the Right springdoc MCP Starter

Current springdoc MCP documentation describes separate starters per web stack:

| Web Stack | Dependency |
|---|---|
| Spring MVC / Servlet | `springdoc-openapi-starter-webmvc-mcp` |
| Spring WebFlux | `springdoc-openapi-starter-webflux-mcp` |

Example dependency shown in current documentation at version 3.2.0:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-mcp</artifactId>
    <version>3.2.0</version>
</dependency>
~~~

The corresponding WebFlux starter uses artifact `springdoc-openapi-starter-webflux-mcp`. Choose the starter matching the application's web stack. Do not add both MVC and WebFlux MCP starters at once just to test; the two stacks configure servers and resources differently.

Current MCP guidance illustrates the springdoc 3.2.0 line, which belongs to the Boot 4.x branch. Do not copy dependency 3.2.0 into a Boot 3.x application running springdoc 2.x. For Boot 3 applications, use the appropriate springdoc 2.x branch for OpenAPI and Spring AI 1.1.x for MCP; if a REST-to-MCP bridge is needed, verify whether a specific artifact/version was released for that branch before deploying.

## 10. Enabling the Bridge Explicitly

Since springdoc 3.1.1, MCP integration is disabled by default. Adding the starter does not automatically open the MCP endpoint. Enable the feature with:

~~~yaml
springdoc:
  ai:
    mcp:
      enabled: true
~~~

If a tool management dashboard is needed, configure the dashboard separately:

~~~yaml
springdoc:
  ai:
    mcp:
      enabled: true
      dashboard-enabled: true
~~~

The bridge requires the OpenAPI specification to be ready when registering tools. springdoc documentation notes that when MCP is enabled, OpenAPI pre-loading is enabled automatically to register tools.

Do not enable the bridge just because the application has Swagger UI. Identify which operations are genuinely suitable for agents to invoke, because a REST endpoint exposed as a tool can execute actions on a user's behalf.

## 11. Documented Compatibility Limits Between springdoc and Spring AI

springdoc's MCP documentation states that the bridge registers tools with `McpSyncServer`; starting in springdoc 3.2.0, it also supports `McpStatelessSyncServer` from Spring AI's `STATELESS` protocol.

This is an important boundary compared to Spring AI 2.1.0-RC2:

- Spring AI 2.1.0-RC2 adds support for the `MODERN` server protocol and requires the MCP Java SDK 2.2.0 line.
- The springdoc MCP guide currently documents support for `SYNC` servers and `STATELESS` servers, but does not confirm REST-to-MCP bridge compatibility with the `MODERN` server protocol.
- Therefore, do not conclude that the springdoc 3.2.0 bridge is compatible with `MODERN` just because Spring AI 2.1 can run `MODERN`.

If `MODERN` is required, verify via integration tests using the exact versions of springdoc, Spring AI, MCP Java SDK, and client. If the bridge is outside supported scope, expose tools using Spring AI native annotations/`ToolCallback` and continue using springdoc for REST/OpenAPI documentation.

A feature in Spring AI does not automatically become a feature supported by the springdoc bridge. Compatibility must be verified at the boundary between the two integrations.

## 12. Spring AI Native MCP Tools

When a tool is not a REST operation or needs dedicated input/output shaped for AI agents, use Spring AI's MCP annotations:

~~~java
@Component
class CatalogTools {

    @McpTool(name = "find_product", description = "Find product by ID")
    ProductResult findProduct(
            @McpToolParam(description = "Product ID", required = true)
            String productId) {
        // ...
    }
}
~~~

Spring AI also provides annotations for resources and prompts:

- `@McpTool`: an action invocable by MCP clients.
- `@McpResource`: data accessed by URI or URI template.
- `@McpPrompt`: structured prompt templates.
- `@McpComplete`: completion suggestions for prompt arguments or resource URIs.

Native tools and OpenAPI-backed tools can coexist. Avoid defining two tools with different names performing the exact same action, as agents may pick the wrong one or duplicate actions.

## 13. Security Is Part of Integration Compatibility

MCP HTTP endpoints do not enforce authentication/authorization on their own just because a Spring AI starter or springdoc MCP starter was added. Per Spring AI documentation, HTTP transports may permit endpoint access by default; Spring Security or a security proxy must establish access boundaries.

Endpoints that may appear in a springdoc MCP integration include:

- `/mcp`: MCP protocol endpoint.
- `/mcp-ui`: developer dashboard if enabled.
- `/api/mcp-admin/*`: dashboard REST API.

Illustrative policy example:

~~~java
@Bean
SecurityFilterChain mcpSecurity(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/mcp", "/mcp-ui/**", "/api/mcp-admin/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/mcp").hasAuthority("SCOPE_mcp.invoke")
            .requestMatchers("/mcp-ui/**", "/api/mcp-admin/**")
                .hasRole("MCP_ADMIN")
            .anyRequest().denyAll()
        )
        .oauth2ResourceServer(oauth -> oauth.jwt())
        .build();
}
~~~

This is an illustrative policy; authorities and JWT configuration must match the real identity system. Do not copy the snippet verbatim if your application uses session logins, API keys, or a different security chain.

### Do Not Treat HITL as Authorization

By default, the bridge requires approval for mutating tools via `require-approval-for-mutating-tools`. This is a guardrail helping users review actions. It does not authenticate callers and does not replace authorization. Anyone able to call the MCP endpoint can still attempt to re-send requests or interact with admin endpoints if those endpoints are unprotected.

Always protect MCP endpoints with Spring Security or a security gateway, even when `require-approval-for-mutating-tools` is enabled.

For HTTP transport, Spring AI documentation also notes that default transports do not validate the `Origin` header automatically. If the MCP server listens on `localhost` or an internal network, a malicious web page could still attempt to call it through a browser via DNS rebinding. Use a security layer or reverse proxy that checks `Origin` per MCP requirements. STDIO does not open a network endpoint and therefore has a different deployment boundary.

### Classifying Tools by Impact

The springdoc MCP bridge classifies `GET`, `HEAD`, and `OPTIONS` as safe by default; `POST`, `PUT`, `PATCH`, and `DELETE` as mutating. This can be customized via `McpToolCustomizer`.

Not every `GET` is safe in business terms. For instance, `GET /cache/invalidate` might mutate state. Conversely, a `POST` might only generate a read-only report. Review every operation by its actual effect rather than relying solely on HTTP method.

## 14. WebMVC and WebFlux Must Match

A Spring MVC application using the Servlet stack needs WebMVC starters. A reactive application using WebFlux needs WebFlux starters. The difference affects:

- Server transport provider type.
- Synchronous vs. reactive handler style.
- Streaming and backpressure handling.
- Security filter chain.
- Runtime transitive dependencies.

Spring AI provides a separate WebFlux client starter when reactive transport is needed. Never mix WebMVC and WebFlux transports in the same configuration just to silence a dependency error. Identify the web application type and pick starters matching the actual stack.

Server types `SYNC` and `ASYNC` must also match tool handlers. `SYNC` servers register synchronous handlers; `ASYNC` servers use reactive handlers. If an annotation scanner fails to pick up methods, check the server type and handler signature before concluding the MCP SDK is incompatible.

## 15. Boot 4 Baseline Configuration Example

This example illustrates an application running Spring Boot 4.1.x, Spring AI 2.0.2, and springdoc 3.2.0. These versions belong to the same compatible branch per the published matrix; still verify release notes and dependency resolution for your project.

Maven dependency management:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.ai</groupId>
            <artifactId>spring-ai-bom</artifactId>
            <version>2.0.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-mcp</artifactId>
        <version>3.2.0</version>
    </dependency>
    <dependency>
        <groupId>org.springframework.ai</groupId>
        <artifactId>spring-ai-starter-mcp-server-webmvc</artifactId>
    </dependency>
</dependencies>
~~~

Configuration:

~~~yaml
springdoc:
  ai:
    mcp:
      enabled: true

spring:
  ai:
    mcp:
      server:
        protocol: STATELESS
~~~

Selecting `STATELESS` server mode is documented for springdoc 3.2.0. It is not an example of enabling `MODERN` protocol `2026-07-28`. If testing `MODERN` with Spring AI 2.1 prerelease, use the matching dependency line and test bridge compatibility separately before adopting it in production.

If the application needs only native Spring AI tools, omit the springdoc MCP starter, keep `springdoc` `webmvc-api` or `webmvc-ui` for REST docs, and use only the Spring AI MCP server starter for the tool endpoint.

## 16. Inspecting the Dependency Tree Before Running

Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springdoc,org.springframework.ai,io.modelcontextprotocol
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-ai --configuration runtimeClasspath
./gradlew dependencyInsight --dependency mcp --configuration runtimeClasspath
./gradlew dependencyInsight --dependency springdoc --configuration runtimeClasspath
~~~

Check:

- Is there exactly one springdoc starter version matching the web stack?
- Does the Spring AI BOM manage all Spring AI modules?
- Is the MCP Java SDK overridden by a direct dependency or another starter?
- Are legacy `io.modelcontextprotocol.sdk:mcp-spring-webmvc/webflux` artifacts still present while using Spring AI 2.x?
- Do transport imports belong to the matching `org.springframework.ai.mcp` packages?
- Are Jackson 2 and Jackson 3 both pulled in in a conflicting way?

Do not force an MCP SDK version via `resolutionStrategy` merely to silence a compile error. First find which dependency introduced the incompatible version into the graph.

## 17. Testing Protocol Negotiation

For handshake-era revisions, test `initialize` to confirm client and server agree on a common revision. Record `protocolVersion` in `InitializeResult` and confirm required capabilities are advertised.

For `MODERN`, check:

- Client sends `server/discover` and receives identity/capabilities.
- Requests include protocol version and client capabilities in metadata.
- Server handles `POST` and returns JSON or a stream per rules.
- Client/server understand multi-round-trip inputs if tools use elicitation or sampling.
- Change notifications arrive via `subscriptions/listen` if those capabilities are enabled.

Do not check only that a TCP port is open or HTTP returns 200. An endpoint can return an HTTP response without understanding the JSON-RPC method, revision, or capabilities required by the client.

## 18. Testing the OpenAPI Bridge Separately from the MCP Protocol

An integration test suite should verify both layers:

### REST/OpenAPI

- `/v3/api-docs` returns a valid document.
- `operationId` values are stable and unique.
- Request parameters and body schemas are accurate.
- Security requirements and response codes reflect the API.
- Group or path filters do not leak internal endpoints.

### MCP

- The MCP endpoint registers only permitted tools.
- Tool names and descriptions suit agents.
- Input JSON Schemas reflect parameters/bodies.
- Tool calls route properly to REST operations or handlers.
- Mutating tools require approval per policy.
- Authentication/authorization is enforced.
- Protocol revision and transport are mutually supported by client and server.

If the REST API runs yet tools do not appear, check bridge registration, pre-loading, `operationId`, customizers, and server type. If tools appear yet calls fail, check input schemas, security headers, transport, and protocol revision.

## 19. Common Compatibility Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Spring AI 2.x fails to start on Boot 3.x | Boot 4 baseline mismatch | Use Spring AI 1.1.x with Boot 3.5.x or upgrade the platform |
| springdoc 3.x fails on Boot 3.x | springdoc 3.x branch targets Boot 4 | Use the corresponding springdoc 2.x release |
| Cannot resolve springdoc MCP artifact | Wrong branch/version or artifact not published for stack | Check the MCP guide and Maven Central coordinates |
| `ClassNotFoundException` in MCP transport | Old MCP SDK imports used with Spring AI 2.x | Switch to `org.springframework.ai.mcp` packages |
| `NoSuchMethodError` in MCP SDK | SDK overridden away from Spring AI-managed version | Use the BOM and inspect the dependency tree |
| Client reports unsupported protocol version | Client and server have no overlapping revision | Pick a common revision or upgrade the SDK |
| Client sends `initialize` to a `MODERN` server | Handshake vs. modern lifecycle mismatch | Use a client supporting `server/discover` or configure a handshake server |
| springdoc bridge registers no tools | `springdoc.ai.mcp.enabled` not enabled or OpenAPI not preloaded | Check properties, starter, and startup logs |
| REST route exists yet MCP tool is missing | Operation excluded by filters or customizers | Check path groups, `operationId`, and `McpToolCustomizer` |
| MCP endpoint open and called unauthorized | Transport does not enforce authorization automatically | Protect endpoints with Spring Security/gateway |
| Tool call rejected by schema validation | Invalid JSON Schema or input | Align schema with handler and client arguments |
| WebFlux handler not registered | Wrong `SYNC`/`ASYNC` server type chosen | Use matching programming model and starter |
| Swagger UI runs yet MCP does not | OpenAPI UI and MCP are two separate integration surfaces | Test MCP endpoint/protocol independently |

## 20. Version Selection Workflow

When starting a project or upgrading:

1. Lock the Spring Boot major/minor and Java baseline.
2. Pick the springdoc branch matching Spring Boot.
3. Pick the Spring AI branch compatible with that Spring Boot version.
4. Let the Spring AI BOM manage the MCP Java SDK unless direct management is required.
5. Determine which handshake revision or `MODERN` the MCP client must support.
6. Choose the appropriate transport: STDIO, Streamable HTTP, or deployed mode.
7. Verify the springdoc MCP bridge supports the exact Spring AI server type your project intends to run.
8. Inspect the dependency tree and package imports.
9. Run integration tests for OpenAPI, tool discovery, tool calls, and security.
10. Upgrade protocol revisions only when both client and server support them and required features are retained.

If a project is stable on Boot 3.5, there is no need to upgrade the entire stack just for Swagger UI. You can keep springdoc 2.x for REST documentation and Spring AI 1.1.x for matching MCP capabilities. When features unique to Spring AI 2.x or the `MODERN` revision are needed, plan a synchronized upgrade of Boot 4, springdoc 3, and the SDK.

## 21. Pre-Release Compatibility Checklist

- [ ] Spring Boot, Spring Framework, and Java versions are within a supported baseline.
- [ ] springdoc branch matches the Spring Boot major/minor version.
- [ ] Spring AI branch matches Spring Boot.
- [ ] MCP Java SDK is managed by the BOM or verified in the dependency tree.
- [ ] Legacy transport artifacts/packages are not mixed with Spring AI 2.x.
- [ ] MVC/WebFlux starters match the web stack.
- [ ] `SYNC`/`ASYNC` handlers match the server type.
- [ ] Transport and MCP protocol revision are identified separately.
- [ ] Client and server negotiate a shared revision.
- [ ] `STATELESS` server mode is not confused with the `MODERN` protocol revision.
- [ ] The springdoc MCP bridge is explicitly enabled if used.
- [ ] Verified that the bridge supports the running MCP server type.
- [ ] Operations exposed as tools have been reviewed.
- [ ] MCP endpoint, dashboard, and admin API have authentication/authorization.
- [ ] Mutating tools have separate approval and authorization policies.
- [ ] Integration tests cover OpenAPI, tool discovery, invocation, and protocol negotiation.
- [ ] Release notes were reviewed when upgrading springdoc, Spring AI, or MCP SDK.

## 22. Official References

- [springdoc-openapi Compatibility](https://github.com/springdoc/springdoc-openapi#compatibility): springdoc compatibility matrix with Spring Boot.
- [springdoc-openapi MCP Support](https://springdoc.org/mcp.html): MCP bridge, WebMVC/WebFlux modules, opt-in property, tool conversion, guardrails, and server integration.
- [springdoc-openapi v2 Documentation](https://springdoc.org/v2/): configuration for Spring Boot 3.x.
- [Spring AI Getting Started](https://docs.spring.io/spring-ai/reference/getting-started.html): Spring AI lines and Spring Boot compatibility.
- [Spring AI MCP Overview](https://docs.spring.io/spring-ai/reference/api/mcp/mcp-overview.html): MCP starters, client/server integration, and transports.
- [Spring AI MCP Server Starter](https://docs.spring.io/spring-ai/reference/api/mcp/mcp-server-boot-starter-docs.html): protocols, transports, `SYNC`/`ASYNC`, and security.
- [Spring AI MCP Modern Server](https://docs.spring.io/spring-ai/reference/api/mcp/mcp-modern-server-boot-starter-docs.html): revision `2026-07-28`, SDK 2.2.0 line requirement, and `MODERN` configuration.
- [Spring AI Upgrade Notes](https://docs.spring.io/spring-ai/reference/upgrade-notes.html): MCP SDK and package changes when upgrading to Spring AI 2.0.
- [Spring AI 2.1.0-RC2 announcement](https://spring.io/blog/2026/11/09/spring-ai-2-1-0-RC2-available-now/): prerelease status and MCP `MODERN` features.
- [MCP Specification](https://modelcontextprotocol.io/specification/2025-11-25): handshake protocol revision.
- [MCP Specification 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28): `MODERN` revision with `server/discover` and request metadata.

## Conclusion

Compatibility among springdoc, Spring AI, and MCP cannot be decided by a single version number. Select springdoc to match Spring Boot, select Spring AI on the same Boot baseline, let the Spring AI BOM manage the MCP Java SDK, and determine the MCP revision supported by both client and server. OpenAPI describes the REST contract; MCP defines how agents discover and invoke tools. The springdoc MCP bridge can convert documented operations into tools, whereas Spring AI native annotations fit agent-specific capabilities. In particular, distinguish `STATELESS` server mode from `MODERN` revision `2026-07-28`, verify documented bridge limits, and protect every MCP endpoint with real authorization. Release only after the dependency graph, protocol negotiation, tool schemas, and security integration have all been tested.
