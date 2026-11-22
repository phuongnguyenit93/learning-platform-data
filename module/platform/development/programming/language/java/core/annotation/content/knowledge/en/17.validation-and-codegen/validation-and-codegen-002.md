# Messager and Diagnostic.Kind: Reporting Errors, Warnings, and Information in Java Annotation Processing

When an **annotation processor** inspects configuration in source code, the most useful outcome is not to throw an exception and halt abruptly, but to **emit a compilation diagnostic**: a message with a clear severity level that describes the violation and, if possible, points to the exact declaration in the source file. Java provides two foundational APIs:

- `javax.annotation.processing.Messager` — the interface a processor uses to **send diagnostics** to the processing/compilation environment.
- `javax.tools.Diagnostic.Kind` — the enum describing the **severity level or kind of diagnostic**, specifically `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE`, and `OTHER`.

A short example located **inside an annotation processor**:

```java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "required field must have type String",
        fieldElement);
```

Here, `fieldElement` is a `javax.lang.model.element.Element` representing the field declaration being checked. `Messager` helps feed the error into the compiler system and points the message to the relevant element. **`ERROR` has the effect of causing compilation to fail**; `WARNING`/`NOTE` generally only report information without causing compilation to fail by default.

This lesson focuses on the standard semantics of each message level, how to obtain `Messager` from a processor, the overloads of `printMessage`, how to attach a source location, the impact on builds/CI, common mistakes, and a compilable Java 17 example to see the actual differences.

## 1. What is a Diagnostic and How Does It Relate to an Annotation Processor?

A **diagnostic** is a message emitted by a compilation tool to inform the programmer about the state of the source: errors, warnings, or information. `javac` emits core Java diagnostics on its own (type errors, syntax errors, unresolved members, etc.). An annotation processor can also add diagnostics **according to rules specific to an application or library**.

For example, the annotation:

```java
@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.FIELD)
@interface CheckedField {
    boolean required() default false;
}
```

does not by itself make `javac` require a field to have type `String`. To enforce the rule "a `@CheckedField(required=true)` field must have type `String`", a processor needs to:

1. Find the fields annotated with the corresponding annotation in the processing round.
2. Read the metadata and inspect the field type.
3. If invalid, send `Diagnostic.Kind.ERROR` via `Messager` so that compilation fails.
4. If not critical, it can send `WARNING`; if it only needs to record progress, it can send `NOTE`.

**Merely declaring an annotation does not create rules on its own**. `Messager` is the tool for *emitting messages*; the logic deciding "when to report, and what kind to report" is built by the processor code or another tool.

## 2. Obtaining Messager Properly

In `AbstractProcessor`, the inherited field `processingEnv` has type `ProcessingEnvironment`. It provides `Messager`:

```java
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.lang.model.element.TypeElement;
import java.util.Set;

public class ExampleProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment round) {

        var messager = processingEnv.getMessager();
        // messager.printMessage(...)
        return true;
    }
}
```

This is an **illustrative skeleton**, not yet a fully working processor: to run it with `javac`, you need to declare supported annotation types/source version, configure the processor on the command line or in a build tool, and provide relevant input. A complete example is in Section 5.

Commonly accompanying components:

| Component | Role |
|---|---|
| `AbstractProcessor` | Provides the lifecycle and `processingEnv` |
| `ProcessingEnvironment.getMessager()` | Obtains the object used to emit diagnostics |
| `RoundEnvironment.getElementsAnnotatedWith(...)` | Finds declarations annotated in the round |
| `Element` | Models a declaration site such as a class, method, field, or parameter |
| `AnnotationMirror` | Models an annotation present on an element |
| `AnnotationValue` | Models the value of an annotation element |
| `Diagnostic.Kind` | Categorizes ERROR/WARNING/NOTE, etc. |
| `Messager.printMessage(...)` | Emits a message with context, optionally including a source location |

`Messager` is neither `java.util.logging.Logger` nor `System.out.println`. It is designed for the **compilation diagnostic channel** that a compiler, IDE, or build tool can consume. The exact presentation (colors, paths, line/column numbers, error counts, etc.) may vary by tool.

## 3. Diagnostic.Kind: What Do the Severity Levels Mean?

Java SE 17 has the following enum constants:

| `Diagnostic.Kind` | Basic Meaning | Typical Effect with `javac` |
|---|---|---|
| `ERROR` | An **error** that prevents the compilation result from being considered successful | Compiler reports `error:`, non-zero exit code |
| `WARNING` | A warning about an issue worth noting, though not necessarily a Java error | Typically reports `warning:`; compilation can still succeed |
| `MANDATORY_WARNING` | A warning in the **mandatory-to-report** category, per the diagnostic contract | May be displayed as `warning:`, not necessarily differing from WARNING in string form |
| `NOTE` | Information or an advisory note, neither an error nor a warning | Typically reports `Note:` |
| `OTHER` | A diagnostic not belonging to the kinds above | General category; do not rely on a fixed presentation format |

### ERROR — Rejecting Invalid Input

```java
messager.printMessage(
        Diagnostic.Kind.ERROR,
        "Field is not a String",
        field);
```

Use when the processed source **violates a mandatory contract**: for example, an annotation is placed on a declaration not supported by the framework, duplicate value names prevent code generation, or an annotation parameter lacks a required condition. Although the compiler may continue invoking the processor in some steps to finish processing, **the compilation result is unsuccessful** because an error has been reported.

`ERROR` is not synonymous with an immediate `throw` of an exception in the `process` method. It is a diagnostic recorded by the compiler. Therefore, do not expect calling `printMessage(ERROR, ...)` to automatically exit the rest of `process`; if the data is invalid, the code must explicitly skip unsafe steps.

### WARNING — Issues That Should Be Fixed, but Compilation Can Continue

```java
messager.printMessage(
        Diagnostic.Kind.WARNING,
        "Provide a reason for this annotation",
        field);
```

Appropriate when a violation does not render the configuration meaningless, but could lead to hard-to-maintain code, usage of deprecated APIs, or unclear configuration. A compilation with warnings can still return exit code 0. However, if the project enables `-Werror`, warnings can cause compilation to fail even though the processor did not emit `ERROR` directly.

### MANDATORY_WARNING — Mandatory Warning

```java
messager.printMessage(
        Diagnostic.Kind.MANDATORY_WARNING,
        "Legacy declaration requires migration",
        field);
```

This kind is a **mandatory warning**, not "a priority level lower than ERROR but higher than WARNING" along some numerical scale. It has its own requirement regarding warning reporting; `javac` output in actual examples still displays `warning:`. To distinguish the meaning, you must look at the diagnostic kind that was passed, not just read a console line.

Not every business warning needs to be mandatory. Choose it deliberately; a discretionary warning from a processor can use regular `WARNING`.

### NOTE — Progress, Additional Information

```java
messager.printMessage(
        Diagnostic.Kind.NOTE,
        "Generated configuration source successfully",
        element);
```

Useful when you want the user to know how many declarations the processor has read or which artifacts were generated. Avoid emitting a NOTE for every trivial detail on large projects: the log can become overly long and obscure diagnostics that genuinely require action. NOTE does not mean "compilation has definitely succeeded"; it is merely information at the time it is emitted.

### OTHER — Not Belonging to the Four Common Groups

`OTHER` exists in `Diagnostic.Kind` to represent a diagnostic that does not fall under ERROR/WARNING/MANDATORY_WARNING/NOTE. For typical processor error reporting or notification tasks, the first four categories are the clearest choices. Do not assume an IDE or compiler will colorize or count `OTHER` the same way as `NOTE`; the tool consuming the diagnostic decides how this unspecialized category is presented.

## 4. The Four Overloads of Messager.printMessage

`Messager` defines the following invocation forms:

```java
printMessage(Diagnostic.Kind kind, CharSequence msg)

printMessage(Diagnostic.Kind kind, CharSequence msg,
             Element e)

printMessage(Diagnostic.Kind kind, CharSequence msg,
             Element e, AnnotationMirror a)

printMessage(Diagnostic.Kind kind, CharSequence msg,
             Element e, AnnotationMirror a, AnnotationValue v)
```

**1. Only kind + message**

```java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.NOTE,
        "Analyzing configuration...");
```

Not tied to a specific source location; the log may lack a specific path/file/line. Suitable for processor-wide messages or summary results.

**2. Adding Element**

```java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "Unsupported field type",
        fieldElement);
```

Attempts to attach the message to the **declaration** represented by `Element`, such as a field name. This is a very useful overload when you want the programmer to click on the error in an IDE and jump close to the place that needs fixing.

**3. Adding AnnotationMirror**

```java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "Unsupported annotation",
        fieldElement,
        annotationMirror);
```

Provides the context of **that specific annotation usage** on an element. Suitable when an element has multiple annotations and only one annotation causes the issue. You need to obtain the `AnnotationMirror` actually associated with `fieldElement`.

