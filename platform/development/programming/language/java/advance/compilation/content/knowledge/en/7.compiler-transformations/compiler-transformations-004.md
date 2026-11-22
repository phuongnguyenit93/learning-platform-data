# Effectively final variables and data captured by lambdas in Java

A lambda expression allows Java code to reference names declared outside the lambda body, such as local variables and parameters of the enclosing method. However, to **capture a local variable**, the compiler requires that variable to be **final** or **effectively final**. This rule is completely different from whether the referenced object is mutable, and even more different from thread safety.

This lesson clearly distinguishes: (1) which local variables the compiler accepts, (2) which values are captured when the lambda is created, (3) which state is read when the callback runs, and (4) what changes when a lambda outlives the method or runs on another thread.

## 1. First example: a lambda capturing local variables

Create the file `FirstCapture.java`:

~~~java
import java.util.function.IntFunction;

public final class FirstCapture {
    public static void main(String[] args) {
        int multiplier = 3;
        String prefix = "result=";

        IntFunction<String> format = value -> prefix + value * multiplier;
        System.out.println(format.apply(4));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 --release 17 FirstCapture.java
java FirstCapture
~~~

Exact stdout:

~~~text
result=12
~~~

Analysis:

- `value` is the **lambda parameter**, received when calling `format.apply(4)`.
- `multiplier` and `prefix` are **local variables of the `main` method**, referenced by the lambda from the outer lexical scope.
- These two local variables are not reassigned after initialization, so they are **effectively final**, without needing the `final` keyword.
- The lambda holds the **values** it needs: the integer `3` for `multiplier`, and the reference value pointing to the `String` object of `prefix`.
- The multiplication and string concatenation in the lambda body are executed **when `apply` is called**, not immediately just because the lambda declaration line was executed.

`IntFunction<String>` is a *functional interface* (one abstract method `apply(int)`); the lambda is type-checked against this target type. A lambda is not a standalone method that can run without a corresponding functional interface.

## 2. Final and effectively final rules

**Final local variable:** has a `final` declaration, assigned only once according to definite assignment rules.

~~~java
final int limit = 10;
// limit = 11; // Compile error
~~~

**Effectively final local variable:** not declared `final`, yet the entire assignment history of the variable satisfies the rules so that it can be treated as a final variable. For a variable initialized right at its declaration, any reassignment breaks effective finality.

~~~java
int limit = 10;
Runnable print = () -> System.out.println(limit);
print.run(); // Prints 10
~~~

Writing without `final` is still valid because there is no other assignment to `limit`. The compiler applies this rule to local variables/parameters used by a lambda, regardless of whether the lambda runs before or after a reassignment statement.

| Scenario (each row is an independent example) | Effectively final? | Why |
| --- | --- | --- |
| `int x = 1;` and only reading `x` | Yes | One initializer, no reassignment |
| `int x = 1; x = 1;` | No | Assigned again even though the value did not change |
| `int x = 1; x++;` | No | Incrementing the variable modifies the variable |
| `int x = 1; x += 0;` | No | Compound assignment still writes to the variable |
| `int x; x = 1;` | Yes if there are no other assignments and definite assignment is satisfied | Uninitialized variable assigned once |
| `int x; if (flag) x = 1; else x = 2;` | Yes if there are no other assignments | Each execution path assigns exactly once |
| `List<String> xs = new ArrayList<>(); xs.add("a");` | Yes | Reference variable is not reassigned |
| `int[] a = {0}; a[0]++;` | Yes | Mutates an array element, does not reassign variable `a` |
| `List<String> xs = new ArrayList<>(); xs = new ArrayList<>();` | No | Changes the reference value of the variable |

The essence of **effectively final** is restricting **assignment to the variable**, not comparing two values with `equals` or checking whether an object is immutable.

### Assignment after declaration: definite assignment

The following snippet is completely valid and runnable:

~~~java
// File: OneAssignment.java
import java.util.function.IntSupplier;

public final class OneAssignment {
    static int choose(boolean flag) {
        int result;
        if (flag) {
            result = 7;
        } else {
            result = 11;
        }
        IntSupplier supplier = () -> result;
        return supplier.getAsInt();
    }

    public static void main(String[] args) {
        System.out.println(choose(true));
        System.out.println(choose(false));
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 OneAssignment.java
java OneAssignment
~~~

Stdout:

~~~text
7
11
~~~

`result` is assigned once along each execution path. The compiler also checks **definite assignment**: the variable must be guaranteed to have a value before being read. `final`/effectively final and definite assignment are two related but non-identical checks.

## 3. Capture cases rejected by the compiler

The snippets in this section are **intentionally invalid** to illustrate compile-time errors.

### Reassigning after creating the lambda

~~~java
int count = 0;
Runnable task = () -> System.out.println(count);
count++;
~~~

The compiler typically reports an error message like:

~~~text
local variables referenced from a lambda expression must be final or effectively final
~~~

One cannot argue that the lambda will run *before* `count++`: the entire local variable is checked, and `count++` makes it lose effective finality.

### Reassigning before creating the lambda

~~~java
int count = 0;
count = 5;
Runnable task = () -> System.out.println(count);
~~~

Also invalid. The second assignment occurred before the lambda creation line, yet it still exists on the variable `count`.

### Reassigning inside the lambda itself

~~~java
int count = 0;
Runnable task = () -> count++; // Error
~~~

A captured local variable cannot become an assignment target inside the lambda body in this way. Writing `count += 1` or `count = count + 1` is still invalid.

### Not definitely assigned

~~~java
int count;
Runnable task = () -> System.out.println(count); // Error
~~~

`count` may be considered effectively final, but it is not guaranteed to have a value before being referenced by the lambda. It must be properly assigned before use.

### Method parameters are also subject to the rule

~~~java
static Runnable bad(int number) {
    number = number + 1;
    return () -> System.out.println(number); // Error
}
~~~

Parameter `number` is reassigned, so it is not effectively final. The fix is to use a new local snapshot:

~~~java
static Runnable good(int number) {
    int adjusted = number + 1;
    return () -> System.out.println(adjusted);
}
~~~

`adjusted` is computed once when calling `good` and is not reassigned.

## 4. Capturing primitives vs. capturing references

Java distinguishes **primitive values** and **reference values**:

- For `int amount = 10`, the value held for the lambda is `10`.
- For `StringBuilder text = new StringBuilder("a")`, the value held is a **reference to the `StringBuilder` object**, not a copy of that object's current contents.
- When the lambda is called, it can read the **new state of the same referenced object**. This does not violate effective finality because the variable `text` has not been reassigned.

Create the file `MutableCapture.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

public final class MutableCapture {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>();
        Supplier<Integer> size = () -> words.size();
        words.add("A");
        words.add("B");
        System.out.println(size.get());

        StringBuilder builder = new StringBuilder("hello");
        Supplier<String> current = () -> builder.toString();
        String snapshot = builder.toString();
        Supplier<String> frozen = () -> snapshot;

        builder.append("-java");
        System.out.println(current.get());
        System.out.println(frozen.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 MutableCapture.java
java MutableCapture
~~~

Stdout:

~~~text
2
hello-java
hello
~~~

`size` and `current` hold references to the mutable objects and **invoke methods on those objects when the callback runs**. Meanwhile `frozen` holds the reference value to the `String` already created by `builder.toString()`, so it returns `"hello"` even though `builder` was modified.

This is the difference between:

~~~java
// Illustrative snippets inside a method that has a corresponding builder
Supplier<String> live = () -> builder.toString(); // Reads state when calling get()
String saved = builder.toString();
Supplier<String> once = () -> saved;               // Holds the already computed result
~~~

If an immutable snapshot of an entire collection is needed, holding a reference is not enough: consider creating an **appropriate copy**, such as `List.copyOf(source)` subject to conditions regarding null elements and the immutability of the contained objects. Copying a collection also does not automatically deep-copy mutable elements.

## 5. A lambda can outlive the method that created it

~~~java
// File: EscapingCapture.java
import java.util.function.IntSupplier;

public final class EscapingCapture {
    static IntSupplier make(int seed) {
        int doubled = seed * 2;
        return () -> doubled + 1;
    }

    public static void main(String[] args) {
        IntSupplier result = make(5);
        System.out.println(result.getAsInt());
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 EscapingCapture.java
java EscapingCapture
~~~

Stdout:

~~~text
11
~~~

Method `make(5)` has already returned when `getAsInt()` is called, yet the lambda still uses `doubled = 10`. Do not imagine the lambda continuously reading back the **stack slot of a finished method**. The compiler/runtime must provide the captured value for the callback to use properly later; a specific implementation does not necessarily create a class file for each lambda.

Not all of a lambda body is executed when the lambda **is created**. For example:

~~~java
int base = 10;
java.util.function.IntSupplier s = () -> base + expensive();
~~~

`base` is captured; `expensive()` still runs **every time `s.getAsInt()`** is called if the body executes. This is only an illustration inside a class with an appropriate `expensive()` method, not a complete program. If you want to compute it once:

~~~java
int computed = expensive();
java.util.function.IntSupplier s = () -> computed;
~~~

The two approaches behave differently when `expensive()` has side effects, is time-consuming, or returns changing values.

## 6. Capturing in loops

### 6.1. Basic `for`: cannot directly capture the incremented `i` variable

~~~java
for (int i = 0; i < 3; i++) {
    Runnable task = () -> System.out.println(i); // Compile error
}
~~~

`i++` makes variable `i` not effectively final. Java **does not create a separate copy of `i` by default** for each lambda under this syntax.

Create a local snapshot in each iteration:

~~~java
// File: LoopCapture.java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

public final class LoopCapture {
    public static void main(String[] args) {
        List<Runnable> tasks = new ArrayList<>();

        for (int i = 0; i < 3; i++) {
            int step = i;
            tasks.add(() -> System.out.println(step));
        }

        for (Runnable task : tasks) {
            task.run();
        }

        List<Supplier<String>> letters = new ArrayList<>();
        for (String letter : List.of("A", "B")) {
            letters.add(() -> letter);
        }
        System.out.println(letters.get(0).get() + letters.get(1).get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 LoopCapture.java
java LoopCapture
~~~

Stdout:

~~~text
0
1
2
AB
~~~

`step` is a new local variable for **each execution of the loop body**, initialized with the value of `i` for that iteration. Each `step` variable is effectively final.

### 6.2. Enhanced `for` has its own iteration variable

With `for (String letter : List.of("A", "B"))`, the variable `letter` is semantically a new iteration variable on each iteration. It can be captured if not reassigned inside the body. Therefore the two `Supplier` instances above return `"A"` and `"B"` in the exact order they were placed in the list.

If inside an enhanced-for you both write `letter = "changed";` and capture `letter`, the compiler will still reject it because that variable is no longer effectively final. Do not equate an enhanced-for variable with a basic-for counter `i`.

## 7. Instance/static fields are not constrained like local variables

The effectively final requirement on locals/parameters **does not mean every field read by a lambda must be final**.

~~~java
// File: FieldCapture.java
import java.util.function.IntSupplier;

public final class FieldCapture {
    private int value = 1;

    IntSupplier reader() {
        return () -> value;
    }

    public static void main(String[] args) {
        FieldCapture owner = new FieldCapture();
        IntSupplier read = owner.reader();
        owner.value = 7;
        System.out.println(read.getAsInt());
        owner.value = 9;
        System.out.println(read.getAsInt());
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 FieldCapture.java
java FieldCapture
~~~

Stdout:

~~~text
7
9
~~~

The lambda inside `reader()` reads the instance field `value` of the **enclosing `this`** when `getAsInt()` is called. The field can be reassigned, so the result differs between the two calls.

**Static fields** can also be read by a lambda, without thereby becoming snapshots. Both instance fields and static fields require appropriate synchronization if read/written by multiple threads.

### To snapshot a field, use a separate local variable

~~~java
// Illustration inside an instance method of a class with field value
int atCreation = this.value;
IntSupplier frozen = () -> atCreation;
IntSupplier live = () -> this.value;
~~~

`frozen` holds the **value of the local variable** when creating the lambda; `live` reads the **current state of the field** at call time. This is a deliberate way to choose between snapshot and live access.

### `this` in lambdas vs. anonymous classes

A lambda uses `this` according to **lexical scope**. Inside an instance method, `this` inside the lambda refers to the instance of the class containing the method; a lambda does not provide an independent `this` to refer to like an anonymous inner class.

~~~java
// Illustration inside an instance method
Runnable a = () -> System.out.println(this.toString());

Runnable b = new Runnable() {
    @Override
    public void run() {
        System.out.println(this.toString());
    }
};
~~~

In `a`, `this` is the enclosing instance. In `b`, `this` is the anonymous class instance. When both use local variables from the enclosing scope, the anonymous class must also obey the final/effectively final constraint; however, the two expression types differ in identity/scope and representation.

## 8. Method references and captured data

A bound method reference can capture the **receiver object**:

~~~java
// Illustration inside a method
StringBuilder builder = new StringBuilder("A");
java.util.function.Supplier<String> read = builder::toString;
builder.append("B");
// read.get() returns "AB"
~~~

The receiver expression `builder` of `builder::toString` is evaluated when the method reference is created. Method `toString()` is called later, when `get()` runs. Thus the receiver reference value can be held while the receiver's state continues to change.

Do not equate `builder::toString` with `builder.toString()`: the first creates a functional object to invoke the method later; the second **calls the method immediately** and returns a `String`.

Method references such as `Type::staticMethod`, `Type::instanceMethod`, and `Type::new` also have their own target type rules. One should not conclude that all method references capture locals in the same way.

## 9. Multi-threaded lambdas: effectively final does not guarantee thread safety

### 9.1. A "single-element array" compiles but still has a data race

~~~java
int[] count = {0};
Runnable increment = () -> count[0]++;
increment.run();
System.out.println(count[0]); // 1 if executed sequentially once
~~~

Local variable `count` is not reassigned, so it is effectively final. Element `count[0]` is modified. However, `count[0]++` consists of read, add, write, and is **not atomic** when two threads execute it concurrently. Using an array merely to "bypass" capture rules hides shared mutable state and makes code hard to understand.

Holder objects, `ArrayList`, `StringBuilder`, etc. can also be captured by reference. A final reference does not automatically make operations on those objects thread-safe.

### 9.2. Use atomic primitives when a shared counter is needed

~~~java
// File: AtomicCapture.java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

public final class AtomicCapture {
    public static void main(String[] args) {
        AtomicInteger counter = new AtomicInteger();

        IntStream.range(0, 1_000)
                .parallel()
                .forEach(i -> counter.incrementAndGet());

        System.out.println(counter.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 AtomicCapture.java
java AtomicCapture
~~~

Stdout:

~~~text
1000
~~~

The `counter` reference is effectively final. Each `incrementAndGet()` is atomic; after the terminal operation `forEach` completes, the total is accurately 1000. **The processing order of elements in a parallel stream is not guaranteed**; do not rely on auxiliary print/update order to infer correctness.

When the goal is simply summing/counting in a stream, it is usually simpler to avoid shared mutable state:

~~~java
long total = java.util.stream.IntStream.range(0, 1_000).parallel().count();
// total is 1000
~~~

That is a reduction managed by the stream API, rather than updating a shared counter from each callback.

### 9.3. Visibility and happens-before remain a separate responsibility

If a lambda is executed by another thread, effective finality only constrains the **local variable binding**. For a captured mutable object, state modifications from one thread may require `synchronized`, `volatile`, atomic classes, or appropriate concurrent mechanisms so other threads see the right data.

`Thread.start()` and `Thread.join()` have relevant *happens-before* rules, but do not replace designing synchronization for reads/writes **occurring concurrently**. An API accepting a lambda may run the callback 0 times, 1 time, or many times, synchronously or asynchronously; read the API contract rather than inferring from lambda syntax.

## 10. How does the compiler represent captures?

Example:

~~~java
// Illustration inside a method
int offset = 10;
java.util.function.IntUnaryOperator add = x -> x + offset;
~~~

There needs to be a way for the lambda body to use `offset = 10` even after the enclosing method has finished. `javac` in modern JDKs typically compiles lambdas via `invokedynamic`, `LambdaMetafactory`, bootstrap metadata, and synthetic methods like `lambda$...`; captured values can be passed in when creating the functional object.

However, **the JLS guarantees behavior, not a single fixed layout of fields/classes/bytecode**. Do not assume:

- Each lambda is created as a separate `Outer$1.class` like an anonymous class.
- Every lambda evaluation creates a new object (non-capturing lambdas may be reused).
- Synthetic method names or the argument order of `invokedynamic` are identical across all `javac` versions.
- A lambda captures a "pointer to a stack local" that can still mutate after the method finishes.

To inspect an actual build:

~~~bash
javap -c -p FirstCapture
javap -v -p FirstCapture
~~~

`-c` prints bytecode instructions, `-p` reveals private/synthetic members, and `-v` expands constant pool/bootstrap metadata. Look for `invokedynamic` and captured arguments, but treat this as evidence **of the compiler/JDK in use**, not a mandatory bytecode pattern.

## 11. Program comparing snapshots with current state

File `CaptureComparison.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.IntSupplier;
import java.util.function.Supplier;

public final class CaptureComparison {
    private int field = 1;

    IntSupplier readField() {
        return () -> field;
    }

    public static void main(String[] args) {
        int local = 7;
        IntSupplier localReader = () -> local;

        CaptureComparison owner = new CaptureComparison();
        IntSupplier liveField = owner.readField();
        int snapshot = owner.field;
        IntSupplier frozenField = () -> snapshot;

        List<String> words = new ArrayList<>();
        Supplier<Integer> size = words::size;

        owner.field = 9;
        words.add("one");
        words.add("two");

        System.out.println(localReader.getAsInt());
        System.out.println(liveField.getAsInt());
        System.out.println(frozenField.getAsInt());
        System.out.println(size.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 CaptureComparison.java
java CaptureComparison
~~~

Stdout:

~~~text
7
9
1
2
~~~

| Expression | Value held/read | Result |
| --- | --- | --- |
| `() -> local` | Captures primitive local `7` | `7` |
| `() -> field` in `readField()` | Lambda uses enclosing instance, reads field on call | `9` |
| `() -> snapshot` | Captures local `snapshot = 1` | `1` |
| `words::size` | Holds receiver `words`, calls `size()` when invoked | `2` |

The example runs sequentially, so the result does not require cross-thread visibility guarantees. If similar mutable field reads/writes are used across multiple threads, a synchronization mechanism must be designed.

## 12. Common errors and fixes

| Error/misconception | Cause | Solution |
| --- | --- | --- |
| `local variables referenced from a lambda expression must be final or effectively final` | Local/parameter was reassigned | Keep the local stable or create a new local snapshot |
| Variable inside lambda is uninitialized | Violates definite assignment | Assign validly on all execution paths before capturing |
| Expecting lambda to see new value of local after `x = ...` | Local capture holds value; reassignment also causes compile error | If live state is needed, use a field/holder with clear ownership |
| Expecting `final List` to be immutable | Final only prevents reassigning the reference | Use immutable data or a snapshot if needed |
| Basic-for `i++` fails capture check | `i` is not effectively final | `int step = i` in the body of each iteration |
| Using `int[1]` to share a counter across threads | Increment is not atomic | Use reduction/AtomicInteger or proper synchronization |
| Lambda runs after method returns, thinking local disappears | Captured the needed value already | No need to keep the method's stack frame |
| Confusing `this` in lambda with anonymous class | Lexical `this` is different | Write `Outer.this`/explicit receiver when needed |
| Assuming creating a lambda pre-evaluates its body | Creating a lambda differs from calling its functional method | Distinguish creation time and invocation time |
| Thinking `javap` must show `Outer$1.class` | Lambda implementation is not required to generate a class file | Use `javap -v`, inspect actual call site |

## 13. Checklist and self-check

Before writing a callback, determine in order: which names are locals/parameters that must be effectively final; which names are fields that can be read dynamically; whether a snapshot or latest state is needed; whether the callback can run after the method or on another thread; whether the callback can be called multiple times/concurrently; and whether reduction/immutable input can be used instead of shared mutation.

**Question 1.** Is `int a = 2; Runnable r = () -> System.out.println(a);` valid?  
**Yes**, if `a` is not reassigned; it is effectively final even without writing `final`.

**Question 2.** Is `int a = 2; a = 2;` still effectively final?  
**No.** Reassigning with the same value is still a second assignment.

**Question 3.** Does a lambda capturing a `List` and calling `list.add(...)` cause an error?  
**No, if the reference variable is not reassigned.** However, the list is mutable and may require synchronization when used across multiple threads.

**Question 4.** Why does a lambda created in a method that has already returned still work?  
The captured local value is retained to execute the callback later; it does not depend on the original stack frame remaining alive.

**Question 5.** Why does basic `for` not directly capture `i`?  
`i++` modifies `i`; a separate local `step = i` is needed in each iteration.

**Question 6.** Are `final int[] count = {0}` and lambda `() -> count[0]++` thread-safe?  
**Not by default.** A final reference does not make element increment atomic.

**Question 7.** Can a lambda reading an instance field modified after creation see the new value?  
**Yes in a sequential program**, because reading the field happens when the callback is invoked. In multi-threaded programs, visibility rules are additionally required.

**Question 8.** What is `this` of a lambda in an instance method?  
It is the enclosing instance according to lexical context, different from `this` of an anonymous class.

**Question 9.** Need the field value at the time the lambda is created?  
Read the field into a local `int snapshot = this.field;` and capture that non-reassigned local.

**Question 10.** Is a non-capturing lambda required to create a new instance every time?  
**There is no such guarantee.** Do not rely on the object identity of a lambda.

### Official references

- [Java Language Specification §4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): effectively final and definite assignment.
- [Java Language Specification §15.27 — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27): lambda scope and semantics.
- [Java Language Specification §15.13 — Method Reference Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.13): bound receivers and method references.
- [Java Language Specification §17.4 — Memory Model](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4): visibility, happens-before, and multithreading.

**Key note:** effectively final is a rule of **not reassigning a local variable/parameter**. A lambda can retain **captured primitive values or reference values**; it does not automatically freeze mutable objects. If a callback runs asynchronously, thread safety is a separate responsibility that must be explicitly designed.