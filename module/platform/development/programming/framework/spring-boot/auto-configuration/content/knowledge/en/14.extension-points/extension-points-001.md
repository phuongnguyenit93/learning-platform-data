# Customizers and builders: customizing beans while preserving Spring Boot's default configuration

## 1. Objective and problem statement

Spring Boot **Auto-configuration** does not only provide an application with the necessary beans. It also establishes many important defaults: HTTP message converters, how the HTTP request factory is selected, JSON support, observability when the corresponding infrastructure is present, SSL, property-based configuration, and other integrated components.

When you need to add a small change, for example:
- Every internal HTTP client sends the `X-App-Client` header.
- An HTTP client calling an external API uses its own `baseUrl`.
- JSON omits `null` fields.
- A `RestTemplate` has a dedicated timeout for a specific service.
- A starter library wants to add shared behavior while still allowing the application to change it.

The solution is usually to **leverage the builder provided by Boot** or **register a customizer bean supported by Boot**. These two mechanisms allow modifying part of the behavior while still inheriting the underlying configuration.

Central principle:

> Obtain the builder already auto-configured by Spring Boot, or contribute a customizer that auto-configuration knows how to apply. Only replace the entire builder/bean when you genuinely need deeper control.

This lesson uses primary examples with **Spring Boot 3.5.x, Java 17+**. The APIs and packages of several classes changed in Spring Boot 4.x; therefore, the import names and configuration style in this lesson are explicitly tied to the 3.5 line.

## 2. Three concepts to distinguish

### 2.1. Builder

A **Builder** is an object that creates another object after the user configures options. For example:

~~~java
// Illustrative example; not a standalone Java program.
RestClient client = restClientBuilder
        .baseUrl("https://catalog.example.test")
        .defaultHeader("X-Team", "catalog")
        .build();
~~~

`RestClient.Builder` holds the configuration to produce a `RestClient`. Spring Boot 3.5 can create a **pre-configured** builder bean via `RestClientAutoConfiguration`.

If you only need to change `baseUrl` for one client, you configure the injected builder and call `build()` instead of creating everything from scratch.

### 2.2. Customizer

A **Customizer** is a callback that receives a builder or the object being configured, and then performs a clearly scoped modification. Example in Spring Boot 3.5:

~~~java
import org.springframework.boot.web.client.RestClientCustomizer;
import org.springframework.context.annotation.Bean;

// Place the method in a @Configuration or @SpringBootApplication class.
@Bean
RestClientCustomizer addClientHeader() {
    return builder -> builder.defaultHeader("X-Team", "catalog");
}
~~~

When creating **`RestClient.Builder` via auto-configuration**, Boot applies the registered `RestClientCustomizer` beans. This makes it possible to add a header without copying all the underlying HTTP configuration.

Not every interface named `*Customizer` is automatically found and applied by Spring Boot to every object. A customizer only takes effect **if the appropriate auto-configuration or builder actually collects and invokes it**.

### 2.3. Configurer

A **Configurer** is a helper class that knows how to apply Spring Boot's defaults to a builder you create. Example `RestClientBuilderConfigurer` from Boot 3.5:

~~~java
import org.springframework.boot.autoconfigure.web.client.RestClientBuilderConfigurer;
import org.springframework.web.client.RestClient;

// Illustrative snippet inside a configuration class.
RestClient.Builder configured =
        configurer.configure(RestClient.builder());
~~~

This is an important mechanism when you are forced to define a builder bean yourself. It helps avoid missing defaults that you cannot see from a single `new` or `builder()` line.

## 3. Auto-configuration flow and extension points

Simplified model:

~~~text
Classpath + Environment + application beans
                      |
                      v
   Matching auto-configuration is activated
                      |
                      v
     Boot prepares default configuration
          /        |           \
         v         v            v
  HTTP factory  Converters   Observability/SSL...
          \        |           /
           \       v          /
       Builder configured by Boot
                      |
                      v
       Matching customizers are applied
                      |
                      v
    Application code adds local customization
                      |
                      v
                  build()
                      |
                      v
                Bean/client used
~~~

The diagram is a mental model and does not strictly describe the internal callback order for every type of builder. The exact ordering among customizers depends on the framework, the extension point, and `@Order`/`Ordered` if supported.

