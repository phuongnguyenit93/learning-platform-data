# Why -target Alone Does Not Guarantee API Availability on Older Java

## 1. Where Does the Real Problem Lie?

Suppose a project must run on **Java 8**, while the developer uses JDK 21 to compile. They see that the compiler generates a `.class` file with **major version 52** (the class-file format corresponding to Java 8), and conclude the program will definitely run on Java 8.

That conclusion is wrong if the source code calls an API that only appeared in a newer Java version, for example `String.repeat(int)` added in **Java 11**. A Java 8 JVM understands the major 52 class-file format, but `java.lang.String` in Java 8 **does not have the `repeat(int)` method** to link and invoke. The program may fail at runtime with `NoSuchMethodError`.

Three conditions must be distinguished:

1. **Allowed grammar/language**: `-source`/`--source`.
2. **Class-file format that older JVMs can load**: `-target`/`--target`.
3. **Platform APIs present in the target Java release**: the Java SE/JDK library supplied to the compile-time type-checking environment, or constrained with `--release`.

`-target` mainly solves question **number 2**, not question **number 3**. On modern JDKs, the commonly recommended way when targeting older Java is **`javac --release <version>`**, while also managing versions of libraries outside Java SE/JDK and running tests on an actually supported runtime.

After this lesson, you can explain why a matching major version can still cause linkage errors, reproduce the error with valid Java 8 code, choose the right `javac` options, and verify the full compile–package–run chain.

## 2. Three Compatibility Axes: Source, Bytecode, and API

| Axis | Option/rule source | Answers the question | Does not guarantee |
| --- | --- | --- | --- |
| **Source language level** | `--source N` | Does the code use syntax/language features valid for Java N? | Whether called APIs exist in Java N |
| **Class file version** | `--target N` | Is the generated `.class` file of a version the target JVM can accept? | Whether called methods/classes exist in Java N runtime |
| **Platform API level** | `--release N`, or suitable old platform classes configuration | Compiler checks source under language N, produces class file N, and sees only the platform API set corresponding to N | That third-party JARs or the runtime environment are definitely compatible |

For example, `List.of(...)` is an API added in Java 9; `String.repeat(int)` has been available since Java 11; `String.formatted(Object...)` since Java 15. These calls can be written using very old Java syntax: their failure when targeting older Java stems from **missing APIs**, not from lambda, record, or switch expression syntax.

**The bytecode format does not assert “all referenced APIs exist on Java 8”.** A class file contains symbolic references to classes, fields, and methods. The virtual machine must resolve those references during linking or when executing the relevant operation. A reference may be valid in the class file yet fail to find the method on an older runtime.

## 3. What Exactly Does -target Control?

Example on JDK 21:

```bash
javac --source 8 --target 8 -d out-target ApiLeak.java
```

- `--source 8` instructs parsing source code under Java 8 language rules.
- `--target 8` instructs generating class files for Java 8, usually with **major version 52**.
- Without locking the platform APIs, the compiler running on JDK 21 can still see API methods from JDK 21 when analyzing and resolving calls in the source.

This does **not** mean `-target 8` alone is always a valid command. On a modern `javac` whose default `--source` level is newer than Java 8, `--target 8` by itself may be rejected because **target cannot be lower than source level**. Adding `--source 8` lets the command satisfy the source/target version constraint, yet **still does not solve API control**.

A table of commonly seen class-file versions:

| Java release | Class-file major version |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

This table helps determine a JVM's ability to read the class-file format. It says nothing about whether `String.repeat`, `java.net.http.HttpClient`, or third-party APIs exist on the machine that will run the program.

The `javap -verbose` command can read `major version` and symbolic references. Even when the major version is right, you still need to check API dependencies.

## 4. Complete Example: Java 8 Bytecode Mistakenly Calling a Java 11 API

Create a file named **`ApiLeak.java`**:

```java
public class ApiLeak {
    public static void main(String[] args) {
        System.out.println("ha".repeat(3));
    }
}
```

There is no new syntax like records or text blocks in the example. The noteworthy part is **the `String.repeat(int)` call**, added in Java 11.

### 4.1. Compiling with JDK 21 using source and target 8

```bash
javac --source 8 --target 8 -d out-target ApiLeak.java
```

On JDK 21, this command can compile successfully: the compiler parses syntax at the Java 8 level, generates a Java 8 class file, yet finds the `repeat(int)` method in the Java SE API that JDK 21 provides to compilation. `javac` may print a warning about legacy source/target choices or bootstrap classpath; **do not rely on the verbatim warning text as a fixed rule**.

