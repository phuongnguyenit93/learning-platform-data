# Distinguishing ClassNotFoundException, NoClassDefFoundError, and Class Initialization Errors

When a Java application loads plugins, discovers providers via `ServiceLoader`, invokes reflection, or creates a new `ModuleLayer`, the following three situations are often lumped together as "missing class":

- **`ClassNotFoundException`:** code explicitly requests looking up/loading a class by name, but the loader cannot find a matching definition. This is a **checked exception** for a lookup operation; a common error in `Class.forName(...)` and `ClassLoader.loadClass(...)`.
- **`NoClassDefFoundError`:** the JVM needs a class definition during loading, linking, or execution, but that definition **is unavailable** (for example, a dependency was present at compile time but missing at runtime). This is a **`LinkageError`**, not an `Exception`. It can also appear **after class initialization has already failed**, even though the `.class` file is still intact.
- **Class initialization error:** the class initializer fails when the JVM runs static initialization (`<clinit>`). If the cause is not an `Error`, the first attempt typically throws **`ExceptionInInitializerError`** wrapping the cause; subsequent uses within the same loader typically throw **`NoClassDefFoundError: Could not initialize class ...`**.

**Decisive point:** you must separate **lookup, loading/linking, and initialization**, inspect the *entire cause chain*, and identify the **actual class loader/module layer**. Seeing `NoClassDefFoundError` does not always mean you should add a JAR; if the class has already failed initialization, adding a JAR will not fix that class's erroneous state in the current loader.

This article moves from the underlying mechanics per Java SE 17 to a runnable example that accurately reproduces all three branches, and then builds a diagnostic workflow for plugin and runtime extensibility systems.

## 1. The Big Picture of a Class Lifecycle in the JVM

It is essential to distinguish the steps according to the Java Language Specification (JLS):

```text
Code requests a Java type
        |
        v
Loading: find/read bytes and create the Class object
        |
        v
Linking
   - Verification: verify bytecode
   - Preparation: create static fields and default values
   - Resolution: link symbolic references when needed
        |
        v
Initialization
   - execute static field initializers and static blocks
   - execute initialization of related superclasses/superinterfaces per JLS
        |
        v
Use class / invoke method / create instance
```

These steps **do not always happen all at once along a simple timeline**: the JVM may *lazily resolve* some symbolic references when first needed, while initialization is only triggered on certain "active uses". Thus, a stack trace may point to **the line calling a plugin method**, while the root cause is a lazily resolved dependency or a static initializer executing at that exact moment.

### Key Milestones

**Loading** is finding the representation of a class and creating its runtime `Class` object, via the bootstrap loader or an application-used class loader. Loaders are not required to see the same classpath. The class name plus the **defining class loader** determine class identity.

**Linking** consists of verification, preparation, and resolution. Resolution—finding a type, method, or field referenced in bytecode—may be deferred. Errors such as `NoClassDefFoundError`, `NoSuchMethodError`, `NoSuchFieldError`, `VerifyError`, or `UnsupportedClassVersionError` belong to linking/definition failures but have **different causes** and should not be fixed the same way.

**Initialization** executes static initializers. It may allocate objects, read configuration, look up services, or call external systems. If logic inside it throws an error, the class may be marked **erroneous** in the loader that defined it.

Separating these three phases helps answer accurately: "Did the JVM fail to find the class, fail while resolving a dependency, or find the class only for its initialization code to throw?"

## 2. Comparing the Three Core Error Types

| Criterion | `ClassNotFoundException` | `NoClassDefFoundError` | `ExceptionInInitializerError` |
| --- | --- | --- | --- |
| Type hierarchy | `ReflectiveOperationException` → `Exception` (checked) | `LinkageError` → `Error` (unchecked) | `LinkageError` → `Error` (unchecked) |
| Typical scenario | Class requested by name, loader cannot find it | Bytecode needs a dependency missing at runtime; or class already failed init | First execution of static initializer throws a throwable **that is not an `Error`** |
| Common location | `Class.forName`, `ClassLoader.loadClass` | Resolving a class in compiled code; active use of an erroneous class | `static { ... }` or static field initialization |
| Caught by `catch (Exception)`? | Yes | No | No |
| Is adding a JAR always enough? | No: also loader scope/module/version | No: may be an erroneous class or other mismatch | No: must fix the root cause inside the initializer |
| How to read the cause | Requested binary name, loader lookup path | Missing binary name or `Could not initialize class` message, cause chain | `getCause()` or `getException()`, original error in initializer |
| Retryability | Can switch loader/configuration depending on lookup | Depends on error kind, class/loader state | An erroneous class cannot be re-initialized in the same defining loader |

