# Dependency Injection into Test Instances and Constructors in Spring TestContext

In plain Java JUnit Jupiter tests, tests usually instantiate objects directly with `new`. When verifying the behavior of Spring-managed beans, tests can receive dependencies from an **`ApplicationContext`**: for example, configured services, repositories, beans selected by profile, or values from `application-test.yml`. The Spring TestContext Framework provides **dependency injection (DI) into the test instance** via fields or setters, and **constructor injection** when integrating with JUnit Jupiter through `SpringExtension`.

These two injection styles differ in when values are assigned, whether `final` fields can be used, how JUnit resolves constructor parameters, and how they interact with lifecycle and context caching. Choosing the right style keeps tests readable and free of `null` fields, `ParameterResolutionException`, or stale references to beans from a closed context.

## 1. How Do JUnit, SpringExtension, and TestContext Coordinate?

JUnit Jupiter manages creating test instances, selecting `@Test` methods, and running lifecycle callbacks. **`SpringExtension`** bridges Spring TestContext with JUnit Jupiter's extension model. Spring TestContext loads (or retrieves from cache) the `ApplicationContext` and uses its beans to supply dependencies to tests.

```text
JUnit Jupiter runner
        |
        +--> SpringExtension / Spring TestContext
        |        |
        |        +--> @Configuration, @Bean, properties, profiles
        |        |           |
        |        |           v
        |        |      ApplicationContext
        |        |
        |        +--> Constructor parameter resolution (before creating test object)
        |        |
        |        +--> Field/setter injection (after test object is created)
        |
        +--> @BeforeEach --> @Test --> @AfterEach --> report
```

The **`DependencyInjectionTestExecutionListener`** registered by default in TestContext handles **field/setter injection on the test instance**. For JUnit Jupiter test **constructors**, `SpringExtension` implements `ParameterResolver` so JUnit can instantiate the test object with Spring beans.

Commonly used annotations:

| Component | Purpose |
|---|---|
| `@ExtendWith(SpringExtension.class)` | Registers integration between JUnit Jupiter and Spring TestContext |
| `@SpringJUnitConfig(MyConfig.class)` | Combines SpringExtension with `@ContextConfiguration` to load a specific configuration |
| `@SpringBootTest` | Loads a Spring Boot application context and integrates SpringExtension |
| `@Autowired` | Requests DI via field, setter, constructor, or parameter |
| `@Qualifier` | Selects a specific bean when multiple beans share the same type |
| `@Value` | Supplies a property from the Spring `Environment` |
| `@TestConstructor(autowireMode = ALL)` | Instructs Spring to resolve all parameters of the test constructor |
| `@TestPropertySource` / `@ActiveProfiles` | Supplies properties or profiles for the test context |
| `@TestInstance` | Controls whether JUnit creates one test object per method or shares one object |
| `@DirtiesContext` | Marks the context to be closed/evicted from cache at the configured milestone |

**Do not add `@ExtendWith(SpringExtension.class)` again** when a Spring Boot testing annotation such as `@SpringBootTest` or `@SpringJUnitConfig` already registers it. A test with only `@Test` and `@Autowired` and no Spring integration will not automatically receive injected beans.

### Distinguishing Test Objects from Beans

`ShippingPolicyTest` is a **test instance** created by JUnit. `ShippingPolicy` is a **bean** created by the Spring `ApplicationContext`. By default, the test instance may be recreated before every method, whereas a singleton bean in the same context can be reused. This distinction is especially important for tests with mutable state or `@DirtiesContext`.

## 2. How Do Field, Setter, and Constructor Injection Differ?

