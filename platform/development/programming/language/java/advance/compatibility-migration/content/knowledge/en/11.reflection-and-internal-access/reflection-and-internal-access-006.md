# Replacing Internal APIs with Standard APIs or Maintained Libraries

In a Java Advance Compatibility Migration project, code may run stably for years relying on classes or methods not guaranteed to be supported by Java SE, such as `sun.misc.Unsafe`, `sun.misc.BASE64Encoder`, `sun.security.x509`, `jdk.internal.reflect.*`, or `com.sun.org.apache.xerces.internal.*`. Those APIs are typically implementation details of a specific JDK version or JVM vendor. When upgrading the JDK, switching vendors, or enabling the JPMS module model, code using them may no longer compile, become inaccessible at runtime, or change behavior.

**Replacing internal APIs with standard APIs or maintained libraries** is the process of identifying code that depends on unstable interfaces, understanding the actual requirement of that code, and then migrating to public APIs with explicit support contracts or maintained third-party dependencies. The goal is not merely to eliminate compiler warnings, but to **reduce reliance on JDK implementation details**, preserve the application's observable contracts, and ensure future upgrades remain manageable.

The lesson is framed in the context of **Reflection and Internal APIs**: why Java 9+ changes access mechanisms, how to investigate hidden dependencies, common API migration examples, criteria for selecting replacement libraries, testing approaches, and the acceptable scope for bypass options during migration.

## 1. Properly Identifying Internal APIs, Standard APIs, and Removed APIs

You should not decide whether an API is supported based solely on its package name. In Java, there are several distinct groups:

| Group | Examples | Compatibility |
|---|---|---|
| Java SE public APIs | `java.util.Base64`, `java.util.concurrent.atomic.AtomicLong`, `java.lang.invoke.VarHandle` | Have platform specifications, documentation, and compatibility policies |
| Public APIs of a specific JDK/vendor | Certain `com.sun.*` APIs or officially documented extension tools | May be supported within a specific JDK/vendor scope, but not portable by default |
| JDK internal APIs | `jdk.internal.*`, many `sun.*`, `com.sun.*.internal.*` | No stable Java SE API guarantee; may be encapsulated or changed |
| Deprecated public APIs | Methods/classes annotated with `@Deprecated` | May still be supported; read specific deprecation notices and removal plans |
| Removed APIs/modules | Certain Java EE/CORBA modules formerly bundled with older JDKs | Need replacement dependencies/APIs; distinct from JPMS encapsulation errors |
| Third-party APIs | ASM, Byte Buddy, XML, JSON, crypto libraries | Support matrix and lifecycle defined by library maintainers |

### 1.1. Package Names Are Not Absolute Proof

- Not everything under `com.sun` is an internal API, and not everything under `javax` is a public API of every JDK.
- A package exported by a module does not automatically mean every API inside is a stable Java SE interface.
- A Java-language `public` API can still reside in a package not exported by its module to other code.
- A class still existing inside the JDK image does not mean applications are permitted to link directly to it.

To evaluate, inspect official API documentation, the module containing the package, export/open status, release notes, compiler warnings, and dependency analysis results on the exact target JDK.

### 1.2. Do Not Equate Deprecated with Internal

`@Deprecated` is a signal about a public API's lifecycle; it does not by itself mean the API has been deleted or cannot be used. An internal API may **have no deprecated annotation at all** yet still be unsupported. Conversely, a deprecated public API can still be a more stable migration path than a reflection hack into a private JVM field.

Distinguish at least three questions:

1. Is the API public and specified for consumers?
2. Is the API deprecated, version-restricted, or scheduled for removal?
3. Does your code use it in a standard way or by bypassing encapsulation?

The handling differs: an internal API needs its dependency path replaced; a deprecated public API requires evaluating timelines and successor APIs; a still-working public API accessed via unnecessary reflection can be replaced with a direct call.

## 2. Why Does Java 9+ Migration Expose These Issues?

Since Java 9, the **Java Platform Module System (JPMS)** organizes the JDK into named modules and enforces readability, exports, and opens rules. Internal packages that could previously be used on the classpath of certain older JDKs are no longer accessible by default.

Key milestones:

- **JDK 9:** introduced JPMS into the JDK, beginning the phase of tightening internal access while providing transition tools and options.
- **JDK 16:** defaulted to stricter encapsulation mechanisms compared to many Java 9–15 stages.
- **JDK 17:** strong encapsulation of JDK internals was tightened under JEP 403. The `--illegal-access` option is no longer an effective mechanism for granting broad access as in earlier releases.
- Some internal APIs remain specially supported by certain components, such as the `sun.misc.Unsafe` group via the `jdk.unsupported` module, but this **does not turn them into stable Java SE APIs**.

Two distinct errors are commonly encountered:

**Compile-time access error** when code imports a non-exported package:

~~~text
package jdk.internal.misc is not visible
(package jdk.internal.misc is declared in module java.base,
 which does not export it to the unnamed module)
~~~

**Runtime reflection error** when code attempts to call `setAccessible(true)` on a member belonging to a module that does not open the corresponding package:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make ... accessible:
module java.base does not "opens java.lang" to unnamed module ...
~~~

A sustainable fix must be based on the goal the code is trying to achieve, not merely adding flags to silence the error.

## 3. Inventorying Where the Project Uses Internal APIs

Before replacing them, identify both direct dependencies and indirect usage. Internal APIs may reside in main source code, tests, build tools, generated code, agents/profilers, or transitive dependencies.

### 3.1. Using jdeps to Find Dependencies on JDK Internal APIs

For a built JAR, you can use:

~~~bash
jdeps --jdk-internals app.jar
~~~

If the JAR needs other dependencies for complete analysis:

~~~bash
jdeps \
  --class-path "lib/*" \
  --jdk-internals \
  app.jar
~~~

For a multi-release JAR, specify the view matching the JDK to inspect:

~~~bash
jdeps \
  --multi-release 17 \
  --jdk-internals \
  --class-path "lib/*" \
  app.jar
~~~

`jdeps` analyzes static dependencies from class files. It typically detects references such as:

~~~text
com.example.FastAccess -> sun.misc.Unsafe          JDK internal API
com.example.CertificateUtil -> sun.security.x509   JDK internal API
~~~

Results must be interpreted according to the JDK and tool version. A warning does not by itself prove the application is already broken, yet it is evidence that the code relies on risky APIs. Conversely, a clean scan **does not prove complete freedom from internal APIs**, because string-based reflection and dynamic class loading may go undetected by the tool.

### 3.2. Searching for Imports, String-Based Reflection, and Unusual Access Methods

You can search in the repository:

~~~bash
rg -n --glob '*.java' \
  'import (sun\.|com\.sun\.|jdk\.internal\.)' .

rg -n --glob '*.java' \
  'Class\.forName|setAccessible|trySetAccessible|privateLookupIn|getDeclaredField|getDeclaredMethod|Unsafe|defineClass' .
~~~

Search further in configuration files:

~~~bash
rg -n --hidden -g '!**/.git/**' \
  'jdk\.internal|sun\.misc|sun\.security|--add-opens|--add-exports|--illegal-access|JAVA_TOOL_OPTIONS|JDK_JAVA_OPTIONS' .
~~~

These are **search heuristics**, not a complete analyzer. A codebase may call `Class.forName` with dynamically concatenated class names or names read from YAML, XML, annotations, databases, or service descriptors. Libraries may load implementations via reflection without the project's source importing any internal class.

If the project uses multiple modules, run analysis on the actual release artifacts, not just the source of a single module. Inspect both bytecode inside published JARs and the actually resolved runtime dependencies.

### 3.3. Combining jdeprscan to Distinguish Deprecated Public APIs

Example:

~~~bash
jdeprscan --release 17 app.jar
~~~

`jdeprscan` helps find references to Java SE APIs deprecated in the selected release. It answers a **different** question from `jdeps --jdk-internals`: deprecated public APIs are not identical to JDK internal APIs. Combining both sources prevents the team from mistreating two distinct kinds of risk as the same.

### 3.4. Using Runtime Logs and Stack Traces

When running the application on the target JDK, capture full exceptions and class loading paths. Errors to distinguish include:

| Error | Common Cause | What to Check |
|---|---|---|
| `InaccessibleObjectException` | Deep reflection into an unopened package | Module/package owner, reflection API, feasibility of removing reflection |
| `IllegalAccessError` | Bytecode accesses a forbidden type/member | Export rules, actually loaded class/module |
| `NoClassDefFoundError` | Class does not exist at runtime or class initialization failed | Artifact, class loader, root cause |
| `ClassNotFoundException` | Dynamic lookup cannot find the class | Class name, classpath/module path, vendor |
| `NoSuchMethodError` | Bytecode calls a method no longer present in the runtime class | Dependency version and method descriptor |
| `UnsupportedClassVersionError` | Class-file version is higher than the JVM supports | JDK runtime and major/minor version |
| `ExceptionInInitializerError` | Static initialization failed, possibly due to internals or configuration | Underlying cause and stack trace |

Do not automatically add `--add-opens` for every error. For example, `NoSuchMethodError` is usually related to binary compatibility or dependency versions, not JPMS access.

## 4. Categorizing Usage by Actual Need

Before modifying an internal call, ask: **what result** does the code need that the API is currently providing?

