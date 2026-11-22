# Enums Implementing Interfaces in Java 17+

An **enum in Java is a special kind of class** that has a fixed set of constants and can **`implements` one or more interfaces**. As a result, each enum constant is not just a symbolic value, but can also provide **polymorphic behavior** under the same contract.

Basic syntax:

~~~java
interface Describable {
    String description();
}

enum Status implements Describable {
    NEW, ACTIVE, DONE;

    @Override
    public String description() {
        return "Status: " + name();
    }
}
~~~

`Status` implements `Describable`: all three constants use the shared implementation of `description()`. When different behavior is needed for each constant, you can use a **constant-specific class body**:

~~~java
interface BinaryOperation {
    int apply(int left, int right);
}

enum Operation implements BinaryOperation {
    ADD {
        @Override
        public int apply(int left, int right) {
            return left + right;
        }
    },
    MULTIPLY {
        @Override
        public int apply(int left, int right) {
            return left * right;
        }
    }
}
~~~

`Operation.ADD` and `Operation.MULTIPLY` are both of type `BinaryOperation`, but `apply` is dispatched according to the specific constant.

This lesson belongs to **Java Core — Class & Object / Enum**, applying to **Java 17+**. Every standalone runnable example explicitly states the filename, `javac`/`java` commands, and stdout; incomplete snippets are noted as illustrative. The sole focus is **enums implementing interfaces**, while also clarifying relationships with enums, class bodies, generic interfaces, default methods, and application design.

## 1. Lesson Objectives

You will learn how to:

- Write `enum E implements Contract` with valid Java syntax.
- Understand the interface contract and override/visibility requirements.
- Distinguish a shared implementation in the enum body from an individual implementation in each constant.
- Use an enum value through an interface-typed variable and understand dynamic dispatch.
- Use `@Override` so the compiler checks the signature.
- Understand that an enum can implement **multiple interfaces**, but cannot extend a class of your choosing.
- Use interface default/static methods and resolve default-method conflicts.
- Apply generic interfaces such as `Function<String,String>`, `Comparator<String>`, and `Predicate<String>`.
- Build strategy, policy, command, and state-dependent behavior with enums.
- Understand how enum constructors, instance fields, and constant-specific class bodies work together with interfaces.
- Distinguish between an enum abstract method and an interface abstract method.
- Choose between an enum implementation, a named class, an anonymous class, and a lambda.
- Use `values()`, `valueOf`, `EnumSet`, and `EnumMap` when an enum is also an interface implementation.
- Understand `name()`, `ordinal()`, `getDeclaringClass()`, and the runtime class of constant-specific bodies.
- Evaluate identity, immutability, shared mutable state, and thread safety.
- Read common compiler errors, checked exceptions, and generic type restrictions.
- Design an API that returns an interface while still allowing code that needs a finite domain to use the enum directly.
- Test each constant against the interface contract and predict the output.

## 2. An Enum Is a Special Class, Not Just an int Constant

~~~java
enum Priority {
    LOW, MEDIUM, HIGH
}
~~~

Each `Priority.LOW` is an enum constant object. Java automatically provides mechanisms such as:

- The constants are declared in a fixed order.
- `Priority.values()` returns an array containing all constants in declaration order.
- `Priority.valueOf("LOW")` finds a constant by its exact name.
- `name()` returns the declared name, such as `"LOW"`.
- `ordinal()` returns the 0-based position in declaration order.
- Enum objects have unique identity within each declaring enum type.
- Every enum type implicitly extends `java.lang.Enum<E>`.

Although an enum has special characteristics of its own, it can still declare fields, methods, constructors (not public/protected), validly override methods, and **implement interfaces** like any other class.

Clients cannot directly call `new Priority()`; enum constants are instances determined by the enum declaration.

## 3. What Is an Interface Contract?

An interface defines the operations that implementing types must provide.

~~~java
interface Label {
    String text();
}
~~~

An enum implements the contract:

~~~java
enum Stage implements Label {
    START, FINISH;

    @Override
    public String text() {
        return name().toLowerCase(java.util.Locale.ROOT);
    }
}
~~~

`Stage` has two constants, but code using `Label` does not need to know whether they belong to an enum or a named class:

~~~java
Label label = Stage.START;
String text = label.text();
~~~

**Strength:** The caller depends on the `Label` interface and does not need to manually check `if (stage == Stage.START)` in every method.

**Limitation:** The interface contract does not itself have `values()`, `name()`, or `ordinal()`. Those operations come from enum/Enum, not from every implementation of the interface.

## 4. Runnable Program: Enum Implementing an Interface

Create the file **`EnumInterfaceBasicsDemo.java`**:

~~~java
public class EnumInterfaceBasicsDemo {
    interface Label {
        String text();
    }

    enum Stage implements Label {
        START, FINISH;

        @Override
        public String text() {
            return name().toLowerCase(java.util.Locale.ROOT);
        }
    }

    static void print(Label label) {
        System.out.println("label=" + label.text());
    }

