# RetentionPolicy.SOURCE: Annotation Metadata That Exists Only in Java Source Code

When reading an annotation such as `@Override` or `@SuppressWarnings`, we often see that it affects the **compilation** process but does not appear once the program is running. Java supports this design through the **`RetentionPolicy.SOURCE`** policy: the compiler sees the annotation in the source code for checking or processing, and then **does not store that annotation usage in the binary representation of the class**.

Basic declaration:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.SOURCE)
@interface CompileTimeHint {
    String value();
}
```

With this annotation, `@CompileTimeHint("example")` can be attached to a valid declaration, but once the compiler finishes, the metadata about the **annotation attachment** is no longer present in the corresponding `.class` file. Therefore, Java reflection at runtime cannot read that attachment back.

This lesson focuses on: **which stages SOURCE exists in, where it disappears, how the compiler/annotation processor can use it, how to verify it with `javac` and `javap`, and when to choose SOURCE instead of CLASS/RUNTIME.**

## 1. What Is Retention?

A **retention policy** specifies how long an annotation is retained across the lifecycle from Java source code to the running program. We place it on the **annotation definition** using the `@Retention` meta-annotation:

```java
@Retention(RetentionPolicy.SOURCE)
@interface SourceTag {}
```

`@Retention` is a meta-annotation: an annotation used to describe **another annotation**. The value `RetentionPolicy.SOURCE` is an enum constant in `java.lang.annotation.RetentionPolicy`.

At a usage site:

```java
@SourceTag
class Service {}
```

there are two distinct concepts:

1. **The `SourceTag` definition**: the annotation type declared with `@interface SourceTag`. It is a Java type that can be compiled separately into `SourceTag.class`.
2. **The usage of `@SourceTag` on `Service`**: the metadata attached to the `Service` declaration. It is this usage that the compiler discards from `Service.class` when retention is SOURCE.

Therefore, the statement "a SOURCE annotation is not in bytecode" must be properly understood as: **the SOURCE annotation attachment is not written into the binary of the annotated element**. It does not mean the compiler forbids generating the `SourceTag.class` file for the annotation definition itself.

## 2. The Lifecycle of SOURCE: Source Code → Compiler → Bytecode → Runtime

```text
Service.java
  @SourceTag
  class Service {}
        |
        v
Compilation stage:
  - Parser and compiler read @SourceTag
  - Check annotation name, @Target location, element types
  - Annotation processor (if configured) can read SOURCE
        |
        v
Service.class:
  - Contains bytecode, class/method/field... for the program
  - Does NOT store the SOURCE @SourceTag usage
        |
        v
Runtime:
  - Reflection cannot retrieve @SourceTag from Service.class
  - Frameworks that only scan metadata in .class cannot see it either
