# BiFunction, BiPredicate, and BiConsumer in Java

In the **java.util.function** package, Java provides three common functional interfaces for when an operation must accept **two inputs**: **BiFunction**, **BiPredicate**, and **BiConsumer**. All three allow expressing behavior with lambdas or method references, but they have different output contracts. Mastering these differences helps design callbacks, work with Maps, combine validation rules, and separate computation from side effects.

This lesson applies to Java 17 or later, explaining generic signatures, the single abstract method (SAM), default methods, practical examples, type limitations, evaluation order, performance, and common mistakes.

## 1. Essence: two parameters, three kinds of behavior

| Interface | SAM method | Two inputs | Result | Example |
| --- | --- | --- | --- | --- |
| **BiFunction<T, U, R>** | R apply(T t, U u) | T and U | R | Compute line total from quantity and unit price |
| **BiPredicate<T, U>** | boolean test(T t, U u) | T and U | boolean | Check whether stock satisfies requested quantity |
| **BiConsumer<T, U>** | void accept(T t, U u) | T and U | No return value | Log an item code and amount |

In the **Bi** prefix, **Bi** indicates the function takes two parameters. The two parameters do not have to be the same type. With BiFunction, the output R can differ from both T and U; with BiPredicate, the result is always a primitive boolean; with BiConsumer, the SAM return type is void.

All three are annotated with **@FunctionalInterface** in Java and can be implemented with lambdas. They serve as **target types**: the compiler uses T, U, and R from the assignment or argument position to infer lambda parameter types.

Short comparison example:

~~~java
java.util.function.BiFunction<Integer, Integer, Integer> add =
    (a, b) -> a + b;
java.util.function.BiPredicate<Integer, Integer> greater =
    (a, b) -> a > b;
java.util.function.BiConsumer<String, Integer> print =
    (name, score) -> System.out.println(name + ": " + score);
~~~

These are **illustrative snippets placed inside a method**, not a standalone runnable program. When applied:

~~~java
System.out.println(add.apply(4, 6));       // 10
System.out.println(greater.test(4, 6));    // false
print.accept("Lan", 9);                    // Lan: 9
~~~

Important point: they differ not only in **return type**, but also in **intent**: transforming, deciding a condition, or performing an action.

## 2. BiFunction<T, U, R>: turning two inputs into one result

Conceptual signature:

~~~java
@FunctionalInterface
public interface BiFunction<T, U, R> {
    R apply(T t, U u);

    // Has default method andThen(...) to compose the result.
}
~~~

- **T:** type of the first argument.
- **U:** type of the second argument.
- **R:** return value type.
- **apply(t, u):** executes the calculation/transformation.

Example with the same input and output types:

~~~java
BiFunction<Integer, Integer, Integer> multiply =
    (quantity, unitPrice) -> quantity * unitPrice;
System.out.println(multiply.apply(3, 20));  // 60
~~~

Example with different types:

~~~java
BiFunction<String, Integer, String> repeat =
    (text, count) -> text.repeat(count);
System.out.println(repeat.apply("Ja", 3));   // JaJaJa
~~~

To run these snippets in a Java class, add import java.util.function.BiFunction and place them in main; note that String.repeat was introduced in Java 11 and does not accept negative counts.

BiFunction can reference a static method taking two parameters:

~~~java
BiFunction<Integer, Integer, Integer> safeMultiply =
    Math::multiplyExact;
~~~

Math.multiplyExact(int, int) detects int overflow with ArithmeticException, unlike ordinary int multiplication which can overflow silently.

BiFunction can also use a method reference to a two-parameter constructor:

~~~java
record Product(String name, int price) {}

BiFunction<String, Integer, Product> newProduct =
    Product::new;
~~~

The record line is a type declaration that must be placed in a valid location (such as class level or inside a method); this illustrative snippet must be placed in a corresponding Java context. BiFunction returns a Product, which need not be the type of either input.

### 2.1. Composing with andThen

BiFunction has the default method **andThen(Function<? super R, ? extends V> after)**, which runs the BiFunction first and then feeds **the single result R** into the subsequent Function:

~~~java
BiFunction<Integer, Integer, Integer> amount =
    (quantity, price) -> quantity * price;

BiFunction<Integer, Integer, String> labelled =
    amount.andThen(total -> "Total=" + total);

System.out.println(labelled.apply(2, 50)); // Total=100
~~~

Visualization:

~~~text
T, U --BiFunction.apply--> R --Function.apply--> V
~~~

Common pitfall: **andThen takes a one-parameter Function**, because the next step only receives the result R. It does not take another BiFunction to re-process the original two arguments.

Execution rules:

- Calling labelled.apply(t, u) first executes amount.apply(t, u).
- Then it executes the subsequent Function with the newly produced result.
- If the first function throws an exception, the second function **does not run**.
- Passing after = null to andThen throws NullPointerException when creating the composition.
- andThen does not automatically handle null in R; the subsequent Function must support null itself if needed.

### 2.2. Separating business logic into transformations

BiFunction fits when the result can be **returned as data**, rather than written directly into an external variable:

~~~java
BiFunction<Integer, Integer, Integer> net =
    (gross, discount) -> gross - discount;

int finalAmount = net.apply(1000, 120);
~~~

You can pass the pricing formula into another processing method, swap policies by replacing the BiFunction in unit tests, or compose it with Function.andThen. Avoid mutating a shared variable inside the lambda when the goal is a repeatable calculation.

## 3. BiPredicate<T, U>: checking a condition on two values

Conceptual signature:

~~~java
@FunctionalInterface
public interface BiPredicate<T, U> {
    boolean test(T t, U u);

    // Default methods: and(...), or(...), negate().
}
~~~

BiPredicate takes two inputs and returns a boolean. It is useful when a condition depends on **a relationship between two values**, such as checking available stock against requested quantity, a score against a minimum threshold, or a user's permission on a resource.

~~~java
BiPredicate<Integer, Integer> sufficient =
    (available, requested) -> requested > 0 && available >= requested;

System.out.println(sufficient.test(5, 3));  // true
System.out.println(sufficient.test(2, 3));  // false
System.out.println(sufficient.test(5, -1)); // false
~~~

The requested > 0 check shows that writing a good BiPredicate is not just comparing two values, but also clarifying the **validity contract** of the request.

### 3.1. Combining conditions: and, or, and negate

Default methods of BiPredicate:

- **and(other):** true when both the left condition **and** the right condition are true.
- **or(other):** true when **at least one** condition is true.
- **negate():** inverts the result of the current condition.

~~~java
BiPredicate<Integer, Integer> enough =
    (available, requested) -> available >= requested;
BiPredicate<Integer, Integer> valid =
    (available, requested) -> requested > 0;

BiPredicate<Integer, Integer> accepted = enough.and(valid);
BiPredicate<Integer, Integer> rejected = accepted.negate();

System.out.println(accepted.test(5, 3)); // true
System.out.println(rejected.test(2, 3)); // true
~~~

Both **and/or short-circuit**:

- With and, if the first predicate returns false, the second predicate is not called.
- With or, if the first predicate returns true, the second predicate is not called.
- With negate, the original predicate is called and the result is inverted; the original predicate object is not mutated.

Short-circuiting is both beneficial for performance and useful for avoiding an unsafe check when a prior guard fails. However, it is also why you should not put side effects such as incrementing counters, logging, or sending notifications inside combined predicates: the number of callback executions can vary depending on inputs and composition order.

### 3.2. Example applying a bound on two values

~~~java
BiPredicate<Integer, Integer> inRange =
    (value, upperBound) -> value >= 0 && value <= upperBound;
~~~

Calling inRange.test(7, 10) returns true. This is a relationship between value and upperBound, not a case for Predicate<Integer> looking at a single input.

When a condition genuinely needs only one piece of data, use **Predicate<T>**; do not invent an extra argument just to use BiPredicate.

## 4. BiConsumer<T, U>: performing an action with two parameters

Conceptual signature:

~~~java
@FunctionalInterface
public interface BiConsumer<T, U> {
    void accept(T t, U u);

