# Attaching errors and warnings to elements with Messager in annotation processors

When building an annotation processor, detecting invalid annotations is only half the job. The other half is **reporting diagnostics at the right severity level and attaching them to the right source location** so users know which annotation, element, or attribute value must be fixed. In Java 17+, the central API for that is `javax.annotation.processing.Messager`, obtained from `ProcessingEnvironment.getMessager()`.

For example: if the convention for `@CheckedName("...")` rejects blank names, users will understand the issue faster when the compiler highlights **the `""` string itself** on the annotation line instead of only printing “Invalid name” without a location. For a short yet still valid value, the processor can emit a `WARNING` as a reminder without blocking compilation. Diagnostic classification and accurate positioning are an important part of developer experience quality.

Lesson objectives: understand the `printMessage` overloads, distinguish `Diagnostic.Kind`, retrieve `Element` / `AnnotationMirror` / `AnnotationValue` properly, build a processor runnable via `javac`, inspect output and exit codes, handle processing *rounds*, avoid duplicate or mislocated diagnostics, and write tests for errors and warnings.

## 1. Context: processors execute at compile time

Annotation processing is part of the build process. When `javac` runs a processor, it provides a model of the program being compiled through `javax.lang.model` and the processing environment through `ProcessingEnvironment`.

Simplified flow:

```text
.java source file
       |
       v
javac parses syntax / symbols / annotations
       |
       v
Annotation processor (AbstractProcessor.process)
       |
       |-- reads Element / AnnotationMirror / AnnotationValue
       |-- checks annotation rules
       |-- calls processingEnv.getMessager().printMessage(...)
       |
       v
Compiler / IDE / build tool receives diagnostics
       |
       +-- ERROR: build fails
       +-- WARNING: reports risk, build can succeed
       +-- NOTE: additional information
       |
       v
Class files can be generated if there are no errors and compilation mode permits
```

`Messager` **is not** a runtime API of a Java application. It is not meant for printing logs to the console while the user's program is running. This object serves **diagnostic reporting from a processor while the compiler is processing source code**.

If a processor only calls `System.out.println("invalid")` or `System.err.println("invalid")`, the output generally lacks standardized severity and source location. The compiler does not treat a console print line as an `ERROR` of the diagnostic system. Use `Messager` instead of trying to manually format “file:line:col” strings.

### Concepts to know

| Component | Role |
| --- | --- |
| `AbstractProcessor` | Convenience base class for implementing `Processor` |
| `ProcessingEnvironment` | Provides `Messager`, `Elements`, `Types`, `Filer`, and options |
| `RoundEnvironment` | List of elements in the current processing round and processing status |
| `Element` | Program model element: class, field, method, parameter... |
| `AnnotationMirror` | A single annotation usage on an element in the Java model |
| `AnnotationValue` | Value of an annotation member, e.g., `"AB"` in `value = "AB"` |
| `Messager` | API for emitting diagnostics from a processor |
| `Diagnostic.Kind` | Severity level of a diagnostic (`ERROR`, `WARNING`, `NOTE`...) |

**Note:** Element and AnnotationMirror are objects belonging to the compiler model; they are not synonymous with `java.lang.reflect.AnnotatedElement` and `java.lang.annotation.Annotation` of runtime reflection.

## 2. Four ways to call Messager.printMessage

Java SE 17 defines four overloads of `Messager.printMessage`:

```java
void printMessage(Diagnostic.Kind kind, CharSequence msg);

void printMessage(Diagnostic.Kind kind, CharSequence msg, Element e);

void printMessage(Diagnostic.Kind kind, CharSequence msg,
                  Element e, AnnotationMirror a);

void printMessage(Diagnostic.Kind kind, CharSequence msg,
                  Element e, AnnotationMirror a, AnnotationValue v);
```

The declarations above **illustrate API signatures**, not code to copy into your class.

| Call | Diagnostic location hint | When to use |
| --- | --- | --- |
| `printMessage(kind, message)` | Not attached to a specific source element | General processor or configuration diagnostics |
| `printMessage(kind, message, element)` | Element: class, method, field... | Rules applying to the entire element |
| `printMessage(kind, message, element, mirror)` | Annotation on the element | Rules applying to the annotation itself |
| `printMessage(kind, message, element, mirror, value)` | A value inside the annotation | Errors/warnings specific to an annotation attribute |

The most important distinction: **the more appropriate context you provide, the better chance the compiler has to mark the right location**. However, the Java API only promises that those objects are *location hints*: depending on compiler, IDE, source availability, and annotation form, the chosen location may be approximate or unspecified. Do not claim every implementation always underlines the exact same characters identically.

Use the most detailed form that makes sense. If an error lies in the value `timeout = -1`, attaching to the `AnnotationValue` of `timeout` is more helpful than attaching to a class hundreds of lines long.

