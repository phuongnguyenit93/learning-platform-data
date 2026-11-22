# Distinguishing `final`, `effectively final`, and immutability in Java

The three concepts **`final`**, **`effectively final`**, and **immutability** often appear together in Java, but they answer three different questions:

- **`final`**: Does Java **prohibit reassigning** a variable, field, or parameter; or prohibit overriding/inheriting a specific declaration?
- **`effectively final`**: Is a local variable or parameter **written without `final`**, yet actually assigned in such a way that the program would still be valid if `final` were added?
- **Immutable object**: After creation, can the **observable state** of an object be modified through valid APIs/aliases?

Example:

~~~java
final StringBuilder builder = new StringBuilder("Java");
builder.append(" Core"); // Valid: modifies the object's contents.
// builder = new StringBuilder(); // Invalid: reassigns a final variable.
~~~

`builder` is a **final reference variable**, whereas `StringBuilder` is a **mutable object**. Meanwhile:

~~~java
String name = "Mai";
Runnable greet = () -> System.out.println(name);
~~~

`name` is not declared `final` but is **effectively final**, so the lambda can capture it. The String value that `name` references is also immutable, but that is **a separate property of String**, not a consequence of being effectively final.

This lesson belongs to Java Core — **Class & Object / The final keyword**, using Java 17+. We will thoroughly examine everything from local variables, parameters, blank final fields, lambdas, and anonymous classes to object graphs, defensive copying, records, API design, and limitations in multithreaded programming.

## 1. Learning objectives

After studying, you will be able to:

1. Accurately explain `final` when applied to a **local variable, method parameter, instance field, static field, method, and class**.
2. Distinguish between **not being able to reassign a reference** and **not being able to modify an object**.
3. Determine when a local variable/parameter is **effectively final** according to Java rules.
4. Understand why local variables used by a lambda or local/anonymous inner class must be final/effectively final.
5. Predict whether assignments inside `if/else` or loops remain effectively final.
6. Distinguish between **final field**, **immutable class**, **shallow immutability**, and **deep immutability**.
7. Understand why `final List`, `final int[]`, and `record` do not automatically guarantee deep immutability.
8. Know how to use **defensive copy**, value objects, and read-only APIs when an object contains mutable references.
9. Understand the relationship between `final`, **constructor invariant**, **safe publication**, and **thread safety**, without making overstated claims.
10. Grasp the limits of `final` in inheritance/overriding and distinguish it from `static`.
11. Run Java 17+ programs yourself with stdout, and accurately predict valid lines and compiler errors.
12. Know how to choose between **in-place mutation**, **returning a new object**, and **a new local variable** in real-world code.

## 2. Core comparison table

| Aspect | `final` | `effectively final` | Immutable object |
| --- | --- | --- | --- |
| What is it? | A keyword in a Java declaration | A property of a local variable/parameter based on how it is assigned | A characteristic of object design |
| Mainly applies to | Variables, fields, parameters, methods, classes | Local variables and parameters, especially during capture | Instances and observable state |
| Prevents reassigning a variable? | Yes, after valid initialization | The variable is not actually reassigned according to the rules; the compiler does not lock it with a keyword | Not necessarily: a variable referencing an immutable object can still be reassigned |
| Prevents modifying a mutable object via an alias? | **No** | **No** | Yes, within the scope of the designed immutability contract |
| Requires writing a keyword? | Yes, `final` | No | Not necessarily; a class can guarantee immutability through its API |
| Lambda local capture? | Allowed if definite assignment is valid | Allowed | Immutability is not a required condition for capture |
| Can be applied to a class/method? | Yes | No | Refers to object/class design, not a modifier |
| Example | `final List<String> xs` | `int x = 1;` without reassignment | `String`, `LocalDate`, properly designed value objects |

**Rule to remember:** `final` and effectively final are mainly about **whether a storage location can be reassigned**. Immutability is about **the state of the referenced object**.

## 3. `final` on primitive variables

A `final` primitive variable cannot be assigned another value after it has been validly initialized.

~~~java
final int maxAttempts = 3;
// maxAttempts = 4; // Compilation error.
~~~

The variable `maxAttempts` holds the primitive value `int 3`; it is not a reference to a mutable object.

Valid usages:

~~~java
final double piApproximation = 3.14;
final boolean enabled = true;
final char grade = 'A';
~~~

Attempting to reassign, even assigning **the exact same value**, is still a prohibited assignment:

~~~java
final int x = 5;
// x = 5; // Still a compilation error.
~~~

Key point: `final` does not mean the compiler checks “whether the new value differs from the old value”. It prevents **invalid reassignments according to the definite assignment/final variable rules**.

### Increment/decrement also modifies the variable

~~~java
final int count = 10;
// count++;  // Error.
// ++count;  // Error.
// count += 2; // Error.
~~~

`++`, `--`, and compound assignment `+=` all attempt to update an already-final variable, even though there is no standalone `=` sign in the usual form.

## 4. `final` on reference variables: holding the reference, not freezing the object

Consider:

~~~java
final java.util.ArrayList<String> names =
        new java.util.ArrayList<>();

names.add("Mai");      // Valid.
names.add("An");       // Valid.
// names = new java.util.ArrayList<>(); // Error.
~~~

Logically:

~~~text
Variable names (final)
+--------------------+
| reference -> List#1|
+---------+----------+
          |
          v
      List#1 mutable
      ["Mai", "An"]
~~~

The variable `names` keeps the same reference to **List#1**, but the contents of List#1 can change. `final` does not prevent `names.clear()` or `names.set(0, "Binh")` if the List implementation allows it.

Another alias can also modify the same object:

~~~java
final StringBuilder text = new StringBuilder("A");
StringBuilder alias = text;
alias.append("B");
// text.toString() yields "AB".
~~~

`text` is never reassigned. The shared object is what gets modified. This is one of the most important distinctions in this lesson.

## 5. Runnable example: final primitive and final reference

