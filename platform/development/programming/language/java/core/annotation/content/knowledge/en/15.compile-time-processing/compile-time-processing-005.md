# RoundEnvironment: Root Elements and Annotated Elements in Compile-Time Annotation Processing

When writing an **annotation processor** in Java, the challenge is not only reading an annotation, but also understanding **the data scope of each processing round**. Java provides the `javax.annotation.processing.RoundEnvironment` interface for that purpose. Two very important APIs are:

- `roundEnv.getRootElements()` — the set of **root elements** passed into the **current processing round**.
- `roundEnv.getElementsAnnotatedWith(...)` — the set of **elements with a specific annotation** within the scope that Java allows inspecting in the current round, including members inside the included types; not only root elements.

For example, a source file has a class `Account` and a method `validate()` annotated with `@Tracked`. `Account` is a root type, but `validate()` is only a method inside the class: **`validate()` is not in `getRootElements()`**. However, `getElementsAnnotatedWith(Tracked.class)` can return **both `Account` and `validate()`** if both are annotated with `@Tracked`.

A processor can generate new source in the current round. The generated source can become a root in the **next round**. Therefore, the data returned by `RoundEnvironment` is **not a snapshot of the entire project at all times**, but rather a per-round view of compilation.

## 1. Context: Annotation Processing Differs from Runtime Reflection

Annotation processing runs at **compile time**, based on APIs in the `java.compiler` module, in particular:

| Component | Role |
|---|---|
| `Processor` / `AbstractProcessor` | Contract and base class for implementing an annotation processor |
| `ProcessingEnvironment` | Provides `Filer`, `Messager`, `Elements`, `Types`, and processing configuration |
| `RoundEnvironment` | Provides data and status of the **current round** |
| `Element` | Models a Java declaration: class, method, field, parameter, package, module... |
| `TypeElement` | An `Element` representing a type declaration, including class/interface/annotation interface |
| `AnnotationMirror` | Models an annotation usage in compiler data |
| `Filer` | Creates source, class files, or resources according to the annotation processing contract |
| `Messager` | Emits notes/warnings/errors at declaration locations while the compiler is processing |

Reading annotations with `Class.getAnnotation(...)` at runtime is **not the same as** reading them via `Element`, `AnnotationMirror`, and `RoundEnvironment`. For example, an annotation with `SOURCE` retention can be seen by the processor during source compilation, even though that annotation usage is omitted from the class file and cannot be read with runtime reflection.

A processor is typically invoked following this pattern:

```java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {
    // Process the data provided by the compiler for this round
    return true;
}
```

This is a **method override inside a processor**, not a standalone Java program. The two parameters differ:

- `annotations`: the annotation types **requested for this processor to handle in that round**, according to the processor selection rules.
- `roundEnv`: the environment for querying roots, annotated elements, and round status.

Do not confuse `annotations` with the list of all annotations used by every element in the source. Similarly, `roundEnv.getRootElements()` is not a list of “every class already on the classpath”.

## 2. getRootElements(): What Is a Root Element?

API:

```java
Set<? extends Element> roots = roundEnv.getRootElements();
```

Returns the set of root elements for annotation processing in the **currently running round**. For a typical Java compiler, roots are usually the **top-level declarations** of a compilation unit, for example:

```java
// File Order.java
@Tracked
class Order {
    @Tracked
    void validate() {}
}

class Supplier {}
```

If this file is among the source inputs of the first round, the root types passed in are typically:

```text
Order
Supplier
```

**`validate()` is not a root:** it is a member element declared **inside** `Order`. Having `@Tracked` on the method does not turn it into a root.

A root type may **not be annotated** with any annotation. `Supplier` in this example can still be a root. Conversely, an annotated method located inside a root type **does not become a root**.

Points to remember:

- A root is an element passed into the processing round by the compiler, **not necessarily an annotated element**.
- Roots are usually top-level type declarations, but the API can also include package or module elements in the corresponding circumstances.
- In subsequent rounds, roots may come from **source/class files generated in the previous round**.
- `getRootElements()` returns a `Set`; **there is no contract guaranteeing iteration order**. If the problem requires stable output, you must sort explicitly.
- There is no promise that every call has roots: the final round or a scenario with no new data may return an empty set.

