# Limitations of Calling Binder Directly Outside the Bean Lifecycle in Spring Boot 3.3

## 1. Objectives

Spring Boot 3.3 provides the `org.springframework.boot.context.properties.bind.Binder` API to bind externalized configuration data into a Java type. In the common case, developers declare `@ConfigurationProperties`, register the bean via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, and let Spring Boot manage bean creation, binding, and validation within the application lifecycle.

However, sometimes you need to invoke Binder **directly**:

- Reading a temporary configuration group at a specific point in the program.
- Converting values from an existing `Environment` into a record or POJO.
- Parsing a `MapPropertySource` in a unit test or standalone tool.
- Binding a `Map<String, Integer>` or `List<String>` without creating a Spring bean.
- Taking a configuration snapshot for a short-lived operation.

These operations are supported, yet it is essential to distinguish **what Binder can do** from the **full `@ConfigurationProperties` bean lifecycle**.

**Core principle:**

> `Binder.bind(...)` is an operation that reads, converts, and binds values from `ConfigurationPropertySources` into an object. It does not automatically register that object as a Spring bean, does not invoke the full bean lifecycle, and does not automatically apply all conveniences Spring Boot sets up for `@ConfigurationProperties` beans in `ApplicationContext`.

This article explains these boundaries in Spring Boot **3.3**, from `Environment` preparation, Config Data, placeholders, conversion, and validation to bean lifecycle, configuration changes, concurrency, and testing.

## 2. Two Different Paths to the Same Configuration Object

### 2.1. Path managed by Spring Boot

```text
SpringApplication.run(...)
  |
  +-- Prepare Environment and Config Data
  |      application.properties / YAML / imports / profiles...
  |
  +-- Initialize ApplicationContext and bean definitions
  |
  +-- Instantiate @ConfigurationProperties bean
  |
  +-- Binder binds data into the bean
  |
  +-- Configured BindHandler / conversion / validation
  |
  +-- BeanPostProcessors and Spring initialization steps
  |
  +-- Bean ready for injection into other components
```

Example:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "client")
public class ClientProperties {
    private String host = "localhost";
    private int port = 8080;

    public String getHost() { return host; }
    public void setHost(String host) { this.host = host; }

    public int getPort() { return port; }
    public void setPort(int port) { this.port = port; }
}
```

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

When properly registered, `ClientProperties` is a **Spring bean**. Other components can receive it via constructor injection. Spring Boot manages binding along with the required lifecycle steps.

### 2.2. Path calling Binder directly

```java
Binder binder = Binder.get(environment);
ClientProperties settings = binder
        .bind("client", ClientProperties.class)
        .orElseGet(ClientProperties::new);
```

Here:

1. `Binder.get(environment)` uses the `ConfigurationPropertySources` attached to `Environment`.
2. `bind("client", ClientProperties.class)` reads and binds data under prefix `client`.
3. The result is a Java object created by this call, **not automatically turned into a bean in the Spring container**.
4. If no values bind, `BindResult` may be empty; `orElseGet(...)` in the example is the caller's fallback strategy.
5. Creating an instance manually does not mean Spring processes `@Autowired`, `@PostConstruct`, `BeanPostProcessor`, AOP proxies, or dependency injection on that instance.

**What is not lost:** Binder can still perform relaxed binding, nested object binding, collections, maps, type conversion, and constructor binding when sources, target types, and supporting components are properly configured.

**What does not happen automatically:** a registered Spring bean, container lifecycle steps, validation tied to bean binding, and application refresh behavior.

## 3. Quick Comparison Table

| Capability | Boot-managed `@ConfigurationProperties` | Directly invoked `Binder` |
| --- | --- | --- |
| Read properties by prefix | Yes | Yes |
| Relaxed binding | Yes | Yes with appropriate `ConfigurationPropertySources` |
| Nested objects/List/Map | Yes | Yes, depending on target type and source |
| Convert `Duration`/`DataSize`/enum | Yes | Yes with appropriate conversion service |
| Read `application.yaml`/profiles/imports | Yes after Boot prepares Env | Only if those sources **already exist** in passed Env/sources |
| Auto-create and register Spring bean | Via config props registration mechanism | **No** |
| Inject dependencies into object | By container if object is a bean | **Not automatic** |
| `@PostConstruct`/`InitializingBean` | Part of bean lifecycle | **Not automatic** |
| BeanPostProcessor/AOP proxy | Can apply to Spring beans | **Does not auto-apply to manual objects** |
| `@Validated`/Bean Validation on config bean | Yes when infrastructure is configured | **Not by default**; needs handler/validator or separate validation |
| Custom converters from ApplicationContext | Can be integrated by Boot for bean binding | Do not assume same converters exist in standalone Binder |
| Bean name, scope, disposal callbacks | Managed by container | **None** unless object is registered |
| Updates when source config changes | Not live-updating by default in standard apps | Also **does not auto-refresh** bound objects |
| Usable outside Spring context | Not via normal bean lifecycle | Yes, if sources and needed infrastructure are supplied |
| BindHandler control | Via Boot configuration/infrastructure | Can be passed directly to `bind(...)` |

This table does not mean every `@ConfigurationProperties` bean auto-hot-reloads. In standard Boot apps, configuration binds at startup and does not update when files change. If refresh is needed, a dedicated mechanism designed for it must be used.

## 4. Basic Binder API in Spring Boot 3.3

Key APIs in `org.springframework.boot.context.properties.bind.Binder`:

```java
Binder.get(Environment environment)

binder.bind(String name, Class<T> target)

binder.bind(String name, Bindable<T> target)

binder.bind(String name, Bindable<T> target, BindHandler handler)

binder.bindOrCreate(String name, Class<T> target)

