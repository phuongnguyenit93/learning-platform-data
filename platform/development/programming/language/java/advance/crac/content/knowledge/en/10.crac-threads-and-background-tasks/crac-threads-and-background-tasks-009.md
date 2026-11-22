# Virtual Threads and Structured Concurrency: Checking Support by Build

Virtual threads and structured concurrency are two important approaches when building Java applications with many concurrent tasks. Virtual threads help create and manage a large number of concurrently running tasks at lower cost than platform threads across many workloads. Structured concurrency organizes child tasks under the scope of a parent task, helping manage waiting for results, task cancellation, and error handling within a clear lifecycle.

When introducing these two features into an application using CRaC, you must verify support across the exact JDK build, Gradle toolchain, compiler, test runtime, and deployment runtime. Virtual threads became an official feature in Java 21. Structured concurrency was introduced as a preview API, and the API can change across JDK releases. A build that compiles successfully is not enough to prove the application can run on a different runtime or can checkpoint/restore safely.

## 1. Distinguishing Virtual Threads and Structured Concurrency

The two concepts are related yet solve two different problems:

| Concept | Problem solved | Lifecycle |
|---|---|---|
| Virtual thread | How to run a task on a lightweight JVM-managed thread | The thread can be created, run, awaited, and terminated like a Java thread |
| Structured concurrency | How to group and coordinate subtasks within a parent task's scope | The parent task awaits or cancels subtasks before leaving the scope |

Virtual threads do not automatically create a parent-child structure for tasks. Conversely, structured concurrency does not mean every subtask must run on a virtual thread; the executor or thread factory used depends on the JDK version's API and configuration.

When used together, an application can create a scope to launch multiple subtasks while running each task on a virtual thread. The scope helps ensure subtasks are managed together with the parent unit of work.

## 2. Virtual Threads: Support Status and How to Check

Virtual threads were finalized in Java 21 (JEP 444). From Java 21 onward, applications can use official APIs such as:

- Thread.ofVirtual() to create a Thread using a virtual thread builder.
- Thread.startVirtualThread(...) to create and start a virtual thread.
- Executors.newVirtualThreadPerTaskExecutor() to create an executor that runs each task on a new virtual thread.
- Thread.currentThread().isVirtual() to determine whether the current thread is a virtual thread or a platform thread.

Example using an executor:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualThreadExample {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            Future<String> first = executor.submit(
                    () -> loadProfile("user-01"));
            Future<String> second = executor.submit(
                    () -> loadOrders("user-01"));

            System.out.println(first.get());
            System.out.println(second.get());
        }
    }

    private static String loadProfile(String userId) {
        return "profile:" + userId;
    }

    private static String loadOrders(String userId) {
        return "orders:" + userId;
    }
}
~~~

The ExecutorService in the example is closed with try-with-resources. Closing the executor waits for submitted tasks to complete per the ExecutorService contract; applications should avoid exiting the managed scope while tasks may still hold uncontrolled resources.

Virtual threads are especially useful for workloads with many I/O-waiting operations. They do not make a CPU-bound computation run faster merely because the thread is virtual. For heavy computation tasks, the number of concurrent tasks still needs to be bounded according to CPU count and system capacity.

### Checking Virtual Threads in Source Code

The most direct way to confirm is compiling a short snippet using Java 21 APIs:

~~~java
public class VirtualThreadCapability {
    public static void main(String[] args) throws Exception {
        Thread thread = Thread.startVirtualThread(
                () -> System.out.println(
                        "isVirtual = "
                                + Thread.currentThread().isVirtual()));
        thread.join();
    }
}
~~~

If the compiler does not recognize Thread.startVirtualThread or isVirtual(), the compiler/toolchain in use does not provide the corresponding API. If it compiles yet the runtime does not support that bytecode or API, the application can still fail at runtime. Check both the compiler and the runtime.

## 3. Structured Concurrency and Preview Status

Structured concurrency provides a way to organize concurrent tasks following lexical scope structure. The parent task opens a scope, forks subtasks, waits for them to finish or cancels on error, and then closes the scope before returning results.

For example, a request needs to load a user profile and an independent order list:

~~~text
Parent request
    |
    v
Open task scope
    |
    +------> Subtask: load profile
    |
    +------> Subtask: load orders
    |
    v