In large projects, do not assume “each file is one root” or “every class in the same package is a root”. A compilation unit can contain multiple top-level declarations; nor are roots simply inferred from the file name.

## 3. getElementsAnnotatedWith(): Finding Annotated Declarations

`RoundEnvironment` has important overloads:

```java
Set<? extends Element> a = roundEnv.getElementsAnnotatedWith(Tracked.class);
Set<? extends Element> b = roundEnv.getElementsAnnotatedWith(
        trackedTypeElement);
```

In the example above, `trackedTypeElement` is a variable of type `TypeElement` representing the **`Tracked` annotation definition**, which can be obtained via `Elements.getTypeElement(...)` or the `annotations` parameter of `process`.

Given a class with a method annotated with the same annotation:

```java
@Tracked
class Order {
    @Tracked
    void validate() {}

    void calculate() {}
}

class Supplier {}
```

We can observe:

| Query | Example Returned Elements |
|---|---|
| `getRootElements()` | `Order`, `Supplier` |
| `getElementsAnnotatedWith(Tracked.class)` | `Order`, `validate()` |
| Does `getElementsAnnotatedWith(...)` find `calculate()`? | No, because this method is not annotated with `@Tracked` |

This is very important: `getElementsAnnotatedWith` is designed to **find elements that have an annotation**, rather than merely filtering top-level roots. The API inspects the elements included in the round: root types, nested member types, and member declarations, constructors, parameters, type parameters, or record components belonging to those qualifying elements, according to the rules of the Java 17 Javadoc. It also inspects package/module elements when within the corresponding processing scope.

**Scope limitation:** it does not automatically traverse the entire Java classpath or every dependency JAR. A type that merely happens to be referenced by a root does not automatically become an element in the set being processed. To inspect a type outside the round's scope, you must proactively look it up using the appropriate modeling APIs; do not use `getElementsAnnotatedWith` as a project-wide search tool.

### There Are Two Overloads: TypeElement and Class

**Using `TypeElement`:**

```java
TypeElement marker = processingEnv.getElementUtils()
        .getTypeElement("org.example.Tracked");

if (marker != null) {
    Set<? extends Element> matches =
            roundEnv.getElementsAnnotatedWith(marker);
}
```

This is an *illustrative snippet inside a processor*; it requires the corresponding imports and an actual annotation named `org.example.Tracked`. Replace that name with the fully qualified name in your project. This approach is especially useful when the annotation to analyze is provided as a compiler model, rather than having processor code load the annotation class at runtime.

**Using `Class<? extends Annotation>`:**

```java
Set<? extends Element> matches =
        roundEnv.getElementsAnnotatedWith(Tracked.class);
```

Simple when the processor has a dependency containing `Tracked` and that class is loaded properly in the processor's runtime environment. The Javadoc notes that the runtime `Class` model and the internal type model in the compiler can differ in some classloader/processing-environment situations. If the annotation class is not in the appropriate processing environment, the result is not necessarily an error but may be no matching elements. With large tooling, `TypeElement`/`AnnotationMirror` is usually a better way to decouple from runtime class dependencies.

If you pass a `TypeElement` that does not represent an annotation type to the corresponding overload, the API may throw `IllegalArgumentException`. A `TypeElement` representing a regular class cannot substitute for an annotation type.

## 4. Processing Rounds: Why Can't Results Be Treated as Immutable Across the Entire Process?

Annotation processing runs in **a sequence of processing rounds**. In the first round, the compiler processes the initial inputs. If a processor creates additional source/class files, the new elements can be passed into the next round. At the final round, the compiler invokes the processor with the completion state.

Simplified model:

```text
Input sources: Example.java
          |
          v
Round 1
  roots: Example, Plain
  marked: @Tracked Example, @Tracked Example.run()
  Processor creates GeneratedTask.java
          |
          v
Round 2
  roots: GeneratedTask
  marked: @Tracked GeneratedTask
  No additional source generated
          |
          v
Round 3 (final)
  processingOver = true
  roots: empty
  marked: empty
          |
          v
Annotation processing ends
```

This is an illustration based on a specific experiment in Section 5; the actual number of rounds depends on the inputs and the generated files. **Each round has its own set of roots and its own set of annotated elements**. Do not just save `getRootElements()` from the first round and assume it already includes every class the processor creates later.

