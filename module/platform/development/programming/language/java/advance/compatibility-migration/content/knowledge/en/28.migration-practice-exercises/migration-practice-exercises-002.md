# Reproducing the Case Where -source and -target Still Call a New API by Mistake

In **Java Advance Compatibility Migration**, a subtle bug is **a JAR whose bytecode is compatible with an older JDK yet references an API that only exists in a newer JDK**. An application can compile completely successfully with the **-source** and **-target** parameters, yet fail when deployed onto a runtime declared as supported.

This is a **practical exercise** in the **Practice Exercises** chapter. We will intentionally create this situation:

1. Use **javac from JDK 21** to compile code declared as **Java 8** compatible.
2. Specify **-source 8 -target 8** while intentionally calling **String.isBlank()**, an API introduced only in **Java 11**.
3. Observe that the compiler can produce a class file with **major version 52**.
4. Run that class on **Java 8** and observe **NoSuchMethodError**.
5. Switch to **--release 8** so the compiler catches the error immediately at build time.
6. Extend the lesson to Gradle, Maven, third-party libraries, CI matrices, and real runtime testing.

Important point before starting: **source language, bytecode format, and the platform API set are three distinct boundaries**. The two flags **-source** and **-target** do not fully control all three boundaries.

> **Practice scope:** The commands below are instructions for learners to run locally or in a lab environment. Shown results are **expected results**, not claims of execution in this article. Compiler messages may vary slightly by JDK vendor and patch version.

## 1. Learning objectives

After this lesson, learners can:

- Explain the differences between **-source**, **-target**, and **--release**.
- Reproduce a Java 8 class-file artifact that calls a Java 11 API.
- Understand why Java 8 can load the class yet fail when linking the method call.
- Use **javap -verbose** and **javap -c** to inspect bytecode.
- Use **--release 8** to block invalid references to standard APIs.
- Distinguish **NoSuchMethodError**, **NoClassDefFoundError**, and **UnsupportedClassVersionError**.
- Design independent testing across **compiler JDK**, **target release**, and **runtime JDK**.
- Recognize the limits of **--release** regarding dependencies and generated code.
- Transfer these concepts to Gradle, Maven, and CI release gates.

## 2. Three compatibility axes developers often confuse

Suppose a project must **run on Java 8**, yet the organization wants to move the build environment to JDK 21.

There are at least three independent questions:

| Axis | Question | Tooling |
|---|---|---|
| Source language | Are new Java syntax features permitted? | **-source** or the source part of **--release** |
| Bytecode | Can the old JVM read the class-file format? | **-target** or the target part of **--release** |
| Java SE API | Do the Java platform classes/methods exist on the old runtime? | **--release** when compiling with a supporting javac |
| Runtime behavior | Do code/dependencies behave properly on the old JVM? | Execution tests on the old JVM |
| Dependency compatibility | Are third-party JARs compatible with the minimum runtime? | Dependency audit and runtime integration tests |

### 2.1. What does -source do?

Example:

~~~bash
javac -source 8 ApiTrap.java
~~~

The **-source 8** option instructs the compiler to check source against Java 8 language syntax/semantics within what javac supports.

It does not mean the compiler automatically uses only Java SE 8 APIs. A method call introduced in Java 11 can still be valid under **Java 8 syntax**.

### 2.2. What does -target do?

Example:

~~~bash
javac -target 8 ApiTrap.java
~~~

The **-target 8** option instructs the compiler to emit a class-file format compatible with Java 8; in this example, **major version 52**.

Bytecode can be in a format the old JVM understands, yet the symbol referenced by the bytecode may not exist in the old runtime's API.

### 2.3. What does --release do?

Example:

~~~bash
javac --release 8 ApiTrap.java
~~~

The **--release 8** option, introduced in JDK 9 via **JEP 247**, combines checking source language, target bytecode, and the permitted **Java platform APIs** for the chosen release.

It prevents compiling with a new JDK while accidentally calling a new JDK API in a program that must run on an older JDK.

### 2.4. Comparison table

| Configuration when running javac 21 | Syntax level | Class-file target | Restricts Java SE APIs to Java 8? |
|---|---|---|---|
| **-source 8 -target 8** | Java 8 | Java 8 | **Incomplete**; can see JDK 21 APIs |
| **--release 8** | Java 8 | Java 8 | **Yes** for supported platform APIs |
| Unconfigured | Defaults to javac 21 | Defaults to javac 21 | Not intended to run on Java 8 |

Key takeaway: **-source 8 -target 8 is not an alias for --release 8**.

## 3. Preparing the lab environment

The main lab uses:

- **JDK 21** to run the newer javac.
- **JDK/JRE 8** to run the artifact on the old runtime.
- A terminal.
- An isolated working directory, e.g., **java-api-trap-lab**.
- No Maven, Gradle, or external dependencies needed in the first part.

You may use JDK 17 or a newer javac supporting **--release 8** instead of javac 21, provided that version includes **String.isBlank()**.

### 3.1. Verify both runtimes

On a machine with JDK 21 on PATH:

~~~bash
java -version
javac -version
~~~

The expected result is version 21 for the compiler to be used. On a machine with multiple JDKs, **java** and **javac** in PATH do not necessarily belong to the same installation.

To guarantee the right compiler, use absolute paths, e.g., on Unix:

~~~bash
/opt/jdks/jdk-21/bin/javac -version
/opt/jdks/jdk8/bin/java -version
~~~

These paths are illustrative only. Replace them with actual JDK installation locations.

Windows PowerShell can use:

~~~powershell
& "C:\Java\jdk-21\bin\javac.exe" -version
& "C:\Java\jdk8\bin\java.exe" -version
~~~

