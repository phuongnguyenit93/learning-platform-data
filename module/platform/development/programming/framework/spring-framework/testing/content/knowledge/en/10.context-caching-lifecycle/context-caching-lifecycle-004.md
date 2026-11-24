# Cache Scope Within the Same JVM and the Impact of Forked Processes

The Spring TestContext Framework stores initialized ApplicationContext instances in a static JVM cache so tests with equivalent configurations can reuse them. This mechanism reduces test execution time because creating a Spring context is often resource-intensive: reading configuration, scanning beans, creating objects, initializing connection pools, and applying auto-configuration.

The scope of the cache is **a single JVM process**. Tests running in the same JVM can share the cache if their context configurations are equivalent. When a build tool creates another forked process, the new process has its own memory and static state, so it has an independent ApplicationContext cache. Two processes do not share initialized contexts, even when running the same test suite with the same configuration.

Understanding this boundary helps explain why a test suite can run fast when tests are grouped into a single worker yet slower when increasing the number of forks, why a context is created multiple times in CI, and how to choose Gradle or Maven configurations suited to execution time, parallelism, and machine resources.

## 1. How Does the ApplicationContext Cache Work?

Whenever Spring Test needs an ApplicationContext, the TestContext Framework builds a merged configuration for the test class. That configuration is used to look up a matching context in the cache.

- If the cache already has a matching context, Spring returns that context.
- If not, Spring creates the context, applies the bootstrap steps, and stores the new context in the cache.
- Test classes with equivalent configurations can reuse the same context.
- When a context is marked invalid or evicted from the cache, Spring must recreate it if a subsequent test needs the corresponding configuration.

By default, the cache is managed in the static memory of the TestContext Framework. Because static fields belong to classes loaded within a JVM, the cache is scoped to the test execution process.

~~~mermaid
flowchart TD
    A["Test class A"] --> K["MergedContextConfiguration"]
    B["Test class B"] --> K
    C["Test class C"] --> K
    K --> Q{"Matching context in cache?"}
    Q -->|"Yes"| R["Reuse ApplicationContext"]
    Q -->|"No"| N["Create new ApplicationContext"]
    N --> S["Store in JVM cache"]
    S --> R
~~~

The diagram illustrates test classes with equivalent configurations. If configurations differ, they may need different cache entries and ApplicationContext instances.

### Why Is Context Reuse Beneficial?

Creating a Spring context can involve many tasks:

- Reading and merging configurations.
- Scanning components or registering bean definitions.
- Creating beans and resolving dependencies.
- Initializing DataSources, connection pools, or clients.
- Applying transaction managers, security, AOP, and post-processors.
- Starting web infrastructure if the context has web configuration.
- Executing bean initialization callbacks.

If 20 test classes all use an equivalent configuration, Spring may only need to create the context once in the JVM and reuse it for subsequent classes. If each class runs in a new JVM, this benefit is lost because each process starts with an empty cache.

## 2. The Cache Key Determines Which Tests Can Share a Context

Spring does not share a context just because two test classes have similar names or belong to the same package. The TestContext Framework compares merged configurations, typically represented by MergedContextConfiguration.

Important factors that can participate in determining the cache key include:

- Resource locations and configuration classes.
- Context initializer classes.
- Context loader.
- Active profiles.
- Property source locations and inline properties.
- Context customizers.
- Parent context if using a context hierarchy.

For example, two test classes both declare:

~~~java
@SpringJUnitConfig(ApplicationTestConfiguration.class)
@ActiveProfiles("test")
@TestPropertySource(properties = "feature.search.enabled=true")
class SearchServiceTest {
}
~~~

~~~java
@SpringJUnitConfig(ApplicationTestConfiguration.class)
@ActiveProfiles("test")
@TestPropertySource(properties = "feature.search.enabled=true")
class SearchControllerCollaboratorTest {
}
~~~

If the merged configuration parts are equivalent and no other factor changes the cache key, both classes can share a context. Having different class names does not automatically force Spring to create a new context.

Conversely, if one test uses the test profile while another uses the integration profile, or different properties alter the context configuration, Spring may create two separate contexts.

