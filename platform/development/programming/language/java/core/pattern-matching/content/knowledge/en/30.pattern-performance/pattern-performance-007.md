# Avoiding Accessors with Side Effects or High Cost When Using Record Patterns in Java 21

## 1. Why Are Accessors a Performance Concern?

Record patterns let you check the type and extract the components of a record in a single expression:

```java
record Payment(String code, long amount) {}

if (value instanceof Payment(var code, var amount)) {
    System.out.println(code + ": " + amount);
}
```

Looking at the syntax, it is easy to assume `Payment(var code, var amount)` is a completely free field-unpacking operation. In reality, in Java 21, **a record pattern reads components by invoking the record's corresponding accessors**. A typical record has compiler-generated accessors that simply return the field. However, Java allows a record author to **explicitly declare an accessor**, and that method can perform arbitrary work: updating a counter, writing logs, allocating collections, recomputing metrics, throwing exceptions, or even calling external services.

Therefore, there are two independent risks:

- **Side effects:** "reading" a component mutates state or an external system. Results may vary across matches and become hard to debug.
- **Excessive cost:** the accessor computes values, copies data, or performs heavy I/O. A short `switch` can hide a lot of expensive work.

A resilient design **keeps accessors pure, fast, stable, and consistent with the component state**. Heavy computation, data fetching, or normalization should have explicit steps and error policies—typically in a constructor/factory or application service—before pattern matching on a snapshot.

This lesson falls under **Performance**, but it also relates to correctness, record semantics, and how a domain model is structured. No single measurement allows concluding that every record pattern is always slow; what matters is **avoiding unexpected work during matching**.

**Java Version:** Record classes have been standard since Java 16 (JEP 395); record patterns (JEP 440) and pattern matching for `switch` (JEP 441) have been stable since **Java 21**. The complete example in Section 8 runs on JDK 21+ without `--enable-preview`.

## 2. Record Patterns Perform Deconstruction via Accessors

A simple record:

```java
record Location(String city) {}
record Shipment(String code, Location location) {}
```

If you use:

```java
case Shipment(var code, Location(var city))
        when city != null && !city.isBlank() ->
    "Đi " + code + " đến " + city;
```

the runtime needs to:

1. Determine that the selector value can match a non-null `Shipment`.
2. Extract the `code` and `location` components via their corresponding accessors to match the record pattern.
3. Determine that `location` matches a non-null `Location` record.
4. Extract `city` via the `Location.city()` accessor.
5. Only **after the pattern structure matches**, evaluate the guard `city != null && !city.isBlank()`.
6. If the guard is true, select the case body.

This is a semantic description; you should not infer from it a fixed number of invocations for every accessor across all compilation strategies, case layouts, or JDKs. In business code, design so that the result does not depend on how many times a component is read.

According to **Java Language Specification 21, `14.30.2**, a record pattern obtains each component by invoking its accessor. The specification also explicitly states: if an accessor invoked during deconstruction throws an exception, matching completes abruptly with **`MatchException`**, with the original exception as its `cause`.

### Comparing Type Patterns and Record Patterns

```java
if (value instanceof Shipment shipment) {
    // Type pattern: binds the whole object, does not deconstruct components yet.
}

if (value instanceof Shipment(var code, var location)) {
    // Record pattern: needs to extract components via accessors.
}
```

If you only need to determine that an object is of type `Shipment` and pass it to a handler, a **type pattern** is usually sufficient. If the logic needs `code` or `location`, a record pattern helps extract them clearly.

Of course, a type pattern does not automatically eliminate all costs: if the handler immediately calls an expensive accessor afterward, the cost still occurs. Decide based on **the data actually needed**, rather than assuming that changing syntax will automatically solve performance.

## 3. Explicit Accessors Can Mutate State

An anti-pattern example:

```java
record TrackedPrice(long cents) {
    private static int reads;