Join / await results
    |
    +------> On error: cancel remaining subtasks per policy
    |
    v
Close scope
    |
    v
Return result to parent request
~~~

Unlike submitting tasks to a shared executor and letting them run independently, the scope structure makes clear who owns the subtasks and when they must finish. When the parent request finishes, subtasks should not continue running orphaned and retaining the old request's resources.

Structured concurrency was introduced as a preview API starting in Java 21 and continues to evolve across JDK releases. Because it is preview, class names, constructors, methods, return types, and shutdown policies can change between preview iterations. Do not take an example from JDK 21 and assume it will compile verbatim on a newer JDK.

When using structured concurrency, specify the exact JDK version the source code targets. Read the JEP and API documentation matching that exact JDK version, then verify with the build's compiler. If the feature changes status in a future JDK, use that JDK's documentation to identify the official API and remove preview flags that are no longer needed.

### Preview API Examples Must Be Tied to a JDK Version

The example below illustrates using StructuredTaskScope in a preview release such as Java 21. It is a version-specific example, not a snippet usable verbatim across every JDK:

~~~java
import java.util.concurrent.StructuredTaskScope;

public class StructuredTaskExample {
    public Response load(String userId) throws Exception {
        try (var scope =
                     new StructuredTaskScope.ShutdownOnFailure()) {
            var profile = scope.fork(() -> loadProfile(userId));
            var orders = scope.fork(() -> loadOrders(userId));

            scope.join();
            scope.throwIfFailed();

            return new Response(profile.get(), orders.get());
        }
    }

    private String loadProfile(String userId) {
        return "profile:" + userId;
    }

    private String loadOrders(String userId) {
        return "orders:" + userId;
    }

    public record Response(String profile, String orders) {}
}
~~~

When moving to a different preview JDK release, recheck constructors, fork return types, how results are retrieved, and join/throwIfFailed methods. Using var in the example does not eliminate API compatibility requirements; the compiler still must recognize the exact methods and return types of the version in use.

## 4. Determining Which JDK Is Actually Used in the Build

One machine can have multiple JDKs installed simultaneously. The java command, javac command, Gradle daemon, Gradle toolchain, and application runtime may point to different JDK builds.

Basic inspection commands:

~~~shell
java -version
javac -version
gradlew.bat --version
gradlew.bat javaToolchains
~~~

Meaning:

- java -version shows the runtime found via PATH in the current terminal.
- javac -version shows the compiler found via PATH.
- gradlew.bat --version shows the Gradle version and the JVM running the Gradle wrapper/daemon for that invocation.
- gradlew.bat javaToolchains lists the JDK toolchains detected by Gradle (when Java plugin/toolchain support is configured).

The output of gradlew.bat --version is not necessarily the compiler used to compile source. If the project declares a Java toolchain, Gradle can select a different JDK for compile/test. Conversely, a JavaExec task or a process launched outside Gradle can use another runtime.

Inside the application itself, you can print the runtime version:

~~~java
System.out.println("Runtime version: " + Runtime.version());
System.out.println("Runtime feature: " + Runtime.version().feature());
System.out.println("Current thread virtual: "
        + Thread.currentThread().isVirtual());
~~~

The snippet checking isVirtual() must be compiled with a JDK containing Java 21+ APIs. If the application must run across multiple JDK versions, place the version check in a module or profile with appropriate source compatibility.

## 5. Configuring the Java Toolchain for Gradle

The Java toolchain helps the build select a JDK of a specific version instead of relying solely on the development machine's PATH.

Example configuration in Gradle Groovy DSL:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

When configured as above, Gradle locates a Java 21 toolchain for the relevant Java tasks. Task compilers and launchers can be selected via the toolchain, while the JVM running Gradle remains a separate concept.

If the project also configures sourceCompatibility, targetCompatibility, or options.release, ensure they are consistent with the toolchain and deployment target. The toolchain specifies the JDK used for tasks; --release restricts target APIs and bytecode. These two configurations do not replace each other.

For virtual threads, if the project compiles with Java 21 or later and the deployment runtime also supports Java 21 or later, there is no need to enable preview just to use virtual threads.

## 6. Enabling Preview for Structured Concurrency

Preview features must be enabled at both compile time and runtime. With Java 21 preview, the compiler must use JDK 21 itself and the --enable-preview flag; the runtime running the preview bytecode must also use JDK 21 with this flag.

