# Designing Policies for `null` Keys and `null` Values

When transforming data into a `Map` using the Java Stream API, the program must answer two distinct questions: **what to do if a key is `null`**, and **what to do if a value is `null`**? An ordinary `HashMap` can hold such values, but that does not mean every collector or every `Map` implementation accepts them. Ignoring this difference easily leads to a `NullPointerException` when `collect` runs, silent record loss, or a `Map` with ambiguous semantics.

This lesson belongs to the **Collecting to Maps** chapter of the **JAVA_STREAM_API** module. We will design explicit `null` policies for `Collectors.toMap`, `groupingBy`, `toUnmodifiableMap`, various `Map` structures, and sequential/parallel pipelines. The content connects directly to `filter`, `map`, `collect`, duplicate-key handling, collector characteristics, laziness, shared state, and data-processing costs.

## 1. Three Data States Must Be Distinguished

Consider a directory `Map<String, String>` mapping user IDs to emails:

```java
import java.util.HashMap;
import java.util.Map;

Map<String, String> emails = new HashMap<>();
emails.put("u1", "an@example.com");
emails.put("u2", null);

System.out.println(emails.get("u1"));          // an@example.com
System.out.println(emails.get("u2"));          // null
System.out.println(emails.get("u3"));          // null
System.out.println(emails.containsKey("u2"));  // true
System.out.println(emails.containsKey("u3"));  // false
```

There are three distinct business states here:

1. **Key present with value**: user `u1` has an email.
2. **Key present with `null` value**: user `u2` has a record but no email yet.
3. **Key absent**: user `u3` has no record in the directory.

`get(key) == null` **cannot distinguish between states 2 and 3**. If the application needs to tell them apart, use `containsKey` together with `get`, or choose a value model that represents absence explicitly.

A `null` key is a separate problem: which group should a record go into when the attribute used as the key is absent? If multiple records have a `null` key, they compete for a single entry in the `Map`, so you must also define a **duplicate-key policy**.

## 2. Not Every `Map` Shares the Same `null` Contract

Before choosing a collector, determine the result structure:

| Structure or API | `null` Key | `null` Value | Notes |
|---|---|---|---|
| `HashMap` | Allows one `null` key | Allowed | No iteration order guaranteed |
| `LinkedHashMap` | Allows one `null` key | Allowed | Preserves insertion order by default |
| `TreeMap` with natural ordering | Not allowed | Allowed | Can use a `null`-supporting comparator to define custom key order |
| `ConcurrentHashMap` | Not allowed | Not allowed | Concurrent structure |
| `Map.of(...)`, `Map.ofEntries(...)` | Not allowed | Not allowed | Unmodifiable; `null` throws an error |
| `Map.copyOf(map)` | Not allowed | Not allowed | Produces an unmodifiable result |
| `Collectors.toUnmodifiableMap(...)` | Not allowed | Not allowed | Java 10+ collector |
| `Collectors.toMap(...)` | Do not rely on accepting `null` | Do not use to store `null` values | Returned `Map` type is not guaranteed |
| `Collectors.groupingBy(classifier)` | Rejects `null` grouping keys | Depends on downstream collector | Do not infer from the result map possibly being a `HashMap` |

Default `Collectors.toMap` commonly creates a `HashMap` on standard JDKs, and some versions may accept a `null` key; **the collector contract guarantees neither the map type nor support for `null` keys**. Meanwhile, a `valueMapper` returning `null` can trigger `NullPointerException` right during accumulation. Therefore, resolve the `null` policy before relying on the collector.

The following snippets use Java 17. The `Map.of` factories appeared in Java 9; `Collectors.toUnmodifiableMap` and `Map.copyOf` arrived in Java 10; `record` became standard in Java 16.

## 3. Understanding `Collectors.toMap` Before Building a Policy

The simplest overload:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record User(String id, String email) {}

List<User> users = List.of(
        new User("u1", "an@example.com"),
        new User("u2", "binh@example.com")
);

Map<String, String> emailById = users.stream()
        .collect(Collectors.toMap(User::id, User::email));

