# Spring Boot Testing: Configuration Precedence and How to Verify the Value Actually Used

## 1. Why can the same key have multiple values?

In a Spring Boot project, the same property can be declared in many places: `application.properties`, `application-test.yml`, environment variables, JVM `-D...`, command-line arguments, `@SpringBootTest(properties = ...)`, `@TestPropertySource`, or a `@DynamicPropertySource` supplying values when Testcontainers runs.

For example, `demo.checkout.retries` might be `2` in the common file, `7` in the `test` profile file, and `12` in a CI environment variable. So **which value does the service actually receive**?

Separate three questions that often get lumped together:

1. **Which values were declared?** Each file or source only shows one *candidate*.
2. **Which value wins in `Environment`?** Spring iterates over `PropertySource`s in priority order; the first source returning a matching value usually wins.
3. **Which value did the bean actually use?** A bean may receive values via `@Value`, `@ConfigurationProperties`, constructors, connection-details, precomputed fields, or caching. What is in `Environment` does not always prove a client is using that exact setting.

This lesson focuses on **test environment configuration**, not just memorizing a precedence table. The goal is to predict common outcomes, verify actual values in a test, trace the winning source, and recognize when checking `Environment` is not enough.

### Learning outcomes

- Understand `PropertySource`, override order, how config data works, and active profiles.
- Distinguish common value sources from test-specific overrides: `@SpringBootTest(properties)`, `@TestPropertySource`, and `@DynamicPropertySource`.
- Write a Java 17+ integration test verifying `Environment`, `@Value`, `@ConfigurationProperties`, and active profiles together.
- Trace the winning source using `ConfigurableEnvironment.getPropertySources()`, origin information, and Actuator `env`/`configprops`.
- Troubleshoot bugs caused by CI config, profiles, test context caching, environment variables, YAML/properties ordering, and Testcontainers.
- Never expose secrets during diagnosis; never mutate global system properties carelessly in parallel tests.

## 2. The right mental model: PropertySource and value selection

Spring exposes an `Environment` containing multiple `PropertySource`s. Each `PropertySource` has a name and can return a value for a key. With `ConfigurableEnvironment`, we can inspect them via `getPropertySources()` **in priority order from highest to lowest**.

Visualize it like this:

~~~text
ConfigurableEnvironment
  |
  +-- Higher-priority source: demo.checkout.mode = "test-inline"
  |
  +-- Next source:            demo.checkout.mode = "boot-inline"
  |
  +-- Another source:         does not contain demo.checkout.mode
  |
  +-- Config data:            demo.checkout.mode = "profile"
  |
  +-- Config data:            demo.checkout.mode = "default"
  |
  +-- Lower-priority sources
             |
             v
   getProperty("demo.checkout.mode")
   -> "test-inline"  (first matching source)
~~~

In a simple case, **a key is not concatenated across sources**; a higher-precedence source with a valid value shadows the same key in lower sources. However, **binding a complex object** does not always equate to individual `getProperty(key)` calls:

- For **scalar properties** like `demo.checkout.retries`, overriding is straightforward.
- For `@ConfigurationProperties`, *relaxed binding*, type conversion, and collection merge/replace have specific rules. In Spring Boot, **a list from a higher-priority source normally replaces the list**, rather than appending elements across files; maps may merge values per key.
- For `${...}` placeholders, referenced values are resolved from `Environment`; nested references can make the final source non-obvious.
- For already-initialized beans, calling `System.setProperty` or changing environment variables afterward does not automatically rebind all beans.

Therefore, verify **the same key, same profile, same application lifecycle phase, and same Spring Boot version**, and ultimately verify the value on the consuming bean/client if that is what business code uses.

## 3. Common precedence order in Spring Boot

Spring Boot 3.5 and 4.x document configuration sources in a defined order; **sources listed later can override earlier sources**. For typical test projects, the overall picture from lowest to highest priority is:

| Tier | Source | Example | Meaning |
| --- | --- | --- | --- |
| 1 | Application default properties | `SpringApplication.setDefaultProperties(...)` | Fallback values |
| 2 | `@PropertySource` on `@Configuration` | Custom properties file | May load late; unsuitable for certain bootstrap settings |
| 3 | Config data | `application.properties`, `application-test.yml`, files outside jar | Common defaults for application and profiles |
| 4 | `RandomValuePropertySource` | `random.uuid`, `random.int` | Supplies only `random.*` keys |
| 5 | OS environment variables | `DEMO_CHECKOUT_RETRIES` | Overrides regular files |
| 6 | JVM system properties | `-Ddemo.checkout.retries=12` | Usually beats OS environment on the same key |
| 7 | JNDI / ServletContext / ServletConfig | Certain servlet or application server environments | Present only when provided by that infrastructure |
| 8 | `SPRING_APPLICATION_JSON` | JSON supplied via env or system property | Overrides many traditional sources |
| 9 | Command-line args | `--demo.checkout.retries=15` | Beats files, env, and JVM properties normally |
| 10 | Boot test properties | `@SpringBootTest(properties = "...")` | Dedicated override in the test context |
| 11 | Test property sources / dynamic properties | `@TestPropertySource`, `@DynamicPropertySource` | High-precedence test mechanisms; see note below |
| 12 | Devtools global settings when active | Developer's devtools config | Can rank very high; normally not relied on in CI |

