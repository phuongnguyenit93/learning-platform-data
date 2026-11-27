# Prefer Narrow-Scope Fixes Over Imposing One Mode on All Classes

## 1. Why Does Class Initialization Need Adjustment?

In the **SPRING_BOOT_NATIVE_IMAGE** module, Spring Boot applications are processed with **Spring AOT** and compiled into GraalVM Native Image to evaluate startup time, memory usage, and compatibility. A critical decision when building a native executable is **when each class's class initializer runs**:

- **Build time:** the static initializer executes in the native-image build process. Static values are recorded into the image heap and become the initial state of the executable.
- **Runtime:** the static initializer executes when the class is first used in the native application.

Native Image can initialize early certain classes that the tool proves are safe. By default, remaining application classes are generally initialized at runtime to keep behavior close to the JVM. When optimization or compatibility fixes are needed, you can specify an explicit scope using:

- `--initialize-at-build-time=<class-or-package>`
- `--initialize-at-run-time=<class-or-package>`

The key takeaway is that **a specific class may need a different policy from the rest of the application**. Find the exact class with an unsuitable static initializer, determine what data that initializer produces, and adjust the smallest scope possible. Applying one mode across the entire classpath can alter the behavior of libraries that are already working properly.

## 2. When Does Class Initialization Occur?

According to Java semantics, a class is initialized when first used under JVM conditions. Loading a class does not mean running its static initializer. A static initializer is typically compiled into the special method `<clinit>`.

Example:

~~~java
public final class RegionSettings {

    static final String REGION = System.getenv("APP_REGION");

    static {
        System.out.println("RegionSettings initialized");
    }

    private RegionSettings() {
    }
}
~~~

When the class is initialized, the JVM reads the environment variable and runs the static block. If Native Image decides or is instructed to initialize this class at build time, the `APP_REGION` value is read from the build machine's environment and static state is saved in the image heap.

If the class is initialized at runtime, the static initializer executes inside the native process's environment when the class is first used. Consequently, deployment environment changes can be reflected accurately.

### 2.1. Build time vs. runtime in Native Image

~~~mermaid
flowchart TB
    S["Java bytecode + dependencies"] --> A["Native Image analyzes class initialization"]
    A --> B{"When is the class initialized?"}
    B -->|Build time| C["Run <clinit> in image builder"]
    C --> D["Write static state to image heap"]
    D --> E["Native executable contains initial state"]
    B -->|Runtime| F["Include class initializer in executable"]
    F --> G["Run <clinit> on first class use"]
    E --> H["Native application runs"]
    G --> H
~~~

When a class is initialized at build time, objects reachable from that class's static fields are stored in the image heap. When the executable starts, the initial image heap serves as the application's starting state.

This can reduce initialization work and class-state checks at runtime. However, if the initializer creates many objects or large data structures, the image heap and binary size may grow. Benefits must be measured on the real application.

## 3. Distinguishing Spring AOT from Class Initialization

These two concepts appear in the same pipeline yet solve two different tasks:

| Concept | What does it do? | Examples |
| --- | --- | --- |
| Spring AOT | Analyzes ApplicationContext and generates code/metadata for startup, binding, and native image | Generates bean registration code, runtime hints |
| Class initialization | Decides when each Java class's static initializer runs | `--initialize-at-build-time`, `--initialize-at-run-time` |
| Native Image compilation | Analyzes bytecode, metadata, and creates executable | `nativeCompile`, `native:compile` |

Spring AOT does not mean every static initializer in the application runs at build time. Conversely, simply adding `--initialize-at-build-time` does not replace the Spring AOT step.

When investigating an error, determine whether the failure lies in ApplicationContext/AOT creation or inside a class's `<clinit>`. Do not alter class initialization policies merely to mask a bean registration or Spring configuration bug.

## 4. Which Classes Suit Build-Time Initialization?

Build-time initialization is appropriate when a static initializer:

- only performs deterministic calculations from fixed data;
- creates small, shared, immutable data structures;
- does not read the build machine's environment;
- does not depend on time, locale, timezone, filesystem, or external services;
- does not create security state or random state that must be distinct per run.

Example of an immutable lookup table:

~~~java
import java.util.Map;

public final class CurrencyCatalog {

    static final Map<String, Integer> FRACTION_DIGITS = Map.of(
        "VND", 0,
        "USD", 2,
        "EUR", 2,
        "JPY", 0
    );

    private CurrencyCatalog() {
    }

    public static int fractionDigits(String currency) {
        return FRACTION_DIGITS.getOrDefault(currency, 2);
    }
}
~~~

This table is constructed entirely from fixed data, and `Map.of` produces an unmodifiable map. If the class is initialized at build time, the lookup table is ready in the image heap and does not need rebuilding when the application starts.

You can specify a single class:

~~~bash
native-image \
  --initialize-at-build-time=com.example.billing.CurrencyCatalog \
  -jar target/billing-service.jar
~~~

There is no need to specify the entire `com.example.billing` package if only `CurrencyCatalog` has a suitable initializer. If the package also contains classes reading databases, locales, or runtime configuration, package scope would be too broad.

## 5. Which Classes Should Initialize at Runtime?

Keep class initialization at runtime if a static initializer depends on data meaningful only in the running environment or creates state that must be fresh per process.

Common examples:

| Content in static initializer | Why runtime is required? |
| --- | --- |
| Reading `System.getenv()` or `System.getProperty()` | Each deployment environment has different values |
| Getting `ZoneId.systemDefault()` or `Locale.getDefault()` | Depends on OS configuration in the running environment |
| Reading files, temp directories, or path variables | Build machine and runtime container have different filesystems |
| Creating `SecureRandom` or random seeds | Random state must not be captured from the build environment |
| Initializing crypto providers or native libraries | May depend on platform, provider, and runtime environment |
| Creating threads, executors, or thread-local state | These are resources of the running process |
| Opening sockets, database connections, or making HTTP calls | Must not execute inside the image builder |
| Reading credentials or secrets | Risks storing sensitive data in the image heap/binary |

Example class reading the deployment region:

~~~java
public final class RegionSettings {

    static final String REGION = System.getenv("APP_REGION");

    private RegionSettings() {
    }

    public static String region() {
        return REGION;
    }
}
~~~

If the class above is initialized at build time, the build machine's region value can remain baked into the binary. You can instruct this class to initialize at runtime:

~~~bash
native-image \
  --initialize-at-run-time=com.example.runtime.RegionSettings \
  -jar target/billing-service.jar
~~~

Even better, if data is inherently application configuration such as region, endpoint, or timeout, consider placing it into Spring `@ConfigurationProperties` and injecting it into beans at runtime. Avoid using static mutable state as a global configuration store.

## 6. Why Avoid Applying One Mode to the Entire Classpath?

### 6.1. Forcing everything to build-time initialization

A global build-time option can cause third-party library static initializers to execute on the build machine. When that happens:

- the build machine's environment, timezone, or system properties can be written into the image heap;
- random seeds, credentials, or system info can be retained in the binary;
- initializers may open files, spawn threads, or perform operations incompatible with the image builder;
- large precomputed data structures can bloat the image heap;
- libraries making runtime assumptions can misbehave or cause the build to fail.

Native Image analyzes automatically to build-time initialize classes proven safe. Do not replace that mechanism with a rule forcing the entire classpath.

### 6.2. Forcing everything to runtime initialization

Conversely, forcing every class to runtime can:

- increase the number of class initializers that must run when the application first uses classes;
- increase the cost of class initialization checks before accessing static fields/methods;
- miss opportunities to pre-prepare immutable lookup tables and data structures;
- conflict with objects already instantiated in the image heap if an object belongs to a class forced to runtime initialization.

Runtime initialization also carries a constraint: **no instance of a class requiring runtime initialization may already exist in the image heap**, because that instance would exist before the class is initialized under Java semantics.

### 6.3. Choosing the scope

| Situation | How to handle |
| --- | --- |
| One class reads environment in its static initializer | Move only that class to runtime or move config reading into a bean/runtime accessor |
| One class builds an immutable lookup table from fixed data | Consider build-time for that exact class |
| A package contains multiple different kinds of classes | Do not apply a policy to the whole package; isolate the class needing adjustment |
| Failure originates from a third-party library | Identify the specific class initializer and consult the library's compatibility guide |
| Unknown which classes run at build time | Enable class initialization diagnostics and trace the specific class |

## 7. Configuring by Class or Package

Native Image provides two primary options:

~~~bash
--initialize-at-build-time=com.example.catalog.CurrencyCatalog
--initialize-at-run-time=com.example.runtime.RegionSettings
~~~

Multiple classes can be specified via a comma-separated list:

~~~bash
--initialize-at-run-time=com.example.runtime.RegionSettings,com.example.crypto.ProviderBootstrap
~~~

Packages can also be specified:

~~~bash
--initialize-at-run-time=com.example.legacy
~~~

A package policy applies more broadly and can include new classes added to that package in the future. A new class with a different static initializer could inadvertently receive an inappropriate policy. Therefore, prefer specific classes; use package scope only when the entire package shares the same requirement and has been audited.

### 7.1. Class hierarchy constraints

Java class initialization is affected by superclasses and interfaces with default methods:

- When a class is initialized, relevant superclasses and superinterfaces with default methods must be initialized under Java rules.
- Relevant supertypes of a build-time initialized class must also be build-time initialized.
- Relevant subtypes of a runtime-initialized class must also be runtime-initialized.
- A class required to initialize at runtime must not have any instances in the image heap.

