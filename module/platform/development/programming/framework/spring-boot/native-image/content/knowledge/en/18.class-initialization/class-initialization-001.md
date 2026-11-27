# Distinguishing Class Loading, Class Linking, and Class Initialization

In Java, a class does not immediately go from a `.class` file to a usable object. The JVM performs three interrelated groups of tasks: **loading**, **linking**, and **initialization**. Understanding these three phases properly helps explain why a static initializer runs at a specific point in time, why `Class.forName` can trigger static code, and why GraalVM Native Image needs to decide which classes are initialized at build time and which are initialized when the application runs.

With Spring Boot Native Image, it is also necessary to distinguish Spring AOT from GraalVM's class initialization. Spring AOT analyzes the application context and generates code to assist startup; GraalVM Native Image performs reachability analysis, creates the executable, and may execute certain class initializers during image creation. These are different activities, even though both can take place during the build phase.

## 1. Three Phases in a Class's Lifecycle

According to the Java Virtual Machine model, the process by which a class or interface becomes ready for use consists of the following main phases:

1. **Loading:** locates the binary representation of a class/interface and creates the corresponding `Class` object in the JVM.
2. **Linking:** verifies the bytecode, prepares static data areas, and resolves symbolic references as needed.
3. **Initialization:** executes the class's initializers, including static field initializers and static initializer blocks.

Linking is commonly described as three sub-steps:

- **Verification:** checks whether the class file/bytecode is valid and conforms to the JVM's constraints.
- **Preparation:** allocates and assigns default values to static fields; assigning initial values according to static field initializers takes place during the initialization phase.
- **Resolution:** converts symbolic references in the constant pool into concrete references used by the JVM. The JVM may perform resolution eagerly or lazily when a reference is used, depending on the specification and implementation.

Overview diagram:

~~~mermaid
flowchart TD
    A["Class is requested for use"] --> B["Loading - load class"]
    B --> C["Linking - link"]
    C --> D["Verification"]
    D --> E["Preparation"]
    E --> F["Resolution"]
    F --> G["Initialization"]
    G --> H["Class is ready for active use"]
~~~

This diagram should not be understood as meaning that every symbolic reference must be resolved before the class is initialized. The JVM allows resolution to occur eagerly or lazily; what matters is that a linkage error must be detected when the program uses the corresponding reference path according to JVM rules.

## 2. Loading: How Does the JVM Find and Load a Class?

Loading is the process where the JVM finds bytecode or a suitable class representation, and then creates a `Class` object representing that type. Sources can be:

- The application's class output directory.
- JARs on the classpath/module path.
- The JDK runtime image and libraries.
- A custom source via a custom class loader.
- A byte array defined by a class loader via `defineClass`.

In a modern Java environment, common class loaders include:

| Class loader | General role |
| --- | --- |
| Bootstrap class loader | Loads core foundational Java classes |
| Platform class loader | Loads platform classes provided by the JDK |
| Application/System class loader | Loads application classes and libraries on the classpath/module path |
| Custom class loader | Loads classes according to rules defined by the application or framework |

The parent delegation mechanism is commonly used: a class loader asks its parent first, and only searches for the class itself if the parent does not find it. This is the standard rule, though a custom class loader may implement a different strategy.

### Class loading does not mean class initialization

You can ask the JVM to load a class without running its static initializer yet:

~~~java
ClassLoader loader = Thread.currentThread().getContextClassLoader();

Class<?> type = Class.forName(
        "com.example.nativeimage.ReportFormatter",
        false,
        loader
);
~~~

The `false` argument requests not to initialize the class in this `Class.forName` call. The class can be loaded and linked as needed, but the static initializer is not triggered by that call alone.

Another common approach:

~~~java
Class<?> type = ReportFormatter.class;
~~~

A class literal obtains the `Class` object of the type. It may cause the class to be loaded, but a class literal itself is **not an active use that triggers class initialization** under Java rules.

Conversely, `Class.forName("com.example.nativeimage.ReportFormatter")` using the single-argument overload behaves equivalently to requesting class initialization (`initialize = true`) if the class has not been initialized yet.

