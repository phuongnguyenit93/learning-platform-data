# Declaring Supported Annotations, Options, and SourceVersion

When building an **annotation processor** in Java, writing code in the `process(...)` method is only part of the work. The `javac` compiler also needs to know: **which annotations** this processor cares about, which **`-A` configuration options** it accepts, and which **Java language version** it is designed to process. Those three groups of information are declared respectively using:

- `@SupportedAnnotationTypes` — declares the set of annotation names supported by the processor;
- `@SupportedOptions` — declares the set of option names the processor accepts from `javac -A...`;
- `@SupportedSourceVersion` — declares the highest `SourceVersion` the processor supports.

The three annotations above belong to the `javax.annotation.processing` package, while `SourceVersion` belongs to `javax.lang.model`. They are **metadata for the annotation processing tool**, not three annotations to attach to processed business classes.

This lesson uses **JDK 17+** and the `javac` compiler. The example builds a processor reading the `@Audited` annotation, taking the `-Aaudit.prefix=CHECK` option, emitting diagnostics during compilation, and then running a regular Java program. Beyond syntax, the key is how to declare metadata **accurately and completely** so the processor does not misclaim annotations, hide configuration errors, or promise support for untested source versions.

## 1. Where Does Annotation Processing Take Place?

Annotation processing is a **compile-time** extension mechanism. `javac` can load suitable processors, supply the source code's element/type model, and invoke processors via the `javax.annotation.processing.Processor` API.

A typical processor extends `AbstractProcessor`:

~~~java
public final class ExampleProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        return false;
    }
}
~~~

This is an **illustrative skeleton snippet**, not yet a standalone class: you must `import` the corresponding types and declare supported metadata. A complete runnable example is in section 3.

General mechanism:

~~~text
Annotated Java source
      |
      v
javac finds/loads the specified processor
      |
      +-- Processor.getSupportedAnnotationTypes()
      +-- Processor.getSupportedOptions()
      +-- Processor.getSupportedSourceVersion()
      |
      v
Round 1: process(annotations, roundEnv)
      |
      +-- can inspect elements
      +-- can emit WARNING / ERROR / NOTE messages
      +-- can create additional source/class/resource files
      |
      v
Next round if new source was created
      |
      v
Final round; javac continues/completes compilation
~~~

A processor is **not a program invoked directly with `java ProcessorClass`**. It is loaded and orchestrated by the compilation environment. A processor can inspect code structure, report compilation errors, or generate new source files, yet does not automatically replace running business tests.

### Who Provides the Three Pieces of Support Information?

`AbstractProcessor` has the corresponding methods:

| Processor Method | Commonly Used Declaration Annotation | Meaning |
| --- | --- | --- |
| `getSupportedAnnotationTypes()` | `@SupportedAnnotationTypes` | The annotation names the processor declares it supports |
| `getSupportedOptions()` | `@SupportedOptions` | The `-A` option **key names** the processor accepts |
| `getSupportedSourceVersion()` | `@SupportedSourceVersion` | The highest Java source version the processor declares it supports |

When using `AbstractProcessor`, annotations are the concise way to provide metadata for the corresponding default methods. You can also **override** these methods if a dynamic supported set is needed, but you must understand consistency and avoid declaring in one place while executing differently.

## 2. `@SupportedAnnotationTypes`: Selecting the Exact Annotations to Process

Example:

~~~java
@SupportedAnnotationTypes("demo.ann.Audited")
public final class AuditProcessor extends AbstractProcessor {
    // ...
}
~~~

The string is the **canonical name** of the supported annotation, including package and type name: `demo.ann.Audited`. Do not write `"Audited"` if the annotation actually resides in package `demo.ann` and you want the processor to support that type.

Multiple annotations:

~~~java
@SupportedAnnotationTypes({
    "demo.ann.Audited",
    "demo.ann.Tracked"
})
~~~

The second sample is **metadata illustration**, not yet a runnable processor because it lacks a complete class body. Both names must point to actual annotations that the processor knows how to handle.

Under `Processor`'s supported pattern mechanism, `"*"` is an expression covering **all annotation types**:

~~~java
@SupportedAnnotationTypes("*")
~~~

