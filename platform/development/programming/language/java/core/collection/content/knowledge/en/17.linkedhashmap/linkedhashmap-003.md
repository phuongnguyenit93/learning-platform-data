# Access-Order Mode and Operations That Change Order

## 1. When "Reading Data" Also Changes Usage History

Suppose a program keeps recently used items. After adding `a`, `b`, `c`, the user reads `a` again. If we want to know which item has gone longest without being used, the insertion order `a,b,c` is no longer enough: `a` was just used, while `b` is now the least recently accessed item.

`LinkedHashMap` has an **access-order mode** to maintain this order.

In that mode, the iteration sequence runs from the least recently accessed entry to the most recently accessed entry. An operation counted as an access can move the relevant entry to the end of the sequence.

The key point to learn is not just "get moves a key to the end." You must know:

- Which operations count as an access.
- Which conditions cause an operation to succeed, be skipped, insert a new entry, or remove a mapping.
- When data does not change, yet the order still changes.
- Why accessing during iteration can invalidate an iterator.

This lesson examines APIs available in Java 17. Execution-path explanations use the OpenJDK 17u source; programs are compiled with `--release 17` and run on OpenJDK 24.0.2. The compiler flag selects the target API/bytecode level and does not change the JVM version running the program.

## 2. Enabling the Mode and Reading Both Ends of the Sequence Correctly

Create the map using the three-argument constructor:

```java
Map<String, Integer> recent = new LinkedHashMap<>(16, 0.75f, true);
```

This is an illustrative declaration in a context where `Map` and `LinkedHashMap` are already imported.

| Parameter | Role |
| --- | --- |
| 16 | Requested initial capacity |
| 0.75f | Load factor |
| true | Selects access-order |

If the last parameter is `false`, or if a standard constructor such as `new LinkedHashMap<>()` is used, the map uses insertion order.

### 2.1. Older at the Head, Newer at the Tail

Given the sequence `a,b,c`:

```text
head                                         tail
least recently accessed          →  most recently accessed
a                 → b       → c
```

A successful `get("a")`:

```text
before: a → b → c
after:  b → c → a
```

You do not need to re-insert `a` or change its value to record this access.

### 2.2. Relative Order, Not a Counter or Clock

Access-order does not store access counts to sort by frequency. A key read once right now can stand behind a key read a thousand times earlier.

It also does not create expiration timestamps on its own. An entry being at the head only indicates its relative position in the access history recorded by the map, not how many seconds old the entry is.

### 2.3. An Access Does Not Always Mean the Sequence Looks Different

If `a` is already at the tail, `get("a")` is still a valid access, but there is no newer position to move it to. The observed sequence may remain unchanged.

Therefore, distinguish two questions:

1. Does the operation belong to the category that accesses an entry?
2. Are the orders before and after actually different?

In the OpenJDK 17u implementation, `afterNodeAccess` only relinks nodes when the entry is not already at the tail. Do not rely on this detail to assume an iterator "might still be usable" after some `get` calls.

## 3. Execution Model: Locate the Entry, Then Update Its Position

The hash table still handles key lookup. Access-order does not turn `get` into a scan from the head of the list to find an element.

When an execution path determines that an entry is accessed, the ordering mechanism can:

1. Unlink the entry from its current position.
2. Link its two former neighbors together.
3. Place that entry at the tail.
4. Keep the head and tail of the chain consistent.

If the entry is already at the tail, there is no need to relink the sequence.

In the referenced source code, this role resides in `afterNodeAccess` of [LinkedHashMap OpenJDK 17u](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/LinkedHashMap.java). This is an implementation explanation; application code uses public operations and does not call internal methods.

The important point is that an entry's position can change even when keys, values, and size all remain unchanged.

## 4. get, getOrDefault, put, and putIfAbsent

The class documentation lists the operations that constitute an access and their related conditions. Consult [LinkedHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html) rather than inferring from names like "read" or "write".

### 4.1. get Hitting a Key vs. get Missing a Key

| State | Data Result | Order Effect |
| --- | --- | --- |
| Key exists with non-null value | Returns value | Entry is accessed, moved to tail if not already at tail |
| Key exists with null value | Returns null | Entry still exists and is accessed |
| Key does not exist | Returns null | No entry to move to tail |