**Do not treat these as three peer exceptions.** The latter two are subclasses of `Error`, not `Exception`; code that only does `catch (Exception e)` can let them slip past. In production applications, the fix is to **repair deployment/loader/initializer**, not to wrap every request in `try/catch(Throwable)` and keep using a broken class.

### Relationship with Other Errors

- `ClassCastException`: two objects/types cannot be cast, often because two loaders defined different copies of the same API class name; not "not found".
- `NoSuchMethodException`: a reflection lookup failed to find a method by signature; distinct from `NoSuchMethodError` caused by runtime binary incompatibility.
- `NoSuchFieldError` and `NoSuchMethodError`: bytecode compiled cleanly, but the linked binary/API has a different version; usually caused by classpath/dependency conflicts.
- `UnsupportedClassVersionError`: the class file was compiled for a newer Java version or an unsupported format for the runtime; not a missing class.
- `VerifyError`: bytecode failed verification.
- `ServiceConfigurationError`: thrown when an SPI provider is misconfigured or fails to load/instantiate; **may wrap or originate from** underlying loading/linking/init errors.

If a stack trace shows an outer framework exception, **follow it down to the root cause** instead of stopping at the wrapper's name.

## 3. ClassNotFoundException: Name-Based Lookup Failed

`ClassNotFoundException` typically occurs when an API is asked to **find a class by its binary name string**, and the class loader cannot locate a definition:

```java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
Class<?> type = loader.loadClass("com.acme.plugin.Handler");
```

This is a **snippet** requiring a non-null context loader and the corresponding class to be available. `loadClass` can throw `ClassNotFoundException`. It normally **does not initialize the class**; if initialization via reflection is needed, see `Class.forName` in section 6.

Example:

```java
Class.forName("com.acme.plugin.MissingHandler");
```

The `Class.forName(String)` API throws `ClassNotFoundException` if the requested binary name cannot be found using the appropriate caller's loader. When passing explicit arguments:

```java
Class.forName("com.acme.plugin.Handler", true, pluginLoader);
```

`pluginLoader` must exist; `initialize=true` also requests initialization after lookup. Therefore this call **can throw linking/initialization errors as well**, not only `ClassNotFoundException`.

### Common Causes

1. **Wrong name:** using a path like `com/acme/Handler.class` or an old package name instead of the binary name `com.acme.Handler`.
2. **Class not packaged:** the `.class` file was not included in the JAR, or the deployment artifact is missing/built with a different profile.
3. **Right JAR, wrong loader:** the system loader, thread context class loader (TCCL), plugin loader, or a `ModuleLayer`'s loader do not share the same visibility.
4. **Modularity:** a named module was not resolved/defined in the queried layer, the loader/module path is wrong, or the layer does not contain the implementation.
5. **Dynamic plugins:** the candidate loader was not yet created or has already been closed; the registry attempts to look up a class from another generation.
6. **Shading/relocation:** the build renamed packages, but reflection/SPI metadata still holds the old name.

**Do not look only at the classpath printed in the shell.** In plugin systems, the application classpath may be correct while `pluginLoader`/TCCL still cannot see the class. Log **the requested binary name + loader type/identity + expected artifact/module version**.

### Checked Exception Does Not Mean Static Dependencies Are Absent

`ClassNotFoundException` makes sense when code **explicitly requests** a name the compiler may not know statically. When precompiled code directly references `Helper`, and at runtime the JVM cannot resolve `Helper`, it normally results in `NoClassDefFoundError` at the reference point—even though the underlying issue is still a "missing class".

Thus, both errors can stem from an absent JAR, but **the error path** differs.

## 4. NoClassDefFoundError: Definition Missing When the JVM Needs It

`NoClassDefFoundError` does not mean "the class exists but the compiler could not see it". In the typical case, **compilation succeeded**, yet a dependency used by the bytecode is absent at runtime.

Example:

```java
package demo.dependent;

public final class Broken {
    public static final String VALUE = Helper.message();
}
```

`Broken.java` compiles cleanly when `Helper.class` is present. If the build or deployment contains `Broken.class` without `Helper.class`, accessing `Broken.VALUE` or initializing `Broken` causes the JVM to require `Helper` and fail with `NoClassDefFoundError`.

### Reading the Message

Example from Java 17:

```text
java.lang.NoClassDefFoundError: demo/dependent/Helper
```

The name in the message may use **JVM internal `/` separators** rather than `.` in a binary name. Check the JAR/runtime environment to verify whether `demo/dependent/Helper.class` actually exists in the source used by the loader.

