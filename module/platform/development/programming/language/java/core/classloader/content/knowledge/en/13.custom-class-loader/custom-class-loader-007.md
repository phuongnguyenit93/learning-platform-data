# Defining Packages and Code Sources When Needed in a Custom ClassLoader

> **Context:** Java Core → ClassLoader → Custom Loader. When reading bytecode yourself from a directory, JAR, plugin repository, or code generator, you not only decide **which class is loaded**, but sometimes also need to attach **package information** (version, vendor, package sealing) and a **code source — CodeSource** to the defined classes. This lesson explains when `definePackage` is needed, how to coordinate `SecureClassLoader`/`ProtectionDomain`, the difference between metadata and actual protection mechanisms, and the rules that must not be broken. Examples use Java 17+.

## 1. The Problem: defineClass Succeeds, but Where Is the Metadata?

A simple custom loader typically looks like this:

```java
// Snippet inside a ClassLoader subclass:
byte[] bytes = readClassBytes(binaryName);
return defineClass(binaryName, bytes, 0, bytes.length);
```

Here, `readClassBytes` is an application-defined helper; the snippet is **not standalone**. It may be sufficient if you only want to load regular classes. However, after defining `sample.plugin.Task`, the following information can matter:

- Which package specification version does `Task.class.getPackage().getSpecificationVersion()` report?
- Which plugin release does `Task.class.getPackage().getImplementationVersion()` reflect?
- Is the package **sealed** to prevent mixing in classes from other sources?
- Can `Task.class.getProtectionDomain().getCodeSource()` indicate which source provided the class?
- If the JAR is signed, do classes in the **same package of the same loader** adhere to consistent certificate rules?

**Answer:** `defineClass` automatically creates a default `Package` for the package name if the loader does not already have one, but specific metadata **does not arise automatically from a JAR manifest file** merely because you read bytes and call `defineClass`. If the application wants specific attributes, configure them **before the first class definition in the package**; if a code source is needed, use the `defineClass` overload that accepts a `ProtectionDomain` or `SecureClassLoader.defineClass` that accepts a `CodeSource`.

Not every custom loader needs to do all of this: only add information/mechanisms when there is a clear use case and consistency can be maintained.

## 2. Distinguishing Three Concepts That Should Not Be Conflated

| Concept | Represented By | Answers the Question |
| --- | --- | --- |
| **Java package metadata** | `java.lang.Package` | Package name, specification/implementation title/version/vendor, sealed status, and annotations if present. |
| **Code source** | `java.security.CodeSource` | Location URL and the set of certificates/signers associated with the code source (if provided/verified). |
| **Protection domain** | `java.security.ProtectionDomain` | Security domain metadata group consisting of code source, class loader, and permission collection/principals per configuration/constructor. |

A `Class<?>` can know its package while `ProtectionDomain.getCodeSource() == null`. Conversely, a class has a `CodeSource` while its package version metadata is empty. The two sets of information **do not substitute for each other**.

Recommended order for a custom loader:

```text
1. Receive loadClass(binaryName) request
2. Check if already loaded and try parent according to policy
3. Inside findClass:
      - locate the exact bytes of a class file
      - determine package name, manifest metadata, source URL
      - check/define Package if needed
      - create an appropriate CodeSource or ProtectionDomain
      - defineClass(binaryName, bytes, domain/source)
4. JVM links/initializes when required by the corresponding rules
```

`definePackage`, `defineClass`, and `resolveClass` are **distinct** steps; calling `definePackage` does not "load" all classes in the package.

## 3. What Is a Package in a Multi-ClassLoader Runtime?

In source code, classes may declare:

```java
package sample.plugin;
```

However, in the JVM, a **runtime package** is distinguished by **package name + defining class loader**. Two different loaders can both define a package named `sample.plugin`, and each loader manages its own `Package`.

Therefore:

```text
Loader A defines sample.plugin.Task
    -> (binary name sample.plugin.Task, defining loader A)
    -> package sample.plugin of loader A

Loader B defines sample.plugin.Task
    -> (binary name sample.plugin.Task, defining loader B)
    -> package sample.plugin of loader B

A != B: two different runtime types, two different runtime packages
```

Important consequences:

- `package-private` cannot automatically be accessed between two classes just because the `package` string is the same.
- The same class name defined by two loaders results in **two different runtime types**; `ClassCastException` can occur when casting an object between them.
- `getDefinedPackage("sample.plugin")` only queries packages **directly defined by the queried loader**, without walking back up to the parent.
- `ClassLoader`'s `getPackage(String)` has been **deprecated since Java 9**, because it can also search the parent and return package metadata that does not match the defining class; prefer `getDefinedPackage`.
- To query the `Package` associated with a specific class, use `clazz.getPackage()` instead of trying to infer it via the system loader.

### A Package Object Is Not a Directory or Classpath Root

`Package` is runtime metadata, **not** a `sample/plugin` directory created on disk. `definePackage` does not add a JAR lookup path; and `getDefinedPackage` does not tell which JAR contains all classes of that package.

## 4. When Does the JVM Automatically Create a Package?

The `ClassLoader.defineClass(String, byte[], int, int, ProtectionDomain)` API and related overloads have a mechanism to ensure a package matching the defined class name. If the loader does not yet have a `Package` for that name, defining the class can create a **default package** with metadata attributes according to `Package` rules.

Therefore, a minimal loader is **not required** to call `definePackage` before every `defineClass`.

However, if you want specification title, version, implementation vendor, or `sealBase` to be set according to a manifest, **you must explicitly define the package before the first `defineClass` in that package**. Do not rely on "updating later after loading a few classes".

Example:

```text
defineClass("sample.plugin.First", bytesFirst, ...)
       -> if package sample.plugin does not exist yet:
          default package metadata is created

definePackage("sample.plugin", ... required metadata ...)
       -> too late: cannot redefine the same package of the loader
```

A package name can only be defined **once in a single loader** and its attributes cannot be changed using `definePackage` afterward. Therefore, deciding the metadata when loading the first class is part of loader design, not "patching labels" after loading.

## 5. definePackage: Version, Vendor, and Sealing

Commonly used overload:

```java
protected Package definePackage(
        String name,
        String specTitle,
        String specVersion,
        String specVendor,
        String implTitle,
        String implVersion,
        String implVendor,
        java.net.URL sealBase);
```

`definePackage` is a `protected` method on `ClassLoader`: subclasses can call it from internal logic; external code cannot call it freely without appropriate `protected` permission.

Parameters:

| Parameter | Meaning |
| --- | --- |
| `name` | Dot-style package name, for example `sample.plugin`. |
| `specTitle` | Specification title. |
| `specVersion` | Specification version; `Package.isCompatibleWith` parses it using dot-separated numeric rules. |
| `specVendor` | Specification vendor. |
| `implTitle` | Implementation title. |
| `implVersion` | Implementation version string, defined by the packager. |
| `implVendor` | Implementation vendor. |
| `sealBase` | Source URL for which the package is marked **sealed**; `null` means the package is not sealed. |

An example in a custom loader:

```java
definePackage(
    "sample.plugin",
    "Demo API", "1.0", "Demo",
    "Plugin Impl", "2.0", "Demo",
    null);
```

Then, with the class `sample.plugin.Task` defined by that loader:

```java
Package p = taskClass.getPackage();
System.out.println(p.getSpecificationTitle()); // Demo API
System.out.println(p.getImplementationVersion()); // 2.0
System.out.println(p.isSealed()); // false
```

These are **two snippets that need to reside in the subclass and caller respectively**; `taskClass` must be defined first. Section 7 has a runnable standalone program.

### Version Limitations

`getImplementationVersion()` only returns the **metadata string** set by the loader; the JVM does not guarantee it is a Maven/SemVer version or matches the running code. For `getSpecificationVersion()`, `Package.isCompatibleWith(String)` compares numeric version components and may throw `NumberFormatException` if the format does not match. Do not use `Package` metadata as a dependency resolver or as a safety condition for accepting untrusted code.

