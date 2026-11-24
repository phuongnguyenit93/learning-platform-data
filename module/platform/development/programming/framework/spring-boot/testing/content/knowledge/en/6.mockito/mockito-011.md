# Distinguishing Plain Java Object Mocks from Bean Overrides in the Spring Context

## 1. Goal

When writing Spring Boot tests, these two snippets look similar yet control **two completely different object graphs**:

```java
@Mock
ShippingGateway shippingGateway;
```

```java
@MockitoBean
ShippingGateway shippingGateway;
```

`@Mock` creates a Mockito object scoped to the Java test class, whereas `@MockitoBean` tells Spring TestContext to **register or replace a bean inside the test's `ApplicationContext`**. If a Spring-managed service was already injected with the real gateway, creating an extra Java mock in the test will not make that service switch to the new mock.

This lesson explains clearly:
- Why `Mockito.mock`/`@Mock` is sufficient for plain Java unit tests yet cannot affect Spring's dependency injection.
- How `@InjectMocks` differs from `@Autowired`, and when to use explicit constructor injection.
- How `@MockitoBean` and `@MockitoSpyBean` work, bean resolution by type/name/qualifier, and behavior when no target bean exists.
- Choices in `@WebMvcTest`, `@SpringBootTest`, and when database/AOP/security tests are required.
- Misconceptions about legacy `@MockBean`/`@SpyBean`, Spring context caching, mock resets, and mocks receiving zero invocations.
- A runnable Maven + Java 17 + JUnit Jupiter example covering unit tests, web slices, and full contexts.

Examples use Spring Boot **3.5.16**, corresponding to Spring Framework 6.2.x where `@MockitoBean` belongs to Spring TestContext. For Boot 3.3 and earlier, see the version compatibility section before copying imports.

## 2. Fundamentals: Java Mock Objects and Spring Beans Are Not the Same Thing

### 2.1. Mockito Creates Fake Java Objects

`Mockito.mock(ShippingGateway.class)` returns a Java object. By default, unstubbed methods return default values (e.g., `0` for `int`; exact semantics depend on return type and Mockito). You control outputs and record interactions:

```java
ShippingGateway gateway = Mockito.mock(ShippingGateway.class);
Mockito.when(gateway.feeFor("HCM")).thenReturn(20);

int result = gateway.feeFor("HCM"); // 20
Mockito.verify(gateway).feeFor("HCM");
```

This snippet illustrates code inside a Java method using the project's `ShippingGateway` interface from Section 6. It does not use `ApplicationContext`, `@ComponentScan`, `@Autowired`, or a bean factory.

Mockito has no knowledge of:
- Which `ShippingGateway` was injected into Spring's `CheckoutService`.
- How many beans implement that interface, or which carries `@Primary`/`@Qualifier`.
- Spring profiles, auto-configuration, transactions, retries, caching, or method security.
- Any beans whose dependency graph was already wired before the mock was created.

Mockito only sees **the object held by the test and calls actually reaching that object**.

### 2.2. Spring Creates and Wires Beans

Suppose the application has this bean graph:

```text
Spring ApplicationContext
  |
  +-- CheckoutController bean
  |       |
  |       +-- CheckoutService bean
  |               |
  |               +-- FlatShippingGateway bean
  |
  +-- MVC, Jackson, and other infrastructure beans
```

When Spring instantiates `CheckoutService`, its constructor receives the `ShippingGateway` bean resolved from the container. If a test then declares:

```java
@Mock
ShippingGateway shippingGateway;

@Autowired
CheckoutService checkoutService;
```

by default the test merely holds **its own separate mock field**, while `checkoutService` continues using the Spring-injected bean. Even worse, without `MockitoExtension`/`openMocks`, the `@Mock` field can remain `null`.

To make Spring replace the dependency inside the container graph built for the test, use:

```java
@SpringBootTest
class ServiceContextTest {
    @MockitoBean
    ShippingGateway shippingGateway;

    @Autowired
    CheckoutService checkoutService;
}
```

Inside the test context, the matching `ShippingGateway` bean becomes a Mockito mock; the real `CheckoutService` receives that mock from Spring. You can still use `when`/`verify` as usual because the overridden bean is still a Mockito mock underneath.

### 2.3. Quick Comparison