**Key terms to remember:**
- **Defaults:** provided by the framework and standard properties.
- **Additive customization:** adding only the parts you need.
- **Replacement:** providing your own bean/builder, which may cause auto-configuration to stop creating the default object due to `@ConditionalOnMissingBean`.
- **Scope:** whether the customization applies to a single client or to all clients using the same kind of builder.

## 4. Choosing the right customization approach

| Goal | Preferred approach | Scope |
| --- | --- | --- |
| Change URL and headers for one HTTP client | Inject `RestClient.Builder`, configure it, then `build()` | The client created at the usage site |
| Add a shared header to all Boot-provided `RestClient.Builder` instances | A `RestClientCustomizer` bean | Builders that go through auto-configuration |
| Keep default JSON config + add one serialization policy | `spring.jackson.*` property or `Jackson2ObjectMapperBuilderCustomizer` | `ObjectMapper` created via the auto-configured builder |
| Provide a globally customized `RestTemplateBuilder` | `RestTemplateBuilderConfigurer.configure(new RestTemplateBuilder())` then change what is needed | Application-provided builder bean |
| Provide your own `RestClient.Builder` while keeping defaults | `RestClientBuilderConfigurer.configure(RestClient.builder())` | Application-provided builder |
| Completely replace an implementation incompatible with defaults | Define a new bean and manage its dependencies | Needs thorough testing; may cause auto-config to back off |

You should escalate the level of intervention gradually: standard property → local builder → customizer bean → configurer + custom builder → full replacement bean. This is a practical order of choice, **not** a fixed processing order in the framework.

## 5. Runnable example: preserving HTTP/JSON defaults while adding a shared header

Suppose we create an HTTP client that calls a catalog service. We want to:
1. Use the `RestClient.Builder` provided by Spring Boot 3.5 to preserve HTTP message converters and the appropriate request factory.
2. Add `X-App-Client: study-service` via a shared `RestClientCustomizer`.
3. Set a dedicated `baseUrl` for the catalog client.
4. Test the JSON response and header **without calling the internet**.

### 5.1. Project structure

~~~text
customizer-demo/
├── pom.xml
└── src/
    ├── main/java/example/ClientCustomizationApplication.java
    └── test/java/example/ClientCustomizationTests.java
~~~

Use Java 17+ and Maven; file and class names must match the example.

### 5.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>customizer-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-web` brings Spring Web and default JSON support for the Boot 3.5 line into the application. `spring-boot-starter-test` provides JUnit Jupiter, AssertJ, and `MockRestServiceServer` tools from Spring Test.

The example version is pinned so that the APIs are compatible. For real projects, use the Spring Boot patch version managed and tested by your project, and avoid downgrading just to match the lesson.

### 5.3. Application and customizer

File `src/main/java/example/ClientCustomizationApplication.java`:

~~~java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.client.RestClientCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.web.client.RestClient;

@SpringBootApplication(proxyBeanMethods = false)
public class ClientCustomizationApplication {

    public static void main(String[] args) {
        SpringApplication.run(ClientCustomizationApplication.class, args);
    }

    @Bean
    RestClientCustomizer appClientHeaderCustomizer() {
        return builder ->
                builder.defaultHeader("X-App-Client", "study-service");
    }

    @Bean
    CatalogClient catalogClient(RestClient.Builder builder) {
        // This is the RestClient.Builder configured by Boot.
        return new CatalogClient(
                builder.baseUrl("https://catalog.example.test").build());
    }

    public static final class CatalogClient {

        private final RestClient client;

        public CatalogClient(RestClient client) {
            this.client = client;
        }

        public Item find(long id) {
            return client.get()
                    .uri("/items/{id}", id)
                    .retrieve()
                    .body(Item.class);
        }

        public record Item(long id, String name) {
        }
    }
}
~~~

**Explanation of key points:**

- `RestClientCustomizer` is a callback interface supported by Spring Boot. Customizer beans are collected when Boot configures `RestClient.Builder`.
- `builder.defaultHeader(...)` adds a default header without requiring you to rewrite HTTP message converters, the request factory, or all of the client logic.
- The `RestClient.Builder builder` parameter in `catalogClient(...)` is **injected**, rather than application code calling `RestClient.builder()` directly.
- `baseUrl(...)` is a **local configuration for the catalog client**.
- `build()` produces the `RestClient` for `CatalogClient`; from there, API calls can use JSON mapping handled by the configured message converters.
- `https://catalog.example.test` is an illustrative URL. No real network requests are sent when running the test in the next section.