**Important note on Tier 11:** Spring Framework TestContext documentation explicitly states that `@DynamicPropertySource` takes higher precedence than values from `@TestPropertySource`, whereas summary tables in some Spring Boot docs list the two entries in an order that can be read the opposite way. Never write a test depending on a collision where **the exact same key** is declared by both mechanisms without verifying on your project's exact version and test setup. Choose one intentional override location and use the winning-source inspection technique in Section 7 to prove it in practice.

Tiers 1–9 represent a **general schema**, not a guarantee that every `ApplicationContext` includes every tier. Tests without a servlet container have no servlet config; tests run directly from an IDE may lack `java -jar` command-line properties; devtools is usually absent from test runners.

**Practical invariants worth remembering:**

- A value in `application-test.properties` **does not automatically** beat `-Ddemo.checkout.retries=12`; JVM system properties have higher priority than config data.
- `@ActiveProfiles("test")` selects the `test` profile, yet **does not turn** every value in `application-test.properties` into the highest-priority source.
- Inline test overrides can beat machine/CI configuration; use them intentionally to isolate tests.
- A `null` value in `SPRING_APPLICATION_JSON` is treated as a missing property on lookup; do not use it to erase values from lower sources.
- `@PropertySource` is added during context refresh; it can be **too late** to change properties Spring Boot reads early, such as `logging.*` or `spring.main.*`.

## 4. Ordering inside the Config Data tier

A common misconception: **"Any file named `application-test` always beats any `application` file."** In reality it depends on **file location, active profiles, document type, and imports**.

With default configuration, key config data groups go from lowest to highest priority:

1. `application.properties` / YAML **inside the classpath/jar**.
2. `application-{profile}.properties` / YAML **inside the classpath/jar** for active profiles.
3. `application.properties` / YAML **outside the jar** at loaded config locations.
4. `application-{profile}.properties` / YAML **outside the jar** at loaded config locations.

This views ordering by **file groups**, not an exhaustive list of every location/import rule. Within each group, specific locations, documents inside a single file, `spring.config.import`, and active profiles further affect the final value.

### 4.1 Common vs. profile-specific configuration

Example:

File `src/test/resources/application.properties`:

~~~properties
demo.checkout.mode=base
demo.checkout.retries=2
~~~

File `src/test/resources/application-test.properties`:

~~~properties
demo.checkout.mode=profile-test
~~~

When the test context starts with `@ActiveProfiles("test")`, the typical result is:

~~~text
demo.checkout.mode    = profile-test
demo.checkout.retries = 2
~~~

`mode` is overridden in the profile file, whereas `retries` is omitted from the profile and inherited from common config data. **The profile does not erase every key from the base file.**

If the same key appears in multiple profile-specific files with multiple active profiles, **the last profile in order can win** per Spring Boot rules; avoid relying on colliding keys across too many profiles. With `spring.profiles.include` and profile groups, additional profiles also participate; confirm the actual active list via `Environment.getActiveProfiles()`.

### 4.2 `.properties` vs. YAML

When `application.properties` and `application.yml` sit in the same location, Spring Boot prefers `.properties`. Use **one consistent primary format** per configuration group; avoid placing the same key in both files and having to reason about precedence.

A YAML file at `src/test/resources/application-test.yml` is valid **config data**. However, `@TestPropertySource(locations = "classpath:/overrides.yml")` does not support YAML like `.properties` files out of the box across setups: Spring Framework supports `.properties`/XML by default; use a custom `PropertySourceFactory` for other formats, or pick a `.properties` file for `@TestPropertySource`.

### 4.3 Config location, additional location, and import

- `spring.config.location` **replaces** the default search locations.
- `spring.config.additional-location` **adds** locations, typically allowing added values to override defaults.
- `spring.config.import` can load config from files, config trees, or external sources; Spring Boot documentation defines specific import ordering rather than guessing by filename.
- `optional:` allows a missing location without failing startup; if you typo a path with `optional:`, the file can silently fail to load.
- `spring.config.name`, `spring.config.location`, and `spring.config.additional-location` are processed **very early**. Set them via env/system properties/command-line or sufficiently early sources, rather than trying to configure them inside a `@PropertySource` bean created later.

If a multi-module project has both `src/main/resources/application.properties` and `src/test/resources/application.properties`, the test runtime classpath can contain two resources at the same path. Behavior depends on how the build constructs the classpath and loads resources; tests should avoid relying on "duplicate definitions at the same classpath path will merge predictably." Use profiles, test properties, or explicit locations transparently.

## 5. Overrides dedicated to the test context

### 5.1 `@ActiveProfiles`: selects a configuration set, not direct values for every key

~~~java
@ActiveProfiles("test")
@SpringBootTest
class CheckoutIntegrationTest {
    // Test context loads the "test" profile.
}
~~~

This snippet only illustrates the annotation in a Spring Boot project with an application class; **it is not a standalone test file**. `@ActiveProfiles` declares the profiles used by Spring TestContext. To inspect the exact active set:

~~~java
@Autowired Environment environment;

// Inside a @Test method:
assertTrue(Arrays.asList(environment.getActiveProfiles()).contains("test"));
~~~

Requires importing `java.util.Arrays`, `org.springframework.core.env.Environment`, `Autowired`, and JUnit assertions; this snippet is also **not standalone**.

**Do not just read `environment.getProperty("spring.profiles.active")` to decide whether `@ActiveProfiles` is active.** A profile activated through TestContext does not necessarily appear as a literal `spring.profiles.active` key in the property source you inspect.

