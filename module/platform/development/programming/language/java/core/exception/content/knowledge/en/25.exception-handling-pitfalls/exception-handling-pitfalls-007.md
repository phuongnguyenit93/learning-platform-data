# Using Exceptions to Mask Simple Condition Checks — Common Pitfall in Java

## 1. Learning Objectives

After this lesson, you will be able to:

- Recognize the anti-pattern of **using exceptions to control normal execution flow** (*exception-driven control flow*), especially when only a simple condition check is needed.
- Distinguish **expected business states** from **contract violations/abnormal errors** that should throw an exception.
- Replace overly broad `try/catch` blocks with guard clauses, clear conditions, `Optional`, structured results, or direct operation APIs when appropriate.
- Know when **catching an exception is actually the right approach**, such as handling input for `Integer.parseInt()`, I/O failures, or public precondition violations.
- Understand **check-then-act** and *time-of-check to time-of-use (TOCTOU)* risks: checking beforehand does not eliminate race conditions or exceptions from the actual operation.
- Preserve error information when exception translation is needed, and avoid catching `NullPointerException` or `IndexOutOfBoundsException` just to hide programming bugs.
- Evaluate the impact on performance, readability, diagnostics, and API contracts in a balanced way.

This lesson uses Java 17+ and focuses on Java Core Exceptions; standalone compilable/runnable examples specify the file name, run command, and expected stdout.

## 2. What Is the Anti-Pattern?

A program may **deliberately perform an operation that it knows will often fail** and then rely on an exception to choose a normal branch, even though the decision condition is already available and there is a clear API to read it.

For example: getting the first element of a list, where an empty list is accepted as a valid business case.

Exception-based approach:

~~~java
String firstOrDefault(List<String> names) {
    try {
        return names.get(0);
    } catch (IndexOutOfBoundsException e) {
        return "Không có tên";
    }
}
~~~

This is **illustrative code inside a class with `java.util.List` imported**. If the list is empty, `get(0)` throws an exception; the code catches it and returns a default value.

In this case, an empty list is an **expected data state**, not a failure. The `List` API already provides `isEmpty()`, so the condition can be expressed directly:

~~~java
String firstOrDefault(List<String> names) {
    if (names.isEmpty()) {
        return "Không có tên";
    }
    return names.get(0);
}
~~~

This is also **illustrative code**, with the same input contract as the previous snippet. The second approach immediately shows the reader the intent: "If there are no elements, use the default value." There is no need to read the exception name and trace the error path to understand normal behavior.

**Important:** saying "do not use exceptions when a simple condition check suffices" does **not** mean **all** exceptions must be eliminated from the code. Exceptions remain very valuable for signaling contract violations, I/O failures, infrastructure errors, and issues that callers need to handle at the appropriate layer.

## 3. Distinguishing Three Types of Situations

A useful design question is: "Is this state a normal outcome that the caller is allowed to encounter?"

| Situation | Meaning | Typically Appropriate Form |
| --- | --- | --- |
| A list may be empty and this is normal | No value at the time of lookup | `isEmpty()`, `Optional`, or an empty result |
| A map may not contain a key | No mapping found | `get`, `containsKey`, `getOrDefault` according to null semantics |
| User input may have an invalid number format | Syntax error according to the chosen parser | Catch **the specific `NumberFormatException`** at the parse boundary and convert it into a validation result |
| A method requires a positive quantity by contract | Caller violated a precondition | Guard and throw a meaningful `IllegalArgumentException` |
| Opening a file may fail due to permissions, deletion, or device error | Resource operation can fail independently of a prior check | Call the actual API and handle `IOException` according to the contract |
| Array access with an invalid index due to an algorithm bug | Programming bug | Fix the algorithm; do not automatically catch and return a fake value |
| A remote API call times out | External failure where side effects may be unknown | Timeout/cancellation, retry, or error reporting per protocol, not just checking "is network available" beforehand |
| Business data is missing but allowed | A normal branch | A return type that expresses missing data, without using throw/catch for every case |

Classification depends on the **API contract**. "Not found" may be a normal state for a `find` method, but a workflow violation for a `requireExisting` method. Two methods can use different handling strategies and both be correct if their names, signatures, and documentation are consistent.

## 4. Why Should try/catch Not Be an if/else in Disguise?

A `catch` block expresses an exceptional handling path. Turning it into a normal branch for a simple condition can create several problems:

1. **Unclear intent.** Readers have to figure out which exception might be thrown just to understand the business branch.
2. **Easy to mask programming bugs.** `catch (NullPointerException)` can swallow an NPE caused by another logic bug inside the same `try` block.
3. **Hard to maintain.** When a new call is added to `try`, it may throw the same exception type for a different reason.
4. **Wrong layer of responsibility.** Infrastructure exceptions get turned into "no data," making the caller think the operation succeeded.
5. **Cost on hot paths.** Actually creating/throwing/catching exceptions repeatedly can introduce overhead from object allocation, stack traces, and control flow.
6. **Distorts observability.** Very high exception counts can pollute metrics and logs if frameworks collect them.
7. **Obscures state contracts.** Instead of returning `Optional.empty()` or `false`, the code implicitly states "a failed operation throws `IndexOutOfBoundsException`."
8. **Hard to triage real errors.** Catching broad `Exception` or `RuntimeException` can make errors that need investigation disappear.

However, there is **no** universal rule that "writing an `if` is always faster than `throw`" in every case. If errors are rare, an API designed to throw an exception can be simple and true to its contract. Performance optimization decisions should be based on workload and controlled measurement.

## 5. First Example: An Empty List Is a Valid Branch

### Less Preferred Approach

~~~java
String firstName(List<String> names) {
    try {
        return names.get(0);
    } catch (IndexOutOfBoundsException ignored) {
        return "Không có tên";
    }
}
~~~

This is **non-standalone illustrative code**. It both uses an exception as an emptiness check and gives the impression that all index errors inside `try` can be treated as "no name."

### Clearer Approach

~~~java
String firstName(List<String> names) {
    if (names.isEmpty()) {
        return "Không có tên";
    }
    return names.get(0);
}
~~~

If the API does not want to provide a default string that could be confused with real data, use a return type that expresses "absent":

~~~java
Optional<String> firstName(List<String> names) {
    return names.isEmpty()
            ? Optional.empty()
            : Optional.ofNullable(names.get(0));
}
~~~

This is **illustrative code** using `java.util.Optional`. `Optional.ofNullable` returns empty if the first element is null; that is appropriate only when the contract treats a null element as equivalent to "no name." If null has a different meaning, a more detailed result type is needed.

**Do not use `Optional` to hide every problem.** If the list is required to have an element, throwing an exception for a contract violation can be the right choice. In that case, check the condition and throw a meaningful error rather than relying on `get(0)` to produce a cryptic `IndexOutOfBoundsException`:

~~~java
String requireFirstName(List<String> names) {
    if (names.isEmpty()) {
        throw new IllegalArgumentException(
                "Danh sách tên không được rỗng");
    }
    return names.get(0);
}
~~~

The three APIs `firstName`, `findFirstName`, and `requireFirstName` can coexist if they genuinely express **three different contracts**. The most important thing is not to turn an expected branch into an error or swallow unexpected errors.

## 6. Standalone Java 17 Example: Guard, Optional, and Parse

Save the file **GuardInsteadOfExceptionDemo.java**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.OptionalInt;

public class GuardInsteadOfExceptionDemo {

    static String firstUsingException(List<String> values) {
        try {
            return values.get(0);
        } catch (IndexOutOfBoundsException e) {
            return "EMPTY";
        }
    }

    static String firstUsingGuard(List<String> values) {
        return values.isEmpty() ? "EMPTY" : values.get(0);
    }

    static Optional<String> findCode(Map<String, String> codes, String key) {
        return Optional.ofNullable(codes.get(key));
    }

    static OptionalInt parseUserNumber(String input) {
        try {
            return OptionalInt.of(Integer.parseInt(input));
        } catch (NumberFormatException e) {
            return OptionalInt.empty();
        }
    }

