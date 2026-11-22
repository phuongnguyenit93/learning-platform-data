# JAR Signatures, Certificates, and Same-Package Consistency

## 1. The problem: same package, yet may not be loaded together

When a class loader loads classes from multiple JARs, the JVM and class loader care about more than just **class names** and **bytecode**. For signed JARs, there is also **digital signature** and **certificate** metadata associated with verified entries. For JARs with package sealing, there is also the constraint that **classes in the same package must come from a consistent JAR source** according to the sealing mechanism.

Example:

~~~text
plugin-a.jar (signed by signer A)
  com/example/shared/Alpha.class

plugin-b.jar (unsigned)
  com/example/shared/Beta.class

                 URLClassLoader L
                      |
             define com.example.shared.Alpha
                      |
          package certificate set = {A}
                      |
             define com.example.shared.Beta
                      |
            certificate set = {} -> mismatch
                      |
                SecurityException
~~~

This is the **fundamental scenario**: two classes are both attempted to be defined by **the same defining loader L** in **the same package**, but their certificate sets do not match. According to the Java 17 Javadoc for `ClassLoader.defineClass`, **the first class defined in a package establishes the exact set of certificates**; subsequent classes added to that package in the same loader must have **the same set** or a `SecurityException` may be thrown.

Another mechanism is **package sealing**: when a package is declared `Sealed: true` in the JAR manifest, a loader that processes manifest/sealing will not allow additional classes of the sealed package to be loaded from a different JAR code source. A violation can cause a `SecurityException`, even if both JARs are signed with the same certificate set.

**Do not conflate these three things:**

1. **JAR signature verification (integrity verification):** Are the bytes of the signed entries still consistent with the signature metadata?
2. **Signer trust decision (trust validation):** Is the signer/certificate trusted by the organization according to trust policy, chain, validity period, key usage, and appropriate conditions?
3. **Package consistency within a loader:** Do the certificates of classes in the same package match, and is package sealing violated?

All three are related, but they are **distinct checks**. A cryptographically valid signature does not automatically make a JAR "safe to execute," nor does it turn a self-signed certificate into a trusted identity.

## 2. Four foundational concepts

### 2.1. Binary class name and runtime package

Given the class:

~~~java
package com.example.shared;

public final class Alpha {}
~~~

`com.example.shared.Alpha` is the binary name; `com.example.shared` is the package name. At runtime, the JVM also considers the defining loader to determine the **runtime package**. Two classes with the same package name but defined by two different loaders **do not automatically belong to a single runtime package**.

This affects package-private access, type identity, and how package consistency is analyzed. The certificate set rule in `ClassLoader.defineClass` applies within **the scope of the loader/package that the loader defines**; it is not a JVM-wide certificate table shared across all loaders.

### 2.2. JAR signature and certificate

A JAR signed using the standard JAR signing mechanism may contain related data in `META-INF/`, such as the manifest `MANIFEST.MF`, signature file `.SF`, and signature block `.RSA`, `.DSA`, or `.EC` depending on the algorithm and tool.

`jarsigner` uses a private key to sign; signature verification checks the bytes/manifest digests according to the JAR mechanism. The certificate associated with the signer helps the verifier evaluate the signer's identity/public key according to its own policy.

Do not conflate:

- **Digest:** used to detect changes to the protected content.
- **Digital signature:** uses a private key to sign the relevant data; verification uses the public key.
- **Certificate:** binds a public key to identity information, and may be part of a certificate chain.
- **Trust:** the conclusion that a chain/signer is accepted based on the trust store, CA source, validity period, revocation, algorithms, timestamp, and application policy.

A JAR with a valid signature can still be malicious code if the signer is untrusted or if the code is valid yet dangerous. A package consistency check only compares **certificate sets**; it does not replace trust policy verification.

### 2.3. CodeSource

`java.security.CodeSource` represents the **code source location** (typically a URL) and associated certificate or code signer information. It can be associated with a `ProtectionDomain` when a class is defined.

Illustrative observation snippet:

~~~java
java.security.ProtectionDomain pd = SomeClass.class.getProtectionDomain();
java.security.CodeSource source =
        pd == null ? null : pd.getCodeSource();
System.out.println(source == null ? null : source.getLocation());
~~~