## 3. Linking: Verification, Preparation, and Resolution

### Verification — verifying bytecode

The JVM checks the class file and type relationships to ensure the bytecode does not violate rules required for execution. For example, bytecode must have appropriate operand types, must not misuse the stack structure, and type accesses must be valid.

If a class fails verification, the JVM may throw `VerifyError`. This is a linkage error, not a logic error inside a static initializer.

### Preparation — preparing static fields

During preparation, the JVM allocates the necessary memory space for static fields and assigns **type-based default values**:

~~~java
public class InitializationExample {

    static int count = 42;
    static boolean enabled = true;
    static String label = "ready";
}
~~~

In the preparation step, static fields initially hold their default values:

- `count` is `0`.
- `enabled` is `false`.
- `label` is `null`.

The expressions `42`, `true`, and `"ready"` are processed during the initialization phase, except for compile-time constant variables which follow special rules and can be inlined by the compiler at call sites.

Preparation does not run object constructors and does not run static initializer blocks either.

### Resolution — resolving symbolic references

Bytecode typically references classes, methods, and fields using symbolic references. Resolution turns those references into concrete access targets used by the runtime.

For example, when a class calls `repository.findById(...)`, the bytecode contains references to the type and method. The JVM needs to identify the corresponding method and check the relevant access/type rules.

If the required class or method is not found, errors may appear as `NoClassDefFoundError`, `NoSuchMethodError`, `NoSuchFieldError`, or other linkage errors. Because resolution can be lazy, an application sometimes only encounters an error when entering a rarely used code branch.

## 4. Initialization: When Does a Static Initializer Run?

Initialization is the phase where the JVM executes a class's static initialization. The main components include:

- Static field initializers that are not compile-time constants.
- Static initializer blocks.
- Operations executed in the order they appear in the class declaration.

Example:

~~~java
public class StartupSettings {

    static String mode = readMode();

    static {
        System.out.println("Static block: mode=" + mode);
    }

    static int retryCount = 3;

    private static String readMode() {
        System.out.println("Reading mode");
        return "safe";
    }
}
~~~

When the class is initialized, static field initializers and static blocks run in source declaration order. With the example above, the output in order is:

~~~text
Reading mode
Static block: mode=safe
~~~

The field `retryCount` receives the value `3` during the same initialization process after the preceding static block has run.

### Active use — actions that trigger initialization

Under Java rules, a class is generally initialized immediately before the first occurrence of one of the following active use scenarios:

1. Creating an instance of the class with `new`.
2. Calling a static method declared by the class.
3. Assigning to or reading a static field declared by the class, if that field is not a compile-time constant.
4. Certain reflection operations that require class initialization, such as `Class.forName(name)` with the default `initialize = true` overload.

Example:

~~~java
public class LazyHolder {

    static {
        System.out.println("LazyHolder initialized");
    }

    static void run() {
        System.out.println("run");
    }

    static final int CONSTANT = 10;
    static int counter = 0;
}
~~~

The following actions have different effects:

~~~java
Class<?> type = LazyHolder.class;
// Class literal does not trigger initialization by itself.

int value = LazyHolder.CONSTANT;
// Compile-time constant can be inlined; no need to initialize LazyHolder.

int current = LazyHolder.counter;
// Reading a non-compile-time constant static field: triggers initialization.

LazyHolder.run();
// Calling a static method: the class is initialized before the method runs.
~~~

### Compile-time constants are an important exception

A constant variable is a `final` variable of primitive type or `String`, initialized with a constant expression as defined by Java. Example:

~~~java
public class BuildConstants {
    public static final int DEFAULT_PORT = 8080;
    public static final String SERVICE = "billing";
}
~~~

The compiler can inline the values of these variables into the bytecode where they are used. Simply reading `BuildConstants.DEFAULT_PORT` or `BuildConstants.SERVICE` does not necessarily trigger initialization of `BuildConstants`.

Conversely, the following field is not a compile-time constant:

~~~java
public static final String MODE = System.getenv("APP_MODE");
~~~

Its value depends on a method call at runtime, so it is not a constant expression. Reading this field can trigger class initialization.

## 5. Initialization Order of Classes, Superclasses, and Interfaces

When a class is initialized for the first time, the JVM must process inheritance relationships before running the initializer of that class.

Example:

~~~java
class Parent {
    static {
        System.out.println("Parent initialized");
    }
}

class Child extends Parent {
    static {
        System.out.println("Child initialized");
    }
}
~~~

Using `Child` for the first time in a way that triggers initialization will initialize `Parent` first, followed by `Child`:

~~~text
Parent initialized
Child initialized
~~~

This rule prevents a subclass from running static initialization before the superclass it depends on.

### Interfaces have different rules from classes

Initializing an interface **does not automatically initialize its superinterfaces** solely because of interface inheritance. This differs from initializing classes and superclasses.

When initializing a class, the JVM must also initialize any superinterfaces of that class that declare default methods, in an order consistent with the interface hierarchy. The purpose is to ensure that default methods can be used with initialized static state.

Example:

~~~java
interface HasDefaultAction {
    int VERSION = initializeVersion();

    static int initializeVersion() {
        System.out.println("HasDefaultAction initialized");
        return 1;
    }

    default void execute() {
    }
}

class ActionService implements HasDefaultAction {
    static {
        System.out.println("ActionService initialized");
    }
}
~~~

When `ActionService` is initialized, because the `HasDefaultAction` interface has a default method, it is initialized before the class. If an interface does not declare a default method, initializing an implementing class does not necessarily trigger initialization of that interface.

## 6. Class Initialization Is Thread-Safe and Runs Only Once

The JVM synchronizes the initialization process for each class/interface. If multiple threads use a class for the first time concurrently:

- One thread executes the initializer.
- Other threads needing that class must wait for the initialization process to complete.
- Once initialization succeeds, subsequent threads use the initialized state.
- The JVM does not re-run the static initializer on every static method call or instance creation.

This mechanism ensures that static initialization is not executed concurrently multiple times within the same class loader.

However, static initializers should not perform heavy work or uncontrolled waiting. If an initializer invokes code that creates a circular wait between threads, accesses external systems, or prolongs startup, all threads requiring that class may be affected.

### Initialization failure

If a static initializer throws an exception:

- If the exception is not an `Error`, the JVM typically wraps it in `ExceptionInInitializerError`.
- The class is marked as having failed initialization (erroneous) in that class loader.
- Subsequent active uses may encounter `NoClassDefFoundError` instead of retrying the initializer.

Example:

~~~java
public class BrokenSettings {

    static {
        if (System.getenv("REQUIRED_SECRET") == null) {
            throw new IllegalStateException("Missing REQUIRED_SECRET");
        }
    }
}
~~~

If the environment variable is missing when the class is initialized, that class cannot be treated as uninitialized to be retried after the environment variable is added. A better design is to read configuration according to the application lifecycle, validate it at an appropriate time, and report configuration errors clearly.

## 7. Distinguishing Class Initialization from Spring Bean Initialization

Spring Boot has its own bean lifecycle. It should not be equated with JVM class initialization.

| Concept | Scope | Example |
| --- | --- | --- |
| Class loading | JVM | Loading `PaymentService.class` |
| Class initialization | JVM | Running `static { ... }` of `PaymentService` |
| Object construction | Java object | Calling `new PaymentService(...)` |
| Bean creation | Spring container | Instantiating object, injecting dependencies, applying BeanPostProcessors |
| Bean initialization callbacks | Spring lifecycle | `@PostConstruct`, `InitializingBean`, init method |
| Spring AOT | Build-time processing | Analyzing context and generating bean registration/initialization code |
| Native Image class initialization | GraalVM build/runtime policy | Choosing which static initializers run during image creation and which run when the executable operates |

Example:

~~~java
@Service
public class PaymentService {

    static {
        System.out.println("Class initialized");
    }

