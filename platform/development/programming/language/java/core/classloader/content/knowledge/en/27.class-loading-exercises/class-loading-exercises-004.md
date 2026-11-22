# Lab: Isolating Two Library Versions in Two ClassLoaders (Java 17+)

A classic **Java ClassLoader** scenario is when two plugins both need a library that has the **same fully qualified class name**, but different versions or behaviors. For example:

- Plugin A needs `lib.Formula` version **v1**: `evaluate(x) = x + 1`.
- Plugin B needs `lib.Formula` version **v2**: `evaluate(x) = x * 10`.
- Both implement the `spi.Calculator` interface provided by the host application.

If all JARs are on the **same application classpath/class loader**, both class files carry the name `lib.Formula`; a single defining loader cannot own **two runtime classes with the same binary name**. In this lab, we create **two distinct `URLClassLoader` instances** sharing the same parent. Each loader reads its own JAR and defines its own version of `lib.Formula`; at the same time, both use the **same runtime interface `spi.Calculator`** via parent delegation.

**Expected result:** Two plugins with the same implementation binary name `plugins.CalculatorImpl` still operate side by side with different results, without causing a `ClassCastException` when the host casts them to `spi.Calculator`. We will directly inspect class identity, defining loader, static state, and a control case using a single shared loader.

## 1. Learning Objectives and Prerequisites

After this lab, you will be able to:

1. Explain why **(binary name, defining class loader)** determines runtime class identity.
2. Package two versions of a library with the **same package/class name** into two separate JARs.
3. Create **two `URLClassLoader` instances**, each having only the JAR URL of the version it needs.
4. Place the **SPI/shared API in the parent** so instances from both plugins can be cast to a common interface.
5. Prove that **A's `lib.Formula` differs from B's `lib.Formula`** even though their names are identical.
6. Prove that static fields/caches of each runtime class are independent.
7. Run a control case with **one loader containing both JARs** to observe namespace collision/version selection by URL order.
8. Identify reasons why isolation fails: the parent classpath being "polluted" with private libraries, wrong loader, duplicated SPI, mismatched resource discovery, or binary compatibility errors.
9. Know how to manage lifecycle, close loaders, and avoid mistaking a class loader for a security sandbox.

**Prerequisites:** JDK 17 or later with `javac`, `java`, and `jar` on PATH; Bash/Linux/macOS/Git Bash or Windows PowerShell terminal. The code uses Java 17-compatible syntax/APIs and requires no Maven/Gradle, external libraries, or IDE.

This is a **standard classpath/JAR lab**, without using `module-info.java`. At the end of the article, there is a comparison with JPMS/module layers.

## 2. Architecture: One Host and Two Plugin Namespaces

```text
                  HOST / APPLICATION CLASSLOADER
                    ├── host.TwoVersions
                    └── spi.Calculator
                              ^
                              | parent delegation
              +---------------+-----------------+
              |                                 |
       URLClassLoader A                  URLClassLoader B
       URLs: [plugin-v1.jar]             URLs: [plugin-v2.jar]
          |                                 |
          +-- plugins.CalculatorImpl        +-- plugins.CalculatorImpl
          |                                 |
          +-- lib.Formula (v1)              +-- lib.Formula (v2)
              evaluate(x)=x+1                  evaluate(x)=x*10
```

The two `lib.Formula` versions have the **same binary name**, but different runtime identities because **defining loader A** is different from **defining loader B**:

```text
("lib.Formula", Loader A) != ("lib.Formula", Loader B)
```

Similarly, `plugins.CalculatorImpl` in JAR A and JAR B are two distinct runtime classes.

Meanwhile:

```text
a.loadClass("spi.Calculator")
    == b.loadClass("spi.Calculator")
    == spi.Calculator.class
```

because both loaders **delegate** loading `spi.Calculator` to the parent, where there is only **one** interface definition. The host uses this interface to communicate with both implementation instances.

### Note: Two Separate Loaders Do Not Automatically Isolate Everything

`URLClassLoader` uses **parent-first delegation** by default. If the parent **already has `lib.Formula`**, both A and B can immediately pick up the parent's class and **not use** the private class in their respective JAR. Therefore, the host's runtime classpath in this lab **only** contains `out/host` — never add `out/v1`, `out/v2`, or `plugin-v1.jar` / `plugin-v2.jar` to the host's `-cp`.

In real-world systems, you must clearly separate:

| Where to Place? | Class/Package | Reason |
|---|---|---|
| **Parent/host** | `spi.Calculator`, host APIs, shared DTO | One runtime type identity for both the host and the two plugins |
| **Loader A** | `lib.Formula` v1, `plugins.CalculatorImpl` for A | Private dependency and implementation |
| **Loader B** | `lib.Formula` v2, `plugins.CalculatorImpl` for B | Private dependency and implementation |
| **Do not place in parent** | Any private version of `lib.Formula` | Prevent parent-first from "overriding" the child's version |
| **Do not package into each plugin JAR** | A copy of `spi.Calculator` | Avoid identity mismatch/SPI class duplication |

## 3. Create the Project Structure

The lab uses **five Java source files**:

```text
two-version-lab/
├── src/
│   ├── host/
│   │   ├── spi/
│   │   │   └── Calculator.java
│   │   └── host/
│   │       └── TwoVersions.java
│   ├── v1/
│   │   └── lib/
│   │       └── Formula.java
│   ├── v2/
│   │   └── lib/
│   │       └── Formula.java
│   └── plugin/
│       └── plugins/
│           └── CalculatorImpl.java
├── out/
│   ├── host/
│   ├── v1/
│   └── v2/
└── dist/
    ├── plugin-v1.jar
    └── plugin-v2.jar
```

**Why does the implementation have only one source file?** We want to demonstrate that the **same implementation code** can link against **two different library class definitions** when compiled/packaged separately. The same file `src/plugin/plugins/CalculatorImpl.java` is compiled **twice**: the first time together with the v1 library into `out/v1`, and the second time together with the v2 library into `out/v2`.

**Why does `lib.Formula` have two source files with the same fully qualified name?** To represent two real versions of a library — they must be compiled **into two separate output folders**, and must not be placed into a single `-d` directory.

## 4. Write the Shared SPI in the Host

File **`src/host/spi/Calculator.java`**:

```java
package spi;

public interface Calculator {
    String version();
    int apply(int value);
}
```

This is the **contract** that the host knows in advance. `version()` is used to observe the result, while `apply(int)` invokes the functionality provided by the plugin.

A good plugin design only lets the host communicate through **types defined by the parent/shared loader**; do not let the SPI's public method signatures expose a private type like `lib.Formula` (because the two loaders have two different types).

If complex objects need to be passed, use shared DTOs/records or interfaces defined by the host rather than passing `lib.Formula` objects directly across the boundary.

## 5. Create Library Version v1

File **`src/v1/lib/Formula.java`**:

```java
package lib;

public final class Formula {
    private static int calls;

    private Formula() {}

    public static String version() {
        return "v1";
    }

    public static int evaluate(int value) {
        ++calls;
        return value + 1;
    }

    public static int calls() {
        return calls;
    }
}
```

In v1, `evaluate(3)` returns **4**. `calls` is the **static state** of the runtime class `lib.Formula` defined by the corresponding loader.

This file only uses standard Java and has no dependency on `spi.Calculator`.

## 6. Create Library Version v2

File **`src/v2/lib/Formula.java`**:

```java
package lib;

public final class Formula {
    private static int calls;

    private Formula() {}

    public static String version() {
        return "v2";
    }

    public static int evaluate(int value) {
        ++calls;
        return value * 10;
    }

    public static int calls() {
        return calls;
    }
}
```

In v2, `evaluate(3)` returns **30**.

The two source files have the **same package `lib`, same class `Formula`, and same method signatures**, but different implementations. This is a good scenario for testing isolation because it does **not** merely use classes with different names, but actually involves a **binary-name collision**.

### What If the Two Versions Have Different APIs?

This lab intentionally keeps the signatures identical to compare behaviors clearly. In real products, one version might replace `evaluate` with a different method. When a plugin is compiled against v2 but the runtime accidentally loads v1, `NoSuchMethodError`, `NoSuchFieldError`, `AbstractMethodError`, or other linking errors can occur depending on the type of change. Proper isolation ensures each plugin sees the exact dependency version it was built/tested with.

## 7. Create the Plugin Implementation (Compiled Twice)

File **`src/plugin/plugins/CalculatorImpl.java`**:

```java
package plugins;

import lib.Formula;
import spi.Calculator;

public final class CalculatorImpl implements Calculator {
    @Override
    public String version() {
        return Formula.version();
    }

    @Override
    public int apply(int value) {
        return Formula.evaluate(value);
    }
}
```

This file **does not hard-code "v1" or "v2"**. It calls the `lib.Formula` found in the namespace of the class loader that defines `plugins.CalculatorImpl`.

At runtime, the bytecode of `CalculatorImpl` contains a **symbolic reference** to `lib.Formula`. When the JVM needs to resolve this reference, the loader associated with the defining class `plugins.CalculatorImpl` participates in locating the related class. For loader A, `lib.Formula` is v1; for loader B, `lib.Formula` is v2.

In this lab, both `CalculatorImpl` and `Formula` belong to the same plugin JAR and are defined by the same child loader; this keeps each plugin's dependency graph consistent.

**Do not attempt to have plugin A directly import an implementation class of plugin B** in this isolation design: they are separate namespaces, and cross-plugin type references require an explicit contract/delegation.

## 8. Write the Host Program: Two Separate Loaders and One Control Loader

File **`src/host/host/TwoVersions.java`**:

```java
package host;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import spi.Calculator;

public final class TwoVersions {

    private static Calculator plugin(URLClassLoader loader)
            throws Exception {
        Class<?> type = loader.loadClass("plugins.CalculatorImpl");
        return (Calculator) type.getDeclaredConstructor()
                .newInstance();
    }

    public static void main(String[] args) throws Exception {
        ClassLoader parent = TwoVersions.class.getClassLoader();
        URL v1 = Path.of(args[0]).toUri().toURL();
        URL v2 = Path.of(args[1]).toUri().toURL();

        try {
            parent.loadClass("plugins.CalculatorImpl");
            System.out.println("Parent sees implementation: true");
        } catch (ClassNotFoundException expected) {
            System.out.println("Parent sees implementation: false");
        }

        try (URLClassLoader a =
                     new URLClassLoader(new URL[]{v1}, parent);
             URLClassLoader b =
                     new URLClassLoader(new URL[]{v2}, parent);
             URLClassLoader both =
                     new URLClassLoader(new URL[]{v1, v2}, parent)) {

            Calculator c1 = plugin(a);
            Calculator c2 = plugin(b);

            System.out.println("Version A: " + c1.version());
            System.out.println("Version B: " + c2.version());
            System.out.println("Result A(3): " + c1.apply(3));
            System.out.println("Result B(3): " + c2.apply(3));

            Class<?> aImpl = a.loadClass("plugins.CalculatorImpl");
            Class<?> bImpl = b.loadClass("plugins.CalculatorImpl");

            System.out.println("Different implementation classes: "
                    + (aImpl != bImpl));

            System.out.println("Different dependency classes: "
                    + (a.loadClass("lib.Formula")
                        != b.loadClass("lib.Formula")));

            System.out.println("Same shared SPI class: "
                    + (a.loadClass("spi.Calculator")
                        == b.loadClass("spi.Calculator")));

            System.out.println("Loader A owns plugin: "
                    + (aImpl.getClassLoader() == a));

            System.out.println("Loader B owns plugin: "
                    + (bImpl.getClassLoader() == b));

            System.out.println("Calls A: "
                    + a.loadClass("lib.Formula")
                       .getMethod("calls").invoke(null));

            System.out.println("Calls B: "
                    + b.loadClass("lib.Formula")
                       .getMethod("calls").invoke(null));

            Calculator shared = plugin(both);
            System.out.println("Shared loader version: "
                    + shared.version());
            System.out.println("Shared result (3): "
                    + shared.apply(3));
            System.out.println("Shared version remains: "
                    + plugin(both).version());
        }
    }
}
```

The program uses **three** loader instances for direct comparison:

- `a`: has **only** the v1 JAR URL.
- `b`: has **only** the v2 JAR URL.
- `both`: has **both URLs**, v1 before v2, serving as a **control case** — not a design that satisfies the requirement to use both versions simultaneously.

Each child loader receives the **same `parent`**, which is the defining loader of `host.TwoVersions`. Because the host also contains `spi.Calculator`, both A and B delegate the SPI to the same parent.

### Analyzing the plugin(URLClassLoader) Snippet

```java
Class<?> type = loader.loadClass("plugins.CalculatorImpl");
return (Calculator) type.getDeclaredConstructor().newInstance();
```

This is an **excerpt** from the full program above. `loadClass` takes the binary name `plugins.CalculatorImpl`. Reflection invokes the public no-arg constructor and creates the object. Finally, it casts the object to **the host's `spi.Calculator`**.

The cast succeeds because both JARs contain only the `plugins.CalculatorImpl` implementation and the private `lib.Formula` library. There is no separate `spi/Calculator.class` file inside the two plugin JARs; the host interface is already provided by the defining parent.

### Why Use try-with-resources?

`URLClassLoader` implements `Closeable`. After the lab finishes, `try-with-resources` calls `close()` on A, B, and both to release the JAR/file handles managed by the loaders.

**`close()` is not "unloadClass"**: already-defined classes can still remain alive as long as strong references exist. In production, do not close a loader before the plugin stops receiving work and completes its lifecycle, because a closed loader may no longer be able to read new classes/resources from its URLs.

## 9. Compile and Package on Linux/macOS/Git Bash

From the `two-version-lab` directory:

```bash
mkdir -p out/host out/v1 out/v2 dist

# Host contains only the SPI and the test program.
javac --release 17 -d out/host \
  src/host/spi/Calculator.java \
  src/host/host/TwoVersions.java

# Plugin v1: compile Formula v1 + the same CalculatorImpl.
# The compile classpath contains only the shared SPI in out/host.
javac --release 17 -cp out/host -d out/v1 \
  src/v1/lib/Formula.java \
  src/plugin/plugins/CalculatorImpl.java

# Plugin v2: Formula v2 + CalculatorImpl compiled separately.
javac --release 17 -cp out/host -d out/v2 \
  src/v2/lib/Formula.java \
  src/plugin/plugins/CalculatorImpl.java

# Package the two JARs without including spi.Calculator in a plugin JAR.
jar --create --file dist/plugin-v1.jar -C out/v1 .
jar --create --file dist/plugin-v2.jar -C out/v2 .

# Important: ONLY out/host is on the runtime -cp.
java -cp out/host host.TwoVersions \
  dist/plugin-v1.jar dist/plugin-v2.jar
```

**Classpath paths on Windows use a different separator** when there are multiple entries: Windows uses `;`, while Linux/macOS use `:`. In this demo, the runtime classpath has only **one** directory `out/host`, so no delimiter is needed; the two JAR paths are **program arguments**, not elements of `-cp`.

### Verify the Two JARs Are Truly Independent

After building:

```bash
jar --list --file dist/plugin-v1.jar
jar --list --file dist/plugin-v2.jar
```

Both must contain the following entries (there may also be manifest and directory entries):

```text
lib/Formula.class
plugins/CalculatorImpl.class
```

**You should not see**:

```text
spi/Calculator.class
host/TwoVersions.class
```

in the plugin JAR. If they are present, the build process included shared API/host code in the plugin artifact; review the packaging to avoid class identity/contract duplication issues later.

## 10. Equivalent Commands on Windows PowerShell

```powershell
New-Item -ItemType Directory -Force -Path out/host, out/v1, out/v2, dist | Out-Null

javac --release 17 -d out/host src/host/spi/Calculator.java src/host/host/TwoVersions.java

javac --release 17 -cp out/host -d out/v1 src/v1/lib/Formula.java src/plugin/plugins/CalculatorImpl.java

javac --release 17 -cp out/host -d out/v2 src/v2/lib/Formula.java src/plugin/plugins/CalculatorImpl.java

jar --create --file dist/plugin-v1.jar -C out/v1 .
jar --create --file dist/plugin-v2.jar -C out/v2 .

java -cp out/host host.TwoVersions dist/plugin-v1.jar dist/plugin-v2.jar
```

These commands also work when paths contain spaces if appropriately quoted when constructing the corresponding commands. To verify which JDK is being used:

```powershell
java -version
javac -version
```

If the terminal cannot find `javac` or `jar`, check the JDK (not just a JRE) and `JAVA_HOME`/PATH. Do not automatically take pre-compiled classes from an IDE without knowing which compile target and output directories the IDE is using.

## 11. Verified Experimental Output

The set of **5 Java source files** and two JARs above were compiled with **`javac --release 17`** and run on JDK 24 with Java 17 compatibility. Exact stdout for the order **v1 then v2**:

```text
Parent sees implementation: false
Version A: v1
Version B: v2
Result A(3): 4
Result B(3): 30
Different implementation classes: true
Different dependency classes: true
Same shared SPI class: true
Loader A owns plugin: true
Loader B owns plugin: true
Calls A: 1
Calls B: 1
Shared loader version: v1
Shared result (3): 4
Shared version remains: v1
```

This is the **output of the program itself**, not a JVM verbose class-loading log.

### Interpreting Each Output Line

| Output Line | Meaning |
|---|---|
| `Parent sees implementation: false` | The host does **not** see `plugins.CalculatorImpl`; the implementation is not accidentally on the application classpath |
| `Version A: v1` | Loader A resolves `lib.Formula` from the v1 JAR |
| `Version B: v2` | Loader B resolves `lib.Formula` from the v2 JAR |
| `Result A(3): 4` | Version v1 executes `3 + 1` |
| `Result B(3): 30` | Version v2 executes `3 * 10` |
| `Different implementation classes: true` | `plugins.CalculatorImpl` of A and B are **two different `Class<?>` instances** |
| `Different dependency classes: true` | `lib.Formula` of A and B are **two different runtime classes** |
| `Same shared SPI class: true` | Both use the same runtime interface defined by the parent |
| `Loader A/B owns plugin: true` | Correct defining loader, not defined on their behalf by the parent or a shared loader |
| `Calls A/B: 1` | Each `lib.Formula` has its **own static field `calls`**; each ran once, so each equals 1 |
| `Shared loader version: v1` | The loader with URL v1 before v2 picks one implementation/Formula class from v1 |
| `Shared result (3): 4` | The shared loader executes v1 behavior; it does not automatically choose "v2 for another request" |
| `Shared version remains: v1` | Calling to load the implementation multiple times on the same loader still yields the same runtime type, without switching to v2 |

### Why Do the Two Versions Keep Separate Static State?

`static int calls` belongs to a runtime class, not to the name `"lib.Formula"` across the entire JVM. Therefore:

```text
("lib.Formula", Loader A).calls = 1
("lib.Formula", Loader B).calls = 1

Those are two separate static variables belonging to two runtime classes.
```

If there were a shared `lib.Formula` library defined by the parent, both plugins could share **the static state of the parent's version**, violating the isolation requirement.

## 12. Additional Control Test: Reversing the Order of the Two JARs

No source code changes are needed. Reverse the order of the arguments:

```bash
java -cp out/host host.TwoVersions \
  dist/plugin-v2.jar dist/plugin-v1.jar
```

PowerShell:

```powershell
java -cp out/host host.TwoVersions dist/plugin-v2.jar dist/plugin-v1.jar
```

Verified output:

```text
Parent sees implementation: false
Version A: v2
Version B: v1
Result A(3): 30
Result B(3): 4
Different implementation classes: true
Different dependency classes: true
Same shared SPI class: true
Loader A owns plugin: true
Loader B owns plugin: true
Calls A: 1
Calls B: 1
Shared loader version: v2
Shared result (3): 30
Shared version remains: v2
```

**Explanation:**

- `a` receives the first URL (now v2), `b` receives the second URL (v1): **each loader still accurately isolates** the version assigned to it.
- `both` receives the URL array `[v2, v1]`: with the default `URLClassLoader` and no identically named class in the parent, it searches the URLs in order and picks v2.
- `both` **cannot define another `plugins.CalculatorImpl`/`lib.Formula` with the same binary name** from the remaining JAR after v2 has already been picked.

This control test shows that **URL order affects a single shared loader**, rather than automatically providing multi-versioning. This ordering is `URLClassLoader`'s class/resource lookup rule when using a single URL search path; with application servers/containers/custom loaders, the lookup policy may differ.