This is a **snippet inside a method**, where `SomeClass` is a real class. The location URL helps observe provenance, but it is **not sufficient** to prove a valid signature or a trusted publisher. There are runtime/protection domains where `CodeSource` does not provide complete information.

### 2.4. Package sealing

**Sealing** is a property of a **package**, typically read from the JAR manifest when the loader supports this mechanism. If a package is sealed, classes in that package must originate from a source matching the **seal base URL**, usually the same JAR. This is a source constraint, not a constraint on the equality of certificate sets.

`Package.isSealed()` and `Package.isSealed(URL)` can be used to inspect package information that a loader has defined, keeping in mind that `Package` objects and sealing are scoped to the specific loader and package-defining mechanism.

## 3. ClassLoader.defineClass requires a consistent certificate set

In Java SE 17, the key overload is:

~~~java
protected final Class<?> defineClass(
        String name,
        byte[] bytes,
        int offset,
        int length,
        java.security.ProtectionDomain domain)
~~~

`name` must be the **binary name** of the class file; if it does not match the internal name in the bytes, the JVM may throw `NoClassDefFoundError`. For a non-null `name`, the Javadoc states the rules:

- **The first class** defined in a package determines **the set of certificates** that subsequent classes in that package must use.
- Certificates are obtained from the `CodeSource` inside the class's `ProtectionDomain`.
- If another class in the same package in that loader has a different certificate set, defining it may throw **`SecurityException`**.
- The certificate set may be **empty** (unsigned), and unsigned versus signed is inconsistent.
- Names starting with `java.` have special restrictions on which loaders may define them; this rule is **independent** of JAR signatures.
- When calling `defineClass` directly, you should provide a **non-null binary name** so that the relevant checks are performed completely.

Diagram:

~~~text
Defining Loader L
   |
   +-- class p.First    CodeSource certificates = [cert A]
   |                    -> records signer set for p
   |
   +-- class p.Second   CodeSource certificates = [cert A]
   |                    -> consistent
   |
   +-- class p.Third    CodeSource certificates = []
                        -> SecurityException
~~~

**Loading order can change which class name gets "rejected"**: the first one defined in the package establishes the certificate set; the subsequent non-matching class is the one rejected. That does not mean the first loaded class is always trusted: the constraint only enforces **uniformity** within the same loader.

`defineClass(String, byte[], int, int)` (without an explicit `ProtectionDomain`) uses the default protection domain. Do not use that overload when you have **verified signer metadata** from different JARs and expect the JVM to know each entry's signer from the byte array alone.

## 4. Package sealing: same signer can still be rejected

A manifest can declare sealing for the entire JAR:

~~~text
Manifest-Version: 1.0
Sealed: true
~~~

Or only for a specific package:

~~~text
Manifest-Version: 1.0

Name: com/example/shared/
Sealed: true
~~~

Note that the manifest has explicit formatting and **blank-line** rules: the main section comes first, package sections start with `Name: .../`, and path names use `/`. Manual manifest editing must respect the JAR specification's encoding and line-folding rules.

If a `URLClassLoader` loads `com.example.shared.Alpha` from `sealed-a.jar` and defines the package with `sealed-a.jar` as the seal base URL, subsequently attempting to load `com.example.shared.Beta` in **the same loader/package** from `other.jar` can cause a **sealing violation**.

Key distinctions:

| Scenario | Certificate consistency | Package sealing |
| --- | --- | --- |
| Same signer certificates, different JARs, unsealed package | Valid with respect to certificates | Not blocked by sealing |
| Different signer/unsigned, same package and loader | May throw `SecurityException` | May be unsealed |
| Same signer, two JARs, package sealed in the first JAR | Certificate sets may match | May throw `SecurityException` due to different seal base |
| Two separate loaders, each defining the package itself | Each loader checks its own set | Each loader manages its own package/seal |
| A signed JAR containing an unsigned entry in the same package | May mismatch during define | Sealing is a separate check |

**Sealing does not perform trust verification**, and **signer equality does not replace sealing**. You should not work around sealing errors by stripping signature metadata or arbitrarily modifying third-party library manifests.

## 5. Java 17+ example: signing one JAR, loading alongside an unsigned JAR

The following example runs on **JDK 17+** using `javac`, `jar`, `keytool`, and `jarsigner`. It demonstrates real **certificate consistency** when a `URLClassLoader` attempts to define two classes in **the same package** from two JARs with different signing states.

