# Extending Config Data via ConfigDataLocationResolver and ConfigDataLoader

Spring Boot lets you declare configuration via files, environment variables, system properties, command-line arguments, and external sources. The **Config Data** system is used when Spring Boot loads `application.yml`, `application.properties`, and resources imported via `spring.config.import`. If an application needs to understand a new location scheme such as `demo:orders` or `acme-config:team/orders`, you can extend this mechanism through two SPIs:

- `ConfigDataLocationResolver<R>`: recognizes a location and resolves it into one or more `ConfigDataResource` instances.
- `ConfigDataLoader<R>`: loads those resources and returns `ConfigData` containing Spring `PropertySource` instances.

Both interfaces belong to `org.springframework.boot.context.config`. They run during the **Environment bootstrap phase**, before most regular Spring beans are created. This lesson uses **Spring Boot 3.3.x and Java 21**, demonstrating a complete extension that supports `demo:orders`, profile-specific resources, `optional:`, priority ordering, registration via `spring.factories`, and testing.

## 1. The problem: importing data from a new scheme

We want to write in `application.yml`:

~~~yaml
spring:
  config:
    import: "demo:orders"
~~~

Suppose the configuration source `demo:orders` provides:

~~~properties
demo.feature.origin=orders
demo.feature.limit=25
~~~

After Spring Boot starts up, the application can read:

~~~java
environment.getProperty("demo.feature.origin");
environment.getProperty("demo.feature.limit", Integer.class);
~~~

Or bind into a record:

~~~java
@ConfigurationProperties(prefix = "demo.feature")
public record DemoFeatureProperties(String origin, int limit) {
}
~~~

Spring Boot does not recognize the `demo:` scheme until we register a resolver and a loader. The SPI pair forms this flow:

~~~text
spring.config.import = demo:orders
            |
            v
   DemoConfigDataLocationResolver
            |
            v
    DemoConfigDataResource
            |
            v
       DemoConfigDataLoader
            |
            v
 ConfigData(MapPropertySource)
            |
            v
       Spring Environment
            |
            v
      @ConfigurationProperties
            |
            v
        Service / Component
~~~

In this example, the loader fetches data from an in-memory Map to keep the focus on the API. When connecting to a remote store, simply replace the data-fetching part in the loader with an actual adapter, while adding timeouts, credentials, and error handling.

## 2. When should you use these two SPIs?

Suitable use cases:

- Importing configuration stored in a remote configuration store.
- Supporting a custom prefix such as `myconfig:namespace/key`.
- Reading multiple configuration layers by tenant, application group, or profile.
- Turning responses from an API into properties for the Environment.
- Packaging a shared import mechanism inside a library/starter.

You do not need a custom resolver if you only want to:

- Import existing YAML via `spring.config.import=optional:file:./extra.yml`.
- Read files in a Kubernetes volume via `configtree:`.
- Convert String values into enums or domain types using a Converter.
- Bind groups of properties with `@ConfigurationProperties`.
- Validate that worker count is greater than 0 with Bean Validation.
- Observe Binder callbacks with `BindHandler`.

Responsibility table:

| Component | Purpose |
| --- | --- |
| `ConfigDataLocation` | The location declared by the user, e.g., `demo:orders` |
| `ConfigDataLocationResolver` | Checks the scheme and creates resources |
| `ConfigDataResource` | Represents the specific source to load |
| `ConfigDataLoader` | Reads the resource and builds ConfigData |
| `ConfigData` | Holds the loaded PropertySources |
| `@ConfigurationProperties` | Consumes properties already present in the Environment |
| `PropertySourceLoader` | Supports reading standard file formats via the corresponding mechanism |

Key point: **a resolver does not necessarily load data**. Its main job is converting a location into resources. The loader is what actually fetches data and builds the PropertySource.

## 3. ConfigDataLocation: location and optional

`ConfigDataLocation` is an object wrapping an import location:

~~~text
demo:orders
optional:demo:orders
file:./extra.yml
classpath:/default.properties
configtree:/etc/secrets/
~~~

Useful methods:

~~~java
location.hasPrefix("demo:");
location.getNonPrefixedValue("demo:");
location.getValue();
location.isOptional();
~~~

`hasPrefix` identifies the scheme, `getNonPrefixedValue` retrieves the remainder after the prefix, and `isOptional` indicates whether the user declared the location as allowed not to exist.

Example:

~~~text
Location: optional:demo:orders
Prefix:   demo:
Name:     orders
Optional: true
~~~

Spring Boot strips the `optional:` prefix before evaluating `getValue()`. However, **optional does not mean ignoring all exceptions**; it is a policy specifically for Config Data not-found errors.

## 4. ConfigDataResource: stable identity

A resource serves as intermediate data between the resolver and the loader. It can hold a document ID, namespace, profile, or normalized location.

Subclasses of `ConfigDataResource` should implement proper `equals`, `hashCode`, and `toString`. This helps detect when two resources represent the same source, avoids duplicate processing, and produces clear diagnostic information.

You should not store secrets in `toString()` because exceptions or bootstrap logs may print that string.

In this example, the resource only needs a name and an optional flag.

## 5. Project structure

~~~text
config-data-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/configdemo/
    │   ├── ConfigDataDemoApplication.java
    │   ├── config/DemoFeatureProperties.java
    │   └── configdata/
    │       ├── DemoConfigDataResource.java
    │       ├── DemoConfigDataLocationResolver.java
    │       └── DemoConfigDataLoader.java
    └── resources/
        ├── application.yml
        └── META-INF/spring.factories
~~~

For a standard Spring Boot application, the SPIs are already included in the core Spring Boot dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter</artifactId>
</dependency>
~~~

Assume the project uses a Maven parent/BOM managing Spring Boot 3.3.x, Java 21, and the appropriate build plugins.

## 6. Step 1: create DemoConfigDataResource

Create `DemoConfigDataResource.java`:

~~~java
package com.example.configdemo.configdata;

import java.util.Objects;

import org.springframework.boot.context.config.ConfigDataResource;

public final class DemoConfigDataResource extends ConfigDataResource {

    private final String name;
    private final boolean optional;

    public DemoConfigDataResource(String name, boolean optional) {
        super(optional);
        this.name = Objects.requireNonNull(name, "name");
        this.optional = optional;
    }

    public String name() {
        return name;
    }

    public boolean optional() {
        return optional;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof DemoConfigDataResource that)) {
            return false;
        }
        return optional == that.optional
                && name.equals(that.name);
    }

    @Override
    public int hashCode() {
        return Objects.hash(name, optional);
    }

    @Override
    public String toString() {
        return (optional ? "optional:" : "") + "demo:" + name;
    }
}
~~~

`super(optional)` passes the optional state to the Spring Boot base class. The `name` property can be `orders` or `orders@dev`, while `optional` handles missing-source processing.

`optional()` in this example is a getter on the demo class, not an assumption that the base class requires such a public getter. In a real system, you should use a resource ID that does not contain passwords or tokens.

## 7. Step 2: write ConfigDataLocationResolver

Create `DemoConfigDataLocationResolver.java`:

~~~java
package com.example.configdemo.configdata;

import java.util.List;

import org.springframework.boot.context.config.ConfigDataLocation;
import org.springframework.boot.context.config.ConfigDataLocationResolver;
import org.springframework.boot.context.config.ConfigDataLocationResolverContext;
import org.springframework.boot.context.config.Profiles;

