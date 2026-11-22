# Package Sealing and Manifest Information

## 1. What Problem Does Package Sealing Solve?

A Java application can place multiple JAR files on the same ClassLoader search path. If two JARs contain classes with the **same package name**, the loader can sometimes load one class from JAR A and another class from JAR B. This is commonly referred to as a **split package on the classpath**.

Example:

~~~text
a.jar
└── demo/locked/Anchor.class

b.jar
└── demo/locked/Other.class
~~~

Without additional rules, a `URLClassLoader` using both JARs can load `demo.locked.Anchor` from A and `demo.locked.Other` from B; both share the same package name and the same defining loader.

**Package sealing** is a mechanism of the JAR format and manifest-aware loaders to enforce that **classes belonging to the same sealed package must come from the same JAR/code source**. When a loader attempts to define a class in the same sealed package from a mismatched source, implementations such as `URLClassLoader` throw a `SecurityException` with a message indicating a *sealing violation*.

It is important to distinguish immediately:

- **Package sealing is not class visibility**: `public`, `private`, package-private, and JPMS `exports`/`opens` are still checked according to their own rules.
- **Package sealing is not JAR digital signing**: `Sealed: true` does not sign bytecode or authenticate the publisher.
- **Package sealing is not an automatic dependency version-locking tool**: it detects certain cases where classes in the same package come from different sources.
- **Package sealing is scoped to the loader defining the package**. Two independent ClassLoaders can still define separate packages with the same name, without merging them into a single JVM-wide package.

In Java 17, `URLClassLoader` uses `Manifest` information when creating a `Package` and when checking subsequent class loads. This is the context for this article.

## 2. Package Name, Runtime Package, and Bytecode Origin

Three related but distinct concepts:

| Concept | Example | Meaning |
|---|---|---|
| Package name | `demo.locked` | Package name written in Java source code |
| Runtime package | `demo.locked` within a specific defining loader (and associated module) | Important for identity and package-private access permissions |
| Code source URL | `file:/.../a.jar` | Where the loader retrieves bytecode from; used in sealing checks |

Two classes with the same package name defined by **two different loaders** do not automatically belong to the same runtime package. Conversely, if the same `URLClassLoader` defines them from two different JARs, package sealing can prevent mixing bytecode from two code sources.

**Order matters:** `Package` metadata is typically determined at the time the package is first defined in the loader. A class loaded early from a JAR can establish the package as sealed or unsealed; subsequent classes must be compatible with that established state.

The JAR specification states that a sealed package requires classes in that package to originate from the same JAR. In the `URLClassLoader` implementation, the comparison is tied to the package's **code source URL**.

## 3. What Is a Manifest and Where Is It Stored?

A standard JAR contains a metadata file:

~~~text
META-INF/MANIFEST.MF
~~~

This is a text file with a **main section** and optional **named sections**. Key attributes for this article:

| Attribute | Scope | Purpose |
|---|---|---|
| `Manifest-Version` | Main | Manifest format version, typically `1.0` |
| `Sealed` | Main or package section | Specifies whether the package is sealed |
| `Specification-Title` | Main or package | Name of the specification that the package implements |
| `Specification-Version` | Main or package | Specification version |
| `Specification-Vendor` | Main or package | Organization providing the specification |
| `Implementation-Title` | Main or package | Implementation name |
| `Implementation-Version` | Main or package | Implementation version |
| `Implementation-Vendor` | Main or package | Implementation vendor |
| `Main-Class` | Main | Entry point for running the JAR with an appropriate launcher; **not sealing** |
| `Class-Path` | Main | May participate in extending the class search path in certain runtimes/loaders; **not sealing** |

Main section example:

~~~text
Manifest-Version: 1.0
Sealed: true

~~~

With this manifest, **the JAR's packages are sealed by default**, unless a package has a named section overriding it. To seal only a single package, place `Sealed: true` in its own section:

~~~text
Manifest-Version: 1.0

Name: demo/locked/
Sealed: true

~~~