For missing-dependency failures, the cause chain often shows the loader that tried and threw `ClassNotFoundException`. This **does not turn the outer error into a checked exception**. Report both the outer `NoClassDefFoundError` and the deepest cause.

### Why Is a File Missing at Runtime Despite Compiling Cleanly?

- A dependency has `provided`/`compileOnly` scope but is not supplied at runtime.
- Fat JAR/shading dropped a class, packages were relocated inconsistently, or duplicate versions overwrote one another.
- A container/application server loads the dependency in a different parent loader; the plugin loader cannot see it or class identities mismatch.
- An optional dependency is actually invoked along a code path; the class is only resolved when that rare path executes.
- The build had the class on the compile classpath, while the runtime classpath/module path differs.
- The loader/layer of an old plugin generation was reclaimed, or the application keeps using an object/class not belonging to the new generation.

**Note:** not every `NoClassDefFoundError` is caused by a physically missing file. It also signals "the class can no longer be initialized" after a prior initialization failure; distinguish them by message/stack trace and the first occurrence.

## 5. Class Initialization Errors: ExceptionInInitializerError and Erroneous Classes

Java runs **class initialization** upon JLS active uses: creating an instance with `new`, calling a static method, reading/writing a static field that is not a compile-time constant, or requesting initialization via `Class.forName(..., true, loader)`. Reading `static final int X = 1` as a constant variable may be inlined and **does not** trigger initialization of the declaring class.

Example:

```java
package demo.init;

public final class Failing {
    static {
        setup();
    }

    private static void setup() {
        throw new IllegalStateException("bad config");
    }
}
```

This class **is present** and its bytecode is valid, yet `setup()` throws `IllegalStateException` when `<clinit>` runs.

### First Time: ExceptionInInitializerError

When an initializer completes abruptly due to a throwable **other than an `Error`**, the JVM wraps it in `ExceptionInInitializerError`. For the example above:

```text
java.lang.ExceptionInInitializerError
Caused by: java.lang.IllegalStateException: bad config
```

**The true diagnosis is the `IllegalStateException: bad config` line and how code/config is loaded in `setup()`**, not hunting for a JAR named "ExceptionInInitializerError".

If an initializer **throws an `Error`**, the JVM may throw that `Error` directly instead of wrapping it in `ExceptionInInitializerError`. Therefore **do not** claim that every static initializer failure begins with `ExceptionInInitializerError`. Either way, a failed class initialization can still cause the class to be marked erroneous.

### Subsequent Times: NoClassDefFoundError Even Though the Class File Exists

Within the same defining class loader, the JVM does not simply re-run the initializer of a class marked erroneous. Instead, the next active use can throw:

```text
java.lang.NoClassDefFoundError: Could not initialize class demo.init.Failing
```

This is an **initialization state** error, not evidence that `Failing.class` vanished. If operations teams only inspect the second request's log and overlook the first request, they often "re-add the JAR" without fixing anything.

A sound verification procedure:

1. Find **the first stack trace** that appeared before the `Could not initialize class` messages.
2. Inspect the cause of `ExceptionInInitializerError` or the direct `Error` to locate the root fault.
3. Inspect static field initializers, static blocks, superclass/superinterface initialization per JLS, configuration, environment, and dependencies invoked inside `<clinit>`.
4. Fix the code/config; create an appropriate **new class loader / layer** or restart the process when needed. Do not expect replacing a config file or JAR on disk to turn an erroneous class into an initialized one.

### Class Loading Does Not Always Trigger Initialization

There is an important difference between two APIs:

```java
Class<?> loaded = Class.forName(
        "demo.init.Failing", false,
        Thread.currentThread().getContextClassLoader());
// initialize=false: does not actively run static initializer.
```

`ClassLoader.loadClass(name)` normally loads a class **without initializing** it. Conversely, `Class.forName(name)` (the single-argument overload) requests initialization. Therefore, a test showing "`loadClass` succeeded" is **not enough** to conclude a plugin is ready; readiness checks must exercise the real runtime contract and manage side effects.

## 6. Complete Java 17 Example: Reproducing All 3 Errors and Reuse of a Broken Class

The example builds three source groups in a small project:

- `demo.missing.Ghost` **is never created**, so looking it up by name causes `ClassNotFoundException`.
- `demo.dependent.Broken` is compiled with `Helper`, but we deliberately delete **only the `Helper.class` bytecode in the test build directory** before running, to reproduce a missing-runtime-dependency `NoClassDefFoundError`.
- `demo.init.Failing` has a static initializer that intentionally throws an exception; `Class.forName(..., false, loader)` only loads it, whereas `true` triggers the initializer and fails.