## 3. Diagnostic.Kind: when error, when warning?

`javax.tools.Diagnostic.Kind` has the relevant values:

- `ERROR`: a mandatory rule was violated; reporting an error causes compilation to fail.
- `WARNING`: suspicious behavior or something needing attention yet still permitted; normal compilation can proceed.
- `MANDATORY_WARNING`: a mandatory warning kind in the diagnostic system, reserved for appropriate cases; do not use it merely to force every warning into an error.
- `NOTE`: supplemental information helping users follow along; do not overuse as it lengthens logs.
- `OTHER`: a diagnostic not fitting the categories above; rarely needed for routine validation.

### Practical rules

| Scenario | Suggested kind | Reason |
| --- | --- | --- |
| Annotation has an empty value while contract requires non-empty | `ERROR` | Source cannot be accepted per processor rules |
| Element carries annotation with wrong `ElementKind` per custom rule | `ERROR` | Source is invalid for the processor |
| Value is valid yet does not follow recommended naming conventions | `WARNING` | Let the user decide or fix gradually |
| Using a legacy API with a replacement path | `WARNING` | Worth reminding without necessarily blocking the build |
| Reporting summary info that does not affect correctness | `NOTE` | Diagnostic aid; should be sparse and clear |
| Language or tool rule requires a mandatory warning | `MANDATORY_WARNING` when truly appropriate | Does not replace `-Werror` policy |

For most routine annotation validation, choose `ERROR` for **mandatory requirement violations**, `WARNING` for **recommendations or issues to review**, and `NOTE` for helpful information. Do not turn everything into `ERROR` because that makes the processor difficult to use in legacy projects or migrations.

**`ERROR` differs from a Java exception.** Calling `messager.printMessage(Diagnostic.Kind.ERROR, ...)` reports a diagnostic to the compiler; it is not `throw new RuntimeException(...)`. Typically the processor can still finish the logic of the current processing round, and the compiler aggregates errors to return a failure result. No need to throw exceptions just to “ensure” errors are seen.

## 4. Java 17+ lab: preparing the annotation and processor

We build the `@CheckedName` checker:

- **Empty** name: `ERROR` `[NAME001]` at the **annotation value**.
- Name **under 3 characters**: `WARNING` `[NAME002]` at the **annotation value**.
- Name **3 characters or longer**: `NOTE` `[NAME000]` at the **annotation** (solely to make the lesson easy to observe).
- The processor does not generate classes, only validates sources.

Structure of an independent practice directory:

```text
messager-lab/
  src/
    diagnostics/
      CheckedName.java
      NameProcessor.java
  examples/
    Cases.java
    Good.java
    Warning.java
  out/
    processor/    (created by javac)
    classes/      (created by javac)
```

The examples require no Maven, Gradle, or `module-info.java` file, because here we focus on an **annotation processor running on the classpath** to reduce off-topic factors.

### 4.1. File src/diagnostics/CheckedName.java

```java
package diagnostics;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface CheckedName {
    String value();
}
```

Explanation:

1. `@Target(ElementType.TYPE)` allows placing the annotation on type declarations (classes, interfaces... per the corresponding target rules).
2. `@Retention(RetentionPolicy.SOURCE)` indicates the annotation is needed only in source/during compilation; it does not need to be retained in class files at runtime.
3. `String value();` is a required annotation member without a default value, making it easy to obtain the exact `AnnotationValue` appearing in source.

`RetentionPolicy.SOURCE` **does not prevent annotation processors from reading the annotation**; on the contrary, source-retention annotations are well suited for compile-time rules, code generation, and static validation.

### 4.2. File src/diagnostics/NameProcessor.java

```java
package diagnostics;

import java.util.Map;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.AnnotationMirror;
import javax.lang.model.element.AnnotationValue;
import javax.lang.model.element.Element;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("diagnostics.CheckedName")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class NameProcessor extends AbstractProcessor {
    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnv) {
        for (TypeElement annotationType : annotations) {
            for (Element element :
                    roundEnv.getElementsAnnotatedWith(annotationType)) {
                AnnotationMirror mirror =
                        findMirror(element, annotationType);
                if (mirror == null) {
                    continue;
                }

                for (Map.Entry<? extends ExecutableElement,
                        ? extends AnnotationValue> entry :
                        mirror.getElementValues().entrySet()) {
                    if (!entry.getKey().getSimpleName()
                            .contentEquals("value")) {
                        continue;
                    }

                    String value = (String) entry.getValue().getValue();
                    if (value.isBlank()) {
                        processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.ERROR,
                            "[NAME001] Ten khong duoc de trong",
                            element, mirror, entry.getValue());
                    } else if (value.length() < 3) {
                        processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.WARNING,
                            "[NAME002] Ten nen co tu 3 ky tu",
                            element, mirror, entry.getValue());
                    } else {
                        processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.NOTE,
                            "[NAME000] Ten hop le: " + value,
                            element, mirror);
                    }
                }
            }
        }
        return true;
    }

    private AnnotationMirror findMirror(
            Element element, TypeElement annotationType) {
        for (AnnotationMirror mirror : element.getAnnotationMirrors()) {
            if (processingEnv.getTypeUtils().isSameType(
                    mirror.getAnnotationType(), annotationType.asType())) {
                return mirror;
            }
        }
        return null;
    }
}
```

