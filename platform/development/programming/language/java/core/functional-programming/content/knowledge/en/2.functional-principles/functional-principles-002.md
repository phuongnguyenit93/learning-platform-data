# Side Effects and External-State Dependencies in Java Functional Programming

In functional-style programming, an important principle is to **separate computation from side effects** and make explicit all data that a computation depends on. Two related but distinct issues are:

- **Side effect:** when performing an operation, the program also produces an observable change or interaction outside its return value.
- **External-state dependency:** the result or behavior of an operation depends on data that the call does not receive directly through its parameters, such as mutable global variables, the current time, the environment, a captured object, or data from an external system.

Java supports lambdas, method references, functional interfaces, and the Stream API for writing code in a functional style, but **does not automatically eliminate side effects or implicit dependencies**. Understanding these two concepts helps you write functions that are more predictable, easier to test, and safer for concurrency.

## 1. What is a side effect?

Consider the method:

~~~java
static int doubleOf(int value) {
    return value * 2;
}
~~~

Given the input 5, the method computes 10 without needing to modify external data. In contrast:

~~~java
static int calls = 0;

static int doubleAndCount(int value) {
    calls++;
    return value * 2;
}
~~~

Two calls to doubleAndCount(5) both return 10 while simultaneously modifying the shared variable calls. **Modifying calls** is a side effect; looking only at the return value does not tell the full story of what happened.

Common side effects:

| Operation | Observable side effect |
| --- | --- |
| Assigning/modifying a static variable or a field of a shared object | Subsequent state changes |
| Adding/removing elements in a shared List or Map | Data held elsewhere is mutated |
| System.out.println, writing to a file, logging, writing to a database | Produces output or modifies an external system |
| Sending an HTTP request, email, or message | Interacts with a service, potentially triggering external actions |
| Incrementing a counter, updating a shared cache | Mutates state that may affect subsequent calls |

**Not every assignment is a concerning side effect.** Creating and mutating a local variable or a new object whose reference has not escaped may simply be an internal implementation detail:

~~~java
static int sumPositive(int[] numbers) {
    int sum = 0;
    for (int n : numbers) {
        if (n > 0) {
            sum += n;
        }
    }
    return sum;
}
~~~

If the input array is not modified by the method and there are no other implicit interactions, the assignment sum += n only updates local state that does not leak outside. A function does not need to avoid all local variables to behave purely; what matters is **not producing observable changes outside the result**.

## 2. How do external-state dependencies differ from side effects?

Example:

~~~java
static int taxPercent = 10;

static int totalWithTax(int price) {
    return price + price * taxPercent / 100;
}
~~~

totalWithTax(100) can return 110 or 120 if another place changes taxPercent from 10 to 20. The method **reads** global state, even though it does not modify that variable itself. Therefore, **a function can depend on external state without causing side effects itself**.

The reverse direction also exists:

~~~java
static int printDouble(int number) {
    int result = number * 2;
    System.out.println(result);
    return result;
}
~~~

The return value may always equal number * 2 while the function still causes a side effect by printing to the console. A method can also both read external state and produce a side effect, such as reading the value of a shared counter and then incrementing that same counter.

| Question | Side effect | External-state dependency |
| --- | --- | --- |
| What do we observe? | The operation causes a change/interaction outside its return value | The result/behavior is governed by data not explicit in the arguments |
| Simple example | System.out.println("Hi") | Reading a mutable static variable |
| Why is it hard to test? | Requires tracking and isolating interactions or mutated state | Requires setting up implicit state before each call |
| How to improve | Move I/O operations or state updates to clear boundaries | Pass data or dependencies through parameters |

Some common sources of implicit dependencies in Java:

- Mutable static variables, stateful singletons, mutable fields of external objects.
- Clock.systemUTC().instant(), System.currentTimeMillis(), LocalDate.now() when no Clock is provided; values change depending on when they are called.
- Random using a stateful source of randomness; each number generation may yield a new result.
- System.getenv, System.getProperty, changing configuration, databases, or files on disk.
- ThreadLocal, transaction state, security state, or context bound to the executing thread.
- Mutable objects captured by a lambda, even if the local reference is declared final.

