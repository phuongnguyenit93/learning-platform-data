# Capturing final and effectively final Local Variables in Java

A **lambda expression** can read variables in the scope where it is declared, including local variables of the enclosing method. When a lambda uses such a local variable, this is called **variable capture**. Java requires a captured local variable to be **`final` or effectively final**: after being assigned a valid value, the variable is not reassigned.

The key point is to distinguish the **local variable** from the **object the variable references**. Not reassigning a reference variable does not mean the object it points to is immutable. This rule also differs from accessing **fields** of an object.

This lesson focuses on lambdas in Java 17+, but the same capture principle also applies when an anonymous class uses a local variable from the enclosing scope.

After this lesson, you will:
- Correctly identify which local variables a lambda is allowed to use and the meaning of `final` versus *effectively final*.
- Predict compile errors when reassigning, incrementing a counter, or using a local variable that is not definitely assigned.
- Distinguish capturing a reference from mutating object state, and distinguish locals from instance/static fields.
- Write callbacks, `Supplier`, `Runnable`, and lambdas in loops with values that need to be remembered clearly.
- Understand the risks of mutable state and concurrency when a lambda runs at a later time or on a different thread.

## 1. Scope and variable capture

**Scope** is the region of code where a variable name can be validly accessed. A lambda can use its own parameters, local variables declared inside the lambda, locals in the enclosing scope, as well as accessible fields of the class.

Illustrative example:

```java
String prefix = "Order-"; // local in the enclosing method
java.util.function.Function<Integer, String> label =
        id -> prefix + id; // id is the lambda parameter; prefix is captured
String result = label.apply(7); // "Order-7"
```

The lines above are a **code snippet placed inside a method**, not a standalone program. `prefix` is created outside, but the lambda can read it because it is in a valid scope. Conversely, `id` is only a parameter of the lambda and does not exist outside the lambda body.

**Capture does not mean immediate execution:** assigning a lambda to `label` creates a behavior object that can be used later. The string concatenation inside only happens when `apply(7)` is called.

In Java, local variables exist according to the execution scope of the containing method/block, while a lambda can exist and be called after the enclosing method has returned. The final/effectively final constraint helps avoid confusing situations if the author expects both the lambda and the method to mutate a local variable.

## 2. What do final and effectively final mean?

### 2.1. Explicit final

A local variable declared `final` cannot be assigned a new value after a valid assignment:

```java
final int base = 10;
java.util.function.IntUnaryOperator addBase = x -> x + base;
int result = addBase.applyAsInt(3); // 13
```

Use `final` so the compiler prevents reassigning the variable name. This helps express a commitment in the source code, especially when the variable serves as a constant value for a task.

### 2.2. Effectively final (final in actual usage)

A variable not declared `final` is still considered *effectively final* if, according to language rules, it is not reassigned after a valid assignment. This is a very common way of writing:

```java
int base = 10; // final not written
java.util.function.IntUnaryOperator addBase = x -> x + base;
int result = addBase.applyAsInt(3); // 13
```

Because `base` is never reassigned, the compiler allows the lambda to capture it. Adding the `final` keyword to this variable does not change the example's result.

**Effectively final is a compile-time condition**, not a dynamic state check while the program is running. Just because a variable has not yet been reassigned in one specific execution branch does not mean it is allowed to be captured if the source code contains an invalid reassignment.

| Local declaration | Can the lambda capture it? | Reason |
| --- | --- | --- |
| `final int threshold = 5;` | Yes | Explicitly final and already assigned. |
| `int threshold = 5;` and never reassigned | Yes | Effectively final. |
| `int threshold = 5; threshold = 6;` | No | Has a reassignment. |
| `int count = 0; count++;` | No | `++` modifies the variable's value. |
| `int count = 0; count += 1;` | No | Compound assignment also changes the variable. |
| `final StringBuilder buffer = new StringBuilder(); buffer.append("x");` | Yes | The reference variable is not reassigned, even though the object changes. |

