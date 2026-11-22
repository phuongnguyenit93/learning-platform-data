# Return Value of `process` and Rules for Claiming Annotation Processing in Java

## 1. Objective: Understanding `true` and `false` in Annotation Processing

In Java, an **annotation processor** is a program invoked by the compiler or build tool to inspect, analyze, or generate files based on annotations at compile time. JSR 269 provides the `javax.annotation.processing.Processor` API; the common way to implement it is by extending `AbstractProcessor`.

A central method:

```java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {
    // Inspect the annotation types assigned in this round.
    return false;
}
```

The boolean value here does **not** answer “whether processing succeeded or not”. It answers the question:

> “Does this processor **claim** (take ownership of processing) the *annotation types* assigned in this invocation?”

- `return true;`: the processor **claims all annotation types in the `annotations` parameter of the invocation**. Processors **after it** in the same round will no longer be assigned those claimed types.
- `return false;`: the processor **does not claim** those types; subsequent processors can still be assigned them if they support them and still match the unclaimed annotation set.

`true` does not prove that the processor successfully processed every element, and `false` does not report a build failure. To report a compilation error, use `Messager.printMessage(Diagnostic.Kind.ERROR, ...)` or a proper error-reporting mechanism.

Two concepts must be kept distinct:

1. **Annotation type:** for example `demo.Trace`, passed as a `TypeElement` in the `annotations` parameter.
2. **Annotated element:** for example, a class `@Trace class Task {}`. To find the annotated elements, call `roundEnv.getElementsAnnotatedWith(Trace.class)` or an appropriate variant.

`process` is called across **multiple processing rounds**, so the meaning of claiming must be understood in the context of **each round and processor order**.

## 2. The `process` Signature and Its Two Parameters

`Processor` declares:

```java
boolean process(
    Set<? extends TypeElement> annotations,
    RoundEnvironment roundEnv
);
```

When extending `AbstractProcessor`, it is typically written as:

```java
@Override
public boolean process(Set<? extends TypeElement> annotations,
                       RoundEnvironment roundEnv) {
    // ...
    return true;
}
```

### The `annotations` Parameter

This is the set of **annotation interfaces (types)** that the tool is **requesting the processor to process in this round**. It is neither a list of every annotation appearing in the project nor a list of all annotated classes.

For example, if the processor supports two types, `demo.Trace` and `demo.Validate`, the `annotations` set may contain only one, both, or be empty. This depends on the annotations currently present, the types already claimed by earlier processors, and the tool's ability to distribute processing.

You should not assume that `annotations.size() == 1` or that the set always has contents. In particular, a processor with `@SupportedAnnotationTypes("*")` can be invoked when this set is empty.

### The `roundEnv` Parameter

`RoundEnvironment` provides contextual information for the processing round:

- `roundEnv.getRootElements()`: the root elements of the current processing round.
- `roundEnv.getElementsAnnotatedWith(Trace.class)`: the matching elements bearing `@Trace` returned by the API in the current round.
- `roundEnv.processingOver()`: `true` when annotation processing has reached the final round.
- `roundEnv.errorRaised()`: indicates whether an error was raised in a previous round, which is useful when handling subsequent rounds.

`roundEnv.getElementsAnnotatedWith(...)` is an operation to find **the elements bearing annotations**; it differs from the set of annotation types passed into `process` by the tool. When you need to work across every type in `annotations`, iterate over the `TypeElement`s and use the appropriate `RoundEnvironment` APIs or `javax.lang.model` model.

## 3. Claim Rules: Who Is Affected by `true` and `false`?

Suppose a round has the annotation type `demo.Trace`. Both processors declare support for `demo.Trace` and are evaluated by the tool in order:

```text
Unclaimed annotation type set: {demo.Trace}
                 │
                 ▼
   Does Processor A support Trace?
                 │ yes
                 ▼
             A.process(...)
                 │
           ┌─────┴─────┐
         false        true
           │             │
    Trace unclaimed     Trace claimed
           │             │
           ▼             ▼
 Processor B can         Processor B is no longer
 be assigned Trace       assigned Trace in that round
```