    public long cents() {
        reads++;                  // Side effect.
        return cents;             // Return the stored component.
    }
}
```

Every time `cents()` is called, the static variable `reads` changes. When `TrackedPrice(var cents)` appears in a record pattern, deconstruction can alter this counter.

**Why is this a bad idea for a domain model?**

- Reading a value is no longer a side-effect-free operation.
- The counter does not measure "number of payments processed"; it only measures how many times the accessor was called—a pattern may be tested even when the guard ultimately evaluates to false.
- In concurrent code, incrementing an unsynchronized static variable can cause data races and lost counts.
- Debugging with extra logs or breakpoints can expose a different execution path than expected.
- Code can repeat deconstruction or change `case` structure without changing domain meaning at all, yet the observed counter differs.

If you need business metrics, count after a **decision or action** has been finalized, rather than counting every time an accessor is read.

### Accessors That Break Value Object Semantics

An even more dangerous case:

```java
record UnstableScore(int score) {
    private static int sequence;

    public int score() {
        return score + sequence++;
    }
}
```

Each read can return a different number. Even though the record stores a final `score` component, external callers observe unstable state. This violates the intuition of a value object and can make a guard like `when score >= threshold` produce hard-to-reproduce results.

This snippet illustrates a design flaw, **not an implementation to use**. It cannot be fixed by "ensuring the compiler only calls the getter once"; the fix is to make the accessor return the actual component value and move any stateful operations to a place with its own contract.

### Side Effects in Accessors Are Not Necessarily Syntax Bugs

Java allows declaring explicit accessor methods as long as they obey signature and access-level rules. The compiler does not forbid side effects or I/O inside an accessor body. Therefore, this is an issue that must be addressed through **code review, design, and testing**, rather than expecting everything to be caught by compilation errors.

## 4. Expensive Accessors: Copying Collections, Computation, and I/O

### 4.1. Copying a List on Every Read

```java
record SlowCatalog(java.util.List<String> codes) {
    public java.util.List<String> codes() {
        return java.util.List.copyOf(codes);
    }
}
```

Here, `codes()` is an explicitly declared component accessor. It runs `List.copyOf` every time it is called. Depending on the implementation and input, `List.copyOf` may copy or reuse an already unmodifiable list; **you cannot assert that every call allocates a new object**. Even so, putting a collection operation into an accessor makes its cost depend on state and list representation, making it less predictable than an accessor that directly returns a field.

If the domain requirement is to **keep a structurally unmodifiable snapshot**, it is better to copy when creating the record:

```java
record SafeCatalog(java.util.List<String> codes) {
    SafeCatalog {
        codes = java.util.List.copyOf(
            java.util.Objects.requireNonNull(codes, "codes"));
    }
}
```

In `SafeCatalog`, the default `codes()` accessor simply returns the stored list; there is no need to copy it again on read. `List.copyOf` rejects null elements, creates an unmodifiable collection, and prevents the caller from affecting the record by adding or removing elements in the source list.

**Limitation:** `List.copyOf` protects the list structure; it does not turn mutable element objects into immutable ones. For `String`, elements are already immutable. For a `List<MutableItem>`, achieving a deep snapshot requires designing the element type or copying accordingly.

### 4.2. Recomputing Every Time

```java
record Matrix(java.util.List<java.util.List<Integer>> rows) {
    public java.util.List<java.util.List<Integer>> rows() {
        // Avoid performing a very large deep copy on every component read
        // if a defensive snapshot at creation time is what the domain needs.
        return rows.stream()
            .map(java.util.List::copyOf)
            .toList();
    }
}
```

This code can do significant work whenever the accessor is called. If the record pattern `Matrix(var rows)` appears in multiple branches, the logic hides the cost at the call site. Alternatives depend on the domain: create a deep snapshot in a factory/constructor, use immutable data structures, or keep creating copies in a separately named method when the caller genuinely needs one.

Distinguish between a **record component accessor** and a **derived method**:

```java
record Measurements(java.util.List<Integer> numbers) {
    long total() {
        return numbers.stream()
            .mapToLong(Integer::longValue)
            .sum();
    }
}
```

`total()` is an additional business method, **not a component accessor**, because the record only declares `numbers`. The record pattern `Measurements(var nums)` does not automatically call `total()`. However, if a guard is written as `when m.total() > limit`, that computation still happens every time the guard is evaluated. That is a separate cost concern to watch out for.

### 4.3. Accessors Calling the Network or Database

Putting queries inside an accessor creates a dangerous responsibility boundary: a branching expression that looks pure can time out, need retries, open transactions, or throw infrastructure exceptions.

Instead of an `Order` record whose accessor queries the database for `riskScore`, **separate it into an enrichment step**:

```text
Raw request
    |
    v