### 5.2 `@SpringBootTest(properties = ...)`: per-test-class overrides

~~~java
@SpringBootTest(properties = {
    "demo.checkout.retries=3",
    "demo.checkout.mode=from-test-annotation"
})
class CheckoutServiceIntegrationTest {
    // ...
}
~~~

`properties` on `@SpringBootTest` and corresponding test slices add key-value pairs into the test `Environment` at higher precedence than standard application config data, env vars, and JVM/CLI args. It is a clear choice for **a small set of fixed values specific to a test**.

However, if you also apply another test override mechanism to **that same key**, the outcome depends on actual precedence, not which annotation sits closer to the class line in source code.

### 5.3 `@TestPropertySource`: file and inline, two levels in one mechanism

~~~java
@TestPropertySource(
    locations = "classpath:/checkout-test.properties",
    properties = {
        "demo.checkout.mode=from-test-inline"
    }
)
class CheckoutServiceIntegrationTest {
    // ...
}
~~~

Within a single `@TestPropertySource`, **inline `properties` beat values for the same key from `locations`**. `@TestPropertySource` ranks high compared to app config, OS env, and JVM system properties.

Relative paths and `classpath:/...` differ in meaning; `classpath:/checkout-test.properties` points to a resource at the classpath root. An empty `@TestPropertySource` annotation makes the framework look for a default file named after the class and fail if missing; always specify `locations` or `properties` intentionally.

With test class inheritance or nested tests, `@TestPropertySource` supports inheriting locations/properties. If a test unexpectedly receives a different value, check annotations on **superclasses, meta-annotations, and test configurations**—not just the current class.

### 5.4 `@DynamicPropertySource`: values supplied by a supplier at runtime

When a Testcontainers port, stub server, or external service changes after startup, storing the final value in a static properties file is awkward. `@DynamicPropertySource` lets you register suppliers:

~~~java
@DynamicPropertySource
static void externalProperties(DynamicPropertyRegistry registry) {
    registry.add("demo.remote.url", () -> "http://127.0.0.1:19090");
}
~~~

The method must be **static**, take one `DynamicPropertyRegistry`, and return `void`. Values are supplied when resolved; here it is a fixed string so the test needs no running container, whereas in real life it might be `container::getJdbcUrl` or `stubServer::baseUrl`.

Spring Framework TestContext documents dynamic properties as taking higher priority than `@TestPropertySource`. Even so, good practice is **not intentionally supplying the same key in multiple test override mechanisms unnecessarily**, and verifying the winner via a test in your actual project. With a superclass sharing `@DynamicPropertySource` while subclasses use different resources, context caching can cause stale reuse; design context identity carefully or apply `@DirtiesContext` selectively.

### 5.5 `@ServiceConnection` and `ConnectionDetails` do not always map to a single property

In Spring Boot versions supporting Testcontainers service connections, `@ServiceConnection` can produce **`ConnectionDetails`** beans consumed directly by Spring auto-configuration to build datasources/clients. In that case, an actual `DataSource` can get its endpoint from connection details rather than any `spring.datasource.url` in `Environment`.

Therefore, to verify **which database is actually connected**:

1. Verify active profiles and relevant properties.
2. Inspect the `DataSource` / `JdbcConnectionDetails` bean or bound configuration.
3. For DB tests, inspect JDBC metadata from a **real connection** rather than guessing solely from `Environment.getProperty("spring.datasource.url")`.

Illustrative snippet inside an integration test with a configured datasource and live connection:

~~~java
@Autowired DataSource dataSource;

@Test
void connectsToExpectedDatabase() throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        String url = connection.getMetaData().getURL();
        assertTrue(url.startsWith("jdbc:postgresql:"));
    }
}
~~~

This is **not a standalone test file**; it requires importing `javax.sql.DataSource`, `java.sql.Connection`, `java.sql.SQLException`, `@Autowired`, `@Test`, and `assertTrue`. It only checks that the JDBC URL is PostgreSQL, not that a production DB was avoided; add assertions on database name, schema, or **test environment** connection details as needed. Avoid printing passwords or full URLs containing credentials.

## 6. Complete Java 17+ example: reproducing precedence and verifying final values

This example is **runnable inside a Spring Boot 3.x module with Java 17+**, requiring no database, Docker, HTTP server, or separate production app. We deliberately place the same key in four places to observe overrides:

- Common config data file.
- Profile `test` config data file.
- Test-only `@TestPropertySource(locations = ...)`.
- Inline test annotations `@SpringBootTest(properties = ...)` and `@TestPropertySource(properties = ...)`.

Another key is supplied by `@DynamicPropertySource` **without colliding on the same key** as the inline test overrides, so the example does not rely on tie-breaking between those two high-priority mechanisms.

### 6.1 Directories and files

~~~text
src/
  test/
    java/
      example/
        PropertyPrecedenceTest.java
    resources/
      application.properties
      application-test.properties
      priority-test.properties
~~~

In standard Gradle or Maven Spring Boot projects, `src/test/resources` appears on the runtime test classpath. No separate production `@SpringBootApplication` is required because the test includes its own minimal configuration.

### 6.2 File `src/test/resources/application.properties`

~~~properties
demo.checkout.mode=base
demo.checkout.retries=2
demo.checkout.region=base-region
demo.checkout.endpoint=http://base.invalid
~~~

### 6.3 File `src/test/resources/application-test.properties`