This is a learning example using a **publicly shown demo keystore and password**; **do not use this key in production systems**. The self-signed certificate is only for creating test signatures; it does not represent an organizationally trusted certificate chain.

### 5.1. Source structure

Create the project:

~~~text
jar-signing-lab/
├── src/
│   ├── pack/
│   │   ├── A.java
│   │   └── B.java
│   └── SignatureBoundaryDemo.java
└── (output directories will be created in later steps)
~~~

File **src/pack/A.java**:

~~~java
package pack;

public final class A {
    public String name() {
        return "A";
    }
}
~~~

File **src/pack/B.java**:

~~~java
package pack;

public final class B {
    public String name() {
        return "B";
    }
}
~~~

Both classes belong to the same Java package `pack` but are packaged into **two different JARs**. They do not depend on each other.

### 5.2. Host file: src/SignatureBoundaryDemo.java

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class SignatureBoundaryDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: SignatureBoundaryDemo <signed.jar> <unsigned.jar>");
        }

        URL signed = Path.of(args[0]).toAbsolutePath().toUri().toURL();
        URL unsigned = Path.of(args[1]).toAbsolutePath().toUri().toURL();

        try (URLClassLoader loader = new URLClassLoader(
                new URL[] { signed, unsigned },
                ClassLoader.getPlatformClassLoader())) {

            Class<?> a = Class.forName("pack.A", false, loader);
            Object[] signers = a.getSigners();
            System.out.println("A loaded: " + (a != null));
            System.out.println("A signed: "
                    + (signers != null && signers.length > 0));

            try {
                Class.forName("pack.B", false, loader);
                System.out.println("B loaded: true");
            } catch (SecurityException mismatch) {
                System.out.println("B rejected: SecurityException");
            }
        }
    }
}
~~~

Because the host is run with only `host-out` on the classpath and the loader's parent is the **platform loader**, `pack.A` and `pack.B` are loaded from the two URLs within the scope of `URLClassLoader` in this exercise. `Class.forName(name, false, loader)` requests loading/linking via the API without eagerly running static initializers.

Interpret `a.getSigners()` within its proper scope: it observes signer information attached to the **already-defined Class**; it does not replace CA/certificate trust policy evaluation. The program intentionally prints only booleans rather than certificate strings that vary by environment.

### 5.3. Create output directories

On Linux/macOS with a compatible shell:

~~~bash
mkdir -p signed-out unsigned-out host-out
~~~

On Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force signed-out, unsigned-out, host-out | Out-Null
~~~

The remaining commands use JDK CLI tools and can be run in an appropriate terminal from inside the `jar-signing-lab` directory.

### 5.4. Compile and create the two JARs

~~~bash
javac --release 17 -d signed-out src/pack/A.java
javac --release 17 -d unsigned-out src/pack/B.java
javac --release 17 -d host-out src/SignatureBoundaryDemo.java

jar --create --file a-signed.jar -C signed-out .
jar --create --file b-unsigned.jar -C unsigned-out .
~~~

At this stage, `a-signed.jar` **is only a filename**; it **is not signed yet**. We will sign it in the next step. `b-unsigned.jar` is left unsigned.

### 5.5. Generate a test key/certificate

Run the following **single-line** command to avoid line-continuation syntax differences across shells:

~~~bash
keytool -genkeypair -alias demo -keyalg RSA -keysize 2048 -validity 365 -dname "CN=Training, OU=Demo, O=Example, L=Hanoi, ST=Hanoi, C=VN" -keystore training.p12 -storetype PKCS12 -storepass changeit -keypass changeit -noprompt
~~~

`keytool` generates a key pair and a self-signed certificate for testing purposes. The password `changeit` appearing directly in the example **is not how secrets should be managed in production**. Never commit real production keystores/private keys into a repository or shareable command history.

### 5.6. Sign JAR A

~~~bash
jarsigner -keystore training.p12 -storetype PKCS12 -storepass changeit -keypass changeit a-signed.jar demo
~~~

The tool may print warnings that the certificate is self-signed, has no timestamp, or is untrusted; that is an **intentional limitation of the demo**, not an expectation that any security policy should accept this signer.

To inspect verification output from the tool:

~~~bash
jarsigner -verify -verbose -certs a-signed.jar
~~~

