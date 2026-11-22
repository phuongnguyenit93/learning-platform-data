# Distinguishing Variable Reassignment from Referenced Object Mutation in Java Lambdas

## 1. Objectives and Real-World Scenarios

When learning **scope and variable capture** in lambdas, there are two operations that look similar but follow different rules:

1. **Reassigning a reference variable (reassignment):** making a variable name point to a different object, e.g. `items = new ArrayList<>();`.
2. **Mutating the state of the object the variable points to (mutation):** keeping the same reference while modifying the object, e.g. `items.add("Java");`.

Java requires a **local** variable used by a lambda from an enclosing scope to be `final` or **effectively final**. This rule forbids reassigning the captured local variable, but **does not automatically forbid modifying the state of a mutable object** that the variable references.

Practical consequence: a lambda can compile validly and still cause side effects, lose thread safety, produce order-dependent results, or mislead learners into thinking `final` means the data cannot change.

After this lesson, you should be able to:

- Explain the differences among a **variable**, a **reference value**, an **object on the heap**, and **object state**.
- Distinguish `final` from `effectively final` when a lambda captures a local variable.
- Accurately predict cases where reassignment causes a compile error and cases where mutation remains valid.
- Know how to avoid shared mutable state, using immutable data, defensive copies, or reduction when appropriate.
- Recognize risks when a lambda is stored for later invocation or executed across multiple threads.

Complete examples use **Java 17 or later**.

## 2. Four Foundational Concepts

### 2.1. Local variables and references

Given the code:

~~~java
List<String> names = new ArrayList<>();
~~~

`names` is a **local variable holding a reference value** to an `ArrayList` object. The object has internal state such as a list of elements. Two variables can hold the same reference:

~~~java
List<String> alias = names;
~~~

At this point `names == alias` is `true`: they both point to the same object. Modifying via one variable is also observable via the other, provided it is the same object and under appropriate access conditions.

### 2.2. Reassigning a variable changes the reference value

~~~java
names = new ArrayList<>(List.of("new"));
~~~

The statement above makes `names` point to a **new object**. `alias` still holds the old reference. A new assignment to a local variable is a change to the variable name's **binding**; this is the behavior that the effectively final rule restricts when a lambda captures that variable.

### 2.3. Mutating means modifying the contents of the same object

~~~java
names.add("Java");
names.set(0, "Core"); // Only runs if the list has an element at index 0.
~~~

These calls change the state of the `List` object without performing an assignment `names = ...`. If `names` points to an `ArrayList` and the list is in an appropriate state, they can be valid even when `names` is declared `final`.

### 2.4. Reference diagram

~~~text
Before mutation:
local names ─────┐
                 ├──► ArrayList #1 ["A"]
local alias ─────┘

After names.add("B"):
local names ─────┐
                 ├──► ArrayList #1 ["A", "B"]
local alias ─────┘

After names = new ArrayList<>():
local names ─────────► ArrayList #2 []
local alias ─────────► ArrayList #1 ["A", "B"]
~~~

This diagram illustrates the semantics of references, not physical JVM memory layout details. If `names` is a local captured by a lambda, the **reassignment** in the last step will make the variable no longer effectively final and cause the lambda code using `names` **not to compile**, even though that assignment itself would be valid without capture.

## 3. The `final` and `effectively final` Rules

### 3.1. `final`: can only be assigned according to initialization rules

~~~java
final int limit = 10;
final List<String> list = new ArrayList<>();
~~~

`limit` cannot be assigned another value; `list` cannot be assigned another reference after initialization. However, `list.add(...)` is still allowed because it modifies the **object**.

~~~java
list.add("A");      // Valid: changes state of a mutable object.
// list = new ArrayList<>(); // Error: cannot reassign a final variable.
~~~

The `final` keyword protects the **variable** at this level; it does not guarantee that the referenced object's structure is immutable. For an object that truly forbids mutation, immutability is determined by the object's API/design, not merely by the `final` keyword on the reference variable.

