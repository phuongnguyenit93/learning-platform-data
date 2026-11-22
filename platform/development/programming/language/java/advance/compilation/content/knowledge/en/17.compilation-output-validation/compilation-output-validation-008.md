# Checking `.class` File Versions Before Java Packaging

## 1. Why Must You Check the Final Output?

A project configured for "Java 17" does not guarantee that the final artifact runs on Java 17. The source code may have been compiled by another toolchain, a module may use `--release 21`, classes produced by a generator may keep a newer target, or an included library may have been built with a newer JDK. After creating a JAR, WAR, or distribution, an older Java runtime may report:

~~~text
java.lang.UnsupportedClassVersionError:
  ... has been compiled by a more recent version of the Java Runtime
~~~

That is a **class-file compatibility** error: the JVM does not support the class file structure version it was asked to load. A **pre-packaging verification gate** should read the actual generated class files, compare them against the committed minimum Java runtime, check preview status, and allow packaging only when the policy is satisfied.

This lesson focuses on **output validation** after compilation and before packaging, rather than merely explaining compiler flags. The final result needs to answer:

- Which `.class` files exist in the build output and JAR?
- What is each file's **major/minor version**?
- Are all of them within the target JVM limit?
- Are there preview classes, unexpected classes, or multi-release JARs needing exceptions?
- Are there dependencies or nested JARs that have not been scanned?
- Have compiler/build scripts used `--release` properly?
- Does CI **fail before publishing the artifact** when invalid output is detected?

## 2. Class File Header Structure and Version Numbers

According to the Java Virtual Machine Specification, every class file begins with:

~~~text
Offset   Size         Field
0x00     4 bytes      magic = 0xCAFEBABE
0x04     2 bytes      minor_version (unsigned u2)
0x06     2 bytes      major_version (unsigned u2)
0x08     ...          constant_pool_count and other structures
~~~

Numbers in a class file are stored in **big-endian** order. Java's `DataInputStream.readInt()` and `readUnsignedShort()` can sequentially read magic, minor, and major here. Do not read as little-endian or mix up the order as `major` then `minor`.

For common Java versions:

| Java release | Major version | Typical class file |
| --- | ---: | --- |
| Java 8 | 52 | 52.0 |
| Java 9 | 53 | 53.0 |
| Java 11 | 55 | 55.0 |
| Java 17 | 61 | 61.0 |
| Java 18 | 62 | 62.0 |
| Java 19 | 63 | 63.0 |
| Java 20 | 64 | 64.0 |
| Java 21 | 65 | 65.0 |
| Java 22 | 66 | 66.0 |
| Java 23 | 67 | 67.0 |
| Java 24 | 68 | 68.0 |

For Java 9 and later, the common relationship is **major = release + 44**. The formula also yields 52 for Java 8; however, a production tool should rely on a table/spec of releases it actually supports, rather than guessing future versions indefinitely.

**Minor version:** normal class files in modern Java versions have minor `0`. For versions supporting preview class-file semantics, minor `65535` indicates a class using **preview features** and restricted to running on the corresponding exact release/flags. Do not treat `61.65535` as equivalent to `61.0`: a build requiring stable Java 17 should reject preview classes, even when major is 61.

### Checking with javap

~~~bash
javap -verbose -classpath out demo.PackageDemo
~~~

Look for the lines:

~~~text
minor version: 0
major version: 61
~~~

`javap` reads compiled classes, unlike opening `pom.xml` or `build.gradle`. It is useful for investigating a specific class, but running `javap` on one class **does not prove the entire artifact** shares the same target.

## 3. Three Versions to Separate During Review

| Concept | Example | Verification |
| --- | --- | --- |
| JDK running the compiler tool | `javac 24.0.2` | `javac -version`, Gradle/Maven toolchain |
| Source language level | Java 17 | `--release 17` or `-source 17` |
| Class file target | 61.0 (Java 17) | Reading bytes, `javap -verbose` |
| Java SE API allowed to call | APIs present in Java 17 | Prefer `--release 17` |
| Actual deployed JVM | Java 17 or newer | Run tests on the minimum runtime |

For example, JDK 24's `javac` compiling with `--release 17` can produce **61.0** bytecode. This is valid: compiler version and class target are **different**.

