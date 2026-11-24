# Investigating ServiceConfigurationError from Registration Files, Modules, or Constructors

An extensible Java application typically uses `java.util.ServiceLoader` to discover implementations of a service interface (SPI) without knowing concrete class names ahead of time. Provider discovery can rely on **META-INF/services** on the classpath or **uses/provides** in the Java Platform Module System (JPMS). The same `ServiceConfigurationError` can arise from a misnamed descriptor file, malformed provider-name syntax, a missing class, a class that does not actually implement the SPI, a missing valid constructor, or a malfunctioning module `provider()` method.

The goal of this article is **systematic investigation rather than guessing from a single error message**: identify where the provider was discovered, at which step the failure occurred, inspect the cause and class loader/module metadata, and fix the true publishing source. We will build two independent Java 17+ labs—one on the **classpath** and one using **explicit named modules**—with verifiable output.

## 1. What Is ServiceConfigurationError and Where Does It Occur?

**java.util.ServiceConfigurationError extends java.lang.Error**, not `Exception`. According to the Java 17 documentation, it signals an error when **locating, loading, or instantiating** a service provider. Therefore:

- `catch (Exception ex)` **does not catch** `ServiceConfigurationError`.
- Catching `ServiceConfigurationError` specifically at the **service discovery/instantiation** boundary makes sense when the host wants to report a configuration error, disable dependent features, or isolate an optional plugin.
- Do not catch `Throwable` and carry on as if nothing happened: `VirtualMachineError`, `ThreadDeath`, and other severe errors are not ordinary provider configuration errors.
- `getMessage()` often carries the service/provider name and hints at the cause, yet **its text is not a stable protocol**. Never classify failures by matching a single message string; inspect the stack trace, `getCause()`, and the actual artifact.

Typical discovery lifecycle:

~~~text
ServiceLoader.load(Service.class)
           |
           v
Create ServiceLoader (not necessarily iterating providers yet)
           |
           v
iterator.hasNext() or iterator.next()
   |
   +--> classpath: locate, read META-INF/services/<SPI>
   |                 parse provider names
   |
   +--> JPMS: locate provides in resolved modules
   |             (consumer named module requires uses)
   |
   v
Load provider class / check subtype or provider()
           |
           v
Instantiate via public no-arg constructor
or invoke public static provider() in explicit named module
           |
           +--> error: ServiceConfigurationError
           |
           v
Obtain provider instance
           |
           v
Invoke business method (provider-specific error)
~~~

**Calling `ServiceLoader.load(...)` alone is not a complete check**. `ServiceLoader` discovers and instantiates providers lazily. Both `Iterator.hasNext()` and `Iterator.next()` can throw `ServiceConfigurationError`; when using `stream()`, errors can surface during the operations that actually discover or load providers, including `Provider.get()`.

Distinguish three groups:

| Stage | Symptom | Possible Error |
| --- | --- | --- |
| No valid registration | No matching descriptor/`provides` found | Usually **0 providers**, not necessarily `ServiceConfigurationError` |
| Registration exists but cannot load/instantiate | Missing class, wrong subtype, constructor/factory failure | **ServiceConfigurationError** |
| Provider created, business call fails | Missing private resource, bad input, I/O, plugin exception | Business error; **does not automatically** become `ServiceConfigurationError` |

For example: a descriptor with a **misspelled file name** goes undiscovered and may yield an empty result set; a descriptor with the **right name declaring a non-existent class** typically produces `ServiceConfigurationError` during iteration. These two cases require different fixes.

## 2. Cause Map: Registration Files, JPMS, and Constructors

| Declaration Source | Situation | What to Verify |
| --- | --- | --- |
| META-INF/services on classpath | Wrong file name, wrong location, missing from runtime classpath | Exact path `META-INF/services/<SPI binary name>`, JAR contents |
| META-INF/services on classpath | Line is not a valid class name, wrong encoding, or I/O error reading | File contents, UTF-8, line numbers, `#` comments, whitespace |
| META-INF/services on classpath | Class name does not exist or is not visible to loader | Which JAR holds the class, which loader is actually in use |
| META-INF/services on classpath | Provider is not a subtype of the SPI | Check actually implemented interfaces and **class identity** |
| META-INF/services on classpath | Provider lacks a public no-argument constructor | `javap -public`, constructors, and class visibility |
| META-INF/services on classpath | Constructor throws an exception or error | Stack trace and `getCause()` |
| Explicit named module (JPMS) | Consumer lacks `uses` service or provider module is not resolved | `module-info`, module graph, how `ServiceLoader.load` is called |
| Explicit named module (JPMS) | `provides` points to unloadable provider, or constructor fails | Runtime module descriptor, loader, cause |
| Explicit named module (JPMS) | `public static provider()` returns null, throws, or wrong type | Signature and return value of the provider method |
| Automatic module | Expected to support provider factory like an explicit named module | Automatic modules use constructors; no provider method support |
| Any model | Two copies of SPI with same name but different defining loaders | Compare `ClassLoader` and `Class` objects, not just class name |

**Not every JPMS error carries the exact name `ServiceConfigurationError`**. `module-info` compilation errors, pre-layer resolution failures, or `IllegalAccessError`/`NoClassDefFoundError` in business code can carry other exception/error types. Identify the first failing stage rather than labeling every plugin error under one name.

