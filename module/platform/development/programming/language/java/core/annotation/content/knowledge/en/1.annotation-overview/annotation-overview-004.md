# Three Ways to Consume Annotations in Java: Compiler, Tooling, and Runtime

An annotation is **metadata** attached to a Java element such as a class, method, or field. It describes additional information about that element for **another party to read and process**. The `@...` marker itself does not execute logic, perform business checks, or create behavior for an object on its own.

An annotation can be consumed in three ways:

1. **The compiler** understands the annotation and performs checks/warnings according to language rules.
2. **Tooling** reads the annotation to analyze, check, generate code, or generate documentation; an annotation processor is a key example.
3. **The running program (runtime)** reads annotations that remain in the class file, usually via Reflection, and then decides to execute behavior.

These three approaches can appear in the same project, but **who reads it, at which stage it is read, and what the result is** must be distinguished.

## 1. Map of the Three Consumption Approaches

| Perspective | When? | Who reads it? | Typical effect | Examples |
| --- | --- | --- | --- | --- |
| Compiler | When `javac` compiles the code | The Java compiler | Checks declarations, emits warnings, or suppresses a group of warnings | `@Override`, `@Deprecated`, `@SuppressWarnings` |
| Tooling | Typically during the build or in a separate analysis task | Annotation processors, IDEs, code/documentation generators, bytecode readers | Checks conventions, emits diagnostics, generates code/files, builds indexes | Processor reading `@ToolHint` |
| Runtime | Once the program is running | Application/library/framework code | Reads metadata to register, route, invoke handlers, or change configuration | `Class.getAnnotation(...)`, frameworks scanning annotations |

Conceptual flow:

```text
.java source code with annotations
        |
        +--> javac: compiler rules (@Override, @Deprecated, ...)
        |
        +--> processor/tool: analyze, check, generate code (when configured)
        |
        v
      Class file .class
        |
        +--> SOURCE metadata: not stored in .class
        +--> CLASS metadata: stored in .class, not visible via standard Reflection
        +--> RUNTIME metadata: stored in .class, readable by Reflection
        |
        v
Running program: code actively queries and processes annotations
```

An annotation can serve **multiple consumers**. For example, `@Deprecated` is used by the compiler to warn when calling an old API and can also be read by analysis tools. The fact that an annotation exists in a class file does not mean the program automatically uses it.

## 2. The First Way: The Compiler Consumes Annotations

These are the annotations that `javac` knows how to handle according to Java's rules:

- `@Override`: confirms that a method actually overrides or implements a valid method from a supertype. Mistyping the name/signature causes a compilation error instead of silently creating a new method.
- `@Deprecated`: marks an API as no longer recommended; the compiler may emit a warning where that API is used, depending on context and warning options. The `since` and `forRemoval` attributes provide additional information.
- `@SuppressWarnings("deprecation")`: instructs the compiler to ignore the deprecation warning category within the scope of the annotated declaration. It does not remove the old API, does not suppress other compilation errors, and does not change runtime behavior.

**Example 1 — compiler checks and runtime metadata reading in the same program.** Create the file `AnnotationConsumersDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RuntimeLabel {
    String value();
}

@RuntimeLabel("catalog")
class Catalog {
    @Deprecated(since = "17")
    static String legacyName() {
        return "legacy";
    }
}

public class AnnotationConsumersDemo {
    @SuppressWarnings("deprecation")
    public static void main(String[] args) {
        RuntimeLabel label = Catalog.class.getAnnotation(RuntimeLabel.class);
        System.out.println(label == null ? "<không tìm thấy>" : label.value());
        System.out.println(Catalog.legacyName());
    }

    @Override
    public String toString() {
        return "demo";
    }
}
```

In the directory containing the file, using **JDK 17 or later**:

```bash
mkdir out
javac --release 17 -d out AnnotationConsumersDemo.java
java -cp out AnnotationConsumersDemo
```

Exact stdout:

```text
catalog
legacy
```

**Breakdown by consumer:**

