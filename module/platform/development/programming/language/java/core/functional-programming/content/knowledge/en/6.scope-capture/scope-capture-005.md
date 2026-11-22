# Accessing Instance Fields and Static Fields from Lambdas in Java

## 1. Objectives

In Java, a **lambda expression** can use data declared outside its body. However, three kinds of data must be distinguished:

1. **Local variables and parameters of the enclosing method**: can only be referenced from a lambda when they are **final** or **effectively final**.
2. **Instance fields**: a lambda can access and update them through the object it sees, including **this.field** in an instance context.
3. **Static fields (class fields)**: a lambda can access and update them through the class, e.g. **TypeName.field**, if access rules allow.

The effectively final rule applies to **captured local variables**, not forbidding a lambda from modifying fields of an object. This distinction is very important when writing callbacks, event handlers, Streams, background tasks, and multithreaded code.

After this lesson, you will be able to accurately explain how a lambda reads instance and static fields; understand **this**, name scope, and when a lambda sees values; avoid misconceptions about immutability, cross-thread visibility, and race conditions; and verify behavior with a standalone Java 17 example.

## 2. What Can a Lambda Access?

A lambda written within the scope of a class or method can use names available under Java's normal scope and access rules. For example:

~~~java
class Counter {
    private int count;                // Instance field
    private static int allUpdates;    // Static field

    void register() {
        int increment = 2;           // Effectively final local variable

        Runnable action = () -> {
            count += increment;
            allUpdates++;
        };
        action.run();
    }
}
~~~

This is a structural illustration snippet, not a standalone runnable program with `main`.

In the lambda above:

- **increment** is a local variable. It is not reassigned after initialization, so it is effectively final and can be captured by the lambda.
- **count** is an instance field. Because the lambda is inside an instance method, the name **count** here implicitly means **this.count**.
- **allUpdates** is a static field. It belongs to the `Counter` class; it can be written explicitly as **Counter.allUpdates**.
- Both update statements run **when `action.run()` is called**, not when the lambda expression is created.
- Both **count += increment** and **allUpdates++** produce side effects, so this lambda is not a pure computation.

Note: the code above runs correctly in the single-threaded illustration, but the **+=** and **++** updates do not automatically become atomic if multiple threads execute concurrently.

## 3. Distinguishing Local Variable Capture from Field Access

### 3.1. Local variables must be final or effectively final

Java requires a local variable referenced by a lambda to be final or **effectively final**. *Effectively final* means that even without writing the **final** keyword, the variable is not reassigned after being assigned a value according to definite assignment rules.

~~~java
void schedule() {
    int step = 5;
    Runnable task = () -> System.out.println(step);
    task.run();
}
~~~

**step** is effectively final, so the snippet above is valid.

The snippet below **does not compile**:

~~~java
void invalid() {
    int step = 5;
    Runnable task = () -> System.out.println(step);
    step = 6; // No longer effectively final.
}
~~~

The reason is not whether the lambda "has run yet or not," but that **the local variable `step` is referenced in the lambda yet reassigned** in the enclosing scope. The compiler rejects it even if the call **`task.run()`** does not appear.

The same rule applies to parameters of the enclosing method if the lambda captures that parameter and the code reassigns the parameter.

### 3.2. Final on a reference does not make the object immutable

~~~java
void register() {
    java.util.List<String> events = new java.util.ArrayList<>();

    Runnable addEvent = () -> events.add("created");
    addEvent.run();

    System.out.println(events); // [created]
}
~~~

The local variable **events** is not reassigned to another `List` object, so it remains effectively final. However, **the `List` object that `events` references is still mutable**. The lambda can call methods that modify that same object.

Distinguish:

- **events = new ArrayList<>()** after capture: reassigns the local variable, breaking effectively final → does not compile.
- **events.add(...)**: modifies the object's state without reassigning the `events` variable → can compile, but introduces side effects.

With multiple threads, concurrently modifying an **ArrayList** via different lambdas is not automatically safe; proper ownership or synchronization is needed.

### 3.3. Instance fields are not constrained by effectively final

~~~java
class Score {
    private int points = 10;

    Runnable bonusTask() {
        return () -> points += 5;
    }
}
~~~

Here **points** is an instance field, not a captured local variable. Java allows the lambda to update that field. What needs to be considered is **invocation timing, business correctness, and synchronization**, not the effectively final condition.

A field declared **final** cannot be reassigned after initialization according to Java's `final` rules. A lambda does not bypass that limit. Yet **final List<String> history** can still have its contents modified if the `List` allows it.

