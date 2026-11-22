# @FunctionalInterface: Checking the Functional Interface Contract in Java

`@FunctionalInterface` is a standard annotation in `java.lang`, used to **instruct the compiler to check that an interface satisfies the functional interface contract**. A functional interface has **one functional abstract method** (single abstract method, commonly called SAM) after applying the language rules on inheritance, `Object` methods, and methods with equivalent signatures.

This contract is very useful because Java can use a **lambda expression** or a **method reference** to provide the implementation for that functional method, instead of having to create a named implementation class.

```java
@FunctionalInterface
interface Converter {
    String convert(String input);
}

// An object implementing the Converter contract.
Converter converter = text -> text.trim();
```

The snippet above illustrates the syntax and assumes it is placed inside a method/block. `@FunctionalInterface` protects the `Converter` declaration at compile time; Java accepts the lambda only because **the target type is a functional interface**, not because the annotation itself creates the lambda.

## 1. The Problem That @FunctionalInterface Solves

Suppose you design an interface to pass a string-processing behavior:

```java
interface TextProcessor {
    String process(String text);
}
```

This is a valid functional interface, even **without `@FunctionalInterface` at all**:

```java
TextProcessor processor = text -> text.toUpperCase();
```

After some time, someone adds a second abstract method:

```java
interface TextProcessor {
    String process(String text);
    boolean isValid(String text);
}
```

At this point, the interface is no longer a functional interface. Places that use a lambda as a `TextProcessor` object will not compile. If from the start you write:

```java
@FunctionalInterface
interface TextProcessor {
    String process(String text);
}
```

then **right at the interface declaration**, `javac` checks the contract. When someone adds an independent abstract method like `isValid`, the compiler reports an error at the annotated interface. The error appears early, close to the source of the change, and maintainers know this is a design commitment.

**Clearly distinguish two points:**

- **Functional interface** is a semantic property of an interface type under Java's rules. An interface can still be a functional interface even without the annotation.
- **`@FunctionalInterface`** is a way to declare intent and instruct the compiler to report an error if the interface does not satisfy that rule. It **does not make an interface functional**, does not generate an implementation, and does not change how lambdas execute.

## 2. What Exactly Counts as an Abstract Method?

You cannot simply count the lines ending with a `;`. Java examines all methods that the interface declares or inherits, distinguishing abstract methods that contribute to the functional contract from other methods.

### 2.1. Basic Case: One Abstract Method

```java
@FunctionalInterface
interface Action {
    void execute();
}
```

Valid. The `execute()` method in an interface is `public abstract` by default when declared as above. For example:

```java
Action action = () -> System.out.println("executed");
action.execute();
```

At runtime, the line `executed` is printed because the code calls `action.execute()`. The annotation itself does not invoke the method.

### 2.2. Default, Static, and Private Methods Do Not Increase the SAM Count

An interface can contain multiple methods, as long as the functional contract remains a single valid abstract method:

- **`default`** with an implementation body: allows providing shared behavior for all implementations.
- **`static`** belonging to the interface: called via the interface name.
- **`private`** with an implementation body inside the interface (Java 9+): helps share internal logic among methods with bodies.

The methods above do not become SAMs. The full example in Section 3 has all three kinds.

**Keep in mind:** adding a default method can create conflicts with related types in a specific inheritance hierarchy; “does not increase the SAM count” does not mean every default method change is compatibility-safe.

### 2.3. Declarations Matching Public Methods of Object Are Not Counted as Extra

Example:

```java
@FunctionalInterface
interface NamedTask extends Runnable {
    boolean equals(Object other);
}
```

`Runnable` provides `void run()`. Although `NamedTask` declares `boolean equals(Object)` (a method matching `public Object.equals(Object)`), `equals` is not counted as an additional functional method under Java's rules. The functional contract remains `run()`.

Similarly, redeclaring a matching signature of `toString()` or `hashCode()` from `Object` does not by itself create an extra SAM. **Do not apply this exception blindly to every method sharing a name with `Object`**: you must check the exact signature and overriding rules for public methods of `Object`.

### 2.4. Inheriting Multiple Abstract Declarations Does Not Necessarily Mean Multiple SAMs

Inherited methods can describe **the same contract with compatible signatures**. Example:

```java
interface First {
    Number value();
}

interface Second {
    Integer value();
}

@FunctionalInterface
interface Combined extends First, Second {
}
```

`Combined` is still valid: both `value()` declarations have the same parameter list, and `Integer` is a return type that is a subtype of `Number`, so Java can identify one suitable functional method.

Conversely, if two abstract methods have **independent names/parameters**, they form two different contracts and a single lambda cannot be used to implement both.