### Examples of Different Configurations

| Test class | Primary configuration | Reusability |
|---|---|---|
| OrderServiceTest | Config A, test profile, property X | Can share with tests having the same configuration |
| OrderControllerTest | Config A, test profile, property X | Can share if the entire cache key is equivalent |
| OrderRepositoryTest | Config B, test profile, property X | Usually needs a different context |
| OrderServiceIntegrationTest | Config A, integration profile, property X | Needs a different context when the profile changes configuration |
| OrderServiceFeatureTest | Config A, test profile, property Y | Needs a different context if the property changes configuration |

A small change in an annotation can produce a different cache key. Therefore, if a project has many variants of @SpringBootTest, @ActiveProfiles, @TestPropertySource, or ContextCustomizer, the number of contexts that need to be created can grow significantly.

### ContextCustomizer Also Affects the Cache Key

ContextCustomizer is part of MergedContextConfiguration. If a customizer holds configuration data, its equals() and hashCode() must fully reflect any data that alters the context.

For example, a customizer selecting a tenant or region must include the tenant/region value in equality. Two tests using the same value can share a context if the remaining factors are equivalent. Two tests using different values need separate contexts.

If equality ignores a value that changes beans or the Environment, Spring may treat two different configurations as equivalent and mistakenly reuse a context. If equality relies on object identity, customizers with the same configuration created as separate instances can reduce reusability.

## 3. The Cache Is Scoped to a Single JVM

Distinguish between three scenarios:

1. Multiple test classes running sequentially in the same JVM.
2. Multiple test classes running in parallel using threads in the same JVM.
3. Tests distributed across multiple separate JVM processes.

The first two scenarios can access the same static cache of the TestContext Framework. The third scenario has a separate cache in each process.

~~~mermaid
flowchart TB
    subgraph P1["JVM process 1"]
        T1["Test class A"]
        T2["Test class B"]
        C1[("Context cache 1")]
        T1 --> C1
        T2 --> C1
    end
    subgraph P2["JVM process 2"]
        T3["Test class C"]
        T4["Test class D"]
        C2[("Context cache 2")]
        T3 --> C2
        T4 --> C2
    end
    C1 -. "No shared heap/static state" .- C2
~~~

For example:

- OrderServiceTest runs in JVM process 1 and creates context A.
- OrderControllerTest also runs in process 1 with an equivalent configuration, so it can reuse context A.
- OrderRepositoryTest runs in process 2 with the same equivalent configuration, but process 2 does not have context A yet. It must create its own context in process 2's cache.

Both contexts may be created from the same configuration files and yield equivalent results, yet they are two independent object graphs in two different heaps.

### The Cache Does Not Reside in the Gradle Daemon or Orchestrating Maven Process

Build tools typically orchestrate tests using worker JVMs. The ApplicationContext is created in the test execution process, not an object that the Gradle daemon or Maven launcher can share across all workers.

Therefore:

- Two Gradle test workers are two independent processes and have separate caches.
- Two test task executions in two separate processes do not share a cache.
- Two Maven Surefire forks are two independent processes and have separate caches.
- A test re-run in the next build will not inherit the static cache of a JVM that terminated in the previous build.

Keeping the Gradle daemon alive does not mean the test worker's ApplicationContext cache remains alive. The cache belongs to the JVM running the tests and exists only for that process's lifetime.

## 4. How Do Forked Processes Differ From Thread-Based Parallel Execution?

Increasing parallelism can be done at multiple levels. Distinguish between parallelism within a single JVM and parallelism across multiple processes.

| Execution mode | JVM count | Cache scope | Primary impact |
|---|---:|---|---|
| Sequential tests in one worker | 1 | One cache | High context reusability |
| JUnit parallel execution in one worker | 1 | Threads share the cache | Can run tests concurrently with the same context |
| Multiple Gradle test workers | Multiple | Each worker has its own cache | Contexts may be created redundantly across workers |
| Multiple Maven Surefire forks | Multiple | Each fork has its own cache | Contexts are not shared across forks |
| New process per test class | Multiple processes per class | Cache is usually lost after each class | Context initialization cost increases sharply |