    public static void main(String[] args) {
        List<String> empty = List.of();
        List<String> names = List.of("An", "Bình");
        Map<String, String> codes = Map.of("A", "Alpha");

        System.out.println("Exception-based empty: "
                + firstUsingException(empty));
        System.out.println("Guard empty: " + firstUsingGuard(empty));
        System.out.println("Guard nonempty: " + firstUsingGuard(names));

        System.out.println("Known code: "
                + findCode(codes, "A").orElse("MISSING"));
        System.out.println("Unknown code: "
                + findCode(codes, "B").orElse("MISSING"));

        System.out.println("Parse 42: "
                + parseUserNumber("42").orElse(-1));
        System.out.println("Parse invalid: "
                + parseUserNumber("abc").orElse(-1));
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac -encoding UTF-8 GuardInsteadOfExceptionDemo.java
java GuardInsteadOfExceptionDemo
~~~

**Exact stdout:**

~~~text
Exception-based empty: EMPTY
Guard empty: EMPTY
Guard nonempty: An
Known code: Alpha
Unknown code: MISSING
Parse 42: 42
Parse invalid: -1
~~~

### Analysis

- Both functions that get the first element return the same result in the example, but `firstUsingGuard` expresses the empty branch using an existing condition.
- `Map.get("B")` returns null because the key does not exist in the map created here; `Optional.ofNullable` turns that into an explicit empty result.
- `parseUserNumber` **still uses `try/catch`** because `Integer.parseInt` documents `NumberFormatException` as its way of reporting invalid numeric syntax. Catching this specific exception at the parse boundary to return `OptionalInt.empty()` is a valid choice.
- Using `-1` is only for display in `main`; a system with valid negative values should not use a negative number as an error sentinel without a clear contract.

**Takeaway:** the mistake is not the existence of the `catch` keyword. The mistake is **using an exception to mask an obvious check or swallowing errors that the system needs to distinguish**.

## 7. NullPointerException Is Not a Reliable "No Value" Signal

Dangerous pattern:

~~~java
int lengthOrZero(Map<String, String> values, String key) {
    try {
        return values.get(key).length();
    } catch (NullPointerException e) {
        return 0;
    }
}
~~~

This is **illustrative code** with `Map` imported. When the key does not exist, `get(key)` returns null and `.length()` throws an NPE. However, the same NPE type could come from `values == null` or another line added to the `try` block. Catching NPE to return 0 can mask a design bug.

Replace it by checking the result itself:

~~~java
int lengthOrZero(Map<String, String> values, String key) {
    String value = values.get(key);
    return value == null ? 0 : value.length();
}
~~~

This handles it properly if the contract specifies that **both a missing key and a null value yield length 0**. However, if you need to distinguish those two states, you must consider the map's semantics.

### Distinguishing a Missing Key from a Present Key with a Null Value

Some `Map` implementations allow null values:

~~~java
Map<String, String> values = new HashMap<>();
values.put("present-null", null);
~~~

This is **illustrative code**; `Map` and `HashMap` must be imported. Both `values.get("missing")` and `values.get("present-null")` return null, but:

- `values.containsKey("missing")` is false.
- `values.containsKey("present-null")` is true.

Similarly, `getOrDefault(key, fallback)` only uses the fallback when **there is no mapping for the key**; if the key is mapped to null in a map that permits nulls, the result can still be null.

**Concurrency note:** on a map modified by other threads, calling `containsKey` followed by `get` is not an atomic operation. Do not use this check as a guarantee that the value still exists on the subsequent read.

## 8. Catching Exceptions Too Broadly Can Mask Programming Bugs

`catch (Exception)` can turn infrastructure errors and even bugs into a fallback that looks like success:

~~~java
String loadName(User user) {
    try {
        return user.profile().displayName();
    } catch (Exception e) {
        return "UNKNOWN"; // Anti-pattern: loses cause distinction.
    }
}
~~~

This is a fragment requiring a `User` class and its methods. If a missing profile is an expected state, the API should return a result expressing absence. If an NPE violates an invariant, the bug must be fixed rather than treated as "no name."

**The scope of `try` also matters:** catching an `IndexOutOfBoundsException` around `validateInput()`, `findIndex()`, and `items.get(index)` together can swallow the same exception type thrown by another method. Narrow the `try` block to the exact operation whose contract expects failure, or use a guard such as `isEmpty()` when emptiness is normal. For concurrently shared data, check-then-act also needs to address races under its own contract.

## 9. Intentional Guard Clauses Differ from Avoiding Exceptions

A **guard clause** checks preconditions or business branches at the start of a method:

~~~java
void register(int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException(
                "quantity must be positive");
    }
    saveQuantity(quantity);
}
~~~

This is **illustrative code** with an application-defined `saveQuantity`. Using `if` to **throw an exception** is right when `quantity <= 0` violates the method's contract. A guard does not always have to return a default value.

Distinguish:

- "If the list is empty, there is nothing to display" is an **expected data branch**; returning an empty list/`Optional` is appropriate.
- "Setting a negative quantity on an order" may be **invalid input**; throw `IllegalArgumentException` or return a validation result at the boundary.
- "In-memory data has a broken invariant" is a **programming/state error**; throw a meaningful error rather than pretending it succeeded.

Code becomes clearer when method names reflect their contracts: `findById` can return `Optional`, while `requireById` can throw a documented "not found" error.

## 10. Java 17: Designing Two Different Lookup Contracts

Save the file **LookupContractDemo.java**:

~~~java
import java.util.Map;
import java.util.Optional;

public class LookupContractDemo {

