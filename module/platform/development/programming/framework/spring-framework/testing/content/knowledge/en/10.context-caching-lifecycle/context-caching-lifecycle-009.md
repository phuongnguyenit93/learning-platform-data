# Scope of hierarchyMode When Dirtying Hierarchical Contexts

The Spring TestContext Framework stores initialized `ApplicationContext` instances in a cache so tests with the same configuration can reuse a context. When a test alters the state of a context and marks it with `@DirtiesContext`, Spring evicts the context from the cache and closes it. On the next run, a test needing that configuration receives a newly created context.

With a single context, eviction is straightforward. For applications with multiple context layers declared via `@ContextHierarchy`, one context can be the parent of several child contexts, and different test classes can share part of that tree. The `hierarchyMode` attribute of `@DirtiesContext` determines how much of the context tree is evicted from the cache. The two values are `EXHAUSTIVE` and `CURRENT_LEVEL`; the default is `EXHAUSTIVE`.

## 1. Context Hierarchies and the Spring TestContext Cache

A context hierarchy is a parent-child `ApplicationContext` structure. A child context can access beans in the parent context, whereas the parent context does not look downward at beans that exist only in a child context.

A web application can split its configuration into a root context containing services, repositories, and shared beans, and a child context containing controllers, handler mappings, or web-specific configuration. Spring TestContext represents this structure using `@ContextHierarchy` with multiple `@ContextConfiguration` declarations.

```java
@ContextHierarchy({
    @ContextConfiguration(name = "root", classes = RootConfig.class),
    @ContextConfiguration(name = "web", classes = WebConfig.class)
})
class WebIntegrationTests {
    // Test uses both the root context and the web child context.
}
```

In the example, `WebConfig` creates a child context with `RootConfig` as its parent context. Beans in `WebConfig` can use beans from `RootConfig`.

When multiple test classes share the same parent configuration, Spring can reuse the parent context in the cache. For instance, an MVC test group and an API test group can have two different child contexts while sharing one root context:

```text
                    Root context
                (shared configuration)
                         |
              +----------+----------+
              |                     |
              v                     v
         MVC child              API child
         (MVC tests)            (API tests)
              |
              v
       MVC feature child
```

If a test dirties the root context, child contexts relying on that root may also no longer be safe to reuse. If a test only dirties a child context, removing both the root and other branches can force Spring to reinitialize many unaffected contexts. `hierarchyMode` helps choose the right processing scope.

## 2. What Does @DirtiesContext Do?

`@DirtiesContext` signals that a test has altered or corrupted the state of an `ApplicationContext`, such as modifying singleton bean state in a way that could affect other tests. Spring TestContext will evict the context from the cache according to configuration and close that context.

The annotation can be placed on a test method or a test class. The attributes controlling timing and scope each have a distinct role:

| Attribute | Controls | Common values |
|---|---|---|
| `methodMode` | When the context is dirtied when annotated on a method | `BEFORE_METHOD`, `AFTER_METHOD` |
| `classMode` | When the context is dirtied when annotated on a class | `BEFORE_CLASS`, `BEFORE_EACH_TEST_METHOD`, `AFTER_EACH_TEST_METHOD`, `AFTER_CLASS` |
| `hierarchyMode` | Scope of the context hierarchy evicted from the cache | `EXHAUSTIVE`, `CURRENT_LEVEL` |

If `@DirtiesContext` is placed on a method, the default is `AFTER_METHOD`. If placed on a class, the default is `AFTER_CLASS`. `hierarchyMode` does not change when dirtying occurs; it only decides how much of the context tree is removed when that action happens.

Example dirtying a context after a test method:

```java
@Test
@DirtiesContext(
        methodMode = DirtiesContext.MethodMode.AFTER_METHOD,
        hierarchyMode = DirtiesContext.HierarchyMode.CURRENT_LEVEL)
void testThatChangesChildContextState() {
    // Alters context state and needs the child context evicted from the cache.
}
```

Because `AFTER_METHOD` is the default for method-level annotations, it can be written more concisely:

```java
@Test
@DirtiesContext(hierarchyMode = DirtiesContext.HierarchyMode.CURRENT_LEVEL)
void testThatChangesChildContextState() {
    // ...
}
```

## 3. EXHAUSTIVE: Clearing the Entire Branch Sharing a Common Ancestor

`DirtiesContext.HierarchyMode.EXHAUSTIVE` is the default mode. This algorithm identifies a common ancestor context for the current test's hierarchy, then evicts from the cache and closes all `ApplicationContext` instances within the sub-hierarchy of that common ancestor.

This scope includes:

- The context at the common ancestor level.
- The test's current context.
- Child contexts beneath the current context.
- Contexts belonging to other hierarchies that share the common ancestor.

