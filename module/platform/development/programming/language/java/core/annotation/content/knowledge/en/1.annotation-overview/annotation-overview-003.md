# Relationship Between Annotation Declaration Site, Usage Site, and Consumer/Processor in Java

## 1. Three Different Roles in the Same Mechanism

When you see `@Something` in Java, you need to distinguish **three sites/three roles**:

1. **Annotation type declaration site**: defines *what the annotation is named, which data elements it accepts, where it can be attached, and until which phase it is retained*.
2. **Annotation usage site**: attaches the annotation to a specific Java element and supplies metadata values at that location.
3. **Annotation consumer/processor**: reads the metadata and then decides to **check, generate code, configure, or execute a behavior**.

The three roles may appear in different files, modules, or libraries. An annotation is a **metadata representation contract** connecting the declaration site and the usage site to the consumer/processor. The `@...` notation itself does not execute business logic, create objects on its own, write logs on its own, or open transactions on its own.

```text
Defining author/library:
  @interface BusinessAction { ... }
               |
               | provides the annotation type and rules
               v
Business developer using it:
  @BusinessAction("BOOK_TICKET")
  void book() { ... }
               |
               | metadata attached to a specific method
               v
Consumer/processor:
  compiler / annotation processor / framework / Reflection
               |
               v
  checks, generates code, registers functionality, or runs logic
```

The final arrow **only happens if there is a party that actually recognizes and processes the annotation**. The definition site and the usage site can be completely valid syntactically, yet without an appropriate consumer/processor, the expected behavior still will not occur.

## 2. Declaration Site: Defining the *Type* of Metadata