```

Meaning of each stage:

- **Before compilation:** the annotation is part of the source code, with syntax and element values that must follow Java rules.
- **During compilation:** the compiler can use the annotation to check the code, and an annotation processor can see it in the source element model.
- **When generating the binary:** according to the Java Language Specification, an annotation attachment with SOURCE retention must not appear in the binary representation of the annotated target.
- **At runtime:** APIs such as `Class.getAnnotation(...)` and `isAnnotationPresent(...)` cannot recover SOURCE annotations on compiled classes.

**SOURCE does not mean the annotation is deleted from the `.java` file.** The source code remains intact on disk; "discarded" here describes how the compiler builds the binary representation.

## 3. Comparing SOURCE, CLASS, and RUNTIME

Java supports three retention levels:

| Policy | Read by the compiler when compiling from source? | Annotation usage stored in `.class`? | Readable by runtime reflection? |
|---|---|---|---|
| `RetentionPolicy.SOURCE` | Yes | **No** | **No** |
| `RetentionPolicy.CLASS` | Yes | Yes, for declaration cases stored per the JLS | **No** by default via standard Java reflection |
| `RetentionPolicy.RUNTIME` | Yes | Yes, for declaration cases stored per the JLS | **Yes** via reflection where supported by the API |

Three examples of intended usage:

- **SOURCE:** assists the compiler or source code analysis tools; the attachment metadata is not needed after compilation.
- **CLASS:** stores metadata for tools that read/transform class files or analyze binaries, even though Java runtime reflection does not expose it by default.
- **RUNTIME:** metadata must be visible to the appropriate reflection APIs when the program runs; commonly used by frameworks that read annotation configurations at startup or while handling requests.

**An easy-to-miss detail:** if **`@Retention` is not declared**, an annotation defaults to **CLASS** retention, neither SOURCE nor RUNTIME:

```java
@interface DefaultRetention {
    String value();
}
```

`DefaultRetention` on a class will follow CLASS retention by default. If you want an annotation to serve only at compile time and be discarded from the binary, you must explicitly specify `@Retention(RetentionPolicy.SOURCE)`.

In addition, the JLS has exceptions regarding annotations on **local variable declarations** or **lambda formal parameters** when considering their presence in the class file for CLASS/RUNTIME; this table should not be overgeneralized as a guarantee that every location using CLASS/RUNTIME is equally accessible via reflection. For SOURCE, the rule that the usage is discarded from the binary remains clear.

## 4. Runnable Java 17+ Example: SOURCE Disappears from Runtime

Create a single file named `RetentionSourceDemo.java`:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

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

@SourceHint("source-only")
@ClassHint("bytecode")
@RuntimeHint("runtime")
class Sample {}

public class RetentionSourceDemo {
    public static void main(String[] args) {
        System.out.println(
                "SOURCE visible: "
                        + Sample.class.isAnnotationPresent(SourceHint.class)
        );
        System.out.println(
                "CLASS visible: "
                        + Sample.class.isAnnotationPresent(ClassHint.class)
        );
        System.out.println(
                "RUNTIME visible: "
                        + Sample.class.isAnnotationPresent(RuntimeHint.class)
        );
        System.out.println(
                "RUNTIME value: "
                        + Sample.class.getAnnotation(RuntimeHint.class).value()
        );
    }
}
```

Compile and run in the directory containing the file:

```bash
javac --release 17 RetentionSourceDemo.java
java RetentionSourceDemo
```

Exact output:

```text
SOURCE visible: false
CLASS visible: false
RUNTIME visible: true
RUNTIME value: runtime
```

**Why?** `Sample` has all three annotations applied on the same declaration. However, the different retention policies determine which metadata exists at runtime. `@SourceHint` is discarded from `Sample.class` by the compiler, `@ClassHint` is written to the class file but is not exposed by ordinary runtime reflection, and `@RuntimeHint` is both written and allowed to be read reflectively.

You can inspect further using the `javap` tool bundled with the JDK:

```bash
javap -v Sample
```

In the metadata section of `Sample.class`:

- There will be a trace of `ClassHint` as an annotation stored in the binary (typically under `RuntimeInvisibleAnnotations`).
- There will be `RuntimeHint` as an annotation intended for runtime (typically under `RuntimeVisibleAnnotations`).
- **No usage of `SourceHint`** is stored in `Sample.class`.

Field names, line ordering, and constant pool indices in the `javap -v` output may vary across JDKs; instead of comparing the entire output, look for the three corresponding annotation names. For the `Sample.class` file in this example, `SourceHint` does not appear in the dump. If you inspect `SourceHint.class` separately, you will see it is still a compiled annotation type; these two facts do not contradict each other.

## 5. SOURCE Remains Useful During Compilation: Compilers and Annotation Processors

Not retaining an annotation until runtime does **not** make it useless. There are two common categories of compile-time applications:

**The compiler processes standard annotations.** For example, `@Override` is used to request checking whether a method actually overrides/implements a method according to Java rules; `@SuppressWarnings` instructs the compiler to suppress certain groups of warnings within a valid scope. Both of these standard annotations use SOURCE retention according to Java SE 17. No runtime reflection is needed for them to take effect.

**Annotation processors process custom annotations.** In Java, the `javax.annotation.processing` API allows a processor to access information about source elements and the annotations on them while `javac` is running. A custom SOURCE annotation is often used to:

- check compile-time conventions (naming/contract/required elements);
- generate Java source files or build resources via `Filer`;
- emit compilation warnings/errors using `Messager` when configuration is invalid;
- collect declaration information to generate code instead of relying on runtime annotation scanning.