A local variable without an initializer can still be assigned once along execution paths accepted by the compiler, provided it satisfies **definite assignment** (definitely assigned before the lambda captures it) and the effectively final rule. When you want clear code, initialize the value before creating the lambda.

## 3. Complete example: final and effectively final

Save as **`LocalCaptureDemo.java`**:

```java
import java.util.function.Function;
import java.util.function.IntUnaryOperator;
import java.util.function.Supplier;

public class LocalCaptureDemo {
    public static void main(String[] args) {
        // Not declared final, but never reassigned.
        String prefix = "ID-";
        int maxLength = 5;

        Function<String, String> formatter = text ->
                prefix + text.substring(0, Math.min(text.length(), maxLength));

        // Explicit final.
        final int multiplier = 3;
        IntUnaryOperator triple = value -> value * multiplier;

        Supplier<String> greeting = () -> "Xin chào Java";

        System.out.println(formatter.apply("functional"));
        System.out.println("6 x 3 = " + triple.applyAsInt(6));
        System.out.println(greeting.get());
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac -encoding UTF-8 LocalCaptureDemo.java
java LocalCaptureDemo
```

**Exact stdout:**

```text
ID-funct
6 x 3 = 18
Xin chào Java
```

`prefix` and `maxLength` are effectively final; `multiplier` is explicitly final. All three are allowed to be captured. The result for `"functional"` takes the first five characters `"funct"`; combined with `"ID-"`, it produces `"ID-funct"`. `greeting` does not need to capture any local variable, yet is still a valid zero-parameter lambda.

Because `substring` requires non-null input, this snippet assumes `formatter.apply` receives a non-null string. Capture does not automatically protect against `NullPointerException` or other data errors.

## 4. Reassignment cases that cause compile errors

The following snippets **intentionally do not compile**. Do not mix them into the runnable program in the previous section.

### 4.1. Reassigning after creating the lambda

```java
int bonus = 5;
java.util.function.IntUnaryOperator add = x -> x + bonus;
bonus = 10; // error: bonus is not effectively final
```

The rule applies to the **entire variable declaration** within the relevant scope, not just whether `bonus` changed value before or after calling `add.applyAsInt(...)`.

### 4.2. Reassigning before creating the lambda

```java
int bonus = 5;
bonus = 10;
java.util.function.IntUnaryOperator add = x -> x + bonus; // error
```

The error still occurs because `bonus` was reassigned. Placing the lambda after the reassignment does not automatically make the variable effectively final.

### 4.3. The ++ operator and compound assignment

```java
int count = 0;
Runnable print = () -> System.out.println(count);
count++; // error when count is captured
```

`count += 1` or `count = count + 1` also breaks effectively final. Whether the compiler flags the error at the lambda line or at the modification statement may vary by message, but this combination of capture and reassignment is invalid.

### 4.4. Local variable not definitely assigned

```java
String message;
Runnable print = () -> System.out.println(message); // error: not definitely assigned
message = "ready";
```

In addition to effectively final, Java requires the local variable to be **definitely assigned** before the lambda uses it according to definite assignment rules. To avoid errors, assign `message` before creating the lambda.

### 4.5. Why not use a mutable "holder" just to bypass the compiler?

You can put a value inside a single-element array or holder object and capture the final reference. That compiles, but it introduces mutable state into the execution flow and can cause synchronization bugs when used across multiple threads. Do not default to `int[] count = {0};` as a good solution for every case; first consider a value-returning transformation, a standard loop, or an appropriate data aggregation mechanism.

## 5. Reference final differs from object immutability

A local holding a reference can be final or effectively final while **the object's contents still change**. Complete example:

Save as **`MutableReferenceDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

public class MutableReferenceDemo {
    public static void main(String[] args) {
        final StringBuilder buffer = new StringBuilder("A");
        Supplier<String> view = () -> buffer.toString();

        System.out.println("Trước: " + view.get());
        buffer.append("B");
        System.out.println("Sau: " + view.get());

        List<String> messages = new ArrayList<>();
        Runnable add = () -> messages.add("done");
        add.run();
        System.out.println("Danh sách: " + messages);
    }
}
```