You should only use `"*"` when the processor genuinely has a broad observation/processing purpose. Declaring too broadly can cause the processor to be invoked in many unrelated cases and risks **claiming** annotations another processor needs to handle.

### “Supported” Does Not Mean “Every Class Gets Processed”

`javac` selects and invokes processors across processing rounds based on present annotations, declared supported annotation sets, and other processors. Inside `process`, you still need to retrieve the exact elements:

~~~java
for (Element element : roundEnv.getElementsAnnotatedWith(Audited.class)) {
    // Process element carrying @Audited.
}
~~~

This is an **illustrative snippet inside `process`**, not a standalone Java file.

If the processor declares support for `demo.ann.Audited` yet looks up an unrelated `@AnotherType`, the metadata and actual behavior do not match. The tooling does not infer intent inside the processor. Write metadata describing **the exact annotations your code processes**.

### Return Value of `process` Is Not a Success Status

`process(...)` returns a `boolean` indicating **whether the processor claims the annotations passed into the current processing round**:

- `return true;`: the processor declares it handles the assigned annotation types in that round; subsequent processors will normally no longer receive those same annotations in the same round.
- `return false;`: does not claim, allowing other processors to also examine the annotations according to the tool's dispatch mechanism.

This value is **not** the answer to “did compilation succeed” or “how many elements were found”. If you need to report an error, use `Messager.printMessage(Diagnostic.Kind.ERROR, ...)` so the compiler receives a diagnostic; do not expect `return false` by itself to fail the build.

## 3. Runnable Project: Annotation, Processor, and Application

We create three Java files, compile the **processor first**, and then use the processor to compile the application. This is a pure JDK 17+ example without Maven or external libraries.

Expected directory tree:

~~~text
processor-demo/
├── src/
│   ├── demo/
│   │   ├── ann/
│   │   │   └── Audited.java
│   │   └── proc/
│   │       └── AuditProcessor.java
│   └── ...
├── appsrc/
│   └── demo/
│       └── app/
│           └── Main.java
└── build/
    ├── processor/
    └── app/
~~~

All following commands run from the `processor-demo` root directory. On Linux/macOS, create the two output directories:

~~~sh
mkdir -p build/processor build/app
~~~

On Windows PowerShell, use an equivalent command:

~~~powershell
New-Item -ItemType Directory -Force build/processor, build/app | Out-Null
~~~

You can also let the IDE create the directories; there is no need to run both variants. Source files must be saved at the exact paths specified.

### 3.1. Declaring the Annotation Used by the Application

**`src/demo/ann/Audited.java`:**

~~~java
package demo.ann;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface Audited {
    String value();
}
~~~

`@Target(TYPE)` specifies that `@Audited` can be placed on type declarations such as classes. `@Retention(SOURCE)` states that this annotation is only needed in source code/compilation, and does not need to be retained in the classfile for runtime reflection to read. These two annotations belong to the **definition of the business annotation**, completely distinct from the three `@Supported...` annotations used to configure the processor.

The `value()` element gives the processor a descriptive label. The lesson does not use `RUNTIME` retention because the desired output is only a compile-time message, not metadata for the running application.

### 3.2. Writing the Processor and Declaring the Three Support Groups

**`src/demo/proc/AuditProcessor.java`:**

~~~java
package demo.proc;

import demo.ann.Audited;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedOptions;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("demo.ann.Audited")
@SupportedOptions("audit.prefix")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class AuditProcessor extends AbstractProcessor {

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        String prefix = processingEnv.getOptions()
                .getOrDefault("audit.prefix", "AUDIT");

        if (prefix == null || prefix.isBlank()) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR,
                    "audit.prefix phải có nội dung");
            return true;
        }

        for (Element element
                : roundEnv.getElementsAnnotatedWith(Audited.class)) {

            String label = element.getAnnotation(Audited.class).value();

            if (label.isBlank()) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@Audited.value không được rỗng",
                        element);
            } else {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.NOTE,
                        prefix + ": " + element.getSimpleName()
                                + " / " + label,
                        element);
            }
        }

        return true;
    }
}
~~~

Core points:

