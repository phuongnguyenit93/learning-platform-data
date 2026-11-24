# `@TestBean` or `@TestConfiguration` for Supplying Fakes and Stubs in Spring Boot Tests

When testing a Spring Boot service, we frequently need to replace dependencies—external API clients, pricing engines, clocks, repositories, or payment gateways—with predictable implementations. Two distinct tasks arise here: **replacing a specific existing bean in the context** vs. **adding a test bean so Spring selects it during injection**. `@TestBean` and `@TestConfiguration` serve these goals, yet they are not interchangeable names for the same mechanism.

**`@TestBean`** belongs to Spring TestContext as of **Spring Framework 6.2** (usable in Spring Boot 3.4.x). It specifies a bean to override using an object returned by a **parameterless static factory method** on the test class. **`@TestConfiguration`** belongs to Spring Boot and has existed since earlier Boot releases; it defines one or more test `@Bean` methods, typically added to the main context via nested classes or `@Import`. By default, it **does not delete production beans of the same type**.

Lesson objectives: understand when to use each approach, avoid duplicate-bean or miswired-dependency errors, write controllable fakes/stubs, manage state, and write tests proving **the service actually uses the intended bean**. The end of the lesson includes a runnable example using Java 17, Spring Boot 3.4.5, JUnit Jupiter, and Gradle.

## 1. What are test doubles for?

An application defines an interface:

```java
public interface SurchargePolicy {
    int fee(String region);
}
```

In production, the implementation might fetch tariffs from an external system. In a test verifying total price calculation, we want it to return `7` for any region so results stay predictable. When connecting to the external system lies outside the test's scope, replacing that dependency makes sense.

| Term | Nature | Example | What is being verified |
| --- | --- | --- | --- |
| **Stub** | Returns predetermined outputs | `fee("HN") -> 7` | How service logic handles the value 7 |
| **Fake** | Working yet simplified implementation | In-memory `Map`-backed repository | Business flow against a fake data store |
| **Mockito mock** | Programmable Mockito object for stubbing and verification | `when(policy.fee("HN")).thenReturn(7)` | Outputs and/or contract interactions |
| **Spy** | Tracks an object with real behavior | Spy wrapping an existing bean | Observing interactions while real side effects may still occur |

`@TestBean` or `@TestConfiguration` are solely **ways to place test doubles into a Spring context**; the fake/stub inside can be a plain Java object without Mockito.

A unit test only needs `new QuoteService(new FixedSurchargePolicy(7))` when checking pure Java arithmetic. Only reach for a test context when you also need to prove Spring wired the right collaborator implementation.

## 2. Bean definitions, names, types, and dependency selection

Consider a service using constructor injection:

```java
@Service
class QuoteService {
    private final SurchargePolicy policy;
    QuoteService(SurchargePolicy policy) {
        this.policy = policy;
    }
}
```

Spring must locate a suitable `SurchargePolicy` bean. With one production implementation, resolution is straightforward. Once a test registers an extra fake for the same interface, the outcome depends on how it is registered:

- **Different name, same type, no `@Primary`/qualifier**: risks `NoUniqueBeanDefinitionException` because no single candidate stands out.
- **New bean definition sharing the old bean's name**: risks `BeanDefinitionOverrideException` when Spring Boot disables bean-definition overriding (the standard default).
- **New bean marked `@Primary` with a different name**: selects the fake for unqualified by-type injection; the production bean remains reachable by name.
- **`@TestBean` explicitly overriding the old bean**: in the test context, the target bean name receives the factory's fake instance without creating an extra same-type candidate.

**Decisive distinction:** changing which dependency gets injected is not always the same as replacing **a bean definition under the same name**. `@Primary` alters selection when Spring resolves by type, whereas TestContext Bean Override replaces the target bean itself.

## 3. `@TestBean`: overriding a bean via a static factory

Import:

```java
import org.springframework.test.context.bean.override.convention.TestBean;
```

`@TestBean` applies to **non-static fields** in a test class, supporting bean selection by type/qualifier or explicit name. A parameterless static factory method supplies the instance that replaces the bean in the test `ApplicationContext`.

Illustrative example (complete class in Section 6):

```java
@SpringBootTest
class QuoteWithTestBeanTest {
    @TestBean(
            name = "externalSurchargePolicy",
            methodName = "newFakePolicy",
            enforceOverride = true)
    private SurchargePolicy policy;

    static SurchargePolicy newFakePolicy() {
        return region -> 7;
    }
}
```

