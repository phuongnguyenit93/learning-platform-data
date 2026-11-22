# Behavioral compatibility: preserving contracts and observable outcomes

In a Java migration, replacing a library, framework, JDK version, or implementation approach is usually not hard when it comes to making new code run. The bigger challenge is ensuring existing components using the system still receive the behavior they relied upon. A method that keeps the same name and return type yet changes element order, `null` handling, exception types, or rounding rules can still break the calling application.

**Behavioral compatibility** is the ability of a new version or implementation to continue satisfying the behavioral contract observed and relied upon by consumers. A consumer can be a Java class calling a method, another module, a process over REST, a data-reading job, or an external system. When internal changes occur while consumers still receive the promised results and effects as before, that change preserves behavioral compatibility.

The focus of this compatibility category is the contract at the boundary between producer and consumer: which inputs are accepted, what outputs mean, how state changes, how errors are represented, and in what order external effects appear. The goal is not preserving every single line of code, but preserving what consumers have the right to rely on.

## 1. Behavior observed from the consumer side

An implementation can change substantially without altering external behavior. For example, loops can be replaced with the Stream API, internal data structures changed, one class split into multiple services, or queries migrated from JDBC to another persistence library. If consumers still receive the same contracted results, this is generally a behaviorally compatible change.

Conversely, small code changes can produce major differences at usage boundaries:

- An API that previously returned an empty list when no data existed now returns `null`.
- A method that previously preserved input order now returns results in non-deterministic order due to using `HashSet`.
- A financial calculation changes rounding rules, differing only on values near boundaries.
- An operation that previously threw `AccountNotFoundException` now returns a default object, leading consumers to think the account exists.
- A function that previously did not mutate the input collection now sorts that collection in place.
- An endpoint that previously returned HTTP status `404` for a non-existent resource now returns `200` with an empty body.

In every case, the new code compiles and runs normally. The problem surfaces only when consumers rely on that behavioral difference to decide their next step.

### 1.1. A contract is what consumers can depend on

A behavioral contract describes the relationship between inputs, state, and results. A contract can be analyzed in terms of the following parts:

| Component | Question to answer | Example |
|---|---|---|
| Preconditions | Which inputs are valid? | `customerId` must not be `null`; amount must be non-negative |
| Postconditions | On success, what do the results mean? | Only open orders belonging to the customer are returned |
| Invariants | What must always remain true before and after the operation? | Balance must not go negative if the account does not support overdraft |
| State | Which data is created, modified, or deleted? | Order transitions from `PENDING` to `CONFIRMED` |
| Side effects | How are external systems affected? | Emitting an event after the transaction commits |
| Errors | How are failure cases represented? | Throwing `OrderNotFoundException` when an order is not found |
| Ordering and stability | Do results or effects have deterministic ordering? | List sorted in ascending creation-time order |
| Idempotency | Does repeating the same operation create extra effects? | Resending a request with the same idempotency key does not create a second transaction |

Not every detail needs to be promised. A good contract clearly distinguishes what consumers are allowed to rely on from implementation details free to change. For instance, a contract can guarantee results sorted by `createdAt`, without guaranteeing that the system uses `ArrayList`, `LinkedList`, or a specific SQL statement.

### 1.2. Observable outcomes are broader than return values

When evaluating behavioral compatibility, comparing return values alone is insufficient. Consumers can observe many other aspects:

- **Values and data structures:** content, data types, formats, precision, units of measure, and how absence is represented.
- **Ordering:** element order in collections, event order, callback order, or record processing order.
- **Mutability:** whether returned collections can be modified; whether input objects get mutated; whether results are independent copies.
- **Errors:** exception types, error codes, HTTP statuses, error details, and when errors occur.
- **State and side effects:** persisted records, emitted messages, created files, committed or rolled-back transactions.
- **Timing and concurrency:** timeouts, post-commit data visibility, contention order across operations, and committed resource limits.
- **Communication:** header names, JSON schemas, encoding, field order if consumers depend on it, retry rules, and protocol semantics.