## 13. The Two Versions Do Not Create a Shared Type for the Implementation

The results in Section 11 prove that `a.loadClass("lib.Formula") != b.loadClass("lib.Formula")`, even though their binary names are identical: **different defining loaders create different runtime types**. Similarly, the two `plugins.CalculatorImpl` versions cannot be cast directly to one another. However, both can still be cast to **one `spi.Calculator` defined by the parent**.

| Type | Defining loader | Shared across both plugins? |
| --- | --- | --- |
| `lib.Formula` v1/v2 | A and B, respectively | No, each is a private dependency |
| `plugins.CalculatorImpl` v1/v2 | A and B, respectively | Cannot cross-cast between implementations |
| `spi.Calculator` | Host/parent | Yes, it is the shared contract |

Within the scope of `main`, you can run additional checks:

```java
Class<?> aType = a.loadClass("plugins.CalculatorImpl");
Class<?> bType = b.loadClass("plugins.CalculatorImpl");
System.out.println(aType.getName().equals(bType.getName())); // true
System.out.println(aType == bType); // false
System.out.println(bType.isInstance(c1)); // false
```

**Reflection does not unify class identity.** It can invoke methods on an object belonging to a specific loader, but type checks, access, and JVM constraints still apply. Do not put the private `lib.Formula` into the public signature of `spi.Calculator`; communicate through host-defined APIs/DTOs.

## 14. When Isolation Fails: Parent Classpath Polluted with the Library

Imagine the host is misconfigured:

```bash
# NOT the right way to run this lab:
java -cp "out/host:dist/plugin-v1.jar" \
  host.TwoVersions dist/plugin-v1.jar dist/plugin-v2.jar
```

On Windows, use `";"` instead of `":"` in `-cp` if you want to reproduce this, but **do not use the incorrect command as a production configuration**.

At this point, the parent/application class loader can find:

```text
plugins.CalculatorImpl
lib.Formula
```

in `plugin-v1.jar`. Because `URLClassLoader` **delegates parent-first** by default, both A and B can receive the parent's class (instead of the class from their own JAR):

```text
a.loadClass("plugins.CalculatorImpl") -> Parent class
b.loadClass("plugins.CalculatorImpl") -> Parent class
a.loadClass("lib.Formula")            -> Parent v1
b.loadClass("lib.Formula")            -> Parent v1
```

This can cause version B's output to no longer be v2, `Different implementation classes` to no longer be true, and `getClassLoader() == b` to be `false`.

**How to fix:** Place private implementations/dependencies only in the plugin loader's URL list. In the parent, keep **shared SPIs/contracts** and libraries that genuinely need to be shared between the host and plugins.

### What If the Parent Needs That Same Library?

When a host framework is forced to carry `lib.Formula` in the parent, you may need a **namespace-scoped custom child-first loader** to let the plugin use a private copy, or build-time relocation/shading, or process-level plugin isolation. You should not override `loadClass` as child-first for **every** package: doing so breaks `java.*`, shared APIs, logging/reflective integration, and type identity.

If you actually implement a custom policy, typically:

```text
java.* / platform.*       -> always parent/platform
spi.* / shared.api.*      -> parent first
plugin private namespaces -> child first, controlled fallback
others                    -> defined policy (usually parent first)
```

This is **policy pseudocode**, not a complete Java implementation. You must handle `getClassLoadingLock`, `findLoadedClass`, `resolveClass`, class loading errors, and the corresponding resource policy.

## 15. Common Errors During the Lab

### Error 1 — ClassNotFoundException When the Host Tries to See the Plugin

In the demo, there is an intentional line:

```java
parent.loadClass("plugins.CalculatorImpl");
```

and it catches `ClassNotFoundException` to print `Parent sees implementation: false`. This is the **expected result**, because the host must not contain the implementation class.

If `a.loadClass("plugins.CalculatorImpl")` throws `ClassNotFoundException` instead, that is not expected. Check:

- Does `plugin-v1.jar` already contain the `plugins/CalculatorImpl.class` entry?
- Does `Path.of(args[0]).toUri().toURL()` point to the correct JAR file?
- Is the binary name `plugins.CalculatorImpl` spelled with the exact package/class?
- Was a directory URL missing a trailing `/` or an unsupported URL protocol accidentally used?

### Error 2 — NoClassDefFoundError: spi/Calculator

The plugin implementation needs to resolve the shared interface `spi.Calculator`. If the host does not have this interface or the child's parent cannot see the host SPI, the JVM can fail when defining/linking the implementation.

**How to fix:** Ensure `spi.Calculator` is in `out/host` and the child loaders use the proper parent containing the SPI. Do not solve this by sneaking an independent copy of the interface into each plugin without checking type identity.

### Error 3 — ClassCastException with Two Versions of spi.Calculator

If a custom child-first policy defines its own separate `spi.Calculator` in A and B, objects from A/B may fail to cast to the `spi.Calculator` interface that the host is using, **even though the names are identical**.

**How to fix:** Ensure a single shared defining loader for the SPI. Print:

```java
System.out.println(
    a.loadClass("spi.Calculator") == Calculator.class);
```

