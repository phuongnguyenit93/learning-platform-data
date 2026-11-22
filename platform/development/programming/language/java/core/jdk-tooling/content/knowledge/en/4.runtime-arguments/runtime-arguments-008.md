# The --enable-preview Option in Java

Java evolves its platform release by release. Some new features are introduced into the JDK in **Preview** status so developers can experiment, evaluate, and submit feedback before the feature is finalized. The **--enable-preview** command-line option enables the preview features of the current Java release when compiling or running a program.

This is an option scoped to the JDK version. To use a preview feature properly, you must identify which Java release the feature belongs to, compile with the corresponding JDK, and enable preview at the right stages of the workflow.

## 1. What is a preview feature?

A **preview feature** is a feature released in a Java version for developers to try out before a decision is made to finalize it. Depending on the feature, a preview may involve the Java language, library APIs, or the virtual machine.

A preview feature typically has the following characteristics:

- It has documentation clearly describing the feature and the release that introduces it.
- Its design, syntax, or API may change in a subsequent preview round.
- It may be finalized as a permanent feature, continue in preview, or be removed.
- It must be explicitly enabled according to the rules of the JDK that releases it.

Preview is a release status with a formal process and official documentation. It does not mean the feature is guaranteed to have the same compatibility stability as finalized Java features.

### Lifecycle of a preview feature

A feature may go through the following stages:

1. **Proposal and development:** the design is discussed, usually described in a JEP.
2. **Preview:** the feature appears in a Java release and is enabled with **--enable-preview**.
3. **Subsequent preview (if any):** syntax, API, or behavior may be adjusted based on feedback.
4. **Final or withdrawn:** the feature may become permanent or be withdrawn from the platform.

Not every feature needs multiple preview rounds. The status and version of each feature must be checked against the corresponding JEP and Java release documentation.

### How does preview differ from a finalized feature?

| Aspect | Preview feature | Finalized feature |
|---|---|---|
| Enabling usage | Requires the appropriate preview option | Usually does not require --enable-preview |
| Cross-version compatibility | May change or be withdrawn | Follows standard Java compatibility policy |
| Purpose | Experimentation and gathering feedback | Stable usage in the platform |
| Production suitability | Requires accepting the risk of changes | Better suited for applications needing long-term stability |

A preview feature should not be confused with an **incubator module**. Incubator modules provide experimental APIs through a separate module mechanism; not every experimental API is enabled with --enable-preview. Read the documentation for the specific feature you are using.

## 2. Where does --enable-preview apply?

This option appears at different stages:

- **Compilation:** passed to **javac** so the compiler accepts preview syntax or APIs supported in that version.
- **Execution:** passed to **java** so the JVM allows running programs that use preview features.
- **Build and test tools:** configure flags separately for the compiler and for the JVM running tests if those processes use preview features.

Enabling preview during compilation does not automatically enable preview at runtime. If compiled source code uses a preview feature, the launch command must also be configured accordingly.

**--enable-preview** enables the set of preview features for the current release; it is not an option to select a single specific JEP. Which features are actually used still depends on the source code, APIs, and capabilities of that JDK.

## 3. Relationship between --enable-preview, --release, and --source

**javac** needs to know the target language version and platform. Related options include:

- **--release N:** compiles against Java platform version N, including the corresponding language level, class file format, and Java SE API set.
- **--source N:** selects the source language level accepted by the compiler.
- **-target N:** selects the output class file version.
- **--enable-preview:** enables preview features of the current Java release.

When using preview, the target version must match the release of the running compiler. For example, to use a Java 21 preview feature, use JDK 21 and specify **--release 21** (or **--source 21** as needed).

~~~bash
javac --enable-preview --release 21 -d out PreviewDemo.java
~~~

You cannot use the JDK 22 compiler to enable Java 21 preview features by setting **--release 21 --enable-preview**. Preview is only supported for the current release of the compiler. If the compiler is JDK 22, the enabled preview features are those of Java 22.

**--release** is usually preferable when you need to restrict the target platform APIs as well. Avoid simply combining **-source** and **-target** and assuming the program is guaranteed to use only APIs available in the target version.

## 4. Example: unnamed pattern preview in Java 21

Java 21 introduced **Unnamed Patterns and Variables** in preview status. This feature allows using an underscore `_` when you do not need to name a variable matched by a pattern.

Create the file `PreviewDemo.java`:

~~~java
public class PreviewDemo {
    static String classify(Object value) {
        return switch (value) {
            case String _ -> "text";
            case Integer number -> "integer";
            case null -> "null";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("hello"));
    }
}
~~~

In the **case String _** branch, the program only needs to check whether the value is of type `String`; it does not use a variable representing the string, so the pattern uses `_` instead of a variable name. The **case Integer number** branch still names `number` because an example might need that value in its processing logic.

With JDK 21, compile:

~~~bash
javac --enable-preview --release 21 -d out PreviewDemo.java
~~~

Run:

~~~bash
java --enable-preview -cp out PreviewDemo
~~~

Output:

~~~text
text
~~~

This example uses a Java 21 preview feature. Unnamed patterns and variables were finalized in Java 22; therefore, the same `_` syntax has different statuses depending on the version. On Java 22 and later, this feature no longer needs to be enabled as a preview. The illustrative example must therefore be compiled and run with JDK 21 to properly demonstrate the purpose of `--enable-preview`.

## 5. Why must preview be enabled at both compile time and runtime?

