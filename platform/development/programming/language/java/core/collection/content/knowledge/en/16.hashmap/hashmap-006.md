# One Null Key and Multiple Null Values Policy

## 1. Two Null Positions Have Two Different Roles

A `HashMap<K, V>` stores key-to-value mappings. It allows:

- At most one mapping with a `null` key in the same map.
- Multiple different mappings sharing a `null` value.
- A single mapping having both a `null` key and a `null` value.

“Multiple null values” should be read as **multiple mappings whose value part is null**, not a single key holding multiple current values. Each key still determines at most one value.

For example, a map can represent:

```text
null     → "default content"
"draft"  → null
"review" → null
```

The key on the left identifies the mapping. The value on the right is the data attached to that key. Allowing duplicate values does not make keys allowed to duplicate.

### Why Do You Need to Understand This Policy?

If an application allows unknown data, `null` can appear during both storing and reading. In that case, `get` returning `null` is not enough to conclude that a key is absent; writing `null` is also not synonymous with removing a mapping.

Conversely, if business rules forbid `null`, the fact that `HashMap` accepts it does not mean every null input is valid. Library capability and application data rules are two layers that must be separated.

This lesson moves from the key–value structure to reading, updating, iterating, and transferring data. All examples use a real `HashMap`, without relying on iteration order that this class does not guarantee.

## 2. Why Is There Only One Null Key?

A map does not store two separate mappings for the same logical key. Calling `put(null, value)` the first time can create a mapping; calling it again with the `null` key replaces that mapping's value.

```text
put(null, "first")
    → null → "first"

put(null, "second")
    → null → "second"
    → does not create a second null key
```

This rule applies per map, not as a “program-wide limit of only one null.” Two different `HashMap` objects can each hold their own null-key mapping.

`null` is a reference that points to no object; there is no separate null class for creating typed null keys. If multiple variables all hold null and are used as keys in the same map that accepts them, they do not become distinct identifiers just because their variable names differ.

### Do Not Use null as a Temporary Code for Multiple Distinct Records

If three records without codes are all written using the `null` key, subsequent writes will replace the previous mapping. You do not have three independent records just because there are three different value objects.

If business logic must retain multiple records with undetermined codes, an appropriate identifier is needed, such as a unique temporary code, a dedicated key type, or a list structure if the data is inherently a sequence of records. Do not expect a map to bypass key uniqueness just for the null case.

### null Is Different from the String "null"

The following snippet is an illustration inside a method, starting with an empty map:

```java
Map<String, String> map = new HashMap<>();
map.put(null, "default");
map.put("null", "literal");

// map.size() is 2.
// map.get(null) is "default".
// map.get("null") is "literal".
```

`"null"` is a four-character string object, whereas `null` is a reference to no object. Automatically converting null into the string `"null"` can erase this distinction if real data is also allowed to use that string as a key.

### HashMap Accepting null Does Not Mean You Can Call Methods on null

`map.get(null)`, `map.put(null, value)`, and `map.containsKey(null)` are supported by `HashMap`. The implementation handles the null-key case according to its contract; application code does not need to and cannot call `null.hashCode()` or `null.equals(...)`.

A `NullPointerException` caused by application code calling a method on a null key is not evidence that `HashMap` rejects that key.

## 3. Why Are Multiple Null Values Valid?

Map values are not required to be unique. Just as two keys can both hold the number `3`, two or more keys can both hold the value `null`.

```text
"draft"  → null
"review" → null
"final"  → null
```

The map above has three mappings. Its size is `3`, even though there are no non-null values.

If you add the mapping `null → null`, the size can become `4`: the null key is a different key from the three existing strings. Writing `put("draft", null)` again afterward does not increase the size further, because the key `"draft"` already exists.

| Question | Appropriate Method |
|---|---|
| Is there a mapping for the null key? | `containsKey(null)` |
| What is the current value of the null key? | `get(null)` |
| Is there at least one mapping with a null value? | `containsValue(null)` |
| How many mappings are there? | `size()` |
| How many mappings have a null value? | Iterate values or entries and count conditionally |

`containsValue(null)` only returns a `boolean`: it does not tell you how many nulls there are, does not indicate which keys have them, and does not prove that the null key exists.

The independent combinations can be:

- No null key, yet multiple null values.
- A null key, yet no null values at all.
- Both a null key and null values.
- Neither.

## 4. Complete Program: One Null Key, Multiple Null Values

