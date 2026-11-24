# Adding a Mock When a Bean Is Missing vs. Requiring Replacement of an Existing Bean

In Spring Boot testing, **adding a mock when a context lacks a bean** and **replacing an existing bean with a mock** are two distinct intentions. A slice test may intentionally omit real adapters, making it reasonable to supply a mock. Conversely, a test verifying application wiring must catch missing beans; if a mock is auto-created, the test can pass despite broken production wiring.

Spring TestContext lets you express this explicitly with `@MockitoBean`:

- **Default `@MockitoBean`:** uses the `REPLACE_OR_CREATE` strategy — replaces a matching bean if present, or creates a new Mockito bean if absent.
- **`@MockitoBean(enforceOverride = true)`:** uses the `REPLACE` strategy — requires a matching bean to already exist in the context; if none exists, **test context initialization must fail**.
- **`@MockitoSpyBean`:** uses the `WRAP` strategy — requires an existing matching original bean to wrap in a spy; it is not a direct substitute for the two modes above.

This is a core topic in **Bean Replacement**. A passing test with default `@MockitoBean` proves the application works *inside the test context after adding the mock*; it **does not prove production actually registered that bean**.

The examples and APIs below target **Java 17+, Spring Framework 6.2+, and Spring Boot 3.4+**; for Spring Boot 4.x, use Spring TestContext annotations instead of the removed legacy `@MockBean`.

## 1. The problem to solve

Suppose an application has a service:

```text
OrderController
      |
      v
OrderNotifier  ---->  ReceiptGateway
                          |
                          v
                  Real REST/Email adapter
```

`OrderNotifier` requires `ReceiptGateway` in its constructor. This yields two valid testing goals:

**Goal A — testing service/controller logic:** you do not want to call the real receipt-sending API and may not load the adapter in a slice. The test only needs a mock `ReceiptGateway` so the service can handle requests. **Allowing mock creation when the bean is absent** is appropriate.

**Goal B — testing application configuration:** the project must have a `ReceiptGateway` adapter registered under the right profile. You still want to replace the adapter to avoid sending emails/API calls in tests, **yet if the production adapter disappears, the test must turn red**. Here, `enforceOverride = true` is mandatory in a context that actually loads the beans being verified.

A common mistake is putting `@MockitoBean` on every collaborator in `@SpringBootTest`, then concluding "Spring wiring is solid" from a green build. By default, the annotation can **hide the very missing-bean bug**.

## 2. Where does bean overriding take place?

Spring TestContext creates or customizes the `ApplicationContext` before `@Test` methods run. Bean overriding participates in bean preparation, not inside a `Mockito.when(...)` call within a test method.

Strategy table:

| Strategy | Matching bean exists | Matching bean does not exist | Meaning |
| --- | --- | --- | --- |
| `REPLACE_OR_CREATE` | Replaces bean with override instance | Creates a new bean | Permits missing bean |
| `REPLACE` | Replaces bean with override instance | Error during context preparation | Requires original bean to exist |
| `WRAP` | Wraps original bean | Cannot wrap an absent bean | Needs real bean to observe/run partial behavior |

`@MockitoBean` maps to `REPLACE_OR_CREATE` by default. Setting `enforceOverride = true` selects `REPLACE`. `@MockitoSpyBean` behaves as `WRAP` and typically requires **exactly one** matching candidate bean.

Quick comparison:

```java
@MockitoBean
ReceiptGateway gateway; // REPLACE_OR_CREATE
```

```java
@MockitoBean(enforceOverride = true)
ReceiptGateway gateway; // REPLACE, bean must exist
```

```java
@MockitoSpyBean
ReceiptGateway gateway; // WRAP, calls real method when unstubbed
```

These snippets are **mutually exclusive alternatives**; do not place all three on the same field. When using a spy, remember real methods can trigger network/database side effects.

**Decision flow:**