Boot 3.5 auto-configures `RestClient.Builder` with **prototype scope**. Essentially, each time the framework requests a new builder bean from the container, it receives a separate configured builder instance. However, a singleton that has the builder injected into its constructor **does not automatically receive a new builder on every method call** of that singleton.

### 5.4. Testing: verifying that the header and JSON mapping work together

File `src/test/java/example/ClientCustomizationTests.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

@SpringBootTest(
    classes = ClientCustomizationApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ClientCustomizationTests {

    @Autowired
    RestClient.Builder bootBuilder;

    @Test
    void customHeaderAndDefaultJsonConverterWorkTogether() {
        RestClient.Builder localBuilder = bootBuilder.clone()
                .baseUrl("https://catalog.example.test");

        MockRestServiceServer server =
                MockRestServiceServer.bindTo(localBuilder).build();

        server.expect(requestTo(
                    "https://catalog.example.test/items/42"))
                .andExpect(header("X-App-Client", "study-service"))
                .andRespond(withSuccess(
                        "{\"id\":42,\"name\":\"Pencil\"}",
                        MediaType.APPLICATION_JSON));

        ClientCustomizationApplication.CatalogClient client =
                new ClientCustomizationApplication.CatalogClient(
                        localBuilder.build());

        ClientCustomizationApplication.CatalogClient.Item item =
                client.find(42);

        assertThat(item).isEqualTo(
                new ClientCustomizationApplication.CatalogClient.Item(
                        42, "Pencil"));

        server.verify();
    }
}
~~~

Run in the project directory:

~~~bash
mvn test -Dtest=ClientCustomizationTests
~~~

Or if the project has Maven Wrapper:

~~~bash
./mvnw test -Dtest=ClientCustomizationTests
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd test '-Dtest=ClientCustomizationTests'
~~~

**Expected result:** test PASSES. The mock server verifies:
1. The client actually calls the URL configured on the builder.
2. The request contains the shared header added by `RestClientCustomizer`.
3. The JSON `{"id":42,"name":"Pencil"}` is converted into the `Item` record by the appropriate converter, instead of requiring a manually built mapper/converter.

The test **does not access a real network**: `MockRestServiceServer.bindTo(localBuilder)` installs a test request factory on that specific builder before `build()` is called. The outcome does not depend on whether the example domain exists.

Some Spring Boot/Maven logs will still appear; this lesson only states that the test is expected to PASS, without inventing a completely fixed stdout snippet.

## 6. How does a Boot-provided builder differ from calling builder() yourself?

Suppose there are two ways to create a client:

~~~java
// Approach A: use the RestClient.Builder injected by Spring Boot.
CatalogClient createUsingBoot(RestClient.Builder bootBuilder) {
    return new CatalogClient(
            bootBuilder.baseUrl("https://catalog.example.test").build());
}

// Approach B: instantiate the builder directly using Spring Framework.
CatalogClient createDirectly() {
    return new CatalogClient(
            RestClient.builder()
                    .baseUrl("https://catalog.example.test")
                    .build());
}
~~~

The snippet above is **illustrative**, assuming `CatalogClient` is imported and both methods live in an appropriate class.

**Approach A** inherits Spring Boot's customizations. **Approach B** still uses Spring Framework's built-in defaults, but **does not automatically inherit all configurations that Boot added to the builder bean**, including the application's `RestClientCustomizer` beans. The same applies to `RestClient.create()` when bypassing the auto-configured builder.

Some of Boot's defaults may include:
- `HttpMessageConverters` integrated with the application's configuration;
- A `ClientHttpRequestFactory` matching the HTTP library on the classpath;
- Customizers contributed by the application or Boot integrations;
- Observation/SSL integration when the corresponding modules are available and configured.

We do not claim that **every** item appears in every project; that depends on dependencies, conditions, and configuration.

### Stateful or immutable builder?

This is a difference that easily causes bugs:

| Builder | Key characteristic | Safe usage |
| --- | --- | --- |
| `RestClient.Builder` | Stateful; setter calls mutate the builder | Use a newly injected instance or `clone()` if multiple configurations are needed |
| `WebClient.Builder` | Similarly stateful | Use Boot's builder and `clone()` when creating multiple variants |
| `RestTemplateBuilder` (Boot) | Most configuration methods return a **new** builder | Keep the return value of each call |

Example with `RestClient.Builder`:

~~~java
// Illustrates two variants; bootBuilder is the injected bean.
RestClient orders = bootBuilder.clone()
        .baseUrl("https://orders.example.test")
        .build();

RestClient billing = bootBuilder.clone()
        .baseUrl("https://billing.example.test")
        .build();
~~~

If you repeatedly mutate **the same** stateful builder and call `build()`, configurations can accumulate and cause unintended side effects. Cloning gives each client its own configuration while still starting from the same defaults.

## 7. Global customizers and local customization

There are three scopes to distinguish:

**Local at the usage site**:

~~~java
@Bean
CatalogClient catalogClient(RestClient.Builder builder) {
    RestClient client = builder
            .baseUrl("https://catalog.example.test")
            .defaultHeader("X-Catalog-Version", "v1")
            .build();
    return new CatalogClient(client);
}
~~~

This is an illustrative snippet when `CatalogClient` is already defined; declare it in a configuration class. The catalog header is solely a decision for the client created from this builder.

**Shared across auto-configured `RestClient.Builder` instances**:

~~~java
@Bean
RestClientCustomizer complianceHeader() {
    return builder ->
            builder.defaultHeader("X-Client-Family", "internal");
}
~~~

When a `RestClient.Builder` comes from Boot, the callback is applied; new builders created by the framework can also receive the same policy.

**Replacing the entire builder**:

~~~java
@Bean
RestClient.Builder restClientBuilder() {
    return RestClient.builder();
}
~~~

This last snippet carries risk: a user-provided `RestClient.Builder` bean can cause auto-configuration to **back off**. You get a working builder, but Boot's customizers and defaults may no longer be applied in the usual way. Section 9 shows how to use `RestClientBuilderConfigurer` if you genuinely must define your own builder bean.

**Design rule:** keep changes meant for a single service in the local builder; put application-wide configuration in an appropriate customizer. Do not put a single partner's base URL into a global customizer unless every client truly uses the same destination.

## 8. RestTemplateBuilder and RestTemplateCustomizer-style customization

In Spring Boot 3.5, `RestTemplate` is still supported for blocking applications. Boot auto-configures **`RestTemplateBuilder`**, and does not necessarily pre-create a singleton `RestTemplate` for every application.

Local example:

~~~java
import java.time.Duration;

import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.web.client.RestTemplate;

// Illustrative snippet inside a service or @Bean.
RestTemplate makePartnerTemplate(RestTemplateBuilder bootBuilder) {
    return bootBuilder
            .rootUri("https://partner.example.test")
            .connectTimeout(Duration.ofSeconds(3))
            .readTimeout(Duration.ofSeconds(5))
            .build();
}
~~~

Methods such as `rootUri`, `connectTimeout`, and `readTimeout` return a new `RestTemplateBuilder`. Writing `bootBuilder.connectTimeout(...);` and discarding the return value can prevent the setting from being applied to `build()` on the original variable.

### Using RestTemplateCustomizer

~~~java
import org.springframework.boot.web.client.RestTemplateCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.http.client.ClientHttpRequestInterceptor;

// Inside a @Configuration class.
@Bean
RestTemplateCustomizer addTrackingHeader() {
    ClientHttpRequestInterceptor interceptor =
            (request, body, execution) -> {
                request.getHeaders().add("X-Tracking", "training");
                return execution.execute(request, body);
            };

    return template -> template.getInterceptors().add(interceptor);
}
~~~

This `RestTemplateCustomizer` bean can be applied to `RestTemplate` instances created by **`RestTemplateBuilder` auto-configured by Boot**. It appends the interceptor to the existing list; replacing the entire list could drop interceptors registered by other libraries.

Each customizer has a specific target/object type:
- `RestClientCustomizer` receives `RestClient.Builder`;
- `RestTemplateCustomizer` receives `RestTemplate`;
- `Jackson2ObjectMapperBuilderCustomizer` receives `Jackson2ObjectMapperBuilder`;
- `WebClientCustomizer` receives `WebClient.Builder` when using WebFlux.

Do not swap `RestClientCustomizer` for `RestTemplateCustomizer` and expect it to automatically affect `RestClient`.

## 9. When you need to provide your own builder: use Configurer to keep defaults

A rarer case: your module requires **registering a `RestClient.Builder` bean yourself**. In that case, do not just write `RestClient.builder()` and conclude that you have inherited Spring Boot's configuration.

With Spring Boot 3.5, use **`RestClientBuilderConfigurer`**:

~~~java
package example;

import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.boot.autoconfigure.web.client.RestClientBuilderConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class CustomRestClientBuilderConfiguration {

    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    RestClient.Builder restClientBuilder(
            RestClientBuilderConfigurer configurer) {

        return configurer.configure(RestClient.builder())
                .defaultHeader("X-Provided-Builder", "custom");
    }
}
~~~

This is an **alternative configuration choice** to the default builder bean; do not include it alongside the sample project in section 5 unless replacement is actually needed.

Why:
1. `configurer.configure(RestClient.builder())` uses Boot's configurer to apply defaults to the new builder.
2. `defaultHeader(...)` adds the application's customization after that step.
3. `@Scope(SCOPE_PROTOTYPE)` preserves the idea of supplying a fresh builder per container request point, close to the prototype behavior Boot uses for `RestClient.Builder`.

**Do not infer that `@Scope("prototype")` makes the builder completely immutable:** the builder itself is still stateful. Multiple threads should not share and concurrently mutate the same builder instance.

Equivalent example for `RestTemplateBuilder`:

~~~java
import java.time.Duration;

import org.springframework.boot.autoconfigure.web.client.RestTemplateBuilderConfigurer;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;

// Place the method in a Spring configuration class.
@Bean
RestTemplateBuilder restTemplateBuilder(
        RestTemplateBuilderConfigurer configurer) {

    return configurer.configure(new RestTemplateBuilder())
            .connectTimeout(Duration.ofSeconds(3))
            .readTimeout(Duration.ofSeconds(5));
}
~~~

The configurer applies Boot's defaults and customizers before adjusting the timeouts. With `RestTemplateBuilder`, each configuration call returns a new builder, and you must `return` that builder.

**Note:** the package names of configurers/builders changed in Spring Boot 4.x—for example, `RestClientBuilderConfigurer` belongs to `org.springframework.boot.restclient.autoconfigure` in the newer line. Do not copy 3.5 imports into 4.x mechanically.

## 10. Customizing Jackson JSON: another Customizer example

If a Spring Boot 3.5 project uses Jackson 2 via the web starter, `Jackson2ObjectMapperBuilderCustomizer` is the extension point for adjusting the `ObjectMapper` built through Boot's builder.

Example omitting null fields when serializing JSON:

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;

import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;

// Place in @Configuration or @SpringBootApplication.
@Bean
Jackson2ObjectMapperBuilderCustomizer omitNullJsonProperties() {
    return builder ->
            builder.serializationInclusion(JsonInclude.Include.NON_NULL);
}
~~~

When `JacksonAutoConfiguration` uses the `Jackson2ObjectMapperBuilder` configured by Boot, the callback affects the mapper created from that builder. The application can still inherit Boot's other settings, such as registered modules and applicable `spring.jackson.*` properties.

If you only need to adjust a feature already supported by a Boot property, you can use:

~~~properties
spring.jackson.default-property-inclusion=non_null
~~~

Properties are suitable for static configuration; customizers are useful when you need extra logic or Java options that are inconvenient to express via properties.

**Counter-example:**

~~~java
// Illustrates replacing the bean directly; NOT recommended
// when the goal is to preserve all Boot defaults.
@Bean
com.fasterxml.jackson.databind.ObjectMapper objectMapper() {
    return new com.fasterxml.jackson.databind.ObjectMapper();
}
~~~

When you define `ObjectMapper` yourself, auto-configuration may stop creating the default mapper due to `@ConditionalOnMissingBean`. A self-created mapper can miss modules or Boot's default configuration. If you truly need a replacement, you must intentionally re-handle all related integrations.

**Version distinction:** Spring Boot 4.x defaults to Jackson 3 and `JsonMapper`; Jackson 2 in the 4.x line is for compatibility/migration. The Jackson 2 extension point above is illustrated for **Boot 3.5**, not as default advice for all newer versions.

## 11. Conditional customization in your own starter/auto-configuration

A Spring Boot starter library should contribute beans only when truly needed, while allowing the application to override them. Sketch example for a library providing a catalog API client:

~~~java
// Illustrative snippet applicable to Spring Boot 3.5;
// assumes CatalogClient is a separately defined public type.
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.web.client.RestClientAutoConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.web.client.RestClient;

@AutoConfiguration(after = RestClientAutoConfiguration.class)
@ConditionalOnClass(RestClient.class)
class CatalogClientAutoConfiguration {

    @Bean
    @ConditionalOnBean(RestClient.Builder.class)
    @ConditionalOnMissingBean(CatalogClient.class)
    CatalogClient catalogClient(RestClient.Builder builder) {
        return new CatalogClient(
                builder.baseUrl("https://catalog.example.test").build());
    }
}
~~~

Meaning:
- `@AutoConfiguration(after=...)` orders this configuration after the auto-configuration that supplies the builder, helping condition evaluation follow bean definition order.
- `@ConditionalOnClass` avoids applying when the API is not on the classpath.
- `@ConditionalOnBean(RestClient.Builder.class)` only creates the client when a suitable builder is available.
- `@ConditionalOnMissingBean(CatalogClient.class)` lets users supply their own client and lets the library **back off**.
- The client in the starter itself takes the builder configured by Boot, thereby continuing to receive the application's customizers.

In a real starter, you must register the FQCN of the auto-configuration class in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. Not every extension point needs a starter: in a normal application, a customizer `@Bean` in a component-scanned `@Configuration` class is enough.

**Avoid wrong ordering:** `@ConditionalOnBean` is sensitive to bean definitions present at evaluation time. For an auto-configuration that depends on a Boot builder, specify ordering explicitly or design conditions according to the corresponding documentation.

## 12. Ordering of multiple customizers and override risks

Suppose two customizers both modify the same header, timeout, or object mapper setting. The final outcome can depend on application order or whether the API **adds**, **replaces**, or **merges** data.

Good practices:
1. Use additive operations when appropriate, such as adding an interceptor/header, rather than resetting the entire collection.
2. If ordering is a business requirement, use `@Order` or `Ordered` when that extension point supports sorting. Check the Javadoc/source for the exact Boot version.
3. Test interactions between application customizers and library ones such as metrics/tracing/logging.
4. Avoid customizers that read shared mutable state and modify it without synchronization.
5. Do not assume that `@Bean` declaration order in source code is the callback execution order.
6. For sensitive settings like Authorization, do not log full headers containing tokens, cookies, or user data.

Example of a customizer setting a regular header:

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.boot.web.client.RestClientCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
@Order(100)
RestClientCustomizer commonHeader() {
    return builder ->
            builder.defaultHeader("X-Client-Group", "internal");
}
~~~

This example uses an annotation to **declare desired order**; you must verify the actual processing order if other customizers also touch `X-Client-Group`. A smaller `@Order` value generally has higher priority when the list is sorted ascending, but you should not guess header merge/override semantics without testing.

## 13. How to verify that defaults are still preserved

Verify at least two layers:

### Behavioral layer

- **HTTP:** do requests include the header added by the customizer?
- **JSON:** are JSON responses deserialized into the DTO?
- **Local customization:** does client A use its own URL/timeout without accidentally changing client B?
- **Extensibility:** when a second customizer is added, does the previously working one still work?
- **No network calls in unit tests:** use `MockRestServiceServer` and avoid depending on real services.
- **Misconfiguration:** try omitting a classpath dependency or disabling auto-configuration to confirm beans are guarded by appropriate conditions.

### Metadata/diagnostics layer

Use `--debug` when running Spring Boot:

~~~bash
java -jar target/customizer-demo-1.0.0.jar --debug
~~~

The `Condition Evaluation Report` helps check which auto-configurations matched or backed off. If Spring Boot Actuator is integrated and the appropriate endpoint is exposed, `/actuator/conditions` can also assist with diagnostics. Do not confuse **condition match** with proof that customizers were actually applied: the latter should be confirmed with behavioral tests.

When suspecting lost defaults after defining your own builder, check:
- Is a user-defined `RestClient.Builder`/`RestTemplateBuilder` bean replacing the default bean?
- Does the builder go through `RestClientBuilderConfigurer`/`RestTemplateBuilderConfigurer`?
- Did you accidentally use `RestClient.create()` or `RestClient.builder()` outside auto-config?
- Is the customizer present in the Spring context?
- Is a later customizer overwriting the same setting?

## 14. Common mistakes and fixes

| Mistake | Cause | Fix |
| --- | --- | --- |
| `RestClientCustomizer` has no effect | Client created via `RestClient.create()` or a self-created builder | Inject Boot's builder or use the configurer |
| Shared header only appears on one client | Header was set locally | Create a `RestClientCustomizer` bean if you want it global |
| Two clients unintentionally share a base URL | Reused a mutated stateful builder | Inject a fresh builder or `clone()` for each variant |
| `RestTemplateBuilder` ignores timeout | Discarded the returned builder value | Assign/store/return the new builder |
| JSON mapping is missing modules | Created `ObjectMapper` directly outside auto-config | Use properties, Jackson builder customizer, or configure the mapper fully |
| Declaring a builder bean loses defaults | Auto-config backed off or custom builder lacks configurer | Use `RestClientBuilderConfigurer`/`RestTemplateBuilderConfigurer` |
| Customizer affects all HTTP clients when only one partner was intended | Global callback scope is too broad | Move configuration to the builder at the usage site |
| Multiple customizers overwrite the same key | Unclear ordering or setter semantics | Separate responsibilities, use ordering when supported, and add tests |
| Copying Boot 3.5 packages to Boot 4 | APIs changed package/name or JSON stack differs | Check Javadoc for the exact version line |
| Assuming customizers automatically affect manually created beans | No code collects/invokes the customizers | Choose a Boot-provided builder or invoke the appropriate configurer |

## 15. Practice exercises

**Exercise 1 – Local customization:** Add a second client calling `https://billing.example.test`. Use `bootBuilder.clone()` and set the header `X-Partner: billing`. Verify that this header is not sent by the catalog client.