Try running with Java 21:

```bash
java -cp out-target ApiLeak
```

**Stdout when running on Java 21:**

```text
hahaha
```

Because the Java 21 runtime has `String.repeat(int)`.

### 4.2. Inspecting the class file: old version, new reference

```bash
javap -verbose -classpath out-target ApiLeak
```

Find the relevant part in the output. You will see a structure similar to:

```text
major version: 52
...
Methodref ... java/lang/String.repeat:(I)Ljava/lang/String;
```

This is an **illustrative excerpt of the relevant lines**, not the full output: constant-pool indexes and instruction offsets may differ. This pair of facts proves something crucial:

- The class file has version **52**, compatible with the Java 8 format.
- The contents still contain a symbolic reference to `java/lang/String.repeat(int)`, a method that does not exist in Java 8.

`javap` only reads the class file, so it does not automatically verify whether the method will be provided by a Java 8 runtime.

### 4.3. Running on an actual JRE/JDK 8

If the machine has a Java 8 runtime, use the **specific path to Java 8's `java` executable**; do not assume `java` on `PATH` is Java 8:

```bash
/path/to/jdk8/bin/java -cp out-target ApiLeak
```

The path here is an illustrative placeholder and must be replaced with the real Java 8 executable. Class file version 52 can be loaded by a Java 8 JVM, but when the `String.repeat(int)` call is resolved, the runtime cannot find a matching method. The **expected error type** is:

```text
java.lang.NoSuchMethodError
```

Detailed messages, stack trace formatting, and linking timing can vary across JVMs; do not require an exact fixed stderr string. The main point: this is **not `UnsupportedClassVersionError`**, because the class-file format was already Java 8 compatible. It is an issue of **a missing method in the runtime API**.

If you only have JDK 21, you can still verify class major 52 and the method reference. However, **to claim behavior has been tested on Java 8**, you must actually run the program with Java 8 or an equivalent environment; running on Java 21 must not be treated as sufficient proof.

## 5. Same Source, Using --release 8 to Catch the Error Early

Recompile the source above with the JDK 21 compiler:

```bash
javac --release 8 -d out-release ApiLeak.java
```

This command must **fail at compile time** because `String.repeat(int)` is not in the Java 8 API set visible to the compiler under `--release 8`. The diagnostic will relate to failing to find method `repeat(int)` on `String`; exact wording depends on the `javac` version.

This is the desired difference:

| Command run on JDK 21 | Compile | Why |
| --- | --- | --- |
| `javac --source 8 --target 8 -d out-target ApiLeak.java` | May succeed | Locks source/target 8 but by default does not lock Java 8 platform APIs |
| `javac --release 8 -d out-release ApiLeak.java` | Fails | Compiler checks `String` against Java 8 APIs, where `repeat(int)` does not exist |

With genuinely Java 8-compatible code, such as replacing the `repeat` call with classic string concatenation:

```java
public class CompatibleEight {
    public static void main(String[] args) {
        System.out.println("ha" + "ha" + "ha");
    }
}
```

Compile and run:

```bash
javac --release 8 -d out-eight CompatibleEight.java
java -cp out-eight CompatibleEight
```

**Stdout:**

```text
hahaha
```

The `CompatibleEight` version compiles successfully against Java 8 APIs/language. To complete Java 8 compatibility verification, run it on a Java 8 runtime and execute appropriate tests.

## 6. What Does --release Actually Control?

According to `javac` documentation, `--release N` combines three conditions:

1. Apply the Java language rules corresponding to release N.
2. Emit class files targeting release N.
3. Compile against the **supported and documented Java SE/JDK APIs** of release N.

Example:

```bash
javac --release 11 -d out11 Main.java
```

The command sets the target to Java 11 for language, class-file format, and visible platform API set. It does not mean the program will run on Java 8, or that non-JDK dependencies are automatically Java 11 compatible.

`--release` cannot be combined with `--source` or `--target` in the same invocation:

```bash
# Wrong: two mutually exclusive source/target configuration methods
javac --release 8 --source 8 ApiLeak.java
```

```bash
# Correct: one option selects the entire release
javac --release 8 ApiLeak.java
```

Nor does every JDK release support the same list of older releases. Check:

```bash
javac --help
javac -version
```

The list of valid values is documented per compiler. Do not design builds assuming the newest JDK can target every Java version ever released; very old releases may no longer be supported.

### 6.1. Why is --release more reliable than just source/target?