A processor should also not call `process(...)` itself to create a new round; **the compiler tool** manages rounds. Generating source/class files through `Filer` is one of the reasons a subsequent round is set up.

## 5. Runnable Java 17 Experiment: Printing Roots, Marked Elements, and Creating the Next Round

This experiment consists of **three input source files** placed in the same directory. To keep the commands short and make element names clearly visible, the example uses the *default package*. In a real project, use a named package and configure a fully qualified annotation type.

### File 1: Tracked.java

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.SOURCE)
@Target({ElementType.TYPE, ElementType.METHOD})
public @interface Tracked {}
```

- `@Retention(SOURCE)` allows the annotation to be seen during source code processing, but the `@Tracked` usage is not retained in the built bytecode.
- `@Target({TYPE, METHOD})` allows annotating classes and methods; therefore the experiment can demonstrate that a method is included in the set of **annotated elements**, even though it is not a root.

### File 2: RoundDemoProcessor.java

```java
import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import java.util.stream.Collectors;
import javax.annotation.processing.*;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.*;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("Tracked")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class RoundDemoProcessor extends AbstractProcessor {
    private int round = 0;
    private boolean created = false;

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment env) {
        round++;

        String roots = env.getRootElements().stream()
                .map(e -> e.getSimpleName().toString())
                .sorted().collect(Collectors.joining(","));

        String marked = env.getElementsAnnotatedWith(Tracked.class).stream()
                .map(e -> e.getKind() + ":" + e.getSimpleName())
                .sorted().collect(Collectors.joining(","));

        System.out.println("round=" + round
                + " over=" + env.processingOver()
                + " errorRaised=" + env.errorRaised());
        System.out.println("roots=[" + roots + "]");
        System.out.println("marked=[" + marked + "]");

        if (!env.processingOver() && !created) {
            created = true;
            try {
                JavaFileObject file = processingEnv.getFiler()
                        .createSourceFile("GeneratedTask");
                try (Writer writer = file.openWriter()) {
                    writer.write("@Tracked class GeneratedTask {}\n");
                }
            } catch (IOException ex) {
                throw new IllegalStateException(ex);
            }
        }
        return true;
    }
}
```

Analysis of the key parts:

1. `@SupportedAnnotationTypes("Tracked")` declares that the processor wants to process the `Tracked` annotation. In an application with packages, you need to use the exact name according to the mechanism for declaring supported annotation types.
2. `@SupportedSourceVersion(RELEASE_17)` declares the source version supported by the processor in the example.
3. `getRootElements()` returns the root set of the **current round**. We take `getSimpleName()` for display.
4. `getElementsAnnotatedWith(Tracked.class)` returns the elements with `@Tracked` in the round; `getKind()` helps distinguish `CLASS` from `METHOD`.
5. Both sets are `sorted()` to **stabilize the printed output**, because a `Set` has no guaranteed order.
6. `created` prevents creating `GeneratedTask.java` multiple times. `Filer` is not an API for writing the same file name over and over every round.
7. `createSourceFile(...)` combined with `openWriter()` writes a new Java source file. The processor generates a class with `@Tracked` to prove it will be found in the next round.
8. `return true` means the processor declares it has handled (*claims*) the annotation types assigned to it in the round according to Java rules. It does not mean every annotation present in the entire project has been processed, and it does not control whether there is a next round.
9. The code only prints information via `System.out` to learn the mechanism. A real processor should use `Messager` to report diagnostics with a source location.

### File 3: Example.java

```java
@Tracked
class Example {
    @Tracked
    void run() {}
}

