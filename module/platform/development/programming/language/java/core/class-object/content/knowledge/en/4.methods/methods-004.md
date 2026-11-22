# Void Methods and Value-Returning Methods in Java

In Java, a **method** is a block of statements declared in a class or interface to perform a behavior. When declaring a method, the developer must specify the **return type**. The two basic cases are:

- **`void` methods:** perform an action but **do not return a value** to the caller.
- **Value-returning methods:** declare a specific type (for example, `int`, `boolean`, `String`, or a user-defined class) and return **a value compatible** with the declared type.

Choosing the right return type helps make the API design clear: a method that **performs work** such as printing a message can use `void`; a method that **computes or provides a result** such as calculating a sum or checking a condition should generally return a value.

## 1. Structure of a Method Declaration

A typical method in a class has the form:

```java
[modifier] returnType methodName(parameterList) {
    // Statements in the method body
}
```

This is a **syntax diagram**, not a standalone Java program. The components:

| Component | Example | Role |
| --- | --- | --- |
| Modifier (if any) | `public`, `private`, `static` | Access level or characteristics of the method |
| Return type | `void`, `int`, `String` | Specifies whether the call produces a usable value, and what the type of the value is |
| Method name | `printMessage`, `calculateTotal` | The name used to invoke the method |
| Parameter list | `int a, int b` | Declares the input data received; may have no parameters |
| Method body | `{ ... }` | Statements executed when the method is called |

Example:

```java
static void printMessage(String message) {
    System.out.println(message);
}

static int add(int a, int b) {
    return a + b;
}
```

Both methods can accept input data. The difference is that **`printMessage` does not produce a return value**, whereas **`add` has a result of type `int`**.

`void` is the keyword for declaring **no return value**. `void` cannot be used as a regular variable type, and `void` is **not** an object or a `null` value.

## 2. `void` Methods: Performing Work Without Returning a Value

A `void` method is often used when the primary purpose is to **produce a side effect**, such as:

- Printing a message or writing logs.
- Updating the state of an object.
- Sending a request, saving data, or performing I/O operations.
- Modifying an object through an API that controls data.
- Executing a sequence of processing steps whose result does not need to be returned to the caller.

Example:

```java
class Lamp {
    private boolean on;

    void turnOn() {
        on = true;
    }

    boolean isOn() {
        return on;
    }
}
```

`turnOn()` returns `void` because its purpose is to change the state of the `on` field. `isOn()` returns `boolean` because the caller needs to know whether the lamp is on or off.

**`void` does not mean "doing nothing."** A `void` method can still perform temporary calculations, call other methods, update data, and throw exceptions.

### 2.1. `void` Methods Can End Naturally

```java
static void greet(String name) {
    System.out.println("Xin chào, " + name);
}
```

If execution reaches the closing `}` at the end of the method body without another exit statement, the `void` method terminates and returns **control** to the caller. No result value is returned.

### 2.2. `return;` in `void` Methods

The `return` keyword is **not prohibited** in a `void` method. The valid form is `return;` **with no expression after it**. It terminates method execution immediately at that point.

```java
static void printPositive(int number) {
    if (number <= 0) {
        System.out.println("Bỏ qua: " + number);
        return; // Exit early; do not return a value
    }

    System.out.println("Hợp lệ: " + number);
}
```

With `printPositive(-2)`, the program prints `Bỏ qua: -2` and then exits the method; the `Hợp lệ` line does not run. With `printPositive(5)`, the condition is false, so the program prints `Hợp lệ: 5` and terminates at the end of the method body.

`return;` is often used as a **guard clause** to avoid nesting multiple `if` statements, as long as the control flow remains easy to understand.

### 2.3. `return expression;` Is Not Allowed in `void` Methods

The snippet below is **invalid**:

```java
static void calculate() {
    return 10; // Compile error: a void method cannot return a value
}
```

To return `10`, the return type must be changed:

```java
static int calculate() {
    return 10;
}
```

