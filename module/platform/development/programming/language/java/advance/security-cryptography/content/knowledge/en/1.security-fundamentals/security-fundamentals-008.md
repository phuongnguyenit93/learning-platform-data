# 1.8. Java 21 Lab Environment and Checking APIs Against JDK Versions

This lesson sets up the **Java 21** lab environment for the Security & Cryptography module, and shows how to verify whether a security class, method, or algorithm is actually present in **the Java version and JDK you are using**. This is a foundational step before studying `MessageDigest`, `Cipher`, `Signature`, `KeyStore`, TLS/JSSE, and newer APIs.

## Lesson Objectives

- Install and select the right **JDK 21**, verifying that `java`, `javac`, `jshell`, your IDE, and build tools use the matching version.
- Compile and run a simple Java 21 program using the standard library and a cryptographic API.
- Cross-check APIs via the **Java SE 21/JDK 21 documentation**, `Since` tags, modules, method signatures, and `javac --release`.
- Distinguish **API existence**, **bytecode compatibility**, and **algorithms/providers actually available at runtime**; avoid misconceptions when developing cryptographic applications.

## 1. Understanding the Three Version Layers

| Layer to Check | Tool or Source | Meaning |
| --- | --- | --- |
| JDK used for development | `javac -version`, Project SDK/toolchain settings | Determines the compiler and available tools. |
| Java used at runtime | `java -version`, `Runtime.version()` | Determines the execution runtime, active standard modules, and security providers. |
| Minimum Java supported by the product | `javac --release 21`, testing on target runtime | Constrains language syntax, platform APIs, and allowed class-file version. |

A **JDK** includes the compiler (`javac`), runtime (`java`), analysis tools (`javap`, `jdeps`), quick REPL (`jshell`), `keytool`, and standard libraries/modules. Installing only a runtime without a compiler is insufficient for the labs. "Java 21" is the major release line; patch numbers like `21.0.x`, JDK vendors, and OS/architectures may differ. Prefer recent security updates in the 21 line from trusted distributors.

**Note:** the JDK selected in a terminal may differ from the JDK used by your IDE, Maven, Gradle, background services, or containers. Concluding "running Java 21" must be based on the environment **actually compiling and running the program**.

## 2. Preparing JDK 21 and Checking Paths

1. Download and install a **JDK 21** compatible with your OS (e.g., Oracle JDK 21 or a supported OpenJDK 21 distribution such as Eclipse Temurin). Pick the right CPU architecture; verify the vendor and apply security patches.
2. Set `JAVA_HOME` pointing to the **JDK root directory** (the folder containing `bin`), and add `JAVA_HOME/bin` to `PATH` according to your OS mechanism.
3. Open a new terminal and run:

```text
java -version
javac -version
jshell --version
```

The expected output shows **major version 21** across all three commands (exact strings vary by vendor, patch level, and OS). `java -version` and `javac -version` must match the chosen environment.

Verify which executables the terminal resolves:

```powershell
# Windows PowerShell
where.exe java
where.exe javac
$env:JAVA_HOME
```

```bash
# Linux / macOS
command -v java
command -v javac
printf '%s\n' "$JAVA_HOME"
```

If multiple JDKs are installed, `where.exe` may list multiple paths: the highest-priority entry on `PATH` normally determines the active command. On Linux/macOS, `command -v` locates the command entry point; it may be a symlink, so inspect links/Java home per your system setup.

```text
java -XshowSettings:properties -version
```

In the properties output, inspect `java.home`, `java.vendor`, `java.version`, and `os.arch`; this confirms the active runtime. The command prints many lines, so check only the relevant properties. When working with IDEs/build tools, inspect their SDK/JDK settings and actual execution commands, not just the terminal.

**Minimum toolset:** terminal, editor/IDE, JDK 21, and a directory for `.java` files. No external cryptography libraries are needed yet to test standard APIs like `MessageDigest` or `Cipher`.

## 3. First Lab: Compiling and Probing a Cryptographic API

Create **`ApiProbe.java`** (filename must match `public class ApiProbe`):

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import javax.crypto.Cipher;

public class ApiProbe {
    public static void main(String[] args) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest("Java 21".getBytes(StandardCharsets.UTF_8));

        // Only verifies an implementation of the transformation exists; does not encrypt data yet.
        Cipher.getInstance("AES/GCM/NoPadding");