Define a custom annotation using the `@interface` keyword:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface BusinessAction {
    String value();
    int level() default 1;
}
```

This is **an annotation type declaration**; it has not yet attached metadata to any business method and has not yet written any processing mechanism.

- `BusinessAction` is the name of the annotation type.
- `value()` is a required element of type `String`; the usage site must provide a value.
- `level()` is an element of type `int`, with a default of `1`.
- `@Target(ElementType.METHOD)` restricts the usage location to method declarations.
- `@Retention(RetentionPolicy.RUNTIME)` requests retaining the annotation so it can be read via Reflection at runtime.

`@Target` and `@Retention` are **meta-annotations**: they describe another **annotation type**. They are not business data of `book()`. When `@Retention` is not declared, the default policy for a custom annotation is `CLASS`: the metadata is stored in `.class` but is not present through the standard Reflection API at runtime.

Annotation elements have restricted types: primitive types, `String`, `Class`, enums, other annotations, or one-dimensional arrays of those types. An element is not a mutable variable of an object; values written at the usage site must satisfy compile-time constant rules. You cannot pass a service object, a runtime request, or a `new HashMap<>()` into an annotation element.

**Responsibility boundary:** the designer of `BusinessAction` creates a metadata interface and a valid scope of use. An `@interface` declaration **does not contain a method body** to process `level` or `value` on its own. Validation or audit-logging logic must be implemented in the metadata consumer.

## 3. Usage Site: Attaching Metadata *Values* to a Specific Location

Once the annotation type exists, business code can attach it to a method:

```java
class BookingService {
    @BusinessAction(value = "BOOK_TICKET", level = 2)
    public void book() {
        System.out.println("Dịch vụ: đã giữ chỗ");
    }
}
```

This code snippet declares that **the `book()` method** carries metadata consisting of `value="BOOK_TICKET"` and `level=2`.

- The usage site references a declared annotation type, adhering to its name, element types, and `@Target`.
- The metadata belongs to the annotated element; it does not turn itself into a statement inside the method body.
- The same `@BusinessAction` can be attached to multiple methods with different values; each attachment site has its own metadata.
- If you write `@BusinessAction("BOOK_TICKET")`, Java interprets that value as belonging to the element named `value`; `level` receives its default value `1`.
- If you write `@BusinessAction` without passing `value`, the compiler reports an error because `value()` has no default. If you attach it to a class while `@Target` only allows `METHOD`, the compiler also reports an error.

A common point of confusion: calling `book()` directly with `new BookingService().book()` still executes **the Java method body as normal**. Without code that reads the annotation, no audit line or special behavior is generated by `@BusinessAction` on its own.

## 4. Consumer/Processor: At Which Step Does Metadata Become Behavior?

Saying “an annotation takes effect” refers to **a party with authority processing it**. Common consumers/processors are not the same:

| Consumer/Processor | When is it read? | How is it read? | Example outcome |
| --- | --- | --- | --- |
| Java compiler, for annotations natively supported by the compiler | During compilation | Language/compiler rules | `@Override` verifies that a method actually overrides; `@SuppressWarnings` affects the specified warnings |
| Annotation processor registered by an application/library | During `javac` compilation | Annotation Processing API, `Element`/`TypeMirror` models | Detects rule violations, reports errors, or generates source/resource files |
| Runtime framework | At startup or when handling a situation | Metadata via Reflection, bytecode-reading tools, or the framework's metadata model | JUnit discovers tests; Spring Web registers mappings; Spring Transaction applies transaction mechanisms when conditions are met |
| Custom-written Java code | At the time the reading code is invoked | `Class`, `Method`, `Field`, and `getAnnotation(...)` in Reflection | Checks permissions by custom rules, logs audit entries, or selects a handler |

**Direct compiler support** and **pluggable annotation processors** are two forms of processing during the compilation phase, but they are not synonymous. `@Override` has language semantics built into `javac` checks; a custom annotation does not automatically get similar business checks without a processor or consumer.

An annotation processor also **does not run automatically just because you declare an annotation**: the processor must be provided/registered through the build tool or compiler mechanism. A runtime framework must likewise be installed, configured, and have the appropriate activation conditions.

## 5. Java 17+ Example: Including Declaration, Usage, and Processing

Create the file **`AnnotationRelationshipDemo.java`** with the complete code below. The example is standalone and uses only the JDK; the primary processing mechanism is custom-written Reflection code, making it easy to see the exact point where metadata is turned into behavior.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

// [1] DECLARATION SITE: defines metadata and applicability rules.
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface BusinessAction {
    String value();
    int level() default 1;
}

class BookingService {
    // [2] USAGE SITE: attaches metadata to a specific method.
    @BusinessAction(value = "BOOK_TICKET", level = 2)
    public void book() {
        System.out.println("Dịch vụ: đã giữ chỗ");
    }
}

public class AnnotationRelationshipDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {
        BookingService service = new BookingService();

        System.out.println("[1] Gọi trực tiếp");
        service.book();

        System.out.println("[2] Bên xử lý annotation");

        // [3] CONSUMER/PROCESSOR: locates the target method and reads the annotation.
        Method method = BookingService.class.getDeclaredMethod("book");
        BusinessAction metadata =
                method.getAnnotation(BusinessAction.class);

        if (metadata == null) {
            System.out.println("Phương thức không có BusinessAction");
            return;
        }

        System.out.println("Metadata: "
                + metadata.value() + ", level=" + metadata.level());

        if (metadata.level() >= 2) {
            System.out.println("Ghi audit: " + metadata.value());
        }

        // The consumer itself actively invokes the method; the annotation does not invoke it on its own.
        method.invoke(service);
    }
}
```

In the directory containing the file, compile and run:

```bash
javac -encoding UTF-8 AnnotationRelationshipDemo.java
java AnnotationRelationshipDemo
```

Standard output on a Unicode-capable terminal:

```text
[1] Gọi trực tiếp
Dịch vụ: đã giữ chỗ
[2] Bên xử lý annotation
Metadata: BOOK_TICKET, level=2
Ghi audit: BOOK_TICKET
Dịch vụ: đã giữ chỗ
```

### Execution Flow Analysis

**Declaration and compilation phase:** `javac` checks that the `@BusinessAction` annotation can be attached to a method, that the `value` element has type `String`, and that `level` has type `int`. Because of `RetentionPolicy.RUNTIME`, the annotation information is written into bytecode in a way that can be retrieved at runtime.

**Direct call:** `service.book()` only prints the line `Dịch vụ: đã giữ chỗ`. Neither `Metadata` nor `Ghi audit` appears because this call site has no consumer reading the annotation.