binder.bindOrCreate(String name, Bindable<T> target)
```

Accompanying types:

- `BindResult<T>`: describes a bound result or an absent state.
- `Bindable<T>`: describes target type, generic types, existing instance, and other binding metadata.
- `BindHandler`: allows customizing the binding process, e.g., validation or unbound property behavior.
- `ConfigurationPropertySource`: data source matching Spring Boot's property-name model.
- `ConfigurationPropertySources`: adapter/registry bridging Spring `PropertySource` to sources Binder reads.

### 4.1. Reading a scalar

```java
Integer retryCount = Binder.get(environment)
        .bind("app.retry-count", Integer.class)
        .orElse(3);
```

If Binder finds no value for `app.retry-count`, `orElse(3)` returns 3. If the property is `0`, the result can be `0`; default 3 is not used simply because the value is zero.

### 4.2. Reading a POJO

```java
ClientProperties properties = Binder.get(environment)
        .bind("client", ClientProperties.class)
        .orElseGet(ClientProperties::new);
```

Binder can invoke the no-arg constructor and setters via JavaBean binding. This code does not invoke `@ConfigurationPropertiesScan` and does not require `@ConfigurationProperties` on the class to specify a prefix: the prefix is already passed to `bind(...)`.

### 4.3. Reading a Map with generic types

```java
import java.util.Map;
import org.springframework.boot.context.properties.bind.Bindable;

Map<String, Integer> limits = Binder.get(environment)
        .bind(
            "app.retry-limits",
            Bindable.mapOf(String.class, Integer.class))
        .orElseGet(Map::of);
```

When present:

```properties
app.retry-limits.billing=3
app.retry-limits.search=0
```

Binder can create `Map<String,Integer>` with `billing → 3`, `search → 0`. Use `Bindable.mapOf(...)` to preserve generic info; passing raw `Map.class` fails to convey the key/value types to convert.

### 4.4. Reading a List with element type

```java
import java.util.List;

List<String> regions = Binder.get(environment)
        .bind("app.regions", Bindable.listOf(String.class))
        .orElseGet(List::of);
```

With:

```properties
app.regions[0]=vn
app.regions[1]=sg
```

the result can be `["vn", "sg"]`. Even when invoking Binder manually, collection binding rules across sources of different precedence still apply: Lists usually come from one winning source rather than concatenating Lists.

## 5. Limitation 1: Environment Must Be Prepared

In Spring Boot 3.3, `Binder.get(environment)` requires `Environment` to have appropriate `ConfigurationPropertySources` attached. This requirement is stated in the Javadoc of `Binder.get(Environment)` itself.

### 5.1. Inside a normal SpringApplication

When a post-startup bean receives `Environment` via constructor injection or a method parameter, Spring Boot has already set up the configuration properties infrastructure during startup.

`ApplicationRunner` example:

```java
package com.example.demo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class StartupDiagnostics {

    @Bean
    ApplicationRunner showRetryCount(Environment environment) {
        return args -> {
            int retries = Binder.get(environment)
                    .bind("app.retry-count", Integer.class)
                    .orElse(3);

            System.out.println("Effective retry count: " + retries);
        };
    }
}
```

By the time `ApplicationRunner` runs, Boot's `Environment` has gone through the standard Config Data phase. Results use existing property sources in precedence order. The goal here is **reading one value for diagnostics**, not creating a duplicate config bean to replace a managed one.

### 5.2. With a manually created StandardEnvironment

If you instantiate a standalone `StandardEnvironment`, do not assume calling `Binder.get(env)` works without attaching adapters.

Example preparing the environment manually:

```java
package com.example.demo;

import java.util.Map;

import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.ConfigurationPropertySources;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;

public class StandaloneBinderExample {

    public static void main(String[] args) {
        StandardEnvironment env = new StandardEnvironment();

        env.getPropertySources().addFirst(
            new MapPropertySource("manual-config", Map.of(
                "app.retry-count", "4",
                "app.enabled", "false"
            ))
        );

        ConfigurationPropertySources.attach(env);

        int count = Binder.get(env)
                .bind("app.retry-count", Integer.class)
                .orElse(3);

        boolean enabled = Binder.get(env)
                .bind("app.enabled", Boolean.class)
                .orElse(true);

        System.out.println(count);   // 4
        System.out.println(enabled); // false
    }
}
```

**Meaning of `attach(env)`:** connects Spring `Environment` to `ConfigurationPropertySources` so Binder can look up properties by configuration property name. It **does not start a Spring Boot application**, does not load `application.yaml`, does not resolve `spring.config.import`, and does not run `ConfigDataEnvironmentPostProcessor`.

`StandardEnvironment` also includes default property sources like system properties and OS environment; in the example, `manual-config` is added first so the illustrative data takes precedence. For strictly isolated unit tests, use tightly controlled data and environments to prevent developer machine variables from affecting tests.

### 5.3. If you want to avoid attaching to a shared Environment

You can create Binder directly from known `ConfigurationPropertySource`s or adapters over Spring `PropertySource`s:

```java
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.ConfigurationPropertySources;
import org.springframework.core.env.StandardEnvironment;

StandardEnvironment env = new StandardEnvironment();

Binder binder = new Binder(
        ConfigurationPropertySources.from(env.getPropertySources()));
```

This is a way to construct Binder manually from sources. **However**, when building Binder via a minimal constructor, realize that other components such as **placeholder resolvers** and **custom conversion services** may not be configured the way `Binder.get(environment)` configures them.

If data contains `${...}` placeholders, use `Binder.get(env)` on an attached Environment or explicitly pass a suitable `PlaceholdersResolver`. Never treat both Binder initialization styles as completely equivalent when a project has complex placeholders/custom converters.

## 6. Limitation 2: Binder Does Not Automatically Load Config Data

A common false assumption:

```java
Environment env = new StandardEnvironment();
Binder binder = Binder.get(env);
```

Even after attaching `ConfigurationPropertySources`, a manually created Environment **does not automatically** read files like:

```text
src/main/resources/application.properties
src/main/resources/application.yaml
config/application-prod.yaml
```

Those files belong to Spring Boot's **Config Data** workflow; they are processed during startup by specialized components.

Features such as:

- `spring.config.import`.
- `spring.config.location`, `spring.config.additional-location`.
- `application-{profile}.properties`, `application-{profile}.yaml`.
- Multi-document YAML separated by `---`.
- Multi-document .properties separated by `#---`.
- `spring.config.activate.on-profile`.
- `spring.config.activate.on-cloud-platform`.

