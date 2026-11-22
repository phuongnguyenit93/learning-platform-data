# Method Declaration Structure and the Meaning of Each Component in Java

In Java, a **method** defines an operation that can be performed within the scope of a class, interface, or an appropriate type declaration. A method declaration answers the questions: **who can call it**, **by what name it is called**, **what data must be provided**, **what result it returns**, **what errors it can report**, and **what code is executed** when called. Understanding the declaration structure is a foundational step before using object methods and designing readable APIs.

This lesson uses Java 17 and later, analyzing simple methods through methods with generics, variable-arity parameters, exceptions, and special methods in abstract classes/interfaces.

## 1. Overview of a Method Declaration

Consider a method inside a class:

~~~java
public final int addPoints(int amount) {
    if (amount < 0) {
        throw new IllegalArgumentException("Điểm không được âm");
    }
    points = Math.addExact(points, amount);
    return points;
}
~~~

This is **a method snippet located inside a class that has an `int points` field**, not a standalone file yet. Its components include:

| Component | In the example | Role |
| --- | --- | --- |
| Access modifier | `public` | Determines the scope of code permitted to call the method |
| Behavior modifier | `final` | Prevents subclasses from overriding this instance method |
| Return type | `int` | The returned result is an `int` integer |
| Method name | `addPoints` | Identifier used in calls |
| Parameter list | `(int amount)` | Receives an `int` argument, assigned to the `amount` parameter |
| Method body | `{ ... }` | Contains the statements that perform the work |
| Return statement | `return points;` | Terminates the current call and returns the value |

The method above does not declare `throws`, yet it can still throw **unchecked** exceptions, such as `IllegalArgumentException` or `ArithmeticException` from `Math.addExact`. Whether `throws` is present or not is not a guarantee that the method will never throw an exception.

### General Syntax Pattern

~~~text
[annotation]
[method-modifier ...] [<type-parameters>] return-type methodName(
    [formal-parameters]
) [throws ExceptionType1, ExceptionType2] {
    // method body
}
~~~

Square brackets in the diagram represent **optional components when explaining syntax**, not characters typed literally into Java. The parts always required in a regular method declaration with a body are the **return type, name, parentheses, and body**; modifiers, generic type parameters, parameters, and `throws` may be omitted.

A minimal valid example inside a class:

~~~java
void greet() {
    System.out.println("Xin chào");
}
~~~

In this example, the method has package-default access (none of `public`, `protected`, or `private` is written), requires no arguments, and returns no value. **The parentheses `()` are still required in the declaration**, even when there are no parameters.

## 2. Modifiers: Access Control and Method Properties

A method can have access modifiers and modifiers that change how it is used. Not all modifiers are valid together or in every kind of declaration.

### Access Levels

| Declaration | Basic calling access |
| --- | --- |
| `public` | Code that can access the enclosing class can call it, subject to module and other type constraints |
| `protected` | Same package or subclass contexts permitted under Java rules |
| *No access modifier written* | **Package-private**: types in the same package |
| `private` | Only within the scope of the class or declaring type permitted under Java access rules; nestmates have a corresponding access mechanism |

Saying a method is `public` does not mean any code can call it regardless of whether the enclosing class is `private`/package-private or the package is not exposed via `exports` in the module system. **Method accessibility also depends on the type containing the method and the usage context**.

A method declared **without an access modifier** is package-private. `default` in an interface's `default void run() { ... }` is a **modifier for a method with a default body**, not a keyword indicating a "default" access level.

### Common Behavior Modifiers

| Modifier | Primary meaning | Things to note |
| --- | --- | --- |
| `static` | Method belongs to the class, called via the class name; has no `this` | Cannot directly use instance fields without an object |
| `final` | Prohibits overriding an instance method in subclasses | Does not apply to making the return value immutable |
| `abstract` | Declares a method without an implementation; its body ends with `;` | The enclosing class must be abstract, except in appropriate interface contexts |
| `synchronized` | Synchronizes execution on the monitor of the instance, or of the `Class` if static | Does not replace proper concurrency design across the entire system |
| `native` | Declares a method implemented through a native mechanism | Has no Java body; rarely used in ordinary application code |
| `strictfp` | Historical modifier related to floating-point arithmetic | Java 17 already uses strict floating-point semantics; it is unnecessary for new code |

