# Components That Form the Cache Key: Configuration, Profiles, Properties, and Bean Overrides

In a Spring Boot test suite, **starting the ApplicationContext** often takes more time than running assertions. Spring TestContext addresses this with the **context cache**: if a later test needs the **same context configuration** as an earlier test in the same JVM, the framework can **reuse the already initialized ApplicationContext**. However, "same configuration" is determined by a **multi-component cache key**, not simply by test class name or sharing `@SpringBootTest`.

For example:

- Two test classes with different names but the same configuration set, active profiles, test properties, and bean overrides **can share a context**.
- One test adds `@ActiveProfiles("qa")` while another uses `"dev"` → **different cache key**.
- Two tests both use `@SpringBootTest`, but one declares `@MockitoBean ExternalClient` and the other does not → **different contextCustomizers**, so a separate context must be created.
- Two tests mock the same bean but use different **field name fallback qualifiers**, `@Qualifier`s, or override names, which can produce **two different keys** even if the business goal looks very similar.
- A different `@DynamicPropertySource` method can change the key; however, **the value returned at runtime by the same supplier** is not automatically used as a new cache key on every runtime change.
- `@DirtiesContext` explicitly evicts a context from the cache; that is **eviction**, not one of the configuration values in the key.

This article belongs to the **Context cache and performance** section of **Spring Boot - testing**, focusing on **“Components That Form the Cache Key: Configuration, Profiles, Properties, and Bean Overrides”**. We will look closely at the exact list of key-forming attributes in Spring Framework 6.2, how Spring Boot/Jakarta/Mockito annotations participate, reasons for cache hits/misses, statistics logs, LRU, JVM forks, `@DirtiesContext`, a Java 17 + Spring Boot 3.5 hands-on demo, and how to improve suite runtime without introducing inter-test dependencies.

**Core rule:** the context cache is a mechanism to **reuse Spring beans**, not a mechanism that automatically isolates mutable bean state. Optimizing hit rate must go hand in hand with strategies for resetting mocks, test data, queues, and external resources to maintain proper test isolation.

## 1. How does the Spring TestContext cache work?

Spring TestContext loads an `ApplicationContext` or `WebApplicationContext` when a test requires Spring-managed beans. After loading successfully, Spring can store the context in the JVM process's **static cache** and look it up by `MergedContextConfiguration` on subsequent runs.

```text
JUnit test class A
       |
       v
TestContextBootstrapper
       |
       v
MergedContextConfiguration
  + classes / locations
  + initializers / loader / parent
  + profiles / property sources
  + context customizers (bean overrides, dynamic props,...)
  + resource base path
       |
       v
   build cache KEY
       |
       +---- cache HIT  ------> reuse ApplicationContext instance
       |                       (singleton beans remain in context)
       |
       +---- cache MISS ------> load / refresh new ApplicationContext
                               -> cache put / LRU eviction
       |
       v
    inject beans into test
    execute test method
```

Key distinctions:

| Concept | Meaning | Important to remember |
|---|---|---|
| Cache hit | Key already has an active context | Usually avoids re-initializing the context |
| Cache miss | No context matches the key | Incurs startup, auto-config, bean creation, DB fixtures depending on app |
| Cache key | Set of merged configuration attributes | Does not include **test class name** by default |
| Cache size | Number of context entries in the JVM | Default maximum **32**, not 32 test methods |
| Eviction | Removing a context from the cache | LRU or `@DirtiesContext`; context may be closed |
| Context state | Existing singletons/caches/connections | Can be mutated by earlier tests if reused |
| Fork JVM | A separate Java process | Static cache is **not** shared across JVMs |

A test running very fast **does not prove a cache hit by itself**: it might simply be starting a small context. A test running slowly **is not always a cache miss**: its assertions might be querying a DB or waiting on network I/O. Use **cache statistics** together with context identity evidence to understand the cause.

## 2. Exact list of cache key components

According to official Spring Framework 6.2 documentation, the `MergedContextConfiguration` key uses the following attributes:

| Key component | Typical source | Example change that alters the key |
|---|---|---|
| **`locations`** | `@ContextConfiguration(locations=...)` | Changing XML/config resource |
| **`classes`** | `@ContextConfiguration(classes=...)` and configuration classes inferred by Spring Boot | `ConfigA.class` differs from `ConfigB.class` |
| **`contextInitializerClasses`** | `@ContextConfiguration(initializers=...)` | `InitA.class` differs from `InitB.class` |
| **`contextCustomizers`** | `ContextCustomizerFactory`: `@DynamicPropertySource`, `@MockitoBean`, `@MockitoSpyBean`, `@TestBean`, Boot test customizations, etc. | Adding mock/spy, changing bean override, different DynamicPropertySource method |
| **`contextLoader`** | `@ContextConfiguration(loader=...)`, Boot test bootstrapper | Different loader class |
| **`parent`** | `@ContextHierarchy` | Different parent context configuration |
| **`activeProfiles`** | `@ActiveProfiles`, resolvers, and inheritance | `qa` differs from `prod` |
| **`propertySourceDescriptors`** | `@TestPropertySource(locations=...)` | `classpath:/a.properties` differs from `b.properties` |
| **`propertySourceProperties`** | `@TestPropertySource(properties=...)` and related inline test config | `feature.mode=a` differs from `feature.mode=b` |
| **`resourceBasePath`** | `@WebAppConfiguration` | Different web resource root |

**Easy-to-miss detail:** `contextCustomizers` is a major key component and is easily fragmented by **Spring Boot** and **Spring Framework 6.2** test mechanisms. A mock field annotation that seems to affect only one test method can actually change the **bean configuration of the entire context**. Fallback field names, bean names, qualifiers, override strategies, and the list of overrides must stay consistent if reuse is desired.

### Is the test class name directly in the key?

Not as an independent key field. Spring Framework's `MergedContextConfiguration.hashCode()` intentionally **excludes `testClass`** so two test classes with equivalent merged configurations can share a context. However, **the test class can influence it indirectly**: it declares profiles, properties, nested configurations, `@DynamicPropertySource` methods, mocks, imports, or other customizers.