Do not assume `-source 17 -target 17` guarantees Java 17 compatibility. On a newer JDK compiler, those two flags can allow referencing **Java SE APIs newer than 17**, even though the bytecode is still 61. For example, `Thread.ofVirtual()` exists in Java 21 but not in Java 17: to make a newer compiler block this call at compile time for target 17, use `--release 17`.

**Practical conclusion:** the class-file gate checks bytecode **format**. `--release` additionally controls the **platform API** at compile time. Runtime tests and dependency verification check the remaining compatibility conditions. These three protective layers complement one another and do not replace each other.

## 4. Complete Experiment: Same Source, Two Class Versions

Use a JDK that supports compiling both `--release 17` and `--release 21` (for example JDK 21 or 24). Create the file:

**`src/demo/PackageDemo.java`**

~~~java
package demo;

public final class PackageDemo {
    public static final class Nested {
        public String label() {
            return "nested";
        }
    }

    public static void main(String[] args) {
        System.out.println(new Nested().label());
    }
}
~~~

This is a complete Java program with a nested class. When compiled, the compiler produces **two class files**, not just one.

In the project directory, using Bash:

~~~bash
mkdir -p out17 out21

javac --release 17 -encoding UTF-8 -d out17 \
  src/demo/PackageDemo.java

javac --release 21 -encoding UTF-8 -d out21 \
  src/demo/PackageDemo.java

java -cp out17 demo.PackageDemo
javap -verbose -classpath out17 demo.PackageDemo
javap -verbose -classpath out21 demo.PackageDemo
~~~

In Windows PowerShell/cmd, put each `javac` invocation on a single line or use the shell's line-continuation character instead of `\` (Bash). The commands can only be run if the `javac` version supports both release 17 and 21.

Application stdout:

~~~text
nested
~~~

The two `javap` checks for class `demo.PackageDemo` show:

~~~text
out17: minor version: 0, major version: 61
out21: minor version: 0, major version: 65
~~~

This is a **summary** of two fields from `javap -verbose` output, not a verbatim single-line `javap` format.

A way to inspect the nested class (Bash/PowerShell must preserve `$` properly):

~~~bash
javap -verbose -classpath out17 'demo.PackageDemo$Nested'
~~~

With `cmd.exe`, use double quotes instead of single quotes. Do not rely on `PackageDemo.class` passing and skip `PackageDemo$Nested.class`, anonymous classes, local classes, or classes generated by annotation processors. All of them can be loaded by the JVM.

## 5. Writing a Java 17 Gate to Check an Entire Directory or JAR

A practical tool needs to run on the classes directory **before `jar` packaging**, and can run again on the JAR after creation. The following program uses Java 17 standard APIs, has no Maven/Gradle dependencies, and enforces a **strict** policy:

1. Every entry ending in `.class` must start with `0xCAFEBABE`.
2. Major version must be between 45 and **target release + 44**.
3. Minor version must equal **0**, meaning preview class files are rejected.
4. If no classes are found, the build must fail.
5. Any failing class must produce a non-zero exit code so the CI/package task blocks release.

This policy intentionally **scans all class entries**, including entries under `META-INF/versions/` of a multi-release JAR. That is safe if the project **has no multi-release JARs**, though it may be too strict for a valid multi-release JAR containing higher-version classes specifically for newer JVMs. Section 9 describes how to adjust when MR-JARs are actually used.

### 5.1. File ClassVersionGate.java

~~~java
import java.io.BufferedInputStream;
import java.io.DataInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

public final class ClassVersionGate {
    private static int maxMajor;
    private static int count;
    private static int errors;

