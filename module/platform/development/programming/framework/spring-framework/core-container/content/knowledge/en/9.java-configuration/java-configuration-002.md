# Registering Library Objects Without @Component Using Java Configuration in Spring

## 1. Scenario and Expected Outcomes

In a Spring application, many objects you need to use come from external libraries outside the development team's source code: `com.fasterxml.jackson.databind.ObjectMapper` for JSON processing, `java.time.Clock` for time control, HTTP clients, SDK clients, encoders, connectors, and third-party adapters.

These classes typically **do not carry `@Component`**. Nor do you normally have permission to modify the source code or add annotations to classes inside a JAR. Therefore, if you only enable `@ComponentScan` and expect Spring to register every library object automatically, the result is usually a missing bean.

The standard approach in **Spring Core Container Java configuration** is to declare a **`@Bean`** method inside a **`@Configuration`** class. That method creates or retrieves the object, configures its required properties, and **returns the object for the container to manage**. Spring registers the bean definition for the factory method and uses it to satisfy dependency injection.

After this lesson, you will be able to:

1. Explain why a library class without `@Component` still becomes a Spring bean using `@Bean`.
2. Write `@Configuration` and a `@Bean` factory method returning an object from an external library; distinguish registering a bean from calling `new` directly in business code.
3. Inject dependencies into **`@Bean` method parameters**, even when the library object takes dependencies via its constructor.
4. Select the right bean when there are multiple instances of the same type, via `@Qualifier`, bean name, or `@Primary`.
5. Manage scope, lazy initialization, init/destroy callbacks, and resource ownership.
6. Understand `@Configuration(proxyBeanMethods=false)` and the difference between dependency injection and **calling a `@Bean` method directly**.
7. Run a practical Java 17+ example using **Jackson ObjectMapper** with no component scan.

> Core idea: **Spring manages an object because a valid bean definition exists**, not because the object's class must carry a Spring annotation.

## 2. Why Doesn't Component Scanning Solve This Problem?

Suppose a library provides:

```java
// From an external library; assume the class has no Spring annotations.
package vendor.sdk;

public final class ExternalClient {
    public ExternalClient(String endpoint, String token) {
        // ...
    }

    public String fetch(String id) {
        // ...
        return id;
    }
}
```

This is a sketched class to explain the constructor API of a hypothetical SDK; it is not a real library you can add to Gradle. The class contains no `@Component`, `@Service`, or `@Component` meta-annotation, and its constructor requires configuration information. `@ComponentScan` with default stereotype filters will not automatically create an `ExternalClient` bean.

To register it, use a factory method:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ExternalClientConfig {
    @Bean
    ExternalClient externalClient() {
        return new ExternalClient(
                "https://api.example.test",
                "demo-token"
        );
    }
}
```

This snippet is again a **structural example**, assuming `vendor.sdk.ExternalClient` and the right imports exist; the URL/token are illustrative only and not a production configuration. In a real project, endpoints/secrets must come from a secure configuration source rather than being hard-coded in source.

Crucially, the `ExternalClient` class **does not need to be modified**. The `externalClient()` method is where application code decides how to build the object; Spring invokes the factory method when it needs to create the bean according to its scope.

### Component scan and @Bean answer two different questions

| Component | Question | Appropriate Use Case |
| --- | --- | --- |
| `@ComponentScan` | Which classes on the classpath are discovered by package/filter? | Classes controlled by the application that can be marked with Spring stereotypes. |
| `@Component` / `@Service` | Is this class a component candidate during a scan pass? | Services, adapters, and handlers located in the application's own source code. |
| `@Bean` | Which method creates/configures an object and registers it as a bean? | Library classes, objects needing builders/factories, complex setup, classes without stereotypes. |
| `@Configuration` | Which class holds Java configuration and bean factory methods? | Separating infrastructure assembly logic from business logic. |

A project can use both registration paths at the same time. `@ComponentScan` is not required for `@Bean` to work; conversely, `@Bean` does not eliminate the need to scan application services.

## 3. Actual Mechanism When Spring Processes @Bean

A Java configuration class typically looks like:

```java
@Configuration
public class InfraConfig {
    @Bean
    public ThirdPartyType thirdPartyType() {
        return new ThirdPartyType(/* configuration arguments */);
    }
}
```

`ThirdPartyType` is only a hypothetical type; this snippet cannot compile without a specific library. Logical path:

```text
Application registers InfraConfig
             |
             v
ConfigurationClassPostProcessor
   analyzes @Configuration + @Bean
             |
             v
Registers BeanDefinition:
   beanName = "thirdPartyType"
   factoryBean = InfraConfig
   factoryMethod = thirdPartyType
             |
             v
Spring needs to create bean per scope
             |
             v
Invoke factory method -> obtain object
             |
             v