Create the file **`FinalReferenceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class FinalReferenceDemo {
    public static void main(String[] args) {
        final int limit = 3;
        final List<String> names = new ArrayList<>();
        final StringBuilder builder = new StringBuilder("Java");

        names.add("Mai");
        names.add("An");
        builder.append(" Core");

        System.out.println("limit=" + limit);
        System.out.println("names=" + names);
        System.out.println("builder=" + builder);

        // limit = 4;                  // Error: final primitive.
        // names = new ArrayList<>();  // Error: final reference.
        // builder = new StringBuilder("X"); // Error.
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 FinalReferenceDemo.java
java FinalReferenceDemo
~~~

Stdout:

~~~text
limit=3
names=[Mai, An]
builder=Java Core
~~~

The result proves: **`final` on a reference does not prohibit calling mutators**. If immutable content is needed, you must choose an immutable type or an API that disallows state changes and prevents mutable aliases.

## 6. `final` on method parameters

A parameter can be declared `final`:

~~~java
static void printLength(final String text) {
    System.out.println(text.length());
    // text = "other"; // Compilation error.
}
~~~

Here, `final` prevents the method's code from **reassigning the parameter variable `text`**. It does not change the parameter-passing mechanism: Java is still **pass-by-value**, and for a reference parameter, the copied value is the **reference value**.

If the parameter points to a mutable object:

~~~java
static void appendSuffix(final StringBuilder builder) {
    builder.append("!");
    // builder = new StringBuilder(); // Error.
}
~~~

then `append` is valid because it modifies the **object**, without reassigning the **parameter**.

### A `final` parameter does not make a method pure

A method with a `final` parameter can still:

- Modify the mutable object that the parameter references.
- Change a static field.
- Write to a file or call a network API.
- Change the state of the receiving object via `this`.
- Throw an exception.

Therefore, `final` helps restrict **parameter rebinding**, rather than proving that “the method has no side effects”.

## 7. Blank final local variables: declare first, assign once

Java allows a **blank final local variable**: declaring `final` without assigning an initializer right on the declaration line.

~~~java
final int score;
score = 90;
System.out.println(score);
// score = 95; // Error: already assigned.
~~~

The key requirement is **definite assignment (DA)**: the compiler must prove that the variable is assigned before it is read; for a final variable, it must satisfy the rules for single assignment across the considered control-flow paths.

An if/else example:

~~~java
final String label;
if (score >= 50) {
    label = "PASS";
} else {
    label = "FAIL";
}
System.out.println(label);
~~~

Every path through the if/else structure assigns `label` once before `println`, so it is valid.

Conversely:

~~~java
final String label;
if (score >= 50) {
    label = "PASS";
}
// System.out.println(label); // Error: unassigned on some path.
~~~

It fails definite assignment when `score < 50`.

### Do not interpret “final = must be assigned on the declaration line”

A local `final` variable can be initialized later, provided it follows the **definite assignment/unassignment rules**. The key point is that an execution path is not allowed to reassign a final variable after it has already been validly assigned.

## 8. Runnable example: blank final across two branches

Save **`BlankFinalLocalDemo.java`**:

~~~java
public class BlankFinalLocalDemo {
    static String category(int score) {
        final String label;

        if (score >= 80) {
            label = "HIGH";
        } else if (score >= 50) {
            label = "PASS";
        } else {
            label = "RETRY";
        }

        return label;
    }

    public static void main(String[] args) {
        System.out.println(category(90));
        System.out.println(category(60));
        System.out.println(category(20));
    }
}
~~~

~~~bash
javac -encoding UTF-8 BlankFinalLocalDemo.java
java BlankFinalLocalDemo
~~~

Stdout:

~~~text
HIGH
PASS
RETRY
~~~

The variable `label` is declared final without an immediate value. Each time the method is called, the program takes **one branch** and assigns `label` exactly once. This code is valid even though the name `label` can receive different values **in different method calls**.

**Do not confuse this:** `final` applies only to **the variable within each call**; it does not turn `label` into an application-wide constant.

## 9. What is `effectively final`?

A local variable or parameter **not declared `final`** can be considered **effectively final** if the way it is assigned satisfies the condition that adding `final` to its declaration would not cause a compilation error related to assignment.

~~~java
String greeting = "Xin chào"; // Without final.
System.out.println(greeting);
// No reassignment to greeting.
~~~

`greeting` is effectively final. Therefore, it can be captured by a lambda or a local/anonymous class if other conditions are met.

**Effectively final is not a modifier:** There is no syntax:

~~~java
// effectively final int x = 1; // Invalid: Java does not have this modifier.
~~~

The compiler **infers** that property from the assignments in the source code.

### Why does Java have this concept?

Before Java 8, many situations where local variables were captured by anonymous inner classes required writing the `final` keyword. Starting with Java 8, an **effectively final** local variable or parameter is also sufficient for those capture scenarios under the current rules.

The goal is to reduce required syntax when a variable does not actually change, **not to allow a lambda to silently modify a local variable from the enclosing scope**.

## 10. Simple example: effectively final and lambdas

Create the file **`EffectivelyFinalLambdaDemo.java`**:

~~~java
public class EffectivelyFinalLambdaDemo {
    public static void main(String[] args) {
        String prefix = "Xin chào";
        String person = "Mai";

        Runnable task = () ->
                System.out.println(prefix + ", " + person + "!");

        task.run();
        task.run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 EffectivelyFinalLambdaDemo.java
java EffectivelyFinalLambdaDemo
~~~

Stdout:

~~~text
Xin chào, Mai!
Xin chào, Mai!
~~~

`prefix` and `person` are written without `final`, yet both are assigned at declaration and **not reassigned**, so they are effectively final. The lambda uses them validly.

If you add:

~~~java
person = "An";
~~~

into the method containing the lambda that captures `person` above, the compiler rejects it: a local variable referenced from a lambda must be **final or effectively final**. It does not matter whether the reassignment line appears before or after the `task.run()` call; the compiler evaluates this property across the source code, not just along an execution path that the author assumes “will run”.

## 11. Why does reassigning a variable make it no longer effectively final?

Consider:

~~~java
int amount = 10;
amount = 20;

Runnable task = () -> System.out.println(amount);
~~~

This is **a snippet intentionally written not to compile**. `amount` has an initializer of 10 and is then reassigned 20. It is not effectively final, so it cannot be captured by the lambda.

Changing it to:

~~~java
final int amount = 20;
Runnable task = () -> System.out.println(amount);
~~~

or:

~~~java
int amount = 20;
Runnable task = () -> System.out.println(amount);
~~~

are both valid. **The core point** is that the captured local variable is not reassigned after initialization according to the rules.

### Can a local variable not declared final be captured if it is assigned later?

Yes. A local variable that is not initialized on its declaration line can be effectively final if it is **assigned once on valid paths** and satisfies definite assignment before being used.

Example:

~~~java
String message;

if (System.getProperty("mode") == null) {
    message = "DEFAULT";
} else {
    message = "CONFIGURED";
}

Runnable task = () -> System.out.println(message);
~~~

This illustrative snippet compiles: `message` has no initializer, is assigned by exactly one if/else branch on each path, and is not reassigned afterward. Do not confuse this with the case where it is **already assigned at declaration** and then assigned again.

## 12. Runnable example: effectively final even when assigned in branches

Save **`EffectivelyFinalBranchesDemo.java`**:

~~~java
public class EffectivelyFinalBranchesDemo {
    static Runnable createGreeting(boolean formal) {
        String greeting;

        if (formal) {
            greeting = "Kính chào";
        } else {
            greeting = "Chào";
        }

        return () -> System.out.println(greeting + " bạn!");
    }

    public static void main(String[] args) {
        Runnable formal = createGreeting(true);
        Runnable informal = createGreeting(false);

        formal.run();
        informal.run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 EffectivelyFinalBranchesDemo.java
java EffectivelyFinalBranchesDemo
~~~

Stdout:

~~~text
Kính chào bạn!
Chào bạn!
~~~

In each call to `createGreeting`, the variable `greeting` is assigned a value according to the corresponding branch. Afterward, it **is not reassigned**. The returned lambda retains the needed value even after the `createGreeting` call has finished.

The result does not mean the lambda holds a reference to a local variable that can still be arbitrarily updated later. It performs capture according to Java's semantics for eligible local values.

## 13. Effectively final identification table

| Local code snippet | Effectively final? | Reason |
| --- | --- | --- |
| `int n = 1;` and not reassigned | Yes | Only one assignment at initialization |
| `int n = 1; n = 2;` | No | There is a second assignment |
| `int n = 1; n++;` | No | Increment updates the variable |
| `int n; n = 1;` and not reassigned | Yes if DA is satisfied | Blank local assigned once |
| `int n; if (flag) n=1; else n=2;` | Yes if DA is satisfied | Each branch assigns once |
| `int n=1; if(flag) n=2;` | No | Already has an initializer, yet still has a path that assigns again |
| `List<String> xs = new ArrayList<>(); xs.add("A");` | Possibly yes | Does not reassign **xs**, only modifies the object |
| `int[] a={1}; a[0]=2;` | Possibly yes | Does not reassign variable `a` |
| `StringBuilder b=new StringBuilder(); b.append("X");` | Possibly yes | Only modifies the object |
| Parameter `int n` not reassigned | Yes | Parameter is effectively final |
| Parameter `int n; n++;` inside method | No | Parameter is updated |

**“Possibly yes”** emphasizes that you need to check **the entire relevant code**: if the variable is reassigned somewhere else, the conclusion changes.

### Special case: updating a field differs from updating a local variable

~~~java
class Counter {
    int value;

    void run() {
        Counter target = this;
        target.value++; // target is still effectively final.
    }
}
~~~

The variable `target` still keeps the same reference value, while the `value` field of the Counter object has changed.

## 14. Effectively final for a method parameter

A parameter written without `final` that is not reassigned inside the method can be effectively final:

~~~java
static Runnable report(int value) {
    return () -> System.out.println(value);
}
~~~

This is an illustrative method that can be placed inside a valid class. `value` is effectively final, so the returned lambda can still use it.

Counterexample:

~~~java
static Runnable invalid(int value) {
    value++;
    // return () -> System.out.println(value); // Error if uncommented.
    return () -> System.out.println("not captured");
}
~~~

The `value++` line makes the parameter not effectively final, even though the declaration syntax does not have `final`.

### Comparison with a `final` parameter

~~~java
static Runnable report(final int value) {
    return () -> System.out.println(value);
}
~~~

Also valid. When there is no reassignment, **including or omitting `final` does not change the printed value**. `final` is useful for making the constraint explicit right at the declaration and causing the compiler to reject reassignments added later.

## 15. Lambda capturing a local variable and modifying a mutable object

A lambda can capture an **effectively final reference variable** and still modify the object that the variable references:

~~~java
StringBuilder builder = new StringBuilder("A");

Runnable append = () -> builder.append("B");
append.run();
append.run();

System.out.println(builder);
~~~

The snippet prints `ABB` when placed in a valid main method. `builder` is not reassigned; the StringBuilder object has its state changed twice.

Therefore:

> **Lambda capture requires the local variable to be final/effectively final, not that the captured object be immutable.**

This also explains why a lambda can modify an `AtomicInteger` or an object's field, but cannot directly reassign a local variable from the enclosing scope.

## 16. Runnable example: lambda updating a captured object

Save the file **`CapturedMutableObjectDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CapturedMutableObjectDemo {
    public static void main(String[] args) {
        List<String> events = new ArrayList<>();

        Runnable first = () -> events.add("A");
        Runnable second = () -> events.add("B");

        first.run();
        second.run();

        System.out.println(events);
        System.out.println("size=" + events.size());

        // events = new ArrayList<>(); // If uncommented, capture error:
        // events would no longer be effectively final.
    }
}
~~~

