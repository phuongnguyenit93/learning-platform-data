# Static Data Types and Errors Caught at Compile Time

A program can be wrong even **before it runs**. For example, you want to store a product quantity in an integer variable, yet you assign the string `"ba"` to that variable. Java will not wait until the program hits that data at runtime: the `javac` compiler detects that the two types are incompatible.

This is a key meaning of a **static type system (static typing)**: the types of expressions and variables are determined and checked according to language rules **during compilation**. This helps eliminate many bugs early, though it does not guarantee that the program will have no runtime exceptions or always produce the right business result.

After this lesson, you will be able to recognize type errors, fix common Java compile errors yourself, choose appropriate type conversions, and anticipate situations where static type checking cannot protect you yet.

## 1. What Does Static Typing Mean?

In Java, every variable or expression has a **type**. The type tells the compiler which operations a value can participate in and which methods can be called on it.

~~~java
int quantity = 3;
long unitPriceVnd = 120_000L;
boolean available = true;
String productCode = "JAVA-01";
~~~

Meaning of each declaration:

| Component | Type | Meaning |
| --- | --- | --- |
| `quantity` | `int` | Whole number quantity within the range of `int` |
| `unitPriceVnd` | `long` | Price in whole VND, with a wider value range than `int` |
| `available` | `boolean` | Only `true` or `false` |
| `productCode` | `String` | Character string representing a product code |

Example:

~~~java
int count = 3;
count = 5;         // Valid: the new value is still int.
// count = "nam";  // Compile error: String cannot be assigned to int.
~~~

The value of `count` changes from 3 to 5, yet **the declared type of the variable does not change**. Static typing does not mean immutable values.

Do not confuse **static typing** with the **`static`** keyword. `static` is used to declare members belonging to a class; it is not the keyword that makes a language statically typed. An ordinary instance variable still undergoes static type checking.

### Important Type Categories

Java has two categories that beginners often need to distinguish:

- **Primitive:** `byte`, `short`, `int`, `long`, `float`, `double`, `char`, and `boolean`. These variables store primitive values.
- **Reference type:** for example, `String`, a user-defined class, an interface, or an array type such as `int[]`. A reference variable stores a reference to an object, or can be `null` if the context allows.

~~~java
int age = 20;          // Primitive int
String name = "An";    // Reference type String
int[] scores = {7, 8}; // Arrays are objects
~~~

`String` is not a primitive type, even though it is used very frequently. `null` is also not an empty string; calling a method through a reference variable that is currently `null` can cause a runtime error.

## 2. From Source Code to `javac` Type Checking

~~~mermaid
flowchart TD
    A[".java file"] --> B["javac: syntax and semantic analysis"]
    B --> C{"Compile errors?"}
    C -->|Yes| D["Report error and require code fix"]
    C -->|No| E["Generate .class bytecode"]
    E --> F["JVM runs the program"]
    F --> G["Result, runtime exception, or logic error"]
~~~

Some important things the compiler can check:

1. Whether statements follow Java grammar: `;`, parentheses/braces, keywords, class structure.
2. Whether a variable, class, or method name being used is declared and accessible from that location.
3. Whether expressions have types compatible with the operation, method call, assignment, and return value.
4. Whether local variables are definitely assigned before being read (*definite assignment*).
5. Whether control flow satisfies rules such as returning a value for non-`void` methods and handling checked exceptions where required.

If compilation fails, look at the error location, read the error kind, and **fix the cause in the code**. Error messages may vary slightly between JDK versions; do not rely on a single exact wording.

Remember: `javac` **does not test all possible inputs** or understand business requirements on its own. It can accept a program that computes tax with the wrong formula as long as the operations remain well-typed.

## 3. A Runnable Java Program: Using the Right Types to Model Data

Create a file named exactly **`StaticTypesDemo.java`** and copy the following code. The example uses JDK 17 or later and requires no libraries outside the JDK.

~~~java
import java.util.Locale;

public class StaticTypesDemo {
    static long calculateAmount(int quantity, long unitPriceVnd) {
        if (quantity < 0 || unitPriceVnd < 0) {
            throw new IllegalArgumentException(
                    "So luong va don gia phai khong am");
        }
        return Math.multiplyExact((long) quantity, unitPriceVnd);
    }

    static String classifyScore(int score) {
        if (score < 0 || score > 10) {
            throw new IllegalArgumentException(
                    "Diem phai tu 0 den 10");
        }
        return score >= 5 ? "Dat" : "Chua dat";
    }

