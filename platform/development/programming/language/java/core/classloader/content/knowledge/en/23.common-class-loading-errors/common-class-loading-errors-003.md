# NoClassDefFoundError After Class Initialization Failure

> **Java Core → ClassLoader → Common Errors.** A `NoClassDefFoundError: Could not initialize class X` message usually does not mean X.class was deleted or a JAR is missing. The class may have **already been loaded successfully**, but running its static initializer (`<clinit>`) failed. The JVM marks that specific runtime class as **erroneous**, and subsequent attempts that require initialization will report `NoClassDefFoundError`. This article analyzes the mechanism, reproduces it in Java 17, identifies the initial cause, and presents the right solutions for applications, tests, servers, and plugin ClassLoaders.

## 1. Core Mechanism

A Java class normally goes through:

~~~text
Loading                Find bytecode / create runtime Class
   |
   v
Linking                Verify, prepare, resolve when appropriate
   |
   v
Initialization         Run static field initializer + static block
   |
   +--------------------------+
   |                          |
   v                          v
SUCCESS                   FAILURE
initialized               erroneous
                              |
                 first active use: EIIE or original Error
                              |
                 later initialization attempt: NCDFE
~~~

`EIIE` is `ExceptionInInitializerError`, and `NCDFE` is `NoClassDefFoundError`. When X's initializer throws an exception such as `IllegalStateException` or `NullPointerException`, the JVM typically wraps it in `ExceptionInInitializerError` on the first failure. If the initializer throws an `Error`, the JVM can propagate that Error itself rather than wrapping it in EIIE.

After the failure, the JVM records the **erroneous** state for that **specific runtime class X**—that is, the class with a specific binary name and defining ClassLoader. A subsequent use **requiring initialization** will throw `NoClassDefFoundError` without re-running `<clinit>`. Modifying environment variables, configuration files, or `System.setProperty` after this event does not automatically reset the class's state.