| Distinction | `@Mock` / `Mockito.mock` | `@MockitoBean` |
| --- | --- | --- |
| Created by | Mockito (test/extension) | Spring TestContext integrated with Mockito |
| Needs a Spring context? | No | Yes |
| Where the object lives | Field/local variable held by the test | Bean in test `ApplicationContext` and injected into field |
| Affects Spring DI? | Not automatically | Yes, when resolved to the target bean |
| Replaces an existing bean? | No | Yes |
| What if no matching bean exists? | Still creates the mock object | By default registers a new mock bean under `REPLACE_OR_CREATE` |
| Context startup cost? | None | Yes; can benefit from context caching |
| Tests Spring wiring? | No | Can verify real service/bean receives the mock; does not test the mocked bean's own logic |
| Best fit | Domain/service unit tests | Slice/web/full-context tests needing collaborator replacement |

The deciding question is **who owns references to the dependencies of the object under test**. If the test constructs the object → the test injects dependencies. If Spring constructs the object → Spring must register/override the bean in its context to swap a dependency.

## 3. Plain Mockito Unit Tests: `@Mock`, `@InjectMocks`, and Setup

### 3.1. JUnit 5 Must Initialize Mockito Fields

```java
@ExtendWith(MockitoExtension.class)
class CheckoutServiceUnitTest {
    @Mock
    ShippingGateway shippingGateway;

    @Test
    void testMethod() {
        when(shippingGateway.feeFor("HCM")).thenReturn(20);
    }
}
```

`@ExtendWith(MockitoExtension.class)` processes Mockito annotations in JUnit Jupiter and manages test state and strict stubbing. When a test only needs one mock, direct creation is equally valid:

```java
ShippingGateway shippingGateway = mock(ShippingGateway.class);
```

No context or `@SpringBootTest` is needed. Never add Spring just to make Mockito run.

### 3.2. `@InjectMocks` Is a Convenience Utility, Not Spring DI

```java
@ExtendWith(MockitoExtension.class)
class ServiceUnitTest {
    @Mock ShippingGateway shippingGateway;
    @InjectMocks CheckoutService checkoutService;
}
```

Mockito attempts to inject the test's mocks/spies into `CheckoutService` (via constructor, setter, or field injection per Mockito rules). It **does not**:
- Start a Spring `ApplicationContext`.
- Resolve beans by `@Qualifier`/`@Primary`.
- Read `@Value` properties from the Spring `Environment`.
- Apply Spring bean lifecycles or AOP advice.
- Recursively build a multi-layer graph of nested services.

Mockito's documentation also notes that injection can fail silently without raising an error immediately; verify behavior with assertions. With a single constructor, writing `new CheckoutService(shippingGateway)` is often clearer:

```java
ShippingGateway mockGateway = mock(ShippingGateway.class);
CheckoutService sut = new CheckoutService(mockGateway);
when(mockGateway.feeFor("HCM")).thenReturn(20);
assertEquals(120, sut.total(100, "HCM"));
```

This is an illustrative snippet inside a method, requiring JUnit/Mockito imports. SUT = system under test, meaning the **object whose real logic you want to test**, while mocks stand in for external collaborators.

### 3.3. What Can a Unit Test Prove?

A service unit test can prove:
- Invalid input rejection before calling outbound dependencies.
- Calculation formulas and business branches.
- Whether collaborators are called and with what arguments.
- Error handling when collaborators throw stubbed exceptions.

It does not prove that `@Transactional` works, controllers return proper JSON, JPA executes valid SQL, or brokers deliver real messages. Those risks require tests at the appropriate Spring/infrastructure boundary.

## 4. `@MockitoBean`: Replacing Beans in Spring TestContext

### 4.1. Right Package and When to Use It

