# Observing Components in the Context Using beans

When a Spring Boot or Spring Cloud application starts, Spring creates one or more `ApplicationContext`s and registers beans from component scanning, Java configuration, auto-configuration, and enabled integrations. When the application does not behave as expected, determining which beans are actually present, which context they belong to, and which beans they depend on is often the first step of an investigation.

Spring Boot Actuator provides the **`beans`** endpoint to inspect the list of beans across application contexts. The endpoint shows the bean name, aliases, scope, type, declaring resource, and dependencies recorded by the container. It helps verify the final outcome of configuration processing, especially when multiple Spring Cloud modules contribute beans to an application.

This lesson belongs to the **Observability** chapter of the `SPRING_CLOUD_CORE` module. It focuses on enabling and reading `/actuator/beans`, understanding context and bean descriptor data structures, using that information to diagnose component scanning/auto-configuration, securing management endpoints, and distinguishing `beans` from other Actuator endpoints.

## 1. Beans and ApplicationContext in a Spring Cloud Application

A bean is an object instantiated, configured, and lifecycle-managed by the Spring IoC container. A bean can be declared via:

- `@Component`, `@Service`, `@Repository`, or `@Controller`.
- An `@Bean` method inside a `@Configuration` class.
- Spring Boot auto-configuration.
- Integrations provided by Spring Cloud or other libraries.
- Programmatic registration via container APIs.

An `ApplicationContext` is the container that holds bean definitions and manages beans for an application scope. A Spring Cloud application can have many beans coming from multiple starters: discovery client, load balancer, Config Client, refresh infrastructure, actuator endpoints, HTTP clients, and business services.

Example of a business service:

```java
@Service
public class CatalogService {

    private final CatalogRepository repository;

    public CatalogService(CatalogRepository repository) {
        this.repository = repository;
    }

    public CatalogItem findById(String id) {
        return repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Catalog item not found"));
    }
}
```

When the context initializes, Spring registers the `catalogService` bean and wires the `catalogRepository` dependency. The `beans` endpoint lets you inspect the details the container manages for these two beans.

## 2. The Spring Boot Actuator beans Endpoint

The `beans` endpoint belongs to Spring Boot Actuator, has the endpoint ID `beans`, and has the default HTTP path:

```text
GET /actuator/beans
```

To use the endpoint, add the Actuator starter to the application:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Then expose the endpoint over HTTP:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,beans
```

By default, Actuator only exposes a small set of HTTP endpoints, usually including `health`. Having the endpoint on the classpath does not mean the endpoint is exposed over HTTP. You need to distinguish:

- **Endpoint present:** Actuator has the corresponding implementation on the runtime classpath.
- **Endpoint enabled/accessible:** the endpoint policy permits using that operation according to the Spring Boot version.
- **Endpoint exposed:** the endpoint is exposed over HTTP or JMX.
- **Access permitted:** network and security allow the caller to make the request.

If the application already has a `management.endpoints.web.exposure.include` configuration, append `beans` to the existing list. Do not overwrite the active endpoint list without checking other required endpoints.

### 2.1. Calling the Endpoint

When the management server uses the same port as the application and the default base path:

```bash
curl http://localhost:8080/actuator/beans
```

You can change the base path:

```yaml
management:
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,beans
```

In that case, the URL will be `/manage/beans`.

If management endpoints run on a separate port:

```yaml
management:
  server:
    port: 9001
```

Requests go to the management port, for example `http://localhost:9001/actuator/beans`. This port should be restricted within an appropriate management network.

### 2.2. Exposing via JMX

If the operational environment uses JMX instead of HTTP, you can configure JMX exposure separately:

```yaml
management:
  endpoints:
    jmx:
      exposure:
        include: beans
```

HTTP exposure and JMX exposure are two separate mechanisms. Only expose through the management channel your organization actually uses.

## 3. Returned Data Structure

