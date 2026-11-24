# MockMvcConfigurer for Scoped Integration

`MockMvcConfigurer` is Spring MVC Test's extension point for attaching a group of shared settings to a `MockMvc` created from a builder. It is useful when multiple requests in the same test suite need common filters, request context, or default behavior, while those settings should apply only to selected `MockMvc` instances.

The key point is that a configurer's scope is tied to the builder on which `.apply(...)` is called. A configurer does not automatically register itself into every `ApplicationContext`, does not become an application-wide filter, and does not affect real requests passing through a servlet container. It customizes the `MockMvc` build process and the requests executed through that instance.

## 1. Where `MockMvcConfigurer` Fits in Building MockMvc

Spring MVC Test provides two common ways to build `MockMvc`:

| Builder Method | Configuration Source | Suitable When |
|---|---|---|
| `MockMvcBuilders.webAppContextSetup(context)` | A loaded `WebApplicationContext` | Testing integration with MVC configuration, controllers, converters, advice, interceptors, and beans in the context |
| `MockMvcBuilders.standaloneSetup(controllers...)` | Controllers and components declared directly on the builder | Needing a narrow slice, explicitly configuring the components participating in the test |

Both return a builder that can accept a configurer via `.apply(...)`:

```java
MockMvc mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .apply(myConfigurer)
        .build();
```

The builder determines which components participate in `MockMvc`. `MockMvcConfigurer` adds or adjusts configuration on that exact builder. Consequently, two tests can share the same `ApplicationContext` yet build two `MockMvc` instances with different integrations.

## 2. Two Hooks in a Configurer's Lifecycle

`MockMvcConfigurer` has two methods:

```java
public interface MockMvcConfigurer {

    void afterConfigurerAdded(ConfigurableMockMvcBuilder<?> builder);

    RequestPostProcessor beforeMockMvcCreated(
            ConfigurableMockMvcBuilder<?> builder,
            WebApplicationContext context);
}
```

Each hook has a distinct timing and purpose.

### `afterConfigurerAdded`

Spring calls this method when the configurer is attached to the builder via `.apply(...)`. The configurer can use the builder to add filters or shared settings for `MockMvc`.

For example, a test suite needs to ensure requests pass through a character encoding filter:

```java
import org.springframework.test.web.servlet.setup.ConfigurableMockMvcBuilder;
import org.springframework.test.web.servlet.setup.MockMvcConfigurer;
import org.springframework.web.filter.CharacterEncodingFilter;
import org.springframework.test.web.servlet.request.RequestPostProcessor;
import org.springframework.web.context.WebApplicationContext;

final class Utf8MockMvcConfigurer implements MockMvcConfigurer {

    @Override
    public void afterConfigurerAdded(ConfigurableMockMvcBuilder<?> builder) {
        builder.addFilters(new CharacterEncodingFilter("UTF-8", true));
    }

    @Override
    public RequestPostProcessor beforeMockMvcCreated(
            ConfigurableMockMvcBuilder<?> builder,
            WebApplicationContext context) {
        return null;
    }
}
```

When this configurer is applied, the filter is added to the filter chain used by `MockMvc`. It is not thereby registered into a servlet container running outside tests. If the filter was already added by the builder or test configuration, do not add it a second time because duplicate filters can produce confusing behavior.

### `beforeMockMvcCreated`

Spring calls this method right before creating `MockMvc`. The method receives the builder and `WebApplicationContext`, and can return a `RequestPostProcessor`.

The `RequestPostProcessor` is applied to requests executed through that `MockMvc`. This is the right place to add default information to requests such as a tenant id, locale, or a request attribute used in the test environment.

For example, a group of tests needs to send the same tenant header:

```java
import java.util.Objects;

import org.springframework.test.web.servlet.request.RequestPostProcessor;
import org.springframework.test.web.servlet.setup.ConfigurableMockMvcBuilder;
import org.springframework.test.web.servlet.setup.MockMvcConfigurer;
import org.springframework.web.context.WebApplicationContext;

final class TenantHeaderConfigurer implements MockMvcConfigurer {

    private final String tenantId;

    TenantHeaderConfigurer(String tenantId) {
        this.tenantId = Objects.requireNonNull(tenantId);
    }

    @Override
    public void afterConfigurerAdded(ConfigurableMockMvcBuilder<?> builder) {
        // No builder modifications needed in this hook.
    }

    @Override
    public RequestPostProcessor beforeMockMvcCreated(
            ConfigurableMockMvcBuilder<?> builder,
            WebApplicationContext context) {

        return request -> {
            request.addHeader("X-Tenant-Id", this.tenantId);
            return request;
        };
    }
}
```

The `RequestPostProcessor` receives `MockHttpServletRequest`, modifies the request, and returns that same request. The configurer does not have to construct requests itself nor modify each `mockMvc.perform(...)` call.

