# Legacy Spring Boot: `@MockBean`, `@SpyBean`, and Bean Replacement Scope in Testing

## 1. Why replace a bean in a Spring test?

In a Spring Boot application, services typically receive dependencies via constructors. For example, `CheckoutService` uses `PaymentGateway`, `DiscountPolicy`, and a repository. Running tests with all real beans might cause a call to hit a database, send an email, or invoke a payment API. Conversely, creating fake objects for everything means the test does not verify the Spring wiring and logic we want to keep.

Two annotations from **legacy Spring Boot** address this need for controlled replacement:

- **`@MockBean`**: puts a **Mockito mock** into the test `ApplicationContext`; it can replace an existing bean or add a mock bean when no matching candidate exists.
- **`@SpyBean`**: creates a **Mockito spy** to wrap a context bean, preserving real behavior when unstubbed while allowing observation and selective call replacement.

A common point of confusion is that `@MockBean` is **different** from `@Mock`. Mockito's `@Mock` only creates a mock object in the test; it does not automatically place that object into the Spring context. In contrast, `@MockBean` creates/registers a mock at the bean level so Spring-injected services use that same mock.

This lesson focuses on Spring Boot **1.4–3.3** and the **3.4–3.5** transition. Starting with Spring Boot **3.4.0**, `@MockBean` and `@SpyBean` are marked deprecated in favor of Spring Framework 6.2's `@MockitoBean` and `@MockitoSpyBean`. **Spring Boot 4.x** removes the legacy annotations. The runnable code in this lesson uses **Java 17 + Spring Boot 3.3.0** so APIs, imports, and dependencies share a consistent baseline.

Lesson objectives:

1. Choose between full mocks and partial spies based on the test contract.
2. Understand bean replacement rules by type/name/qualifier, missing-bean cases, and multiple-bean cases.
3. Use `@MockBean` within `@WebMvcTest` and `@SpringBootTest` at the proper scope.
4. Know how to stub spies safely, handle Spring AOP proxies, and avoid unintended side effects.
5. Understand Mockito reset, Spring TestContext caching, and shared state.
6. Write tests that actually prove behavior rather than mocking away the component under test.
7. Distinguish incompatible differences when upgrading from legacy Boot to Spring Framework bean overrides.

## 2. Three commonly confused levels of mocking

Consider the service:

```java
@Service
class CheckoutService {
    private final PaymentGateway gateway;

    CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    String checkout(String orderId, long amount) {
        return gateway.charge(orderId, amount);
    }
}
```

This is a **structural example**; declaring `PaymentGateway` and Spring imports is required to run it. There are three setup approaches:

| Approach | Where does the mock object live? | When is it appropriate? |
| --- | --- | --- |
| `PaymentGateway gateway = mock(PaymentGateway.class)` | Local variable, not a Spring bean | Unit tests instantiating the service with `new CheckoutService(gateway)` |
| `@Mock PaymentGateway gateway` | Test field initialized by Mockito/extension | Mockito unit tests, or tests with manual setup |
| `@MockBean PaymentGateway gateway` | Bean in the **Spring test ApplicationContext**, also injected into the field | Tests where a real Spring-managed service/controller must receive a mock gateway |

Conceptual bug example:

```java
@SpringBootTest
class BrokenTest {
    @Autowired
    CheckoutService service;

    @Mock
    PaymentGateway gateway;

    @Test
    void test() {
        when(gateway.charge("ORD-42", 100L))
                .thenReturn("TX-42");
        // service may still hold the REAL gateway from ApplicationContext.
    }
}
```

This is a **counter-example snippet**, not a complete test. Even if the `@Mock` field is initialized by Mockito, it still **does not automatically replace the bean** held inside `service`.

Fix it by using `@MockBean` on the gateway if the goal is to run the Spring context, or remove `@SpringBootTest` and construct the service via its constructor with the mock if only a unit test is needed.

```text
JUnit + @Mock:
 test field ------> mock A
 Spring context --> CheckoutService --> gateway B

Spring Boot + @MockBean:
 test field -------+
                   |
 Spring context --> mock A
      |
      +--> CheckoutService --> mock A
```

## 3. Nature and scope of `@MockBean`

### 3.1. Registering a Mockito mock as a Spring bean

Spring Boot 3.3 provides `org.springframework.boot.test.mock.mockito.MockBean`. On a **field**:

```java
@MockBean
PaymentGateway gateway;
```

The framework infers the bean type from the field, registers a Mockito mock, and injects that mock back into the field. If there is **one matching bean** of this type, Boot replaces that bean in the test context. If no matching bean exists yet, Boot can add a new mock bean. This is convenient in slice tests, though it can also mask configuration bugs if you assume an existing bean was replaced.

On a **class**, the type must be specified explicitly:

```java
@SpringBootTest
@MockBean(PaymentGateway.class)
class PaymentIntegrationTest {
    @Autowired
    PaymentGateway gateway;
}
```

This is not standalone test code since it still needs `@Test` and an application class. Legacy `@MockBean` supports repetition at the class level:

```java
@MockBean(PaymentGateway.class)
@MockBean(EmailGateway.class)
@SpringBootTest
class CheckoutIntegrationTest {
    // Both PaymentGateway and EmailGateway become mocks.
}
```

Declaring `EmailGateway` here is illustrative. Do not mock the service under test itself if real business logic needs to execute.

### 3.2. Distinguishing bean replacement by type vs. bean name

Suppose the context has two `PaymentGateway` implementations: `bankGateway` and `sandboxGateway`. Mocking by type alone may fail to disambiguate candidates or miss the bean the service actually injects. In that case, specify the name explicitly:

```java
@MockBean(name = "bankGateway")
PaymentGateway gateway;
```

Or use a qualifier on the field:

```java
@MockBean
@Qualifier("bankGateway")
PaymentGateway gateway;
```

These two approaches are **alternatives**, not meant to be mandatory together. The bean name must be verified from actual configuration, such as `@Component("bankGateway")` or a `@Bean` method name. If the service injects `@Qualifier("sandboxGateway")`, replacing `bankGateway` may **fail to isolate** the call the test intends to control.

### 3.3. Attributes in the legacy API

| `@MockBean` Attribute | Purpose |
| --- | --- |
| `value` / `classes` | Types to mock, commonly used at the class level |
| `name` | Specific bean name to replace or register |
| `answer` | Mockito default answer |
| `extraInterfaces` | Additional interfaces the mock implements |
| `serializable` | Requests a serializable mock |
| `reset` | Chooses `MockReset.BEFORE`, `AFTER`, or `NONE` |

These are **legacy Boot** attributes. When migrating to Framework's `@MockitoBean`, do not assume each attribute has a counterpart with the same name or behavior.

### 3.4. Unstubbed mocks do not run real code

On an unstubbed mock, methods return Mockito default values: typically `null` for references, `0` for primitive numbers, and `false` for booleans, depending on the return type and default answer. If a service requires a transaction ID but the mock gateway was not stubbed, a `null` can trigger downstream failures. That is mock behavior, not proof that the real production service returns null.

Stub the appropriate data for the test and **verify important arguments**. If a 100,000 order subtotal is discounted to 90,000, verifying `charge("ORD-42", 90_000L)` is far more useful than `charge(anyString(), anyLong())`.

## 4. Nature and scope of `@SpyBean`

### 4.1. A spy wraps a real object

`@SpyBean` uses a Mockito spy rather than a pure mock. When unstubbed, called methods can run real logic:

```java
@SpyBean
DiscountPolicy discountPolicy;
```

In a Spring Boot test, if Spring has a `DiscountPolicy` bean, calling `discountPolicy.payable(100_000L)` executes the real algorithm—for instance returning 90,000. This differs sharply from `@MockBean DiscountPolicy`, which returns `0L` by default if unstubbed.

```text
@MockBean:
  test/service --> Mockito mock --> stubs / default answer

@SpyBean:
  test/service --> Mockito spy --> is method stubbed?
                                   | Yes -> return stub
                                   | No -> call real method
```

### 4.2. When should you use a spy?

A spy fits when you:

- Want to **keep real business logic** of a service or policy while observing a meaningful call.
- Need to override a single branch of a class whose remaining logic is valuable.
- Need to verify how real beans collaborate while controlling one hard-to-reproduce point.

A spy is unsuitable if the real method touches a **production database**, payments, email, network, or causes uncontrolled side effects. In those scenarios, mocking the outbound gateway or setting up a dedicated integration test environment is clearer.

### 4.3. Stubbing a spy safely

With a Mockito spy:

```java
doReturn(77_000L)
        .when(discountPolicy)
        .payable(100_000L);
```

`doReturn(...).when(spy).method(...)` avoids calling the real method **during the stubbing step itself**. The alternative pattern:

```java
when(discountPolicy.payable(100_000L))
        .thenReturn(77_000L);
```

can invoke the real method before registering the stub. For a pure function with no side effects, the second style might appear harmless, but for a method touching DB/network or mutating state, it is dangerous.

**Rule:** when using a spy, prefer `doReturn`/`doThrow`/`doAnswer` for methods that risk side effects. Never make a test pass by silently executing production logic during the Arrange step.

### 4.4. Legacy `@SpyBean` handles missing beans differently from the new Framework API

Spring Boot 3.3 Javadoc describes attaching spies by type/name and includes a mechanism to **add a bean when no matching bean exists**. Do not rely on that behavior in place of verifying whether production configuration actually defines the real bean.