```text
What do you want to test?
         |
         +-- Pure logic, no Spring?
         |       --> Mockito @Mock or mock(...) + new Service(...)
         |
         +-- Slice test intentionally missing a collaborator?
         |       --> @MockitoBean (default)
         |
         +-- Bean MUST exist in the current context?
         |       --> @MockitoBean(enforceOverride = true)
         |
         +-- Real bean exists, want to keep partial real behavior?
                 --> @MockitoSpyBean when appropriate
```

## 3. How does `@Mock` differ from `@MockitoBean`?

In a plain Java unit test:

```java
@ExtendWith(MockitoExtension.class)
class OrderNotifierUnitTest {
    @Mock ReceiptGateway gateway;

    @Test
    void canSend() {
        OrderNotifier service = new OrderNotifier(gateway);
        // when(gateway.send(...)) then assert...
    }
}
```

This snippet illustrates structure and is not a standalone test since imports and assertions are omitted. Key point: `@Mock` creates a Mockito object when processed by `MockitoExtension`. It **does not register a Spring bean**. The test instantiates the service with `new` and passes the mock into the constructor.

Conversely:

```java
@SpringJUnitConfig(SomeConfig.class)
class OrderNotifierContextTest {
    @MockitoBean
    ReceiptGateway gateway;

    @Autowired
    OrderNotifier service;
}
```

This is also an illustrative snippet needing a real `SomeConfig`. `@MockitoBean` is processed by Spring TestContext, so the mock is both a Mockito object and present inside `ApplicationContext` for `OrderNotifier` to inject.

| Tool | Produces Mockito mock? | Visible to Spring context? | Requires production bean to exist? |
| --- | --- | --- | --- |
| `Mockito.mock(...)` | Yes | No | No |
| Mockito `@Mock` | Yes, when initialized properly | No | No |
| `@MockitoBean` | Yes | Yes | No |
| `@MockitoBean(enforceOverride=true)` | Yes | Yes | **Yes, in the loaded context** |
| `@MockitoSpyBean` | Spy | Yes | Requires matching bean to wrap |

Do not add `@SpringBootTest` merely to obtain a Mockito mock when testing a service via constructor injection. Equally, do not mistake `@Mock` for a Spring bean when resolving dependencies inside a context.

## 4. Complete example: one service, two strategies

**Business contract:**

- `OrderNotifier.sendReceipt(orderId)` requires a non-null, non-blank order ID.
- For valid IDs, the service calls `ReceiptGateway.send(orderId)` and returns the response string.
- The real adapter returns `real:ORD-7`.
- The test mock returns `mock:ORD-7`.
- We separate **a context declaring no gateway** from **a context with an existing gateway bean** to show the difference.

Layout:

```text
src/
├── main/java/example/testing/beans/
│   ├── OrderNotifier.java
│   └── OrderNotifierDemo.java
└── test/java/example/testing/beans/
    ├── CreateIfAbsentTest.java
    └── ReplaceExistingTest.java
```

### 4.1. Production file OrderNotifier.java

Create `src/main/java/example/testing/beans/OrderNotifier.java`:

```java
package example.testing.beans;

import java.util.Objects;

public final class OrderNotifier {
    private final ReceiptGateway gateway;

    public OrderNotifier(ReceiptGateway gateway) {
        this.gateway = Objects.requireNonNull(
                gateway, "gateway");
    }

    public String sendReceipt(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                    "orderId must not be blank");
        }
        return gateway.send(orderId);
    }
}

interface ReceiptGateway {
    String send(String orderId);
}

final class RealReceiptGateway implements ReceiptGateway {
    @Override
    public String send(String orderId) {
        return "real:" + orderId;
    }
}
```

This compiles and runs on JDK 17+: the file has exactly one top-level `public` type (`OrderNotifier`); the remaining types are package-private and accessible to tests **in the same package**. In larger projects, split interfaces/adapters into separate files with suitable visibility when referenced across packages.

The service is **not annotated with `@Service`** because both tests declare beans via `@Bean`. What matters here is not which classes Spring scans, but whether TestContext contains a `ReceiptGateway` **bean definition**. Do not accidentally add `@Component` to the adapter in Case A, as that would defeat the "missing bean in context" scenario.