**4. Adding AnnotationValue**

```java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "This value must not be blank",
        fieldElement,
        annotationMirror,
        annotationValue);
```

Adds the context of **a specific annotation value**, such as the string `reason = ""`. If the compiler has the corresponding location, it can point directly to the value region causing the error.

Importantly, the overloads accepting `Element`/`AnnotationMirror`/`AnnotationValue` provide information so that **the tool attempts** to attach the right source location. The Javadoc does not guarantee that all compilers, IDEs, or every kind of element will print the exact same column position; for synthetic elements, metadata from binaries, or default values, coordinates may be less accurate. Therefore, you should test on your actual toolchain.

### How to Find AnnotationMirror and AnnotationValue

A processor can traverse the metadata:

```java
for (AnnotationMirror mirror : field.getAnnotationMirrors()) {
    if (!mirror.getAnnotationType().toString()
            .equals("org.example.CheckedField")) {
        continue;
    }
    for (var entry : mirror.getElementValues().entrySet()) {
        if (entry.getKey().getSimpleName().contentEquals("reason")) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR,
                    "Reason is invalid",
                    field,
                    mirror,
                    entry.getValue());
        }
    }
}
```

This is an **illustrative snippet inside a processor**: `field` is the `Element` of the annotated declaration, and `org.example.CheckedField` is the hypothetical fully qualified name of the annotation in the project. `getElementValues()` only includes elements written explicitly, and does not automatically list all `default` values. If you also want to inspect defaults, you can use `processingEnv.getElementUtils().getElementValuesWithDefaults(mirror)`.

If the author omits `reason` and uses the empty default value, you can **read the default value**, but there is no source location corresponding to a `reason = ...` pair because the user never wrote it. In that case, attach the error to the `AnnotationMirror` or `Element` rather than assuming you can always point to an exact `AnnotationValue` in source.

## 5. Complete Java 17+ Program: NOTE, WARNING, MANDATORY_WARNING, and ERROR

This experiment creates an annotation and a processor that automatically checks three conditions. We compile one valid input and one invalid input to observe both the **diagnostics** and the **exit code**.

Place the four files below in the **same empty directory**. The example intentionally uses the default package to keep the `javac` commands short; real-world projects should use named packages.

### File 1 — CheckedField.java

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.FIELD)
public @interface CheckedField {
    String reason() default "";
    boolean required() default false;
}
```

- `SOURCE` is sufficient for an annotation processor to read while compiling the Java file being processed.
- `FIELD` only allows placing the annotation on field declarations.
- `reason()` is an explanatory string; `required()` represents a business requirement in the example.

The `@CheckedField` definition itself **does not force a field to be a String**, nor does it require entering `reason` since both elements have default values. Those rules are implemented in the processor below.

### File 2 — FieldCheckProcessor.java

```java
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("CheckedField")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class FieldCheckProcessor extends AbstractProcessor {
    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment round) {
        for (Element field :
                round.getElementsAnnotatedWith(CheckedField.class)) {

            CheckedField config = field.getAnnotation(CheckedField.class);

            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.NOTE,
                    "checking field " + field.getSimpleName(),
                    field);

            if (config.reason().isBlank()) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.WARNING,
                        "document the reason",
                        field);
            }

            if (field.getSimpleName().toString().startsWith("legacy")) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.MANDATORY_WARNING,
                        "legacy field needs migration",
                        field);
            }

            if (config.required()
                    && !field.asType().toString()
                            .equals("java.lang.String")) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "required field must have type String",
                        field);
            }
        }
        return true;
    }
}
```

Steps:

1. `@SupportedAnnotationTypes("CheckedField")` informs that the processor supports this annotation. Since the example uses the default package, the simple name `CheckedField` is the valid type name; when moving to a package, use the corresponding **fully qualified name**.
2. `@SupportedSourceVersion(RELEASE_17)` indicates the source version level supported by the processor.
3. `getElementsAnnotatedWith(CheckedField.class)` retrieves the elements annotated with `@CheckedField` in the current round. `@Target(FIELD)` ensures our example only uses the annotation on fields.
4. `config.reason().isBlank()` emits `WARNING` when no explanation is provided; this is a choice of the processor, not a core Java rule.
5. A field name starting with `legacy` emits `MANDATORY_WARNING`; this is likewise just an illustrative rule.
6. A field marked `required=true` whose type is other than `java.lang.String` emits `ERROR`. The demo checks the type name via `TypeMirror.toString()` for simplicity. **In production processors**, you should use `Types.isSameType` and `Elements.getTypeElement(...)` to compare types instead of string comparison, because generics, aliases, declared/error types, and complex configurations are not handled properly using `toString()` alone.
7. `return true` means the processor declares that it has processed (*claims*) the annotation types assigned to it in the round. It does **not** make the compiler succeed if there is an `ERROR`, nor does it substitute for halting processing on error branches.

### File 3 — ValidData.java

```java
class ValidData {
    @CheckedField(reason = "identifier", required = true)
    String id;