BeanPostProcessor, init callbacks, lifecycle
             |
             v
Object can be injected into other beans
```

**Milestones to understand accurately:**

- `@Bean` is an annotation **on a method**, not an annotation forced onto the library class.
- In Spring 6.2, the standard default bean name is the method name: `thirdPartyType`. You can specify an explicit name with `@Bean("someName")`.
- The declared return type of the method affects how Spring searches for beans by type; declare a type specific enough for the injection points that need it.
- Spring does not "turn library source into a component". The container manages **the object supplied by the factory method**.
- Registering a bean definition, creating an instance, and invoking init callbacks are separate steps. Non-lazy singletons are typically created during context refresh; `prototype` beans are created per request.
- Spring can still apply dependency injection and lifecycle processing to the object returned from `@Bean` if the relevant annotations/infrastructure are configured.

## 4. Writing @Bean Properly: From Minimal to Having Dependencies

### 4.1. Object needing no dependencies

```java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TimeConfig {
    @Bean
    Clock appClock() {
        return Clock.systemUTC();
    }
}
```

`Clock` belongs to the Java standard library; that class carries no `@Component`. Once `TimeConfig` is loaded into Spring, the `appClock` bean can be injected into a service:

```java
import java.time.Clock;
import java.time.Instant;

public final class AuditService {
    private final Clock clock;

    public AuditService(Clock clock) {
        this.clock = clock;
    }

    public Instant now() {
        return Instant.now(clock);
    }
}
```

`AuditService` here is an ordinary Java class; to make it a Spring bean, it must be registered via `@Bean` or appropriate component scanning. Configuring `Clock` independently lets tests use a fixed clock and production use the system clock without calling `Instant.now()` directly in many places.

### 4.2. Factory method receiving dependencies from the container

If a client must use another registered object, declare the dependency in the **`@Bean` parameters**:

```java
@Configuration(proxyBeanMethods = false)
public class ClientConfig {
    @Bean
    ClientSettings clientSettings() {
        return new ClientSettings("https://example.test");
    }