System.out.println(emailById.get("u1")); // an@example.com
```

The two functions `User::id` and `User::email` are the **key mapper** and **value mapper**, respectively. The collector expects a value to place into the map for each source element. When data is complete and keys are unique, this pattern is concise.

Important overloads:

| Overload | Effect |
|---|---|
| `toMap(keyMapper, valueMapper)` | Creates a map, throws `IllegalStateException` on duplicate keys |
| `toMap(keyMapper, valueMapper, mergeFunction)` | Allows resolving duplicate keys |
| `toMap(keyMapper, valueMapper, mergeFunction, mapFactory)` | Also lets you choose the result `Map` structure |

An error to distinguish:

```java
List<User> duplicateIds = List.of(
        new User("u1", "old@example.com"),
        new User("u1", "new@example.com")
);

// Do not run: duplicate key "u1" will throw IllegalStateException.
// duplicateIds.stream()
//         .collect(Collectors.toMap(User::id, User::email));
```

`IllegalStateException` from **duplicate keys** and `NullPointerException` from **`null` values** are two separate issues. Adding a `mergeFunction` handles duplicate keys, yet **does not make `null` a valid value** for `toMap`.

## 4. Four Practical Policies for `null` Keys

Given input:

```java
record Ticket(String id, String team, String description) {}

List<Ticket> tickets = List.of(
        new Ticket("T1", "backend", "API"),
        new Ticket("T2", null, "Uncategorized"),
        new Ticket("T3", "frontend", "UI")
);
```

The `team` attribute may be missing, so you must pick one of the policies matching the business contract.

### 4.1. Reject records missing a key

If `team` is a required field, the error should surface clearly at the processing boundary:

```java
import java.util.Objects;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, String> descriptionsByTeam = tickets.stream()
        .collect(Collectors.toMap(
                ticket -> Objects.requireNonNull(
                        ticket.team(),
                        "Missing team for ticket " + ticket.id()
                ),
                Ticket::description,
                (oldValue, newValue) -> newValue
        ));
```

For `T2`, `Objects.requireNonNull` throws `NullPointerException` with traceable context. In a real system, you can validate and throw a domain `IllegalArgumentException` or return a validation result before constructing the stream. **What matters is rejecting intentionally**, rather than waiting for an incidental collector failure.

### 4.2. Skip records missing a key

If records lacking a key fall outside the report scope:

```java
Map<String, String> descriptionsByTeam = tickets.stream()
        .filter(ticket -> ticket.team() != null)
        .collect(Collectors.toMap(
                Ticket::team,
                Ticket::description,
                (first, later) -> first
        ));

System.out.println(descriptionsByTeam.keySet());
// Contains "backend" and "frontend", without ticket T2.
```

Filtering reduces the number of aggregated records. This decision affects data totals: track dropped records if the business requires accountability or auditing.

### 4.3. Map to a designated fallback key

If the report wants an "Uncategorized" group:

```java
Map<String, Long> countsByTeam = tickets.stream()
        .collect(Collectors.groupingBy(
                ticket -> ticket.team() == null
                        ? "(uncategorized)"
                        : ticket.team(),
                Collectors.counting()
        ));

System.out.println(countsByTeam.get("(uncategorized)")); // 1
```

The fallback key must belong to the data domain and **must not accidentally collide with a real valid key**. If a real team is named `"(uncategorized)"`, the two cases merge together. Use a dedicated key type to distinguish them or a validation policy to prevent that collision.

### 4.4. Represent an absent key as a distinct state

Using `Optional` as a `Map` key can represent missing data without using a `null` key:

```java
import java.util.Optional;

Map<Optional<String>, Long> counts = tickets.stream()
        .collect(Collectors.groupingBy(
                ticket -> Optional.ofNullable(ticket.team()),
                Collectors.counting()
        ));

System.out.println(counts.get(Optional.of("backend"))); // 1
System.out.println(counts.get(Optional.empty()));       // 1
```

`Optional.empty()` is **a non-null key object** representing the group without a team. For long-lived APIs, consider defining a custom key type, such as `TeamKey` with a field distinguishing known vs. unknown, instead of a collision-prone sentinel string.

### 4.5. When you genuinely need to keep a `null` key

If you must remain compatible with a legacy format that prescribes **a `null` key**, use a structure that supports it and operate explicitly:

```java
import java.util.LinkedHashMap;
import java.util.Map;