    @CheckedField
    int count;

    @CheckedField(reason = "backward compatibility")
    String legacyCode;
}
```

`id` is valid, having a reason and properly typed as String when required. `count` has no reason so it only produces a warning. `legacyCode` produces a mandatory warning due to the field naming rule.

### File 4 — InvalidData.java

```java
class InvalidData {
    @CheckedField(required = true)
    int id;
}
```

Field `id` has `required=true` but type `int`, so the processor sends `ERROR`. At the same time, it also lacks `reason`, so there is a warning as well.

### Compilation Commands and Observations

In the directory containing the four files, first compile the annotation and processor:

```bash
javac --release 17 CheckedField.java FieldCheckProcessor.java
```

Then compile each input separately, avoiding combining them into one invocation so the diagnostic levels are easy to read:

```bash
javac --release 17 -cp . -processorpath . -processor FieldCheckProcessor ValidData.java

javac --release 17 -cp . -processorpath . -processor FieldCheckProcessor InvalidData.java
```

**Result with ValidData.java:** exit code **0** (success), despite having two warnings. Excerpt of the meaningful diagnostics from the Java 17 run:

```text
ValidData.java:3: Note: checking field id
ValidData.java:6: Note: checking field count
ValidData.java:6: warning: document the reason
ValidData.java:9: Note: checking field legacyCode
ValidData.java:9: warning: legacy field needs migration
2 warnings
```

In the actual console output, the compiler also prints the field declaration line and the `^` caret indicating the position; the order and line/column details may differ across IDEs, JDKs, and other processors. The output above is a **summarized diagnostic excerpt**, not the full byte-for-byte console output.

**Result with InvalidData.java:** **non-zero** exit code (failure). Diagnostic excerpt from Java 17:

```text
InvalidData.java:3: Note: checking field id
InvalidData.java:3: warning: document the reason
InvalidData.java:3: error: required field must have type String
1 error
1 warning
```

**What the experiment demonstrates:** a processor can produce warnings and notes while still compiling successfully. When it sends `Diagnostic.Kind.ERROR`, compilation fails. Even though `MANDATORY_WARNING` is a different enum from `WARNING`, the console output in the example displays both as `warning:`.

This is a program that runs *inside the compiler*, not an application with `public static void main` to invoke `java FieldCheckProcessor`. The annotation processor is loaded and invoked by `javac` via `-processor`.

## 6. Attaching Messages to the Right Source Location: Why Pass Element?

Compare:

```java
// General message, usually without a field location.
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "Invalid field");

// Message attached to the field declaration.
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "Invalid field",
        field);
