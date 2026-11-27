# Tracing the Initialization Chain to Find Root Causes

## 1. Why Do We Need to Trace the Class Initialization Chain?

In a Spring Boot application, an error appearing at startup may originate from the static initializer of a class invoked indirectly through multiple dependencies. With GraalVM Native Image, the situation is even more complex because some classes may be initialized during the build while others are kept to initialize when the process runs.

One class can trigger initialization of another class when reading a static field, calling a static method, creating an instance, or performing a dependent operation. Therefore, the class appearing last in a stack trace is not necessarily the root cause. You need to find the **initialization chain**, when each class is initialized, and the first operation that caused the failure.

In the **SPRING_BOOT_NATIVE_IMAGE** module, this lesson guides you through tracing the initialization chain on the JVM and Native Image, distinguishing build-time from runtime failures, isolating classes with side effects, and choosing the appropriate fix.

## 2. Java's Class Initialization Rules

Under Java rules, a class is initialized prior to certain active operations such as creating an instance, calling a static method, or reading/writing a non-constant static field. Initialization consists of executing static field initializers and static initializer blocks in textual order within the class.

Example:

```java
final class DatabaseDefaults {
    static final int PORT = 5432;

    static {
        System.out.println("DatabaseDefaults initialized");
    }
}

final class DataSourceFactory {
    static final String URL = createUrl();

    static {
        System.out.println("DataSourceFactory initialized");
    }

    private static String createUrl() {
        return "jdbc:postgresql://localhost:" +
                DatabaseDefaults.PORT;
    }
}
```

When `DataSourceFactory` is initialized, `createUrl()` is invoked. If that operation triggers initialization of another class, the related initializers may appear in the chain.

Note: a `static final` primitive or `String` assigned a constant expression can be a compile-time constant and does not necessarily trigger class initialization when read. For instance, `PORT = 5432` is a constant variable; do not rely solely on reading this field to assume `DatabaseDefaults` has been initialized.

## 3. Indirect Initialization Chains

Consider the example:

```java
final class AppConfig {
    static final String REGION =
            System.getenv("APP_REGION");
}

final class CloudClient {
    static final String ENDPOINT =
            "https://" + AppConfig.REGION + ".api.internal";
}

final class ClientRegistry {
    static final CloudClient CLIENT = new CloudClient();
}
```

When the application accesses `ClientRegistry.CLIENT`, the chain can look like:

```text
ClientRegistry initialization
  -> construct CloudClient
      -> initialize CloudClient
          -> read AppConfig.REGION
              -> initialize AppConfig
                  -> System.getenv("APP_REGION")
```

If Native Image initializes one of the classes in this chain at build time, the builder's environment value may be stored in the image heap. If another class is kept for runtime, the same dependency chain may run at process startup.

Do not look only at the outermost class. Trace the static fields, static methods, and constructors called by initializers, including those inside third-party libraries.

## 4. Two Environments to Monitor

| Environment | Initialization timing | Tools / indicators |
|---|---|---|
| Standard JVM | When a class is first used per Java rules | JVM unified logging, stack traces, logs inside initializers |
| Native Image build | When the compiler runs initializers selected for build time | Native Image build logs / class initialization diagnostics |
| Native executable runtime | When classes selected for runtime initialize | Application logs, stack traces, runtime diagnostics |
| Spring AOT | When the ApplicationContext is analyzed to generate code | `processAot` / AOT processing logs and condition/configuration output |

Spring AOT and Native Image class initialization are two distinct activities. AOT analyzes bean structure and generates code. Class initialization decides whether static initializers run during the build or in the runtime process. An AOT error is not necessarily a class initialization error, and vice versa.

## 5. Enabling Class Initialization Logs on the JVM

On modern JDKs, unified logging can display class initialization:

```bash
java -Xlog:class+init=info -jar target/orders-service.jar
```

For more detail:

```bash
java -Xlog:class+init=debug -jar target/orders-service.jar
```

Syntax and log levels depend on the JDK version. Logs can be very verbose, especially in Spring Boot with many dependencies. Filter by the package/class under investigation and preserve the earliest log entries associated with the error.

You can combine this with Spring's startup logging:

```bash
java -Xlog:class+init=info -jar target/orders-service.jar --debug
```

Spring Boot's `--debug` flag can generate a condition evaluation report; it does not replace JVM class initialization logs. The two sources answer different questions: which classes were initialized vs. which configurations/conditions matched.

## 6. Tracing Class Initialization in Native Image Builds

Native Image provides class initialization diagnostic options, though option names and support levels vary by GraalVM version. GraalVM releases have provided options such as:

```bash
native-image -H:+PrintClassInitialization ...
```

Some versions may support tracing by class or package:

```bash
native-image --trace-class-initialization=com.example.AppConfig ...
```

**Do not treat the commands above as immutable syntax across all versions.** Before using them, check:

```bash
native-image --help
native-image --expert-options
native-image --version
```