public final class DemoConfigDataLocationResolver
        implements ConfigDataLocationResolver<DemoConfigDataResource> {

    private static final String PREFIX = "demo:";

    @Override
    public boolean isResolvable(
            ConfigDataLocationResolverContext context,
            ConfigDataLocation location) {

        return location.hasPrefix(PREFIX);
    }

    @Override
    public List<DemoConfigDataResource> resolve(
            ConfigDataLocationResolverContext context,
            ConfigDataLocation location) {

        String name = readName(location);
        return List.of(
                new DemoConfigDataResource(name, location.isOptional()));
    }

    @Override
    public List<DemoConfigDataResource> resolveProfileSpecific(
            ConfigDataLocationResolverContext context,
            ConfigDataLocation location,
            Profiles profiles) {

        String name = readName(location);

        // Profile variants are optional in this demo.
        return profiles.getAccepted().stream()
                .map(profile -> new DemoConfigDataResource(
                        name + "@" + profile, true))
                .toList();
    }

    private static String readName(ConfigDataLocation location) {
        String name = location.getNonPrefixedValue(PREFIX);

        if (!name.matches("[a-z][a-z0-9-]*")) {
            throw new IllegalArgumentException(
                    "Invalid demo config name: " + name);
        }
        return name;
    }
}
~~~

### isResolvable recognizes the scheme

For `demo:orders`, the method returns true. For `optional:demo:orders`, `ConfigDataLocation` has already recognized optionality, so `hasPrefix("demo:")` also matches the scheme properly.

For `file:./extra.yml` or `classpath:/default.properties`, the resolver returns false. A resolver should not claim all locations and attempt to resolve everything itself; when multiple resolvers exist, Spring Boot selects the first implementation supporting the location according to resolver order.

### resolve creates a basic resource

`resolve(...)` turns `demo:orders` into `DemoConfigDataResource("orders", false)`.

It **does not create a PropertySource yet**. The data is loaded later. If a location resolves to multiple resources, the list order must be in **ascending priority** so higher-precedence configuration layers can override lower ones.

### resolveProfileSpecific creates variants

In this example, `orders@dev` and `orders@prod` are two names defined by the application's own convention. Spring Boot does not invent that convention for every custom scheme.

`Profiles.getAccepted()` provides the list of accepted profiles during Config Data processing, including the appropriate active/default profile information. You should not read `System.getenv("SPRING_PROFILES_ACTIVE")` and assume it represents the complete profile information.

If you do not override `resolveProfileSpecific`, the interface's default implementation returns an empty list: the extension will not automatically generate profile-specific resources.

### Why are profile resources optional?

The example treats `orders` as the mandatory base data, while `orders@dev` and `orders@prod` may be absent. Therefore, the resolver sets the optional=true flag on the variants.

In a real system, if every environment must have its own data, you need a different policy design. Do not blindly make every profile-specific resource optional without a business requirement.

## 8. Step 3: write ConfigDataLoader

Create `DemoConfigDataLoader.java`:

~~~java
package com.example.configdemo.configdata;

import java.io.IOException;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.config.ConfigData;
import org.springframework.boot.context.config.ConfigDataLoader;
import org.springframework.boot.context.config.ConfigDataLoaderContext;
import org.springframework.boot.context.config.ConfigDataResourceNotFoundException;
import org.springframework.core.env.MapPropertySource;

public final class DemoConfigDataLoader
        implements ConfigDataLoader<DemoConfigDataResource> {

    @Override
    public ConfigData load(
            ConfigDataLoaderContext context,
            DemoConfigDataResource resource) throws IOException {

        Map<String, Object> values = switch (resource.name()) {
            case "orders" -> Map.of(
                    "demo.feature.origin", "orders",
                    "demo.feature.limit", "25");
            case "orders@dev" -> Map.of(
                    "demo.feature.limit", "5");
            case "orders@prod" -> Map.of(
                    "demo.feature.limit", "100");
            case "billing" -> Map.of(
                    "demo.feature.origin", "billing",
                    "demo.feature.limit", "40");
            default -> null;
        };

        if (values == null) {
            throw new ConfigDataResourceNotFoundException(resource);
        }

        MapPropertySource source = new MapPropertySource(
                "demoConfigData[" + resource.name() + "]",
                values);

        return new ConfigData(List.of(source));
    }
}
~~~