**Warning:** delete only the build file `out/demo/dependent/Helper.class` in the dedicated demo folder; do not delete source files or files in a real project.

### 6.1. Source Structure

```text
class-error-demo/
├── ErrorTaxonomyDemo.java
└── demo/
    ├── dependent/
    │   ├── Helper.java
    │   └── Broken.java
    └── init/
        └── Failing.java

out/ (generated by javac, dedicated to this demo)
```

### 6.2. Code for Each File

**`demo/dependent/Helper.java`**

```java
package demo.dependent;

public final class Helper {
    public static String message() {
        return "ready";
    }
}
```

**`demo/dependent/Broken.java`**

```java
package demo.dependent;

public final class Broken {
    public static final String VALUE = Helper.message();
}
```

`VALUE` is not a compile-time constant because its value comes from a method call. When initializing `Broken`, the JVM must resolve/call `Helper.message()`; if `Helper.class` is gone, the error surfaces at runtime.

**`demo/init/Failing.java`**

```java
package demo.init;

public final class Failing {
    static {
        setup();
    }

    private static void setup() {
        throw new IllegalStateException("bad config");
    }
}
```

`setup()` always throws an exception from static initialization. Calling a separate method also avoids the compiler rule that a static initializer must not **complete abruptly on all paths directly visible to the compiler**.

**`ErrorTaxonomyDemo.java`**

```java
public final class ErrorTaxonomyDemo {
    public static void main(String[] args) throws Exception {
        ClassLoader loader = ErrorTaxonomyDemo.class.getClassLoader();

        try {
            Class.forName("demo.missing.Ghost", true, loader);
        } catch (ClassNotFoundException ex) {
            System.out.println("lookup=" + ex.getClass().getSimpleName());
        }

        try {
            Class.forName("demo.dependent.Broken", true, loader);
        } catch (NoClassDefFoundError ex) {
            System.out.println("missingDependency=" + ex.getClass().getSimpleName());
            System.out.println("missingName=" + ex.getMessage());
        }

        Class<?> notInitialized =
                Class.forName("demo.init.Failing", false, loader);
        System.out.println("loadedOnly=" + notInitialized.getSimpleName());

        try {
            Class.forName("demo.init.Failing", true, loader);
        } catch (ExceptionInInitializerError ex) {
            Throwable cause = ex.getCause();
            System.out.println("firstInit=" + ex.getClass().getSimpleName());
            System.out.println("rootCause=" + cause.getClass().getSimpleName()
                    + ":" + cause.getMessage());
        }

        try {
            Class.forName("demo.init.Failing", true, loader);
        } catch (NoClassDefFoundError ex) {
            System.out.println("retryInit=" + ex.getClass().getSimpleName());
        }
    }
}
```

The separate `catch` blocks here are meant to **intentionally classify outcomes in an illustrative program**; this is not a "catch every `Error` and keep running" policy for production. In production, log at an appropriate boundary and fix the root fault.

### 6.3. Compiling and Creating a Controlled Deployment Failure

Run with **JDK 17 or newer** inside the `class-error-demo` directory:

```bash
mkdir -p out
javac --release 17 -d out \
  ErrorTaxonomyDemo.java \
  demo/dependent/Helper.java \
  demo/dependent/Broken.java \
  demo/init/Failing.java

# Delete only the dependency in the demo's build output:
rm out/demo/dependent/Helper.class

java -cp out ErrorTaxonomyDemo
```

If using Windows PowerShell, you can run the corresponding commands:

```powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -d out ErrorTaxonomyDemo.java demo/dependent/Helper.java demo/dependent/Broken.java demo/init/Failing.java
Remove-Item -LiteralPath "out/demo/dependent/Helper.class" -Force
java -cp out ErrorTaxonomyDemo
```

**Stdout verified with `javac --release 17` and `java` on Java 17:**

```text
lookup=ClassNotFoundException
missingDependency=NoClassDefFoundError
missingName=demo/dependent/Helper
loadedOnly=Failing
firstInit=ExceptionInInitializerError
rootCause=IllegalStateException:bad config
retryInit=NoClassDefFoundError
```

### 6.4. Line-by-Line Interpretation

