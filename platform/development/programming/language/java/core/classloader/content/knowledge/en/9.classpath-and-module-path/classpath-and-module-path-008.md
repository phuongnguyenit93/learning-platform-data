# Multi-release JAR and Selecting Bytecode by Java Version

## 1. What problem does a Multi-release JAR solve?

A Java library sometimes needs to **run on multiple JVM versions** while wanting to take advantage of APIs or more efficient implementations in newer JDKs. If only classes compiled with Java 17 are placed into the JAR, Java 8 cannot load those classes. If only Java 8-compatible classes are kept, the library cannot leverage capabilities introduced in Java 11, 17, or later.

**Multi-release JAR (MR-JAR)**, introduced in **Java 9 by JEP 238**, allows a single JAR file to contain **multiple versions of classes/resources for different Java releases**. The JVM and MR-JAR-aware class loaders select the version appropriate for the **actual running Java runtime**, based on the internal structure of the JAR and the manifest attribute.

Imagine the same binary name `demo.Selector`:

```text
library.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       ├── 11/
│       │   └── demo/Selector.class      (Java 11 version)
│       └── 17/
│           └── demo/Selector.class      (Java 17 version)
└── demo/
    ├── Main.class                       (base version)
    └── Selector.class                   (base version, Java 8)
```

The `demo.Selector` classes with the same name are **mutually alternative variants**. In a single load of this name through a loader reading the MR-JAR, the JVM selects **one appropriate class file**. It does not run all three versions simultaneously and does not create three `Class<?>` objects just because all three files exist in the archive.

This article focuses on **search paths inside a JAR**, **the bytecode selection algorithm**, **how to build a runnable MR-JAR**, **ClassLoader effects**, and **compatibility errors**.

## 2. Conditions for a JAR to truly be multi-release

Simply placing files under `META-INF/versions/` is **not enough**. The JAR must have the main manifest attribute:

```text
Manifest-Version: 1.0
Multi-Release: true

```

The physical file is `META-INF/MANIFEST.MF`. The `Multi-Release: true` attribute must reside in the **main section** (before the blank line separating sections). The value `true` is case-insensitive according to the specification, but should be written consistently as above.

- If this attribute is **absent** or other than `true`, the runtime treats the JAR as a regular JAR when looking up classes; `META-INF/versions/N` entries are not used as versioned alternatives.
- `N` in `META-INF/versions/N` is the **Java feature release number** (for example `9`, `11`, `17`, `21`), **not** the class file major version number.
- The lowest meaningful version for a versioned directory is **9**. The `META-INF/versions/8/` directory does not work as a Java 8-specific branch under MR-JAR rules.
- Entries for Java 8 or lower must reside in the **root directory of the JAR** if the library claims to support them.
- The `META-INF/versions/N` directory must contain the exact same package path as the root version, for example `META-INF/versions/17/com/acme/Foo.class`; it cannot be replaced with a different file name and expect the JVM to map it automatically.

The name `N` must follow the specification's valid positive integer representation; do not use `v17`, `017`, or arbitrary strings. Use `META-INF/versions/17` exactly to create a branch for Java 17.

**Distinguish the two types of versions from the start:**

| Value | Example | Meaning |
|---|---|---|
| Java feature release | `17` | Java 17 JDK/JVM |
| MR-JAR directory | `META-INF/versions/17` | Variant eligible for selection from Java 17 onward when no higher matching version exists |
| Class file major | `61` | Major version of a Java 17 class file |
| Class file minor | `0` | Standard class version without preview features |

`META-INF/versions/17` is a **directory targeting Java 17**; it is not synonymous with `major_version=17` inside the bytecode.

## 3. Entry selection algorithm: highest number not exceeding the runtime

Suppose the runtime is running Java feature version `R` and an MR-aware class loader needs to find a logical entry, such as `demo/Selector.class`.

For Java 9 and later and a JAR with `Multi-Release: true`, the general rule is:

1. Look for the entry with the same path at `META-INF/versions/R/`.
2. If not found, search successively lower version directories, from `R-1` down to **`9`**.
3. Pick the **entry with the highest version ≤ R** if it exists.
4. If no matching versioned entry is found, use the entry in the **root directory**.
5. If the root also does not have a matching entry, looking up that class fails.