Performance can also become part of the contract when the system publishes or depends on a specific bound, such as an API responding within an SLA threshold. However, do not automatically assume every difference of a few milliseconds breaks compatibility. Clearly identify which bounds are operational commitments and which consumers depend on them.

## 2. Distinguishing behavioral compatibility from other compatibility types

Compatibility types are related yet test different questions. A change can pass compilation checks while still breaking runtime behavior.

| Compatibility type | Primary question | Example breaking change |
|---|---|---|
| Source compatibility | Does consumer source code compile with the new API? | Removing an overload called by consumers |
| Binary compatibility | Does compiled bytecode link and run against the new library? | Removing a method descriptor referenced by old bytecode |
| API compatibility | Is the public API surface preserved? | Renaming a public class or changing a method signature |
| Protocol/data compatibility | Do both sides continue understanding the same protocol and data? | Renaming a JSON field or changing enum meanings |
| Behavioral compatibility | Do consumers continue receiving contracted behavior? | Keeping the method signature while changing results or exceptions |

For example, `getUsers()` may still exist with the signature `List<User> getUsers()`, preserving source and binary compatibility. Yet if the new version deduplicates users, changes list ordering, or returns an unmodifiable collection when the old contract allowed modification, consumers can still break. API or binary compatibility tools do not automatically detect all such differences.

Behavioral compatibility also does not mean all old behavior must exist forever. A product may intentionally fix a bug or change semantics, yet in doing so must recognize this as a contract change, assess impacted consumers, and provide a suitable transition path.

## 3. Java example: changing the implementation while preserving semantics

Suppose a service provides a method retrieving the names of active users:

```java
public List<String> findActiveNames(List<User> users) {
    if (users == null) {
        throw new IllegalArgumentException("users must not be null");
    }

    List<String> result = new ArrayList<>();
    for (User user : users) {
        if (user != null && user.isActive()) {
            result.add(user.getName());
        }
    }
    return result;
}
```

After reading the old implementation and confirming the behavior relied upon by consumers, the contract can be described as follows:

1. Parameter `users` must not be `null`; if `null`, the method throws `IllegalArgumentException`.
2. `null` elements inside the list are skipped.
3. Only users with `isActive() == true` are included in the result.
4. Result ordering matches appearance order in the input list.
5. If duplicate names exist, duplicate elements are retained.
6. The result is an independently mutable `ArrayList`; modifying the result does not mutate the input list.
7. If `getName()` returns `null`, that value is retained in the result.

A Stream API rewrite may be shorter yet alter multiple semantics:

```java
public List<String> findActiveNames(List<User> users) {
    return users.stream()
            .filter(User::isActive)
            .map(User::getName)
            .distinct()
            .toList();
}
```

The new version can cause the following differences:

- When `users == null`, it throws `NullPointerException` instead of `IllegalArgumentException`.
- If the list contains a `null` element, `User::isActive` throws `NullPointerException` instead of skipping it.
- `distinct()` removes duplicate names, changing result count and content.
- `toList()` returns an unmodifiable list, unlike the mutable `ArrayList` of the old implementation.

If the behaviors above belong to the contract to preserve, the Stream API can be used while maintaining semantics:

```java
public List<String> findActiveNames(List<User> users) {
    if (users == null) {
        throw new IllegalArgumentException("users must not be null");
    }

    return users.stream()
            .filter(Objects::nonNull)
            .filter(User::isActive)
            .map(User::getName)
            .collect(Collectors.toCollection(ArrayList::new));
}
```

With a `List` input, the stream preserves the list's encounter order. Omitting `distinct()` keeps duplicate names; `Collectors.toCollection(ArrayList::new)` creates a mutable result; `map(User::getName)` preserves `null` if a user's name is `null`. Input validation keeps the promised exception type and message.

This example demonstrates that technical changes are only safe when boundary semantics remain intact. Using the Stream API itself neither creates nor breaks compatibility; choosing operations and collectors decides the outcome.

### 3.1. Another example: preserving monetary calculation rules

Suppose a fee-calculation contract specifies two decimal places and `HALF_UP` rounding:

```java
public BigDecimal calculateFee(BigDecimal amount, BigDecimal rate) {
    return amount.multiply(rate)
            .setScale(2, RoundingMode.HALF_UP);
}
```