### Parallelism Within the Same JVM

If JUnit Jupiter runs multiple tests using threads within the same worker process, the threads still belong to the same JVM and can access the shared ApplicationContext cache.

This avoids creating a context per thread. However, it does not guarantee that every bean in the context is safe under concurrent access.

For example, a singleton service holding shared mutable state can suffer race conditions when two tests invoke it simultaneously. Repositories, connection pools, and stateful beans must be used according to their thread-safety contracts.

Attention must also be paid to tests that mutate or evict contexts from the cache using @DirtiesContext. If a context is being used concurrently by multiple tests, closing or evicting the context can affect other tests. Tests that affect context lifecycle must be organized to avoid running concurrently with tests using the same context.

### Parallelism Across Multiple JVMs

When the build tool creates multiple worker processes, each worker has its own heap. Workers can run tests simultaneously, but they cannot share in-memory ApplicationContext objects.

This provides process isolation and utilizes multiple CPU cores. In return, if workers need the same context configuration, each worker may still have to create its own context.

For example, 4 workers running tests that require ApplicationTestConfiguration may create up to 4 equivalent contexts, one in each cache. The actual number depends on how tests are distributed and how many processes actually execute those tests.

## 5. Cache Size Limit and the LRU Mechanism

The Spring TestContext Framework has a default cache size limit of **32 contexts** in common default configurations. The limit can be adjusted with the property:

~~~properties
spring.test.context.cache.maxSize=64
~~~

Or by passing a system property to the test JVM:

~~~text
-Dspring.test.context.cache.maxSize=64
~~~

When the cache exceeds the limit, Spring uses an LRU (Least Recently Used) strategy: the least recently used context will be evicted from the cache to make room for a new context.

Evicting a context from the cache means Spring can no longer reuse that entry. When a subsequent test needs the corresponding configuration, the context must be recreated. Eviction also triggers context closing lifecycle according to the cache mechanism.

### Why Can Cache Churn Occur?

Suppose a test suite has 50 distinct context configurations while the cache holds at most 32 entries. As tests continuously cycle through different configurations, older entries may be evicted before tests need to reuse them.

As a result:

- Contexts are recreated repeatedly.
- Startup costs repeat.
- Database pools or web infrastructure may be initialized many times.
- Total execution time increases even though the number of tests has not changed.

Increasing cache maxSize can help retain more contexts, but each context may hold many beans, internal caches, connection pools, or resources. An overly large cache increases heap usage and can cause memory pressure.

Do not raise the limit merely because you see cache misses. First determine the actual number of context configurations and check whether many tests are creating unnecessary variants.

### Configuring the Limit in the Test JVM

With Gradle, you can pass the property to the Test task:

~~~groovy
tasks.withType(Test).configureEach {
    systemProperty 'spring.test.context.cache.maxSize', '64'
}
~~~

With Maven Surefire:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <systemPropertyVariables>
            <spring.test.context.cache.maxSize>64</spring.test.context.cache.maxSize>
        </systemPropertyVariables>
    </configuration>
</plugin>
~~~

The property name must be passed to the JVM executing the tests. Setting it in the Maven/Gradle launcher environment without forwarding it to the worker JVM may prevent the test process from receiving the expected value.

## 6. How Do Forked Processes Affect Gradle?

Gradle executes tests using test worker processes. Key properties controlling how workers are created include:

- maxParallelForks: the number of worker processes that can run in parallel for a Test task.
- forkEvery: the maximum number of test classes executed in a single worker process before Gradle stops that worker and creates a new process.
- systemProperty: passes a system property into the test worker JVM.

### maxParallelForks

Example:

~~~groovy
tasks.test {
    maxParallelForks = 1
}
~~~

One worker process is used at a time for this Test task. Test classes executed in the same worker can reuse the cache if their context configurations are equivalent.

If increased:

~~~groovy
tasks.test {
    maxParallelForks = 4
}
~~~

Gradle can run up to four worker processes simultaneously. Each worker has its own Spring cache. Increasing the worker count can shorten execution time when tests are independent and the machine has enough CPU/RAM, but it can also increase context creations and memory consumption.