~~~properties
demo.checkout.mode=profile-test
demo.checkout.retries=7
demo.checkout.region=profile-region
demo.checkout.endpoint=http://profile.invalid
~~~

`@ActiveProfiles("test")` on the test activates this profile file. `retries=7` is only in config data; subsequent test overrides leave this key untouched to prove **the profile file beats the common file**.

### 6.4 File `src/test/resources/priority-test.properties`

~~~properties
demo.checkout.mode=test-file
demo.checkout.region=test-file-region
~~~

This file is **not loaded automatically just because its name includes `test`**. It is explicitly requested via `@TestPropertySource(locations = "classpath:/priority-test.properties")`.

### 6.5 File `src/test/java/example/PropertyPrecedenceTest.java`

~~~java
package example;

import java.net.URI;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.Environment;
import org.springframework.core.env.PropertySource;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.TestPropertySource;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@ActiveProfiles("test")
@SpringBootTest(
        classes = PropertyPrecedenceTest.TestApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "demo.checkout.mode=boot-test")
@TestPropertySource(
        locations = "classpath:/priority-test.properties",
        properties = {
                "demo.checkout.mode=test-inline",
                "demo.checkout.region=inline-region"
        })
@DisplayName("Spring Boot property precedence")
class PropertyPrecedenceTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableConfigurationProperties(CheckoutSettings.class)
    static class TestApplication {
    }

    @ConfigurationProperties(prefix = "demo.checkout")
    public record CheckoutSettings(
            String mode,
            int retries,
            String region,
            URI endpoint) {
    }

    @DynamicPropertySource
    static void provideDynamicEndpoint(DynamicPropertyRegistry registry) {
        // Simulates an endpoint known at runtime without needing a real server.
        registry.add(
                "demo.checkout.endpoint",
                () -> "http://127.0.0.1:19090");
    }

    @Autowired
    Environment environment;

    @Autowired
    ConfigurableEnvironment configurableEnvironment;

    @Autowired
    CheckoutSettings settings;

    @Value("${demo.checkout.mode}")
    String injectedMode;

    @Test
    @DisplayName("Inline TestPropertySource overrides files and Boot test properties")
    void inlineTestPropertyWinsForMode() {
        assertAll(
                () -> assertEquals("test-inline",
                        environment.getRequiredProperty("demo.checkout.mode")),
                () -> assertEquals("test-inline", injectedMode),
                () -> assertEquals("test-inline", settings.mode()));
    }

    @Test
    @DisplayName("Test profile supplies keys not overridden in test annotations")
    void activeProfileSuppliesRetries() {
        assertAll(
                () -> assertEquals(7,
                        environment.getRequiredProperty(
                                "demo.checkout.retries", Integer.class)),
                () -> assertEquals(7, settings.retries()),
                () -> assertTrue(Arrays.asList(
                        environment.getActiveProfiles()).contains("test")));
    }

    @Test
    @DisplayName("Inline properties beat TestPropertySource locations")
    void inlineOverridesTestResource() {
        assertAll(
                () -> assertEquals("inline-region",
                        environment.getRequiredProperty("demo.checkout.region")),
                () -> assertEquals("inline-region", settings.region()));
    }

    @Test
    @DisplayName("DynamicPropertySource supplies the final bound endpoint")
    void dynamicEndpointIsUsed() {
        URI expected = URI.create("http://127.0.0.1:19090");

        assertAll(
                () -> assertEquals(expected.toString(),
                        environment.getRequiredProperty(
                                "demo.checkout.endpoint")),
                () -> assertEquals(expected, settings.endpoint()));
    }

    @Test
    @DisplayName("Lists sources with the same key without guessing source names")
    void canInspectCompetingSources() {
        List<String> candidates = sourcesContaining(
                "demo.checkout.mode");

        assertFalse(candidates.isEmpty());
        assertEquals("test-inline",
                environment.getRequiredProperty("demo.checkout.mode"));

        // When debugging, set a breakpoint and inspect candidates.
        // Do not assert PropertySource names since they depend on version.
    }

    private List<String> sourcesContaining(String key) {
        List<String> names = new ArrayList<>();

        // Iteration order: highest to lowest priority.
        for (PropertySource<?> source :
                configurableEnvironment.getPropertySources()) {
            if (source.getProperty(key) != null) {
                names.add(source.getName());
            }
        }

        return names;
    }
}
~~~

**The test above is self-contained for Spring configuration**: `@SpringBootConfiguration`, `@EnableAutoConfiguration`, and `@EnableConfigurationProperties` create a minimal context to bind the `CheckoutSettings` record. No other application beans, network, or Docker are needed. The tests use JUnit Jupiter from Spring Boot starter test. `webEnvironment = NONE` skips creating a web server.

**Notable design point:** all five test methods share one Spring test context; global properties are never mutated between tests. `demo.checkout.endpoint` is supplied via a static supplier. `CheckoutSettings` is a configuration properties record bound by Spring Boot via its constructor; the real object must receive the final `URI` from the winning source.

### 6.6 Why are the results predicted as follows?

| Key | Common file | Test profile file | Test resource | `@SpringBootTest` inline | `@TestPropertySource` inline | Dynamic | Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `demo.checkout.mode` | `base` | `profile-test` | `test-file` | `boot-test` | `test-inline` | — | **`test-inline`** |
| `demo.checkout.retries` | `2` | `7` | — | — | — | — | **`7`** |
| `demo.checkout.region` | `base-region` | `profile-region` | `test-file-region` | — | `inline-region` | — | **`inline-region`** |
| `demo.checkout.endpoint` | `http://base.invalid` | `http://profile.invalid` | — | — | — | `http://127.0.0.1:19090` | **`http://127.0.0.1:19090`** |