**Path note:** `Name: demo/locked/` has a trailing `/`, representing the `demo.locked` package. It is not `Name: demo.locked` and not a filename like `Anchor.class`.

There must be a **blank line** between the main section and a named section. Each section must end according to manifest syntax; when creating the file manually, include a trailing newline. Manifest files follow the line-length/continuation rules of the JAR specification and should not be manually joined into one very long line.

## 4. `Sealed` Precedence Rules: JAR-Wide vs. Per-Package

The cases:

**A. `Sealed` not declared:**

~~~text
Manifest-Version: 1.0

~~~

By default, packages in the JAR are **not sealed** unless specified in a per-package section.

**B. Declared in the main section:**

~~~text
Manifest-Version: 1.0
Sealed: true

~~~

All packages in the JAR are sealed by default.

**C. Main sealed, one package overridden as unsealed:**

~~~text
Manifest-Version: 1.0
Sealed: true

Name: demo/open/
Sealed: false

~~~

The `demo.open` package is unsealed, while other packages remain sealed according to the main section.

**D. Main unsealed, one package overridden as sealed:**

~~~text
Manifest-Version: 1.0
Sealed: false

Name: demo/locked/
Sealed: true

~~~

Only `demo.locked` is sealed per this section; other packages remain unsealed unless overridden elsewhere.

The value of `Sealed` is `true` or `false`, case-insensitive. A specific named section **takes precedence over** the value in the main section. Version and vendor attributes can also have per-package values.

**Note:** Sealing does not apply to the unnamed package; a class that needs to belong to a sealed package must be declared in a named package.

## 5. Java 17+ Hands-On Lab: A Sealed, B Different Source, Open Package Still Works

We will build two JARs from four classes:

~~~text
sealing-demo/
├── a-src/
│   └── demo/
│       ├── locked/Anchor.java
│       └── open/One.java
├── b-src/
│   └── demo/
│       ├── locked/Other.java
│       └── open/Two.java
├── host-src/
│   └── SealingDemo.java
└── manifests/
    ├── a.mf
    └── b.mf
~~~

`a.jar` seals **only** the `demo.locked` package and attaches version metadata. `b.jar` is not sealed. When a `URLClassLoader` sees both A and B:

- Loading `Anchor` from A first → the `demo.locked` package is created in a sealed state at A.
- Loading `Other` from B afterward → `SecurityException` due to a sealing violation.
- The other package `demo.open` is unsealed, so `One` from A and `Two` from B can both be defined by that same loader.
- If `Other` from B is loaded first, the `demo.locked` package starts in an unsealed state; subsequently attempting to load `Anchor` from JAR A, which declares sealing, → also causes a sealing violation.

We use **classes with different names** in the same package to eliminate confusion with the scenario where two JARs contain the exact same FQCN and only one version is found first.

### 5.1. Classes in JAR A: `Anchor`

File **`a-src/demo/locked/Anchor.java`**:

~~~java
package demo.locked;

public final class Anchor {
    private Anchor() {
    }

    public static String origin() {
        return "ANCHOR_A";
    }
}
~~~

File **`a-src/demo/open/One.java`**:

~~~java
package demo.open;

public final class One {
    private One() {
    }

    public static String origin() {
        return "ONE_A";
    }
}
~~~

### 5.2. Classes in JAR B: `Other`

File **`b-src/demo/locked/Other.java`**:

~~~java
package demo.locked;

public final class Other {
    private Other() {
    }

    public static String origin() {
        return "OTHER_B";
    }
}
~~~

File **`b-src/demo/open/Two.java`**:

~~~java
package demo.open;

public final class Two {
    private Two() {
    }

    public static String origin() {
        return "TWO_B";
    }
}
~~~

All four classes depend only on standard Java. The host will load them by string name and reflection; **do not import** any `demo.locked.*` or `demo.open.*` class so the host application does not inadvertently place them into another defining loader.

### 5.3. Manifest for A with Per-Package Metadata

File **`manifests/a.mf`** (create with a trailing newline):

~~~text
Manifest-Version: 1.0
Implementation-Title: Example A Archive