    @Bean
    VendorClient vendorClient(ClientSettings settings) {
        return new VendorClient(settings.endpoint());
    }
}
```

`ClientSettings` and `VendorClient` are illustrative types, not built-in Spring classes. Spring resolves `ClientSettings` via normal dependency injection and then invokes `vendorClient(settings)`. This is a clean way to assemble objects, especially when using `proxyBeanMethods=false`.

**Avoid** writing `vendorClient() { return new VendorClient(clientSettings().endpoint()); }` when `proxyBeanMethods=false`: that is a **regular Java call**, creating an extra `ClientSettings` instead of reliably using the container-managed singleton. Passing method parameters is the consistent approach.

### 4.3. Registering an object created by a library builder/factory

Not every library has a convenient public constructor. A factory method can call a builder or static factory:

```java
@Bean
ExternalSdkClient sdkClient(AppProperties settings) {
    return ExternalSdkClient.builder()
            .endpoint(settings.endpoint())
            .timeout(settings.timeout())
            .build();
}
```

This is **Java API pseudocode for a hypothetical SDK**. Spring cares about the final returned object; how the library builds the object (constructor, builder, static factory, connection pool) is the library's own decision.

## 5. Complete Example: Registering Jackson ObjectMapper Without @Component

The following real example uses:

- **Java 17+**.
- **Spring Framework 6.2.9** with `AnnotationConfigApplicationContext`.
- **Jackson Databind 2.18.2**: the external library class `ObjectMapper` **needs no `@Component`**.
- Two differently configured `ObjectMapper` beans, one `Clock` bean, and one service bean wired via `@Bean` parameters.
- Completely **without declaring `@ComponentScan`**.

The example fixes time so that stdout results can be re-verified regardless of the current date.

### 5.1. File structure

```text
third-party-bean-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── demo/
                └── ThirdPartyBeansDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'third-party-bean-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.18.2'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.ThirdPartyBeansDemo'
}
```

Spring Context includes transitive dependencies for the needed IoC components. Jackson Databind brings in the needed Jackson dependencies via standard Gradle resolution. This is a plain Spring example; Spring Boot applications typically use Boot's dependency management/BOM to align versions.

### 5.2. Java program

**`src/main/java/demo/ThirdPartyBeansDemo.java`**

```java
package demo;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class ThirdPartyBeansDemo {

    // This is just a regular Java class, without @Component.
    public static final class ReportService {
        private final ObjectMapper mapper;
        private final Clock clock;

        public ReportService(ObjectMapper mapper, Clock clock) {
            this.mapper = mapper;
            this.clock = clock;
        }

        public String buildReport() throws JsonProcessingException {
            Map<String, Object> data = new LinkedHashMap<>();
            data.put("source", "jackson");
            data.put("year", LocalDate.now(clock).getYear());
            return mapper.writeValueAsString(data);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        // Jackson ObjectMapper has no @Component in the library.
        @Bean("compactMapper")
        ObjectMapper compactMapper() {
            return new ObjectMapper();
        }

        @Bean("prettyMapper")
        ObjectMapper prettyMapper() {
            return new ObjectMapper()
                    .enable(SerializationFeature.INDENT_OUTPUT);
        }

        @Bean
        Clock clock() {
            return Clock.fixed(
                    Instant.parse("2024-06-11T00:00:00Z"),
                    ZoneOffset.UTC
            );
        }

        // Two ObjectMappers of the same type: select the exact name at the injection point.
        @Bean
        ReportService reportService(
                @Qualifier("compactMapper") ObjectMapper mapper,
                Clock clock) {
            return new ReportService(mapper, clock);
        }
    }

    public static void main(String[] args) throws JsonProcessingException {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            System.out.println("compact=" +
                    context.containsBean("compactMapper"));
            System.out.println("pretty=" +
                    context.containsBean("prettyMapper"));
            System.out.println("mapper-count=" +
                    context.getBeansOfType(ObjectMapper.class).size());

            ObjectMapper first = context.getBean(
                    "compactMapper", ObjectMapper.class);
            ObjectMapper second = context.getBean(
                    "compactMapper", ObjectMapper.class);

            System.out.println("singleton=" + (first == second));
            System.out.println("report=" +
                    context.getBean(ReportService.class).buildReport());
        }
    }
}
```

**Run from the project directory:**

```bash
gradle run --quiet
```

If the project has the Gradle Wrapper, on Linux/macOS you can use `./gradlew run --quiet`; on Windows use `gradlew.bat run --quiet`. Gradle uses the dependency and toolchain configuration to compile/run. Running `javac ThirdPartyBeansDemo.java` standalone will lack Spring/Jackson libraries unless you configure the classpath manually.

**Lines printed by the program:**

```text
compact=true
pretty=true
mapper-count=2
singleton=true
report={"source":"jackson","year":2024}
```

Why is the output deterministic?

1. `Config.class` is passed directly to `AnnotationConfigApplicationContext`; Spring processes `@Configuration` and the four `@Bean` factory methods. There is no `@ComponentScan`.
2. `compactMapper` and `prettyMapper` are **two bean definitions** of the same type `ObjectMapper`, both returning a Jackson library object. Both names exist in the context.
3. `getBeansOfType(ObjectMapper.class)` finds two beans, so `mapper-count=2`.
4. By default `@Bean` has singleton scope. Two calls to `getBean("compactMapper", ObjectMapper.class)` in the same context return the same instance.
5. Spring selects `compactMapper` for the `reportService(...)` method thanks to `@Qualifier("compactMapper")`. It does not confuse it with `prettyMapper` even though both have the same return type.
6. `Clock.fixed(...)` always provides the same instant on 2024-06-11 UTC, so the year is 2024.
7. `LinkedHashMap` preserves insertion order of `source` then `year`; `compactMapper` does not enable pretty printing, so the single-line JSON matches stdout exactly.
8. `ReportService` also **carries no `@Component`**, yet it still becomes a bean because the `@Bean ReportService reportService(...)` method registered it.

**This is a demo of Java configuration and IoC**; it does not start a web server, does not require Spring MVC/Boot, and makes no network calls. Any Gradle/build environment logs, if present, are separate from the five intentional output lines above.

## 6. Choosing @Bean Names, @Qualifier, and @Primary

### 6.1. A library may need multiple instances of the same type

A real system might use two `ObjectMapper`s:

- One mapper outputting public JSON according to API rules.
- One mapper for internal logs with a different format.

Or there may be two HTTP clients of the same class with different endpoints, timeouts, or credentials. When there are multiple beans of the same type, injecting solely by type can become ambiguous.

```java
@Bean("internalMapper")
ObjectMapper internalMapper() {
    return new ObjectMapper();
}

@Bean("externalMapper")
ObjectMapper externalMapper() {
    return new ObjectMapper();
}
```

This snippet uses the same Jackson dependency as the demo and must reside inside a configuration class. If a consumer class takes a single `ObjectMapper` without enough information to pick a candidate, Spring can throw `NoUniqueBeanDefinitionException`.

**Select explicitly with a qualifier:**

```java
@Bean
ExternalExporter externalExporter(
        @Qualifier("externalMapper") ObjectMapper mapper) {
    return new ExternalExporter(mapper);
}
```

`ExternalExporter` is an illustrative business class, not built into Spring/Jackson. `@Qualifier` attached at the injection point selects the corresponding bean.

### 6.2. Selecting a default candidate with @Primary

```java
@Bean
@Primary
ObjectMapper appMapper() {
    return new ObjectMapper();
}

