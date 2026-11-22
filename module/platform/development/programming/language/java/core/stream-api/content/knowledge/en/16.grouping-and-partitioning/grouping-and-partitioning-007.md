# Handling Null Grouping Keys and Empty Groups

In the Java Stream API, `Collectors.groupingBy` can turn multiple records into a `Map<K, List<T>>`, while `Collectors.partitioningBy` splits them into two branches, `true` and `false`. However, real-world data often has **missing grouping keys** or an **expected group that receives no elements**. Without a clear handling policy, a report may throw exceptions, omit groups, display wrong counts, or confuse "no data" with "group exists but no matching records".

This lesson belongs to the **Grouping and Partitioning** chapter of the `JAVA_STREAM_API` module. It focuses on the contract of `groupingBy` when the classifier returns `null`, how to represent absent grouping values, distinguishing groups that **do not appear** from groups that are **empty due to downstream filtering**, how `partitioningBy` differs, and the impact of operation ordering, parallel sources, resources, and performance. These concepts connect directly to lazy pipelines, `filter`, `map`, and `collect`.

Basic examples use Java 8 syntax. Sections using `Collectors.filtering` explicitly note that they require **Java 9 or later**.

## 1. Distinguishing Three Easily Confused States

Suppose we manage tasks across `"Backend"`, `"Frontend"`, and `"QA"` teams.

There are at least three distinct situations:

1. **A task's key is `null`**: the task has not been assigned to a group. This is an issue with the value returned by the *classifier*.
2. **There are no tasks belonging to `"QA"`**: if you only collect from the task list, `groupingBy` normally **does not create a `"QA"` key**.
3. **There are tasks belonging to `"Frontend"`, but none satisfy a filter in a downstream collector**: the `"Frontend"` key can still appear with an **empty list** or a `count = 0` result.

These three states are not equivalent:

```text
Input data
   |
   +-- Task(team = null) ------------> classifier has no key
   |
   +-- No Task(team=QA) exists ------> Map has no QA key
   |
   +-- Task(team=Frontend)
            |
            +-- downstream filter drops all --> Frontend = []
```

They require different handling strategies. `Optional.empty()`, an absent Map key, and `Collections.emptyList()` are not the same concept.

## 2. How Does groupingBy Work?

A common expression:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<String> words = Arrays.asList("ant", "apple", "bear", "bird");

Map<Character, List<String>> byFirstLetter = words.stream()
        .collect(Collectors.groupingBy(text -> text.charAt(0)));

System.out.println(byFirstLetter.get('a')); // [ant, apple]
System.out.println(byFirstLetter.get('b')); // [bear, bird]
System.out.println(byFirstLetter.containsKey('c')); // false
```

`groupingBy(classifier)` applies the `classifier` function to each element that passed preceding intermediate operations, then routes that element to the corresponding group's accumulator. By default, the downstream collector is `toList()`.

You can visualize the logical contract as:

```text
Stream<T>
   │
   ├── classifier(t) -> k1 -> accumulate group k1
   ├── classifier(t) -> k2 -> accumulate group k2
   └── classifier(t) -> k1 -> accumulate group k1
                              │
                              ▼
                         Map<K,List<T>>
```

The Map contains only the keys **that actually appeared among classified elements**. `groupingBy` does not know the full list of valid keys in the business domain and does not automatically create groups for unseen keys.

## 3. Null Keys: groupingBy Does Not Accept a Classifier Returning null

This is the most common error:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

final class Task {
    private final String id;
    private final String team;
    private final boolean done;

    Task(String id, String team, boolean done) {
        this.id = id;
        this.team = team;
        this.done = done;
    }

    String id()   { return id; }
    String team() { return team; }
    boolean done() { return done; }
}

List<Task> tasks = Arrays.asList(
        new Task("T01", "Backend", true),
        new Task("T02", null, false),
        new Task("T03", "Frontend", false),
        new Task("T04", "Backend", false)
);
```

If you run:

```java
// Error example: intentionally illustrates classifier returning null.
Map<String, List<Task>> invalid = tasks.stream()
        .collect(Collectors.groupingBy(Task::team));
```

The pipeline will throw `NullPointerException` when `Task::team` returns `null`. The exception message on many JDKs is `element cannot be mapped to a null key`.