**Constraints to remember:**

1. The `policy` field must be an **instance field** whose type matches the bean being overridden; Spring injects the override instance into the field for test inspection.
2. The factory `newFakePolicy` must be **`static`**, take **no parameters**, and have a compatible return type. It is not a `@Bean` factory injected with parameters by the Spring container.
3. `name` identifies the **bean to replace**; when omitted, Spring infers it by type, qualifiers, and field name according to candidate-matching rules.
4. `methodName` is optional if the factory follows Spring's naming convention, though specifying it helps when multiple factories exist or when safely refactoring field names.
5. `enforceOverride=true` requires the target bean to **already exist**. A missing bean or misspelled name fails context loading, catching tests that no longer replace the intended dependency.
6. Leaving the default `enforceOverride=false` lets `REPLACE_OR_CREATE` **create a new bean** if no match exists. That can hide configuration bugs when your intent was replacing a production bean.
7. Overrides apply solely to the **test context**—they never modify production source code or delete the bean in unrelated contexts.

This pattern fits cleanly when supplying a plain Java fake or stub, especially when the production bean talks to external infrastructure that tests should avoid.

### Multiple candidates sharing an interface?

If both `stripePaymentGateway` and `localPaymentGateway` implement `PaymentGateway`, `@TestBean PaymentGateway gateway` does not specify which one to override. Supply `name="stripePaymentGateway"` or `@Qualifier` matching the target bean. Bean overrides do not perform all the complex inference of general autowiring; ambiguous declarations fail test context startup.

### AOP advice from the replaced bean is not inherited automatically

`REPLACE` / `REPLACE_OR_CREATE` overrides in Spring TestContext register a **manual singleton**. The test-provided instance bypasses full production bean post-processing. Never assume `@Transactional`, `@Cacheable`, retry, or security proxies that wrapped the production bean remain attached to your fake.

To test a service's transactions, **keep the service real**, replace only external-system dependencies, and verify transactions against a real repository/database. Replacing the service itself with `@TestBean` strips away evidence of production service advice.

## 4. `@TestConfiguration`: adding test-specific beans and configuration

Import:

```java
import org.springframework.boot.test.context.TestConfiguration;
```

`@TestConfiguration` is a Spring Boot annotation for defining test `@Bean`s. Unlike `@TestBean`, `@Bean` methods inside `@TestConfiguration` can accept container-injected dependencies as parameters. It suits building complex fakes or multiple supporting beans.

Two common organization patterns:

- **Nested static `@TestConfiguration`** inside a test class: Spring Boot includes it alongside the primary app configuration when loading that test's context.
- **Top-level `@TestConfiguration`** in `src/test/java`: normally **excluded** from automatic component scanning; tests opt in explicitly via `@Import(MyTestConfiguration.class)`. This promotes reuse across multiple tests.

Example:

```java
@TestConfiguration(proxyBeanMethods = false)
class PolicyTestConfiguration {
    @Bean("testSurchargePolicy")
    @Primary
    SurchargePolicy fakeSurchargePolicy() {
        return region -> 11;
    }
}
```

The `testSurchargePolicy` bean has a different name from production's `externalSurchargePolicy`. Once imported, both beans can coexist; `@Primary` only causes **by-type** injections to prefer the fake.

**Do not confuse `@Primary` with overriding:** anything using `@Qualifier("externalSurchargePolicy")` or `ApplicationContext.getBean("externalSurchargePolicy")` still receives the production bean. Injecting `List<SurchargePolicy>` receives both real and fake. When the goal is **never instantiating or calling the production bean**, naming `@TestBean` explicitly or restructuring conditional/profile configuration is clearer.

### Why not simply declare a `@Bean` with the production name?

Declaring `@Bean("externalSurchargePolicy")` in test config while production already defines that name does not automatically override it. With bean-definition overriding disabled, the context fails due to the duplicate name. Enabling `spring.main.allow-bean-definition-overriding=true` globally just to dodge the error can mask real configuration conflicts and introduce registration-order fragility. Prefer `@TestBean` for **targeted replacement** or a distinct name + `@Primary` for by-type selection.

## 5. Demo project — versions and structure

This example pins **Java 17, Spring Boot 3.4.5, Spring Framework 6.2.x (managed by Boot)**, Gradle Groovy DSL, and JUnit Jupiter. Selecting Boot **3.4.x** is deliberate because `@TestBean` does not exist in Spring Framework 6.1 / Boot 3.3.