```java
import java.util.HashMap;
import java.util.Map;

public class HashMapNullPolicyDemo {
    public static void main(String[] args) {
        Map<String, String> messages = new HashMap<>();

        System.out.println("firstNullKeyOld="
                + messages.put(null, "default"));
        System.out.println("secondNullKeyOld="
                + messages.put(null, "fallback"));
        System.out.println("sizeAfterNullKeyWrites=" + messages.size());
        System.out.println("nullKeyValue=" + messages.get(null));

        messages.put("draft", null);
        messages.put("review", null);
        System.out.println("sizeAfterNamedNullValues=" + messages.size());
        System.out.println("hasNullValue=" + messages.containsValue(null));

        System.out.println("oldBeforeNullNull="
                + messages.put(null, null));
        System.out.println("hasNullKey=" + messages.containsKey(null));
        System.out.println("nullKeyNow=" + messages.get(null));
        System.out.println("finalSize=" + messages.size());

        int nullKeyCount = 0;
        int nullValueCount = 0;
        for (Map.Entry<String, String> entry : messages.entrySet()) {
            if (entry.getKey() == null) {
                nullKeyCount++;
            }
            if (entry.getValue() == null) {
                nullValueCount++;
            }
        }
        System.out.println("nullKeyCount=" + nullKeyCount);
        System.out.println("nullValueCount=" + nullValueCount);
    }
}
```

Save as `HashMapNullPolicyDemo.java`, then compile and run:

```shell
javac --release 17 -encoding UTF-8 HashMapNullPolicyDemo.java
java HashMapNullPolicyDemo
```

Exact output:

```text
firstNullKeyOld=null
secondNullKeyOld=default
sizeAfterNullKeyWrites=1
nullKeyValue=fallback
sizeAfterNamedNullValues=3
hasNullValue=true
oldBeforeNullNull=fallback
hasNullKey=true
nullKeyNow=null
finalSize=3
nullKeyCount=1
nullValueCount=3
```

### Explaining the Checkpoints

The two null-key writes create a single mapping:

- The first call returns `null` because there was no previous value.
- The second call returns `"default"`, and the current value becomes `"fallback"`.
- The size after both writes remains `1`.

The two string keys `"draft"` and `"review"` are added with null values, bringing the size to `3`.

Finally, `put(null, null)` replaces the null key's value from `"fallback"` to null. The size remains `3`; at this point all three mappings carry a null value.

The last two counters have different meanings:

```text
nullKeyCount=1
nullValueCount=3
```

There is no need to rely on where the null key is printed in iteration order. The program only counts or reads by specific keys, so the output does not depend on any incidental `HashMap` ordering.

## 5. Three States When Reading a Key

For a key `k`, you must distinguish:

| State | `get(k)` | `containsKey(k)` |
|---|---|---|
| No mapping for `k` | `null` | `false` |
| Mapping `k → null` exists | `null` | `true` |
| Mapping `k → "ready"` exists | `"ready"` | `true` |

This table also applies when `k` is the null key in a `HashMap`. The null key does not eliminate the difference between “no mapping yet” and “mapped to a null value.”

If business logic distinguishes “not yet recorded” from “recorded without a value yet,” preserve that distinction when reading. Simply checking `get(k) != null` merges the first two states.

### getOrDefault Does Not Replace Every null with a Fallback Value

`getOrDefault(k, fallback)` chooses `fallback` when **there is no mapping** for the key. If the key is mapped to a null value, the result is still null.

Therefore, the name “default” does not mean “every null result will be replaced by another value.” You must choose the right rule:

- Fall back when the key is absent.
- Fall back when the value is null, regardless of whether the key is present or absent.
- Keep the two situations separate to handle them differently.

The first two rules differ in meaning, even though in an application that forbids null values they may yield the same result for valid data.

Reading with `get` or `getOrDefault` also does not automatically insert a new key. Returning a fallback value does not mean it has been stored in the map.

### Optional Does Not Automatically Preserve Presence Information

If you wrap `Optional.ofNullable(map.get(k))`, both an absent mapping and a mapping with a null value produce `Optional.empty()`. That wrapping may be suitable if the application intentionally merges the two states, but it does not help preserve a distinction that was already discarded.

When you need to represent multiple business states, you can use a result type that states the state explicitly or combine presence information through a controlled access mechanism.

## 6. Writing null Differs from Removing a Mapping

For a mutable `HashMap`:

| Successful Operation | State After Operation |
|---|---|
| `put(k, null)` | Key `k` has a mapping; value is null |
| `remove(k)` | Key `k` no longer has a mapping |
| `remove(k, null)` | Removes only if `k` currently maps to null |

`put(k, null)` is not an alias for `remove(k)`. If data uses null to represent the state “record exists, value not yet set,” removing the mapping destroys the “record exists” information itself.

Single-argument `put` and `remove` return the previous value. A null result here still has two possibilities: there was no previous mapping, or there was a mapping with a null value.

If you need to know whether the key existed beforehand, in a single-threaded data-ownership scenario you can record `containsKey(k)` before the operation. Checking after `remove` cannot recover the difference, because both “originally absent” and “just removed” result in the key being absent afterward.

Two separate calls are not automatically an atomic operation. `HashMap` does not provide synchronization for multiple threads mutating data concurrently; do not infer thread-safe state distinction solely from two lines calling `containsKey` then `remove`.

### Does Removing via values Remove One or All?

`map.values().remove(null)` removes a single occurrence of the null value if present, meaning it drops one corresponding mapping from the map. It does not automatically remove all mappings that have a null value.