This is a snippet inside a method that has variable `a` and imports `spi.Calculator`. The expected result is `true`.

### Error 4 — NoSuchMethodError or IncompatibleClassChangeError

An implementation was built with library v2, but at runtime it accidentally resolves `lib.Formula` v1 with a different API. The JVM may throw `NoSuchMethodError` or an appropriate `LinkageError` when it needs to resolve the method/class.

**How to fix:** Identify which loader defines the runtime `lib.Formula` and which JAR provides the class. Build/test the matching implementation + dependency pair, rather than relying solely on Maven dependency declarations.

### Error 5 — Static State Is Not Separated

If `Calls A` and `Calls B` are not independent after running both plugins, you might be:

- using a `lib.Formula` class defined by the parent;
- using a single shared loader containing both JARs;
- storing counters/state in a **shared class** defined by the parent;
- accidentally keeping a host-wide singleton holding plugin state.

**How to fix:** Inspect `Class.getClassLoader()` of the private dependency and where static fields are declared. Class identity is what determines static storage.

### Error 6 — Package Sealing or Signer Mismatch

Two JARs with the same package name in the **same loader** can sometimes also encounter `SecurityException` due to JAR manifest `Sealed: true` or different signer certificate sets. Two separate plugin loaders create separate runtime packages, but do not turn a signed JAR into a trusted one or eliminate all classloading checks.

**How to fix:** Check your packaging/manifest/signing policy; do not catch the error and silently fall back to another class source.

### Error 7 — Resource from Another Version

`ClassLoader.getResource` and `getResources` have their own lookup policy. If you write custom child-first class loading while leaving resources parent-first, v2 code might read v1's config/schema. Organize resource namespaces per plugin, use the right loader, or use `SomePluginClass.class.getResourceAsStream` when appropriate. For `META-INF/services`, multiple provider descriptors must be preserved rather than picking only a single resource.

### Error 8 — Closing the Loader Too Early

`URLClassLoader.close()` prevents loading **new** classes/resources provided by that loader according to its contract. Closing it immediately after creating an instance and then running a long-lived plugin can cause errors when code uses a dependency or resource for the first time later on.

**How to fix:** Tie the loader to the plugin lifecycle; stop requests/tasks, unregister services, close resources, and only then close the loader.

## 16. Observing Class Origins via JVM Logs and Java APIs

### 16.1. Printing the Defining Loader

In the demo's `main` method, we already have:

```java
System.out.println(aImpl.getClassLoader() == a);
System.out.println(bImpl.getClassLoader() == b);
```

This confirms **defining loader object identity**. Do not just print the class name `lib.Formula` and conclude which version it belongs to, because both names are identical.

You can supplement this with code source information:

```java
Class<?> formulaA = a.loadClass("lib.Formula");
var pd = formulaA.getProtectionDomain();
var source = pd == null ? null : pd.getCodeSource();
System.out.println(source == null
        ? "(unknown)"
        : source.getLocation());
```

This is an **illustrative snippet** inside a method. Code source is an indicator of origin, **not proof that all code is safe/trusted**, and in a custom loader it may be `null`.

### 16.2. Enabling Class Loading Logs (HotSpot/OpenJDK)

```bash
java '-Xlog:class+load=info' -cp out/host \
  host.TwoVersions dist/plugin-v1.jar dist/plugin-v2.jar
```

PowerShell:

```powershell
java "-Xlog:class+load=info" -cp out/host host.TwoVersions dist/plugin-v1.jar dist/plugin-v2.jar
```

The log can show multiple `plugins.CalculatorImpl` / `lib.Formula` events from two different JARs. Depending on the JVM, logging verbosity, and class loading timing, the source URL format, timestamps, and line ordering vary. **Do not write exact stdout assertions** against VM diagnostic logs; use them to observe class origins and cross-check with `getClassLoader()`.

### 16.3. Explicit Loader Class Lookup API

```java
Class<?> v1Type = Class.forName("lib.Formula", false, a);
Class<?> v2Type = Class.forName("lib.Formula", false, b);
System.out.println(v1Type == v2Type); // false
```

This is a snippet with variables `a` and `b`. The `Class.forName(name, initialize, loader)` overload lets you specify the loader explicitly; `false` does not request initialization. **The single-argument `Class.forName("lib.Formula")`** does not automatically use a plugin loader or the thread context class loader: it uses the defining loader of the calling class. From the host, if `lib.Formula` is not in the parent, the single-argument call can fail.

## 17. How to Organize When Adding a Third Plugin?

Each plugin can be associated with a **generation/loader scope**:

```text
Host + shared SPI
    |
    +-- Plugin A / Loader A / lib.Formula v1
    +-- Plugin B / Loader B / lib.Formula v2
    +-- Plugin C / Loader C / lib.Formula v3
```

A plugin manager should keep metadata:

- Plugin ID and version.
- Source JAR path/URL.
- Loader instance and parent.
- Implementation class name.
- Compatible shared SPI type/version.
- Instance/start/stop state.
- Service/resource registrations.
- Thread pool/TCCL policy and cleanup hooks.

Do not let an implementation class or private dependency object from loader A enter B's API without an appropriate contract. If plugins need to interact, use host-defined shared interfaces/DTOs, a message bus, or adapters.