`jarsigner` output may include algorithm details, signer names, warnings, timestamps, and statuses that vary by JDK. **Do not treat this command's stdout as a fixed snapshot**. `-strict` mode may return a non-zero exit code due to certificate warnings in this self-signed test, even though the JAR data has not been tampered with.

More importantly: `jarsigner -verify` checks the signature according to the tool's algorithms/rules; **it does not mean your organization trusts the certificate or has audited the code inside the JAR**.

### 5.7. Run the host demo

~~~bash
java -cp host-out SignatureBoundaryDemo a-signed.jar b-unsigned.jar
~~~

On a standard JDK 17+, with both JARs built properly and signer metadata verified, **the exact stdout of the program** is:

~~~text
A loaded: true
A signed: true
B rejected: SecurityException
~~~

Explanation:

1. `pack.A` comes from `a-signed.jar`, which has code signers attached to the class after the JAR entry is verified.
2. `URLClassLoader` defines `pack.A` in package `pack` with the test signer's certificate set.
3. When this loader tries to define `pack.B` from `b-unsigned.jar`, it is in the same package `pack` but has an empty certificate set, which no longer matches the established set.
4. `ClassLoader.defineClass` detects the package certificate mismatch and throws `SecurityException`; the demo catches that exact exception type to print the last line.
5. Java source `B` is valid, and `b-unsigned.jar` can also be opened/read normally. The issue is that **you cannot add Class B with a different certificate to the same package in the same defining loader**.

**This is not a package sealing demonstration.** The two JARs created with `jar --create` in this example do not declare `Sealed: true`; the error is caused by differing certificates, not the seal base.

### 5.8. Variant: separate class loaders

If `pack.A` is defined by loader L1 and `pack.B` by an independent loader L2, certificate consistency is checked separately within each loader's scope. Looking strictly at the same-package certificate rule, L1 and L2 **do not need equal signer sets**, because each loader has its own package definitions.

However, that **does not turn the two loaders into environments that can freely interchange all classes**: package-private access and runtime type identity differ, and host/plugin code can run into type errors when sharing APIs. Do not fix a certificate mismatch by splitting loaders if the architecture genuinely requires both classes to share the same runtime package for package-private member access.

## 6. Why can a signed JAR contain unsigned entries?

Signing a JAR does not always mean **every entry currently in the archive** is signed. New entries may be added after signing, or a manifest/signature may only protect specific entries; in that case, a mix of signed and unsigned entries can exist.

When a `JarFile` is opened in verification mode and the entry bytes have been read/checked, `JarEntry.getCodeSigners()` or `getCertificates()` provides information for **that entry** if present. If the entry is unsigned, the value may be null. If you retrieve metadata before finishing reading the verified entry, you cannot draw a definitive conclusion from that `null` alone.

For **multi-release JARs**, an entry targeting a specific Java version may have its own signature; the Java 17 `JarFile` Javadoc notes verifying the versioned entry's contents against that entry's own signature.

Implications for class loading:

- Check **each class entry individually** when determining signer/certificate consistency, rather than labeling all entries as "signed JAR."
- If a package already has a class with signer set A, an unsigned class in the same package within the same loader can cause a mismatch.
- Fat JAR building/repackaging can alter the entry list and signature metadata; you must not copy an old `META-INF` signature directory onto new bytes and assume the signature remains valid.
- **Do not automatically delete `.SF`/`.RSA` files** to "fix" verification or package certificate errors. Doing so destroys provenance evidence and may violate deployment policy.

## 7. Using JarFile to inspect entry signatures: read completely before checking

This Java 17+ example can be used as an auxiliary utility for the demo, but do not use it to conclude that a signer is trusted under enterprise policy.

Create **InspectEntry.java**:

~~~java
import java.io.InputStream;
import java.nio.file.Path;
import java.security.CodeSigner;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

public class InspectEntry {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: InspectEntry <jar-file> <entry-name>");
        }

        try (JarFile jar = new JarFile(Path.of(args[0]).toFile(), true)) {
            JarEntry entry = jar.getJarEntry(args[1]);
            if (entry == null) {
                throw new IllegalArgumentException(
                        "Entry missing: " + args[1]);
            }

            try (InputStream in = jar.getInputStream(entry)) {
                in.transferTo(java.io.OutputStream.nullOutputStream());
            }

            CodeSigner[] signers = entry.getCodeSigners();
            System.out.println("signed entry: "
                    + (signers != null && signers.length > 0));
        }
    }
}
~~~