1. **`lookup=ClassNotFoundException`:** `Class.forName` explicitly requested `demo.missing.Ghost`, which has no class definition at all.
2. **`missingDependency=NoClassDefFoundError`:** `Broken.class` still exists; during initialization, the JVM needed `Helper.class`, which was removed from the runtime output.
3. **`missingName=demo/dependent/Helper`:** the missing dependency's name, **not `Broken`**, appears in the message in the test environment.
4. **`loadedOnly=Failing`:** `Class.forName(..., false, loader)` returned `Class<?>` without running the static initializer; the class name prints normally.
5. **`firstInit=ExceptionInInitializerError`:** the initializer ran only when `initialize=true` and threw `IllegalStateException`.
6. **`rootCause=IllegalStateException:bad config`:** you need to fix the config/logic in `setup()`, not add a JAR for `Failing`.
7. **`retryInit=NoClassDefFoundError`:** `Failing`'s class file still exists, but its initialization state is failed in the same defining loader.

If you skip deleting `Helper.class` after compiling, the missing-dependency branch **does not** occur and the demo's output changes. That demonstrates this is a runtime packaging/visibility issue, not a compile error.

## 7. How to Find the Root Cause in a Stack Trace

A stack trace can have multiple error layers:

```text
java.lang.NoClassDefFoundError: demo/dependent/Helper
    at demo.dependent.Broken.<clinit>(Broken.java:4)
    ...
Caused by: java.lang.ClassNotFoundException: demo.dependent.Helper
    at ...ClassLoader...
```

This is an **illustrative diagram** following a common pattern, not the exact stdout of `ErrorTaxonomyDemo`. Read it as follows:

- **Outer error**: the JVM could not resolve a class required by bytecode.
- **`Broken.<clinit>`**: the error surfaced inside `Broken`'s static initialization code (this line does not mean Helper failed to initialize; it is the call site that triggered resolution).
- **Cause `ClassNotFoundException`**: a loader lookup failed. You still need to investigate *which loader* performed the lookup and what scope it can see.

For class initialization:

```text
java.lang.ExceptionInInitializerError
    at ...
Caused by: java.lang.IllegalStateException: bad config
    at demo.init.Failing.setup(Failing.java:...)
    at demo.init.Failing.<clinit>(Failing.java:...)
```

If you log only the outer `ExceptionInInitializerError` without preserving its cause, you lose the real configuration error. After a few requests, logs will only show `NoClassDefFoundError: Could not initialize class demo.init.Failing`; you must locate **the first failure**.

### Step-by-Step Error Reading Checklist

1. **Outermost exception name:** `ClassNotFoundException`, `NoClassDefFoundError`, `ExceptionInInitializerError`, or a framework wrapper?
2. **What is the message?** `com/foo/Bar` suggests a missing dependency; `Could not initialize class` suggests an erroneous class.
3. **What is the root cause?** `ClassNotFoundException` in a loader, `IllegalStateException` from config, `NullPointerException` in an initializer, or an incompatibility error?
4. **First frame in your own code:** `<clinit>`, `Class.forName`, `ServiceLoader`, plugin registry API, or business logic?
5. **Which class loader / module layer?** Cross-check identity, parent delegation, TCCL, module name, and artifact version.
6. **When did the first failure occur?** The current error may merely be a consequence of an earlier failed initialization.
7. **Does it reproduce on the exact production artifact?** IDE and unit-test classpaths can differ from the deployed artifact.

Do not catch `Throwable` to "mask" these errors application-wide. At the plugin initialization boundary, you can isolate a failing candidate, log the full stack trace, and keep a healthy active generation running. If an error occurs on a class in the active generation, assess the instance/module loader state and apply a proper restart/replace policy.

## 8. Class Loader Issues: The Right JAR Can Still Have the Wrong Visibility Scope

In a Java plugin architecture, there are multiple lookup paths:

```java
ClassLoader defining = PluginEntry.class.getClassLoader();
ClassLoader context = Thread.currentThread().getContextClassLoader();
ClassLoader system = ClassLoader.getSystemClassLoader();
```

This is a **snippet**; `PluginEntry` must exist and be loaded. These three variables are not guaranteed to be the same loader. `context` can even be `null`, and in multi-threaded systems TCCL can vary per request.

### Class Identity by Name + Defining Loader

`com.acme.api.Plugin` defined by loader P is **not** the same runtime type as `com.acme.api.Plugin` defined by loader C. When the host expects the API type from P but the plugin loads its own copy from C, `ClassCastException` or another `LinkageError` can occur even though both class files exist. The standard solution:

- The host/shared parent loader **owns the service interfaces and API contracts**.
- Child plugin loaders only own implementations and dependencies requiring isolation.
- A new candidate generation uses its own loader/layer when new class definitions are needed.
- The registry tracks generations, avoiding passing V1 classes/instances to V2 as if they shared identity.