| Style | Injection Timing | Strengths | Notes |
|---|---|---|---|
| **Field** `@Autowired ShippingService service;` | After JUnit creates the test instance | Very concise for tests | Fields cannot be `final` with this style; dependencies are less visible on the constructor signature |
| **Setter** `@Autowired void setService(...)` | After the instance is created | Values can be updated or reinjected across the lifecycle | Adds setup methods; avoid hidden state |
| **Constructor** `@Autowired Test(ShippingService service)` | When JUnit creates the instance; Spring resolves parameters | Makes dependencies explicit; allows `final` fields | Requires constructor autowiring config and attention to JUnit `ParameterResolver` |
| **Test method parameter** `@Test void test(@Autowired Service s)` | When JUnit invokes the test method | Useful for beans needed in a single method | Works only with SpringExtension and a matching bean |

Syntactic example of field injection:

```java
@SpringJUnitConfig(TestConfig.class)
class ServiceTest {
    @Autowired
    Service service;
}
```

The example above only illustrates annotation placement; `TestConfig` and `Service` must be defined in the project, and `@Test` methods must be added for a complete test.

Setter injection can also be written inside a test class:

```java
private Service service;

@Autowired
void setService(Service service) {
    this.service = service;
}
```

And constructor injection allows declaring `final` fields:

```java
private final Service service;

@Autowired
ServiceTest(Service service) {
    this.service = service;
}
```

**Do not extrapolate production constructor rules to test constructors:** Spring can automatically pick a single constructor on a production bean without `@Autowired`, whereas JUnit instantiates test classes. A test constructor needs `@Autowired`, `@TestConstructor(ALL)`, or an equivalent parameter injection mechanism; having a single constructor is not enough for Spring to supply all parameters by default.

## 3. Complete Java 17+ Example: Two Ways to Receive the Same Bean

The example uses this rule: orders with a subtotal below **500,000 VND** pay a shipping fee of **30,000 VND**; from that threshold upward, shipping is free. Negative subtotals are invalid. We place a bean in test configuration to observe Spring injecting the exact object.

Project layout:

```text
src/
├── main/java/com/example/shop/
│   └── ShippingPolicy.java
└── test/java/com/example/shop/
    ├── ShippingTestConfig.java
    ├── ShippingFieldAndSetterTest.java
    └── ShippingConstructorInjectionTest.java
```

### 3.1. Production Code

File **`src/main/java/com/example/shop/ShippingPolicy.java`**:

```java
package com.example.shop;

public final class ShippingPolicy {
    private final long freeShippingThresholdVnd;

    public ShippingPolicy(long freeShippingThresholdVnd) {
        if (freeShippingThresholdVnd < 0) {
            throw new IllegalArgumentException("threshold must be nonnegative");
        }
        this.freeShippingThresholdVnd = freeShippingThresholdVnd;
    }

    public long feeVnd(long subtotalVnd) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("subtotal must be nonnegative");
        }
        return subtotalVnd >= freeShippingThresholdVnd ? 0L : 30_000L;
    }
}
```

This is plain Java and can be unit tested with `new ShippingPolicy(500_000L)` without Spring. Here we use a Spring context to practice test dependency injection mechanics.

### 3.2. Test-Only Spring Configuration

File **`src/test/java/com/example/shop/ShippingTestConfig.java`**:

```java
package com.example.shop;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class ShippingTestConfig {

    @Bean
    ShippingPolicy shippingPolicy() {
        return new ShippingPolicy(500_000L);
    }
}
```

The test config loads only the declared bean, avoiding booting an entire application just to practice injection. Because the file lives under `src/test/java`, it belongs to the test source set, not production sources.

### 3.3. Field and Setter Injection

File **`src/test/java/com/example/shop/ShippingFieldAndSetterTest.java`**:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;

@SpringJUnitConfig(ShippingTestConfig.class)
class ShippingFieldAndSetterTest {

    @Autowired
    private ShippingPolicy policy;

    private ApplicationContext context;

    @Autowired
    void setContext(ApplicationContext context) {
        this.context = context;
    }

    @Test
    void fieldInjectionProvidesTheConfiguredPolicy() {
        assertEquals(30_000L, policy.feeVnd(499_999L));
        assertEquals(0L, policy.feeVnd(500_000L));
    }