    record Item(String id, String name) {
    }

    static Optional<Item> find(
            Map<String, Item> items, String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException(
                    "id must not be blank");
        }
        return Optional.ofNullable(items.get(id));
    }

    static Item require(
            Map<String, Item> items, String id) {
        return find(items, id).orElseThrow(() ->
                new IllegalStateException("Item not found: " + id));
    }

    public static void main(String[] args) {
        Map<String, Item> items =
                Map.of("A", new Item("A", "Notebook"));

        System.out.println("Find A: "
                + find(items, "A").map(Item::name).orElse("MISSING"));
        System.out.println("Find B: "
                + find(items, "B").map(Item::name).orElse("MISSING"));

        try {
            require(items, "B");
        } catch (IllegalStateException e) {
            System.out.println("Require B: " + e.getMessage());
        }

        try {
            find(items, "");
        } catch (IllegalArgumentException e) {
            System.out.println("Blank ID: "
                    + e.getClass().getSimpleName());
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 LookupContractDemo.java
java LookupContractDemo
~~~

**Exact stdout:**

~~~text
Find A: Notebook
Find B: MISSING
Require B: Item not found: B
Blank ID: IllegalArgumentException
~~~

### Design Explanation

- `find` returns `Optional.empty()` for a **valid but nonexistent** ID. This is the expected branch of a lookup API.
- A null/empty/blank ID is treated as a **precondition violation**; the guard explicitly throws `IllegalArgumentException`.
- `require` expresses a different contract: the caller requires the item to exist. If it does not, the method throws an appropriate error rather than silently returning null.
- Callers do not need to catch `NullPointerException` to infer "no item."
- In a larger system, `require`'s exception could be a dedicated domain class such as `ItemNotFoundException`; the example uses a JDK exception to avoid extra auxiliary classes.

An HTTP API can map `ItemNotFoundException` to 404 if the contract and access permissions allow. Do not assume every `IllegalStateException` in every layer is a "not found" error.

## 11. Parsing Data: Why Catching NumberFormatException Can Be Reasonable

`Integer.parseInt(String)` does not provide an `OptionalInt` result directly: it returns a valid `int` or throws `NumberFormatException` if the syntax or range is not accepted.

At the input boundary, you can deliberately convert that mechanism into a validation result:

~~~java
OptionalInt parseOptionalInt(String input) {
    try {
        return OptionalInt.of(Integer.parseInt(input));
    } catch (NumberFormatException e) {
        return OptionalInt.empty();
    }
}
~~~

This is **illustrative code** with `java.util.OptionalInt` imported. Catching a specific exception here is not like calling `list.get(0)` on an empty list just to catch `IndexOutOfBoundsException`: the parser API does not provide a simple equivalent check that guarantees matching all parsing rules.

**Be careful with homemade prechecks:**

~~~java
if (input.matches("[0-9]+")) {
    return Integer.parseInt(input);
}
~~~

This is **incomplete illustrative code**; it does not check integer overflow, may reject plus/minus signs that the parser accepts, and may enforce rules different from the parser. A regex check does not guarantee `parseInt` will not throw `NumberFormatException`. If you want to support a narrower business format, that should be an **intentional validation rule**, not a guess meant to completely replace the parser.

### Should Exceptions Be Avoided If the Invalid Input Rate Is Very High?

It can be worth considering on hot paths, but do not rush to rewrite a number-parsing algorithm just to avoid exceptions. Safer options:

- Define the data contract first: which number formats and ranges are actually valid?
- Use a parser with a non-throwing status/result API if the chosen library supports it and fits.
- Measure throughput, allocation, and latency with a realistic invalid-input rate.
- If writing a custom parser, thoroughly test signs, `int` bounds, Unicode, unexpected characters, and edge cases.
- Do not swallow errors at another layer just because the input string might be invalid.

**There is no rule that "every parse error should return `Optional.empty()`."** If the caller needs to know why the number is invalid (overflow, invalid characters, required field), a `ValidationResult` type containing a specific error code may be more appropriate.

## 12. When Not to Precheck: Check-Then-Act and TOCTOU

This is an important exception to the advice "check conditions beforehand, avoid using exceptions."

Suppose an application does:

~~~java
if (Files.exists(path)) {
    return Files.readString(path);
}
return "";
~~~

This is **illustrative code** with `java.nio.file.Files` imported, a `path` variable of type `Path`, and a method with an appropriate checked-exception contract. Checking existence **does not guarantee** the subsequent `readString` call will succeed:

- The file may be deleted or renamed between the two operations.
- Access permissions may change.
- The existence check may be inconclusive due to I/O restrictions.
- Reading the file may fail due to disk, encoding, or resource errors.
- The file context may change between checking and using it.

Therefore, for I/O, a more accurate approach is usually to **attempt the actual operation and handle the appropriate exception**:

~~~java
try {
    return Files.readString(path);
} catch (NoSuchFileException e) {
    return "";
}
~~~

This is **illustrative code** inside a method that declares/handles remaining `IOException`s, with `Files`, `NoSuchFileException`, and `Path` imported. It only converts **file-not-found errors** into an empty result if that is the application's contract; other I/O errors continue to be reported to avoid hiding failures.

If the application needs to distinguish a missing file from an existing empty file, **do not use an empty string for both states**. You can return `Optional<String>` or a structured result type where the absence case is clearly defined.

**Principle:** a precheck does not guarantee the condition still holds at the time of use. When the operation itself can fail due to external factors, **exceptions are an essential part of the contract**, not an anti-pattern.

## 13. Concurrency: Check-Then-Act Can Create Races

Suppose a `ConcurrentHashMap` stores tasks. One thread does:

~~~java
if (tasks.containsKey("job-1")) {
    Task task = tasks.get("job-1");
    task.run();
}
~~~

This is **illustrative code**, assuming `tasks` is a concurrent map and `Task` is a business type. Even though `containsKey` and `get` are each individually thread-safe, the **check-then-get** sequence is not atomic: another thread can remove the key in between. Then `task` can be null and `task.run()` throws an NPE.

A reasonable approach if you only need the value at a single point in time:

~~~java
Task task = tasks.get("job-1");
if (task != null) {
    task.run();
}
~~~

This is **illustrative code**. It avoids the window between `containsKey` and `get`, though it does not guarantee the task is not canceled or modified elsewhere while running; separate lifecycle requirements still need coordination mechanisms.

If the condition and update **must be atomic on the same key**, consider `ConcurrentHashMap`'s atomic operations such as `computeIfAbsent`, `compute`, `putIfAbsent`, or `remove(key, value)` according to their respective contracts. Do not place blocking or slow callbacks inside an atomic operation if doing so increases contention or risks reentrancy; read each method's contract carefully.

### Databases Also Have TOCTOU

Code like "check if the email already exists; if not, insert" cannot prevent two requests from both passing the check and inserting duplicates. If uniqueness is required, the database must enforce it with a **unique constraint**/transaction or appropriate synchronization mechanism; the application handles conflict errors according to its contract.

There is no way to turn a condition **changeable by another actor** into an invariant simply by adding an `if` before the operation.

## 14. Standalone Java 17 Example: Demonstrating the Race Between containsKey and get

This program uses two threads and `CountDownLatch` to schedule intentionally: the reader thread checks that the key exists, then the writer thread removes the key **before** the reader thread calls `get`. Because ordering synchronization is established, stdout does not depend on scheduler speed.

Save the file **CheckThenActRaceDemo.java**:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;

public class CheckThenActRaceDemo {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, String> tasks =
                new ConcurrentHashMap<>();
        tasks.put("job-1", "READY");

        CountDownLatch checked = new CountDownLatch(1);
        CountDownLatch removed = new CountDownLatch(1);

        Thread reader = new Thread(() -> {
            boolean existed = tasks.containsKey("job-1");
            checked.countDown();

            try {
                removed.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            String after = tasks.get("job-1");
            System.out.println("Precheck: " + existed);
            System.out.println("Read after removal: " + after);
        }, "reader");

        Thread writer = new Thread(() -> {
            try {
                checked.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            } finally {
                // Even if an error occurs while waiting, release the latch so the reader does not hang.
                tasks.remove("job-1");
                removed.countDown();
            }
        }, "writer");

        reader.start();
        writer.start();

        reader.join();
        writer.join();

        System.out.println("Final containsKey: "
                + tasks.containsKey("job-1"));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 CheckThenActRaceDemo.java
java CheckThenActRaceDemo
~~~

**Stdout when there are no unintended interrupts:**

~~~text
Precheck: true
Read after removal: null
Final containsKey: false
~~~

### Why Does the Output Demonstrate the Race?

- The map initially contains `"job-1" -&gt; "READY"`.
- The reader calls `containsKey` before signaling `checked.countDown()`, so `existed` is true.
- The writer only performs the removal after `checked.await()` completes, then signals `removed.countDown()`.
- The reader only calls `get` after `removed.await()` completes. Because the key was removed, `get` returns null.
- The output demonstrates that **a precheck can become stale**, not that `ConcurrentHashMap` is not thread-safe.
- `join()` ensures both threads have finished before `main` prints the final state.

In the example, the catch branch handles interrupts by restoring the flag and terminating the thread. This is not the core of the lesson, but it avoids swallowing cancellation requests. Do not use this demo to infer that prechecking is always dangerous; for a list **not modified concurrently**, `isEmpty()` before `get(0)` is normal design.

## 15. Which APIs Help Express State Without Exceptions?

There is no single tool for every situation. Choose based on what the result means.

| Need | Potentially Suitable API/Form | Notes |
| --- | --- | --- |
| Empty list | `isEmpty()` | If the list is modified concurrently, understand the synchronization mechanism |
| Get first element of a finite stream | `stream().findFirst()` | Not necessarily better than `isEmpty()+get(0)` for every `List` |
| Map without a mapping | `get()`, `containsKey()`, `getOrDefault()` | Clarify null semantics and concurrent modification |
| Find an optional record | `Optional&lt;T&gt;` | Can express absence; do not use if multiple failure reasons are needed |
| Check an empty collection | `Collection.isEmpty()` | Do not wait until an iterator throws an error |
| Null/blank string | `value == null`, `String.isBlank()` | Call `isBlank` only after knowing it is non-null |
| Convert data with a throwing parser | Catch the specific parse exception at the boundary | Avoid reimplementing an incomplete parser |
| Validate required parameters | Guard, `Objects.requireNonNull()` | May intentionally throw an exception for contract violations |
| Access files/resources | Attempt the operation and handle I/O errors appropriately | Prechecks do not eliminate races |
| Result with both error code and data | Application-defined record/Result type | Avoid multiple indistinguishable sentinels |
| Async tasks | `CompletableFuture` with success/failure completion | Failed futures must be observed, not automatically turned into null |

### Optional Is a Contract, Not a Cure-All

For example, a `find` method returning `Optional.empty()` when data does not exist makes sense. However, returning empty when the database is offline **hides the critical difference** between "not found" and "unable to check."

If the caller needs to know multiple outcomes—not found, unauthorized, timeout, infrastructure failure—use an informative result type or throw meaningful exceptions per the API. Do not collapse everything into empty just so the code does not need a `catch`.

## 16. "Look Before You Leap" and "Easier to Ask Forgiveness"

Two styles are commonly known by their English names:

- **LBYL — Look Before You Leap:** check the condition, then perform the operation.
- **EAFP — Easier to Ask Forgiveness than Permission:** attempt the operation, then handle failure.

In Java, you should not apply one slogan to every API.

**LBYL is usually reasonable** when the condition is a normal data branch, there is no relevant race, and the check has direct meaning: `list.isEmpty()`, `input == null`, `quantity <= 0`.

**EAFP can be reasonable** when the operation's API is the source of truth, race risks make prechecks unreliable, or the API only provides exceptions for actual failures: `Files.readString()`, network I/O, standard parsers, or database constraints.

**What matters is the contract**, not syntactic preference. Do not use exceptions as a routine branching tool when a clear condition exists; at the same time, do not use prechecks as a "magic charm" to pretend resource operations cannot fail.

## 17. Exceptions and Performance: Optimize in the Right Place

**Actually throwing an exception** can be costly: allocating a `Throwable`, potentially capturing a stack trace, transferring control to `catch`, and logging if the application chooses to log. If this happens on a normal execution path thousands or millions of times, the overhead can be significant.

However:

- The cost depends on the JVM, exception type, stack depth, frequency, JIT, and logger.
- Simply having a `try` block without throwing an error **does not mean** paying the stack-trace cost on every run.
- A JVM may optimize specific patterns; do not assume every exception path always has the same overhead.
- Benchmarks can be skewed by logging to the console in a loop, skipping warm-up, or not using a realistic load.
- A guard check can increase state reads/locking or suffer from TOCTOU, so it is not automatically faster or more correct than every operation that uses exceptions.
- For **rare** exceptions, diagnostic capability can matter more than tiny timing differences.

If you suspect exception-driven control flow is causing a performance issue:

1. Use a profiler/metrics to confirm exceptions are actually being thrown frequently.
2. Determine whether the case is an expected business state or a system error.
3. Replace the API with appropriate semantics: condition check, `Optional`, structured result, or atomic operation.
4. Re-measure throughput, allocation rate, and p95/p99 latency with the same workload.
5. Check whether errors/observability were masked after the change.
6. If a microbenchmark is needed, you can use JMH in a separately configured project; JMH is not included in Java SE alone.

**Do not change an API just because a synthetic benchmark shows an `if` statement is faster than `throw`.** Contract quality, concurrency correctness, and diagnostic capability remain the decisive criteria.

## 18. "Not Throwing an Exception" Does Not Mean Proper Error Handling

A wrong change is removing `catch` logic or returning a fallback for every situation:

~~~java
String fetchProfile() {
    try {
        return remoteService.fetchProfile();
    } catch (RuntimeException ignored) {
        return "UNKNOWN";
    }
}
~~~

This is **non-standalone illustrative code**. Even with `try/catch`, the main issue is not just performance. It causes the caller to receive `UNKNOWN` and think the system succeeded when the backend may actually be failing.

An intentional fix:

- If a missing profile is a valid business outcome, return an empty value or `Optional` when **absence is genuinely confirmed**.
- If infrastructure does not respond, produce a distinct observable error state or throw an API-layer exception that preserves the cause.
- If caching is desired, establish a clear fallback policy; consider whether stale data is safe in the business context.
- If the operation has side effects, do not blindly advise retrying when it is unclear whether the previous request succeeded.

**A good API tells the caller three different stories:** data is present, data is absent by contract, or the result could not be determined due to an error.

## 19. Common Mistakes When Refactoring Away from Exception-Driven Control Flow

### 19.1. Turning Real Errors into Normal Branches

Changing `catch (IOException) { return null; }` to `if (!Files.exists(path)) return null;` does not eliminate `readString` failures. Permission errors, device errors, and races still need to be handled.

### 19.2. Checking for Null After Dereferencing

~~~java
String name = user.getName();
if (user == null) {
    return "UNKNOWN";
}
~~~

This is **intentionally wrong illustrative code**: if `user == null`, an NPE occurs before the check. The guard must be placed **before** any operation requiring a non-null object.

### 19.3. Returning a Sentinel That Conflicts with Real Values

Using `-1` or an empty string for errors can cause confusion with valid values. If the value domain can contain those values, use `Optional`, a record, or a result type with an explicit status.

### 19.4. Using Optional.empty for Every Kind of Error

Turning a database error, timeout, or permission error into "not found" can lead to wrong business decisions. `Optional` should express **absence**, not automatically represent every failure.

### 19.5. Catching NullPointerException and Continuing

A `catch (NullPointerException)` block can hide programming bugs. If null is valid, check it directly or design an appropriate data type. If null is invalid, fix the invariant or report a meaningful error.

### 19.6. Catching IndexOutOfBoundsException for Loops

~~~java
int i = 0;
try {
    while (true) {
        consume(items.get(i++));
    }
} catch (IndexOutOfBoundsException ignored) {
    // treated as end of list
}
~~~

This is **intentionally discouraged illustrative code**, with `items` and `consume` available. When a loop knows the size, use `for (int i=0; i<items.size(); i++)` or a for-each loop as needed. Using an exception to signal termination hurts readability and can swallow index errors from other operations inside the `try` block.

### 19.7. Prechecking a Map and Trusting the Result Forever

On concurrent data structures, `containsKey` and `get` are two separate operations. If atomicity is needed, choose an appropriate thread-safe operation/contract.

### 19.8. Writing a Custom Regex Parser Not Equivalent to the Standard API

A simple regex may not check overflow, negative signs, or character ranges; code after the regex can still throw `NumberFormatException`. Respect the parser's contract and only add checks for specific business constraints.

### 19.9. Refactoring in a Way That Loses the Cause

If translating an I/O error into an API-layer exception, use a constructor that accepts `Throwable cause` instead of only copying the message. Do not turn "do not use exceptions for normal branches" into "do not preserve exceptions on real error paths."

### 19.10. Adding Scattered Guards Without a Contract

Some methods return null, some return empty, and some throw `IllegalArgumentException` for the same condition. Standardize API naming, documentation, and return types so callers do not have to guess.

### 19.11. Catching Exception Too Broadly

`catch (Exception)` can swallow `InterruptedException` in a waiting method; the cancellation signal is lost if code continues without a corresponding policy. Always review checked exceptions and cancellation contracts when changing a catch block.

### 19.12. Judging by Performance Before Checking Correctness

A guard might avoid an exception while introducing a race; or it may be slightly cheaper while masking errors. Contract correctness is a prerequisite before optimizing.

## 20. Code Review Checklist

When you see a `try/catch` block on a frequent execution path, ask:

1. Is the condition causing the exception an **expected business case** or a **contract violation/abnormal error**?
2. Is there a direct, clear, and sufficiently safe check API such as `isEmpty()`?
3. If using a guard, can the condition change between the check and the operation?
4. Is an atomic operation, transaction, or failure handling on the operation itself needed instead of a precheck?
5. Is the `try` block narrow enough that `catch` does not swallow errors from other statements?
6. Is the caught exception type specific, or is it catching `Exception`/`RuntimeException` too broadly?
7. Can the missing-data case be expressed with `Optional` or a clear result type?
8. Could null, sentinel values, and empty be confused with valid data?
9. Should syntax-invalid input reported by a standard parser be converted into a validation error at the boundary?
10. When a genuine technical error occurs, does the code preserve the cause and provide sufficient diagnostic information?
11. Is an operation with side effects being blindly retried inside `catch`?
12. If code was changed for performance, was the right workload measured and correctness verified after refactoring?

## 21. Practice Exercises

### Exercise 1: Replace an Exception-Driven Loop

Rewrite the list-iteration snippet using a `for-each` loop or a valid index-based loop. Show that an empty list is handled normally without throwing an error.

~~~java
int i = 0;
try {
    for (;;) {
        System.out.println(items.get(i++));
    }
} catch (IndexOutOfBoundsException e) {
    // End of elements.
}
~~~

This is **illustrative code intentionally needing improvement**, with `items` already in context.

### Exercise 2: Distinguish "Not Found" from "System Error"

Design an API to retrieve a document: a nonexistent document is allowed to return empty, while a data-read error must not be turned into empty. Write tests demonstrating both branches.

### Exercise 3: Check-Then-Act on a Map

Explain why `containsKey` followed by `get` does not guarantee the value still exists when a map has multiple writers. If the requirement is "register a task if not already present," look up `putIfAbsent` and how to avoid creating two duplicate tasks.

### Exercise 4: Parser and Validation Result

Design a function that reads an age from a string. It must distinguish missing input, invalid format, out of range 0–150, and valid. Consider whether an `OptionalInt` is enough to represent all requirements; if not, use a record or sealed result type containing a status code.

## 22. Summary

- **Do not use exceptions as an `if/else` in disguise** when a simple condition accurately describes a normal data branch.
- An empty list, a missing map key, or an optional lookup usually has clearer ways to be expressed: `isEmpty()`, `get`, `Optional`, or a result type.
- **Exceptions still have their place:** contract violations, standard parser errors, I/O failures, infrastructure errors, and situations that cannot be guaranteed by a precheck.
- **Beware of TOCTOU:** with files, concurrent maps, and databases, checking beforehand does not guarantee the state remains valid at the time of use.
- Catch exceptions at **the narrowest scope and the right type**, preserve the cause when translating errors, and do not use fallbacks to mask real errors.
- Optimize performance only after understanding the contract and measuring the impact on a realistic workload.

**Conclusion:** Replacing exception-driven control flow with simple conditions makes code intent clearer and can reduce overhead when errors are thrown frequently. However, conditions cannot replace exception handling for every operation; the right choice must be based on **the nature of the state, the API contract, and the atomicity of the operation**.