### Cannot Redefine the Same Package

If `definePackage` is called again for the same `name` on the same loader, the method may throw `IllegalArgumentException` because the package is already defined. For a parallel loader, two threads preparing package metadata concurrently need proper synchronization to avoid a race between `getDefinedPackage` and `definePackage`.

## 6. Package Sealing: What Does It Guarantee, and What Must a Custom Loader Do?

A `Package` is **sealed** when `sealBase` is non-`null`. In JAR packaging terms, classes in a sealed package must belong to the exact marked archive source. Checking metadata:

```java
Package p = someClass.getPackage();
boolean sealed = p.isSealed();
boolean fromExpectedBase = p.isSealed(expectedJarUrl);
```

`someClass` and `expectedJarUrl` are variables in a real program; the snippet illustrates the API.

**Common misconception:** assigning `sealBase` to `definePackage` only creates the sealed metadata attribute for `Package`. If **you write your own loader** and call `defineClass` from raw bytes yourself, you must manage source determination, package sealing checks, and consistency according to your loader design; do not assume all JAR/manifest source-matching logic of `URLClassLoader` will automatically be replicated for your loader.

An **illustrative** check rule before defining more classes from `sourceUrl`:

```java
// Placed in the loader, before defineClass, with:
// packageName, sourceUrl, and shouldBeSealed determined from a trusted source.
Package pkg = getDefinedPackage(packageName);
if (pkg == null) {
    definePackage(packageName,
            null, null, null, null, null, null,
            shouldBeSealed ? sourceUrl : null);
} else if (pkg.isSealed()) {
    if (!pkg.isSealed(sourceUrl)) {
        throw new SecurityException("Package sealing violation");
    }
} else if (shouldBeSealed) {
    throw new SecurityException("Cannot seal already-unsealed package");
}
```

This is a **snippet placed in a subclass**, with the three variables `packageName`, `sourceUrl`, and `shouldBeSealed` from the application's policy. In production, the same synchronization lock is needed when checking and when loading classes, determining package metadata once, and avoiding mixing certificate sets/source policies between JARs.

When using `URLClassLoader`, it implements manifest/package metadata handling and package sealing when loading from JARs; you should not rebuild it if you only need a standard loader. **Sealing does not replace module access permissions, JAR signing, or isolation between defining loaders.**

## 7. Code Source: CodeSource and ProtectionDomain

### What Does CodeSource Contain?

`java.security.CodeSource` contains:

- **Location URL** describing the source associated with the class, usually a JAR URL or directory URL.
- **Certificates/signers** associated with the code, when present and properly verified.

Example:

```java
java.net.URL origin = Path.of("build/plugin")
        .toAbsolutePath().toUri().toURL();

java.security.CodeSource source = new java.security.CodeSource(
        origin, (java.security.cert.Certificate[]) null);
```

This is a snippet requiring `import java.nio.file.Path;` (or the full name as in the example), not a class with `main`. `origin` here describes **where the application believes the bytes came from**. **Setting a CodeSource URL yourself does not prove the bytes were actually loaded from that source**; you must read/verify them through the proper process.

### Attaching Source via SecureClassLoader

`java.security.SecureClassLoader` extends `ClassLoader` and has overloads:

```java
protected final Class<?> defineClass(
        String name, byte[] b, int off, int len, CodeSource cs);

protected final Class<?> defineClass(
        String name, java.nio.ByteBuffer b, CodeSource cs);
```

If a non-`null` `CodeSource` is passed, `SecureClassLoader` creates an appropriate `ProtectionDomain` for the defined class. You can check:

```java
ProtectionDomain pd = clazz.getProtectionDomain();
CodeSource cs = pd.getCodeSource();
URL url = cs == null ? null : cs.getLocation();
```

This is a snippet where `clazz` is a `Class<?>` defined by the loader. When there is no explicit code source, `cs` may be `null`. Never assume `clazz.getProtectionDomain().getCodeSource().getLocation()` always has a value — avoid `NullPointerException`.

