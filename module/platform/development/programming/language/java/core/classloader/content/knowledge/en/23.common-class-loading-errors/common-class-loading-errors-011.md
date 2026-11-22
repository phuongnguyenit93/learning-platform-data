# SecurityException Due to Package Sealing, Certificates, or Prohibited Packages

When a Java application loads classes from JARs, `ClassLoader` can throw **`java.lang.SecurityException`** even if the class file exists, the path is correct, and the compiled bytecode is valid. In the **Java core – classloader** topic, there are three causes that are easily confused:

1. **Package sealing violation**: the loader defines classes belonging to the **same runtime package** from JAR sources that do not conform to the `Sealed` package rule.
2. **Package signer/certificate mismatch**: the loader defined the first class in the package with **one set of signer certificates**, but a subsequent class in the same package has a **different** certificate set (for example, signed and unsigned).
3. **Prohibited package name `java.*`**: an application/custom loader attempts to **define on its own** a class whose binary name starts with `java.`, whereas Java allows only the designated group of platform loaders to do this.

All three cases can manifest as a `SecurityException`, but **their validation rules, causes, and fixes differ**. They also **do not depend on whether SecurityManager is enabled**: especially from JDK 24 onward, SecurityManager has been permanently disabled, yet the class loading constraints above still have their own significance.

## 1. Concepts to Distinguish

Before fixing the error, it is necessary to distinguish these terms:

| Term | Meaning |
|---|---|
| **Binary class name** | A name such as `sample.api.First`, `java.demo.Forbidden`; passed to `ClassLoader.loadClass` and `defineClass` |
| **JAR entry name** | The path inside the archive, such as `sample/api/First.class`; different from the binary name |
| **Defining loader** | The loader that actually defines the runtime class; may differ from the loader initially invoked due to parent delegation |
| **Runtime class identity** | The pair **(binary name, defining class loader)** |
| **Runtime package identity** | For regular classes, the pair **(package name, defining class loader)** |
| **JAR sealing** | A manifest/package convention to require classes in a package to be loaded by a loader from a matching JAR source |
| **Signer certificate set** | The set of code source certificates associated with a class upon definition, checked for consistency within the loader's package |
| **`ProtectionDomain` / `CodeSource`** | Metadata related to the class/code source, which may contain a URL and certificates |
| **`SecurityManager`** | A historical permission-checking mechanism, distinct from the class definition checks discussed here |

A JAR containing `a.b.C` **does not guarantee** the class will be loaded successfully: the JVM/loader also checks the name, source, package permissions, signatures, class file version, and type linking.

**Important:** The same package name in two different loaders **is not the same runtime package**. Sealing and signer conditions are evaluated within the appropriate loader/package context, which does not mean every JAR across the entire JVM is forced to share a single certificate set.

## 2. Three Causes of SecurityException: Quick Comparison

| Scenario | Source of Check | Example | Resolution Approach |
|---|---|---|---|
| **Sealing violation** | JAR manifest/package metadata, loaders such as `URLClassLoader` | `sample.api.First` from sealed JAR A, `sample.api.Second` from JAR B | Move classes in the same sealed package into the proper JAR, or redesign the sealing/package |
| **Signer mismatch** | `ClassLoader#defineClass` and the package's certificate set | First class from a signed JAR, subsequent class unsigned in the same package/loader | Sign the classes consistently, avoid mixing unsigned/signed, or separate namespaces/loaders according to the architecture |
| **`java.*` prohibited** | `ClassLoader#defineClass` and the reserved platform namespace | A custom loader defines `java.demo.Forbidden` | Rename the package to an application namespace; delegate standard classes to the platform |
| **Legacy permission denial** | SecurityManager in older runtimes when enabled | `checkPermission(new FilePermission(...))` | Inspect the legacy JDK/policy; **do not equate** this with the three errors above |

On OpenJDK/HotSpot, the stack trace or message often includes phrases such as:

```text
sealing violation: package ... is sealed
sealing violation: can't seal package ...: already loaded
class "..."'s signer information does not match signer information of other classes in the same package
Prohibited package name: java.demo
```

These are **diagnostic message patterns**, not fixed strings guaranteed by every Java implementation. There may be differences in capitalization, punctuation, stack traces, JDK versions, and frameworks. **Rely on the exception class, root cause, and classloader/code source**; do not write error-handling code that matches the message verbatim.

## 3. What Is Package Sealing?

In the **JAR File Specification**, a package can be declared **sealed**. For loaders that support JAR manifest sealing, the goal is to ensure that classes defined by **that loader** in that package originate from the **same JAR source** according to the sealing rules.

Example JAR A:

```text
a.jar
├── META-INF/
│   └── MANIFEST.MF
└── sample/
    └── api/
        └── First.class
```

Manifest:

```text
Manifest-Version: 1.0
Sealed: true

```

JAR B:

```text
b.jar
└── sample/
    └── api/
        └── Second.class
```

If **the same `URLClassLoader`** loads `sample.api.First` from A and then attempts to load `sample.api.Second` from B, package `sample.api` has already been recorded as sealed with source A; the class from B does not come from the corresponding seal base. The loader may throw `SecurityException`.

**It is not an error caused by duplicate package names themselves.** If both JARs are unsealed and share the same package, in the standard classpath/unnamed module model they can both provide classes with **different binary names** in the same runtime package — however, independent constraints such as signer certificates or module resolution still apply.

### 3.1. Manifest Declaring JAR-Wide Sealing

Placed in the **main section**:

```text
Manifest-Version: 1.0
Sealed: true

```

`Sealed: true` applies by default to packages in the JAR, except for those with a specific override in individual manifest sections.

`Sealed: false` or omitting the `Sealed` attribute typically leaves packages unsealed, subject to the specification rules and package-level overrides.

### 3.2. Sealing Only a Single Package

A manifest can be configured specifically:

```text
Manifest-Version: 1.0

Name: sample/api/
Sealed: true

```

Note:

- `Name: sample/api/` is the **package directory entry name**, using `/` separators and a trailing `/`.
- A blank line separates the **main section** and the individual section.
- This is **manifest** data, not Java source.
- Other packages do not automatically become sealed just because one package is marked `Sealed: true`.

Another pattern:

```text
Manifest-Version: 1.0
Sealed: true

Name: sample/api/
Sealed: false

```

means every package is sealed by default, **except `sample.api` which is overridden to be unsealed**. Do not hand-write syntactically invalid sections or forget the terminating newline; inspect `META-INF/MANIFEST.MF` after building.

### 3.3. Who Enforces Sealing?

**JAR manifest sealing is a behavior of the loader/packaging mechanism**, typically `URLClassLoader` when opening JARs and processing package metadata. At the low level, `ClassLoader#defineClass` **does not automatically read manifests or determine a JAR seal base** solely from a `byte[]` array.

If you write a custom loader that reads bytes and calls `defineClass`, you need to decide how to:

1. Read manifest/package attributes.
2. Define package metadata using `definePackage` when needed.
3. Compare the source of subsequent classes against the seal base.
4. Verify signer certificates/`CodeSource` according to the rules.

Relying on raw `defineClass` and claiming “JAR sealing is enforced” is wrong. Conversely, **you should not ignore package metadata when writing a production custom loader** that performs a role equivalent to standard JAR loaders.

## 4. Java 17+ Demo: Sealing, Prohibited Packages, and Valid/Invalid Class Loading

This exercise creates two JARs with the same `sample.api` package where each JAR contains a class with a **different name**, a test class under `java.demo`, and a main program that loads them via dedicated loaders.

Source/output structure:

```text
package-security-demo/
├── src/
│   ├── one/sample/api/First.java
│   ├── two/sample/api/Second.java
│   ├── java/demo/Forbidden.java
│   └── app/PackageFailures.java
├── sealed.mf
├── out/
│   ├── one/
│   ├── two/
│   ├── forbidden/
│   └── app/
└── dist/
```

### 4.1. Class in the First JAR

File **`src/one/sample/api/First.java`**:

```java
package sample.api;

public class First {
    public static String name() {
        return "first";
    }
}
```

### 4.2. Class in the Second JAR

File **`src/two/sample/api/Second.java`**:

```java
package sample.api;

public class Second {
    public static String name() {
        return "second";
    }
}
```

Both classes share the **same package name `sample.api`** but have **different binary names**. This highlights a sealing/signing failure rather than a duplicate definition error for the exact same class.

### 4.3. Test Class in a Prohibited Namespace

File **`src/java/demo/Forbidden.java`**:

```java
package java.demo;

public class Forbidden {
}
```

**For educational demonstration only.** Real application code must not be placed under the `java.*` namespace. In this experiment, `javac --release 17` can produce the `java/demo/Forbidden.class` file on the JDK in use; compiling it does not grant permission for an **application-defined loader to define a runtime class** with that name.

### 4.4. Test Runner Program

File **`src/app/PackageFailures.java`**:

```java
package app;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;

public final class PackageFailures {
    static final class BytesLoader extends ClassLoader {
        BytesLoader(ClassLoader parent) {
            super(parent);
        }

        Class<?> define(String name, byte[] bytes) {
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader parent =
                PackageFailures.class.getClassLoader();

        URL[] urls = {
            Path.of(args[0]).toUri().toURL(),
            Path.of(args[1]).toUri().toURL()
        };

        try (URLClassLoader loader =
                new URLClassLoader(urls, parent)) {
            Class<?> first = loader.loadClass(
                    "sample.api.First");

            System.out.println("First loader: "
                    + (first.getClassLoader() == loader));

            try {
                loader.loadClass("sample.api.Second");
                System.out.println("Second: loaded");
            } catch (SecurityException ex) {
                System.out.println("Second: SecurityException");
            }
        }

        BytesLoader own = new BytesLoader(parent);
        byte[] bytes = Files.readAllBytes(Path.of(args[2]));

        try {
            own.define("java.demo.Forbidden", bytes);
            System.out.println("Forbidden: loaded");
        } catch (SecurityException ex) {
            System.out.println("Forbidden: SecurityException");
        }
    }
}
```

**Roles of the two loaders:**

- `URLClassLoader` checks JAR/package metadata when locating classes from the URLs.
- `BytesLoader` intentionally calls `defineClass` directly to prove that **the `java.*` namespace is still checked**, even without a JAR manifest or SecurityManager.
- `First` is loaded **before `Second`** to establish the runtime package state, and then the second load reveals the sealing or signer mismatch.

In practice, you must check `args.length` and print usage instructions when arguments are missing; the example below is run with exactly three arguments. Catching `SecurityException` here is for **measuring failures**. **Do not swallow exceptions in a production plugin manager** and treat the plugin as successfully loaded.

### 4.5. Sealing Manifest

File **`sealed.mf`**:

```text
Manifest-Version: 1.0
Sealed: true

```

This is the input manifest for the `jar` tool. The final blank line marks the end of the main section.

### 4.6. Compilation and JAR Packaging Commands (Bash)

From the `package-security-demo` directory, using JDK 17+:

```bash
mkdir -p out/one out/two out/forbidden out/app dist

javac --release 17 -d out/one src/one/sample/api/First.java
javac --release 17 -d out/two src/two/sample/api/Second.java
javac --release 17 -d out/forbidden src/java/demo/Forbidden.java
javac --release 17 -d out/app src/app/PackageFailures.java

# JAR A with a sealed package.
jar --create --file dist/one-sealed.jar \
  --manifest sealed.mf -C out/one .

# JAR A without sealing (control JAR for comparison).
jar --create --file dist/one-open.jar -C out/one .

# JAR B without sealing.
jar --create --file dist/two-open.jar -C out/two .

# Case 1: sealed A + B containing the same package.
java -cp out/app app.PackageFailures \
  dist/one-sealed.jar dist/two-open.jar \
  out/forbidden/java/demo/Forbidden.class

# Case 2: neither A nor B is sealed.
java -cp out/app app.PackageFailures \
  dist/one-open.jar dist/two-open.jar \
  out/forbidden/java/demo/Forbidden.class
```

### 4.7. Equivalent Commands in PowerShell

From the same directory, in Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path out/one, out/two, out/forbidden, out/app, dist | Out-Null

javac --release 17 -d out/one src/one/sample/api/First.java
javac --release 17 -d out/two src/two/sample/api/Second.java
javac --release 17 -d out/forbidden src/java/demo/Forbidden.java
javac --release 17 -d out/app src/app/PackageFailures.java

jar --create --file dist/one-sealed.jar --manifest sealed.mf -C out/one .
jar --create --file dist/one-open.jar -C out/one .
jar --create --file dist/two-open.jar -C out/two .

java -cp out/app app.PackageFailures dist/one-sealed.jar dist/two-open.jar out/forbidden/java/demo/Forbidden.class
java -cp out/app app.PackageFailures dist/one-open.jar dist/two-open.jar out/forbidden/java/demo/Forbidden.class
```

The commands work with JDK 17+ when `java`, `javac`, and `jar` are on the PATH.

### 4.8. Verified Output

**Case 1 — A sealed, B unsealed:**

```text
First loader: true
Second: SecurityException
Forbidden: SecurityException
```

**Case 2 — Both A and B unsealed:**

```text
First loader: true
Second: loaded
Forbidden: SecurityException
```

The example was compiled with **`javac --release 17`**, packaged with `jar`, and run successfully on **OpenJDK 24**. The strings above are stdout produced by the test code itself, not the stack trace of `SecurityException`.

**Conclusions from the comparison:**

1. Two unsealed JARs can provide two differently named classes in the same package under the same defining loader when all remaining conditions are satisfied.
2. Sealing the package from JAR A causes a class in the same runtime package from source B to be rejected.
3. Regardless of whether sealing is enabled, the custom `BytesLoader` still cannot define the name `java.demo.Forbidden`.
4. The occurrence of `SecurityException` **does not mean SecurityManager is enabled**.
5. Removing sealing does not fix the `java.*` package error, because that is **an independent check**.

## 5. Why Can Class Loading Order Change the Error Message?

With `URLClassLoader`, package metadata is checked when the loader defines a class in the package.

### Scenario A — Package Starts Sealed

```text
load sample.api.First from sealed a.jar
   |
   +--> package sample.api: sealed with a.jar
   |