A migration switching to `double`, or switching `HALF_UP` to `HALF_EVEN`, can yield different results on boundary values. Differences may be rare in ordinary data yet still affect invoices, reconciliation, or reports. To preserve compatibility, maintain precision, scale, rounding rules, negative-value handling, and `null` input handling per the existing contract.

## 4. Identifying what must be preserved vs. what may change

Do not deduce the entire contract solely from the implementation. Cross-check API docs, existing tests, real consumers, historical data, and operational commitments. Behavior can be divided into four groups:

| Group | Meaning | How to handle during migration |
|---|---|---|
| Published contract | Documented in docs, schemas, APIs, or official commitments | Must be preserved by default; changing requires versioning or a transition path |
| Behavior relied on by consumers | Undocumented, yet evidence shows consumers use it | Verify impact scope, then decide whether to keep, transition, or change under control |
| Implementation detail | Internal approach not exposed externally | Can change provided no differences leak across the boundary |
| Buggy or out-of-contract behavior | Anomalous outcome, unpromised, with no valid consumer entitled to rely on it | Do not automatically turn into a contract; evaluate before fixing or removing |

Difficulty often lies between "accidental behavior" and "behavior consumers already depend on." For instance, docs never promised return order, yet a consumer relied on that order for years. That dependency does not automatically elevate ordering into a formal contract, yet serves as evidence of migration risk. Identify which consumers are impacted and whether consumers can be updated simultaneously.

A helpful approach is recording commitment levels for each behavior:

- **Guaranteed:** promised by docs or schemas; must be preserved within the published compatibility scope.
- **Observed and relied upon:** currently used by consumers; must be evaluated before changing.
- **Unspecified:** uncommitted and with no observed consumer reliance; should not be relied upon when designing new features.
- **Deprecated:** still supported during the transition period, yet has an established replacement and removal milestone.

This classification avoids two extremes: accidentally breaking important behavior, or freezing every legacy detail including bugs no longer worth maintaining.

## 5. Process for preserving compatibility in a migration

### Step 1: Identify boundaries and consumers

List components calling APIs, reading data, or receiving side effects from the component being replaced. For Java applications, boundaries can be public methods, inter-module interfaces, event listeners, repositories, file formats, or REST endpoints. For shared libraries, consider both consumers compiled concurrently and consumers compiled against older versions.

Do not check only direct call sites. Behavior can propagate via adapters, callbacks, message brokers, caches, or separate processes. Even an internal API within the same repository can be a real contract if multiple modules depend on it.

### Step 2: Describe the contract by scenario

For each operation, document success cases, boundary inputs, pre- and post-state, side effects, errors, and ordering. Focus on questions consumers can observe. If a detail is unclear, mark it unspecified instead of guessing.

For example, with `transfer(source, target, amount)`, the contract should clarify: whether zero amounts are valid; what error a missing account produces; whether failed transfers leave partial writes; whether both accounts update atomically; whether retried requests create a second transaction; and whether events publish before or after commit.

### Step 3: Capture the baseline of the old version

When documentation is lacking, characterization tests record currently running behavior. Tests should use representative inputs, including boundary values and error cases. For systems with side effects, observe storage state, emitted messages, and external service call counts.

Characterization tests document what the old implementation actually does; they do not prove that behavior is the right design. After capturing a baseline, the team must classify which behaviors are contracts, which are unintended dependencies, and which are bugs to intentionally fix.

### Step 4: Run the same scenarios on the new implementation

Use the same datasets and scenarios to compare old and new versions. Compare data structures and semantics rather than log strings alone. For APIs, compare statuses, headers, bodies, and error semantics. For data writes, compare final state and side effects. For concurrency, build scenarios testing appropriate interleaving and atomicity.

### Step 5: Use adapters or compatibility layers when needed

If the new library has different semantics, place an adapter at the boundary to translate back to the contract legacy consumers use. Adapters can normalize exceptions, convert `Optional` to legacy return types, restore ordering, map new enums to legacy values, or transform data schemas.