    public static void main(String[] args) {
        print(Stage.START);
        print(Stage.FINISH);

        Label current = Stage.START;
        System.out.println("same object=" +
                (current == Stage.START));
        System.out.println("enum name=" + Stage.START.name());
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumInterfaceBasicsDemo.java
java EnumInterfaceBasicsDemo
~~~

Stdout:

~~~text
label=start
label=finish
same object=true
enum name=START
~~~

`print(Label)` accepts any implementation of Label. When Stage.START is passed, the method still calls the behavior from enum Stage via the interface reference.

## 5. Declaration Syntax: `implements` Goes After the Enum Name

Structure:

~~~java
enum EnumName implements InterfaceA, InterfaceB {
    FIRST, SECOND;

    // fields, constructors, methods...
}
~~~

The `implements` part comes **before the `{`**. The constants are listed first; if the enum also has members (fields, constructors, methods), use `;` as a separator after the list of constants.

Example:

~~~java
interface Coded {
    int code();
}

enum HttpState implements Coded {
    OK(200), NOT_FOUND(404);

    private final int code;

    HttpState(int code) {
        this.code = code;
    }

    @Override
    public int code() {
        return code;
    }
}
~~~

The constructor `HttpState(int)` is called when the constants `OK(200)` and `NOT_FOUND(404)` are initialized. Enum constructors cannot be declared `public` or `protected`. Clients also cannot call `new HttpState(200)`.

## 6. Runnable Program: Enum Constructor and Interface

Create **`EnumConstructorInterfaceDemo.java`**:

~~~java
public class EnumConstructorInterfaceDemo {
    interface Coded {
        int code();
    }

    enum HttpState implements Coded {
        OK(200), NOT_FOUND(404);

        private final int statusCode;

        HttpState(int statusCode) {
            this.statusCode = statusCode;
        }

        @Override
        public int code() {
            return statusCode;
        }
    }

    public static void main(String[] args) {
        Coded success = HttpState.OK;
        Coded failure = HttpState.NOT_FOUND;

        System.out.println(success.code());
        System.out.println(failure.code());

        for (HttpState state : HttpState.values()) {
            System.out.println(state.name() + "=" + state.code());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumConstructorInterfaceDemo.java
java EnumConstructorInterfaceDemo
~~~

Stdout:

~~~text
200
404
OK=200
NOT_FOUND=404
~~~

The interface methods are implemented by the same enum class, yet they read **each constant's own field**.

## 7. Why Is `public` Required When Implementing an Interface Method?

Normal abstract methods in an interface are `public` (and abstract, except for special cases in interfaces). Therefore, the implementing enum method must have at least `public` accessibility:

~~~java
interface Action {
    void run();
}

enum Job implements Action {
    BUILD;

    @Override
    public void run() {
        System.out.println("building");
    }
}
~~~

Accessibility cannot be reduced:

~~~java
// enum Invalid implements Action {
//     BUILD;
//     @Override
//     void run() {} // Compile error: reduces visibility of public Action.run().
// }
~~~

Always add `@Override` to the implementation so the compiler catches an incorrect name/signature or an incompatible return type.

## 8. Shared Implementation: All Constants Use One Method

If the behavior is the same except for the data, place the implementation in the **enum body**:

~~~java
interface Displayable {
    String display();
}

enum Role implements Displayable {
    READER("read"), WRITER("write");

    private final String label;

    Role(String label) {
        this.label = label;
    }

    @Override
    public String display() {
        return "[" + label + "]";
    }
}
~~~

Constant-specific bodies are not needed for READER and WRITER. Each instance has a different label field; the `display()` method is defined **once**.

**Prefer this approach when behavior is primarily data + one shared formula.** If each constant has a different algorithm, constant-specific overriding is more appropriate.

## 9. Runnable Program: Shared Implementation Reading a Field

Create **`SharedImplementationDemo.java`**:

~~~java
public class SharedImplementationDemo {
    interface Displayable {
        String display();
    }

    enum Role implements Displayable {
        READER("read"), WRITER("write");

        private final String label;

        Role(String label) {
            this.label = label;
        }

        @Override
        public String display() {
            return "[" + label + "]";
        }
    }

    public static void main(String[] args) {
        for (Role role : Role.values()) {
            Displayable value = role;
            System.out.println(value.display());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 SharedImplementationDemo.java
java SharedImplementationDemo
~~~

Stdout:

~~~text
[read]
[write]
~~~

Each constant is a Displayable. The interface call selects `Role.display`, and this method reads the corresponding label field.

## 10. Constant-Specific Class Body: One Algorithm per Constant

Syntax:

~~~java
enum Operator implements IntOperation {
    ADD {
        @Override
        public int apply(int x, int y) {
            return x + y;
        }
    },
    MULTIPLY {
        @Override
        public int apply(int x, int y) {
            return x * y;
        }
    };
}
~~~

The `{ ... }` braces after each constant create a **constant-specific class body**. In terms of type semantics, constants with class bodies belong to specialized anonymous subclasses of the enum type and can override instance methods.

This is **not** an anonymous class created by the regular `new Interface() { ... }` syntax. You are still declaring **enum constants**; you cannot create arbitrary enum instances with `new`.

### When to Use It?

- Each enum value has a different strategy.
- Each constant must fulfill an abstract behavior contract.
- The number of strategies is a finite set known at compile time.
- You want to avoid repeating `switch` chains in multiple places.

## 11. Runnable Program: Polymorphic Operators

Create **`EnumOperationDemo.java`**:

~~~java
public class EnumOperationDemo {
    interface IntOperation {
        int apply(int left, int right);
    }

    enum Operation implements IntOperation {
        ADD {
            @Override
            public int apply(int left, int right) {
                return left + right;
            }
        },
        MULTIPLY {
            @Override
            public int apply(int left, int right) {
                return left * right;
            }
        };
    }

    static int calculate(IntOperation operation,
                         int left, int right) {
        return operation.apply(left, right);
    }

    public static void main(String[] args) {
        System.out.println("add=" +
                calculate(Operation.ADD, 3, 4));
        System.out.println("multiply=" +
                calculate(Operation.MULTIPLY, 3, 4));
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumOperationDemo.java
java EnumOperationDemo
~~~

Stdout:

~~~text
add=7
multiply=12
~~~

The caller `calculate(IntOperation)` does not need to know the specific enum constant, nor does it need a `switch`; dispatch occurs according to the actual operation instance.

## 12. Abstract Methods in an Enum Combined with an Interface

An enum can declare an abstract instance method itself, requiring constant-specific class bodies to provide an implementation:

~~~java
interface TextProvider {
    String text();
}

enum Message implements TextProvider {
    HELLO {
        @Override
        public String text() {
            return "Hello";
        }
    },
    GOODBYE {
        @Override
        public String text() {
            return "Goodbye";
        }
    };

    @Override
    public abstract String text();
}
~~~

Here `text()` is a method in the interface and is also declared abstract by the enum. Each constant-specific subclass must implement the method.

**It is not mandatory** to repeat the abstract method in the enum body if each constant already provides a valid implementation for the interface contract. However, declaring it abstract in the enum body can make **the rule "each constant must implement it itself"** explicit and checked by the compiler.

### The Compiler Ensures Completeness

If you add a constant `UNKNOWN` without a body implementing `text()`, compilation will fail because the concrete enum constant does not satisfy the abstract requirement.

## 13. Runnable Program: Abstract Enum Method

Create **`AbstractEnumMethodDemo.java`**:

~~~java
public class AbstractEnumMethodDemo {
    interface TextProvider {
        String text();
    }

    enum Message implements TextProvider {
        HELLO {
            @Override
            public String text() {
                return "Hello";
            }
        },
        GOODBYE {
            @Override
            public String text() {
                return "Goodbye";
            }
        };

        @Override
        public abstract String text();
    }

    public static void main(String[] args) {
        for (Message message : Message.values()) {
            System.out.println(message.text());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 AbstractEnumMethodDemo.java
java AbstractEnumMethodDemo
~~~

Stdout:

~~~text
Hello
Goodbye
~~~

A new constant that does not implement the abstract method will be caught by javac before running the program.

## 14. Combining a Shared Implementation with Specific Overrides

Not every constant needs a class body. The enum can provide a shared method, and then only certain constants override it:

~~~java
interface Description {
    String describe();
}

enum Mode implements Description {
    NORMAL,
    SILENT {
        @Override
        public String describe() {
            return "No output";
        }
    };

    @Override
    public String describe() {
        return "Normal output";
    }
}
~~~

`Mode.NORMAL.describe()` uses the shared implementation. `Mode.SILENT.describe()` dispatches to the override in the constant-specific class body.

This is suitable when most enum constants use a default behavior and a few constants have genuine exceptions.

## 15. Runnable Program: Default in the Enum Body, Specific Overrides

Create **`EnumOverrideFallbackDemo.java`**:

~~~java
public class EnumOverrideFallbackDemo {
    interface Description {
        String describe();
    }

    enum Mode implements Description {
        NORMAL,
        SILENT {
            @Override
            public String describe() {
                return "No output";
            }
        };

        @Override
        public String describe() {
            return "Normal output";
        }
    }

    public static void main(String[] args) {
        for (Mode mode : Mode.values()) {
            Description behavior = mode;
            System.out.println(mode.name() + ":" +
                    behavior.describe());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumOverrideFallbackDemo.java
java EnumOverrideFallbackDemo
~~~

Stdout:

~~~text
NORMAL:Normal output
SILENT:No output
~~~

The caller sees the same method `Description.describe`. Dispatch is based on the actual enum constant/class behavior.

## 16. Interface-Typed References and Member Access Limitations

~~~java
interface Action {
    void execute();
}

enum Task implements Action {
    BUILD;

    @Override
    public void execute() {
        System.out.println("build");
    }
}
~~~

When writing:

~~~java
Action action = Task.BUILD;
action.execute();
~~~

This compiles properly. However:

~~~java
// action.name();  // Compile error: Action does not have name().
~~~

Even though the runtime object is a Task enum constant, the **declared type** Action determines which methods are accessible through the reference.

If business code needs the enum name, you should:
- keep variables typed as `Task` at the boundary where the finite enum domain matters;
- or add a method such as `code()` to the Action contract if all implementations need to provide a code;
- or perform an explicit type check at a justified boundary, avoiding excessive casting in core logic.

## 17. Runnable Program: An Interface Reference Does Not Lose Enum Identity

Create **`InterfaceReferenceDemo.java`**:

~~~java
public class InterfaceReferenceDemo {
    interface Action {
        String execute();
    }

    enum Task implements Action {
        BUILD, TEST;

        @Override
        public String execute() {
            return "run:" + name().toLowerCase(
                    java.util.Locale.ROOT);
        }
    }

    public static void main(String[] args) {
        Action action = Task.BUILD;

        System.out.println(action.execute());
        System.out.println("same instance=" +
                (action == Task.BUILD));

        Task original = Task.valueOf("TEST");
        System.out.println(original.name());
    }
}
~~~

~~~bash
javac -encoding UTF-8 InterfaceReferenceDemo.java
java InterfaceReferenceDemo
~~~

Stdout:

~~~text
run:build
same instance=true
TEST
~~~

An Action-typed reference does not create a wrapper/copy object. It holds a reference to the same singleton-like enum constant Task.BUILD.

## 18. An Enum Can Implement Multiple Interfaces

Java allows:

~~~java
enum Command implements Runnable, Describable {
    START;

    @Override
    public void run() {
        System.out.println("start");
    }

    @Override
    public String description() {
        return "Start command";
    }
}
~~~

The interfaces must be in a comma-separated list after `implements`, and all abstract methods must be fulfilled.

**However, an enum cannot simultaneously extend an arbitrary class**, because an enum implicitly extends `Enum<Command>`. Use interfaces to split up behavioral contracts.

## 19. Runnable Program: Two Interfaces

Create **`EnumMultipleInterfacesDemo.java`**:

~~~java
public class EnumMultipleInterfacesDemo {
    interface Describable {
        String description();
    }

    enum Command implements Runnable, Describable {
        START, STOP;

        @Override
        public void run() {
            System.out.println("run:" + name());
        }

        @Override
        public String description() {
            return "Command " + name();
        }
    }

    public static void main(String[] args) {
        Runnable runnable = Command.START;
        Describable info = Command.START;

        runnable.run();
        System.out.println(info.description());
        System.out.println("same constant=" +
                (runnable == info));
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumMultipleInterfacesDemo.java
java EnumMultipleInterfacesDemo
~~~

Stdout:

~~~text
run:START
Command START
same constant=true
~~~

An enum instance can be viewed through multiple interface references; it is still the same object.

## 20. Interface Default Methods: Enums Inherit the Implementation

An interface can provide a default method:

~~~java
interface Described {
    String code();

    default String display() {
        return "[" + code() + "]";
    }
}
~~~

The enum only needs to implement `code()` if it does not want to override `display()`:

~~~java
enum Level implements Described {
    LOW, HIGH;

    @Override
    public String code() {
        return name().toLowerCase(java.util.Locale.ROOT);
    }
}
~~~

`Level.LOW.display()` is allowed and returns `[low]`. Default methods help add shared behavior to all implementations of Described without duplicating logic.

### Do Not Confuse Default with Abstract

A default method already has a body, so overriding it in the enum is optional. For an abstract interface method without a compatible implementation, the enum must implement it itself.

## 21. Runnable Program: Default Method from an Interface

Create **`EnumDefaultMethodDemo.java`**:

~~~java
public class EnumDefaultMethodDemo {
    interface Described {
        String code();

        default String display() {
            return "[" + code() + "]";
        }
    }

    enum Level implements Described {
        LOW, HIGH;

        @Override
        public String code() {
            return name().toLowerCase(
                    java.util.Locale.ROOT);
        }
    }

    public static void main(String[] args) {
        Described first = Level.LOW;
        Described second = Level.HIGH;

        System.out.println(first.display());
        System.out.println(second.display());
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumDefaultMethodDemo.java
java EnumDefaultMethodDemo
~~~

Stdout:

~~~text
[low]
[high]
~~~

Default dispatch is still ordinary polymorphism: the default method `display` calls `code` provided by the actual implementation.

## 22. Two Interfaces with Default Methods Having the Same Signature

Consider:

~~~java
interface ShortLabel {
    default String label() {
        return "short";
    }
}

interface LongLabel {
    default String label() {
        return "long";
    }
}
~~~

If the enum implements both, Java cannot automatically choose between two unrelated default methods. The enum must **override the method** to resolve the conflict:

~~~java
enum DisplayMode implements ShortLabel, LongLabel {
    COMPACT;

    @Override
    public String label() {
        return ShortLabel.super.label() + "/" +
                LongLabel.super.label();
    }
}
~~~

`ShortLabel.super.label()` and `LongLabel.super.label()` are **interface-qualified super invocations**; this syntax differs from `Enum.super` and is only used when valid according to the rules.

## 23. Runnable Program: Resolving a Default-Method Conflict

Create **`DefaultConflictDemo.java`**:

~~~java
public class DefaultConflictDemo {
    interface ShortLabel {
        default String label() {
            return "short";
        }
    }

    interface LongLabel {
        default String label() {
            return "long";
        }
    }

    enum Mode implements ShortLabel, LongLabel {
        COMPACT;

        @Override
        public String label() {
            return ShortLabel.super.label() + "/" +
                    LongLabel.super.label();
        }
    }

    public static void main(String[] args) {
        System.out.println(Mode.COMPACT.label());
    }
}
~~~

~~~bash
javac -encoding UTF-8 DefaultConflictDemo.java
java DefaultConflictDemo
~~~

Stdout:

~~~text
short/long
~~~

If you omit the override in Mode, the declaration will not compile due to the conflict between the two inherited defaults. Choose one clear behavior or combine them intentionally.

## 24. An Interface's Static Method Does Not Become an Enum Static Method

Example:

~~~java
interface Codes {
    static String normalize(String text) {
        return text.strip().toUpperCase(
                java.util.Locale.ROOT);
    }
}
~~~

Even though `Mode implements Codes`, the client uses:

~~~java
String code = Codes.normalize(" low ");
~~~

You should not write `Mode.normalize(" low ")` and assume an inherited static interface method: **static methods of an interface are not inherited the way instance/default methods are inherited**.

If this utility is needed inside the enum implementation, call the interface name directly via `Codes.normalize(...)` or organize an appropriate helper.

## 25. Runnable Program: Interface Static Utility

Create **`InterfaceStaticUtilityDemo.java`**:

~~~java
public class InterfaceStaticUtilityDemo {
    interface Codes {
        static String normalize(String value) {
            return value.strip().toUpperCase(
                    java.util.Locale.ROOT);
        }
    }

    enum Mode implements Codes {
        LOW, HIGH;

        String normalized() {
            return Codes.normalize(name());
        }
    }

    public static void main(String[] args) {
        System.out.println(Codes.normalize(" low "));
        System.out.println(Mode.HIGH.normalized());
    }
}
~~~

~~~bash
javac -encoding UTF-8 InterfaceStaticUtilityDemo.java
java InterfaceStaticUtilityDemo
~~~

Stdout:

~~~text
LOW
HIGH
~~~

`Codes.normalize` is an interface static method. `Mode.HIGH.normalized` is an enum instance method of Mode.

## 26. Generic Interfaces: An Enum Can Fix Type Arguments

An enum declaration cannot itself declare generic type parameters like a generic class declaration `class Box<T>`. However, an enum can implement a **parameterized interface**:

~~~java
enum TextTransform
        implements java.util.function.Function<String, String> {
    TRIM {
        @Override
        public String apply(String value) {
            return value.strip();
        }
    },
    UPPER {
        @Override
        public String apply(String value) {
            return value.toUpperCase(
                    java.util.Locale.ROOT);
        }
    };
}
~~~

All constants of TextTransform are `Function<String,String>`. When passing a constant into code expecting a Function, the compiler checks the input/output types.

### Do Not Infer "Each Constant Has Its Own Generic Type Parameter"

An enum type cannot become `TextTransform<T>` where each constant has an arbitrary different T. If you need multiple heterogeneous behaviors with different type parameters, you may need named generic strategy classes/factories or separate enums.

## 27. Runnable Program: An Enum Implementing Function

Create **`EnumFunctionDemo.java`**:

~~~java
import java.util.List;
import java.util.Locale;
import java.util.function.Function;

public class EnumFunctionDemo {
    enum TextTransform implements Function<String, String> {
        TRIM {
            @Override
            public String apply(String value) {
                return value.strip();
            }
        },
        UPPER {
            @Override
            public String apply(String value) {
                return value.toUpperCase(Locale.ROOT);
            }
        };
    }

    public static void main(String[] args) {
        List<String> source = List.of(" java ", " core ");

        Function<String, String> transform =
                TextTransform.TRIM;

        System.out.println(source.stream()
                .map(transform)
                .toList());

        System.out.println(source.stream()
                .map(TextTransform.UPPER)
                .toList());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 EnumFunctionDemo.java
java EnumFunctionDemo
~~~

Stdout:

~~~text
[java, core]
[ JAVA ,  CORE ]
~~~

Stream.map accepts Function; the enum constants are implementations. `toList()` is supported in Java 16+, making it suitable for Java 17.

## 28. Enum Implementing Comparator<T>

An enum can provide a finite set of sorting strategies through `Comparator<String>`:

~~~java
enum SortMode implements java.util.Comparator<String> {
    LENGTH {
        @Override
        public int compare(String a, String b) {
            return Integer.compare(a.length(), b.length());
        }
    },
    ALPHABETICAL {
        @Override
        public int compare(String a, String b) {
            return a.compareTo(b);
        }
    };
}
~~~

Comparator only requires `compare` as a SAM (along with default/helper methods), so a lambda is also an option. An enum fits when the strategy names (`LENGTH`, `ALPHABETICAL`) are shared choices with a stable domain identity.

### Comparator Principles

A Comparator must be consistent with requirements such as antisymmetry, transitivity, and the ability to handle valid inputs. For integer quantities, use `Integer.compare` instead of `a.length()-b.length()` in general code to avoid the overflow-prone subtraction pattern.

## 29. Runnable Program: Two Comparator Constants

Create **`EnumComparatorDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class EnumComparatorDemo {
    enum SortMode implements Comparator<String> {
        LENGTH {
            @Override
            public int compare(String a, String b) {
                return Integer.compare(a.length(), b.length());
            }
        },
        ALPHABETICAL {
            @Override
            public int compare(String a, String b) {
                return a.compareTo(b);
            }
        };
    }

    public static void main(String[] args) {
        List<String> words = new ArrayList<>(
                List.of("pear", "kiwi", "apple", "fig"));

        words.sort(SortMode.LENGTH);
        System.out.println("length=" + words);

        words.sort(SortMode.ALPHABETICAL);
        System.out.println("alphabetical=" + words);
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumComparatorDemo.java
java EnumComparatorDemo
~~~

Stdout:

~~~text
length=[fig, pear, kiwi, apple]
alphabetical=[apple, fig, kiwi, pear]
~~~

`List.sort` is a stable sort: the two words of length 4 preserve their relative order with pear before kiwi after sorting by length. SortMode acts as both enum constants and Comparator implementations.

## 30. Enum Implementing Predicate<T>

`Predicate<String>` has the abstract method `boolean test(String)`. Enum constants can provide different rules:

~~~java
enum TextRule implements java.util.function.Predicate<String> {
    NON_BLANK {
        @Override
        public boolean test(String value) {
            return value != null && !value.isBlank();
        }
    },
    STARTS_WITH_J {
        @Override
        public boolean test(String value) {
            return value != null && value.startsWith("J");
        }
    };
}
~~~

This is an example of the **Strategy pattern with an enum**: the same interface for a finite set of rules.

### When Not to Use an Enum?

If a rule depends on per-request/per-user configuration and has thousands of runtime variants, creating a class/factory that accepts constructor parameters may be more natural than fixed enum constants. Enum constants are not the place to create a new object for each input request.

## 31. Runnable Program: Predicate Strategy

Create **`EnumPredicateDemo.java`**:

~~~java
import java.util.function.Predicate;

public class EnumPredicateDemo {
    enum TextRule implements Predicate<String> {
        NON_BLANK {
            @Override
            public boolean test(String value) {
                return value != null && !value.isBlank();
            }
        },
        STARTS_WITH_J {
            @Override
            public boolean test(String value) {
                return value != null && value.startsWith("J");
            }
        };
    }

    static boolean accepts(Predicate<String> rule,
                           String text) {
        return rule.test(text);
    }

    public static void main(String[] args) {
        System.out.println(accepts(TextRule.NON_BLANK, "Java"));
        System.out.println(accepts(TextRule.NON_BLANK, "   "));
        System.out.println(accepts(TextRule.STARTS_WITH_J, "Java"));
        System.out.println(accepts(TextRule.STARTS_WITH_J, "Core"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumPredicateDemo.java
java EnumPredicateDemo
~~~

Stdout:

~~~text
true
false
true
false
~~~

The caller receives a Predicate<String> and does not know whether it is an enum or a lambda. The enum provides clear names for each behavior to log/configure/select at the boundary.

## 32. Interface Default Combinators with an Enum Predicate

`Predicate<T>` has default methods such as `and`, `or`, and `negate`, allowing rules to be combined:

~~~java
java.util.function.Predicate<String> combined =
        TextRule.NON_BLANK.and(TextRule.STARTS_WITH_J);
~~~

**Important:** `combined` has type Predicate<String> but is not necessarily an enum constant or a `TextRule`; it is a composed predicate created through the default method. Do not blindly cast it back to TextRule.

Separate:
- *Named finite rule*: `TextRule.NON_BLANK` (enum constant).
- *Composed runtime rule*: `NON_BLANK.and(STARTS_WITH_J)` (a Predicate object fulfilling the contract).

If business configuration is only allowed to choose one of the named rules, keep the enum type at the configuration boundary instead of allowing arbitrary composed predicates.

## 33. Runnable Program: Composition via a Default Method

Create **`EnumPredicateCompositionDemo.java`**:

~~~java
import java.util.function.Predicate;

public class EnumPredicateCompositionDemo {
    enum Rule implements Predicate<String> {
        NON_BLANK {
            @Override
            public boolean test(String s) {
                return s != null && !s.isBlank();
            }
        },
        STARTS_J {
            @Override
            public boolean test(String s) {
                return s != null && s.startsWith("J");
            }
        };
    }

    public static void main(String[] args) {
        Predicate<String> combined =
                Rule.NON_BLANK.and(Rule.STARTS_J);

        System.out.println("Java=" + combined.test("Java"));
        System.out.println("Core=" + combined.test("Core"));
        System.out.println("blank=" + combined.test("  "));
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumPredicateCompositionDemo.java
java EnumPredicateCompositionDemo
~~~

Stdout:

~~~text
Java=true
Core=false
blank=false
~~~

`and` comes from the Predicate default method. The Rule constants do not need to reimplement the combinator themselves.

## 34. Enum Implementing Runnable or a Custom Command

With a finite set of commands, enum constants can implement a Command interface:

~~~java
interface Command {
    void execute();
}

enum BasicCommand implements Command {
    START {
        @Override
        public void execute() {
            System.out.println("start");
        }
    },
    STOP {
        @Override
        public void execute() {
            System.out.println("stop");
        }
    };
}
~~~

This is a simple form of Command/Strategy. If `execute()` needs dependencies (a database, HTTP client, or request context), pass them as method parameters or place them in an **execution context** with a clear contract, rather than storing global mutable request state inside the enum constant.

## 35. Runnable Program: Command with Passed-In Context

Create **`EnumCommandDemo.java`**:

~~~java
public class EnumCommandDemo {
    interface Command {
        void execute(Context context);
    }

    static final class Context {
        private int counter;

        void increase() {
            counter++;
        }

        void decrease() {
            counter--;
        }

        int counter() {
            return counter;
        }
    }

    enum CounterCommand implements Command {
        INCREMENT {
            @Override
            public void execute(Context context) {
                context.increase();
            }
        },
        DECREMENT {
            @Override
            public void execute(Context context) {
                context.decrease();
            }
        };
    }

    public static void main(String[] args) {
        Context context = new Context();

        CounterCommand.INCREMENT.execute(context);
        CounterCommand.INCREMENT.execute(context);
        CounterCommand.DECREMENT.execute(context);

        System.out.println("count=" + context.counter());
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumCommandDemo.java
java EnumCommandDemo
~~~

Stdout:

~~~text
count=1
~~~

Enum constants specify the logic; the mutable context is created separately for the workflow. This is usually a better design than placing a shared mutable `counter` field inside an enum constant.

## 36. Interface Contract Containing a Checked Exception

An enum implementing interface methods must adhere to `throws` declarations:

~~~java
interface Loader {
    String load() throws java.io.IOException;
}
~~~

The enum implementation can declare `throws IOException` or throw no exception, depending on the constant:

~~~java
enum Source implements Loader {
    INLINE {
        @Override
        public String load() {
            return "data";
        }
    },
    FAILING {
        @Override
        public String load() throws java.io.IOException {
            throw new java.io.IOException("missing");
        }
    };
}
~~~

Callers through a Loader reference must still handle IOException because the interface contract method declares the checked exception.

If the interface method does **not** declare a compatible checked exception, the implementing enum method cannot arbitrarily add a broader throws IOException.

## 37. Runnable Program: IOException Contract

Create **`EnumCheckedExceptionDemo.java`**:

~~~java
import java.io.IOException;

public class EnumCheckedExceptionDemo {
    interface Loader {
        String load() throws IOException;
    }

    enum Source implements Loader {
        INLINE {
            @Override
            public String load() {
                return "data";
            }
        },
        FAILING {
            @Override
            public String load() throws IOException {
                throw new IOException("missing");
            }
        };
    }

    public static void main(String[] args) {
        for (Source source : Source.values()) {
            Loader loader = source;
            try {
                System.out.println(source.name() + ":" +
                        loader.load());
            } catch (IOException ex) {
                System.out.println(source.name() + ":" +
                        ex.getMessage());
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumCheckedExceptionDemo.java
java EnumCheckedExceptionDemo
~~~

Stdout:

~~~text
INLINE:data
FAILING:missing
~~~

There are two constant behaviors but one clear `Loader` exception contract.

## 38. `values()` and `valueOf` Still Belong to the Enum Type

When an enum implements an interface, Java does **not** add `values()` or `valueOf(String)` to that interface.

~~~java
Action operation = Operation.ADD;
// operation.values(); // Wrong.
// operation.valueOf("ADD"); // Wrong.
~~~

Use the proper enum type:

~~~java
Operation[] operations = Operation.values();
Operation chosen = Operation.valueOf("ADD");
~~~

If business code wants to iterate over all enum constants, it needs to know the **enum type** or receive a collection of choices from configuration. An arbitrary Action implementation does not necessarily belong to a finite enum.

### Is `valueOf` Case-Sensitive?

Yes. `Operation.valueOf("ADD")` matches the exact declaration name; `"add"` does not match automatically. If the input comes from a user, validate/normalize at the boundary with an explicit policy instead of assuming valueOf will automatically trim/case-fold.

## 39. Runnable Program: Iterating Constants via an Interface

Create **`EnumValuesInterfaceDemo.java`**:

~~~java
public class EnumValuesInterfaceDemo {
    interface NamedAction {
        String label();
    }

    enum Action implements NamedAction {
        START, STOP;

        @Override
        public String label() {
            return name().toLowerCase(
                    java.util.Locale.ROOT);
        }
    }

    public static void main(String[] args) {
        for (Action action : Action.values()) {
            NamedAction behavior = action;
            System.out.println(behavior.label());
        }

        Action chosen = Action.valueOf("STOP");
        System.out.println("chosen=" + chosen.name());
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumValuesInterfaceDemo.java
java EnumValuesInterfaceDemo
~~~

Stdout:

~~~text
start
stop
chosen=STOP
~~~

The boundary knows the finite enum domain and therefore uses `Action.values()`; the generic execution side uses the NamedAction interface.

## 40. `EnumSet` When an Enum Implements an Interface

`EnumSet<E>` is an optimized collection for enum constants of the same declaring enum type. It requires E to be an enum type, not an arbitrary interface.

~~~java
java.util.EnumSet<Permission> permissions =
        java.util.EnumSet.of(Permission.READ, Permission.WRITE);
~~~

If the interface is named `Check`, you cannot use `EnumSet<Check>` just because Permission implements Check — Check does not satisfy the enum type bound.

**Design:** Use EnumSet<Permission> to describe the finite set of choices; inside the behavior-checking logic, each Permission can still act as the Check interface.

## 41. Runnable Program: EnumSet and Behavior

Create **`EnumSetInterfaceDemo.java`**:

~~~java
import java.util.EnumSet;

public class EnumSetInterfaceDemo {
    interface PermissionCheck {
        boolean allows(String operation);
    }

    enum Permission implements PermissionCheck {
        READ {
            @Override
            public boolean allows(String operation) {
                return "read".equals(operation);
            }
        },
        WRITE {
            @Override
            public boolean allows(String operation) {
                return "write".equals(operation);
            }
        };
    }

    public static void main(String[] args) {
        EnumSet<Permission> granted =
                EnumSet.of(Permission.READ, Permission.WRITE);

        for (Permission permission : granted) {
            PermissionCheck check = permission;
            System.out.println(permission.name() + ":" +
                    check.allows("write"));
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumSetInterfaceDemo.java
java EnumSetInterfaceDemo
~~~

Stdout:

~~~text
READ:false
WRITE:true
~~~

EnumSet iterates in the natural order of the enum declarations. The elements are still Permission constants implementing PermissionCheck.

## 42. `EnumMap`: Key Is an Enum Type, Value Can Be an Interface

`EnumMap<E,V>` requires key E to be an enum type:

~~~java
java.util.EnumMap<TaskKind, TaskHandler> handlers =
        new java.util.EnumMap<>(TaskKind.class);
~~~

Interface-typed values allow mapping from finite enum choices to reusable/customizable implementations, including named classes, lambdas, or other enum constants.

This pattern is useful when **the list of choices is closed**, yet the behavior implementation can be configured or swapped at runtime. You do not have to cram every algorithm directly into the enum body.

## 43. Runnable Program: EnumMap Associating Interface Strategies

Create **`EnumMapStrategyDemo.java`**:

~~~java
import java.util.EnumMap;
import java.util.function.IntUnaryOperator;

public class EnumMapStrategyDemo {
    enum TaskKind {
        DOUBLE, SQUARE
    }

    public static void main(String[] args) {
        EnumMap<TaskKind, IntUnaryOperator> handlers =
                new EnumMap<>(TaskKind.class);

        handlers.put(TaskKind.DOUBLE, value -> value * 2);
        handlers.put(TaskKind.SQUARE, value -> value * value);

        System.out.println("double=" +
                handlers.get(TaskKind.DOUBLE).applyAsInt(4));
        System.out.println("square=" +
                handlers.get(TaskKind.SQUARE).applyAsInt(4));
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumMapStrategyDemo.java
java EnumMapStrategyDemo
~~~

Stdout:

~~~text
double=8
square=16
~~~

This is an **alternative** to having the enum implement the interface directly. Choose an enum method when the behavior is stable and intrinsic to the choice; choose EnumMap with interface values when you need pluggable implementations.

## 44. Constant-Specific Bodies Affect Runtime Class Metadata

If an enum constant has a class body:

~~~java
enum Style {
    SIMPLE,
    CUSTOM {
        @Override
        String label() {
            return "custom";
        }
    };

    String label() {
        return "simple";
    }
}
~~~

`SIMPLE.getClass()` is normally `Style.class`, whereas `CUSTOM.getClass()` is the class of the constant-specific anonymous subclass.

To reliably get the **declaring enum class**, use `getDeclaringClass()` instead of `getClass()`:

~~~java
Style.CUSTOM.getDeclaringClass() == Style.class // true
~~~

This matters for reflection, enum registries, and code that does not want to depend on generated class names.

## 45. Runnable Program: `getClass` Differs from `getDeclaringClass`

Create **`EnumDeclaringClassDemo.java`**:

~~~java
public class EnumDeclaringClassDemo {
    interface Described {
        String description();
    }

    enum Style implements Described {
        SIMPLE,
        CUSTOM {
            @Override
            public String description() {
                return "custom";
            }
        };

        @Override
        public String description() {
            return "simple";
        }
    }

    public static void main(String[] args) {
        System.out.println("simple plain class=" +
                (Style.SIMPLE.getClass() == Style.class));
        System.out.println("custom plain class=" +
                (Style.CUSTOM.getClass() == Style.class));
        System.out.println("custom declaring class=" +
                (Style.CUSTOM.getDeclaringClass() ==
                        Style.class));
        System.out.println("custom description=" +
                Style.CUSTOM.description());
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumDeclaringClassDemo.java
java EnumDeclaringClassDemo
~~~

Stdout:

~~~text
simple plain class=true
custom plain class=false
custom declaring class=true
custom description=custom
~~~

**Do not write** business logic such as `constant.getClass() == Style.class` and assume all constants share one exact runtime class when constant-specific class bodies are present.

## 46. `name()` and `ordinal()` Are Not a Default Interface Contract

`name()` is a final instance method inherited from `Enum` that returns the declared identifier. `ordinal()` returns the declaration position.

Example:

~~~java
enum Mode {
    FIRST, SECOND
}
~~~

- `Mode.FIRST.name()` → `"FIRST"`.
- `Mode.FIRST.ordinal()` → `0`.

If an interface has a `String code()` method, the enum can implement it using `name()`, though that is not always a good API.

### Data Stability

- `ordinal()` can change when constants are reordered; do not use it as a persistent database ID.
- `name()` changes if a constant is renamed; if an external protocol requires stability, declare an explicit `code` field.
- `toString()` can be overridden; do not use it in place of `name()` when exact enum declaration identity is needed.

## 47. Runnable Program: A Stable Interface Code Distinct from `name()`

Create **`StableEnumCodeDemo.java`**:

~~~java
public class StableEnumCodeDemo {
    interface Coded {
        String code();
    }

    enum PaymentState implements Coded {
        WAITING("W"), SETTLED("S");

        private final String code;

        PaymentState(String code) {
            this.code = code;
        }

        @Override
        public String code() {
            return code;
        }
    }

    public static void main(String[] args) {
        for (PaymentState state : PaymentState.values()) {
            Coded value = state;
            System.out.println(state.name() + ":" +
                    value.code() + ":" + state.ordinal());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 StableEnumCodeDemo.java
java StableEnumCodeDemo
~~~

Stdout:

~~~text
WAITING:W:0
SETTLED:S:1
~~~

`code()` is an external/domain contract, decoupled from the names and order of enum constants.

## 48. Should You Implement `Comparable` in an Enum?

Every enum E already inherits `Comparable<E>` behavior through `java.lang.Enum<E>` and has a natural ordering based on declaration order. Enum's `compareTo` is final and cannot be overridden to change the natural order.

If you need a business ordering such as by priority score, use:
- an explicit `Comparator<E>`;
- another enum that implements `Comparator<SpecificType>`;
- a `sortKey()` field in the enum together with a Comparator that compares the key.

Do not attempt to arbitrarily redeclare `Comparable<Other>` to change the enum's own ordering; it can conflict with generic inheritance of `Comparable<E>`.

## 49. Runnable Program: Natural Enum Order and a Custom Comparator

Create **`EnumOrderingDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class EnumOrderingDemo {
    enum Priority {
        LOW(30), MEDIUM(20), HIGH(10);

        private final int rank;

        Priority(int rank) {
            this.rank = rank;
        }

        int rank() {
            return rank;
        }
    }

    public static void main(String[] args) {
        List<Priority> values = new ArrayList<>(
                List.of(Priority.HIGH, Priority.LOW, Priority.MEDIUM));

        values.sort(Comparator.naturalOrder());
        System.out.println("natural=" + values);

        values.sort(Comparator.comparingInt(Priority::rank));
        System.out.println("by rank=" + values);
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumOrderingDemo.java
java EnumOrderingDemo
~~~

Stdout:

~~~text
natural=[LOW, MEDIUM, HIGH]
by rank=[HIGH, MEDIUM, LOW]
~~~

Natural enum ordering is based on declaration order; the custom comparator is based on the explicit rank field.

## 50. Shared Mutable State in an Enum: Be Careful

Enum constants are created during class initialization and have a stable identity. However, **enum instance fields can be mutable** if you allow it.

~~~java
enum Counter {
    INSTANCE;

    int value;

    void increment() {
        value++;
    }
}
~~~

If Counter.INSTANCE is used from multiple threads, `value++` is not atomic. Being an "enum singleton" does not automatically make every method thread-safe.

### When Using an Enum as a Stateless Strategy

Prefer:
- final configuration fields set in the enum constructor;
- methods that compute on their parameters;
- passing per-request context as arguments;
- using immutable data snapshots;
- concurrency primitives if shared mutable state is truly needed.

Do not store request-specific user/session data in enum constants.

## 51. Runnable Program: AtomicInteger in an Enum When a Shared Counter Is Needed

Create **`EnumAtomicCounterDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class EnumAtomicCounterDemo {
    interface Counter {
        int incrementAndGet();
    }

    enum GlobalCounter implements Counter {
        INSTANCE;

        private final AtomicInteger value = new AtomicInteger();

        @Override
        public int incrementAndGet() {
            return value.incrementAndGet();
        }
    }

    public static void main(String[] args) {
        Counter counter = GlobalCounter.INSTANCE;

        System.out.println(counter.incrementAndGet());
        System.out.println(counter.incrementAndGet());
        System.out.println("same object=" +
                (counter == GlobalCounter.INSTANCE));
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumAtomicCounterDemo.java
java EnumAtomicCounterDemo
~~~

Stdout:

~~~text
1
2
same object=true
~~~

AtomicInteger provides atomic increments. The example runs sequentially, so stdout is deterministic; in multithreaded tests, synchronization is needed when reading the final result.

## 52. Enum Constants and Object Identity

For an enum type, each declared constant has a stable object identity. Comparing with `==` is the standard choice:

~~~java
Operation a = Operation.ADD;
Operation b = Operation.valueOf("ADD");
System.out.println(a == b);
~~~

The result is true when `Operation` is an enum type containing ADD.

When a reference has an interface as its declared type, you still hold the same object reference. No copy is needed to convert from an enum type to an interface:

~~~java
IntOperation strategy = Operation.ADD;
~~~

### `equals`

Enum.equals is final and uses the corresponding identity semantics. Do not override equals/hashCode on an enum to create a different "value equality". If the domain needs an object with many dynamic fields and value-based equality, a record or a named immutable class may be more suitable than an enum.

## 53. How Does an Enum Implementing an Interface Differ from a Named Class or a Lambda?

| Characteristic | Enum implementing interface | Named class implementing interface | Lambda |
| --- | --- | --- | --- |
| Number of instances | Fixed by enum constants | Multiple created via `new`/factory | According to lambda evaluation semantics |
| Named choices | Yes | According to class/object design | Does not inherently have enum-style names |
| Interface polymorphism | Yes | Yes | Yes, if a functional interface |
| Multiple abstract methods | Can implement | Can implement | Not directly |
| Per-instance constructor args from caller | No | Yes | Not via class constructor syntax |
| Constant-specific overrides | Yes | Via subclasses/instances | No class body |
| Generic type parameters on declaring type | Enum is not generic | Can be generic | Based on target functional type |
| `values()`/`valueOf` | Present on enum type | Not inherently present | No |
| EnumSet/EnumMap key | Yes | No | No |
| Behavioral extensibility from runtime plugins | Limited by finite constants | Broader | Broader when the target fits |
| Shared mutable state risk | Yes | Yes | Yes, via capture |

If the choices form a **finite set with domain meaning**, an enum strategy is a strong choice. If choices are configured dynamically or require per-instance dependencies, named strategies/lambdas can be more flexible.

## 54. When Is an Enum Strategy Better Than `switch`?

Suppose each call site has:

~~~java
switch (operation) {
    case ADD -> left + right;
    case MULTIPLY -> left * right;
}
~~~

A switch expression on an enum is useful and clear if the logic is short, performed **in one place**, needs compiler exhaustiveness checks, and has no plugin interface contract.

An enum implementing an interface with constant-specific methods is advantageous when:
- multiple places need the same behavior;
- you want the caller to know only the interface;
- each enum constant naturally owns an algorithm;
- you want to reduce repeated switches across multiple modules;
- you want to test the behaviors of all constants against one contract.

**It is not a rule that "every switch on an enum is wrong."** If the behavior does not belong to the enum's domain or is just a one-off mapping, a switch can be easier to read.

## 55. Runnable Program: Comparing Switch with Polymorphism

Create **`EnumSwitchVsPolymorphismDemo.java`**:

~~~java
public class EnumSwitchVsPolymorphismDemo {
    interface BinaryOp {
        int apply(int a, int b);
    }

    enum Mode implements BinaryOp {
        ADD {
            @Override
            public int apply(int a, int b) {
                return a + b;
            }
        },
        MULTIPLY {
            @Override
            public int apply(int a, int b) {
                return a * b;
            }
        };
    }

    static int withSwitch(Mode mode, int a, int b) {
        return switch (mode) {
            case ADD -> a + b;
            case MULTIPLY -> a * b;
        };
    }

    static int polymorphic(BinaryOp op, int a, int b) {
        return op.apply(a, b);
    }

    public static void main(String[] args) {
        System.out.println("switch=" +
                withSwitch(Mode.ADD, 3, 4));
        System.out.println("interface=" +
                polymorphic(Mode.MULTIPLY, 3, 4));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 EnumSwitchVsPolymorphismDemo.java
java EnumSwitchVsPolymorphismDemo
~~~

Stdout:

~~~text
switch=7
interface=12
~~~

Both are valid in Java 17. Choose the abstraction level based on reuse scope and complexity; do not replace a switch with an enum method as a mechanical rule.

## 56. Using an Interface to Decouple the Module API from the Enum Implementation

For example, the API module publishes:

~~~java
public interface DiscountPolicy {
    long apply(long cents);
}
~~~

The implementation module can use:

~~~java
enum StandardDiscount implements DiscountPolicy {
    NONE, TEN_PERCENT;

    @Override
    public long apply(long cents) {
        return switch (this) {
            case NONE -> cents;
            case TEN_PERCENT -> cents - cents / 10;
        };
    }
}
~~~

These snippets are illustrative and belong in appropriate files/packages.

The client only needs `DiscountPolicy` to apply the behavior. However, when the client has to list standard choices or parse string codes, it needs to know specifically about `StandardDiscount` (or a service that lists choices).

**API Design:** If plugins outside the module also need to implement DiscountPolicy, avoid making the interface contract depend on enum-only methods such as `name()`.

## 57. Runnable Program: Interface Contract with a Named Alternative

Create **`EnumAndNamedImplementationDemo.java`**:

~~~java
public class EnumAndNamedImplementationDemo {
    interface DiscountPolicy {
        long apply(long cents);
    }

    enum StandardDiscount implements DiscountPolicy {
        NONE {
            @Override
            public long apply(long cents) {
                return cents;
            }
        },
        TEN_PERCENT {
            @Override
            public long apply(long cents) {
                return cents - cents / 10;
            }
        };
    }

    static final class FixedDiscount implements DiscountPolicy {
        private final long reduction;

        FixedDiscount(long reduction) {
            if (reduction < 0) {
                throw new IllegalArgumentException("reduction");
            }
            this.reduction = reduction;
        }

        @Override
        public long apply(long cents) {
            return Math.max(0, cents - reduction);
        }
    }

    static long calculate(DiscountPolicy policy, long cents) {
        if (cents < 0) {
            throw new IllegalArgumentException("cents");
        }
        return policy.apply(cents);
    }

    public static void main(String[] args) {
        System.out.println("enum=" +
                calculate(StandardDiscount.TEN_PERCENT, 1000));
        System.out.println("named=" +
                calculate(new FixedDiscount(75), 1000));
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumAndNamedImplementationDemo.java
java EnumAndNamedImplementationDemo
~~~

Stdout:

~~~text
enum=900
named=925
~~~

The interface allows the core calculation to accept both a **finite enum strategy** and a **stateful named class**. This is a key advantage of designing an independent interface.

## 58. Both Enum and Lambda Implementing a Functional Interface

An enum constant implementing `Function<T,R>` or `Predicate<T>` can be passed wherever a lambda is accepted. For example:

~~~java
java.util.function.IntUnaryOperator op =
        NumberTransform.DOUBLE;
~~~

or:

~~~java
java.util.function.IntUnaryOperator op =
        value -> value * 2;
~~~

Distinctions:
- An enum has constant names, finite known strategies, and a shared stable object identity.
- A lambda has flexible behavior, can capture runtime values, and does not have an enum constants list.
- When an algorithm contains configuration that varies per request, a lambda/factory or a named class may be more suitable.
- Interface-typed APIs allow choosing the implementation approach without changing the caller signature.

## 59. Runnable Program: Enum and Lambda in One API

Create **`EnumLambdaInterchangeDemo.java`**:

~~~java
import java.util.function.IntUnaryOperator;

public class EnumLambdaInterchangeDemo {
    enum NumberTransform implements IntUnaryOperator {
        DOUBLE {
            @Override
            public int applyAsInt(int value) {
                return value * 2;
            }
        },
        SQUARE {
            @Override
            public int applyAsInt(int value) {
                return value * value;
            }
        };
    }

    static int transform(IntUnaryOperator strategy, int input) {
        return strategy.applyAsInt(input);
    }

    public static void main(String[] args) {
        System.out.println("enum=" +
                transform(NumberTransform.DOUBLE, 4));

        int offset = 3;
        System.out.println("lambda=" +
                transform(value -> value + offset, 4));
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumLambdaInterchangeDemo.java
java EnumLambdaInterchangeDemo
~~~

Stdout:

~~~text
enum=8
lambda=7
~~~

Code consuming IntUnaryOperator does not need to know whether the implementation is an enum or a lambda. `offset` is an effectively final local variable captured by the lambda.

## 60. An Enum Implementing an Interface Does Not Change Java Inheritance Rules

A Java enum:
- implicitly extends `java.lang.Enum<E>`;
- cannot have an arbitrary explicit `extends SomeClass` clause;
- can implement multiple interfaces;
- cannot be arbitrarily subclassed from outside using `extends MyEnum`;
- cannot have additional instances created with `new`.

Constant-specific class bodies provide anonymous subclasses *created by the enum declaration itself*, but that does not mean the application is allowed to subclass the enum from any arbitrary file.

### Common Mistakes

~~~java
// enum Wrong extends SomeBase implements Action { ONE } // Wrong: an enum cannot arbitrarily extend a class.
// class Extra extends MyEnum { }                    // Wrong: enums cannot be subclassed.
~~~

If you need an extensible hierarchy from plugins, use an interface + appropriate named classes/records, rather than forcing an enum to act as a framework base class with arbitrary subclasses.

## 61. Using Enum Constants in an Interface-Typed Collection

A `List<SomeInterface>` can hold enum constants alongside other implementations:

~~~java
java.util.List<DiscountPolicy> policies = java.util.List.of(
        StandardDiscount.NONE,
        StandardDiscount.TEN_PERCENT,
        new FixedDiscount(75)
);
~~~

This is a conceptual snippet based on the types from the previous example. The collection holds references to objects implementing the same interface.

**Unlike EnumSet:** `List<DiscountPolicy>` does not require elements to be enums; whereas `EnumSet<StandardDiscount>` only holds constants of the declaring enum type.

Use common interface collections when behavior can come from multiple implementation types. Use EnumSet/EnumMap when leveraging finite enum keys/domains.

## 62. Equality and `hashCode` Through an Interface

For enum constants, identity semantics are strong and stable. With interface-typed references:

~~~java
DiscountPolicy a = StandardDiscount.NONE;
DiscountPolicy b = StandardDiscount.NONE;
System.out.println(a == b); // true
~~~

However, if `DiscountPolicy` has named class instances or lambdas, equality/identity may differ. You cannot assume that **every interface implementation** is a singleton or value-equal.

### Design

If business logic needs code identity (for example, `"NONE"`), add a `String code()` method to the domain interface or store the enum code externally. Do not rely on `implementation.getClass().getName()` or `System.identityHashCode` as a business key.

## 63. Reflection When an Enum Implements an Interface

At runtime:

~~~java
Action.class.isAssignableFrom(Task.class)
~~~

is true if Task implements Action. Meanwhile:

~~~java
Task.class.isEnum()
~~~

is true for the declaring enum class. However, with a constant-specific class body, `Task.CONSTANT.getClass().isEnum()` can be false because the runtime class is a subclass of the enum, not the declaring enum class. Use:

~~~java
Task.CONSTANT.getDeclaringClass().isEnum()
~~~

to check the declaring enum type with the proper semantics.

### The Java Class API Is Not Business Metadata

Do not parse synthetic class names of constant bodies to infer strategy identity. Use `name()` or a stable explicit code() field.

## 64. Runnable Program: Reflection Confirming Interface and Enum Declaration

Create **`EnumReflectionDemo.java`**:

~~~java
public class EnumReflectionDemo {
    interface Action {
        void execute();
    }

    enum Task implements Action {
        RUN {
            @Override
            public void execute() {
            }
        };
    }

    public static void main(String[] args) {
        System.out.println("implements Action=" +
                Action.class.isAssignableFrom(Task.class));
        System.out.println("declaring enum=" + Task.class.isEnum());
        System.out.println("constant runtime enum=" +
                Task.RUN.getClass().isEnum());
        System.out.println("declaring matches=" +
                (Task.RUN.getDeclaringClass() == Task.class));
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumReflectionDemo.java
java EnumReflectionDemo
~~~

Stdout:

~~~text
implements Action=true
declaring enum=true
constant runtime enum=false
declaring matches=true
~~~

Constant-specific RUN has its own anonymous subclass class metadata; `getDeclaringClass` still returns Task.class.

## 65. Enum Constructor and Initialization Pitfalls

Enum constants are initialized during class initialization. Be especially careful when enum constructors access static fields of the enum itself that are not compile-time constants: Java imposes restrictions to avoid illegal forward references/circular initialization.

### Safe Choices

- Initialize constant configuration through constructor arguments.
- Use final instance fields to hold code/label/config.
- Avoid performing IO, threading, registering callbacks, or accessing global mutable services inside enum constructors.
- Do not publish partially initialized `this`.
- If initialization can fail, handle it according to a documented service startup policy.

For example, an enum strategy should be pure when possible:

~~~java
enum Multiplier implements java.util.function.IntUnaryOperator {
    DOUBLE(2), TRIPLE(3);

    private final int factor;

    Multiplier(int factor) {
        this.factor = factor;
    }

    @Override
    public int applyAsInt(int value) {
        return factor * value;
    }
}
~~~

This is a valid and easily testable snippet: the constants have an immutable factor configuration.

## 66. Runnable Program: Parameterized Enum Strategy

Create **`ParameterizedEnumStrategyDemo.java`**:

~~~java
import java.util.function.IntUnaryOperator;

public class ParameterizedEnumStrategyDemo {
    enum Multiplier implements IntUnaryOperator {
        DOUBLE(2), TRIPLE(3);

        private final int factor;

        Multiplier(int factor) {
            this.factor = factor;
        }

        @Override
        public int applyAsInt(int value) {
            return Math.multiplyExact(value, factor);
        }
    }

    public static void main(String[] args) {
        IntUnaryOperator doubleOp = Multiplier.DOUBLE;
        IntUnaryOperator tripleOp = Multiplier.TRIPLE;

        System.out.println("double=" + doubleOp.applyAsInt(5));
        System.out.println("triple=" + tripleOp.applyAsInt(5));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ParameterizedEnumStrategyDemo.java
java ParameterizedEnumStrategyDemo
~~~

Stdout:

~~~text
double=10
triple=15
~~~

All constants use the same algorithm but differ in their immutable factor, so constant-specific class bodies are not needed.

## 67. Null Handling in Enum Interface Methods

Enum constants are not null; however, **arguments** passed into interface methods can be null unless forbidden by the contract.

Example:

~~~java
enum Formatter implements java.util.function.UnaryOperator<String> {
    TRIM;

    @Override
    public String apply(String input) {
        return java.util.Objects.requireNonNull(
                input, "input").strip();
    }
}
~~~

The API must clearly define:
- return an empty string for null?
- reject with a NullPointerException/IllegalArgumentException?
- or represent a missing value with Optional?

Each constant should not adopt a different null policy when they must all satisfy a common interface contract, unless the domain explicitly specifies the difference.

## 68. Runnable Program: Consistent Argument Validation

Create **`EnumNullValidationDemo.java`**:

~~~java
import java.util.Objects;
import java.util.function.UnaryOperator;

public class EnumNullValidationDemo {
    enum Formatter implements UnaryOperator<String> {
        TRIM, UPPER;

        @Override
        public String apply(String input) {
            String checked = Objects.requireNonNull(input, "input");

            return switch (this) {
                case TRIM -> checked.strip();
                case UPPER -> checked.toUpperCase(
                        java.util.Locale.ROOT);
            };
        }
    }

    public static void main(String[] args) {
        System.out.println(Formatter.TRIM.apply(" Java "));

        try {
            Formatter.UPPER.apply(null);
        } catch (NullPointerException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 EnumNullValidationDemo.java
java EnumNullValidationDemo
~~~

Stdout:

~~~text
Java
rejected=input
~~~

You can provide a shared implementation using switch when null validation applies to every constant. If the algorithms are complex, constant-specific methods can be easier to extend.

## 69. Unit Tests: Every Constant Must Conform to the Interface Contract

For an enum `Strategy implements Function<X,Y>`, tests should:

1. Iterate over `Strategy.values()` to check every constant.
2. Verify the result with normal inputs.
3. Check boundary values and negative/null inputs according to the contract.
4. Check overflow, precision, locale, and encoding if relevant to the logic.
5. Verify exception types and messages according to the API.
6. Check shared mutable state/cross-request behavior if the enum holds state.
7. Check interface default methods/composition.
8. Verify persistence-code stability when an external protocol uses code().
9. Verify that every enum constant is registered in mapping/selection.
10. Do not test generated synthetic class names of constant bodies.

**Insufficient:** testing only `Operation.ADD` and trusting that the other constants are implemented correctly. The compiler checks signatures, but it cannot prove the arithmetic/business semantics of a method body.

## 70. Runnable Program: Contract Tests for the Whole Enum

Create **`EnumContractTestDemo.java`**:

~~~java
public class EnumContractTestDemo {
    interface IntOperation {
        int apply(int left, int right);
    }

    enum Operation implements IntOperation {
        ADD {
            @Override
            public int apply(int left, int right) {
                return left + right;
            }
        },
        MULTIPLY {
            @Override
            public int apply(int left, int right) {
                return left * right;
            }
        };
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        check(Operation.ADD.apply(2, 3) == 5, "ADD");
        check(Operation.MULTIPLY.apply(2, 3) == 6, "MULTIPLY");

        for (Operation operation : Operation.values()) {
            IntOperation polymorphic = operation;
            check(polymorphic.apply(1, 1) >= 1,
                    operation.name());
        }

        System.out.println("specific cases PASS");
        System.out.println("interface contract PASS");
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumContractTestDemo.java
java EnumContractTestDemo
~~~

Stdout:

~~~text
specific cases PASS
interface contract PASS
~~~

These are compact executable assertions. In real projects, JUnit parameterized tests can iterate over enum constants and check more case tables.

## 71. Do Not Use an Enum When the Set of Implementations Needs Dynamic Extension

An enum is a finite type determined by its source declaration. You cannot add enum constants at runtime via a configuration file, database row, or plugin JAR while preserving proper enum semantics.

If business requirements call for:
- users creating their own policies;
- new plugins implementing behavior;
- each customer having different configuration;
- strategies with complex constructor dependencies;
- multiple runtime instances per strategy;

then define an **interface contract**, and provide named implementations/factories/service registration. An enum can represent **standard built-in choices**, not necessarily the entire universe of behaviors.

### Combination

A `DiscountPolicy` interface + `StandardDiscount` enum + `ConfigurableDiscount` class is a model that is usually more flexible than trying to cram every rule into enum constants.

## 72. Checklist for Choosing an Enum Implementing an Interface

Before designing, check:

- Is the set of choices finite, stable, and part of the domain?
- Does each choice have sufficiently clear behavior to attach directly to the enum?
- Is there a single accurate interface contract for all choices?
- Does the caller benefit from not needing to know the specific enum type?
- Does the behavior only differ in data, or does each constant truly need an override?
- Is there a need to implement multiple interfaces?
- Do default methods help with shared behavior?
- Are there conflicts between default methods that need to be resolved?
- Are checked exceptions clearly defined?
- Are generic type arguments uniform across all constants?
- Is there any dangerous shared mutable state?
- Are the enum's name/ordinal being used as an external ID?
- Does the logic require runtime plugins/configurable instances?
- Does testing cover all constants and boundaries?
- Do EnumSet/EnumMap help represent finite choices?
- Does code using reflection know that a constant-specific runtime class differs from the declaring enum class?

If many answers indicate a need for dynamic configuration, consider named strategy classes or an EnumMap mapping to other implementations.

## 73. Common Compiler Errors

| Issue | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| `enum E extends Base` | Enum implicitly extends Enum<E> | Remove extends; use an interface/composition |
| `enum E implements I` but missing an abstract method | Contract is not implemented | Implement the shared method or implement per constant |
| Interface-implementing method missing `public` | Reduces visibility | Declare `public` |
| Wrong @Override method signature | Does not override contract | Match name, args, and return type |
| Constant has a body without implementing enum abstract method | Constant must be concrete | Override in each body |
| Two interface defaults with the same signature | Inheritance conflict | Override and resolve explicitly |
| Calling `EnumType.interfaceStaticMethod` | Static interface methods are not inherited | `InterfaceName.method` |
| `new EnumType()` | Cannot arbitrarily instantiate an enum | Use constants |
| Casting an interface-typed value to an enum without certainty | May be another implementation | Check the type first or keep the enum at the boundary |
| `EnumSet<MyInterface>` | EnumSet requires an enum type | `EnumSet<MyEnum>` |
| Calling `name()` through an interface that does not declare name() | Declared type restricts the API | Use the enum type or domain code() |
| `enum MyEnum<T>` | Enum declarations are not generic like classes | Implement a fixed parameterized interface |
| Overriding `Enum.compareTo` | Enum.compareTo is final | Use a Comparator |
| Refactoring a constant body while relying on `getClass()==Enum.class` | Constant body creates a subclass | Use `getDeclaringClass()` |
| Adding IOException in an implementation not allowed by the contract | Checked exception override restriction | Adjust throws contract/handle it |
| Mutating an enum field concurrently without synchronization | Singleton constant is not automatically thread-safe | Immutable state/Atomic/synchronization |

## 74. Anti-Patterns to Avoid

**A giant enum depending on every service:** Each constant calling HTTP, SQL, UI, and global config makes code hard to test and complicates init/lifecycle. Separate service dependencies.

**Using ordinal as a database key:** Changing the declaration order alters the meaning of existing data.

**Overusing name/toString as a public API protocol:** A stable code field is needed instead.

**Storing request state in enum constants:** All requests share the same constant object, causing data races and data leakage between workflows.

**Forcing an interface to rely on enum-only APIs:** Not every implementation of the interface is an enum.

**Repeatedly using `instanceof`/casts after receiving an interface:** The interface may be missing a needed operation; review the API contract.

**Avoiding every switch:** A switch expression on an enum can be clear and exhaustively checked; not every one-line mapping needs to become a constant-specific class body.

**Checking the runtime class with `getClass()==EnumType.class`:** Wrong for constants with specific bodies; use `getDeclaringClass()`.

**Not testing individual algorithms:** Valid interface method signatures do not guarantee that each constant's logic is correct.

## 75. Exercise 1 — Write the Correct Syntax

An interface:

~~~java
interface Action {
    void run();
}
~~~

Declare an enum Job with constants BUILD and CLEAN that both print the constant name.

**Answer:**

~~~java
enum Job implements Action {
    BUILD, CLEAN;

    @Override
    public void run() {
        System.out.println(name());
    }
}
~~~

`Job.BUILD.run()` prints BUILD. `Job.CLEAN.run()` prints CLEAN. The method implementation is shared.

## 76. Exercise 2 — Different Behavior per Constant

`interface Operation { int apply(int a,int b); }` and enum ADD/MULTIPLY.

**Suggested Answer:** Use constant-specific bodies overriding `public int apply(int,int)`; ADD returns a+b, MULTIPLY returns a*b. It can also be implemented together using a switch when the logic is very short. Test both.

## 77. Exercise 3 — Visibility

~~~java
interface Task {
    void execute();
}

enum Job implements Task {
    RUN;

    // void execute() {} // Wrong.
}
~~~

**Answer:** The implementation must be `public void execute()`, preferably with `@Override`. The interface abstract method `execute()` is public.

## 78. Exercise 4 — Interface Default Method

An interface has `String code()` and default `String display(){ return "["+code()+"]"; }`. An enum implements code.

**Answer:** Overriding display in the enum is not mandatory; the default method already has an implementation. `enumConstant.display()` calls the default method and through `code()` receives the proper constant behavior.

## 79. Exercise 5 — Two Interfaces with the Same Default

Interfaces A and B both have default `String label()`. The enum implements both.

**Answer:** The enum must override label to resolve the conflict. You can call `A.super.label()` or `B.super.label()` inside the override using valid Java interface-super syntax.

## 80. Exercise 6 — Enum and Generic Interface

Can you declare `enum Transform implements Function<String,String>`?

**Answer:** Yes. All constants implement the same Function<String,String> contract. However, declaring something like `enum Transform<T>` as a generic class is invalid.

## 81. Exercise 7 — Interface Variable

~~~java
Runnable callback = SomeEnum.RUN;
~~~

Suppose SomeEnum implements Runnable. Can you call `callback.name()` directly?

**Answer:** No, Runnable does not have `name()`. The runtime object is still an enum constant, but the declared type of the reference is Runnable.

## 82. Exercise 8 — EnumSet

Given `enum Permission implements Check { READ, WRITE; ... }`. Should you write `EnumSet<Check>` or `EnumSet<Permission>`?

**Answer:** `EnumSet<Permission>`, because the EnumSet generic parameter must be an enum type. The Check interface does not satisfy the bound `E extends Enum<E>`.

## 83. Exercise 9 — Constant-Specific Metadata

`enum X { A, B { @Override String text(){...} }; String text(){...} }`. Is `X.B.getClass()==X.class` necessarily true?

**Answer:** No; B has a constant-specific class body, so B's runtime class differs from the declaring enum class X. `X.B.getDeclaringClass()==X.class` is true.

## 84. Exercise 10 — Enum Strategy and Shared State

An enum implements Counter, has `int value` and `value++`. Multiple threads call the same constant.

**Answer:** It is not thread-safe just because it is an enum. Use immutable/per-request state, AtomicInteger, or appropriate synchronization if a shared mutable counter is a genuine requirement.

## 85. Exercise 11 — Choosing a Solution

A discount policy has four fixed kinds, each calculated by its own formula, with no per-user config.

**Suggested Answer:** An enum implementing DiscountPolicy with constant-specific bodies or a shared implementation + immutable fields. If kinds are added via plugins or runtime config, named implementations/a registry may be more suitable.

## 86. Exercise 12 — Testing the Contract

Why does the compiler accept an enum implementing an interface, yet unit tests are still needed for every constant?

**Answer:** The compiler guarantees signatures/types/access contracts, not that each implementation uses the right formula, null policy, overflow/precision, or exception semantics. Iterate over `values()` and test per-constant scenarios.

## 87. Summary of Rules to Remember

- **An enum can implement interface(s)** with `enum E implements I1, I2`.
- **An enum cannot itself extend an arbitrary class** because it already has the implicit superclass Enum<E>.
- **The interface contract** can be implemented in common in the enum body or individually for constants.
- **A constant-specific body** creates a specific override for behavior and affects runtime class metadata.
- **Interface default methods** are inherited if there is no conflict/override.
- **Static interface methods** are called via the interface name, not inherited like instance methods.
- **Generic interfaces** can be implemented by an enum with fixed type arguments.
- **EnumSet/EnumMap** require an enum type as the element/key, not just an interface type.
- **Enum values()/valueOf** are enum APIs and do not belong to an arbitrary interface.
- **Enum constants are fixed instances**, not instantiated further with `new`.
- **Polymorphism through an interface** lets the caller depend on the contract rather than a specific constant.
- **Long-lived shared enum state**: prefer immutability and pay attention to concurrency.
- **getDeclaringClass()** is suitable for identifying the enum type when constant-specific bodies are present.
- **Thoroughly test** every constant to ensure contract behavior.

## 88. End-of-Lesson Checklist

- [ ] I can write `enum E implements I` with valid syntax.
- [ ] I understand that an enum is a special class with fixed constants.
- [ ] I know that an enum implicitly extends Enum<E>.
- [ ] I know that an enum can implement multiple interfaces.
- [ ] I properly use `public` and `@Override` when implementing an interface method.
- [ ] I can distinguish between a shared method and constant-specific overrides.
- [ ] I know that an enum abstract method can force every constant to implement it individually.
- [ ] I know that an interface default method can be inherited by an enum.
- [ ] I can resolve a default-method conflict.
- [ ] I know that a static interface method is not inherited like an instance method.
- [ ] I can pass an enum constant to an interface-typed method.
- [ ] I can distinguish between interface APIs and enum-only APIs.
- [ ] I know that `values()`/`valueOf` exist only on the declaring enum type.
- [ ] I know that enum constructors pass configuration for each constant.
- [ ] I do not use `new` to create enum objects.
- [ ] I can implement generic Function/Predicate/Comparator interfaces with an enum.
- [ ] I know that a composed Predicate is not necessarily still an enum constant.
- [ ] I use EnumSet<EnumType> and EnumMap<EnumType,V> properly.
- [ ] I do not use ordinal as a durable external ID.
- [ ] I understand how `getClass` and `getDeclaringClass` differ with specific bodies.
- [ ] I do not override the final Enum.compareTo/equals/hashCode methods.
- [ ] I know that enum constants have a stable identity.
- [ ] I understand that mutable enum fields are not automatically thread-safe.
- [ ] I use a per-request context instead of storing session state on an enum.
- [ ] I know that checked exceptions must comply with the interface contract.
- [ ] I can distinguish a finite enum strategy from runtime plugin implementations.
- [ ] I know when a switch is clearer than constant-specific methods.
- [ ] I test every constant and boundary condition.
- [ ] I can predict the stdout of the Java 17+ programs above.

**Conclusion:** **An enum implementing an interface** is a way to combine a **finite, clearly named set of choices** with a **polymorphic behavioral contract**. You can implement a method once in the enum body, or override it per constant-specific class body. The interface allows general calling code without depending on the implementation, while the enum provides `values()`, `EnumSet`, `EnumMap`, and stable identity. Choose an enum strategy for closed domain choices; choose named classes/lambdas/a registry when behavior needs to be configured or extended at runtime. Always keep enum state simple, contracts clear, and test the behavior of **each constant**.