Service/factory: fetch riskScore, handle timeout/errors
    |
    v
EvaluatedOrder(id, riskScore)  <- immutable snapshot
    |
    v
switch / record pattern       <- classification only
    |
    v
Decision                      <- business outcome
```

Not all data needs to be precomputed: if a score is extremely expensive and only some paths use it, you can defer computation **at the service layer with a clear contract**. The key point is not to hide that activity inside a value object's accessor that pattern matching may invoke.

## 5. Accessor Call Counts Are Not a Business Contract

Consider:

```java
return switch (value) {
    case Payment(var code, var amount) when amount >= 1_000L ->
        "Giá trị cao";
    case Payment(var code, var amount) ->
        "Giá trị thường";
    default -> "Không phải Payment";
};
```

When `Payment.amount` is less than 1,000, the first case can match structurally while its guard is false; the second case is then selected. Deconstruction operations are tied to evaluating patterns. You should not assume that:

- Both cases always share **a single** accessor read.
- Every case always forces reading each component **exactly once** in all configurations.
- Counting getter calls is a way to count which cases were selected.
- Short source code always means few runtime operations.

The compiler/JVM may optimize specific paths; reliable design does not depend on exact call-count details. If you need to measure a specific implementation, use a profiler/microbenchmark in the target environment rather than asserting a fixed read count across all JDKs.

### Side Effects in Guards Make the Problem Worse

```java
// Anti-pattern if isEligible queries a service or mutates state:
case Payment p when remoteService.isEligible(p) ->
    approve(p);
```

This is an **illustrative snippet inside a switch where the service and handler are declared**, not standalone code. A guard can be evaluated and return false; the case is not selected, yet the I/O has already occurred. If the guard throws an exception, it is not treated as false to move on to the next case.

Prefer:
- Short, null-safe, pure guards using already available data.
- Evaluating expensive policies once in a clearly named step.
- A snapshot record storing the finalized result, if keeping that value is the right contract.
- If a score needs real-time updates, defining freshness/consistency explicitly rather than caching implicitly.

## 6. Exceptions Caused by Accessors: `MatchException`

This is a Java 21 semantic rule that is especially important for debugging.

```java
record Fragile(int value) {
    public int value() {
        throw new IllegalStateException("unavailable");
    }
}
```

When Java evaluates:

```java
Object input = new Fragile(5);

try {
    if (input instanceof Fragile(var n)) {
        System.out.println(n);
    }
} catch (MatchException ex) {
    System.out.println(ex.getCause().getClass().getSimpleName());
}
```

The call to the `Fragile.value()` accessor during deconstruction throws `IllegalStateException`. According to **JLS Java 21 `14.30.2**, pattern matching completes abruptly with a `MatchException` whose cause is `IllegalStateException`. The snippet above prints the cause name `IllegalStateException`.

**Do not confuse the following outcomes:**

| Situation | Behavior |
| --- | --- |
| Selector does not have a matching type | Pattern does not match; subsequent cases may be tested |
| Nested record component is null | Nested record pattern does not match; guard does not run |
| Pattern matches but `when` returns false | Next case is evaluated |
| Accessor used in deconstruction throws an exception | Matching throws `MatchException`; it is not treated as pattern false |
| Guard or body throws an exception | Exception occurs in the guard/body, not from the accessor-deconstruction wrapping rule |

Therefore, trying to "use a fallback case to catch query failures" is not how to handle an accessor that throws during matching. Place queries at the service/boundary layer, handle exceptions where the error policy is understood, and then pattern match on the prepared data.

