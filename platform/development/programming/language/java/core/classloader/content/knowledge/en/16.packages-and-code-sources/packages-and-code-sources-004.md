# CodeSource and Bytecode Source Location in Java ClassLoader

## 1. The Problem: "Which JAR Did This Class Come From?"

When encountering `ClassNotFoundException`, `NoClassDefFoundError`, `NoSuchMethodError`, conflicts between multiple library versions, or suspecting that a plugin was loaded incorrectly, a very useful diagnostic question is: **From which source did the JVM receive the definition of the currently running class?**

A common approach:

~~~java
Class<?> type = SomeLibraryClass.class;
java.security.CodeSource source =
        type.getProtectionDomain().getCodeSource();
java.net.URL location = source == null ? null : source.getLocation();
System.out.println(location);
~~~

However, this printout needs to be understood correctly:

- **`CodeSource` is metadata about the code origin attached to the `ProtectionDomain` of the class**; it is not an API guaranteed to return **the specific `.class` file path that was read**.
- **`CodeSource.getLocation()` is a `URL`**, which can point to a **JAR**, a **directory**, another source address, or **`null`**.
- **`Class.getProtectionDomain()`** is the step to retrieve the protection domain attached to the runtime class; `CodeSource` may be `null`, and if `CodeSource` is present, `location` may still be `null`.
- **A custom ClassLoader can explicitly assign a CodeSource** when defining a class; the declared URL does not by itself become proof that the bytes were actually fetched from that URL.
- **Defining loader, code source, resource URL, and the class file origin in the build** are distinct concepts.

This article belongs to the **Packages and Code Sources** group and dives into **CodeSource and bytecode source location**: its meaning, related APIs, common misconceptions, and reliable diagnostic techniques. The Java 17+ example below practically verifies loading from a JAR, loading custom-read bytes, and assigning a descriptive source URL.

## 2. Participating Objects

### 2.1. `Class<?>`: the actual class the program is using

~~~java
Class<?> type = java.util.ArrayList.class;
~~~

`type` represents a specific **runtime class**. Two classes with the same binary name but defined by two different ClassLoaders can be **two different `Class<?>` objects**.

~~~java
System.out.println(type.getName());
System.out.println(type.getClassLoader());
System.out.println(type.getModule());
~~~

These three expressions are **illustrative snippets**, placed inside one of your methods; they help identify the **name**, **defining loader**, and **module**. They do not by themselves reveal the full history of reading every byte from disk or network.

### 2.2. `ProtectionDomain`: the protection domain attached to the class

~~~java
java.security.ProtectionDomain domain = type.getProtectionDomain();
~~~

`ProtectionDomain` describes the protection context of a class, historically linked to the permission-granting mechanism and code source of the Java security architecture.

Structurally, a protection domain may be associated with:

- `CodeSource` — information about the code origin.
- `ClassLoader` — the associated loader.
- `PermissionCollection` — permission data under the legacy security model or related APIs.
- `Principal[]` in corresponding forms of protection domains.

**Do not use `ProtectionDomain` as a modern sandboxing system merely by setting metadata.** `SecurityManager` was deprecated in Java 17 and is no longer a recommended mechanism for new software; behavior also depends on the running JDK. `ProtectionDomain` values are useful for **provenance diagnostics**, not as a "security passport that has verified the file path."

### 2.3. `CodeSource`: codebase URL and code-signing evidence when available

~~~java
java.security.CodeSource source = domain.getCodeSource();
~~~

`java.security.CodeSource` stores:

- **`URL location`**: the codebase/origin assigned to the code.
- Information about **certificates** or **CodeSigners**, if present and applicable.

The contract of [Java SE 21 CodeSource](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/CodeSource.html) allows a `null` location URL; certificates/signers may also be absent. **Do not assume that a class is always digitally signed, or that the location URL always points directly to a `.class` file**.

### 2.4. `ClassLoader`: the class-loading mechanism, not CodeSource itself

~~~java
ClassLoader definingLoader = type.getClassLoader();
~~~

The defining loader affects runtime class identity. Meanwhile, `CodeSource` is information accompanying the class's `ProtectionDomain`; a single loader can define **multiple classes from different code sources**.