Run:

```bash
javac -encoding UTF-8 MutableReferenceDemo.java
java MutableReferenceDemo
```

**Exact stdout:**

```text
Trước: A
Sau: AB
Danh sách: [done]
```

`buffer` is final so you cannot write `buffer = new StringBuilder("C");`. However, `buffer.append("B")` modifies the contents of the referenced object; it is not a reassignment of the `buffer` variable at all. Similarly, `messages` is not reassigned, so the lambda can call `messages.add(...)`.

Semantically, the lambda retains access to the **same object**, so a later call to `view.get()` sees the modified contents. This is the difference between **immutability of a local variable name** and **immutability of object state**.

Mutating object state through a lambda can be valid, but you need to think about side effects. If the lambda runs in a Stream, an asynchronous callback, or across multiple threads, the `ArrayList` and `StringBuilder` in the example above **do not automatically guarantee thread safety**. `final` only prevents reassigning the reference variable; it does not create a locking mechanism or guarantee consistency of operations on the object.

## 6. Fields are not subject to the same local capture restriction

**Local variables** and **instance/static fields** have different contracts. The final/effectively final rule here applies to local variables, formal parameters, or exception parameters used from the enclosing scope; **instance fields or static fields are not required to be final** for a lambda to read or modify them.

Complete example saved as **`FieldCaptureDemo.java`**:

```java
public class FieldCaptureDemo {
    private int counter;
    private static int total;

    void runExample() {
        Runnable increment = () -> {
            counter++;
            total++;
        };

        increment.run();
        increment.run();

        System.out.println("instance=" + counter);
        System.out.println("static=" + total);
    }

    public static void main(String[] args) {
        new FieldCaptureDemo().runExample();
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 FieldCaptureDemo.java
java FieldCaptureDemo
```

**Exact stdout:**

```text
instance=2
static=2
```

`counter` belongs to the `FieldCaptureDemo` object; `total` belongs to the class. A lambda in an instance method can access and modify them, so both are incremented twice. However, **compiling does not mean it is safe when multiple threads increment concurrently**: `counter++` and `total++` are not atomic increments. If there is concurrent execution, you must choose a synchronization mechanism suited to the requirements.

### this in a lambda and an anonymous class

In a lambda declared in an instance context, `this` points to the **enclosing instance**, not a "lambda" object with its own `this`. You can write `() -> this.counter++` equivalently to the field access in the example above.

By contrast, in an **anonymous class** implementing `Runnable`, `this` inside the implementation points to the instance of that anonymous class. This is an important difference when converting an anonymous class to a lambda.

## 7. Capture in loops: keeping a valid snapshot

The control variable of a classic `for` loop is normally updated on each iteration, so it is not effectively final:

```java
for (int i = 0; i < 3; i++) {
    // INVALID: i is incremented in the for loop's update clause.
    // tasks.add(() -> System.out.println(i));
}
```

To let each callback remember a value from the loop, create a **new local variable that is not reassigned** inside the loop body.

Save as **`LoopCaptureDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class LoopCaptureDemo {
    public static void main(String[] args) {
        List<Runnable> actions = new ArrayList<>();

        for (int i = 0; i < 3; i++) {
            final int snapshot = i;
            actions.add(() -> System.out.println("index=" + snapshot));
        }

        actions.forEach(Runnable::run);

        List<Runnable> names = new ArrayList<>();
        for (String item : List.of("A", "B")) {
            names.add(() -> System.out.println("item=" + item));
        }

        names.forEach(Runnable::run);
    }
}
```

Run:

```bash
javac -encoding UTF-8 LoopCaptureDemo.java
java LoopCaptureDemo
```

**Exact stdout:**

```text
index=0
index=1
index=2
item=A
item=B
```

