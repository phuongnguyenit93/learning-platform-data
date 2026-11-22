# SecureClassLoader and the Historical Role of Permissions

> **Java Core → ClassLoader → Packages and Code Sources.** `java.security.SecureClassLoader` extends `ClassLoader` to associate a `CodeSource` and `ProtectionDomain` with a defined class, while also providing the `getPermissions(CodeSource)` hook. It originated in the Java security model that included `SecurityManager` and policy files. **Starting in JDK 24, the Security Manager is permanently disabled:** keeping `SecureClassLoader` does not turn a plugin into sandboxed code. This lesson distinguishes between still-useful APIs, historical permission mechanisms, actual runtime behavior, and protection strategies suited to the modern JVM.

## 1. Accurate Summary Before Writing Code

Three statements must be kept separate:

1. **`SecureClassLoader` is a real `ClassLoader`.** It can read class-file bytes, define classes at runtime, delegate to its parent, maintain class namespaces, and attach `CodeSource`/`ProtectionDomain` as specified by the API.
2. **`PermissionCollection` is metadata/mechanism from the legacy model.** Previously, when a `SecurityManager` was enabled, permission checks could rely on `ProtectionDomain` in the access-control context. `getPermissions(CodeSource)` allowed a subclass to contribute permissions for a newly defined class.
3. **In JDK 24+, there is no Security Manager to enforce that policy-based sandbox model.** Returning an empty permission set from `getPermissions` **no longer prevents** a class from reading files, environment properties, or opening network connections via `SecurityManager`. Resource control by the OS/container or specialized APIs is a separate matter.

To keep in mind:

```text
SecureClassLoader
  = ClassLoader + CodeSource / ProtectionDomain / permissions metadata support

SecureClassLoader != "untrusted-code sandbox" on modern Java

Class identity: (binary name, defining loader)
Source metadata: CodeSource(location, certificates/signers)
Legacy authorization: SecurityManager + AccessController + Policy + Permissions
Modern JDK 24+: legacy authorization is essentially no longer active
```

`SecureClassLoader` **was not removed just because the Security Manager is gone**. It remains the public superclass of `URLClassLoader` and still provides the `defineClass` overloads that accept `CodeSource`. Even so, the word “Secure” in the class name should not be read as a safety guarantee.

## 2. Where Does SecureClassLoader Sit in the ClassLoader Hierarchy?

The basic inheritance hierarchy:

```text
java.lang.Object
  └── java.lang.ClassLoader
        └── java.security.SecureClassLoader
              └── java.net.URLClassLoader
```

A custom loader can extend either `ClassLoader` or `SecureClassLoader` directly:

- **Extending `ClassLoader`:** typically overrides `findClass` and calls `defineClass(String, byte[], int, int, ProtectionDomain)` when you want to attach a custom-built domain.
- **Extending `SecureClassLoader`:** adds the `defineClass(..., CodeSource)` overloads; its implementation builds an appropriate `ProtectionDomain` from `CodeSource` and the permission hook.
- **Using `URLClassLoader`:** if the primary sources are directory/JAR URLs, the standard class loader already handles most JAR class/resource lookup and code source construction. You do not necessarily need to rewrite `findClass` yourself.

Example of creating a subclass:

```java
import java.security.SecureClassLoader;

public final class MyLoader extends SecureClassLoader {
    public MyLoader(ClassLoader parent) {
        super(parent);
    }

    // Override findClass when you need to read bytes from a custom source.
}
```

This is a **compilable** class without a `main` method. It does not load classes from a new source until you actually implement `findClass` or configure a source lookup mechanism.

As with other loaders, calling `loadClass("demo.Task")` does not always make `MyLoader` the defining loader: parent-first delegation may return a class defined by the parent. Distinguish between **the loader requested to find the class** and **the loader that actually defines it**.

## 3. Core API of SecureClassLoader

The specialized methods:

```java
protected final Class<?> defineClass(
        String name,
        byte[] b, int off, int len,
        java.security.CodeSource cs);

protected final Class<?> defineClass(
        String name,
        java.nio.ByteBuffer b,
        java.security.CodeSource cs);

protected java.security.PermissionCollection getPermissions(
        java.security.CodeSource codesource);
```

These are **illustrative signatures**, not a standalone Java file you can copy and compile directly. They are `protected`, so they are normally called or overridden from an appropriate subclass.

Meaning of each element:

| Element | Role |
| --- | --- |
| `name` | Expected binary name, e.g., `demo.Task`, not `demo/Task.class`. |
| `b` | Valid JVM class-file bytes for a class/interface. Does not accept Java source code. |
| `off`, `len` | Valid slice of data in `byte[]`; `len` is the byte count, not the end index. |
| `ByteBuffer` | Byte input within the range defined by `position()/limit()` per the API. |
| `CodeSource cs` | Describes the code source of the class; may be `null`. |
| `getPermissions(cs)` | Hook that creates the `PermissionCollection` attached to the protection domain in the `CodeSource`-based `defineClass` path. |

If `cs` is non-`null`, the `SecureClassLoader#defineClass` overloads create a protection domain attached to the class. The `defineClass` methods are `final`: do not override them; instead, customize byte lookup in `findClass`, permission metadata in `getPermissions`, or loader configuration.

Do not confuse `ClassLoader.defineClass(..., ProtectionDomain)` with `SecureClassLoader.defineClass(..., CodeSource)`: the last parameter type is different. `SecureClassLoader` bridges from a code source to a domain, whereas `ClassLoader` lets you pass an already-prepared domain.

## 4. CodeSource: Describes the Code Source, Does Not Verify It

`java.security.CodeSource` represents information about a **location URL** and associated certificates/signers.

Creating a code source for bytes read from a directory:

```java
// Inside a method that imports java.nio.file.Path, java.net.URL,
// java.security.CodeSource, and java.security.cert.Certificate:
URL location = Path.of("plugin-classes")
        .toAbsolutePath().toUri().toURL();
CodeSource cs = new CodeSource(
        location, (java.security.cert.Certificate[]) null);
```

In a JAR loader, the location usually points to the actual archive source rather than arbitrarily to a `.class` entry. However:

- `new CodeSource(location, null)` only attaches **metadata that you supply**. It does not verify that the bytes were genuinely read from that URL.
- Location is not guaranteed to be non-`null` in every domain; do not write `pd.getCodeSource().getLocation()` without null checks in production code.
- `null` certificates mean **no certificate metadata was provided**; it does not mean “signed and verified JAR”.
- If the source is a signed JAR, signature verification must go through the appropriate JAR verification API and process, reading and checking entries properly; manually constructing a `CodeSource` does not replace that step.
- Two independent loaders can define a class with the same binary name and the same `CodeSource.location` and still produce **two distinct runtime types**. Type identity is determined by the binary name and the defining loader, not the source URL.

To inspect an actual class:

```java
Class<?> clazz = /* obtain from the loader to inspect */;
ClassLoader definingLoader = clazz.getClassLoader();
java.security.ProtectionDomain pd = clazz.getProtectionDomain();
java.security.CodeSource source =
        pd == null ? null : pd.getCodeSource();
java.net.URL url = source == null ? null : source.getLocation();
```

This is a snippet assuming `clazz` is already provided; the placeholder comment only describes the required variable and is not a runnable program. `url` helps inspect source metadata, but it is neither cryptographic attestation nor sole proof of the class-loading path.

## 5. ProtectionDomain: From CodeSource to Historical Permission Context

`ProtectionDomain` associates domain metadata with a class. Previously, domains on the call stack and the access-control context played a role in access decisions when `SecurityManager` checked permissions.

The classic model:

```text
class bytes -> SecureClassLoader.defineClass(..., CodeSource)
                       |
                       v
           getPermissions(CodeSource)
                       |
                       v
           ProtectionDomain(CodeSource,
                            PermissionCollection,
                            ClassLoader, ...)
                       |
                       v
                    Class<?>
                       |
                       v
          Legacy SecurityManager permission checks
                       |
                       +--> grant/deny by domain/context/policy
```