Note: **A parameter with a reference type can also carry mutable internal state**. Passing a List into a method makes the dependency more explicit, but if another caller modifies the List concurrently, behavior remains hard to predict. Purity also requires discipline in how input objects are used.

## 3. Pure functions, determinism, and expression substitutability

A **pure function** in practical Java terms has two properties:

1. Given the same stable inputs, the computation returns the same result.
2. The call causes no observable side effects outside its return value.

When an expression is pure, you can replace a call with its corresponding result without changing the observable behavior of the program. This is the idea of **referential transparency**.

~~~java
static int discount(int amount, int percent) {
    return amount * percent / 100;
}
~~~

When amount = 200 and percent = 10, the result is always 20 (ignoring overflow for excessively large inputs; the example is meant to illustrate small inputs). To change the discount rate, pass a new percent. The method does not need to read a hidden percent variable.

Compare:

~~~java
static int activeDiscountPercent = 10;

static int discountFromGlobal(int amount) {
    return amount * activeDiscountPercent / 100;
}
~~~

The call discountFromGlobal(200) hides an important input, activeDiscountPercent. Changing the global value between two calls causes different results.

**Getting the same result is not enough to prove a function is pure.** Two calls to System.out.println("hello") both return void, yet still print twice. Similarly, a function that reads the clock may happen to return the same millisecond in two closely spaced calls; it still depends on time.

In Java, saying “pure function” is a **commitment about behavior and related state**, not a standard modifier or annotation verified by the compiler. Common Java libraries allow both pure callbacks and callbacks with side effects.

## 4. Lambdas and capture: effectively final does not mean immutable

A local variable used by a lambda must be final or **effectively final**: once assigned, that variable must not be reassigned.

~~~java
int threshold = 50;
java.util.function.IntPredicate eligible = score -> score >= threshold;
~~~

The snippet above is valid. Reassigning threshold after creating the lambda will prevent the program from compiling.

However, this constraint only protects the **local reference variable**; it does not make the object referenced by that variable immutable:

~~~java
java.util.List<String> audit = new java.util.ArrayList<>();
java.util.function.Consumer<String> recorder = message -> audit.add(message);

recorder.accept("started");
~~~

audit is not reassigned, so it satisfies the capture requirement, yet recorder still mutates the List. This is a side effect on an object that can be observed outside the lambda.

Similarly, a lambda can read a mutable field:

~~~java
class Pricing {
    int surcharge = 5;

    java.util.function.IntUnaryOperator calculator =
        amount -> amount + surcharge;
}
~~~

The result of calculator.applyAsInt(100) can change if surcharge changes. **A lambda is syntax for passing behavior; it does not automatically guarantee pure or thread-safe behavior.**

An even riskier example is when a callback both reads and mutates a counter:

~~~java
int[] counter = {0};
java.util.function.IntSupplier next = () -> ++counter[0];
~~~

The counter variable remains effectively final, but the array element changes: two calls to next.getAsInt() return 1 and 2, respectively. Using an array or AtomicInteger to work around the effectively final restriction does not turn this logic into a pure function. AtomicInteger makes the specific increment/read operation atomic, but does not automatically guarantee that the entire algorithm is safe or deterministic.

## 5. Consequences in the Stream API: stateless and non-interference

The Stream API recommends that pipeline behavioral parameters, such as lambdas in filter, map, sorted, and reduce, be **non-interfering** with the source and in most cases **stateless**.

- **Non-interfering:** the callback does not modify the data source being traversed by the pipeline, except for specific exceptions permitted by the API documentation.
- **Stateless:** the result of the callback for an element does not depend on any state that may change during pipeline execution.

### 5.1. Avoid modifying the source while traversing

