# Default Field Values and Local Variable Initialization Requirements in Java

## 1. Both Are Variables, So Why Can One Be Read Immediately While the Other Causes a Compilation Error?

Consider two Java code snippets:

```java
class Notebook {
    int pageCount;                 // Field of each Notebook.

    void printCount() {
        System.out.println(pageCount); // Valid: initially, the field has the value 0.
    }
}
```

```java
class Example {
    void printCount() {
        int pageCount;                  // Local variable.
        // System.out.println(pageCount);
        // If you remove //, the line above does not compile:
        // variable pageCount might not have been initialized
    }
}
```

Both variables are declared with type `int`. The difference is **their location and kind of variable**.

- **Fields** are declared directly inside a class body or in an appropriate type declaration. An instance field belongs to each object; a `static field` belongs to the class. Java provides **default values** for fields during the allocation/initialization process, before explicit initializations are applied.
- **Local variables** declared inside a method, constructor, or block must be **assigned a value before being read**. Java does not provide usable default values for local variables. The compiler uses the **definite assignment** rule to check control-flow paths that can reach the point where the variable is read.
- **Array elements** also have default values when an array is created; whether the local variable holding the array reference has been assigned is distinct from the array's elements being initialized.

This rule is part of the Java language and does not depend on what technique the operating system or a real-world JVM uses to "clear memory". You should not rely on garbage data or assumptions about memory layout to explain the results.

## 2. Table of Default Values for Fields and Array Elements

If no explicit assignment changes the value, Java guarantees the following default initialization values:

| Data Type | Default Value | Notes |
| --- | --- | --- |
| `byte` | `0` | Integer value 0, of type `byte`. |
| `short` | `0` | Integer value 0, of type `short`. |
| `int` | `0` | Not `null`. |
| `long` | `0L` | The printable representation of the result is `0`. |
| `float` | `0.0f` | Printed normally with `println` as `0.0`. |
| `double` | `0.0d` | Printed normally with `println` as `0.0`. |
| `char` | `'\u0000'` | NUL character, Unicode U+0000, **not** the character `'0'` or a space. |
| `boolean` | `false` | Not `0` or `null`. |
| Any reference type | `null` | Includes `String`, user-defined classes, interfaces, enums, arrays, and many other reference types. |

In the table, `0L`, `0.0f`, and `0.0d` are literal notations illustrating the exact types; the default values themselves do not need to be "written" into the program. For `char`, `'\u0000'` represents the character with value 0; printing the NUL character directly usually **does not produce a visible character** on the terminal.

This rule applies to both **instance fields** and **static fields**. For example:

```java
class Profile {
    int age;                  // Instance field -> 0
    boolean verified;         // Instance field -> false
    String displayName;       // Instance field -> null

    static long createdCount;  // Static field -> 0L
    static Profile active;     // Static field -> null
}
```

This is a compilable class declaration without its own `main` method. The `createdCount` field has only **one state belonging to the class**; each `Profile` object has its own `age`, `verified`, and `displayName`.

**A default value is not always a valid business value.** For example, `age == 0` could be an actual state or indicate an unassigned value, while `displayName == null` does not automatically mean "empty name". If the model requires a positive age and a non-empty name, the constructor or object creation method should validate and set appropriate data.

## 3. Standalone Runnable Example: Observing All Type Groups

Create the file **`FieldDefaultsDemo.java`** with the following code (Java 17 or later):

```java
class DefaultValues {
    byte byteValue;
    short shortValue;
    int intValue;
    long longValue;
    float floatValue;
    double doubleValue;
    char charValue;
    boolean booleanValue;
    String text;
    int[] numbers;

    static int staticCount;
}

public class FieldDefaultsDemo {
    public static void main(String[] args) {
        DefaultValues values = new DefaultValues();

        System.out.println("byte=" + values.byteValue);
        System.out.println("short=" + values.shortValue);
        System.out.println("int=" + values.intValue);
        System.out.println("long=" + values.longValue);
        System.out.println("float=" + values.floatValue);
        System.out.println("double=" + values.doubleValue);
        System.out.println("charCode=" + (int) values.charValue);
        System.out.println("boolean=" + values.booleanValue);
        System.out.println("text=" + values.text);
        System.out.println("numbers=" + values.numbers);
        System.out.println("staticCount=" + DefaultValues.staticCount);
    }
}
```