    private static void check(String name, InputStream source)
            throws IOException {
        try (DataInputStream in =
                     new DataInputStream(new BufferedInputStream(source))) {
            if (in.readInt() != 0xCAFEBABE) {
                System.out.println("FAIL " + name + " invalid magic");
                errors++;
                return;
            }

            int minor = in.readUnsignedShort();
            int major = in.readUnsignedShort();
            count++;

            boolean valid = major >= 45
                    && major <= maxMajor
                    && minor == 0;

            System.out.println((valid ? "OK " : "FAIL ")
                    + name + " " + major + "." + minor);

            if (!valid) errors++;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println(
                    "Usage: ClassVersionGate "
                    + "<target-java-release> <classes-dir-or-jar>");
            System.exit(2);
        }

        int release = Integer.parseInt(args[0]);
        if (release < 8) {
            throw new IllegalArgumentException("Java 8+ expected");
        }
        maxMajor = release + 44;
        Path path = Path.of(args[1]);

        if (Files.isDirectory(path)) {
            try (Stream<Path> files = Files.walk(path)) {
                for (Path file : files
                        .filter(p -> p.toString().endsWith(".class"))
                        .sorted().toList()) {
                    check(path.relativize(file).toString()
                                    .replace('\\', '/'),
                            Files.newInputStream(file));
                }
            }
        } else if (path.toString().endsWith(".jar")) {
            try (ZipFile jar = new ZipFile(path.toFile())) {
                List<? extends ZipEntry> entries =
                        Collections.list(jar.entries()).stream()
                                .filter(e -> !e.isDirectory()
                                        && e.getName().endsWith(".class"))
                                .sorted(Comparator.comparing(ZipEntry::getName))
                                .toList();

                for (ZipEntry entry : entries) {
                    check(entry.getName(), jar.getInputStream(entry));
                }
            }
        } else {
            throw new IllegalArgumentException(
                    "Expected a classes directory or .jar file");
        }

        if (count == 0) {
            System.err.println("FAIL no .class files found");
            System.exit(1);
        }

        System.out.println(
                "RESULT checked=" + count + " errors=" + errors);

        if (errors != 0) System.exit(1);
    }
}
~~~

**Explanation of key parts:**
- `Files.walk(path)` collects all `.class` files in the directory and subdirectories, including nested/local/anonymous classes generated by the compiler.
- `ZipFile` iterates through `.class` entries in the JAR. Running `jar tf` manually helps identify names and paths when needed.
- `readInt` checks the magic number, and `readUnsignedShort` reads **minor then major** in order.
- `major <= maxMajor` accepts classes from older Java versions that can be loaded by the target JVM under version rules, without forcing every class to equal the maximum major version.
- `minor == 0` is a **no-preview** policy for ordinary classes. This is a choice of the gate, not a JVMS statement that every historical class file always had minor 0.
- `System.exit(1)` produces a failing exit code. Do not allow the packaging tool to ignore the gate's exit code.

**Intentional limitations:** the gate only reads the **header** (magic/major/minor); it does not parse the entire constant pool, verify JAR signatures, inspect nested JARs inside, or confirm API/runtime compatibility. A valid header does not prove a class file is complete or safe. Use it only with **trusted artifacts in the build pipeline**, or implement read limits, ZIP bomb protection, and advanced file I/O handling if applied to untrusted inputs.

### 5.2. Compiling the Gate

Create `ClassVersionGate.java` at the project root, then:

~~~bash
mkdir -p toolout
javac --release 17 -encoding UTF-8 -d toolout ClassVersionGate.java
~~~

This gate works when run on JDK 17+, provided the JVM has all the Java standard APIs used. You need a JDK to run the compiler to build the gate; afterwards a JVM can run the class from `toolout`.

### 5.3. Checking a Java 17 Directory — PASS

~~~bash
java -cp toolout ClassVersionGate 17 out17
~~~

Output from the executed test:

~~~text
OK demo/PackageDemo$Nested.class 61.0
OK demo/PackageDemo.class 61.0
RESULT checked=2 errors=0
~~~

**Exit code: 0.** Both the top-level and nested classes have a format compatible with minimum Java 17. This gate traverses both, instead of just running `javap` on the main class.

### 5.4. Checking Java 21 Classes When Targeting Java 17 — FAIL

~~~bash
java -cp toolout ClassVersionGate 17 out21
~~~

Verification output:

~~~text
FAIL demo/PackageDemo$Nested.class 65.0
FAIL demo/PackageDemo.class 65.0
RESULT checked=2 errors=2
~~~

**Exit code: 1.** This is the expected result: a Java 17 JVM does not support Java 21's class-file major version 65.

If the actual target is Java 21:

~~~bash
java -cp toolout ClassVersionGate 21 out21
~~~

Output:

~~~text
OK demo/PackageDemo$Nested.class 65.0
OK demo/PackageDemo.class 65.0
RESULT checked=2 errors=0
~~~