```text
Java Runtime R ≥ 9
  search demo/Selector.class
       │
       ▼
META-INF/versions/R/demo/Selector.class?
       │ not found
       ▼
META-INF/versions/(R-1)/demo/Selector.class?
       │ not found
       ▼
... search downward to 9 ...
       │ not found
       ▼
demo/Selector.class at JAR root
       │
       ▼
ClassLoader defines class from selected bytecode
```

**Important:** The runtime **does not necessarily choose a branch whose number exactly equals the version it is running**. If Java 21 sees only `versions/17` and `versions/11`, it chooses **17**, because this is the newest version **not exceeding 21**. If Java 15 has no version 15 but has 11, it chooses 11. Java 8 does not execute Java 9's MR-JAR algorithm and uses the root path like a regular JAR.

### Selection table example

Suppose the JAR contains:

```text
demo/Selector.class
META-INF/versions/11/demo/Selector.class
META-INF/versions/17/demo/Selector.class
META-INF/versions/21/demo/Helper.class
```

When looking up **`demo.Selector`**:

| Java runtime | Selected entry for `demo.Selector` |
|---|---|
| Java 8 | `demo/Selector.class` (root) |
| Java 9, 10 | `demo/Selector.class` (root) |
| Java 11–16 | `META-INF/versions/11/demo/Selector.class` |
| Java 17–20 | `META-INF/versions/17/demo/Selector.class` |
| Java 21+ | `META-INF/versions/17/demo/Selector.class`, if there is no Selector version in a higher branch |

The `versions/21/demo/Helper.class` entry **does not affect** the selection of `Selector.class`: the JVM selects **independently per logical path**, rather than choosing a single directory for the entire JAR.

If only version `17` is present without `11`, Java 11 **falls back to the root**; it does not try to load the Java 17 class from a higher branch and hope the bytecode works.

## 4. “Selecting the right branch” and “compatible bytecode” are two different checks

MR-JAR prioritizes directories by **Java runtime version**, but the JVM still has to read and verify the actual **class file version** of the selected bytes.

In a class file, the initial fields are magic, `minor_version`, and `major_version`. Some mappings:

| Java release | Class file major | Standard minor |
|---|---:|---:|
| Java 8 | 52 | 0 |
| Java 9 | 53 | 0 |
| Java 11 | 55 | 0 |
| Java 17 | 61 | 0 |
| Java 21 | 65 | 0 |
| Java 25 | 69 | 0 |
| Java 26 | 70 | 0 |

A file under `META-INF/versions/17/` **must not** require a class file version higher than what Java 17 supports according to the MR-JAR specification. For example, placing **major 65** bytecode (compiled for Java 21) into the `versions/17` branch is an invalid structure: Java 17 will **select** this entry by path but **cannot load** that bytecode.

- Use `javac --release 8` to produce the root version supporting Java 8.
- Use `javac --release 11` to produce the Java 11 variant.
- Use `javac --release 17` to produce the Java 17 variant.
- A build using JDK 17 or later can compile all three targets if the compiler supports them; there is no need to run `javac` from each target runtime.

`javac --release N` constrains syntax, target class version, and the standard API set of release N during compilation. Merely renaming a directory to `versions/N` **does not turn** bytecode from a newer release into bytecode for N.

**Preview bytecode warning:** `minor=65535` indicates a dependency on preview features of that exact Java version; preview bytecode is not automatically compatible with future Java releases even if the major version is lower. Do not package preview classes as long-term variants just because MR-JAR has a corresponding branch. Prefer code that uses Java APIs and features standardized for the target runtime.

## 5. Complete example: one JAR with three versions for Java 8, 11, and 17

We will create an `mr-demo.jar` consisting of:

- `demo.Main` in the root, compiled for Java 8 compatibility.
- The root version of `demo.Selector` returning the string `"base-8"`.
- The Java 11 version of `demo.Selector` returning `"java-11"`.
- The Java 17 version of `demo.Selector` returning `"java-17"`.

All `Selector` variants keep **the same public API** `public static String selected()`. This is a good pattern to see the JVM actually switch implementations depending on the runtime.

### 5.1. Preparing the source structure

Create the files and directories as follows:

```text
mr-demo/
├── src/
│   ├── base/
│   │   └── demo/
│   │       ├── Main.java
│   │       └── Selector.java
│   ├── v11/
│   │   └── demo/
│   │       └── Selector.java
│   └── v17/
│       └── demo/
│           └── Selector.java
└── out/
    ├── base/
    ├── v11/
    └── v17/
```

The `out` directories have no files yet and will hold the compilation results. Each version of `Selector.java` resides in a **separate source root** because they share the same package/binary name and cannot be placed in the same standard compilation source path.

### 5.2. Java 8 version: src/base/demo/Selector.java

```java
package demo;

public final class Selector {
    private Selector() {
    }

    public static String selected() {
        return "base-8";
    }
}
```

### 5.3. Shared runner class: src/base/demo/Main.java

```java
package demo;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Selected: " + Selector.selected());
    }
}
```

Note that `Main` does not call any API available only from Java 9 onward, because the root version will be compiled with `--release 8`. It references the same logical type `demo.Selector`; which version executes that method is determined when the runtime loads `Selector`.

### 5.4. Java 11 version: src/v11/demo/Selector.java

```java
package demo;

public final class Selector {
    private Selector() {
    }

    public static String selected() {
        return "java-11";
    }
}
```

### 5.5. Java 17 version: src/v17/demo/Selector.java

```java
package demo;

public final class Selector {
    private Selector() {
    }

    public static String selected() {
        return "java-17";
    }
}
```

The 11 and 17 versions in this article only change the output string for easy verification. In real libraries, branches can implement behavior differently (for example, using APIs or algorithms available in newer JDKs), **but must preserve the shared public API contract**.

### 5.6. Compiling each release properly

From the `mr-demo` directory, with **JDK 17 or later** supporting targets 8, 11, and 17, create the three output directories. If using Bash:

```bash
mkdir -p out/base out/v11 out/v17
```

On Windows PowerShell, you can create them with:

```powershell
New-Item -ItemType Directory -Force out/base,out/v11,out/v17 | Out-Null
```

Next, run the following `javac` commands in the terminal:

```bash
javac --release 8 -d out/base src/base/demo/Main.java src/base/demo/Selector.java
javac --release 11 -d out/v11 src/v11/demo/Selector.java
javac --release 17 -d out/v17 src/v17/demo/Selector.java
```

Result:

```text
out/
├── base/
│   └── demo/
│       ├── Main.class
│       └── Selector.class
├── v11/
│   └── demo/
│       └── Selector.class
└── v17/
    └── demo/
        └── Selector.class
```

Do not compile all three `Selector.java` files into **a single output directory**, because classes with the same name will overwrite one another or conflict. Nor are three versions of `Main` needed; `Main` in the root can call the implementation of `Selector` that the JVM selected.

### 5.7. Packaging the multi-release JAR

Using the `jar` tool from JDK 17+:

```bash
jar --create --file mr-demo.jar --main-class demo.Main -C out/base . --release 11 -C out/v11 . --release 17 -C out/v17 .
```

In this command, there are **two different meanings of `--release`**:

- `javac --release N` selects the compilation level and API compatibility for Java N.
- `jar --release N` instructs packaging the following files into `META-INF/versions/N/`.

The `jar` tool creates metadata so the archive is recognized as an MR-JAR, including `Multi-Release: true` in the manifest. Depending on the JDK version, the packaging process may check certain constraints on same-named class versions.

The resulting archive has the logical structure:

```text
mr-demo.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       ├── 11/
│       │   └── demo/Selector.class
│       └── 17/
│           └── demo/Selector.class
└── demo/
    ├── Main.class
    └── Selector.class
```

In `META-INF/MANIFEST.MF`, the important attributes will include:

```text
Manifest-Version: 1.0
Main-Class: demo.Main
Multi-Release: true

```

There may be additional attributes added by the `jar` tool (such as `Created-By`). The manifest file in the archive is not required to contain **exactly only those three lines** as shown in the snippet.

### 5.8. Running on different JVMs

Common command:

```bash
java -jar mr-demo.jar
```

However, the result depends on **the Java version of the `java` command being executed**:

| JVM running the command | Selector variant | Stdout |
|---|---|---|
| Java 8 | Root, targeting Java 8 | `Selected: base-8` |
| Java 9 or 10 | Root | `Selected: base-8` |
| Java 11–16 | `versions/11` | `Selected: java-11` |
| Java 17–20 | `versions/17` | `Selected: java-17` |
| Java 21 or later | `versions/17` if there is no higher variant | `Selected: java-17` |

