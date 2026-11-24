# When to Close the Context Before or After a Class or Method

The Spring TestContext Framework can cache the ApplicationContext so multiple tests share a single initialized context. This makes tests run faster, but it also means singleton bean state can persist after a test method or test class. When a test alters the context to the point where other tests cannot continue using it safely, Spring provides the **@DirtiesContext** annotation to mark the context for eviction from the cache and closure.

@DirtiesContext allows choosing when to process the context at two levels:

- **Per test method:** close the context before or after a specific method.
- **Per test class:** close the context before the class, after the class, or before/after each test method in the class.

Choosing the right timing determines which tests receive a fresh context, which tests can reuse a cached context, and when Spring triggers bean shutdown. This lesson focuses on the BEFORE_METHOD, AFTER_METHOD, BEFORE_CLASS, AFTER_CLASS, BEFORE_EACH_TEST_METHOD, and AFTER_EACH_TEST_METHOD modes.

## 1. Why Do You Need to Choose When to Close ApplicationContext?

Spring TestContext typically reuses contexts across tests with equivalent configurations. For example, two test classes both using @SpringBootTest with the same configuration can receive the same cached context within a JVM.

This is useful because context initialization can take time: Spring must read configuration, create beans, inject dependencies, run initialization callbacks, and set up infrastructure components. If every test method created a new context, the suite could slow down significantly.

However, a shared context also holds runtime state. A test may:

- Mutate mutable fields of a singleton bean.
- Alter configuration or component registrations inside the context in an unrecoverable way.
- Replace or mutate a shared bean.
- Close a resource managed by a bean.
- Leave the context no longer representative of the initial state expected by other tests.

For example, a bean storing temporary state in memory:

~~~java
@Component
class FeatureRegistry {

    private final Map<String, Boolean> features = new HashMap<>();

    void enable(String name) {
        features.put(name, true);
    }

    boolean isEnabled(String name) {
        return features.getOrDefault(name, false);
    }
}
~~~

If one test calls enable("checkout"), a subsequent test using the same bean may observe that state. When this state cannot be reliably reset, you can mark the context dirty so Spring evicts it from the cache and creates a new context for the next use.

Not every data change requires @DirtiesContext. If a test merely inserts a record in the database and can roll back the transaction or clean up data explicitly, use the corresponding data isolation mechanism. @DirtiesContext is intended for scenarios where the Spring context itself must be replaced.

## 2. How Does @DirtiesContext Work?

The @DirtiesContext annotation informs Spring TestContext that the context used by a test has been modified and should no longer be reused from the cache.

When a context is marked dirty, Spring removes it from the cache and closes the context. Closing triggers bean lifecycle callbacks, such as @PreDestroy, DisposableBean.destroy(), or configured destroy methods. When a subsequent test needs the same configuration, Spring recreates the context.

The lifecycle can be visualized as follows:

~~~text
Test needs ApplicationContext
          |
          v
   Look up in context cache
          |
     +----+----+
     |         |
    Yes        No
     |         |
     v         v
Use cached   Create new context
context      and put into cache
     |         |
     +----+----+
          |
          v
       Run test
          |
          v
   @DirtiesContext?
          |
     +----+----+
     |         |
     No       Yes
     |         |
     v         v
Keep context  Mark dirty,
in cache      evict from cache,
              close context
~~~

Closing the context does not mean the entire JVM restarts. Spring only processes the corresponding ApplicationContext. Static fields, manually managed singletons outside Spring, committed database data, and remote service state are not automatically reset.

## 3. Closing the Context Per Test Method

When placing @DirtiesContext on a test method, the methodMode attribute determines when the context is marked dirty.

Two primary modes:

| MethodMode | Timing | Meaning |
|---|---|---|
| BEFORE_METHOD | Before the method runs | Evict the existing context from the cache so the method starts with a fresh context |
| AFTER_METHOD | After the method finishes | Close the context the method just used so the next test must create or retrieve another context |