In addition, if you call `fragile.value()` directly **outside** pattern matching, that is a normal Java method call; do not assume all such exceptions become `MatchException`.

## 7. When to Use a Type Pattern Instead of a Nested Record Pattern?

Suppose the domain has:

```java
record Point(int x, int y) {}
record Route(String id, Point start, Point end) {}
```

If the goal is simply to pass a `Route` to a handler:

```java
case Route route -> handleRoute(route);
```

then a type pattern is enough—there is no need to read coordinates in the case label. Avoid writing:

```java
case Route(var id, Point(var x1, var y1),
           Point(var x2, var y2)) ->
    handleRouteById(id);
```

if the handler actually only needs `id`. The second pattern adds constraints that `start` and `end` must match non-null `Point` instances; when they are null, the case does not match. It can change behavior **rather than just increasing cost**.

Another option, if only the ID is needed:

```java
case Route route -> handleRouteById(route.id());
```

With a simple implicit accessor, reading the single needed component is clear. However, if the `id()` accessor is custom and expensive, you still need to fix the data source design. Switching to a type pattern is not an automatic optimization.

**Rule:** only deconstruct the levels and components truly needed to decide the branch. If a nested record pattern is capturing too much data, re-evaluate null semantics and business boundaries before refactoring.

## 8. Complete Java 21 Program: Detecting Accessor Calls and Using a Snapshot

The following program illustrates two classification approaches:

- `Tracked` has a `score()` accessor that intentionally increments a counter. This is an **anti-pattern for demonstration purposes**, not for real domains.
- `Snapshot` stores data with default accessors.
- `classifyTracked` deconstructs `Tracked` directly.
- `prepare` reads `Tracked.score()` **once explicitly in source code**, creating a snapshot.
- `classifySnapshot` runs multiple times on the snapshot without calling `Tracked`'s accessor again.
- `Broken` demonstrates an exception in an accessor causing pattern matching to throw `MatchException`.

Create the file **`AccessorPatternCostDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class AccessorPatternCostDemo {

    private static final AtomicInteger READS = new AtomicInteger();

    record Tracked(String id, int score) {
        public int score() {
            READS.incrementAndGet();
            return score;
        }
    }

    record Snapshot(String id, int score) {}

    enum Branch { HIGH, NORMAL, OTHER, NULL_INPUT }

    record Decision(Branch branch, String detail) {}

    static Decision classifyTracked(Object input) {
        return switch (input) {
            case null ->
                new Decision(Branch.NULL_INPUT, "null");

            case Tracked(var id, var score) when score >= 10 ->
                new Decision(Branch.HIGH, id);

            case Tracked(var id, var score) ->
                new Decision(Branch.NORMAL, id);

            default ->
                new Decision(Branch.OTHER, "unsupported");
        };
    }

    // Data-reading cost is placed in a clearly named step.
    static Snapshot prepare(Tracked tracked) {
        return new Snapshot(tracked.id(), tracked.score());
    }

    static Decision classifySnapshot(Object input) {
        return switch (input) {
            case null ->
                new Decision(Branch.NULL_INPUT, "null");

            case Snapshot(var id, var score) when score >= 10 ->
                new Decision(Branch.HIGH, id);

            case Snapshot(var id, var score) ->
                new Decision(Branch.NORMAL, id);

            default ->
                new Decision(Branch.OTHER, "unsupported");
        };
    }

    record Broken(int value) {
        public int value() {
            throw new IllegalStateException("read failed");
        }
    }

    static int deconstructBroken(Object input) {
        if (input instanceof Broken(var n)) {
            return n;
        }
        return -1;
    }

    public static void main(String[] args) {
        Tracked tracked = new Tracked("R-1", 4);

        Decision direct = classifyTracked(tracked);
        System.out.println("direct=" + direct.branch());
        System.out.println(
            "accessorObserved=" + (READS.get() > 0));

        int before = READS.get();
        Snapshot snapshot = prepare(tracked);
        int after = READS.get();

        System.out.println("prepareReads=" + (after - before));

        Decision first = classifySnapshot(snapshot);
        Decision second = classifySnapshot(snapshot);
        System.out.println("snapshot1=" + first.branch());
        System.out.println("snapshot2=" + second.branch());
        System.out.println(
            "additionalTrackedReads=" + (READS.get() - after));

        System.out.println(
            "high=" +
            classifySnapshot(new Snapshot("R-2", 15)).branch());
        System.out.println(
            "other=" + classifySnapshot("not a snapshot").branch());
        System.out.println(
            "null=" + classifySnapshot(null).branch());

        try {
            System.out.println(
                "broken=" + deconstructBroken(new Broken(9)));
        } catch (MatchException ex) {
            System.out.println(
                "cause=" +
                ex.getCause().getClass().getSimpleName());
        }
    }
}
```