Setting maxParallelForks = 1 does not mean every Test task across the entire build shares one JVM. Each task may have its own worker process, and tasks running in parallel can also create multiple processes.

### forkEvery

forkEvery decides when Gradle replaces a worker process after a number of test classes. The default value is 0, meaning no limit on the number of classes before the worker is reused during the task's lifetime.

Example:

~~~groovy
tasks.test {
    forkEvery = 0
}
~~~

The worker can run all test classes assigned to it, giving the cache a chance to live longer.

If set to:

~~~groovy
tasks.test {
    forkEvery = 1
}
~~~

The worker process is replaced after every test class. The Spring cache of the old process cannot be transferred to the new process. If multiple classes use the same context, they may have to reinitialize the context on each fork.

Such a configuration can be useful to isolate tests that leak state or fail due to accumulated static state. However, JVM and ApplicationContext startup costs can increase significantly.

### Example of a Controlled Gradle Configuration

~~~groovy
tasks.withType(Test).configureEach {
    maxParallelForks = 1
    forkEvery = 0

    systemProperty 'spring.test.context.cache.maxSize', '64'
}
~~~

This illustrative configuration prioritizes cache reuse within each Test task. For large projects, you can increase maxParallelForks after measuring execution time and resource usage. Keep in mind that workers still have separate caches when the fork count is greater than one.

## 7. How Do Forked Processes Affect Maven Surefire?

The Maven Surefire Plugin controls the process running unit tests. Two key properties are:

- forkCount: the maximum number of JVM forks running tests in parallel.
- reuseForks: determines whether a fork process is reused across multiple test classes.

### A Reused Fork

Example:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <forkCount>1</forkCount>
        <reuseForks>true</reuseForks>
    </configuration>
</plugin>
~~~

With one fork and reuseForks enabled, the process can run multiple test classes. The Spring cache persists within that process and can be reused across compatible classes.

This is a common configuration when wanting to keep caching effective. Specific defaults may vary by plugin version or project configuration, so check the actual build configuration.

### Multiple Fork Processes

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <forkCount>4</forkCount>
        <reuseForks>true</reuseForks>
    </configuration>
</plugin>
~~~

Surefire can distribute tests across up to four JVMs. Each JVM has its own cache. Equivalent contexts may be recreated across multiple forks if the tests needing them are distributed to different processes.

### Not Reusing Forks

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <forkCount>1</forkCount>
        <reuseForks>false</reuseForks>
    </configuration>
</plugin>
~~~

When reuseForks is disabled, Surefire creates a new process for each test class according to the plugin's forking mechanism. Each process starts with an empty cache and terminates after its assigned test slice.

This option offers higher isolation, but typically makes Spring test suites slower because contexts are difficult to reuse across classes.

### Quick Comparison

| Configuration | Process | Ability to retain cache across test classes |
|---|---|---|
| forkCount = 1, reuseForks = true | One reused fork | High among tests running in the same fork |
| forkCount > 1, reuseForks = true | Multiple reused forks | Present within each fork, not shared between forks |
| reuseForks = false | New process per test class | Almost no reuse across classes |

The attributes above must be read alongside parallel configuration, provider, and Surefire version. Do not infer the number of contexts from a single attribute alone.

## 8. Why Can a Test Suite Be Slow When Multiple Forks Are Enabled?

Suppose there are 30 test classes and all need the same Spring Boot context. If run sequentially in one JVM without eviction or @DirtiesContext, the context may only need to be created once.

If split evenly across three fork processes, each process may need to create its own context. In total, three context initializations may occur instead of one.

The cost is not only creating beans. A context can open:

- Database connection pools.
- HTTP client connection pools.
- Embedded servers.
- Message listener containers.
- Schedulers or executors.
- Caches and resource managers.
- Beans holding substantial memory.

When multiple forks initialize simultaneously, external systems like databases may receive more connection pools. CI machines also need more RAM because each JVM holds its own set of objects.