## 4. Lambdas Accessing Instance Fields via this

In an **instance method**, a lambda can reference a field by its short name or **this.field**:

~~~java
class Account {
    private int balance = 100;

    Runnable depositAction(int amount) {
        return () -> {
            this.balance += amount;
        };
    }
}
~~~

**amount** is a parameter of **depositAction**, is captured, and must be effectively final. **this.balance** is a field belonging to the current `Account`. When the task is called, the **balance** field is read and updated at that moment.

If after creating the task another operation changes `balance` before it runs, the task will add to the **current value** of the field, rather than automatically saving a snapshot of the old value.

Illustrative snippet:

~~~java
Account account = new Account();
Runnable deposit = account.depositAction(20);
deposit.run();
~~~

The two snippets are a coordinated illustration; if you want to read `balance` from outside the class, an appropriate accessor or observable result is needed. After one `deposit` run, `account`'s `balance` increases from 100 to 120 according to the example's logic.

**`this` in a lambda** has lexical meaning: it is **`this` of the enclosing object where the lambda is declared**. A lambda does not create an object with its own **`this`** for the author to use in the way an anonymous inner class does.

### 4.1. Difference from anonymous inner classes

~~~java
class IdentityExample {
    private final String name = "outer";

    Runnable lambda() {
        return () -> System.out.println(this.name);
    }

    Runnable anonymous() {
        return new Runnable() {
            private final String name = "anonymous";

            @Override
            public void run() {
                System.out.println(this.name);
                System.out.println(IdentityExample.this.name);
            }
        };
    }
}
~~~

If you call **lambda().run()**, the printed line is **outer**. If you call **anonymous().run()**, it prints **anonymous** then **outer**.

In the lambda, **this** is the current `IdentityExample`. In the **run()** method of the anonymous class, **this** is that anonymous object itself; to reference the enclosing instance you must write **IdentityExample.this**.

This is a difference in lexical scope and class definition; you should not infer that a lambda is always implemented as an anonymous class. The JVM may choose its own lambda implementation strategy, and business code should not depend on the underlying synthetic class identity/type.

### 4.2. A field name shadowed by a local variable

~~~java
class ShadowExample {
    int value = 10;

    void print() {
        int value = 3;
        Runnable task = () -> {
            System.out.println(value);
            System.out.println(this.value);
        };
        task.run();
    }
}
~~~

The output is **3** then **10**: the unqualified name **value** resolves to the local variable, while **this.value** points to the instance field.

A lambda does not create a name-declaration scope completely separate from the enclosing method's local variables. You **cannot redeclare a lambda parameter with the same name as a local variable that already exists** in its enclosing scope. Use clear names and **this.field** when the distinction matters.

## 5. Accessing Static Fields from Lambdas

A **static** field belongs to the class and is shared across instances according to class-field semantics. Lambdas in both **static methods** and **instance methods** can access a static field if visibility rules allow.

~~~java
class Metrics {
    private static int requests = 0;

    static Runnable incrementTask() {
        return () -> Metrics.requests++;
    }
}
~~~

**Metrics.requests** is accessed when the task runs. The code compiles, but the **++** increment is not automatically synchronized. When run concurrently across multiple threads, some increments can be lost.

A static method **has no `this`** corresponding to an instance of the class:

~~~java
class WrongThis {
    int number = 5;

    static Runnable invalid() {
        // Invalid in static context:
        // return () -> System.out.println(this.number);
        return () -> System.out.println("static context");
    }
}
~~~

To read an instance field in a static method, you need a **reference to a specific object**:

~~~java
class Reader {
    private int number = 7;

    static Runnable readLater(Reader target) {
        return () -> System.out.println(target.number);
    }
}
~~~

**target** is a captured local parameter, so it must be effectively final; meanwhile, **target.number** is an instance field read at run time. The two rules do not conflict.

### 5.1. Static fields are not captured like local variables

You can change the value of a static field after creating a lambda:

~~~java
class GlobalState {
    static int level = 1;

    static Runnable showLevel() {
        return () -> System.out.println(GlobalState.level);
    }
}
~~~

If you create **Runnable task = GlobalState.showLevel()**, then assign **GlobalState.level = 9**, and then call **task.run()** on the same thread, the task prints **9**. This does not violate effectively final, because **level is a static field**, not a local variable.

This also explains why a lambda relying on a mutable static field can return different results even when given the same explicit arguments: the actual input also depends on shared state.

## 6. Capture Time vs. Value-Read Time

One of the most error-prone differences is **a retained reference** versus **a field value read later**.