    @Test
    void setterInjectionProvidesTheApplicationContext() {
        assertSame(policy, context.getBean(ShippingPolicy.class));
    }
}
```

When preparing the test, Spring TestContext injects `policy` into the field and calls the `setContext` setter. The first test verifies the configured bean's rules; the second confirms the field points to the same singleton bean managed by `ApplicationContext`.

### 3.4. Constructor Injection with `@TestConstructor(ALL)`

File **`src/test/java/com/example/shop/ShippingConstructorInjectionTest.java`**:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.test.context.TestConstructor;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringJUnitConfig(ShippingTestConfig.class)
@TestPropertySource(properties = "app.currency=VND")
@TestConstructor(autowireMode = TestConstructor.AutowireMode.ALL)
class ShippingConstructorInjectionTest {

    private final ShippingPolicy policy;
    private final String currency;

    ShippingConstructorInjectionTest(
            ShippingPolicy policy,
            @Value("${app.currency}") String currency) {
        this.policy = policy;
        this.currency = currency;
    }

    @Test
    void constructorProvidesFinalDependencies() {
        assertEquals(0L, policy.feeVnd(500_000L));
        assertEquals("VND", currency);
    }

    @Test
    void injectedPolicyRejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> policy.feeVnd(-1L));
    }
}
```

Here `@TestConstructor(ALL)` tells Spring to resolve **all constructor parameters**, so `ShippingPolicy` is injected by type and `currency` comes from `@Value` via `@TestPropertySource`. Once instantiated, both fields are `final`.

These two test classes contain **4 `@Test` methods** in total, all expected to PASS when the context, test engine, and dependencies are properly configured. No database, MockMvc, or web server is required. The Java classes and imports in the four files suffice for Java 17+ and a Spring Boot project with compatible Spring TestContext/JUnit Jupiter.

### 3.5. Running the Examples via Maven or Gradle

The project needs test dependencies such as `spring-boot-starter-test` and a compatible JUnit Jupiter runner. Run from the module directory containing `pom.xml` or `build.gradle` and the wrapper:

```bash
# Maven: run just the two example classes
./mvnw -Dtest=ShippingFieldAndSetterTest,ShippingConstructorInjectionTest test

# Or Gradle: test task using JUnit Platform
./gradlew test --tests "com.example.shop.ShippingFieldAndSetterTest" --tests "com.example.shop.ShippingConstructorInjectionTest"
```

On Windows use `mvnw.cmd` or `gradlew.bat`. Run only the command matching your project's build tool; you do not need to run both. **Expected result: 4 tests passed, 0 failed**. There is no fixed business stdout because tests report outcomes through Maven/Gradle/JUnit, and report formatting varies by version.

If you run `./mvnw test` or `./gradlew test` for the whole module, the test count may exceed 4 if other tests exist.

## 4. Which Rules Govern Test Constructor Autowiring?

SpringExtension provides constructor parameter resolution in two ways:

1. **Individual parameters:** if a parameter carries `@Autowired`, `@Qualifier`, `@Value`, or has a matching `ApplicationContext` type, Spring can resolve that specific parameter.
2. **Entire constructor:** if the constructor carries `@Autowired`, the class carries `@TestConstructor(autowireMode = ALL)`, or the default test constructor autowire mode is changed to `ALL`, Spring handles **all constructor parameters**.

Comparison table:

| Configuration | Resolution Behavior |
|---|---|
| `@Autowired` on constructor | All parameters belong to Spring |
| `@TestConstructor(autowireMode = ALL)` on test class | All parameters belong to Spring |
| `spring.test.constructor.autowire.mode=all` | Enables all-parameter autowiring globally per Spring TestContext configuration unless overridden |
| Default `ANNOTATED` | Only Spring-recognized parameters; other parameters can be resolved by another JUnit extension |

