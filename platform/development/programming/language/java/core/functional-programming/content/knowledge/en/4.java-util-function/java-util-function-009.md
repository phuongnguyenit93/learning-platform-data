# ObjIntConsumer and combining objects with primitive types in Java

## 1. Objectives

**ObjIntConsumer<T>** is a functional interface in **java.util.function**. It takes an object of type **T** and a primitive **int** value, performs an action, and finishes without returning a value. It is the right tool when you need to pass behavior that processes an **object + integer** pair, such as adding a quantity to an item, awarding points to an account, or writing a numeric value to a buffer.

After this lesson, you can recognize its SAM signature, write compatible lambdas and method references, distinguish ObjIntConsumer from BiConsumer/IntConsumer and other specializations, coordinate multiple operations in order, and control side effects, nulls, overflow, and concurrent access.

## 2. Signature of ObjIntConsumer<T>

Simplified declaration from Java 17:

~~~java
@FunctionalInterface
public interface ObjIntConsumer<T> {
    void accept(T t, int value);
}
~~~

This is a description for learning **the built-in JDK API**, not code you need to redeclare yourself. Import when using it:

~~~java
import java.util.function.ObjIntConsumer;
~~~

Reading each part:

| Component | Meaning |
| --- | --- |
| **T** | Reference type of the first argument, such as Account, Stock, StringBuilder |
| **int** | Primitive type of the second argument, such as quantity or score |
| **accept(T t, int value)** | Single abstract method (SAM) |
| **void** | No return value; the effect of the call usually lies in updating or manipulating data |
| **@FunctionalInterface** | Allows the compiler to verify the single-SAM contract |

Because it has exactly one abstract method, ObjIntConsumer works with **lambdas** and **method references**. A lambda's type is determined by the assignment context (target typing):

~~~java
ObjIntConsumer<StringBuilder> appendNumber =
        (builder, number) -> builder.append(number);

StringBuilder b = new StringBuilder("Qty=");
appendNumber.accept(b, 12);
System.out.println(b); // Qty=12
~~~

Here **builder** has type StringBuilder and **number** is primitive int. The line **appendNumber.accept(b, 12)** mutates the object b itself. A **void** return type does not mean there is no observable outcome: an external object or resource may have changed.

**Note accurately that generic T applies only to the first argument.** This signature always takes an int in the second position; you cannot write ObjIntConsumer<Account, Integer> or ObjIntConsumer<Account, Long> because the interface has only one type parameter.

## 3. Comparing with related interfaces

| Interface | SAM | Purpose |
| --- | --- | --- |
| **Consumer<T>** | **void accept(T t)** | Takes one object |
| **IntConsumer** | **void accept(int value)** | Takes one int |
| **BiConsumer<T,U>** | **void accept(T t, U u)** | Takes two objects |
| **ObjIntConsumer<T>** | **void accept(T t, int value)** | Takes one object and one int |
| **ObjLongConsumer<T>** | **void accept(T t, long value)** | Takes one object and one long |
| **ObjDoubleConsumer<T>** | **void accept(T t, double value)** | Takes one object and one double |
| **BiFunction<T,U,R>** | **R apply(T t, U u)** | Takes two objects and returns one result |

**ObjIntConsumer is not a subinterface of BiConsumer.** It is a **primitive specialization** for when the second argument is an int. Therefore, you cannot directly assign an ObjIntConsumer<T> variable to a BiConsumer<T,Integer> variable; a lambda adapter is needed if an API requires switching interfaces.

### 3.1. Primitives avoid boxing at the SAM boundary

Compare:

~~~java
BiConsumer<StringBuilder, Integer> boxed =
        (target, number) -> target.append(number);

ObjIntConsumer<StringBuilder> primitive =
        (target, number) -> target.append(number);
~~~

BiConsumer uses **Integer** because generic type parameters cannot be primitives. When calling **boxed.accept(builder, 42)** with an int literal argument, Java must perform autoboxing to turn 42 into an Integer matching the SAM. ObjIntConsumer accepts **int directly**, so no boxing is needed just to pass the second argument across the **accept** call.