### 3.2. `effectively final`: not written `final` yet never reassigned

~~~java
int threshold = 10;
Runnable show = () -> System.out.println(threshold);
show.run(); // Prints 10
~~~

`threshold` is a local assigned once and never changed afterwards, so the compiler treats it as **effectively final**. Writing `final` does not change the meaning in this case.

If we change the code to:

~~~java
int threshold = 10;
Runnable show = () -> System.out.println(threshold);
threshold = 20; // Compile error because threshold is already captured by the lambda.
~~~

The compiler examines **the scope and assignments in the code**, without waiting for the program to run. Even if the assignment statement appears after the lambda is created or on a rarely executed branch, an assignment that makes the variable not effectively final can still cause the lambda to be rejected at compile time. Do not assume that copying a value into a lambda automatically makes reassigning the local variable valid.

### 3.3. Uninitialized locals and assignment branches

The effectively final rule is not simply "there must be exactly one `=` sign in the entire code." A local variable without an initializer can be **assigned once along each valid path** before use and still be captured, provided it satisfies the definite assignment/effectively final rules.

Valid example placed in a method:

~~~java
final int score;
if (condition) {
    score = 100;
} else {
    score = 0;
}
Runnable printScore = () -> System.out.println(score);
~~~

This is a **code snippet** that requires a `boolean` variable `condition` defined in scope. Each branch initializes `score` once before the lambda uses it. For a local not declared `final`, Java also has equivalent rules for path-wise assignment and no subsequent modification; you should rely on the compiler/JLS in complex cases rather than inferring from the number of lines containing `=`.

### 3.4. Operation comparison table

| Operation | Reassigns local variable? | Modifies referenced object? | If local is captured by a lambda |
| --- | --- | --- | --- |
| `count = 2` | Yes | Not applicable for primitive | Invalid if it breaks effectively final |
| `list = anotherList` | Yes | Not directly | Invalid if it breaks effectively final |
| `list.add("X")` | No | Yes, if list is mutable | May compile; also check List contract |
| `list.clear()` | No | Yes, if mutable | May compile; still has side effects |
| `builder.append("X")` | No | Yes | May compile; builder is modified |
| `atomic.incrementAndGet()` | No | Yes, via AtomicInteger | May compile; individual increment is atomic |
| `list.size()` | No | Normally no | May compile; only reads state |

**Note:** "may compile" does not mean "always runs successfully." Calling `add` on `List.of(...)` throws `UnsupportedOperationException`; calling a method on a `null` reference can throw `NullPointerException`; sharing an `ArrayList` across threads can fail synchronization.

## 4. What Does a Lambda Capture?

A lambda can access parameters, local variables, and members in valid scope. For **captured local variables**, Java requires `final`/`effectively final`. This restriction helps avoid misunderstandings about a changing local on the stack while the lambda behavior can outlive the block that created it.

Example:

~~~java
int minimum = 3;
Predicate<String> accepted =
        name -> name != null && name.length() >= minimum;
~~~

Here `minimum` is not reassigned; each time the lambda runs, it uses the captured local value. If `minimum` is a primitive `int`, the value used by the lambda does not change through local variable reassignments because such reassignments are not allowed in the capture case.

With a reference:

~~~java
List<String> audit = new ArrayList<>();
Consumer<String> record = name -> audit.add(name);
~~~

The lambda uses the **reference** to the object that `audit` pointed to at capture time. It can modify the object through that reference. **There is no automatic copy of the entire ArrayList** when creating the lambda.

### Capture does not mean a snapshot of state

~~~java
List<String> shared = new ArrayList<>(List.of("A"));
Supplier<Integer> size = () -> shared.size();

System.out.println(size.get()); // 1
shared.add("B");
System.out.println(size.get()); // 2
~~~

This illustrative code needs `java.util.List`, `java.util.ArrayList`, and `java.util.function.Supplier` imported, placed inside a method. The variable `shared` keeps the same reference and remains effectively final; the object's state changes between the two calls to `size.get()`, so the results differ.

