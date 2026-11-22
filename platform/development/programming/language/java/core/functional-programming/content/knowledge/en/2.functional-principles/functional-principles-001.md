# Pure Functions and Same Input, Same Output in Java

## 1. Objectives

After this lesson, you will be able to:

- Explain a **pure function** and the two conditions it must satisfy simultaneously: its result depends solely on its inputs, and it produces no **observable side effects**.
- Distinguish determinism from purity, and understand what "same input" means when a parameter is a mutable object.
- Identify hidden dependencies on time, random numbers, global state, files, databases, or mutable objects.
- Write and test Java data transformations in a pure-function style, and place I/O operations at the boundaries of the program.

## 2. What Is a Pure Function?

A function is considered pure when **both** of the following conditions hold:

1. **The same input in terms of values and relevant state always produces the same result.** The function does not arbitrarily read external state that can change between calls. For a valid input, the result is determined solely by the input; if the function reports an error, the error behavior must also be consistent with the input.
2. **It does not modify observable state outside the function.** It does not mutate mutable parameters or shared variables, write to files or databases, print logs to the console, or send HTTP requests. Creating local objects for computation is normal; the issue is whether that mutation is exposed and affects elsewhere.

Consider the mathematical example **f(x) = x × x**: when x = 3, the result is always 9. When a function only computes and returns a result, we can replace the call with the resulting value itself without changing program behavior in the corresponding context. This property is called **referential transparency**.

~~~java
static int square(int x) {
    return x * x;
}
~~~

The function above is pure within the domain of Java's **int** type: even with integer overflow in multiplication, the result is still deterministically defined by Java for the same operands. However, overflow can cause the result to differ from the expected mathematical square; you should choose a data type or check for overflow according to business requirements.

**"Same input" does not simply mean the same reference address.** If you pass an object whose contents can change, two calls receiving the same reference may still observe two different states. To achieve stability, clearly define the input data, its lifecycle, and the possibility of concurrent modification.

## 3. A Deterministic Result Is Not Enough to Make a Function Pure

The following snippet returns the same arithmetic result but still has a side effect:

~~~java
static int twiceAndPrint(int x) {
    System.out.println("Computing " + x);
    return x * 2;
}
~~~

For x = 5, the return value is always 10; however, calling it twice prints two lines. If you replace the calls with the constant 10, the program loses those printed lines: therefore, the function is **not pure**.

Conversely, the following function does not modify data, yet still has a hidden dependency:

~~~java
static boolean isExpired(java.time.Instant deadline) {
    return java.time.Instant.now().isAfter(deadline);
}
~~~

With the same **deadline** argument, the result can change over time. The improvement is to pass the point in time of observation as an **explicit input value**:

~~~java
static boolean isExpired(java.time.Instant deadline,
                         java.time.Instant now) {
    return now.isAfter(deadline);
}
~~~

The second function is pure if its arguments are immutable **Instant** values. Note: merely passing a **Clock** or **Random** object into a function and calling its methods does not necessarily make the function pure; that object may still represent a mutable source of state. To be pure, pass the **already-read time value**, the **already-generated random value**, or model the input/output state explicitly.

| Case | Same input gives same result? | No side effects? | Pure? |
| --- | --- | --- | --- |
| **x → x * 2** on **int** | Yes | Yes | Yes |
| Compute then **System.out.println(...)** | Yes for return value | No | No |
| Read **Instant.now()** inside the function | Not guaranteed | Possibly | No |
| Read mutable **static** variable | Not guaranteed | Possibly | No |
| Modify passed **List** and return its size | Not guaranteed | No | No |
| Create local **ArrayList**, return new result list | Yes if input is stable | Yes | Yes |

The table describes observable behavior; it does not mean that every function that uses objects, allocates memory, or throws exceptions is impure.

## 4. Standalone Runnable Java 17 Example

Create a file named **PureFunctionDemo.java** with the following content:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class PureFunctionDemo {
    static int sumSquares(List<Integer> values) {
        return values.stream()
                .mapToInt(value -> value * value)
                .sum();
    }

    static String normalize(String text) {
        return text.strip().toLowerCase(Locale.ROOT);
    }

    static List<Integer> append(List<Integer> source, int item) {
        List<Integer> copy = new ArrayList<>(source);
        copy.add(item);
        return List.copyOf(copy);
    }

    public static void main(String[] args) {
        List<Integer> original = List.of(1, 2, 3);

        System.out.println(sumSquares(original));
        System.out.println(sumSquares(original));
        System.out.println(normalize("  JAVA  "));
        System.out.println(append(original, 4));
        System.out.println(original);
    }
}
~~~

