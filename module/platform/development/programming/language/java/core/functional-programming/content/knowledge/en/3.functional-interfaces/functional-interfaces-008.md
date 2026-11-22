# Recognizing `Runnable`, `Callable`, and `Comparator` in Java

## 1. Objectives

**Runnable**, **Callable**, and **Comparator** are three familiar functional interfaces in Java. They can all be implemented using **lambda expressions** or **method references** when compatible, yet they solve three very different problems:

- **Runnable** describes an action that returns no result.
- **Callable<V>** describes a task that returns a value of type **V**, and may declare checked exceptions.
- **Comparator<T>** describes a rule for comparing two values of type **T** to determine ordering.

After this lesson, you will be able to read the single abstract method (**SAM — Single Abstract Method**) signature to recognize each interface; choose the right one for your purpose; write Java 17 examples using lambdas, method references, and ExecutorService; explain the comparison contract; and avoid mistakes involving ordering, asynchronous tasks, and exception handling.

## 2. Recap: Why Are These Three Interfaces Functional Interfaces?

A **functional interface** has exactly one abstract method counted under Java's rules. The interface may also have **default**, **static**, and **private** methods, as well as declarations matching public methods of **Object**, and still satisfy the functional interface condition.

**@FunctionalInterface** is an annotation recommended so the compiler checks the “one SAM” contract, though a valid interface remains a functional interface even without that annotation.

Example:

~~~java
@FunctionalInterface
interface Action {
    void execute();

    default void describe() {
        System.out.println("Action");
    }
}
~~~

**Action** has one SAM, **execute()**; the **default** method does not become a second SAM. Therefore, an object can be created via **Action action = () -> System.out.println("Done");**.

A lambda implements **the body of the SAM**, while the lambda's type is inferred from the target-type context (**target typing**). Without a matching SAM type, a standalone lambda does not carry a functional type to initialize an ordinary variable.

## 3. Quick Identification Table

| Interface | Package | Primary abstract method | Parameters | Result | Checked exceptions |
| --- | --- | --- | --- | --- | --- |
| **Runnable** | **java.lang** | **void run()** | None | Returns no value | **run** does not declare **throws** |
| **Callable<V>** | **java.util.concurrent** | **V call() throws Exception** | None | Returns **V** | **call** is allowed to throw checked exceptions |
| **Comparator<T>** | **java.util** | **int compare(T a, T b)** | Two **T** values | Negative, 0, or positive integer | **compare** does not declare checked exceptions |

Quick selection rules:

1. Have **work to run**, no return value needed: think of **Runnable**.
2. Have **work to run**, need to **receive a result** or want to declare checked exceptions: think of **Callable<V>**.
3. Need to **define an ordering between two objects**, for sorting, ordered sets, or ordered maps: think of **Comparator<T>**.

**Comparator** does not represent a background task. Even though it is also a functional interface, it answers “**does a come before, equal, or after b?**”, not “**what work should run?**”.

## 4. Runnable: An Action with No Return Value

### 4.1. Signature and Lambda

~~~java
@FunctionalInterface
public interface Runnable {
    void run();
}
~~~

This is an abbreviated illustration of **java.lang.Runnable**'s SAM signature, not a request to redeclare the built-in interface.

Usage example:

~~~java
Runnable printMessage = () -> System.out.println("Hello");
printMessage.run();
~~~

**Runnable** takes no parameters in **run()**, returns no value, and declares no checked exceptions. The lambda above is a valid implementation because its body performs an action without returning a value.

**Taking no parameters** does not mean “cannot access data”. A lambda can capture **final** or **effectively final** local variables, or access object state; those must be considered carefully in multithreaded execution.

### 4.2. Runnable Does Not Create a New Thread by Itself

~~~java
Runnable job = () -> System.out.println(
        Thread.currentThread().getName());

job.run();                 // Calls directly on the current thread.
new Thread(job).start();   // Schedules execution on a new thread.
~~~

**job.run()** is just a normal method call. **new Thread(job).start()** is what asks the JVM to create an execution thread to run the **run** logic. When using an executor, the executor itself manages scheduling.

Do not use thread-name printing examples to claim a fixed output order, because thread scheduling has no guaranteed order without coordination.

### 4.3. Checked Exceptions in Runnable

Because **run()** declares no checked exceptions, a lambda body implementing **Runnable** cannot let a checked exception propagate out directly:

~~~java
// Does not compile if keeping this lambda as-is:
// Runnable invalid = () -> Thread.sleep(100);
~~~

**Thread.sleep(...)** declares **InterruptedException**, so it must be caught or handled inside the lambda:

~~~java
Runnable pause = () -> {
    try {
        Thread.sleep(100);
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
    }
};
~~~

Restoring the interrupted flag is usually the sensible approach when you cannot propagate the checked exception out of **run**'s signature and want outer code to have a chance to observe the stop request. The exact interruption-handling strategy depends on the task's lifecycle.

**Runnable** can still throw unchecked exceptions such as **IllegalArgumentException** or **RuntimeException**; “declares no checked exceptions” does not mean all errors are automatically swallowed or handled by the system.

## 5. Callable<V>: A Task That Returns a Result

### 5.1. Signature and Generic Type

~~~java
@FunctionalInterface
public interface Callable<V> {
    V call() throws Exception;
}
~~~

This is an abbreviated illustration of **java.util.concurrent.Callable**'s SAM signature.

Example:

~~~java
Callable<Integer> calculate = () -> 6 * 7;
Integer answer = calculate.call(); // 42
~~~

Here **call()** returns **Integer**. Because the method declaration has **throws Exception**, a direct caller must handle or declare the appropriate exception, even when the concrete lambda only does simple arithmetic.

You can write **Callable<String>**, **Callable<List<Order>>**, or **Callable<Report>** depending on the result. When a task has no meaningful value yet you still want **Callable<Void>**, the lambda must return **null**, because **Void** has no normal values to instantiate. For simple tasks returning nothing, **Runnable** usually expresses intent more clearly.

### 5.2. Callable Does Not Run Asynchronously by Itself

Like Runnable, **calculate.call()** is a direct call and runs on the calling thread. To have it scheduled by an executor, use **ExecutorService.submit(Callable<V>)** and receive a **Future<V>**.

~~~java
ExecutorService executor = Executors.newSingleThreadExecutor();
try {
    Callable<Integer> calculate = () -> 21 * 2;
    Future<Integer> future = executor.submit(calculate);
    Integer result = future.get(); // Waits for completion, then gets 42.
} finally {
    executor.shutdown();
}
~~~

This is an **illustrative snippet** placed inside a method that handles/declares checked exceptions and imports classes from **java.util.concurrent**, not a standalone program. The complete runnable program appears in section 8.

**Future.get()** can block the waiting thread until the task completes, or terminates due to interruption/cancellation/failure. If the task throws an exception inside the executor, **get()** typically throws **ExecutionException** with the root cause in **getCause()**. **get()** can also throw **InterruptedException** if the waiting thread is interrupted and **CancellationException** (unchecked) if the future was cancelled.

**shutdown()** prevents the executor from accepting new tasks and initiates termination after already-submitted tasks; by itself it does not guarantee waiting for all of them to finish. If you need to wait with a timeout, use **awaitTermination(...)** or wait on the **Future** objects according to your application's contract.

### 5.3. Choosing Runnable or Callable When Submitting?

**ExecutorService** has overloads accepting both **Runnable** and **Callable**:

~~~java
Runnable save = () -> System.out.println("Saved");
Callable<Integer> count = () -> 3;

Future<?> saveFuture = executor.submit(save);
Future<Integer> countFuture = executor.submit(count);
~~~

With **submit(Runnable)**, **Future.get()** returns **null** upon success, because the task itself has no result. With **submit(Callable<Integer>)**, **Future.get()** returns the **Integer** produced by **call()**. There is also an overload **submit(Runnable task, T result)** that lets you associate a pre-supplied result with a Runnable upon completion; therefore, do not assume every future from a Runnable always returns null if another overload is used.

**execute(Runnable)** returns no Future; **submit(...)** returns a Future. Choose the API based on the need to observe completion and handle failures, not just because both can run code.

## 6. Comparator<T>: Defining Order Between Two Elements

### 6.1. Signature and Return Value

~~~java
@FunctionalInterface
public interface Comparator<T> {
    int compare(T a, T b);
    // default/static methods and equals(Object) declaration omitted.
}
~~~

This is an abbreviated description, not the full JDK definition. **Comparator** remains a functional interface even though the API has many **default/static** methods and declares **equals(Object)**: the method matching **Object.equals** does not increase the number of SAMs to implement.

Meaning of **compare(a, b)**:

- **Negative** value: **a** comes before **b**.
- **0**: **a** and **b** are considered equivalent in comparison order.
- **Positive** value: **a** comes after **b**.