are all tied to the appropriate Config Data loading step. A standalone Binder **is not a Config Data loader** and will not re-trigger file discovery or profile processing.

### 6.1. Easy-to-misunderstand example

```properties
# application.properties
spring.config.import=classpath:/config/remote.properties
app.client.timeout=5s
```

If a manual `StandardEnvironment` only holds default PropertySources, `Binder` does not go find `application.properties` and import `remote.properties`. Putting literal `spring.config.import=...` into a `MapPropertySource` does not make Binder execute imports either.

To use data loaded by Boot, call Binder **after** Spring Boot has prepared Environment. To use data from external files outside Boot, supply a source already read/converted into a suitable `ConfigurationPropertySource`, or use an appropriate Config Data mechanism at startup.

### 6.2. Timing of Binder invocation determines available sources

If code reads inside a very early `EnvironmentPostProcessor`, certain property sources or profile-specific data may **not yet be added**, depending on ordering. Do not assume values read by an early Binder match those after Boot startup finishes.

For critical startup properties like `spring.config.name`, `spring.config.location`, or `spring.main.*`, identify the exact phase of use. A Binder invoked late cannot rewind time to change file-loading decisions already made.

## 7. Limitation 3: Bound Objects Do Not Automatically Become Beans

Example:

```java
ClientProperties raw = Binder.get(environment)
        .bindOrCreate("client", ClientProperties.class);
```

`raw` is a plain Java object. The call above **does not**:

- Register a `BeanDefinition` in `ApplicationContext`.
- Assign a bean name or scope.
- Perform dependency injection on `@Autowired` fields.
- Run `BeanPostProcessor` / `BeanFactoryPostProcessor` on that object.
- Trigger `@PostConstruct`/`InitializingBean.afterPropertiesSet()` via the bean lifecycle.
- Create an AOP proxy just because the class or method carries annotations.
- Manage `@PreDestroy` or `DisposableBean` when the context closes.
- Register the object so it can be `@Autowired` into another service.

### 7.1. Example where @PostConstruct is not invoked

```java
package com.example.demo.config;

import jakarta.annotation.PostConstruct;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "client")
public class ClientProperties {

    private String host = "localhost";
    private boolean initialized;

    public String getHost() { return host; }
    public void setHost(String host) { this.host = host; }

    public boolean isInitialized() { return initialized; }

    @PostConstruct
    public void init() {
        initialized = true;
    }
}
```

After a direct call:

```java
ClientProperties p = Binder.get(environment)
        .bindOrCreate("client", ClientProperties.class);
```

you can only be sure Binder attempted to bind properties. `p.isInitialized()` can still be `false` because `@PostConstruct` is not invoked by Binder automatically. Only when the class is created and managed by the container as a Spring bean do lifecycle callbacks have a chance to run.

**Better design:** property objects should primarily hold data. If you need resource initialization with side effects, place it in a Spring-managed service that consumes `ClientProperties`, rather than opening connections/threads or registering callbacks inside properties getters/setters.

### 7.2. @ConfigurationProperties does not perform magic on its own

A class with:

```java
@ConfigurationProperties(prefix = "client")
public class ClientProperties { /* ... */ }
```

is not necessarily a bean if unregistered. Likewise, passing that class into `Binder.bind("client", ClientProperties.class)` does not register it in the context.

`@ConfigurationPropertiesScan` and `@EnableConfigurationProperties` are **bean registration** mechanisms. `Binder` is a **data binding** mechanism. They can work together, yet they are not the same operation.

### 7.3. Intentionally returning the result from a @Bean method

If the object is constructed inside a `@Bean` method:

```java
@Configuration(proxyBeanMethods = false)
class ClientConfiguration {

    @Bean
    ClientProperties clientProperties(Environment environment) {
        return Binder.get(environment)
                .bindOrCreate("client", ClientProperties.class);
    }
}
```

then **the return value of the `@Bean` method** is managed by the container after the method runs, and Spring can apply appropriate bean lifecycle steps to that bean. This differs from creating the object in a utility method outside the container.

Still, this is not always necessary; for standard `@ConfigurationProperties`, it is usually simpler to write:

```java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ClientProperties.class)
class ClientConfiguration {
}
```

Do not inadvertently combine manual binding with `@ConfigurationProperties` binding on the same bean, as it can cause duplicate binding or obscure failure points.

## 8. Limitation 4: Validation Does Not Run Automatically Like Bean Binding

Suppose a configuration class has:

```java
package com.example.demo.config;

import jakarta.validation.constraints.Min;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "worker")
public class WorkerProperties {

    @Min(1)
    private int threads = 4;

    public int getThreads() { return threads; }
    public void setThreads(int threads) {
        this.threads = threads;
    }
}
```

And source:

```properties
worker.threads=0
```

Binding the number `0` to `int` succeeds as **conversion**, yet violates `@Min(1)`.

When `WorkerProperties` is registered by Spring Boot as a `@ConfigurationProperties` bean and a compatible Bean Validation provider is present, validation can fail startup. However:

```java
WorkerProperties value = Binder.get(environment)
        .bindOrCreate("worker", WorkerProperties.class);
```

should not be assumed to guarantee running the **exact validation mechanism** of bean-managed `@ConfigurationProperties`. `@Validated` is metadata for validation infrastructure; it does not automatically turn every plain Binder call into a validated call.