Quote rules:

- `subtotal` must be non-negative; negative values throw `IllegalArgumentException`.
- Total equals `subtotal + surcharge`.
- Real `ExternalSurchargePolicy` returns `35` for `HN`, `20` for `HCM`, and `50` otherwise.
- `@TestBean` replaces the real bean with a fake returning `7`; `@TestConfiguration` adds a `@Primary` fake returning `11`.
- Uses `Math.addExact` to avoid silent `int` overflow.

File tree:

```text
settings.gradle
build.gradle
src/main/java/com/example/beanoverride/BeanOverrideApplication.java
src/main/java/com/example/beanoverride/SurchargePolicy.java
src/main/java/com/example/beanoverride/ExternalSurchargePolicy.java
src/main/java/com/example/beanoverride/QuoteService.java
src/test/java/com/example/beanoverride/FixedSurchargePolicy.java
src/test/java/com/example/beanoverride/QuoteUnitTest.java
src/test/java/com/example/beanoverride/QuoteRealContextTest.java
src/test/java/com/example/beanoverride/QuoteWithTestBeanTest.java
src/test/java/com/example/beanoverride/FakeSurchargeTestConfiguration.java
src/test/java/com/example/beanoverride/QuoteWithTestConfigurationTest.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'spring-test-bean-replacement'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Let Spring Boot manage Spring Framework and JUnit dependencies consistently. Never manually mix `spring-test` 6.2 into a Boot 3.3 project pinned to Framework 6.1 just to gain the new annotations. Use a Gradle Wrapper compatible with your JDK and Boot version.

## 6. Production code: service does not instantiate its dependency directly

**`src/main/java/com/example/beanoverride/BeanOverrideApplication.java`**

```java
package com.example.beanoverride;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BeanOverrideApplication {
    public static void main(String[] args) {
        SpringApplication.run(BeanOverrideApplication.class, args);
    }
}
```

**`src/main/java/com/example/beanoverride/SurchargePolicy.java`**

```java
package com.example.beanoverride;

public interface SurchargePolicy {
    int fee(String region);
}
```

**`src/main/java/com/example/beanoverride/ExternalSurchargePolicy.java`**

```java
package com.example.beanoverride;

import org.springframework.stereotype.Component;

@Component("externalSurchargePolicy")
public class ExternalSurchargePolicy implements SurchargePolicy {
    @Override
    public int fee(String region) {
        return switch (region) {
            case "HN" -> 35;
            case "HCM" -> 20;
            default -> 50;
        };
    }
}
```

The production bean intentionally avoids network calls so the demo runs standalone. When a real app calls remote systems, the test double's value grows even clearer: decoupling service branches from remote instability and cost.

**`src/main/java/com/example/beanoverride/QuoteService.java`**

```java
package com.example.beanoverride;

import org.springframework.stereotype.Service;

@Service
public class QuoteService {
    private final SurchargePolicy policy;

    public QuoteService(SurchargePolicy policy) {
        this.policy = policy;
    }

    public Quote quote(int subtotal, String region) {
        if (subtotal < 0) {
            throw new IllegalArgumentException(
                    "subtotal must be non-negative");
        }
        int surcharge = policy.fee(region);
        return new Quote(
                subtotal,
                surcharge,
                Math.addExact(subtotal, surcharge));
    }

    public record Quote(int subtotal, int surcharge, int total) {
    }
}
```

Constructor injection is a prerequisite for bean replacement to take effect: Spring selects the implementation when creating `QuoteService`. If the service hardcoded `new ExternalSurchargePolicy()` or a static helper internally, neither `@TestBean` nor `@Primary` could swap that call.

## 7. Plain Java fake/stub tests and the baseline context

**`src/test/java/com/example/beanoverride/FixedSurchargePolicy.java`**

```java
package com.example.beanoverride;

public final class FixedSurchargePolicy implements SurchargePolicy {
    private final int fee;

    public FixedSurchargePolicy(int fee) {
        this.fee = fee;
    }