class Plain {}
```

`Example` is a top-level class with `@Tracked`. `run()` is a method with `@Tracked`. `Plain` is a top-level class **without** the `Tracked` annotation.

### Compiling and Running the Processor

In the directory containing the three files, first compile the annotation definition and the processor:

```bash
javac --release 17 Tracked.java RoundDemoProcessor.java
```

Then invoke the processor **explicitly** to process the source being studied:

```bash
javac --release 17 -cp . -processorpath . -processor RoundDemoProcessor Example.java
```

Exact output in the Java 17 experiment:

```text
round=1 over=false errorRaised=false
roots=[Example,Plain]
marked=[CLASS:Example,METHOD:run]
round=2 over=false errorRaised=false
roots=[GeneratedTask]
marked=[CLASS:GeneratedTask]
round=3 over=true errorRaised=false
roots=[]
marked=[]
```

**Why three rounds?**

- **Round 1:** `Example` and `Plain` are the initial roots. `getElementsAnnotatedWith` sees `Example` and the `run` method, and does not see `Plain`. The processor creates the `GeneratedTask.java` file.
- **Round 2:** the compiler brings the new type `GeneratedTask` into the round; because `GeneratedTask` is annotated with `@Tracked`, it is present in both `roots` and `marked`. The processor does not create more source because the `created` flag is already set.
- **Round 3:** the final processing round has `processingOver() == true` and no new roots in the experiment. At this point, `roundEnv.getRootElements()` and `getElementsAnnotatedWith(...)` both return empty sets.
- `errorRaised()` in all three rounds is `false` because there were no error-kind diagnostics in the preceding rounds.

The line count and result order were intentionally stabilized by sorting in the code. However, a project with other processors, different input sources, or additional generated sources may have **different rounds and element sets**. The output above is the result of those exact three files and illustrative commands.

Key takeaway: **getRootElements finds roots, getElementsAnnotatedWith finds annotated declarations; both apply only to the round currently being processed.**

## 6. Does getRootElements Include All Nested Elements?

No. `Element` forms a hierarchical structure. From a class's `TypeElement`, you can call `getEnclosedElements()` to see the members declared directly inside it:

```java
for (Element root : roundEnv.getRootElements()) {
    System.out.println("ROOT " + root.getSimpleName());

    for (Element enclosed : root.getEnclosedElements()) {
        System.out.println("  CHILD " + enclosed.getKind()
                + " " + enclosed.getSimpleName());
    }
}
```

This is a snippet **located inside a processor method** where a valid `roundEnv` variable is available and `Element` is imported. It traverses **one level of nested declarations**, rather than automatically walking deep into the entire tree. If recursion is needed, you can traverse `getEnclosedElements()` or use an `ElementScanner` in `javax.lang.model.util`.

Notes:

- `getRootElements()` does not return all members in a flattened form.
- `getEnclosedElements()` retrieves the **declarations enclosed within** an element without automatically determining whether they have the annotation being searched for.
- For the task of “finding `@Tracked` within the round scope”, `getElementsAnnotatedWith(Tracked.class)` is usually shorter and less error-prone than traversing the tree manually.
- If the requirement is to inspect every member or enforce special rules not based solely on a single annotation, traversing the element tree is the useful approach.

Example with a class containing a nested class:

```java
class Container {
    @Tracked
    static class Nested {}

    @Tracked
    void run() {}
}
```

`Container` is a top-level root when this source belongs to the round. `Nested` is a member type; `run` is a member method. They **do not become independent roots** merely because they are annotated. However, when located inside types that the API considers *included* in the round, they can appear in `getElementsAnnotatedWith(Tracked.class)`.

## 7. processingOver and errorRaised: Different Meanings

`RoundEnvironment` provides two status checks:

```java
boolean over = roundEnv.processingOver();
boolean hadErrors = roundEnv.errorRaised();
```

| API | What It Actually Answers |
|---|---|
| `processingOver()` | Is this round the final round, meaning types generated in this round will **not be processed in a subsequent round**? |
| `errorRaised()` | Was an error-kind diagnostic raised in the **previous round**? |

**Do not confuse round status with error status.** `processingOver() == true` does not mean compilation failed. In the experiment that was run, the final round had `over=true` and `errorRaised=false`.

A common pattern:

```java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {

    if (roundEnv.processingOver()) {
        // Finalize statistics/state; do not attempt to generate more sources
        return true;
    }

    for (Element element
            : roundEnv.getElementsAnnotatedWith(Tracked.class)) {
        // Process the annotated elements of this round
    }
    return true;
}
```

The snippet above is an illustration inside a processor; in a real example, you need to use the annotation name supported by the processor. Tasks that generate additional source files should be performed in a **non-final** round; do not expect a file created in the final round to be carried by the compiler into a new round.

`errorRaised` reflects the **prior round** state, so `errorRaised() == false` should not be interpreted as a guarantee that the entire compilation will definitely succeed afterward. A processor can use `Messager` to emit an error during the current round itself; that information will affect subsequent processing steps.

When errors occur, let the compiler tool decide subsequent rounds according to the contract; do not hardcode your program around the assumption that “every run has exactly three rounds”.

## 8. Why Is GeneratedTask Not in getRootElements of the First Round?

In the experiment, the processor writes:

```java
JavaFileObject file = processingEnv.getFiler()
        .createSourceFile("GeneratedTask");