Compile:

~~~bash
javac --release 17 InspectEntry.java
~~~

After creating and signing the two JARs in section 5:

~~~bash
java InspectEntry a-signed.jar pack/A.class
java InspectEntry b-unsigned.jar pack/B.class
~~~

**Stdout of each invocation** in the exact order above:

~~~text
signed entry: true
~~~

~~~text
signed entry: false
~~~

Notes:

- The `JarFile(file, true)` constructor enables verification; reading the entire entry stream is what provides the complete conditions to check the digest/signature for a signed entry.
- `getCodeSigners()` is JAR entry metadata after verification; **it does not confirm a trusted CA**.
- If the JAR has been modified such that signature validation fails, a `SecurityException` may be thrown while reading the entry; the helper does not swallow the error or print a misleading "false" result.
- For multi-release JARs, you must identify the exact versioned entry being inspected; do not generalize all versioned classes from a root entry.

## 8. CodeSource, ProtectionDomain, and custom ClassLoaders

A custom loader can call the overload:

~~~java
Class<?> type = defineClass(
        binaryName, classBytes, 0, classBytes.length,
        protectionDomain);
~~~

**This is an illustrative snippet inside a `ClassLoader` subclass**, without variable declarations or standalone runnable code.

Here:

- `binaryName` should reflect the real name in the classfile; you should not pass `null` to bypass name/certificate checks.
- `classBytes` must come from an approved source; having bytes does not prove the source is trustworthy.
- `protectionDomain` may contain a `CodeSource`, which holds the URL and signer/certificate information.
- Once a signed JAR has been properly verified, you must **preserve each entry's signer metadata** when defining the Class; never declare unsigned bytecode as signed.
- If you use the `defineClass(name, bytes, off, len)` overload without an appropriate `ProtectionDomain`, you may lose CodeSource/signers tracking that JAR-specialized loaders maintain.

Applications with custom loaders reading from the filesystem or custom storage must clearly define source provenance, signer verification, package sealing, classpath sharing, and error handling. **Do not build a "security shim" by fabricating a `CodeSource` with self-assigned certificates without actually verifying the bytes.**

`ProtectionDomain` and Java's `SecurityManager` are historical components of the Java security model. In JDK 17, the Security Manager is marked deprecated for removal; legacy permission models should not be treated as a default modern sandbox for untrusted code. Nevertheless, **package certificate consistency** in `defineClass` remains a JVM/JDK constraint governing class loading behavior and signer sets.

## 9. Certificate equality is not trust validation

Ask two separate questions:

**Question A: "Do the classes in this package have the same signer certificate set?"**

This is the concern of the `ClassLoader.defineClass` Javadoc. If `pack.A` has set A and `pack.B` has set B, compare **their respective certificate sets**, not merely text alias names like `demo`, JAR paths, or organization names.

**Question B: "Is this signer trusted to run code?"**

This is a trust/policy decision: whether the certificate chain validates to an accepted trust anchor, whether algorithms are sufficiently strong, whether signatures and timestamps are valid, whether certificates have the right key-usage scope, and whether the organization approves the publisher/artifact/hash.

Two JARs with the same certificate set **can** satisfy package signer consistency and still be code that is not permitted to run under enterprise policy. Conversely, two JARs from **two reputable CAs** may still not share **the same exact signer set**, and therefore cannot be mixed in the same package within one loader.

Do not confuse certificate chain display order with Java API equality rules; do not write business policy based on the string representation of `Certificate.toString()`. If pinning is required, use cryptographic APIs, fingerprints, and trust stores provided by an appropriate security library.

## 10. Sealing and package-info in a multi-JAR environment

`ClassLoader.definePackage` allows specifying metadata such as specification/implementation title, version, vendor, and seal base. When a loader reads a JAR manifest, loaders like `URLClassLoader` use that data to configure package properties.

The same package can appear in multiple JARs, with outcomes depending on:

- **Package sealing:** whether it is sealed, what the seal base URL is, and whether the package has already been defined.
- **Package certificate consistency:** which certificate set each Class defined by the loader carries.
- **Class loading order:** the first class can determine the package's certificate set and metadata/seal.
- **Package identity:** whether the classes share the same defining loader, or reside in different loaders.
- **Named modules:** JPMS package/module rules can add constraints; do not assume classpath/JAR sealing behaves identically with every custom named module layer.