If you need to remove all of them, you can use `removeIf(Objects::isNull)` on the values view of a mutable map. You must decide explicitly whether this matches business rules: filtering out all nulls drops those mappings, not just cleans up a representation.

## 7. Complete Program: Presence, Fallback Values, and Removal

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class HashMapNullPresenceDemo {
    public static void main(String[] args) {
        Map<String, String> states = new HashMap<>();
        states.put("draft", null);

        System.out.println("draftGet=" + states.get("draft"));
        System.out.println("missingGet=" + states.get("missing"));
        System.out.println("hasDraft=" + states.containsKey("draft"));
        System.out.println("hasMissing=" + states.containsKey("missing"));
        System.out.println("draftOrDefault="
                + states.getOrDefault("draft", "fallback"));
        System.out.println("missingOrDefault="
                + states.getOrDefault("missing", "fallback"));
        System.out.println("sizeAfterReads=" + states.size());

        boolean existed = states.containsKey("draft");
        String removedOld = states.remove("draft");
        System.out.println("existedBeforeRemove=" + existed);
        System.out.println("removedOld=" + removedOld);
        System.out.println("hasDraftAfterRemove="
                + states.containsKey("draft"));

        states.put("draft", null);
        System.out.println("conditionalNullRemove="
                + states.remove("draft", null));
        System.out.println("sizeAfterConditionalRemove=" + states.size());

        states.put("a", null);
        states.put("b", null);
        states.put("c", null);
        System.out.println("oneNullRemoved=" + states.values().remove(null));
        System.out.println("sizeAfterOneNullRemove=" + states.size());
        System.out.println("stillHasNullValue=" + states.containsValue(null));
        System.out.println("allNullsRemoved="
                + states.values().removeIf(Objects::isNull));
        System.out.println("finalSize=" + states.size());
    }
}
```

Save as `HashMapNullPresenceDemo.java`, then compile and run:

```shell
javac --release 17 -encoding UTF-8 HashMapNullPresenceDemo.java
java HashMapNullPresenceDemo
```

Exact output:

```text
draftGet=null
missingGet=null
hasDraft=true
hasMissing=false
draftOrDefault=null
missingOrDefault=fallback
sizeAfterReads=1
existedBeforeRemove=true
removedOld=null
hasDraftAfterRemove=false
conditionalNullRemove=true
sizeAfterConditionalRemove=0
oneNullRemoved=true
sizeAfterOneNullRemove=2
stillHasNullValue=true
allNullsRemoved=true
finalSize=0
```

### Reading Identical Results Correctly

`draftGet` and `missingGet` are both null, but `hasDraft=true` and `hasMissing=false`. The two reads do not increase the size.

`draftOrDefault=null`, while `missingOrDefault=fallback`, matching the rule that the fallback applies only when no mapping exists.

Removing `"draft"` returns `removedOld=null`, yet it actually took effect because `existedBeforeRemove=true` and afterward the key is gone. The overload `remove("draft", null)` returns a `boolean` flag: `true` indicates the conditional removal succeeded, not an old `String` value.

After adding `"a"`, `"b"`, and `"c"` all with null values, a single removal via `values().remove(null)` leaves size `2` and still contains null. The program deliberately makes no claim about which of the three keys was chosen. Only the subsequent `removeIf` filters out all remaining mappings.

## 8. Update Methods Do Not Interpret null the Same Way

The fact that `HashMap` allows storing null values does not mean every method treats null as an ordinary value in every position.

The table below assumes a mutable map, a valid passed-in function that does not mutate the map during computation, and no concurrent mutating access:

| Method | If a Mapping with a null Value Already Exists |
|---|---|
| `get(k)` | Returns null |
| `getOrDefault(k, fallback)` | Still returns null because the key has a mapping |
| `putIfAbsent(k, v)` | Can write `v`; treats a null value as no value to preserve |
| `computeIfAbsent(k, fn)` | Calls the function to try computing a non-null value |
| `computeIfPresent(k, fn)` | Does not call the function, because a non-null current value is required |
| `compute(k, fn)` | Calls the function with old value null; a null result means remove the mapping |
| `merge(k, incoming, fn)` | Uses the non-null `incoming` without combining with the null old value |

### 8.1. putIfAbsent Does Not Mean containsKey Is false

The method name easily leads readers to think it writes only when the key is absent. The contract also covers the case where the key currently maps to null.

If an application wants to preserve null as a meaningful recorded state, it should not use `putIfAbsent` and expect it to always protect that state from being overwritten. Choose the rule based on the actual requirement for mapping presence.

### 8.2. computeIfAbsent Returning null Does Not Create a New null Value

If the function returns a non-null value, the method can write that value when the value was previously missing or currently null.

If the function returns null:

- A key that was absent still gets no new mapping.
- A key that already had a null-value mapping keeps that null mapping.

This differs from thinking “returning null erases all trace of the key.” The next program verifies both cases separately.

A consequence when used as a cache: if the loader function returns null for a not-found result, `computeIfAbsent` does not store a non-null marker to record that a check occurred. Subsequent calls may still invoke the loader again. If you need to remember “checked but no result found,” use an explicit state representation suited to your application design.

### 8.3. computeIfPresent Requires a Non-Null Value

A key can have `containsKey(k) == true`, yet `computeIfPresent` will not run the function because the current value is null.

Therefore, the word “Present” in the method name cannot be read apart from the specific conditions of its contract. It is not merely a check for key existence.

If the function is actually called for a non-null old value and returns null, the mapping is removed.

### 8.4. compute Returning null Is a Request to Remove the Mapping

`compute` passes null as the old value both when there is no mapping and when there is a null mapping. From the old-value parameter alone, the function cannot distinguish these two situations.

If the function returns null, the mapping is removed if present; if it was absent, it remains absent. Do not use `compute(k, ... -> null)` to “store a null value” the way `put(k, null)` does.

### 8.5. merge Takes a Non-Null Input Value

Even though `HashMap.put(k, null)` is valid, `merge(k, null, fn)` is not valid for that reason. The incoming value parameter of `merge` must be non-null.

When the old value is null or no mapping exists, `merge` associates the non-null incoming value directly. Only when a non-null value already exists does it invoke the remapping function. If the remapping function returns null, the mapping is removed.

Three positions must be distinguished:

1. The passed-in key can be null with `HashMap`.
2. The incoming value to `merge` must be non-null.
3. A null result from the remapping function means remove the mapping.

It is the same word null, but its role differs; reading the parameter position and contract type carefully prevents confusion.

## 9. Complete Program: Verifying Update Rules

```java
import java.util.HashMap;
import java.util.Map;

