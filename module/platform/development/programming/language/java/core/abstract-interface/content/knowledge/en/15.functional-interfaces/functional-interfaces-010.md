# Choosing a Custom Interface or Using Runnable, Callable, and java.util.function

When you need to pass behavior into another method, Java typically allows using a lambda or a method reference. The important question is which interface type accurately describes the contract of that behavior. Prioritize the type that the API requires; if you are designing the API yourself, choose a standard type when the meaning already matches and create a custom interface when the business contract needs its own name or rules.

## 1. Distinguishing Regular Interfaces and Functional Interfaces

A **functional interface** is an interface that has exactly one abstract method to implement. It can be annotated with @FunctionalInterface so that the compiler checks this condition. The interface can still have default and static methods.

~~~java
@FunctionalInterface
interface DiscountPolicy {
    long finalPrice(long originalPrice);
}
~~~

Because there is only one abstract operation, we can pass a lambda such as `price -> price * 90 / 100`. An interface name like DiscountPolicy tells the reader which discount policy the lambda represents.

A regular interface can have multiple abstract methods and represents a contract consisting of multiple operations. A lambda cannot implement an interface with multiple abstract methods on its own; that case usually requires an implementation class or an anonymous class.

## 2. When to Use the Standard Types?

| Need | Suitable Type | Contract |
| --- | --- | --- |
| A task that takes no input and returns no result | Runnable | `void run()` |
| A task that has a result and can throw a checked exception | Callable&lt;T&gt; | `T call() throws Exception` |
| Transform a value T into R | Function&lt;T, R&gt; | `R apply(T value)` |
| Check a value and return true/false | Predicate&lt;T&gt; | `boolean test(T value)` |
| Accept a value and perform an action | Consumer&lt;T&gt; | `void accept(T value)` |
| Supply a value without needing input | Supplier&lt;T&gt; | `T get()` |
| Transform a value into the same type | UnaryOperator&lt;T&gt; | A specialization of Function&lt;T, T&gt; |
| Combine two values of the same type into one value of the same type | BinaryOperator&lt;T&gt; | A specialization of BiFunction&lt;T, T, T&gt; |

The types in the table belong to Java's standard APIs; Runnable is in java.lang, Callable is in java.util.concurrent, and Function, Predicate, Consumer, Supplier, and their variants are in java.util.function. They are suitable when your contract genuinely matches the meaning and signature of that type.

### Example: Using java.util.function

File `StandardFunctionsDemo.java`:

~~~java
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.function.Supplier;

public class StandardFunctionsDemo {
    public static void main(String[] args) {
        Function<String, Integer> length = String::length;
        Predicate<Integer> isPositive = n -> n > 0;
        Supplier<String> greeting = () -> "Xin chao";
        Consumer<String> print = System.out::println;

        System.out.println(length.apply("Java"));
        System.out.println(isPositive.test(3));
        System.out.println(greeting.get());
        print.accept("Hello");
    }
}
~~~

Run with Java 17 or later:

~~~bash
javac StandardFunctionsDemo.java
java StandardFunctionsDemo
~~~

Output:

~~~text
4
true
Xin chao
Hello
~~~

In this example, Function transforms a string into its length, Predicate checks for a positive number, Supplier creates a greeting, and Consumer prints a string. There is no need to define a new interface yourself because the meaning is already clearly expressed by the standard types.

## 3. When Should You Create a Custom Functional Interface?

Create a custom interface when the type name helps express business meaning, when the contract needs specific rules, or when the method needs to declare a checked exception that standard types do not support. For example, DiscountPolicy clearly expresses that this is a policy for calculating the final price; Function&lt;Long, Long&gt; only indicates that there is a numeric transformation.

File `DiscountDemo.java`:

~~~java
@FunctionalInterface
interface DiscountPolicy {
    long finalPrice(long originalPrice);
}

public class DiscountDemo {
    public static void main(String[] args) {
        DiscountPolicy memberDiscount = price -> price * 90 / 100;
        System.out.println(memberDiscount.finalPrice(100_000L));
    }
}
~~~

Run:

~~~bash
javac DiscountDemo.java
java DiscountDemo
~~~

Output:

~~~text
90000
~~~

The name DiscountPolicy clarifies the purpose of the parameter that the method accepts. In public APIs or business code, a type with a domain-specific name is often easier to read when that contract genuinely has its own meaning.

Another case is checked exceptions. The methods of Function and most types in java.util.function do not declare checked exceptions. If the behavior needs to throw IOException, you can handle the exception right inside the lambda, wrap the exception in an unchecked exception, or define a custom contract:

~~~java
@FunctionalInterface
interface IOFunction<T, R> {
    R apply(T input) throws java.io.IOException;
}
~~~

You should only create a type like IOFunction when propagating checked exceptions is a useful part of the API. Avoid creating interfaces such as MyFunction&lt;T, R&gt; merely to duplicate Function&lt;T, R&gt; without adding any meaning or behavior.

## 4. Runnable and Callable in Asynchronous Tasks