If you only want to exit early in a `void` method, use `return;`.

## 3. Value-Returning Methods: Declared Type and the `return` Statement

For a non-`void` method, the type placed before the method name indicates the **result type** that the caller is permitted to receive.

```java
static int multiply(int a, int b) {
    return a * b;
}

static boolean isEven(int number) {
    return number % 2 == 0;
}

static String fullName(String firstName, String lastName) {
    return firstName + " " + lastName;
}
```

- `multiply` returns `int`.
- `isEven` returns `boolean`.
- `fullName` returns a reference of type `String`.

The `return expression;` statement performs three important tasks:

1. Evaluates the expression after the `return` keyword.
2. Converts the result into a type compatible with the declared return type (according to conversion rules permitted by Java).
3. Terminates method execution at that point and passes the value back to the caller.

For example, `int result = multiply(3, 4);` causes the variable `result` to receive `12`. Code **after an executed `return` statement** in the same call will not continue to run.

Do not confuse **parameter types** with **return types**. `static double average(int a, int b)` accepts two `int` values but returns a `double`; the two groups of types are independent and serve two different directions of data transfer.

## 4. Complete Java 17 Program Combining `void` and Value-Returning Methods

Save all of the following code to the file **`MethodReturnDemo.java`**:

```java
class Receipt {
    final int amount;

    Receipt(int amount) {
        this.amount = amount;
    }
}

public class MethodReturnDemo {
    static void greet(String name) {
        System.out.println("Xin chào, " + name);
    }

    static int add(int a, int b) {
        return a + b;
    }

    static boolean isAdult(int age) {
        return age >= 18;
    }

    static String category(int score) {
        if (score >= 80) {
            return "Giỏi";
        }
        if (score >= 50) {
            return "Đạt";
        }
        return "Cần cố gắng";
    }

    static void printPositive(int number) {
        if (number <= 0) {
            System.out.println("Bỏ qua: " + number);
            return;
        }
        System.out.println("Hợp lệ: " + number);
    }

    static Receipt createReceipt(int amount) {
        return new Receipt(amount);
    }

    public static void main(String[] args) {
        greet("An");

        int sum = add(7, 5);
        System.out.println("Tổng: " + sum);
        System.out.println("Đủ tuổi: " + isAdult(20));
        System.out.println("Xếp loại: " + category(76));

        printPositive(-3);
        printPositive(4);

        Receipt receipt = createReceipt(150);
        System.out.println("Biên lai: " + receipt.amount);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 MethodReturnDemo.java
java MethodReturnDemo
```

**Exact stdout:**

```text
Xin chào, An
Tổng: 12
Đủ tuổi: true
Xếp loại: Đạt
Bỏ qua: -3
Hợp lệ: 4
Biên lai: 150
```

Explanation:

1. `greet("An")` is a `void` method call; its effect is printing a message.
2. `add(7, 5)` returns the integer `12`; the calling code stores the result in `sum` and then prints it.
3. `isAdult(20)` returns the boolean value `true`, which can be concatenated into a string when printing.
4. `category(76)` returns `"Đạt"` due to the second conditional branch. Even though there are multiple `return` statements in the source code, **only one execution path is chosen** for a single call.
5. `printPositive(-3)` hits the early `return;`, so it does not print `Hợp lệ: -3`; `printPositive(4)` reaches the end of the body and prints `Hợp lệ: 4`.
6. `createReceipt(150)` returns **a reference to a newly created `Receipt` object**. The caller can read `receipt.amount` because this field has appropriate access in the example (the classes are in the same package).

`Receipt` and `MethodReturnDemo` are two top-level classes in the same source file; only `MethodReturnDemo` is declared `public`. The code above intentionally has no dependencies outside the JDK.

## 5. Using the Result of a Method Call

A method call with a non-`void` return type is an **expression that has a value**, so it can appear in many different contexts:

```java
int total = add(3, 5);                   // Assign the result to a variable
int doubled = add(3, 5) * 2;             // Use in an expression
System.out.println(add(3, 5));          // Pass as an argument
if (isAdult(20)) {                       // Use in a boolean condition
    System.out.println("Đủ tuổi");
}
```

These short snippets assume they are inside a method that can call `add` and `isAdult` declared in section 4; they are **not standalone programs**.

In particular, **it is not required to store the result** in a variable:

```java
add(3, 5); // Valid, but the result 8 is ignored
```

Java allows a method call to be used as an expression statement even when it returns a value. Ignoring the result is sometimes reasonable if the method also has a side effect; however, for a function that only performs computation, this is often a sign of a coding mistake or a missing step that uses the result.

Conversely, **a `void` call does not provide a value** that can be assigned or used in expressions requiring a value.

```java
greet("An");                // Valid: void method call statement
int x = greet("An");        // WRONG: void cannot be converted to int
System.out.println(greet("An")); // WRONG: println requires an argument with a value
```

If you simply want to both print a greeting and have a string for further use, you need to separate the intent into a method that **returns a string** and a print statement:

```java
static String greeting(String name) {
    return "Xin chào, " + name;
}

// In main:
String message = greeting("An");
System.out.println(message);
```

`greeting` produces a value, whereas `println` performs the printing action and has return type `void`. This separation makes it easy to test the result and reuse the string-creating method.

## 6. Distinguishing `return` from `System.out.println`

These two actions are **not equivalent**:

| `return` | `System.out.println` |
| --- | --- |
| Passes a value back to the caller (if the method has a return type) | Writes content to standard output |
| Terminates the current method call immediately at that statement | After printing finishes, subsequent statements can still run |
| The result can be stored or reused by the caller | `println` itself returns `void` |
| Does not have to display any information on the screen | Has the effect of printing to the screen/output stream |
| `return;` is valid in a `void` method to exit early | `println` can be called from both `void` and non-`void` methods |

An example that is wrong in terms of intent:

```java
static int square(int number) {
    System.out.println(number * number);
    // WRONG: missing return of an int value
}
```

Simply printing the result `number * number` **does not satisfy** the `int` return type requirement. The correct version if you want to **return** it is:

```java
static int square(int number) {
    return number * number;
}
```

The caller decides whether to display or store the result:

```java
int result = square(6);
System.out.println(result); // 36
```

If the task is truly only to print the square and there is no need to return a result, you can use:

```java
static void printSquare(int number) {
    System.out.println(number * number);
}
```

The choice depends on **the method's contract**, not on whether there is a calculation inside.

## 7. Non-`void` Methods Must Return on Every Normal Completion Path

For a method declared to return a value, Java verifies that there is no **execution path that can complete normally without a return value**. This is a compile-time check; it is not enough that "most cases have a `return`."

### Incorrect Example: Missing Return Branch

```java
static String result(int score) {
    if (score >= 50) {
        return "Đạt";
    }
    // WRONG: if score < 50, the method reaches the end of its body without returning
}
```

Fix using `else`:

```java
static String result(int score) {
    if (score >= 50) {
        return "Đạt";
    } else {
        return "Chưa đạt";
    }
}
```

Or use a default result after `if`:

```java
static String result(int score) {
    if (score >= 50) {
        return "Đạt";
    }
    return "Chưa đạt";
}
```

Both approaches satisfy the requirement: every path that **completes normally** returns a `String`.

### `return` Inside Loops and `switch`

`return` inside a loop or `switch` **exits the entire method**, not just the loop/`switch`. Do not confuse it with `break` or `continue`:

- `break` typically exits the matching loop or `switch` block.
- `continue` skips the rest of the current loop iteration and moves to the next iteration.
- `return` terminates the method and can send a result back to the caller.

For some loops, the compiler cannot guarantee that an iteration triggering `return` will always occur, so paths where the loop does not execute or the branch is not entered must still be considered. A value-returning method **can throw an exception** instead of returning in a branch; when an exception exits the method, that branch is not a normal completion path.

### Example with an Exception Instead of a Value