```text
CustomerServiceTest     PaymentServiceTest
  @SpringBootTest          @SpringBootTest
  same config/profiles     same config/profiles
  no bean overrides        no bean overrides
        |                       |
        +-------- SAME KEY -----+
                        |
                        v
               shared ApplicationContext
```

If one class uses `@SpringBootTest(classes=A.class)` and another uses `@SpringBootTest(classes=B.class)`, different `classes` → different key, even if both configurations create beans that "look identical".

## 3. Configuration: classes, locations, loader, initializers, parent

### 3.1. `@SpringBootTest(classes=...)`

Example:

```java
@SpringBootTest(
    classes = ApplicationForTest.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ServiceIntegrationTest {
}
```

`@SpringBootTest` is the entry point for initializing a Spring Boot application test context. `classes` affects the merged configuration and thus the cache key. Certain Boot test differences such as `webEnvironment`, `properties`, and context customizers can also alter the key; do not infer from two classes using the same general annotation that they will share.

**For intentional reuse**, multiple test classes can specify **a single configuration class** instead of each test declaring its own nested `@TestConfiguration` class for a minor tweak. Still, never compromise correctness: if a test truly needs a different bean graph, a separate context is the right outcome.

### 3.2. `@ContextConfiguration` and initializers

```java
@ContextConfiguration(
    classes = ApplicationForTest.class,
    initializers = FeatureInitializer.class)
class FeatureTest {
}
```

Changing `FeatureInitializer.class` to a different class alters `contextInitializerClasses`. This holds true even when two initializers set the **exact same property value**: the cache key is based on **declarations**, rather than running the application and comparing the resulting bean graph.

### 3.3. Context hierarchy and web resource base path

- `@ContextHierarchy` creates parent/child relationships; a child's key includes the parent configuration. `@DirtiesContext(hierarchyMode=...)` can evict multiple related contexts.
- `@WebAppConfiguration("src/main/webapp")` contributes to `resourceBasePath`; a web test context can differ from a non-web context.
- `@ContextConfiguration(loader=CustomLoader.class)` changes `contextLoader`, even with identical config classes.

These attributes appear less often in unit tests but matter for legacy XML, servlet web contexts, and multi-layered Spring contexts.

## 4. Active profiles and differing bean behavior

`@ActiveProfiles` selects the set of Spring profiles when creating the test context:

```java
@SpringBootTest(classes = CacheDemoApplication.class)
@ActiveProfiles("local")
class LocalTest {
}

@SpringBootTest(classes = CacheDemoApplication.class)
@ActiveProfiles("staging")
class StagingTest {
}
```

The two contexts have different keys even if neither profile **declares any `@Profile` beans**. Spring does not optimize by building contexts and checking if beans match; the key is computed **before startup**, based on metadata. Assigning an arbitrary per-class profile can increase context count and suite duration.

### Profile resolution and inheritance

- `@ActiveProfiles({"test","postgres"})` can differ from `@ActiveProfiles("test")`.
- Profiles from a superclass/enclosing test class can be inherited depending on `inheritProfiles`.
- A custom `ActiveProfilesResolver` can return profiles dynamically; stable reuse requires a configuration-deterministic resolver.
- Changing the `spring.profiles.active` property via another source **does not replace** understanding `@ActiveProfiles` and the relevant key fields; verify which annotations/properties are actually merged.
- Spring Framework normalizes certain profile values (e.g., deduplicating/sorting in merged configuration), so do not assume merely reordering text always creates a new key. Check metadata/logs or test actual identity.
- A profile that produces a different bean graph requires its own context; **never force sharing** by removing an important annotation just to shave test time.

### Unified test fixture profile

When multiple integration tests run against the same fake database or Testcontainers service with identical bean definitions, a base test class can be used:

```java
@ActiveProfiles("integration")
abstract class IntegrationBaseTest {
}
```

This is a snippet, not a runnable file: test subclasses still need `@SpringBootTest` or appropriate Spring test context config. A base test class keeps the profile policy consistent, but **does not guarantee the same key** if subclasses still declare different `@MockitoBean`/`@DynamicPropertySource`/properties.

## 5. Test properties: inline, files, Boot annotations, and dynamic suppliers

### 5.1. `@TestPropertySource(properties=...)`

```java
@TestPropertySource(properties = "checkout.mode=stub")
class StubModeTest {}

@TestPropertySource(properties = "checkout.mode=live")
class LiveModeTest {}
```

**Different literal property strings** → different `propertySourceProperties`. TestContext does not need to know whether the two settings end up altering any beans. It must create separate contexts by key to avoid inadvertently using beans bound to another configuration.

### 5.2. `@TestPropertySource(locations=...)`

```java
@TestPropertySource(
    locations = "classpath:/test-config/alpha.properties")
class AlphaConfigTest {}

@TestPropertySource(
    locations = "classpath:/test-config/beta.properties")
class BetaConfigTest {}
```

Property resource paths/descriptors participate in `propertySourceDescriptors`. Two files with identical contents but **different paths** still produce different keys. With the same descriptor, **editing the file contents between two runs in the same JVM** does not make the cache compute a new key; the key is not a hash of file contents. A test wanting a reload can use `@DirtiesContext` or structure build/test fixtures to avoid runtime mutation.

### 5.3. `@SpringBootTest(properties=...)`

```java
@SpringBootTest(
    classes = CacheDemoApplication.class,
    properties = "checkout.mode=stub")
class CheckoutStubTest {}
```

Spring Boot integrates test properties/initializers with TestContext bootstrapping; different values can change the key. In practice, **`@SpringBootTest(properties)` and `@TestPropertySource(properties)`** do not necessarily produce identical merged configurations even if `Environment` ends up with the same key/value, because their sources and customizers differ. Standardize how declarations are written across test classes that need reuse instead of assuming "same Environment" suffices for sharing.

**Note:** `application-test.yml`/`application.properties` are loaded during Boot startup; regular property sources do not automatically act as per-file key fields like "contents of all YAML files". The cache key comes from test context metadata and customizers. To have a context reflect changed property sources, run a fresh JVM, change the test configuration, or perform explicit eviction.

