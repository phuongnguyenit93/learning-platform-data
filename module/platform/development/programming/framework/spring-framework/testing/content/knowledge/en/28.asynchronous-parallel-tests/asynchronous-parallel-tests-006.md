# Parallel Execution Configuration of the Test Runner

Spring tests can take a long time when they must initialize application contexts, access databases, or call integrated services. Running multiple tests concurrently makes better use of CPU and reduces total wait time, but it is only safe when tests do not contend over shared state.

In modern Spring projects, JUnit Jupiter is typically the test execution engine. JUnit has parallel execution mechanisms at the test class and test method levels, configurable via `junit-platform.properties`, annotations, or custom configuration. Build tools like Gradle and Maven also support running multiple JVM test workers. These two configuration layers are separate and can be used together.

When enabling parallel execution, three things must be decided: which tests are allowed to run concurrently, what the target concurrency level is, and how to protect resources shared across tests. With Spring Test, the last point is especially important because tests can share an application context, singleton beans, databases, system properties, or external resources.

## 1. Test execution layers

A Java test suite can execute across multiple layers:

1. **Build tool:** Gradle or Maven discovers tests, creates test tasks, and may launch multiple JVM workers.
2. **JUnit Platform:** discovers engines and coordinates tests via the launcher.
3. **JUnit Jupiter Engine:** executes tests written with JUnit Jupiter, including test classes, methods, lifecycle callbacks, and extensions.
4. **Spring TestContext Framework:** integrates the Spring context, dependency injection, test transactions, and listeners into the JUnit lifecycle.

JUnit Jupiter manages parallelism across nodes in the test tree, such as test classes and test methods. Build tools can simultaneously run multiple JVM processes. If both are enabled, the total number of concurrently running tests can exceed the thread count configured inside a single JUnit worker.

High-level diagram:

```text
Gradle / Maven test task
        |
        +--> JVM worker 1 --> JUnit Platform --> JUnit Jupiter
        |                                      +--> Test class A
        |                                      +--> Test class B
        |
        +--> JVM worker 2 --> JUnit Platform --> JUnit Jupiter
                                               +--> Test class C
                                               +--> Test class D
```

Within each JVM worker, JUnit Jupiter can also run multiple test nodes concurrently if parallel execution is enabled. Therefore, understand the configuration of both the build tool and JUnit before raising parallelism.

## 2. Enabling parallel execution in JUnit Jupiter

JUnit Jupiter disables parallel execution by default. To enable it, add a `junit-platform.properties` file to the test classpath, typically at:

```text
src/test/resources/junit-platform.properties
```

Minimum contents:

```properties
junit.jupiter.execution.parallel.enabled = true
```

Enabling this property alone does not mean all test classes and methods automatically run concurrently. JUnit also has default execution modes for nodes and a thread pool strategy configuration. If modes are not specified, nodes usually continue running in `SAME_THREAD` by default.

To run both test classes and test methods concurrently, configure:

```properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = concurrent
junit.jupiter.execution.parallel.mode.classes.default = concurrent
```

The two mode properties have different scopes:

- `junit.jupiter.execution.parallel.mode.default` sets the default mode for nodes in the test tree, typically methods.
- `junit.jupiter.execution.parallel.mode.classes.default` sets the default mode for test classes.

Valid mode values are `same_thread` and `concurrent`. Property names and values must be spelled accurately in the properties file.

### Configuration file location

JUnit Platform looks for `junit-platform.properties` on the test runtime classpath. With Gradle or Maven, `src/test/resources` is normally included on the default test classpath. If the file is placed in another directory, ensure that directory is configured as a test resource.

Do not place this file in `src/main/resources` if the goal is solely controlling tests. Test configuration should live in the test source or resource set to avoid affecting the production runtime.

## 3. Choosing execution mode for classes and methods

JUnit Jupiter provides two primary execution modes:

| Mode | Meaning |
| --- | --- |
| `same_thread` | Child nodes execute sequentially on the same thread as the parent node |
| `concurrent` | Child nodes can execute concurrently with other nodes |

The two mode properties can be combined to choose the parallelism scope.

### Running methods concurrently within each class, while classes run sequentially

```properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = concurrent
junit.jupiter.execution.parallel.mode.classes.default = same_thread
```

This configuration lets methods inside a class run concurrently, while top-level classes stay on the same thread per the class default mode. Special care is needed when methods share an instance or mutable state.

### Running classes concurrently, with methods inside each class sequential

```properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = same_thread
junit.jupiter.execution.parallel.mode.classes.default = concurrent
```

This is a more conservative choice for many Spring projects: independent test classes can run concurrently, while methods inside the same class remain sequential. Even so, two classes can still share a database, static state, or the same cached Spring context.

### Running both classes and methods concurrently

```properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = concurrent
junit.jupiter.execution.parallel.mode.classes.default = concurrent
```

This configuration has a higher degree of parallelism. Use it only when test methods are state-independent, do not rely on execution order, and have synchronization mechanisms for shared resources.

## 4. Choosing thread count via execution strategy

JUnit Jupiter provides strategies for configuring parallel execution via:

```properties
junit.jupiter.execution.parallel.config.strategy = <strategy>
```

The standard strategies are:

- `dynamic`: computes parallelism based on available processors and a configured factor.
- `fixed`: uses a fixed parallelism level specified by the user.
- `custom`: uses a project-supplied implementation of `ParallelExecutionConfigurationStrategy`.

If no strategy is specified, JUnit uses the default strategy corresponding to the JUnit Jupiter version's configuration. When you want explicit control over test suite load, declare the strategy explicitly.

### Dynamic strategy

The dynamic strategy calculates parallelism from the number of available processors. You can set a factor:

```properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = concurrent
junit.jupiter.execution.parallel.mode.classes.default = concurrent
junit.jupiter.execution.parallel.config.strategy = dynamic
junit.jupiter.execution.parallel.config.dynamic.factor = 1
```

With `dynamic.factor = 1`, target parallelism is computed approximately equal to the number of available CPUs visible to the JVM. For example, if the JVM sees 8 processors, target parallelism is around 8.

You can adjust the factor to increase or decrease target parallelism:

```properties
junit.jupiter.execution.parallel.config.dynamic.factor = 0.5
```

With a factor of 0.5 and 8 processors, target parallelism is roughly 4. The dynamic strategy is useful when the same test suite runs on developer machines, CI runners, and build machines with varying CPU counts.

JUnit also supports capping the maximum pool size by a factor:

```properties
junit.jupiter.execution.parallel.config.dynamic.max-pool-size-factor = 2
```

This property defines the factor used to compute maximum pool size from available processors. It is a cap on pool size, distinct from target parallelism.

### Fixed strategy

The fixed strategy lets you declare a specific parallelism level:

```properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = concurrent
junit.jupiter.execution.parallel.mode.classes.default = concurrent
junit.jupiter.execution.parallel.config.strategy = fixed
junit.jupiter.execution.parallel.config.fixed.parallelism = 4
```

Here JUnit sets target parallelism to 4. You can also configure maximum pool size:

```properties
junit.jupiter.execution.parallel.config.fixed.max-pool-size = 8
```

`parallelism` is the target concurrency level; `max-pool-size` caps the maximum number of threads in the pool. Do not treat `parallelism = 4` as a guarantee that exactly four threads will always be active throughout the entire test run. JUnit uses a ForkJoinPool and may spawn additional threads during certain blocking situations to maintain progress, within the configured pool limit.

### Custom strategy

When parallelism needs custom calculation logic, you can implement `ParallelExecutionConfigurationStrategy` and register the class:

```properties
junit.jupiter.execution.parallel.config.strategy = custom
junit.jupiter.execution.parallel.config.custom.class = com.example.test.CustomParallelStrategy
```

