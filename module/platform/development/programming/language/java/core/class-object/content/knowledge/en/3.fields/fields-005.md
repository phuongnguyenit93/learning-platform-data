# Distinguishing Fields, Parameters, and Local Variables in Java

## Objectives

After this lesson, you will be able to:

- Correctly identify **fields**, **parameters**, and **local variables** when reading a Java class.
- Distinguish the declaration location, *scope*, when a value is received, stored state, and accessibility of each kind.
- Understand the difference between an **instance field** and a **static field**, and between a field's default value and the *definite assignment* rule for local variables.
- Distinguish an object's field from a parameter/local variable with the same name using `this` and the class name.
- Accurately explain Java's **pass-by-value** parameter-passing mechanism for primitive types and reference types.
- Use `final`, *effectively final* variables, and `var` in the appropriate context, avoiding misunderstandings when writing constructors, methods, and lambdas.

## 1. Three Common Kinds of Variables in a Java Class

Consider the simple class below:

~~~java
public class Product {
    private String name;       // Instance field
    private int quantity;       // Instance field
    private static int created; // Class field (static field)

    public Product(String name, int quantity) { // Two constructor parameters
        this.name = name;
        this.quantity = quantity;
        created++;
    }

    public void add(int amount) { // amount is a method parameter
        int oldQuantity = quantity; // Local variable
        quantity += amount;
        System.out.println(oldQuantity + " -> " + quantity);
    }
}
~~~

This is **a complete compilable class**, but it does not have `main`; a standalone runnable program example will appear later.

- **Field**: `name`, `quantity`, and `created` are declared directly in the class body, outside the methods/constructors. The first two fields belong to each object; `created` belongs to the class because it has `static`.
- **Parameter**: `name`, `quantity` in the constructor and `amount` in `add`. When calling the constructor/method, an *argument* provides the value for the corresponding formal parameter.
- **Local variable**: `oldQuantity` is declared inside the body of `add`, used to store the quantity before updating it in that call.

The name `quantity` in the same program can be a **field** or a **parameter**, depending on where it is declared and how it is referenced. Data type does not determine the variable kind: fields, parameters, and local variables can all have type `int`, `String`, an array, or another reference type.

### 1.1. Core Comparison Table

| Criterion | Field | Parameter | Local variable |
| --- | --- | --- | --- |
| Declaration location | Directly in a class or a type with fields, outside methods/constructors | In the parameter list of a constructor/method, lambda, or corresponding parameter context | Inside a method/constructor body, block, or certain constructs such as loops |
| Belongs to | The object if not `static`; the class if `static` | A single call or execution of the construct receiving the parameter | A single execution of the declaring scope |
| Initial value | Has a default value; an initializer/constructor can change it | Assigned from the argument when the call starts | Must be definitely assigned before being read; has no default value to read |
| Scope of use | Follows the class's naming, access, and static/instance rules | Scope defined by the parameter declaration, typically the method/constructor body | From the point of declaration within the corresponding block/construct |
| Common modifiers | `private`, `public`, `protected`, `static`, `final`, ... | Can use `final`; cannot declare `private` or `static` for method parameters | Can use `final`; `var` supports local type inference in valid contexts |
| Example | `private int balance;` | `deposit(int amount)` | `int fee = 2;` |
| Access via `this` | Can use `this.field` for an instance field | No `this.parameter`; a parameter is its own variable name | No `this.local`; a local is its own variable name |

**Terminology note:** At the Java specification level, a parameter is a distinct kind of variable with its own scope/initialization rules; in everyday speech, people sometimes call parameters "local variables" as well. When analyzing a program, it is best to clearly separate the three groups so you do not confuse their roles.

## 2. Field: State of an Object or Class

An **instance field** represents part of the state of each object. With two different objects, each object has a field with the same name but **its own state location**:

~~~java
class Counter {
    int value;

    void increment() {
        value++;
    }
}
~~~

This is a class declaration snippet usable in an appropriate Java file, without `main`. If you create `Counter first = new Counter();` and `Counter second = new Counter();`, after calling `first.increment()`, the value of `first.value` is `1`, while `second.value` is still `0`.

Conversely, a **static field** is associated with the class:

~~~java
class Counter {
    static int totalCreated;
    int value;

    Counter() {
        totalCreated++;
    }
}
~~~