~~~java
java.util.List<Integer> values =
    new java.util.ArrayList<>(java.util.List.of(1, 2, 3));

// Incorrect example: do not run in the complete demonstration program.
values.stream()
    .filter(n -> {
        values.add(n + 10);  // Interferes with the source being traversed.
        return n % 2 != 0;
    })
    .toList();
~~~

This operation violates the non-interference requirement and can cause errors, unreliable behavior, or unexpected results depending on the source and execution strategy. You should not rely on it always throwing ConcurrentModificationException.

The right approach if you need a new result:

~~~java
java.util.List<Integer> extended = values.stream()
    .map(n -> n + 10)
    .toList();
~~~

map produces the resulting values without modifying values. If the business logic needs to update the original collection, perform the update in a separate, controlled step.

### 5.2. Avoid accumulating through shared state

~~~java
java.util.List<Integer> numbers = java.util.List.of(1, 2, 3, 4);
java.util.List<Integer> shared = new java.util.ArrayList<>();

// Not suitable for parallelStream:
numbers.parallelStream().forEach(shared::add);
~~~

ArrayList is not safe when multiple threads add elements concurrently; the element count or contents can be wrong, and the data structure can be corrupted. With a sequential stream, adding to an external list still has a side effect and reduces clarity.

If the goal is to produce a list:

~~~java
java.util.List<Integer> doubled = numbers.parallelStream()
    .map(n -> n * 2)
    .toList();
~~~

If the goal is a sum:

~~~java
int sum = numbers.parallelStream()
    .mapToInt(Integer::intValue)
    .sum();
~~~

In these examples, the result is produced by the Stream terminal operation without needing callbacks to mutate a shared variable.

### 5.3. Do not confuse forEach and peek with pure transformations

forEach is typically meant for side effects at the **final processing boundary**, such as printing computed results. In a parallel stream, forEach does not guarantee execution in encounter order. forEachOrdered is used when preserving order by contract is needed, but it still does not turn the callback into a pure function.

peek is mainly suited for observation during debugging; because Streams are lazy and can be optimized, do not place critical business logic such as writing audits, sending requests, or updating a database inside peek or filter/map and assume the callback is guaranteed to run exactly once on every element.

An example that can be misleading:

~~~java
long count = java.util.stream.Stream.of("A", "B")
    .peek(System.out::println)
    .count();
~~~

You must not build business logic assuming the two letters are guaranteed to be printed. When the source has a known size, count can compute the result without traversing each element or calling peek.

### 5.4. Side effects become even harder to control when running in parallel

A pipeline that depends on a shared counter or callback ordering will struggle to guarantee determinism when switching from stream() to parallelStream(). Even with synchronized or AtomicInteger, the result may still depend on execution order if the computation makes different decisions based on the counter increment position.

For parallel reduce, the combining operation must be **associative** with a matching identity value. For example, integer addition generally works well; subtraction is not associative, so it cannot be arbitrarily used as a parallel associative reduction. In floating-point arithmetic, differences in addition order can also change rounding results; “having no side effects” is not enough to guarantee bit-for-bit identical results across all execution orders.

## 6. Turning implicit dependencies into explicit inputs

Improving a function often starts by listing **what actually determines the result**.

Example with hidden clock and tax dependencies:

~~~java
static int currentTaxPercent = 10;

static String quoteBad(int basePrice) {
    int total = basePrice + basePrice * currentTaxPercent / 100;
    return java.time.Instant.now() + ": " + total;
}
~~~

The result depends on both currentTaxPercent and the current time, even though it only accepts basePrice. A version that makes all data explicit:

~~~java
static String quoteText(
    int basePrice,
    int taxPercent,
    java.time.Instant issuedAt
) {
    int total = basePrice + basePrice * taxPercent / 100;
    return issuedAt + ": " + total;
}
~~~

The same trio of stable arguments will produce the same string. The caller retrieves the time and tax rate from the system, then passes them into the function. This organization allows testing with a fixed Instant without needing to alter a global clock.

