# Test Troubleshooting — Multiple Beans of the Same Type, Wrong Qualifiers, or Incorrect Bean Overrides

## 1. Why Do These Errors Only Appear When Running Spring Boot Tests?

A Spring Boot application often registers multiple beans implementing the same interface. That is frequently good design: multiple payment gateways, email senders, tax policies, object mappers, or HTTP clients. Problems arise when Spring needs to inject **a single** bean yet finds multiple candidates, encounters a mismatched qualifier, or a test tries to mock a bean and overrides the **wrong bean** or accidentally creates an extra bean.

Example:

```java
public interface TaxPolicy {
    BigDecimal tax(BigDecimal subtotal);
}

@Component("domesticTaxPolicy")
class DomesticTaxPolicy implements TaxPolicy { /* ... */ }

@Component("exportTaxPolicy")
class ExportTaxPolicy implements TaxPolicy { /* ... */ }
```

Both beans implement `TaxPolicy`. An unqualified injection lacks disambiguation:

```java
@Service
class PricingService {
    PricingService(TaxPolicy policy) {
        // When two candidates exist without further hints,
        // Spring may throw NoUniqueBeanDefinitionException.
    }
}
```

Another scenario: production code injects `@Qualifier("domesticTaxPolicy")` accurately, yet the test declares:

```java
@MockitoBean(name = "domestikTaxPolicy") // Typo.
TaxPolicy taxPolicy;
```

Under `@MockitoBean`'s default strategy **`REPLACE_OR_CREATE`**, a nonexistent bean name quietly creates a brand-new mock bean. The test context **may still start**, while the service keeps using the real `domesticTaxPolicy` bean rather than the mock the test just stubbed. That produces a **false positive or baffling test failure** far trickier than an explicit startup crash.

This lesson centers on three questions:

1. **Which beans are actually registered** as injection candidates?
2. **Which bean did Spring select, and why?** `@Qualifier`, `@Primary`, `@Fallback`, bean name, generics, or profile?
3. **Did the test override the exact bean used by the collaborator?** Or did it merely create an isolated mock that is never invoked?

### After This Lesson You Will Be Able To

- Distinguish `NoUniqueBeanDefinitionException`, `NoSuchBeanDefinitionException`, `BeanDefinitionOverrideException`, and mock tests with zero interactions.
- Analyze by-type, by-qualifier, and by-name injection, including `@Primary` and `@Fallback` precedence.
- Use `@MockitoBean(name=..., enforceOverride=true)` to fail fast when targeting the wrong bean.
- Differentiate `@MockitoBean`, `@MockitoSpyBean`, `@TestBean`, Mockito `@Mock`, and `@TestConfiguration`.
- Write integration tests verifying **bean identity**, type, candidate count, and real service flows.
- Test intentional startup failures safely with `ApplicationContextRunner` without turning the whole suite red.
- Know when `@WebMvcTest` suffices and when `@SpringBootTest` is needed.
- Reduce context cache fragmentation caused by inconsistent field names/qualifiers.
- Diagnose proxy, transaction, conditional bean, and profile issues without enabling global bean overriding.

## 2. Symptom -> Cause -> Evidence Map

| Symptom | Common Cause | Check First |
| --- | --- | --- |
| `NoUniqueBeanDefinitionException`: expected single matching bean, found 2 | Single-bean injection with multiple candidates and no discriminator | List of bean names/types; constructor qualifiers |
| `NoSuchBeanDefinitionException`: no bean named ... | Wrong qualifier/name, unscanned package, bean excluded by profile/condition | Existing bean names; `@Profile`, `@Conditional...` |
| `UnsatisfiedDependencyException` | Bean needs a dependency that could not resolve; usually a wrapper | Inner **root cause**: no unique, no bean, creation failure |
| `BeanDefinitionOverrideException` | Two definitions share the same bean name and Boot forbids overriding | Duplicate `@Bean`/`@Component`, test imports |
| `BeanCreationException` | Bean factory, injection, or config failed; broad wrapper | Deepest `Caused by` and condition report |
| Mockito "Wanted but not invoked" | Stubbed/verified a mock the service is not using | `context.getBean(name)`; collaborator injection identity |
| Stub returns null despite `when(...).thenReturn(...)` | Real bean called, different mock, or mismatched args | Verify mock instance, args, overloaded methods |
| `@MockitoSpyBean` cannot find target | `WRAP` requires an existing bean and a unique candidate | Name/qualifier, bean scope, TestContext config |
| Unit test `@Mock` works, yet `@SpringBootTest` still uses real bean | Mockito `@Mock` does not register a Spring bean | Use `@MockitoBean` when overriding context beans |
| Test passes alone, fails in suite | Context cache/profile/mock reset/shared mutable state | Cache keys, mock fields, parallel tests, data isolation |
| Slice test missing service bean | `@WebMvcTest` loads only the MVC slice | `@MockitoBean` collaborator or narrow `@Import` |
| App bean exists in production, missing in test | Component scan, active profiles, conditional auto-config differ | Effective profiles, test properties, component scan |

**Never fix immediately by setting `spring.main.allow-bean-definition-overriding=true`.** That flag masks duplicate bean names and can make tests run with different behavior from production. First find both definitions and decide whether to **select one bean**, **replace one bean**, or **adjust component scanning**.

## 3. How Does Spring Select a Bean?

### 3.1. Bean Type and Bean Name Are Not Synonymous

Spring registers bean definitions with both a **name** and a **type**. Example:

```java
@Component("domesticTaxPolicy")
public class DomesticTaxPolicy implements TaxPolicy {
    // ...
}
```

The bean name is `domesticTaxPolicy`; its concrete type is `DomesticTaxPolicy`; it is also assignable to `TaxPolicy`. Calling:

```java
context.getBean("domesticTaxPolicy", TaxPolicy.class);
```

looks up by **explicit name** and checks type compatibility. In contrast:

```java
context.getBean(TaxPolicy.class);
```

looks up a single bean by type; if two beans match without a unique winner, it throws `NoUniqueBeanDefinitionException`.

However, **autowiring a field or constructor** carries extra injection-point metadata—qualifiers, primary/fallback flags, parameter names, generics—so it does not always behave identically to `getBean(Type.class)`. Do not assume a service injected the wrong bean simply because `getBean(TaxPolicy.class)` throws ambiguity; inspect the service's injection metadata.

### 3.2. `@Qualifier` to Specify Semantics Explicitly

```java
public PricingService(
        @Qualifier("domesticTaxPolicy") TaxPolicy domestic,
        @Qualifier("exportTaxPolicy") TaxPolicy export) {
    this.domestic = domestic;
    this.export = export;
}
```

Selects a bean by type **narrowed by qualifier**. A bean name also acts as a fallback qualifier value. `@Qualifier` is essentially a **by-type candidate filter**, not purely a bean-ID lookup API like `@Resource(name=...)`.

If a qualifier matches no bean's type/name/qualifier metadata, injection fails. If multiple beans share the **same** qualifier, requesting a single bean remains ambiguous; qualifiers are not guaranteed unique.

### 3.3. `@Primary`: Default Bean When Unqualified

```java
@Component("domesticTaxPolicy")
@Primary
class DomesticTaxPolicy implements TaxPolicy {
    // ...
}
```

When injecting `TaxPolicy` without a qualifier and two beans match, `@Primary` prioritizes domestic. Yet an injection marked `@Qualifier("exportTaxPolicy")` still picks export: **explicit qualifier filtering** is not overridden by an unrelated primary bean.

