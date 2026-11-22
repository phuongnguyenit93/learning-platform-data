# Supplier<T>, Consumer<T>, Predicate<T>, and Function<T,R> in Java Generics

## 1. Why does Java need these four functional interfaces?

In `java.util.function`, Java provides **functional interfaces** to treat behavior as a value: it can be stored in variables, passed into methods, returned from methods, and combined with lambdas or method references.

The four most important interfaces have different roles:

- **`Supplier<T>`**: supplies a value of type T **with no arguments**.
- **`Consumer<T>`**: takes T and performs an action, **returning no result**.
- **`Predicate<T>`**: takes T and returns **true/false** as a primitive boolean.
- **`Function<T,R>`**: takes T and **transforms it into R**.

Visual diagram:

~~~text
Supplier<T>         () ───────→ T
Consumer<T>          T ───────→ void
Predicate<T>         T ───────→ boolean
Function<T,R>        T ───────→ R
~~~

Generic parameters allow the compiler to check compatibility between data and behavior. For example, `Function<String,Integer>` takes a String and returns an Integer; `Predicate<User>` checks a User, rather than an arbitrary type bypassed by a raw type.

Quick example:

~~~java
Supplier<String> supplier = () -> "Java";
Consumer<String> consumer = System.out::println;
Predicate<String> predicate = s -> !s.isBlank();
Function<String, Integer> mapper = String::length;

String s = supplier.get();          // "Java"
boolean ok = predicate.test(s);    // true
int size = mapper.apply(s);        // 4
consumer.accept(s);                // Prints Java
~~~

The snippet above assumes importing `java.util.function.*` and being placed inside a method. The complete Java 17+ program, compilation command, and exact stdout are in section 9.

## 2. Functional interface, SAM, and target typing

A **functional interface** is an interface with exactly one abstract method eligible under Java rules; it may have multiple default/static methods. A lambda is converted into an implementation according to the *target type* of the functional interface.

Custom example:

~~~java
@FunctionalInterface
interface TextRule<T> {
    boolean matches(T value);
}
~~~

Usage:

~~~java
TextRule<String> longText = value -> value.length() >= 5;
boolean result = longText.matches("Java"); // false
~~~

`@FunctionalInterface` helps the compiler verify that the declaration still satisfies the SAM rule; the annotation is not required for an interface to be used with lambdas.

The `Supplier`, `Consumer`, `Predicate`, and `Function` interfaces have different SAMs. The compiler infers lambda parameter types from an assignment or method parameter:

~~~java
Predicate<String> a = s -> s.length() > 2;
Function<String, Boolean> b = s -> s.length() > 2;
~~~

The same lambda expression can be assigned to two different target types, but **Predicate does not directly replace Function**: the method contract and available combinator methods differ. `Predicate.test` returns a primitive boolean; `Function.apply` in the second example returns a boxed Boolean.

## 3. Core API table

| Interface | Abstract method | Data flow | Typical combinators |
| --- | --- | --- | --- |
| `Supplier<T>` | `T get()` | No input → T | No predefined `andThen`. |
| `Consumer<T>` | `void accept(T t)` | T → action | `andThen` |
| `Predicate<T>` | `boolean test(T t)` | T → boolean | `and`, `or`, `negate`, `isEqual`, `not` |
| `Function<T,R>` | `R apply(T t)` | T → R | `compose`, `andThen`, `identity` |

Based on the business goal, choose:
- Creating an object/default value on demand: Supplier.
- Logging, printing, sending notifications, operations with side effects: Consumer.
- Filtering or validating conditions: Predicate.
- Extracting fields, normalizing, and converting objects: Function.

They are **behavioral contracts**, not classes that automatically guarantee purity, caching, concurrency, or data validity.

## 4. Supplier<T>: supplying a value right when get() is called

Method:

~~~java
T get();
~~~

Example:

~~~java
Supplier<String> greeting = () -> "Xin chào";
String text = greeting.get();
~~~

The lambda `() -> ...` has no parameters. Creating a supplier **does not immediately execute** the lambda body; computation occurs when the caller invokes `get()`.