Returning exactly -1, 0, or 1 is not required. You must pay attention to the **sign** of the number while maintaining the comparator's consistency rules.

~~~java
Comparator<Integer> ascending = Integer::compare;

System.out.println(ascending.compare(2, 5) < 0); // true
System.out.println(ascending.compare(5, 5) == 0); // true
System.out.println(ascending.compare(7, 5) > 0); // true
~~~

The method reference **Integer::compare** is compatible with two **int** parameters and returns **int**; when used as **Comparator<Integer>**, Java can unbox non-null **Integer** arguments. If arguments can be null, a separate policy is needed.

### 6.2. Do Not Arbitrarily Use Subtraction as a Comparator

~~~java
// Dangerous when subtraction overflows int:
Comparator<Integer> broken = (a, b) -> a - b;

// Safer for int:
Comparator<Integer> safe = Integer::compare;
~~~

For example, with **a = Integer.MAX_VALUE** and **b = -1**, **a - b** overflows and can return a negative value, inverting the order incorrectly. **Integer.compare** handles integer ordering by comparison semantics without depending on an overflowing subtraction result.

For **long**, use **Long.compare** or **Comparator.comparingLong(...)** instead of casting a difference to **int**. For floating-point numbers, be aware of **Double.compare**'s handling of **NaN**, **-0.0**, and **+0.0** if your data can contain them.

### 6.3. Building a Comparator from Properties

~~~java
Comparator<String> byLength =
        Comparator.comparingInt(String::length);
Comparator<String> byLengthThenName =
        byLength.thenComparing(Comparator.naturalOrder());

List<String> sorted = List.of("Java", "Go", "Kotlin", "C")
        .stream()
        .sorted(byLengthThenName)
        .toList();
~~~

The result is **sorted = [C, Go, Java, Kotlin]**. It compares by length first, and on ties compares by **String**'s natural order. **thenComparing** lets you add clear secondary rules; **reversed()** reverses the order; **comparingInt**, **comparingLong**, and **comparingDouble** avoid boxing when extracting primitive sort keys.

**Comparator.naturalOrder()** uses the natural ordering provided by **Comparable** values. For example, **String** has its own natural order, which is not the linguistic collation of every locale; if natural-language collation is needed, use a comparator suited to the locale and business rules.

### 6.4. The Comparator Contract: More Than Just Returning a Number

A valid comparator must satisfy these properties:

1. **Antisymmetry in sign**: **sign(compare(a,b)) = -sign(compare(b,a))**.
2. **Transitivity**: if **compare(a,b) > 0** and **compare(b,c) > 0**, then **compare(a,c) > 0**.
3. **Consistency with comparator equality**: if **compare(a,b) == 0**, the comparison sign of **a** and **b** against any object **z** must be the same under the contract.
4. No dependence on state that changes unexpectedly while a structure is using the comparator, such as mutating data used as sort keys.

A comparator used in **TreeSet** or **TreeMap** defines **order-equivalence** via **compare(a,b) == 0**. This matters because two elements that differ according to **equals** can still be treated as the same key by the comparator.

Example:

~~~java
Comparator<String> onlyLength =
        Comparator.comparingInt(String::length);
java.util.Set<String> words = new java.util.TreeSet<>(onlyLength);
words.add("Go");
words.add("Hi");
System.out.println(words.size()); // 1
~~~

**"Go"** and **"Hi"** are both 2 characters long; the comparator considers them equivalent. In a system that needs to keep both values, add a secondary criterion such as **thenComparing(Comparator.naturalOrder())**. Java does not force every comparator to be consistent with **equals**, but inconsistency can cause ordered sets/maps to behave surprisingly relative to the general **Set/Map** contract.

### 6.5. Handling `null` and Stable Ordering

~~~java
Comparator<String> nullSafe =
        Comparator.nullsLast(Comparator.naturalOrder());
~~~

**nullsFirst** or **nullsLast** lets you specify how `null` is ordered when data allows `null`. Do not assume comparators accept `null` without such a policy.

**List.sort(comparator)** sorts a mutable list in place, whereas **stream().sorted(comparator).toList()** creates a result list from the stream without directly modifying the source list. Mutable sources modified concurrently require separate coordination.

For inputs **with an encounter order**, **Stream.sorted()** is **stable**: elements considered equal by the comparator retain their initial encounter order. For **unordered** streams, there is no corresponding stability guarantee. If the system requires a clear tie-breaker rule, write a comparator with a secondary criterion instead of relying solely on stability.

