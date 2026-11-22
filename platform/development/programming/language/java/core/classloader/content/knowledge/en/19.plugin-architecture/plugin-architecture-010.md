# Identifying Isolation Models in Containers and Test Runners

## 1. Why Must We Identify the Right Type of Isolation?

In Java, **isolation** does not have just one meaning. An application server can run multiple web applications in the same JVM, with each application using its own ClassLoader. A test runner can create a new test object for each method while still keeping **the same class loader and static fields**. A build tool can run tests in a **forked JVM process**; in that case, the heap, static fields, loader instances, and many VM states are all separated from the build process.

If we do not know which isolation layer the system is using, it is easy to draw wrong conclusions:

- “Two applications have the same class name, so they must be the same type.”
- “JUnit creates a new test object, so static fields are reset.”
- “Closing a URLClassLoader means the JVM has unloaded the class.”
- “Running tests in parallel across multiple threads is the same as running them in multiple JVMs.”
- “The container has isolated the plugins, so plugins cannot affect one another.”
- “The plugin class loader can see every class in the host.”
- “Every container uses parent-first like the default ClassLoader.”

**Lesson objective:** distinguish and identify **isolation by object/test instance, thread, ClassLoader, Module/ModuleLayer, JVM process, and operating system container**, with concrete runtime indicators for debugging ClassLoaders in **application containers** and **test runners**.

This topic belongs to the **Plugin Architecture** group, so the focus is on **class lookup/loading boundaries, type identity, API sharing, state management, and lifecycle**; do not treat isolation as a single security switch.

## 2. Map of Isolation Layers

| Layer | How It Is Formed | Can Isolate | Not Isolated by Default |
|---|---|---|---|
| Test instance/object | Creating a new instance of the test class | Instance fields of the new object | Static fields, JVM, class loader, database |
| Thread | Running code on a different Thread | Call stack, thread-local state | Heap, static fields, class definitions |
| ClassLoader | Different loaders defining the same binary name | Runtime class identity, static fields of separate classes, class namespace | Process, general heap, files/sockets, shared APIs |
| JPMS Module/Layer | Module graph, `requires`/`exports`/`opens`, and loader mapping | Readability/encapsulation, service discovery, module scope | Process, heap, general sandbox security |
| JVM process | A different OS process running a different JVM | Heap/GC, static state, class loader graph, system properties, process-level caches | File system, database, network, external services |
| OS container | Namespaces, cgroups, mount/network configuration | Many OS-level resources depending on configuration | External resources/volumes, kernel, shared endpoints |

**There is no simple hierarchy where “a higher layer encompasses all security permissions”:** A ClassLoader separates runtime type identity but does not prevent a plugin from calling file/network APIs itself; a module encapsulates APIs rather than acting as a sandbox; a JVM process separates memory but can still share the same database. An OS container also depends on mount configuration, networking, capabilities, and deployment policy.

To diagnose a specific situation, we must determine **what is shared**, **what is recreated**, and **when it is cleaned up**.

## 3. ClassLoader Isolation: Same Name Does Not Mean Same Runtime Class

For normal classes, the JVM distinguishes runtime classes by **binary name** and **defining ClassLoader**. Therefore:

```text
Shared Parent Loader
     ├── shared.api.PluginContract
     │
     ├── AppLoader-A
     │     └── app.impl.Worker
     │
     └── AppLoader-B
           └── app.impl.Worker
```

Two copies of `app.impl.Worker` can have the same binary name and the same bytes from the same JAR, yet be **different runtime classes** if defined by two independent loaders. Each copy has its **own static fields** and can undergo separate class initialization.

An example of identity:

```java
// Snippet, not a standalone program:
Class<?> a = loaderA.loadClass("app.impl.Worker");
Class<?> b = loaderB.loadClass("app.impl.Worker");

System.out.println(a.getName().equals(b.getName())); // true
System.out.println(a == b);                          // false if each loader defines it itself
```

The second statement **only** evaluates to `false` if each loader actually defines its own copy. If both delegate to the same parent that already has `app.impl.Worker`, `a == b` can be `true`.

### Defining Loader Differs from Initiating Loader

`loadClass(name)` on a child loader can find the class from the parent. In that case:
- The child loader is the one **initiating the request**.
- The defining loader of the returned class may be the **parent**.
- `type.getClassLoader()` indicates the **defining loader**, not necessarily the loader that was originally invoked.

To identify true isolation, **do not look only at the loader name of the variable passed to `loadClass`**. Inspect the returned `Class<?>` object itself and its defining loader.

## 4. Parent-First, Child-First, and the Class Source Actually Selected