~~~mermaid
flowchart LR
    A["30 test classes"] --> B["1 JVM"]
    B --> C["1 cache"]
    C --> D["1 context if configuration matches"]
    A --> E["3 JVM forks"]
    E --> F["Cache 1"]
    E --> G["Cache 2"]
    E --> H["Cache 3"]
    F --> I["Context 1"]
    G --> J["Context 2"]
    H --> K["Context 3"]
~~~

The diagram is an illustrative example when tests are split across forks and each fork runs at least one class needing the same configuration. Actual distribution is determined by the build tool.

### When Multiple Forks Are Still Beneficial

Multiple forks can reduce total execution time when:

- Tests have many independent parts and long business execution times.
- Tests do not have to restart a heavy context in every class.
- The CI machine has many CPUs and sufficient RAM.
- The test database or broker can handle the number of concurrent connections.
- Tests do not share files or data causing contention.

Therefore, there is no single optimal fork count for every project. You need to measure total time, context initialization time, RAM/CPU usage, and load on test infrastructure.

## 9. Reading Statistics to See How the Cache Is Being Used

The Spring TestContext Framework can log cache statistics. Enable DEBUG level for the logger:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

Depending on the logging backend and test configuration, this can be placed in logback-test.xml, application-test.properties, or the logging configuration used by tests.

Statistics typically help observe:

- Current cache size.
- Cache size limit.
- Cache hit count.
- Cache miss count.
- Information about context hierarchy if present.

A cache hit means Spring found a matching context and reused it. A cache miss means no matching entry existed yet, so a new context had to be loaded.

Illustrative example:

~~~text
Spring test ApplicationContext cache statistics:
size = 4, maxSize = 32, parentContextCount = 0,
hitCount = 120, missCount = 4
~~~

If hitCount climbs quickly while missCount stays low, the cache is reusing contexts effectively. If missCount climbs continuously, tests may be creating many different configurations, contexts may be getting evicted, or new processes may be created repeatedly.

Statistics must be read per JVM. Each fork has its own cache and metrics. Logs from multiple processes can interleave, so inspect the PID or process information in the logs when analyzing CI runs.

### Analyzing Cache Misses

When seeing many cache misses, check:

1. Do test classes use different classes/locations configurations?
2. Does @ActiveProfiles create many profile combinations?
3. Does @TestPropertySource declare differing values?
4. Do ContextCustomizers have stable equals/hashCode implementations?
5. Are many @DirtiesContext annotations evicting contexts from the cache?
6. Is cache maxSize too small for the actual number of configurations?
7. Is the build tool creating many forks or replacing workers too frequently?

Not every cache miss is a bug. If two tests genuinely need different configurations, separate contexts are right. The goal is to eliminate unnecessary differences that reduce sharing.

## 10. @DirtiesContext and Its Impact on the Cache

@DirtiesContext marks an ApplicationContext as modified or no longer safe to reuse. Spring Test will evict the corresponding context from the cache and close it according to the framework's lifecycle.

Example:

~~~java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ChangesGlobalConfigurationTest {
    // Test alters context state
}
~~~

After the class completes, the context may be evicted from the cache. A subsequent test class needing an equivalent configuration will have to create a new context.

If @DirtiesContext is used frequently, cache hits drop and initialization time increases. Only use it when a test genuinely alters context configuration or state to the point where it can no longer be safely reused.

### Forks and @DirtiesContext Solve Different Problems

Forking a process creates a new memory boundary and static state. @DirtiesContext invalidates a context within the current JVM's cache.

- Use forks when process isolation or resetting JVM-level static state is required.
- Use @DirtiesContext when a test makes a context unsafe to reuse.
- Use @BeforeEach/@AfterEach or fixtures when only test-method state needs resetting.
- Use transaction rollback when database data belongs to the test transaction and rollback meets requirements.

Do not use forkEvery = 1 or reuseForks = false merely to hide a test that mutates a singleton. Identify which state is leaking and choose the appropriate isolation mechanism.

## 11. Context Cache and External Resources

An ApplicationContext may contain beans holding resources such as connection pools, embedded servers, schedulers, or message listeners. Reusing a context also means those beans can live across multiple test classes in the same JVM.

This can reduce startup costs, but tests must respect resource lifecycles.

### Database Connection Pools