## 7. Comparing Lambdas and Method References

All three functional interfaces support lambdas or method references when signatures match:

~~~java
Runnable runnable1 = () -> System.out.println("Hello");
Runnable runnable2 = System.out::println;
// Does runnable2 still need an argument for println? See explanation below.
~~~

**Note:** the line **Runnable runnable2 = System.out::println** above **should not be used as a default conversion example**, because **PrintStream.println** has many overloads; depending on context the compiler may pick the no-argument overload. With heavily overloaded APIs, choose the explicit call **() -> System.out.println()** or a method reference to a custom method with a clear signature. A cleaner, more readable example:

~~~java
class Messenger {
    void notifyDone() {
        System.out.println("Done");
    }
}

Messenger messenger = new Messenger();
Runnable r = messenger::notifyDone;
Callable<String> c = () -> "Done";
Comparator<String> comparator = String::compareTo;
~~~

This is an **illustrative snippet** in a valid Java context with the corresponding imports. **String::compareTo** is an instance method reference whose receiver comes from the first parameter, compatible with **compare(String a, String b)**. When comparing potentially null Strings, this method does not handle null automatically.

**Identify by signature, not syntax:** **() -> "OK"** fits **Callable<String>** but not **Runnable** because it must return a result. **(a, b) -> Integer.compare(a, b)** fits **Comparator<Integer>** because it takes two parameters and returns **int**. **() -> doWork()** can fit **Runnable** when the method call's return value is discarded under statement-expression rules; rely on the target type and compiler overload resolution, not solely on the shape of parentheses.

## 8. Standalone Java 17 Example: All Three Interfaces in One Program

The example uses **Runnable** to print a message, **Callable<Integer>** to compute a result, and **Comparator<String>** to sort a list by length and then by name.

