# `ProtectionDomain` in `defineClass` Variants

> **Java Core → ClassLoader → Packages and Code Sources.** `ProtectionDomain` is metadata attached to a runtime class when a classloader defines the class from bytecode. It connects a **`CodeSource` (code location/certificates)**, a **`ClassLoader`**, **`Principal`**s, and the `PermissionCollection` information of the Java security architecture. This article accurately compares the `defineClass` overloads, shows how to pass an explicit domain or receive the default domain, explains certificate consistency rules within the same package, demonstrates how to use `SecureClassLoader`, and specifically distinguishes **code-source metadata** from an **actual sandbox** on modern JDK versions.

## 1. Short Answer: How Does `ProtectionDomain` Relate to `defineClass`?

A custom loader typically calls `defineClass` from `findClass` after obtaining the bytes:

~~~java
Class<?> type = defineClass(name, classBytes, 0, classBytes.length);
~~~

This call defines the class with a **default `ProtectionDomain`**. If you want to attach a programmatically provided domain, use the overload:

~~~java
Class<?> type = defineClass(
        name, classBytes, 0, classBytes.length, explicitDomain);
~~~

Both are **snippets inside a `ClassLoader` subclass**, not valid code to call from an arbitrary application class: `defineClass` is `protected final`. Another option is to use the `ByteBuffer` overload or the `SecureClassLoader` subclass, which accepts a `CodeSource`.

**Key takeaways:**

- `defineClass` creates a **runtime `Class<?>`** from bytecode; `ProtectionDomain` is the domain **attached to the defined class**.
- `CodeSource` in the domain describes the **location and signer/certificate information** provided through a verified loading process; it **does not guarantee** that the class file was actually read from that URL.
- If `null` is passed for `ProtectionDomain`, the VM/JDK uses the **default domain** according to the `ClassLoader` contract.
- From JDK 24 onward, **the Security Manager is permanently disabled**. Attaching a `ProtectionDomain` or granting `Permission`s does not turn a plugin into a sandbox capable of restricting resource access. However, `CodeSource` metadata, certain package name/certificate checks, and class-definition rules still apply.

### Overloads to Remember

| API in subclass | Attached domain | Notes |
| --- | --- | --- |
| `defineClass(byte[] b, int off, int len)` | No domain argument; default mechanism | **Deprecated** since Java 1.1; does not take a binary name, should not be used |
| `defineClass(String name, byte[] b, int off, int len)` | **Default domain** | Standard recommendation when there is no custom source metadata |
| `defineClass(String name, byte[] b, int off, int len, ProtectionDomain pd)` | `pd` if non-null; otherwise default | Checks package certificates, name, and class-file bytes |
| `defineClass(String name, ByteBuffer b, ProtectionDomain pd)` | `pd` or default | Equivalent in semantics, defining a class from the buffer's remaining bytes |
| `SecureClassLoader.defineClass(String name, byte[] b, int off, int len, CodeSource cs)` | Creates a `ProtectionDomain` from `cs` when `cs != null` | Convenience API of `SecureClassLoader` |
| `SecureClassLoader.defineClass(String name, ByteBuffer b, CodeSource cs)` | Same as the byte-array overload | Uses `CodeSource` directly without passing a `ProtectionDomain` |

**Caution:** Java also has specialized APIs such as `MethodHandles.Lookup.defineClass` and `Lookup.defineHiddenClass`. They have their own lookup/loader/package/hidden-class semantics and are **not overloads of `ClassLoader.defineClass`** explained here.

## 2. Data Structure: What Does `ProtectionDomain` Contain?

Main components:

~~~text
Class<?> runtimeType
       |
       v
ProtectionDomain
       +-- CodeSource
       |      +-- URL/location (may be null)
       |      +-- Certificates / CodeSigners (may be null)
       +-- PermissionCollection (metadata/legacy policy)
       +-- ClassLoader (may be null)
       +-- Principal[] (often empty)
~~~

Commonly used APIs:

~~~java
ProtectionDomain domain = SomeClass.class.getProtectionDomain();
CodeSource source = domain.getCodeSource();
ClassLoader defining = SomeClass.class.getClassLoader();

