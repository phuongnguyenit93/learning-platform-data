# Declaring Supported Annotation Types, Options, and Source Version When Writing an Annotation Processor (Java 17+)

An **annotation processor** is a program that runs during **Java compilation** to inspect declarations along with their annotations and perform tasks such as convention checks, reporting errors via compiler diagnostics, or generating source/resource files. So that the compiler knows **which annotation types** a processor handles, **which options** it understands, and **which Java syntax version** it supports, Java provides three standard meta-annotations in the `javax.annotation.processing` package:

~~~java
@SupportedAnnotationTypes("demo.DemoMark")
@SupportedOptions("message")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class DemoProcessor extends AbstractProcessor {
    // Implement process(...) to handle compilation rounds.
}
~~~

The snippet above is a **condensed template**, not a standalone runnable file. This lesson covers the full meaning, limitations, interaction with `javac`, how to retrieve options, the difference between annotations on the **processor class** and annotations on the **target source code**, along with a verified Java 17 example.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish the **annotation type to be processed** from the **processor class that performs the processing**.
- Properly use `@SupportedAnnotationTypes` to declare the fully qualified names of the annotation types recognized by the processor.
- Use `@SupportedOptions` to register configuration keys, pass them using the `javac -Akey=value` syntax, and read them via `ProcessingEnvironment.getOptions()`.
- Use `@SupportedSourceVersion` with `SourceVersion.RELEASE_17`; distinguish the **source version being compiled** from the JDK version running the processor.
- Understand how `AbstractProcessor` provides `getSupportedAnnotationTypes()`, `getSupportedOptions()`, and `getSupportedSourceVersion()` from the meta-annotations above.
- Create, compile, and run a Java 17+ processor; verify standard output (stdout) from the processor via `javac`.
- Recognize processor selection via `-processor`, classpath/processorpath, `META-INF/services` registration capability, and processing rounds.
- Avoid mistakes such as wrong annotation names, incorrect options, missing supported versions, or confusing compile-time mechanisms with runtime Reflection.

## 2. Getting the Three Conceptual Layers Right

Consider a scenario where you create an `@DemoMark` annotation to mark classes that need to be checked at compile time. There are three distinct entities:

1. **Annotation type:** `demo.DemoMark` declared with `public @interface DemoMark`. Project code uses `@DemoMark` on classes.
2. **Processor:** `demo.DemoProcessor` is a **Java class** implementing the `javax.annotation.processing.Processor` contract, typically by extending `AbstractProcessor`. It receives information from the compiler and processes the marked elements.
3. **Processor configuration meta-annotations:** `@SupportedAnnotationTypes`, `@SupportedOptions`, and `@SupportedSourceVersion` are placed on the **processor class**, not on the classes that the processor intends to check.

Model:

~~~text
src/demo/DemoMark.java
        |
        |  declares @interface DemoMark
        v
src/demo/Example.java: @DemoMark on class
        |
        |  javac --release 17 -processor demo.DemoProcessor
        v
src/demo/DemoProcessor.java (pre-compiled)
        |
        +--> @SupportedAnnotationTypes("demo.DemoMark")
        +--> @SupportedOptions("message")
        +--> @SupportedSourceVersion(RELEASE_17)
        |
        +--> process(annotations, roundEnv)
                |
                +--> reads -Amessage=hello from processingEnv
                +--> finds classes annotated with @DemoMark
                +--> checks / reports diagnostics / generates code if needed
~~~

**Important:** `@SupportedAnnotationTypes` is not placed on `@interface DemoMark` to make it process itself. The processor still needs to be compiled, selected/discovered by the compiler, and have `process(...)` execution code.

## 3. `@SupportedAnnotationTypes` — Declaring Processed Annotation Types

Typical declaration:

~~~java
import javax.annotation.processing.SupportedAnnotationTypes;

@SupportedAnnotationTypes("demo.DemoMark")
public class DemoProcessor extends AbstractProcessor {
    // ...
}
~~~

Usage:

- The annotation value is `String[]`: you can pass **a single name** as in the example or multiple names `{"demo.DemoMark", "demo.Check"}`.
- Use the **canonical name with its package** for the annotation type, for example `demo.DemoMark`. Only write `"DemoMark"` when the type is in the unnamed package; in real projects, you should define a package and use the exact name.
- This is an **annotation name filter**, not a list of source class names, not the processor name, and not a list of source packages to scan.
- `"*"` is a pattern indicating support for all annotation types; there are also namespace-based patterns for annotation names. Use wildcards carefully, as accepting too many types can cause out-of-scope processing.
- In the case of the module system, name resolution may consider module-qualified names according to the annotation processing API rules; the Java 17 example below intentionally uses a regular package and simple fully qualified names.

The information is advertised via:

~~~java
Set<String> supported = processor.getSupportedAnnotationTypes();
~~~

If you extend `AbstractProcessor` and do not override the method, the default implementation can read the information from `@SupportedAnnotationTypes` on the processor class.

**Consequences of an incorrect name:** For example, if a project has the annotation `demo.DemoMark` but you declare `@SupportedAnnotationTypes("DemoMark")`, the processor may not be invoked as expected for that annotation. Check the package, casing, and identifier of the annotation type.

### Multiple Annotation Types

~~~java
@SupportedAnnotationTypes({
    "demo.DemoMark",
    "demo.CompileCheck"
})
class MultiProcessor extends AbstractProcessor {
    // ...
}
~~~

This is an example of **supported metadata**, not a complete processor: the class above still requires a `process(...)` method to validly extend `AbstractProcessor` in a real program.

### Returning `true`/`false` from `process(...)`

The processor signature:

~~~java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {
    // ...
    return true;
}
~~~

A `true` value means the processor **claims** the annotation types belonging to the processing round it received, according to the rules of the annotation processing system; other processors will no longer be invited to process those claimed annotation types in that same dispatch. `false` means it does not claim them. This does **not** mean the compiler immediately halts all processing rounds, does not mean the target code runs itself, and does not prove that the processor succeeded in generating files.

If you declare `@SupportedAnnotationTypes("*")` and always `return true`, be aware of the impact on other processors. When designing a library, it is usually best to register only the annotation types you actually process rather than unnecessarily taking over everything.

## 4. `@SupportedOptions` — Declaring Supported Option Keys

A processor may have configuration settings such as enabling strict mode, choosing an output file name, or setting a prefix. Instead of hard-coding them, the user passes options at compile time.

Declaration:

~~~java
import javax.annotation.processing.SupportedOptions;

@SupportedOptions({"message", "strict"})
class ConfiguredProcessor extends AbstractProcessor {
    // ...
}
~~~

Rules:

- In `@SupportedOptions`, declare the **key names**, such as `"message"` or `"strict"`; do **not** include the `-A` prefix.
- On the command line, pass `-Amessage=hello` or `-Astrict=true` to `javac`. `-Akey=value` is an option **for annotation processors**, unlike `-Dkey=value` which is for Java system properties.
- The processor reads the key–value map via `processingEnv.getOptions()`. Typically, you use `get("message")` or check `containsKey("strict")`.
- When an option is not passed, looking up that key may return `null`. Provide defaults in the processor's logic if needed.
- `@SupportedOptions` **only advertises the keys the processor understands**; it does not automatically parse numbers, cast booleans, apply defaults, or validate values. Your `process(...)` or initialization code itself must perform validation.
- The compiler may warn about `-A...` options not recognized by any processor. Therefore, you should publish the exact names of the options actually handled and use them consistently.

Example of reading options:

~~~java
String message = processingEnv.getOptions()
        .getOrDefault("message", "default");
boolean strict = Boolean.parseBoolean(
        processingEnv.getOptions().getOrDefault("strict", "false"));
~~~

This snippet illustrates code **inside an already initialized processor**. If you need to ensure `strict` only accepts `true`/`false`, validate the string manually; `Boolean.parseBoolean("unexpected")` returns `false` instead of throwing an error, easily hiding typos in configuration.

### Namespaced Options

A processor can define structured keys, such as `demo.mode`, then pass `-Ademo.mode=fast` and read `get("demo.mode")`. Using a consistent namespace is especially useful when a build has multiple processors, preventing two libraries from accidentally using the same key.