```

With the overload taking `field`, `javac` can display the filename, declaration line, and `^` caret underneath the field name. This capability matters when there are hundreds of fields: instead of a generic "Invalid field", the programmer knows **where to fix it**.

When configuration resides in an element of an annotation:

```java
@Constraint(min = -1, max = 10)
int quantity;
```

A good diagnostic can attach to the **`AnnotationValue` of `min`** if you have the appropriate `Element`, `AnnotationMirror`, and `AnnotationValue`. However, errors involving **two values** (such as min being greater than max) may fit better when attached to the annotation or the entire declaration, along with a clear explanation of the relationship that needs fixing. Avoid providing a "very precise" location that is semantically the wrong location.

Quality tips:

- Use messages with **clear verbs and conditions**: `"required field must have type String"` is better than `"invalid"`.
- State the **observed value** and **expected value** when appropriate: `"expected String, found int"`.
- Attach the corresponding `Element`; use a deeper overload when an actual annotation mirror/value is available.
- Include an easily searchable message code/suffix if your organization has a convention, without making the message hard to read.
- Do not force users to open the processor's source code just to understand how to fix the issue.

## 7. printMessage(ERROR) Differs from throw Exception

One of the biggest misconceptions is treating:

```java
messager.printMessage(Diagnostic.Kind.ERROR, "Invalid", element);
```

as equivalent to `throw new IllegalStateException(...)`.

**They are different:**

| Approach | Meaning | Primary Impact |
|---|---|---|
| `printMessage(ERROR, ..., e)` | Source error diagnostic under the processing contract | Compiler marks an error, and the user's source location is pointed out |
| `throw new RuntimeException(...)` | Processor encountered an unhandled exception | Can cause the processor/compiler task itself to fail with a stack trace, providing user-unfriendly error details |
| `printMessage(WARNING, ..., e)` | Advisory warning | Compiler may still succeed depending on flags |
| `System.out.println(...)` | Prints to standard output | Not treated as a diagnostic by itself and does not cause compilation to fail |

Emit `ERROR` for **invalid source input**, then proactively avoid generating broken code. Only throw exceptions for internal errors that truly cannot be handled in a controlled manner (for example, when an invariant in the processor's own implementation is broken), and when appropriate, convert them into clear diagnostics.

For example:

```java
if (!isValid(element)) {
    processingEnv.getMessager().printMessage(
            Diagnostic.Kind.ERROR,
            "Invalid declaration for code generation",
            element);
    continue; // Skip the invalid element.
}
generateSource(element); // Run only for valid elements.
```

This snippet is **Java pseudocode inside a processor loop**, requiring corresponding `isValid` and `generateSource` methods in a real program. Key takeaway: `printMessage(ERROR)` does not stop execution of the subsequent lines of code on its own.

## 8. -Werror, -nowarn, and Compiler Flags

Diagnostic severity is also tied to build configuration. With `javac`:

**`-Werror`:** treats warnings as a cause for compilation failure. With the same `ValidData.java` from the example above, running:

```bash
javac --release 17 -Werror -cp . -processorpath . \
    -processor FieldCheckProcessor ValidData.java