By contrast, Spring Framework 6.2+ `@MockitoSpyBean` uses the **WRAP** strategy, requiring **exactly one existing singleton bean** to wrap. During an upgrade, an older test that accidentally relied on the legacy annotation creating a bean may begin failing at context bootstrap; that is a configuration issue to fix, not just an annotation rename.

## 5. Runnable example: Spring Boot 3.3.0 + Java 17

The following example is a small Spring Boot project **with no web or database layer**. It checks Spring wiring, keeps `CheckoutService` and `DiscountPolicy` running for real, and replaces `PaymentGateway` with a mock. The spy portion keeps the real policy or selectively stubs a single decision.

### 5.1. Project structure

```text
legacy-bean-test/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/
    │   ├── ShopApplication.java
    │   ├── PaymentGateway.java
    │   ├── DemoPaymentGateway.java
    │   ├── DiscountPolicy.java
    │   └── CheckoutService.java
    └── test/java/example/
        ├── CheckoutMockBeanTest.java
        └── CheckoutSpyBeanTest.java
```

### 5.2. Gradle build

**`settings.gradle`:**

```groovy
rootProject.name = 'legacy-bean-test'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The project needs a compatible Gradle Wrapper, such as Gradle 8.5 with Boot 3.3 and Java 17. Version 3.3.0 is pinned so legacy examples do not get mixed with Boot 4 imports. In real systems, use the Boot/Java/Gradle versions supported by your project and an appropriate maintenance release.

### 5.3. Application and real beans

**`src/main/java/example/ShopApplication.java`:**

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

**`src/main/java/example/PaymentGateway.java`:**

```java
package example;

public interface PaymentGateway {
    String charge(String orderId, long amountInVnd);
}
```

**`src/main/java/example/DemoPaymentGateway.java`:**

```java
package example;

import org.springframework.stereotype.Component;

@Component
public class DemoPaymentGateway implements PaymentGateway {
    @Override
    public String charge(String orderId, long amountInVnd) {
        return "DEMO-" + orderId;
    }
}
```

This adapter returns dummy data in-memory without performing real payments. In a real application, `PaymentGateway` typically represents an external gateway that must be isolated in service tests.

**`src/main/java/example/DiscountPolicy.java`:**

```java
package example;

import org.springframework.stereotype.Component;

@Component
public class DiscountPolicy {
    public long payable(long subtotal) {
        if (subtotal <= 0L) {
            throw new IllegalArgumentException(
                    "subtotal must be positive");
        }
        return subtotal >= 100_000L
                ? subtotal - 10_000L
                : subtotal;
    }
}
```

This illustrative policy deducts 10,000 VND if subtotal is at least 100,000 VND; non-positive amounts are rejected.

**`src/main/java/example/CheckoutService.java`:**

```java
package example;

