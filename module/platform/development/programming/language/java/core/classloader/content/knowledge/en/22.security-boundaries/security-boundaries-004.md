# Avoid Taking Arbitrary Class Names or Paths from Untrusted Data

## 1. The Problem and Safety Principles

A Java application with plugins, a ClassLoader, reflection, or file handling may receive strings from an HTTP request, tenant configuration, queue message, or third-party metadata. Such a string looks harmless while it is still data, but becomes a **privileged decision** if passed directly into `Class.forName`, `ClassLoader.loadClass`, `Files.readString`, `getResourceAsStream`, or `URLClassLoader`.

~~~java
// ANTI-PATTERN: illustrative only, not a standalone program.
String className = request.getParameter("class");
Object plugin = Class.forName(className)
        .getConstructor().newInstance();

String path = request.getParameter("file");
String content = Files.readString(Path.of(path));
~~~

External input can now choose which class to instantiate or which file to read, outside the intended business behavior. Java still enforces class loading rules and Java access control; however, **the ability to locate a class/file does not by itself prove that the caller has permission to use it**.

**Principle:** The client selects an **authorized operation code or resource ID**, while the host manages the mapping to the implementation, ClassLoader, JAR, resource, and actual path.

A better example:

~~~text
Client selects "health" ──> AuthZ ──> Registered HealthJob factory
Client selects "guide"  ──> AuthZ ──> docs/guide.txt from trusted registry
Client sends FQCN or ../../secret ──> rejected
~~~

Checking only the syntax of a class name, file name, or regex **is not** a business authorization check.

## 2. Inputs to Watch Out For

| Untrusted input | API receiving input | Problem |
|---|---|---|
| Binary class name such as `demo.plugin.Report` | `Class.forName(name)` | Input determines which class is requested to initialize |
| Class name from external configuration | `loader.loadClass(name)` | Input determines which class the loader looks up |
| Provider name | Reflection, dependency injection, `ServiceLoader` | May instantiate unapproved implementation code |
| Resource name | `getResource` / `getResourceAsStream` | Reads/discloses internal resources |
| File path | `Path.of(input)` and `Files.readString` | Path traversal, absolute path, symlink |
| Class source URL | `new URLClassLoader(urls, parent)` | Loads bytecode from an untrusted artifact |
| URL to open | `URL.openStream()` | Accesses unexpected source/SSRF if permitted by the application |
| ZIP/JAR entry name | File extraction | Zip Slip, writing files outside the intended directory |

These APIs are not inherently vulnerable; the risk is that the application **hands over target selection to untrusted input** without source controls and authorization.

## 3. Selecting Operations via an Allowlist, Not via FQCN

Instead of letting users send `"java.lang.Runtime"`, `"demo.admin.ResetAll"`, or an arbitrary class name, the API should only accept **predefined tokens** such as `"health"` and `"version"`.

~~~java
// Illustrative code; requires Job/HealthJob/VersionJob and imports.
Map<String, Supplier<Job>> allowed = Map.of(
        "health", HealthJob::new,
        "version", VersionJob::new
);
Supplier<Job> factory = allowed.get(userKey);
if (factory == null) {
    throw new IllegalArgumentException("Unsupported operation");
}
Job selected = factory.get();
~~~

The security comes from **who controls the map**: if a client can send both the `key` and an FQCN and register a new entry itself, this table is no longer a host-controlled allowlist.

Do not simply blacklist a few sensitive class names or check that a name falls under the `com.mycompany.plugins` prefix. An untrusted JAR can declare classes in that same package itself. The bytecode source, implementation registration privileges, and operation selection permissions must all be controlled.

In addition to an allowlist, AuthN/AuthZ is still required: users must only be allowed to execute operations permitted by their role/tenant/scope.

## 4. Selecting Documents via Key, Not Accepting Raw Paths

A document endpoint should accept `"guide"` or `"rules"` instead of `"docs/guide.txt"` or `"../../config/secret.txt"` from the client.

~~~java
// Illustrative code.
Map<String, String> documents = Map.of(
        "guide", "docs/guide.txt",
        "rules", "docs/rules.txt"
);
String allowedPath = documents.get(documentKey);
if (allowedPath == null) {
    throw new IllegalArgumentException("Unknown document");
}
~~~

The physical path resides in a config/registry that only the host has permission to modify. If the document contains tenant-specific data, you must also verify that the document ID belongs to the authenticated tenant. **Do not accept a tenant ID from a query string without checking permissions**.