Do not mark every bean `@Primary`: multiple primary candidates remain ambiguous. Never use `@Primary` to mask a broken qualifier in code that actually needs the **export** policy.

### 3.4. `@Fallback` in Spring Framework 6.2

`@Fallback` marks beans as fallback candidates:

```java
@Component("exportTaxPolicy")
@Fallback
class ExportTaxPolicy implements TaxPolicy {
    // ...
}
```

If exactly one regular (non-fallback) candidate remains, that regular candidate takes priority—a new mechanism in Spring Framework 6.2. **This snippet is not part of the runnable project** because the project keeps both candidates equal to demonstrate ambiguity. Check version-specific docs when using it in Boot 3.5 / Framework 6.2.

### 3.5. Parameter/Field Names Can Also Act as Hints

Without qualifiers, `@Primary`, or `@Fallback`, Spring can match the injection point's name against bean names:

```java
public SomeService(TaxPolicy domesticTaxPolicy) {
    // Can match the bean named domesticTaxPolicy.
}
```

Do not rely blindly on parameter-name luck: Java requires the `-parameters` compiler flag for Spring to read parameter names reliably. Spring 6.2 includes a fast shortcut for name matching when no other precedence rules apply. Renaming a parameter during refactoring can silently alter DI behavior if you rely on implicit name matching.

**Recommendation:** When business logic requires a specific implementation among several, place `@Qualifier` on the constructor parameter. Keep bean names explicit and stable, use `@Primary` only for true defaults, and never depend on accidental variable names.

### 3.6. Injecting All Beans When Multiple Candidates Are Truly Needed

```java
@Autowired
Map<String, TaxPolicy> allPolicies;

@Autowired
List<TaxPolicy> policyList;
```

Spring can inject collections or maps containing all assignable beans of a type, with map keys defaulting to bean names. That requests **multiple beans**, eliminating single-bean ambiguity. You can also use `ObjectProvider<TaxPolicy>` for lazy lookup or streaming, though calling `getObject()` when multiple candidates exist still hits ambiguity—it does not pick the right business bean magically.

### 3.7. Generics and Bean Conditions

Spring treats generic types as a form of qualification in many scenarios: `Repository<Order>` and `Repository<Customer>` stay distinct despite sharing a raw type. Additionally, `@Profile`, `@ConditionalOnProperty`, `@ConditionalOnMissingBean`, and component-scan filters decide **whether a bean gets registered**. Switching profiles can produce an entirely different set of candidates from the same source code.

## 4. Diagnose via `ApplicationContext` Instead of Guessing

If the context **starts**, query metadata directly from the context inside a test:

```java
Map<String, TaxPolicy> candidates =
        context.getBeansOfType(TaxPolicy.class);

assertThat(candidates).containsKeys(
        "domesticTaxPolicy", "exportTaxPolicy");

TaxPolicy actual =
        context.getBean("domesticTaxPolicy", TaxPolicy.class);
```

Use `ApplicationContext.getBeanNamesForType(TaxPolicy.class)` when you only need bean names without instantiating every instance. For lazy/`FactoryBean` beans, query behavior can depend on type prediction and factory initialization; avoid calling these probes casually during production startup.

For beans injected into collaborators, verify:
- **Which constructor** is the injection point, and do parameters carry `@Qualifier`?
- Are there two beans of the same type with only one marked `@Primary`?
- Do bean names match spelling, case, and package scanning?
- Was the bean excluded from the test context by `@Profile`/`@ConditionalOnMissingBean`?
- Is the bean an AOP proxy or a direct object? Check target/proxy when needed.
- Is the test reading from the **same `ApplicationContext`** or a parent/child/isolated runner?
- Which test class or superclass declared the override field? Are meta-annotations involved?

**Never look at `@Autowired SomeType` on a test field and assume the service received that exact same instance.** The test field and the service's constructor parameter may have different qualifiers.

## 5. `@MockitoBean`: Replace, Create, or Replace the Wrong Bean?

Spring Framework 6.2 defines three strategies for bean override infrastructure:

| Strategy | Purpose | When Target Does Not Exist |
| --- | --- | --- |
| `REPLACE_OR_CREATE` | Replace if present; otherwise create new | Creates a new bean |
| `REPLACE` | Replace an existing bean only | Fails |
| `WRAP` | Wrap an existing bean | Fails; requires clear target |

`@MockitoBean` defaults to **`REPLACE_OR_CREATE`**. `@MockitoBean(enforceOverride=true)` enforces **`REPLACE`**. `@MockitoSpyBean` uses **`WRAP`**, requiring an exact existing bean, typically a singleton.

### 5.1. Named Override Failing Fast If Target Is Wrong

```java
@MockitoBean(
    name = "domesticTaxPolicy",
    enforceOverride = true)
TaxPolicy domesticTaxPolicy;
```

This is the safest pattern when multiple beans share a type: it targets the **exact bean name**, and if that bean is renamed or vanishes, test setup fails fast instead of silently creating a ghost mock.

In the sample project, `PricingService` injects the bean named `domesticTaxPolicy`, so stubbing and verifying this field actually exercises the service path.

### 5.2. Fallback Qualifier from Field Name

When multiple candidates exist, `@MockitoBean` on a field infers the target using **field type and qualifier**. Without an explicit `@Qualifier`, the field name serves as a **fallback qualifier**:

```java
@MockitoBean(enforceOverride = true)
TaxPolicy exportTaxPolicy;
```

Field name `exportTaxPolicy` matches the bean name, so the right override is selected. Still, to avoid brittle refactoring when renaming variables in critical tests, declaring `name="exportTaxPolicy"` explicitly is safer.

**Cache implication:** qualifiers and field names also enter the Spring TestContext cache key. Two test classes mocking the same bean with different field names can spin up two separate contexts unnecessarily. Standardize names/qualifiers via shared bases or composed annotations where equivalent.

### 5.3. Wrong Name Creates an Extra Bean Without Touching the Service

```java
@MockitoBean(name = "domestikTaxPolicy")
TaxPolicy typoMock;
```

Because `domestikTaxPolicy` does not exist, the default strategy **creates a new bean**. The context now holds the real domestic, real export, and typo mock beans. The service still injects `@Qualifier("domesticTaxPolicy")`, so stubbing the typo mock **never affects the service**.

A test checking only "context loads" gives a false green; a test verifying real service behavior fails or reports `Wanted but not invoked`. The sample project includes a dedicated JUnit test **proving a ghost mock gets created while the business service never calls it**.

### 5.4. `@MockitoSpyBean` Differs from `@MockitoBean`

```java
@MockitoSpyBean(name = "domesticTaxPolicy")
TaxPolicy domesticTaxPolicy;
```

A spy **retains real behavior** for unstubbed methods. When stubbing a spy, prefer:

```java
doReturn(new BigDecimal("2.00"))
        .when(domesticTaxPolicy)
        .tax(new BigDecimal("100.00"));
```

`when(spy.realMethod()).thenReturn(...)` **invokes the real method during stubbing**, potentially triggering side effects or exceptions. `doReturn(...).when(spy)...` avoids that. When beans carry Spring AOP proxies (`@Transactional`, `@Cacheable`, `@Retryable`), spy/target/proxy semantics get subtler; verification may need to inspect the right layer and account for advisors. The sample **omits AOP** so that complexity does not obscure the primary topic.

### 5.5. Plain Mockito `@Mock` Does Not Override Spring Beans

```java
@Mock
TaxPolicy domesticTaxPolicy;
```