Consequently, a policy change for one class may cause Native Image to require adjusting additional related classes. Read the build messages and handle according to the actual hierarchy; do not widen the policy to an entire package just to make error messages disappear.

## 8. Spring Boot Example: Separating Fixed Data from Runtime Configuration

Suppose an application has a currency code lookup table and region configuration:

~~~java
public final class CurrencyCatalog {
    static final Map<String, Integer> FRACTION_DIGITS = Map.of(
        "VND", 0,
        "USD", 2,
        "EUR", 2
    );

    private CurrencyCatalog() {
    }
}
~~~

This is fixed data and may be suitable for build-time initialization if it has no other runtime dependencies.

For region, prefer Spring configuration:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.region")
public record RegionProperties(String name) {
}
~~~

Register the properties using `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, then inject into beans that need it. The value can be supplied at runtime:

~~~yaml
app:
  region:
    name: ap-southeast-1
~~~

In another environment, override via an environment variable:

~~~bash
APP_REGION_NAME=ap-southeast-2 ./target/billing-service
~~~

There is no need to force `RegionProperties` or the entire configuration package to build time. The Spring Binder reads property sources when the native application starts; class initialization policy is a separate mechanism.

## 9. Placing Policies into Maven and Gradle

### 9.1. Maven Native Build Tools

Native Image arguments can be passed via the `native-maven-plugin` plugin configuration. Example:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>--initialize-at-run-time=com.example.runtime.RegionSettings</buildArg>
            <buildArg>--initialize-at-build-time=com.example.catalog.CurrencyCatalog</buildArg>
        </buildArgs>
    </configuration>
</plugin>
~~~

Place the configuration in the application module that builds the native executable. If the project uses Spring Boot Parent or an internal parent POM, check the effective POM to avoid duplicate declarations or overrides from parent configuration. Plugin names and DSLs may vary by version; consult your active Native Build Tools version.

### 9.2. Gradle Native Build Tools

Kotlin DSL example in `build.gradle.kts`:

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add(
                "--initialize-at-run-time=com.example.runtime.RegionSettings"
            )
            buildArgs.add(
                "--initialize-at-build-time=com.example.catalog.CurrencyCatalog"
            )
        }
    }
}
~~~

Arguments are attached to the `main` binary. With Groovy DSL or other plugin versions, container syntax may vary; verify the project's plugin configuration before copying this snippet verbatim.

After changing policies, you must rebuild the native executable. Merely changing environment variables when running the binary cannot alter class initialization policies already compiled into the executable.

## 10. Diagnosing Class Initialization

When a build fails or the application behaves differently from the JVM, do not guess which class needs a policy change. Gather evidence first.

### 10.1. Printing class initialization lists and reasons

Diagnostics can be enabled:

~~~bash
native-image -H:+PrintClassInitialization -jar target/billing-service.jar
~~~

Depending on the GraalVM version, this option prints information about classes initialized at build time and their associated reasons/categories. Output can be long; filter by the package or class under investigation. Verify options on your installed GraalVM via `native-image --help-extra` or `native-image --expert-options`.

### 10.2. Tracing a specific class

If a class is suspected:

~~~bash
native-image \
  --trace-class-initialization=com.example.runtime.RegionSettings \
  -jar target/billing-service.jar
~~~

Tracing helps identify where the class is initialized during the build. Options and detail levels may differ by GraalVM version; check `native-image --help`/`--help-extra` if the installed release does not recognize the flag.

### 10.3. Reading the static initializer

Once the class is identified:

1. Open the class's static field initializers and static blocks.
2. Follow methods invoked directly or indirectly.
3. Look for reads of environment variables, system properties, files, clock, locale, timezone, randomness, or system resources.
4. Check whether created objects can enter the image heap.
5. Check superclasses, interfaces with default methods, and related subtypes.
6. Choose the smallest policy and rebuild.

Not every `UnsupportedFeatureError` is a class initialization error. If an error involves reflection, JNI, resources, or proxies, fix the appropriate metadata instead of changing class policies.

## 11. Narrow-Scope Troubleshooting Workflow

Suppose the native image shows `RegionSettings` was initialized at build time and the executable always uses the CI machine's region.

**Step 1 — confirm the cause**

Inspect the static initializer:

~~~java
static final String REGION = System.getenv("APP_REGION");
~~~

This is an environment value captured when the class is initialized.

**Step 2 — prefer fixing the design**

If this is application configuration, move it to Spring `@ConfigurationProperties` and inject the bean. If a static API is required for compatibility reasons, at least read the value inside a method called at runtime rather than storing it in a static initializer:

~~~java
public final class RegionSettings {
    private RegionSettings() {
    }

    public static String region() {
        return System.getenv("APP_REGION");
    }
}
~~~

**Step 3 — if code cannot be modified yet, specify runtime for that class**

~~~bash
native-image \
  --initialize-at-run-time=com.example.runtime.RegionSettings \
  -jar target/billing-service.jar
~~~

Do not move the entire `com.example` package to runtime just because one class reads the environment.

**Step 4 — test using an environment different from the build machine**

Build the image with one `APP_REGION` value, then run the executable with a different value. The result must reflect the desired runtime configuration.

**Step 5 — re-measure**

Compare startup, RSS, build duration, and business flow behavior before and after the change. Runtime initialization may add cost on first use of the class; verify whether that cost matters for the application.

## 12. Testing Class Initialization

A test suite should verify both correctness and performance impact:

| Test | How to run | What to verify |
| --- | --- | --- |
| Environment isolation | Build with env var A, run with B | Binary does not retain A if data must be read at runtime |
| Timezone/locale | Build and run with different timezones/locales | Result follows the running environment when business logic requires runtime |
| Static immutable data | Compare lookup results on JVM and native | Fixed data matches identically |
| Randomness/security | Launch multiple native processes | Seeds/security state are created at the right time and not shared from build |
| External resources | Run in a container with runtime filesystem/network | No unintended I/O occurs at build time |
| Class hierarchy | Build after changing one class's policy | No superclass/subtype or image heap constraint violations |
| Startup/footprint | Measure identical workload before and after | Policy change yields measurable benefit without errors |

Test the executable in at least two distinct configuration environments. JVM tests alone cannot verify which static state was captured into the image heap.

## 13. Common Errors

| Symptom | Possible cause | How to resolve |
| --- | --- | --- |
| Native always uses CI environment value | Class containing `System.getenv()` initialized at build time | Move config reading to runtime or designate that class with `--initialize-at-run-time` |
| Build fails when forcing package build-time | Some class in the package performs an unsafe operation | Identify the specific class; drop the package policy and configure per class |
| Image heap contains instance of runtime class | An object of a runtime class was created at build time | Find the instantiation path, move creation to runtime, or adjust related policies |
| Class policy affected by superclass | Java class initialization constraints | Inspect relevant supertypes and adjust related scope |
| Native starts slower after moving many classes to runtime | Many initializers and class-state checks run at runtime | Narrow the runtime list, keeping only classes needing runtime environment |
| Larger binary after enabling build-time | Initializer creates many objects stored in image heap | Narrow classes, reduce static data, or initialize large data at runtime |
| Diagnostic option unrecognized | Differences between GraalVM versions | Check `native-image --help`, `--help-extra`, and version-specific docs |
| Spring AOT still fails after changing class policy | Error belongs to ApplicationContext/AOT rather than `<clinit>` | Inspect bean conditions, generated code, and runtime hints |

## 14. Pre-Release Checklist

- [ ] Identified problematic class initializers via logs/traces, not by guessing at the package level.
- [ ] Read the class's static initializer and indirect calls.
- [ ] Distinguished fixed data from runtime-environment-dependent data.
- [ ] Kept credentials, random seeds, and system data out of the image heap at build time.
- [ ] Used `--initialize-at-build-time` only for classes with deterministic, safe initializers needing optimization.
- [ ] Used `--initialize-at-run-time` only for classes requiring runtime state.
- [ ] Avoided applying broad package policies when only one class needed changing.
- [ ] Verified superclass/subtype constraints and image heap objects.
- [ ] Tested with environment/timezone/locale different from the build machine.
- [ ] Measured startup, RSS, image size, and build duration after changes.
- [ ] Verified policies in the proper Maven/Gradle native build configuration.

**Key takeaway:** Native Image defaults to runtime initialization for application classes it cannot prove safe to initialize early. Build-time initialization can reduce runtime work but also captures static state into the image heap. When troubleshooting, locate the specific class initializer, separate fixed state from environmental state, and adjust the smallest possible class scope. Expand to a package only when every class within that scope genuinely requires the same policy.

## References

- [GraalVM — Specify Class Initialization Explicitly](https://www.graalvm.org/latest/reference-manual/native-image/guides/specify-class-initialization/): syntax for `--initialize-at-build-time`, `--initialize-at-run-time`, and class/package examples.
- [GraalVM — Class Initialization in Native Image](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/ClassInitialization/): defaults, safe class initialization, image heap, and class hierarchy constraints.
- [GraalVM — Native Image Basics](https://www.graalvm.org/latest/reference-manual/native-image/basics/): distinguishing build time/runtime and static state stored in the image heap.
- [GraalVM — Security Considerations in Native Image](https://www.graalvm.org/dev/security-guide/native-image/): risks of sensitive data and random state when static initializers run at build time.
- [GraalVM — Native Image Command-line Options](https://www.graalvm.org/reference-manual/native-image/Options/): how to check supported options by GraalVM version.