Compile and run in the directory containing the file:

```bash
javac FieldDefaultsDemo.java
java FieldDefaultsDemo
```

Expected output:

```text
byte=0
short=0
int=0
long=0
float=0.0
double=0.0
charCode=0
boolean=false
text=null
numbers=null
staticCount=0
```

The fields above have no explicit initializers, so the program observes their default values. `(int) values.charValue` converts the NUL character code to the number `0` for clear output. When concatenating a `String` with a `null` reference, Java produces the text representation `null` in the concatenated string; this **does not turn** the `text` or `numbers` fields into the string `"null"`.

Some important distinctions:

- `new DefaultValues()` creates a new **object** with its instance fields initialized according to Java rules.
- `DefaultValues values;` inside a method is only a declaration of an unassigned **local variable holding a reference**. You cannot read `values` before assigning a value.
- `DefaultValues.staticCount` is a static field belonging to the class; no instance is needed to read it (when access permissions allow).
- If you write `values.numbers.length` right in this example, the program can throw a `NullPointerException` because the `numbers` field is `null` and does not yet point to an array.

## 4. When Are Default Values Set?

For an object created with `new`, the main steps can be visualized as follows:

1. Java allocates the object and sets its instance fields to their default values (`0`, `false`, `null`, ...), including fields that will be reassigned in an initializer or constructor.
2. The steps to construct the parent/child object chain proceed according to Java's constructor rules.
3. Each class's **instance field initializers** such as `int count = 5;` and **instance initializer blocks** such as `{ count++; }` are executed at the appropriate time, in textual order within the class, after initializing the superclass portion.
4. The class's constructor body completes the remaining assignments and checks. When a constructor chain uses `this(...)`, the initializers of the same class are not executed again merely because of the additional delegating call.

For **static fields**, Java also has a phase that sets default values when the class undergoes *preparation*, before **static field initializers** and `static { ... }` execute during **class initialization**. Class initialization usually occurs before the first *active use*; it is not the same as merely reading or loading the class metadata.

Example of initializers overriding default values:

```java
class Configuration {
    static int port = 8080;   // Overrides 0 during class initialization.
    String host = "localhost"; // Overrides null during instance initialization.

    Configuration(String host) {
        this.host = host;      // Overrides again based on the constructor parameter.
    }
}
```

The comments describe the logical order, not that the three values can always be easily observed from normal code. **You should not intentionally read fields of a partially constructed object** to rely on their default values: doing so often creates design bugs, especially when a constructor calls an overridable method.

### The Order of Field Initializers and Instance Initializers Matters

Complete program **`InitializationValuesDemo.java`**:

```java
class Score {
    int value = 3;

    {
        value += 4;
    }

    Score() {
        value *= 2;
    }

    int getValue() {
        return value;
    }
}

public class InitializationValuesDemo {
    public static void main(String[] args) {
        Score first = new Score();
        Score second = new Score();
        System.out.println(first.getValue());
        System.out.println(second.getValue());
    }
}
```

```bash
javac InitializationValuesDemo.java
java InitializationValuesDemo
```

```text
14
14
```

Each new object initially has `value == 0`; the field initializer assigns `3`; the instance initializer adds `4` to make `7`; the constructor doubles it to `14`. That is the **final state after initialization**, no longer the default value. The two instances go through the same steps but own independent fields.

Similarly, if you declare `static int count = 3;` and then have `static { count += 4; }`, the value normally seen after class initialization is `7`. The `static` block does not run again when creating a second object.

## 5. Local Variables: Declaration Does Not Mean Initialization

A local variable is declared inside a block, method, or constructor:

```java
class LocalVariableExample {
    void calculate() {
        int quantity;              // Declaration only.
        quantity = 5;              // First assignment.
        System.out.println(quantity); // Valid because it is definitely assigned.
    }
}
```

There is no rule that automatically assigns `quantity = 0` to make a local variable readable. The compiler checks **every execution path that can reach the read** to determine whether the variable has been definitely assigned. In the method above, every path to `println` passes through `quantity = 5;`, so it is valid.