### 4.2. Case A: mock created even when bean is absent

Create `src/test/java/example/testing/beans/CreateIfAbsentTest.java`:

```java
package example.testing.beans;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@SpringJUnitConfig(CreateIfAbsentTest.Config.class)
class CreateIfAbsentTest {

    // REPLACE_OR_CREATE: creates a mock if no gateway bean exists.
    @MockitoBean
    private ReceiptGateway receiptGateway;

    @Autowired
    private OrderNotifier notifier;

    @Autowired
    private ApplicationContext context;

    @Test
    void createsMockWhenGatewayBeanDoesNotExist() {
        when(receiptGateway.send("ORD-7"))
                .thenReturn("mock:ORD-7");

        String actual = notifier.sendReceipt("ORD-7");

        assertEquals("mock:ORD-7", actual);
        verify(receiptGateway).send("ORD-7");
        assertSame(receiptGateway,
                context.getBean(ReceiptGateway.class));
        assertTrue(
                Mockito.mockingDetails(receiptGateway).isMock());
    }

    @Test
    void invalidIdIsRejectedBeforeCallingMock() {
        assertThrows(IllegalArgumentException.class,
                () -> notifier.sendReceipt(" "));
        verifyNoInteractions(receiptGateway);
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {
        // NO @Bean ReceiptGateway in this context.
        @Bean
        OrderNotifier orderNotifier(ReceiptGateway gateway) {
            return new OrderNotifier(gateway);
        }
    }
}
```

**Why does this class pass despite the missing gateway?** Before Spring instantiates `OrderNotifier`, the bean override infrastructure sees the `@MockitoBean` field, creates a `ReceiptGateway` mock via `REPLACE_OR_CREATE`, and registers it in the context. `OrderNotifier`'s constructor receives that mock. The first test stubs and verifies a valid call; the second confirms validation happens before touching the gateway.

Removing `@MockitoBean` without supplying a matching bean causes Spring to fail creating `OrderNotifier` due to the unsatisfied constructor dependency. That is a structural difference—not caused by assertions inside the test methods.

**Valid conclusion:** "A context containing only `OrderNotifier`, once augmented with a mock `ReceiptGateway`, executes the expected logic." **Invalid conclusion:** "Production already has a `ReceiptGateway` adapter."

### 4.3. Case B: requiring replacement of an existing bean

Create `src/test/java/example/testing/beans/ReplaceExistingTest.java`:

```java
package example.testing.beans;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringJUnitConfig(ReplaceExistingTest.Config.class)
class ReplaceExistingTest {

    // REPLACE: requires a matching bean to exist before replacing.
    @MockitoBean(enforceOverride = true)
    private ReceiptGateway receiptGateway;

    @Autowired
    private OrderNotifier notifier;

    @Autowired
    private ApplicationContext context;

    @Test
    void replacesPreviouslyRegisteredGatewayBean() {
        when(receiptGateway.send("ORD-7"))
                .thenReturn("mock:ORD-7");

        String actual = notifier.sendReceipt("ORD-7");

        assertEquals("mock:ORD-7", actual);
        assertNotEquals("real:ORD-7", actual);
        verify(receiptGateway).send("ORD-7");
        assertSame(receiptGateway,
                context.getBean(ReceiptGateway.class));
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {

        @Bean
        ReceiptGateway receiptGateway() {
            return new RealReceiptGateway();
        }

        @Bean
        OrderNotifier orderNotifier(ReceiptGateway gateway) {
            return new OrderNotifier(gateway);
        }
    }
}
```

Here, `Config.receiptGateway()` pre-defines a `ReceiptGateway` bean. `@MockitoBean(enforceOverride = true)` locates that exact bean and replaces it with a Mockito mock. Consequently, `OrderNotifier` receives the mock and the real implementation is never called.