A declaration cannot be both `abstract` and `final`; `abstract` needs to be implemented by overriding in a concrete subclass, whereas `final` prevents overriding. An `abstract` method also cannot be declared `static` or `private` in ways that conflict with these rules.

**Typically**, in application examples, we use `public` for operations exposed externally, `private` for implementation details, `static` for operations that do not depend on the state of an instance, and `final` when we truly want to prohibit overriding.

## 3. Return Type: `void` and Value-Returning Methods

Following the modifiers is the return type, for example `int`, `String`, `boolean`, `List<String>`, `int[]`, or `void`.

- **`void`:** the method does not return a result value. You can write `return;` to exit early, or let execution reach the end of the method body.
- **Specific type:** the method must ensure that normal completion paths return an expression compatible with the declared type, such as `return count;` if returning `int`.
- **Reference type:** can return a reference to an object, for example `String`, `Student`, `List<String>`; the return type does not automatically create an object.
- **Array:** `int[] scores()` returns a reference to an `int[]` array.

Valid examples when placed inside a class:

~~~java
void reset() {
    count = 0;
}

int count() {
    return count;
}

String status(boolean ready) {
    if (ready) {
        return "READY";
    }
    return "WAITING";
}
~~~

Assume the class has an `int count` field. This snippet only illustrates methods; it is not yet a program with `main`.

An intentional error example:

~~~java
int broken(boolean ok) {
    if (ok) {
        return 1;
    }
    // Compilation error: there is a normal completion path that does not return int
}
~~~

**`return` and `System.out.println` are not synonymous.** `println` displays output to stdout, whereas `return` passes the result value back to the caller. A method can print data without returning a value, return a value without printing, or do both.

## 4. Method Names and Naming Conventions

A method name is an identifier such as `calculateTotal`, `isReady`, or `getBalance`. Java's identifier rules apply: keywords such as `class` or `return` cannot be used as method names in the usual way, names cannot start with a digit, and names are case-sensitive.

The common Java convention is **lowerCamelCase**:

- `deposit`, `withdraw`: verbs representing state-changing operations;
- `calculateTotal`: computational behavior;
- `isActive`, `hasPermission`: questions for a `boolean` value;
- `balance`, `getBalance`: providing readable state if there is a public reason.

You should choose names that express intent rather than vague names like `doSomething`. The method name is part of the API that callers must understand, so readability is more important than saving a few characters.

Method names are case-sensitive: `print` and `Print` are two different names. Do not rely on capitalization differences to create two hard-to-distinguish behaviors.

## 5. Formal Parameter List

*Formal parameters* are declared **inside parentheses**; each regular parameter has a type and a name:

~~~java
int multiply(int left, int right) {
    return left * right;
}
~~~

When calling `multiply(3, 4)`, the two expressions `3` and `4` are **arguments**, while `left` and `right` are **parameters** inside the method body. The order of arguments corresponds to the order of parameters, and Java checks whether the types are compatible or whether an allowed conversion exists.

A method can have no parameters: `balance()`. Multiple parameters are separated by commas: `transfer(Account receiver, long amount)`.

Parameters can have the `final` modifier and appropriate annotations:

~~~java
void printLabel(final String label) {
    System.out.println(label);
}
~~~

Here, `final` **prohibits reassigning the parameter variable** `label` inside the method, though it does not by itself guarantee that any referenced object is immutable. Parameters can also be primitive types, reference types, arrays, and appropriate generic types.

### Java Always Passes Arguments by Value

With `int amount`, a copy of the integer value is assigned to the parameter. With `Account account`, a copy of the **reference value** is assigned to the parameter; both the caller and the method can point to the same object. The method can modify the object's state if permitted, but assigning `account = new Account(...)` inside the method body does not make the caller's variable point to the new object.

Distinguish this from "pass-by-reference" in the sense used by other languages; Java passes **values**, even when that value is a reference.

## 6. Varargs: Variable Number of Arguments

The syntax `Type... name` declares a **variable arity parameter**, shortened to *varargs*. For example:

~~~java
int sum(int... numbers) {
    int total = 0;
    for (int number : numbers) {
        total = Math.addExact(total, number);
    }
    return total;
}
~~~

`sum(1, 2, 3)` returns 6; `sum()` returns 0; it can also be called with an array `sum(new int[] {1, 2, 3})` because at runtime, a varargs parameter is handled as an array.

