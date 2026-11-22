# `final` on Variables: Assign Only Once in Java

In Java, the **`final`** keyword placed on a **variable** restricts the ability to **assign a value to that variable**. Once a `final` variable has been assigned a value according to the initialization rules, another value cannot be reassigned to **that same variable**.

Example:

```java
final int MAX_RETRIES = 3;
// MAX_RETRIES = 5;  // Compilation error: final variable has already been assigned.
```

For reference types:

```java
final StringBuilder message = new StringBuilder("Java");
message.append(" 17");            // Valid: modifies the StringBuilder object.
// message = new StringBuilder(); // Error: reassigning the message variable.
```

**Key point to remember from the start:** `final` on a variable prevents **reassignment of the variable**; it does not automatically make **the object that the reference points to** immutable. A `final` variable may reference a mutable object, and fields/elements inside the object can still change through allowed APIs.

This article focuses on the **"assign only once"** meaning of `final` for **local variables, method/constructor parameters, instance fields, and static fields**; how the compiler checks definite assignment, scenarios with conditional branches/loops, object references, lambdas, and common errors in Java 17+.

## 1. Understanding Three Terms Correctly: Variable, Assignment, and Value

Consider:

```java
int number = 10;
```

- `number` is a **variable** of type `int`.
- `10` is the **initial value**.
- `=` in the declaration performs **initialization**, meaning it puts the initial value into the variable.

If we later write:

```java
number = 20;
```

this is **assignment/reassignment**: the `number` variable receives a new value. For a regular variable, this is valid if the assignment satisfies type compatibility and other rules.

However:

```java
final int number = 10;
// number = 20; // Invalid.
```

The `number` variable has already been initialized. `final` causes the compiler to reject another value assignment to it.

### What Does "Assign Only Once" Mean?

The phrasing above is a helpful intuition, but more precisely:

> A `final` variable is only allowed to **receive a value through initialization/assignment along the control paths permitted by Java**, and cannot be **reassigned** afterward.

A special case is a **blank final**: it can be declared first and assigned a value later, provided that the *definite assignment* and *definite unassignment* rules required by Java are satisfied.

Therefore, `final` **does not require** every local variable declaration to write an initializer on the same line.

## 2. Initialized `final` Local Variables: Cannot Be Reassigned

This is the simplest case.

```java
void process() {
    final int limit = 100;
    System.out.println(limit);

    // limit = 200; // Compilation error.
}
```

`limit` is a local variable and is assigned at declaration. It cannot receive a second value.

Even if the new assignment has the **same value** as the original one, the compiler does not allow it either:

```java
final int value = 7;
// value = 7; // Still an error.
```

**`final` does not check whether the value changes.** It restricts **assignment to the variable**. A second assignment is prohibited even when the right-hand side equals the first right-hand side.

### Update Operators Are Also Assignments

The following statements are **invalid** for an initialized `final` local variable:

```java
final int count = 1;

// count++;      // Error.
// ++count;      // Error.
// count += 2;   // Error.
// count *= 3;   // Error.
// count = 1;    // Error.
```

Because `++`, `--`, and compound assignments such as `+=` all update **the `count` variable itself**, they are also restricted by `final`.

Conversely, simply **reading** the variable is valid:

```java
final int count = 3;
int doubled = count * 2;
System.out.println(doubled); // 6
```

## 3. Java 17 Program: Local `final`

Save the entire code as **`FinalLocalDemo.java`**:

```java
public class FinalLocalDemo {
    public static void main(String[] args) {
        final int base = 10;
        final int multiplier = 3;
        int result = base * multiplier;

        System.out.println("base = " + base);
        System.out.println("multiplier = " + multiplier);
        System.out.println("result = " + result);

        result += 5; // result is not final.
        System.out.println("result mới = " + result);

        // base = 20;       // INVALID: base is final.
        // multiplier++;    // INVALID: multiplier is final.
    }
}
```

Run with JDK 17 or later:

```bash
javac -encoding UTF-8 FinalLocalDemo.java
java FinalLocalDemo
```

**Exact stdout:**

```text
base = 10
multiplier = 3
result = 30
result mới = 35
```

Explanation: `base` and `multiplier` are not reassigned, whereas `result` is a regular variable so `result += 5` is valid. Using a `final` variable in a calculation expression does not cause **the variables receiving the result** to automatically become `final` as well.

## 4. Blank Final Local Variable: Declare First, Assign Later

A **blank final variable** is a `final` variable declared **without an initializer** at its declaration site.

Example:

```java
final int value;
value = 42;
System.out.println(value); // 42

// value = 50; // Error: second assignment.
```

Steps:

1. Declare `final int value;`.
2. The compiler does not yet consider `value` to have a value that can be read.
3. The line `value = 42;` is a valid initializing assignment.
4. From then on, no further value may be assigned to `value`.

### Cannot Be Read Before Assignment