This reduces unnecessary type conversions, especially when processing very large numbers of primitive values. Even so, **do not conclude that every program using ObjIntConsumer automatically runs faster**: the JIT, escape analysis, allocation, and internal code still matter greatly. If performance is a goal, benchmark the actual scenario.

### 3.2. When to choose which?

- Need to **perform an action** on an object and an integer: ObjIntConsumer<T>.
- Need to update an object with a **long** or **double**: ObjLongConsumer<T> or ObjDoubleConsumer<T>.
- Need an action on two reference types: BiConsumer<T,U>.
- Need to **return a new result** instead of just performing an effect: BiFunction or an appropriate domain method.
- Need an action taking only primitive int: IntConsumer.

Choose the interface by **contract** rather than chasing lambda brevity.

## 4. Writing lambdas and method references

An ObjIntConsumer can be expressed as a lambda:

~~~java
ObjIntConsumer<StringBuilder> addInt =
        (builder, amount) -> builder.append(amount);
~~~

Or a method reference:

~~~java
ObjIntConsumer<StringBuilder> addInt =
        StringBuilder::append;
~~~

Both snippets above are alternatives; **do not declare the same name addInt in the same scope**. The method reference **StringBuilder::append** uses the first argument of **accept** as the receiver (builder) and the second argument as the **append(int)** parameter. Even though **append(int)** returns StringBuilder, calling it can match a **void** target when the return value is discarded.

Given a custom class like this:

~~~java
class Counter {
    private int total;

    void add(int value) {
        total = Math.addExact(total, value);
    }

    int total() {
        return total;
    }
}
~~~

Then:

~~~java
ObjIntConsumer<Counter> increase = Counter::add;
Counter c = new Counter();
increase.accept(c, 3);
System.out.println(c.total()); // 3
~~~

Both snippets must be in a context where Counter is declared and ObjIntConsumer is imported; these are **code fragments**, not a standalone file.

**You do not need a lambda in every case.** If the consumer is not being passed around or composed, calling **counter.add(3)** directly is sometimes clearer. Consumers are useful when behavior is supplied as an API parameter, passed to an orchestration class, or configured dynamically.

## 5. Defining a clear update contract

ObjIntConsumer usually represents a **side effect**. The task receives data and may:

- Mutate the state of the passed-in object.
- Write data or call another API.
- Accumulate numbers into an accumulator.
- Write logs or emit events.

Because **accept** returns void, the caller cannot obtain a new result value directly from the call. If state changes, the outcome is observed through the object or external system.

Before writing a consumer, clarify:

1. **Meaning of the int:** increment amount, absolute value, index, unit, or status code?
2. **Value domain:** is 0 valid? Are negatives allowed? Maximum limit?
3. **Object ownership:** may it be mutated directly, or must a copy be made?
4. **Failures:** where are nulls, overflow, or I/O errors detected?
5. **Concurrency:** can multiple threads mutate the same object simultaneously?

For a pure calculation method expected to return a new object, choose a type **with a return value**. Consumer does not make data immutable or create automatic transactions.

## 6. Coordinating steps: there is no andThen()

An easily overlooked difference in Java 17: **ObjIntConsumer<T> does not provide a default andThen() method**. This differs from Consumer<T>, IntConsumer, and BiConsumer<T,U>, which do have **andThen**.

The following **does not compile**:

~~~java
// ObjIntConsumer<Stock> validate = ...;
// ObjIntConsumer<Stock> update = ...;
// ObjIntConsumer<Stock> both = validate.andThen(update);
~~~

To perform multiple steps in order, combine them in a new lambda:

~~~java
ObjIntConsumer<Stock> combined = (item, amount) -> {
    validate.accept(item, amount);
    update.accept(item, amount);
};
~~~

This snippet assumes **Stock**, **validate**, and **update** are already defined in context.

You can create a reusable helper method where needed:

~~~java
static <T> ObjIntConsumer<T> sequence(
        ObjIntConsumer<? super T> first,
        ObjIntConsumer<? super T> second) {
    java.util.Objects.requireNonNull(first);
    java.util.Objects.requireNonNull(second);
    return (target, number) -> {
        first.accept(target, number);
        second.accept(target, number);
    };
}
~~~

