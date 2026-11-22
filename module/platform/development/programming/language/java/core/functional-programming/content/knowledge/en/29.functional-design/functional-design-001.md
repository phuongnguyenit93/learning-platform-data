# Building Pure Computations and Keeping Side Effects at the Boundary in Java

A functional design (*functional design*) does not necessarily have to eliminate all I/O, mutable variables, or exceptions. Applications still need to read files, call APIs, get the current time, query databases, and save results. The more important idea is to **separate the part that decides the result from the part that interacts with the outside world**: build an easily testable computation core, then place reading/writing at a few identifiable and controllable boundaries.

This organization is often called **functional core, imperative shell**: the core mainly processes inputs into outputs, while the shell orchestrates tasks that have side effects. In Java 17+, we can apply this principle using regular methods, `record`, `Stream`, `List`, and small interfaces without needing any specialized framework.

## 1. What Does “Pure” Mean?

A pure function (*pure function*) has two memorable characteristics:

1. **The result depends only on the input arguments**, not on hidden state such as the system clock, mutable global variables, the current database, or thread execution order.
2. **No observable side effects**: it does not write to files, print to the console, modify an external object, send requests, increment a global counter, or mutate the input data.

If you call the same function with **the same input data by value**, the result must have the same meaning; this is determinism (*determinism*) within the context of that computation.

Simple example:

```java
static long subtotalCents(int quantity, long unitPriceCents) {
    if (quantity <= 0 || unitPriceCents < 0) {
        throw new IllegalArgumentException("Invalid data");
    }
    return Math.multiplyExact((long) quantity, unitPriceCents);
}
```

This is a method placed inside a Java class. It does not read or modify external state; `Math.multiplyExact` reports an overflow error instead of returning an incorrect total. With the same `quantity` and `unitPriceCents`, it always returns the same result or the corresponding error type.

Conversely:

```java
static long calculatePrice(int quantity) {
    long price = GlobalPriceTable.currentPrice(); // Reads hidden state.
    System.out.println("Calculating price");      // Writes to console.
    return quantity * price;
}
```

This is **code illustrating a design with side effects**, not a standalone program; `GlobalPriceTable` is a hypothetical example and not a standard Java API. The same `quantity` can yield different results if the price table has changed. You should not write pure unit tests for this method while ignoring its environmental dependencies.

A pure function can still use **local mutable variables** internally, such as accumulating a sum in a `for` loop, as long as it does not expose that mutable state or affect objects owned by the outside. “Pure” does not mean **every statement must use Stream**.

## 2. Distinguishing Data, Decisions, and Actions

A business flow can be divided into three categories of work:

| Work Category | Examples | Appropriate Place |
| --- | --- | --- |
| **Reading data** | Reading files, querying databases, receiving HTTP requests, reading the clock | Boundary/adapter |
| **Decisions** | Parsing, validating, filtering, calculating prices, applying discount policies, rendering reports to `String` | Functional core |
| **Executing effects** | Writing files, saving transactions, sending emails, calling services, printing logs | Boundary/adapter |

Basic workflow:

```text
Outside world
    |
    v
[Read adapter]  -- received data ---->  [Parse + Validate]
                                             |
                                             v
                                        [Pure computation]
                                             |
                                             v
                                        [Create result/plan]
                                             |
                                             v
[Write adapter] <-- commands/output --  [Orchestration layer]
    |
    v
Outside world
```

In the diagram, **parse** is considered a pure computation when it only takes an already-available string and converts it into structured data, without opening files or calling APIs itself. **Render** can also be pure if it only produces a `String` from input values, rather than calling `println` itself.

A boundary does not have to be a single file/class. The goal is to make side effects **easy to find, easy to control, and easy to replace during testing**.

## 3. Example Design: Generating an Order Value Report

Problem: the input file consists of lines in the format `SKU,quantity,unitPriceCents`. The application needs to calculate the subtotal before discount, apply a 10% discount if the subtotal is **10,000 cents** or more, and output a report.

To keep the example deterministic and avoid floating-point drift:

- Unit prices use `long` as **cents**.
- Quantity uses `int` and must be positive.
- Unit price cannot be negative; SKU cannot be blank.
- Line amount is `quantity × unitPriceCents`.
- Discount equals `subtotal / 10` if the threshold is reached; integer division rounds down to the cent, defined as **this example's policy**, not a general rule for all monetary business logic.
- `Math.multiplyExact`, `Math.addExact`, and `Math.subtractExact` help detect overflow.
- The input format is intentionally simple; it does not yet handle full CSV with commas inside quoted fields.

Instead of designing a `calculateFromFile(path)` function that reads the file, computes, and writes the file all at once, we separate them:

```text
Files.readString(path)          -- impure I/O boundary
parse(rawText)                  -- pure
calculate(items)                -- pure
render(summary)                 -- pure
Files.writeString(path, report) -- impure I/O boundary
```

The computation core knows nothing about file paths, the console, databases, HTTP, or how the program is run.

## 4. Complete, Compilable Java 17+ Example

Save to file **`FunctionalCoreDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Objects;

public class FunctionalCoreDemo {
    record Item(String sku, int quantity, long unitPriceCents) {}

    record Summary(
            long subtotalCents,
            long discountCents,
            long payableCents
    ) {}

    // PURE: Only converts a line of text into data.
    static Item parseLine(String line) {
        String[] parts = line.split(",", -1);
        if (parts.length != 3) {
            throw new IllegalArgumentException("Invalid format: " + line);
        }
        return new Item(
                parts[0].trim(),
                Integer.parseInt(parts[1].trim()),
                Long.parseLong(parts[2].trim())
        );
    }

    // PURE: Does not open files, does not modify the input string.
    static List<Item> parse(String rawText) {
        Objects.requireNonNull(rawText, "rawText");
        return rawText.lines()
                .filter(line -> !line.isBlank())
                .map(FunctionalCoreDemo::parseLine)
                .toList();
    }

    // PURE: Validation and calculation depend only on items.
    static Summary calculate(List<Item> items) {
        Objects.requireNonNull(items, "items");

        long subtotal = 0L;
        for (Item item : items) {
            Objects.requireNonNull(item, "item");
            if (item.sku() == null || item.sku().isBlank()
                    || item.quantity() <= 0
                    || item.unitPriceCents() < 0L) {
                throw new IllegalArgumentException("Invalid item");
            }

            long amount = Math.multiplyExact(
                    (long) item.quantity(),
                    item.unitPriceCents()
            );
            subtotal = Math.addExact(subtotal, amount);
        }

        long discount = subtotal >= 10_000L
                ? subtotal / 10L : 0L;
        long payable = Math.subtractExact(subtotal, discount);
        return new Summary(subtotal, discount, payable);
    }

    // PURE: Returns String; does not println or write to file.
    static String render(Summary summary) {
        Objects.requireNonNull(summary, "summary");
        return "subtotalCents=" + summary.subtotalCents() + "\n"
                + "discountCents=" + summary.discountCents() + "\n"
                + "payableCents=" + summary.payableCents() + "\n";
    }

    // IMPURE BOUNDARY: Reads and writes files in the orchestration layer.
    static String runFiles(Path source, Path destination)
            throws IOException {
        String rawText = Files.readString(
                source, StandardCharsets.UTF_8
        );

        List<Item> items = parse(rawText);
        Summary summary = calculate(items);
        String report = render(summary);

        Files.writeString(
                destination, report, StandardCharsets.UTF_8
        );
        return report;
    }

    public static void main(String[] args) throws IOException {
        if (args.length == 0) {
            // Demo without files for deterministic stdout.
            String sample = "PEN,2,2500\nBOOK,1,6000\n";
            System.out.print(render(calculate(parse(sample))));
        } else if (args.length == 2) {
            // Reading/writing files and printing to console are all boundaries.
            System.out.print(
                    runFiles(Path.of(args[0]), Path.of(args[1]))
            );
        } else {
            throw new IllegalArgumentException(
                    "Usage: java FunctionalCoreDemo [input.txt output.txt]"
            );
        }
    }
}
```

Compile and run with **JDK 17 or later**:

```bash
javac -encoding UTF-8 FunctionalCoreDemo.java
java FunctionalCoreDemo
```

**Exact stdout of the no-argument mode:**

```text
subtotalCents=11000
discountCents=1100
payableCents=9900
```