    @Override
    public int fee(String region) {
        return fee;
    }
}
```

This is an **immutable stub** safe to reuse repeatedly with no mutable counters or caches. If you need a fake repository supporting writes and reads, design dedicated reset/isolation when test contexts are cached.

**`src/test/java/com/example/beanoverride/QuoteUnitTest.java`**

```java
package com.example.beanoverride;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class QuoteUnitTest {
    private final QuoteService service =
            new QuoteService(new FixedSurchargePolicy(9));

    @Test
    void computesQuoteWithInjectedStub() {
        assertEquals(
                new QuoteService.Quote(100, 9, 109),
                service.quote(100, "HN"));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> service.quote(-1, "HN"));
    }
}
```

This unit test verifies Java rules and constructor-injected stub behavior. It does not prove which bean Spring selects, since **no context is started**.

**`src/test/java/com/example/beanoverride/QuoteRealContextTest.java`**

```java
package com.example.beanoverride;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

@SpringBootTest
class QuoteRealContextTest {
    @Autowired
    private QuoteService service;

    @Autowired
    private ApplicationContext context;

    @Test
    void originalPolicyIsUsed() {
        assertInstanceOf(
                ExternalSurchargePolicy.class,
                context.getBean("externalSurchargePolicy"));

        assertEquals(
                new QuoteService.Quote(100, 35, 135),
                service.quote(100, "HN"));
    }
}
```

This class loads the production context without overrides or fake imports. It serves as the baseline against which the two bean-replacement tests below are compared.

## 8. `@TestBean` test: fake replaces the exact production bean

**`src/test/java/com/example/beanoverride/QuoteWithTestBeanTest.java`**

```java
package com.example.beanoverride;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.convention.TestBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class QuoteWithTestBeanTest {
    @TestBean(
            name = "externalSurchargePolicy",
            methodName = "createFake",
            enforceOverride = true)
    private SurchargePolicy policy;

    @Autowired
    private QuoteService service;

    @Autowired
    private ApplicationContext context;

    static SurchargePolicy createFake() {
        return new FixedSurchargePolicy(7);
    }

    @Test
    void targetBeanIsOverriddenAndInjected() {
        assertSame(
                policy,
                context.getBean("externalSurchargePolicy"));
        assertInstanceOf(FixedSurchargePolicy.class, policy);
        assertEquals(
                1,
                context.getBeansOfType(SurchargePolicy.class).size());

        assertEquals(
                new QuoteService.Quote(100, 7, 107),
                service.quote(100, "HN"));
    }

    @Test
    void serviceGuardRemainsActive() {
        assertThrows(IllegalArgumentException.class,
                () -> service.quote(-1, "HN"));
    }
}
```

The test verifies three pieces of evidence: **the bean was replaced under the exact name**, **the instance injected into the test is the fake**, and **the real service used the fake to compute 107**. Because `enforceOverride=true`, deleting or renaming the production `externalSurchargePolicy` bean fails the context rather than silently creating a second bean.

`@TestBean` also supports selection by type/qualifier without `name`. When multiple beans share a type, stating the bean name explicitly as shown prevents ambiguity. Here the factory sits inside the test class; for external factories, `methodName` accepts `fully.qualified.Class#staticMethod` per Spring's API.

Note: the fake bean returning 7 is a plain Java object, not a Mockito mock. If a test needs to verify invocations, build a fake that records calls or choose `@MockitoBean` as appropriate.

## 9. `@TestConfiguration` test: adds a primary bean without removing the real bean

A top-level test configuration is added only when a test `@Import`s it.

**`src/test/java/com/example/beanoverride/FakeSurchargeTestConfiguration.java`**

```java
package com.example.beanoverride;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@TestConfiguration(proxyBeanMethods = false)
public class FakeSurchargeTestConfiguration {
    @Bean("testSurchargePolicy")
    @Primary
    public SurchargePolicy testSurchargePolicy() {
        return new FixedSurchargePolicy(11);
    }
}
```

**`src/test/java/com/example/beanoverride/QuoteWithTestConfigurationTest.java`**

```java
package com.example.beanoverride;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertSame;

@SpringBootTest
@Import(FakeSurchargeTestConfiguration.class)
class QuoteWithTestConfigurationTest {
    @Autowired
    private QuoteService service;

    @Autowired
    private ApplicationContext context;

    @Test
    void primaryFakeIsSelectedForTypeInjection() {
        assertInstanceOf(
                ExternalSurchargePolicy.class,
                context.getBean("externalSurchargePolicy"));

        Object fake = context.getBean("testSurchargePolicy");
        assertInstanceOf(FixedSurchargePolicy.class, fake);

        assertEquals(
                2,
                context.getBeansOfType(SurchargePolicy.class).size());
        assertSame(fake, context.getBean(SurchargePolicy.class));

        assertEquals(
                new QuoteService.Quote(100, 11, 111),
                service.quote(100, "HN"));
    }
}
```