public class HashMapNullUpdateMethodsDemo {
    public static void main(String[] args) {
        Map<String, String> states = new HashMap<>();
        states.put("draft", null);
        System.out.println("putIfAbsentOld="
                + states.putIfAbsent("draft", "ready"));
        System.out.println("draftNow=" + states.get("draft"));

        states.put("loadable", null);
        String loaded = states.computeIfAbsent("loadable", key -> "loaded");
        System.out.println("computeIfAbsentValue=" + loaded);

        String missingResult = states.computeIfAbsent("missing", key -> null);
        System.out.println("missingComputeResult=" + missingResult);
        System.out.println("hasMissingAfterCompute="
                + states.containsKey("missing"));

        states.put("explicit-null", null);
        String nullResult = states.computeIfAbsent("explicit-null", key -> null);
        System.out.println("existingNullComputeResult=" + nullResult);
        System.out.println("hasExplicitNullAfterComputeIfAbsent="
                + states.containsKey("explicit-null"));

        String skipped = states.computeIfPresent("explicit-null", (key, old) -> {
            throw new AssertionError("Must not run for a null value");
        });
        System.out.println("computeIfPresentResult=" + skipped);
        System.out.println("hasExplicitNullAfterComputeIfPresent="
                + states.containsKey("explicit-null"));

        states.compute("explicit-null", (key, old) -> null);
        System.out.println("hasExplicitNullAfterCompute="
                + states.containsKey("explicit-null"));

        String nullKeyValue = states.computeIfAbsent(
                null, key -> key == null ? "default" : key);
        System.out.println("computedNullKeyValue=" + nullKeyValue);

        Map<String, Integer> counts = new HashMap<>();
        counts.put("hits", null);
        System.out.println("firstMerge="
                + counts.merge("hits", 1, Integer::sum));
        System.out.println("secondMerge="
                + counts.merge("hits", 2, Integer::sum));
        System.out.println("mergeRemovalResult="
                + counts.merge("hits", 1, (old, incoming) -> null));
        System.out.println("hasHitsAfterMergeRemoval="
                + counts.containsKey("hits"));

        try {
            counts.merge("invalid", null, Integer::sum);
            throw new AssertionError("Expected NullPointerException");
        } catch (NullPointerException expected) {
            System.out.println("nullMergeInput=NullPointerException");
        }
    }
}
```

Save as `HashMapNullUpdateMethodsDemo.java`, then compile and run:

```shell
javac --release 17 -encoding UTF-8 HashMapNullUpdateMethodsDemo.java
java HashMapNullUpdateMethodsDemo
```

Exact output:

```text
putIfAbsentOld=null
draftNow=ready
computeIfAbsentValue=loaded
missingComputeResult=null
hasMissingAfterCompute=false
existingNullComputeResult=null
hasExplicitNullAfterComputeIfAbsent=true
computeIfPresentResult=null
hasExplicitNullAfterComputeIfPresent=true
hasExplicitNullAfterCompute=false
computedNullKeyValue=default
firstMerge=1
secondMerge=3
mergeRemovalResult=null
hasHitsAfterMergeRemoval=false
nullMergeInput=NullPointerException
```

### 9.1. Key Already Exists Yet putIfAbsent Still Replaces the Value

`"draft"` already had a null mapping, yet `putIfAbsent("draft", "ready")` still writes `"ready"`. The returned old value is null; it does not prove that the key was previously absent.

### 9.2. Two computeIfAbsent Calls Return null with Different Presence Outcomes

For `"missing"`, the function returns null and the key remains absent. For `"explicit-null"`, the function also returns null, yet the key still retains its null mapping:

```text
hasMissingAfterCompute=false
hasExplicitNullAfterComputeIfAbsent=true
```

Next, `computeIfPresent` does not run the function for `"explicit-null"`; the function body contains an `AssertionError` so the program fails if the “does not run” assumption is wrong.

Finally, `compute(... -> null)` removes the mapping for `"explicit-null"`, so `containsKey` becomes false.

### 9.3. The Mapping Function Must Handle a Null Key If the Application Allows It

The call `computeIfAbsent(null, ...)` uses a function that checks `key == null`, so it produces `"default"` for the null key.

If the function were replaced with `key -> key.toUpperCase()`, an exception could come from the function body calling a method on null, even though the map accepts a null key. Container rules do not replace data checks inside the function passed by the application.

### 9.4. A Null Old Value Is Not Passed to Integer::sum on the First merge

`counts` starts with `"hits" → null`. The first `merge` takes the value `1` directly, so the result is `1`; it does not attempt to add a null `Integer`.

The next call has old value `1`, combining with `2` to produce `3`. The following call's remapping function returns null, removing the mapping. Passing a null incoming value to another `merge` call is rejected with `NullPointerException`.

The computation functions in the example do not themselves add or remove mappings in the map while running. Return results according to the contract rather than mutating the map itself from inside the function and expecting simple semantics.

## 10. Iteration and Computation Must Account for Possible null

`HashMap.forEach` and the views do not automatically skip mappings with null keys or null values.

The snippets below are **error-prone patterns, for analysis only**, assuming the map allows and currently contains null:

```java
// May fail because key is null.
map.forEach((key, value) -> System.out.println(key.length()));