Compile and run:

~~~bash
javac PureFunctionDemo.java
java PureFunctionDemo
~~~

Exact output:

~~~text
14
14
java
[1, 2, 3, 4]
[1, 2, 3]
~~~

**Explanation:**

- **sumSquares** only reads the input list and computes the sum of squares. With **List.of(1, 2, 3)**, the sum is 1 + 4 + 9 = 14 on both calls. The example assumes non-null elements and operations within a suitable range; for large numbers, consider **int** overflow.
- **normalize** processes a string, which is an immutable value. **strip()** removes leading/trailing whitespace and **toLowerCase(Locale.ROOT)** makes the lowercasing rules independent of the host machine's default locale. A null argument will cause a **NullPointerException** consistently for the same input.
- **append** creates a new list and does not add directly to **source**. **List.copyOf** returns a list that does not allow modifying elements through methods such as **add**; with immutable **Integer** elements in this example, this is a safe output to share. **List.copyOf** copies element references rather than automatically deep-copying mutable objects.
- **main** prints to the console, so **main** is not pure. Placing I/O outside the computations allows the core processing logic to remain pure and easy to test.

**Contract limitation:** the illustrative methods above are considered pure provided the input data is not modified during computation. For instance, **sumSquares** accepts a **List<Integer>** that could be mutable; if another thread modifies the list during the call, the result or exception may vary depending on execution scheduling. A function does not automatically enforce immutability on parameters owned by external callers.

## 5. Mutable Inputs and Hidden State

### 5.1. Mutating Parameters Is a Side Effect

~~~java
static int addAndCount(List<String> names, String name) {
    names.add(name);
    return names.size();
}
~~~

If **names** initially contains one element, calling it twice with the same **name** on **that same list** can return 2 and then 3. The function both mutates its input and introduces call-history dependence.

You can switch to returning a new result, letting the caller decide whether to update its own variable:

~~~java
static List<String> withName(List<String> names, String name) {
    List<String> copy = new java.util.ArrayList<>(names);
    copy.add(name);
    return List.copyOf(copy);
}
~~~

**withName** does not modify the original list, but when passing reference data that may be concurrently modified, a stable input contract is still required. **List.copyOf** also does not accept null elements; that is an API decision to consider during design.

### 5.2. Mutable Static Variables Leave Inputs Incomplete

~~~java
static int runningTotal = 0;

static int addAndRecord(int amount) {
    runningTotal += amount;
    return runningTotal;
}
~~~

With the same **amount = 5**, the first result may be 5 and the second 10. The function depends on **runningTotal** and mutates it at the same time. Replace this with explicit state transitions:

~~~java
static int nextTotal(int currentTotal, int amount) {
    return currentTotal + amount;
}
~~~

The caller can use **total = nextTotal(total, 5)** to update its state in the orchestration layer. The **nextTotal** function remains pure: the old state is the input, and the new state is the result. This is the foundational idea when handling state with reducers or event models.

### 5.3. Outer-Layer Immutability Is Not Necessarily Deep Immutability

A **final** variable only prevents reassigning the reference; **final List<String> items = new ArrayList<>()** still allows **items.add(...)**. A **List.unmodifiableList(...)** is a view that disallows modification through the wrapper, but the underlying data can still be modified via another reference. **List.copyOf(...)** creates a structural snapshot of the list in typical cases, yet does not deep-copy mutable elements. A **record** also does not automatically provide deep immutability if its components hold mutable arrays or lists.

When designing pure inputs, prefer **String**, numbers, **Instant**, **LocalDate**, enums, records containing immutable values, or snapshots of the required data. For complex object graphs, clearly define ownership, copying, and the desired level of immutability.

## 6. Pure Functions in Lambdas, Streams, and Business Logic

Lambda syntax **does not automatically guarantee** purity. The following lambda is not pure because it operates on shared state:

~~~java
List<String> names = List.of("An", "Binh");
names.forEach(name -> System.out.println(name));
~~~

**forEach** is intentionally used for side effects. Meanwhile, the transformation below is easier to reason about because it only builds result data:

~~~java
List<String> upper = names.stream()
        .map(name -> name.toUpperCase(Locale.ROOT))
        .toList();