If a class genuinely needs to read the clock at runtime, **dependency injection** via Clock is a useful technique:

~~~java
class TimestampSource {
    private final java.time.Clock clock;

    TimestampSource(java.time.Clock clock) {
        this.clock = clock;
    }

    java.time.Instant now() {
        return clock.instant();
    }
}
~~~

In the real application you can provide Clock.systemUTC(); in tests, provide Clock.fixed(instant, zone). Note the distinction: **passing Clock makes the dependency explicit and easy to mock, but now() still depends on the state of the Clock** if the Clock runs in real time; it is not a pure function on its own. Passing a **captured Instant** into the computation is what makes that computation independent of changing time.

Similarly, instead of calling a Random source inside a pricing or code-generation function, you can pass the generated value into the pure processing part. When you need to simulate a random sequence for tests, passing a seeded RandomGenerator is one way to control the dependency, though each call to nextInt still mutates the generator's state.

## 7. Organizing “functional core, imperative shell”

A practical pattern in Java:

1. **Imperative shell (interaction layer):** reads requests, clocks, configuration, databases; writes logs, sends responses, updates data.
2. **Functional core (computation core):** receives explicit values, computes and returns new values; does not perform I/O or mutate shared state.

Example of quote calculation logic:

- The shell retrieves line items, quote timestamp, and discount rate from the request/configuration.
- The core computes the total and produces a well-typed result.
- The shell saves or prints the quote after the core finishes.

This allows unit tests to run fast and reproducibly, because the pricing logic does not need a database, real clock, or server. It also makes it easy for readers to see where side effects can occur. Side effects are not “forbidden”: real-world applications **must** read/write I/O. The goal is to place them in the right spots and coordinate them deliberately.

## 8. Complete Java 17+ program

The example below intentionally keeps the computation from modifying external data. Console printing and audit recording live in main; the issue timestamp is obtained from Clock and then passed into the message-building function.

Create the file **FunctionalEffectsDemo.java**:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;

public class FunctionalEffectsDemo {
    record Line(String item, int unitPrice, int quantity) {}
    record Quote(String code, int subtotal, int discount, int total) {}

    // Computes from explicit inputs without modifying the lines list.
    static Quote calculate(
        String code,
        List<Line> lines,
        int discountPercent
    ) {
        if (discountPercent < 0 || discountPercent > 100) {
            throw new IllegalArgumentException("Invalid discount");
        }

        int subtotal = lines.stream()
            .mapToInt(line ->
                Math.multiplyExact(line.unitPrice(), line.quantity())
            )
            .reduce(0, Math::addExact);
        int discount = Math.multiplyExact(
            subtotal, discountPercent
        ) / 100;
        return new Quote(
            code,
            subtotal,
            discount,
            Math.subtractExact(subtotal, discount)
        );
    }

    // String depends only on Quote and the passed-in instant.
    static String receipt(Quote quote, Instant issuedAt) {
        return quote.code() + "@" + issuedAt
            + " total=" + quote.total();
    }

    public static void main(String[] args) {
        List<Line> lines = List.of(
            new Line("Book", 100, 2),
            new Line("Pen", 20, 3)
        );
        Quote first = calculate("Q-001", lines, 10);
        Quote second = calculate("Q-001", lines, 10);

        System.out.println(first);
        System.out.println(first.equals(second));

        // At the application boundary, decide the instant.
        Clock fixed = Clock.fixed(
            Instant.parse("2026-01-02T03:04:05Z"),
            ZoneOffset.UTC
        );
        Instant issuedAt = fixed.instant();
        String message = receipt(first, issuedAt);
        System.out.println(message);

        // Writing audit is an intentional side effect.
        List<String> audit = new ArrayList<>();
        audit.add("created:" + first.code());
        System.out.println(audit);

        // Pipeline transforms data without touching audit/lines.
        List<String> items = lines.stream()
            .filter(line -> line.quantity() > 1)
            .map(Line::item)
            .toList();
        System.out.println(items);
    }
}
~~~