The default value of methodMode is AFTER_METHOD.

### 3.1. BEFORE_METHOD: Closing the Context Before the Method

Use BEFORE_METHOD when the test needs a fresh context from the start because the context may have been altered by a previously run test or by setup executed before the method.

~~~java
@SpringBootTest
class FeatureRegistryTest {

    @Autowired
    private FeatureRegistry featureRegistry;

    @Test
    @DirtiesContext(
        methodMode = DirtiesContext.MethodMode.BEFORE_METHOD
    )
    void startsWithFreshFeatureRegistry() {
        assertFalse(featureRegistry.isEnabled("checkout"));
    }
}
~~~

The sequence at the test method level is:

1. Spring processes the BEFORE_METHOD mode and removes the old context from the cache if that context was in use.
2. Spring prepares a new context for the test.
3. @BeforeEach callbacks execute.
4. The test method runs.
5. @AfterEach callbacks execute.
6. The new context may remain in the cache if no other closing mode applies.

BEFORE_METHOD guarantees the method receives a fresh context at its start. It does not automatically close the new context after the method finishes. If the method also dirties the context and needs it closed immediately after running, consider the AFTER_METHOD mode for that scenario or design the test class with an appropriate mode.

Another case is when a test needs to verify that a bean is recreated after another test altered the context. Attaching BEFORE_METHOD to the method needing fresh state clearly expresses that boundary.

### 3.2. AFTER_METHOD: Closing the Context After the Method

This is the default mode when placing @DirtiesContext on a method. Use it when the method directly modifies context state and subsequent tests should not reuse that context.

~~~java
@SpringBootTest
class FeatureRegistryMutationTest {

    @Autowired
    private FeatureRegistry featureRegistry;

    @Test
    @DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void changesSharedFeatureRegistry() {
        featureRegistry.enable("checkout");
        assertTrue(featureRegistry.isEnabled("checkout"));
    }
}
~~~

It can be written more concisely because AFTER_METHOD is the default:

~~~java
@Test
@DirtiesContext
void changesApplicationContextState() {
    // Perform changes that make the context unsafe to reuse.
}
~~~

Sequence:

1. Spring prepares or retrieves the context from the cache.
2. @BeforeEach callbacks run.
3. The test method runs.
4. @AfterEach callbacks run.
5. Spring runs the post-test-method listener, marks the context dirty, and closes it.
6. The next test needing the corresponding configuration will have to create a new context.

Placing @DirtiesContext on a method limits the impact to the test that actually dirties the context. Other methods in the same class can continue using the cached context if no other annotation or mode requests closure.

### 3.3. Comparing the Two Method Modes

Suppose a test class has three methods A, B, and C, all using the same context configuration:

~~~text
@DirtiesContext(BEFORE_METHOD) on B:

A: uses context X
B: evicts X -> creates and uses context Y
C: can reuse Y

@DirtiesContext(AFTER_METHOD) on B:

A: uses context X
B: uses X -> closes X after B
C: creates and uses context Y
~~~

This is the view at the cache level. If an equivalent context was already used by another test class, the dirty operation also affects subsequent uses of that context within the same JVM.

Choose BEFORE_METHOD when the method itself needs protection from leftover state from earlier tests. Choose AFTER_METHOD when the method creates state that leaves the context unusable after it finishes.

## 4. Closing the Context Per Test Class

When placing @DirtiesContext on a class, the classMode attribute determines when context handling occurs during the entire class's lifecycle.

Spring provides four modes:

| ClassMode | Timing | Scope |
|---|---|---|
| BEFORE_CLASS | Before the test class runs | Close the context before all test methods of the class |
| AFTER_CLASS | After the test class finishes | Close the context after all test methods of the class |
| BEFORE_EACH_TEST_METHOD | Before each test method | Refresh the context before every method in the class |
| AFTER_EACH_TEST_METHOD | After each test method | Close the context after every method in the class |