```

This uses multi-line syntax for shells that support backslash continuation; in PowerShell/cmd on Windows, use a single line or the appropriate line-continuation syntax for your shell:

```bash
javac --release 17 -Werror -cp . -processorpath . -processor FieldCheckProcessor ValidData.java
```

Because the processor emits warnings, compilation can fail under `-Werror` even though no field violates the processor's `ERROR` condition. When diagnosing a build failure, check **the compiler flags**, not just the Java source.

**`-nowarn` / `-Xlint:none`:** can control the display of certain compiler-emitted warnings, but **do not treat them as a filter that can disable all diagnostics from every processor and every mandatory warning**. Behavior can vary across diagnostic kinds and implementations. If a business rule must block the build, use `ERROR`; do not rely on external warning-display policies.

**`-Xmaxerrs N` / `-Xmaxwarns N`:** limits the number of diagnostics displayed by `javac` in the respective categories. A build with many errors may only show a subset if the limit is low.

**`-Xlint`:** allows enabling/disabling warning categories known to `javac`. Having `-Xlint:all` enabled does not mean a custom annotation processor will automatically exist or that all rules will run automatically.

A good operational practice: configure **processor discovery**, the processor path, and warning-as-error settings in your build/CI; do not rely on "it builds green on my machine" if the IDE does not run the processor.

## 9. Combining with RoundEnvironment and Processing Rounds

A processor is invoked across multiple rounds if sources/classes are generated during processing. On each call to `process`:

```java
boolean over = roundEnv.processingOver();
boolean raisedBefore = roundEnv.errorRaised();
```

- `processingOver()` indicates whether the current round is the final round of annotation processing; sources generated in the final round will not be processed in a subsequent round.
- `errorRaised()` indicates whether **an error was raised in the previous round**; do not infer from `false` that the final compilation result will succeed.

A defensive pattern:

```java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {

    if (roundEnv.processingOver()) {
        return true;
    }

    for (Element e :
            roundEnv.getElementsAnnotatedWith(CheckedField.class)) {
        validateAndReport(e);
    }
    return true;
}
```

This is an illustrative skeleton: `validateAndReport` needs to be defined in the processor and use `Messager`. If a task needs to print a summary report in the final round, it can do so, but do not automatically **repeat all errors from previous rounds** just because the summary step runs one more time.

### Avoiding Duplicate Reports on the Same Input

If a processor scans `RoundEnvironment` round by round and maintains state, it needs to track which elements have already been processed. For example, a generator might create additional source files, triggering a new round; if the scan logic is poorly designed and re-scans all previously seen types, the same error may be printed multiple times. Scope processing to the elements present in the current round or use an explicit identifier/deduplication mechanism.

Do not assume an arbitrary classpath scan has a stable ordering. A `Set<? extends Element>` does not guarantee iteration order, so if diagnostics require deterministic ordering, sort them by an appropriate key. Do not tie logic like "the first warning line is the most important" to an arbitrary order.

### ERROR and Source Generation

If an invalid annotation prevents code generation from producing valid output, it is better to:

1. Emit an `ERROR` diagnostic at the violating source location.
2. Mark the input as erroneous and skip generating output for that input.
3. Let the compiler handle the failure according to the annotation processing lifecycle.

Avoid emitting `ERROR` while also generating invalid source files, which causes users to receive dozens of cascading secondary errors that obscure the root cause.

## 10. Using NOTE and Progress Messages Appropriately

A `NOTE` diagnostic is not completely harmless in terms of developer experience: a processor in a large project may run across thousands of elements. If every element emits three NOTEs, the console/CI log becomes noisy and hides important warnings.

Practical choices:

- Few, meaningful NOTEs at start/end milestones or when generating important artifacts.
- WARNING when there is a real risk and the user can take action.
- ERROR when the input fails to satisfy a mandatory contract.
- MANDATORY_WARNING only when mandatory-warning semantics are genuinely required.
- Limit repeating diagnostics across rounds or across multiple processors.

If detailed debugging is needed, consider a processor option (for example, `-AmyProcessorDebug=true`) and only emit detailed NOTEs when debugging is enabled. When using annotation processor options of the form `-Akey=value`, your code needs to declare supported options or handle them so the compiler/build recognizes them as supported options; do not treat arbitrary keys as standard Java flags.

**There is no rule requiring NOTE to appear before WARNING or ERROR.** Different compilers/IDEs may group or sort diagnostics differently. For integration tests, verify the severity kind and core message content rather than relying on full byte-for-byte output and ordering if the toolchain is not fixed.

## 11. @SuppressWarnings and Custom Diagnostics

`@SuppressWarnings` is the standard annotation used by compilers/tools to ignore certain warnings with specific keys. However:

**Calling `Messager.printMessage(WARNING, ...)` from a processor does not automatically create an `-Xlint` warning category or a suppression rule for `@SuppressWarnings("custom-key")`.**

If you want users to be able to disable a custom processor warning within a specific scope, you need to:

1. Define the suppression key and which diagnostic types are allowed to be suppressed.
2. Before emitting a warning, have the processor inspect `@SuppressWarnings` or a custom configuration annotation according to documented rules.
3. Skip only matching warnings, without suppressing mandatory errors.
4. Test scopes (class, method, field) and precedence consistently.

Do not expect `@SuppressWarnings("unchecked")` to suppress the `"document the reason"` warning in the example by default. The two warnings belong to independent mechanisms.

If a warning is truly a serious issue affecting correctness, choose `ERROR` instead of relying on a warning that can easily be ignored. Conversely, do not overuse ERROR for every style issue or improvement suggestion.

## 12. Why Messages from an IDE and javac May Differ

Java defines the `Messager`/`Diagnostic.Kind` model, but the tools consuming diagnostics may behave differently:

- **javac CLI** typically prints the source line, line number, `^`, message, and error/warning counts.
- **IDEs** may present markers/gutter icons, a Problems view, quick navigation, or only run the processor when annotation processing is enabled.
- **Build tools** such as Maven/Gradle may aggregate diagnostics, add prefixes, filter logs, run incremental compilation, or wrap compiler output.
- **The Compiler API** may deliver diagnostics to clients via `DiagnosticListener` depending on how it is integrated.

Therefore, write messages that are self-explanatory enough even when an IDE does not attach precisely to the element name. A context-free message like `"invalid value"` is harder to act on than `"@CheckedField(required=true) requires java.lang.String, found int"`.

In automated tests, verify:

- Valid inputs yield a successful exit code.
- Inputs violating an ERROR rule yield a failing exit code.
- WARNING and NOTE appear according to the triggered rules.
- Reasonable file/line or element information is reported if the toolchain supports it.
- No unintended duplicate diagnostics appear across rounds.
- The tool runs on the JDK/compiler version used by the actual project.

If the toolchain changes its display formatting, semantic checks will still hold up.

## 13. Common Mistakes When Using Messager

### Mistake 1 — Printing to System.out and Assuming the Build Will Fail

```java
System.out.println("ERROR: invalid annotation");
```

This is a console string, not `Diagnostic.Kind.ERROR`. To let the compiler know there is an error, use `processingEnv.getMessager().printMessage(ERROR, ..., element)`.

### Mistake 2 — Calling ERROR and Continuing to Generate Code from Invalid Data

`printMessage(ERROR)` does not stop the remaining Java lines in `process` on its own. You need `continue`, `return`, or proper control-flow branching to avoid generating broken source code.

### Mistake 3 — Reporting a Generic Error Without an Element

`printMessage(ERROR, "Invalid")` may lack the fix location; pass the appropriate `Element`. When you want to point to a specific annotation member-value pair, consider also passing `AnnotationMirror` and `AnnotationValue`.

### Mistake 4 — Assuming WARNING Never Breaks the Build

Enabling `-Werror` can cause compilation to fail. If CI requires zero warnings, the build can fail even when the processor code only emits WARNING.

### Mistake 5 — Using MANDATORY_WARNING as ERROR

`MANDATORY_WARNING` is still a **warning kind**, not an error that forces compilation to fail under every configuration. If you need a constraint that must fail compilation, use ERROR.

### Mistake 6 — Confusing NOTE with Arbitrary Debug Logging

NOTEs can appear in large numbers and make logs hard to read. A processor running across many modules should avoid sending a NOTE for every field unless debugging.

### Mistake 7 — Believing -Xlint:all Automatically Activates Processors

`-Xlint:all` only applies to warning categories supported by javac. An annotation processor must be discovered/configured; `Messager` APIs will not be invoked automatically if the processor does not run.

### Mistake 8 — Using Mismatched Element/AnnotationValue

If you pass an `AnnotationMirror` not present on the referenced `Element`, or an `AnnotationValue` not belonging to that mirror, the source location may not be useful. Always retrieve metadata from the exact declaration being inspected.

### Mistake 9 — Reporting Duplicates Across Rounds

Re-scanning all sources and emitting the same warnings/errors in every round causes confusion and can make tests flaky. Structure processing by round while handling each necessary declaration consistently.

### Mistake 10 — Comparing Java Types Using toString in Production Code

In the `required=true` example, `field.asType().toString().equals("java.lang.String")` is used for illustration. For real-world type checking, use `Types.isSameType`, `Types.isAssignable`, or compatible operations on `TypeMirror` so you do not depend on string representations.

### Mistake 11 — Treating a Default Value as an Explicitly Written Source Element

An annotation element that does not appear explicitly may have a default value. The diagnostic still needs to report the violation, but there is no source literal pair to attach to precisely. Report it on the annotation or the enclosing declaration.

### Mistake 12 — Using throw for Normal Input Errors

An unhandled processor exception can produce a stack trace that makes it hard for users to understand how to fix their input. Emit clear diagnostics with Messager for source contract errors; reserve exceptions for internal errors where processing cannot continue.

## 14. Process for Choosing Diagnostic.Kind

When detecting an issue in a processor, answer the following in order:

1. **Is this invalid input according to a mandatory contract?** If so, send `ERROR` at the right `Element`/annotation value, then avoid generating code from the invalid input.
2. **Is this a guideline violation where the result is still usable?** Use `WARNING`. Clearly state how to fix it and the consequences if left unfixed.
3. **Is this a mandatory warning under the tool's semantics?** Consider `MANDATORY_WARNING`, but do not substitute it for ERROR when failure is genuinely needed.
4. **Is it merely information for the user?** Use `NOTE`, and limit the quantity.
5. **Does it need to point accurately to the declaration/value?** Choose the `printMessage` overload with the deepest practical and accurate context.
6. **Could it repeat when source generation triggers a new round?** Build idempotent handling or store an appropriate deduplication key.
7. **Is it effective in CI?** Test valid/invalid inputs and the `-Werror` flag; verify that the build actually runs the processor.

A decision diagram:

```text
Event detected in processor
        |
        +-- Violates mandatory contract? --> ERROR (+ skip invalid generation)
        |
        +-- Risk requiring user fix?     --> WARNING
        |                                    (or intentional MANDATORY_WARNING)
        |
        +-- Only needs status update?    --> NOTE