```java
final int value;
// System.out.println(value); // INVALID: might not have been initialized.
value = 42;
```

The compiler uses control-flow analysis to ensure a local variable is **definitely assigned** before being read. Java does not automatically supply a default value of `0` for **uninitialized local variables** as it does for instance fields.

A blank final variable **is not allowed to be assigned simply because it has "not been used yet"** if the compiler has already determined earlier that it has a value. What is evaluated is the possibility of assignment along valid execution paths.

## 5. `final` with `if`/`else`: Choosing a Value Once

A practical scenario is wanting a `final` variable to receive one of two results depending on a condition:

```java
final String environment;

if (production) {
    environment = "PROD";
} else {
    environment = "DEV";
}

System.out.println(environment);
```

Although the source code contains **two assignment lines**, in each normal run only **one branch** is executed, so each valid control path assigns the `environment` variable only once.

**Important point:** "assign only once" does **not** mean that across the entire Java file there can appear only **one assignment statement** to the final variable. The compiler analyzes control branches and definite assignment conditions.

### Complete Example

Save **`FinalBranchDemo.java`**:

```java
public class FinalBranchDemo {
    static String mode(boolean production) {
        final String environment;

        if (production) {
            environment = "PROD";
        } else {
            environment = "DEV";
        }

        return environment;
    }

    public static void main(String[] args) {
        System.out.println(mode(true));
        System.out.println(mode(false));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 FinalBranchDemo.java
java FinalBranchDemo
```

Stdout:

```text
PROD
DEV
```

Explanation:
- `mode(true)` enters the first branch and assigns `environment = "PROD"`.
- `mode(false)` enters the `else` branch and assigns `environment = "DEV"`.
- In each call to `mode`, the parameter and local variable belong to **that separate invocation**; two calls do not "assign twice" to a single shared variable.

### What If a Branch Is Missing?

```java
final String mode;
if (production) {
    mode = "PROD";
}

// System.out.println(mode); // INVALID: production might be false.
```

If `production` is false, `mode` has not been assigned. Therefore, Java does not allow reading it at a point where the variable might be uninitialized.

Fixes can include adding an `else`, using an expression that has a value in all cases, or designing an appropriate `return`/`throw` path.

## 6. Using the Conditional Operator When Choosing the Final Value

If only one conditional value is needed, you can initialize it directly:

```java
final String label = enabled ? "ON" : "OFF";
```

`label` is assigned exactly once when evaluating the expression.

Compare:

```java
final int port;
if (testMode) {
    port = 8081;
} else {
    port = 8080;
}
```

and:

```java
final int port = testMode ? 8081 : 8080;
```

Both can be valid and have the same meaning if `testMode` has no relevant side effects. The conditional operator version is usually shorter, while `if`/`else` is clearer when determining the value is complex.

**`port` must not be assigned again** after the result has been determined.

## 7. `final` and `switch`: Ensuring Every Valid Path Has a Value

In Java 17, a **switch expression** can return a result to initialize a final variable:

```java
final int severity = switch (level) {
    case "LOW" -> 1;
    case "MEDIUM" -> 2;
    case "HIGH" -> 3;
    default -> 0;
};
```

`switch` here is an **expression**: it yields a final value, not a call that updates the variable multiple times.

### Runnable Example

Save **`FinalSwitchDemo.java`**:

```java
public class FinalSwitchDemo {
    static int priority(String level) {
        final int result = switch (level) {
            case "LOW" -> 1;
            case "MEDIUM" -> 2;
            case "HIGH" -> 3;
            default -> 0;
        };
        return result;
    }

    public static void main(String[] args) {
        System.out.println(priority("LOW"));
        System.out.println(priority("HIGH"));
        System.out.println(priority("UNKNOWN"));
    }
}
```

```bash
javac -encoding UTF-8 FinalSwitchDemo.java
java FinalSwitchDemo
```

Stdout:

```text
1
3
0
```

Note: a `switch` on a null `String` reference does not automatically fall into `default` under standard Java 17 rules; `null` must be handled separately if it is a valid input of the API.

## 8. `final` in Loops: Distinguishing a Fixed Variable from a New Variable Each Iteration

`final` often causes an error when applied to a **loop control variable** that needs to be incremented/decremented:

```java
// INVALID:
// for (final int i = 0; i < 3; i++) {
//     System.out.println(i);
// }
```

Because `i++` is an assignment to `i`, the compiler rejects it if `i` is declared `final` and initialized to `0`.

### `final` Variable Declared Inside the Loop Body

```java
for (int i = 0; i < 3; i++) {
    final int squared = i * i;
    System.out.println(squared);
}
```

This is valid code. Each iteration of the loop body initializes a **local variable for that respective block execution**. There is no second assignment to the `squared` variable itself after it is initialized in that iteration.

### Enhanced for with a `final` Loop Variable