import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    public record Receipt(
            String orderId,
            long chargedAmount,
            String transactionId) {}

    private final PaymentGateway gateway;
    private final DiscountPolicy policy;

    public CheckoutService(
            PaymentGateway gateway,
            DiscountPolicy policy) {
        this.gateway = gateway;
        this.policy = policy;
    }

    public Receipt checkout(String orderId, long subtotal) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                    "orderId must not be blank");
        }

        long amount = policy.payable(subtotal);
        String transactionId = gateway.charge(orderId, amount);
        return new Receipt(orderId, amount, transactionId);
    }
}
```

`@SpringBootApplication` in package `example` lets component scanning locate `DemoPaymentGateway`, `DiscountPolicy`, and `CheckoutService`. Constructor injection ensures the service receives the beans present in the context.

### 5.4. Test A — replacing the gateway with `@MockBean`

**`src/test/java/example/CheckoutMockBeanTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@SpringBootTest(
        classes = ShopApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class CheckoutMockBeanTest {
    @Autowired
    CheckoutService checkout;

    @Autowired
    ApplicationContext context;

    @MockBean
    PaymentGateway gateway;

    @Test
    void replacesGatewayButRunsRealServiceAndPolicy() {
        when(gateway.charge("ORD-42", 90_000L))
                .thenReturn("TX-42");

        CheckoutService.Receipt receipt =
                checkout.checkout("ORD-42", 100_000L);

        assertEquals("ORD-42", receipt.orderId());
        assertEquals(90_000L, receipt.chargedAmount());
        assertEquals("TX-42", receipt.transactionId());
        assertSame(gateway, context.getBean(PaymentGateway.class));

        verify(gateway).charge("ORD-42", 90_000L);
    }

    @Test
    void rejectsBlankOrderWithoutCallingGateway() {
        assertThrows(IllegalArgumentException.class,
                () -> checkout.checkout(" ", 100_000L));
        verifyNoInteractions(gateway);
    }
}
```

Each assertion proves something specific:

- `chargedAmount==90000`: the real `DiscountPolicy` applied the discount rule properly.
- `transactionId=="TX-42"`: the service used the stubbed result from the mock gateway.
- `assertSame(gateway, context.getBean(PaymentGateway.class))`: the mock field and the bean injected in the context are the exact same instance.
- `verify(..., 90000)`: the gateway received the exact amount calculated by the service.
- On the invalid input path, the gateway is never called.

This test does not prove HTTP endpoints, database commits, or external payment protocols because those components are not built into the demo application.

### 5.5. Test B — spying the real policy, mocking the external gateway

**`src/test/java/example/CheckoutSpyBeanTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.boot.test.mock.mockito.SpyBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringBootTest(
        classes = ShopApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class CheckoutSpyBeanTest {
    @Autowired
    CheckoutService checkout;

    @MockBean
    PaymentGateway gateway;

    @SpyBean
    DiscountPolicy policy;

    @Test
    void spyCallsRealPricingMethodByDefault() {
        when(gateway.charge("ORD-7", 90_000L))
                .thenReturn("TX-7");

        CheckoutService.Receipt result =
                checkout.checkout("ORD-7", 100_000L);

        assertEquals(90_000L, result.chargedAmount());
        assertEquals("TX-7", result.transactionId());
        verify(policy).payable(100_000L);
        verify(gateway).charge("ORD-7", 90_000L);
    }

    @Test
    void spyCanReplaceOnePricingDecision() {
        doReturn(77_000L).when(policy).payable(100_000L);
        when(gateway.charge("ORD-8", 77_000L))
                .thenReturn("TX-8");

        CheckoutService.Receipt result =
                checkout.checkout("ORD-8", 100_000L);

        assertEquals(77_000L, result.chargedAmount());
        assertEquals("TX-8", result.transactionId());
        verify(policy).payable(100_000L);
        verify(gateway).charge("ORD-8", 77_000L);
    }
}
```

The first test keeps the real policy logic; the second stubs only `payable(100000)` to simulate a special decision. Both still use the mock gateway, so no external payment side effects occur.

**Note:** `@SpyBean` normally resets Mockito interactions/stubs per test, but if `DiscountPolicy` itself holds mutable state, resetting the spy will not restore that data automatically. The policy in this example is stateless, so that issue does not arise.

### 5.6. Running and expected results

In the project directory with a suitable Gradle Wrapper:

```bash
./gradlew test
./gradlew test --tests example.CheckoutMockBeanTest
./gradlew test --tests example.CheckoutSpyBeanTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.CheckoutSpyBeanTest
```

Expected outcome: **4 test methods pass**; Gradle reports `BUILD SUCCESSFUL` when tests and build tasks succeed with no errors. There is no fixed business stdout; Boot log lines and task counts depend on the environment.

The example has no HTTP or database layer, so no container runtime or API keys are needed. If copied into an existing project, beans with conflicting names or unintended auto-configuration may appear; compare against this minimal setup.

## 6. Comparing mock, spy, and real beans by contract

| What you want to prove | Appropriate setup | Valuable assertion |
| --- | --- | --- |
| Service does not call gateway on invalid input | Real service + mock gateway | Exception/error and `verifyNoInteractions` |
| Service calculates the right amount | Real service and policy + mock gateway | Returned amount and argument sent to gateway |
| Controller maps URL and JSON properly | `@WebMvcTest` + mock service | HTTP status, JSON fields |
| Policy calculates boundary values accurately | Plain JUnit or real policy bean | Input/output table at thresholds |
| Observe how many times real service calls policy | Spy policy if call count is part of contract | `verify(spy)` alongside outcome |
| Repository actually persists data | Real repository/DB | Query reading back persisted row |
| Outbound HTTP uses correct method/headers/body | Protocol-level HTTP mock server | Request wire contract |
| Security filter rejects unauthorized access | Appropriate security test context | 401/403 + no forbidden effect |

**Do not mock the class whose logic is under test.** A test with `@MockBean DiscountPolicy` stubbed to return 90000 does not verify the discount rule; it only proves Mockito returns the configured value. A service unit test using `new DiscountPolicy()` is stronger and faster for that purpose.

## 7. Scope of `@MockBean` in `@WebMvcTest`

In Spring Boot 2.x/3.3, `@WebMvcTest` loads the MVC slice: controllers, MVC infrastructure, and certain web-related beans, while typically **not loading regular services**. Controllers need service beans, making `@MockBean` very common here.

```java
@WebMvcTest(OrderController.class)
class OrderControllerWebTest {
    @Autowired
    MockMvc mvc;

    @MockBean
    OrderService orders;

    @Test
    void serializesOrderStatus() throws Exception {
        when(orders.find("ORD-42"))
                .thenReturn(new OrderView("ORD-42", "PAID"));

        mvc.perform(get("/orders/ORD-42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("PAID"));
    }
}
```

This is an **illustrative MVC skeleton** requiring `OrderController`, `OrderService`, `OrderView`, and application imports. It proves routing/status/JSON against a mocked service response, **not** service logic or persistence.

A common mistake is switching to `@SpringBootTest` simply because `@WebMvcTest` cannot find a service. If the goal is only the web contract, supply a mock service appropriate for the slice; if you want an end-to-end flow with multiple real beans, move intentionally to an integration test.

## 8. Scope in `@SpringBootTest` and other slices

`@SpringBootTest` loads the Boot context, suitable when checking real bean configuration or multi-layer interaction. In that case, `@MockBean` should only replace dependencies **outside the verification target**, such as remote clients or email gateways.

```text
@SpringBootTest
  real controller (if any)
     |
  real checkout service
     |                   |
  real discount         mock payment gateway
     |
  real repository (if the target includes persistence)
```

With `@DataJpaTest`, the target is entities/repositories/queries, so do not mock the repository under test. You may mock an auxiliary collaborator if the slice genuinely needs it. Similarly, in WebFlux, Security, or batch tests, understand **which beans the slice scans** before adding mocks.

**Replacement scope:** `@MockBean`/`@SpyBean` affect the context requested by the test, rather than mutating global production bean definitions. Different test contexts can have different mock sets and therefore distinct cache keys.

## 9. Context initialization order and late stubbing issues

In standard Boot tests, the `ApplicationContext` is refreshed **before `@Test` methods run**. If a bean calls a remote client inside `@PostConstruct` or during context refresh, a stub configured in `@BeforeEach` or `@Test` will be registered **after** that initialization call.

```text
Spring test context startup
    |
    +--> create beans
    +--> @PostConstruct / initialization
    |       +--> calls PaymentGateway
    |
    +--> inject @MockBean field into test instance
    |
JUnit @BeforeEach / @Test
    +--> when(gateway.charge(...)).thenReturn("TX-42")
          ^ too late for calls during context startup
```

Boot 3.3 documentation notes this limitation with `@MockBean`. If you must control behavior **during context refresh**, consider creating a pre-stubbed mock via a test `@Bean` in an appropriate `@TestConfiguration`, or redesigning so bean initialization does not invoke external systems. Do not simply add `@MockBean` and expect earlier startup calls to replay.

## 10. Mock/spy reset and context cache

### 10.1. Default `AFTER` reset

Legacy Boot annotations offer `reset` with modes `MockReset.BEFORE`, `MockReset.AFTER`, and `MockReset.NONE`. The default is **`AFTER`**, meaning the Boot test infrastructure resets Mockito stubs/interactions after each test method.

```java
@MockBean(reset = MockReset.AFTER)
PaymentGateway gateway;
```

This is a **syntax example** requiring `import org.springframework.boot.test.mock.mockito.MockReset`. With `@SpyBean`, the `reset` option works similarly.

**Resetting does not close and recreate the ApplicationContext.** The context may be cached and reused; the mock object stays in the context while its interactions/stubs are cleared. A real singleton containing a `Map` or counter retains its state after reset; clean up state with fixtures or stateless design.

### 10.2. Impact on context cache

Spring TestContext caches contexts by configuration set. `@MockBean`/`@SpyBean` participate in context customization and cache keys; two tests with different mock/spy lists can create **two contexts**. This slows down the suite if every test class replaces dozens of different beans.

Sensible optimizations:

- Use plain unit tests when Spring is unnecessary.
- Only mock/spy beans at boundaries you actually need to control.
- Keep test configurations consistent where possible.
- Avoid abusing `@DirtiesContext` just to reset Mockito.
- Keep test data and mutable singleton state independent of the context cache.

### 10.3. Reset and test ordering

Never write test B assuming test A ran first to set up or clean up data. When proving that invalid input does not call the gateway, `verifyNoInteractions(gateway)` is valid **for that scenario itself**, without relying on other tests.

## 11. Spring AOP proxies, spies, and caveats

A bean annotated with `@Transactional`, `@Cacheable`, `@PreAuthorize`, or other advice may be wrapped by Spring in a proxy. When spying on such a bean, the **proxy** and **target** can differ; `Mockito.verify` or `when` may act on an unexpected object.

In Spring Boot 3.3, legacy `@SpyBean` provides the `proxyTargetAware` attribute (default `true`) so Mockito APIs like `verify` operate against the target for AOP-advised beans. In special cases, Boot docs mention `AopTestUtils.getTargetObject(...)` or `getUltimateTargetObject(...)` to access the target.

Before fixing an AOP spy test, ask: does the behavior you need to prove live on the **call through the proxy** or on the **real method**? If the goal is testing transaction/security/cache advice, accidentally calling the target directly can bypass advice and yield a misleading green test.

Also note `@Cacheable` expressions referencing parameter names: Spring Boot 3.3 recommends compiling with `-parameters` when spying beans with such methods so caching infrastructure can read parameter names. Do not assume every cache failure after adding a spy is a Mockito bug.

## 12. Bean name, scope, and container registry issues

### 12.1. Beans of the same type

If the context has multiple beans implementing the same interface, `@MockBean PaymentGateway` can report ambiguous candidates or replace an unintended bean. Use a bean `name` or `@Qualifier` matching the dependency the real service injects.

### 12.2. Objects that are not actual Spring beans

`@MockBean` only replaces beans inside the context. An instance created with `new` or held in a static field outside IoC is not automatically replaced. Legacy Spring Boot Javadoc also distinguishes dependencies **registered directly without a bean definition**: a mock may be added alongside the existing dependency rather than replacing that reference.

### 12.3. Scopes and proxies

Prototype, request/session-scoped beans, or `FactoryBean`s have specific nuances; do not assume every object is a regular singleton. When adopting the new Framework API, bean overrides target **singletons**, and spies require exactly one existing bean. When migrating from legacy annotations, verify scopes and `BeanFactory`/`FactoryBean` behavior in your target version's Javadoc.

### 12.4. Do not patch over issues with global bean overriding

Some applications disable overriding bean names. Never enable global bean-definition overriding just to push tests past an uninvestigated configuration error. Use dedicated bean override mechanisms, `@TestConfiguration`, or targeted test profiles and inspect the actual candidates.

## 13. Version timeline: when to use the legacy API vs. when to migrate

| Release line | Status | How to handle |
| --- | --- | --- |
| Spring Boot 1.4–2.x | Has `@MockBean` and `@SpyBean` | Use the imports/test runners/BOM for that line |
| Spring Boot 3.0–3.3 | Legacy API remains standard | The Boot 3.3 examples in this lesson apply |
| Spring Boot 3.4–3.5 | Legacy API present but **deprecated for removal** since 3.4 | Begin migrating to Spring Framework 6.2+ annotations |
| Spring Boot 4.x | Legacy `org.springframework.boot.test.mock.mockito` API removed | Use Framework's `@MockitoBean` and `@MockitoSpyBean` |

Imports:

```java
// Spring Boot 3.3 and earlier:
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.boot.test.mock.mockito.SpyBean;

// Spring Framework 6.2+ (Boot 3.4+), Framework 7.x (Boot 4.x):
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
```

These are **version-specific alternatives**; do not mix both annotation sets in the same test for the same bean without understanding the override strategy.

**Do not use Spring Framework 6.2 annotations in a Boot 3.3 project managing Spring Framework 6.1.x** by forcing individual artifact versions. Upgrade the entire Boot BOM in a compatible combination and then update imports.

## 14. Key differences when switching to `@MockitoBean` and `@MockitoSpyBean`

| Aspect | Legacy Boot | Framework 6.2+ |
| --- | --- | --- |
| Mock bean annotation | `@MockBean` | `@MockitoBean` |
| Spy bean annotation | `@SpyBean` | `@MockitoSpyBean` |
| Class-level type declaration | `@MockBean(PaymentGateway.class)` | `@MockitoBean(types = PaymentGateway.class)` |
| Missing mock bean | Can add a new mock | Defaults to `REPLACE_OR_CREATE`; supports `enforceOverride = true` to require an existing bean |
| Missing spy bean | Legacy had conditional creation paths | `WRAP` requires exactly one existing singleton bean |
| Bean selection | Type/name/qualifier via legacy rules | Type/name/field qualifier with field-name fallback; be mindful of cache keys |
| Context hierarchy | Legacy-specific mechanism | `contextName` to target a specific level |
| Reset enum | `org.springframework.boot.test.mock.mockito.MockReset` | `org.springframework.test.context.bean.override.mockito.MockReset` |
| Other attributes | `answer`, `extraInterfaces`, `serializable`, `proxyTargetAware`... | Do not assume 1-to-1 equivalents |

A seemingly simple upgrade:

```java
// Legacy:
@MockBean
PaymentGateway gateway;

@SpyBean
DiscountPolicy policy;

// New (Framework 6.2+, when bean and scope are valid):
@MockitoBean
PaymentGateway gateway;

@MockitoSpyBean
DiscountPolicy policy;
```

This is an illustrative snippet, **not a standalone test class**. If the old `@SpyBean` silently added a policy when the application lacked a policy bean, the new `@MockitoSpyBean` will fail: you must register the real bean or switch the target to a mock.

When it matters that an **existing bean must be replaced**, `@MockitoBean(enforceOverride = true)` catches missing type/name matches early. It also prevents old tests from passing by silently creating a mock even when production wiring is broken.

The newer Spring Framework also has AOP proxy differences for `REPLACE`/`WRAP` strategies; verify transactions, caching, and method security across the proper proxy boundaries. Do not treat compilation alone as proof that migration is complete.

## 15. Migration workflow for legacy Boot tests

1. **Lock down versions:** Boot, Framework, JDK, Maven/Gradle, `spring-boot-starter-test`, and dependency management.
2. **Inventory each usage:** web slice mocks, outbound gateway mocks, bean spies, class-level mocks, bean names/qualifiers, custom reset, AOP proxies.
3. **Upgrade to a compatible BOM:** Boot 3.4+ supports Framework 6.2; Boot 4 uses the newer Framework API and technology-specific test starters.
4. **Update imports/annotations:** `@MockBean` → `@MockitoBean`, `@SpyBean` → `@MockitoSpyBean`, class-level `classes` → `types` per the new API.
5. **Verify bean existence:** spies require an existing singleton bean; for mocks where the test requires a real bean to exist, use `enforceOverride=true`.
6. **Audit attributes:** `reset`, `name`, qualifiers, and legacy attributes without direct equivalents.
7. **Run tests layer by layer:** compile tests, JUnit unit tests, MVC/JPA slices, `@SpringBootTest`, and database/HTTP integration tests.
8. **Verify behavior:** actual HTTP/body/state/events, not just Mockito verify calls.
9. **Check context overhead:** whether distinct context counts increased due to qualifiers/bean overrides.
10. **Sign off migration with test counts and results:** test discovery has not dropped and key tests still protect contracts.

**Boot 4 warning:** do not only rename annotations—also review technology-specific test starters/modules, `@WebMvcTest`/`@DataJpaTest` packages, and other APIs. Do not pull Boot 3.x artifacts into a Boot 4 BOM just to keep a legacy import alive.

## 16. Common error troubleshooting table

| Symptom | Potential cause | How to check/fix |
| --- | --- | --- |
| Mock field accepts stub, but service runs real code | Used `@Mock` instead of `@MockBean`, or service created outside context | Verify same Spring bean/instance |
| Mockito `Wanted but not invoked` | Service uses a different bean or took another branch | Check injection, requests, and arguments |
| `NoUniqueBeanDefinitionException` | Multiple beans of same type, missing qualifier/name | Select exact bean with `@Qualifier`/`name` |
| MVC slice fails due to missing service | Slice does not auto-load regular services | `@MockBean` or intentional test configuration |
| Stub does not match; mock returns null | Argument mismatch or forgotten stub | Assert inputs and use consistent matchers |
| `InvalidUseOfMatchersException` | Mixing literals with `any`/`eq` in one invocation | If one matcher is used, every arg in the invocation needs a matcher |
| Spy invokes real method while stubbing | `when(spy.method())` executes real method during Arrange | Use `doReturn`/`doThrow` |
| Spy causes unintended side effects | Unstubbed method executes for real | Mock outbound calls or isolate infrastructure |
| Context fails during bean initialization | Test stub configured too late for startup callback | Preconfigure mock bean before refresh or redesign initialization |
| Test passes alone, fails in full suite | Unreset singleton/DB state, differing context config | Clean up fixtures and investigate cache |
| Slow suite loading many contexts | Every class defines a distinct mock/spy set | Reduce overrides and standardize configurations |
| Spy on `@Transactional` fails verify | AOP proxy vs. target mismatch | Check `proxyTargetAware`/`AopTestUtils` |
| Boot 3.4 deprecation warnings | Legacy API slated for removal | Plan migration |
| Boot 4 lacks `MockBean` | Legacy Boot API removed | Move to Framework annotations |
| `@MockitoSpyBean` reports missing bean | Framework `WRAP` requires existing singleton | Configure real bean or switch to mock |
| Test passes despite broken business logic | Mocked away the very service/repository under test | Adjust boundaries and assert real outputs/state |

Read the **first root cause** when context loading fails. A Mockito argument matcher error is fundamentally different from a missing Spring bean error; do not treat either by broadening `@SpringBootTest`.

## 17. Hands-on exercises

### Exercise 1 — Find why `@Mock` does not replace the bean

Given a test with `@Autowired CheckoutService` and a `@Mock PaymentGateway` field:

- Explain why the service may still hold the real gateway bean.
- Switch to legacy `@MockBean` in Boot 3.3.
- Stub the gateway to return `TX-42` when amount equals 90,000.
- Assert the receipt values and verify the gateway received the exact amount.

**Criteria:** do not settle for a green test; prove the mock bean in the context and the one inside the service are the same object.

### Exercise 2 — Spy a single decision

Run `CheckoutSpyBeanTest`. In the test with `doReturn(77_000L)`, temporarily replace it with `when(policy.payable(100_000L)).thenReturn(...)` in a sandbox. The pure policy may still pass. Describe why that pattern poses risks if the policy has side effects. Restore `doReturn`.

### Exercise 3 — Mock or keep the real service?

For an HTTP endpoint returning order status, compare:

- `@WebMvcTest` + mock service: evidence of web mapping/serialization.
- `@SpringBootTest` + mock gateway + real service/repository: evidence of internal business flow.
- Integration test with DB/container and HTTP mock server: evidence of transactions/persistence and wire protocol.

Write one key assertion for each level. If a database is not needed yet, do not load a DB just to reach integration level.

### Exercise 4 — Multiple implementations of one interface

Add `bankGateway` and `sandboxGateway` to the test sandbox; specify a qualifier on the service. Use `@MockBean(name = "bankGateway")` and verify the service receives the right bean. If the service uses sandbox, does mocking bank help? The answer depends on the goal, though the two beans cannot be assumed interchangeable.

### Exercise 5 — Watch caching and reset

Create a stateful singleton `Counter` and wrap it with a spy. Run two test methods. Mockito reset clears interactions, but does `Counter.value` reset to 0 automatically? Use fixture reset or redesign state so tests are independent. Do not default to `@DirtiesContext`.

### Exercise 6 — Migrate to Framework 6.2+

Take a Boot 3.3 class with:

```java
@MockBean
PaymentGateway gateway;

@SpyBean
DiscountPolicy discountPolicy;
```

Upgrade via a compatible BOM, switch to `@MockitoBean`/`@MockitoSpyBean`, and verify that the policy bean exists and is a singleton. If the old test relied on `@SpyBean` adding a new policy, migration requires fixing the design rather than just swapping imports.

## 18. Pre-completion checklist

- [ ] I know whether the Boot version in use supports `@MockBean`/`@SpyBean`.
- [ ] I distinguish Mockito `@Mock`/`@Spy` from Spring Boot bean replacement.
- [ ] I know **which real bean** is replaced, by type, name, or qualifier.
- [ ] I am not mocking the primary class whose logic needs testing.
- [ ] When using a spy, I know unstubbed methods execute real code.
- [ ] I use `doReturn`/`doThrow` when preventing real methods from running during Arrange.
- [ ] I have isolated database/network/email/payment side effects.
- [ ] I know resetting Mockito state does not reset state inside real singletons.
- [ ] I understand mocks/spies affect context cache keys and suite performance.
- [ ] When a bean uses AOP, I understand proxy vs. target and the right verification point.
- [ ] For startup callbacks, I do not assume stubs inside `@Test` retroactively affect context refresh.
- [ ] For Boot 3.4–3.5, I recognize the deprecation and have a migration plan.
- [ ] For Boot 4, I use Framework override annotations and appropriate test modules.
- [ ] When migrating a spy, I verified that exactly one singleton bean exists.
- [ ] Tests assert return values, state, or business effects properly.

## 19. Decision diagram

```text
Only want to test Java logic?
    -> JUnit + mock()/@Mock, instantiate service via constructor.

Need Spring to create/inject beans?
    |
    +-- External dependency needs to be fully mocked?
    |       -> Legacy @MockBean (Boot <= 3.3).
    |
    +-- Need to keep real logic and intercept partially?
    |       -> Legacy @SpyBean; control side effects/proxy.
    |
    +-- Only testing MVC mapping?
    |       -> @WebMvcTest + mock services outside the slice.
    |
    +-- Testing multiple internal beans?
            -> @SpringBootTest + intentionally mock outbound dependencies.

Boot >= 3.4: plan migration to Framework @MockitoBean/@MockitoSpyBean.
Boot 4: legacy Boot API removed, use new annotations.
```

Two rules to remember: **mock at the right boundary** and **never let a spy execute unintended real effects**. `@MockBean`/`@SpyBean` control beans in the test context; they do not verify business behavior on their own, make transactions/databases/networks safe, or replace observable assertions.

## 20. Official documentation by version

- Spring Boot 3.3 `@MockBean` JavaDoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/mock/mockito/MockBean.html
- Spring Boot 3.3 `@SpyBean` JavaDoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/mock/mockito/SpyBean.html
- Spring Boot 3.3 Testing Applications, “Mocking and Spying Beans”: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.4 deprecated Mockito integration: https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/mock/mockito/package-summary.html
- Spring Framework 6.2 `@MockitoBean` and `@MockitoSpyBean`: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html
- Spring Framework Bean Overrides: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/bean-overriding.html
- Spring Boot Testing (current release line): https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
- Mockito: https://site.mockito.org/
- JUnit: https://docs.junit.org/current/user-guide/