1. `@SupportedAnnotationTypes("demo.ann.Audited")` restricts the annotation types the processor accepts for processing.
2. `@SupportedOptions("audit.prefix")` declares that the processor understands the **key `audit.prefix`**.
3. `@SupportedSourceVersion(SourceVersion.RELEASE_17)` declares Java 17 source level.
4. `processingEnv.getOptions()` reads `-A` options passed by the tool to the processor; if the key is absent, the example defaults to `AUDIT`.
5. `roundEnv.getElementsAnnotatedWith(Audited.class)` retrieves only elements carrying `@Audited` in the current round.
6. `Messager` sends diagnostics to the compiler. `Kind.NOTE` is an informational note, while `Kind.ERROR` causes compilation to fail via the normal mechanism.
7. `return true` claims the annotations the processor received; it does not mean “the source code compiled successfully”.

The `if (roundEnv.processingOver())` section illustrates that the processor may be called again in the **final round**. In this example, no extra source files are generated, so there is no need to execute annotation-checking logic in the final round.

### 3.3. Writing the Application Using the Annotation

**`appsrc/demo/app/Main.java`:**

~~~java
package demo.app;

import demo.ann.Audited;

@Audited("entrypoint")
public final class Main {
    public static void main(String[] args) {
        System.out.println("Hello, processor");
    }
}
~~~

The application remains a regular Java class. The processor observes `@Audited` metadata during compilation; `Main.main` itself does not invoke the `process` method.

## 4. Compile the Processor Then Compile the Application

### Step 1: Compile the Annotation and Processor

~~~sh
javac --release 17 -encoding UTF-8 -d build/processor src/demo/ann/Audited.java src/demo/proc/AuditProcessor.java
~~~

This command creates the necessary classfiles under `build/processor`, for example:

~~~text
build/processor/
├── demo/ann/Audited.class
└── demo/proc/AuditProcessor.class
~~~

We compile the annotation and processor **in the same pass** so `AuditProcessor` can reference `Audited.class`. `--release 17` requests Java 17 source, bytecode, and platform API compatibility for this compilation. The JDK running the compiler must support `--release 17`.

### Step 2: Specify the Processor When Compiling the Application

~~~sh
javac --release 17 -encoding UTF-8 -cp build/processor -processorpath build/processor -processor demo.proc.AuditProcessor -Aaudit.prefix=CHECK -d build/app appsrc/demo/app/Main.java
~~~

Meaning of each group:

| Option | Meaning in the Example |
| --- | --- |
| `--release 17` | Compile application code at Java 17 compatibility level |
| `-cp build/processor` | Lets `Main.java` source find the `demo.ann.Audited` annotation |
| `-processorpath build/processor` | Lets the compiler find the processor class and dependencies when loading the processor |
| `-processor demo.proc.AuditProcessor` | **Explicitly selects** the processor to run |
| `-Aaudit.prefix=CHECK` | Passes option key `audit.prefix` with value `CHECK` |
| `-d build/app` | Output directory for `Main.class` |

Explicit `-processor` selection is important: the experiment **does not need** to set up a service provider file, nor depend on differing processor auto-discovery across JDK/build tool versions. Thus we can focus strictly on the three metadata mechanisms being studied.

When the processor encounters `@Audited("entrypoint")`, it sends a `NOTE` diagnostic for the element. The compiler may display a line containing content similar to:

~~~text
CHECK: Main / entrypoint
~~~

This is the **message content produced by the processor**, not a copy of the entire `javac` stdout/stderr. Depending on the JDK, caret position, source path, and prefix such as `Note:` may vary. The compiler usually outputs diagnostics to the tool's message stream; **do not treat NOTE as stdout from the application**.

### Step 3: Run the Application Class

~~~sh
java -cp build/app demo.app.Main
~~~

**Exact stdout:**

~~~text
Hello, processor
~~~

Here `-cp build/app` is sufficient to run the simple program, because `@Audited` has `SOURCE` retention and `Main`'s bytecode does not need the annotation API at runtime. In more complex applications, the runtime classpath must include all actually needed dependencies; `-processorpath` only serves loading processors at compile time.

### Experiment: Omitting the Option

Recompile the application omitting `-Aaudit.prefix=CHECK` while keeping the other options. The processor uses the default value `AUDIT` in the snippet:

~~~java
processingEnv.getOptions()
        .getOrDefault("audit.prefix", "AUDIT");
~~~

The message produced by the processor then is:

~~~text
AUDIT: Main / entrypoint
~~~

This proves `@SupportedOptions` does not automatically supply default values; **the default value is decided by the processor code itself**.

## 5. `@SupportedOptions` and `-A` Syntax

Annotation processing options take the form:

~~~text
-Akey
-Akey=value
~~~

Example:

~~~sh
javac -Aaudit.prefix=CHECK ...
~~~

The command line above is a **syntax illustration**, not a standalone command because of the ellipsis. Use the full command from section 4 to test.

Inside the processor:

~~~java
String value = processingEnv.getOptions().get("audit.prefix");
~~~

This is a **snippet placed inside the processor**, where `processingEnv` has been initialized by `AbstractProcessor`. If the user passes `-Aaudit.prefix=CHECK`, the value is `"CHECK"`; if omitted, `get` returns `null`. For an option having only a key without `=...`, the value represented by the tool may be `null`; when code needs a string, check explicitly.

This lesson's example uses:

~~~java
@SupportedOptions("audit.prefix")
~~~

It only declares the **key name** recognized by the processor; it does not automatically validate how long the value string is, whether it is business-valid, or whether it lies in an allowed set of values. Validation lives in `process` or `init` code written by the author.

### What Makes a Valid Option?

A good design needs to describe:

- **Key:** exact name such as `audit.prefix`, sensitive to spelling and dots.
- **Value type:** e.g., non-empty string or a value set `strict|lenient`.
- **Default value:** e.g., `AUDIT` when not provided.
- **Behavior on invalid input:** emit `ERROR`, do not guess.
- **Scope of impact:** only changes diagnostic prefix, does not control runtime code.

For enum-like options, use explicit validation and give clear messages rather than accepting arbitrary strings. For example, if a user passes `-Aaudit.prefix=`, `String.isBlank()` in the processor above leads to an `ERROR` diagnostic; the compiler will fail so the user fixes the configuration.

A typo key such as `-Aaudit.prefx=CHECK` is **not supported** by `@SupportedOptions("audit.prefix")`. `javac` may emit a message about an option not claimed by any processor; whether or not the tool warns, our processor **cannot read the value under the right key**, so it falls back to the `AUDIT` default. Check both compiler logs and output to catch key typos.

### Multiple Options

When a processor has multiple configurations, you can declare:

~~~java
@SupportedOptions({"audit.prefix", "audit.mode"})
~~~

and read:

~~~java
String prefix = processingEnv.getOptions().get("audit.prefix");
String mode = processingEnv.getOptions().get("audit.mode");
~~~

This is an **illustrative snippet**, not requiring adding `audit.mode` to the current runnable example. Publishing a key should only be done once the processor has code/contract handling that key. Avoid listing unused keys just to suppress “unrecognized processor option” warnings.

## 6. `@SupportedSourceVersion` and `SourceVersion`

`SourceVersion` is an enum in the `javax.lang.model` package, with constants like `RELEASE_8`, `RELEASE_11`, `RELEASE_17`, `RELEASE_21` depending on what the JDK provides. A processor written for JDK 17 can declare:

~~~java
@SupportedSourceVersion(SourceVersion.RELEASE_17)
~~~

This declares the **latest source version level supported by the processor**. It does not switch the JVM to Java 17 and does not mean the processor can only be used strictly with Java 17: for lower source levels within the tool's supported range, the processor may still run.

**Distinguishing two configurations:**

- `javac --release 17`: requests compiling source/bytecode and platform APIs according to Java 17.
- `@SupportedSourceVersion(RELEASE_17)`: the **processor's** metadata about the language level it understands.

When using a newer JDK compiler and compiling source at a version newer than 17, a processor declaring at most `RELEASE_17` may cause `javac` to emit a warning like “supported source version ... less than -source ...”. That warning reminds the processor author to **review and update compatibility commitments**, rather than simply bumping the number making the processor automatically understand all new language constructs.

### When Should `SourceVersion.latestSupported()` Be Used?

If the processor genuinely works well across multiple Java versions and is tested accordingly, the author can override:

~~~java
@Override
public SourceVersion getSupportedSourceVersion() {
    return SourceVersion.latestSupported();
}
~~~