load sample.api.Second from b.jar
   |
   +--> seal base violation -> SecurityException
```

### Scenario B — Package Starts Unsealed, Subsequent JAR Attempts to Seal

```text
load sample.api.Second from unsealed b.jar
   |
   +--> package sample.api: not sealed
   |
load sample.api.First from sealed a.jar
   |
   +--> cannot “retroactively seal” a package already defined under a different policy
   |
   +--> SecurityException
```

Both are sealing violations, yet the messages differ. Do not fix the issue by shuffling JAR order “to make it run” without understanding the contract: reordering may only change **which class wins** or which check fails.

Another issue is a **duplicate class**: if two JARs both contain `sample/api/First.class` and share the same loader, the loader may pick the first version according to its lookup policy. That is **not** a sealing error merely because of a duplicate file; distinguish it from **different classes within the same sealed package**.

## 6. Certificate/Signer Mismatch Is Independent of Sealing

In addition to package sealing, **`ClassLoader#defineClass`** checks the consistency of the certificate set in a package belonging to **a single defining loader**.

According to the Java SE 17 JavaDoc:

- The **first class** defined by the loader in a package determines **that package's set of certificates**.
- Subsequent classes defined by **the same loader** in the same package must have **the same set of certificates**.
- The set of certificates is obtained from the **`CodeSource` of the `ProtectionDomain`** associated with the class.
- If the certificate sets do not match, `defineClass` can throw **`SecurityException`**.
- When the `defineClass` overload receives `name = null`, some name-based checks are not performed according to the JavaDoc; **do not use `null` as a trick to bypass checks**. Provide the proper binary name when defining a class.

Example:

```text
loader L:
  sample.api.First  from one-signed.jar  [certificate set S]
  sample.api.Second from two-open.jar    [unsigned/empty set]
         |
         v
      SecurityException
      because signer information is inconsistent
```

Key point: **A package can be unsealed and still violate signer consistency**. Sealing concerns the **JAR source/seal base**; signer mismatch concerns the **signer certificate set**. These are two separate checks.

### A Signer Certificate Is Not a “Global Trust Level”

The certificate set used for package consistency is signer information attached to the code source. It does not mean:

- The JVM automatically verifies that every certificate was issued by a trusted public CA.
- Two JARs with the same signer certificate have been authorized by your organization to run.
- JAR signing replaces dependency provenance, vulnerability, and update pipeline checks.
- A signed JAR automatically protects plugins against all malicious behavior.

A JAR signed with a **self-signed test certificate** can pass the signer check step, but it should not be treated as proof of trust in production.

### Can Signed and Unsigned Classes Be Mixed in the Same Package?

Under **the same defining loader**, if the first class has non-empty signer certificates while a subsequent class in the same runtime package is unsigned, the sets differ, so a `SecurityException` may occur.

If two plugins are defined by **two separate class loaders** and **do not share the same runtime package**, checks between classes from the two defining loaders do not apply to the same loader's package. However, objects/types created by the two loaders are not automatically compatible either. **Separating loaders to avoid errors** is only appropriate when it fits the class identity and API boundary architecture; it is no substitute for a proper signing policy.

## 7. Optional Practice: Reproducing a Signer Mismatch with JDK Tools

Section 4 created `dist/one-open.jar` and `dist/two-open.jar` — both **unsealed**. We sign **only** the first JAR with a test certificate to isolate the signer cause from sealing.

From the exercise directory:

```bash
# FOR LOCAL TESTING ONLY.
# "changeit" is a public demo password; never use it
# for real signing keys or production environments.
keytool -genkeypair \
  -alias lesson \
  -keyalg RSA \
  -keysize 2048 \
  -storetype PKCS12 \
  -keystore demo-test.p12 \
  -storepass changeit \
  -keypass changeit \
  -dname "CN=Lesson Test" \
  -validity 2 \
  -noprompt

# Sign the first JAR, keeping the second JAR unsigned.
jarsigner \
  -keystore demo-test.p12 \
  -storepass changeit \
  -keypass changeit \
  -signedjar dist/one-signed.jar \
  dist/one-open.jar lesson

# Verify that the JAR contains signature metadata.
jarsigner -verify dist/one-signed.jar

# Load the first class from the signed JAR and the subsequent class from the unsigned JAR.
java -cp out/app app.PackageFailures \
  dist/one-signed.jar dist/two-open.jar \
  out/forbidden/java/demo/Forbidden.class
```

In **PowerShell**, write long commands on a single line or use valid PowerShell line-continuation syntax instead of Bash-style trailing `\` characters:

```powershell
keytool -genkeypair -alias lesson -keyalg RSA -keysize 2048 -storetype PKCS12 -keystore demo-test.p12 -storepass changeit -keypass changeit -dname "CN=Lesson Test" -validity 2 -noprompt