This is an **illustrative method** that must be placed in a class with ObjIntConsumer imported. If **first.accept** throws an exception, **second.accept** will not be called. If first already mutated state and second fails, the lambda **does not automatically roll back** the state.

To orchestrate a task consisting of validation, update, and audit, a common order is:

~~~text
Object + int
    |
    v
validate -- failure --> error message
    |
    v
update   -- failure --> error message
    |
    v
audit success
~~~

This order only describes the calls; if you need atomic transactions or guaranteed event recording after a database commit, design a dedicated transaction/outbox or orchestration mechanism.

## 7. Complete Java 17 program: receiving stock

The inventory management example below combines **ObjIntConsumer<Stock>**, a method reference, an **int[]** array, and an adapter to **BiConsumer<Stock,Integer>**. Validation, updating, and result reporting are separated into distinct actions.

Create the file **ObjIntConsumerDemo.java**:

~~~java
import java.util.Objects;
import java.util.function.BiConsumer;
import java.util.function.ObjIntConsumer;

public class ObjIntConsumerDemo {
    static final class Stock {
        private final String sku;
        private int units;

        Stock(String sku, int units) {
            this.sku = Objects.requireNonNull(sku);
            if (units < 0) {
                throw new IllegalArgumentException("Negative initial stock");
            }
            this.units = units;
        }

        String sku() {
            return sku;
        }

        int units() {
            return units;
        }

        void receive(int amount) {
            units = Math.addExact(units, amount);
        }
    }

    public static void main(String[] args) {
        Stock notebook = new Stock("NOTE", 10);
        Stock pen = new Stock("PEN", 0);

        ObjIntConsumer<Stock> validate = (item, amount) -> {
            Objects.requireNonNull(item, "item");
            if (amount < 0) {
                throw new IllegalArgumentException("Negative amount");
            }
        };

        ObjIntConsumer<Stock> update = Stock::receive;

        ObjIntConsumer<Stock> audit = (item, amount) ->
                System.out.println("Added " + amount + " to " + item.sku());

        ObjIntConsumer<Stock> receiveAndAudit = (item, amount) -> {
            validate.accept(item, amount);
            update.accept(item, amount);
            audit.accept(item, amount);
        };

        receiveAndAudit.accept(notebook, 4);

        BiConsumer<Stock, Integer> boxedAdapter =
                (item, amount) -> receiveAndAudit.accept(item, amount);
        boxedAdapter.accept(pen, 2);

        int[] laterDeliveries = {1, 3};
        for (int amount : laterDeliveries) {
            validate.accept(notebook, amount);
            update.accept(notebook, amount);
        }

        System.out.println("NOTE=" + notebook.units());
        System.out.println("PEN=" + pen.units());
    }
}
~~~

Use JDK 17 or later:

~~~bash
javac ObjIntConsumerDemo.java
java ObjIntConsumerDemo
~~~

**Exact output:**

~~~text
Added 4 to NOTE
Added 2 to PEN
NOTE=18
PEN=2
~~~

Explanation:

- Notebook starts with 10 units. Receiving 4 brings the count to 14 and prints the message.
- Pen starts with 0 units. **boxedAdapter** takes Integer and delegates to ObjIntConsumer; pen becomes 2 and prints the message.
- The **int[] {1, 3}** loop adds 1 then 3 to notebook, so **14 → 15 → 18**. The loop only runs validation and update, not audit; therefore there are no two extra Added lines.
- **Stock::receive** is a method reference taking a Stock receiver and an int parameter, matching the **accept(Stock,int)** contract.
- **Math.addExact** throws ArithmeticException when the int sum exceeds range, rather than silently overflowing. The calculation is evaluated before assignment, so if it throws, the **units** field is not updated by that assignment.
- **main** uses System.out.println and mutates objects, so this is a procedure with side effects. Do not confuse it with a pure function.

**Limitation to note:** **Stock.receive(int)** does not directly forbid negative numbers; that rule is currently checked by **validate** at the call layer. If every update path must protect the inventory invariant, place the core validation inside Stock.receive itself or a single business update entry point. Do not treat an outer wrapper lambda as sufficient protection if other callers can bypass it.