The default algorithm of `ClassLoader.loadClass` follows a parent-first direction:

```text
loadClass(name)
    │
    ▼
findLoadedClass(name)
    │ not present
    ▼
parent.loadClass(name) / bootstrap
    │ not found by parent
    ▼
findClass(name) on current loader
    │
    ▼
runtime Class<?>
```

In a plugin system, **parent-first** is very well suited for **shared APIs**: service interfaces, DTOs, and protocol types must be understood by both the host and the plugin as the same runtime class.

Conversely, **child-first** can be useful when each plugin needs its own dependency version, but clear rules are required:
- Do not attempt to override Java platform classes.
- Do not redefine host/shared APIs in the child.
- Identify which packages are private to the plugin and which packages belong to the container.
- Do not catch every `LinkageError` and silently fall back to another class version.
- Check package access and type identity along the callback path between the plugin and the host.

**Child-first does not mean complete isolation:** platform classes, shared APIs, and resources may still be shared; the actual class/resource lookup policy also depends on the framework.

## 5. Web Application Containers: Common ClassLoader Diagram

Application servers/web containers such as Tomcat use multiple loaders to separate the container runtime and the web applications. A common conceptual model:

```text
Bootstrap / Platform
         │
       System
         │
       Common
       /    \
   Webapp-A  Webapp-B
      │         │
  WEB-INF/  WEB-INF/
  classes   classes
  + lib     + lib
```

In a typical configuration:
- The **Common loader** provides container libraries or shared components.
- **Webapp-A** sees its own classes/resources in `WEB-INF/classes` and JARs in `WEB-INF/lib`.
- **Webapp-B** has its own corresponding deployment area.
- Each webapp loader can define its own copy of the same binary name from JARs located inside the webapp.
- API/platform classes and some servlet/container APIs are usually delegated to an upper loader.

**Tomcat example:** the Class Loader How-To documentation describes that the Webapp loader by default prioritizes the webapp's internal repositories for many application classes (**local-first**), unlike the default parent-first behavior of `ClassLoader`; however, there are exceptions for the JRE base and container-provided Jakarta EE APIs. There may be a `<Loader delegate="true"/>` configuration that changes the delegation priority rules.

This shows that **“Java ClassLoader is parent-first” is not enough to guess the behavior of every container**. You must read the policy of the specific runtime and deployment setup.

### When Do Two Webapps Share a Type?

Suppose both webapps use:
- The `jakarta.servlet.Servlet` API provided by the container from the shared layer.
- `com.example.JsonHelper` packaged separately in each `WEB-INF/lib`.

They can use the **same runtime type** `jakarta.servlet.Servlet` while using **two different runtime types** `com.example.JsonHelper`. If `JsonHelper` contains a static cache, each webapp will have its own cache **if** each loader actually defines that class itself. If the class is placed in the common loader and is used from that layer, the static cache can be shared.

**Do not guess by JAR name**; a JAR present in two places is not enough to determine which class is being used. You need to check the defining loader and code source.

## 6. A Shared API Is a Mandatory “Bridge” Between Loaders

If plugin A implements `api.Service` defined by loader A, while the host uses `api.Service` defined by the parent, the two interfaces with the same name **are not the same type**. The result can be:
- `ClassCastException` when casting.
- `ServiceConfigurationError` when ServiceLoader finds that the provider is not assignable.
- `LinkageError` or `IllegalAccessError` when the dependency structure differs at runtime.
- Reflection sees matching names, but `==` on `Class<?>` returns `false`.

Good design:

```text
             Host / Shared API Loader
                      │
                  api.Service
                      │
           ┌──────────┴─────────┐
           │                    │
      PluginLoader-A       PluginLoader-B
       impl.ServiceA        impl.ServiceB
           │                    │
           └──── implements api.Service ────┘
```

Plugin implementations are separate, while the **API is shared**. The host receives objects through the shared interface and does not cast them to an implementation class of another loader.

## 7. Java 17+ Demo: Two Loaders, Two Static States, One Shared Interface

This is a practical test to **identify ClassLoader-based isolation**. The program creates **two `URLClassLoader` instances** over the same directory containing the implementation. Both use the host loader as their parent, so they use the same `CounterService` interface. However, they define two separate copies of the implementation class with different static counters.

### 7.1. Directory Structure

```text
loader-isolation/
├── src/
│   ├── api/CounterService.java
│   ├── plugin/CounterImpl.java
│   └── host/IsolationDemo.java
├── host-out/
└── plugin-out/
```

### 7.2. src/api/CounterService.java

```java
package example.api;

public interface CounterService {
    int next();
}
```

### 7.3. src/plugin/CounterImpl.java