**Exercise 2 – Global customization:** Add a `RestClientCustomizer` that only sets `X-Trace-Demo: enabled`. Verify with `MockRestServiceServer` that the catalog client still parses JSON properly and receives both shared headers.

**Exercise 3 – Losing defaults:** Temporarily construct a `RestClient` with `RestClient.create()` in a standalone test. Observe that the `RestClientCustomizer` header does not appear automatically. Explain the difference between Spring Framework defaults and additional configuration provided by Spring Boot.

**Exercise 4 – Configurer:** Create a custom builder configuration following section 9 and verify that the header/JSON tests still PASS. Use only one builder bean provision approach at a time to avoid unexpected competing beans.

**Exercise 5 – JSON:** Add a `Jackson2ObjectMapperBuilderCustomizer` configured to omit nulls; serialize a record with a nullable property and compare the before/after output.

## 16. Self-check questions

**Question 1.** Spring Boot has already auto-configured `RestClient.Builder`. If you want each client to use a different base URL while keeping default converters, what should you do?

**Answer:** Inject the Boot-provided builder, apply `baseUrl(...)` locally, and call `build()`. If creating multiple variants from the same stateful builder, consider `clone()`.

**Question 2.** When should you use `RestClientCustomizer`?

**Answer:** When you want to add a shared change across `RestClient.Builder` instances handled by Spring Boot, such as a common header or shared interceptor, while preserving the underlying configuration.