If `Processor A` returns `false`, `Processor B` can be invoked with `Trace` when the compiler distributes the unclaimed set. If `Processor A` returns `true`, `Processor B` no longer has `Trace` to receive in **that round**.

| First processor | Value from `process` | Status of `demo.Trace` in the same round | Can the next processor receive `Trace`? |
|---|---|---|---|
| A observes metadata | `false` | Unclaimed | Yes |
| A owns the processing | `true` | Claimed | No, because this type is no longer unmatched |
| A returns `true` with two assigned types | `true` | Both assigned types are claimed | Does not receive the claimed types |
| A returns `false` after reporting an error via `Messager` | `false` | Unclaimed | Still possible; error reporting and claiming are two independent axes |

Note the exact scope:

- Claiming applies to **the annotation types assigned by the tool**, not “marking individual classes as inspected”.
- `true` does not modify source code, does not remove annotations from class files, and does not prevent any other tools from reading the metadata at another time.
- A processor running **earlier** that has already been invoked does not have its results “undone” simply because a later processor claims the type.
- A processor may still be called again in **subsequent rounds** if it has participated in processing; claiming in the current round does not automatically disable future invocations.
- If a processor supports multiple annotation types, a `boolean` does not allow claiming only **part of the `annotations` set in a single invocation**. Returning `true` claims the entire received set; to separate processing ownership, you need to design the set of types/processors accordingly.

## 4. `@SupportedAnnotationTypes` Determines Which Types a Processor Cares About

`AbstractProcessor` can declare the annotation types it supports via:

```java
import javax.annotation.processing.SupportedAnnotationTypes;

@SupportedAnnotationTypes("demo.Trace")
public class TraceProcessor extends AbstractProcessor {
    // ...
}
```

This is an illustrative snippet; you still need to declare the class, import `AbstractProcessor`, and override `process` when writing a complete program.

Some valid support patterns:

| Declaration | Meaning |
|---|---|
| `@SupportedAnnotationTypes("demo.Trace")` | Supports the `demo.Trace` type |
| `@SupportedAnnotationTypes({"demo.Trace", "demo.Validate"})` | Supports both types |
| `@SupportedAnnotationTypes("demo.*")` | Supports annotation interfaces whose names match the package/type pattern permitted by Java |
| `@SupportedAnnotationTypes("*")` | Universal processor: supports all annotation interfaces, including an empty set |

Type names must be exact; `"Trace"` does not substitute for `"demo.Trace"` when the type belongs to the `demo` package. The API also allows declaring support by overriding `getSupportedAnnotationTypes()` instead of using the configuration annotation.

Distinguishing between **supporting** and **claiming**:

- `@SupportedAnnotationTypes` determines **which annotation types a processor can be assigned**.
- `process(...): boolean` determines **whether the assigned types are claimed or not**.
- The toolchain also has to **discover/instantiate the processor** from the build configuration; merely declaring `@SupportedAnnotationTypes` does not automatically cause the processor to run.

In a Java module environment, the supported-type declaration syntax can also take a form with a module name prefix where appropriate. For the Java 17 classpath example in this article, use a fully qualified name such as `demo.Trace`.

## 5. Complete Java 17+ Example: One Processor Returns `false`, One Processor Returns `true`

The example set uses **four files** in the `demo` package:

```text
src/
└── demo/
    ├── Trace.java
    ├── Example.java
    ├── ObserveProcessor.java
    └── ClaimProcessor.java
```

When compiling `Example`, both processors support `demo.Trace`. `ObserveProcessor` runs first and **does not claim**, while `ClaimProcessor` runs second and **claims**.

### File 1 — `src/demo/Trace.java`

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface Trace {
    String value();
}
```

`@Trace` serves the compilation phase, so `RetentionPolicy.SOURCE` is chosen. An annotation processor **does not require `RUNTIME`** to process annotations on the source being compiled.

### File 2 — `src/demo/Example.java`

```java
package demo;

@Trace("checkout")
public class Example {
}
```

The `Example` class is annotated with `demo.Trace`. This is the annotation usage that both processors will be assigned in the first round.

### File 3 — `src/demo/ObserveProcessor.java`

```java
package demo;

import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;