The `beans` endpoint returns information grouped by application context. Each context has an identifier, parent information if any, and a map of beans belonging to that context.

Abbreviated example:

```json
{
  "contexts": {
    "application": {
      "parentId": null,
      "beans": {
        "catalogService": {
          "aliases": [],
          "scope": "singleton",
          "type": "com.example.catalog.CatalogService",
          "resource": "class path resource [com/example/catalog/CatalogService.class]",
          "dependencies": [
            "catalogRepository"
          ]
        },
        "catalogRepository": {
          "aliases": [],
          "scope": "singleton",
          "type": "com.example.catalog.CatalogRepository",
          "resource": "class path resource [com/example/catalog/CatalogRepository.class]",
          "dependencies": []
        }
      }
    }
  }
}
```

This is an illustrative structural example, not a fixed output across all applications. Bean names, resources, and dependency lists depend on how beans are registered.

Important fields:

| Field | Meaning | How to Use |
| --- | --- | --- |
| `contexts` | Map of application contexts | Identify which context a bean belongs to |
| `parentId` | ID of the parent context if present | Understand parent/child context relationships |
| `beans` | Map of beans keyed by bean name | Locate a specific bean |
| `aliases` | Aliases of the bean | Recognize multiple names pointing to the same bean |
| `scope` | Bean scope | Distinguish singleton, prototype, request, or other scopes |
| `type` | Bean type described by the container | Verify the actual implementation |
| `resource` | Source/resource associated with the bean definition if available | Find where the bean is declared |
| `dependencies` | Bean dependencies recorded by the container | Observe direct dependency relationships |

### 3.1. Bean Names and Aliases

A bean name is the identifier used inside the container. For components, the default name is usually derived from the class name following component naming rules; for `@Bean` methods, the default name is usually the method name.

Example:

```java
@Configuration(proxyBeanMethods = false)
class CatalogConfiguration {

    @Bean
    CatalogGateway catalogGateway() {
        return new HttpCatalogGateway();
    }
}
```

The default bean name is `catalogGateway`. If declaring names or aliases:

```java
@Bean(name = {"catalogGateway", "primaryCatalogGateway"})
CatalogGateway catalogGateway() {
    return new HttpCatalogGateway();
}
```

The endpoint can display the bean name and aliases. An alias is an additional name for the same bean; it does not mean Spring created another independent object.

### 3.2. Scope

Scope indicates the lifecycle and visibility of a bean. Common values include:

- `singleton`: one instance per bean definition within a container.
- `prototype`: the container creates a new instance whenever the bean is requested through the corresponding mechanism.
- `request`: one instance per HTTP request when web scope is active.
- `session`: one instance per HTTP session.
- Custom scopes registered by the application or framework.

Do not conclude that an application has only one object across the entire JVM just because its scope is singleton. Spring's singleton is managed per container/bean definition; multiple application contexts can have singleton beans with the same name that are distinct instances.

### 3.3. Type and Resource

`type` helps identify the class/implementation seen by the container. This is useful when an interface has multiple implementations and the application unintentionally selects a different implementation than expected.

`resource` provides information about the resource associated with the bean definition if available, such as a classpath resource or declaration source. For beans created programmatically or via factories, `resource` might not directly describe the Java method location as readers might expect.

Do not rely on the resource string as a stable API for automated parsing. It is primarily for diagnostics.

### 3.4. Dependencies

`dependencies` shows the beans that the container records as dependencies of the inspected bean. For example, `catalogService` depends on `catalogRepository`.

This list is useful for understanding container-level wiring, but it is not a full call graph. It does not show every method a bean calls at runtime, every object manually instantiated with `new`, or all hidden dependencies inside libraries.

## 4. Observing the Context Hierarchy

An application can have parent and child contexts. For example, a Spring MVC application might separate a root context and a servlet context; Spring Boot may also create a separate management context in certain configurations.

The `beans` endpoint groups data by context. Illustrative example:

```json
{
  "contexts": {
    "application": {
      "parentId": null,
      "beans": {
        "catalogService": {
          "scope": "singleton",
          "type": "com.example.catalog.CatalogService",
          "dependencies": ["catalogRepository"]
        }
      }
    },
    "management": {
      "parentId": "application",
      "beans": {
        "healthEndpoint": {
          "scope": "singleton",
          "type": "org.springframework.boot.actuate.health.HealthEndpoint",
          "dependencies": []
        }
      }
    }
  }
}
```

Context names in this example are illustrative only. Read the actual IDs from the response.

### 4.1. Why Observe the Right Context?

A bean can reside in the parent context yet be accessed from a child context via Spring's bean lookup mechanism. Therefore, when locating a bean:

1. Identify which context holds the bean definition.
2. Check parent-child relationships.
3. Check whether beans with the same name exist across multiple contexts.
4. Do not treat two beans with the same name in two different contexts as a single object.

This is especially important when an application has multiple servlet contexts, a management context, or a test context hierarchy.

### 4.2. Distinguishing Duplicate Bean Names and Aliases

If a bean has two aliases, the endpoint may display the aliases inside that bean's descriptor. If the same name appears in two different contexts, those are two separate container scopes. Check the context ID before concluding that a bean was registered twice.

## 5. Using beans to Diagnose Auto-configuration

Spring Boot auto-configuration can create many beans based on classpath, properties, and existing beans. The `beans` endpoint shows the final result: which beans are actually in the context.

For example, to verify a load-balanced HTTP client:

```java
@Configuration(proxyBeanMethods = false)
class CatalogClientConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate catalogRestTemplate() {
        return new RestTemplate();
    }
}
```

After the application starts, locate the `catalogRestTemplate` bean in the response and verify its type/scope. If the bean is missing, check further:

- Was the configuration class imported or component-scanned?
- Did the configuration's conditions match?
- Are required dependencies on the runtime classpath?
- Did an initialization error prevent the context from starting cleanly?
- Was the bean created in a different context?

The `beans` endpoint only tells you whether a bean is present; it does not fully explain why an auto-configuration was skipped. Use the `conditions` endpoint or condition evaluation report to investigate matching/unmatching conditions.

### 5.1. Detecting Unexpected Implementations

Suppose the application expects to use an HTTP gateway via the `CatalogGateway` interface, yet the response shows the created bean is `StubCatalogGateway` while the environment expects an HTTP gateway. This could happen because:

- A test profile is still active.
- A feature flag property selects the stub.
- A test configuration was imported at runtime.
- Another configuration with a higher-priority condition registered the bean.

Check `type` and `resource` to locate the bean's source, then cross-reference with properties/profiles and the condition report.

### 5.2. Detecting Multiple Beans for the Same Interface

An interface can have multiple implementations coexisting. The `beans` endpoint lists bean names and types so you can determine the number of implementations.

If injection fails due to multiple candidates, inspect code for `@Qualifier`, `@Primary`, or auto-configuration conditions. `@Primary` only influences candidate selection during injection; it does not remove other beans from the context.

## 6. Reading and Filtering Results

In large applications, the `/actuator/beans` response can be quite long. You can save the output for investigation:

```bash
curl -s http://localhost:8080/actuator/beans > beans.json
```

Use `jq` to view context IDs:

```bash
jq '.contexts | keys' beans.json
```

Find a bean by name:

```bash
jq '.contexts[].beans.catalogService' beans.json
```

List bean names and types across contexts:

```bash
jq -r '.contexts | to_entries[] as $context
  | $context.value.beans | to_entries[]
  | [$context.key, .key, .value.type] | @tsv' beans.json
```

Filtering commands only help analyze received data; they do not alter the Spring context. If a bean name contains special characters, use safe map-access syntax in your JSON query tool instead of assuming every bean name is a valid identifier.

Do not store responses containing internal details in public places or attach them to external issues without reviewing them first.

## 7. Distinguishing beans from Other Actuator Endpoints

