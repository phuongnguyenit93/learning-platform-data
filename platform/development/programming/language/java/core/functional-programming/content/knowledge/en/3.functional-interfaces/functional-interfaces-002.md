# @FunctionalInterface: Optional Annotation to Express and Verify Intent

In Java, a **functional interface** is an interface that has exactly **one abstract method that must be implemented** according to the rules of the Java language. It can serve as a **target type** for lambda expressions and method references. The **`@FunctionalInterface` annotation is optional**: it explicitly expresses the design intent to use the interface as a functional interface and asks the compiler to verify the validity of that intent.

The most important point: **an interface becomes a functional interface because of its method structure, not because the annotation is attached**. Conversely, adding `@FunctionalInterface` to an interface with an invalid structure causes a compile-time error; the annotation does not turn it into a functional interface.

This lesson focuses on the meaning of the annotation, how the compiler checks it, exceptions in counting abstract methods, and usage choices in Java 17+ API design.

## 1. What Are Functional Interfaces and SAM?

SAM stands for **Single Abstract Method**. Example:

```java
@FunctionalInterface
interface TextRule {
    boolean test(String text);
}
```

The `test(String)` method has no body; a lambda can provide the implementation:

```java
TextRule nonBlank = text -> text != null && !text.isBlank();
boolean valid = nonBlank.test("Java"); // true
```

These two snippets are illustrative examples that can be placed in the same Java program; the second snippet must be inside a method or initializer block. The compiler checks the functional signature, parameter types, return type, and exception constraints when converting the lambda into an object of `TextRule`.

**A functional interface is a type contract.** A lambda cannot exist as a value of an arbitrary standalone type: it requires a functional interface as its target type through assignment, method argument, casting, or a valid inferred context.

## 2. The Exact Role of @FunctionalInterface

The annotation belongs to `java.lang`, so no `import` declaration is needed:

```java
@FunctionalInterface
interface Formatter {
    String format(String value);
}
```

When encountering the annotation, the compiler verifies that the `Formatter` declaration actually satisfies the functional interface rules. If someone accidentally adds an incompatible abstract method, the source code will fail to compile, helping catch contract-breaking changes early.

Without the annotation, an interface can still be a functional interface:

```java
interface PlainFormatter {
    String format(String value);
}

// Inside a method:
PlainFormatter trim = String::trim;
String result = trim.format("  Hello  "); // "Hello"
```

Therefore:

- **With annotation and valid**: the compiler accepts it; lambdas/method references can use that interface as a target type.
- **Without annotation but valid**: lambdas/method references can **still** use it.
- **With annotation but invalid**: the compiler reports an error **right at the interface declaration**.
- **Without annotation and invalid**: the interface may still be a normal interface; however, it cannot be used as a lambda target type.

The annotation does not generate additional methods, does not provide an implementation automatically, does not change method invocation rules, does not make lambdas run faster, and does not force using a lambda instead of an anonymous class. Nor does it certify that the function is *pure*, side-effect-free, thread-safe, or always executed exactly once.

## 3. Abstract Method Counting Rules: What Counts?

For typical examples, consider the set of abstract methods of the interface, including **inherited** methods, and apply Java's rules to determine a single functional contract. Methods with equivalent signatures and compatible return types can together represent one functional method; merely counting lines containing the `abstract` keyword will lead to the wrong conclusion.

### 3.1. A Single Abstract Method: Valid

```java
@FunctionalInterface
interface StringTransform {
    String apply(String source);
}
```

`apply` is the functional method. Methods in a regular interface are implicitly `public abstract` if they have no body and do not belong to exceptions like `default`, `static`, or `private`. Therefore, you do not need to write `public abstract` explicitly.

### 3.2. Default Methods Do Not Increase the Abstract Method Count

```java
@FunctionalInterface
interface Validator {
    boolean isValid(String input);

    default boolean isInvalid(String input) {
        return !isValid(input);
    }
}
```

`isInvalid` already has a body and can call the functional method `isValid`. The interface remains valid; the lambda only needs to implement `isValid`.

### 3.3. Static and Private Methods Are Not Additional SAMs

```java
@FunctionalInterface
interface Labeler {
    String label(String text);

    static Labeler withPrefix(String prefix) {
        String safePrefix = sanitize(prefix);
        return value -> safePrefix + value;
    }

    private static String sanitize(String value) {
        return value == null ? "" : value;
    }
}
```

`withPrefix` is a utility method belonging to the interface, has a body, and is called as `Labeler.withPrefix("Hi ")`. `sanitize` is an internal helper of the interface; private methods in interfaces have been supported since Java 9. Neither adds an abstract obligation for the lambda.

### 3.4. Methods Matching Public Methods of Object Are Not Counted

```java
@FunctionalInterface
interface Reporter {
    void report(String message);

    boolean equals(Object other);
    String toString();
}
```

Even though `equals` and `toString` are declared without bodies, they match **public** methods of `java.lang.Object`, so they are not counted as additional abstract methods when determining a functional interface. `report` remains the single functional method.