@SupportedAnnotationTypes("demo.Trace")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class ObserveProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (!roundEnv.processingOver() && !annotations.isEmpty()) {
            System.out.println("ObserveProcessor: "
                    + annotations.iterator().next().getQualifiedName());
        }

        return false; // Do not claim Trace.
    }
}
```

`ObserveProcessor` prints the annotation type name when requested to process `Trace`; it returns `false` so that a subsequent processor still has the opportunity to access `Trace`.

### File 4 — `src/demo/ClaimProcessor.java`

```java
package demo;

import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;

@SupportedAnnotationTypes("demo.Trace")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class ClaimProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (!roundEnv.processingOver() && !annotations.isEmpty()) {
            System.out.println("ClaimProcessor: "
                    + annotations.iterator().next().getQualifiedName());
        }

        return true; // Claim Trace in the current round.
    }
}
```

### How to Compile and Observe the Result

From the directory containing `src`, run with JDK 17 or newer:

```bash
javac -d out src/demo/Trace.java src/demo/ObserveProcessor.java src/demo/ClaimProcessor.java
javac -cp out -processorpath out -processor demo.ObserveProcessor,demo.ClaimProcessor -d out src/demo/Example.java
```

The first command compiles the annotation type and the two processors. The second command compiles `Example` and **explicitly specifies the processor order**: `ObserveProcessor` then `ClaimProcessor`.

**Stdout from the two processors in the round with the annotation:**

```text
ObserveProcessor: demo.Trace
ClaimProcessor: demo.Trace
```

Why do both lines appear?

1. `javac` finds `@demo.Trace` on `Example`.
2. The processor `ObserveProcessor` supports `demo.Trace` and is invoked first.
3. `ObserveProcessor` returns `false`; `demo.Trace` remains unclaimed.
4. The processor `ClaimProcessor` also supports `demo.Trace`, so it is invoked and prints the second line.
5. `ClaimProcessor` returns `true`, claiming `demo.Trace`; no subsequent processor continues to receive that type in the same round.
6. In the final round, `annotations` is usually empty; the condition in both processors does not print any additional lines.

This is direct output from `System.out.println` inside the processors, not output from a `main` application. Depending on your machine or IDE and how you run it, there may be additional compiler/build information beyond this stdout; the two lines above are what the processors explicitly print.

### Changing the Order to See the Effect of `true`

Run with `ClaimProcessor` first:

```bash
javac -cp out -processorpath out -processor demo.ClaimProcessor,demo.ObserveProcessor -d out src/demo/Example.java
```

**Stdout from the processor for the `Trace` annotation:**

```text
ClaimProcessor: demo.Trace
```

Because `ClaimProcessor` claimed `Trace`, `ObserveProcessor` is not assigned the `Trace` annotation type afterward in that round. However, do not interpret this to mean that `ObserveProcessor` is removed from the build or can never be invoked again: the final processing round and other conditions can still cause a participating processor to be invoked with an empty set of types.

### Turning `Example` into a Standalone Java Program If You Want to Run It

Annotation processing takes place during **compilation** and does not require running `Example`. If you want a `main` method, you can add:

```java
public static void main(String[] args) {
    System.out.println("Example running");
}
```

**inside** the `Example` class, recompile, and then run:

```bash
java -cp out demo.Example
```

Then the application stdout will be exactly:

```text
Example running
```

The `main` snippet above is only an illustrative addition and is not in the original `Example.java` of the compilation example. The two processors do not run again when executing the program via `java`.

## 6. The Same Annotation Type Can Be Examined by Multiple Processors

An annotation type such as `demo.Trace` does not have an immutable “owner” hardcoded by Java. Multiple processors can register support for it at the same time.

Example pipeline:

```text
@Trace on Example.java
        │
        ▼
Processor ValidateTrace
        │  reads metadata, may report errors
        │  process(...) -> false
        ▼
Processor GenerateTraceIndex
        │  reads metadata, may generate files
        │  process(...) -> true
        ▼
Another processor supporting Trace
        └─ is no longer assigned Trace in the same round