The Java 17 Javadoc for `ClassLoader.definePackage` notes that loaders expecting accurate metadata from a JAR should call `definePackage` **before `defineClass`** if manifest/seal info needs to be supplied. If `defineClass` creates the Package first with default metadata, attempting to redefine package properties afterward is not a reliable design.

Do not use `getPackage(String)` (deprecated since Java 9) to conclude that a package was defined by the current loader itself: the old API can look up packages from ancestors. `getDefinedPackage(String)` is clearer when you want to inspect a package defined by **that specific loader**.

## 11. Suggestion for creating a separate sealed JAR for study

To study sealing **separately** from signatures, you can create two **unsigned** JARs with the same package `pack`:

~~~text
a-sealed.jar   : contains pack/A.class and manifest Sealed: true
b-unsigned.jar : contains pack/B.class
~~~

Sample manifest in `sealed.mf`:

~~~text
Manifest-Version: 1.0
Sealed: true
~~~

After compiling `pack.A` and `pack.B`:

~~~bash
jar --create --file a-sealed.jar --manifest sealed.mf -C signed-out .
~~~

`jar` can add/adjust the appropriate manifest metadata. When a `URLClassLoader` loads A from `a-sealed.jar` first, it defines package `pack` as sealed against that JAR's code source. If the same loader then loads B from `b-unsigned.jar`, class B can be rejected due to a **sealing violation**, even though both classes are unsigned and have identical certificate sets.

This is **an observational exercise based on the `SignatureBoundaryDemo` example**, where you change the arguments to `a-sealed.jar b-unsigned.jar` and inspect the runtime error type/stack trace. In that run, `A signed: ...` will be false while the final line reports `SecurityException`; the root cause is package sealing, not a certificate mismatch.

**Do not add `Sealed: true` to the signer example in section 5**, because running both checks at once can obscure the specific cause you are studying.

## 12. When can the same package name still be loaded from two JARs?

In the traditional classpath mechanism, a loader such as `URLClassLoader` can typically load class `p.A` from JAR 1 and `p.B` from JAR 2 if:

1. Both JARs are visible via the search URLs.
2. The package is not blocked by a sealing policy on the second source.
3. The certificate sets of the class entries are compatible under `defineClass`.
4. The class names/bytecode are valid and do not collide on duplicate definitions of the same binary name in the loader.
5. Related dependencies and loader constraints can be resolved.

For example, if both JARs are **unsigned** and the package is unsealed, they can usually be loaded together. However, this still carries risks around split packages, versioning, and build reproducibility. Do not treat "it loads" as proof that all APIs or security policies are sound.

If **the defining loaders differ**, mixing the same package name in source does not mean they share the same runtime package: package-private access and type identity can be incompatible. "Using another loader to get rid of SecurityException" can trade one error for many class isolation bugs.

In JPMS, **named modules** enforce different package/module ownership and readability checks. Split packages across named modules can be rejected by module resolution even if a similar classpath setup previously worked. Do not apply the conclusion "unsigned/unsealed => always works" to JPMS.

## 13. Common pitfalls in fat JARs, shading, and repackaging

### 13.1. Mixing signed and unsigned classes into the same package

A fat JAR builder may merge multiple dependency JARs, including signed JARs, into a single new JAR. If it preserves `META-INF` signature metadata intact while altering contents or the manifest, verification can fail. If it strips signatures without controlling provenance/trust policy, the artifact loses signer information; that is not "fixing" integrity.

**The right approach:** the build pipeline must have an explicit policy for signed input JARs, stripping/re-signing only under authorized circumstances, artifact attestation, and verification of the output. If bytes change, the original signature no longer attests to the new artifact.

### 13.2. Two versions of the same library sharing a package

If a class `com.example.Util` exists in two JARs, parent-first or wildcard classpath ordering can cause the loader to pick an unintended version. Sealing and signer checks can catch some mixing scenarios, but they are not a dependency version resolution system.

### 13.3. Split packages on the classpath

Two JARs both placing classes into `com.example.shared` constitute a split package in terms of source packaging. The traditional classpath can handle it if signers/sealing are consistent, yet it remains prone to conflicts. Named modules impose stricter constraints.

