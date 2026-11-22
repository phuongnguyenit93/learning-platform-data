# Managing Changes to Null, Exceptions, Result Ordering, and Side Effects

## 1. API Evolution Is Not Just Changing Method Signatures

When upgrading Java, a framework, or a library, development teams often start by checking obvious issues: does the class still exist, did the method change parameters or return type, do dependencies cause linkage errors, and does the source still compile? However, an API can **keep the exact same signature and still break the contract with its consumers**.

For example, the method:

```java
List<Order> findOrders(String customerId);
```

can keep the same declaration across two versions while changing how it behaves:

- Previously accepted `null` and treated it as a request to fetch all orders; the new version throws `NullPointerException`.
- Previously returned an empty list when there were no results; the new version returns `null`.
- Previously threw `IllegalArgumentException` if the customer ID was invalid; the new version returns an empty list.
- Previously returned results in ascending creation time order; the new version does not guarantee ordering.
- Previously only read data; the new version updates the `lastAccessedAt` field on every call.

All of the above changes can leave the JVM method descriptor unchanged. Old client bytecode still links, yet results, error handling branches, repeatability, and system data can differ. That is the problem of **behavioral compatibility** in API evolution.

In the context of Java Advance Compatibility Migration, managing the following four contract categories is especially important:

1. **Null contract:** whether the API accepts `null`, when it returns `null`, and how it distinguishes `null` from empty or absent values.
2. **Exception contract:** which exception types the API uses to report errors, when they occur, whether the cause is preserved, and whether retries are allowed.
3. **Ordering contract:** whether the API guarantees result ordering, processing order, or event emission order.
4. **Side-effect contract:** whether the call mutates state, emits events, writes logs, creates resources, or affects other services; how many times side effects happen and when.

You should not assume all current behavior is an immutable contract. However, before changing it, you must identify what consumers depend on, which behavior is documented, and what must be preserved for a safe rollout.

## 2. Distinguishing Source, Binary, and Behavioral Compatibility

| Compatibility Dimension | Key Question | Risk Example |
| --- | --- | --- |
| Source compatibility | Does old Java source code recompile with the new API? | Changing `List<T>` to `Optional<List<T>>` forces call sites to change |
| Binary compatibility | Does old bytecode link with the new implementation? | Deleting an old method can cause `NoSuchMethodError` |
| Behavioral compatibility | Does a valid call still preserve committed results and observable effects? | Method still returns `List<T>` but changes order or returns `null` |
| Data/protocol compatibility | Are data and messages between versions still understood consistently? | Serializer drops fields, changes meaning of `null`, alters precedence |
| Operational compatibility | Do running and observing the system still meet requirements? | A read method starts issuing many requests or creating background load |

Consider two implementations below that share the same signature:

```java
// API version A
public List<String> names() {
    return List.of();
}

// API version B
public List<String> names() {
    return null;
}
```

There is no change in method name, parameters, or return type. However, the client:

```java
for (String name : api.names()) {
    System.out.println(name);
}
```

runs normally with version A and can throw `NullPointerException` with version B. Using an API diff only at the signature level is insufficient; contract tests are needed for what consumers observe.

A change can also create **silent breakage**: no exception is thrown, yet the system returns different data or triggers unwanted updates. Cases such as wrong pagination order, altered semantics of absence, and repeated side effects are often harder to detect than compile errors.

## 3. Defining the Contract Before Modifying

To manage APIs consistently, describe behavior in four verifiable groups:

| Component | What to Record | Example |
| --- | --- | --- |
| Preconditions | Validity conditions for input, including `null` | `customerId` must be non-null and non-blank |
| Postconditions | Type and meaning of result, including not-found cases | Not found returns an empty list, never `null` |
| Error semantics | Exceptions, business errors, retryability, and context | Invalid input -> `IllegalArgumentException`; infrastructure error -> `RepositoryException` |
| Ordering & effects | Result ordering, mutated state, emitted events | Sort by `createdAt` then `id`; read operation writes no data |

Example of a contract description clearer than a signature:

```text
findOrders(customerId):
  Input:
    customerId: non-null, non-blank
  Success:
    returns non-null, immutable snapshot list
    if no matches: empty list
    order by createdAt ASC, id ASC
  Errors:
    IllegalArgumentException for invalid customerId
    RepositoryException for storage failure
  Side effects:
    no database writes
    no business events
    may emit metrics/logs
```

It is not necessary to write documentation in this format for every tiny method. For public APIs, shared libraries, service contracts, or critical business flows, clear descriptions assist reviews and before/after upgrade comparisons.

Both **documented contracts** and **actual consumer assumptions** must be considered. A result order never promised might still be relied upon by consumers. When changing it, notifications and a migration plan may be needed even if the old implementation had no formal commitment.

## 4. Changing How Input `null` Is Accepted

### 4.1. From Accepting `null` to Rejecting `null`

Old API:

```java
public List<User> search(String department) {
    if (department == null) {
        return allUsers();
    }
    return usersIn(department);
}
```

New API:

```java
public List<User> search(String department) {
    Objects.requireNonNull(department, "department");
    return usersIn(department);
}
```

The signature did not change, yet consumers that used to call `search(null)` to fetch all records will fail. This cannot be treated as a harmless refactor. Before changing, you must:

1. Find call sites that could pass `null`, including data from deserialization, mapping, and reflection.
2. Identify the legacy meaning of `null`: “no filter”, “unknown”, “use default”, or “invalid”.
3. Choose replacement APIs with clear semantics, such as `findAll()` and `findByDepartment(String)`.
4. Decide the transition phase: keep old behavior with warnings, or create new methods and deprecate the old method.
5. Test both direct calls and requests crossing controller/service boundaries.