| Actual Need | Common Legacy Approach | Preferred Replacement |
|---|---|---|
| Base64 encode/decode | `sun.misc.BASE64Encoder` / `BASE64Decoder` | `java.util.Base64` |
| Atomic counter / compare-and-set | Direct `sun.misc.Unsafe` | `AtomicInteger`, `AtomicLong`, `VarHandle` |
| Direct byte/buffer access | Unsafe / internal ByteBuffer fields | `ByteBuffer`, `FileChannel`, or public memory APIs appropriate for the JDK |
| Inspecting class/method properties | Reflection into internal metadata | `java.lang.Class`, `java.lang.reflect`, `java.lang.invoke` |
| Dynamic class creation/definition | Reflection on `ClassLoader#defineClass` or internal APIs | Appropriate `MethodHandles.Lookup` APIs, `java.lang.instrument`, maintained bytecode tools |
| Reading XML | JDK-internal Xerces implementation | `javax.xml.parsers`, `org.w3c.dom`, `javax.xml.transform` |
| Using security algorithms | Concrete JDK-internal providers | `java.security`, `javax.crypto`, maintained providers |
| Generating/modifying X.509 | `sun.security.x509` | Public APIs if sufficient for the use case; if certificates must be generated, use a crypto library with a support matrix |
| Bytecode transformation | ASM embedded inside the JDK | Maintained ASM/Byte Buddy artifacts with explicitly pinned versions |
| Catching OS signals | `sun.misc.Signal` | Shutdown hook/lifecycle API when semantics fit; OS mechanism or dedicated library if specific signal handling is required |

A public API may not be capable of replacing every internal operation 1:1. For example, `VarHandle` solves many memory-ordered variable accesses and atomic operations, yet does not automatically replace every native memory allocation or dynamic class definition use case from `Unsafe`. Separate the requirements rather than applying a single recipe to every occurrence of a class name.

## 5. Example: sun.misc.BASE64Encoder to java.util.Base64

This is a straightforward conversion, yet encoding and line-break semantics still need to be preserved.

### 5.1. Legacy Approach

In code running on some older JDKs:

~~~java
import sun.misc.BASE64Encoder;

import java.nio.charset.StandardCharsets;

public class TokenEncoder {
    public String encode(String value) {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        return new BASE64Encoder().encode(bytes);
    }
}
~~~

`sun.misc.BASE64Encoder` is an internal API and should not continue to be used in target code on newer JDKs.

### 5.2. New Approach Using the Standard API

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class TokenEncoder {
    public String encode(String value) {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        return Base64.getEncoder().encodeToString(bytes);
    }

    public String decode(String encoded) {
        byte[] decoded = Base64.getDecoder().decode(encoded);
        return new String(decoded, StandardCharsets.UTF_8);
    }
}
~~~

`java.util.Base64` has existed since Java 8 and provides encoder/decoder variants following different conventions:

- `getEncoder()` and `getDecoder()` for basic Base64.
- `getUrlEncoder()` and `getUrlDecoder()` for the URL-safe variant.
- `getMimeEncoder()` and `getMimeDecoder()` for MIME rules with appropriate line handling.

Do not pick a variant just because they all generate valid-looking strings. Legacy code might insert line breaks after a certain number of characters or accept whitespace differently. Such discrepancies can affect files, protocols, tokens, or digital signatures.

### 5.3. Verifying the Contract

Example test design:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

class TokenEncoderTest {
    @Test
    void roundTripUtf8() {
        String original = "Xin chào Java";
        String encoded = Base64.getEncoder()
                .encodeToString(original.getBytes(StandardCharsets.UTF_8));

        String decoded = new String(
                Base64.getDecoder().decode(encoded),
                StandardCharsets.UTF_8
        );

        assertEquals(original, decoded);
    }

    @Test
    void basicEncoderDoesNotInsertLineBreaks() {
        byte[] data = new byte[100];
        String result = Base64.getEncoder().encodeToString(data);
        assertFalse(result.contains("\n"));
        assertFalse(result.contains("\r"));
    }
}
~~~

If data from legacy systems is still being read, test compatibility with real fixtures: legacy Base64 outputs, padded/unpadded inputs, whitespace, binary data, empty values, and Unicode strings. You may need to choose the MIME decoder or add a data normalization layer if the legacy contract genuinely permits whitespace. Do not loosen the parser by default if the data belongs to a security context.

## 6. Example: Using AtomicLong or VarHandle Instead of Unsafe

`sun.misc.Unsafe` is commonly used to access fields by offset, perform compare-and-swap, read/write with specific memory ordering, or manipulate off-heap memory. Some capabilities have clear public API replacements, while others require redesign.

### 6.1. For an Atomic Counter, Prefer AtomicLong

Instead of obtaining a field offset and calling the Unsafe API, use:

~~~java
import java.util.concurrent.atomic.AtomicLong;

public final class SequenceGenerator {
    private final AtomicLong next = new AtomicLong();

    public long allocate() {
        return next.getAndIncrement();
    }

    public long current() {
        return next.get();
    }
}
~~~