Compile and run with JDK 21 or newer:

```bash
javac --release 21 -encoding UTF-8 AccessorPatternCostDemo.java
java AccessorPatternCostDemo
```

**Expected output:**

```text
direct=NORMAL
accessorObserved=true
prepareReads=1
snapshot1=NORMAL
snapshot2=NORMAL
additionalTrackedReads=0
high=HIGH
other=OTHER
null=NULL_INPUT
cause=IllegalStateException
```

### Output Analysis

**`direct=NORMAL`:** `Tracked` has `score == 4`, which does not satisfy the `score >= 10` guard of the first case, so the remaining branch receives it. The method directly uses a record pattern, so it can invoke an accessor with side effects.

**`accessorObserved=true`:** the program only confirms that the accessor was called at least once; it **does not try to pin down a specific count** for the case chain or across all JDKs. This is sufficient proof that deconstruction accesses the accessor.

**`prepareReads=1`:** `prepare` explicitly calls `tracked.score()` exactly once between the two counter reads. This is a property of that code, not the number of deconstruction calls generated by the compiler.

**`snapshot1=NORMAL`, `snapshot2=NORMAL`:** the same immutable snapshot containing score 4 is classified twice. Both reads use `Snapshot`'s normal accessors without accessing `Tracked.score()` again.

**`additionalTrackedReads=0`:** the source accessor counter does not increase during the two snapshot classifications. That **does not** prove classification has zero cost; it only proves there is no need to repeat a read belonging to the original source.

**`high=HIGH`, `other=OTHER`, `null=NULL_INPUT`:** branches handling high scores, other input types, and a null selector. `case null` is an explicit policy, not relying on `default` to handle null.

**`cause=IllegalStateException`:** `Broken`'s accessor throws an exception during deconstruction; `MatchException` is caught and its cause type is printed, without falling through to fallback cases.

This is a **behavioral demo**, not an absolute-speed benchmark result. The counter intentionally creates a side effect to illustrate the issue; production code should eliminate that kind of accessor.

## 9. Designing Boundaries for Expensive or Unstable Data

A clearer way to structure an application is typically:

```text
Input / request
      |
      v
Fetch / calculate / normalize
      |  (errors, timeouts, retries in service)
      v
Validated snapshot record
      |  (pure accessors, consistent state)
      v
Pattern matching / switch
      |
      v
Decision with branch ID
      |
      v
Log / metrics / persistence / response
```

**Separation of responsibilities:**

- **Service:** calls API/DB, computes risk score, manages timeouts/circuit breakers.
- **Factory/constructor:** validation, normalization, defensive copying, rejecting invalid data.
- **Snapshot record:** holds resolved data, simple accessors.
- **Switch:** selects cases, evaluates pure conditions, returns results.
- **Observability layer:** records case IDs and success status, without relying on getter call counts.

Some systems require near real-time data. In those cases, caches/snapshots must have a **creation timestamp, version, or staleness policy** appropriate for the domain. A prepared snapshot may be cheap to classify repeatedly, but you must not assume it is always up to date.

### Example: Service Evaluating Before Matching

