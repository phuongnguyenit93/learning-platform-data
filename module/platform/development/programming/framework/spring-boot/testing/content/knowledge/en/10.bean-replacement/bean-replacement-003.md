# Selecting Beans by Type, Name, and Qualifier with Multiple Candidates in Spring Boot Tests

## 1. Objective

Suppose an application has two beans implementing the `ShippingGateway` interface:

- `economyGateway`: standard shipping, fee 10.
- `expressGateway`: express shipping, fee 30.

The real `QuoteService` uses `expressGateway` via constructor injection. In a test, if you want to mock only `expressGateway` to return fee 55 while keeping `economyGateway` real, how does Spring know **exactly which bean to replace**?

That is the goal of this lesson: understanding and applying bean selection by **type**, **bean name**, **`@Qualifier`**, and `@MockitoBean`'s **field name fallback** rule. It also covers multiple-candidate scenarios, `@Primary` effects, accidental mock creation from typos, `enforceOverride` rules, and how to verify a bean was genuinely replaced in `ApplicationContext`.

After this lesson, you will be able to:
- Map out bean candidates for an interface and identify a service's injection point.
- Choose the right `@MockitoBean` syntax at field or class level when targeting a specific bean.
- Resolve ambiguity with explicit `name` or `@Qualifier`, understanding the limits of relying on field names.
- Distinguish **bean names** from **qualifier metadata** and from **Java variable names**.
- Apply `@MockitoSpyBean` to the exact target while preserving other beans.
- Write JUnit/Spring Boot tests capable of catching "test passed because a new bean was created" instead of replacing the production bean.
- Diagnose `NoUniqueBeanDefinitionException`, bean override errors, and dependency injection bypassing mocks.

Technical context: **Java 17+, Spring Boot 3.5.16, Spring Framework 6.2, JUnit Jupiter, Mockito**. Spring Boot 3.4–3.5 uses `org.springframework.test.context.bean.override.mockito.MockitoBean` and `MockitoSpyBean`. For other versions, check the corresponding documentation before copying annotations/imports.

## 2. Two independent choices: the bean Spring injects into the service vs. the bean the test overrides

First, separate **two decisions**:

1. **Production wiring:** which bean Spring selects to inject into `QuoteService`'s constructor/field.
2. **Test bean override:** which bean Spring TestContext selects to replace with a Mockito mock/spy **before the test context is used**.

They are related but not identical. A test annotation only produces the intended effect if it targets the exact bean that the service receives.

```text
Application's ApplicationContext
  |
  +-- economyGateway : ShippingGateway (real implementation, fee 10)
  |
  +-- expressGateway : ShippingGateway (real implementation, fee 30)
  |
  +-- quoteService   : QuoteService
          |
          +-- constructor @Qualifier("expressGateway")
                    -> expressGateway

Correct override test ApplicationContext:
  economyGateway : real bean (fee 10)
  expressGateway : Mockito mock (stubbed fee 55)
  quoteService   : real bean -> expressGateway mock
```

If a test creates `ShippingGateway mock = Mockito.mock(...)` without placing it into the context, the Spring-managed `QuoteService` still uses the real `expressGateway`. If the test overrides the **wrong** `economyGateway`, the service still uses the real `expressGateway`. If the test creates a new bean named `typoGateway`, the service still uses the real `expressGateway`.

**Simply having "a mock in the test" is not enough. Ask: which bean name is the mock replacing, and where does the call from the service actually go?**

## 3. Core terminology

| Concept | Meaning | Example |
| --- | --- | --- |
| Bean type | Java type of the bean, possibly an interface/superclass | `ShippingGateway` |
| Bean name | Unique identifier within a context; can be declared explicitly and have aliases | `"expressGateway"` |
| Bean candidate | Bean matching the type and other autowiring rules | Two implementations of `ShippingGateway` |
| `@Qualifier` | Metadata/constraint used to filter candidates by type | `@Qualifier("expressGateway")` |
| Field name fallback | When no qualifier is present, the **test field name** can act as a fallback qualifier for override | `@MockitoBean ShippingGateway expressGateway;` |
| `@Primary` | Prioritizes a bean when Spring autowires with multiple eligible candidates | `@Primary` on one implementation |
| Bean override | Spring TestContext replaces or wraps a bean in the test context | `@MockitoBean` or `@MockitoSpyBean` |
| SUT | System under test: the object whose real behavior is being verified | `QuoteService` |
| Mock | Mockito test double, does not execute real implementation by default | `when(mock.fee("HCM")).thenReturn(55)` |
| Spy | Wrapper tracking a real bean, calls real method unless stubbed | `@MockitoSpyBean(name="expressGateway")` |

**A bean name is not synonymous with a class name or interface name.** A bean from `@Component` usually derives its name from the class per Spring naming rules. A `@Bean` method bean typically takes the method name unless configured otherwise. When multiple implementations exist, assign clear names, especially for adapters with distinct business roles.

**`@Qualifier("fast")` is not always a request for a bean named `fast`.** A qualifier filters among type-compatible beans: it can match a bean name or declared qualifier metadata. Conversely, `@MockitoBean(name="fast")` targets a specific **bean name**. If a real bean is named `expressGateway` but carries custom qualifier metadata `fast`, those two forms can select differently.

## 4. Bean selection rules of `@MockitoBean` in Spring Framework 6.2

### 4.1. Placed on a field: type first, qualifier/name to disambiguate

```java
@MockitoBean
ShippingGateway shippingGateway;
```

First Spring inspects the **field type** (`ShippingGateway`). If exactly one matching bean exists, it can replace that bean. If multiple matching beans exist, Spring needs a disambiguator:
- `@Qualifier` on the field.
- Or, if `@Qualifier` is absent, the Java field name serves as a **fallback qualifier**.
- Or specifying the exact bean name via `@MockitoBean`'s `name`/`value` attribute.