### 5.4. `@DynamicPropertySource` and changing values

`@DynamicPropertySource` is widely used with Testcontainers:

```java
@DynamicPropertySource
static void dbProperties(DynamicPropertyRegistry registry) {
    registry.add(
        "spring.datasource.url",
        postgres::getJdbcUrl);
}
```

This snippet assumes `postgres` is a container fixture with proper lifecycle. **The declared method** participates in `contextCustomizers`/cache key; **the value returned by the supplier** does not automatically become a separate key element each time the supplier changes. Therefore:

1. Two test classes declaring two different static dynamic property methods can produce **two context keys** even if both suppliers return the same URL.
2. One fixed method pointing to a container whose URL/port changes between tests may continue reusing the **old context** with a DataSource/beans already created from the initial URL. **Container lifecycle, context cache, and dynamic property methods** must be aligned consistently.
3. If a base class has `@DynamicPropertySource` and subclasses alter the environment outside the same method, consider `@DirtiesContext` on the class needing refresh per Spring's guidance, or avoid mutable suppliers by keeping the container stable across the suite.
4. With Spring Boot `@ServiceConnection`, Testcontainers wiring also flows through Boot test customizers; do not conclude that every port change automatically creates a new context.

Do not place a separate `@DynamicPropertySource` on every test class if they all use a single shared container with proper lifecycle; it can fragment the cache unnecessarily. Conversely, **do not share a stopped container** under the same cache key if a cached DataSource still points to the old port.

## 6. Bean overrides are part of the cache key, not just fixtures

With Spring Framework 6.2, the following annotations exist:

- **`@MockitoBean`:** replaces a bean with a Mockito mock; default strategy `REPLACE_OR_CREATE`, with `enforceOverride=true` available to require a target bean to exist.
- **`@MockitoSpyBean`:** wraps an existing bean with a spy, typically requiring a single matching candidate.
- **`@TestBean`:** replaces a bean with an object created by a test factory method, without Mockito.
- Spring Boot 3.4+ deprecated the legacy test annotations **`@MockBean`/`@SpyBean`** in favor of Spring Framework's `@MockitoBean`/`@MockitoSpyBean`, so this article uses the new API on Boot 3.5.

These overrides participate in `contextCustomizers`. Hence test classes with different overrides receive different contexts **before test methods run**.

### 6.1. With and without a mock → two context keys

```java
@SpringBootTest(classes = CacheDemoApplication.class)
class RealClientTest {
    @Autowired ExternalClient externalClient;
}

@SpringBootTest(classes = CacheDemoApplication.class)
class MockClientTest {
    @MockitoBean ExternalClient externalClient;
}
```

The second case needs a bean graph with a mock; the first needs the real client. Sharing one context between the two tests would be fundamentally wrong. The cache miss is **intentional isolation by configuration**.

### 6.2. Fallback field names can alter the key

`@MockitoBean` on a field infers the bean type to override. Without an explicit `@Qualifier`, **the field name is used as a fallback qualifier**. Is this Spring Security documentation? No: this is the policy of **Spring Framework TestContext bean overriding**. Spring recommends naming fields consistently across test classes to avoid unnecessary distinct context keys.

```java
// Test A:
@MockitoBean
ExternalClient externalClient;

// Test B:
@MockitoBean
ExternalClient paymentGateway;
```

Even if only one matching bean exists and both mock the same target by type, differing qualifier/fallback metadata can still cause a **cache key split**. This is crucial when multiple classes copy test code and rename the field for "readability", inadvertently spawning new contexts.

Stable solution when sharing mock setup is genuinely needed:

```java
@MockitoBean(
    name = "externalClient",
    enforceOverride = true)
ExternalClient externalClient;
```

Use the same **explicit bean name, type, qualifier, and mock configuration** across test classes. You can lift the override policy onto a shared meta-annotation/test base when appropriate. Do not force two tests needing **different overrides** into the same key: they must keep separate contexts for semantic correctness.

### 6.3. Why changing Mockito stubbing usually doesn't change the key

```java
when(externalClient.call()).thenReturn("MOCK-A");
// In another test method:
when(externalClient.call()).thenReturn("MOCK-B");
```

Two runtime `when(...)` calls are **not** fields in `MergedContextConfiguration`. They change the behavior of the **mock instance** stored inside the context rather than creating a new key. With Spring TestContext bean override support, `MockitoResetTestExecutionListener` normally resets mocks after or before each test according to the `MockReset` configuration; if reset is disabled, mock stubs/interactions can leak when the context is shared.

**Do not use `@DirtiesContext` just to reset Mockito stubs**: it is slow and masks test isolation issues. Prefer proper mock/lifecycle reset; keep test code independent.

### 6.4. `@MockitoSpyBean` and `@TestBean`

- A spy wraps a real bean, so it can **execute side effects** if stubbed improperly; use `Mockito.doReturn(...).when(spy)...` when you need to avoid invoking the real method.
- `@TestBean` uses a factory method, and its name/qualifier/scope and override configuration participate in the appropriate context customizer.
- Bean overriding is not the same as `spring.main.allow-bean-definition-overriding=true`. The framework's test bean override infrastructure handles it intentionally; **do not enable global bean-definition overriding** just to patch broken test config.
- With `@ContextHierarchy`, specify `contextName` on `@MockitoBean` when overriding only at one level; otherwise it may apply to multiple hierarchy levels and cause errors or fragmentation.
- Avoid mocking every dependency inside `@SpringBootTest` if you only want to test a pure Java service: a Mockito unit test without a Spring context is faster and creates no cache key.

## 7. Runnable demo: Java 17 + Spring Boot 3.5, testing cache keys via context identity

This demo does **not rely on milliseconds** and does not require a specific test method order. We create **marker test configuration classes** annotated like ordinary test classes, then use `TestContextManager` to ask Spring TestContext to load the context for each marker and compare the **exact `ApplicationContext` instances**.

This is a diagnostic/training technique to see key behavior in one test class. In real projects, you normally just put `@SpringBootTest` on each integration test class instead of invoking `TestContextManager` manually in every method. Still, this public API lets us demonstrate reuse/misses without relying on random test class execution order.