Do not "solve" every error by dumping all JARs onto the system classpath. That hides classloader issues and increases the risk of version conflicts.

### Parent Delegation and TCCL

Default class loaders are normally **parent-first** when looking up classes. This can cause a plugin expecting API/dependency V2 to actually receive V1 from the parent. Frameworks use TCCL in certain lookups, especially discovery/`ServiceLoader`; if context is wrong, providers may not be found.

Compare:

- `getClass().getClassLoader()` for the relevant object/class;
- `Thread.currentThread().getContextClassLoader()` at the discovery point;
- the loader passed explicitly to `Class.forName(name, true, loader)`;
- `ModuleLayer.findLoader(moduleName)` if using JPMS;
- the loader parent chain and the list of JARs/modules visible to that loader.

**Do not assume the system loader sees all dependencies** in an app server or modular runtime. If `ClassLoader.getSystemClassLoader()` cannot see a class, that does not mean the plugin loader cannot see it either.

## 9. Relationship to JPMS, ModuleLayer, and ServiceLoader

**A named module must be resolved/defined with a valid dependency graph.** A JAR sitting in a directory is not enough to make it an available module for a layer. For plugins using `ModuleFinder`, `Configuration.resolve/resolveAndBind`, and `ModuleLayer`, check:

- the module containing the service API is resolved; the consumer has the appropriate `requires`;
- providers are included in the layer if `ServiceLoader` is expected to discover them; with `uses`/`provides`, `resolveAndBind` can add provider modules;
- the class loader is retrieved from the right layer and module; module `exports`/`opens`/access match the contract;
- the SPI provider registered metadata properly and has a valid constructor/provider method.

A `ClassNotFoundException` when looking up a class by string and a `ServiceConfigurationError` when loading an SPI provider are two distinct signals; inspect the deepest cause. `ServiceLoader` can fail if the provider class is missing, not assignable to the service, fails instantiation/initialization, or has invalid metadata. Do not turn `ServiceConfigurationError` into "no plugins found" and silently ignore it.

### Reloading a Plugin Does Not Heal an Erroneous Class in an Old Generation

Once static initialization has failed in V1's loader:

- `ServiceLoader.reload()` only clears the `ServiceLoader` instance's discovery cache; it **does not reset the initialization state** of `Class<?>` in the defining loader.
- Replacing the V1 JAR file on disk does not alter already-loaded class definitions.
- To fix code/config with a V2 deployment, you normally must **build a new generation** with a new loader/layer and validate it; in-flight requests using V1 still need to be handled/drained per policy.
- Retaining strong references from V1 (threads, static caches, callbacks, listeners, TCCL) can prevent releasing the old loader.

Therefore, in plugin hot-replacement workflows, readiness/health checks must **exercise sufficient necessary code paths** (with controlled side effects) to avoid publishing a candidate that merely "passes `loadClass`" while failing static initialization.

## 10. Diagnostic Tools When Errors Do Not Reproduce in the IDE

### Inspecting Artifacts

For production JARs:

```bash
jar --list --file plugin.jar
```

Look for entry names like `com/acme/plugin/Handler.class` and related dependencies. For classpath-packaged JARs, entry names must match packages; if classes are shaded/relocated, check the post-build binary name. For modular JARs, also check `module-info.class` and module dependencies.

You can inspect class descriptors/bytecode once you know the artifact and classpath:

```bash
javap -classpath plugin.jar com.acme.plugin.Handler
```

`javap` reveals public type/method signatures to spot version skew. This command is a **usage template**—there is no `plugin.jar` in the demo; substitute your actual artifact. With multiple dependencies, provide the appropriate classpath/module path to resolve the information you need.

### Observing Actual Class Loading via JVM Logs

With Java 17:

```bash
java -Xlog:class+load=info -cp out ErrorTaxonomyDemo
```

This command runs the compiled demo; class loading logs can be very verbose, so use them during diagnosis and filter by the target package/loader name. Depending on the JVM and logging setup, output contains class/JAR sources; avoid sending it to public logs if environment paths are sensitive.

`-verbose:class` is also a common option, though unified logging `-Xlog:class+load=info` offers finer control in Java 17. **Class-load logs only record load events; they do not tell you which initializer failed without reading the stack trace/cause.**

### Checking Dependency Trees, Builds, and Deployments

Maven/Gradle systems have distinct dependency scopes and packaging rules. Check **effective runtime dependencies**, not just compile dependencies. If multiple copies of the same class exist, verify **which copy the class loader actually chose** via appropriate logs or code sources. For plugin deployments, record the plugin ID, generation ID, artifact hash, loader identity, module layer, and runtime Java version.