A `URLClassLoader` using JAR URLs typically knows the origin of the classes it loads from a JAR/directory and attaches the appropriate source information. A custom subclass of `ClassLoader` using `defineClass(String, byte[], ...)` may be assigned a default protection domain by the JVM, in which the location is unspecified.

## 3. Contract of `CodeSource.getLocation()`

~~~java
URL origin = codeSource.getLocation();
~~~

The returned meaning is **the URL of the codebase/source recorded in the CodeSource**. It is not synonymous with:

1. The path of the **`.class` entry** inside a JAR.
2. The path of the compiled **`.java` source** file.
3. The path of the JAR **that Maven/Gradle originally downloaded**.
4. Every URL that the `ClassLoader` checked before finding the class.
5. A file that still exists at the time you call the method.
6. A checksum record or cryptographic proof that the bytes were read from that URL.

Typical scenarios:

| How is the class loaded? | What `CodeSource.getLocation()` may show | Interpretation |
|---|---|---|
| Application classes from `build/classes` directory | Directory URL `file:/.../build/classes/` | **Classpath root**, not individual `.class` files |
| Dependency from `helper.jar` via `URLClassLoader` | URL `file:/.../helper.jar` | The JAR containing the class, without `!/pkg/Helper.class` |
| Custom loader reads `byte[]` then calls `defineClass` without attaching source | `null` location or no CodeSource | **Missing source metadata** does not mean bytes do not exist |
| Custom `SecureClassLoader` passes an explicit `CodeSource` | URL declared by the loader | **Metadata provided by the loader**, must be verified if authenticity is required |
| JDK platform classes | May not have a suitable CodeSource to print | Do not treat `null` as an error; inspect the runtime module if needed |
| Framework using nested JARs or memory/generated classes | Loader/framework-specific URL, or `null` | May not match a physical file path; inspect the specific loader/launcher |

Do not establish a rigid rule that every URL starting with `file:` is a JAR, or that `null` always means bootstrap. Reality depends on the loader and how the class was defined.

## 4. Safely Retrieving the Source with Null Handling

A simple helper:

~~~java
static java.net.URL codeSourceLocation(Class<?> type) {
    java.security.ProtectionDomain domain = type.getProtectionDomain();
    if (domain == null) {
        return null;
    }
    java.security.CodeSource source = domain.getCodeSource();
    return source == null ? null : source.getLocation();
}
~~~

**This is an illustrative method** and must be placed inside a class. There is no blind conversion from URL to `Path`.

Usage:

~~~java
URL location = codeSourceLocation(SomeType.class);
System.out.println(location == null ? "(unknown)" : location);
~~~

**Note**: when using `getProtectionDomain()` in a legacy SecurityManager environment, the caller may be subjected to a permission check; this is not an API guaranteed to be error-free across all historical JDK environments.

### 4.1. Why check for `null` at two levels?

You should not do this directly:

~~~java
String p = type.getProtectionDomain()
               .getCodeSource()
               .getLocation()
               .getPath();
~~~

The line above can throw a `NullPointerException` when `CodeSource` or the location URL is absent. Even when non-null, `URL.getPath()` **is not yet a reliable filesystem path** due to percent-encoding, protocols other than `file:`, `jar:` forms, nested JARs, remote URLs, or Windows path encoding.

For a `file:` URL pointing to a filesystem path, the proper conversion when a `Path` is needed is:

~~~java
Path path = Path.of(location.toURI());
~~~

This snippet is illustrative, requires `import java.nio.file.Path;`, and must handle `URISyntaxException`. Before converting, ensure `location != null` and that the protocol is filesystem-compatible. Do not use `Path.of` for HTTP URLs, `jrt:`, or framework-defined schemes.

### 4.2. Do not assume every `CodeSource` comes from URLClassLoader

Cases where classes are loaded from byte arrays, the JDK image, instrumentation, proxy/generated classes, network/custom protocols, and framework packaging may have different origins or no useful location URL.

To find out which loader defined the class:

~~~java
ClassLoader loader = type.getClassLoader();
System.out.println(loader == null ? "bootstrap" : loader.getClass().getName());
~~~