    // Default method: andThen(BiConsumer<? super T, ? super U> after)
}
~~~

BiConsumer takes two arguments, but its accept method returns no result. Common examples include **printing, logging, updating data, writing audit records, emitting events**, or callbacks connecting to an external system.

~~~java
BiConsumer<String, Integer> printScore =
    (name, score) -> System.out.println(name + "=" + score);

printScore.accept("Mai", 10); // Mai=10
~~~

Do not use BiConsumer when you need to retrieve a computed value. If you want to turn two inputs into a result, use BiFunction. If you want to ask a true/false question, use BiPredicate.

### 4.1. BiConsumer's andThen

BiConsumer.andThen chains two actions **in order**: it runs the original consumer and then runs the subsequent consumer with **the same two arguments**.

~~~java
BiConsumer<String, Integer> first =
    (name, score) -> System.out.println("A:" + name + ":" + score);
BiConsumer<String, Integer> second =
    (name, score) -> System.out.println("B:" + name + ":" + score);

BiConsumer<String, Integer> both = first.andThen(second);
both.accept("An", 8);
~~~

Stdout of the snippet:

~~~text
A:An:8
B:An:8
~~~

If the first action throws an exception, the second action **is not called**; andThen does not automatically roll back side effects that already occurred. Passing after = null throws NullPointerException when creating the chain.

Key distinction from BiFunction.andThen: **BiConsumer.andThen takes another BiConsumer and both receive T, U**, whereas BiFunction.andThen takes a Function that processes **the result R**.

### 4.2. BiConsumer and side-effect properties

Consumer is the behavior type suited for side effects, but that does not mean every BiConsumer lambda mutates external state. A lambda that only computes and discards a result can still be void-compatible, though it usually has no practical value.

When a BiConsumer modifies shared data, the author must consider:

- Can it be called multiple times or retried?
- Can it be called from multiple threads? If so, is the target data thread-safe?
- Does it depend on ordering or atomicity of the action chain?
- If the second action fails, how is the already-executed first action handled?

BiConsumer provides no guarantees of transactions, retries, idempotency, or thread safety. Those are the responsibility of the calling API and application design.

## 5. Comparing default methods of the three interfaces

| Interface | Key default method(s) | Additional argument type | Characteristics |
| --- | --- | --- | --- |
| BiFunction<T,U,R> | andThen(after) | Function<? super R,? extends V> | Transforms result R into V |
| BiPredicate<T,U> | and(other), or(other), negate() | BiPredicate or no argument | Boolean logical composition; and/or short-circuit |
| BiConsumer<T,U> | andThen(after) | BiConsumer<? super T,? super U> | Executes two actions sequentially with the same T, U |

There is no default compose method for BiFunction or BiConsumer like Function.compose, and no result-transforming andThen for BiPredicate. When you need more complex composition APIs, create explicit intermediate functions or define an appropriate custom interface.

Mnemonic by purpose: **BiFunction returns a value; BiPredicate returns a condition; BiConsumer performs an action.**

## 6. Java APIs that use BiFunction and BiConsumer

These interfaces are useful beyond standalone lambda declaration examples. The Java Collections Framework uses them to pass behavior into Map methods.

### 6.1. Map.forEach takes BiConsumer

~~~java
java.util.Map<String, Integer> scores =
    new java.util.LinkedHashMap<>();
scores.put("An", 8);
scores.put("Binh", 9);

scores.forEach((name, score) ->
    System.out.println(name + "=" + score));
~~~

Stdout:

~~~text
An=8
Binh=9
~~~

BiConsumer receives each key and corresponding value. The example uses LinkedHashMap so traversal order follows insertion order predictably; do not assume HashMap or Map.of always iterates in the written order.

### 6.2. Map.compute and Map.computeIfPresent take BiFunction

~~~java
java.util.Map<String, Integer> inventory =
    new java.util.HashMap<>();
inventory.put("pen", 5);

inventory.computeIfPresent("pen", (key, oldCount) -> oldCount + 2);
System.out.println(inventory.get("pen")); // 7
~~~