The `beans` endpoint is often used alongside other diagnostic endpoints, but each endpoint answers a specific question:

| Endpoint | Question Answered | When to Use |
| --- | --- | --- |
| `/actuator/beans` | Which beans exist in the context and how are they described? | Check bean name, type, scope, dependencies, and context |
| `/actuator/conditions` | Why did an auto-configuration/condition match or not match? | Investigate beans not created due to conditions |
| `/actuator/configprops` | Which `@ConfigurationProperties` were bound? | Inspect configurations bound into properties objects |
| `/actuator/env` | What are the property sources and Environment values? | Investigate precedence and configuration sources |
| `/actuator/mappings` | Which HTTP handler mappings are registered? | Check controllers and HTTP endpoints |
| `/actuator/health` | What status do health indicators report? | Check system and dependency health |
| `/actuator/metrics` | Which metrics are published? | Monitor operational metrics |

Examples:

- Bean does not appear: check `beans`, then `conditions`.
- Bean appears but has wrong configuration values: check `configprops` and `env`.
- Controller exists but route does not work: check `mappings`.
- Bean connects to Redis but Redis is unavailable: check `health` and connection logs.

Using the right endpoint reduces investigation time and avoids drawing conclusions from data that does not answer the question at hand.

## 8. Observing Spring Cloud Components

In a Spring Cloud application, the `beans` endpoint helps inspect component groups such as:

| Group | Example Bean Types to Look For | Diagnostic Meaning |
| --- | --- | --- |
| Discovery | DiscoveryClient implementation | Confirm provider discovery is created |
| Service registration | ServiceRegistry/Registration integration | Identify the integration managing registration |
| Load balancing | LoadBalancerClient, supplier, or client integration | Check that load balancing beans are present |
| Configuration | Config Client and property-related infrastructure | Check configuration loading components |
| Refresh | Refresh-related scope/endpoint infrastructure | Check beans supporting refresh |
| Circuit breaker | Factory/implementation integration | Identify loaded circuit breaker integration |
| Actuator | Endpoints and health contributors | Check management components |

Exact class names and bean names change across release trains, starters, and providers. Do not write scripts tightly coupled to an internal bean name if you can check by supported interface or behavior instead.

### 8.1. Checking DiscoveryClient

If the application expects Eureka or Consul but does not see the corresponding implementation, check:

- Is the discovery starter on the runtime classpath?
- Was the auto-configuration excluded?
- Did a property disable discovery?
- Is the bean in a different context?

Then use `conditions` and startup logs to find the cause. Seeing a DiscoveryClient bean does not prove the registry is reachable or returning valid instances; check health, logs, and actual discovery calls.

### 8.2. Checking LoadBalancer

If a client calls a service ID URL and hits `UnknownHostException`, the `beans` endpoint can help verify whether the load-balanced HTTP client bean and LoadBalancer components were created.

However, the bean response does not prove the request interceptor/filter processed a specific URL. You need an integration test or request trace/logs to verify actual behavior.

### 8.3. Checking Refresh Infrastructure

If the application needs refresh scope, you can look for the related infrastructure beans in the context. However, the presence of refresh infrastructure beans does not prove every configuration bean has the right scope or that properties refreshed successfully. Also inspect the target bean's scope, the refresh endpoint, logs, and configuration values after refresh.

## 9. Securing the beans Endpoint

The `beans` response can reveal:

- Internal class and package names.
- Bean names reflecting business structure.
- Dependency relationships between components.
- Resource paths or declaration locations.
- Loaded integrations and libraries.

This data is useful for operations, but it is also architectural information. Do not expose the endpoint broadly to the Internet.

### 9.1. Expose Only Necessary Endpoints