For example, if a new library throws `NewClientException` while the application's API promised `RemoteServiceException`, an adapter can catch the new exception and map it to the old public exception. Consumers continue observing the familiar contract while internals are replaced.

Adapters should have well-defined scope and be tested as contract boundaries. If kept indefinitely, document maintenance ownership; if used only for transition, define removal criteria and timelines.

### Step 6: Roll out in phases and monitor

For large systems, use expand-and-contract: expand schemas or APIs so old and new versions operate side by side; migrate consumers step by step; confirm zero traffic still depends on old behavior; then remove legacy paths. For persisted data, controlled dual-read or dual-write may be needed, with a defined source of truth and divergence-handling rules.

Production monitoring should focus on signals meaningful to the contract: error rates by category, created record counts, emitted message counts, SLO latencies, retry counts, and outcome discrepancies. Generic success logs are insufficient to prove two versions are compatible.

### Step 7: Communicate changes when the contract cannot be kept

Sometimes old semantics are no longer appropriate or cannot be maintained safely. Treat this as a contract change: identify impacted consumers, supply a new version or endpoint if necessary, publish before/after examples, deprecation windows, migration guides, and how to confirm consumers have migrated.

Do not silently change behavior and expect consumers to notice on their own. An intentional breaking change can still be a sound engineering decision if managed as a genuine migration.

## 6. Testing behavioral compatibility

Different test layers uncover different risks. A solid test suite typically combines:

1. **Unit tests:** verify input rules, outputs, errors, and invariants in narrow scope.
2. **Contract tests:** verify producer and consumer agree on schemas, semantics, and protocols at boundaries.
3. **Characterization tests:** record old-version behavior when documentation is incomplete.
4. **Differential tests:** run identical inputs through two implementations and compare outputs or side effects.
5. **Integration tests:** verify transactions, persistence, messaging, caching, and real components work together properly.
6. **Compatibility tests with old consumers:** verify bytecode, configs, or payloads produced by old consumers still work with the new version when supported.

A JUnit 5 example for the earlier method's contract:

```java
@Test
void preservesOrderDuplicatesAndMutableResult() {
    List<User> input = List.of(
            activeUser("An"),
            activeUser("Binh"),
            activeUser("An"),
            inactiveUser("Chi")
    );

    List<String> result = service.findActiveNames(input);

    assertEquals(List.of("An", "Binh", "An"), result);
    assertDoesNotThrow(() -> result.add("Dung"));
    assertEquals(4, input.size());
}

@Test
void rejectsNullListWithTheContractedException() {
    assertThrows(
            IllegalArgumentException.class,
            () -> service.findActiveNames(null)
    );
}
```

The first test checks ordering, duplicates, and mutability of the result. The second checks the exception type for invalid input. In a real project, add cases for `null` elements, `null` names, empty lists, and verify that mutating the result does not mutate input data if promised.

Avoid writing tests that lock down internal details such as variable names, loop counts, private method call orders, or internal collection types invisible to consumers. Such tests make migration harder without proving behavioral compatibility.

### 6.1. Testing both errors and side effects

A test checking solely that a method throws an exception may be insufficient. For data updates, verify post-error state to confirm transactions rolled back cleanly. For event emission, check that events fire the exact number of times at the right moment. For retries, verify operations are idempotent per contract.

For instance, if `confirmOrder()` promises to emit `OrderConfirmed` only after transaction commit, tests must observe both order state and events. If an event fires before commit and the transaction rolls back, consumers receive a false notification even though the method ultimately fails.

### 6.2. Boundary data often exposes differences

Proactively test values where a new implementation is likely to behave differently from the old one:

- `null`, empty strings, empty collections, and `null` elements;
- negative numbers, zero, very large values, decimals right at rounding midpoints;
- Unicode characters, timezones, locales, and date-time formats;
- duplicate data, unordered data, and data missing fields;
- timeouts, retries, duplicate requests, and concurrent operations;
- enums or schemas adding values unknown to old consumers.

These cases are especially critical when swapping libraries, upgrading JDKs, migrating databases, changing serializers, or altering asynchronous execution.