A custom strategy fits when CI has heterogeneous runner types or when a team wants to tune thread pools by environment. This is a low-level extension point; for most projects, dynamic or fixed strategy is enough.

## 5. Which strategy to choose for a Spring project?

There is no single optimal parallelism value for every test suite. Consider the workload characteristics:

| Test characteristic | Recommendation |
| --- | --- |
| Many pure Java unit tests, independent and CPU-bound | Dynamic or fixed with parallelism close to available CPUs |
| Tests waiting on databases or HTTP services | May need more threads than CPUs, but must limit connection pools and external resources |
| Many heavy Spring contexts, fewer independent tests | Start by running classes concurrently and methods sequentially |
| Tests sharing static state or system properties | Serialize or use resource locks |
| Tests altering application context with `@DirtiesContext` | Do not run concurrently with other tests sharing the same context |
| Tests using `@TestInstance(PER_CLASS)` and mutable fields | Keep methods sequential or protect state explicitly |

A relatively conservative starting configuration for Spring integration tests can be:

```properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = same_thread
junit.jupiter.execution.parallel.mode.classes.default = concurrent
junit.jupiter.execution.parallel.config.strategy = dynamic
junit.jupiter.execution.parallel.config.dynamic.factor = 1
```

This allows independent test classes to run concurrently while keeping methods in each class sequential. Once tests are confirmed safe against shared state, concurrency can be expanded to the method level.

## 6. Controlling parallelism with annotations

You can configure execution mode for a class or method using `@Execution`:

```java
@Execution(ExecutionMode.CONCURRENT)
class IndependentControllerTests {

    @Test
    void readsPublicEndpoint() {
        // Independent test.
    }

    @Test
    void readsHealthEndpoint() {
        // Independent test.
    }
}
```

`@Execution(CONCURRENT)` indicates that the annotated node may run concurrently under JUnit's mechanism. Global configuration must still have parallel execution enabled.

If a class must run sequentially:

```java
@Execution(ExecutionMode.SAME_THREAD)
class SharedStateTests {

    @Test
    void updatesSharedConfiguration() {
        // Uses shared mutable state.
    }

    @Test
    void readsSharedConfiguration() {
        // Depends on shared state.
    }
}
```

`@Execution` expresses intent directly on the test class, but it does not automatically lock external resources. If multiple classes access the same resource, synchronization at that shared scope is required.

## 7. Protecting shared resources with ResourceLock

When tests need to access shared resources such as system properties, the default locale, or a shared file, JUnit provides `@ResourceLock`.

Example:

```java
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;

@ResourceLock(value = "shared-system-property", mode = ResourceAccessMode.READ_WRITE)
class SystemPropertyTests {

    @Test
    void changesPropertyTemporarily() {
        System.setProperty("app.mode", "test");
        try {
            assertThat(System.getProperty("app.mode")).isEqualTo("test");
        }
        finally {
            System.clearProperty("app.mode");
        }
    }
}
```

JUnit coordinates tests declaring the same resource key to prevent concurrent execution when a test requests conflicting access. `READ_WRITE` requires exclusive read/write access; `READ` mode allows multiple tests to read concurrently as long as no test is writing the same resource.

You can use constants like `Resources.SYSTEM_PROPERTIES`, `Resources.LOCALE`, or custom resource keys where appropriate. Importantly, all tests accessing the same resource must use the same resource lock name. If one test mutates a system property while another does not declare the lock, JUnit cannot infer the conflict.

`@ResourceLock` protects tests within the same JUnit execution context. It does not lock a database, file, or service across separate JVM processes or other builds. For external resources, appropriate synchronization at that layer is needed.

## 8. Relationship with JUnit lifecycle

By default, JUnit Jupiter creates a new test instance for each test method (`PER_METHOD`). This reduces field sharing between methods. If you use:

```java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class SharedTestInstance {
    // One instance shared across multiple test methods.
}
```

