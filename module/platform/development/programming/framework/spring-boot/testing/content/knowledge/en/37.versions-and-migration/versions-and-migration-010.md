# AOT, Native Testing, and Supported Annotation Scope

## 1. Why Do JVM Tests Pass While GraalVM Native Tests Fail?

In the **Spring Boot - testing** module, **Versions and Migration** group, this lesson explains what actually happens when moving from JVM integration tests to **Spring AOT** and **GraalVM Native Image tests**. A `@SpringBootTest` that passes on the JVM can fail during `processTestAot`, `nativeCompile`, or `nativeTest`, even with identical business assertions.

The fundamental reason: on the JVM, Spring can scan the classpath, infer the bean graph, load resources, and use reflection/dynamic proxies at runtime. With AOT (ahead-of-time), Spring **analyzes and processes the `ApplicationContext` before runtime**, generating code and metadata for GraalVM; decisions around bean definitions, profiles, and conditions are locked in at build time. GraalVM Native Image operates under a closed-world assumption, so reflection, resource lookups, dynamic proxies, JNI, serialization, and initialization must be known to the native compiler ahead of time.

This is not simply a `@Test` issue. Distinguish six stages:

1. **JUnit test on the JVM**: code and the Spring context run normally; no native image is needed.
2. **Application Spring AOT processing**: prepares the bean graph and generates source/metadata for the production application.
3. **Spring TestContext AOT processing**: discovers test configurations, processes each required context, and generates test context initializers.
4. **AOT-enabled JVM runtime**: runs the application with generated artifacts using `-Dspring.aot.enabled=true`; still runs on the JVM and does not prove native compiler readiness.
5. **Native application executable**: GraalVM compiles the main program into a native binary.
6. **Native test executable**: GraalVM compiles the JUnit engine + test classes + AOT-processed Spring test contexts into a binary to execute tests.

**A JVM PASS does not automatically imply a native PASS.** Conversely, a native build failing during build-time AOT analysis is not yet a JUnit assertion failure. This lesson builds a clear classification of annotations and test styles: those supported within clear bounds, those requiring runtime hints or provider checks, and those unsupported in the version stack examined.

Consistent stack throughout: **Java 17, Spring Boot 3.3.0, Spring Framework 6.1, JUnit Jupiter 5, Gradle 8.x, and GraalVM Native Build Tools Gradle plugin 0.10.1**. This is a **deliberately pinned historical stack** for understanding migration; newer versions may alter annotation, Mockito, or Native Image characteristics. Do not assume APIs from Spring 6.2, 7.0, or Boot 4.x exist in Boot 3.3.

## 2. Learning Outcomes

After this lesson, you can:

- Distinguish `AOT processing` from `GraalVM native-image compilation` and native test execution.
- Explain the roles of `processAot`, `processTestAot`, `nativeCompile`, and `nativeTest`.
- Use `@SpringBootTest` or Spring Boot test slices within appropriate scope where native testing supports them.
- Understand that a JUnit Platform `TestEngine` is still required to execute test classes inside the native test image.
- Know that Spring TestContext AOT processes **each distinct `ApplicationContext` by configuration**, not once per test method.
- Distinguish `@DisabledInAotMode` (Spring) from `@DisabledInNativeImage`/`@EnabledInNativeImage` (JUnit Jupiter).
- Know that `@ContextHierarchy` is unsupported in Spring TestContext AOT mode on the studied stack.
- Recognize that `@ActiveProfiles`, `@TestPropertySource`, `@Import`, and `@TestConfiguration` affect configuration **at build time**, not runtime hot reconfiguration.
- Understand that `@DynamicPropertySource` can supply runtime-derived values, yet must not be relied upon to alter bean graphs/conditions already frozen at AOT build time.
- Identify risks with `@MockBean`/`@SpyBean` and Mockito in native tests depending on toolchain/version; never assume automatic JVM-equivalent support.
- Understand how `@DirtiesContext`, `@Transactional`, and `@Sql` behave and that they do not automatically confer native capability to third-party libraries.
- Use `@RegisterReflectionForBinding` and `@ImportRuntimeHints` to supply reflection/resource metadata when Spring does not infer it automatically.
- Know that a custom `ContextLoader` must implement `AotContextLoader` and a custom `TestExecutionListener` must implement `AotTestExecutionListener` to participate in AOT processing.
- Verify context-specific build-time property values and profile activation.
- Write native-friendly tests using real services or test fakes instead of complex mocking frameworks.
- Establish a workflow running JVM tests first, then `processTestAot`, and finally `nativeTest` on a compatible GraalVM installation.
- Distinguish compilation/runtime errors from test assertion failures and "no tests discovered".
- Keep reflection/resource hints minimal rather than registering every class unconditionally.
- Design CI to run JVM tests frequently and native smoke/integration tests on a schedule or change-triggered cadence aligned with build cost.
- Evaluate support matrices across **framework + Boot + test engine + third-party libraries + OS/GraalVM**, rather than by annotation name alone.

## 3. End-to-End AOT Test Diagram

```text
                 Source code + test classes
                            |
                     Java compilation
                            |
              +-------------+---------------+
              |                             |
              v                             v
        JVM Gradle test               processTestAot
              |                             |
        Jupiter engine               Find TestContext tests
        loads Spring                 Group unique contexts
        by reflection                Analyze bean graphs
              |                     Generate initializers
              v                     Register runtime hints
        Assertions/report                     |
                                            v
                                     native-image compiler
                                            |
                                  JUnit engine + test code
                                  + generated AOT assets
                                  + reachable classes
                                            |
                                            v
                                       nativeTest
                                            |
                                  Native test executable
                                            |
                                  Assertions + test report
```

The Spring Boot Gradle plugin coordinates with GraalVM Native Build Tools to configure these tasks. For native tests, integration normally runs both `processAot` **and** `processTestAot` before compiling the test binary. Manually building an executable from `javac` is not equivalent to Spring TestContext native testing.

### 3.1. AOT Processing Is Not a Native Binary

`processTestAot` generates code and metadata, yet it **does not** execute test assertions inside a native executable. It can PASS even when native compilation later fails due to reflection in a third-party library, or it can fail immediately if a test context cannot be AOT-processed.

### 3.2. A Native Binary Is Not Just a JVM With Another Flag

GraalVM Native Image compiles a closed-world executable. Many dynamic features are unavailable compared to standard JVM classpath scanning and reflection. Do not try to fix failures by arbitrarily "switching JDK vendors"; identify missing hints, library incompatibilities, build-time properties, or environment issues.

### 3.3. AOT Runtime on the JVM Is Only One Verification Column

`spring.aot.enabled=true` requires generated artifacts in the application JAR or runtime classpath; it helps catch issues in generated code without proving native-image reflection/resource/proxy metadata is complete. By default, the JVM ignores generated AOT assets unless that flag is set.

## 4. Version Boundary: Spring Boot 3.3, Spring Framework 6.1, and JUnit

| Component | Stack in This Lesson | Meaning |
| --- | --- | --- |
| JDK source/bytecode | Java 17 | API & language target |
| Spring Boot | 3.3.0 | Boot tests, auto-configuration, Gradle AOT |
| Spring Framework | 6.1.x managed by Boot BOM | TestContext AOT, `@DisabledInAotMode` |
| JUnit | Jupiter 5.x managed by Boot BOM | Test methods, native-image conditions |
| Gradle | 8.x, e.g., 8.7 | `test`, `nativeTest` build integration |
| GraalVM Native Build Tools | Gradle plugin 0.10.1 | Native compiler tasks |
| GraalVM JDK | A GraalVM build with `native-image` matching Java target | Compile/run native binaries |
| Legacy Spring Native | **Not used** | Do not mix Boot 2.x/experimental APIs |

**Do not hardcode JUnit library versions out of sync with the Boot BOM** without clear justification; native builds are very sensitive to runtime engine and platform versions. Inspect actual dependency resolution on `NoClassDefFoundError` or missing `TestEngine` errors.

### 4.1. Do Not Copy Boot 4.x Examples Into Boot 3.3

Spring Boot 3.4+ moves away from `@MockBean`/`@SpyBean`, Spring Framework 6.2+ adds `@MockitoBean`/`@MockitoSpyBean`, and Spring Framework 7.x brings further AOT/JPA changes. This lesson never pretends later APIs exist in Boot 3.3. If you upgrade versions, re-verify the full annotation matrix.

### 4.2. GraalVM Must Include `native-image`

Verify with:

```bash
java -version
native-image --version
./gradlew --version
```

`java -version` showing a JDK does not mean the `native-image` executable is installed. Depending on the GraalVM distribution, the compiler may be bundled or require separate installation; verify alignment between your Java target and GraalVM Native Build Tools. Native compilation also requires OS toolchain dependencies (C/C++ linker/libraries) per GraalVM documentation.

## 5. What Spring TestContext AOT Actually Does

The Spring TestContext Framework provides AOT support for integration tests loading an `ApplicationContext`. At build time, it:

1. Discovers relevant test classes/suites via the test classpath and registered JUnit Platform engines.
2. Computes the context configurations required by those test classes.
3. Invokes the Spring AOT engine to process each expected **unique `ApplicationContext`**.
4. Generates `ApplicationContextInitializer` code, bean registration logic, and metadata/hints.
5. Writes the mapping between test classes and generated context initializers.
6. GraalVM Native Build Tools consumes these assets when building the native test executable.
7. At native runtime, Spring TestContext loads the AOT-processed context and still participates in context caching.

Annotations are not freely "re-interpreted dynamically at runtime like on the JVM". The bean graph is generated in a build-time context; code expecting runtime profile/condition changes to swap bean definitions contradicts AOT assumptions.

### 5.1. The Cache Key Still Applies

Two test classes with equivalent configurations share the generated context and context cache in the native test runtime. Mutable singleton state can still leak across methods/classes; AOT **does not** create a fresh context per test method.