Each value is verified from two angles:

1. `environment.getRequiredProperty(...)`: the effective value in `Environment`, including type conversion to `Integer.class`.
2. `settings...()` or `@Value`: the value the bean/test field **actually receives** from Spring, not merely what sits in a file.

For `mode`, all three reads must equal `test-inline`. For `endpoint`, no real server is running, yet `URI` binding proves conversion succeeded; **it does not prove network connectivity succeeded**.

If a test fails solely because the CI environment injects a different key from a higher-priority source, the test exposes **that the actual value differed**. Then investigate the original source rather than changing the assertion to match whatever random machine value happened to appear.

### 6.7 Gradle setup and run commands

In `build.gradle` of a **Spring Boot project that already has the plugin/dependency management**, these basic dependencies must be present:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This is only an **addition snippet**, not a complete `build.gradle`. The Java toolchain should be Java 17 or newer. With the project's Gradle wrapper:

~~~bash
./gradlew test --tests example.PropertyPrecedenceTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.PropertyPrecedenceTest
~~~

**Expected outcome:** JUnit Jupiter discovers **5 test methods** and all five PASS on a properly configured project. The tests print no stdout themselves; Gradle/IDE verbosity varies so there is no fixed stdout string. When Gradle completes cleanly, it prints a status like `BUILD SUCCESSFUL` if related tasks also succeed.

**Version note:** the example uses Spring Boot 3.x with constructor-bound record configuration properties and JUnit Jupiter. For Spring Boot 4.x, check your project's migration guide and current module dependencies; `Environment`/TestContext principles still apply, though you should not blindly copy Gradle configuration across major versions.

## 7. How do you find the exact winning source?

Suppose a test receives `demo.checkout.mode=unexpected`. Searching the entire repository for the key name may return many files without showing which one **actually loaded and won**. Instead of guessing, inspect `ConfigurableEnvironment` at runtime.

### 7.1 Iterating `PropertySource`s in order

In a Spring Boot test injected with `ConfigurableEnvironment`, you can add a helper method:

~~~java
static void diagnose(ConfigurableEnvironment env, String key) {
    System.out.println("Effective: " + env.getProperty(key));
    for (PropertySource<?> source : env.getPropertySources()) {
        Object candidate = source.getProperty(key);
        if (candidate != null) {
            System.out.println(source.getName() + " -> " + candidate);
        }
    }
}
~~~

**This is an illustrative snippet** inside code with `ConfigurableEnvironment` and `PropertySource` imports, not a standalone file. Run it only on **non-sensitive keys** like `demo.checkout.mode`; never use it to print passwords, private keys, tokens, or the entire environment.

The list is traversed from highest to lowest priority; the first source matching the direct key name normally determines the value. However:

- A `PropertySource` may transform key names (especially environment variables or configuration-binding wrappers).
- Effective values via `Environment` may have placeholders resolved and types converted, differing from raw values in the property source.
- `@ConfigurationProperties` applies relaxed binding, so verifying the bound bean is an essential extra step.
- If the application registers custom `PropertySource`s, ordering can differ from the default diagram.
- Values can be adjusted by wrappers, proxies, or connection-details outside `Environment`.

Do not write assertions demanding a source name equal `"Inlined Test Properties"` or a specific internal class name; source naming/formatting can change across versions. **Assert the final value** and use source names for diagnosis.

### 7.2 Reading origin (file, line, location) when Spring Boot provides it

Spring Boot supports origin tracking for many config data sources. You can extend the helper:

~~~java
import org.springframework.boot.origin.Origin;
import org.springframework.boot.origin.OriginLookup;

static void diagnoseOrigin(ConfigurableEnvironment env, String key) {
    for (PropertySource<?> source : env.getPropertySources()) {
        Object value = source.getProperty(key);
        if (value == null) {
            continue;
        }

        Origin origin = OriginLookup.getOrigin(source, key);
        System.out.println("source=" + source.getName()
                + ", origin=" + (origin == null
                ? "not available" : origin));
    }
}
~~~

This is **illustrative code to place in a class/helper with Spring imports**, not a `main` program. `OriginLookup.getOrigin(...)` can return `null` for sources that do not support origin tracking. For application properties/YAML files with origin tracking, the info usually pinpoints the **resource and line/column position**. For system properties or inline test overrides, it may show only the source name rather than a file path or line.

Never assert file line numbers in CI: editing comments or reordering lines will break tests without changing behavior. Origin is an **investigation tool**, not part of a business contract.

### 7.3 Distinguishing `Environment` from bound `@ConfigurationProperties`

If `environment.getProperty("demo.checkout.retries")` returns `7` yet the service uses `10`, possible reasons include:

- The bean was created before a property source change took effect.
- The service applies its own default/clamp/transform (e.g., `Math.max(10, retries)`).
- Another `@Bean` builds the client from `ConnectionDetails`.
- The value was bound under a relaxed/aliased name or a different prefix.
- Multiple `@ConfigurationProperties` beans exist and the service injected the wrong one.
- The value was cached, refreshed, or overridden by runtime code.

How to verify real effectiveness:

1. `Environment`: assert source resolution.
2. **Configuration bean**: assert the actual `@ConfigurationProperties` or `@Value`.
3. **Consuming bean/client**: assert observable fields/getters/metadata or connection-creation behavior.
4. For databases, HTTP, Kafka: test actual interaction/connection if that is required, not just text properties.

Only when step 3 or 4 reflects the expected setting do you have strong evidence that **runtime is using the intended configuration**.

## 8. Actuator `env` and `configprops`: diagnosing outside the test runner

If the application includes `spring-boot-starter-actuator`, these endpoints help:

- `/actuator/env`: lists property sources, active/default profiles, and properties visible through the environment.
- `/actuator/env/{property.name}`: focuses on one key, its winning source, and candidate sources.
- `/actuator/configprops`: inspects `@ConfigurationProperties` beans and bound values, revealing discrepancies between config files and final objects.

Example **only for controlled dev/test environments with restricted access**:

~~~properties
management.endpoints.web.exposure.include=health,env,configprops
~~~

Once an application **with Actuator and a web server is running**, you can run:

~~~bash
curl http://localhost:8080/actuator/env/demo.checkout.mode
~~~

Do not assume this command works against the Section 6 example, which uses `webEnvironment = NONE` and enables no Actuator. Endpoints may also have a different prefix, port, or be protected by Spring Security.

**Security warning:** `env` and `configprops` can expose sensitive data. Spring Boot sanitizes values by default per Actuator settings. Never set `management.endpoint.env.show-values=always` in unprotected environments, never disable sanitization for secrets, and never expose endpoints publicly just for debugging. In unit/integration tests, asserting **non-secret** keys is safer and far more stable.

## 9. Cases that easily lead to misunderstanding precedence

### 9.1 `@ActiveProfiles` does not "override the entire Environment"

`@ActiveProfiles("test")` only selects active profiles. Other config sources—environment variables, JVM `-D`, test annotations—can still beat keys from the profile file. To prevent CI host settings from interfering with tests, override critical keys inside the test context intentionally.

### 9.2 JVM system properties, IDE settings, and Gradle

A command like:

~~~bash
java -Ddemo.checkout.retries=12 -jar my-app.jar
~~~

is an example of a **JVM system property for a packaged application**. Yet when running JUnit via Gradle, the test JVM may be a **forked process**; system properties on the Gradle daemon, IDE, and test JVM are not automatically identical. To pass properties to a Gradle test task, explicitly configure `systemProperty` or runtime test flags instead of assuming `-D` reaches the right JVM.

Illustrative snippet inside an existing `build.gradle`:

~~~groovy
tasks.named('test') {
    useJUnitPlatform()
    systemProperty 'demo.checkout.retries', '12'
}
~~~

When applied, test thresholds can change if **no higher-precedence test override exists**. In the Section 6 example, `retries` would see `12` from the system property instead of `7`, because the example **does not override `retries`** via a test annotation. That is a deliberate modification to demonstrate precedence; **do not add this setting while running the 5-PASS suite in Section 6**.

### 9.3 OS environment variables and relaxed binding

In a shell, `DEMO_CHECKOUT_RETRIES=12` normally maps to `demo.checkout.retries` for Spring Boot binding. Use canonical kebab-case in `@Value` and clear structures in `@ConfigurationProperties`. Env var naming rules go beyond replacing dots with underscores: list indices and map keys follow specific rules.

Checking `System.getenv("DEMO_CHECKOUT_RETRIES")` only proves the shell exported the variable; it does not prove `Environment` chose it. Verify both the winning property and the bound bean.

### 9.4 YAML profile documents with `spring.config.activate.on-profile`

In `application.yml`, multiple YAML documents can use `spring.config.activate.on-profile` to load a document only for a specific profile. However, `spring.profiles.active` and `spring.profiles.default` must reside in **non-profile-specific documents**—never inside a document already gated on a profile expecting it to activate additional profiles.

`spring.profiles.include` and `spring.profiles.group.*` also carry rules requiring non-profile-specific documents. Violating these can cause Spring Boot configuration errors or unexpected active profiles.

### 9.5 `@TestPropertySource` YAML and duplicate resource names

`@TestPropertySource` accepts `.properties`/XML by default, and does not read YAML the way Spring Boot config data does. To use a test profile YAML, put it in `application-test.yml` and activate the profile; if you need a custom YAML location in `@TestPropertySource`, use a compatible `PropertySourceFactory` for your Spring Framework version.

When two files with the same name appear across modules/classpath locations, **never guess how they merge**. Specify explicit `classpath:/...` paths and inspect origin.

### 9.6 Test context caching

Spring TestContext **caches `ApplicationContext`** across test classes with equivalent context configurations. If test A calls `System.setProperty("demo.checkout.retries", "99")` mid-suite and test B reuses a cached context or already-bound bean, results become confusing. Put configuration in **test annotations/fixtures** rather than mutating process-global state.

If dynamic properties differ per subclass while sharing a base class configuration, separate context configurations or apply `@DirtiesContext` selectively. Even then, `@DirtiesContext` incurs startup overhead and should not be slapped on every test merely to mask unclear configuration.

### 9.7 Declaration order in source code is not precedence order

Putting `@TestPropertySource` above `@SpringBootTest` in Java source, or reordering lines inside an annotation, does not decide precedence. Spring Boot and Spring TestContext mechanics decide it. Do not rely on annotation order during code review.

### 9.8 `ConnectionDetails` can bypass raw key values