```java
static int positiveValue(int number) {
    if (number <= 0) {
        throw new IllegalArgumentException("number must be positive");
    }
    return number;
}
```

If `number <= 0`, the method throws an exception and **no `int` value is returned**. If `number > 0`, the method returns `number`. This is valid code; there is no need to write `return` after `throw`.

## 8. The Return Type Must Be Compatible with the Expression in `return`

Java checks the return type **at compile time**, even if the result is not used by the caller.

### 8.1. Returning Primitives

```java
static long count() {
    return 10;        // Valid: int literal is widened to long
}

static double average(int a, int b) {
    return (a + b) / 2.0; // double, not integer division
}

static boolean hasItems(int count) {
    return count > 0;
}
```

`return "10";` is invalid in a method declared to return `int`; Java does not automatically convert a `String` into an integer in a `return` statement. Similarly, `return 1;` is invalid for a `boolean` return type.

A method declared to return `double` can return an `int` expression through an appropriate widening conversion, but that **does not fix an operation already computed in the wrong type**. For example, `return (a + b) / 2;` performs **integer division** first and only then converts the result to `double`. Use `2.0` in the division if you want a decimal value.

### 8.2. Returning References

```java
static CharSequence label() {
    return "Hello";            // String is a CharSequence
}

static Object box() {
    return Integer.valueOf(7); // Integer is also an Object
}
```

The type of the `return` expression must be appropriately convertible to the return type. A superclass/interface type can accept a reference to an object of a compatible subclass or implementing class.

### 8.3. Returning `null`

```java
static String findName(boolean found) {
    if (found) {
        return "An";
    }
    return null;
}
```

`null` is a valid value for a **reference type** (except under specialized language/tool constraints), but **not** a value for a primitive type.

```java
static int findNumber() {
    return null; // WRONG: null cannot be converted to int
}
```

A method returning `String` with `null` can cause the caller to encounter a `NullPointerException` when executing `findName(false).length()`. Clearly document the contract if `null` may be returned, or design a result type that represents the not-found state, such as `Optional<String>` when appropriate.

### 8.4. `void` Differs from `Void` and `null`

- `void` (lowercase) indicates that a method **has no return value**.
- `java.lang.Void` (capitalized) is **a reference class** often used in generic APIs to represent the absence of a meaningful result; it **does not turn into `void`**.
- A method declared with `Void` can use `return null;`, because `null` is a reference value; this is not the same as `void` with `return;`.

Illustrative example:

```java
static void doWork() {
    return; // void: no value
}

static Void doOtherWork() {
    return null; // Void: returns a null reference value
}
```

There is no need to use `Void` for regular methods if `void` serves the purpose; `Void` mainly appears in generic API contracts, for example `Callable<Void>`.

## 9. Returning Primitives vs. Returning Objects: Understanding Reference Values

Java **passes parameters by value**, and the `return` statement likewise provides a **value** to the caller. When the type is a reference type, that value is a **reference to the object**, not an automatic copy of the entire object.

Example:

```java
class Box {
    int value;

    Box(int value) {
        this.value = value;
    }
}

class Factory {
    static Box createBox() {
        return new Box(10);
    }

    static Box sameBox(Box input) {
        return input;
    }
}
```

The declarations above are examples for use in other code, not a standalone program. Place this snippet inside a method that has access:

```java
Box first = Factory.createBox();
Box second = Factory.sameBox(first);
second.value = 99;

System.out.println(first.value);  // 99
System.out.println(first == second); // true
```

- `createBox()` creates a new `Box` object and returns a reference to that object.
- `sameBox(first)` receives a copy of the reference value, and then `return input;` returns a reference to the same object; there is no `new Box(...)` inside `sameBox`.
- Because `first` and `second` reference the same object, modifying `second.value` is observed through `first.value`.
- For `int`, `double`, `boolean`, etc., a returned primitive value does not inherently have an "object-sharing" mechanism like a reference.