**Call through the consumer:** the code obtains the method via `getDeclaredMethod("book")`, reads the annotation via `getAnnotation(BusinessAction.class)`, retrieves the two metadata elements, applies the `level >= 2` rule to print the audit message, and then calls the method via `method.invoke(service)`. This is logic *chosen by the consumer's author*; Java cannot infer that `level=2` means “must log an audit entry”.

The `metadata == null` check has practical significance: a method might not be annotated, or the annotation might not be retained for Reflection. You should not assume `getAnnotation(...)` always returns an object.

### Three Small Changes to Verify Yourself

1. Remove the `method.invoke(service)` call: the consumer/processor still reads the metadata and prints the audit message, but the `book()` method only runs during the direct call.
2. Remove `@BusinessAction(...)` from `book()`: the direct call line still works; the consumer prints the message indicating there is no annotation and then stops.
3. Change `RetentionPolicy.RUNTIME` to `RetentionPolicy.CLASS`: the annotation may still be present in the `.class` file, but `getAnnotation(...)` cannot find it via standard Reflection; there is no metadata/audit output from the consumer.

These changes demonstrate that **having a declaration site + usage site does not guarantee behavior**: there must be a consumer/processor and a point that actually triggers it.

## 6. How Annotations Travel from Source Code to Compiler and Runtime

The declaration site determines the presence of metadata at different stages through the retention policy:

| Retention | In source | In `.class` | Standard Reflection at runtime |
| --- | --- | --- | --- |
| `RetentionPolicy.SOURCE` | Yes | No | No |
| `RetentionPolicy.CLASS` | Yes | Yes | No |
| `RetentionPolicy.RUNTIME` | Yes | Yes | Yes |

Note: `CLASS` metadata can still be processed by **bytecode-reading tools**; the last column only refers to the standard Reflection API. A `SOURCE` annotation can still be analyzed by the compiler or an annotation processor **during compilation**. Therefore, `RUNTIME` is not “the best kind for every annotation”; it must be chosen based on **who needs to read it and when**.

```text
                JAVA SOURCE CODE
         ┌─────────────────────────────┐
         │ Declare @interface          │
         │ Attach @BusinessAction(...) │
         └──────────────┬──────────────┘
                        │
                        v
                 JAVAC / BUILD
      ┌─────────────────┴─────────────────┐
      │ Check syntax, @Target,            │
      │ element types and values          │
      │                                   │
      │ Registered annotation processor:  │
      │ checks / generates code           │
      └─────────────────┬─────────────────┘
                        │
                        v
          .class (based on retention)
                        │
                        v
              RUNNING APPLICATION
      ┌─────────────────┴─────────────────┐
      │ Runtime consumer recognizes the   │
      │ annotation and applies rules      │
      └───────────────────────────────────┘
```

Not every system includes every branch. Annotations intended solely for compile-time can fulfill their purpose before execution; annotations intended for Reflection require `RUNTIME`.

Also, do not confuse `@Target` with `@Retention`: `@Target` restricts **where the annotation can be attached**, whereas `@Retention` controls **how long it is retained**. Choosing a valid attachment target does not mean the runtime can read that annotation.

## 7. The Relationship in Real-World Applications

Suppose you are building a ticket booking system using a web framework:

- **The library/framework designer** declares the annotation type (for example, an annotation specifying an HTTP mapping) and also writes the consumer to scan, register, and route.
- **The application developer** attaches the annotation to a controller method with the path or HTTP method to handle.
- **The running framework** reads metadata at valid locations, registers the corresponding route, and later dispatches requests to the handler when a matching request arrives.

In Spring, for example, `@GetMapping("/tickets")` describes a mapping; the application needs the Spring Web component and appropriate controller configuration for the mapping to be registered and used. In JUnit, `@Test` marks a method; the test engine decides which methods are executed. With Spring `@Transactional`, the metadata is an input to the framework's transaction mechanism; merely placing the annotation in code does not prove that every call path is intercepted or runs inside an actual transaction.

All of the examples above belong to **libraries outside Java SE**; they are not required to compile the `AnnotationRelationshipDemo.java` example.