### 7.1. Directory structure

```text
context-cache-key-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/cache/
    │   ├── CacheDemoApplication.java
    │   ├── AlternativeApplication.java
    │   ├── Snapshot.java
    │   ├── ExternalClient.java
    │   └── SecondaryClient.java
    └── test/
        ├── java/com/example/cache/
        │   └── ContextCacheKeyTest.java
        └── resources/
            ├── variant-alpha.properties
            └── variant-beta.properties
```

Only **`ContextCacheKeyTest`** contains `@Test` methods. Its nested static marker classes **contain no JUnit test methods**; they only carry annotations so `TestContextManager` constructs the corresponding configuration. They are not `@Nested` JUnit tests.

### 7.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>context-cache-key-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Boot 3.5's `spring-boot-starter-test` brings in Spring TestContext, JUnit Jupiter, AssertJ, and Mockito. `@MockitoBean` belongs to package `org.springframework.test.context.bean.override.mockito` available in Spring Framework 6.2. The example needs no web server, JPA, DB, or Kafka. A minimal Spring Boot config, without enabling all auto-configurations, keeps every context small while still exposing TestContext's key attributes.

**Why not use `ApplicationContextRunner` to prove caching?** `ApplicationContextRunner.run(...)` creates and closes a context per invocation by design to test auto-configuration; it is **not Spring TestContext's static context cache mechanism**. To demonstrate keys/caching, TestContext (`@SpringBootTest`/`@SpringJUnitConfig` or `TestContextManager`) is required.

### 7.3. Root config and beans

File **`src/main/java/com/example/cache/CacheDemoApplication.java`**:

```java
package com.example.cache;

import org.springframework.boot.SpringBootConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootConfiguration
public class CacheDemoApplication {

    @Bean
    public Snapshot snapshot(Environment env) {
        return new Snapshot(
                env.getProperty("demo.value", "default"));
    }

    @Bean
    public ExternalClient externalClient() {
        return () -> "real-external";
    }

    @Bean
    public SecondaryClient secondaryClient() {
        return () -> "real-secondary";
    }
}
```

`@SpringBootConfiguration` is a Spring configuration class recognized by the Boot test bootstrapper. We omit `@EnableAutoConfiguration` and `@ComponentScan` to keep the bean graph minimal, fitting a lesson on cache keys. `Snapshot` captures the **property value at context initialization time**: if the same context is reused even when an external property supplier changes, the snapshot bean still holds the old value.

File **`src/main/java/com/example/cache/AlternativeApplication.java`**:

```java
package com.example.cache;

import org.springframework.boot.SpringBootConfiguration;
import org.springframework.context.annotation.Bean;

@SpringBootConfiguration
public class AlternativeApplication {

    @Bean
    public Snapshot snapshot() {
        return new Snapshot("alternative");
    }
}
```

Replacing configuration class `CacheDemoApplication` with `AlternativeApplication` changes `classes`, producing a different context. No change in test class name is needed to observe this.

File **`src/main/java/com/example/cache/Snapshot.java`**:

```java
package com.example.cache;

public record Snapshot(String value) {
}
```

File **`src/main/java/com/example/cache/ExternalClient.java`**:

```java
package com.example.cache;

@FunctionalInterface
public interface ExternalClient {
    String call();
}
```

File **`src/main/java/com/example/cache/SecondaryClient.java`**:

```java
package com.example.cache;

@FunctionalInterface
public interface SecondaryClient {
    String call();
}
```

Both client interfaces have real beans so `@MockitoBean(enforceOverride=true)` in tests can **replace an existing bean**. `Snapshot` reads a property to prove the context is bound to the initial value. There is no external network or real secrets.

### 7.4. Two property resources

File **`src/test/resources/variant-alpha.properties`**:

```properties
demo.value=alpha-file
```

File **`src/test/resources/variant-beta.properties`**:

```properties
demo.value=beta-file
```

Different file paths → different `propertySourceDescriptors`. This lesson does not test hashing of file contents and does not attempt to mutate files at runtime.

### 7.5. JUnit test class: comparing configurations, profiles, properties, and overrides

File **`src/test/java/com/example/cache/ContextCacheKeyTest.java`**:

```java
package com.example.cache;

import java.util.Map;

import org.junit.jupiter.api.Test;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.MapPropertySource;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.TestContext;
import org.springframework.test.context.TestContextManager;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mockingDetails;

class ContextCacheKeyTest {

    // Learning technique: create TestContext for marker classes.
    // Spring uses the SHARED static ContextCache within the JVM.
    private static ApplicationContext load(Class<?> marker) {
        return new TestContextManager(marker)
                .getTestContext()
                .getApplicationContext();
    }

    private static String snapshotValue(ApplicationContext ctx) {
        return ctx.getBean(Snapshot.class).value();
    }

    // --------- @Test methods: 18 cache-key verification scenarios ---------

    @Test
    void twoDifferentTestClassesWithSameConfigShareContext() {
        ApplicationContext a = load(BaseA.class);
        ApplicationContext b = load(BaseB.class);

        assertThat(a).isSameAs(b);
        assertThat(snapshotValue(a)).isEqualTo("default");
    }

    @Test
    void repeatedLoadOfSameMarkerHitsCache() {
        ApplicationContext a = load(BaseA.class);
        ApplicationContext again = load(BaseA.class);

        assertThat(again).isSameAs(a);
    }

    @Test
    void differentConfigurationClassesProduceDifferentContexts() {
        ApplicationContext base = load(BaseA.class);
        ApplicationContext other = load(AlternativeConfig.class);

        assertThat(base).isNotSameAs(other);
        assertThat(snapshotValue(other))
                .isEqualTo("alternative");
    }

    @Test
    void differentActiveProfilesProduceDifferentContexts() {
        ApplicationContext alpha = load(ProfileAlphaA.class);
        ApplicationContext beta = load(ProfileBeta.class);

        assertThat(alpha).isNotSameAs(beta);
        assertThat(snapshotValue(alpha)).isEqualTo("default");
        assertThat(snapshotValue(beta)).isEqualTo("default");
        // Identical bean graphs still do not make the keys identical.
    }

    @Test
    void sameActiveProfileAcrossClassesReusesContext() {
        ApplicationContext a = load(ProfileAlphaA.class);
        ApplicationContext b = load(ProfileAlphaB.class);

        assertThat(a).isSameAs(b);
    }

    @Test
    void differentInlineTestPropertiesSplitCache() {
        ApplicationContext a = load(InlineAlphaA.class);
        ApplicationContext b = load(InlineBeta.class);

        assertThat(a).isNotSameAs(b);
        assertThat(snapshotValue(a)).isEqualTo("inline-alpha");
        assertThat(snapshotValue(b)).isEqualTo("inline-beta");
    }

    @Test
    void sameInlineTestPropertiesAcrossClassesReuseContext() {
        assertThat(load(InlineAlphaA.class))
                .isSameAs(load(InlineAlphaB.class));
    }

    @Test
    void differentPropertyResourceDescriptorsSplitCache() {
        ApplicationContext a = load(FileAlphaA.class);
        ApplicationContext b = load(FileBeta.class);

        assertThat(a).isNotSameAs(b);
        assertThat(snapshotValue(a)).isEqualTo("alpha-file");
        assertThat(snapshotValue(b)).isEqualTo("beta-file");
    }

    @Test
    void samePropertyFileAcrossClassesReusesContext() {
        assertThat(load(FileAlphaA.class))
                .isSameAs(load(FileAlphaB.class));
    }

    @Test
    void springBootTestInlinePropertiesAffectKey() {
        ApplicationContext a = load(BootPropertyA.class);
        ApplicationContext b = load(BootPropertyB.class);

        assertThat(a).isNotSameAs(b);
        assertThat(snapshotValue(a)).isEqualTo("boot-a");
        assertThat(snapshotValue(b)).isEqualTo("boot-b");
    }

    @Test
    void differentInitializerClassesSplitContextKey() {
        ApplicationContext a = load(WithFirstInitializer.class);
        ApplicationContext b = load(WithSecondInitializer.class);

        assertThat(a).isNotSameAs(b);
        assertThat(snapshotValue(a)).isEqualTo("init-one");
        assertThat(snapshotValue(b)).isEqualTo("init-two");
    }

    @Test
    void differentDynamicPropertyMethodsSplitKeysEvenIfValuesSame() {
        ApplicationContext a = load(DynamicProviderA.class);
        ApplicationContext b = load(DynamicProviderB.class);

        assertThat(a).isNotSameAs(b);
        assertThat(snapshotValue(a)).isEqualTo("dynamic-same");
        assertThat(snapshotValue(b)).isEqualTo("dynamic-same");
    }

    @Test
    void mockOverrideChangesContextKeyAndBeanType() {
        ApplicationContext real = load(BaseA.class);
        ApplicationContext mocked = load(MockExternalA.class);

        assertThat(mocked).isNotSameAs(real);

        assertThat(mockingDetails(
                real.getBean(ExternalClient.class)).isMock())
                .isFalse();

        assertThat(mockingDetails(
                mocked.getBean(ExternalClient.class)).isMock())
                .isTrue();
    }

    @Test
    void identicalExplicitNamedOverridesReuseCacheAcrossClasses() {
        ApplicationContext a = load(MockExternalA.class);
        ApplicationContext b = load(MockExternalB.class);

        assertThat(a).isSameAs(b);
    }

    @Test
    void differentSetsOfMockOverridesNeedDifferentContexts() {
        ApplicationContext one = load(MockExternalA.class);
        ApplicationContext two = load(MockExternalAndSecondary.class);

        assertThat(two).isNotSameAs(one);
        assertThat(mockingDetails(
                two.getBean(ExternalClient.class)).isMock())
                .isTrue();
        assertThat(mockingDetails(
                two.getBean(SecondaryClient.class)).isMock())
                .isTrue();
    }

    @Test
    void differentFallbackMockFieldNamesCanSplitKeys() {
        ApplicationContext a = load(MockByTypeNamedAsBean.class);
        ApplicationContext b = load(MockByTypeRenamedField.class);

        assertThat(a).isNotSameAs(b);
        assertThat(mockingDetails(
                a.getBean(ExternalClient.class)).isMock()).isTrue();
        assertThat(mockingDetails(
                b.getBean(ExternalClient.class)).isMock()).isTrue();
    }

    @Test
    void samePropertyValueFromDifferentDeclarationPathsNeedNotShare() {
        ApplicationContext a = load(InlineFromTestProperty.class);
        ApplicationContext b = load(InlineFromBootTest.class);

        assertThat(snapshotValue(a)).isEqualTo("same-value");
        assertThat(snapshotValue(b)).isEqualTo("same-value");
        assertThat(a).isNotSameAs(b);
    }

    @Test
    void markingContextDirtyEvictsAndRecreatesIt() {
        TestContext tc = new TestContextManager(DirtyMarker.class)
                .getTestContext();

        ApplicationContext before = tc.getApplicationContext();

        tc.markApplicationContextDirty(
                DirtiesContext.HierarchyMode.EXHAUSTIVE);

        ApplicationContext after = tc.getApplicationContext();

        assertThat(after).isNotSameAs(before);
        assertThat(snapshotValue(after)).isEqualTo("dirty-marker");
        // @DirtiesContext has an equivalent effect when
        // Spring's TestExecutionListener processes the annotation.
    }

    // ------------ Marker classes: annotations only ------------

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    static class BaseA {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    static class BaseB {}

    @SpringBootTest(
        classes = AlternativeApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    static class AlternativeConfig {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    @ActiveProfiles("alpha")
    static class ProfileAlphaA {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    @ActiveProfiles("alpha")
    static class ProfileAlphaB {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    @ActiveProfiles("beta")
    static class ProfileBeta {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    @TestPropertySource(properties = "demo.value=inline-alpha")
    static class InlineAlphaA {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    @TestPropertySource(properties = "demo.value=inline-alpha")
    static class InlineAlphaB {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    @TestPropertySource(properties = "demo.value=inline-beta")
    static class InlineBeta {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    @TestPropertySource(
        locations = "classpath:/variant-alpha.properties")
    static class FileAlphaA {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    @TestPropertySource(
        locations = "classpath:/variant-alpha.properties")
    static class FileAlphaB {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    @TestPropertySource(
        locations = "classpath:/variant-beta.properties")
    static class FileBeta {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "demo.value=boot-a")
    static class BootPropertyA {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "demo.value=boot-b")
    static class BootPropertyB {}

    public static class FirstInitializer
            implements ApplicationContextInitializer<
                    ConfigurableApplicationContext> {

        @Override
        public void initialize(ConfigurableApplicationContext ctx) {
            ctx.getEnvironment().getPropertySources().addFirst(
                new MapPropertySource(
                    "firstInit",
                    Map.of("demo.value", "init-one")));
        }
    }

    public static class SecondInitializer
            implements ApplicationContextInitializer<
                    ConfigurableApplicationContext> {

        @Override
        public void initialize(ConfigurableApplicationContext ctx) {
            ctx.getEnvironment().getPropertySources().addFirst(
                new MapPropertySource(
                    "secondInit",
                    Map.of("demo.value", "init-two")));
        }
    }

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    @ContextConfiguration(initializers = FirstInitializer.class)
    static class WithFirstInitializer {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    @ContextConfiguration(initializers = SecondInitializer.class)
    static class WithSecondInitializer {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    static class DynamicProviderA {
        @DynamicPropertySource
        static void sameValue(DynamicPropertyRegistry registry) {
            registry.add("demo.value", () -> "dynamic-same");
        }
    }

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    static class DynamicProviderB {
        @DynamicPropertySource
        static void sameValue(DynamicPropertyRegistry registry) {
            registry.add("demo.value", () -> "dynamic-same");
        }
    }

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    static class MockExternalA {
        @MockitoBean(
            name = "externalClient", enforceOverride = true)
        ExternalClient externalClient;
    }

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    static class MockExternalB {
        @MockitoBean(
            name = "externalClient", enforceOverride = true)
        ExternalClient externalClient;
    }

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    static class MockExternalAndSecondary {
        @MockitoBean(
            name = "externalClient", enforceOverride = true)
        ExternalClient externalClient;

        @MockitoBean(
            name = "secondaryClient", enforceOverride = true)
        SecondaryClient secondaryClient;
    }

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    static class MockByTypeNamedAsBean {
        @MockitoBean
        ExternalClient externalClient;
    }

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    static class MockByTypeRenamedField {
        @MockitoBean
        ExternalClient gateway;
    }

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    @TestPropertySource(properties = "demo.value=same-value")
    static class InlineFromTestProperty {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "demo.value=same-value")
    static class InlineFromBootTest {}

    @SpringBootTest(
        classes = CacheDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
    @TestPropertySource(properties = "demo.value=dirty-marker")
    static class DirtyMarker {}
}
```