**Do not overgeneralize this rule to every method of `Object`.** For example, `clone()` is `protected` in `Object`, so it does not belong to the exception for matching public methods.

### 3.5. Inherited Abstract Methods Are Also Counted

```java
interface Work {
    void execute();
}

@FunctionalInterface
interface LoggedWork extends Work {
    default void printLabel() {
        System.out.println("work");
    }
}
```

`LoggedWork` does not declare `execute` itself, but inherits it from `Work`. Therefore, the functional method is still `execute()`, and you can write `LoggedWork action = () -> System.out.println("run");`.

If an interface inherits multiple abstract declarations with equivalent signatures, the compiler applies override-equivalence and return-type substitutability rules to determine whether there is one valid functional method. In tricky cases with generics/covariant returns, let the compiler confirm rather than counting manually.

## 4. Complete Java 17 Example: With and Without the Annotation

Save as **`FunctionalInterfaceAnnotationDemo.java`**:

```java
@FunctionalInterface
interface TextFormatter {
    String format(String text);

    // Matches a public Object method: not counted as a second SAM.
    boolean equals(Object other);

    // Has a body: not counted as an abstract method.
    default String twice(String text) {
        return format(text) + " | " + format(text);
    }

    static TextFormatter withPrefix(String prefix) {
        String safe = safePrefix(prefix);
        return text -> safe + text;
    }

    private static String safePrefix(String prefix) {
        return prefix == null ? "" : prefix;
    }
}

// Not annotated, yet still a functional interface.
interface PlainFormatter {
    String format(String text);
}

public class FunctionalInterfaceAnnotationDemo {
    public static void main(String[] args) {
        // Lambda: implements TextFormatter.format(String).
        TextFormatter tagged = text -> "[Java] " + text;
        System.out.println(tagged.format("Lambda"));
        System.out.println(tagged.twice("SAM"));

        // Static factory creates a lambda capturing the prefix value.
        TextFormatter prefixed = TextFormatter.withPrefix("Hi ");
        System.out.println(prefixed.format("Lan"));

        // Method reference works even though PlainFormatter has no annotation.
        PlainFormatter plain = String::trim;
        System.out.println(plain.format("  Hello  "));

        // Built-in functional interface in the JDK.
        Runnable task = () -> System.out.println("Runnable running");
        task.run();
    }
}
```

Compile and run with JDK 17 or later in the directory containing the file:

```bash
javac -encoding UTF-8 FunctionalInterfaceAnnotationDemo.java
java FunctionalInterfaceAnnotationDemo
```

**Exact stdout:**

```text
[Java] Lambda
[Java] SAM | [Java] SAM
Hi Lan
Hello
Runnable running
```

Explanation:

1. `TextFormatter` has `format(String)` as its functional method. Declaring `equals(Object)` does not make it lose its functional nature.
2. `tagged` is a lambda implementing `format`; calling `twice` uses the existing default method and invokes `format` twice.
3. `withPrefix` is a static factory returning a `TextFormatter`. The private static method merely helps sanitize the factory's input.
4. `PlainFormatter` is not annotated, yet `String::trim` still matches the `String -> String` signature.
5. `Runnable` illustrates a standard JDK functional interface. The lambda provides the implementation for `run()`.

The example also shows that `@FunctionalInterface` **is not attached to a lambda**. It is attached to the **interface declaration**, where the contract accepting a lambda is defined.

## 5. When the Compiler Must Report an Error

### 5.1. Adding an Incompatible Second Abstract Method

**The following snippet intentionally does not compile:**

```java
@FunctionalInterface
interface BrokenRule {
    boolean test(String value);
    String explain(String value);
}
```

Here `test` and `explain` are two distinct abstract methods that must be implemented. The annotation forces the compiler to report an error because `BrokenRule` is not a functional interface. Depending on the API goal, you can:
- Turn `explain` into a default method with an appropriate implementation that does not break semantics.
- Move `explain` to another interface.
- Keep the interface with multiple abstract methods while removing the annotation, accepting that the interface is **not** a target type for lambdas.

You should not fix it merely by deleting the annotation if the original intent of the API was to accept lambdas; in that case, the design contract has still been broken.

### 5.2. Having No Abstract Method at All

**The following snippet intentionally does not compile:**

```java
@FunctionalInterface
interface MarkerOnly {
}
```

An empty marker interface has no functional method for a lambda to implement. If a marker type is needed, remove `@FunctionalInterface`. If you want to accept a lambda, you must define a genuinely meaningful functional method.

### 5.3. An Interface with Multiple Abstract Methods Without the Annotation

```java
interface TwoOperations {
    void start();
    void stop();
}
```

The `TwoOperations` declaration itself is valid without the annotation. However, **the following assignment intentionally does not compile**:

```java
TwoOperations operations = () -> System.out.println("start");
```

A lambda cannot implement two independent abstract methods by itself. Removing the annotation only removes the check at the declaration site; it does not make that type support lambdas.

### 5.4. The Annotation Must Be Used on an Appropriate Interface

