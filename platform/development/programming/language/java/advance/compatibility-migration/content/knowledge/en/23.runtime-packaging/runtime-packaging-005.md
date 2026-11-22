# Public API Limits and Per-Branch Testing of Multi-Release JARs

## 1. The Problem: One Library, Multiple Java Versions

A Java library may need to continue serving applications running on Java 8, while also wanting to leverage APIs and optimization mechanisms available in Java 17 or Java 21. Forcing all consumers to upgrade Java immediately could break the library developer's support contract. Writing code strictly for Java 8 makes it difficult for the library to take advantage of new runtime features.

A **multi-release JAR (MRJAR)** solves part of this problem: a single JAR file containing a base implementation layer and variants for individual Java levels. The JVM selects the class best matching the running release, while **the library's public API must be kept consistent across branches** according to the JAR File Specification.

The danger is that under the same class name, the bytecode executed on Java 8 can differ from the code running on Java 17 or 21. A unit test passing on the current JDK does not prove:

- The **base** branch still runs on the declared minimum Java version.
- The **17** branch does not accidentally add a public method that only exists in Java 17.
- The **21** branch does not change behavior, security checks, or serialized data.
- The **11** runtime actually uses the base or an intermediate branch as expected.
- Dependency analysis, coverage, shading, signing, and module packaging tools all understand MRJAR.
- A consumer compiled against one branch can link when running on another branch.

This lesson focuses on two tasks in **Java Advance Compatibility Migration — Packaging and Environment**:

1. Understand **the limits of the public API** when creating same-named classes in `META-INF/versions/N`.
2. Build a **build, artifact inspection, and per-branch testing matrix** to prove a JAR properly supports the committed JDKs.

## 2. What Is a Multi-Release JAR, and What Is It Not?

JEP 238 introduced multi-release JARs into the platform starting in Java 9. A JAR can contain:

~~~text
library.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       ├── 9/
│       │   └── com/example/lib/Feature.class
│       ├── 17/
│       │   └── com/example/lib/Feature.class
│       └── 21/
│           └── com/example/lib/Feature.class
└── com/example/lib/Feature.class
~~~

The manifest in the **main section** must contain:

~~~text
Manifest-Version: 1.0
Multi-Release: true
~~~

When the MRJAR mechanism is used, a sufficiently new Java runtime prioritizes the appropriate versioned entries instead of only reading classes at the root.

**An MRJAR is not:**

- A tool for publishing **different v1/v2/v3 APIs** in the same JAR depending on the Java runtime.
- A form of Maven classifier or multiple release artifacts automatically selected by a dependency resolver.
- A feature that allows Java 21 bytecode to run on Java 8 merely by changing the path inside the JAR.
- An automated compatibility test suite.
- A mechanism that automatically preserves backward/forward behavioral compatibility.
- A replacement for versioning a library using semantic/API versioning.

The core idea is **same library contract, multiple runtime-specific implementations**, not “same dependency coordinates with a public interface that changes depending on the machine”.

## 3. Directory Structure and Recognition Rules

A valid MRJAR uses the path:

~~~text
META-INF/versions/N/<relative-entry-path>
~~~

where `N` is a valid Java release version number and **`N >= 9`**.

Example:

~~~text
com/example/Codec.class
META-INF/versions/11/com/example/Codec.class
META-INF/versions/17/com/example/Codec.class
META-INF/versions/21/com/example/Codec.class
~~~

There is no special `META-INF/versions/8` branch for Java 8. Code for Java 8, or a lower minimum if supported, is placed at the **root**.

### 3.1. The Manifest Is a Necessary Condition

If `Multi-Release: true` is missing or the value is not recognized as `true`, simply having a `META-INF/versions` directory will not cause the class loader to select the alternative versions. The manifest specification accepts the value `true` case-insensitively, but it should be written in standard form for easier review.

Do not expect copying class files into `META-INF/versions` while forgetting the manifest to work automatically.

### 3.2. Class-File Version Limits

A class located in branch `N` must have a class-file major version **no higher than** the bytecode level corresponding to Java `N`. For example:

| Location | Maximum Java level in branch | Maximum class-file major |
| --- | ---: | ---: |
| Root — library commits to Java 8 | Java 8 | 52 |
| `META-INF/versions/9` | Java 9 | 53 |
| `META-INF/versions/11` | Java 11 | 55 |
| `META-INF/versions/17` | Java 17 | 61 |
| `META-INF/versions/21` | Java 21 | 65 |

Do not place a class compiled with Java 21 defaults (major 65) into the `versions/17` directory and hope a Java 17 runtime will accept it. Directory names do not transform bytecode.

### 3.3. Not Every Entry in `META-INF` Is Versioned

The JAR File Specification states that **resources under `META-INF` are not versioned by the MRJAR mechanism**, such as `META-INF/services/...`. Do not place ServiceLoader provider configuration files under `META-INF/versions/17/META-INF/services` and expect ServiceLoader to select them automatically based on the JDK.

For module descriptors, there are specific rules when placing `module-info.class` in a versioned branch; see the JPMS section below.

## 4. Which Branch Does the JVM Select?

Suppose a JAR contains root, branch 9, branch 17, and branch 21:

~~~text
Root:     Feature.class  (Java 8 compatible)
Version9: Feature.class  (Java 9)
Version17:Feature.class  (Java 17)
Version21:Feature.class  (Java 21)
~~~

When the runtime supports MRJAR and uses an appropriate class loading mechanism, the JVM searches from the current release downward:

| Executing JVM | Search priority order when loading `Feature` | Result when all variants above exist |
| --- | --- | --- |
| Java 8 | Root only | Root |
| Java 9 | 9 → root | Branch 9 |
| Java 11 | 11 → 10 → 9 → root | Branch 9 |
| Java 17 | 17 → … → 9 → root | Branch 17 |
| Java 19 | 19 → 18 → 17 → … → root | Branch 17 |
| Java 21 | 21 → 20 → 19 → … → root | Branch 21 |
| Java 23 | 23 → 22 → 21 → … → root | Branch 21 |

**The closest branch not exceeding the runtime** is selected; it does not necessarily have to match the exact current release number.

### 4.1. Selection Occurs Per Entry/Class

Suppose branch 21 only has `FastCodec.class`, while `CodecConfig.class` only appears in the root. On Java 21, the JVM may use:

~~~text
FastCodec.class   -> META-INF/versions/21/...
CodecConfig.class -> root/...
~~~

Do not assume the runtime always selects **a single directory** and ignores all other directories. The fallback rule applies per entry name, within the scope of class loaders/JAR access that support MRJAR.

### 4.2. Beware of Custom Class Loaders

Standard class loaders and tooling recognize MRJARs according to the specification. However, a custom loader that reads a JAR manually as a ZIP and defines classes from the root bytes may ignore versioned entries. For fat JAR launchers, plugin frameworks, nested-JAR loaders, or custom classpath scanners, you must verify whether the implementation supports MRJAR.

Do not run one test using `java -cp library.jar` and assume that a custom loader mechanism in an application server handles MRJAR identically.

## 5. The Most Important Constraint: The Public API Must Be Identical

The JAR File Specification requires that **the public API exported by classes in an MRJAR must be identical across versions**. That is why the same public class in the Java 17 branch must still exist in the root with the same fully qualified name and access modifier, except for the exception specified for certain non-exported packages in modular MRJARs.