Mockito `@Mock` creates a mock for unit testing; it **does not register the mock in the `ApplicationContext`**. The `PricingService` Spring bean still receives the real `TaxPolicy`. For pure unit tests without a context, use Mockito `@InjectMocks` or pass mocks via constructor. To replace a collaborator **inside a Spring context**, use `@MockitoBean`.

### 5.6. `@TestBean` for Fixed Fakes

Spring TestContext also offers `@TestBean` to replace a bean using an instance returned by a static factory method:

```java
// Standalone snippet, not part of the runnable Maven project.
@TestBean(
    name = "domesticTaxPolicy",
    methodName = "fakeDomestic",
    enforceOverride = true)
TaxPolicy domesticTaxPolicy;

static TaxPolicy fakeDomestic() {
    return subtotal -> new BigDecimal("2.00");
}
```

Use it when you want a deterministic fake **without Mockito stubbing or verification**. It requires a matching static factory signature, TestContext support, and exact bean override targeting—distinct from registering a same-named `@Bean` in `@TestConfiguration` and enabling global overriding.

### 5.7. Scopes and `FactoryBean`

Bean override infrastructure targets singletons primarily; non-singleton/prototype/custom scopes and `FactoryBean`s carry special semantics depending on Spring Framework version and override strategy. Do not assume overriding a `FactoryBean` leaves the original factory intact. For scoped beans, test the appropriate scope and consult version docs rather than turning everything into a singleton just for mocking.

## 6. Distinguishing Injection Ambiguity from Duplicate Bean Definitions

**Multiple beans of the same type**:

```text
NoUniqueBeanDefinitionException:
expected single matching bean but found 2:
domesticTaxPolicy, exportTaxPolicy
```

Cause: two **differently named** beans share a type, and the injection point lacks disambiguation. Fix with a qualifier, meaningful `@Primary`/`@Fallback`, redesigned injection, or collection injection.

**Two definitions sharing the same name**:

```text
BeanDefinitionOverrideException:
Invalid bean definition with name 'domesticTaxPolicy'
```

Cause: two bean definitions **collide on the same name** while Spring Boot disallows overriding by default. Fix by renaming a bean, removing duplicate imports/scans, or using TestContext `@MockitoBean`/`@TestBean` for intentional overrides. Never flip the global overriding flag to hide this.

**Qualifier pointing to a nonexistent bean**:

```text
UnsatisfiedDependencyException
  caused by NoSuchBeanDefinitionException:
  No qualifying bean of type 'TaxPolicy' ...
```

Cause: `@Qualifier("wrongName")`, wrong profile, slice omitting the target bean, or incompatible type. Do not fix with `@Primary`: `@Primary` only chooses among existing candidates.

**These log excerpts are illustrative**, not exact exception messages from the project below; actual logs vary by Spring version, bean names, and exception wrappers.

## 7. `@Primary`, `@Qualifier`, `@Bean` Name: Choosing by Need

| Need | Solution | Notes |
| --- | --- | --- |
| Business code always requires **one** specific implementation | `@Qualifier("domesticTaxPolicy")` on constructor | Explicit semantics, independent of parameter names |
| App has a default implementation for unqualified injections | `@Primary` on the default bean | Do not mark multiple beans primary |
| One implementation is strictly a fallback | `@Fallback` (Spring 6.2+) | Works when one clear regular candidate remains |
| Need all implementations | `List<T>`, `Map<String,T>` | Inject collection instead of single bean |
| Need optional/lazy lookup | `ObjectProvider<T>` | `getObject()` can still hit ambiguity |
| Want bean by exact name | `@Resource(name="...")` or `getBean(name,type)` | Verify type compatibility |
| Test needs to mock a named bean | `@MockitoBean(name=...,enforceOverride=true)` | Prevents silent ghost beans |
| Test needs real behavior with one stubbed method | `@MockitoSpyBean` + `doReturn` | Watch side effects and AOP |
| Test needs a fake from a static factory | `@TestBean` | Fail fast via `enforceOverride` |
| Bean exists only under a profile | Correct `@ActiveProfiles`/test properties | Do not mock a nonexistent bean when fail-fast matters |
| Extra beans created by duplicate scanning | Fix `@ComponentScan`/`@Import` | Never turn on global overriding to mask it |

## 8. Runnable Sample Project — Spring Boot 3.5.0, Java 17

A quoting app with two `TaxPolicy` beans **implementing the same interface under distinct names**. `PricingService` uses explicit constructor qualifiers so the app boots cleanly; `MisconfiguredContextTest` uses `ApplicationContextRunner` to reproduce ambiguity and missing-qualifier errors in **isolated broken contexts** without breaking the rest of the suite.

```text
bean-diagnosis-demo/
├── pom.xml
└── src/
    ├── main/java/example/diagnosis/
    │   ├── BeanDiagnosticsApplication.java
    │   ├── TaxPolicy.java
    │   ├── DomesticTaxPolicy.java
    │   ├── ExportTaxPolicy.java
    │   ├── PriceQuote.java
    │   └── PricingService.java
    └── test/java/example/diagnosis/
        ├── BeanCandidatesTest.java
        ├── DomesticPolicyOverrideTest.java
        ├── ExportPolicyOverrideTest.java
        ├── DomesticPolicySpyTest.java
        ├── PhantomOverrideTest.java
        └── MisconfiguredContextTest.java
```

No HTTP server, database, Docker, or external network is required. `spring-boot-starter` and `spring-boot-starter-test` supply JUnit, Spring TestContext/Mockito, AssertJ, and `ApplicationContextRunner`.

### What Does Each Test Class Verify?

| Class | Type | JUnit Methods | What It Checks |
| --- | --- | ---: | --- |
| `BeanCandidatesTest` | Spring integration | 4 | Two beans of same type, ambiguity, right qualifiers, business behavior |
| `DomesticPolicyOverrideTest` | Spring + named mock | 3 | Mocks only named domestic bean; export remains real |
| `ExportPolicyOverrideTest` | Spring + field fallback | 2 | Field-name fallback picks export; domestic remains real |
| `DomesticPolicySpyTest` | Spring + spy | 2 | Spy runs real/stubbed behavior without calling real method during stub |
| `PhantomOverrideTest` | Spring + accidental bean creation | 1 | Misspelled mock exists yet service never calls it |
| `MisconfiguredContextTest` | Isolated runner | 2 | Unqualified ambiguity and missing-qualifier startup failures |
| **Total** | | **14** | 14 expected JUnit methods |

**Do not put an intentionally failing `@SpringBootTest` into the Maven suite.** If a test boots Spring with a missing bean, assertions never run and Maven merely reports context load failure. `ApplicationContextRunner` is the right tool to assert startup failures as **expected outcomes**.

## 9. `pom.xml`

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>bean-diagnosis-demo</artifactId>
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

The Spring Boot parent/BOM manages aligned versions of Spring Framework (6.2.x in Boot 3.5), JUnit Jupiter, Mockito, and AssertJ. Uses `org.springframework.test.context.bean.override.mockito.MockitoBean` instead of `@MockBean`, which was deprecated in Boot 3.4/3.5.

## 10. Main Class and `TaxPolicy` Interface

`src/main/java/example/diagnosis/BeanDiagnosticsApplication.java`:

```java
package example.diagnosis;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BeanDiagnosticsApplication {
    public static void main(String[] args) {
        SpringApplication.run(BeanDiagnosticsApplication.class, args);
    }
}
```

`src/main/java/example/diagnosis/TaxPolicy.java`:

```java
package example.diagnosis;

import java.math.BigDecimal;

@FunctionalInterface
public interface TaxPolicy {
    BigDecimal tax(BigDecimal subtotal);
}
```

`TaxPolicy` has a single abstract method, allowing lightweight lambdas inside `ApplicationContextRunner` diagnostic configs.

## 11. Two Beans of the Same Type: `DomesticTaxPolicy` and `ExportTaxPolicy`

`src/main/java/example/diagnosis/DomesticTaxPolicy.java`:

```java
package example.diagnosis;

import java.math.BigDecimal;
import java.math.RoundingMode;

import org.springframework.stereotype.Component;

@Component("domesticTaxPolicy")
public class DomesticTaxPolicy implements TaxPolicy {
    @Override
    public BigDecimal tax(BigDecimal subtotal) {
        return subtotal.multiply(new BigDecimal("0.10"))
                .setScale(2, RoundingMode.HALF_UP);
    }
}
```

`src/main/java/example/diagnosis/ExportTaxPolicy.java`:

```java
package example.diagnosis;

import java.math.BigDecimal;
import java.math.RoundingMode;

import org.springframework.stereotype.Component;

@Component("exportTaxPolicy")
public class ExportTaxPolicy implements TaxPolicy {
    @Override
    public BigDecimal tax(BigDecimal subtotal) {
        return subtotal.multiply(BigDecimal.ZERO)
                .setScale(2, RoundingMode.HALF_UP);
    }
}
```

These are **two valid beans** sharing an interface. Neither has `@Primary`, intentionally keeping ambiguity for `getBean(TaxPolicy.class)`. With proper qualifiers on the service, the application starts normally.

- For subtotal `100.00`, domestic tax is `10.00`.
- For subtotal `100.00`, export tax is `0.00`.
- Each policy returns tax scaled to 2 decimal places using `RoundingMode.HALF_UP`.

No external network or environment reads are used, keeping the example deterministic.

## 12. `PriceQuote` and `PricingService`

`src/main/java/example/diagnosis/PriceQuote.java`:

```java
package example.diagnosis;

import java.math.BigDecimal;

public record PriceQuote(
        BigDecimal subtotal,
        BigDecimal tax,
        BigDecimal total,
        String region) {
}
```

`src/main/java/example/diagnosis/PricingService.java`:

```java
package example.diagnosis;

import java.math.BigDecimal;
import java.util.Objects;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class PricingService {
    private final TaxPolicy domesticPolicy;
    private final TaxPolicy exportPolicy;

    public PricingService(
            @Qualifier("domesticTaxPolicy")
            TaxPolicy domesticPolicy,
            @Qualifier("exportTaxPolicy")
            TaxPolicy exportPolicy) {
        this.domesticPolicy = domesticPolicy;
        this.exportPolicy = exportPolicy;
    }

    public PriceQuote quote(
            BigDecimal subtotal,
            boolean exportOrder) {

        if (subtotal == null || subtotal.signum() < 0) {
            throw new IllegalArgumentException(
                    "subtotal must be non-negative");
        }

        TaxPolicy selected =
                exportOrder ? exportPolicy : domesticPolicy;

        BigDecimal tax = Objects.requireNonNull(
                selected.tax(subtotal),
                "tax must not be null");

        return new PriceQuote(
                subtotal,
                tax,
                subtotal.add(tax),
                exportOrder ? "EXPORT" : "DOMESTIC");
    }
}
```

### Why Does Constructor Injection Put `@Qualifier` on **Both** Parameters?

Without both qualifiers, Spring sees two `TaxPolicy` candidates. Parameter names `domesticPolicy`/`exportPolicy` do not match bean names `domesticTaxPolicy`/`exportTaxPolicy`, so fallback name matching cannot save it. Context startup fails with `NoUniqueBeanDefinitionException` when constructing `PricingService`.

Someone might try a quick fix by putting `@Primary` on domestic, yet then an unqualified `export` parameter would silently receive the domestic policy—a **dangerous business bug**. The proper fix is explicitly qualifying both dependencies.

### Business Assertions

- `quote(new BigDecimal("100.00"), false)` -> subtotal `100.00`, tax `10.00`, total `110.00`, region `DOMESTIC`.
- `quote(new BigDecimal("100.00"), true)` -> tax `0.00`, total `100.00`, region `EXPORT`.
- Null or negative input -> `IllegalArgumentException`.
- Mock returning null tax -> `NullPointerException("tax must not be null")` via `Objects.requireNonNull`.

## 13. `BeanCandidatesTest.java` — Verifying Candidates and Resolution

`src/test/java/example/diagnosis/BeanCandidatesTest.java`:

```java
package example.diagnosis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class BeanCandidatesTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    PricingService pricingService;

    @Autowired
    @Qualifier("domesticTaxPolicy")
    TaxPolicy domestic;

    @Autowired
    @Qualifier("exportTaxPolicy")
    TaxPolicy export;

    @Test
    void twoTaxPoliciesExistUnderDistinctNames() {
        Map<String, TaxPolicy> beans =
                context.getBeansOfType(TaxPolicy.class);

        assertThat(beans).containsOnlyKeys(
                "domesticTaxPolicy",
                "exportTaxPolicy");
    }

    @Test
    void unqualifiedTypeLookupIsAmbiguous() {
        assertThrows(NoUniqueBeanDefinitionException.class,
                () -> context.getBean(TaxPolicy.class));
    }

    @Test
    void qualifiersSelectExpectedImplementations() {
        assertThat(domestic)
                .isInstanceOf(DomesticTaxPolicy.class);
        assertThat(export)
                .isInstanceOf(ExportTaxPolicy.class);

        assertThat(context.getBean(
                "domesticTaxPolicy", TaxPolicy.class))
                .isSameAs(domestic);
        assertThat(context.getBean(
                "exportTaxPolicy", TaxPolicy.class))
                .isSameAs(export);
    }

    @Test
    void serviceRoutesToCorrectPolicyByQualifiers() {
        PriceQuote local = pricingService.quote(
                new BigDecimal("100.00"), false);
        PriceQuote overseas = pricingService.quote(
                new BigDecimal("100.00"), true);

        assertThat(local.tax())
                .isEqualByComparingTo("10.00");
        assertThat(local.total())
                .isEqualByComparingTo("110.00");
        assertThat(local.region()).isEqualTo("DOMESTIC");

        assertThat(overseas.tax())
                .isEqualByComparingTo("0.00");
        assertThat(overseas.total())
                .isEqualByComparingTo("100.00");
        assertThat(overseas.region()).isEqualTo("EXPORT");
    }
}
```

**4 JUnit methods.** The second test intentionally triggers an exception via `ApplicationContext.getBean(Type.class)` and **catches it with `assertThrows`**, so the test PASSES when ambiguity behaves properly.

Lesson: having two beans of the same type is valid; failure happens only when an injection point asks for **one** bean without sufficient disambiguation.

## 14. `DomesticPolicyOverrideTest.java` — Targeted Named Override

`src/test/java/example/diagnosis/DomesticPolicyOverrideTest.java`:

```java
package example.diagnosis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class DomesticPolicyOverrideTest {

    @MockitoBean(
        name = "domesticTaxPolicy",
        enforceOverride = true)
    TaxPolicy domesticTaxPolicy;

    @Autowired
    PricingService pricingService;

    @Autowired
    ApplicationContext context;

    @Test
    void namedMockReplacesOnlyDomesticBean() {
        assertThat(context.getBean("domesticTaxPolicy"))
                .isSameAs(domesticTaxPolicy);

        assertThat(Mockito.mockingDetails(
                domesticTaxPolicy).isMock()).isTrue();

        assertThat(context.getBean("exportTaxPolicy"))
                .isInstanceOf(ExportTaxPolicy.class);
    }

    @Test
    void pricingServiceUsesTheNamedMock() {
        BigDecimal subtotal = new BigDecimal("100.00");

        when(domesticTaxPolicy.tax(subtotal))
                .thenReturn(new BigDecimal("7.50"));

        PriceQuote quote = pricingService.quote(
                subtotal, false);

        assertThat(quote.tax())
                .isEqualByComparingTo("7.50");
        assertThat(quote.total())
                .isEqualByComparingTo("107.50");

        verify(domesticTaxPolicy).tax(subtotal);
    }

    @Test
    void exportPolicyRemainsRealAndDoesNotCallMock() {
        PriceQuote quote = pricingService.quote(
                new BigDecimal("100.00"), true);

        assertThat(quote.tax())
                .isEqualByComparingTo("0.00");
        assertThat(quote.region()).isEqualTo("EXPORT");

        verifyNoInteractions(domesticTaxPolicy);
    }
}
```

**3 JUnit methods.** `@MockitoBean` gives this class a distinct context from unmocked tests; the suite does not assume those contexts share one bean graph. Because of `enforceOverride=true`, renaming the production bean `domesticTaxPolicy` without updating the test causes context startup **to fail immediately** instead of spawning a ghost mock.

### Checking Mock Identity Matters More Than Just Checking Stubbing

Calling:

```java
context.getBean("domesticTaxPolicy")
```

must return the exact instance held by the `domesticTaxPolicy` field. The service then invokes that named bean via its constructor qualifier. For AOP-proxied beans, identity is subtler and requires proxy-aware checks; this example uses simple unproxied components.

### Mock Reset

Spring TestContext automatically resets Mockito bean mocks between test methods (default `MockReset.AFTER`). Each test should declare its own stubbing/verification rather than relying on another method's state. If JUnit parallel tests share the same mock context, isolate them because concurrent resets and stubbing can race.

## 15. `ExportPolicyOverrideTest.java` — Field-Name Fallback

`src/test/java/example/diagnosis/ExportPolicyOverrideTest.java`:

```java
package example.diagnosis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ExportPolicyOverrideTest {

    // No explicit name: field name acts as fallback qualifier.
    @MockitoBean(enforceOverride = true)
    TaxPolicy exportTaxPolicy;

    @Autowired
    PricingService pricingService;

    @Autowired
    ApplicationContext context;

    @Test
    void mockFieldNameSelectsExportBean() {
        assertThat(context.getBean("exportTaxPolicy"))
                .isSameAs(exportTaxPolicy);
        assertThat(context.getBean("domesticTaxPolicy"))
                .isInstanceOf(DomesticTaxPolicy.class);
    }

    @Test
    void exportMockDoesNotAffectDomesticCalculations() {
        BigDecimal subtotal = new BigDecimal("100.00");

        when(exportTaxPolicy.tax(subtotal))
                .thenReturn(new BigDecimal("5.00"));

        PriceQuote exportQuote = pricingService.quote(
                subtotal, true);
        PriceQuote domesticQuote = pricingService.quote(
                subtotal, false);

        assertThat(exportQuote.tax())
                .isEqualByComparingTo("5.00");
        assertThat(exportQuote.total())
                .isEqualByComparingTo("105.00");
        assertThat(domesticQuote.tax())
                .isEqualByComparingTo("10.00");
        assertThat(domesticQuote.total())
                .isEqualByComparingTo("110.00");

        verify(exportTaxPolicy).tax(subtotal);
    }
}
```

**2 JUnit methods.** The field name `exportTaxPolicy` matches the bean name. Spring TestContext supports this inference, yet renaming the field to `policy` during refactoring can trigger ambiguity or split cache keys. For critical tests, explicit `@MockitoBean(name=..., enforceOverride=true)` as in section 14 is easier to audit.

## 16. `DomesticPolicySpyTest.java` — `WRAP`, Not `REPLACE`

`src/test/java/example/diagnosis/DomesticPolicySpyTest.java`:

```java
package example.diagnosis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.verify;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class DomesticPolicySpyTest {

    @MockitoSpyBean(name = "domesticTaxPolicy")
    TaxPolicy domesticTaxPolicy;

    @Autowired
    PricingService pricingService;

    @Test
    void unstubbedSpyRunsRealImplementation() {
        BigDecimal subtotal = new BigDecimal("100.00");

        PriceQuote quote = pricingService.quote(
                subtotal, false);

        assertThat(quote.tax())
                .isEqualByComparingTo("10.00");

        verify(domesticTaxPolicy).tax(subtotal);
    }

    @Test
    void doReturnOverridesOnlySelectedSpyMethod() {
        BigDecimal subtotal = new BigDecimal("100.00");

        doReturn(new BigDecimal("2.00"))
                .when(domesticTaxPolicy).tax(subtotal);

        PriceQuote quote = pricingService.quote(
                subtotal, false);

        assertThat(quote.tax())
                .isEqualByComparingTo("2.00");
        assertThat(quote.total())
                .isEqualByComparingTo("102.00");

        verify(domesticTaxPolicy).tax(subtotal);
    }
}
```

**2 JUnit methods.** A spy does not replace the bean completely: real behavior still executes unless stubbed. Use `doReturn` to avoid invoking the real implementation during stub setup. When a production bean has side effects, DB writes, security proxies, or caching, understand proxy/target boundaries; using a mock or testing with the real collaborator and isolated test data may be cleaner.

## 17. `PhantomOverrideTest.java` — Misspelled Mock Yet Context Still Starts

`src/test/java/example/diagnosis/PhantomOverrideTest.java`:

```java
package example.diagnosis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verifyNoInteractions;

import java.math.BigDecimal;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class PhantomOverrideTest {

    // Intentionally misspelled to demonstrate REPLACE_OR_CREATE.
    // Do not copy this pattern into business tests.
    @MockitoBean(name = "typoDomesticTaxPolicy")
    TaxPolicy typoDomesticTaxPolicy;

    @Autowired
    ApplicationContext context;

    @Autowired
    PricingService pricingService;

    @Test
    void wrongNameCreatesUnusedMockInsteadOfOverriding() {
        Map<String, TaxPolicy> beans =
                context.getBeansOfType(TaxPolicy.class);

        assertThat(beans).containsOnlyKeys(
                "domesticTaxPolicy",
                "exportTaxPolicy",
                "typoDomesticTaxPolicy");

        assertThat(context.getBean("typoDomesticTaxPolicy"))
                .isSameAs(typoDomesticTaxPolicy);

        PriceQuote actual = pricingService.quote(
                new BigDecimal("100.00"), false);

        // The service still uses the real domestic implementation.
        assertThat(actual.tax())
                .isEqualByComparingTo("10.00");

        verifyNoInteractions(typoDomesticTaxPolicy);
    }
}
```

**1 JUnit method.** This test **intentionally simulates an anti-pattern while PASSING** to demonstrate the design flaw: the typo mock exists, yet the business flow never touches it. Any test assuming that typo mock replaced the real dependency would fail or assert false expectations.

**Right fix**:

```java
@MockitoBean(
    name = "domesticTaxPolicy",
    enforceOverride = true)
TaxPolicy domesticTaxPolicy;
```

Then assert bean identity and collaborator calls as in `DomesticPolicyOverrideTest`. Never enable the global bean-definition-overriding flag or misuse `@Primary` just to make the test pass.