jarsigner -keystore demo-test.p12 -storepass changeit -keypass changeit -signedjar dist/one-signed.jar dist/one-open.jar lesson

jarsigner -verify dist/one-signed.jar

java -cp out/app app.PackageFailures dist/one-signed.jar dist/two-open.jar out/forbidden/java/demo/Forbidden.class
```

**Program output** verified on JDK 24:

```text
First loader: true
Second: SecurityException
Forbidden: SecurityException
```

This time:

- `sample.api.First` comes from a **signed JAR**, which is **not sealed**.
- `sample.api.Second` comes from an **unsigned JAR**, in the same runtime package of the loader.
- Loading the second class throws `SecurityException` because **the signer information differs**, not because of sealing.
- The `Forbidden` error remains independent and is reproduced a third time.

**Warning about `jarsigner -verify`:** With a self-signed test certificate, the tool may print `jar verified` **with warnings** about the trust/PKIX chain, soon-to-expire certificate, and missing trusted timestamp. This is expected behavior in this test, and **the text “jar verified” alone must not be used to certify software trustworthiness**.

Do not commit, publish, or reuse a test keystore with the password `changeit`. Production signing must have dedicated key management, trust policies, signature verification, and secret handling.

### If You Want to See the Detailed Cause

In the demo, temporarily replace the catch block:

```java
} catch (SecurityException ex) {
    System.out.println("Second: SecurityException");
}
```

with:

```java
} catch (SecurityException ex) {
    ex.printStackTrace();
}
```

This is an **illustrative replacement snippet** inside the demo's method, not a standalone program. When run, the stack trace helps distinguish sealing verification in `URLClassLoader` from the signer check in `ClassLoader#defineClass`. Do not hard-code full stack traces into the lesson because they vary across JDK versions and vendors.

## 8. Prohibited Package java.*: Unrelated to Sealing or Certificates

The third restriction appears in `ClassLoader#defineClass`. For an ordinary application/custom loader, names such as:

```text
java.demo.Forbidden
java.lang.MyString
java.util.CustomCollections
```

all begin with `java.`, so they cannot be defined by the loader itself.

The Java SE 17 JavaDoc states specifically: classes whose names begin with `java.` can only be defined by **the platform class loader or its ancestors**. This does not mean “any loader whose parent is the platform loader is allowed”; an application-created loader is a **child**, not the platform loader or an ancestor.

### Permitted loadClass vs. Prohibited defineClass

```java
ClassLoader pluginLoader = new ClassLoader(
        ClassLoader.getSystemClassLoader()) {
};

Class<?> core = pluginLoader.loadClass("java.lang.String");
System.out.println(core == String.class);
```

This is a valid illustrative snippet inside a method, **without its own `main`**. By default, `loadClass` delegates to the parent to obtain the runtime-defined `String`, so the comparison is normally `true` on a standard JVM.

By contrast, `BytesLoader` in the demo calls:

```java
own.define("java.demo.Forbidden", bytes);
```

and receives a `SecurityException` because it tries to have **a custom loader define a new class on its own in the `java.*` namespace**.

**Note:** Compiling to a `java/demo/Forbidden.class` file does not mean the JVM allows an application loader to load that class; compile-time and runtime class definition enforce different checks.

### Do Not “Fix” This by Switching to javax.* or jdk.*

The `java.*` rule in `defineClass` is a specifically documented constraint. However, names such as `javax.*`, `jdk.*`, and `sun.*` are also commonly reserved for or tied to the platform/JDK/frameworks and may be subject to module/package access or other restrictions. **Do not squat on ecosystem namespaces** merely to bypass a check.

Use your own package, for example:

```java
package com.example.plugin;
```

This is an illustrative package declaration. Name packages after the domain/organization that owns the code to avoid conflicting with the platform.

## 9. How Defining Loader, Parent Delegation, and Runtime Package Relate

From the JVM's perspective, a normal runtime package is identified by:

```text
(package name, defining class loader)
```

Example:

```text
Loader A defines sample.api.First
Loader B defines sample.api.Second
    |
    +--> same package name "sample.api"
    +--> DIFFERENT defining loader
    +--> DIFFERENT runtime package
```

Consequences:

- The two classes do not automatically share **package-private access**, even though the source code declares the same `package sample.api;`.
- A package sealed in URLClassLoader A does not automatically make the identically named package in loader B the same sealed package.
- Package signer consistency is enforced within the loader's class-definition context; it does not mean the signer of every class with the same package name **across the entire JVM** must match.
- If the host passes a private API class from loader A to loader B, `ClassCastException`, `IllegalAccessError`, or `LinkageError` can arise depending on the situation.