## 3. Classpath Descriptors: Rules That Are Easy to Get Wrong

On the classpath, a service configuration file has an **exact path**:

~~~text
META-INF/services/com.example.spi.MyService
~~~

The file name is the **full binary name of the service interface/class**, not the provider name, and has no `.txt`, `.class`, or `.java` extension. This file sits at the **root of each JAR** containing registrations. Each valid line is the fully qualified name of one provider class; a `#` starts a comment through the end of the line. `ServiceLoader` allows whitespace around lines, though provider names cannot contain internal whitespace.

Example:

~~~text
# UTF-8 text; file name = META-INF/services/demo.spi.Action
demo.providers.Healthy
demo.providers.Backup
~~~

**Three errors to distinguish:**

1. The file is renamed from `META-INF/services/demo.spi.Action` to `META-INF/services/demo.spi.Actions`. With a single JAR on the classpath, the loader **does not see a registration file for Action** and may return 0 providers.
2. The file has the right name, but one line reads `demo.providers.NotPresent`. That name is parsed as a registration; when Java cannot find the class, `ServiceConfigurationError` can be thrown during iteration.
3. The file has the right name, but contains `"not a class name!"`. That is not a valid binary name; the parser can report `ServiceConfigurationError` while reading the descriptor, **before instantiating anything**.

All three can lead users to report "failed to load plugin", yet they are not fixed with the same action. Case (1) requires fixing packaging/file name; case (2) requires fixing registration or classpath; case (3) requires fixing formatting/encoding.

**Do not read a source file in the project and conclude the JAR is right.** Verify what is actually inside the deployed artifact using `jar --list` and inspect the contents of that entry in the artifact itself (you can extract a copy while investigating). Windows paths display different directory separators, yet **entry names inside a JAR** still use `/`.

## 4. Java 17+ Classpath Lab: Reproducing Seven Variants

This lab compiles a single set of provider classes and packages multiple JARs with **different descriptors**. Thus, simply swapping JARs on the runtime classpath lets us distinguish packaging, class-name, subtype, and constructor errors.

### 4.1. Directory Tree

~~~text
classpath-lab/
├── src/
│   ├── api/demo/spi/Action.java
│   ├── host/demo/host/Check.java
│   └── providers/demo/providers/
│       ├── Healthy.java
│       ├── NeedsArgument.java
│       ├── Boom.java
│       └── NotAction.java
├── descriptors/
│   ├── good/META-INF/services/demo.spi.Action
│   ├── typo/META-INF/services/demo.spi.Actions
│   ├── missing-class/META-INF/services/demo.spi.Action
│   ├── bad-syntax/META-INF/services/demo.spi.Action
│   ├── no-ctor/META-INF/services/demo.spi.Action
│   ├── throws/META-INF/services/demo.spi.Action
│   └── wrong-type/META-INF/services/demo.spi.Action
├── build/               (created during build)
└── dist/                (created during build)
~~~

### 4.2. Shared SPI

File **src/api/demo/spi/Action.java**:

~~~java
package demo.spi;

public interface Action {
    String id();
}
~~~

Both host and providers reference **dist/api.jar** at compile time. Provider JARs do not repackage `demo/spi/Action.class`.

### 4.3. Healthy Provider

File **src/providers/demo/providers/Healthy.java**:

~~~java
package demo.providers;

import demo.spi.Action;

public final class Healthy implements Action {
    public Healthy() {}

    @Override
    public String id() {
        return "ok";
    }
}
~~~

This is a valid classpath provider: public class, implements `Action`, public no-argument constructor.

### 4.4. Class Implements the Interface but Lacks a No-Arg Constructor

File **src/providers/demo/providers/NeedsArgument.java**:

~~~java
package demo.providers;

import demo.spi.Action;

public final class NeedsArgument implements Action {
    public NeedsArgument(String message) {}

    @Override
    public String id() {
        return "argument";
    }
}
~~~

Once you explicitly declare **only** a constructor taking `String`, Java no longer generates a no-argument constructor. Thus `ServiceLoader` cannot instantiate it under classpath rules, even though the class exists and implements `Action`. This is a distinct root cause, **not `ClassNotFoundException`**.

### 4.5. Constructor Has the Right Signature but Throws an Exception

File **src/providers/demo/providers/Boom.java**:

~~~java
package demo.providers;

import demo.spi.Action;

public final class Boom implements Action {
    public Boom() {
        throw new IllegalStateException("construction failed");
    }

    @Override
    public String id() {
        return "boom";
    }
}
~~~

`ServiceLoader` locates the class and matching constructor, yet **instantiation fails**. In the `ServiceConfigurationError` stack trace, `getCause()` reveals the original exception thrown by the constructor. During investigation, record the entire cause chain rather than just the label "could not instantiate".

### 4.6. Class Exists but Is Not a Subtype of the SPI

File **src/providers/demo/providers/NotAction.java**:

~~~java
package demo.providers;

public final class NotAction {
    public NotAction() {}
}
~~~

This class intentionally **does not implement `Action`**. If a descriptor lists it as a provider of `demo.spi.Action`, Java seeing the class is not enough: the type check fails and `ServiceConfigurationError` is thrown during discovery/instantiation.