Example Gradle Groovy DSL configuration for a project pinned to JDK 21:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['--enable-preview']
}

tasks.withType(Test).configureEach {
    jvmArgs '--enable-preview'
}

tasks.withType(JavaExec).configureEach {
    jvmArgs '--enable-preview'
}
~~~

In real projects, enable preview only for source sets, modules, or tasks that need to use preview APIs. Do not enable it globally if the application does not need preview, because this flag affects compiling and running classes using preview features.

### Compiler and Runtime Must Be the Same Preview JDK

Preview features are bound to a specific JDK release. For example:

- Code using JDK 21 preview APIs must be compiled with the JDK 21 compiler with --enable-preview.
- A JDK 21 runtime must have --enable-preview when running classes using preview.
- A newer JDK compiler cannot use --enable-preview to generate preview bytecode for an older JDK release by setting --release to the older release.
- Preview APIs can change or be removed in the next release; source must be updated to the new release's API.

Therefore, sourceCompatibility = 21 or options.release = 21 by itself does not prove JDK 21 structured concurrency preview is enabled properly. Both the compiler version and preview flags must be checked.

## 7. Checking Support Across Each Layer of the Build

Check each layer separately rather than concluding from a single java -version command.

| Check layer | What to confirm | Evidence |
|---|---|---|
| JDK on terminal | Which version PATH points to | java -version, javac -version |
| Gradle runtime | Which JVM is running Gradle | gradlew.bat --version |
| Gradle toolchain | Which JDK is chosen for compile/test | gradlew.bat javaToolchains and toolchain configuration |
| Compiler | Whether virtual thread/structured concurrency APIs compile | Run compile task with actual source |
| Test runtime | Whether the preview flag is passed to the test JVM | Run tests using the preview API |
| JavaExec/application | Whether the JVM launching the application has the right JDK and flags | Run the actual task or inspect launch configuration |
| Production runtime | Whether the deployment JRE/JDK supports the exact bytecode/API | Inspect image/container and java -version in the runtime environment |
| CRaC runtime | Whether the build supports checkpoint/restore for the thread usage and libraries | Test checkpoint/restore on the exact JDK, vendor, OS, and configuration |

A passing compile only proves the source is compatible with the compiler/task that ran. It does not prove the production runtime uses the same JDK, the test JVM has the preview flag, or the CRaC runtime can safely checkpoint that workload.

## 8. How to Create a Small Capability Check

For virtual threads, you can add a small program to a test source set:

~~~java
import java.util.concurrent.Executors;

public class VirtualThreadProbe {
    public static void main(String[] args) throws Exception {
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            executor.submit(() -> {
                System.out.println("virtual = "
                        + Thread.currentThread().isVirtual());
            }).get();
        }
    }
}
~~~

For structured concurrency, the capability probe must be compiled with the exact target preview JDK, with preview flags at both compile time and runtime. The probe should invoke the constructors and methods actually used by the application, because checking only that a class name exists does not guarantee full API compatibility.

Do not use reflection to attempt detecting every preview variant and calling methods by name. Preview APIs can change parameter types, return types, and behavior; a compile-time check against the target JDK usually gives clearer results.

After the probe succeeds, module and application tests still must run. If a project has multiple modules, each module may use separate source sets, toolchains, or compiler options; do not infer from one module compiling cleanly that the entire build uses the same configuration.

## 9. Virtual Threads, Structured Concurrency, and CRaC

CRaC restores process state, including JVM state and supported runtime components. Yet using virtual threads or structured concurrency does not automatically guarantee the application can checkpoint at any arbitrary moment.

### Active Virtual Threads

A virtual thread is a Java thread managed by the JVM. A virtual thread may be running, waiting on I/O, canceled, or finished. When checkpointing, the application needs to determine which tasks can continue after restore and which tasks must finish beforehand.

Questions to answer:

- Is a virtual thread currently handling a request allowed to continue from checkpointed state?
- Is it holding a transaction, stream, socket, or lock?
- Is it in the middle of an external side effect?
- If the task is re-executed after restore, is the business logic idempotent?
- Does the specific CRaC runtime support the thread state and libraries being used?

Do not keep a virtual thread waiting indefinitely on external events if it holds unrecoverable resources. For background tasks, clear stop, drain, cancel, and resume mechanisms are needed.

### Structured Task Scopes