`@FunctionalInterface` is not used to mark a normal class or method. Nor can the annotation fix signature errors, generic errors, or inheritance conflicts that already make the interface declaration invalid.

## 6. Impact on API Design and Maintenance

Suppose an initial public API is:

```java
@FunctionalInterface
public interface EventHandler {
    void handle(String event);
}
```

Clients can use `event -> System.out.println(event)`. If a later version adds `void onError(Throwable error);` as an abstract method, the interface loses its functional nature: client lambdas no longer have a valid target type, and the compiler catches the change right in the module defining the interface thanks to the annotation.

If adding behavior is necessary, consider a `default` method with sound default semantics, or design a suitable new interface. **Do not add a default method just to get past the compiler** if no reasonable default implementation exists; doing so easily creates a misleading API contract.

Adding `@FunctionalInterface` helps readers immediately understand the intended use of the interface. At the same time, it acts as a long-term compile-time check when multiple people maintain the code. For interfaces designed to pass callbacks, predicates, mappers, factories, or actions, the annotation is usually a good choice.

There are interfaces that happen to have one abstract method but were designed for another purpose or are expected to evolve in ways that break functional compatibility. Java allows omitting the annotation; the decision depends on whether you want to commit to preserving the SAM contract across future changes.

## 7. Relation to Standard Functional Interfaces

Before creating a custom interface, check the built-in types in the JDK:

| Interface | Functional method | Typical purpose |
| --- | --- | --- |
| `Runnable` | `void run()` | Run an action taking no arguments and returning no result. |
| `Supplier<T>` | `T get()` | Supply or defer creating a value. |
| `Consumer<T>` | `void accept(T value)` | Accept a value to perform an action. |
| `Predicate<T>` | `boolean test(T value)` | Test a condition. |
| `Function<T, R>` | `R apply(T value)` | Transform an input into a result. |
| `UnaryOperator<T>` | `T apply(T value)` | Transform a value while keeping the same type. |
| `BiFunction<T, U, R>` | `R apply(T left, U right)` | Transform two inputs. |
| `Comparator<T>` | `int compare(T a, T b)` | Compare two values for ordering. |
| `Callable<V>` | `V call() throws Exception` | Compute a result that may throw a checked exception. |

The generic interfaces in `java.util.function` are often sufficient for simple cases. Create a custom interface when domain naming, type constraints, exceptions, default methods, or code readability make a dedicated contract clearly meaningful.

Example:

```java
java.util.function.Predicate<String> valid =
        text -> text != null && !text.isBlank();

boolean ok = valid.test("Java"); // true
```

This illustrative snippet can be placed inside a method. `Predicate<String>` is the target type; `@FunctionalInterface` is declared on the JDK's `Predicate` interface rather than appearing at the `valid` variable site.

## 8. Common Misconceptions

- **“Without the annotation, you cannot use lambdas.”** False. An interface with a valid SAM structure still serves as a target type.
- **“Adding the annotation automatically turns an interface into a SAM.”** False. The compiler rejects it if the contract does not have exactly one valid functional method.
- **“Just count the number of method declarations in the file.”** False. You must consider inherited methods, equivalent declarations, public methods of `Object`, `default`, `static`, and `private`.
- **“An interface with a second default method is not functional.”** False. A default method already has an implementation and does not create a second implementation obligation.
- **“An interface that declares no methods itself but inherits a SAM is not functional.”** False. Inherited abstract methods are still counted.
- **“The annotation guarantees the lambda has no side effects.”** False. The annotation only checks the interface's structural contract.
- **“You can only use a lambda, not an anonymous class.”** False. A functional interface can still be implemented by a regular class or an anonymous class.
- **“Deleting the annotation fixes the error caused by adding a second SAM.”** False for an API committed to supporting lambdas: the structure is no longer compatible even when the annotation is gone.

## 9. Self-Check

**Question 1.** Is the interface below valid with the annotation?

```java
@FunctionalInterface
interface Task {
    void run();
    default void log() { System.out.println("log"); }
    static Task noOp() { return () -> {}; }
}
```

**Yes.** Only `run()` is an abstract method requiring implementation.

**Question 2.** If `@FunctionalInterface` is removed from `Task`, is the assignment `Task t = () -> {};` still valid?

**Yes.** The interface still has a single functional method.

**Question 3.** Is `@FunctionalInterface interface Empty {}` valid?

**No.** There is no abstract method to implement.

**Question 4.** If an abstract `void cancel();` is added to `Task`, what happens?

**Invalid with the annotation;** the compiler detects two distinct abstract methods. Removing the annotation still does not allow the lambda `() -> {}` to implement both `run` and `cancel`.

**Question 5.** Why should the annotation be added to a custom callback interface defined by a development team?

Because the annotation **states the intent clearly** and **asks the compiler to preserve the functional interface constraint across code edits**, making contract-breaking changes easy to detect at compile time.

Takeaway: **The SAM rules determine whether an interface can be used as a lambda target type; `@FunctionalInterface` helps the compiler verify and readers recognize that intent.**