## 18. `MisconfiguredContextTest.java` — Reproducing Failures Safely

`src/test/java/example/diagnosis/MisconfiguredContextTest.java`:

```java
package example.diagnosis;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.NoSuchBeanDefinitionException;
import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

class MisconfiguredContextTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner();

    record BrokenConsumer(TaxPolicy policy) {
    }

    @Configuration(proxyBeanMethods = false)
    static class AmbiguousConfig {

        @Bean("alphaPolicy")
        TaxPolicy alphaPolicy() {
            return subtotal ->
                    subtotal.multiply(new BigDecimal("0.01"));
        }

        @Bean("betaPolicy")
        TaxPolicy betaPolicy() {
            return subtotal ->
                    subtotal.multiply(new BigDecimal("0.02"));
        }

        @Bean
        BrokenConsumer brokenConsumer(TaxPolicy policy) {
            return new BrokenConsumer(policy);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class WrongQualifierConfig {

        @Bean("alphaPolicy")
        TaxPolicy alphaPolicy() {
            return subtotal ->
                    subtotal.multiply(new BigDecimal("0.01"));
        }

        @Bean
        BrokenConsumer brokenConsumer(
                @Qualifier("missingPolicy") TaxPolicy policy) {
            return new BrokenConsumer(policy);
        }
    }

    @Test
    void unqualifiedInjectionFailsWithTwoCandidates() {
        runner.withUserConfiguration(AmbiguousConfig.class)
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                    .hasRootCauseInstanceOf(
                        NoUniqueBeanDefinitionException.class);
            });
    }

    @Test
    void wrongQualifierFailsWithMissingCandidate() {
        runner.withUserConfiguration(WrongQualifierConfig.class)
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                    .hasRootCauseInstanceOf(
                        NoSuchBeanDefinitionException.class);
            });
    }
}
```

**2 JUnit methods.** `ApplicationContextRunner` builds a **small, isolated context per test run**, allowing the test to verify startup failure as expected behavior. Do not annotate this class with `@SpringBootTest`; its nested configs never enter the production app context.

### Distinguishing the Two Root Causes

- `AmbiguousConfig` defines `alphaPolicy` and `betaPolicy`, while `BrokenConsumer(TaxPolicy policy)` has no qualifier or matching name => multiple candidates => `NoUniqueBeanDefinitionException`.
- `WrongQualifierConfig` defines only `alphaPolicy`, while the method demands `@Qualifier("missingPolicy")` => no matching candidate => `NoSuchBeanDefinitionException`.

Spring normally wraps the root cause inside `BeanCreationException` or `UnsatisfiedDependencyException`; assertions use `hasRootCauseInstanceOf` rather than hardcoding full exception messages.

## 19. Running Maven and Expected Results

Create the files matching the directory tree, use **JDK 17+** and a compatible Maven version, then run:

```bash
mvn test
```

You can also run each class individually:

```bash
mvn test -Dtest=BeanCandidatesTest
mvn test -Dtest=DomesticPolicyOverrideTest
mvn test -Dtest=ExportPolicyOverrideTest
mvn test -Dtest=DomesticPolicySpyTest
mvn test -Dtest=PhantomOverrideTest
mvn test -Dtest=MisconfiguredContextTest
```

| Class | Methods | Expected |
| --- | ---: | --- |
| `BeanCandidatesTest` | 4 | PASS; `assertThrows` ambiguity |
| `DomesticPolicyOverrideTest` | 3 | PASS; domestic mocked, export real |
| `ExportPolicyOverrideTest` | 2 | PASS; export mocked, domestic real |
| `DomesticPolicySpyTest` | 2 | PASS; spy real/stubbed behavior |
| `PhantomOverrideTest` | 1 | PASS; ghost mock deliberately unused |
| `MisconfiguredContextTest` | 2 | PASS; asserted startup root causes |
| **Total** | **14** | **14 expected JUnit methods** |

**These are expected outcomes based on source code, not observed Maven logs.** Inspect `target/surefire-reports/` to confirm test counts, failures, errors, and skips. In particular, the context tests **trigger intentional exceptions handled via assertions**, rather than representing an accidental build failure.

## 20. An 8-Step Diagnostic Workflow

### Step 1 — Read the Root Cause Instead of Stopping at "Failed to load ApplicationContext"

Spring Test may report:

```text
java.lang.IllegalStateException: Failed to load ApplicationContext
  ...
Caused by: UnsatisfiedDependencyException
  ...
Caused by: NoUniqueBeanDefinitionException
  ...
```

Follow `Caused by` down to the details naming the type, candidate beans, and injection point. Subsequent tests may report only context failure threshold exceeded because the Spring Test cache recorded the earlier failure for that config; inspect the **first** failure log for that cache key rather than patching the threshold symptom.

### Step 2 — List Candidates in the Right Context

Use `getBeanNamesForType(Type.class)`/`getBeansOfType(...)`, or inspect Boot's debug condition evaluation report when the context cannot start. `@SpringBootTest(properties = "debug=true")` prints detailed auto-configuration diagnostics, though never dump secrets or raw environments into CI logs.

If the full app context fails to start, `ApplicationContextRunner` with minimal configs can reproduce the ambiguity in a narrow scope.

### Step 3 — Check Names, Types, and Qualifiers

- Does `@Component("...")` match `@Qualifier`?
- Is the bean name the `@Bean` method name or an explicit `@Bean(name=...)`?
- Does the injection point parameter carry `@Qualifier`, or does it rely solely on the variable name?
- Is the bean assignable to the exact interface type and generic arguments?
- Do multiple `@Primary` beans or a `@Fallback` alter resolution?

### Step 4 — Check Scope and Registration

- Does the test profile differ from production?
- Are `@Profile`/`@ConditionalOnProperty` active as expected?
- Did `@WebMvcTest` omit a collaborator or did `@SpringBootTest` load the full graph?
- Did `@TestConfiguration` accidentally create a colliding bean name?
- Did `@ComponentScan` sweep in unintended test or legacy packages?
- Did auto-configuration back off due to `@ConditionalOnMissingBean`?

### Step 5 — Check Mock Override Metadata

- Does `@MockitoBean` target the right interface/type?
- Are there multiple beans of the same type? If so, specify `name=...` or a qualifier.
- Is `enforceOverride=true` set so ghost beans cannot spawn silently?
- Does the field name match the intended bean name when relying on fallback qualification?
- Do multiple test classes override the same target with different field names, splitting the context cache?
- Did someone use plain Mockito `@Mock` instead of Spring TestContext bean override?

### Step 6 — Verify the Collaborator Actually Invokes the Mock

Do not assert only that the mock field was injected. Verify:

```java
assertThat(context.getBean("domesticTaxPolicy"))
        .isSameAs(domesticTaxPolicy);

when(domesticTaxPolicy.tax(subtotal))
        .thenReturn(new BigDecimal("7.50"));

PriceQuote result =
        pricingService.quote(subtotal, false);

verify(domesticTaxPolicy).tax(subtotal);
```

If verification reports zero interactions, check whether the service took another branch, inspect the constructor's qualifier, verify which bean instance is being checked, or look for `equals` mismatches on arguments. With AOP proxies, account for Mockito wrapper/target semantics before asserting object identity.

### Step 7 — Check Test Boundaries and Caching

`@WebMvcTest` scans only the MVC slice, whereas `@SpringBootTest` loads the full context; differing mock configurations produce distinct cache keys. `@MockitoBean` qualifiers and field names participate in the cache key. Under parallel execution, shared singleton mocks can suffer reset/stub races. Maintain test isolation and consistent names; do not sprinkle `@DirtiesContext` everywhere just to reset Mockito.