// May fail on unboxing because an Integer value is null.
for (Integer value : stock.values()) {
    int quantity = value;
}
```

If display is needed, a replacement string can be used solely for presentation. If computation is needed, you must decide what null means first.

For example, “unknown quantity” is different from “quantity equals 0.” Automatically turning null into `0` can make a total look complete even though part of the data is undetermined.

### getOrDefault Can Still Cause an Unboxing Error

The following illustration can also throw `NullPointerException` if `"draft"` is already mapped to null:

```java
// stock is Map<String, Integer> and has "draft" -> null.
int count = stock.getOrDefault("draft", 0);
```

The fallback value `0` is not selected simply because the existing value is null. The method returns `Integer null`, and then the assignment must unbox it to `int` and fails.

When this error occurs during reading/unboxing, the null mapping itself is not removed.

## 11. Complete Program: Presenting and Summing Known Data

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class HashMapNullPresentationDemo {
    public static void main(String[] args) {
        Map<String, Integer> stock = new HashMap<>();
        stock.put(null, null);
        stock.put("pen", 3);
        stock.put("draft", null);

        List<String> rows = new ArrayList<>();
        stock.forEach((key, value) -> {
            String keyText = Objects.toString(key, "<null-key>");
            String valueText = Objects.toString(value, "<null-value>");
            rows.add(keyText + "=" + valueText);
        });
        Collections.sort(rows);
        System.out.println("rows=" + rows);

        int knownTotal = 0;
        int unknownCount = 0;
        for (Integer value : stock.values()) {
            if (value == null) {
                unknownCount++;
            } else {
                knownTotal += value;
            }
        }
        System.out.println("knownTotal=" + knownTotal);
        System.out.println("unknownCount=" + unknownCount);

        try {
            int count = stock.get("draft");
            System.out.println("unexpectedCount=" + count);
        } catch (NullPointerException expected) {
            System.out.println("nullUnboxing=NullPointerException");
        }
        System.out.println("draftStillExists=" + stock.containsKey("draft"));
    }
}
```

Save as `HashMapNullPresentationDemo.java`, then compile and run:

```shell
javac --release 17 -encoding UTF-8 HashMapNullPresentationDemo.java
java HashMapNullPresentationDemo
```

Exact output:

```text
rows=[<null-key>=<null-value>, draft=<null-value>, pen=3]
knownTotal=3
unknownCount=2
nullUnboxing=NullPointerException
draftStillExists=true
```

### Why Are Rows Put into a List and Sorted?

`HashMap` does not guarantee iteration order. The program collects display rows into a separate list and sorts the strings to produce deterministic stdout.

The labels `<null-key>` and `<null-value>` are purely for display. The program does not replace the null key with a label string and does not replace null values in the map with another string.

In a real application, labels should be chosen so readers understand them. If real data could contain the same label string, a distinguishable presentation is needed; do not treat a display label as a data identifier.

### knownTotal Does Not Claim Every Quantity Is Known

Two mappings with null values are counted in `unknownCount=2`; the value `3` contributes to `knownTotal=3`.

The variable name and output state that this is the sum of the known portion of the data. They do not silently assume the two unknown values equal `0`.

