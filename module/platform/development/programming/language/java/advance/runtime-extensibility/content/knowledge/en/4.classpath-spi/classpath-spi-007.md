# Classpath SPI Failure Lab: Wrong Service Name, Missing Constructor, and Missing Resource

Java Service Provider Interface (SPI) lets a host locate implementations via **java.util.ServiceLoader** without hardcoding concrete class names. Yet a single wrong character in the descriptor name, a provider missing a suitable constructor, or a resource omitted from the JAR produces different runtime behavior. This lesson builds **five experimental JAR packages** from the same Java 17+ codebase, runs each package in its own process, and explains why each failure occurs.

**Scope:** SPI running on the **classpath** (unnamed modules), declaring providers via **META-INF/services**. With the Java Platform Module System (JPMS) on the module path, `provides`/`uses` syntax and provider instantiation rules differ; do not apply all classpath constructor rules from this example directly to the module path.

## 1. Three Points That Can Fail in the ServiceLoader Lifecycle

Before experimenting, separate three stages to avoid misdiagnosing failures:

1. **Finding service configuration (discovery):** `ServiceLoader` searches for resources at the exact path `META-INF/services/<binary name of SPI interface>`. If no matching descriptor is found, iterating over `ServiceLoader` can return **0 providers**, even though the implementation class is still inside the JAR.
2. **Reading, checking, and instantiating providers:** the class name on each descriptor line must exist, be accessible, be compatible with the SPI, and be instantiable under classpath rules. During provider iteration, errors such as a misspelled class name or missing public no-argument constructor are typically reported via **`ServiceConfigurationError`**.
3. **Using the provider:** a validly loaded provider can still fail inside its business method when needing a resource omitted from the JAR. That is an **implementation/resource failure**, not necessarily a `ServiceLoader` discovery error.

Example descriptor for interface `dev.lab.spi.Greeter`:

~~~text
META-INF/services/dev.lab.spi.Greeter
~~~

Valid content of that file:

~~~text
dev.lab.plugin.HelloGreeter
~~~

The **file name** is the fully qualified name of the service interface, not the implementation name. The **file contents** are one or more binary names of implementation classes, one name per line. The descriptor is a UTF-8 text file under `META-INF/services` at the classpath/JAR root. Blank lines and comments starting with `#` are allowed, but a wrong path or wrong class name will not be auto-corrected by Java.

Hypothesis table for comparing experiment results:

| Intentional Change | Affected Stage | Expected Result in Sample Host |
| --- | --- | --- |
| No changes | Discovery → instantiation → `greet` call | OK: Xin chào, Java! |
| Wrong **descriptor file name** | Cannot find configuration for `Greeter` | NO_PROVIDER |
| Misspelled **class name inside descriptor** | Found configuration yet cannot find provider class | CONFIG_ERROR |
| Provider lacks **public no-argument constructor** | Cannot instantiate provider on classpath | CONFIG_ERROR |
| Missing **messages/greeting.txt** in JAR | Provider instantiates yet `greet` cannot read file | RESOURCE_ERROR: messages/greeting.txt not found |

The labels `NO_PROVIDER`, `CONFIG_ERROR`, and `RESOURCE_ERROR` in the table are **strings printed by the test program**, not standard JVM error codes. We intentionally standardize output so the experiment stays consistent across JDK versions; during real diagnostics, always inspect the full cause inside the exception.

## 2. Preparing the Lab Directory Tree