Once you know the loader, you can inspect its configuration/URLs if its API permits. For `URLClassLoader`, `getURLs()` returns **the loader's URL search path**, but **that is not proof of which URL was used for the specific class under inspection**.

## 5. How Does CodeSource Differ from a Class Resource URL?

Many developers use:

~~~java
URL resource =
        SomeType.class.getResource("SomeType.class");
~~~

Or:

~~~java
String entry = SomeType.class.getName().replace('.', '/') + ".class";
ClassLoader loader = SomeType.class.getClassLoader();
URL resource = loader == null
        ? ClassLoader.getSystemResource(entry)
        : loader.getResource(entry);
~~~

These are **two ways to look up a resource** (snippets; requires a valid `SomeType`). They may yield a URL such as:

~~~text
jar:file:/libs/helper.jar!/demo/lib/Helper.class
~~~

whereas `CodeSource` may be:

~~~text
file:/libs/helper.jar
~~~

Reason: the resource URL points to the **specific entry** found, while the CodeSource URL describes the **codebase**.

However:

- Resource lookup has its own delegation, so the URL found **is not necessarily the bytes that created `Class<?>`**, especially when the class has been instrumented/redefined or a custom loader has a different mapping.
- A class defined from `byte[]` may **have no published `.class` resource**.
- With modules, platform classes, hidden classes, nested JARs, and custom class loaders, the shape of the resource URL can vary.
- Treat **`CodeSource` + `ClassLoader` + `Module` + class/resource URL** as **complementary clues**, rather than equating them.

### 5.1. Do not confuse `getResource` with `getProtectionDomain`

| Call | Returned Object | Meaning |
|---|---|---|
| `type.getProtectionDomain()` | `ProtectionDomain` | Domain metadata attached to the runtime class |
| `domain.getCodeSource()` | `CodeSource` or `null` | Codebase/certificates/signers when available |
| `source.getLocation()` | `URL` or `null` | Recorded codebase source URL |
| `type.getClassLoader()` | `ClassLoader` or `null` | Defining loader (`null` typically corresponds to bootstrap) |
| `type.getModule()` | `Module` | Runtime module; name may be `null` for an unnamed module |
| `type.getResource("X.class")` | `URL` or `null` | Looks up a resource related to the class per API rules |
| `urlLoader.getURLs()` | `URL[]` | Search path of the loader, not a per-class URL |

## 6. Java 17+ Practice: CodeSource with a JAR URL, Null URL, and Synthetic Source

The following example requires only JDK 17+, with no Maven/Gradle needed. We prepare **a single library class** and load it via three different paths:

1. `URLClassLoader` receives the URL of `helper.jar` → `CodeSource.location` records the JAR URL.
2. A custom `ClassLoader` reads `Helper.class` from a directory and uses the default `defineClass` → **location is unspecified**.
3. A custom `SecureClassLoader` still reads **that exact same class file** from the directory but attaches a **synthetic** CodeSource URL that is not where the bytes were read from → illustrating why **a source URL cannot be treated as strong evidence**.

### 6.1. Directory structure

~~~text
demo/
├── src/
│   ├── app/
│   │   └── OriginDemo.java
│   └── lib/
│       └── demo/
│           └── lib/
│               └── Helper.java
└── build/
    ├── app/
    ├── lib/
    │   └── demo/lib/Helper.class
    └── helper.jar
~~~

**Reproduction condition:** when running, `-cp` contains only `build/app`, **not `build/lib` or `build/helper.jar`**. If you put them on the application classpath, parent-first delegation may define `demo.lib.Helper` first, defeating the purpose of comparing loaders.

### 6.2. File `src/lib/demo/lib/Helper.java`

~~~java
package demo.lib;

public final class Helper {
    public static String value() {
        return "HELPER_OK";
    }
}
~~~

This class uses a single binary name. The program will create **distinct runtime classes with the same name** under different defining loaders; this is valid behavior in the class-loading model when there are no conflicting loading constraints.

### 6.3. File `src/app/OriginDemo.java`

~~~java
import java.io.IOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.CodeSource;
import java.security.SecureClassLoader;
import java.security.cert.Certificate;

public class OriginDemo {
    static final String NAME = "demo.lib.Helper";

    static final class PlainBytesLoader extends ClassLoader {
        private final Path root;