**This is a runnable processor**, not pseudocode. In the lab, diagnostic messages use unaccented Vietnamese so console logs remain consistent across environments. In real projects, you can choose UTF-8 Vietnamese or English messages and standardize localization.

Mechanism explanation:

1. `@SupportedAnnotationTypes("diagnostics.CheckedName")` declares the annotation type supported by the processor. The name is the **fully qualified name**, matching the annotation's package.
2. `@SupportedSourceVersion(SourceVersion.RELEASE_17)` declares the source level supported by the processor. Demo commands use `--release 17` to avoid warnings about newer source versions.
3. `process(annotations, roundEnv)` receives the current round's set of annotation types and the environment to find marked elements.
4. `roundEnv.getElementsAnnotatedWith(annotationType)` retrieves `Element`s. Using the overload taking `TypeElement` avoids depending on loading an annotation class via reflection inside the processor.
5. `findMirror` locates the exact `AnnotationMirror` on the element by comparing `TypeMirror` via `Types.isSameType`.
6. `mirror.getElementValues()` contains `ExecutableElement -> AnnotationValue` pairs for annotation members **explicitly declared** in that usage.
7. For the member named `value`, we read the data and emit diagnostics with all three objects `element, mirror, entry.getValue()` when the error belongs to a value.
8. `return true` indicates the processor has *claimed* the annotation types it handles, affecting whether subsequent processors can process the same annotations; **it does not mean the build succeeded**. Success/failure is decided by diagnostics and the compiler.

`entry.getValue().getValue()` returns an `Object`, yet the annotation defines `String value()` so casting `(String)` matches **this specific annotation definition**. If you support multiple member types (primitive, enum, class literal, nested annotation, array), handle each according to the corresponding value kind and API rather than casting every `AnnotationValue` to `String`.

## 5. Compile the processor first, then run it

In the `messager-lab` directory, execute:

```bash
javac --release 17 -d out/processor src/diagnostics/CheckedName.java src/diagnostics/NameProcessor.java
```

This command compiles both the annotation interface and the processor. When successful, you have:

```text
out/processor/diagnostics/CheckedName.class
out/processor/diagnostics/NameProcessor.class
```

Afterward, the application compiler needs **two perspectives**:

- `-cp out/processor`: allows sample source code to import `diagnostics.CheckedName`.
- `-processorpath out/processor`: allows the compiler to load class `diagnostics.NameProcessor` to execute annotation processing.
- `-processor diagnostics.NameProcessor`: selects the exact desired processor, **without relying on auto-discovery**.
- `-proc:only`: **runs only annotation processing without generating class files for application sources**; useful when testing diagnostics.
- `-d out/classes`: specifies the output directory if the compiler creates files; `-proc:only` does not emit `.class` files for input classes.

Note: in a real project, the annotation artifact may reside on the compile classpath or module path, while the processor artifact sits on the processor path. Do not conflate “user code imports the annotation” and “compiler loads processor code” merely because the lab places them in the same directory for convenience.

**Verified with JDK 24 using `--release 17`:** the command compiling the two files in `src/diagnostics` succeeded with exit code `0`. The code uses no APIs newer than Java 17.

## 6. Verifying ERROR, WARNING, and NOTE at the right locations

### 6.1. File examples/Cases.java

```java
import diagnostics.CheckedName;

@CheckedName("")
class MissingName {}

@CheckedName("AB")
class ShortName {}

@CheckedName("Customer")
class GoodName {}
```

There is no `public` class, so a single source file `Cases.java` can contain all three class declarations above.

Run:

```bash
javac --release 17 -cp out/processor -processorpath out/processor -processor diagnostics.NameProcessor -proc:only -d out/classes examples/Cases.java
```

Verified actual diagnostic excerpt:

```text
examples/Cases.java:3: error: [NAME001] Ten khong duoc de trong
@CheckedName("")
             ^
examples/Cases.java:6: warning: [NAME002] Ten nen co tu 3 ky tu
@CheckedName("AB")
             ^
examples/Cases.java:9: Note: [NAME000] Ten hop le: Customer
@CheckedName("Customer")
^
1 error
1 warning
```

Meaning:

- **`[NAME001]` — ERROR:** the underline position is at **the `""` value**, not on the `MissingName` class line, because of calling overload `printMessage(ERROR, ..., element, mirror, value)`.
- **`[NAME002]` — WARNING:** the position is at **the `"AB"` value**, still considered valid source by the compiler if there are no other errors.
- **`[NAME000]` — NOTE:** the position is at **the `@CheckedName` annotation**, because of calling the overload passing only `element, mirror`.
- Because an `ERROR` occurred, **`javac` returns a non-zero exit code** (specific test: `1`). Do not rely on the line `"1 error"` as the sole machine-readable API; check the compiler's exit code.

The line numbers above match the exact source in Section 6.1. Diagnostic wording is the string defined by the processor, while path formatting, column indicators, caret symbols, and additional details may differ across shells, IDEs, and `javac` implementations.

### 6.2. File examples/Good.java: succeeding with NOTE only

```java
import diagnostics.CheckedName;

@CheckedName("Customer")
class Customer {}
```

Run:

```bash
javac --release 17 -cp out/processor -processorpath out/processor -processor diagnostics.NameProcessor -proc:only -d out/classes examples/Good.java
```

Diagnostic excerpt:

```text
examples/Good.java:3: Note: [NAME000] Ten hop le: Customer
@CheckedName("Customer")
^
```

**Exit code `0`** in the verified experiment. `NOTE` is neither `ERROR` nor `WARNING` and does not itself fail compilation. `-proc:only` still does not emit `Customer.class`, even when exit code is `0`.

In a processor meant for real production releases, it is not necessary to emit `NOTE` on every valid annotation: doing so can clutter logs on large projects. We added `NOTE` solely to illustrate attaching to the annotation and distinguishing diagnostic severity levels.

### 6.3. File examples/Warning.java: warnings do not block normal builds

```java
import diagnostics.CheckedName;

@CheckedName("AB")
class ShortName {}
```

Run:

```bash
javac --release 17 -cp out/processor -processorpath out/processor -processor diagnostics.NameProcessor -proc:only -d out/classes examples/Warning.java
```

Excerpt:

```text
examples/Warning.java:3: warning: [NAME002] Ten nen co tu 3 ky tu
@CheckedName("AB")
             ^
1 warning
```

In this experiment, the compiler **returns exit code `0`**. If the build team wants to reject warnings, run:

```bash
javac --release 17 -cp out/processor -processorpath out/processor -processor diagnostics.NameProcessor -proc:only -Werror -d out/classes examples/Warning.java
```

The additional diagnostic looks like:

```text
error: warnings found and -Werror specified
1 error
1 warning
```

Now the compiler **returns a non-zero exit code** (experiment: `1`), yet the processor **still emits a `WARNING`**, without changing `Diagnostic.Kind.WARNING` into `ERROR`. `-Werror` is a **javac/build policy**, not a severity kind that processors must use for every warning.

## 7. Diagnostic attachment locations: Element, mirror, and value

Consider three ways of diagnosing the same annotation:

```java
Messager messager = processingEnv.getMessager();

// Whole element; compiler suggests the class/field/method declaration location.
messager.printMessage(
    Diagnostic.Kind.ERROR,
    "[RULE100] Phan tu khong hop le",
    element);

// Specific annotation on the element.
messager.printMessage(
    Diagnostic.Kind.WARNING,
    "[RULE101] Annotation can xem lai",
    element, mirror);

// A specific valued member inside the annotation.
messager.printMessage(
    Diagnostic.Kind.ERROR,
    "[RULE102] Gia tri khong hop le",
    element, mirror, annotationValue);
```

This snippet **only illustrates how to call the API** inside a processor, assuming variables `element`, `mirror`, and `annotationValue` were obtained properly; it is not a standalone Java file. The complete runnable skeleton is in `NameProcessor.java` above.

**Location attachment rules:**

1. Errors belonging to the **entire class** (e.g., “annotated class must be public”): use the class's `Element`.
2. Errors belonging to the **annotation usage itself** (e.g., “this annotation should not be used here”): use `Element + AnnotationMirror`.
3. Errors belonging to **an annotation parameter** (e.g., `@Check(min = -5)`): use `Element + AnnotationMirror + AnnotationValue` of `min`.
4. Errors belonging to **general configuration** (e.g., invalid processor option with no specific element): use the overload without `Element`, providing a clear enough message.

Do not take the `Element` of a parent class and arbitrarily pair it with an `AnnotationMirror` belonging to a child field. The tuple must describe **the exact same annotation usage on the exact element**; otherwise, the location hint can be wrong or unusable.

### How to find AnnotationMirror by actual type

`Element.getAnnotationMirrors()` can contain multiple different annotations. Do not pick `get(0)` and assume it is always the right type. The processor used:

```java
processingEnv.getTypeUtils().isSameType(
    mirror.getAnnotationType(),
    annotationType.asType())
```

The annotation mirror's `TypeMirror` is matched against the `TypeElement` passed in by the compiler. This is safer than comparing only the short string name `"CheckedName"`, because there may be annotations in different packages sharing the same simple name.

When you only have the `TypeElement` of the target annotation, an alternative is obtaining the fully qualified name via `Elements`/`TypeElement.getQualifiedName()` and comparing intentionally. Using `Types.isSameType` in the lab fits the same type model within the current processing round.

### How to find the AnnotationValue of the attribute to report

`mirror.getElementValues()` returns a map with keys of type `ExecutableElement` representing the annotation member (e.g., `String value();`), and values of type `AnnotationValue` correspondingly.

In the lab:

```java
if (entry.getKey().getSimpleName().contentEquals("value")) {
    String value = (String) entry.getValue().getValue();
    // entry.getValue() is the AnnotationValue to attach to the location.
}
```

For annotations with multiple attributes, find the exact key by name or element model instead of grabbing the first entry. The map is not a contract for inferring the source position of “attribute #1”; retrieving the right key is what matters.

## 8. Default annotation values are a common trap

If an annotation declares:

```java
public @interface Threshold {
    int min() default 0;
}
```

And the user writes:

```java
@Threshold
class Example {}
```

Then in the `@Threshold` usage, **there is no explicit `min` value written in source**. Per the model API:

- `AnnotationMirror.getElementValues()` retrieves members **explicitly specified** in the annotation use.
- `processingEnv.getElementUtils().getElementValuesWithDefaults(mirror)` returns a map including valid default values.

These are **separate illustrative declarations**, not inside the lab's `@CheckedName` project. When validating the rule “`min` must be greater than 0”, if the attribute is omitted in the annotation use, the effective value is still the default `0`; retrieve it through the defaults-aware API so it is not missed.

However, a **default value has no source location at the annotation usage site**. If reporting an error for `min=0` inherited from default, trying to attach that `AnnotationValue` to source that never wrote `min` may produce an approximate location or fail to display as desired. In that case, a diagnostic attached to the **AnnotationMirror** or **Element** can be more meaningful, accompanied by a message “default value 0 was used”.

Point of distinction: **obtaining the correct logical value** and **locating a source character** are two separate concerns. Do not promise a caret will always exist for a default value the user never typed.

## 9. Multi-round processors: avoiding duplicate reports

Annotation processing can occur across multiple **rounds**, especially when a processor or another tool creates new sources via `Filer`. The compiler may feed newly generated files/elements into the next round.

Two methods of `RoundEnvironment` to know:

```java
roundEnv.processingOver();
roundEnv.errorRaised();
```

- `processingOver()` indicates this round is the final round related to annotation processing; usually used for intentional wrap-up tasks without generating new sources.
- `errorRaised()` reflects error status from the previous round per the API contract; **it does not replace tracking validation state yourself** or deciding final build success.

`RoundEnvironment.getElementsAnnotatedWith(...)` retrieves elements **within the scope of the current round**. The lab processes only elements received in the current round without manually rescanning all sources/classpath, so it does not duplicate diagnostics for the same source merely because the compiler invokes `process` multiple times.

To view processor activity across rounds during debugging:

```bash
javac --release 17 -XprintRounds -XprintProcessorInfo -cp out/processor -processorpath out/processor -processor diagnostics.NameProcessor -proc:only examples/Good.java
```

The `-XprintRounds` and `-XprintProcessorInfo` flags are `javac` diagnostic options whose detailed output varies by JDK and discovered annotations. They help identify when the processor is invoked, which annotations it handles, and whether multiple rounds occur. Do not send all of those logs to application stdout.

**Do not produce duplicate errors across rounds:** if a processor accumulates a list of `Element`s across multiple rounds and re-reports the same error in the final round, users may receive duplicate diagnostics. Choose the right processing round, identify elements stably, and emit one diagnostic per intentional violation.

### return true and return false

`process(...)` returning `true` means the processor **claims** the assigned annotation types; other processors might no longer be asked to process these same annotations under annotation dispatch rules. `false` means not claiming them.

The return value **does not** mean:

- `true` = annotation is valid.
- `false` = compilation failed.
- `false` = the compiler will automatically turn warnings into errors.

Emit `Diagnostic.Kind.ERROR` when an actual error exists. Claiming annotation types and reporting validation failures are two independent decisions.

## 10. Do not use exceptions to replace Messager

There is a clear difference between:

```java
processingEnv.getMessager().printMessage(
    Diagnostic.Kind.ERROR,
    "[NAME001] Ten khong duoc de trong",
    element, mirror, value);
```

and:

```java
throw new IllegalArgumentException("Ten khong duoc de trong");
```