### 4.7. Host Distinguishing Configuration Errors from Business Errors

File **src/host/demo/host/Check.java**:

~~~java
package demo.host;

import demo.spi.Action;
import java.util.Iterator;
import java.util.ServiceConfigurationError;
import java.util.ServiceLoader;

public final class Check {
    public static void main(String[] args) {
        boolean trace = args.length > 0 && "--trace".equals(args[0]);
        Iterator<Action> providers =
                ServiceLoader.load(Action.class).iterator();
        boolean found = false;

        for (;;) {
            Action action;
            try {
                if (!providers.hasNext()) {
                    break;
                }
                action = providers.next();
            } catch (ServiceConfigurationError error) {
                System.out.println("CONFIG_ERROR");
                if (trace) {
                    error.printStackTrace(System.err);
                }
                return;
            }

            found = true;
            try {
                System.out.println("FOUND " + action.id());
            } catch (RuntimeException failure) {
                // Business logic runs after the provider has been instantiated.
                System.out.println("PROVIDER_RUNTIME_ERROR");
                if (trace) {
                    failure.printStackTrace(System.err);
                }
            }
        }

        if (!found) {
            System.out.println("NO_PROVIDER");
        }
    }
}
~~~

**Why must `try` wrap both `hasNext()` and `next()`?** Java 17 allows `ServiceConfigurationError` to be thrown by **both**. For `bad-syntax`, the issue can surface while reading config right inside `hasNext()`; for `no-ctor` or `throws`, the error is typically detected when `next()` tries to instantiate the provider.

This code intentionally **stops discovery after a configuration error**. Under the JDK contract, an iterator after a `ServiceConfigurationError` only makes a best-effort attempt to locate subsequent providers; recovery is not guaranteed. A continue-trying strategy for optional plugins must enforce error/iteration limits, log rejected providers, and avoid treating an incomplete provider set as full success. For investigation, stopping and fixing the artifact reproduces causes more consistently.

When `--trace` is passed, the exception prints to **stderr**, so JDK-specific stack trace text may vary. Stable stdout contains only the labels shown in the example.

### 4.8. Contents of the Seven Descriptors

Create the text files under `descriptors/` with their **corresponding contents**:

**good/META-INF/services/demo.spi.Action**

~~~text
demo.providers.Healthy
~~~

**typo/META-INF/services/demo.spi.Actions** (intentionally wrong **file name**, not wrong content)

~~~text
demo.providers.Healthy
~~~

**missing-class/META-INF/services/demo.spi.Action**

~~~text
demo.providers.DoesNotExist
~~~

**bad-syntax/META-INF/services/demo.spi.Action**

~~~text
not a class name!
~~~

**no-ctor/META-INF/services/demo.spi.Action**

~~~text
demo.providers.NeedsArgument
~~~

**throws/META-INF/services/demo.spi.Action**

~~~text
demo.providers.Boom
~~~

**wrong-type/META-INF/services/demo.spi.Action**

~~~text
demo.providers.NotAction
~~~

There is no shared descriptor file in `build/providers/`. We place each descriptor into **each JAR** during packaging; each run uses only one variant JAR and `api.jar`.

### 4.9. Compile, Package JARs, and Run