1. The compiler verifies that `toString()` actually overrides `Object.toString()` thanks to `@Override`. Try changing the signature to `toString(int n)` while keeping `@Override`: compilation fails.
2. The compiler knows that `Catalog.legacyName()` is marked `@Deprecated`. `@SuppressWarnings("deprecation")` on `main` suppresses the deprecation warning at the call site inside this method; you can see the warning by removing the suppress annotation and compiling with `-Xlint:deprecation`.
3. The runtime does not "execute `@RuntimeLabel`". It is the call `Catalog.class.getAnnotation(RuntimeLabel.class)` that **actively reads** the metadata, and then our code prints `value()` to the screen.
4. Calling `Catalog.legacyName()` still returns `"legacy"`. `@Deprecated` does not disable the method.

`--release 17` here keeps the example compatible with Java 17 language/APIs when using a newer JDK. The file name must be `AnnotationConsumersDemo.java` because it contains `public class AnnotationConsumersDemo`.

### The Compiler Does Not Automatically Understand Every Custom Annotation

If you create your own `@Audit` or `@CheckAccess` annotations, `javac` only checks the **valid usage** of the annotation (element types, `@Target`, required values, etc.). The compiler does not guess business meaning such as "log when the method is called" or "block users who are not logged in". To achieve that effect, there must be a processor, tool, or runtime code that actually processes the annotation.

## 3. The Second Way: Tooling Consumes Annotations

**Tooling** is a broader category than annotation processors. IDEs can analyze source code, documentation generators can read annotations, build tools can scan class files, and libraries can generate code based on annotations. In Java, the most common way to learn this mechanism is the **annotation processing API** (`javax.annotation.processing`, JSR 269).

A processor runs **during compilation when enabled**, yet has a responsibility distinct from `javac`'s built-in checks. It receives a model of program elements, finds elements marked with annotations, and then emits diagnostics or generates additional files using the provided API. A processor does not need to run the application program.

**Example 2 — a processor reading an annotation that exists only in source.** Create three files in the same directory, without a `package` declaration to focus on the mechanism.

File `ToolHint.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface ToolHint {
    String value();
}
```

File `ToolHintProcessor.java`:

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