Only add `beans` to the exposure list when there is an operational need:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,beans
```

Avoid configuring `include: "*"` in production environments without fully evaluating every exposed endpoint.

### 9.2. Restrict Access with Spring Security

If the application uses Spring Security, protect Actuator endpoints with an appropriate management role. Illustrative example for a servlet application:

```java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class ActuatorSecurityConfiguration {

    @Bean
    SecurityFilterChain actuatorSecurity(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to("health"))
                    .permitAll()
                .requestMatchers(EndpointRequest.toAnyEndpoint())
                    .hasRole("ACTUATOR")
                .anyRequest()
                    .authenticated()
        );

        return http.build();
    }
}
```

This is a policy example and must be integrated with existing authentication/authorization mechanisms. When an application defines its own `SecurityFilterChain`, Actuator's default security auto-configuration may no longer apply; ensure the active chain actually protects management endpoints.

Beyond application-level security, restrict the management port using network policies, firewalls, private networks, or an authenticated reverse proxy.

### 9.3. Do Not Confuse Exposure with Authorization

`management.endpoints.web.exposure.include` determines which endpoints are exposed over HTTP. Spring Security determines who can call the endpoints. Configuring exposure does not automatically create authentication; configuring roles does not make an unexposed endpoint available.

## 10. The beans Endpoint Is Not a Full Introspection Tool

The `beans` endpoint is a diagnostic interface for container-published information. It has limitations:

- It does not dump all internal fields/values inside objects.
- It does not show every method call or the runtime call graph.
- It does not display objects manually instantiated with `new` outside the container.
- It does not prove a bean is healthy or that downstream connections succeed.
- It is not a stable API source for business logic to decide processing flows.
- It can contain large amounts of data in applications with many contexts and starters.

When you need to observe business state, use metrics, health indicators, logs, or tracing. When you need to check properties, use `env` and `configprops`. When you need to check auto-configuration conditions, use `conditions`.

Do not write production application logic that depends on parsing the `beans` response to look up an internal bean name and alter behavior. Bean names and auto-configuration structures can change when upgrading Spring Boot or starters.

## 11. Diagnostic Workflow When a Bean Does Not Appear

Suppose the application expects the `catalogClient` bean but it does not appear in the response.

1. Confirm the request hits the right application/management port and the right context of the instance under investigation.
2. Search for the `catalogClient` key in every context, not just the first context.
3. Check component scan packages or configuration imports.
4. Check whether the bean method is declared and its configuration is loaded.
5. Check profiles, properties, and `@ConditionalOnProperty`.
6. Open `/actuator/conditions` to view the auto-configuration condition report.
7. Check the runtime dependency tree if the bean comes from a starter.
8. Check startup logs for initialization errors or excluded auto-configurations.
9. If the application has a context hierarchy, determine whether the bean is in the parent or child context.
10. Write a small integration test to verify the bean is present with the corresponding properties/classpath.

Example searching for the bean in the response:

```bash
jq '.contexts | to_entries[]
  | {context: .key, bean: .value.beans.catalogClient}' beans.json
```

If the result is `null` in all contexts, the bean is not described under that name in the response. It may have another name, be created in an uninspected context, or not be registered yet. Use the type and configuration source to determine the exact name.

## 12. Diagnostic Workflow When a Bean Appears Wrong or Duplicated

If there are multiple beans for the same interface:

1. List bean names and types in each context.
2. Check aliases to distinguish aliases from independent beans.
3. Identify the scope and context containing each bean.
4. Check the configuration class creating the bean and its conditions.
5. Check `@Primary`, `@Qualifier`, and injection points.
6. Inspect the condition report if the bean comes from auto-configuration.
7. Test injection in a small context to confirm which candidate is selected.

Example filtering beans whose type relates to gateway:

```bash
jq -r '.contexts | to_entries[] as $context
  | $context.value.beans | to_entries[]
  | select(.value.type | contains("CatalogGateway"))
  | [$context.key, .key, .value.type] | @tsv' beans.json