Therefore, looking only at a `null` return value cannot determine whether the order was affected.

No "missing-key entry" is automatically created when calling `get`.

### 4.2. getOrDefault Distinguishes a Missing Key from a null Value

If the key is present in the map, `getOrDefault` returns the value associated with it and records an access, even if that value is `null`.

If the key is absent, the method returns the fallback value; it does not add a new mapping and does not record a missing entry in history.

The fallback value is not a value that gets stored automatically in the map.

### 4.3. put on an Existing Key Can Change Order Even If the Value Stays the Same

In access-order, `put` on an existing key is an access to that entry. Even if the new value equals the old value, the entry can still move to the tail.

This differs from an insertion-ordered map: in insertion-order mode, `put` on an existing key preserves the old position.

If the key does not exist yet, `put` adds a new entry at the tail. The map gains both new data and a new position.

### 4.4. putIfAbsent Is Not Necessarily a "No-Op"

When a key already has a non-null value, `putIfAbsent` does not replace the value. However, the entry is still counted as accessed in the access-order structure.

For example, given `a,b,c` and `a=1`, `putIfAbsent("a", 99)` returns `1` and does not change it to `99`, yet the sequence can become `b,c,a`.

If the key is currently mapped to `null`, the method can associate the provided value with it; the entry is also accessed. If the key is absent, it creates a new entry at the tail.

In the referenced implementation, even the case where a `null` entry receives `putIfAbsent` with `null` again goes through the access path. Returning `null` is not a general indicator of "no effect."

## 5. Conditional replace, setValue, and replaceAll

### 5.1. replace Only Creates an Access When Replacement Occurs

For `replace(key, newValue)`:

- Entry exists for `key`: performs value replacement and accesses the entry.
- No `key`: no replacement, no entry created to access.

For `replace(key, expectedValue, newValue)`:

- Key exists and old value matches condition: replaces and accesses the entry.
- Condition does not match or key is absent: no replacement, key is not moved to the tail.

Replacing with the same value that is already present is still a performed replacement if the condition matches. The new value does not need to differ according to `equals` for the entry to be accessed.

The return value of `replace(key, newValue)` can be `null` when the old value was `null`. To understand the effect, you must know whether an entry existed, not just look at the return value.

### 5.2. Entry.setValue Is Not map.put

Obtaining a `Map.Entry` from `entrySet` and calling `setValue` modifies the value through a view. The `LinkedHashMap` documentation does not count operations on collection views as entry accesses that alter access-order.

Thus, the same intent to "change a value" can have different effects on history depending on which API is used.

Choose based on the intended semantics; do not substitute one API for another just because they appear to produce the same final value.

### 5.3. replaceAll Is Not Equivalent to a Per-Key replace Loop

In the referenced `LinkedHashMap` implementation, `replaceAll` walks through the entries and replaces values; it does not automatically turn each entry into an access that moves it to the tail.

This also requires the passed function to have no side effects that structurally modify the map or call access operations that relink the sequence.

The statement "`replaceAll` preserves order" in the example below refers to a pure function computing the new value from its arguments. If the function itself calls `map.get`, `map.put`, or modifies the map by another route, those side effects must be considered as well.

## 6. Java 17 Example: Reads, Conditional Writes, and View Modifications

Save as **AccessOrderBasics.java**:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.Map;

public class AccessOrderBasics {
    static void show(String label, Map<String, Integer> map) {
        System.out.println(label + ": " + new ArrayList<>(map.keySet()));
    }

