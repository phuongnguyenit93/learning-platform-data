# JUnit Jupiter `@Nested` for Grouping Related Test Scenarios

When a behavior has multiple contexts, a flat list of `@Test` methods with names like `testCase1`, `testCase2` makes it hard to tell which states the system has been tested in. JUnit Jupiter provides the **`@Nested`** annotation to place tests sharing the same context inside a subclass, creating a meaningful tree: "Active account" → "BASIC plan" → "Cannot open paid documents".

This lesson explains how to organize tests with `@Nested`, the setup/teardown lifecycle at each level, state scoping, and how to combine it with Spring Boot. The main example is **runnable Java 17+ and JUnit Jupiter**, with real assertions. `@Nested` is a JUnit Jupiter feature, not a Spring Boot-specific annotation.

## 1. Concept and foundational syntax

`@Nested` (import `org.junit.jupiter.api.Nested`) marks a **non-`static` inner class** inside a test class. JUnit Jupiter discovers the tests inside it, creates a hierarchical structure, and applies lifecycle callbacks from enclosing classes. A nested class can in turn contain other nested classes.

```java
class LoginPolicyTest {
    @Nested
    class WhenUserIsActive {
        @Test
        void allowsLoginWithValidCredentials() {
            // Example showing where assertions for this context belong.
        }
    }

    @Nested
    class WhenUserIsLocked {
        @Test
        void rejectsLogin() {
            // Structural example, without assertions or standalone execution yet.
        }
    }
}
```

This snippet illustrates **structure**, not a complete test. Using `@Nested` alone does not make a test more useful; you need input data, actions, and assertions proving the right behavior.

| Annotation | Meaning |
|---|---|
| `@Test` | Marks a test method |
| `@Nested` | Represents a context group at the inner-class level |
| `@DisplayName` | Gives clear group/test names in the IDE and reports |
| `@BeforeEach` | Setup before each test method at that level or child levels |
| `@AfterEach` | Cleanup after each test method, from inner level to outer level |
| `@BeforeAll` / `@AfterAll` | One-time setup/cleanup according to the lifecycle of the corresponding test level |
| `@TestInstance` | Specifies test instance creation as `PER_METHOD` or `PER_CLASS` |
| `@ParameterizedTest` | Runs the same test logic with multiple datasets; can live inside `@Nested` |

When to use `@Nested`: a rule needs verification in "before/after" states, across "guest/user/admin" roles, or in "valid requests/invalid requests" groups. When there are only 2–3 simple tests with no shared setup or context, keeping tests flat is usually clearer. **Group by conditions that affect the outcome**, and avoid grouping under generic labels like "PositiveTests" if it does not explain the condition.

## 2. Complete example: document access policy

Suppose a document management system has the following rules:

1. If the account is **inactive**, no documents may be opened.
2. If the account is **active**, the `BASIC` plan can read free documents but cannot open premium documents.
3. If the account is **active**, the `PREMIUM` plan can read both types of documents.
4. If `Plan` is `null`, explicitly reject with an exception.

These rules form two context levels: **account status** and **plan type**. Within each context, tests verify access rights to each type of document.

### 2.1. Production class

File **`src/main/java/com/example/library/DocumentAccessPolicy.java`**:

```java
package com.example.library;

import java.util.Objects;

public final class DocumentAccessPolicy {
    public enum Plan {
        BASIC, PREMIUM
    }

    public boolean canAccess(Plan plan, boolean accountActive,
                             boolean premiumDocument) {
        Objects.requireNonNull(plan, "plan");
        return accountActive && (!premiumDocument || plan == Plan.PREMIUM);
    }
}
```

`Objects.requireNonNull` rejects `null` with `NullPointerException`; for an inactive account, the result is `false`; for an active account, non-premium documents are allowed, while premium documents require `Plan.PREMIUM`.

### 2.2. Test class using two levels of `@Nested`

File **`src/test/java/com/example/library/DocumentAccessPolicyTest.java`**:

```java
package com.example.library;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DocumentAccessPolicyTest {
    private DocumentAccessPolicy policy;
    private boolean active;
    private DocumentAccessPolicy.Plan plan;

    @BeforeEach
    void createNewPolicy() {
        policy = new DocumentAccessPolicy();
    }

    @Nested
    @DisplayName("When the account is active")
    class ActiveAccount {
        @BeforeEach
        void enableAccount() {
            active = true;
        }

        @Nested
        @DisplayName("And the plan is BASIC")
        class BasicPlan {
            @BeforeEach
            void selectPlan() {
                plan = DocumentAccessPolicy.Plan.BASIC;
            }

            @Test
            @DisplayName("Can read free documents")
            void allowsFreeDocument() {
                assertTrue(policy.canAccess(plan, active, false));
            }

            @Test
            @DisplayName("Is denied premium documents")
            void deniesPremiumDocument() {
                assertFalse(policy.canAccess(plan, active, true));
            }
        }

        @Nested
        @DisplayName("And the plan is PREMIUM")
        class PremiumPlan {
            @BeforeEach
            void selectPlan() {
                plan = DocumentAccessPolicy.Plan.PREMIUM;
            }

            @Test
            @DisplayName("Can read free documents")
            void allowsFreeDocument() {
                assertTrue(policy.canAccess(plan, active, false));
            }

            @Test
            @DisplayName("Can read premium documents")
            void allowsPremiumDocument() {
                assertTrue(policy.canAccess(plan, active, true));
            }
        }
    }

    @Nested
    @DisplayName("When the account is inactive")
    class InactiveAccount {
        @BeforeEach
        void disableAccount() {
            active = false;
        }

        @Test
        @DisplayName("Cannot read free documents")
        void deniesFreeDocument() {
            assertFalse(policy.canAccess(
                    DocumentAccessPolicy.Plan.BASIC, active, false));
        }

        @Test
        @DisplayName("Cannot read premium documents")
        void deniesPremiumDocument() {
            assertFalse(policy.canAccess(
                    DocumentAccessPolicy.Plan.PREMIUM, active, true));
        }
    }

    @Test
    @DisplayName("Rejects null plan")
    void rejectsNullPlan() {
        assertThrows(NullPointerException.class,
                () -> policy.canAccess(null, true, false));
    }
}
```

These are **two complete Java files**, with proper package, class, and imports to compile in a project that has the JUnit Jupiter API/engine. `@SpringBootTest` is not needed: this logic is plain Java, with no beans or I/O.

The expected outcome is **7 `@Test` methods**, all passing. Because each group is in a different inner class, having two groups both define `allowsFreeDocument()` is valid; they are two methods on two distinct Java classes.

In an IDE, readers typically see a tree similar to the following (display format depends on the runner):

```text
DocumentAccessPolicyTest
├── When the account is active
│   ├── And the plan is BASIC
│   │   ├── Can read free documents                 PASS
│   │   └── Is denied premium documents             PASS
│   └── And the plan is PREMIUM
│       ├── Can read free documents                 PASS
│       └── Can read premium documents              PASS
├── When the account is inactive
│   ├── Cannot read free documents                  PASS
│   └── Cannot read premium documents               PASS
└── Rejects null plan                               PASS
```

When using Maven Wrapper in a module configured for JUnit 5/Jupiter:

```bash
./mvnw -Dtest=DocumentAccessPolicyTest test
```

Or Gradle Wrapper with JUnit Platform enabled for the test task:

```bash
./gradlew test --tests "com.example.library.DocumentAccessPolicyTest"
```

On Windows, use `mvnw.cmd` or `gradlew.bat`; run from the correct module directory. With Spring Boot, the `spring-boot-starter-test` dependency usually provides the required JUnit Jupiter artifacts. If it is a manually configured Gradle Java project, ensure the engine and `useJUnitPlatform()` are present. The suite is expected to have **7 tests passed, 0 failed**; no business stdout is defined. Names/report trees differ across IntelliJ, Eclipse, Surefire, and Gradle, but the assertions must be the same.

## 3. Lifecycle: outer-level setup runs before inner-level setup

A more important feature than grouping names is **inheriting lifecycle callbacks along the chain of enclosing inner classes**. When running `ActiveAccount.BasicPlan.allowsFreeDocument()`, the order is:

```text
Create test instance (default lifecycle)
  → @BeforeEach of DocumentAccessPolicyTest: createNewPolicy()
  → @BeforeEach of ActiveAccount: enableAccount()
  → @BeforeEach of BasicPlan: selectPlan()
  → @Test: allowsFreeDocument()
  → @AfterEach of BasicPlan (if present)
  → @AfterEach of ActiveAccount (if present)
  → @AfterEach of DocumentAccessPolicyTest (if present)
```

Thus `policy` is created before `ActiveAccount` and `BasicPlan` access it, and then `active` and `plan` are assigned to match the context. When running tests in `PremiumPlan`, JUnit does not run `BasicPlan`'s setup. When running `rejectsNullPlan()` on the outer class, none of the nested classes' setups are invoked.

`@BeforeEach` on outer and inner classes runs **for every invocation within the child group**, not once when the group starts. `@AfterEach` runs in reverse: inner level first, outer level last. If one level has multiple `@BeforeEach` methods, do not assume JUnit executes them in source-line order; combine order-dependent steps into one explicit method.

### Is each test truly independent?

With the default **`TestInstance.Lifecycle.PER_METHOD`** lifecycle, JUnit creates a fresh corresponding test object for each test method, including objects along the nested chain. Therefore, regular fields of the test class do not retain values across different test executions. However, **static variables, singleton beans, databases, files, and out-of-JVM caches** can still be shared. `@Nested` does not automatically clean up those resources.