if (source != null && source.getLocation() != null) {
    System.out.println(source.getLocation());
}
~~~

This is a **snippet** that requires importing `java.security.ProtectionDomain` and `java.security.CodeSource`. `getProtectionDomain()` returns the domain associated with the runtime class, but diagnostic code should not assume that every `Class` or every runtime image has a non-null `CodeSource`.

### 2.1. `CodeSource` Is Not a VM-Verified "Byte Source"

`new CodeSource(URL, Certificate[])` describes the URL and certificates passed to it. If you put `file:/example/plugins/a.jar` into `CodeSource` but define bytes read from elsewhere, `defineClass` alone **does not match the URL against the actual source** and does not verify an archive based on the URL name.

Therefore:

- The URL may simply be **metadata** decided by the custom loader.
- Do not use a hand-crafted `CodeSource` as proof of a valid digital signature.
- When using signed JARs, the loading code must actually **verify the JAR/signature** through proper reading/JAR verification before trusting the returned certificates.
- `CodeSource.getCertificates()` and `CodeSource.getCodeSigners()` reflect the information provided or converted per the API; `null` or empty does not automatically imply verified code.

**Important distinction:** `ProtectionDomain` is a property of a **runtime class**; `CodeSource` is only part of the domain's metadata. The same physical JAR can be defined by multiple loaders into different runtime types.

### 2.2. Two Main Constructor Styles of `ProtectionDomain`

~~~java
ProtectionDomain staticDomain =
        new ProtectionDomain(codeSource, permissions);

ProtectionDomain domainWithContext =
        new ProtectionDomain(
                codeSource, permissions, definingLoader, principals);
~~~

This is a **snippet requiring appropriate variables**. The two-argument form represents a domain with the given permissions; the four-argument form also stores the loader and principals, serving the contextual policy model of the former Security Manager. On JDK 24+, **these permissions cannot be turned into a file/network blocking boundary** merely by passing the domain to `defineClass`.

Do not infer from `domain.getPermissions() == null` that a class is "allowed everything," nor infer from `getPermissions()` containing a `FilePermission` that the process will be blocked from other operations by modern Java policy. You must consider the JDK version and the actual enforcement system.

## 3. The Default Domain: Omitting It or Passing `null`

The Javadoc of `ClassLoader.defineClass(String, byte[], int, int)` confirms that when no domain is specified, the class receives a **default `ProtectionDomain`**. The JDK creates the default domain when first needed and **reuses** it for subsequent calls using the default mechanism.

With the five-argument overload:

~~~java
defineClass(name, bytes, 0, bytes.length, null);
~~~

Passing `null` for `protectionDomain` means using the exact same **default domain**; it does not mean the class has no domain.

**Do not guess the internal structure of the default domain from a specific JDK.** On some runtimes, `getCodeSource()` may be a non-null object whose URL is `null`; on JDK 24+, `getPermissions()` on the default domain is `null` according to the JDK documentation. Therefore, diagnostic code should check separately:

~~~java
CodeSource cs = clazz.getProtectionDomain().getCodeSource();
boolean hasSourceLocation =
        cs != null && cs.getLocation() != null;
~~~

This snippet requires a valid `clazz` variable. `hasSourceLocation == false` does not mean the Java class file was never read; it only means the domain does not carry a code-source URL in the inspected field.

### 3.1. Why Shouldn't You Overuse the Default Domain?

When loading a large number of plugins/dependencies from many places, letting all of them receive the default domain leaves metadata without any indication of which artifact they came from. If you need real audit/provenance, you can attach a verified `CodeSource`, but this must be accompanied by **byte-source verification**, versioning, logging, and loader management.

The default domain is sufficient for many internal loaders that do not use legacy permissions, as long as you do not rely on it in place of identity, path, or trust-source checks.

## 4. The Overload Accepting an Explicit `ProtectionDomain`

Standard signature:

~~~java
protected final Class<?> defineClass(
    String name, byte[] b, int off, int len,
    ProtectionDomain protectionDomain);
~~~

