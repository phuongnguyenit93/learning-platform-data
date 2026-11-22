# Choosing Annotation Lifecycle by Consumer and Time of Use in Java

## 1. The Problem: Who Needs to Read the Annotation and When?

When defining a custom annotation with `@interface`, we usually have a specific goal: prompting the compiler to perform checks, supporting an annotation processor in generating code, allowing a tool to analyze `.class` files, or letting a framework read configuration while the application is running. Those consumers access metadata at **different stages**.

Java allows an annotation author to specify how long metadata is retained using the `@Retention` meta-annotation. The three policy levels are:

- `RetentionPolicy.SOURCE`: metadata is only needed in source code and during compilation; it is not saved in the class file.
- `RetentionPolicy.CLASS`: metadata is recorded in the class file so bytecode-reading tools can use it; standard reflection does not return it at runtime.
- `RetentionPolicy.RUNTIME`: metadata is recorded in the class file and can be accessed by standard reflection APIs at runtime.

Choosing the right retention is how to **match the metadata lifecycle to the actual metadata consumer**. Not every annotation needs `RUNTIME`; conversely, if a framework uses `Class.getAnnotation(...)`, then `SOURCE` or `CLASS` is not enough.

Example question to answer before declaring:

> “Will this annotation be read by `javac`, an annotation processor, a post-compilation `.class` scanner, or Java reflection while the application is running?”

The answer determines the appropriate retention.

## 2. How Is `@Retention` Placed on an Annotation Type?

`@Retention` belongs to the `java.lang.annotation` package. It takes a `RetentionPolicy` enum value:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.SOURCE)
@interface SourceMarker {
    String value();
}