For `orders`, the loader returns these properties:

~~~text
demo.feature.origin = orders
demo.feature.limit  = 25
~~~

For `orders@dev`, it only returns:

~~~text
demo.feature.limit  = 5
~~~

When the dev variant is processed as profile-specific Config Data, it can override `limit` from the base version, while `origin` still comes from `orders`.

### isLoadable

`ConfigDataLoader` has a default `isLoadable(ConfigDataLoaderContext, R)` method. With a dedicated `DemoConfigDataResource` and a single loader, there is no need to override it. If multiple loaders claim the same resource, a conflict occurs; the Javadoc requires that multiple loaders must not accept the same resource simultaneously.

### MapPropertySource and ConfigData

`MapPropertySource` is a `PropertySource` implementation for representing key-value pairs. A loader can return one or more PropertySources through `ConfigData`.

The list of property sources inside a `ConfigData` is required by the documentation to be in **ascending order of priority**: a source appearing later can win when a key collides with an earlier source.

### When a resource does not exist

The loader throws:

~~~java
throw new ConfigDataResourceNotFoundException(resource);
~~~

This is how you indicate that a resource was resolved but not found. `optional:` only has clear meaning when the error is classified under the Config Data not-found category.

Do not turn every exception from HTTP, databases, or JSON parsing into not-found: if the backend returns 401/403 or malformed syntax, the application needs to report the appropriate error.

## 9. Step 4: register the SPI via spring.factories

Create the file:

~~~text
src/main/resources/META-INF/spring.factories
~~~

Contents:

~~~properties
org.springframework.boot.context.config.ConfigDataLocationResolver=com.example.configdemo.configdata.DemoConfigDataLocationResolver
org.springframework.boot.context.config.ConfigDataLoader=com.example.configdemo.configdata.DemoConfigDataLoader
~~~

The implementations in this example have a no-arg constructor so Spring Boot can instantiate them through the factory mechanism.

**Spring Boot 3.x note:** auto-configuration classes are typically declared in `AutoConfiguration.imports`, but these two Config Data SPIs are still registered via **`META-INF/spring.factories`**. Do not move these two entries to `AutoConfiguration.imports`.

Simply annotating them with `@Component` is not a sufficient way to register a resolver/loader: they must run before the normal application context completes component scanning and bean creation.

## 10. Step 5: use import and bind data

The `application.yml` file:

~~~yaml
spring:
  config:
    import: "demo:orders"

demo:
  feature:
    limit: 10
~~~

Spring Boot reads the location, invokes the resolver, invokes the loader, and contributes the PropertySource. According to Config Data rules, **the imported document can override the document declaring the import**, so `limit=25` from `demo:orders` will take precedence over `limit=10` in the document above, assuming no higher-priority source exists.

Create `DemoFeatureProperties.java`:

~~~java
package com.example.configdemo.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.feature")
public record DemoFeatureProperties(String origin, int limit) {
}
~~~

Create the application class:

~~~java
package com.example.configdemo;

import com.example.configdemo.config.DemoFeatureProperties;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDataDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigDataDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showConfig(DemoFeatureProperties properties) {
        return args -> System.out.println(
                "origin=" + properties.origin()
                        + ", limit=" + properties.limit());
    }
}
~~~

Run:

~~~bash
./mvnw spring-boot:run
~~~

Expected output:

~~~text
origin=orders, limit=25
~~~

`@ConfigurationProperties` binds values after Config Data has already contributed properties to the Environment; it is not the mechanism that discovers resolvers.

## 11. Results when using profiles

Try:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.arguments="--spring.profiles.active=dev"
~~~

The resolver can additionally produce the `orders@dev` resource, and the loader returns `limit=5`:

~~~text
origin=orders, limit=5
~~~

Similarly:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.arguments="--spring.profiles.active=prod"
~~~

The `orders@prod` resource returns `limit=100`:

~~~text
origin=orders, limit=100
~~~

Expected results assume these resources are loaded under Config Data priority rules, with no CLI argument, environment variable, or higher-priority source changing `demo.feature.limit`.

With the `staging` profile where the demo store has no `orders@staging`, the profile-specific resource is marked optional, so its missing-resource error can be ignored, leaving the base value `limit=25`.

### Multiple active profiles

When profiles like `prod,live` are active, the order and list of profile-specific resources can affect the final value. If the extension resolves multiple resources, follow the API's **ascending priority** rule and test the ordering with the supported profiles.

Do not rely on arbitrary Map iteration order or mutate active profiles yourself while the loader is loading profile-specific data.

## 12. Optional and missing resources

Compare:

~~~properties
spring.config.import=demo:missing
~~~

with:

~~~properties
spring.config.import=optional:demo:missing
~~~

In this example, `missing` does not exist:

- A mandatory import typically causes the application to stop with a Config Data resource not-found error.
- An optional import can ignore the missing resource and continue startup if all remaining conditions are satisfied.

Distinction table:

| Error | Should it be treated as a missing resource? |
| --- | --- |
| Document/configuration set does not exist | Yes |
| HTTP 404 meaning the namespace does not exist | Yes, per the API contract |
| HTTP 401/403 | No, this is an authentication/authorization error |
| HTTP 500/503 | No, this is an infrastructure error |
| Timeout | Do not silently convert into not-found |
| Malformed JSON/YAML syntax | No, this is a data error |
| Invalid location format | Should not be ignored as a valid missing resource |

`optional:` does not guarantee that the properties required by a bean will exist. If a bean is annotated with `@NotNull` or `@NotBlank`, a missing optional import can still cause validation to fail.

## 13. Priority order across multiple imports

Example:

~~~yaml
spring:
  config:
    import:
      - "demo:orders"
      - "demo:billing"
~~~

In the loader:

~~~text
orders  → origin=orders,  limit=25
billing → origin=billing, limit=40
~~~

Depending on how imports are processed, a later location can have higher priority for colliding keys. The result can be `origin=billing, limit=40` if no higher-priority source overrides it.

With multiple PropertySources in a single `ConfigData`:

~~~java
new ConfigData(List.of(
        new MapPropertySource("defaults", defaults),
        new MapPropertySource("overrides", overrides)));
~~~

Place lower-precedence sources first and higher-precedence sources later; this is the rule stated in the `ConfigData` API.

### Interaction with environment and CLI

Config Data is one layer in Spring Boot's `PropertySource` precedence. Sources such as environment variables, system properties, and command-line arguments can normally override Config Data values.

Example:

~~~bash
java -jar app.jar --demo.feature.limit=200
~~~

With the CLI override, the final value can be 200 even though the loader supplied 25.

## 14. ResolverContext during bootstrap

`ConfigDataLocationResolverContext` provides these methods:

~~~java
context.getBinder();
context.getBootstrapContext();
context.getParent();
~~~

- `getBinder()` provides a Binder for reading values **already contributed earlier** during Config Data loading. You must not assume all application properties are ready yet.
- `getBootstrapContext()` provides the shared bootstrap context, which is useful when clients connecting to external sources are expensive to instantiate.
- `getParent()` provides the parent resource that triggered a resolve, or null if none. It can help resolve imports relative to the parent resource.

Avoid circular dependencies:

~~~text
Loading remote:orders requires app.remote.token
But app.remote.token is only inside remote:orders
=> bootstrap does not yet have the token to read the resource
~~~

Credentials should be supplied from a source available earlier, such as environment variables or an appropriate bootstrap secret source.

## 15. LoaderContext and startup objects