Characteristics:

1. **`name`** is the binary name, such as `org.example.Plugin` — not the path `org/example/Plugin.class`. The API allows `null`, but **you should pass a concrete name**.
2. **`b, off, len`** bound the byte region containing a valid class file. Incorrect offset/length can lead to `IndexOutOfBoundsException`.
3. **`protectionDomain`**, if non-null, is attached to the class; if `null`, the default domain is used.
4. When the bytes are not a valid class file, `ClassFormatError` (or a subtype/related error) may occur.
5. If `name` differs from the binary name declared in the bytes, the JVM may throw **`NoClassDefFoundError`**.
6. If the name starts with `java.` and the defining loader is not of a permitted kind per the API, **`SecurityException`** is thrown.
7. Within the same package of a loader, defined classes must have the **same set of signing certificates**, or **`SecurityException`** will be thrown.
8. Defining a duplicate binary name in the **same loader** is a separate issue that can throw **`LinkageError`**; supplying a different domain does not make it valid.

**Real security does not appear automatically:** this overload attaches domain metadata; it does not isolate plugin code from Java APIs or process-level access rights.

### 4.1. Which Check Does `name == null` Weaken?

The Javadoc states that the package certificate-set comparison step **is not performed in the same way when `name` is `null`**. For this reason, the legacy overload `defineClass(byte[], off, len)`, which takes no name, is deprecated and discouraged. Always supply a **trusted binary name** and verify that the bytecode matches that name.

Do not use `name = null` to "bypass JAR signing errors": that weakens consistency checks and creates design risks. If a package signer mismatch occurs, fix it with the proper artifacts/certificates and avoid mixing signed and unsigned classes in the same package of a loader.

## 5. Java 17+ Example: Attaching `ProtectionDomain`, Reading Metadata, Testing Default and `ByteBuffer`

The experiment has **two Java files**: a plugin class and a host loader. To prevent the parent loader from loading the plugin class first, **compile the plugin into a separate directory**, and when running, put only the host classes on the application classpath.

Directory structure:

~~~text
pd-lab/
├── plugin-src/
│   └── demo/plugin/Greeter.java
├── host-src/
│   └── ProtectionDomainDemo.java
└── build/
    ├── plugin/   (generated)
    └── host/     (generated)
~~~

File **`plugin-src/demo/plugin/Greeter.java`**:

~~~java
package demo.plugin;

public class Greeter {
    static {
        System.out.println("Greeter initialized");
    }

    public Greeter() { }
}
~~~

File **`host-src/ProtectionDomainDemo.java`**:

~~~java
import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.CodeSource;
import java.security.Permissions;
import java.security.Principal;
import java.security.ProtectionDomain;
import java.security.cert.Certificate;

public class ProtectionDomainDemo {
    static final class ByteLoader extends ClassLoader {
        ByteLoader() {
            super(ProtectionDomainDemo.class.getClassLoader());
        }

        Class<?> withDomain(
                String name, byte[] bytes, ProtectionDomain pd) {
            return defineClass(name, bytes, 0, bytes.length, pd);
        }

        Class<?> withDefault(String name, byte[] bytes) {
            return defineClass(name, bytes, 0, bytes.length);
        }