When a context has only a single `pricingService` bean of type `PricingService`, writing `@MockitoBean PricingService pricingService;` suffices. But with two `ShippingGateway` beans, `@MockitoBean ShippingGateway gateway;` is ambiguous because no bean is named `gateway` and no qualifier narrows down a single candidate.

### 4.2. Three ways to specify the target explicitly

**Approach A — specify the bean name directly:**

```java
@MockitoBean(name = "expressGateway", enforceOverride = true)
ShippingGateway mockExpress;
```

This is the easiest choice to audit when you know the bean's registered name. The field name `mockExpress` need not match the bean name because `name` already identifies the target.

**Approach B — use `@Qualifier` on the override field:**

```java
@MockitoBean
@Qualifier("expressGateway")
ShippingGateway selectedGateway;
```

Use this when the project already relies on qualifiers in wiring. Spring filters `ShippingGateway` beans by the qualifier value. `@Qualifier` requires `import org.springframework.beans.factory.annotation.Qualifier`.

**Approach C — rely on the field name as a fallback qualifier:**

```java
@MockitoBean
ShippingGateway expressGateway;
```

If a type-compatible bean named `expressGateway` exists, Spring can select it via field-name fallback. This is concise but fragile when refactoring field names. With multiple candidates serving distinct roles, prefer **explicit name/qualifier** so test intent does not depend on an incidental variable name.

### 4.3. Comparison of declarations and outcomes

| Test declaration | Context has `economyGateway` and `expressGateway` | Expected outcome |
| --- | --- | --- |
| `@MockitoBean ShippingGateway gateway;` | Two beans of same type; no target named `gateway` | Ambiguous; context can fail while processing overrides |
| `@MockitoBean ShippingGateway expressGateway;` | Bean named `expressGateway` exists | Field-name fallback selects express |
| `@MockitoBean @Qualifier("expressGateway") ShippingGateway target;` | Candidate by qualifier/name | Selects express |
| `@MockitoBean(name="expressGateway") ShippingGateway target;` | Bean name express exists | Selects express |
| `@MockitoBean(name="economyGateway") ShippingGateway target;` | Bean name economy exists | Selects economy; service using express remains real |
| `@MockitoBean(name="expresGateway") ShippingGateway target;` | Typo in name; default `REPLACE_OR_CREATE` | May create a **new mock bean**; real express is unreplaced |
| `@MockitoBean(name="expresGateway", enforceOverride=true) ShippingGateway target;` | No bean with that name exists | Context fails, catching the typo |
| `@MockitoBean QuoteService quoteService;` | Only one QuoteService bean | Replaces service by type; does not test real service logic |

Check **both the replaced bean and the unreplaced bean**. A lone `verify(mock).fee("HCM")` does not prove the entire object graph is wired as intended if the test calls the mock directly or the SUT itself is mocked.

### 4.4. `value` as an alias for `name`

```java
@MockitoBean("expressGateway")
ShippingGateway gateway;
```

This shorthand works when no other attributes are needed. In the exercises below, `name="expressGateway"` is used for clarity and to pair with `enforceOverride=true`.

### 4.5. Note on `@Primary`

`@Primary` prioritizes a candidate when Spring autowires a dependency by type across multiple implementations. However, **bean overrides follow their own target-selection logic** based on type, field qualifier, field-name fallback, and explicit name. Do not assume marking a bean `@Primary` ensures a test always mocks that bean, especially when replacing a non-`@Primary` bean.

If the production service explicitly uses `@Qualifier("expressGateway")`, the override must target `expressGateway`; even if `economyGateway` has `@Primary`, the service's explicit qualifier determines its dependency under Spring's wiring rules.

## 5. Distinguishing `@Qualifier` for DI vs. `@Qualifier` on a test field

Two common placements:

```java
@Service
class QuoteService {
    private final ShippingGateway gateway;

    QuoteService(@Qualifier("expressGateway") ShippingGateway gateway) {
        this.gateway = gateway;
    }
}
```

```java
@SpringBootTest
class QuoteServiceTest {
    @MockitoBean
    @Qualifier("expressGateway")
    ShippingGateway selected;

    @Autowired
    QuoteService quoteService;
}
```

The qualifier **on the constructor** tells Spring to inject the implementation matching that qualifier. The qualifier **on the test field** tells the override mechanism which target bean to locate. These are two distinct selection points; normally both must point to the same bean if you expect stubbing to affect the service.

Consider a bean whose name differs from its qualifier metadata:

```java
// Illustrative snippet outside the sample project:
@Bean("expressGateway")
@Qualifier("priority")
ShippingGateway expressGateway() {
    return new ExpressGateway();
}
```

When multiple beans of the same type exist:
- `@Qualifier("priority")` can filter down to bean `expressGateway` via qualifier metadata if that label uniquely identifies it.
- `@MockitoBean(name = "expressGateway")` selects the bean named express.
- `@MockitoBean(name = "priority")` looks for a bean **named priority**; it does not interpret `priority` as qualifier metadata. Without a bean of that name and without enforcement, it may **create a new mock bean**.

Therefore, whenever you encounter a label like `"priority"`, check whether it is a bean name, alias, or qualifier. Never assume a `@Qualifier` string is always a bean name.

### 5.1. Qualifiers need not be unique

Spring allows using one qualifier value as a tag across multiple beans, particularly when injecting `List<ShippingGateway>` or `Set<ShippingGateway>`. If two beans both carry `@Qualifier("fast")`, `@MockitoBean @Qualifier("fast") ShippingGateway gateway;` is still insufficient to pick **one** bean. Specify a concrete name or separate qualifiers according to contract.