In Map.computeIfPresent, the BiFunction receives the **key (K)** and **current value (V)** and returns the new value V. The callback is typically invoked when there is a mapping to a **non-null** value, per the Map contract. If the callback returns null, the corresponding mapping may be **removed**, rather than automatically acting as a no-op that preserves the value. With Map.compute, the callback can receive a null old value when no mapping exists or when it maps to null (depending on the Map type).

Because null cases matter, do not casually put arbitrary logic into compute/merge without checking the method's contract.

### 6.3. Map.merge: BiFunction receives two values, not the key

~~~java
java.util.Map<String, Integer> totals =
    new java.util.HashMap<>();
totals.merge("book", 2, Integer::sum);
totals.merge("book", 3, Integer::sum);

System.out.println(totals.get("book")); // 5
~~~

Map.merge has a remappingFunction parameter compatible with **BiFunction<? super V, ? super V, ? extends V>**. The two callback arguments here are **the old value** and **the value to merge**, not key and value. If the key has no non-null mapping yet, merge uses the supplied value without calling remappingFunction; if the callback returns null when called, the mapping is removed.

The exact same lambda syntax (a, b) -> a + b can mean different things in compute and merge. Always read the actual API signature to know **what the two arguments represent**.

### 6.4. Map.replaceAll also uses BiFunction

~~~java
java.util.Map<String, Integer> prices =
    new java.util.HashMap<>();
prices.put("a", 10);
prices.put("b", 20);

prices.replaceAll((key, oldPrice) -> oldPrice + 1);
~~~

Here BiFunction receives the key and old value and returns the new value. replaceAll mutates the Map's contents; even though the callback may be pure, **the Map.replaceAll call itself** produces a side effect on the Map. Distinguish the purity of the callback function from the purity of **the overall API call**.

### 6.5. BiPredicate is usually a custom-passed business rule

java.util.Map does not have a general equivalent to forEach that directly accepts a BiPredicate to filter by key and value. When you need to check two factors simultaneously, you can define your own helper method:

~~~java
static <T, U> boolean check(
        T first,
        U second,
        java.util.function.BiPredicate<? super T, ? super U> rule) {
    return rule.test(first, second);
}
~~~

Using it with concrete data:

~~~java
boolean ok = check(5, 3,
    (available, requested) -> available >= requested);
~~~

Passing a BiPredicate into a method is useful when you need interchangeable rules in tests, validation policies, or combined conditions.

## 7. Relationship with Function, Predicate, Consumer, and BinaryOperator

The java.util.function package has corresponding single-input interfaces:

| Single input | Two inputs |
| --- | --- |
| Function<T,R> | BiFunction<T,U,R> |
| Predicate<T> | BiPredicate<T,U> |
| Consumer<T> | BiConsumer<T,U> |

Several other interfaces also accept two values but carry stronger constraints:

**BinaryOperator<T>** is a specialization of BiFunction<T,T,T>, meaning both inputs and the output must have the same type T.

~~~java
java.util.function.BinaryOperator<Integer> max = Integer::max;
System.out.println(max.apply(4, 9)); // 9
~~~

BinaryOperator is typically appropriate when combining two values of the same kind, such as an accumulator for reduce or merge, and provides static methods like minBy/maxBy to create Comparator-based operators.

**IntBinaryOperator** is a specialized functional interface for two primitive ints returning an int:

~~~java
java.util.function.IntBinaryOperator sum = Integer::sum;
System.out.println(sum.applyAsInt(4, 9)); // 13
~~~

IntBinaryOperator **is not a subinterface of BiFunction<Integer,Integer,Integer>**; it has its own SAM taking and returning primitive int.

If you only need two Object inputs and a primitive int result, there is **ToIntBiFunction<T,U>**; similarly there are ToLongBiFunction and ToDoubleBiFunction. If you need a consumer taking one object and one primitive int value, there is **ObjIntConsumer<T>** (alongside ObjLongConsumer, ObjDoubleConsumer).

There is no interface named **IntBiPredicate** in the standard java.util.function package. When you want a two-int-parameter predicate that avoids boxing, you can define a specialized functional interface yourself:

~~~java
@FunctionalInterface
interface IntPairTest {
    boolean test(int left, int right);
}
~~~

BiPredicate<Integer,Integer> remains suitable for many problems, but when a callback runs in a hot loop with large data volumes, evaluate boxing/unboxing costs and benchmark before optimizing.

## 8. Generics, type inference, and method references

All three interfaces are **generic interfaces whose SAM is non-generic at the method level**. T and U are declared on the interface, while R is only on BiFunction. Therefore, lambdas can receive a clear target type and the compiler infers the lambda parameters:

~~~java
java.util.function.BiFunction<String, Integer, String> format =
    (text, count) -> text + ":" + count;
~~~

In that target type, text has type String and count has type Integer. With method references, the referenced method signature must also match:

~~~java
java.util.function.BiPredicate<String, String> same =
    String::equals;
~~~

An unbound instance method reference of the first passed-in object can work like (a, b) -> a.equals(b) when the target matches; specifically, String::equals has Object as its second parameter, which accepts String.

### 8.1. Wildcards and variance

When writing APIs with type parameters, declare wildcards according to data flow direction:

~~~java
static <T, U> boolean passes(
        T left,
        U right,
        java.util.function.BiPredicate<? super T, ? super U> condition) {
    return condition.test(left, right);
}
~~~

The condition can accept supertypes of T and U because it **consumes** both inputs. Similarly, an API accepting a BiConsumer can usually accept BiConsumer<? super T,? super U>.

BiFunction both accepts two values and produces an output, so the flexible form in API parameters is usually:

~~~java
java.util.function.BiFunction<? super T, ? super U, ? extends R>
~~~

T and U use super because the function consumes data; R uses extends because the function produces data. The snippets containing T, U, R here are **generic signature patterns**, not standalone Java statements.

Overly broad parameterization or using raw types to bypass generic errors can lose static type checking and cause ClassCastException. Keep type parameters explicit or use wildcards appropriately for the purpose.

### 8.2. Boxing/unboxing and null

With BiFunction<Integer,Integer,Integer>, Integer is a wrapper type: the lambda (a,b) -> a+b typically unboxes both inputs to int, adds them, and boxes the result. If a or b is null, addition throws NullPointerException.

BiPredicate<Integer,Integer> returns a primitive boolean, yet both Integer inputs can still be null; BiConsumer<String,Integer> can receive null if the caller passes null, and the callback must decide how to handle it.

Do not assume Java automatically validates inputs, converts null to 0, or prevents overflow. For monetary calculations, consider BigDecimal and rounding policies; for int, Math.addExact or Math.multiplyExact helps detect overflow.

### 8.3. Checked exceptions

The SAMs apply, test, and accept of these three interfaces **do not declare checked exceptions**. A lambda that directly throws an unhandled IOException or SQLException will not be compatible with those SAMs.

The solution depends on design: handle the exception at an appropriate boundary, return a result type capable of representing errors, or define a custom functional interface with an appropriate throws clause. Do not blindly catch Exception and return null/false, as that loses business error information.

## 9. Complete runnable Java 17+ program

Problem: given order lines, use **BiPredicate** to decide whether to accept, **BiFunction** to compute and format the amount, and **BiConsumer** to print audit logs and record events. The program intentionally keeps the last two actions separate from the calculation, helping distinguish value-returning functions from side effects.

Create the file **BiInterfacesDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.BiConsumer;
import java.util.function.BiFunction;
import java.util.function.BiPredicate;

public class BiInterfacesDemo {
    record OrderLine(String sku, int quantity, int unitPrice) {}