```java
package example.impl;

import example.api.CounterService;

public final class CounterImpl implements CounterService {
    private static int counter = 0;

    public CounterImpl() {
    }

    @Override
    public int next() {
        return ++counter;
    }
}
```

### 7.4. src/host/IsolationDemo.java

```java
package example.host;

import example.api.CounterService;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class IsolationDemo {
    public static void main(String[] args) throws Exception {
        URL location = Path.of("plugin-out").toUri().toURL();
        ClassLoader parent = IsolationDemo.class.getClassLoader();

        try (URLClassLoader a = new URLClassLoader(
                     new URL[] {location}, parent);
             URLClassLoader b = new URLClassLoader(
                     new URL[] {location}, parent)) {

            Class<?> classA = a.loadClass("example.impl.CounterImpl");
            Class<?> classB = b.loadClass("example.impl.CounterImpl");

            CounterService a1 = (CounterService)
                    classA.getDeclaredConstructor().newInstance();
            CounterService a2 = (CounterService)
                    classA.getDeclaredConstructor().newInstance();
            CounterService b1 = (CounterService)
                    classB.getDeclaredConstructor().newInstance();

            System.out.println("A first: " + a1.next());
            System.out.println("A second: " + a2.next());
            System.out.println("B first: " + b1.next());

            System.out.println("same implementation class: "
                    + (classA == classB));
            System.out.println("both use shared API: "
                    + (a1 instanceof CounterService
                       && b1 instanceof CounterService));
            System.out.println("A defined by A: "
                    + (classA.getClassLoader() == a));
            System.out.println("B defined by B: "
                    + (classB.getClassLoader() == b));

            try {
                classA.cast(b1);
                System.out.println("unexpected cross-cast");
            } catch (ClassCastException expected) {
                System.out.println("cross-loader cast rejected");
            }
        }
    }
}
```

### 7.5. Compiling with the Right Classpath

Create the directories. On Bash:

```bash
mkdir -p host-out plugin-out
```

On Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force host-out,plugin-out | Out-Null
```

Compile/run with JDK 17+:

```bash
javac --release 17 -d host-out src/api/CounterService.java src/host/IsolationDemo.java
javac --release 17 -cp host-out -d plugin-out src/plugin/CounterImpl.java
java -cp host-out example.host.IsolationDemo
```

**Never add `plugin-out` to the host classpath when trying the example**. If you do, the parent loader may define `example.impl.CounterImpl` first; the two URLClassLoaders will delegate to the same parent, and the static-state isolation result will no longer hold.

Output structure:

```text
host-out/
├── example/api/CounterService.class
└── example/host/IsolationDemo.class

plugin-out/
└── example/impl/CounterImpl.class
```

### 7.6. Expected Stdout

```text
A first: 1
A second: 2
B first: 1
same implementation class: false
both use shared API: true
A defined by A: true
B defined by B: true
cross-loader cast rejected
```

**Explanation:**

1. `classA` and `classB` have the same binary name `example.impl.CounterImpl`, but two different defining loader instances; therefore `classA != classB`.
2. The static field `counter` of classA is incremented from 0 → 1 → 2; classB has its **own static counter**, incremented from 0 → 1.
3. Both classes implement **the same `CounterService` defined by the parent**, because the host/shared API is placed only in `host-out`. Therefore, objects of both can be cast to the service interface.
4. However, `classA.cast(b1)` is invalid: b1 is an instance of classB, not classA. Class casting is based on **type identity**, not string names.
5. `URLClassLoader.close()` upon exiting try-with-resources closes the resources managed by the loader; it **does not prove that the class has been unloaded or that static state is immediately garbage-collected**.

This is an example of **one JVM, two loaders**. System variables, the heap, sockets, and the filesystem still share the same process. It does not provide process isolation.

## 8. Test Runner: Test Instance Isolation Is Not ClassLoader Isolation

**JUnit Jupiter** by default creates **a new instance of the test class for each test method** (`PER_METHOD` lifecycle). This reduces contamination of **instance fields**, but it does not mean:
- a new JVM for each method;
- a new ClassLoader for each method;
- static fields of the test class are reset;
- the database/file/temp directory is reset;
- code in a background thread stops on its own.

Illustrative JUnit 5 example:

```java
// Test class snippet when the project already has the JUnit Jupiter dependency:
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class StateIsolationTest {
    private int instanceCount = 0;
    private static int sharedCount = 0;

    @Test
    void first() {
        assertEquals(1, ++instanceCount);
        ++sharedCount;
    }

    @Test
    void second() {
        assertEquals(1, ++instanceCount);
        ++sharedCount;
    }
}
```

This is a **JUnit project snippet**, not a standalone runnable Java SE program; it requires the JUnit Jupiter dependency, engine, and test runner. Both assertions on the instance field will pass under the `PER_METHOD` default. **Do not predict the final value of sharedCount based on test order** unless an execution order rule is configured; the static value persists per runtime class and does not reset just because JUnit creates a new test instance.

You can use `@TestInstance(TestInstance.Lifecycle.PER_CLASS)` if you want a shared test object; this further increases the likelihood of sharing instance state between methods, yet **still does not change the nature of static state or JVM process isolation**.

### Static Contamination Across Tests

A class:

```java
public final class GlobalState {
    public static int count = 0;
}
```

If two tests belong to the same defining loader in the same JVM, they can see **the same `GlobalState.count`**. The first test increments the variable; the second test running afterward may observe a value different from what it assumed. That is a common cause of tests that fail only when running the full suite, yet pass when run individually.

How to fix:
- Reset static state in a controlled manner in `@BeforeEach`/`@AfterEach` if appropriate.
- Avoid global mutable static state when designing the application.
- Use dependency injection/independent test fixtures.
- If a third-party library cannot be reset, use a **forked JVM** or a stronger isolation layer via the build tool.

## 9. Java 17+ Demo Without JUnit: Static State Within a Single Process

Create the file `ProcessStateDemo.java`:

```java
public final class ProcessStateDemo {
    private static int counter = 0;