**Do not use a per-plugin loader as a blanket trick to hide sealing/signature problems.** It can reduce package conflicts between plugin versions when architecturally sound, but it also creates namespace/type boundaries that must be managed carefully.

### When Parent Wins Over Child

If the parent loader has already defined `sample.api.First`, a parent-first child `URLClassLoader` may return the class from the parent instead of defining the copy inside the plugin JAR itself. In that case, the child's package/sealing/signer checks apply to **the classes the child actually defines**, not every class name requested on the child via `loadClass`.

Check:

```java
System.out.println(type.getClassLoader());
System.out.println(type.getModule());
```

This is a snippet using a `Class<?> type` variable inside a method, not a standalone program. Do not infer the defining loader solely from the variable on which `loader.loadClass(...)` was called.

## 10. What Happens with a Hand-Written Custom ClassLoader?

A loader that reads bytes directly:

```java
protected Class<?> findClass(String name)
        throws ClassNotFoundException {
    byte[] data = loadBytesFromTrustedSource(name);
    return defineClass(name, data, 0, data.length);
}
```

This is a **Java pseudocode example**, because `loadBytesFromTrustedSource` is not defined.

From the perspective of security/package rules:

- `defineClass` still enforces **checks such as `java.*` names and the signer certificate set**.
- If passing a `ProtectionDomain`, `CodeSource` carries the appropriate certificate data per the contract; do not forge or alter certificates “to make it run”.
- `defineClass` does not inherently know the **manifest sealing** of arbitrary byte sources unless the loader provides the corresponding package metadata and verification.
- Do not redefine the same binary name in the same loader; that situation is a distinct **duplicate definition/`LinkageError`**.
- If the bytecode is malformed, `ClassFormatError` or `VerifyError` may occur; do not turn every failure into `SecurityException` or `ClassNotFoundException`.
- If the passed name differs from the class name inside the bytes, `NoClassDefFoundError` may occur; that is not package sealing.

For applications needing standard JAR loading, **`URLClassLoader`** is a more practical choice than implementing all package verification yourself. For large plugin ecosystems, you can use an existing module/plugin manager and design clear package namespaces.

## 11. Practical Diagnosis: From Exception to Root Cause

When encountering a `SecurityException` during class loading, an effective workflow is:

1. **Read the full stack trace.** Does the error occur when `URLClassLoader` checks sealing, or in `ClassLoader#defineClass` when checking certificates/namespace?
2. **Identify the actual binary name.** Does it start with `java.`? Does it belong to a package that already had a class loaded earlier?
3. **Identify the defining loader.** Do not guess from the class name or JAR path. Record the class loader object identity of the successfully loaded classes.
4. **Check the loading order.** Which class in the package was defined first, and from which JAR?
5. **Inspect each JAR's manifest.** Is `Sealed: true` present in the main section or a package-specific section?
6. **Inspect JAR signing.** Is the first JAR signed while the next JAR is unsigned? Are the certificate sets different? Is there a signature verification error?
7. **Distinguish duplicate-named resources/JARs.** Having two JARs with the same package but different class names differs from having a duplicate binary class name.
8. **Inspect the actual classpath/module path.** Which loader sees which JARs? Is parent-first/child-first delegation having an effect?
9. **Do not enable SecurityManager to fix it.** Sealing, signing, and package reservation errors can still occur when the manager is absent.
10. **Fix the root cause.** Align package/JAR boundaries, signing policy, or namespaces; do not catch and ignore the error.

### Inspecting the Manifest with JDK Tools

```bash
jar --list --file dist/one-sealed.jar
jar --list --file dist/two-open.jar
```

`jar --list` confirms the class entries and manifest entry, but **does not print the manifest contents itself**. To inspect `META-INF/MANIFEST.MF`, use an archive viewer or extract it **into a separate temporary directory**:

```bash
mkdir -p manifest-inspect
cd manifest-inspect
jar --extract --file ../dist/one-sealed.jar META-INF/MANIFEST.MF
```

These are example Bash commands inside the experiment directory; the relative path `../dist/...` assumes `manifest-inspect` sits alongside `dist`. After opening the text file, check `Sealed` and the package sections.

### Inspecting Signing

```bash
jarsigner -verify -verbose -certs dist/one-signed.jar
```

The command can display the digital signature and warnings about the certificate chain/timestamp. **A JAR verified for integrity does not automatically mean every signer is trusted**; trust verification must rely on the actual trust store/PKI policy.

If you need to inspect class metadata once loading succeeds:

```java
Class<?> type = loader.loadClass("sample.api.First");
System.out.println("Class: " + type.getName());
System.out.println("Defining loader: " + type.getClassLoader());

Package pkg = type.getPackage();
System.out.println("Package sealed: "
        + (pkg != null && pkg.isSealed()));

var pd = type.getProtectionDomain();
var source = pd == null ? null : pd.getCodeSource();
System.out.println("Code source: "
        + (source == null ? "(unknown)" : source.getLocation()));
```

This is an illustrative snippet inside a method that has a `loader` variable. `Package.isSealed()` reports package metadata; `CodeSource.getLocation()` provides code source information when available, **not proof of trust**. It can also be `null` depending on the class/runtime.

For certificates, `CodeSource.getCertificates()` may return an array or `null`. Do not use `toString()`, URL order, or certificate count alone as security validation criteria.

## 12. Proper Fixes for Each Error Type

### A. Sealing violation

**Proper fix:** Place all classes belonging to the sealed package into a single consistent JAR/seal base according to the contract; or reconsider whether sealing is actually needed. A project that intentionally splits the `sample.api` package across multiple JARs should **not** seal that package in one JAR and load the rest from another JAR through the same loader.

Architectural options:

- Consolidate classes belonging to the same sealed package into a single consistent JAR.
- Separate packages by artifact/module/plugin ownership to avoid split packages.
- Remove or modify `Sealed` **only when doing so meets packaging and security requirements**, never to mask a broken deployment.
- For independent plugins, use separate loaders if type boundaries and shared APIs are clearly designed.
- Add build validation to check manifests and split packages before deployment.

**Mistake:** Removing an exception catch or reversing the JAR order without fixing the package/source structure.

### B. Signer certificate mismatch

**Proper fix:** Apply a consistent JAR signing policy for classes sharing a runtime package/defining loader. For example, if signed packages are required, ensure that classes in the same package have the **same appropriate signer certificate set**, and move unsigned dependencies to a different package where appropriate.

You can:

- Standardize on a valid signing key/certificate pipeline for shared packages.
- Check whether post-build repacking/shading has invalidated signature metadata in the JAR.
- Do not mix unsigned and signed entries under the same runtime package of a single loader.
- Avoid package collisions between third-party libraries with different provenance or signing.
- Verify signer trust, expiration, and timestamp/chain validation **in addition to** consistency requirements to ensure real security.

**Mistake:** Assigning a new self-signed certificate to each JAR and assuming “having both signed is enough.” Two different certificate sets can still violate package consistency.

### C. Prohibited `java.*` Package

**Proper fix:** Place application classes in a namespace you own, such as `com.example.plugin`, and **let the platform loaders provide standard classes**.

- Do not attempt to define `java.lang.String` or `java.foo.Helper` from an ordinary application loader.
- Do not expect changing the parent loader to the platform loader to grant permission to define `java.*` names.
- Do not use `--add-opens`/`--add-exports` flags to “grant permission” for `defineClass` in the `java.*` namespace; those flags govern module access.
- Check whether bytecode generators, shading, or relocation renamed binary names incorrectly.

**Mistake:** Overriding `loadClass` as child-first and assuming that disables `defineClass` security checks.

## 13. Distinguishing from Other Errors

| Error | Difference from the Three SecurityException Causes |
|---|---|
| `ClassNotFoundException` | The requested loader could not find the class under its lookup contract |
| `NoClassDefFoundError` | The JVM needed a class that could not be resolved (or whose initialization previously failed); can also be caused by a mismatched class-file name |
| `ClassFormatError` | The bytes do not conform to the class file structure |
| `VerifyError` | The bytecode fails to satisfy verifier rules |
| `UnsupportedClassVersionError` | The class file version is newer than the runtime supports |
| `LinkageError` | Can be caused by duplicate class definition or loading constraints; not necessarily sealing |
| `IllegalAccessError` | JVM access/package/module rules forbid accessing the member/type |
| `ClassCastException` | Incompatible runtime types, commonly encountered across loader boundaries |
| `InaccessibleObjectException` | Deep reflection is restricted by JPMS/open package rules, not JAR sealing |
| `JarException` / `ZipException` | Archive/ZIP/JAR data errors, distinct from per-package signer consistency |

A single stack trace can contain multiple exception layers: read the **root cause** and loader progression. Do not “fix” `SecurityException` merely by adding a dependency to the classpath, and do not “fix” `ClassNotFoundException` by removing sealing when the class source has not even been found.

## 14. Is SecurityManager Involved?

Under **JEP 411**, `SecurityManager` was **deprecated for removal** starting in JDK 17; under **JEP 486**, it is **permanently disabled** starting in JDK 24. The rules for package namespaces, JAR sealing, and certificate consistency remain separate mechanisms of class loading/packaging.

Therefore:

- A `SecurityException` in the demo is reproduced on **JDK 24**, where `SecurityManager` cannot be enabled in the legacy model.
- `ProtectionDomain` and `CodeSource` still serve certain metadata/signer roles, but it should not be inferred that they automatically enable the legacy permission sandbox.
- Package sealing and signer checking **do not guarantee that a plugin is trustworthy or will not read files/network**.
- A separate `ClassLoader` provides runtime type/dependency isolation, **not a process/OS sandbox**.
- For untrusted plugin code, dedicated process/container/OS permissions, resource limits, and IPC contracts are required.

Security constraints in class loading are **different from** business-level authorization and OS privilege restrictions.

## 15. Verification Checklist for Plugin/JAR Builds

To avoid discovering errors in production:

- [ ] Each module/plugin has clearly owned package namespaces.
- [ ] Do not generate or relocate application classes into `java.*`.
- [ ] No sealed package is split across multiple JARs within the same loader.
- [ ] JAR-wide and per-package `Sealed` manifests are verified after building.
- [ ] The signer certificate set of classes in the same runtime package is consistent with policy.
- [ ] Unsigned plugin classes are not accidentally mixed into a vendor's signed package.
- [ ] JAR signing verification and trust checks are performed separately, rather than checking signer count alone.
- [ ] Parent delegation and plugin-private class isolation are verified.
- [ ] Tests cover multiple JARs sharing a package with different class names.
- [ ] Tests cover signer mismatches (in an isolated test environment) if the application uses signed JARs.
- [ ] Defining loader and code source are logged when class loading fails.
- [ ] `SecurityException` is never caught to silently fall back to a same-named class from an untrusted source.
- [ ] Tested on the actual target JDK, version, and module path.
- [ ] A package migration plan is in place rather than merely changing URL classpath order.

## 16. Self-Check Questions

**1. Two unsealed JARs each contain differently named classes in package `sample.api`. Will SecurityException automatically be thrown?** No; under the same loader, sharing a package does not itself cause a sealing violation. However, signer certificates or other constraints can still cause an error.

**2. What does `Sealed: true` in the main section mean?** It marks packages in the JAR as sealed by default, except for package-level overrides.

**3. Can you seal only `sample.api`?** Yes, by using an individual manifest section with `Name: sample/api/` and `Sealed: true`.

**4. `URLClassLoader` loads the first class from sealed JAR A and then a subsequent class in the same package from JAR B. What is the primary error?** A seal base/source consistency violation, typically throwing `SecurityException`.

**5. Signed JAR A and unsigned JAR B, sharing the same loader and package, both unsealed. Can SecurityException be thrown?** Yes, due to inconsistent certificate/signer sets.

**6. If both JARs are signed, is a mismatch guaranteed not to happen?** No. Classes in the same runtime package must have compatible/matching certificate sets as checked by the loader, not merely both be signed.

**7. `java.demo.Forbidden` is not in the standard JDK; can a custom loader define it on its own?** No; names beginning with `java.` are restricted by `defineClass`.

**8. Why is `child.loadClass("java.lang.String")` normally permitted?** The child delegates to receive the class defined by the appropriate platform loader rather than creating a class with that name itself.

**9. Does a SecurityException from sealing prove that SecurityManager is enabled?** No. This is an independent classloader/JAR check.

**10. Does separating two plugins into distinct loaders make classes in the same package belong to the same runtime package?** No. A runtime package also depends on the defining loader.

**11. Is `CodeSource.getLocation()` proof that a JAR is trustworthy?** No. It is source metadata; trust and integrity must be verified separately.

**12. If you use raw `defineClass` with bytes read from a JAR, does sealing take effect automatically?** Not by default; the custom loader must handle the package manifest and sealing policy appropriately.

## 17. Official References

- **Java SE 17 — `ClassLoader#defineClass`:** `SecurityException` checks when certificates are inconsistent or the name starts with `java.`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Java SE 17 — JAR File Specification, Package Sealing:** main/per-entry `Sealed` attributes and same-JAR rules: https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html
- **Java SE 17 — `URLClassLoader`:** loading classes from URLs/JARs and package metadata: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- **Java SE 17 — `Package.isSealed`:** package metadata: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Package.html
- **Java SE 17 — `CodeSource` / `ProtectionDomain`:** code source, certificates, and domain: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/CodeSource.html
- **Java SE 17 — `jarsigner` tool:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/jarsigner.html
- **JEP 411 and JEP 486:** https://openjdk.org/jeps/411 and https://openjdk.org/jeps/486

**Takeaway:** When encountering `SecurityException` in class loading, ask **is the error caused by manifest sealing, signer certificates, or the `java.*` namespace?** Sealing and signer consistency typically involve classes in **the same package defined by the same loader**; the reserved `java.*` package is a separate restriction in `defineClass`. Fix the actual root cause and verify the classloader, manifest, and signing policy — do not rely on SecurityManager or catch and suppress exceptions to hide errors.
