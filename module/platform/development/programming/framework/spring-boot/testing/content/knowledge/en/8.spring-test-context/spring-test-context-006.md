# Context Hierarchy and Parent/Child Configuration Scope

## 1. Understanding the Topic in Spring TestContext

A **context hierarchy** is a relationship between **two or more distinct `ApplicationContext` objects**: a lower-level context (child) can look up beans in an upper-level context (parent) when no matching bean is found locally. Each context has its own bean definitions, bean lifecycle, and configuration scope. The Spring TestContext Framework lets you declare this relationship in integration tests using `@ContextHierarchy` together with `@ContextConfiguration`.

The most important point is the **asymmetric lookup direction**:

- **Child → parent:** the child can use parent beans via the context tree lookup mechanism.
- **Parent ↛ child:** the parent cannot automatically see beans defined only in a child.
- **Child A ↛ child B:** two child contexts sharing a parent cannot automatically see each other's local beans.
- **Duplicate bean names:** a local bean in a child can **shadow** a bean with the same name in the parent when looked up through the child; the parent's bean still exists and continues to be used normally by the parent.

Lesson goals: understand the structure, define hierarchies in Java 17+/Spring Boot tests, verify actual bean scopes with JUnit Jupiter, distinguish configuration inheritance from Java class inheritance, and understand how hierarchies affect the context cache, `@DirtiesContext`, profiles, bean overrides, and Spring MVC.

### 1.1. When Is a Hierarchy Needed?

A single context suffices for most Spring Boot unit tests, slice tests, and integration tests. A hierarchy makes sense when **the application genuinely organizes contexts into tiers**, such as:

1. **Root/DispatcherServlet-style Spring MVC:** a root context holds services, repositories, and infrastructure; a DispatcherServlet owns a child `WebApplicationContext` holding controllers, handler mappings, and MVC configuration.
2. **Multiple web contexts sharing a common foundation:** two servlets/endpoint groups share services from one root while keeping separate controllers and web configurations.
3. **Spring Batch or modularized applications:** infrastructure configuration lives in the parent, while each job/module has its own child context.
4. **Testing a specific layered structure:** needing to prove which tier owns a bean, what the child inherits, and that a change in a child does not alter the parent's scope.

**Do not infer that every Spring Boot application automatically has root + child contexts.** Many standard Boot Servlet applications run inside a single application context. Using `@SpringBootTest`, `@WebMvcTest`, or organizing packages into layers does not automatically create a context hierarchy. Declare a hierarchy only when the runtime design or test scenario genuinely calls for it.

## 2. Diagram and Bean Visibility Rules

Imagine one parent and two children:

```text
                      Parent ApplicationContext
                    ┌─────────────────────────────┐
                    │ dataSource                  │
                    │ paymentRepository           │
                    │ paymentService              │
                    │ label = "SHARED"            │
                    └───────────┬─────────────────┘
                                │
                  ┌─────────────┴──────────────┐
                  │                            │
          Child A Context               Child B Context
       ┌──────────────────┐          ┌──────────────────┐
       │ restController   │          │ soapEndpoint     │
       │ label = "REST"   │          │ label = "SOAP"   │
       └──────────────────┘          └──────────────────┘

Child A: sees paymentService, restController; looking up label => "REST".
Child B: sees paymentService, soapEndpoint; looking up label => "SOAP".
Parent: does not see restController or soapEndpoint;
        looking up label on parent still returns "SHARED".
```

This is a **conceptual diagram**, not an implementation program. In a real hierarchy, child A and child B are two separate context objects sharing one parent; they do not merge into a single flat context.

| Question | On Parent | On Child |
|---|---|---|
| Can a bean declared only in the parent be looked up? | Yes, locally | Yes, via ancestor if not shadowed |
| Can a bean declared only in a child be looked up? | No | Yes, locally |
| Bean with the same name exists in both parent and child? | Lookup on parent gets parent's | Lookup on child prefers local bean |
| Does a parent singleton have the same instance when accessed from a child? | Owned by parent | Lookup from child returns the same parent singleton unless shadowed |
| Does a child's bean appear automatically in a sibling child? | Not applicable | No, a sibling is not an ancestor |

### 2.1. Separating Bean Registration from Bean Lookup

When calling `child.getBean("paymentService")`, Spring may not find that name in the child and continue searching in the parent. **This does not mean the bean was copied or re-registered into the child.**

Therefore, two APIs have distinct meanings:

- `child.containsBean("paymentService")` can be `true`: the name can be resolved across the hierarchy including the parent.
- `child.containsLocalBean("paymentService")` can be `false`: the child itself did not register a bean by that name.
- `child.getParent()` returns the immediate parent context; for a root context, it returns `null`.