@SupportedAnnotationTypes("ToolHint")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class ToolHintProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        for (Element element : roundEnv.getElementsAnnotatedWith(ToolHint.class)) {
            ToolHint hint = element.getAnnotation(ToolHint.class);
            processingEnv.getMessager().printMessage(
                Diagnostic.Kind.NOTE,
                "ToolHint: " + element.getSimpleName() + " => " + hint.value(),
                element
            );
        }
        return true;
    }
}
```

File `ImportantService.java`:

```java
@ToolHint("review endpoint contract")
public class ImportantService {
}
```

**Execute in order** (with JDK 17+):

```bash
mkdir out
javac --release 17 -d out ToolHint.java ToolHintProcessor.java
javac --release 17 -cp out -processorpath out -processor ToolHintProcessor -d out ImportantService.java
```

In the second step, `javac` displays a diagnostic of kind `NOTE` with the main message:

```text
ToolHint: ImportantService => review endpoint contract
```

The file name, line number, and caret details displayed by the compiler around the diagnostic may vary across versions/tools. This is **a message emitted by the processor during compilation**, not the stdout of the `ImportantService` program.

Key points explained:

- `@Retention(SOURCE)` allows the processor to see `@ToolHint` in the source; the annotation **does not need to exist in the `ImportantService.class` file**.
- `@Target(TYPE)` restricts usage to types such as classes/interfaces; you cannot arbitrarily move `@ToolHint` onto a local variable.
- `@SupportedAnnotationTypes("ToolHint")` declares the annotation the processor is interested in; use the fully qualified name with package in real-world implementations.
- `RoundEnvironment.getElementsAnnotatedWith(ToolHint.class)` finds matching elements in the current processing round. A processor can be invoked across multiple rounds, especially when code is generated; this example simply prints a note for the elements found.
- `processingEnv.getMessager()` sends diagnostics to the compiler. In a real project, a processor can also use `Filer` to generate source or resource files.
- `-cp out` lets the compiler see the application's `ToolHint` type; `-processorpath out` specifies where to find the processor; `-processor ToolHintProcessor` instructs it to run that specific processor. You can register processors for automatic discovery via a service descriptor in a real build.

Try omitting `-processor ToolHintProcessor` in the second compile command **and making sure no processor is auto-registered**: `ImportantService` is still a valid Java class, but there will be no custom message from `ToolHintProcessor`. This shows that declaring an annotation alone is not enough to trigger a tool.

**Important distinction:** the compiler and a processor can both run during the `javac` command, but `@Override` is a rule checked automatically by the Java compiler itself, whereas `@ToolHint` is only interpreted according to the logic we write in `ToolHintProcessor`.

## 4. The Third Way: The Program at Runtime Consumes Annotations

When using `@Retention(RUNTIME)`, the necessary annotation information is retained in the class file so that the running program can read it via Reflection. Application code or a framework decides what to do with the information read.

In Example 1:

```java
RuntimeLabel label = Catalog.class.getAnnotation(RuntimeLabel.class);
if (label != null) {
    String name = label.value();
    System.out.println(name);
}
```

`getAnnotation(RuntimeLabel.class)` returns an object representing the annotation if that annotation type is present according to Reflection rules; it can return `null` if not found. Therefore, check for null before reading values when you are not certain the annotation exists.

Common APIs:

| API | Where it reads from | What to keep in mind |
| --- | --- | --- |
| `Class.getAnnotation(YourAnnotation.class)` | Annotations on a class | May consider inheritance according to `@Inherited` rules |
| `Class.getDeclaredAnnotation(YourAnnotation.class)` | Annotations declared directly on a class | Does not look up inherited annotations |
| `Method.getAnnotation(...)` | Annotations on a method | Must obtain the exact `Method` object first |
| `Field.getAnnotation(...)` | Annotations on a field | Must obtain the exact `Field` object first |
| `AnnotatedElement.getAnnotationsByType(...)` | Retrieves annotations by type, including valid repeated cases | Useful with `@Repeatable` |

Framework example: a framework may scan classes/methods for routing, mapping, or configuration annotations and then register the corresponding handlers. **The framework actively processes annotations**; the JVM does not automatically see `@Something` and invoke a business method.

Reflection only lets us **read metadata**; it does not implicitly enforce access rules, dependency injection, transactions, or validation. For behavior to happen, there must be a component that implements it and is triggered at the right time.

## 5. `@Retention` Determines Which Consumers Can See It

The three policies in `java.lang.annotation.RetentionPolicy`:

| Policy | Retained in `.class`? | Readable by standard Reflection at runtime? | Suitable scenarios |
| --- | --- | --- | --- |
| `SOURCE` | No | No | Source-level hints/checks, annotation processors |
| `CLASS` | Yes | No | Tools that analyze or transform bytecode after compilation |
| `RUNTIME` | Yes | Yes | Runtime logic reading via Reflection |

If you **do not declare `@Retention`**, the default is `RetentionPolicy.CLASS`.

In Example 1, try changing:

```java
@Retention(RetentionPolicy.RUNTIME)
```

to:

```java
@Retention(RetentionPolicy.CLASS)
```

Recompile and run: the first line will be `<không tìm thấy>`, while the second line is still `legacy`. Metadata of type `RuntimeLabel` cannot be retrieved via standard Reflection under the `CLASS` policy, even though that annotation may still be recorded in the class file.

You should distinguish between **annotations stored in bytecode** and **annotations exposed by Reflection**. A bytecode reading/transformation tool can still inspect a `CLASS` annotation, whereas `Catalog.class.getAnnotation(RuntimeLabel.class)` cannot read it.

`@Target` answers a different question: **where** an annotation is allowed to be placed; it does not determine whether the runtime can read it. In the examples, `@Target(TYPE)` allows annotating a class, whereas `@Retention(RUNTIME)` or `SOURCE` determines the retention lifecycle.

A few additional notes:

- `@Inherited` only takes effect under specific conditions for annotations on a **class** when queried through the inheritance mechanism; it does not make annotations on methods or interfaces inherited the way annotations on a superclass are.
- An annotation with `RUNTIME` does not guarantee that a tool or framework will scan that target. It also depends on scan scope, class loader, initialization timing, and processing logic.
- An annotation processor can read `SOURCE` during compilation rounds; inferring that "the processor also reads via runtime Reflection on application classes" is wrong about the mechanism in the example.
- `@SuppressWarnings` is not a security tool; it only affects supported compiler warnings.

## 6. Choosing a Consumption Approach for Real-World Needs

| Goal | Where to start | Why? |
| --- | --- | --- |
| Catch method overriding mistakes right when writing code | `@Override` with the compiler | Detected before running, no infrastructure needed |
| Warn about old APIs and migrate APIs gradually | `@Deprecated` with compiler/IDE checks | Notifies API users |
| Enforce structural rules and generate code during the build | Annotation processor/tool | Build-time analysis; can fail the build or generate resources |
| Register handlers, configuration, or mappings at runtime | `RUNTIME` annotation + scanning/processing code | Makes decisions based on metadata when the application starts or runs |
| Scan compiled metadata without running the application | A `.class` reader tool | Can analyze both `CLASS` and `RUNTIME` via bytecode |

The timing of processing should be chosen intentionally. If an error can be fully verified at compile time, early checking usually gives good feedback. If a decision depends on runtime state, there must be a component running in practice to handle it. Both can be combined when there is a reason to do so.

## 7. Common Misconceptions

**"Having an annotation means the behavior runs automatically."** False: applying an annotation only attaches metadata. In Example 2, the message appears because `ToolHintProcessor` was configured and executed; in Example 1, the string `catalog` is printed because the code actively calls `getAnnotation`.

**"Any annotation can be read with Reflection."** False: with `SOURCE` or `CLASS`, the program cannot read that annotation using standard Reflection; `RUNTIME` is required for the runtime annotation retrieval approach shown in this article.

**"SOURCE is useless because it gets stripped at compile time."** False: a processor can already use that annotation **before** it is omitted from the class file.

**"Annotation processors and reflection are the same thing."** False: a processor works with a code model during the compile-time processing phase; reflection queries information on loaded types/members while the program is running.

**"`@Deprecated` or `@SuppressWarnings` changes the result of a method."** False: they are primarily concerned with information/warnings; they do not make a method stop working or get called differently.

**"Setting `RUNTIME` is enough for a framework to handle it."** False: the framework must actually scan, recognize, and process that annotation; the scan scope must also be configured properly.

## 8. Self-Check

1. Keep `@RuntimeLabel("catalog")` but change the retention to `SOURCE`, then recompile and rerun Example 1. Predict the result of `getAnnotation` and explain why.
2. In Example 2, why can `@ToolHint` still be read by the processor even though it uses `SOURCE`? What happens if the processor is not enabled?
3. Place `@ToolHint` on a local variable. Why does the compiler reject it even when the processor is not running?
4. A library wants to read annotations from loaded classes at application startup: which retention is needed and what additional processing component is required?
5. Distinguish between "the compiler automatically checks `@Override`" and "the processor defines custom rules for `@ToolHint`" in one sentence.

**Suggested answers:** (1) `getAnnotation` returns `null`, and the first line in the example will print `<không tìm thấy>`; (2) the processor reads the source model during compilation, and if the processor is not run, its diagnostic will not appear; (3) `@Target(TYPE)` does not permit `LOCAL_VARIABLE`; (4) `RUNTIME` and code/a framework that actually reads and processes the metadata; (5) the `@Override` rule belongs to the Java compiler, whereas the `@ToolHint` rule resides in a developer-supplied processor.

## 9. Key Takeaway

When encountering a new annotation, ask yourself in sequence: **Who is the consumer? At which stage is it read? Does the metadata persist long enough for that consumer? Where does the processing logic live?** These four questions help accurately distinguish the roles of the compiler, tooling, and runtime without mistakenly attributing behavior to the annotation itself.