These are two **illustrative** snippets inside a method that already has `element/mirror/value`. When throwing an exception from a processor, the compiler/build tool may print a stack trace for a processor implementation bug instead of underlining where the user needs to fix code. Exceptions should be reserved for abnormal cases where **the processor itself hits an internal error**; for **source failing to follow rules**, reporting `ERROR` at the corresponding location gives a better experience.

If the processor can continue analyzing safely, it can emit **multiple independent errors** in one pass so the user can fix them together. However, do not emit meaningless cascading errors simply because one bad value caused every dependent check to fail.

### Do not overuse stdout/stderr

`Messager` is an abstract API; implementations may display diagnostics in terminals, IDE windows, or build tool UIs. The Oracle API states explicitly that messages **do not necessarily appear as text on `System.out` or `System.err`**. Therefore:

- Do not write tests relying solely on the compiler's `System.out`.
- Do not call `System.err.println` as the primary way to halt compilation.
- For unit/integration tests, inspect **compiler diagnostics and compilation results**.
- If writing custom Java Compiler API tests, you can use `DiagnosticCollector<JavaFileObject>` or an appropriate implementation listener; this is more structured than parsing the entire console log.

## 11. javac options related to annotation processing

| Flag | Role | When to use |
| --- | --- | --- |
| `-processor diagnostics.NameProcessor` | Select processor class directly | Labs, reproducible tests, avoiding auto-discovery dependence |
| `-processorpath out/processor` | Search path for processors | Processors and separate dependencies |
| `-cp out/processor` | Search path for annotations/APIs used in source | So source can import annotations |
| `-proc:only` | Run annotation processing without generating classes for compiled sources | Testing validation and generated sources |
| `-proc:none` | Do not run annotation processing | Isolating processor-caused errors |
| `-XprintRounds` | Print rounds information | Debugging processing rounds |
| `-XprintProcessorInfo` | Print processor/annotation types info | Debugging processor discovery |
| `-Werror` | Treat warnings as build failure cause | CI quality gate rules |
| `-Xmaxerrs N`, `-Xmaxwarns N` | Limit number of diagnostics printed in detail | Controlling long logs |
| `--release 17` | Source/API/target matching Java 17 | Keeping examples Java 17 compatible |

**`-processorpath` differs from `-cp`**, even though in the lab both point to `out/processor` because we placed the annotation interface and processor class in one directory. In real projects, separate the two artifacts to avoid accidentally carrying compiler implementations into runtime.

### Automatic processor discovery

You can register processors via a service provider file inside the processor JAR:

```text
META-INF/services/javax.annotation.processing.Processor
```

The file content is the fully qualified name of the processor:

```text
diagnostics.NameProcessor
```

This is a **description of the registration mechanism**, not a complete JAR creation command in the lab. When packaging completely, place the service file in the proper location inside the artifact and configure the processor search path. Default behavior for processor discovery/auto-execution has changed across JDK releases; for reliable examples on modern toolchains, the lab uses `-processor diagnostics.NameProcessor` **explicitly**.

### Is @SupportedSourceVersion needed?

Yes, or override `getSupportedSourceVersion()` accordingly. If a processor declares it supports only a source version older than the source being used, `javac` may emit a warning about supported source version. That is a tool diagnostic related to processor configuration, **not a user annotation error**.

In the lab, `SourceVersion.RELEASE_17` is paired with `--release 17` for a consistent environment. When upgrading a project to newer Java, evaluate the APIs and source versions the processor actually supports rather than changing the version constant while ignoring compatibility.

## 12. Distinguishing source format errors from processor errors

Suppose a user writes:

```java
@CheckedName(
class Broken {}
```

This is **intentionally invalid Java syntax**. The parser cannot produce a valid annotation use like the lab expects, so the compiler may report syntax errors before the processor runs. You should not expect `Messager` to diagnose an `AnnotationValue` that does not exist in a valid Java model.

Conversely:

```java
@CheckedName("")
class MissingName {}
```

This is **valid annotation syntax**, yet **the processor's custom rule** rejects empty names. At this point, attaching `ERROR` to the value via `Messager` serves its exact purpose.

Two distinct error categories:

- **Syntax/types/language contracts:** normally handled directly by `javac`.
- **Domain business constraints of the annotation:** enforced by the processor and reported via `Messager`.

Do not try to write a processor to replace the parser, type checker, or language rules already guaranteed by Java.