To verify "the bean is placed in the right tier," use `containsLocalBean(...)` or inspect `getParent()` directly when appropriate. `@Autowired` succeeding alone does not prove the bean was defined in the child.

### 2.2. Duplicate Names Across Tiers Are Not Same-Context Override Errors

If both parent and child define a bean named `label`, the child shadows the parent bean for lookups by name. The parent is unmodified, and both contexts continue managing their own instances.

Distinctions to remember:

- **Same name in two different contexts:** valid in a parent/child relationship; child lookup prefers local.
- **Same name between two bean definitions in the same context:** may be rejected or governed by that single context's bean definition overriding policy.
- **Same type with different names:** autowiring by type may find multiple candidates and throw `NoUniqueBeanDefinitionException`. Names, `@Qualifier`, `@Primary`, and bean placement in the hierarchy can all influence selection. Do not mechanically assume "having a child ignores every parent bean of that type."

**Scope** here primarily means *registration and lookup visibility across contexts*, not `singleton/prototype/request/session` bean scopes. A `singleton` bean is only a singleton within **the bean factory/context that owns it**; a parent singleton used by a child still belongs to the parent.

## 3. What Do `@ContextHierarchy` and `@ContextConfiguration` Declare?

In Spring TestContext, `@ContextHierarchy` accepts an array of `@ContextConfiguration` elements. Each element describes **one context level**, ordered from parent first to child after:

```java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(
        name = "parent",
        classes = ParentConfig.class),
    @ContextConfiguration(
        name = "child",
        classes = ChildConfig.class)
})
class HierarchyIntegrationTest {
    // Tests use the loaded child ApplicationContext.
}
```

This is an **illustrative configuration snippet**, assuming the config classes already exist. Meaning:

1. TestContext loads `ParentConfig` into the parent-level context.
2. Loads `ChildConfig` into the child-level context, with its parent pointing to the context created in step 1.
3. `SpringExtension` integrates Spring TestContext with JUnit Jupiter, handling dependency injection, lifecycle callbacks, and caching support.
4. `@Autowired ApplicationContext` in a test typically receives **the lowest (child) context** of the hierarchy.
5. `name = "parent"/"child"` assigns a **hierarchy level name**, useful when a test subclass wants to merge/override a specific level; it is **not a bean name**.

You can use `classes = ...` to supply `@Configuration` classes, or `locations = ...` for XML configs if the system uses XML. A hierarchy can contain levels using different resource types; when **merging the same level** through test class inheritance, the resource type at that level must be consistent.

**Do not confuse with:**

- `@ContextConfiguration(classes = {A.class, B.class})`: multiple config classes contributing to **one** context (when there is no hierarchy).
- `@Import(B.class)`: pulls additional bean definitions into the current config; does not create a child context.
- `@Nested` in JUnit: nests test classes for test organization; does not automatically create a Spring context level.
- `@Configuration` class extending another class: Java/config inheritance; does not automatically create an `ApplicationContext.getParent()` relationship.

## 4. Complete Java 17+ Example: Checking Parent/Child Beans

The example below needs only **a single test file** inside a Spring Boot project with JUnit Jupiter, Spring TestContext, and Spring Context. It needs no controller, server, database, or Docker. The goal is to verify the exact context structure with runnable code rather than just reading descriptions.

### 4.1. Project Configuration to Run

In a Spring Boot Gradle Groovy DSL project **that already has the Spring Boot plugin, repositories, and appropriate dependency management**, ensure the starter and test starter are present:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Or in Maven, the test dependency belongs in your project's `pom.xml`:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

A real Spring Boot application normally already includes a production starter. These snippets are **dependency additions**, not complete build files; do not declare duplicate dependencies. Run from the module containing the test.

### 4.2. Standalone Test File

Create **`src/test/java/com/example/testing/context/ContextHierarchyTest.java`**:

```java
package com.example.testing.context;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.ContextHierarchy;
import org.springframework.test.context.junit.jupiter.SpringExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(
        name = "parent",
        classes = ContextHierarchyTest.ParentConfig.class),
    @ContextConfiguration(
        name = "child",
        classes = ContextHierarchyTest.ChildConfig.class)
})
class ContextHierarchyTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    GreetingSettings settings;

    @Autowired
    GreetingService service;

    @Test
    void childCanUseParentBeanButParentCannotSeeChildBean() {
        ApplicationContext parent = context.getParent();
        assertNotNull(parent);

        assertEquals("Hello Linh", service.greet("Linh"));

        // Bean lives in parent but is resolved by child.
        assertTrue(context.containsBean("greetingSettings"));
        assertFalse(context.containsLocalBean("greetingSettings"));
        assertTrue(parent.containsLocalBean("greetingSettings"));
        assertSame(parent.getBean(GreetingSettings.class), settings);

        // Bean declared only in child.
        assertTrue(context.containsLocalBean("greetingService"));
        assertFalse(parent.containsBean("greetingService"));
    }

    @Test
    void childBeanWithSameNameShadowsParentBean() {
        ApplicationContext parent = context.getParent();
        assertNotNull(parent);

        assertEquals("CHILD", context.getBean("label", String.class));
        assertEquals("PARENT", parent.getBean("label", String.class));
        assertTrue(context.containsLocalBean("label"));
        assertTrue(parent.containsLocalBean("label"));
    }

    record GreetingSettings(String prefix) {}

    static final class GreetingService {
        private final GreetingSettings settings;

        GreetingService(GreetingSettings settings) {
            this.settings = settings;
        }

        String greet(String name) {
            return settings.prefix() + " " + name;
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class ParentConfig {
        @Bean
        GreetingSettings greetingSettings() {
            return new GreetingSettings("Hello");
        }

        @Bean("label")
        String parentLabel() {
            return "PARENT";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class ChildConfig {
        @Bean
        GreetingService greetingService(GreetingSettings settings) {
            return new GreetingService(settings);
        }

        @Bean("label")
        String childLabel() {
            return "CHILD";
        }
    }
}
```

**Expected result:** **2 passing `@Test` methods** on Spring Framework supporting `@ContextHierarchy` and JUnit Jupiter. The file prints nothing to stdout; test counts in console/reports depend on the build tool. One test confirms the child can use a bean configured in the parent while the parent cannot see a child-only bean; the other confirms shadowing by **name**.

Run on Linux/macOS:

```bash
# Gradle project
./gradlew test --tests "com.example.testing.context.ContextHierarchyTest"

# Or Maven project using Surefire/JUnit Jupiter
./mvnw -Dtest=ContextHierarchyTest test
```

Pick the right command for your project type; do not assume both wrappers exist. On Windows PowerShell, you can use `.\gradlew.bat test --tests "com.example.testing.context.ContextHierarchyTest"` or `.\mvnw.cmd "-Dtest=ContextHierarchyTest" test`. If the Maven Surefire plugin or Gradle test task does not pick up the test, verify JUnit Platform configuration and source sets/test selectors before blaming the hierarchy.

### 4.3. Explaining the Execution Path in the Test

- TestContext builds **ParentConfig** as a parent context containing `greetingSettings` and a bean named `label` with value `PARENT`.
- TestContext builds **ChildConfig** as a child context containing `greetingService` and a bean named `label` with value `CHILD`.
- When Spring creates `greetingService(GreetingSettings settings)` in the child, type `GreetingSettings` is resolved in the parent; `GreetingService`'s constructor receives that bean.
- `@Autowired GreetingSettings settings` in the test receives the instance provided by the parent. `assertSame` confirms it is the **exact same instance**, because beans default to singleton in the parent.
- `context.containsBean("greetingSettings")` is `true`, whereas `context.containsLocalBean("greetingSettings")` is `false`: the child finds the bean through the parent, but **does not own that bean definition**.
- `parent.containsBean("greetingService")` is `false`: there is no reverse lookup path from parent down to child.
- The two `label` beans live in **two different contexts**, so querying on the child returns `CHILD` while querying on the parent returns `PARENT`. This is shadowing in a context hierarchy, not a duplicate bean definition inside one factory.

If the example fails at startup, read the root cause. A bean in the parent depending on a child-only bean cannot be created via normal lookup; place shared dependencies in the parent or fix the dependency direction in the design.

## 5. Parent and Child Configuration Scope: Where Should Beans Live?

A common division:

| Component Category | Parent Usually Manages | Child Usually Manages |
|---|---|---|
| Shared business services | Services, policies, repositories, transaction infrastructure | Beans specific to an endpoint/job/module |
| Connectivity infrastructure | Shared DataSource, HTTP clients, message clients if needed | Configuration specific to one servlet/module |
| Web MVC | Only appropriate shared components | Controllers, handler mappings, MVC adapters |
| Test configuration | Shared test fixtures/config across children | Test beans specific to each child |
| State | Intentionally shared singletons | Locally scoped beans |

This is a **suggested design guideline**, not a rigid Spring rule for every bean type. Components should only live in the parent if they are genuinely shared across multiple children and do not depend backward on child beans.

### 5.1. Dependencies Must Point in the Right Direction

**Valid:** a service created in the child needs a repository in the parent. The child can resolve the repository from its ancestor.