Name: demo/locked/
Sealed: true
Specification-Title: Demo Package Contract
Specification-Version: 1.0
Implementation-Title: Locked Package A
Implementation-Version: 2.1.0

~~~

Explanation:

- There is no `Sealed: true` in the main section, because we do not want to seal `demo.open`.
- The `Name: demo/locked/` section seals **that specific package**.
- `Specification-Title` and `Specification-Version` describe the package's specification.
- `Implementation-Title` and `Implementation-Version` in the package section provide metadata when the loader defines `demo.locked` from A.
- `Implementation-Title: Example A Archive` in the main section can apply to other packages, while `Locked Package A` in the named section **overrides it for `demo.locked`**.

File **`manifests/b.mf`**:

~~~text
Manifest-Version: 1.0

~~~

There is no `Sealed` or version metadata for `demo.locked` in B, so when B is the source that defines the package first, the package is established as **unsealed**.

### 5.4. Host Inspecting `Package` and Loading Same-Package Classes

File **`host-src/SealingDemo.java`**:

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;

public final class SealingDemo {
    private SealingDemo() {
    }

    private static boolean sealingViolation(
            ClassLoader loader, String name) {
        try {
            loader.loadClass(name);
            return false;
        } catch (SecurityException expected) {
            return true;
        } catch (ClassNotFoundException unexpected) {
            throw new IllegalStateException(
                    "Required class missing: " + name, unexpected);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: SealingDemo <a.jar> <b.jar>");
        }

        Path a = Path.of(args[0]).toAbsolutePath().normalize();
        Path b = Path.of(args[1]).toAbsolutePath().normalize();

        if (!Files.isRegularFile(a) || !Files.isRegularFile(b)) {
            throw new IllegalArgumentException("Both JARs must exist");
        }

        URL aUrl = a.toUri().toURL();
        URL bUrl = b.toUri().toURL();

        // Classes in A/B depend only on java.base.
        // The platform loader does not hold the host's demo.locked/demo.open.
        ClassLoader parent = ClassLoader.getPlatformClassLoader();

        try (URLClassLoader combined = new URLClassLoader(
                    new URL[] {aUrl, bUrl}, parent);
             URLClassLoader reverse = new URLClassLoader(
                    new URL[] {bUrl, aUrl}, parent);
             URLClassLoader aOnly = new URLClassLoader(
                    new URL[] {aUrl}, parent);
             URLClassLoader bOnly = new URLClassLoader(
                    new URL[] {bUrl}, parent)) {

            Class<?> anchor = combined.loadClass(
                    "demo.locked.Anchor");
            Package pkg = anchor.getPackage();

            System.out.println("Anchor sealed: " + pkg.isSealed());
            System.out.println("Sealed at A URL: "
                    + pkg.isSealed(aUrl));
            System.out.println("Sealed at B URL: "
                    + pkg.isSealed(bUrl));
            System.out.println("Spec title: "
                    + pkg.getSpecificationTitle());
            System.out.println("Spec version: "
                    + pkg.getSpecificationVersion());
            System.out.println("Impl title: "
                    + pkg.getImplementationTitle());
            System.out.println("Impl version: "
                    + pkg.getImplementationVersion());

            System.out.println("A then B violation: "
                    + sealingViolation(combined,
                            "demo.locked.Other"));

            Class<?> one = combined.loadClass("demo.open.One");
            Class<?> two = combined.loadClass("demo.open.Two");
            System.out.println("Open package unsealed: "
                    + !one.getPackage().isSealed());
            System.out.println("Open from same loader: "
                    + (one.getClassLoader()
                    == two.getClassLoader()));

            Class<?> firstB = reverse.loadClass(
                    "demo.locked.Other");
            System.out.println("B first unsealed: "
                    + !firstB.getPackage().isSealed());
            System.out.println("B then A violation: "
                    + sealingViolation(reverse,
                            "demo.locked.Anchor"));

            Class<?> onlyA = aOnly.loadClass(
                    "demo.locked.Anchor");
            Class<?> onlyB = bOnly.loadClass(
                    "demo.locked.Other");
            System.out.println("Separate loaders succeed: "
                    + (onlyA != null && onlyB != null));
            System.out.println("Same name package object: "
                    + (onlyA.getPackage() == onlyB.getPackage()));
        }
    }
}
~~~