Transition example:

```java
public List<User> findAll() {
    return repository.loadAll();
}

public List<User> findByDepartment(String department) {
    Objects.requireNonNull(department, "department");
    return repository.loadByDepartment(department);
}

/** @deprecated Use findAll() or findByDepartment(...). */
@Deprecated
public List<User> search(String department) {
    return department == null ? findAll() : findByDepartment(department);
}
```

Keeping the old API allows compiled clients to continue operating while the team migrates consumers one by one. Remove the old method only according to the agreed support roadmap.

### 4.2. `null` Is Not Synonymous with Empty String, Empty Collection, or Missing Field

In many APIs, these states carry distinct meanings:

- `null` parameter: not provided or unknown.
- Empty string `""`: has a value, with length zero.
- Whitespace-only string: has content, but violates business constraints.
- Empty collection: has a list, with zero elements.
- **Absent** field in JSON: client did not send the field; may mean “keep existing value” in PATCH.
- JSON field with `null` value: client explicitly requested clearing the value, or represents a state with no data yet.

Example in an update API:

```json
{"displayName": null}
```

is not necessarily equivalent to:

```json
{}
```

If the endpoint handles partial updates, the rules “field absent = unchanged” and “field null = clear” must be clearly defined. When changing serializers, DTOs, validation, or mapping libraries, the risk of losing the distinction between these two states is particularly high.

### 4.3. Overloads and the `null` Literal

Adding an overload can prevent call sites using `null` from compiling:

```java
void send(String value) { }
void send(Integer value) { }

// send(null); // Ambiguous: String and Integer have no subtype relationship.
```

A method previously accepting only `String` could be called with `null` unambiguously. When the library adds an overload accepting `Integer`, recompiling consumer source code may report an ambiguous method call, even though old client bytecode still references the method with descriptor `(Ljava/lang/String;)V`.

This is an example of an API change where source compatibility and behavioral compatibility diverge. If the semantics of the two overloads are too close, consider clearer method names instead of forcing consumers to cast `null` everywhere.

## 5. Changing How Absence Is Represented in Output

### 5.1. Returning `null` vs. Returning an Empty Collection

The two states may be handled differently by clients:

```java
List<Order> orders = service.findOrders(customerId);

if (orders == null) {
    // Could mean: not yet queried, unknown data, or legacy API.
} else if (orders.isEmpty()) {
    // Queried successfully and confirmed there are no results.
}
```

Replacing `null` with an empty list is often a more convenient design if both share the same meaning of “no results”. However, it cannot be changed mechanically if consumers distinguish “no data available yet” from “empty data”.

Conversely, changing an empty list to `null` can break clients iterating over it, calling `size()`, using the Stream API, or serializing directly.

When converting, clearly specify:

- Whether the API guarantees always returning non-null.
- What state an empty collection represents.
- Whether the returned value is mutable or immutable.
- Whether it can contain `null` elements.
- Whether the result is a snapshot or a view updated with source state.

For example, `Collections.emptyList()`, `List.of()`, and an empty `ArrayList` all contain zero elements yet differ in mutability. Switching to `List.of()` can cause `UnsupportedOperationException` in consumers that used to `add()` to the result. This is also a behavioral change even though it is not directly related to `null`.

### 5.2. Moving from Nullable Return to `Optional<T>`

Old API:

```java
public User findById(String id) {
    return repository.getOrNull(id);
}
```

New API:

```java
public Optional<User> findById(String id) {
    return Optional.ofNullable(repository.getOrNull(id));
}
```

Changing the return type from `User` to `Optional<User>` alters both the source signature and the binary descriptor. Do not directly modify a public method used by old consumers if the goal is preserving compatibility. You can add a new API:

```java
public Optional<User> findOptional(String id) {
    return Optional.ofNullable(repository.getOrNull(id));
}

/** @deprecated Use findOptional(String). */
@Deprecated
public User findById(String id) {
    return findOptional(id).orElse(null);
}
```

As a result, old clients using `findById(String)` still receive the exact nullable contract. New clients use `findOptional(String)` where absence is represented explicitly. Once consumers have migrated, the old method can be considered for removal at an appropriate release milestone.

### 5.3. `Optional` Is Not the Default Solution for Every Kind of Absence

`Optional<T>` fits best for APIs meaning “zero or one value”. It does not by itself adequately represent:

- Not found versus unauthorized access.
- No data versus query error.
- Data not yet loaded versus data loaded and empty.
- Non-existent versus deleted.

For distinct business states, a dedicated result type may be needed:

```java
sealed interface LookupResult
        permits Found, NotFound, Forbidden {
}

record Found(User user) implements LookupResult {
}

record NotFound() implements LookupResult {
}

record Forbidden() implements LookupResult {
}
```

The example uses modern Java syntax; when applying it, use a JDK/toolchain supporting the corresponding language features.

Do not use `Optional.empty()` to mask database or network errors if the old contract distinguished failure from not found. Otherwise, clients may assume the operation succeeded while real data became inaccessible.

## 6. Nullability Annotations, Validation, and Their Limits

Some codebases declare annotations such as `@Nullable`, `@NonNull`, or `@NotNull` to express contracts. Annotations can serve static analysis, IDEs, or validation frameworks, yet actual behavior depends on the annotation suite and tools used.