## 8. Combining with primitive arrays and IntStream

When you have one **Stock** and multiple **int** incoming amounts, a direct loop is a simple choice:

~~~java
int[] amounts = {2, 5, 1};
for (int amount : amounts) {
    receiver.accept(stock, amount);
}
~~~

This illustrative code assumes **receiver** is ObjIntConsumer<Stock> and **stock** is initialized. There is no need to convert each array element to Integer.

Using **IntStream** also works:

~~~java
java.util.Arrays.stream(amounts)
        .forEach(amount -> receiver.accept(stock, amount));
~~~

Here IntStream's **forEach** expects an **IntConsumer**. The lambda **amount -> receiver.accept(stock, amount)** takes one int parameter and captures the **stock** reference; inside it calls the two-argument ObjIntConsumer.

Point of caution: **forEach can be a side-effecting operation**. If running a parallel stream where multiple callbacks update **stock** concurrently, race conditions or unstable results can occur unless state and logic are properly synchronized.

When you have multiple objects and multiple corresponding update amounts, validate the counts and relationship between the two sources before processing:

~~~java
if (stocks.size() != amounts.length) {
    throw new IllegalArgumentException("Different lengths");
}
for (int i = 0; i < amounts.length; i++) {
    receiver.accept(stocks.get(i), amounts[i]);
}
~~~

This snippet is also just a fragment with the variables already declared. If an error occurs on the third element, the first two elements may already have been updated. If business logic requires the entire batch to succeed or fail together, validate all data upfront and use an appropriate transaction strategy rather than relying solely on a loop.

## 9. Adapter between ObjIntConsumer and BiConsumer

Sometimes an API expects BiConsumer<T,Integer>, but existing logic is an ObjIntConsumer<T>. You can wrap it:

~~~java
ObjIntConsumer<StringBuilder> primitive =
        StringBuilder::append;

BiConsumer<StringBuilder, Integer> boxed =
        (builder, number) -> primitive.accept(builder, number);
~~~

For an API expecting ObjIntConsumer when you already have a BiConsumer:

~~~java
BiConsumer<StringBuilder, Integer> boxed =
        (builder, number) -> builder.append(number);

ObjIntConsumer<StringBuilder> primitive =
        (builder, number) -> boxed.accept(builder, number);
~~~

These two snippets are **two separate conversions** using the same variable names, so do not paste them into the same scope.

Their null contracts also differ:

- The second parameter **int** of ObjIntConsumer cannot be null.
- The second parameter **Integer** of BiConsumer can be null if the API and lambda allow it; unboxing a null Integer to int throws **NullPointerException**.
- The first parameter **T** is still a reference and can be null; an explicit policy or **Objects.requireNonNull** is needed.

An adapter does not automatically fix thread safety, overflow bugs, or side effects of the underlying consumer.

## 10. Data safety and multithreading

The ObjIntConsumer interface **does not guarantee thread safety**. Two threads concurrently calling a consumer on a mutable object can cause lost updates if addition only performs ordinary read–compute–write:

~~~java
// Illustrating a flawed pattern when sharing an unsynchronized counter:
ObjIntConsumer<Counter> add = Counter::add;
add.accept(sharedCounter, 1);
~~~

This fragment assumes Counter and sharedCounter are declared. An operation like **total += delta** is not automatically atomic. Solutions depend on context:

- Each thread owns a separate accumulator, then results are merged afterward.
- Use **synchronized** or a lock to protect the check-and-mutate region.
- For a single suitable counter, consider **AtomicInteger**, with an appropriate bounds/overflow policy.
- Route updates through a queue and process sequentially.
- Where possible, shift from mutation to functions that create new data, coordinating state at a responsible layer.

Using ObjIntConsumer does not make execution asynchronous. A normal **accept(...)** call runs immediately on the calling thread; scheduling on threads requires a thread/executor or another API.

## 11. Common mistakes in practice