## 3. Applying a Configurer to a Specific MockMvc

Suppose a controller reads the tenant id from a header:

```java
@RestController
class OrderController {

    @GetMapping("/orders/{id}")
    OrderView findOrder(
            @PathVariable long id,
            @RequestHeader("X-Tenant-Id") String tenantId) {
        return new OrderView(id, tenantId);
    }
}

record OrderView(long id, String tenantId) {
}
```

A test can build `MockMvc` with a default tenant for all requests:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.web.SpringJUnitWebConfig;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.webAppContextSetup;

@SpringJUnitWebConfig(WebConfig.class)
class OrderControllerTests {

    @Autowired
    WebApplicationContext context;

    MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = webAppContextSetup(context)
                .apply(new TenantHeaderConfigurer("tenant-test"))
                .build();
    }

    @Test
    void usesTheConfiguredTenant() throws Exception {
        mockMvc.perform(get("/orders/{id}", 42))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.tenantId").value("tenant-test"));
    }
}
```

`WebConfig` here is the application's MVC configuration or a test configuration registering `OrderController`. The example highlights the integration point: the configurer is applied when building the builder, so requests going through `mockMvc` receive the tenant header without repeating the header in every test.

If another group of tests needs a different tenant, that group can create its own `MockMvc`:

```java
MockMvc anotherTenantMvc = webAppContextSetup(context)
        .apply(new TenantHeaderConfigurer("tenant-another"))
        .build();
```

The two instances share the same context while keeping separate request configurations. Applying a configurer to the second builder does not alter the configuration of the previously built `MockMvc`.

## 4. Using Built-In Configurers from Libraries

Not every configurer has to be written by hand. Libraries can provide `MockMvcConfigurer` implementations to integrate with `MockMvc` through this exact builder mechanism.

A common example is Spring Security Test. When building `MockMvc` manually with `WebApplicationContext`, you can apply `springSecurity()`:

```java
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;

MockMvc mockMvc = MockMvcBuilders
        .webAppContextSetup(context)
        .apply(springSecurity())
        .build();
```

Spring Security's configurer integrates the security filter chain with `MockMvc` and enables the library's request post-processor utilities. Tests can then simulate users or authentication details per request, for example:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;

mockMvc.perform(get("/profile").with(user("alice")))
        .andExpect(status().isOk());
```

Here there are two configuration scopes:

- `.apply(springSecurity())` integrates Spring Security into the `MockMvc` built from that builder.
- `.with(user("alice"))` provides an identity for a specific request.

Distinguishing these two scopes keeps tests clear: security configuration is integrated once per instance; per-scenario identity or data is specified on the corresponding request.

## 5. Configurer Scope and Reuse Patterns

The scope of a `MockMvcConfigurer` is determined by where it is applied:

| Where Applied | Scope of Effect |
|---|---|
| `.apply(configurer)` on a single builder | The `MockMvc` created from that builder |
| Applying the same configurer to multiple builders | Each `MockMvc` created from an applied builder |
| Using the configurer inside a MockMvc factory helper | The instances created by that helper |
| Merely declaring the configurer as a bean in the context | Not automatically applied to every `MockMvc` builder |

An immutable configurer holding only configuration values such as a tenant id or pre-built filter can usually be reused across multiple builders. If a configurer holds mutable state while requests run, consider creating separate instances per `MockMvc`, especially when tests run in parallel. Do not store current-request data in shared fields of a configurer because multiple requests may execute concurrently.

You can create a factory to avoid repeating setup:

```java
final class TestMockMvcFactory {

    private TestMockMvcFactory() {
    }

    static MockMvc forTenant(WebApplicationContext context, String tenantId) {
        return MockMvcBuilders.webAppContextSetup(context)
                .apply(new TenantHeaderConfigurer(tenantId))
                .build();
    }
}
```

This factory makes the scope of application visible at the call site:

```java
MockMvc mockMvc = TestMockMvcFactory.forTenant(context, "tenant-test");
```

Only create a factory when multiple tests genuinely share the same `MockMvc` construction convention. For a single test, calling `.apply(...)` directly is usually easier to read.

## 6. When to Use `MockMvcConfigurer` vs. Other Mechanisms

Not every MockMvc configuration needs a dedicated configurer. Choose the extension point based on the scope of the behavior:

| Need | Appropriate Mechanism |
|---|---|
| Add filters or configure the builder for a group of MockMvc instances | `MockMvcConfigurer` and `.apply(...)` |
| Add a header, principal, or data to a specific request | `RequestPostProcessor` via `.with(...)` |
| Assert on the response of a specific request | `ResultMatcher` via `.andExpect(...)` |
| Run an action after a specific request | `ResultHandler` via `.andDo(...)` |
| Default settings on a builder within a test suite | `defaultRequest(...)` or an appropriate configurer |
| Customize MockMvc auto-created by Spring Boot | Spring Boot builder customization mechanism, such as `MockMvcBuilderCustomizer` |