A `javac` instance can compile Java 8 code against the running JDK's APIs if given only `--source 8 --target 8`. With `--release 8`, the compiler uses platform API data for Java 8, eliminating the chance of accidentally calling `String.repeat`, `List.of`, or other newer Java SE APIs.

This is important because “valid Java 8 syntax” does not mean “the program uses Java 8 APIs”. A method call written with ordinary syntax may not exist in the older release.

### 6.2. What --release does not control

`--release` does not guarantee the entire application will run properly on an older runtime if other factors are involved:

- **Third-party libraries:** a JAR built for newer Java may have too high a class-file version or call APIs missing on the target runtime.
- **Reflection:** code can load classes/invoke methods by string name; the compiler does not fully verify those reflective paths.
- **ServiceLoader, plugins, dynamic class loading:** implementations loaded at runtime may require different APIs/runtimes.
- **Native code/JNI:** native libraries, OS architecture, or DLL/SO versions may not be available.
- **Behavioral compatibility:** the same API exists, yet there are behavior changes, bug fixes, or different environmental conditions.
- **Packaging and runtime config:** classpath/module path, resources, security policy, or entry point may be wrong.
- **Multi-release JARs and dynamically generated bytecode:** you must check the classes selected on the target runtime, not just the main app module.

Therefore, **`--release` is an important build condition, not an end-to-end compatibility certificate**. Combine it with dependency constraints and real tests on the target JRE/JDK.

## 7. Runtime Errors to Distinguish

| Error | Typical situation | Relation to -target and APIs |
| --- | --- | --- |
| `UnsupportedClassVersionError` | Older JVM encounters a class file with too new a major version | `-target`/`--release` directly affects the class file emitted by the compiler |
| `NoSuchMethodError` | Method was referenced in bytecode but does not exist with the expected name/descriptor at link/run time | Class-file format can be completely valid; runtime API/binary mismatch |
| `NoSuchFieldError` | Field referenced by bytecode does not exist in the runtime class | May be due to incompatible API version or binary |
| `NoClassDefFoundError` | JVM cannot find/define a required class during execution | May be due to missing classpath/runtime module or error while defining the class |
| `ClassNotFoundException` | Code explicitly requests to look up a class (e.g., `Class.forName`) but the classloader cannot find it | Often related to dynamic loading, reflection, plugins |
| `AbstractMethodError` | Dispatching to an implementation missing a required method in the binary hierarchy | May be due to binary incompatibility between library versions |

Do not confuse `NoSuchMethodError` with a **compile-time** error like “cannot find symbol”: when compiling with `--release 8`, the compiler rejects it early; when mistakenly compiling with newer JDK APIs, the older runtime only discovers the missing method later.

### 7.1. Why does the JVM accept version 52 yet still fail?

A class file contains a constant pool and symbolic references. For example, `javap -verbose` shows a reference to `java/lang/String.repeat:(I)Ljava/lang/String;`. Major version 52 only tells the JVM that the class-file structure is written in the Java 8 format. It does not force Java 8's API to have a method named `repeat`; when the JVM needs to resolve that reference, the Java 8 runtime has no matching implementation.

### 7.2. Why is it not fixed by “just adding -target 8”?