In Spring Boot with service connections, reading `spring.datasource.url` does not prove the final JDBC connection uses that URL. Tests should inspect the real `DataSource` or connection metadata and confirm they are not accidentally hitting a production database. That is why a lesson on **"the value actually used"** cannot stop at reading property sources.

## 10. Test strategies to guard against environment-specific config bugs

Testing strategy table:

| What you want to be sure of | How to check | Example assertion |
| --- | --- | --- |
| Which profile the test uses | `Environment.getActiveProfiles()` | `test` is in active set |
| Profile config data overrides common key | Spring context test | `retries == 7` |
| Inline test override beats file | `@TestPropertySource` + env | `mode == "test-inline"` |
| Bean receives bound value | `@ConfigurationProperties` / `@Value` | `settings.mode()` matches |
| Dynamic API endpoint registered | `@DynamicPropertySource` | `settings.endpoint()` matches |
| Which source supplied the property | `ConfigurableEnvironment.getPropertySources()`, origin | Name of first source with the key |
| Which DB the system connects to | Integration test with real `DataSource` | Valid JDBC URL/schema/metadata |
| CI env vars blocked by test override | Test run in CI with controlled inputs | Final result as specified |
| Secrets not exposed when debugging | Security review, Actuator sanitization | No plain-text credentials logged |

Not every test needs `@SpringBootTest`. For a class using `@ConfigurationProperties` and validation, you can test binding with `ApplicationContextRunner` or a focused test slice without booting the whole app; when verifying **config data/profiles/test annotations of the actual Spring Boot context**, an integration test structured like Section 6 is easier to explain.

### Do not adjust assertions to "match the environment"

If `retries` evaluates to `12` on CI instead of `7`, do not casually change `assertEquals(7, ...)` to `12` without understanding the source. Determine whether CI passes a `-D` flag or env var, how properties reach the test JVM, and whether the test needs a fixed override to stay isolated or is intentionally testing host environment interaction.

Well-targeted tests express **values expected by the contract**; that goal dictates whether host overrides should be allowed.

## 11. Workflow for investigating an unexpected configuration value

Suppose a Spring service has a 30-second request timeout in dev yet CI yields 5 seconds:

1. **Identify the exact key** the bean consumes—such as `demo.http.request-timeout`—avoiding confusion with unrelated keys like `server.tomcat.connection-timeout`.
2. **Determine the context and phase:** is the test running via `@SpringBootTest`, `@WebMvcTest`, or no Spring context? Did the bean bind at startup or compute per request?
3. **Read the actual active profiles:** `getActiveProfiles()`, checking profile groups/includes, not just filenames.
4. **Read the effective property:** `environment.getProperty(key)`, with target type when possible.
5. **Walk sources in precedence order:** find the first source holding that key and see which candidates are shadowed.
6. **Inspect origin when available:** file, line, resource, or system/environment/test inline source.
7. **Inspect the real bean:** `@ConfigurationProperties`, `@Value`, client settings, timeout builder, or connection details, depending on how the app consumes it.
8. **Check runtime inputs:** IDE run config, Gradle test JVM, CI secrets/env, Maven Surefire system properties, command-line args.
9. **Fix at the right layer:** adjust config data/profile, add a test override, fix the key name, fix bean binding, or fix container/connection-details wiring.
10. **Lock it in with a regression test:** assert the expected value and consuming bean without hardcoding fragile source names.

The concrete `CheckoutSettings` test in Section 6 serves as a **regression test**: if configuration order changes or `@ActiveProfiles("test")` is accidentally dropped, at least the `retries`/profile assertions will catch it.

## 12. Common misconceptions

**Misconception 1 — "`application-test.properties` always has the highest priority."**  
False. Profile files are config data; environment variables, JVM system properties, certain command-line args, and test overrides can beat them. Fix: inspect `Environment` and beans.

**Misconception 2 — "Because `@ActiveProfiles` is present, `Environment` definitely has `spring.profiles.active=test`."**  
`@ActiveProfiles` configures TestContext; literal property sources may differ. Use `getActiveProfiles()` as proof.

**Misconception 3 — "`priority-test.properties` contains `test` in its name so it loads automatically."**  
False. Arbitrary files must be referenced by `@TestPropertySource`, `spring.config.import`, or another explicit loader.

**Misconception 4 — "Passing YAML to `@TestPropertySource(locations=...)` works just like `application.yml`."**  
Spring TestContext does not support every format at `locations` out of the box. For YAML, use config data or an appropriate factory.

**Misconception 5 — "Adding `@PropertySource` can override any startup setting."**  
Many `logging`/`main` settings are read earlier than `@PropertySource` processing during refresh. Use externalized configuration sources active at the right phase.

**Misconception 6 — "`@SpringBootTest(properties)` and `@TestPropertySource` are completely identical."**  
They are separate declaration mechanisms with precedence rules to understand. Avoid setting the same key in both unless intentionally testing overrides.

**Misconception 7 — "`DynamicPropertySource` is always evaluated once at registration time."**  
The registry accepts a supplier; values are supplied at resolution time, not necessarily on the registration line. If a supplier has side effects or reads mutable time-varying state, tests become unstable.

**Misconception 8 — "Checking `Environment` is enough to prove the JDBC client uses the right URL."**  
Not true when connection details, client builders, or caches intervene. Inspect the real bean/client and connection when needed.