Paths below are relative to the root directory **lab/**:

~~~text
lab/
├── src/
│   ├── api/dev/lab/spi/Greeter.java
│   ├── plugin/dev/lab/plugin/HelloGreeter.java
│   ├── plugin/dev/lab/plugin/NeedsArgsGreeter.java
│   └── host/dev/lab/host/Host.java
├── descriptors/
│   ├── good/META-INF/services/dev.lab.spi.Greeter
│   ├── bad-file/META-INF/services/dev.lab.spi.Greeters
│   ├── bad-provider/META-INF/services/dev.lab.spi.Greeter
│   └── no-ctor/META-INF/services/dev.lab.spi.Greeter
└── resources/
    └── messages/greeting.txt
~~~

The **build/** and **dist/** directories will be created by compile commands later. Each `descriptors` branch is an independent configuration set for one experimental package; do not place multiple conflicting descriptor sets into the same JAR simultaneously.

This lab requires only **JDK 17 or higher** and the `javac`, `jar`, and `java` tools included with the JDK. The shell commands use bash/POSIX syntax; on Windows you can run them in a compatible bash environment, or switch to PowerShell and change classpath separators as instructed below.

## 3. Writing Shared Source Code for All Cases

### 3.1. API/SPI Known to Both Host and Plugin

File **src/api/dev/lab/spi/Greeter.java**:

~~~java
package dev.lab.spi;

public interface Greeter {
    String greet(String name);
}
~~~

`Greeter` is the **shared contract**. We compile it into an API JAR and place that JAR on the host's classpath. Implementations will be compiled against this same API; do not package a separate copy of `Greeter` inside the plugin JARs in the commands below.

### 3.2. Valid Provider with Its Own Resource

File **src/plugin/dev/lab/plugin/HelloGreeter.java**:

~~~java
package dev.lab.plugin;

import dev.lab.spi.Greeter;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;

public final class HelloGreeter implements Greeter {
    public HelloGreeter() {
        // Public no-argument constructor: ServiceLoader can call it.
    }

    @Override
    public String greet(String name) {
        try (InputStream input =
                HelloGreeter.class.getResourceAsStream("/messages/greeting.txt")) {
            if (input == null) {
                throw new IllegalStateException(
                        "messages/greeting.txt not found");
            }
            String prefix =
                    new String(input.readAllBytes(), StandardCharsets.UTF_8).strip();
            return prefix + ", " + name + "!";
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }
}
~~~

File **resources/messages/greeting.txt** has a single line:

~~~text
Xin chào
~~~

Notes on resources:

- A path starting with **/** in `Class.getResourceAsStream` denotes an absolute path from the **classpath root of the class's defining loader**. The JAR must contain the entry `messages/greeting.txt`.
- If that entry is absent, the method returns **`null`**; the code explicitly throws `IllegalStateException` with a clear message.
- The resource is read when calling `greet`, **after the provider has been discovered and instantiated**. Thus missing-resource errors in this lab are not converted by `ServiceLoader` into `CONFIG_ERROR`.
- `strip()` removes trailing newline characters; decoding as UTF-8 keeps the Vietnamese content independent of the machine's default charset.

### 3.3. Provider Intentionally Missing a Suitable Constructor

File **src/plugin/dev/lab/plugin/NeedsArgsGreeter.java**:

~~~java
package dev.lab.plugin;

import dev.lab.spi.Greeter;

public final class NeedsArgsGreeter implements Greeter {
    private final String prefix;

    public NeedsArgsGreeter(String prefix) {
        this.prefix = prefix;
    }

    @Override
    public String greet(String name) {
        return prefix + ", " + name + "!";
    }
}
~~~

This class **compiles cleanly** and implements `Greeter` with the right type, yet declares only a constructor taking a `String`. A class that already declares a parameterized constructor **does not get an auto-generated no-argument constructor from Java**. For a provider listed in `META-INF/services` on the classpath, `ServiceLoader` requires a public no-argument constructor to instantiate it and will report `ServiceConfigurationError` when it cannot obtain one.

Do not confuse this with a `public` class **declaring no constructors at all**: the compiler can generate a default no-argument constructor with matching access, so that case would not reproduce a missing-constructor failure.

### 3.4. Host to Observe Results

File **src/host/dev/lab/host/Host.java**:

~~~java
package dev.lab.host;

import dev.lab.spi.Greeter;
import java.util.ServiceConfigurationError;
import java.util.ServiceLoader;

public final class Host {
    public static void main(String[] args) {
        int found = 0;

        try {
            for (Greeter provider : ServiceLoader.load(Greeter.class)) {
                found++;
                try {
                    System.out.println("OK: " + provider.greet("Java"));
                } catch (IllegalStateException ex) {
                    System.out.println("RESOURCE_ERROR: " + ex.getMessage());
                }
            }

            if (found == 0) {
                System.out.println("NO_PROVIDER");
            }
        } catch (ServiceConfigurationError ex) {
            System.out.println("CONFIG_ERROR");
        }
    }
}
~~~

