# Adding a Customizer to Modify Behavior Without Replacing the Entire Bean in Spring Boot

## 1. Problem: Needing to Add Behavior While Keeping Default Configuration

A Spring Boot library typically pre-creates beans so an application can use them immediately: an HTTP client, ObjectMapper, task executor, cache manager, or a specialized library client. After integration, each application may need to tweak a few behaviors:

- Add default headers to an HTTP client.
- Register a serializer or module for JSON.
- Add a custom interceptor, retry policy, or timeout.
- Change the thread name prefix or shutdown settings of an executor.
- Add a codec for a protocol.

If users had to re-declare the entire bean just to alter one small setting, they would have to duplicate default configuration, manage dependencies manually, and take responsibility for updates when the library changes. That approach easily loses integrations Spring Boot already supplies such as message converters, observation, metrics, SSL, resource management, or conditional configurations.

A **Customizer** is an extension point that lets an application contribute a callback to adjust a builder or object that auto-configuration is creating. Auto-configuration still owns the bean creation process and preserves defaults; the customizer modifies only the behavior it cares about.

## 2. What Is a Customizer?

A customizer is usually a single-method callback interface that receives a target object and modifies some settings on that object.

Example contract:

~~~java
@FunctionalInterface
public interface ClientBuilderCustomizer {
    void customize(ClientBuilder builder);
}
~~~

A bean implementing this interface can add a header:

~~~java
@Bean
ClientBuilderCustomizer applicationHeader() {
    return builder -> builder.defaultHeader(
            "X-Application", "catalog-service");
}
~~~

Auto-configuration collects the customizers, applies them to the builder, and only then calls build to create the client.

A good customizer has a narrow, predictable scope:
- Only changes settings within its responsibility.
- Does not create a replacement bean in the Spring container.
- Does not perform network calls or database access inside the callback.
- Does not retain the builder to mutate it at an indeterminate time after the bean has been created.
- Does not assume there is only one customizer in the application.

A customizer is an extension contract; it is not an automatic Java mechanism. Each subsystem must define its target type, invocation timing, and ordering rules.

## 3. Distinguishing Customizers, Configuration Properties, and Bean Replacement

These three mechanisms address different needs:

| Mechanism | Appropriate when | Example |
| --- | --- | --- |
| `@ConfigurationProperties` | Users need to change common, stable options expressible as configuration | Base URL, timeout, pool size, cache TTL |
| Customizer | Users need to add advanced behavior that the library has not exposed as properties | Adding interceptors, serializers, headers, codecs |
| Declaring a bean of the same type | Users need a substantially different implementation or lifecycle | Using a different client, custom factory, replacing the entire ObjectMapper |

A practical rule of thumb: properties are for configuration choices the library wants to support officially; customizers are for intentional extension points; bean overrides are for cases where the application wants to own the implementation.

Do not create a property for every method of a third-party library. Neither should you force users to replace an entire bean just to add a single interceptor.

## 4. Spring Boot Already Provides Many Built-In Customizers

Before designing a new interface yourself, check whether the subsystem already has a suitable extension point.

| Customizer | Target object | Purpose |
| --- | --- | --- |
| `RestClientCustomizer` | `RestClient.Builder` | Add shared configuration for RestClient |
| `WebClientCustomizer` | `WebClient.Builder` | Add shared configuration for WebClient |
| `Jackson2ObjectMapperBuilderCustomizer` | `Jackson2ObjectMapperBuilder` | Adjust ObjectMapper while keeping auto-configuration |
| `ThreadPoolTaskExecutorCustomizer` | `ThreadPoolTaskExecutor` | Adjust the executor created from the builder |
| `RSocketStrategiesCustomizer` | `RSocketStrategies.Builder` | Add codecs or encoding/decoding strategies |

These interfaces are callback beans. The subsystem's auto-configuration accepts them and applies them to the corresponding object.

Key reminder: not every customizer receives a builder. For instance, `ThreadPoolTaskExecutorCustomizer` receives a `ThreadPoolTaskExecutor` instance, whereas `RestClientCustomizer` receives a `RestClient.Builder`. Read the contract of the exact interface before choosing lifecycle and testing strategies.

## 5. Choosing the Customization Scope

A change can apply at different scopes:

1. **Single instance:** configure only one client or bean at its usage site.
2. **All builders supplied by Spring Boot:** register a shared customizer bean in the ApplicationContext.
3. **Entire implementation:** replace the bean or subsystem configuration completely.

For example, if only one client needs a specific base URL, inject the builder and call `baseUrl(...)` in the service creating the client. If all RestClients need the same application identification header, use `RestClientCustomizer`.

For `WebClient.Builder` and `RestClient.Builder`, builders are stateful. Changes on a builder affect clients subsequently built from that exact builder. When needing multiple clients with distinct configurations, clone the builder before modifying it so one client's settings do not bleed into another.

## 6. Designing a Custom Customizer for a Library

Suppose a library provides `WidgetClient` to call an external service. The library's builder supports:
- `baseUrl(...)` to set the service address.
- `defaultHeader(...)` to add headers.
- `requestInterceptor(...)` to add request processing.
- `build()` to create the final client.

The library defines a public extension point in the autoconfigure module:

~~~java
package com.acme.widget.autoconfigure;

import com.acme.widget.client.WidgetClient;

@FunctionalInterface
public interface WidgetClientBuilderCustomizer {

    void customize(WidgetClient.Builder builder);
}
~~~

This contract has one clear goal: let the application adjust `WidgetClient.Builder` before auto-configuration builds `WidgetClient`.

Place the interface in the autoconfigure module or an API module accessible to consuming applications. Do not leave the interface only in an unexported internal package if users must declare beans implementing it.

## 7. Auto-Configuration Applies All Customizers Before Building

Auto-configuration can collect multiple beans of the same type using `ObjectProvider`:

~~~java
package com.acme.widget.autoconfigure;

import com.acme.widget.client.WidgetClient;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(WidgetClient.class)
@EnableConfigurationProperties(WidgetClientProperties.class)
public class WidgetClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(WidgetClient.class)
    WidgetClient widgetClient(
            WidgetClientProperties properties,
            ObjectProvider<WidgetClientBuilderCustomizer> customizers) {

        WidgetClient.Builder builder = WidgetClient.builder()
                .baseUrl(properties.getBaseUrl());

        customizers.orderedStream()
                .forEach(customizer -> customizer.customize(builder));

        return builder.build();
    }
}
~~~

Bean creation flow:

1. Spring Boot reads properties and creates the default configuration for the builder.
2. `ObjectProvider.orderedStream()` retrieves `WidgetClientBuilderCustomizer` beans in Spring order.
3. Each callback adjusts the same builder for this client creation.
4. Auto-configuration calls `build()` once to create `WidgetClient`.
5. `@ConditionalOnMissingBean` ensures the default client is created only when the application has not provided a bean of the same type.

If there are no customizers, the stream is empty and the client is still created from default configuration. There is no need to declare a no-op customizer just to populate the list.

This is an architectural example: `WidgetClient`, `WidgetClientProperties`, and the builder methods are illustrative library APIs. When applying to a real library, substitute that client's actual contracts.

## 8. Applications Contributing Multiple Independent Customizers

Each requirement can be packaged into its own bean:

~~~java
@Configuration(proxyBeanMethods = false)
class WidgetClientCustomizationConfiguration {

    @Bean
    @Order(10)
    WidgetClientBuilderCustomizer applicationHeader() {
        return builder -> builder.defaultHeader(
                "X-Application", "catalog-service");
    }

    @Bean
    @Order(20)
    WidgetClientBuilderCustomizer tenantHeader() {
        return builder -> builder.defaultHeader(
                "X-Tenant", "north");
    }
}
~~~

The two customizers do not need to know about each other. One bean adds application info, the other adds tenant info. Auto-configuration collects both and applies them in order.

Spring orders beans implementing `Ordered` or annotated with `@Order`; lower order values are applied first. If two customizers modify the same setting, the outcome depends on how the builder handles calls and callback order. For instance, if `defaultHeader` replaces the previous value of the same header, a callback running later can overwrite the earlier value.

Specify order only when a genuine relationship exists between steps. Avoid using order as an implicit mechanism to resolve configuration conflicts without clear explanation.

## 9. Properties Should Be Applied Before Customizers

Auto-configuration should apply stable properties first, and then invoke customizers so the application has a chance to make finer adjustments.

For example:

~~~java
WidgetClient.Builder builder = WidgetClient.builder()
        .baseUrl(properties.getBaseUrl())
        .connectTimeout(properties.getConnectTimeout())
        .readTimeout(properties.getReadTimeout());

customizers.orderedStream()
        .forEach(customizer -> customizer.customize(builder));

return builder.build();
~~~

This sequence creates a consistent baseline:
- Properties express the default configuration officially supported by the library.
- Customizers can add interceptors or tweak advanced options.
- `build()` produces the final instance after all callbacks finish.

If a customizer overrides a value already set by a property, treat that as intentional override behavior. Document clearly so users understand which configuration source takes precedence.

Do not apply customizers after building if the customizer contract expects a builder. Once the object is built, changes may have no effect or require implementation-specific mutation APIs.

## 10. Real-World Example: RestClientCustomizer

Spring Boot 3.3 provides `RestClientCustomizer` in package `org.springframework.boot.web.client`. This interface receives `RestClient.Builder`.

~~~java
import org.springframework.boot.web.client.RestClientCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class RestClientConfiguration {

    @Bean
    RestClientCustomizer applicationIdentityHeader() {
        return builder -> builder.defaultHeader(
                "X-Application", "orders-service");
    }
}
~~~

A service uses the Boot-supplied builder:

~~~java
@Service
class CatalogGateway {

    private final RestClient client;

    CatalogGateway(RestClient.Builder builder) {
        this.client = builder
                .baseUrl("https://catalog.example.test")
                .build();
    }
}
~~~

Boot creates and configures `RestClient.Builder` with appropriate message converters and request factory. The customizer bean adds the header to auto-configured builders. The service only needs to choose a base URL and build the client.

If calling `RestClient.create()` directly, Boot's auto-configuration path and `RestClientCustomizer` are not applied. Therefore, when you want to benefit from Boot's shared configuration, inject the auto-configured builder.

## 11. WebClientCustomizer Example and Stateful Builders

`WebClientCustomizer` in package `org.springframework.boot.web.reactive.function.client` receives `WebClient.Builder`.

~~~java
@Bean
WebClientCustomizer correlationHeader() {
    return builder -> builder.defaultHeader(
            "X-Correlation-Source", "billing");
}
~~~

The builder can be injected where the client is created:

~~~java
@Service
class BillingGateway {

    private final WebClient client;

    BillingGateway(WebClient.Builder builder) {
        this.client = builder
                .baseUrl("https://billing.example.test")
                .build();
    }
}
~~~

Spring Boot documentation notes that `WebClient.Builder` is stateful: any changes to the builder affect clients subsequently created from that builder. If the same place needs multiple clients with distinct settings, clone before customizing:

~~~java
WebClient.Builder billingBuilder = builder.clone();
WebClient.Builder identityBuilder = builder.clone();

WebClient billingClient = billingBuilder
        .baseUrl("https://billing.example.test")
        .build();

WebClient identityClient = identityBuilder
        .baseUrl("https://identity.example.test")
        .build();
~~~

If calling `WebClient.create()` directly, Boot's auto-configuration and customizers are not applied.

## 12. Jackson Example: Adding Configuration While Keeping Default ObjectMapper

Spring Boot provides `Jackson2ObjectMapperBuilderCustomizer`. This interface lets you adjust `Jackson2ObjectMapperBuilder` while preserving the default auto-configuration process.

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

@Configuration(proxyBeanMethods = false)
class JacksonCustomizationConfiguration {

    @Bean
    @Order(10)
    Jackson2ObjectMapperBuilderCustomizer omitNullProperties() {
        return builder -> builder.serializationInclusion(
                JsonInclude.Include.NON_NULL);
    }
}
~~~

Spring Boot has an internal customizer with order `0`. A customizer at order `10` is applied after that customizer. Thus, the application can add its own rules while still using the Boot-managed builder and JSON integrations.

If you declare your own `ObjectMapper` bean or your own `Jackson2ObjectMapperBuilder` bean to replace the default configuration, Spring Boot stops auto-configuring ObjectMapper via the standard mechanism. Choose a customizer when you only need to change a few serialization rules.

## 13. ThreadPoolTaskExecutorCustomizer Example

Spring Boot 3.3 includes `ThreadPoolTaskExecutorCustomizer` in package `org.springframework.boot.task`. The callback receives a `ThreadPoolTaskExecutor` instance.