Using JDK 17 or later, run in the directory containing the file:

~~~bash
javac FunctionalEffectsDemo.java
java FunctionalEffectsDemo
~~~

Stdout:

~~~text
Quote[code=Q-001, subtotal=260, discount=26, total=234]
true
Q-001@2026-01-02T03:04:05Z total=234
[created:Q-001]
[Book, Pen]
~~~

Detailed analysis:

- calculate uses the input Lines and discountPercent = 10; subtotal = 100 × 2 + 20 × 3 = 260, discount = 26, total = 234. The method does not read global variables and does not mutate lines.
- first.equals(second) returns true because the Quote record implements equals based on its components. Two calls to calculate with the same immutable inputs produce equivalent results.
- Clock.fixed returns a fixed time. The shell retrieves this Instant, while receipt only formats already-known data. If you want to issue the quote at real time, the shell can use Clock.systemUTC() without changing receipt.
- audit.add(...) is a side effect, placed explicitly in main so readers know when it happens.
- filter/map/toList creates a new list of items without adding elements to audit or lines. Stream.toList() creates a List that cannot have elements added, removed, or replaced.

The example uses List.of containing records that only hold String and int, so the inputs here cannot be silently mutated by the caller. In real-world systems, if a record contains a List or mutable object, the record **does not automatically provide deep immutability**: you need defensive copying, clear ownership, or appropriate immutable types.

**On errors and data limits:** calculate validates discountPercent and uses Math.multiplyExact/addExact/subtractExact to detect int overflow; these operations can throw exceptions on invalid data. The demonstration program uses small valid numbers. Real monetary business logic typically requires BigDecimal or the smallest currency unit with explicit rounding rules; the example here focuses on managing side effects.

## 9. Effective testing when state and side effects are explicit

When a function does not implicitly depend on a clock, mutable singleton, database, or callback ordering, unit tests can pass exact inputs and compare results. Example for the program above:

~~~java
// Illustrates an assertion in a test method;
// not a standalone program.
var lines = java.util.List.of(
    new FunctionalEffectsDemo.Line("Notebook", 50, 2)
);
var result = FunctionalEffectsDemo.calculate("Q-T", lines, 10);
assert result.total() == 90;
~~~

Java's assert statement may be disabled by default; in real tests, prefer JUnit assertions or enable -ea. This example is a simple arithmetic check, requiring no database or clock mocks.

Testing I/O and side effects is different: verifying that a repository is called at the right time, an event is sent once, or an audit is recorded with the right data. Abstracting these interactions behind interfaces as dependencies enables using test doubles or fakes. Placing calculations in the core allows testing business rules independently without mocking every service.

For time-dependent behavior, replace direct LocalDate.now() calls by accepting an explicit Clock or Instant. For randomness, you can pass generated random values or provide a deterministic source for tests. For global state, narrow the scope of mutation and convert it to parameters or immutable data objects where possible.

## 10. Side effects can appear in subtle places

### 10.1. Mutating inputs

~~~java
static int[] sortInPlace(int[] data) {
    java.util.Arrays.sort(data);
    return data;
}
~~~

sortInPlace mutates the array passed in by the caller. Returning the same array does not make the method pure. If you need behavior with fewer side effects, create a copy before sorting:

~~~java
static int[] sortedCopy(int[] data) {
    int[] copy = data.clone();
    java.util.Arrays.sort(copy);
    return copy;
}
~~~

The sortedCopy method does not mutate the input array. However, the result is a new mutable array; the caller can still mutate the returned array afterward.

### 10.2. Caching or memoization

A function may write to an internal cache to improve speed. If the cache is completely hidden and does not alter observable results, users may sometimes still view that API as functionally pure. Even so, caching still adds state that must be managed, and can affect memory, concurrency, execution order, and errors. Do not equate “same result” with “no internal state at all.”