        PlainBytesLoader(Path root) {
            super(OriginDemo.class.getClassLoader());
            this.root = root;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!NAME.equals(name)) {
                throw new ClassNotFoundException(name);
            }
            try {
                byte[] bytes = Files.readAllBytes(
                        root.resolve(name.replace('.', '/') + ".class"));
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException ex) {
                throw new ClassNotFoundException(name, ex);
            }
        }
    }

    static final class LabelLoader extends SecureClassLoader {
        private final Path root;
        private final URL label;

        LabelLoader(Path root, URL label) {
            super(OriginDemo.class.getClassLoader());
            this.root = root;
            this.label = label;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!NAME.equals(name)) {
                throw new ClassNotFoundException(name);
            }
            try {
                byte[] bytes = Files.readAllBytes(
                        root.resolve(name.replace('.', '/') + ".class"));
                CodeSource declared =
                        new CodeSource(label, (Certificate[]) null);
                return defineClass(
                        name, bytes, 0, bytes.length, declared);
            } catch (IOException ex) {
                throw new ClassNotFoundException(name, ex);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path jar = Path.of("build/helper.jar").toAbsolutePath();
        Path root = Path.of("build/lib");

        CodeSource appSource =
                OriginDemo.class.getProtectionDomain().getCodeSource();
        System.out.println("appSourceIsDirectory="
                + Files.isDirectory(
                        Path.of(appSource.getLocation().toURI())));

        try (URLClassLoader loader = new URLClassLoader(
                new URL[] { jar.toUri().toURL() },
                OriginDemo.class.getClassLoader())) {

            Class<?> cls = loader.loadClass(NAME);
            CodeSource source = cls.getProtectionDomain().getCodeSource();
            System.out.println("jarCodeSourceMatches="
                    + jar.toRealPath().equals(
                            Path.of(source.getLocation().toURI())
                                    .toRealPath()));
            System.out.println("jarDefiningLoaderMatches="
                    + (cls.getClassLoader() == loader));
            System.out.println("classResourceAvailable="
                    + (loader.getResource(
                            "demo/lib/Helper.class") != null));
        }

        Class<?> plain = new PlainBytesLoader(root).loadClass(NAME);
        CodeSource plainSource =
                plain.getProtectionDomain().getCodeSource();
        System.out.println("plainByteLocationNull="
                + (plainSource == null
                    || plainSource.getLocation() == null));

        URL label = new URL("file:/synthetic/location.jar");
        Class<?> tagged = new LabelLoader(root, label).loadClass(NAME);
        System.out.println("labeledCodeSourceSynthetic="
                + label.equals(tagged.getProtectionDomain()
                        .getCodeSource().getLocation()));
        System.out.println("sameNameDifferentClass="
                + plain.getName().equals(tagged.getName()) + ","
                + (plain != tagged));
    }
}
~~~

#### Intent of each loader

- `PlainBytesLoader` reads bytes directly using `Files.readAllBytes` and uses `ClassLoader.defineClass(name, bytes, ...)`. With the JDK's default protection domain in this example, **no location URL is assigned**. **The `CodeSource` object itself does not necessarily have to be null; `getLocation()` itself can be null**.
- `LabelLoader` extends `SecureClassLoader` and uses the protected overload `defineClass(name, bytes, offset, length, CodeSource)`. It **explicitly declares** a URL `file:/synthetic/location.jar` even though the bytes were read from `build/lib`. The path `/synthetic/location.jar` **does not need to exist** for this metadata to be set.
- `URLClassLoader` uses a URL pointing to a real JAR. It extends `SecureClassLoader` and provides a `CodeSource` from the loaded origin as governed by the API.
- All three loaders use the application loader as their parent, but `demo.lib.Helper` is **not** on the app runtime classpath. Therefore, each loader can define its own copy of `Helper`.

Using **`NAME`** and explicit source files intentionally separates **class identity** from **location metadata**.

### 6.4. Compiling/running from the `demo` directory

Linux/macOS:

~~~sh
mkdir -p build/app build/lib
javac --release 17 -d build/lib src/lib/demo/lib/Helper.java
jar --create --file build/helper.jar -C build/lib .
javac --release 17 -d build/app src/app/OriginDemo.java
java -cp build/app OriginDemo
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/app, build/lib | Out-Null
javac --release 17 -d build/lib src/lib/demo/lib/Helper.java
jar --create --file build/helper.jar -C build/lib .
javac --release 17 -d build/app src/app/OriginDemo.java
java -cp build/app OriginDemo
~~~

**Exact stdout**, verified with JDK 21 and `javac --release 17` after building the `demo` tree:

~~~text
appSourceIsDirectory=true
jarCodeSourceMatches=true
jarDefiningLoaderMatches=true
classResourceAvailable=true
plainByteLocationNull=true
labeledCodeSourceSynthetic=true
sameNameDifferentClass=true,true
~~~

All checks intentionally print **booleans** instead of machine-dependent absolute paths. The two values on the last line are:
1. `plain.getName().equals(tagged.getName()) == true`;
2. `plain != tagged == true`.

### 6.5. Reading the results correctly

| Output | What it proves |
|---|---|
| `appSourceIsDirectory=true` | `OriginDemo` running from the `build/app` directory has a CodeSource URL pointing to the directory-style classpath root |
| `jarCodeSourceMatches=true` | The CodeSource location of `Helper` defined by `URLClassLoader` matches the actual JAR URL of the demo |
| `jarDefiningLoaderMatches=true` | `Helper` in the first branch was indeed defined by the specified loader |
| `classResourceAvailable=true` | The resource `demo/lib/Helper.class` exists in the JAR along the loader's lookup path |
| `plainByteLocationNull=true` | Custom `defineClass` does not require a location URL; **this does not mean bytecode was not read** |
| `labeledCodeSourceSynthetic=true` | A custom `SecureClassLoader` can attach a CodeSource URL of its own choosing |
| `sameNameDifferentClass=true,true` | Two classes with the same binary name but different defining loaders can be two distinct runtime types |

**Semantic limitation:** this example proves that `CodeSource` is data attached when defining a class, not a supply-chain verification mechanism. If you need to know where bytes were actually loaded from, you must cross-check the loader implementation, artifacts, cryptographic hashes, and deployment process.

### 6.6. Practice variations

**Variation A — Print actual URLs:** replace the boolean lines with `System.out.println(source.getLocation())`. The output will contain machine-specific paths; therefore it is not included as fixed stdout.

**Variation B — Change the source file:** have `PlainBytesLoader` read `build/lib` as before, but change the `label` URL. `labeledCodeSourceSynthetic` remains true when compared against the newly assigned URL, even though the bytes did not change. This proves its metadata role.

**Variation C — Run with the wrong classpath:** add `build/helper.jar` to `-cp` when running. The application loader may define `Helper` before the child loaders, causing `jarDefiningLoaderMatches` to no longer be true. This is the effect of **parent-first delegation**, not a `CodeSource` bug.

**Variation D — Resource lookup:** call `loader.getResource("demo/lib/Helper.class")` and print the URL. It may have the form `jar:file:...!/demo/lib/Helper.class`, which differs from the CodeSource URL `file:.../helper.jar`.

## 7. Why Is CodeSource Not an Artifact Security Check?

### 7.1. A location URL does not authenticate bytes

The `CodeSource(URL, certificates)` contract allows an application/loader to set the **CodeSource location** from data it chooses. The `LabelLoader` branch in the demo uses a URL that is not where the bytes were read from. Therefore:

~~~text
CodeSource.getLocation() != cryptographic evidence of source bytes
~~~

If you are checking "is this plugin the exact signed and approved JAR?", **comparing URL strings alone is not enough**. Use an integrity/signature verification process or artifact hashes from a trusted channel, along with a controlled loader policy.

### 7.2. Certificates and CodeSigners do not automatically mean a class is trustworthy

`CodeSource.getCertificates()` or `getCodeSigners()` may return `null` or no data if unsigned or if the loader does not supply signing information. Even when data is present, how it is created and validated still depends on the JAR verification mechanism, trust stores, trust policy, and the loader in use.

Merely **attaching** a `CodeSource` does not turn an application into a standard signature-verification system. With `URLClassLoader` reading signed JARs, there are checks related to JAR verification and signer consistency; building a trust policy still requires specifying how inputs are verified.