Creating `new Counter()` twice increments the same `Counter.totalCreated`. `static` does not mean the field is automatically thread-safe: `totalCreated++` consists of multiple operations and is not guaranteed to be atomic when multiple threads write concurrently.

### 2.1. Fields Have Default Values, Unlike Parameters and Locals

Explicitly unassigned `int` fields are initially `0`; `boolean` fields are `false`; reference-type fields such as `String` are `null` (other primitive types receive defaults corresponding to their type). This holds for instance and static fields prior to the relevant initializers. A **parameter** receives its value from the argument at the time of the call, whereas a **local variable** cannot be read before it has been definitely assigned according to the *definite assignment* rule.

When classifying these three kinds of variables, what matters more than repeating the default-value table verbatim is this: **a field belongs to the object/class, a parameter belongs to the call, and a local belongs to the execution scope**. They differ in both where they are declared and when they receive their values; the following examples clarify each group.

### 2.2. Access and Encapsulation

For state data, fields are typically declared `private` and modified through methods to protect validity conditions:

~~~java
class Wallet {
    private int balance;

    void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        balance += amount;
    }

    int balance() {
        return balance;
    }
}
~~~

This snippet is an illustrative class declaration without `main`. `balance` is a field; `amount` is a parameter. Declaring it `private` affects **the field's accessibility from other code**; it does not turn it into a local variable.

## 3. Parameter: A Name Receiving a Value from a Call

Parameters are written in the parameter list when **declaring** a method or constructor. When **calling** a method/constructor, you pass *arguments* in.

For example:

~~~java
void rename(String newName) {
    this.name = newName;
}
~~~

This is an illustrative method inside a class that has an instance field `name`. `String newName` is the **formal parameter declaration**; in the call `book.rename("Java");`, `"Java"` is the **argument**. `newName` exists under that name within the method scope, and the call supplies its initial value.

- Each call has its own parameter variables for that call.
- A parameter is not automatically a field: changing a parameter via assignment **does not automatically change the object's state**.
- The same holds for constructor parameters: `this.name = name;` is an explicit operation that copies the parameter's value into the field.
- In a regular method, a parameter has a declared type, a name, and optionally the `final` modifier; Java **does not support default arguments in method declarations** using syntax like `void f(int x = 1)`.

Parameters also appear in **lambdas** and **catch clauses**, with their own details regarding type, scope, and modifiers. In this lesson, the main focus is on method/constructor parameters to make comparison with fields and local variables easier.

### 3.1. Java Always Passes Parameters by Value

This is a particularly important principle:

- For **primitive types** such as `int`, the method receives a **copy of the numeric value**. Reassigning the parameter does not modify the caller's variable.
- For **reference types** such as `StringBuilder` or `Box`, the method receives a **copy of the reference value**. This copy points to the same object, so the method can modify the object's contents if the object allows it.
- If the method **reassigns the reference parameter to another object**, the original reference variable in the caller still remains unchanged. Java **does not pass the caller's variable by reference**.

The runnable program in Section 6 will illustrate all three of these scenarios.

## 4. Local Variable: A Variable Used Within an Execution Scope

A local variable is declared inside a block, a method/constructor body, or a construct that permits local variable declarations. For example:

~~~java
void calculate(int price) {
    int tax = 2;
    int total = price + tax;
    System.out.println(total);
}
~~~

`price` is a parameter; `tax` and `total` are local variables. Each time the method runs, the corresponding local variables serve only that execution. They do not become fields of the object and cannot be read from another method simply by that variable name.

### 4.1. Local Variables Must Be Assigned Before Being Read

A field has a default value, whereas a local variable must satisfy the **definite assignment** rule (definitely assigned on every control-flow path that can reach the point where it is read).

~~~java
void example(boolean enabled) {
    int result;

    if (enabled) {
        result = 10;
    } else {
        result = 20;
    }

    System.out.println(result); // Valid: both branches assign result
}
~~~

This is an illustrative method, not a standalone runnable file. If you remove the `else` branch without assigning `result` on another path, the compiler will report that the local variable might not have been initialized. Even if you know "enabled is actually always true", the compiler still applies control-flow analysis according to the language rules.

Note the distinction:

~~~java
class Example {
    int field;   // Defaults to 0

    void method() {
        int local;
        // System.out.println(local); // Does not compile if uncommented
        local = 5;
        System.out.println(field + local);
    }
}
~~~

