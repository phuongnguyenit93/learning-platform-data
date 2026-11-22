# Choosing a functional interface by parameter count, return type, and operation intent in Java

## 1. Goal: choosing the right contract for behavior

In Java, lambdas and method references must have a functional interface as their **target type**. Choosing the interface carries design meaning: when seeing a `Predicate<T>` parameter, readers immediately know the caller must supply a **condition**; `Function<T,R>` expresses a **transformation**; `Consumer<T>` expresses **accepting a value and performing an action**.

Most standard types live in the `java.util.function` package (since Java 8). Instead of memorizing names in isolation, decide based on three questions in order:

1. **How many arguments?** Zero, one, or two?
2. **What is the result?** Returns `boolean`, returns a value `R`, returns the same type `T`, or returns nothing (`void`)?
3. **What is the business intent of the operation?** Checking a condition, transforming data, updating/recording, supplying a value, or combining two values?

Choose the type that conveys **the clearest intent** when multiple types technically work. For example, a lambda taking `String` and returning `boolean` could be written as `Function<String,Boolean>`, but `Predicate<String>` expresses a condition better and supports `and`, `or`, and `negate`.

## 2. Quick decision table for reference types

| Argument count | Return type | Intent | Functional interface | Abstract method |
| --- | --- | --- | --- | --- |
| 0 | `T` | Supply or create a value | `Supplier<T>` | `T get()` |
| 1 `T` | `boolean` | Check a condition | `Predicate<T>` | `boolean test(T)` |
| 1 `T` | `R` | Map/transform | `Function<T,R>` | `R apply(T)` |
| 1 `T` | `T` | Transform preserving type | `UnaryOperator<T>` | `T apply(T)` |
| 1 `T` | `void` | Accept and process with effect | `Consumer<T>` | `void accept(T)` |
| 2 `T,U` | `boolean` | Check relationship/condition | `BiPredicate<T,U>` | `boolean test(T,U)` |
| 2 `T,U` | `R` | Combine or map two values | `BiFunction<T,U,R>` | `R apply(T,U)` |
| 2 same type `T` | `T` | Combine two same-type values | `BinaryOperator<T>` | `T apply(T,T)` |
| 2 `T,U` | `void` | Process/record both values | `BiConsumer<T,U>` | `void accept(T,U)` |

`UnaryOperator<T>` **extends** `Function<T,T>`; `BinaryOperator<T>` **extends** `BiFunction<T,T,T>`. These are specialized types expressing that the output value has the same type as the input, rather than a different lambda execution mechanism.

**Quick selection flow:**

~~~text
Behavior to pass
├── 0 arguments
│   └── Returns value T                  -> Supplier<T>
├── 1 argument T
│   ├── Returns boolean                  -> Predicate<T>
│   ├── Returns no result                -> Consumer<T>
│   ├── Returns same type T              -> UnaryOperator<T>
│   └── Returns other/unconstrained R    -> Function<T,R>
└── 2 arguments
    ├── Returns boolean                  -> BiPredicate<T,U>
    ├── Returns no result                -> BiConsumer<T,U>
    ├── Two Ts, returns T                -> BinaryOperator<T>
    └── Returns any R                    -> BiFunction<T,U,R>
~~~

For primitive types `int`, `long`, and `double`, consider the **primitive variants** in Section 5 to avoid boxing/unboxing.

## 3. Choosing by operation intent

### 3.1. `Supplier<T>`: supplying a value when called

`Supplier<T>` takes no arguments and returns a `T` via `get()`. Use it for simple factories, default values, or supplying input when an API requests it.

~~~java
Supplier<String> greeting = () -> "Xin chào";
Supplier<List<String>> emptyNames = ArrayList::new;
~~~

These are **illustrative snippets inside a method**, requiring imports `java.util.function.Supplier`, `java.util.List`, and `java.util.ArrayList`. `get()` may create a new value or return an existing one depending on how it is written; **`Supplier` does not automatically guarantee caching**, nor is it inherently a pure function. The API decides when and how many times `get()` is called.

Distinguish `Supplier<T>` from `Function<Void,T>`: using `Void` as a dummy parameter is both hard to read and requires passing a parameter value; `Supplier` accurately expresses zero arguments.

### 3.2. `Predicate<T>`: a true/false question

Use `Predicate<T>` when you need an input condition `T` and a `boolean` result, such as filtering orders, validating names, or checking policies.