then methods in the same class share one object. If they run concurrently, mutable fields, mocks, collections, or state updated in `@BeforeEach`/`@AfterEach` can be accessed concurrently.

With `PER_CLASS`, choose one of the following approaches:

- Keep methods sequential with `@Execution(SAME_THREAD)`.
- Design the test instance and collaborators to be thread-safe.
- Isolate data and state per method.
- Use resource locks if methods access the same identified resource.

`@BeforeAll` and `@AfterAll` must also be designed not to contend with concurrently running test nodes. Do not use lifecycle callbacks to mutate global configuration while other tests are reading it.

## 9. Specific considerations with Spring TestContext Framework

Spring TestContext Framework can cache `ApplicationContext` instances across test classes with equivalent configurations. Caching reduces Spring startup time, but it also means multiple tests can share the same context and singleton beans.

### Singleton beans and mutable state

Spring beans default to singleton scope. If tests call a bean that has mutable fields or alters shared state, two concurrently running tests can interfere with each other. Keep services and controllers stateless whenever possible, create isolated test data, and avoid using singletons to hold temporary test state.

### @DirtiesContext

`@DirtiesContext` marks the context as no longer usable and instructs Spring to evict it from the cache or close it according to the declared scope. If one test marks the context dirty while another test is using the same context, parallel tests can fail unpredictably. Do not run `@DirtiesContext` tests concurrently with other tests sharing the same context; consider serializing that group of tests.

### Mock beans and context configuration changes

Annotations that replace beans or configure mocks in Spring tests can alter the cached context. If tests require different bean configurations, let Spring create distinct contexts or separate test scopes clearly. Do not manually mutate shared singleton beans across concurrent tests.

### Transactions in tests

Spring manages test transactions per current thread. Each test method runs on its own thread when executed concurrently, and the test transaction is typically bound to that execution thread. One test's data is not automatically inside another test's transaction.

However, tests can still collide when writing to the same table, using the same unique keys, touching the same records, or relying on the same seed data. Use distinct IDs per test, clean up data in a controlled manner, and avoid assuming one test's transaction rollback isolates data from all other threads.

### Async code in the application

JUnit runs test methods on JUnit threads, whereas `@Async`, `CompletableFuture`, or application executors may use other threads. A transaction bound to the test thread does not automatically propagate to worker threads. When testing async code, wait for the task to finish and assert final state explicitly; do not rely on the test thread's rollback to control operations performed on worker threads.

## 10. Parallel configuration in Gradle and Maven

JUnit controls parallelism inside a single JVM test process. Build tools can launch multiple independent JVM processes, each with its own JUnit engine and thread pool.

### Gradle

To configure Gradle to use JUnit Platform:

```groovy
tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

Gradle provides the `maxParallelForks` property to determine how many test JVM workers run concurrently:

```groovy
tasks.withType(Test).configureEach {
    useJUnitPlatform()
    maxParallelForks = 2
}
```

`maxParallelForks = 2` allows up to two JVM test workers for that task. Each worker can in turn run multiple JUnit test nodes concurrently if `junit-platform.properties` enables parallel execution. Total load can grow quickly if both levels are high.

For example, two JVM workers with a JUnit target parallelism of 4 can yield a nominal concurrency of roughly eight test nodes, depending on test distribution and resources. Tune both configuration layers according to CPU, RAM, connection pools, and external services.

### Maven Surefire

With Maven Surefire, `forkCount` determines how many JVM test processes can run concurrently:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <forkCount>2</forkCount>
        <reuseForks>true</reuseForks>
    </configuration>
</plugin>
```

JUnit Jupiter parallel execution is still configured separately via `junit-platform.properties`. `forkCount` does not replace `junit.jupiter.execution.parallel.*`; it controls the number of JVM processes, while JUnit controls the nodes inside each process.

Do not enable both a high fork count and a large JUnit thread pool without measuring load. For example, four JVMs each running eight tests concurrently can produce around 32 active test nodes, not counting the application's own internal threads.