### 5.2. Bean names and aliases

The Spring bean registry can associate one or more aliases with a bean. When overriding a candidate, use the clearly configured canonical bean name, inspect context metadata when debugging, and avoid coupling tests to aliases likely to drift during refactoring. This helps in projects using `@Bean(name={"expressGateway","fastShipping"})` or importing configurations across modules.

### 5.3. Fallback field names affect the context cache

Spring TestContext factors qualifiers, including fallback field names, into determining whether a context configuration can be reused. Two test classes overriding the same bean with different field names can produce different **cache keys**, forcing Spring to start more contexts.

Therefore:
- For the same target bean, pick consistent field names and qualifiers.
- For easily confused beans, explicit `name` helps reviewers immediately recognize the target.
- Do not force unrelated tests to share unnecessary mocks solely for cache hits: accurate test boundaries matter more than micro-optimization.

## 6. Complete runnable demo: two beans implementing one interface

The project below demonstrates six test styles, two intentional failure cases, and the difference between "a mock was created" and "the right bean was replaced."

### 6.1. Maven layout

```text
bean-selection-lab/
├── pom.xml
├── src/main/java/com/example/beanselection/
│   ├── BeanSelectionApplication.java
│   ├── ShippingGateway.java
│   ├── EconomyGateway.java
│   ├── ExpressGateway.java
│   └── QuoteService.java
└── src/test/java/com/example/beanselection/
    ├── OriginalWiringTest.java
    ├── UniqueTypeOverrideTest.java
    ├── NamedOverrideTest.java
    ├── QualifierOverrideTest.java
    ├── FieldNameFallbackTest.java
    ├── ClassLevelOverrideTest.java
    ├── SelectedSpyTest.java
    ├── WrongNameCreatesBeanTest.java
    ├── AmbiguousOverrideExercise.java
    └── MissingTargetExercise.java
```

All `*Test` classes are designed to PASS. The two `*Exercise` classes are designed to FAIL when run individually, so Maven Surefire's default test naming pattern excludes them.

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
  <artifactId>bean-selection-lab</artifactId>
  <version>1.0.0</version>
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
</project>
```

`spring-boot-starter-test` provides JUnit Jupiter, Mockito, and Spring TestContext under Spring Boot's dependency management. The project needs no web server, database, or Docker.

### 6.3. Application and two implementations

`src/main/java/com/example/beanselection/BeanSelectionApplication.java`:

```java
package com.example.beanselection;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BeanSelectionApplication {
    public static void main(String[] args) {
        SpringApplication.run(BeanSelectionApplication.class, args);
    }
}
```

`src/main/java/com/example/beanselection/ShippingGateway.java`:

```java
package com.example.beanselection;

public interface ShippingGateway {
    int fee(String city);
}
```

`src/main/java/com/example/beanselection/EconomyGateway.java`:

```java
package com.example.beanselection;

import org.springframework.stereotype.Component;

@Component("economyGateway")
public class EconomyGateway implements ShippingGateway {
    @Override
    public int fee(String city) {
        return 10;
    }
}
```

`src/main/java/com/example/beanselection/ExpressGateway.java`:

```java
package com.example.beanselection;

import org.springframework.stereotype.Component;

@Component("expressGateway")
public class ExpressGateway implements ShippingGateway {
    @Override
    public int fee(String city) {
        return 30;
    }
}
```

`src/main/java/com/example/beanselection/QuoteService.java`:

```java
package com.example.beanselection;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class QuoteService {
    private final ShippingGateway gateway;

    public QuoteService(@Qualifier("expressGateway") ShippingGateway gateway) {
        this.gateway = gateway;
    }

    public int total(int subtotal, String city) {
        if (subtotal < 0) {
            throw new IllegalArgumentException("subtotal must be >= 0");
        }
        return subtotal + gateway.fee(city);
    }
}
```

Without mocks: `total(100,"HCM") = 100 + 30 = 130`. The `economyGateway` bean still exists but is not selected by `QuoteService`. This is the key setup for the tests below.

### 6.4. Test #1 — No override: confirm baseline wiring

`src/test/java/com/example/beanselection/OriginalWiringTest.java`:

```java
package com.example.beanselection;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class OriginalWiringTest {
    @Autowired QuoteService quoteService;
    @Autowired ApplicationContext context;

    @Test
    void serviceUsesExpressAndBothBeansExist() {
        assertEquals(130, quoteService.total(100, "HCM"));
        assertEquals(10,
                context.getBean("economyGateway", ShippingGateway.class)
                        .fee("HCM"));
        assertEquals(30,
                context.getBean("expressGateway", ShippingGateway.class)
                        .fee("HCM"));
        assertTrue(context.containsBean("economyGateway"));
        assertTrue(context.containsBean("expressGateway"));
    }
}
```

This test confirms the **real configuration**: both beans are present and the service picks express. It acts as a baseline to understand all changes in the override tests.

### 6.5. Test #2 — Single `QuoteService`: override by type

`src/test/java/com/example/beanselection/UniqueTypeOverrideTest.java`:

```java
package com.example.beanselection;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.mockito.Mockito.when;

@SpringBootTest
class UniqueTypeOverrideTest {
    @MockitoBean(enforceOverride = true)
    QuoteService quoteService;

    @Autowired ApplicationContext context;

    @Test
    void uniqueTypeIdentifiesServiceBean() {
        when(quoteService.total(100, "HCM")).thenReturn(999);

        assertEquals(999, quoteService.total(100, "HCM"));
        assertSame(quoteService, context.getBean(QuoteService.class));
    }
}
```

Because only one `QuoteService` exists, type alone selects the target. This test **does not test QuoteService logic** since it mocks the service itself; its sole aim is proving selection by type. In business unit tests, keep the service real and mock the gateway.

### 6.6. Test #3 — Multiple gateways: override by bean name

`src/test/java/com/example/beanselection/NamedOverrideTest.java`:

```java
package com.example.beanselection;

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
class NamedOverrideTest {
    @MockitoBean(name = "expressGateway", enforceOverride = true)
    ShippingGateway target;