`ConfigDataLoader.load(...)` receives `ConfigDataLoaderContext`. The in-memory example does not use the context because there are no shared resources.

The Javadoc allows certain supported constructor parameters in a resolver/loader such as `DeferredLogFactory` and `ConfigurableBootstrapContext`; a resolver can also use `Binder` or `ResourceLoader` within the scope supported by the API.

Do not inject a regular `@Service` or JPA repository into a loader and expect it to exist already. The Config Data phase runs before most runtime beans are created, whereas that datasource or service might itself depend on the very properties supplied by the loader.

A remote client at bootstrap should be lightweight, with bounded timeouts and a controlled lifecycle.

## 16. Building a real loader for remote configuration

When using HTTP/API, recommended workflow:

~~~text
1. Receive the resource with its namespace and profile.
2. Read the endpoint/credentials from available bootstrap configuration.
3. Send the request with a finite timeout.
4. Classify 404, 401, 403, 429, and 5xx responses.
5. Perform bounded retries for appropriate errors.
6. Parse the payload and validate its schema.
7. Convert the payload into Map<String, Object>.
8. Create a MapPropertySource with a clear source name.
9. Return ConfigData for Spring Boot to add to the Environment.
~~~

Illustrative pseudo-code (`RemoteDocument`, `remoteClient`, and `validateAndFlatten` are custom-designed classes/methods, **not built-in Spring Boot APIs**):

~~~java
public ConfigData load(
        ConfigDataLoaderContext context,
        RemoteConfigDataResource resource) throws IOException {

    RemoteDocument doc =
            remoteClient.fetch(resource.identifier());

    if (doc == null) {
        throw new ConfigDataResourceNotFoundException(resource);
    }

    Map<String, Object> values =
            validateAndFlatten(doc);

    return new ConfigData(List.of(
            new MapPropertySource(
                    "remote[" + resource.identifier() + "]",
                    values)));
}
~~~

Required design criteria:

- Do not log tokens, passwords, or full sensitive payloads.
- Set finite timeouts and retries so startup never hangs indefinitely.
- Do not turn every remote error into not-found.
- Enforce limits on payload size and number of keys.
- Validate the schema before exposing properties.
- Record a non-sensitive origin or version for traceability.
- Define priority ordering when multiple remote config layers contain the same key.
- Ensure keys do not collide or get flattened incorrectly.
- Consider caching/bootstrap sharing with `ConfigurableBootstrapContext`.
- Do not automatically reload beans simply because the remote store changes.

### Secret sources

If the backend supplies secrets, you should not print the entire PropertySource when debugging. Resource `toString` must also contain only non-sensitive IDs. Observability endpoints such as Actuator must have proper access control enabled.

## 17. Config Data is not hot reload

A typical application:

~~~text
Startup
  → prepare Environment
  → process Config Data imports
  → create ApplicationContext
  → bind @ConfigurationProperties
  → create beans and run business logic
~~~

Resolvers/loaders run during the data-loading phase. When remote data changes after startup, Spring Boot does not by default reload every Config Data resource and rebuild `@ConfigurationProperties` beans.

If runtime refresh is needed, you must design a separate mechanism with consistency, synchronization, error handling, and appropriate access control. Do not use a loader as a background polling loop.

## 18. Common mistakes

### Wrong spring.factories

A misspelled filename, wrong directory, or wrong class name prevents Spring Boot from discovering the implementations. You need the exact `META-INF/spring.factories` file and both fully qualified interface keys.

### Overly broad isResolvable

If a resolver accepts every location, it can conflict with `file:`, `classpath:`, or `configtree:`. Only accept the dedicated prefix that your extension actually supports.

### Resource missing equals/hashCode

A resource without stable equality can cause unwanted duplicate processing when the same import appears multiple times.

### Not preserving the optional flag

If `location.isOptional()` is not passed to the base resource, a missing location may not be handled as expected.

### Not implementing resolveProfileSpecific