Do not let a "read premium document" test depend on a "subscribe to premium plan" test having run beforehand. Each test must set up its own scenario and assert its own outcome.

## 4. `@BeforeAll`, `@AfterAll`, and the `PER_CLASS` lifecycle

`@BeforeAll`/`@AfterAll` handle one-time operations for a test group, such as preparing an immutable shared fixture. Under `PER_METHOD`, these callbacks must normally be `static`; since Java 16, Java allows declaring static members inside inner classes. When you want to use **non-static** callbacks at a nested level, apply `@TestInstance(TestInstance.Lifecycle.PER_CLASS)` to the group:

```java
@Nested
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class WithSharedFixture {
    @BeforeAll
    void prepareOnce() {
        // Executed only once for this group.
    }

    @Test
    void checksBehavior() {
        // Add real assertions when integrating into a project.
    }
}
```

The snippet above **only illustrates the lifecycle mechanism** inside a test class that already has JUnit configured and proper imports; it is not a standalone program. In real usage, import `org.junit.jupiter.api.TestInstance`, `BeforeAll`, `Nested`, `Test`, and write assertions. Switching to `PER_CLASS` means tests in the group can share an instance, making state leakage easier. For most unit tests, keeping `PER_METHOD` and `@BeforeEach` avoids hidden dependencies.

Even when shared initialization is needed, distinguish **immutable shareable data** from **mutable state that must be refreshed**. Parallel execution makes race conditions and nondeterminism even more apparent.

## 5. Combining `@Nested` with `@ParameterizedTest`

`@Nested` groups **contexts**; `@ParameterizedTest` repeats **the same rule with different datasets**. For example, every plan type must be rejected when the account is inactive:

```java
@Nested
class InactiveAccount {
    @ParameterizedTest
    @EnumSource(DocumentAccessPolicy.Plan.class)
    void deniesPremiumDocumentsForAllPlans(
            DocumentAccessPolicy.Plan plan) {
        assertFalse(policy.canAccess(plan, false, true));
    }
}
```

This is a snippet **added to an outer test class that has the `policy` field**, not a standalone file. It requires importing `org.junit.jupiter.params.ParameterizedTest`, `org.junit.jupiter.params.provider.EnumSource`, `org.junit.jupiter.api.Nested`, and static importing `assertFalse`; the project must have the appropriate `junit-jupiter-params` dependency. Because `Plan` has two values, this snippet creates **2 executions**.

If values only differ in input while sharing the same expected behavior, using a parameterized test is usually cleaner than creating many `@Nested` classes. If each group has different setup and expected behavior, `@Nested` expresses scope better. Both can be used together.

## 6. Applying with Spring Boot TestContext

In Spring Boot, `@Nested` is useful for grouping scenarios in `@WebMvcTest`, `@DataJpaTest`, or `@SpringBootTest`, but **a nested structure does not create an ApplicationContext on its own**.

### Inheriting configuration from the outer class

Spring TestContext Framework defaults to **`INHERIT`** mode when processing many test configuration annotations for nested classes. For example, an outer class declaring `@SpringBootTest` and `@ActiveProfiles("test")` lets child groups inherit this configuration:

```java
@SpringBootTest
@ActiveProfiles("test")
class OrderServiceIntegrationTest {
    @Autowired
    OrderService service;

    @Nested
    class WhenOrderIsPending {
        @Test
        void canCancel() {
            // Arrange order, call service, assert result.
        }
    }

    @Nested
    class WhenOrderIsShipped {
        @Test
        void cannotCancel() {
            // Arrange shipped order, assert cancellation is rejected.
        }
    }
}
```

This is **code illustrating how to organize Spring tests**; it does not compile standalone because `OrderService`, Spring imports, and assertions depend on the specific application. Do not copy it as a complete test. Depending on test configuration and `SpringExtension`, beans injected into the outer class can be accessed by child classes.

Spring provides `@NestedTestConfiguration(EnclosingConfiguration.OVERRIDE)` when you need to change how configuration is inherited in a child group. The default mode can also be changed via the `spring.test.enclosing.configuration` property; if a child test does not have the expected annotations/config, check both annotations and system properties.

### Three limitations to remember

1. **ApplicationContext can be cached and reused** across tests with equivalent configurations. `@Nested` does not guarantee a fresh context for each child class; introducing many different profiles/properties can also increase context count and execution time.
2. **Test object lifecycle does not mean DB data is rolled back.** When testing repositories or services, appropriate transactions/cleanup must be in place. `@Transactional` on tests follows Spring Test's transaction management semantics; operations running in another process or thread may not participate in that transaction.
3. **Do not add `@SpringBootTest` just to use `@Nested`.** If you are only testing plain Java rules, JUnit Jupiter suffices. When testing HTTP, use the web slice or integration test with the right scope; when testing the DB, use a real repository/DB or equivalent environment.