**Problematic:** a service created in the parent needs a controller that exists only in the child. The parent has no way to discover the child during dependency resolution; autowiring will normally fail. If the parent needs a callback or interface, put a shared contract in the parent and design an appropriate registration mechanism; do not simply dump every bean into the parent to hide the error.

### 5.2. Using the Right Scope When Testing

A `singleton` bean owned by the parent may be shared as the same instance across multiple children; if it holds mutable state and a test mutates that state, tests sharing the parent can affect one another. Adding a child context **does not automatically isolate mutable parent state**.

Conversely, if two children each declare their own `CacheService` bean, they usually get independent instances because they belong to two separate factories (under default singleton scope). However, if the bean uses static fields, an external DB/Redis, or an off-JVM singleton, context isolation **does not guarantee** isolation of those external resources.

### 5.3. Parent/Child Contexts vs. `BeanDefinition` Inheritance

Spring XML has a concept of a "child bean definition inheriting from a parent bean definition" via the XML `parent` attribute. That is **bean definition metadata inheritance**, completely different from the relationship between **two `ApplicationContext` instances** and `getParent()`. When reading "parent/child" in Spring docs, distinguish whether it refers to context objects, config classes, or bean definitions.

## 6. Inheriting Hierarchies Across Test Classes: Merging and Overriding the Right Level

Spring TestContext allows declaring part of a hierarchy on a **test superclass** and extending/adjusting it on a **test subclass**. This technique differs from Java class inheritance of business logic; it describes only the context configuration Spring TestContext loads for the final test class.

### 6.1. Naming Each Level to Merge Accurately

**Illustrative, assuming config classes already exist; not a standalone program:**

```java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(
        name = "parent", classes = SharedConfig.class),
    @ContextConfiguration(
        name = "child", classes = WebConfig.class)
})
abstract class BaseWebIntegrationTest {
}

@ContextHierarchy(
    @ContextConfiguration(
        name = "child", classes = ExtraWebConfig.class)
)
class ExtendedWebIntegrationTest extends BaseWebIntegrationTest {
}
```

In the subclass, Spring **merges the configuration of the level named `child`**. Conceptually:

- Parent uses `SharedConfig` like the base class.
- Child is configured from `WebConfig` **and** `ExtraWebConfig`.
- A third level is not created just because the subclass also has `@ContextHierarchy`.
- If `ExtraWebConfig` defines a bean with the same name as `WebConfig` inside the **same child context**, review overriding policies and configuration rather than mistaking it for cross-level shadowing.

Level names form a contract during inheritance. If a subclass introduces a new name that does not match the intended level, Spring may form another level, altering the dependency graph and context load speed.

### 6.2. Overriding Configuration at the Exact Level with `inheritLocations = false`

Suppose the base class defines the parent/child hierarchy above, but a test subclass needs to replace **the entire child configuration** with an alternative test config:

```java
@ContextHierarchy(
    @ContextConfiguration(
        name = "child",
        classes = AlternativeWebConfig.class,
        inheritLocations = false)
)
class AlternativeWebIntegrationTest extends BaseWebIntegrationTest {
}
```

Meaning: the `child` level uses `AlternativeWebConfig` instead of also inheriting `WebConfig` from the base; the parent still keeps `SharedConfig`. The default `inheritLocations = true` merges configurations at the same level when valid. The `inheritInitializers` attribute controls initializer inheritance separately and follows corresponding rules; do not conflate the two.

**Key point:** `inheritLocations = false` only affects **configuration inheritance for the named level** in the test class hierarchy; it does not mean "delete the parent ApplicationContext" nor does it delete beans existing in a runtime app.

### 6.3. Implicit Parent Context via Superclass

Spring TestContext also has a scenario where a superclass declares a regular `@ContextConfiguration`, and then a subclass declares `@ContextHierarchy`. In official documentation examples, the superclass configuration can become an **implicit parent context** for the child contexts in subclasses. Therefore, inspect annotations on superclasses as well when investigating a hierarchy; do not look only at the current test class.

For new code, **name `parent` and `child` levels explicitly** when extending via inheritance. This reduces confusion between "merging configs into one context" and "adding a level to a hierarchy."

## 7. Spring MVC: Root and DispatcherServlet Contexts

A traditional Spring MVC architecture may have:

- **Root `WebApplicationContext`:** shared services, repositories, and infrastructure, typically created by `ContextLoaderListener`.
- **Child `WebApplicationContext`:** controllers, handler mappings, and `DispatcherServlet`-specific configuration.

In an integration test modeling this architecture, you can combine `@WebAppConfiguration` with `@ContextHierarchy`:

```java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextHierarchy({
    @ContextConfiguration(
        name = "root", classes = SharedWebRootConfig.class),
    @ContextConfiguration(
        name = "dispatcher", classes = MvcDispatcherConfig.class)
})
class MvcHierarchyIntegrationTest {

    @Autowired
    WebApplicationContext webContext;

    // MockMvc can be configured against the child WebApplicationContext.
}
```

This is an **illustrative snippet**: it requires config classes, Spring Test/MVC imports, and project controllers to run. Under an appropriate `@WebAppConfiguration` environment, `webContext` is injected as the **child/lowest `WebApplicationContext`**, so it can see both child controllers and root services.

**Distinction with Spring Boot:** a Boot web application typically uses a single context created by auto-configuration; it **does not necessarily** replicate the traditional two-context root/dispatcher architecture. Do not add `@ContextHierarchy` to every `@SpringBootTest` or `@WebMvcTest` just because it is a web test. When using MockMvc in Boot, `@AutoConfigureMockMvc` is often enough for HTTP verification.

When a real application explicitly uses multiple DispatcherServlets or hierarchical contexts, test hierarchies can reflect that architecture. Use meaningful level names (e.g., `root`, `apiServlet`) and ensure each config class loads into the **right level**.

## 8. Spring TestContext Cache When Using Hierarchies

The Spring TestContext Framework **caches loaded `ApplicationContext` instances** within the same test process so test classes with equivalent configs do not rebuild every bean. With hierarchies, configuration levels can be cached and reused independently under matching keys.

Example of two test groups:

```text
Context hierarchy for Test A: SharedConfig -> RestConfig
Context hierarchy for Test B: SharedConfig -> SoapConfig

If the parent's cache key is compatible:
    the same SharedConfig parent can be reused;
    RestConfig and SoapConfig create distinct child contexts.
```

This is a **conditional caching model** and does not promise that every test sharing a config class name will definitely reuse the exact same object: cache keys are also affected by loaders, initializers, active profiles, property sources, context customizers, parent configuration, and related factors. The context cache also has a size limit and can evict entries.

### 8.1. Benefits and Risks of Reusing a Parent

Benefit: saves startup cost for expensive infrastructure beans and speeds up CI when multiple children share a parent.

Risk: if a test mutates state on a singleton in the parent, later tests can be affected. `@ContextHierarchy` and caching are not "data reset" mechanisms. For databases/Redis/queues, use properly scoped fixtures and cleanup; a fresh context does not guarantee a clean database.

**Best practice:** keep context configs immutable, test data independent, and avoid modifying static fields or shared singletons. Only mark a context dirty when a test genuinely corrupts context state so it cannot be safely reused.

### 8.2. `@DirtiesContext` with `hierarchyMode`

Spring provides `@DirtiesContext` to mark a context as non-reusable; the framework evicts the affected contexts from cache and closes them according to the chosen mode.

When a hierarchy is declared, two important modes apply:

| Mode | Effect on Cache | When to Consider |
|---|---|---|
| `EXHAUSTIVE` (default for hierarchies) | Evicts all subhierarchies sharing the appropriate ancestor with the current context; scope can be broad | Shared/parent infrastructure was mutated and the entire related branch must be clean |
| `CURRENT_LEVEL` | Evicts the context at **the lowest level visible to the current test** and contexts in its subhierarchy; leaves ancestors intact | Test only corrupted child-specific state and wants to keep the clean parent cached for reuse |

**Illustration** on a test already declaring a hierarchy as in Section 4:

```java
@Test
@DirtiesContext(
    hierarchyMode = DirtiesContext.HierarchyMode.CURRENT_LEVEL
)
void mutatesChildOnlyState() {
    // Action that genuinely dirties state in the child.
}
```

This is an **illustrative snippet**, not a standalone runnable test. In `CURRENT_LEVEL` mode, "current level" is the lowest level visible to the test class; if the test injects the child, that is usually the child. If that context has descendants beneath it, those descendants are evicted too. `EXHAUSTIVE` mode can affect other hierarchies sharing an ancestor, so it carries a higher cost.

**Do not add `@DirtiesContext` unconditionally to every test** to "ensure independence." Doing so reloads contexts constantly, hides poor fixtures, and slows down the suite. Choose `hierarchyMode = CURRENT_LEVEL` only when there is evidence the dirty state lives in the child; if the parent was genuinely mutated, keeping the parent cached can break other tests.

## 9. Bean Overrides and Mocks Must Target the Right Level

In a Spring TestContext test, you may want to replace a dependency with a fake/mock to isolate failures. With a hierarchy, you must know **which level holds the real bean** and **which level receives the override**.

### 9.1. Versions Supporting `contextName`