The default method returns an empty list; Spring Boot does not automatically generate profile variants for new schemes.

### Using the wrong exception

Non-existent resources use the appropriate not-found exception; HTTP 403 errors or malformed data must carry different semantics. Do not swallow errors just to let the app start.

### Wrong source ordering

Multiple resources or property sources must be ordered in ascending priority. Reversing the order can produce final values that violate the contract.

### Reading runtime beans at bootstrap

Do not depend on JPA repositories or services that have not yet been created in a loader constructor.

### Leaking secrets via logs

Do not print result maps or resources containing credentials. Only log the source name and appropriate error category.

### Confusing import output with final value

CLI arguments or the environment can take higher precedence than Config Data. Inspect the effective property value rather than checking only what the loader returned.

## 19. Runtime verification

After creating the classes and `spring.factories`:

~~~bash
./mvnw clean package
java -jar target/config-data-demo.jar
~~~

The JAR name is only an example. Use the actual artifact produced by the build.

Try profiles:

~~~bash
java -jar target/config-data-demo.jar --spring.profiles.active=dev
java -jar target/config-data-demo.jar --spring.profiles.active=prod
~~~

Test importing `demo:missing` and `optional:demo:missing` by editing the config file or passing appropriate arguments. Compare the startup error and the values of `DemoFeatureProperties`.

To observe details in a development environment:

~~~bash
java -jar target/config-data-demo.jar --logging.level.org.springframework.boot.context.config=TRACE
~~~

Do not enable widespread TRACE logging in production where logs can overload the system or expose configuration details.

Verify the registration file is inside the JAR:

~~~bash
jar tf target/config-data-demo.jar
~~~

In a Spring Boot executable JAR, the application's `spring.factories` typically resides at `BOOT-INF/classes/META-INF/spring.factories`; in a library JAR it typically resides at `META-INF/spring.factories`.

## 20. Unit testing the resolver/loader

Use JUnit, AssertJ, and Mockito via `spring-boot-starter-test`:

~~~java
package com.example.configdemo.configdata;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

import java.util.List;
import org.junit.jupiter.api.Test;

import org.springframework.boot.context.config.ConfigData;
import org.springframework.boot.context.config.ConfigDataLoaderContext;
import org.springframework.boot.context.config.ConfigDataLocation;
import org.springframework.boot.context.config.ConfigDataLocationResolverContext;

class DemoConfigDataSpiTest {

    @Test
    void recognizesDemoPrefix() {
        var resolver = new DemoConfigDataLocationResolver();
        var context = mock(ConfigDataLocationResolverContext.class);

        assertThat(resolver.isResolvable(
                context,
                ConfigDataLocation.of("demo:orders"))).isTrue();

        assertThat(resolver.isResolvable(
                context,
                ConfigDataLocation.of("file:./extra.yml"))).isFalse();
    }

    @Test
    void resolvesResource() {
        var resolver = new DemoConfigDataLocationResolver();
        var context = mock(ConfigDataLocationResolverContext.class);

        List<DemoConfigDataResource> resources =
                resolver.resolve(
                        context, ConfigDataLocation.of("demo:orders"));

        assertThat(resources).hasSize(1);
        assertThat(resources.get(0).name()).isEqualTo("orders");
        assertThat(resources.get(0).optional()).isFalse();
    }

    @Test
    void loadsProperties() throws Exception {
        var loader = new DemoConfigDataLoader();
        var context = mock(ConfigDataLoaderContext.class);

        ConfigData data = loader.load(
                context,
                new DemoConfigDataResource("orders", false));

        assertThat(data.getPropertySources()).hasSize(1);
        assertThat(data.getPropertySources().get(0)
                .getProperty("demo.feature.limit"))
                .isEqualTo("25");
    }
}
~~~

Unit tests verify the exact methods provided by the implementation, but do not on their own prove that Spring Boot discovered `spring.factories`.