These are also placeholders. **Do not run both commands simply by the names java/javac** if PATH changes uncontrollably.

### 3.2. When no Java 8 runtime is available

You can perform the compile and **javap** inspection steps with a newer JDK first. However, to observe **NoSuchMethodError on a Java 8 runtime**, a real Java 8 runtime or a reliable container/test image containing Java 8 is mandatory.

Never write "reproduced runtime error" merely because the compiler gave no warning.

### 3.3. Directory structure

~~~text
java-api-trap-lab/
  src/
    ApiTrap.java
  out/
    source-target/
    release/
~~~

Create directories manually or via OS-appropriate commands. Keep **separate output directories** for the two compilations to avoid confusing old class files.

## 4. Writing source that intentionally calls a new API

Create file **src/ApiTrap.java**:

~~~java
public final class ApiTrap {
    public static void main(String[] args) {
        String input = "   ";

        // String.isBlank() only exists since Java 11.
        boolean blank = input.isBlank();

        System.out.println("isBlank = " + blank);
    }
}
~~~

This source is intentionally problematic when required to run on Java 8.

### 4.1. Why is this syntax valid in Java 8?

- Class, main method, and local variable all use Java 8 syntax.
- Calling an instance method with dot notation is syntax that has existed for a long time.
- There are no records, text blocks, switch expressions, or newer syntax features.
- The only difference is that **the String.isBlank() API does not exist in Java 8**.

**String.isBlank()** was introduced in **Java 11**. With javac 21, the compiler sees this method in the current Java platform unless instructed to compile against an older release's API via **--release**.

### 4.2. Why choose String.isBlank()?

It has three advantages for the lab:

1. Requires no third-party dependencies.
2. The call is small enough to inspect easily in bytecode.
3. Clear API distinction: **absent in Java 8**, **present in Java 11+**.

Because the source uses a new API without new syntax, it demonstrates the exact gap in **-source/-target**.

## 5. Experiment A: newer javac with -source 8 -target 8

Use **javac 21**:

~~~bash
javac -source 8 -target 8 \
  -d out/source-target \
  src/ApiTrap.java
~~~

On Windows PowerShell this can be written on one line:

~~~powershell
& "C:\Java\jdk-21\bin\javac.exe" -source 8 -target 8 -d out\source-target src\ApiTrap.java
~~~

If `out/source-target` does not exist yet, prepare it beforehand per your shell. Javac can create package directories, yet creating the output root for the lab keeps control simple.

### 5.1. Expected result

On a newer javac supporting these options, **compilation can succeed**, even though the source calls a Java 11 API.

The compiler may emit warnings about **-source/-target** usage or setting the boot class path, depending on version. **A warning is not a compile error.**

Expected:

~~~text
Build result: SUCCESS
Generated: out/source-target/ApiTrap.class
Target class-file major version: 52
Referenced Java method: java.lang.String.isBlank()
~~~

This is the expected outcome of the experiment, not fixed standard stdout from javac.

### 5.2. Why does the compiler let it pass?

Javac performs two tasks:

- Checks whether the source uses syntax beyond Java 8.
- Generates a class file in Java 8 bytecode format.

Yet when resolving **String.isBlank()**, the compiler can look at the API of **JDK 21 executing javac**, where that method exists.

Thus javac knows how to emit a symbol invocation named **java/lang/String.isBlank:()Z**, even though the Java 8 runtime never defined that symbol.

### 5.3. An easily overlooked warning

If the compiler prints a warning about the boot class path when using **-source 8**, that is precisely the sign that the configuration has not locked down Java 8 platform APIs. Do not simply suppress the warning with **-Xlint:-options** and declare the artifact fully compatible.

The proper solution for modern cross-release compilation is **--release 8** and testing on a Java 8 runtime.

## 6. Experiment B: inspecting the class-file version with javap

Use **javap** from the newer JDK to inspect the newly compiled artifact:

~~~bash
javap -verbose \
  -classpath out/source-target \
  ApiTrap
~~~

Find the line:

~~~text
major version: 52
~~~

**Major 52** corresponds to the Java 8 class-file format.

### 6.1. Viewing the API call in the constant pool

Also inside **javap -verbose** output, a method reference equivalent to the following may appear:

~~~text
Methodref java/lang/String.isBlank:()Z
~~~

Line formatting and constant-pool indices may vary by compiler.

Meaning:

- Owner class: **java/lang/String**.
- Method name: **isBlank**.
- Descriptor: **()Z**, meaning takes no arguments and returns boolean.
- Bytecode references a method that runtime must resolve.

### 6.2. Viewing bytecode instructions

~~~bash
javap -c -p \
  -classpath out/source-target \
  ApiTrap
~~~

Expect an instruction inside the body of **main** equivalent to:

~~~text
invokevirtual java/lang/String.isBlank:()Z
~~~

No need to memorize constant-pool indices. Focus on **invokevirtual**, the method name, and the descriptor.

### 6.3. Interim conclusion

At this point we have:

- Java 8 class-file version.
- Java 8 syntax source.
- Referenced symbol belonging to the Java 11 API.

**This is evidence that class-file version and Java API compatibility are two independent axes.** Yet to prove the Java 8 runtime will fail, we need the next step.

## 7. Experiment C: running the class file on Java 8

Use the **Java 8 runtime**, not Java 21:

~~~bash
/opt/jdks/jdk8/bin/java \
  -cp out/source-target \
  ApiTrap
~~~

Windows PowerShell:

~~~powershell
& "C:\Java\jdk8\bin\java.exe" -cp out\source-target ApiTrap
~~~

### 7.1. Expected result