### 5.2. Multiple Test Profiles Generate Multiple Contexts

`@ActiveProfiles("test")` and `@ActiveProfiles("integration")` produce two distinct test contexts and AOT-generated initializers. Multiplying contexts makes native builds heavier and slows down AOT processing. Do not merge unrelated contexts recklessly if doing so compromises test fidelity.

### 5.3. Build-Time AOT Errors Can Differ From Runtime

For example, a `@Configuration` bean might depend on a profile/property supplied only **when running the native test executable**, even though the AOT processor had to decide whether the bean exists **earlier at build time**. The build can fail or produce an unexpected bean graph. Keep build-time AOT environments aligned rather than relying solely on runtime system properties.

## 6. Annotation Support Table: The Short Answer

Distinguish **"Spring TestContext recognizes the annotation"** from **"every library/behavior executes in a GraalVM native binary"**. The table below covers Spring Boot 3.3 / Spring Framework 6.1:

| Annotation / Feature | Classification | What to Verify |
| --- | --- | --- |
| `@SpringBootTest` | **Supported for AOT/native tests** | App bean graph and dependencies are native-compatible |
| `@WebMvcTest`, `@DataJpaTest`, Boot test slices | **Supported by Boot per slice model** | Hints for controllers/serializers/JPA/providers and scoped beans |
| JUnit Jupiter `@Test`, `@ParameterizedTest`, `@Nested` | **Supported by JUnit engine** | Engine discovery, params/resources, and native build plugin |
| `@ContextConfiguration`, `@Import`, `@TestConfiguration` | **Supported for static configuration** | Custom loaders and graphs must be AOT-processable |
| `@ActiveProfiles`, `@TestPropertySource` | **Supported; bean graph logic resolved at build time** | Build-time profile/property selection |
| `@DynamicPropertySource` | **Supported mechanism, timing-sensitive** | Dynamic endpoints, container lifecycles, conditions/bean graphs |
| `@Autowired` / `@Resource` in test class | **Usable within version constraints** | Bean types, lifecycle, and native hints |
| `@Transactional`, `@Sql` | **Usable in TestContext conditionally** | Transaction manager, schema/resources, runtime hints |
| `@DirtiesContext` | **TestContext semantics apply** | Native context reload overhead, external data cleanup |
| `@RegisterReflectionForBinding`, `@ImportRuntimeHints` | **Mechanisms to register AOT hints** | Reflection/resources/proxies adequately described |
| `@DisabledInAotMode` | **Exact Spring 6.1 annotation** | Class/method scope and shared-context rules |
| `@DisabledInNativeImage` / `@EnabledInNativeImage` | **JUnit native runtime condition** | Conditional execution inside native executable only |
| `@ContextHierarchy` | **Unsupported in TestContext AOT mode** | Must redesign context composition |
| Boot 3.3 `@MockBean` / `@SpyBean` | **Caution: Mockito/native limitations** | Do not assume JVM parity; consider test/fake strategies |
| Test class `@PersistenceContext` / `@PersistenceUnit` injection | **Check AOT version; avoid relying on it in 6.1 native tests** | Prefer `@Autowired` Spring repositories/services |
| Custom `ContextLoader` | **Conditional** | Must implement `AotContextLoader` to join AOT processing |
| Custom `TestExecutionListener` | **Conditional** | Implement `AotTestExecutionListener` when contributing at AOT time |
| JUnit 4 tests | **Platform/engine configuration-dependent** | Vintage engine/runtime and native compatibility; not `@RunWith` alone |
| TestNG and other engines | **Toolchain/engine-dependent** | Requires a JUnit Platform `TestEngine` registered for the native build |

"Supported" in this table **does not guarantee every combination of Boot starters, databases, mocks, Testcontainers, tracing agents, and plugins works out of the box**. With native tests, running the integration test inside the compiled binary is the final proof.

## 7. `@SpringBootTest` in Native Tests

A test such as:

```java
@SpringBootTest(
        classes = AotLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class AotIntegrationTest {
    @Autowired GreetingService greetings;

    @Test
    void contextLoadsAndGreetWorks() {
        assertEquals(
                "Hello, Ada",
                greetings.greet("Ada"));
    }
}
```

This is an abbreviated snippet; the full runnable source appears in Section 19. Spring Boot/Spring Framework can process `@SpringBootTest` through TestContext AOT. Inside the native executable, test methods still run via JUnit Jupiter while the `ApplicationContext` uses generated initialization assets.

**This does not mean** every application bean is automatically native-compatible: an SDK using arbitrary reflection, dynamic classpath scanning, JNI, or unhinted resources can still break the native image.

### 7.1. Test Slices

`@WebMvcTest`, `@DataJpaTest`, `@JsonTest`, and other slices shrink the set of loaded beans. Native image testing can use test slices, provided each slice has its required dependencies and hints. For instance:

- `@WebMvcTest` with Jackson/validation/security requires checking controller request/response types and filters.
- `@DataJpaTest` requires a native-compatible ORM/database driver, entity metadata, and JPA support.
- `@JsonTest` requires serializer/deserializer/record binding hints when the engine cannot infer them.
- Slices do not start a full embedded server; native test tasks do not expand slice scope.

**Never combine two test slices arbitrarily.** If full integration is needed, use `@SpringBootTest`; if partial context is needed, respect the single slice contract.

## 8. `@ContextConfiguration`, `@TestConfiguration`, and `@Import`

When context composition is static and deterministic, Spring AOT can analyze it at build time:

```java
@TestConfiguration(proxyBeanMethods = false)
class TestClockConfig {
    @Bean
    Clock fixedClock() {
        return Clock.fixed(
                Instant.parse("2026-11-08T00:00:00Z"),
                ZoneOffset.UTC);
    }
}
```

This is an illustrative snippet requiring imports. `@Import(TestClockConfig.class)` on the test exposes the test config's bean definitions to the AOT processor.

A common mistake is **adding or removing beans at runtime after AOT generated code has fixed the bean graph** and expecting Spring to re-run classpath scanning or `@Conditional` evaluation like on the JVM. With AOT, bean graph selection must be coherent at build time.

### 8.1. `@ContextConfiguration` Custom Loaders

If a project uses `@ContextConfiguration(loader=SomeLoader.class)` with a custom loader, JVM execution alone is not enough. To participate in AOT processing, the custom loader must implement `AotContextLoader`. Default loaders provided by Spring Framework and Spring Boot already implement it; custom ones must be checked against the SPI.

### 8.2. `ApplicationContextInitializer`

`ApplicationContextInitializer` modifies a context before refresh. However, a runtime initializer must not arbitrarily introduce new beans or definitions that AOT never processed. For custom AOT contributions, use Spring AOT extensions and hint registration rather than runtime scanning tricks.

### 8.3. `TestExecutionListener`

Spring TestContext `@TestExecutionListeners` still drives test lifecycle callbacks. A custom listener that must execute work at AOT build time needs `AotTestExecutionListener`. Otherwise, it may act only as a runtime test listener where supported without contributing AOT hints or registrations.

## 9. `@ActiveProfiles`, `@TestPropertySource`, and Bean Graph Selection

Consider:

```java
@Profile("test")
@Configuration
class TestOnlyBeans {
    @Bean
    PaymentClient paymentClient() {
        return new FakePaymentClient();
    }
}
```

This is an illustrative snippet; interfaces/classes are undeclared. With Spring AOT, whether `TestOnlyBeans` exists is decided from profiles and conditions during build-time AOT processing. Building an image under the `"test"` profile and switching to `"production"` at runtime to swap the entire bean graph does not behave like dynamic JVM configuration.

### 9.1. Do Not Treat Profiles as Runtime Bean-Definition Feature Toggles

Keep clear:

- `@ActiveProfiles("native-test")` on a test class informs the AOT processor of that test's context configuration.
- `@TestPropertySource(properties="feature.useMock=true")` can evaluate bean definition conditions at build time.
- Flipping `feature.useMock` once the native test executable is compiled **does not force AOT to regenerate the graph**.
- Runtime properties read as **values** by existing beans can still be dynamic depending on the binding mechanism, whereas properties controlling **whether beans exist** must align at build time.

### 9.2. Do Not Claim Every Property Is Frozen

AOT does not make every `Environment.getProperty(...)` a compile-time constant. Distinguish properties evaluated for `@Conditional`/`@Profile`/BeanFactory conditions from properties read by existing beans at runtime. Verify each case against actual wiring and code.

### 9.3. Common Sources of Configuration Mismatch

- Gradle daemon JVM vs. Gradle test JVM.
- `processTestAot` is a build-time `JavaExec` task with its own environment and system properties.
- The native test executable runs in its own runtime process environment.
- Docker/CI secrets injected at runtime are absent during AOT build time.
- `application-test.yml` sits on the classpath while its profile is not actually active.
- Testcontainers dynamic mapped ports are only known when containers start at runtime.

Log sanitized build-time profile/property keys alongside runtime environment settings without printing credentials.

## 10. `@DynamicPropertySource`, Testcontainers, and Native AOT

`@DynamicPropertySource` is the Spring TestContext API for dynamic property suppliers (often Testcontainers host/port values). Example:

```java
@DynamicPropertySource
static void register(DynamicPropertyRegistry registry) {
    registry.add("service.endpoint",
            container::getServiceEndpoint);
}
```

**This is an illustrative snippet** with `container`/methods undeclared. It does **not** mean Spring knows the mapped port at build time.

With AOT, verify:

1. Is the dynamic value an **endpoint/credential for an existing bean** or does it toggle bean definitions?
2. Is Testcontainers starting during build-time analysis or only at native test runtime?
3. Is the context cached/reused after an earlier container already stopped?
4. Are runtime hints for drivers, SDKs, and serialization complete?
5. Can the native test binary communicate with the Docker network/host architecture?