Example of what not to do:

~~~java
// Root -- Java 8
package example.api;

public class PriceCalculator {
    public long total(long price, int quantity) {
        return price * quantity;
    }
}
~~~

~~~java
// META-INF/versions/17 -- DOES NOT MATCH PUBLIC API CONTRACT
package example.api;

public class PriceCalculator {
    public java.math.BigDecimal total(
            java.math.BigDecimal price, int quantity) {
        return price.multiply(
                java.math.BigDecimal.valueOf(quantity));
    }
}
~~~

Two classes with the same name but public methods having different descriptors: a caller compiled against one branch may fail to link when running against the other branch.

A better model:

~~~java
// Both root and every alternative branch keep:
public long total(long price, int quantity)
~~~

while the **internal implementation** is allowed to use different APIs/algorithms per JDK.

### 5.1. Public API Is Not Just a List of Method Names

Components to consider include:

- Fully qualified class name and visibility.
- Public/protected constructors.
- Public/protected methods, static/instance, return type, and parameter types.
- Public/protected fields, field types, and modifiers.
- Superclass/interfaces and type compatibility.
- API aspects affected by generics/signatures, exceptions, annotations, or inheritance.
- Nested classes/interfaces/enums/records if they are part of the public contract.
- Method/field behavior that consumers rely on, even if the bytecode signature does not change.

**Binary API**, **source API**, and **behavioral contract** are related but not identical. For example, changing a generic signature might preserve the erased descriptor while causing consumer recompilation errors; changing an exception policy can break applications even though the method descriptor does not change.

### 5.2. Method Return Type Is Part of the JVM Descriptor

In bytecode, `calculate(long)long` has descriptor `(J)J`; changing it to `calculate(long)java.math.BigDecimal` produces a different descriptor. Even if the method name and parameters stay the same, a Java caller compiled against the old descriptor may encounter `NoSuchMethodError`.

Therefore, when checking the public API, do not merely compare method names with a text search. Compare compiled descriptors/signatures and test with a real consumer.

## 6. “Identical” Public API Does Not Mean Bytecode Must Be Identical

MRJARs exist precisely so implementations can differ. For example, the same public method:

~~~java
public static String encode(byte[] bytes)
~~~

The Java 8 branch can convert bytes to hex manually using a loop. The Java 17 branch can use `java.util.HexFormat`. The public API is completely identical.

Changes commonly appropriate in a versioned implementation:

- Using a Java SE API only available in a newer JDK **inside** the method.
- Using a more optimal algorithm or newer concurrency primitives.
- Using a branch-specific package-private helper class when packaging rules allow.
- Reducing allocation overhead or changing internal implementation details.
- Optimizing file reading, hashing, buffering, or data processing provided behavior remains correct.

Condition: usage from the consumer side **must not require a different Java public API depending on the runtime**.

### 6.1. A Stable Public API Still Requires Behavioral Testing

Two branches may both return `String`, yet one branch produces lowercase hex and the other uppercase hex. The API signature has not changed, but the result differs:

~~~text
Java 8:  0a1b...
Java 17: 0A1B...
~~~

For hashing, tokens, protocol headers, JSON serialization, or cache keys, that difference can break the system. Therefore **an API parity check does not replace behavioral compatibility tests**.

## 7. API Differences That Should Not Be Introduced in a Branch

| Change in higher branch | Risk |
| --- | --- |
| Adding a public method only in branch 21 | Consumer compiled on 21 but running on 17 may hit `NoSuchMethodError` |
| Removing/renaming a public method in branch 17 | Consumer compiled against root may hit linkage errors |
| Changing parameter/return type | Changes JVM method descriptor |
| Changing an instance method to static | `IncompatibleClassChangeError` or related linkage error |
| Changing a public field type or removing a field | `NoSuchFieldError` or ABI mismatch |
| Changing a public class to an interface or vice versa | Type/linkage incompatibility |
| Changing a public constructor to private | Consumers creating instances may fail |
| Adding a public class only in a higher branch (non-modular JAR) | Violates exported API/counterpart constraint in root |
| Changing superclass/interfaces altering type relations | May break assignability/linkage |
| Changing generic signature/annotation API | May break source/reflection/tooling even though JVM descriptor remains intact |

If you genuinely need to release a new API, **bump the library/API artifact version** with a clear compatibility policy, or create separate runtime-specific artifacts, rather than hiding new APIs inside an MRJAR branch.

## 8. Exceptions and Internal Areas That Must Be Understood Accurately

The specification distinguishes public/protected classes in the exported API from internal classes.

### 8.1. Package-Private Helpers

A non-public helper may exist only in branch 17 for an optimized implementation:

~~~text
Root:
  example/api/Codec.class

META-INF/versions/17:
  example/api/Codec.class
  example/api/Hex17Support.class  (package-private)
~~~

The public `Codec` must preserve the API contract, while `Hex17Support` is an internal detail. However, names, visibility, and class dependencies must still adhere to MRJAR rules and module boundaries; you should not use a higher-branch class as the public return type of `Codec`.

### 8.2. Modular JARs and Non-Exported Packages

For a **modular multi-release JAR**, the specification has an exception: a public/protected class in a **non-exported package** does not necessarily need to have a counterpart class with the same name and access in the root. The reason is that the package does not belong to the public API exported by the module.

This is not a license to arbitrarily change the API of an **exported package**. If the module descriptor exports `example.api`, classes in `example.api` must still maintain API parity.

You should not rely on this exception when the same JAR is also used on the classpath and expected to have JPMS-equivalent encapsulation. Classpath and module path control accessibility differently.

### 8.3. Internal Does Not Mean Zero Impact

A package-private class that changes behavior can still cause a public method to return a different result. Reflection, serialization, ServiceLoader, logging, and scanning frameworks can also observe internals. Therefore, “non-public” only relaxes the API constraint; it does not automatically make changes risk-free.

## 9. End-to-End Example: SHA-256 Hex Library Supporting Java 8 and 17

We want to publish a JAR:

- **Root** compiled for Java 8 so all older consumers can use it.
- **Branch 17** uses `HexFormat` available in Java 17.
- Both branches expose **the exact same public API**.
- The sha256 hex output is always lowercase, regardless of runtime.

Source structure:

~~~text
src/
├── main/
│   └── java/
│       └── example/crypto/HexDigest.java
└── java17/
    └── java/
        └── example/crypto/HexDigest.java
~~~

Both files have the same fully qualified class name but **reside in different source sets**. Do not compile both as two identically named classes in the same compilation unit/source set.

### 9.1. Root Implementation for Java 8

File `src/main/java/example/crypto/HexDigest.java`:

~~~java
package example.crypto;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

public final class HexDigest {
    private static final char[] HEX =
            "0123456789abcdef".toCharArray();

    private HexDigest() {
    }