~~~java
Predicate<String> notBlank = value -> value != null && !value.isBlank();
Predicate<String> shortEnough = value -> value != null && value.length() <= 8;
Predicate<String> accepted = notBlank.and(shortEnough);
~~~

`Predicate` has composition methods `and`, `or`, `negate`, and the static method `Predicate.not(...)`. `and` and `or` are **short-circuiting** conditional combinators (they may skip evaluating the right-hand side if the result is already determined), just like the corresponding logical operators. This style fits well when conditions produce no side effects.

Choose `BiPredicate<T,U>` when the condition needs **two** inputs, such as `(password, minLength) -> password.length() >= minLength`. Type parameters `T` and `U` do not need to be the same.

### 3.3. `Function<T,R>`: transforming input into output

`Function<T,R>` is for converting one value into another value: from an order to a customer name, from a DTO to a domain model, or from a string to a parsed object.

~~~java
Function<String, Integer> length = String::length;
Function<Integer, String> label = count -> "Độ dài: " + count;
Function<String, String> describe = length.andThen(label);
~~~

In this illustrative snippet (importing `java.util.function.Function`), `describe.apply("Java")` returns `"Độ dài: 4"`. `andThen` runs the current function first and then the next function; `compose` runs the passed-in function first. Two functions can be composed when output/input types are compatible.

Use `UnaryOperator<T>` if both input and output **are `T`** (e.g., normalizing a `String`, updating a value object to a new copy). `Function<T,T>` is still valid, but `UnaryOperator<T>` states the intent more tightly. Do not choose `UnaryOperator` if the result is actually a different type.

### 3.4. `Consumer<T>`: performing an action, returning no data

`Consumer<T>` takes `T` and returns `void`. Typical cases: logging, displaying, emitting events, or invoking an action whose result is not passed back.

~~~java
Consumer<String> print = System.out::println;
print.accept("Đã xử lý");
~~~

`Consumer` has `andThen` to run two actions in order. Note that side effects like console printing or mutating external state are unsuitable to stuff into every `Stream.map`/`filter` step; when you need to build a list of results, prefer `map` followed by `toList` or a collector.

With two arguments, use `BiConsumer<T,U>`, such as `(key, value) -> log(key, value)`. `Map.forEach` accepts `BiConsumer<? super K, ? super V>`, because each entry provides both key and value.

### 3.5. `BiFunction<T,U,R>` and `BinaryOperator<T>`: combining two values

A computation needing two parameters usually fits `BiFunction<T,U,R>`:

~~~java
BiFunction<String, Integer, String> repeat =
        (text, count) -> text.repeat(count);
String result = repeat.apply("ha", 3);  // "hahaha"
~~~

If **both inputs and the output share the same type**, use `BinaryOperator<T>` to express the combining operation:

~~~java
BinaryOperator<String> chooseLonger =
        (left, right) -> left.length() >= right.length() ? left : right;
~~~

Both snippets assume `java.util.function.BiFunction` and `BinaryOperator` are imported and placed inside a method. `BinaryOperator` has utilities `minBy(Comparator)` and `maxBy(Comparator)`. When using this type in `Stream.reduce`, adhere to the reduction's specific requirements such as *associativity* when required by the API; not every two-argument calculation is suitable as a parallel reduction.

## 4. Examples with the same shape but different intent

A lambda taking `String` can serve many purposes:

| Statement to express | Choose | Why |
| --- | --- | --- |
| "Is this string valid?" | `Predicate<String>` | Result is a `boolean` condition |
| "How long is this string?" | `ToIntFunction<String>` | Returns primitive `int`; `Function<String,Integer>` works but incurs boxing |
| "Normalize the string" | `UnaryOperator<String>` | Input and output are both `String` |
| "Convert string to `User`" | `Function<String,User>` | Converts to a different type |
| "Print string to console" | `Consumer<String>` | `void` action |
| "Generate a default string" | `Supplier<String>` | Takes no arguments |
| "Check if string is at least length n" | `BiPredicate<String,Integer>` | Two arguments, returns `boolean` |
| "Join two strings into one" | `BinaryOperator<String>` | Two `String`s, returns `String` |

**Choosing by API contract:** for `Consumer<String>`, the lambda `s -> s.length()` is still valid syntax because a method call is a *statement expression* and Java can discard the returned `int`. However, calling `length()` and discarding the result rarely does anything useful; if you need the length, use `Function<String,Integer>` or `ToIntFunction<String>`, while `Consumer` should represent an intentional action. Do not turn `Consumer` into a "function returning null" via `Function<T,Void>` when the contract is purely an action.