```java
int[] values = {2, 4, 6};

for (final int value : values) {
    System.out.println(value);
    // value++; // INVALID: cannot reassign a final variable.
}
```

The enhanced `for` allows declaring the iteration element as `final`. Each iteration receives the element value according to the loop's mechanism; the program cannot reassign the `value` variable itself inside the loop body.

### Runnable Example

Save **`FinalLoopDemo.java`**:

```java
public class FinalLoopDemo {
    public static void main(String[] args) {
        for (int i = 0; i < 3; i++) {
            final int square = i * i;
            System.out.println("square = " + square);
        }

        int sum = 0;
        for (final int value : new int[]{2, 4, 6}) {
            sum += value;
        }
        System.out.println("sum = " + sum);
    }
}
```

```bash
javac -encoding UTF-8 FinalLoopDemo.java
java FinalLoopDemo
```

Stdout:

```text
square = 0
square = 1
square = 4
sum = 12
```

**Tip:** if a loop needs a counter variable to be updated, **do not mark that counter variable `final`**. However, a read-only variable derived from the counter in each iteration can very reasonably be `final`.

## 9. `final` on Primitive Variables: Locks the Variable's Value, Not All Calculations

Primitive types such as `int`, `long`, `double`, `boolean`, and `char` store their values directly according to Java's type model.

```java
final int width = 4;
final int height = 5;

int area = width * height;
area += 10;
```

- `width` and `height` cannot be reassigned.
- `area` is allowed to change because it is not declared `final`.
- The expression `width * height` computes a value; it **does not update `width` or `height`**.

A final declaration can also be used for a primitive boolean:

```java
final boolean active = true;
// active = false; // INVALID.
```

It can also be used with a local variable whose type is a reference to a boxed primitive:

```java
final Integer count = 7;
// count = 8; // INVALID: reassigning the count reference.
```

Because `Integer` is an immutable value object, a caller cannot mutate that integer's contents via a setter. However, the reason **`count = 8` is not allowed** is still the constraint of the `final` variable.

## 10. `final` on References: Does Not Mean an Immutable Object

This is the most common misconception.

```java
final StringBuilder builder = new StringBuilder("Java");
builder.append(" Core");     // Valid.
// builder = new StringBuilder("Other"); // Error.
```

`builder` keeps the initialized reference unchanged. However, the `StringBuilder` object can change its contents through `append`.

### `final` Array Example

```java
final int[] numbers = {1, 2, 3};
numbers[0] = 9;               // Valid: updates an array element.
// numbers = new int[]{4, 5}; // INVALID: reassigning the numbers variable.
```

Arrays **are mutable objects**. `final` on the `numbers` variable does **not** make each array element final.

### `final` Collection Example

```java
final java.util.List<String> names =
        new java.util.ArrayList<>();

names.add("An");       // Valid.
names.add("Bình");     // Valid.
// names = new ArrayList<>(); // INVALID: reassigning the names variable.
```

The `names` variable cannot be assigned to another list, but the referenced `ArrayList` object can be modified if the API allows it.

### Two Questions That Must Be Kept Separate

1. **Can the reference be changed to another object?** `final` on the variable answers **no**, once initialized.
2. **Can the object change its state?** That depends on **the object type, fields, methods, and design contract**. `final` on the variable does not determine that.

## 11. Complete Program: `final` with Arrays, Lists, and Builders

Save **`FinalReferenceDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class FinalReferenceDemo {
    public static void main(String[] args) {
        final int[] values = {1, 2};
        final List<String> names = new ArrayList<>();
        final StringBuilder text = new StringBuilder("Java");

        values[0] = 10;
        names.add("An");
        names.add("Bình");
        text.append(" 17");

        System.out.println(Arrays.toString(values));
        System.out.println(names);
        System.out.println(text);

        // values = new int[]{3, 4};             // INVALID
        // names = new ArrayList<>();            // INVALID
        // text = new StringBuilder("Other");    // INVALID
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 FinalReferenceDemo.java
java FinalReferenceDemo
```

**Stdout:**

```text
[10, 2]
[An, Bình]
Java 17
```

This is empirical proof that `final` **is not deep immutability**.

### An Immutable Object Can Be Referenced by a Non-Final Variable

```java
String message = "Java";
message = message + " 17";
```

A `String` object is considered immutable; string concatenation does not modify the contents of the old object, but instead creates/obtains a resulting string. However, the `message` variable **is not final**, so it can be assigned the resulting reference.

If we write:

```java
final String message = "Java";
// message = message + " 17"; // INVALID: reassigning a final variable.
```

then the compiler rejects it—not because `String` needs to be "unlocked", but because **assignment to the `message` variable is locked**.

## 12. Aliasing: Another Variable Can Still Modify a `final` Variable's Object

Suppose:

```java
final StringBuilder first = new StringBuilder("A");
StringBuilder alias = first;

alias.append("B");
System.out.println(first); // AB
```