You may see a message close to:

~~~text
Exception in thread "main" java.lang.NoSuchMethodError:
  java.lang.String.isBlank()Z
    at ApiTrap.main(ApiTrap.java:...)
~~~

Exact wording, line numbers, and how the JVM renders the method signature may vary. **The key error type is NoSuchMethodError** when the JVM attempts to execute a call to a method absent in Java 8's **java.lang.String** class.

### 7.2. Why is it not UnsupportedClassVersionError?

Because the class file is **major 52**, Java 8 can read this format.

The JVM does not necessarily check and resolve every method reference right when loading the class. When executing the call to **String.isBlank()**, the JVM must link the reference to a matching method in the Java 8 platform class. The method does not exist, producing a linkage error.

If the class file were major 65 from Java 21, Java 8 would reject it early with **UnsupportedClassVersionError**. Yet in this lab, the class format is valid; **the API symbol** is the problem.

### 7.3. Why does running on Java 21 succeed?

Test the same artifact with Java 21:

~~~bash
/opt/jdks/jdk-21/bin/java \
  -cp out/source-target \
  ApiTrap
~~~

Expected result:

~~~text
isBlank = true
~~~

Java 21 has the **String.isBlank()** method, so the method reference resolves. This is not evidence that the artifact is Java 8 compatible; it is only evidence that it runs on Java 21.

## 8. Experiment D: using --release 8 to catch the error at compile time

Now compile **the same source**, changing the options:

~~~bash
javac --release 8 \
  -d out/release \
  src/ApiTrap.java
~~~

Windows PowerShell:

~~~powershell
& "C:\Java\jdk-21\bin\javac.exe" --release 8 -d out\release src\ApiTrap.java
~~~

### 8.1. Expected result

Javac 21 may report:

~~~text
error: cannot find symbol
        boolean blank = input.isBlank();
                             ^
  symbol:   method isBlank()
  location: variable input of type String
~~~

Desired result:

~~~text
Compile result: FAILURE (intended)
Reason: String.isBlank() is not part of Java 8 platform API.
No valid ApiTrap.class should be released from this attempt.
~~~

This is **a successful compatibility-control test**: the bug is caught before release rather than when running on a customer machine.

### 8.2. How does --release act at the API layer?

With **--release 8**, javac uses Java 8 platform API information instead of exposing the entire Java platform API of JDK 21 to the source.

Because **String.isBlank()** is not part of the Java 8 API, the compiler cannot resolve the call and reports an error.

### 8.3. Why use --release instead of bootclasspath tricks?

Previously, there was a technique configuring **-bootclasspath** or equivalent to compile against classes of an older JDK. That approach requires preparing exact boot classes and has many error-prone details.

**--release** is the JDK-supported mechanism for compiling for older releases within the targets supported by the current javac. It is easier to review, more consistent, and blocks newer platform APIs more effectively than using only **-source/-target**.

Not every javac supports every older release; check documentation for your compiler target. For instance, using **--release 8** with JDK 21 is a commonly supported scenario.

## 9. Experiment E: fixing the source to be genuinely Java 8 compatible

Replace the **String.isBlank()** method with logic using only Java 8 APIs:

~~~java
public final class ApiTrap {
    public static void main(String[] args) {
        String input = "   ";

        boolean blank = input.trim().isEmpty();

        System.out.println("isBlank = " + blank);
    }
}
~~~

Then:

~~~bash
javac --release 8 \
  -d out/release \
  src/ApiTrap.java
~~~

And run on Java 8:

~~~bash
/opt/jdks/jdk8/bin/java \
  -cp out/release \
  ApiTrap
~~~

Expected result:

~~~text
isBlank = true
~~~

### 9.1. Warning on semantic compatibility

**trim().isEmpty() is not strictly equivalent to String.isBlank() in all Unicode cases.**

- **String.trim()** handles a character whitespace range according to legacy semantics.
- **String.isBlank()** relies on the whitespace character definition in the newer Java API.
- Certain Unicode strings can yield different results.

The replacement above serves only the lab with ASCII-whitespace strings. In a real product, if exact semantics of the new API must be preserved, write or use an equivalent implementation tested against your project's Unicode dataset and support policy.

### 9.2. When should you not rewrite the API yourself?

If a new feature has complex semantics or involves security/crypto, do not replace it with a crude helper. Other options:

- Use a verified library that still supports Java 8.
- Defer the feature until Java 8 support ends.
- Split implementations by runtime.
- Deliberately raise the minimum Java version and announce a breaking change.

Fixing a compile error does not automatically preserve business behavior.

## 10. Summary results matrix

| Configuration | Compile with JDK 21 | Class major | Run on Java 8 | Run on Java 21 |
|---|---|---:|---|---|
| Source calls isBlank, **-source 8 -target 8** | May succeed | 52 | **NoSuchMethodError** | Succeeds |
| Source calls isBlank, **--release 8** | **Fails intentionally** | Not released | Not applicable | Not applicable |
| Source uses trim().isEmpty(), **--release 8** | Succeeds | 52 | Succeeds with demo input | Succeeds |
| Source calls isBlank, default JDK 21 compile | Succeeds | 65 | **UnsupportedClassVersionError** | Succeeds |

The table distinguishes two errors that many people lump together as "Java 8 incompatible":

- **Bytecode too new:** the JVM cannot load the class format.
- **API too new:** the JVM can load the class format, yet cannot resolve the symbol.

## 11. Deep dive: linking mechanism in the JVM

Inside the class file, the call does not embed the code of **String.isBlank()**. It contains a symbolic reference to a method on a specific class.

A simplified representation:

~~~text
ApiTrap.class
  major version = 52
  constant pool:
    java/lang/String
    isBlank
    ()Z
  code:
    invokevirtual ... java/lang/String.isBlank:()Z
          |
          v
Java 8 runtime java.lang.String
          |
          +--> No method named isBlank()Z
          |
          v
NoSuchMethodError
~~~

The class file remains valid at the format level. The error occurs when the JVM must resolve the reference to an absent API.

### 11.1. Conceptual phases

- **Loading:** locates/reads the class.
- **Verification:** checks bytecode structure and related constraints.
- **Preparation:** prepares static fields and required state.
- **Resolution:** maps symbolic references to real entities.
- **Initialization:** runs class initialization when needed.

Exact resolution timing may be performed eagerly or lazily per the JVM specification. What does not change is that a nonexistent method reference can cause **NoSuchMethodError** when needed.

### 11.2. NoSuchMethodError vs NoClassDefFoundError

If source calls a **new method on an existing class** like **String.isBlank()**, Java 8 still has **java.lang.String**, just not that method. The typical failure is **NoSuchMethodError**.

If source directly references **a class present only in a newer JDK**, an older runtime can hit **NoClassDefFoundError** or **ClassNotFoundException** depending on how it is looked up/loaded.

For example, **java.util.HexFormat** exists only since Java 17; an application targeting Java 11 yet miscompiled with a newer JDK can stumble when loading/using that class on Java 11.

### 11.3. UnsupportedClassVersionError differs from both above

If the compiler emits a class file exceeding the major version supported by the runtime JVM, the JVM can reject the class before reaching any API call.

To investigate properly, first check the **class major version**, then check **method/class references** and the runtime classpath.

## 12. Bonus exercise: new Collection APIs

Create file **ListTrap.java**:

~~~java
import java.util.List;

public final class ListTrap {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Binh");
        System.out.println(names);
    }
}
~~~

**List.of()** was introduced in Java 9. It does not exist in Java 8.

### 12.1. Try compiling with source/target

~~~bash
javac -source 8 -target 8 \
  -d out/source-target \
  src/ListTrap.java
~~~

Javac 21 can compile it because JDK 21 provides **List.of()**, while the call syntax remains Java 8 compatible.

### 12.2. Run on Java 8

~~~bash
/opt/jdks/jdk8/bin/java \
  -cp out/source-target \
  ListTrap
~~~

Expect **NoSuchMethodError** for **java.util.List.of(...)**.

### 12.3. Switch to --release 8

~~~bash
javac --release 8 \
  -d out/release \
  src/ListTrap.java
~~~

Expect the compiler to report **List.of()** cannot be found in the Java 8 API.

### 12.4. Intentional fix

A Java 8 compatible version:

~~~java
import java.util.Arrays;
import java.util.List;

public final class ListTrap {
    public static void main(String[] args) {
        List<String> names = Arrays.asList("An", "Binh");
        System.out.println(names);
    }
}
~~~

**Note:** **Arrays.asList** and **List.of** have different semantics. List.of creates an unmodifiable list that rejects nulls; Arrays.asList creates a fixed-size list backed by an array, allowing element replacement via **set** and permitting nulls. If business code relies on immutability or null rejection, choose an alternative with matching semantics, not just an older API with a similar name.

## 13. Bonus exercise: when the baseline is Java 11

In many modern projects, the baseline is not Java 8 but Java 11.

An example:

~~~java
public final class ApiTrap11 {
    public static void main(String[] args) {
        String message = "Hello %s".formatted("migration");
        System.out.println(message);
    }
}
~~~

**String.formatted()** appeared in Java 15 and does not exist in Java 11.

Try with javac 21:

~~~bash
javac -source 11 -target 11 \
  -d out/source-target \
  src/ApiTrap11.java
~~~

Expect compilation into class-file **major 55**, yet running on Java 11 encounters a missing method error.

Use:

~~~bash
javac --release 11 \
  -d out/release \
  src/ApiTrap11.java
~~~

Expect the compiler to detect that the **formatted** call is not part of the Java 11 API.

### 13.1. Why add the Java 11 exercise?

It proves the problem is not limited to Java 8. **Any migration compiling on a newer JDK while supporting an older runtime** must distinguish:

- Source/language target.
- Bytecode target.
- Java SE API target.
- Execution runtime.

## 14. Side experiment: source syntax exceeding the release

To see how **-source** protects the language, create file:

~~~java
public record Point(int x, int y) {
}
~~~

Records are a standard language feature starting in Java 16.

If using:

~~~bash
javac -source 8 -target 8 \
  -d out/source-target \
  src/Point.java
~~~

The compiler rejects record syntax because of **-source 8**.

This clarifies the difference:

- **New syntax features**: typically blocked by **-source**.
- **New API calls using old syntax**: can slip past **-source/-target**.
- **--release**: also blocks Java platform API calls beyond the release.

Do not conclude **-source/-target are useless**; they perform their intended job, which is simply incomplete for runtime compatibility goals.

## 15. Why was using -bootclasspath once popular?

In older build systems, developers could specify a bootclasspath containing the target JDK's classes to prevent the compiler from seeing newer APIs.

Old model:

~~~text
new javac
   |
   +--> -source 8
   +--> -target 8
   +--> Java 8 bootclasspath
   |
   v
Restrict visible APIs
~~~

However, this approach has issues:

- Requires preparing exact old JDK boot classes.
- Easy to misconfigure paths or modules.
- Inconvenient for the JDK 9+ platform module system.
- Can diverge between local and CI configurations.
- Must distinguish Java 8 **rt.jar** from newer modular JDKs.