        System.out.println("Runtime feature: " + Runtime.version().feature());
        System.out.println("SHA-256 bytes: " + digest.length);
        System.out.println("Hex characters: "
                + HexFormat.of().formatHex(digest).length());
        System.out.println("AES/GCM available: true");
    }
}
```

From the folder containing the file, run:

```text
mkdir out
javac --release 21 -encoding UTF-8 -d out ApiProbe.java
java -cp out ApiProbe
```

On a **standard JDK 21 with a provider supporting AES/GCM**, the output is:

```text
Runtime feature: 21
SHA-256 bytes: 32
Hex characters: 64
AES/GCM available: true
```

Explanation:

- `--release 21` instructs the compiler to check Java 21 syntax and platform APIs while emitting Java 21 bytecode. `-encoding UTF-8` avoids depending on the machine's default charset; `-d out` places `.class` files in a separate folder.
- `java -cp out ApiProbe` runs the compiled class on whatever runtime `java` points to. If the runtime is Java 24, `Runtime feature` prints `24` even though bytecode was compiled with `--release 21`.
- SHA-256 always yields 256 bits = **32 bytes**; unseparated hexadecimal uses **64 characters**. `HexFormat` is a standard API introduced in Java 17.
- `Cipher.getInstance("AES/GCM/NoPadding")` requests a **transformation** from a security provider. This only proves a provider supplies the transformation; it **does not** test key usage, IV/nonce handling, AAD, or encryption workflow security. If no provider supports the transformation, it throws an exception instead of printing the last line.

`Runtime.version().feature()` reveals the current runtime version; it does not confirm which version compiled the code. Keep those two facts separate when reporting environment issues.

## 4. Cross-Checking an API Against a JDK Version: Five-Step Process

Suppose you encounter an example using `javax.crypto.KEM` or `java.util.HexFormat` and want to know whether it runs on Java 17/21.

**Step 1 — Identify the exact fully qualified name.** Note the package, class name, and specific method/overload. For instance, `javax.crypto.KEM.getInstance(String)` is more precise than saying "KEM." A class may exist in an older release while a **specific method** was added later.

**Step 2 — Open documentation tied to the target version.** For Java 21, use the [Java SE 21 & JDK 21 API Specification](https://docs.oracle.com/en/java/javase/21/docs/api/). Locate the exact class and read in order:

- `Module` and `Package` (e.g., `javax.crypto.KEM` belongs to `java.base`).
- Purpose description, methods, parameter types, return types, and checked exceptions.
- `Since` of the **class** and, where present, of the specific **constructor/method/field** used.
- `Deprecated`, `forRemoval`, preview/incubator requirements (if any), provider requirements, or implementation notes.

**Step 3 — Compare with older and active versions.** Java 17 and Java 21 docs can differ. For example:

| API | Info from Official Docs | Conclusion |
| --- | --- | --- |
| `java.util.HexFormat` | `Since: 17` | Present in platform APIs from Java 17 onward. |
| `javax.crypto.KEM` | `Since: 21` | Not in Java 17 APIs; code referencing this class requires a Java 21 or newer baseline. |
| `java.security.MessageDigest` | Long-standing API, but algorithms depend on providers | Having the class does not mean every algorithm name is supported. |

Reading `Since` reveals **when the API was introduced**. It does not guarantee identical behavior across all patches, providers, or vendors. When a requirement targets a specific version, consult documentation for that **exact version** rather than generic web searches (which may return docs for Java 22/25/26...).

**Step 4 — Let the compiler verify compatibility.** Use `--release` with the Java level your application supports. This is stronger than checking a single doc page.

**Step 5 — Verify on the target runtime.** For security APIs, runtime checks must confirm providers, security policy settings, algorithms, and working parameters. A clean build only proves the code compiles against APIs at compile time; it does not guarantee the algorithm works at runtime.

## 5. Testing Precisely with `--release`: An API Introduced in Java 21

According to the [Javadoc of `javax.crypto.KEM` for Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.html), the `KEM` class has `Since: 21`. Create **`VersionGate.java`**:

```java
import javax.crypto.KEM;