    @Autowired QuoteService quoteService;
    @Autowired ApplicationContext context;

    @Test
    void replacesExpressAndLeavesEconomyReal() {
        when(target.fee("HCM")).thenReturn(55);

        assertEquals(155, quoteService.total(100, "HCM"));
        verify(target).fee("HCM");

        assertSame(target,
                context.getBean("expressGateway", ShippingGateway.class));
        assertEquals(10,
                context.getBean("economyGateway", ShippingGateway.class)
                        .fee("HCM"));
    }
}
```

The test field is named `target`, while the annotation explicitly sets `expressGateway`, so Spring replaces the right express bean. The test asserts output from the real service (155), the context instance, and that economy still works with fee 10.

### 6.7. Test #4 — Override by `@Qualifier`

`src/test/java/com/example/beanselection/QualifierOverrideTest.java`:

```java
package com.example.beanselection;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringBootTest
class QualifierOverrideTest {
    @MockitoBean
    @Qualifier("expressGateway")
    ShippingGateway selected;

    @Autowired QuoteService quoteService;

    @Test
    void qualifierSelectsTheCorrectCandidate() {
        when(selected.fee("HCM")).thenReturn(55);

        assertEquals(155, quoteService.total(100, "HCM"));
        verify(selected).fee("HCM");
    }
}
```

The field name is `selected`, different from the bean name. `@Qualifier("expressGateway")` distinguishes the two candidates. In real apps with qualifier metadata distinct from bean names, this also selects the target by metadata rather than exact bean name.

### 6.8. Test #5 — Fallback by field name

`src/test/java/com/example/beanselection/FieldNameFallbackTest.java`:

```java
package com.example.beanselection;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.when;

@SpringBootTest
class FieldNameFallbackTest {
    @MockitoBean
    ShippingGateway expressGateway;

    @Autowired QuoteService quoteService;

    @Test
    void fieldNameActsAsFallbackQualifier() {
        when(expressGateway.fee("HCM")).thenReturn(55);

        assertEquals(155, quoteService.total(100, "HCM"));
    }
}
```

This is a **fallback** rule, not a mechanism to name a bean via annotation. Renaming `expressGateway` to `gateway` while both candidates exist would cause context loading to fail due to insufficient selection info.

### 6.9. Test #6 — Class-level override with `types` and `name`

`src/test/java/com/example/beanselection/ClassLevelOverrideTest.java`:

```java
package com.example.beanselection;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.when;

@SpringBootTest
@MockitoBean(
        types = {ShippingGateway.class},
        name = "expressGateway",
        enforceOverride = true)
class ClassLevelOverrideTest {
    @Autowired QuoteService quoteService;

    @Autowired
    @Qualifier("expressGateway")
    ShippingGateway mockExpress;

    @Test
    void typeLevelDeclarationTargetsNamedBean() {
        when(mockExpress.fee("HCM")).thenReturn(55);

        assertEquals(155, quoteService.total(100, "HCM"));
    }
}
```

When placed on a **class**, `types` must be declared because there is no field from which to infer the type. When `name` is specified, the `types` list must contain **one type**; to replace multiple differently named beans, use multiple repeatable `@MockitoBean` annotations or controlled configuration.

### 6.10. Test #7 — Spying exactly one bean among multiple candidates

`src/test/java/com/example/beanselection/SelectedSpyTest.java`:

```java
package com.example.beanselection;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;

@SpringBootTest
class SelectedSpyTest {
    @MockitoSpyBean(name = "expressGateway")
    ShippingGateway expressGateway;

    @Autowired QuoteService quoteService;