The unboxing section intentionally triggers an error on `stock.get("draft")`. After catching the exception, `draftStillExists=true` confirms that reading does not make the mapping disappear.

## 12. Transferring Data to Another Map Requires Checking Its Null Policy

The declared type `Map<K, V>` does not force every implementation to allow null keys and null values. `HashMap` has the specific policy described above; changing how a map is created or changing its implementation can change that policy.

| Creation Method or Map Type | Relevant Null Key/Value Behavior |
|---|---|
| `new HashMap<>()` | Allows one null key, multiple null values |
| `new HashMap<>(source)` | Can copy valid null mappings from an existing source map |
| `Map.of(...)` | Rejects null keys and null values |
| `Map.copyOf(source)` | Rejects mappings with null keys or null values |
| `Collections.unmodifiableMap(source)` | A read-through wrapper over `source`; does not strip or forbid nulls already in `source` |
| `ConcurrentHashMap` | Rejects null keys and null values |

Do not read this table as meaning these options are interchangeable by swapping one line:

- A mutable map differs from an unmodifiable map.
- A copied map differs from a live wrapper.
- The null policy is another axis that must be examined explicitly.

### Copying null Does Not Mean the Source Can Be null

`new HashMap<>(source)` can copy a null-key or null-value mapping from the source. However, `source` itself must still be a valid map; passing a null source map argument is a different error from an entry inside the source containing null.

Similarly, `putAll` into a mutable `HashMap` can copy null values from the source; it does not skip or filter them out. If a key already exists, a source null value can overwrite the previous value in the target.

### Unmodifiable Does Not Mean Null-Free

An `unmodifiableMap` wrapper prevents modifying mappings through the wrapper, but if the source allows null, reads through the wrapper can still observe null. If the source is validly modified through another reference, the wrapper can see those changes.

Conversely, factories such as `Map.of` both create unmodifiable maps and enforce a null-rejection policy. You must not infer the policy of all unmodifiable maps from one group of factories alone.

### When Switching to ConcurrentHashMap

`ConcurrentHashMap` disallowing null is a difference that must be handled in terms of data semantics. You should not simply drop null mappings or replace them with `0`, an empty string, or an arbitrary object without defining the business rule.

You may need an explicit state such as “not yet loaded,” “not found,” “data present,” or a dedicated result type. This lesson does not replace concurrent-access design; the point to remember is that data acceptance policies also change when switching implementations.

## 13. Complete Program: Copies, Wrappers, and Input Validation

```java
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;

public class HashMapNullCopyPoliciesDemo {
    private static void expectNullPointer(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected NullPointerException");
        } catch (NullPointerException expected) {
            System.out.println(label + "=NullPointerException");
        }
    }

    private static void putNonNull(
            Map<String, String> target, String key, String value) {
        Objects.requireNonNull(key, "key");
        Objects.requireNonNull(value, "value");
        target.put(key, value);
    }

    public static void main(String[] args) {
        Map<String, String> source = new HashMap<>();
        source.put(null, "default");
        source.put("draft", null);

        Map<String, String> copied = new HashMap<>(source);
        Map<String, String> readOnly = Collections.unmodifiableMap(source);
        System.out.println("copyHasNullKey=" + copied.containsKey(null));
        System.out.println("copyHasDraft=" + copied.containsKey("draft"));
        System.out.println("copyDraftValue=" + copied.get("draft"));

        source.put("draft", "ready");
        source.put("later", null);
        System.out.println("copyDraftAfterSourceUpdate=" + copied.get("draft"));
        System.out.println("readOnlyDraft=" + readOnly.get("draft"));
        System.out.println("readOnlyHasLater=" + readOnly.containsKey("later"));

        try {
            readOnly.put("new", "value");
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println("readOnlyPut=UnsupportedOperationException");
        }

        expectNullPointer("mapCopyOf", () -> Map.copyOf(source));
        expectNullPointer("mapOfNullValue", () -> Map.of("draft", null));
        expectNullPointer("mapOfNullKey", () -> Map.of(null, "default"));

        Map<String, String> concurrent = new ConcurrentHashMap<>();
        expectNullPointer("concurrentNullKey",
                () -> concurrent.put(null, "value"));
        expectNullPointer("concurrentNullValue",
                () -> concurrent.put("draft", null));

        Map<String, String> validated = new HashMap<>();
        putNonNull(validated, "ok", "ready");
        expectNullPointer("boundaryNullKey",
                () -> putNonNull(validated, null, "value"));
        expectNullPointer("boundaryNullValue",
                () -> putNonNull(validated, "draft", null));
        System.out.println("validatedSize=" + validated.size());
        System.out.println("validatedHasNullKey="
                + validated.containsKey(null));
        System.out.println("validatedHasNullValue="
                + validated.containsValue(null));
    }
}
```

Save as `HashMapNullCopyPoliciesDemo.java`, then compile and run:

```shell
javac --release 17 -encoding UTF-8 HashMapNullCopyPoliciesDemo.java
java HashMapNullCopyPoliciesDemo
```