try (Writer writer = file.openWriter()) {
    writer.write("@Tracked class GeneratedTask {}\n");
}
```

This file is **not an initial input of the first round**. It is created while the processor is in Round 1, so it is picked up by the compiler for processing in Round 2.

Consequence:

- **Round 1:** `roots=[Example,Plain]`; `GeneratedTask` is not yet in the round's root set.
- **Round 2:** `roots=[GeneratedTask]`, because this is a new type generated by the previous round.
- **Round 3:** there are no new types, so `roots=[]` in the experiment.

Do not interpret `getRootElements()` as “every type ever seen”. If you want to accumulate results across multiple rounds, the processor must deliberately manage its own aggregated data:

```java
private final Set<String> processedNames = new java.util.TreeSet<>();

@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {
    if (!roundEnv.processingOver()) {
        for (Element element
                : roundEnv.getElementsAnnotatedWith(Tracked.class)) {
            processedNames.add(element.toString());
        }
    }
    return true;
}
```

This is an **illustrative snippet inside a processor**, not standalone; it requires importing `Set`, `TypeElement`, `RoundEnvironment`, and `Element`. The processor instance's `processedNames` set can accumulate names across rounds. In a real implementation, if you need an identity that distinguishes overloads/methods with the same name, storing only `element.toString()` may not suffice; design a stable key including element kind, owner/type, and signature when appropriate.

Do not retain references to `RoundEnvironment` or `Element` for arbitrary use outside a processing round or after compilation finishes; those are objects provided within the compiler context. It is usually better to extract the necessary information and store it in your own model.

## 9. How Does the annotations Set Passed to process Differ from the Marked Set?

Each invocation:

```java
boolean process(
    Set<? extends TypeElement> annotations,
    RoundEnvironment roundEnv)
```

has **two sets of data answering two questions**:

| Data | Question |
|---|---|
| `annotations` | Which **annotation types** are assigned by the compiler for this processor to handle in the round? |
| `roundEnv.getElementsAnnotatedWith(Tracked.class)` | Which **declared elements** within the round scope have `@Tracked`? |

For example, `annotations` may contain `Tracked` (a `TypeElement`), whereas `getElementsAnnotatedWith(Tracked.class)` may contain `Example` and `run()` (two `Element`s carrying the annotation). Confusing the `TypeElement` representing the annotation *type* with the `Element` representing the *annotated* declaration can easily lead to mistakenly processing the class instead of the method.

In a processor supporting multiple annotations:

```java
@SupportedAnnotationTypes({
    "org.example.Command",
    "org.example.Query"
})
public class RouterProcessor extends AbstractProcessor {
    // ...
}
```

You can iterate over the `TypeElement`s in `annotations` and call `getElementsAnnotatedWith(annotationType)` for each type, if that fits your design. This is an **illustrative configuration pattern**, not a standalone snippet; the package and both annotations must actually exist when implemented.

`return true` indicates that the processor **claims** the received annotation types. `return false` allows other processors an opportunity to handle them according to the compiler's rules. The return value is not a “processing succeeded without errors” condition, nor does it guarantee there will be no new processing round if source files are generated.

## 10. Non-Type Elements: Method, Field, Parameter, Constructor, Record Component

In Java, annotations can be placed on many kinds of declarations depending on `@Target`. A processor may need to handle the exact element kind, for example allowing `@Tracked` only on methods.

Suppose an annotation is allowed on methods:

```java
import java.lang.annotation.*;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.SOURCE)
@interface Handler {}