| Mistake | Cause | Fix |
| --- | --- | --- |
| Writing ObjIntConsumer<T,Integer> | Interface has only one generic T | Use ObjIntConsumer<T> |
| Expecting **accept** to return a value | SAM returns void | Use a value-returning function |
| Calling **a.andThen(b)** | ObjIntConsumer has no andThen | Write a coordinating lambda or sequence helper |
| Passing null **Integer** and unboxing | Unboxing null throws NullPointerException | Check for null first |
| Not defining the meaning of the int | Callers confuse amount with index or absolute value | Use clear naming and business contracts |
| Adding ints without overflow checks | Result can wrap around silently | Math.addExact or an appropriate numeric type |
| Skipping negative-value checks | Quantity becomes invalid data | Validate at the invariant-enforcing boundary |
| Mutating the same object in a parallel stream | Race conditions or lost updates | Manage ownership, synchronize, or redesign |
| Auditing before updating and treating it as success | May log success when update fails | Define ordering and error/transaction strategy |

## 12. Testing each contract

At minimum, test the following cases for an inventory-management consumer:

1. An object with 5 units receives 3 more and becomes 8.
2. Whether receiving 0 is valid per the rules; if so, the quantity does not change.
3. Negative amounts are rejected before updating.
4. A null object is rejected without running update or audit.
5. At **Integer.MAX_VALUE**, adding 1 causes Math.addExact to throw ArithmeticException without recording an overflowed total.
6. If update fails, the "success" audit does not run.
7. If multiple threads are involved, test the synchronization design or ownership mechanism directly; do not infer atomicity from a functional interface.

Example testing addition and state, placed in a class with access to Stock:

~~~java
Stock item = new Stock("TEST", 5);
ObjIntConsumer<Stock> receive = Stock::receive;
receive.accept(item, 3);
if (item.units() != 8) {
    throw new AssertionError("Expected 8 units");
}
~~~

A single test does not prove all safety conditions, especially for concurrency. Examine the object contract, error paths, and how callers use the consumer.

## 13. Self-practice exercises

**Exercise 1 — Choose the interface.** Pick the right type for four tasks: (a) updating a Student's int score, (b) updating an Account's long balance, (c) printing only an int, (d) taking two objects and returning a new object.

**Answer:** (a) ObjIntConsumer<Student>; (b) ObjLongConsumer<Account> if genuinely an action; (c) IntConsumer; (d) BiFunction<T,U,R> with appropriate types.

**Exercise 2 — Predict the output.**

~~~java
StringBuilder text = new StringBuilder("S=");
ObjIntConsumer<StringBuilder> append = StringBuilder::append;
append.accept(text, 3);
append.accept(text, 7);
System.out.println(text);
~~~

**Answer:** **S=37**. Both numbers are appended to the string in order; this is not arithmetic addition 3 + 7.

**Exercise 3 — Fix the composition error.**

~~~java
ObjIntConsumer<StringBuilder> first =
        (b, n) -> b.append(n);
ObjIntConsumer<StringBuilder> second =
        (b, n) -> b.append("!");
// Wrong: first.andThen(second)
~~~

**Solution:**

~~~java
ObjIntConsumer<StringBuilder> both = (b, n) -> {
    first.accept(b, n);
    second.accept(b, n);
};
~~~

With initial builder **X** and n=2, the result after one call **both.accept(builder, 2)** is **X2!**.

**Exercise 4 — Design.** A system adds points to a Student using ObjIntConsumer<Student>, but two threads update concurrently. Propose a null contract, negative/overflow checks, invariant protection inside Student's method, and an appropriate synchronization or state-ownership strategy. Only then write the lambda or method reference turning the behavior into an ObjIntConsumer.

## 14. Key takeaways

**ObjIntConsumer<T> has the SAM void accept(T object, int value).** It is a functional interface for an action combining an object and a **primitive int**, avoiding unnecessary boxing on the SAM's second parameter. It **is not a subinterface of BiConsumer**, has no built-in **andThen**, and a normal **accept** call does not spawn a new thread.

When using it, give the numeric parameter a clear business meaning, check null/range/overflow, and define side-effect ordering and error boundaries. If you need a new result instead of mutating state, choose a method or functional interface with a return value.