**Important:** even though some `Map` implementations (such as `HashMap`) support **`null` keys**, `Collectors.groupingBy` still does not accept **`null` classification results**. Passing `HashMap::new` to the overload with `mapFactory` **does not bypass this rule**.

Similarly, `Collectors.groupingByConcurrent` must not be used to handle `null` grouping keys; it also requires valid classifier keys, and common `ConcurrentMap` implementations reject `null` keys.

### Distinguishing null source elements from null keys

A `List<Task>` can also contain **a `null` element itself**, causing the method reference `Task::team` to throw `NullPointerException` before returning any key. That is a different input issue from a valid `Task` object whose `team` field is `null`.

If the list may contain null `Task` entries:

```java
import java.util.Objects;

Map<String, List<Task>> safeInput = tasks.stream()
        .filter(Objects::nonNull)
        .filter(task -> task.team() != null)
        .collect(Collectors.groupingBy(Task::team));
```

Here, the two filter steps address two different causes: null records and null keys. Using `filter(Objects::nonNull)` alone **is not enough** to exclude tasks with a null team.

## 4. Policy A: Dropping Records Without a Key

If report requirements only include assigned tasks, you can exclude records with `team == null` right before `groupingBy`:

```java
Map<String, List<Task>> assignedOnly = tasks.stream()
        .filter(task -> task.team() != null)
        .collect(Collectors.groupingBy(Task::team));

System.out.println(assignedOnly.get("Backend").size());  // 2
System.out.println(assignedOnly.get("Frontend").size()); // 1
System.out.println(assignedOnly.containsKey("QA"));      // false
```

Pros: simple, clear intent, avoids representing a missing-key group. Cons: **task T02 no longer appears in this report**.

Only apply a filtering policy when dropping data is an intentional business decision. If the system needs auditing, unassigned task counts, or missing-data warnings, do not silently drop those tasks.

## 5. Policy B: Using an Explicit Placeholder Key

If you want to keep unassigned tasks as well, convert `null` into a **non-null** key:

```java
private static final String UNASSIGNED = "[CHUA_PHAN_NHOM]";

// Illustrated within the scope of the class holding constant UNASSIGNED:
Map<String, List<Task>> byTeam = tasks.stream()
        .collect(Collectors.groupingBy(
                task -> task.team() == null
                        ? UNASSIGNED
                        : task.team()
        ));

System.out.println(byTeam.get(UNASSIGNED).size()); // 1
System.out.println(byTeam.get("Backend").size());   // 2
```

This is convenient when exporting reports or rendering UIs. However, **the placeholder key must not collide with a real key value**. If users can actually create a team named `"[CHUA_PHAN_NHOM]"`, the two groups will be merged into one.

Better options for production projects include:

- Reserving an internal identifier that cannot be used as a team ID, and translating it to a UI label only at the presentation layer.
- Using an enum or domain key type with a distinct `UNASSIGNED` case.
- Using `Optional<String>` as the key so you do not have to invent a sentinel string.

Do not arbitrarily pick `""` if the empty string is also a data value that needs to be distinguished.

## 6. Policy C: Using Optional as the Map Key

`Optional.ofNullable` converts a `null` team into `Optional.empty()`. Crucially: **`Optional.empty()` is a non-null Optional object**, so it can be used as a key in `groupingBy`.

```java
import java.util.Optional;

Map<Optional<String>, List<Task>> optionalGroups = tasks.stream()
        .collect(Collectors.groupingBy(
                task -> Optional.ofNullable(task.team())
        ));

System.out.println(
        optionalGroups.get(Optional.empty()).size()
); // 1

System.out.println(
        optionalGroups.get(Optional.of("Backend")).size()
); // 2
```

This model clearly represents both cases:

- `Optional.of("Backend")`: team key with a value.
- `Optional.empty()`: team is absent.

Because `Optional` implements `equals`/`hashCode` properly, multiple Optionals wrapping the same team are treated as the same key. For an intermediate Map used internally during processing, this preserves the distinction between a missing key and a real team name.

In return, the output API type becomes `Map<Optional<String>, List<Task>>`, so callers reading the Map must handle `Optional` explicitly. You do not have to expose this key type directly to JSON, SQL, or UI; convert it into a domain-friendly report model at system boundaries.

### When null must be treated as a data error

Sometimes a team is mandatory, and a missing team is an **error** rather than a group. Validating before or during collection makes that explicit:

```java
import java.util.Objects;

Map<String, List<Task>> strictGroups = tasks.stream()
        .collect(Collectors.groupingBy(task ->
                Objects.requireNonNull(
                        task.team(),
                        "Task " + task.id() + " has no team"
                )
        ));
```

On the sample data, this intentionally throws `NullPointerException` with a business message. If the system needs to report multiple invalid records in a single import pass, use a separate validation/error-collection step instead of failing on the first error.

## 7. Empty Groups: groupingBy Does Not Auto-Generate Keys

The source contains only Backend and Frontend teams:

```java
Map<String, Long> counts = tasks.stream()
        .filter(task -> task.team() != null)
        .collect(Collectors.groupingBy(
                Task::team,
                Collectors.counting()
        ));

System.out.println(counts.get("Backend"));      // 2
System.out.println(counts.get("Frontend"));     // 1
System.out.println(counts.containsKey("QA"));   // false
System.out.println(counts.get("QA"));           // null
```

The `null` result of `counts.get("QA")` here means **the Map does not contain the QA key**, not that the classifier was allowed to return null. Those are two completely different events.

Do not confuse this with:

```java
counts.getOrDefault("QA", 0L) // returns 0L, but DOES NOT add the QA key
```

`getOrDefault` only returns a fallback value for that lookup. After this call, `counts.containsKey("QA")` is still `false`.

Similarly:

```java
Map<String, List<Task>> groups = tasks.stream()
        .filter(task -> task.team() != null)
        .collect(Collectors.groupingBy(Task::team));

List<Task> qa = groups.getOrDefault(
        "QA",
        java.util.Collections.emptyList()
);

System.out.println(qa.isEmpty());             // true
System.out.println(groups.containsKey("QA")); // false
```

`qa` here is a fallback list, not a new group stored in the Map.

## 8. Always Showing All Expected Groups? Add the Business Domain Key Set

If a report must include Backend, Frontend, and QA even when there are no tasks, we must supply the **list of expected teams** from the business requirements. The Stream of tasks cannot know this list on its own.

### Approach 1: Normalize the Map after collect

```java
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<String> expectedTeams = Arrays.asList(
        "Backend", "Frontend", "QA"
);

Map<String, List<Task>> grouped = tasks.stream()
        .filter(task -> task.team() != null)
        .collect(Collectors.groupingBy(Task::team));

Map<String, List<Task>> report = new LinkedHashMap<>();

for (String team : expectedTeams) {
    report.put(
            team,
            grouped.getOrDefault(
                    team,
                    java.util.Collections.emptyList()
            )
    );
}

System.out.println(report.get("QA").size()); // 0
System.out.println(report.containsKey("QA")); // true
```

This approach has two advantages:

1. Teams appear in the order defined by `expectedTeams` thanks to `LinkedHashMap`.
2. Groups with no elements are explicitly represented by an empty list.

**Note:** `Collections.emptyList()` is an unmodifiable list. If the report needs elements added after collection, create `new ArrayList<>()` for empty groups rather than calling `add` on an immutable list. Do not mutate the contents of these lists while the result is being read across multiple threads without synchronization.

If you also want to retain teams outside the expected set, define an explicit policy for adding them to the report. The loop above only builds the report for teams in `expectedTeams`.

### Approach 2: Only populate missing groups

```java
Map<String, List<Task>> mutableGroups = tasks.stream()
        .filter(task -> task.team() != null)
        .collect(Collectors.groupingBy(Task::team));

for (String team : expectedTeams) {
    mutableGroups.computeIfAbsent(
            team,
            key -> new java.util.ArrayList<Task>()
    );
}

System.out.println(mutableGroups.containsKey("QA")); // true
System.out.println(mutableGroups.get("QA").isEmpty()); // true
```

This adds missing groups directly onto the collected Map while preserving existing groups. However, the Map returned by `groupingBy`'s default overload **does not guarantee a concrete type, mutability, or iteration order**. If the project relies on mutating the Map afterward as part of a reliable contract, specify a `mapFactory` to create a known mutable Map:

```java
Map<String, List<Task>> mutableGroups = tasks.stream()
        .filter(task -> task.team() != null)
        .collect(Collectors.groupingBy(
                Task::team,
                LinkedHashMap::new,
                Collectors.toList()
        ));

for (String team : expectedTeams) {
    mutableGroups.computeIfAbsent(
            team,
            key -> new java.util.ArrayList<Task>()
    );
}
```