This is an illustrative snippet in a processor class with `import javax.lang.model.SourceVersion;`. It retrieves the latest source version supported by **the JDK currently running the tool**. That avoids updating a fixed enum constant on every JDK upgrade, yet **is a broader support commitment** and requires appropriate tests.

Do not choose `latestSupported()` just to make warnings disappear: if the processor analyzes `Tree API`, expressions, syntax, or the type model under old assumptions, newer Java versions can break those assumptions. For processor libraries distributed to others, publish a list of supported JDKs/sources based on real testing.

Another fact: if a processor is **compiled into Java 21 bytecode**, a Java 17 JVM cannot load it simply because the code returns `RELEASE_17`. For a processor to run on JDK 17, the processor artifact itself must be compiled compatibly (e.g., `--release 17`) and must not use new runtime APIs absent from JDK 17.

## 7. Three Ways to Declare Metadata: Annotations, Overrides, Build Tools

### Annotations Are the Concisest Approach

In most static processors:

~~~java
@SupportedAnnotationTypes("demo.ann.Audited")
@SupportedOptions("audit.prefix")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class AuditProcessor extends AbstractProcessor {
    // ...
}
~~~

Metadata sits right on the class, easy to review alongside processing code. This is an **illustrative skeleton**, not replacing the complete class in section 3.

### Overriding for Dynamic Supported Sets

A processor can override three methods:

~~~java
@Override
public Set<String> getSupportedAnnotationTypes() {
    return Set.of("demo.ann.Audited");
}

@Override
public Set<String> getSupportedOptions() {
    return Set.of("audit.prefix");
}

@Override
public SourceVersion getSupportedSourceVersion() {
    return SourceVersion.RELEASE_17;
}
~~~

These are illustrative methods in a class extending `AbstractProcessor`, with `import java.util.Set;` and `import javax.lang.model.SourceVersion;`. If overriding, pick **a single source of truth** for metadata; avoid having annotations and methods return different sets that mislead maintainers.

### Compiler Configuration Does Not Replace Processor Metadata

Options `-A...`, `-processor`, and `-processorpath` are specified **when invoking `javac`**:

- `-Akey=value`: passes option data.
- `-processor fully.qualified.ProcessorName`: selects the processor to run.
- `-processorpath path`: where the compiler locates processors and dependencies when loading.
- `-proc:only`: runs only annotation processing without performing the normal compilation step into application classfiles.
- `-proc:none`: disables annotation processing.

Even if the build tool passes `-Aaudit.prefix=CHECK`, the processor must still declare `audit.prefix` as a supported option and explain how to process the value itself. Conversely, merely adding `@SupportedOptions` to the processor does not automatically add `-A...` to the build command.

Some build tools (Maven, Gradle, IDEs) help package/declare processors, yet **support metadata is the processor's contract**, while execution selection/options are the build invocation's responsibility.

## 8. Loading Processors: Explicit Selection and Auto-Discovery

The example uses `-processor demo.proc.AuditProcessor` to avoid relying on default discovery mechanisms. In real projects, a processor JAR can register via a service provider file:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

The file content is the processor class name:

~~~text
demo.proc.AuditProcessor
~~~

This is a **service provider configuration**, not a Java file and not part of the three `@Supported...` annotations. It can allow tools to discover the processor from an appropriately configured location on the processor path, depending on the policy of the `javac` version and build tool.

Do not assert that every new compiler/JDK version will **automatically scan the classpath and run every processor** merely because a JAR has a service file. Default annotation processing policies have changed across JDK versions; for reproducible workflows, **explicitly specify the processor or configure the processor path and processing mode** in the build.

Furthermore, when creating a processor JAR, package all dependent classes of the processor, not just the main class. In this lesson, `AuditProcessor` depends directly on `Audited.class`, so `build/processor` contains both. When loaded in a real environment, the compiler must find those classes on the processor loading path.

## 9. Processing Rounds and the Meaning of Support Selections

Annotation processing can have **multiple rounds**. If a processor generates valid additional source files, the compiler can feed the new files into the next round. Therefore:

- `roundEnv.getElementsAnnotatedWith(...)` returns matching elements in the **current round**, not necessarily the entire project in every round.
- `roundEnv.processingOver()` indicates the processing run is ending, suitable for certain final summary/diagnostic tasks.
- `roundEnv.errorRaised()` provides information about errors raised during prior processing; it should not be used to replace `Diagnostic.Kind.ERROR` for errors detected by the processor.
- `process` can be called multiple times; code needs to avoid creating duplicate files or repeating unwanted side effects.
- `getSupportedAnnotationTypes()` is information tools use to select/dispatch annotation types; it does not decide your round-processing logic for you.

If a processor handles multiple annotation types, process them appropriately and decide clearly when to claim. There is no need to `return true` if the processor only observes annotations and wants other processors to continue processing, though returning `false` also does not automatically guarantee every processor is called in every context. Read the specific contract of `Processor`.

### Avoiding Name Scope Errors

Suppose the annotation is in `com.company.audit.Audited` yet metadata states:

~~~java
@SupportedAnnotationTypes("demo.ann.Audited")
~~~

Then the application's annotation does not match the name the processor declared it supports; the processor may fail to receive the needed annotations, even though the code inside `process` is syntactically valid.

Do not use `"*"` to mask a name declaration bug. Fix the exact fully qualified name, verify the processor was loaded, use round diagnostic options if needed, and ensure the annotation is actually present in the source being compiled.

## 10. Typical Errors and How to Diagnose Them

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| No NOTE created by processor | Processor not selected/loaded, annotation name mismatch, or code skipped the round with the annotation | Check `-processor`, processor path, and `@SupportedAnnotationTypes` |
| `Annotation processor ... not found` | Processor class or dependency missing/wrong on processor path | Check paths and class files |
| Build runs but `-A...` has no effect | Misspelled key, option not read, or default took over | Check `@SupportedOptions` and `processingEnv.getOptions()` |
| Warning “option ... not recognized” | No processor claimed that key | Check exact key name and supported list |
| Warning “supported source version ... less than -source ...” | Processor declares support for an older source level than currently compiled | Evaluate compatibility and update `SourceVersion` with testing |
| `UnsupportedClassVersionError` when loading processor | Processor bytecode newer than JVM running the compiler | Compile processor with an appropriate target |
| `package demo.ann does not exist` when compiling app | Application compile classpath missing annotation class | Check `-cp build/processor` |
| Source created multiple times causing `FilerException` | Processor writes duplicate same path across multiple rounds | Manage processing rounds and generated file names |

To see more activity when the compiler runs processors, `javac` has useful diagnostic options:

~~~sh
javac -XprintRounds -XprintProcessorInfo --release 17 -encoding UTF-8 -cp build/processor -processorpath build/processor -processor demo.proc.AuditProcessor -Aaudit.prefix=CHECK -d build/app appsrc/demo/app/Main.java
~~~

The two flags `-XprintRounds` and `-XprintProcessorInfo` help print info about rounds and processors/annotations considered. Exact message formatting may differ across JDK releases; they are used to **investigate configuration**, not as a runtime application API.

### Trying Disabling Processing to Understand Boundaries

Keep the classpath for the annotation, yet add `-proc:none` and remove `-processor` selection from the compile command, for example:

~~~sh
javac --release 17 -encoding UTF-8 -cp build/processor -proc:none -d build/app appsrc/demo/app/Main.java
~~~

`Main.java` can still compile if the annotation class itself is available and the source code is valid; however, **AuditProcessor does not run**, so there will be no `CHECK: Main / entrypoint` NOTE. This proves **using an annotation in code** and **the tool actually running a processor** are two separate steps.

With `-proc:only`, the tool runs processors without generating application classfiles as in normal compilation. If you want to run `java demo.app.Main` afterward, you need a compilation pass producing the appropriate application classfiles.

## 11. Designing Maintainable Metadata

A quality processor doesn't just compile; it needs a clear and stable contract:

**For supported annotations:** choose qualified names, avoiding unnecessarily broad patterns. When adding a new annotation, update metadata, processing code, and tests together. If you want other processors to jointly process an annotation, explicitly design claiming with `process`.

**For options:** document keys, value types, defaults, validation conditions, and impact on output. Misconfigurations should produce clear messages; do not silently fall back if an error could make build outputs wrong. Do not put sensitive secrets into NOTE messages or generated sources just because an option can pass any string.

**For source version:** choose the level matching Java constructs the processor actually understands. When upgrading the JDK, run the test suite across published `--release`/`-source` versions; do not bump the constant just to silence warnings.