Manual calculation: `PEN` is `2 × 2500 = 5000` cents; `BOOK` is `1 × 6000 = 6000` cents. The subtotal `11000` cents meets the 10% discount threshold, so the discount is `1100` and the payable amount is `9900`.

Running with two arguments:

```bash
java FunctionalCoreDemo orders.txt report.txt
```

The program reads UTF-8 content from `orders.txt`, parses it into `Item`s, calculates `Summary`, generates text, and writes `report.txt`. The source file must exist and follow the right format; paths, permissions, and I/O errors depend on the environment. `Files.writeString` with default options can create or overwrite the destination file's content; use it only when it matches application policy.

Note: the example parses a **comma-separated three-field format**, not a standard CSV parser with escaping or quoted fields. In real applications, if SKUs contain commas or multilingual data requires quoting, use a proven CSV parser or an appropriate input format. The choice of parser does not change how the pure core is separated from the boundary.

## 5. Why Is the `calculate()` Method a Good Computation Core?

In the program above, `calculate()`:

- Only receives data via the `List<Item>` argument.
- Does not call `Files`, `System.out`, `System.currentTimeMillis`, a logger, or the network.
- Does not modify the input list or the `Item` records.
- Uses a local `subtotal` variable for computation, without exposing that mutable variable outside.
- Returns a `Summary` record holding the computed values, easy to compare with `equals()`.
- Throws exceptions according to **deterministic rules** for invalid data or overflow.

Therefore, the logic that decides the payable amount can be tested with pure data without creating files, starting a server, or setting up a database.

Small test example inside a class in the same package or placed inside the demo class itself:

```java
Summary actual = calculate(List.of(
        new Item("PEN", 2, 2500L),
        new Item("BOOK", 1, 6000L)
));

Summary expected = new Summary(11000L, 1100L, 9900L);

if (!actual.equals(expected)) {
    throw new AssertionError("Wrong result: " + actual);
}
```

This is a **snippet** that needs to be in a scope where `Item`, `Summary`, `calculate()`, and `java.util.List` are visible; it is not a standalone program. `record` provides value-based comparison of its components, so `Summary.equals()` is suitable for comparison.

**Distinguishing a pure function from an “exception-free” function:** a computation may throw `IllegalArgumentException` or `ArithmeticException` depending on the data. If the error is determined entirely by the input, it still does not automatically become an I/O-style side effect. In large systems, expected errors can be represented by a result type such as a custom `Result<Success, Failure>`, instead of using exceptions for every case.

## 6. `parse()` and `render()` Can Also Be Pure

Many developers only separate the price calculation, while still letting the parser open files or the renderer print to the console. Observe the difference:

**Do not tie the parser to the environment:**

```java
static List<Item> parseFile(Path path) throws IOException {
    return parse(Files.readString(path));
}
```

This illustrative snippet depends on the environment: the same `path` could have different contents, the file might not exist, or it might be locked. It is a **read adapter**, not a pure parser.

**Pure parser:**

```java
static List<Item> parse(String rawText) {
    return rawText.lines()
            .filter(line -> !line.isBlank())
            .map(FunctionalCoreDemo::parseLine)
            .toList();
}
```

The shortened snippet above illustrates the idea; the full runnable version in Section 4 also checks for `null`. The parser depends only on the passed-in string.

Similarly, the `render(summary)` method **returns** a `String`. `System.out.print(render(summary))` performs the side effect **outside** the renderer. Thanks to this, the same rendering logic can be reused to return an HTTP response, write a file, or serve as data in tests.

A good practice is to make pure functions accept **values that already carry enough information**: the parser accepts `String`, the calculator accepts `List<Item>`, and the renderer accepts `Summary`. Do not require them to look up global dependencies to do their job.

## 7. Replace Hidden State with Explicit Arguments

Some side effects are harder to spot than `Files.writeString`:

| Hidden Dependency Source | Hard-to-Test Example | Move to Boundary |
| --- | --- | --- |
| Time | `LocalDate.now()` inside discount logic | Pass `LocalDate today` or `Clock` |
| Random numbers | `new Random().nextInt()` inside pricing | Generate decision outside, pass result/seed or abstraction |
| Runtime configuration | `System.getenv("DISCOUNT")` | Read config once at entrypoint, pass `Policy` |
| Database | `repository.findPrice(sku)` inside `map` | Fetch data beforehand, pass existing price table into core |
| Network | `httpClient.send(...)` during validation | Adapter calls HTTP, core validates response data |
| Default locale/time zone | Formatting without specifying locale | Pass chosen `Locale`/`ZoneId` or configuration |

Example of a date-dependent policy:

```java
static boolean isPromotionActive(
        LocalDate today,
        LocalDate from,
        LocalDate through
) {
    return !today.isBefore(from) && !today.isAfter(through);
}
```

This is a snippet inside a class, requiring `import java.time.LocalDate;`. The function does not call `LocalDate.now()`, so tests can pass any date. The entry point or adapter can read `LocalDate.now(clock)` and pass it in, while the date policy remains a pure computation.

`Clock` is a useful technique when a service needs the time in multiple places; **passing a concrete time value directly** into the computation function is often even simpler if the feature only needs a single fixed point in time.

## 8. A Pure Stream Is Not Guaranteed Just by Using `map()`

Stream operations are often well-suited for expressing data transformations:

```java
List<String> normalized = names.stream()
        .filter(name -> !name.isBlank())
        .map(name -> name.trim().toUpperCase(Locale.ROOT))
        .toList();
```

This is a snippet inside a method, requiring `java.util.List`, `java.util.Locale`; `names` is a `List<String>` containing no `null`s. It creates a result list without modifying `names`.

However, if the callback performs I/O, `Stream` itself does not make the side effect disappear:

```java
// NOT a pure functional core:
orders.stream()
        .map(order -> {
            auditLogger.log(order);     // Side effect.
            return pricingService.call(order); // May perform I/O.
        })
        .toList();
```

The names `auditLogger`, `pricingService`, and `orders` in the snippet are application dependencies, not built-in Java APIs. This code can be affected by execution order, network errors, timeouts, and retries.

Better, when possible:

1. Read external data in an adapter.
2. Convert data into value types that are easy to compute with.
3. Use pure `map`/`filter`/`reduce` or a pure `for` loop to make decisions.
4. Collect the results with `toList()`, `collect()`, or a return object.
5. Perform subsequent read/write actions at an intentional boundary.

**`peek()` is not the right place for mandatory I/O.** Some pipelines can optimize and skip intermediate callbacks if the terminal operation does not need them, such as `count()` on a sized source. With parallel streams, the `peek` invocation order is not necessarily encounter order either. Business logic should not depend on the invocation count or order of side effects in an intermediate operation.

## 9. Where Is Mutable State Acceptable?

Functional design **does not forbid** all mutable variables. You should distinguish:

**Local variables confined entirely within a function call**

```java
static long sumCents(List<Long> amounts) {
    long total = 0;
    for (long amount : amounts) {
        total = Math.addExact(total, amount);
    }
    return total;
}
```

This is a snippet inside a class with `java.util.List`. If it does not modify `amounts`, only uses the local `total`, and returns a `long`, the function can be pure. A `for` loop does not make it “less functional” semantically.

**Shared state / state passed in from outside**

```java
static long sumWithSideEffect(
        List<Long> amounts, long[] sharedTotal
) {
    for (long amount : amounts) {
        sharedTotal[0] += amount;
    }
    return sharedTotal[0];
}
```

This is an example with a side effect: the caller holds `sharedTotal` and observes it being mutated. Under concurrent execution, race conditions can also occur.

If multiple results are needed, return a `record` containing those values instead of mutating multiple output parameters. When you need to build a temporary collection inside a function, you can create a new one and return an **immutable copy** via `List.copyOf(...)` if the elements are also safe to share. Remember that `List.copyOf` only copies the list structure; it **does not deep-copy** mutable objects inside.

## 10. Fast Testing of the Pure Part Without I/O

Each function can be tested independently:

| Scenario | Input | Expected Result |
| --- | --- | --- |
| Subtotal below threshold | `Item("A",1,2500)` | `subtotal=2500,discount=0,payable=2500` |
| Subtotal at threshold | `Item("A",4,2500)` | `subtotal=10000,discount=1000,payable=9000` |
| Subtotal above threshold | `Item("A",2,6000)` | `subtotal=12000,discount=1200,payable=10800` |
| Empty list | `List.of()` | `Summary(0,0,0)` |
| Non-positive quantity | `Item("A",0,2500)` | `IllegalArgumentException` |
| Negative unit price | `Item("A",1,-1)` | `IllegalArgumentException` |
| Malformed line string | `"A,2"` | `IllegalArgumentException` |
| Sum exceeds `long` | Large enough data to overflow | `ArithmeticException` |

When tests need to check exceptions in JUnit 5, `assertThrows` can be used; however, the Java example in Section 4 needs no testing library outside the JDK.

A quick check in Java inside the class:

```java
Summary a = calculate(List.of(new Item("A", 4, 2500L)));
if (!a.equals(new Summary(10000L, 1000L, 9000L))) {
    throw new AssertionError(a);
}
```

This is a snippet, not a standalone runnable file. It does not need to create input/output files; it runs fast and produces stable results.

**Testing the boundary is different:** you need to test missing files, access permissions, UTF-8 characters, existing destination files, and mid-write failures. Those belong in tests at the I/O layer, not mixed into tests for the discount formula.

## 11. Designing Results for Side Effects: Command, Plan, or Event

In some business flows, the computation core does not just return a total; it also decides **what action needs to be taken**. Instead of sending an email or writing to the database itself, it can return a data description:

```java
record NotificationPlan(String recipientId, String message) {}

static NotificationPlan planReceipt(
        String customerId,
        long payableCents
) {
    return new NotificationPlan(
            customerId,
            "Paid: " + payableCents + " cents"
    );
}
```

This is an illustrative record and method declaration inside a class. `planReceipt` only creates a value; it **does not send** the notification.

The shell can receive `NotificationPlan`, verify sending policies, and then use an external adapter to communicate with the notification service. This approach brings benefits:

- Testing “whether to send a notification and what content to send” does not require connecting to a mail server.
- The plan can be logged and approved before execution.
- Transactions, outbox, or idempotency mechanisms can be applied in the adapter layer.
- Changing the notification provider does not force changes to the content-generation logic.

Even so, **a pure plan does not by itself guarantee the action happens exactly once**. Exactly-once delivery, retries, transactions, and commits are concerns of the I/O boundary and infrastructure, and must be designed separately.

## 12. An I/O Boundary Does Not Mean “Catch All Errors and Ignore Them”

In `runFiles`, `Files.readString` or `Files.writeString` can throw `IOException`. `parseLine` can throw `NumberFormatException` or `IllegalArgumentException`, while `calculate` can throw `ArithmeticException` due to overflow.

An orchestration layer can group errors:

| Error Group | Examples | Typical Policy Needed |
| --- | --- | --- |
| Invalid data | Missing column, negative quantity, invalid price | Return validation error, do not fabricate business results |
| Overflow | Total exceeds `long` | Report error clearly or change monetary type/arithmetic |
| Read error | File not found, permission denied | Choose conditional retry or return error |
| Write error | Disk full, network error, locked file | Warn about partial write state, do not assume transaction |
| External service error | Timeout, 5xx, invalid response payload | Bounded retry/idempotency and appropriate orchestration |

Do not replace this with `catch (Exception ignored) { return new Summary(0,0,0); }`: doing so turns a file read error or invalid data into a valid order totaling zero.

If safe file writing is required, you can write to a temporary file and then perform an **atomic rename when the file system supports it**. In a database, you need transactions. In a network environment, you need idempotency keys/outbox or retry policies. Those mechanisms live in the shell/adapter and do not alter the pricing formula in the core.

## 13. Common Design Mistakes