Explanation:
1. `i` in `for (int i = 0; i < 3; i++)` changes, so it cannot be captured directly.
2. Each execution of the loop body creates a separate `snapshot`, assigned once and unchanged. Each lambda captures its corresponding `snapshot` value.
3. With an **enhanced for** (`for (String item : ...)`), the `item` variable of each iteration is treated as a separate variable for that iteration. If `item` is not reassigned, the lambda can capture it directly.
4. `actions.forEach(Runnable::run)` runs the callbacks one by one in list order, so stdout can be predicted accurately as above. If replaced by asynchronous tasks, you must not assume log lines will always appear in the same order.

This example also shows that callbacks can be **created inside a loop yet run after the loop finishes**. Capture helps each callback retain the exact data of the iteration that created it.

## 8. Notes on execution timing and state

### 8.1. A lambda can run after the declaring method finishes

```java
static java.util.function.Supplier<String> makeSupplier(String prefix) {
    return () -> prefix + "Java";
}
```

This illustrative snippet can be placed in a class. After `makeSupplier("Hello ")` returns, the caller can still call `supplier.get()` and receive `"Hello Java"`. The parameter `prefix` is effectively final if not reassigned in the method.

You should not think that Java keeps the entire method stack frame alive for the lambda. What matters is that the lambda can continue using the **captured value or reference** according to semantics guaranteed by the language; bytecode details and optimizations are decided by the compiler/runtime.

### 8.2. Capturing a reference does not create a deep copy

With an immutable `String`, the captured string value is simple to reason about. With a `List`, `StringBuilder`, or mutable domain object, the lambda can still observe later modifications of the **same object**. If you want unchanged contents, create immutable data or an independent copy of appropriate depth before capturing:

```java
List<String> snapshot = List.copyOf(source);
java.util.function.Supplier<List<String>> reader = () -> snapshot;
```

This is an illustrative snippet with `source` being an existing `List<String>`. `List.copyOf` creates a list whose structure cannot be modified through its API and rejects null elements, but **does not automatically deep-copy** the objects inside. For immutable `String`s, that property fits; when elements are mutable objects, consider copying the elements.

### 8.3. Concurrency and visibility

`final` or effectively final **does not automatically make every access thread-safe**. If a lambda holds a reference to a mutable object and is called from multiple threads, synchronization, visibility, and race conditions must still be handled according to the Java Memory Model.

For example, `AtomicInteger` can be suitable for a simple concurrently updated counter, but does not replace synchronization design for multiple related pieces of state. With Streams, prefer `map`, `filter`, `reduce`, and an appropriate collector instead of mutating a shared `ArrayList` in a parallel lambda.

### 8.4. Purity and testing

A lambda that captures an immutable value and computes a pure result is usually easy to test. A lambda that depends on mutable objects, global fields, or I/O can produce different results across calls with the same arguments. When designing APIs, consider passing inputs directly or taking a snapshot if reproducibility is needed.

## 9. Name scope rules in lambdas

A lambda in Java has a name scope close to its containing block. It **does not allow redeclaring a local variable name in the enclosing scope** as a parameter name or local variable inside the lambda.

**Intentionally invalid example:**

```java
int value = 7;
java.util.function.IntUnaryOperator f = value -> value * 2;
// Invalid: lambda parameter named value collides with local variable in enclosing scope.
```

Fix:

```java
int value = 7;
java.util.function.IntUnaryOperator f = x -> x + value;
```

In the valid example, `x` is the lambda parameter, and `value` is the captured effectively final local.

Other rules:
- A local declared **inside a lambda body** has the scope of that block, but cannot share a name with a local currently in the enclosing scope.
- Both lambda parameters and local variables of the enclosing method follow their scope's access rules; `this` does not become a new local variable of the lambda.
- You cannot use a local variable outside the lambda's lexical scope. Capture does not allow bypassing normal scope rules.

## 10. How to choose a design instead of "bypassing" final