    public static void main(String[] args) {
        System.out.println("test A: " + ++counter);
        System.out.println("test B: " + ++counter);
    }
}
```

Run:

```bash
javac ProcessStateDemo.java
java ProcessStateDemo
java ProcessStateDemo
```

Each process prints the same two lines:

```text
test A: 1
test B: 2
```

Because we run `java ProcessStateDemo` **twice**, the shell creates **two JVM processes**, and static state starts fresh in the second process. Within **a single run**, “test A” and “test B” (these are just printed labels) both use the `ProcessStateDemo` class and therefore share the counter.

This is a **process boundary** comparison: two different JVMs do not share the same heap/class static fields. Of course, both can still operate on the same file or database if the code requires it.

## 10. Gradle Test: Forked JVMs and Worker Reuse

In Gradle Java/JVM testing, the `Test` task typically runs tests in a **forked JVM worker process** separate from the build process. However, **a single worker process can run multiple test classes**, so **a forked JVM does not automatically mean one JVM per test class/method**.

Key configuration options:

| Gradle Test property | Practical Meaning |
|---|---|
| `maxParallelForks` | Maximum number of test JVM worker processes running in parallel for a single Test task |
| `forkEvery` | Maximum number of test classes/definitions a process handles before being replaced with a new process; `0` means no limit is applied |
| `maxHeapSize` | Heap size of the forked test JVM |
| `jvmArgs` | JVM options for workers |
| `useJUnitPlatform()` | Configures tests to run using JUnit Platform |

Example `build.gradle.kts` for a Gradle Kotlin DSL project:

```kotlin
tasks.test {
    useJUnitPlatform()
    maxParallelForks = 2
    forkEvery = 1
    maxHeapSize = "512m"
}
```

This is a **Gradle configuration snippet**, not standalone Java source run with `javac`. Appropriate Gradle project/JUnit dependencies must be present.

Interpretation:
- Allows up to two forked test JVM workers to run concurrently according to Gradle limits.
- `forkEvery=1` configures creating a new process after each test class/definition, increasing process isolation **between test classes**, though it incurs JVM startup overhead.
- Does not mean each test **method** is isolated in a separate process.
- Tests sharing a filesystem/database/external service can still contaminate each other, even across two JVM processes.

**Performance caution:** a `forkEvery` value that is too small slows down the test suite noticeably. Only increase process isolation when there is a clear need, such as a library holding static state that is hard to reset or memory/resource leaks that need to be contained.

## 11. Maven Surefire/Failsafe: Forked Processes and ClassLoader Strategy

**Maven Surefire** has several ways to launch tests and build the test classpath. You should not assume it is always just a plain `java -cp ...` inside the Maven JVM itself.

Useful options when debugging:
- `forkCount`: configures the number of forked JVM test processes in supported plugin versions.
- `reuseForks`: controls the reuse of forked processes across multiple tests/test classes according to the configuration.
- `useSystemClassLoader`: affects the strategy of using the system class loader versus an isolated loader in certain execution modes.
- `useManifestOnlyJar`: uses a manifest-only JAR for long classpaths when appropriate.
- `argLine`: passes JVM arguments to the forked test process in typical configurations.

A `pom.xml` snippet:

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-surefire-plugin</artifactId>
      <version>3.5.3</version>
      <configuration>
        <forkCount>1</forkCount>
        <reuseForks>true</reuseForks>
      </configuration>
    </plugin>
  </plugins>
</build>
```

