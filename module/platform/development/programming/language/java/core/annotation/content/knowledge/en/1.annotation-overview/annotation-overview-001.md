# Annotations in Java and the Role of Metadata

## 1. What Is an Annotation?

**An annotation** is a way to attach **metadata** to an element of a Java program using syntax that starts with the `@` sign. The annotated element can be a class, method, field, parameter, constructor, or other locations permitted by the annotation type.

**Metadata** means “data that describes data.” In Java code, an annotation describes additional information about an element: *what that element means, how it needs to be checked, or how a tool/framework should process it*. For example:

```java
class Task {
    @Override
    public String toString() {
        return "Task";
    }
}
```

`@Override` tells the compiler that `toString()` is defined to override a method in a supertype. If a developer writes the signature incorrectly to the point where the method does not actually override, the compiler will report an error. Here, the annotation helps detect the error; it does not itself change the logic that returns `"Task"`.

Unlike comments using `//` or `/* ... */` intended primarily for human readers, annotations have a structure recognized by Java, so the compiler, build tools, libraries, or frameworks can inspect and process them according to defined rules.

## 2. The Role of Annotations: Describing to Be Processed by Another Party

An annotation by itself **is not a statement that executes business logic**. Placing `@Something` on a method does not cause that method to run automatically. An effect only occurs when **a mechanism that understands that annotation** reads and processes it.

| Who Processes It? | When | Example | Effect |
| --- | --- | --- | --- |
| Java compiler | At compile time | `@Override` | Checks whether the method actually overrides. |
| Java compiler | At compile time | `@SuppressWarnings("unchecked")` | Instructs the compiler to suppress the specified warning category within the appropriate scope; does not fix the cause of the warning. |
| Annotation processor | During compilation | Annotations defined by libraries/tools | Can check rules, emit error messages, or generate additional code/resources. |
| Framework/library | At startup or at runtime | JUnit's `@Test`, Spring's `@Transactional` | The framework finds the annotation and applies the mechanism implemented by **the framework itself**. |
| Code using Reflection | At runtime, if the annotation is retained until runtime | Custom annotation with `@Retention(RUNTIME)` | The program reads the metadata and then decides how to proceed. |

For example, in Spring, having `@Transactional` on a method does not mean the JVM automatically opens a transaction. Spring must manage the object and apply the corresponding transaction mechanism; the specific behavior also depends on how the method is invoked and the Spring configuration.

As a result, annotations separate **declarative information** from **the code that executes the mechanism**: developers mark their intent right next to the relevant element, while tools process it centrally according to their own rules.

## 3. Syntax and Data Inside Annotations

Common syntax:

- Passing no elements: `@Override`, `@Deprecated`.
- Passing a named element: `@SuppressWarnings(value = "unchecked")`.
- Shorthand when assigning only the element named `value`: `@SuppressWarnings("unchecked")`.
- Passing multiple elements: `@Info(author = "Lan", version = 2)` (with `@Info` defined as in the example below).

Values in an annotation are **declarative and fixed at compile time**. Permitted element types include primitive types, `String`, `Class`, enums, other annotation types, and one-dimensional arrays of those types. You cannot use an arbitrary object, a value obtained from a running request, or a local variable that changes at runtime as an element value.

Java provides several built-in annotations such as `@Override`, `@Deprecated`, and `@SuppressWarnings`. We can also define custom annotations using the `@interface` keyword. A custom annotation type typically has **elements** that look like parameterless method declarations and can have default values.

## 4. Complete Example: Defining, Applying, and Reading an Annotation

Create the file **`AnnotationDemo.java`** with the following content. The example uses Java 17+ and requires only the JDK, without Spring or external libraries.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Info {
    String author();
    int version() default 1;
}

public class AnnotationDemo {
    @Info(author = "Lan", version = 2)
    public void process() {
        System.out.println("Đang xử lý");
    }

    public static void main(String[] args) throws NoSuchMethodException {
        Info info = AnnotationDemo.class
                .getDeclaredMethod("process")
                .getAnnotation(Info.class);

        System.out.println(info.author());
        System.out.println(info.version());
    }
}
```

Compile and run in the directory containing the file:

```bash
javac -encoding UTF-8 AnnotationDemo.java
java AnnotationDemo
```

Standard output (stdout):

```text
Lan
2
```

Step-by-step explanation:

1. `@interface Info` declares an **annotation type**, consisting of a required `author()` and `version()` defaulting to `1`.
2. `@Target(ElementType.METHOD)` restricts `@Info` to method declarations. Applying it to a class will be rejected by the compiler.
3. `@Retention(RetentionPolicy.RUNTIME)` requests retaining metadata of `@Info` so running code can retrieve it via Reflection.
4. `@Info(author = "Lan", version = 2)` places two metadata values onto the `process()` method.
5. `getDeclaredMethod("process")` retrieves the Reflection object describing the method; `getAnnotation(Info.class)` reads the annotation; `author()` and `version()` read the two values.

Important observation: the output **does not contain the line `Đang xử lý`**, because `main` never called `process()`. Simply attaching and reading an annotation does not trigger the method body. To produce actual behavior, we must write code that processes the metadata, or delegate to a framework that supports processing that annotation.

If `version = 2` is omitted at the usage site, `info.version()` returns the default value `1`. If `@Retention(RetentionPolicy.RUNTIME)` is removed, the custom annotation defaults to `CLASS` retention; a standard `getAnnotation(Info.class)` call returns `null`, so the example needs to be adjusted before accessing elements.

## 5. Where Are Annotations Kept and When Are They Read?

Annotations start in the **source code**. Depending on the *retention policy*, that information may only be useful at compile time or may also be written into the `.class` file.

| `RetentionPolicy` | Present in source code? | Saved into `.class`? | Readable via standard Reflection at runtime? |
| --- | --- | --- | --- |
| `SOURCE` | Yes | No | No |
| `CLASS` | Yes | Yes | No |
| `RUNTIME` | Yes | Yes | Yes |

Here are two common processing flows:

```text
Source code with @Annotation
    |
    +--> javac / annotation processor --> checks, warnings, code generation at compile time
    |
    +--> .class file (if retention is CLASS or RUNTIME)
              |
              +--> Reflection / framework at runtime
                   (reads only annotations with RUNTIME retention)