Some diagnostic options belong to the expert/internal category and may be renamed or removed. When building via Maven/Gradle, pass the exact build argument through the Native Build Tools plugin and verify in the logs that the argument reached the Native Image compiler.

Do not leave tracing options permanently in production configuration if they are only for diagnostics; detailed logs can increase build time and output volume.

## 7. Reading the Initialization Report in Order

When you have a report, focus on the following details:

- Which classes were initialized at build time.
- Which classes were initialized at runtime.
- The reason or dependency that caused a class to initialize.
- Which classes initialized immediately before the failing class.
- Whether any class both reads environment/files/network and initialized at build time.
- Whether any class depends on objects or native resources that cannot be stored in the image heap.

Do not look only for the class appearing at the end of the report. Reconstruct the call chain from the trigger point down to the initializer causing the side effect. If the report does not show the full call path, add controlled logging inside the initializer in a test environment or use stack traces to identify callers.

## 8. Using Temporary Logs to Locate the Trigger Point

In application-owned code, you can add temporary logging:

```java
final class RegionConfig {

    static final String REGION;

    static {
        System.err.println(
                "Initializing RegionConfig, user.dir=" +
                System.getProperty("user.dir"));
        REGION = System.getenv("APP_REGION");
    }
}
```

This log helps determine whether the initializer executed in the build process or the runtime process, but use it only in a diagnostic branch. Never log secrets or the entire environment.

Another approach is throwing an exception with a stack trace in tests to inspect the call path, though such side effects must never remain in release code. Before adding logs, check whether the initializer may already be executed by the compiler at build time; build logs and runtime logs are two separate outputs.

## 9. Distinguishing Build-Time Initialization Errors from Runtime Initialization Errors

### Errors during the build

Common signs:

- Native Image build fails while initializing a class.
- Messages mentioning objects that cannot be stored in the image heap.
- Build process attempts to open files, connect to the network, or start threads.
- Build-machine environment values show up in static state.

Resolution direction: find the initializer causing side effects, separate immutable logic from environment-dependent logic, or switch eligible classes to runtime initialization.

### Errors when the native executable runs

Common signs:

- A static initializer throws an exception at process startup or on the first request.
- The runtime environment lacks a file/library expected by the initializer.
- A static field holds a value unsuitable for the deployment environment.
- `ExceptionInInitializerError` or `NoClassDefFoundError: Could not initialize class` errors.

Resolution direction: inspect the underlying exception inside `ExceptionInInitializerError`, identify which class failed, and check the class initialization policy along with its dependency chain.

## 10. Understanding ExceptionInInitializerError and NoClassDefFoundError

If a static initializer throws an exception, the JVM typically wraps the first failure in `ExceptionInInitializerError`. Subsequent uses may receive `NoClassDefFoundError: Could not initialize class`, because the class failed during initialization in that process.

Example:

```java
final class SecretConfig {
    static final String TOKEN;

    static {
        TOKEN = Files.readString(
                Path.of("/run/secrets/api-token"));
    }
}
```

If the file does not exist, the first initialization attempt can throw an exception. Later stack traces might only show `Could not initialize class SecretConfig`, hiding the root cause.

When debugging:

1. Find the very first error in the process logs.
2. Open the deepest `Caused by`.
3. Identify the class initializer and file/environment/network operation.
4. Check the process user, paths, mounts, and permissions.
5. Re-run in a fresh process after fixing; a failed class will not self-recover within the same process.

## 11. Identifying Failing Classes in a Dependency Chain

The failing class may belong to a library rather than application source code. For example, an SDK with a static initializer that reads a config file or loads a native library. Do the following:

- Identify the JAR containing the class from the dependency tree or build report.
- Inspect the class's static fields and static initializer if suitable source/decompiler is available.
- Find other classes invoked from the initializer.
- Check the library version and GraalVM Native Image support notes.
- Check whether the library already provides reachability metadata or Spring `RuntimeHints`.

Do not directly patch dependency JARs or generated sources. If the bug lives in a library, consider upgrading to a Native Image-compatible version, configuring initialization appropriately, or reporting upstream with a minimal stack trace.

## 12. Isolating with Run-Time Initialization

If a class depends on the environment and should not initialize at build time, you can instruct Native Image to keep initialization until runtime:

```bash
native-image \
  --initialize-at-run-time=com.example.environment.RegionConfig \
  ...
```

In Maven/Gradle, pass this option through Native Build Tools configuration. Illustrative Gradle example:

```groovy
graalvmNative {
    binaries {
        main {
            buildArgs.add(
                '--initialize-at-run-time=com.example.environment.RegionConfig'
            )
        }
    }
}
```

Verify the DSL for your plugin version. After rebuilding, confirm via reports/logs or testing in an environment different from the builder that the class actually initializes at runtime.

Switching a class to runtime is not always the final fix. If the initializer creates threads, connects to a database, or makes network calls, move those side effects into a bean lifecycle or service instead of letting a static initializer do that work.