The `for` loop actively **iterates** over `ServiceLoader`. Merely calling `ServiceLoader.load(...)` without iterating is insufficient to prove a provider can be instantiated: `ServiceLoader` loads and instantiates providers **lazily**. In this example, each host run places only **one** plugin JAR on the classpath to avoid discovery interference from other experimental JARs.

The host catches `ServiceConfigurationError` in the outer block because discovery/instantiation errors can arise as the iterator advances to a provider. The host catches `IllegalStateException` around `greet` solely to illustrate the intentional resource error. In real systems, log the **exception and root cause**: do not merely print a label as in this lab.

## 4. Creating Descriptors for Four Variants

Create the exact files below; they are files **without an extension** after the interface name.

**A. Valid configuration:** `descriptors/good/META-INF/services/dev.lab.spi.Greeter`

~~~text
dev.lab.plugin.HelloGreeter
~~~

**B. Wrong file name:** `descriptors/bad-file/META-INF/services/dev.lab.spi.Greeters`

~~~text
dev.lab.plugin.HelloGreeter
~~~

In B, **the file contents are right yet the file name has an extra `s`**. `ServiceLoader` is called with `Greeter.class`, so it looks for `META-INF/services/dev.lab.spi.Greeter` specifically; the file named `Greeters` does not match. This is the **no-provider-discovered** case.

**C. Wrong class name inside:** `descriptors/bad-provider/META-INF/services/dev.lab.spi.Greeter`

~~~text
dev.lab.plugin.HeloGreeter
~~~

In C, the descriptor file name is right, yet **`HeloGreeter`** is missing an `l` compared to the actual class `HelloGreeter`. `ServiceLoader` finds the descriptor and attempts to resolve the misspelled class name, resulting in **`ServiceConfigurationError`** during iteration. It does not silently ignore this error and report `NO_PROVIDER`.

**D. Provider missing public no-arg constructor:** `descriptors/no-ctor/META-INF/services/dev.lab.spi.Greeter`

~~~text
dev.lab.plugin.NeedsArgsGreeter
~~~

In D, both the file name and class name are right; the problem arises only when `ServiceLoader` attempts to instantiate `NeedsArgsGreeter`.

Case **E (missing resource)** reuses descriptor A, while intentionally omitting `resources/messages/greeting.txt` from the JAR.

## 5. Compiling Classes and Packaging Five JARs

From the root directory `lab/`, run sequentially in bash/POSIX:

~~~bash
mkdir -p build/api build/plugin build/host dist

javac -encoding UTF-8 -d build/api src/api/dev/lab/spi/Greeter.java
jar --create --file build/api.jar -C build/api .

javac -encoding UTF-8 -cp build/api.jar -d build/plugin src/plugin/dev/lab/plugin/HelloGreeter.java src/plugin/dev/lab/plugin/NeedsArgsGreeter.java
javac -encoding UTF-8 -cp build/api.jar -d build/host src/host/dev/lab/host/Host.java

jar --create --file dist/good.jar -C build/plugin . -C descriptors/good . -C resources .
jar --create --file dist/bad-file.jar -C build/plugin . -C descriptors/bad-file . -C resources .
jar --create --file dist/bad-provider.jar -C build/plugin . -C descriptors/bad-provider . -C resources .
jar --create --file dist/no-ctor.jar -C build/plugin . -C descriptors/no-ctor . -C resources .
jar --create --file dist/no-resource.jar -C build/plugin . -C descriptors/good .
~~~

**Explanation of packaging commands:**

- `javac -d` creates class files matching the package tree, such as `build/plugin/dev/lab/plugin/HelloGreeter.class`.
- `build/api.jar` contains `Greeter.class` and is placed on the **shared** classpath at compile time and runtime.
- `-C build/plugin .` packages implementation classes from the root of `build/plugin` into the root of the JAR; entry names carry no `build/plugin` prefix.
- `-C descriptors/good .` places `META-INF/services` at the right location at the JAR root.
- `-C resources .` places `messages/greeting.txt` at the JAR root.
- `no-resource.jar` **omits** the `-C resources .` argument, making it a package with valid provider/descriptor yet missing the resource needed to execute `greet`.