Useful grouping examples for a controller: `ValidRequests`, `MissingFields`, `Unauthenticated`, `Forbidden`, with explicit assertions on HTTP status, body, and error mapping. Grouping only improves test readability; the scope of evidence still depends on the Spring context, mocks, and real dependencies used by the test.

## 7. Package organization and test naming guidelines

Place tests near the production code with the same responsibility:

```text
src/main/java/com/example/library/DocumentAccessPolicy.java
src/test/java/com/example/library/DocumentAccessPolicyTest.java
```

Keep **one top-level test class for one relatively clear responsibility**, then use `@Nested` inner classes for input conditions/states. This makes it easy to locate tests from source code and spot missing branches from the result tree.

Naming conventions:

- Outer class: `DocumentAccessPolicyTest` or `OrderControllerTest`.
- Group class: `ActiveAccount`, `BasicPlan`, `InvalidRequest`; `@DisplayName` can phrase it as "When...".
- Test method: action-oriented behavior name, such as `deniesPremiumDocument`, `rejectsNullPlan`.
- Shared fixture: outer-level `@BeforeEach`; group-specific fixture: `@BeforeEach` at that level.
- Typically 1–2 nested levels are easy to follow; avoid deep nesting that forces readers to trace through many setups for a single test.

Do not use `static` nested test classes. A Java `static class` nested inside another is a nested class in Java syntax, but JUnit Jupiter **`@Nested` requires a non-static inner class**. If a group only exists to feed parameterized datasets to one rule, use `@ParameterizedTest` instead.

## 8. Common mistakes

| Symptom | Common cause | Fix |
|---|---|---|
| Methods in the child class do not run | Missing `@Nested`, class declared `static`, running with JUnit 4 runner, or missing Jupiter engine | Use a non-static `@Nested class`, configure JUnit Jupiter/Platform |
| `policy` or fixture is `null` | Assuming setup in a sibling group also runs for another group | Move shared setup to the outer class; place specific setup in the right ancestor group |
| Test passes alone, fails when running the whole group | Static/shared state, uncleaned DB/files, `PER_CLASS` lifecycle sharing state | Prepare isolated data and restore/clean up after each test |
| `@BeforeAll` throws an error | Static/lifecycle declaration incompatible with Java/JUnit | Use a static callback when supported, or `PER_CLASS` with a non-static callback |
| A group causes too many Spring contexts to start | Excessively varied context/profile configurations | Narrow test scope, use slices, manage profiles and context cache |
| Report looks nice but test catches no bugs | Clear `@DisplayName` but weak assertions or only checking non-null | Assert exact outcomes, statuses, state, and edge cases |
| Tests seem to run in a different order than before | Assuming groups or methods run in declaration order | Design independent tests; do not rely on UI display order |
| Very deep test tree | Nesting for every data variant and every single condition | Flatten layers; use parameterization for multiple inputs sharing one rule |

**Do not use `@TestMethodOrder` just to patch state dependencies.** Test execution order should be treated as an operational detail, not a condition for business logic to pass. Do not assume `@Nested` automatically runs serially if the environment enables parallel execution: shared resources must be managed properly.

## 9. Practice checklist

- [ ] I have at least two genuinely distinct contexts that benefit from clear naming.
- [ ] Every `@Nested` group class is a **non-static** inner class.
- [ ] `@Test` methods have assertions for specific behavior, not just nice group names.
- [ ] Shared setup is at the outer level, specific setup at the inner level, following the lifecycle order.
- [ ] Tests do not depend on execution order or mutable state from other tests.
- [ ] `@BeforeAll`/`@AfterAll` and `@TestInstance` are chosen based on real lifecycles, not to share state arbitrarily.
- [ ] `@ParameterizedTest` is used when multiple inputs share the same expected behavior.
- [ ] Unit tests do not load a Spring context unnecessarily; integration tests explicitly know which config/beans/DB they use.
- [ ] When Spring TestContext is used, I understand nested configuration inheritance and context caching rules.
- [ ] Maven/Gradle discovers all test groups; I ran the full class and verified the actual invocation count.

**Remember:** `@Nested` clarifies **Given (context)**, while each `@Test` proves **When/Then (behavior and outcome)**. Use structure to express business rules and avoid hidden state; add nesting levels only when those levels make tests easier to read and maintain.

### Further reading

- [JUnit User Guide — Nested Tests](https://docs.junit.org/6.0.0/writing-tests/nested-tests.html)
- [JUnit User Guide — Annotations](https://docs.junit.org/6.0.0/writing-tests/annotations)
- [Spring Framework — Nested TestContext Configuration](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/support-classes.html)