```

This diagram is a **design process**, not automatic behavior inferred by Java from annotation names.

## 15. Self-Check Exercises

### Exercise 1 — Choosing a Diagnostic Severity

A processor requires `@Entity` to be placed only on non-abstract classes so that a factory can be generated. An abstract class is annotated with `@Entity`. What should be reported?

**Answer:** typically `ERROR` if a valid factory cannot be generated according to the contract. The diagnostic should be attached to the `TypeElement` of the offending class.

### Exercise 2 — Warnings and Exit Code

`ValidData.java` in the example reports NOTE, WARNING, and MANDATORY_WARNING, but no ERROR. What is the default javac result?

**Answer:** it can still succeed (the experiment yields exit code 0); warnings are printed for the user's consideration. If `-Werror` is added, the build can fail due to the warnings.

### Exercise 3 — printMessage Without an Element

Two calls:

```java
messager.printMessage(Diagnostic.Kind.ERROR, "Wrong field");
messager.printMessage(Diagnostic.Kind.ERROR, "Wrong field", field);
```

Which call is more useful when you need to point to the exact line of the violating field?

**Answer:** the second call, because passing `Element` lets the compiler attach a source location when possible.

### Exercise 4 — Is MANDATORY_WARNING Equivalent to ERROR?

**Answer:** no. It is still a warning kind. `ERROR` is what represents a mandatory violation that causes compilation to fail; compiler flags such as `-Werror` can change the consequence of a warning.

### Exercise 5 — Errors Printed Multiple Times

A processor prints the same error in three processing rounds. Does RoundEnvironment automatically deduplicate all errors?

**Answer:** no. The processor must structure scanning with the proper round scope and/or deduplicate by an appropriate identity; `Messager` does not automatically provide a deduplication policy for business-rule diagnostics.

### Exercise 6 — Default Values

An annotation defines `String reason() default "";`, and the user only writes `@CheckedField`. If you want to report `"reason must be provided"` at the source, can you reliably obtain an `AnnotationValue` for a `reason=""` literal?

**Answer:** no. The user did not write that pair, so you should report the error on the annotation mirror or element; if you need to read the default value for analysis, use the `Elements.getElementValuesWithDefaults` API.

### Exercise 7 — How Does System.out Differ from Messager?

**Answer:** `System.out.println` produces ordinary text output and is not automatically recognized by the compiler as a diagnostic. `Messager.printMessage` passes a `Diagnostic.Kind` classification and can attach source context.

### Exercise 8 — Is a WARNING Suppressed by @SuppressWarnings("custom") by Default?

**Answer:** no. A custom processor that wants to support suppression must implement its own mechanism to recognize keys, evaluate scope, and decide not to emit the corresponding warning.

### Exercise 9 — More Precise Source Locations

When an annotation has `@Limit(max = -1)` and the error lies in the value of `max`, which overload can provide the most specific source context?

**Answer:** the overload accepting `Diagnostic.Kind`, message, `Element`, `AnnotationMirror`, and `AnnotationValue`, with the mirror/value pointing accurately to `max`. However, display precision still depends on the compiler/IDE.

### Exercise 10 — Does NOTE Guarantee the Build Succeeded?

**Answer:** no. NOTE only reports information; the build can fail elsewhere due to a compiler error or another processor.

## 16. Summary

**Messager** is the diagnostic reporting channel for annotation processors; **Diagnostic.Kind** distinguishes severity levels. `ERROR` is for unacceptable input; `WARNING` highlights risks that do not necessarily cause failure; `MANDATORY_WARNING` is for mandatory warnings; `NOTE` is for informational messages; `OTHER` is for diagnostic kinds outside the categories above.

To make a processor helpful to programmers, emit messages with the **right severity, clear content, accurate source element, and no unintended duplicates**. Combining `RoundEnvironment`, `Messager`, and `Element`/`AnnotationMirror`/`AnnotationValue` turns an annotation processor into a real compile-time checking tool. A good message identifies **the violated condition and how to fix it**, rather than merely saying "invalid annotation".

### Official Java SE 17 Documentation

- [Messager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Messager.html): the four overloads of `printMessage` and rules for associating diagnostics with source locations.
- [Diagnostic.Kind](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.Kind.html): the `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE`, and `OTHER` kinds.
- [Diagnostic](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.html): the diagnostic model provided by the Java Compiler API.
- [ProcessingEnvironment](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/ProcessingEnvironment.html): `getMessager()` and processor resources.
- [RoundEnvironment](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): `getElementsAnnotatedWith` and round state.
- [Elements](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Elements.html): `getElementValuesWithDefaults` and declaration-model utilities.
- [javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `-processor`, `-processorpath`, `-Werror`, `-Xlint`, and diagnostic display options.