```

Do not delete a bean simply because multiple implementations exist. Multiple implementations can be intentional by design; errors only occur when injection lacks a suitable qualifier or selection rule.

## 13. Testing Bean Observation in the Context

You do not need to call the real HTTP endpoint in every unit test. For configuration tests, you can start the context and inspect beans directly:

```java
@SpringBootTest
class CatalogContextTest {

    @Autowired
    ApplicationContext context;

    @Test
    void registersCatalogService() {
        assertThat(context.containsBean("catalogService"))
                .isTrue();

        assertThat(context.getBean("catalogService"))
                .isInstanceOf(CatalogService.class);
    }
}
```

If the goal is to verify that the Actuator endpoint is exposed, write an integration test calling the endpoint using MockMvc or an HTTP client suitable for your test setup:

```java
@SpringBootTest
@AutoConfigureMockMvc
class BeansEndpointTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exposesBeansEndpointWhenConfigured() throws Exception {
        mockMvc.perform(get("/actuator/beans"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.contexts").exists());
    }
}
```

This endpoint test example requires the Actuator dependency, configuring `beans` exposure in test properties, and appropriate security configuration. If the endpoint is secured, the test must provide proper authentication rather than disabling security in production configuration.

### 13.1. Testing Conditional Components

You can create two test contexts with different properties to verify that a bean is only registered when conditions match:

```java
@SpringBootTest(properties = "catalog.client.stub=true")
class StubCatalogContextTest {

    @Autowired
    ApplicationContext context;

