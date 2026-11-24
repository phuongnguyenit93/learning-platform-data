# Dependency Conditions and Explicit Opt-In Mechanism of MCP Integration

Springdoc-openapi can convert REST operations described in OpenAPI into MCP tools for AI agents to discover and invoke. However, adding the MCP dependency to the classpath does not mean the MCP endpoint is exposed immediately. This integration uses an opt-in mechanism: the application must set the `springdoc.ai.mcp.enabled=true` property.

This condition separates three decisions: whether the MCP library is present in the dependency graph, whether the application explicitly enables MCP, and whether the admin dashboard is opened. Understanding each condition helps prevent unintentionally widening the integration surface, and makes it easier to diagnose why a bean or endpoint was not registered.

This lesson focuses on the right dependency for WebMVC/WebFlux, the property enabling MCP, auto-configuration conditions, environment profiles, the dashboard, security, testing enabled/disabled states, and diagnosing the condition report.

## Objectives

After this lesson, you will be able to:

- Distinguish the presence of the MCP starter from MCP integration being enabled.
- Choose the right starter for Spring MVC or Spring WebFlux.
- Configure `springdoc.ai.mcp.enabled` explicitly.
- Understand the default `false` value starting in Springdoc 3.1.1.
- Separate enabling the MCP server from enabling the Developer Dashboard.
- Use profiles and environment variables to enable the integration per environment.
- Understand the roles of `@ConditionalOnClass`, `@ConditionalOnProperty`, and `@ConditionalOnMissingBean`.
- Check startup preloading and timeouts when MCP is enabled.
- Protect MCP endpoints with Spring Security.
- Test missing dependency, missing property, `false`, and `true` cases.
- Diagnose auto-configuration using `--debug` and Actuator conditions.

## 1. What Does Springdoc's MCP Integration Do?

Springdoc MCP integration bridges OpenAPI and the Model Context Protocol. It reads operations described on `@RestController` classes, converts OpenAPI metadata into tool definitions, and exposes an MCP endpoint for compatible clients to discover and invoke tools.

Information from OpenAPI is used to build tools:

- `operationId` becomes the default tool name, normalized to fit tool naming rules.
- `summary` and `description` provide explanatory text for AI agents.
- Parameters and request bodies are converted into the input JSON Schema.
- The controller's first tag is used to group tools in the dashboard.
- `@McpToolDescription` can provide a tailored description specifically for agents.

This integration uses existing REST endpoints in the application. Enabling MCP does not create new business logic in controllers; it creates an interface for MCP clients to discover and call the operations registered in the tool registry.

## 2. Choosing the Dependency by Web Stack

Springdoc provides separate starters for Spring MVC and Spring WebFlux. Add only the starter matching the application's web stack.

### 2.1. Spring MVC / Servlet

For applications using `spring-boot-starter-web`, add:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-mcp</artifactId>
    <version>SPRINGDOC_VERSION</version>
</dependency>
~~~

### 2.2. Spring WebFlux / Reactive

For applications using `spring-boot-starter-webflux`, add:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-mcp</artifactId>
    <version>SPRINGDOC_VERSION</version>
</dependency>
~~~

`SPRINGDOC_VERSION` is a placeholder in the Maven example; replace it with the version managed by your project or use the Springdoc BOM if the project already imports it.

Do not add both starters just to experiment. Pick the module matching the actual web runtime, avoiding pulling both Servlet and Reactive integrations into the same application unless the architecture requires it.

### 2.3. Checking Spring Boot Compatibility

MCP starters were introduced in the Springdoc 3.x line. Current Springdoc 3.2.0 documentation presents starters for Spring Boot 4. If an application is running Spring Boot 3 with Springdoc 2.x, do not upgrade just the MCP starter to 3.x to get this feature; the Springdoc major version and Spring Boot major version must be compatible per the compatibility matrix.

Before adding the dependency, check:

- The Spring Boot and Spring Framework versions in use.
- The Springdoc version supported for that Spring Boot version.
- The matching starter for WebMVC or WebFlux.
- The Spring AI/MCP dependencies resolved via the starter's dependency management.

Do not force a different major version of Spring AI or Springdoc onto the classpath without inspecting the dependency tree.

## 3. Dependency Presence Does Not Mean MCP Is Enabled