Import for Spring Framework 6.2+:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
```

This annotation is part of Spring TestContext bean overriding. It is processed when tests run with a Spring extension/context, such as `@SpringBootTest`, `@WebMvcTest`, `@DataJpaTest`, or suitable `@SpringJUnitConfig`.

```java
@WebMvcTest(CheckoutController.class)
class CheckoutControllerWebTest {
    @Autowired MockMvc mvc;
    @MockitoBean CheckoutService checkoutService;
}
```

```java
@SpringBootTest
class CheckoutServiceContextTest {
    @Autowired CheckoutService checkoutService;
    @MockitoBean ShippingGateway shippingGateway;
}
```

First case: real controller, real MVC layer, mocked service. Second case: real service, mocked gateway. Both use Mockito, yet the **real object under test** is different.

### 4.2. Resolving the Exact Bean by Type, Name, and Qualifier

When placed on a field, Spring infers the bean type from the field type. When multiple beans share the same type, disambiguate explicitly:

```java
// Illustrative example when context has multiple PriceClient beans:
@MockitoBean
@Qualifier("remotePriceClient")
PriceClient priceClient;
```

Or:

```java
@MockitoBean(name = "remotePriceClient")
PriceClient priceClient;
```

`PriceClient` is an illustrative interface outside the sample project. Spring can also fall back to the **field name as a qualifier** when no explicit qualifier is given. Consequently, mocking the same bean under different field names across tests can alter the context cache key; keep names consistent when tests intentionally share a context configuration.

You can also place it at the class level:

```java
@MockitoBean(types = {ShippingGateway.class})
@SpringBootTest
class AlternativeOverrideTest {
    // ...
}
```

This illustrates syntax and is not a required class in the runnable project. When specifying a bean name at the type level, `types` must be clear and match a single bean type for that name.

### 4.3. Missing Target Beans: REPLACE_OR_CREATE and enforceOverride

By default, Spring Framework uses the `REPLACE_OR_CREATE` strategy for `@MockitoBean`. If a matching target bean exists, it is replaced with the mock. If none exists, Spring registers a new mock bean.

This is convenient in `@WebMvcTest`: services are usually **excluded from the MVC slice**, yet the controller needs a service dependency, so the mock is added to the context. Downside: a full-context test can accidentally pass even if the real production bean disappeared from component scanning.

To catch missing target beans:

```java
@MockitoBean(enforceOverride = true)
ShippingGateway shippingGateway;
```

`enforceOverride=true` requires an existing bean to replace (`REPLACE` strategy). This fits `@SpringBootTest` when you want assurance the production bean exists; avoid applying it blindly in slices that intentionally exclude real services.

### 4.4. Scope, FactoryBean, and Proxies

Spring TestContext bean overrides target singleton beans. Overriding non-singleton beans can fail; `@MockitoSpyBean` further requires exactly one existing bean to wrap.

If the target is produced by a `FactoryBean`, override behavior applies to the produced object per Spring Framework rules; do not confuse the factory with the object injected into collaborators.

Spring can wrap real beans in AOP proxies for transactions, caching, retries, or method security. `@MockitoBean` registers **a direct replacement mock**, so advice from the original bean **is no longer present on that mock**. Calling a mocked service never proves transactions, caching, or security on the real service.

Mocking bean **A** does not automatically strip AOP from a real bean **B**; examine carefully which exact bean was overridden.

### 4.5. Resetting Between Tests

`@MockitoBean` is managed by Spring TestContext; by default it resets mocks after each test method (`MockReset.AFTER`). Contexts can be cached and reused across tests while Mockito stubbing and interaction history are reset.

Do not assume that also resets databases, static state, filesystems, or external services. For shared data, design separate fixtures, transactions, or cleanup. Calling `Mockito.reset(mock)` manually inside tests often indicates unclear test boundaries.

## 5. `@MockitoSpyBean`: Observing a Bean with Real Behavior

A spy fundamentally observes **a real object** and supports selective stubbing/verifying, unlike a mock which skips real logic by default.

| Tool | What is created/wrapped | Spring DI |
| --- | --- | --- |
| `spy(realObject)` or `@Spy` | Mockito spy of a test-created object | Not registered in the container |
| `@MockitoSpyBean` | Existing Spring bean wrapped with a spy | Yes; requires an existing target bean |
| `@MockitoBean` | Mockito mock replacing a Spring bean | Yes; real methods of the replaced bean do not run |

```java
@SpringBootTest
class CheckoutSpyBeanTest {
    @MockitoSpyBean
    CheckoutService checkoutService;

    @Test
    void observesRealMethod() {
        int result = checkoutService.total(100, "HCM");
        assertEquals(200, result);
        verify(checkoutService).total(100, "HCM");
    }
}
```

This runs in Section 6's project. Because neither the service nor the real gateway is stubbed, the total is **200**.

When stubbing spies, remember:

```java
// May execute the real method right during stub setup:
when(spy.someMethod()).thenReturn(value);

// Generally avoids calling the real method at stubbing time:
doReturn(value).when(spy).someMethod();
```

Both lines merely illustrate the pattern; `spy` and `value` are defined by specific tests. `@MockitoSpyBean` uses the `WRAP` strategy and interacts differently with Spring AOP proxies than `@MockitoBean`. In proxied systems, the spy target and the injected proxy may not be the exact same Java reference; follow Spring Framework guidance when stubbing/verifying proxied methods. Never spy on methods with uncontrolled side effects (sending emails, charging payments, network calls).

## 6. Runnable Practice Project with Maven

The same shipping quote use case will be tested across five scopes. The difference between a Java mock and a Spring mock bean is **directly observable**, not just theoretical.

### 6.1. Project Tree

```text
mock-boundary-lab/
├── pom.xml
├── src/main/java/com/example/mockboundary/
│   ├── MockBoundaryApplication.java
│   ├── ShippingGateway.java
│   ├── FlatShippingGateway.java
│   ├── CheckoutService.java
│   └── CheckoutController.java
└── src/test/java/com/example/mockboundary/
    ├── CheckoutServiceUnitTest.java
    ├── CheckoutControllerWebTest.java
    ├── CheckoutServiceContextTest.java
    ├── DetachedMockSpringTest.java
    └── CheckoutSpyBeanTest.java