    @Test
    void registersStubGateway() {
        assertThat(context.getBean(CatalogGateway.class))
                .isInstanceOf(StubCatalogGateway.class);
    }
}
```

This test verifies wiring results. If conditions do not match, inspect the `conditions` report to find the reason.

## 14. Common Errors

| Symptom | Possible Cause | Where to Check |
| --- | --- | --- |
| `/actuator/beans` returns 404 | Actuator not added, endpoint not exposed, or different base path | Check starter and `management.endpoints.web.exposure` |
| 401/403 | Security requires authentication/role | Check SecurityFilterChain and user permissions |
| Expected bean not seen | Component scan, import, or condition did not match | Check `conditions`, profiles, and packages |
| Bean seen but different type | Implementation selected by another profile/condition | Check `type`, `resource`, and properties |
| Bean name appears multiple times | Bean is in multiple contexts or duplicate registration configuration | Check context ID, aliases, and configuration |
| Dependencies unclear | Dependency list is not a full call graph | Check constructor, `@Bean` method, and code |
| Configured property not seen | Looking at the wrong endpoint | Use `env` or `configprops` |
| Unsure why auto-configuration skipped bean | Beans only shows the final result | Use `conditions` |
| Response too large | Application has many beans/contexts | Filter JSON with jq and query the right context |
| Management port unreachable | Separate port blocked or wrong port called | Check `management.server.port` and network policy |
| Singleton bean has multiple copies | Multiple ApplicationContexts have separate bean definitions | Check context hierarchy and scope |

Brief investigation sequence:

1. Confirm the right endpoint and context.
2. Check bean name, alias, type, scope, and dependencies.
3. Cross-reference the context hierarchy.
4. Use `conditions` if the bean is not created.
5. Use `env`/`configprops` if properties affect configuration.
6. Check logs and health when the bean is present but malfunctions.
7. Review security and management network if the endpoint is unreachable.

## 15. Practice: Inspecting Catalog Beans in a Spring Cloud Application

Suppose an application has the following components:

- `CatalogService` handles business logic.
- `CatalogRepository` accesses data.
- `CatalogGateway` calls another catalog service.
- `DiscoveryClient` looks up instances.
- Load-balanced `RestTemplate` calls by service ID.

### Step 1 — Add Actuator

Add `spring-boot-starter-actuator` to the application dependencies and align versions via Spring Boot dependency management.

### Step 2 — Expose beans in Local/Test Environments

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,beans
```

Do not expose this endpoint publicly in production without security and network controls.

### Step 3 — Start the Application and Retrieve the List

```bash
curl -s http://localhost:8080/actuator/beans > beans.json
```

### Step 4 — Inspect Business Beans

```bash
jq '.contexts[].beans.catalogService' beans.json
jq '.contexts[].beans.catalogRepository' beans.json
```

Confirm bean name, type, scope, and dependencies.

### Step 5 — Inspect Spring Cloud Integrations

Locate discovery/load balancer beans by type or actual name in the response. If the expected implementation is missing, check dependencies and the condition report.

### Step 6 — Inspect the Context Hierarchy

```bash
jq '.contexts | to_entries[] | {id: .key, parentId: .value.parentId}' beans.json
```

Identify which context holds the bean. If the same name appears in multiple contexts, verify whether it is an intentional separate context configuration or an unintended duplicate registration.

### Step 7 — Verify Endpoint Security

Verify that only administrative users/roles can read the endpoint and the management port is not exposed outside the management network. Do not save outputs containing architectural details into public artifacts.

### Self-Check Questions

1. What is the Spring Boot Actuator `beans` endpoint used to observe?
2. Which dependency provides Actuator endpoints?
3. Why might adding the Actuator starter still not allow calling `/actuator/beans` over HTTP?
4. What do `contexts` and `parentId` help understand?
5. What do the `aliases`, `scope`, `type`, `resource`, and `dependencies` fields mean?
6. Is an alias a new bean instance?
7. Why can singletons in two ApplicationContexts be two distinct instances?
8. Does the `beans` endpoint show all runtime method calls?
9. Which endpoint is used to find out why an auto-configuration did not match?
10. When you need to view bound properties, which endpoint should you use?
11. Why must the `beans` endpoint be protected?
12. When should you use an integration test instead of only reading Actuator output?

**Suggested answers:** (1) The list of beans by application context and their descriptors; (2) `spring-boot-starter-actuator`; (3) Because the endpoint must be exposed over HTTP and permitted for access; (4) Relationships between parent/child contexts; (5) Aliases, scope, type, declaring resource, and container-recorded dependencies; (6) No, an alias is another name for the same bean; (7) Singletons are managed per container; (8) No, the endpoint is not a call graph; (9) `conditions`; (10) `configprops` or `env` depending on the question; (11) Because it reveals class names, packages, bean structure, and internal relationships; (12) When you need to verify lifecycle/context isolation or actual runtime behavior rather than just viewing current state.

## 16. Key Principles to Remember

- Actuator's `beans` endpoint shows the beans managed by Spring in each ApplicationContext.
- You need to add the Actuator starter, expose the endpoint, and configure appropriate access permissions.
- Bean descriptors may contain aliases, scope, type, resource, and dependencies.
- Context ID and parent ID help distinguish beans across parent/child contexts.
- Aliases do not create new bean instances; singletons are managed per container.
- The `beans` endpoint describes the container, not a call graph or health report.
- Use `conditions` to investigate auto-configuration, `env`/`configprops` to inspect properties, `mappings` to inspect HTTP routes, and `health` to check dependency status.
- In Spring Cloud, the endpoint helps verify that discovery, load balancer, config, and refresh infrastructure beans were created; it does not prove those integrations are operating properly.
- Only expose the endpoint on a management network and restrict it with authentication/authorization.
- Use integration tests to verify bean wiring and actual request behavior; never let business logic depend on parsing endpoint output.

Observing beans with `/actuator/beans` reveals the actual wiring result of the Spring container instead of merely inferring from source code. When combined with `conditions`, `env`, `configprops`, and logs, operators can clearly pinpoint which beans were created, which context they belong to, and whether further investigation belongs at the configuration or runtime layer.

## References

- [Spring Boot Reference — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot Reference — Exposing Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.exposing)
- [Spring Boot API — BeansEndpoint](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/beans/BeansEndpoint.html)
- [Spring Framework Reference — The IoC Container](https://docs.spring.io/spring-framework/reference/core/beans.html)