Map<String, String> legacy = new LinkedHashMap<>();
for (Ticket ticket : tickets) {
    legacy.put(ticket.team(), ticket.description());
}

System.out.println(legacy.containsKey(null)); // true
System.out.println(legacy.get(null));         // Uncategorized
```

`LinkedHashMap` permits a `null` key; with multiple records sharing a key, `put` **overwrites the earlier value with the later one**. That is a *last wins* policy in a sequential loop. Do not assume `Collectors.toMap` or `groupingBy` will preserve `null` keys the same way across all JDKs.

## 5. Four Policies for `null` Values

Suppose `email` is an optional attribute:

```java
List<User> users = List.of(
        new User("u1", "an@example.com"),
        new User("u2", null),
        new User("u3", "chi@example.com")
);
```

Do not call directly:

```java
// Can throw NullPointerException when encountering a null value:
// Map<String, String> byId = users.stream()
//         .collect(Collectors.toMap(User::id, User::email));
```

Even the overload with a merge function does not make `null` a valid value in `toMap`.

### 5.1. Reject missing values

```java
Map<String, String> requiredEmails = users.stream()
        .collect(Collectors.toMap(
                User::id,
                user -> Objects.requireNonNull(
                        user.email(),
                        "Missing email for " + user.id()
                )
        ));
```

This solution fits when email is mandatory; the error surfaces as the terminal `collect` consumes elements.

### 5.2. Exclude records without a value

```java
Map<String, String> knownEmails = users.stream()
        .filter(user -> user.email() != null)
        .collect(Collectors.toMap(User::id, User::email));

System.out.println(knownEmails.containsKey("u2")); // false
```

This policy **does not retain record `u2` in the resulting map**. If the business meaning is "the user exists, but their email is not yet known", use another approach.

### 5.3. Replace `null` with a default value

```java
Map<String, String> emailsWithFallback = users.stream()
        .collect(Collectors.toMap(
                User::id,
                user -> user.email() == null
                        ? "(no email)"
                        : user.email()
        ));

System.out.println(emailsWithFallback.get("u2")); // (no email)
```

The default value must be clearly defined so it is not mistaken for a real email. Substituting a fallback **transforms the information**, so downstream consumers must know it is a placeholder.

### 5.4. Preserve the meaning "key present, value not yet set"

One `toMap`-compatible approach is using `Optional` as the value:

```java
import java.util.Optional;

Map<String, Optional<String>> optionalEmails = users.stream()
        .collect(Collectors.toMap(
                User::id,
                user -> Optional.ofNullable(user.email())
        ));

System.out.println(optionalEmails.containsKey("u2"));      // true
System.out.println(optionalEmails.get("u2").isEmpty());    // true
System.out.println(optionalEmails.containsKey("u4"));      // false
```

In this map, **every `Optional` value is non-null**; `Optional.empty()` indicates the email is absent. Distinguishing an `Optional.empty()` on an existing key from a missing key still requires `containsKey` or guarded access, because `Map.get` returns `null` when no mapping exists.

This is a valid modeling option when three states must be distinguished cleanly, despite the extra wrapper object and type-reading overhead. In large APIs, a record representing domain states can be cleaner than nesting `Optional` everywhere.

### 5.5. When real `null` values must be stored

`HashMap` and `LinkedHashMap` allow `null` values:

```java
Map<String, String> rawEmails = new LinkedHashMap<>();
for (User user : users) {
    rawEmails.put(user.id(), user.email());
}

System.out.println(rawEmails.containsKey("u2")); // true
System.out.println(rawEmails.get("u2"));         // null
```

This policy stores actual `null`s, suitable when legacy data compatibility is required. It demands that map consumers always distinguish `containsKey` from `get`. Do not pick `Collectors.toMap` for this task solely because `HashMap` supports `null`.

## 6. How Do Duplicate Keys and `null` Interact?

Each key in a `Map` has only one mapping at a time. If the input has multiple records sharing a key, you must specify how values are selected or combined:

```java
List<User> updates = List.of(
        new User("u1", "old@example.com"),
        new User("u1", "new@example.com")
);

Map<String, String> latest = updates.stream()
        .collect(Collectors.toMap(
                User::id,
                User::email,
                (previous, current) -> current
        ));