    public PaymentService() {
        System.out.println("Object constructed");
    }

    @PostConstruct
    void initializeBean() {
        System.out.println("Spring bean initialized");
    }
}
~~~

The three log lines represent three distinct events:

1. The JVM initializes the `PaymentService` class and runs the static block.
2. Spring creates an instance via the constructor.
3. Spring executes the bean initialization callback after dependency injection according to the lifecycle.

A class can be initialized before Spring creates its bean instance. A class can also be used to create objects not managed by Spring; in that case, class initialization still occurs, while the Spring bean lifecycle does not.

## 8. When Do Spring AOT and GraalVM Handle Class Initialization?

In the Spring Boot Native Image workflow, there are at least two build-time processes to distinguish:

### Spring AOT processing

Spring AOT analyzes the application context to identify bean definitions, the dependency graph, configuration, and contributions from the framework. It generates context initialization code and runtime hints for native compilation.

During analysis, Spring may need to instantiate or invoke certain infrastructure components to process configuration. Therefore, static initializers or code of some beans/processors may execute inside the AOT process running on the JVM. This **does not mean** that the static state of every class is packaged into the native executable.

### GraalVM Native Image build

Native Image performs reachability analysis and applies class initialization policies. Depending on the class and configuration, GraalVM can:

- Initialize the class during image creation (build-time initialization).
- Defer class initialization until the native executable runs (run-time initialization).

When a class is initialized at build time, the corresponding static state can be stored in the image heap and become the initial state of the executable. When a class is configured to initialize at runtime, the initializer will run in the native process according to runtime initialization rules.

~~~mermaid
flowchart TD
    S["Source + dependencies"] --> A["Spring AOT on JVM"]
    A --> G["Generated code + runtime hints"]
    G --> N["GraalVM Native Image analysis"]
    N --> P{"Class initialization policy"}
    P -->|"Build time"| B["Run initializer during image build"]
    B --> H["Store static state in image heap"]
    P -->|"Run time"| R["Leave initializer for native process"]
    H --> X["Native executable"]
    R --> X
    X --> U["Application uses class"]
~~~

The two build phases may execute static initializers in two different processes and contexts. Do not assume a side effect occurring in the Spring AOT JVM will automatically become static state in the native image. Identify accurately from logs which phase an initializer runs in.

## 9. Build-Time Initialization and Run-Time Initialization in Native Image

### Build-time initialization

When GraalVM initializes a class at build time, static fields and related state can be placed into the image heap. This can reduce the work required when the application starts up.

For example, a class containing only an immutable data table, deterministically built from constants in the source, may be suitable for early initialization:

~~~java
public final class CurrencyTable {

    static final Map<String, Integer> FRACTIONS = Map.of(
            "USD", 2,
            "JPY", 0,
            "VND", 0
    );

    private CurrencyTable() {
    }
}
~~~

If an initializer only constructs deterministic data and does not depend on the runtime environment, build-time initialization can be a reasonable choice. However, image heap cost and compatibility with the GraalVM version should be checked.

### Run-time initialization

A class should be initialized at runtime if its static initializer depends on the state of the execution environment:

~~~java
public final class RuntimeSettings {

    static final String APP_MODE =
            System.getenv().getOrDefault("APP_MODE", "default");

    static final long STARTED_AT = System.currentTimeMillis();

    private RuntimeSettings() {
    }
}
~~~

If this class is initialized at build time, the environment value and timestamp from the build machine may get baked into the image heap. When the native executable runs in a different container, it will not automatically recompute those values.

Signs that typically require runtime initialization:

- Reading environment variables or system properties.
- Getting the current time or generating random values.
- Creating threads, executors, or schedulers.
- Opening files/sockets or initializing native resources.
- Detecting hostname, network interfaces, or machine configuration.
- Accessing secrets, credentials, or paths that only exist in the runtime container.

Even better, many values do not need static fields at all. They can be read via constructor injection, `@ConfigurationProperties`, or a service with a clear lifecycle. That way, the application does not have to rely on class initialization timing to obtain runtime configuration.