### 8.1. Manual checking with BindHandler

Spring Boot includes `ValidationBindHandler` in the package:

```java
org.springframework.boot.context.properties.bind.validation
```

Example in a component that already holds a suitable Spring `Validator`:

```java
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.bind.validation.ValidationBindHandler;
import org.springframework.core.env.Environment;
import org.springframework.validation.Validator;

public final class ManualValidatedBinding {

    private final Environment environment;
    private final Validator validator;

    public ManualValidatedBinding(Environment environment,
                                  Validator validator) {
        this.environment = environment;
        this.validator = validator;
    }

    public WorkerProperties load() {
        return Binder.get(environment)
                .bind(
                    "worker",
                    Bindable.of(WorkerProperties.class),
                    new ValidationBindHandler(validator))
                .orElseGet(WorkerProperties::new);
    }
}
```

**Points to understand:**

- Requires a `Validator` that actually supports `WorkerProperties` and has appropriate validation infrastructure.
- `ValidationBindHandler` runs on that specified `bind(...)` call; its use once does not add validation to `Binder.bind(...)` elsewhere.
- In the example, if no properties are bound, the `orElseGet(WorkerProperties::new)` branch creates an object **outside the bind call**; this fallback object must be validated separately if policy requires validation even when sources are absent.
- If fail-fast behavior is needed for mandatory properties, clearly define behavior when `BindResult` is empty and when the object violates constraints.

Besides `ValidationBindHandler`, you can run Bean Validation on the bound result via an injected infrastructure service. That option is easy to control when the application needs multiple business rules or independent policies.

### 8.2. Conversion errors still differ from validation errors

```properties
worker.threads=abc
```

Here the error happens when converting `"abc"` to `int`, before `@Min(1)` can ever be evaluated. `ValidationBindHandler` is not a converter-error fixer; it only validates bound results.

Distinguish `BindException`/`ConversionFailedException` from Bean Validation violations to report accurate messages to operators.

### 8.3. Custom BindHandlers must be passed intentionally

If the bean-managed pipeline has `BindHandler`s installed by Boot via configuration-properties infrastructure/advisors, a standalone Binder **does not automatically** receive that same handler chain. If you need to:

- Reject unbound properties.
- Record metrics or track binding.
- Validate against constraints.
- Handle errors with custom logic.

configure the supported `BindHandler` **directly on the Binder call**, or use managed bean binding if that is the real goal.

## 9. Limitation 5: Converters and Placeholders May Differ

### 9.1. Binder's default conversion

Binder supports common types via its conversion service, such as:

- `String` → `int`, `Integer`, `boolean`, `Boolean`.
- Duration strings → `java.time.Duration`.
- Size strings → `DataSize`.
- Enum names → declared enums.
- Nested configuration → JavaBean/constructor-bound targets.
- Lists/Maps with identifiable element/key/value types.

So using Binder directly does not mean you have to parse every number or Duration yourself.

### 9.2. Custom converters from Spring context

Suppose the application defines:

```java
@Component
@ConfigurationPropertiesBinding
public class StringToRegionConverter
        implements Converter<String, Region> {

    @Override
    public Region convert(String source) {
        return Region.parse(source);
    }
}
```

In bean-managed configuration-properties binding, Spring Boot can integrate properly registered converters. But with a standalone `Binder`, especially created via `new Binder(...)` outside `ApplicationContext`, **do not assume this converter is present**.

If specialized conversion is required, options include:

1. Use bean-managed `@ConfigurationProperties` so Boot manages the infrastructure.
2. Configure an appropriate `ConversionService` and pass it to the matching Binder constructor.
3. Read the value using a Binder-supported intermediate type, then convert via a dedicated service with clear error handling.

Do not solve it by adding a converter bean and expecting every `new Binder(...)` call in unit tests or CLI tools to discover it automatically.

### 9.3. Placeholders in values

Example:

```properties
app.base-url=https://api.example.test
app.client-url=${app.base-url}/v1
```

In a prepared Environment, `Binder.get(environment)` can use an appropriate resolver to resolve property-reference placeholders. Yet if you construct manually:

```java
Binder binder = new Binder(
        ConfigurationPropertySources.from(env.getPropertySources()));
```

do not assume a minimally constructed Binder gets the same `PlaceholdersResolver` and context as a Binder created from Environment.

If the application needs placeholders, use `Binder.get(environment)` after `ConfigurationPropertySources.attach(env)`, or pass an appropriate `PlaceholdersResolver` to the Binder constructor. Never let a literal `${app.base-url}` sneak into a Java field only to be discovered when the HTTP client uses the URL.

## 10. Limitation 6: No Automatic Dependency Injection or AOP

A configuration object having:

```java
public class Settings {
    @Autowired
    private SomeService service;
}
```

when created by `Binder.bindOrCreate(...)` is not guaranteed to have `SomeService` injected by Spring. Accessing that field can encounter `null` if it bypassed the bean lifecycle.

Likewise, annotations like `@Transactional`, `@Async`, or `@Cacheable` typically rely on Spring proxies/infrastructure. An object returned by Binder does not automatically receive a proxy merely because its methods carry annotations.

**Recommendation:** do not design `@ConfigurationProperties` as a service with injected dependencies. Separate into:

```text
Configuration object (data and validation only)
        |
        v
Spring-managed service (dependency injection, lifecycle, logic)
```

Example:

```java
@Service
public class ClientService {

    private final ClientProperties settings;
    private final HttpClient httpClient;

    public ClientService(ClientProperties settings,
                         HttpClient httpClient) {
        this.settings = settings;
        this.httpClient = httpClient;
    }
}
```

In the example, `ClientProperties` is registered as a bean, `ClientService` is also a bean, and injection happens via constructor. If using manual Binder to obtain a temporary configuration snapshot, pass that snapshot as **data** into the service instead of treating it as a Spring-managed component.