```

### 6.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>mock-boundary-lab</artifactId>
  <version>0.0.1-SNAPSHOT</version>
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
```

`spring-boot-starter-test` brings in Mockito, JUnit Jupiter, and Spring Test/AssertJ under Spring Boot dependency management. No individual library versions need to be declared in this project.

### 6.3. Application Code

`src/main/java/com/example/mockboundary/MockBoundaryApplication.java`:

```java
package com.example.mockboundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MockBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(MockBoundaryApplication.class, args);
    }
}
```

`src/main/java/com/example/mockboundary/ShippingGateway.java`:

```java
package com.example.mockboundary;

public interface ShippingGateway {
    int feeFor(String zone);
}
```

`src/main/java/com/example/mockboundary/FlatShippingGateway.java`:

```java
package com.example.mockboundary;

import org.springframework.stereotype.Component;

@Component
public class FlatShippingGateway implements ShippingGateway {
    @Override
    public int feeFor(String zone) {
        return 100;
    }
}
```

`src/main/java/com/example/mockboundary/CheckoutService.java`:

```java
package com.example.mockboundary;

import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final ShippingGateway shippingGateway;

    public CheckoutService(ShippingGateway shippingGateway) {
        this.shippingGateway = shippingGateway;
    }

    public int total(int subtotal, String zone) {
        if (subtotal < 0) {
            throw new IllegalArgumentException("Subtotal must be >= 0");
        }
        return subtotal + shippingGateway.feeFor(zone);
    }
}
```

`src/main/java/com/example/mockboundary/CheckoutController.java`:

```java
package com.example.mockboundary;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/checkout")
public class CheckoutController {
    private final CheckoutService checkoutService;

    public CheckoutController(CheckoutService checkoutService) {
        this.checkoutService = checkoutService;
    }

    @GetMapping("/quote")
    public Quote quote(@RequestParam int subtotal,
                       @RequestParam String zone) {
        return new Quote(checkoutService.total(subtotal, zone));
    }

    public record Quote(int total) {}
}
```

There are no mocks in application code. With `subtotal = 100`, the real `FlatShippingGateway` returns a fee of 100, producing `total=200`.

### 6.4. Test #1: Java Mock, No Spring Context

`src/test/java/com/example/mockboundary/CheckoutServiceUnitTest.java`:

```java
package com.example.mockboundary;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class CheckoutServiceUnitTest {
    @Mock
    ShippingGateway shippingGateway;

    @InjectMocks
    CheckoutService checkoutService;

    @Test
    void mockFeeIsUsedByJavaObject() {
        when(shippingGateway.feeFor("HCM")).thenReturn(20);

        assertEquals(120, checkoutService.total(100, "HCM"));
        verify(shippingGateway).feeFor("HCM");
    }

    @Test
    void invalidSubtotalSkipsGateway() {
        assertThrows(IllegalArgumentException.class,
                () -> checkoutService.total(-1, "HCM"));
        verifyNoInteractions(shippingGateway);
    }
}
```

Mockito creates the service object and injects the mocked gateway. Spring does not start. The test verifies business logic, not Spring bean wiring.

### 6.5. Test #2: Real Controller + Mocked Service in Web Slice

`src/test/java/com/example/mockboundary/CheckoutControllerWebTest.java`:

```java
package com.example.mockboundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(CheckoutController.class)
class CheckoutControllerWebTest {
    @Autowired
    MockMvc mvc;

    @MockitoBean
    CheckoutService checkoutService;

    @Test
    void webSliceUsesMockService() throws Exception {
        when(checkoutService.total(100, "HCM")).thenReturn(120);

        mvc.perform(get("/checkout/quote")
                        .param("subtotal", "100")
                        .param("zone", "HCM"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").value(120));

        verify(checkoutService).total(100, "HCM");
    }
}
```

`@WebMvcTest` sets up MVC infrastructure and the controller without loading all `@Service` beans like a full context. `@MockitoBean` registers a `CheckoutService` mock bean so the controller constructor receives its dependency. `MockMvc` tests HTTP routing, request parameters, JSON serialization, and delegation without running a real web server. Because the service is mocked, this test **does not** verify the service's calculation formula.

### 6.6. Test #3: Full Context Keeping Service Real, Overriding Gateway

`src/test/java/com/example/mockboundary/CheckoutServiceContextTest.java`:

```java
package com.example.mockboundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringBootTest
class CheckoutServiceContextTest {
    @Autowired
    ApplicationContext context;

    @Autowired
    CheckoutService checkoutService;

    @MockitoBean(enforceOverride = true)
    ShippingGateway shippingGateway;

    @Test
    void contextInjectsMockIntoRealService() {
        when(shippingGateway.feeFor("HCM")).thenReturn(20);

        assertEquals(120, checkoutService.total(100, "HCM"));
        assertSame(shippingGateway,
                context.getBean(ShippingGateway.class));
        verify(shippingGateway).feeFor("HCM");
    }
}
```

Here the service is **created by Spring** and injected with the mocked gateway **provided by Spring bean override**. `enforceOverride=true` asserts that a real gateway bean existed before overriding. `assertSame` holds in this project because the gateway has no AOP proxy; do not generalize reference-identity assertions to proxied beans.

### 6.7. Test #4: Detached Java Mock Does Not Affect Injected Bean

`src/test/java/com/example/mockboundary/DetachedMockSpringTest.java`:

```java
package com.example.mockboundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;

@SpringBootTest
class DetachedMockSpringTest {
    @Autowired
    CheckoutService checkoutService;

    @Test
    void detachedJavaMockDoesNotChangeSpringWiring() {
        ShippingGateway detached = mock(ShippingGateway.class);

        int result = checkoutService.total(100, "HCM");

        assertEquals(200, result); // real gateway still returns 100
        verifyNoInteractions(detached);
    }
}
```

This test deliberately proves that a standalone Java mock exists yet **does not sit on the service's call path**. The result is 200, whereas the tests stubbing the gateway/service above return 120. The test does not stub the detached object so as not to trigger `UnnecessaryStubbingException` under strict Mockito; trying to stub a detached mock and seeing unused-stubbing failures is a telltale sign the SUT never used it.

### 6.8. Test #5: Spying a Spring Bean and Running Real Methods

`src/test/java/com/example/mockboundary/CheckoutSpyBeanTest.java`:

```java
package com.example.mockboundary;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;

@SpringBootTest
class CheckoutSpyBeanTest {
    @MockitoSpyBean
    CheckoutService checkoutService;

    @Test
    void spyRunsRealService() {
        int result = checkoutService.total(100, "HCM");

        assertEquals(200, result);
        verify(checkoutService).total(100, "HCM");
    }
}
```

`@MockitoSpyBean` wraps the real bean. Because it is unstubbed, the real method calls the real `FlatShippingGateway` and returns 200. Spying fits when you want to observe calls while keeping real business behavior.

### 6.9. Running the Project and Observing Results

Requires JDK 17+ and Maven. In the directory containing `pom.xml`:

```bash
mvn -q -Dtest=CheckoutServiceUnitTest test
mvn -q -Dtest=CheckoutControllerWebTest test
mvn -q -Dtest=CheckoutServiceContextTest test
mvn -q -Dtest=DetachedMockSpringTest test
mvn -q -Dtest=CheckoutSpyBeanTest test
mvn -q test
```

All five test classes are designed to pass their assertions; Maven exits with code `0` when all tests succeed. No fixed stdout is claimed because Spring/Maven logs and timings vary by environment. `-Dtest=...` selects one class; `mvn -q test` runs all classes ending in `Test`.

| Test | Real bean/SUT | Mocked/spied object | Verified result |
| --- | --- | --- | --- |
| Unit | `CheckoutService` Java object | `@Mock ShippingGateway` | Total = 120 |
| Web slice | `CheckoutController` Spring bean | `@MockitoBean CheckoutService` | JSON total = 120 |
| Full context | `CheckoutService` Spring bean | `@MockitoBean ShippingGateway` | Total = 120 |
| Detached mock | `CheckoutService` Spring bean | Standalone Java mock, uninjected | Total = 200 |
| Spy bean | `CheckoutService` Spring bean via spy | `@MockitoSpyBean CheckoutService` | Total = 200 |

You can run the real application:

```bash
mvn spring-boot:run
```

Call the endpoint from another terminal:

```bash
curl "http://localhost:8080/checkout/quote?subtotal=100&zone=HCM"
```

When the sample code runs without external overrides, the JSON body is:

```json
{"total":200}
```

When the application runs normally without test mocks, Spring injects the real `FlatShippingGateway`, showing why 120 in tests is mock-driven rather than production output.

## 7. Comparing `@MockitoBean` with `@MockBean` and `@MockitoSpyBean` with `@SpyBean`

Avoid confusing the two packages:

| API | Package | Status |
| --- | --- | --- |
| `@Mock` / `@Spy` | `org.mockito` | Plain Java Mockito; still right for unit tests |
| `@MockBean` / `@SpyBean` | `org.springframework.boot.test.mock.mockito` | Legacy; deprecated in Spring Boot 3.4 for removal in Boot 4.0 |
| `@MockitoBean` / `@MockitoSpyBean` | `org.springframework.test.context.bean.override.mockito` | Spring Framework 6.2+; current choice for context tests |

Migration example:

```java
// Legacy in Spring Boot 3.x (deprecated since 3.4):
import org.springframework.boot.test.mock.mockito.MockBean;

// Current for Spring Framework >= 6.2:
import org.springframework.test.context.bean.override.mockito.MockitoBean;
```

After updating imports, update the annotations in tests. However, **do not** convert `@Mock` to `@MockitoBean`: unit tests should stay plain Mockito. When moving from Spring Boot 3.3 or earlier, verify your BOM/Framework version because older releases lack the Spring TestContext annotations.

Details around matching, bean overriding, and reset can differ slightly between legacy and current APIs. When migrating, run the full test suite and inspect classes using `@Qualifier`, bean names, context hierarchies, `FactoryBean`, proxies, or multiple implementations.

## 8. Common Mistakes

### 8.1. Putting `@Mock` in a Spring Test and Assuming It Replaced the Bean

```java
@SpringBootTest
class WrongTest {
    @Mock ShippingGateway gateway;
    @Autowired CheckoutService checkoutService;
}
```

Even when `MockitoExtension` initializes the mock, the Spring service still calls `FlatShippingGateway`. Fix: use `@MockitoBean` for context dependencies, or drop Spring and construct the service directly with the mock.

### 8.2. Putting Both `@InjectMocks` and `@Autowired` on the Same Field

```java
@SpringBootTest
@ExtendWith(MockitoExtension.class)
class ConfusingTest {
    @Autowired @InjectMocks CheckoutService checkoutService;
    @Mock ShippingGateway gateway;
}
```

Two frameworks now attempt to initialize/inject the same field, making test semantics unpredictable. Pick one path:
- Plain Java: `MockitoExtension`, `@Mock`, constructor/`@InjectMocks`, no Spring context.
- Spring: `@Autowired` real service, `@MockitoBean` collaborator, no `@InjectMocks`.

### 8.3. Mocking the Very Thing You Want to Test

```java
@SpringBootTest
class TrivialTest {
    @MockitoBean CheckoutService checkoutService;

    @Test
    void onlyChecksStubbing() {
        when(checkoutService.total(100, "HCM")).thenReturn(120);
        assertEquals(120, checkoutService.total(100, "HCM"));
    }
}
```

The test mostly asserts the stub it just configured, **testing nothing of the real service's formula**. Mocking the service makes sense when the SUT is the controller in a web slice. When the SUT is the service, keep the service real and mock the gateway.

### 8.4. Forgetting the Spring Context with `@MockitoBean`

`MockitoExtension` does not process `@MockitoBean`. If a test has no Spring TestContext, bean override annotations cannot override any bean. For non-Spring unit tests, use `@Mock`; for Spring tests, use `@SpringBootTest`/`@WebMvcTest` and the right Spring TestContext imports.

### 8.5. Mocking a Non-Existent Bean and Still Passing

By default, `@MockitoBean` can create a mock bean when no target exists. In full-context tests where the target bean must exist, set `enforceOverride=true` to catch component-scan/profile/config errors.

### 8.6. Ambiguous Beans: Type Alone Is Not Enough

When two beans implement the same interface, `@MockitoBean ShippingGateway gateway` can be ambiguous or pick an unintended candidate via fallback naming. Use `@Qualifier` or `@MockitoBean(name = "...")`. Keep field names consistent across tests that intend to share the Spring context cache.

### 8.7. Mocking a Repository and Claiming Database Verification

`verify(repository).save(...)` only shows the mock received a call. It proves nothing about SQL, JPA mappings, constraints, transactions, or migrations. Use `@DataJpaTest` and suitable database tests for persistence; for end-to-end flows, keep real repositories/DB in integration tests.

### 8.8. Mocking a `@Transactional`/`@Cacheable` Bean and Expecting to Test Proxy Behavior

`@MockitoBean` replaces the bean directly with a mock, so AOP advice on the replaced bean does not run as real behavior. To verify transactions/caching/security, keep that bean real, mock outbound dependencies at the outer boundary, and write proper integration tests.

### 8.9. Spy Accidentally Triggering Side Effects

`when(spy.call()).thenReturn(result)` can run the real method during stubbing. For methods with side effects, use `doReturn(result).when(spy).call()` or mock at the outbound port to prevent unintended emails, DB writes, or network calls.

### 8.10. Assuming Context Caching and Mock Reset Are the Same Thing