The default value of classMode is AFTER_CLASS.

### 4.1. BEFORE_CLASS: Cleaning Before the Class Starts

Choose BEFORE_CLASS when the class needs to start with a fresh context, for example because another test class shared the configuration and may have altered the context earlier.

~~~java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.BEFORE_CLASS)
class IsolatedApplicationContextTest {

    @Autowired
    private FeatureRegistry featureRegistry;

    @Test
    void startsWithExpectedRegistryState() {
        assertFalse(featureRegistry.isEnabled("checkout"));
    }
}
~~~

Spring processes this mode before the test class's initialization callbacks. After evicting the old context from the cache, a new context is created when tests need it.

BEFORE_CLASS takes effect at the class boundary. If methods inside the class alter the context, that context can still be shared among methods of the class itself until another mode marks it dirty. If you want each method to receive a fresh context, use BEFORE_EACH_TEST_METHOD.

### 4.2. AFTER_CLASS: Closing After the Entire Class Completes

AFTER_CLASS is the default mode when placing @DirtiesContext at the class level:

~~~java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class LegacyConfigurationMutationTest {

    @Autowired
    private FeatureRegistry featureRegistry;

    @Test
    void changesFeatureState() {
        featureRegistry.enable("legacy-mode");
    }

    @Test
    void checksAnotherFeature() {
        // Can share the same context within the class scope.
    }
}
~~~

After all test methods and callbacks finish, Spring marks the context dirty and closes it. Subsequent test classes cannot retrieve that context from the cache.

It can be shortened:

~~~java
@SpringBootTest
@DirtiesContext
class ContextMutationTest {
    // ...
}
~~~

Placing the annotation at the class level means the entire class takes responsibility for needing the context closed after the class finishes. This is an appropriate choice when multiple methods in the class share a context whose state is modified during testing.

### 4.3. BEFORE_EACH_TEST_METHOD: Fresh Context Before Each Method

Choose this mode when test methods need isolation with a fresh context before starting:

~~~java
@SpringBootTest
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.BEFORE_EACH_TEST_METHOD
)
class IndependentContextTests {

    @Autowired
    private FeatureRegistry featureRegistry;

    @Test
    void firstScenario() {
        assertFalse(featureRegistry.isEnabled("checkout"));
        featureRegistry.enable("checkout");
    }

    @Test
    void secondScenario() {
        assertFalse(featureRegistry.isEnabled("checkout"));
    }
}
~~~

Before each test method, Spring evicts the current context from the cache. When the method needs the context, Spring creates a new one. Thus, singleton state is recreated for each method.

This mode can be helpful when multiple methods modify singleton beans and manual state reset is unreliable. In return, the context may have to initialize many times, slowing down the suite.

### 4.4. AFTER_EACH_TEST_METHOD: Closing After Each Method

This mode marks the context dirty after each test method:

~~~java
@SpringBootTest
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD
)
class ContextMutationPerTestTests {

    @Autowired
    private FeatureRegistry featureRegistry;

    @Test
    void enablesCheckout() {
        featureRegistry.enable("checkout");
        assertTrue(featureRegistry.isEnabled("checkout"));
    }

    @Test
    void enablesSearch() {
        featureRegistry.enable("search");
        assertTrue(featureRegistry.isEnabled("search"));
    }
}
~~~

After each method, Spring closes the context that the method just used. The next method will need a new context when running.

### 4.5. Distinguishing the Two Per-Method Modes at the Class Level

BEFORE_EACH_TEST_METHOD and AFTER_EACH_TEST_METHOD both aim to run each method in its own context. The difference lies at the start and end boundaries:

~~~text
BEFORE_EACH_TEST_METHOD

Before A: evict old context -> create context A
Run A
Before B: evict context A -> create context B
Run B
Before C: evict context B -> create context C
Run C
Context C may remain in cache after the class

AFTER_EACH_TEST_METHOD