## 11. Limitation 7: No Auto-Refresh After Sources Change

Suppose at startup:

```properties
app.retry-count=3
```

Then code runs:

```java
var snapshot = Binder.get(environment)
        .bind("app.retry-count", Integer.class)
        .orElse(0);
```

`snapshot` is `3` at call time. Later, if an external system modifies a property source or config file outside the process to `app.retry-count=5`, `snapshot` **does not automatically become 5**.

Keep these distinct:

- **Editing a file on disk:** standard Spring Boot does not reload Config Data just because a file changed.
- **Mutating a `MutablePropertySource` in the same Environment:** new reads/binds can observe new values if the source updated properly, yet previously bound objects still do not update themselves.
- **Binder holding references to sources:** this is not a file watcher/reloader/callback system for existing beans.
- **Spring Cloud refresh or custom solutions:** separate infrastructure, not an automatic feature of `Binder.bind`.

### 11.1. Immutable snapshots prevent confusion

With a record:

```java
public record RetryPolicy(
        int maxRetries,
        java.time.Duration backoff) {
}
```

When running:

```java
RetryPolicy policy = Binder.get(environment)
        .bind("app.retry", RetryPolicy.class)
        .orElse(new RetryPolicy(3, java.time.Duration.ofSeconds(1)));
```

`policy` is a data structure at binding time. Treat it as a **snapshot**. If configuration changes and the application requires updated policies, design a process to obtain a fresh snapshot and hand it over safely across threads/requests.

### 11.2. Be careful when rebinding into the same mutable object

```java
ClientProperties existing = new ClientProperties();

Binder.get(environment).bind(
        "client",
        Bindable.ofInstance(existing));
```

`Bindable.ofInstance(existing)` lets Binder use the existing instance as the target. Binding can mutate object state **in place**, so never do this concurrently while threads are reading the object without synchronization and clear snapshot rules.

Do not assume `Binder` or created JavaBean objects are thread-safe/hot-reloadable just because they come from Spring Boot. A reliable strategy is binding into a new instance, validating, and swapping an immutable/protected reference if dynamic config updates are truly needed.

## 12. BindResult: Empty Result Does Not Mean Valid Defaults Exist

`Binder.bind(...)` returns `BindResult<T>`. It does not always contain an object.

Example:

```java
BindResult<ClientProperties> result = Binder.get(environment)
        .bind("client", ClientProperties.class);
```

If no properties match prefix `client`, the result can be **unbound**. Ways to handle:

```java
ClientProperties a = result.orElseGet(ClientProperties::new);
```

Or:

```java
if (result.isBound()) {
    ClientProperties b = result.get();
}
```

Do not call `result.get()` before knowing whether it is bound; the API throws an exception when no value exists. `bindOrCreate(...)` is another option when you need a target instantiated even if binding finds no data, yet the newly created object still needs adequate constructors/defaults to be in a valid state.

### 12.1. Missing entire prefix vs. missing a child property

Suppose the JavaBean is:

```java
public class RetryProperties {
    private int maxRetries = 3;
    private boolean enabled = true;

    public int getMaxRetries() { return maxRetries; }
    public void setMaxRetries(int x) { maxRetries = x; }

    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean x) { enabled = x; }
}
```

If:

```properties
app.retry.enabled=false
```

then Binder can create an object with:

```text
maxRetries=3
enabled=false
```

If **there are no `app.retry.*` keys**, calling `bind("app.retry", RetryProperties.class)` can yield no result, and code must pick a fallback. Choose `orElseGet(RetryProperties::new)` to preserve field initializers; choose fail-fast if the prefix is mandatory.

### 12.2. Do not confuse 0/false/empty with missing

```properties
app.retry.max-retries=0
app.retry.enabled=false
```

`0` and `false` are explicit values. Binder does not substitute defaults 3/true just because they are "falsy." Empty strings have their own semantics depending on target type and conversion, and must not automatically be treated as "missing source."

## 13. Constructor Binding, Records, and @DefaultValue When Calling Directly

Binder can bind types designed for constructor binding, not only JavaBeans with setters.

Example:

```java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.bind.DefaultValue;

public record RetryOptions(
        @DefaultValue("3") int maxRetries,
        @DefaultValue("1s") Duration backoff,
        @DefaultValue("false") boolean enabled) {
}
```

Usage:

```java
RetryOptions options = Binder.get(environment)
        .bind("app.retry", RetryOptions.class)
        .orElse(new RetryOptions(3, Duration.ofSeconds(1), false));
```

If present:

```properties
app.retry.max-retries=0
app.retry.backoff=500ms
app.retry.enabled=false
```

Binder can construct the record with `maxRetries=0`, `backoff=500ms`, and `enabled=false`. Spring Boot's `@DefaultValue` applies when **a component property is not found** during binding; it does not override explicit `0` or `false` values.

**Important note:** `@DefaultValue` on record components does not turn `bind(...)` into an instruction to instantiate an object for a **completely absent prefix**. Calling code should handle empty `BindResult` or use a suitable API if an object is always required. Do not confuse constructor-binding defaults with Spring bean registration.

### 13.1. Constructor binding is not an @Autowired constructor

A constructor receiving configuration:

```java
public RetryOptions(int maxRetries, Duration backoff, boolean enabled)
```

is not a constructor asking Spring to inject beans of type `int`/`Duration`. Binder supplies values from property sources matched by parameter/record component names. Never put `DataSource` or services into a configuration record expecting Binder to pull beans from the context.

## 14. BindHandler: Per-Call Behavior Control

`BindHandler` in Spring Boot 3.3 provides hooks during binding, such as:

- `onStart`: starting to bind a property.
- `onSuccess`: bound successfully.
- `onFailure`: bind failed.
- `onFinish`: finished processing.