### Attaching via ClassLoader with ProtectionDomain

If extending `ClassLoader` instead of `SecureClassLoader`, you can use:

```java
defineClass(
        binaryName, bytes, 0, bytes.length, protectionDomain);
```

`protectionDomain` is a `java.security.ProtectionDomain` created or managed by the application, which may contain a `CodeSource` and related information. If `null`, `defineClass` uses the default domain per the Javadoc. **Not every custom loader has to build its own ProtectionDomain**; only do so when metadata and permissions genuinely need to be controlled.

### CodeSource Is Not an Automatic Security Sandbox

In Java 17, `SecurityManager` was deprecated for removal; as of JDK 24, the Security Manager has been permanently disabled per JEP 486. Do not use `ProtectionDomain` or `CodeSource` as a promise that untrusted plugin bytecode has been sandboxed under the legacy security policy. They remain metadata APIs and related constraints, but safe isolation for untrusted code may require a **process boundary**, a container, or a solution with an appropriate threat model.

## 8. Complete Hands-On Practice: Package Metadata + CodeSource

The following example creates two separate custom loaders that both read the bytecode of `sample.plugin.Task`:

- The first loader is **not sealed**, with specification/implementation metadata attached before defining the class.
- The second loader is **sealed** at the same source URL.
- Each loader creates its **own runtime class and Package**.
- Each class stores the declared CodeSource URL through `SecureClassLoader`.

No libraries outside the JDK and no physical JAR file are used; `origin` is set to the URL of the `build/plugin` directory, matching where the example reads the class bytes from.

### Source Structure

```text
src/
  sample/
    plugin/
      Task.java
  app/
    PackageSourceDemo.java
build/
  plugin/        (created by javac)
  app/           (created by javac)
```

**File `src/sample/plugin/Task.java`:**

```java
package sample.plugin;

public class Task {
    public String message() {
        return "hello";
    }
}
```

**File `src/app/PackageSourceDemo.java`:**

```java
import java.io.IOException;
import java.net.URL;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.CodeSource;
import java.security.SecureClassLoader;
import java.security.cert.Certificate;

public class PackageSourceDemo {
    static final class PluginLoader extends SecureClassLoader {
        private final Path root;
        private final URL origin;
        private final boolean sealed;

        PluginLoader(Path root, URL origin, boolean sealed) {
            super(ClassLoader.getPlatformClassLoader());
            this.root = root;
            this.origin = origin;
            this.sealed = sealed;
        }

        @Override
        protected Class<?> findClass(String binaryName)
                throws ClassNotFoundException {
            Path path = root.resolve(
                    binaryName.replace('.', '/') + ".class");

            final byte[] bytes;
            try {
                bytes = Files.readAllBytes(path);
            } catch (IOException ex) {
                throw new ClassNotFoundException(binaryName, ex);
            }

            int dot = binaryName.lastIndexOf('.');
            if (dot >= 0) {
                String pkgName = binaryName.substring(0, dot);
                if (getDefinedPackage(pkgName) == null) {
                    definePackage(
                            pkgName, "Demo API", "1.0", "Demo",
                            "Plugin Impl", "2.0", "Demo",
                            sealed ? origin : null);
                }
            }

            CodeSource codeSource = new CodeSource(
                    origin, (Certificate[]) null);

            return defineClass(
                    binaryName, bytes, 0, bytes.length, codeSource);
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Path.of("build/plugin").toAbsolutePath();
        URL origin = root.toUri().toURL();

        PluginLoader open = new PluginLoader(root, origin, false);
        Class<?> first = Class.forName(
                "sample.plugin.Task", false, open);
        Package pkg = first.getPackage();

        System.out.println("class defined by custom loader: "
                + (first.getClassLoader() == open));
        System.out.println("package title: "
                + pkg.getSpecificationTitle());
        System.out.println("package version: "
                + pkg.getImplementationVersion());
        System.out.println("unsealed: " + !pkg.isSealed());
        System.out.println("code source matches: "
                + origin.equals(first.getProtectionDomain()
                        .getCodeSource().getLocation()));
        System.out.println("repeated lookup same class: "
                + (Class.forName("sample.plugin.Task", false, open)
                        == first));

        PluginLoader sealed = new PluginLoader(root, origin, true);
        Class<?> second = Class.forName(
                "sample.plugin.Task", false, sealed);

        System.out.println("sealed: "
                + second.getPackage().isSealed());
        System.out.println("sealed at origin: "
                + second.getPackage().isSealed(origin));
        System.out.println("different runtime classes: "
                + (first != second));
        System.out.println("different Package objects: "
                + (first.getPackage() != second.getPackage()));
    }
}
```