`first` and `alias` both reference **the same `StringBuilder` object**. `final` only applies to **the `first` variable**; it does not restrict the `alias` variable and does not automatically make the shared object immutable.

Diagram:

```text
first (final) ──────┐
                    ├──> StringBuilder { "AB" }
alias (normal) ─────┘
```

If:

```java
alias = new StringBuilder("C");
```

then `alias` switches to the new object; `first` still keeps the old object `"AB"`. There is no behavior where "final keeps all other variables always pointing to the same object".

### `final` Does Not Protect Shared Contents

A `final List<String>` can still be modified by code holding an alias to the same `ArrayList`:

```java
List<String> source = new ArrayList<>();
final List<String> stored = source;
source.add("A");
```

`stored` still points to the list that now contains the element `"A"`. If you want to **encapsulate** data, you need strategies such as defensive copying, immutable collections, and controlling mutable elements, rather than merely attaching `final` to the reference.

## 13. `final` on Method Parameters

A parameter can be declared as `final`:

```java
static void greet(final String name) {
    System.out.println("Xin chào " + name);
    // name = "Khác"; // INVALID: cannot reassign the parameter.
}
```

A formal parameter is initialized when calling the method from **the argument value**. Even if the caller has a non-final variable, the copy of the value passed into the final parameter cannot be reassigned inside the method body.

`final` on a parameter is a way to express the intent "do not use the parameter variable as a place to store another value". It does **not** change Java's argument-passing mechanism: it is still always **pass-by-value**.

### A final Reference Parameter Still Allows Mutation

```java
static void addItem(final List<String> items) {
    items.add("Java"); // Valid if the list is mutable.
    // items = new ArrayList<>(); // INVALID.
}
```

This snippet can modify the list that the caller also holds. That **does not prove Java passes variables by reference**; the method receives a copy of **the reference value** pointing to the same object.

### Runnable Program

Save **`FinalParameterDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class FinalParameterDemo {
    static void increase(final int number) {
        System.out.println("Trong method: " + (number + 1));
        // number++; // INVALID: final parameter.
    }

    static void add(final List<String> values) {
        values.add("Java");
        // values = new ArrayList<>(); // INVALID.
    }

    public static void main(String[] args) {
        int original = 5;
        increase(original);
        System.out.println("Ở main: " + original);

        List<String> list = new ArrayList<>();
        add(list);
        System.out.println(list);
    }
}
```

```bash
javac -encoding UTF-8 FinalParameterDemo.java
java FinalParameterDemo
```

Stdout:

```text
Trong method: 6
Ở main: 5
[Java]
```

`increase` only computes a new value and prints it without modifying the parameter. `add` modifies the shared list object. Both follow pass-by-value, regardless of whether the parameter has `final`.

## 14. `final` on Constructor Parameters

Constructors can also use `final` parameters:

```java
class Person {
    private final String name;

    Person(final String name) {
        this.name = name;
        // name = "Other"; // INVALID: final parameter.
    }
}
```

Distinguish:
- `name` on the right is the constructor's **final parameter**.
- `this.name` on the left is the **final instance field**.
- `this.name = name;` assigns **the parameter's value** to **the object's field**, **not** reassigning the `name` parameter.

The two components are two different variables, even though they share the same name. `final` on the parameter does not automatically make the field final, and `final` on the field does not automatically make the parameter final.

Example:

```java
class Product {
    private String label;

    Product(final String label) {
        this.label = label;
    }

    void rename(String newLabel) {
        this.label = newLabel; // Field is not final.
    }
}
```

Here, the final `label` parameter only forbids reassigning **the parameter during construction**. The `this.label` field is still non-final, so it can be changed later according to the API.

## 15. `final` Variables and `final` Instance Fields: Same Principle, Different Initialization Site

For a `final` **local variable**, the compiler checks the assign-once guarantee within the block/method call scope. For a `final` **instance field**, every object initialization path that completes normally must assign the field properly according to constructor/initializer rules.

~~~java
class Ticket {
    private final String id;

    Ticket(String id) {
        this.id = java.util.Objects.requireNonNull(id);
    }
}
~~~

`new Ticket("A")` and `new Ticket("B")` create two instances with independent `id` values. This connects to the article **Final Fields and the Requirement to Assign Values on Every Initialization Branch**; the detailed analysis of constructor paths/definite assignment belongs to that article.

## 16. Constructor Overloading and Blank Final Fields

If there are multiple constructors, you must ensure that every object construction path initializes the blank final field.

Valid example:

```java
class Configuration {
    private final String mode;

    Configuration() {
        this("DEFAULT");
    }

    Configuration(String mode) {
        this.mode = mode;
    }

    String mode() {
        return mode;
    }
}
```

The no-argument constructor calls `this("DEFAULT")`. The parameterized constructor assigns the `mode` field. Each constructed object has one final value for `mode`.