Spring can reuse an `ApplicationContext` across tests with compatible configurations. `@MockitoBean` resets Mockito state, yet **does not reset all other state** inside the context or external systems. Tests still need independent fixtures, transactional cleanup, or explicit isolation.

## 9. Impact on Test Slices, Integration Tests, and Performance

| Goal | Appropriate test style | Mock boundary |
| --- | --- | --- |
| Pricing/validation rules in a service | Plain Mockito unit test without Spring | Mock gateway/repository ports |
| HTTP mapping, JSON, validation, exception handlers | `@WebMvcTest` + `MockMvc` | `@MockitoBean` service collaborator |
| Service and bean wiring in full context | `@SpringBootTest` | `@MockitoBean` outbound gateway |
| JPA mappings/queries | `@DataJpaTest` with a database | Do not mock the repository under test |
| Caching, transactions, security advice | Spring context/integration test | Keep the advised bean real |
| REST → service → repository → DB | Integration test with real database | Mock only out-of-scope external systems |
| Selective observation of a real bean | `@MockitoSpyBean` | Spy the right bean; beware side effects |

**Cost:** Plain Java unit mocks load no Spring context and give fast feedback. `@WebMvcTest` loads a slice; `@SpringBootTest` loads the full context. Different mock-bean overrides alter context config/cache keys; varying fallback field names or overusing `@DirtiesContext` forces Spring to boot multiple contexts.

Do not force every test into `@SpringBootTest` just for convenient autowiring. Choose the **smallest boundary sufficient to catch the targeted bug**, keeping real beans wherever the behavior under test lives.

## 10. Diagnosing by Symptom

| Symptom | Likely cause | What to check |
| --- | --- | --- |
| `when(...)` configured yet results still come from the real bean | Java mock was not injected | Is SUT created via `new` or `@Autowired`? Is `@MockitoBean` using the right type? |
| `@Mock` field is `null` | Mockito annotations not initialized | `@ExtendWith(MockitoExtension.class)` or `Mockito.mock(...)` |
| `@MockitoBean` has no effect | Missing Spring TestContext / wrong import | Spring Boot/Framework version and test annotations |
| `@WebMvcTest` fails with `UnsatisfiedDependencyException` | Service is excluded from web slice | Add `@MockitoBean` for service or `@Import` if real service is truly needed |
| Bean override reports multiple candidates | Multiple implementations of the type | Explicit `@Qualifier` or bean name |
| Full-context test passes even though original bean was removed | `REPLACE_OR_CREATE` created a new test bean | Use `enforceOverride = true` if bean existence must be verified |
| Stubbing a spy triggers a real request | Spy ran real method | Use `doReturn` or mock the outbound dependency |
| Mockito reports `UnnecessaryStubbingException` | Unused stub / wrong mock / wrong arguments | Inspect the object graph and actual invocations |
| Full-context test still misses a bug in a mocked gateway | Gateway never ran real implementation | Write tests for the gateway or an appropriate integration test |
| Tests slow from repeated context startups | Divergent mock overrides, qualifiers, properties, `@DirtiesContext` | Group configurations intentionally; prefer unit/slice tests |
| Transactions/security behave unexpectedly | Advised bean was replaced with a mock | Keep the bean real when testing AOP |
| Upgrading to Boot 4 fails to find `@MockBean` | Legacy Spring Boot API scheduled for removal | Migrate to Spring TestContext `@MockitoBean` per version |

Debugging workflow:
1. **Identify the SUT:** which bean holds the logic that must run for real?
2. **Identify the owner:** is the SUT instantiated by the test or by Spring?
3. **Identify collaborators:** which objects are held in the SUT's constructor/fields?
4. **Check mock placement:** is it just a Java variable or a registered bean override?
5. **Check bean selection:** type, name, qualifier, scope, proxy, context hierarchy.
6. **Check assertions:** do they prove real SUT behavior rather than echoing stubs? For persistence/HTTP, assert observable state.

## 11. Going Further: When Extra Care Is Needed

### 11.1. Multiple Context Hierarchies

With `@ContextHierarchy`, bean overrides apply across context levels by default; `@MockitoBean`/`@MockitoSpyBean`'s `contextName` attribute narrows it to the level named via `@ContextConfiguration(name = "...")`. This is an advanced scenario for parent/child contexts; omit it when a project has a single Spring Boot context.

### 11.2. AOP and Mockito Spies

`@MockitoSpyBean` uses the `WRAP` strategy rather than `REPLACE`. When the original bean is wrapped in a Spring proxy, calls through the proxy vs. `verify` on the spy target need careful inspection. Depending on configuration, Spring keeps advice/proxies around the spy; do not assume the proxy and the spy are the exact same Java reference.