Illustrative example:

```java
public User findById(String id) {
    Objects.requireNonNull(id, "id");
    return repository.find(id);
}
```

The `Objects.requireNonNull` call performs a runtime check and throws `NullPointerException` when the argument is `null`. Conversely, merely adding a non-null annotation does not necessarily cause runtime to enforce that condition automatically.

Distinguish:

1. **Static contract:** IDE or analyzer warns when passing a potentially `null` value.
2. **Runtime validation:** code or framework actually validates input values.
3. **Serialization/transport behavior:** how missing fields, `null` fields, and default values are mapped.

When upgrading a validation framework, do not assume unchanged annotations mean unchanged behavior. Configurations enabling/disabling validators, validation ordering, and exception mapping may change.

### 6.1. Timing of Errors Is Also Part of the Contract

Two implementations:

```java
public void submit(String id) {
    Objects.requireNonNull(id, "id");
    queue.enqueue(id);
}
```

and:

```java
public void submit(String id) {
    queue.enqueue(id);
    Objects.requireNonNull(id, "id");
}
```

both throw `NullPointerException` when `id` is `null`, yet the latter implementation may have already sent a message into the queue before reporting the error. Therefore, when changing how `null` validation works, verify ordering and side effects, not just the exception type.

## 7. Exception Contract: Error Type, Timing, and Recoverability

An API can report failure via:

- Checked exceptions, such as `IOException`.
- Unchecked exceptions, such as `IllegalArgumentException`, `IllegalStateException`, or a business exception.
- A result object representing success/failure.
- `Optional.empty()` if the contract defines “no value” as non-error.
- Failed asynchronous completion, e.g., an exceptionally completed `CompletableFuture`.
- Returning an error code in a response or message when the API crosses an HTTP/message boundary.

Changing the error reporting form changes how clients retry, roll back, log, and notify users.

### 7.1. Checked Exceptions and Source Compatibility

Old version:

```java
public byte[] load(String path) throws IOException {
    return Files.readAllBytes(Path.of(path));
}
```

New version:

```java
public byte[] load(String path) {
    try {
        return Files.readAllBytes(Path.of(path));
    } catch (IOException ex) {
        throw new UncheckedIOException(ex);
    }
}
```

The JVM signature of method `load(String)` does not include the `throws` clause. Therefore, changing only checked exception declarations does not by itself alter the method descriptor. However, when recompiling source code:

- Clients may no longer be allowed to have a `catch` block catching a checked exception that the compiler knows cannot be thrown in the `try` block.
- Clients may need to change retry/rollback logic if the new exception is unchecked.
- Exceptions wrapped inside `UncheckedIOException` may be handled differently by interceptors or exception handlers.

The reverse situation, adding `throws IOException` to an API, can force new consumers to catch or redeclare the exception even though the method's bytecode retains the same descriptor.

### 7.2. Exception Types Are Not Just Messages

Suppose a client:

```java
try {
    repository.save(order);
} catch (DuplicateOrderException ex) {
    return Result.alreadyExists();
} catch (TransientStorageException ex) {
    return Result.retryLater();
}
```

If the new framework merges both cases into `RepositoryException`, the client no longer knows when it may retry and when it must return a different business result. Even though the method keeps the same signature, exception translation has changed the behavior of the entire system.

When changing exception mapping, identify:

| Dimension | What to Preserve or Publish |
| --- | --- |
| Exception type | Checked, unchecked, class hierarchy, specific subtypes |
| Trigger conditions | Invalid input, not found, conflict, timeout, infrastructure |
| Timing | Before side effects, mid-transaction, or after successful write |
| Cause | Are `getCause()` and context preserved |
| Retryability | Is it safe to call again, is backoff/idempotency key needed |
| Observability | Do logs, metrics, traces, HTTP statuses, and error codes remain consistent |
| Transaction | Does the exception trigger transaction rollback per policy |

### 7.3. Do Not Accidentally Swallow Exceptions

Dangerous example:

```java
public Optional<User> find(String id) {
    try {
        return Optional.ofNullable(repository.find(id));
    } catch (Exception ex) {
        return Optional.empty();
    }
}
```

This code conflates “user not found” with connection failures, serialization failures, and unexpected bugs. Consumers may interpret `Optional.empty()` as a successful lookup with no data.

If you need to translate exceptions across a boundary, catch specific types and preserve semantics:

```java
public Optional<User> find(String id) {
    try {
        return Optional.ofNullable(repository.find(id));
    } catch (StorageTimeoutException ex) {
        throw new UserLookupUnavailableException("Lookup timed out", ex);
    }
}
```

The example assumes business exceptions are already defined. What matters is that the new exception has a clear purpose and preserves the cause, without turning infrastructure errors into an absent state.

## 8. Exceptions in Asynchronous and Lazy APIs

### 8.1. Changing from Synchronous to Asynchronous

Two APIs:

```java
User fetch(String id);
CompletableFuture<User> fetchAsync(String id);
```

differ not only in return type:

- Errors from `fetch` can be thrown immediately within the call.
- Errors from an asynchronous operation are usually represented by an exceptionally completed future.
- Clients waiting with `join()` may observe `CompletionException` wrapping the cause.
- Clients waiting with `get()` may receive `ExecutionException`.
- Execution thread, cancellation, and side-effect timing may differ.

If migration moves an API from synchronous to asynchronous, redefine where errors are handled and transaction boundaries. You cannot simply change the return type and keep existing assumptions about exceptions.