**Meaning of strict mode:** if `@Bean ReceiptGateway receiptGateway()` were removed while `OrderNotifier` still needed a gateway, Spring TestContext cannot "rescue" the test by registering a mock. It must fail during context preparation, signaling that no bean exists to replace.

**Evidence limit:** this example only proves the bean exists in the **test fixture's configuration** and was successfully replaced. To prove **production configuration** defines the bean, load the appropriate production configuration in the test context; never declare a test-only bean just to make `enforceOverride=true` pass and claim production wiring works.

### 4.4. Negative example: strict mode fails when bean is absent

Suppose we reuse `CreateIfAbsentTest.Config` (which defines only `OrderNotifier`) and switch the annotation to strict mode.

**Example intentionally designed to fail; do not include in a green suite:**

```java
@SpringJUnitConfig(CreateIfAbsentTest.Config.class)
class StrictWithoutBeanTest {

    @MockitoBean(enforceOverride = true)
    ReceiptGateway receiptGateway;

    @Test
    void cannotReachTestBodyWhenContextCannotStart() {
        // No ReceiptGateway bean exists to REPLACE.
    }
}
```

This illustrative class sits in the same package as the tests above with similar imports. When run standalone, the expected outcome is that **ApplicationContext creation fails because no target bean exists to override**, so `@Test` never executes. Do not call "test method never ran" an assertion failure; it is a **context setup** failure delivering fail-fast behavior.

Mental trace:

```text
Context lacks ReceiptGateway
          |
          +-- @MockitoBean
          |     --> Spring creates mock ReceiptGateway
          |     --> OrderNotifier is constructed
          |     --> test methods can run
          |
          +-- @MockitoBean(enforceOverride = true)
                --> Spring looks for a bean to REPLACE
                --> Not found -> context creation error
                --> test method never executes
```

To observe the contrast, the two passing test classes and the negative snippet suffice. **There is no need to leave a permanently failing test in production builds** just to demonstrate the concept; applying strict mode in the right places is the sustainable practice.

### 4.5. Gradle configuration and running tests

In a Spring Boot project with Gradle plugins, repositories, and dependency management configured, the relevant `build.gradle` (Groovy DSL) snippet is:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is an **incremental configuration snippet** for a complete Spring Boot project. It omits plugin versions and Java toolchain declarations. You need dependencies compatible with `org.springframework.test.context.bean.override.mockito.MockitoBean`, meaning Spring Framework 6.2+; Spring Boot 3.4/3.5 and 4.x provide the new mechanism through their managed Framework versions.

Run the two expected-green classes:

```bash
./gradlew test --tests example.testing.beans.CreateIfAbsentTest
./gradlew test --tests example.testing.beans.ReplaceExistingTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.testing.beans.CreateIfAbsentTest"
.\gradlew.bat test --tests "example.testing.beans.ReplaceExistingTest"
```

**Expected:** the two tests in `CreateIfAbsentTest` and one test in `ReplaceExistingTest` all pass—**3 test methods** total. Gradle/JUnit output varies by version and configuration, so there is no single fixed stdout string. Check the test report to inspect individual method results.

**Do not include `StrictWithoutBeanTest`** in regular passing runs: that class illustrates fail-fast behavior and must fail during context creation. If you want to assert the missing-bean failure as a passing `assertThrows`, write a dedicated test driving context bootstrapping programmatically rather than putting `assertThrows` inside a method that never gets invoked.

### 4.6. Checking Java logic with javac/java

To isolate service logic from bean overriding, create `src/main/java/example/testing/beans/OrderNotifierDemo.java`:

```java
package example.testing.beans;

public class OrderNotifierDemo {
    public static void main(String[] args) {
        ReceiptGateway real = new RealReceiptGateway();
        OrderNotifier notifier = new OrderNotifier(real);

        System.out.println(notifier.sendReceipt("ORD-7"));

        try {
            notifier.sendReceipt(" ");
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

From the project root directory:

```bash
javac -d out src/main/java/example/testing/beans/OrderNotifier.java src/main/java/example/testing/beans/OrderNotifierDemo.java
java -cp out example.testing.beans.OrderNotifierDemo
```

Exact stdout:

```text
real:ORD-7
orderId must not be blank
```

This plain Java demo **does not run JUnit or Spring TestContext**; it merely demonstrates the real service and adapter running without a container. The `REPLACE_OR_CREATE` and `REPLACE` strategies are demonstrated by the Spring test classes in Sections 4.2–4.3.

## 5. Choosing correctly in Spring Boot slice and integration tests

### 5.1. `@WebMvcTest`: adding a missing mock is usually intentional

`@WebMvcTest` focuses on the MVC layer. A controller whose constructor requires a service typically needs a mock because the real service lives **outside the slice**. Default `@MockitoBean` makes sense here:

```java
@WebMvcTest(OrderController.class)
class OrderControllerWebTest {

    @MockitoBean
    OrderApplicationService service;

    @Autowired
    MockMvc mockMvc;

    // Test status, binding, validation, JSON...
}
```

This is an **illustrative class snippet**, not standalone-runnable because `OrderController`/`OrderApplicationService` are undefined and no assertion methods exist. Real tests must configure security when applicable, send requests, and verify responses. Remember: a service outside the MVC slice **can be newly created as a mock** without signaling a design flaw.

Enabling `enforceOverride=true` on a service intentionally excluded from the slice causes the context to fail mechanically—meaning **the test goal was misconfigured**. Only enable strict mode when the bean is expected to exist in that context.

### 5.2. `@SpringBootTest`: strict when verifying production bean presence

In full-context integration tests, a missing production bean is often a bug worth catching. You can structure it like this:

```java
@SpringBootTest
class ReceiptWiringTest {

    @MockitoBean(enforceOverride = true)
    ReceiptGateway receiptGateway;

    @Autowired
    OrderNotifier notifier;

    @Test
    void usesMockOfExistingGateway() {
        when(receiptGateway.send("ORD-7"))
                .thenReturn("mock:ORD-7");
        assertEquals("mock:ORD-7",
                notifier.sendReceipt("ORD-7"));
    }
}
```

This is an **illustrative snippet**, not a copy-and-run class: it requires proper imports, real app config registering `OrderNotifier`/`ReceiptGateway`, and matching types. If the test runs a profile different from production or defines a test-specific `@Bean` replacement, it only proves that profile's context. **Enforce override cannot prove anything about beans the context never loads.**

In Spring Boot 4, do not assume `@SpringBootTest` automatically configures `MockMvc`; MVC testing needs explicit test MVC setup (e.g., `@AutoConfigureMockMvc` where appropriate). This does not change `@MockitoBean` semantics: overriding depends on TestContext and the loaded bean set.

### 5.3. Focused tests: no context needed for pure logic

If the goal is merely checking that `OrderNotifier.sendReceipt(...)` invokes the right collaborator for an input, use plain JUnit + Mockito:

```java
ReceiptGateway gateway = Mockito.mock(ReceiptGateway.class);
OrderNotifier notifier = new OrderNotifier(gateway);

when(gateway.send("ORD-7")).thenReturn("ok");
assertEquals("ok", notifier.sendReceipt("ORD-7"));
verify(gateway).send("ORD-7");
```

This snippet belongs inside a test method with Mockito/JUnit imports. Without a context, "whether a bean exists" does not apply; that is a **separate question** tested at the Spring TestContext boundary.

## 6. Selecting which bean to override: type, name, and qualifier

Bean overriding does not perform all the heuristics of standard autowiring. It generally resolves beans by type and qualifier; when multiple candidates exist, the field name can also act as a fallback qualifier. Thus, ambiguous types can replace the wrong bean or fail due to ambiguity.

Example config with two beans:

```java
@Bean("emailReceiptGateway")
ReceiptGateway emailGateway() { ... }

@Bean("smsReceiptGateway")
ReceiptGateway smsGateway() { ... }
```

This snippet illustrates configuration methods without full implementations. To strictly replace the email bean, select **by name**:

```java
@MockitoBean(
        name = "emailReceiptGateway",
        enforceOverride = true)