Structured concurrency bounds subtask lifetimes within a scope. This is an advantage when preparing for checkpoint: the application can stop creating new scopes, wait for current scopes to finish or cancel subtasks per policy, and only then transition to a quiescent state.

A scope does not automatically become a CRaC Resource. Components managing requests or task scopes still need to participate in checkpoint coordination to:

- Stop accepting requests to create new scopes.
- Wait for active scopes to finish.
- Cancel scopes per rules when waiting for completion is not possible.
- Ensure subtasks have closed owned resources.
- Restart background tasks after restore if business logic requires.

If a scope is midway through execution and gets checkpointed, do not assume restore will bring subtasks and external systems back into the same logical state. Subtasks may already have sent requests or written external data prior to checkpoint.

### Pinning and Native Operations

Virtual threads are normally unmounted from their carrier when waiting on JVM-supported operations. However, certain synchronized code sections or native operations can restrict unmounting depending on the JDK and operation type. This affects scalability and can make stopping/draining threads harder to predict.

Pinning behavior has improved across JDK releases; do not apply conclusions from one version to every other version. Consult the target JDK documentation, observe workloads with the appropriate diagnostic tools, and test with the native libraries in use.

## 10. Common Configuration Mistakes

**Development machine has a newer JDK yet Gradle uses an older toolchain.**

The compiler chosen by Gradle may not recognize virtual thread or structured concurrency APIs. Check javaToolchains and task toolchain configuration.

**Compile succeeds yet tests report preview errors.**

The test JVM has not received --enable-preview, or tests run with a different JDK than the compiler that generated the preview bytecode.

**Enabling preview only for JavaCompile.**

Preview bytecode also needs to be run with an appropriate runtime with the --enable-preview flag. Configure Test, JavaExec, and production launchers accordingly.

**Using an old --release with a newer JDK's --enable-preview.**

Preview features belong to the exact JDK compiler running. You cannot use the current JDK's preview flag to generate preview APIs of an older release.

**Structured concurrency sample fails to compile on a newer JDK.**

Preview APIs changed across releases. Cross-reference code against the exact JDK's JEP/API documentation and update source for the target version.

**Production only has a JRE/JDK different from the build toolchain.**

Bytecode may use APIs that the production runtime does not provide. Inspect the runtime inside the container or deployment host, not only the development environment.

**Assuming virtual threads automatically solve every concurrency problem.**

Virtual threads do not eliminate race conditions, deadlocks, connection pool limits, remote service limits, or backpressure requirements. Concurrency count still must be controlled according to the resources they use.

**Assuming a structured scope is automatically safe for checkpointing.**

A scope manages the relationship between parent and child tasks; it does not automatically stop traffic, complete database transactions, or reverse external side effects. Connect scopes to the application's checkpoint workflow.

## 11. Verification Procedure Before Adoption into the Application

A practical workflow can proceed in order:

1. Identify the target JDK and the vendor/runtime that will run production.
2. Check the Gradle wrapper and the JVM running Gradle.
3. Configure the Java toolchain explicitly for modules.
4. Verify virtual threads with a capability probe on JDK 21 or later.
5. If using structured concurrency, identify the exact preview JDK version and enable preview in compile/test/runtime accordingly.
6. Compile and run unit tests on the exact toolchain.
7. Run integration tests with real databases, HTTP clients, brokers, and libraries.
8. Run the application with the exact production runtime and confirm no APIs are missing.
9. Perform checkpoint/restore under representative workload, including I/O-waiting tasks and active task scopes.
10. Verify after restore that there are no duplicated tasks, unfinished transactions, stale connections, or repeated side effects.

When upgrading the JDK, rerun capability probes and checkpoint/restore tests. Do not rely on a prior passing build to conclude a new JDK has the same preview API or the same CRaC behavior.

## 12. Conclusion

Virtual threads are an official API from Java 21; structured concurrency is a preview API that can change across JDK releases. Support verification must cover the compiler, Gradle toolchain, test runtime, application launcher, and production runtime. For preview APIs, the compiler and runtime must use the corresponding JDK release and have preview enabled on both sides.

In CRaC applications, virtual threads and structured concurrency must be placed within a clear task lifecycle management workflow. The application must stop creating new work, drain or cancel running tasks, finish dependent resources, and verify behavior after restore on the exact build to be deployed.