## 7. Common sources of behavioral changes in Java

### 7.1. Collections and the Stream API

Switching `List` to `Set` can drop duplicates and alter order. Switching `ArrayList` to `List.of(...)` or `Stream.toList()` can turn collections immutable. Using `HashMap` or `HashSet` can break code relying on accidental ordering. Using `parallelStream()` can alter execution order and expose race conditions if lambdas carry side effects.

During migration, inspect encounter order, duplicate handling, mutability, null policies, and thread safety. If ordering is not contracted, consumers should not rely on it; if ordering matters, express it clearly with appropriate types and comparators.

### 7.2. Exceptions and representing missing results

Switching from an exception to `Optional`, from `null` to an empty object, or from checked exceptions to unchecked exceptions can change how consumers handle failures. Distinguish "not found", "invalid input", "unauthorized", "service temporarily unavailable", and "system error". Collapsing these cases into a single default value often loses information consumers need to retry or respond accurately.

### 7.3. Date/time, locale, and timezone

Migrating from `Date`/`Calendar` to `java.time` can be a good improvement, yet instant and timezone semantics must be defined. `LocalDateTime` does not represent a unique instant without a timezone. Formatting dates using machine default locales or timezones can produce different output for identical data between development and production environments. Pass `ZoneId`, `Locale`, or `Clock` explicitly when part of the contract.

### 7.4. Serialization and configuration

Changing Jackson versions, naming strategies, or enum settings can change JSON output and deserialization. `null` values might be omitted instead of emitted; new fields may get different defaults; unrecognized enums may throw errors or map to defaults. When data is stored long-term or exchanged with independent consumers, schemas and compatibility rules must be verified as part of the behavioral contract.

### 7.5. Transactions and asynchronous processing

Moving a synchronous operation to `@Async`, a message queue, or a reactive pipeline can alter when errors surface, processing order, and when data becomes visible. Consumers that previously received exceptions directly might now receive failures only via callbacks or dead-letter queues. Clearly define delivery semantics, retries, ordering, idempotency, and transaction boundaries.

## 8. Common thinking traps

- **Checking compilation only:** code that compiles does not prove runtime results remain compatible.
- **Checking API signatures only:** keeping method names and return types does not guarantee preserving semantics.
- **Comparing happy paths only:** differences commonly emerge on boundary inputs, errors, retries, and partial states.
- **Treating all observed behavior as a contract:** this can freeze bugs or internal details. Classify using documentation and consumer evidence.
- **Treating undocumented behavior as unimportant:** real consumers may already depend on it. Locate and assess consumers before changing.
- **Adding adapters without a removal plan:** transition layers become technical debt without owners and exit conditions.
- **Comparing logs instead of state:** identical logs do not prove databases, messages, or side effects are identical.
- **Changing multiple semantics at once:** when results diverge, it becomes very hard to pinpoint which change caused a regression. Break migrations into observable, verifiable steps.

## 9. Checklist before concluding a migration preserves behavioral compatibility

- [ ] Identified affected consumers and communication boundaries.
- [ ] Documented valid inputs, outputs, errors, and post-operation state.
- [ ] Checked ordering, duplicates, mutability, and null policies where relevant.
- [ ] Captured side effects, transactions, retries, and idempotency.
- [ ] Distinguished published contracts, consumer-relied behavior, and implementation details.
- [ ] Established baselines or contract tests for critical behaviors.
- [ ] Compared the new implementation across the same scenarios, including error cases and boundary data.
- [ ] Defined clear scope, owners, and removal criteria for any adapters or transition mechanisms.
- [ ] Communicated breaking changes to impacted consumers with concrete migration guidance.
- [ ] Production telemetry monitors key contracted outcomes and side effects.

## 10. Conclusion

Behavioral compatibility is the ability to maintain the commitments observable by consumers when an implementation changes. Preserving it requires specifying contracts at boundaries, identifying consumers, capturing baselines, testing both success and failure paths, and managing semantic changes along a clear roadmap. A good migration can deeply transform how a system is built as long as committed behaviors remain intact; when a contract must change, that change must be recognized and communicated as an official part of the migration.
