# Do Not Use `var` for Fields or Method Return Types — Java 17+

## 1. Goal and Short Answer

In Java 17+, `var` supports **local-variable type inference**, not a syntax for replacing declared types everywhere in a program.

**Two core rules:**

- **Do not use `var` to declare a class field**, whether it is an instance field, `static`, or `final`.
- **Do not use `var` as a method's return type**, even if the method executes `return` on an expression whose type the compiler could determine.

~~~java
public final class Counter {
    private int value = 0; // Valid: field has explicit int type

    public int getValue() { // Valid: explicit int return type
        var snapshot = value; // Valid: var declares a local variable in the method body
        return snapshot;
    }
}
~~~

The following lines are **not valid Java syntax**:

~~~java
// private var value = 0;       // INVALID: var cannot declare a field
// public var getValue() {      // INVALID: var cannot be a return type
//     return 0;
// }
~~~

`var` does not turn Java into a dynamically typed language. The compiler still infers a **concrete static type** for the local variable at its declaration site and checks types in subsequent statements.

## 2. Fields, Local Variables, and Method Return Types Differ

Three concepts that are easily confused when learning the syntax:

| Construct | Where Is It Located? | How Is the Type Declared? |
|---|---|---|
| **Instance field** | Inside a class, outside method/constructor/local blocks | Write an explicit type name |
| **Static field** | Inside a class, with `static` | Write an explicit type name |
| **Local variable** | Inside a method, constructor, or valid statement block | Can use `var` if conditions are met |
| **Method return type** | Before the method name in the signature | Write the return type, or `void` |
| **Method parameter** | Inside `(...)` of the method declaration | Write an explicit parameter type |

Example:

~~~java
final class Account {
    private final String owner;       // Field: String
    private static int nextId = 1;    // Static field: int

    Account(String owner) {            // Constructor parameter: String
        var normalized = owner.trim(); // Local variable: String
        this.owner = normalized;
    }

    String getOwner() {                // Method return: String
        var result = owner;            // Local variable: String
        return result;
    }
}
~~~

In this example, the compiler automatically determines the types of `normalized` and `result` from their initializer expressions. However, the syntax of **fields** and **method signatures** still requires stating a concrete type name.

**A class can contain both explicit type declarations and `var`**: each belongs to its own valid scope, with no conflict between them.

## 3. Invalid on Fields: An Initializer Does Not Make `var` Valid

Even when a field has an obvious initial value, you still **cannot** write:

~~~java
// DO NOT INSERT INTO A CLASS TO COMPILE
// class Wrong {
//     private var name = "Java";
//     static var attempts = 0;
//     final var enabled = true;
// }
~~~

This is invalid because `var` is not permitted in the type position of a field. Modifiers like `private`, `static`, or `final` do not change this restriction.

The valid way:

~~~java
final class Settings {
    private String name = "Java";
    private static int attempts = 0;
    private final boolean enabled = true;
}
~~~

**Fields are not inferred from their initial values** in Java 17. The compiler knows `"Java"` has type `String`, but Java does not define `var` syntax for fields based on that information.

### What If a Field Receives a Generic Object?

~~~java
import java.util.ArrayList;
import java.util.List;

final class Group {
    private final List<String> members = new ArrayList<>();
}
~~~

Here Java allows the **diamond `<>`** on the right-hand side thanks to the **explicit target type** `List<String>` on the left-hand side. This is not a field declaration using `var`.

With the code:

~~~java
// private final var members = new ArrayList<String>(); // INVALID
~~~

it is still a syntax error even though the initializer specifies `ArrayList<String>`.

**Design benefit:** declaring `List<String>` as the field shows that the code relies on the `List` abstraction rather than locking the API to the `ArrayList` implementation class.

## 4. Invalid on Return Types: `return` Does Not Replace the Type Declaration

Java requires a method to declare its return type in its signature:

~~~java
static int sum(int a, int b) {
    return a + b;
}
~~~

You cannot replace `int` with `var`:

~~~java
// static var sum(int a, int b) {
//     return a + b;
// }
~~~

Reason: `var` is an inference mechanism for **local variable declarations in allowed language positions**, not a mechanism for inferring a method's return type across all `return` branches.

A method that returns no value uses `void`, **not `var`**:

~~~java
static void logMessage(String message) {
    System.out.println(message);
}
~~~

### `var` Can Still Be Used Inside a Value-Returning Method

~~~java
static long square(int input) {
    var result = (long) input * input; // Infers long
    return result;                     // Explicit long return type
}
~~~

Here `result` is a local variable of type `long`; the `square` method still has a signature returning `long`.

### Distinguishing the Return Expression from the Method Signature

~~~java
static double average(int x, int y) {
    var total = x + y;   // int
    return total / 2.0;  // double
}
~~~