System.out.println(latest.get("u1")); // new@example.com
```

Here the merge function **picks the later value according to the encounter order** of an ordered list processed sequentially. For sources without an encounter order or when "latest" means business time, do not rely on incidental pipeline order: compare timestamps or versions explicitly.

If an update record has `email == null`, the merge function above **cannot rescue** the failure caused by the value mapper returning `null`. First choose a policy from Section 5: reject, skip, substitute, or use `Optional`.

Example of "latest update even when email is missing":

```java
Map<String, Optional<String>> latestUpdates = List.of(
        new User("u1", "old@example.com"),
        new User("u1", null)
).stream().collect(Collectors.toMap(
        User::id,
        user -> Optional.ofNullable(user.email()),
        (previous, current) -> current
));

System.out.println(latestUpdates.get("u1").isEmpty()); // true
```

This is a **last-update-overwrites rule**, where `Optional.empty()` means the update explicitly cleared the email. If `null` means "leave the current field unchanged", the merge function must be written differently:

```java
Map<String, Optional<String>> keepOldWhenMissing = List.of(
        new User("u1", "old@example.com"),
        new User("u1", null)
).stream().collect(Collectors.toMap(
        User::id,
        user -> Optional.ofNullable(user.email()),
        (previous, current) -> current.isPresent() ? current : previous
));

System.out.println(keepOldWhenMissing.get("u1").orElseThrow());
// old@example.com
```

Both outcomes are **technically valid** yet carry different business meanings. Encode the policy explicitly instead of guessing whether `null` means "delete" or "ignore".

## 7. Why Does `groupingBy` Not Automatically Group `null` Keys?

`Collectors.groupingBy(classifier)` uses keys produced by the classifier. In standard JDK implementations, when the classifier returns `null`, the collector throws `NullPointerException` with a message along the lines of "element cannot be mapped to a null key". Even though `HashMap` can hold a `null` key, **`groupingBy` does not provide a contract for `null` group keys**.

```java
// Do not run: there is a ticket with team == null.
// Map<String, List<Ticket>> groups = tickets.stream()
//         .collect(Collectors.groupingBy(Ticket::team));
```

Instead, encode the decision in code:

```java
// Option 1: drop records missing a key.
Map<String, List<Ticket>> knownGroups = tickets.stream()
        .filter(ticket -> ticket.team() != null)
        .collect(Collectors.groupingBy(Ticket::team));

// Option 2: separate into an Optional.empty() key group.
Map<Optional<String>, List<Ticket>> allGroups = tickets.stream()
        .collect(Collectors.groupingBy(
                ticket -> Optional.ofNullable(ticket.team())
        ));

System.out.println(allGroups.get(Optional.empty()).size()); // 1
```

`groupingByConcurrent` is also not a workaround to bypass `null` key checks: its result is typically a `ConcurrentMap`, and `null` grouping keys are unsupported. To support a group for missing information, use a non-null key such as `Optional.empty()` or a defined domain value.

### 7.1. Using `partitioningBy` when there are only two cases

If you only need to split "has team" and "missing team", you can use `partitioningBy`, because the key is a non-null `Boolean`:

```java
Map<Boolean, List<Ticket>> byMissingTeam = tickets.stream()
        .collect(Collectors.partitioningBy(
                ticket -> ticket.team() == null
        ));

System.out.println(byMissingTeam.get(true).size());  // 1: missing team
System.out.println(byMissingTeam.get(false).size()); // 2: has team
```

This keeps both groups without needing a placeholder string. However, it only represents two states; when grouping by specific team values, use `groupingBy` with a non-null classifier.

## 8. `Map.merge` and `computeIfAbsent`: `null` Has Special Semantics Too

Many collectors and map-updating routines rely on `Map.merge`. You must understand the rules of `Map` itself:

```java
Map<String, Integer> counts = new HashMap<>();
counts.merge("java", 1, Integer::sum);
counts.merge("java", 1, Integer::sum);
System.out.println(counts.get("java")); // 2
```

With `merge(key, value, remappingFunction)`:

- The supplied `value` argument **must be non-`null`**.
- If the key has no mapping or currently maps to `null`, `merge` sets the new value without invoking the merge function.
- If the key already has a non-null value, the merge function receives the old and new values.
- If the merge function **returns `null`**, the mapping for that key is **removed**.

```java
Map<String, String> map = new HashMap<>();
map.put("k", null);
map.merge("k", "A", String::concat);
System.out.println(map.get("k")); // A