Spring Boot includes handlers for cases like validation, ignoring specific errors, or reporting unbound properties.

**Do not** write custom handlers just to "make Binder work," because for standard configuration beans Boot already manages the required infrastructure. Use handlers when there is a clear requirement for validation, strictness, or observing manual binding.

### 14.1. NoUnboundElementsBindHandler

Spring Boot provides:

```java
org.springframework.boot.context.properties.bind.handler.NoUnboundElementsBindHandler
```

This handler detects properties within the binding scope that appeared yet were not bound into the target, when configured properly. In manual binding, there is no guarantee unknown keys are rejected if you **do not attach a handler** or equivalent strictness mechanism.

Still, unknown/unbound detection depends on how sources enumerate keys and property name structures. Do not treat this handler as an absolute schema validator for every kind of custom `PropertySource`.

### 14.2. Do not hide conversion errors with an ignore handler

Some BindHandlers allow continuing past bind errors or returning fallback values. However, if `app.retry-count=abc` and the application needs an integer, silently ignoring the error can leave it running with stale/unexpected values. For critical operational settings, prefer failing fast and reporting errors with source context.

## 15. Using Binder in Unit Tests Without a Spring Context

A unit test can create a minimal `Environment`, add a Map source, attach it, and bind. Example:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.ConfigurationPropertySources;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;

class ManualBinderTest {

    @Test
    void bindsFromManualMap() {
        StandardEnvironment env = new StandardEnvironment();

        env.getPropertySources().addFirst(
            new MapPropertySource(
                "test-values",
                Map.of(
                    "client.host", "api.example.test",
                    "client.port", "9090"
                )
            )
        );

        ConfigurationPropertySources.attach(env);

        ClientProperties result = Binder.get(env)
                .bindOrCreate("client", ClientProperties.class);

        assertEquals("api.example.test", result.getHost());
        assertEquals(9090, result.getPort());
    }
}
```

This example tests **Binder and the model** against an explicit source. It does not prove:

- Config Data files are discovered/loaded from the right locations by Spring Boot.
- Profile-specific files are selected by `spring.profiles.active`.
- `@ConfigurationPropertiesScan` creates the bean properly.
- `@Validated` fails fast inside a real `ApplicationContext`.
- Custom Spring bean converters are integrated properly by Boot.
- `@PostConstruct` and BeanPostProcessors execute properly.
- Test properties or OS environment overrides have production-like precedence.

To test those, use tests with a Spring context, such as `ApplicationContextRunner` or `@SpringBootTest` depending on the goal.

## 16. Testing Behavior of Bean-Managed @ConfigurationProperties

`ApplicationContextRunner` from `spring-boot-test` spins up a lightweight ApplicationContext to verify registration/binding of a configuration bean.

Example:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class ClientConfigContextTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withUserConfiguration(Config.class);

    @Test
    void bindsManagedBean() {
        runner.withPropertyValues(
                "client.host=api.example.test",
                "client.port=9090")
            .run(context -> {
                assertThat(context).hasNotFailed();
                ClientProperties props =
                        context.getBean(ClientProperties.class);
                assertThat(props.getHost())
                        .isEqualTo("api.example.test");
                assertThat(props.getPort()).isEqualTo(9090);
            });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(ClientProperties.class)
    static class Config {
    }
}
```

With the context runner, property values are supplied directly and the configuration bean is Spring-managed. To also verify the **actual Config Data / profile-file loading phase**, write an integration test booting the matching workflow; an `ApplicationContextRunner` does not replicate every step of `SpringApplication` by default.

### 16.1. Testing Bean Validation

When a property has `@Validated`/constraints and a Bean Validation provider exists:

```properties
worker.threads=0
```

A context test can verify startup fails due to `@Min(1)`. A pure Binder test should separately test the handler/validator used by the direct bind call.

Do not compare the two tests solely by `int threads` after binding, because a direct unvalidated Binder can return 0 while managed bean binding rejects the context. That is a lifecycle/infrastructure difference, not broken relaxed binding.

## 17. Combining Binder with Bean Initialization Logic: Choosing the Right Point

Design options:

### Option A — Let Boot manage configuration automatically

```java
@ConfigurationProperties(prefix = "client")
public class ClientProperties {
    // JavaBean accessors or constructor-bound model
}
```

```java
@SpringBootApplication
@ConfigurationPropertiesScan
class DemoApplication {
}
```

Use this when configuration is a long-lived part of the application needing injection, validation, metadata, and standard startup Config Data sources.

### Option B — @Bean method returning a constructed object

```java
@Configuration(proxyBeanMethods = false)
class ClientConfig {

    @Bean
    Client client(ClientProperties properties) {
        return new Client(
                properties.getHost(),
                properties.getPort());
    }
}
```

`Client` is an illustrative business class. When a service/client needs real connections, construct it from the managed configuration bean inside a `@Bean` method. There is no need to use Binder manually inside this method.

### Option C — Direct Binder for a local snapshot

```java
public record QueryOptions(int limit, boolean includeArchived) {
}
```

```java
QueryOptions options = Binder.get(environment)
        .bind("report.query", QueryOptions.class)
        .orElse(new QueryOptions(100, false));
```

Suitable when a group of values is needed for a short operation and Spring does not need to manage the resulting object. Verify limits and snapshot consistency before using it.

### Option D — Binder in a standalone tool

A CLI tool that does not boot Spring Boot can:

1. Create an appropriate `Environment` or `ConfigurationPropertySources`.
2. Load data into the chosen sources.
3. Configure placeholders/conversion/validation as needed.
4. Bind to the target type.
5. Handle missing/invalid values.
6. Close self-created resources per its own lifecycle.

In this approach, **do not expect** Spring Boot to discover Config Data, instantiate beans, or run `ApplicationContext` callbacks.