## 13. When Should You Refactor Instead of Changing Initialization Policy?

An initializer may be doing too much:

```java
final class ApplicationBootstrap {
    static final Rules RULES = loadRulesFromDisk();
    static final Client CLIENT = connectToRemoteService();
    static final String REGION = System.getenv("APP_REGION");
}
```

Switching the entire class to runtime initialization forces all of that work to run at startup, including disk reads and network connections. A cleaner design:

- Immutable data: keep in constants or pure classes.
- Deployment configuration: bind via `@ConfigurationProperties`.
- Reading external files: use a service/bean with a runtime path.
- HTTP/database clients: instantiate beans following lifecycle and connection policies.
- Threads/schedulers: start/stop via Spring-managed lifecycle.
- Secrets: retrieve from a secret source at runtime, never embedded in static state.

Refactoring to separate side effects from initializers makes testing easier, reduces initialization-order dependencies, and clarifies startup failures.

## 14. Step-by-Step Diagnostic Workflow

Use the following workflow when a native build or process startup fails:

1. **Record the first error:** capture the entire initial exception and its `Caused by` chain, not just the last error line.
2. **Identify the phase:** did the failure occur during Maven/Gradle AOT, Native Image compilation, or running the executable?
3. **Locate the class initializer:** identify the class with the relevant static field or `static` block.
4. **Reconstruct the dependency chain:** trace classes/methods/constructors called from the initializer.
5. **Classify the side effect:** environment, file, clock, randomness, network, thread, native library, or immutable data.
6. **Read the initialization report:** confirm whether the class is handled at build time or runtime.
7. **Choose the fix:** refactor side effects, switch eligible classes to runtime, or keep build-time if the initializer is deterministic.
8. **Rebuild from the recorded configuration:** do not change multiple variables simultaneously to avoid losing track of the root cause.
9. **Run in the target runtime image:** verify paths, libraries, user, and environment.
10. **Run regression tests:** ensure fixing the initializer did not alter other bean/configuration behavior.

## 15. Common Symptoms and Causes Table

| Symptom | Possible cause | Check first |
|---|---|---|
| Build reports object cannot be stored in image heap | Static state holds threads, sockets, native handles, or unsupported objects | Class initialization report and initializer chain |
| Build attempts to read developer-machine files | File access inside a static initializer running at build time | Stack trace, CWD, and file path |
| Native uses builder environment values | Static field was frozen in the image heap | Build/runtime environments and class policy |
| Runtime throws `ExceptionInInitializerError` | Initializer failed during process startup | Deepest `Caused by` |
| Later calls report `Could not initialize class` | First initialization attempt already failed | Earliest process log entries |
| Fails only inside container | Files/libraries/permissions differ from host or runtime-init class depends on environment | Mounts, user, loader, and runtime config |
| Slow startup after moving many classes to runtime | Too much work shifted to process startup | Compare initialization reports and readiness time |
| Fails after upgrading dependency | Library's initializer or policy changed | Dependency version and updated report |

## 16. Hands-on Exercise: Tracing a Three-Class Initialization Chain

**Context:** an application has `ClientRegistry`, `RemoteClient`, and `DeploymentSettings`. A static field reads `APP_REGION` and constructs an endpoint.

**Step 1 — Create the dependency chain.** Have `ClientRegistry` initialize `RemoteClient`, and have `RemoteClient` read `DeploymentSettings.REGION`.

**Step 2 — Run on JVM with logging.** Use `-Xlog:class+init=info` and temporary logs inside initializers to observe the order.

**Step 3 — Build Native Image.** Enable class initialization diagnostics appropriate for your GraalVM version; save logs and distinguish build-time vs. runtime classes.

**Step 4 — Change environment.** Build with `APP_REGION=build-region`, run with `APP_REGION=runtime-region`; observe static values.

**Step 5 — Isolate.** Switch `DeploymentSettings` alone to runtime initialization and rebuild; verify runtime values.

**Step 6 — Refactor.** Replace static environment access with `@ConfigurationProperties` or Spring `Environment` in an appropriate bean.

**Step 7 — Regression test.** Run on JVM and native with both environments, confirming endpoints use the right configuration and recording startup and error behavior.

Completion criteria: able to describe the initialization order, identify the first class causing side effects, explain whether classes are build-time or runtime initialized, and demonstrate the solution with the native executable.

## 17. Conclusion

Class initialization failures are often the result of a dependency chain, not just the class named in the final error message. To locate the true root cause, combine JVM class-init logging, Native Image initialization diagnostics, stack traces, and inspection of static initializers across related classes.

With Spring Boot Native Image, distinguish Spring AOT from Native Image class initialization, determine build/runtime timing for each class, avoid side effects in initializers, and move only necessary classes to runtime initialization. After fixing, rebuild and test the executable inside the target runtime container to confirm configuration values, resources, and startup behavior are all correct.