In contrast:

```java
class InvalidLocal {
    void print() {
        int quantity;
        // System.out.println(quantity); // Uncomment -> compilation error.
    }
}
```

The code shown **compiles because the erroneous line is commented out**. Uncommenting it produces an error message like `variable quantity might not have been initialized`. This is a **compile-time** error, not Java running and reading `0` or a "garbage value".

### Difference from Method and Constructor Parameters

Parameters are also variables within an execution scope, but they are **assigned from the call arguments** when the method/constructor begins, so they can be read immediately:

```java
class ParameterExample {
    void show(int count) {
        System.out.println(count); // Valid: the parameter has an argument passed in.
    }
}
```

For example, `show(0)` prints `0` because the caller passes `0`, **not because Java automatically defaults local variables**. If a reference-type parameter receives `null`, it carries a valid `null` value, but it should not be dereferenced without checking.

A variable declared in an incrementing `for` loop via an initializer (`for (int i = 0; ... )`) or an iteration variable in an enhanced `for` loop (`for (String name : names)`) also has a value at valid usage points through its corresponding mechanism; there is no "default value for all local variables".

## 6. Definite Assignment: Java Checks Based on Control Flow

To decide whether a local variable has been assigned before being read, the compiler examines the program structure, **without test-running the program** to guess inputs. Distinguish two points:

- **Being assigned on one branch** is not enough if another branch can still reach the read point without an assignment.
- **Being definitely assigned on every path that can reach the read point** is the required condition; you can use `if/else`, `switch`, or an assignment before branching to guarantee it.

### 6.1. Assigning Only Inside an `if` Branch: Not Enough

```java
class BranchProblem {
    static void show(boolean selected) {
        int price;
        if (selected) {
            price = 100;
        }

        // System.out.println(price);
        // Uncomment -> error: price might not have been assigned.
    }
}
```

The `selected == false` path skips the assignment. The compiler does not allow reading `price` after the `if`.

Fix using `else`:

```java
class BranchSolution {
    static void show(boolean selected) {
        int price;
        if (selected) {
            price = 100;
        } else {
            price = 50;
        }

        System.out.println(price); // Valid on both branches.
    }
}
```

Or set an initial value before the `if`:

```java
int price = 50;
if (selected) {
    price = 100;
}
System.out.println(price);
```

The latter snippet is only a **code fragment inside a method with a valid `selected` variable**, not a standalone program. Proactive initialization is a simple way to keep code readable when a variable has a business-meaningful default value.

### 6.2. Two Independent `if` Statements Do Not Replace `if/else` in General

```java
boolean isExpress = true;
int fee;

if (isExpress) {
    fee = 20;
}
if (!isExpress) {
    fee = 5;
}
// System.out.println(fee); // May fail the definite assignment check.
```

The two conditions are opposites to human logic, but Java does not prove arbitrary relationships between two independent `if` expressions. Use `if/else` to clearly express "definitely one of the two branches":

```java
int fee;
if (isExpress) {
    fee = 20;
} else {
    fee = 5;
}
System.out.println(fee);
```

The snippets above are **illustrative code inside a method**, without a `public` class or `main`.

### 6.3. A Loop Might Not Execute

```java
class LoopProblem {
    static void printFirst(boolean available) {
        int first;

        while (available) {
            first = 1;
            break;
        }

        // System.out.println(first);
        // Uncomment -> error: available could be false from the start.
    }
}
```

Even though there is an assignment inside the loop, the compiler must account for the case where the loop runs **0 times**. Fix this by initializing before the loop or structuring the control flow so there is a definite assignment on the path to the read point.

`do/while` guarantees that the loop body begins executing at least once, yet every branch inside such as `break`, `continue`, exceptions, or conditional assignments must still be considered when proving definite assignment. You should not replace `while` with `do/while` just to "trick" the compiler.

### 6.4. `switch`: All Exit Paths Must Be Covered

Valid Java 17 pattern inside a method:

```java
static String category(int code) {
    String result;

    switch (code) {
        case 1 -> result = "Basic";
        case 2 -> result = "Advanced";
        default -> result = "Unknown";
    }

    return result;
}
```