### How to Run

Standing in the root directory containing `src`, run:

```bash
javac -d build/plugin src/sample/plugin/Task.java
javac -d build/app src/app/PackageSourceDemo.java
java -cp build/app PackageSourceDemo
```

**Stdout was compiled and verified on OpenJDK 24; the code only uses APIs available in Java 17 and earlier:**

```text
class defined by custom loader: true
package title: Demo API
package version: 2.0
unsealed: true
code source matches: true
repeated lookup same class: true
sealed: true
sealed at origin: true
different runtime classes: true
different Package objects: true
```

### Explaining the Results

1. `build/plugin` is **not on `-cp build/app`**, so the parent platform loader does not define `sample.plugin.Task` from there. `PluginLoader.findClass` receives the name from `Class.forName(name, false, loader)` and reads the bytes itself.
2. `getDefinedPackage(pkgName) == null` allows package metadata to be declared before `defineClass`. Both values `Demo API` and `2.0` appear accurately on `clazz.getPackage()`.
3. `CodeSource(origin, null)` attaches a source URL that the example also actually uses to read the bytes. `ProtectionDomain.getCodeSource().getLocation()` returns the matching URL. The example **does not verify signatures** because the test class source has no certificates.
4. The subsequent `Class.forName(..., false, open)` call returns the **same `Class<?>`** on the same loader.
5. The second loader attaches `sealBase = origin`, so `Package.isSealed()` and `isSealed(origin)` return `true`. The experiment demonstrates package metadata; it **does not test package sealing across multiple source JARs**.
6. Two independent loaders allow the same binary name to have two different runtime types, along with two separate `Package` objects. Do **not** infer that just because they share the same CodeSource URL, their type identity is also the same.

### Limitations of the Example in Real-World Implementations

This `findClass` is only a simplified single-class/package version: it lacks a cache/manifest parser, certificate verification, package sealing checks when loading from multiple sources, file size limits, allowed-source policies, or parallel-capable registration. With multiple classes in the same package and concurrent loading, `getDefinedPackage` + `definePackage` must be guarded by a proper locking mechanism to avoid `IllegalArgumentException` due to a race.

Do not use this loader as-is to run untrusted bytecode; `CodeSource` does not turn it into a sandbox.

## 9. Metadata from a JAR Manifest: How Should It Be Done Properly?

When classes come from a JAR, the corresponding attributes can be declared in `META-INF/MANIFEST.MF`:

```text
Manifest-Version: 1.0
Specification-Title: Demo API
Specification-Version: 1.0
Specification-Vendor: Demo
Implementation-Title: Plugin Impl
Implementation-Version: 2.0
Implementation-Vendor: Demo
Sealed: false
```

This is an **example of manifest content**, not JVM output. Manifests also allow **package-specific sections**, typically taking the form:

```text
Name: sample/plugin/
Specification-Title: Plugin API
Implementation-Version: 2.1
Sealed: true
```

When a custom loader parses a manifest, it must determine the attribute policy by package section or main section of the manifest according to the JAR Specification. Section names use **slashes** like entry names, whereas `definePackage` uses **dots** in the package name. `Sealed: true` requires a seal base matching the **archive source** URL, not arbitrarily using a URL to a `.class` entry.

A JAR-managing loader should:

1. Open the JAR in a controlled manner and accurately identify the source of the class bytes.
2. Read the manifest/metadata for the relevant package, considering the scope of main/section attributes.
3. Before the first definition, call `definePackage` with the appropriate metadata.
4. For a sealed package, verify that the source of subsequent classes in the **same loader/package** matches the seal base.
5. Supply a `CodeSource` tied to the **actual source** of the bytes; if signed, only recognize certificates that have been verified according to the appropriate JarFile/JarVerifier mechanism.

If you only need normal loading from URLs/JARs and want manifest metadata/sealing to work via the standard mechanism, **prefer `URLClassLoader`** — it is already built for URL/JAR lookup paths along with packaging metadata. Handling `JarFile` yourself and calling `defineClass` on entry bytes means **you own the remaining responsibilities**, rather than getting all of `URLClassLoader`'s behavior for free.

### Do Not Confuse CodeSource with Manifest Title/Version

Manifest metadata such as `Implementation-Version` is **package information**. `CodeSource` primarily concerns **location and certificates**. You can have package version `2.0` and `CodeSource` URL `file:/.../plugin.jar` at the same time; they are not the same attribute, and one cannot be inferred from the other through the `defineClass` API.

## 10. Certificates, Signing, and Package Consistency Checks

The Javadoc for `ClassLoader#defineClass(..., ProtectionDomain)` specifies that **the first class defined in a package** establishes the **set of certificates** that subsequent classes **in that package defined by the same loader** must have. The certificate set is taken from the `CodeSource` of the `ProtectionDomain`; a mismatch causes a `SecurityException`. The `SecureClassLoader.defineClass(..., CodeSource)` overload serves to create the domain for this case.

Specifically:

- `CodeSource(origin, null)` indicates **no certificates are provided**, which does not mean the JAR was signed or verified.
- Manually creating a `Certificate` object and putting it into `CodeSource` **is not equivalent** to verifying the archive signature and ensuring the bytes are signed data.
- If multiple JARs provide classes in one package, the loader must keep **certificate sets consistent**. Changing only the source `URL` does not necessarily cause a certificate mismatch if the certificate sets are compatible; package sealing is a separate source check.
- If signed JAR verification is needed, use the JAR verification mechanism and control reading the entire entry before trusting the appropriate certificate metadata. Distinguish between signing assurance, loader identity, package sealing, and permissions.
- Do not pass `null` as the binary class name merely to bypass certain namespace/certificate checks; the Javadoc recommends **always providing the binary name** to confirm that the newly defined class matches expectations.

Errors that may occur:

| Error | Typical Cause |
| --- | --- |
| `IllegalArgumentException` at `definePackage` | Package has already been defined in the same loader. |
| `SecurityException` at `defineClass` | Inconsistent package certificate set, or defining a `java.*` name from a disallowed loader. |
| `NoClassDefFoundError` (wrong name) | The passed `binaryName` does not match the actual name in the bytecode. |
| `ClassFormatError` | Invalid/corrupted class file data. |
| `LinkageError` | Attempting to define a duplicate class name in the same loader, or violating another linkage constraint. |
| `ClassNotFoundException` | `findClass` could not find/read the target class bytes. |
| `NullPointerException` when reading CodeSource | Assuming `getProtectionDomain().getCodeSource()` is always non-`null`. |

Do not treat every `SecurityException` as "unsigned JAR"; you must read the message, cause, class/package context, and policy applied by the loader.

## 11. Package Metadata Does Not Replace the Module System or Other Java Rules

Java 9+ has JPMS with named modules, `module-info.java`, readability, `exports`, and `opens`. `Package` attributes such as `Specification-Version` and `Sealed` are not module access permissions. A class defined in the **unnamed module** of a custom loader does not automatically become a class of a named module merely by calling `definePackage`.

In addition:

- **Package-private access** is still based on the runtime package consisting of the package name and defining loader.
- **Exports/opens** of a named module control access/reflective access levels according to module rules, and are not granted by manifest `Sealed`.
- **Class identity** remains binary name + defining loader for ordinary classes/interfaces; two loaders reading the same JAR do not create the same runtime type.
- **ProtectionDomain/CodeSource** is not a tool that automatically resolves `IllegalAccessError` due to module/package boundaries or missing-class errors.
- If a plugin needs to communicate via a host interface, place the shared interface under an appropriate parent loader; if the plugin defines its own copy of that interface, casting may fail.

When package-info annotations matter, ensure `package-info.class` comes from the correct loader definition; the deprecated `ClassLoader.getPackage(String)` may return package metadata from a parent, causing you to misread it.

## 12. Practical Loader Design: Sequence and Concurrency

A safer workflow for a loader with multiple plugin JARs:

```text
Request loadClass("sample.plugin.Task")
    |
    v
findLoadedClass / parent delegation / class loading lock
    |
    v
Locate the actual JAR entry and verify bytes/source
    |
    v
Determine package from binary name
    |
    +-- package does not exist yet:
    |      read manifest and definePackage before the first class
    |
    '-- package already exists:
           check metadata/sealBase/certificates policy
    |
    v
Build CodeSource / ProtectionDomain consistent with the source
    |
    v
defineClass(name, bytes, domain/source)
    |
    v
Return Class<?>; JVM will link/init per the corresponding semantics
```

Points to consider:

**1. Concurrency:** `getDefinedPackage` followed by `definePackage` is not an atomic transaction for the entire JAR read and class definition. If a custom loader registers `registerAsParallelCapable` and multiple threads load **two differently named classes in the same package**, the per-name class-loading lock may **not prevent a package-level race**. You must synchronize on dedicated package state; do not simply `catch (IllegalArgumentException)` and swallow it without verifying that the metadata/seal base is consistent.

**2. No redefinition:** a loader cannot update `sample.plugin.Task` simply by calling `defineClass` a second time or changing `CodeSource` after the class has already been defined. Hot reloading typically involves creating a new loader and managing old objects and shared interfaces.

**3. Data source principle:** the `CodeSource` URL must correspond to the source of the bytes the loader actually read if you intend to use it for diagnostics/policy. Do not take a URL from a user-supplied name and attach it without checking; the metadata could be wrong or forged.

**4. Sealed packages:** a sealed package must have a consistent source base; if the loader performs the check itself, it must do so **before defining additional classes**. A different URL that resolves to the same file on the filesystem may also require a dedicated canonicalization/validation policy.

**5. Loader ownership:** who is responsible for closing the JAR/URLClassLoader/stream? `definePackage` does not manage archive handles. Use try-with-resources for `JarFile` and entry streams when you open them yourself.

**6. Phase-specific errors:** defining successfully does not guarantee that resolution of all dependencies or initialization will succeed. Do not equate package metadata errors with a `NoClassDefFoundError` caused by a missing dependency or a failed static initializer.

## 13. Mistakes and How to Fix Them

| Mistake | Consequence | How to Fix |
| --- | --- | --- |
| Always calling `definePackage` before every `defineClass` without checking state | `IllegalArgumentException` when loading the second class in the package. | Manage package state; declare it once. |
| Defining the first class and only then reading manifest metadata | Default package already exists; metadata is not updated by definePackage. | Read metadata before the first defineClass. |
| Using `getPackage` on the loader to check whether a package has been defined | May retrieve a package from the parent, using the wrong loader namespace. | Use the loader's `getDefinedPackage` or `clazz.getPackage()`. |
| Thinking `Package.isSealed()` automatically ensures a custom loader reads from the right JAR | A raw-bytes loader might not enforce the full source-checking policy. | Design sealing checks for all source classes or use URLClassLoader. |
| Attaching an arbitrary `CodeSource` URL and treating it as proof of provenance | Incorrect or unverified metadata. | Derive it from a verified byte source and manage trust. |
| Mixing signed and unsigned classes in the same runtime package | Certificate-set mismatch may throw `SecurityException`. | Keep provenance/certificates consistent; separate packages/loaders if needed. |
| Using ProtectionDomain as a complete sandbox on modern Java | Does not protect against untrusted code as expected. | Use an appropriate isolation boundary rather than relying on the legacy SecurityManager. |
| Placing a copy of the host API into another plugin loader | Same binary name but different defining loader, leading to ClassCastException. | Share the API from the parent; control parent delegation. |
| Opening a JAR and forgetting to close it | Leaks file descriptors/locks. | Close `JarFile`/streams by lifecycle using try-with-resources. |
| Confusing package version with module version | Misinterprets dependency/resolution policy. | Distinguish JAR manifest, `Package` metadata, and module descriptors. |
| Reading bytes yourself but forgetting to check the binary name | `NoClassDefFoundError: wrong name` or loading the wrong target class. | Pass the expected binary name and confirm the class file matches. |
| Two threads concurrently calling `definePackage` with the same name | Race/exception and risk of choosing the wrong metadata. | Synchronize per package and verify policy before allowing the class to be defined. |