### 10.1. Do Not Confuse Dynamic Values With Dynamic Bean Graphs

If a `BeanFactory` condition uses a runtime-only value to pick a bean class, AOT may have generated a different graph. Avoid designing native tests that alter bean definitions based on mapped ports; use stable bean types and inject endpoints at the proper phase where supported.

### 10.2. `@ServiceConnection`

Spring Boot Testcontainers integration includes `@ServiceConnection` to supply connection details from containers. It does not make every third-party driver native-compatible or ensure Docker availability on `nativeTest` CI runners. Proper Boot 3.3 dependencies and runtime hooks are still required.

### 10.3. Do Not Use `@DirtiesContext` as a Universal Fix

`@DirtiesContext` forces Spring context reloads at test runtime, yet it cannot alter the AOT-generated bean graph or add missing native metadata. Nor does it clean up external databases, topics, or Redis keys. Use it only when context state truly cannot be reset, and validate with the native toolchain.

## 11. `@DisabledInAotMode`: Spring 6.1's Mechanism

`@DisabledInAotMode` lives in:

```java
import org.springframework.test.context.aot.DisabledInAotMode;
```

It tells TestContext that the annotated test class **should not be AOT-processed**; under JUnit Jupiter, the corresponding test class or method is disabled in Spring AOT runtime mode.

Method-level example:

```java
@Test
@DisabledInAotMode
void requiresOrdinaryJvmSpringMode() {
    assertFalse(
            AotDetector.useGeneratedArtifacts());
}
```

This is an illustrative snippet; the runnable example in Section 19 provides complete imports. It **runs on the ordinary JVM** yet is skipped when Spring AOT generated artifacts are active. At method level, the enclosing class's context can still be AOT-processed because other methods in the class need it.

### 11.1. Class-Level Affects Build Time

```java
@DisabledInAotMode
@SpringBootTest
class LegacyJvmOnlyIntegrationTest {
    @Test
    void usesUnsupportedRuntimeFeature() {
        // JVM-only coverage.
    }
}
```

This is a snippet. Spring TestContext skips AOT optimization for this test class's context. **Critical rule:** if other test classes share **the exact same `ApplicationContext` configuration**, every class sharing that context must also carry `@DisabledInAotMode`; otherwise build/runtime exceptions can occur. Never annotate just one class in a shared-context group while leaving the others unmarked.

### 11.2. Never Disable the Whole Native Suite Just to Turn Builds Green

Native testing exists to surface incompatibilities. Use `@DisabledInAotMode` **sparingly with a clear reason**, document the coverage gap/migration task, and keep the JVM test running. If critical areas like security, serialization, or database behavior only have JVM tests skipped in native mode, write native-safe replacement tests.

### 11.3. Method-Level vs. Class-Level

- Method-level: skips that method during Spring AOT runs; remaining methods in the class can still be processed and executed.
- Class-level: skips the entire test class and excludes its distinct context from AOT processing.
- For **shared context configurations**, class-level exclusion must be applied consistently across all classes sharing that context.

## 12. `@DisabledInNativeImage` and `@EnabledInNativeImage` Are JUnit Conditions

JUnit Jupiter provides:

```java
import org.junit.jupiter.api.condition.DisabledInNativeImage;
import org.junit.jupiter.api.condition.EnabledInNativeImage;
```

Examples:

```java
@Test
@DisabledInNativeImage
void usesOnlyJvmInstrumentation() {
    // Runs on an ordinary JVM, not native executable.
}

@Test
@EnabledInNativeImage
void onlyVerifyNativeBehavior() {
    // Runs only within a GraalVM native image.
}
```

**Core distinction:** these annotations are **JUnit native runtime conditions**, not directives telling Spring TestContext to exclude an `ApplicationContext` from build-time AOT processing. For a Spring context that cannot be AOT-processed, putting `@DisabledInNativeImage` on a test method will not prevent `processTestAot` from failing. Use `@DisabledInAotMode` when you need to control AOT processing.

### 12.1. Comparison Table

| Annotation | Ordinary JVM | JVM With Spring AOT Artifacts | GraalVM Native Test | Excludes Context From Build-Time AOT? |
| --- | --- | --- | --- | --- |
| No skip annotation | Runs | Runs | Runs, if compatible | No |
| `@DisabledInAotMode` (method) | Runs | Skipped | Skipped | Does not exclude whole context |
| `@DisabledInAotMode` (class) | Runs | Skipped | Skipped | **Yes**, subject to shared-context rule |
| `@DisabledInNativeImage` | Runs | Runs, if still on JVM | Skipped | **No** |
| `@EnabledInNativeImage` | Skipped | Skipped if on JVM | Runs | **No** |

When excluding pure Java behavior that only works on the JVM, method-level conditions may suffice. When preventing Spring AOT from processing an incompatible context, Spring's **class-level** annotation and shared-context consistency are what matter.

### 12.2. `@Disabled` Does Not Fix Broken Generated Code

If a native image fails to compile due to reachability or hint issues in a production bean, marking a JUnit method `@Disabled` does not give Spring runtime hints for that bean. Fix the root build issue. Never treat skipped tests as evidence of native coverage.

## 13. `@ContextHierarchy`: An Official Limitation

Spring Framework TestContext AOT **does not support `@ContextHierarchy`** in the studied version. This is a documented limitation, not something fixed by adding `@Import`. A test relying on a parent-child `ApplicationContext` hierarchy can pass on the JVM yet is ineligible for AOT/native execution.

Example (**do not place in the runnable project**):

```java
@ContextHierarchy({
    @ContextConfiguration(classes = ParentConfig.class),
    @ContextConfiguration(classes = ChildConfig.class)
})
class LegacyHierarchyTest {
    // ...
}
```

How to handle it:

1. Keep this test on the JVM; mark it with class-level `@DisabledInAotMode` if it breaks AOT processing.
2. Design a **flat test context** for behavior needing native coverage using explicit `@Import`/`@ContextConfiguration`.
3. If production uses a hierarchy, keep the JVM test to protect that behavior while native smoke/integration tests validate a compatible `ApplicationContext`.
4. Never silently delete a parent context without checking injection, bean overrides, and security behavior.
5. Never claim replacing `@ContextHierarchy` with another annotation is semantically identical.

## 14. Mockito `@MockBean`/`@SpyBean`: Caution in Native Mode

In Spring Boot **3.3**, `@MockBean`/`@SpyBean` come from Boot test support and rely on Mockito. On the JVM they are standard; however, generating mocks/spies relies on dynamic proxies, bytecode generation, and inline mocking that differ in Native Image. Spring Boot GraalVM guidance documents **Mockito/native test limitations**. Never construct a table claiming "`@MockBean` works in all native tests" without verifying your exact version and provider.

### 14.1. Native-Friendly Test Example

Instead of relying on a mocking framework to generate dynamic implementations, define a **static test fake bean**:

```java
public interface PriceGateway {
    int price(String sku);
}

public final class FixedPriceGateway
        implements PriceGateway {

    @Override
    public int price(String sku) {
        return 50;
    }
}

@TestConfiguration(proxyBeanMethods = false)
class FakeGatewayConfig {
    @Bean
    @Primary
    PriceGateway fakePriceGateway() {
        return new FixedPriceGateway();
    }
}
```

This is a **design snippet**, not part of the runnable lab; production code must provide full interfaces/gateway beans for clean overrides. Static test fakes are easier to AOT-process than bytecode-generated Mockito mocks, provided you verify they do not distort the test goal.

### 14.2. Do Not Delete Mockito Tests From the JVM Regression Suite

Mock-based tests remain valuable on the JVM. Separate native smoke tests for paths needing native verification while keeping interaction assertions in the JVM unit suite. Native PASS does not require re-running 100% of Mockito-heavy tests in native mode if the toolchain lacks full support.

### 14.3. Note When Upgrading to Newer Boot

Spring Framework 6.2+ introduces `@MockitoBean`/`@MockitoSpyBean` and Boot 3.4+ deprecates legacy `@MockBean`. These **do not exist in Boot 3.3**. Never copy a snippet using a future annotation and blame AOT for the compiler failure.

## 15. `@Autowired`, JPA Injection, and Test-Only Dependencies

Spring TestContext native tests support injecting Spring-managed beans from the AOT-generated context. The approach least coupled to internals is injecting services or repositories:

```java
@SpringBootTest
class RepositoryBehaviorTest {
    @Autowired OrderRepository orders;

    @Test
    void savesOrder() {
        // Exercise repository through Spring.
    }
}
```

This snippet is not runnable because `OrderRepository` is undeclared. For JPA, verify which injection annotations your Spring Framework version supports directly on the **test instance**. In particular, do not assume `@PersistenceContext`/`@PersistenceUnit` on test fields behaves identically in Framework 6.1 AOT mode; several improvements arrived in Framework 7.x.

**Misconception to avoid:** claiming "JPA does not work in native tests" is false. A limitation on test-instance injection annotations does not mean Hibernate/JPA providers cannot compile to native images. Check provider/version notes and test via repository or `EntityManager` pathways appropriately.

### 15.1. `@Transactional`

`@Transactional` on a test-managed transaction retains Spring TestContext rollback semantics where supported. In native tests, the transaction manager, datasource, DB driver, and external database must still work properly; AOT does not conjure a missing transaction manager.

### 15.2. `@Sql`

`@Sql` executes SQL setup/cleanup scripts from the test classpath, provided native resource inclusion is configured; if the script is missing from the native executable, the test fails even with valid SQL. Register resource hints when needed. Never use `@Sql` to fix an AOT-generated bean graph or assume it cleans up external databases across unrelated tests.

### 15.3. `@DirtiesContext`

`@DirtiesContext` closes and evicts the Spring TestContext at runtime; it does not reset external databases. A native test executable still holds its AOT-generated context: "reloading the context" does not mean "re-scanning all classes and bean conditions like JVM dynamic startup".