A method that returns a reference **does not automatically protect internal state**. If a mutable object held inside a class is returned directly, the caller can modify that object if its API allows it. When encapsulation is needed, consider immutable objects or a defensive copy.

## 10. Methods Can Both Return a Value and Have Side Effects

The difference between `void` and non-`void` lies in the **result type**, not a rule of "having or not having side effects."

Example of a method that **returns a value** while also modifying state:

```java
class Counter {
    private int value;

    void increment() {
        value++;
    }

    int incrementAndGet() {
        value++;
        return value;
    }

    int getValue() {
        return value;
    }
}
```

- `increment()` modifies the field and has no return value.
- `incrementAndGet()` **both** modifies the field **and** returns the new value.
- `getValue()` only reads the field and returns its value, without modifying the field in this implementation.

If the business requirement is simply "perform the change," `void` is usually appropriate. If the caller **needs** the state or result after the operation, returning a value can be useful. Choose the return type to reflect the **public meaning of the API**, not merely based on the number of lines of code inside.

### Runnable Example: Side Effects and Return Values

Save as **`CounterDemo.java`**:

```java
class Counter {
    private int value;

    void increment() {
        value++;
    }

    int incrementAndGet() {
        value++;
        return value;
    }

    int getValue() {
        return value;
    }
}

public class CounterDemo {
    public static void main(String[] args) {
        Counter counter = new Counter();
        counter.increment();
        System.out.println("Sau void: " + counter.getValue());

        int newValue = counter.incrementAndGet();
        System.out.println("Kết quả trả về: " + newValue);
        System.out.println("Giá trị hiện tại: " + counter.getValue());
    }
}
```

```bash
javac -encoding UTF-8 CounterDemo.java
java CounterDemo
```

Stdout:

```text
Sau void: 1
Kết quả trả về: 2
Giá trị hiện tại: 2
```

There is no contradiction in `incrementAndGet()` updating state and returning a result. When using a real API, what you need to read is the method's **contract** regarding its return value and side effects.

## 11. `return` and `finally`: Execution Order You Need to Know

In `try`/`finally`, Java ensures that the `finally` block is executed while exiting `try` in normal cases, even when a `return` is present. Therefore, you should not assume that "encountering `return` skips every `finally`."

Runnable example, saved as **`FinallyReturnDemo.java`**:

```java
public class FinallyReturnDemo {
    static int compute() {
        try {
            System.out.println("Đang tính");
            return 10;
        } finally {
            System.out.println("Dọn dẹp");
        }
    }

    public static void main(String[] args) {
        System.out.println("Kết quả: " + compute());
    }
}
```

```bash
javac -encoding UTF-8 FinallyReturnDemo.java
java FinallyReturnDemo
```

Stdout:

```text
Đang tính
Dọn dẹp
Kết quả: 10
```

The expression after `return` is evaluated first; then `finally` runs before the result is handed back to the caller. **Avoid writing `return` inside `finally`**: it can mask the return value or an active exception being thrown and make the program unpredictable. `finally` can also encounter special situations such as abrupt JVM termination where execution does not proceed like normal flow, so it should not be treated as an absolute guarantee in all system scenarios.

## 12. Relation to Method Overriding and Overloading

The return type affects a method's contract, but it is not enough to distinguish two methods with the same name when **overloading**.

### 12.1. Cannot Overload by Return Type Alone

Incorrect example:

```java
class Calculator {
    int parse(String text) {
        return Integer.parseInt(text);
    }

    double parse(String text) {
        return Double.parseDouble(text);
    }
}
```

Both methods share the name `parse` and the same parameter list `(String)`. They **cannot coexist** merely because one returns `int` and the other returns `double`. In Java, the return type **is not part of the method signature used to distinguish overloads**.

Valid example:

```java
class Calculator {
    int parse(String text) {
        return Integer.parseInt(text);
    }

    double parse(double value) {
        return value;
    }
}
```

The two `parse` methods above have **different parameter lists**, so they are valid. In real-world API code, choose names so that the meaning of each operation is clear rather than trying to use overloading to "select" a desired result type.