**Question 3.** Why can `new ObjectMapper()` cause default behavior to be lost?

**Answer:** Because a directly instantiated object does not automatically receive the modules, properties, and customizers attached by auto-configuration to Boot's mapper.

**Question 4.** When providing your own `RestClient.Builder` bean, what must you do to preserve defaults?

**Answer:** Use `RestClientBuilderConfigurer.configure(RestClient.builder())` and then add the changes you need. Consider `prototype` scope when you need per-request builder provisioning like Boot's default.

**Question 5.** Do `RestClient.Builder` and `RestTemplateBuilder` have the same semantics?

**Answer:** No. `RestClient.Builder` is stateful and mutated in place, whereas `RestTemplateBuilder` follows a style of returning a new builder instance on configuration calls.

## 17. Official references

- Spring Boot 3.5 Reference — Calling REST Services (RestClient, WebClient, RestTemplate customization): https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html
- Spring Boot 3.5 API — RestClientAutoConfiguration: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/client/RestClientAutoConfiguration.html
- Spring Boot 3.5 API — RestClientCustomizer: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/client/RestClientCustomizer.html
- Spring Boot 3.5 API — RestClientBuilderConfigurer: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/client/RestClientBuilderConfigurer.html
- Spring Boot 3.5 API — RestTemplateBuilderConfigurer: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/client/RestTemplateBuilderConfigurer.html
- Spring Boot 3.5 API — Jackson2ObjectMapperBuilderCustomizer: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jackson/Jackson2ObjectMapperBuilderCustomizer.html
- Spring Framework 6.2 API — MockRestServiceServer: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/web/client/MockRestServiceServer.html