### 13.4. Duplicated annotations or APIs across loaders

Even if neither loader violates its own certificate set or sealing rules, a host and a plugin can define two separate copies of `shared.Api` with the same name. This causes runtime type errors and annotation mismatches. **Signer/sealing checks do not make two Classes from two defining loaders the same type.**

## 14. Diagnosing SecurityException properly

A `SecurityException` during class loading can stem from a package certificate mismatch, a sealing violation, restrictions on defining `java.*` packages, or other runtime rules.

Do not guess based solely on the word "security" in the exception. Collect:

1. **Full stack trace and message**, identifying whether the failure occurs in `URLClassLoader`, `ClassLoader.defineClass`, manifest/sealing, or JAR verification.
2. **Binary name** being loaded and package name, e.g., `pack.B` / `pack`.
3. **Defining loader identity**: is it the same loader that defined the earlier class in that package?
4. **Code source/JAR URL** of the class that loaded successfully, along with signer certificates if provided.
5. **Manifest**: is `Sealed: true` present in the main section or a per-package section?
6. **JAR signature metadata**: `jarsigner -verify -verbose -certs` for each input artifact; are there warnings about unsigned entries or self-signed certificates?
7. **Classpath/URL order**: which JAR provides the class first; are there duplicate JARs or versions?
8. **Build/repackaging steps**: did merging/shading/re-signing alter bytes or signature metadata?
9. **Runtime JPMS/module layer**: does this package belong to a named module, and is there a split package?
10. **Trust policy**: is the signer trusted by the organization, separate from signer equality checks?

Sample snippet for inspecting the `CodeSource` of a loaded class:

~~~java
static void inspect(Class<?> clazz) {
    java.security.ProtectionDomain pd = clazz.getProtectionDomain();
    java.security.CodeSource cs = pd == null ? null : pd.getCodeSource();
    System.out.println("class: " + clazz.getName());
    System.out.println("loader: " + clazz.getClassLoader());
    System.out.println("source: " +
            (cs == null ? "unknown" : cs.getLocation()));
    Object[] signers = clazz.getSigners();
    System.out.println("has signers: " +
            (signers != null && signers.length > 0));
}
~~~

This is an **illustrative snippet placed inside another class**, not a standalone program with `main`. When `CodeSource` is null or `getSigners()` is null, interpret it according to the loader and class-defining mechanism rather than concluding "the artifact is untrusted."

## 15. Appropriate inspection tools

| Tool/API | What it is used for | What it does not replace |
| --- | --- | --- |
| `jar --list --file x.jar` | List entries, locate class/manifest/signature files | Signer trust verification |
| `jar --describe-module --file x.jar` | View relevant descriptor/module info | Certificate consistency |
| `jarsigner -verify -verbose -certs x.jar` | Check signatures and signer info/warnings | Confirming code is harmless |
| `keytool -list -v -keystore store.p12` | Inspect certificates/aliases in a keystore | Checking every JAR entry |
| `JarFile(file, true)` + reading entire entry | Trigger signature verification for each signed entry read | Organizational CA trust policy |
| `JarEntry.getCodeSigners()` | Inspect signers after verification | Proving an artifact is safe |
| `Class.getSigners()` | Inspect signers of a runtime Class | Full chain/trust validation |
| `Package.isSealed()` | Check package sealing metadata | Certificate/trust verification |
| `Class.getProtectionDomain().getCodeSource()` | Class source and signer metadata if present | Proof that all permissions/certificates are valid |

To prevent regressions, CI/CD can record artifact checksums and validate them against release policy, verify JAR signing, check package layout, and test-load critical classes in a production-like environment.

## 16. Do not confuse certificate consistency with code permissions

In modern Java, runtime code can be governed by multiple distinct security mechanisms:

- **OS/process/container security**: file/network permissions and process isolation.
- **JPMS**: module readability, exports, opens, and package ownership.
- **ClassLoader**: type identity, delegation, and certain certificate consistency checks.
- **JAR signature**: archive/entry integrity and signer metadata.
- **Application trust policy**: publisher/artifact allowlists, certificate validation, artifact attestation, and process sandboxing when needed.

A class defined from a signed JAR **does not automatically receive special privileges**, nor is it blocked from reading files simply for lacking a signature. Do not use JAR signing or package sealing as a general sandbox to run untrusted plugins.

