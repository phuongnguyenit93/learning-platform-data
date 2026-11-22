# Mapping Class Names to Explicitly Bounded Data Sources in a Custom ClassLoader

## 1. The Problem to Solve

A custom `ClassLoader` can define Java classes from data retrieved from a directory, a JAR, a database, the network, or a dedicated bytecode repository. However, going from a **binary class name** such as `demo.plugins.Greeting` to a **byte data source** is a critical design decision. If every class name string is turned into an arbitrary path or URL without bounds, the loader can easily end up loading the wrong bytecode, accessing locations outside the allowed area, depending on an unclear lookup order, or consuming excessive resources.

The goal of this lesson is to design an **explicit, bounded mapping**:

1. Determine **which binary class names are accepted**.
2. Determine **the byte source corresponding to each name**.
3. Restrict **the directories or repositories allowed to be read** and validate paths after normalization.
4. Limit **the data size, number of classes, or amount of work** according to operational requirements.
5. Distinguish **parent delegation** from the **private bytecode source** controlled by this loader.
6. Explain how to return `ClassNotFoundException` or an appropriate error instead of guessing another class when the name/source does not match.
7. Do not confuse bytecode validity, the ability to define a class, and trust/safe access for executed code.

Example of the principle:

~~~text
Binary name                Approved source
----------------------------------------------------------
demo.plugins.Greeting   ->  plugin-classes/demo/plugins/Greeting.class
demo.plugins.Parser     ->  [not in allowlist: rejected]
java.lang.String        ->  bootstrap/platform via delegation

Never use a user-supplied name to arbitrarily
select a file outside the trusted root or an arbitrary URL.
~~~

**The protection scope is very important:** the bounded mapping here protects **the data source that the custom loader's `findClass` reads and defines on its own**. It is **not a security sandbox to prevent plugin code from reading files, opening network connections, or using any Java API**. In Java 17+, you should not rely on `SecurityManager` as a trustworthy sandboxing measure; the Java Security Manager was deprecated for removal in Java 17 and is not a mechanism for isolating arbitrary code in new designs.

## 2. Class Names Used in the API: Binary Name Rather Than Path Name

`ClassLoader.loadClass(String name)` and `findClass(String name)` work with the **binary name** of a type, for example:

| Kind | Example |
| --- | --- |
| Class in a package | `com.example.Greeting` |
| Class in the unnamed package | `Greeting` |
| Nested member class | `com.example.Outer$Inner` |
| Corresponding class file entry name | `com/example/Greeting.class` |
| Corresponding resource path | `com/example/Greeting.class` |
| JVM internal name in the class file | `com/example/Greeting` |

Do not replace the binary name string with a URL, `../secret`, or an arbitrary path. Nested class names in class files typically use `$`, rather than the `.` of source syntax. For example, `Outer.Inner` may be the canonical/source name, whereas the binary name is `Outer$Inner`.

A convention that **can** be used is:

~~~java
String resource = binaryName.replace('.', '/') + ".class";
~~~

This is an **illustrative snippet**, not a policy safe enough to use with uncontrolled input. It converts a name into a path, but it **does not answer** which names are valid, which directories are permitted, whether the caller has permission to request that name, whether the file lies within the root, whether the bytes are an actual class file and within the size limit.

If the requirements are very narrow, an **explicit allowlist map** is usually clearer than converting every name into a path.

## 3. Two Common Mapping Approaches and When to Choose Them

### 3.1. Explicit Per-Binary-Name Mapping

Example:

~~~java
Map<String, Path> approved = Map.of(
        "demo.plugins.Greeting",
        Path.of("demo", "plugins", "Greeting.class")
);
~~~

This clearly shows:

- Only `demo.plugins.Greeting` is looked up by the custom loader in its private repository.
- The path is a **relative path** under the trusted root, not an absolute path determined by the caller.
- Another name such as `demo.plugins.Admin` will have no mapping.
- Simply being in `demo.plugins` is still **not enough** for a name to be loaded if it is not in the allowlist.

Pros: easy to review, audit, hash/checksum, and version-pin. Cons: with many classes, a large manifest must be managed; the manifest should be generated from a controlled build/plugin-registration process rather than manually entering thousands of entries.

### 3.2. Validated Prefix/Package Mapping