Example **replacing** the constructor of `ShippingConstructorInjectionTest` in Section 3.4 with an `@Autowired` constructor:

```java
@Autowired
ShippingConstructorInjectionTest(
        ShippingPolicy policy,
        @Value("${app.currency}") String currency) {
    this.policy = policy;
    this.currency = currency;
}
```

When using this form, remove `@TestConstructor(ALL)` from the class and add `import org.springframework.beans.factory.annotation.Autowired`. This is a **replacement snippet**; do not add a second constructor with the same signature. Both options achieve the same goal: beans are supplied when creating the test instance and can be stored in `final` fields.

### Distinguishing Spring's Resolver from JUnit Jupiter's Resolvers

JUnit also has resolvers for `TestInfo`, `TestReporter`, and `@ParameterizedTest` arguments. If a constructor is marked **autowirable as a whole** by Spring, Spring is responsible for resolving every argument; other extensions **will not** resolve parameters on that constructor.

Example of what to avoid when Spring owns the entire constructor:

```java
@Autowired
MyTest(ShippingPolicy policy, TestInfo testInfo) {
    // Spring attempts to resolve TestInfo in this constructor as well.
}
```

This is a conceptual illustration, not a standalone class. If the context has no `TestInfo` bean, instantiating the test object can fail. When you need `TestInfo`, it is simpler to accept it on a JUnit method:

```java
@Test
void usesTestInfo(TestInfo info) {
    assertFalse(info.getDisplayName().isBlank());
}
```

The second snippet belongs inside a test class and needs imports for `org.junit.jupiter.api.TestInfo`, `org.junit.jupiter.api.Test`, and `assertFalse`. JUnit provides `TestInfo` to method parameters; there is no need to turn it into a Spring bean.

If a constructor is **not** in `ALL` mode, you can place `@Autowired` on **a specific parameter** and let JUnit handle other parameters via its own resolvers. Still, keeping Spring dependencies in the constructor and JUnit metadata in `@BeforeEach` or `@Test` is generally easier to maintain.

### Version and Default Configuration

When `spring.test.constructor.autowire.mode` is not set to `all`, the default mode is `ANNOTATED`. Depending on version, the setting can be configured via system properties, `SpringProperties`, or JUnit Platform configuration parameters. Declare `@TestConstructor(ALL)` explicitly on the test class when you want clear behavior independent of machine/CI global settings.

With Spring Framework 7.0, `SpringExtension` requires JUnit Jupiter 6.0 or higher; Spring Boot projects usually manage compatible version sets. Therefore, do not copy JUnit dependency versions carelessly from old articles into newer Spring Framework projects.

## 5. Lifecycle, Context Cache, and `@DirtiesContext`

By default, JUnit uses `@TestInstance(PER_METHOD)`: **each test method receives a new test instance**. The constructor is invoked again whenever JUnit creates a new instance, and field/setter injection runs for that instance. However, Spring TestContext normally **caches the `ApplicationContext`** by configuration. When the context is reused, singleton beans can be **the exact same object** across many tests, even though the test instances differ.

With `@TestInstance(PER_CLASS)`, JUnit shares a single test instance across multiple test methods. The constructor usually runs only once for that instance; mutable fields in the test class risk being reused unintentionally.

**Important warning:** avoid combining *constructor injection + `PER_CLASS` + `@DirtiesContext` closing the context before/after each test method*. When the context is closed and replaced, the existing test instance still holds beans injected via its constructor; the constructor does not run again, so fields can reference beans belonging to a closed context.

**Anti-pattern example to recognize**, not standalone because `SomeService` and imports depend on an application:

```java
@SpringBootTest
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
class RiskyTest {
    private final SomeService service;

    @Autowired
    RiskyTest(SomeService service) {
        this.service = service;
    }
}
```