Even when the path comes from an allowlist, reading should still enforce controls on root, symlinks, file type, size, and resource lifecycle, especially when multiple parties can modify the filesystem.

## 5. Complete Java 17+ Program: Safe Factory and Resource Handling

The following standalone example creates two jobs and two files in a temporary directory, checks invalid tokens, and rejects path traversal. The program does not use a class name received from a client to load bytecode.

Create the file **`SafeSelectionDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.InvalidPathException;
import java.nio.file.Path;
import java.util.Map;
import java.util.function.Supplier;

public final class SafeSelectionDemo {
    private SafeSelectionDemo() {
    }

    interface Job {
        String run();
    }

    static final class HealthJob implements Job {
        @Override
        public String run() {
            return "HEALTH_OK";
        }
    }

    static final class VersionJob implements Job {
        @Override
        public String run() {
            return "VERSION_1";
        }
    }

    private static final Map<String, Supplier<Job>> JOBS = Map.of(
            "health", HealthJob::new,
            "version", VersionJob::new
    );

    private static final Map<String, String> DOCS = Map.of(
            "guide", "docs/guide.txt",
            "rules", "docs/rules.txt"
    );

    static Job selectJob(String key) {
        Supplier<Job> factory = JOBS.get(key);
        if (factory == null) {
            throw new IllegalArgumentException("Unknown job");
        }
        return factory.get();
    }

    static String selectDocument(Path root, String key)
            throws IOException {
        String relative = DOCS.get(key);
        if (relative == null) {
            throw new IllegalArgumentException("Unknown document");
        }
        return readConfinedFile(root, relative);
    }

    // Defense in depth; does not fully prevent filesystem races.
    static String readConfinedFile(Path root, String input)
            throws IOException {
        if (input == null || input.isBlank()) {
            throw new SecurityException("Empty path");
        }

        final Path relative;
        try {
            relative = Path.of(input);
        } catch (InvalidPathException ex) {
            throw new SecurityException("Invalid path", ex);
        }

        if (relative.isAbsolute()) {
            throw new SecurityException("Absolute path denied");
        }

        Path base = root.toRealPath();
        Path candidate = base.resolve(relative).normalize();

        if (!candidate.startsWith(base)) {
            throw new SecurityException("Path escapes root");
        }

        Path step = base;
        for (Path part : base.relativize(candidate)) {
            step = step.resolve(part);
            if (Files.isSymbolicLink(step)) {
                throw new SecurityException("Symlink denied");
            }
        }

        Path real = candidate.toRealPath();
        if (!real.startsWith(base) || !Files.isRegularFile(real)) {
            throw new SecurityException("Not a confined regular file");
        }

        return Files.readString(real, StandardCharsets.UTF_8).strip();
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("safe-selection-");
        Path docs = root.resolve("docs");
        Path guide = docs.resolve("guide.txt");
        Path rules = docs.resolve("rules.txt");

        try {
            Files.createDirectories(docs);
            Files.writeString(guide, "GUIDE_OK\n",
                    StandardCharsets.UTF_8);
            Files.writeString(rules, "RULES_OK\n",
                    StandardCharsets.UTF_8);

            System.out.println("job health: "
                    + selectJob("health").run());
            System.out.println("job version: "
                    + selectJob("version").run());

            boolean classDenied = false;
            try {
                selectJob("java.lang.Runtime");
            } catch (IllegalArgumentException expected) {
                classDenied = true;
            }
            System.out.println("arbitrary class rejected: "
                    + classDenied);

            System.out.println("document guide: "
                    + selectDocument(root, "guide"));
            System.out.println("document rules: "
                    + selectDocument(root, "rules"));

            boolean documentDenied = false;
            try {
                selectDocument(root, "../secret");
            } catch (IllegalArgumentException expected) {
                documentDenied = true;
            }
            System.out.println("unknown document rejected: "
                    + documentDenied);

            boolean traversalDenied = false;
            try {
                readConfinedFile(root, "../private.txt");
            } catch (SecurityException expected) {
                traversalDenied = true;
            }
            System.out.println("path traversal rejected: "
                    + traversalDenied);
        } finally {
            Files.deleteIfExists(guide);
            Files.deleteIfExists(rules);
            Files.deleteIfExists(docs);
            Files.deleteIfExists(root);
        }
    }
}
~~~

### Compile and Run

Use **JDK 17 or later**; open a terminal in the directory containing the file:

~~~bash
javac -encoding UTF-8 SafeSelectionDemo.java
java SafeSelectionDemo
~~~

Both commands run on Bash, PowerShell, and Command Prompt when the JDK is in `PATH`. No external libraries are required.

**Stdout:**

~~~text
job health: HEALTH_OK
job version: VERSION_1
arbitrary class rejected: true
document guide: GUIDE_OK
document rules: RULES_OK
unknown document rejected: true
path traversal rejected: true
~~~

**Explanation:** The two factories are selected by key; `"java.lang.Runtime"` is rejected as an invalid key rather than passed into reflection. Similarly, `"../secret"` is not in the document list; the direct test call `readConfinedFile(root, "../private.txt")` detects that the candidate escapes the root after normalization and rejects it. The program creates and deletes test data in a temporary directory and does not print machine-dependent paths.

The example intentionally **does not** accept real input from the network; it reproduces values a caller could send to verify behavior. The path-checking method illustrates **an additional layer of defense**, not an atomic solution against concurrent filesystem manipulation.

## 6. Why Is normalize + startsWith Not Enough?

A commonly seen check:

~~~java
// Illustration: root and relative are already configured.
Path base = root.toAbsolutePath().normalize();
Path file = base.resolve(relative).normalize();

if (!file.startsWith(base)) {
    throw new SecurityException("Outside resource root");
}
~~~

It helps reject paths containing `../` that escape the root after normalization, but it does not solve every scenario:

- **Symlink:** `base/docs/link` can point to a file/directory outside the root; the syntactic path can still start with `base`.
- **TOCTOU:** Between the `Files.isSymbolicLink`/`toRealPath` check and `Files.readString`, the entry on the filesystem can be swapped.
- **Filesystem aliases:** Hard links, mount points, Windows drive/UNC paths, and case sensitivity can affect how the root is interpreted.
- **Attacker-writable root:** If an adversary controls the directory tree, they can replace names/entries even after validation completes.

The demo calls `toRealPath()`, rejects symlinks in components under the root, and re-checks the real path. This is **defense in depth**, not a strong guarantee against TOCTOU.

For production, it is best **not to let an untrusted caller control the filesystem root**. If you need race protection in a mutable directory, consider `SecureDirectoryStream` when supported by the filesystem provider, or OS file descriptor/directory handle mechanisms. Process/container isolation can also be applied with read/write permissions restricted strictly to the granted directory.

## 7. Path Forms to Recognize

| Input | Problem |
|---|---|
| `../secrets/data.txt` | Parent traversal |
| `/etc/passwd` | Unix absolute path |
| `C:\Windows\...` | Windows drive path |
| `\\server\share\...` | UNC network path |
| `docs/link/private.txt` | Symlink that may escape the root |
| `%2e%2e%2fsecret` | Encoded traversal if decoded by the protocol |
| `..%252fsecret` | Double decoding across layers |
| `../../target.txt` in ZIP | Zip Slip during extraction |

Do not try to fix this by simply blacklisting strings like `..`, `%2e`, or `/`: decoding behavior, separators, and Unicode normalization can vary across layers. Decode at the proper protocol boundary, validate **the actual value passed to the filesystem**, and prefer accepting only a business ID instead of a path.

If extracting externally supplied JAR/ZIP archives, validate every destination against the root and handle symlinks/overwrites properly before writing files. Do not concatenate `entry.getName()` directly with the target directory without validation.

## 8. ClassLoader Resource Visibility Is Not User Authorization

`ClassLoader.getResource(name)` finds a URL; `getResourceAsStream(name)` opens a stream; `getResources(name)` can list multiple resources with the same name. These are **lookup APIs**, not authorization mechanisms for end users.

~~~java
// Illustration: requires InputStream and a valid loader variable.
try (InputStream input =
             loader.getResourceAsStream("internal/settings.json")) {
    // Having a stream does not mean its contents may be returned to every HTTP caller.
}
~~~

A loader may have visibility to an internal resource while the client **is not authorized** to view it. If you pass the input `"internal/settings.json"` directly from a request into `getResourceAsStream` and return the bytes, you can create a data exposure path.

Also keep in mind:

- `ClassLoader.getResource("pkg/name.txt")` typically takes a path from the root, without a leading slash.
- `SomeClass.class.getResource("name.txt")` resolves the name relative to the class's package, whereas `"/pkg/name.txt"` is root-relative.
- Parent-first resource lookup can return the parent's resource when there is a name collision with the child; named modules also enforce encapsulation/`opens`.
- The fact that a loader can find a file inside a JAR **does not** prove the user is permitted to access it, even if the filename is hard to guess.

**Safe approach:** Specify resources from a trusted map/config by **ID and permissions**; avoid letting the caller select any resource visible to the loader.

## 9. Do Not Accept Plugin JAR URLs from Requests

Anti-pattern:

~~~java
// UNSAFE: input is allowed to determine the code source and class.
URL artifact = new URL(requestUrl);
try (URLClassLoader child = new URLClassLoader(
        new URL[] {artifact},
        ClassLoader.getSystemClassLoader())) {
    Object plugin = child.loadClass(requestClassName)
            .getConstructor().newInstance();
}
~~~

This is an illustrative snippet, not a standalone runnable program. If `requestUrl`/`requestClassName` comes from an untrusted source, the host can load and execute bytecode outside the application's policy.

A better authorization chain:

~~~text
pluginId from client
      |
      v
AuthN / AuthZ and tenant policy
      |
      v
Host-managed trusted registry
      |
      v
Approved artifact ID + version + content digest
      |
      v
Verify source/signature/checksum against trust policy
      |
      v
Load loader from approved artifact
      |
      v
Provider implements host's shared API
~~~

Do not treat a “signed JAR” as proof that the code cannot harm the system. Signatures help verify origin/integrity under a trust policy, while code review, runtime permissions, update policy, and isolation remain separate concerns.

## 10. Class.forName Can Initialize Classes

With the overload:

~~~java
// Illustrative code; typeName has already been selected from a trusted registry.
Class<?> type = Class.forName(typeName);
~~~

Java requires initialization of the class (if not yet initialized). Static initializers and static field initializers can execute **even before an explicit constructor call**.

~~~java
// Illustrative code, not the main demo class.
public final class SampleComponent {
    static {
        System.out.println("Static initializer runs");
    }

    public SampleComponent() {
        System.out.println("Constructor runs");
    }
}
~~~

The overload `Class.forName(name, false, loader)` does not require immediate initialization, but **it is not authorization**: the caller still chooses which class is loaded, and subsequent instantiation/calls can still execute code.

Do not rely on an approach like “only allow class names starting with `demo.trusted.`”. An untrusted JAR author can create a class with that name themselves. **Source artifact and deployment permissions** matter more than a package prefix.

## 11. ServiceLoader and Discovery Also Require Trusted Sources

`ServiceLoader.load(Service.class, trustedLoader)` discovers providers via a service descriptor, such as `META-INF/services/demo.api.Service`. If an attacker can replace the JAR/descriptor, they can cause the framework to discover a different provider class.

`ServiceLoader` checks provider/service type rules, but **does not evaluate the security intent of the implementation**. Therefore, you must protect permissions to install plugins, modify artifacts, alter the service registry, and configure loaders. Simply switching the TCCL to an untrusted loader can also cause any TCCL-based API to discover providers from the wrong source.

Shared interfaces/DTOs should be defined by the host/parent loader to avoid two incompatible copies of API class identity. Do not let user-supplied metadata choose the defining loader or URL of a service provider.

## 12. A ClassLoader Is Not a Sandbox

A ClassLoader manages **loading, namespaces, delegation, class identity, and resource lookup**. By default, it does not prevent a plugin from calling filesystem/network APIs with the JVM process's permissions, does not limit CPU/memory, and does not undo all effects of already-executed code when `URLClassLoader.close()` is called.

- Parent-first delegation is not equivalent to “a less-privileged plugin”.
- JPMS `exports`/`opens` primarily serve encapsulation and reflective access, and do not replace OS isolation.
- In Java 17, `SecurityManager` is **deprecated for removal**; you should not assume a security manager automatically protects plugins in a modern JVM.
- For genuinely untrusted code, you need **process/container isolation**, filesystem/network permission restrictions, resource quotas, and communication over authenticated APIs/IPC.

A class/path allowlist is a necessary defensive layer, but **it cannot make arbitrary bytecode safe** if you attempt to execute it with host privileges.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| `Class.forName(userInput)` | User chooses which class is requested to initialize | Token → trusted factory |
| Only checking FQCN regex or package prefix | A valid name does not prove authorization or code provenance | Trusted registry + artifact policy |
| Calling `Path.of(userInput)` and reading immediately | Absolute path, traversal, symlink | Document ID + root/OS permission |
| Relying only on `normalize().startsWith(root)` | Does not prevent symlinks/TOCTOU | Root ownership, directory-handle/isolation |
| Accepting arbitrary `getResourceAsStream(name)` | May expose internal resources | Allowed resource names + AuthZ |
| Letting the client supply a plugin URL | May load untrusted bytecode | Approved artifact registry + version pin |
| Treating `ServiceLoader` as a trust validator | A type-valid provider can still be malicious | Verify source and deployment permissions |
| Treating a loader as a sandbox | Plugin code runs with process privileges | Isolate when bytecode is untrusted |
| Returning stack traces/paths to the client | Leaks filesystem/module information | Generic error codes, internal logging |
| Falling back to a broader lookup when validation fails | Fail-open, breaks policy | Reject and log the error |
| Allowing users to edit the key→class map | Users bypass the allowlist | Configuration editable only by trusted parties |

## 14. Checklist for Protecting the ClassLoader Boundary

1. **Data source:** Who can modify the class name/path/plugin URL?
2. **AuthZ:** Is the caller/tenant authorized to invoke the operation, view the document, or install the plugin?
3. **Registry:** Is the ID → class/resource/artifact map controlled by a trusted party?
4. **Class loading:** Is an FQCN from a request passed directly into `Class.forName`/`loadClass` anywhere?
5. **Artifact:** Is the JAR pinned by version/content digest and provenance?
6. **Resource:** Can a key be used instead of a raw path/resource name?
7. **Filesystem:** Is the root writable by an attacker; are absolute paths/traversal/symlinks/races handled?
8. **Module:** Is module encapsulation checked while still maintaining separate authorization?
9. **Lifecycle:** Are streams, threads, TCCL, listeners, and loaders cleaned up properly?
10. **Isolation:** Is a separate process/container needed when bytecode is untrusted?
11. **Observability:** Are rejected attempts logged sufficiently without leaking secrets?
12. **Tests:** Have you tested `../`, absolute paths, symlinks, unknown keys, and unapproved artifacts?

## 15. Self-Check

**Question 1.** A regex confirms that `"java.lang.Runtime"` is a syntactically valid class name. Can it be passed directly from a request into `Class.forName`?

**Answer:** No. Syntactic validity does not grant permission to choose an implementation; use a token allowlist and check authorization.

**Question 2.** Why does `Class.forName(name, false, loader)` not make arbitrary class names safe?

**Answer:** It only avoids requiring immediate initialization; class loading/selection is still determined by the input, and code can still execute during subsequent usage steps.

**Question 3.** Does `normalize().startsWith(root)` prevent every path escape?

**Answer:** No. Symlinks and race conditions between check and open are critical limitations; root ownership and filesystem/OS support are also required.

**Question 4.** Does the loader finding `internal/secret.json` mean an HTTP user is allowed to view that file?

**Answer:** No. Loader visibility is different from user authorization.

**Question 5.** Why should you accept `"guide"` instead of `"docs/guide.txt"`?

**Answer:** The host chooses the path itself from an approved list of documents, rather than letting the client dictate the path.

**Question 6.** Is a plugin JAR loaded via `URLClassLoader` automatically restricted in network/file permissions?

**Answer:** No. A ClassLoader is not a sandbox; untrusted code requires process/container/OS isolation.

**Question 7.** Is sharing the package prefix `com.trusted.plugins` sufficient to verify that a class is safe?

**Answer:** No. Package names are self-declared by the bytecode author; you must control the source artifact and deployment permissions.

## 16. Official Documentation

- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `getResource`, and resource lookup.
- [Java SE 17 — Class.forName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#forName(java.lang.String)): initialization in the default overload.
- [Java SE 17 — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): `resolve`, `normalize`, `startsWith`, `toRealPath`.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `readString`, `isSymbolicLink`.
- [Java SE 17 — SecureDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): relative directory operations.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): URLs and loader lifecycle.
- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): provider discovery.
- [JEP 411 — Deprecate the Security Manager for Removal](https://openjdk.org/jeps/411): SecurityManager changes in Java 17.

**Remember:** **Never let untrusted data directly choose a class name, resource/file path, or plugin source URL.** Use a **business key + authorization + host-owned allowlist**; control filesystem traversal, symlinks/TOCTOU, and OS permissions when file access is needed. A ClassLoader organizes class loading, **not a security boundary for arbitrary code**.