map.merge("k", "B", (oldValue, newValue) -> null);
System.out.println(map.containsKey("k")); // false: merge removed the mapping

// map.merge("k", null, (a, b) -> a); // NullPointerException
```

Because `null` is a special signal in `merge`, do not return `null` from a merge function to mean "keep the entry with a `null` value". It deletes the mapping.

`computeIfAbsent` also has its own rule: if the key has no mapping or maps to `null`, it invokes the mapping function; if that function returns `null`, the method does not record a new mapping:

```java
Map<String, String> cache = new HashMap<>();
cache.computeIfAbsent("u1", key -> null);
System.out.println(cache.containsKey("u1")); // false
```

Do not equate "no mapping found" with "mapping with a null value" when choosing update APIs.

## 9. Unmodifiable Results and `null` Policies

Unmodifiable map factories generally have contracts that **forbid `null` keys and values**:

```java
import java.util.Map;
import java.util.stream.Collectors;

Map<String, String> fixed = Map.of(
        "u1", "an@example.com",
        "u2", "binh@example.com"
);

Map<String, String> result = users.stream()
        .filter(user -> user.email() != null)
        .collect(Collectors.toUnmodifiableMap(
                User::id,
                User::email
        ));
```

`toUnmodifiableMap` (since Java 10) rejects both `null` keys and `null` values; if keys collide without a merge function, it also throws `IllegalStateException`. `Map.copyOf` (Java 10+) likewise rejects `null` in the source map. `Map.of` (Java 9+) rejects `null` and duplicate keys at creation time.

If you **must** have an unmodifiable map that still contains `null`, you can copy into a `HashMap` and wrap it with `Collections.unmodifiableMap`:

```java
import java.util.Collections;

Map<String, String> legacy = new HashMap<>();
legacy.put(null, "no code");
legacy.put("u1", null);

Map<String, String> readOnly =
        Collections.unmodifiableMap(new HashMap<>(legacy));

System.out.println(readOnly.containsKey(null)); // true
System.out.println(readOnly.containsKey("u1")); // true
// readOnly.put("u2", "x"); // UnsupportedOperationException
```

Copying ensures subsequent edits to `legacy` do not directly affect `readOnly`. However, this is **shallow immutability**: if values are mutable objects, callers can still mutate internal state of those objects. The wrapper does not automatically make data deeply immutable.

## 10. Parallel Execution: Correctness First, Performance Second

A `parallelStream()` pipeline can split the source, accumulate into multiple intermediate maps, and combine them. For `toMap`, merging maps can be costly, especially when many keys collide:

```java
Map<String, Long> eventCounts = List.of(
        "open", "save", "open", "close"
).parallelStream().collect(Collectors.groupingBy(
        event -> event,
        Collectors.counting()
));

System.out.println(eventCounts.get("open")); // 2
```

Do not update an external `HashMap` from multiple threads via `forEach`:

```java
Map<String, String> shared = new HashMap<>();

// Wrong: shared HashMap is unsafe under concurrent updates.
// users.parallelStream().forEach(user ->
//         shared.put(user.id(), user.email()));
```

Several reminders:

1. `Collectors.toMap` does not guarantee that the returned `Map` is thread-safe. `collect` manages intermediate maps per the collector contract; it does not mean external code can mutate the result map concurrently at will.
2. `Collectors.toConcurrentMap` and `groupingByConcurrent` target concurrent results, yet concurrent structures generally **forbid `null` keys and values**. Do not switch to a concurrent collector just to process data with `null`.
3. If the merge function picks the "first" or "last" item, consider encounter order and associativity semantics. For unordered data, use an explicit timestamp/version key when picking "latest".
4. If the source has records with missing data, normalize/filter/validate according to policy before parallel accumulation. A mapper failure may occur on a worker thread and propagate to the terminal operation.
5. Do not assume `parallel()` is faster. Maintaining intermediate maps, merging results, and synchronization can slow down small pipelines; choose parallel execution only after measuring on suitable data.

## 11. Stream Lifecycle and Large Data Sources

`filter`, `map`, and intermediate operations are lazy: they describe processing rules, while `collect` actually consumes the stream. An error from a mapper returning `null` usually surfaces only when the terminal operation runs.

```java
var pipeline = users.stream()
        .map(User::email);
