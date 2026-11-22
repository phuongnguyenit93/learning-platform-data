# Java Core Scope and How to Cross-Reference JDK Versions When Learning Abstraction/Interface

## 1. Reading the scope of this lesson accurately

In the topic **Java Core – abstract/interface**, “Java Core” is understood as the **Java language concepts and Java SE platform APIs** needed to design, implement, and use abstraction. This lesson focuses on how Java defines types and contracts, how classes implement them, how language rules change across JDK versions, and how to verify things yourself when documentation or an IDE gives different results.

Topics **within the primary scope**:

- **Language mechanisms:** `abstract class`, `abstract` methods, `interface`, `extends`, `implements`, overriding, access scope, reference types, polymorphism, and version-specific `default`/`static`/`private` methods in interfaces.
- **Contracts and design:** the boundary between what calling code is allowed to know and what an implementation must do; substitutability between implementations; when to choose an interface or an abstract class.
- **Java SE APIs as examples:** `Runnable`, `Comparable`, `Comparator`, `List`, `AbstractList`, `AutoCloseable`, and how to read API docs to determine the exact contract.
- **Version compatibility:** which syntax appears in which Java version, how to check the compiler/runtime, and how to compile targeting a Java release.

Things **not required to understand these fundamentals**: Spring DI/AOP, Hibernate, Gradle plugins, vendor SDKs, framework protocols, or large-scale system architecture. They may **use** interfaces and abstract classes, but the rules of those constructs are governed by the Java language. For example, Spring's `@Component` annotation does not determine whether a `private` method in an interface is valid in Java 8.

“Java Core” is a common learning term, **not the name of an official release independent of Java SE**. When an exact conclusion is needed, the statement must be tied to a **specific Java SE/JDK release**, such as Java 8, 17, or 21.

## 2. Distinguishing Java SE, JDK, JVM, libraries, and frameworks

| Concept | What is it used for? | Relevance to this lesson |
| --- | --- | --- |
| Java language | Specifies the syntax and semantics of `interface`, `abstract`, `sealed`, access modifiers, overriding… | **Authoritative source** for verifying which constructs are allowed to be written. |
| Java SE platform | Defines the standard APIs and the platform components required for general Java applications. | Provides contract examples such as `java.lang.Runnable`, `java.util.List`. |
| JDK (Java Development Kit) | Development toolkit containing the `javac` compiler, `java` launcher, Javadoc, and other tools along with a platform implementation. | Used to **compile/run/verify** compatibility. |
| JVM | Executes bytecode and provides runtime mechanisms, including class loading and dynamic method invocation. | Explains why a call through an interface can select an implementation at runtime. |
| External libraries/frameworks | Provide additional APIs, such as Spring, Jackson, JUnit. | Only an **application context**; they do not decide Java Core syntax rules. |

It is necessary to separate **the presence of a language feature** from **the presence of a library method**. For instance, starting in Java 8 there is default method syntax in interfaces; however, a specific method on `List` or `Comparator` must be checked separately on the Javadoc page for the **API version** in use.

The JDK and Java SE are also not completely identical: the JDK API documentation also includes JDK-specific tools/packages. An API being present in a JDK release does not automatically mean it belongs to the Java SE API contract usable across all platform implementations.

## 3. Version milestones that actually affect interfaces and abstraction

This table lists **standardized feature milestones**, rather than assuming all Java versions share the same syntax.

| Java release | Notable changes | Practical impact |
| --- | --- | --- |
| Java 7 and earlier | Basic interfaces have abstract method contracts and constants; no default/static methods with bodies in interfaces yet. | Implementing classes must provide implementations for abstract methods that they have not inherited from elsewhere. |
| **Java 8** | Interfaces support `default` and `static` methods; lambdas and functional interfaces are an important part of Java 8 programming. | Can provide default behavior while preserving the contract; can pass a lambda where an interface has exactly one abstract method. |
| **Java 9** | Interfaces are allowed to have `private` instance/static methods. | Default/static methods can share internal logic without exposing it as public API. |
| Java 16 | `record` becomes an official feature. | Easy to describe shallowly immutable data with declared components; a record can `implements` interfaces. This is not a replacement for every abstract class. |
| **Java 17** | `sealed class` and `sealed interface` become official features. | Intentionally restricts which types can directly `extends`/`implements` an abstraction. |

What **remains consistent throughout**: an interface represents a type/contract; an abstract class can contain shared state and behavior; a Java class directly inherits from only one superclass but can implement multiple interfaces; overriding methods must obey the language contract.