### 12.2. Overriding and Return Types

When **overriding** an instance method, the subclass method must satisfy Java's return type compatibility rules:

- It can keep the exact same return type.
- For reference types, it can use a **covariant return type** (returning an appropriate subtype of the reference return type in the superclass).
- You cannot arbitrarily change a `void`-returning method into an `int`-returning method when overriding, nor change a primitive type `int` to `long`.

Illustrative example:

```java
class Animal {
}

class Dog extends Animal {
}

class AnimalFactory {
    Animal make() {
        return new Animal();
    }
}

class DogFactory extends AnimalFactory {
    @Override
    Dog make() {
        return new Dog(); // Valid: Dog is a subtype of Animal
    }
}
```

The subclass `DogFactory` can declare `Dog make()` because `Dog` is a subtype of `Animal`. This is **overriding**, which differs from **overloading**. The snippet above consists of illustrative type declarations and has no `main`.

## 13. `void` Methods and Value-Returning Methods in Interfaces

An interface can declare behaviors with both result forms:

```java
interface Printer {
    void print(String text);

    int pagesPrinted();
}
```

An implementing class must provide appropriate method bodies if it is a concrete class:

```java
class ConsolePrinter implements Printer {
    private int pages;

    @Override
    public void print(String text) {
        System.out.println(text);
        pages++;
    }

    @Override
    public int pagesPrinted() {
        return pages;
    }
}
```

In an interface, regular abstract methods are `public abstract` according to the language rules. Therefore, the implementing methods in a concrete class use `public`; you cannot reduce the visibility to package-private. `print` is `void` and `pagesPrinted` returns `int`. The two methods represent two different functions: **performing an action** and **querying information**.

An `abstract` method without a body only **declares a contract**; only a method with a body directly contains `return` statements. When implementing it, the `void`/non-`void` rules still apply just as in regular classes.

## 14. Choosing a Return Type for an Easy-to-Use API

Base the choice on the method's goal:

| Goal | Usually Suitable Return Type | Example |
| --- | --- | --- |
| Print a message | `void` | `void printInvoice()` |
| Calculate a total amount | `int`, `long`, or an appropriate numeric type | `long totalPrice()` |
| Check a condition | `boolean` | `boolean isValid()` |
| Return a display name | `String` | `String displayName()` |
| Find an object | A reference type or `Optional<T>` depending on the contract | `Optional<User> findUser(int id)` |
| Create an object | An appropriate class or interface | `Receipt createReceipt()` |
| Update data without needing to return information | `void` | `void changePassword(String value)` |
| Update and need to know whether it succeeded | `boolean` or an appropriate result type | `boolean tryReserve(int count)` |
| Update and return the new state | The type of the state | `int incrementAndGet()` |

**It is not mandatory** for every update action to return `void`: an update method can return a status, the number of affected rows, or the object itself to support a fluent API. Conversely, a calculation method can choose `void` if the contract only requires outputting the result via I/O. What matters is that **the caller knows what it will receive**.

For a testable API, pure calculations (with little or no side effects) should generally **return the result** and let the caller decide whether to print, save, or use it. For example, `int calculateTotal()` is more convenient to reuse than `void printTotal()` when the same result must be used across the UI, tests, and business logic.

Avoid creating a "dummy" return value (for example, `return 0;`) just to satisfy the compiler when the method genuinely has no meaningful result. Adjust the return type or clearly define the contract instead.

## 15. Common Errors and How to Fix Them