A method can certainly contain multiple type-inferred local variables. However, the **return contract** is still defined by the `double` type at the start of the signature.

## 5. `var` Inside Constructor Bodies, Instance Initializers, and Static Initializers

You cannot declare a field with `var`, but you **can declare local variables with `var` inside code blocks** of a class, such as a constructor:

~~~java
final class Product {
    private final String code;

    Product(String rawCode) {
        var normalized = rawCode.strip();
        this.code = normalized;
    }
}
~~~

And inside an **instance initializer block**:

~~~java
final class Metrics {
    private int total = 0;

    {
        var initialValue = 5; // Local variable inside the initializer block
        total = initialValue;
    }
}
~~~

Similarly, inside a **static initializer**:

~~~java
final class Configuration {
    private static final int DEFAULT_SIZE;

    static {
        var computed = 16 * 2; // Local variable of type int
        DEFAULT_SIZE = computed;
    }
}
~~~

**Position distinction:**

- `private var total = 0;` → invalid because it is declaring a field.
- Inside `{ var temporary = 0; }` → valid if it is inside a valid statement block and has an initializer.

A statement block **does not turn a local variable into a field**. The variable `temporary` only exists within the lexical scope of the block and cannot be accessed from outside.

## 6. Conditions for Local Inference Do Not Permit Field Inference

In a valid **local position**, the compiler infers the type from the initializer; in a **field position** or **method signature**, even if the type could be guessed from an expression, Java 17 still demands an explicit type.

~~~java
var count = 1;                   // local: int
var list = new java.util.ArrayList<String>(); // local: ArrayList<String>
String nullable = null;          // Explicit reference type
// var absent = null;            // Local cannot infer type
// var missing;                  // Local missing initializer
~~~

Do not conflate the two questions “**does the expression have an inferable type?**” and “**does the declaration position allow var?**”. A valid expression is not enough if you are declaring a field or a return type.

## 7. `var` Does Not Change Field or Method Return Contracts

Consider a class with a simple interface:

~~~java
final class Invoice {
    private final long cents;

    Invoice(long cents) {
        if (cents < 0) {
            throw new IllegalArgumentException("negative amount");
        }
        this.cents = cents;
    }

    long getCents() {
        var snapshot = cents; // long
        return snapshot;
    }

    String describe() {
        var label = "cents=";
        return label + cents;
    }
}
~~~

Parts that stay **stable in the API**:

- The `cents` field is always declared `long`.
- The constructor takes a `long` parameter.
- `getCents()` declares a `long` return type.
- `describe()` declares a `String` return type.

Parts that can be **shortened locally**:

- `snapshot` and `label` are local variables with suitable initializers.

This is a sensible way to combine `var`: keep types clear at **class/API boundaries** and reduce type repetition where the initializer makes the concrete type obvious.

### Why Is an Explicit Return Type Important?

Callers may depend on the signature:

~~~java
long totalCents = invoice.getCents();
String text = invoice.describe();
~~~

If the method author modifies the internal computation expression, the explicit signature lets the compiler verify that the returned value remains compatible. This serves as a layer of protection for the API contract during refactoring.

## 8. Method Parameters, Lambdas, and Generic Types at API Boundaries

**Method parameters** still require explicit types: `static String format(int n)` is valid, whereas `format(var n)` is invalid. For **lambda** parameters, since Java 11 `var` can be used when the lambda already has a target type:

~~~java
java.util.function.IntBinaryOperator add =
        (var left, var right) -> left + right;
System.out.println(add.applyAsInt(2, 3)); // 5
~~~

A lambda parameter list must not mix `var` with untyped parameters or explicitly typed parameters. For instance, `var callback = x -> x + 1;` is still invalid because the initializer is a lambda lacking a functional target type.

For generics, field/API declarations should express **the desired abstraction level**:

~~~java
private final java.util.List<String> members =
        new java.util.ArrayList<>();
~~~

Here `List<String>` is the published field type; the diamond receives the target type. If in local code you write `var bag = new java.util.ArrayList<>();`, the inferred type in this situation is `ArrayList<Object>`, and it does not automatically infer `ArrayList<String>` from later `add` calls. Allowed positions and generic inference are mentioned here to **distinguish API boundaries from local code**, not to replace the dedicated coverage in other lessons.

## 9. Return Type Does Not Automatically Change Based on `var` Inside the Method

Suppose a method is declared to return `long`, but the internal expression has type `int`:

~~~java
static long twice(int input) {
    var result = input * 2; // int; calculation happens in int
    return result;          // Widening int -> long on return
}
~~~

**Pitfall:** if `input` is too large, the `int` multiplication can overflow **before** converting to `long`. `var` does not predict an intent to compute in a wider type.

~~~java
static long twiceSafe(int input) {
    var result = (long) input * 2; // long from the time of multiplication
    return result;
}
~~~