If you want the **exact order of `expectedTeams`** even when original groups are encountered in a different order, building a new `LinkedHashMap` from the expected key list as in **Approach 1** expresses the intent more clearly.

## 9. Filtering Before Grouping vs. Filtering Inside Grouping

This is the subtlest aspect of empty groups.

Suppose we want to group tasks by team while keeping only **completed tasks**. The data has a Frontend team, but none of Frontend's tasks are completed.

### Upstream filtering: groups can disappear

```java
Map<String, List<Task>> doneOnly = tasks.stream()
        .filter(task -> task.team() != null)
        .filter(Task::done)
        .collect(Collectors.groupingBy(Task::team));

System.out.println(doneOnly.containsKey("Backend"));  // true
System.out.println(doneOnly.containsKey("Frontend")); // false
```

Because only tasks with `done == true` reach `groupingBy`, the classifier **never sees** the Frontend key. There is no way for the Collector to infer that Frontend is a group that should be displayed.

### Downstream filtering: groups are preserved even when empty

Since **Java 9**, `Collectors.filtering(predicate, downstream)` allows checking each element **after its group has been identified**:

```java
Map<String, List<Task>> doneByTeam = tasks.stream()
        .filter(task -> task.team() != null)
        .collect(Collectors.groupingBy(
                Task::team,
                Collectors.filtering(
                        Task::done,
                        Collectors.toList()
                )
        ));

System.out.println(doneByTeam.get("Backend").size());  // 1
System.out.println(doneByTeam.get("Frontend").size()); // 0
System.out.println(doneByTeam.containsKey("Frontend")); // true
System.out.println(doneByTeam.containsKey("QA"));       // false
```

The difference is not merely performance; **it is the semantics of the report**.

```text
Before grouping:
  source → filter(done) → groupingBy(team)
                         Frontend no longer appears

In downstream:
  source → groupingBy(team, filtering(done, toList()))
                         Frontend is created with []
                         QA still does not exist if there is no Task for it
```

**Condition:** even with `Collectors.filtering`, the classifier is still invoked first to form the group. It must still return a non-null key. Therefore, `filter(task -> task.team() != null)` or a key normalization step is still required if the source allows null teams.

### Same behavior with counting

```java
Map<String, Long> doneCounts = tasks.stream()
        .filter(task -> task.team() != null)
        .collect(Collectors.groupingBy(
                Task::team,
                Collectors.filtering(
                        Task::done,
                        Collectors.counting()
                )
        ));

System.out.println(doneCounts.get("Backend"));  // 1
System.out.println(doneCounts.get("Frontend")); // 0
System.out.println(doneCounts.containsKey("QA")); // false
```

Here `Frontend → 0L` is an actual entry in the Map. That value is distinct from the absence of the QA key.

### Approach for Java 8

Java 8 **does not have** `Collectors.filtering`. If you want to preserve empty groups when no element matches a condition, you can group all tasks that have valid keys first, and then filter each list:

```java
Map<String, List<Task>> allGroups = tasks.stream()
        .filter(task -> task.team() != null)
        .collect(Collectors.groupingBy(Task::team));

Map<String, List<Task>> doneGroups = new java.util.HashMap<>();

for (Map.Entry<String, List<Task>> entry : allGroups.entrySet()) {
    List<Task> doneTasks = entry.getValue().stream()
            .filter(Task::done)
            .collect(Collectors.toList());
    doneGroups.put(entry.getKey(), doneTasks);
}

System.out.println(doneGroups.containsKey("Frontend")); // true
System.out.println(doneGroups.get("Frontend").isEmpty()); // true
```

This approach is easy to understand, but requires intermediate lists for each group and a second pass to filter them. When Java 9+ is available, `Collectors.filtering` is usually more direct.

## 10. partitioningBy: Always Has Both true and false Keys

`Collectors.partitioningBy(predicate)` solves a specialized problem: splitting by **a single boolean condition**. The result has both `Boolean.TRUE` and `Boolean.FALSE` keys, **even when one branch has no elements**.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<Integer> scores = Arrays.asList(70, 85, 92);

Map<Boolean, List<Integer>> partitions = scores.stream()
        .collect(Collectors.partitioningBy(score -> score >= 50));