If each fork creates a context with HikariCP, each process can create its own pool. With four forks, the database may receive four pools instead of one. If each pool allows up to 10 connections, the potential connection limit grows substantially.

Account for the number of concurrent processes and configure pools according to the test database's capacity. A test suite might run fine with one worker yet overload the database when running multiple forks.

### Testcontainers

Testcontainers can be managed per test class, suite, or context lifecycle depending on how they are declared. If the cached context is reused longer than the container's lifecycle, beans may hold endpoints of a stopped resource.

Ensure container lifecycles match the contexts using them. @DynamicPropertySource typically registers resource addresses into the context; if the context is cached, those configuration values belong to the created context. Do not stop a container while the context is still being reused.

### HTTP Servers and Message Brokers

A context with an embedded server or message listener can occupy ports, threads, and connections for as long as it is cached. Multiple forks can launch multiple corresponding instances.

If ports are fixed, processes can collide. Use dynamic ports when appropriate and ensure each process has independent resources. For shared brokers or databases, test namespaces and data must be isolated to avoid collisions.

### Shutdown and Cleanup

When a context is closed due to eviction or @DirtiesContext, beans with destroy callbacks can release resources. When a worker process terminates, the process and its OS resources terminate as well. Even so, do not rely on process termination to replace explicit cleanup of external data or resources.

## 12. An Example Measuring the Impact of Forks

Suppose a suite has 24 test classes:

- 18 classes share context A.
- 4 classes use context B.
- 2 classes use context C.

If all 24 classes run in one JVM without eviction or dirty contexts, the number of context creations can be close to three.

If tests are evenly distributed across three JVMs, each JVM may need to create context A. Contexts B and C may also be created in multiple JVMs depending on distribution. The total number of creations can exceed three.

| Hypothetical execution mode | Process count | Possible number of context creations |
|---|---:|---|
| One process, sufficiently large cache | 1 | About 3 |
| Three processes, each needing context A | 3 | At least 3 for A, plus B/C depending on distribution |
| A new process for each class | 24 | Could be close to 24 if every class needs a context |
| Two long-lived reused processes | 2 | Up to two copies of each configuration used in both processes, depending on distribution |

This is a model for understanding trends, not an exact time forecast. Time also depends on bean counts, startup hooks, databases, Docker, CPU, heap, and whether tests actually share cache keys.

### Measuring With Logs Instead of Only Watching Total Time

To compare two fork configurations:

1. Run the same set of tests and enable cache logging at DEBUG.
2. Record the actual number of processes, hits/misses, and context initialization times.
3. Re-run with a different fork count.
4. Compare total time, number of context creations, and RAM/CPU usage.
5. Check whether the database/broker experiences increased load or errors from concurrent connections.

If total time drops while context count surges sharply, the new configuration may be trading initialization cost for parallelism. Evaluate whether the CI machine and test infrastructure have sufficient resources for that execution mode.

## 13. Common Mistakes When Misunderstanding Cache Scope

### Thinking the Gradle Daemon Holds the Spring Cache

The Gradle daemon orchestrates the build. The test worker JVM executes tests and holds the ApplicationContext cache. When the worker terminates, the worker's static cache ends as well.

Keeping the daemon alive does not allow contexts to be reused in a new test worker.

### Thinking Multiple Forks Share a Single Context

Each fork is a process with its own heap. An ApplicationContext object cannot be shared directly across processes. Processes can create equivalent contexts, but each process owns its own instance.

### Increasing maxParallelForks While Expecting Startup to Happen Only Once

Adding forks creates multiple independent caches. If every worker runs tests requiring the same context, each worker may have to create that context. Measure initialization counts and actual costs before increasing forks.

### Setting forkEvery Too Low

If workers are replaced after every class or very few classes, the cache does not have enough time to be utilized. Repeated JVM startups and Spring context startups can make the suite slower.

### Setting cache maxSize Too High

A large cache holds many contexts and beans in the heap. If contexts contain pools or servers, accumulated resources can strain memory and external systems. Choose maxSize based on actual configuration counts and resource capacity.

### Using @DirtiesContext to Handle Every State Bug