This is a **POM snippet**, not a complete standalone `pom.xml`. The plugin version is a configuration example and should be verified against your actual project version.

If a test class is loaded by an **isolated test ClassLoader** instead of the system class loader, you may observe:
- `Class.forName(name)` from test code resolves different classes than code running in the Maven/plugin realm.
- Resources/providers looked up via TCCL change.
- Reflection or `instanceof` between a library in the test and the Maven plugin class realm may be incompatible due to class identity.

**Forking a process and loader isolation are two separate decisions:** forking creates a new JVM; inside that process, there is still its own class loader hierarchy and loading strategy. Do not try to fix a type identity error merely by guessing that `forkCount` will solve everything.

## 12. Identifying Whether Parallel Tests Run via Threads or Processes

Some parallel execution mechanisms:
- JUnit Platform can execute methods/classes across multiple worker threads within **the same JVM**.
- Gradle `maxParallelForks` runs multiple **JVM test worker processes**.
- A build system or CI can run multiple test tasks/jobs across multiple processes/machines.
- A custom runner can create independent class loaders within the same JVM to execute test suites.

Indicator table:

| Observed Indicator | Multiple Threads, One JVM | Multiple ClassLoaders, One JVM | Multiple JVM Processes |
|---|---|---|---|
| Process ID | Same | Same | Different |
| Static state of the same runtime class | Usually shared | Separate if defined separately | Separate |
| `Class<?>` of the same binary name | Same if same defining loader | Can be different | Cannot compare objects directly across processes |
| Heap | Shared | Shared | Separate |
| ClassLoader identity | Usually same | Different | Each process has its own graph |
| ThreadLocal | Separate per thread | Depends on thread; not automatic loader isolation | Not shared across processes |
| External file/database | Can be shared | Can be shared | Can still be shared |

**A single JVM process** is confirmed via process-level diagnostics. **Two different loader Java objects** alone are not enough to say they define two separate classes, because parent delegation can return the same class.

## 13. Runtime Probes: What to Print to Know Where You Are Isolated?

When running inside a container/test runner, create a helper like this:

```java
public final class RuntimeProbe {
    private RuntimeProbe() {
    }

    public static void print(Class<?> type) {
        System.out.println("pid=" + ProcessHandle.current().pid());
        System.out.println("thread=" + Thread.currentThread().getName());
        System.out.println("name=" + type.getName());
        System.out.println("loader=" + type.getClassLoader());
        System.out.println("module=" + type.getModule());
        System.out.println("TCCL="
                + Thread.currentThread().getContextClassLoader());
        System.out.println("source="
                + (type.getProtectionDomain().getCodeSource() == null
                    ? "<unknown>"
                    : type.getProtectionDomain().getCodeSource().getLocation()));
    }

    public static void main(String[] args) {
        print(RuntimeProbe.class);
    }
}
```

Compile/run:

```bash
javac RuntimeProbe.java
java RuntimeProbe
```

**Do not assume fixed stdout** for PID, thread name, loader `toString()`, or CodeSource: they depend on the OS, JDK, IDE, runner, and working path. When you need to compare real data, run the probe inside **each test/application/plugin boundary** and compare.

### Explanation of Each Field

- **PID:** does it belong to the same JVM process? A single process can have multiple class loaders.
- **Thread:** tasks on different threads can share class/static state.
- **Class name:** specifies the binary name; not enough to conclude class identity.
- **ClassLoader:** indicates the defining loader of `type`; for bootstrap, it is usually represented as `null`.
- **Module:** the runtime module of the class; named/unnamed/module layer is related to access.
- **TCCL:** the loader acting as the **discovery context** for certain SPIs/frameworks, not necessarily the defining loader of the class.
- **CodeSource:** if present, indicates the location associated with the protection domain; it can be `null`, synthetic, or lack a useful URL. Do not treat it as absolute security proof.

Better than just reading `loader.toString()`: compare **reference equality** (`a.getClassLoader() == b.getClassLoader()`) directly within the same JVM and check **`Class<?>` identity** whenever possible.

## 14. TCCL, Context Switching, and Plugin Discovery

The **Thread Context ClassLoader (TCCL)** is a field on `Thread` so that a framework in a parent loader can discover providers belonging to the application/plugin context.

Example:

```java
// Snippet:
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    ServiceLoader<MyService> services =
            ServiceLoader.load(MyService.class);
    services.findFirst().ifPresent(service -> service.start());
} finally {
    thread.setContextClassLoader(previous);
}
```

