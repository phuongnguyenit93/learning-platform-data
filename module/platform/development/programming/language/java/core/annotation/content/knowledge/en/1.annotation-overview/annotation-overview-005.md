# Why Do Custom Annotations Need a Processor to Take Effect?

> **Key takeaway:** Custom annotations only attach **metadata (descriptive information)** to declarations or data types permitted by Java. Annotations themselves contain no mechanism to execute statements, intercept calls, check business rules, or generate code on their own. For metadata to change the outcome, there must be a component that **reads it, interprets it, and performs an action** at a specific time: at compile time, at application startup, or at runtime.

## 1. Distinguishing “declaring intent” from “executing behavior”

Suppose we write:

~~~java
@Audit
public void transferMoney() {
    // Perform money transfer
}
~~~

Reading the annotation name, we *expect* the method to be logged. However, Java does not inherently understand what `@Audit` means to log, when to log, where to send the log, or how to handle errors. If we create `@Audit` ourselves and no code reads it, `transferMoney()` still just runs its method body as normal. An annotation does not automatically insert `try/finally`, call a logger, or modify bytecode.

A custom declaration only defines the **metadata structure**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Audit {
    String action() default "unknown";
}
~~~

- `@interface Audit`: defines an annotation type and an `action` element of type `String`.
- `@Target(METHOD)`: the compiler checks that this annotation is only placed on methods.
- `@Retention(RUNTIME)`: metadata is retained until runtime so APIs such as reflection can read it.
- `default "unknown"`: provides a default value; it does not define a logging action.

Even with `@Retention(RUNTIME)`, the JVM does not automatically invoke an “annotation function” when the method is executed. Annotations also do not have `before()` or `after()` methods in the sense of callbacks; annotation elements only return metadata values.

### Built-in annotations are a different case

For example, `@Override` is recognized by the **Java compiler** and used to check whether a method actually overrides one; `@FunctionalInterface` is also checked by the compiler. `@Deprecated` can trigger warnings at usage sites; `@SuppressWarnings` instructs the compiler or related tools on how to handle warnings. That effect exists because **the tools were programmed to understand them**, not because every annotation inherently has the ability to control a program. Defining a custom `@MyOverride` with a similar name does not make `javac` apply the rules of `@Override`.

## 2. “Annotation processors” can operate at multiple stages

| Stage | Component reading the annotation | What effects can it produce? | Examples |
| --- | --- | --- | --- |
| **Compile time** | JSR 269 standard annotation processor, executed via `javac` | Inspect source code structure, emit errors/warnings, generate new source files or resources | MapStruct generating mapper code; custom processors checking conventions |
| **Startup / runtime configuration** | Framework scanning classes, methods, fields, and metadata | Register components, build mapping metadata, set up interceptors/proxies | Spring discovering `@Component`, `@RequestMapping` |
| **While the application is running** | Reflection, frameworks, interceptors, proxies, or custom business code we write | Read annotation values and decide whether to perform an action | Bean Validation running validators; an interceptor writing logs |
| **Build / bytecode tooling** | Tools that read class files or transform bytecode | Analyze or transform artifacts depending on the tool | Instrumentation or class-file analysis tools |

The term “processor” in the question should be understood **broadly** as a *metadata consumer/handler*. Specifically, `javax.annotation.processing.Processor` is an API **only for the compile-time phase**. An application can use reflection to process annotations at runtime without writing any `AbstractProcessor`.

Conceptual flow:

~~~text
Declare @MyAnnotation on a Java element
                  |
                  v
         Annotation / metadata
                  |
         Does anything read it?
          /                  \
        No                   Yes
         |                    |
         v                    v
No additional          Read values +
behavior occurs        apply a rule
                              |
                              v
                      Observable effect
~~~

Java can check syntax, element types, and annotation placement without a separate processor. These basic checks are **not equivalent** to executing the business logic intended by the annotation author.

## 3. Runtime example: an annotation does not run until code reads it

Create the file **`AnnotationDemo.java`** below. All types are in the default package, so it can be compiled standalone with Java 17+.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Label {
    String value();
}

class Worker {
    @Label("Quan trọng")
    void run() {
        System.out.println("Worker.run()");
    }
}

public class AnnotationDemo {
    public static void main(String[] args) throws NoSuchMethodException {
        Worker worker = new Worker();

        // Normal method call: the JVM does not print the label automatically.
        worker.run();

        // This is the code that actively processes the metadata.
        Method method = Worker.class.getDeclaredMethod("run");
        Label label = method.getAnnotation(Label.class);
        if (label != null) {
            System.out.println("Nhãn: " + label.value());
        }
    }
}
~~~

Compile and run:

~~~bash
javac AnnotationDemo.java
java AnnotationDemo
~~~

Expected output:

~~~text
Worker.run()
Nhãn: Quan trọng
~~~

Look at the two points in time:

1. `worker.run()` prints the single line `Worker.run()`, regardless of whether `@Label` is present.
2. Afterward, **the code inside `main` itself** retrieves the `Method`, calls `getAnnotation(Label.class)`, and uses `label.value()` to print the second line.