In this case, `field` can be read before being explicitly assigned because it already defaults to `0`; `local` must be assigned `5` before being read.

### 4.2. Local Variable Scope and Blocks

Curly braces create useful block scopes:

~~~java
void blocks() {
    int outer = 10;

    if (outer > 0) {
        int inner = 5;
        System.out.println(outer + inner);
    }

    System.out.println(outer);
    // System.out.println(inner); // Error: inner is out of scope
}
~~~

In the method above, `outer` is used in both the outer block and the `if` block; `inner` is only in scope inside the `if` block. When a declaration is placed inside a `for` loop such as `for (int i = 0; i < 3; i++)`, the variable `i` only exists within the scope permitted by the `for` construct; `i` cannot be read after the loop.

In Java, **you cannot redeclare a local variable or parameter with the same name inside a nested block while the scope of the outer variable is still active**. For example, if a method has already declared `int n = 1;`, a nested block cannot redeclare `int n = 2;` in a way that creates two local variables with the same name and overlapping scopes. This is different from a local/parameter shadowing a **field** with the same name, which is valid.

### 4.3. `var` Only Infers Types in Permitted Contexts

Since Java 10, local variable declarations with an initializer can use `var`:

~~~java
var count = 5;            // Inferred type is int
var title = "Java";       // Inferred type is String
var names = new java.util.ArrayList<String>();
~~~

These are illustrative local variable lines inside a method. `var` **is not a dynamic data type**: the compiler infers a concrete static type at compile time. `var count = 5;` does not allow later assigning `count = "text";`.

The following declarations are invalid:

~~~java
// A local int is allowed to be declared unassigned:
int temporary;

// Invalid in a local context: no initializer to infer the type
// var unknown;

// Invalid at class level: Java does not allow var as the type of a field
// private var score = 10;
~~~

You cannot use `var` in place of a parameter's type in a regular method/constructor declaration; Java 11+ has a separate `var` syntax for **lambda parameters** with specific constraints. `var` also cannot be used for a local declaration without an initializer or with an initializer that is just `null`.

## 5. Name Collisions: A Field Shadowed by a Parameter or Local Variable

When a field and a parameter have the same name, the simple name inside the method usually refers to the parameter; the field can be explicitly specified using `this.fieldName`.

~~~java
class Person {
    private String name;

    Person(String name) {
        this.name = name;
    }

    void rename(String name) {
        this.name = name;
    }

    void print() {
        String name = "Local";
        System.out.println(name);      // Local variable
        System.out.println(this.name); // Instance field
    }
}
~~~

In the constructor `Person(String name)`:

- `name` on the right side of `=` is the parameter.
- `this.name` on the left side is the instance field.
- If you write `name = name;`, it only reassigns the parameter to itself. The field `name` **does not receive the argument's value**.

In `print()`, `String name = "Local";` is a local variable that shadows the field `name`. `this.name` can still access the field.

**`this` is only meaningful in an appropriate instance context.** A static method has no current object `this`; to access an instance field from a static method, you must have a reference to an object, such as `person.name` if access permissions allow it. For a static field, the explicit way to write it is `ClassName.field`.

When a class involves inheritance, a local/parameter can shadow a field, and a field in a subclass can also hide a superclass field; those are different naming mechanisms. Within the scope of this lesson, the principle to keep in mind is **do not confuse identical names with being the same variable**.

## 6. Standalone Runnable Example: All Three Variable Kinds in One Program

Save the code to **`VariableKindsDemo.java`**:

~~~java
public class VariableKindsDemo {
    private final String name; // Instance field
    private int points;        // Instance field, defaults to 0
    private static int createdCount; // Static field, defaults to 0

    public VariableKindsDemo(String name, int points) {
        // name and points on the right side of = are constructor parameters.
        this.name = name;
        this.points = points;
        createdCount++;
    }

    public void addPoints(int points) {
        int before = this.points; // Local variable
        this.points += points;    // this.points: field; points: parameter

        System.out.println(name + ": " + before + " -> " + this.points);
    }

    public void printScopes() {
        int points = 999; // Local variable shadows the field points
        System.out.println("local=" + points + ", field=" + this.points);
    }