The general rules when generics, overloading, inheritance, and complex return types are involved concern **override-equivalent signatures**, the ability of one method to override the remaining declarations, and compatible return types. Do not just compare method name strings visually; let the compiler validate the specific definition.

## 3. Working Example: SAM with Default, Static, Private, and Lambda

Create a file named **`FunctionalInterfaceDemo.java`**:

```java
import java.util.Locale;

@FunctionalInterface
interface Labeler {
    String label(String input); // The single functional method

    default String decorate(String input) {
        return surround(label(input));
    }

    private String surround(String value) {
        return "[" + value + "]";
    }

    static Labeler upperCase() {
        return value -> value.toUpperCase(Locale.ROOT);
    }
}

public class FunctionalInterfaceDemo {
    public static void main(String[] args) {
        Labeler upper = text -> text.trim().toUpperCase(Locale.ROOT);
        System.out.println(upper.label("  java  "));
        System.out.println(upper.decorate("  java  "));

        Labeler trim = String::trim;
        System.out.println(trim.decorate(" api "));

        System.out.println(Labeler.upperCase().label("lambda"));
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac --release 17 FunctionalInterfaceDemo.java
java FunctionalInterfaceDemo
```

Stdout:

```text
JAVA
[JAVA]
[api]
LAMBDA
```

Part-by-part explanation:

1. `Labeler` has only one abstract method: `String label(String input)`.
2. `upper` is a lambda compatible with the signature `String -> String`. The lambda body trims whitespace and then converts it to uppercase.
3. `decorate` is a default method that calls the functional method `label` and wraps the result in square brackets. It works for every implementation of `Labeler`.
4. `surround` is a private helper with a body, and it adds no implementation requirement for the lambda.
5. `upperCase` is a static factory returning a `Labeler` object created from a lambda.
6. `String::trim` is a method reference to an instance method on `String`: Java binds the incoming `String` parameter as the object on which `trim()` is called and uses the result as the return value.

None of the code here reads the annotation via Reflection. Checking the contract is the compiler's job; lambdas and method references are checked for compatibility with the functional descriptor according to Java's type rules.

If you need to separate .class output from the source:

```bash
javac --release 17 -d out FunctionalInterfaceDemo.java
java -cp out FunctionalInterfaceDemo
```

The `out` directory must exist or be created by the compiler in a way appropriate for the environment. The stdout output remains unchanged.

## 4. Declarations That Cause the Compiler to Reject @FunctionalInterface

Each example in this section is an **independent error case**, not combined into the working example file from Section 3.

### 4.1. Two Independent Abstract Methods

```java
@FunctionalInterface
interface WrongService {
    void start();
    void stop();
}
```

Error: `start()` and `stop()` create two separate abstract methods. There is no single method descriptor for a lambda to implement.

To have a functional interface, you need to decide which behavior is core; the other behavior can be turned into a default method if there is a sensible implementation, or separated into another interface. **Do not turn a method into a dummy default method just to pass the check**, because that easily creates incorrect business behavior.

### 4.2. No Abstract Methods

```java
@FunctionalInterface
interface EmptyTask {
    default void execute() {
        System.out.println("default");
    }
}
```

Error: there is no abstract method for a lambda to provide an implementation for. An interface with only default/static/private methods is not a functional interface.

### 4.3. Applying the Annotation to a Class

```java
@FunctionalInterface
abstract class TaskBase {
    abstract void execute();
}
```

Error: `@FunctionalInterface` applies to an **interface**, including interfaces that inherit from others, not to a class or abstract class. An abstract class with exactly one abstract method still does not become a functional interface.

### 4.4. Adding an Abstract Method to an Interface Used by Lambdas

**Before the change:**

```java
@FunctionalInterface
interface Rule {
    boolean test(String value);
}
```

**After the change:**

```java
@FunctionalInterface
interface Rule {
    boolean test(String value);
    String reason(String value);
}
```

An error occurs at the `Rule` declaration because the `reason` method makes the contract no longer a SAM. Call sites using lambdas may also fail if the annotation is removed; removing `@FunctionalInterface` only hides the warning that protects the contract without solving the cause.

### 4.5. Inheriting Two Genuinely Different Contracts

```java
interface Load {
    void load();
}

interface Save {
    void save();
}

@FunctionalInterface
interface LoadAndSave extends Load, Save {
}
```

This fails because `load()` and `save()` are different. Extending multiple interfaces **is not forbidden in itself**, as `Combined` in Section 2.4 shows; what decides validity is whether the set of abstract methods can be consolidated into a single functional contract.