@Bean
ObjectMapper legacyMapper() {
    return new ObjectMapper();
}
```

This configuration snippet requires importing `org.springframework.context.annotation.Primary`. When injecting by type `ObjectMapper` without a specific qualifier, `@Primary` can select `appMapper`. However, do not use `@Primary` to mask having multiple distinct configurations where business logic needs to target a specific one.

**Distinction:** `@Primary` takes effect during **dependency selection**; it does not change the bean name, scope, or remove the remaining bean from the context.

### 6.3. Method name, bean name, and alias

```java
@Bean({"jsonWriter", "publicJsonWriter"})
ObjectMapper writer() {
    return new ObjectMapper();
}
```

This snippet creates **one** bean with name `jsonWriter` and alias `publicJsonWriter`, not two independent objects. Use two separate `@Bean` methods if you truly need two configurations/instances. In a standard declaration, `@Bean ObjectMapper objectMapper()` has the default name `objectMapper`.

## 7. Wiring Dependencies via @Bean Method Parameters

Suppose a library client needs `Clock`, `ObjectMapper`, and configuration:

```java
@Bean
VendorClient vendorClient(
        @Qualifier("compactMapper") ObjectMapper mapper,
        Clock clock,
        ClientOptions options) {
    return new VendorClient(mapper, clock, options);
}
```

This is an **illustrative example**; `VendorClient` and `ClientOptions` are types provided by a hypothetical application/library. Spring resolves each method parameter just like standard dependency injection. This approach has three advantages:

- Dependencies are clearly visible in the factory method signature.
- You can substitute objects in tests via another configuration without touching library source code.
- You do not have to call other `@Bean` methods directly and accidentally create objects outside the expected lifecycle.

### Should you return an interface or a concrete type?

If the bean's public API only needs a `Client` interface, you can declare:

```java
@Bean
Client client() {
    return new HttpClientAdapter();
}
```

`Client` and `HttpClientAdapter` are hypothetical types. However, Spring may rely on the **declared return type** when it needs to predict a bean's type **before creating an instance**. If another place injects `HttpClientAdapter` directly while the factory method declares only `Client`, early type matching can be limited.

A useful rule of thumb: **declare a return type specific enough** for the injection points allowed to use the bean. If you want classes to know only the interface, keep the interface type consistent across injection points and service APIs.

### Creating a bean via an SDK's static factory method

```java
@Bean
VendorConnection connection(VendorSettings settings) {
    return VendorConnection.open(
            settings.endpoint(),
            settings.accessToken()
    );
}
```

Structural snippet, not a real SDK API. In Spring, `@Bean` can call any valid object creation mechanism published by the vendor. Spring does not need to know the SDK's internal constructor as long as the factory method returns the proper object.

## 8. @Configuration(proxyBeanMethods=false) and Calling @Bean Methods

This is an easy place to introduce bugs when integrating libraries.

### 8.1. Two ways to assemble beans

**Recommended: factory method parameters.**

```java
@Configuration(proxyBeanMethods = false)
class Config {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    TimeService timeService(Clock clock) {
        return new TimeService(clock);
    }
}
```

`TimeService` here is a hypothetical example type with a constructor accepting `Clock`. The container resolves the `Clock` parameter according to the current scope and rules.

**Watch out: direct method call.**

```java
@Configuration(proxyBeanMethods = false)
class Config {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    TimeService timeService() {
        return new TimeService(clock());
    }
}
```

Because `proxyBeanMethods=false`, the `clock()` call inside `timeService()` is an ordinary Java call. It creates a `Clock` **different from the object registered as a bean** (given the factory above), if the method actually constructs a new object. In some scenarios, this bug causes two connection pools/HTTP clients or mismatched lifecycles.

In full mode `@Configuration(proxyBeanMethods=true)`, Spring normally uses class enhancement so that calls between `@Bean` methods are routed through the container according to scope. Still, code using **parameter injection** is clearer and does not depend on how the configuration class is proxied.

**Rule:** With `proxyBeanMethods=false`, do not use cross-calls between `@Bean` methods assuming you will get the container singleton. Choose injection via parameters; it is also easier to test and less surprising.

### 8.2. Do not call factory methods from business code

The line:

```java
new ExternalClientConfig().externalClient();
```

even if the configuration and method are accessible, merely **creates a Java object**. It is not equivalent to `applicationContext.getBean(ExternalClient.class)`. An object created by manually calling into a newly instantiated configuration may not receive lifecycle/proxying/configuration from the container.

To use a bean, inject it into a service constructor, or at startup/test boundaries use `ApplicationContext.getBean(...)`. In domain/business code, avoid depending directly on the container when constructor injection suffices.

## 9. Scope and Lazy Initialization for Library Beans

### 9.1. Default singleton

`@Bean` defaults to singleton (per container). This makes sense for reusable objects such as a configured mapper, immutable config, or a client documented by the vendor as thread-safe.

```java
@Bean
ObjectMapper objectMapper() {
    return new ObjectMapper();
}
```

Once the object is created and fully configured, requests for the bean in the same context normally receive the same instance. However, **do not automatically infer that every library object is thread-safe** just because Spring provides a singleton; check each library's contract and avoid mutating configuration after sharing.

For example, Jackson's `ObjectMapper` can generally be used concurrently safely **when all configuration is completed before the first read/write calls**. Mutating shared configuration while multiple threads are using it can cause unpredictable behavior; if different configurations are needed, register separate mappers or use appropriate immutable reader/writer configurations.

### 9.2. Prototype for stateful objects

```java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
VendorRequestBuilder requestBuilder(VendorSettings options) {
    return new VendorRequestBuilder(options);
}
```

This is an example with hypothetical `VendorRequestBuilder`/`VendorSettings`; requires importing `Scope` and `ConfigurableBeanFactory`. Prototype is suitable when an object holds per-request state and the vendor does not allow safe reuse.

If a singleton consumer needs one instance per operation, it can inject `ObjectProvider<VendorRequestBuilder>` and call `getObject()` when starting work. Do not inject a prototype directly into a singleton and expect Spring to automatically swap the object on every method call.

### 9.3. @Lazy only changes creation timing, not scope

```java
@Bean
@Lazy
ObjectMapper expensiveMapper() {
    return new ObjectMapper();
}
```

Requires importing `org.springframework.context.annotation.Lazy`. For a singleton bean, `@Lazy` typically defers bean creation until it is actually requested. However, if another eager singleton requires the mapper in its constructor/factory method, that dependency can force Spring to create the mapper early. `@Lazy` does not turn a singleton into a prototype.

### 9.4. Library resource lifecycle

An SDK client with `close()`/`shutdown()` may hold sockets, executors, or its own threads. With `@Bean`, Spring supports:

- `initMethod`: calls the named init method when appropriate.
- `destroyMethod`: calls the named destroy method; by default, Spring can infer public `close`/`shutdown` methods for eligible beans.
- `@PreDestroy` or `DisposableBean` when the class/adapter itself supports them and the right processor is present.
- `AutoCloseable`/lifecycle APIs depending on framework and class rules.

**Structural** example when an SDK has `start()` and `stop()` methods:

```java
@Bean(initMethod = "start", destroyMethod = "stop")
VendorConnection managedConnection(VendorSettings options) {
    return new VendorConnection(options);
}
```

Do not assume every SDK has these methods. If the vendor returns a global singleton, a client borrowed from another container, an object managed by an app server, or one whose lifecycle belongs to another party, **Spring should not close a resource it does not own**. In that case you can use `@Bean(destroyMethod = "")` to disable destroy method inference.

**Note:** The container typically does not fully manage destroy callbacks for prototype beans after handing out an instance; calling code must close resources at the appropriate time.

## 10. Externalizing Configuration Instead of Hard-Coding Secrets

Library classes often need hosts, credentials, and timeouts. A `@Bean` method is a good assembly point, yet secrets must not appear as hard-coded strings in Git.

An example using Spring `Environment`:

```java
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
class ClientConfiguration {
    @Bean
    VendorClient vendorClient(Environment environment) {
        String endpoint = environment.getRequiredProperty("vendor.endpoint");
        String apiKey = environment.getRequiredProperty("vendor.api-key");

        return new VendorClient(endpoint, apiKey);
    }
}
```

`VendorClient` is an illustrative type. `Environment` is an infrastructure bean/object that Spring can supply when executing the factory method. `getRequiredProperty` ensures missing-configuration errors surface early. Property sources can come from application configuration, environment variables, secret stores, or appropriate `PropertySource`s.

In Spring Boot, `@ConfigurationProperties` is often better suited for many configuration fields, validation, and testing; that is an additional Boot infrastructure feature. Regardless of how configuration is read, the `@Bean` principle remains creating/configuring the SDK object from resolved information.

**Do not log credentials** when debugging bean creation failures. Log enough context to diagnose the endpoint/mode, while masking tokens and sensitive values.

## 11. Importing and Organizing Multiple Configuration Classes

Splitting configuration by group is helpful:

```java
@Configuration(proxyBeanMethods = false)
class JsonLibraryConfig {
    @Bean
    ObjectMapper apiMapper() {
        return new ObjectMapper();
    }
}