The program creates **four separate `URLClassLoader` instances** so each scenario has an independent package state. This prevents the A-first loading case from accidentally affecting the B-first case.

**Do not use the application/system loader as the parent in this example** because the host does not need a shared API from the JARs; choosing the platform loader ensures the test is not shadowed by `demo.locked.*` classes on the application classpath. In a real plugin system that requires a host interface, the parent must be the loader that sees the shared API—do not automatically choose the platform loader in every case.

### 5.5. Compiling and Packaging

Requires **JDK 17+**, run from the `sealing-demo/` directory.

**Bash (Linux, macOS, or Git Bash):**

~~~bash
mkdir -p build/a build/b build/host dist

javac -encoding UTF-8 -d build/a \
  a-src/demo/locked/Anchor.java \
  a-src/demo/open/One.java

javac -encoding UTF-8 -d build/b \
  b-src/demo/locked/Other.java \
  b-src/demo/open/Two.java

javac -encoding UTF-8 -d build/host \
  host-src/SealingDemo.java

jar --create --file dist/a.jar \
  --manifest manifests/a.mf -C build/a .

jar --create --file dist/b.jar \
  --manifest manifests/b.mf -C build/b .

java -cp build/host SealingDemo dist/a.jar dist/b.jar
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force build/a,build/b,build/host,dist | Out-Null

javac -encoding UTF-8 -d build/a a-src/demo/locked/Anchor.java a-src/demo/open/One.java

javac -encoding UTF-8 -d build/b b-src/demo/locked/Other.java b-src/demo/open/Two.java

javac -encoding UTF-8 -d build/host host-src/SealingDemo.java

jar --create --file dist/a.jar --manifest manifests/a.mf -C build/a .

jar --create --file dist/b.jar --manifest manifests/b.mf -C build/b .

java -cp build/host SealingDemo dist/a.jar dist/b.jar
~~~

Before running, inspect the JARs:

~~~bash
jar --list --file dist/a.jar
jar --list --file dist/b.jar
jar --extract --file dist/a.jar META-INF/MANIFEST.MF
~~~

The `jar --extract` command writes `META-INF/MANIFEST.MF` to the current directory, so **running the extract command is not mandatory** if you only need to verify the logic; you can inspect the manifest using a ZIP/JAR viewer. If you do run extract, do so in a separate inspection directory to avoid overwriting project files with the same name.

Required key entries:

~~~text
a.jar:
  demo/locked/Anchor.class
  demo/open/One.class
  META-INF/MANIFEST.MF

b.jar:
  demo/locked/Other.class
  demo/open/Two.class
  META-INF/MANIFEST.MF
~~~

Using `jar --manifest` ensures the metadata is packaged into the JAR. If you build the JAR without the intended manifest, `Package.getImplementationVersion()` may be `null` and sealing will not take effect as shown in the example.

### 5.6. Output

With the structure above, no duplicate classes from the parent, and standard JDK 17 `URLClassLoader`:

~~~text
Anchor sealed: true
Sealed at A URL: true
Sealed at B URL: false
Spec title: Demo Package Contract
Spec version: 1.0
Impl title: Locked Package A
Impl version: 2.1.0
A then B violation: true
Open package unsealed: true
Open from same loader: true
B first unsealed: true
B then A violation: true
Separate loaders succeed: true
Same name package object: false
~~~

**Reading the output:**