This is a **snippet**; `MyService`, `pluginLoader`, and `start()` are APIs provided by the application. `ServiceLoader.load(S.class)` uses the TCCL; **`Class.forName("p.Impl")` does not automatically use the TCCL**.

### Why Does TCCL Easily Cause “Isolation Leaks”?

If webapp/plugin A sets a worker thread's TCCL to `Loader-A` and does not restore it:
- The next request belonging to B may discover A's provider.
- A long-lived worker thread may hold a **strong reference** to Loader-A.
- After undeployment, the old class loader may not yet be eligible for GC/unloading.

Therefore, you must use `try/finally` when changing the TCCL yourself, and the container must properly manage the thread pool/worker lifecycle.

## 15. “Same Package” Can Still Be Two Runtime Packages

In the JVM, having the same package name as a string **is not enough** to grant package-private access between two classes defined by different loaders. Two classes can declare:

```java
package example.impl;
```

yet one class belongs to `Loader-A` and the other belongs to `Loader-B`. They do not automatically become the same runtime package with package-private access. In named module systems, runtime package identity also involves the module.

This causes the following situation:
- When compiled in the same source tree, package-private access works.
- When deployed into a container with separated class loaders, the runtime throws `IllegalAccessError` or a corresponding linkage/access error.
- The package name and class name in the stack trace still look identical, making the root cause hard to find.

**Solution:** do not design plugin boundaries around cross-loader package-private access; use a public shared API or place classes that must share a runtime package into the same defining loader/module according to the appropriate configuration.

## 16. ModuleLayer Isolation Differs from ClassLoader Isolation

JPMS (Java 9+) provides:
- **Module** and `module-info.java`: `requires`, `exports`, `opens`, `uses`, `provides`.
- **ModuleLayer**: a grouping of modules resolved in a runtime configuration.
- **ClassLoader mapping**: a layer can use one or more loaders.

Not every module has its own loader. One loader can define classes for multiple modules. And module readability/encapsulation **is not a substitute for a process sandbox**.

```text
Boot layer
  ├── host.app
  └── shared.api
        │
        ▼
Child layer for plugins
  ├── plugin.one  ─┐
  └── plugin.two  ─┴─ one or more ClassLoaders
```

Module A may be able to read B without being allowed to access an unexported package of B. Conversely, having a `Class<?>` of a class from another module does not automatically allow private reflection if the package is not open.

### Identification Indicators

- `type.getModule().getName()`: module name, or `null` if it is an unnamed module.
- `type.getModule().getLayer()`: the layer of a named module when present.
- `type.getClassLoader()`: defining loader.
- `callerModule.canRead(targetModule)`: readability.
- `targetModule.isExported(packageName, callerModule)` / `isOpen(...)`: runtime package permissions.

**Do not conclude that a plugin is “sandboxed” just because it is in a child layer.** The Java module mechanism does not provide memory/process isolation or block arbitrary filesystem/network access.

## 17. Process Isolation: Static State Resets, but External State May Remain

A test runner that runs each test class in its own JVM process has these advantages:
- The ClassLoader graph starts fresh; classes and static fields from the old process are no longer shared.
- System properties, installed runtime hooks, and cached singletons of the new Java process typically initialize according to that JVM configuration.
- A JVM crash in one worker generally does not bring down the heap of another worker (though the build may still report a failure).
- You can choose different JVM arguments and a different heap limit.

However:
- Two tests can still write to **the same database schema**.
- Two processes can contend for **the same TCP port**, file lock, or fixed temp directory.
- The same OS user/credentials can access out-of-process resources.
- A subprocess spawned by an earlier test can remain alive if cleanup is done improperly.
- A new process costs CPU/memory and startup latency.

Therefore, process isolation is **a wall around the process's Java heap and class identity**, not an automatic transaction rollback for external systems.

### An OS Container Is Yet Another Layer

A Docker/Kubernetes container is an isolation mechanism at the **OS/runtime deployment** level, which may include namespace/network/mount/cgroup restrictions. A container can hold one or more processes depending on its design, though by convention a JVM service usually runs one main process.

If two JVM processes reside in the same container, they are still **two processes**; if two JVMs run in two different containers, they also have separate OS boundaries. However, both containers can still mount the same volume or talk to the same database.

**Do not equate** an “application container” (Tomcat/servlet container) with an “OS container” (Docker): the word “container” is used for two very different kinds of systems.

## 18. Plugin Systems: Deciding What Needs to Be Shared

A robust plugin architecture typically divides classes into:

| Component | Suggested Location | Reason |
|---|---|---|
| Java platform API | Bootstrap/platform loaders | Same JVM platform type |
| Shared SPI/interface/DTO | Host/common parent loader or shared module | Stable runtime identity at the boundary |
| Plugin implementation | Plugin-specific loader/module | Allows independent versions |
| Private third-party libraries | Plugin loader when isolation is needed | Avoids version conflicts with other plugins |
| Truly shared libraries | Common loader with a clear version policy | Reduces duplication; easily causes shared state |
| Credentials/config | Managed per deployment boundary | Do not treat ClassLoader as a secret store |
| Lifecycle resources | Plugin owner/manager | Clear stop/close/unregister |

Do not put everything into the parent: doing so loses the ability to have independent versions and can cause library conflicts. Nor should you push everything down to the child: if the child redefines the shared service interface, casting and discovery will break.

## 19. Loader Lifecycle and Leak Risks During Redeployment

When a webapp/plugin is redeployed, the old loader may still remain reachable via TCCL, `ThreadLocal`, servlet container listeners, scheduled executors, service provider caches, or references to `Class<?>`/implementations. Shutdown needs to quiesce requests, unregister callbacks, stop workers, restore context on the appropriate threads, close I/O and the loader when applicable, and then drop strong references. If loaded-class count/metaspace grows, inspect **retaining paths** with heap/thread diagnostics; `URLClassLoader.close()` and a single GC do not prove that classes have been unloaded.

## 20. Common Errors by Isolation Boundary

| Symptom | Hypothesis Worth Checking |
|---|---|
| Test passes individually but full suite fails | Static/shared mutable state, test order, external resource pollution |
| One webapp fails casting a class from another app | Same name but different defining ClassLoaders |
| ServiceLoader cannot find provider | Wrong TCCL/explicit loader, missing `META-INF/services` or `provides` |
| ClassCastException despite identical class name | Different defining loaders; do not compare string names |
| IllegalAccessError when separating a plugin | Runtime package/loader/module access differs from compile time |
| NoSuchMethodError when container holds multiple lib versions | Parent/shared vs. webapp dependency differs from compile-time ABI |
| Replaced JAR and ran again, yet old behavior remains | Old loader already defined the class; not properly redeployed/restarted |
| Cannot delete JAR after undeploy | Loader/JarFile/other file handle not yet closed |
| Metaspace grows after multiple redeployments | Loader still reachable via threads/TCCL/caches/listeners |
| Gradle test static state persists across classes | Multiple test classes reuse one JVM worker |
| Parallel test methods cause races | Multiple threads share object/static/external state |
| Tests running in different JVMs still contend for port | Process isolation does not separate external resources |
| Reflection throws InaccessibleObjectException | JPMS package does not have appropriate opens |
| Class.forName in host does not see plugin | Uses caller's loader instead of plugin loader/TCCL |

**Do not try to solve every error by switching to child-first.** If the issue is an external shared database, concurrency, or a class loader leak, changing delegation will not fix the root cause.

## 21. Checklist for Identifying the Isolation Model in a Real Project

When inspecting a server/test suite whose architecture is unclear:

1. **Check the process boundary.** Do the tasks share the same PID? Does the build tool fork JVM workers? Check Gradle `forkEvery`/`maxParallelForks` or Surefire `forkCount`/`reuseForks`.
2. **Check the thread boundary.** Does the test runner run in parallel using threads or processes? Is TCCL set separately per task?
3. **Check the test instance lifecycle.** JUnit `PER_METHOD` or `PER_CLASS`? This only determines the test object lifecycle; it does not automatically reset static fields.
4. **Check the loader graph.** Print the defining loader of the service API, plugin implementation, and suspect dependencies.
5. **Check the delegation order.** Parent-first or child-first? Is there a whitelist for platform/shared APIs?
6. **Check runtime type identity.** Within the same JVM, compare `Class<?>` using `==`; matching names are not enough.
7. **Check the JPMS graph.** Which module/layer is the type in? How are `requires`, `exports`, and `opens` configured?
8. **Check the classpath/code source.** Does the class file come from `WEB-INF/lib`, common/lib, a plugin jar, or the test runtime classpath? Is there shadowing?
9. **Check shared mutable state.** Static caches, singletons, ThreadLocal, global registries, filesystem, DB, ports.
10. **Check the lifecycle.** After test/undeploy, are loaders, threads, callbacks, and resource handles cleaned up?
11. **Create a small test to verify the hypothesis.** Two independent loaders + shared API; two JVM processes; JUnit isolated instances; change only one variable at a time.
12. **Read the exact-version documentation for the runner/container.** Default configurations can change; do not carry over assumptions from another framework.

## 22. Mini Decision Tree: To What Extent Is This Situation Isolated?