With `input = 2_000_000_000`:

~~~java
System.out.println(twice(2_000_000_000));     // -294967296
System.out.println(twiceSafe(2_000_000_000)); // 4000000000
~~~

Both methods **return `long` per their signatures**, yet the **types of the intermediate calculations** differ. This is an important reason to understand the type the compiler infers, rather than just reading the word `var`.

### The Compiler Still Checks the Return Type

~~~java
static int count() {
    var text = "not an int";
    // return text; // Compile error: String cannot be converted to int
    return 1;
}
~~~

`var` does not let you “hide” a return value of the wrong type. The method signature remains a contract enforced by the compiler.

## 10. Fixing Errors in Fields and Method Signatures Properly

| Incorrect Usage | Why Is It Wrong? | Replace With |
| --- | --- | --- |
| `private var name = "Java";` | `var` cannot declare a field | `private String name = "Java";` |
| `static var count = 1;` | `static` does not make a field type-inferred | `static int count = 1;` |
| `public var name() { ... }` | Method signature must declare a return type | `public String name() { ... }` |
| `void set(var x)` | Method parameter must have a type | `void set(int x)` |
| `record Pair(var a, int b)` | Record component requires a type | `record Pair(int a, int b)` |

If the code is **already inside a method/constructor/block body**, `var local = expression;` can be valid; do not fix a field or method signature by moving data into a local variable and losing the external contract.

## 11. Complete, Standalone Java 17 Example

Save the file with the exact name **`VarMemberReturnDemo.java`**:

~~~java
import java.io.StringReader;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.function.IntBinaryOperator;
import java.util.function.IntUnaryOperator;

public final class VarMemberReturnDemo {
    private static final int DEFAULT_LIMIT = 5; // Field: explicit type
    private static int created = 0;             // Static field: explicit type

    private final String label;                 // Instance field
    private final List<String> history = new ArrayList<>();

    static {
        var marker = "class initialized";      // Local in static block
        if (marker.isEmpty()) {
            throw new IllegalStateException("empty marker");
        }
    }

    {
        var entry = "instance initialized";     // Local in instance block
        history.add(entry);
    }

    VarMemberReturnDemo(String rawLabel) {
        var normalized = Objects.requireNonNull(rawLabel).strip();
        label = normalized;
        created++;
    }

    public String labelText() {                 // Explicit return type
        var prefix = "Label:";
        return prefix + label;
    }

    public int sum(int left, int right) {        // Explicit parameters/return type
        var result = left + right;
        return result;
    }

    public List<String> history() {              // Return interface List<String>
        return List.copyOf(history);
    }

    static long twice(int input) {               // Return long, compute in int
        var result = input * 2;
        return result;
    }

    static long twiceSafe(int input) {           // Return long, compute in long
        var result = (long) input * 2;
        return result;
    }

    public static void main(String[] args) throws Exception {
        var demo = new VarMemberReturnDemo("  Core  ");
        System.out.println("label=" + demo.labelText());
        System.out.println("history=" + demo.history());
        System.out.println("sum=" + demo.sum(2, 3));

        var count = DEFAULT_LIMIT; // int
        count += 2;
        System.out.println("local int=" + count);

        var title = "Java"; // String
        System.out.println("text length=" + title.length());

        var names = new ArrayList<String>();
        names.add("Lan");
        System.out.println("typed list=" + names);

        List<String> contract = new ArrayList<>();
        contract.add("An");
        System.out.println("interface list=" + contract);

        var inferredReturn = demo.history(); // List<String>
        System.out.println("return item=" + inferredReturn.get(0));

        var nullable = (String) null;
        System.out.println("typed null=" + (nullable == null));

        IntBinaryOperator add = (var a, var b) -> a + b;
        System.out.println("lambda vars=" + add.applyAsInt(3, 4));

        var increment = (IntUnaryOperator) (x -> x + 1);
        System.out.println("lambda target=" + increment.applyAsInt(5));

        for (var i = 0; i < 2; i++) {
            System.out.println("for=" + i);
        }

        try (var reader = new StringReader("Z")) {
            System.out.println("reader=" + (char) reader.read());
        }

        System.out.println("twice int first=" + twice(2_000_000_000));
        System.out.println("twice long first=" + twiceSafe(2_000_000_000));

        var alias = demo;
        System.out.println("same instance=" + (alias == demo));
        System.out.println("objects created=" + created);
    }
}
~~~

**Requirements:** JDK 17 or later; terminal positioned in the directory containing `VarMemberReturnDemo.java`. No Maven, Gradle, or non-JDK libraries required.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 VarMemberReturnDemo.java
java -cp . VarMemberReturnDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\VarMemberReturnDemo.java
java -cp . VarMemberReturnDemo
~~~

**Exact expected output:**