Tools like `jdeps` are useful for finding static bytecode dependencies, but **do not detect dependencies loaded via reflection, dynamically constructed resource names, ServiceLoader metadata, or unexecuted code paths**. Combine static inspection with integration tests.

## 11. Different Failure Stages Require Different Fixes

| Symptom | Question to Ask | Investigation/Remediation Path |
| --- | --- | --- |
| `ClassNotFoundException: com.x.Plugin` at `Class.forName` | Is the binary name right; which loader is looking it up? | Check package, artifact, TCCL, parent/child loader, ModuleLayer |
| `NoClassDefFoundError: com/x/Helper` when calling `Plugin.start` | Was Helper present at compile time but absent at runtime? | Compare build output and runtime packaging, scopes, module graph |
| `NoClassDefFoundError: Could not initialize class com.x.Plugin` | Was there a prior `<clinit>` failure? | Find the first failure, root cause, fix initializer/config, create new loader/generation |
| `ExceptionInInitializerError` | What `NullPointerException`/`IllegalStateException` is in the cause? | Fix static initialization, health checks, side effects |
| `UnsupportedClassVersionError` | Is the runtime JDK new enough for the class file version? | Use an appropriate `--release` target or upgrade the runtime |
| `NoSuchMethodError`/`NoSuchFieldError` | Do runtime API/dependencies differ from compile time? | Check binary compatibility, class shadowing, transitive conflicts |
| `ClassCastException` between host/plugin API | Did two loaders define the same API FQCN? | Place shared API in parent, only implementations in child |
| `ServiceConfigurationError` | What failed in metadata/implementation/constructor/provider method? | Check `META-INF/services` or `provides`, cause, and context loader |
| Failure only after redeploy | Are V1 loader/threads/caches still alive? | Check classloader retention, registry, lifecycle, and clean cutover |
| Intermittent failure under parallel execution | Does static initialization depend on mutable state/locks or request context? | Remove side effects from `<clinit>`, synchronize properly, validate per generation |

### What Not to Do

**Do not blindly delete JAR caches.** If the error is caused by a failed class initialization, deleting cached files does not alter runtime class state.

**Do not `catch (Throwable)` and keep serving with a broken class.** You can log or isolate a failing candidate at a clear boundary, but many `Error` types indicate a fault that cannot be safely recovered within that context.

**Do not swap class loaders just to mask a missing dependency.** A new loader will still fail if the artifact lacks `Helper.class`. Fixing it requires a valid deployment graph.

**Do not hold mutable global state in static initializers when avoidable.** Static initialization that depends on config or runtime I/O is hard to recover from, especially for dynamically loaded plugins.

**Do not guess the error from the top line alone.** For `ExceptionInInitializerError` and erroneous `NoClassDefFoundError`, the crucial clue often lies in earlier logs or nested causes.

## 12. Designing Plugins So Errors Can Be Isolated and Recovered

A plugin manager should separate three layers of responsibility:

```text
Artifact/Dependency validation
    |
    | check manifest, Java target, dependencies, signature
    v
Candidate loader/layer (not yet serving requests)
    |
    | load + link + initialize + construct + health/contract tests
    v
Validated generation
    |
    | atomic publish after passing readiness
    v
Active generation
    |
    | request-scoped lease / lifecycle
    v
Retire -> drain -> cleanup old generation
```

### Why Must Validation Touch Initialization?

Simply calling `ClassLoader.loadClass` can return a valid `Class<?>` even if static initialization will fail on the first request. Health checks should actively execute a **representative readiness contract**, such as calling a method without unintended side effects, validating configuration, and initializing providers per contract.

You should not "call every method" just to be sure—some methods may submit transactions, delete data, or depend on inputs. Readiness must be **purpose-built** and run in an appropriate environment/configuration.

### Isolating a Failed Candidate

If V2 hits `ExceptionInInitializerError`, `NoClassDefFoundError`, or `ServiceConfigurationError` during prepare/validate, you can:

1. Log the error/cause chain/loader identity/artifact version and clean up the candidate's resources.
2. **Do not** publish candidate V2.
3. Keep the running V1 generation serving if it is still healthy.
4. Fix dependencies/configuration or redeploy as a **new candidate generation**; do not attempt to re-run the static initializer of an erroneous class in the same loader.
5. Do not recycle a class loader or engine context left in an unknown state after partial initialization.

When catching errors at the plugin boundary, distinguish isolatable faults from severe JVM errors like `OutOfMemoryError`; never assume every `Error` is recoverable simply because a catch block exists.

### Balancing Performance and Diagnostics