The compiler needs the preview flag to accept unfinalized features of that version. When using a preview language feature, the class file is marked as depending on the preview of that specific release.

At runtime, the JVM checks this compatibility. Therefore:

- Omitting **--enable-preview** at the compile step can cause the compiler to report syntax errors or reject preview APIs.
- Enabling preview at compile time but omitting the flag at the run step can cause the JVM to reject the preview class file.
- Compiling with JDK 21 and running on JDK 22 does not turn a Java 21 preview class file into a Java 22 preview class file.
- A class file that uses preview can only be run with the exact Java release that generated it, with preview enabled.

Some common errors may relate to missing the preview flag or running a class file on the wrong JDK version. When encountering errors, check both the actual compiler and runtime, not just the Java version displayed by the IDE.

## 6. Configuration when running with build tools and IDEs

In projects using Maven, Gradle, or an IDE, adding the flag for the compiler alone is not enough. You must ensure the JVM launching tests and the application also receives **--enable-preview**.

Typically, you need to check the following points:

1. **JDK toolchain:** the project compiler uses the exact JDK version that introduces the preview feature.
2. **Compile task:** pass **--enable-preview** and the corresponding **--release** version to the compiler.
3. **Test task:** pass **--enable-preview** to the JVM running unit tests or integration tests if the tests/application use preview features.
4. **Run/debug configuration:** configure JVM arguments for the process running or debugging the application.
5. **CI pipeline:** use the exact JDK and pass the flags in both compile and test/run so CI results match the developer's machine.

The specific configuration field names depend on the version of the Maven Compiler Plugin, Surefire, Gradle, and the IDE. Configure the flags on the appropriate tasks rather than just adding a generic compiler argument string and assuming all child JVMs will receive it.

With a direct run command, the placement of the flag is clear:

~~~bash
java --enable-preview -cp out PreviewDemo
~~~

This flag belongs to the JVM launched by the command above. If a build tool forks another JVM to run tests, that child JVM must also be configured.

## 7. Environment checks and troubleshooting

When using preview features, verify the exact compiler and runtime being invoked:

~~~bash
java --version
javac --version
~~~

Both commands should point to the same JDK line that the project intends to use. If the machine has multiple JDKs, check **JAVA_HOME**, **PATH**, and the separate JDK configuration in the IDE/build tool.

Some common scenarios:

| Symptom | Possible cause | Resolution |
|---|---|---|
| Compiler reports preview feature is not enabled | Missing --enable-preview in the javac command | Add the preview flag and select the matching release |
| Compiler reports preview is only supported for the current release | --release does not match the JDK compiler version | Use the matching JDK or avoid trying to compile preview features of an older release |
| JVM rejects the preview class file | Missing flag at runtime or using the wrong Java version | Enable preview and run on the exact JDK that produced the class file |
| Runs from terminal but tests fail | Test runner forks a separate JVM without the flag | Configure JVM arguments for the test task |
| IDE reports errors but CLI compiles | IDE uses a different JDK or language level | Align Project SDK, compiler level, and run configuration |
| CI build fails | CI uses a different JDK than the developer machine | Pin the toolchain and verify versions in the pipeline |

You can use **javap -v** to inspect class file metadata. For preview class files, the version information can show preview indicators; this is an additional check when investigating incompatibilities between the compiler and runtime.

## 8. Risks and responsible usage

Preview features are useful for evaluating new capabilities, testing syntax, and providing feedback for Java's evolution. However, because the design may change, long-term reliance on preview creates upgrade costs:

- Source code may need modifications when syntax or APIs change.
- Each JDK upgrade may require updating compiler flags and runtime flags.
- Preview class files are tied to the exact Java release that created them.
- Production, CI, test, and developer machine environments must all standardize on the same version.
- A feature may be withdrawn before becoming permanent.

Before using preview in a project, define the experimentation goals, JDK version, scope of affected code, and migration plan for when the feature is finalized or changed. For systems requiring long-term compatibility, prefer finalized APIs and language features.

## 9. Checklist for using --enable-preview

- Identify the preview feature name and the JDK release that introduces it.
- Read the JEP or release notes to confirm the feature's status in the release being used.
- Install that exact JDK release; check **java --version** and **javac --version**.
- Pass **--enable-preview** to the compiler and use **--release** or **--source** matching the current release.
- Pass **--enable-preview** to the JVM running the application.
- Separately configure the JVMs running unit tests, integration tests, and debugging.
- Use the same JDK release on developer machines and in CI.
- Do not run preview class files with a different release.
- Evaluate the risk of changes before introducing a preview feature into production.
- When the feature becomes permanent, remove the preview flag if no other preview features are needed and update the configuration to stable mode.

## 10. Key terminology

| Term | Meaning |
|---|---|
| Preview feature | A feature released for experimentation and gathering feedback |
| --enable-preview | Enables preview features of the current JDK release |
| --release | Selects the target Java platform version when compiling |
| --source | Selects the source language level |
| -target | Selects the output class file version |
| JEP | Java Enhancement Proposal, a document describing a feature proposal and its development status |
| Incubator module | A module providing experimental APIs via the incubator mechanism |
| Preview class file | A class file that depends on preview features of a specific release |
| Runtime argument | An option passed to the JVM when launching an application |

The key takeaway: **--enable-preview** is always tied to the current JDK release. Enable the flag at both the compile and run steps, keep the same JDK version across the entire toolchain, and only use preview when the project accepts the possibility of future source code changes.