`-A...` options do not determine which processors are loaded. They only supply options to the processors selected by the compiler; to specifically select a processor, use `-processor` or an appropriate discovery approach.

## 5. `@SupportedSourceVersion` — Supported Java Language Version

Example:

~~~java
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;

@SupportedSourceVersion(SourceVersion.RELEASE_17)
class Java17Processor extends AbstractProcessor {
    // ...
}
~~~

`SourceVersion` is located in the `javax.lang.model` package. `RELEASE_17` is the enum constant corresponding to the Java 17 source version. Related API method:

~~~java
SourceVersion sourceVersion = processor.getSupportedSourceVersion();
~~~

This value states **up to which Java source language/construct version the processor declares support**. It does **not** mean:

- The processor automatically compiles source into Java 17 bytecode.
- The processor forces the current JVM to be JDK 17.
- The processor sets the version of the annotation type or library.
- The compiler ignores the `--release`/`-source` option of the compile command.
- Any new features after Java 17 are supported by the processor simply because the running JDK is a newer version.

In the main example, we use **`javac --release 17`**. This instructs the compiler to compile targeting release 17; both standard Java APIs and class file output are constrained appropriately by that option. `@SupportedSourceVersion(RELEASE_17)` describes the level self-declared by the processor and does not replace `--release 17`.

When compiling with a newer JDK using `--release 21` while the processor only advertises `RELEASE_17`, the compiler may issue a warning that the processor's supported source version is lower than the source version being used. Choose a clear upgrade policy: test the processor with the new Java version and update support once verified.

### Should You Use a Fixed Version?

Use `@SupportedSourceVersion(SourceVersion.RELEASE_17)` when you want to declare a specific, tested support level. If it is genuinely compatible with newer versions and you want to evaluate based on the current compiler, you can **override** `getSupportedSourceVersion()`, for example:

~~~java
@Override
public SourceVersion getSupportedSourceVersion() {
    return SourceVersion.latestSupported();
}
~~~

This is an advanced design choice. `latestSupported()` does not prove your processor code properly handles all new source features; real testing is needed. If you override this method, the overridden method's result becomes the API answer instead of `AbstractProcessor`'s default based on `@SupportedSourceVersion`.

## 6. Complete Java 17+ Example: A Processor Reading All Three Configurations

This practical example uses **three Java files** in the same `demo` package and a `build` output directory. The processor is compiled first; then `javac` loads it to process the target file. This approach does not require setting up the ServiceLoader mechanism because we explicitly specify the processor with `-processor`.

### 6.1. `src/demo/DemoMark.java` — Defining the Target Annotation

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface DemoMark {}
~~~

`DemoMark` only marks type declarations; `SOURCE` retention is already **sufficient** for an annotation processor at compile time. `RUNTIME` is not needed for `javac` to pass this annotation to the processor.

### 6.2. `src/demo/DemoProcessor.java` — Declaring the Processor

~~~java
package demo;

import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedOptions;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;

@SupportedAnnotationTypes("demo.DemoMark")
@SupportedOptions("message")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class DemoProcessor extends AbstractProcessor {

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        int count =
                roundEnv.getElementsAnnotatedWith(DemoMark.class).size();

        if (count > 0) {
            System.out.println("types="
                    + String.join(",", getSupportedAnnotationTypes()));
            System.out.println("options="
                    + String.join(",", getSupportedOptions()));
            System.out.println("version=" + getSupportedSourceVersion());
            System.out.println("message="
                    + processingEnv.getOptions().get("message"));
            System.out.println("marked=" + count);
        }

        return true;
    }
}
~~~

Key highlights:

- The class extends `AbstractProcessor`, so it is provided with `ProcessingEnvironment` when the compiler instantiates the processor and calls `init(...)` per the API contract.
- `getSupportedAnnotationTypes()`, `getSupportedOptions()`, and `getSupportedSourceVersion()` are implemented by `AbstractProcessor` based on the three annotations declared on `DemoProcessor`.
- `roundEnv.getElementsAnnotatedWith(DemoMark.class)` returns the elements annotated with `@DemoMark` in the current processing round; in the demo there is one class.
- `roundEnv.processingOver()` is used to detect the final round, where no new code should continue to be generated; the demo skips printing in the final round to keep stdout stable.
- `count > 0` avoids printing the summary during compiler rounds that have no matching elements.
- The code chooses `System.out.println(...)` **solely so the lesson has verifiable stdout**. Production processors typically use `processingEnv.getMessager().printMessage(Diagnostic.Kind.NOTE, ...)` for informational messages or `ERROR` when violations are detected, because diagnostics integrate better with the compiler.
- `return true` notifies that the processor has claimed the processed annotation types in the round per the API rules; it is not returning a `true`/`false` result from a single validation check.

### 6.3. `src/demo/Example.java` — The Code Being Processed

~~~java
package demo;

@DemoMark
public class Example {}
~~~

This is the target source class; no `main` is needed. The processor reads this class during `javac` compilation, not via `java Example`.

### 6.4. Compiling and Triggering the Processor

From the **parent directory of `src`**, run in order:

~~~bash
javac --release 17 -d build src/demo/DemoMark.java src/demo/DemoProcessor.java

javac --release 17 \
  -cp build \
  -processorpath build \
  -processor demo.DemoProcessor \
  -Amessage=hello \
  -d build \
  src/demo/Example.java
~~~