~~~bash
javac -encoding UTF-8 CapturedMutableObjectDemo.java
java CapturedMutableObjectDemo
~~~

Stdout:

~~~text
[A, B]
size=2
~~~

`events` is effectively final, so it can be captured. Both lambdas use the same List reference. Calling `add` modifies the object, without reassigning `events`.

**Note on concurrency:** If you run these two lambdas on two threads instead of calling them sequentially as in the example, ArrayList does not automatically become thread-safe just because the reference is effectively final. You need synchronization/a concurrent collection or a proper ownership design.

## 17. Local classes and anonymous classes also have capture rules

It is not just lambdas. A **local class** or **anonymous inner class** can reference local variables/parameters from the enclosing scope when they are final or effectively final according to Java rules.

Java 17 example:

~~~java
int prefix = 10;

java.util.function.IntSupplier supplier =
        new java.util.function.IntSupplier() {
            @Override
            public int getAsInt() {
                return prefix + 2;
            }
        };
~~~

`prefix` is written without final, yet is not reassigned, so the anonymous class can use it.

This is not a lambda; the syntax creates an instance of an anonymous class. Both capture mechanisms have rules related to effectively final, but **`this` in a lambda and `this` in an anonymous class are different**:

- A lambda does not create its own meaning of `this` like an anonymous class instance; `this`, if valid, points to the enclosing instance.
- Inside an anonymous class, `this` points to the anonymous class instance.

Do not use the similarity in capture rules to infer that all dispatch/`this` mechanisms are the same.

## 18. Runnable example: anonymous class capturing effectively final variables

Create **`AnonymousCaptureDemo.java`**:

~~~java
import java.util.function.IntSupplier;

public class AnonymousCaptureDemo {
    static IntSupplier multiplyBy(int factor) {
        int adjustment = 1;

        return new IntSupplier() {
            @Override
            public int getAsInt() {
                return factor * 3 + adjustment;
            }
        };
    }

    public static void main(String[] args) {
        IntSupplier supplier = multiplyBy(4);
        System.out.println("result=" + supplier.getAsInt());
    }
}
~~~

~~~bash
javac -encoding UTF-8 AnonymousCaptureDemo.java
java AnonymousCaptureDemo
~~~

Stdout:

~~~text
result=13
~~~

`factor` is an effectively final parameter; `adjustment` is an effectively final local variable. The returned anonymous class can use both after `multiplyBy` has finished.

If you add the assignment `adjustment = 2;` inside the method, that variable loses its effectively final status and accessing it inside the anonymous class does not compile.

## 19. For-loops: a changing variable cannot be captured directly

This snippet is intentionally invalid:

~~~java
for (int i = 0; i < 3; i++) {
    // Runnable task = () -> System.out.println(i); // Error:
    // i increments via i++, so it is not effectively final.
}
~~~

The variable `i` of a traditional for-loop is updated in every iteration. To create a lambda that holds **the current iteration's value**, use a new local variable:

~~~java
for (int i = 0; i < 3; i++) {
    final int snapshot = i;
    Runnable task = () -> System.out.println(snapshot);
    task.run();
}
~~~

Here, `snapshot` is assigned once per iteration/body execution and is not reassigned.

### For-each differs

~~~java
for (String name : java.util.List.of("Mai", "An")) {
    Runnable task = () -> System.out.println(name);
    task.run();
}
~~~

An enhanced-for variable can qualify as effectively final **in each iteration** if it is not reassigned in the body. Therefore, it can be captured by a lambda under Java rules, even though successive iterations have a different `name`.

## 20. Runnable example: creating a list of lambdas per iteration

Create **`LoopCaptureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class LoopCaptureDemo {
    public static void main(String[] args) {
        List<Runnable> actions = new ArrayList<>();

        for (int i = 0; i < 3; i++) {
            int snapshot = i;
            actions.add(() -> System.out.println("index=" + snapshot));
        }

        for (String name : List.of("Mai", "An")) {
            actions.add(() -> System.out.println("name=" + name));
        }

        for (Runnable action : actions) {
            action.run();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 LoopCaptureDemo.java
java LoopCaptureDemo
~~~

Stdout:

~~~text
index=0
index=1
index=2
name=Mai
name=An
~~~

Each iteration creates a local `snapshot` that is not reassigned. In the enhanced-for loop, `name` also satisfies the capture condition. The Runnables are stored and only invoked **after the loops creating actions finish**, yet they still print the values corresponding to the iteration in which they were created.

## 21. When you need to update a counter inside a lambda

Because a captured local variable must be effectively final, the following snippet is invalid:

~~~java
int count = 0;
// Runnable increment = () -> count++; // Capture error.
~~~

There are several alternative designs:

1. **Use the pipeline result** if possible: `stream.filter(...).count()` or `mapToInt(...).sum()`.
2. **Use a mutable accumulator object** in sequential code when that is a clear choice.
3. **Use `AtomicInteger`** if atomic updates are needed and the contract fits, but do not use it merely to bypass the compiler without understanding state sharing.
4. **Use an instance field** if the counter belongs to an object with a clear lifetime.
5. **Write a regular for-loop** if logic that mutates local state is clearer than a lambda.

### Example of an accumulator via an object

~~~java
java.util.concurrent.atomic.AtomicInteger count =
        new java.util.concurrent.atomic.AtomicInteger();

java.util.List.of("A", "B", "C").forEach(
        item -> count.incrementAndGet());

System.out.println(count.get());
~~~

The snippet above prints `3` when placed inside a method. The variable `count` remains effectively final; the **AtomicInteger object** is updated. This illustrates the mechanism, not a recommendation to replace every local int with an AtomicInteger.

If there is no concurrency, a for-loop with `int count` is usually easier to read. If there is concurrency, a single AtomicInteger does not by itself make all operations on a dataset and all multi-variable invariants atomic.

## 22. What is immutability?

An object is considered **immutable** when its observable state **does not change after the object is validly constructed**, according to the public contract of that type.

Example with `String`:

~~~java
String text = "Java";
String other = text;
text = text + " Core";
~~~

The original `String` with content `"Java"` is not modified. `text` is assigned a reference to the resulting String, while `other` continues referencing the old String.

Distinguish:

- **Immutable object**: the state of the object itself is not modified through the provided operations.
- **Final variable**: a variable cannot be reassigned after it has been validly initialized.
- **Effectively final variable**: a non-final local/parameter that is not reassigned according to the rules.
- **Reference to a mutable object**: can hold a fixed reference while still changing the object's state.

An immutable object can be referenced through a **non-final variable**:

~~~java
String text = "A";
text = "B"; // Valid: non-final variable.
~~~

This operation does not make the String object `"A"` mutable.

## 23. Runnable example: immutable String, mutable StringBuilder

Save **`ImmutableVsMutableDemo.java`**:

~~~java
public class ImmutableVsMutableDemo {
    public static void main(String[] args) {
        final String first = "A";
        String stringAlias = first;

        String result = first.concat("B");
        System.out.println("first=" + first);
        System.out.println("alias=" + stringAlias);
        System.out.println("result=" + result);

        final StringBuilder builder = new StringBuilder("A");
        StringBuilder builderAlias = builder;
        builder.append("B");

        System.out.println("builder=" + builder);
        System.out.println("builderAlias=" + builderAlias);
        System.out.println("sameBuilder=" + (builder == builderAlias));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ImmutableVsMutableDemo.java
java ImmutableVsMutableDemo
~~~

Stdout:

~~~text
first=A
alias=A
result=AB
builder=AB
builderAlias=AB
sameBuilder=true
~~~

`first.concat("B")` does not modify the original String; it produces a resulting String with contents `"AB"`. `StringBuilder.append("B")` modifies the state of the StringBuilder object, so the alias also sees `"AB"`.

**Do not conclude that “`final` makes String immutable”.** `String` already has immutable semantics even when the variable referencing it is not final.

## 24. Basic immutable class design

An immutable value object typically has:

1. A `final` class or a strategy preventing subclasses from breaking invariants/immutability.
2. `private final` fields.
3. Data validation and normalization in the constructor/factory.
4. No mutators that change state after initialization.
5. No exposure of mutable fields or references that could alter state from the outside.
6. If it has mutable nested data, **defensive copy** or an appropriate ownership strategy.
7. Do not let `this` escape from the constructor before initialization is complete.

Example:

~~~java
public final class Temperature {
    private final double celsius;

    public Temperature(double celsius) {
        if (!Double.isFinite(celsius)) {
            throw new IllegalArgumentException("finite temperature required");
        }
        this.celsius = celsius;
    }

    public double celsius() {
        return celsius;
    }

    public Temperature plus(double delta) {
        return new Temperature(celsius + delta);
    }
}
~~~

This is **a standalone class without main**. `plus` creates a new object instead of modifying the old one. The constructor checks `Double.isFinite`, so if addition produces infinity or NaN, the constructor throws an exception instead of creating an invalid Temperature.

### Must all immutable classes be final?

Not every immutable design **requires** using a `final class`, but `final` is a simple way to prevent subclasses from adding mutable behavior that breaks assumptions about the object. If a class is open for inheritance, you must carefully control contracts, state exposure, and overridable methods. For small value objects, a `final class` or a Java `record` usually makes the intent clear.

## 25. Runnable example: an immutable value object returning a new copy

Create the file **`ImmutableCounterDemo.java`**:

~~~java
public class ImmutableCounterDemo {
    static final class Counter {
        private final int value;

        Counter(int value) {
            if (value < 0) {
                throw new IllegalArgumentException("negative value");
            }
            this.value = value;
        }

        Counter increment() {
            return new Counter(Math.addExact(value, 1));
        }

        int value() {
            return value;
        }
    }

    public static void main(String[] args) {
        Counter first = new Counter(1);
        Counter second = first.increment();
        Counter third = second.increment();

        System.out.println("first=" + first.value());
        System.out.println("second=" + second.value());
        System.out.println("third=" + third.value());
        System.out.println("same=" + (first == second));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ImmutableCounterDemo.java
java ImmutableCounterDemo
~~~

Stdout:

~~~text
first=1
second=2
third=3
same=false
~~~

`first.increment()` does not modify the `first` object. It creates `second` with value 2, and then `third` with value 3. `first == second` is false because these are two separate objects. The example shows that **immutable design can go hand in hand with `final` fields**, but the “no state mutation” meaning comes from **an API that returns a new object** and does not expose mutators.

## 26. Shallow immutability and deep immutability

A class whose fields are all `final` can still be modified **indirectly** through a mutable object graph:

~~~java
class Team {
    private final java.util.List<String> names;

    Team(java.util.List<String> names) {
        this.names = names;
    }

    java.util.List<String> names() {
        return names;
    }
}
~~~

Even though `names` is private final:

- The constructor keeps **the same List reference** that the caller passed in.
- The caller can call `source.add("An")`, and then Team observes the new element.
- The getter returns the mutable List directly; the caller can call `team.names().clear()`.
- The field was never reassigned, yet **the state observed by Team** has changed.

### Deep immutability requires considering every level

~~~text
Team object
  final names -------> List object (mutable)
                         |
                         +-- "Mai" (immutable String)
                         +-- "An"  (immutable String)
~~~

If we use `List.copyOf(names)` and the elements are immutable Strings, we prevent structural mutation of the List through ordinary paths and avoid aliasing the mutable source List. If the elements are `Student` objects with setters, copying the list **does not** deep-copy the Students.

You should not claim that “`List.copyOf` makes every object inside immutable”. It only provides guarantees at the **container level** according to its contract.

## 27. Runnable example: defensive copy when receiving and returning data

Save **`DefensiveCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class DefensiveCopyDemo {
    static final class Team {
        private final List<String> names;

        Team(List<String> input) {
            names = List.copyOf(input);
        }

        List<String> members() {
            return names;
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("Mai");

        Team team = new Team(input);
        input.add("An");

        System.out.println("input=" + input);
        System.out.println("team=" + team.members());

        try {
            team.members().add("Binh");
        } catch (UnsupportedOperationException ex) {
            System.out.println("cannot edit team list");
        }

        System.out.println("team again=" + team.members());
    }
}
~~~

~~~bash
javac -encoding UTF-8 DefensiveCopyDemo.java
java DefensiveCopyDemo
~~~

Stdout:

~~~text
input=[Mai, An]
team=[Mai]
cannot edit team list
team again=[Mai]
~~~

Here `List.copyOf(input)` rejects a null source/null elements and creates/obtains a list that cannot be modified via ordinary mutators. The list stored in Team is unaffected by adding An to `input` after initialization. Because the elements are immutable `String` values, the example avoids the risk of modifying elements through an alias.

**Do not claim that `List.copyOf` always allocates a new object**: it may reuse a suitable unmodifiable list. The structural immutability contract is what matters.

## 28. `final` arrays are an easy-to-confuse case

~~~java
final int[] scores = {80, 90};
scores[0] = 100; // Valid.
// scores = new int[] {70, 60}; // Error: reassigns the reference.
~~~

An array object always has mutable elements; `final` only protects **the `scores` variable**.

If you need a class that does not expose the array:

~~~java
final class ScoreBoard {
    private final int[] scores;

    ScoreBoard(int[] input) {
        scores = input.clone();
    }

    int[] snapshot() {
        return scores.clone();
    }
}
~~~

This is an illustrative class. When using `int[]`, clone copies primitive elements, so the snapshot array has an independent structure. However, with `Person[]`, clone only copies the **references to Person objects**; it does not deep-copy each Person.

### An immutable class must avoid returning a mutable array directly

~~~java
int[] getScores() {
    return scores; // If the raw private array is returned, the caller can modify it.
}
~~~

Even when the field is `private final`, the getter above opens a path to mutation. A defensive copy is usually needed at both the **input boundary and the output boundary**.

## 29. Java `record`: shallowly immutable, not automatically deeply immutable

Java 17 has records:

~~~java
record Point(int x, int y) {}
~~~

A record has final component fields and accessor methods; `Point` is well suited as a value object containing primitive components.

However:

~~~java
record Roster(java.util.List<String> names) {}
~~~

the `names` component is a **reference**. If the caller passes a mutable ArrayList and the accessor returns that reference, the content can still change after record construction.

### How to handle a record containing a List

~~~java
record SafeRoster(java.util.List<String> names) {
    SafeRoster {
        names = java.util.List.copyOf(names);
    }
}
~~~

The compact constructor replaces the component parameter reference with a structurally unmodifiable list, and Java initializes the component field from the parameter after the constructor body according to record compact constructor rules. With immutable String elements, this approach helps protect the state of Roster.

**Do not conclude that every component object is immutable just because a record has final fields**. A record only conveniently supports building data carriers; invariants/deep immutability still need to be designed.

## 30. Runnable example: a record needing to protect a mutable component

Save **`RecordImmutabilityDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RecordImmutabilityDemo {
    record Roster(List<String> names) {
        Roster {
            names = List.copyOf(names);
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("Mai");

        Roster roster = new Roster(input);
        input.add("An");

        System.out.println("input=" + input);
        System.out.println("record=" + roster.names());

        try {
            roster.names().clear();
        } catch (UnsupportedOperationException ex) {
            System.out.println("record list cannot be cleared");
        }

        System.out.println("record again=" + roster.names());
    }
}
~~~

~~~bash
javac -encoding UTF-8 RecordImmutabilityDemo.java
java RecordImmutabilityDemo
~~~

Stdout:

~~~text
input=[Mai, An]
record=[Mai]
record list cannot be cleared
record again=[Mai]
~~~

The `Roster` record uses a compact constructor to obtain a structurally unmodifiable list. `input` is subsequently modified, yet `roster.names()` still returns `[Mai]`. The caller cannot successfully invoke `clear()` on the returned list.

This is shallow containment suitable for immutable String elements. If it is a List containing mutable elements, you must continue inspecting deeper layers.

## 31. `final` on instance fields

An **instance final field** must be initialized properly according to constructor/initializer rules; afterward, normal Java source code cannot reassign the field. Example:

~~~java
class User {
    private final String id;
    User(String id) {
        this.id = java.util.Objects.requireNonNull(id);
    }
}
~~~

This is a **blank final field**, distinct from an effectively final local variable captured by a lambda. B144–B145 cover in depth the analysis of all initialization branches and locations for assigning final fields; in this lesson, you only need to grasp the difference between **a field assigned once** and **a local variable that is not reassigned but written without final**.

## 32. Static final fields: constants and limits

`static final` combines **a class-level field** with **a non-reassignable binding**. Only certain final variables of primitive/`String` types initialized with a constant expression are **constant variables** according to the JLS; not every `static final` is inlined.

~~~java
static final int MAX_RETRIES = 3;
static final java.time.LocalDate START =
        java.time.LocalDate.of(2026, 1, 1);
~~~

The first line is a compile-time constant candidate, while the second is computed during runtime initialization. B147 is where constant expressions, switch/annotations, class initialization, and binary inlining are thoroughly analyzed; here we only draw the boundary with immutability.

## 33. `final` methods: prohibiting overriding, not overloading

`final` on an **instance method** prevents subclasses from overriding that method, but does not prevent declaring another overload; `final` does not prove a method is pure or free of side effects.

~~~java
class Parent {
    final void work() {}
    void work(String context) {}
}
~~~

Both distinct signatures are valid. A final method does not make the object immutable either. B149 is where you learn thoroughly about overriding, static hiding, template method, sealed hierarchies, polymorphism, and when to lock extension points.

## 34. `final` classes: prohibiting inheritance, not automatically immutable

A `final class` prohibits another class from using `extends` on it, **without automatically locking its state**:

~~~java
final class Counter {
    private int value;
    void increment() { value++; }
}
~~~

Even though Counter cannot be subclassed, calling `increment()` still changes the field value. Conversely, an immutable object can exist while the variable referencing it is not final. The difference between an **inheritance contract** and a **data immutability contract** is the core point; B149 teaches final methods/classes in detail.

## 35. Runnable example: a final class is still mutable

Create **`FinalClassMutableDemo.java`**:

~~~java
public class FinalClassMutableDemo {
    static final class Counter {
        private int value;

        void increment() {
            value++;
        }

        int value() {
            return value;
        }
    }

    public static void main(String[] args) {
        final Counter counter = new Counter();
        counter.increment();
        counter.increment();

        System.out.println("count=" + counter.value());
        System.out.println("type final=" +
                java.lang.reflect.Modifier.isFinal(
                        counter.getClass().getModifiers()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 FinalClassMutableDemo.java
java FinalClassMutableDemo
~~~

Stdout:

~~~text
count=2
type final=true
~~~

Here there are **two places using `final`**:

1. The nested class `Counter` is final, so it cannot be subclassed.
2. The local variable `counter` is final, so it cannot be assigned a new reference.

Neither **prohibits** calling `increment()` to change the `value` field of the Counter instance.

## 36. `final` and object identity / equality

A final variable keeps **the same reference** after valid initialization, but identity does not mean immutable state.

~~~java
final StringBuilder first = new StringBuilder("A");
StringBuilder alias = first;

alias.append("B");

System.out.println(first == alias); // true
System.out.println(first);          // AB
~~~

Conversely, two immutable values can be equal according to `equals()` while being two objects with different identities:

~~~java
String first = new String("Java");
String second = new String("Java");

System.out.println(first == second);      // false
System.out.println(first.equals(second)); // true
~~~

`String.equals` compares contents. **Do not use `final` to infer `==` or equality**. Identity, value equality, and immutability are different axes.

### Immutable objects can be shared more safely

If an object is truly immutable, multiple variables/threads can read it together without worrying about an alias directly changing the object's state. However, **how the reference and related data are published** must still follow appropriate memory-model/visibility rules; immutability is not immunity against all concurrency bugs.

## 37. `final` fields and the Java Memory Model: understanding just enough

Java provides special guarantees about **final fields** in the Java Memory Model. If an object is constructed properly and **`this` does not escape before the constructor finishes**, the initialized values of final fields have important initialization visibility guarantees for other threads observing the object.

However, you must not draw overly strong conclusions:

- **`final` does not make `count++` atomic**.
- **`final` does not turn a mutable List into a thread-safe one**.
- **Post-constructor** modifications to a mutable object referenced by a final field still require proper visibility/synchronization if shared across threads.
- Multiple related fields may still require a lock/immutable snapshot to ensure consistency.
- If the object or `this` is published while the constructor has not yet completed, safe-construction assumptions can be broken.
- Reflection/deserialization/unsafe mechanisms may have special rules or risks beyond this simple style of code.

### Example of a final reference holding a mutable object

~~~java
class SharedState {
    final java.util.List<String> values =
            new java.util.ArrayList<>();

    void add(String value) {
        values.add(value);
    }
}
~~~

If multiple threads concurrently call `add` on a SharedState instance, `ArrayList` is not thread-safe just because the `values` field is final. You need a concurrency design, ownership, or immutable copy.

**Practical takeaway:** Final fields help make object design safer and easier to reason about, but **thread safety is a property of all operations and state sharing as a whole**, not a single keyword.

## 38. Is `final` a constant?

A **final variable** is restricted from reassignment; a **compile-time constant variable** must additionally satisfy JLS conditions regarding primitive/`String` type and constant expressions.

~~~java
final int runtime = Integer.parseInt("42");
~~~

`runtime` is valid and final, but its value is determined at runtime. If you need “today's date”, `static final LocalDate TODAY = LocalDate.now()` only captures the date when the class is initialized, and does not automatically change at midnight. B147 thoroughly distinguishes compile-time/runtime constants, while here you must not infer that `final` means “immutable object”.

## 39. A final reference can still be `null`

`final String name = null;` is valid under assignment rules, but it does not mean `name` is non-null or safe to call methods on. `final` and null validation are two independent conditions. When the domain requires non-null, use `Objects.requireNonNull` in the constructor/factory and have tests for invalid input. Do not confuse a final reference with an already-created object.

## 40. Final and defensive copies when a constructor receives mutable input

When a `final` field holds a reference to mutable data provided by the caller, the constructor should **copy-in** and the getter should provide a representation that prevents the caller from modifying internal state.

~~~java
final class Schedule {
    private final java.util.Date date;
    Schedule(java.util.Date date) {
        this.date = new java.util.Date(
                java.util.Objects.requireNonNull(date).getTime());
    }
    java.util.Date date() {
        return new java.util.Date(date.getTime());
    }
}
~~~

Both copies prevent aliases from directly modifying the internal `Date`. `List.copyOf` only copies **the collection structure**; it does not deep-copy mutable elements. Aliasing, view/snapshot, and ownership scenarios are taught in depth in lesson B146.

## 41. Runnable example: a mutable Date needs copying despite a final field

Create the file **`FinalDateDefensiveCopyDemo.java`**:

~~~java
import java.util.Date;

public class FinalDateDefensiveCopyDemo {
    static final class Snapshot {
        private final Date captured;

        Snapshot(Date source) {
            if (source == null) {
                throw new IllegalArgumentException("source required");
            }
            captured = new Date(source.getTime());
        }

        Date captured() {
            return new Date(captured.getTime());
        }
    }

    public static void main(String[] args) {
        Date source = new Date(1_000L);
        Snapshot snapshot = new Snapshot(source);

        source.setTime(2_000L);

        Date outgoing = snapshot.captured();
        outgoing.setTime(3_000L);

        System.out.println("source=" + source.getTime());
        System.out.println("outgoing=" + outgoing.getTime());
        System.out.println("snapshot=" + snapshot.captured().getTime());
    }
}
~~~

~~~bash
javac -encoding UTF-8 FinalDateDefensiveCopyDemo.java
java FinalDateDefensiveCopyDemo
~~~

Stdout:

~~~text
source=2000
outgoing=3000
snapshot=1000
~~~

`source` is the caller's mutable Date; `Snapshot` copies the time value upon creation. The getter returns a new Date, so modifying `outgoing` does not change the internal Date state either. As a result, Snapshot preserves the meaning of “a snapshot of the instant 1000 milliseconds since the epoch” in this example.

Do not claim that every mutable type can be safely deep-copied with a simple constructor. For object graphs with aliases/cycles/resources, a specific ownership and copying policy must be designed.

## 42. An object graph may only be partially immutable

An object graph may only be **shallow immutable**: a `final List<Student>` field and `List.copyOf(source)` prevent changing the reference/list structure, yet a mutable `Student` can still be modified through an alias.

Therefore, state the contract clearly: fully immutable, immutable container, or controlled mutation? If deep immutability is required, choose immutable element types, deep copies, or appropriate ownership management. B146 analyzes aliasing/snapshot levels in depth; the specific point here is that **a captured variable being effectively final** does not solve mutation inside the object graph.

## 43. When should you use `final` without requiring immutability?

Choose `final` even when the object is still mutable when you want to keep a **binding** stable, such as an ID, dependency, private List field, local snapshot, or constructor parameter. That does not force every entity to be immutable: a `private final List<String> items = new ArrayList<>();` can still be modified through controlled methods.

Conversely, use **immutable value objects** and defensive copies when sharing multiple aliases, passing results between threads, or using them as keys. B150 applies all final choices to class design decisions; you should not add final according to a mechanical ratio or pattern.

## 44. When should you prefer immutable objects?

Immutable objects are especially well suited for:

- **Value objects** such as Money, Quantity, DateRange, and Address with a fixed contract.
- Configurations that do not change during the lifecycle of an operation.
- Data exchanged between threads when no post-creation mutation is needed.
- Snapshots, audit records, and keys in a map/set when equality/hashCode is based on state.
- Values that have multiple aliases and where you want to avoid unexpected side effects.
- Pure functions whose results are built from input.

You should weigh the tradeoffs: creating new objects can incur allocation/copying overhead; large models can use immutable persistent data structures or caching. However, **do not assume immutability is always slow** — the JVM has many optimizations, and the benefits in reasoning/testability are often significant.

If an object requires a clearly changing lifecycle, you can use an **encapsulated mutable entity** combined with immutable value objects instead of trying to force every entity to be immutable.

## 45. Common compiler errors

| Scenario | Error form / reason |
| --- | --- |
| Reassigning `final int x` | Cannot assign a value to final variable |
| `final int x;` read before assignment | Variable might not have been initialized |
| Blank final field not assigned in a valid constructor | Might not have been initialized |
| Lambda capturing a reassigned local variable | Local variables referenced from lambda expression must be final or effectively final |
| Anonymous class capturing a reassigned local variable | Local variables referenced from an inner class must be final or effectively final |
| Overriding a final method | Cannot override final method |
| Using `extends` on a final class | Cannot inherit from final class |
| Incompatible `final` and `abstract` on the same class/method | Illegal combination of modifiers |
| `final` constructor | Modifier final not allowed for constructor |
| `final` field assigned in an initializer and again in a constructor | Cannot assign a value to final variable |

Actual messages may vary by compiler/version. Check **where and how many times the variable is assigned, and whether it is a local/field/parameter or a method/class**, then fix it according to the semantics.

### How to fix lambda capture errors

If a local variable needs to change before creating the lambda:

~~~java
int mutable = 1;
mutable++;
int snapshot = mutable;
Runnable task = () -> System.out.println(snapshot);
~~~

`mutable` is not effectively final, whereas `snapshot` is a new local variable assigned once. The lambda captures `snapshot`. If the intent is for the lambda to read state that **changes over time**, you should use a state-holder object with clear ownership/synchronization instead of trying to work around the compiler with hard-to-read tricks.

## 46. Runnable example: snapshotting a variable before a lambda

Create **`LambdaSnapshotDemo.java`**:

~~~java
public class LambdaSnapshotDemo {
    public static void main(String[] args) {
        int counter = 1;
        counter++;

        final int captured = counter;
        Runnable task = () -> System.out.println("captured=" + captured);

        counter++;
        task.run();

        System.out.println("counter=" + counter);
    }
}
~~~

~~~bash
javac -encoding UTF-8 LambdaSnapshotDemo.java
java LambdaSnapshotDemo
~~~

Stdout:

~~~text
captured=2
counter=3
~~~

`counter` is updated multiple times, so it is not effectively final. `captured` is a final local variable assigned once with the value `2`. The lambda reads `captured`, while `counter` is later incremented to `3`. These are **two distinct primitive variables**, not two references to the same mutable object.

If `captured` is a reference to a mutable object, snapshotting the reference can still reveal changes to the object's state. To snapshot immutable contents, an appropriate copy is needed.

## 47. Comprehensive example: all three concepts in one program

Create the file **`FinalEffectivelyImmutableSummaryDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class FinalEffectivelyImmutableSummaryDemo {
    record Label(String text) {
        Label {
            if (text == null || text.isBlank()) {
                throw new IllegalArgumentException("text required");
            }
        }
    }

    public static void main(String[] args) {
        final List<String> mutableList = new ArrayList<>();
        String suffix = "!";

        Runnable add = () -> mutableList.add("Java" + suffix);
        add.run();

        Label immutableLabel = new Label("CORE");
        Label another = new Label(immutableLabel.text() + " 17");

        System.out.println("list=" + mutableList);
        System.out.println("first label=" + immutableLabel.text());
        System.out.println("another=" + another.text());

        // mutableList = new ArrayList<>(); // Not allowed: final.
        // suffix = "?"; // If uncommented, lambda capture error.
    }
}
~~~

~~~bash
javac -encoding UTF-8 FinalEffectivelyImmutableSummaryDemo.java
java FinalEffectivelyImmutableSummaryDemo
~~~

Stdout:

~~~text
list=[Java!]
first label=CORE
another=CORE 17
~~~

Three corresponding points:

1. `mutableList` is a **final reference**, yet the ArrayList object is modified by the lambda via `add`.
2. `suffix` is **effectively final** because it is not reassigned, so the lambda can capture it.
3. The `Label` record holds an immutable String component; in this example, no mutable state is exposed. `another` is a new Label object and does not alter `immutableLabel`.

The program does not prove that “every record is deep immutable”; it only demonstrates a record with a **String component** and appropriate validation.

## 48. Exercise 1 — Valid or error?

Consider:

~~~java
final int a = 10;
final StringBuilder b = new StringBuilder("A");
String c = "C";

b.append("B");

// a = 20;
// b = new StringBuilder();
// c = "D";

Runnable r = () -> System.out.println(c);
~~~

Questions:

- Is the line `b.append("B")` valid?
- What happens if `a = 20` is uncommented?
- What happens if `b = new StringBuilder()` is uncommented?
- If `c = "D"` is uncommented, is the lambda still valid?

**Answer:** Append is valid because it only modifies the object. Reassigning a/b is invalid due to `final`. Reassigning c causes `c` to lose its effectively final status, so the lambda capturing c becomes invalid.

## 49. Exercise 2 — Which variables are effectively final?

~~~java
int x = 1;
int y;
if (x > 0) {
    y = 10;
} else {
    y = 20;
}
int z = 3;
z++;

Runnable task = () -> System.out.println(x + y);
~~~

**Answer:** `x` is effectively final (not reassigned); `y` is effectively final as it is assigned once per branch and DA is satisfied; `z` is **not** effectively final due to `z++`. The lambda validly captures `x` and `y`.

If the code is modified to add `x++` after the declaration, `x` loses its effectively final status and the lambda does not compile.

## 50. Exercise 3 — Is a final array immutable?

~~~java
final int[] values = {1, 2};
int[] alias = values;
alias[0] = 9;
System.out.println(values[0]);
~~~

**Answer:** Prints `9`. The final variable `values` holds the same array reference, but the array is mutable. `alias` and `values` point to the same array object. If you want an independent snapshot of `int[]`, use `clone()` or `Arrays.copyOf` where appropriate.

## 51. Exercise 4 — Record and mutable List

Given:

~~~java
record Group(java.util.List<String> names) {}

java.util.List<String> input = new java.util.ArrayList<>();
input.add("A");

Group group = new Group(input);
input.add("B");

System.out.println(group.names());
~~~

**Answer:** Prints `[A, B]`. The record component field is final, yet it holds **the same mutable List reference**. Write a compact constructor using `List.copyOf(names)` to protect the structure and describe conditions regarding null and mutable element objects.

## 52. Exercise 5 — Designing an immutable DateRange

Requirement: create a `DateRange` class with:

- Two fields `private final java.time.LocalDate start` and `end`.
- A constructor using `Objects.requireNonNull` for both.
- Reject `end.isBefore(start)`.
- Getters returning the LocalDate directly because it is immutable.
- Method `withEnd(LocalDate newEnd)` returning a **new DateRange**.
- No public setters.
- Test that the old object does not change after `withEnd`.

**Hint:** You can use the record `record DateRange(LocalDate start, LocalDate end)` with compact constructor validation; a record holding immutable LocalDate components fits this value object well.

## 53. Exercise 6 — Final method differs from an immutable class

Given:

~~~java
final class Counter {
    private int value;

    final void increment() {
        value++;
    }
}
~~~

**Answer:** The class cannot be subclassed and the method cannot be overridden according to the respective rules, yet the Counter object is still mutable because `increment()` modifies `value`. There is no such thing as two `final` keywords automatically creating an immutable object.

## 54. Exercise 7 — Why doesn't a lambda see the “new value” of a local variable?

Snippet intentionally causing an error:

~~~java
String status = "PENDING";
Runnable r = () -> System.out.println(status);
status = "DONE";
~~~

Java rejects this because `status` is not effectively final. To report a snapshot, create `String capturedStatus = status;` and capture `capturedStatus`. If you want the lambda to read state that changes at runtime, place the state in an object with an appropriate API and pay attention to concurrency if different threads are involved.

Do not use a one-element array as a trick to bypass effectively final in production code when it hides mutable shared state.

## 55. Self-assessment checklist

- [ ] I can distinguish a final primitive variable from a final reference variable.
- [ ] I understand that a final reference does not prevent mutating methods or array element assignment.
- [ ] I know that reassigning the same value to a final variable is still prohibited.
- [ ] I know that a blank final local variable can be assigned once after declaration when DA is satisfied.
- [ ] I understand that each method call has its own final local variable, not an application-wide constant.
- [ ] I know that effectively final is a property **requiring no keyword**.
- [ ] I can distinguish a local variable with an initializer that is assigned again from a blank local assigned across branches.
- [ ] I know that a method parameter can be final or effectively final.
- [ ] I know that local variables captured by lambdas/anonymous/local classes must be final/effectively final.
- [ ] I understand that mutating a captured object does not make the local reference lose its effectively final status.
- [ ] I know that a for-index `i++` is not effectively final, whereas a local snapshot can be.
- [ ] I know that an enhanced-for variable can be captured in each iteration.
- [ ] I can distinguish immutable `String` and mutable `StringBuilder`.
- [ ] I do not infer that a `final` class is immutable.
- [ ] I know that a `final` method prohibits overriding, without inherently preventing side effects.
- [ ] I know that constructors do not have `final`.
- [ ] I know that a blank final instance field must be initialized through valid constructors.
- [ ] I understand that a `static final` primitive/String constant differs from a `static final` object reference.
- [ ] I know that a record only supports shallow immutability across component references.
- [ ] I know when defensive copying of input/output is needed.
- [ ] I can distinguish shallow copy, deep copy, unmodifiable view, and immutable element.
- [ ] I understand that a `final` field has memory-model benefits but is not automatically thread-safe.
- [ ] I know that `final` does not replace validation/non-null checks.
- [ ] I can choose between a final local, effectively final capture, and an immutable value object depending on the goal.
- [ ] I can run and explain all the Java 17+ programs in this lesson.

**Conclusion:** `final` is a **declaration constraint**: a variable/field/parameter cannot be reassigned after valid initialization; a method cannot be overridden, and a class cannot be extended. **`Effectively final`** is a property of a local variable or parameter that does not need to write final yet can be captured under Java rules. **Immutability** is a characteristic of **object state** ensured by API design, defensive copying, and ownership. The three concepts can coexist, yet **do not imply one another**. Correctly recognizing the boundary between variable, reference, and object helps write valid lambdas, protect invariants, and share Java data more safely.