Scanning classpaths, creating loaders/layers, loading plugins, and running static initializers all have costs. Do not repeat these steps per request. **Prepare/validate up front, then publish an immutable generation**, so subsequent requests use only the appropriate snapshot.

At the same time, do not cache "class not found" failures forever if the loader/module graph is updated in a controlled way: cache policies should be tied to **loader/generation version**. A new generation with a new loader/layer is a natural boundary for reloading changed implementations.

Class-load logging is very useful for debugging, though it adds noticeable overhead and log volume; enable it on demand. In normal operation, keep metadata minimal: plugin ID/version, exception name, missing binary name, loader identity, and tracking ID—without logging secrets or bytecode.

## 13. Incident Troubleshooting Decision Tree

```text
Error during plugin load/execute?
       |
       +-- ClassNotFoundException?
       |       |
       |       +-- Explicit lookup by name failed
       |             -> check binary name + right loader/layer + artifact
       |
       +-- NoClassDefFoundError?
       |       |
       |       +-- Message "Could not initialize class ..."?
       |       |        -> find the first failed initialization
       |       |        -> root cause in <clinit> + erroneous state
       |       |
       |       +-- Missing "pkg/Class" or "wrong name"?
       |                -> check runtime dependency + bytecode/package/loader
       |
       +-- ExceptionInInitializerError?
       |       |
       |       +-- read getCause() and <clinit> stack trace
       |       +-- fix code/config and replace generation/loader when needed
       |
       +-- Other LinkageError?
       |       |
       |       +-- NoSuchMethodError/NoSuchFieldError/VerifyError/...
       |                -> check binary compatibility, Java target, bytecode
       |
       +-- ServiceConfigurationError or framework wrapper?
               |
               +-- unwrap full cause chain and inspect class loader/provider
```

This flow is a **diagnostic guide**, not an absolute rule for every JVM implementation. `NoClassDefFoundError` has additional complex cases beyond the branches shown above; inspect the message, cause, bytecode references, and actual runtime behavior.

## 14. Pre-Release and Incident Investigation Checklist

**Before releasing a plugin:**

- [ ] JAR/module contains all required runtime dependencies, not only the compile classpath.
- [ ] Correct `--release`/Java target compatible with the production runtime is used.
- [ ] Shared plugin API resides in the appropriate loader/module; per-version implementations/dependencies do not collide on class identity.
- [ ] SPI metadata, `uses/provides`, or `META-INF/services` is packaged and tested in a runtime matching production.
- [ ] Static initializers do not depend on risky I/O operations, hard-to-control global state, or unvalidated config.
- [ ] Candidates are loaded, initialized, instantiated, and health/contract tested **before** atomic cutover.
- [ ] Policies exist to clean up failed candidates and never reuse loaders/classes in an erroneous state.
- [ ] Tests cover missing post-compile dependencies, wrong loader, Java target version, static initialization failure, and retries.
- [ ] Logger preserves the cause chain + generation ID without leaking secrets.

**When an incident occurs:**

- [ ] Correctly classify checked `ClassNotFoundException`, `LinkageError`, and `ExceptionInInitializerError`.
- [ ] Inspect the entire stack trace/cause, not only the top line.
- [ ] If the message says `Could not initialize class`, locate **the first failure** of the initializer.
- [ ] Identify the actual binary name, package/path, class version, and artifact hash.
- [ ] Record the defining loader, TCCL, parent loader, ModuleLayer, and relevant request/generation context.
- [ ] Compare the runtime dependency graph against the build-time graph.
- [ ] Use `-Xlog:class+load=info`/`javap`/`jar --list` only as needed and protect sensitive environment paths.
- [ ] Prefer recovery via a validated generation or controlled process restart; do not force reuse of erroneous classes.

### Java SE 17 References

- [`ClassNotFoundException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassNotFoundException.html)
- [`NoClassDefFoundError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html)
- [`ExceptionInInitializerError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ExceptionInInitializerError.html)
- [`Class.forName`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader))
- [JLS `12.2–12.4: loading, linking, initialization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html)
- [`ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [`ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)

**Conclusion:** `ClassNotFoundException` signals that an **explicit lookup** could not find a class; `NoClassDefFoundError` signals that the JVM could not obtain a required class definition **or that a previously failed-initialization class cannot be used again**; `ExceptionInInitializerError` leads you to **the cause inside static initialization** on the first failure. To diagnose and fix plugin systems accurately and quickly, always separate *failure phase*, *class loader/module layer*, and *root cause*, then manage deployment/initialization along generation lifecycles—never guess from the exception name alone.