## 16. Runtime Hints: Reflection, Resources, Proxies, Serialization

GraalVM closed-world analysis requires advance notice of dynamic operations it cannot deduce statically. Spring AOT generates many hints automatically from bean definitions, configuration properties, and Spring infrastructure, yet cannot guarantee coverage for custom libraries.

Common hint categories:

| Hint Type | Symptom When Missing | Fix Direction |
| --- | --- | --- |
| Reflection | Constructors/methods/records inaccessible | `@RegisterReflectionForBinding` or `RuntimeHintsRegistrar` |
| Classpath resource | `getResourceAsStream` returns null | `resources().registerPattern(...)` |
| JDK dynamic proxy | Interface proxy fails to create | `RuntimeHints.proxies()` / framework hints |
| Serialization | DTO/serializer lacks runtime metadata | Appropriate binding/serialization hints |
| JNI | Native library/call unsupported | Native Image JNI metadata/provider |
| Resource bundle | i18n/messages missing | Bundle hints |
| Third-party driver | SDK initialization fails | Native reachability metadata, version upgrade, library hints |

**Never enable reflection across the entire classpath** just to make one test pass. Overly broad hints bloat binary size and attack surface and hurt maintainability. Register only the specific classes, constructors, fields, and resource patterns actually needed.

### 16.1. `@RegisterReflectionForBinding`

Spring Framework provides:

```java
@RegisterReflectionForBinding(TicketPayload.class)
class AotIntegrationTest {
    // ...
}
```

This Spring annotation registers runtime reflection hints for constructors, properties, records, and related binding types. It fits when tests use Jackson/data binding on a DTO that Spring AOT does not infer automatically.

### 16.2. `@ImportRuntimeHints`

```java
@ImportRuntimeHints(TestResourceHints.class)
class AotIntegrationTest {
    // ...
}
```

`TestResourceHints` implements `RuntimeHintsRegistrar` and can register resources under `src/test/resources`. Unlike binding annotations targeting DTOs, this works well for resource paths or explicit reflection/proxy types that cannot be inferred.

### 16.3. `RuntimeHintsRegistrar` vs. `TestRuntimeHintsRegistrar`

- Spring Core's `RuntimeHintsRegistrar` registers hints scoped to a component/context via `@ImportRuntimeHints`.
- Spring TestContext's `TestRuntimeHintsRegistrar` registers global hints specific to test infrastructure via `META-INF/spring/aot.factories`.
- If hints are reusable across production and tests, prefer Core `RuntimeHintsRegistrar` over the global test-only SPI.
- Never write redundant registrars if Spring AOT already infers the hints accurately; duplicate hints do not make tests safer.

### 16.4. Hints Are Not Executable Coverage

`processTestAot` or registering a type can PASS while the native test still fails at runtime due to a missing resource, an unsupported native driver, or a business assertion. Always run `nativeTest` and inspect real reports.

## 17. Designing the Hands-On Example

The project includes:

- `AotLabApplication`: minimal Boot application.
- `GreetingProperties`: `@ConfigurationProperties(prefix="demo")` record demonstrating AOT-visible binding.
- `GreetingService`: plain Java business logic receiving injected configuration.
- `TicketPayload`: Java record used for JSON binding in integration tests.
- `TestResourceHints`: registrar registering a test-only resource.
- `AotIntegrationTest`: `@SpringBootTest` + `@ActiveProfiles` + `@TestPropertySource` + runtime hints + skip annotation.
- `GreetingUnitTest`: two pure JUnit tests requiring no Spring context.
- `src/test/resources/samples/native-proof.txt`: test resource packaged into the native executable.

The lab omits Mockito, JPA, databases, Docker, HTTP servers, and `@ContextHierarchy` to focus cleanly on **AOT processing vs. annotation support**. Each component produces clear proof. Expand to databases/HTTP only after the baseline `nativeTest` passes on your toolchain.

### 17.1. Directory Tree

```text
spring-aot-test-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/aot/
    │   ├── AotLabApplication.java
    │   ├── GreetingProperties.java
    │   └── GreetingService.java
    └── test/
        ├── java/example/aot/
        │   ├── TicketPayload.java
        │   ├── TestResourceHints.java
        │   ├── AotIntegrationTest.java
        │   └── GreetingUnitTest.java
        └── resources/samples/
            └── native-proof.txt
```

**Every `public class`/`public record` matches its filename and lives in `example.aot`.** The text resource physically exists under `src/test/resources`; native image metadata registers its pattern.

## 18. Gradle Build: `processTestAot` and `nativeTest`

### 18.1. `settings.gradle`

```groovy
rootProject.name = 'spring-aot-test-lab'
```

### 18.2. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
    id 'org.graalvm.buildtools.native' version '0.10.1'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-json'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    testLogging {
        events 'passed', 'failed', 'skipped'
        exceptionFormat 'full'
    }
}
```

Explanation:

- Java 17 is the compilation target; the Native Image toolchain must match the Java target.
- `spring-boot-starter` supplies Spring Boot core and auto-configuration.
- `spring-boot-starter-json` adds Jackson and auto-configuration for `ObjectMapper`.
- `spring-boot-starter-test` provides Spring Test + JUnit Jupiter.
- `junit-platform-launcher` on test runtime ensures native `TestEngine` discovery has its required dependency.
- `org.graalvm.buildtools.native` enables the GraalVM plugin; the Spring Boot plugin wires AOT tasks accordingly.
- `useJUnitPlatform()` is required for Jupiter tests on Gradle's `test` task.
- We **do not declare manual `nativeCompile`/`nativeTest` tasks**, relying on the documented Boot + Native Build Tools integration.
- Do not invoke `nativeTest` using a regular JDK lacking the `native-image` toolchain.

### 18.3. Why Plugin `0.10.1`?

This is the Native Build Tools line aligned with Spring Boot 3.3.0, as documented in Boot 3.3 guides. In real setups, verify compatible GraalVM versions and plugin patches; do not drop a Boot 4.x-era plugin into a Boot 3.3 build and blame framework APIs for errors.

### 18.4. Should `nativeTest` Run on Every PR?

Native compilation consumes significantly more CPU, RAM, and time than JVM tests. Boot documentation recommends keeping most tests on the JVM while focusing native tests on behavior likely to diverge—such as reflection, resource loading, dynamic proxies, serialization, and startup. CI can run native smoke tests on critical PRs or nightly schedules based on risk; **never skip native tests completely** when your production artifact is a native executable.

## 19. Runnable Source Code: Application and Properties

### 19.1. `AotLabApplication.java`

**`src/main/java/example/aot/AotLabApplication.java`**

```java
package example.aot;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(GreetingProperties.class)
public class AotLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                AotLabApplication.class, args);
    }
}
```

`@EnableConfigurationProperties(GreetingProperties.class)` explicitly registers the properties bean, allowing Spring Boot to perform constructor binding on the Java 17 record for `demo.*`. The bean graph is AOT-processed at build time.

### 19.2. `GreetingProperties.java`

**`src/main/java/example/aot/GreetingProperties.java`**

```java
package example.aot;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record GreetingProperties(String prefix) {}
```

The record creates an immutable configuration object. The test sets `demo.prefix=Hello` via `@TestPropertySource`. In Spring Boot 3, a record with a single constructor automatically uses constructor binding—no `@ConstructorBinding` is needed for this simple case.

### 19.3. `GreetingService.java`

**`src/main/java/example/aot/GreetingService.java`**

```java
package example.aot;

import org.springframework.stereotype.Service;

@Service
public final class GreetingService {

    private final GreetingProperties properties;

    public GreetingService(GreetingProperties properties) {
        this.properties = properties;
    }

    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "name must not be blank");
        }
        return properties.prefix() + ", " + name.strip();
    }
}
```

The project avoids arbitrary reflection inside business methods. It serves as a clean baseline: if `processTestAot` fails, the cause points to build/toolchain/annotation setup rather than complex application algorithms.

## 20. Test Payload and Test-Only Resource Hints

### 20.1. `TicketPayload.java`

**`src/test/java/example/aot/TicketPayload.java`**

```java
package example.aot;

public record TicketPayload(String code, int quantity) {}
```

Test-only DTO used for a Jackson round-trip. Because the record is referenced solely from test code, Spring AOT does not always have enough evidence to add reflection hints automatically for every binding path; `@RegisterReflectionForBinding` makes the intent explicit.

### 20.2. `TestResourceHints.java`

**`src/test/java/example/aot/TestResourceHints.java`**

```java
package example.aot;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public final class TestResourceHints
        implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {
        hints.resources().registerPattern(
                "samples/native-proof.txt");
    }
}
```

Spring AOT runs the registrar and writes the resource pattern into hints consumed by Native Image. It **does not** create the file if `src/test/resources/samples/native-proof.txt` is missing—the real resource must exist.

### 20.3. `native-proof.txt`

**`src/test/resources/samples/native-proof.txt`**

```text
AOT test resource is available.
```

The file contains a single line with whatever line ending the editor uses. The test uses `trim()` to avoid LF/CRLF sensitivity, while explicitly decoding with UTF-8 to avoid platform charset dependence.

## 21. `AotIntegrationTest.java` — Spring TestContext + Annotations

**`src/test/java/example/aot/AotIntegrationTest.java`**

```java
package example.aot;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;

import org.springframework.aot.AotDetector;
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.ImportRuntimeHints;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.aot.DisabledInAotMode;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = AotLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("aot-lab")
@TestPropertySource(properties = "demo.prefix=Hello")
@RegisterReflectionForBinding(TicketPayload.class)
@ImportRuntimeHints(TestResourceHints.class)
class AotIntegrationTest {

    @Autowired
    GreetingService service;

    @Autowired
    GreetingProperties properties;

    @Autowired
    ObjectMapper objectMapper;