### 11.3. Reactive / Asynchronous Code

Mocking methods returning Reactor `Mono`/`Flux` requires stubbing an actual publisher; otherwise subscribing code may hit `null` or missing signals. `verify(mock).send(...)` only confirms the method was called, not that the publisher was subscribed to, the message reached a broker, or a transaction committed. Choose `StepVerifier`, mock servers, Testcontainers, and integration tests matching the behavior to verify.

### 11.4. Never Let Test Mocks Leak into Production

`@MockitoBean` is a **Spring TestContext** tool belonging in the test source set and test annotations. Avoid placing test-double beans inside `src/main` to make the application “easier to start”; that can hide real production configuration bugs. Use clean interfaces and environment-specific configuration when production vs. test implementations differ.

### 11.5. Mockito Strictness

JUnit's `MockitoExtension` flags unused stubs, argument mismatches, and suspicious interactions. If a stub is never called, that often signals the mock was placed in the wrong spot. Never silence warnings globally with `lenient()`; inspect the dependency graph and test intent instead.

## 12. Self-Practice Exercises

1. In `CheckoutServiceContextTest`, change `@MockitoBean` to `@Mock` while keeping `@Autowired CheckoutService`. Predict the total and explain why the mock is never called.
2. In `CheckoutControllerWebTest`, remove `@MockitoBean CheckoutService`. Predict why the MVC slice fails when the controller constructor lacks a service bean.
3. Rewrite `CheckoutServiceUnitTest` using `new CheckoutService(shippingGateway)` instead of `@InjectMocks`. Explain where the dependency gets injected.
4. Add two `ShippingGateway` implementations with qualifiers and test them. Select the right bean using `@MockitoBean(name = "...")` and verify calls from the real service.
5. Register a real gateway bean only under a `production` profile. Compare default `@MockitoBean` vs. `enforceOverride=true` in a full-context test when that profile is inactive.
6. Add a method with side effects to a spied bean. Compare `when(spy.method())` against `doReturn(...).when(spy).method()` and explain the risk.
7. Write a JPA test with a real repository instead of `@MockitoBean Repository`, and verify database state after `saveAndFlush`. What new behavior is now proven?
8. Explain why a full-context test that mocks the service cannot prove `@Transactional` works on the real service.

You have mastered the lesson when you can clearly state: **which object is real, which is fake, whether Spring or Mockito manages it, who injected it, and what the assertions actually prove**.

## 13. Application Checklist

- [ ] Have I clearly identified the SUT and the collaborators to mock?
- [ ] Does the SUT belong to a test-built Java object graph or a Spring `ApplicationContext`?
- [ ] When Spring is unnecessary for a unit, am I using `@Mock`/`Mockito.mock` and constructor injection?
- [ ] When Spring creates the SUT, am I using `@MockitoBean` to replace the right collaborator in the context?
- [ ] When testing an MVC controller, is the service normally `@MockitoBean` inside `@WebMvcTest`?
- [ ] When testing service logic, is the service itself kept as a real bean/object?
- [ ] When the real bean must exist, is `enforceOverride=true` appropriate?
- [ ] When multiple beans share a type, have I specified the exact bean name or `@Qualifier`?
- [ ] If using a spy, have I checked for side effects and AOP proxies?
- [ ] Is the mocked bean carrying transaction/caching/security behavior that I actually meant to test?
- [ ] Do I know the exact Spring Boot/Framework version and the right annotation package?
- [ ] Am I calling `verify` on the exact object actually invoked by the SUT?
- [ ] Does the test assert real results/HTTP/DB outcomes at the boundary rather than only testing stub setup?
- [ ] Could context caching or mock resets hide shared state elsewhere?

**Long-term rule:** `@Mock` mocks Java objects, `@InjectMocks` wires mocks into objects managed by Mockito/the test, and `@MockitoBean` adjusts the bean graph inside **Spring TestContext**. `@MockitoSpyBean` wraps a real bean while allowing original logic to run. Pick the tool based on **who owns the SUT** and **which behavioral boundary needs proof**.

## 14. Official Sources

- Spring Framework 6.2 — `@MockitoBean` and `@MockitoSpyBean`: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html
- Spring Framework — Bean Overriding in Tests, AOP proxies: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/bean-overriding.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 API — `@MockBean` deprecated: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/mock/mockito/MockBean.html
- Mockito — `@InjectMocks` Javadoc: https://javadoc.io/static/org.mockito/mockito-core/5.18.0/org.mockito/org/mockito/InjectMocks.html
- JUnit Jupiter — Extension Model: https://docs.junit.org/5.11.4/user-guide/