**You need to register or specify the processor** via build/`javac` configuration. Simply creating `@interface MyAnnotation` with SOURCE retention **does not automatically produce business logic, custom checks, or code generation**. The compiler still checks annotation syntax and language rules; any custom behavior must be implemented by a processor or another tool.

## 6. Java 17 Experiment: An Annotation Processor Reads SOURCE and Then It Disappears

This experiment directly demonstrates that **a SOURCE annotation can be processed when compiling source code yet is no longer present on the class file after compilation**.

Create three files in the same directory. The example uses the default package to simplify the `javac` commands; in real projects, you should organize them into separate packages.

**File `SourceTag.java` — annotation retained only in source:**

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface SourceTag {
    String value();
}
```

**File `PrintSourceTagProcessor.java` — processor reading the annotation at compile time:**

```java
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;

@SupportedAnnotationTypes("SourceTag")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class PrintSourceTagProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        for (Element element
                : roundEnv.getElementsAnnotatedWith(SourceTag.class)) {
            SourceTag tag = element.getAnnotation(SourceTag.class);
            System.out.println("processing: "
                    + element.getSimpleName()
                    + " -> " + tag.value());
        }
        return true;
    }
}
```

**File `AnnotatedTask.java` — declaration annotated with SOURCE:**

```java
@SourceTag("validate-me")
class AnnotatedTask {}
```

Standing inside the directory containing all three files, compile the annotation and processor first:

```bash
javac --release 17 SourceTag.java PrintSourceTagProcessor.java
```

Next, compile the **source code** `AnnotatedTask.java` with the processor explicitly specified:

```bash
javac --release 17 -cp . -processorpath . -processor PrintSourceTagProcessor AnnotatedTask.java
```

Output actively printed by the processor:

```text
processing: AnnotatedTask -> validate-me
```

Finally, inspect the generated class:

```bash
javap -v AnnotatedTask
```

The full output of `javap` contains many details about the class file; **there is no `@SourceTag("validate-me")` usage** in the metadata of `AnnotatedTask.class`.

During compilation, `roundEnv.getElementsAnnotatedWith(SourceTag.class)` finds `AnnotatedTask`, and `element.getAnnotation(SourceTag.class)` retrieves the value `"validate-me"` from the annotation model in the processing phase. When the compiler emits the class file, the SOURCE usage is discarded. Thus, the two results do not contradict each other.

The example processor only **prints information** for observation; it neither generates code nor enforces any validation condition yet. To report a compilation error, a processor can use `processingEnv.getMessager().printMessage(Diagnostic.Kind.ERROR, ..., element)`; to create files, use `processingEnv.getFiler()`. Creating files or reading resources is not a built-in feature of SOURCE retention.

## 7. What SOURCE Can Do and What It Cannot Do

| Requirement | Is SOURCE suitable? | Explanation |
|---|---|---|
| Ask the compiler to verify a method override | Yes | For example `@Override`; behavior is defined by the compiler |
| Suppress certain compiler warnings | Yes | For example `@SuppressWarnings("unchecked")` |
| Processor generates code from source declarations | Yes | The processor is invoked during the build and sees SOURCE |
| Check conventions when the author compiles the relevant sources | Yes | If a processor/tool is configured, the annotation is present in that compilation pass |
| Framework uses reflection to read annotations at startup | **No** | SOURCE metadata is not in the class file |
| Runtime DI scans `@SourceTag` on beans | **No** | The scanner/runtime cannot read an attachment that has been discarded |
| Tool reads bytecode of a built library to find `@SourceTag` | **No** | The binary does not store SOURCE usages |
| Store configuration for runtime behavior decisions | **No** | Another storage option is needed, typically RUNTIME or generated data |
| Library compiled once, consumer wants to re-process SOURCE with only the JAR | **No, not by reading the original annotation** | The JAR does not carry the SOURCE attachment for a processor to recover |

We must distinguish between **a processor reading SOURCE while compiling source code** and **a processor reading annotations on a previously compiled class**. When the input consists only of bytecode, the SOURCE data at the usage site has already been discarded; an annotation processor cannot reconstruct what was not saved.

## 8. SOURCE Is Not the Same as @Target, and Does Not Guarantee Business Behavior

The two meta-annotations answer two different questions:

- `@Target`: **where** the annotation is allowed to be placed (class, method, field, parameter, type use, etc.).
- `@Retention`: **until which stage** the annotation is retained (SOURCE, CLASS, RUNTIME).

Example:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.SOURCE)
@interface Reviewed {
    String reviewer();
}

class Checkout {
    @Reviewed(reviewer = "team")
    void pay() {}
}
```