```

Returning `false` is useful for **supplementary processors**, such as checking conventions, recording metrics, or observing annotations without wanting to “take” the type away from the main processor. Returning `true` makes sense when a processor actively takes on full processing of the assigned set of annotation types and wants subsequent processors not to compete for processing the same types in that round.

However, this is not a rigid rule that “validators must return false / generators must return true”. A code-generating processor may still return `false` so that other processors can continue operating; a checking processor can also claim a type when it truly owns that type. What matters is the **coordination intent** and the impact on other processors.

Do not expect `true` to protect all side effects. Other processors may have already run earlier; tools that do not participate in the same processing chain can also read the annotations.

## 7. Why Does `true` Not Mean “Processing Succeeded”?

Consider a checking processor:

```java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {

    for (TypeElement annotationType : annotations) {
        for (Element element :
                roundEnv.getElementsAnnotatedWith(annotationType)) {
            // A business validation rule.
            if (!isValid(element)) {
                processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR,
                    "Invalid annotation usage",
                    element
                );
            }
        }
    }
    return true;
}
```

This is an **illustrative snippet**, not a standalone program; it assumes the `isValid` method and the `Element` / `Diagnostic` imports are provided in an actual processor.

Even when an error is reported with `Diagnostic.Kind.ERROR`, the method can still return `true` to claim the annotation types being assigned. The build fails due to the **diagnostic error**, not because of the boolean `true`.

Similarly:

```java
return false;
```

does not signal to the compiler that the processor's work has failed at all. It only allows the annotation types to continue being examined by subsequent processors.

The three feedback mechanisms have different roles:

| Mechanism | Meaning |
|---|---|
| `return true` / `return false` | Whether or not to claim the current set of annotation types |
| `processingEnv.getMessager().printMessage(ERROR, ...)` | Reports a proper compilation error |
| Uncaught exception from the processor | Exceptional situation; may interrupt annotation processing |

Normally, use `Messager` for source errors that users can fix, rather than throwing uncontrolled exceptions. Clearly distinguish that “an error was detected”, “whether the processor handles the type”, and “whether the compiler completes the build” are three separate states.

## 8. The Scope of Claiming Is the Assigned Types, Not Individual Elements

Suppose a processor supports:

```java
@SupportedAnnotationTypes({
    "demo.Trace",
    "demo.Validate"
})
```

In a round, `annotations` contains both types. If the processor only inspects elements with `@Trace` yet returns `true`, **both `Trace` and `Validate` present in the assigned set are claimed**.

There is no return value such as:

```java
return claimOnlyTrace; // Just a boolean, does not carry a list of types.
```

to express “claim `Trace` but do not claim `Validate`” in the same invocation.

If you need to process one type and leave another type for a subsequent processor, the architectural options include:

- Split processors according to groups of annotation types with different claiming rights.
- Use `return false` so as not to claim the assigned set, while coordinating to avoid duplicate operations.
- Declare only the annotation types that the processor actually takes on to process.
- Design an explicit processing order and policy if multiple processors belong to the same toolset.

Do not ignore a `TypeElement` in your logic and assume it is unaffected when the processor returns `true`. The claim scope follows **the `annotations` set**, independent of how many elements the code actually traversed.

## 9. Special Case: `@SupportedAnnotationTypes("*")`

The `"*"` wildcard is used by `Processor` to represent **all annotation types**, including situations where no annotation types are present in the round.

```java
import javax.annotation.processing.SupportedAnnotationTypes;

@SupportedAnnotationTypes("*")
public class UniversalProcessor extends AbstractProcessor {
    // ...
}
```

The snippet above only illustrates the annotation configuration; you need to write a complete class when using it in practice.

### `"*"` Combined with `return true`

According to the `Processor` contract, if a processor supports `"*"` and returns `true`, it **claims all annotation types currently in the assigned set**. This can prevent other processors from being assigned those types in the round, even if the universal processor only intended to perform a general inspection step.

Therefore, for a **non-exclusive** scanning/checking tool:

```java
@SupportedAnnotationTypes("*")
public class ObservationProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        // Observe root elements or check supplementary rules.
        return false; // Do not claim annotation processing ownership from other processors.
    }
}
```

The example is an illustrative fragment requiring imports for JSR 269 types and a `@SupportedSourceVersion` declaration or overriding the corresponding method for a complete configuration.

### An Empty `annotations` Set Can Still Be Passed to a Universal Processor

If no annotation types are present in a round, annotation processing can still take place and a processor supporting `"*"` can be invoked with an **empty set**. Handle this safely:

```java
if (annotations.isEmpty()) {
    // There are no annotation types in the assigned set for this round.
}
```

Do not access `annotations.iterator().next()` without checking. Although it can be called when the set is empty, that does not mean the processor will automatically be discovered and launched in every build configuration: valid tool/processor discovery configuration is still required.

A universal checker should consider returning `false`, especially if the tool only adds supplementary checks and must coexist with processors that handle specific annotations.

## 10. Processing Rounds and the Final Round

Annotation processing does not necessarily consist of a single pass. When a processor generates new source files, the compiler can feed those sources into a **subsequent round** so that processors continue discovering annotations.

Conceptual example:

```text
Round 1:
  initial input: Example.java with @Trace
  processor reads Trace, may generate GeneratedExample.java
      │
      ▼