System.out.println(partitions.get(true));   // [70, 85, 92]
System.out.println(partitions.get(false));  // []
System.out.println(partitions.containsKey(false)); // true
```

Even on a **completely empty** Stream, the partitioning collector still returns two entries:

```java
Map<Boolean, List<Integer>> emptyPartitions =
        java.util.stream.Stream.<Integer>empty()
                .collect(Collectors.partitioningBy(n -> n > 0));

System.out.println(emptyPartitions.size());      // 2
System.out.println(emptyPartitions.get(true));   // []
System.out.println(emptyPartitions.get(false));  // []
```

Conversely, `groupingBy` with a Boolean classifier **does not guarantee both keys** when one branch has no elements:

```java
Map<Boolean, List<Integer>> groupedBoolean = scores.stream()
        .collect(Collectors.groupingBy(score -> score >= 50));

System.out.println(groupedBoolean.containsKey(true));  // true
System.out.println(groupedBoolean.containsKey(false)); // false
```

`groupingBy` only creates groups that have data, whereas `partitioningBy` has a contract of **exactly two partitions**, each holding its downstream result.

### partitioningBy with downstream counting

```java
Map<Boolean, Long> countsByPassing = scores.stream()
        .collect(Collectors.partitioningBy(
                score -> score >= 50,
                Collectors.counting()
        ));

System.out.println(countsByPassing.get(true));  // 3
System.out.println(countsByPassing.get(false)); // 0
```

If the source is empty, both partitions hold `0L`. A zero count on a partition is not a missing key.

**Limitation:** `partitioningBy` only applies when the problem naturally splits into **two branches** of the same predicate. If you need three or more groups such as Backend, Frontend, QA, you must use `groupingBy` and explicitly fill in missing groups if needed.

## 11. Nested Grouping: Outer Group Can Exist While Inner Group Is Missing

A report may need to group by team and then by status. At the inner grouping level, the absence of a status also causes its corresponding key to be missing.

Example:

```java
Map<String, Map<Boolean, List<Task>>> nestedGrouping = tasks.stream()
        .filter(task -> task.team() != null)
        .collect(Collectors.groupingBy(
                Task::team,
                Collectors.groupingBy(Task::done)
        ));

System.out.println(
        nestedGrouping.get("Frontend").containsKey(false)
); // true

System.out.println(
        nestedGrouping.get("Frontend").containsKey(true)
); // false
```

If each team that appears must include both `true` and `false` statuses, replace the downstream `groupingBy(Task::done)` with `partitioningBy(Task::done)`:

```java
Map<String, Map<Boolean, List<Task>>> nestedPartition = tasks.stream()
        .filter(task -> task.team() != null)
        .collect(Collectors.groupingBy(
                Task::team,
                Collectors.partitioningBy(Task::done)
        ));

System.out.println(nestedPartition.get("Frontend").get(true));  // []
System.out.println(nestedPartition.get("Frontend").get(false).size()); // 1
```

This **only populates both partitions inside teams that appeared**. Team QA is still absent from the outer Map. To make QA appear, you need the expected team list and an outer-key population step as shown in Section 8.

## 12. Parallel Streams, groupingByConcurrent, and Ordering Issues

When using `parallelStream()`, regular `groupingBy` may allocate multiple intermediate Maps and merge them. `groupingByConcurrent` provides a **concurrent and unordered** Collector, which can fit when you only need to group by key and do not care about encounter order.

```java
import java.util.concurrent.ConcurrentMap;

ConcurrentMap<String, Long> concurrentCounts = tasks.parallelStream()
        .filter(task -> task.team() != null)
        .collect(Collectors.groupingByConcurrent(
                Task::team,
                Collectors.counting()
        ));