class PaymentService {
    @Handler
    void pay() {}
}
```

The processor can filter:

```java
for (Element e : roundEnv.getElementsAnnotatedWith(Handler.class)) {
    if (e.getKind() != ElementKind.METHOD) {
        continue;
    }
    ExecutableElement method = (ExecutableElement) e;
    System.out.println(method.getSimpleName());
}
```

This is illustrative code inside `process`, with `ElementKind`, `ExecutableElement`, and `Handler` validly imported/declared. `pay()` is not a root, but it can be returned by `getElementsAnnotatedWith` because it is an annotated declaration located inside a type of the round.

Similarly:

- `ElementKind.FIELD`: field declaration.
- `ElementKind.CONSTRUCTOR`: constructor declaration.
- `ElementKind.PARAMETER`: method/constructor parameter.
- `ElementKind.TYPE_PARAMETER`: type parameter declaration.
- `ElementKind.RECORD_COMPONENT`: record component (supported in Java 17).

You cannot cast every `Element` to `TypeElement`. Check `getKind()` or `instanceof` and use the appropriate modeling interface: `TypeElement` for types; `ExecutableElement` for methods/constructors; `VariableElement` for fields/parameters; `RecordComponentElement` for record components.

Some annotations are **type-use** rather than **declaration** annotations. For example, `List<@NonNull String>` is an annotation on a type argument; do not assume every type-use annotation becomes a separate `Element` in `getElementsAnnotatedWith`. When you need to analyze annotated types, work with the `TypeMirror` and `AnnotationMirror` models of those types, rather than scanning declarations alone.

## 11. Extended Characteristics: @Inherited and Repeatable Annotations

**Annotations with `@Inherited`:** The Java 17 Javadoc clearly states that `getElementsAnnotatedWith(...)` can return elements that are annotated **directly or via inheritance**. Therefore, this API should not be defined as “only source lines that have `@X` directly before the declaration”. When you need to distinguish declared annotations from inherited behavior, you must consider the `@Inherited` rules along with the corresponding compiler model.

Note that `@Inherited` is scoped to **inheritance along a class's superclass**, and does not mean every method override or interface implementation automatically inherits annotations. Whether a type counts as *included in the round* remains a condition of `RoundEnvironment`; `@Inherited` does not make a distant type on the classpath automatically appear in every round.

**Repeatable annotations:** if `@Tag` is declared with `@Repeatable(Tags.class)`, it can appear multiple times on the same declaration. Java 17's `RoundEnvironment` provides the APIs:

```java
getElementsAnnotatedWithAny(TypeElement... annotations)
getElementsAnnotatedWithAny(
    Set<Class<? extends Annotation>> annotations)