For example, if running with Java 17, the **exact** stdout of the program is:

```text
Selected: java-17
```

If the machine only has JDK 21 installed, this table describes the behavior of the respective JVMs and does **not** mean a single run on Java 21 can faithfully emulate JVM 8. To verify that Java 8 actually runs it, you must use a Java 8 runtime; to verify Java 11, use a Java 11 runtime. The `javac --release 8` command **does not force `java -jar` to run as Java 8**.

## 6. Verifying the actual JAR and bytecode

You should not verify an MR-JAR solely by the filename `mr-demo.jar`. After building, check the **structure**, **manifest**, **class file version**, and **runtime selection**.

### 6.1. Listing physical entries in the archive

```bash
jar --list --file mr-demo.jar
```

Look for the important entries:

```text
demo/Main.class
demo/Selector.class
META-INF/versions/11/demo/Selector.class
META-INF/versions/17/demo/Selector.class
META-INF/MANIFEST.MF
```

These are **the lines to look for**, not the entire stdout in a fixed order. Listing physical entries shows that the files exist, but **does not tell** which file a specific JVM selected.

### 6.2. Inspecting the class file major version with javap

```bash
javap -verbose -classpath out/base demo.Selector
javap -verbose -classpath out/v11 demo.Selector
javap -verbose -classpath out/v17 demo.Selector
```

In the long output of each command, the expected values respectively are:

```text
base: major version: 52
v11:  major version: 55
v17:  major version: 61
```

The three lines above are a **summary of the results**, not a verbatim stdout snippet from a single `javap` command. `javap -verbose` also displays the constant pool entries, methods, and attributes.

For an MR-JAR, `javap` supports the `--multi-release` option on JDKs that support it. For example:

```bash
javap --multi-release 11 -classpath mr-demo.jar -c demo.Selector
javap --multi-release 17 -classpath mr-demo.jar -c demo.Selector
```

You can use these commands to inspect the effective class version for each target release, instead of accidentally inspecting only the root. If you inspect files inside the JAR directly with a ZIP tool, you must manually pick the right physical entry.

### 6.3. Using jar --validate

```bash
jar --validate --file mr-demo.jar
```

The `jar` tool is capable of checking certain constraints, especially when versioned classes exist. However, **succeeding at the validate step does not prove 100% that the API, dependencies, or runtime behavior of every branch are compatible**. The specification does not require the tool or the JVM to thoroughly verify the equivalence of all public APIs across class versions.

### 6.4. Determining the actual running runtime

```bash
java -version
javac -version
```

The two commands can use two different installations via `PATH`, an IDE, a Gradle toolchain, Docker, or CI. The **JVM runtime** determines the MR-JAR branch when loading; the **compiler** determines the bytecode major version during the build. A release built from CI with JDK 21 and deployed to Java 17 must be verified on an actual Java 17 runtime.

## 7. Each class/resource is selected individually, not the entire JAR as “version 17”

A common misconception is that if the runtime selects version 17, **every class in the JAR** is taken from `versions/17`. In reality, **each logical path** is looked up independently across the chain of versioned directories.

For example:

```text
demo/Api.class
demo/FeatureA.class
demo/FeatureB.class

META-INF/versions/11/demo/FeatureA.class
META-INF/versions/17/demo/FeatureB.class
```

On Java 17:

- `demo.Api` has no versioned entry, so it uses `demo/Api.class` in the root.
- `demo.FeatureA` uses `versions/11/demo/FeatureA.class` (the highest ≤17 among FeatureA's own versions).
- `demo.FeatureB` uses `versions/17/demo/FeatureB.class`.

All three logical classes coexist in **a single application** and can use different optimized versions. This explains why code in one branch can fail if internal APIs between classes are incompatible.

**Resources can also be versioned**, but not just any file under `META-INF` is allowed to be replaced. The specification states that **resources under `META-INF` are not versioned**; for example, a service provider configuration `META-INF/services/...` cannot arbitrarily have a separate copy placed under `META-INF/versions/N/META-INF/services/...` and expect the multi-release mechanism to select it.

If an application/plugin reads ZIP entries at a low level, it can see the physical paths of each version. The result of reading a resource via `ClassLoader.getResource(...)` or `Class.getResource(...)` may depend on the runtime and the loader's JAR-aware implementation; do not assume every ZIP file reading API automatically applies the MR-JAR virtual view.

## 8. When there are multiple JAR/classpath entries: which search order wins?

The `versions/N` rule applies **after a class loader has selected the appropriate JAR source to search for the class name**. It does not replace ClassLoader delegation rules or the order of classpath entries.

For example:

```text
Host Application ClassLoader
    ├── shared.jar (has demo.Selector)
    └── mr-demo.jar (has demo.Selector + versions/11 + versions/17)

Plugin ClassLoader
    └── plugin.jar
```

If the queried loader finds `demo.Selector` from `shared.jar` first under the active policy and classpath order, the `Selector` version in `mr-demo.jar` **may not be considered**. Conversely, if it selects `mr-demo.jar`, then when reading the logical path `demo/Selector.class`, MR-JAR chooses the entry appropriate for the JVM version.

Similarly, if a custom loader inherits the default `ClassLoader.loadClass`, it typically uses the order:

```text
findLoadedClass(name)
    ↓ not found yet
parent.loadClass(name) / bootstrap
    ↓ parent did not find it
findClass(name)
    ↓
resolveClass(c) if requested
```

This policy is **parent-first**. If the parent has already defined `demo.Selector`, the child loader usually will not read the `Selector` variant from its own MR-JAR.

**Two layers of selection must be clearly separated:**

1. **Which ClassLoader** receives and resolves the class request according to delegation/classpath/module path rules?
2. **Inside the selected MR-JAR**, which versioned entry matches the Java runtime?

A custom loader that implements `findClass` using `ZipFile.getEntry("demo/Selector.class")` to read only the root can **bypass** MR-JAR versioning. A loader that wants to support MR-JAR must use an appropriate JAR-reading mechanism instead of assuming the root entry is always the final bytecode.

## 9. JarFile, JarEntry, and the “runtime view”

`java.util.jar.JarFile` is the API for reading JAR contents. With MR-JAR, it is necessary to distinguish:

- **Physical view**: all actual paths inside the ZIP/JAR, including the root and `META-INF/versions/11`, `META-INF/versions/17`.
- **Runtime-selected view**: when looking up the logical name `demo/Selector.class`, the highest version matching the configured release is treated as the entry to use.

According to the Java API, a `JarFile` opened via a regular constructor **does not necessarily automatically apply** MR-aware lookup for the current Java runtime; `JarFile`'s default behavior can treat the JAR as an unversioned archive. When writing a class loader/JAR reader, there is a constructor and a `Runtime.Version` parameter to request viewing for a target version, for example `JarFile(File, boolean, int, Runtime.Version)`.

### Example of reading entries by runtime version (Java 17+)

Create the file `JarViewDemo.java`:

```java
import java.io.File;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.zip.ZipFile;

public final class JarViewDemo {
    private static void check(String path, int feature)
            throws Exception {
        Runtime.Version version = Runtime.Version.parse(
                Integer.toString(feature)
        );

        try (JarFile jar = new JarFile(
                new File(path),
                true,
                ZipFile.OPEN_READ,
                version
        )) {
            JarEntry entry = jar.getJarEntry("demo/Selector.class");
            System.out.println(feature + ": " + entry.getRealName());
        }
    }

    public static void main(String[] args) throws Exception {
        check("mr-demo.jar", 8);
        check("mr-demo.jar", 11);
        check("mr-demo.jar", 17);
        check("mr-demo.jar", 21);
    }
}
```

Assuming `mr-demo.jar` was created properly as in section 5, compile/run this program with JDK 21 (or newer) to have an environment covering levels 8, 11, 17, and 21:

```bash
javac JarViewDemo.java
java JarViewDemo
```

The selected real paths will be:

```text
8: demo/Selector.class
11: META-INF/versions/11/demo/Selector.class
17: META-INF/versions/17/demo/Selector.class
21: META-INF/versions/17/demo/Selector.class
```

**Key distinction:** In this example, `JarFile` is **configured with a view by Runtime.Version** to read the entry; it **does not launch Java code under multiple different JVMs**. The printed result for feature 8 is the base entry in the virtual lookup. To prove the application actually runs on Java 8, you still must run `java -jar mr-demo.jar` with JRE/JDK 8.

Note: The `Runtime.Version` parameter cannot turn the current JVM environment into a different version or help load newer bytecode on an older JVM. This is an API for **selecting which entry to read** from a JAR, serving appropriate analysis/packaging/loader tools.

## 10. Public APIs must be consistent across variants

The MR-JAR specification imposes constraints on the **public API** of class versions. If a public/protected class resides in a versioned directory of a standard MR-JAR, it must “preside over” a corresponding definition with an appropriate name and access level in a lower version/root; public APIs are expected to be equivalent across versions.

This ensures user code does not have to be recompiled for each runtime simply because they move from Java 11 to 17.

### Stable API example — right approach

Root:

```java
package api;

public final class Feature {
    public static String value() {
        return "fallback";
    }
}
```

Version in `versions/17`:

```java
package api;

public final class Feature {
    public static String value() {
        return "optimized";
    }
}
```

These are **two mutually alternative source options** with the same binary name and should not be compiled into the same output directory. They preserve the same public method signature and class characteristics, differing only in implementation.

### Divergent API example — dangerous

Root:

```java
package api;

public final class Feature {
    public static String value() {
        return "fallback";
    }
}
```

The versioned branch changes to:

```java
package api;

public final class Feature {
    // Removed public static String value()!
    public static int valueAsInt() {
        return 1;
    }
}
```

If an application is compiled to call `Feature.value()` but the JVM selects a versioned class that no longer has this method, it can encounter **`NoSuchMethodError`** at linking/usage time, even though the class file major version is valid and the entry is in the right branch. Do not use MR-JAR to silently change public API signatures.

**There are exceptions for non-exported packages in a modular multi-release JAR** according to the module specification, but those are deliberate design cases. For regular libraries running on the classpath, keeping a **consistent public binary API** across all branches is an essential principle.

Do not rely solely on `jar --validate` to prove the API contract: the tool and runtime are not required to verify every condition. You should run binary API checks with dedicated tests/tools and test the application on the supported JDKs.

## 11. ClassLoader and type identity in MR-JAR

When the application ClassLoader defines `demo.Selector` from `versions/17`, that runtime class still has the binary name **`demo.Selector`**. The path `META-INF/versions/17` is **the location of the selected class file**, not part of the binary name or the Java package.

Therefore:

```java
Class<?> selected = Class.forName("demo.Selector");
System.out.println(selected.getName()); // demo.Selector
```

This is a **snippet**; to run standalone it needs a `main` and either handling `ClassNotFoundException` or declaring `throws`. `getName()` does not return `META-INF.versions.17.demo.Selector`.

The `Class<?>` object represents a runtime class defined by its **defining loader**. A runtime does not load multiple variants of the same binary name into **the same defining ClassLoader** and swap them once the Java version is fixed. Once `demo.Selector` is defined, subsequent `loadClass` calls normally return that class.

If there are **two independent defining ClassLoaders**, they can create two runtime classes with the same name from two JARs or even two ways of viewing bytecode. They do not automatically become a single type, because this is the **ClassLoader identity mechanism**, separate from MR-JAR's version selection by runtime.

It is also necessary to distinguish:
- **Loading**: The ClassLoader/JVM locates and defines the runtime class from the selected bytes.
- **Linking**: The JVM verifies/prepares and resolves references as needed.
- **Initialization**: The JVM executes `static` initializer expressions/blocks upon appropriate active use.

MR-JAR **selects the class file to be loaded**; it does not alter Java's initialization rules by itself.

## 12. Java 8, classpath, module path, and compatibility limits

### 12.1. What does Java 8 see?

Java 8 **does not yet have** the multi-release mechanism. It sees `mr-demo.jar` as a regular JAR and uses the class entries in the **root**. Files located under `META-INF/versions/11` or `META-INF/versions/17` are archive entries and do not become versions selected by JVM 8.

That means:

- If Java 8 needs to be supported, the classes required to run the application must have Java 8-compatible versions at the root.
- The root cannot use source syntax/standard APIs available only in Java 11/17.
- Do not place the `Main.class` entry point only in `versions/17` and claim Java 8 can run `java -jar`.
- Dependencies located outside the JAR must also be Java 8-compatible; having root bytecode 52.0 alone is not enough.

### 12.2. Java 9+ on the classpath

With standard class loaders supporting MR-JAR, the appropriate versions are selected automatically when the JAR is on the classpath. Users do not need to call `Class.forName("META-INF.versions.17.demo.Selector")` explicitly — that is not even the class's binary name.

Run:

```bash
java -cp mr-demo.jar demo.Main
```

With JDK 17, the program equivalently selects `versions/17` just like `java -jar mr-demo.jar` in section 5, producing stdout:

```text
Selected: java-17
```

### 12.3. Module path

An MR-JAR can appear on the module path (as an automatic module or an explicit modular multi-release JAR) starting from Java 9, but the **module descriptor** must also obey specific constraints:

- `module-info.class` can be in the root or in a versioned location according to MR modular JAR rules.
- Versioned descriptors must maintain consistency according to the JAR specification; there are certain defined exceptions for platform module requirements and `uses`.
- Public/protected classes in **non-exported** packages have different “preside over” rules compared to exported APIs.

These are **additional** requirements of the module system. The example in section 5 is a **classpath / executable JAR without module-info**, so that the fundamental bytecode selection mechanism is clearly visible.

### 12.4. The bootstrap loader does not support MR-JAR lookup

The specification notes that **the bootstrap class loader does not support MR-JAR** in the same way as regular class loaders. If an MR-JAR is placed on the bootstrap search path using a mechanism such as `-Xbootclasspath/a` (on JVMs that still support it), the archive is treated as a normal JAR. Do not extrapolate the classpath example in section 5 to every special JVM loading location.

## 13. Common errors and how to detect them

| Symptom | Possible cause | How to resolve |
|---|---|---|
| Java 17 still uses the root version | Missing `Multi-Release: true`, wrong path, missing exact entry, non-MR-aware loader, or parent picked a different class | Check the manifest, `jar --list`, defining loader, and classpath |
| Java 11 throws `UnsupportedClassVersionError` | Root or branch 11 contains bytecode exceeding the major version supported by Java 11 | Compile with `javac --release 11` and verify major ≤55 |
| Java 8 fails to run the JAR | Root contains classes newer than Java 8 or lacks classes/dependencies in root | Compile the root with `--release 8`; test on Java 8 |
| Java 21 selects branch 17 | No version 21 exists for the logical class in question | This is the expected fallback: picking the highest matching version ≤21 |
| Versioned class has a different name or package | Entry path does not match the binary name | Place the class version in the exact same package and name as the root |
| `jar --validate`/build reports an API mismatch | A branch changed public signatures/modifiers/constructors | Keep APIs compatible or redesign the branches |
| `NoSuchMethodError` when upgrading the JVM | Runtime selects a branch whose API does not match the caller | Compare public binary APIs and test on the target runtime |
| Only root is used when reading with custom tools | Loader/JarFile opens the physical view or ignores versioned entries | Choose appropriate MR-aware lookup/`Runtime.Version` |
| Debugging via `Class.getName()` does not show the version | The binary name does not contain `versions/N` | Inspect the source code/JAR entry or the proper runtime view |
| Versioned branch contains a class valid only with preview | A JVM of another preview version rejects the class even after selecting the branch | Do not rely on preview features for multi-JDK release MR-JARs |
| “Upgraded JDK yet the old class did not change” | The class was already defined by the loader; process not restarted / loader not replaced | Restart the process or use a designed reload mechanism |

### A systematic debugging sequence

1. Verify the actual **runtime**: `java -version` in the exact execution environment.
2. Verify the JAR is actually on the **classpath/module path** and is not shadowed by another JAR with the same class name or by a parent loader.
3. List **physical entries** with `jar --list --file <jar>`.
4. Check that the main manifest has **`Multi-Release: true`** and valid `META-INF/versions/N/...` paths.
5. Verify the **selected entry** for the logical name on that runtime — via an MR-aware `JarFile`, `javap --multi-release`, or a test run.
6. Verify the **class file major version** of the selected variant itself and its binary API against the compile target.
7. Run tests/smoke tests on **each minimum JDK the library claims to support**, not only the build JDK.

Do not fix issues by manually changing the `major_version` number in a class file: the bytecode instructions, constant pool, and APIs may still require newer JVM features.

## 14. When should you use it and when is it unnecessary?

An MR-JAR is useful when a library simultaneously needs:

- An **older baseline runtime** still used by customers.
- One or more **optimized implementations / implementations leveraging newer APIs** on JDK 9+.
- A single distribution artifact that keeps a stable public API and lets the JVM select automatically.

For example, cryptography, I/O, runtime diagnostics, or networking libraries can have separate implementations for Java 11/17 while the API seen by the application remains the same.

However, MR-JAR increases maintenance responsibility: multiple build targets, multiple bytecode versions for the same binary name, API verification, and a multi-JDK test matrix. If a library only supports Java 17 and later and does not need different implementations by runtime, **a regular JAR compiled with `--release 17` may suffice**. Do not add versioned branches merely to increase directory count without a clear learning/operational benefit.

### Recommended release workflow

- Specify the **minimum JDK** and the list of **truly needed versioned branches**.
- Keep the root complete with the minimum API/implementation.
- Compile **each branch with `--release N`**, isolating output directories.
- Package with `jar --release N` or a build task that creates proper entries and manifest.
- Verify MR-JAR structure, class file versions, and API consistency.
- Run smoke/integration tests with representative Java runtimes, especially the **baseline**, **each branch transition point**, and **the latest supported runtime**.
- Be cautious of shading, repackaging, or fat-JAR layout tools that may alter entry paths/manifest. After outputting the final artifact, **re-read the released artifact itself** instead of only checking intermediate build directories.

## 15. Self-check questions

1. **Which Java version introduced MR-JAR?** Java 9, under JEP 238.
2. **Is creating `META-INF/versions/17` alone enough to activate it?** No; the main manifest attribute `Multi-Release: true` is needed.
3. **Running on Java 21, a JAR has Selector in root, versions/11, and versions/17. What does the JVM use?** `versions/17/demo/Selector.class`.
4. **Running on Java 10, but the JAR only has versioned 11, 17, and root. What does the JVM use?** Root.
5. **Does being under `versions/17` mean class file major=17?** No; Java 17 corresponds to major 61.
6. **Is a class file with major 65 placed under `versions/17` valid for Java 17 to run?** No; Java 17 does not support Java 21 class files.
7. **Do `javac --release 11` and `jar --release 11` do the same thing?** No; one selects the compilation/API target, while the other selects the directory inside the MR-JAR.
8. **Does Java 8 pick `versions/11` if the root entry does not exist?** No; it does not support multi-release lookup.
9. **Does each runtime pick a single directory for the entire JAR?** No; it picks the highest matching version **separately for each logical entry**.
10. **Does having the same binary name `demo.Selector` in root and versions/17 create two different classes in the same defining ClassLoader on a single load?** No; the loader picks one entry for that runtime.
11. **Does lacking version 21 prevent Java 21 from running an MR-JAR with versions/17?** No; Java 21 can use version 17 if compatible.
12. **Does a successful `jar --validate` guarantee that all public APIs and dependencies are completely compatible?** No; additional binary API checks and runtime tests are needed.
13. **Is placing `META-INF/services/...` under `META-INF/versions/N/META-INF/services` the standard way to version service configuration?** No; resources under `META-INF` are not versioned by that mechanism.
14. **If a custom loader only calls `ZipFile.getEntry("demo/Selector.class")`, does it automatically select branch 17?** No; that queries the physical root path, so an MR-aware mechanism must be used if runtime-based selection is desired.

## Authoritative references

- [JEP 238 — Multi-Release JAR Files](https://openjdk.org/jeps/238): motivation and design of the multi-version mechanism in a single JAR.
- [JAR File Specification — Multi-release JAR files, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html): `META-INF/versions/N` structure, manifest, lookup algorithm, bytecode/API constraints, and module rules.
- [The jar Command, JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jar.html): syntax for `jar --create`, `--release`, `--list`, and `--validate`.
- [JarFile API, Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/jar/JarFile.html): runtime version view and `getRealName()`.
- [javap command, JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html): class file analysis and multi-release options.

**Key takeaway:** With a valid MR-JAR, a ClassLoader supporting this mechanism looks up **entries by logical name**, selects the versioned copy with **the highest N not exceeding the running JVM version**, and finally falls back to the root. The selected bytecode must still be compatible with the JVM; a single JAR containing multiple versions does not replace compiling for the right target and testing on each supported runtime.