ReceiptGateway emailReceiptGateway;
```

Or select by qualifier:

```java
@MockitoBean(enforceOverride = true)
@Qualifier("emailReceiptGateway")
ReceiptGateway gateway;
```

Both approaches are **alternatives**, not meant to be mandatory together. Verify real bean names from application code/config rather than guessing. Tests must not inadvertently introduce extra beans of the same interface and alter `@Primary`, qualifier, or by-type injection.

**Common traps:**

- Field named `gateway` has the right type, yet the context has multiple `ReceiptGateway` beans. Do not assume Spring knows which bean to replace.
- Field name initially matches a bean name and later gets renamed during refactoring; name fallback can alter the selected candidate and change Spring TestContext's cache key.
- A bean registered by profile/condition exists only in certain environments. Strict mode only guarantees existence **within the context the test actually loads**.
- A dependency registered directly as an instance without a corresponding bean definition; override infrastructure may not recognize it as a candidate to replace.

With multi-level `@ContextHierarchy`, an override can affect multiple levels. To restrict to one level, set `contextName` matching `@ContextConfiguration(name = "...")` according to your Spring Framework version's documentation.

## 7. `@MockitoSpyBean` is `WRAP`, not strict replacement

Sometimes you want most real bean behavior to execute while observing or stubbing one method using `@MockitoSpyBean`. However, it **differs** from `@MockitoBean(enforceOverride=true)`:

| Aspect | Strict mock | Spy |
| --- | --- | --- |
| Mechanism | `REPLACE` | `WRAP` |
| Requires original bean? | Yes | Yes, typically exactly one candidate |
| Unstubbed methods | Mockito mock returns default/configured answer | Typically calls real method |
| Risk of real I/O | Low if target alone is mocked | Higher since real methods run |
| Observes real behavior? | No, original target is replaced | Yes, though AOP/spy details must be assessed |
| Purpose | Fully replace dependency; missing bean is an error | Observe/control part of an existing real bean |

With a spy, `Mockito.when(spy.method())` can invoke the **real method during stubbing**. If the method touches DB/network, use `doReturn(value).when(spy).method(...)` where appropriate to prevent side effects. Never treat a spy as a way to "verify the bean exists" if you do not want any real behavior running.

**Crucial note on proxies:** `@MockitoBean` (`REPLACE`/`REPLACE_OR_CREATE`) replaces the bean directly with a mock and may **discard Spring AOP advice** around the original bean, such as `@Transactional`, `@Cacheable`, or method security. `@MockitoSpyBean` uses a different `WRAP` mechanism and can preserve AOP proxying around the spy. Never mock a service and claim its transaction/cache/security advice was tested.

## 8. How mocks can cause a false-positive integration test

Suppose a production configuration change drops an adapter bean:

```text
A @Configuration / @ComponentScan changes
       |
       v
ReceiptGateway is not registered in app context
       |
       v
Test has @MockitoBean (default)
       |
       v
Spring TestContext creates a new mock gateway
       |
       v
OrderNotifier initializes successfully, test PASSES
       |
       v