    public static void main(String[] args) {
        int quantity = 3;
        long unitPriceVnd = 120_000L;
        String productCode = "JAVA-01";
        int score = 8;

        long totalVnd = calculateAmount(quantity, unitPriceVnd);
        double average = (7 + 8 + 9) / 3.0;
        boolean canBuy = score >= 5 && quantity > 0;

        System.out.println("Tong tien: " + totalVnd + " VND");
        System.out.println("Ket qua: " + classifyScore(score));
        System.out.printf(
                Locale.ROOT, "Diem TB: %.1f%n", average);
        System.out.println("Duoc mua: " + canBuy);
        System.out.println("Ma hang: " + productCode);
        System.out.println(
                "Chuyen long sang int: " + Math.toIntExact(42L));

        // Try uncommenting each line below to see javac errors:
        // quantity = "ba";
        // boolean wrong = 1;
        // int narrowed = 3.5;
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 StaticTypesDemo.java
java StaticTypesDemo
~~~

Expected output:

~~~text
Tong tien: 360000 VND
Ket qua: Dat
Diem TB: 8.0
Duoc mua: true
Ma hang: JAVA-01
Chuyen long sang int: 42
~~~

Interpreting by data:

- `quantity` has type `int` and `unitPriceVnd` has type `long`. The `calculateAmount` method declares clear inputs and returns `long`.
- `(long) quantity` converts the quantity to `long` before multiplication. `Math.multiplyExact` helps detect if the **`long` result** overflows; ordinary integer multiplication does not necessarily report overflow errors on its own.
- `classifyScore` returns `String`; both branches of the `?:` operator return strings.
- `average` has type `double`. Writing `3.0` makes the division produce a floating-point result, unlike dividing two integers.
- `canBuy` is a `boolean` built from comparison expressions and the logical operator `&&`.
- `printf(Locale.ROOT, ...)` fixes the decimal separator to `.` so the example output is easy to verify across different regional settings.

Reading the return type is a fast way to predict how a method may be used:

~~~java
long amount = StaticTypesDemo.calculateAmount(2, 20_000L);
String result = StaticTypesDemo.classifyScore(7);
// boolean result = StaticTypesDemo.classifyScore(7); // Does not compile.
~~~

The last snippet is only an illustration when placed inside another method; the invalid line has been commented out.

## 4. Data Type Errors `javac` Catches Early

Each example in the table below is intentionally written wrong. **Test only one error at a time** so multiple messages do not obscure the root cause.

| Invalid line of code | Why doesn't it compile? | How to fix |
| --- | --- | --- |
| `int count = "3";` | `String` does not implicitly convert to `int` | `Integer.parseInt("3")` when data comes from a string |
| `String label = 3;` | No automatic assignment from `int` to `String` | `String.valueOf(3)` or `"3"` |
| `boolean active = 1;` | Java does not treat the number 1 as `true` | Use `true` or a conditional expression |
| `int amount = 3.5;` | A floating-point literal cannot be implicitly narrowed to `int` | Choose `double` or round/convert intentionally |
| `char symbol = "A";` | `"A"` is a `String`, whereas `char` is a UTF-16 code unit | Use `'A'` when you want a `char` |
| `int number = 3_000_000_000;` | Un-suffixed integer literal exceeds `int` range | Use `long number = 3_000_000_000L;` |
| `unknownName++;` | No matching declaration in scope | Declare the proper name / check spelling |
| `int x = Math.toIntExact("5");` | Parameter requires `long`, not `String` | Convert the string to a number with an appropriate API first |
| `return "text";` in a method declared to return `int` | Incompatible return type | Return an `int` or change the method contract |

The error message is not always on the exact line that caused the issue. A missing brace or parenthesis earlier can make `javac` report errors many lines later. Fix the first sensible error, recompile, and then inspect again.

### Test a Real Error with a Short File

Create a separate `WrongType.java`:

~~~java
public class WrongType {
    public static void main(String[] args) {
        int quantity = "ba";
        System.out.println(quantity);
    }
}
~~~

Run:

~~~bash
javac WrongType.java
~~~

Compilation **fails** because `String` cannot be converted to `int`. There is no need to memorize every word of the error message; the key is identifying that the receiving side expects `int` while the assigned side is `String`. Fix:

~~~java
int quantity = Integer.parseInt("3");
~~~

The fixed line compiles, yet `Integer.parseInt("ba")` still throws `NumberFormatException` **at runtime**. Thus, static typing prevents assigning the wrong category of data, but does not guarantee that an input string contains a valid number.

## 5. Type Conversion: Widening, Narrowing, and Data Loss

Java allows certain **automatic widening conversions**, whereas many narrowing conversions require an explicit cast or a checked method.

~~~java
int small = 42;
long larger = small; // Valid: int -> long, preserves the value.

// int narrowed = larger; // Compile error: long -> int.
// int narrowed = (int) larger; // Compiles, but risks data loss.

int checked = Math.toIntExact(larger); // 42; throws an error if outside int range.
~~~

With an explicit cast, the compiler knows you **intentionally permit the conversion**, but it does not prove the value remains accurate. For example:

~~~java
long big = 3_000_000_000L;
int unsafe = (int) big; // Compiles, but the int value is no longer 3000000000.
// Math.toIntExact(big); // Throws ArithmeticException because it exceeds int range.
~~~

### Two Divisions That Look Almost Alike

~~~java
int a = 10;
int b = 4;

double first = a / b;          // 2.0: int division first, then converted to double.
double second = (double) a / b; // 2.5: converts a to double before dividing.
~~~

The types of the operands in the expression determine which rules the division follows. Declaring the result variable as `double` cannot bring back the fractional part already lost in integer division.

Notably, Java can allow an `int` constant expression to be assigned to `byte`, `short`, or `char` when the compiler **knows the value is within the valid range**, though that does not mean arbitrary `int` variables narrow automatically. For example:

~~~java
byte smallConstant = 100; // Valid: int constant within byte range.
int generalNumber = 100;
// byte copy = generalNumber; // Does not compile: variable value could change.
~~~

Do not insert a cast merely to “make the red error go away”. Before casting, ask about the **value range, precision, and business meaning** of the data.

## 6. Unassigned Variables and the `final` Keyword

For **local variables**, Java requires the variable to be **definitely assigned** before being read. For example:

~~~java
public class DefiniteAssignmentDemo {
    public static void main(String[] args) {
        int score;
        boolean hasExam = true;

        if (hasExam) {
            score = 8;
        }

        // System.out.println(score); // Does not compile:
        // the hasExam == false branch may leave score unassigned.

        int safeScore = hasExam ? 8 : 0;
        System.out.println(safeScore); // 8
    }
}
~~~

A field is initialized by default according to Java rules, yet that does not mean an unassigned local variable automatically gets the value 0. These are two different situations.

`final` prevents **reassigning a variable** once it has been assigned under definite assignment rules:

~~~java
final int passMark = 5;
// passMark = 6; // Does not compile: cannot reassign.

final StringBuilder text = new StringBuilder("Java");
text.append(" core"); // Valid: the object's contents can still change.
// text = new StringBuilder(); // Does not compile: reassigning a final reference.
~~~

**`final` does not automatically make an object immutable.** For reference types, it protects *the reference value stored in the variable*, not changes inside the referenced object.

## 7. Reference Variable Types and Method Call Capability

The same object can be held through variables with **different declared types**. The compiler checks a call based on the **type of the expression at the call site**, not merely the object's runtime class.

~~~java
Object value = "Hello";

// System.out.println(value.length()); // Does not compile:
// Object does not declare a length() method.

String text = (String) value;
System.out.println(text.length()); // 5
~~~

The cast lets the program compile, though it does not guarantee safety for every object:

~~~java
Object value = Integer.valueOf(42);
// String text = (String) value; // Compiles if uncommented,
// but will throw ClassCastException at runtime.
~~~

In real methods, avoid unfounded casts. If you need to check, use `instanceof` to verify that an object has a compatible type before using it:

~~~java
Object item = "Java";
if (item instanceof String) {
    String text = (String) item;
    System.out.println(text.length()); // 4
}
~~~

Polymorphism also causes **which implementation of an instance method executes** to depend on the runtime object. Compile-time type checking of the call and runtime selection of the implementation are two different layers of mechanisms, not contradictory to each other.

### Generics Help Catch Mismatched Collection Element Types

~~~java
java.util.List<String> names = new java.util.ArrayList<>();
names.add("An");
// names.add(42); // Does not compile: the list is declared to accept String.

String first = names.get(0); // Result type is checked as String.
~~~

Generics strengthen static checking, though Java uses *type erasure* for many aspects of generic execution. Using raw types, unsafe casts, or external data can cause errors to appear at runtime. Therefore, **generics are not proof that a program is immune to all type errors**.

## 8. `var` Is Still Statically Typed, Not a Dynamic Variable

Starting in Java 10, in certain local variable declarations, you can let the compiler **infer the type** from the initializer expression:

~~~java
var count = 3;         // Inferred as int.
var title = "Java";    // Inferred as String.

count = 5;             // Valid.
// count = "five";     // Does not compile: count was already inferred as int.
~~~

`var` does not mean the variable changes type across assignments. Nor can it replace explicit types everywhere:

~~~java
// var withoutValue; // Invalid: missing initializer.
// var empty = null;  // Cannot infer type from null.
// void test(var x) {} // Cannot use var as a regular method parameter type.
~~~

Use `var` when the type is already obvious and it makes the code easier to read; use explicit type names when doing so helps learners or maintainers clearly see the data contract.

## 9. Bugs That Static Typing Does Not Completely Eliminate

Compare three situations:

| Problem Type | Example | When Does Java Detect It? |
| --- | --- | --- |
| Type or syntax error | `int score = "8";` | At compile time |
| Runtime exception | `10 / zero` with `zero = 0` at runtime | When execution reaches the operation |
| Logic error | Using `>` instead of `>=` for a passing threshold | May run normally; requires testing against requirements |

Examples of snippets that **compile** yet still have issues:

~~~java
int zero = 0;
// System.out.println(10 / zero); // Throws ArithmeticException at runtime.

int[] values = {2, 4};
// System.out.println(values[2]); // Throws ArrayIndexOutOfBoundsException.

String message = null;
// System.out.println(message.length()); // Throws NullPointerException.

int tooLarge = Integer.MAX_VALUE;
tooLarge++;
System.out.println(tooLarge); // -2147483648: int overflows and wraps around.
~~~

In the last example, Java does not automatically throw an error when normal `int` increment overflows the range. When you need to detect overflow in integer addition, you can use `Math.addExact(...)` or an appropriate range-checking approach.

### Checked Exceptions Are Also Verified at Compile Time

Some APIs may declare **checked exceptions**. Java requires the caller to **catch or further declare** the checked exceptions that must be handled. For example:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

class ReadTextDemo {
    static String readText(Path path) throws IOException {
        return Files.readString(path);
    }
}
~~~

Here, the `throws IOException` signature acknowledges that the read operation can fail at runtime. The compiler checks for the presence of the **catch-or-declare** mechanism, yet cannot predict whether the file exists, read permissions are valid, or the disk encounters an error.

By contrast, common runtime errors such as `NullPointerException` are *unchecked exceptions*; Java does not force a method to write `throws NullPointerException` or force callers to catch it.

## 10. How to Read and Fix `javac` Error Messages

When you see an error message, follow this process:

1. **Locate the file and line of the error.** Read the expression on that line and a few preceding lines if needed.
2. **Identify the expected type and the actual type.** For example, the left-hand side expects `int`, while the expression on the right is `String`.
3. **Check whether the data makes sense conceptually.** Quantities should be numbers, product codes are usually strings; do not force a cast that contradicts the data's nature.
4. **Choose a safe fix:** fix the declaration, parse strings with a validating API, add an assignment, or call the right method.
5. **Recompile** after each small group of fixes, then **run and test**, because zero compile errors does not mean the requirement is met.

Some common message patterns:

| Clue | Direction to Investigate |
| --- | --- |
| `incompatible types` | Mismatched type in assignment, return, or passing an argument |
| `cannot find symbol` | Misspelled name, missing declaration, or missing import |
| `possible lossy conversion` | Narrowing conversion risking data loss |
| `variable ... might not have been initialized` | Local variable not definitely assigned |
| `method ... cannot be applied to given types` | Wrong number or types of arguments |
| `unreported exception ...` | Checked exception not caught or declared |
| `';' expected` | Possibly missing statement terminator or earlier syntax mistake |

Do not fix errors by turning everything into `String` or inserting casts everywhere. Doing so may let the program compile, yet you lose control over data and it will still fail at runtime.

## 11. Boundary Cases Worth Checking

The table below emphasizes that type checking and **valid value checking** complement each other.

| Case | Does `javac` block it? | What needs to happen? |
| --- | --- | --- |
| `int age = "20";` | Yes | Fix the type / string conversion boundary |
| `int age = -1;` | No | If age cannot be negative, validate the rule yourself |
| `Long.parseLong("abc")` | No | May throw `NumberFormatException` at runtime |
| `int x = Integer.MAX_VALUE; x++;` | No | Overflows per `int` semantics; check explicitly if disallowed |
| `long big = 3_000_000_000;` | Yes | Literal needs suffix `L` |
| `byte x = 100;` | No | Constant is within `byte` limits |
| `byte x = 200;` | Yes | Constant exceeds `byte` range |
| `Object x = "Hi"; x.length();` | Yes | Type `Object` does not declare `length()` |
| `Object x = 42; (String) x;` | Not for a type-valid cast | May throw `ClassCastException` at runtime |
| `String s = null; s.length();` | Usually no | May throw `NullPointerException` at runtime |
| `double x = 10 / 4;` | No | Result is `2.0`; change the division if `2.5` is wanted |
| `int[] a = {1}; a[1]` | No | May throw `ArrayIndexOutOfBoundsException` |

Note on the cast in the table: `(String) x` is an **expression**; in a Java program it must be placed inside a valid statement, such as `String text = (String) x;`. The intent here is to illustrate type-checking behavior, not a standalone code file.

## 12. Self-Practice Exercises and Answers

**Exercise 1 — Find the compile errors.** Read the snippet below and explain why each commented line will fail if uncommented:

~~~java
int tickets = 2;
// tickets = "two";
// boolean paid = 1;
// char grade = "A";
~~~

*Answer:* `tickets` already has type `int`, so a string cannot be assigned directly; `boolean` does not use 1 in place of `true`; `char` needs a `'A'` literal instead of the `String` `"A"`.

**Exercise 2 — Fix the division.**

~~~java
int sum = 7 + 8 + 9;
double average = sum / 3;
System.out.println(average);
~~~

*Prediction:* Prints `8.0` because integer division yields 8. To express the right intent when the sum is not evenly divisible, write `(double) sum / 3` or `sum / 3.0`. With this sum, both still yield 8.0; try `sum = 25` to see the difference (integer division gives 8, floating-point division gives around 8.333...).

**Exercise 3 — Runtime or compile error?** Given `Object anything = "Java";`, why does `anything.length()` fail to compile, while `((String) anything).length()` is valid? If the actual object is changed to `Integer.valueOf(7)`, what happens?

*Answer:* The declared type `Object` does not have `length()`; casting to `String` grants permission to call it at compile time. If the runtime object is an `Integer`, casting to `String` causes `ClassCastException`.

**Exercise 4 — Large values.** Why does `long money = 3_000_000_000;` fail to compile? Write it correctly and explain why changing only the variable's type on the left is not enough.

*Answer:* An un-suffixed literal is processed under `int` literal rules and overflows the range; use `3_000_000_000L`, where the `L` suffix indicates a `long` literal.

**Exercise 5 — Design test cases.** Write a method `static int positiveCount(String raw)` that accepts an integer string and rejects negative numbers. Distinguish the errors to handle for the three inputs `"5"`, `"-2"`, and `"abc"`.

*One possible solution:*

~~~java
static int positiveCount(String raw) {
    int count = Integer.parseInt(raw);
    if (count < 0) {
        throw new IllegalArgumentException("Khong duoc am");
    }
    return count;
}
~~~

Results: `"5"` returns 5; `"-2"` throws `IllegalArgumentException` per the rule; `"abc"` throws `NumberFormatException` during parsing (which is a subclass of `IllegalArgumentException`). Even when code is well-typed, you must **validate data** at runtime.

**Exercise 6 — Distinguish `final` and static typing.** Given `final StringBuilder sb = new StringBuilder("A");`, why does `sb.append("B")` run while `sb = new StringBuilder("C")` fails to compile?

*Answer:* `final` forbids reassigning the variable once assigned; the `StringBuilder` object remains mutable. The type of `sb` does not change in either case.

## 13. Checklist Before Submitting a Java Program

- [ ] The `.java` file and the `public` class match in name.
- [ ] Variable names are meaningful and their types match the units and value ranges.
- [ ] No accidental assignment of `String` to a numeric type or `int` to `boolean`.
- [ ] Understand widening/narrowing conversions and the risk of data loss.
- [ ] Local variables are definitely assigned before being used.
- [ ] Arguments passed match the types and count required by the method.
- [ ] No casts added just to bypass type errors; checks are used when needed.
- [ ] Input values are validated according to business rules.
- [ ] Compiled with `javac`, run with `java`, and tested on boundary cases.
- [ ] Distinguish **zero compile errors** from **zero runtime errors and correct results**.

## Key Takeaways

**Static typing is an early detection barrier**, helping Java reject many improper uses of data before execution. When the compiler reports an error, ask “what type does this expression have?” and “what type does this usage site require?”. Yet when the compiler reports no error, you still must ask “are the values valid?” and “does the algorithm satisfy the requirement?”. Understanding all three layers—**type checking, data validation, and logic verification**—is the foundation for writing reliable Java code.