## 13. Common mistakes when attaching diagnostics

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Processor reports error yet IDE only shows log line, cannot jump to source | Used `println` or overload `printMessage(kind,msg)` without element | Use `Element` or mirror/value when location exists |
| Caret `^` lands on the class instead of the annotation value | Passed only `Element` | Locate the exact `AnnotationMirror` and `AnnotationValue` |
| Error reported on a different annotation | Picked mirror by index `get(0)` | Match the specific annotation type |
| Attribute with a default value not found | Used only `getElementValues()` | Consider `getElementValuesWithDefaults()` |
| Underlining default value misses exact character | Defaults have no written location in the annotation use | Report at mirror/element and explain the default |
| Build still succeeds despite warning | `WARNING` does not block compilation by default | Report `ERROR` only for mandatory violations, or use `-Werror` in CI |
| Processor does not run | Processor not added to path or not specified/discovered | Check `-processor` and `-processorpath` |
| Processor runs yet finds no annotations | Wrong fully qualified name, wrong target, wrong source path, round has no elements | Verify `@SupportedAnnotationTypes` and source model |
| Each error repeats two or more times | Re-processing elements across multiple rounds or duplicate reporting logic | Control rounds and deduplicate if needed |
| Stack trace instead of code fix location | Threw exception instead of emitting valid diagnostic | Call `Messager` for user code errors |
| Build tool does not show exact same terminal output | Different compiler implementation diagnostic UI/logging | Inspect compiler results/diagnostics rather than fixed text formatting |
| `-Werror` causes warnings to fail the build | Compiler policy, not processor changing severity itself | Check quality gate and whether diagnostic severity is appropriate |

## 14. Designing user-friendly and testable messages

A good diagnostic should answer **what is wrong, where it is wrong, and how to fix it**. For example, instead of:

```text
Invalid annotation
```

use a message like:

```text
[NAME001] @CheckedName.value must not be blank; provide a non-empty name
```

The demo uses short strings with stable codes `[NAME001]`, `[NAME002]`, `[NAME000]`. These codes help users look up documentation, write less language-dependent unit tests, and distinguish processor errors from `javac` errors.

Recommendations:

1. Each validation kind has **a stable diagnostic code** and consistent severity.
2. Attach diagnostics to the location **most directly fixable**.
3. Do not display unnecessary sensitive data in messages, especially annotation values containing internal configuration.
4. Distinguish mandatory rules from advice, avoiding `ERROR` for stylistic preferences.
5. Suggest concrete actions: “provide non-empty value”, “use supported enum”, “add missing method”, instead of generic notices.
6. For complex processors, use a message catalog if multi-language support is needed; Java API `ProcessingEnvironment.getLocale()` can support localization policies when provided by the environment.

**Do not promise stable line/column numbers or compiler wording** across every JVM. What can be kept stable by processor design are diagnostic codes, trigger conditions, and relationships to the inspected elements/values.

## 15. Writing tests for diagnostic locations and severities

There are two complementary test layers:

### Integration tests with javac (like the lab)

- **Error case:** `Cases.java` produces `1 error`, `1 warning`, and `1 Note`; non-zero exit code.
- **Warning-only case:** `Warning.java` produces a warning; exit code 0.
- **Note-only case:** `Good.java` produces a note; exit code 0.
- **Warning with `-Werror` case:** `Warning.java` now makes the build fail.
- **Location check:** on standard `javac` in the experiment, the `^` caret of error/warning points right at the value, while note points at the annotation.

In PowerShell, read **`$LASTEXITCODE` immediately after running `javac`**:

```powershell
javac --release 17 -cp out/processor -processorpath out/processor -processor diagnostics.NameProcessor -proc:only examples/Cases.java
$LASTEXITCODE
```

For instance, `Cases.java` returned `1` in the verification run. In Bash/zsh, `echo $?` immediately after `javac` provides the status. Read the exit code before running another command to avoid capturing the wrong status.

**Do not assume “warnings are errors”** when the quality gate is not enabled. Having output with one warning yet exit code 0 is completely normal under default compiler mode.

### Testing via Java Compiler API

Unit testing tools can use:

```java
javax.tools.DiagnosticCollector<
        javax.tools.JavaFileObject> diagnostics =
        new javax.tools.DiagnosticCollector<>();
```

This is an **illustrative snippet declaring a collector**, not a complete test program. `JavaCompiler.getTask(...)` can accept a `DiagnosticListener`; after compilation, tests can iterate `diagnostics.getDiagnostics()` to verify:

- Whether `diagnostic.getKind()` is the expected `ERROR`/`WARNING`/`NOTE`.
- Whether the message contains code `[NAME001]` or `[NAME002]`.
- Whether source and position are supplied when supported by the environment.
- Whether the boolean compilation result matches the test case.

If the processor runs in an existing JVM via the Java Compiler API, configuring the processor instance/path may differ from standalone `javac` commands. Do not assert that every `-processorpath` command-line option is passed through the exact same channel across all build tools.

When verifying positions, check **presence of source and belonging to the annotation region** rather than hardcoding exact column numbers across every compiler version. That produces a less brittle test.

## 16. Checklist before publishing an annotation processor