### 8.2. Lazy Evaluation Can Shift Error Timing

Example:

```java
Stream<Order> orders = repository.streamOrders();
```

Creating a `Stream` may not have executed all data-reading steps yet. Errors may appear only when a terminal operation is called:

```java
List<Order> result = orders.toList();
```

In a migration from `List<Order>` to `Stream<Order>`, errors can shift from the time the repository is called to the time the stream is consumed. You must establish who is responsible for closing resources, whether the transaction is still open, and whether the stream may be consumed multiple times.

In particular, replacing an eager result with a lazy one can cause side effects and exceptions to emerge later, after resource scopes or transactions have already ended.

### 8.3. Preserving Interrupt and Cancellation Status

Do not translate every exception into a generic type and thereby lose `InterruptedException` or cancellation signals. When code catches `InterruptedException` at a boundary that cannot redeclare it, a common option is restoring the interruption status:

```java
try {
    worker.await();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new OperationCancelledException("Interrupted", ex);
}
```

Actual handling depends on the API contract and the application's concurrency model. The critical thing is that migration does not silently turn a cancelled task into a success state or infinite retries.

## 9. Result Ordering Is Part of the Contract

A result containing the right elements in the wrong order can still break business logic:

- The first page of pagination fetches different records than before.
- A batch processor executes a later step before an earlier step.
- A rule engine runs low-priority rules before high-priority rules.
- The UI displays unstable data across refreshes.
- Tests or consumers compare data in a fixed order.
- Digital signatures, hashes, or cache keys depending on ordered representations change.

Therefore, distinguish:

1. **Element set:** is all the right data present?
2. **Element ordering:** is ordering guaranteed and by what criteria is it sorted?
3. **Tie stability when values are equal:** if two elements are equal under the comparator, is there a tie-breaker?
4. **Processing order:** do callbacks, events, or side effects occur in that order?

### 9.1. `List` Does Not by Itself Promise Business Ordering

`List` preserves element positions within the collection. However, the signature `List<Order> findOrders()` does not tell whether the list is sorted by time, id, or priority. If the old implementation used a query with `ORDER BY` while the new implementation does not, both return valid `List` instances yet have different behavioral contracts.

To be clear, document:

```text
findOrders():
  returns orders sorted by createdAt DESC, id ASC
```

If there is no ordering commitment, explicitly state “ordering unspecified” and avoid writing consumers that rely on an accidentally observed order.

### 9.2. Different Collections Have Different Iteration Rules

| Structure | Ordering-Related Characteristics |
| --- | --- |
| `ArrayList` | Preserves element positions according to insertion/modification operations |
| `LinkedHashSet` | Usually maintains insertion order |
| `TreeSet` | Sorted by natural ordering or comparator |
| `HashSet` | Does not guarantee iteration order |
| `LinkedHashMap` | Ordered by insertion or access depending on configuration |
| `TreeMap` | Sorted by key |
| `HashMap` | Does not guarantee iteration order |

Never treat the order observed in one run of `HashMap` or `HashSet` as a stable contract. Changing JDK, element count, or hashing/resizing behavior can alter the order while remaining compliant with the collection's API.

### 9.3. Sorting with a Comparator Having a Tie-Breaker

Example needing to sort orders by creation date descending:

```java
Comparator<Order> orderComparator =
        Comparator.comparing(Order::createdAt)
                .reversed()
                .thenComparing(Order::id);

orders.sort(orderComparator);
```

If multiple orders share the same `createdAt`, `id` helps create a deterministic order, provided `id` is suitable and stable. If the tie-breaker is omitted, loading data twice from sources with different input ordering can produce different results despite the same primary criterion.

When adding a tie-breaker, distinguish:

- Is this clarifying a contract that originally only promised sorting by `createdAt`, or changing a published order?
- Do consumers rely on the relative stability of equal elements?
- How is `null` in sort keys handled?
- Do locale/collation and timezone affect comparisons?

`Comparator.nullsFirst(...)` or `nullsLast(...)` can clearly define ordering for nullable keys; choose according to the contract rather than merely avoiding `NullPointerException`.

## 10. Stream API, Parallelism, and Encounter Order

### 10.1. Encounter Order Does Not Always Exist

A stream can have an **encounter order** if the source or a transformation defines an order. For example, a stream from `List` has an encounter order, whereas a stream from `HashSet` does not guarantee one.

```java
List<String> names = List.of("An", "Binh", "Chi");

List<String> result = names.stream()
        .map(String::toUpperCase)
        .toList();
```

For an ordered stream, `toList()` preserves encounter order in the result. However, if changing the source to an unordered collection, do not expect the same order just because the pipeline looks similar.

### 10.2. `forEach` and `forEachOrdered`

```java
names.parallelStream().forEach(System.out::println);
```

In a parallel stream, `forEach` does not guarantee executing side effects in encounter order. If observable order is required:

```java
names.parallelStream().forEachOrdered(System.out::println);
```

`forEachOrdered` maintains encounter order if the stream has one, but can reduce parallelism benefits and does not make arbitrary side effects thread-safe. Before switching a stream from sequential to parallel, check whether any consumer relies on callback order or shared mutable state.

### 10.3. `sorted()` and `unordered()`

`Stream.sorted()` can produce ordering according to a comparator. For streams with an encounter order, sorting is stable; for unordered streams, there is no same commitment regarding the relative position of equal elements. Use a comparator with a tie-breaker if deterministic results are needed.