### Hot-Reload Is Not Redefining in the Same Loader

If `plugin-v1.jar` is replaced with a new version on disk, the already-defined runtime class `("lib.Formula", A)` **does not automatically change**. Nor can a loader call `defineClass` a second time with the same binary name to create a new runtime type within the same loader.

Typically, you create a **new loader generation**, load/configure the new plugin, route requests to that generation, and then stop the old generation. Once no references remain from the host/threads/caches, the old loader may become eligible for reclamation by the JVM/GC; **there is no API to request arbitrary, immediate class unloading**.

### Unload and Close

`URLClassLoader.close()` closes the resources/JAR handles managed by the loader; class unloading is decided by the JVM/GC and depends on loader reachability. `close()` does not immediately invalidate already-loaded `Class<?>` objects or instances.

Sources that keep an old loader alive: plugin instances in registries, `ServiceLoader` caches, event listeners, thread pool TCCLs, `ThreadLocal`s, scheduled tasks, reflection handles, logging/JDBC/MBeans, and other host references.

## 18. When Should You Use a Custom ClassLoader or JPMS Instead of URLClassLoader?

### Choose URLClassLoader When

- Each plugin consists of one or a few standard JARs/directories.
- The parent contains only appropriate shared API/JDK dependencies.
- Parent-first delegation is sufficient to ensure the private library from the child is used.
- No custom resource policy or bytecode transformations are needed.

This lab falls squarely into this case. **There is no need to override `loadClass` or write `defineClass` directly** to achieve isolation.

### Consider a Custom ClassLoader When

- A dependency with the same binary name **is already on the parent**, yet the plugin must use its private copy, requiring child-first **only for a specific namespace**.
- Classes come from memory/remote storage/a specialized container.
- A custom resource lookup/`getResources` priority policy is needed, with tests to prevent mismatches.
- There is codegen/transformation or a plugin framework coordinating complex namespaces.

When overriding `loadClass` yourself, you must check locking/`findLoadedClass`/`resolveClass` and not catch/swallow `LinkageError` as if it were `ClassNotFoundException`. For `java.*` and shared APIs, you must preserve the proper platform/type identities.

### Consider JPMS ModuleLayer When

- Plugin JARs are **named modules** with `module-info.java`, `requires`, `exports`, `opens`, and `provides ... with ...`.
- You need module configuration/readability/service discovery and clear module boundaries.
- There is a requirement to map modules to one or multiple class loaders.

`ModuleLayer.defineModulesWithOneLoader` and `defineModulesWithManyLoaders` are different strategies. **A module is not synonymous with a class loader**, and separating named modules does not necessarily create isolation equivalent to one loader per plugin/JAR. Design the module graph, loader mappings, and package conflicts clearly before changing architecture.

## 19. Security: Two Separate Loaders Are Not Two Sandboxes

**Class loader isolation does not independently restrict file, network, CPU, or operating system access of plugin code**. It primarily isolates **runtime type identity, versioned dependencies, and static state**, and supports lifecycle.

A plugin from an untrusted source running in the same JVM can still cause side effects through many APIs that the process has permission to use. `SecurityManager` is a historical mechanism that was deprecated for removal in JDK 17 and **permanently disabled starting in JDK 24**; do not rely on it as the default sandbox for a modern Java architecture.

For untrusted plugins, consider a separate **worker process/container**, OS permissions, network egress controls, resource quotas, blocking/controlling native access, and a small RPC/IPC contract. Do not infer that "having two `URLClassLoader` instances means plugin A cannot affect B" beyond the scope of class identity.

## 20. Automated Tests Needed for Production Deployment

The observations in the lab can be turned into assertions:

1. The parent does not find `plugins.CalculatorImpl`.
2. Loader A is actually the defining loader of implementation A, and loader B of implementation B.
3. `a.loadClass("lib.Formula") != b.loadClass("lib.Formula")`.
4. `a.loadClass("spi.Calculator") == b.loadClass("spi.Calculator") == Calculator.class`.
5. `c1.version()` returns `v1` and `c2.version()` returns `v2` when A=v1, B=v2.
6. `c1.apply(3) == 4`, `c2.apply(3) == 30`.
7. Static `calls` counters are independent across the two versions.
8. The shared loader containing both JARs picks one version according to URL policy; reverse the URL order as a control check.
9. After activating a plugin, shared API calls work without needing private types from another loader.
10. The plugin lifecycle closes resources/threads and does not retain references to a retired plugin loader.

Do not write tests that strictly depend on **when classes unload** after `System.gc()`; GC is not an on-demand unloading mechanism, and workloads/collectors can vary. Test application-controlled behavior and use profiling/heap retaining paths to investigate memory.

### A Small Challenge: Cross-Checking Identity

In `main`, after obtaining `aImpl`, `bImpl`, and `c1`, add:

```java
System.out.println("Same binary name: "
        + aImpl.getName().equals(bImpl.getName()));
System.out.println("A object is B instance: "
        + bImpl.isInstance(c1));
```

This is an **illustrative insertion**, not part of the original verified stdout. Expected output:

```text
Same binary name: true
A object is B instance: false
```

That is a concise demonstration of the difference between a **name** and a **runtime type**.