This is a historical diagram, **not an active sandbox mechanism on JDK 24+**.

Commonly useful getters:

```java
ProtectionDomain pd = clazz.getProtectionDomain();
CodeSource cs = pd.getCodeSource();
PermissionCollection permissions = pd.getPermissions();
```

Proper `java.security.*` imports or fully qualified names are needed; this is a snippet where `clazz` must already exist. `getPermissions()` may return `null` depending on how the class was defined. An empty `PermissionCollection` simply means no static permissions are listed; it **does not prove** that an I/O operation will be denied on a modern JVM.

### Legacy Permission Types

Common historical `Permission` types:

| Permission | Legacy Purpose |
| --- | --- |
| `java.io.FilePermission` | Permission to read/write/delete files by path. |
| `java.net.SocketPermission` | Permission to connect/listen/resolve by host/port. |
| `java.util.PropertyPermission` | Permission to read/write system properties. |
| `java.lang.RuntimePermission` | Permission for specific JVM operations. |
| `java.security.AllPermission` | Grants all permissions in the Security Manager model; especially dangerous if granted by mistake in a policy. |

When the Security Manager was enabled, matching permission checks could throw `AccessControlException`. When it is not enabled, many operations do not consult this kind of permission policy. Starting in JDK 24, **it is no longer possible to re-enable** the Security Manager to rely on them.

### getPermissions Is Not an Arbitrary Access Rule for All APIs

`SecureClassLoader#getPermissions(CodeSource)` is a hook that returns permissions attached when creating the protection domain. It does **not** automatically block `Files.readString`, `System.getProperty`, or `Socket.connect` by throwing or returning an empty permission set in a JVM without a Security Manager. If you want to enforce access control at the business layer, you must place checks at **the API/service boundaries you own** or use OS/process isolation. Internal checks alone do not prevent arbitrary Java code in the same process from calling other JDK libraries directly.

## 6. History of SecurityManager, Policy, and AccessController

### Before Removal from the Execution Path

Java once had an in-process security model based on permission checks:

1. A class was defined by a loader together with a `ProtectionDomain`.
2. `CodeSource` described the code location and certificate metadata.
3. `java.security.Policy` could grant permissions by source/signers.
4. `SecurityManager`, when enabled, along with check points in platform APIs, consulted permissions.
5. `AccessController.checkPermission(...)`/`doPrivileged(...)` participated in stack-based access control.

Example policy file **for recognizing legacy applications only**:

```text
grant codeBase "file:/opt/legacy/plugins/-" {
    permission java.util.PropertyPermission "app.config", "read";
    permission java.io.FilePermission "/opt/legacy/plugins/-", "read";
};
```

This is not a configuration to use for protecting plugins on a modern JDK. `-Djava.security.policy` no longer provides its former security enforcement in JDK 24+.

`AccessController.doPrivileged` was used to execute an action within a defined scope with specific stack-inspection semantics. It should **not** be understood simply as “enabling admin mode” or “giving a code block unlimited permissions” in every case. Previously, the outcome also depended on policy, protection domains, and calling context.

### Timeline to Remember

| Java Version | Status |
| --- | --- |
| Java 1.2 onward | Security architecture with `ProtectionDomain`, `CodeSource`, `SecureClassLoader`, `Policy`, and `SecurityManager`. |
| Java 8 and earlier versions | Many applets/Web Start/containers used permission grants and security policy checks; this did not mean every app enabled Security Manager. |
| Java 17 | **JEP 411** deprecated the Security Manager **for removal**; compatibility remained, but developers were advised to migrate. |
| Java 17–23 | Legacy options to enable/use Security Manager remained with release-specific restrictions/warnings. |
| **JDK 24 and later** | **JEP 486** **permanently disabled** the Security Manager; it can no longer be installed or activated in the legacy way. Related APIs remain for a transition period with restricted/changed behavior. |

This lesson covers the **historical role** in the literal sense: understanding why the APIs were designed that way, while not applying a disabled security model to a JVM running JDK 24+.