public class VersionGate {
    public static void main(String[] args) {
        System.out.println(KEM.class.getName());
    }
}
```

Using a **JDK 21 compiler**, run sequentially:

```text
mkdir out17
javac --release 17 -d out17 VersionGate.java
```

The command above **must fail** because `javax.crypto.KEM` was not yet in the Java 17 API (exact error message varies; usually includes `cannot find symbol`). Next:

```text
mkdir out21
javac --release 21 -d out21 VersionGate.java
java -cp out21 VersionGate
```

Output when run on Java 21 or later:

```text
javax.crypto.KEM
```

This example only references the **API type**; it does not call `KEM.getInstance(...)` and does not prove a specific KEM algorithm is available. That is an important distinction between **having the `KEM` class** and **having a provider supporting a KEM algorithm**.

### Why Use `--release` Instead of `--source` and `--target`?

- `--source 21` checks Java 21 syntax; `--target 21` selects output bytecode version. When compiling with a newer JDK, this pair **does not fully restrict standard APIs to Java 21**.
- `--release 21` combines language rules, bytecode level, and **public APIs of platform release 21**. For code targeting Java 21, this is the right choice.
- `--release` only accepts levels supported by the **current compiler**. JDK 17 cannot compile with `--release 21`; use a sufficiently recent JDK compiler. Nor can JDK 21 target arbitrary future releases.
- This flag does not check third-party dependency APIs, native libraries, reflection, runtime config, or cryptographic algorithm availability.

Code compiled for Java 21 typically has class-file major version **65**. You can run `javap -verbose out/ApiProbe.class` and look for `major version`; however, the class-file version only reflects bytecode format, **not** runtime library/provider checks. An older runtime unable to read newer class files throws `UnsupportedClassVersionError`.

## 6. Three Separate Questions When Working with Java Cryptography

**Question A: Does Java have this class and method?** Read the target version's Javadoc, `Since`, module/exports, and test with `javac --release`. For example, `java.security.MessageDigest`, `java.security.Signature`, and `javax.crypto.Cipher` are all standard JDK APIs.

**Question B: Does the runtime have the needed algorithm/provider?** JCA/JCE uses the **provider** mechanism. `MessageDigest.getInstance("SHA-256")` and `Cipher.getInstance("AES/GCM/NoPadding")` look up implementations. Standard algorithm names, policies, and providers can differ across JDK releases or deployment configs. `NoSuchAlgorithmException` or `NoSuchPaddingException` requires checking **the actual service/transformation name and providers**, rather than assuming the Java class is missing.

**Question C: Is the algorithm usage secure and protocol-compatible?** Having a provider with the algorithm is only a prerequisite. You must still select key size, nonce/IV, mode, padding, encoding, key storage rules, and error handling properly. For example, AES/GCM requires never reusing a nonce with the same key; calling `getInstance` does not check that rule.

To inspect providers without changing configuration, create **`ProviderProbe.java`**:

```java
import java.security.MessageDigest;
import java.security.Provider;
import java.security.Security;
import javax.crypto.Cipher;