| Practical need | Appropriate design | What to watch out for |
| --- | --- | --- |
| Passing a constant configuration into a callback | Capture a final/effectively final local | Simple, readable, and easy to test. |
| Saving the index of each `for` iteration | Create a `snapshot` inside the loop body | Each callback has its own value. |
| Performing an accumulation calculation | Use `reduce`, `collect`, or an explicit loop | Avoid side effects on enclosing variables. |
| Counting across multiple threads | `AtomicInteger` or an appropriate synchronization mechanism | Atomicity of one variable does not guarantee multi-variable invariants. |
| Reading a list that may be modified later | Take a snapshot before capturing | Consider shallow vs. deep copy. |
| Updating an object's state | Access fields according to the object's contract | Consider synchronization and thread ownership. |

Instead of writing `int count = 0; list.forEach(x -> count++);` (which does not compile), you can use `long count = list.stream().filter(predicate).count();` when the goal is counting elements matching a condition. This shifts from a side effect to a clear result computation. If the need is simply a sequential loop with multiple actions, a `for` loop is often simpler than forcing logic into a lambda.

## 11. Common mistakes and how to spot them

1. **Thinking `final` means an immutable object:** final locks the reference variable, not the object's state.
2. **Reassigning a captured local:** `x = ...`, `x++`, `x += ...` make the variable not effectively final.
3. **Thinking reassigning before the lambda is valid:** effectively final checks the entire variable declaration, not just the period after creating the lambda.
4. **Capturing `i` of a classic `for` loop:** `i` is incremented; create `final int snapshot = i` inside the loop body.
5. **Thinking enhanced for also always fails:** each enhanced for iteration has its own variable and can be captured when not reassigned.
6. **Using a local not definitely assigned:** Java requires definite assignment before use in a lambda.
7. **Declaring a parameter name matching an enclosing local:** a lambda cannot shadow a local currently in scope.
8. **Confusing fields with locals:** fields are not subject to the effectively final rule for local capture, though other access and concurrency rules still apply.
9. **Thinking capture deep-copies an object:** a mutable reference still points to an object that can be modified.
10. **Using a mutable array/holder to "dodge" the compiler and running in parallel:** can cause lost updates and race conditions.
11. **Thinking creating a lambda immediately runs its code:** the lambda body runs when the functional method is called, except for expressions outside the body evaluated when creating the lambda.
12. **Relying on execution order of async callbacks:** captured values may be right, but execution order and logs are not guaranteed without coordination.

## 12. Self-check

**Question 1.** Why is this snippet valid?

```java
int offset = 3;
java.util.function.IntUnaryOperator plus = n -> n + offset;
```

Because `offset` is assigned once and never changed: it is **effectively final** even without writing `final`.

**Question 2.** If we add `offset++` after creating `plus`, is the code valid?

**No.** `offset` is no longer effectively final. The order "create lambda first, modify variable later" does not make it valid.

**Question 3.** Is `final StringBuilder sb = new StringBuilder("A"); Runnable r = () -> sb.append("B");` valid?

**Yes.** The lambda modifies the object's state rather than reassigning `sb`. In a multi-threaded application, thread safety still needs attention.

**Question 4.** Why does `for (int i=0; i<3; i++) callbacks.add(() -> use(i));` fail?

Because `i` changes in the loop, so it is not effectively final. Create `final int snapshot = i;` inside the loop body and capture `snapshot`.

**Question 5.** Can a class's `counter` field be incremented inside a lambda?

**Yes.** Concurrent updates just need to be handled if multiple threads modify the field simultaneously; that is a concurrency issue, not an effectively final error.

**Question 6.** Does a lambda capturing `List<String> items` see changes when someone else calls `items.add(...)`?

**It can see them**, because it holds the same object reference. However, when running concurrently without synchronization, visibility or consistent state must not be assumed. If fixed data is needed, take a snapshot and ensure elements meet immutability requirements.

**Key Takeaway:** **A captured local must be final or effectively final; fields and object state follow different rules.** Clearly distinguishing these three concepts will help you write safe callbacks, understand deferred lambda execution, and design easily testable data processing.