1. `Anchor` comes from A, and A's manifest seals `demo.locked`. `pkg.isSealed()` is `true`.
2. `pkg.isSealed(aUrl)` is `true`, whereas `pkg.isSealed(bUrl)` is `false` because the two code source URLs are different.
3. `Package` accurately reflects `Specification-Title`, `Specification-Version`, `Implementation-Title`, and `Implementation-Version` from A's package section.
4. `combined` attempts to load `Other` from B into a package already sealed at A → `SecurityException` is caught, printing `true`.
5. The `demo.open` package is unsealed, so `One` from A and `Two` from B can coexist in **the same defining loader**.
6. `reverse` loads class B first, defining `demo.locked` as unsealed; loading class A with `Sealed: true` afterward also triggers a violation because an already-defined unsealed package cannot be sealed.
7. The two separate loaders `aOnly`/`bOnly` have **separate `Package` objects**, even though the package name strings are identical; there is no sealing violation across two independent loaders.

Key takeaway: **class loading order**, not merely URL order on the classpath, determines which class creates the package metadata first. `Anchor` is only in A and `Other` is only in B: when `Other` is requested first, the loader can traverse URL A then URL B and obtain the class from B.

## 6. How Is Package Metadata Retrieved and Used?

`java.lang.Package` provides useful methods:

| API | Meaning |
|---|---|
| `Class.getPackage()` | Gets the `Package` associated with the runtime class |
| `Package.getName()` | Package name |
| `Package.isSealed()` | Whether the package is sealed |
| `Package.isSealed(URL)` | Whether the package is sealed **with respect to this code source URL** |
| `Package.getSpecificationTitle()` | Specification title from the manifest |
| `Package.getSpecificationVersion()` | Specification version |
| `Package.getSpecificationVendor()` | Specification vendor |
| `Package.getImplementationTitle()` | Implementation title |
| `Package.getImplementationVersion()` | Implementation version |
| `Package.getImplementationVendor()` | Implementation vendor |
| `Package.isCompatibleWith(String)` | Checks whether the specification version meets the required level using dot-separated numeric rules |

**Do not treat `Implementation-Version` as a dependency version enforcement mechanism.** It is metadata that may be absent or assigned by the build pipeline. The JVM does not automatically reject a JAR just because a package's `Implementation-Version` does not match application expectations.

For `Package.isCompatibleWith("1.2")`, specification versions are interpreted as non-negative numeric components separated by dots; invalid formats can throw `NumberFormatException`. This is not a full SemVer comparator like npm/Maven and should not be used for version strings such as `"1.2.3-beta"` without custom handling.

### Package Metadata Is Not Per-Class JAR Metadata

Within a loader, `Package` is metadata attached to the **package definition**, not an independent copy per class. If an unsealed package is first defined from JAR A and a class from JAR B is later loaded into the same package, `classB.getPackage()` can still point to the `Package` defined from A.

Therefore, **do not use a package's `getImplementationVersion()` as proof that every class in the package came from the same JAR**, especially when an unsealed package spans multiple sources.

To trace a specific class, check `Class.getProtectionDomain().getCodeSource().getLocation()` **when available**; the value may be null or inaccessible in some environments. That provides **the class's bytecode origin**, which is distinct from `Package` metadata.

## 7. Distinguishing Package Sealing from JAR Signing

A JAR file can be:

- **Sealed but unsigned:** `Sealed: true` only enforces source consistency for classes in the package; it does not authenticate the publisher.
- **Signed but unsealed:** Signatures are used to verify integrity/certificates under the JAR signing mechanism, but packages may not use sealing.
- **Both signed and sealed:** The two mechanisms serve different purposes.

Within the same runtime package, classes may also be subject to signer/certificate consistency constraints when defining a class; this is separate from `Sealed`. Do not fix sealing errors by arbitrarily disabling signature verification or editing the manifest inside a signed JAR, as doing so can invalidate the signature.

**Sealing is not a sandbox.** A plugin running bytecode in the same process still has the permissions of that process. Use process/container boundaries if you need to run untrusted code.

## 8. Sealing and ClassLoader Identity

Common misconception: "A JVM can have only one `demo.locked.Anchor` class if the package is sealed." This is **false**.

The JVM identifies a runtime class by its binary name **and its defining loader**. Two independent loaders can load the same JAR:

~~~text
(loader A, demo.locked.Anchor)  ≠  (loader B, demo.locked.Anchor)
~~~