Every branch assigns `result`; `default` handles all remaining values, so `return result` is valid. If you remove `default` in this `switch statement`, the compiler cannot guarantee that every value of `code` leads to an assignment.

A shorter and clearer alternative is a **switch expression**:

```java
static String category(int code) {
    return switch (code) {
        case 1 -> "Basic";
        case 2 -> "Advanced";
        default -> "Unknown";
    };
}
```

In the latter example, `switch` directly produces a return value. Both snippets are **methods to place inside a class**, without a separate `main`.

### 6.5. Operations on a Variable Also Count as Reads

```java
int count;
// count++;         // Error: needs to read count before incrementing.
// count += 2;      // Error: needs to read the old value before adding.
// System.out.println(count); // Error: read before assignment.
count = 0;
count++;
System.out.println(count); // Valid: prints 1.
```

`count++` and `count += 2` both use the variable's current value. A simple assignment like `count = 0` is a write and does not require a prior read. The erroneous lines are commented out so that the remaining snippet is valid when placed inside a method.

## 7. Complete Example of Definite Assignment with Multiple Branches

Create the file **`LocalAssignmentDemo.java`**:

```java
public class LocalAssignmentDemo {
    static String shipping(boolean express, int distance) {
        String label;
        int fee;

        if (express) {
            label = "Express";
            fee = 20;
        } else {
            label = "Standard";
            fee = 5;
        }

        int surcharge;
        if (distance > 100) {
            surcharge = 7;
        } else {
            surcharge = 0;
        }

        return label + ": " + (fee + surcharge);
    }

    public static void main(String[] args) {
        System.out.println(shipping(true, 120));
        System.out.println(shipping(false, 20));

        int quantity;
        quantity = 4;
        quantity += 1;
        System.out.println("quantity=" + quantity);
    }
}
```

Compile and run:

```bash
javac LocalAssignmentDemo.java
java LocalAssignmentDemo
```

Exact output:

```text
Express: 27
Standard: 5
quantity=5
```

At the `return` statement, the variables `label`, `fee`, and `surcharge` are all definitely assigned on every control-flow path reaching `return`. Calling the method with `true, 120` selects fee `20` plus surcharge `7`; with `false, 20`, it selects fee `5` plus `0`. The variable `quantity` is assigned `4` before executing `quantity += 1`.

**Takeaway:** Not assigning immediately on the declaration line can still be valid; Java's requirement is **not to read a variable before the compiler proves an assignment has occurred**.

## 8. `final` Fields and `final` Local Variables: Same Single-Assignment Immutability, Different Initial Mechanics

The `final` keyword restricts **variable reassignment**, but it does not change the default principles between fields and locals.

### 8.1. Blank Final Instance Field

```java
class Member {
    private final String id; // Blank final field: no explicit initializer yet.

    Member(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id is required");
        }
        this.id = id;
    }

    String getId() {
        return id;
    }
}
```

`id` still has the default reference value during allocation, but **the source code must guarantee definite assignment of the blank final field** according to Java rules before the constructor completes normally. You cannot rely on the default `null` to skip assigning a required `final` field. If another constructor is added, that constructor must also ensure `id` is validly assigned, usually via `this(...)`.

A blank final instance field can also be assigned in an instance initializer; however, it must follow the definite assignment rules and must not be reassigned in the constructor. Prefer initializing at the declaration site or in the constructor when doing so makes the state easier to understand.

### 8.2. Blank Final Static Field

```java
class AppInfo {
    static final String VERSION;

    static {
        VERSION = "1.0";
    }
}
```

`VERSION` does not have an initialization expression on the field declaration line, yet it is assigned once in the static initializer. The compiler requires a blank final static field to be definitely assigned according to static initialization rules. Afterward, `AppInfo.VERSION` cannot be reassigned.

### 8.3. `final` Local Variables

```java
class FinalLocal {
    static int choose(boolean high) {
        final int limit;
        if (high) {
            limit = 100;
        } else {
            limit = 10;
        }
        return limit;
    }
}
```

Every path to `return` assigns `limit` **exactly once**, so the code is valid. Adding `limit = 20;` after `if/else` causes an error because the `final` variable has already been definitely assigned; Java does not allow reassignment.