You should also add integration tests that boot the real application with `spring.config.import=demo:orders`, verifying profiles, optionality, priority, and startup error handling at the actual Config Data phase.

## 21. Integration test scenarios to include

| Scenario | Expected outcome |
| --- | --- |
| `spring.config.import=demo:orders` | `origin=orders`, `limit=25` |
| YAML in the same document sets `limit=10` | Import can override it to 25 |
| Active profile dev | `limit=5` from `orders@dev` |
| Active profile prod | `limit=100` from `orders@prod` |
| Mandatory import is missing | Startup fails with not-found |
| Optional import is missing | Missing resource can be ignored |
| CLI `--demo.feature.limit=200` | CLI can override import |
| Resolver missing from `spring.factories` | Scheme is not recognized |
| Wrong property type from source | Error when Binder consumes property |
| 403 from remote API | Must not be treated as not-found |
| Two imports share the same key | Last value wins by priority order |

Do not check only the Map object returned by the loader. Also verify the **effective value in the Environment** and the bound bean.

## 22. Practice questions

### Exercise 1 — Separation of responsibilities

A team wants to support `vaultlike:team-a/orders`. Which component recognizes the scheme, which performs the HTTP request, and which holds the resource ID?

**Answer:** resolver, loader, and resource, respectively.

### Exercise 2 — Optional

Why can `optional:demo:missing` be ignored while `demo:missing` causes an error?

**Answer:** the optional flag is passed to the resource, and Spring Boot handles the not-found exception according to the corresponding policy.

### Exercise 3 — Profiles

Add an `orders@staging` case returning `limit=50` to the loader and run with `staging`; explain the priority result relative to the base resource.

### Exercise 4 — Source ordering

Import `demo:orders` then `demo:billing`, both providing `demo.feature.limit`. Predict the value when no other source overrides it.

### Exercise 5 — Wrong error type

The remote API returns 403. Should you convert it to `ConfigDataResourceNotFoundException` just so `optional:` lets startup proceed?

**Answer:** no; an access-permission error does not mean the resource does not exist.

### Exercise 6 — Bootstrap

The resolver needs a token that is only provided by the unloaded resource itself. Explain the circular dependency and find a credential source bootstrapped earlier.

### Exercise 7 — Resource equality

Why should two `DemoConfigDataResource("orders", false)` instances compare equal? Answer based on resource identification and deduplication.

### Exercise 8 — Choosing the right mechanism

You only need to convert the String `"apac"` into `RegionCode("APAC")`. Do you need the Config Data SPI?

**Answer:** no; you only need an appropriate converter for configuration binding.

## 23. Summary

`ConfigDataLocationResolver` and `ConfigDataLoader` are the two extension points for **new Config Data sources** in Spring Boot. The resolver turns a location into resources; the loader loads resources and returns ConfigData with PropertySources. Spring Boot processes those properties in the Environment, while application beans read them via `@Value` or `@ConfigurationProperties`.

Core principles:

- Register both implementations via `META-INF/spring.factories` in Spring Boot 3.3.
- Keep resource identity stable and never expose secrets.
- Maintain clear priority ordering when there are multiple resources or PropertySources.
- Define a profile-specific mechanism yourself if your custom scheme requires it.
- Use `optional:` properly for missing resources, without masking security or parsing errors.
- Minimize dependencies during bootstrap, configure timeouts, and handle errors for remote config.
- Write unit tests specifically for resolver/loader logic and integration tests for discovery, import, profiles, and priority.

## References

- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [ConfigDataLocationResolver API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/ConfigDataLocationResolver.html)
- [ConfigDataLoader API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/ConfigDataLoader.html)
- [ConfigDataResource API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/ConfigDataResource.html)
- [ConfigData API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/ConfigData.html)
- [ConfigDataLocation API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/ConfigDataLocation.html)
- [Profiles API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/Profiles.html)