~~~java
import org.springframework.boot.task.ThreadPoolTaskExecutorCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class ExecutorCustomizationConfiguration {

    @Bean
    ThreadPoolTaskExecutorCustomizer executorShutdownPolicy() {
        return executor -> {
            executor.setWaitForTasksToCompleteOnShutdown(true);
            executor.setAwaitTerminationSeconds(20);
        };
    }
}
~~~

Boot's `ThreadPoolTaskExecutorBuilder` supports adding customizers to configure the created executor. This customizer adjusts the executor instance while the builder configures it.

Do not confuse this interface with a callback receiving a builder. Its contract is `customize(ThreadPoolTaskExecutor taskExecutor)`, so code operates directly on the executor instance.

## 14. When Are Customizers Applied and When Are They Skipped?

Applicability depends on how the object is created:

| Object creation path | Is auto-configuration customizer applied? |
| --- | --- |
| Inject Boot-auto-configured builder then call `build()` | Yes, if the subsystem integrates customizers |
| Library auto-configuration accepts customizer beans and invokes callbacks | Yes |
| Call `RestClient.create()` or `WebClient.create()` directly | Auto-configured builder customizers are not applied |
| Application declares a complete client bean itself | Default bean backs off; default factory customizers do not run automatically on the application bean |
| Create builder manually via constructor/standalone API | Not automatically; must invoke customizers manually if reusing the contract |

The last point is crucial when writing libraries. Merely having a customizer bean in the context does not mean Spring will automatically find every object of that type and modify it. An auto-configuration or factory must actively collect and invoke the callbacks.

## 15. How Customizers Interact with @ConditionalOnMissingBean

An auto-configuration typically creates a default bean using:

~~~java
@Bean
@ConditionalOnMissingBean(WidgetClient.class)
WidgetClient widgetClient(...) {
    // Create default client and apply customizers
}
~~~

When the application registers a `WidgetClientBuilderCustomizer`, the default bean is still created and the callback is applied.

When the application registers its own `WidgetClient` bean, the `@ConditionalOnMissingBean` condition no longer matches. The default factory does not run, so customizers intended for that factory's builder do not automatically affect the application-created bean.

This behavior is intentional:
- Customizer: the application wants to keep the library's factory and defaults, only adding behavior.
- Bean override: the application wants full ownership of the object and how it is constructed.

If an application creates its own bean yet still wants to reuse customizers, it can create a builder and invoke the callbacks following the appropriate contract. However, consider using a public builder bean or factory to avoid duplicating default creation logic.

## 16. Do Not Use BeanPostProcessor Instead of an Intentional Customizer

`BeanPostProcessor` can intercept beans after container initialization or before they are put into service. It is a broad extension point with lifecycle implications.

Using a general `BeanPostProcessor` just to add a header to one client type is often confusing:
- Its impact can be broader than the beans the library intends to support.
- The point of intervention is hard to spot at the bean declaration site.
- Proxies or post-processor ordering can alter behavior.
- Tests must cover both lifecycle and object replacement.

A dedicated customizer makes the target type and adjustment timing explicit. Use `BeanPostProcessor` only when you genuinely need to intervene in the lifecycle of many beans under a general rule, not to replace a simple builder callback.

## 17. Designing Customizers for Maintainability

A public extension point needs a stable contract:

- **Name the target clearly:** e.g. `WidgetClientBuilderCustomizer`, not a generic interface named `Customizer`.
- **Keep methods simple:** a single `customize(...)` callback suffices for most cases.
- **Do not leak internal implementations:** expose only APIs users need for configuration.
- **Separate by subsystem:** HTTP clients, caches, and executors should have distinct customizers if they have different lifecycles.
- **Support multiple beans:** design for a collection of callbacks instead of injecting only one instance.
- **Define ordering:** use `Ordered` or `@Order` when order matters and explain what happens when two customizers modify the same setting.
- **Preserve defaults:** apply properties and internal configuration before callbacks, then build the object last.
- **Document scope:** state clearly whether the customizer affects one instance, all Boot-created builders, or one specific bean factory.

A customizer should not grant power to mutate everything in the container. It should open only the exact point the library intends to support.

## 18. Testing Customizers with ApplicationContextRunner

For auto-configuration libraries, `ApplicationContextRunner` helps test default beans and callbacks without starting the entire application.