Create or retrieve context A
Run A -> close context A
Create or retrieve context B
Run B -> close context B
Create or retrieve context C
Run C -> close context C
~~~

In BEFORE mode, a context may remain retained after the last method because there is no corresponding AFTER step. In AFTER mode, the last method's context is also closed after the method finishes. This can affect another test class using the same configuration immediately afterward.

## 5. Quick Selection Table by Scope and Timing

The two attributes methodMode and classMode have different scopes of application:

| Where is the annotation placed? | Attribute | Mode | Result |
|---|---|---|---|
| Test method | methodMode | BEFORE_METHOD | Fresh context before the annotated method |
| Test method | methodMode | AFTER_METHOD | Context closed after the annotated method |
| Test class | classMode | BEFORE_CLASS | Context refreshed before the class starts |
| Test class | classMode | AFTER_CLASS | Context closed after the class finishes |
| Test class | classMode | BEFORE_EACH_TEST_METHOD | Fresh context before each method in the class |
| Test class | classMode | AFTER_EACH_TEST_METHOD | Context closed after each method in the class |

Example:

~~~java
// Method-level: choose timing via methodMode.
@Test
@DirtiesContext(methodMode = DirtiesContext.MethodMode.BEFORE_METHOD)
void needsFreshContext() {
}

// Class-level: choose timing via classMode.
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ContextChangingTests {
}
~~~

Do not use methodMode to describe a class-level mode or classMode to describe a single method. Choosing the attribute matching the annotation's placement clarifies intent and avoids scope confusion.

## 6. Ordering With JUnit Jupiter Callbacks

When Spring processes @DirtiesContext relates to JUnit's lifecycle callbacks. With JUnit Jupiter integrated via SpringExtension, the typical order for a test method is:

~~~text
Spring beforeTestClass
    |
    +-- BEFORE_CLASS if configured
    |
JUnit @BeforeAll
    |
    +-- BEFORE_EACH_TEST_METHOD if configured on class
    |
Spring beforeTestMethod
    |
    +-- BEFORE_METHOD if configured on method
    |
JUnit @BeforeEach
    |
JUnit @Test
    |
JUnit @AfterEach
    |
Spring afterTestMethod
    |
    +-- AFTER_METHOD if configured on method
    +-- AFTER_EACH_TEST_METHOD if configured on class
    |
JUnit @AfterAll
    |
Spring afterTestClass
    |
    +-- AFTER_CLASS if configured
~~~

This has practical implications:

- With BEFORE_METHOD, the context is refreshed before @BeforeEach, so the test method's setup receives beans from the fresh context.
- With AFTER_METHOD, the context is processed after @AfterEach, so the test's cleanup callbacks can still use beans from the context that just ran.
- With BEFORE_CLASS, the context is processed at the boundary before the class's initialization callbacks.
- With AFTER_CLASS, the context is processed after @AfterAll callbacks have finished.

Spring callbacks are executed through TestExecutionListener. If using JUnit 4 or TestNG, the integration order can be expressed through the corresponding framework's lifecycle; the meaning of Spring's modes remains before or after the method/class boundary.

## 7. Example Tracking a Mutated Bean

Suppose an application has a singleton bean holding runtime configuration state. One test mutates the state and needs Spring to create a fresh bean for the next test.

~~~java
@Component
class RuntimeSwitch {

    private boolean enabled;

    boolean isEnabled() {
        return enabled;
    }

    void enable() {
        enabled = true;
    }
}
~~~

The test can use AFTER_METHOD:

~~~java
@SpringJUnitConfig(RuntimeSwitchConfig.class)
class RuntimeSwitchTest {

    @Autowired
    private RuntimeSwitch runtimeSwitch;

    @Test
    @DirtiesContext
    void changesRuntimeSwitch() {
        runtimeSwitch.enable();
        assertTrue(runtimeSwitch.isEnabled());
    }

    @Test
    void startsWithDefaultSwitchState() {
        assertFalse(runtimeSwitch.isEnabled());
    }
}
~~~