For `Boolean`, distinguish a **primitive boolean check** suited to `Predicate` from an API that genuinely needs a **nullable `Boolean` object**. `Predicate.test` always returns primitive `boolean`, so it cannot represent a three-state `true`/`false`/`null` result without explicit conversion rules.

## 5. When to use primitive-specialized interfaces?

General types `Function<T,R>`, `Supplier<T>`, and `UnaryOperator<T>` take **reference** type parameters, not `int`, `long`, or `double` directly. Writing `Function<int,long>` is a compile error; you must use wrappers `Integer`/`Long`, or prefer primitive interfaces.

| Shape | Specialized type | SAM method |
| --- | --- | --- |
| `int -> boolean` | `IntPredicate` | `boolean test(int)` |
| `long -> boolean` | `LongPredicate` | `boolean test(long)` |
| `double -> boolean` | `DoublePredicate` | `boolean test(double)` |
| `int -> int` | `IntUnaryOperator` | `int applyAsInt(int)` |
| `long -> long` | `LongUnaryOperator` | `long applyAsLong(long)` |
| `double -> double` | `DoubleUnaryOperator` | `double applyAsDouble(double)` |
| `(int,int) -> int` | `IntBinaryOperator` | `int applyAsInt(int,int)` |
| `(long,long) -> long` | `LongBinaryOperator` | `long applyAsLong(long,long)` |
| `() -> int` | `IntSupplier` | `int getAsInt()` |
| `() -> long` | `LongSupplier` | `long getAsLong()` |
| `() -> double` | `DoubleSupplier` | `double getAsDouble()` |
| `() -> boolean` | `BooleanSupplier` | `boolean getAsBoolean()` |
| `int -> void` | `IntConsumer` | `void accept(int)` |
| `long -> void` | `LongConsumer` | `void accept(long)` |
| `double -> void` | `DoubleConsumer` | `void accept(double)` |
| `T -> int` | `ToIntFunction<T>` | `int applyAsInt(T)` |
| `T -> long` | `ToLongFunction<T>` | `long applyAsLong(T)` |
| `T -> double` | `ToDoubleFunction<T>` | `double applyAsDouble(T)` |
| `int -> R` | `IntFunction<R>` | `R apply(int)` |
| `double -> R` | `DoubleFunction<R>` | `R apply(double)` |
| `int -> long` | `IntToLongFunction` | `long applyAsLong(int)` |
| `long -> int` | `LongToIntFunction` | `int applyAsInt(long)` |
| `(T,U) -> int` | `ToIntBiFunction<T,U>` | `int applyAsInt(T,U)` |
| `(T,int) -> void` | `ObjIntConsumer<T>` | `void accept(T,int)` |

There are also symmetric variants such as `LongFunction<R>`, `DoubleToLongFunction`, `IntToDoubleFunction`, `LongToDoubleFunction`, `DoubleToIntFunction`, `ToLongBiFunction<T,U>`, `ToDoubleBiFunction<T,U>`, `ObjLongConsumer<T>`, and `ObjDoubleConsumer<T>`. Read the name by pattern: **which source type, which target type, how many arguments**.

Illustrative example:

~~~java
IntPredicate positive = n -> n > 0;
IntUnaryOperator squared = n -> n * n;
ToLongFunction<String> countLetters = value -> value.length();
LongBinaryOperator sum = Long::sum;
~~~

This snippet requires `import java.util.function.*;` placed inside a method. `countLetters` returns primitive `long` via widening conversion from `int`; if you only need an `int` length, `ToIntFunction<String>` is more appropriate.

**Why is choosing primitives useful?** Specialized types avoid boxing/unboxing when converting primitives in pipelines, especially in `IntStream`/`LongStream`/`DoubleStream`. However, do not claim primitives are always faster in every task; measure actual cost if performance is a critical requirement.

Example:

~~~java
long total = orders.stream()
        .mapToLong(order -> order.unitPrice() * order.quantity())
        .sum();
~~~

`mapToLong` takes `ToLongFunction<? super Order>`, returns a `LongStream`, and then `sum()` adds the `long` elements. This is an example of passing a function to the Stream API without creating a `Long` wrapper for each value.

## 6. Complete Java 17 example: choosing interfaces in a problem