If you remove the reflection block, the method still runs and there is no `Nhãn: Quan trọng` line. If you change `@Retention(RUNTIME)` to `@Retention(CLASS)` and recompile, the `getAnnotation(Label.class)` call returns `null`, leaving only the `Worker.run()` line. The `CLASS` case can still be processed by tools that read class files; only **runtime reflection via the API above** cannot see that annotation.

### Who finds the annotated elements?

In the example, we already know `Worker.class` and the name `run`. With many classes, an application needs a mechanism to find the classes to inspect (manual registration, a list of classes, or a library/framework scanning the classpath), and only then uses reflection to read annotations. `@Retention(RUNTIME)` only ensures metadata is present when read; it **does not automatically scan the entire project**.

If you want `@Audit` to automatically log around method calls in an application, there must be wrapper code around the call, an interceptor, a proxy, or an appropriate instrumentation/bytecode mechanism. Merely writing a reflection loop at startup is not enough to intercept calls to methods.

## 4. Compile-time example: a processor reads annotations during `javac`

Sometimes we want to inspect or generate code **before running the application**. Java supports annotation processing under JSR 269 via `javax.annotation.processing`. The following example uses a simple processor to emit a compiler note, clearly illustrating that the behavior resides in the *processor*.

Create three files in the same directory.

**File `DemoTag.java`:**

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface DemoTag {
    String value();
}
~~~

**File `TagProcessor.java`:**

~~~java
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("DemoTag")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class TagProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        for (Element element : roundEnv.getElementsAnnotatedWith(DemoTag.class)) {
            DemoTag tag = element.getAnnotation(DemoTag.class);
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.NOTE,
                    "Tag: " + element.getSimpleName() + " -> " + tag.value(),
                    element);
        }
        return true;
    }
}
~~~

**File `Example.java`:**

~~~java
@DemoTag("demo")
public class Example {
    public static void main(String[] args) {
        System.out.println("Example chạy bình thường");
    }
}
~~~

Run with JDK 17 or newer:

~~~bash
javac DemoTag.java TagProcessor.java
javac -cp . -processor TagProcessor Example.java
java Example
~~~

When compiling `Example.java`, the compiler will display a **note containing** `Tag: Example -> demo` (the position, prefix, and diagnostic formatting may vary by environment). When running the program, the exact stdout is:

~~~text
Example chạy bình thường
~~~

**Key observation:** The content `Tag: Example -> demo` is a diagnostic from **compilation**, not the result of the JVM automatically handling `@DemoTag`. `DemoTag` has `RetentionPolicy.SOURCE`, so it does not even need to exist at runtime for the compile-time processor to read it.

How the processor works in this example:

1. `javac` receives the processor via the `-processor TagProcessor` option.
2. `@SupportedAnnotationTypes` indicates that the processor is interested in the `DemoTag` type.
3. `process(...)` is invoked across processing rounds; `RoundEnvironment` provides the annotated elements.
4. `process` reads the elements and metadata, then calls `Messager` to emit diagnostics.
5. After compilation, the `Example` program executes completely independently of the processor's diagnostic output.

In real-world projects, processors are typically packaged into a separate dependency, declared on the **annotation processor path**, or registered with the build tool. Processors like MapStruct can also use `Filer` to generate new Java files in subsequent rounds. The standard JSR 269 API is primarily intended for **analysis, validation, and generating new files**; it does not directly allow arbitrarily replacing the body of an existing method. Libraries that intervene deeply in the AST/compiler, such as Lombok, rely on their own mechanisms outside the scope of a pure annotation processor.

**Note on JDK versions:** Do not rely on a processor being “accidentally” discovered from the classpath. Configure the processor explicitly with `-processor`, `-processorpath`, or the corresponding build configuration; JDKs and build tools differ in how they automatically discover and run processors. Because the example uses `-processor`, it does not depend on that default behavior.

## 5. What do Retention and Target determine?

| Declaration | How long is metadata retained? | Suitable processor |
| --- | --- | --- |
| `RetentionPolicy.SOURCE` | Only in source code / during compiler processing; not stored in the class file | Compile-time annotation processor |
| `RetentionPolicy.CLASS` | Stored in the class file; not directly accessible via default runtime reflection | Class-file reading/transformation tools |
| `RetentionPolicy.RUNTIME` | Stored in the class file and accessible via reflection at runtime | Reflection, runtime frameworks, or class-file tools |

If `@Retention` is omitted, the default is `CLASS`. `@Target` only specifies valid placement targets (for example `TYPE`, `METHOD`, `FIELD`, `PARAMETER`, `ANNOTATION_TYPE`, `TYPE_USE`). An annotation with the right target and retention **still has no business behavior** if there is no consumer that understands it.

In particular, just because runtime reflection can see an annotation does not mean your framework will apply it. The framework must locate the right class/method, read the right annotation type, and have the corresponding handling logic. Conversely, a compile-time processor can still read a `SOURCE` annotation that is invisible at runtime.