### Step 8 — Apply Minimal Fixes and Lock Them In with Negative Tests

- Multiple beans: add explicit qualifiers at the **exact injection point**.
- Wrong qualifier: fix the name or registration condition instead of adding a misleading `@Primary`.
- Wrong override: use named `@MockitoBean(enforceOverride=true)` and verify real collaborator interactions.
- Duplicate name: remove duplicate definitions/imports; never enable global overriding.
- Slice missing bean: `@MockitoBean` the collaborator in the slice or `@Import` only required configs.
- Add a regression test for the **failure class encountered** before merging.

## 21. `@WebMvcTest` vs `@SpringBootTest`: When Is a Missing Bean Expected?

`@WebMvcTest(MyController.class)` builds only the MVC slice and skips scanning `@Service`/`@Repository` collaborators by default. If the controller depends on `PricingService`, the slice test fails startup with `NoSuchBeanDefinitionException` even though production `@SpringBootTest` finds the bean.

Illustrative snippet:

```java
@WebMvcTest(PricingController.class)
class PricingControllerTest {

    @MockitoBean
    PricingService pricingService;

    // @Autowired MockMvc mvc; tests...
}
```

`PricingController` is outside the core sample, so this is an **architectural snippet**, not a standalone runnable file. In MVC tests, mock the service when checking HTTP mappings, serialization, and controller validation; switch to `@SpringBootTest`/`@AutoConfigureMockMvc` when testing real service/repository collaboration.

**Do not fix slice failures by importing the entire application needlessly**, as that forfeits slice speed and isolation. Import only minimal security/configurations or mock the right collaborator.

## 22. `@TestConfiguration` Does Not Automatically Replace Existing Beans

Suppose a test declares:

```java
@TestConfiguration
class FakeConfig {
    @Bean("domesticTaxPolicy")
    TaxPolicy domesticTaxPolicy() {
        return value -> new BigDecimal("0.00");
    }
}
```

If the context already registers a bean named `domesticTaxPolicy`, adding a duplicate definition with the same name triggers `BeanDefinitionOverrideException` under Boot defaults. `@TestConfiguration` is not an **automatic safe override mechanism for every case**.

Solutions:

1. `@MockitoBean(name="domesticTaxPolicy", enforceOverride=true)` when a Mockito mock is wanted.
2. `@TestBean(name="domesticTaxPolicy", enforceOverride=true)` when a static-factory fake is wanted.
3. Profile or conditional bean configurations selecting test adapters cleanly with verified semantics.
4. `@Primary` on a **differently named** test fake when changing unqualified default injection without replacing definitions, remembering that explicit `@Qualifier` parameters still bind to their named beans rather than `@Primary`.
5. For unit-testing `PricingService` alone, instantiate it directly with mock dependencies without a Spring context.

**Enabling `spring.main.allow-bean-definition-overriding=true` as a general fix is discouraged**; it hides duplicate components and creates order-dependent behavior.

## 23. `@Primary` and `@Qualifier`: No Context Error Yet Wrong Business Result

A subtle trap occurs when an app has two policies and domestic is marked `@Primary`. An export service accidentally omits the qualifier on its constructor:

```java
public ExportService(TaxPolicy policy) {
    this.policy = policy; // May receive domestic @Primary.
}
```

The context boots cleanly and unit tests mocking the raw type pass, yet production behavior is wrong (exports get taxed at domestic rates). Fix with explicit `@Qualifier("exportTaxPolicy")`, write an integration test for export input, and assert `tax=0.00`.

Therefore, **no `NoUniqueBeanDefinitionException` does not guarantee the right bean was injected**. Spring may validly pick a default candidate per annotations that violates business intent. Tests must assert real behavior, not merely `contextLoads()`.

## 24. Bean Overrides and AOP Proxies: Right Name Can Still Miss Scope

`@MockitoBean` uses replacement strategies, so a mock bean may **lose AOP advice** originally attached to the target—such as `@Transactional`, `@Cacheable`, `@Retryable`, or method security. A controller test mocking the service does not verify production transaction or retry behavior.

`@MockitoSpyBean` uses `WRAP`, which can preserve an AOP proxy around the spy per Spring Framework behavior. Consequently:

- To test retry/transaction semantics, keep the real bean and mock **downstream** dependencies rather than replacing the advised service itself.
- When spying a proxied bean, check `@MockitoSpyBean`/AOP docs; `AopTestUtils.getUltimateTargetObject(...)` and proxy-aware verification may be needed when advisors are active.
- Prefer `doReturn`/`doThrow` over `when(spy.method())` to avoid side effects during stubbing.
- Never conclude a bean "was never called" if you are verifying the wrong proxy layer or a call hit a cache.
- `@ContextHierarchy` can apply overrides across **multiple levels**; set `contextName` to target the exact context level.

These subtleties explain why **named override + expected behavior + actual interaction** beats checking `Mockito.mockingDetails(mock).isMock()` alone.

## 25. Profiles, `@ConditionalOnMissingBean`, and Component Scanning

A missing-bean error does not automatically mean a typo in `@Qualifier`. Common alternatives:

**Different profile**:

```java
@Profile("live")
@Component("externalTaxPolicy")
class ExternalTaxPolicy implements TaxPolicy {
    // ...
}
```

When tests run with `@ActiveProfiles("test")`, `externalTaxPolicy` is never created. Any code still requiring `@Qualifier("externalTaxPolicy")` fails with a missing dependency. Fix the profile design or provide a test adapter instead of creating an unconditional ghost mock.

**Auto-configuration backs off**: `@ConditionalOnMissingBean` skips registering a default bean when the test already supplies a bean of that type. Adding a mock/fake alters condition evaluation and changes the bean graph; inspect the Spring Boot condition evaluation report.

**Accidental component scanning**: Importing test configs, scanning overly broad packages, or misplacing top-level test configurations can create extra beans. Top-level `@TestConfiguration` classes are excluded from normal component scanning, so import them explicitly only where needed.

**`@Bean` methods and names**: `@Bean` defaults to the method name, yet `@Bean(name="...")` or aliases change it. Check real bean names in context metadata instead of guessing from class names.

## 26. Context Caching: Mock Field Names Affect Test Performance

Spring TestContext keys its cache by `MergedContextConfiguration`, where bean-override customizers capture mock definitions. Two tests:

```java
@MockitoBean
TaxPolicy exportTaxPolicy;
```

and:

```java
@MockitoBean
TaxPolicy policy;
```

do not necessarily share a cache key even if the developer considers them the same type. Field names act as fallback qualifiers and can cause **both ambiguity and context fragmentation**.

Better practices:
- Share a base annotation or base test class for tests needing identical overrides.
- Use consistent explicit bean names.
- Keep `@ActiveProfiles` and `@SpringBootTest(properties=...)` aligned where shared contexts make sense.
- Do not add `@DirtiesContext` needlessly to "refresh mocks"; Spring provides reset modes.
- Never force-merge contexts whose bean graphs or profiles legitimately differ.

The default JVM context cache holds 32 entries (LRU) in Spring TestContext. Unnecessary keys slow startup, though **correct bean wiring always takes priority over cache hit rates**.

## 27. Diagnosing with Negative Tests Before Changing Production

A safe workflow when ambiguity hits:

1. Write a tiny `ApplicationContextRunner` configuration reproducing **two candidates + one unqualified consumer**.
2. Assert root cause `NoUniqueBeanDefinitionException`.
3. Add explicit `@Qualifier("alphaPolicy")` to the consumer in the test config and confirm startup succeeds.
4. Write a Spring Boot integration test against the real application configuration with proper qualifiers.
5. Write a test overriding a named target with `enforceOverride=true`.
6. Try a wrong bean name in an **isolated experiment** to verify fail-fast rather than a ghost mock.
7. Keep regression tests covering business behavior for each implementation.
8. Run the full suite to ensure test mocks did not shadow a bean under another profile.

**Never leave intentionally broken configs inside production component scans.** Use an isolated runner or dedicated negative harness for failure testing rather than breaking the production app just to inspect a stack trace.

## 28. Common Rash "Fixes" to Avoid

| Rash "Fix" | Why It Is Wrong | Alternative |
| --- | --- | --- |
| Adding `@Primary` to an arbitrary bean | Can route business logic to wrong implementation | Explicit `@Qualifier` at injection point |
| Enabling global bean overriding | Masks duplicate bean definitions | Remove duplicate/import or use TestContext override |
| Mocking interface by type when multiple beans exist | Ambiguous or overrides wrong target | Named `@MockitoBean(..., enforceOverride=true)` |
| Putting `@Mock` in `@SpringBootTest` expecting override | Mock stays only on test instance | `@MockitoBean` or constructor-injected unit test |
| Using default `@MockitoBean` for a required bean | Typo spawns ghost bean | `enforceOverride=true` |
| Renaming mock fields inconsistently | Changes fallback qualifier and cache key | Standardize field name or explicit name |
| Checking `contextLoads()` only | Context may wire the wrong implementation | Assert bean identities and business outcomes |
| Stubbing a spy via `when(spy.call())` | Invokes real method during stub setup | `doReturn(...).when(spy)...` |
| Removing `@Qualifier` "to reduce annotations" | Spring may bind wrong `@Primary` bean | Document and keep injection contract |
| Switching every `@WebMvcTest` to `@SpringBootTest` | Loses slice isolation and speed | Mock or import exact slice collaborator |
| Deleting tests hitting `NoUnique` | Loses bug coverage | Negative runner test expecting the failure |
| Asserting exact full error messages | Fragile across framework upgrades | Assert exception/root cause class |
| `@DirtiesContext` after every method | Wastes context cache | Scope mock/data resets properly |
| Letting Spring Boot scan entire test config package | Causes duplicate beans | Import test configs explicitly |

## 29. Pre-QA Sign-Off Checklist

- [ ] Followed `Failed to load ApplicationContext` down to the root cause?
- [ ] Listed exact names, types, and count of candidate beans?
- [ ] Confirmed whether injection expects a single bean or a collection?
- [ ] Checked `@Primary`, `@Fallback`, and `@Qualifier` at the injection point?
- [ ] Avoided relying on parameter names when business rules require explicit selection?
- [ ] Checked test profiles, conditional registration, and component scans?
- [ ] Distinguished `NoUniqueBeanDefinitionException` from duplicate bean names?
- [ ] Specified explicit `@MockitoBean` targets when multiple beans share a type?
- [ ] Set `enforceOverride=true` whenever the target **must** already exist?
- [ ] Verified the named bean inside the context is the exact mock/spy instance?
- [ ] Verified the real collaborator invokes the expected mock and ignores wrong mocks?
- [ ] Avoided using plain Mockito `@Mock` expecting Spring bean replacement?
- [ ] Understood `@MockitoSpyBean` `WRAP` and real-method side effects?
- [ ] Used `@TestBean`/`@TestConfiguration` appropriately?
- [ ] Kept `allow-bean-definition-overriding=true` off instead of hiding broken setups?
- [ ] Preserved clear boundaries between unit, slice, and integration tests?
- [ ] Added negative `ApplicationContextRunner` tests for missing/ambiguous candidates?
- [ ] Asserted root-cause classes rather than fragile exact full messages?
- [ ] Confirmed no ghost mocks or accidental profile shifts remain in release tests?
- [ ] Verified mocks reset cleanly so tests are independent of method order?
- [ ] Standardized context cache field qualifiers where classes share overrides?
- [ ] Verified actual Maven test reports before declaring tests passing?

## 30. Exercises

1. Remove `@Qualifier` from both constructor parameters of `PricingService`, observe the root cause, and restore them. Never leave the broken version in main source.
2. Remove only the export qualifier and put `@Primary` on domestic; analyze why the context boots yet export quotes calculate wrong tax.
3. Rename `@Component("domesticTaxPolicy")` to `"domesticTaxRules"`; verify `enforceOverride=true` tests fail immediately on context load.
4. Remove `enforceOverride=true` and pass a misspelled `@MockitoBean(name="typo...")`; reproduce the phantom bean.
5. Take `@MockitoBean(enforceOverride=true) TaxPolicy exportTaxPolicy`, rename the field to `policy`, and observe fallback qualifier and context behavior.
6. Add `@Primary` to one policy inside an isolated runner and verify ambiguity resolves when semantically valid.
7. Place `@Fallback` on one policy (Framework 6.2+) and verify the remaining regular candidate wins.
8. Switch `@MockitoSpyBean` stubbing from `doReturn` to `when` in an isolated experiment to observe whether the real method runs at stubbing time.
9. Create a `@TestBean` for domestic using a static factory; verify name selection and `enforceOverride`.
10. Add a `@WebMvcTest` controller test missing its service and fix it with `@MockitoBean` without importing the whole app.
11. Create a profile-specific implementation and verify how `@ActiveProfiles` alters the candidate set.
12. Add `@ConditionalOnMissingBean` to an optional adapter and observe how the context changes when a test registers a mock.
13. Create duplicate bean definitions sharing a name in an isolated runner and assert startup failure instead of enabling global overrides.
14. Change a bean to a non-singleton scope and inspect override constraints in your Spring version.
15. Measure cached context counts before and after standardizing mock field names across tests.

## 31. Official References

1. [Spring Framework 6.2 — @MockitoBean and @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html): field-name fallback qualifiers, explicit names, `enforceOverride`, `WRAP`, and context caching.
2. [Spring Framework 6.2 — Bean Overriding in Tests](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/bean-overriding.html): `REPLACE`, `REPLACE_OR_CREATE`, `WRAP`, singleton/proxy semantics.
3. [Spring Framework — Autowired Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html): type matching, qualifier narrowing, and bean/parameter name matching.
4. [Spring Framework — @Primary and @Fallback](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html): prioritizing implementations.
5. [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@WebMvcTest`, `@TestConfiguration`, and `@MockitoBean`.
6. [Spring Framework 6.2 — @TestBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-testbean.html): static factory-based test overrides.
7. [Spring Framework 6.2 — Context Caching](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html): context customizers, qualifiers, and cache reuse.
8. [Spring Boot — Creating Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): `@ConditionalOnMissingBean` and `ApplicationContextRunner`.
9. [Spring Framework 6.2 — TestContext Framework](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework.html): lifecycle and bean override support.

### Conclusion

**Multiple beans of the same type are not a bug by themselves.** The problem lies in **missing selection hints**, **wrong qualifiers/names**, or **test mocks overriding the wrong target**. Inspect the root cause, enumerate candidates, differentiate `@Primary`/`@Fallback`/`@Qualifier`, use `@MockitoBean(name=..., enforceOverride=true)` to replace the right bean, verify **bean identity + business outcome + Mockito interactions**, and use `ApplicationContextRunner` to test intentional startup failures while keeping the suite green.