The `\` symbol is used for command line continuation in **Bash/POSIX shells**. On Windows PowerShell, write the entire second command on a single line (or use PowerShell's line-continuation syntax), for example:

~~~powershell
javac --release 17 -cp build -processorpath build -processor demo.DemoProcessor -Amessage=hello -d build src/demo/Example.java
~~~

Explanation:

- The first step creates `build/demo/DemoMark.class` and `build/demo/DemoProcessor.class`. If the `build` directory does not exist yet, `javac -d build` may require you to create the directory first in some environments; the safest approach is to create `build` before running.
- `-cp build` makes `DemoMark` and dependent classes available for compiling `Example`.
- `-processorpath build` points to where the compiler looks for annotation processor classes. Real projects typically use a processor JAR located on a separate processor path.
- `-processor demo.DemoProcessor` **specifies the processor by its full name**, without relying on auto-discovery.
- `-Amessage=hello` supplies the `message` option with the value `hello`.
- `--release 17` keeps the example at Java 17; a JDK 17 or newer compiler needs to support this release.
- `-d build` is the destination directory for the class files compiled from the target source code.

**Stdout of the second `javac` step:**

~~~text
types=demo.DemoMark
options=message
version=RELEASE_17
message=hello
marked=1
~~~

The lines above were verified using `javac --release 17` on a JDK that supports release 17. Normally, the compiler does not add other lines if there are no warnings/errors; when an IDE or build tool wraps the compiler, the UI displaying diagnostics/stdout may differ.

**Line-by-line explanation:**

1. `types=demo.DemoMark` confirms that the processor advertises support for `demo.DemoMark`.
2. `options=message` confirms that `@SupportedOptions` registers the `message` key.
3. `version=RELEASE_17` is the `SourceVersion` value declared by the processor.
4. `message=hello` confirms that `processingEnv.getOptions().get("message")` accurately reads the passed option.
5. `marked=1` confirms that `RoundEnvironment` sees one `@DemoMark` declaration in the relevant round.

If you omit `-Amessage=hello`, the `message=...` line may print `null` because the demo processor has no fallback; in real code, you should handle missing options.

## 7. Processors Operate Across Processing Rounds

Annotation processing is not a single callback for the entire project. The compiler may organize **multiple rounds**, especially when a processor generates new source files via `Filer`. Each `process(...)` round is provided with:

- `Set<? extends TypeElement> annotations`: the annotation types provided to the processor in the round.
- `RoundEnvironment roundEnv`: the environment for querying the elements participating in the current round and the processing round state.
- `roundEnv.getElementsAnnotatedWith(...)` to find the elements carrying the annotation type under consideration.
- `roundEnv.processingOver()` to determine whether it is the final round, when no new rounds will arise from newly generated source files.

In the example, the processor **does not generate new files**, so there is one round containing `Example` and a final round. The code intentionally does not print when `processingOver()` is `true`; this is a way to keep stdout predictable for teaching purposes.

`getSupportedAnnotationTypes()` describes **which annotation types** a processor can handle; it does not guarantee that every round will have an element annotated with that annotation. Therefore, `count` can be 0, especially when the compiler processes multiple rounds or multiple source files. You should not throw an error simply because a round lacks an annotation type supported by the processor.

## 8. How Is a Processor Selected or Discovered?

The three `@Supported...` annotations **describe** a processor; they **do not automatically register** it for every `javac` run. The compiler must be able to locate the processor:

**Approach 1 — explicit specification**, suitable for hands-on exercises:

~~~bash
javac -processor demo.DemoProcessor -processorpath build -cp build src/demo/Example.java
~~~

This approach can be combined with `--release 17`, `-Amessage=hello`, and `-d build` as in the main example. Its advantage is easy control over which processor is executed, without depending on ServiceLoader entries.

**Approach 2 — service provider registration** in a JAR or classpath that the compiler uses to discover processors:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

The content of the service file is the fully qualified processor class name, for example:

~~~text
demo.DemoProcessor
~~~

This is the **service file content**, not a Bash command and not Java code. When the processor is present on the right search path and the compiler environment enables/allows annotation processing, the service discovery mechanism can load the processor. When packaging a JAR, you must preserve the `META-INF/services/...` path. With modern JDKs and build configurations, the default annotation processing policy may differ, so production builds must explicitly declare the processor path/processing configuration rather than assuming the compiler will always run processors automatically.

**Do not put** the annotation class name `demo.DemoMark` in the service file; the service requires an implementation of `javax.annotation.processing.Processor` such as `demo.DemoProcessor`.

**Approach 3 — programmatic compilation API**: `JavaCompiler` and tooling can configure processors programmatically, though that is an advanced topic. In this lesson, using the `javac` command line is sufficient to illustrate the mechanism clearly.

### `-proc:only` and `-proc:none`

- `-proc:only` requests running annotation processing **without continuing to the normal compilation phase to produce class files from the target sources**, which is suitable for testing processors or generating sources.
- `-proc:none` disables annotation processing during compilation.
- To explicitly request processing, you can use `-processor` as in the hands-on example; when experimenting with newer JDKs, do not simply expect that "having a processor JAR means the compiler runs it automatically."

Note that `-proc:only` does not enable processing with a processor that has not yet been compiled or validly loaded. `DemoProcessor` must still already be present on `-processorpath`.

## 9. Registration via Annotations and Overriding Methods

`AbstractProcessor` reads the standard annotations to fulfill the methods of the `Processor` interface. Three pairs to remember:

| Meta-annotation on the processor class | Corresponding method | Data type |
| --- | --- | --- |
| `@SupportedAnnotationTypes({...})` | `getSupportedAnnotationTypes()` | `Set<String>` |
| `@SupportedOptions({...})` | `getSupportedOptions()` | `Set<String>` |
| `@SupportedSourceVersion(SourceVersion.RELEASE_17)` | `getSupportedSourceVersion()` | `SourceVersion` |

If an implementation **overrides** these methods, the compiler will use the values returned by the overridden methods. For example, a set of annotation types determined by processor code can be supported:

~~~java
@Override
public Set<String> getSupportedAnnotationTypes() {
    return Set.of("demo.DemoMark", "demo.CompileCheck");
}
~~~

This is an illustrative snippet inside a processor body and requires `import java.util.Set;`. At an advanced level, an overridden method may also depend on compiler state per the API contract, but you must avoid assuming `processingEnv` has been initialized at all times if the method is queried before/outside the corresponding initialization sequence.

For an introductory lesson, **prefer the three static declaration annotations**: they are easy to read, easy to verify, and clearly demonstrate the purpose of standard metadata.

Do not confuse `@SupportedAnnotationTypes` with `@Target`. `@Target` applies to the annotation type you define yourself—for example, `@DemoMark` can only be placed on `TYPE`—whereas `@SupportedAnnotationTypes` advertises the ability to recognize an annotation type **on the processor side**. Likewise, `@Retention(SOURCE)` on `DemoMark` does not replace `@SupportedSourceVersion` on the processor: one governs **annotation retention duration**, while the other declares the **supported source version**.

## 10. Common Mistakes and How to Self-Check

**1. Wrong package name in `@SupportedAnnotationTypes`.** If you use `"DemoMark"` when the actual type is `demo.DemoMark`, the processor will not match the annotation properly. Print `getSupportedAnnotationTypes()` and verify the fully qualified name.

**2. Placing `@SupportedAnnotationTypes` on the annotation type instead of the processor class.** This meta-annotation configures the processor implementation; the target annotation type only needs to declare its appropriate `@Target` and `@Retention` meta-annotations.

**3. Forgetting to declare `@SupportedOptions` while passing `-Amessage=hello`.** The compiler may warn that the option is not recognized by any processor. Register `"message"` on the processor, do not write `"-Amessage"`.

**4. Assuming `@SupportedOptions` automatically validates values.** Advertising a key does not guarantee `message` is non-empty or `strict` is a valid boolean. Validate values yourself from `processingEnv.getOptions()` and report clear errors on misconfiguration.

**5. Confusing `-A` with `-D`.** `-Aname=value` passes data into the annotation processing environment; `-Dname=value` is a Java system property for the corresponding JVM process. These two channels are not automatically exchanged.

**6. Confusing `@SupportedSourceVersion(RELEASE_17)` with `--release 17`.** The meta-annotation declares the processor's support; the command-line `--release` controls the compilation target/source API. Use both in their proper roles when testing.

**7. Compiling target sources before the processor is available.** You need to build the processor JAR/classes first, configure classpath/processorpath, and then compile the sources to be processed. For the demo, use two separate `javac` commands.

**8. Confusing classpath with processorpath.** Classpath helps the compiler resolve types used in the source; processor path is where the compiler loads processors from. The demo sets `build` for both because it holds both `DemoMark` and `DemoProcessor`, whereas larger projects may separate the artifacts.

**9. Thinking `RUNTIME` retention is required for a compile-time processor to read an annotation.** Annotations with `SOURCE` retention are still received by processors when the compiler parses source code; the `@DemoMark` example demonstrates this directly.

**10. Assuming a processor will always run whenever a processor class exists.** False: annotation processing configuration and a selection/discovery mechanism are required. `-processor demo.DemoProcessor` helps verify this explicitly.

**11. Printing on every processing round and thinking the processor is being called erroneously.** Annotation processing has multiple rounds; when single output is needed, check `processingOver()` or manage state appropriately, and avoid assuming `process` is invoked only once.

**12. Failing to distinguish `return true` from `return false`.** This is a decision to claim the annotation types in the processing round, not the compiler's success status or the annotation's value.

**13. Indiscriminately declaring the `"*"` wildcard.** A processor may receive more than intended, especially if it always claims annotation types. Restrict to the exact packages/types whenever possible and write integration tests alongside other processors.

**14. Keeping `RELEASE_17` fixed without testing when upgrading the Java source version.** When the compiler targets a newer release, the processor may emit warnings or encounter new language constructs that its processing code does not yet support. Test, adjust the support level, and avoid declaring `latestSupported()` without verification.

**15. Using `System.out` as a production error reporting channel.** The lesson code uses stdout for easy verification; real processors should prefer `Messager` for diagnostics, especially `Diagnostic.Kind.ERROR` when you want the compiler to report an error.

## 11. Practice Exercises in Increasing Order of Difficulty

1. Run the three files `DemoMark`, `DemoProcessor`, and `Example` exactly as in the example. Explain each line of stdout and state which annotation type the processor receives.
2. Change `-Amessage=hello` to `-Amessage=team`. Verify that the `message=team` line changes while the supported types and source version remain unchanged.
3. Omit `-Amessage`. Observe the value read in the demo and add default fallback logic so that `null` is not printed.
4. Add the `strict` option to `@SupportedOptions({"message", "strict"})`. Pass `-Astrict=true`; write a check that accepts only `true` and `false`, and use `Messager` to report an error on invalid input.
5. Create an additional `@interface CompileCheck` in package `demo` and set `@SupportedAnnotationTypes({"demo.DemoMark", "demo.CompileCheck"})`. Verify that the processor receives both types and adjust the `process` logic to count each type separately.
6. Remove `@DemoMark` from `Example` and compile. Check whether the processor is still invoked under the configuration used and why `count > 0` helps prevent irrelevant output.
7. Change the annotation target of `DemoMark` from `TYPE` to `METHOD`; try applying it to a class to observe the compiler error and distinguish it from the `@SupportedAnnotationTypes` filter.
8. Replace `@Retention(SOURCE)` with `CLASS` or `RUNTIME` for `DemoMark`. Explain why compile-time processing can still see the annotation in all three cases when the source code is compiled.
9. Run `javac --release 17 -proc:only ...` to observe running processing only; then try `-proc:none` and inspect the difference. Always keep the processor pre-compiled and compiler options consistent.
10. Replace `@SupportedSourceVersion(SourceVersion.RELEASE_17)` by overriding `getSupportedSourceVersion()` to return `SourceVersion.latestSupported()`. Compare the output on your current JDK and discuss the risks of declaring an untested version level.
11. Package the processor into a JAR and try registering `META-INF/services/javax.annotation.processing.Processor`. Compare automatic discovery with explicit `-processor` specification; inspect the policies of the JDK/build tool in use.
12. Write a validation processor for `@NonEmptyName` placed on a class; use `processingEnv.getMessager().printMessage(Diagnostic.Kind.ERROR, ..., element)` if the class name violates the rule, and demonstrate that `javac` reports an error even though the target program has not run.

## 12. Checklist Before Applying to a Project

| Question | What you should be able to answer |
| --- | --- |
| Is a processor a class or an annotation type? | It is a class implementing `Processor`, typically extending `AbstractProcessor` |
| Where are supported annotation types declared? | `@SupportedAnnotationTypes` on the processor |
| What is the typical value of `@SupportedAnnotationTypes`? | A fully qualified name such as `"demo.DemoMark"` |
| Where is the value for `@SupportedOptions("message")` read? | `processingEnv.getOptions().get("message")` |
| How are command-line options passed? | `javac -Amessage=hello` |
| How does a processor declare its supported source version? | `@SupportedSourceVersion(SourceVersion.RELEASE_17)` or overriding the corresponding method |
| Is `--release 17` the same as `@SupportedSourceVersion`? | No; one controls the compiler target, while the other describes what the processor supports |
| Can `@Retention(SOURCE)` be used on the target annotation? | Yes, for compile-time annotation processing |
| How do you ensure the processor runs? | Configure the proper paths and `-processor` or a discovery mechanism |
| Can `process(...)` run multiple times? | Yes, across processing rounds |
| What does `return true` mean? | Claims the annotation types in the round according to the processing contract |

**Conclusion:** The three standard meta-annotations on a processor **declare the supported scope, configuration, and source version** so the compiler can coordinate processing. They do not replace compiling or registering the processor, do not automatically validate options, and do not determine the program's bytecode version. Once you clearly understand `@SupportedAnnotationTypes`, `@SupportedOptions`, and `@SupportedSourceVersion` along with how they interact with `AbstractProcessor`, `ProcessingEnvironment`, and `javac`, you have a solid foundation for developing practical Core Java annotation processors.

### References

- [Java SE 17 — SupportedAnnotationTypes](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/SupportedAnnotationTypes.html).
- [Java SE 17 — SupportedOptions](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/SupportedOptions.html).
- [Java SE 17 — SupportedSourceVersion](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/SupportedSourceVersion.html).
- [Java SE 17 — AbstractProcessor](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html).
- [Java SE 17 — Processor](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html).
- [Java SE 17 — ProcessingEnvironment](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/ProcessingEnvironment.html).
- [Java SE 17 — SourceVersion](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/SourceVersion.html).
- [Java SE 17 — javac options (`-A`, `-processor`, `-processorpath`, `--release`)](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html).