`@Reviewed` is valid on a method, and the compiler will check that the element value has the correct type. However, **there is no default Java rule** that automatically verifies the reviewer, creates an audit log, or blocks deployment. To enforce a rule like "reviewer must not be empty", you must write a custom processor or analysis tool. `@Target(METHOD)` does not affect the SOURCE policy, and `@Retention(SOURCE)` does not allow placing the annotation on locations outside `@Target`.

You can attach `@Documented` or other meta-annotations when appropriate for documentation needs; they do not automatically promote retention from SOURCE to RUNTIME.

## 9. Why Is SOURCE Often Useful for Build-Time Design?

Some information is only needed while building the software. Storing it in the binary may be unnecessary:

1. **The compiler needs it immediately when checking source code**, such as for warnings or overrides.
2. **A processor can transform the annotation into other artifacts** such as Java source files, metadata files, or diagnostics. Generated artifacts (if any) exist according to the processor's generation mechanism; the SOURCE usage itself still does not reside in the class file.
3. **Runtime has less dependency** on reading the original annotations. Runtime code should consume generated artifacts or runtime configuration according to the application's design.

For example, suppose a build-time framework has `@GenerateAdapter` with SOURCE retention. An annotation processor can generate an adapter class from the marked source. When the program runs, the adapter is already compiled like a regular class and works even though `@GenerateAdapter` is no longer in the bytecode. This is a **design with a code-generating processor**, not the default behavior of every SOURCE annotation.

Conversely, if a runtime framework uses `SomeClass.class.getAnnotation(...)` to decide handler registration, switching the annotation to SOURCE will prevent the runtime from reading it. In that case, `@Retention(RUNTIME)` is usually the more appropriate choice.

## 10. Common Misconceptions

### Mistake 1: Forgetting @Retention and assuming the annotation defaults to SOURCE

```java
@interface ConfigMarker {}

@ConfigMarker
class Component {}
```

The `ConfigMarker` annotation has a default retention of **CLASS**. For SOURCE, you need:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.SOURCE)
@interface SourceOnlyMarker {}
```

### Mistake 2: Using getAnnotation to read SOURCE at runtime

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.SOURCE)
@interface SourceAudit {}

@SourceAudit
class AuditJob {}

class AuditReader {
    static boolean check() {
        return AuditJob.class.isAnnotationPresent(SourceAudit.class);
    }
}
```

`check()` returns `false`. It does not prove that the source code never contained `@SourceAudit`; it proves that reflection does not see SOURCE annotations on the compiled class.

### Mistake 3: Thinking a SOURCE annotation will automatically trigger a processor

```java
@Retention(RetentionPolicy.SOURCE)
@interface Validate {}
```

This definition only selects the retention. A corresponding processor/compiler check and configuration are needed for that tool to run. Otherwise, `@Validate` is typically only checked by Java according to general annotation rules (name, elements, `@Target`, etc.).

### Mistake 4: Thinking SOURCE means the annotation definition file is not compiled

`SourceTag.java` is still a type declaration, and `javac` can still generate `SourceTag.class`. It is the metadata **on the annotated class**, such as `@SourceTag` on `AnnotatedTask`, that is discarded from `AnnotatedTask.class`.

### Mistake 5: Expecting a processor to process SOURCE from a pre-built JAR

If a JAR contains `AnnotatedTask.class` built from source that had `@SourceTag`, that annotation usage is no longer in the binary. A processor running in another project, seeing only the built class, cannot rediscover the original SOURCE metadata. If cross-project consumption is needed, design generated and packaged metadata artifacts, or choose another appropriate retention policy.