For larger repositories, you can accept all names matching an **exact package boundary**, and then convert them by path convention, for example `demo.plugins.*`. However, you must also check:

- The binary name has syntax permitted by the policy.
- The prefix is `demo.plugins.` **including the trailing dot**, to avoid accidentally permitting `demo.pluginsEvil.*`.
- It contains no `/`, backslashes, path traversal sequences, or forged names.
- Whether the portion after the prefix matches the binary name forms that need to be supported (including nested names `$`).
- The final path must reside inside the verified root, after accounting for symlinks and the filesystem's canonicalization behavior.

**Do not treat a simple regex as the standard for all valid Java names** if the tool needs to support Unicode identifiers, generated class names, nested/anonymous forms, or special definitions. A policy that permits only a subset is valid if clearly stated; do not claim that it validates every valid binary name under the JVM spec.

The hands-on example below uses an **explicit allowlist** to make the mapping problem as clear as possible.

## 4. Three Boundaries to Define Explicitly

### 4.1. Name Boundary (Namespace)

Allow registered binary names or package scopes. A custom loader should not define foundational packages such as `java.*` on its own; the JVM restricts defining `java.*` in application class loaders, and attempting to load a separate copy of a core API can cause serious type identity errors.

The list of permitted names can be supplied by a trusted configuration, a build-generated manifest, or an authenticated registry. **End-user input should not by itself grant permission to load an arbitrary class**.

### 4.2. Data Boundary (Source Boundary)

The root directory or data repository must be selected from trusted configuration, not freely concatenated from input. For a filesystem:

~~~text
trustedRoot = /srv/app/plugins/v1/classes/
requested = demo.plugins.Greeting
relative = demo/plugins/Greeting.class
candidate = trustedRoot/relative
~~~

Checks:

1. The relative path is genuinely **not absolute**.
2. After canonicalization/real-path resolution, the candidate is still **inside** the trusted root.
3. The source is an allowed regular file and its size does not exceed the limit.
4. If symlinks are accepted, the **final target** of the symlink is still inside the root; if symlinks are not allowed, each path component must be checked.
5. Do not treat `String.startsWith("/srv/app/plugins")` as a path boundary: `/srv/app/plugins-evil/...` shares the same string prefix but lies outside the root. Use `Path.startsWith(otherPath)` after appropriate normalization.

In a filesystem environment where untrusted parties can make concurrent modifications, calling `toRealPath` and then reading the file can suffer from a **TOCTOU race**. Checking the path before opening is not a guarantee against an attacker capable of swapping a symlink or directory between the two steps. Under such a threat model, you need to design an immutable/permission-controlled repository or use access primitives via a directory handle/`SecureDirectoryStream` when supported by the provider, combined with OS-level controls.

### 4.3. Resource Boundary (Resource Limits)

A class file might be too large, or a plugin repository might have millions of entries. Limits need to match actual needs:

- **Maximum bytes per class file**, capped at the read step, not only via a prior `Files.size` check.
- **Number of allowed classes** or number of class definitions according to the manifest.
- **I/O duration or request timeout** if bytes come from the network.
- **Concurrent requests/caches** to avoid memory blow-up.
- **Trusted source/hash/signature** when the plugin supply chain is an important factor.

A byte limit does not prove bytecode is safe; nor is JVM verification a file/network permission sandbox. An allowlist restricts **what the loader looks up on its own**, rather than replacing process/container isolation for untrusted code.

## 5. Standalone Java 17+ Example: A Loader That Reads Only One Class from a Fixed Root

We create a host app and a separate plugin class. The following custom loader:

- Allows only the **binary name `demo.plugins.Greeting`** in the private repository.
- Reads the corresponding file from a root passed **once when creating the loader**.
- Uses `toRealPath` and `Path.startsWith` to reject targets that escape outside the root.
- Checks for a regular file and caps reading at **1 MiB**.
- Calls `defineClass` with **the exact requested binary name**, so that the JVM verifies the name inside the class file.
- Uses the platform loader as its parent, allowing required Java runtime classes to be found through delegation.
- Does not load a class on its own when the name differs from the allowlist, even if a file with another name exists in the root.

### 5.1. Directory Tree