This is a rule in [JLS `12.4.2](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.4.2), not merely a HotSpot detail.

### 1.1. Distinguishing Three Easily Confused Errors

| Error | Layer Where It Occurs | Signs |
| --- | --- | --- |
| `ClassNotFoundException` | An API requests looking up a class by name but cannot find it | Checked exception from `loadClass`, `Class.forName` |
| `NoClassDefFoundError` due to a missing definition/dependency | JVM/linking cannot obtain a required definition | May include the missing class/dependency name |
| `NoClassDefFoundError: Could not initialize class X` | X already has a runtime Class, but prior initialization failed | Should look for the first exception from `X.<clinit>` |
| `ExceptionInInitializerError` | First failed init due to a non-Error exception | `getCause()` contains the original exception |
| `ClassFormatError` / `VerifyError` | Classfile/verification | Invalid bytes or bytecode |
| `UnsupportedClassVersionError` | Runtime does not support the classfile version | Check JDK version and `javac --release` |

A `NoClassDefFoundError` without the phrase “Could not initialize class” can still have multiple causes, so do not diagnose all of them as static-init failures. Conversely, if a first `ExceptionInInitializerError` already occurred, continuing to copy JARs is not the first fix step.

## 2. When Does Class Initialization Occur?

Under JLS `12.4.1, initialization can be triggered immediately before:

- Creating an instance with `new X()`.
- Calling a static method of X: `X.run()`.
- Assigning or reading a static field declared by X, except in the case of a **constant variable** with a compile-time constant value.
- Reflection APIs/`Class.forName(..., true, loader)` and certain method handles per the Java spec.
- When a subclass needs to be initialized, the JVM initializes its superclass and eligible superinterfaces that have default methods according to the specification's algorithm.

The following operations **do not by themselves imply** that initialization has succeeded:

~~~java
Class<?> type = X.class;
Class<?> onlyLoaded = loader.loadClass("demo.X");
Class<?> noInit = Class.forName("demo.X", false, loader);
~~~

This is a snippet requiring a valid X and loader. `ClassLoader.loadClass` is not considered an initialization command; `Class.forName(name,false,loader)` explicitly states that initialization is not required at that call. However, some other linking/resolution steps can still occur, so “not yet initialized” does not mean every reflection operation is completely error-free.

### 2.1. The Constant-Variable Exception

~~~java
static final String LABEL = "hello";       // compile-time constant
static final int SIZE = 42;                // compile-time constant
static final Object OBJECT = new Object(); // not a constant variable
static final int COUNT = compute();        // not a constant variable
~~~

These are illustrative field declarations inside a class. The compiler may inline `LABEL` or `SIZE` at the caller, so reading them does not necessarily initialize the declaring class. Reading `OBJECT` or `COUNT` typically requires initialization.

## 3. Lab 1: First EIIE, Next NoClassDefFoundError

**Single file `InitFailureDemo.java`:**

~~~java
public final class InitFailureDemo {
    static final class Broken {
        static final int NUMBER = initialize();

        private static int initialize() {
            System.out.println("initializer runs");
            throw new IllegalStateException("configuration missing");
        }

        static int read() {
            return NUMBER;
        }
    }

    public static void main(String[] args) {
        for (int attempt = 1; attempt <= 2; attempt++) {
            System.out.println("attempt=" + attempt);
            try {
                System.out.println("value=" + Broken.read());
            } catch (LinkageError error) {
                System.out.println("error="
                        + error.getClass().getSimpleName());
                if (error instanceof ExceptionInInitializerError e) {
                    System.out.println("root="
                            + e.getCause().getClass().getSimpleName());
                }
            }
        }
    }
}
~~~

Run on JDK 17+:

~~~bash
javac --release 17 InitFailureDemo.java
java -cp . InitFailureDemo
~~~

Expected stdout:

~~~text
attempt=1
initializer runs
error=ExceptionInInitializerError
root=IllegalStateException
attempt=2
error=NoClassDefFoundError
~~~

**Explanation:**

1. `Broken.read()` is a static call, so the JVM must initialize `Broken` first.
2. The static field initializer `NUMBER=initialize()` prints `initializer runs` and then throws `IllegalStateException`.
3. Because this is not an `Error`, on the first attempt the JVM reports `ExceptionInInitializerError` whose `getCause()` is the original error.
4. The runtime class `Broken` transitions to erroneous; the `read` method never actually returns a value.
5. On the next call, `Broken.read()` does not re-execute the static initializer. The JVM throws `NoClassDefFoundError`.
6. `LinkageError` is used in this lab because both EIIE and NCDFE are its subclasses; in production, do not catch every `Error` and silently ignore it.

**Why not write `static { throw new RuntimeException(); }` directly?** The Java language has a rule that a static initializer **must be able to complete normally**, so a block that unconditionally throws an exception may fail to compile. Moving the failure into the `initialize()` method produces valid code and represents a real-world scenario such as a failed configuration read.

**Stdout limitation:** This lab prints only the Throwable class name; if `printStackTrace()` is printed, the message or cause stack may vary across JVMs/JDKs. Tests are not required to assert the entire stack trace line by line.

## 4. How Does the JVM Store Class State?

JLS `12.4.2 and JVMS `5.5` describe a state for each runtime class:

| State | Behavior When Initialization Is Required |
| --- | --- |
| Verified/prepared, not yet initialized | One thread begins initialization |
| Being initialized by thread T | Re-entry by T itself follows special rules; other threads wait |
| Successfully initialized | Use the class without re-running static init |
| Erroneous after failure | Throw `NoClassDefFoundError` |

Class initialization has an **initialization lock** managed by the JVM. It is not `ClassLoader.getClassLoadingLock(name)`: the latter lock relates to loading/defining a class, preventing duplicate `defineClass` calls. A thread-safe loader implementation does not guarantee that static initializers will not fail.

If thread T1 begins initialization and thread T2 concurrently needs that class, T2 waits for T1. If T1 fails, T2 resumes and sees the erroneous state and receives NCDFE. **Which thread gets the first error depends on the scheduler**, not on thread names.

### 4.1. What If Static Code Throws an Error?

~~~java
static int load() {
    throw new AssertionError("invariant broken");
}
~~~

This snippet sits inside a class initialized via a static field. Because `AssertionError extends Error`, the initialization algorithm is not required to wrap the first occurrence into `ExceptionInInitializerError`; the first caller may see `AssertionError` directly. Afterward, the class is still erroneous and the next attempt requiring initialization receives `NoClassDefFoundError`.

Do not write the explanation “every first-time error is EIIE”. The exact rule is **to wrap non-Error throwables**, keeping Errors according to the specification's algorithm.

### 4.2. What If Superclass Initialization Fails?

When `Child extends Parent`, the JVM must initialize `Parent` before executing the static initializer of `Child`. If Parent fails, Child can be marked erroneous without Child's static code ever having run. Subsequent errors mentioning Child in the logs do not necessarily point to a cause inside `Child.<clinit>`.

How to find the root cause: trace the **stack trace of the earliest failure**, including `Parent.<clinit>`/superinterfaces and dependent static factories. Do not just search for the class name on the last NCDFE line.

## 5. Lab 2: Loading a Class Does Not Mean Initializing It

**`InitializationTriggerDemo.java`:**

~~~java
public final class InitializationTriggerDemo {
    static final class Sample {
        static {
            System.out.println("Sample initialized");
        }

        static final String CONSTANT = "fixed";
        static int dynamic = 7;
    }

    public static void main(String[] args) throws Exception {
        Class<?> type = Class.forName(
            "InitializationTriggerDemo$Sample",
            false,
            InitializationTriggerDemo.class.getClassLoader());

        System.out.println("loaded=" + type.getSimpleName());
        System.out.println("constant=" + Sample.CONSTANT);
        System.out.println("before dynamic read");
        System.out.println("dynamic=" + Sample.dynamic);
    }
}
~~~

~~~bash
javac --release 17 InitializationTriggerDemo.java
java -cp . InitializationTriggerDemo
~~~

Stdout:

~~~text
loaded=Sample
constant=fixed
before dynamic read
Sample initialized
dynamic=7
~~~

`Class.forName(name,false,loader)` obtains the Class object without initializing; reading the compile-time constant `Sample.CONSTANT` does not force initialization; only reading the nonconstant `Sample.dynamic` triggers the static block. This is how to distinguish **“the class was found/loaded”** from **“the class was initialized successfully”**.

## 6. Can You Fix the Configuration and Retry in the Same Loader?

Suppose we have a static singleton:

~~~java
public final class Settings {
    static final String TOKEN = readRequiredToken();

    static String readRequiredToken() {
        String token = System.getProperty("service.token");
        if (token == null) {
            throw new IllegalStateException("missing service.token");
        }
        return token;
    }
}
~~~

This is a compilable class (without a main method). The first time an active use causes `readRequiredToken()` to throw, `Settings` becomes erroneous. You can call `System.setProperty("service.token","fixed")`, but **that does not cause the static initializer of the same runtime Settings class to run again**.

Operations that **do not reset the erroneous state**:

- `Class.forName(name, false, sameLoader)`.
- `ClassLoader.loadClass(name)` with the same defining loader.
- Calling `System.gc()`.
- Calling `URLClassLoader.close()` while still holding the old `Class<?>`.
- Replacing/overwriting the JAR file while the JVM still holds the loaded class.
- Infinitely retrying a static method on a class whose init has already failed.

There is no general-purpose Java SE API like `resetClinit`. Practical recovery is to **restart the JVM after fixing the cause**, or in a plugin architecture create a **new defining ClassLoader** to obtain a new runtime class.

## 7. Lab 3: Recovering with a New Loader for Plugins

Structure:

~~~text
new-loader-lab/
├── plugin-src/demo/plugin/Settings.java
├── host-src/NewLoaderDemo.java
└── build/
    ├── plugin/
    ├── host/
    └── plugin.jar
~~~

**`plugin-src/demo/plugin/Settings.java`:**

~~~java
package demo.plugin;

public final class Settings {
    private static final String VALUE = initialize();

    private static String initialize() {
        String token = System.getProperty("lesson.token");
        System.out.println("init token=" + token);
        if (token == null) {
            throw new IllegalStateException("token unavailable");
        }
        return token;
    }

    public static String read() {
        return VALUE;
    }
}
~~~

**`host-src/NewLoaderDemo.java`:**

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class NewLoaderDemo {
    private static final String TYPE = "demo.plugin.Settings";

    static URLClassLoader open(URL jar) {
        return new URLClassLoader(
            new URL[] {jar}, ClassLoader.getPlatformClassLoader());
    }

    static void initialize(String label, ClassLoader loader) {
        try {
            Class.forName(TYPE, true, loader);
            System.out.println(label + "=OK");
        } catch (LinkageError problem) {
            System.out.println(label + "="
                    + problem.getClass().getSimpleName());
        } catch (ClassNotFoundException missing) {
            throw new IllegalStateException(missing);
        }
    }

    public static void main(String[] args) throws Exception {
        URL jar = Path.of("build", "plugin.jar")
                .toAbsolutePath().toUri().toURL();
        System.clearProperty("lesson.token");

        try (URLClassLoader oldLoader = open(jar)) {
            Class<?> oldType = oldLoader.loadClass(TYPE);

            initialize("old-first", oldLoader);
            System.setProperty("lesson.token", "ready");
            initialize("old-again", oldLoader);

            try (URLClassLoader newLoader = open(jar)) {
                Class<?> fresh =
                        Class.forName(TYPE, true, newLoader);
                System.out.println("same-class="
                        + (oldType == fresh));
                System.out.println("new-value="
                        + fresh.getMethod("read").invoke(null));
            }
        } finally {
            System.clearProperty("lesson.token");
        }
    }
}
~~~

From the `new-loader-lab` root (POSIX shell, Java 17+):

~~~bash
mkdir -p build/plugin build/host
javac --release 17 -d build/plugin \
    plugin-src/demo/plugin/Settings.java
jar --create --file build/plugin.jar -C build/plugin .

javac --release 17 -d build/host host-src/NewLoaderDemo.java
java -cp build/host NewLoaderDemo
~~~

Expected stdout:

~~~text
init token=null
old-first=ExceptionInInitializerError
old-again=NoClassDefFoundError
init token=ready
same-class=false
new-value=ready
~~~

**Notes:**

1. The first loader `oldLoader` finds the class in the JAR and the first init fails. Afterward `lesson.token` is fixed, but initializing with the same loader still encounters NCDFE.
2. The new loader `newLoader` genuinely **defines** the same binary name into a different runtime Class itself. Because it is not erroneous and the config is now fixed, `<clinit>` succeeds.
3. `same-class=false` checks **runtime class identity**, and does not claim that the old class has been unloaded.
4. Do not place `plugin.jar` on the host classpath or change the parent to a loader that already defined `demo.plugin.Settings`: parent delegation could cause both “new loaders” to still return the same old Class.
5. `System.setProperty` is the fault-simulation mechanism for this lab; in production, do not use shared process properties as a mutable config across concurrent requests.
6. `try-with-resources` closes the URLClassLoader/JAR handles, but does not automatically stop threads, clear static maps, or force the JVM to unload classes.

**Do not use a new loader as a way to mask every error:** you must **fix the root cause** first. If the config is still missing, the new class will fail as well.

## 8. The First Error Log Is What Needs Investigation

On a server, the first request touching `ConfigHolder` may fail at 09:00, while application logs get truncated and only the 10:00 requests printing NCDFE remain. This leads operators to mistakenly conclude that a JAR disappeared after deployment.

Diagnosis:

1. Collect the stack trace of the **first failure** from the exact JVM/process/generation.
2. Look for `ExceptionInInitializerError`, `<clinit>`, `Caused by`, or an `Error` directly from a static initializer.
3. Record the class name, process id, defining loader, and the timestamp of the first active use.
4. Distinguish among config, network, JDBC, native link, bytecode/dependency, or permission errors.
5. Check failures in **other threads**: initialization is synchronized, so a second request may only see NCDFE after waiting on the first thread.
6. When the failure starts in a superclass, find the root exception in the superclass rather than only looking at the subclass shown in the latest NCDFE.
7. Do not let a framework catch every `Throwable` and discard the original error; for a broken component, record a FAILED/UNHEALTHY status and avoid placing it into active routing.

### 8.1. Printing the Entire Cause Chain

~~~java
static void report(Throwable failure) {
    Throwable current = failure;
    while (current != null) {
        System.err.println(current.getClass().getName()
                + ": " + current.getMessage());
        current = current.getCause();
    }
}
~~~

This helper snippet must be placed inside a class. `ExceptionInInitializerError.getCause()` is the modern API for retrieving the wrapped exception; `getException()` still exists for backward compatibility. For a `NoClassDefFoundError` after an init failure, there is **no guarantee** that the original error/cause remains intact across all JDKs; the first logs are the most important source.

### 8.2. Distinguishing ClassNotFoundException and NoClassDefFoundError

For example, `Class.forName("missing.Dependency")` throws `ClassNotFoundException` if the loader cannot find the class by name. However, if A.class exists and during linking/initialization it needs a B that is absent at runtime, the JVM may raise `NoClassDefFoundError`, and the cause may name B. If A's `<clinit>` fails, subsequent attempts to initialize A can also throw NCDFE **even though A's bytes still exist**.

Therefore, first examine the **full error message, root cause, and time of occurrence** before modifying the classpath/module path.

## 9. Why Does Static Initialization Commonly Fail?

| Cause | Common Root Error | Appropriate Action |
| --- | --- | --- |
| Static config reads a missing env/file | `IllegalStateException`, `NullPointerException` | Validate before startup, clearly naming the missing key |
| Static singleton initializes a DB/HTTP client | Timeout or unchecked exception | Move to an instance lifecycle with bounded retries |
| Static initializer calls a missing dependency | Wrapped `NoClassDefFoundError`/`ClassNotFoundException` | Check runtime dependencies and loader |
| Static reflective scanner encounters a signature mismatch | `NoSuchMethodError`/`IllegalAccessError`/related | Check binary compatibility and JPMS access |
| Native library load inside a static block | `UnsatisfiedLinkError` | Check OS/architecture, native library path, and JNI symbols |
| Static code throws `AssertionError` | A direct `Error` | Handle the violated invariant; the first error may be AssertionError |
| Creating too many objects | `OutOfMemoryError` | Check memory demand/limits/leaks |
| Circular/cross-thread init order | NPE from partial state or deadlock | Refactor the static dependency graph |
| Superclass initialization failure | Error originating from `Parent.<clinit>` | Trace the earliest parent failure |
| Loader close races with a plugin callback | Error when needing to load an unloaded class/resource | Quiesce/drain before closing |

**If the issue is a class initialization deadlock**, you may not see EIIE or NCDFE at all, because the threads are **waiting on one another** without marking the class erroneous. Use a thread dump/JFR or `jcmd` on the live JVM to tell them apart.

## 10. Better Design: Do Not Let Transient I/O Break a Class

A risky pattern:

~~~java
public final class GatewayHolder {
    static final RemoteGateway CLIENT = RemoteGateway.connect();
}
~~~

This is only a snippet; `RemoteGateway` is an application-defined type. If `connect()` fails at first active use, `GatewayHolder` can remain erroneous **for the entire lifetime of the runtime class**.

A simpler instance API:

~~~java
public final class GatewayManager {
    private volatile RemoteGateway current;

    public synchronized RemoteGateway getOrCreate() {
        RemoteGateway existing = current;
        if (existing != null && existing.isHealthy()) {
            return existing;
        }

        RemoteGateway fresh = RemoteGateway.connect();
        current = fresh;
        return fresh;
    }
}
~~~

This is also a snippet and not yet a complete production solution: you still need to handle old resources, concurrency with close, timeouts, backoff, and a circuit breaker. It illustrates the core point: **the class can be initialized normally**, while the connection is created according to the service lifecycle and can perform bounded retries after transient failures.

Principles:

- Static fields should favor constants or immutable dependencies with reliable initialization.
- Configuration validation and I/O that can fail should be placed in an explicit factory or startup service.
- Do not publish a component that has failed a health check.
- Retries must be bounded, avoid infinite loops, and include appropriate logs/circuit breakers.
- For a class that is already erroneous in the application loader, restarting the JVM after fixing the configuration is usually the clearest option; do not use reflection/Unsafe to “force `<clinit>` to run again”.

## 11. Unit Tests, Plugins, and ServiceLoader

**Unit tests:** the first test may render a class erroneous within the same test JVM, and the second test fixes the mock/property yet still hits NCDFE. A good approach is to inject dependencies into instances and avoid stateful static initializers, or isolate tests using **JVM forks / fresh defining loaders** when initialization behavior itself is the subject under test.

**Plugins:** a new plugin version should be loaded through a new-generation loader, preserving shared API identity in the parent, checking version/health before publishing, draining old tasks, unregistering callback/DI/reflection caches, closing plugin resources, and then closing the old loader. Creating a new URLClassLoader object that still delegates the implementation class to the old parent **does not create a new runtime class**.

**ServiceLoader:** it may discover the provider properly, yet when the provider is instantiated, the provider's static initializer fails. Depending on the provider instantiation path, the caller may see a wrapped `ServiceConfigurationError`. Always inspect the underlying cause/first log before editing `META-INF/services`/module `provides`.

**Class unloading:** `URLClassLoader.close()` does not force already-loaded classes to unload. GC handles unloading when the defining loader becomes eligible for reclamation and the JVM decides to collect it. `System.gc()` is not an API for resetting static fields or init state.

## 12. Troubleshooting Checklist

- [ ] Determine whether the message says **`Could not initialize class`** or indicates another missing class/dependency error.
- [ ] Find the **first `ExceptionInInitializerError` or original `Error`** in the logs of the same JVM/classloader.
- [ ] Inspect the specific `<clinit>` method or static field initializer that threw the error.
- [ ] If a superclass/superinterface failed, analyze the chain before modifying the child.
- [ ] Record the Java version, startup command, classpath/module path, TCCL, and defining loader.
- [ ] Fix the config/secret/dependency/native path **first**.
- [ ] Do not retry an erroneous class in the same defining loader.
- [ ] Restart the JVM or create a **new loader + new runtime class** when re-initialization is needed.
- [ ] For plugins, do not publish a new generation until initialization and health checks succeed.
- [ ] Record the full root cause and test both success and failed-first-use paths.
- [ ] Do not use `System.gc()`, `close(loader)`, or `Class.forName(...false...)` expecting to reset state.
- [ ] When unit testing multiple test cases, avoid sharing a static initialization failure across tests.

## 13. Self-Check Questions

1. Can NCDFE occur after a static-init failure even though the class file is still in the JAR? **Yes**.
2. What is typically received on the first active use when `IllegalStateException` escapes an initializer? **ExceptionInInitializerError**.
3. What happens on the next attempt requiring initialization of the same runtime class? **NoClassDefFoundError**.
4. Does the initializer automatically re-run after fixing an env/property? **No**.
5. If the initializer throws `AssertionError` the first time, does the JVM always wrap it in EIIE? **No**, an Error can be thrown directly.
6. Is `ClassLoader.loadClass` an initialization command? **No**.
7. How does `Class.forName(name,true,loader)` differ from the false overload? **true requests initialization**.
8. Does reading `static final String X="abc"` necessarily trigger initialization? **No**, it may be a compile-time constant.
9. What about reading `static final int N=calculate()`? **It is not a constant variable**, so active use can trigger initialization.
10. If two threads initialize a Class concurrently, does `<clinit>` run twice? **No**, the JVM coordinates initialization.
11. Can a Parent class failure make a Child erroneous? **Yes**.
12. Does creating a new URLClassLoader always create a new Class? **No**, if it delegates to a parent that has already defined it.
13. Why does `System.gc()` not cure an erroneous class? **GC does not reset initialization state**.
14. What is required for recovery in a plugin? **Fix the root cause and use a new-generation loader that actually defines the new class**.
15. What is the fundamental difference between CNFE and NCDFE? **CNFE is a checked lookup failure; NCDFE is an Error during runtime/linking/init state**.
16. Which error is most important in the logs? **The first original error**, not just the final NCDFE.
17. Should you create a failure-prone DB connection inside `static {}`? **No**, lifecycle and retries should be managed in a service.
18. If a thread dies from a class-init error while the process stays alive, can another request receive NCDFE? **Yes**, the same runtime class is already erroneous.

## 14. Authoritative References

1. [JLS `12.4.1 — When Initialization Occurs](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.4.1): active use, constants.
2. [JLS `12.4.2 — Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.4.2): erroneous state, initialization locks, EIIE, and NCDFE.
3. [JVMS `5.5 — Initialization](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.5): runtime initialization procedure.
4. [ExceptionInInitializerError — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ExceptionInInitializerError.html): causal exception and hierarchy.
5. [NoClassDefFoundError — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/NoClassDefFoundError.html): runtime linkage error.
6. [ClassNotFoundException — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassNotFoundException.html): checked lookup failure.
7. [Class — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html): `forName` and initialize flag.
8. [ClassLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, delegation, class identity.
9. [URLClassLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/URLClassLoader.html): loader lifecycle/close.
10. [JLS `12.7 — Class Unloading](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.7): GC/defining loader eligibility.

**Remember:** The `NoClassDefFoundError: Could not initialize class X` error is usually the **consequence of a previously failed initialization**, not a missing `X.class`. Read the first exception/cause in `<clinit>`, fix the root cause, and then use a fresh JVM or a new defining ClassLoader when a new class is needed. Do not expect retrying the same erroneous class, modifying properties, or `System.gc()` to reset the state.