        Class<?> withBuffer(
                String name, ByteBuffer bytes, ProtectionDomain pd) {
            return defineClass(name, bytes, pd);
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(
                Path.of("build/plugin/demo/plugin/Greeter.class"));
        String name = "demo.plugin.Greeter";

        ByteLoader specific = new ByteLoader();

        // The URL below is metadata; the JAR file does NOT need to exist.
        CodeSource source = new CodeSource(
                Path.of("provenance/plugin-origin.jar").toUri().toURL(),
                (Certificate[]) null);

        Permissions permissions = new Permissions();
        permissions.add(new RuntimePermission("lesson.marker"));
        permissions.setReadOnly();

        ProtectionDomain domain = new ProtectionDomain(
                source, permissions, specific, new Principal[0]);

        Class<?> type = specific.withDomain(name, bytes, domain);
        ProtectionDomain actual = type.getProtectionDomain();

        System.out.println("custom loader="
                + (type.getClassLoader() == specific));
        System.out.println("source marker="
                + actual.getCodeSource().getLocation().getPath()
                    .endsWith("plugin-origin.jar"));
        System.out.println("domain loader="
                + (actual.getClassLoader() == specific));
        System.out.println("permission metadata="
                + actual.getPermissions().implies(
                    new RuntimePermission("lesson.marker")));

        System.out.println("defined, not initialized");
        type.getDeclaredConstructor().newInstance();
        System.out.println("instance created");

        ByteLoader defaultLoader = new ByteLoader();
        Class<?> defaultClass =
                defaultLoader.withDefault(name, bytes);
        CodeSource defaultSource =
                defaultClass.getProtectionDomain().getCodeSource();
        System.out.println("default source has location="
                + (defaultSource != null
                    && defaultSource.getLocation() != null));

        ByteLoader bufferLoader = new ByteLoader();
        ByteBuffer buffer = ByteBuffer.wrap(bytes);
        Class<?> fromBuffer =
                bufferLoader.withBuffer(name, buffer, null);
        System.out.println("buffer class=" + fromBuffer.getName());

        try {
            new ByteLoader().withDomain(
                    "demo.plugin.Other", bytes, domain);
            System.out.println("wrong name rejected=false");
        } catch (NoClassDefFoundError expected) {
            System.out.println("wrong name rejected=true");
        }
    }
}
~~~

From the `pd-lab` directory, with JDK 17+ (POSIX shell):

~~~bash
mkdir -p build/plugin build/host
javac --release 17 -d build/plugin \
    plugin-src/demo/plugin/Greeter.java
javac --release 17 -d build/host \
    host-src/ProtectionDomainDemo.java
java -cp build/host ProtectionDomainDemo
~~~

**Expected stdout on standard OpenJDK 21:**

~~~text
custom loader=true
source marker=true
domain loader=true
permission metadata=true
defined, not initialized
Greeter initialized
instance created
default source has location=false
buffer class=demo.plugin.Greeter
wrong name rejected=true
~~~

Explanation:

1. `withDomain` attaches an explicitly created domain to the class in loader `specific`. The class's `getClassLoader()` is that loader.
2. `CodeSource` has the URL passed by the program; the "source marker" line **only checks metadata** and does not prove that `plugin-origin.jar` exists or was verified.
3. `permission metadata=true` reflects that `PermissionCollection` holds a marker **we placed ourselves**, not an access right enforced by the OS or JDK 24+.
4. `defineClass` does not trigger the initializer, so `Greeter initialized` appears when invoking the constructor via reflection, **after** the `defined, not initialized` line.
5. `defaultLoader` uses the overload without a domain, so there is no explicitly declared source URL; the example checks **location** rather than assuming the entire `CodeSource` object is `null`.
6. `ByteBuffer` defines another copy of the class under a **new loader** with the default domain. Do not rely on the original buffer changing its `position()`/`limit()` after the call; if reuse is needed, use `duplicate()`/`slice()` and manage state explicitly.
7. The name `demo.plugin.Other` does not match the name `demo.plugin.Greeter` inside the class bytes, so the JVM rejects it with `NoClassDefFoundError`.

**Example limitation:** Each definition of the same binary name uses a **new `ByteLoader` instance**. If you try to redefine `demo.plugin.Greeter` inside `specific` itself, you will hit a duplicate-definition error. Do not add `build/plugin` to the host's `java -cp` if you want to preserve the loader-isolation experiment.

## 6. The `ByteBuffer` Overload: Same Domain Rules, Different Byte Form

Overload:

~~~java
protected final Class<?> defineClass(
    String name, ByteBuffer data, ProtectionDomain pd);
~~~

It consumes class bytes from the buffer according to its configured bounds/remaining bytes, applying the **same binary name, package signer, `java.*`, and domain rules** as the byte-array overload. You can use `ByteBuffer.wrap(bytes)` or a buffer obtained from I/O or a memory-mapped file as needed.

What stays the same:

- `pd == null` still selects the default `ProtectionDomain`.
- A buffer containing invalid class data can throw `ClassFormatError`.
- A name that does not match the class file is rejected.
- The same loader cannot define a duplicate runtime binary name by "switching overloads" from a byte array to a `ByteBuffer`.

**Practical advice:** Do not depend on side effects to the `position`/`limit` of the buffer object itself after `defineClass` across all implementations. If your code needs to read the bytes again, prepare `duplicate()`/`asReadOnlyBuffer()` or keep a separate byte source. Also evaluate lifetime and ownership when the buffer involves a memory-mapped file/resource.

## 7. `SecureClassLoader`: Accepting `CodeSource` Instead of Building a Domain Yourself

`SecureClassLoader` is a subclass of `ClassLoader` with the following overloads:

~~~java
protected final Class<?> defineClass(
        String name, byte[] b, int off, int len,
        CodeSource cs);

protected final Class<?> defineClass(
        String name, ByteBuffer b, CodeSource cs);
~~~

When `cs != null` is provided, `SecureClassLoader` creates/looks up the appropriate `ProtectionDomain` and associates it with the class. There is a protected hook:

~~~java
protected PermissionCollection getPermissions(CodeSource cs);
~~~

Previously, subclasses could override this hook to attach permission metadata based on `CodeSource` for the Java Security Manager. **The JDK 25 Javadoc states clearly:** permissions can no longer be used to control resource access because the Security Manager is no longer supported.

### 7.1. Comparing the Two Styles

| What you have | Choice |
| --- | --- |
| You already have a specific `ProtectionDomain` and need to pass it as-is | `ClassLoader.defineClass(..., pd)` |
| You have a `CodeSource` and want `SecureClassLoader` to build the domain | `SecureClassLoader.defineClass(..., cs)` |
| You have no custom code-source metadata | `ClassLoader.defineClass(...)` without `pd`, or `pd = null` |
| You want to prevent plugins from reading files/network on JDK 24+ | **Do not use** `ProtectionDomain`/`Permission` as a sandbox; use process/OS/container isolation |
| You want to audit artifact and signer provenance | Verify the actual byte source/signature, then attach an appropriate `CodeSource` to retain metadata |

### 7.2. `SecureClassLoader` Example Using `CodeSource`

File **`SecureSourceDemo.java`**, using the bytes of `Greeter.class` compiled in section 5:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.CodeSource;
import java.security.SecureClassLoader;
import java.security.cert.Certificate;

public class SecureSourceDemo {
    static final class OriginLoader extends SecureClassLoader {
        OriginLoader() {
            super(SecureSourceDemo.class.getClassLoader());
        }