When learning an API, **“Since: 8” on a Javadoc page** indicates the milestone when that API appeared; whereas **JEPs/the Java Language Changes page** indicate the status of a language feature. These two kinds of information answer two different questions.

### 3.1. Java 8: default and static methods in interfaces

Create the file **`CoreVersionDemo.java`**:

```java
public class CoreVersionDemo {
    interface Greeter {
        String name(); // implicitly public abstract

        default String greet() {
            return "Hello, " + name();
        }

        static String topic() {
            return "Java Core";
        }
    }

    static final class Student implements Greeter {
        @Override
        public String name() {
            return "Lan";
        }
    }

    public static void main(String[] args) {
        Greeter greeter = new Student();
        System.out.println(greeter.greet());
        System.out.println(Greeter.topic());
    }
}
```

If you are using **JDK 17** as the compiler:

```bash
javac --release 8 CoreVersionDemo.java
java CoreVersionDemo
```

Output:

```text
Hello, Lan
Java Core
```

Explanation: `name()` is the abstract contract, and `Student` must implement it; `greet()` is a default method usable through a `Greeter` object; `topic()` is called via the **interface name**. For interfaces, `static` methods are not inherited like instance methods. `default` does **not** mean “Java will automatically choose how to handle every multiple-inheritance conflict”: when two unrelated interfaces provide default methods with the same signature, the implementing class generally has to resolve the conflict itself by overriding.

Because the target of this example is Java 8, do not use `var`, `record`, `sealed`, or interface private methods in the same file.

### 3.2. Java 9: private helper method in an interface

Create a separate file **`InterfacePrivateDemo.java`**:

```java
import java.util.Locale;

public class InterfacePrivateDemo {
    interface Formatter {
        default String title(String value) {
            return normalized(value).toUpperCase(Locale.ROOT);
        }

        private String normalized(String value) {
            return value.trim();
        }
    }

    static final class BasicFormatter implements Formatter {
    }

    public static void main(String[] args) {
        Formatter formatter = new BasicFormatter();
        System.out.println(formatter.title("  java core  "));
    }
}
```

Compile using JDK 17 with release 9 and then run:

```bash
javac --release 9 InterfacePrivateDemo.java
java InterfacePrivateDemo
```

Output:

```text
JAVA CORE
```

If changed to `javac --release 8 InterfacePrivateDemo.java`, the compiler **must reject** it because Java 8 does not support private methods in interfaces yet. Regardless of whether the running JDK 17 understands the new syntax, `--release 8` enforces checking against the rule set supported for target 8. Error message content may differ between compiler versions.

Note: `private` in an interface is for helpers with a body, not a way to declare an abstract method for external implementing classes to override.

### 3.3. Java 17: restricting direct implementations with a sealed interface

Create the file **`SealedDemo.java`**:

```java
public class SealedDemo {
    sealed interface Result permits Ok, Failed {
    }

    record Ok(String value) implements Result {
    }

    record Failed(String reason) implements Result {
    }

    public static void main(String[] args) {
        Result result = new Ok("done");
        System.out.println(result instanceof Ok);
    }
}
```

Compile and run with a JDK 17+ that supports target 17:

```bash
javac --release 17 SealedDemo.java
java SealedDemo
```

Output:

```text
true
```

In this example, `Result` restricts the **types allowed to directly implement** it to `Ok` and `Failed`. Both `record` types are inherently final, so they satisfy the rules for permitted subtypes. Another class cannot arbitrarily `implements Result`. It is important to distinguish the scope of `sealed`: it controls type extension relationships, and **does not automatically guarantee** data validation, security, or deep immutability of every object.

Code using `record` and `sealed` does not compile when targeting `--release 8` or `--release 11`. If you encounter examples using `sealed` in JDK 15/16, that was during the **preview** stage, so you need to check the exact status of that release; in Java 17, `sealed` is already a standard feature and does not require `--enable-preview`.

## 4. Which documentation should you cross-reference?

When there is a conflict between a blog post, an IDE, and a code snippet, you should look it up in order of the question you need to resolve:

| Question | Source to open | How to read it |
| --- | --- | --- |
| “From which Java version is this syntax valid?” | **Java Language Changes** and **Java Language Specification (JLS)** for the release | Identify keywords, modifiers, language restrictions, and final/preview status. |
| “Since when has `List` or `Comparator` had this method?” | **Version-specific API Javadoc**, the specific class/interface page | Check the signature, `Since`, `default`/`static`, error conditions, and `@Deprecated`. |
| “Was the feature in preview or already stable?” | The relevant **JEP** and release notes | Compare proposal status, preview/incubator, final, and changes across each release. |
| “Which JDK version can compile/run the code?” | `javac` and `java` documentation, and actual tool output | Check the selected JDK, `--release`, classpath/module path, and runtime. |
| “Which JDK should be chosen for a long-term project?” | Release/support roadmap of the specific JDK vendor | Distinguish feature releases from LTS, support durations, and vendor-specific licenses. |

Useful **official** links:

1. [Java Language Changes – Java 17](https://docs.oracle.com/en/java/javase/17/language/java-language-changes-release.html) — language milestones; includes the `sealed` and `record` sections.
2. [JLS Java SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/index.html) — official language rules; look up the sections on Interfaces, Classes, and Method Declarations.
3. [Java SE 17 & JDK 17 API Specification](https://docs.oracle.com/en/java/javase/17/docs/api/index.html) — look up individual API signatures, packages/modules, `Since`, and `@Deprecated`.
4. [`javac` JDK 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html) — the `--release`, `--source`, and `--target` options.
5. [JEP 409: Sealed Classes](https://openjdk.org/jeps/409) — history and status of sealed types.
6. [Oracle Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html) — release schedule and LTS classification.
7. [JDK 27 Release Notes (Sep 15, 2026)](https://www.oracle.com/java/technologies/javase/27all-relnotes.html) — an example of a page documenting changes in a release newer than Java 17.

Each document has its own **version**. Do not read the Java 21 Javadoc and claim that an API exists in Java 8, or use the Java 17 JLS to infer Java 8 syntax. For older Oracle tutorials, read the version notice if the document states that it was written for JDK 8.

**Time reference to state explicitly when comparing “latest”:** as of **October 23, 2026**, JDK 27 is the feature release shipped in September 2026, while JDK 25 is Oracle's latest LTS release on the published list. `LTS` is a release support policy, **not** syntax or the `interface` type system. When reading this lesson at a later date, re-check the roadmap instead of assuming these numbers remain current.

## 5. How to verify the actual Java/JDK on your machine

### Step 1: inspect which compiler and runtime are being invoked

Open a terminal in the project directory and run:

```bash
java -version
javac -version
```

Both commands need to be checked **separately**, because the system may point `java` and `javac` to two different JDK installations depending on `PATH`, `JAVA_HOME`, the IDE, or the build toolchain configuration. `java -version` displays the runtime; `javac -version` displays the compiler. You cannot infer the actual build JDK solely from the “Project SDK” UI setting if the build uses a different toolchain.

If `javac` does not exist while `java` runs, the environment might only have a runtime installed or `PATH` might not point to the JDK's tools directory. Check your JDK installation and shell configuration.

### Step 2: choose the target version rather than defaulting to the compiler version

With a JDK that supports Java 8/9/17, use the commands:

```bash
javac --release 8 CoreVersionDemo.java
javac --release 9 InterfacePrivateDemo.java
javac --release 17 SealedDemo.java
```

**`--release N`** instructs the compiler to check syntax according to Java N, generate class files for that version, and compile against the platform API set published by release N. This is the preferred option when you want to verify compatibility with Java N.

Do not confuse these:

- `--source N` restricts **language syntax**, but on its own does not prove that the code only uses APIs present in Java N.
- `--target N` selects the **target bytecode format**, which is also insufficient to restrict APIs to Java N if misconfigured.
- `--release N` combines the aspects above with checking against the platform APIs of release N. Do not combine `--release` with `--source` or `--target` in the same command.

`javac` only supports a **finite set of target releases**; running `javac --help` on the JDK currently in use shows the supported list. A newer JDK does **not necessarily** still support compiling for every very old release.

### Step 3: verify the target runtime

Compiling successfully with `--release 17` does **not** mean the `.class` file can be run on Java 8. The runtime must support the class file format and the features/APIs required by the program; the standard approach is to use a runtime at or newer than the target version and verify actual dependencies.

For example, when `SealedDemo.java` is compiled with `--release 17`, run it with a Java 17+ runtime:

```bash
java SealedDemo
```

If you encounter `UnsupportedClassVersionError`, re-check the output of `java -version`, the compilation version, and the location of the class file being loaded. If you encounter `NoSuchMethodError` or `ClassNotFoundException`, you also need to inspect API differences and the dependency/runtime classpath; changing `--target` alone is not enough to guarantee compatibility.

### Step 4: with build tools, cross-check the version in all three places

In a project using Maven/Gradle/an IDE, identify:

1. **JDK running the build/compiler**: the selected `javac` version or Java toolchain.
2. **Target compilation release**: the compiler's `release` setting; in a Gradle project this may be `options.release`, and in Maven `maven.compiler.release`.
3. **JDK running the application**: the `java` version in the execution environment or container.

A project can run its build on JDK 21 while emitting bytecode targeting Java 17 if the compiler supports `--release 17`. That does not make Java 21 syntax automatically valid in files compiled for Java 17.

## 6. Process for verifying a specific claim

Suppose you see the statement: “In Java, an interface can declare a private method”. A rigorous way to verify this is:

1. **Turn it into a versioned question:** “Can a private instance method be declared in an interface in **Java 8**? What about **Java 9**?”
2. **Check the language source:** the *Java Language Changes* page records the milestone for private interface methods as Java 9.
3. **Write the smallest compilable sample:** use `InterfacePrivateDemo.java` above, isolated from frameworks.
4. **Compile both targets using the same suitable JDK:** `--release 8` will be rejected; `--release 9` is valid.
5. **Conclude with the exact scope:** “Private helper methods in interfaces are supported starting from Java 9”; do not overgeneralize to “any interface method can be private abstract” or “Java 8 supports it too because JDK 17 is installed”.

Similarly, for the statement “an interface can have implemented methods”, you need to ask what kind of method: `default`/ `static` from Java 8; `private` helper from Java 9. For “Can `sealed interface` be used?”, you must ask whether it is preview in Java 15/16 or a standard feature in Java 17 and later.

When sources disagree, record the **Java version**, **documentation URL**, **javac command**, **minimal input**, and **observed output** in full. A video or blog post that omits the version is not sufficient to refute the compiler and the version-matched specification.

## 7. Important boundaries and common mistakes

- **Do not confuse keywords with libraries.** `abstract`/`interface` belong to the language; `List`/`Comparator` are APIs; Spring is a framework. Each category requires an appropriate reference source.
- **Do not use a newer JDK to infer an older JDK.** A program running on Java 17 using record/sealed syntax does not prove it runs or compiles for Java 8.
- **Do not equate the JDK with the Java SE spec.** Certain specific tools and APIs belong to the JDK, not to the general Java SE guarantee. Do not depend on internal APIs merely because the compiler on your machine happens to see them.
- **Do not misunderstand `default` methods as “needing no implementation”.** `default` provides an implementation directly in the interface, yet is still subject to overriding, conflict resolution, and access rules.
- **Do not equate LTS with feature recency.** LTS relates to the support policy; a newer non-LTS release may add features, though it may not suit every operational strategy.
- **Do not overlook preview features.** A feature in preview status may require specific compile/run flags and may change before becoming finalized. Do not take preview examples and present them as universal Java SE syntax.
- **Do not let API docs of a newer version obscure `Since` and `Deprecated`.** A method might not exist yet, may have changed status, or may have been removed in the target version.
- **Do not generalize a test result to every environment.** A standalone example checks syntax; real builds also depend on the module path, classpath, annotation processors, build tools, and target runtime.

## 8. Checklist to apply to every abstract/interface lesson going forward

Before reading or writing an example, confirm for yourself:

- Is this a **Java language rule** or a **library API**?
- Which **Java version** does the lesson use; in which release did the feature appear; is it final or preview?
- Is the compiler using the **right `--release`**; does the JDK installation support that release?
- Does the execution runtime have the capabilities matching the compiled binary and the required APIs?
- Does the abstraction example require any **external libraries**? If so, separate Java Core rules from that library's behavior.
- Is the conclusion based on version-matched **JLS/Javadoc/JEP/release notes** and a minimal reproducible example?

**Self-practice:** Try compiling the three files `CoreVersionDemo.java`, `InterfacePrivateDemo.java`, and `SealedDemo.java` using JDK 17 with `--release 8`, `--release 9`, and `--release 17`, respectively. Next, deliberately lower `--release` for the latter two files and explain why the compiler rejects them. Cross-reference your conclusions with Java Language Changes rather than relying on whether the IDE highlights the syntax.

**Remember:** in Java Core, abstraction/interface syntax and contracts are determined by the **language version**; platform APIs are specified by the **Java SE version**; `javac --release` together with the runtime environment turns claims into verifiable facts. Always state the version explicitly before concluding “yes” or “no” for a feature.