~~~text
bounded-loader-demo/
├── plugin-src/
│   └── demo/
│       └── plugins/
│           └── Greeting.java
└── host-src/
    └── HostDemo.java
~~~

After compilation, we have two independent directories:

~~~text
bounded-loader-demo/
├── plugin-classes/
│   └── demo/
│       └── plugins/
│           └── Greeting.class
└── host-classes/
    ├── HostDemo.class
    └── HostDemo$BoundedLoader.class
~~~

**Important:** do not include `plugin-classes` on the host application classpath. If the parent can also see the plugin class, parent-first delegation may return the class defined by the parent, causing the demo to no longer prove that the loader loads its own bytecode.

### 5.2. Plugin File: plugin-src/demo/plugins/Greeting.java

~~~java
package demo.plugins;

public class Greeting {
    public String message() {
        return "hello from mapped class";
    }
}
~~~

This is a standalone Java file for the plugin. The default constructor provided by javac has access appropriate for a public class. It does not reference any host class.

### 5.3. Host File: host-src/HostDemo.java

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class HostDemo {
    static final class BoundedLoader extends ClassLoader {
        private static final int MAX_BYTES = 1_048_576;

        private final Path trustedRoot;
        private final Map<String, Path> approved = Map.of(
                "demo.plugins.Greeting",
                Path.of("demo", "plugins", "Greeting.class")
        );

        BoundedLoader(Path root) throws IOException {
            super(ClassLoader.getPlatformClassLoader());
            this.trustedRoot = root.toRealPath();

            if (!Files.isDirectory(trustedRoot)) {
                throw new IOException("Not a directory: " + trustedRoot);
            }
        }

        @Override
        protected Class<?> findClass(String binaryName)
                throws ClassNotFoundException {
            Path relative = approved.get(binaryName);

            if (relative == null) {
                throw new ClassNotFoundException(
                        "Not allowlisted: " + binaryName);
            }

            try {
                if (relative.isAbsolute()) {
                    throw new IOException("Expected relative path");
                }

                Path candidate = trustedRoot.resolve(relative).toRealPath();
                if (!candidate.startsWith(trustedRoot)) {
                    throw new IOException("Outside trusted root");
                }
                if (!Files.isRegularFile(candidate)) {
                    throw new IOException("Not a regular class file");
                }

                byte[] bytes;
                try (InputStream in = Files.newInputStream(candidate)) {
                    bytes = in.readNBytes(MAX_BYTES + 1);
                }

                if (bytes.length == 0 || bytes.length > MAX_BYTES) {
                    throw new IOException("Invalid class-file size");
                }

                return defineClass(
                        binaryName, bytes, 0, bytes.length);
            } catch (IOException error) {
                throw new ClassNotFoundException(
                        "Cannot read approved class: " + binaryName,
                        error);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: HostDemo <plugin-classes-directory>");
        }

        BoundedLoader loader = new BoundedLoader(Path.of(args[0]));

        Class<?> plugin = loader.loadClass("demo.plugins.Greeting");
        Object instance = plugin.getDeclaredConstructor().newInstance();
        String message = (String) plugin.getMethod("message")
                .invoke(instance);

        System.out.println("defined by bounded loader: "
                + (plugin.getClassLoader() == loader));
        System.out.println("message: " + message);

        Class<?> stringType = loader.loadClass("java.lang.String");
        System.out.println("standard class uses bootstrap: "
                + (stringType.getClassLoader() == null));

        try {
            loader.loadClass("demo.plugins.Unknown");
            System.out.println("unknown plugin class rejected: false");
        } catch (ClassNotFoundException expected) {
            System.out.println("unknown plugin class rejected: true");
        }
    }
}
~~~

Technical points of the code:

- `Map.of` is a structurally immutable map (it provides no API to modify entries at runtime); the mapping configuration does not change between lookups.
- `toRealPath()` on the root and candidate resolves the actual existing path, including symlinks according to the provider's default behavior. `Path.startsWith` checks **path components**, avoiding string-prefix confusion.
- `readNBytes(MAX_BYTES + 1)` limits the bytes read into the array; if the file is larger than 1 MiB, the array will contain one extra byte and then be rejected. Do not use unbounded `Files.readAllBytes` on a source that may be very large.
- `defineClass(binaryName, bytes, 0, bytes.length)` requires the bytes to represent a class matching the name being loaded. If the file bytes have an invalid format or the wrong internal class name, the JVM reports the corresponding error and does not rename the class after the filename.
- The parent loader is the **platform loader**, so core classes such as `java.lang.String` are still handled by the bootstrap/runtime loaders.
- `findClass` only manages the private source; the default `loadClass` still performs delegation to the parent. **Do not treat this as an absolute allowlist of every class that the loader can return.**

### 5.4. Compiling and Running

Open a terminal in the `bounded-loader-demo` directory. The following commands run on JDK 17 or later on Windows, Linux, and macOS when the directories are created properly:

~~~bash
javac --release 17 -d plugin-classes plugin-src/demo/plugins/Greeting.java
javac --release 17 -d host-classes host-src/HostDemo.java
java -cp host-classes HostDemo plugin-classes
~~~

**Exact stdout when running with the files above and a standard configuration:**

~~~text
defined by bounded loader: true
message: hello from mapped class
standard class uses bootstrap: true
unknown plugin class rejected: true
~~~

Explanation:

1. Because only `host-classes` is included in `-cp`, the host's system/app loader is not provided with the bytes for `demo.plugins.Greeting` from the plugin directory.
2. `BoundedLoader` calls its parent first; the platform loader does not have `demo.plugins.Greeting` in the standard JDK, so it proceeds to the loader's `findClass` and reads the bytes from the trusted root.
3. `getClassLoader() == loader` is true because **this loader is the defining loader** of the plugin class.
4. Reflection creates an instance and invokes the public method `message()`. The returned String is a Java core type, shared properly through bootstrap/platform delegation.
5. `java.lang.String` is found through the parent/bootstrap loader; the plugin loader does not define its own copy of String.
6. The name `demo.plugins.Unknown` is not in the allowlist. The parent cannot find that name in the demo setup; `findClass` throws `ClassNotFoundException`, so the application prints the rejection result.

## 6. Limitations of the Example: Protecting the Mapping, Not Sandboxing the Plugin

The example in Section 5 is a **bounded filesystem mapping sample for learning the API**, not a safe runtime for untrusted code. The limitations are intentionally stated clearly:

**First, the parent still has the authority to look up classes.** If you call `loader.loadClass("java.util.List")`, the parent/bootstrap loader can return the Java runtime type. This is necessary for the plugin to execute Java code. If the author expects that only `Greeting` and absolutely no other class can be returned, then a `findClass` allowlist **does not meet** that expectation. Some plugin mechanisms try to override `loadClass` to enforce a different policy, but arbitrarily blocking core types will cause plugin linking to fail. Do not try to turn a class loading boundary into a system security permission.

**Second, the root directory must be trustworthy and have write-access controls.** `toRealPath()` + `startsWith` prevents the current path from pointing outside the root at check time; they do not provide an atomic transaction between checking and opening the file. If an attacker has permission to swap symlinks or replace files in the repository concurrently, you need an immutable repository, OS file ownership/permissions, bytecode signing, or an appropriate directory-handle-based file opening mechanism.

**Third, the byte limit does not verify the trustworthiness of the bytecode.** A class file smaller than 1 MiB can do a great deal when initialized/executed. JVM verification protects bytecode type safety, but does not restrict all I/O, CPU, network behavior, or static initializer side effects.

**Fourth, a custom loader does not automatically make unloading/reloading safe.** A `Class<?>` already defined by a loader cannot arbitrarily have its “bytes swapped” simply by editing the file and calling `loadClass` again. To use a new definition of the same binary name, you typically must create a new loader, manage its lifecycle, and release references to the old loader if you want GC to be able to unload it.

**Fifth, a byte cap and allowlist are not a process-wide resource quota.** The JVM may load other dependencies, and the plugin may allocate heap or spawn threads; the application needs additional limits and isolation if the threat model requires them.

### 7. Why Not Use className.replace to Read Any File?

A commonly seen snippet:

~~~java
@Override
protected Class<?> findClass(String name)
        throws ClassNotFoundException {
    String file = name.replace('.', '/') + ".class";
    byte[] bytes = Files.readAllBytes(Path.of("/some/root", file));
    return defineClass(name, bytes, 0, bytes.length);
}
~~~

**This is an illustrative anti-pattern; it is not a standalone runnable file.** Besides lacking `IOException` handling, the snippet has these issues:

- Does not specify which packages or class names are actually permitted.
- Has no check that the actual candidate path lies inside the trusted root.
- Does not handle symlinks that redirect the candidate to a file outside the root.
- Does not limit the file size before allocating memory to read the entire file.
- Does not explicitly state whether dependencies are delegated to the parent or loaded by the loader itself.
- Does not distinguish between “class not found” and “path rejected by policy”.
- Does not guarantee that the bytes come from an approved artifact.

Constructing a path is merely a **mechanism for transforming the name's format**, not a complete “class name → trusted data source mapping” policy.

For a library with a large number of valid classes, you can generate a manifest at build time to map names to JAR entries, add hashes and versions, and apply the same scope-control philosophy. You should not broaden permissions simply by allowing all binary names and all URLs.

## 8. If the Source Is a JAR Instead of a Directory

A design can map:

~~~text
com.example.spi.PluginA -> plugins/plugin-a-v3.jar!/com/example/spi/PluginA.class
com.example.spi.PluginB -> plugins/plugin-b-v1.jar!/com/example/spi/PluginB.class
~~~

This is a **conceptual map**, not a filesystem path syntax that `Path.of` understands literally. `!/...` is reminiscent of the `jar:file:...!/entry` resource URL syntax.

Required bounds:

1. Select approved JARs via a manifest/registry, rather than deriving an arbitrary URL from the class name.
2. Restrict the size and origin of the JAR; defend against excessive compression/zip bombs if the source is untrusted.
3. Allow only registered entries; validate entry names properly and do not allow path traversal during extraction.
4. Limit the class bytes that the loader reads from each entry; avoid unbounded reads.
5. Have a clear parent delegation strategy for host/JDK APIs.
6. Choose existing `URLClassLoader`/module APIs when appropriate, instead of writing a custom ZIP/class file parser.
7. Close `URLClassLoader` when no longer in use to release open resources; closing it does not immediately unload all defined classes.

Java 17 API example:

~~~java
try (java.net.URLClassLoader loader =
         new java.net.URLClassLoader(
                 new java.net.URL[] { approvedJar.toUri().toURL() },
                 ClassLoader.getPlatformClassLoader())) {
    Class<?> type = loader.loadClass("com.example.spi.PluginA");
}
~~~

**Illustrative snippet**, assuming `approvedJar` is a validated `Path` that actually contains the class. Even though the JAR URL is restricted to a single file, `URLClassLoader` itself **does not create a class-name allowlist** like the `BoundedLoader` example; if a strict allowlist is needed, check the name at the appropriate API wrapper/loader policy layer. Parent delegation can also return classes from the parent.

## 9. If the Source Is the Network, a Database, or Object Storage

You can map the binary name to a **stable internal identifier**, for example:

~~~text
demo.plugins.Greeting
    -> artifact-id: plugin-greeting@sha256:...
    -> trusted object storage entry
    -> byte[] after verification / limits
    -> defineClass(binaryName, ...)
~~~

The key point: **a binary name is not a URL chosen by the caller**. The loader should not do:

~~~java
// NOT a safe pattern: the caller controls the source URL
URL url = new URL(userInput);
byte[] bytes = url.openStream().readAllBytes();
~~~

This is an illustrative anti-pattern; it is not a complete program. In addition to unbounded bytes, this approach risks accessing unintended network endpoints (SSRF in a service context), lacks integrity verification, and makes cache/version coordination difficult.

A more sound design:

- A service registry/manifest maps **allowed binary names** to verified artifact identifiers.
- The storage client accesses **only configured buckets/endpoints**.
- TLS, authn/authz, and hashes/signatures ensure the data comes from an authorized source.
- Timeouts, bounded retries, byte limits, and circuit breakers prevent hanging the loader thread.
- Fetch/validation errors are wrapped appropriately in `ClassNotFoundException` when the name has no definition; bytecode/linkage errors are left for the JVM to report with their corresponding causes.
- Include observability (logs/metrics) for the requested name, artifact ID, and fetch duration without leaking secrets.
- Do not trigger unexpected network fetches on every `loadClass`; consider preloading approved data or using a bounded cache.

## 10. Parent-First Delegation and Allowlist: Which Boundary Is Applied?

The default implementation of `ClassLoader.loadClass(String, boolean)` typically works as follows:

~~~text
loadClass(name)
      |
      v
findLoadedClass(name)
      |
      v
parent.loadClass(name)
      |
  not found
      |
      v
findClass(name)
      |
      v
defineClass(name, bytes, ...)
~~~

Therefore, if the parent already knows `demo.plugins.Greeting`, the child may **not read** its own mapped file, even if the allowlist contains that name.

Design implications:

- In plugin isolation, place shared APIs in the parent and independent implementations in a separate loader.
- Do not assume an allowlist in `findClass` blocks everything the parent can return.
- If you need to **strictly block a binary name** from being returned, you must design the policy at the appropriate API/loader-routing layer, taking into account both parent delegation and JVM constraints on core classes.
- If **child-first** is needed for plugin packages, override `loadClass` carefully, avoiding defining core/shared API classes yourself, which causes `ClassCastException`/`LinkageError`. Child-first is not inherently safer.
- The parent loader can be the platform loader, the application loader, or a shared loader; the choice depends on package sharing and the plugin's dependencies.

Distinguish between the **initiating loader** (the loader that receives/participates in the load request) and the **defining loader** (the loader that actually defines the type). When the parent returns a Class, `type.getClassLoader()` reports the defining loader, which may not be the child.

## 11. When to Throw ClassNotFoundException vs. Letting LinkageError Surface

For `findClass(String)`, the primary contract is to throw `ClassNotFoundException` if the loader cannot find a definition for the requested name.

Scenarios:

| Scenario | Handling Approach |
| --- | --- |
| Name is not in the allowlist | `ClassNotFoundException` with an easy-to-debug message |
| Mapped file does not exist | `ClassNotFoundException` with an appropriate `IOException` cause |
| File is outside the trusted root after resolving symlinks | Reject without reading; for example, use `ClassNotFoundException` with a policy/IO cause |
| File is unreadable or exceeds the byte cap | Reject per policy; I/O cause and clear description |
| Bytes are not a valid class file | `defineClass` may throw `ClassFormatError` |
| Bytes carry a binary name different from the requested name | The JVM may throw `NoClassDefFoundError` for the wrong name |
| Disallowed duplicate class name definition in the same loader | `LinkageError` |
| Loader constraint violation during linking | Appropriate `LinkageError` |

**Do not catch all `Throwable` and convert everything into `ClassNotFoundException`.** Doing so masks `OutOfMemoryError`, `LinkageError`, and serious programming issues. The example catches only `IOException` around the byte-reading part; errors thrown by the JVM from `defineClass` preserve their original semantics.

In production environments, if a policy rejects a file because it is outside the trusted root, you can use a clearer internal policy error type in the API above the loader; because the `findClass` interface requires `ClassNotFoundException` when a definition cannot be provided, wrapping a meaningful cause makes sense in the sample implementation.

## 12. Checking the Name Inside Bytecode and Type Identity

`defineClass(name, bytes, 0, bytes.length)` does not simply attach an arbitrary “label” to a byte array. The class file contains an internal type identifier. The JVM checks consistency between the requested name and the definition; if there is a mismatch or malformed bytes, definition fails.

In addition, **runtime type identity** is the combination of:

~~~text
(binary class name, defining ClassLoader)
~~~

Two different loaders can define the same binary name from the same byte array, resulting in two distinct runtime types. Therefore:

- `Class<?>` instances from two loaders can have the same `getName()`, yet `a == b` is `false`.
- Casting an object from version A to the same-named class B can throw `ClassCastException`.
- Each definition has its own static fields/initialization.
- A shared interface/API should be defined by a common parent, rather than bundling multiple copies of the API into different plugin loaders.
- Changing the byte source in the mapping does not “update” an already loaded Class definition. To hot-reload, you usually need to create a new defining loader.

Class loader mapping and class identity are closely linked: **the chosen byte source determines the class content, while the defining loader determines the runtime namespace of that class**.

## 13. Minimum Safety Checks and Practical Limitations

| Risk | Minimum Check | Remaining Limitation |
| --- | --- | --- |
| Arbitrary class name | Signed exact allowlist/manifest | Parent can still load other names |
| Path traversal | Relative path + canonical root + `Path.startsWith` | Concurrent filesystem changes require a stronger model |
| Symlink outside root | Check that `toRealPath` target lies within the root | Subject to TOCTOU race if the repository allows concurrent modifications |
| Oversized file | `readNBytes(MAX+1)` and reject if exceeded | Many small classes can still consume large total memory |
| Forged bytecode | Allowlisted artifact, integrity/hash/signature | Valid bytecode can still execute side effects |
| Dependency conflict | Parent API sharing, version policy | Requires testing and module/loader constraints |
| Malicious network source | Fixed endpoint, auth, timeout, byte cap | Requires credential, retry, and SSRF protection |
| Hot reload memory leak | Loader lifecycle and releasing references | Static caches, TCCL, and threads may retain the loader |

**Product principle:** if a plugin is provided by an untrusted party and you need to prevent access to file/network/process APIs, use **isolation at the process/container/VM level with appropriate OS permissions and policies**. A Java class loader primarily provides a **loading mechanism and type-identity isolation**, not a replacement for a security sandbox.

## 14. How to Write Tests for Bounded Mapping

A good test suite must verify both the happy path and policy rejections:

1. **Correct name, correct source:** `demo.plugins.Greeting` is defined successfully from its corresponding file.
2. **Name outside the allowlist:** `demo.plugins.Unknown` is rejected (unless provided by the parent under the chosen policy).
3. **Missing file:** a root configuration missing the approved file leads to a reasonable error, without falling back to nearby files.
4. **Mismatched class bytes:** the file is named Greeting.class, but inside it contains another class; the JVM must not silently accept the requested name.
5. **Exceeding the byte cap:** a source exceeding the limit is rejected without unbounded reading.
6. **Symlink outside root:** on filesystems allowing symlinks, a canonical target outside the root is rejected.
7. **Parent class:** `java.lang.String` is still found via bootstrap, rather than being self-defined.
8. **Same name in parent:** verify whether parent-first will prioritize the parent or whether the routing policy needs to be changed.
9. **Two independent loaders:** if each loader defines the same bytes, verify that `classA != classB` and that static state is isolated.
10. **Multiple threads requesting the same class:** use proper `ClassLoader.loadClass` synchronization to avoid duplicate self-definition; avoid unsafe custom caches.
11. **Root modified while the loader is active:** determine an anti-race policy or require an immutable data source.
12. **Logging:** rejected names and causes provide enough diagnostic detail, without exposing internal paths or secrets to end users unnecessarily.

You do not need to use a specific testing framework, but make sure the tests distinguish between **class lookup errors**, **policy rejections**, **bytecode verification/linkage**, and **static initializer errors**.

## 15. Common Mistakes When Designing a Mapping Yourself

**Mistake 1: Concatenating input strings directly with a path.** This leads to path traversal, names that do not match the package, and overly broad class-loading permissions.

**Mistake 2: Checking only a string prefix.** `/data/plugins-evil` also starts with `/data/plugins` as a string; use `Path.startsWith` on canonical/real paths.

**Mistake 3: Believing normalize is enough to block symlinks.** `normalize()` handles `.`/`..` syntactically and **does not resolve symbolic links on its own**. `toRealPath` provides the actual target information when the file exists; for repositories with hostile concurrent writes, additional protections are still required.

**Mistake 4: Using uncapped `Files.readAllBytes` from an arbitrary source.** This risks large memory allocations or resource exhaustion.

**Mistake 5: Assuming a findClass allowlist also controls the parent.** The default `loadClass` queries the parent first; other names may be returned from the parent.

**Mistake 6: Redefining `java.lang.*` or a shared API class.** This easily causes JVM constraint violations and type identity conflicts.

**Mistake 7: Swallowing every Throwable and reporting ClassNotFoundException.** This hides information about malformed class file structure, linkage errors, OOM, or runtime errors in static initializers.

**Mistake 8: Calling `resolveClass` yourself and thinking the plugin code has run.** Linking is different from class initialization; you need to understand when `<clinit>` runs.

**Mistake 9: Modifying the file on disk and expecting `loadClass` to return an updated Class.** A Class already defined in the old loader does not change on its own; a new loader may be needed.

**Mistake 10: Treating bytecode verification as a sandbox.** A valid class can access files, the network, or dangerous APIs depending on the process's permissions.

**Mistake 11: Ignoring package metadata/sealing/signers.** When switching to a loader packaging from JARs, you may need to preserve package sealing rules, code source, certificates, and an appropriate `ProtectionDomain`; merely reading bytes and calling `defineClass` does not automatically reproduce all JAR packaging information.

**Mistake 12: Not logging mapping decisions.** When debugging multiple plugins with the same binary name, you need to know the actual defining loader, artifact version, and source identifier, rather than logging only a class name string.

## 16. When to Use URLClassLoader or Built-in APIs?

Writing a custom `ClassLoader` is useful when you need specialized control over source mapping, verification policy, and delegation. However, if you need to load classes from a fixed set of JAR URLs, `URLClassLoader` (Java 17) can be a good fit and reduce the need to read class bytes manually.

In JPMS, if a plugin is a true named module, you should look into `ModuleFinder`, `Configuration`, and `ModuleLayer` to design module resolution and module loaders with proper semantics instead of assuming a directory mapping is sufficient to replace JPMS.

Practical options:

| Need | Design Approach |
| --- | --- |
| Specific classes from a controlled directory | Explicit allowlist + custom `findClass` |
| Multiple approved JARs, classpath-like loading | `URLClassLoader` and a source/URL allowlist |
| Plugins with named modules, requires/exports | JPMS `ModuleFinder`/`ModuleLayer` |
| Dynamically generated bytecode | `defineClass`/hidden-class APIs under an appropriate contract |
| Code from untrusted parties requiring system permission isolation | Process/container isolation, do not use ClassLoader as a sandbox |

## 17. Self-Check

**1. Why is `name.replace('.', '/') + ".class"` not yet a bounded mapping?**  
Because it only converts the name into a path without restricting the names, data source, size, or access permissions.

**2. In what cases is an exact allowlist better than a package prefix?**  
When only a small set of classes is approved or when each class must be tied to a specific artifact/hash/version.

**3. Why must you check `candidate.toRealPath().startsWith(root.toRealPath())`?**  
To detect canonical targets outside the root, even when the path traverses a symlink; TOCTOU must still be considered for repositories with untrusted writers.

**4. Why does `findClass` reject the name Unknown while `loader.loadClass("java.lang.String")` still succeeds?**  
Because parent/bootstrap delegation runs before `findClass` in the default loader.

**5. If a file named Greeting.class contains the bytecode of WrongName, will the JVM treat it as Greeting?**  
No; `defineClass` checks the consistency of the class file name and may report a linkage error.

**6. Does the 1 MiB limit guarantee that plugin code cannot harm the app?**  
No. This is only a byte cap for reading a single class, not permission control over the behavior of Java code.

**7. Why should you not catch `Throwable` around `defineClass` to always return `ClassNotFoundException`?**  
Because you must preserve the original semantics of class file/linkage errors and critical errors such as OOM for accurate diagnosis.

**8. When a parent loader already has the same binary name, will the child define its own copy under the default `loadClass`?**  
Usually no; parent-first delegation will return the parent's Class.

**9. If a class has been loaded from a file, and you edit the file and call `loadClass` again, will it get the new bytes?**  
Not automatically. The defined runtime class still belongs to the old loader; hot reloading typically requires a new loader and lifecycle management.

**10. If you need to actually prevent a plugin from reading the filesystem, is a bounded ClassLoader sufficient?**  
No. You need isolation/permissions at the process, OS, container, or VM level according to the threat model.

## 18. References

- **Java SE 17 — ClassLoader**: `findClass`, `loadClass`, `defineClass`, `getClassLoadingLock`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Java SE 17 — Path**: `resolve`, `normalize`, `startsWith`, `toRealPath`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html
- **Java SE 17 — Files**: `newInputStream`, `isRegularFile`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- **Java SE 17 — InputStream**: `readNBytes`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html
- **Java SE 17 — URLClassLoader**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- **JVMS 17 §5.3 — Creation and Loading** (defining/initiating loaders): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- **JLS 17 §12.2 — Loading of Classes and Interfaces**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2