System.out.println(concurrentCounts.get("Backend")); // 2
```

Several rules must be maintained:

- `groupingByConcurrent` **does not allow the classifier to return null**; you still must filter, normalize, or convert to a non-null Optional key.
- Keys with no elements still **do not appear automatically**.
- The collector is `UNORDERED`, so if the downstream builds a List, **element order within each group is not guaranteed** as it would be when collecting with encounter order.
- `ConcurrentMap` does not mean every `List` or mutable object inside the map is automatically safe for concurrent modification **after** collection.
- Do not assume parallel/concurrent is always faster: key distribution, contention, combination cost, and source size determine actual performance.

If a report must preserve task order by date or input order, explicitly define a sort key and use an appropriate collector/order, or sort deterministically after collection. Do not rely on an iteration order not guaranteed by the API.

## 13. Handling Missing Keys and Missing Groups in Statistics

With `Collectors.counting`, `summingLong`, `averagingInt`, or `mapping`, a missing group means **no element mapped to that group**. On the other hand, if the group was created first and the downstream filtered everything out, the downstream's default value is a distinct result:

| Situation | Example result | `containsKey`? |
| --- | --- | --- |
| No Task belongs to QA | `get("QA") == null` | No |
| Frontend exists, downstream filters out all Tasks | `get("Frontend").isEmpty()` | Yes |
| Frontend exists, downstream `filtering` then `counting` | `get("Frontend") == 0L` | Yes |
| `partitioningBy` has no element matching predicate | `get(true).isEmpty()` | Yes |
| `partitioningBy(..., counting())` on empty Stream | `get(true) == 0L` and `get(false) == 0L` | Yes for both |
| Key is `Optional.empty()` | Group containing Tasks without a team | Yes, if a Task with null team was seen |

**Do not use default values to infer whether original data existed.** For example, `summingLong` can return 0 because positive and negative values cancel out, not necessarily because the group was empty. Similarly, `getOrDefault` can mask the fact that a key is genuinely absent from the Map if the caller does not check `containsKey`.

For reports that need to distinguish three states (`MISSING`, `EMPTY`, `NON_EMPTY`), design an explicit DTO or report enum instead of inferring from `null` and list sizes. For instance, a completely empty `Map` is a different fact from a Map with three keys where each key holds an empty list.

## 14. Stream Lifecycle and Memory Cost

`groupingBy`, `partitioningBy`, and their variants are all **terminal collect** operations. They consume the pipeline once; you cannot reuse the same Stream instance after `collect`.

For resource-backed sources such as `Files.lines`, `collect` **does not automatically close the source Stream**. Use `try-with-resources` where the source is owned:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static Map<String, Long> countNonEmptyLinesByPrefix(Path path)
        throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines
                .filter(line -> !line.isEmpty())
                .collect(Collectors.groupingBy(
                        line -> line.substring(0, 1),
                        Collectors.counting()
                ));
    }
}
```

The example assumes every non-empty line has a first character; `filter` here prevents `substring(0, 1)` from failing on empty strings. Read errors occurring during lazy traversal can surface as `UncheckedIOException`, and `try-with-resources` still guarantees the opened Stream is closed.

If all elements are retained in `Map<K,List<T>>`, memory can grow roughly proportionally to the number of input elements plus Map and List overhead. When only counts/sums are needed, using downstream `counting`/`summingLong` avoids retaining all records, though it still incurs cost proportional to the number of groups. When populating thousands of expected groups, also consider Map size and empty container overhead.

## 15. Combined Example: Team Report with Both Unassigned and Empty Groups

Report requirements:

- Tasks with `team == null` must appear in the **Unassigned** group.
- Backend, Frontend, and QA teams **must all be present**, even when they have no tasks.
- Each group displays only completed tasks, yet **the group does not disappear** if it has no completed tasks.
- Display order must be fixed: Backend, Frontend, QA, Unassigned.

This uses Java 9+ for downstream `Collectors.filtering`:

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

String unassigned = "[CHUA_PHAN_NHOM]"; // reserved code, does not collide with real teams
List<String> teamOrder = Arrays.asList(
        "Backend", "Frontend", "QA", unassigned
);

// tasks is the Task list created in Section 3.
Map<String, List<Task>> collected = tasks.stream()
        .collect(Collectors.groupingBy(
                task -> task.team() == null
                        ? unassigned
                        : task.team(),
                Collectors.filtering(
                        Task::done,
                        Collectors.toList()
                )
        ));

Map<String, List<Task>> report = new LinkedHashMap<>();

for (String team : teamOrder) {
    report.put(
            team,
            collected.getOrDefault(team, Collections.emptyList())
    );
}