## 7. What Changed When the Security Manager Was Disabled in JDK 24?

According to Oracle's official documentation and **JEP 486**:

- The Security Manager cannot be enabled with `-Djava.security.manager=...` at startup: the JVM reports an error.
- `System.setSecurityManager(...)` throws `UnsupportedOperationException`; `System.getSecurityManager()` always returns `null`.
- `AccessController.doPrivileged(...)` executes the action directly with no-Security-Manager semantics; it no longer establishes a call-stack privilege boundary.
- `AccessController.checkPermission(...)` **always throws `AccessControlException`** in JDK 24+, so do not use it as a “check whether permission is granted” test in modern applications.
- `Policy.getPolicy()` returns a policy that grants no permissions; policy-setting methods and related APIs have restricted behavior. Settings from `java.policy` are no longer an enforcement mechanism.
- `ProtectionDomain` continues to exist as an object and hold metadata, but **legacy permission policies are not used to restrict a class's file/network access**.
- Platform APIs that previously threw `SecurityException` only when the Security Manager blocked an operation generally no longer perform that check.

Two seemingly opposite phenomena must be distinguished:

1. **A resource is accessed even though the collection lists no permission:** on JDK 24+, this is not a contradiction because permission enforcement has ceased.
2. **A direct call to `AccessController.checkPermission` still throws:** that is specified compatibility behavior for the obsolete API, not proof that permission checks are actively protecting files or the network.

Do not rely on “`checkPermission` throws, so files are still safe”: code can call filesystem/network APIs directly without going through that check.