    @Test
    void spyTargetsOneRealBeanWithoutReplacingBehavior() {
        assertEquals(130, quoteService.total(100, "HCM"));
        verify(expressGateway).fee("HCM");
    }
}
```

`@MockitoSpyBean` uses the **WRAP** strategy and requires exactly one existing matching bean. Without stubbing, `ExpressGateway`'s real method runs, so the fee remains 30. `@MockitoBean` replaces the entire bean with a mock whose unstubbed methods return default values (typically 0 for `int`).

When a spied method has side effects, `when(spy.method()).thenReturn(value)` can invoke the real method during stubbing; prefer `doReturn(value).when(spy).method()` when side effects must be avoided.

### 6.11. Test #8 — Wrong name silently creates an extra mock bean

`src/test/java/com/example/beanselection/WrongNameCreatesBeanTest.java`:

```java
package com.example.beanselection;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class WrongNameCreatesBeanTest {
    // Intentional typo: "expresGateway" (missing an s).
    @MockitoBean(name = "expresGateway")
    ShippingGateway newMock;

    @Autowired QuoteService quoteService;
    @Autowired ApplicationContext context;

    @Test
    void newMockDoesNotReplaceRealExpressBean() {
        assertTrue(context.containsBean("expresGateway"));
        assertTrue(context.containsBean("expressGateway"));
        assertEquals(130, quoteService.total(100, "HCM"));
    }
}
```

This is a **positive test illustrating a trap**, not an application testing strategy: because `@MockitoBean` defaults to `REPLACE_OR_CREATE`, a new mock bean named `expresGateway` gets created. The service with `@Qualifier("expressGateway")` still uses the real express bean and returns 130. Never infer "the test uses `@MockitoBean`, so the old bean was definitely replaced."

To catch typos when your intent is replacing an **existing** bean, use `enforceOverride = true` as in Test #3.

### 6.12. Run commands

In the `bean-selection-lab` directory with JDK 17+ and Maven:

```bash
mvn -q clean test
mvn -q -Dtest=NamedOverrideTest test
mvn -q -Dtest=QualifierOverrideTest test
mvn -q -Dtest=FieldNameFallbackTest test
mvn -q -Dtest=ClassLevelOverrideTest test
mvn -q -Dtest=SelectedSpyTest test
mvn -q -Dtest=WrongNameCreatesBeanTest test
```

All `*Test`-suffixed classes are designed to PASS with the configuration and versions above. Maven returns exit code 0 when all tests succeed; Spring logs, execution order, and timing stats vary by environment.

Expected asserted behavior:

| Class | Which mock/spy | Result of `quoteService.total(100,"HCM")` |
| --- | --- | --- |
| `OriginalWiringTest` | No mock | 130 |
| `UniqueTypeOverrideTest` | Mocks QuoteService itself | Stub returns 999; real service not tested |
| `NamedOverrideTest` | Mocks express by name | 155 |
| `QualifierOverrideTest` | Mocks express by qualifier | 155 |
| `FieldNameFallbackTest` | Mocks express via field name | 155 |
| `ClassLevelOverrideTest` | Mocks express at class level | 155 |
| `SelectedSpyTest` | Spies real express | 130 |
| `WrongNameCreatesBeanTest` | Creates new mock bean with typo | 130 |

No standalone `javac` is needed: tests use Spring/JUnit/Mockito on Maven's test classpath; the reproducible command is `mvn test` (or `mvn -q clean test` in a clean environment).

## 7. Two exercises that intentionally trigger context errors

The following classes are named `*Exercise` so Surefire skips them by default; run them only when observing the errors. **Do not** include them in a default CI suite expected to PASS.

### 7.1. Missing qualifier with two candidates

`src/test/java/com/example/beanselection/AmbiguousOverrideExercise.java`:

```java
package com.example.beanselection;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest
class AmbiguousOverrideExercise {
    // "gateway" matches neither "economyGateway" nor "expressGateway".
    @MockitoBean
    ShippingGateway gateway;

    @Test
    void contextCannotChooseBetweenTwoGatewayBeans() {
        // Should not reach this method when context override is ambiguous.
    }
}
```

Run:

```bash
mvn -Dtest=AmbiguousOverrideExercise test
```

This test is expected to **FAIL while loading ApplicationContext**: Spring finds multiple beans matching `ShippingGateway` and no qualifier/fallback name resolves a single target. Read the bean override root cause rather than fixing it by deleting one of the production implementations.

Intended fix: add `@Qualifier("expressGateway")`, change to `@MockitoBean(name="expressGateway")`, or name the field `expressGateway` if relying on fallback. Prefer explicit selection matching the contract.

### 7.2. Nonexistent bean name with `enforceOverride=true`

`src/test/java/com/example/beanselection/MissingTargetExercise.java`:

```java
package com.example.beanselection;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest
class MissingTargetExercise {
    @MockitoBean(name = "expresGateway", enforceOverride = true)
    ShippingGateway gateway;

    @Test
    void cannotReplaceNonexistentNamedBean() {
        // Does not run because no bean named "expresGateway" exists.
    }
}
```

Run:

```bash
mvn -Dtest=MissingTargetExercise test
```

Expected to FAIL during context preparation because **REPLACE** mode requires an existing bean. Unlike `WrongNameCreatesBeanTest` without enforcement, where a new mock is created and the test can pass despite the real bean remaining untouched.

Fix `"expresGateway"` to `"expressGateway"` to match the actual project bean name. Note that exact timing/stack trace details depend on Spring Framework/Maven/Surefire; do not treat any summarized message in this lesson as verbatim stdout.

## 8. Multiple candidates: how to decide step by step

When opening a real project, follow this sequence:

1. **Identify the type** required by the collaborator, e.g., `PaymentPort`.
2. **List bean definitions of that type** and their actual bean names. Never guess from class names; `@Bean` methods, `@Component("name")`, aliases, profiles, and `@Conditional` can change the list.
3. **Inspect the SUT's injection point**: does the constructor use `@Qualifier`? `@Primary`? Bean name? `Map<String,PaymentPort>` or list injection?
4. **Identify the override target**: which bean actually produces side effects or returns data to simulate?
5. **Choose explicit syntax**: `@MockitoBean(name="...")` when the bean name is known; `@MockitoBean @Qualifier("...")` if the project disambiguates by qualifier metadata; use type alone only when unique.
6. **Consider `enforceOverride=true`** when the test should FAIL if the target bean was not created by application configuration.
7. **Verify via behavior**: stub the mock → call the real SUT → assert outputs/side effects; confirm other beans were not mistakenly overridden.
8. **Keep the test context scoped properly**: slice tests contain only a subset of beans; having fewer candidates than the full app is normal and should be understood.

Example checking registered beans by type in a context test:

```java
// Illustrative snippet in a test with @Autowired ApplicationContext context:
Map<String, ShippingGateway> beans =
        context.getBeansOfType(ShippingGateway.class);
System.out.println(beans.keySet());
```

Requires `import java.util.Map`. In the sample project with no override, this type's map contains at least `economyGateway` and `expressGateway`. Key set iteration order is not a contract; do not assert an unspecified map order. With a mock bean, `getBeansOfType` also reveals newly registered names if `REPLACE_OR_CREATE` occurs.

A clear verification when multiple candidates exist:

```java
ShippingGateway express =
        context.getBean("expressGateway", ShippingGateway.class);
ShippingGateway economy =
        context.getBean("economyGateway", ShippingGateway.class);