    public static void main(String[] args) {
        Map<String, Integer> stock = Map.of("book", 4, "pen", 2);
        List<OrderLine> lines = List.of(
            new OrderLine("book", 2, 100),
            new OrderLine("pen", 3, 10),
            new OrderLine("pen", 1, 10)
        );

        BiPredicate<Integer, Integer> enoughStock =
            (available, requested) -> requested > 0 && available >= requested;
        BiPredicate<Integer, Integer> withinLimit =
            (available, requested) -> requested <= 2;
        BiPredicate<Integer, Integer> accepted = enoughStock.and(withinLimit);

        BiFunction<Integer, Integer, Integer> lineAmount = Math::multiplyExact;
        BiFunction<Integer, Integer, String> displayAmount =
            lineAmount.andThen(value -> value + " VND");

        List<String> events = new ArrayList<>();
        BiConsumer<String, Integer> log =
            (sku, amount) -> System.out.println("sold:" + sku + "=" + amount);
        BiConsumer<String, Integer> record =
            (sku, amount) -> events.add(sku + "=" + amount);
        BiConsumer<String, Integer> logThenRecord = log.andThen(record);

        int total = 0;
        for (OrderLine line : lines) {
            int available = stock.getOrDefault(line.sku(), 0);
            if (!accepted.test(available, line.quantity())) {
                System.out.println("SKIP " + line.sku() + " x" + line.quantity());
                continue;
            }
            System.out.println(line.sku() + " -> "
                + displayAmount.apply(line.quantity(), line.unitPrice()));
            int amount = lineAmount.apply(line.quantity(), line.unitPrice());
            logThenRecord.accept(line.sku(), amount);
            total = Math.addExact(total, amount);
        }
        System.out.println("total=" + total);
        System.out.println("events=" + events);
        System.out.println("rejected=" + accepted.negate().test(2, 3));
    }
}
~~~

Compile and run in the directory containing the file using JDK 17 or later:

~~~bash
javac BiInterfacesDemo.java
java BiInterfacesDemo
~~~

**Exact** stdout:

~~~text
book -> 200 VND
sold:book=200
SKIP pen x3
pen -> 10 VND
sold:pen=10
total=210
events=[book=200, pen=10]
rejected=true
~~~

Step-by-step data flow explanation:

1. For book, stock = 4 and requested = 2. Both enoughStock and withinLimit are true. BiFunction computes 2 × 100 = 200 and andThen produces "200 VND".
2. BiConsumer logThenRecord prints the book event first, then stores "book=200" in the events list. Printing and list appending are **side effects** placed in a clear location.
3. For the pen line with quantity 3, stock = 2 so enoughStock is false; BiPredicate.and short-circuits, the line is skipped, and no corresponding event is recorded.
4. For the pen line with quantity 1, both conditions are true; the amount is 10. The total of the two accepted lines is 200 + 10 = 210.
5. events is an ArrayList updated by BiConsumer. The program iterates sequentially, so the order of the two elements is book then pen.
6. accepted.negate().test(2,3) is true, because accepted.test(2,3) is false.

The example uses a **fixed stock table** to focus on illustrating callbacks, not a real inventory-deduction system. When building a real order workflow, you must update inventory consistently, account for previously accepted orders, and control concurrency and transactions. Checking each line against a static stock snapshot is not enough to prevent overselling.

In the program, displayAmount applies lineAmount first to print the string, and then the code calls lineAmount a second time to get amount for auditing and the total. This is safe for the pure multiplication used here, but in real business logic you should **compute once and reuse the result** if the calculation is expensive or has side effects.

## 10. Other application patterns

### 10.1. BiFunction for decoupling calculation policies

~~~java
static int priceAfter(
        int base,
        int discount,
        java.util.function.BiFunction<Integer, Integer, Integer> policy) {
    return policy.apply(base, discount);
}
~~~

By passing in a policy, callers can choose a discount formula without modifying the orchestration method. However, because the parameters are boxed Integers, for high-volume calculations consider IntBinaryOperator or an explicit domain data type. If monetary formulas involve rounding, clearly specify calculation order and currency unit.

### 10.2. BiPredicate for checking relationships between two objects

~~~java
record User(String id, String role) {}
record Resource(String ownerId, boolean publicAccess) {}

java.util.function.BiPredicate<User, Resource> canView =
    (user, resource) ->
        resource.publicAccess() || resource.ownerId().equals(user.id());
~~~