### 10.3. Exceptions and totality

A method that throws an exception does not necessarily mutate shared state, but it can interrupt control flow and force the caller to handle the error. In many effect models, throwing an exception is considered an observable effect; practical definitions of “pure” in application programming may distinguish computation errors from I/O or mutation.

For a predictable design, state input preconditions and errors clearly; you can represent expected errors as result values when appropriate. Do not silently catch all exceptions and return a default value, as that can hide business errors.

### 10.4. Mutating fields inside a record or shallowly unmodifiable collection

~~~java
record Bag(java.util.List<String> items) {}

java.util.List<String> mutable = new java.util.ArrayList<>();
Bag bag = new Bag(mutable);
mutable.add("A");
~~~

bag.items() now sees "A" even though the items reference inside the record is final. You can use List.copyOf in the constructor if you need to protect the list structure, though mutable elements inside still require further consideration.

## 11. When to use side effects and where to draw the boundary?

You do not need to turn every piece of Java into Streams or lambdas in pursuit of purity. In real applications, database writes, sending events, generating reports, and logging are all necessary. What matters is **deciding clearly where side effects will occur**:

- **Input/output handling layer:** read data, authenticate, call services, commit transactions, emit events, or print results.
- **Business rules layer:** receive already-collected data, apply conditions and compute results, minimizing reading/mutating external state.
- **Data contracts:** express inputs, outputs, failure possibilities, and mutability scope; avoid hiding important dependencies in static fields.
- **Concurrency:** keep transformation functions in streams as stateless as possible; place state-updating operations in dedicated mechanisms with explicit synchronization guarantees.
- **Testing:** use fixed inputs and compare outputs for the core; separately test side-effecting interactions through replaceable dependencies.

For example, after computing a Quote, calling repository.save(quote) has a side effect but is completely reasonable. If you place repository.save(...) directly inside a Stream's map() that transforms each line item, retries, parallel execution, or pipeline optimizations will make side effects hard to control. Compute the data first, then persist it according to the system's transaction, retry, and idempotency policies.

## 12. Common misconceptions and self-check questions

**Misconception 1: “If it doesn't write outside, the function is pure.”** A function that reads a tax rate from a mutable static field, the current time, or file contents still has implicit dependencies; the same arguments can yield different results.

**Misconception 2: “Using lambdas or Streams is pure functional programming.”** A lambda can easily capture a mutable ArrayList, mutate fields, or perform I/O. Streams do not enforce pure callbacks.

**Misconception 3: “An effectively final captured variable is thread-safe.”** final/effectively final guarantees that the local variable is not reassigned, not that the referenced object's state is immutable or synchronized.

**Misconception 4: “With AtomicInteger, a parallel stream is already optimal and safe.”** AtomicInteger supports specific atomic operations, but stateful callbacks can still produce non-deterministic, hard-to-read, and slow logic. Using an appropriate collector/reduction is usually better.

**Misconception 5: “Records and unmodifiable Lists are always deeply immutable.”** A record containing a mutable object and a structurally unmodifiable List containing mutable elements can still expose state mutated from outside.

**Misconception 6: “Side effects are always bad.”** Side effects are necessary for real-world interaction. The problem is implicit, uncontrolled side effects scattered throughout computations and hard to test.

Self-check:

1. A method only reads a mutable static variable without modifying anything: does it have a side effect or an external-state dependency?
2. Why can a List<String> captured in a lambda still have elements added to it even though the reference variable is final?
3. Why is mutating a shared ArrayList inside parallelStream().forEach(...) unsafe?
4. Does passing Clock.systemUTC() into an object make the now() method a pure function? How is passing a fixed Instant different?
5. How can you keep price calculation independent of fetching the time, logging, or saving to a database?

If you can distinguish between **explicit inputs, implicitly read state, and observable side effects**, you have a solid foundation for designing lambdas, Stream pipelines, and Java APIs that are easier to maintain, test, and run concurrently.