## 11. Step-by-step guide to enabling parallel execution safely

A practical rollout approach:

1. Measure current test suite runtime and identify time-consuming test groups.
2. Categorize independent tests, database tests, tests mutating global state, and tests needing dedicated contexts.
3. Enable parallel execution in JUnit starting with concurrent classes and same-thread methods.
4. Pick dynamic or fixed strategy with moderate parallelism.
5. Add `@ResourceLock` or `@Execution(SAME_THREAD)` for tests sharing inseparable resources.
6. Keep `maxParallelForks`/`forkCount` at an appropriate level without multiplying thread layers before measuring load.
7. Run the test suite repeatedly on CI to uncover flaky race conditions.
8. Expand concurrency to the method level once tests are verified safe.
9. Monitor RAM, CPU, database connections, context startup times, and error logs as load increases.

If the test suite begins failing intermittently after enabling parallelism, treat it as a sign of unisolated shared state or resources. Look for shared sources such as static fields, mutable singleton beans, shared files, system properties, database records, mock servers, or a context closed while another test is still using it.

## 12. Starter configuration example

For a Spring Boot project using JUnit Jupiter, you can start with:

```properties
# src/test/resources/junit-platform.properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = same_thread
junit.jupiter.execution.parallel.mode.classes.default = concurrent
junit.jupiter.execution.parallel.config.strategy = fixed
junit.jupiter.execution.parallel.config.fixed.parallelism = 4
junit.jupiter.execution.parallel.config.fixed.max-pool-size = 8
```

Gradle:

```groovy
tasks.withType(Test).configureEach {
    useJUnitPlatform()
    maxParallelForks = 1
}
```

This configuration allows at most one Gradle test JVM, within which JUnit has a target parallelism of four and allows the pool to expand up to eight threads under ForkJoinPool mechanics. Test classes can run concurrently; methods within the same class remain on `same_thread` by default.

This is only a starting point. If integration tests share a small database or a container service with limited connections, reduce parallelism. If tests mostly wait on I/O and resources are sufficient, you can carefully try increasing concurrency.

## 13. Common issues

### Enabled parallel.enabled, yet tests still run sequentially

Check `mode.default` and `mode.classes.default`. Simply enabling the feature does not automatically change the execution mode. In addition, `@Execution(SAME_THREAD)` annotations or resource locks may force some nodes to run sequentially.

### Tests pass in isolation but fail when running the whole suite

Usually caused by shared state, duplicate database data, shared files, system properties, or mutated contexts. Isolate data, protect resources, or serialize dependent test groups.

### Increasing parallelism makes tests slower

This can happen due to CPU/RAM overload, concurrent context creation increasing memory pressure, exhausted database connection pools, or throttled external services. Higher parallelism does not always reduce total runtime.

### Gradle/Maven runs multiple workers, and JUnit also spawns many threads

These are two independent parallelism layers. Calculate total load as the number of JVM workers multiplied by the target concurrency in each worker, then measure in the actual CI environment.

### Test transactions do not isolate async operations

Test transactions are bound to the test execution thread. Work running in a separate executor may not participate in that transaction. Wait for the task to complete and manage data created by worker threads explicitly.

## 14. Conclusion

JUnit Jupiter controls parallel execution of test classes and test methods via `junit.jupiter.execution.parallel.*` properties, execution modes, and strategies. `dynamic` adapts to CPU count, `fixed` sets a specific parallelism level, and `custom` serves bespoke control needs. Gradle `maxParallelForks` and Maven Surefire `forkCount` control the number of JVM workers, which is a separate configuration layer from JUnit's thread pool.

With Spring Test, start by running independent test classes concurrently while keeping methods within a class sequential. Protect global state with resource locks, avoid sharing mutable singletons, and pay attention to `@DirtiesContext`, transactions, and async tasks. Increase parallelism incrementally and measure on CI to achieve good speed while keeping tests stable.