Relevant references: [Oracle — The Security Manager Is Permanently Disabled](https://docs.oracle.com/en/java/javase/24/security/security-manager-is-permanently-disabled.html) and [JEP 486](https://openjdk.org/jeps/486).

## 8. Hands-On Example: CodeSource + getPermissions Without Creating a Sandbox

The hands-on example below uses **Java 17+**, compiles the application and plugin into **two separate directories**, and loads the bytecode via a `SecureClassLoader` subclass. The `getPermissions` hook returns an empty collection—meaning it **does not declare** `PropertyPermission("java.version","read")`—yet the plugin still calls `System.getProperty("java.version")` successfully when the JVM has no Security Manager enabled.

**Important regarding conditions:** the output was verified on **OpenJDK 21 without Security Manager enabled**. On JDK 24+, the Security Manager is always disabled, so the absence of a permission sandbox is also confirmed by the specification/JEP 486; do not extrapolate this result to an older JVM running with Security Manager enabled.

### Directory Structure

```text
src/
  plugin/
    sandboxdemo/
      Worker.java
  app/
    SecureLoaderDemo.java
plugin-classes/     (generated by javac)
app-classes/        (generated by javac)
```

**File `src/plugin/sandboxdemo/Worker.java`:**

```java
package sandboxdemo;

public class Worker {
    public String message() {
        return "plugin-ok";
    }

    public boolean canReadVersion() {
        return System.getProperty("java.version") != null;
    }
}
```

**File `src/app/SecureLoaderDemo.java`:**

```java
import java.io.IOException;
import java.net.URL;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.CodeSource;
import java.security.PermissionCollection;
import java.security.Permissions;
import java.security.ProtectionDomain;
import java.security.SecureClassLoader;
import java.security.cert.Certificate;
import java.util.PropertyPermission;
import java.util.concurrent.atomic.AtomicInteger;

public class SecureLoaderDemo {
    static final class PluginLoader extends SecureClassLoader {
        private final Path root;
        private final URL sourceUrl;
        final AtomicInteger permissionCalls = new AtomicInteger();

        PluginLoader(Path root) throws IOException {
            super(ClassLoader.getPlatformClassLoader());
            this.root = root.toAbsolutePath();
            this.sourceUrl = this.root.toUri().toURL();
        }

        @Override
        protected PermissionCollection getPermissions(CodeSource cs) {
            permissionCalls.incrementAndGet();
            return new Permissions();
        }

        @Override
        protected Class<?> findClass(String binaryName)
                throws ClassNotFoundException {
            Path path = root.resolve(
                    binaryName.replace('.', '/') + ".class");
            try {
                byte[] data = Files.readAllBytes(path);
                CodeSource source = new CodeSource(
                        sourceUrl, (Certificate[]) null);
                return defineClass(
                        binaryName, data, 0, data.length, source);
            } catch (IOException e) {
                throw new ClassNotFoundException(binaryName, e);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        PluginLoader loader = new PluginLoader(
                Path.of("plugin-classes"));
        Class<?> c = Class.forName(
                "sandboxdemo.Worker", false, loader);
        ProtectionDomain pd = c.getProtectionDomain();
        Object plugin = c.getDeclaredConstructor().newInstance();

        System.out.println("defined by plugin loader: "
                + (c.getClassLoader() == loader));
        System.out.println("source URL matches: "
                + (pd.getCodeSource().getLocation().equals(
                        Path.of("plugin-classes")
                            .toAbsolutePath().toUri().toURL())));
        System.out.println("permissions callback invoked: "
                + (loader.permissionCalls.get() == 1));
        System.out.println("explicit property permission: "
                + pd.getPermissions().implies(
                        new PropertyPermission("java.version", "read")));
        System.out.println("class code runs: "
                + c.getMethod("message").invoke(plugin));
        System.out.println("property read at runtime: "
                + c.getMethod("canReadVersion").invoke(plugin));
        System.out.println("same class on repeat: "
                + (Class.forName("sandboxdemo.Worker", false, loader) == c));
    }
}
```

### Compiling and Running

From the root directory containing `src`:

```bash
javac --release 17 -d plugin-classes src/plugin/sandboxdemo/Worker.java
javac --release 17 -d app-classes src/app/SecureLoaderDemo.java
java -cp app-classes SecureLoaderDemo
```

Stdout **compiled, run, and verified** on OpenJDK 21 without Security Manager enabled:

```text
defined by plugin loader: true
source URL matches: true
permissions callback invoked: true
explicit property permission: false
class code runs: plugin-ok
property read at runtime: true
same class on repeat: true
```

### Explanation of Each Result

1. `plugin-classes` is not on `-cp app-classes`; the parent platform loader does not load `sandboxdemo.Worker` from that directory, so `PluginLoader` defines the class directly.
2. `CodeSource.location` is set from the exact directory where the demo reads the bytecode and enters the class's `ProtectionDomain`.
3. The `getPermissions(cs)` hook is invoked **once** when the domain is constructed to define the first class from that `CodeSource`. The count is an observed demo result, not a universal contract for every loader or call pattern.
4. `getPermissions()` returns an empty `Permissions` collection. `PermissionCollection.implies(PropertyPermission(...))` returns `false`, meaning the collection does not list that permission.
5. **The plugin still reads `java.version`** because the test JVM has no Security Manager enforcing legacy checks. This is the key illustration: an empty collection **does not automatically block** `System.getProperty` calls.
6. Calling `Class.forName` again with the same name and loader returns the exact same `Class<?>` without redefining it.
7. Reflection in the demo merely invokes methods on the class defined by the custom loader; it **does not** prove the class is isolated or verified as trustworthy.

**Do not use this pattern to run untrusted plugins in the same JVM.** On the contrary, the goal is to clearly illustrate the difference between permission metadata and actual enforcement.

## 9. Why Do CodeSource and Permissions Still Exist in the API?

There are three distinct needs:

**A. Legacy code compatibility.** Many loaders and frameworks were built when security policies and `SecurityManager` were part of the JVM. Removing the classes/APIs immediately would break binary compatibility. The JDK follows a roadmap of disabling them first and potentially removing parts of the API later.

**B. Source information and consistency checks.** `CodeSource` can still be read from `ProtectionDomain` for class diagnostics or metadata logic; certificate consistency rules within a runtime package still apply. However, source information supplied by a loader can be misconfigured, so actual provenance must be understood.

**C. Inheritance hierarchy.** `URLClassLoader` extends `SecureClassLoader`, and some custom loaders use `defineClass(..., CodeSource)`. Continuing to provide the overloads lets applications work with class files and source metadata without forcing them to construct `ProtectionDomain` from scratch.

Therefore, you should not say “`SecureClassLoader` is completely useless”; rather, **its historical permission-based sandbox role is no longer active on JDK 24+**, while class loading and source-domain metadata remain separate functions.

### getPermissions Does Not Decide Which Code Gets Loaded

`getPermissions` is called along the domain-construction path of `defineClass` that accepts `CodeSource`; it does not validate the class-file bytes themselves. If you want to restrict plugins at the management layer, you must check package allowlists, versions, verified signatures, actual sources, dependencies, and policies before calling `defineClass` or executing the plugin.

Class definition is still subject to JVM rules such as `ClassFormatError`, `NoClassDefFoundError` (wrong name), `SecurityException` for the `java.` namespace or inconsistent certificate sets, and `LinkageError` on duplicate class definition. **These remaining checks are not equivalent to a SecurityManager sandbox.**

## 10. Key Security Distinctions

### Sandboxing, Class Isolation, and Module Encapsulation Are Three Different Things

| Mechanism | What Does It Solve? | Does It Block All OS Permissions of a Plugin? |
| --- | --- | --- |
| Custom `ClassLoader` | Organizes class lookup paths, delegation, and runtime class identity. | No. |
| `SecureClassLoader` + `CodeSource` | Attaches source/domain metadata; permission checks formerly had meaning with Security Manager. | No on JDK 24+. |
| JPMS (`module-info.java`, `exports`, `opens`) | Readability, strong encapsulation, and reflective access within the module graph. | Not a file/network/process sandbox. |
| JAR signing | Enables integrity/origin verification against an appropriate trust chain. | Does not restrict the behavior of code once executed. |
| OS user permissions / container isolation | Restricts resources/processes at the OS level, with proper configuration. | Can create real boundaries, depending on configuration and threat model. |
| Separate process/service boundary | Isolates the plugin into another process, communicating via IPC with controlled access. | Provides clearer boundaries when combined with OS controls. |

A **validly signed** JAR can still contain dangerous logic or bugs; a signature does not turn it into restricted-privilege code. A class strongly encapsulated by the module system still runs inside the JVM process with the process's OS permissions unless external policies block them.

### Can You Use a Restricted Plugin API?

You can design a `PluginContext` that only exposes methods like `readPublicConfig()` or `publishEvent()` and checks caller permissions at the business layer. This is a good design for **trusted/vetted extensions**, but it is **not a full sandbox** if arbitrary plugin code can still call `Files`, `Socket`, reflection, or other APIs directly in the same process. To defend against malicious bytecode, stronger boundaries are required.

## 11. Designing Plugins on the Modern JVM: What Should You Choose?

If plugins are trusted but need dynamic loading:

1. Create a loader with an appropriate parent to share the host API (e.g., a `Plugin` interface residing in the parent).
2. Choose `URLClassLoader` for standard JARs/directories, or a `SecureClassLoader`/`ClassLoader` subclass when you genuinely need a custom bytecode source or source metadata.
3. Validate class-file bytes, binary names, and dependencies; manage namespaces and package sealing/certificates if the framework is responsible for them.
4. Scope loaders to the plugin lifecycle so they can be unloaded when no longer reachable; close `URLClassLoader` to release resources, but do not treat `close()` as an immediate unload command.
5. Record actual provenance when diagnostics are needed; do not treat `CodeSource` itself as trustworthy verification.

If plugins are **untrusted** or you want filesystem/network control:

1. Run the code in a **separate process** with a restricted OS user/privileges; consider containers, seccomp/App Sandbox, filesystem mounts, and network policies suited to the environment.
2. Design a clear IPC/API, authorize by operation, and validate data coming from the plugin.
3. Separate resource isolation from plugin authentication. Verify signatures/provenance through an appropriate trust mechanism.
4. Block unnecessary capabilities at the process/infrastructure level, not merely by passing an empty collection into `ProtectionDomain`.
5. Establish a clear threat model: “preventing a plugin from accidentally corrupting config” is different from “defending against malicious code actively trying to escape a sandbox”.

Do not promise that a default-configured container stops every kind of attack; actual isolation depends on OS permissions, mounts, networking, syscall policies, and platform updates.

## 12. Common Technical Pitfalls

| Misconception / Error | Why It Is Wrong | How to Handle It |
| --- | --- | --- |
| “The name `SecureClassLoader` means it is secure.” | It is a loader subclass with source/permissions support, not a modern security boundary. | Define your threat model and process/OS boundaries. |
| “I return `new Permissions()`, so the plugin cannot read files.” | There is no Security Manager enforcing that collection on JDK 24+. | Do not use `getPermissions` as a sandbox. |
| “`CodeSource` points to a valid URL, so the bytes are verified.” | The URL can be set arbitrarily by a custom loader. | Verify the actual read source, signatures/hashes/chain if needed. |
| “Security Manager can still be used with `-Djava.security.manager=allow`.” | JDK 24+ refuses to enable the Security Manager. | Migrate away from the legacy policy model. |
| “`AccessController.checkPermission` throws, so files/network are blocked too.” | In JDK 24+, this obsolete method always throws even though other operations still run. | Enforce permissions via appropriate OS/process APIs. |
| “Policy grants permissions from `java.policy` in JDK 24.” | The Security Manager policy mechanism is disabled. | Migrate configuration to real controls. |
| “`getProtectionDomain().getPermissions() == null` means a loader bug.” | A domain may have no static permissions depending on how the class was defined. | Check for `null`; do not infer enforcement. |
| “A plugin interface with the same name can be cast across two loaders.” | Matching binary names are not enough; different defining loaders create two runtime types. | Share the host API through the parent loader. |
| “Adding `CodeSource` after a class is defined updates its domain.” | The domain is bound when the class is defined; it is not an arbitrarily mutable property. | Decide metadata before `defineClass`. |
| “Closing a class loader immediately unloads all classes.” | Class unloading depends on reachable references/GC, not `close()`. | Manage lifecycle/caches/threads. |
| “`SecureClassLoader` automatically parses manifests and verifies signed JARs.” | Those responsibilities belong to the loader/JAR verification pipeline. | Use `URLClassLoader`/`JarFile` properly and check provenance. |
| “Module encapsulation is equivalent to blocking filesystem access.” | JPMS manages visibility of Java packages, not OS permissions per domain. | Enforce permissions at API/process/OS levels. |

## 13. How to Read Legacy Code Containing getPermissions or doPrivileged

When maintaining a legacy application, separate the questions:

- Where is `getPermissions(CodeSource)` overridden? Does it return a static collection, grant permissions by source, or call `super.getPermissions`?
- Which classes is the loader defining, which protection domains do they belong to, and which classes are simply delegated to the parent?
- Did the application enable Security Manager at startup or install it at runtime?
- Are there policy files/`java.security.policy` or assumptions about `AllPermission`, `FilePermission`, and `SocketPermission`?
- Are `AccessController.doPrivileged` blocks used to narrow privilege scope or to bypass checks on the call stack?
- Are there `AccessController.checkPermission`/`Policy.setPolicy` calls that need to be replaced with real controls before upgrading to JDK 24+?
- Are libraries **catching every `SecurityException` as if a resource were guaranteed to be forbidden**? Some of those exceptions can still come from other mechanisms; classify them by API and actual cause.
- Did previous safety rely on an applet/container blocking malicious code, or on unenforced domain metadata rules?

### Practical Migration Process

1. Identify the JDK version in use and whether `SecurityManager` is enabled in the legacy environment. In Java 17–23, exact policies and warnings depend on the release.
2. Locate usages of `SecurityManager`, `AccessController`, `Policy`, `Permission` (especially direct calls), and Java launcher options.
3. Write tests describing the security boundaries **actually required**: which directories must not be read, which networks must not be called, which configs must not be overwritten.
4. Choose testable replacements: process/OS sandboxes, network namespaces, container profiles, IPC controls, server-side authz.
5. Evaluate whether source metadata should be kept for auditing/debugging; you can continue using `CodeSource`, but do not treat it as an authorization gate.
6. Run tests on JDK 24+; do not expect startup with `-Djava.security.manager` or `AccessController.checkPermission` checks to work with legacy semantics.
7. If a third-party library depends too heavily on the Security Manager, plan to replace it or upgrade to a compatible version; do not silently downgrade security by ignoring errors.

On Java 17–23 when auditing legacy source, `jdeprscan` can help locate deprecated APIs in class files, but it does not replace runtime/policy configuration analysis. Static scanning results alone do not confirm that enforcement previously worked as intended.

## 14. Knowledge Check

1. **Where does `SecureClassLoader` primarily differ from `ClassLoader`?**  
   It provides `defineClass` overloads accepting `CodeSource` and a `getPermissions` hook to build a protection domain in Java's API model.
2. **Starting in JDK 24, does setting an empty `FilePermission` automatically stop a plugin from calling `Files.readString`?**  
   No. The Security Manager is disabled, so a permission collection is no longer a filesystem sandbox.
3. **If a class has `CodeSource.location`, does that prove the bytes came from that URL?**  
   No; a custom loader can set inaccurate metadata. The actual source must be verified.
4. **Can `ProtectionDomain.getPermissions()` be `null`?**  
   Yes. This state should not be used to conclude whether the system is enforcing or denying operations.
5. **`getPermissions` returns `false` when checking `PropertyPermission`, yet `System.getProperty` still succeeds in the demo. Why?**  
   The demo does not have a Security Manager enabled. Permission metadata is not used by the runtime to deny the property call.
6. **Can JDK 24 enable the Security Manager with `-Djava.security.manager=allow`?**  
   No. The JVM rejects attempts to enable the disabled mechanism.
7. **Is `AccessController.checkPermission` on JDK 24+ worth using to check real access?**  
   No; it always throws an exception under the updated API behavior.
8. **How is `URLClassLoader` related to `SecureClassLoader`?**  
   `URLClassLoader` extends `SecureClassLoader`, but that does not turn `URLClassLoader` into a sandbox.
9. **Do two loaders that attach the same source URL and define `demo.Task` produce the same runtime type?**  
   No; the defining loader is part of type identity.
10. **What approach should you use to run truly untrusted bytecode?**  
    Prefer a process boundary and appropriate OS/container restrictions with controlled IPC, rather than relying only on class-loader permissions.
11. **Should you use `java.security.Policy` to manage plugin permissions on modern Java?**  
    Not in the way Security Manager used to; the policy mechanism is disabled in JDK 24+.
12. **What value does `SecureClassLoader` still have when the Security Manager is gone?**  
    Class loading and `CodeSource`/`ProtectionDomain` metadata, within the bounds of the API, can still be useful for compatibility and diagnostics.

## 15. Official References

- [Java SE 25 — SecureClassLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/SecureClassLoader.html): `defineClass` overloads, `getPermissions`; API Note confirms permissions are no longer used for access control because the Security Manager is not supported.
- [Java SE 21 — SecureClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureClassLoader.html): pre-JDK 24 version context.
- [Java SE 21 — CodeSource](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/CodeSource.html): source location/certificates.
- [Java SE 21 — ProtectionDomain](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/ProtectionDomain.html): domain metadata and static/dynamic permissions.
- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): class loading, defining loader, protection domain, class-file name checks.
- [JEP 411 — Deprecate the Security Manager for Removal](https://openjdk.org/jeps/411): Java 17 context.
- [JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486): decision to remove activation starting in JDK 24.
- [Oracle Java SE 24 — The Security Manager Is Permanently Disabled](https://docs.oracle.com/en/java/javase/24/security/security-manager-is-permanently-disabled.html): list of changes to `System`/`Policy`/`AccessController`/`ProtectionDomain` and migration guidance.
- [JVM Specification §5.3](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): runtime classes are identified by binary name and defining loader.