**Exit code: 0.** This only indicates that the class file format is compatible with the Java 21 limit; it does not yet confirm all dependencies or APIs.

## 6. Placing the Gate Before the JAR Packaging Step

### 6.1. Minimal Manual Pipeline

Suppose the minimum Java runtime is 17 and the code is in `src/demo`:

~~~bash
mkdir -p out17 toolout dist

javac --release 17 -encoding UTF-8 -d toolout ClassVersionGate.java
javac --release 17 -encoding UTF-8 -d out17 src/demo/PackageDemo.java

java -cp toolout ClassVersionGate 17 out17

jar --create --file dist/package-demo.jar -C out17 .

java -cp toolout ClassVersionGate 17 dist/package-demo.jar
java -cp dist/package-demo.jar demo.PackageDemo
~~~

This sequence is **dependency-correct**, though in Bash CI you should enable failing on command error to avoid continuing even if the gate fails:

~~~bash
set -e
# javac, ClassVersionGate, and jar commands as above.
~~~

The `set -e` command must be configured in an appropriate shell script context; if using complex pipelines/conditionals, check exit-status propagation behavior. In PowerShell, after `java -cp ... ClassVersionGate 17 out17`, check `$LASTEXITCODE` and throw an error if non-zero; PowerShell 5.1 does not always automatically stop a script merely because a native executable returns exit 1.

**A good practice:** CI has explicit stages `compile → verify-classes → package → verify-package → integration-test → publish`. Publish runs only when all preceding stages succeed.

### 6.2. Checking the JAR After Creation

~~~bash
jar --create --file package-demo.jar -C out17 .
java -cp toolout ClassVersionGate 17 package-demo.jar
jar --list --file package-demo.jar
~~~

When tested, the JAR contains two class files; the gate prints:

~~~text
OK demo/PackageDemo$Nested.class 61.0
OK demo/PackageDemo.class 61.0
RESULT checked=2 errors=0
~~~

Even after verifying the directory, you still need to verify the final JAR if the packaging step might add classes from other modules, generated output, shading/relocation, or dependency classes. **The exact published artifact** is the source of truth.

## 7. Maven: Controlling Compiler Release and Enforcing Packaging Constraints

With Maven, configure the compiler release to reduce risk from the start. Example snippet in `pom.xml`:

~~~xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

This is only a **configuration snippet** of a complete POM. The Maven Compiler Plugin must support `release` and the active JDK compiler must support the Java 17 target. If you need stable plugin version management, add `maven-compiler-plugin` to `build/plugins` or parent `pluginManagement` per project standards.

In the Maven lifecycle, `compile` runs before `package`. A practical CI workflow:

~~~bash
mvn clean compile

java -cp toolout ClassVersionGate 17 target/classes

mvn package
java -cp toolout ClassVersionGate 17 target/my-app.jar
~~~

Two points to adjust when applying this:
- `toolout` must actually contain `ClassVersionGate.class` compiled from section 5.
- `target/my-app.jar` is an **illustrative name**; replace it with the actual artifact path from the Maven configuration rather than assuming every project uses that name.

If building automated command orchestration, make the gate step a **mandatory precondition before packaging** (for example, a plugin execution in an appropriate phase such as `prepare-package`), not merely a command users remember to run. If `mvn package` can be run on its own without going through the gate, the practical workflow still has a gap.

For **multi-module Maven** projects, each module may have a different compiler target. The gate needs to run on module class outputs included in the final artifact, and also run on the final JAR/WAR if assembly/shading can introduce new class files. Do not infer that "the parent POM sets Java 17, so every JAR in the distribution automatically has 61.0."

### Distinguishing Maven's Compiler from the Deployment Runtime

`mvn -version` shows the JVM running Maven, but the Maven Toolchains Plugin or compiler configuration may use a different compiler JDK. Check the **actual toolchain**, compiler args, and `javap` output. `maven.compiler.release=17` cannot downgrade classfiles already compiled inside third-party dependencies.

## 8. Gradle: Verification Build Task Before `jar`

The Gradle Java plugin provides `JavaCompile`, `classes`, and `jar`. Set `options.release=17` so the compiler enforces matching source/target/platform APIs:

~~~groovy
plugins {
    id 'java'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}
~~~

This is a **`build.gradle` snippet**, not Java source. If the project uses Gradle Java Toolchains, it can choose a compiler JDK other than Java 17 while still setting `options.release = 17`.

A sample way to wire the gate (Groovy DSL), assuming the gate is already compiled into `tools/class-version-gate-classes`:

~~~groovy
tasks.register('verifyBytecode', JavaExec) {
    dependsOn tasks.named('classes')
    classpath = files("$rootDir/tools/class-version-gate-classes")
    mainClass = 'ClassVersionGate'
    args '17', layout.buildDirectory
            .dir('classes/java/main').get().asFile.absolutePath
}

tasks.named('jar') {
    dependsOn tasks.named('verifyBytecode')
}
~~~

This is an **illustrative integration configuration** that must be placed alongside the Java plugin and requires `ClassVersionGate.class` in the declared directory. It does not compile the gate itself; in production, package the verifier as a dedicated plugin/task or a separate build tool with managed dependencies. If the project has outputs in other locations, multi-language builds, or multiple compile tasks, do not hardcode only `classes/java/main` and miss other classes.

**Dependency chain:** `verifyBytecode` depends on `classes`; `jar` depends on `verifyBytecode`; therefore running `jar` must pass through the gate. If a class violates the policy, JavaExec throws an error to Gradle and packaging does not proceed by default.

When building the final distribution, a **second gate** may be needed to check the final JAR and dependencies bundled in a shadow/fat JAR. Checking only `build/classes/java/main` is not enough if `jar` or `shadowJar` pulls in classes from elsewhere.

## 9. Multi-Release JARs and Class Files for Newer JVMs

A **Multi-release JAR (MR-JAR)** can contain multiple versions of the same class, for example:

~~~text
com/example/Feature.class
META-INF/versions/17/com/example/Feature.class
META-INF/versions/21/com/example/Feature.class
~~~

The manifest usually contains the attribute:

~~~text
Multi-Release: true
~~~

With a valid MR-JAR, a Java 17 JVM can select the base class or a matching versioned entry **not exceeding the runtime version**, whereas a Java 21 JVM can pick the 21 entry. Thus, an MR-JAR serving Java 17 **can legitimately contain major 65 class files in `META-INF/versions/21/`**, provided the base and the classes actually used by Java 17 are Java 17 compatible and MR-JAR rules are followed.

The gate in section 5 is **intentionally strict**: it checks **all** class entries and fails if any major exceeds 61. It suits an artifact without MR-JARs or a policy where "all entries must be Java 17." **Do not blindly apply the strict gate to conclude that a valid MR-JAR is broken**.

A proper MR-JAR verifier needs to:
1. Confirm the manifest contains `Multi-Release: true` if relying on versioned entries.
2. Distinguish base entries from `META-INF/versions/N/` paths.
3. For target Java T, model the **class selected by runtime T**: the highest versioned entry for the same logical class where N does not exceed T, or the base entry.
4. Check the format and APIs of the effective entries that Java T will load; also check newer versioned entries against **their own respective release**, if the artifact promises support for those runtimes.
5. Verify consistency of packages/APIs, service loading, and module metadata, not just the major number.

MR-JARs are much more complex than a flat JAR. If the project does not actively need them, avoid manually creating a `META-INF/versions` directory and treating every gate violation as an exception.

## 10. Fat JAR, Nested JAR, WAR, and Dependencies

An ordinary JAR contains `.class` files at direct paths. However, other packaging formats may have:

- **Shaded/fat JAR:** dependency class files are merged directly into the JAR; the gate can scan the direct class entries if it checks the final artifact.
- **Spring Boot executable JAR:** classes may live under `BOOT-INF/classes`, while dependency JARs sit in `BOOT-INF/lib`. The gate in section 5 checks `.class` files directly under `BOOT-INF/classes` but **does not open nested JARs in `BOOT-INF/lib`**.
- **WAR:** app classes are in `WEB-INF/classes`, and dependencies may be in `WEB-INF/lib` — you must open and validate the relevant JARs.
- **Modular JAR:** contains `module-info.class` and module dependencies; the module descriptor is also a class file and must be included in format checks.
- **Native image:** not distributed in standard JVM class-file structure; use a gate appropriate for the actual artifact/runtime.