## 10. Configuring GraalVM Class Initialization

GraalVM Native Image provides options to control when classes are initialized. Two common options are:

- `--initialize-at-build-time=<class-or-package>`: requests that the specified classes be initialized during image build.
- `--initialize-at-run-time=<class-or-package>`: defers initialization of the specified classes to runtime.

Example requesting `RuntimeSettings` to be initialized when the native executable runs:

~~~text
--initialize-at-run-time=com.example.nativeimage.RuntimeSettings
~~~

This example only illustrates the class name. Replace it with the actual class and check the options for the Native Image version in use.

### Maven Native Build Tools

Arguments can be added to the `native-maven-plugin` configuration:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>--initialize-at-run-time=com.example.nativeimage.RuntimeSettings</buildArg>
        </buildArgs>
    </configuration>
</plugin>
~~~

If the project already has plugin configuration in a parent POM or native profile, add the argument to the existing configuration to avoid duplicate plugin declarations. Check the logs to confirm the argument is passed to Native Image.

### Gradle Native Build Tools

Groovy DSL example:

~~~groovy
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add(
                "--initialize-at-run-time=com.example.nativeimage.RuntimeSettings"
            )
        }
    }
}
~~~

The DSL API and binary names may vary by plugin version. For Kotlin DSL, use the corresponding typed properties/APIs of the installed version.

### Should you force an entire package to initialize at build time?

You should not apply `--initialize-at-build-time` to the entire application just to reduce startup time. Doing so can cause library static initializers to run on the build machine and freeze inappropriate state into the image. Start from the toolchain's default policy, read warnings/traces, and only adjust classes with a clear reason.

A class may depend on a superclass or other components; changing the initialization policy requires considering dependency relationships as well. Native Image may reject an inconsistent configuration or require adjusting additional related classes.

## 11. Example of Bugs Caused by Static State Frozen at Build Time

Suppose an application needs to select an endpoint based on the environment:

~~~java
public final class ApiEndpoint {

    static final String BASE_URL =
            System.getenv().getOrDefault(
                    "PARTNER_API_URL",
                    "https://sandbox.example.test"
            );

    private ApiEndpoint() {
    }
}
~~~

If `ApiEndpoint` is initialized during the native-image build, `BASE_URL` may retain the value from the build environment. When running the production container with `PARTNER_API_URL=https://api.partner.example`, the application may still use the sandbox URL stored in the image heap.

A better fix is to move configuration into a runtime bean:

~~~java
@ConfigurationProperties(prefix = "partner.api")
public record PartnerApiProperties(URI baseUrl) {
}
~~~

~~~java
@Service
public class PartnerClient {

    private final PartnerApiProperties properties;

    public PartnerClient(PartnerApiProperties properties) {
        this.properties = properties;
    }

    public URI baseUrl() {
        return properties.baseUrl();
    }
}
~~~

With runtime configuration:

~~~yaml
partner:
  api:
    base-url: https://api.partner.example
~~~

The Spring Binder receives the value when the application runs and injects it into the bean. If the deployment environment changes, a different property can be supplied without freezing the endpoint in a static initializer.

If you cannot change a library's design and the class must read runtime state in a static initializer, consider `--initialize-at-run-time` for that class. First, however, evaluate moving the logic out of the static initializer, as that approach is usually easier to test and operate.

## 12. Diagnosing Class Initialization in Native Image

The following symptoms often help isolate the problem:

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Environment values in native differ from container | Static field initialized at build time | Inspect initializers, traces, and runtime initialization policy |
| Native build reports invalid class initialization | Initializer performs an operation unsupported in the hosted/build-time context | Identify the offending class and check whether initialization should be deferred |
| Native startup is unexpectedly slow | Many classes perform heavy work during runtime initialization | Measure startup, inspect traces, and assess whether classes can be safely initialized at build time |
| Works on JVM but native fails when using a class | Difference in initialization policy or class dependencies | Read the exception and class initialization trace |
| `ExceptionInInitializerError` error | Static initializer throws an exception on first run | Find the root cause exception in the static block/field initializer |
| Subsequent uses report `NoClassDefFoundError` | Class was marked erroneous after a failed initialization | Start a fresh process after fixing the root cause |
| Timestamp/random values remain identical across binary runs | Value was computed at build time and stored in the image heap | Inspect static initializers and move to runtime |
| Errors from threads or sockets created in an initializer | Build-time initialization attempts to create OS/process-bound resources | Defer initialization or move resource creation into the runtime lifecycle |