**For reproducible builds:** separate the processor artifact from the application, define classpath/processor path clearly, choose explicit processors or proper service registration, and ensure builds do not accidentally use an old processor.

**For diagnostics:** use `Messager` with `ERROR` for invalid conditions, `WARNING` when there are notable risks, and `NOTE` for brief necessary information. Avoid flooding NOTEs every round or printing sensitive option data to CI logs.

A review process can directly inspect the three methods:

~~~java
getSupportedAnnotationTypes()
getSupportedOptions()
getSupportedSourceVersion()
~~~

and compare them against actual behavior in `process(...)`. This is how discrepancies between “what the processor advertises” and “what the processor does” are caught.

## 12. Practice Exercises

**Exercise 1 — Omit the option.** Compile the application with `-processor demo.proc.AuditProcessor` but omit `-Aaudit.prefix=CHECK`. Explain why the NOTE uses the default `AUDIT` prefix, and why `@SupportedOptions` does not supply defaults itself.

**Exercise 2 — Misspelled key.** Replace `-Aaudit.prefix=CHECK` with `-Aaudit.prefx=CHECK`. Observe the compiler log and processor message. Distinguish “option declared as supported” from “actual value retrieved from map”.

**Exercise 3 — Annotation name mismatch.** In a test copy, change `@SupportedAnnotationTypes("demo.ann.Audited")` metadata to another name and recompile the processor. Predict why `@Audited` elements are no longer received by the processor as before. Fix the qualified name back.

**Exercise 4 — Invalid annotation data.** Replace `@Audited("entrypoint")` with `@Audited("")`. The processor emits an `ERROR` diagnostic on the element; explain why `return true` does not turn that error into success.

**Exercise 5 — SourceVersion.** Use a JDK supporting Java newer than 17 and compile the application at a source level higher than 17. Observe the source version warning if emitted by the compiler; distinguish bumping `SourceVersion` from changing `--release` and running compatibility tests.

**Exercise 6 — Disable processing.** Run `-proc:none` as in section 10. Why can the annotation still exist in source while the processor produces no NOTE? When is `-proc:only` useful?

**Exercise 7 — Design a second option.** Suppose we want to support `-Aaudit.mode=strict`. Identify changes in `@SupportedOptions`, how to read `getOptions()`, valid values, and the message when users pass an invalid `audit.mode`.

### Self-Assessment

1. **What is `@SupportedAnnotationTypes` used for?** — Declares the set of annotation type names the processor supports; normally uses fully qualified names.
2. **Should `"*"` be the default?** — No; it is too broad unless the processor genuinely has a comprehensive processing purpose.
3. **Does `@SupportedOptions` store option values?** — No; it declares keys; values are read from `processingEnv.getOptions()`.
4. **Where does `-Aaudit.prefix=CHECK` take effect?** — When `javac` runs annotation processing, not when the JVM runs the application.
5. **Does `@SupportedSourceVersion(RELEASE_17)` force the JVM to use Java 17?** — No; it is the processor's source-level support declaration.
6. **Difference between `--release 17` and `RELEASE_17` in the annotation?** — The former configures the compilation target; the latter is the processor's source-handling capability metadata.
7. **Does `process` returning `true` mean the build succeeded?** — No; it means claiming the supplied annotation types.
8. **When to use `Messager.ERROR`?** — When detecting an invalid condition that must fail compilation, such as an invalid annotation value.
9. **Why does the example have both `-cp` and `-processorpath`?** — One lets application code see the annotation class, the other lets the compiler load the processor and its dependencies.
10. **When changing to a new JDK, should SourceVersion be bumped automatically?** — Only after verifying the processor understands the new Java source and model properly.
11. **Why not rely solely on processor auto-discovery?** — Because behavior and build/JDK configurations can differ; explicit selection makes the example reproducible.

**Connecting the concepts:** A reliable annotation processor needs to **accurately declare its annotation scope**, **clearly define its option contract**, and **publish a verified Java source level**. Those three pieces of metadata connect directly to `javac` configuration and the annotation processing loop; understanding them helps you distinguish errors where a processor did not run, received the wrong option, or was source-version incompatible — instead of blindly guessing in application code.