If you need to run untrusted third-party code, isolate it using OS processes/VMs/containers alongside OS policies and supply-chain controls. `ClassLoader` and signer metadata are one part of the picture, not the entire defense model.

## 17. Common misconceptions

| Misconception | What to remember |
| --- | --- |
| "Having a .RSA file means the whole JAR is definitely fully signed" | You must verify which entries are actually signed and match current bytes |
| "jarsigner verify succeeds => the signer is trusted" | Integrity verification is different from trust validation |
| "Two JARs from the same CA have the same signer set" | Exact certificate sets can differ even when issued by the same CA |
| "Same signer => a sealed package can be mixed across two JARs" | Sealing checks the seal base/JAR source |
| "Unsigned JAR => cannot contain Java classes" | Unsigned classes are valid in many applications |
| "Package certificate check applies JVM-wide" | Checked within the scope of the defining loader/package |
| "Two classes with the same package name are always one runtime package" | The defining loader is part of runtime package identity |
| "Deleting signature files fixes every error" | Can break integrity/provenance and violate policy |
| "CodeSource URL alone proves a file is trusted" | The URL is source metadata, not a trust decision |
| "If there is a package certificate mismatch, just catch the Exception" | `SecurityException` is a runtime error that requires fixing packaging/policy |
| "Sealing and signing are the same thing" | Sealing checks package source; signing checks integrity/signer metadata |
| "Custom defineClass bytes automatically infer the signer" | Verified metadata must be preserved via an appropriate CodeSource/ProtectionDomain |

## 18. Self-check exercises

**1. If within the same loader, package `p` has already defined a class with certificate set A, is a subsequent unsigned class in the same package valid?**  
No, under the `defineClass` rule when the sets do not match; it may throw `SecurityException`.

**2. Are two classes in the same source package but defined by two separate defining loaders subject to a single JVM-wide package certificate set?**  
No. Each loader has its own namespace/package definition, though loader constraints and access rules still apply.

**3. A package is sealed in JAR A; JAR B has the same signer and also contains that package. Can the same loader definitely load both?**  
No. If the source does not match the seal base, a sealing violation can occur.

**4. Why is `JarEntry.getCodeSigners()` sometimes null before reading entry bytes?**  
Because signature verification for an entry is performed while reading it; you must read the entry completely through a verified `JarFile` to obtain signer metadata.

**5. Does `jarsigner -verify` automatically decide whether the demo's self-signed certificate is trusted by your organization?**  
No. Trust policy is a separate step requiring evaluation of chains/anchors and system requirements.

**6. Can a new fat JAR reuse the original signature metadata of a repackaged JAR as-is?**  
No; changing bytes or the manifest typically invalidates old signatures or renders the signer metadata inaccurate.

**7. Does `Package.isSealed()` check digital signatures or the seal base?**  
It inspects the package's sealing property; it does not verify signer trust.

**8. Are two unsigned and unsealed JARs sharing a package guaranteed to always load together?**  
Not strictly; duplicate binary names, bytecode/linkage, class loaders, dependencies, and module rules still apply.

**9. Should you pass `null` as the binary name when calling `defineClass` directly to avoid signer consistency checks?**  
No. You should pass the proper name so the JVM performs name and certificate consistency checks.

**10. If the log only shows `SecurityException` with no clear cause, what is the first step?**  
Read the full stack trace/root cause, identify the class/package, loader, code source, and manifest; then distinguish between a signer mismatch and a sealing violation.

## 19. Official references

- Java SE 17 — **ClassLoader** (`defineClass` and exact certificate set rules within the same package): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 — **JarFile** (verified signed entries, signer metadata, and limits regarding certificate trust): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html
- Java SE 17 — **JarEntry** (`getCodeSigners`/`getCertificates`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarEntry.html
- Java SE 17 — **Package** (`isSealed`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Package.html
- Java SE 17 — **CodeSource**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/CodeSource.html
- Java SE 17 — **ProtectionDomain**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/ProtectionDomain.html
- Java SE 17 — **URLClassLoader**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- **JAR File Specification** (package sealing, signatures, and manifest): https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html
- Java SE 17 — **jarsigner command**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jarsigner.html
- Java SE 17 — **keytool command**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html
- JVM Specification Java 17 §5.3 — Creation and Loading (runtime package/defining loader): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3