## 14. Self-Check Questions

1. **Is a custom loader that only calls `defineClass` required to call `definePackage` first?**  
   No. `defineClass` can create a default package. Only call `definePackage` beforehand when specific metadata/sealing is needed.
2. **Why does calling `definePackage("sample.plugin", ...)` after the first class has already loaded usually fail?**  
   Because the package in the loader has already been defined and cannot be redefined to change its metadata.
3. **How does `getDefinedPackage` differ from `getPackage`?**  
   `getDefinedPackage` returns the package defined by that loader; the deprecated `getPackage` can search parents and lead to metadata that does not match the runtime package.
4. **Do two loaders with the same `Package.getName()` share one runtime package?**  
   No. Runtime packages differ when defining loaders differ.
5. **What does `sealBase == null` mean?**  
   The package is not sealed; providing a URL means the package metadata is sealed at that base.
6. **Does `CodeSource` directly store `Implementation-Version`?**  
   No. It primarily attaches location and certificates; version/title belong to `Package`.
7. **If `CodeSource.location` returns a URL set by the application, does that prove the class file is signed and valid?**  
   No. Declaring metadata yourself does not verify bytes or signatures.
8. **Why is the certificate set of the first class in a package important?**  
   Subsequent classes in the same package/loader require a compatible set of certificates; otherwise, a `SecurityException` may be thrown.
9. **Does a sealed package automatically make bytecode safe like a sandbox?**  
   No. It concerns package provenance; it does not replace process isolation or a runtime permission system.
10. **Why does a parallel loader need per-package locking?**  
    Two classes with different binary names in the same package can concurrently attempt to call `definePackage` with different information.
11. **In JDK 9+, what should you query to obtain package metadata from a given custom loader?**  
    `thatLoader.getDefinedPackage(name)` or `clazz.getPackage()` of a class defined by that loader.
12. **Should you implement manifest/sealing handling yourself for every application that only reads JARs?**  
    No. If `URLClassLoader` meets your requirements, prefer using the standard API and avoid duplicating error-prone rules.

## 15. Official Documentation

- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `definePackage`, `getDefinedPackage`, `defineClass`, package metadata, and certificate rules.
- [Java SE 21 — Package](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Package.html): specification/implementation metadata, `isSealed`, `isCompatibleWith`.
- [Java SE 21 — SecureClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureClassLoader.html): `defineClass(String,byte[],int,int,CodeSource)` and `getPermissions`.
- [Java SE 21 — CodeSource](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/CodeSource.html): location URL and certificate/signers metadata.
- [Java SE 21 — ProtectionDomain](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/ProtectionDomain.html): security domain fields/constructors.
- [Java SE 21 — URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): JAR search, class definition, and standard lifecycle.
- [Java SE 21 — JAR File Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html): manifest attributes, package sections, sealing, and signed JARs.
- [JVM Specification §5.3](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): runtime type identity, defining loader, and runtime package.
- [JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486): status of the Security Manager in JDK 24+.
