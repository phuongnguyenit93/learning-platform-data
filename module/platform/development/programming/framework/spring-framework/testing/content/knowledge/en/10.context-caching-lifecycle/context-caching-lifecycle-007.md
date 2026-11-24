# @DirtiesContext When Tests Corrupt Shared State

The Spring TestContext Framework caches `ApplicationContext` instances so multiple tests with the same configuration can share an initialized context. This mechanism reduces test execution time, but it also means singleton beans and state residing in the context can be retained across multiple tests.

If a test alters context state in a way that subsequent tests cannot continue using safely, Spring provides the `@DirtiesContext` annotation. This annotation marks the context as no longer trustworthy, instructing Spring to remove the context from the cache and close it. When a later test needs the same configuration, Spring creates a new context.

## 1. Why Can Shared State Affect Tests?

Inside a Spring `ApplicationContext`, singleton beans are normally created once and shared across all consumers in that context. If a bean holds mutable state, one test can inadvertently leave state behind for a test running afterward.

For example, a bean storing a list of enabled features:

```java
@Component
public class FeatureRegistry {

    private final Set<String> enabledFeatures = new HashSet<>();

    public void enable(String feature) {
        enabledFeatures.add(feature);
    }

    public boolean isEnabled(String feature) {
        return enabledFeatures.contains(feature);
    }
}
```

If the Spring context is cached and two tests share this bean, the first test can add a feature. The second test then sees that feature even though it never prepared that state.

```text
Test A
  |
  | registry.enable("experimental")
  v
FeatureRegistry in ApplicationContext
  |
  | state remains
  v
Test B
  |
  | isEnabled("experimental") == true
  v
Result depends on Test A having run first
```

This is a form of state leakage between tests. Test B is no longer independent: its outcome depends on ordering or which other tests ran beforehand.

## 2. What Does @DirtiesContext Solve?

`@DirtiesContext` marks the associated `ApplicationContext` as dirty. The Spring TestContext Framework removes that context from the cache and closes it. The next time a test needs a context with the same configuration, Spring initializes a new context.

The annotation can be used on a test method:

```java
@SpringBootTest
class FeatureRegistryTest {

    @Autowired
    private FeatureRegistry featureRegistry;

    @Test
    @DirtiesContext
    void enablesTemporaryFeature() {
        featureRegistry.enable("experimental");

        assertTrue(featureRegistry.isEnabled("experimental"));
    }
}
```

At the method level, by default Spring marks the context dirty after the test method finishes. The test can mutate beans while running; afterward the context is evicted from the cache so tests needing this context do not continue receiving altered state.

The default mode can be written explicitly:

```java
@Test
@DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
void enablesTemporaryFeature() {
    // ...
}
```

The annotation can also be placed on a test class:

```java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class LegacyConfigurationTest {
    // Tests in the class
}
```

At the class level, by default Spring marks the context dirty after all test methods in the class have finished. This is useful when the entire class may alter shared state and only needs to evict the context after the class ends.

## 3. How Are Contexts Cached and Recreated?

The Spring TestContext Framework stores initialized contexts in a cache. Test configuration is used as the basis for determining whether a context can be reused. Test classes with equivalent configurations can receive the same cached context.

When `@DirtiesContext` is applied, Spring removes the relevant context from the cache and closes it. Subsequent uses will not retrieve the instance marked dirty.

```text
Test class A
     |
     v
Look up context in cache
     |
     v
ApplicationContext C1
     |
     v
Test A mutates shared state
     |
     v
@DirtiesContext marks C1 dirty
     |
     +----> Evict C1 from cache
     |
     +----> Close C1
                 |
                 v
Test class B needs same configuration
                 |
                 v
          C1 no longer in cache
                 |
                 v
       Create new ApplicationContext C2
```

The new context has beans reinitialized according to configuration. State held in bean instances of the old context is not carried over to the new context.

This does not mean every test creates a new context. Spring still reuses contexts across tests when the context has not been marked dirty and configuration permits sharing.

## 4. Method-Level Modes

When placing `@DirtiesContext` on a test method, the `methodMode` attribute determines when the context is marked dirty.

| MethodMode | Timing | Purpose |
|---|---|---|
| `BEFORE_METHOD` | Before the test method executes | The test needs to start with a fresh context after a previous context may have been altered |
| `AFTER_METHOD` | After the test method executes | The current test alters the context and needs the context evicted upon completion |

`AFTER_METHOD` is the default value at the method level.

Example:

```java
@SpringBootTest
class FeatureRegistryTest {

    @Autowired
    private FeatureRegistry featureRegistry;

    @Test
    @DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void enablesTemporaryFeature() {
        featureRegistry.enable("experimental");

        assertTrue(featureRegistry.isEnabled("experimental"));
    }

    @Test
    void startsWithoutExperimentalFeature() {
        assertFalse(featureRegistry.isEnabled("experimental"));
    }
}
```