### 4.1. Lazy evaluation is not memoization

~~~java
AtomicInteger calls = new AtomicInteger();
Supplier<Integer> next = calls::incrementAndGet;

System.out.println(calls.get()); // 0
System.out.println(next.get());  // 1
System.out.println(next.get());  // 2
~~~

This snippet requires `java.util.concurrent.atomic.AtomicInteger`. Two calls to `get()` produce two different results. Supplier **does not automatically cache** the result or run only once.

If you want cached lazy initialization, you must explicitly design result storage and appropriate synchronization if used across multiple threads. Supplier also does not automatically run on a separate thread: by default `get()` is a synchronous call.

### 4.2. Supplier helps avoid unnecessary computation

~~~java
static String choose(boolean fallbackNeeded,
                     Supplier<String> fallback) {
    return fallbackNeeded ? fallback.get() : "primary";
}
~~~

If fallbackNeeded is false, the supplier is not called. Conversely, passing an already-computed value causes that computation to happen before the call:

~~~java
// Suppose expensiveOperation() is an application-defined method.
Supplier<String> deferred = () -> expensiveOperation();
// String immediate = expensiveOperation();
~~~

The difference lies in **when it is called**, not in any inherent speed of lambdas.

### 4.3. Standard APIs that use Supplier

`Optional.orElseGet(Supplier<? extends T>)` only calls the fallback supplier when the Optional has no value:

~~~java
Optional<String> language = Optional.of("Java");
String name = language.orElseGet(() -> "fallback"); // "Java"
~~~

`Stream.generate(Supplier<T>)` uses a supplier to provide stream elements; you should usually use `limit` when a finite number is wanted:

~~~java
List<String> values = Stream.generate(() -> "A")
        .limit(3)
        .toList(); // [A, A, A]
~~~

These examples require importing `java.util.Optional`, `java.util.stream.Stream`, and `java.util.List` respectively. Stream has its own lazy pipeline mechanism; do not confuse it with the execution timing of `Supplier.get()`.

## 5. Consumer<T>: an action that takes input and returns no value

SAM:

~~~java
void accept(T value);
~~~

Example:

~~~java
Consumer<String> print = System.out::println;
print.accept("Java");
~~~

`Consumer` fits logging, sending events, updating state, and collection terminal operations. Calling `accept` returns `void`, therefore:

~~~java
// String result = print.accept("Java"); // Does not compile.
~~~

If you need a String result produced, use `Function<T,R>`.

### 5.1. Consumer.andThen runs in order

~~~java
Consumer<String> audit =
        s -> System.out.println("audit=" + s);
Consumer<String> send =
        s -> System.out.println("send=" + s);

audit.andThen(send).accept("done");
~~~

Output:

~~~text
audit=done
send=done
~~~

`andThen` passes **the same input** through both consumers. The second consumer is called only when the first consumer completes normally; if the first consumer throws an exception, the next step is not executed. The API requires `after` to be non-null.

### 5.2. Consumer in collections and streams

~~~java
List.of("A", "B").forEach(System.out::println);

Stream.of("A", "B")
        .forEachOrdered(System.out::println);
~~~

`Iterable.forEach` and `Stream.forEach` accept a Consumer. `forEachOrdered` preserves the stream's encounter order when that matters; `parallelStream().forEach` may not execute side effects in the expected order.

A Consumer **can** mutate state, so avoid using it to concurrently add to an unsynchronized shared `ArrayList` in a parallel stream. If you want to collect results, prefer `collect` or `toList` instead of overusing side effects.

## 6. Predicate<T>: a condition returning boolean

SAM:

~~~java
boolean test(T value);
~~~

Example:

~~~java
Predicate<Integer> positive = n -> n > 0;
Predicate<Integer> even = n -> n % 2 == 0;

boolean a = positive.test(4); // true
boolean b = even.test(5);     // false
~~~

Predicate has a **primitive boolean return** and default methods that help combine logic without writing a long lambda for every condition.