@Retention(RetentionPolicy.CLASS)
@interface ClassMarker {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@interface RuntimeMarker {
    String value();
}
```

`@Retention(...)` must be placed on the **annotation type definition**, not as an option re-specified at each usage site:

```java
@RuntimeMarker("checkout")
class CheckoutService {}
```

Each annotation type has a defined retention policy. For example, if `@RuntimeMarker` has `RUNTIME`, all uses of `@RuntimeMarker` follow that policy.

When **`@Retention` is not declared**, Java's default is **`RetentionPolicy.CLASS`**, not `SOURCE` and not `RUNTIME`:

```java
@interface DefaultMarker {
    String value();
}
// Equivalent in retention to @Retention(RetentionPolicy.CLASS).
```

You should explicitly write `@Retention` for custom-designed annotations so readers do not have to remember the default value and to clearly express the intent of the API.

## 3. Three Policies Corresponding to Three Lifecycle Stages

Visualizing the common progression:

```text
.java source code
    |
    | javac: parse, type checking, annotation processing
    v
Compilation output .class / .jar
    |
    | tool reading .class files or bytecode
    v
Application loads classes and runs on the JVM
    |
    | reflection: Class.getAnnotation(...), Method.getAnnotations(), ...
    v
Framework/application logic processing metadata
```

Decision table:

| Policy | Present in source / during compilation | Retained in `.class` | Readable via standard Java reflection |
|---|---|---|---|
| `SOURCE` | Yes | No | No |
| `CLASS` | Yes | Yes | No |
| `RUNTIME` | Yes | Yes | Yes |

The table above describes annotations on supported declarations, such as classes, methods, or fields; the specific storage for *type-use annotations* depends on the annotation's location in the class file.

### `SOURCE`: Done After the Compilation Stage

`SOURCE` is for metadata that is useful while the compiler or annotation processor is processing source code, when the post-compilation program does not need to inspect it again.

For example, in the standard library, `@Override` and `@SuppressWarnings` have `SOURCE` retention: they serve compiler checks and do not need to become runtime metadata.

Choose `SOURCE` when the conditions fit:

- The compiler/annotation processor needs to see the annotation **during the compilation pass containing the annotated source code**.
- There is no need to look up the annotation again from already-compiled libraries that only have `.class` files.
- No bytecode scanner or reflection logic depends on the annotation after compilation.

`SOURCE` does not guarantee that an annotation processor will run automatically: the processor must also be registered, enabled in the build process, and programmed to process the annotation.

### `CLASS`: Retaining Metadata in the Artifact for Post-Compilation Reading

`CLASS` is for tools that work with bytecode or class files, such as a `.class` inspection/transformation step in the build pipeline. The metadata remains in the artifact, even though standard reflection does not expose it.

Choose `CLASS` when:

- The processor runs **after compilation**, takes `.class` or `.jar` as input, and needs to read the annotation.
- The tool actively parses class-file attributes or uses a bytecode library.
- `Class.getAnnotation(...)` or similar APIs are not needed in the application at runtime.

`CLASS` can also serve tools that process annotations located in already-compiled dependency libraries, if the tool is capable of reading the corresponding class-file metadata.

Be careful: **an annotation existing in the class file does not mean Java reflection sees it**. Tools that read bytecode directly and standard reflection have different access mechanisms.

### `RUNTIME`: Framework or Application Needs Reflection

`RUNTIME` is for metadata that needs to be queried via reflection after the JVM loads the class.

Example:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Timed {
    String name();
}
```

A framework can look up the `@Timed` annotation on a method via `Method.getAnnotation(Timed.class)`, and then actively trigger timing code. The annotation does not measure time on its own; the framework's logic does that.

Choose `RUNTIME` when the consumer actually needs APIs such as:

- `Class.getAnnotation(...)` or `Class.isAnnotationPresent(...)`.
- `Method.getAnnotation(...)`, `Field.getAnnotation(...)`, `Constructor.getAnnotations()`.
- `Parameter.getAnnotations()` or another reflection API for the exact annotation target location.
- `AnnotatedElement.getDeclaredAnnotations()` and publicly exposed lookup variants.

`RUNTIME` is the longest metadata retention level among the three policies. Runtime metadata still resides in the class file, so bytecode scanners can usually read it as well. Choose `RUNTIME` if reflection is needed; there is no need to change the annotation to `CLASS` just because another bytecode tool also uses it.

## 4. Which Policy Should Each Consumer Choose?

| Consumer / Requirement | When Metadata Is Needed | Retention to Consider | Why |
|---|---|---|---|
| `javac` checking annotations when reading source | During compilation | `SOURCE` | Metadata does not need to accompany the artifact |
| Annotation processor directly reading source files being compiled | During compilation | `SOURCE` | Processor uses the element model provided by the compiler |
| Code generator needing to find annotations on compiled libraries | Subsequent build step or when reading `.class` dependencies | `CLASS` or `RUNTIME` | `SOURCE` has already been stripped from the class file |
| Post-`javac` bytecode analyzer | After compilation | `CLASS` | Sufficient to retain metadata for bytecode tools |
| Bytecode transformer processing packaged artifacts | Build / load / transform, using class-file APIs | `CLASS` or `RUNTIME` | The tool must read class-file attributes |
| Framework calling reflection in the application | Runtime | `RUNTIME` | Reflection APIs require runtime-visible annotations |
| Runtime scanner reading bytecode directly without reflection | Runtime, but on `.class` bytes | `CLASS` may be sufficient | Need to verify the scanner actually reads runtime-invisible annotations |
| No specific consumer | Undetermined | Cannot yet decide by timing | Define how it will be consumed before designing |

**Key point:** choose based on **how the consumer accesses metadata**, not only on whether it runs at build time or runtime. A tool running at runtime that reads bytecode directly can see `CLASS`; conversely, runtime code that only uses standard reflection strictly requires `RUNTIME`.

In a real project, check the documentation and implementation of the tool/framework. Merely seeing an annotation appear in an API is not enough to infer the required retention without knowing who reads it.

## 5. Complete Java 17+ Example: Three Retentions, One Class

Create the file **`RetentionChoiceDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface SourceHint {
    String value();
}

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
@interface ClassHint {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RuntimeHint {
    String value();
}

@SourceHint("compile")
@ClassHint("bytecode")
@RuntimeHint("reflection")
class OrderHandler {
}

public class RetentionChoiceDemo {
    public static void main(String[] args) {
        Class<OrderHandler> type = OrderHandler.class;

        System.out.println("SOURCE reflection="
                + type.isAnnotationPresent(SourceHint.class));
        System.out.println("CLASS reflection="
                + type.isAnnotationPresent(ClassHint.class));
        System.out.println("RUNTIME reflection="
                + type.isAnnotationPresent(RuntimeHint.class));

        RuntimeHint hint = type.getAnnotation(RuntimeHint.class);
        System.out.println("value=" + hint.value());
    }
}
```

Save the file and run it with JDK 17 or later:

```bash
javac RetentionChoiceDemo.java
java RetentionChoiceDemo
```

**Exact stdout:**

```text
SOURCE reflection=false
CLASS reflection=false
RUNTIME reflection=true
value=reflection
```

Explanation:

1. All three annotations are valid and share the `TYPE` target.
2. `javac` sees the annotations in the source code, but `SourceHint` is stripped from the class file after compilation.
3. `ClassHint` is recorded in the class file, but **does not appear through `isAnnotationPresent`**.
4. `RuntimeHint` is recorded with runtime visibility; `isAnnotationPresent` returns `true` and `getAnnotation` reads `value` as `"reflection"`.

All annotation types and `OrderHandler` are declared without the `public` modifier in the same file; `RetentionChoiceDemo` is the only public class and matches the file name, so the example adheres to Java rules.

**Do not conclude that `SOURCE`/`CLASS` failed or were completely deleted by the JVM** from the `false` result of reflection. With `CLASS`, metadata can still exist at the class-file bytes layer; the `false` result only reflects how standard Java reflection exposes annotations.

## 6. Inspecting the Class File with `javap -v`

After compiling the example in Section 5, use:

```bash
javap -v OrderHandler
```

In the detailed class-file information, observe the annotation declaration groups:

- `RuntimeVisibleAnnotations`: annotation data with `RUNTIME` retention; this example contains `RuntimeHint`.
- `RuntimeInvisibleAnnotations`: annotation data saved into the class file that does not need to be exposed via reflection; this example contains `ClassHint`.
- `SourceHint` is not recorded as an annotation on `OrderHandler` because of `SOURCE` retention.

Class-file attribute names may appear in `javap` output with descriptor notation or constant-pool indexes. You only need to recognize the difference between *Visible* and *Invisible*, without memorizing the entire class-file encoding.

If an annotation is used on a **TYPE_USE** position, the class file may use other attributes such as `RuntimeVisibleTypeAnnotations` and `RuntimeInvisibleTypeAnnotations`. This does not change the principle of choosing retention; it only reflects different annotation forms in the class-file format.

When using `javap` or a bytecode-reading library, you need to inspect **the exact class file containing the annotated declaration**, rather than only looking at the annotation definition file. `@Retention` resides in the annotation type definition; the data of a usage resides in the class file of the annotated element, if the policy requires retaining it.

## 7. Annotation Processors and Choosing `SOURCE`

An annotation processor following the `javax.annotation.processing` API works during the compilation process, accessing program information through the `javax.lang.model` element model. For annotations on source code compiled in that pass, `SOURCE` retention is the natural choice if the processing result does not require re-reading metadata from the artifact.

Example defining an annotation that marks a class requiring documentation generation:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface GenerateSummary {
    String value();
}
```

This is **illustrative content for a separate file named `GenerateSummary.java`**, not part of the `RetentionChoiceDemo.java` program above. A suitable processor can find types carrying `@GenerateSummary` via `RoundEnvironment.getElementsAnnotatedWith(GenerateSummary.class)` when compiling source code that uses the annotation.

Distinctions to keep in mind:

- **Retention and when a processor runs are two different concepts.** `SOURCE` does not automatically trigger a processor, does not register a processor, and does not force the compiler to generate files.
- The processor must be built, supplied to `javac` with the proper configuration, and actually process the corresponding annotation type.
- If you want a processor or another tool to read annotations on classes of a dependency that **only has `.class` files**, `SOURCE` is not enough because the information has already been stripped from the artifact. In that case, consider `CLASS` or `RUNTIME`.
- If the processor also needs to generate annotations that a runtime framework will read directly, those may be **two annotation types** with different purposes or the same annotation with `RUNTIME` retention by design.

Do not switch all processor-oriented annotations to `RUNTIME` just because of the word “processor”. Check whether the processor needs to read source code, class files, or runtime reflection.

## 8. Bytecode-Reading Tools Differ from Reflection

Suppose a build pipeline has a tool that checks that classes marked `@InternalApi` are not exported in a library. The tool runs **after `javac`** and only takes `.class` files. An annotation of this kind can be declared as:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
@interface InternalApi {
    String owner();
}
```

That definition retains metadata so a scanner that understands the class-file format can read it. `Class.getAnnotation(InternalApi.class)` at application runtime still returns `null` for an annotation retained at `CLASS`.

If the scanner is a **reflection library** scanning loaded classes, it does not behave like a bytecode reader. In that case, even if the scanner is called “annotation scanning”, the `CLASS` policy is not enough. You must check whether the library is using `Class.getAnnotations()` or reading class bytes directly.

Some bytecode tools have options to scan both runtime-visible and runtime-invisible annotations; whether `CLASS` is found depends on the tool's configuration and capabilities. Choosing the right retention also requires **verifying the specific scanner** with a practical test.

## 9. Runtime Frameworks and Annotation Processing

Many runtime mechanisms, such as endpoint routers, handler registration, checking whether a method has an annotation, or configuration controllers, can read annotations via reflection. In that case, `RUNTIME` is usually required.

Example:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Action {
    String value();
}
```

A class can use:

```java
class InventoryService {
    @Action("reserve")
    void reserve() {
    }
}
```

A runtime component can obtain `InventoryService.class.getDeclaredMethod("reserve")` and then call `getAnnotation(Action.class)` to find metadata. This is the act of **reading metadata**; the annotation does not execute a method on its own and does not create a dispatch mechanism by itself.

Some frameworks also leverage bytecode, proxies, pre-generated indexes, or other optimizations. Therefore, for annotations of **existing frameworks**, follow the retention required by the framework/documentation; when designing custom annotations, base the decision on the metadata consumption path you control.

`@Retention(RUNTIME)` **does not guarantee** that a framework will find or apply the annotation if the framework is not programmed to recognize that type. Besides retention, the attachment target (`@Target`), scan scope, method accessibility, and framework configuration can all matter.

## 10. Common Misconceptions When Choosing Retention

### 10.1. Forgetting to Declare `@Retention` and Waiting for Reflection

```java
@interface FeatureFlag {
    String name();
}

@FeatureFlag(name = "checkout")
class Checkout {}
```

The default is `CLASS`. `Checkout.class.getAnnotation(FeatureFlag.class)` cannot return this annotation. If runtime reflection is required, add `@Retention(RetentionPolicy.RUNTIME)` **on `FeatureFlag`** and recompile the code using it.

### 10.2. Using `SOURCE` for a Scanner That Only Accepts `.class`

`SOURCE` is not saved in the class file. A post-processing step that only accepts `.jar` files will not be able to read a `SOURCE` annotation placed on a class solely from that artifact.

If a build tool needs metadata after compilation, use `CLASS` or `RUNTIME` as appropriate. You cannot recover the `SOURCE` annotation content of an already-compiled class just by switching the reading tool.

### 10.3. Using `CLASS` for `getAnnotation`

`CLASS` retains data in the class file, **but it is not used for standard annotation reflection**. The two lines below express different needs:

```java
// Bytecode tool: reads class-file attributes according to the JVM format.
// Java reflection:
SomeClass.class.getAnnotation(MyAnnotation.class);
```

If the actual processing path is the second line, choose `RUNTIME`.

### 10.4. Confusing `@Target` with `@Retention`

- `@Target(ElementType.METHOD)` answers “where can the annotation be placed?”.
- `@Retention(RetentionPolicy.RUNTIME)` answers “how long is the annotation retained and is it visible to reflection?”.

An annotation can have `@Target(METHOD)` and `@Retention(SOURCE)` or `@Retention(RUNTIME)` depending on the reader. Choosing the right target does not replace choosing the right retention.

### 10.5. Assuming `@Inherited` Makes an Annotation Extend Its Lifecycle

`@Inherited` relates to how certain annotations on a class are found through a superclass; it does **not** turn `SOURCE` or `CLASS` into `RUNTIME`. If you want to query an inherited annotation via reflection, the annotation still needs the appropriate retention. The `@Inherited` mechanism does not automatically apply to methods, fields, interfaces, or packages as a general inheritance rule.

### 10.6. Using `@Documented` to Retain an Annotation at Runtime

`@Documented` relates to how the Javadoc tool includes an annotation in API documentation. It does not change the retention policy. Similarly, `@Repeatable` solves having the same annotation appear multiple times at one valid location; this meta-annotation alone does not make a `SOURCE` annotation runtime-visible.

### 10.7. Modifying Only the Annotation Definition Without Recompiling Annotated Code

If you change `@Retention(SOURCE)` to `@Retention(RUNTIME)`, classes **already compiled against the old version** do not automatically receive the new metadata. Old class files may have already discarded the annotation information; you need to recompile **the sources that use the annotation** and build a new artifact.

Even when changing from `CLASS` to `RUNTIME`, the attribute storing the annotation in the old class file may not match the new reflection mechanism. Rebuild all affected code before evaluating the result.

### 10.8. Using `RUNTIME` to Fix a Processor Not Running

If a processor is not configured or does not support the annotation, changing retention to `RUNTIME` **does not address the cause**. Check processor registration, `annotationProcessorPath`/build tool configuration, Java version support, and annotation name filtering.

The issue “does the compiler invoke the processor?” is independent of the issue “does the annotation exist at runtime?”.

## 11. Design Criteria and Trade-offs

A good retention choice balances reading requirements with metadata retention capability.

### Retain Metadata to the Extent Needed

If an annotation only requires the compiler to warn about errors, `SOURCE` is enough. If post-compilation bytecode analysis is needed, metadata must at minimum be retained (`CLASS` or `RUNTIME`). If runtime reflection is the consumption interface, `RUNTIME` is necessary.

Retaining metadata longer can cause class files or artifacts to contain more information. However, changing retention alone does not guarantee significant performance improvements; size and cost depend on the number of annotations, values, classes, and how the framework scans. **Do not guess a number or optimize by feel**; measure the artifact and scan time if that is genuinely an issue.

### Security and Sensitive Data

Although `SOURCE` is not written into the class file as an annotation, values may still remain in source code, repositories, or build tool outputs. `CLASS` and `RUNTIME` make metadata present in the artifact. **Do not place passwords, tokens, or secrets directly in annotation values** expecting `CLASS` to prevent runtime users from viewing them; class-file reading tools can extract them.

### Distinguishing Retention from the Presence of the Annotation Type

The class defining `MyAnnotation` can still be compiled into `MyAnnotation.class` and referenced by normal code, even with `@Retention(SOURCE)`. `SOURCE` removes the **metadata of the annotation application** from the annotated class file; it does not mean the type definition necessarily disappears from the entire program.

For example, in Section 5, `SourceHint.class` is still referenced by reflection code as a class literal, yet `OrderHandler.class` does not carry a `@SourceHint` annotation that can be read or found from bytecode.

### Compatibility and Release Process

Changing retention is changing the metadata consumption contract. If you switch from `RUNTIME` back to `CLASS`, code that previously called `getAnnotation` may stop finding the metadata. Moving up to `RUNTIME` requires recompiling annotated classes and checking packaging, shading, or bytecode transformation workflows as well. When an annotation API has already been published to multiple modules, you need to notify and test the relevant consumers.

## 12. Selection Process in a Project

Follow sequentially:

1. **Name the metadata:** what is the annotation used to describe, on a class/method/field/package or another location? Choose `@Target` separately according to this need.
2. **Identify the direct consumer:** compiler, annotation processor, class-file scanner, or Java reflection/framework?
3. **Identify the consumer's input:** source code being compiled, `.class` files from dependencies, or classes loaded in the JVM?
4. **Choose the retention level:**
   - Information only needed at the step where the compiler reads source: consider `SOURCE`.
   - Metadata needed in the class file for a bytecode scanner: consider `CLASS`.
   - Java reflection needed at runtime: choose `RUNTIME`.
5. **Cross-check with the actual tool:** ensure the processor is run, the scanner reads the right attributes, or the framework has logic to recognize the annotation.
6. **Create a test:** directly check the processor output, `javap -v` on the class file, or the `getAnnotation` result; do not rely solely on `@Annotation` being in the source.
7. **Check the packaged artifact:** class-file metadata must still exist in the used product; a transform/obfuscation step can affect it.

Example decisions:

- “Use `@GenerateBuilder` for a processor to generate code while `javac` is compiling source”: `SOURCE` is usually enough.
- “Use `@ArchitectureRule` for a CI plugin to check bytecode in a JAR”: `CLASS` is usually enough.
- “Use `@Route` for the program to call `Method.getAnnotation(...)` at startup”: `RUNTIME` is needed.

If two different consumers use **the same annotation type**, choose the policy that satisfies the one needing the metadata the longest. For instance, if a compile-time processor **and** runtime reflection both read an annotation, the appropriate policy is `RUNTIME`.

## 13. Retention Classification Exercises

Given the scenarios:

1. An annotation helps the compiler identify where to suppress warnings, with no tool processing metadata after compilation.
2. A CI tool only takes the JAR file after the build and scans classes containing the annotation to generate a report.
3. An application uses `Method.getDeclaredAnnotations()` to register handlers at startup.
4. A processor generates a new Java class from an annotation on a source file currently being compiled.
5. A post-build tool scans `.class` files, while the application also calls `Class.getAnnotation(...)` to read that same annotation.
6. An annotation without `@Retention`: what is the default value?
7. A class using a `SOURCE` annotation has finished compiling: can the value be retrieved using `javap -v` on the annotated class file?
8. Does a `CLASS` annotation remain in the bytecode, and does `Class.isAnnotationPresent(...)` return `true`?

Answers:

1. **`SOURCE`**: serves compile time, no need to store class-file metadata.
2. **`CLASS`** is usually enough: the tool reads bytecode after compilation; `RUNTIME` can also store it, but is unnecessary if there is no reflection.
3. **`RUNTIME`**: reflection requires runtime-visible annotations.
4. **`SOURCE`** is usually enough: the processor processes the source of the current compilation pass, if there are no subsequent consumers.
5. **`RUNTIME`**: satisfies both the bytecode scanner and reflection simultaneously.
6. **`CLASS`**: this is Java's default retention.
7. **No**: the usage of a `SOURCE` annotation is not saved as metadata in the annotated class file.
8. **Present in the class file, but does not appear through standard reflection**: `isAnnotationPresent(...)` returns `false` for a `CLASS`-only annotation if no other inheritance/runtime annotation mechanism is involved.

## 14. End-of-Article Checklist

- Identified the **actual consumer** rather than relying on the annotation name or framework name.
- `@Target` accurately describes **where it is applied**, while `@Retention` describes the **metadata lifecycle**.
- Used only during source compilation → consider `SOURCE`.
- Needs to be read from `.class`/`.jar` by a bytecode scanner → `CLASS` is usually enough.
- Needs `Class`/`Method`/`Field.getAnnotation(...)` or Java reflection → `RUNTIME`.
- No `@Retention` → Java defaults to `CLASS`.
- `CLASS` is still stored in the class file, even though Java reflection does not see it.
- `RUNTIME` does not make an annotation work on its own; there must be code or a framework consuming it.
- `@Documented` and `@Inherited` do not replace retention.
- When changing retention, recompiled the annotated classes and checked the actual artifact.
- Confirmed that the scanner/processor/framework reads the right annotation type at the right stage.
- Did not put secret data into annotation values just thinking `CLASS` metadata is “hidden” from the application.

A well-defined annotation will have a retention that clearly expresses **who will read it**, **from what data form**, and **at what time**. As a result, metadata persists long enough for the consumer while avoiding the false expectation that the compiler, bytecode tools, and runtime reflection observe annotations in the same way.