```

These two overloads return the set of elements annotated with **at least one** of the provided annotation types. The Javadoc explicitly notes that they can be useful when handling repeating annotations and container annotations together. Accordingly, if you design a processor for repeatable annotations, you need to account for both `Tag` and `Tags` rather than assuming a single lookup for `Tag` will fully represent all container structures in every compilation form.

The “Any” APIs use **union-of-element-sets** semantics, rather than returning a list with each annotation occurrence matching the exact number of times the annotation was written. If you want to read each `Tag` instance along with its values, the processor also needs to use `getAnnotationMirrors()` or the appropriate API on the element, according to how repeatable annotations are expanded.

## 12. Example: Processing Markers from Source vs. Compiled Inputs

When looking directly at annotations on source code, a processor can read a SOURCE-retention annotation because it exists in the source code currently being processed. However, when a project later receives only **a compiled class/JAR file**, the SOURCE annotation usage is no longer in the binary.

That creates a difference:

| Scenario | What Is Observed |
|---|---|
| Compiling `Example.java` with SOURCE `@Tracked` and the corresponding processor | The processor can see `@Tracked` in the current round |
| Running `javap -v Example` after compilation | The SOURCE annotation is not stored on `Example.class` |
| Another project adds only `Example.class` to the classpath and runs the processor on a different file | The processor cannot reconstruct `@Tracked` on `Example` from the binary |
| The processor creates `GeneratedTask.java` with `@Tracked` in round 1 | The compiler can pass `GeneratedTask` into round 2, and the processor sees the SOURCE annotation on the new source |

Choose the retention policy and build flow appropriate for where the annotation needs to be consumed. `RoundEnvironment` is a compile-time API, yet it cannot reverse a retention decision if metadata has already been stripped from an input binary.

## 13. Common Mistakes When Using RoundEnvironment

### Mistake 1 — Iterating Over Roots and Assuming You Have Every Annotated Method

```java
for (Element element : roundEnv.getRootElements()) {
    if (element.getAnnotation(Tracked.class) != null) {
        // Detects only annotated roots
    }
}
```

The snippet above does **not** automatically find `@Tracked` on `run()`. If you need all annotated declarations and the API supports that kind, use `getElementsAnnotatedWith(Tracked.class)`. Or implement a proper recursive scan over the element tree if you need more custom logic.

### Mistake 2 — Using getRootElements to Scan Every Type in Dependencies

The API only covers roots in the processing round, not the entire classpath. To look up a type by name, use `Elements.getTypeElement(...)` and analyze the type's structure if the tool truly needs it.

### Mistake 3 — Assuming Every Round Has the Same List of Elements

Rounds change as additional sources are generated. A processor needs to handle the **current round** and manage state explicitly if it must aggregate full information. Do not conclude everything was processed in Round 1 merely because one scan succeeded.

### Mistake 4 — Generating the Same File in Every Round

```java
// Incorrect workflow if executed repeatedly on every round:
processingEnv.getFiler().createSourceFile("GeneratedTask");
```

`Filer` does not allow a processor to recreate the same pathname multiple times within a single processing run. Check a file-generation flag, input type, and creation conditions, or follow a rule to generate only when needed.

### Mistake 5 — Generating Code When processingOver=true and Expecting Another Round

`processingOver()` confirms the final round; types created in that round **are not processed by a subsequent round**. Reserve finalization actions that do not require processing new types for the final round.

### Mistake 6 — Confusing errorRaised with “Whether the Current Round Has Errors”

`errorRaised()` reflects errors from the **previous round**. Errors arising in the current round may be reported by the compiler after the processor runs; do not use false as a guarantee that the whole compilation is safe.

### Mistake 7 — Expecting Set Order to Match Source Order

`Set<? extends Element>` does not guarantee an order meaningful for business logic or stdout. If order matters, sort by a meaningful key and check for declarations with duplicate names.

### Mistake 8 — Confusing Class with TypeElement

When using the `getElementsAnnotatedWith(Class<? extends Annotation>)` overload, the annotation class must be present in the processor's runtime context. When flexibility with the compiler model is needed, use the `TypeElement` overload and the annotation's fully qualified name, avoiding unnecessary classloader dependencies.

### Mistake 9 — Using Only getElementsAnnotatedWith to Analyze Type-Use Annotations

Type-use metadata sits on **type usage** sites and does not necessarily become a declaration `Element`. To inspect `List<@NonNull String>` or complex return types, analyze `TypeMirror`/`AnnotationMirror` instead of expecting to find an element via a marker on a type argument.

### Mistake 10 — Treating return true as Stopping the Compiler or Guaranteeing Build Success

`return true` means claiming the annotation types in the round under the processor selection policy. It does not make the compiler ignore type errors and does not prevent generated source from triggering a new round. To report a violation, use `Messager.printMessage(Diagnostic.Kind.ERROR, ...)`.

## 14. Workflow for Designing a Reliable Processor

When creating a new processor, you can follow this workflow:

1. **Define the annotation with clear target and retention:** should it apply to a class, method, or which element? Does the compiler need to read SOURCE?
2. **Register the supported annotation types:** `@SupportedAnnotationTypes(...)` or override `getSupportedAnnotationTypes()`; if multiple processors process together, clarify the claim semantics.
3. **Determine the input set:** use `getElementsAnnotatedWith` when you only care about annotated declarations, or use roots and traverse the tree when global rules are needed.
4. **Check kind/type:** do not unconditionally cast to `TypeElement`. Extract data from `Element`, `ExecutableElement`, and `TypeMirror` as needed.
5. **Distinguish rounds:** create files only if needed, ensure there are no duplicate names, and do not treat the final round as a place to generate source for a next round.
6. **Emit errors at the right location:** use `Messager` to attach diagnostics to an `Element`. Use `System.out` only for observation examples and simple debugging.
7. **Design information accumulation if needed:** for example, indexing annotated elements across multiple rounds, handling duplicates, and ensuring deterministic output.
8. **Test both initial source and generated source:** check Round 1, Round 2, the final round, methods nested inside a root, unannotated roots, errors, and compilation behavior.
9. **Integrate properly into the build:** the processor must be discovered or explicitly invoked; adding only the annotation JAR does not guarantee the processor runs. With multiple modules/packages, maintain the proper processor path and annotation classpath.
10. **Measure quality using real compilation results:** ensure valid code passes, invalid code produces meaningful diagnostics, and generated files exist properly without duplication.

A robust processor is one that clearly understands **which processing round elements belong to** and **its own annotation rules**, rather than simply looping over roots and assuming everything has been inspected.

## 15. Self-Check Exercises

### Exercise 1 — Roots and Annotated Elements

```java
@Tracked
class Report {
    @Tracked void render() {}
    void save() {}
}