// Pipeline not yet consumed.

// Actual processing occurs only when a terminal operation requests data.
long missing = pipeline.filter(Objects::isNull).count();
System.out.println(missing); // 1
```

Do not reuse `pipeline` after `count()`; a Stream is for single-use consumption only. For resource-backed sources like `Files.lines(path)`, use `try-with-resources` to close the resource:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static Map<String, String> readPairs(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines
                .map(line -> line.split("=", 2))
                .filter(parts -> parts.length == 2)
                .filter(parts -> !parts[0].isBlank())
                .collect(Collectors.toMap(
                        parts -> parts[0],
                        parts -> parts[1],
                        (oldValue, newValue) -> newValue
                ));
    }
}
```

This example forbids blank keys, permits empty string values `""`, and picks the last occurrence when a key repeats. In production applications, the data format must clearly define escaping for `=`, character encoding, malformed lines, and sensitive data handling. `Collectors.toMap` must retain all key/value pairs in memory; do not apply it directly to an infinite source without a terminating limit.

## 12. Runnable Consolidated Example (Java 17+)

The standalone program below demonstrates three different policies: dropping `null`, preserving absence markers with `Optional`, and genuinely storing `null` keys/values in a `LinkedHashMap`.

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Objects;
import java.util.stream.Collectors;

public class NullMapPolicyDemo {
    record User(String id, String team, String email) {}