**Misconception 9 — "Calling `System.setProperty` in `@BeforeEach` isolates each test."**  
System properties are JVM-wide state and break parallel execution and context caching. Prefer test annotations; if mutation is unavoidable, strictly restore and isolate it.

**Misconception 10 — "First source with an expected name means the value bound properly."**  
Source names are metadata; the binder applies relaxed binding and conversion. Assert the real bean too.

**Misconception 11 — "Underscore env var names can be guessed arbitrarily."**  
Spring Boot relaxed binding follows specific rules (casing, hyphens, list indices). Verify canonical names and actual binding outcomes.

**Misconception 12 — "Any key in the application can be logged for debugging."**  
Never log secrets, passwords, tokens, keys, or entire `Environment`/Actuator dumps. Query only safe keys, lock down endpoints, and respect sanitization.

**Misconception 13 — "Versions don't matter because all precedence docs say the exact same thing."**  
Spring Boot, Spring Framework, test runners, and extensions evolve. When two docs describe colliding high-priority test sources inconsistently, measuring inside the running context is the definitive check. Avoid setting the same key across multiple high-precedence mechanisms unnecessarily.

**Misconception 14 — "Lists in config are always appended across profile and base files."**  
With `@ConfigurationProperties`, binding a list typically replaces values from lower-priority sources rather than appending. Inspect the bound object instead of assuming concatenation.

## 13. Advanced practice: test the consuming bean instead of only the key

Some settings affect behavior in ways `getProperty` alone cannot verify.

### HTTP client timeouts

A bean built in `@Configuration` might read `demo.http.timeout` and scale or convert it into a `Duration`. Tests should check the timeout configured on the client builder if the API allows, or verify behavior against a controlled stub server. Do not assert a raw `5000` and assume the client uses 5 seconds.

### Testcontainers database connections

With `@DynamicPropertySource`, you can supply `spring.datasource.url` from `container::getJdbcUrl`; with `@ServiceConnection`, auto-configuration can consume `ConnectionDetails`. Those are two distinct designs; avoid configuring two competing sources accidentally and guessing order. Integration tests should inspect connection metadata/schemas or execute an actual query against the database container.

### `@ConfigurationProperties` mappings with defaults

Records or beans with defaults can fall back when a property is missing, or validation can reject invalid values. Tests should assert the **final value on the bean** as well as missing/invalid cases, not just raw property sources. Pay special attention to `Duration`, `DataSize`, and case-insensitive enum conversion when code relies on binding.

### Systems with refresh or dynamic configuration

Some applications use a config server, refresh scopes, `EnvironmentChangeEvent`, or runtime-reloading code. In those systems, define **at which point in time** "actually used" is measured. Startup binding unit tests and refresh integration tests may need separation; never assume every bean updates automatically when a property source changes.

## 14. Pre-finalization checklist for test configuration

- [ ] Know the exact **canonical key** and **consuming bean/client** for the property.
- [ ] Distinguish common files, profile files, external config, OS env, JVM system props, command-line args, and test annotations.
- [ ] `@ActiveProfiles` verified via `getActiveProfiles()`; no guessing from filenames.
- [ ] If using `@TestPropertySource`, verify `locations` and inline `properties`; inline can override files.
- [ ] For `@DynamicPropertySource`, method is `static`, accepts `DynamicPropertyRegistry`, and supplier does not rely on flaky state.
- [ ] Avoid setting the same key across multiple high-precedence test-specific sources unless precedence itself is under test.
- [ ] Verified effective values via `Environment` and **bound beans** (`@Value`/`@ConfigurationProperties`) where appropriate.
- [ ] When troubleshooting, iterate `ConfigurableEnvironment.getPropertySources()` in order and inspect origins if available.
- [ ] If using `@ServiceConnection`/`ConnectionDetails`, inspect the real client/connection instead of only reading `spring.datasource.url`.
- [ ] No uncontrolled `System.setProperty` across tests or polluted context caches.
- [ ] CI/test JVM environment variables configured deliberately, independent of developer machine settings.
- [ ] No secrets logged, no exposed Actuator `env`/`configprops`, and no disabled sanitization for convenience.
- [ ] Precedence measurements performed on the **exact Spring Boot/Framework version** and right test context type.
- [ ] Regression tests focus on the contract: selected configuration and its real effect on beans/outputs.

**Conclusion:** configuration precedence is only the **map**. The source of truth at test runtime is `Environment` and the beans/clients constructed from it. When two places declare the same key, do not fix configuration by intuition: verify active profiles, the winning source, and bound values—then place the test override in one clear spot and lock down the behavior with assertions.

### Official references

- [Spring Boot 3.5 — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): property source order, config data locations, profile-specific files, and test overrides.
- [Spring Boot — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html): `spring.profiles.active`, `spring.profiles.include`, profile groups, and ordering.
- [Spring Framework — Context Configuration with Test Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html): `@TestPropertySource`, inline/file precedence, and inheritance.
- [Spring Framework — Context Configuration with Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): `@DynamicPropertySource`, dynamic suppliers, relative precedence, and context caching.
- [Spring Framework — Environment Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html): `Environment`, `ConfigurableEnvironment`, and `PropertySource`.
- [Spring Boot — Actuator Environment Endpoint](https://docs.spring.io/spring-boot/api/rest/actuator/env.html): inspecting property sources, origins, and effective properties at runtime.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): `env`/`configprops` and sanitization.
- [Spring Boot — OriginLookup API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/origin/OriginLookup.html): reading origins when supported by a property source.