In **Spring Framework 6.2+**, test bean overriding provides annotations such as `@MockitoBean`, `@MockitoSpyBean`, and `@TestBean`. With a hierarchy, you can specify `contextName` matching the `name` on `@ContextConfiguration` to restrict the override to one level:

```java
@ContextHierarchy({
    @ContextConfiguration(
        name = "parent", classes = SharedConfig.class),
    @ContextConfiguration(
        name = "child", classes = FeatureConfig.class)
})
class FeatureIntegrationTest {

    @MockitoBean(contextName = "child")
    FeatureGateway featureGateway;
}
```

**This is only an illustrative snippet**, not a standalone test: it requires the test extension, config classes, field type, and a supporting Spring Framework version. It expresses the intent to replace the `FeatureGateway` bean at the `child` level.

In Spring Boot **3.3.x projects using Spring Framework 6.1.x**, `@MockitoBean` does not yet exist; Boot previously provided its own `@MockBean`/`@SpyBean` (Boot began deprecating those annotations in 3.4). Do not copy `@MockitoBean(contextName=...)` into an older project and conclude Mockito cannot mock. Always read documentation matching your exact version.

### 9.2. Why Is an Explicit Level Needed?

If a bean type exists in both parent and child, or you want to override a bean defined at a single level, an unscoped mock config may replace the wrong bean or affect multiple levels. With `@MockitoBean/@MockitoSpyBean` in newer Spring Framework versions, an override without `contextName` may be considered across hierarchy levels; specifying the name avoids overly broad semantics.

Distinguish clearly:

- Mockito's `@Mock` creates a mock inside the test class; **it does not automatically replace a bean in the Spring context**.
- `@MockitoBean`/`@MockBean` are framework/version-specific mechanisms for overriding beans inside the test context.
- Stubbing a parent mock can affect **every child using that parent** if context caching reuses the parent; therefore manage resets/stubbing and avoid state leakage.
- A local bean in a child can shadow a parent bean of the same name; if you mock in the parent while the child defines a same-named bean, lookups through the child may never reach the parent mock.

Do not treat "mocking worked" as proof of valid configuration: assert the exact bean injected into the SUT and the exact level affected.

## 10. Profiles, Properties, and Configuration Scope

Annotations/sources like `@ActiveProfiles`, `@TestPropertySource`, `@DynamicPropertySource`, and `@Configuration` affect how contexts load. In a hierarchy, **do not deduce properties/profiles from level names**. Level names `parent` and `child` in `@ContextConfiguration` only identify hierarchy levels; they do not activate corresponding profiles.

### 10.1. Questions to Verify

1. Which bean config classes load into the parent vs. the child?
2. Is a bean with `@Profile("test")` registered in the intended context when the test activates the profile?
3. Which property sources and precedence actually take effect in each context? Does the parent environment merge into the child?
4. Does the test class inherit `@ActiveProfiles` or `@TestPropertySource` from a superclass?
5. If a context is already cached with different configs/properties, does the current test reuse it or build a new one?

**Hypothetical example:** the parent declares `DataSource` and the child declares controllers. If the child needs a different DB URL for testing, yet the parent already built `DataSource` from a different property, changing a property only in the child after the parent initialized **will not rebuild the parent bean**. Supply configuration/overrides at the right time and to the level that owns the bean.

### 10.2. Reducing Drift Between Local IDE and CI

A hierarchy test can pass in an IDE yet fail in CI if profiles, environment variables, JDK, config resource paths, databases, or mock overrides differ. Compare:

- Same set of config classes/locations and annotations on the test superclass.
- Same active profiles, test properties, and dependency versions.
- Same JVM/test runner; same context loader capable of loading hierarchies.
- Same cache policy, parallel execution settings, and fixture state.

For debugging, you can log bean names and parent contexts in the test environment, avoiding logging secrets. Use `context.getParent()`, `containsLocalBean`, and `containsBean` to narrow down **which exact level owns a bean**, rather than guessing from a long stack trace.

## 11. Common Pitfalls and How to Trace Them