- [ ] Validation rules distinguish **mandatory** and **recommended**.
- [ ] `ERROR` is used when source is genuinely invalid per the processor contract.
- [ ] `WARNING` is used when the build can continue; interaction with `-Werror` has been verified.
- [ ] Every diagnostic carries a code and concrete remediation message.
- [ ] Diagnostics belonging to class/field/method are attached to the right `Element`.
- [ ] Diagnostics belonging to an annotation are attached to the right `AnnotationMirror`.
- [ ] Diagnostics belonging to an annotation attribute are attached to the right `AnnotationValue` when appropriate source exists.
- [ ] Checked both **explicitly specified** values and **default** values if the contract requires.
- [ ] Do not produce meaningless duplicate diagnostics across multiple processing rounds.
- [ ] Processor declares `@SupportedAnnotationTypes` and supported source version accurately.
- [ ] Build/test records JDK version, classpath/processor path, annotation processing mode, and exit code.
- [ ] Error, warning, and success examples are all tested with independent sources.
- [ ] Do not use `throw` or `println` as the primary reporting mechanism for user validation errors.

## 17. Exercises with answers

**Exercise 1: Choosing the overload for a value error**

You have `@Range(min = -2)` on a method, and the rule requires `min >= 0`. Where should the diagnostic be attached?

**Answer:** Use the overload with the method's `Element`, `@Range`'s `AnnotationMirror`, and `min = -2`'s `AnnotationValue`. If `min` was omitted and an invalid default was taken, attaching to the mirror/element can be more helpful since there is no token position for that value at the annotation use.

**Exercise 2: Can printing to console make the compiler treat it as an error?**

A processor calls `System.err.println("Error")` without emitting a diagnostic. Does the compiler automatically return a failed exit code?

**Answer:** No. A console text line is not `Diagnostic.Kind.ERROR`. Use `Messager.printMessage(ERROR, ...)` so the compiler receives structured errors.

**Exercise 3: Does return true make the build pass?**

A processor emits an `ERROR` and then returns `true`. Does the build succeed?

**Answer:** No, `true` only claims annotation types; `ERROR` still causes compilation to fail.

**Exercise 4: Warnings and -Werror**

A processor emits only a `WARNING`. In default mode, can compilation succeed? What about with `-Werror`?

**Answer:** It can succeed when there are no other errors. When `-Werror` applies, the warning causes the compiler to fail the build under that policy.

**Exercise 5: Annotation defaults**

`@Threshold` omits `min() default 0`. Does `getElementValues()` always return `min=0`?

**Answer:** No; `getElementValues()` returns only explicitly supplied members. Use `Elements.getElementValuesWithDefaults(...)` to include defaults.

**Exercise 6: Duplicate diagnostics**

A processor re-emits the same `ERROR` for a class across two rounds. Does this make compilation fail more reliably?

**Answer:** No. A single error already takes effect; repeating creates noise. Clarify processing rounds, element sets, and deduplication rules.

**Exercise 7: Severity and location of NOTE**

The program `Good.java` only produces a `NOTE` at `@CheckedName("Customer")`. Why is there no class file after compilation?

**Answer:** Because the test command used `-proc:only`, not because of `NOTE`. Remove `-proc:only` and compile normally if you want class files generated.

## 18. Summary and authoritative references

`Messager` enables annotation processors to report **errors/warnings/information** through the compiler's official diagnostic system. The overloads accepting `Element`, `AnnotationMirror`, and `AnnotationValue` are essential for **attaching diagnostics to the exact spot users need to fix**, rather than emitting a single contextless log line. The `ERROR`/`WARNING`/`NOTE` levels determine how the compiler and build tools respond; they are **not controlled by the return value of `process(...)`**.

References:

1. [Java SE 17 — javax.annotation.processing.Messager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Messager.html): four overloads, location hints, error/warning/note levels.
2. [Java SE 17 — javax.tools.Diagnostic.Kind](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.Kind.html): diagnostic kinds.
3. [Java SE 17 — javax.annotation.processing.RoundEnvironment](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): elements per round, `processingOver`, `errorRaised`.
4. [Java SE 17 — javax.lang.model.element.AnnotationMirror](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/AnnotationMirror.html): reading the annotation model and explicitly declared values.
5. [Java SE 17 — javax.lang.model.util.Elements](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Elements.html): `getElementValuesWithDefaults`.
6. [JDK 17 — javac command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `-processor`, `-processorpath`, `-proc:only`, `-Werror`, and compile configuration.

**Mindset to remember:** when detecting a violation, determine the **severity** first (`ERROR` or `WARNING`), determine the **offending target** next (`Element`, annotation, or value), and pass both pieces of information to `Messager`. A quality processor not only knows source code is wrong, but helps users pinpoint **exactly where to fix and why**.