Conversely, if you need to fix the result at lambda creation time, you can precompute an immutable value:

~~~java
int fixedSize = shared.size();
Supplier<Integer> snapshotSize = () -> fixedSize;
~~~

If `shared` adds elements later, `snapshotSize.get()` still returns the determined `fixedSize`. This is the difference between capturing a **computed value** and capturing a **reference to read state later**.

### Fields and locals are not constrained the same way

The effectively final rule applies to **local variables, parameters, and exception parameters** referenced by a lambda. **Instance fields** and **static fields** are not local captures of that kind; fields can be reassigned if their declaration and access rules allow.

~~~java
class CounterHolder {
    private int total;

    Runnable incrementer() {
        return () -> total++; // Compiles: total is a field, not a local.
    }
}
~~~

This is an illustrative class, not a standalone program with `main`. If multiple threads call `incrementer()` on the same instance, `total++` is not an atomic operation and can race. The capture rule only checks reassignability of **local variables**; it does not guarantee visibility or atomicity for fields in multithreaded execution.

## 5. Complete Java 17 Example: Reassignment, Alias, and Mutation

Create the file **`CaptureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import java.util.function.IntConsumer;

public class CaptureDemo {
    public static void main(String[] args) {
        // threshold is an effectively final local.
        int threshold = 10;
        List<String> messages = new ArrayList<>();

        // messages is not reassigned; the List object can be modified.
        Consumer<Integer> classify = number ->
                messages.add(number >= threshold
                        ? "high:" + number : "low:" + number);

        classify.accept(7);
        classify.accept(12);
        System.out.println(messages);

        List<String> original = new ArrayList<>(List.of("A"));
        List<String> alias = original;

        // A method reference also invokes the operation on the same object.
        Consumer<String> append = original::add;
        append.accept("B");

        System.out.println(original);
        System.out.println(original == alias);

        // Capture a snapshot of the current list structure.
        List<String> snapshot = List.copyOf(original);
        append.accept("C");
        System.out.println(snapshot);
        System.out.println(original);

        final StringBuilder builder = new StringBuilder("start");
        Runnable update = () -> builder.append("-done");
        update.run();
        System.out.println(builder);

        AtomicInteger counter = new AtomicInteger();
        IntConsumer count = number -> counter.incrementAndGet();
        count.accept(1);
        count.accept(2);
        System.out.println(counter.get());
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 CaptureDemo.java
java CaptureDemo
~~~

**Exact stdout:**

~~~text
[low:7, high:12]
[A, B]
true
[A, B]
[A, B, C]
start-done
2
~~~

Analysis:

1. `threshold` is not reassigned, so the `classify` lambda is allowed to capture it. `messages.add(...)` modifies the **List object**, without reassigning the local variable `messages`.
2. `original` and `alias` point to the same `ArrayList`; `append.accept("B")` modifies that object, so the list becomes `[A, B]` and `original == alias` prints `true`.
3. `List.copyOf(original)` creates a list that **cannot have its structure added to/removed from/modified via the List API**, recording the elements at the time of the call; when `original` adds `"C"`, `snapshot` remains `[A, B]`. In this example the elements are immutable `String`s.
4. `builder` is declared `final` but `StringBuilder` is mutable, so `append` still executes and prints `start-done`.
5. `AtomicInteger` is a mutable object with atomic value-update operations. `counter` is not reassigned; `incrementAndGet` modifies the **internal state** of the object, and two calls make the value `2`. The parameter `number` is unused in this example lambda because the goal is to illustrate the increment; it can be named `ignored` if you want to make that explicit.

**Lesson learned:** these lambdas and method references compile because there is no reassignment of captured locals. They can still cause external state to change. Safety cannot be inferred from the compiler accepting the lambda.

## 6. Error Cases: Reassigning a Local Variable Already Used by a Lambda

The following snippets are **intentional error examples; do not merge them into a runnable program**.

### 6.1. Reassigning a reference variable

~~~java
List<String> items = new ArrayList<>();
Runnable task = () -> System.out.println(items.size());
items = new ArrayList<>(); // Compiler error: items is not effectively final.
~~~

The error occurs even though the lambda only calls `size()` and does not mutate. The compiler's condition is that `items` is not reassigned when captured by a lambda, not merely forbidding mutation inside the lambda.

### 6.2. Reassigning a primitive

~~~java
int number = 1;
Runnable task = () -> System.out.println(number);
number++; // Also updates the local variable, violating effectively final.
~~~

`number++` changes the value of the local variable. The variable is no longer effectively final, even when the increment statement is outside the lambda body.

### 6.3. Reassigning right inside the lambda

~~~java
List<String> items = new ArrayList<>();
Runnable task = () -> {
    items = new ArrayList<>(); // Compile error.
};
~~~

A lambda cannot use an assignment to change the binding of a captured local variable. If you want to create a new collection for its own processing, declare a **new local variable inside the lambda**:

~~~java
Runnable task = () -> {
    List<String> temporary = new ArrayList<>();
    temporary.add("Java");
    System.out.println(temporary);
};
~~~

Each call to `run()` in this example creates a new `ArrayList`, so there is no need to share the same mutable object with previous calls. If the requirement is genuinely to save the result, design a return value using `Supplier<List<String>>`, `Function`, or pass through an appropriate state-management API instead of trying to bypass the compiler.

### 6.4. Assigning a new reference to another variable is not "modifying the object"

~~~java
List<String> first = new ArrayList<>(List.of("A"));
List<String> second = first;
second = new ArrayList<>(List.of("B"));
~~~

After the last line, `first` still points to the list `["A"]`, while `second` points to `["B"]`. The assignment changes the **variable `second`**, not `first`'s object. If a lambda captures `second` in the same scope, that reassignment will cause a compile error; if the lambda only captures `first`, reassigning **`second`** does not make `first` lose effectively final status.

## 7. `final` Does Not Mean Immutable or Thread-Safe

### 7.1. There are multiple levels of non-changeability

| Declaration / data creation | What is protected | What is not automatically guaranteed |
| --- | --- | --- |
| `final List<String> list = new ArrayList<>();` | Cannot reassign the `list` variable | Can still `add`/`remove`; not automatically thread-safe |
| `List<String> list = new ArrayList<>();` and never reassign | Local variable is effectively final for lambda capture | Can still modify the object; not automatically immutable |
| `List.of("A", "B")` | Cannot modify list structure via `List` | Not deep immutable by default if elements are mutable objects |
| `List.copyOf(source)` | New unmodifiable list, capturing structure at copy time | Does not deep-copy mutable elements |
| `Collections.unmodifiableList(source)` | Cannot modify through the wrapper | If `source` is still held, modifying `source` can show through the wrapper |
| `AtomicInteger` | Certain operations like `incrementAndGet` have atomic guarantees | Does not turn an entire multi-step workflow into a transaction |

For example, `List.copyOf` only copies references to elements and creates an unmodifiable structure; if an element is a mutable `StringBuilder`, modifying the contents of that `StringBuilder` itself is still observable from both source and copy.

### 7.2. A `final` field is not inherently deep immutable either

~~~java
class Store {
    final List<String> entries = new ArrayList<>();

    void add(String entry) {
        entries.add(entry); // Still valid.
    }
}
~~~

This class is for illustration only. `final` prevents changing the reference of the `entries` field after initialization; it does not turn `ArrayList` into an immutable list. To design a more immutable object, prevent exposing mutable references, make defensive copies when receiving/returning data, and ensure internal components also satisfy the desired immutability.

### 7.3. Immutable data reduces friction when using lambdas

With unchanging data, sharing across multiple functions is usually more predictable. One way to organize it:

~~~java
List<String> source = List.of("An", "Binh");
List<String> upper = source.stream()
        .map(String::toUpperCase)
        .toList();
~~~

This is illustrative code inside a method. `source` is not mutated; the pipeline produces a result list and `Stream.toList()` returns an unmodifiable list. The computation has explicit inputs and outputs, is easy to test, and reduces the risk of depending on external state.

## 8. Issues with Shared Mutable State and Parallel Processing

### 8.1. A valid lambda is not necessarily thread-safe

~~~java
List<Integer> results = new ArrayList<>();
IntConsumer save = value -> results.add(value);
~~~

The snippet above **compiles**: `results` is effectively final and the `add` method does not reassign that variable. However, if multiple threads call `save.accept(...)` concurrently, `ArrayList` does not provide thread safety for such concurrent modifications. Results may lose elements, have corrupted state, or exhibit unexpected behavior.

Using `parallelStream().forEach(results::add)` to collect results is a common mistake. Use an aggregation designed for Streams:

~~~java
List<Integer> squares = List.of(1, 2, 3, 4)
        .parallelStream()
        .map(n -> n * n)
        .toList();
~~~

This is an illustrative snippet with an ordered input; `toList()` produces results in the pipeline's encounter order when ordered. It avoids manually updating a shared `ArrayList` inside `forEach`. In practice, **do not automatically use `parallelStream` assuming it will be faster**; weigh overhead and business requirements.

### 8.2. Use reduction when the goal is computation

Side-effecting approach:

~~~java
AtomicInteger total = new AtomicInteger();
List.of(1, 2, 3).forEach(total::addAndGet);
System.out.println(total.get()); // 6
~~~

Direct result-expressing approach:

~~~java
int total = List.of(1, 2, 3).stream()
        .mapToInt(Integer::intValue)
        .sum();
System.out.println(total); // 6
~~~

The two independent snippets produce the same sum in this small example. The second approach makes it clearer that the intent is to compute a value, not update shared state. `AtomicInteger` is useful when an atomically updated counter is genuinely needed, but should not be used just to bypass the effectively final rule.

### 8.3. Visibility and atomicity issues

Even when all updates are syntactically valid, the Java Memory Model still matters when data is shared across threads. Operations like `counter++` on a regular field are not atomic; a `volatile` field provides certain visibility/ordering rules but **does not make `++` atomic**. `AtomicInteger.incrementAndGet()` provides an atomic guarantee for that value update operation, yet two steps updating two different objects still do not automatically form a transaction.

Therefore, safety rules should be split into two questions: *is the local variable captured according to compiler rules?* and *is shared state synchronized and semantically sound?* Answering "yes" to the first question cannot replace the second.

## 9. When a Lambda Is Called at a Different Time

### 9.1. Do not confuse creation time with execution time

~~~java
List<String> items = new ArrayList<>();
Runnable printSize = () -> System.out.println(items.size());

items.add("A");
printSize.run(); // Prints 1.
items.add("B");
printSize.run(); // Prints 2.
~~~

Here the lambda does not run when assigned to `printSize`. When `run` is called, it reads the current state of the object that the captured reference points to. Thus, two calls can produce different results without any reassignment of the `items` variable.

### 9.2. Loops and capture

In a classic `for` loop, the counter variable changes on each iteration so it is not effectively final:

~~~java
List<Runnable> tasks = new ArrayList<>();
for (int i = 0; i < 3; i++) {
    // Error: i is modified by i++.
    tasks.add(() -> System.out.println(i));
}
~~~

The solution is to create a local variable for **each iteration** that is not reassigned:

~~~java
List<Runnable> tasks = new ArrayList<>();
for (int i = 0; i < 3; i++) {
    int index = i;
    tasks.add(() -> System.out.println(index));
}
tasks.forEach(Runnable::run); // Prints 0, then 1, then 2 on three lines.
~~~

A new local variable `index` is created for each iteration. Each lambda captures a different `index` value. With a `for-each` loop, the element variable declared in the loop also has per-iteration scope, so it can be captured when not reassigned within that iteration.

### 9.3. A lambda can outlive the block that created it

If a method returns a lambda, the lambda can be called after the creating method finishes. Captured local variables do not need to remain alive as an original stack frame for the lambda to use them; Java semantics ensure the data needed by the lambda remains accessible via an appropriate runtime mechanism. You should not rely on a specific assumption about how the compiler/JVM represents capture in memory.

Illustrative example:

~~~java
static Supplier<Integer> sizeLater(List<String> input) {
    List<String> view = input;
    return () -> view.size();
}
~~~

This is an illustrative method in a class, requiring `Supplier`/`List` imports. `view` is not reassigned so it is effectively final; when the lambda is called later, the result may reflect external modifications to the **List instance**. To snapshot the structure, you can use `List.copyOf(input)` before creating the lambda, noting that it requires no `null` elements and is only a shallow copy.

## 10. Design Patterns to Avoid Confusion

### 10.1. Pass parameters, return results

Prefer writing with clear inputs and outputs:

~~~java
static List<String> appendCopy(List<String> source, String value) {
    List<String> result = new ArrayList<>(source);
    result.add(value);
    return result;
}
~~~

This is an illustrative method in a class, requiring `List` and `ArrayList` imports. `source` is not structurally modified by the method; the caller receives a new list to manage further. If the API requires an unmodifiable result, return `List.copyOf(result)` or a solution matching the contract for nulls and element types.

### 10.2. Separate intentional mutation from transformation pipelines

Suppose you need to log when performing a business action. You do not necessarily have to place log calls inside `map`/`filter` to create hidden side effects. You can transform data with pure functions and then perform save/print operations at a clear boundary:

~~~java
List<String> output = input.stream()
        .filter(value -> value != null && !value.isBlank())
        .map(String::trim)
        .toList();

output.forEach(System.out::println);
~~~

This is an illustrative snippet inside a method, with `input` being a valid `List<String>`. `output` is the result of the pipeline; `forEach` afterwards clearly expresses the intent to print data. You should define the actual `null`-handling, exception, and logging contract according to the problem.

### 10.3. Use defensive copies when exposing mutable data

If an API returns an internal `ArrayList` directly, the caller can mutate the owning object's state. One way to protect the structure is to return an unmodifiable copy:

~~~java
List<String> getEntries() {
    return List.copyOf(entries);
}
~~~

This is an illustrative method in a class owning the `entries` field; `List.copyOf` requires the input collection not to contain `null` elements. If elements have mutable state, further evaluate deep-copy requirements or design immutable elements. A `Collections.unmodifiableList(entries)` only creates an unmodifiable **view** through a wrapper, which can reflect later structural changes to `entries`; it does not have the same snapshot semantics as `List.copyOf`.

## 11. Practice Exercises

### Exercise 1 — Predict compilation

~~~java
int base = 2;
Function<Integer, Integer> add = n -> n + base;
base = 3;
~~~

**Question:** why does it fail? **Answer:** `base` is a local captured by the lambda yet reassigned, so it is not effectively final. If you want an addition depending on a changing parameter, pass the `base` value into the function or create a new lambda based on another local variable with a stable value.

### Exercise 2 — Distinguish reference from contents

~~~java
List<String> entries = new ArrayList<>();
Consumer<String> collect = entries::add;
collect.accept("A");
collect.accept("B");
System.out.println(entries);
~~~

The result is `[A, B]`. The `entries` variable is not reassigned; the List object is mutated. Explain why adding `final` to the declaration of `entries` does not make the `add` lines fail.

### Exercise 3 — Alias

Write two variables `a` and `b` both pointing to an `ArrayList`, add an element via `a`, and read via `b`. Then reassign `b` to a new `ArrayList` when no lambda captures `b`. State clearly when the two variables still point to the same object and when the references have separated.

### Exercise 4 — Snapshot

Given `List<String> mutable = new ArrayList<>(List.of("A"));`, create `List<String> snapshot = List.copyOf(mutable);`, then call `mutable.add("B")`. Compare the two lists. Next, try with a list containing a mutable object to explain why `List.copyOf` is not a deep copy.

### Exercise 5 — Loops and capture

Create three `Runnable`s, each printing the corresponding index `0`, `1`, `2`. Distinguish why directly capturing the counter variable of a classic `for` loop fails and capturing an `index` variable declared in each iteration is valid.

### Exercise 6 — Streams and shared state

Given `List<Integer> nums = List.of(1,2,3,4,5);`. Write how to compute the sum of squares using `mapToInt(n -> n*n).sum()`. Compare with using an `AtomicInteger` updated in `forEach`; explain why the reduction approach expresses the computation goal more clearly and depends less on external mutable state. Try an empty list and note the sum is `0`.

### Exercise 7 — Design question

A callback receives `List<Order> orders`, holds the reference, and may be called after the list has changed. If the requirement is to process **the exact data at the time the callback was registered**, what would you do? Hint: create an appropriate snapshot and consider mutable elements; do not rely on a local variable being `final` to infer an immutable object.

## 12. Common Misconceptions

| Misconception | Reality | How to handle |
| --- | --- | --- |
| "The lambda captures a `final` variable so the object won't change" | `final` protects variable reassignment, not mutable objects | Check API/immutability design |
| "If the list isn't modified inside the lambda, there are no side effects" | A callback can call mutating methods on the object elsewhere | Inspect the entire call chain and access rights |
| "After creating the lambda, you can reassign the captured local" | The compiler checks effectively final across the entire scope | Pass parameters or create a new variable |
| "Copying a List always deep-copies objects" | `List.copyOf` creates a new structure, which can share mutable elements | Deep-copy when required |
| "`AtomicInteger` makes the whole workflow thread-safe" | Only the operations it guarantees are atomic | Evaluate shared state and overall transactions |
| "Compiling means parallel-safe" | Capture checks differ from memory synchronization | Avoid shared mutable state or use proper mechanisms |
| "A lambda automatically keeps a snapshot of a List" | A lambda captures a reference, not cloning object state automatically | Make defensive copies intentionally |
| "`Collections.unmodifiableList` is a snapshot" | It is usually a wrapper view over the source | Choose `List.copyOf` if you want a structural snapshot |
| "Assigning a different reference also modifies the old object" | Reassigning a variable only changes the binding; the old object is not directly modified | Draw an alias diagram to check |

## 13. Lambda Code Review Checklist

Before using a lambda that captures an outer variable, determine:

1. Is the accessed variable a **local**, **parameter**, **field**, or **static field**?
2. If it is a captured local/parameter: is it `final` or effectively final? Are there any reassignments, `++`, or `--` affecting the variable?
3. Is the captured value a **primitive/immutable value** or a **reference to a mutable object**?
4. Does the lambda call methods that modify the referenced object or external fields?
5. Are there other **aliases** pointing to the object that could mutate it? Could the lambda be called after the object's state changes?
6. If the lambda runs on multiple threads, what ensures **visibility**, **atomicity**, and update ordering? Can sharing state be avoided?
7. If a snapshot is needed, is it a **value** snapshot, a **collection structure** snapshot, or a **deep element snapshot**?
8. If the goal is computation, can you return the result via `Function`/`Supplier` or use `map`/`reduce`/`collect` to reduce side effects?

## 14. Conclusion and Reference Documentation

**Reassigning a variable** changes the value stored in the variable (for example, changing the reference to a new object). **Mutating the referenced object** modifies the object's state without reassigning the variable. For local variables captured by a lambda, Java requires `final` or **effectively final**, so reassignment is restricted; mutation of a mutable object can still compile and run.

This rule helps clarify syntax and scope, **not a promise of immutability or thread safety**. For more testable and safer code, clarify side-effect boundaries, prefer immutable data when appropriate, avoid unsynchronized shared mutable state, and use reduction instead of updating outer variables when an aggregated result is needed.

Official documentation: *Java Language Specification* on **`4.12.4 final Variables`**, **`15.27 Lambda Expressions`**, and variable scope in Java; Javadoc for **`java.util.List`**, **`java.util.concurrent.atomic.AtomicInteger`**, **`java.util.function`**, and **`java.util.stream.Stream`**.