@DirtiesContext drops the cache entry and recreates the context, which can be expensive. If a failure is only due to test data or a mock needing reset, use appropriate cleanup or lifecycle methods.

### Assuming Parallel Tests in the Same JVM Are Always Safe

The cache can share contexts, yet singleton beans and shared data can still be accessed concurrently. Verify thread-safety, isolate data, and avoid closing a context while other tests are using it.

### Forgetting That Tasks/Modules Have Separate Workers

A multi-module build may run multiple Test tasks. Each task may launch its own worker JVM. Contexts are not automatically shared across tasks or modules simply because they run in the same Gradle/Maven build.

## 14. Choosing the Right Fork and Cache Strategy

There is no single configuration suited to every project. Decide based on test types and available resources.

| Scenario | Configuration direction to consider |
|---|---|
| Many test classes share the same Spring context | Keep worker processes alive longer to leverage the cache |
| Context startup is very heavy, CI has limited RAM | Reduce the number of concurrent forks |
| Independent tests, long processing time, high-CPU/RAM machine | Try increasing fork counts and measure results |
| Tests leak static state between classes | Fix the source of state; use separate forks when process isolation is required |
| Many distinct contexts and cache misses due to eviction | Evaluate configuration counts and adjust maxSize |
| Tests need separate contexts due to configuration changes | Keep different cache keys and accept separate contexts |
| Tests use @DirtiesContext frequently | Review why contexts are mutated and whether smaller state can be reset |

A reasonable starting configuration is to keep workers reused, avoid forking too frequently, and use a worker count suited to CI resources. Then measure with cache logs and actual execution times to tune.

With Gradle, check maxParallelForks and forkEvery. With Maven Surefire, check forkCount and reuseForks. If using both Surefire and Failsafe, each plugin/task has its own process and lifecycle; do not assume the cache is shared between the two phases.

## 15. Investigation Workflow When Contexts Are Created Too Many Times

When context startup dominates test execution time, you can follow this sequence:

1. Enable DEBUG for org.springframework.test.context.cache.
2. Identify how many JVM workers are running.
3. Compare cache hits/misses within each process.
4. Group tests by merged context configuration.
5. Inspect differences in profiles, properties, initializers, customizers, and loaders.
6. Check whether contexts are evicted by @DirtiesContext or LRU eviction.
7. Check whether forkEvery/reuseForks is terminating workers too early.
8. Re-measure after adjustments to confirm context creation counts decrease.

If cache misses are high within each process, focus on configuration and cache keys. If each process has good hits while the total context count remains high, the cause may lie in the fork count or how the build tool distributes tests.

If a context is recreated after every test class despite identical configuration, inspect logs and actual configuration before concluding the cache is broken. Tests might be using @DirtiesContext, a customizer might lack proper equality, or each class might be receiving different properties/profiles.

## 16. Design Principles to Leverage the Cache Safely

To gain benefits from the ApplicationContext cache without making tests interdependent:

- Use consistent context configurations for tests that genuinely need the same environment.
- Avoid creating unnecessary profile/property variants.
- Design immutable ContextCustomizers and implement equals/hashCode based on configuration.
- Do not put per-test-method state into customizers.
- Reset mutable bean state or use appropriate fixtures.
- Only use @DirtiesContext when a context genuinely cannot be reused.
- Choose maxSize according to context count and memory capacity.
- Measure fork counts alongside context initialization counts, not just total time.
- Ensure resources like database pools, containers, servers, and brokers have lifecycles compatible with the context.
- When running tests in parallel, verify bean thread-safety and data independence.

The ApplicationContext cache is an in-memory cache of the JVM executing tests. Test classes in the same process can reuse contexts when their MergedContextConfiguration is equivalent. Parallel threads in the same process can still use that cache, though bean state and lifecycle require care. Forked processes create a new memory space and cache, so increasing forks or replacing workers frequently can increase the number of Spring context initializations.

When configuring Gradle or Maven, balance parallelism against startup cost and per-context resources. Monitoring hits/misses, cache eviction, worker counts, and context creation times will reveal whether overhead comes from test configuration or from how the build tool distributes tests.