Example testing that a customizer is applied:

~~~java
class WidgetClientAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    WidgetClientAutoConfiguration.class))
                    .withPropertyValues(
                            "acme.widget.base-url=https://widget.example.test");

    @Test
    void appliesCustomizerAndKeepsDefaultClient() {
        runner.withBean(
                WidgetClientBuilderCustomizer.class,
                () -> builder -> builder.defaultHeader(
                        "X-Test-Mode", "enabled"))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(WidgetClient.class);

                    WidgetClient client =
                            context.getBean(WidgetClient.class);

                    assertThat(client.defaultHeaders())
                            .containsEntry("X-Test-Mode", "enabled");
                    assertThat(client.baseUrl())
                            .isEqualTo("https://widget.example.test");
                });
    }
}
~~~

This test verifies:
- Auto-configuration still creates a single default client bean.
- The customizer is discovered and invoked before `build()`.
- The header is added.
- The base URL from properties is preserved.

Additional tests can be added:
- No customizers: client is still created with defaults.
- Two customizers: both changes appear.
- Two customizers modifying the same setting: verify ordering and final outcome.
- User provides a custom client bean: default bean backs off.
- Optional dependency absent: auto-configuration does not create clients depending on that class.

Note: the `WidgetClient` example and `defaultHeaders()`/`baseUrl()` accessors are illustrative APIs. Adapt assertions to your library's actual API.

## 19. Standalone Java 17 Example to Understand Callbacks

The following program models the customizer idea in pure Java. It has a builder, two independent callbacks, and a final build step. The program does not use Spring; the Spring-specific part is the container automatically discovering and ordering customizer beans.