        Class<?> fromSource(String name, byte[] bytes, CodeSource cs) {
            return defineClass(name, bytes, 0, bytes.length, cs);
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(
                Path.of("build/plugin/demo/plugin/Greeter.class"));

        CodeSource source = new CodeSource(
                Path.of("metadata/source.jar").toUri().toURL(),
                (Certificate[]) null);

        OriginLoader loader = new OriginLoader();
        Class<?> type = loader.fromSource(
                "demo.plugin.Greeter", bytes, source);

        CodeSource recorded =
                type.getProtectionDomain().getCodeSource();

        System.out.println("from origin loader="
                + (type.getClassLoader() == loader));
        System.out.println("source has marker="
                + (recorded != null
                    && recorded.getLocation() != null
                    && recorded.getLocation().getPath()
                        .endsWith("source.jar")));
    }
}
~~~

Compile/run from `pd-lab`:

~~~bash
javac --release 17 -d build/host host-src/SecureSourceDemo.java
java -cp build/host SecureSourceDemo
~~~

Stdout:

~~~text
from origin loader=true
source has marker=true
~~~

**Explanation:** `SecureClassLoader` converts `CodeSource` into a `ProtectionDomain`; `source.jar` in the metadata path **is not loaded or verified by the program**. The experiment still reads bytes from `build/plugin/demo/plugin/Greeter.class`. Setting an arbitrary URL does not prove provenance.

`URLClassLoader` is a common subclass of `SecureClassLoader` that loads classes/resources from a URL search path and attaches the corresponding code-source metadata. Using this standard library loader is usually simpler than writing `defineClass` yourself if you only need dynamic JAR loading; you still must manage `URLClassLoader.close()` and TCCL/resources.

## 8. Package Certificates/Signers: An Invariant to Preserve

An important point in the `ClassLoader.defineClass` Javadoc: **the first class defined in a package** determines the set of certificates that subsequent classes in that package must match. The certificate set is obtained from the `CodeSource` in `ProtectionDomain`.

Conceptual example:

~~~text
Loader L
  package example.lib
    A.class -- CodeSource certificates = {Signer-X}
    B.class -- CodeSource certificates = {Signer-X}  → same set: valid
    C.class -- CodeSource certificates = {Signer-Y}  → different set: SecurityException
~~~

This applies at the package scope of the **same loader** under the class-definition contract. It does **not** mean that two classes in different packages must share a signer, or that all JARs with the same package name in two different loaders share a single certificate set.

**Distinguish two easily confused factors:**

- Different `CodeSource.getLocation()` values **do not automatically mean** a signer mismatch. Java checks the **certificate set**, not JAR URL equality.
- If one class is unsigned and another is signed in the same package of a loader, the certificate-set difference can be rejected. Errors can also occur when mixing signed JARs with different signer sets.
- `Package sealing` is a different rule: manifest/`definePackage` metadata may require classes of a package to come from a consistent seal base. Do not call every sealing error a certificate mismatch.
- Passing `name = null` may bypass the package certificate comparison step as described in the Javadoc, **which is not a proper fix**. Supply the binary name and organize JARs/signers consistently.

### 8.1. Do Not "Self-Sign" by Stuffing Certificates into `CodeSource`

Constructing a `CodeSource(URL, Certificate[])` with self-collected certificates does not turn bytes into verified signed code. To prove a JAR is signed, you must run signature/entry-byte verification via the JAR verifier before trusting certificate metadata.

A reliable command to check:

~~~bash
jarsigner -verify -verbose -certs plugin.jar
~~~

This is a sample command to inspect a **real JAR**; replace `plugin.jar` with your artifact. `jarsigner` is part of the JDK toolchain (check availability in your active JDK). With a custom `JarFile` loader, note that an entry's signer information may only be meaningful after the verifier has read and verified the full entry contents; do not grab signer metadata from an unverified entry and assign it to a class.

## 9. Why Is `ProtectionDomain` No Longer a Sandbox on Modern JDKs?

### 9.1. Version History to Distinguish

| Version | Status |
| --- | --- |
| Java 8, many pre-17 JDKs | Security Manager/Policy was a mechanism that could control permissions for code by `ProtectionDomain` when enabled and with security checks |
| Java 17–23 | Security Manager was **deprecated for removal**; activation behavior depended on release and configuration, and new sandbox projects should not be built on it |
| Java 24 and later | **Security Manager permanently disabled** (JEP 486); cannot be re-enabled at startup or via `System.setSecurityManager` |
| JDK 25/26 | `ProtectionDomain`/`CodeSource` still exist for API compatibility/metadata, but `PermissionCollection` is not used to block resources via Security Manager |

JDK 24+ has key characteristics according to Oracle guidance:

- `System.getSecurityManager()` returns `null`.
- `System.setSecurityManager(...)` throws `UnsupportedOperationException`.
- Attempts to enable it with `-Djava.security.manager=...` flags are rejected by the JDK at startup.
- The Java Policy API is disabled/narrowed; domains are not granted permissions from a policy acting like the old Security Manager.
- Some security-related methods become no-ops, return fixed values, or throw exceptions per API migration.
- Class-definition checks **such as `java.*` names, class-file name mismatches, and signer consistency** are still enforced per the `defineClass` Javadoc; do not infer that "removing the Security Manager" means "all bytecode is defined unconditionally."

**Technical conclusion:** `new ProtectionDomain(cs, permissions)` can still describe the `permissions` passed to it, but **there is no Security Manager mechanism to enforce** that a plugin cannot open sockets/files/processes. To protect a system from untrusted plugins, use **OS process boundaries**, containers, filesystem/network permissions, appropriate OS/VM sandboxes, signature verification, and architectural restrictions on callable APIs.

### 9.2. `ProtectionDomain.implies` and `PermissionCollection` Should Not Be System Authorization Decisions

In older JDKs, `ProtectionDomain.implies(permission)` had meaning within the policy/permission model. After JDK 24, policy semantics are degraded; a result on metadata does not equate to an OS/VM enforcement step. Modern systems should not rely on testing domain permissions to decide whether a caller may read secrets or access resources.

If authorization is needed in an application, use **principal/identity validation** and permission checks at the business/API boundary (e.g., authenticated caller + role/capability check), rather than using a classloader domain as a substitute for actor identity.

## 10. Distinctions That Do Not Belong to `ProtectionDomain`

Do not confuse these layers:

1. **Runtime class identity:** binary name + defining loader. A different domain does not allow defining a duplicate class name in the same loader; the same domain does not make classes in two loaders the same type.
2. **Package certificate consistency:** based on `CodeSource` certificates during `defineClass`; not `JPMS requires`.
3. **Package sealing:** a rule declaring a seal base/manifest, distinct from signer certificates.
4. **JPMS module access:** `requires`/readability, `exports`, `opens`, module layers. Attaching a domain does not fix `IllegalAccessError` or `InaccessibleObjectException`.
5. **Resource loading:** `ClassLoader.getResource` locates resources; it does not use `ProtectionDomain.getCodeSource()` as a resolver.
6. **Native-access controls:** the `--enable-native-access` flag on modern JDKs is a separate mechanism; `ProtectionDomain` is not used to enable JNI/FFM.
7. **Class linking and initialization:** `defineClass` creates the runtime class; `resolveClass` links it; `<clinit>` runs on initialization triggers, not because a domain was added.
8. **JAR URLs and file handles:** a domain is only metadata; opening/closing JARs is the responsibility of the loader/resource owner such as `URLClassLoader` and `JarFile`.

## 11. Common Errors and Fixes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `NoClassDefFoundError: wrong name` during `defineClass` | `name` differs from the binary name in the bytes | Fix the class name ↔ class file mapping; do not rename arbitrarily |
| `SecurityException: Prohibited package name java...` | Loader is not permitted to define `java.*` packages | Do not use `java.*` names for plugins |
| `SecurityException` on signer mismatch | Mixing classes in the same package with different signing certificate sets | Keep signers/packages consistent; verify JARs |
| `ClassFormatError` or `VerifyError` | Corrupted/incompatible bytes | Check the class file, Java version, and bytecode toolchain |
| `IndexOutOfBoundsException` | Invalid `off`/`len` | Compute bounds properly; use the right buffer |
| `LinkageError` when defining a duplicate name | Loader defines a class with the same name multiple times | `findLoadedClass` + `getClassLoadingLock`; do not redefine |
| Plugin can still open files even though domain has empty `Permissions` | No Security Manager enforcing the domain | Use OS/process isolation and explicit authorization |
| `ClassCastException` with the same class name | Two different defining loaders | Share the API via parent; check type identity |
| `IllegalAccessError`/`InaccessibleObjectException` | JPMS access/exports/opens | Fix module graph/access; a domain does not open packages |
| Wrong audit source URL | Custom-created `CodeSource` does not match the byte source | Track the real artifact and verify before attaching metadata |
| `getProtectionDomain().getCodeSource()` is null or URL is null | Default domain or missing source metadata | Null-check; do not conclude the class does not exist |
| Random errors on `ByteBuffer` reuse | Buffer state/contents reused improperly | Keep bytes immutable, duplicate/slice, and manage I/O lifetime |

### 11.1. Checklist When Writing `findClass` Yourself

- [ ] Receive the correct **binary name** and map it to a valid class-file entry.
- [ ] Read bytes from a trusted source and close `InputStream`/`JarFile` appropriately.
- [ ] If `CodeSource` is needed, obtain it from the **actual artifact** and verify signatures before trusting certificate metadata.
- [ ] Choose the default PD, explicit PD, or `SecureClassLoader` overload based on metadata needs; do not use it to promise a sandbox.
- [ ] Maintain certificate consistency within the same package/loader and package sealing when declared.
- [ ] Do not define classes in `java.*` from a plugin/application loader.
- [ ] Keep `findLoadedClass`/locking handled by default `loadClass`, avoiding duplicate definitions.
- [ ] Test both the `byte[]` overload and the `ByteBuffer` overload if your library supports both sources.
- [ ] Log the binary name, defining loader, `CodeSource` location, module, and artifact version **without leaking sensitive information**.
- [ ] When reloading a plugin, use a new-generation loader and clean up old loader/JAR handles; changing the domain does not reset a runtime class.
- [ ] On JDK 24+, use a process/OS sandbox for untrusted code instead of Security Manager/PD.

## 12. Self-Check Questions

1. If no `ProtectionDomain` is passed to `defineClass`, does the class have a domain? **Yes, the default domain.**
2. Does passing `null` to the PD overload differ from the default overload? **In terms of domain selection, no: both use the default.**
3. Does `CodeSource.getLocation()` prove the bytecode actually came from that URL? **No, if the loader sets metadata itself without verifying the source.**
4. Does `ProtectionDomain` determine whether a class in loader A can be cast to a class of the same name in loader B? **No; runtime type identity depends on the defining loader.**
5. Which overloads of `SecureClassLoader` accept `CodeSource`? **The byte-array and `ByteBuffer` variants of `SecureClassLoader` itself.**
6. Why should `name = null` not be used for `defineClass`? **It drops the expected binary-name check and weakens certificate/package consistency checks.**
7. Do different `CodeSource` URLs with identical certificate sets automatically fail the signer check? **Not solely because of different URLs; the signer check is based on certificate sets.**
8. Does `ProtectionDomain` automatically verify a JAR's digital signature from a hypothetical URL? **No.**
9. Does JDK 25 still enable the Java Security Manager to sandbox plugins? **No; it has been permanently disabled since JDK 24.**
10. Does `defineClass` taking a `ByteBuffer` allow defining a duplicate name in the same loader? **No.**
11. What does the `wrong name` test pattern prove? **A class file has a real binary name; a different `name` argument will be rejected.**
12. Does a non-null `ProtectionDomain.getPermissions()` guarantee the VM will forbid operations outside those permissions? **No on JDK 24+; there is no Security Manager enforcement.**
13. Should you trust `Signer-X` merely because a custom loader stuffed it into `CodeSource`? **No; you must verify the JAR signature/entry bytes.**

## 13. Official References

1. [`ClassLoader` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): all `defineClass` overloads, default domain, package signer constraints, `name` validation, `ByteBuffer`.
2. [`SecureClassLoader` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/SecureClassLoader.html): `defineClass(..., CodeSource)` and `getPermissions` hook; API note on Security Manager.
3. [`ProtectionDomain` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/ProtectionDomain.html): constructors, `getCodeSource`, `getPermissions`, `getClassLoader`, `getPrincipals`.
4. [`CodeSource` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/CodeSource.html): location, certificate/signer metadata.
5. [Security Manager Permanently Disabled — JDK 25](https://docs.oracle.com/en/java/javase/25/security/security-manager-is-permanently-disabled.html): API/policy changes since JDK 24, why permissions no longer create a sandbox.
6. [JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486): official design decision.
7. [JVMS §5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3): runtime class identity, defining/initiating loader.
8. [`JarFile` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/jar/JarFile.html): JAR entries, verifier metadata, and code signer information.

**Conclusion:** The `defineClass` variants differ in **byte representation** (`byte[]` vs. `ByteBuffer`) and **domain selection** (default, passing a `ProtectionDomain`, or letting `SecureClassLoader` create one from `CodeSource`). A domain attaches code-source/certificate and permission metadata to a runtime class, but **does not alter class identity** and **does not replace a sandbox** on JDK 24+. Always preserve the expected binary name, package signer consistency, and verify the actual artifact before trusting metadata.