```java
record EvaluatedOrder(String id, int score, boolean approved) {}

// Sketch in application service, assuming helpers exist:
// int score = riskService.calculate(rawOrder);
// boolean approved = policyService.approve(rawOrder, score);
// EvaluatedOrder evaluated = new EvaluatedOrder(id, score, approved);

// Case labels in switch receiving EvaluatedOrder or Object:
case EvaluatedOrder(var id, var score, var approved)
        when approved && score >= 10 ->
    accept(id);
case EvaluatedOrder(var id, var score, var approved) ->
    reject(id);
```

This is an **illustrative snippet**, not a standalone runnable program. The guard only reads two already-available values. Do not write `case EvaluatedOrder(var id, var score, true)` assuming the literal `true` is a valid Java 21 component pattern: that syntax is invalid. Use `var approved` and `when approved` as shown above.

Score and policy evaluation are separate steps, so expensive operations are not hidden inside accessors or guards.

## 10. Is Reading Once Always Better?

Not always.

If a value is rarely used, **eager precomputation** can be wasteful. If data can change, a stale copy can be wrong. If the domain requires every operation to decide based on a consistent snapshot, recomputing in separate places can also be wrong.

Instead of "caching everything," consider:

1. **Usage frequency:** is the component on the hot path or only in a rarely executed branch?
2. **Actual cost:** is the accessor an implicit field return, CPU computation, collection copy, or I/O?
3. **Stability:** does the data change over time or across threads?
4. **Consistency:** at what point in time must the decision take its snapshot?
5. **Storage/copy cost:** is the snapshot too large?
6. **Lifetime:** will the data be reused across multiple classifications?
7. **Error policy:** if loading/calculation fails, how should the caller be notified?

A simple accessor call is sometimes cheaper than allocating an intermediate object. An aggregation over a large collection may need precomputation, whereas a simple primitive property is rarely worth optimizing separately. **Measure and verify before claiming better or worse performance.**

## 11. Benchmarks and Profilers

Proper performance evaluation does not measure console printing inside an accessor, because I/O and the console environment easily drown out any record pattern cost.

A sensible benchmark plan:

- Use **JMH** for Java microbenchmarks, with separate warmup and measurement phases.
- Test enough inputs to cover guard true/false, nested pattern match/fail, and other cases.
- Consume results so the compiler cannot eliminate unobserved work.
- Measure allocation/GC and CPU, not just wall-clock time.
- If an accessor performs I/O, measure at the integration/application level and track latency/timeouts—do not mistake it for a pure CPU microbenchmark.
- Keep JDK, hardware, heap, data, and load consistent when comparing.
- Inspect a profiler to see where time is actually spent: custom getters, list copies, services, guards, or post-case processing.

**Do not state numbers like "record patterns are X% slower than old switch"** without measured data on the same workload. This lesson highlights design risks and verification methods.

## 12. Code Review Checklist

| Question | Risk Signal | Solution |
| --- | --- | --- |
| Does the record have custom accessors? | Accessor performs I/O, mutates state, copies objects | Keep accessors pure or move work to an explicit step |
| Is the record pattern extracting too many components? | Long nested patterns, unused variables | Only deconstruct the data needed |
| Are there multiple cases of the same type with guards? | Deconstruction may happen while evaluating multiple cases | Do not depend on call counts; measure when needed |
| Does the guard have side effects? | Calls services, increments counters, records metrics | Pre-evaluate policies; keep guards pure |
| Can an accessor throw an exception? | Matching stops abruptly | Understand `MatchException` and design error boundaries |
| Can a component be null? | Nested pattern fails or guard throws NPE | Define null contracts, check at the right place |
| Does the record hold mutable collections? | Caller mutates data between reads | Copy at creation, use immutable elements and clear ownership |
| Is a computation repeated? | Same score computed in multiple branches | Use a local variable or snapshot per consistency needs |
| Is there improper caching? | Stale data or high memory usage | Define lifecycle, TTL/version, and invalidation |
| Are guard-false cases tested? | Another case is selected, yet the accessor may still have run | Test case IDs, outputs, and exceptions |
| Was it actually measured? | Conclusions based on code length | Use a profiler/JMH with a suitable workload |
| Do metrics count getter calls? | Business counters have wrong semantics | Record metrics after the decision/action |