Suppose a list of orders has customer name, quantity, unit price, and payment status. We want to filter paid orders, extract customer names, compute total amount, add a service fee, check a name, and print results. Each operation needs a contract with its own clear meaning.

Create the file **InterfaceChoiceDemo.java**:

~~~java
import java.util.List;
import java.util.function.*;

public class InterfaceChoiceDemo {
    record Order(String customer, int quantity, long unitPrice, boolean paid) {}

    static long amount(Order order) {
        return order.quantity() * order.unitPrice();
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("An", 2, 15_000, true),
                new Order("Binh", 1, 25_000, false),
                new Order("Chi", 3, 10_000, true)
        );

        Predicate<Order> isPaid = Order::paid;
        Function<Order, String> getCustomer = Order::customer;
        ToLongFunction<Order> getAmount = InterfaceChoiceDemo::amount;
        Supplier<String> title = () -> "Đơn đã thanh toán";
        Consumer<String> output = System.out::println;
        BiPredicate<String, Integer> minLength =
                (name, min) -> name != null && name.length() >= min;
        BiConsumer<String, Long> showMoney =
                (label, value) -> System.out.println(label + ": " + value);
        LongUnaryOperator addServiceFee = value -> value + 5_000;
        UnaryOperator<String> trim = String::trim;
        BinaryOperator<String> join = (left, right) -> left + " / " + right;

        List<Order> paidOrders = orders.stream().filter(isPaid).toList();
        List<String> customers = paidOrders.stream().map(getCustomer).toList();
        long subtotal = paidOrders.stream().mapToLong(getAmount).sum();

        output.accept(title.get() + ": " + customers);
        showMoney.accept("Tổng", subtotal);
        showMoney.accept("Cộng phí", addServiceFee.applyAsLong(subtotal));
        output.accept("Tên hợp lệ: " + minLength.test("An", 2));
        output.accept(join.apply(trim.apply("  An "), "Chi"));
    }
}
~~~

Compile and run from the directory containing the file using JDK 17+:

~~~bash
javac --release 17 InterfaceChoiceDemo.java
java InterfaceChoiceDemo
~~~

**Verified output from running:**

~~~text
Đơn đã thanh toán: [An, Chi]
Tổng: 60000
Cộng phí: 65000
Tên hợp lệ: true
An / Chi
~~~

Explanation matching each interface's exact role:

1. `Predicate<Order>` defines the **order-retention condition** `paid == true`. `Stream.filter` uses that predicate directly.
2. `Function<Order,String>` turns `Order` into `String` (customer name) via `Stream.map`.
3. `ToLongFunction<Order>` extracts the primitive `long` amount via `Stream.mapToLong`, enabling summation via `LongStream.sum()`.
4. `Supplier<String>` provides the title when `get()` is called; the title needs no input parameter.
5. `Consumer<String>` calls `println` to output information, returning no data to the caller.
6. `BiPredicate<String,Integer>` compares name length against a threshold, taking two input types and returning `boolean`.
7. `BiConsumer<String,Long>` takes a label and an amount to display.
8. `LongUnaryOperator` takes `long` and returns `long`, representing adding a fee with the same output type.
9. `UnaryOperator<String>` preserves type `String` during `trim`; `BinaryOperator<String>` combines two strings into one.

The data has two paid orders: `An` 2 × 15,000 = 30,000; `Chi` 3 × 10,000 = 30,000; subtotal is 60,000, plus fee 5,000 gives 65,000. There is no random output order: the `List.of` source preserves encounter order, and `filter`, `map`, and `toList` in the example preserve that order accordingly.

`BiConsumer<String, Long>` uses reference type `Long`, so the `long subtotal` argument is boxed when passed to `accept`. If a two-parameter operation consisting of a label object and a `long` is a performance hot spot, consider `ObjLongConsumer<String>`. This illustrates choosing by **function shape** first, then refining by **actual data types**.

## 7. Choosing an interface according to the API receiving the lambda

When an API already exists, **the API's parameter type determines the target type**; you cannot unilaterally switch to an interface that "looks nicer" if the API does not accept it.