### 7.3. A ProtectionDomain can be reused

When using `ClassLoader.defineClass` with an overload that does not provide a protection domain, the JDK attaches a **default protection domain** per the contract. You should not assume each `Class<?>` has its own distinct CodeSource URL or its own ProtectionDomain object.

On the other hand, `SecureClassLoader` can create/cache protection domains based on `CodeSource`; two classes from the same JAR can share the same codebase. `CodeSource` is not a "file read event" log for each individual class.

### 7.4. Runtime module and source location are not equivalent

With JPMS:

~~~java
Module module = SomeType.class.getModule();
System.out.println(module.isNamed());
System.out.println(module.getName());
~~~

This is an illustrative snippet. `module.getName()` indicates the module name (which can be `null` for an unnamed module), not the JAR URL. In custom module layers, a module can come from a runtime image, a directory, or a modular JAR; `Module` and `CodeSource` answer different questions.

## 8. Diagnosing Class Location in Real-World Applications

A reliable workflow when suspecting a wrong JAR version:

1. **Identify the exact runtime `Class<?>`:** via an object, stack trace, or the class under investigation.
2. **Print the binary name, defining ClassLoader, and module:** distinguish two classes with the same name defined by two loaders.
3. **Read `ProtectionDomain`/`CodeSource` with null guards:** obtain the location URL if available; if `null`, report "no location" without fabricating an origin.
4. **Check the resource URL and class-loading logs:** `SomeType.class.getResource("SomeType.class")`, along with loader/framework-specific diagnostics if needed.
5. **Compare the runtime JAR against the build dependency graph:** in Maven/Gradle, version resolution is one thing; what files get copied into a container, which JARs appear on the launcher classpath, and which loader actually runs are another.
6. **Inspect the actual launcher:** `java -cp`, `java -jar`, module path, IDE, Spring Boot launcher, application server, or plugin container may construct classpaths differently.
7. **If the URL points to a JAR:** use `jar --list --file path/to/foo.jar` and checksum tools to cross-check the artifact, rather than trusting the URL alone.
8. **If the URL is null or synthetic:** read the custom loader implementation, byte sources/caches, resource mappings, and where the protection domain is assigned.
9. **If the class exists but still fails:** examine the specific linkage error, `NoSuchMethodError`, `IllegalAccessError`, `ClassCastException`, versions, and module access.
10. **If security proof is required:** verify cryptographic hashes or JAR signatures against your own trust policy; `CodeSource` metadata is only a clue.

### 8.1. Class-loading logs in HotSpot

You can run the program with:

~~~sh
java -Xlog:class+load=info -cp build/app OriginDemo
~~~

The log typically includes the class name and the source reported by the VM/loader, though the format and completeness depend on the runtime/JDK. Do not treat `-Xlog` as an API that replaces independent bytecode verification.

### 8.2. Comparing source location against actual bytes

If you need to conclude "which bytes defined this class," `CodeSource` information **is not enough**. You need to:

- Collect the exact JAR/version artifact in the runtime environment and hash it.
- Or, for a custom loader, instrument/log at the `readAllBytes`/`defineClass` site and hash the exact byte array before defining.
- With agent redefinition/instrumentation, note that the running class bytes may have been transformed compared to the bytes in the original file.
- Keep logs with timestamps, versions, and loader identity, and avoid logging sensitive paths or secrets in production logs.

**Scope limitation:** Core Java does not provide a universal `Class.getOriginalBytecodePath()` API that returns the exact origin of every class in every ClassLoader. `CodeSource` is one piece of information, not a complete verification solution.

## 9. Common Pitfalls to Avoid