    @Autowired
    Environment environment;

    @Test
    void aotProcessedContextCanInjectService() {
        assertNotNull(service);
        assertEquals("Hello, Ada", service.greet("Ada"));
    }

    @Test
    void testPropertySourceIsApplied() {
        assertEquals("Hello", properties.prefix());
        assertTrue(environment.acceptsProfiles(
                org.springframework.core.env.Profiles
                        .of("aot-lab")));
    }

    @Test
    void jacksonRecordBindingWorks() throws Exception {
        TicketPayload expected =
                new TicketPayload("T-42", 3);

        String json =
                objectMapper.writeValueAsString(expected);

        TicketPayload actual =
                objectMapper.readValue(
                        json,
                        TicketPayload.class);

        assertEquals(expected, actual);
    }

    @Test
    void testResourceIsReadable() throws Exception {
        try (InputStream stream =
                getClass().getResourceAsStream(
                        "/samples/native-proof.txt")) {

            assertNotNull(stream);

            String content = new String(
                    stream.readAllBytes(),
                    StandardCharsets.UTF_8).trim();

            assertEquals(
                    "AOT test resource is available.",
                    content);
        }
    }

    @Test
    void rejectsBlankName() {
        IllegalArgumentException ex =
                assertThrows(
                        IllegalArgumentException.class,
                        () -> service.greet("  "));

        assertEquals(
                "name must not be blank",
                ex.getMessage());
    }