The first test marks the context dirty after running. When the second method needs a context with the same configuration, Spring creates a new context and the RuntimeSwitch bean is reinitialized.

Test method order is not guaranteed based solely on source appearance order. The two methods above remain independent: if the second method runs first, it receives the default state; if it runs after the first method, the context has been evicted from the cache and recreated.

If only one method needs a fresh context before running, you can use BEFORE_METHOD on that method. If every method in the class needs its own context, class-level BEFORE_EACH_TEST_METHOD or AFTER_EACH_TEST_METHOD can express the policy more clearly.

## 8. @DirtiesContext and Test Class Inheritance

Spring TestContext supports test configuration inherited from a superclass. When @DirtiesContext is placed on a superclass, subclass test classes can be affected according to annotation inheritance policies and JUnit/Spring test configuration.

Example:

~~~java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
abstract class BaseContextMutationTest {
}

class PaymentFlowTest extends BaseContextMutationTest {

    @Test
    void changesPaymentConfiguration() {
        // ...
    }
}
~~~

A base class can group a common policy for a test group. However, if only one subclass test class dirties the context, placing the annotation on that exact subclass limits the impact better.

When inheriting test classes, consider:

- Whether the annotation on the superclass is inherited under its annotation policy.
- Whether the subclass adds configuration that changes the context cache key.
- Whether the dirty mode on the superclass causes the context to close after each subclass.
- Whether subclasses genuinely need the same lifecycle policy.

Do not use a large base test class just to group annotations if subclasses have different context lifecycles. Policies should be placed at the level closest to the group of tests that genuinely share that requirement.

## 9. Context Hierarchy and hierarchyMode

Some applications test multiple levels of ApplicationContext, such as a parent context holding shared services and a child context holding web components. In this situation, @DirtiesContext has the hierarchyMode attribute to control the scope of context eviction from the cache.

The two options are:

- EXHAUSTIVE (default): uses an algorithm to evict related contexts in the hierarchy to avoid reusing part of a context tree that is no longer valid.
- CURRENT_LEVEL: limits the dirty operation to the current context level in the hierarchy.

~~~java
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS,
    hierarchyMode = DirtiesContext.HierarchyMode.CURRENT_LEVEL
)
class WebChildContextTest {
    // ...
}
~~~

You only need to care about hierarchyMode when tests actually use @ContextHierarchy or have parent/child contexts. For applications with a single context, keeping the default is usually enough. Choosing too broad a scope can force many contexts to reinitialize; choosing too narrow a scope can retain a parent or child context no longer matching test state.

## 10. Distinguishing Closing the Context From Rolling Back Data

@DirtiesContext manages the Spring ApplicationContext lifecycle. It does not replace transaction rollback and does not delete data in all external systems.

| Change during test | Usually appropriate mechanism |
|---|---|
| Singleton bean has state mutated that cannot be safely reset | @DirtiesContext |
| Database records created inside a test transaction | Transaction rollback |
| Temporary files created during test | Clean up files in lifecycle cleanup |
| Data committed to a shared database | Delete data via fixtures/cleanup or separate database |
| Messages sent to a broker | Test queues/topics and appropriate cleanup |
| Stateful external service | Resettable fake/mock or test service environment |

Example of a transactional repository test:

~~~java
@DataJpaTest
class ProductRepositoryTest {

    @Autowired
    private ProductRepository repository;

    @Test
    void savesProduct() {
        Product product = repository.save(new Product("Keyboard"));
        repository.flush();

        assertTrue(repository.findById(product.getId()).isPresent());
    }
}
~~~

@DataJpaTest typically runs inside a transaction that is rolled back after the test. In this case, there is no need to mark the context dirty merely because the test saved an entity. If the test alters a singleton bean or corrupts context configuration, that is a matter for @DirtiesContext.

## 11. Cost and Impact on the Context Cache