`unordered()` allows the pipeline to drop encounter order requirements in subsequent steps. It can help optimize certain parallel operations, but is unsuitable if the output is an ordering-committed API.

In particular, `findFirst()` and `findAny()` have different semantics: `findFirst()` respects encounter order when present, whereas `findAny()` is permitted to select any element. Switching between the two methods for performance optimization can change observable results.

## 11. Database Result Ordering and Pagination

A SQL query without `ORDER BY` does not guarantee row order. Previously observed ordering can change when upgrading drivers, databases, indexes, or query planners.

Example insufficient for pagination:

```sql
SELECT id, created_at, total
FROM orders
LIMIT 20 OFFSET 20;
```

Example with clear ordering:

```sql
SELECT id, created_at, total
FROM orders
ORDER BY created_at DESC, id ASC
LIMIT 20 OFFSET 20;
```

If `created_at` is not unique, adding `id` as a tie-breaker makes ordering more deterministic. Even so, offset pagination can still yield duplicate or skipped records between requests if rows are inserted/deleted concurrently. When high consistency is required, consider snapshot or keyset pagination per the product contract.

ORM/framework changes can inadvertently turn a previously sorted query into an unsorted query. When an API publishes ordering, test results at the integration-test level with multiple records sharing the same primary comparator key and with concurrent modifications where appropriate.

### 11.1. JSON Object Order Differs from JSON Array Order

When replacing a serializer, distinguish ordering that belongs to the contract from mere presentation. Element ordering in an **array** usually carries meaning; key ordering of a **JSON object** should generally not be treated by consumers as business information unless a specific protocol defines that requirement.

If using a JSON string to generate signatures or hashes, establish canonicalization or deterministic serialization rules; do not depend on the accidental iteration order of a `Map`.

## 12. Side Effects: What Else Did a Method Do Besides Returning a Value?

A side effect is an observable state change or action beyond the return value, such as:

- Writing/updating/deleting database records.
- Modifying caches or in-memory mutable state.
- Publishing events to queues, message brokers, or event buses.
- Sending HTTP requests, emails, or webhooks.
- Generating IDs, reading current time, creating files, locking or opening resources.
- Writing audits, metrics, logs, or traces.
- Invoking consumer callbacks, triggering lazy loading, or starting background tasks.

Not every side effect is bad. However, consumers need to know **whether** a side effect exists, whether it occurs **before or after returning**, **how many times** it can occur, inside **which transaction**, and whether it can **recover** upon failure.

### 12.1. Changing from Read-Only to Read-and-Write

Old API:

```java
public User getUser(String id) {
    return repository.findById(id);
}
```

New API:

```java
public User getUser(String id) {
    User user = repository.findById(id);
    repository.updateLastAccessed(id, Instant.now());
    return user;
}
```

The signature did not change, yet the read call now performs a database write. Consequences can include increased load, new write permission requirements, locks/transactions occurring, replication lag, audit events, and failures in tests previously using read-only transactions.

If tracking is desired, create a method whose name explicitly expresses the side effect or place that action at an appropriate boundary. If keeping the old name, publish and test the side effect as part of the new contract.

### 12.2. Changing the Order of Side Effects

Compare:

```java
public void createOrder(Order order) {
    repository.save(order);
    publisher.publish(new OrderCreated(order.id()));
}
```

with:

```java
public void createOrder(Order order) {
    publisher.publish(new OrderCreated(order.id()));
    repository.save(order);
}
```

Both versions share the same signature and the same two operations, yet if `save` fails, the second version may have already emitted an event for a non-existent order. Even the first approach risks emitting an event inconsistently relative to the transaction if publishing occurs before commit. When consistency is needed, use an appropriate strategy such as transactional outbox, idempotent consumers, or post-commit event emission per a verified design.

### 12.3. Changing How Many Times a Callback Is Invoked

Suppose the API:

```java
void process(Item item, Consumer<Item> callback);
```

previously invoked the callback exactly once. After adding retries, the callback may be invoked multiple times. If the consumer callback sends emails or deducts money, the impact can be severe even though the API still accepts the same `Consumer<Item>`.

The contract should state at least:

- Whether the callback is invoked 0, 1, or multiple times.
- Whether it can be called again after a failure.
- On which thread the callback runs.
- Whether ordering between callbacks is guaranteed.
- Whether concurrent execution is possible.
- Whether exceptions from the callback are propagated, logged, retried, or ignored.

Do not use a callback with non-idempotent side effects inside a retry mechanism without protection against duplicate execution.

## 13. Idempotency, Retries, and Transactions

### 13.1. Idempotency Is a Behavioral Property, Not a Return Type

An idempotent operation can be called repeatedly while the final effect equals a single call, within the defined contract scope. Setting state to a value is usually easier to make idempotent than incrementing a value:

```java
account.setStatus("ACTIVE"); // Can be idempotent with respect to final state.
account.incrementPoints(10); // Usually not idempotent.
```

Repeated logging or metric recording can still be an observable side effect; clearly define **which level of idempotency** the system commits to (business state, external events, billing, audit).

Changing an API from non-retrying to auto-retrying can increase the number of writes, outgoing requests, or emitted events. If consumers already have retries externally, two layers of retries combining can cause amplification.

### 13.2. Using an Idempotency Key When Appropriate

Example of a command:

```java
PaymentResult charge(
        String requestId,
        String accountId,
        BigDecimal amount);
```

If `requestId` is defined as an idempotency key, the implementation can record processed requests to avoid double-charging when clients retry. However, merely adding a `requestId` parameter to the signature does not guarantee idempotency; the system needs to design state storage, race condition checks, and result replay.