| API / operation | Contract accepted by the API | Intent |
| --- | --- | --- |
| `Stream<T>.filter(...)` | `Predicate<? super T>` | Keep or drop elements |
| `Stream<T>.map(...)` | `Function<? super T,? extends R>` | Transform each element |
| `Stream<T>.mapToInt(...)` | `ToIntFunction<? super T>` | Convert to primitive `int` |
| `Stream<T>.mapToLong(...)` | `ToLongFunction<? super T>` | Convert to primitive `long` |
| `Stream<T>.forEach(...)` | `Consumer<? super T>` | Perform an action |
| `Optional<T>.orElseGet(...)` | `Supplier<? extends T>` | Create a fallback value when absent |
| `Map<K,V>.forEach(...)` | `BiConsumer<? super K,? super V>` | Receive key and value |
| `Map<K,V>.computeIfAbsent(...)` | `Function<? super K,? extends V>` | Compute value from key when absent |
| `Stream<T>.reduce(identity, accumulator)` | `BinaryOperator<T>` | Combine values of the same type |
| `IntStream.map(...)` | `IntUnaryOperator` | Convert `int` to `int` |
| `IntStream.filter(...)` | `IntPredicate` | Filter by `int` |
| `IntStream.mapToObj(...)` | `IntFunction<? extends U>` | Convert `int` to object |
| `LongStream.sum()` | Accepts no callback | API aggregates directly; no operator needed |

`? super T` and `? extends R` are variance wildcards: they allow the API to accept functions handling a supertype of the element or returning a subtype of the expected result. Check the actual method signature in your IDE/Javadoc before choosing an interface.

**Distinguish similar APIs:** `Optional.orElse(value)` takes a precomputed value, whereas `Optional.orElseGet(supplier)` takes supplying behavior so it can be called only when a fallback is actually needed. `Map.computeIfAbsent` takes `Function<K,V>` because the function must know **the key**; you cannot directly substitute `Supplier<V>` when the API signature requires Function.

## 8. Combining behaviors: prefer the right type that supports composition

Many interfaces provide composition methods, helping model processing chains with the right semantics:

~~~java
Predicate<String> nonBlank = text -> text != null && !text.isBlank();
Predicate<String> shortText = text -> text != null && text.length() <= 10;
Predicate<String> valid = nonBlank.and(shortText);

Function<String, String> trim = String::trim;
Function<String, Integer> length = String::length;
Function<String, Integer> normalizedLength = trim.andThen(length);

Consumer<String> first = text -> System.out.println("A:" + text);
Consumer<String> second = text -> System.out.println("B:" + text);
Consumer<String> both = first.andThen(second);
~~~

These are **illustrative snippets placed inside a method**, requiring imports `java.util.function.Predicate`, `Function`, and `Consumer`. `valid` checks both conditions; `normalizedLength.apply(" Java ")` returns 4; `both.accept("X")` prints `A:X` followed by `B:X`.

Compositions with side effects still depend on ordering, state, and exceptions. For example, if the first Consumer throws an exception, the second Consumer does not execute. With a `Predicate` containing side effects, `and`/`or` may skip the second part due to short-circuiting. Prefer pure checking/transformation functions when you need easily testable logic.

## 9. When not to use types in java.util.function directly?

Some behaviors already have **domain-specialized** functional interfaces outside the `java.util.function` package. Use them when the API or domain semantics call for them.

- `Runnable` in `java.lang` expresses `() -> void`, usually a task to execute, such as passing to a `Thread` or `Executor`. It returns no result.
- `Callable<V>` in `java.util.concurrent` expresses `() -> V` and can declare `throws Exception`. It fits tasks with a result and potential checked exceptions; it differs from `Supplier<V>` in its checked-exception contract.
- `Comparator<T>` in `java.util` expresses `(T,T) -> int` for ordering comparisons. Do not replace it with `BiFunction<T,T,Integer>` when an API expects Comparator; comparison semantics include specific ordering contracts.
- `java.util.EventListener` is not inherently a functional interface; each specific subtype must be checked for its abstract contract.
- When **three arguments** are needed, the standard `java.util.function` set has no general `TriFunction<T,U,V,R>`. You can create a domain-appropriate functional interface or group related arguments into a record/value object and pass it to `Function`.

Example of a business-named interface (declared **at class/interface level, not inside a method**):

~~~java
@FunctionalInterface
interface PricePolicy {
    long calculate(long basePrice);
}
~~~

`PricePolicy` has a signature similar to `LongUnaryOperator`, but a business domain name can make the API clearer. Choose a custom interface when it has a stable public meaning or needs specialized documentation/contracts; for ordinary utility callbacks, standard types avoid unnecessary abstractions.