    public static void main(String[] args) {
        Map<String, Integer> map = new LinkedHashMap<>(16, 0.75f, true);
        map.put("a", 1);
        map.put("b", 2);
        map.put("c", 3);
        map.put("d", 4);
        show("initial", map);

        System.out.println("contains a: " + map.containsKey("a"));
        show("after contains", map);
        System.out.println("get b: " + map.get("b"));
        show("after get b", map);
        System.out.println("get missing: " + map.get("missing"));
        show("after missing", map);
        System.out.println("default a: " + map.getOrDefault("a", -1));
        show("after default a", map);

        System.out.println("old c: " + map.put("c", 30));
        show("after put c", map);
        System.out.println("existing b: " + map.putIfAbsent("b", 200));
        show("after putIfAbsent b", map);
        System.out.println("failed replace d: " + map.replace("d", 999, 40));
        show("after failed replace", map);
        System.out.println("successful replace d: " + map.replace("d", 4, 40));
        show("after successful replace", map);

        Map.Entry<String, Integer> first = map.entrySet().iterator().next();
        first.setValue(11);
        show("after entry setValue", map);
        System.out.println("values after setValue: " + new ArrayList<>(map.values()));
        map.replaceAll((key, value) -> value + 1);
        show("after replaceAll", map);
        System.out.println("values after replaceAll: " + new ArrayList<>(map.values()));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 AccessOrderBasics.java
java AccessOrderBasics
```

Stdout on the stated environment:

```text
initial: [a, b, c, d]
contains a: true
after contains: [a, b, c, d]
get b: 2
after get b: [a, c, d, b]
get missing: null
after missing: [a, c, d, b]
default a: 1
after default a: [c, d, b, a]
old c: 3
after put c: [d, b, a, c]
existing b: 2
after putIfAbsent b: [d, a, c, b]
failed replace d: false
after failed replace: [d, a, c, b]
successful replace d: true
after successful replace: [a, c, b, d]
after entry setValue: [a, c, b, d]
values after setValue: [11, 30, 2, 40]
after replaceAll: [a, c, b, d]
values after replaceAll: [12, 31, 3, 41]
```

### 6.1. Why Did putIfAbsent Move b to the Tail?

`b` still has value `2`, not `200`. However, it was just accessed by `putIfAbsent`. You must observe both values and the key sequence to see the full effect.

### 6.2. Two replace Calls Differ by Condition

The replacement on `d` with expected value `999` failed. `d` was not moved to the tail.

The replacement with expected value `4` succeeded; `d` became `40` and was moved to the tail.

### 6.3. Observing Without Disturbing History

The `show` method constructs an `ArrayList` from `keySet`. Iterating a view this way does not call `get` for each key, so printing the sequence does not move keys to the tail.

`setValue` changes the value of the first entry `a` to `11`. `replaceAll` increments the values without generating new access history. The `values` lines inspect the updated contents without issuing `get` calls that would cause additional effects.

## 7. compute and merge: Consider Execution Paths, Not Just Method Names

These methods may reuse an existing mapping, recompute a value, insert a new entry, skip, or remove. Therefore, a table that merely says "`compute` always moves the key to the end" is missing conditions.

The table below describes the main branches, assuming the passed function does not modify or access the map itself:

| Operation | Execution Branch | Position Effect |
| --- | --- | --- |
| computeIfAbsent | Already has a non-null value | Uses existing entry and records an access |
| computeIfAbsent | Computes a non-null value for a new key | Appends entry at tail |
| computeIfAbsent | Fills a non-null value for a currently null entry | Updates and accesses the entry |
| computeIfPresent | Has a non-null value, function returns non-null | Updates and accesses the entry |
| computeIfPresent | Function returns null | Removes mapping; entry no longer exists to place at tail |
| compute | Function returns non-null, entry exists | Updates and accesses the entry |
| compute | Function returns non-null, entry does not exist | Appends entry at tail |
| compute | Function returns null | Creates no new entry; if mapping exists, removes it |
| merge | Keeps/updates mapping with non-null result | Existing entry is accessed or new entry is appended at tail |
| merge | Remapping function returns null | Removes mapping |

If an entry is already at the tail, the access branch may produce no visible difference in the observed sequence. If removed, the relative order of the remaining entries is preserved.

### 7.1. Leaving the Value Unchanged Can Still Be an Access

`compute("a", (key, value) -> value)` when `a` has a non-null value still uses and updates the mapping along that path. The final value matching the previous one does not mean the entry stays in place.

Similarly, `computeIfAbsent` on a mapping that already has a non-null value does not invoke the mapping function, yet still records the use of the existing entry.

### 7.2. Returning null Has Multiple Meanings

`null` from `get` can be the value of an existing entry.

`null` from a remapping function can instruct the method not to create a new entry or to remove a mapping, depending on the method.

Do not apply the same ordering rule to every `null` result. Determine the mapping beforehand, the method branch, and the mapping afterward.

### 7.3. Skip Branches with null Entries Require Careful Reading

In the source of [HashMap OpenJDK 17u](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/HashMap.java), where the methods inherited by `LinkedHashMap` are implemented:

- `computeIfPresent` does not invoke the remapping function if the current value is `null`; that skip branch does not call `afterNodeAccess`.
- `computeIfAbsent` on a `null` entry where the function returns `null` keeps the `null` mapping; that return path also does not call `afterNodeAccess`.

This is a **specific implementation-branch analysis**, verified further in the next program on the stated environment. Do not infer from the general list of method families in the Javadoc a guarantee that every call with `compute` in its name must move an entry regardless of `null` conditions or skip branches.

When an application relies on such specific branches to define usage history, document the exact cases and verified version. If you want a simpler rule, you can deliberately avoid `null` values in your application model; that is a design choice, not a mandatory limitation of `LinkedHashMap`.

### 7.4. Remapping Functions Should Not Interfere with Order

Do not call `map.get` on the same map to retrieve a value that the function already received as an argument. In access-order, that call can alter links even without changing values.

`compute`/`merge` methods restrict modifying the map inside the remapping function. A side effect that causes structural modification may be detected and throw an error, while also making order reasoning harder to get right.

If a pure function throws an exception, do not treat it as a successful update. If the function already produced side effects before throwing, do not assume the system will automatically roll back all of those effects.

## 8. Java 17 Example: Remapping Branches and null

Each line of the program starts with **a fresh map**, ordered `a,b,c`. The `nullAtA` parameter selects `a=1` or `a=null`.

By re-initializing each case, results are not influenced by history from previous test lines.

Save as **AccessOrderRemapping.java**:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.function.Function;

public class AccessOrderRemapping {
    static void test(String label, boolean nullAtA,
            Function<Map<String, Integer>, Object> operation) {
        Map<String, Integer> map = new LinkedHashMap<>(16, 0.75f, true);
        map.put("a", nullAtA ? null : 1);
        map.put("b", 2);
        map.put("c", 3);

        Object result = operation.apply(map);
        System.out.println(label + " => result=" + result
                + "; keys=" + new ArrayList<>(map.keySet())
                + "; values=" + new ArrayList<>(map.values()));
    }

    public static void main(String[] args) {
        test("absent hit", false, m -> m.computeIfAbsent("a", key -> 99));
        test("absent new", false, m -> m.computeIfAbsent("d", key -> 9));
        test("present update", false, m -> m.computeIfPresent("a", (key, value) -> value + 10));
        test("present remove", false, m -> m.computeIfPresent("a", (key, value) -> null));
        test("compute unchanged", false, m -> m.compute("a", (key, value) -> value));
        test("compute missing null", false, m -> m.compute("x", (key, value) -> null));
        test("merge update", false, m -> m.merge("a", 10, Integer::sum));
        test("merge remove", false, m -> m.merge("a", 10, (oldValue, added) -> null));
        test("get mapped null", true, m -> m.get("a"));
        test("default mapped null", true, m -> m.getOrDefault("a", -1));
        test("present mapped null", true, m -> m.computeIfPresent("a", (key, value) -> 9));
        test("absent null result", true, m -> m.computeIfAbsent("a", key -> null));
        test("absent fills null", true, m -> m.computeIfAbsent("a", key -> 9));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 AccessOrderRemapping.java
java AccessOrderRemapping
```

Stdout:

```text
absent hit => result=1; keys=[b, c, a]; values=[2, 3, 1]
absent new => result=9; keys=[a, b, c, d]; values=[1, 2, 3, 9]
present update => result=11; keys=[b, c, a]; values=[2, 3, 11]
present remove => result=null; keys=[b, c]; values=[2, 3]
compute unchanged => result=1; keys=[b, c, a]; values=[2, 3, 1]
compute missing null => result=null; keys=[a, b, c]; values=[1, 2, 3]
merge update => result=11; keys=[b, c, a]; values=[2, 3, 11]
merge remove => result=null; keys=[b, c]; values=[2, 3]
get mapped null => result=null; keys=[b, c, a]; values=[2, 3, null]
default mapped null => result=null; keys=[b, c, a]; values=[2, 3, null]
present mapped null => result=null; keys=[a, b, c]; values=[null, 2, 3]
absent null result => result=null; keys=[a, b, c]; values=[null, 2, 3]
absent fills null => result=9; keys=[b, c, a]; values=[2, 3, 9]
```

### 8.1. Cases That Use an Existing Entry

`absent hit` uses `a=1` without calling the function that produces `99`, yet `a` is still moved to the tail.

`compute unchanged` returns the existing value, yet the sequence still becomes `b,c,a`.

These two examples show that "the value did not change" cannot be used as the criterion for determining order.

### 8.2. Cases That Remove or Do Not Create a Mapping

`present remove` and `merge remove` remove `a` from the map, leaving `b,c`.

`compute missing null` does not create `x`, so `a,b,c` stays unchanged. There is no entry `x` to place as most recent.

### 8.3. Identifying null by State, Not Only by Return Value

`get mapped null` and `default mapped null` both return `null`, but `a` exists so it moves to the tail: `b,c,a`.

`present mapped null` and `absent null result` also return `null`, but in those skip/unfilled branches of the explained implementation, the sequence stays `a,b,c`.

`absent fills null` computes `9`, updates `a`, and moves `a` to the tail.

The lines belonging to special `null` branches should be read alongside the implementation scope and environment of this lesson. They are not a reason to invent a rule of thumb such as "`null` always preserves order" or "`null` always triggers an access."

## 9. putAll Produces a Sequence of Accesses in Source Order

`putAll` does not only add missing keys. With access-order, mappings already present in the destination map are also processed as corresponding accesses.

The class documentation specifies that accesses are performed in the order of the source map's `entrySet`.

Suppose the destination currently has `a,b,c,d` and the source provides `c,a,e`:

| Step | Processed Mapping | Destination Order After Step |
| --- | --- | --- |
| Start | Not processed yet | a,b,c,d |
| 1 | c | a,b,d,c |
| 2 | a | b,d,c,a |
| 3 | new e | b,d,c,a,e |

`b` and `d` are not touched by this `putAll` batch, so they remain ahead of the entries just moved to the tail, in their relative order.

### 9.1. A Source Without an Order Contract Makes Results Harder to Predict

If the source is an insertion-ordered `LinkedHashMap` with `c,a,e`, there is a solid basis to use that exact sequence for the table.

If the source is a `Map` without ordering guarantees, do not assume `putAll` will follow alphabetical order or the history in which data was originally created. The destination records entries in the order the source actually yields them.

If you want a specific ordering rule, control the source order or prepare the update sequence explicitly.

### 9.2. Both New Additions and Re-Accesses Matter

The new key `e` is at the tail because it was just added. Existing `c` and `a` still change positions because `putAll` re-accesses them.

Do not apply the assumption "only new keys affect order" to an access-ordered map.

Do not use the very map whose order is changing as the source and assume copying onto itself is harmless. Source iteration and destination accesses must be considered together.

## 10. Operations That Do Not Automatically Move an Entry to the Tail

The table below covers **the operation itself**, excluding side effects from additional user code:

| Operation | Automatically records an access to refresh position? |
| --- | --- |
| containsKey | No |
| containsValue | No |
| size, isEmpty | No |
| Iterating keySet, values, entrySet | No |
| Reading key/value from a Map.Entry | No |
| Entry.setValue via view | No |
| forEach with a function using only its arguments | No |
| replaceAll with a pure function computing new values | Does not automatically create per-key accesses like replace |
| Failed conditional replace | No |
| get or getOrDefault when key is not found | No entry to refresh |

### 10.1. Not Re-Accessing Does Not Mean Not Modifying the Map

`remove` deletes a mapping; `clear` empties the map. These operations change structure, though they are not position refreshes of the removed entry.

Removing through a view also has a real effect on the map. It does not automatically mark the remaining entries as recently accessed.

Therefore, distinguish three kinds of effects:

- Updating key–value content.
- Adding/removing mappings.
- Changing position according to access history.

A method may involve more than one kind, or none at all.

### 10.2. Observation Code Can Indirectly Trigger Accesses

A custom logging helper like "iterate `keySet`, call `map.get(key)`, print the value" can alter order. The cause is the extra `get` calls, not `keySet` counting as an access itself.

Similarly, a function passed to `forEach` might call `get` or `put` itself. In that case, those calls must be accounted for; do not use the name `forEach` to conclude the entire code block has no effect.

To merely observe mappings during a pass, obtain both key and value from `entrySet` and avoid calling APIs that refresh positions.

### 10.3. Snapshotting a Key List Does Not Freeze the Map

`new ArrayList<>(map.keySet())` snapshots the key sequence into a list. Calling `get` on each key afterward is still an access on the map.

Iterating the snapshot list may avoid some issues caused by the map's iterator having its sequence relinked on the same thread, but it does not turn `get` calls into history-neutral operations.

Nor does copying the key list create a multi-thread consistent snapshot without proper coordination.

## 11. Iterator: Even When size Is Unchanged, It Can Still Become Invalid

In access-order, changing order is a form of structural modification. Therefore, a successful `get` can affect an active iterator.

Error-prone pattern:

```java
for (String key : recent.keySet()) {
    Integer value = recent.get(key);
    System.out.println(value);
}
```

This is an **illustrative snippet to avoid**, not a recommended standalone program. It iterates the map and then accesses the same map via `get`.

If `get` moves an entry that is not at the tail to the tail, the previously created iterator may detect the modification and throw `ConcurrentModificationException`.

### 11.1. Iterate entrySet to Read Data Already in the Entry

If you only need to read every pair, use:

```java
for (Map.Entry<String, Integer> entry : recent.entrySet()) {
    String key = entry.getKey();
    Integer value = entry.getValue();
    System.out.println(key + "=" + value);
}
```

This is a snippet in a context with `recent` and the appropriate imports. Reading the value from the entry does not trigger an additional access on the map.

If you need to remove during iteration, refer to the iterator's own `remove` operation per its contract. Do not arbitrarily modify structure through the map and continue using the old iterator.

### 11.2. Fail-Fast Is Diagnostic, Not a Business Condition

Detection is implemented on a best-effort basis. Do not write logic such as "if there is no `ConcurrentModificationException`, the loop must be safe."

For example, calling `get` on the entry already at the tail may not relink the list in a given implementation, but that does not make it a stable iterator usage pattern across all histories.

`ConcurrentModificationException` is also not solely a multi-threading issue. A single thread can invalidate its own iterator by modifying structure outside permitted paths.

## 12. Java 17 Example: putAll, Safe Read Loop, and Affected Iterator

Save as **AccessOrderBulkAndIteration.java**:

```java
import java.util.ArrayList;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.StringJoiner;

public class AccessOrderBulkAndIteration {
    public static void main(String[] args) {
        Map<String, Integer> map = new LinkedHashMap<>(16, 0.75f, true);
        map.put("a", 1);
        map.put("b", 2);
        map.put("c", 3);
        map.put("d", 4);

        Map<String, Integer> incoming = new LinkedHashMap<>();
        incoming.put("c", 30);
        incoming.put("a", 10);
        incoming.put("e", 5);
        map.putAll(incoming);
        System.out.println("after putAll: " + new ArrayList<>(map.keySet()));

        StringJoiner joined = new StringJoiner("; ");
        for (Map.Entry<String, Integer> entry : map.entrySet()) {
            joined.add(entry.getKey() + "=" + entry.getValue());
        }
        System.out.println("safe entries: " + joined);
        System.out.println("after safe loop: " + new ArrayList<>(map.keySet()));

        Iterator<String> iterator = map.keySet().iterator();
        System.out.println("iterator first: " + iterator.next());
        System.out.println("get c during iteration: " + map.get("c"));
        System.out.println("after get c: " + new ArrayList<>(map.keySet()));
        try {
            System.out.println("iterator next: " + iterator.next());
        } catch (ConcurrentModificationException expected) {
            System.out.println("observed iterator: ConcurrentModificationException");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 AccessOrderBulkAndIteration.java
java AccessOrderBulkAndIteration
```

Observed stdout on the stated environment:

```text
after putAll: [b, d, c, a, e]
safe entries: b=2; d=4; c=30; a=10; e=5
after safe loop: [b, d, c, a, e]
iterator first: b
get c during iteration: 30
after get c: [b, d, a, e, c]
observed iterator: ConcurrentModificationException
```

### 12.1. putAll Follows the c,a,e Sequence

The result `b,d,c,a,e` matches the analysis table. `c` becomes `30`, `a` becomes `10`, and `e` is added with `5`.

The `entrySet` loop reads keys and values directly. The sequence afterward remains `b,d,c,a,e`.

### 12.2. A Single get Invalidates the Old Iterator

The iterator already returned `b`. Then `get("c")` moves `c` to the tail, making the sequence `b,d,a,e,c`. Size is still `5`, but the order links changed.

On the documented runtime environment, the next `next()` call observes `ConcurrentModificationException`. The `observed` line is the result of a diagnostic experiment; do not turn throwing in every invalid situation into an absolute guarantee.

The example intentionally catches the exception so the program exits cleanly and explains the cause. In real code, fix the iteration or update model instead of using `catch` to continue with an invalidated iterator.

## 13. Implications of Using Access-Order in Applications

### 13.1. Define What "Using an Item" Means

If you check existence with `containsKey`, the item is not refreshed. If you retrieve the value with `get`, the item is accessed.

If `putIfAbsent` finds existing data, it can still refresh the position without changing content. If a conditional `replace` fails, it does not.

These differences affect how the head of the sequence is interpreted. Choose the API that matches the meaning of "use" in your problem, not just the return type.

### 13.2. No Built-in Bound, Expiration, or Concurrency Safety

Access-order provides a relative history of entries. It does not automatically bound the number of mappings, expire entries by time, or coordinate multiple threads.

An eviction mechanism, if needed, is an additional policy. Do not assume that passing `true` alone gives you a complete cache.

### 13.3. get Can Be a Structural Modification

If a synchronization locking design classifies every `get` as a pure read, that design must be revisited when using access-order. Two threads calling `get` simultaneously can both mutate the order chain.

`LinkedHashMap` is not thread-safe. Use an appropriate coordination mechanism covering order-changing operations, iterations, and operation sequences requiring consistency.

Do not use fail-fast behavior as a substitute for coordination.

### 13.4. Copying Does Not Preserve the Mode

`new LinkedHashMap<>(source)` creates an insertion-ordered map receiving the sequence yielded by `source` at copy time. It does not automatically enable `accessOrder=true` just because `source` is in access-order mode.

If the new map also needs to maintain access-order, create it with the desired configuration and then insert mappings in the appropriate sequence.

Copying mappings is not automatically a deep copy of keys and values, nor does it automatically produce a consistent snapshot when `source` is being modified concurrently.

## 14. How to Test Order Intentionally

A good test clearly specifies:

1. The map's mode.
2. The data and sequence before the operation.
3. The operation along with its conditions.
4. The return value, remaining mappings, and sequence after the operation.
5. The environment when testing a specific implementation branch.

To verify key sequence, compare a `List` created from `keySet`. Checking only `Map.equals` or `keySet.equals` does not verify order.

Use data with at least several entries and pick a key that is not already at the tail. If every test accesses the tail entry, many order-expectation bugs will be masked because the sequence has nothing to change.

For conditional branches, test both success and failure. For `null`, distinguish missing keys, keys currently mapped to `null`, `null` recomputation results, and mapping removals.

The observation helper in this lesson only iterates a view. If a test uses `get` to check a value, that check itself can alter state before the next assertion. You can check order first, or inspect the `entry`/`values` sequence without triggering extra accesses.

For programs with consecutive operations, record step-by-step history or initialize a fresh map per case as in the second program. Never let a hidden verification step become the reason later results are hard to explain.

## 15. Common Pitfalls and Fixes

| Misconception | Correct Understanding |
| --- | --- |
| Access-order orders by highest access count | It is a relative order by most recently recorded access |
| get is always structurally read-only | A get hitting an entry can relink the sequence |
| get returning null must not change anything | It may have accessed an entry holding a null value |
| put with the same value does not affect order | An existing entry can still be refreshed |
| putIfAbsent that does not insert is a no-op | When a value already exists, it can still count as an access |
| Failed replace also moves the key to the tail | Only a performed replacement records an access per replace rules |
| Every compute call has the same effect | Consider hit, insert, skip, remove branches and null conditions |
| setValue and put behave identically for history | Operating via an entry view does not create an access like put |
| putAll only affects new keys | It also re-accesses existing mappings in source order |
| Unchanged size means the iterator remains valid | Changing order can also be a structural modification |
| Printing data cannot modify the map | A print helper calling get can refresh history |
| No exception means usage is definitely correct | Fail-fast only provides best-effort diagnostics |
| Copy constructor preserves access-order | The Map-taking constructor creates insertion-order mode |
| Enabling access-order gives a full cache | Capacity limits, expiration, and coordination require separate policies if needed |

## 16. Self-Check Exercises with Solutions

### Exercise 1: Re-Accessing a Key

An access-ordered map has `a,b,c`. `get("a")` succeeds, then `get("c")` succeeds. What is the final sequence?

**Solution:** after `get("a")` it is `b,c,a`; after `get("c")` it is `b,a,c`.

### Exercise 2: Key Not Found

From `a,b,c`, call `getOrDefault("x", -1)`. What are the result and order?

**Solution:** returns `-1`; `x` is not added, and the sequence remains `a,b,c`.

### Exercise 3: Value Unchanged

From `a=1,b=2,c=3`, call `putIfAbsent("a", 99)`. Are both value and order preserved?

**Solution:** `a`'s value stays `1` and the method returns `1`, but the sequence becomes `b,c,a` if `a` was not already at the tail.

### Exercise 4: replace with Same Value

From `a=1,b=2,c=3`, call `replace("a", 1, 1)`. Does the new value need to differ from the old value for `a` to be refreshed?

**Solution:** no. The condition matches so the replacement is performed; `a` can be moved to the tail even though it remains `1`.

### Exercise 5: Skipping a null Value

A map has `a=null,b=2,c=3`. In the referenced implementation path, does `computeIfPresent("a", (key, value) -> value + 1)` invoke the function and move `a` to the tail?

**Solution:** no. This branch skips because the current value is `null`, does not invoke the remapping function, and does not call `afterNodeAccess`. This case should be read within the implementation scope of the lesson.

### Exercise 6: Remapping Function Returns null

From `a=1,b=2,c=3`, `merge` `a` with a non-null value, but the remapping function returns `null`. Does `a` become the tail entry?

**Solution:** the mapping for `a` is removed; the sequence becomes `b,c`. There is no entry `a` to keep at the tail.

### Exercise 7: putAll Source

Destination currently has `a,b,c,d`. Source yields `b` then `a`. Assuming the update batch neither removes nor adds any keys, what is the final sequence?

**Solution:** processing `b` produces `a,c,d,b`; processing `a` next produces `c,d,b,a`.

### Exercise 8: Read-Only Iteration

You need to export existing pairs without refreshing history. Choose `keySet` plus `get` or `entrySet` plus `getValue`?

**Solution:** use `entrySet` and read key/value from each entry. `keySet` plus `get` can alter order and affect an active iterator over the map.

### Exercise 9: Testing That Masks Changes

All `get` tests pick the tail entry. Does an unchanged sequence prove `get` does not count as an access?

**Solution:** no. The tail entry is already in the newest position. You must test a key at the head or in the middle to observe movement.

### Exercise 10: Observation with Side Effects

A test checks a value using `get("a")` before asserting the sequence. Can that check itself change the sequence result?

**Solution:** yes. With access-order, `get` affects history. Design verification steps so they do not disturb the state being tested.

## 17. References

- [LinkedHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html): access-order mode, operation list, `putAll`, `replace`, views, and fail-fast limitations.
- [LinkedHashMap.java OpenJDK 17u](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/LinkedHashMap.java): `get`, `getOrDefault`, `afterNodeAccess`, `replaceAll`, and iterator.
- [HashMap.java OpenJDK 17u](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/HashMap.java): inherited `putIfAbsent`, `replace`, `compute`, and `merge` branches.
- [Map Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): `null` value conditions, remapping functions, mappings, and views.

When using access-order, treat order as part of the state that operations can mutate. To predict it accurately, consider the API kind, execution conditions, and any surrounding observation calls or remapping functions.