1. **"`getCodeSource().getLocation()` is always a JAR file."** False: it can be a directory, another URL, or `null`.
2. **"If CodeSource is null, the JVM failed to load the class."** False: the class already exists; only the source metadata is missing.
3. **"The CodeSource object is always null when a custom loader uses `defineClass(byte[])`."** False: it can exist while `getLocation()` is `null`, as demonstrated.
4. **"`getLocation()` returns the `.class` file path."** False for JAR sources: it is usually the URL of the **archive/codebase**, not the individual entry.
5. **"Having a class resource URL guarantees the running bytes match the current resource."** False for custom loaders, instrumentation, modified archives, and other caching mechanisms.
6. **"Finding a `.class` resource proves that loader defined the runtime class."** False: resource lookup and defining loader/class identity are separate steps.
7. **"A CodeSource URL is proof of a verified digital signature."** False: a URL does not verify cryptographic provenance.
8. **"Two classes with the same name and the same CodeSource URL are always the same runtime type."** False if their defining loaders differ.
9. **"The Maven/Gradle cache path is always the CodeSource location at runtime."** False for shaded JARs, repackaging, containers, and custom loaders.
10. **"`URL.getPath()` is a filesystem Path that can be used directly."** False if the URL is percent-encoded, uses a non-`file` protocol, or has platform-specific path quirks.
11. **"The module name tells you the JAR URL."** False: module identity and code source origin are different.
12. **"The system classpath lists every class source."** False for bootstrap/platform modules and plugin/framework loaders.
13. **"If the location points to a non-existent file, the class was never loaded."** False: the URL may be synthetic metadata, the file may have been moved, or the loader may have read the bytes into memory.
14. **"You can secure a plugin just by changing its CodeSource without anything else."** False: security requires a trust policy and dedicated verification mechanisms.

## 10. Self-Check Questions

1. What kinds of information does `CodeSource` store besides the URL?
2. Which metadata does `Class.getProtectionDomain()` provide access to?
3. Why should you have null guards for both `CodeSource` and `getLocation()`?
4. How do location URLs typically differ between a class loaded from a directory and a class loaded from a JAR?
5. Given `jar:file:/libs/x.jar!/p/X.class`, what URL does `CodeSource` location typically point to?
6. Why does `CodeSource.getLocation()` not prove that the bytes were actually read from that URL?
7. Does a custom `ClassLoader.defineClass(name, bytes, ...)` guarantee a non-null location URL?
8. What metadata does `SecureClassLoader.defineClass(name, bytes, ..., CodeSource)` allow a loader to control?
9. Do two classes with the same binary name and the same source URL but different loaders necessarily have the same runtime identity?
10. Does reading `SomeType.class.getResource("SomeType.class")` always yield the exact loaded bytes? Why or why not?
11. Why is `Path.of(location.toURI())` only appropriate when the URL represents a filesystem resource?
12. When encountering `NoSuchMethodError`, how should you verify which artifact/version is actually running?
13. How do `Module.getName()` and `CodeSource.getLocation()` answer different questions?
14. When a custom loader uses bytes from memory or the network, what states can `CodeSource` have?
15. In the example, why is `labeledCodeSourceSynthetic=true` even though the bytes were still read from `build/lib`?
16. If a class is instrumented by an agent after being loaded, does `CodeSource` prove that the running bytes have not been transformed?
17. When the CodeSource location is `null`, what additional diagnostic sources are useful?
18. Why should you use checksums/signature verification instead of just comparing URLs when you need to authenticate a plugin's origin?

**Completion criteria:** run the Java 17+ example and explain all seven lines of stdout; distinguish **CodeSource URL**, **class resource**, **defining loader**, **Module**, and **the bytes that defined the class**; handle nulls properly and establish a diagnostic workflow without drawing conclusions beyond what the APIs provide.

## 11. Official Documentation

- [Java SE 21 — `CodeSource`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/CodeSource.html): location URL, certificates, code signers, `getLocation()`.
- [Java SE 21 — `ProtectionDomain`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/ProtectionDomain.html): class protection domain and CodeSource metadata.
- [Java SE 21 — `Class.getProtectionDomain()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getProtectionDomain()): retrieves the protection domain attached to the runtime class.
- [Java SE 21 — `SecureClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureClassLoader.html): `defineClass` overload accepting `CodeSource`.
- [Java SE 21 — `URLClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): finding classes from JAR/directory URLs and related source information.
- [Java SE 21 — `ClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `defineClass`, default protection domain, delegation, and defining loader.

In the example, **CodeSource metadata is created by the loader**, so this article makes no promise that a URL by itself authenticates an artifact. Java 17+ is sufficient to compile and run; stdout was verified with JDK 21 and `javac --release 17`.