## 6. Connecting to Spring, validation, and familiar libraries

**Spring `@Component`:** The Spring container has a mechanism to register beans through configuration and component scanning. The annotation marks a class as a candidate; when you create an object with `new` without putting it into the container, simply adding `@Component` does not cause that object to be managed automatically.

**Spring `@Transactional`:** Transaction management infrastructure (commonly using proxies for calls through a Spring bean) inspects the metadata and opens/closes transactions according to configuration. Creating an instance yourself with `new` or calling another method on the same instance (self-invocation in common proxy mode) may bypass the interceptor. The annotation itself does not start a transaction. The exact mechanism also depends on proxy/AspectJ and project configuration.

**Bean Validation `@NotNull`:** A constraint takes effect when there is a provider/validator executing it, for example a `Validator.validate(object)` call or an integration that triggers validation when handling a request. Simply placing a constraint on a field does not automatically block every value assignment in Java. If creating a custom constraint, you typically need the constraint annotation, a `ConstraintValidator`, valid configuration, and a validation trigger point.

**MapStruct `@Mapper`:** An annotation processor generates the implementation class at build time; at runtime, the compiled class is used. If the processor is not run, you will not have the corresponding generated code, even though the interface type and annotation may still be syntactically valid.

These examples share a common formula:

~~~text
Annotation (metadata declaration)
    + Discovery/reading component
    + Processing rules
    + Activation timing
    = Observable behavior
~~~

## 7. When designing your own annotation, what do you need to decide?

Answer these four questions in order before creating a new annotation:

1. **What does it mark?** Define the allowed Java elements using `@Target`, required/optional attributes, and default values.
2. **Who will read it?** Choose a compile-time `Processor`, direct reflection code, framework integration, a proxy/interceptor, or a class-file tool.
3. **When is it read?** At compile time, during container initialization, during validation, or before/after each call? Choose the appropriate `@Retention`.
4. **What happens if the processor or configuration is missing?** Will there be a build error, missing generated classes, an optional process skipped, or an error detected at runtime? Design error messages and test the behavior.

For example, if the goal is “every method annotated with `@Audit` must be logged when invoked”, merely declaring `@Audit` is not enough. You need to choose a mechanism that wraps the call; register it in the appropriate lifecycle; read the method's metadata; log according to policy; and test both proxy calls and direct calls. If you cannot control all call paths, you should not claim that auditing is always applied.

Using annotations is appropriate when you want declarative configuration repeated across many elements and already have a clear, centralized processor. For an action that only needs to be called in one place, a regular method call is sometimes more transparent and easier to test.

## 8. Common misconceptions

- **“Having `@Retention(RUNTIME)` makes an annotation work automatically.”** False: that is only the condition for reflection to see the metadata, not a processor.
- **“Every annotation is handled by `AbstractProcessor`.”** False: `AbstractProcessor` is for compile time; Spring and many frameworks have their own runtime mechanisms.
- **“`@Target` and `@Retention` define business logic.”** False: they only specify where the annotation can be placed and how long metadata is retained.
- **“Declaring the dependency containing the annotation is enough.”** False when a processor is needed: you must configure how to trigger the processor or the corresponding runtime infrastructure; sometimes the annotation API and the processor reside in two separate dependencies.
- **“A compile-time processor runs again when the application executes.”** False: generated code/diagnostics happen at compile time; runtime processing requires a separate runtime component.
- **“Reflection finding an annotation means every call is intercepted.”** False: reflection only reads; interception requires an execution mechanism wrapping the call path.

## 9. Self-check for understanding

**Question 1.** You create `@TrackTime` with `@Retention(RUNTIME)` and apply it to 10 methods. There is no code reading it yet. Will timing logs appear automatically?

**Answer:** No. The metadata is readable, but there is no interceptor/proxy or other code measuring time and writing logs.

**Question 2.** An annotation only needs to enforce the rule “a misnamed class must report an error at compile time”—when should it be processed?

**Answer:** At compile time using an annotation processor; `SOURCE` is usually sufficient if the metadata is not needed after compilation.

**Question 3.** Why might a runtime annotation using `RetentionPolicy.CLASS` not be read by Spring or reflection?

**Answer:** Standard reflection does not directly expose `CLASS` annotations. Handling such metadata requires an appropriate class-file reading tool, or using `RUNTIME` when the integration requires reflection (note that some frameworks have their own metadata readers).

**Question 4.** What makes `@Transactional` take effect when Spring manages a method?

**Answer:** The transaction infrastructure is configured, locates the metadata, and executes transaction advice through a supporting mechanism (usually a proxy); the annotation only provides the declaration.

**Mini exercise:** Using `AnnotationDemo.java` from Section 3, remove only the reflection part and run it again; compare stdout. Then restore it and change retention from `RUNTIME` to `CLASS`. Explain each result using three factors: **where the metadata exists, who reads it, and what action is performed by the code**.