### 7.6. Explaining the evidence from the 18 JUnit tests

| Test method | Key component | Conclusion |
|---|---|---|
| `twoDifferentTestClassesWithSameConfigShareContext` | Identical merged configuration | Different class names still yield **same context instance** |
| `repeatedLoadOfSameMarkerHitsCache` | Identical key | Subsequent call reuses context |
| `differentConfigurationClassesProduceDifferentContexts` | `classes` | Different config class → different instance |
| `differentActiveProfilesProduceDifferentContexts` | `activeProfiles` | Different profile → different context even if beans match |
| `sameActiveProfileAcrossClassesReusesContext` | Equal `activeProfiles` | Context reused between two marker classes |
| `differentInlineTestPropertiesSplitCache` | `propertySourceProperties` | Different inline value → different context |
| `sameInlineTestPropertiesAcrossClassesReuseContext` | Same inline metadata | Context reused |
| `differentPropertyResourceDescriptorsSplitCache` | `propertySourceDescriptors` | Different test property file → different context |
| `samePropertyFileAcrossClassesReusesContext` | Same descriptor | Context reused |
| `springBootTestInlinePropertiesAffectKey` | Boot test properties | Different Boot test property → different context |
| `differentInitializerClassesSplitContextKey` | `contextInitializerClasses` | Different initializer class → different context |
| `differentDynamicPropertyMethodsSplitKeysEvenIfValuesSame` | `contextCustomizers` | Different source method, same value, yet different context |
| `mockOverrideChangesContextKeyAndBeanType` | `contextCustomizers` | Mock override differs from real, bean is indeed a mock |
| `identicalExplicitNamedOverridesReuseCacheAcrossClasses` | Equal override metadata | Mocked context is shared |
| `differentSetsOfMockOverridesNeedDifferentContexts` | Set of overrides | Adding second mock → different context |
| `differentFallbackMockFieldNamesCanSplitKeys` | Field fallback qualifier | Different field names can fragment cache |
| `samePropertyValueFromDifferentDeclarationPathsNeedNotShare` | Property source declaration | Same value in Environment yet different key |
| `markingContextDirtyEvictsAndRecreatesIt` | Eviction, **not a key field** | Same marker yet new context after dirty |

**The test is a technique for proving cache identity**, not relying on log strings or elapsed time. An `isSameAs` assertion directly measures `ApplicationContext` object identity, and `isNotSameAs` confirms more than one context instance exists. Cache hit/miss counters are still useful when optimizing **the entire suite**, since these are only a few marker cases.

**About `markApplicationContextDirty`:** in real tests, `@DirtiesContext` on a class/method is handled by Spring test execution listeners according to before/after modes. Calling the method directly merely demonstrates eviction inside one JUnit test without relying on method execution order. Do not mark other shared contexts dirty unless you want to increase suite cost.

### 7.7. Running Maven

Requires JDK 17+, Maven. Inside `context-cache-key-demo`:

```bash
mvn test
mvn -Dtest=ContextCacheKeyTest test
```

If Maven Wrapper is set up: `./mvnw test` or `mvnw.cmd test` on Windows.