    public static void main(String[] args) {
        List<User> users = List.of(
                new User("u1", "backend", "an@example.com"),
                new User("u2", null, null),
                new User("u3", "frontend", "chi@example.com")
        );

        // 1. Drop null values: u2 is excluded from the email map.
        Map<String, String> knownEmails = users.stream()
                .filter(user -> user.email() != null)
                .collect(Collectors.toMap(User::id, User::email));
        System.out.println(knownEmails.containsKey("u2")); // false

        // 2. Preserve the "user exists without email" state.
        Map<String, Optional<String>> emailStates = users.stream()
                .collect(Collectors.toMap(
                        User::id,
                        user -> Optional.ofNullable(user.email())
                ));
        System.out.println(emailStates.containsKey("u2"));   // true
        System.out.println(emailStates.get("u2").isEmpty()); // true

        // 3. Group by team, treating missing team as its own group.
        Map<Optional<String>, Long> teamCounts = users.stream()
                .collect(Collectors.groupingBy(
                        user -> Optional.ofNullable(user.team()),
                        Collectors.counting()
                ));
        System.out.println(teamCounts.get(Optional.empty())); // 1

        // 4. When legacy Map compatibility with real nulls is required.
        Map<String, String> legacy = new LinkedHashMap<>();
        for (User user : users) {
            legacy.put(user.team(), user.email());
        }
        System.out.println(legacy.containsKey(null)); // true
        System.out.println(legacy.get(null));         // null

        // 5. Non-null and unmodifiable policy.
        Map<String, String> immutableEmails = users.stream()
                .filter(user -> user.email() != null)
                .collect(Collectors.toUnmodifiableMap(
                        User::id,
                        User::email
                ));
        System.out.println(immutableEmails.size()); // 2
    }
}
```

The program avoids depending on iteration order of maps produced by `toMap`, `groupingBy`, or `toUnmodifiableMap`. It verifies contents using `containsKey`, `get`, and `size`, which are the contracts suited to the demonstration's purpose.

## 13. Policy Selection Table

| Business Requirement | Suggested Policy |
|---|---|
| Key mandatory; missing key is invalid data | Check with `Objects.requireNonNull` or explicit validation |
| Aggregate only records that have a key | `filter(row -> row.key() != null)` |
| Need a separate group for missing keys | Non-colliding fallback key, `Optional.empty()`, or domain key type |
| Must store `null` keys for a legacy protocol | Use `HashMap`/`LinkedHashMap` directly and control overwrite policy |
| Value mandatory; `null` is an error | Validate before `toMap` or reject inside the value mapper |
| Drop records when value is missing | `filter(row -> row.value() != null)` |
| Missing value must be distinct from absent key | `Map<K, Optional<V>>` or domain status type |
| Must store real `null` values | Use a `null`-supporting map and distinguish `containsKey` from `get` |
| Duplicate keys where only the latest matters | Merge by explicit timestamp/version; do not guess from unguaranteed order |
| Unmodifiable result forbidding `null` | `Collectors.toUnmodifiableMap` or `Map.copyOf` |
| Unmodifiable result that still needs `null` | Wrap a copy with `Collections.unmodifiableMap` and note shallow immutability |

## 14. Common Mistakes

| Misconception | Consequence | Fix |
|---|---|---|
| "`HashMap` accepts `null`, so `toMap` accepts all `null`s too" | `toMap` has its own contract; a `null` value mapper can throw | Choose a `null` policy before the collector |
| "`groupingBy` can group using `null` keys" | A classifier returning `null` usually throws `NullPointerException` | Use `Optional.empty()` or a fallback key |
| "Adding a merge function lets `toMap`'s value mapper return `null`" | Merge does not handle `null` incoming values | Convert `null` to a non-null value beforehand |
| "`get(k) == null` means the key does not exist" | Confuses a missing key with a stored `null` | Check `containsKey` |
| "`Map.merge(k, v, fn)` can accept `v == null`" | Throws `NullPointerException` | Only pass non-null values |
| "Returning `null` from a remapping function stores `null`" | `Map.merge` deletes the mapping | Use an explicit `null`-storing policy |
| "`Map.copyOf` freezes even maps containing `null`" | `null` is rejected | Remove/normalize `null` or use an appropriate wrapper |
| "`parallelStream().forEach(map::put)` is a fast way to build a map" | Shared map is not thread-safe | Use a collector or properly designed concurrent structure |
| "Replacing a `null` key with any string is always safe" | May collide with a real key and merge wrongly | Use a key type that cleanly represents missingness |
| "No email means no user" | Loses distinction between existing record and missing attribute | Use `Optional`/explicit state or keep a null-valued mapping |

## 15. Self-Check

1. **Can `HashMap` contain a `null` key?** Yes, but that does not guarantee `Collectors.toMap` or `groupingBy` accepts `null` keys.
2. **Why is `map.get("u2") == null` insufficient to conclude `u2` does not exist?** Because `u2` may be mapped to `null`; you also need `containsKey`.
3. **Is `Collectors.toMap(User::id, User::email)` safe when email can be `null`?** No. You must choose a handling policy before collecting.
4. **To drop records with `team == null`, what step goes before `toMap`?** `filter(user -> user.team() != null)`.
5. **To still group records with `team == null` using `groupingBy`, how do you do it?** Use a classifier returning `Optional.ofNullable(team)` or a non-null fallback key.
6. **Does `toUnmodifiableMap` allow `null` keys or values?** No; it rejects both.
7. **What does `Map.merge` do when the remapping function returns `null`?** Removes the mapping for that key.
8. **When `computeIfAbsent` gets `null` from the mapping function, what happens?** It does not create a new mapping if the key is absent or mapped to `null`.
9. **Why can a placeholder like `"(uncategorized)"` be dangerous?** Because it may collide with a real group name, merging two semantically different datasets.
10. **To preserve the state "user exists without email" while still using `toMap`, what value type should you choose?** You can use `Optional<String>`, with `Optional.empty()` representing a missing email.
11. **With duplicate keys and an update record having a `null` value, what must you decide?** Whether `null` means "delete value", "ignore update", "use default", or error; the merge function must implement that exact policy.
12. **How do you create a read-only map that still contains `null` for legacy protocol compatibility?** Copy into a `HashMap` and wrap with `Collections.unmodifiableMap`; note this is shallow immutability.

**Takeaway:** `null` in **keys** and `null` in **values** represent different problems. Before calling `collect` into a `Map`, decide whether the application will **reject, skip, substitute, explicitly model absence, or store `null` directly** in each case. Then choose the right collector and map type, duplicate-key handling rules, and ordering/mutability contracts. Doing so ensures declarative pipelines produce predictable results even with incomplete data and parallel execution.