Regarding checked exceptions, standard `Function`, `Predicate`, and `Supplier` do not add `throws IOException`/SQL exceptions to their SAMs. A lambda throwing an incompatible checked exception will not compile unless handled inside the lambda or using another interface with an appropriate `throws` contract. Do not silently wrap every exception in RuntimeException when the API expects callers to handle it intentionally.

## 10. Common interface-selection mistakes

1. **Choosing `Function<T,Boolean>` over `Predicate<T>` for a binary condition** without reason: loses dedicated condition combinators and may incur boxing. If a nullable `Boolean` result is genuinely needed, that is a different requirement that should be stated explicitly.
2. **Using `Consumer<T>` to accumulate results that could be returned:** mutating an external list from `forEach` is hard to follow and unsafe in parallel execution. For new data, use `map`, `reduce`, `collect`, or `toList` depending on the task.
3. **Using `Function<Void,T>` instead of `Supplier<T>`:** creates a meaningless parameter. Use `Supplier` when there is no input.
4. **Defaulting to `BiFunction` for a `(T,T)->T` combine operation:** `BinaryOperator<T>` clearly states all three positions share the same type, fitting many reduce APIs.
5. **Confusing return type `void` with type `Void`:** `Void` is a reference type, not the `void` keyword; `Consumer` is for returning no result.
6. **Using wrappers in primitive pipelines unnecessarily:** `Function<Integer,Integer>` incurs boxing, whereas `IntUnaryOperator` takes and returns `int`. Choose specialized types when appropriate.
7. **Assuming interface names determine purity:** `Function` can also cause side effects, `Supplier` can return values that change over time, and `Predicate` can read shared state. Purity comes from the implementation body and involved data.
8. **Trying to force a multi-argument callback into a lambda without a target type:** Java needs an explicit functional interface to determine the signature. If an API needs a custom type, declare an interface with exactly one SAM or use another matching type.
9. **Confusing `BiPredicate<T,U>` with `BinaryOperator<T>`:** both take two arguments, but the former returns `boolean` and the latter returns `T`. Always start by asking about **the return type**.

## 11. Interface-selection exercises

Choose the appropriate type, then compare with the answer:

| Scenario | Suggested answer | Explanation |
| --- | --- | --- |
| Generate a new order ID, no parameters | `Supplier<String>` | No arguments, returns String |
| Check whether a primitive age is greater than 18 | `IntPredicate` | Takes int, returns boolean |
| Convert `User` to `UserDto` | `Function<User,UserDto>` | Two different reference types |
| Increment a long value by 1 | `LongUnaryOperator` | long → long |
| Compare `User` and permission `Role` | `BiPredicate<User,Role>` | Two arguments, checks a condition |
| Update UI by name and count | `BiConsumer<String,Integer>` | Takes two values, returns no result |
| Get the character count of a `String` | `ToIntFunction<String>` | Object → int |
| Combine two `BigDecimal`s into a sum | `BinaryOperator<BigDecimal>` | Both inputs and result are BigDecimal |
| Format a `double` into a display string | `DoubleFunction<String>` | double → String |
| Create a task returning data and declaring checked exceptions | `Callable<V>` | Task semantics, supports checked exceptions |

**Try explaining further:** for the problem "compute the fee for an order", should you use `Function<Order,Long>` or `ToLongFunction<Order>`? If the fee is a primitive long used for calculations/Streams, `ToLongFunction<Order>` usually exposes the target type better and avoids boxing. If the API expects `Function<Order,Long>`, you must use the exact API signature; do not arbitrarily change the parameter type.

## 12. Pre-lambda checklist

Before choosing an interface, check yourself:

1. Which callback type does the specific API accept? If there is no API yet, what contract am I defining?
2. Are there 0, 1, or 2 parameters? Are they reference or primitive types?
3. Is the return type actually `void`, `boolean`, `T`, `R`, or a primitive?
4. Is there an interface that clearly expresses condition, transformation, supplying, consuming, or combining?
5. Does the lambda need to handle checked exceptions or carry domain-specific semantics?
6. Is there any risk of boxing, mutating shared state, computation cost, or misusing callbacks in a Stream?

**Conclusion:** To choose the right functional interface, deduce **argument count → return type → operation intent**, then match against the target API contract. `Supplier`, `Predicate`, `Function`, `Consumer`, `UnaryOperator`, `BinaryOperator`, and the `Bi...` variants cover most reference-type callbacks; `Int...`, `Long...`, `Double...`, `To...`, and `Obj...` variants handle primitives appropriately. Good choices make code self-documenting and let callers know exactly what behavior to supply.