Another type of application is a **compile-time annotation processor**: a library provides an annotation `@GenerateSomething` and a registered processor. The processor can traverse annotated elements and generate additional source code. The new code must be processed by the compiler as part of the build process. Annotations **do not alter the body of existing written Java methods on their own**; any change in behavior must come from a specific tool or processing mechanism.

### Who Depends on Whom?

Syntactically, the **usage site** must know the annotation type so the compiler can validate it. The **consumer/processor** must also recognize the annotation type or corresponding metadata convention in order to process it. However, business logic does not need to call the consumer directly if the framework orchestrates that flow; this turns metadata into a way to connect declarative code with a shared mechanism.

This mechanism is useful for repetitive concerns (such as mapping, validation, testing, serialization, and transactions) when the consumer/processor already exists and the operating rules are sufficiently clear. It can make debugging difficult if learners do not know **which consumer runs, when it runs, and on which objects/methods**.

## 8. Common Conceptual Mistakes

1. **Confusing defining an annotation with implementing a feature.** Writing `@interface Audit` only creates a metadata type. Without a consumer, no logs are generated automatically.
2. **Confusing attaching an annotation with executing code.** `@BusinessAction` on `book()` does not cause `book()` to execute by itself, as shown by the direct call in the example.
3. **Not identifying who reads the annotation.** An idea such as “mark methods that need checking” is not enough; you must specify which compiler, processor, framework, or Reflection code enforces the checking rules.
4. **Using `CLASS` and expecting `getAnnotation(...)` to see it.** Standard Reflection requires annotations with `RUNTIME` retention; `CLASS` serves bytecode-reading tools or appropriate build needs.
5. **Confusing the consumer's authority with the annotation's authority.** Attaching a custom `@RequiresRole("ADMIN")` to a method does not protect the method unless an authentication and authorization mechanism actually runs on every call path that needs protection.
6. **Confusing all annotations with runtime annotations.** `@Override` is useful right inside the compiler; it does not need a Reflection consumer when the program runs.
7. **Forgetting the usage target.** An annotation with `@Target(ElementType.METHOD)` cannot be arbitrarily attached to a class or field. A processor/consumer may also scan only a specific scope, so having the right annotation type alone is not enough.

## 9. How to Analyze Any Annotation

When encountering an unfamiliar annotation in a project, trace through this sequence of questions:

1. **Where is it declared?** Identify the package/library containing `@interface` and the elements that can be passed to it.
2. **Where is it allowed to be attached?** Read `@Target` and check whether the annotation is attached to the right class/method/field/parameter or other valid target.
3. **Who supplies the data?** Check the values written at the usage site, the default values, and the differences across usage sites.
4. **Who is the consumer?** The built-in compiler, a build annotation processor, a specific framework, or custom-written Reflection code?
5. **When does the consumer run and how is it triggered?** Compile-time, bootstrap, upon receiving a request, when running tests, or when a consumer method is called?
6. **Does the consumer actually see the annotation?** Check the retention, scan scope, target object being processed, and how metadata is retrieved.
7. **Which piece of code produces the observed behavior?** Cross-check logs, handler/processor code, and execution results; do not infer it from the annotation name.

### Self-Check Exercises

**Exercise 1.** Declare `@interface Flag { String value(); }` and attach `@Flag("IMPORTANT")` to a method, without writing a processor and without any runtime consumer. What happens? — If the usage site is valid and compiles successfully, the metadata alone does not make the method perform business logic on its own.

**Exercise 2.** A library has an annotation with `@Retention(SOURCE)` and an annotation processor that runs during `javac`. Can the processor use the annotation? — Yes, compile-time processing does not require the metadata to survive until runtime.

**Exercise 3.** In the runnable example, you change `level=2` to `level=1`. Is the audit still printed, and does `book()` still run? — The audit is no longer printed because the `level >= 2` condition is false; `book()` still runs twice (once directly, once via `method.invoke(service)`), assuming no other part of the consumer is modified.

**Exercise 4.** Why can an annotation be present while Spring/JUnit does not produce the expected behavior? — The right runtime engine, configuration, activation conditions, and call paths supported by the framework are required.

The relationship to remember is: **the declaration site defines the shape and rules of the metadata; the usage site supplies metadata for a specific element; the consumer/processor reads the metadata at the appropriate phase and actively performs the behavior**.