### Runnable Example

Save **`FinalFieldConstructorDemo.java`**:

```java
class Configuration {
    private final String mode;
    private final int port;

    Configuration() {
        this("DEV", 8080);
    }

    Configuration(String mode, int port) {
        this.mode = mode;
        this.port = port;
    }

    String describe() {
        return mode + ":" + port;
    }
}

public class FinalFieldConstructorDemo {
    public static void main(String[] args) {
        Configuration first = new Configuration();
        Configuration second = new Configuration("PROD", 9090);

        System.out.println(first.describe());
        System.out.println(second.describe());
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 FinalFieldConstructorDemo.java
java FinalFieldConstructorDemo
```

Stdout:

```text
DEV:8080
PROD:9090
```

Note: in Java 17, `this(...)` or `super(...)` in a constructor must follow the rule of appearing at the beginning of the constructor body. In this example, `this("DEV", 8080)` is the first call.

### Error When Not Initializing All Branches

```java
class BadConfiguration {
    final String mode;

    BadConfiguration(boolean enabled) {
        if (enabled) {
            mode = "ACTIVE";
        }
        // INVALID: if enabled is false, mode has not been assigned.
    }
}
```

This is **an intentionally non-compiling example**. To fix it, you must handle the `else` path or always assign an appropriate value.

## 17. Blank Final Fields with Instance Initializers

A blank final instance field can also be assigned in an **instance initializer** of the class itself, for example:

~~~java
class Token {
    final String kind;
    { kind = "ACCESS"; }
    Token() {}
}
~~~

The constructor cannot reassign `kind` because the initializer has already assigned it. In this chapter, the main focus remains `final` on **variables**, so the places where blank final fields can be assigned and the constructor/initializer order are covered in the article **Blank Final Fields and Where Assignment Is Permitted**.

## 18. Static Final Fields: Class-Level Values, Assigned Only Once

A `static final` field is a static variable belonging to the class and is restricted from reassignment.

```java
class Limits {
    static final int MAX_USERS = 100;
}
```

Through valid usage `Limits.MAX_USERS`, code can read the value `100`; it cannot be modified:

```java
// Limits.MAX_USERS = 200; // INVALID.
```

A specific `Limits` instance is not needed because the field is static.

### Blank Static Final Field

You can declare a blank static final field and initialize it inside a **static initializer**:

```java
class Limits {
    static final int MAX_USERS;

    static {
        MAX_USERS = 100;
    }
}
```

If a static final field already has an initializer, it cannot be assigned again in a static block.

The compiler must prove that the blank static final field is assigned according to the rules when class initialization completes normally.

### Java 17 Example

Save **`StaticFinalDemo.java`**:

```java
class Limits {
    static final int MAX_USERS;
    static final String APPLICATION = "Learning";

    static {
        MAX_USERS = 100;
    }

    static String describe() {
        return APPLICATION + ": " + MAX_USERS;
    }
}

public class StaticFinalDemo {
    public static void main(String[] args) {
        System.out.println(Limits.describe());
        System.out.println(Limits.MAX_USERS);
    }
}
```

```bash
javac -encoding UTF-8 StaticFinalDemo.java
java StaticFinalDemo
```

Stdout:

```text
Learning: 100
100
```

**Do not confuse:** `static final` is not always a *compile-time constant*. That also depends on **the type** and **the initialization expression**.

## 19. Compile-Time Constants Differ from Regular `final`

Not every `final` is a **constant variable** at compile time:

~~~java
final int value = Integer.parseInt("42");
static final java.time.LocalDate START =
        java.time.LocalDate.of(2026, 1, 1);
~~~

The value is established at runtime rather than being a valid constant expression according to the JLS. A `final` variable only restricts **reassigning the binding**; the exact conditions for a primitive/String final variable to be treated as a constant variable, cross-module inlining, and class initialization timing are covered in the article **Static Final Constants and Compile-Time Constant Conditions**.

## 20. `final` with `var`: The Inferred Type Remains Fixed

Since Java 10, a local variable can use `var` if the compiler can infer the type from the initializer. `final` can be combined with it seamlessly:

```java
final var name = "Java";
final var count = 10;
```

- `name` is inferred to have type `String`.
- `count` is inferred to have type `int`.
- Both variables are final: they cannot be reassigned after initialization.

This is **not** dynamic typing. The static type of the variable is determined at compile time, and `final` restricts reassignment.

```java
final var builder = new StringBuilder("A");
builder.append("B"); // Valid.
// builder = new StringBuilder("C"); // INVALID.
```

### Specific Limitation of `var`

`var` requires an initializer in a local variable declaration to infer the type. For example:

```java
// final var value; // INVALID: no initializer to infer the type.
```

If a blank final is needed, declare an **explicit type**:

```java
final String value;
value = "Java";
```

Do not assume that `final var` can be "left blank and have its type inferred upon later assignment" like a dynamic type.