System.out.println(report.get("Backend").size());  // 1
System.out.println(report.get("Frontend").size()); // 0
System.out.println(report.get("QA").size());       // 0
System.out.println(report.get(unassigned).size()); // 0
System.out.println(report.containsKey("QA"));      // true
```

Key points:

1. The classifier **never returns null** thanks to the reserved key for unassigned tasks.
2. `Collectors.filtering` retains observed groups even when a group has no completed tasks.
3. `LinkedHashMap` constructs the report in the desired order and adds the QA group that never appeared in the source.
4. `Collections.emptyList()` is used only as a read-only value for groups with no elements, not for updates via `add`.
5. The report includes only groups in `teamOrder`. If the source contains another valid team, define an additional display policy or treat it as out-of-config data.

If additional statistics are needed—such as total tasks, total completed tasks, and tasks skipped due to missing teams—design a report or downstream collector that captures all of them. Do not try to reverse-engineer the initial total task count from a `Map<String,List<Task>>` that contains only completed tasks.

## 16. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `groupingBy(Task::team)` when `team == null` | Throws `NullPointerException` | Filter, replace with a reserved code, or group by `Optional.ofNullable` |
| Changing `groupingBy` to `HashMap::new` to accept null keys | Does not bypass `groupingBy`'s classifier contract | Ensure the classifier returns non-null keys |
| Filtering only `Objects::nonNull` on Tasks | Can still encounter null team keys | Check `task.team() != null` separately |
| Dropping Tasks without a team when the report needs to count them | Loss of business data | Choose a policy that retains an unassigned group |
| Using a placeholder string that can collide with a real team name | Accidentally merges two groups | Use a reserved code, enum/key type, or `Optional` |
| Using `groupingBy` and expecting every configured team to appear | Unseen groups have no key | Populate keys from the expected team list |
| Calling `getOrDefault("QA", emptyList())` and assuming QA is now in the Map | No new key is added | Build a new report Map or use `computeIfAbsent` |
| Filtering `done` before `groupingBy` when incomplete groups must remain | Groups disappear | Use downstream `Collectors.filtering` on Java 9+ |
| Using `Collectors.filtering` and expecting unseen groups to be created | Downstream does not know domain keys automatically | Supply the expected key list |
| Using `groupingBy` on Boolean and expecting both true/false | Branch with no elements is missing | Use `partitioningBy` |
| Using `groupingByConcurrent` to preserve element order within groups | Collector is unordered | Choose an appropriate collector/ordering |
| Treating `0` as proof a group had no Tasks | Sum can be 0 due to arithmetic | Check `containsKey` and retain sufficient statistics |
| Assuming terminal `collect` closes file sources | Resources remain open | Use `try-with-resources` |

## 17. Self-Check Questions

1. Does `groupingBy` accept a classifier returning `null` when using `HashMap::new`? **No**; it still throws `NullPointerException`.
2. What does `Optional.ofNullable(team)` do? **Creates a non-null Optional key**; `Optional.empty()` represents an absent team.
3. When no Task belongs to QA, does `groupingBy` create `QA → []`? **No**; it does not auto-generate the QA key.
4. Does `map.getOrDefault("QA", emptyList())` add QA to the Map? **No**; it only returns a fallback list.
5. Why does filtering `Task::done` **before** grouping differ from `Collectors.filtering(Task::done, toList())` **inside** grouping? **Because** pre-filtering can eliminate all elements of a group and make its key vanish, whereas downstream filtering keeps groups that were classified.
6. Which Java version introduced `Collectors.filtering`? **Java 9**; on Java 8 you can group first and then filter the lists.
7. How many keys does `partitioningBy` return on an empty Stream? **Two**: `true` and `false`, each with an empty downstream result.
8. Does `groupingBy(x -> predicate(x))` always return two Boolean keys? **No**; it creates keys only for branches that had elements.
9. Does `groupingBy(team, partitioningBy(done))` add an unseen team to the outer Map? **No**; it only guarantees both partitions **inside teams that have data**.
10. Does `groupingByConcurrent` allow a classifier to return null? **No**; and it does not guarantee encounter order.
11. Why should an empty list and an absent key not be treated as the same state? **Because** a report may need to distinguish a group that was observed with no valid elements from a group that never appeared.
12. To always output Backend, Frontend, and QA, what extra information is required? **The list of expected teams**, and then building/populating the result Map from that list.

**Guiding principle:** Explicitly decide whether **keys with missing data are dropped, rejected with an error, or placed into a dedicated group**, and whether **groups with no elements should disappear or be kept with an empty result**. `groupingBy` does not accept null classifier keys and does not auto-generate unseen groups; `partitioningBy` always provides both Boolean keys; `Collectors.filtering` keeps observed groups but does not create groups outside the observed data. Get the semantics right first before optimizing parallelism, memory, and performance.