| Symptom | Likely Cause | How to Fix |
|---|---|---|
| Test sees `context.getParent() == null` | Only one context loaded; hierarchy not declared or recognized properly | Check `@ContextHierarchy`, extension, and test bootstrapper |
| `NoSuchBeanDefinitionException` when creating a parent bean | Parent depends on a bean that exists only in the child | Move shared dependency up to parent or fix dependency direction |
| Child does not see parent bean | Parent did not load intended config, profile inactive, or bean is shadowed | Inspect actually loaded configs and local bean names |
| Same bean name returns different values across two levels | Shadowing by name, which may be completely intentional | Query parent and child directly; assert the intended contract |
| `NoUniqueBeanDefinitionException` in child | Multiple beans of the same type with different names and no clear selection rule | Use `@Qualifier`/`@Primary` or adjust config |
| Bean overriding error when merging configs | Two bean definitions with the same name inside **one context** | Rename/adjust definitions or fix level merging; do not confuse with shadowing |
| Subclass gets three contexts instead of two | `@ContextHierarchy` added a level with a different name or unexpected inheritance | Keep `name` consistent, read superclass annotations |
| Child still has old config beans in subclass | Default `inheritLocations = true` merges configs at the same named level | Use `inheritLocations = false` when genuinely replacing a level's config |
| Cache very slow or parent keeps reloading | Overly broad `@DirtiesContext`, varying profiles/properties/customizers causing cache misses | Review cache keys, dirty scope, shared state |
| Test mocks the wrong hierarchy level | Override applies across multiple levels or is shadowed by local bean | Use version-appropriate scoped overrides; assert the real injected bean |
| MVC test context lacks servlet infrastructure | Missing `@WebAppConfiguration` or improper web context config | Use proper web test setup and root/dispatcher configs |
| Spring Boot `@SpringBootTest` does not build root/child as expected | Boot does not automatically create a hierarchy just because web starter is present | Use hierarchies only when app/runtime needs them, and configure tests explicitly |

### 11.1. Reproducible Diagnostic Sequence

If a `@ContextHierarchy` test fails:

1. **Identify when the error occurred:** test compilation, loading config classes, refreshing the bean factory, dependency injection, or assertion.
2. **Read the first meaningful root cause:** `BeanCreationException` is often a wrapper; locate the underlying cause involving bean definitions, profiles, properties, or ambiguity.
3. **Verify the number of levels:** `@Autowired ApplicationContext`, inspect `getParent()`, and walk up ancestors; do not assume there are always two levels.
4. **Verify bean ownership:** use `containsLocalBean` at each level and compare against `containsBean`.
5. **Verify config inheritance:** inspect `@ContextHierarchy` on superclasses and subclasses; compare `name`, `inheritLocations`, `classes/locations`.
6. **Check caching only when needed:** was a context dirtied, did a test mutate singleton state, or did it create many config variants?
7. **Re-run via the build wrapper:** ensure the same module, profiles, and required properties as CI.

Do not fix failures by enabling bean overriding globally or adding `@DirtiesContext` to every test. Both can make tests pass temporarily while masking layering errors or shared state leaks.

## 12. Misconceptions to Clear Up

**"The child sees the parent bean, so that bean belongs to the child."** False. The child can resolve beans from the parent; `containsLocalBean` confirms where it is actually registered.

**"The parent can `@Autowired` a controller in the child."** Generally false. The parent is created first and has no bean factory lookup downward into children.

**"Two children of the same parent automatically see each other's beans."** False. They only share what the ancestor provides.

**"Two beans with the same name in parent and child always cause a duplicate error."** False if they belong to two different contexts; duplicate definitions inside the same bean factory are a separate issue.

**"Java `extends` on a base test class automatically creates a context hierarchy."** False. You must inspect how `@ContextConfiguration`/`@ContextHierarchy` are declared and inherited.

**"The level name `child` is a bean name."** False. Level names control TestContext merging/overriding; bean names are determined by `@Bean` and bean-naming rules.

**"`@DirtiesContext` removes only the single modified bean."** False. The framework marks contexts and updates the **context cache**, not individual beans.

**"`@DirtiesContext(CURRENT_LEVEL)` always cleans up all data."** False. It evicts the context at the current level and applicable descendants from cache; external databases, files, message queues, or parent singletons can still retain state.

**"`@SpringBootTest` automatically builds a root + DispatcherServlet child hierarchy."** Not by default. Hierarchies require explicit structure; single-context Boot tests remain the norm.

## 13. Self-Check Exercises

### Exercise A — Why Do Lookup Results Differ?

Suppose the parent has `@Bean("paymentMode")` returning `"NORMAL"`, and the child declares a bean of the same name returning `"SANDBOX"`. Predict:

- `child.getBean("paymentMode")`;
- `parent.getBean("paymentMode")`;
- `child.containsLocalBean("paymentMode")`;
- `parent.containsLocalBean("paymentMode")`.

**Answer:** `"SANDBOX"`, `"NORMAL"`, `true`, and `true`, respectively. The two beans live in **two different contexts**, so they do not overwrite each other.

### Exercise B — Checking Which Level Owns a Bean

Suppose the child can use `sharedRepository`, but the test must prove the bean actually lives in the parent. Write two assertions:

```java
assertTrue(child.containsBean("sharedRepository"));
assertFalse(child.containsLocalBean("sharedRepository"));
```