In this context, **two** `SurchargePolicy` beans exist: real `externalSurchargePolicy` and fake `testSurchargePolicy`. `@Primary` causes `QuoteService` (which injects by type) to receive the fake. Yet looking up `externalSurchargePolicy` by name still returns the real bean: you cannot claim `@TestConfiguration` eliminated the production dependency across the entire application.

Using a **nested static `@TestConfiguration`** inside the test class makes Spring Boot add that config to the test context without a separate top-level file and `@Import`. Avoid simultaneously declaring a nested config and importing another config with colliding bean names.

## 10. Running and expected results

With a Gradle Wrapper compatible with Boot/JDK, from the project root:

```bash
./gradlew clean test
./gradlew test --tests com.example.beanoverride.QuoteUnitTest
./gradlew test --tests com.example.beanoverride.QuoteRealContextTest
./gradlew test --tests com.example.beanoverride.QuoteWithTestBeanTest
./gradlew test --tests com.example.beanoverride.QuoteWithTestConfigurationTest
```

On Windows, run `gradlew.bat` with the same arguments. These assertions are **designed to PASS** given the original code and compatible dependencies; these are expected outcomes from the examples, **not stdout from an actually executed build**.

| Test | Spring context? | Bean received by service | Quote for `subtotal=100`, `HN` |
| --- | --- | --- | --- |
| `QuoteUnitTest` | No | Direct Java stub, fee 9 | `Quote(100,9,109)` |
| `QuoteRealContextTest` | Yes, default | Real policy, fee 35 | `Quote(100,35,135)` |
| `QuoteWithTestBeanTest` | Yes, bean overridden | Fake replacing `externalSurchargePolicy`, fee 7 | `Quote(100,7,107)` |
| `QuoteWithTestConfigurationTest` | Yes, test bean added | `testSurchargePolicy` marked primary, fee 11 | `Quote(100,11,111)` |

These Spring test classes can use **distinct contexts** because their overrides/imports differ. It is not a single context mutating arbitrarily between test methods. Spring TestContext caching makes context configuration and managing fake mutable state essential.

## 11. When to use Mockito instead of a Java fake

In Spring Framework 6.2, `@MockitoBean` replaces a bean with a Mockito mock. The snippet below is an **excerpt** placed inside a Spring test class with imports:

```java
@MockitoBean(name = "externalSurchargePolicy")
SurchargePolicy policy;

@BeforeEach
void setUp() {
    Mockito.when(policy.fee("HN")).thenReturn(7);
}
```

The matching imports are `org.springframework.test.context.bean.override.mockito.MockitoBean` and `org.mockito.Mockito`. Use this approach when different tests need different responses or when `verify(policy).fee("HN")` must be asserted. For simple, fixed behavior, a Java fake/stub is easier to read and avoids mocking API coupling.

Distinguish this from legacy `@MockBean` in `org.springframework.boot.test.mock.mockito.MockBean`: Boot **deprecated that API in 3.4** in favor of `@MockitoBean`. Never confuse the similar-sounding `@TestBean`, `@MockitoBean`, `@MockBean`, and `@TestConfiguration`; each carries distinct version requirements and semantics.

## 12. Limitations and common mistakes

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Cannot import `@TestBean` | Using Framework 6.1/Boot 3.3 | Upgrade to Boot 3.4+ or use `@TestConfiguration` for your version |
| `@TestBean` fails because target bean does not exist | Wrong name/type, `enforceOverride=true` | Confirm the bean is actually registered in the tested context |
| `@TestBean` factory method not found | Method not static, takes parameters, or wrong name/type | Use static no-arg factory and explicit `methodName` |
| Multiple beans of same type, context fails to start | `@TestConfiguration` adds fake without priority selector | Add `@Primary` or `@Qualifier` at the injection point |
| Duplicate bean definition name error | Test `@Bean` name collides with production, overriding off | Use a distinct name + primary or targeted `@TestBean` |
| `@Primary` set yet something still calls real bean | Dependency uses `@Qualifier`/name or collection injection | Check how each collaborator injects the dependency |
| Test never receives fake | Forgot `@Import`; top-level test config was not loaded | Assert bean identity/type as well as service results |
| Test uses fake yet real external adapter still fails in prod | Adapter integration went untested | Write adapter contract/integration tests with controlled infra |
| Fake retains state from earlier test | Singleton/context cache, unreset collection | Build immutable fakes, reset, or isolate state properly |
| Test skips Spring advice on fake bean | Override registers bare singleton, bypassing regular proxy processing | Keep real services behind proxies; test advice via proper beans/integration |