public class ProviderProbe {
    public static void main(String[] args) throws Exception {
        for (Provider provider : Security.getProviders()) {
            System.out.println("Provider: " + provider.getName());
        }
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        System.out.println("SHA-256: " + digest.getProvider().getName());
        Cipher aesGcm = Cipher.getInstance("AES/GCM/NoPadding");
        System.out.println("AES/GCM: " + aesGcm.getProvider().getName());
    }
}
```

Run:

```text
javac --release 21 -d out ProviderProbe.java
java -cp out ProviderProbe
```

Provider names and order in the output **depend on the runtime**, so do not assume a fixed stdout. Some environments include OS, hardware, third-party, or FIPS providers. For portability, usually call `getInstance("...")` **without hardcoding a provider name**; specify a provider only when system requirements demand it and the deployment environment is tested. Avoid editing `conf/security/java.security` just to "make an example run"; understand the configuration and root cause first.

**Three types of documentation to read together:**

1. [Java 21 API Specification](https://docs.oracle.com/en/java/javase/21/docs/api/) — classes, methods, `Since`, modules, and API contracts.
2. [Java 21 JCA Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-cryptography-architecture-jca-reference-guide.html) and [JDK Providers Documentation](https://docs.oracle.com/en/java/javase/21/security/oracle-providers.html) — provider resolution, service lists, and implementations bundled with Oracle JDK 21.
3. [Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/21/docs/specs/security/standard-names.html) — naming conventions for algorithms, transformations, keystores, and security APIs.

**Do not equate "standard name" with "guaranteed in every provider."** The standard names spec defines naming; provider documentation and runtime tests tell you what is actually implemented.

## 7. Command-Line Tools Supporting Cross-Checking

| Tool | Example | Value and Limitations |
| --- | --- | --- |
| `java` | `java --version` | Identifies the runtime invoked from the terminal. |
| `javac` | `javac --release 21 ...` | Verifies code fits Java 21 API/syntax scope; emits bytecode. |
| `jshell` | `jshell` then `Runtime.version()` | Quick expression/API checks; use the same JDK you intend to test. |
| `javap` | `javap -public javax.crypto.KEM` | Inspects public members of a class in the active JDK; does not replace `Since`. |
| `jdeps` | `jdeps --jdk-internals out` | Finds dependencies on JDK internal APIs in compiled classes; does not check cryptographic strength. |
| `keytool` | `keytool -help` | Familiarizes with key/certificate management tool; no need to generate real keys in this lesson. |

`java --list-modules` lists runtime modules. `java --describe-module java.base` or `javap` helps inspect installed modules/classes; for Java 21 APIs, still cross-check Javadoc because a newer JDK may include APIs absent from release 21.

Never use internal `sun.*` or `com.sun.*` packages as substitutes for standard APIs merely because you saw the classes when inspecting the JDK. Internal APIs can be encapsulated, changed, or blocked at runtime. `jdeps --jdk-internals` helps catch such issues, though "none found" does not prove full compatibility with a release.

## 8. Syncing IDEs and Build Tools

If a project uses Maven, configure the Java release level (snippet in `pom.xml`):

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

Check `mvn -version` to see which Java Maven runs on and ensure the Maven Compiler Plugin supports `release`. If the project defines separate plugin/toolchain configs, keep them aligned on version 21.

If using Gradle Groovy DSL, declare a Java toolchain:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Toolchains pick a suitable JDK for related tasks; you need a compatible Gradle/plugin version and an installed or resolvable JDK 21. The runtime used to **execute the application** must still be verified separately. In your IDE, inspect **Project SDK**, **language level**, **compiler/build JDK**, test configs, and run configs. After changing JDKs, re-run the actual build command and verify `java -version` in the execution environment.

## 9. Common Errors and How to Isolate Them

| Symptom | Common Cause | Check / Remediation Step |
| --- | --- | --- |
| `javac` not found | Full JDK not installed or `PATH` lacks JDK `bin` | Check `JAVA_HOME`, `where.exe javac` / `command -v javac`. |
| `release version 21 not supported` | Active compiler is older than Java 21 | Check `javac -version` and IDE/Maven/Gradle JDK; pick JDK 21 or newer. |
| `cannot find symbol` on a JDK API | API added in a newer release; wrong package/signature; or lower `--release` build | Check `Since`, overload signature, and test the target `--release`. |
| `UnsupportedClassVersionError` | Runtime older than class-file version | Compare `java -version`, `javac --release`, and `javap -verbose`; run on compatible runtime or target lower baseline. |
| `NoSuchAlgorithmException` / `NoSuchPaddingException` | Current provider lacks the algorithm/transformation name or name is misspelled | Check Java Security Standard Algorithm Names, registered providers, and actual JDK config. |
| `ClassNotFoundException` / `NoClassDefFoundError` | Wrong classpath/module-path or missing runtime dependency | Verify `-cp`, JARs/modules, and packaged dependencies. |
| `package ... is not visible`, `InaccessibleObjectException` | Module/reflection access restriction, often involving internal APIs | Switch to supported public APIs; review exports/opens and module config rather than long-term workarounds. |
| Terminal works yet IDE/build fails | Different processes pick different JDKs/toolchains | Check JDK at every layer: IDE, compiler plugin, test runner, runtime container. |

**Distinguishing library namespaces:** the `javax.crypto` namespace is part of Java SE; that does not mean every package starting with `javax.` belongs to Java SE. `jakarta.*` libraries or third-party crypto libraries require **separate** dependencies and version checks outside `--release` scope.

## 10. Self-Check Exercises and Completion Criteria

1. Save the output of `java -version`, `javac -version`, and executable paths. Explain why an IDE can use a different JDK from the terminal.
2. Compile/run `ApiProbe.java` with `--release 21`. Explain why 32 SHA-256 bytes turn into 64 hexadecimal characters, and why `Cipher.getInstance` is not yet a secure encryption test.
3. Look up Java 21 Javadoc for `HexFormat` and `KEM`, identify their `Since` values, then test `VersionGate.java` with `--release 17` and `--release 21`.
4. Run `ProviderProbe.java`, noting the actual provider names for SHA-256 and AES/GCM on your machine. Compare with the JDK Providers Documentation and explain why another machine might report different providers.
5. Pick one security API yourself (such as `java.security.Signature` or `java.security.KeyStore`), and record **fully qualified name → method → Since → module → target release → required provider/runtime test**.

You have completed this lesson when you can clearly answer: **"Which JDK am I compiling with, which JDK am I running on, which release introduced this API, and which runtime supplies the actual algorithm?"**

### Official References (Pinned to Java/JDK 21)

- [Java SE 21 & JDK 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/)
- [JDK 21 Tool Specifications, including `javac`, `javap`, and `jdeps`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/index.html)
- [`javac` JDK 21: meaning of `--release`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [`HexFormat` (Since 17)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HexFormat.html)
- [`KEM` (Since 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.html)
- [JCA Reference Guide JDK 21](https://docs.oracle.com/en/java/javase/21/security/java-cryptography-architecture-jca-reference-guide.html)
- [JDK Providers Documentation JDK 21](https://docs.oracle.com/en/java/javase/21/security/oracle-providers.html)