### Challenge 2: A New Dependency Only in v2

Create `lib.Extra` only inside the plugin v2 JAR and have the v2 implementation call this class. When keeping two separate loaders, v2 sees `lib.Extra`, while v1 does not need to see it. If you change the app classpath/JAR URLs inconsistently, the experiment may encounter `NoClassDefFoundError`.

This is a **self-directed** extension exercise; you need to add the file/class and recompile. Do not state a fixed output without actually running the extended code.

### Challenge 3: Observing Identically Named Resources

Add `plugin.properties` to both JARs with contents `version=v1` and `version=v2`. Compare `a.getResourceAsStream("plugin.properties")` and `b.getResourceAsStream("plugin.properties")`, and then `both.getResources("plugin.properties")`. You will see that the **resource lookup** problem differs from class identity: a single loader can enumerate **multiple resources with the same name**, whereas there is only one runtime class per binary name.

When designing a child-first loader for classes, you must control the corresponding resource lookup priority if resources are tightly coupled to versions.

## 21. Checklist Before Finishing the Lab

- [ ] Compile the **two `lib.Formula` versions separately**, not into a shared output directory.
- [ ] Both plugin JARs contain `lib/Formula.class` and `plugins/CalculatorImpl.class`.
- [ ] The host output contains only `spi/Calculator.class` and `host/TwoVersions.class`.
- [ ] The runtime command uses `-cp out/host` — **do not** place the plugin JARs on the parent classpath.
- [ ] The two loaders `a` and `b` share the same parent and have **different URL lists**.
- [ ] A returns version v1 / 4; B returns version v2 / 30.
- [ ] The two implementation `Class<?>` objects and the two dependency `Class<?>` objects are distinct.
- [ ] The shared SPI `Class<?>` is the same across A/B and the host.
- [ ] The static counters are independent.
- [ ] A single shared loader containing both JARs picks the first version according to URL order, rather than running two identically named definitions side by side.
- [ ] Tested the control cases with reversed URL order and with the private implementation mistakenly placed on the parent.
- [ ] Know how to close a loader and do not confuse `close` with unload.
- [ ] Understand why runtime type isolation **is not a security sandbox**.

## 22. Self-Check Questions

**1. Two `lib/Formula.class` files have the same name in two JARs. Can they coexist in the JVM?** Yes, if they are defined by **two different defining loaders**.

**2. Why not put both versions into the same defining loader?** A single defining loader owns only one runtime class per binary name; one version can shadow the other.

**3. In the lab, why can the host cast both CalculatorImpl objects to `spi.Calculator`?** Because the interface is defined only by the parent, and both children delegate to the parent.

**4. What happens if you use two URLClassLoaders but add `plugin-v1.jar` to the host `-cp`?** Parent-first delegation can cause the child to return the v1 class defined by the parent, breaking private-version isolation.

**5. Are the two `static int calls` fields of `lib.Formula` shared?** No; they are two static fields in two runtime classes with different defining loaders.

**6. Why does the shared loader's result change from v1 to v2 when reversing the URL order?** `URLClassLoader` searches URLs in order when the parent does not provide the class, and then keeps only one definition with the same binary name in that loader.

**7. Does `Class.forName("lib.Formula")` in the host automatically choose a plugin loader based on the thread context?** No; the single-argument overload uses the defining loader of the calling class. Use the overload with a loader argument if you need to specify one explicitly.

**8. Can two implementation classes with the same name be cast to each other?** Not just because their names match; runtime class identity depends on the defining loader.

**9. Does `URLClassLoader.close()` remove runtime classes immediately?** No; it releases sources/handles per the API, while class unloading is decided by the JVM/GC.

**10. Do two separate class loaders guarantee running untrusted plugin code safely?** No; you need process/OS isolation and controlled execution permissions.

**11. When should you choose a custom child-first loader?** When a private namespace must take precedence over an identically named version on the parent and you already have clear policies for packages, locking, resource lookup, and shared APIs.

**12. At what level does this exercise prove isolation?** **Class identity, dependency version, and static state** of private classes; it does not by itself prove process-security isolation or hot unloading.

## 23. References

- **Java SE 17 `ClassLoader`** — binary names, defining loader, parent delegation, `loadClass`, `findClass`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Java SE 17 `URLClassLoader`** — looking up classes/resources in URL order after parent, `close()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- **JVMS Java SE 17 §5.3 — Creation and Loading** — runtime class identity tied to binary name + defining loader: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- **Java SE 17 `Class.forName`** — overload with explicit name, `initialize`, and loader: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- **Java SE 17 `ServiceLoader`** — using shared service types, provider discovery, TCCL/module variants: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- **Java SE 17 `ModuleLayer`** — alternatives for named-module plugins and loader mappings: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- **JLS Java SE 17 §§12.2–12.4** — loading, linking, and initialization: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html

**Key takeaway:** **Two versions of the same `lib.Formula` can run side by side because they are defined by two different class loaders.** Keep the **SPI/shared contracts in the parent**, while private implementations and dependencies stay in separate JARs/loaders. Always verify `getClassLoader()`, class identity, static state, and URL order; do not confuse "two JARs" with "two namespaces" if they are being loaded by **one loader**.