    @Test
    @DisabledInAotMode
    void jvmOnlyTestDoesNotRequireGeneratedAssets() {
        // Runs in ordinary JVM testing; skipped in
        // Spring AOT mode, including native test runs.
        assertFalse(
                AotDetector.useGeneratedArtifacts());
    }
}
```

### 21.1. What Does Each Annotation Prove?

- `@SpringBootTest`: context is loaded and AOT-processed by Spring TestContext.
- `@ActiveProfiles("aot-lab")`: the profile participates in test configuration during AOT processing.
- `@TestPropertySource`: supplies `demo.prefix` for configuration properties.
- `@RegisterReflectionForBinding(TicketPayload.class)`: explicit Jackson record binding hints.
- `@ImportRuntimeHints(TestResourceHints.class)`: explicit classpath resource hints.
- `@Autowired`: bean injection from the generated context.
- `@DisabledInAotMode` on **one method**: that method runs on the normal JVM yet is skipped in AOT mode; the class's other five methods still require the AOT context.
- `org.junit.jupiter.api.Test`: JUnit Jupiter drives test discovery and execution.

### 21.2. Why Must an AOT Smoke Test Still Assert Business Logic?

`aotProcessedContextCanInjectService` does not stop at verifying the Spring context starts; it asserts the exact business output. `jacksonRecordBindingWorks` tests serialization/deserialization—behavior that frequently breaks when reflection metadata is missing in a native image.

### 21.3. Why Put `@RegisterReflectionForBinding` on the Test Class?

Spring TestContext AOT docs allow this annotation on test classes. It demonstrates adding hints **scoped strictly to the test** rather than registering reflection on every application DTO in production unnecessarily.

### 21.4. `@DisabledInAotMode` Is Not a Passing Native Test

When `nativeTest` runs, `jvmOnlyTestDoesNotRequireGeneratedAssets` is expected to be skipped, not counted as an executed pass. CI must record skipped counts. If a skipped test covers critical business logic, add a native-safe replacement test instead of leaving a coverage gap.

## 22. `GreetingUnitTest.java` — Pure JUnit Without a Context

**`src/test/java/example/aot/GreetingUnitTest.java`**

```java
package example.aot;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingUnitTest {

    @Test
    void greetingIsPureJava() {
        GreetingService service =
                new GreetingService(
                        new GreetingProperties("Hi"));

        assertEquals(
                "Hi, Linh",
                service.greet("  Linh  "));
    }

    @Test
    void blankNameIsRejected() {
        GreetingService service =
                new GreetingService(
                        new GreetingProperties("Hi"));

        assertThrows(
                IllegalArgumentException.class,
                () -> service.greet(" "));
    }
}
```

These two pure unit tests omit `@SpringBootTest`, so they need no Spring TestContext or AOT-generated context, yet in the native test binary they still need JUnit native engine discovery and reachable Java classes. That is why **you do not convert every unit test into `@SpringBootTest`** just to "support AOT".

### 22.1. Total JUnit Method Counts

| Test Class | JUnit Methods | Ordinary JVM | Native AOT |
| --- | ---: | ---: | ---: |
| `AotIntegrationTest` | 6 | 6 expected to run | 5 run, 1 `@DisabledInAotMode` skipped |
| `GreetingUnitTest` | 2 | 2 expected to run | 2 expected to run |
| **Total** | **8** | **8 selected to run** | **7 selected to run, 1 skipped** |

These are **expected counts from the source code**, not an executed test report. Actual JUnit reports can include container/test-engine nodes; on compile, runtime, or filter errors, observed numbers will differ.

## 23. Running on the JVM

### 23.1. Baseline

Linux/macOS:

```bash
./gradlew clean test
```

Windows PowerShell:

```powershell
.\gradlew.bat clean test
```

Expected: the Spring Boot test context starts, properties bind, Jackson round-trips cleanly, the resource file is read, and pure unit tests pass. The `@DisabledInAotMode` method **still executes on the ordinary JVM** (no generated AOT runtime artifacts are active).

### 23.2. Running Individual Classes

```bash
./gradlew test --tests example.aot.AotIntegrationTest
./gradlew test --tests example.aot.GreetingUnitTest
```

If an individual test fails with `@ActiveProfiles`/`@TestPropertySource`, inspect context configuration before blaming the native toolchain. Until the JVM baseline passes, fix Java imports, dependencies, bean wiring, and assertions first.

### 23.3. Reading Real Results

Gradle test reports:

```text
build/test-results/test/TEST-*.xml
build/reports/tests/test/index.html
```

Inspect `tests`, `failures`, `errors`, and `skipped` per run. `BUILD SUCCESSFUL` does not prove a native executable compiled; the JVM `test` task is distinct from `nativeTest`.

## 24. Running `processTestAot` and Then `nativeTest`

Requires GraalVM `native-image` on a matching toolchain along with OS native build dependencies.

### 24.1. Checking AOT Test Processing Alone

```bash
./gradlew processTestAot
```

If this task succeeds, Spring processed the test contexts and generated assets for the current configuration. **It has not yet run JUnit inside a native binary.** If it fails, investigate Spring beans, conditions, custom loaders, or annotations before debugging the native compiler.

### 24.2. Compiling and Running the Native Test Executable

```bash
./gradlew nativeTest
```

Native Build Tools coordinates with Spring Boot AOT tasks to compile the native test executable and run tests. Dependencies, plugins, OS, and JDK must all be compatible.

Windows PowerShell:

```powershell
.\gradlew.bat processTestAot
.\gradlew.bat nativeTest
```

### 24.3. Distinguishing Tasks

| Task | What It Does | What It Does Not Prove |
| --- | --- | --- |
| `test` | JUnit JVM tests | Native support |
| `processAot` | Generates AOT assets for the application | Native binary compilation/testing |
| `processTestAot` | Generates AOT assets for `TestContext` | Successful native execution |
| `nativeCompile` | Builds production native executable | Native JUnit tests passed |
| `nativeTest` | Builds and runs native test executable | All JVM tests ran if any were skipped/filtered |
| `bootJar` | Builds JVM executable JAR | Native tests ran |
| `bootBuildImage` | Builds container image per config | Native JUnit testing |

### 24.4. If `nativeTest` Is Too Slow

Native compilation takes substantial CPU, RAM, and wall-clock time. Locally, run JVM `test` frequently; in CI, run `processTestAot` early to catch configuration issues, and reserve `nativeTest` for critical native smoke paths and release builds. Never set SLAs based on someone else's machine.

## 25. AOT-Enabled JVM Application Mode

You can verify Spring AOT generated application code on the JVM:

```bash
./gradlew bootJar
java -Dspring.aot.enabled=true -jar build/libs/spring-aot-test-lab-0.0.1-SNAPSHOT.jar
```

Precondition: the JAR must **contain generated AOT assets**. With Gradle/native plugin integration, confirm your build tasks package the generated AOT sources and resources. Running `bootJar` normally does not guarantee every configuration/version bundles them automatically; follow the Boot 3.3 AOT plugin guide (if separate AOT packaging/tasks are needed).

### 25.1. Do Not Apply `spring.aot.enabled` Directly to Ordinary `test` Tasks

`java -Dspring.aot.enabled=true` runs the **application** on the JVM with AOT assets; it does not replace `nativeTest`. Simply passing that flag to `./gradlew test` without running test AOT processing and placing generated test initializers on the test runtime classpath causes Spring TestContext to fail looking for missing artifacts.

### 25.2. AOT Mode Is Not Just a Startup Optimization Flag

When generated artifacts are active, profile and conditional choices were locked at build time. Setting a runtime property to flip the bean graph and expecting generated code to re-scan is wrong. This mode helps detect misaligned configs before native compilation.

## 26. Resource Hints: A Controlled Negative Experiment

On a learning branch, remove:

```java
@ImportRuntimeHints(TestResourceHints.class)
```

from `AotIntegrationTest`, keep `src/test/resources/samples/native-proof.txt`, and run JVM `test` first. The JVM still finds the file via standard classpath resources. Under `nativeTest`, the resource may be missing unless another mechanism registered the pattern in the binary; `testResourceIsReadable` will reveal the difference.

**This is an experiment, not a claim that missing hints fail on every compiler or configuration:** a native build may receive the resource pattern from automatic metadata or another plugin. To confirm, inspect native image resource config/generated metadata and actual test reports.

Afterwards, restore `@ImportRuntimeHints` to keep intent explicit and reproducible across toolchains.

### 26.1. Troubleshooting Resource Paths

Use `samples/native-proof.txt` and `getResourceAsStream("/samples/native-proof.txt")`. The leading slash in `getResourceAsStream` denotes an absolute classpath resource, whereas `registerPattern` normally takes a resource path without a leading slash. Avoid absolute filesystem paths in native hints.

### 26.2. Never Package All Resources Into the Native Image

A broad `**/*` pattern bloats the binary and can bundle test fixtures or secrets unnecessarily. Register only resources actually read, and never store credentials inside test resources.

## 27. Reflection Hints: A Negative Experiment

In a sandbox, remove:

```java
@RegisterReflectionForBinding(TicketPayload.class)
```

Then run:

```bash
./gradlew test
./gradlew processTestAot
./gradlew nativeTest
```

The JVM Jackson round-trip will still PASS. The native test may lack reflection metadata to deserialize the Java record **if no other auto-hints cover it**. If it still passes, inspect whether AOT discovered `TicketPayload` from other code/metadata before claiming the annotation is unnecessary everywhere.

**Canonical fix:** declare exact reflection hints for the type, or use binding paths AOT infers automatically; never force reflection on everything. For third-party serializers, consult reachability metadata and provider docs.

## 28. Why Can `RuntimeHints` Not Fix `@ContextHierarchy`?

`RuntimeHints` tells GraalVM which classes, resources, and proxies are used at runtime. It **does not** change whether the Spring TestContext AOT engine supports a context hierarchy structure. If `@ContextHierarchy` is unsupported in AOT processing, adding reflection hints for `ParentConfig`/`ChildConfig` **will not** make TestContext support hierarchies.

Redesign the test or exclude the JVM-only context from native AOT processing intentionally. Never suppress build-time errors and assume native tests ran cleanly.

## 29. Build-Time Profiles and Conditions: Negative Experiment

Suppose an app has:

```java
@Configuration
class ConditionalConfig {

    @Bean
    @ConditionalOnProperty(
            name = "demo.special.enabled",
            havingValue = "true")
    SpecialService specialService() {
        return new SpecialService();
    }
}
```

**Non-standalone snippet:** `SpecialService` is undefined. If the Spring AOT processor generates the bean graph when the property is `false`, and you later flip the property to `true` at runtime, do not expect the generated context to instantiate `SpecialService` like ordinary JVM classpath scanning.

### 29.1. Valid Ways to Handle This

- Supply the profiles/properties governing bean definitions to AOT processing at build time.
- Keep runtime feature flags controlling behavior inside **existing beans**, rather than toggling bean classes arbitrarily.
- When multiple graphs are needed, build and test distinct native artifacts per profile.
- Do not treat the fact that JVM `@TestPropertySource` varies per test class as proof that one native executable can dynamically materialize arbitrary graphs without generated initializers.

## 30. Native Test Discovery, JUnit Engines, and Filters

A Gradle task can compile a native image yet execute fewer tests than expected because:

- Only a subset of test classes can be AOT-processed.
- Classes/methods are marked `@DisabledInAotMode` or `@DisabledInNativeImage`.
- `@Tag`, Gradle `--tests`, or engine filters select only a subset.
- Jupiter engine/`junit-platform-launcher` is missing or version-mismatched on test runtime.
- JUnit 4 tests require the Vintage engine on JUnit Platform.
- Custom test tasks/source sets were excluded from `processTestAot`/`nativeTest` configuration.
- Native image does not support a particular test framework plugin or library.

### 30.1. Do Not Confuse Skipped With Undiscovered

A `@DisabledInAotMode` method is discovered conditionally by the JUnit engine and intentionally not executed in AOT mode. Report it as `skipped`, not "the native runtime failed to find JUnit `@Test`".

### 30.2. Read the Right Task Report

Inspect `nativeTest` task output and artifacts produced by your native plugin/version; do not read an earlier JVM `test` XML report and call native tests PASS. In CI, archive JVM and native JUnit results separately.

### 30.3. Pure Unit Tests and AOT Generation

Pure JUnit unit tests require no Spring `ApplicationContext`; the Spring TestContext AOT processor does not need to generate initializers for them. Yet the JUnit engine can still compile them into the native test executable when test selection and plugin support apply. Never force pure unit tests to use `SpringExtension` just for discovery.

## 31. `@Sql` and Transactional Tests in Native Mode

Suppose a `@DataJpaTest` reads `schema.sql`/`test-data.sql`:

```java
@DataJpaTest
@Sql("/sql/seed-test-data.sql")
class JpaRepositoryNativeTest {
    @Test
    void findsSeededEntity() {
        // Assertions via repository.
    }
}
```

This snippet is **not runnable**: Entity, Repository, datasource, and resource are omitted. Native tests require:

1. Native support for the JPA provider and DB driver.
2. Resource `sql/seed-test-data.sql` included inside the native image.
3. Entity metadata, converters, proxies, and reflection hints.
4. Correct Spring TestContext transaction rollback semantics.
5. Separation of internal JVM test data from external database side effects when targeting real DBs.

If an `@Sql` script is not packaged, the error is a missing resource, not an SQL dialect issue. If DB connections fail, check service readiness, network, and drivers—never tweak `@Transactional` to work around missing runtime hints.

## 32. `@DirtiesContext` and the Native Cache

`@DirtiesContext` makes a test reload its context at runtime. However, the AOT-generated context retains the same pre-processed bean graph; it will not synthesize new bean definitions for a different runtime profile.

- Useful when a singleton or bean state is mutated and cannot be reset otherwise.
- Not a default mechanism for database fixture cleanup.
- Does not create new GraalVM reflection hints after image compilation.
- Native startup/reinitialization timings can differ from JVM; benchmark separately if relevant.
- Under parallel tests, closing/evicting a context used by another thread causes races.
- With many distinct test contexts, AOT build time and context cache memory increase noticeably.

## 33. `TestRuntimeHintsRegistrar` and `AotTestExecutionListener`

These are two key extension points for projects with custom test infrastructure.

### 33.1. Global Hints

If a custom test framework/library needs resources or reflection across all test contexts, implement `TestRuntimeHintsRegistrar` and register it in `META-INF/spring/aot.factories`. When hints belong to a production component, prefer `RuntimeHintsRegistrar` alongside that component to avoid unconditional packaging.

### 33.2. Custom `TestExecutionListener`

A custom listener with build-time contributions that must run during AOT processing should implement `AotTestExecutionListener`. Do not implement only `TestExecutionListener` and expect Spring AOT to invoke it at build time.

### 33.3. Custom `ContextLoader`

A custom loader must implement `AotContextLoader` to support AOT build time and runtime. Never attach `@ContextConfiguration(loader=LegacyLoader.class)` to a native test suite assuming the engine can infer how to generate the context.

### 33.4. AOT Failures Fail Fast by Default

Spring Framework 6.1 **fails** by default on AOT processing errors. Property `spring.test.aot.processing.failOnError=false` lets processing continue and log errors during diagnostics; **never use this setting in a default CI release gate**, as it hides missing native coverage and broken contexts.

## 34. Categorizing Failures by Phase

| Phase | Symptom | Likely Root Cause |
| --- | --- | --- |
| `compileJava` | Cannot resolve annotation/record | Wrong imports/version/API |
| `compileTestJava` | `@DisabledInAotMode` class not found | Spring Framework version too old |
| `test` (JVM) | `Failed to load ApplicationContext` | Bean scan/config/dependencies |
| `test` (JVM) | Assertions failed | Business or test logic |
| `processTestAot` | Unsupported hierarchy | `@ContextHierarchy` in AOT |
| `processTestAot` | Missing property / bean graph failure | Build-time profile/condition mismatch |
| `processTestAot` | Custom loader/listener errors | Missing AOT SPI implementation |
| `nativeCompile` / native image build | Unsupported reflection/library | Missing hints or reachability metadata |
| `nativeTest` startup | Resource not found | Missing resource hints or packaging |
| `nativeTest` startup | Cannot instantiate bean | Generated config or provider incompatibility |
| `nativeTest` JUnit | Skipped due to annotation | `@DisabledInAotMode`/native condition |
| `nativeTest` JUnit | Test assertion failed | Real behavioral divergence |
| `nativeTest` zero tests | Engine/filter/task discovery | `TestEngine`, selectors, or runtime deps |
| Native-only CI | Linker/platform/architecture errors | GraalVM/OS/C compiler toolchain |
| Native-only CI | Docker/network connection error | Container readiness or permissions |

Never lump all of these under "native test failed", because fixes differ radically.

## 35. When You Need to Register Resource or Reflection Hints

A clean diagnostic sequence:

1. Run the JVM test with the exact input to rule out business bugs.
2. Run `processTestAot` to validate Spring-generated contexts.
3. Read the root cause before the final `Caused by` when the native compiler fails.
4. Identify the exact missing type, method, or resource.
5. Check whether Spring AOT already generates hints for it.
6. If not, add `@RegisterReflectionForBinding`/`@ImportRuntimeHints`/`RuntimeHintsRegistrar` at the proper scope.
7. Re-run `nativeTest` and confirm the test actually executed without being skipped or filtered.
8. Inspect binary size and metadata scope if hints expanded broadly.
9. Add a regression test for the fixed behavior.
10. Record GraalVM/JDK/Native Build Tools versions, since provider updates can alter required hints.

**Do not commit unfiltered reflection agent output** as permanent reachability metadata: running the tracing agent during tests captures test-infrastructure hints unnecessary in the production binary. Review and trim metadata intentionally and re-test.

## 36. Maven `nativeTest` When Not Using Gradle

With Spring Boot 3.3 Maven starter parent and the Native Build Tools Maven plugin, configure the `nativeTest` profile and run:

```bash
mvn test
mvn -PnativeTest test
```

The second command runs the AOT/native test pipeline when plugins and profiles are configured properly. Do not assume `mvn -Pnative test` automatically runs native **test** coverage—the `native` profile builds the production AOT/native binary, whereas `nativeTest` builds and runs the test binary.

**Important:** without `spring-boot-starter-parent`, you must configure `spring-boot:process-test-aot` and the Native Build Tools test goal per the Boot 3.3 Maven plugin guide. Never copy a Boot 4.x POM or a `native-maven-plugin` from a different generation into a Boot 3.3 project.

### 36.1. Maven Test Naming Still Matters

Surefire uses default patterns such as `*Test`/`*Tests`; Maven Failsafe commonly uses `*IT`. Engine selection and file naming govern which tests AOT processes. If native test counts are low, do not add hints blindly when Maven includes filtered out the test classes from the start.

## 37. Scoping the Native Test Suite

To balance build cost and risk:

| Test Layer | Goal | Priority |
| --- | --- | --- |
| Pure JVM unit tests | Business logic, edge cases | Run on every PR |
| JVM `@SpringBootTest` | Dependency injection, transactions, integration | Run regularly |
| JVM test slices | MVC/JPA/JSON behavior in scope | Run regularly |
| `processTestAot` | Test context AOT generation | Run on test config/AOT changes |
| JVM app with generated AOT | App startup with AOT assets | Useful for early debugging |
| `nativeTest` smoke | Startup, binding, resources, hints | Run on native CI toolchain |
| Native DB/HTTP integration | Provider behavior inside binary | Based on release risk |
| Production native binary E2E | Real deployment environment | Release / critical paths |

A suite with many JVM-only tests remains valuable. However, do not claim full native compatibility if critical serialization, security, or provider paths have never executed inside a native binary.

### 37.1. When Multiple Profiles Exist

If a profile alters the bean graph, create a native testing/release plan for each graph you must support. Do not assume a single generated initializer adapts dynamically to every runtime profile.

### 37.2. Dealing With Unsupported Annotations

- Move behavior needing native coverage onto an equivalent static bean graph where valid.
- For `@ContextHierarchy`, retain the JVM test or intentionally flatten the test scope.
- For Mockito tests, consider native-safe test fakes or real collaborators rather than forcing Mockito on an unsupported toolchain.
- For custom loaders/listeners, implement the AOT SPI before converting.
- For JPA/resources/JSON, verify native provider support and hints.

## 38. Controlled Negative Experiments

### 38.1. Testing Class-Level `@DisabledInAotMode`

Create **one class with an independent test context** (distinct properties/beans) annotated with `@DisabledInAotMode`; verify it runs under JVM `test` while excluded from AOT build and native runtime. Never omit the annotation on another class sharing the same context, as Spring enforces consistency across shared-context groups.

### 38.2. Testing `@DisabledInNativeImage`

Put `@DisabledInNativeImage` on a JUnit method. Even though the method is skipped inside the native executable, TestContext AOT still processes the enclosing class/context at build time. If that context is unsupported, switch to `@DisabledInAotMode` or redesign the context.

### 38.3. Testing Runtime Property Changes Controlling Bean Graphs

Create a `@ConditionalOnProperty` config in a sandbox, run AOT processing with `false`, and run with `true` at runtime. Compare with ordinary JVM startup. Never rely on this pattern for production toggles without designing build-time profiles.

### 38.4. Testing Missing Resource Hints

Remove `@ImportRuntimeHints` and run `nativeTest`; if the test fails with a missing resource, restore the pattern. If it still passes, inspect auto-hints/plugin behavior rather than assuming hints never matter.

### 38.5. Testing Missing Reflection Hints

Remove `@RegisterReflectionForBinding` and observe native JSON record binding; if it passes because auto-configuration generated Jackson metadata, inspect the generated hints before concluding the annotation is redundant.

### 38.6. Testing `@ContextHierarchy` Migration From JVM

In an experimental branch, keep one hierarchy-based class and one flat-context replacement. JVM runs pass both; AOT processes the flat-context version while the hierarchy-based test stays marked JVM-only if unsupported.

### 38.7. Testing Mockito

Create a Boot 3.3 JVM test using `@MockBean` alongside a native-smoke fake-bean equivalent. Compare coverage and behavior. Never treat "mocks were skipped" as native verification of business logic.

### 38.8. Testing Custom Loaders

Use a legacy custom `ContextLoader` in AOT, record the full error, then implement `AotContextLoader` or revert to the default Spring Boot loader. Never add reflection hints to paper over a missing SPI contract.

## 39. Common Misconceptions

### 39.1. "JVM Passed, So Native Will Pass"

False—the native compiler requires reachability metadata, resources, proxies, native-friendly libraries, and AOT-generated contexts.

### 39.2. "`processTestAot` Passed, So `nativeTest` Will Pass"

False—`processTestAot` only generates assets; native compilation or runtime can still fail in later steps.

### 39.3. "`@DisabledInNativeImage` Is the Same as `@DisabledInAotMode`"

False—a JUnit native condition does not exclude a Spring test context from build-time AOT analysis.

### 39.4. "Adding Reflection Hints Fixes `@ContextHierarchy`"

False—that is a TestContext AOT architectural limitation, not simply missing class reflection.

### 39.5. "A Runtime Profile Can Add Any Bean"

False for AOT-generated bean graphs: build-time conditions and profiles may have already fixed the decision.

### 39.6. "Every `@MockBean` Runs identically in Native and JVM"

Never assume this in Boot 3.3; Mockito/native image support has provider, version, and toolchain limits.

### 39.7. "`@SpringBootTest` Automatically Adds the JUnit Engine"

False. JUnit Platform still requires a compatible Jupiter `TestEngine` and launcher; `SpringExtension` does not replace the engine.

### 39.8. "`@DirtiesContext` Makes Spring AOT Re-Analyze Everything"

False. A compiled native image cannot dynamically add new classpath items, hints, or bean conditions.

### 39.9. "A Test Resource on the JVM Is Automatically in the Native Image"

Not guaranteed. Native resource inclusion depends on metadata/hints and native image build configuration.

### 39.10. "`@Sql` Cleans Up an External DB Across Contexts"

False when tests run in parallel on a shared DB; AOT does not solve isolation or data ownership.

### 39.11. "No Need to Separate Skips From Passes"

False. Skipped tests are not verified native behavior. CI must track executed, failed, and skipped counts separately.

### 39.12. "Boot 4.x Docs Apply Directly to Boot 3.3"

False—APIs, annotations, and plugin versions changed. Pin documentation to your exact release line.

### 39.13. "`nativeCompile` Alone Suffices Without `nativeTest`"

Compiling the native app binary proves an artifact builds, not that assertions execute inside the native runtime. `nativeTest` supplies different proof.

### 39.14. "Having Any GraalVM JDK Is Enough"

Not guaranteed; you need the `native-image` CLI/component, the OS C/C++ compiler/linker toolchain, enough RAM, and runtime OS compatibility.

### 39.15. "Any Mockito Error Is a Spring AOT Bug"

It may be a native-image/JUnit/Mockito instrumentation incompatibility; classify the failure before widening hints.

## 40. Symptom Diagnostic Table

| Symptom | Suggested Cause | First Step |
| --- | --- | --- |
| `processTestAot` task missing | GraalVM native/AOT plugin not applied | Inspect Gradle plugins |
| `native-image: command not found` | GraalVM Native Image not installed | Check `native-image --version` and GraalVM env |
| `@DisabledInAotMode` cannot resolve | Wrong Framework version or import | Spring 6.1+, verify package |
| Unsupported context hierarchy | `@ContextHierarchy` in AOT | Switch to flat context or disable class |
| Bean missing in AOT build | Profile/property evaluated at build time | Inspect `processTestAot` environment |
| Native reflection constructor error | Missing reflection hints | Add `@RegisterReflectionForBinding` |
| Test resource returns null | Missing resource hints or packaging | Check `@ImportRuntimeHints`/resource path |
| Jackson binding fails only in native | Record/serializer hints or provider | Check binding hints and `ObjectMapper` config |
| Missing `TestEngine` | Dependency/runtime classpath issue | Check `junit-platform-launcher`/Jupiter |
| All native tests skipped | Disabled annotations or filters | Check skipped counts and reasons |
| JVM runs 8, native runs 7 | AOT-only skip method | Expected from `@DisabledInAotMode` |
| Class skipped yet AOT still processes shared context | Shared-context consistency rule | Annotate all classes sharing that config |
| `@DisabledInNativeImage` set yet AOT build fails | Native-only skip does not exclude AOT | Use `@DisabledInAotMode` or fix graph |
| Native compilation OOM | Image build memory pressure | Increase RAM, tune toolchain/CI runner |
| Native process starts yet DB fails | Driver or service readiness | Check native driver, health, connection |
| Wrong dynamic port | Testcontainers lifecycle/property timing | Check `@DynamicPropertySource`/`@ServiceConnection` |
| `@MockBean` creation fails in native | Mockito dynamic mocking limitation | Use native-safe test fake; keep JVM tests |
| Maven `nativeTest` profile not found | Missing Boot parent/plugins/profile | Configure Boot 3.3 `nativeTest` |
| Gradle `test` passes, `nativeTest` finds 0 tests | Native runner selection/engine issue | Inspect task logs, filters, test reports |
| Runtime conditional bean differs | Build-time AOT graph fixed | Align profiles and conditions |
| `@Sql` script missing in native | Test resource not packaged | Add resource hints |
| Custom `TestContext` loader fails AOT | Not an `AotContextLoader` | Implement AOT-compatible loader |
| Unexpected test bean reloads | Context caching/dirtying | Inspect cache diagnostics; avoid `@DirtiesContext` misuse |
| Native smoke passes yet production API fails | Insufficient native coverage | Add native HTTP/provider integration tests |

## 41. Hands-On Exercises

1. Run `./gradlew clean test` on the JVM and record exact executed, skipped, and failed method counts.
2. Run `./gradlew processTestAot` and inspect the generated test assets.
3. Install a compatible GraalVM Native Image and run `./gradlew nativeTest`; record executed/skipped counts from the real report.
4. Keep `@DisabledInAotMode` on one method and observe it run in ordinary JVM tests yet skip in native tests.
5. Switch that annotation to `@DisabledInNativeImage` in a sandbox; compare AOT build-time processing vs. native runtime selection.
6. Create a class-level `@DisabledInAotMode` with a distinct context key and inspect build-time handling.
7. Create two classes sharing one context; mark only one class-level `@DisabledInAotMode` to observe the shared-context consistency rule.
8. Remove `@RegisterReflectionForBinding`, observe native Jackson record binding, and inspect generated hints.
9. Remove `@ImportRuntimeHints`, test native resource lookup, and inspect resource metadata.
10. Write a `RuntimeHintsRegistrar` for a proxy interface in a sandbox and verify the exact interface list.
11. Create a test with `@ContextHierarchy`, capture the unsupported AOT error, and design a flat-context alternative.
12. Create a `@ConditionalOnProperty` bean, vary the property between AOT build time and runtime, and compare outputs.
13. Try `@ActiveProfiles` with two profiles yielding different bean graphs and count generated contexts.
14. Convert a JVM `@MockBean` test to an explicit test fake bean and run a native smoke test.
15. Keep Mockito interaction tests on the JVM without claiming fake-bean native smoke tests cover Mockito assertions.
16. Create a `@JsonTest` with a DTO record and custom serializer; check binding/reflection hints.
17. Create a `@WebMvcTest` controller returning a DTO; check endpoint/JSON native serialization.
18. Create a `@DataJpaTest` with an embedded/native-compatible driver and entity/SQL resources; note provider-specific limitations.
19. Add an `@Sql` script under `src/test/resources` and verify native resource availability.
20. Create a runtime-only custom `TestExecutionListener` and study `AotTestExecutionListener` for build-time contributions.
21. Create a custom `ContextLoader` in a sandbox and examine the `AotContextLoader` contract.
22. Add a JUnit 4 test with the Vintage engine to run via Platform; check real native plugin support.
23. Run the ordinary JVM app with `spring.aot.enabled=true` on a JAR containing generated artifacts; note differences from JVM tests.
24. Run `nativeCompile` and `nativeTest` separately and explain why one passing does not prove the other passes.
25. Build a CI matrix for JVM tests + AOT processing + native smoke, tracking build times, resource cost, and coverage gaps.
26. Upgrade Boot 3.3 → newer Boot on a separate branch, comparing versions, test annotations, Mockito support, and Native Build Tools plugin compatibility.
27. Use the tracing agent to discover missing hints for a third-party library; review and sanitize metadata rather than copying raw JSON blindly.
28. Maintain an inventory of tests skipped in native mode with owners and reasons, proposing native-safe replacements for critical paths.

## 42. QA Checklist When Moving Tests to AOT/Native

- [ ] Recorded exact Spring Boot, Framework, JUnit, Gradle, Native Build Tools, and GraalVM versions.
- [ ] JVM baseline tests run with real executed counts.
- [ ] `processTestAot` generates test-scoped contexts cleanly.
- [ ] `nativeTest` executes the test binary, not just `nativeCompile`.
- [ ] Test runtime includes a compatible JUnit Jupiter engine and launcher.
- [ ] `@SpringBootTest`/test slices match intended scope.
- [ ] `@ActiveProfiles` and bean-graph-controlling properties align at build time.
- [ ] `@TestConfiguration`/`@Import` beans are visible to the AOT processor.
- [ ] `@DynamicPropertySource` supplies appropriate dynamic values without expecting runtime bean-graph changes.
- [ ] `@ContextHierarchy` has been removed from AOT tests or explicitly redesigned.
- [ ] `@DisabledInAotMode` method vs. class scope is properly understood.
- [ ] All classes sharing a context with a class-level `@DisabledInAotMode` carry consistent annotations.
- [ ] `@DisabledInNativeImage` is not misused as an AOT build-time exclusion.
- [ ] Mockito `@MockBean`/`@SpyBean` native compatibility was verified rather than assumed.
- [ ] JPA test injection annotations match the active Framework version.
- [ ] `@Transactional` and `@Sql` are tested with real providers and packaged resources.
- [ ] `@DirtiesContext` is not used as a substitute for missing runtime hints.
- [ ] Custom loaders implement `AotContextLoader` where required.
- [ ] Custom listeners implement the right AOT SPI if making build-time contributions.
- [ ] DTO/record bindings carry reflection hints where needed.
- [ ] Classpath resources have both resource hints and real source files.
- [ ] Native proxies, serialization, and third-party libraries have matching reachability metadata.
- [ ] Avoided overly broad wildcard reflection/resource registrations.
- [ ] GraalVM `native-image`, C/C++ toolchain, and CI RAM are provisioned.
- [ ] Native tests do not depend on unavailable Docker/providers.
- [ ] Reports distinguish build errors, native runtime errors, assertion failures, and skips.
- [ ] JVM-only tests remain maintained where native support is incomplete.
- [ ] Critical native paths have native-compatible regression tests.
- [ ] Avoided setting `spring.test.aot.processing.failOnError=false` just to turn CI green.
- [ ] Never claimed native PASS without running `nativeTest` on the target toolchain.
- [ ] Re-verified the annotation support matrix when upgrading Boot/Framework.
- [ ] Hints and tracing agent outputs contain zero test secrets or sensitive data.
- [ ] Project docs separate exact commands and expected vs. observed results.

## 43. A Quick Decision Tree for Immediate Use

```text
JVM @SpringBootTest PASS, nativeTest FAIL?
        |
        +-- processTestAot FAIL?
        |       |
        |       +-- @ContextHierarchy?
        |       |       -> Unsupported AOT; redesign/disable.
        |       |
        |       +-- Build-time property/profile mismatch?
        |       |       -> Align AOT build configuration.
        |       |
        |       +-- Custom loader/listener?
        |               -> AotContextLoader/AotTestExecutionListener.
        |
        +-- native-image compiler FAIL?
        |       |
        |       +-- Reflection/resource/proxy missing?
        |       |       -> RuntimeHints/@RegisterReflectionForBinding.
        |       |
        |       +-- Mockito/native library incompatible?
        |               -> Native-safe fake/upgrade/metadata.
        |
        +-- Native executable starts but tests FAIL?
        |       |
        |       +-- Resource missing?
        |       |       -> registerPattern, package resource.
        |       |
        |       +-- External driver/service?
        |       |       -> Provider native support/readiness.
        |       |
        |       +-- Assertion mismatch?
        |               -> Diagnose actual business behavior.
        |
        +-- Native tests are skipped/not discovered?
                |
                +-- @DisabledInAotMode/@DisabledInNativeImage?
                +-- JUnit engine/filters/classpath?
                +-- Wrong Gradle/Maven source set/test task?
```

## 44. Summary

**AOT test support is real**, yet **it does not mean every annotation and dynamic JVM testing technique runs inside a GraalVM Native Image**. With Spring Boot 3.3 / Framework 6.1, `@SpringBootTest` and many test slices are supported; `@ContextHierarchy` is a documented limitation; Spring `@DisabledInAotMode` governs build-time test context processing, distinct from JUnit native-only conditions. `@ActiveProfiles`, `@TestPropertySource`, and bean conditions must be evaluated against the build-time context. Reflection, resources, and proxies require runtime hints when Spring cannot infer them, and Mockito/native integration must be verified independently.

A trustworthy testing workflow is **JVM tests → TestContext AOT processing → GraalVM native test execution**, with each stage reporting its own results and failures. Never treat skipped tests or `failOnError=false` as proof of successful migration. Maintain JVM test coverage, add native-safe smoke and integration assertions for paths likely to diverge, and keep version matrices aligned during upgrades.

## 45. Official Documentation and Verification Resources

- Spring Framework 6.1 — TestContext AOT package/Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/test/context/aot/package-summary.html
- Spring Framework 6.1 — `@DisabledInAotMode` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.1/javadoc-api/org/springframework/test/context/aot/DisabledInAotMode.html
- Spring Framework — Ahead of Time Support for Tests: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/aot.html
- Spring Framework — Core AOT optimizations and runtime hints: https://docs.spring.io/spring-framework/reference/core/aot.html
- Spring Framework 6.1 — `@RegisterReflectionForBinding` API: https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/aot/hint/annotation/RegisterReflectionForBinding.html
- Spring Framework — RuntimeHints & `@ImportRuntimeHints`: https://docs.spring.io/spring-framework/reference/core/aot.html
- Spring Boot 3.3 — Testing native applications: https://docs.spring.io/spring-boot/3.3/reference/packaging/native-image/testing-native-applications.html
- Spring Boot 3.3 — Gradle AOT plugin/tasks: https://docs.spring.io/spring-boot/docs/3.3.0-SNAPSHOT/gradle-plugin/reference/htmlsingle/
- Spring Boot 3.3 — Maven AOT processing: https://docs.spring.io/spring-boot/3.3/maven-plugin/aot.html
- Spring Boot 3.3 — Native image advanced topics: https://docs.spring.io/spring-boot/3.3/reference/packaging/native-image/advanced-topics.html
- Spring Boot 3.3 — Spring Boot testing: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot GraalVM wiki — Mockito/native limitations: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-with-GraalVM
- JUnit Jupiter — `@DisabledInNativeImage`/`@EnabledInNativeImage` conditions: https://docs.junit.org/5.11.4/user-guide/index.html
- GraalVM — Native Image testing with Maven and Gradle: https://www.graalvm.org/latest/reference-manual/native-image/guides/debug-native-tests-maven-gradle/