After the first method, the context is removed from the cache. When the next method needs a context, Spring creates a new context and injects beans from the new context into the corresponding test instance. Thus, the registry starts in its initial state.

Use `BEFORE_METHOD` when the current test itself needs protection from a context that may have been altered earlier. Use `AFTER_METHOD` when the current test is the one dirtying the context and must ensure subsequent tests do not reuse it.

## 5. Class-Level Modes

When placing the annotation on a class, the `classMode` attribute determines when Spring marks the context dirty.

| ClassMode | Timing | Scenario |
|---|---|---|
| `BEFORE_CLASS` | Before tests in the class begin | The class needs a fresh context from the very start |
| `AFTER_CLASS` | After all test methods in the class finish | The entire class may alter the context; this is the default |
| `BEFORE_EACH_TEST_METHOD` | Before each test method | Each method needs to run with a refreshed context |
| `AFTER_EACH_TEST_METHOD` | After each test method | Each method may dirty the context and needs it evicted immediately after running |

Example refreshing the context after each method:

```java
@SpringBootTest
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD
)
class FeatureRegistryIsolationTest {

    @Autowired
    private FeatureRegistry featureRegistry;

    @Test
    void enablesFeatureA() {
        featureRegistry.enable("feature-a");

        assertTrue(featureRegistry.isEnabled("feature-a"));
    }

    @Test
    void enablesFeatureB() {
        featureRegistry.enable("feature-b");

        assertTrue(featureRegistry.isEnabled("feature-b"));
    }
}
```

After each method, the context is removed from the cache. Each subsequent test method will need a new context when Spring prepares to execute it. This approach prevents methods from sharing bean state altered by a preceding method.

If cleaning once after the class finishes is sufficient, using `AFTER_CLASS` is less costly. If only one method alters the context, placing the annotation on that method usually expresses the scope more accurately.

## 6. Distinguishing Method Mode and Class Mode

Both attributes serve a similar purpose but apply at two different scopes:

- `methodMode` is used when `@DirtiesContext` is placed on a method.
- `classMode` is used when `@DirtiesContext` is placed on a class.

There is no need to declare both in the same annotation. Choose the annotation placement scope according to where the mutation originates.

For example, if only one method alters a singleton bean, you can write:

```java
@Test
@DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
void changesSharedRegistry() {
    // ...
}
```

If every test in the class has the potential to alter the context, you can place it on the class:

```java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ContextMutationTest {
    // ...
}
```

Do not place `@DirtiesContext` on a base test class by default if only some subclasses actually alter the context. Annotations are inherited under Spring's annotation rules, so the scope of impact can be broader than intended. Clearly identify which test classes need to dirty the context.

## 7. Context Hierarchy and hierarchyMode

Some test applications use multiple layers of `ApplicationContext` with parent–child relationships, typically declared with `@ContextHierarchy`. In that case, marking a context dirty requires specifying which contexts in the hierarchy will be removed from the cache.

`@DirtiesContext` provides the `hierarchyMode` attribute:

| HierarchyMode | Scope |
|---|---|
| `EXHAUSTIVE` | Default mode; removes the current context and related contexts at parent levels in the hierarchy |
| `CURRENT_LEVEL` | Only removes the context at the current level |

Example:

```java
@ContextHierarchy({
        @ContextConfiguration(classes = RootConfig.class),
        @ContextConfiguration(classes = WebConfig.class)
})
@SpringBootTest
class WebContextTest {

    @Test
    @DirtiesContext(
            methodMode = DirtiesContext.MethodMode.AFTER_METHOD,
            hierarchyMode = DirtiesContext.HierarchyMode.CURRENT_LEVEL
    )
    void changesWebContext() {
        // Verify behavior belonging to the web-level context
    }
}
```

The example illustrates choosing the scope for a context hierarchy. Actual configuration names and bootstrapping depend on the test type used by the project.

With `EXHAUSTIVE`, Spring handles context eviction across the full scope of the hierarchy from the current level up to parent levels. This may require other child contexts depending on the parent context to be recreated as well. With `CURRENT_LEVEL`, Spring only removes the context at the current level and keeps parent contexts in the cache.

Only choose `CURRENT_LEVEL` when the parent context remains valid and the mutation only affects the context at the current level. If mutated state resides in the parent context or can affect other child contexts, the default `EXHAUSTIVE` scope is safer.

If a test only uses a single standard `ApplicationContext`, there is no need to worry about this attribute; leaving the default is sufficient.

## 8. @DirtiesContext Does Not Replace Transaction Rollback

An important point is that `@DirtiesContext` manages the lifecycle of the Spring `ApplicationContext`. It is not a mechanism for rolling back all data or state outside the application.