A **non-`final`** local variable can be assigned multiple times, as long as it is assigned before being read. In a lambda or local/anonymous class, Java requires captured local variables to be `final` or *effectively final* (not reassigned after initial assignment according to the rules). This is why certain local variables cannot be modified after being used in a lambda, whereas instance fields can be modified according to access rules.

`final` on a **reference variable** only prohibits assigning it to another reference; it does not automatically make the contents of the pointed-to object immutable.

## 9. Arrays: Local Reference Variables and Array Elements Are Two Different Things

Creating an array with `new int[3]` allocates an array object and assigns the default value `0` to **each element**. For `String[]`, each element is initially `null`. This happens regardless of whether the variable holding the array reference is a local variable or a field.

```java
import java.util.Arrays;

public class ArrayDefaultsDemo {
    public static void main(String[] args) {
        int[] scores = new int[3];
        String[] labels = new String[2];
        boolean[] flags = new boolean[2];

        System.out.println(Arrays.toString(scores));
        System.out.println(Arrays.toString(labels));
        System.out.println(Arrays.toString(flags));
    }
}
```

Save as **`ArrayDefaultsDemo.java`**:

```bash
javac ArrayDefaultsDemo.java
java ArrayDefaultsDemo
```

```text
[0, 0, 0]
[null, null]
[false, false]
```

Here, the local variables `scores`, `labels`, and `flags` **have all been assigned using `new ...` expressions** at declaration time. The elements inside the arrays are given default values automatically by Java.

In contrast:

```java
class ArrayLocalProblem {
    static void example() {
        int[] scores;
        // System.out.println(scores[0]);
        // If uncommented: compilation error because the local variable scores has not been assigned.
    }
}
```

After assigning `scores = new int[3];`, you can read `scores[0]` as `0`. If instead you write `scores = null;`, the local variable is assigned (satisfying definite assignment), but reading `scores[0]` at runtime will throw a `NullPointerException`. **Definite assignment does not prove that a reference is non-`null`.**

Another easily confused example:

```java
class ArrayHolder {
    int[] values; // Reference field has default value null.
}

class UseArrayHolder {
    static void check() {
        ArrayHolder holder = new ArrayHolder();
        System.out.println(holder.values == null); // true
    }
}
```

The `values` field is `null`, meaning **no array exists yet** for this field. Only after executing `holder.values = new int[3];` do array elements with the value `0` exist.

## 10. Hiding a Field Name with a Local Variable (*Shadowing*)

You can declare a local variable or parameter with the same name as a field:

```java
class Player {
    private int score;     // Field: defaults to 0.

    void show() {
        int score = 10;    // Local variable: has a value from assigning 10.
        System.out.println(score);
        System.out.println(this.score);
    }
}
```

Inside `show()`, the simple name `score` refers to the local variable due to name resolution rules; `this.score` refers to the object's field. If you call `new Player().show()`, the two output lines are `10` and `0`, respectively. The example is a valid class declaration; to run it, place it in a program with a `main` method.

Having a field with a default value **does not rescue** an uninitialized local variable with the same name:

```java
class ShadowProblem {
    int count;

    void print() {
        int count;
        // System.out.println(count);      // Error: reading unassigned local count.
        System.out.println(this.count);    // Valid: reading field -> 0.
    }
}
```

The compiler treats `count` without `this` as the **local variable**, whereas `this.count` is the instance field. This rule explains many cases where beginners wonder, "I already have an int field, so why does Java still report it as uninitialized?"

In practice, you should avoid confusing name shadowing. The case where a constructor parameter has the same name as a field is very common and clear when using `this`:

```java
class Person {
    private String name;

    Person(String name) {
        this.name = name;
    }
}
```

`name` on the right-hand side is the parameter already assigned when the constructor call begins; `this.name` on the left-hand side is the field.

## 11. Combined Runnable Example: Default Fields, Blank Final Fields, and Definitely Assigned Locals

Create the file **`AssignmentRulesDemo.java`**:

```java
class Enrollment {
    static final String CATEGORY;
    static int totalCreated;

    static {
        CATEGORY = "course";
    }

    final int id;
    int attempts;
    String nickname;
    boolean confirmed;

    Enrollment(boolean vip) {
        if (vip) {
            id = 9;
        } else {
            id = 4;
        }
        totalCreated++;
    }
}

public class AssignmentRulesDemo {
    public static void main(String[] args) {
        Enrollment first = new Enrollment(true);

        int selected;
        if (first.id > 5) {
            selected = 100;
        } else {
            selected = 200;
        }

        int[] slots = new int[2];

        System.out.println("attempts=" + first.attempts);
        System.out.println("nickname=" + first.nickname);
        System.out.println("confirmed=" + first.confirmed);
        System.out.println("id=" + first.id);
        System.out.println("selected=" + selected);
        System.out.println("category=" + Enrollment.CATEGORY);
        System.out.println("created=" + Enrollment.totalCreated);
        System.out.println("slot0=" + slots[0]);
    }
}
```

Run with JDK 17+:

```bash
javac AssignmentRulesDemo.java
java AssignmentRulesDemo
```

```text
attempts=0
nickname=null
confirmed=false
id=9
selected=100
category=course
created=1
slot0=0
```

Explanation of each group:

1. `attempts`, `nickname`, and `confirmed` are instance fields with no declared initializer and no assignment in the constructor. Their default values are `0`, `null`, and `false`, respectively.
2. `id` is a **blank final instance field**. Both `if/else` branches in the constructor ensure it is assigned exactly once: the `vip == true` case yields `id == 9`.
3. `CATEGORY` is a **blank final static field** assigned in a static initializer; this is class initialization, not a final default value of `null`.
4. `totalCreated` is a static field defaulting to `0`, which the constructor then increments to `1`. Since only one `Enrollment` is created, the line is `created=1`.
5. `selected` is a local variable that is only declared before the `if`. Both branches assign it, so printing `selected=100` is valid.
6. `slots` is a local variable **that has been assigned** a reference from `new int[2]`, whereas `slots[0]` is an array element automatically initialized to `0`.

## 12. Misconceptions Related to the Compiler and Runtime

### 12.1. "Java Automatically Assigns 0 to All `int` Variables"

False. Java guarantees `0` for `int` **fields** and `int` **array elements**. A local `int number;` does not automatically have a readable value; the compiler requires definite assignment before reading it.

### 12.2. "The Compiler Knows the Condition Is Always True Because I Know the Data in Advance"

Definite assignment analysis follows specific rules; the compiler does not deduce full business semantics or all arithmetic conditions. Structure your code clearly with `if/else`, an initial assignment, or a `switch` covering all branches. Avoid relying on non-obvious deductions that make code hard to read.

### 12.3. "Having Default Values Means the Object Is Already in a Valid State"

Not necessarily. `String email == null` or `int age == 0` may violate the model's invariants. If an email or a positive age is required, accept parameters and validate them in the constructor. Default values are a technical guarantee about initial state, not a substitute for business constraints.

### 12.4. "A Local Variable Assigned `null` Is Safe"

False. Definite assignment only checks that **the variable has been assigned**; it does not guarantee that an object exists. `String s = null;` satisfies definite assignment, yet `s.length()` still throws a `NullPointerException` at runtime.

### 12.5. "A `final` Field Does Not Need Initialization Because It Already Has a Default"

False. A blank final field is subject to strict definite assignment checks: it must be assigned according to the rules before the constructor or class initialization completes normally. The default value during allocation does not replace the source code's responsibility to initialize it.

### 12.6. "Having an Array Means Every Reference Element Already Has an Object"

False. `new Customer[3]` creates **one array object** with three `null` elements; it does not invoke the `Customer` constructor. To use `customers[0].getName()`, you must first assign a `Customer` instance to element 0.

### 12.7. "Reading Another Field from an Initializer Always Sees Its Final Value"

Not always true. Fields initially receive default values; explicit initializers run in the order they are defined. For example, methods called from an initializer may read an incomplete state, causing unpredictable bugs. Avoid overusing side effects and circular dependencies inside initializers.

### 12.8. "A `static` Variable Is Always a Constant"

`static` means the field belongs to the class; it can still be modified unless otherwise constrained. `final` prohibits reassigning the field after proper initialization, though `final` on a reference itself does not make the referenced object immutable.