With the tree from the earlier section, if an MVC test dirties the context and `EXHAUSTIVE` is used, the scope can include the entire tree:

```text
                    Root context
                         X
              +----------+----------+
              X                     X
              v                     v
         MVC child              API child
              X
              v
       MVC feature child
```

The `X` symbol denotes a context evicted from the cache and closed. When a test in the MVC branch uses the default mode, the API branch can also be evicted because it shares the root context with the current test.

### 3.1. When Is EXHAUSTIVE Appropriate?

Use `EXHAUSTIVE` when altered state can affect the ancestor context or multiple child branches sharing that ancestor. For example:

- A test mutates a singleton bean residing in the root context.
- A test alters shared configuration or state that other child contexts depend on.
- A test modifies bean structure or resources tied to the parent context.
- You cannot be certain the change is confined to a single child context.

Because this is the default mode, simply declaring `@DirtiesContext` causes Spring to apply the exhaustive algorithm:

```java
@Test
@DirtiesContext
void modifiesSharedParentState() {
    // Operation that alters shared hierarchy state.
}
```

The advantage is broad cleanup, reducing the risk of a child context continuing to use a mutated parent. The cost is that tests in other branches may have to reinitialize contexts even though those branches themselves were untouched by the current test.

## 4. CURRENT_LEVEL: Clearing From the Current Level Downward

`DirtiesContext.HierarchyMode.CURRENT_LEVEL` only evicts the context at the lowest level of the hierarchy visible to the current test, along with all contexts in sub-hierarchies of that level. Ancestors above and sibling branches are not evicted by this operation.

In the MVC/API example, if the current test sees root and MVC child, the lowest level the test sees is MVC child. When using `CURRENT_LEVEL`, the result is as follows:

```text
                    Root context
                         |
              +----------+----------+
              |                     |
              v                     v
         MVC child              API child
              X
              v
       MVC feature child
              X
```

MVC child and its child contexts are closed and removed from the cache. The root context remains retained, and API child can continue using the cached root context.

### 4.1. Example Declaring CURRENT_LEVEL

```java
@ContextHierarchy({
    @ContextConfiguration(name = "root", classes = RootConfig.class),
    @ContextConfiguration(name = "web", classes = WebConfig.class)
})
class BaseWebTests {
    // Hierarchy configuration inherited by subclass test classes.
}

class ExtendedWebTests extends BaseWebTests {

    @Test
    @DirtiesContext(
            hierarchyMode = DirtiesContext.HierarchyMode.CURRENT_LEVEL)
    void dirtiesOnlyTheWebBranch() {
        // Alters state belonging only to the web child context.
    }
}
```

In this case, the test sees a hierarchy consisting of root and web child. The current level is web child, so `CURRENT_LEVEL` preserves root and evicts web child along with its child contexts.

### 4.2. When Is CURRENT_LEVEL Appropriate?

Use `CURRENT_LEVEL` when changes are isolated to the current context or its child branch, while the parent context remains valid and reusable. For example:

- A test mutates a singleton bean declared only in the web child context.
- A test alters the state of a handler or component belonging to the child context.
- Multiple test hierarchies share a stable root context while having distinct child contexts.
- You want to avoid reinitializing contexts in other branches when they are unaffected.

Do not choose `CURRENT_LEVEL` merely to make tests run faster if the test mutated the parent context. When a dirty parent remains in the cache, child contexts created from that parent can continue observing invalid state. Choose the scope based on where the change occurs and which contexts depend on it.

## 5. Comparing Both Algorithms on the Same Context Tree

Suppose there is a shared root context, an MVC child, and an API child. MVC child also has a feature child.

| Context | `EXHAUSTIVE` when tested at MVC child | `CURRENT_LEVEL` when tested at MVC child |
|---|---|---|
| Root context | Evicted | Retained |
| Current MVC child | Evicted | Evicted |
| MVC feature child | Evicted | Evicted |
| API child with same root | Evicted | Retained |

The primary difference lies in the common ancestor and sibling branches. `CURRENT_LEVEL` starts from the lowest context visible to the test and clears its descendants. `EXHAUSTIVE` finds the common ancestor of related hierarchies and clears the entire sub-hierarchy beneath that ancestor.

If a test has only one context, there is no parent-child tree to distinguish the two algorithms; `hierarchyMode` primarily matters when using `@ContextHierarchy`.

## 6. Determining the “Current Level” in a Test Class Hierarchy

Current level is not simply the class containing the test method. It is the `ApplicationContext` at the lowest level in the hierarchy visible to the current test.

Example:

```java
@ContextHierarchy({
    @ContextConfiguration(name = "root", classes = RootConfig.class),
    @ContextConfiguration(name = "web", classes = WebConfig.class),
    @ContextConfiguration(name = "feature", classes = FeatureConfig.class)
})
abstract class BaseFeatureTests {
}

class FeatureControllerTests extends BaseFeatureTests {

    @Test
    @DirtiesContext(hierarchyMode = DirtiesContext.HierarchyMode.CURRENT_LEVEL)
    void dirtiesFeatureContext() {
        // Test sees root -> web -> feature.
    }
}
```

The test sees three levels. `feature` is the lowest level, so `CURRENT_LEVEL` evicts the feature context and any contexts beneath feature. Root and web contexts remain cached.

If a test class only declares or inherits up to the `web` level, then `web` becomes the current level for that test. Therefore, the same `hierarchyMode = CURRENT_LEVEL` can have different scopes depending on the hierarchy visible to the test class.

When a test class inherits configuration from a base class, read the full `@ContextHierarchy` configuration in effect for the subclass. Do not determine the current level solely from annotations written directly on the subclass.

## 7. Combining hierarchyMode With methodMode and classMode

`hierarchyMode` only determines the scope of cache eviction. When eviction happens is still decided by `methodMode` or `classMode`.

### 7.1. Dirtying After a Test Method

```java
@Test
@DirtiesContext(
        methodMode = DirtiesContext.MethodMode.AFTER_METHOD,
        hierarchyMode = DirtiesContext.HierarchyMode.CURRENT_LEVEL)
void resetsChildContextAfterThisTest() {
    // Alters state inside the child context.
}
```

Once the current test finishes running, the child context and its descendants are evicted from the cache. Subsequent tests needing the same child configuration will create a new context; the parent can be reused.

### 7.2. Dirtying Before a Test Method

```java
@Test
@DirtiesContext(
        methodMode = DirtiesContext.MethodMode.BEFORE_METHOD,
        hierarchyMode = DirtiesContext.HierarchyMode.CURRENT_LEVEL)
void startsWithFreshChildContext() {
    // Test starts with a recreated child context.
}
```

This mode is useful when ensuring a context altered by an earlier test is evicted before the current method runs. It does not automatically clean databases or state outside the ApplicationContext.

### 7.3. Dirtying After Each Method in a Class

```java
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD,
        hierarchyMode = DirtiesContext.HierarchyMode.CURRENT_LEVEL)
class MutableChildContextTests {

    @Test
    void firstTest() {
        // ...
    }

    @Test
    void secondTest() {
        // ...
    }
}
```

After each method, Spring evicts the current level and its descendants. The next method needing that context will reinitialize the child context. This can be time-consuming if the class has many tests; only use it when every method genuinely dirties the context.

### 7.4. Dirtying After a Class

```java
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS,
        hierarchyMode = DirtiesContext.HierarchyMode.EXHAUSTIVE)
class SharedContextMutationTests {
    // Tests alter shared state within the hierarchy.
}
```

After the class finishes, Spring evicts contexts according to the exhaustive algorithm. Timing and scope configuration should accurately reflect where mutations happen and which other tests are affected.

## 8. Example of Two Test Hierarchies Sharing a Parent

Suppose an application has a root context containing services and repositories, while web and API test classes use separate child configurations.

```java
@Configuration
class RootConfig {
    @Bean
    SharedService sharedService() {
        return new SharedService();
    }
}

@Configuration
class MvcConfig {
    @Bean
    MvcController mvcController(SharedService service) {
        return new MvcController(service);
    }
}

@Configuration
class ApiConfig {
    @Bean
    ApiHandler apiHandler(SharedService service) {
        return new ApiHandler(service);
    }
}
```

Two test hierarchies can declare the same root configuration:

```java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(name = "root", classes = RootConfig.class),
    @ContextConfiguration(name = "mvc", classes = MvcConfig.class)
})
class MvcIntegrationTests {
}

@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(name = "root", classes = RootConfig.class),
    @ContextConfiguration(name = "api", classes = ApiConfig.class)
})
class ApiIntegrationTests {
}
```

When the root configuration is identical, TestContext can share the root context in the cache. If a test in `MvcIntegrationTests` only modifies a bean specific to the MVC child, `CURRENT_LEVEL` preserves the root and API child. If the test modifies `SharedService` or shared state in root, `EXHAUSTIVE` is safer because it evicts root and all child contexts in hierarchies sharing that ancestor.

The configuration classes in the example are illustrative. For Spring to recognize the hierarchy properly, context configurations must be declared with the appropriate parent-child relationship and have compatible metadata so the cache recognizes the shared root portion.

## 9. What hierarchyMode Does Not Do

`hierarchyMode` only controls evicting `ApplicationContext` instances from the cache and closing contexts within the selected scope. It does not replace cleanup mechanisms for resources outside the context lifecycle.

For example, the following operations need separate management:

- Deleting database records or rolling back transactions appropriately.
- Stopping containers, servers, or processes started by tests.
- Deleting temporary files and directories created by tests.
- Restoring system properties, mocked system environments, or static state.
- Resetting caches of external libraries or shared resources.

Closing an `ApplicationContext` can invoke bean destruction callbacks and release bean-managed resources if they are configured properly. However, you cannot assume every change outside the context is automatically undone.

`@DirtiesContext` is also not the default way to clean test data. If a test only alters database data within a properly managed transaction, rollback or fixture cleanup is usually more appropriate than closing and rebuilding the entire context.

## 10. Impact on Test Suite Speed and Stability

Every context evicted from the cache may have to be recreated on the next test. This process can include reading configuration, creating beans, initializing connection pools, starting mock servers, or connecting to integration resources.

`EXHAUSTIVE` has a broader scope, so it can cause tests in other branches to reinitialize contexts. That increases execution time, yet eliminates contexts depending on an ancestor that may have been altered.

`CURRENT_LEVEL` can preserve the parent and sibling branches, thereby reducing the number of contexts that must be recreated. In return, tests must ensure mutations are truly confined to the current level and its descendants. If a mutation reaches the parent while the parent stays cached, subsequent tests can observe stale or wrong state.

Do not pick a mode based on speed alone. First identify which context owns the mutated bean or configuration, then identify which contexts depend on it. Cache eviction scope must cover every context that could be affected.

## 11. Common Mistakes

**Thinking CURRENT_LEVEL only clears a single context.** The algorithm also clears all contexts in sub-hierarchies of the current level. If the child has nested child layers, those are evicted too.

**Thinking EXHAUSTIVE only clears the parent and current branch.** The exhaustive algorithm also includes other hierarchies sharing a common ancestor with the current test. A child context in a sibling branch can also be closed.

**Using CURRENT_LEVEL after mutating a bean in the parent.** The parent may remain in the cache and be used by subsequent child contexts. Use a sufficiently broad scope when the parent is affected.

**Confusing hierarchyMode with classMode or methodMode.** `hierarchyMode` decides the eviction scope; `classMode` and `methodMode` decide eviction timing.

**Ignoring contexts inherited from a base test class.** Current level is determined from the hierarchy visible to the current test, including inherited configuration.

**Using @DirtiesContext to clean the database.** Closing the context does not automatically roll back all transactions or delete committed data. Manage transactions and data separately.

**Putting @DirtiesContext on every test.** This forfeits cache benefits and can make the suite significantly slower. Only mark dirty when a test genuinely alters context state.

**Assuming sibling contexts are always independent.** Two children can share beans from a parent. If the parent is mutated, the sibling can also be affected even if the test does not directly call beans in the sibling.

## 12. Workflow for Choosing hierarchyMode

When a test in a context hierarchy needs `@DirtiesContext`, determine:

1. Which context levels in `@ContextHierarchy` does the current test see?
2. Which context is the lowest level visible to the test?
3. Does the mutated bean or state belong to the current level, a child context, or an ancestor?
4. Do other hierarchies share an ancestor context with the current test?
5. If the parent remains cached, will remaining child contexts still receive valid state?
6. If clearing exhaustively, will tests in other branches have to reinitialize contexts?
7. Must dirtying occur before a method, after a method, after each method, or after a class?
8. Are there resources outside ApplicationContext requiring separate cleanup?

The following practical rules can be used:

- Choose `CURRENT_LEVEL` when changes are confined to the lowest context visible to the test and its descendants; the parent and other branches remain valid.
- Choose `EXHAUSTIVE` when changes can affect a common ancestor or multiple hierarchies sharing that ancestor; this is also the default of `@DirtiesContext`.
- Choose `methodMode` or `classMode` separately according to when the context must be evicted.
- Use transactions, cleanup fixtures, or lifecycle callbacks for data and resources outside ApplicationContext.

## 13. References

- [Spring Framework Reference — @DirtiesContext](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dirtiescontext.html): describes how to mark a context dirty and examples of using `CURRENT_LEVEL` in a context hierarchy.
- [DirtiesContext.HierarchyMode Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/annotation/DirtiesContext.HierarchyMode.html): exact definition of cache eviction scope for `EXHAUSTIVE` and `CURRENT_LEVEL`.
- [Spring Framework Reference — Context Hierarchies](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/hierarchies.html): how to declare and use context hierarchies in tests.

Understanding the scope of `hierarchyMode` helps avoid two opposite problems: keeping a mutated parent context, or clearing too many contexts and forcing tests in unrelated branches to reinitialize. Identify the mutated context level, its descendants, and shared ancestors before choosing the algorithm; then the Spring TestContext cache will be cleaned to the exact required scope.