Exact output:

```text
copyHasNullKey=true
copyHasDraft=true
copyDraftValue=null
copyDraftAfterSourceUpdate=null
readOnlyDraft=ready
readOnlyHasLater=true
readOnlyPut=UnsupportedOperationException
mapCopyOf=NullPointerException
mapOfNullValue=NullPointerException
mapOfNullKey=NullPointerException
concurrentNullKey=NullPointerException
concurrentNullValue=NullPointerException
boundaryNullKey=NullPointerException
boundaryNullValue=NullPointerException
validatedSize=1
validatedHasNullKey=false
validatedHasNullValue=false
```

### 13.1. HashMap Copies Null Mappings

`copied` contains the null key and the `"draft"` key with a null value. After the source changes `"draft"` to `"ready"`, the copy still retains its own old mapping.

This is independence of the mapping structure, not a deep copy of objects. The example uses `String` values to avoid mixing the null topic with mutating the contents of mutable objects.

### 13.2. The Wrapper Still Sees the Source

`readOnlyDraft=ready` and `readOnlyHasLater=true` because the wrapper reads through to the source. Attempting to write through the wrapper fails with `UnsupportedOperationException`.

These two facts do not contradict each other: disallowing writes through the wrapper reference is not snapshotting and freezing all source data.

### 13.3. Factories and Concurrent Maps Reject null

The three tests `Map.copyOf`, `Map.of`, and the two tests on `ConcurrentHashMap` verify their respective null restrictions.

The helper methods throw `AssertionError` if an operation expected to reject null instead runs normally. Thus the output is not just pre-printed messages; it reflects actual exceptions observed at runtime.

### 13.4. Boundary Validation Has a Scope of Guarantee

`putNonNull` calls `Objects.requireNonNull` on both key and value before writing. In the example, both null inputs are rejected, leaving the validated map with exactly one valid mapping.

However, a helper method does not by itself turn every `HashMap` into a null-forbidding map type. If another place holds a mutable reference and calls `put`, `putAll`, `replaceAll`, or changes a value through an entry directly, it can still write null.

To enforce a “no nulls” rule across an entire application, you must control write paths and data ownership. The generic declaration `Map<String, String>` alone does not make Java forbid passing null in key or value positions.

## 14. Choosing the Meaning of null Consistently

The library does not decide for you whether null means “not yet entered,” “does not exist,” “not applicable,” or “error.” If different parts of an application interpret it differently, the same null mapping can produce contradictory results.

Before choosing a representation, determine:

1. Do you need to distinguish “no record yet” from “record exists, value not yet set”?
2. Does a null key have a single business meaning, or is it just masking a missing identifier?
3. Could there be multiple records missing an identifier that must be kept separate?
4. Do computations, loaders, and merge operations treat null according to that same meaning?
5. Will the data be transferred to a factory or another implementation with a different null policy?

### When null Can Be a Suitable Representation

If an internal map is owned and accessed in a controlled way, states are clearly defined, all read/processing paths handle them thoroughly, and using null does not lose data that needs to be distinguished, it can be a viable representation choice.

For example, the state “record exists, description not yet entered” can be distinguished from “no record yet” by key presence, provided this policy is agreed upon consistently.

### When State Should Be Represented Explicitly

If there are multiple reasons a value is absent or multiple state transitions, a single null may not carry enough information. A data type with a state field or a dedicated result type often expresses the program's intent more accurately.

Do not mechanically replace null with an empty string, `0`, or a special key: those values may already be valid real data. Any replacement requires rules to avoid collapsing two distinct states into one.

An enum key or a meaningfully named key type sometimes expresses a “default” role more clearly than null. However, the choice should follow the data and usage, not merely the desire to avoid seeing the word null in code.

## 15. Common Pitfalls

| Symptom | Likely Cause | Semantically Sound Fix |
|---|---|---|
| Multiple records without codes leave only the last one | All used the same null key | Keep distinct identifiers or change structure to match business rules |
| `get` returns null and code concludes the key is absent | Ignoring the possibility of a null value | Check presence when distinction is needed |
| `getOrDefault` still returns null | The key has a null mapping | Choose an explicit fallback rule |
| `remove` returns null and code concludes nothing was removed | The old value may have been null | Record presence through an appropriate access mechanism |
| `compute(... -> null)` loses the key | Null is the removal signal in this method | Use the right API if you want to store a null value |
| `merge(k, null, fn)` throws an exception | This incoming parameter must be non-null | Do not generalize `put` policy to every method |
| Reading a count throws NullPointerException | Unboxing `Integer null` | Handle null before arithmetic |
| Converting to `Map.copyOf` fails | Source has null keys/values | Design a state conversion or choose a suitable structure |
| Unmodifiable wrapper still exposes null | Mutability restriction and null policy are separate axes | Understand the wrapper reads through to the source rather than sanitizing data |

## 16. Self-Check

### Question 1: Three Null-Key Writes