Runnable and Callable both describe tasks, but their contracts differ:

- **Runnable** does not return a result and the run() method does not declare any checked exceptions. Use it when you need to perform an action, such as logging or updating state.
- **Callable&lt;T&gt;** returns a value of type T and the call() method can declare Exception. Use it when the task needs to return a result or propagate a checked exception back to where the result is retrieved.
- When submitting a task using ExecutorService.submit(...), the result is a Future. Future.get() waits for the task to complete; with Callable, it returns the result. With Runnable, Future.get() returns null when the task completes normally.
- Future.get() can throw InterruptedException or ExecutionException. Real-world code should handle these two cases appropriately; if you catch InterruptedException without rethrowing it, you usually need to restore the interrupt flag using Thread.currentThread().interrupt().

File `ExecutorTasksDemo.java`:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ExecutorTasksDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<?> completed = pool.submit(
                () -> System.out.println("Runnable ran")
            );
            Future<Integer> answer = pool.submit(() -> 40 + 2);

            completed.get();
            System.out.println(answer.get());
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Run:

~~~bash
javac ExecutorTasksDemo.java
java ExecutorTasksDemo
~~~

Output:

~~~text
Runnable ran
42
~~~

The single-threaded executor runs the two tasks in the order they were submitted, so the output above is consistent. finally ensures shutdown() is called even if retrieving the result encounters an error. shutdown() stops accepting new tasks and gives submitted tasks a chance to complete; it does not wait on its own like awaitTermination().

Do not confuse Callable with Supplier&lt;T&gt;. Both can return T, but Supplier&lt;T&gt; is a general-purpose value-providing type that does not declare checked exceptions; Callable&lt;T&gt; is designed for result-returning tasks in concurrency APIs and can throw Exception. Use the right type according to the API you are calling.

## 5. Useful Variants

When working with primitive types frequently, using specialized interfaces can avoid unnecessary boxing/unboxing, for example IntPredicate, IntConsumer, IntSupplier, IntUnaryOperator, LongUnaryOperator, or ToIntFunction&lt;T&gt;. When accepting two parameters, consider BiFunction&lt;T, U, R&gt;, BiPredicate&lt;T, U&gt;, or BiConsumer&lt;T, U&gt;. Do not choose a more complex type if Function, Predicate, Consumer, or Supplier already describes the contract sufficiently.

Some standard functional interfaces also support behavior composition: Function has compose() and andThen(), Predicate has and(), or(), and negate(), and Consumer has andThen(). These methods are useful when you need to combine multiple steps while keeping data types clear.

## 6. Type Selection Process

1. **Check the API signature first.** If the method requires Runnable, Callable&lt;T&gt;, or another standard type, provide that exact type.
2. **Match the number of parameters and the result type.** No input/no result is usually Runnable; no input/with result can be Supplier&lt;T&gt; or Callable&lt;T&gt; depending on the API and exception rules; T to R is Function&lt;T, R&gt;; T to boolean is Predicate&lt;T&gt;.
3. **Consider the business meaning.** If a type name such as DiscountPolicy, RetryPolicy, or AuthorizationRule makes the contract significantly clearer, a custom interface may be appropriate.
4. **Consider exceptions and specific constraints.** If you need to declare a checked exception or the API requires its own contract, consider a custom interface.
5. **Distinguish one behavior from multiple operations.** A single abstract operation fits a lambda; multiple independent operations usually require a regular interface.
6. **Prioritize simplicity and consistency.** Do not create multiple equivalent types that differ only in name if they do not express a useful distinction.

## 7. Common Mistakes

- Choosing Runnable for work that needs to return data, and then trying to get the result from the Runnable's Future. Use Callable&lt;T&gt; when submitting requires a result.
- Using Supplier&lt;T&gt; for a task submitted to an API that requires Callable&lt;T&gt;. The two types have similar signatures but are not automatically interchangeable; use a lambda that matches the target type required by the API.
- Using Function&lt;T, Boolean&gt; for true/false conditions. Predicate&lt;T&gt; expresses the intent more clearly and provides condition-combining operations.
- Creating a custom interface that duplicates Function or Consumer completely without any additional meaning. This gives the API more types to learn and convert between.
- Forgetting that a lambda needs a target type. Declare the type explicitly or pass the lambda to a method with a functional interface parameter; the target type cannot be inferred for a standalone lambda like an ordinary value.
- Providing multiple overloads that differ only by functional interfaces with similar signatures. Some lambdas can become hard to select or cause ambiguity; distinct method names or clear parameter types make the API easier to use.
- Forgetting to handle errors when calling Future.get(). Errors in the task are usually wrapped in an ExecutionException; you need to inspect the root cause when diagnosing.

Practical guideline: use a standard interface when it accurately expresses the contract and fits the API; use a custom interface when a domain-specific name, checked exception, or specific rule makes the contract clearer. For concurrency tasks, clearly distinguish between an action without a result (Runnable) and a task with a result (Callable&lt;T&gt;).