## 13. Common Mistakes

**Mistake 1 — assuming record accessors are always default getters.** Java allows overriding them. Read the record declaration before assuming deconstruction is cheap.

**Mistake 2 — treating an accessor exception as a non-matching pattern.** In record matching, an exception from an accessor is wrapped in `MatchException` with a cause; it does not fall through to fallback cases.

**Mistake 3 — using getter call counts as business metrics.** A false guard can still involve component calls; count selected cases via explicit outcomes/policies.

**Mistake 4 — logging inside getters, altering performance.** Logging involves I/O and side effects, plus the risk of leaking sensitive data. Use a profiler, debug breakpoints, or log at the decision layer.

**Mistake 5 — copying a list on every read when the domain needs an immutable snapshot.** Usually you should copy/validate at record creation, then use the simple implicit accessor.

**Mistake 6 — replacing a record pattern with a type pattern while still calling an expensive getter.** Different syntax does not fix the root cause. Redesign the computation/accessor source.

**Mistake 7 — calling APIs inside `when`.** Guards are evaluated before a case is selected; this can cause latency/exceptions in hard-to-predict places.

**Mistake 8 — thinking a final reference means deep immutability.** Mutable components can still change; a consistent snapshot requires proper ownership/copying and element types.

**Mistake 9 — optimizing by precomputing every field.** For rarely used or rapidly changing data, this can be wasteful or wrong; analyze frequency, cost, and consistency.

## 14. Practice Exercises

**Exercise 1.** For `Tracked` in the program, why is `accessorObserved` printed as a Boolean instead of a fixed count? Answer: the demo does not rely on the number of deconstructions across cases to infer behavior for all JDKs.

**Exercise 2.** Write `record Bad(int value)` whose `value()` accessor throws `IllegalArgumentException`. Match it with `instanceof Bad(var value)` in Java 21. What exception type is thrown by the matching process? Answer: `MatchException` with `IllegalArgumentException` as its cause.

**Exercise 3.** When you only need to distinguish `Shipment` from other types, use a type pattern instead of `Shipment(var code, Location(var city))`. Compare the `location == null` case between the two patterns.

**Exercise 4.** With `SafeCatalog(List<String>)`, add an element to the source list after creation; check whether the snapshot changes. Why is `List.copyOf` not enough if elements have setters?

**Exercise 5.** Refactor a guard that calls `remotePolicyService.check(request)` into a separate service step, producing `EvaluatedOrder` and a pure guard `when approved`. Specify where timeouts are caught.

**Exercise 6.** Write tests for `Tracked(score=9)`, `Tracked(score=10)`, and a null selector. Test the selected branch, not just comparing how many times the getter was called.

**Exercise 7.** Design a method to measure allocations when an accessor creates a list copy from large data. Include warmup/JMH and test multiple list sizes. Explain why printing to the console inside the accessor makes results unreliable.

**Exercise 8.** If a snapshot stores `riskScore` but data must be refreshed after 30 seconds, which layer should hold the timestamp/TTL/invalidation? Why should you not embed a hidden remote refresh mechanism inside a record accessor?

## 15. Summary

**Record patterns can invoke custom component accessors, so not every deconstruction is cheap and side-effect-free.** In Java 21, an accessor throwing an exception during pattern matching produces a `MatchException` with the original cause. An accessor that mutates state or performs expensive work can make guards, `switch`, and debugging unpredictable.

Good design keeps getters pure, fast, and stable; protects data in constructors or creates snapshots via services; deconstructs only the needed components; keeps `when` pure and null-safe; handles exceptions at boundaries; and measures with profilers/JMH rather than guessing. When optimizing, always verify **correctness and data consistency policies** before performance.

### Official References

- [JLS Java 21 — `14.30.2 Pattern Matching](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.2) — record patterns invoking accessors and `MatchException` rules.
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).
- [Oracle Java 21 — Record Classes](https://docs.oracle.com/en/java/javase/21/language/records.html).
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440).
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [OpenJDK JMH](https://github.com/openjdk/jmh) — Java benchmarking.