During migration, test multiple calls with the same key, calls with different keys, and error handling before/after commit to confirm behavior.

### 13.3. Exceptions and Transaction Rollback

Transaction frameworks have their own rules on what causes rollback. In some common configurations, unchecked exceptions may trigger rollback by default while checked exceptions do not necessarily do so; this depends on the framework, annotations, and configuration.

Therefore, changing from `IOException` to `UncheckedIOException` or changing how exceptions are wrapped can cause transactions to roll back differently, even though input data and method signatures remain unchanged. When upgrading frameworks, verify the real transaction policy instead of guessing from exception names.

### 13.4. Do Not Assume “Failure” Means “No Side Effect Occurred”

A request can write to the database successfully yet time out before the response reaches the client. The consumer sees an exception and retries, creating the possibility of duplicate writes. Similarly, a transaction may roll back data while emails or external events outside the transaction have already been sent.

The API should clearly define:

- Which outcome confirms the commit completed.
- Which errors allow automatic retry.
- Whether there is a way to check request status via correlation/idempotency key.
- Which side effects sit outside the transaction.
- How to recover or compensate when failure happens mid-way between steps.

## 14. Side-Effect Changes When Using Caches, Lazy Loading, and Streams

### 14.1. Caches Affect Source Access Counts

A method that previously queried the database on every call and uses caching after migration may return the same value in simple tests. However, behavior changes:

- Data freshness may differ.
- Callbacks/metrics attached to each source query may fire fewer times.
- Storage errors may appear later or be masked on cache hits.
- Side effects relying on data loading may not happen on every invocation.

Define freshness, invalidation, TTL, and consistency level. Do not treat caching as “just an optimization” when consumers depend on fresh data immediately after writes.

### 14.2. Lazy Loading Can Shift Side Effects

If a method switches from returning an already-loaded `List<T>` to a lazily evaluated `Stream<T>`, database reads and exceptions can occur during the terminal operation. Consumers need to know resource lifetimes and who closes the stream, especially for streams tied to connections/result sets.

In the case of moving to reactive streams, subscription can trigger execution. If each subscription queries the source again, subscribing twice can produce duplicate side effects. Document API semantics instead of assuming publishers/futures/streams are direct drop-in replacements for eager lists.

### 14.3. `parallelStream()` and Shared Mutable State

Unsafe example:

```java
List<String> output = new ArrayList<>();

items.parallelStream()
        .map(Item::name)
        .forEach(output::add);
```

`ArrayList` is not synchronized for concurrent writes; results can be wrong or unstable. For building lists, prefer collection operations managed by the stream framework:

```java
List<String> output = items.parallelStream()
        .map(Item::name)
        .toList();
```

This example avoids mutating a shared list inside `forEach`. If external side effects are required, define the concurrency contract and synchronization or processing separation.

## 15. Comprehensive Example: Evolving an Order Search API

Suppose the old version had an implicit contract:

```java
public List<Order> search(String customerId) {
    if (customerId == null) {
        return null;
    }
    List<Order> results = repository.findByCustomer(customerId);
    return results; // Old repository returns in ascending createdAt order.
}
```

In the new version, the team wants to:

1. Require `customerId` to be non-null.
2. Return an empty list when there are no results.
3. Return results in descending `createdAt` order.
4. Throw `OrderLookupException` on storage failures, instead of the raw exception.
5. Emit an audit event on every search.

If applied simultaneously while keeping the `search(String)` name and signature, old consumers might:

- Use `null` to represent a request with no customer selected yet.
- Distinguish `null` from an empty list.
- Use the first element as the oldest order.
- Catch only the old repository's exception.
- Call `search` in code paths that must stay read-only and should not emit audit events.

These are five behavioral breaking changes even though the method descriptor remains compatible.

### 15.1. A Separate New API Approach

Instead of silently changing the old method, introduce an API with a new name/contract:

```java
public List<Order> findRecentOrders(String customerId) {
    Objects.requireNonNull(customerId, "customerId");
    if (customerId.isBlank()) {
        throw new IllegalArgumentException("customerId is blank");
    }

    List<Order> result;
    try {
        result = repository.findByCustomer(customerId);
    } catch (StorageException ex) {
        throw new OrderLookupException("Cannot query orders", ex);
    }

    return result.stream()
            .sorted(Comparator
                    .comparing(Order::createdAt)
                    .reversed()
                    .thenComparing(Order::id))
            .toList();
}
```

The example assumes business types and repository already exist. The new method returns a sorted non-null list and does not automatically emit audit events. If the product truly requires auditing, determine at which boundary audit records must be written and how to ensure transactions/no duplicates; do not inject it into every query simply because of migration.

### 15.2. Keeping an Adapter for Old Consumers

```java
/** @deprecated Legacy nullable lookup; migrate to findRecentOrders(). */
@Deprecated
public List<Order> search(String customerId) {
    if (customerId == null) {
        return null;
    }
    return repository.findByCustomerInLegacyOrder(customerId);
}
```

The adapter must genuinely preserve the old contract during the support window. If the new repository no longer provides legacy ordering, explicitly sort using the old comparator. Do not call the new method and hope side aspects such as null/exception/order remain unchanged.

### 15.3. Migrating Consumers Group by Group

Consumers moving to `findRecentOrders` need to update assumptions about inputs, empty results, exceptions, and ordering. For audit events, decide on a dedicated API or orchestration layer that actively writes audits per workflow. Once all consumers have migrated and the support window has ended, the old `search` method can be considered for removal in a clearly announced release.