If you truly need `PER_CLASS` together with per-method `@DirtiesContext`, **field/setter injection** allows TestContext to reinject into the instance after the context changes. More simply, keep `PER_METHOD` when using constructor injection and avoid unnecessary context closures.

`@DirtiesContext` is not a substitute for database cleanup. Closing and recreating contexts can be very expensive; clean test data, use transactions/rollbacks, or isolate fixtures instead where appropriate.

## 6. Controlling Bean and Property Sources in Spring Boot

### Missing Beans or Multiple Candidates

If a test reports a missing bean, inspect the test configuration being loaded. `@SpringJUnitConfig(ShippingTestConfig.class)` registers only beans inside `ShippingTestConfig` and its imports; it does not load the entire `@SpringBootApplication`. `@SpringBootTest` typically loads a broader context. When using a slice like `@WebMvcTest`, services or repositories outside the slice may be absent; supply appropriate mocks or beans.

When multiple beans share an interface, injecting by type can be ambiguous. Use `@Qualifier` to choose explicitly:

```java
@Autowired
PaymentTest(@Qualifier("sandboxGateway") PaymentGateway gateway) {
    this.gateway = gateway;
}
```

This is an illustrative snippet in a test assuming type `PaymentGateway`, field `gateway`, and a bean named `sandboxGateway`; it needs `@Autowired` and `@Qualifier` imports and cannot run standalone.

### Property Configuration

In the complete example, `@TestPropertySource(properties = "app.currency=VND")` sets a specific property read by the constructor with `@Value`. In a real Spring Boot project, you can also use `@ActiveProfiles("test")` with `src/test/resources/application-test.yml`, `@DynamicPropertySource` for dynamic values from Testcontainers, or mechanisms supported by your Spring Boot version.

Confirm which profiles and properties the test actually loads. If `app.currency` is missing, `@Value` will not invent a value; the test can fail while creating the context or test instance. Avoid accidentally using production database configurations or secrets when tests only need fixtures.

### Mockito Mocks vs. Spring Bean Mocks

Mockito's `@Mock` creates a mock object in test scope, but **does not register it in the `ApplicationContext` by default**. When you want to replace a bean inside a Spring context, use the version-appropriate mechanism such as `@MockitoBean` (newer Spring Framework) or `@MockBean` in older Spring Boot projects. Check actual dependency versions and imports; do not apply an annotation from an outdated article and assume the context is configured right.

## 7. Injecting Dependencies Directly into Test Methods

SpringExtension also supports parameter injection on eligible JUnit Jupiter methods, not only constructors:

```java
@Test
void shippingRuleWorks(@Autowired ShippingPolicy policy) {
    assertEquals(0L, policy.feeVnd(500_000L));
}
```

This snippet is a **method placed inside a test class that registers SpringExtension and loads a `ShippingPolicy` bean**, requiring imports for `@Test`, `@Autowired`, and `assertEquals`. Method parameter injection is useful when a dependency is only used in one test. If many methods share a bean, constructor or field injection usually communicates that more clearly.

On `@BeforeEach` and `@AfterEach`, SpringExtension can also resolve recognized Spring parameters. When combining `@ParameterizedTest` with Spring parameters, distinguish which parameters JUnit supplies from `@CsvSource`/`@MethodSource` and which ones Spring supplies; avoid resolver conflicts. `@Nested` classes can also inherit outer Spring configuration under `@NestedTestConfiguration` modes, though each nested group **does not automatically get a brand-new context**.

## 8. Choosing the Test Style by Scope of Evidence

Having DI does not mean a test has verified every boundary:

| Goal | Usually Suitable Choice |
|---|---|
| Pure logic without Spring beans | Plain JUnit + `new`; fastest and clearest |
| Verify a small bean config and test injection | `@SpringJUnitConfig` with a concise test config |
| Verify auto-configuration and bean collaboration of a Spring Boot app | `@SpringBootTest` |
| Verify MVC requests/status/validation/JSON | `@WebMvcTest` + `MockMvc` and configured collaborators |
| Verify JPA mappings/queries | `@DataJpaTest` or integration test with a suitable database |
| Need a dependency in just one test method | `@Autowired` method parameter or clearly scoped field |