This snippet **assumes** `child` is a valid `ApplicationContext` and the test imports JUnit's `assertTrue/assertFalse`. To prove it even more strictly, add `assertTrue(child.getParent().containsLocalBean("sharedRepository"))` after confirming the parent is not null.

### Exercise C — Merge or Override?

A base test declares:

```java
@ContextHierarchy({
    @ContextConfiguration(name = "parent", classes = SharedConfig.class),
    @ContextConfiguration(name = "child", classes = WebConfig.class)
})
abstract class BaseTest {
}
```

Two **different** subclass declarations:

```java
// Merge more config into the child level:
@ContextHierarchy(
    @ContextConfiguration(
        name = "child",
        classes = ExtraWebConfig.class))
class MergeTest extends BaseTest {
}

// Replace the child-level configuration:
@ContextHierarchy(
    @ContextConfiguration(
        name = "child",
        classes = AlternativeWebConfig.class,
        inheritLocations = false))
class ReplaceTest extends BaseTest {
}
```

These are **snippets for reading semantics**, not standalone runnable examples. Answer for yourself: do both subclasses keep the parent, does a third level get created, and does the child's old config remain?

**Answer:** Both keep the `SharedConfig` parent and target the level named `child`. `MergeTest` keeps `WebConfig` and adds `ExtraWebConfig`; `ReplaceTest` uses `AlternativeWebConfig` instead of the inherited child config. No third level is created when reusing the same level name.

### Exercise D — Choosing Dirty Mode

Two hierarchy tests share one parent context and use different children. One test mutates **only** mutable state inside a child, leaving the parent untouched. Consider `@DirtiesContext(hierarchyMode = CURRENT_LEVEL)` to evict the dirty context while keeping the ancestor. If the test mutates a parent singleton, keeping the parent cached is dangerous; use an appropriate isolation/cleanup strategy or dirty at a broader scope.

### Checklist Before Finishing a Hierarchy Test

- [ ] Clearly understood whether the real app needs multiple `ApplicationContext` instances or a single context.
- [ ] Each level is described by the right `@ContextConfiguration`, ordered parent → child.
- [ ] When subclasses merge/override, `name` is consistent across levels.
- [ ] Understood `inheritLocations` and did not confuse merging with adding a new level.
- [ ] Shared beans are owned by the appropriate ancestor, and children do not force reverse parent dependencies.
- [ ] Distinguished `containsBean`, `containsLocalBean`, and `getParent()`.
- [ ] Handled same-name shadowing and same-type ambiguity according to the contract.
- [ ] Context cache and `@DirtiesContext` scope do not break isolation for other tests.
- [ ] Bean overrides/mocks target the right level and match the Spring version.
- [ ] Profiles, properties, config resources, and build tools align across IDE and CI.
- [ ] Examples/tests verify real behavior, not merely `assertNotNull(context)`.
- [ ] Can run tests individually and as a full suite; configuration errors are diagnosed by context level.

## 14. Key Takeaways to Apply Properly

In Spring TestContext, `@ContextHierarchy` is a tool for creating **multiple contexts with a genuine parent/child relationship**. Parent beans can be looked up by children, child beans do not flow back up to the parent, and same-named local beans in a child shadow parent beans without deleting the parent bean. Across a test class hierarchy, **level names + inheritance rules** determine whether configs merge or override. Caching and `@DirtiesContext` can affect multiple contexts, so choose the scope matching the state that actually changed.

The most valuable takeaway is not memorizing annotations, but knowing **which bean belongs to which level, who can see whom, which context is being injected, and which context is being cached/dirtied**. When you can answer those four questions with concrete assertions, you can design and debug hierarchical tests reliably.

## Official References

- [Spring Framework — Context Hierarchies (TestContext)](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/hierarchies.html): syntax, parent/child architecture, merging and overriding named hierarchy levels.
- [Spring Framework — @ContextHierarchy](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-contexthierarchy.html): annotation definition and Java/Kotlin examples.
- [Spring Framework — Context Configuration Inheritance](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/inheritance.html): `inheritLocations` and `inheritInitializers`.
- [Spring Framework — @DirtiesContext](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dirtiescontext.html): dirtying the context cache and `hierarchyMode`.
- [Spring Framework Javadoc — DirtiesContext.HierarchyMode](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/annotation/DirtiesContext.HierarchyMode.html): exact scope of `EXHAUSTIVE` and `CURRENT_LEVEL`.
- [Spring Framework — Bean Overrides in Context Hierarchies](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/hierarchies.html#testcontext-ctx-management-ctx-hierarchies-bean-overrides): `contextName` on `@MockitoBean`/`@MockitoSpyBean` in supported frameworks.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): TestContext integration and Boot testing capabilities.