@Configuration(proxyBeanMethods = false)
@Import(JsonLibraryConfig.class)
class ApplicationConfig {
    @Bean
    ReportService reportService(ObjectMapper apiMapper) {
        return new ReportService(apiMapper);
    }
}
```

This is a different structural snippet from the runnable demo above: `ReportService` here is a hypothetical type whose constructor takes only `ObjectMapper`; requires importing `Bean`, `Configuration`, `Import`, `ObjectMapper`. `@Import` loads configuration classes containing bean definitions. There is no need to place `@Component` on `ObjectMapper`.

In multi-module applications, each library group can have its own configuration: JSON, HTTP client, database adapter, cache, or message producer. Which configurations are imported/scanned determines whether their beans appear in that context.

**Do not confuse:** `@Import(SomeConfig.class)` and `@ComponentScan` are different. `@Import` explicitly declares the configuration source/related types, whereas scanning searches for classes by package/filter.

## 12. Registering a Library Without @Bean Is Possible, When?

There are programmatic bean registration APIs:

```java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();

context.registerBean(
        "appClock",
        Clock.class,
        Clock::systemUTC
);
context.refresh();
try {
    Clock clock = context.getBean("appClock", Clock.class);
    // Use clock.
} finally {
    context.close();
}
```

This is valid Java code when `java.time.Clock`, `org.springframework.context.annotation.AnnotationConfigApplicationContext`, and Spring dependencies are imported. `registerBean(...)` registers a bean definition with a supplier; it likewise does not require `@Component` on `Clock`.

However, **`@Bean` is usually easier to read and maintain** when a project already uses Java configuration. Programmatic registration suits dynamic bootstrapping, plugin registrars, framework integration, or code that builds a context from runtime metadata.

You can register a pre-existing instance via bean factory APIs, but **lifecycle, initialization, and closing of the object** must be understood accurately per the chosen API; do not treat placing an instance into a registry as wholly equivalent to a `@Bean` factory method.

## 13. Common Errors and Fixes

### 13.1. Scanning the application package but not finding classes from a JAR

**Symptom:** injecting `ObjectMapper` or an SDK client throws `NoSuchBeanDefinitionException`/`UnsatisfiedDependencyException`.

**Cause:** the library class carries no matching stereotype and has no bean definition supplied by `@Bean`/autoconfiguration.

**Fix:** declare a `@Bean` method returning the right type and load the `@Configuration` class into the context. Do not assume expanding `@ComponentScan` to vendor packages will solve it.

### 13.2. @Bean exists, but the @Configuration class is not loaded

A configuration file sitting in source code that is **not registered, imported, scanned, or autoconfigured** will not run on its own. Check `AnnotationConfigApplicationContext(Config.class)`, `@Import`, the Spring Boot application's package placement, and relevant conditions/profiles.

### 13.3. Two instances of the same type cause ambiguous dependency errors

If there are two `ObjectMapper`s and an injection point only specifies `ObjectMapper`, Spring can report `NoUniqueBeanDefinitionException`.

**Fix:** use `@Qualifier` to pick the right bean, or `@Primary` when there truly is a default. If the use case needs all instances, inject `Map<String, ObjectMapper>` or an appropriate collection to choose deliberately.

### 13.4. Calling a @Bean method directly with proxyBeanMethods=false

For example, `new Client(mapper())` creates an extra `ObjectMapper` object outside the registered instance when `mapper()` calls `new ObjectMapper()`. This can cause configuration, identity, or lifecycle mismatches. **Fix:** pass `ObjectMapper mapper` as a parameter to the other factory method.

### 13.5. Creating a client with new on every request

If a client or connection pool is expensive to initialize, instantiating it directly in a request handler wastes resources and is hard to shut down.

**Fix:** register a singleton bean **if the class is thread-safe and the lifecycle fits**, and inject the client into the service. Do not blindly make every library a singleton; check vendor documentation.

### 13.6. Spring closes an object owned elsewhere

An object with a public `close()` may have a destroy callback inferred by Spring while that resource is managed by an application server or another party. The consequence is prematurely closing a shared connection.

**Fix:** determine ownership; if it does not belong to Spring, use `@Bean(destroyMethod = "")` or an appropriate registration/lifecycle mechanism and test shutdown.

### 13.7. Forgetting to close an object owned by Spring

If a bean holds threads/sockets and requires `shutdown()` without a configured destroy callback, context shutdown may fail to release resources.

**Fix:** verify the library's lifecycle API, configure `destroyMethod` when appropriate, close the context properly, and test resources after shutdown.

### 13.8. Factory method returns an overly broad interface

Spring may not be able to predict the concrete type at injection points evaluated before the singleton is created. **Fix:** declare a sufficiently specific return type or standardize dependency injection on the service interface.

### 13.9. Spring-managed custom mapper mutated after use

A shared `ObjectMapper` is reconfigured while multiple threads are serializing. This can cause hard-to-reproduce bugs.

**Fix:** complete configuration before the bean is published to callers; use separate instances per policy, or readers/writers created via the appropriate Jackson APIs.

### 13.10. @Bean exists, assuming @ComponentScan won't create a duplicate bean

If the same class is both scanned via a stereotype and also created by another factory method of the same type, the context can end up with **two differently named instances** or bean name collisions.

**Fix:** inspect each registration path, avoid duplicate registration, and use clear names/qualifiers. Do not rely on bean definition overriding always being enabled, as configuration behavior varies by environment.

### 13.11. Using @Bean to "fix" library source code

`@Bean` does not add annotations to vendor classes, does not turn every `new VendorType()` call across the entire program into a managed bean, and does not automatically alter the behavior of objects created outside the container.

**Fix:** all code needing the configured object should **inject the bean from Spring**; limit manual instantiation in business paths.

### 13.12. Using @ConditionalOnMissingBean in plain Spring Framework

`@ConditionalOnMissingBean` belongs to **Spring Boot autoconfigure**, not a core annotation available in a project depending only on `spring-context`.

**Fix:** in plain Spring, manage configuration explicitly or use `@Conditional` with a matching `Condition` if needed; in Boot, use conditional auto-configuration in the proper context to supply a default bean that the application can still override by policy.

## 14. Testing and Observing Registered Beans

### 14.1. Checking bean names, identity, and type

The complete example in section 5 used:

```java
context.containsBean("compactMapper");
context.getBeansOfType(ObjectMapper.class).size();
context.getBean("compactMapper", ObjectMapper.class);
```

These three checks verify existence, count, and instance. When adding beans of the same type, check both names and how injection points resolve, because `getBean(ObjectMapper.class)` may be ambiguous even though `containsBean("compactMapper")` returns true.

### 14.2. Checking where a bean definition came from

```java
var beanFactory = context.getBeanFactory();
var definition = beanFactory.getBeanDefinition("compactMapper");