## 18. No Automatic Configuration Metadata or Actuator Bean Information

`spring-boot-configuration-processor` runs at compile time and detects `@ConfigurationProperties` types in matching source code; it is not triggered by runtime `Binder.bind` calls.

If you only have a utility:

```java
SomeOptions opts = Binder.get(environment)
        .bind("custom", SomeOptions.class)
        .orElse(null);
```

that call does not automatically produce:

- `META-INF/spring-configuration-metadata.json`.
- A `@ConfigurationProperties` bean entry in Actuator `/actuator/configprops`.
- IDE autocomplete for prefix `custom`.
- A runtime property description/schema.

If you want IDE support for manually read properties, author `META-INF/additional-spring-configuration-metadata.json` and let the annotation processor merge it during the build. That is **metadata tooling**, not a side effect of Binder.

If the object is not a Spring bean, do not expect Actuator to list it as a container-tracked configuration properties bean.

## 19. Reading Simple Values: Environment or Binder?

When you need a single scalar with no nested structure:

```java
String url = environment.getProperty(
        "client.base-url", "http://localhost:8080");
```

may suffice. Binder is helpful when you want Boot-style typed conversion:

```java
java.time.Duration timeout = Binder.get(environment)
        .bind("client.connect-timeout",
              java.time.Duration.class)
        .orElse(java.time.Duration.ofSeconds(3));
```

For multiple related fields:

```java
ClientProperties config = Binder.get(environment)
        .bindOrCreate("client", ClientProperties.class);
```

yet if that object is stable application configuration, bean-managed `@ConfigurationProperties` is usually clearer.

**Decision criteria:**

| Situation | Preferred approach |
| --- | --- |
| Read one String for diagnostics | `Environment.getProperty(...)` |
| Read one scalar with type conversion | `Environment.getProperty(key, Type.class)` or Binder when Boot semantics needed |
| Bind local record/Map/List | Direct Binder + result handling |
| Configuration shared across services | Managed `@ConfigurationProperties` |
| Need startup validation | Managed `@ConfigurationProperties` with validation |
| Need Config Data ordering, imports, and profiles | SpringApplication prepares Env first |
| Need hot reload | Separate refresh mechanism, do not rely on a one-off Binder |
| Need a class with Spring dependencies | Spring-managed service/bean, not a standalone Binder DTO |

Do not overuse Binder inside every getter or every HTTP request when the configuration is actually a static set of values throughout the application lifecycle.

## 20. Common Mistakes When Calling Directly

### Mistake 1 — `Binder.get(new StandardEnvironment())` does not behave as expected

**Cause:** `ConfigurationPropertySources` may not have been attached yet.

**Fix:** for a standalone `ConfigurableEnvironment`, call `ConfigurationPropertySources.attach(env)` first; in a normal Spring Boot environment, use the env prepared by the container.

### Mistake 2 — Reading application.yaml yet result is missing

**Cause:** a manually constructed `StandardEnvironment` does not run the Config Data loader.

**Fix:** bind against an Environment prepared by `SpringApplication` or load specific sources appropriately.

### Mistake 3 — Object has @PostConstruct yet remains uninitialized

**Cause:** Binder instantiates a Java object; it does not invoke the bean lifecycle.

**Fix:** move the bean/service into the container if lifecycle is needed, or remove side effects from the configuration object.

### Mistake 4 — @Autowired field is null

**Cause:** the returned object is not a managed bean.

**Fix:** do not place dependencies inside configuration DTOs; use constructor injection on managed services.

### Mistake 5 — @Validated does not fail when directly binding `threads=0`

**Cause:** direct Binder does not automatically include the same validation handler.

**Fix:** pass `ValidationBindHandler` with a suitable validator or validate the result manually; if startup fail-fast is needed, use managed properties.

### Mistake 6 — Custom converter works in beans but not in a CLI tool

**Cause:** a standalone Binder does not automatically pull every converter registered in a Spring context.

**Fix:** supply the appropriate conversion service or move binding to the managed infrastructure.

### Mistake 7 — `${...}` values are not resolved

**Cause:** building a minimal Binder from sources without configuring a matching placeholder resolver.

**Fix:** use `Binder.get(environment)` on an attached Env or supply a suitable resolver.

### Mistake 8 — Changing application.properties does not change the object

**Cause:** a one-off Binder returns a snapshot; there is no live reload.

**Fix:** address refresh needs separately and pass fresh snapshots safely.

### Mistake 9 — `BindResult.get()` throws an exception

**Cause:** no properties bound under the prefix.

**Fix:** check `isBound()` or use `orElse(...)`/`orElseGet(...)`/`bindOrCreate(...)` per contract.

### Mistake 10 — Binding Map.class gives wrong key/value types

**Cause:** missing generic type metadata.

**Fix:** `Bindable.mapOf(String.class, Integer.class)` or `Bindable.of(ResolvableType)`.

### Mistake 11 — Binding into an object used by multiple threads

**Cause:** mutable instance gets updated mid-flight.

**Fix:** bind into a new object, validate, then swap snapshots safely rather than mutating a shared object uncontrolled.

### Mistake 12 — Mistyped property goes unreported by Binder

**Cause:** default binding is not an omniscient schema validator; unknown keys can go unbound without throwing.

**Fix:** use strict handlers/validation/tests when needed, and verify metadata/sources clearly.

### Mistake 13 — Looking only at Binder error without checking source precedence

**Cause:** CLI/env/profile can override the value in the file you are inspecting.

**Fix:** check the effective value and origin; log non-sensitive info or use secured diagnostic tools.

## 21. Diagnosing Binder Errors Directly

Example helper classifying binding:

```java
package com.example.demo;

import org.springframework.boot.context.properties.bind.BindException;
import org.springframework.boot.context.properties.bind.BindResult;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;

public class ConfigReader {

    private final Environment environment;

    public ConfigReader(Environment environment) {
        this.environment = environment;
    }

    public int retryCount() {
        try {
            BindResult<Integer> result = Binder.get(environment)
                    .bind("app.retry-count", Integer.class);

            if (!result.isBound()) {
                return 3;
            }

            return result.get();
        } catch (BindException ex) {
            throw new IllegalStateException(
                "Invalid configuration: app.retry-count", ex);
        }
    }
}
```

This code deliberately separates:

- **No binding result** → default 3 per application policy.
- **Valid value** → returns the converted integer.
- **Bind/conversion error** → reports error with key context while preserving the original exception.

A direct Binder call is not necessarily wrapped in the exact same exception chain as `@ConfigurationProperties` bean registration at startup. To investigate issues, inspect `ex.getCause()`, target type, source name/origin when available, and non-sensitive raw values.

Never log passwords, tokens, or secrets inside custom exception messages.

## 22. Testing Boundaries Transparently

Tests should be split into two groups, rather than expecting a single Binder unit test to verify every aspect of Spring Boot startup:

| Test | What it verifies | What it does NOT verify automatically |
| --- | --- | --- |
| Binder + MapPropertySource + attach | Relaxed names, conversion, class binding, BindResult | Config Data/profiles/bean lifecycle |
| Binder with ValidationBindHandler | Validation on the configured call | Automatic validation of all other calls |
| Binder with custom ConversionService | Passed converter works | Spring Boot auto-discovering all converter beans |
| ApplicationContextRunner + EnableConfigurationProperties | Managed binding/injection/validation in configured context | All Config Data startup behavior |
| SpringBootTest with profiles/files | Full bootstrap integration, per test setup | Production hot reload |
| Manual rebind with MutablePropertySource | New call observes updated source data | Auto-updating old objects |
| Running in production-like container | Real OS env and precedence | Immutability across deployments |

If you modify Binder calls in early-running code, add an integration test simulating the exact **timing** when configuration sources are prepared, not just a simple `Map`-reading unit test.

## 23. Checklist When Deciding to Use Binder Outside the Bean Lifecycle

- [ ] Do I truly need manual Binder, or would a `@ConfigurationProperties` bean be simpler?
- [ ] Is `Environment` prepared and attached with proper `ConfigurationPropertySources`?
- [ ] If creating a standalone `StandardEnvironment`, did I attach properly?
- [ ] Is the data in an existing PropertySource, or does it depend on Config Data loaders, imports, and profiles?
- [ ] Is the call guaranteed to execute after the required sources have been loaded?
- [ ] Do prefixes and property names consistently use lowercase kebab-case?
- [ ] Have I handled empty `BindResult` instead of blindly calling `get()`?
- [ ] Are generic types preserved for Lists/Maps via `Bindable`?
- [ ] Are placeholders resolved by the current Binder's resolver?
- [ ] Does any type require a custom converter not supplied to this Binder?
- [ ] Is validation needed? If so, did I pass `ValidationBindHandler` or validate the result?
- [ ] Are unknown or malformed properties handled per a proper fail-fast policy?
- [ ] Have I avoided mistaking a bound object for a Spring bean with DI/lifecycle/AOP?
- [ ] If the object needs to be injected, have I registered a managed bean properly?
- [ ] Have I avoided recreating Binder and rebinding static config on every request?
- [ ] If config changes dynamically, have I designed rebind/refresh and thread-safety?
- [ ] Do diagnostic logs omit secrets and preserve exception causes?
- [ ] Are manual Binder unit tests and managed-bean integration tests clearly separated?
- [ ] Are runtime config, defaults, validation, and IDE metadata managed at the right layers?

## 24. Conclusion and Key Takeaways

Direct `Binder` usage **is not "weak" at type-safe binding**: it still matches property names, converts values, and constructs objects from configuration data. However, **a single binding call does not equal the entire ApplicationContext lifecycle**.

Remember the six boundaries:

1. **Sources:** Binder only sees `ConfigurationPropertySources` provided/attached; it does not discover Config Data automatically.
2. **Timing:** Calling before Boot loads required sources can return missing or different values than after startup.
3. **Beans:** Objects returned by Binder are not automatically registered, injected, or given `@PostConstruct`, AOP, or shutdown callbacks.
4. **Validation:** `@Validated`/custom handlers are not present by default in every direct bind; configure explicitly when needed.
5. **Conversion/placeholders:** A standalone Binder does not automatically inherit all container conversion/placeholder infrastructure.
6. **Configuration changes:** Binding creates/updates data at call time, not an automatic hot-reload/thread-safe snapshot service.

When configuration is foundational to a Spring Boot application, prefer **bean-managed `@ConfigurationProperties`**. When you need a local snapshot, isolated test, or CLI tool, use **direct Binder**, proactively supplying sources, converters, validators, fallbacks, and object management.

## 25. References

- Spring Boot **3.3 API — Binder**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/Binder.html
- Spring Boot **3.3 API — Bindable**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/Bindable.html
- Spring Boot **3.3 API — BindResult**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/BindResult.html
- Spring Boot **3.3 API — ConfigurationPropertySources**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/source/ConfigurationPropertySources.html
- Spring Boot **3.3 API — ValidationBindHandler**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/validation/ValidationBindHandler.html
- Spring Boot **3.3 Reference — Externalized Configuration / Type-safe Configuration Properties**: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot **3.3 API — @ConfigurationProperties**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html
- Spring Framework — **Container Extension Points / BeanPostProcessor / Bean Lifecycle**: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html

**Final message:** Treat `Binder.bind` as **a function turning configuration data into an object**, and `ApplicationContext` as **the bean and lifecycle management system**. Only by maintaining clear boundaries between the two can applications avoid subtle bugs involving early-loaded sources, missing validation, differing converters, uninjected objects, and non-refreshing configuration.