Both implementation classes are present in all JARs to simplify the build. A class residing inside a JAR **does not mean** it is a registered provider: only the class named in the `Greeter` descriptor is selected by `ServiceLoader`. Therefore `good.jar` never attempts to instantiate `NeedsArgsGreeter`, even though that class is also in the archive.

Directly inspect the key entries:

~~~bash
jar --list --file dist/good.jar
jar --list --file dist/bad-file.jar
jar --list --file dist/no-resource.jar
~~~

Inside `good.jar`, you must see:

~~~text
dev/lab/plugin/HelloGreeter.class
dev/lab/plugin/NeedsArgsGreeter.class
META-INF/services/dev.lab.spi.Greeter
messages/greeting.txt
~~~

`jar --list` may also list `META-INF/MANIFEST.MF` and directory entries; the four lines above are **the entries to confirm**, not the entire stdout of `jar`. In `bad-file.jar`, the descriptor entry must be `META-INF/services/dev.lab.spi.Greeters`. In `no-resource.jar`, `messages/greeting.txt` must **not** appear.

## 6. Running Each Experiment Independently

Run five separate Java processes; in each process, the classpath contains only **host classes, the API JAR, and one single experimental JAR**:

~~~bash
for case_name in good bad-file bad-provider no-ctor no-resource; do
    printf '%s -> ' "$case_name"
    java -cp "build/host:build/api.jar:dist/$case_name.jar" dev.lab.host.Host
done
~~~

**Exact expected stdout** with the files and source code above:

~~~text
good -> OK: Xin chào, Java!
bad-file -> NO_PROVIDER
bad-provider -> CONFIG_ERROR
no-ctor -> CONFIG_ERROR
no-resource -> RESOURCE_ERROR: messages/greeting.txt not found
~~~

The **:** character separates `-cp` entries on Linux/macOS; when running Java directly in **Windows PowerShell/CMD**, replace it with **;**. Note that `for`/`printf` above is bash syntax; you can invoke each `java` command individually in a Windows shell.

Each result has a distinct meaning:

### Experiment 1 — Valid Package

`ServiceLoader` finds descriptor `Greeter` → reads `HelloGreeter` → loads class → finds public no-arg constructor → instantiates provider → host calls `greet` → `HelloGreeter` finds `messages/greeting.txt` → prints `OK`. The resource is read via the classpath without needing the file next to the working directory.

### Experiment 2 — Wrong Service File Name

`bad-file.jar` contains the implementation class and full resource, yet `ServiceLoader` sees no file named **META-INF/services/dev.lab.spi.Greeter**. No provider is registered for that SPI, so the `for` loop does not run and `found = 0`. This is **`NO_PROVIDER`**, not an instantiation error. Fixing the descriptor file name requires no Java code changes.

### Experiment 3 — Wrong Declared Class Name

`bad-provider.jar` has a descriptor with the **right SPI name**, yet inside it lists `HeloGreeter`. When iterating over providers, `ServiceLoader` attempts to find a class by that name and throws `ServiceConfigurationError`. The host prints `CONFIG_ERROR`. Unlike Experiment 2, the error occurred **after the service configuration was discovered**. Fixing the **descriptor contents** is the solution.

### Experiment 4 — Missing Required Constructor

`no-ctor.jar` lists the exact name `NeedsArgsGreeter`. That class exists and implements `Greeter`, yet declares only `NeedsArgsGreeter(String)`. When running on the classpath, `ServiceLoader` does not know how to supply a `String` value automatically and finds no public no-argument constructor; the outcome is standardized as `CONFIG_ERROR`. Fix this by providing a **valid public no-arg constructor**, or designing a provider/DI mechanism with an explicit contract instead of assuming classpath `ServiceLoader` will auto-inject constructor arguments.

### Experiment 5 — Missing Provider Resource