Starting in Springdoc 3.1.1, MCP integration is opt-in. The `springdoc.ai.mcp.enabled` property defaults to `false`. When only the starter is added without enabling the property:

- MCP tool integration is not registered.
- The default MCP endpoint `/mcp` is not opened.
- The MCP dashboard is not created.
- Existing REST endpoints and OpenAPI documentation continue working per their own configuration.

Enable the integration in `application.yml`:

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

When the property is `true`, Springdoc builds the tool registry from OpenAPI and registers the MCP surface for the matching web module. If the property is absent or `false`, MCP integration is not registered.

This is a critical distinction between:

| Condition | Meaning |
|---|---|
| MCP starter is in the dependency graph | MCP classes and auto-configuration can be loaded |
| `springdoc.ai.mcp.enabled=true` | The application permits Springdoc to register MCP integration |
| `springdoc.ai.mcp.dashboard-enabled=true` | The application also enables the Developer Dashboard |

## 4. Understanding Auto-Configuration Conditions

Spring Boot auto-configuration uses conditions to decide which beans are registered. MCP integration requires matching classes on the classpath and the property enabling the feature.

### 4.1. Classpath Condition

`@ConditionalOnClass` checks whether a class exists on the classpath. This is how libraries keep integrations optional: if an application lacks the MCP module, configuration depending on MCP should not be loaded.

General example:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(OptionalMcpApi.class)
class OptionalMcpConfiguration {
    // Beans are only valid when the optional API is on the classpath
}
~~~

`OptionalMcpApi` is an illustrative name for a class from an optional integration. When writing your own auto-configuration, you can use `name = "fully.qualified.OptionalMcpApi"` to avoid forcing the JVM to load the optional type directly in certain configuration structures.

### 4.2. Property Condition

`@ConditionalOnProperty` checks values in the Spring `Environment`. For an extension that should only run when MCP is enabled, you can write:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "springdoc.ai.mcp",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
class MyMcpExtensionConfiguration {

    @Bean
    PropertyConditionMarker propertyConditionMarker() {
        return new PropertyConditionMarker();
    }
}

record PropertyConditionMarker() {
}
~~~

`matchIfMissing = false` makes clear that if the property is missing, the extension is not registered. This is also the default behavior of `@ConditionalOnProperty`, though declaring it explicitly signals to readers that this is an opt-in feature.

### 4.3. Bean Condition

`@ConditionalOnBean` and `@ConditionalOnMissingBean` inspect beans already registered in the context. They are commonly used to let applications replace a default bean with a custom bean.

Example:

~~~java
@Bean
@ConditionalOnMissingBean
MyMcpExtensionMarker myMcpExtensionMarker() {
    return new MyMcpExtensionMarker();
}
~~~

Place bean conditions on auto-configurations that load after user-declared beans. Bean definition registration order can affect condition evaluation results.

Do not confuse `@ConditionalOnMissingBean` with the MCP enablement switch. It only decides whether to create a default bean; `springdoc.ai.mcp.enabled` is the setting that turns Springdoc's MCP integration on or off.

## 5. Enabling MCP by Profile

Not every environment should expose MCP. Keep it disabled by default and enable it only in a profile intended for environments that need AI agents.

`application.yml`:

~~~yaml
springdoc:
  ai:
    mcp:
      enabled: false
~~~

`application-mcp.yml`:

~~~yaml
springdoc:
  ai:
    mcp:
      enabled: true
      dashboard-enabled: true
~~~

Run with the profile:

~~~bash
SPRING_PROFILES_ACTIVE=mcp java -jar app.jar
~~~

On PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "mcp"
java -jar app.jar
~~~

Spring Boot will load `application-mcp.yml` when the `mcp` profile is active. In container environments, you can set the environment variable directly:

~~~text
SPRINGDOC_AI_MCP_ENABLED=true
~~~

The decision to enable MCP should live in controlled deployment configuration. Do not enable it across all environments just because the dependency is already inside the image.

## 6. Enabling the Dashboard Independently from the MCP Server

The MCP server and the Developer Dashboard are two separate components. When MCP integration is enabled, the dashboard still remains disabled by default. To enable the admin UI, configure:

~~~yaml
springdoc:
  ai:
    mcp:
      enabled: true
      dashboard-enabled: true
      dashboard-path: /mcp-ui
~~~

Default endpoints:

| Component | Default Path |
|---|---|
| MCP server | `/mcp` |
| Developer Dashboard | `/mcp-ui` |
| Dashboard REST API | `/api/mcp-admin/**` |

If only remote MCP clients need to connect, there is no need to enable the dashboard. If you enable the dashboard, protect both the UI page and its REST API.

You can change the MCP endpoint with `springdoc.ai.mcp.mcp-endpoint` and the dashboard path with `springdoc.ai.mcp.dashboard-path`. When changing them, update both MCP client configuration and security matchers together.

## 7. Preloading and Initialization Conditions at Startup

The MCP tool registry is built from the OpenAPI specification. Therefore, when MCP is enabled, Springdoc automatically forces `springdoc.pre-loading-enabled=true` so the OpenAPI document is ready at startup.

Related properties:

| Property | Default | Role |
|---|---:|---|
| `springdoc.ai.mcp.enabled` | `false` | Enables MCP integration |
| `springdoc.ai.mcp.init-timeout-seconds` | `30` | Timeout waiting for OpenAPI spec at startup |
| `springdoc.ai.mcp.base-url` | `http://localhost:8080` | Base URL for HTTP calls executing tools |
| `springdoc.ai.mcp.mcp-endpoint` | `/mcp` | Path of the MCP server |
| `springdoc.ai.mcp.paths-to-exclude` | empty | Path patterns excluded from tool generation |
| `springdoc.ai.mcp.dashboard-enabled` | `false` | Enables the dashboard |

If an application has many controllers, customizers, or slow OpenAPI generation, startup time may increase when MCP is enabled because the document must be generated early. Monitor startup duration and adjust `init-timeout-seconds` when justified by real environment metrics.

`springdoc.ai.mcp.base-url` is the address used when an MCP tool calls back into the REST API. If the application runs behind a reverse proxy or inside a container, determine an address reachable by the MCP process; do not default to the public URL if an internal service URL is more appropriate.

## 8. Excluding Paths from MCP Tool Generation

Not every REST operation should be handed to AI agents. You can use:

~~~yaml
springdoc:
  ai:
    mcp:
      enabled: true
      paths-to-exclude:
        - /internal/**
        - /admin/**
        - /actuator/**
~~~

`paths-to-exclude` uses Ant-style path patterns and only filters operations out of MCP tool generation. It does not remove endpoints from the default OpenAPI document, does not block HTTP requests, and does not replace Spring Security or gateway policies.

If a path is excluded from MCP, users can still call that route via REST if the route is exposed and the caller has permission. Manage permissions at the API layer separately.

## 9. Protecting MCP Endpoints

MCP endpoints form an integration surface capable of discovering and invoking APIs. Springdoc does not provide built-in authentication/authorization for them; the application must apply Spring Security or equivalent controls.

Paths to consider together:

- `/mcp`: MCP server endpoint.
- `/mcp-ui/**`: Developer Dashboard.
- `/api/mcp-admin/**`: Dashboard REST API.

Example dedicated filter chain for MCP:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class McpSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain mcpSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher(
                "/mcp",
                "/mcp-ui/**",
                "/api/mcp-admin/**"
            )
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().hasRole("MCP_ADMIN")
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

This example illustrates authority checks. In a real application, integrate matchers into your existing authentication strategy, pick roles/scopes appropriate for MCP clients, and check `SecurityFilterChain` ordering. If the transport uses `POST`, evaluate CSRF according to your authentication mechanism and how clients send tokens; do not disable CSRF application-wide just to get MCP working.

Human-in-the-Loop (HITL) in MCP guardrails is a confirmation step before executing an operation that can mutate data. It is not authentication, not authorization, and does not replace security filters.

## 10. Guardrails When Tools Can Mutate Data

Springdoc MCP classifies tools by HTTP method:

| Default Classification | HTTP Methods |
|---|---|
| Safe/read-only | `GET`, `HEAD`, `OPTIONS` |
| Mutating | `POST`, `PUT`, `DELETE`, `PATCH`, and other methods |

By default, `springdoc.ai.mcp.guardrails.require-approval-for-mutating-tools=true`. When an agent calls a mutating tool, the server returns a response requesting approval instead of executing the HTTP call immediately.

Configurable via:

~~~yaml
springdoc:
  ai:
    mcp:
      guardrails:
        require-approval-for-mutating-tools: true
        safe-methods: GET,HEAD,OPTIONS
~~~

To disable the approval requirement:

~~~yaml
springdoc:
  ai:
    mcp:
      guardrails:
        require-approval-for-mutating-tools: false
~~~

Consider this configuration only when the environment already has proper access controls and operational safeguards. A `GET` endpoint can still alter state if an API is poorly designed; you can override classification in `McpToolCustomizer` according to a reviewed policy.

Do not treat guardrails as a security boundary. Anyone who can reach the MCP endpoint can also invoke the approval API via the provided mechanism; access control must still be enforced in application security.

## 11. Conditions for Application Extension Beans

If the application adds its own `McpToolCustomizer`, tool metadata, or MCP helper beans, place them behind the same MCP-enabled condition. Otherwise, extensions may be created when MCP integration is disabled or cause startup failures when the MCP starter is absent from the classpath.

Example with an application-owned extension bean:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "springdoc.ai.mcp",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
class MyMcpExtensionConfiguration {

    @Bean
    MyMcpExtensionMarker myMcpExtensionMarker() {
        return new MyMcpExtensionMarker();
    }
}
~~~

If an extension directly references classes from the MCP starter, also place `@ConditionalOnClass` on a separate configuration class. That ensures the application can still start without the MCP module.

Springdoc provides extension points such as `McpToolCustomizer` to rename tools, change descriptions, modify input schemas, or exclude tools from the registry. You can use `@McpToolDescription` on controller methods to supply descriptions meant for AI agents. These extensions only take effect when MCP integration is enabled.

### Tool Grouping Depends on OpenAPI Metadata

Springdoc uses `operationId` as the default tool name and the controller's first tag to group tools. Therefore, if an operation lacks a clear `operationId` or tag, names and groups in the MCP dashboard can be hard to understand.

Before enabling MCP, verify:

- Every operation intended for exposure has a clear `operationId`.
- `summary`/`description` explains the tool's purpose and constraints.
- Request parameters and request bodies are describable with schemas.
- Controllers have appropriate tags so the dashboard groups tools cleanly.
- Internal or sensitive operations are filtered out of tool generation.

## 12. Key MCP Properties to Know

MCP properties live under the `springdoc.ai.mcp` prefix and take effect only when the application includes the appropriate MCP starter.

| Property | Default | Purpose |
|---|---|---|
| `springdoc.ai.mcp.enabled` | `false` | Enables/disables MCP tool integration |
| `springdoc.ai.mcp.base-url` | `http://localhost:8080` | Base URL for HTTP tool execution calls; if unset, uses localhost with the server port |
| `springdoc.ai.mcp.init-timeout-seconds` | `30` | Timeout waiting for the OpenAPI spec at startup |
| `springdoc.ai.mcp.paths-to-exclude` | empty | List of path patterns excluded from conversion to MCP tools |
| `springdoc.ai.mcp.mcp-endpoint` | `/mcp` | Path of the MCP server |
| `springdoc.ai.mcp.dashboard-enabled` | `false` | Enables the Developer Dashboard |
| `springdoc.ai.mcp.dashboard-path` | `/mcp-ui` | Path of the dashboard |
| `springdoc.ai.mcp.guardrails.require-approval-for-mutating-tools` | `true` | Requires confirmation before mutating tools |
| `springdoc.ai.mcp.guardrails.safe-methods` | `GET,HEAD,OPTIONS` | HTTP methods treated as read-only by default |
| `springdoc.ai.mcp.audit.redact` | `true` | Masks values with secret-like names in audit events |

If the dashboard is enabled, audit events appear in the dashboard and are logged via the MCP audit logger. Keep redaction enabled unless the audit sink is a trusted store with access controls. Never put tokens, passwords, or sensitive data in tool descriptions or examples.

## 13. Testing Enable/Disable Conditions for Extensions

`ApplicationContextRunner` is well suited for testing application-owned optional configurations on the JVM. Example creating a marker bean that exists only when MCP is enabled:

~~~java
@Configuration(proxyBeanMethods = false)
class OptionalMcpExtensionConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "springdoc.ai.mcp",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
    )
    McpExtensionMarker mcpExtensionMarker() {
        return new McpExtensionMarker();
    }
}

record McpExtensionMarker() {
}
~~~

Test the missing property, `false`, and `true` cases:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class OptionalMcpExtensionConfigurationTests {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(
                OptionalMcpExtensionConfiguration.class
            );

    @Test
    void missingPropertyKeepsExtensionDisabled() {
        runner.run(context ->
            assertThat(context)
                .doesNotHaveBean(McpExtensionMarker.class)
        );
    }

    @Test
    void falseKeepsExtensionDisabled() {
        runner.withPropertyValues(
            "springdoc.ai.mcp.enabled=false"
        ).run(context ->
            assertThat(context)
                .doesNotHaveBean(McpExtensionMarker.class)
        );
    }

    @Test
    void trueRegistersExtension() {
        runner.withPropertyValues(
            "springdoc.ai.mcp.enabled=true"
        ).run(context ->
            assertThat(context)
                .hasSingleBean(McpExtensionMarker.class)
        );
    }
}
~~~

This tests the application's extension configuration; it does not replace integration tests for the Springdoc MCP starter. `ApplicationContextRunner` is a JVM auto-configuration testing tool; do not use it as a native-image integration test.

### MCP Integration Test Matrix

Beyond extension beans, verify the actual starter according to this matrix:

| MCP Starter | Property | Dashboard | Expected Result |
|---|---|---|---|
| Absent | Any | Any | No MCP integration |
| Present | Unset | Not enabled | MCP disabled by default |
| Present | `false` | Not enabled | MCP server not registered |
| Present | `true` | Not enabled | MCP server and tool registry registered |
| Present | `true` | `true` | MCP server and dashboard registered |

When enabled, use a compatible MCP client/test harness to send `initialize`, then call `tools/list` and verify expected operations appear. Do not merely issue a `GET` to `/mcp` and conclude the server works; Streamable HTTP transport has its own request/response rules.

## 14. Diagnosing Auto-Configuration

When the property is enabled yet MCP beans or endpoints do not appear, inspect auto-configuration conditions before writing manual beans.

Run the application with `--debug`:

~~~bash
java -jar app.jar --debug
~~~

Spring Boot prints the condition evaluation report, showing which auto-configurations matched or were skipped and why. If Actuator is present, you can expose the `conditions` endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,conditions
~~~

Then inspect `/actuator/conditions`. This endpoint exposes sensitive configuration details about application internals; protect it with Spring Security and expose it only in appropriate operational environments.

Check in order:

1. Does the dependency tree include the right MCP starter?
2. Does the starter match WebMVC or WebFlux?
3. Is the Springdoc major version compatible with the Spring Boot major version?
4. Does the active `Environment` actually have `springdoc.ai.mcp.enabled=true`?
5. Which profile is active and which configuration file overrides the property?
6. Does the condition report indicate a class or property condition mismatch?
7. Was OpenAPI preloaded and completed before `init-timeout-seconds`?
8. Do security matchers block the MCP endpoint or dashboard?

## 15. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Added MCP starter yet `/mcp` is missing | `springdoc.ai.mcp.enabled` is not set to `true` | Enable the property in the right profile |
| Property `springdoc.mcp.enabled` has no effect | Wrong prefix | Use `springdoc.ai.mcp.enabled` |
| Dashboard missing even though MCP runs | `dashboard-enabled` defaults to `false` | Enable the dashboard explicitly if truly needed |
| App fails to start with MCP classes | Wrong starter added or incompatible dependency version | Select WebMVC/WebFlux starter and version per compatibility matrix |
| Tool list is empty | Controllers not scanned/described or OpenAPI lacks matching operations | Check `/v3/api-docs`, package/path scanning, and operation metadata |
| Cryptic tool names | Missing or unstable `operationId` | Set explicit `operationId` values |
| Tool group falls into `Other` | Controller missing tag | Add an appropriate `@Tag` |
| Internal tools still appear | `paths-to-exclude` or custom filter not configured | Filter tools and protect runtime routes |
| MCP startup timeout | Slow OpenAPI generation or base configuration not ready | Check preload logs and adjust timeout with evidence |
| Dashboard returns 401/403 | Security chain requires permissions | Grant appropriate role/scope for operators |
| MCP endpoint accessible without login | Endpoint not protected in Spring Security | Protect `/mcp`, `/mcp-ui/**`, and `/api/mcp-admin/**` |
| Mutating tool requests approval yet remains unsafe | HITL mistaken for authorization | Check identity and permissions in the application layer |

## 16. Environment-Based Deployment Workflow

A controlled deployment workflow:

1. Confirm compatible Spring Boot and Springdoc versions.
2. Choose the MCP starter matching the web stack.
3. Keep `springdoc.ai.mcp.enabled=false` in default configuration.
4. Set `true` only in approved profiles or environments.
5. Start with the dashboard disabled; enable only when operationally needed.
6. Determine a `base-url` reachable by tool execution.
7. Exclude internal/sensitive paths from the tool registry.
8. Add authentication/authorization for MCP and dashboard endpoints.
9. Keep mutating approval guardrails enabled unless another policy exists.
10. Test `initialize` and `tools/list` with an MCP client.
11. Inspect startup logs, condition reports, and audit redaction.
12. Monitor startup time and tool invocation errors after release.

Do not enable MCP in production just to try the dashboard. Use a test profile or an integration environment with restricted access.

## 17. Comprehensive Hands-On Exercise

Build a Spring Boot application with `ProductController` and MCP integration:

1. Identify whether the application uses Spring MVC or WebFlux.
2. Add the matching `springdoc-openapi-starter-webmvc-mcp` or `springdoc-openapi-starter-webflux-mcp`.
3. Confirm the dependency version is compatible with Spring Boot.
4. Start with `springdoc.ai.mcp.enabled` undeclared and verify MCP is not registered.
5. Set `springdoc.ai.mcp.enabled=false` and verify it remains disabled.
6. Set the property to `true` in the `mcp` profile.
7. Call MCP `initialize` and `tools/list` to verify tools generated from the controller.
8. Enable the dashboard with `dashboard-enabled=true` and inspect `/mcp-ui`.
9. Configure `paths-to-exclude` to exclude `/admin/**`.
10. Add Spring Security rules for `/mcp`, `/mcp-ui/**`, and `/api/mcp-admin/**`.
11. Verify mutating tools return an approval request per the default guardrail.
12. Run the application with `--debug` and read the condition report.
13. Write `ApplicationContextRunner` tests for the extension bean when the property is missing, `false`, and `true`.
14. Include dependency, property, and security configuration checks in the CI pipeline.

### Completion Criteria

- [ ] Selected the right MCP starter for WebMVC/WebFlux.
- [ ] Understand that having the MCP starter on the classpath does not auto-enable MCP integration.
- [ ] Configured `springdoc.ai.mcp.enabled=true` explicitly.
- [ ] Understand the `false` default starting from Springdoc 3.1.1.
- [ ] Separated the dashboard from the MCP server via `dashboard-enabled`.
- [ ] Understand preloading is enabled when MCP integration is enabled.
- [ ] Know how to use `@ConditionalOnProperty` for extension beans.
- [ ] Checked dependency and property conditions in the condition report.
- [ ] MCP tools contain only intended operations.
- [ ] `/mcp`, `/mcp-ui/**`, and `/api/mcp-admin/**` are protected.
- [ ] HITL is not used as a substitute for authorization.
- [ ] Tests cover missing, `false`, and `true` property states.

## Continuing Further

After this lesson, combine MCP enablement with `McpToolCustomizer`, `@McpToolDescription`, tool grouping, schema conversion, and audit logging. Adding the dependency only provides the integration capability; the decision to expose MCP tools must be expressed in configuration, verified with condition tests, and protected at the application layer.

## References

- [Springdoc MCP Support](https://springdoc.org/#mcp-support)
- [Springdoc MCP properties](https://springdoc.org/#springdoc-openapi-mcp-properties)
- [Springdoc releases – MCP integration](https://github.com/springdoc/springdoc-openapi/releases)
- [Spring Boot – Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot – ConditionalOnProperty API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html)
- [Spring Boot – Troubleshooting Auto-configuration](https://docs.spring.io/spring-boot/how-to/application.html)