### Mistake 6: Changing retention to fix a missing processor issue

If the processor does not run due to build configuration, switching `SOURCE` to `RUNTIME` **will not automatically cause the processor to be invoked**. You need to check `-processor`, `-processorpath`, processor dependencies, and the build configuration. Retention governs metadata preservation, whereas processor activation is a separate matter.

### Mistake 7: Thinking SOURCE eliminates all impact on the build process

A SOURCE annotation can result in compiler diagnostics, or diagnostics and files generated by a processor. It disappears from the bytecode of the annotated target, yet **the decisions and artifacts produced during compilation can still affect the final program**. This explains why SOURCE is both absent at runtime and useful in code generation systems.

## 11. Choosing SOURCE or Another Retention?

Ask **who needs to read the annotation** and **at what time**:

| Design question | Recommended choice |
|---|---|
| Only the compiler or a processor compiling source needs the information? | `SOURCE` |
| A tool processing `.class` files after the build needs to read metadata? | Consider `CLASS` or `RUNTIME` depending on the tool |
| The application/framework reads the annotation via reflection at runtime? | `RUNTIME` |
| Is omitting the retention declaration acceptable? | Only when the default `CLASS` behavior is desired |
| Want to control where it can be attached (class, method, field...)? | Declare `@Target` **independently** of retention |

**Design rule:** choose the shortest retention that still satisfies the metadata consumer. If all decisions are completed at compile time, SOURCE usually expresses intent clearly and avoids putting annotation usages into the binary. If the runtime depends on the original metadata, SOURCE will not suffice.

## 12. Self-Check Exercises

**Exercise 1.** Declaration:

```java
@Retention(RetentionPolicy.SOURCE)
@interface CheckName {}

@CheckName
class Customer {}
```

After compilation, does `Customer.class.getAnnotation(CheckName.class)` return an annotation object?

**Answer:** no; it returns `null` because `@CheckName` on `Customer` has SOURCE retention and is not stored in the binary.

**Exercise 2.** Which policy does an annotation without `@Retention` belong to?

**Answer:** `RetentionPolicy.CLASS`. Do not assume SOURCE just because an annotation is used when writing source code.

**Exercise 3.** If a processor is invoked while `javac` compiles the file `Customer.java`, can it recognize `@CheckName`?

**Answer:** yes, if the processor is configured and handles the right annotation type. The SOURCE rule does not prevent a compile-time processor from accessing metadata from the source currently being compiled.

**Exercise 4.** If the processor is only run later in a project consuming `Customer.class` from a JAR without the `Customer.java` source code, can it still see `@CheckName`?

**Answer:** no. The SOURCE usage has already been discarded from the binary, so the processor cannot recover it from the JAR alone.

**Exercise 5.** A framework uses reflection to scan annotations on classes at startup. Choose SOURCE or RUNTIME?

**Answer:** `RUNTIME`, because the framework needs to read annotations at runtime. SOURCE can be used if the architecture is changed so that a compile-time processor generates separate metadata/artifacts consumed by the runtime, though in that case the framework **no longer reads the SOURCE annotation directly via reflection**.

**Exercise 6.** Why can `javap -v Sample` display `ClassHint`, yet `Sample.class.isAnnotationPresent(ClassHint.class)` returns `false`?

**Answer:** CLASS stores the annotation attachment in the class file, whereas standard Java reflection does not expose that annotation at runtime; that is the difference between metadata **being present in the binary** and **being exposed to reflection at runtime**.

## References

- [Java SE 17 — RetentionPolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/RetentionPolicy.html): SOURCE, CLASS, RUNTIME, and the meaning of each level.
- [Java SE 17 — @Retention](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Retention.html): meta-annotation declaring retention and the CLASS default.
- [JLS Java SE 17 `9.6.4.2 — Retention](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.2): mandatory rules when the compiler generates the binary, and exception cases.
- [Java SE 17 — Annotation Processing](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/package-summary.html): processor APIs and compile-time processing.
- [Java SE 17 — javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): the compiler tool and processor options.