`no-resource.jar` still validly registers `HelloGreeter`. The `for` loop receives the provider, the host calls `greet`, and then `getResourceAsStream` returns `null`. The program reports `RESOURCE_ERROR` because `HelloGreeter` itself threw `IllegalStateException`. **`ServiceLoader` already completed discovery and instantiation successfully**. If a provider reads a resource inside its constructor and the constructor throws an error, `ServiceLoader` can wrap the instantiation cause inside `ServiceConfigurationError`; **where the resource is read** affects where the failure surfaces.

## 7. How to Diagnose Without Guessing

When an SPI fails to work, inspect in execution order:

**Step 1 — Identify which service the host is requesting.** Read the exact call `ServiceLoader.load(Greeter.class)`. The binary name to register is `dev.lab.spi.Greeter`. Do not deduce the descriptor file name from the implementation class name.

**Step 2 — List entries inside the deployed JAR.** Use `jar --list --file path/to/plugin.jar`. Check the exact names `META-INF/services/dev.lab.spi.Greeter` and `messages/greeting.txt`. Package names, letter case, and dots in the descriptor name all matter. A file misplaced under `src/main/resources/META-INF/services` **inside the JAR** (carrying an extra source prefix) will not match the path `ServiceLoader` expects.

**Step 3 — Read the descriptor contents after building.** You can extract the JAR in a separate inspection directory, or view it with a ZIP tool, to verify each line contains the fully qualified provider name. For the demo, run:

~~~bash
jar --extract --file dist/good.jar META-INF/services/dev.lab.spi.Greeter
~~~

The command above extracts the file into the current directory, so only run it from an **empty inspection directory** if you want to avoid overwriting an existing file of the same name. The descriptor does not use Java `import` syntax, does not contain a `.class` suffix, and does not use a path like `dev/lab/plugin/HelloGreeter.class`.

**Step 4 — Check the class and constructor.** Use `javap` to inspect public signatures:

~~~bash
javap -public -classpath dist/good.jar dev.lab.plugin.HelloGreeter
javap -public -classpath dist/no-ctor.jar dev.lab.plugin.NeedsArgsGreeter
~~~

In `HelloGreeter` you will see `public HelloGreeter()`; in `NeedsArgsGreeter` there is only `public NeedsArgsGreeter(java.lang.String)`. Ensure the provider class is `public`, assignable to the SPI, and has an appropriate constructor. If the constructor itself throws an exception, inspect the cause rather than merely changing the descriptor.

**Step 5 — Distinguish provider not found from resource not found.** If iteration yields **0 providers**, investigate descriptor/classpath/loader first. If the provider was instantiated yet a method fails, inspect the implementation's classes/resources/dependencies. Use `HelloGreeter.class.getResourceAsStream("/messages/greeting.txt")` to look up a resource relative to the class's loader; do not use on-disk paths like `src/main/resources/messages/greeting.txt` when running from a JAR.

**Step 6 — Inspect the full exception when debugging.** The lab host intentionally normalizes errors; when exact diagnostics are needed, replace the `ServiceConfigurationError` catch body with:

~~~java
ex.printStackTrace(System.err);
~~~

Inspect all underlying causes as well, such as missing provider class, wrong type, missing constructor, error thrown inside the constructor, or missing runtime dependency. Do not assume every `ServiceConfigurationError` is caused by a misspelled descriptor name.

## 8. Subtle Distinctions That Often Cause Confusion