| Symptom | Cause | Fix |
| --- | --- | --- |
| `void cannot be converted to int` or an equivalent message | Assigning the result of a `void` call to a numeric variable | Change the method design to return `int` or remove the assignment |
| `return 5;` inside `void method()` | Trying to return a value in a `void` method | Use `return;` or change the return type |
| `return;` inside `int method()` | Not returning a value of the required type | Use a compatible `return expression;` |
| `missing return statement` | There is a normal completion path missing `return` | Cover all branches with a result or use `throw` for invalid data |
| `System.out.println(result)` and assuming the method returned `result` | Confusing writing to stdout with returning | Add `return result;` if the return type requires it |
| Returning `null` from an `int` method | `null` is only valid for reference types | Return a valid number or redesign the API |
| `return "123";` from an `int` method | String is not automatically converted to int | Convert explicitly in a controlled way, for example `Integer.parseInt(...)` |
| Two methods with the same name/parameters but different return types | Attempting to overload by return type alone | Change the parameter list or method name |
| Calculation result has an incorrect fractional part | Integer division before returning `double` | Use floating-point arithmetic, for example `/ 2.0` |
| Returning a mutable object and the caller unexpectedly mutates data | Returning the same reference to internal state | Encapsulate, create an appropriate copy, or use an immutable object |
| Writing `return` inside `finally` and losing the original result | `finally` can abruptly alter how the method completes | Keep `finally` for cleanup and avoid `return` there |

`javac` messages may vary across JDKs. Read the **return type** declaration line, inspect every `return` statement, and identify where the **call result is being used**.

## 16. Self-Practice with Answers

### Exercise 1: Which Methods Are `void`?

Consider the following declarations:

```java
static void a() { System.out.println("A"); }
static int b() { return 10; }
static String c() { return "C"; }
static void d() { return; }
```

**Answer:** `a` and `d` are `void` methods. `d` has `return;` but does not produce a value. `b` returns `int` and `c` returns `String`.

### Exercise 2: Which Part Is Wrong?

```java
static int absolute(int x) {
    if (x < 0) {
        return -x;
    }
}
```

**Answer:** Missing `return x;` (or an appropriate result) when `x >= 0`. Fix:

```java
static int absolute(int x) {
    if (x < 0) {
        return -x;
    }
    return x;
}
```

With `x = Integer.MIN_VALUE`, negating an `int` can overflow; this example only illustrates the `return` flow and does not replace an absolute-value API that must account for all data cases.

### Exercise 3: Predict the Output

```java
static void announce() {
    System.out.println("Đang xử lý");
}

static int compute() {
    announce();
    return 4 * 3;
}
```

In `main`:

```java
System.out.println("Kết quả: " + compute());
```

**Answer:**

```text
Đang xử lý
Kết quả: 12
```

Because `compute()` calls the `void` method to print first, and then returns the value `12` to the print statement in `main`.

### Exercise 4: Is the Following Expression Valid?

```java
static String getStatus() {
    return "READY";
}

static void printStatus() {
    System.out.println(getStatus());
}
```

**Answer:** Valid. `getStatus()` returns the string `"READY"`, and `println(...)` receives that string to print it. `printStatus()` is `void`; it does not return a string to the caller.

### Exercise 5: Value or Reference?

```java
class Item {
    int quantity = 1;
}

static Item same(Item item) {
    return item;
}
```

Assume inside a method:

```java
Item first = new Item();
Item second = same(first);
second.quantity = 8;
System.out.println(first.quantity);
```

**Answer:** Prints `8`. `same` returns **the same reference value** rather than creating a new object; both `first` and `second` access the same `Item`.

## Key Takeaways

- **`void`:** a method that **produces no return value**; it can end naturally or use `return;` to exit early.
- **Specific return type:** uses `return expression;` with a **compatible** value, ensuring every path that can complete normally returns a result.
- **`return` differs from printing to the screen:** `return` passes a value back to the caller and terminates the method; `println` only performs an output operation.
- **Results can be used directly:** assigned to a variable, passed as an argument, or combined in an expression or condition; this cannot be done with a `void` call.
- **Side effects do not determine the return type:** a method can both modify state and return a value.
- **Reference types:** return a reference to an object rather than automatically creating a copy of the object; **`null`** is valid for reference types but not for primitives.
- When designing a method, define **the contract with the caller** first: does it only need to perform an action, or does it need a value for further processing?