System.out.println(definition.getFactoryMethodName());
```

This snippet can be placed inside the demo's `try` block; the result for the bean definition `@Bean("compactMapper") ObjectMapper compactMapper()` is normally `compactMapper`. You can inspect `getResourceDescription()` to trace the configuration, though the exact string varies by environment.

### 14.3. Testing the injection path instead of only getBean()

A good test should verify that `ReportService.buildReport()` actually outputs compact JSON. If `prettyMapper` were injected by mistake, the output would contain indentation/newlines and differ from the expected result. This is a direct signal that `@Qualifier` or assembly is wrong.

### 14.4. Testing scope and lifecycle

- For singletons, two `getBean("compactMapper")` calls in the same context return the same instance.
- For prototypes configured on a `@Bean` method, two normal lookups create different instances; do not mutate state on both assuming they share it.
- For clients with `close`/`shutdown`, test closing the context and observe that callbacks/resources are released.
- For externally owned resources, test that closing the context does **not** close the object when the destroy callback is disabled.

### 14.5. Testing missing dependencies and misconfiguration

If a factory method needs `Environment.getRequiredProperty(...)` and the property does not exist, an error during bean creation is the expected behavior for a required dependency. If a secret is wrong or a vendor client cannot connect, do not "fix" it by catching broadly and returning `null` from `@Bean`; classify configuration errors, network errors, and retry policies per library.

## 15. Design Patterns for Different Types of Libraries

### 15.1. JSON serializer

`@Bean ObjectMapper` is a shared object if configuration is finalized before use. Multiple mappers can be registered for independent policies and injected by qualifier, as in the runnable example.

### 15.2. HTTP client

An HTTP client should usually reuse connection/thread resources when recommended by the library. Create it with a builder from timeout, TLS, and endpoint configuration, then register it with `@Bean`; choose scope and shutdown method according to vendor documentation. Do not assume all HTTP clients share the same thread-safety and lifecycle characteristics.

### 15.3. DataSource / connection pool

A `DataSource` can be created using the pool library's factory/builder and registered via `@Bean`. Provide driver, URL, and authentication, and clearly define who owns the pool. In Spring Boot, auto-configuration for `DataSource` typically already exists; do not manually register a duplicate alongside the built-in bean unintentionally.

### 15.4. Third-party SDK client

Registering via `@Bean` centralizes endpoint, timeout, token provider, and retry policy in one place. If the SDK serves multiple accounts/regions, name each bean and select via `@Qualifier`. Do not embed tokens into constructors in source code; load them via secure configuration.

### 15.5. Test doubles

You can swap a `@Bean` factory method to supply a fake/stub in a test context without modifying library code:

```java
@Configuration(proxyBeanMethods = false)
class TestClockConfig {
    @Bean
    Clock clock() {
        return Clock.fixed(
            Instant.parse("2030-01-01T00:00:00Z"),
            ZoneOffset.UTC
        );
    }
}
```

This snippet is a valid configuration class when importing `Bean`, `Configuration`, `Clock`, `Instant`, `ZoneOffset`. Load **one** appropriate clock configuration for the test context instead of accidentally creating two `Clock`s of the same type and causing injection ambiguity. For objects that are hard to fake, design an application-owned adapter/interface and register the SDK-backed adapter via `@Bean`.

## 16. Self-Practice and Answers

**Question 1.** Why is simply adding `@ComponentScan(basePackages="com.fasterxml.jackson")` not the standard way to create an `ObjectMapper`?

**Answer:** Default component scanning finds classes carrying stereotypes or matching markers; `ObjectMapper` does not need and is not designed to be a Spring component. Declaring `@Bean ObjectMapper ...` lets the application configure the instance deliberately.

**Question 2.** A project has no `@ComponentScan`, yet has registered a `@Configuration` with a `@Bean` factory method. Is the object managed by Spring?

**Answer:** Yes, provided the configuration is loaded/processed and the bean is created successfully. Component scanning is only one of the ways to register beans.

**Question 3.** In the demo there are two `ObjectMapper`s. Why is the factory method `reportService(@Qualifier("compactMapper") ObjectMapper mapper, ...)` not ambiguous?

**Answer:** The qualifier narrows candidates to the bean with the matching name; Spring supplies the compact mapper to the service.

**Question 4.** If `@Qualifier` were removed in the demo, what could happen?

**Answer:** There are two mappers of the same type without a clearly designated default candidate, so dependency injection can throw `NoUniqueBeanDefinitionException`. Do not rely on variable names as a mandatory configuration rule; use explicit qualifiers.

**Question 5.** Do two calls to `context.getBean("compactMapper")` create two mappers?

**Answer:** Not in the default singleton scope; the same bean name in the same context returns the same instance. Switching scope to prototype causes two normal lookups to create two instances.

**Question 6.** Why should `@Configuration(proxyBeanMethods=false)` go hand in hand with parameter injection on `@Bean` methods?

**Answer:** Because calling another `@Bean` method directly is an ordinary Java call and can create an extra instance outside the registered bean. Method parameters are resolved by the container by name/type/qualifier and scope.

**Question 7.** A library object has a `close()` method. Can you assume by default that Spring is allowed to close it on context shutdown?

**Answer:** Ownership must be determined. Spring has destroy-callback inference for eligible close/shutdown methods, yet for objects managed by another environment you may need to disable it via `destroyMethod=""`. Do not treat the presence of `close()` as proof that Spring owns the resource.

**Question 8.** Why can a factory method declaring an interface return type make an injection point by concrete class hard to resolve early?

**Answer:** Spring predicts types from factory method metadata before instances are created; if the declared return type is too general, the concrete type may not yet be known. Declare a sufficiently specific return type or inject consistently by interface.

**Question 9.** If you want to configure a different singleton vendor client in tests, must you edit the library's source?

**Answer:** No. Use test-specific Java configuration to return a fake/differently configured object, or supply the appropriate bean per test context policy while avoiding unintended duplicate registrations.

**Question 10.** Does `@Bean` automatically cause methods of a library client to run in a transaction or be cached?

**Answer:** No. `@Bean` only registers/configures the object in the IoC Container. Transactions, caching, and proxy behaviors require separate infrastructure, annotations, invocation paths, and dependencies.

## 17. References

- [Spring Framework 6.2 — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java.html): overview of configuring beans in Java.
- [Spring Framework 6.2 — Basic Concepts: @Bean and @Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/basic-concepts.html): meaning of bean factory methods and full/lite configuration.
- [Spring Framework 6.2 — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html): factory method parameters, bean names, scopes, lifecycle, init/destroy callbacks.
- [Spring Framework 6.2 — Using the @Configuration Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/configuration-annotation.html): inter-bean dependencies, method interception, and `proxyBeanMethods=false`.
- [Spring Framework 6.2 — Container Dependency Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies.html): how the container resolves dependencies.
- [Jackson Databind — ObjectMapper API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/2.18.2/com/fasterxml/jackson/databind/ObjectMapper.html): mapper API used in the lesson.
- [Spring Framework — Bean Overview](https://docs.spring.io/spring-framework/reference/core/beans/definition.html): bean definitions, metadata, and how Spring manages instances.

**Core knowledge summary:** When a library lacks `@Component`, we create a bean definition using **`@Bean`** on a configuration loaded by Spring. The factory method builds/configures the object; the IoC Container manages dependencies, scope, and lifecycle according to the configuration. Component scanning is for finding candidate classes with matching markers, whereas `@Bean` is the tool for deliberately assembling library objects whose source we cannot edit.