### `MockMvcConfigurer` and `RequestPostProcessor`

These two APIs are related but do not replace each other:

- `MockMvcConfigurer` participates during `MockMvc` construction; it can adjust the builder and provide a shared request post-processor.
- `RequestPostProcessor` modifies a single request directly. Tests can attach it with `.with(...)` without defining a configurer.

If only one test needs a header or user, using `.with(...)` directly is usually simpler. If every request through a `MockMvc` needs the same setup, a configurer can consolidate that rule in one place.

### `MockMvcConfigurer` and Spring Boot Auto-Configuration

In tests using `@SpringBootTest` with `@AutoConfigureMockMvc`, Spring Boot creates `MockMvc` itself and manages the builder. Declaring a bean of type `MockMvcConfigurer` does not mean that bean is automatically `.apply(...)`ed to the builder.

If you need to customize a builder managed by Spring Boot, use Boot's extension point such as `MockMvcBuilderCustomizer`. If you explicitly call `MockMvcBuilders.webAppContextSetup(...)` or `standaloneSetup(...)`, you can apply `MockMvcConfigurer` directly. Pick a single owner for configuration to avoid adding the same filter or request processor twice.

## 7. Common Mistakes

### Expecting a Configurer to Affect Every MockMvc

A configurer takes effect only when applied to a builder. Creating a class implementing `MockMvcConfigurer` or registering it as a bean does not automatically make all tests use it. Check where builders are constructed and ensure `.apply(...)` is called at the right spot.

### Confusing Request Post-Processors with Filters

`RequestPostProcessor` modifies the simulated request before it is processed. Filters participate in the servlet processing chain. If you need to test filter behavior, add the filter to the builder or integrate it via an appropriate configurer; modifying a request with a post-processor does not prove a filter ran.

### Adding Filters Multiple Times

A filter may already be added by application configuration, test configuration, or another configurer. Adding the filter again can run logic twice or alter processing order. Check where filters are registered before adding them to the builder.

### Using a Stateful Shared Configurer in Parallel Tests

Do not keep `currentTenant`, `currentUser`, or mutable request data in shared fields and update those fields before each request. Two concurrent requests can overwrite each other's state. Use immutable configurers to supply defaults, or pass per-request data using `.with(...)`.

### Putting Too Much Behavior into One Configurer

A single configurer bundling security, tenant, locale, mock clock, and multiple unrelated filters makes it hard to tell which configuration drives a behavior. Split by meaningful responsibility and apply only what each `MockMvc` needs.

### Treating `MockMvc` as a Real Server

`MockMvc` simulates the Spring MVC processing flow in a test environment. Filters added via the builder belong to that MockMvc's filter chain; they do not prove that deployment configuration on an external servlet container or reverse proxy is correct. Container-dependent properties must be tested at the appropriate integration tier.

## 8. Workflow for Designing a Scoped Configurer

When an integration needs to be shared across a group of tests, follow this sequence:

1. Identify the behavior to share: filters, request metadata, security integration, or other builder settings.
2. Identify exactly which tests or `MockMvc` instances need that behavior.
3. Choose the right hook: `afterConfigurerAdded` to modify the builder; `beforeMockMvcCreated` to supply a request post-processor that can access the context.
4. Write the configurer with immutable configuration and narrow responsibility.
5. Attach it to the builder with `.apply(...)` where `MockMvc` is created.
6. Test a representative request to confirm the integration actually takes effect.
7. If another test needs different settings, create a separate builder or `MockMvc` instead of mutating a shared configurer's state.
8. Check existing filters and customizers to avoid duplicate registration.

## 9. References

- [Spring Framework Reference — Setup Options](https://docs.spring.io/spring-framework/reference/testing/mockmvc/setup-options.html): how to build `MockMvc` with `webAppContextSetup` and `standaloneSetup`.
- [Spring Framework Javadoc — `MockMvcConfigurer`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/web/servlet/setup/MockMvcConfigurer.html): contract and two hooks of the configurer.
- [Spring Framework Javadoc — `ConfigurableMockMvcBuilder`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/web/servlet/setup/ConfigurableMockMvcBuilder.html): builder configuration methods.
- [Spring Security Reference — MockMvc Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): how to integrate Spring Security with `springSecurity()`.
- [Spring Boot API — `MockMvcBuilderCustomizer`](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/autoconfigure/web/servlet/MockMvcBuilderCustomizer.html): builder extension point in Spring Boot test auto-configuration.

`MockMvcConfigurer` helps encapsulate a reusable integration and attach it to the exact `MockMvc` instances that need it. Use the builder hook for shared setup, the request post-processor for request data, and place `.apply(...)` where the instance is built so the scope of effect always stays clear.