## 16. Testing Behavioral Contracts with JUnit

Write tests before migration to capture critical behavior. **Contract** tests differ from implementation-detail tests: they verify what consumers rely on, without locking down every line of internal code.

### 16.1. Null and Empty Contract

JUnit 5 example with the new API:

```java
@Test
void rejectsNullCustomerId() {
    assertThrows(
            NullPointerException.class,
            () -> service.findRecentOrders(null));
}

@Test
void returnsEmptyNonNullListWhenNoOrders() {
    List<Order> result = service.findRecentOrders("customer-404");

    assertNotNull(result);
    assertTrue(result.isEmpty());
}
```

If the contract chooses `IllegalArgumentException` instead of `NullPointerException`, tests must reflect that choice. The two are not equivalent to consumers catching a specific exception.

### 16.2. Exception Translation

```java
@Test
void preservesStorageFailureAsCause() {
    StorageException failure =
            new StorageException("database unavailable");
    when(repository.findByCustomer("customer-1"))
            .thenThrow(failure);

    OrderLookupException actual = assertThrows(
            OrderLookupException.class,
            () -> service.findRecentOrders("customer-1"));

    assertSame(failure, actual.getCause());
}
```

This is JUnit 5 and Mockito style pseudocode; exception names and mock setup vary by codebase. Testing causes helps avoid losing diagnostic context when changing frameworks.

### 16.3. Ordering and Tie-Breaker

```java
@Test
void sortsByCreatedAtDescendingThenIdAscending() {
    List<Order> result = service.findRecentOrders("customer-1");

    assertEquals(
            List.of("order-c", "order-a", "order-b"),
            result.stream().map(Order::id).toList());
}
```

Tests need fixtures creating appropriate data (multiple orders with identical timestamps, deterministic IDs). If there is only one order, the test cannot detect ordering regressions.

### 16.4. No Out-of-Contract Side Effects

```java
@Test
void searchingDoesNotWriteOrPublishBusinessEvents() {
    service.findRecentOrders("customer-1");

    verify(repository, never()).save(any());
    verify(eventPublisher, never()).publish(any());
}
```

A similar test can verify an operation happens exactly once:

```java
verify(eventPublisher, times(1)).publish(any(OrderCreated.class));
```

Interaction tests should be used at critical boundaries; there is no need to mock every internal method. For DB transactions and message brokers, integration tests or tests across contract boundaries carry higher value than mock-only tests because they check commit timing and duplicate possibilities.

### 16.5. Testing with Old and New Artifacts

If compiled clients must still be supported, keep a consumer contract test suite built against the old API and run it against the new implementation. Do not merely recompile tests from old source against the new API; doing so can miss binary linkage errors. In parallel, run the new consumer test suite to confirm the new contract.

Beyond deterministic unit tests, property-based or metamorphic tests can be used for invariants:

- Non-null result for every valid input.
- Sorted according to the published comparator.
- Two calls with the same idempotency key do not create two business records.
- Invalid input causes no side effects.
- Retryable failures preserve cause/error code and do not multiply side effects beyond the contract.

For concurrency, use tests with controlled timing and schedulers when possible; do not treat one successful run as conclusive proof of thread safety.

## 17. Process for Managing API Changes During Migration

### Step 1: Establish the Contract Baseline

Record signatures, nullability, observable exceptions, data ordering, side effects, callback invocation counts, retries, and transaction semantics. Save existing tests along with JDK, framework, dependency, and runtime versions.

### Step 2: Identify Consumers and Dependency Depth

Locate consumers using the API: Java code, reflection, REST/JSON clients, message consumers, batch jobs, and automated callers. Check where consumers rely on `null`, exception types, the first element, or calling the method read-only.

### Step 3: Classify Changes

| Change | Risks to Evaluate | Common Transition Approaches |
| --- | --- | --- |
| Accept `null` -> reject `null` | Old clients throw exceptions | New method, validation at boundary, legacy adapter |
| Return `null` -> empty collection | Consumers distinguish “unknown” from “empty” | Clear result type, deprecation |
| Nullable `T` -> `Optional<T>` | Source/binary signature changes | New method with different name, keep old method |
| Checked -> unchecked exception | Catch/retry/rollback differs | Exception adapter, document error mapping |
| Exception -> empty result | Loses distinction between error and not found | Keep infrastructure errors, use multi-state result type |
| Ascending -> descending sort | Pagination and consumer logic change | API with clear name/params, contract tests |
| Ordered collection -> unordered | Nondeterministic results | Preserve sort or announce breaking change |
| Read-only -> write/event | Permissions, load, transactions, duplicates | Split command/query or explicit orchestration |
| Sync -> async/lazy | Error timing, lifecycle, threads | New API, test async/cancellation/resources |

### Step 4: Choose a Compatibility-Preserving Strategy

You can choose:

1. **Keep the old contract:** fix the implementation to continue preserving published behavior.
2. **Additive API:** keep the old method and add a method with a new name/contract.
3. **Time-bound adapter:** convert between old and new representations, with an owner and removal milestone.
4. **API versioning:** create a next-generation endpoint/interface/schema when changes are broad or involve multiple systems.
5. **Planned breaking release:** announcements, migration docs, consumer inventory, and rollout/rollback.

There is no single approach fitting every API. For security changes requiring rejection of dangerous inputs, old behavior may have to change immediately; in that case, clearly mark it as a breaking behavioral change and provide remediation guidance for consumers.