```

**Do not confuse `@Retention` with `@Target`:**

- `@Retention` determines up to which stage an annotation persists.
- `@Target` determines where an annotation can be attached.

These two annotations are **meta-annotations**: annotations used to describe another annotation type itself. Other meta-annotations include `@Documented` (related to appearing in Javadoc), `@Inherited` (certain annotations on a class can be inherited by subclasses according to Reflection rules), and `@Repeatable` (allows repeated occurrences). Not every annotation can be used in every location or is automatically inherited.

## 6. How Are Annotations Applied in Practice?

**In plain Java:**

- `@Override` helps the compiler check the intent to override a method. Proper overriding still occurs according to Java rules even without writing `@Override`, but omitting the annotation loses a useful check.
- `@Deprecated` marks an API as no longer recommended for use, so the compiler and tools issue warnings/information. It does not by itself forbid calling the API.
- `@SuppressWarnings` adjusts compiler warnings within the supported scope; it should only be used after understanding why the warning arises.

**In libraries and frameworks (requiring the corresponding library and environment):**

- `@Test`: JUnit discovers and runs test methods through the test engine.
- `@Entity`: The JPA provider reads information mapping a class to a managed entity.
- `@RestController` / `@GetMapping`: Spring Web recognizes controllers and HTTP routes when the application has the appropriate configuration, components, and processing mechanisms.
- `@Transactional`: Spring can apply transaction boundaries through its configured management and interception mechanisms.

These library examples **are not built into Java SE**. Having the source code compile or having the annotation appear at runtime is not enough for the system to perform the desired behavior; there must be a component that actually consumes the metadata.

## 7. How Does Metadata Differ from Comments, Configuration, and Runtime State?

| Form | Primary Purpose | Who Uses It? |
| --- | --- | --- |
| Comment `// ...` | Explanation for human readers, ignored during compilation | Developers |
| Javadoc `/** ... */` | Generate structured API documentation | Javadoc tool, IDEs, readers |
| Annotation `@...` | Attach typed metadata with validity rules | Compiler, processors, frameworks, Reflection |
| External configuration (e.g., properties files) | Environment or application settings | Configuration code and the corresponding framework |
| Runtime variables/objects | Data that can change while the program is running | Program logic |

For example, “this method has the role of handling HTTP GET” is declarative information well suited for a web framework annotation. Conversely, “the timeout value of the request just received is 150 ms” is runtime data and should not be forced into an annotation element because annotation values must satisfy compile-time constant requirements.

Use annotations when they help the system express a convention that is **stable and has a clear processor**. If a parameter needs to change by environment or by user request, consider configuration or runtime data instead of creating more annotations.

## 8. Common Misconceptions

1. **“Having an annotation makes Java automatically execute the functionality.”** False. `@Override` has meaning because the compiler understands it; `@Test` requires JUnit; `@Transactional` requires the corresponding Spring mechanism. A custom annotation without processing code may simply remain idle metadata.
2. **“Every annotation can be read using Reflection.”** False. With the standard Reflection API, the annotation type must have `RUNTIME` retention; `SOURCE` and `CLASS` are not returned that way.
3. **“An annotation is just a nicer comment.”** Incomplete. Annotations are syntax- and type-checked by the compiler, restricted in placement by `@Target`, and can be processed by tools via APIs.
4. **“Annotation values change like object fields.”** False. Annotation elements are declarative metadata with restricted types and values, not per-object mutable state.
5. **“Simply marking something `@Deprecated` prevents old code from being called.”** False. Annotations help convey signals and warnings; blocking usage must be handled by a different mechanism.

## 9. Knowledge Self-Check

**Scenario 1:** You place `@Info(author = "Lan")` on `process()` but never use Reflection or a tool that understands `@Info`. Does the method run automatically? **No**; the annotation only describes metadata.

**Scenario 2:** You replace `@Retention(RUNTIME)` in the example with `@Retention(CLASS)`. What changes? The annotation is still present in the `.class` file, but `getAnnotation(Info.class)` via standard Reflection does not see it; without a `null` check, accessing `info.author()` will throw a `NullPointerException`.

**Scenario 3:** Why should you use `@Override` when writing an overriding method? Because the compiler can detect an incorrect signature or a method that does not actually override as the author intended.

Key takeaway: **annotations provide structured metadata about a program; it is the compiler, tools, or frameworks that determine what effect that metadata produces and when.**