```text
Given two execution contexts X and Y
            │
            ▼
Same PID?
   ├─ No → JVM process states are separated
   │        └─ still check shared files/DB/network
   └─ Yes
        │
        ▼
Do X and Y use the same runtime Class<?> for the suspect type?
   ├─ Yes → same static state for that type
   │         └─ test instances/threads can still be separate
   └─ No
        │
        ▼
Different defining ClassLoaders?
   ├─ Yes → class namespace/static state of that type is separated
   │         └─ shared API/resources/process can still be shared
   └─ Need to check Module/Layer or the actual resolved class
        │
        ▼
Check TCCL, parent delegation, and code source
            │
            ▼
If facing an access issue:
   check module readability, exports, opens
            │
            ▼
If facing a state issue:
   check static, ThreadLocal, cache, external resources
```

The diagram is a **diagnostic workflow**, not a background Java algorithm. For example, across multiple JVM processes, you cannot compare two `Class<?>` objects directly because they reside in two different heaps.

## 23. Self-Check Questions

1. **Can two Tomcat webapps in the same JVM have two runtime class copies with the same name?** Yes, if two separate webapp loaders define them.
2. **Is parent-first always the default order of the Tomcat webapp loader?** No; Tomcat's webapp loader uses local-first for many app classes along with important exceptions.
3. **What does the JVM use to distinguish two classes with the same binary name?** Binary name and defining loader.
4. **Does calling loadClass on the same loader object guarantee it is the defining loader?** No, a parent may define the class.
5. **Do two plugin instances have separate static state just because they are two objects?** No; you must check which runtime class the static field belongs to.
6. **Can two separate defining loaders hold two separate static fields for the same class name?** Yes.
7. **How does the host receive plugin objects from two different loaders?** Through a shared interface/API defined by a common loader, or an appropriate data boundary.
8. **Does JUnit PER_METHOD reset static fields?** No.
9. **Does JUnit running tests in parallel using threads separate the JVM heap?** No.
10. **What does Gradle maxParallelForks primarily control?** The number of forked test JVM worker processes that can run in parallel.
11. **Is Gradle forkEvery=1 closer to isolation per test method or per test class?** Test class/definition, not per-method by default.
12. **What does Maven Surefire forkCount=0 mean regarding processes?** No forked test JVM is created under that configuration; you need to check the loader strategy for that plugin version.
13. **Do two separate JVMs share static fields?** No, though they can still share DB/files/ports.
14. **Is the TCCL the defining loader of every class executed by a thread?** No; it is only a contextual loader for APIs/frameworks that use it.
15. **Does closing a URLClassLoader guarantee immediate class unloading?** No.
16. **Are an OS container and a servlet container the same concept?** No.
17. **Is a custom ModuleLayer a sandbox against file/network access?** No.
18. **Why cannot two classes with the same name be cast even with identical bytecode?** Different defining loaders produce different runtime type identities.
19. **If a test fails only when running the full suite, what should you check first?** Shared static/external state, test order, runner process/thread reuse, and class loader boundaries.
20. **What data supports diagnosis most effectively?** PID, thread, Class object/defining loader, module/layer, TCCL, class source, and runner configuration.

## 24. Official Documentation and Further Reading

- [Java SE 17 — ClassLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, `loadClass`, `findLoadedClass`, and defining loaders.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): URL-based loader, closing, and JAR resources.
- [JVMS 17 — Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): class identity, runtime packages, and loading.
- [Java SE 17 — ModuleLayer API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html): module layers and module-to-loader mapping.
- [Apache Tomcat — Class Loader How-To](https://tomcat.apache.org/tomcat-11.0-doc/class-loader-howto.html): Common/Webapp class loaders, WEB-INF, and delegation exceptions.
- [Gradle — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): forked JVMs, `maxParallelForks`, `forkEvery`, and test workers.
- [Maven Surefire — Class Loading and Forking](https://maven.apache.org/surefire/maven-surefire-plugin/examples/class-loading.html): choosing a class loader strategy and fork modes.
- [JUnit 5 User Guide — Test Instance Lifecycle](https://docs.junit.org/5.12.0/user-guide/#writing-tests-test-instance-lifecycle): `PER_METHOD`/`PER_CLASS` and test object state.

**Conclusion:** Identifying isolation models in containers and test runners means pinpointing **the specific boundaries of class definitions, static state, module access, threads, processes, and external resources**. For Java plugins, verify the **defining ClassLoader** and shared API first; for tests, distinguish the **test instance lifecycle** from a **forked JVM process**. Do not treat any single mechanism as absolute isolation or a substitute for a security solution.