| Mistake | Harm | Fix |
| --- | --- | --- |
| Price calculation function reads price table from DB | Tests require a DB and results depend on hidden state | Pass queried price table data into the core |
| Reading `LocalDate.now()` inside promotion condition | Results change with real time | Pass caller-selected timestamp/clock |
| `map()` or `peek()` directly writes to files | Side effect sits inside a lazy pipeline, hard to predict execution | Collect results first, then write at the boundary |
| Mutating input collection inside `filter` | Violates non-interfering principle, can fail during iteration | Create a new result collection |
| Using `parallelStream().forEach(sharedList::add)` | Race conditions and no ordering guarantee | Use `toList()`/`collect()` |
| Returning an internal mutable `List` directly and continuing to mutate it | Caller observes result changing after return | Return an immutable copy when appropriate |
| Confusing a local `for` loop with external side effects | Misses simple, readable code | Distinguish local mutation from shared state |
| Using `double` for money without stating a rounding policy | Can cause decimal precision errors | Use cents or `BigDecimal` with clear scale/rounding |
| Collapsing all exceptions into a default value | Hides bad data and environment failures | Separate data errors, computation errors, and I/O errors |
| Treating `Files.writeString` as a transaction | File may be partially written on failure | Choose temp file/atomic move or transaction when needed |
| Every method takes repository/logger/client | Core is tightly coupled to infrastructure | Move read/write operations to adapters, core takes values |
| “Pure” but using mutable objects modified on another thread | Same input reference can have different contents | Take a snapshot/immutable value before computing |

## 14. Process for Applying This in Real Projects

When refactoring a piece of business code with many side effects into a functional design, you can follow these steps:

1. **List all sources of I/O/hidden state:** DB, HTTP, files, time, random, environment, logger, shared mutable fields.
2. **Identify the true inputs of the decision:** required data, policies, effective date, configuration parameters.
3. **Design value objects:** `record`, new collections, enums, or DTOs carrying self-contained values.
4. **Extract pure functions:** parse, normalize, validate, calculate, select, plan, render.
5. **Let the shell orchestrate:** read sources, pass data into the core, receive results, execute external actions.
6. **Test the core with values:** normal inputs, boundaries, data errors, overflow, empty states.
7. **Test adapters separately:** file permissions, HTTP timeouts, transactions, retries, encoding, payload formats.
8. **Measure the impact of changes:** easier testing, fewer dependencies, safer concurrency properties; but do not trade away performance or overcomplicate architecture for small problems.

Good design is usually **a few clear boundaries**, not dozens of pointless abstraction layers. When an action genuinely must happen in the middle of a decision chain, split the workflow into steps: **purely compute request → execute I/O → compute next decision from response**. This keeps side-effect sites clearly visible while remaining flexible.

## Knowledge Self-Check

**Question 1.** Is `String report = render(summary)` a side effect if `render` only concatenates strings?

**Answer:** No. It only creates a `String` value from `summary`. `System.out.print(report)` or `Files.writeString(..., report)` is the side effect.

**Question 2.** Does using a `long subtotal` variable and a `for` loop inside `calculate` make the function impure?

**Answer:** No, as long as that variable only exists within the function call, does not modify input data or external state, and the result depends solely on the inputs.

**Question 3.** To calculate a promotion based on the current date, should you call `LocalDate.now()` in the core or pass a date provided by the shell?

**Answer:** Pass a chosen date/clock so pure tests do not depend on the system clock.

**Question 4.** Is `parallelStream().map(x -> { shared.add(x); return x; }).toList()` safe because the terminal operation is `toList()`?

**Answer:** No. `shared.add` inside the mapper is a shared side effect that can cause race conditions; `toList()` does not protect external variables.

**Question 5.** If a file is half-written and then fails, does pure computation automatically roll it back?

**Answer:** No. Purity only separates decisions from effects. Rollback, atomic replacement, or transactions must be designed at the boundary.

**Question 6.** When an email must be sent after calculating a total, what kind of result can the core return?

**Answer:** A `NotificationPlan` or a value describing the message to send. The adapter will send the email and handle retries/idempotency.

## Key Takeaways

- **Functional core:** accepts explicit values, makes decisions, returns new values; avoids I/O and hidden state.
- **Imperative shell:** reads from/writes to the outside world, feeds data into the core, and applies results to the environment.
- `parse(String)`, `calculate(List<Item>)`, and `render(Summary)` can be pure; `Files.readString`, `Files.writeString`, network, clock, and console are boundary side effects.
- You do not need to abandon `for` loops or local variables to achieve purity; what matters is **producing no observable side effects**.
- **Turn time, configuration, randomness, and price tables into explicit input data** when they affect decisions.
- Test the core with immutable values, test I/O separately; build error handling, retries, and transactions at the proper boundary.