Expected **18 `@Test` methods**, all PASS when Spring Boot 3.5/Framework 6.2/Mockito test support work properly. Each test performs comparisons within its own method so it does not depend on JUnit order. Several methods intentionally create new contexts to test keys; thus **total startup contexts in the demo exceed one**, which is completely appropriate for a training test.

The sample code has been reviewed against official APIs and semantics; **it does not claim Maven was executed while writing the lesson**. When applying to a real project, run on your JDK/CI and verify the exact Spring Framework/Boot versions, especially if using Boot 4 and `@MockitoBean` with newer test infrastructure.

## 8. Context cache vs. object cache or Testcontainers reuse

Three independent reuse layers:

| Layer | What does it reuse? | What it does NOT do automatically |
|---|---|---|
| Spring TestContext cache | **ApplicationContext + Spring singleton beans** | Does not roll back DB or reset mutable state |
| JPA/Hibernate 1st/2nd-level cache | Entities/query data per EntityManager/cache provider | Does not determine TestContext cache key |
| Testcontainers container reuse/shared fixture | Docker process/port/database service | Does not reload Spring context when container URL changes |
| HTTP client connection pool | TCP connections | Does not make `@ActiveProfiles` equal |
| Maven/Gradle build cache | Artifacts/compilation/test task outputs | Does not share JVM-static Spring context across forks |

**Common Testcontainers trap:** each test class declares its own container (dynamic port), yet expects context reuse; or conversely uses a shared `@DynamicPropertySource` method and context reuse after the container has stopped. Align **container lifecycle**, test data, dynamic prop declarations, and context reuse. Do not disable test isolation just to achieve a high hit rate.

## 9. Reading context cache stats and optimizing with evidence

### 9.1. Enabling DEBUG for the cache

Example in **`src/test/resources/application.properties`** of a real project:

```properties
logging.level.org.springframework.test.context.cache=DEBUG
```

Or an equivalent logging system configuration for the test JVM. Spring TestContext logs statistics such as:
- `size`, `maxSize`;
- `hitCount`, `missCount`;
- `parentContextCount`;
- `failureCount` depending on version/log format.

Do not assert exact log output verbatim because format, logging system, and test order can vary. The goal is to spot the **number of unique context keys**, miss growth rate, LRU evictions, and test classes creating stray configurations.

### 9.2. maxSize limit and LRU

Spring Framework 6.2 has a default maximum of **32 contexts** in the static cache, configurable via system property:

```bash
mvn test -Dspring.test.context.cache.maxSize=64
```

Set it early enough before the cache is initialized (as a system property in the JVM running the tests). LRU evicts/closes least-used contexts when capacity is exceeded; if a suite uses more than 32 context keys, **load → evict → reload** thrashing can occur. However, setting `maxSize` too high can **consume heap, threads, JDBC pools, and sockets** since every context holds resources. Eliminating unnecessary keys is usually better than merely raising size.

### 9.3. The cache exists only within one JVM process

The TestContext cache is **static in-memory**, not a distributed cache. If Maven Surefire/Gradle/IDE runs tests across **multiple forks/JVMs**, each process has its own cache. For example, `reuseForks=false` or fork-per-test-class can cause excessive context startups even with identical keys. Within one fork, tests can share; **across forks they cannot**.

When measuring performance, record:
1. number of JVM forks and test classes per fork;
2. cache hits/misses;
3. context startup time and total suite time;
4. memory/threads/external resources;
5. test isolation failures under parallel execution.

**We do not advise disabling all forks/parallelism unconditionally:** CPU-heavy or integration I/O projects may achieve better wall-clock time with multiple forks even with a lower cache hit rate. Measure according to CI profile, resources, and stability.

### 9.4. Failure threshold vs. LRU/eviction

Since Spring Framework 6.1, `spring.test.context.failure.threshold` defaults to **1**. For a **failing context key**, the framework generally stops retrying in the same JVM and reports a preemptive failure on subsequent attempts to fail fast. A higher positive integer can be configured for diagnostics, but should not be used to hide a misconfiguration.

```bash
mvn test -Dspring.test.context.failure.threshold=2
```

This is a **policy limiting failed context load retries**, not "a successful cache is reused twice". An `IllegalStateException` stating failure threshold exceeded **is not itself the root error**: find the **first** failure for that key in the logs to see which property, database, bean definition, or port caused the context to fail.

## 10. `@DirtiesContext`: use when appropriate, do not abuse

`@DirtiesContext` tells TestContext that the context **has been altered to a state no longer safe for reuse**. Spring evicts the entry from the cache according to before/after mode and hierarchy mode. The next test with an equivalent key loads a new context.

```java
@SpringBootTest
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_CLASS)
class ModifiesBeanDefinitionsTest {
}
```

This non-standalone snippet (requires imports/config) declares the test class will **dirty the context**. Only dirty if you mutate bean definitions/properties/runtime global state that cannot be safely reset. Do not use `@DirtiesContext` after every test just because test data in a `List` changed — resetting the list/data properly is far cheaper.

### What `@DirtiesContext` does NOT do

- Does not automatically delete committed data in a database.
- Does not roll back Kafka messages, cloud API calls, written files, or sent HTTP requests.
- Does not guarantee a Testcontainers container is stopped/restarted as desired.
- Does not fix races between parallel tests sharing a database.
- Does not replace access checks, network isolation, or transaction cleanup.

A new context can still use the **same external DB**; if old data remains, new tests are still affected. Proper test fixture isolation/cleanup, unique IDs, transaction boundaries, or container lifecycle management are required.

## 11. Test isolation during context reuse

A cached context means singletons can be used across multiple test methods/classes. Risks:

| Mutable component | Can leak to next test? | Typical reasonable isolation |
|---|---|---|
| Mockito stubbings/interactions | Yes if improperly reset/custom lifecycle | Mockito reset listener or deliberate reset |
| In-memory List/Map/AtomicReference bean | Yes | Reset in `@BeforeEach`/`@AfterEach` or per-test data ID |
| Committed database rows | Yes | Truncate/test transaction, fixture cleanup/unique schema |
| Redis keys | Yes | Prefix by test ID, cleanup TTL |
| Kafka messages/consumer offsets | Yes | Unique topic/group, explicit ack/cleanup |
| Clock/feature flags in singletons | Yes | Inject controlled clock, reset state |
| Thread pools/schedulers | Tasks may still be running | Await completion, proper lifecycle shutdown |
| Runtime Spring `Environment` mutation | Yes, if shared context | Avoid mutating environment between tests; separate context when needed |
| SecurityContext/MDC/ThreadLocal | Can leak via thread if not cleared | Security test listeners, explicit cleanup, executor propagation |
| HTTP mock server mappings | Yes | Reset stubs/recorded requests per test |

**Reuse does not mean lacking test independence.** A good test can share an application context and still cleanly reset business state. If `@DirtiesContext` is the only thing making tests pass, that is a signal to investigate mutable global state, test ordering, or leaked async work.

### When `@MockitoBean` reset takes effect

Spring Framework bean override support uses `MockitoResetTestExecutionListener` to reset mocks/spies before or after a test depending on configuration. It does **not** change the cache key between two methods sharing the annotation. If you use manual Mockito mocks outside the Spring context or alter reset modes, manage their lifecycle separately.

In a base test:
- keep mocked field names consistent;
- separate mandatory mocks from optional stubs;
- avoid adding a mock per test class just as a setup workaround;
- use slice tests if service/controller tests do not need the full app;
- keep explicit qualifiers when the app has multiple beans of the same interface.

**Do not alter a mock's role/qualifier just to "create a new context to be safe".** That slows the suite and usually masks missing resets.

## 12. @DynamicPropertySource + bean override: tricky case in CI

Suppose two test classes both need a Testcontainers database:

```java
abstract class PostgresIntegrationTestBase {

    @DynamicPropertySource
    static void datasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url",
                () -> sharedDatabaseJdbcUrl());
    }
}
```

This is a snippet (hypothetical helper, requires container definition). Distinguish between:

- **Test class A** uses the base dynamic method; **Test class B** also inherits that exact method. If all other metadata matches, they have a chance to share the key.
- **Test class B** declares an additional `@MockitoBean` or `@TestPropertySource` → different key even though the database URL is identical.
- **A new container per class** using the same inherited method → the context can be reused, keeping the old DataSource. Do not design container lifecycle against cache lifecycle.
- **Test A** invokes `@DirtiesContext` → entry evicted, class B may have to re-initialize the context even with the same key.
- **A new Maven Surefire fork** → fresh static cache; even with the same key, objects are not shared across processes.

If you want to test a different connection string, give the context an **actually different configuration** or explicitly dirty/recreate it; do not expect a runtime supplier value to accidentally create a new key. With Boot's `@ServiceConnection`, check connection details customization and lifecycle similarly.

## 13. Checklist for optimizing performance based on cache keys

- [ ] I know the context cache lives in **Spring TestContext**, not `ApplicationContextRunner`.
- [ ] I have reviewed all `MergedContextConfiguration` components: locations, classes, initializers, customizers, loader, parent, profiles, property descriptors/properties, resourceBasePath.
- [ ] Test class name alone **is not a cache key field**; annotations/config decide.
- [ ] Integration tests intended for reuse share the same **configuration classes** or Boot bootstrap setup.
- [ ] Profiles are unified when environments are genuinely identical; no pointless per-test profiles.
- [ ] `@TestPropertySource` inline/file paths are not split into unnecessary variants.
- [ ] `@SpringBootTest(properties)` is declared consistently across classes.
- [ ] `@DynamicPropertySource` methods and resource lifecycles are stable, not just having the same supplier value at one point.
- [ ] Bean overrides serving the same purpose use consistent `@MockitoBean` field name, type, qualifier, explicit name, and mock config.
- [ ] Test classes needing real bean vs. mock bean have **properly separated keys**.
- [ ] Mock stubbings are reset at the right lifecycle phase without needlessly dirtying the context.
- [ ] Test data/DB/Redis/Kafka/async work is isolated independently of the cached context.
- [ ] `@DirtiesContext` is used only when the context genuinely cannot be safely reused.
- [ ] I measure hits/misses via `org.springframework.test.context.cache=DEBUG` rather than inferring from a single millisecond reading.
- [ ] I check `spring.test.context.cache.maxSize`, LRU, and heap/resource costs.
- [ ] I remember the cache is shared **only within the same JVM**, not across test forks.
- [ ] I look for the **first startup error** when encountering context failure threshold exceeded.
- [ ] For `@WebMvcTest`/`@DataJpaTest`/`@SpringBootTest`, I do not assume test slices all share a context.
- [ ] Tests outside the framework (plain Mockito, JUnit unit tests) omit the Spring context when unnecessary.
- [ ] I do not "optimize" by removing annotations that construct a required bean graph.
- [ ] With real external resources, fixture lifecycle and caching are compatible.
- [ ] I run `mvn test`/CI with the expected test forks/profile/JVM options.

**Conclusion:** The Spring context cache distinguishes entries by **merged configuration**, especially four groups to remember: **classes/configuration, active profiles, test properties, and context customizers containing bean overrides/dynamic properties**. Two differently named tests can share, and two tests both using `@SpringBootTest` can miss. Performance optimization is not about erasing all differences: **standardize only configurations that are genuinely equivalent**, while keeping each test independent in data and side effects. Use cache stats + context identity as proof instead of guessing.

### Official Documentation

- [Spring Framework 6.2 — Context Caching](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html)
- [Spring Framework 6.2 — @MockitoBean and @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html)
- [Spring Framework 6.2 — Bean Overriding in Tests](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/bean-overriding.html)
- [Spring Framework 6.2 — @TestPropertySource](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-testpropertysource.html)
- [Spring Framework 6.2 — @DynamicPropertySource](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-dynamicpropertysource.html)
- [Spring Framework 6.2 — Context Failure Threshold](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/failure-threshold.html)
- [Spring Framework 6.2 — MergedContextConfiguration Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/test/context/MergedContextConfiguration.html)
- [Spring Framework 6.2 — TestContextManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/test/context/TestContextManager.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