Round 2:
  input: source/classes generated in the previous round
  processor looks for annotations on the new elements
      │
      ▼
Final round:
  processingOver() == true
  opportunity for summary checks; should not generate new sources
```

A processor that has already been invited to process in an earlier round **will continue to be invoked in subsequent rounds**, including the final round, even when no annotation types are assigned in that round.

Consequences:

- Do not use `annotations.isEmpty()` as the sole check to decide “this is the final round”. Use `roundEnv.processingOver()`.
- Returning `true` once does not exclude the processor from subsequent rounds.
- If the processor is invoked with an empty `annotations` set, it must still handle it validly, especially in the final round.
- If you need to aggregate results across rounds, the processor can maintain state between invocations on **the same processor instance**; manage duplicates and state carefully.
- Normally do not generate new sources when `processingOver() == true`. Creating a source file in the final round does not trigger a normal subsequent compilation round for it and may produce warnings.

### `processingOver()` Does Not Determine the Claim Value

Example:

```java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {
    if (roundEnv.processingOver()) {
        // Summarize, clean up state, report diagnostics if needed.
        return false;
    }
    // Process the assigned annotation types.
    return true;
}
```

This is an illustrative fragment. A processor can return different values per round; `Processor` permits the boolean value to vary based on its own criteria. Do not infer that returning `false` in the final round is an error or causes the processor to run infinitely.

## 11. An Annotation May Not Be Assigned Even If “It Appears Somewhere”

A processor is only assigned annotation types **according to the round's present/unmatched rules**, rather than scanning the entire classpath or entire repository on every invocation.

Notable scenarios:

### Annotation Exists on a Compiled Dependency

If a JAR contains an annotated class that is not among the root elements or the matching set of the current compilation pass, the processor may not be requested to process that annotation. `@SupportedAnnotationTypes("pkg.Marker")` does not automatically turn a processor into a scanner for every JAR on the classpath.

If the project needs to analyze dependencies, design a dedicated classpath/element-model reading workflow or bytecode tool as needed; do not expect `process` to automatically provide every place where the annotation appears.

### Repeatable Annotations Wrapped in a Container

When a repeatable annotation `@Tag` is written multiple times, the compiler represents it via the container `@Tags`. Under annotation processing rules, `@Tag` annotations that **only appear inside the container** are not considered *present* merely because they are elements of `@Tags.value()`.

Therefore, a processor handling repeatable annotations should register **both the repeatable type and the container type** in `getSupportedAnnotationTypes()`, for example:

```java
@SupportedAnnotationTypes({
    "demo.Tag",
    "demo.Tags"
})
```

This avoids missing cases where the compiler distributes `Tags` as the present annotation type instead of `Tag` directly. The processor then needs to read the container according to the `javax.lang.model` model when retrieving child data.

### Annotation Type Already Claimed by an Earlier Processor

If an earlier processor already claimed `demo.Trace` in the round, a subsequent processor is not assigned `Trace` merely because it also declares support for it. This is a matter of **processor coordination**, not the annotation disappearing from the source code.

### Processor Has Not Been Discovered/Instantiated

If `javac` is not configured to use the processor, there is no reason for `process` to be invoked. Check `-processor`, the processor path/module path, build tool configuration, and the service registration mechanism (`META-INF/services/javax.annotation.processing.Processor`) when using automatic discovery.

## 12. Designing a Responsible Processor

A processor can both recognize annotation types, read elements, and emit diagnostics, yet it should avoid claiming too broadly. Mental model:

```text
Step 1: Determine the annotation types you actually support.
Step 2: Inspect the annotations assigned in the current round.
Step 3: Retrieve matching elements using RoundEnvironment.
Step 4: Execute the checking/code-generation logic.
Step 5: Choose the claim boolean based on the coordination policy.
Step 6: Expect to be invoked in subsequent rounds, including the final round.
```

Recommendations by goal:

| Goal | Boolean suggestion | Explanation |
|---|---|---|
| Processor completely owns a specific annotation type and wants to prevent later processors from also handling that type | `true` | Claims the entire assigned set |
| Independent checker that only observes/emits warnings, expecting other processors to continue processing | `false` | Does not claim |
| Universal checker `"*"` running alongside multiple annotation processors | Usually `false` | Avoids claiming every annotation type |
| Processor has multiple annotation types but only wants to claim part of them | Revisit architecture | A single boolean cannot express partial claiming in the same call |
| Processor encounters an error on an element while still determining its claim policy | `true` or `false` depending on processing ownership | Report errors via `Messager`, do not use the boolean to indicate an error |
| Final round with no new annotations | No mandatory answer | Use `processingOver()`, ensuring the method tolerates an empty set |

In addition:

- Do not rely on the iteration order of a `Set<? extends TypeElement>` to decide which annotation takes priority unless you explicitly sort it.
- Do not execute non-idempotent side effects every time `process` is called; a processor can participate in multiple rounds.
- When using `Filer` to generate sources/resources, avoid attempting to recreate the same file multiple times (which can lead to `FilerException`).
- Emit diagnostics with a specific element location so learners/users receive clear, understandable information.
- Test with **two processors** supporting the same annotation type to detect unintended claiming early.
- If you return `true`, ensure you genuinely accept responsibility for all assigned annotation types, not just one arbitrarily chosen type.

## 13. Common Mistakes and How to Fix Them

### 13.1. Thinking `return true` Means “Build Succeeded”

Incorrect. It means claiming the annotation types. The build can still fail due to syntax errors, compiler errors, or `Diagnostic.Kind.ERROR` reported by a processor.

### 13.2. Thinking `return false` Means “Processing Failed”

Incorrect. A validator may have completed its task and intentionally returned `false` so that other processors can continue receiving the type.

### 13.3. Ignoring the Boolean Value Because “There Is Only One Processor”

Even if there is currently only one processor, a future build configuration might add other processors. The return value is part of the coordination policy and should not be chosen arbitrarily.

### 13.4. Using `"*"` and `return true` for a Monitoring-Only Tool

This can unintentionally claim multiple annotation types, blocking specialized processors that run afterward. Consider `return false` for a universal checker.

### 13.5. Assuming Claiming Grants Permanent Exclusivity

Claiming only coordinates **unclaimed annotation types in the current round**. It does not prevent earlier processors, does not delete metadata, does not disable subsequent rounds, and does not guarantee that there is only one consumer across the entire system.

### 13.6. Confusing the `annotations` Set with the List of Annotated Classes

The `annotations` parameter contains `TypeElement` instances representing **annotation types**; to find annotated classes/methods/fields, use `roundEnv.getElementsAnnotatedWith(...)` and filter by `ElementKind` or inspect the element model as needed.

### 13.7. Assuming `annotations` Is Always Non-Empty

A processor invoked in subsequent rounds, including the final round, may receive an empty set. A `"*"` processor can also be invoked in situations where no types are present. Check `isEmpty()` and `processingOver()` for their intended purposes.

### 13.8. Only Declaring `@SupportedAnnotationTypes` and Expecting the Processor to Run

The processor must be discovered and loaded. With `javac`, check `-processor` and `-processorpath` or the appropriate module path / service registration mechanism. The example command used `-processor` explicitly to eliminate reliance on service discovery.

### 13.9. Missing the Container of a Repeatable Annotation

If `@Tag` can appear multiple times and produce `@Tags`, register support for both `Tag` and `Tags` and handle the container case with proper semantics. Do not assume that the inner annotation is always present as a standalone type in the `annotations` set.

### 13.10. Assuming Reporting `ERROR` Automatically Claims the Annotation

An error diagnostic does not automatically determine the boolean returned by `process`. If the processor wants to claim the annotations set, it must still return `true`; if it wants to preserve the types for other processors, it returns `false`. The two decisions are independent.

## 14. Exercises to Master the Rules

Suppose in a round there is an initial unmatched set:

```text
{ demo.Trace, demo.Validate }
```

There are three processors in order:

```text
P1 supports demo.Trace
P2 supports demo.Trace and demo.Validate
P3 supports demo.Validate
```

Analyze the following scenarios:

1. P1 receives `Trace` and returns `true`. Can P2 still receive `Trace`?
2. In the same scenario, can P2 be assigned `Validate`?
3. P1 returns `false`. Can P2 receive both `Trace` and `Validate`?
4. P2 is assigned both types and returns `true`; can P3 receive `Validate` in that round?
5. P2 only reads `@Trace` elements, yet is assigned both types and returns `true`; is `Validate` claimed?
6. If P2 reports `Diagnostic.Kind.ERROR` yet returns `false`, does this boolean report a processing failure?
7. If a universal processor `"*"` running first returns `true`, what happens to the types in the unmatched set?
8. A processor was invoked in the first round and claimed `Trace`; when moving to the final round with no new annotations, can it still be invoked?
9. When `annotations` is empty, should you immediately call `annotations.iterator().next()`?
10. When a repeatable `@Tag` is contained within `@Tags`, does registering support only for `Tag` guarantee covering all usages?

**Answers:**

1. **No.** `Trace` was already claimed by P1 in the round.
2. **Possibly.** `Validate` has not been claimed by P1; P2 declares support for this type.
3. **Possibly.** Both types remain unclaimed, depending on the set the compiler assigns to P2 in the round.
4. **No.** If P2 receives both and returns `true`, `Validate` has been claimed.
5. **Yes.** The boolean claims the entire assigned set, not only the type that the code read.
6. **No.** `false` means not claiming; the compilation error is caused by `Diagnostic.Kind.ERROR`.
7. **All assigned types are claimed**, preventing subsequent processors from receiving them in the round.
8. **Yes.** Processors that were invited in one round continue to be invited in subsequent rounds, including the final round.
9. **No.** You must check for an empty set and handle `processingOver()` where appropriate.
10. **Not guaranteed.** You should support both the repeatable type and the container type as recommended by the API.

## 15. Final Checklist

- `process` returns `true` to **claim the assigned set of annotation types**, not to report success.
- `process` returns `false` to **not claim**, not to report failure.
- Claiming affects processors **running afterward in the same round**, and does not revoke the results of earlier processors.
- `annotations` contains annotation **types** as `TypeElement`s, not the annotated classes/methods.
- Use `roundEnv.getElementsAnnotatedWith(...)` to retrieve the corresponding elements.
- Declare supported types accurately using `@SupportedAnnotationTypes` or `getSupportedAnnotationTypes()`.
- The processor must be built/discovered/configured for the compiler to actually invoke `process`.
- If using `"*"` as a universal checker, normally return `false` so as not to block other processors.
- The boolean value does not allow selectively claiming part of the assigned `annotations` set in the same call.
- A processor can be invoked across multiple rounds; use `roundEnv.processingOver()` instead of guessing based on `annotations.isEmpty()`.
- Always handle an empty `annotations` set and avoid regenerating the same files across multiple rounds.
- Report actual errors using `Messager` and `Diagnostic.Kind.ERROR`, independent of the returned boolean.
- When working with repeatable annotations, consider registering support for both the repeatable type and the container.
- Try writing a build with multiple processors supporting the same type to verify execution order and claiming policy.

**Reference:** Java SE 17, `javax.annotation.processing.Processor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html ; `RoundEnvironment`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html .

Key takeaway: **`process` is the coordination mechanism among processors in each processing round**. Clearly understanding the claim boolean, the assigned set of `TypeElement`s, and processor ordering helps avoid accidentally “swallowing” annotations so that other processors no longer receive their work.