Create the file **FunctionalInterfacesDemo.java**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FunctionalInterfacesDemo {
    public static void main(String[] args) throws Exception {
        Runnable announce =
                () -> System.out.println("Runnable: completed");

        Callable<Integer> calculate = () -> 6 * 7;

        Comparator<String> byLengthThenName =
                Comparator.comparingInt((String s) -> s.length())
                          .thenComparing(Comparator.naturalOrder());

        List<String> languages = List.of("Java", "Go", "Kotlin", "C");
        List<String> sorted = languages.stream()
                .sorted(byLengthThenName)
                .toList();

        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<?> announcement = executor.submit(announce);
            Future<Integer> calculation = executor.submit(calculate);

            Object announcementResult = announcement.get();
            Integer value = calculation.get();

            System.out.println("Runnable result: " + announcementResult);
            System.out.println("Callable result: " + value);
            System.out.println("Sorted: " + sorted);
            System.out.println("Source: " + languages);
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Compile and run with JDK 17 or later:

```bash
javac FunctionalInterfacesDemo.java
java FunctionalInterfacesDemo
```

Output:

```text
Runnable: completed
Runnable result: null
Callable result: 42
Sorted: [C, Go, Java, Kotlin]
Source: [Java, Go, Kotlin, C]
```

**Why is the output in this order?**

- **Executors.newSingleThreadExecutor()** provides an executor with one worker thread that processes submitted tasks in submission order. **announcement.get()** in main waits for the **Runnable** to finish before main prints its result, so the Runnable's first line appears before **Runnable result: null**.
- **submit(Runnable)** creates a **Future<?>** whose **get()** returns null when the task succeeds, because no result value is supplied.
- **submit(Callable<Integer>)** creates a **Future<Integer>**; the calculation returns 42 and main reads the value via **get()**. This work runs on the worker thread, while the **System.out.println** statements after **get()** run on the main thread.
- **byLengthThenName** sorts by ascending length; the strings in the example have lengths: **C = 1**, **Go = 2**, **Java = 4**, **Kotlin = 6**. The source list **languages** is unmodified because **stream().sorted(...).toList()** is used.
- **finally** calls **shutdown()** to end the executor's lifecycle. Both **Future.get()** calls already completed successfully before printing, so no ongoing work remains in this normal example.

In real programs, when the main thread is interrupted or a future fails, you must manage task cancellation, executor termination, and error reporting according to application policy. This example is intentionally simple to highlight the three SAM signatures.

## 9. How Do Errors and Exceptions Differ?

### 9.1. Runnable Does Not Declare Checked Exceptions

~~~java
Runnable task = () -> {
    // Must handle IOException internally if calling an API that throws IOException.
    System.out.println("Running");
};
~~~

For a task run by **ExecutorService.submit(Runnable)**, an unchecked exception thrown in **run()** can be stored in the Future; when calling **get()**, it surfaces as an **ExecutionException**. If run via **new Thread(task).start()** or called directly with **run()**, the exception path differs; do not assume every Runnable error surfaces through a Future.

### 9.2. Callable Permits Checked Exceptions

~~~java
Callable<String> task = () -> {
    if (true) {
        throw new java.io.IOException("Cannot read input");
    }
    // Return branch only so the example has a String return type.
};
~~~

This lambda **does not compile** because every path throws an exception and the block after a constant condition creates hard-to-read unreachable/control-flow checks; use the following clear, valid example:

~~~java
Callable<String> task = () -> {
    String value = System.getProperty("example.value");
    if (value == null) {
        throw new java.io.IOException("Missing example.value");
    }
    return value;
};
~~~

**Callable.call()** declares throws Exception, so a checked **IOException** inside the lambda is valid. When executed by an executor and retrieved via **Future.get()**, the exception from the task is wrapped in **ExecutionException**. Distinguish **an exception caused by the task** from **InterruptedException of the waiting thread**.

**Good practice:** handle exceptions at the layer that owns responsibility, log/preserve the necessary cause, and avoid turning every exception into null and letting the pipeline continue with missing data.

## 10. Mistakes from Choosing the Wrong Interface and Misunderstanding SAM

### 10.1. Returning a Value in Runnable

~~~java
// Wrong: Runnable.run() must return void.
// Runnable wrong = () -> { return 42; };

Callable<Integer> correct = () -> 42;
~~~

**Runnable** is for an action; **Callable<Integer>** is for when the value 42 is a task result that needs to be received back.

### 10.2. Comparator Missing Parameters

~~~java
// Wrong: Comparator.compare(a,b) requires two parameters.
// Comparator<String> wrong = () -> 0;

Comparator<String> correct = (a, b) -> a.compareTo(b);
~~~

Do not try to force a zero-argument task into Comparator just because both can use lambdas. The functional type is determined by the SAM signature.

### 10.3. Confusing Callable with Supplier<T>

**Supplier<T>** also has a zero-parameter SAM returning **T**, but it is **T get()** and declares no checked exceptions. **Callable<V>** has **V call() throws Exception**, tied closely to task and concurrency APIs. Choose according to the contract and the consumer:

~~~java
java.util.function.Supplier<Integer> supplier = () -> 42;
Callable<Integer> callable = () -> 42;
~~~

The two lambdas look similar, yet the two variables belong to different interfaces. You cannot directly assign a **Supplier<Integer>** to a **Callable<Integer>** variable; to convert, you can create an adapter such as **Callable<Integer> fromSupplier = supplier::get;**.

### 10.4. Confusing Comparator with Comparable

**Comparable<T>** belongs to **java.lang** and requires **compareTo(T other)**: a natural rule provided by **the class itself**. **Comparator<T>** belongs to **java.util** and requires **compare(T a, T b)**: a comparison rule **external to the class**, allowing multiple variants (by age, name, score, creation date, etc.).

For instance, **String** already implements **Comparable<String>**, yet you can still create **Comparator<String> byLength** to sort by length. **Comparable** is not a two-parameter interface like Comparator, which is another reason to read the SAM signature before choosing.

## 11. Rules for Reading Existing Code

When you encounter a lambda, look at its **target type**:

~~~java
Runnable onClose = () -> releaseResources();
Callable<Boolean> check = () -> isReady();
Comparator<User> byAge = (left, right) ->
        Integer.compare(left.age(), right.age());
~~~

The methods **releaseResources()**, **isReady()**, and class **User** here are illustrative names, not a standalone program. You can quickly deduce:

- **onClose**: runs an action, no need to obtain a value from calling **run()**.
- **check**: a task returning **Boolean**; can be executed directly or submitted to an executor.
- **byAge**: takes two **User** objects and returns a comparison sign based on age; used with sorting or ordered structures.

Then check further: who invokes the lambda, which thread does it run on, is a Future retrieved, is mutable state captured, are there checked exceptions, and is the comparator transitive and stable?

A lambda does not create concurrency by itself, does not guarantee purity by itself, and does not solve errors by itself. Those properties depend on how the interface is used and the specific contract of the program.

## 12. Practice Exercises and Answers

### Exercise 1: Choose the Interface

Match each requirement to the appropriate interface:

1. “After receiving an event, print the status and no return value is needed.”
2. “Compute the invoice total in an executor and retrieve the result after completion.”
3. “Sort employees by name and then by employee ID.”

**Answer:** (1) **Runnable**, (2) **Callable<BigDecimal>** or an appropriate domain result type, (3) **Comparator<Employee>** with **thenComparing**. If requirement (1) needs failure notification, you still need to decide on an exception-observation or Future mechanism depending on how it is run.

### Exercise 2: Read the Comparison Sign

~~~java
Comparator<Integer> descending = (a, b) ->
        Integer.compare(b, a);
~~~

Question: Does **descending.compare(10, 3)** return a negative number, 0, or a positive number?

**Answer:** negative, because **Integer.compare(3, 10) < 0**. Under a descending comparator, 10 comes before 3. Do not assume “a larger first number always makes compare positive”; the sign depends on the **desired order**.

### Exercise 3: Fix an Overflow-Prone Comparator

~~~java
Comparator<Integer> unsafe = (a, b) -> a - b;
~~~

**Suggested answer:**

~~~java
Comparator<Integer> ascending = Integer::compare;
Comparator<Integer> descending =
        (a, b) -> Integer.compare(b, a);
~~~

Test with **Integer.MIN_VALUE**, **Integer.MAX_VALUE**, negative numbers, positive numbers, 0, and duplicate values. All three comparator contract properties are required, not just a few passing calls.

### Exercise 4: Predict Executor Output

Given:

~~~java
ExecutorService executor = Executors.newSingleThreadExecutor();
try {
    Runnable r = () -> { };
    Callable<String> c = () -> "OK";
    System.out.println(executor.submit(r).get());
    System.out.println(executor.submit(c).get());
} finally {
    executor.shutdown();
}
~~~

This is a code snippet inside a method that declares or handles exceptions and has the corresponding imports.

**Answer:** the program prints:

```text
null
OK
```

**Future** returns null from **submit(Runnable)** under the single-argument overload; **Callable<String>** returns **"OK"**. **get()** waits for completion; calling **submit** does not mean the return value is immediately available without waiting.

### Exercise 5: Multi-Criteria Comparator

Create a comparator for strings: **ascending length**, and on equal length **descending natural order**.

**Suggested answer:**

~~~java
Comparator<String> comparator =
        Comparator.comparingInt(String::length)
                .thenComparing(Comparator.reverseOrder());
~~~

This is an illustrative snippet placed in a context importing **Comparator**. Test with **["bb", "aa", "c", "ddd"]**: the result is **[c, bb, aa, ddd]**. If `null` should be allowed, add an explicit null policy, such as wrapping the comparator with **Comparator.nullsLast(...)**.

## 13. Knowledge Checklist During Code Review

Before accepting code using these three interfaces, ask yourself:

1. **Is the SAM type right?** Runnable has no result, Callable has a result, Comparator takes two objects and returns a comparison sign.
2. **Where does the task run?** Calling **run()** or **call()** directly does not start a new thread; **Thread.start()** or an executor determines scheduling.
3. **How are exceptions handled?** **run()** declares no checked exceptions; **call()** can declare them; **Future.get()** can wait and wrap task errors.
4. **Are completion and resource shutdown tracked?** Executors need lifecycle management; do not abandon Futures or worker threads.
5. **Does the Comparator obey its contract?** Avoid overflowing subtraction, check transitivity, tie-breakers, and null handling.
6. **Is the Comparator consistent with `equals` if placed in TreeSet/TreeMap?** **compare(a,b) == 0** determines order-equivalent elements.
7. **Does the lambda access shared mutable state?** Consider thread safety, execution timing, and ordering.

## 14. Takeaways

**Runnable — void run() — action without a return value. Callable<V> — V call() throws Exception — task returning a value and allowed to declare checked exceptions. Comparator<T> — int compare(T,T) — ordering rule based on the sign of the result.**

What they share is having exactly one SAM, so lambdas/method references can be used when types match. What determines the choice among them is **the purpose of the call**, **parameter count**, **return type**, **exception contract**, and **how libraries consume the object**. Reading these factors accurately helps you choose the right interface, avoid confusing concurrency with sorting, and write testable, maintainable Java code.