Therefore, you must **define the scan scope**:
- Should application classes be scanned?
- Should test classes be scanned? Tests may be compiled with a newer Java version if the project allows it, but should not enter the runtime artifact.
- Should bundled dependencies be scanned?
- Should generated classes (annotation processors, bytecode enhancement, Kotlin/Scala classes, etc.) be scanned?
- Should output be checked after shading, assembly, or repackaging?
- Are there container/runtime libraries provided outside the artifact that need compatibility testing?

**Do not claim full artifact compatibility** just because a verifier that only reads `target/classes` passed. It only confirms the portion that was actually checked.

## 11. Preview Class Files and Release Policy

A class using a preview feature can have minor version **65535**, for example class file `65.65535` for a Java 21 preview build. A runtime of the same Java release requires the corresponding preview conditions to load it. You cannot just change its `major` to run on Java 17.

For a stable distribution policy, the simple choices are:
- **No preview**: require `minor == 0` for every checked class (as in the sample gate).
- **Controlled preview usage**: verify the exact major, minor, release, `--enable-preview` at compile/run time, and the corresponding JDK matrix; prohibit publishing as a stable Java 17 artifact if it depends on another version's preview features.

Do not try to "fix" bytecode by overwriting the 2 minor bytes from 65535 to 0: the bytecode/semantics may require preview runtime support. Binary patching does not substitute for recompiling for the right target.

## 12. A Correct Class-File Version Does Not Guarantee Correct APIs/Runtime

A major 61 class can still fail to run on Java 17 if:
- Compiled with `-source 17 -target 17` on a newer JDK while using Java 21/24 APIs; `--release 17` will block many such errors.
- A runtime dependency was compiled for Java 21 and a Java 17 JVM loads that class.
- The class references a method from a newer library version, while runtime provides an older version (`NoSuchMethodError`).
- Incompatible `ServiceLoader`, reflection, module exports, native/JNI, or generated proxies exist.
- The class file has a valid header/format, but the rest of the file is corrupted or the bytecode fails JVM verification.
- Multiple JARs duplicate a class, and classpath order causes the JVM to load a different version than the verified one.

Therefore, a serious pipeline should combine:

~~~text
javac --release N
      |
      v
Scan all application .class files for target N
      |
      v
Check dependency min-Java, classpath/module path
      |
      v
Package artifact
      |
      v
Scan the package itself after assembly/repackage
      |
      v
Run smoke/integration tests on real Java N
      |
      v
Publish
~~~

For a Java library that must support multiple runtimes, running tests on the **minimum supported JDK** is essential. Running on JDK 24 does not prove the artifact runs on JDK 17.

## 13. Detecting Wrong Class Versions in CI

**Scenario 1: a module accidentally uses Java 21**

Typically:
- `javap -verbose` on that module shows major 65.
- The target-17 gate prints `FAIL ... 65.0`, exit code 1.
- Check `--release`, the JavaCompile task, compiler toolchain, and plugin/module overrides.
- Clean-build the module and verify again before packaging.

**Scenario 2: source is right, but generated classes are newer**

A bytecode generator, instrumentation task, or language plugin may generate class files after `javac`. If the gate runs **before** that task and not after, the artifact will still have newer classes. Place the verifier after all **transform** steps that can modify/add classes and before the publish step.

**Scenario 3: a dependency in a fat JAR is too new**

All application classes are 61.0, yet a shaded dependency contains 65.0 classes. If the gate only scans app output, CI passes falsely. Scan the final shaded JAR or the corresponding resolved dependency artifacts.

**Scenario 4: an empty JAR or missing classes**

A script that merely checks "no wrong version seen" can pass even when it finds zero classes. The sample gate requires `checked > 0`. That does not mean every artifact must contain classes (e.g., a resources-only JAR); a specific policy must specify which artifact types can be valid without classes.

**Scenario 5: the gate encounters an invalid magic number**

Data named `.class` without the `CAFEBABE` magic number: broken packaging, wrong file type generated, or data corruption. The gate rejects it; the compiler/JVM may also fail to load it. If the file belongs to an untrusted artifact, apply memory/stream limits and use a suitable verifier.