If compilation uses a newer source level (for instance JDK 21's default), `-target 8` alone can cause a configuration error because target is lower than source. Adding `-source 8` resolves the language-level conflict, yet the missing API problem remains. The right solution when wanting Java 8 compatibility is to set **`--release 8`** (if supported by the JDK), or an appropriate toolchain/bootclasspath with Java 8 APIs and verify on the target runtime.

## 8. Why Is -source/-target Plus Platform Classes an Old, Hard-to-Manage Approach?

Before `--release` existed, to cross-compile properly, one typically had to configure all three:

- `-source` to limit language features;
- `-target` to limit bytecode format;
- the exact **platform classes** of the target JDK so the compiler would not mistakenly see newer APIs.

Targeting **Java 8 and earlier**, some older configurations used `-bootclasspath` pointing to the target JDK's platform class libraries (and related settings). Note: you must not simply grab `rt.jar` from an arbitrary JDK and assume you have a standard environment; the classpath can also involve other platform libraries and the entire toolchain.

For **Java 9 and above**, the platform uses JPMS and system modules; platform configuration differs from the bootclasspath era of Java 8. The `javac` documentation describes `--system` when using `-source`/`-target` in scenarios targeting JDK 9+ that need the appropriate platform classes.

**In modern projects, unless there are special requirements, prefer `--release`.** It significantly reduces the risk of mistakenly using newer APIs because the compiler is running on a JDK newer than the target runtime.

Do not tweak the bootclasspath or use flags that break encapsulation arbitrarily just to make a program “compile pass”. If code relies on internal JDK APIs, identify the support contract and replace them with appropriate public APIs whenever possible.

## 9. Step-by-Step Verification Guide by Layer Using javac, javap, and java

A reproducible workflow:

1. **Select the minimum runtime:** for example Java 8.
2. **Lock the build toolchain:** record `javac -version`, compiler vendor/build, executable path, and how the build tool chooses the JDK.
3. **Lock language and APIs:** use `--release 8` instead of `--target 8` alone.
4. **Record sources and dependencies:** library versions, JAR hashes, annotation processors, generated sources, compile classpath/module path.
5. **Build into a clean directory:** avoid class files from other compilations; check exit codes and stderr.
6. **Use `javap -verbose`:** check major version and suspicious method references.
7. **Run on the actual runtime:** verify `java -version` of the target environment, then run the program and tests.
8. **Compare results:** compiler errors, class-format errors, linkage errors, or logic errors occur at different layers; clearly record which layers passed.

### 9.1. Checking major version

```bash
javap -verbose -classpath out-target ApiLeak
```

Look for the `major version: 52` line and the reference to `String.repeat`. Using `javap` from a newer JDK can read a class file targeting an older JDK; **that does not mean the older runtime definitely has the API the class calls**.

### 9.2. Checking APIs against the target JDK

Running `javac --release 8` causes calls to newer Java APIs to be caught before generating class files. This is the most useful static check when targeting standard Java SE APIs. For external dependencies, verify their binary compatibility separately.

### 9.3. Checking on the actual runtime

Run `java -version` and, if multiple JDKs are present, invoke via the specific executable path. In CI, it is best to have one job compiling with `--release 8` and a test job running on a Java 8 runtime (if Java 8 is still on the project's list of supported platforms).

Running on Java 21 **does not replace** Java 8 testing: Java 21 has more APIs and can load many older class files.

## 10. Applying in Gradle and Maven

### 10.1. Gradle (Groovy DSL)

Example of a project using the Gradle Java plugin, with JDK 21 as the compiler but targeting Java 8 at runtime:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 8
    options.encoding = 'UTF-8'
}
```

This is a **build configuration**, not a standalone Java file. `toolchain` selects a suitable level-21 JDK for Java tool tasks; `options.release = 8` asks the compiler to check source/class format/platform APIs according to Java 8. Ensure the resolved JDK actually supports `--release 8`.

**Do not replace `options.release` by setting only `targetCompatibility = '1.8'` and assuming Java 8 APIs are locked**. In builds with toolchains and multiple source sets, check the different compile tasks such as main/test, processor paths, and resolved dependencies.

### 10.2. Maven Compiler Plugin

Example configuration (requires Maven Compiler Plugin supporting the `release` parameter):

```xml
<project>
  ...
  <properties>
    <maven.compiler.release>8</maven.compiler.release>
  </properties>
  ...
</project>
```

This is an **illustrative configuration snippet** inside a Maven project's `pom.xml`; the `...` markers indicate positions of other XML parts of the POM, not a complete standalone runnable POM file. Record the Maven/plugin versions, actual JDK/compiler, and dependencies. For builds running on very old JDKs, `release` support of the compiler/plugin must be checked for the specific version.

Neither Gradle nor Maven turns a third-party library already compiled for newer Java into a Java 8 binary merely by setting release for the application's source.

## 11. Third-Party Libraries: The Remaining Gap of --release

Suppose the library `lib/modern.jar` was built with Java 17 while the application targets Java 8. Even though `javac --release 8` gives application classes major 52, the JAR may still contain major 61 classes. Java 8, when required to load such a class, may throw `UnsupportedClassVersionError`.

Another case: the JAR also uses the Java 8 class format, yet internally calls an API introduced in Java 11. When running on Java 8, it may hit `NoSuchMethodError` just like the `ApiLeak` example. `--release` on the **application's compilation** does not re-verify every binary reference inside external JARs.

Therefore, you need to:

- Choose **the right library version supporting the project's minimum Java**; check documentation and dependency policies.
- Inspect the JARs that runtime will use, including transitive dependencies.
- Use binary/class-file version analysis tools when needed; do not treat the version number in a JAR's file name as sufficient proof.
- Run integration tests on the actual older runtime, especially reflection, service loader, plugin, or native paths.

`jdeps` can help identify package/module dependencies, but does not replace checking method-level availability per Java release and runtime testing. Do not use `jdeps` output alone to declare all APIs Java 8 compatible.

## 12. Pitfalls in Practice

| Pitfall | Consequence | How to fix |
| --- | --- | --- |
| Configuring only `-target 8` | May conflict with source level, or still use newer APIs | Prefer `--release 8` |
| Using `-source 8 -target 8` with a newer JDK | Old source/class format yet current platform APIs | Add API constraint using `--release 8` |
| Checking only `major version 52` | Misses references to Java 11 APIs | Verify `--release` and test on Java 8 |
| Testing only on JDK 21 | Misses missing-method errors on Java 8 | Test on the minimum supported runtime |
| Using `--release 8` while depending on a Java 17 JAR | Application classes are valid but dependency has a newer major version | Pin and inspect all runtime dependencies |
| Using reflection or dynamic plugins | Compiler cannot observe every class/method invoked at runtime | Test dynamic code paths on the target runtime |
| Running stale class files from output directory | Unexpected results, hard to tell which compilation produced the file | Clean build, check classpath and artifact hashes |
| Confusing `java` with `javac` | Actual compiler and runtime differ from expected versions | Record executable paths and `-version` for both |
| Conflating compile errors with linkage errors | Fixing the wrong layer, e.g., editing source when only a runtime dependency is missing | Distinguish compile diagnostics, class-format, and symbol resolution |
| Drawing conclusions from a newer runtime | Masks missing-API errors on older Java | Test on older runtime and real deploy environment |

## 13. Self-Check Exercises

**Exercise 1.** JDK 21 compiles `ApiLeak.java` with `--source 8 --target 8` and `javap` shows major 52. Is it guaranteed to run on Java 8?

**Answer:** No. The class still references `String.repeat(int)` from Java 11. A Java 8 JVM can read major 52, yet does not have that method, so when the call is linked it will result in `NoSuchMethodError`.

**Exercise 2.** Using `--target 8` alone on JDK 21, without `--source`, is it guaranteed to successfully produce a Java 8 class?

**Answer:** No. The default source level follows the newer compiler, so target 8 can be lower than the source level and be rejected. Even when combined with `--source 8` to compile successfully, Java 8 platform APIs are still not guaranteed.

**Exercise 3.** Why does `javac --release 8 ApiLeak.java` fail, while `javac --source 8 --target 8 ApiLeak.java` can succeed on JDK 21?

**Answer:** `--release 8` also restricts the Java SE/JDK APIs to those corresponding to Java 8; whereas source/target primarily restrict language and class-file version, and can still let the compiler see APIs of the running JDK.

**Exercise 4.** The application compiles with `--release 8` yet depends on a JAR containing major 61 classes. Is it guaranteed to run on Java 8?

**Answer:** No. Java 8 cannot load class version 61 when needed and may throw `UnsupportedClassVersionError`. The release setting of the application's source does not lower the version of external JARs.

**Exercise 5.** If a major 52 class loads successfully yet calls a missing method at runtime, what category does the error belong to?

**Answer:** Binary linkage errors such as `NoSuchMethodError`, not class-file version errors.

**Exercise 6.** As long as `javap -verbose` shows major 52 and there is no new Java syntax, can runtime tests be skipped?

**Answer:** No. You must examine symbolic references, dependency JARs, reflection/dynamic loading, runtime configuration, and run tests on Java 8 if that is a platform that must be supported.

## 14. References

- **Oracle JDK 21 — The javac Command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html — meaning of `--source`, `--target`, `--release`, section *Compiling for Earlier Releases of the Platform*.
- **Oracle JDK 21 — The javap Command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html — `-verbose` and class-file metadata.
- **Java SE 21 JVMS, Chapter 4:** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html — class file version, constant pool, method references.
- **Java SE 21 JVMS, Chapter 5:** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html — loading, linking, resolution, and runtime errors.
- **Java SE 11 String API:** https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/String.html#repeat(int) — `String.repeat(int)` available since Java 11.
- **Gradle Java compilation/toolchains:** https://docs.gradle.org/current/userguide/toolchains.html — compiler/toolchain and Java compile options.

**Takeaway:** **`-target` only controls the `.class` format; it does not make newer APIs disappear from the JDK used to compile.** Use `--release` to block Java SE/JDK APIs not belonging to the target release, control binary dependencies, and run tests on the lowest runtime you must support to verify actual execution capability.