assertThat(Mockito.mockingDetails(express).isMock()).isTrue();
assertThat(Mockito.mockingDetails(economy).isMock()).isFalse();
```

This is an **illustrative snippet** when a test uses `@MockitoBean(name="expressGateway")` and imports AssertJ/Mockito. With proxied or spied beans, `mockingDetails(...).isMock()` may require checking target vs. proxy; do not treat it as the sole criterion across all AOP architectures. In the simple demo project, this check has direct meaning.

## 9. Replacing the wrong bean: symptoms and causes

### 9.1. Stub is configured but the SUT still runs the real implementation

```java
@MockitoBean(name = "economyGateway")
ShippingGateway economy;

@Autowired QuoteService quoteService;

@Test
void wrongTarget() {
    when(economy.fee("HCM")).thenReturn(55);
    // QuoteService uses expressGateway, so it still returns 130.
    assertEquals(130, quoteService.total(100, "HCM"));
}
```

This is an **illustrative snippet**, not a standalone file. If you expected 155 but got 130, you likely mocked `economyGateway` by mistake. Spring will not redirect the service's injection point to economy just because a test replaced the economy bean.

Under Mockito strictness, unused stubs can emit warnings or errors depending on runner and mock setup. When diagnosing, check the target and actual call path rather than adding `lenient()` to hide it.

### 9.2. Field name changed during refactoring shifts the override target

Initially:

```java
@MockitoBean ShippingGateway expressGateway;
```

After refactoring only the field name:

```java
@MockitoBean ShippingGateway gateway;
```

With two candidates in the context, bean selection shifts from "chose express via fallback" to "ambiguous." That is why explicit `name`/`@Qualifier` is usually preferable for important tests.

### 9.3. `@Primary` misunderstood as "tests will override primary"

Production `@Autowired` may select a `@Primary` bean, but `@MockitoBean`'s override mechanism relies on type and test qualifier/name. If a test needs to replace a specific non-primary implementation, state the target explicitly. In complex projects, inspect the context's bean definitions to confirm resolution before modifying tests.

### 9.4. `@Qualifier` placed in the wrong location

```java
@MockitoBean
ShippingGateway mockExpress;

@Autowired
@Qualifier("expressGateway")
QuoteService quoteService;
```

This example **makes no sense** if `QuoteService` has only one bean and `@Qualifier` was placed on the **QuoteService** field instead of `ShippingGateway`: it does nothing to disambiguate `ShippingGateway` candidates for override. The qualifier must be on the **mock field being selected** (or explicit `name` on `@MockitoBean`), and the service's injection point must carry its qualifier if production wiring requires it.

### 9.5. Slice tests create a mock without a production bean

In `@WebMvcTest`, service collaborators usually lack real beans because the slice only loads MVC-related beans. `@MockitoBean Service service;` uses `REPLACE_OR_CREATE` to register a mock. That is appropriate for web slice goals, **not** proof that production registers a service bean.

In `@SpringBootTest` where the goal is verifying that a production bean exists, use `enforceOverride=true` when replacing a real bean; if missing, the test fails instead of spawning a new mock bean.

### 9.6. Right bean, incompatible field type

If bean `expressGateway` has class/interface type `ShippingGateway` yet the test declares `@MockitoBean(name="expressGateway") WrongInterface mock;`, the type will be incompatible with the expected dependency. Always use a compatible type matching the contract the service receives; naming does not bypass type safety.

### 9.7. `@MockitoSpyBean` cannot find a single target

Unlike `@MockitoBean`, a spy requires exactly one existing bean to wrap. When multiple beans share the type, specify `name` or qualifier. When the target is missing completely, there is no "create new spy" mode akin to `REPLACE_OR_CREATE`; fix the context or use a mock bean if real behavior is unnecessary.

## 10. Advanced cases

### 10.1. Bean overrides for `@Bean` methods

Instead of `@Component("expressGateway")`, real projects might register:

```java
@Configuration(proxyBeanMethods = false)
class ShippingConfiguration {
    @Bean("economyGateway")
    ShippingGateway economyGateway() {
        return new EconomyGateway();
    }

    @Bean("expressGateway")
    ShippingGateway expressGateway() {
        return new ExpressGateway();
    }
}
```

This code **illustrates an alternative registration style for the sample project**—do not add it simultaneously to the sample project or duplicate bean names will occur. `@MockitoBean(name="expressGateway")` still selects the bean by name. Avoid leaving both `@Component` and `@Bean` active for the same instance type and misdiagnosing duplicate/ambiguity errors.

### 10.2. Multiple beans with the same raw generic type

Suppose you have `Store<Customer>` and `Store<Order>`. Generics can act as part of Spring's autowiring qualification, yet test bean overrides must respect the **type/signature** and metadata supported by Spring TestContext. Avoid ambiguous raw `Store` declarations when multiple beans exist or assuming type erasure is harmless. Pick explicit bean names or declare types per API docs, and verify against the test context.

### 10.3. FactoryBean and scopes

Spring Framework bean overrides only support **singleton beans**; overriding non-singletons may fail. If a bean is produced by a `FactoryBean`, `@MockitoBean` replaces the produced bean with a singleton mock, whereas `@MockitoSpyBean` creates a spy of the **object created by the FactoryBean**, not the `FactoryBean` itself. If scoped proxies exist, know which object is injected to avoid verifying the wrong proxy.

### 10.4. Context hierarchy

With `@ContextHierarchy`, a `@MockitoBean` can apply to **every level** by default. To replace a bean only in a child context, set `contextName` matching `@ContextConfiguration(name="...")`:

```java
@MockitoBean(
    name = "expressGateway",
    contextName = "app-config")