When testing a small formula, booting `@SpringBootTest` just to obtain the bean is unnecessary overhead. Conversely, a unit test injecting a mocked repository into a service does not prove real queries work. Scope selection always depends on **which bugs need to be caught**.

## 9. Common Errors

| Symptom | Likely Cause | What to Check |
|---|---|---|
| `@Autowired` field stays `null` | Test lacks SpringExtension or injection listener was excluded | Check integration annotations and `@TestExecutionListeners` |
| `ParameterResolutionException` | Constructor parameter has no matching resolver | Use `@Autowired` on constructor, `@TestConstructor(ALL)`, or proper parameter annotations |
| `NoSuchBeanDefinitionException` | Test context lacks the bean to inject | Check `@SpringJUnitConfig`, `@SpringBootTest`, profiles, bean definitions |
| `NoUniqueBeanDefinitionException` | Multiple beans of the same type | `@Qualifier`, `@Primary`, or explicit bean selection config |
| `@Value` fails to resolve | Property was not loaded | `@TestPropertySource`, profiles, or proper test properties |
| Constructor accepting `TestInfo` fails under Spring `ALL` mode | Spring owns the whole constructor, leaving no room for other resolvers | Move `TestInfo` to the method or use parameter-level injection |
| Cannot inject bean into a `final` field | Field injection runs after construction | Use constructor injection with `final` |
| Later test fails with a closed context | `PER_CLASS` + constructor injection + per-method `@DirtiesContext` | Choose `PER_METHOD` or field/setter injection with reinjection |
| Suite runs slowly | Loading full context, overusing `@DirtiesContext`, varying configs too often | Use small contexts, reuse configs, keep state isolated |
| Test passes "green" while only checking bean != null | Assertions do not prove behavior | Invoke bean methods and verify outputs as shown in the example |

If you customize `@TestExecutionListeners`, do not accidentally drop `DependencyInjectionTestExecutionListener`. When adding a listener, use the proper merge mode rather than replacing all default listeners.

## 10. Checklist Before Completing a DI-Based Test

- [ ] I know **why this test needs a Spring context**; if it does not, I use a plain unit test.
- [ ] The test registers `SpringExtension` directly or through an appropriate annotation.
- [ ] Beans, qualifiers, profiles, and properties all come from an explicit test configuration.
- [ ] Field/setter injection happens after JUnit constructs the instance; I do not try to inject into `final` fields that way.
- [ ] Constructor injection has `@Autowired`, `@TestConstructor(ALL)`, or an equivalent parameter recognition mechanism.
- [ ] When Spring owns the entire constructor, I do not expect another JUnit resolver to handle parameters there.
- [ ] I distinguish `PER_METHOD`/`PER_CLASS` lifecycle from Spring context caching.
- [ ] I avoid constructor injection holding stale beans when `@DirtiesContext` closes the context between test methods.
- [ ] When multiple beans share a type, `@Qualifier` or explicit selection is declared.
- [ ] The test verifies **behavior and results**, not merely bean existence.
- [ ] Verified that the build tool discovers the tests and Spring/JUnit dependencies are compatible.

**Remember:** JUnit creates and runs the test instance; Spring TestContext supplies beans from the `ApplicationContext`. **Field/setter injection** assigns beans after the object is created; **constructor injection** receives beans right at instantiation, supporting `final` dependencies. Base your choice on test intent, Spring context scope, and execution lifecycle.

### Official Documentation

- [Spring Framework — Dependency Injection of Test Fixtures](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/fixture-di.html)
- [Spring Framework — SpringExtension and Constructor Injection](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/support-classes.html)
- [Spring Framework — JUnit Jupiter Integration Annotations](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-junit-jupiter.html)