## 21. `final` and Lambdas: Captured Variables Must Be final or effectively final

A local variable/parameter used by a lambda from an enclosing scope must be **final or effectively final** (not reassigned according to Java's rules):

~~~java
int offset = 3;
java.util.function.IntUnaryOperator addOffset =
        number -> number + offset;
System.out.println(addOffset.applyAsInt(4)); // 7
// offset++; // Uncommenting this will make the lambda invalid.
~~~

**Effectively final** does not automatically create immutability: an effectively final reference can still point to a mutable object. The article **Distinguishing final, effectively final, and Immutability** analyzes multiple assignment paths, loops, anonymous/local classes, and detailed capture examples.

## 22. Anonymous Classes and Local Classes: Same Capture Concept

**Anonymous classes** and **local classes** can capture local variables/parameters from the enclosing scope with the final/effectively final requirement. If code attempts to reassign a captured local variable, the compiler rejects it; you cannot "work around" it by letting the lambda modify the outer variable itself.

~~~java
final int step = 2;
Runnable action = new Runnable() {
    @Override public void run() {
        System.out.println(step);
    }
};
action.run(); // 2
~~~

This is a rule about the local **binding**; it does not prevent the anonymous object/its own fields from having mutable state. Challenging cases (capturing a loop index, variables assigned in branches) are explained separately in B148.

## 23. `final` Does Not Mean an Object Is Created Only Once in the Program

A declaration inside a method:

```java
static void process() {
    final Object value = new Object();
}
```

Each call to `process()` executes the local declaration once according to the method mechanism; assignment to the `value` variable is only restricted **within that invocation**.

If `process()` is called multiple times, Java can create **many different objects**, not just a single object shared across the entire program.

Similarly, a `final` instance field in different objects represents independent fields:

```java
class Item {
    final int id;

    Item(int id) {
        this.id = id;
    }
}

Item first = new Item(1);
Item second = new Item(2);
```

`first.id` and `second.id` have different values without violating `final`. Each object is initialized with its corresponding constructor value.

**`final` on a local variable/field does not automatically mean a singleton or global constant.** If a single shared instance is desired, a dedicated design such as a static field, factory, or dependency injection is required.

## 24. `final` Fields and Multithreaded Safety

`final` fields have **special initialization semantics** in the Java Memory Model when the object is constructed properly and `this` does not escape prematurely. However, `final` does not turn a mutable object into an immutable one, does not make `count++` atomic, and does not automatically synchronize subsequent modifications to the object graph.

For example, `private final java.util.List<String> items = new java.util.ArrayList<>();` keeps the reference stable, yet still requires synchronization rules when threads update the same list. Choose immutable snapshots, encapsulation, or synchronization based on the contract, rather than inferring thread-safety from the `final` modifier alone.

## 25. `final` in Records: Component Fields Are final, Not Deeply Immutable

A Java 17 `record` has `private final` component fields and corresponding accessors:

~~~java
record Point(int x, int y) {}
~~~

Neither `x` nor `y` can be reassigned after initialization. However, `record Data(int[] values) {}` can still expose a mutable array; a final reference does not guarantee **deep immutability**. If the domain needs a value snapshot, use immutable component types or appropriate defensive copies. Detailed analysis is in the article on **final references** and the article on **effectively final/immutability**.

## 26. `final` Variables Differ from `final` Methods and `final` Classes

The same keyword applies different scope constraints:

| Location | Meaning |
| --- | --- |
| `final int x = 5;` | Variable `x` cannot be reassigned |
| `final SomeObject ref = ...;` | Reference cannot be reassigned; the object may still be mutable |
| `private final String id;` | Field must be properly initialized and cannot be reassigned |
| `final void work()` | Subclasses cannot override that method |
| `final class Value {}` | Does not allow other classes to extend Value |

The article **final on Methods and Classes** goes into detail about overriding, overloading, sealed hierarchies, and extension points; do not use final variable rules to reason about inheritance capabilities.

## 27. `final` in catch, for-each, and try-with-resources

Several special declaration forms also allow/apply similar constraints.

### Catch parameter

```java
try {
    Integer.parseInt("x");
} catch (final NumberFormatException exception) {
    System.out.println("Không phải số hợp lệ");
    // exception = new NumberFormatException(); // INVALID.
}
```

`exception` is a catch parameter and can be declared final. Reassigning the caught-exception parameter is prohibited; reading the exception and calling its methods remain valid.

For a **multi-catch parameter**, Java has language constraints that prevent this parameter from being reassigned in normal usage. It is not necessary to add `final` everywhere just to achieve that behavior.

### Enhanced for

```java
for (final String name : new String[]{"An", "Bình"}) {
    System.out.println(name);
}
```

Each iteration has a final iteration element variable according to the enhanced-for declaration mechanism. `name = "Other";` cannot be written in the body.

### Try-with-resources

```java
try (final java.io.StringReader reader =
             new java.io.StringReader("Java")) {
    System.out.println((char) reader.read());
}
```

The resource variable `reader` is final by declaration. Java manages closing the resource according to try-with-resources syntax. Since Java 9, an existing **final or effectively final** resource variable can be used in the appropriate position, instead of necessarily declaring a new variable inside the parentheses.

**Note:** final is not the reason the resource is closed; it is the semantics of **try-with-resources** that govern calling `close()`.

## 28. Table of Common Errors When Using `final`

| Code/Scenario | Cause | Fix |
| --- | --- | --- |
| `final int n = 1; n = 2;` | Reassigning an already-final variable | Create a new result variable or remove final if updating is truly needed |
| `final int n = 1; n++;` | `++` updates the variable | Use a regular counter variable |
| `final int n = 1; n += 2;` | Compound assignment is also an assignment | Use `int other = n + 2;` |
| `final int n; println(n);` | Reading before definite assignment | Assign a valid value before reading |
| `final String mode; if(flag) mode="A"; print(mode);` | The false branch might leave it unassigned | Add `else` or a value-selecting expression |
| `final int x = 1; if(flag) x = 2;` | There is a path that assigns a second time | Design single-time initialization per branch |
| `for(final int i=0;i<3;i++)` | `i++` assigns the final variable | Use `int i` |
| `final var x;` | `var` lacks an initializer to infer the type | Use an explicit type for a blank final |
| `final List<String> x = new ArrayList<>(); x.add("A");` | Actually **valid** | Distinguish list mutation from variable reassignment |
| `final int[] a = {1}; a[0] = 2;` | Actually **valid** | `final` does not apply to individual elements |
| `void f(final User u) { u = new User(); }` | Reassigning a final parameter | Return a new object to the caller or intentionally remove final |
| `private final int id;` without assignment in the constructor | Blank final field is not validly initialized | Initialize at field/initializer/constructor on all required paths |
| Final field has an initializer, constructor reassigns | Second assignment | Initialize through only one appropriate mechanism |
| Blank static final field is unassigned | Class initialization does not ensure the field has a value | Assign in a static initializer/field declaration |
| Capturing a variable and then reassigning it | The variable is no longer effectively final | Use another variable or an appropriate state/ownership solution |
| `final StringBuilder b = ...; b.append(...)` | Actually **valid** | If immutable contents are needed, use an immutable representation |
| `static final List<String> ITEMS = new ArrayList<>(); ITEMS.add(...)` | Actually **valid** | An immutable list is needed if you want to forbid modifying the object |
| `final class X` where the object still has setters | A final class only forbids inheritance | Design an immutable object separately |
| Changing a public static final compile-time constant without older clients seeing it | Constant inlining may occur | Consider versioning/recompiling clients |

## 29. Practice Exercises with Answers

### Exercise 1 — Final Variable with the Exact Same Value as Initially

```java
final int score = 10;
// score = 10;
```

**Answer:** if uncommented, the code **does not compile**. `final` prohibits a second assignment even when the right-hand side equals the old value.

### Exercise 2 — Two `if`/`else` Branches

```java
final String state;
if (ready) {
    state = "READY";
} else {
    state = "PENDING";
}
System.out.println(state);
```

**Answer:** valid if `ready` is a defined boolean. Each execution path assigns `state` only once; after `if`/`else`, the variable is definitely assigned.

### Exercise 3 — Missing Branch

```java
final int result;
if (valid) {
    result = 1;
}
// System.out.println(result);
```

**Answer:** reading `result` at the end will cause a compilation error because `valid` might be false. Add `else`/return/throw or a way to determine the value along every appropriate path.

### Exercise 4 — `final` with Arrays

```java
final int[] scores = {5, 6};
scores[0] = 9;
System.out.println(scores[0]);
// scores = new int[]{1, 2};
```

**Answer:** prints `9`. Modifying an array element is valid; reassigning `scores` to another array is invalid.

### Exercise 5 — `final` with a Mutable List

```java
final java.util.List<String> items =
        new java.util.ArrayList<>();
items.add("A");
items.add("B");
System.out.println(items);
```

**Answer:** prints `[A, B]`. The final constraint is placed on **the items variable**, not on the structure of the `ArrayList`.

### Exercise 6 — Final Parameter

```java
static void change(final StringBuilder builder) {
    builder.append("!");
    // builder = new StringBuilder("X");
}
```

**Answer:** `append` is valid if builder is non-null and mutable. The line reassigning `builder` is invalid. The caller can observe the appended contents through the passed object.

### Exercise 7 — Local final per Loop Iteration

```java
for (int i = 0; i < 3; i++) {
    final int value = i + 1;
    System.out.println(value);
}
```

**Answer:**

```text
1
2
3
```

The `value` variable is initialized once in each execution of the block's declaration; it is not reassigned inside the block.

### Exercise 8 — Final Field in a Constructor

```java
class Point {
    final int x;
    final int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }
}
```

**Answer:** valid. Each constructed instance initializes the two fields. Other constructors must also ensure the blank final fields are initialized along valid paths.

### Exercise 9 — Final Reference and Alias

```java
final StringBuilder left = new StringBuilder("A");
StringBuilder right = left;
right.append("B");
System.out.println(left);
```

**Answer:** `AB`. `left` does not change its reference value, but the shared object is modified through `right`.

### Exercise 10 — Lambda and Effectively Final

```java
int offset = 3;
java.util.function.IntUnaryOperator f = x -> x + offset;
System.out.println(f.applyAsInt(4));
```

**Answer:** `7`. The `offset` variable is not explicitly declared final, but it is effectively final. If an assignment `offset = 5;` is added in the same scope, capturing it may no longer be valid.

### Exercise 11 — `final var`

```java
final var greeting = "Hello";
System.out.println(greeting);
```

**Answer:** valid in Java 17; `greeting` is inferred to have type `String` and is final. `final var greeting;` is invalid because `var` requires an initializer.

### Exercise 12 — Static Final and Mutable Objects

```java
class Registry {
    static final java.util.List<String> NAMES =
            new java.util.ArrayList<>();
}

Registry.NAMES.add("An");
```

**Answer:** the add operation can be valid because `Registry.NAMES` references a mutable list. `Registry.NAMES = new ArrayList<>();` is invalid because the static field is final. To prevent callers from adding elements in the API, appropriate access control and an immutable collection are needed.

### Exercise 13 — Record Containing an Array

```java
record Data(byte[] bytes) { }
final Data value = new Data(new byte[]{1});
value.bytes()[0] = 9;
```

**Answer:** modifying the array element is valid and changes the array inside the created record. The fact that the `value` variable and component reference field are final does not automatically copy the array or prevent mutation.

## 30. Checklist When Deciding to Add `final` to a Variable

1. **Does the variable need to be reassigned?** If not, `final` makes that intent clear.
2. **Are you using a primitive or a reference?** `final` prevents reassignment for both, but a mutable object can still change state.
3. **If it is a blank final, has the compiler verified it is assigned before being read?**
4. **If assigned across branches**, do all required paths initialize it without assigning twice?
5. **If a counter variable is incremented/decremented in a loop**, do not use `final` on that counter variable itself.
6. **If a local `final` is declared in a loop body**, understand that it is initialized on each respective execution of that block.
7. **If it is a parameter**, do you need to reassign the parameter in the body? If so, consider creating a separate local result variable.
8. **If it is an instance final field**, has it been initialized in the appropriate field initializer/instance initializer/constructor?
9. **If there are overloaded constructors**, do all valid constructor chaining paths ensure that blank final fields have a value?
10. **If it is a static final field**, does it have a valid initializer or static block?
11. **If you call the variable a "constant"**, is it truly a compile-time constant or just a final reference?
12. **If a final reference points to a list/array/builder**, is there still mutable state or an alias from elsewhere?
13. **If captured in a lambda**, is the local variable/parameter final or effectively final?
14. **If using `var`**, is there an initializer to infer the type and do you genuinely want to lock the variable?
15. **If true immutability is needed**, have you protected mutable fields/nested elements and state exposure paths?
16. **If used across multiple threads**, have you considered the thread-safety of the mutable object, not just the final modifier?
17. **If a public API contains compile-time constants**, have you considered the inlining effect when upgrading versions?
18. **If you encounter a javac error**, identify which assignment is attempting to modify **the final variable** rather than assuming that all operations on the object are forbidden.

## Key Takeaways

- **`final` on a variable restricts reassigning the variable**. A validly initialized variable cannot receive a new assignment, even with the same value.
- **A blank final** can be declared first and initialized later if it satisfies Java's **definite assignment/definite unassignment** rules.
- **Multiple code branches can contain assignment statements** for a final variable, as long as the compiler guarantees that valid control paths only initialize the variable according to the rules.
- `++`, `--`, and `+=` are all forms of variable updates, so they do not apply to initialized final variables.
- **A final reference does not mean an immutable object**: you can modify elements of a `final int[]`, add to a `final ArrayList`, or call `append` on a `final StringBuilder`.
- **A final parameter** cannot be reassigned inside a method, yet it still receives the argument value via **pass-by-value**.
- **Final instance/static fields** must be initialized at the proper place and control path; constructors/initializers have their own rules.
- **Final/effectively final** is an important condition when a lambda/local class captures a local variable.
- **Final fields, final methods, and final classes are different**: locking variable assignment, forbidding overriding, or forbidding inheritance are rules at different declaration locations.
- Use `final` to **express the intent of keeping a variable stable**, but to protect object state, design **immutability, defensive copying, access control**, and **thread-safety** separately.