    public static void main(String[] args) {
        VariableKindsDemo a = new VariableKindsDemo("A", 10);
        VariableKindsDemo b = new VariableKindsDemo("B", 20);

        a.addPoints(3);
        b.addPoints(4);
        a.printScopes();

        System.out.println("A=" + a.points + ", B=" + b.points);
        System.out.println("created=" + VariableKindsDemo.createdCount);
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 VariableKindsDemo.java
java VariableKindsDemo
~~~

**Exact output:**

~~~text
A: 10 -> 13
B: 20 -> 24
local=999, field=13
A=13, B=24
created=2
~~~

Analysis:

1. `name`, `points`, and `createdCount` are all fields; the first two fields belong to each object A/B, while `createdCount` belongs to the class and is incremented when the constructor runs.
2. `main(String[] args)` has the parameter `args`, which is a string array passed in by the JVM. The two names `a` and `b` are local variables in the `main` method, holding references to the two objects.
3. In `addPoints(int points)`, `points` is a parameter receiving `3` or `4`; `before` is a local variable holding the old field value during that call.
4. `this.points += points` modifies the field of **the object receiving the call**, without reassigning the parameter.
5. `printScopes()` creates a local variable `points = 999`, while A's field remains `13`. Therefore, the printed line shows both `local=999` and `field=13`.
6. In `main`, the calls involving the two objects A/B show that the fields are independent; `createdCount` is a class-level shared value.

**Key takeaway:** A name like `points` appearing in multiple places does not prove it is a single variable. You need to examine **where it is declared** and **the referencing expression**.

## 7. Standalone Runnable Example: Pass-by-Value and Object References

Save the code under the name **`ParameterPassingDemo.java`**:

~~~java
public class ParameterPassingDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void changeNumber(int number) {
        number += 10; // Only modifies the copied parameter
        System.out.println("inside number=" + number);
    }

    static void changeBox(Box box) {
        box.value += 5;  // Modifies the same object as the caller
        box = new Box(999); // Reassigns the parameter variable, not the caller's variable
        System.out.println("inside box=" + box.value);
    }

    public static void main(String[] args) {
        int number = 7;    // Local variable
        Box box = new Box(20); // Local variable referencing an object

        changeNumber(number);
        System.out.println("outside number=" + number);

        changeBox(box);
        System.out.println("outside box=" + box.value);
    }
}
~~~

Command to run:

~~~bash
javac ParameterPassingDemo.java
java ParameterPassingDemo
~~~

Output:

~~~text
inside number=17
outside number=7
inside box=999
outside box=25
~~~

Detailed explanation:

- `number` in `main` is a local variable with the value `7`. When calling `changeNumber(number)`, Java creates the call's parameter `number` with **a copy of the value `7`**. Adding `10` inside the method produces `17`, without changing the `number` variable in `main`.
- `box` in `main` stores a reference value pointing to the `Box(20)` object. The parameter `box` of `changeBox` receives **a copy of that reference value**; both temporarily point to the same object.
- `box.value += 5` changes the field of the referenced object from `20` to `25`. Because `main` still references the same original object, `25` is observed.
- `box = new Box(999)` only makes **the parameter box** point to a new object inside the method; `main`'s local variable `box` still points to the old object. Therefore, the method prints `999`, and the caller prints `25`.

Java **only passes by value**, even when the copied value is a reference. The phrase "passing objects by reference" can easily mislead learners into thinking a method can directly reassign the caller's reference variable.

## 8. Lifetime, Scope, and How the JVM Executes

**Scope** is the region of code where a variable name is allowed to be referenced according to Java's rules. It is different from **the lifetime of a value/object** and different from actual memory layout.

- **Instance field**: is part of an object's state. It can be accessed across many different method calls as long as an appropriate reference exists and access is permitted.
- **Static field**: is tied to the class in the class-loading context; it does not create separate copies when calling methods or creating more objects with `new`.
- **Parameter/local variable**: belongs to the scope of a single method/constructor/block execution. Each call has its own binding; a local name does not automatically appear in another call.
- **An object created inside a method**: does not necessarily disappear as soon as the method finishes. If a reference to the object is returned or stored in a field/another structure, the object can continue to exist.
- **A local variable captured by a lambda**: the compiler and runtime handle it according to capture rules, so you should not use the simplistic rule "every local variable always lives on the stack and then disappears" to explain Java semantics.

You should not equate field = heap and local variable = stack as a **mandatory guarantee** of Java. That may serve as an intuitive model for beginners, but the JVM/JIT has the freedom to optimize how storage is arranged. From a language perspective, distinguishing them by **declaration, scope, value assignment, and accessibility** is more accurate.

## 9. `final`, Effectively Final, and Lambda Capture

The `final` keyword can appear before a field, parameter, or local variable, though the specific effect depends on the kind of variable:

| Variable | What does `final` mean? |
| --- | --- |
| Instance field | Follows the single-assignment rule for final fields; can be assigned at declaration or during a permitted initialization phase, such as a constructor |
| Static field | Follows the single-assignment rule for final fields; typically assigned at declaration or in a static initializer |
| Parameter | The parameter variable cannot be reassigned inside the method body |
| Local variable | Cannot be reassigned after being assigned a value under the definite assignment rules |

For example, the following snippets are placed in an appropriate method context:

~~~java
final int limit = 10;
// limit = 11; // Invalid: reassigning a final local variable

final StringBuilder builder = new StringBuilder("A");
builder.append("B"); // Valid: does not change the reference variable builder
// builder = new StringBuilder(); // Invalid: reassigning a final variable
~~~

`final` on a reference **does not automatically make the referenced object immutable**. If an immutable object is needed, you must design/choose an appropriate data type.

An **effectively final** local variable or parameter is one that is not declared `final` but is never reassigned according to the language rules. A lambda or anonymous class can capture local variables and parameters only when they are `final` or *effectively final*.

### Standalone Runnable Capture Program

Save the file **`CaptureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CaptureDemo {
    static void greet(final String prefix) {
        String name = "Lan"; // Effectively final
        Runnable sayHello = () -> System.out.println(prefix + " " + name);
        sayHello.run();
    }

    public static void main(String[] args) {
        greet("Chào");

        List<String> names = new ArrayList<>(); // Effectively final
        Runnable printSize = () -> System.out.println("size=" + names.size());

        names.add("Java"); // Modifies the object, does not reassign the names variable
        printSize();
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 CaptureDemo.java
java CaptureDemo
~~~

Output:

~~~text
Chào Lan
size=1
~~~

In `greet`, `prefix` is a final parameter; `name` is an effectively final local variable. The lambda can read both. In `main`, `names` is effectively final because the reference variable is not reassigned, even though elements are added to the `ArrayList` object.

If you add `name = "Mai";` after the declaration while still using `name` in the lambda, or add `names = new ArrayList<>();` after the lambda captures `names`, the compiler will report an error because the variable is no longer effectively final. This is a **compile-time** check, not a restriction on modifying the contents of a mutable object.

## 10. Other Easily Confused Cases

### 10.1. A Parameter and an Argument Are Not the Same Variable

~~~java
int original = 5; // local variable
printValue(original); // original is the argument expression
~~~

`printValue` could be declared `static void printValue(int value) { ... }` in the same class. `value` is the parameter, initialized from the value of the argument `original`. When the method executes `value = 10`, the variable `original` remains `5`. This snippet only illustrates the relationship; it is not a standalone program.

### 10.2. A Field and a Local with the Same Name Do Not Mean Two Fields

~~~java
class Sample {
    int value = 10;

    void show() {
        int value = 3;
        System.out.println(value);      // 3: local variable
        System.out.println(this.value); // 10: instance field
    }
}
~~~

The local variable `value` only exists within the scope of `show()`; it does not replace the field or create a new field in the object. `this.value` is the explicit way to reference the field.

### 10.3. Loop Variables and Block Variables

~~~java
for (int i = 0; i < 2; i++) {
    int square = i * i;
    System.out.println(square);
}
// Neither i nor square can be referenced here
~~~

This is a snippet inside a method. `i` and `square` are local variables with different scopes. `i` belongs to the scope of the `for` construct; `square` belongs only to the loop body block. Each execution of the block can handle its own value of the local variable according to Java's semantic model.

### 10.4. A `final` Parameter Does Not Prevent Modifying the Object

~~~java
void rename(final StringBuilder builder) {
    builder.append("!");
    // builder = new StringBuilder(); // Invalid
}
~~~

The parameter `builder` cannot be reassigned if declared `final`, yet `append` can still modify the object that the reference points to. This is also an example showing that "a variable that cannot be reassigned" is different from "an immutable object".

### 10.5. Access Permissions Belong to Fields, Not Locals

`private`, `protected`, `public` apply to appropriate member declarations, such as fields. Do not place them on local variables or method parameters in the way fields are declared. Local variables can inherently only be referenced within the scope defined by the block, whereas a field is additionally governed by its access modifier and the class type that contains it.

## 11. Common Errors Table

| Error or misconception | Cause | Resolution |
| --- | --- | --- |
| `variable x might not have been initialized` | Reading a local variable before the compiler confirms it has been assigned | Assign a value on every execution path reaching the read point |
| Field `String name` is automatically `""` | Confusing the default value of a reference type | Remember that reference fields default to `null`; initialize when needed |
| Constructor `name = name;` does not update the field | A same-named parameter is shadowing the field | Use `this.name = name;` |
| `non-static variable ... cannot be referenced from a static context` | Using an instance field directly without an object inside a static method | Access it via an object reference, or make it static if the data truly belongs to the class |
| Modifying a parameter and expecting the caller's variable to change | Misunderstanding pass-by-value | Return the new value and assign it in the caller, or modify object state by design |
| Two objects use `static` and expect two independent values | `static` is a class field | Use an instance field for per-object data |
| Reading a local variable outside the closing `}` | The variable name is out of scope | Move where it is used or adjust the declaration scope appropriately |
| Redeclaring a parameter's name as a local variable in the same scope | Overlapping name scopes | Choose a different name, or reuse the already declared parameter |
| Lambda reports that a variable must be final/effectively final | The local/parameter is reassigned before or after capture | Redesign the data flow and use a variable that is not reassigned |
| Assuming `final List` is immutable | `final` only restricts reassigning the variable | Protect the data using an unmodifiable API or defensive copying |
| Using `var` to declare a field | Local variable type inference does not apply to fields | Write the field type explicitly, for example `private int count;` |
| Confusing scope with stack/heap memory | Java semantics do not require storing each variable at a fixed address | Rely on scope, how variables are assigned, and object references rather than guessing JVM layout |

## 12. Self-Check

**Question 1.** Given the declaration `private int counter;` at the top of a class and `int counter = 5;` inside a method, how many variables are there?  
**Answer:** There is one instance field and a separate local variable. Inside the method, the simple name `counter` usually refers to the local; `this.counter` refers to the field.

**Question 2.** Why can `int age;` in a class be read as `0`, whereas `int age;` in a method cannot be printed before being assigned?  
**Answer:** Fields are given a default value by Java; local variables must satisfy the definite assignment rule before every read.

**Question 3.** When calling `addPoints(3)`, what are the number `3` and `int points` in the method signature, respectively?  
**Answer:** `3` is the argument, while `points` is the parameter initialized from the argument.

**Question 4.** Does `void change(int x) { x = 100; }` modify the caller's variable `n` when `change(n)` is called?  
**Answer:** No. `x` is a copy of the value passed in; changing `x` does not automatically reassign `n`.

**Question 5.** Is `void add(final List<String> values) { values.add("A"); }` valid when passed a modifiable `ArrayList`?  
**Answer:** Yes. `final` prevents reassigning the parameter `values`, not modifying the contents of the referenced object.

**Question 6.** How can the field `private static int total;` and the local `int total = 5;` inside a static method be distinguished?  
**Answer:** The local uses the name `total`; access the field using `TênLớp.total` (subject to access permissions). Do not use `this` in a static method.

**Question 7.** A local variable is declared as `List<String> names = new ArrayList<>();`, used in a lambda, and then `names.add("B")` is called: does the local lose its effectively final status?  
**Answer:** No. The call to `add` modifies the list; it does not reassign the variable `names`. If you write `names = new ArrayList<>();`, then the variable is no longer effectively final.

## Conclusion

To distinguish the three kinds of variables correctly, look at **the declaration location first**: declared in the class body is a **field**, in the parameter list is a **parameter**, and in a method/block is a **local variable**. A field holds the state of an object or class and has a default value; a parameter is initialized from the argument when the call begins; a local variable must be definitely assigned before being read. Scope determines where a variable name can be used; `this.field` resolves cases where a name is shadowed; Java passes both primitive types and reference values **by value**. Mastering these principles helps constructors, methods, and lambdas work as expected.