**Scenario 6: compiler and runtime configurations differ**

`javac -version` does not necessarily match `java -version`; Maven/Gradle toolchains may also differ from the JVM running the build tool. Read the compiler invocation, inspect binary class files, and confirm the actual runtime inside the deployment image/container.

## 14. Pre-Release Checklist

- [ ] Minimum supported Java release is formally defined (for example, 17).
- [ ] `javac` or JavaCompile uses `--release 17` (and appropriate encoding).
- [ ] Clean build, with no stale `.class` files from a different target.
- [ ] `javap -verbose` confirms the version of several representative classes.
- [ ] Gate checks **all** application `.class` files, including nested/local/anonymous/generated classes.
- [ ] Magic and major/minor are valid, with no out-of-policy preview classes.
- [ ] Gate returns a **non-zero exit code** when intentionally mixing a Java 21 class into a Java 17 artifact.
- [ ] Output is verified strictly **after** compile/codegen/transform steps.
- [ ] Dependencies have appropriate class-file/API compatibility.
- [ ] Packaging does not inject unverified classes.
- [ ] Final JAR/WAR/fat JAR is verified according to **its format**, including nested JARs if present.
- [ ] If using an MR-JAR, the verifier understands versioned entry rules instead of performing an indiscriminate strict scan.
- [ ] Tested at least once on the **actual minimum Java runtime**.
- [ ] CI blocks publishing when the gate or integration tests fail.
- [ ] Build tool/plugin/JDK versions are recorded for reproducibility.

## 15. Self-Check Questions

**Question 1.** What class-file major version does Java 17 have?  
**Answer:** 61.

**Question 2.** Does JDK 24 compiling with `--release 17` necessarily produce major 68?  
**Answer:** No. It generates classes targeting Java 17, normally major 61.

**Question 3.** Running `javap` only on the main class shows 61.0 — can you release with confidence?  
**Answer:** Not yet; there are still nested/generated classes and dependencies/final package.

**Question 4.** What must be done when a 65.0 class appears in a flat JAR targeting Java 17?  
**Answer:** Block packaging, find the module/dependency generating the Java 21 class, fix the release setting or replace the dependency.

**Question 5.** Is major 61, minor 65535 the same as major 61, minor 0?  
**Answer:** No. Minor 65535 carries preview semantics; a non-preview policy must reject it.

**Question 6.** Does a gate inspecting only bytes 0–7 prove a class is completely valid?  
**Answer:** No. It only checks the magic number and class-file version header.

**Question 7.** An MR-JAR has `META-INF/versions/21/Foo.class` with major 65 while targeting runtime 17. Is that always an error?  
**Answer:** No. When the MR-JAR is properly configured, a Java 17 runtime does not select the version 21 entry; a strict gate over all entries can report a false positive.

**Question 8.** `jar tf` lists `BOOT-INF/lib/dependency.jar`; does the sample gate scan classes inside that dependency?  
**Answer:** No. The verifier needs to open nested JARs or check dependency artifacts before packaging.

**Question 9.** An app uses only `-target 17` and calls a Java 21 API, producing a 61.0 class file. Does the gate detect the API mismatch?  
**Answer:** No. Use `--release 17` and run tests on real Java 17.

**Question 10.** Why must the gate fail when finding a single wrong-version class, even if the main class is right?  
**Answer:** The JVM may load the wrong class on another code branch at runtime; an artifact should not be released with an out-of-policy incompatible class.

## 16. Official References

- [JVMS 17 §4.1 — ClassFile structure and major/minor version](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.1)
- [Oracle Java 17 javac command — `--release`, `--target`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [Oracle javap command — verbose class-file inspection](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html)
- [JAR File Specification — Multi-Release JAR files](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html#multi-release-jar-files)
- [Gradle JavaCompile and toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
- [Maven Compiler Plugin — Setting `--release`](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)

**Key takeaway:** checking the right version before packaging is not just reading `javac -version`. Inspect the **headers of all actual class files**, use `--release` to constrain source/target/API, clearly separate flat JARs from MR-JARs and nested dependencies, make the gate a mandatory precondition before publish, and test on the minimum Java runtime. Only when these validation layers all pass is there a solid basis to trust that the artifact is compatible with the target.