## 5. Second Experiment: Inheritance, Object, and Lambda Remain Valid

Create the file **`SamInheritanceDemo.java`**:

```java
interface First {
    Number value();
}

interface Second {
    Integer value();
}

@FunctionalInterface
interface Combined extends First, Second {
}

@FunctionalInterface
interface NamedTask extends Runnable {
    boolean equals(Object other);
}

public class SamInheritanceDemo {
    public static void main(String[] args) {
        Combined c = () -> 42;
        NamedTask task = () -> System.out.println("done");

        System.out.println(c.value());
        task.run();
    }
}
```

Run:

```bash
javac --release 17 SamInheritanceDemo.java
java SamInheritanceDemo
```

Exact stdout:

```text
42
done
```

Why does this work?

- `Combined` inherits two compatible `value()` declarations: the method provided by the lambda returns `Integer` for the expression `42`, satisfying both the `Integer` and `Number` requirements.
- `NamedTask` inherits `Runnable.run()`. The `equals(Object)` declaration corresponds to a public instance method of `Object`, so it does not add another functional method.
- The lambda `() -> System.out.println("done")` provides the implementation for `run()`; the behavior only happens when the code calls `task.run()`.

None of the examples require any libraries outside the JDK.

## 6. The Exact Role of the Annotation in the Compiler

`@FunctionalInterface` is a standard annotation recognized by the Java compiler. Annotation declarations of this kind must be used in the proper place and satisfy the functional interface rules. If they do not, the compiler emits a compilation error.

Several properties to distinguish:

| Aspect | Meaning |
| --- | --- |
| `@Target(ElementType.TYPE)` | The annotation is declared to be placed on types, but the special rule of `@FunctionalInterface` also requires that type to be a valid interface |
| `@Retention(RetentionPolicy.RUNTIME)` | Metadata of this annotation is retained so it can be queried at runtime; **this does not mean runtime is where the contract is validated** |
| `@Documented` | The annotation can appear in API documentation generated by tools such as Javadoc |
| Compiler enforcement | `javac` checks the functional interface contract at compile time |
| Lambda target typing | The compiler determines whether the target type is a functional interface and whether the lambda/method reference is compatible with the descriptor |

Note: **applying** `@FunctionalInterface` is not mandatory when using lambdas. For example, the standard interface `Runnable` is a functional interface and is treated by Java as a valid target type because of its contract; the fact that an interface lacks the annotation **is not enough to conclude** that a lambda cannot be used.

Similarly, `@FunctionalInterface` is not equivalent to `@Override`. Both help the compiler verify design intent, but `@Override` checks whether a method validly overrides/implements a method from a supertype, whereas `@FunctionalInterface` checks the abstract contract shape of **the entire interface**.

## 7. Lambdas Need a Target Type: The Annotation Does Not Define the Algorithm Itself

Consider:

```java
@FunctionalInterface
interface Check<T> {
    boolean test(T input);
}
```

Since there is only one method `boolean test(T)`, you can use:

```java
Check<String> nonBlank = value -> !value.isBlank();
boolean result = nonBlank.test("Java"); // true
```

The compiler relies on **the target type `Check<String>`** to infer that the parameter `value` has type `String`, verifies that the lambda expression returns `boolean`, and produces the corresponding execution mechanism when the program runs.

The line `nonBlank.test("Java")` is where the behavior is actually invoked. The annotation does not perform the string check on its own.

A functional interface using generics can still be valid; the number of type parameters (`<T>`) does not equate to the number of abstract methods. Validity depends on the set of methods that must be implemented.

A lambda error does not necessarily mean the interface is not a functional interface. For example, `Check<String> invalid = value -> value.length();` is invalid because the lambda returns `int` while the functional method must return `boolean`. `@FunctionalInterface` on `Check` is still valid; **it is the lambda implementation itself that mismatches the type**.

Method references (`String::trim`, `System.out::println` when matching the target type) follow the same principle: checking that the signature matches the functional descriptor, without needing an annotation processed at runtime.

## 8. When Maintaining a Library: Which Changes Preserve the Contract, and Which Break It?

Suppose you publish:

```java
@FunctionalInterface
public interface MessageHandler {
    void handle(String message);
}
```

Library users can write:

```java
MessageHandler handler = message -> System.out.println(message);
```

Evaluating some changes:

| Change to `MessageHandler` | Preserves SAM? | Notes |
| --- | --- | --- |
| Add a `default` method with a body | Usually yes | The number of abstract methods does not increase; inheritance conflicts still need to be checked |
| Add a `static` utility method | Yes | Not an instance functional method |
| Add a `private` helper with a body | Yes | Used only internally within the interface |
| Add an abstract method with a different signature and contract | No | The annotation catches the error early; existing lambdas are no longer compatible |
| Add a declaration matching a public method of `Object` | Possibly yes | Only if it satisfies the exact valid signature rules |
| Change the parameters/return type of the SAM | May still be a SAM | However, lambdas, method references, and code currently using the API may need to be updated |

When designing an API for a callback, event handler, or single-behavior strategy, apply `@FunctionalInterface` to affirm that **the ability to pass an implementation using a lambda is part of the intended contract**. Do not use it if the interface intentionally requires multiple independent abstract behaviors.

A default method can extend behavior without requiring every existing lambda to implement an extra method. However, source compatibility, binary compatibility, and behavior are separate concerns; the table above **only checks the functional interface contract**.

## 9. Common Misconceptions

**“Without `@FunctionalInterface`, lambdas cannot be used.”** False. The compiler looks at the properties of the target type. The annotation clarifies intent and enables checking directly at the interface declaration.

**“A functional interface may declare only one method.”** False. It can have default, static, private methods, and methods corresponding to public methods of `Object`; inherited methods and signature equivalence must also be considered.

**“One abstract method in the interface file itself is enough.”** Not necessarily. The interface may inherit additional abstract methods from parent interfaces. You must consider the entire effective contract.

**“Extending two interfaces definitely means lambdas cannot be used.”** False. If the abstract methods are compatible and can be unified into a single function, for example, `Combined` is still a functional interface.

**“Applying the annotation automatically generates code/lambda implementations.”** False. The compiler verifies the shape of the interface. The lambda or implementing class must still be provided by the application code.

**“Because the annotation is retained at runtime, the JVM decides the contract.”** False. The Java compiler checks the functional interface rules at compile time. The fact that metadata remains present at runtime does not change this verification mechanism.

**“If adding an abstract method causes an error, just remove the annotation.”** False. When an interface has multiple independent abstract methods, a lambda still has no single functional method to implement. The interface design needs to be revisited.

## 10. Self-Check Exercises

**Exercise 1.** Predict which declarations are considered functional interfaces:

```java
interface A {
    void run();
}

@FunctionalInterface
interface B {
    void run();
    default void reset() {}
}

@FunctionalInterface
interface C {
    void run();
    int count();
}

@FunctionalInterface
interface D extends Runnable {
    String toString();
}
```

**Exercise 2.** Given `@FunctionalInterface interface Reader { String read(); }`, if you want to add a `readOrDefault()` capability while keeping lambda compatibility, how would you declare it?

**Exercise 3.** Why is the line `Labeler trim = String::trim;` in Example 3 valid, whereas `Labeler invalid = String::length;` is invalid?

**Exercise 4.** Explain the difference between an error in the definition of an interface with two abstract methods and an error in a lambda whose return type does not match the SAM.

**Exercise 5.** An interface does not have `@FunctionalInterface` attached, yet it has one SAM. Can it be used with lambdas? What is the risk if someone else adds a second abstract method during maintenance?

### Solution Hints

1. `A`, `B`, and `D` are functional interfaces; `C` is invalid with the annotation because it has two independent abstract methods. `D` only has `Runnable.run()` as its functional method because `toString()` matches a public method of `Object`.
2. Use a **default method with a body**, such as `default String readOrDefault() { ... }` with logic based on `read()`; evaluate appropriate default behavior before introducing it into the API.
3. `String::trim` is compatible with the `String -> String` type of `Labeler.label`, whereas `String::length` returns `int`, which does not match the required `String`.
4. A definition error means no valid functional contract exists; a lambda error can occur even when the interface is valid, because the lambda body does not satisfy the signature/return type.
5. Yes. The annotation is optional; without it, the project loses a signal of intent and a direct check error at the declaration if the contract is broken.

## 11. Checklist Before Using @FunctionalInterface

1. Does the interface truly describe **a single abstract behavior** after accounting for inherited methods as well?
2. Are any additional methods default/static/private, or covered by the exception matching a public method of `Object`?
3. Do the generic types, parameters, and return type of the SAM fit the intended lambdas or method references?
4. Could a new change accidentally add a second abstract method and break the callback API?
5. Has the compiler checked everything successfully when compiling the entire interface and the relevant call sites?

`@FunctionalInterface` is a **compiler-verified design commitment**: the interface declares exactly one abstract behavior that can be supplied with a lambda or method reference. Understanding the rules for counting abstract methods and the role of the compiler will help you design clear callbacks/strategies while catching breaking changes for API users early.