| Situation | Key Takeaway |
| --- | --- |
| Descriptor misnamed so provider is unseen | Typically yields empty iteration; Java **does not scan all classes implementing SPI** to infer providers |
| Descriptor exists yet contains wrong class name | Iteration can throw `ServiceConfigurationError`; do not silently turn it into "0 providers" |
| Class declares no constructors | Compiler may generate a default no-arg constructor; check actual access rather than skimming source code |
| Class has only parameterized constructors | Does not automatically get a no-arg constructor; classpath `ServiceLoader` does not auto-inject dependencies |
| Public constructor throws an error | Still a provider instantiation failure; inspect the exception cause |
| Provider created yet method lacks a required resource | Error occurs when using the provider; depends on how the implementation handles `null`/IO exceptions |
| Resource file exists in source yet is absent from JAR | IDE run may succeed while packaged deployment fails; inspect the **built artifact** |
| Provider class name valid yet outside runtime classpath | Discovering the descriptor can still fail at the provider class-loading step |
| Plugin API appears under two different class loaders | Two types with the same name are not necessarily compatible; keep the SPI provided by a shared loader |
| Multiple providers present | Discovery order can depend on classpath and loader setup; do not rely on arbitrary order |
| Called `ServiceLoader.load` without iterating | Has not verified the provider can be instantiated; iterate or actively obtain providers |
| Provider on JPMS module path | Provider rules and module declarations differ; distinguish classpath experiments from module path |

**ClassLoader and TCCL:** the `ServiceLoader.load(Greeter.class)` overload uses the current thread's context class loader to find providers; in the lab's `java -cp` command, the main thread sees the JARs on the application classpath by default. A complex plugin host with separate loaders should consider the `ServiceLoader.load(Greeter.class, pluginLoader)` overload while ensuring the `Greeter` API keeps a unified class identity. If a framework relies on the thread context class loader (TCCL), the host must set/restore it within the proper scope to avoid leaking context across plugins.

**Resources and exceptions:** `Class.getResourceAsStream("/x")` takes a `/` path from the classpath root; `ClassLoader.getResourceAsStream("x")` uses a path without a leading `/`. Do not use `System.getProperty("user.dir")` to infer resource locations inside a JAR. Read resources via `InputStream`, close resources, and check for `null` as shown in the example.

**Classpath and packaging:** In Maven/Gradle, classes and `src/main/resources` are normally included in the JAR under default settings, yet you should still verify the final artifact and runtime dependencies. Do not confuse the **compile** classpath with the **runtime** classpath. Adding a library to the build does not guarantee the host loads that library. Do not package two separate copies of the SPI API under different loaders if both sides must exchange SPI objects.

**Safety:** A descriptor file is merely a declaration list of providers; it does not authenticate the code vendor. The host must control which plugin JARs are permitted to be installed, API versions, artifact provenance, permissions, and error/lifecycle handling. `ServiceLoader` does not automatically create a sandbox for untrusted plugins.

## 9. Reinforcement Exercises and Completion Criteria

You can repeat the experiment with small variations, testing one factor at a time:

1. **Remove the descriptor from `good.jar`:** build a JAR containing only classes and resources. Prediction: `NO_PROVIDER`. Reason: missing service registration despite the class existing.
2. **Keep the descriptor right yet change contents to a class not implementing `Greeter`:** `ServiceLoader` will reject the incompatible provider type. An actually existing class is needed to distinguish this from a misspelled class name.
3. **Add a public no-arg constructor to `NeedsArgsGreeter`, then rebuild:** if the constructor creates a valid object, `no-ctor` no longer fails on construction; also check the return value and any resources if the implementation needs them.
4. **Place the resource at `messages/Greeting.txt` instead of `messages/greeting.txt`:** test exact path lookup when deployed on a case-sensitive system.
5. **Run the host with two plugin JARs simultaneously:** observe how `ServiceLoader` discovers configurations and see why each initial test had to run in a process with a controlled classpath.

An experiment is considered complete when you can accurately explain:

- **`NO_PROVIDER`** means `ServiceLoader` found no declared provider for the requested service on the current classpath (in the corresponding experiment).
- **`CONFIG_ERROR`** is a failure while reading/interpreting provider declarations or loading/instantiating a provider; inspect the cause to tell whether it is a class name or constructor issue.
- **`RESOURCE_ERROR`** in the lab appears **after the provider was already created**, because the implementation could not find its needed data file.
- Fixes must be applied at the **right layer**: descriptor name, descriptor contents, constructor/provider, or resource inside the released JAR.

The most valuable test method is **packaging real JARs, loading only the exact artifact under test, iterating `ServiceLoader`, and observing each stage**. Once you separate discovery, instantiation, and execution, you will avoid editing Java code for a packaging bug, or editing descriptors when the real cause is an omitted resource.