Each loader has its own namespace and can define its own `Package`. Sealing guarantees the consistency of **a package defined by a loader** with its corresponding code source, rather than forcing the entire JVM to have only one instance of a class/package with that name.

Conversely, even when **unsealed**, having a host and a plugin independently define two classes with the same FQCN can cause a `ClassCastException`. Therefore, do not use sealing to solve all class identity issues. Shared APIs between a host and plugins must be loaded from a common loader, while implementations can reside in separate child loaders.

## 9. Sealing and JAR Search Order

A parent-first loader normally delegates to its parent first. If the parent already has the requested class, the child `URLClassLoader` can return the parent's class **without defining the class itself**; in that case, the child's package sealing state does not determine the outcome for the parent-defined class.

Within a `URLClassLoader`'s own URL path, URL order determines where classes are found when multiple sources exist. However, distinguish two scenarios:

**Same FQCN appears in both A and B:** The URL searched first can supply the bytecode; the class in the later URL is shadowed. Name collision alone does not force the loader to define both versions.

**Two different FQCNs in the same package:** Class A and Class B can be picked up from two different JARs. If the package is sealed at one source, attempting to add a class from the other source will trigger a `SecurityException`. This is the runnable case in this article.

To diagnose issues in a real system, do not just reorder `-cp` and guess. Inspect the **defining loader**, the **CodeSource URL** if available, the **manifest sealing attributes**, and **which class is loaded first**.

## 10. Sealing with JPMS, Plain JARs, and Custom Loaders

**Classpath/unnamed modules:** The example scenario uses two plain JARs and `URLClassLoader`, which is the typical context for manifest-based package sealing.

**JPMS named modules:** Module/package definition, readability, `exports`, `opens`, and split-package constraints are governed by the module system. You cannot simply apply a rule like "add `Sealed: true` to solve all split packages on the module path." With named modules, clean module/package design and adhering to module resolution is the primary approach.

**Custom ClassLoader:** If you read bytecode manually via `Files.readAllBytes` and call `ClassLoader.defineClass(...)`, Java does not automatically read `META-INF/MANIFEST.MF` from a custom repository to apply sealing policies like `URLClassLoader` does. You must define `Package` yourself and handle metadata, code source, and source checks appropriately when implementing such a loader.

`URLClassLoader.definePackage(String name, Manifest man, URL url)` provides an API to establish metadata and sealing from a manifest; you should not bypass package consistency when writing a custom loader for sealed JARs.

## 11. Common Errors and How to Fix Them

| Symptom | Likely Cause | Resolution |
|---|---|---|
| `SecurityException: sealing violation` | Loader defines a class in the same package from a different code source than the sealed package | Check the manifest, JAR locations, and class loading order |
| "Can't seal package: already loaded" | Package was established as unsealed first, and a later JAR attempts to seal it | Eliminate split packages or ensure the package comes from a single source |
| `Package.isSealed() == false` despite `Sealed: true` in manifest | Wrong section, wrong `Name` path, or package was already defined from another source | Check `META-INF/MANIFEST.MF` and the package owner |
| `getImplementationVersion() == null` | Metadata not declared or loader does not pass metadata when defining the package | Check the manifest and loader implementation |
| Main-section sealed manifest seals other packages too | `Sealed: true` in the main section applies by default to the entire JAR | Use a per-package section or `Sealed: false` to override |
| Two loaders load the same sealed package without error | Two separate package/runtime namespaces | This may be valid behavior; verify class identity |
| Same unsealed package yet casting still fails | Duplicate FQCN across different defining loaders | Share API types through a parent loader |
| Renaming the JAR still causes a sealing error | Two different code source URLs / search path still splits the bytecode | Consolidate the package into one JAR or fix dependency topology |
| Class file is present but loader refuses to define it | Sealing, signer consistency, or bytecode error | Inspect the full cause and which class source was selected |
| Metadata does not reflect the version of every class | Package is defined once, not per class | Inspect the individual class's `CodeSource` |