~~~

**Stream.toList()** has been available since Java 16 and returns a list that cannot be modified via mutating **List** methods. It does not make every element deeply immutable. A lambda reading a captured value under **effectively final** rules can still be impure if that value is a reference to a mutable object.

A typical workflow separates into three zones:

1. **Read** data at the boundary: HTTP requests, databases, files, system clock, or random sources.
2. **Pure computation** on the collected values: normalization, rule validation, pricing, grouping, filtering, summing, state transitions.
3. **Perform effects**: save results, send notifications, write logs, or return HTTP responses.

For example, to evaluate order expiration: the outer layer gets **Instant.now()** once, then calls **isExpired(deadline, now)**. Computations in the core become reproducible by passing the exact same pair of values in tests.

## 7. Practical Value and Limitations

- **Easy to test:** you can build a table of input/output pairs and assert directly, without needing to mock clocks, networks, or databases inside the computation function.
- **Easy to reason about:** results depend less on call order; refactoring and reuse are safer when input contracts are clear.
- **Easy to parallelize:** if no shared state is mutated concurrently, independent computations are less prone to race conditions. Still, you must watch out for mutable inputs and synchronization/threading overhead.
- **Memoizable:** caching by input is suitable when the function is pure and inputs have a stable key representation. Caching the result of a function that reads time or live data directly can return stale, unexpected results.
- **Not every function needs to be pure:** saving to a database, writing files, and logging are necessary application effects. The goal is to place effects in clear locations while keeping most business logic independently computable.
- **Do not equate purity with performance:** copying data to avoid mutation has memory and time costs. Choose data structures, snapshot sizes, and immutability boundaries based on practical needs.

## 8. Checking Purity During Code Review

Check each item in turn:

1. Does the function read **System.currentTimeMillis()**, **Instant.now()**, **Math.random()**, mutable static variables, stateful singletons, updatable configuration, or data from I/O?
2. Does the function modify parameters, referenced objects, collections, static fields, or external resources?
3. Does the function print to the console, write logs, call APIs, send messages, or operate on a database?
4. Given the same **fixed input values**, including object contents, can the result be reproduced? Is there a race condition that could change the answer?
5. Does the function return a shared mutable object that the caller could later modify, affecting subsequent calls?
6. If using **Stream** or lambdas, does the body only transform values or does it contain side effects? Could **parallelStream()** expose shared-state access issues?

**Helpful testing practices:** call the function multiple times with the same immutable dataset and assert the results; keep a snapshot of the input data to assert it was not modified; run the computation with different input data, then call it again with the initial dataset to detect history dependence. These are ways to find bugs, but a few tests cannot prove absolute purity; you must still read the contract and dependencies.

## 9. Practice Exercises

**Exercise 1 — Classification.** Consider three methods:

~~~java
static int a(int x) { return x + 1; }

static int b(int x) {
    System.out.println(x);
    return x + 1;
}

static long c(long offset) {
    return System.currentTimeMillis() + offset;
}
~~~

**Answer:** **a** is pure under **int** arithmetic; **b** has a deterministic numeric output but has a console side effect; **c** depends on the system clock and therefore does not guarantee the same output for the same input. Only **a** satisfies both conditions.

**Exercise 2 — Fixing a design.** A **discountPrice** function currently reads the discount rate from a mutable static variable and logs on every calculation. Change it to **discountPrice(price, rate)** that only computes the result, moving configuration reading and logging to the caller layer. Clearly define rounding mode and monetary data type (for example, **BigDecimal**) according to business requirements; do not use **double** arithmetic as the default solution for money.

**Exercise 3 — Reasoning about Lists.** If **List<Integer> xs = new ArrayList<>(List.of(1, 2))** is passed to a function that only reads its elements, and another part of the code calls **xs.add(3)** before the next calculation, why can the result differ despite using the same **xs** variable? Answer: reference identity did not change, but **data value** changed; inputs must be considered by their observable state, or an appropriate snapshot/immutability should be used.

## 10. Takeaways

**Pure function = result determined solely by inputs + no observable side effects.** These two conditions are independent and both are required. In Java, purity is a property of **behavior and data contracts**, not a language keyword, nor does it arise automatically from writing lambdas, Streams, **final**, or **record**. Turn mutable dependencies into **explicit input values**, create new results instead of mutating shared data, and place I/O at program boundaries so code is easy to test, reproduce, and maintain.