~~~text
label=Label:Core
history=[instance initialized]
sum=5
local int=7
text length=4
typed list=[Lan]
interface list=[An]
return item=instance initialized
typed null=true
lambda vars=7
lambda target=6
for=0
for=1
reader=Z
twice int first=-294967296
twice long first=4000000000
same instance=true
objects created=1
~~~

### Why Does This Code Respect the Scope of `var`?

1. The fields `DEFAULT_LIMIT`, `created`, `label`, and `history` all state **explicit types**.
2. The methods `labelText`, `sum`, `history`, `twice`, `twiceSafe`, and `main` all have **explicit return types**, including `void`.
3. The variables `marker`, `entry`, `normalized`, `prefix`, and `result` are **local** inside valid statement blocks.
4. `IntBinaryOperator add = (var a, var b) -> ...` is valid because the lambda has a target type.
5. `var nullable = (String) null` has type `String` because the cast supplies a type for the initializer.
6. `var inferredReturn = demo.history()` infers `List<String>` from the **declared return type of the method**, not because the compiler inspects the runtime object.
7. `twice` and `twiceSafe` both return `long`, but the types of their intermediate multiplication differ, resulting in different outputs — static typing is still in control.
8. `same instance=true` because assigning `alias` copies the reference without creating a new object.

## 12. Exercises with Solutions

### Exercise A — Fix Field Declaration

Invalid snippet:

~~~java
// final class Item {
//     private var id = 7;
// }
~~~

**Answer:**

~~~java
final class Item {
    private int id = 7;
}
~~~

### Exercise B — Fix Method Return Type

Invalid snippet:

~~~java
// static var greeting() {
//     return "Hello";
// }
~~~

**Answer:**

~~~java
static String greeting() {
    return "Hello";
}
~~~

You can use a local `var` inside the method body:

~~~java
static String greeting() {
    var text = "Hello";
    return text;
}
~~~

### Exercise C — `var` Inside a Constructor

~~~java
final class User {
    private final String name;

    User(String input) {
        var trimmed = input.trim();
        name = trimmed;
    }
}
~~~

**Answer:** valid. `trimmed` is a local variable of type `String`; `name` is an explicitly declared field. If `input` can be null, validation should be added according to the contract.

### Exercise D — Does `var` Make a Method Return a New Type?

~~~java
static long compute(int x) {
    var doubled = x * 2;
    return doubled;
}
~~~

**Answer:** the method's return type is still **`long`**; `doubled` has type **`int`**. The multiplication happens in `int`, and only afterward is the result widened to `long`. For large inputs, there is a risk of `int` overflow before returning. How to fix if `long` multiplication is needed: `var doubled = (long) x * 2;`.

### Exercise E — Valid Position or Not?

Evaluate:

~~~java
// private final var names = new ArrayList<String>();
// public var names() { return List.of("An"); }

static List<String> names() {
    var result = List.of("An");
    return result;
}
~~~

**Answer:** the two commented lines are **invalid** because they are a field and a return type. The `names()` method is valid, explicitly declaring a return type of `List<String>`; `result` is a local variable inferring its type from `List.of("An")`.

### Exercise F — Generics with Fields

You want a field to maintain the `List<String>` API while constructing it with `ArrayList`:

~~~java
private final java.util.List<String> names =
        new java.util.ArrayList<>();
~~~

**Answer:** valid and expresses abstraction. Do not change it to `private final var names = ...` because `var` cannot declare a field.

## 13. Checklist and Conclusion

- [ ] Know that `var` is only type-inference syntax in **valid local declarations**.
- [ ] Do not use `var` for instance fields, static fields, or final fields.
- [ ] Do not use `var` in the return type position of a method.
- [ ] Do not use `var` for regular method parameters or record components.
- [ ] Use explicit types to represent class/API contracts.
- [ ] Know that local `var` is valid in methods, constructors, and instance/static initializer blocks.
- [ ] Know that `var` requires an initializer with an inferable type; a bare null literal is not enough.
- [ ] Know `var` in `for`, enhanced `for`, `try-with-resources`, and conditional lambda parameters.
- [ ] Understand that `var` syntax does not change type upon reassignment.
- [ ] Remember that generics, overloads, operators, and member access are still **checked statically**.
- [ ] Know that the initializer's type can cause overflow before the result is returned as a wider type.
- [ ] Choose explicit type declarations when the abstraction level or data contract matters.
- [ ] Compile and run `VarMemberReturnDemo.java` with `javac`/`java`; compare every line of expected output.

**Conclusion:** In Java 17+, `var` is a convenience to reduce type-name repetition for **local variables with valid initializers**. It is **not a data type**, so it cannot be used as a **field type** or **method return type**. Declare types explicitly at class/API boundaries and use `var` inside statement bodies when the initializer makes the static type easy to understand and verify.