### 6.1. and and or short-circuit

~~~java
Predicate<String> present = s -> s != null;
Predicate<String> longEnough = s -> s.length() >= 3;

Predicate<String> valid = present.and(longEnough);
boolean result = valid.test(null); // false; does not call longEnough.
~~~

`and` calls the second predicate only when the first predicate is true. With `or`, the second step runs only when the first step is false:

~~~java
Predicate<Integer> negative = n -> n < 0;
Predicate<Integer> zero = n -> n == 0;

Predicate<Integer> nonPositive = negative.or(zero);
boolean yes = nonPositive.test(0); // true
~~~

Order matters if the later condition might throw an exception or have side effects. When checking for null, place `s != null` before `s.length()`.

### 6.2. negate, isEqual, and not

~~~java
Predicate<String> blank = String::isBlank;
Predicate<String> notBlank = blank.negate();

boolean a = notBlank.test("Java"); // true

Predicate<String> isJava = Predicate.isEqual("Java");
boolean b = isJava.test("Java");    // true
~~~

`isEqual` uses the appropriate value equality rules, including handling null according to its contract.

Java 11+ also has `Predicate.not`:

~~~java
List<String> nonBlanks = Stream.of("A", "", "B")
        .filter(Predicate.not(String::isBlank))
        .toList(); // [A, B]
~~~

If the source contains null, the method reference `String::isBlank` can still throw NullPointerException; `Predicate.not` is not a null validator.

### 6.3. Predicate fits filter and validation

~~~java
List<Integer> adults = List.of(16, 22, 30)
        .stream()
        .filter(age -> age >= 18)
        .toList(); // [22, 30]
~~~

A Predicate should generally represent a condition without creating side effects. Avoid relying on how many times a predicate is called or its execution order when a stream implementation may optimize the pipeline.

## 7. Function<T,R>: taking T and producing R

SAM:

~~~java
R apply(T value);
~~~

Example:

~~~java
Function<String, Integer> length = String::length;
Integer size = length.apply("Java"); // 4
~~~

In `Function<String,Integer>`, the input is String and the output is Integer. `String.length()` returns int, which is boxed into Integer to match the generic return type.

Use Function when:
- Transforming an entity into a DTO.
- Extracting an object property.
- Normalizing strings.
- Converting a string into a number, date, or enum.
- Processing `Stream.map`.

~~~java
List<Integer> lengths = List.of("Java", "Go")
        .stream()
        .map(String::length)
        .toList(); // [4, 2]
~~~

### 7.1. andThen: the latter runs second

~~~java
Function<String, Integer> length = String::length;
Function<Integer, Integer> square = n -> n * n;

Function<String, Integer> f = length.andThen(square);
int result = f.apply("java"); // 16
~~~

The order is:

~~~text
"java" → length → 4 → square → 16
~~~

### 7.2. compose: the argument runs first

~~~java
Function<String, Integer> length = String::length;
Function<Integer, Integer> square = n -> n * n;

Function<String, Integer> f = square.compose(length);
int result = f.apply("abc"); // 9
~~~

The order:

~~~text
"abc" → length → 3 → square → 9
~~~

Read `A.andThen(B)` as A then B, while `B.compose(A)` is also A then B. When types differ, the compiler helps prevent wrong composition; when functions share the same types, an order reversal bug can sometimes still compile yet produce a different result.

### 7.3. identity

~~~java
Function<String, String> same = Function.identity();
String value = same.apply("ok"); // "ok"
~~~

`identity()` returns its input unchanged; it is useful in APIs expecting a Function when no actual transformation step is needed.

### 7.4. Function does not automatically guarantee purity

A Function can read/modify state or throw an unchecked exception. The interface only defines the `T→R` shape; it does not promise immutable results, caching, or automatic error handling. In streams, prefer clear lambdas that do not depend on mutable shared state.

## 8. Composing the four interfaces into a Java pipeline

A processing flow can look like:

~~~text
Supplier<List<User>>
        │ get()
        ▼