Declaration rules:

- Each method can have at most **one** varargs parameter.
- If varargs is present, it must be the **last parameter**.
- Write `int... numbers`, not `int numbers...`.
- The method body can use `numbers.length`, `numbers[index]`, and loops over the array.

An **intentionally invalid syntax** example that cannot compile:

~~~java
void invalid(String... names, int year) {
}
~~~

Varargs does not mean every way of calling is valid: Java still checks argument types, and calls involving overloads/varargs can sometimes become ambiguous.

## 7. Generic Method: Type Parameters Placed Before the Return Type

In a generic method, the **type parameter list** is placed **after the modifiers but before the return type**.

~~~java
public static <T extends CharSequence> String describe(T label, int value) {
    return label + " = " + value;
}
~~~

Here:

- `public static`: modifiers.
- `<T extends CharSequence>`: declares the type parameter `T`, with an upper bound of `CharSequence`.
- `String`: the **return** type, independent of the choice of `T`.
- `describe`: the method name.
- `(T label, int value)`: the parameter list consisting of one value of type `T` and one `int`.

You can pass a `String` or `StringBuilder` as `label` because both are compatible with `CharSequence`. The compiler usually infers `T` from the arguments; when needed, you can specify a type witness, such as `Example.<String>describe("x", 3)` if the method is in the `Example` class.

Do not confuse `<T>` appearing **before** the return type with `List<T>` **as** the return type. A generic method can have both at the same time:

~~~java
static <T> java.util.List<T> singleton(T element) {
    return java.util.List.of(element);
}
~~~

This snippet is self-contained at the class-declaration level; `List.of` does not accept `null` as an element and may throw `NullPointerException`.

## 8. The `throws` Clause and How It Differs from `throw`

`throws` appears **after the parentheses** (and after array brackets if the discouraged trailing array syntax is used), before the method body:

~~~java
static String readFirstLine(java.nio.file.Path path)
        throws java.io.IOException {
    try (var reader = java.nio.file.Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
~~~

This snippet illustrates a method placed inside a class, using Java 17+ APIs. `throws java.io.IOException` indicates that the operation may throw a **checked exception**; callers normally must `catch` it or propagate it with an appropriate `throws` declaration. The read method may return `null` if the file has no lines.

Comparison:

| Keyword | Typical location | Meaning |
| --- | --- | --- |
| `throws IOException` | In the method **header** | Declares the type of exception that may propagate so the compiler can check it |
| `throw new IOException("...")` | In the method **body** | Actually throws an exception object at runtime |
| `return value` | In the method **body** | Returns a result and completes the call normally |

A method can declare `throws A, B` for multiple appropriate exception types. For **unchecked exceptions** such as `IllegalArgumentException`, Java does not require a `throws` declaration. Declaring `throws` does not require a direct `throw` statement in the body: the exception can also originate from a called method.

## 9. Method Body and Completion Rules

The `{ ... }` part is the **method body**, containing local variable declarations, statements, method calls, conditionals, loops, `try`/`catch`, and appropriate `return` statements.

~~~java
static String verdict(int score) {
    if (score >= 5) {
        return "PASS";
    }
    return "RETRY";
}
~~~

When calling `verdict(7)`, the `if` branch returns `"PASS"`; the rest is not executed in that call. When calling `verdict(3)`, the result is `"RETRY"`.

A `void` method can reach the closing `}` at the end of the body without needing `return;`. For a value-returning method, Java does not allow a normal execution path to fall off the end of the body without a return value.

In particular, **not every method has a body inside its declaration itself**. An `abstract` or `native` method ends with `;`, while its implementation comes from a subclass or corresponding native code:

~~~java
abstract class Shape {
    abstract double area();
}
~~~

*This is an illustrative abstract class definition snippet; it has no `main`.* Do not write `{ }` for `abstract double area();`; if an empty body is written, the declaration no longer conforms to abstract method syntax.

## 10. Complete Example: Reading Each Part and Running It

Create the file **`MethodDeclarationDemo.java`**. The file has a package-level `Report` class and a `public MethodDeclarationDemo` class containing `main`.

~~~java
import java.io.IOException;

class Report {
    private int total;

    Report(int opening) {
        if (opening < 0) {
            throw new IllegalArgumentException("Số ban đầu không được âm");
        }
        this.total = opening;
    }

    public int add(int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("Số cộng không được âm");
        }
        total = Math.addExact(total, amount);
        return total;
    }

    public void print() {
        System.out.println("Total: " + total);
    }

    public void print(String prefix) {
        System.out.println(prefix + total);
    }

    public static boolean isValid(int amount) {
        return amount >= 0;
    }

    public static <T extends CharSequence> String join(
            T label, String... parts) throws IOException {
        if (parts.length == 0) {
            throw new IOException("Thiếu nội dung");
        }
        return label + ": " + String.join(", ", parts);
    }
}

public class MethodDeclarationDemo {
    public static void main(String[] args) {
        Report report = new Report(10);

        System.out.println(report.add(5));
        report.print();
        report.print("Số dư = ");
        System.out.println(Report.isValid(0));

        try {
            System.out.println(Report.join(
                    new StringBuilder("Mục"), "A", "B"));
            Report.join("Rỗng");
        } catch (IOException ex) {
            System.out.println("Lỗi: " + ex.getMessage());
        }
    }
}
~~~

In the directory containing the file, run:

~~~bash
javac -encoding UTF-8 MethodDeclarationDemo.java
java MethodDeclarationDemo
~~~

Stdout:

~~~text
15
Total: 15
Số dư = 15
true
Mục: A, B
Lỗi: Thiếu nội dung
~~~

### Analyzing Each Declaration in the Program

**Constructor `Report(int opening)`:** looks quite similar to a method, but it is a **constructor**, not a method in the semantic sense of Java declarations. It shares the same name as the class and **has no return type**, not even `void`. `new Report(10)` creates the object and then initializes the `total` field via the constructor.

**`public int add(int amount)`:** `public` is the access level, `int` is the return type, `add` is the name, and `amount` is an `int` parameter. Inside the body, an invalid condition throws an exception; if valid, the amount is added to the instance field `total` and the method returns the new balance.

**`public void print()`:** has no parameters and return type `void`. It prints `Total: 15` and **does not return a value** to a caller variable.

**`public void print(String prefix)`:** has the same name `print` but includes an additional parameter. This is another **overload** of `print`; the JVM/compiler distinguishes the two calls based on the appropriate parameter list.

**`public static boolean isValid(int amount)`:** a static method, used as `Report.isValid(0)` without needing a `Report` object to receive the call. The method does not depend on the instance field `total` and returns `boolean`.

**`public static <T extends CharSequence> String join(T label, String... parts) throws IOException`:** simultaneously illustrates access control, the static modifier, a generic type parameter, the `String` return type, a regular parameter, varargs, and a checked exception clause. The call with `StringBuilder` shows that `T` does not have to be `String`.

**`public static void main(String[] args)`:** the conventional entry point when running a Java 17 application in the classic way. `public` allows the launcher to access it, `static` allows running without instantiating `MethodDeclarationDemo`, `void` returns no result, and `String[] args` receives command-line arguments (which may have no elements).

Amounts, points, or totals here are merely illustrative data; what matters is that **the same declaration structure template** can express very different behaviors.

## 11. Instance Methods and Static Methods

Both forms share the same header–body structure, but how they are called and their access to state differ:

| Characteristic | Instance method | Static method |
| --- | --- | --- |
| Declaration example | `int add(int amount)` | `static boolean isValid(int amount)` |
| Typical invocation | `report.add(5)` | `Report.isValid(5)` |
| Has `this`? | Yes (in an appropriate context) | No |
| Accesses instance fields? | Can directly use fields of `this` | Requires a reference to an object |
| Can be overloaded? | Yes | Yes |
| Overridden in subclasses? | Yes, when eligible and not `final` | Static methods are **not overridden**; they can be *hidden* |

You should not call a static method through an object variable (even though Java has cases that allow it), because writing `Report.isValid(...)` clearly shows that this is a class-level operation.

In `Report.add`, the name `total` is equivalent to `this.total` when no other variable shadows the name. Meanwhile, `Report.isValid` cannot write `this.total`, because a static method has no `this`.

## 12. Overloading: Same Name with Different Parameter Lists

The following two declarations in `Report` are valid:

~~~java
public void print() {
    System.out.println("Total: " + total);
}

public void print(String prefix) {
    System.out.println(prefix + total);
}
~~~

They differ in **parameter count and types**, so the compiler can select the matching method for `report.print()` or `report.print("Số dư = ")`.

According to the Java Language Specification, a **method signature** relates to the **method name and formal parameter type list** under specific compatibility/generics rules. It **does not include the return type, parameter variable names, access modifiers, or throws clauses** for distinguishing overloads.

An intentional error example:

~~~java
int size() {
    return 1;
}

long size() {
    return 2L;
}
~~~

If these two declarations are placed in the same class, the compiler reports a **duplicate method declaration**: differing only in the return types `int` and `long` is not enough to create a valid overload.

Similarly, replacing `int value` with `int count` **only renames the parameter** and does not create a new signature. Varargs `String... values` is treated as the array type `String[]` in the signature; you cannot declare an additional overload `void test(String[] values)` alongside `void test(String... values)` in the same class as if they were two distinct signatures.

Do not confuse **overloading** (multiple methods with the same name and different parameters) with **overriding** (a subclass providing a replacement implementation for an eligible instance method of a superclass).

## 13. Overriding and the `@Override` Annotation

Annotations can appear before a method's modifiers. `@Override` asks the compiler to verify that the method actually overrides or implements a corresponding method from a superclass/interface.

Standalone example: create the file **`OverrideMethodDemo.java`**:

~~~java
class Message {
    public String text() {
        return "Base";
    }
}

class FriendlyMessage extends Message {
    @Override
    public String text() {
        return "Hello";
    }
}

public class OverrideMethodDemo {
    public static void main(String[] args) {
        Message message = new FriendlyMessage();
        System.out.println(message.text());
    }
}
~~~

~~~bash
javac OverrideMethodDemo.java
java OverrideMethodDemo
~~~

Stdout:

~~~text
Hello
~~~

`@Override` is an annotation; it is not a return type. `public String text()` in the subclass has the same name and parameter list as the overridden method, and a compatible return type. If you accidentally rename it to `texts()`, the compiler reports an error thanks to `@Override`. In this example, calling `message.text()` selects the implementation of the **actual object** `FriendlyMessage`.

`@Override` does not replace overriding rules: a valid `final` method in a superclass cannot be overridden; static methods are not overridden, and can only be hidden according to hiding rules.

## 14. Differences When Declaring Methods in an Interface

An interface can declare abstract methods, as well as `default`, `static`, and `private` methods according to the rules of modern Java versions.

Example type definition (without `main`):

~~~java
interface Greeter {
    String greet(String name);

    default String greetMorning(String name) {
        return "Good morning, " + name;
    }

    static boolean validName(String name) {
        return name != null && !name.isBlank();
    }

    private String prefix() {
        return "Hello";
    }

    default String greetWithPrefix(String name) {
        return prefix() + ", " + name;
    }
}
~~~

Explanation:

- `String greet(String name);` is an abstract method of the interface, implicitly `public abstract`. It has **a `;` instead of a body**, and a concrete implementing class must provide a corresponding implementation unless a valid implementation is inherited.
- `default String greetMorning(...)` has a default execution body and is permitted in an interface.
- `static boolean validName(...)` belongs to the interface itself and is called via `Greeter.validName(...)`.
- `private String prefix()` is an internal helper method inside the interface (Java 9+); it has a body and cannot be called directly by implementing classes like a public method.

The `default` modifier in an interface is **completely different** from the case where a class omits an access modifier (package-private). In Java 17, you cannot arbitrarily use `default` as a method modifier in a regular class the way you do in an interface.

## 15. Common Syntax, Type, and Declaration Errors

| Error | Incorrect example or misconception | Correct understanding |
| --- | --- | --- |
| Omitting the return type | `public calculate() { ... }` in a class not named `calculate` | A method must have a return type such as `void`, `int`, or `String`; constructors are a separate case |
| Writing `void` for a constructor | `void Report(int opening) { ... }` | This becomes a method named `Report`, **not a constructor** |
| Omitting `()` | `void greet { ... }` | Requires `void greet() { ... }` |
| Returning the wrong type | `int count() { return "x"; }` | The expression after `return` must be compatible with the `int` type |
| Missing return | `int count() { if (ok) return 1; }` | Normal completion paths must return a value |
| Returning a value from `void` | `void run() { return 1; }` | `void` can only use `return;` or reach the end of the body |
| Using `this` in static | `static void run() { this.run(); }` | A static method has no `this` |
| Placing varargs in the middle | `void f(int... values, String name)` | Varargs, if present, must come last |
| Wrong position for type parameter | `static String <T> f(T x)` | Write `static <T> String f(T x)` |
| Defining overloads differing only in return type | `int f()` and `String f()` | Same signature, not two valid overloads |
| Confusing `throws` with `throw` | `throws new IOException()` in header | `throws IOException` declares the type; `throw new IOException()` is in the body |
| Using `abstract` with a body | `abstract void f() { }` | An abstract method ends with `;` |
| Using `default` as package-private | `default void f() { }` in a regular class | Package-private means **not writing an access modifier** |
| Confusing parameter with argument | Calling `add(amount)` and treating `amount` as the declaration | `int amount` in the declaration is the parameter; the expression in a call is the argument |

Another error is **declaring a method inside the body of another method** like a "nested function". Java does not support declaring a regular method directly inside another method; you must move the declaration to become a member of the class or use an appropriate construct such as a lambda for a specific function.

## 16. How to Quickly Read a Complex Declaration

Look at the following declaration line (this is only the header; the body already appeared in the `Report.join` method in the complete example):

~~~java
public static <T extends CharSequence> String join(
        T label, String... parts) throws IOException
~~~

Reading from left to right:

1. `public` — the caller has access depending on the context.
2. `static` — the operation belongs to the class, with no `this`.
3. `<T extends CharSequence>` — declares the generic type `T`.
4. `String` — result type.
5. `join` — method name.
6. `T label` — first parameter, of type `T`.
7. `String... parts` — last parameter receiving a variable number of `String` elements.
8. `throws IOException` — indicates a checked exception that may propagate to the caller.
9. `{ ... }` in the actual definition — contains the statements performing the operation.

This way of reading is helpful when encountering method signatures in Java libraries. Being able to read a declaration lets you predict where the method is allowed to be called and verify the input/output types before writing execution code.

## 17. Knowledge Self-Check

**Question 1.** In `private static long multiply(int a, int b)`, which parts are the access modifier, class-level modifier, return type, name, and parameters?

**Question 2.** Fix the declaration `public sum(int a, int b) { return a + b; }` into a valid method that returns an integer sum, without being mistaken for a constructor.

**Question 3.** Why is `void send(String... messages, boolean urgent)` invalid? If you want to pass multiple messages, fix the parameter positions.

**Question 4.** A method writes `int value()` but only has `System.out.println(5);` in its body, with no `return`. Will it compile? Why or why not?

**Question 5.** Do the two methods `int size()` and `long size()` in the same class create valid overloads? If two different behaviors are needed, what can be changed?

**Question 6.** How does `throws IOException` differ from `throw new IOException("error")`? In the case of a checked exception, what must the caller do?

**Question 7.** In `static <T> T identity(T item)`, do the `<T>` component and the other two `T` occurrences play the same role?

**Question 8.** What rules must a method annotated with `@Override` still obey? Can `static` and `final` methods be overridden like normal instance methods?

**Answer Key:**

1. `private`, `static`, `long`, `multiply`, two parameters `int a` and `int b`.
2. `public int sum(int a, int b) { return a + b; }`.
3. Varargs must be last: `void send(boolean urgent, String... messages)`.
4. No; the method is declared to return `int` yet can complete normally without returning an `int`.
5. No; they differ only in return type. Change the parameter type list/count or give the methods different names according to their meaning.
6. `throws` is a declaration in the header; `throw` executes throwing an exception in the body. The caller handles it or propagates an appropriate checked exception declaration.
7. `<T>` **declares the type parameter**; `T` in the return type and parameter type positions **uses** that type.
8. The method must genuinely override/implement a valid declaration; `final` prevents overriding, while `static` applies hiding instead of overriding.

## 18. Reference Documentation

- [Java Language Specification 17, §8.4 — Method Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4): method structure in classes, modifiers, parameters, method signature, body, and exceptions.
- [Java Language Specification 17, §9.4 — Interface Method Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.4): method declarations in interfaces.
- [Java Language Specification 17, §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): invocation rules and method selection.

**Remember:** the structure **modifiers → type parameters (if any) → return type → name → parameter list → throws (if any) → body or semicolon** defines the method's contract. Reading each part of the declaration helps you understand how to call it properly, the data types passed and received, and the constraints that Java checks at compile time.