Consider the code:

~~~java
class Temperature {
    int degrees = 20;

    Runnable liveReader() {
        return () -> System.out.println(degrees);
    }

    Runnable snapshotReader() {
        int snapshot = degrees;
        return () -> System.out.println(snapshot);
    }
}
~~~

Call in sequence:

~~~java
Temperature value = new Temperature();
Runnable live = value.liveReader();
Runnable snapshot = value.snapshotReader();
value.degrees = 27;
live.run();
snapshot.run();
~~~

Output:

~~~text
27
20
~~~

- **liveReader** reads the **instance field** when the lambda runs, so it sees 27 in this single-threaded case.
- **snapshotReader** first copies the field value into the local variable **snapshot**. The lambda captures the **int** value of the local variable, so it keeps 20.
- If the captured local variable is a **reference to a mutable object**, the lambda retains that reference; changes to the object's contents can still be observed. "Capturing a reference" does not mean "deep copying."

With multiple threads, a write on one thread and a read on another **do not implicitly have a happens-before relationship**. In that case, you must not assume `liveReader` will definitely see the latest value without synchronization/volatile/atomic or an appropriate memory relationship.

### 6.1. A subtlety with method references

Suppose **handler** is a mutable field holding an object implementing `Runnable`:

~~~java
class DelegateHolder {
    Runnable handler = () -> System.out.println("first");

    Runnable dynamic() {
        return () -> handler.run();
    }

    Runnable bound() {
        return handler::run;
    }
}
~~~

At creation time:

- **dynamic()** creates a lambda that reads the **handler** field when it runs.
- **bound()** creates a bound method reference; the receiver expression **handler** is evaluated when the method reference is created, and the receiver object is retained.

If you later assign **handler = () -> System.out.println("second")**, calling the task from **dynamic()** can print **second**, whereas the task previously created from **bound()** still calls the old `Runnable` object and prints **first** in the single-threaded case above.

The core point is that **the receiver expression of a bound method reference is evaluated when creating the reference**, whereas the lambda **() -> handler.run()** evaluates the `handler` field at runtime. This difference can affect callback design when a dependency can be replaced.

## 7. Standalone Runnable Java 17 Example

The example below demonstrates simultaneously:

- An instance field separate for each object.
- A static field shared across objects.
- A local variable **step** captured by the lambda because it is effectively final.
- Lambdas that can be created earlier yet update fields when **run()** is called.
- The state of objects A and B being updated independently, while static state accumulates.

Create the file **LambdaFieldAccessDemo.java**:

~~~java
public class LambdaFieldAccessDemo {
    private final String name;
    private int instanceCount = 10;
    private static int sharedCount = 100;

    public LambdaFieldAccessDemo(String name) {
        this.name = name;
    }

    public Runnable makeIncrementTask() {
        int step = 3;

        return () -> {
            this.instanceCount += step;
            LambdaFieldAccessDemo.sharedCount += step;

            System.out.println(
                    name + ": instance=" + instanceCount
                    + ", static=" + sharedCount
            );
        };
    }