False conclusion: "production bean wiring is healthy"
```

To prevent this:

1. **Classify the test goal first:** behavior, MVC slice, adapter contract, or real wiring.
2. **Choose the right context:** slice tests intentionally omitting beans are fine; full-context tests protecting wiring must load real configuration/profiles.
3. **Enable strict mode at the right boundary:** apply `enforceOverride=true` to beans that must exist, not blindly to every mock.
4. **Never register a test bean solely to make strict mode pass:** that only proves the test fixture, not production.
5. **Keep targets real when testing AOP:** when checking transactions/security/caching, mock dependencies behind the target rather than the advised target itself.

Strict does not mean "always better." It is a **contract assertion about context structure**. Misusing it causes needless red tests, just as misusing lenient creation causes false green tests.

## 9. Real-world failure patterns and reading symptoms

### Missing bean in context

Symptoms typically show context startup failing because no matching candidate exists to override or a dependency goes unsatisfied. With `@MockitoBean(enforceOverride=true)`, verify whether the bean definition is included in the test's config/profile. If it ought to exist, **fix the registration** rather than removing strict mode to force a pass.

### Multiple beans sharing an interface

When multiple implementations exist, matching may be ambiguous. Specify `name` or `@Qualifier` explicitly and verify which bean the component actually injects. Do not slap `@Primary` onto a test bean casually to silence ambiguity without understanding runtime differences.

### `@Mock` has no effect on Spring context

Mockito initializes the mock field, yet Spring still injects another adapter or fails with a missing bean. When the mock must be a Spring bean, use `@MockitoBean`; in plain Java unit tests, call the constructor directly.

### Mocking a `@Transactional` service invalidates transaction tests

Replacing the target with a mock bypasses AOP proxies. `verify(mock).method()` does not prove transactions committed, caches populated, or authorization ran. Use Spring integration tests with the **real service**.

### Spy triggers unintended real work

Using `when(...)` on a spy can execute real methods during stubbing; switch to `doReturn(...)`/`doThrow(...)` when appropriate and avoid spying I/O adapters with uncontrolled side effects.

### Slow tests spent starting contexts

Every override set, qualifier, and naming pattern can affect Spring TestContext's cache. Name fields consistently and structure tests sharing the same goal uniformly to prevent unnecessary context splits. Never use `@DirtiesContext` as a default workaround for uncleaned test data.

### Mocks reset, yet DB/cache data persists

The test framework resets mocks, not databases, Redis, message queues, or static/singleton state. Manage fixtures, transactions, and cleanup explicitly; never treat bean mocking as full-application isolation.

## 10. Upgrading legacy `@MockBean` to `@MockitoBean`

In older Spring Boot projects, you may see:

```java
import org.springframework.boot.test.mock.mockito.MockBean;
```

Starting in Spring Boot **3.4**, Boot's `@MockBean`/`@SpyBean` are deprecated in favor of Spring Framework annotations. In Spring Boot **4.0**, support for the legacy annotations is removed. New code uses:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
```

**Never swap imports without checking semantics:**

- `@MockitoBean` defaults to replace-or-create; if an older test "accidentally" passed by creating a missing bean, determine whether that was intentional or a masked bug.
- To fail when a bean is absent, set `enforceOverride=true`.
- Placing legacy annotations inside `@Configuration` does not translate 1:1 to Spring Framework's `@MockitoBean`. Check supported declaration sites in the docs; generally place fields or annotations on supported test classes/hierarchies rather than copying legacy annotations inside `@TestConfiguration`.
- In Spring Framework 6.2, overriding non-singleton scopes has restrictions: favor singletons and avoid assuming prototype/request scopes override seamlessly. Verify docs for your exact version in complex scenarios.
- Context hierarchies and bean-name matching can alter migrated tests; specify `contextName`/qualifiers only when actually needed.

**Intentional migration example:** testing a real controller while mocking a service outside the web slice => default `@MockitoBean`. Full-context test requiring a production adapter => `@MockitoBean(enforceOverride=true)` while ensuring the test does not register a fake adapter that lets strict mode pass artificially.

## 11. When to use `@Primary` or `@TestBean` instead?

An alternative is creating a `@TestConfiguration` containing a fake:

```java
@TestConfiguration
class FakeGatewayConfig {

    @Bean
    @Primary
    ReceiptGateway fakeGateway() {
        return id -> "fake:" + id;
    }
}
```

This is an illustrative config snippet requiring Spring Boot `TestConfiguration`, Spring `Bean`/`Primary` imports, and the matching interface. `@Primary` prioritizes the fake bean during by-type autowiring; it **does not necessarily replace the production bean**. The original bean may still be instantiated and cause side effects. Thus, it is not equivalent to `@MockitoBean(name="...", enforceOverride=true)` when you must replace an exact existing bean.