### Tracing class initialization

GraalVM Native Image provides a class initialization trace option in supported versions, typically used as:

~~~text
--trace-class-initialization=com.example.nativeimage.RuntimeSettings
~~~

This option lets you observe when and from where a class is initialized. Exact option names/formats may vary across GraalVM releases; verify with `native-image --help` or the documentation for your exact version.

When investigating:

1. Identify classes with notable static field initializers or static blocks.
2. Check logs/traces to see whether the class is initialized at build time or runtime.
3. Verify whether static values depend on the build machine's environment, time, randomness, or resources.
4. If the class requires the runtime environment, move the logic out of the static initializer or apply an appropriate runtime initialization policy.
5. Rebuild the executable and test in a container with different configuration from the build machine.
6. Run tests multiple times and verify static state is not unintentionally persisted.

Do not fix class initialization errors by mechanically adding reflection hints. Reflection metadata and class initialization are two separate mechanisms.

## 13. Hands-on Exercise: Observing the Three Phases and Static Initializer Timing

Create a small Spring Boot project with an `InitializationProbe` class:

~~~java
package com.example.nativeimage;

public final class InitializationProbe {

    static final String BUILD_MARKER = "probe-v1";

    static final String APP_MODE =
            System.getenv().getOrDefault("APP_MODE", "default");

    static {
        System.out.println("InitializationProbe initialized: " + APP_MODE);
    }

    private InitializationProbe() {
    }

    public static String appMode() {
        return APP_MODE;
    }
}
~~~

Create a service that uses this class:

~~~java
@Service
public class ProbeService {

    public String appMode() {
        return InitializationProbe.appMode();
    }
}
~~~

Perform the following steps:

1. Use `InitializationProbe.class` to get the class literal and observe that the static initializer does not necessarily run during this operation.
2. Use `Class.forName("com.example.nativeimage.InitializationProbe", false, loader)` and verify the class has not undergone active use to initialize.
3. Call `InitializationProbe.appMode()` and observe that the static initializer runs before the first invocation.
4. Run the JVM application with `APP_MODE=dev`, then change to `APP_MODE=prod` in a new process and compare.
5. Build the native executable; if needed, configure this class for runtime initialization with `--initialize-at-run-time`.
6. Run the binary with `APP_MODE=prod`, verifying the value is read from the runtime container.
7. Use GraalVM's class initialization trace to see which phase initializes the class.
8. Compare with a class that only builds immutable data from constants and consider whether build-time initialization is appropriate.

### Self-Check Questions

1. How do loading, linking, and initialization differ?
2. What parts of linking are verification, preparation, and resolution?
3. Why does preparation assign default values to static fields before initializers run?
4. Why does reading a compile-time constant not necessarily initialize a class?
5. Why can initializing a subclass trigger initialization of its superclass and certain superinterfaces?
6. Why is class initialization synchronized by the JVM?
7. How can `ExceptionInInitializerError` and `NoClassDefFoundError` be related?
8. How does Spring AOT processing differ from GraalVM build-time class initialization?
9. When should `--initialize-at-run-time` be used?
10. Why can reading environment variables in a static initializer cause issues when building a native image?

**Completion criteria:** be able to explain loading, linking, and initialization in the JVM lifecycle; identify active uses and compile-time constants; accurately describe superclass/interface ordering, thread safety, and initialization errors; distinguish class initialization from the Spring bean lifecycle/AOT; and select and verify appropriate build-time or run-time initialization when building a GraalVM Native Image.