    public static String sha256Hex(byte[] input) {
        try {
            byte[] digest =
                    MessageDigest.getInstance("SHA-256").digest(input);
            char[] output = new char[digest.length * 2];

            for (int i = 0; i < digest.length; i++) {
                int unsigned = digest[i] & 0xff;
                output[2 * i] = HEX[unsigned >>> 4];
                output[2 * i + 1] = HEX[unsigned & 0x0f];
            }

            return new String(output);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }
}
~~~

When compiling the root, use a Java compiler with `--release 8` or a supported compiler/bootclasspath pipeline to guarantee Java 8 APIs. Example using a JDK that supports the corresponding option:

~~~bash
javac --release 8 \
  -d build/classes/base \
  src/main/java/example/crypto/HexDigest.java
~~~

### 9.2. Implementation for Java 17+

File `src/java17/java/example/crypto/HexDigest.java`:

~~~java
package example.crypto;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class HexDigest {
    private HexDigest() {
    }

    public static String sha256Hex(byte[] input) {
        try {
            byte[] digest =
                    MessageDigest.getInstance("SHA-256").digest(input);
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }
}
~~~

`HexFormat` is an API introduced in Java 17, so this code does not belong in the root if the library must support Java 8. Compile the branch separately:

~~~bash
javac --release 17 \
  -d build/classes/java17 \
  src/java17/java/example/crypto/HexDigest.java
~~~

**API comparison:** Both classes are `public final`, have a private constructor, and have one public static method `sha256Hex(byte[]):String`. They differ in implementation details and private fields, which aligns with the purpose of an MRJAR.

### 9.3. Packaging with `jar`

Example commands compatible with a JDK tool supporting `--release` in `jar`:

~~~bash
jar --create \
  --file build/hex-digest.jar \
  -C build/classes/base .

jar --update \
  --file build/hex-digest.jar \
  --release 17 \
  -C build/classes/java17 .
~~~

`jar --release 17` places the following entries into `META-INF/versions/17` and helps create an MRJAR. When building a real artifact, confirm that `Multi-Release: true` is present in the manifest and inspect the entry list, because depending on the pipeline, packaging, shading, or custom build steps may overwrite the manifest.

Verification commands:

~~~bash
jar --list --file build/hex-digest.jar
jar --validate --file build/hex-digest.jar
~~~

The JAR is expected to contain:

~~~text
META-INF/MANIFEST.MF
example/crypto/HexDigest.class
META-INF/versions/17/example/crypto/HexDigest.class
~~~

This example illustrates minimal construction; production builds should use plugins/tasks with explicit dependencies, toolchain management, and reproducible artifacts.

## 10. Testing the Result with an Independent Consumer

The consumer uses only the public API:

~~~java
package example.consumer;

import example.crypto.HexDigest;
import java.nio.charset.StandardCharsets;

public final class Main {
    public static void main(String[] args) {
        byte[] bytes = "hello".getBytes(StandardCharsets.UTF_8);
        System.out.println(HexDigest.sha256Hex(bytes));
    }
}
~~~

Expected output:

~~~text
2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824
~~~

Compile the consumer targeting Java 8 to confirm the root API is usable:

~~~bash
javac --release 8 \
  -cp build/hex-digest.jar \
  -d build/consumer-classes \
  src/consumer/java/example/consumer/Main.java
~~~

Run the same consumer bytecode on the committed supported JVM runtimes:

~~~bash
java -cp build/hex-digest.jar:build/consumer-classes \
  example.consumer.Main
~~~

On Windows, the typical classpath separator is `;` instead of `:`. The commands above are a **practice scenario**, not commands executed for this lesson.

### 10.1. Identical Output Does Not Prove the Right Branch Was Selected

Both implementations intentionally produce identical results. To prove the runtime actually selects the branch, you can:

- Inspect the code of each variant using `javap --multi-release`.
- Use appropriate class-load diagnostics/JAR resource inspection tools.
- Check implementation-specific dependencies of the packaged classfiles.
- Try a control scenario with instrumentation/debug markers in a controlled test environment, without breaking the public API.

Do not add a public method such as `implementationVersion()` only in the higher branch just for “easier testing”: that very action causes API divergence. If a public diagnostic method is needed, it must also have the same signature in the root and every branch.

## 11. Compile Base Once and Each Branch Once

A proper pipeline typically cleanly separates:

~~~text
compileBase (--release 8)
      |
      +----> classes/base/

compile17 (--release 17)
      |
      +----> classes/java17/

packageMultiReleaseJar
      |
      +----> hex-digest.jar
             root/...
             META-INF/versions/17/...
~~~

**Do not mix output folders before packaging.** If Java 17 classes are copied over the root, the JAR may no longer support Java 8 even if the manifest declares it multi-release.

### 11.1. Dependencies Flow from Higher Branches Toward Base

Branch 17 may use APIs declared in the root and Java 17 classes; the root **must not** directly depend on classes that only exist in branch 17 or Java 17 APIs. If the root contains bytecode referencing newer classes and runs on Java 8, class loading/linkage may fail.

When compiling a higher branch, having the base output on the classpath can be useful for shared classes. However, you must avoid mistakenly feeding compiled classes of a higher branch back as a dependency to the root.

### 11.2. Use `--release` Instead of Only `-source`/`-target`

If a JDK 21 compiler compiles the root with `-source 8 -target 8`, the code may accidentally call newer JDK APIs visible to the compiler on the current platform. `javac --release 8` restricts the platform API to release 8 and produces appropriate bytecode.

However, `--release` does not automatically guarantee that third-party JARs on the classpath also support Java 8. You still need to check dependency metadata, bytecode, and test running on a real JDK 8 when that is a support requirement.

## 12. Do Not Let the Compiler “See” APIs Only Present in Higher Branches

Suppose root `PublicClient` calls:

~~~java
return Java17OnlyHelper.fastPath(input);
~~~

yet `Java17OnlyHelper` only exists in `META-INF/versions/17`. Root compilation only succeeds if the build accidentally places branch 17 on the classpath; on Java 8, the call will fail to resolve.

Therefore:

1. Compile the root targeting the minimum release.
2. Do not place higher-branch versioned output on the root compile classpath.
3. Analyze static references using `jdeps`.
4. Run the root on the minimum JDK in a clean test environment.
5. Test code paths that may be lazily loaded, not just app startup.

MRJAR is not a “runtime feature flag” that lets the root arbitrarily reference classes that do not exist on older runtimes.

## 13. API Parity Must Be Verified on Compiled Artifacts

For every public/protected class, you need to compare the compiled output:

~~~text
Root public API
   ↕
JDK 9 selected public API
   ↕
JDK 17 selected public API
   ↕
JDK 21 selected public API
~~~

Ask:

- Same class name and accessibility?
- Same public/protected constructor signatures?
- Same public/protected field names/types/modifiers?
- Same method descriptors and static/instance flags?
- Same generic signatures that matter to source consumers?
- Same superclass/interfaces and type relationships?
- No new public methods/classes outside the root contract?
- Do annotations/reflection/serialization still preserve the right semantics?

### 13.1. Checking with `javap --multi-release`

Example:

~~~bash
javap --multi-release base \
  -classpath build/hex-digest.jar \
  -public -s example.crypto.HexDigest

javap --multi-release 17 \
  -classpath build/hex-digest.jar \
  -public -s example.crypto.HexDigest
~~~

`-s` shows JVM descriptors. `-public` is useful for inspecting public members; for libraries where protected APIs matter, use `-protected` or combine with an appropriate API diff tool.

In JDK/tool versions that support it, `javap --multi-release VERSION` selects the corresponding view. Do not assume `javap -classpath file.jar Foo` always inspects the running branch if no version is specified.

### 13.2. `jar --validate` Is the First Line of Verification

~~~bash
jar --validate --file build/hex-digest.jar
~~~

According to the `jar` tool documentation, the validator can check integrity and exported API consistency across versioned entries. If the tool reports an error, fix it before releasing.

**However, this is not comprehensive certification:** the JAR File Specification notes that checking every aspect of a public API is difficult and the runtime is not required to validate API parity. Binary signature checks still need to be combined with compile tests, reflection behavior checks, and end-to-end tests on real JDKs.

### 13.3. Comparing APIs Intentionally

If the project uses an API diff tool such as japicmp, Revapi, or a custom compatibility framework, verify that the tool is MRJAR-aware and selects the right variant. A tool that reads root entries as a ZIP and reports “no changes” does not prove branch 21 is compatible.

API diff results must be tied to the **exact per-release class view** and supported policy, not just the Maven version of the whole JAR.

## 14. Exposing APIs via Generics, Bridge Methods, and Annotations

Binary compatibility is sometimes more complex than plain class/method names:

~~~java
public interface Repository<T> {
    T find(String id);
}
~~~

The compiler can generate bridge methods when overriding generic methods. A change to the class hierarchy or generic signature in a versioned class can cause different bridge methods and create linkage errors when a consumer is compiled against one view and run against another.

Additional points to examine:

- Generic `Signature` attribute.
- Bridge and synthetic methods with runtime impact.
- Annotations with `RUNTIME` retention read by frameworks.
- Parameter names/annotations if used by dependency injection, serialization, or reflection.
- Checked exceptions in method contracts.
- Default interface methods and static/instance access.
- Public nested classes, enum constants, records, and sealed types.

The MRJAR specification requires a uniform exported API; in practice, **a library's compatibility policy** should also cover metadata that consumers/tooling treat as part of the contract.

### 14.1. Keeping the Same Signature While Changing Annotations Can Break Behavior

Two branches both have:

~~~java
public String encode(String value)
~~~

but one branch has a different validation annotation or JSON annotation, which can cause frameworks to process it differently. That is why reflection, serialization, and integration paths should be tested on each runtime, not just compared by API text.

## 15. Public Constants and Compile-Time Values Are a Special Case

Suppose a public class has:

~~~java
public static final int MAX_CHUNK_SIZE = 1024;
~~~

If branch 17 changes the value to `2048` while keeping the same field signature, the API surface looks similar at a glance, but Java consumers may have **inlined** the compile-time constant value during compilation. Older callers may keep using `1024` even on a runtime that selects branch 17.

Therefore, public compile-time constants should not be turned into a way of advertising different capabilities per JDK. If a value genuinely depends on the runtime, you can provide a **public method preserving the same signature** across all branches:

~~~java
public static int recommendedChunkSize()
~~~

Even then, differing method return values must still conform to the documented business contract. For example, a value that is purely a performance hint may acceptably vary; a value involved in a protocol handshake or data format may not be allowed to differ.

## 16. Which Java APIs Is Each Branch Allowed to Use?

Suppose a library has a Java 8 root, plus branches 17 and 21.

| Code located in | May use Java SE APIs from | Must not depend on |
| --- | --- | --- |
| Root | Minimum Java level (here Java 8) | Java 9/17/21-only APIs |
| `versions/17` | APIs existing up to Java 17 | Java 18–21-only APIs |
| `versions/21` | APIs existing up to Java 21 | APIs introduced after Java 21 |

This rule follows the **corresponding runtime release**. The Java 21 branch can use `record` or Java 21 APIs if standardized/permitted in that release; the root cannot directly use those newer syntax/APIs.

### 16.1. Removed APIs or Changed Behavior

“Higher JDK” does not mean every older API stays unchanged. A branch 21 implementation may need changes because APIs/modules from Java 8 are no longer bundled. MRJAR helps implement internal changes while preserving the public API, yet behavior such as security defaults, locale, timezone, TLS, and serialization must still be tested.

### 16.2. Preview Features

Preview features should not be treated as a stable foundation for a public API in an MRJAR. They carry release-dependent compiler/runtime flag requirements and can change across JDKs. If used in a higher branch's implementation, build flags and runtime policy must be tightly controlled; in widely distributed libraries, standardized APIs should generally be preferred.

## 17. Branch Fallback Does Not Mean Every Class Combination Is Safe

A Java 21 runtime can select some classes from branch 21, some from 17, and the rest from the root. Those classes must be **compatible with one another** at runtime.

Example:

~~~text
Root:                  PublicCodec + InternalBuffer
META-INF/versions/17:  PublicCodec + FastBuffer
META-INF/versions/21:  PublicCodec
~~~

On Java 21, `PublicCodec` is loaded from branch 21. `FastBuffer` has no variant 21, so it may be loaded from branch 17 if looked up. `InternalBuffer` may still come from the root.

What to verify:

- Does branch 21 accidentally call a helper 17 method that never existed?
- Does the higher-branch helper exist with a class-file target not exceeding the runtime?
- Are different package-private APIs used that cause `NoSuchMethodError`?
- Does initialization/serialization state differ across helpers selected from different branches?

Do not just test “Java 21 uses version 21”: it uses **an effective set of entries** after fallback rules.

## 18. A Test Matrix Required for MRJARs

With branches root, 9, 17, and 21:

| Runtime JDK | Effective branch for classes having all variants | Test suite to run |
| --- | --- | --- |
| Java 8 | root | Base API, minimum runtime, behavior, dependencies |
| Java 9 | 9 | Java 9 branch and module behavior if used |
| Java 11 | 9 | Fallback 9 and JDK 11 environment changes |
| Java 17 | 17 | Branch 17, Java 17 APIs, reflection/serialization |
| Java 19 | 17 | Fallback 17 and Java 19 behavior if supported |
| Java 21 | 21 | Branch 21, class-file 65, integration |
| Java 23 | 21 | Fallback 21 and newer runtime compatibility |

If a library only commits to Java 8, 17, and 21, that may be the minimum runtime set. However, if the product claims support for **every Java LTS or every release between milestones**, choose a test matrix reflecting that commitment. The branch fallback mechanism can cause failures that only appear in a specific runtime range.

### 18.1. Do Not Use One JDK to Simulate Every Runtime

`javap --multi-release 8/17/21` and view-selection properties can help analyze classes, but they do not replace launching real JVM versions. Java 8 has different module, class-loading, TLS, and GC behavior from Java 17/21.

### 18.2. Test Each Variant and Intersection Path

Do not only check that `Feature.class` is selected. You need to test methods involving helper classes, service providers, resources, runtime dependencies, and lazily initialized classes.

A multi-branch MRJAR can pass green on Java 8 and 21 yet fail on Java 11 because branch 9 relies on an assumption that no longer holds. Therefore you must test **each actual runtime zone**.

## 19. Testing the Public API with a Pre-Compiled Consumer

A major source of bugs is a consumer compiled on a higher runtime but deployed on a lower runtime still supported by the library. If the public API differs across branches, errors only appear when the JVM resolves methods/classes.

Recommended test:

1. Compile a consumer using the **root public API** targeting the minimum Java level.
2. Keep the consumer bytecode unchanged.
3. Run the consumer with the same MRJAR on the target JDKs.
4. Ensure there is no `NoSuchMethodError`, `NoSuchFieldError`, `IllegalAccessError`, or behavior drift.
5. If the library allows consumers to compile on a newer JDK and still run on an older JDK, also compile a consumer on the appropriate release and test cross-direction compatibility per product policy.

Example consumer usage:

~~~java
import example.crypto.HexDigest;

final class Consumer {
    static String hash(byte[] input) {
        return HexDigest.sha256Hex(input);
    }
}
~~~

The consumer does not need to know whether the runtime selects root or branch 17. That is the **stable API contract** an MRJAR aims for.

### 19.1. Compiling on a Newer JDK Does Not Prove the Consumer Can Run on an Older JDK

Even if the public API is identical, the compiler might generate a newer class-file version or the consumer might accidentally call a newer Java API. When certifying compatibility, record `--release`, dependencies, and corresponding JVM tests.

## 20. `jdeps --multi-release`: Analyzing Dependencies of Each Branch

`jdeps` can analyze a multi-release JAR by release view:

~~~bash
jdeps --multi-release base \
  --summary build/hex-digest.jar

jdeps --multi-release 17 \
  --summary build/hex-digest.jar

jdeps --multi-release 21 \
  --summary build/hex-digest.jar
~~~

`base` means inspecting root entries; version `17` or `21` is the level used to select class variants. Do not confuse `jdeps --multi-release 21` with running tests on Java 21.

### 20.1. Detecting JDK Internal APIs

~~~bash
jdeps --multi-release 17 \
  --jdk-internals build/hex-digest.jar
~~~

If a branch depends on internal JDK APIs, evaluate the likelihood of being affected by strong encapsulation or API removal. `jdeps` does not always catch dynamic reflection by class name string, native code, or runtime-generated bytecode; combine it with smoke/integration tests.

### 20.2. Detecting Missing Dependencies

~~~bash
jdeps --multi-release 21 \
  --missing-deps build/hex-digest.jar
~~~

Read results in the context of the full classpath/module path, because a missing reference in static analysis can come from an optional dependency or a dependency omitted from the analysis environment. Do not treat every warning as a production failure, nor blindly ignore it.

## 21. Inspecting Each Branch's Bytecode Directly

`javap` does not only print signatures; it also disassembles:

~~~bash
javap --multi-release base \
  -classpath build/hex-digest.jar \
  -c -private example.crypto.HexDigest

javap --multi-release 17 \
  -classpath build/hex-digest.jar \
  -c -private example.crypto.HexDigest
~~~

In the SHA-256 example, base has the hex conversion loop, while the Java 17 branch can contain calls to `java/util/HexFormat`.

In addition:

~~~bash
javap --multi-release 17 \
  -classpath build/hex-digest.jar \
  -verbose example.crypto.HexDigest
~~~

Confirm the class `major version` and the method references in the constant pool. Do not take the output of one class in root and conclude that every class under `META-INF/versions/17` also uses the same bytecode/API.

### 21.1. Do Not Release Based Solely on a Signature Diff

Disassembly helps verify the existence of a branch-specific implementation, but it does not verify business logic. A branch might use the right Java 17 API yet handle empty bytes or Unicode differently from the base. Tests must cover data/behavior.

## 22. Testing Behavior by Input Category

For `HexDigest.sha256Hex`, cases should include:

- Input `byte[0]`.
- A positive/negative byte when represented as a signed Java `byte`.
- Standard ASCII strings.
- Multi-byte UTF-8 data, if consumers convert text to bytes.
- Large payloads to check performance/memory.
- `null` and exception contract (expected behavior must be settled).
- Concurrent execution from multiple threads.

JUnit 5 example (illustrating test cases only):

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import example.crypto.HexDigest;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class HexDigestContractTest {
    @Test
    void sameHashOnEverySupportedJdk() {
        byte[] input = "hello".getBytes(StandardCharsets.UTF_8);

        assertEquals(
            "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
            HexDigest.sha256Hex(input)
        );
    }
}
~~~

This test is valuable when running **the same contract test** on real JVMs with the packaged JAR. Do not only run tests directly against the branch 17 output directory; doing so can bypass MRJAR selection/fallback logic.

### 22.1. Should Performance Be Compared?

MRJARs often exist to optimize per JDK. Therefore benchmarks should run under fair conditions: warmup, input distribution, JIT/GC, and the same hardware and JVM configuration when possible.

However, do not prioritize performance to the point of sacrificing correctness: a Java 21 branch returning a different result from base is not a “valid optimization” just because it is faster.

## 23. Testing Serialization and Persistent Data

A public class with identical methods but different internal fields between root and branch 17 can impact Java serialization, JSON/XML mapping, persistence, or reflection.

Example:

~~~java
public final class SessionState implements Serializable {
    private static final long serialVersionUID = 1L;
    private final String sessionId;
    // Remaining implementation fields may differ by branch.
}
~~~

If root and branch 17 share the same `serialVersionUID` yet have different serialized fields, data written by Java 8 is not guaranteed to restore properly on Java 17. `serialVersionUID` does not perform automatic schema conversion.

Therefore, if exposed classes or DTOs participate in persistence:

1. Create data fixtures using a writer on Java 8.
2. Read the fixtures on Java 17/21.
3. Create data fixtures using a writer on Java 17/21.
4. Read on Java 8 if rollback/interoperability is required.
5. Verify invariants and business meaning, not just absence of exceptions.

MRJAR does not replace data schema versioning. For long-lived data, it is usually best to keep the serialized DTO format stable or choose an appropriate schema-based format.

## 24. Resources: Is Every File Selected by Version Like Classes?

The JAR File Specification permits eligible resource entries in versioned directories in addition to class files. However, some areas within `META-INF` have special rules and are not versioned like normal resources.

### 24.1. Example of a Runtime-Specific Resource

~~~text
Root:
  example/config/defaults.properties

META-INF/versions/17:
  example/config/defaults.properties
~~~

When resource lookup goes through an MRJAR-aware API/class loader, the selected resource can follow the runtime release. However, if code reads ZIP/JAR entries manually or uses a custom loader, the result may differ.

### 24.2. Do Not Version `META-INF/services` This Way

Do not create:

~~~text
META-INF/versions/17/META-INF/services/example.spi.Service
~~~

and expect it to be handled as a standard versioned service configuration. `META-INF` is an area with special rules; provider configuration under `META-INF/services` is not a resource eligible for ordinary versioning.

If service implementations need to vary by runtime, design provider classes and registration appropriately for module/classpath, and test ServiceLoader across supported JDKs.

## 25. What Does Java 8 See in a Multi-Release JAR?

Java 8 does not support MRJAR selection. It processes JARs under the traditional model using root classes. `META-INF/versions/N` entries simply sit inside the ZIP/JAR as data that the traditional class loader does not use to override root classes.

Consequences:

- Root classes **must** run on Java 8 if that is the Java minimum.
- A public class existing only in branch 17 does not become a usable public class on Java 8.
- Root cannot depend on Java 17-only types.
- The manifest does not automatically provide a compatibility shim.
- An older plugin/agent that scans every `.class` in the archive may try to read Java 17 bytes and fail, even though a Java 8 runtime will not select that class.

That last point matters when using bytecode scanners, code quality tools, or shading plugins: **tools scanning raw ZIPs may inspect classes that the runtime will never load on Java 8**.

## 26. Multi-Release JARs and the Java Platform Module System

An MRJAR can be:

- A non-modular JAR placed on the **classpath**.
- A JAR without a module descriptor placed on the **module path** as an automatic module.
- An **explicit modular MRJAR** having `module-info.class` at the root or an eligible versioned directory.

These forms differ in how they control exports, opens, requires, and service providers.

### 26.1. `module-info.class` in Branch 9

A library keeping root support for Java 8 can place its module descriptor at:

~~~text
META-INF/versions/9/module-info.class
~~~

to become an explicit module when used on the module path on a suitable JDK. This allows the same artifact to stay Java 8-compatible on the traditional classpath while declaring a module on newer JDKs.

Illustrative descriptor example:

~~~java
module example.crypto {
    exports example.crypto;
}
~~~

Having a valid descriptor does not automatically mean every reflection framework works; you may need to check `opens`, dependencies, and the runtime module graph.

### 26.2. Versioned Module Descriptors Have Strict Restrictions

According to the JAR File Specification, a versioned `module-info.class` overriding an older descriptor must keep the same module descriptor, except for specifically allowed differences, including certain **non-transitive requires** on `java.*`/`jdk.*` modules and `uses` clauses.

Do not use a branch 21 `module-info.class` to silently rename the module, change exported packages, or alter the public module contract. The specification requires preserving compatibility; tools may check it, though the runtime is not an exhaustive enforcer.

### 26.3. Both Classpath and Module Path Need Testing When Supported

A library might work well on the classpath yet fail on the module path due to exports/opens or service loading. If the product claims support for both, the test matrix should cover both dimensions:

~~~text
JDK 17 + classpath
JDK 17 + module path
JDK 21 + classpath
JDK 21 + module path
~~~

Do not use classpath-only test results to infer module-path behavior.

## 27. `JarFile`, `ZipFile`, and How Tooling Views a JAR

`java.util.jar.JarFile` supports multi-release processing, but **how JarFile is instantiated** and the runtime version view affect which entries are returned.

The Java API lets you specify a `Runtime.Version` when opening JarFile to select a release-specific view. Conversely, `ZipFile` reads actual ZIP entries; iterating it as a plain ZIP does not automatically apply MRJAR logical class selection rules.

### 27.1. A Pitfall When Writing Custom Scanners

Pseudo-code example:

~~~text
for each zip entry whose name ends with .class:
    read bytecode
    analyze as Java 8 class
~~~

The scanner encounters `META-INF/versions/17/...` as well and may report “Unsupported class file major version 61”, even though the root supports Java 8. The problem is that the scanner reads **all physical entries** yet mistakenly assumes all of them must be loaded on Java 8.

Solution: decide whether the tool analyzes **all variants** or the **logical view of a runtime**, use MRJAR-aware APIs/tools, or process versioned entries according to explicit rules.

### 27.2. Explicitly Document Tool Mode During Audits

Two different needs:

- **Artifact audit:** inspect all entries, including every versioned class, to detect malicious/stale/unexpected binaries.
- **Runtime-specific API/dependency analysis:** inspect the exact effective entries that a Java `N` runtime will select.

Do not mix the two kinds of reports and conclude that a branch has been tested.

## 28. Shading, Fat JARs, Spring Boot Launchers, and Other Packaging

An MRJAR can be altered by the packaging process:

- Shading/relocation changes package/class names.
- Fat JAR plugins merge multiple dependency JARs.
- Nested JAR launchers or custom class loaders.
- Assembly plugins copy entries while losing the manifest.
- Minifiers/obfuscators process root classes while skipping versioned classes.
- Repackagers drop `META-INF/versions` or flatten to one fixed branch.

There is no rule that “every fat JAR supports or does not support MRJAR”. It depends on the launcher/plugin version and packaging approach. You must inspect the **final artifact**, not just the original JAR in the Maven cache.

### 28.1. Post-Packaging Checks

~~~bash
jar --list --file build/final-app.jar
jar --validate --file build/final-app.jar
~~~

If `final-app.jar` is an executable JAR with a nested structure and its own loader, `jar --validate` cannot replace an end-to-end test of that launcher. Run the application from the final artifact on each JDK, verifying class loading and logs.

### 28.2. Duplicate Entries and Relocation

Two dependencies both containing `META-INF/versions/17/example/Codec.class` can create conflicts when merged. Shading requires consistent rules for duplicate entry handling, package relocation, and manifests; uncontrolled “first wins” can cause a runtime JAR to pick the wrong variant.

## 29. Signing and Integrity of Multi-Release JARs

An MRJAR can be signed like an ordinary JAR, though keep in mind each versioned entry is data inside the archive and may carry its own signature metadata under JAR signing rules.

Changes after signing:

- Adding/removing classes in a branch.
- Shading/relocation.
- Changing the manifest.
- Recompressing/repackaging entries in a way that alters signed data.

can cause signature verification to fail or lose provenance information. If your organization requires artifact signing, **finish packaging first and then sign**, then verify the exact artifact to be released.

Do not treat a JVM selecting the right class as proof that a JAR comes from a trusted origin. Integrity/signature verification and runtime branch selection are separate verification dimensions.

## 30. Maven: How to Organize Multi-Release Builds

Maven has an official **Guide to Multi-Release JARs**. The core idea:

1. Compile root sources targeting the minimum Java release.
2. Configure a separate compiler execution for each higher branch.
3. Place branch output into the proper `META-INF/versions/N` directory.
4. Use the JAR plugin to package the MRJAR and ensure the manifest.
5. Check the packaged JAR with `jar --validate` and test across multiple JDKs.

In compatible Maven Compiler Plugin versions, configuring `multiReleaseOutput` on the branch execution can place output under the versioned directory.

### 30.1. Check Plugin Versions Instead of Copying Any Random POM

Maven Compiler Plugin and Maven JAR Plugin have features/parameters that change across releases. For example, `multiReleaseOutput` or automatic `Multi-Release` detection must be checked against the **actual plugin version**. Do not take an old snippet and assume it remains valid across all major versions.

Model example:

~~~text
compile-main:
  source roots = src/main/java
  release      = 8
  output       = target/classes

compile-java17:
  source roots = src/main/java17
  release      = 17
  output       = target/classes/META-INF/versions/17

jar:
  inputs       = target/classes
  manifest     = Multi-Release: true
  validate     = after packaging
~~~

This is a **configuration model**, not a copy-pasteable POM file. When applying it, you must manage source roots, generated sources, compiler executions, dependencies, and lifecycle phases appropriately for your release/plugins.

### 30.2. Test Using a Different JVM Than the Maven Runtime

Maven can run on JDK 21 while compiling the root with `--release 8`. Plugin/test forks can also run on different JVMs. If CI only runs `mvn test` on JVM 21, the base branch is not tested end-to-end on Java 8 merely because of compiler target 8.

To test Java 8 and 17, configure test runners/toolchains or a CI matrix that actually uses those JVMs.

## 31. Gradle: Source Sets and Packaging Tasks

With Gradle, you can create a separate compilation task for the branch using toolchains and an appropriate `options.release`. **Illustrative Groovy DSL skeleton** example:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 8
}

def compile17 = tasks.register('compileJava17', JavaCompile) {
    source = fileTree('src/main/java17')
    classpath = files(sourceSets.main.output, configurations.compileClasspath)
    destinationDirectory = layout.buildDirectory.dir('classes/java/java17')
    javaCompiler = javaToolchains.compilerFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
    options.release = 17
}

tasks.named('jar', Jar) {
    dependsOn compile17
    manifest {
        attributes('Multi-Release': 'true')
    }
    from(compile17.flatMap { it.destinationDirectory }) {
        into 'META-INF/versions/17'
    }
}
~~~

This is an example task setup for a simple Java project, not a complete production configuration. It assumes a Gradle version supporting the APIs used and appropriate JDK/toolchains; source directories, dependency classpaths, test source sets, and reproducibility settings must be adjusted per project.

**Important:** `options.release = 8` is set for JavaCompile tasks in general, so the `compileJava17` task must override it to 17 as shown in the example. Do not let a later-applied rule accidentally alter the branch's `release`.

### 31.1. Separate Compile and Test Tasks

CI can run:

~~~text
assemble MRJAR
validate JAR
testOnJava8  -> root selected
testOnJava17 -> Java17 selected
testOnJava21 -> Java17 fallback (if there is no 21 branch)
~~~

The existence of a Gradle Java toolchain does not automatically run all JVM test variants. You must explicitly create/declare Test tasks or CI jobs per your support policy.

## 32. API Parity Checks Do Not Equal Runtime Behavior Verification

Suppose `jar --validate` succeeds. That still leaves questions:

- Does branch 17 use an API that no longer works properly on JDK 21?
- Is a custom class loader failing to select the right branch?
- Do reflection frameworks/JSON serializers read fields/annotations the same way?
- Are service resources and module descriptors right?
- Is there JDK-specific behavior in security, TLS, locale, timezone, or file handling?
- Are native/JNI/agent dependencies compatible?
- Do performance regressions exceed the budget?

Therefore, the pipeline must have **two independent gates**:

**Gate 1 — Structural/packaging/API:** manifest, entries, class versions, exported signatures, and module constraints.

**Gate 2 — Execution/behavior:** the same contract tests executed on target JDKs and deployment environments.

An MRJAR that is “structurally valid” yet tested only on Java 21 cannot be declared as supporting Java 8.

## 33. Common Failures and Where to Investigate

| Symptom | Likely cause | Investigation step |
| --- | --- | --- |
| Java 17 still runs root implementation | Manifest missing `Multi-Release: true` or loader unsupported | Check manifest, final JAR, launcher |
| Java 8 reports `UnsupportedClassVersionError` | Root contains bytecode higher than Java 8 | `javap -verbose` root, compile release |
| Java 17 reports `UnsupportedClassVersionError` | `versions/17` contains major >61 | Check compile task, artifact entry |
| `NoSuchMethodError` on only one JDK | API or inter-branch helper mismatch | `javap --multi-release`, class loading |
| `NoSuchFieldError` when consumer changes runtime | Field API diverges across variants | API diff, consumer binary tests |
| `ClassNotFoundException` from higher branch | Branch references missing class/dependency | `jdeps --multi-release`, module/classpath |
| `jar --validate` reports differing APIs | Public/protected signatures diverge | Compare root and branch with `javap` |
| Tests pass from build dir but fail on packaged JAR | Layout or manifest lost/wrong | Run tests against final JAR |
| Framework cannot find service provider | Provider config versioned improperly | Inspect `META-INF/services`, ServiceLoader |
| Module path fails, classpath passes | `module-info.class`, exports/opens/requires | `jar --describe-module`, JPMS tests |
| Shaded JAR loses branch 17 | Packaging tool drops entries or rewrites manifest | Inspect final artifact tree |
| Coverage tool fails on root-compatible JAR | Scanner tries to parse all classes in versions/21 | Upgrade bytecode tool or use MRJAR-aware filtering |
| Java 21 result differs from Java 17 | Behavioral drift, defaults/locale/serialization | Golden fixtures, integration tests |
| Native agent fails on newer Java | Agent/ASM/JNI does not support runtime | Agent support matrix, class-file version |

One symptom can have multiple causes. First identify **which class file and JAR are actually loaded**, then adjust the build.

## 34. Targeted Diagnostic Commands

### 34.1. Inspect Structure and Manifest

~~~bash
jar --list --file build/library.jar
jar --validate --file build/library.jar
~~~

If you need to view the manifest, you can extract it for inspection in a permitted temporary workspace or use an appropriate ZIP/JAR inspection tool. Do not modify a signed JAR directly just to inspect its manifest.

### 34.2. Inspect API and Bytecode per Branch

~~~bash
javap --multi-release base \
  -classpath build/library.jar -public -s example.api.Feature

javap --multi-release 17 \
  -classpath build/library.jar -public -s example.api.Feature

javap --multi-release 21 \
  -classpath build/library.jar -public -s example.api.Feature
~~~

### 34.3. Inspect Dependencies per Branch

~~~bash
jdeps --multi-release base \
  --summary build/library.jar

jdeps --multi-release 17 \
  --summary build/library.jar
~~~

### 34.4. Identify the Runtime/JVM Used

~~~bash
java -version
javac -version
jar --version
~~~

In CI, record the JDK vendor/build/runtime image; `java -version` on a developer machine does not prove production containers use the same JVM.

### 34.5. Inspect Class Loading at Runtime When Needed

On JDKs supporting unified logging:

~~~bash
java -Xlog:class+load=info \
  -cp build/library.jar:build/consumer-classes \
  example.consumer.Main
~~~

Logs can be verbose and detail varies by JVM; choose appropriate log levels/destinations, store data safely, and combine with inspection of the final JAR.

## 35. The Test Matrix Should Extend to Packaging Environments

For libraries used on both classpath and module path, or distributed via fat JARs and application servers:

| Test dimension | Typical values |
| --- | --- |
| Runtime JDK | Java 8, 11, 17, 21 per support policy |
| Packaging | Original MRJAR, shaded JAR, nested/executable JAR if used |
| Loading mode | Classpath, module path, custom loader if supported |
| Consumer | Compile against base API, compile against highest supported API |
| Behavior | Unit contract, integration, reflection/serialization |
| Tooling | JAR validator, API diff, jdeps, coverage, scanner |
| Architecture | OS/container/JDK vendor if dependencies are affected |
| Security | Signature, provenance, modules, TLS/crypto when relevant |

There is no need to multiply the matrix infinitely. Choose **the combinations genuinely committed to by the product** and high-risk boundaries. For example, Java 8 × module path is not a valid combination under JPMS, so do not put it into test requirements as though a module path exists on Java 8.

### 35.1. Key Point: Test the Artifact After Packaging

Projects often compile each branch successfully and test each output directory separately; yet bugs appear when the JAR Plugin/Shade Plugin creates the final artifact. Therefore you must have tests using the **actual release JAR** and production-like class loader configuration.

## 36. Controlled MRJAR Release Process

1. **Lock down the minimum Java level** and supported runtime JDKs.
2. **Design the public API once**; document the public/protected contract in the root module.
3. **Separate source sets for each branch**, keeping differing implementations internal.
4. **Compile each branch with its corresponding `--release N`**; root must not use newer APIs.
5. **Package** the manifest and versioned directories properly.
6. **Inspect the final JAR** with `jar --list` and `jar --validate`.
7. **Compare API views** using `javap --multi-release` or an MRJAR-aware diff tool.
8. **Analyze dependencies** per branch with `jdeps --multi-release`.
9. **Run consumer compatibility tests** across supported runtimes/JDKs.
10. **Run behavioral/integration tests** with the final artifact, including resource, service, module, and agent paths if applicable.
11. **Verify shading/signing/provenance** and build plugin versions.
12. **Canary or staged release**, monitoring errors, performance, and compatibility metrics.

Turn these steps into a reproducible pipeline with logs, checksums, and artifact lineage; do not rely on manually copying `.class` files on a developer's machine.

## 37. Reviewer Checklist

- [ ] Clear rationale for using an MRJAR instead of simply raising minimum Java or splitting artifacts.
- [ ] Root classes actually run on the declared minimum runtime.
- [ ] Every branch properly uses `META-INF/versions/N` with `N >= 9`.
- [ ] Final JAR manifest has `Multi-Release: true` in the main section.
- [ ] Class-file major version does not exceed the branch's Java release.
- [ ] No public/protected APIs added, removed, or changed in type per branch.
- [ ] Public/protected classes and exported packages follow the JAR spec counterpart rule.
- [ ] Modular/non-exported package exceptions (if any) are used intentionally.
- [ ] Generics APIs, bridge methods, inheritance, and annotations/reflection are evaluated when consumers rely on them.
- [ ] Public constants do not change values per runtime in a way that breaks binary/semantic contracts.
- [ ] Root does not depend on Java 9+/17+/21+ APIs or helper classes only present in higher branches.
- [ ] Higher branches do not use Java release APIs newer than that branch's own level.
- [ ] Inter-branch fallback and helpers are tested.
- [ ] `jar --validate` passes on the final artifact.
- [ ] `javap --multi-release`/API diff has compared the public API across every supported view.
- [ ] `jdeps --multi-release` has checked critical dependencies of each view.
- [ ] Consumer tests compiled against the base API run across the declared JVM matrix.
- [ ] Tests run on real JDKs, not merely by changing selection-simulation properties.
- [ ] Contract tests cover null/empty/boundaries/concurrency and runtime-specific behavioral differences.
- [ ] Serialized/persisted data is cross-read tested if the application requires rollback/interoperability.
- [ ] Resource and ServiceLoader behavior does not rely on improperly versioning `META-INF/services`.
- [ ] Module descriptor/exports/opens are verified when the JAR is used on the module path.
- [ ] Custom class loaders and nested JAR/fat JARs have verified evidence of actually supporting MRJAR.
- [ ] Shading, obfuscation, and signing do not unintentionally drop or alter entries.
- [ ] Build tool/compiler/test/coverage plugins are pinned to compatible versions.
- [ ] CI tests the final post-packaging artifact, not just classes folders.
- [ ] Release notes document supported Java levels and notable branch-specific behavior.

## 38. Common Misconceptions

**“An MRJAR allows new APIs on newer Java in the same JAR.”** That is not a valid purpose of an MRJAR: the exported public API must be uniform across releases.

**“Just creating `versions/8` creates a Java 8 branch.”** False. Root is the base; valid versioned directories start at 9.

**“Java 21 always selects the `versions/21` directory.”** Only if the corresponding entry exists; otherwise the JVM falls back to lower branches/root.

**“The manifest does not matter if versioned classes already exist.”** False. `Multi-Release: true` is the signal for runtimes/tooling to recognize an MRJAR.

**“Placing a major 65 class under `versions/17` will run on Java 17.”** False. Directory names do not make a class file compatible.

**“A new public method intended only for Java 21 is an internal optimization.”** False if the exported API differs between versions; that must be solved through separate API versioning.

**“Keeping API signatures identical guarantees behavior is always compatible.”** False. Constants, serialization, annotations, locale, security, and concurrency can still differ.

**“`jar --validate` passing means everything is fine.”** Not enough. The specification does not require the validator or JVM to verify all API semantics; runtime/contract tests are still needed.

**“One unit test on JDK 21 covers all branches.”** False. The root and branches 9/17 may not have been executed at all.

**“The same JAR version means the class loader definitely loads the same bytecode.”** False. MRJAR intentionally swaps bytecode per runtime.

**“`ZipFile` or custom scanners surely understand runtime branch selection.”** False. Tools may only look at physical entries or the base.

**“`META-INF/services` can be versioned like normal resources.”** False under MRJAR rules for `META-INF`.

**“Branch 21's module descriptor can export any new packages.”** Not an arbitrary change: versioned module descriptors have strict constraints.

**“Shading preserves MRJAR as long as `.class` files still exist.”** Not sufficient; manifest, directory layout, relocation, and loader behavior must all be checked.

**“Root's `--release` guarantees every dependency supports minimum Java.”** False. Third-party JARs may require a newer runtime.

## 39. Technical Documentation and Tool Limitations

Refer to release-specific documentation when building or reviewing an MRJAR:

- **OpenJDK JEP 238 — Multi-Release JAR Files:** design mechanism and goals.
  https://openjdk.org/jeps/238
- **Java JAR File Specification — Multi-release JAR files:** manifest, layout, selection, class-file constraints, exported API, and modular exceptions.
  https://docs.oracle.com/en/java/javase/25/docs/specs/jar/jar.html
- **`jar` Tool Guide:** `--release`, `--validate`, packaging, and integrity.
  https://docs.oracle.com/en/java/javase/25/docs/specs/man/jar.html
- **`javap` Tool Guide:** `--multi-release`, descriptors, and disassembly.
  https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
- **`jdeps` Tool Guide:** `--multi-release`, dependency analysis, and JDK internals.
  https://docs.oracle.com/en/java/javase/25/docs/specs/man/jdeps.html
- **Apache Maven — Guide to Multi-Release JARs:** compiler executions and JAR packaging.
  https://maven.apache.org/guides/mini/guide-multi-release-jars.html
- **`java.util.jar.JarFile` API:** runtime version views and how tooling opens MRJARs.
  https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html
- **Gradle Java Toolchains and JavaCompile documentation:** release-specific compile tasks and packaging task graph.

These links point only to technical documentation, not a locked-in plugin version table for every project. When migrating, verify actual plugin/JDK vendor/tool versions.

## 40. Conclusion

Multi-release JARs allow a library to maintain a **low minimum Java level** while using **specialized implementations** on newer runtimes. Yet this flexibility comes with an essential rule: **the exported public API must remain consistent across branches**; a library must not turn itself into multiple different API versions simply because the JVM picks an entry in `META-INF/versions/N`.

A safe workflow keeps the root and each branch at appropriate compile releases, packages the manifest properly, compares API views at the bytecode level, analyzes dependencies, and **runs the same contract tests on each real JDK**. At the same time, it must check cross-branch fallback, resource/module loading, shading, signing, and the actual post-packaging artifact.

Treat an MRJAR as **one library with multiple execution paths**, not a simple JAR with a few extra class files. Only when every execution path preserves the public contract and is verified across all committed runtimes can JDK upgrades and multi-environment library distribution rest on a reliable foundation of compatibility and operation.