File `CustomizerDemo.java`:

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class CustomizerDemo {

    record BuiltClient(String baseUrl, Map<String, String> headers) {
    }

    static final class ClientBuilder {

        private String baseUrl;
        private final Map<String, String> headers = new LinkedHashMap<>();

        ClientBuilder baseUrl(String baseUrl) {
            this.baseUrl = Objects.requireNonNull(baseUrl);
            return this;
        }

        ClientBuilder defaultHeader(String name, String value) {
            headers.put(name, value);
            return this;
        }

        BuiltClient build() {
            if (baseUrl == null) {
                throw new IllegalStateException("baseUrl is required");
            }
            return new BuiltClient(baseUrl, Map.copyOf(headers));
        }
    }

    @FunctionalInterface
    interface ClientCustomizer {
        void customize(ClientBuilder builder);
    }

    public static void main(String[] args) {
        List<ClientCustomizer> customizers = List.of(
                builder -> builder.defaultHeader(
                        "X-Application", "catalog-service"),
                builder -> builder.defaultHeader(
                        "X-Request-Mode", "safe")
        );

        ClientBuilder builder = new ClientBuilder()
                .baseUrl("https://api.example.test");

        customizers.forEach(customizer -> customizer.customize(builder));

        BuiltClient client = builder.build();

        System.out.println(client.baseUrl());
        System.out.println(client.headers().get("X-Application"));
        System.out.println(client.headers().get("X-Request-Mode"));
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac CustomizerDemo.java
java CustomizerDemo
~~~

Exact stdout:

~~~text
https://api.example.test
catalog-service
safe
~~~

Two customizers add two headers on the same builder. There is no need to create a new client for each change and no need to rewrite the base URL configuration.

In Spring Boot, `ObjectProvider.orderedStream()` handles collecting and sorting callbacks from the ApplicationContext. The callback and builder concept in the plain Java program remains the same.

## 20. Common Pitfalls and Diagnostics

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Customizer bean exists in context but has no effect | Factory does not collect or invoke customizers | Check auto-configuration and the bean creation method |
| Default bean disappears after adding customizer | Customizer mistakenly declared with target bean type or wrong condition | Use a separate customizer interface, keep `@ConditionalOnMissingBean` on target bean |
| Customizer does not run for application-created bean | Default factory backed off | Apply customizer in the application's factory or use a shared builder/factory |
| Only one of multiple customizers applied | Code injects a single callback instead of a collection/provider | Use `ObjectProvider.orderedStream()` or collection injection |
| Result changes when adding another customizer | Multiple callbacks modify the same setting | Specify `@Order`, separate responsibilities, or remove conflicts |
| Headers/interceptors appear multiple times | Callback applied repeatedly or builder reused | Create a separate builder per instance and inspect callback invocation sites |
| One client receives another client's base URL | Shared stateful builder | Clone the builder before per-client customization |
| Customizer runs yet final bean is unchanged | Callback invoked after build or on the wrong builder | Apply callbacks before `build()` |
| Used `RestClient.create()` and missing shared headers | Bypassed Boot's auto-configured builder | Inject `RestClient.Builder` and build client from the builder |
| ObjectMapper loses Boot defaults | Declared replacement ObjectMapper/builder | Use `Jackson2ObjectMapperBuilderCustomizer` if only tweaking settings |
| Order is not as expected | Missing `Ordered`/`@Order` or two callbacks conflict | Assign explicit order and test ordering |
| Context fails to start when customizer needs target bean | Customizer injects final client while factory is building client | Customizers should accept only builders or unfinished targets, avoiding circular dependency |

## 21. Checklist Before Releasing a Customizer API

1. Identify exactly which bean or builder is allowed to be customized.
2. Check whether the subsystem already has a Spring Boot-provided customizer interface.
3. Define a dedicated interface whose name accurately reflects the target.
4. Expose the interface in a module consumers can depend on.
5. Apply properties and defaults before invoking customizers.
6. Collect all callbacks, not just a single bean.
7. Support ordering with `Ordered`/`@Order` if order is meaningful.
8. Invoke callbacks before creating the final instance.
9. Keep `@ConditionalOnMissingBean` on the default bean so users can override when truly needed.
10. Verify customizers do not lose defaults, observation, metrics, or message converters.
11. Test zero customizers, one customizer, multiple customizers, and user bean override.
12. Document clearly which builders/instances the customizer applies to and which creation paths bypass it.

## 22. Self-Check Questions

1. What is a customizer used for? **Allows adding behavior to a builder or object during creation while preserving existing factories/defaults.**
2. When should properties be used? **When it is a common, stable configuration option needing official support.**
3. When should a customizer be used? **When needing an advanced extension point or additional callback without replacing the entire bean.**
4. What object does `RestClientCustomizer` receive? **`RestClient.Builder`.**
5. What benefit does `Jackson2ObjectMapperBuilderCustomizer` preserve? **It lets you adjust the Jackson builder while keeping Boot's default auto-configuration.**
6. Does `ThreadPoolTaskExecutorCustomizer` receive a builder or an instance? **It receives a `ThreadPoolTaskExecutor` instance.**
7. What does `ObjectProvider.orderedStream()` solve? **Collects customizer beans and iterates them in Spring order.**
8. Does `@Order(10)` run before or after `@Order(0)`? **After; lower order values are applied first.**
9. Do customizers automatically run on beans declared manually by the application? **No; the factory must invoke callbacks.**
10. Why should stateful builders be cloned when creating multiple clients? **So per-client settings of one client do not affect another.**
11. Why should `BeanPostProcessor` not be used for every small customization? **It intervenes broadly in lifecycle and makes impact scope harder to see than a dedicated callback.**
12. When should you replace a bean completely? **When the application needs a substantially different implementation or lifecycle and accepts owning the configuration.**

## Official References

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): autoconfigure modules can publish callback interfaces so applications can customize initialized components.
- [Spring Boot 3.3 — Calling REST Services](https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html): using WebClient/RestClient builders, customizer beans, scope of application, and stateful builders.
- [Spring Boot 3.3.13 — RestClientCustomizer JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/client/RestClientCustomizer.html): callback for `RestClient.Builder`.
- [Spring Boot 3.3.13 — WebClientCustomizer JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/reactive/function/client/WebClientCustomizer.html): callback for `WebClient.Builder`.
- [Spring Boot 3.3.13 — Jackson2ObjectMapperBuilderCustomizer JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jackson/Jackson2ObjectMapperBuilderCustomizer.html): customizing Jackson builder while preserving default auto-configuration.
- [Spring Boot 3.3.13 — ThreadPoolTaskExecutorCustomizer JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/task/ThreadPoolTaskExecutorCustomizer.html): callback for `ThreadPoolTaskExecutor`.
- [Spring Boot 3.3.13 — ThreadPoolTaskExecutorBuilder JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/task/ThreadPoolTaskExecutorBuilder.html): builder and customizers applied to executors.