From the **classpath-lab/** directory, with JDK 17+ and a bash/POSIX shell:

~~~bash
mkdir -p build/api build/providers build/host dist

javac --release 17 -encoding UTF-8 -d build/api \
  src/api/demo/spi/Action.java
jar --create --file dist/api.jar -C build/api .

javac --release 17 -encoding UTF-8 \
  -cp dist/api.jar -d build/providers \
  src/providers/demo/providers/*.java

javac --release 17 -encoding UTF-8 \
  -cp dist/api.jar -d build/host \
  src/host/demo/host/Check.java

for case_name in good typo missing-class bad-syntax no-ctor throws wrong-type
do
  jar --create --file "dist/$case_name.jar" \
    -C build/providers . -C "descriptors/$case_name" .
done

for case_name in good typo missing-class bad-syntax no-ctor throws wrong-type
do
  printf "%s -> " "$case_name"
  java -cp "build/host:dist/api.jar:dist/$case_name.jar" \
    demo.host.Check
done
~~~

**Exact expected stdout** with the exact JARs and classpath listed above:

~~~text
good -> FOUND ok
typo -> NO_PROVIDER
missing-class -> CONFIG_ERROR
bad-syntax -> CONFIG_ERROR
no-ctor -> CONFIG_ERROR
throws -> CONFIG_ERROR
wrong-type -> CONFIG_ERROR
~~~

Interpretation:

- **good**: descriptor name and constructor are valid; prints `FOUND ok`.
- **typo**: the provider class is present, yet the services file is named `demo.spi.Actions` instead of `demo.spi.Action`. There is no registration for the queried SPI, so it prints `NO_PROVIDER` rather than **necessarily throwing an error**.
- **missing-class**: the descriptor requests a class that does not exist in the runtime loader.
- **bad-syntax**: the provider name is invalid directly in the file contents.
- **no-ctor**: missing public no-arg constructor.
- **throws**: constructor runs and throws `IllegalStateException`.
- **wrong-type**: class exists, but is not assignable to `Action`.

When running on Windows in PowerShell/CMD, the `-cp` separator is **;**, not **:**. The `for` syntax, line-continuation `\`, `$case_name` variable, and `mkdir -p` are bash syntax; use Git Bash/WSL or rewrite equivalently for PowerShell.

To inspect the root cause of each variant, run individually:

~~~bash
java -cp "build/host:dist/api.jar:dist/throws.jar" \
  demo.host.Check --trace

java -cp "build/host:dist/api.jar:dist/no-ctor.jar" \
  demo.host.Check --trace

javap -public -classpath "dist/api.jar:dist/no-ctor.jar" \
  demo.providers.NeedsArgument
~~~

The `javap` command confirms there is a constructor taking `String` and **no empty constructor**. For `throws`, the stack trace shows the provider instantiation path and the underlying `IllegalStateException`. Do not match full stderr against literal text: messages and stack frames depend on how the JDK formats errors.

## 5. Evidence-Based Classpath Diagnostic Workflow

When `ServiceLoader` finds no providers or throws `ServiceConfigurationError`, proceed step by step:

1. **Confirm what the service type actually is.** Print `Action.class.getName()` and `Action.class.getClassLoader()`; do not infer from a simple name or an interface copy in the source tree.
2. **Confirm which class loader looks up providers.** `ServiceLoader.load(Action.class)` uses the calling thread's TCCL; `ServiceLoader.load(Action.class, explicitLoader)` uses the passed loader. Classpaths of IDEs, test runners, servlet containers, and worker threads can differ.
3. **Inspect the exact runtime JAR.** Use `jar --list --file plugin.jar` to check for `META-INF/services/demo.spi.Action` and the relevant `.class` files. Do not look only at files outside the JAR.
4. **Open the correctly named descriptor and inspect every line.** Verify exact binary class names, no invalid whitespace, no accidental `.class` suffix, and valid UTF-8. One bad line can fail the entire discovery pass.
5. **Check whether the class can be loaded.** If the class name is right yet the JVM reports class not found, check missing dependencies, class loader scope, JAR version, and module/classpath deployment.
6. **Check subclassing and constructors.** Check SPI compatibility via `isAssignableFrom(...)` on the actual `Class` object; use `javap -public` or controlled reflection to confirm a suitable constructor.
7. **Inspect `getCause()` and the stack trace.** Distinguish parse errors, linkage errors, constructor failures, or factory code throwing exceptions.
8. **Fix the artifact and rerun in a clean process** whenever possible; do not rely on `reload()` as a way to "heal" a broken descriptor or JAR.

Reference commands:

~~~bash
jar --list --file dist/good.jar
jar --list --file dist/missing-class.jar
javap -public -classpath "dist/api.jar:dist/good.jar" \
  demo.providers.Healthy
~~~

When logging in a real system, record **service name, provider name (if known), artifact path/hash, JDK version, loader identity, module name, exception class, message, cause chain, and stage**. Avoid writing full plugin source or configuration passwords to logs. Track `NO_PROVIDER`, `CONFIG_ERROR`, and `PROVIDER_RUNTIME_ERROR` separately.

**Easily misunderstood detail:** two JAR files both containing a descriptor for the same SPI can cause `ServiceLoader` to discover multiple providers. Descriptor order depends on `ClassLoader.getResources(...)` ordering. Never build system correctness on an accidental classpath order; and certainly never place a broken JAR ahead of a good provider expecting the good provider to always be used.

## 6. JPMS: What Changes When Providers Live in a Named Module?

Since Java 9, explicit named modules typically declare providers in **module-info.java**:

~~~java
// In a provider module (illustrative code):
module demo.provider {
    requires demo.api;
    provides demo.spi.Action with demo.provider.Direct;
}
~~~

A consumer that is an **explicit named module** must declare **`uses demo.spi.Action`** if it calls `ServiceLoader` for that service. If `uses` is missing, `ServiceLoader` can throw `ServiceConfigurationError` immediately when creating the loader; check for errors at the `load(...)` call, not only during iteration.

Comparison with classpath descriptors:

| Aspect | Classpath / Unnamed Module | Explicit Named Module |
| --- | --- | --- |
| Where providers are declared | `META-INF/services/<SPI>` | `provides ... with ...` in `module-info` |
| Discovery scope | `ClassLoader` and resources visible to it | Resolved module graph; can use `load(layer, service)` |
| Consumer `uses` | No `module-info` | Requires `uses` for an explicit named module caller |
| How provider is instantiated | Public no-arg constructor | Public no-arg constructor **or valid provider method** |
| Must provider class implement SPI? | Yes | If using `provider()`, the factory class **does not necessarily** implement the SPI |
| Name/type validity checks | Mostly discovered during runtime scan | Many descriptor errors are caught by `javac` at module compile time |
| Simultaneous resource descriptors | Service file registers classpath providers | Providers in named modules are identified by `provides`; do not use service files as an alternate registration source |
| Provider discovery order | Depends on `ClassLoader.getResources` and descriptor order | Module order within a layer is not guaranteed |

A **provider method** in an explicit named module is a **`public static` method named `provider`, taking no parameters, with a return type assignable to the service**. If present, `ServiceLoader` invokes it to obtain the instance. The method may return `null` or throw an error; both cause `ServiceConfigurationError` during provider creation.

**Automatic modules** on the module path follow different rules: they require a provider constructor and do not support the explicit-named-module `provider()` factory style. Therefore, any guidance saying "just add `public static provider()`" must verify whether the artifact is actually an explicit module or an automatic module.

Distinguish **an unresolved module** from **a resolved provider that failed to instantiate**. Simply having a module in the `--module-path` directory does not prove it belongs to the executed module graph. In the lab below, we add `--add-modules demo.provider` to ensure the provider module is resolved.

## 7. Java 17+ JPMS Lab: Direct Constructor and Factory Provider

This lab is separate from `classpath-lab` to avoid binary name collisions between the two codebases. We create three explicit modules:

- **demo.api**: exports the public SPI `Action`.
- **demo.provider**: registers two providers—one directly via a public constructor and one via `public static provider()`.
- **demo.host**: declares `uses` and calls `ServiceLoader`.

### 7.1. Directory Tree

~~~text
module-lab/
├── src/
│   ├── demo.api/
│   │   ├── module-info.java
│   │   └── demo/spi/Action.java
│   ├── demo.provider/
│   │   ├── module-info.java
│   │   └── demo/provider/
│   │       ├── Direct.java
│   │       └── Factory.java
│   └── demo.host/
│       ├── module-info.java
│       └── demo/host/Main.java
└── build/mods/              (created on compilation)
~~~

### 7.2. API Module

File **src/demo.api/module-info.java**:

~~~java
module demo.api {
    exports demo.spi;
}
~~~

File **src/demo.api/demo/spi/Action.java**:

~~~java
package demo.spi;

public interface Action {
    String id();
}
~~~

### 7.3. Provider Module and Two Instantiation Mechanisms

File **src/demo.provider/module-info.java**:

~~~java
module demo.provider {
    requires demo.api;
    provides demo.spi.Action with
            demo.provider.Direct, demo.provider.Factory;
}
~~~

File **src/demo.provider/demo/provider/Direct.java**:

~~~java
package demo.provider;

import demo.spi.Action;

public final class Direct implements Action {
    public Direct() {}

    @Override
    public String id() {
        return "direct";
    }
}
~~~

File **src/demo.provider/demo/provider/Factory.java**:

~~~java
package demo.provider;

import demo.spi.Action;

public final class Factory {
    private Factory() {}

    // In an explicit named module, ServiceLoader receives the instance from this method.
    public static Action provider() {
        return () -> "factory";
    }
}
~~~

`Factory` **does not implement `Action`** and has a private constructor. This is valid because it exposes a `provider()` method returning `Action`; `ServiceLoader` calls `provider()` and receives a lambda that actually implements `Action`. **Do not apply this pattern to a classpath descriptor** and expect classpath `ServiceLoader` to call `Factory.provider()`: the classpath case requires the provider class to be assignable to the SPI and have a public no-arg constructor.

You do not need `exports demo.provider` in `module-info`: provider classes may reside in unexported packages, and the service framework still has appropriate access to the provider. If the host itself wants to reflect on non-public members of a provider, analyze `opens`/`exports` separately—do not infer access from the fact that `ServiceLoader` could instantiate it.

### 7.4. Host Module with `uses`

File **src/demo.host/module-info.java**:

~~~java
module demo.host {
    requires demo.api;
    uses demo.spi.Action;
}
~~~

File **src/demo.host/demo/host/Main.java**:

~~~java
package demo.host;

import demo.spi.Action;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.ServiceConfigurationError;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        boolean trace = args.length > 0 && "--trace".equals(args[0]);

        try {
            List<String> ids = new ArrayList<>();
            for (Action provider : ServiceLoader.load(Action.class)) {
                ids.add(provider.id());
            }

            Collections.sort(ids);
            for (String id : ids) {
                System.out.println("FOUND " + id);
            }
            if (ids.isEmpty()) {
                System.out.println("NO_PROVIDER");
            }
        } catch (ServiceConfigurationError error) {
            System.out.println("CONFIG_ERROR");
            if (trace) {
                error.printStackTrace(System.err);
            }
        }
    }
}
~~~

The host collects IDs and **sorts** them before printing because provider discovery order across multiple modules is not generally defined. In this lab both providers live in the same module with a specific `provides` order, yet sorting keeps output independent of ordering policies as exercises expand to additional modules.

Note that in real production code, `provider.id()` can throw business exceptions and should be caught separately. Here both providers have pure `id()` methods, so the `try/catch` focuses on failures when `ServiceLoader` resolves or instantiates providers.

### 7.5. Compile and Run on the Module Path

From the **module-lab/** directory, JDK 17+ and a bash/POSIX shell:

~~~bash
mkdir -p build/mods

javac --release 17 -encoding UTF-8 \
  --module-source-path src -d build/mods \
  -m demo.api,demo.provider,demo.host

java --module-path build/mods \
  --add-modules demo.provider \
  -m demo.host/demo.host.Main
~~~

Exact expected stdout:

~~~text
FOUND direct
FOUND factory
~~~

Use the following commands to inspect the **compiled module descriptors**:

~~~bash
java --module-path build/mods --describe-module demo.provider
java --module-path build/mods --describe-module demo.host
~~~

`--describe-module` may print additional package names, `requires`, `exports`, and varying order across JDKs; what matters is that `demo.provider` contains **`provides demo.spi.Action`** and `demo.host` contains **`uses demo.spi.Action`**. If you see no providers when trying in another environment, inspect the resolved graph and note that the example passes `--add-modules demo.provider` to bring it into the graph.

### 7.6. Reproducing Failures from a Module Provider Method

After confirming the lab succeeds, **only in your isolated lab copy**, change the body of `Factory.provider()` to:

~~~java
public static Action provider() {
    return null;
}
~~~

This is a **single-method edit snippet**, not a complete Java file. Recompile `module-lab` with the `javac` command above, then rerun. The compiler accepts it because the return type is `Action`, yet `ServiceLoader` receiving `null` from `provider()` throws `ServiceConfigurationError`. The host prints:

~~~text
CONFIG_ERROR
~~~

Enable `--trace` to view the specific cause/stack trace:

~~~bash
java --module-path build/mods --add-modules demo.provider \
  -m demo.host/demo.host.Main --trace
~~~

Another variant is having `Factory.provider()` throw `IllegalStateException`. Then `ServiceConfigurationError` typically carries a cause reflecting the failure inside the factory. Note: **exact message/cause details depend on the case and JDK version**, so never compare full stack traces against literal text.

To reproduce a **constructor failure in an explicit named module**, restore a valid `Factory.provider()` and change `Direct`'s constructor:

~~~java
public Direct() {
    throw new IllegalStateException("module constructor failed");
}
~~~

Recompilation still succeeds (valid public no-arg constructor), yet instantiating `Direct` throws and `ServiceLoader` reports `ServiceConfigurationError`. This is a runtime failure. Conversely, if you **completely remove** the public no-arg constructor from `Direct` and `Direct` has no valid `provider()`, `javac` can reject the `provides` clause at compile time; do not attribute every module definition error to a single runtime exception.

### 7.7. Reproducing a Consumer Missing `uses`

In the lab, remove the `uses demo.spi.Action;` line from `demo.host`'s `module-info.java`, recompile, and call `ServiceLoader.load(Action.class)`. Per the JDK 17 contract, a caller in an explicit named module that does not declare `uses` for the service can hit `ServiceConfigurationError` right at the **`load(...)` call**.

Point to verify: the host code placed the `load(...)` call inside the `try/catch` block so `CONFIG_ERROR` is observed. If you only wrap the `for`-loop in `try` while constructing the `ServiceLoader` **outside `try`**, the loader creation failure from missing `uses` will escape the boundary.

To fix it, restore `uses` in the consumer's `module-info.java`; do not modify `provides` in the provider module if the fault truly originates from the consumer.

## 8. Proper Module Error Investigation Sequence

For named modules, the workflow must start with **runtime configuration**, rather than immediately hunting for `META-INF/services`:

1. **Verify whether the provider is an explicit, automatic, or unnamed module.** Run `jar --describe-module` for modular JARs or `java --describe-module` with the module path; inspect `module-info.class` and the module graph.
2. **Check whether the consumer declares `uses`.** `ServiceLoader.load` from an explicit module requires a corresponding `uses`; wrap the loader-creation call itself in `try`.
3. **Check whether the provider is resolved.** Simply residing in the module-path directory is insufficient; verify root modules, `--add-modules`, resolution, or runtime `ModuleLayer`.
4. **Read the provider's `provides ... with ...`.** The provider class must be declared in the module providing the service; many subtype/constructor errors are caught early by `javac` when built cleanly from source.
5. **Check the instantiation mechanism:** without a provider method, a public no-arg constructor and assignability are required; with `public static provider()`, verify return type, non-null return, and exceptions thrown.
6. **Verify SPI identity:** which API module is read by consumer and provider? Two copies of an interface with the same name defined by different loaders may not be assignable.
7. **Inspect the cause chain and runtime class/module:** print `class.getModule().getName()` and `getClassLoader()` when a valid `Class` object exists. Do not rely on `getName()` alone since it does not distinguish loaders.
8. **Fix the right artifact and redeploy:** if the module descriptor is wrong, rebuild the module; if constructor/factory fails, fix the implementation; if the module was not resolved, fix the graph and layer construction.

**Compile-time `module-info` errors must not be masked under the `ServiceConfigurationError` label.** For example, a `module-info` using `provides` with a provider outside the module or failing JLS requirements can be rejected by `javac` before the application ever runs. Separating failure timing saves substantial investigation time.

`ModuleLayer` adds further subtlety: `ServiceLoader.load(layer, Action.class)` searches for services in that layer and its parent layers per the API contract, **not scanning classpath/unnamed module providers** the way a full TCCL scan does. Therefore, missing providers in a layer-specific lookup does not necessarily mean the provider implementation is broken; the host may be querying the wrong layer.

## 9. How Constructors, Provider Methods, and Linkage Errors Differ

| Case | What Is Proven | What Can Still Be Wrong |
| --- | --- | --- |
| Provider class appears in `jar --list` | `.class` file exists in the artifact | Is the runtime JAR visible to the loader? Is the class an SPI subtype? |
| `Class.forName(name, false, loader)` succeeds | Class can be located/defined by that loader | Public no-arg constructor, dependencies during initialization, provider method, and access permissions |
| `javap` shows `public X()` | Bytecode has the right constructor shape | Constructor may throw an exception |
| Provider `implements` SPI in source | Source contains the `implements` clause | Runtime SPI may have a different class identity |
| Class has `public static provider()` | Method with matching name exists | Only used as a provider method in supporting module contexts; return type or value may be wrong |
| `ServiceLoader.load(...)` returns an object | `ServiceLoader` created | Not yet iterated, loaded, or instantiated providers |
| `Iterator.hasNext()` returns `true` | A provider candidate exists | `Iterator.next()` can still throw `ServiceConfigurationError` |
| Provider instance created successfully | Constructor/factory returned an instance | Business methods can still throw exceptions or misconfigure resources |

**`NoClassDefFoundError` is not synonymous with `ClassNotFoundException`.** A provider class may exist, yet when the JVM links or initializes it, another dependency is missing or incompatible. Inspect the cause chain and dependency list rather than only editing the descriptor name. For other linkage errors (`NoSuchMethodError`, `IncompatibleClassChangeError`, `IllegalAccessError`), inspect the runtime ABI/JAR; do not assume every `Error` is wrapped by `ServiceLoader` into `ServiceConfigurationError` at every step.

**TCCL:** `ServiceLoader.load(Service.class)` uses `Thread.currentThread().getContextClassLoader()`. A worker thread with a different context loader than the main thread, or a plugin manager using its own loader, may locate the descriptor yet fail to load the right implementation/API. When design permits, use `ServiceLoader.load(Service.class, pluginLoader)` and manage loaders explicitly. Modifying TCCL without restoring it in `finally` can trigger cascading lookup failures on subsequent requests.

**Class identity:** two `Class` objects with the same name `demo.spi.Action` defined by two different `ClassLoader` instances are **two distinct JVM types**. When seeing "not a subtype" even though source implements `Action`, check the defining loader of both the interface and implementation; avoid bundling a separate copy of the API JAR into each plugin if the host expects providers to implement the host-defined interface.

## 10. Logging Sufficient Information Without Exposing Sensitive Data

Do not simply catch and print `"CONFIG_ERROR"`; production needs enough context to trace back to the root cause. A simple helper at the error boundary might look like:

~~~java
// Illustrative integration snippet, not a standalone Java file.
static void reportServiceFailure(
        Class<?> service, ServiceConfigurationError error) {
    System.err.println("service=" + service.getName());
    System.err.println("serviceLoader=" + service.getClassLoader());
    System.err.println("message=" + error.getMessage());

    Throwable cause = error.getCause();
    int depth = 0;
    while (cause != null && depth < 8) {
        System.err.println("cause[" + depth + "]="
                + cause.getClass().getName()
                + ": " + cause.getMessage());
        cause = cause.getCause();
        depth++;
    }
    error.printStackTrace(System.err);
}
~~~

For structured production loggers, prefer fields for `service`, `candidateProvider`, `artifactId`, `artifactHash`, `loaderId`, `moduleName`, `stage` (`LOOKUP`/`PARSE`/`LOAD`/`INSTANTIATE`/`INVOKE`), `exceptionClass`, `rootCauseClass`, and `correlationId`. Never use a `ClassLoader`'s `hashCode()` as a globally unique identifier; assign dedicated IDs in the plugin manager when needed.

Even if `getCause()` is `null`, a serious error can exist in the descriptor itself; **a null cause does not mean a false alarm**. Log the exact message and context for diagnosis. If `provider()` returns `null` in a named module, the JDK may report `"provider method returned null"` without a user-thrown `Throwable` cause.

Avoid logging full plugin source code, credentials, URLs with tokens, or user data; print full stack traces only to protected internal log channels. In systems spanning multiple JDK versions, do not parse exact wording from stack traces as a programmatic protocol.

## 11. What Happens If Iteration Continues After ServiceConfigurationError?

Per the Java 17 Javadoc, after `Iterator.hasNext()` or `next()` throws `ServiceConfigurationError`, subsequent calls make a **best-effort** attempt to locate remaining providers, with **no guarantee of recovery**. A malformed configuration file can stall the iterator or trigger repeated errors in sequence.

Therefore:

- **Mandatory SPIs** such as authentication, policy, or logic where completeness of the provider set is a safety invariant: typically fail closed and do not run with a partial set.
- **Optional plugins** may allow degraded mode if the host defines an error boundary, caps retry/iteration steps, logs rejected providers, and reports partial status.
- **Do not write `while(iterator.hasNext())` with `hasNext` outside `try`**: parse errors can still escape.
- **Do not call `iterator.next()` indefinitely after an error** expecting automatic skipping.
- **Do not call `reload()` as a way to fix a descriptor**. `reload()` clears the `ServiceLoader` cache; it does not repair JARs, module descriptors, constructors, or dependencies.
- **Do not swap JAR/loader sources while the same iterator is in flight** and expect predictable results. On redeploy, create a fresh loading session following lifecycle rules.

Where plugins can be structured as independent artifacts with a plugin manager controlling class loaders, isolating discovery per package helps keep one broken JAR from breaking other plugins. However, that approach requires managing parent delegation and SPI identity rather than spawning arbitrary `URLClassLoader` instances.

## 12. Common Diagnostic Pitfalls

| Symptom | Common Mistake | How to Fix |
| --- | --- | --- |
| Class exists in JAR, yet `NO_PROVIDER` | Assuming `.class` presence lets `ServiceLoader` auto-scan implementations | Check `META-INF/services` or module `provides` |
| `ServiceConfigurationError` from wrong class name | Inspecting only the right class's constructor in source | Inspect the **actual descriptor line** specifying which class is requested |
| "not a subtype" despite `implements` in source | Treating identical class names as identical types | Compare class loaders/modules and the runtime API JAR |
| Constructor takes one parameter, no public no-arg | Assuming Java always generates a default constructor | Add an explicit public no-arg constructor or switch to an explicit module factory if appropriate |
| Constructor throws, yet log lacks cause | Catching `Error` and printing only `getMessage()` | Log stack trace and `getCause()` |
| Provider module not found | Checking only that the JAR is on `--module-path` | Check resolved modules and service loader scope |
| Named consumer lacks `uses` | Editing only `provides` in the provider | Add `uses` to the consumer named module |
| `Factory.provider()` returns `null` | Thinking returning `null` means "no provider" | This is a configuration/instantiation error; use a different capability-selection mechanism |
| Module factory class does not implement SPI | Applying classpath rules to an explicit named module | Verify `public static` no-arg `provider()` returns a subtype of the SPI |
| `module-info` compilation fails | Trying to catch `ServiceConfigurationError` at runtime | Fix JLS module declarations before build |
| Iterator stops advancing after catch | Infinite retry loop | Stop or cap steps; never promise recovery |
| Error persists after `reload()` | Cache cleared, yet broken artifact remains unchanged | Fix the JAR/module and create an appropriate loader |
| Provider method runs, yet business method fails | Lumping business errors into descriptor errors | Separate discovery phase from invocation phase |

A rare but important case: if `ClassLoader.getResources` fetches a service descriptor over an **HTTP URL** and the server returns **200 OK with an HTML page for a missing path** instead of 404, `ServiceLoader` can try to parse the HTML as provider names and throw `ServiceConfigurationError`. This is why you must verify resource origins—not only JAR contents—in environments using network URLs in class loaders.

## 13. Quick Investigation Checklist

Before closing a `ServiceConfigurationError` investigation, be able to answer:

1. **Is this classpath, an automatic module, or an explicit named module?**
2. **What is the exact service type** (class/interface), and what are its `ClassLoader` and `Module`?
3. **Where does the registration come from**: `META-INF/services/<SPI>` or `provides` in `module-info`?
4. **If classpath**: does the descriptor have the exact name, location, UTF-8 encoding, and class names; does the class really exist in the runtime JAR?
5. **If JPMS**: does the consumer declare `uses`, does the provider declare `provides`, is the module resolved, and are the loader/layer correct?
6. **Instantiation mechanism**: public no-arg constructor or `provider()` in a supported context? Does it throw or return `null`?
7. **Subtype and dependencies**: is the provider assignable to the runtime service `Class` object, and are any libraries or ABIs missing?
8. **Failure stage**: `ServiceLoader.load`, `hasNext`, `next`, `Provider.get`, or business invocation?
9. **Cause/logging**: have service/provider names, artifact, module, class loader, stack trace, and cause chain been recorded?
10. **Fix and regression test**: was the artifact/config fixed at the right stage and re-run against a clean classpath/module graph?

**Reinforcement exercises:** (a) change `classpath-lab`'s `good` descriptor to `demo.providers.DoesNotExist` and compare the result with `typo`; (b) update `NeedsArgument` to add a public no-arg constructor and verify `no-ctor` turns into `FOUND`; (c) enable `--trace` to classify constructor throws vs. `wrong-type`; (d) in `module-lab`, remove `uses` from the consumer and then restore it; (e) make `Factory.provider()` return `null` and then fix it; (f) run service lookup with a loader that cannot see the descriptor and explain why finding zero providers is **not necessarily** a `ServiceConfigurationError`.

## 14. Standard References and Conclusion

- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): *Deploying service providers*, *Errors*, `iterator()`, `stream()`, `load(ModuleLayer,...)`, `reload()`.
- [Java SE 17 — ServiceConfigurationError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceConfigurationError.html): `Error` hierarchy and purpose.
- [Java SE 17 — ServiceLoader.Provider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.Provider.html): `type()`, `get()`, and instantiation errors.
- [JLS 17 — Module Declarations / Service Provision](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.4): rules for `provides` and provider methods.
- [Java SE 17 — jar](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html) and [javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): inspecting artifact contents, constructors, and APIs.

**Conclusion:** `ServiceConfigurationError` is an **error signal at the discovery, loading, or instantiation boundary of a provider**, not a single-cause diagnosis. To investigate properly, first identify **classpath descriptor vs. JPMS registration**, then verify the exact class loader/module, inspect subtype/constructor or provider method, read the cause chain, and reproduce with a minimal artifact. Finding no provider, failing to instantiate a provider, and failing during provider execution are **three distinct states**; distinguishing them is essential to fixing the root cause and preventing recurring issues in plugin systems.