For example, if a test writes a record to a real database and then marks the context dirty, closing the context does not automatically delete that record from the database. The database is a resource independent of bean lifecycles in the context.

For tests using transactions managed by Spring Test, you can use `@Transactional` so database changes are rolled back after the test by default:

```java
@SpringBootTest
@Transactional
class OrderRepositoryTest {

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void savesOrderInsideTestTransaction() {
        Order order = new Order("ORDER-42");

        orderRepository.save(order);

        assertTrue(orderRepository.findById("ORDER-42").isPresent());
    }
}
```

In a standard transactional test setup, Spring Test rolls back the transaction after the test method unless configured to commit or complete the transaction otherwise. This mechanism serves data isolation, not replacing the context cache.

We can distinguish:

| State to clean up | Appropriate mechanism |
|---|---|
| Mutable state in a singleton bean of the context | Reset the bean or use `@DirtiesContext` if the context needs recreating |
| Database changes inside a test transaction | Transaction rollback |
| Committed database data or data outside test transactions | SQL cleanup, repository cleanup, or database reset strategy |
| Files, messages, external caches, or HTTP services | Dedicated cleanup mechanism for that resource |
| Static fields or global JVM state | Restore state via test code or a dedicated management mechanism |

When a test modifies multiple types of resources, a separate cleanup strategy is needed for each type. Marking the context dirty only resolves the portion of state belonging to the context.

## 9. When Should @DirtiesContext Be Used?

Consider `@DirtiesContext` when a test genuinely alters context state and it cannot be reliably restored.

Typical scenarios:

- A test dynamically registers or removes beans in the context.
- A test alters internal context configuration or state.
- A test mutates a shared singleton bean with no proper way to reset it.
- A test alters the state of a Spring component such that subsequent tests cannot continue using it.
- A test verifies a special configuration that leaves the context no longer representative of the original configuration.

For example, a test may mutate a shared registry:

```java
@SpringBootTest
class FeatureRegistryMutationTest {

    @Autowired
    private FeatureRegistry featureRegistry;

    @Test
    @DirtiesContext
    void registersTemporaryFeature() {
        featureRegistry.enable("temporary-feature");

        assertTrue(featureRegistry.isEnabled("temporary-feature"));
    }
}
```

After this method, Spring removes the context from the cache. Other tests using the same configuration will be provided with a new context when needed.

If a bean has a safe reset method and tests can invoke it in `@AfterEach`, resetting directly is usually faster than closing and recreating the entire context. `@DirtiesContext` is appropriate when altered state makes the context untrustworthy, or restoring individual components is too complex and error-prone.

## 10. When Should @DirtiesContext Not Be Used?

Do not use this annotation simply because you want every test to start with a fresh context. Recreating a context can be time-consuming because Spring must load configuration, create beans, connect resources, and perform related initialization steps.

Cases that typically do not need `@DirtiesContext`:

**Local fixtures are mutated.** If a test only mutates an object created inside the method, that object is not shared with other tests. There is no need to evict the entire context.

**Mocks are reset or recreated at the right scope.** If a test uses per-instance mocks or has an explicit reset mechanism, there is no need to mark the context dirty just because a mock received invocations.

**The database needs rollback.** Use test transactions or data cleanup. Closing the context does not mean deleting written data.

**Beans can be restored safely.** If bean state can be reset with an explicit operation in `@AfterEach`, direct reset is usually less expensive.

**Merely wanting to avoid execution-order dependencies.** Make fixtures and test state independent first. Using `@DirtiesContext` on every class can mask a test design that shares state unnecessarily.

## 11. Impact on Test Suite Performance

The Spring context is often one of the most time-consuming parts of integration tests. The cache helps avoid recreating contexts when multiple test classes share the same configuration.

When using `@DirtiesContext`, the context is evicted from the cache. If multiple test classes mark the same context dirty, Spring must create a new context repeatedly. Bean startup, database connections, client initialization, and configuration steps may repeat.

Example:

```text
Without @DirtiesContext:
  Test A ----+
  Test B ----+----> Share ApplicationContext C1
  Test C ----+

With @DirtiesContext after each class:
  Test A ---------> C1 ----> close
  Test B ---------> C2 ----> close
  Test C ---------> C3 ----> close
```

The diagram illustrates tests with equivalent configurations. When the context is not marked dirty, Spring can reuse C1. When each class dirties the context, subsequent runs must create new contexts.

If a test suite has many `@DirtiesContext` annotations, execution time can increase significantly. Limit the annotation to the exact test method or class that mutates the context, and choose the mode matching when the context must be evicted.

Do not remove `@DirtiesContext` just to speed up the suite if a test genuinely corrupts the context. Instead, check whether bean state can be reset or mutable resources can be separated from the shared context.

## 12. Combining With Test Inheritance