    public static void main(String[] args) {
        LambdaFieldAccessDemo a = new LambdaFieldAccessDemo("A");
        LambdaFieldAccessDemo b = new LambdaFieldAccessDemo("B");

        Runnable taskA = a.makeIncrementTask();
        Runnable taskB = b.makeIncrementTask();

        taskA.run();
        taskA.run();
        taskB.run();

        System.out.println("A final=" + a.instanceCount);
        System.out.println("B final=" + b.instanceCount);
        System.out.println("Shared final=" + sharedCount);
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac LambdaFieldAccessDemo.java
java LambdaFieldAccessDemo
~~~

Exact output:

~~~text
A: instance=13, static=103
A: instance=16, static=106
B: instance=13, static=109
A final=16
B final=13
Shared final=109
~~~

**Explanation:**

1. A and B each have **instanceCount = 10**; **sharedCount = 100** has only one value at the class level.
2. **taskA** and **taskB** are created, but nothing is updated until **run()** is called.
3. First run of `taskA`: A increases **10 → 13**, shared increases **100 → 103**.
4. Second run of `taskA`: A increases **13 → 16**, shared increases **103 → 106**.
5. Run of `taskB`: B increases **10 → 13**, shared increases **106 → 109**.
6. B still has **13**, A has **16**; shared is **109**. This is a sequential execution on the main thread, so the order and stdout are deterministic.

**step** is not reassigned in **makeIncrementTask**, so it is valid to capture. **name** is a final instance field, while **instanceCount** and **sharedCount** are mutable fields and are read/updated when the lambda runs. **this** inside the lambda is A or B depending on which instance called **makeIncrementTask**.

This example intentionally runs sequentially. If switched to concurrent execution, do not use the result above to infer that **+=** is thread-safe.

## 8. What Do Static Final and Instance Final Mean?

Declaring **final** on a field does not automatically make the entire object graph immutable:

~~~java
class Settings {
    static final java.util.List<String> AUDIT =
            new java.util.ArrayList<>();
}
~~~

The **AUDIT** reference cannot be reassigned after initialization, yet the program can still call **Settings.AUDIT.add("event")**. A lambda can modify this list, creating global side effects and potential bugs in a multithreaded environment.

By contrast, with a final primitive field:

~~~java
class Options {
    final int retryLimit = 3;
}
~~~

Normal code cannot reassign **retryLimit** after proper initialization under Java rules. A lambda cannot change this. If mutable state is needed, design it with a controlled mutable field or use an appropriate state object.

**static final** is often used for constants or fixed references, but it is not a "pure function guarantee seal." When a `static final` value is a mutable object, that object itself can still change through its methods.

## 9. Multithreading: Reading/Writing Fields Is Not Necessarily Safe

### 9.1. Non-atomic increment

~~~java
class Statistics {
    static int total = 0;

    static Runnable newTask() {
        return () -> total++;
    }
}
~~~

If multiple threads run **newTask()** concurrently, **total++** consists of read, add, and write steps and can lose updates. Similarly, **this.instanceCount++** can race when the same instance is used by multiple threads.

A **lambda** having a SAM does not create synchronization. Using **volatile** for an `int` variable helps with **value visibility and memory ordering** according to the Java Memory Model, but **volatile++ is still not an atomic increment**.

### 9.2. Atomic solution for an independent counter

~~~java
import java.util.concurrent.atomic.AtomicInteger;

class SafeStatistics {
    private static final AtomicInteger TOTAL = new AtomicInteger();

    static Runnable newTask() {
        return TOTAL::incrementAndGet;
    }

    static int total() {
        return TOTAL.get();
    }
}
~~~

This snippet is an example of a standalone class without `main`. **AtomicInteger.incrementAndGet()** atomically increments a counter, and the returned `int` value can be discarded when used as a **Runnable**. If the count can exceed `int` limits, appropriate overflow/bounding rules must be in place; `AtomicInteger` does not turn `int` into an unbounded integer.

For an object with multiple fields that have related invariants, merely changing each field to `AtomicInteger` **does not guarantee** that updating multiple fields together is atomic. In that case, `synchronized`, locks, message queues, immutable state, or another mechanism is needed depending on the goal.

### 9.3. Object-level synchronized example

~~~java
class SafeAccount {
    private int balance;

    synchronized void deposit(int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("Negative amount");
        }
        balance = Math.addExact(balance, amount);
    }

    synchronized int balance() {
        return balance;
    }

    Runnable depositTask(int amount) {
        return () -> deposit(amount);
    }
}
~~~

**amount** is validly captured if not reassigned. The **deposit** method locks on the current **SafeAccount** instance, so multiple threads calling into **the same instance** are coordinated for both checking and writing. A synchronized method on an **instance** does not automatically protect a static field shared across multiple instances.

These snippets do not have a standalone `main`; they illustrate how to protect state when a lambda may run on multiple threads.

## 10. Side Effects, Testing, and Better Design

A lambda reading instance fields or mutable static fields often depends on **state outside its declared parameters**. Therefore, if you want a computation function that is easy to test, consider passing the needed values as parameters and returning a result instead of mutating fields.

Example of a pure computation style:

~~~java
static int nextCount(int current, int step) {
    return Math.addExact(current, step);
}
~~~

Orchestration code can call **nextCount(instanceCount, step)** and then update the field at a controlled boundary. **nextCount** itself modifies no fields, reads no global state, and always produces the same behavior for the same two arguments.

A layered design often has:

- **Reading data / receiving events:** depends on environment, I/O, time, users.
- **Computing results:** functions taking concrete values; easy to test independently.
- **Updating state or sending effects:** in the state-owning layer, with clear error and synchronization contracts.

Not every callback needs to be turned into a pure function. What matters is recognizing where side effects occur and only allowing updates within appropriate boundaries.

### 10.1. Mutable static fields and testing

If tests share a **static int state**, an earlier test can leave behind a value that causes a later test to fail even when each individual test's logic is correct. To avoid order dependence:

- Limit mutable static state in business logic.
- Move needed state into an instance created per test, or a dependency passed in from outside.
- If static state must be used, manage its lifecycle/reset according to the test contract and avoid parallel tests without isolation.
- Assert both return values and state/effects if those are observable behaviors.

### 10.2. Lambda lifecycle and references to this

A lambda referencing **this.instanceField** can retain a reference to the enclosing instance. If the callback is stored long-term in a static registry or a longer-lived object, it can keep that instance alive longer than intended.

For example, registering a lambda as a listener without unregistering it when a component is destroyed can make it harder for the component to be garbage-collected while the registry still holds the lambda. Unregister policies, subscription lifecycles, and callback ownership should be designed clearly. Not every lambda retains **this**; it depends on what it references and how the compiler/JVM implements it.

## 11. Common Mistakes

| Mistake | Why it is wrong | How to handle |
| --- | --- | --- |
| Thinking fields must be effectively final | That rule applies to captured local variables/parameters | Distinguish locals from instance/static fields |
| Thinking a lambda snapshots every field's value upfront | A lambda normally reads fields at execution time | Use a local snapshot if you want to freeze a value |
| Reassigning a local variable after capture | The variable loses effectively final status | Extract a fixed local value or change the design |
| Thinking **final List** cannot be modified | Final locks the reference, not the contents | Use appropriate immutable data/snapshots |
| Using **this** in a static method | A static context has no `this` instance | Pass a specific object as a parameter |
| Confusing **this** of a lambda with an anonymous class | Lambdas use lexical `this` | Use **this.field**, **Outer.this** in the right context |
| Using a mutable static field for per-object data | Every instance shares the same field | Use an instance field if separate state is needed |
| Believing **volatile++** is atomic | Volatile does not make read-modify-write atomic | `AtomicInteger`, locks, or ownership design |
| Running callbacks updating mutable objects in parallel streams | Can race and lose updates | Independent data or synchronization mechanisms |
| Storing callbacks referencing `this` for too long | Can extend object lifetimes | Manage listener registration/unregistration clearly |

## 12. Practice Exercises

### Exercise 1: Read the new value or the old value?

~~~java
class Box {
    int value = 2;