ShippingGateway expressGateway;
```

This is a syntax example meaningful only in tests using a real context hierarchy with an `app-config` level. The Maven project in Section 6 uses a single ApplicationContext, so this setting is unnecessary there.

### 10.5. Type-level and repeatable overrides

`@MockitoBean` can be placed on classes, superclasses, interfaces, and as meta-annotations where supported. For example, replacing **two different beans of the same type**:

```java
@SpringBootTest
@MockitoBean(types = ShippingGateway.class, name = "economyGateway")
@MockitoBean(types = ShippingGateway.class, name = "expressGateway")
class BothGatewaysMockedTest {
    // @Autowired @Qualifier("...") ShippingGateway to stub each bean.
}
```

This is **illustrative**, not something to add to the existing tests. Each annotation has its own target name; never write a single annotation `types={ShippingGateway.class,OtherClass.class}, name="expressGateway"` because **when `name` is set, `types` must contain only one type**.

### 10.6. Context caching and multiple mock sets

Spring's context cache considers bean override customizers; if each test class selects different beans or configures different qualifiers/names, Spring may create separate contexts. That is expected because the object graphs genuinely differ. Use plain Java unit tests for pure logic, web slices for HTTP-only checks, and full contexts for wiring. Avoid abusing `@DirtiesContext` or changing fallback field names out of habit, as both slow down the suite.

### 10.7. AOP, transactions, and security

A bean replaced with a Mockito mock via `@MockitoBean` no longer retains the original bean's real logic and proxy/advice behaviors at that point. A `@SpringBootTest` that mocks a `@Transactional` service **does not** prove real service transactions work. Keep the bean whose behavior you want to test real, mock outbound gateways/repositories where test boundaries permit, or run integration tests with real infrastructure.

`@MockitoSpyBean` differs: it wraps an existing bean with a spy, which may require attention to Spring AOP proxies and targets. When spied methods call databases/networks, control side effects; stub with `doReturn(...).when(spy).method()` to avoid calling real code while creating stubs.

### 10.8. @Mock vs. @MockitoBean

Mockito's `@Mock` creates a Java object inside the test; it **does not** register anything in the Spring context. Spring Framework TestContext's `@MockitoBean` tells Spring to replace/register the matching bean. If the test instantiates the SUT with `new`, use `@Mock`/`Mockito.mock`. If Spring `@Autowired` provides the SUT, use bean overrides when adjusting the SUT's collaborators.

Never place both `@InjectMocks` and `@Autowired` on the same SUT thinking Mockito will replace dependencies inside the Spring context; they are two separate management mechanisms.

## 11. Deciding by Spring Boot test type

| Risk to verify | Tool and target | Notes when multiple candidates exist |
| --- | --- | --- |
| Internal logic of `QuoteService` | Unit test; `new QuoteService(mock)` and Mockito `@Mock` | No Spring bean selection needed |
| Real wiring of `QuoteService` to express | `@SpringBootTest`, no mock gateway, assert 130 | `@Qualifier` on constructor guarantees express is chosen |
| Service logic with fake fee | `@SpringBootTest` + `@MockitoBean(name="expressGateway")` | Keep service real; confirm economy is untouched |
| Controller HTTP mapping | `@WebMvcTest` + `@MockitoBean` service collaborator | Slice may omit real service; `REPLACE_OR_CREATE` makes sense |
| Behavior of express adapter itself | Unit/adapter test with real `ExpressGateway` | Do not mock the adapter under test |
| Observing real express method | `@MockitoSpyBean(name="expressGateway")` | Requires unique target bean; watch side effects |
| Beans with `@Transactional`/`@PreAuthorize` | Integration with real service bean | Mock at outbound boundary; do not replace the advised bean itself |
| Persistence repository/queries | `@DataJpaTest` and appropriate database | Do not mock the repository under test |
| Implementations varying by profile | Profile-matched test context + right target name/qualifier | Do not assume every bean exists under all profiles |
| Multiple context levels | `@MockitoBean(contextName="...")` with hierarchies | Match exact context level and canonical name |

If a test is not meant to verify Spring DI, favor fast, clear unit tests. When using a Spring context, target **one specific bean** to replace, then assert results flowing through the real bean that consumes it.

## 12. Debugging by error message

| Symptom | Possible cause | Action |
| --- | --- | --- |
| `No qualifying bean of type ...` | No bean for injection point in current profile/slice | Check scanning, profiles, `@Bean`, or `@MockitoBean` for slice collaborators |
| `NoUniqueBeanDefinitionException` | Multiple candidates of same type; injection/override lacks selector | Add `@Qualifier`, explicit bean name, or design `@Primary` per wiring rules |
| `Failed to load ApplicationContext` with `@MockitoBean ShippingGateway gateway;` | Ambiguous override or missing/enforced target | Read `Caused by` related to bean overrides |
| `when(mock.fee(...))` does not affect total | Mock is not the bean used by SUT | Check constructor qualifiers, target name, and object graph |
| Test passes yet a new mock bean was created | Typo in `name` with `REPLACE_OR_CREATE` | Use `enforceOverride=true` to catch errors |
| Spy fails due to missing bean | `@MockitoSpyBean` requires an existing unique bean | Specify name/qualifier or fix profile |
| `@MockitoBean` picks wrong bean after field rename | Fallback field name changed | Use explicit `name`/`@Qualifier` |
| Bean has `@Primary` but test replaces wrong target | Confused production autowiring with override selection | Check actual bean names/qualifiers used |
| Bean proxy does not match mock reference | AOP/scoped proxy or spy wrapping | Inspect Spring proxy/target and behavior instead of identity alone |
| Context loads repeatedly, slowing tests | Differing overrides, qualifiers, or field names | Standardize naming/config by test boundary |
| Legacy Boot test cannot find `MockitoBean` | Spring Framework lacks 6.2 API | Use version-appropriate API or upgrade Boot/Framework |

### 12.1. Follow the first root cause

`Failed to load ApplicationContext` is usually just a wrapper. Locate the first specific `Caused by`, such as candidate ambiguity, missing bean name, or inability to override a non-singleton. With Spring TestContext's failure threshold (Spring Framework 6.1+), a cache key failing once can cause subsequent attempts to report "skipping repeated attempt"; inspect the **first failure** rather than tweaking the threshold.

### 12.2. Inspecting existing types, names, and qualifiers

In a context test, use `ApplicationContext#getBeansOfType(...)` to inspect the map of bean names → matching instances. When checking a single name, `containsBean("...")` verifies presence. For targeted mocks, `Mockito.mockingDetails(bean).isMock()` and `verify(mock).fee(...)` help verify in simple projects. With proxies or `FactoryBean`s, remember returned objects may be proxies/products; avoid relying solely on object identity.