## 12. Checklist for Designing Sealing-Safe JARs

1. **Know which packages appear in dependency JARs.** Check `demo/locked/*.class` entries using `jar --list --file ...`.
2. **Read the actual manifest in the runtime JAR.** Verify main/per-entry `Sealed`, package path names, blank lines, and manifest structure.
3. **Do not spread a sealed package across multiple JARs in the same defining loader.** If splitting is needed, consider reorganizing modules/packages or intentionally removing sealing after assessing the impact.
4. **Do not confuse the parent loader with the `ClassLoader` superclass.** Sealing controls package classes defined by a loader from a code source; parent delegation can supply classes from another loader.
5. **Keep build and runtime classpaths consistent.** Maven/Gradle shading, fat JARs, or relocation can alter package layouts and manifests; inspect the final artifact after the build.
6. **Do not blindly copy `Sealed: true` from another JAR.** If bundling multiple libraries into one JAR, design the metadata and code sources appropriately.
7. **Treat package metadata/versions according to their actual semantics.** Do not use `Implementation-Version` as a compatibility enforcement contract.
8. **Test both forward and reverse load orders when split packages exist.** Sealing errors may surface on the second class load, not necessarily when creating the loader.
9. **Distinguish classpath from module path.** With JPMS, check module resolution and package encapsulation separately.
10. **Maintain file permissions and trusted code sources.** Sealing does not replace integrity verification or sandboxing.

## 13. Self-Check Questions

**Question 1.** `a.jar` declares `Name: demo/locked/`, `Sealed: true`. `b.jar` contains another class in `demo.locked`. A `URLClassLoader` loads `Anchor` from A, then loads `Other` from B. What is the result?

**Answer:** A sealing violation, typically `SecurityException`, because the package was already sealed at code source A.

**Question 2.** If class B is loaded before class A, is the sealing error guaranteed to disappear?

**Answer:** No. B can establish `demo.locked` as unsealed, and then A attempting to seal the same package in the loader also causes a sealing violation.

**Question 3.** How does `Sealed: true` in the main section differ from `Sealed: true` under `Name: demo/locked/`?

**Answer:** The main section sets the default for all packages in the JAR. A named section sets or overrides the value for a specific package.

**Question 4.** Do two independent ClassLoaders loading two classes in `demo.locked` from two different JARs necessarily violate sealing?

**Answer:** No. Each loader has its own package namespace; sealing is checked when a loader defines classes belonging to its own package.

**Question 5.** Does `Package.getImplementationVersion()` automatically prevent an application from running with the wrong dependency version?

**Answer:** No. It is metadata, not a dependency solver; the application or build tool must check compatibility itself.

**Question 6.** Does a sealed package mean the JAR is digitally signed and trusted?

**Answer:** No. Sealing ensures source consistency for classes in a package; signing and execution permission control are separate concerns.

**Question 7.** If two JARs contain the **same binary class name** but the loader only loads the class from JAR A, is there automatically a sealing violation?

**Answer:** No. Sealing errors occur when attempting to define multiple classes in the same package from incompatible code sources; merely having duplicate filenames on disk does not mean the loader defined both.

## 14. Official Documentation

- [Java SE 17 — JAR File Specification, Package Sealing](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html): `Sealed` semantics in main/per-package sections and code sources.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): URL search, `definePackage(Manifest, URL)`, and package metadata.
- [Java SE 17 — Package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Package.html): `isSealed`, `isSealed(URL)`, specification/implementation metadata, and compatibility.
- [Java SE 17 — JarFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html): reading JARs and manifests.
- [Java SE 17 — Manifest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/Manifest.html): main attributes and named entries.
- [Java Virtual Machine Specification 17 — Loading and Linking](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): runtime class identity and the class loading process.

**Remember:** `Sealed: true` in a manifest requires classes of **a package** to originate from **a consistent JAR code source within the same defining loader**. A manifest can set a JAR-wide default or override it per package. `Specification-*`/`Implementation-*` metadata helps describe versions, but does not automatically guarantee compatibility or security.