This is an **illustrative snippet** that can be placed inside a method along with the appropriate record definitions. The primary use case for BiPredicate is a condition tied to **two entities**. In real systems, authorization rules must also handle null, authentication, missing resources, and multiple roles; the example only shows a simple relationship.

### 10.3. BiConsumer for callbacks when results have a key and value

~~~java
java.util.function.BiConsumer<String, Integer> audit =
    (key, value) -> System.out.println("Changed " + key + "=" + value);
~~~

BiConsumer can be passed into a processing stage that has already finalized data, such as emitting an audit for a product-code/quantity pair. Use BiConsumer when the action needs no return value. If the callback must report success/failure via a value, consider BiFunction<T,U,Result> or designing a dedicated Result type instead of hiding failures.

## 11. Common mistakes when using the three interfaces

**Mistake 1 — Calling the wrong SAM method.** BiFunction calls apply, BiPredicate calls test, BiConsumer calls accept. The three names correspond to three different contracts; there is no common execute method in the standard interfaces.

**Mistake 2 — Confusing BiFunction.andThen with BiConsumer.andThen.** BiFunction takes a Function to transform **a single result R**; BiConsumer takes a BiConsumer and passes **both arguments T, U** to each action.

**Mistake 3 — Using BiConsumer to compute data.** A lambda that mutates an external total variable without returning a result makes code depend on shared state, hard to test, and unsafe in parallel execution. Whenever possible, use BiFunction to return a result and place side effects in a separate step.

**Mistake 4 — Putting side effects in BiPredicate.** Because and/or short-circuit, the right-hand predicate may not run; do not use them to guarantee logging or incrementing a counter an exact number of times.

**Mistake 5 — Misunderstanding Map callback parameters.** Map.forEach receives key and value; compute receives key and oldValue; merge receives oldValue and newValue. All three take two parameters, but their meanings differ.

**Mistake 6 — Ignoring null.** Map.compute and merge have special rules when the callback returns null. An Integer unboxed from null throws NullPointerException. Designs must explicitly state whether data can be null.

**Mistake 7 — Assuming lambdas are automatically thread-safe.** A BiConsumer mutating a shared ArrayList in a parallel stream can lose data or corrupt state. Functional interfaces do not automatically synchronize or isolate side effects.

**Mistake 8 — Overusing boxed types on hot paths.** BiFunction<Integer,Integer,Integer> can incur boxing/unboxing. Consider IntBinaryOperator or ToIntBiFunction where appropriate, and measure real performance before optimizing.

**Mistake 9 — Confusing generic type parameters.** BiPredicate<T,U> has no type parameter R because its output is fixed to boolean. BiConsumer<T,U> has no output. BiFunction<T,U,R> has three type parameters. Do not use raw types to avoid declaring the proper signature.

**Mistake 10 — Assuming each callback runs only once.** Depending on the calling API, behavior may be re-executed by business control flow; invocation order can also differ in concurrent environments. Side-effect design must account for retries, exceptions, idempotency, and transactions.

## 12. Self-check

1. When both inputs are Integer but you need to return a String, which interface is most appropriate? Why?
2. Does BiPredicate.and call the second predicate when the first predicate is false? How does that affect things if the second predicate writes a log?
3. In BiFunction.andThen, how many parameters does the function in the next step have, and where does its input type come from?
4. With Map.merge("x", 2, Integer::sum), does the Integer::sum callback receive the key "x"?
5. Does BiConsumer.andThen continue running the second action if the first action throws an exception?
6. Why is BinaryOperator<Integer> suitable for adding two Integers, while BiFunction<Integer,String,Long> suits a different kind of problem?
7. If you sum amounts millions of times using two ints, which primitive interface can help limit boxing?
8. Identify where side effects occur in the example program and explain why folding all of them into BiFunction is not good design.

**Key takeaway:** choose **BiFunction** to **return a result from two inputs**, **BiPredicate** to **evaluate a condition on two inputs**, and **BiConsumer** to **perform an action with two inputs**. Understanding their SAMs, composition rules, generics, boxing, nulls, and side effects helps apply this trio properly with Java APIs and business requirements.