### 12.3. Do not fix issues by disabling protective boundaries

When a mock fails to take effect, do not:
- Convert every test into a full `@SpringBootTest` mocking every dependency.
- Enable global bean overriding or strip qualifiers from production code.
- Remove `@Primary` or security annotations without knowing which bean the service needs.
- Add `lenient()` when stubs go unused instead of fixing mock placement.
- Assert only against the stub in the test and claim the service uses the mock.

The right fix is selecting the proper bean and testing the **real SUT** via observable behavior.

## 13. Practice questions and suggested answers

1. Two beans `economyGateway` and `expressGateway` share an interface. Is `@MockitoBean ShippingGateway gateway;` enough? **No**; the type is not unique and field name `gateway` cannot select a target. A name or qualifier is needed.
2. If you write `@MockitoBean ShippingGateway expressGateway;`, which mechanism selects the bean? **Field-name fallback** when no `@Qualifier` is present.
3. Declared `@MockitoBean(name="economyGateway")` while `QuoteService` uses express. What fee results after stubbing economy = 55? **30**, because QuoteService still uses the real express bean; total = 130 for subtotal 100.
4. Misspelled `@MockitoBean(name="expresGateway")`. Is the context guaranteed to fail? **No**; default `REPLACE_OR_CREATE` can create a new mock bean. Use `enforceOverride=true` when replacing an existing bean is mandatory.
5. Does `@Qualifier("priority")` on `expressGateway` mean the bean's name is `priority`? **No**. `@Qualifier("priority")` is a filter criterion; `name="priority"` selects by bean name.
6. How does `@MockitoSpyBean(name="expressGateway")` differ from `@MockitoBean(name="expressGateway")`? A spy wraps an existing bean and runs real methods by default; a mock replaces the bean and does not run real implementation by default.
7. Why does `@MockitoBean(name="expressGateway")` in a full-context test prevent testing real `ExpressGateway` code? Because the gateway method is mocked; a separate test keeping `ExpressGateway` real is required.
8. With class-level `@MockitoBean(types={ShippingGateway.class}, name="expressGateway")`, what differs from field-level? You must specify `types`; when `name` is set, the type list must hold only one type.
9. Two test classes replace the same bean using different field-name fallbacks. What is the impact? It can alter the context cache key; use consistent names or explicit bean names.
10. With two beans sharing `@Qualifier("fast")`, is `@MockitoBean @Qualifier("fast")` sufficient? Not necessarily; if multiple candidates still match, you must select a unique bean name/candidate.

## 14. Code review checklist

- [ ] Have I identified the bean type and the list of beans **actually registered** in the test context?
- [ ] Do I know the target bean's name and how it differs from Java field variable names?
- [ ] Are there multiple candidates of the same type? Did I specify `name` or `@Qualifier` explicitly?
- [ ] Is the qualifier value a bean name, alias, or qualifier metadata? Am I confusing them?
- [ ] Which bean does Spring inject into the SUT via constructor, `@Primary`, or qualifier?
- [ ] Is the override target the bean the **real SUT actually calls**?
- [ ] If the bean must exist, did I consider `enforceOverride=true`?
- [ ] Does the test check at least one bean was not mistakenly mocked, or check bean identity where appropriate?
- [ ] If using `@MockitoSpyBean`, does the target exist uniquely as a singleton?
- [ ] If placed on a class, are `types` and `name` valid (`name` paired with one type)?
- [ ] If testing pure logic only, did I consider a plain Mockito unit test with constructor injection?
- [ ] When testing service transactions/security/caching, is the service kept real rather than mocked?
- [ ] When a test fails, did I trace the Spring TestContext root cause instead of patching assertions?
- [ ] When refactoring fallback field names, did I recheck bean targeting and context caching?
- [ ] Did I run tests on the target Spring Boot/Framework version both individually and as a suite?

**Key takeaway:** Select beans by **type** when unique; use an **explicit bean name** or **`@Qualifier`** when multiple candidates exist; treat field names merely as fallbacks; and use `enforceOverride=true` to catch missing beans when replacing an existing bean. Then verify the call path from the **real SUT** to the right mock inside the Spring context, rather than only confirming a standalone stub works.

## 15. Official references

- Spring Framework 6.2 — `@MockitoBean` and `@MockitoSpyBean`, selection by type/name/qualifier: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html
- Spring Framework — Bean Overriding in Tests: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/bean-overriding.html
- Spring Framework — Fine-tuning Autowiring with Qualifiers: https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-qualifiers.html
- Spring Framework — `@Primary` and `@Fallback`: https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-primary.html
- Spring Framework — Context Caching: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5.16 release (version used in examples): https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
- JUnit 5 User Guide: https://docs.junit.org/5.11.4/user-guide/