List<User> → stream()
                  │ filter(Predicate<User>)
                  ▼
                 User
                  │ map(Function<User,String>)
                  ▼
                String
                  │ accept(Consumer<String>)
                  ▼
             Final action
~~~

Example: Supplier creates a list of Users; Predicate keeps adults; Function normalizes names; Consumer prints each name.

In Java 17, you can define:

~~~java
record User(String name, int age) {}
~~~

The compiler checks each step of the pipeline. `filter` must receive a Predicate usable with User; `map` must accept User and produce String; `forEachOrdered` passes String to Consumer<String>.

This is the benefit of generics: **constraining input/output types across composed behaviors** without manual casts.

## 9. Complete Java 17+ program and output verification

Save the following content as **FunctionalInterfacesDemo.java**:

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.function.Supplier;

public class FunctionalInterfacesDemo {
    record User(String name, int age) {}

    public static void main(String[] args) {
        Supplier<List<User>> source = () -> List.of(
                new User(" Lan ", 22),
                new User("Minh", 16),
                new User("An", 30)
        );

        Predicate<User> adult = user -> user.age() >= 18;
        Predicate<User> named = user -> !user.name().isBlank();

        Function<User, String> cleanName =
                user -> user.name().trim();
        Function<String, String> upper = String::toUpperCase;

        Consumer<String> print =
                name -> System.out.println("user=" + name);

        source.get().stream()
                .filter(adult.and(named))
                .map(cleanName.andThen(upper))
                .forEachOrdered(print);

        System.out.println(
                "minor=" +
                adult.negate().test(new User("Minh", 16))
        );

        Function<String, Integer> length = String::length;
        Function<Integer, Integer> square = n -> n * n;

        System.out.println(
                "compose=" +
                square.compose(length).apply("abc")
        );
        System.out.println(
                "andThen=" +
                length.andThen(square).apply("java")
        );
        System.out.println(
                "identity=" +
                Function.<String>identity().apply("ok")
        );
        System.out.println(
                "isEqual=" +
                Predicate.isEqual("An").test("An")
        );

        Consumer<String> audit =
                s -> System.out.println("audit=" + s);
        Consumer<String> send =
                s -> System.out.println("send=" + s);

        audit.andThen(send).accept("done");

        AtomicInteger calls = new AtomicInteger();
        Supplier<Integer> next = calls::incrementAndGet;

        System.out.println("before=" + calls.get());
        System.out.println("next=" + next.get());
        System.out.println("next=" + next.get());
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -Xlint:all FunctionalInterfacesDemo.java
java FunctionalInterfacesDemo
~~~

**Exact** stdout:

~~~text
user=LAN
user=AN
minor=true
compose=9
andThen=16
identity=ok
isEqual=true
audit=done
send=done
before=0
next=1
next=2
~~~

### Output explanation

1. `source.get()` provides three Users. `adult.and(named)` keeps Lan and An because they are 18 or older; 16-year-old Minh is filtered out.
2. `cleanName.andThen(upper)` trims whitespace and uppercases; `forEachOrdered` prints LAN before AN in encounter order.
3. `adult.negate()` indicates Minh is a minor: true.
4. `square.compose(length)` computes 3 then squares it to 9; `length.andThen(square)` computes 4 then squares it to 16.
5. `Function.identity()` keeps "ok" unchanged; `Predicate.isEqual("An")` matches the string "An".
6. `audit.andThen(send)` executes both actions in order.
7. `before=0` proves creating the Supplier has not incremented the counter yet; the next two `get()` calls return 1 and 2 respectively.

The program uses unaccented names so the uppercase example is simple and produces stable results in typical execution environments. In internationalized systems, `Locale` should be explicitly considered for case conversions.

## 10. Method references and type inference

These forms:

~~~java
Function<String, Integer> a = s -> s.length();
Function<String, Integer> b = String::length;

Consumer<String> printer = System.out::println;
Predicate<String> blank = String::isBlank;
Supplier<List<String>> listFactory = ArrayList::new;
~~~

are all valid if the required classes are imported. The target functional interface determines the compatible type of the method reference.

Common categories of method references:

| Form | Example | Meaning |
| --- | --- | --- |
| `Class::staticMethod` | `Integer::parseInt` | Calls a static method. |
| `object::instanceMethod` | `System.out::println` | Calls on a specific object. |
| `Class::instanceMethod` | `String::length` | First parameter is the receiver. |
| `Class::new` | `ArrayList::new` | Creates an object via constructor. |

Lambdas are often easier to read when logic needs multiple steps, intermediate variables, or error checks. Method references are often more concise when simply forwarding to a clearly named method.

### Passing a Function to a generic method

~~~java
static <T, R> R transform(
        T value, Function<? super T, ? extends R> function) {
    return function.apply(value);
}
~~~

Usage:

~~~java
Integer result = transform("Java", String::length); // 4
~~~

The compiler infers types T/R from value, the target, and the method reference. `? super T` lets it accept a function consuming a supertype of T; `? extends R` lets it accept a function returning a subtype of R.

## 11. Wildcards, variance, and the PECS rule

Standard functional interfaces also need **the right data direction**. Java generic invariance means `Consumer<Number>` is not automatically a `Consumer<Integer>`, but wildcards in APIs can express safe usage relationships:

~~~java
Consumer<Number> printNumber = System.out::println;
Consumer<? super Integer> acceptInteger = printNumber;
acceptInteger.accept(42);

Supplier<Integer> integerSource = () -> 7;
Supplier<? extends Number> numberSource = integerSource;
Number value = numberSource.get();
~~~

- `Consumer` takes **input**: `? super T` allows a callback to accept a supertype of `T`.
- `Supplier` produces **output**: `? extends R` allows a callback to produce a subtype of `R`.
- `Function` both takes `T` and returns `R`, so transforming APIs can accept `Function<? super T, ? extends R>`.

This is PECS (*Producer Extends, Consumer Super*), a guide to data direction rather than making generic types covariant. The next lesson analyzes the **actual signatures** of `Stream.map`, `Comparator`, `Predicate`, and using callbacks with super/subtypes; here we only need to recognize the consumer/producer direction of the four interfaces.

## 12. Primitive specializations

Generics use reference types, so `Function<String,Integer>` and `Predicate<Integer>` can incur boxing/unboxing. Java has specialized functional interfaces:

| Goal | Interface | Method |
| --- | --- | --- |
| Supply int | `IntSupplier` | `getAsInt()` |
| Consume int | `IntConsumer` | `accept(int)` |
| Test int | `IntPredicate` | `test(int)` |
| int → int | `IntUnaryOperator` | `applyAsInt(int)` |
| int → long | `IntToLongFunction` | `applyAsLong(int)` |
| T → int | `ToIntFunction<T>` | `applyAsInt(T)` |
| int → R | `IntFunction<R>` | `apply(int)` |

Example:

~~~java
IntSupplier answer = () -> 21;
IntUnaryOperator doubleIt = n -> n * 2;
IntPredicate even = n -> n % 2 == 0;

int value = doubleIt.applyAsInt(answer.getAsInt()); // 42
boolean yes = even.test(value); // true
~~~

These classes are in `java.util.function` and fit well when working with `IntStream`, `LongStream`, and `DoubleStream`. That does not mean boxing is always a severe performance issue: measure before optimizing real processing paths.

Syntax like `Supplier<int>` or `Function<int,int>` is invalid: type arguments of standard generics must be reference types.

## 13. Common mistakes

### 13.1. Using Supplier when a parameter is needed

~~~java
// Supplier<String> wrong = name -> "Hello " + name;
Function<String, String> correct = name -> "Hello " + name;
~~~

Supplier has no parameters; Function has one input.

### 13.2. Using Consumer and expecting a result

~~~java
Consumer<String> print = System.out::println;
// String result = print.accept("Java"); // Does not compile.
~~~

`accept` returns void. Use Function if a new value is needed.

### 13.3. Confusing Predicate with Function<T,Boolean>

~~~java
Predicate<String> nonBlank = s -> !s.isBlank();
Function<String, Boolean> sameCondition = s -> !s.isBlank();
~~~

They express a similar condition, but their APIs differ: Predicate has `and/or/negate` and returns primitive boolean; Function has `compose/andThen` and returns boxed Boolean.

### 13.4. Reversing compose and andThen

Write out the data flow:

~~~text
"A" -> normalize -> parse -> calculate
~~~

then chain from the previous step's output into the next step's input. With Functions of the same types, the wrong order sometimes still compiles but produces the wrong result.

### 13.5. Predicate accessing a null value

~~~java
Predicate<String> longer = s -> s.length() >= 3;
// longer.test(null); // NullPointerException.
~~~

A safe approach:

~~~java
Predicate<String> present = s -> s != null;
Predicate<String> safe = present.and(s -> s.length() >= 3);
~~~

The second step is not called if the first step is false.

### 13.6. Assuming Supplier automatically caches or runs async

Supplier only provides `get`. An implementation may recompute, cache, or call an external system, but none of those behaviors are provided automatically by the interface.

### 13.7. Side effects in parallel streams

~~~java
List<String> output = new ArrayList<>();
// source.parallelStream().forEach(output::add);
~~~

This is unsafe if output is an unsynchronized shared ArrayList. Use collectors or an appropriate concurrency design. Predicate/Function/Consumer do not make mutable state thread-safe on their own.

### 13.8. Checked exceptions in lambdas

The SAMs of the four standard interfaces do not declare checked exceptions. A lambda throwing an unhandled IOException usually cannot be assigned directly to the corresponding `Function<T,R>` or `Consumer<T>`. You can catch/wrap appropriately or define a custom functional interface with `throws E` if the contract needs to preserve checked exceptions.

### 13.9. Reusing a terminated stream

A Stream is not a collection that can repeatedly execute terminal operations. After `forEach`, `toList`, or another terminal operation, you should not reuse the same stream. If a fresh stream is needed each time, a `Supplier<Stream<T>>` can be appropriate:

~~~java
Supplier<Stream<String>> fresh =
        () -> Stream.of("Java", "Go");

long first = fresh.get().count();   // 2
long second = fresh.get().count();  // 2
~~~

Here the supplier creates **a new stream on each get**, avoiding reuse of a consumed stream.

## 14. Small API design using all four interfaces

A generic method can accept four separate behaviors:

~~~java
static <T, R> void process(
        Supplier<? extends T> loader,
        Predicate<? super T> accepted,
        Function<? super T, ? extends R> mapper,
        Consumer<? super R> sink) {

    T value = loader.get();

    if (accepted.test(value)) {
        sink.accept(mapper.apply(value));
    }
}
~~~

Example:

~~~java
process(
        () -> " Java ",
        text -> !text.isBlank(),
        String::trim,
        System.out::println
);
~~~

The output is `Java`. Each step has a clear responsibility: supplying, checking, transforming, and final handling. Each lambda can be replaced with a test implementation to verify true/false branches or call counts without changing the body of `process`.

### Testing the rejected branch

~~~java
AtomicInteger sent = new AtomicInteger();

process(
        () -> "A",
        text -> false,
        String::trim,
        text -> sent.incrementAndGet()
);

System.out.println(sent.get()); // 0
~~~

Predicate returns false, so mapper/sink do not run. This method is synchronous and calls Supplier only once; it has no built-in retry, async execution, or transaction semantics.

## 15. When should you not use these four interfaces?

They are sufficient for many small APIs, but some cases need other types:

- Two inputs, one result: `BiFunction<T,U,R>`.
- Two inputs, no result: `BiConsumer<T,U>`.
- Two inputs, returning boolean: `BiPredicate<T,U>`.
- T → T: `UnaryOperator<T>`.
- Two T's → T: `BinaryOperator<T>`.
- Callbacks throwing a specific checked exception: custom functional interface with `throws E`.
- Domain contracts with clear names like `AuthorizationRule` or `PricePolicy`, especially when a meaningful name makes the API easier to read than a generic `Function`.

There is no need to write a custom interface to replace `Supplier<T>` if it adds no extra contract. Conversely, do not force critical domain logic into anonymous lambdas that are hard to test and hard to find while debugging.

## 16. Practical Java checklist

1. **Determine the number of inputs and output type** before choosing an interface.
2. **Keep generic type arguments** instead of using raw `Function` or raw `Predicate`.
3. **Use method references judiciously** to clarify intent, though multi-step lambdas remain suitable when specific logic is needed.
4. **Verify compose/andThen direction** using a T→R diagram.
5. **Be mindful of short-circuiting** in Predicate.and/or; the second condition may not run.
6. **Define the null policy** for each step, especially when using instance method references on objects.
7. **Do not assume purity**; although side effects in Predicate/Function should be minimized, the interfaces do not enforce it.
8. **Do not assume laziness/caching/async** beyond what Supplier and the stream API actually guarantee.
9. **Consider wildcard variance** when designing generic methods taking a function of a supertype or a supplier returning a subtype.
10. **Do not use unsynchronized shared mutable state** inside a parallel stream consumer.
11. **Choose primitive specializations** in primitive processing paths when APIs and performance require them.
12. **Use the compiler with the target source release**, e.g., `javac --release 17`, and verify deterministic stdout rather than relying on order not promised by the API.

## 17. Self-check questions

**1.** If a lambda takes no parameters and returns a String, which interface should you choose?

**Answer:** `Supplier<String>` with `String get()`.

**2.** If you want to log a String without producing a result, what should you use?

**Answer:** `Consumer<String>` with `void accept(String)`.

**3.** If you want to keep Users aged 18 or older with `Stream.filter`, what should you use?

**Answer:** `Predicate<User>`, for example `u -> u.age() >= 18`.

**4.** If you want to convert a User into a String, what should you use?

**Answer:** `Function<User,String>`.

**5.** Does `Predicate.and` always evaluate both conditions?

**Answer:** No. It short-circuits when the first condition is false.

**6.** What does `Consumer.andThen` do when the first consumer throws an exception?

**Answer:** The exception is propagated; the subsequent consumer is not executed for that invocation.

**7.** Do `length.andThen(square)` and `square.compose(length)` have the same processing order?

**Answer:** Yes. Both execute length first, then square.

**8.** Does Supplier automatically memoize?

**Answer:** No. `get()` can return a new result on every call.

**9.** What does `Function.identity()` mean?

**Answer:** It returns the input value unchanged, with no transformation.

**10.** Why are `Supplier<Integer>` and `IntSupplier` not completely identical?

**Answer:** Supplier<Integer> returns a boxed Integer via get; IntSupplier returns a primitive int via getAsInt.

**11.** Why can a `Consumer<Number>` be used where a `Consumer<? super Integer>` is expected?

**Answer:** Consumer<Number> can handle Integer because Integer is a subtype of Number; `? super Integer` expresses the correct input-accepting direction.

**12.** Why should you not call `parallelStream().forEach(list::add)` if list is a shared ArrayList?

**Answer:** Consumer does not provide thread safety, and ArrayList is not safe for unsynchronized concurrent additions.

## 18. Summary

The four standard interfaces can be remembered by **data direction**:

~~~text
Supplier<T>   = get T              → get()
Consumer<T>   = work with T        → accept(T)
Predicate<T>  = ask if T is true   → test(T)
Function<T,R> = convert T into R   → apply(T)
~~~

They provide type-checked behavioral contracts, forming the foundation for lambdas, method references, collections, streams, Optional, and many modern APIs.

What matters is understanding **SAM and type inference**, **the difference between an action and a result**, **short-circuiting**, **compose/andThen order**, **wildcard direction**, and practical limits: Supplier does not auto-cache; Consumer has side effects that must be controlled; Predicate/Function are not guaranteed to be pure; none of the interfaces automatically provide thread safety or checked exception handling.

Choosing the right interface makes Java code easier to read, easier to test, flexible when composing functionality, and more type-safe.