When test classes inherit from a base class with Spring configuration, pay attention to how `@DirtiesContext` can affect test classes sharing the configuration or context hierarchy.

Example:

```java
@SpringBootTest
abstract class BaseIntegrationTest {

    @Autowired
    protected FeatureRegistry featureRegistry;
}

class FeatureReadTest extends BaseIntegrationTest {

    @Test
    void readsDefaultFeature() {
        assertFalse(featureRegistry.isEnabled("experimental"));
    }
}

@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class FeatureMutationTest extends BaseIntegrationTest {

    @Test
    void enablesFeature() {
        featureRegistry.enable("experimental");

        assertTrue(featureRegistry.isEnabled("experimental"));
    }
}
```

The test class that mutates state is marked dirty upon completion. Other test classes using the same configuration will need a valid context when running. Spring can create a new context if the previous one was removed from the cache.

Place the annotation on the class that actually mutates the context. If placed on the base class, all subclasses may be affected and increase context initialization counts unexpectedly.

## 13. Common Mistakes When Using @DirtiesContext

| Symptom | Possible cause | Solution |
|---|---|---|
| Subsequent test sees bean state from a previous test | Context is reused and bean holds mutable state | Reset the bean or mark the context dirty on the mutating test |
| Test suite runs slowly after adding the annotation | Context is evicted from the cache too frequently | Narrow the annotation scope and choose the appropriate mode |
| Database data still exists after the context is closed | Context reset does not roll back committed database changes | Use transaction rollback or data cleanup |
| Test still sees old static state | Static fields reside outside the ApplicationContext | Restore static state separately |
| Many test classes must reinitialize contexts | Annotation placed on base class or broad context hierarchy | Check annotation placement and hierarchyMode |
| Test does not start with a new context as expected | Wrong methodMode or classMode chosen | Precisely determine when the context must be evicted |
| Parent/child beans in context hierarchy reinitialized unexpectedly | Default EXHAUSTIVE scope affects parent context | Consider CURRENT_LEVEL if only the current context is altered |
| Tests still depend on order despite using the annotation | State resides in external resources or lacks other cleanup mechanisms | Build dedicated cleanup for each resource |

When diagnosing, identify where the altered state resides: in a bean inside the context, in the database, in a static field, or in an external service. Then choose a cleanup mechanism matching that state's lifecycle.

## 14. How to Choose the Mode in Practice

You can choose the mode by answering two questions: which test scope dirties the context, and when must the context be evicted?

| Scenario | Usually appropriate choice |
|---|---|
| One method dirties the context after running | `@DirtiesContext(methodMode = AFTER_METHOD)` |
| One method needs a fresh context before running | `@DirtiesContext(methodMode = BEFORE_METHOD)` |
| Entire class dirties the context and only needs eviction after the class | `@DirtiesContext(classMode = AFTER_CLASS)` |
| Each method in the class needs a fresh context after running | `@DirtiesContext(classMode = AFTER_EACH_TEST_METHOD)` |
| Each method must start after a context eviction | `@DirtiesContext(classMode = BEFORE_EACH_TEST_METHOD)` |
| Class needs to evict the old context before starting | `@DirtiesContext(classMode = BEFORE_CLASS)` |
| Only one context in a hierarchy is altered | Consider `hierarchyMode = CURRENT_LEVEL` |
| Parent context may also be affected | Use default `hierarchyMode = EXHAUSTIVE` |

For example, if a single method adds a bean or mutates singleton state that cannot be reset, placing the annotation on the method is usually sufficient. If the entire class is a test group dedicated to manipulating configuration and the context must be evicted after each method, class-level `AFTER_EACH_TEST_METHOD` expresses intent more clearly.

## 15. Investigation Workflow When Tests Corrupt Shared State

When a test only fails if run after another test, trace shared state before adding `@DirtiesContext`:

1. **Reproduce the issue:** run the test individually and with the test suite to determine whether there is an order dependency.
2. **Identify whether the context is shared:** check whether test classes have equivalent Spring configuration and can use the same cache entry.
3. **Find mutable beans or resources:** inspect which singleton, static state, cache, registry, or listener was modified.
4. **Determine the scope of mutation:** only one method, an entire class, or a context hierarchy.
5. **Choose a restoration approach:** reset the bean if it can be restored safely; use `@DirtiesContext` if the context is no longer trustworthy.
6. **Choose timing:** method mode or class mode must reflect when the context needs to be evicted.
7. **Verify resources outside the context:** confirm databases, files, messages, and external services have dedicated cleanup.
8. **Re-run in a different order:** ensure results no longer depend on previously run tests.

A reliable test should prepare the state it needs and leave no side effects beyond its expected scope. `@DirtiesContext` is a tool to protect subsequent tests after a test has altered the context, while helping Spring evict and recreate the context when necessary. Using the right scope and timing preserves test independence without sacrificing the benefits of context caching.