**--release** was designed to handle platform-release cross-compilation more conveniently. Do not misuse bootclasspath or manually modify JDK installations when javac supports **--release**.

## 16. Gradle: replacing sourceCompatibility/targetCompatibility with options.release

Suppose **build.gradle** has:

~~~groovy
plugins {
    id 'java'
}

sourceCompatibility = JavaVersion.VERSION_1_8
targetCompatibility = JavaVersion.VERSION_1_8
~~~

If Gradle runs **javac 21** without configuring **--release**, setting source/target to Java 8 does not guarantee blocking Java 11 APIs like **String.isBlank()**.

### 16.1. Recommended configuration for Java 8 target

~~~groovy
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
}
~~~

Meaning:

- Compiles using the JDK 21 toolchain.
- Constrains syntax, bytecode, and Java platform APIs to the Java 8 target.
- Catches the **String.isBlank()** call right at compile time.

**Use a Gradle version that still supports the corresponding JDK and target release configuration.** Do not infer that every Gradle release can run daemon/test tasks on both Java 8 and Java 21.

### 16.2. Gradle Kotlin DSL

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(8)
}
~~~

Choose Groovy or Kotlin DSL per project; no need to maintain both.

### 16.3. Building with --release is not enough for runtime tests

Gradle can compile targeting Java 8 using JDK 21 while running the **Test** task on Java 21. In that case, a dependency JAR that only runs on Java 21 can still slip through undetected.

At least one **Java 8 runtime smoke/integration test** on the released artifact is needed if Java 8 is in the support policy.

### 16.4. Do not use a test JVM too old for unsupported tools

Newer Gradle/Test/coverage plugin versions may have high minimum Java versions. If a Java 8 test launcher is unsupported by the current stack, separate a runtime smoke job executing the artifact with Java 8 or select tool versions per support policy.

Do not produce a green test lane by skipping all execution tests on Java 8.

## 17. Maven: using maven.compiler.release

With a modern Maven Compiler Plugin supporting **release**:

~~~xml
<properties>
    <maven.compiler.release>8</maven.compiler.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.1</version>
            <configuration>
                <release>8</release>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

The version in the example illustrates syntax only. For real projects, check Maven Compiler Plugin, JDK, and Maven runtime compatibility.

### 17.1. Misleading configuration

~~~xml
<properties>
    <maven.compiler.source>8</maven.compiler.source>
    <maven.compiler.target>8</maven.compiler.target>
</properties>
~~~

If the actual javac is a newer JDK, these two properties do not carry the same API compatibility meaning as **release**.

### 17.2. Maven Toolchains

If the Maven process runs on JDK 21 while the compiler is selected as JDK 8, javac 8 naturally compiles against Java 8 APIs. However, that is a different toolchain design from **javac 21 --release 8**.

Explicitly record:

- Which JDK Maven runs on.
- Which actual javac is the compiler.
- What the **release** target is.
- Which JDK the test executor uses.
- Which JVM plugins/annotation processors run on.
- Which runtime the final artifact is tested on.

Maven Compiler Plugin and test plugins have separate toolchain support; do not assume compiler toolchains automatically govern all Maven goals.

## 18. Crucial limitation: --release does not check all third-party libraries

**--release 8** is very useful for restricting **Java platform APIs** to Java 8. Yet it is not a validator for the entire dependency graph.

Example:

~~~text
Application --release 8
       |
       +--> LegacyCompatibleLibrary.class (major 52)
                     |
                     +--> calls String.isBlank() (Java 11)
~~~

Suppose a library was miscompiled with **-source 8 -target 8**, just like the first experiment. The application calls the library's public API without calling **String.isBlank()** directly in application source.

### 18.1. How does the bug still slip through?

Application source:

~~~java
public final class App {
    public static void main(String[] args) {
        System.out.println(LegacyCompatibleLibrary.isInputBlank("  "));
    }
}
~~~

Library source:

~~~java
public final class LegacyCompatibleLibrary {
    public static boolean isInputBlank(String value) {
        return value.isBlank();
    }
}
~~~

If the library was previously compiled with **javac 21 -source 8 -target 8** into class major 52, and then the application compiles with **--release 8** and a classpath containing that library:

- Application source only calls the library method.
- The library class file has Java 8 format.
- The application compiler does not necessarily re-analyze every method body inside dependencies.
- The Java 8 runtime can still fail when executing the library code.

**--release does not retroactively fix misbuilt bytecode or dependencies.**

### 18.2. Remediation

- Confirm minimum Java versions of dependencies from vendors.
- Evaluate bytecode versions of JARs.
- Check transitive dependencies and shaded JARs.
- Run integration/smoke tests on a real older runtime.
- Use dependency validation/SBOMs and build reproducibility.
- When libraries are under your control, build them with the appropriate **--release**.
- Do not ship artifacts relying solely on class-file major versions.

### 18.3. Class major version cannot prove every API reference

A tool that only checks all class majors <= 52 will miss **String.isBlank()** inside a major 52 class. That is the exact point of this exercise.

Distinguish:

- Class-file version scanner: detects bytecode that is too new.
- Java platform API compatibility checker: detects platform APIs that are too new.
- Runtime integration test: verifies behavior/dependencies.
- Public API diff tool: checks published library interfaces.

These tools complement one another rather than being synonymous.

## 19. Cases where --release alone is still insufficient to guarantee runtime

Beyond miscompiled dependencies, several other error sources exist:

### 19.1. Reflection and dynamic invocation

Source may use:

~~~java
Class.forName("java.util.HexFormat");
~~~

The **Class.forName** call itself has existed for a long time, while the class name is a string. Compiling with **--release 8** does not check from the string alone whether that class actually exists at runtime.