### Step 5: Write Tests Protecting Contracts

Prioritize tests for null/empty, exception mapping, data ordering, and side-effect counts. For cross-service APIs, use contract/integration tests and scenarios with multiple producer–consumer versions running concurrently.

### Step 6: Release and Monitor

Observe exception rates by type, retry counts, latency, database update frequency, event counts, duplicate rates, pagination outputs, and corresponding business metrics. For canary rollouts, compare old/new versions using comparable data and traffic.

### Step 7: Remove Compatibility Layers When Ready

Only remove adapters and legacy endpoints after confirming consumers no longer depend on them, transition data is stable, and support policies allow. Archive the migration guide and actual evidence to support maintenance of future upgrades.

## 18. Distinguishing What Is Contract vs. What Is Implementation Detail

You do not need to turn every implementation behavior into a public guarantee. If an API only promises “returns a set of results, order not guaranteed”, switching from `HashSet` to `TreeSet` may not violate the published contract. However, before switching, still check whether real consumers informally rely on ordering, especially in long-running deployed systems.

Helpful review questions:

- Does the API documentation clearly state `null` scenarios?
- Are exception classes and error codes used by clients to decide retries or display messages?
- Is result ordering published or reused for pagination?
- Does a method named `get/find/read` unexpectedly perform writes or publish events?
- Can callbacks be invoked multiple times, on another thread, or after the method returns?
- Does changing the JDK/framework alter default serializers, transaction managers, collections, or stream executors?

A good design principle is to **explicitly state what is guaranteed and avoid implicitly promising what cannot be controlled**. For example, if ordering is not part of the contract, explicitly state “unspecified ordering”; if an API can emit events, state the conditions and delivery guarantees rather than relying on the method name.

## 19. Common Mistakes

**Checking only compilation and runtime linkage.** A green build does not guarantee `null`, exceptions, sorting, or side effects remain unchanged. Critical behavioral contracts must be tested.

**Changing a nullable return to an empty list without analyzing semantics.** If `null` means “data not loaded yet” while an empty list means “no records”, merging both states loses information.

**Assuming `@NonNull` changes runtime behavior on its own.** Annotations only take effect depending on the tool or framework used; confirm validation is actually executed.

**Swallowing all exceptions and returning `Optional.empty()`.** This turns infrastructure errors into a “not found” business state, breaking monitoring and retries.

**Changing exception types while ignoring transaction policy.** Checked/unchecked translation can alter rollback behavior, especially when frameworks rely on exception types.

**Trusting `HashMap` order or SQL results without `ORDER BY`.** Ordering observed in one environment is not guaranteed in another.

**Adding `parallelStream()` without checking side effects.** Callback order and thread safety can change; shared mutable state easily suffers races.

**Turning a read method into a write method without notice.** Clients may be calling it inside a read-only transaction or with read-only permissions.

**Enabling retries without checking idempotency.** A timeout does not prove side effects did not occur; retries can duplicate operations.

**Using mock-only unit tests to conclude events/transactions are safe.** Mocks can verify calls but cannot by themselves prove actual commit timing or rollback policies.

**Bundling multiple behavioral changes into one release without isolated evidence.** When regressions occur, it becomes difficult to tell whether nullability, exception mapping, sorting, or side-effect changes caused the bug.

## 20. Checklist Before Approving Changes

For an API with existing consumers, before releasing, you should have answers for:

- [ ] Identified all `null`, blank, missing input cases, and default values.
- [ ] Identified `null`, empty, optional results, and not-found state representations.
- [ ] Recorded exception types, trigger conditions, causes, retryability, and rollback policies.
- [ ] Checked synchronous exceptions, asynchronous exceptions, cancellation, and lazy evaluation where relevant.
- [ ] Identified the ordering contract, comparator, tie-breaker, and data source.
- [ ] Ensured no reliance on iteration order not guaranteed by collections/DB.
- [ ] Identified side effects, side-effect order, execution counts, and transaction boundaries.
- [ ] Evaluated idempotency when adding retries, queues, or multiple callbacks.
- [ ] Reviewed impact when converting sequential code to parallel or async.
- [ ] Tested behavior of serializers, validation, and frameworks after migration.
- [ ] Have dedicated tests for null, empty, exceptions, ordering, and effects on critical paths.
- [ ] Have old-client/new-implementation tests when binary compatibility is committed.
- [ ] Have adapters or versioning plans if new behavior is incompatible.
- [ ] Have consumer list, responsible owners, and rollout/rollback plans.
- [ ] Release notes clearly document breaking behavioral changes, not just method signature changes.
- [ ] Metrics/logs are sufficient to detect errors after rollout.

Checklists help turn seemingly “internal” changes into traceable engineering decisions. The level of testing and documentation should match the API's blast radius; it is not necessary to apply the same strictness to every non-public helper method.

## 21. Conclusion

In Java API evolution, changing return values or parameters is not the only risk. A method can keep the same signature and link completely fine yet still break the contract if it shifts `null` handling, changes exception types, drops ordering guarantees, or introduces new side effects.

For safe migration, view an API as an **observable contract**: which inputs are valid, what outputs represent what, how errors appear, what ordering results have, and what state a call mutates. Record the baseline, classify breaking changes, provide adapters or new API versions when needed, and test null/empty, error semantics, ordering, and side effects from the consumer's perspective. This approach helps avoid the “build succeeded but business logic broke” situation when upgrading the JDK, frameworks, or libraries.