Closing a context forces the next test needing the corresponding configuration to initialize a new context. For a large application, this can take several seconds or longer depending on the number of beans, database connections, servers, and initialized resources.

If a class has many methods and uses BEFORE_EACH_TEST_METHOD or AFTER_EACH_TEST_METHOD, the context can be recreated many times. If multiple classes mark an equivalent context dirty, later classes may also lose the chance to reuse the cache.

Several consequences to account for:

- Suite execution time rises when many contexts are evicted.
- Beans with initialization or shutdown callbacks run repeatedly.
- Connection pools, embedded servers, or context-bound resources are created/closed along that lifecycle.
- Tests may expose repeated initialization errors masked by a long-lived shared context.
- If a context fails to close cleanly due to held resources, cleanup errors may appear after the test.

Do not use @DirtiesContext as a default reset mechanism for every test. If a bean has mutable state, consider designing a test-focused reset API, creating new instances in the needed scope, using fakes, or restoring state in @AfterEach. Use dirty context when the context itself needs to be replaced.

## 12. Common Mistakes When Choosing a Mode

### 12.1. Using AFTER_CLASS While Expecting Each Method to Have a Fresh Context

AFTER_CLASS only closes the context after the entire test class completes. Methods within the class can share one context. If each method needs a fresh context, choose BEFORE_EACH_TEST_METHOD or AFTER_EACH_TEST_METHOD.

### 12.2. Using BEFORE_CLASS While Expecting the Context to Close After the Class

BEFORE_CLASS cleans at the start of the class. The context created for the class can still remain in the cache after the class finishes. To close after the class, use AFTER_CLASS.

### 12.3. Putting BEFORE_METHOD on a Method That Dirties the Context After Running

BEFORE_METHOD only handles the context before the method. If the method itself alters the context and needs it evicted after running, choose AFTER_METHOD or an appropriate class-level policy.

### 12.4. Thinking @DirtiesContext Resets the Database

A context may contain a DataSource and connection pool, yet closing the context does not automatically roll back committed transactions or delete data written by tests to a shared database. Use transactions, separate databases, or data cleanup at the appropriate scope.

### 12.5. Using Dirty Context to Mask Shared State Bugs

If multiple tests constantly need to close the context because a bean holds state, the bean or fixture design may be inappropriate. Check whether state can be reset via an explicit API or moved to a narrower-scoped object.

### 12.6. Closing the Context Too Early While Cleanup Callbacks Still Need Beans

With AFTER_METHOD, Spring processes it after @AfterEach callbacks. If cleanup is placed elsewhere or uses custom listeners, check listener ordering. Do not hold references to beans from a closed context and use them in a subsequent test.

### 12.7. Placing the Annotation on a Base Class With the Wrong Scope

A class-level annotation on a superclass can affect multiple subclasses. If only one class alters the context, place the policy on that class to avoid creating new contexts for tests that do not need them.

### 12.8. Overusing BEFORE_EACH_TEST_METHOD and AFTER_EACH_TEST_METHOD

Both modes can reinitialize the context for every single method. When the suite is slow, review which tests genuinely dirty the context and switch to method-level annotations if only a few methods need it.

## 13. Diagnosing When Contexts Are Closed or Reinitialized

When logs indicate Spring is closing or creating new contexts, identify which test marked it dirty and which mode is in effect.

You can enable logging for TestContext and the context cache in test configuration:

~~~properties
logging.level.org.springframework.test.context=DEBUG
logging.level.org.springframework.context=INFO
~~~

Depending on the Spring version and logging configuration, useful information may include:

- Currently running test class/method.
- Whether the context was found in the cache or had to be created anew.
- Context being marked dirty.
- Context being closed and bean destroy callbacks invoked.
- Reason the context was not reused or differing cache configurations.

When investigating, check:

1. Is @DirtiesContext placed on a method, class, or base class?
2. Which value is used for methodMode or classMode?
3. Are there nested test classes or inherited classes causing the annotation to apply at a different scope than expected?
4. Does the test actually alter the ApplicationContext or only external data?
5. Are any cleanup callbacks still using beans after the context closes?
6. Is recreating the context exposing configuration errors or unstable resource dependencies?

If contexts are recreated continuously, read logs at the start and end of test classes/methods. That usually identifies the annotation or listener requesting context closure.

## 14. Comprehensive Example: Choosing Modes by Scenario

A test class can use a class-level policy when all methods alter the same kind of context:

~~~java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ApplicationModeTests {

    @Autowired
    private RuntimeSwitch runtimeSwitch;

    @Test
    void enablesMaintenanceMode() {
        runtimeSwitch.enable();
        assertTrue(runtimeSwitch.isEnabled());
    }

    @Test
    void checksAnotherRuntimeSetting() {
        // Tests in the class share the context by design.
    }
}
~~~

If only one method alters the context, you can narrow the annotation:

~~~java
@SpringBootTest
class ApplicationModeTests {

    @Autowired
    private RuntimeSwitch runtimeSwitch;

    @Test
    @DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void enablesMaintenanceMode() {
        runtimeSwitch.enable();
        assertTrue(runtimeSwitch.isEnabled());
    }

    @Test
    void checksDefaultRuntimeSetting() {
        assertFalse(runtimeSwitch.isEnabled());
    }
}
~~~

If every method needs a clean context before running:

~~~java
@SpringBootTest
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.BEFORE_EACH_TEST_METHOD
)
class FreshContextForEveryMethodTests {

    @Autowired
    private RuntimeSwitch runtimeSwitch;

    @Test
    void firstMethodCanChangeState() {
        runtimeSwitch.enable();
    }

    @Test
    void secondMethodStartsWithDefaultState() {
        assertFalse(runtimeSwitch.isEnabled());
    }
}
~~~

The examples use RuntimeSwitch to illustrate singleton state. In a real application, consider whether that state belongs in a singleton bean or can be isolated in a smaller component.

## 15. Decision Workflow for When to Close the Context

Before adding @DirtiesContext, pinpoint the scope and timing:

1. **Identify what changed.** Is it state of the Spring context/singleton bean or just database data, files, or external services?
2. **Identify the test causing the change.** Just one method, every method in a class, or an earlier class that left the context unsafe?
3. **Choose the boundary.** Use method-level when only one method needs handling; use class-level when the policy applies to the whole class.
4. **Choose timing.** BEFORE when a fresh context is needed before running; AFTER when the context must be closed after the test used and modified it.
5. **Account for callbacks.** Ensure setup and cleanup run at the desired moment relative to Spring closing the context.
6. **Evaluate cost.** Does the context have to reinitialize many times? Can state be reset more narrowly?
7. **Verify test independence.** Run the test method individually and within the suite to ensure results do not depend on order.

A short decision table can be used:

| Need | Choice |
|---|---|
| One method needs a fresh context before running | @DirtiesContext(methodMode = BEFORE_METHOD) |
| One method dirties the context after running | @DirtiesContext on method or AFTER_METHOD |
| One class needs a fresh context before starting | classMode = BEFORE_CLASS |
| One class dirties the context and needs closing at the end | classMode = AFTER_CLASS |
| Each method in the class needs a fresh context before running | classMode = BEFORE_EACH_TEST_METHOD |
| Close the context after each method in the class | classMode = AFTER_EACH_TEST_METHOD |

## Conclusion

@DirtiesContext lets you choose when Spring removes an ApplicationContext from the cache and closes it. BEFORE_METHOD and AFTER_METHOD apply to a single test method; BEFORE_CLASS, AFTER_CLASS, BEFORE_EACH_TEST_METHOD, and AFTER_EACH_TEST_METHOD apply to a test class. Choosing the timing according to where state is modified and where a clean context is required keeps tests independent while avoiding recreating contexts more often than necessary.