    Runnable live() {
        return () -> System.out.println(value);
    }

    Runnable snapshot() {
        int saved = value;
        return () -> System.out.println(saved);
    }
}
~~~

Create a box, obtain both `Runnable`s, assign **box.value = 8**, and then call **live.run()** and **snapshot.run()** in sequence on the same thread.

**Answer:** prints **8** then **2**. `live` reads the field at run time; `snapshot` captures the local `int` taken when the `Runnable` was created.

### Exercise 2: Predict instance and static results

~~~java
class Counts {
    int own = 1;
    static int shared = 10;

    Runnable task() {
        return () -> {
            own++;
            shared++;
        };
    }
}
~~~

Create two instances **a** and **b**; call **a.task().run()** twice and **b.task().run()** once, sequentially. What are the final values of **a.own**, **b.own**, and **Counts.shared**?

**Answer:** **a.own = 3**, **b.own = 2**, **Counts.shared = 13**. The `own` field is independent per instance; the `shared` field accumulates from both.

### Exercise 3: Identify non-compiling code

~~~java
int step = 1;
Runnable action = () -> System.out.println(step);
step++; // Error: captured local variable was modified.
~~~

**Fix:** keep `step` effectively final; if you want to update controlled state, put that state in an explicitly owned object or change the design to compute a new value. Do not use a single-element array just to "work around" the effectively final rule if the real goal is shared state.

### Exercise 4: Write a safer callback

Design a counter shared by tasks updating from multiple threads. Determine whether the state should be instance or static; choose `AtomicInteger` or `synchronized` appropriately; handle overflow if applicable; and test correctness when multiple tasks complete. Finally, explain why a lambda does not make thread-safety appear automatically.

## 13. Key Takeaways

**A lambda can read/modify instance and static fields** according to Java access rules. **Effectively final** applies to local variables and enclosing method parameters captured by a lambda, not as a ban on modifying fields.

- **this** in a lambda is the enclosing instance where the lambda is declared; a static context has no `this`.
- An **instance field** belongs to each object; a **static field** is shared at the class level.
- A lambda reads **the current field at runtime** unless you intentionally capture the value into a local variable or bind a receiver appropriately.
- **Being accessible does not mean thread-safe**: `volatile` does not make `++` atomic, and mutable static state can affect multiple instances/tests.
- When logic should be easy to test, separate computation from input values and place state-updating effects at a clear boundary.