## 13. Checklist for Diagnosing "variable might not have been initialized"

When the compiler reports an error on a variable, check in order:

1. **Identify what kind of variable is actually being read.** Is it a local variable, parameter, field, or array element? Is a local name shadowing a field?
2. **Find the first read.** `println(x)`, `x++`, `x += 1`, `someMethod(x)`, or `return x` all use the value of `x`.
3. **List the branches that can reach the read point.** Is there an `if` without an `else`, an incomplete `switch`, a loop that might not execute, or a `break` or `return` that alters the path?
4. **Ensure an assignment occurs before every path reaching the read.** Use an explicit initializer when there is a meaningful default value; use `if/else` or `switch` if each branch needs a different value.
5. **If the variable is `final`, also check for reassignment.** A final local variable must be assigned exactly once on the corresponding path; blank final fields must be initialized according to their own rules.
6. **Distinguish compile errors from runtime exceptions.** A local variable that is not definitely assigned causes a compile error; a reference assigned `null` whose method is invoked causes a runtime error.

Brief fix example:

```java
// Before: may cause a compilation error if shippingFee is read outside the if.
int shippingFee;
// if (express) shippingFee = 20;
// System.out.println(shippingFee);

// After: every branch assigns a value.
if (express) {
    shippingFee = 20;
} else {
    shippingFee = 5;
}
System.out.println(shippingFee);
```

This snippet is placed inside a method that already has a `boolean` variable `express`; the original erroneous lines are commented out. The fix expresses **the meaning of each branch** without using an arbitrary assignment to hide the error.

## 14. Self-Check and Practice

**Question 1.** A class declares `boolean enabled;`, `char symbol;`, and `String title;` without assigning anything. What values do the three fields have immediately after the object is initialized and not yet modified?

**Answer:** `false`, the character U+0000 (NUL), and `null`. The U+0000 character is not `'0'`.

**Question 2.** Why does the following snippet not compile?

```java
void test(boolean condition) {
    int value;
    if (condition) {
        value = 7;
    }
    // System.out.println(value);
}
```

**Answer:** If you uncomment the `println` line, there is an execution path with `condition == false` where `value` is not assigned. Fix it with an `else` branch or by assigning an initial value before the `if`.

**Question 3.** Is `int[] values = new int[2];` inside a method valid for printing `values[1]` immediately after the declaration? If so, what is the result?

**Answer:** Valid. The local variable `values` has been assigned an array reference; the second element is default-initialized to `0`.

**Question 4.** With `String text = null;` inside a method, does the compiler block `text.length()` for being unassigned?

**Answer:** No: `text` has been assigned. The `text.length()` call will fail at runtime with a `NullPointerException` if executed.

**Question 5.** Can a `final int id;` field simply keep its default value `0` without an explicit assignment in a constructor or initializer?

**Answer:** No. A blank final field must be definitely assigned during the appropriate initialization process; the default `0` in memory does not replace that compile-time obligation.

**Question 6.** If a method declares `int x;` and only assigns `x = 4;` after the statement `x++;`, what is wrong?

**Answer:** `x++` reads the old value of `x` before incrementing; at that point, `x` is not definitely assigned. You must assign it before `x++`.

**Question 7.** A field is `int level = 5;` and a subsequent instance initializer is `{ level += 2; }`. If the constructor does not modify `level`, what is its value after initialization?

**Answer:** `7`. The field has `0` during the default phase, then is assigned `5`, and then is incremented by `2`.

**Question 8.** In `AssignmentRulesDemo`, if you change `new Enrollment(true)` to `new Enrollment(false)`, which lines change?

**Answer:** `id=9` becomes `id=4`; `selected=100` becomes `selected=200`. The default values of the other fields, the category, the object creation count, and the array element value remain the same.

---

**Remember:** Java assigns default values to **instance fields**, **static fields**, and **array elements**; **local variables** must be definitely assigned before being read. Assigning `null` is still a valid assignment, but it does not guarantee safety when accessing the object. For `final`, ensure that variables/fields are initialized according to the rules and not reassigned. When a program has branches and loops, inspect every path to the point where a variable is read to distinguish compile-time errors from runtime data states.