An empty map calls `put(null, "A")`, `put(null, "B")`, `put(null, "C")` in sequence. What are the size and current value of the null key?

**Answer:** Size `1`, value `"C"`. Three writes to the same key do not create three mappings.

### Question 2: Three Different Keys, Same Null Value

An empty map stores `"a" → null`, `"b" → null`, `"c" → null`. What is the size? Does this violate uniqueness?

**Answer:** Size is `3`. The keys are different; values are allowed to duplicate, so there is no violation.

### Question 3: null and "null"

A map has a null key and the string key `"null"`. Must they be the same key?

**Answer:** No. The string `"null"` is an object with content; null is a reference to no object.

### Question 4: get(null) Returns null

Can you conclude there is no null key?

**Answer:** No. There could be a `null → null` mapping. Use `containsKey(null)` when you need to distinguish presence, within an appropriate access mechanism.

### Question 5: Null Mapping and Fallback Value

Key `"draft"` exists with a null value. What does `getOrDefault("draft", "fallback")` return?

**Answer:** Null. The fallback value is used when no mapping exists, rather than replacing every null.

### Question 6: remove Returns null

A key exists with a null value, and `remove(k)` returns null. Could the removal have reduced the size?

**Answer:** Yes. The old value returned is null; the mapping may still have just been removed.

### Question 7: computeIfAbsent vs. compute

A key currently has a null mapping. Two separate calls in two independent scenarios are `computeIfAbsent(k, x -> null)` and `compute(k, (x, old) -> null)`. How does key presence differ afterward?

**Answer:** The first call keeps the existing null mapping; the second call removes the mapping. You cannot interpret every null return from a computation function as the same signal.

### Question 8: putIfAbsent

A key already exists, but its value is null. Can `putIfAbsent(k, "ready")` write `"ready"`?

**Answer:** Yes. The method also covers the case where the key currently maps to null, not only when `containsKey` is false.

### Question 9: merge with Null Input

`HashMap` allows null values, so is `merge(k, null, fn)` accepted just because of that?

**Answer:** No. The incoming value to `merge` must be non-null. You must read each method's contract.

### Question 10: Removing null via values

There are three mappings with null values. Is a single `values().remove(null)` guaranteed to remove all three?

**Answer:** No. It removes one matching occurrence if present. To filter out all of them, you must perform an appropriate filtering operation and accept dropping those mappings.

### Question 11: Does Unmodifiable Mean Non-Null?

A `Collections.unmodifiableMap` wrapper over a `HashMap` contains nulls. Can reads through the wrapper return null?

**Answer:** Yes. The wrapper does not filter or replace nulls; it prevents modifying mappings through the wrapper reference.

### Question 12: Counting Unknown Quantities

A map contains `"pen" → 3`, `"draft" → null`. Can you conclude the true total quantity is `3` if null means “unknown”?

**Answer:** You only know the sum of the known portion is `3`. There is still one undetermined value; do not turn it into `0` unless business rules specify that.

## 17. Practice: Preserving Full State When Reading

Write a program using `HashMap<String, Integer>` and create:

```text
null    → 5
"draft" → null
"ready" → 8
```

Perform the following:

1. Count the number of mappings, null keys, and null values.
2. Read `"draft"` and an absent key `"missing"`; print both value and presence.
3. Compare the `getOrDefault` results for both keys using the same fallback number.
4. Replace the null key's value with null; recount null values.
5. Remove `"draft"` alone and explain why the returned value can be null even though the size decreases.
6. Collect rows for display in a deterministic order without assuming HashMap order.
7. Try copying with `new HashMap<>(source)` and compare its policy with `Map.copyOf(source)`.

Milestones to reach:

```text
Initially: size = 3, null keys = 1, null values = 1.
draft exists; missing does not exist.
get for both can return null.
getOrDefault uses the fallback only for missing.
After put(null, null): null values = 2, size still = 3.
After remove("draft"): size = 2, null key remains.
```

Finally, state one business choice clearly:

- If null carries a meaningful state, describe how every read path preserves the distinction from an absent key.
- If the application forbids null, point out where validation happens and how to prevent other write paths from bypassing the rule.
- If multiple missing-value states are needed, propose a representation with explicit state names instead of collapsing everything into null.

The goal is to preserve data information and use the API according to its contract, not merely to stop the program from throwing exceptions.

## References

- [Java 17 — HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): support for null keys/values and update methods.
- [Java 17 — Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): distinguishing absent mappings from null values; `getOrDefault`, `compute`, `merge`, and null-rejecting factories.
- [Java 17 — Objects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html): displaying null references and validating inputs with `requireNonNull`.
- [Java 17 — Collections.unmodifiableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)): unmodifiable wrapper that reads through to the source map.
- [Java 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): policy rejecting null keys or null values.

All five standalone programs use APIs compatible with Java 17 and later, were compiled with `javac --release 17 -encoding UTF-8`, and ran on JDK 24.0.2. The output blocks are actual results; none depend on `HashMap`'s unguaranteed iteration order.