class Plain {}
```

If this source is an input of the first round and `@Tracked` has TYPE/METHOD targets, what do `getRootElements()` and `getElementsAnnotatedWith(Tracked.class)` typically contain?

**Answer:** roots are `Report` and `Plain`; annotated elements include `Report` and the `render()` method. `save()` is not annotated, so it is not in the marked set.

### Exercise 2 — Root Type Without Annotations

Why is `Plain` still in roots even though it does not have `@Tracked`?

**Answer:** roots are determined by the input data of the processing round, not by whether they have the marker annotation being searched for.

### Exercise 3 — Generating Source

The processor generates `@Tracked class GeneratedTask` in Round 1. Which round's roots does this type appear in?

**Answer:** typically **Round 2**, the next round that picks up the generated source. It is not yet in the roots of Round 1.

### Exercise 4 — Final Round

Does `processingOver() == true` imply `errorRaised() == true`?

**Answer:** no. A normal final round can have `processingOver=true` and `errorRaised=false`.

### Exercise 5 — TypeElement and Class

When an annotation is represented by the compiler `TypeElement` model and you do not want to depend on loading the runtime class in the processor, which overload should you call?

**Answer:** `getElementsAnnotatedWith(TypeElement)`, with a `TypeElement` that actually represents the annotation type declaration.

### Exercise 6 — ElementKind

The processor sees `@Tracked` on a method; can it directly cast `(TypeElement) element`?

**Answer:** no. A method is an `ExecutableElement`, typically having `ElementKind.METHOD`. You must check the element kind and use the right interface.

### Exercise 7 — @Inherited

According to the Javadoc, does `getElementsAnnotatedWith` return only directly declared annotations?

**Answer:** not necessarily. It may consider inherited annotations according to Java semantics if the corresponding type is in the round; the class/superclass limitations of `@Inherited` still apply.

### Exercise 8 — Choosing the Right Tool

If you want to detect a `@NonNull` qualifier on the type argument in `List<@NonNull String>`, is calling only `getElementsAnnotatedWith(NonNull.class)` sufficient?

**Answer:** you should not rely on that. This is a type-use annotation; you need to inspect the type model and the annotation mirrors at the exact type location.

### Exercise 9 — Set and Ordering

Why does the example use `sorted()` before printing roots and marked elements?

**Answer:** the returned collection is a `Set`, which does not guarantee iteration order; sorting makes the example's output stable and easy to compare.

### Exercise 10 — Responsibility of Filer

Why does the processor have a `created` flag and check `!env.processingOver()` before calling `createSourceFile`?

**Answer:** to avoid creating duplicate files across multiple rounds and to avoid generating source in a round that no longer processes new types.

## 16. Summary and References

**Three sentences to remember:**

1. `getRootElements()` is the **root elements of the current round**, usually top-level types; **not all members or all dependencies**.
2. `getElementsAnnotatedWith(...)` finds **declarations with the corresponding annotation within the round scope**, including annotated members inside root/nested types; it may also account for inherited annotations according to Java rules.
3. `processingOver()` and `errorRaised()` reflect **processing status**, whereas sources generated by `Filer` can introduce new roots in the **next round**.

Official Java SE 17 documentation:

- [RoundEnvironment](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html) — the `getRootElements`, `getElementsAnnotatedWith`, `getElementsAnnotatedWithAny`, `processingOver`, and `errorRaised` contracts.
- [Processor](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html) — round sequence, annotation type selection/claiming, and the final round.
- [AbstractProcessor](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html) — base class for implementing a processor.
- [Filer](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html) — creating source/class/resource files in annotation processing, and file creation constraints.
- [Element](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/Element.html) — declaration model, kinds, and enclosed elements.
- [javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html) — `-processor` and `-processorpath` when activating a processor.