Spring TestContext's `@TestBean` can replace a bean with a test implementation supplied via a factory method instead of Mockito. Choose this when a fake needs real behavior/state for testing rather than simple stubbing. Match the strategy and version carefully; **do not mix tools merely because their names sound alike**.

**Rule:** if you only need a fake dependency for unit tests, skip the Spring context. If a mock must participate in bean injection, use Spring TestContext overrides. If you need a stateful/behavioral fake, use a fitting `@TestBean`/test configuration and confirm whether the real bean still lives in the context.

## 12. Common pitfalls

**1. Treating an auto-created mock as proof the original bean exists.** Under `REPLACE_OR_CREATE`, that conclusion is false. Use strict mode to guard existence.

**2. Enabling strict mode in a slice that intentionally omits collaborators.** Context failure is the expected outcome of a mismatched requirement; use default creation when a slice needs extra dependencies.

**3. Annotating `@Mock` and expecting Spring to inject it.** Mockito fields do not become Spring beans automatically. Match the annotation to the boundary.

**4. Failing to disambiguate when multiple candidates exist.** Type, qualifiers, field fallback, and bean names must align with real configuration.

**5. Enabling strict mode while defining the target mock/bean in test configuration.** The test only proves the fixture is wired, not production wiring.

**6. Enabling global bean definition overriding.** It can hide duplicate bean errors and is no substitute for `@MockitoBean`.

**7. Mocking the exact bean whose proxy needs testing.** Losing target transaction/cache/security advice yields green tests that fail to verify framework behavior.

**8. Spying an uncontrolled I/O adapter.** Spies can run real methods; avoid side effects during stubbing appropriately.

**9. Confusing context creation failures with assertion failures.** `enforceOverride=true` with an absent bean fails **before any test method runs**; inspect the bean override root cause rather than editing unexecuted assertions.

**10. Renaming fields and shifting selected candidates.** With multiple beans, use consistent names/qualifiers; field names can act as fallback qualifiers and alter context cache keys.

**11. Using legacy `@MockBean` in Boot 4.** Legacy Boot annotations no longer exist; switch to the new Spring TestContext API.

**12. Neglecting non-Mockito state cleanup.** Mock resets do not clear DBs/caches; maintain isolation with proper setup/cleanup.

**13. Applying strict mode to beans in another profile.** Strict mode applies only to the **current context** and cannot verify an unloaded profile.

**14. Keeping tests green by mocking everything.** Mocking the target/service under test reduces the test to checking stubs. Keep the SUT real and restrict test doubles to collaborators.

## 13. Pre-QA sign-off checklist

- Am I **adding a mock to populate a slice** or **replacing an existing production bean**?
- If the bean is missing, should the test pass or fail? Does `enforceOverride` reflect that?
- Does Spring TestContext load the exact configuration/profile I intend to verify?
- With multiple beans of the same type, do I need `name`/`@Qualifier`?
- Does the test actually exercise the real SUT or merely test mock stubs?
- Would a plain unit test with constructor injection suffice, or is a Spring context truly needed?
- Is the test proving business behavior, bean wiring, proxy advice, or HTTP/DB integration?
- If a bean name/config changes, will strict tests fail in the right place instead of silently adding a mock?
- Does mocking strip AOP/transaction/cache/security advice from the target under test?
- Are caches/DBs reset and data isolated across test methods and contexts?
- Do APIs match the exact Spring Framework version and package imports?
- Do conclusions drawn after a green test stay within the actual scope of evidence?

**Conclusion:** `@MockitoBean` defaults to **`REPLACE_OR_CREATE`**, allowing new mocks when no bean exists; `@MockitoBean(enforceOverride = true)` uses **`REPLACE`**, requiring an existing bean. Choose the mode based on the invariant you want to protect, not whichever makes tests pass fastest. A context passing thanks to a newly created mock **is not proof of valid production configuration**.

## 14. References

- [Spring Framework 6.2 — @MockitoBean and @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html)
- [Spring Framework — Bean Overriding in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/bean-overriding.html)
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