If the Java 8 runtime lacks **java.util.HexFormat**, errors can occur at runtime.

### 19.2. ServiceLoader and resource configurations

A service provider class may exist or run only on a newer JDK. The compiler does not necessarily catch ahead of time all errors occurring when loading providers by name from **META-INF/services**.

### 19.3. JNI and native code

JNI/native libraries may not support the target OS/architecture/JDK. Valid bytecode targets do not resolve binary dependencies.

### 19.4. Java agents and instrumentation

Byte Buddy, Mockito, JaCoCo, APM agents, or bytecode libraries may require versions supporting the newer compiler/runtime. Those failures are tool/runtime compatibility, not purely platform API compatibility.

### 19.5. JDK behavior and security policies

TLS, truststores, GC, locale, charset, timezone, or reflection policies can change across JDKs, even when code uses longstanding APIs.

### 19.6. Multi-release JARs

The same JAR may contain class variants under **META-INF/versions/**. Old and new runtimes can select different implementations. Test each real runtime.

**Section conclusion:** **--release** catches an important class of compile-time mistakes, yet does not replace runtime tests and integration tests.

## 20. Using javap and inspection tools for the right purpose

### 20.1. javap -verbose

Used to inspect major class-file version, constant pool, and method references.

~~~bash
javap -verbose -classpath out/source-target ApiTrap
~~~

### 20.2. javap -c

Used to inspect bytecode instructions, such as **invokevirtual String.isBlank()**.

~~~bash
javap -c -classpath out/source-target ApiTrap
~~~

### 20.3. jdeps

**jdeps** helps analyze static dependencies and detects many cases depending on JDK internal APIs, e.g., with appropriate options like **--jdk-internals**.

However, **do not treat a clean jdeps result with no warnings as proof that every Java platform API call belongs to Java 8**. Static dependency analysis and release API-signature validation are two different checks.

### 20.4. Animal Sniffer and API compatibility checkers

Some projects use **Animal Sniffer** or API signature checkers to guard target runtimes, particularly in build systems with custom needs.

If **--release** is already used with a supporting JDK, it is usually the most convenient baseline mechanism for Java SE platform APIs; additional tools can still help check non-platform APIs, libraries, or project policies.

### 20.5. Do not verify solely via a Build SUCCESS message

A build can succeed because:

- Tests ran on the new JDK, not the baseline.
- Generated classes are stale.
- Transitive dependencies were swapped in a local cache.
- Faulty code paths were untested.
- The build did not actually use the declared compiler.

Collect evidence: compiler version, flags, class major, API references, and runtime tests.

## 21. Designing CI so the error does not recur

A pipeline for a project that must support Java 8 can separate:

~~~text
Source commit
      |
      +--> Compile with javac 21 --release 8
      |          |
      |          +--> Block new platform APIs
      |
      +--> Package artifact
      |
      +--> Runtime smoke on Java 8
      |          |
      |          +--> Run real dependencies
      |
      +--> Runtime smoke on Java 21
      |          |
      |          +--> Verify behavior on target JDK
      |
      +--> Integration tests + security tests
      |
      v
Release gate
~~~

### 21.1. Why are both old and new runtimes needed?

- Java 8 runtime catches API/dependency incompatibilities against the baseline.
- Java 21 runtime catches behavior/framework/agent incompatibilities against the target.
- Both protect the rolling deployment period when both JDKs are supported concurrently.

### 21.2. One artifact or two artifacts?

If releasing a single Java 8 target artifact, test that exact artifact on both runtimes.

If releasing two variants, test per variant and set distinct identities. Do not let CI publish artifacts based on whichever job finishes last and overwrite content at the same coordinates.

### 21.3. Keep output directories independent

Separate build workspaces or outputs per CI job. Do not run javac 8 and javac 21 simultaneously writing into one shared directory and then inspect a class file that may have been overwritten.

### 21.4. Use clean builds

Generated sources or stale class files can mask compile errors. At minimum, release verification should have a clean, reproducible path independent of prior outputs.

## 22. Suggested automated tests for the experiment itself

The lesson test suite can include two kinds:

**Expected failure — API too new with --release 8:**

~~~text
Input: ApiTrap.java with String.isBlank()
Compiler: javac 21
Flags: --release 8
Expected: compilation fails
Reason: Java 8 API does not include isBlank()
~~~

**Expected runtime failure — misbuilt with -source/-target:**

~~~text
Input: ApiTrap.java with String.isBlank()
Compiler: javac 21
Flags: -source 8 -target 8
Expected compile: may succeed
Expected class major: 52
Runtime: Java 8
Expected runtime: NoSuchMethodError
~~~

**Expected success — fixed source and --release 8:**

~~~text
Input: ApiTrap.java with Java 8-compatible implementation
Compiler: javac 21
Flags: --release 8
Expected compile: success
Expected class major: 52
Runtime Java 8: success
Runtime Java 21: success
~~~

### 22.1. Do not assert exact compiler warnings

Warning text can vary by JDK vendor and patch version. Tests should focus on exit codes, presence/absence of valid artifacts, class major version, and runtime behavior.

### 22.2. Do not assert exact NoSuchMethodError messages

Method name and error type matter; message/stack-trace rendering can vary. If turning the experiment into programmatic tests, distinguish **NoSuchMethodError** from **UnsupportedClassVersionError** rather than matching exact strings.

### 22.3. The test lane must genuinely use Java 8

In CI, selecting a JDK on PATH can be overridden by the build tool via toolchains. For smoke tests, invoke a **java** executable with an explicit path/launcher and log its version right inside the test job.

## 23. A tough question: does using javac 8 solve it?

If using **javac 8** itself to compile:

~~~text
javac 8 -source 8 -target 8
~~~

the compiler sees Java 8 platform APIs, so source calling **String.isBlank()** will not compile.

However, there are trade-offs:

- CI must continue maintaining a JDK 8 compiler while JDK 8 may sit outside the project's maintenance policy.
- Newer build tools may not run on JDK 8.
- Annotation processors may require a newer JDK.
- Security support of the baseline JDK must be evaluated.
- Testing on an old compiler does not replace testing on the target compiler.

If the newer javac supports **--release 8**, using the newer javac with the release target is a useful way to maintain API/language compatibility. Yet testing on the older runtime remains necessary if the organization commits to supporting it.

## 24. Another tough question: does --release 8 block JDK internals?

**--release** primarily allows using APIs of the corresponding platform release defined for compilation. It also restricts relying on JDK-specific internals that are not part of the approved API.

Therefore, a codebase previously calling **sun.misc.*** or **com.sun.*** may hit compile errors when switching to **--release**, even though that code previously built with **-source/-target**.

This can be a signal that the project depends on internal APIs, not necessarily a bug in --release. Remediation:

- Find supported Java SE/JDK replacement APIs.
- Upgrade libraries/frameworks depending on internal APIs.
- Evaluate reflection/module compatibility.
- If a runtime-specific implementation is required, isolate and test it explicitly.
- Do not abuse **--add-exports** or **--add-opens** as a way to bypass every check.

Module-opening flags and **--release** have specific constraints on modern javac; read javac documentation for the actual JDK.

## 25. Java API compatibility is not library compatibility

Distinguish:

| API source | Does --release 8 fully protect it? | What else is needed? |
|---|---|---|
| Java SE 8 APIs supported by javac | Yes, within target release scope | Runtime tests |
| Java SE APIs introduced after Java 8 | Blocks direct calls in source | Compile tests |
| Third-party library compiled with major 52 calling Java 11 API | Does not automatically re-analyze library bodies | Runtime/integration tests |
| Major 65 library added at runtime | Does not guarantee every classpath path | Dependency audit/runtime |
| Reflection calling class/method names as Strings | Cannot fully verify statically | Runtime tests |
| Java agents/JNI | No | Compatibility matrix |
| Differences in TLS/GC/locale configuration | No | Per-runtime regression tests |
| Generated source | Yes if generated source is actually compiled with --release | Processor output/runtime tests |

A proper exercise should not end with "just add --release and everything is solved". **--release** solves the platform JDK API problem at compile time, while full system compatibility requires additional evidence.

## 26. Real-world scenario: SDK built on Java 17 while supporting Java 11

Suppose an SDK declares **minimum Java 11**. The team switches the compiler to JDK 17, keeping:

~~~text
-source 11
-target 11
~~~

A developer uses **java.util.HexFormat**, an API introduced in Java 17, inside the SDK's implementation.

The JDK 17 compiler accepts the syntax and sees HexFormat. The artifact class version still targets Java 11, yet when a consumer runs on Java 11, class **java.util.HexFormat** does not exist.

The failure mode depends on how the class is loaded and methods are called; it may involve **NoClassDefFoundError** or a class resolution failure, distinct from **String.isBlank()** which is a new method on an existing class.

If the SDK compiler uses **--release 11**, the direct reference to HexFormat is caught at compile time.

Takeaway: when seeing **UnsupportedClassVersionError**, check the class major version; when seeing **NoSuchMethodError/NoClassDefFoundError**, check API/platform class availability and the runtime dependency graph.

## 27. Review questions

### Question 1

Is a class with **major version 52** guaranteed to run properly on Java 8?

**Answer:** No. Java 8 understands bytecode format 52, yet the class may reference newer APIs or incompatible dependencies.

### Question 2

Does **-source 8** block calling **String.isBlank()** when the compiler is JDK 21?

**Answer:** Not necessarily. The call uses Java 8 syntax; if the compiler sees Java 21 platform APIs, it can compile.

### Question 3

What does **-target 8** control?

**Answer:** Target class-file format, which is insufficient to restrict all methods to Java 8 platform APIs.

### Question 4

Which bug in the lab does **--release 8** catch?

**Answer:** The direct call to **String.isBlank()**, a method absent from the Java 8 API.

### Question 5

Why can the Java 8 runtime raise **NoSuchMethodError** instead of **UnsupportedClassVersionError**?

**Answer:** The class-file version is already Java 8 (major 52), yet the method reference points to an API that did not exist in Java 8.

### Question 6

Is **--release 8** alone enough to protect all transitive dependencies?

**Answer:** No. It does not automatically analyze the entire body of pre-compiled JARs, reflection, or native dependencies. Runtime tests and dependency analysis are required.

### Question 7

Should **String.isBlank()** be replaced with **trim().isEmpty()** in every application?

**Answer:** No. The two can differ on certain Unicode whitespace characters; verify semantics before replacing.

### Question 8

Does CI compiling for target Java 8 using javac 21 and running unit tests on Java 21 prove Java 8 compatibility?

**Answer:** No. You must run the artifact on a real Java 8 runtime or have corresponding evidence for remaining runtime risks.

## 28. Common mistakes when running the lab

### 28.1. Accidentally using Java 21 to run the Java 8 runtime experiment

**Symptom:** The program prints **isBlank = true**, with no error.

**Solution:** verify the **java** executable path and **java -version** inside the exact terminal/job.

### 28.2. Failing to create separate output directories

**Symptom:** Compiling with **--release 8** fails, yet an old class file still sits in the output directory.

**Solution:** use separate **out/source-target** and **out/release** directories, cleaning build-owned outputs when needed.

### 28.3. Treating a warning as the main error

**Symptom:** Warnings about bootclasspath or source options make learners think compilation was blocked.

**Solution:** inspect exit code and class files; distinguish warnings from compile errors.

### 28.4. Running javap on source instead of the right class

**Symptom:** Cannot see major version or method reference.

**Solution:** point classpath to the newly compiled output directory.

### 28.5. Using javac 8 instead of javac 21

**Symptom:** Source calling isBlank is rejected immediately even with -source 8 -target 8.

**Solution:** this is normal behavior because javac 8 cannot see String.isBlank. The main lab requires **a newer javac** to expose the loophole.

### 28.6. Running the experiment on a JDK that no longer supports -source 8

**Symptom:** Compiler rejects the old release option.

**Solution:** check javac documentation and select a supported target/compiler pair; the illustrative example uses JDK 21.

### 28.7. Treating -Xlint:-options as a fix

**Symptom:** Warning vanishes, artifact still fails on Java 8.

**Solution:** use **--release 8**, do not just hide the warning.

### 28.8. Replacing an API with a helper that has different semantics

**Symptom:** ASCII tests pass while Unicode/production data diverges.

**Solution:** check behavior, edge cases, and contracts before changing code.

### 28.9. Believing a major-version scanner completes verification

**Symptom:** All classes are major 52, yet Java 8 still fails.

**Solution:** check method references and run real runtime tests.

### 28.10. Forgetting dependencies or generated code

**Symptom:** Main source uses --release 8, yet the app still fails due to library/processor output.

**Solution:** inspect the full artifact, dependencies, and test runtime.

## 29. Copyable practice checklist

### Preparation

- [ ] Have JDK 21 javac or a newer JDK supporting --release 8.
- [ ] Have a real Java 8 runtime to run the experiment.
- [ ] Checked versions of both executables.
- [ ] Created source ApiTrap.java with String.isBlank().
- [ ] Separated output directories across compilations.

### -source/-target experiment

- [ ] Ran javac 21 -source 8 -target 8.
- [ ] Recorded exit code and warnings if any.
- [ ] Inspected class-file major 52 with javap.
- [ ] Inspected method reference String.isBlank() with javap.
- [ ] Ran artifact with Java 8.
- [ ] Recorded NoSuchMethodError.
- [ ] Re-ran with Java 21 for comparison.

### --release experiment

- [ ] Ran javac 21 --release 8 on the original source.
- [ ] Confirmed compilation rejects the newer API method.
- [ ] Fixed source with an appropriate Java 8-compatible approach.
- [ ] Compiled --release 8 successfully.
- [ ] Ran artifact on Java 8.
- [ ] Ran on Java 21 if required by support policy.

### Applying to projects

- [ ] Gradle/Maven has an appropriate release target.
- [ ] Build JVM/compiler JDK is explicitly documented.
- [ ] Runtime smoke tests exist on the minimum JDK.
- [ ] Dependencies are checked for Java compatibility.
- [ ] Annotation processors/generated code are checked.
- [ ] No stale output/cache masks errors.
- [ ] CI matrix and release gate align with support policy.
- [ ] Public minimum Java version is declared accurately.

## 30. Lab result record template

~~~text
Lab ID: SOURCE_TARGET_API_TRAP
Application source:
Compiler vendor/version:
Compile flags A: -source 8 -target 8
A compile exit code:
A warning count:
A class major version:
A referenced API:
A runtime Java 8 result:
A runtime Java 21 result:

Compile flags B: --release 8
B compile exit code:
B compiler diagnosis:

After source fix:
Compile flags: --release 8
Class major:
Runtime Java 8:
Runtime Java 21:
Dependency/runtime notes:
Evidence paths:
Conclusion:
~~~

A record containing compiler version, classfile version, method reference, and runtime outcome is better evidence than merely writing "command succeeded".

## 31. References

Always verify against the exact JDK/compiler in use:

- **JEP 247 — Compile for Older Platform Versions:** https://openjdk.org/jeps/247
- **javac command (JDK 21):** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- **Java 21 Virtual Machine Specification, class-file format:** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html
- **JVM Specification — Loading, Linking and Initializing:** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html
- **String API, Java 8:** https://docs.oracle.com/javase/8/docs/api/java/lang/String.html
- **String API, Java 11:** https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/String.html
- **List API, Java 8:** https://docs.oracle.com/javase/8/docs/api/java/util/List.html
- **Gradle Java Toolchains:** https://docs.gradle.org/current/userguide/toolchains.html
- **Gradle JavaCompile options.release:** https://docs.gradle.org/current/dsl/org.gradle.api.tasks.compile.CompileOptions.html
- **Maven Compiler Plugin:** https://maven.apache.org/plugins/maven-compiler-plugin/
- **Maven Compiler Plugin — Set --release:** https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html
- **Animal Sniffer Maven Plugin:** https://www.mojohaus.org/animal-sniffer/animal-sniffer-maven-plugin/

Examples of stdout, line numbers, and warnings are presented according to expected compiler/runtime behavior, not fixed output across every JDK vendor.

---

**Conclusion:** The flags **-source 8 -target 8** can produce a **major 52** class file while still allowing code to call **String.isBlank()**, a method that exists only from Java 11. Java 8 reads the class format yet fails to find the method when linking the call, leading to **NoSuchMethodError**. Switching to **--release 8** makes javac detect calls to overly new platform APIs right at compile time. In real migrations, combine **--release**, dependency/generated-code checks, and **runtime tests on the minimum JDK**. Ensuring old bytecode is a necessary condition, not complete proof of Java compatibility.