**Easy-to-miss detail:** `@Primary` affects candidate selection only for by-type injection; an explicit `@Qualifier("externalSurchargePolicy")` still selects the real bean. If your goal is blocking every path to a remote dependency, adding primary alone may not suffice.

**AOP and transactions:** a fake installed with `@TestBean` does not inherit advice from the replaced bean. Replacing a payment client to test business logic makes sense; replacing an entire transactional service and claiming rollback works has no supporting evidence.

**Context caching and isolation:** a singleton fake holding a `List` or `Map` can be mutated across tests sharing a context; `@TestInstance(PER_METHOD)` only recreates JUnit test instances, not Spring contexts. Reset appropriately in `@BeforeEach`, isolate test data, or choose immutable fakes. Reserve `@DirtiesContext` for when a fresh context is truly needed, given its time cost.

## 13. Counter-experiments to catch wrong bean replacement setups

Try these on a **copy of the example** and revert afterward:

1. Remove `@Primary` from `FakeSurchargeTestConfiguration`: with two differently named `SurchargePolicy` beans and by-type injection on `QuoteService`, candidate selection turns ambiguous and context loading fails.
2. Rename the production bean while keeping `@TestBean(name="externalSurchargePolicy", enforceOverride=true)`: context override must fail instead of silently creating a second bean.
3. Remove `@Import(FakeSurchargeTestConfiguration.class)`: the service uses the real fee 35; asserting 111 must fail.
4. Change `new FixedSurchargePolicy(7)` to `new FixedSurchargePolicy(8)`: `QuoteWithTestBeanTest` must fail on `Quote(100,7,107)`.
5. Add `@Qualifier("externalSurchargePolicy")` to a collaborator's dependency: in the `@TestConfiguration` context, that collaborator receives the real bean even though the test bean is `@Primary`.
6. Give the fake a mutable counter across multiple test methods and drop cleanup: running tests individually vs. as a suite can yield different results—a sign of shared state, not JUnit ordering bugs.

Good evidence goes beyond "context loaded successfully." Verify **the actual injected object**, **return values**, and the exact scope the test double replaced.

## 14. Review checklist for tests using Spring fakes/stubs

- Do the Java/Spring Boot versions support the annotations being used?
- Is the intent to **override an existing bean** or **add a new bean and steer injection choice**?
- With `@TestBean`, is the field non-static and the static factory parameterless and type-compatible? Should `enforceOverride=true` be enabled to catch config errors?
- With `@TestConfiguration`, is the class in test sources, nested or explicitly `@Import`ed by the right tests? Does any new bean name accidentally collide with production?
- When using `@Primary`, do collaborators actually inject by type? Do qualifiers, names, or collection injections change behavior?
- Do tests assert both bean identity/type and business outputs rather than just "context loads"?
- Does the fake hold mutable state, singleton data, or external DB state? Who resets/cleans it up, and is it safe under parallel runs?
- Does the overridden bean carry critical AOP/transaction/security advice that requires real integration testing?
- Are there separate contract tests for the real adapter so green fake tests are not mistaken for working production infrastructure?

**Conclusion:** **`@TestBean` (Spring Framework 6.2+) fits when you want to explicitly replace a specific bean with a fake/stub from a static factory**, especially with `name` and `enforceOverride=true`. **`@TestConfiguration` fits when adding test configuration**, letting you supply fakes via `@Bean` + `@Primary` or clear injection setups. Both only establish evidence for the test context; proving business rules and infrastructure work requires solid assertions and integration/contract tests at the right boundaries.

## Official references

- Spring Framework 6.2 — `@TestBean`: https://docs.spring.io/spring-framework/docs/6.2.4/javadoc-api/org/springframework/test/context/bean/override/convention/TestBean.html
- Spring Framework — Bean Overriding in Tests: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/bean-overriding.html
- Spring Boot 3.4 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.4/reference/testing/spring-boot-applications.html
- Spring Boot 3.4 — `@TestConfiguration` API: https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/context/TestConfiguration.html