This standard API has clear semantics, avoids depending on object layout, and does not require code to access the Unsafe singleton via reflection. However, when migrating from Unsafe to AtomicLong, check the semantics: which method returns the value before/after increment, overflow behavior, visibility, atomicity, and performance requirements.

### 6.2. For Specific Fields, Use VarHandle When Appropriate

`VarHandle` belongs to `java.lang.invoke` since Java 9, supporting various variable access operations with well-defined memory ordering.

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public final class Counter {
    private volatile long value;

    private static final VarHandle VALUE;

    static {
        try {
            VALUE = MethodHandles.lookup()
                    .findVarHandle(Counter.class, "value", long.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public long incrementAndGetOldValue() {
        return (long) VALUE.getAndAdd(this, 1L);
    }

    public long current() {
        return (long) VALUE.getVolatile(this);
    }
}
~~~

In the example, `MethodHandles.lookup()` is called from the code of the class owning the field itself, so it has appropriate access to find that private field. Do not infer that this lookup can read every private field of every JDK class.

`getAndAdd` returns the previous value; `getVolatile` reads with volatile semantics. When replacing an Unsafe operation with VarHandle, choose the exact access mode for memory ordering rather than just picking a method with a similar name. The plain, opaque, acquire/release, and volatile modes do not have identical memory constraints.

### 6.3. Cases That Cannot Be Replaced Mechanically

The following use cases require dedicated design and verification:

- Native memory allocation/deallocation: may require `ByteBuffer.allocateDirect`, or the public Foreign Function & Memory API on supporting JDKs such as JDK 22+, depending on lifecycle requirements and the runtime baseline.
- File mapping and IO: consider `FileChannel`, `MappedByteBuffer`, or an appropriate memory API.
- Generating/defining bytecode classes: examine the package, class loader, module, lifetime, and class-definition API.
- Complex lock-free optimizations: ensure linearizability, happens-before, publication, and concurrency testing.
- Serialization frameworks or runtime agents: usually it is better to upgrade to a maintained dependency rather than manually patching Unsafe call sites inside them.

Do not downgrade bytecode or open `jdk.internal.misc` as a default solution; JVM layout, GC, and memory safety are areas with very high risk of behavioral change.

## 7. Replacing Deep Reflection into JDK Internals

### 7.1. Common Errors with setAccessible

Example of a snippet reading an implementation detail of `String`:

~~~java
import java.lang.reflect.Field;

public class UnsafeStringInspector {
    public static Object readBackingStorage(String text) throws Exception {
        Field field = String.class.getDeclaredField("value");
        field.setAccessible(true);
        return field.get(text);
    }
}
~~~

This approach carries many risks:

- Package `java.lang` belongs to module `java.base` and is not open by default to external code for deep reflection on modern JDKs.
- The private field of `String` is an implementation detail and may change type or meaning across JDKs.
- The result is internal storage, **not a public contract** for processing characters or bytes.
- The runtime may throw `InaccessibleObjectException` or run into issues when switching vendors.

If you need a **character array** for text processing, use `String.toCharArray()` or `CharSequence`. If you need **bytes in a specific charset**, use `String.getBytes(StandardCharsets.UTF_8)`. If you need to check Unicode character lengths and positions, distinguish UTF-16 code units, code points, and grapheme clusters. Do not use private fields as shortcuts when the code's intent has not been clarified.

### 7.2. Public Reflection Remains a Standard API

Not all reflection needs to be removed. Java provides public APIs:

~~~java
import java.lang.reflect.Method;

public class PublicMethodLookup {
    public static Method findRunMethod(Class<?> type)
            throws NoSuchMethodException {
        return type.getMethod("run");
    }
}
~~~

`Class.getMethod` looks up public methods according to reflection rules. For APIs that a library commits to supporting and whose packages/modules are accessible, public reflection can be a legitimate choice, especially in frameworks/plugins.

What must be avoided is using reflection to bypass access permissions into private members not owned by your code or into an unopened JDK package.

### 7.3. When Code Owns a Module and Needs to Allow Framework Reflection

For applications written as modules where a framework needs deep reflection on the application's entities, a long-term solution may be opening **your exact package** to the **exact framework module**:

~~~java
module com.example.orders {
    requires com.example.framework;

    opens com.example.orders.model to com.example.framework;
}
~~~

This is completely different from opening private JDK packages to the entire classpath. When a framework genuinely needs deep reflection, declaring `opens` inside a module you manage is a clearer contract than a hidden JVM option in a startup script.

If the framework sits on the classpath or uses a specialized class loader, access rules and target module names must be verified for the specific deployment. Opening packages is only part of it: the framework must also support the new JDK, annotations, and serialization semantics.

### 7.4. MethodHandles Is Not a Free Bypass

`java.lang.invoke.MethodHandles` provides ways to look up and invoke methods/fields with explicit access checking. `MethodHandles.privateLookupIn` can be used when the caller has appropriate permissions and the module containing the target package permits corresponding deep reflection. It does **not** automatically disable JPMS strong encapsulation.

For example, if an application component needs controlled internal access, you can place the logic inside the module owning the member itself, expose a public API, or declare a narrowly scoped package open. Do not replace a `setAccessible(true)` call with `privateLookupIn` and assume access errors will disappear.

## 8. Other JDK Internal API Groups and Replacement Options

### 8.1. XML: Avoid JDK-Internal Parser Implementations

If code imports classes from `com.sun.org.apache.xerces.internal.*` or an embedded JDK parser implementation, you can use the standard Java SE API:

~~~java
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;
import java.io.InputStream;

public final class XmlDocuments {
    public static Document parse(InputStream input) throws Exception {
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();

        factory.setFeature(
            "http://apache.org/xml/features/disallow-doctype-decl", true
        );
        factory.setExpandEntityReferences(false);

        return factory.newDocumentBuilder().parse(input);
    }
}
~~~

This is an example using the public factory API; XML parser security configuration must be chosen according to needs. Specific features such as the URI feature in the example may be implementation-dependent; verify that the actual parser supports them and fails safely when security features are not applied. Do not copy a few parser flags and conclude that XML parsing is immune to every form of XML External Entity (XXE) or DoS attack.

When Xerces-specific capabilities are needed, use a maintained Xerces artifact with explicitly managed dependencies instead of importing the JDK-embedded internal implementation. Check namespaces, serialization, and external entity handling on the exact parser/version.

### 8.2. Cryptography and Providers

If code references concrete implementations in `com.sun.crypto.provider.*` or `sun.security.*`, use the Java Cryptography Architecture (JCA/JCE), such as:

~~~java
import javax.crypto.Cipher;

public final class CryptoFactory {
    public static Cipher aesGcmCipher() throws Exception {
        return Cipher.getInstance("AES/GCM/NoPadding");
    }
}
~~~

This is an example of obtaining an instance via the standard API, **not a complete encryption example**. Real encryption requires keys, IV/nonce, tag sizes, key management, and protection against nonce reuse. The public API solves decoupling consumers from implementation classes, but does not by itself guarantee secure cryptographic configuration.

If the environment requires a specific provider or FIPS, explicitly document the allowed provider list, algorithm choices, and test on the target JDK/vendor/runtime. Do not assume all providers share the same implementation or input handling.

### 8.3. X.509: Distinguishing Certificate Handling from Certificate Issuance

To **read** X.509 certificates and validate chains according to your use case, Java SE provides `CertificateFactory`, `KeyStore`, `CertPathValidator`, and `SSLContext`. Example of reading a certificate:

~~~java
import java.io.InputStream;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

public final class Certificates {
    public static X509Certificate readX509(InputStream input)
            throws Exception {
        CertificateFactory factory = CertificateFactory.getInstance("X.509");
        return (X509Certificate) factory.generateCertificate(input);
    }
}
~~~

However, if legacy code uses `sun.security.x509` to **issue or sign** certificates directly, the Java SE public API does not directly provide all the builders required for that workflow. Consider a maintained crypto library such as Bouncy Castle, a PKI service, a supported CA tool, or redesigning how certificates are provisioned.

Preserve subject, issuer, SAN, key usage, extended key usage, validity, chain building, and trust semantics per the real contract. Compiling without errors after switching libraries does not prove that the new certificates will be accepted by clients.

### 8.4. Bytecode Manipulation: Removing Reliance on JDK-Embedded ASM

Some legacy frameworks/agents import `jdk.internal.org.objectweb.asm.*` or private implementation packages inside the JDK. Those are not stable public ASM APIs for applications.

Options:
- Use the official **ASM** artifact matching the class-file version produced by the target JDK.
- Use **Byte Buddy** or a maintained instrumentation library when bytecode manipulation logic operates at a higher level.
- If only the Java agent lifecycle is needed, rely on the public `java.lang.instrument` API and compatible bytecode dependencies.

Pin versions and check the library's support matrix rather than specifying "use the latest version" in an irreproducible build. Newer bytecode may introduce class-file attributes, constant pool tags, or features that older libraries do not understand. Test class loading, verification, stack map frames, instrumentation, and rollback on startup.

### 8.5. Dynamic Class Definition

If legacy code uses reflection on `ClassLoader#defineClass` or internal APIs to define classes from a byte array, examine **which package/module the class belongs to**, **which class loader owns it**, **what its lifetime is**, and **whether the class needs to be discoverable by name**.

Replacement directions:
- `MethodHandles.Lookup#defineClass` when the bytecode has a binary name in a package matching the lookup class.
- `MethodHandles.Lookup#defineHiddenClass` for certain dynamically generated runtime classes, following the hidden class model on supporting JDKs.
- A subclass of `ClassLoader` using protected APIs with proper boundaries and lifecycle when the use case requires it.
- Bytecode/instrumentation libraries that support the target JDK.

The options above are **not drop-in replacements**. Hidden classes do not share the same name-lookup characteristics as ordinary classes; lookups are subject to access/module constraints; custom class loaders affect identity, security, resource lifecycle, and leaks. Therefore, test Class.forName, reflection, dependency injection, serialization, and unloading if the use case requires them.

### 8.6. sun.misc.Signal

If code catches `sun.misc.Signal` to clean up resources when a process exits, you can consider `Runtime.getRuntime().addShutdownHook(...)` or framework lifecycle hooks:

~~~java
public final class ShutdownLifecycle {
    public static void install() {
        Runtime.getRuntime().addShutdownHook(
            new Thread(() -> System.out.println("Shutting down"))
        );
    }
}
~~~

A shutdown hook does not fully replace every OS signal handling mechanism: it is not guaranteed to run when a process is forcefully terminated, suffers a severe native crash, or in any strict shutdown order. If the system genuinely needs to handle a specific signal with well-defined semantics, design around the OS/process manager or use a supported library/platform API rather than claiming a shutdown hook is a 1:1 equivalent.

## 9. When Should You Choose a Maintained Third-Party Library?

Not every required capability is provided by Java SE as a convenient public API. Choosing a maintained library can be safer than writing your own parser, bytecode emitter, certificate builder, or network protocol stack.

However, replacing a dependency is a new operational commitment. You need to evaluate:

| Criterion | Specific Questions |
|---|---|
| Java baseline | Does the new library support the lowest JDK committed to by the product? |
| Maintenance | Are there regular releases, bug fixes, security patches, and a reasonable disclosure process? |
| Compatibility | Do the API/ABI versions and behavior match the legacy code's contract? |
| Dependency graph | Does it pull in additional artifacts, native libraries, split packages, or conflicting versions? |
| License | Are the license and distribution requirements suitable for the product? |
| Security | Are there known vulnerabilities and supported patches? |
| Modularity | Does it work on the classpath, module path, custom images, and inside containers? |
| Performance | Are allocation, memory, latency, and throughput acceptable? |
| Operations | Are metrics/logging/debugging and upgradability available? |
| Exit strategy | Can the library be swapped out later without modifying all business code? |

Do not assume "third-party library" means "maintained." Some legacy libraries merely wrap internal APIs and do not yet support newer JDKs. Verify the exact artifact version being placed into the runtime, including transitive dependencies.

### 9.1. Creating Abstractions to Avoid Locking In Business Code

Instead of letting every module call internal APIs or replacement library APIs directly, you can define an interface tailored to the domain's needs:

~~~java
public interface TokenCodec {
    String encode(byte[] data);
    byte[] decode(String value);
}
~~~

Implementation using the standard API:

~~~java
import java.util.Base64;

public final class StandardBase64Codec implements TokenCodec {
    @Override
    public String encode(byte[] data) {
        return Base64.getEncoder().encodeToString(data);
    }

    @Override
    public byte[] decode(String value) {
        return Base64.getDecoder().decode(value);
    }
}
~~~

If the legacy system had a specific encoding variant, the abstraction allows adding a separately tested compatibility adapter. This is an intentional wrapper layer; you should not create abstractions around every simple Java SE call merely out of general principle.

### 9.2. Pinning Versions and Tracking Dependencies

In Gradle or Maven, use the artifact/version selected based on the support matrix; manage versions via catalogs/BOMs/dependency management following project conventions.

Illustrative example, without assigning a fake version as if it were verified:

~~~groovy
dependencies {
    implementation("org.ow2.asm:asm:<compatible-pinned-version>")
}
~~~

Similarly, certificate or instrumentation libraries must have locked versions and be updated according to project policy. Avoid uncontrolled dynamic versions in release pipelines. After upgrading, verify the class-file version and the actual dependency graph of the resolved artifacts.

## 10. The --add-opens and --add-exports Options Are Only Transitional Solutions

JPMS permits certain options that adjust access at launch time:

~~~bash
java \
  --add-opens java.base/java.lang=ALL-UNNAMED \
  -jar legacy-app.jar
~~~

This example option opens `java.base`'s `java.lang` package for deep reflection from unnamed modules. It can help an un-updated legacy library run in the short term, yet it also grants very broad permissions. It should not become a default production configuration merely because a stack trace mentions `InaccessibleObjectException`.

Another example of temporary exports:

~~~bash
java \
  --add-exports java.base/jdk.internal.misc=ALL-UNNAMED \
  -jar legacy-app.jar
~~~

`--add-exports` enables access to APIs of non-exported packages across module boundaries, while `--add-opens` serves runtime deep reflection into packages. For compile-time access, the compiler may need corresponding options for code importing internal packages. These options do not guarantee that symbols still exist, signatures remain unchanged, or semantics are preserved.

**Simply adding flags does not fix the problem.** It alters the process's module-access policy, which can mask the risk of unreplaced internal APIs.

### 10.1. How to Manage Exceptions

For each flag, record:

- Affected process/task and JDK vendor/version.
- Opened or exported module/package, and the module granted permission.
- Stack trace or failure case making the flag necessary.
- Library/source file requesting access.
- Owner and target library version to eliminate the bypass.
- Tests proving the flag is still needed and tests used to confirm removal of the flag.
- Review deadline or specific migration milestone.

Replace `ALL-UNNAMED` with a specific module name when the architecture allows it. In cases where the package belongs to **the application's own module**, prefer editing module-info.java with `exports`/`opens` scoped as needed. For private JDK fields, the long-term direction remains eliminating dependence on implementation details.

### 10.2. Avoid --illegal-access in New Migration Plans

Workflows from Java 9–15 may have used `--illegal-access=permit` or similar modes to defer fixing reflection. On JDK 17, this mechanism no longer opens the entire JDK as before. Do not use it as a substitute for updating frameworks and fixing internal API calls.

## 11. Controlled Migration Process

A large change should be broken down by need, risk, and verifiability, rather than finding/replacing every internal package name all at once.

### Step 1: Lock In the JDK and Runtime Floor

Record the JDK versions that must be supported (for example, lowest product runtime, build JDK, production JDK), vendor, and deployment method. Standard APIs such as VarHandle or the Foreign Function & Memory API can only be used if the target runtime supports the required version. Do not choose Java APIs newer than the runtime floor the product still declares it supports.

### Step 2: Build an Inventory

Use `jdeps --jdk-internals`, source/config searches, and runtime logs to record:
- Class/module or JAR using internal APIs.
- API being called and its true purpose.
- Usage frequency, code path, and owner.
- Feasibility of replacing with a public API or maintained dependency.
- Actual warnings and errors on the target JDK.
- Criticality level and semantics preservation requirements.

Distinguish your own code, generated code, direct dependencies, and transitive dependencies. Modifying application source code does not automatically fix a third-party library dependency that internally bundles those calls.

### Step 3: Choose the Handling Approach

Based on the nature of the need:

1. A public Java SE API satisfies the need: prefer the standard API.
2. Public API is insufficient: consider a maintained library.
3. The need depends on a non-portable runtime mechanism: consider redesigning, creating an adapter, or moving the capability to a process/service with an explicit contract.
4. Cannot be replaced immediately: use minimally scoped, time-boxed module-access exceptions.

Incompatible changes in output, exceptions, or lifecycle must be documented before writing code.

### Step 4: Split Diffs into Manageable Groups

Examples:
- Migrating Base64/parsing/encoding.
- Replacing concurrency operations and Unsafe.
- Upgrading frameworks to eliminate deep reflection into the JDK.
- Moving bytecode instrumentation to a library version supporting the target JDK.
- Replacing internal certificate/crypto providers.
- Removing --add-opens/--add-exports case by case.

When each group has its own build/tests, identifying the cause of regressions is easier.

### Step 5: Build and Run on the Target Runtime

After making replacements, run:
- Compile with the appropriate Java SE target, preferring `javac --release` when using a newer compiler for an older runtime.
- Unit tests verifying APIs/adapters.
- Integration tests with related frameworks, serialization, crypto, DB, XML, and native dependencies.
- Smoke tests on the target JDK/vendor and runtime image.
- Tests for code paths using reflection/dynamic class loading, not just startup.
- Performance/concurrency checks when replacing low-level primitives.
- Run `jdeps --jdk-internals` on post-build artifacts to detect any remaining static dependencies.

For libraries published to consumers, verify both source/binary compatibility and lowest-JDK support, not just that your own application runs.

### Step 6: Remove Bypasses and Update Operations

Try removing temporary flags one by one and rerun the relevant scenarios. If a flag is still needed, there must be an issue/owner or a commitment to upgrade the dependency. Update runbooks, container args, build toolchains, and diagnostic scripts so old flags are not accidentally reintroduced.

## 12. Verifying Behavior After Replacing APIs

A migration succeeds only when **consumers observe that the contract is preserved** or changes have been announced, not merely because the compiler stays silent.

| Change | Recommended Tests |
|---|---|
| Base64 | Byte fixtures, padding, MIME line breaks, URL-safe, Unicode |
| Time/charset | Explicit charsets, timezone/locale, null/empty inputs |
| Atomic/VarHandle | Atomicity, ordering, visibility, overflow, race conditions |
| Reflection | Class discovery, DI, serialization, annotations, module boundaries |
| Bytecode/agent | Class verification, runtime class-file version, instrumentation, startup |
| Certificate/crypto | Formats, algorithms, key usage, chain validation, TLS integration |
| XML/parser | Sample data, namespaces, schemas, external entities, invalid input errors |
| Native/direct memory | Lifecycle, leaks, concurrency, platform/architecture, and failure paths |

### 12.1. Example Characterization Test for Codec Conversion

If encoded data has been stored in a database or exchanged with partners, save some byte fixtures from the old version. During migration, compare the new adapter's output against the old contract. If the old format does not follow standard Base64, clearly decide two distinct questions:
- Is decoding historical data required?
- Is continuing to produce output in the old format for current consumers required?

Do not force every system onto a new format merely because the standard API provides it out of the box. A codec may need a legacy-compatible read mode while always writing the new format, with agreed-upon versioning.

### 12.2. Regression Testing for Reflection

For frameworks using reflection, run scenarios:
- Instantiating objects/beans from annotations or metadata.
- Serializing/deserializing objects containing private fields.
- Loading plugins/services through the right class loader.
- Accessing constructors and members on the module path.
- Testing error paths, not just a simple object.

If `--add-opens` has been removed, check the actual startup command in staging/production. A test running on the classpath may pass while the modular deployment still fails.

### 12.3. Measuring Performance When Replacing Low-Level APIs

Replacing Unsafe with AtomicLong/VarHandle can alter access patterns and performance. However, a single benchmark result is not enough to reject a public API. Measure under representative workloads, distinguish correctness requirements from micro-optimizations, inspect GC/memory/throughput, and decide based on published operational thresholds.

## 13. Common Mistakes

- **Fixing errors only with --add-opens:** the application runs, yet still depends on JDK implementation details.
- **Treating all com.sun.* as internal:** you may mistakenly replace or remove supported public/vendor-specific APIs.
- **Running jdeps only once:** string-based reflection, generated code, or plugins may not appear in static analysis.
- **Replacing Unsafe with VarHandle by method name:** memory ordering and semantics may differ.
- **Changing the Base64 encoder while forgetting line breaks/padding:** breaks contracts with clients or legacy data.
- **Reading String's private value instead of public text APIs:** relies on an internal representation that can change.
- **Using privateLookupIn as a JPMS bypass:** this API is still subject to access control.
- **Manually patching bytecode of unmaintained dependencies:** creates a maintenance burden and may fail on newer class-file versions.
- **Assuming newer libraries always support older JDKs:** check the minimum Java release of the artifact and its dependency graph.
- **Fixing only compile errors:** reflection and linkage errors often surface when code paths are executed.
- **Failing to manage exceptions:** internal access flags may get copied into containers/CI for multiple processes unintentionally.
- **Failing to distinguish public APIs from behavioral changes:** compilation passes, yet formatting/exceptions/transactions/serialization differ.
- **Ignoring security:** writing custom crypto, XML parser, or certificate handling replacements can be riskier than the old dependency.

## 14. Checklist for Completing Internal API Replacement

- [ ] Identified the JDK/vendor/runtime floor and environments to support.
- [ ] Scanned artifacts with jdeps --jdk-internals and searched source/config for reflection.
- [ ] Categorized internal APIs, deprecated public APIs, and third-party dependencies.
- [ ] Recorded the actual need, code path, and owner for each usage.
- [ ] Prioritized public Java SE APIs when they satisfy the contract.
- [ ] If using external libraries, verified maintenance, security, license, and Java baseline.
- [ ] No remaining static dependencies on JDK internal APIs in migrated items.
- [ ] Deep reflection points into the JDK have been replaced or have managed temporary exceptions.
- [ ] Verified APIs, class files, and transitive dependencies on the lowest still-supported JDK.
- [ ] Tested outputs, exceptions, historical data, and side effects of replacement APIs.
- [ ] Tested concurrency/memory ordering when replacing Unsafe or low-level primitives.
- [ ] Tested module path, class loaders, framework reflection, and instrumentation where relevant.
- [ ] Remaining --add-opens/--add-exports have defined scope, owners, and removal plans.
- [ ] Builds, tests, deployments, and runbooks reflect the new dependencies and configuration.

## 15. Conclusion

JDK internal APIs may offer useful technical capabilities in a specific version, yet they are not a stable contract for applications. When Java migration exposes errors such as InaccessibleObjectException, IllegalAccessError, or classes no longer existing, remediation should start from the **actual purpose of the code**, then move to **public Java SE APIs** or **libraries with an explicit support lifecycle**. Workarounds such as --add-opens and --add-exports should be used only with strict limits during transition, not become hidden dependencies in production.

Combining an inventory via jdeps, searching source/config for reflection, selecting replacements according to support matrices, testing behavior on the target JDK, and gradually removing bypass flags will help the system break free from implementation-detail dependencies, preserve compatibility, and reduce the cost of Java upgrades in subsequent releases.
