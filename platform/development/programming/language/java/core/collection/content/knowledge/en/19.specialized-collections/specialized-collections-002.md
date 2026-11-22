# EnumMap: Mapping with Enum Keys

## 1. When the Key Domain Is a Known Set of Constants

Suppose a program has three stages: `PLANNED`, `RUNNING`, and `DONE`. Each stage needs a display label, a task count, or a list of related data. This is a **each enum key maps to a value** relationship, rather than merely a set of selected stages.

`EnumMap<K,V>` is a specialized `Map` implementation for cases where all keys belong to **a single enum type**. We still use familiar operations such as `put`, `get`, `remove`, and `containsKey`, but the structure knows the key type's constant domain in advance.

For example, with `EnumMap<Stage, String>`, the keys are the constants of `Stage` and the values are strings. With `EnumMap<Stage, List<Task>>`, the same key domain is used to group tasks. The value type is not restricted to an enum; only the key type has this constraint.

Three things to understand before writing code:

1. An EnumMap only accepts keys of the single enum type specified when the map is created.
2. Iteration order is the declaration order of the enum constants, not the order in which put is called.
3. Knowing the entire key domain does not mean the map already contains a mapping for every constant.

This lesson starts from an empty map, observes operations and null policies, and then moves on to copying, views, and counting/grouping applications. The complete programs use Java 17 or later.

## 2. Relationship Between enum, EnumMap, and Map

### 2.1. Keys Are Enum Constants, Not Constant String Names

Given the declaration `enum Stage { PLANNED, RUNNING, DONE }`, the valid keys of the stage map are `Stage.PLANNED`, `Stage.RUNNING`, and `Stage.DONE`. The string `"RUNNING"` is not of the same type as `Stage.RUNNING`.

`EnumMap` does not automatically convert user-entered strings into enum constants. If input arrives as a string, parsing and validation must occur at the input boundary according to application rules. Do not replace all keys with strings just to avoid modeling the data domain.

An enum constant has a stable identity within that enum type itself. Two different enums may both declare the name `RUNNING`, but their constants do not become the same key because of that. An EnumMap for Stage is not a shared map for every enum that happens to have the same constant name.

### 2.2. Key Type Constraint

The class signature is `EnumMap<K extends Enum<K>, V>`. That forces K to be an appropriate enum type. The common way to instantiate it, illustrated inside a method, is:

```java
EnumMap<Stage, String> labels = new EnumMap<>(Stage.class);
```

`Stage.class` is the `Class` object describing the enum type, not a key being inserted. The constructor uses that information even when the map has no entries yet.

If you only need to expose the mapping capability to calling code, you can declare the variable using the interface:

```java
// Illustration, assuming Stage has already been declared.
Map<Stage, String> labels = new EnumMap<>(Stage.class);
```

The object is still an EnumMap and still iterates in enum declaration order. The Map variable type indicates that the calling code only needs general map operations; it does not change how the underlying object stores and iterates over data.

### 2.3. Do Not Mix Multiple Enum Types in One EnumMap

Standard generics catch passing the wrong key type at compile time. Do not bypass generics or use raw types to insert an enum that does not belong to the key domain. Casting does not turn a constant of another enum into a valid constant of the enum chosen by the map.

For lookups via `get(Object)` or `containsKey(Object)`, an object that is not a key of this domain is not automatically interpreted by its name. The fact that the API accepts Object does not mean the map becomes a string lookup table or an arbitrary key store.

If you must obtain the enum type from a constant in generic code, the appropriate API is `getDeclaringClass()`. Do not assume `constant.getClass()` is always the declaring enum class itself, because a constant with a class body can have its own runtime subclass. In concrete code like the examples here, passing `Stage.class` directly is clearest. You can cross-check this at [Enum — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Enum.html).

## 3. Mechanism and Iteration Order

### 3.1. A Finite Enum Domain Enables a Specialized Representation

The [EnumMap — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumMap.html) documentation describes an internal array-based representation. Because the map knows a single enum type and its set of constants, it can associate each constant with its corresponding slot in the specialized structure.

This differs from having to support arbitrary key objects like a general-purpose map. Users do not need to manually create an array and use `ordinal()` everywhere to locate the value slot. EnumMap provides the full Map contract for insertion, removal, existence checks, and views.

`ordinal()` is the position of a constant in the enum declaration and is designed for specialized structures like this. Do not use ordinal as a business code or long-term storage identifier just because you understand the internal mechanism: changing the declaration order can change those position numbers.

### 3.2. Order Is Declaration Order, Not Alphabetical or Insertion Order

With `Stage { PLANNED, RUNNING, DONE }`, the iteration order of present keys always follows that declaration sequence. Even if you insert DONE first, PLANNED second, and RUNNING last, the map still iterates as PLANNED, RUNNING, DONE.

The views `keySet()`, `values()`, and `entrySet()` all reflect this key order. The values view is traversed according to the corresponding keys; it does not sort string or numeric values on its own.

`EnumMap` has no constructor taking a comparator to choose a different order. Having an iteration order does not mean it implements `SortedMap` or `NavigableMap`; there are no operations like `lowerKey`, `subMap`, or `descendingMap` just because the printed output looks ordered.

If a screen needs a display order different from the enum order, define a separate display order for that output pass. Do not arbitrarily reorder the enum declaration just to affect one display line without considering other places that depend on it.

### 3.3. A New Map Starts Empty

`new EnumMap<>(Stage.class)` only defines the key domain. It does not automatically add three mappings and does not assign default values to the constants.

If only RUNNING has been put, the size is one and only RUNNING appears during iteration. Knowing that PLANNED and DONE are usable keys is different from the map currently holding data for them.

## 4. Program 1: Creating a Map and Observing Operations

Save the complete program to `EnumMapBasicsDemo.java`:

```java
import java.util.EnumMap;
import java.util.Map;

public class EnumMapBasicsDemo {
    enum Stage { PLANNED, RUNNING, DONE }

    public static void main(String[] args) {
        EnumMap<Stage, String> labels = new EnumMap<>(Stage.class);
        System.out.println("initialSize=" + labels.size());
        labels.put(Stage.DONE, "finished");
        labels.put(Stage.PLANNED, "waiting");
        labels.put(Stage.RUNNING, "working");
        System.out.println("labels=" + labels);
        System.out.println("keys=" + labels.keySet());
        System.out.println("values=" + labels.values());
        System.out.println("oldValue=" + labels.put(Stage.RUNNING, "active"));
        System.out.println("sizeAfterUpdate=" + labels.size());
        System.out.println("running=" + labels.get(Stage.RUNNING));
        for (Map.Entry<Stage, String> entry : labels.entrySet()) {
            System.out.println(entry.getKey() + ":" + entry.getValue());
        }
        System.out.println("removed=" + labels.remove(Stage.PLANNED));
        System.out.println("remaining=" + labels);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 EnumMapBasicsDemo.java
java EnumMapBasicsDemo
```

Stdout:

```text
initialSize=0
labels={PLANNED=waiting, RUNNING=working, DONE=finished}
keys=[PLANNED, RUNNING, DONE]
values=[waiting, working, finished]
oldValue=working
sizeAfterUpdate=3
running=active
PLANNED:waiting
RUNNING:active
DONE:finished
removed=waiting
remaining={RUNNING=active, DONE=finished}
```

### 4.1. Insertion Order vs. Result Order

`initialSize=0` confirms that the constructor does not create mappings for all constants. The put calls are in the order DONE, PLANNED, RUNNING, yet the `labels` and `keys` lines still follow the declaration order PLANNED, RUNNING, DONE.

`values=[waiting, working, finished]` follows the key order. It is not sorted alphabetically by the strings, nor by the time each string was put into the map.

### 4.2. Updating an Existing Key and Removing a Mapping

`put(Stage.RUNNING, "active")` returns the old value `working`. The map still has three mappings; the RUNNING key does not get a second entry and does not move to the end as in insertion order.

The entry loop shows that the new value active sits right at RUNNING. `remove(Stage.PLANNED)` returns waiting and removes that mapping, leaving only RUNNING and DONE in their natural relative order.

The basic rules are still those of Map: each key corresponds to at most one mapping; putting an existing key replaces its value; removing deletes the mapping rather than removing the enum constant from the language or from the Stage type.

## 5. Null and Missing Mappings

### 5.1. Null Keys Are Rejected, Null Values Are Allowed

EnumMap rejects `put(null, value)` with a `NullPointerException`. Null is not a constant of the enum type chosen by the map.

However, the map allows mappings with a null value. Therefore, after `put(Day.MON, null)`, the key MON still has a mapping and is counted in `size()`.

Operations that check or remove a null key do not behave the same way as inserting a null key: on EnumMap, `containsKey(null)` returns false, `get(null)` returns null, and `remove(null)` returns null. Do not infer that every method accepting null must throw, nor infer from `get(null)` working that `put(null, ...)` is allowed.

### 5.2. Three States to Distinguish

| State for a valid enum key | `get(key)` | `containsKey(key)` | Counted in size? |
|---|---|---|---|
| No mapping yet | null | false | No |
| Mapping with null value | null | true | Yes |
| Mapping with non-null value | That value | true | Yes |

`getOrDefault` only uses the default when there is no mapping. It does not replace a null value of an existing mapping with the default.

Conversely, methods such as `putIfAbsent`, `computeIfAbsent`, and `merge` have their own rules regarding null values. You cannot use a single rule like “if the key is present, every operation leaves it unchanged” to describe all of them. In the next example, `putIfAbsent` treats a null-valued mapping as a case where a value can be set.

### 5.3. Having All Keys and Having All Non-Null Values Are Two Different Requirements

If an application requires every day to have a configuration, you must check that all constants have a mapping. If it also requires non-null configurations, you must check the value condition as well.

An EnumMap whose mapping count equals the number of constants in the key domain has a mapping for every constant, yet may still contain null values. Conversely, all existing mappings being non-null does not prove that every constant is covered.

## 6. Program 2: Null Values and Key Coverage Checks

Save to `EnumMapNullCoverageDemo.java`. `EnumSet` is used to compute the days that do not yet have mappings; it does not replace the EnumMap holding the schedule.

```java
import java.util.EnumMap;
import java.util.EnumSet;

public class EnumMapNullCoverageDemo {
    enum Day { MON, TUE, WED }

    public static void main(String[] args) {
        EnumMap<Day, String> schedule = new EnumMap<>(Day.class);
        schedule.put(Day.MON, null);
        schedule.put(Day.WED, "work");
        System.out.println("monGet=" + schedule.get(Day.MON));
        System.out.println("monPresent=" + schedule.containsKey(Day.MON));
        System.out.println("tueGet=" + schedule.get(Day.TUE));
        System.out.println("tuePresent=" + schedule.containsKey(Day.TUE));
        System.out.println("size=" + schedule.size());
        System.out.println("monDefault=" + schedule.getOrDefault(Day.MON, "off"));
        System.out.println("tueDefault=" + schedule.getOrDefault(Day.TUE, "off"));
        System.out.println("nullGet=" + schedule.get(null));
        System.out.println("nullPresent=" + schedule.containsKey(null));
        System.out.println("nullRemove=" + schedule.remove(null));
        try {
            schedule.put(null, "invalid");
            throw new AssertionError("Expected NullPointerException");
        } catch (NullPointerException expected) {
            System.out.println("nullPut=NullPointerException");
        }
        EnumSet<Day> missing = EnumSet.allOf(Day.class);
        missing.removeAll(schedule.keySet());
        System.out.println("missingMappings=" + missing);
        System.out.println("oldNullValue=" + schedule.putIfAbsent(Day.MON, "study"));
        System.out.println("afterPutIfAbsent=" + schedule);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 EnumMapNullCoverageDemo.java
java EnumMapNullCoverageDemo
```

Stdout:

```text
monGet=null
monPresent=true
tueGet=null
tuePresent=false
size=2
monDefault=null
tueDefault=off
nullGet=null
nullPresent=false
nullRemove=null
nullPut=NullPointerException
missingMappings=[TUE]
oldNullValue=null
afterPutIfAbsent={MON=study, WED=work}
```

### 6.1. MON Has a Mapping, TUE Does Not

Both `monGet` and `tueGet` print null, but `monPresent=true` while `tuePresent=false`. `size=2` counts MON and WED.

`monDefault=null` because MON already has a null mapping. `tueDefault=off` because TUE has no mapping yet. This is an essential distinction when writing default configurations or checking for missing data.

### 6.2. Computing the Set of Missing Keys

`EnumSet.allOf(Day.class)` creates the set of all Day constants. Removing the keys currently present in schedule leaves `[TUE]`. MON is not flagged as missing a mapping even though its value is null.

If the rule is that every day must have a non-null schedule string, this check alone is not enough; you need to inspect each day's value. EnumMap does not know on its own whether a null value is valid under business rules.

### 6.3. putIfAbsent with a Null Old Value

`putIfAbsent(Day.MON, "study")` returns null and sets MON to study. The mapping count does not increase because MON was already present; the value changes because `putIfAbsent`'s policy also applies when a key is currently mapped to null.

When deciding to allow null values in an application API, you must account for the effect on any additional Map methods you use. A wrapper layer may choose to forbid null values for a simpler contract, but that is an application-level policy, not an inherent limitation of EnumMap.

## 7. Choosing the Right Constructor When Creating or Copying

### 7.1. Key Type Known in Advance: Pass the Enum's Class

The `EnumMap(Class<K> keyType)` constructor creates an empty map with the specified key domain. This is the clear choice when initializing a new configuration, label table, or data grouping.

There is no no-arg constructor like `new EnumMap<Stage, String>()`. Generic type information in source code cannot substitute for the Class information needed at runtime for the structure to know the constant domain.

`Stage.class` can be used even before any mappings or constants have been placed in the map. An enum type that declares no constants at all can still have an empty EnumMap of that type; knowing the type and having elements are two separate concerns.

### 7.2. Copying from an EnumMap

The constructor accepting an EnumMap obtains the key type from the source map itself, so an empty source map is still valid. It creates a new map structure initially containing the same mappings, if any.

This is useful when you want a configuration copy whose mappings can be modified independently of the current one. However, if the values are mutable objects, the maps can still share references; the constructor does not deep-copy data inside the values.

EnumMap's `clone()` is also described as a shallow copy. In the examples, the copy constructor is used so the intent to create a new map is clear right at the declaration site.

### 7.3. Copying from a General Map

The `EnumMap(Map<K, ? extends V> source)` constructor has two cases:

| Actual source object | Can it be empty? | How the enum domain is determined |
|---|---|---|
| Is an EnumMap | Yes | Uses the key type already held by the source EnumMap |
| Is another map, such as HashMap | No | Needs at least one mapping to infer the enum type from a key |

Therefore, it is incorrect to say every constructor taking a Map rejects empty maps. A variable declared as Map that points to an empty EnumMap is still handled as an EnumMap source.

Conversely, an empty `HashMap<Size, String>` still provides no actual key to infer the enum at runtime, even though the programmer sees Size in the generic type. The constructor throws `IllegalArgumentException` instead of guessing the type.

### 7.4. When the Source May Be Empty, Pass the Type Explicitly Then Call putAll

If a method already knows the key type Size but receives a source Map that might be empty, it can create `new EnumMap<>(Size.class)` first and then call `putAll(source)`. Copying an empty source into a map whose key domain is already known is valid.

This separates two responsibilities: specifying the key domain via Class, and then populating the existing mappings. There is no need to insert a dummy mapping just to let the constructor infer the type.

## 8. Program 3: Constructor Cases and Independence

Save the complete program to `EnumMapConstructorsDemo.java`:

```java
import java.util.EnumMap;
import java.util.HashMap;
import java.util.Map;

public class EnumMapConstructorsDemo {
    enum Size { SMALL, MEDIUM, LARGE }

    public static void main(String[] args) {
        EnumMap<Size, String> empty = new EnumMap<>(Size.class);
        EnumMap<Size, String> directCopy = new EnumMap<>(empty);
        Map<Size, String> emptyAsMap = empty;
        EnumMap<Size, String> runtimeEnumCopy = new EnumMap<>(emptyAsMap);
        System.out.println("emptyDirectCopy=" + directCopy.size());
        System.out.println("emptyRuntimeEnumCopy=" + runtimeEnumCopy.size());
        try {
            new EnumMap<Size, String>(new HashMap<Size, String>());
            throw new AssertionError("Expected IllegalArgumentException");
        } catch (IllegalArgumentException expected) {
            System.out.println("emptyHashCopy=IllegalArgumentException");
        }
        Map<Size, String> source = new HashMap<>();
        source.put(Size.LARGE, "L");
        source.put(Size.SMALL, "S");
        EnumMap<Size, String> inferred = new EnumMap<>(source);
        System.out.println("inferred=" + inferred);
        source.put(Size.SMALL, "S2");
        inferred.put(Size.MEDIUM, "M");
        System.out.println("sourceSmall=" + source.get(Size.SMALL));
        System.out.println("copiedSmall=" + inferred.get(Size.SMALL));
        System.out.println("sourceHasMedium=" + source.containsKey(Size.MEDIUM));
        System.out.println("independentCopy=" + inferred);
        EnumMap<Size, String> explicit = new EnumMap<>(Size.class);
        explicit.putAll(new HashMap<Size, String>());
        System.out.println("explicitWithEmptySource=" + explicit.size());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 EnumMapConstructorsDemo.java
java EnumMapConstructorsDemo
```

Stdout:

```text
emptyDirectCopy=0
emptyRuntimeEnumCopy=0
emptyHashCopy=IllegalArgumentException
inferred={SMALL=S, LARGE=L}
sourceSmall=S2
copiedSmall=S
sourceHasMedium=false
independentCopy={SMALL=S, MEDIUM=M, LARGE=L}
explicitWithEmptySource=0
```

### 8.1. Both Ways of Copying an Empty EnumMap Work

`emptyDirectCopy=0` is a copy from an EnumMap variable. `emptyRuntimeEnumCopy=0` is a copy from a Map variable pointing to the same empty EnumMap. Both succeed because the source object retains the Size domain.

`emptyHashCopy=IllegalArgumentException` shows the other case: an empty HashMap does not retain the enum domain through that specialized mechanism for EnumMap to infer.

### 8.2. A Non-Empty Source Is Copied in Enum Order

The HashMap source has SMALL and LARGE. When inferred is created, the new map has `{SMALL=S, LARGE=L}` in Size declaration order, independent of the source HashMap's iteration order. The example avoids printing the entire HashMap so it does not rely on an order that HashMap does not guarantee.

Next, updating SMALL in source to S2 does not change the SMALL mapping in the copy. Adding MEDIUM to inferred does not add MEDIUM to source. The `independentCopy` line shows all three mappings in SMALL, MEDIUM, LARGE order.

Finally, creating a map with `Size.class` and calling `putAll` with an empty HashMap gives size 0, which is completely valid. This approach also works when the source has matching data.

## 9. EnumMap Views

### 9.1. keySet, values, and entrySet View the Same Data

EnumMap views are live views backed by the map, not copied collections. Adding or removing a mapping in the map is reflected when inspecting previously obtained views.

| View | Elements | Iteration order |
|---|---|---|
| `keySet()` | Enum constants that currently have a mapping | Enum declaration order |
| `values()` | Values of the mappings | Corresponding key order |
| `entrySet()` | Key–value pairs | Enum key order |

If the map does not contain every constant, `keySet` is not the set of all constants either. When you need the full domain, use `values()` on the enum type or an EnumSet of all constants; do not confuse `Stage.values()` with `labels.values()`.

### 9.2. Removing Through a View Affects the Map

`keys.remove(enumKey)` removes the mapping for that key. `values.remove(value)` removes one mapping with a matching value per collection view behavior, which does not mean removing all mappings with the same value. Calling `clear()` through a view that supports removal removes the corresponding mappings from the map.

The key view does not support `add` or `addAll`. A lone key does not specify the value to assign to the mapping. To add entries, use `put` with both key and value. Do not assume that because the map is modifiable, every mutating method on every view is supported.

### 9.3. Updating Through an Entry During Iteration

During an `entrySet()` traversal of an EnumMap, you can use `entry.setValue(newValue)` to update the value of the corresponding mapping. When doing so, the key remains the same enum constant and the order does not change.

Do not hold onto an entry obtained from an iterator and assume it is a durable snapshot across subsequent structural changes. If you need to retain independent data, copy it into a type with an appropriate contract rather than relying on a backing lifecycle not designed for that purpose.

## 10. Program 4: Backed Views, Entry Updates, and Map.equals

Save to `EnumMapViewsDemo.java`. All operations are performed sequentially; the example does not rely on whether an iterator observes or skips interleaved structural modifications.

```java
import java.util.Collection;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public class EnumMapViewsDemo {
    enum Mode { FAST, SAFE, DEBUG }

    public static void main(String[] args) {
        EnumMap<Mode, Integer> map = new EnumMap<>(Mode.class);
        map.put(Mode.DEBUG, 30);
        map.put(Mode.SAFE, 10);
        map.put(Mode.FAST, 10);
        Set<Mode> keys = map.keySet();
        Collection<Integer> values = map.values();
        System.out.println("initial=" + map);
        System.out.println("removeSafe=" + keys.remove(Mode.SAFE));
        System.out.println("removeValue10=" + values.remove(10));
        System.out.println("afterViewRemovals=" + map);
        map.put(Mode.SAFE, 20);
        System.out.println("sameKeyView=" + keys);
        System.out.println("sameValueView=" + values);
        for (Map.Entry<Mode, Integer> entry : map.entrySet()) {
            entry.setValue(entry.getValue() + 1);
        }
        System.out.println("afterEntryUpdate=" + map);
        try {
            keys.add(Mode.FAST);
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println("keyAdd=UnsupportedOperationException");
        }
        Map<Mode, Integer> hash = new HashMap<>(map);
        System.out.println("enumEqualsHash=" + map.equals(hash));
        System.out.println("hashEqualsEnum=" + hash.equals(map));
        EnumMap<Mode, Integer> copy = new EnumMap<>(map);
        map.clear();
        System.out.println("keyViewAfterClear=" + keys);
        System.out.println("valueViewAfterClear=" + values);
        System.out.println("copyAfterClear=" + copy);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 EnumMapViewsDemo.java
java EnumMapViewsDemo
```

Stdout:

```text
initial={FAST=10, SAFE=10, DEBUG=30}
removeSafe=true
removeValue10=true
afterViewRemovals={DEBUG=30}
sameKeyView=[SAFE, DEBUG]
sameValueView=[20, 30]
afterEntryUpdate={SAFE=21, DEBUG=31}
keyAdd=UnsupportedOperationException
enumEqualsHash=true
hashEqualsEnum=true
keyViewAfterClear=[]
valueViewAfterClear=[]
copyAfterClear={SAFE=21, DEBUG=31}
```

### 10.1. Removing via Keys and via Values

The map has DEBUG, SAFE, FAST inserted, yet prints `{FAST=10, SAFE=10, DEBUG=30}`. Removing SAFE through keys removes the SAFE=10 mapping.

After that, values only has one 10 left, corresponding to FAST. `values.remove(10)` removes that mapping, leaving only DEBUG=30 in the map. This call does not return the removed value; it returns a boolean indicating whether the collection changed.

Putting SAFE=20 through the map causes the previously obtained views to print `[SAFE, DEBUG]` and `[20, 30]`, reflecting the new state in enum order.

### 10.2. Changing Values Without Changing Keys

The entry loop adds one to each existing value, producing `{SAFE=21, DEBUG=31}`. This updates the two existing values; it does not create two new keys or fill in any missing constants. FAST still has no mapping.

`keys.add(Mode.FAST)` is rejected with `UnsupportedOperationException`. To add FAST, you must specify a value with a put call.

### 10.3. Equality with Another Map and Copies

The HashMap created from the current map has the same mappings, so equals is true in both directions. Map equality does not require the two objects to have the same implementation, nor does it check for the same iteration order.

The EnumMap copy created before clear retains SAFE=21 and DEBUG=31. After `map.clear()`, the old views of the original map are empty while copy still holds data. A view and a copy are two different relationships.

## 11. Weakly Consistent Iterators Do Not Mean Thread-Safe

Iterators from EnumMap's collection views are described as **weakly consistent**: they do not throw `ConcurrentModificationException`, and they may or may not reflect modifications made while iteration is in progress.

You should not write an example with interleaved adds/removes and present a single stdout as a guarantee across all environments when the contract permits multiple observable outcomes. The examples here keep operations in clear phases so the results are deterministic.

The absence of an exception does not prove the map has synchronization. EnumMap is not synchronized for concurrent access across threads. If one thread modifies while other threads use the same map, a design that coordinates all access paths is required.

In particular, sequences such as checking for absence and then putting, or reading a count, adding, and writing back, do not become atomic simply because the structure is EnumMap. Default Map methods like merge or computeIfAbsent on this structure also do not carry the concurrent update guarantees of a concurrent map.

If a program needs a consistent snapshot of data to process, creating the copy must also occur under appropriate access control. Copying while the source is being modified without coordination does not create a transactional snapshot on its own.

## 12. Application: Counting and Grouping Data by Enum

### 12.1. Full Counts vs. Groups Created Only When Needed

An event stream with levels LOW, MEDIUM, HIGH often needs two forms of data:

- Counts for every level, including levels that have not appeared.
- Lists of messages for the levels that actually had events.

Both use the Severity key domain, but have different initialization policies. The counts map is populated with 0 for all constants from the start. The groups map starts empty and creates a list only when the corresponding level is encountered.

Save the complete program to `EnumMapGroupingDemo.java`:

```java
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;

public class EnumMapGroupingDemo {
    enum Severity { LOW, MEDIUM, HIGH }
    record Event(Severity severity, String message) {}

    public static void main(String[] args) {
        List<Event> events = List.of(
                new Event(Severity.HIGH, "server"),
                new Event(Severity.LOW, "typo"),
                new Event(Severity.HIGH, "disk"));
        EnumMap<Severity, Integer> counts = new EnumMap<>(Severity.class);
        for (Severity severity : Severity.values()) {
            counts.put(severity, 0);
        }
        EnumMap<Severity, List<String>> groups = new EnumMap<>(Severity.class);
        for (Event event : events) {
            counts.merge(event.severity(), 1, Integer::sum);
            groups.computeIfAbsent(event.severity(), key -> new ArrayList<>())
                    .add(event.message());
        }
        System.out.println("counts=" + counts);
        System.out.println("groups=" + groups);
        System.out.println("independentLists="
                + (groups.get(Severity.LOW) != groups.get(Severity.HIGH)));
        for (Severity severity : Severity.values()) {
            System.out.println(severity + ": count=" + counts.get(severity)
                    + ", messages=" + groups.getOrDefault(severity, List.of()));
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 EnumMapGroupingDemo.java
java EnumMapGroupingDemo
```

Stdout:

```text
counts={LOW=1, MEDIUM=0, HIGH=2}
groups={LOW=[typo], HIGH=[server, disk]}
independentLists=true
LOW: count=1, messages=[typo]
MEDIUM: count=0, messages=[]
HIGH: count=2, messages=[server, disk]
```

### 12.2. Why Is MEDIUM Still Printed Even With No Events?

The input data only has HIGH, LOW, HIGH. The loop over `Severity.values()` created count mappings for LOW, MEDIUM, and HIGH, so the count result has MEDIUM=0.

The groups map was not pre-populated with every key. `computeIfAbsent` only created lists for LOW and HIGH when events were encountered. Since MEDIUM never appeared, groups does not contain that key. When displaying results, `getOrDefault(severity, List.of())` supplies an empty list for reading.

The counts map and the groups map do not contradict each other. They share the same key domain but represent two kinds of information with different policies for missing mappings.

### 12.3. merge Updates the Count

`counts.merge(severity, 1, Integer::sum)` adds one to an existing non-null count. In the example, every level was initialized to 0, so after three events we have LOW=1, MEDIUM=0, HIGH=2.

By the Map contract, if a key is absent or associated with null, merge uses the provided value to set the mapping instead of calling the remapping function as it does for a non-null value. The value passed to merge in the example is 1, which is non-null.

Using merge here makes the update operation clear in sequential code. It does not turn EnumMap into an atomic concurrent update structure.

### 12.4. Each Group Needs Its Own List

`key -> new ArrayList<>()` creates a new list when a level does not yet have a non-null list. HIGH events are added to HIGH's own list in order of appearance: server then disk.

`independentLists=true` proves LOW and HIGH do not point to the same list. If you used a single shared mutable list as the value for all keys, adding a message for one level would make other levels see the same message through the shared reference.

`List.of()` in `getOrDefault` is only used as an empty result for reading when a group is missing. It is not put into groups and then passed to `add`, and it is not used in place of an ArrayList that needs to be mutated.

The key order LOW, MEDIUM, HIGH is determined by the enum; the message order inside each List is determined by how the input data is processed. EnumMap does not sort elements inside values on its own.

## 13. Choosing the Right Structure for an Enum Domain

| Need | Suitable structure to consider | Key distinction |
|---|---|---|
| Each enum constant associated with a value | `EnumMap<E,V>` | Has a key–value relationship |
| Only track which constants are selected | `EnumSet<E>` | Only presence/absence needed, no separate V value |
| Keys of multiple types or an open key domain | General-purpose Map as required | Not the key domain of a single enum |
| Need neighbor or range lookups by a custom comparator | A suitable navigable ordered Map | EnumMap does not provide the NavigableMap API |

EnumMap is usually a reasonable starting point when the requirement is genuinely a mapping keyed by a single enum type. The array representation leverages the finite key domain; basic operations have constant-time cost according to the implementation description. However, do not turn that into a claim that every program is faster than every use of HashMap.

Iterating, copying, or processing large values still carries its own cost. An EnumMap holding long lists does not make operations on those lists constant-time. When performance is a specific requirement, measure the actual operations and data in use.

### 13.1. A Mapping Table Does Not Enforce Exhaustiveness Like a Selection Expression

EnumMap is well suited for label tables, per-state configurations, data grouping, and possibly tables mapping enum constants to handler functions. However, creating a map does not make the compiler enforce that every constant has a mapping.

When a new enum constant is added, the mapping table may still compile while missing configuration for that constant. If an API requires a complete table, validate the constant domain at initialization or with an explicit check, rather than waiting for `get` to return null on a rarely executed path.

### 13.2. Mutability and Data Sharing

Declaring a variable as `Map` does not make the data read-only. Returning the EnumMap or its key view directly to another component can grant permission to modify or remove mappings. If an API needs restricted read access or a separate data copy, design the return value to match that requirement.

You should also distinguish replacing a mapping from mutating a value object. An EnumMap copy that is structurally independent can still hold the same List or configuration object as the source. When mutable value data must also be isolated, copy the values according to that type's contract.

## 14. Testing an EnumMap Table

### 14.1. Checks Worth Writing

1. A map created with Class starts empty and accepts the intended enum domain.
2. Insertions in any order still iterate in declaration order.
3. Putting the same key returns the old value, does not increase size, and does not change order.
4. Null keys are rejected on insertion; null values are represented differently from missing mappings.
5. If the table must be complete, every constant has a mapping and satisfies the application's value condition.
6. Copying from an empty EnumMap succeeds; an empty general map is handled by specifying Class explicitly.
7. Removing through a view affects the source as specified by the contract; a copy does not update automatically with the source.
8. When grouping data, keys do not accidentally share the same mutable collection.

Check order using a list of keys in iteration order. `Map.equals` or `Set.equals` checks mappings or element sets, not order.

Do not use the fact that an iterator does not throw `ConcurrentModificationException` to test thread safety. Do not rely on a single observed outcome of interleaved modifications where the weakly consistent contract allows seeing or not seeing them.

### 14.2. Note on Numeric Values

The view example adds one to Integer values that were already initialized as non-null. If an application allows null values, numeric operations may need an explicit policy before Java auto-unboxes the Integer. The fact that EnumMap allows null does not automatically supply a default numeric value.

In the counting example, populating 0 for every level is an explicit representation decision, not automatic constructor behavior.

## 15. Common Pitfalls

| Misconception | Consequence | How to handle |
|---|---|---|
| EnumMap accepts any enum in the same map | Wrong key domain | Specify a single enum type |
| A constant's string name is an enum key | Fails to look up as intended or wrong type | Convert and validate input before using constants |
| Generics are enough to use a no-arg constructor | No matching constructor exists | Pass the enum's Class |
| Because the map knows the enum domain, all mappings already exist | `get` returns null, size is smaller than expected | Proactively initialize or check coverage |
| Iteration order follows put calls | Wrong prediction of results | Follows enum declaration order |
| Having order means having comparator/subMap | Wrong API usage | Distinguish EnumMap from SortedMap/NavigableMap |
| Getting null means the key is missing | Misses mappings with null values | Use `containsKey` when you need to distinguish |
| `getOrDefault` replaces any null value | Default is not used as expected | Understand it only applies when a mapping is missing |
| Any empty Map can be copied into an EnumMap | `IllegalArgumentException` for non-EnumMap sources | Pass Class then call `putAll` |
| Every constructor taking a Map rejects empty sources | Overlooks sources that are actually EnumMaps | Read the key-domain inference rules accurately |
| `keySet` is an independent set | `remove` deletes mappings from the source | Create a collection copy if independence is needed |
| Copying a map deep-copies all values | Unintended sharing of mutable data | Define how values are copied |
| Iterator not throwing means thread-safe | Uncoordinated state access may occur | Design synchronization for multi-threaded requirements |

## 16. Self-Check

### Questions

1. Why is `Stage.class` needed when creating an empty EnumMap?
2. Does inserting DONE before PLANNED cause DONE to be iterated first?
3. After putting the same constant twice, does size automatically increase by two?
4. Can EnumMap contain null keys? Can it contain null values?
5. Is `get` returning null enough to distinguish MON having no mapping from MON having a null value?
6. Does `getOrDefault` on a null-valued mapping return the default or null?
7. Why does copying an empty HashMap throw an error while copying an empty EnumMap does not?
8. Can a Map variable pointing to an empty EnumMap be copied using the constructor that takes a Map?
9. Does a weakly consistent iterator guarantee seeing every modification made during traversal?
10. How do EnumSet and EnumMap differ in role?

### Answers

1. Class provides the enum domain at runtime even when no key is present to infer from.
2. No; the constant declaration order determines iteration order.
3. No; the second call replaces the value of the same mapping.
4. Null keys are not accepted on put; null values are accepted.
5. No; you need `containsKey` or a wrapper-layer contract that forbids null values.
6. Null, because the mapping exists.
7. The source EnumMap already holds the key type; an empty HashMap has no mappings for the constructor to infer the enum type from.
8. Yes, because the constructor recognizes when the actual source object is an EnumMap.
9. No; it may or may not see modifications. Nor does it make the map synchronized on its own.
10. EnumSet stores which constants are present; EnumMap stores the relationship from each mapped constant to a value.

## 17. Practice With Reference Results

### Exercise 1: Order Independent of Insertion

Declare `enum Color { RED, GREEN, BLUE }`. Insert BLUE=3, RED=1, then GREEN=2 into an EnumMap. Predict the `keySet` order before running.

Reference result: `[RED, GREEN, BLUE]`. Then update RED to 10: size remains three, order stays the same, only RED's value changes.

### Exercise 2: All Keys Present, Not All Values Non-Null

Create a map for Color and put all three keys, with GREEN mapped to null. Compute the set of constants without a mapping using `EnumSet.allOf` and `removeAll(keySet)`.

Reference result: the missing-mappings set is empty, yet there is still one null value. If every color must have a non-null label, the coverage check must be paired with a value check.

### Exercise 3: Potentially Empty Source

Write a method that accepts a `Map<Color,String>` which may be empty. Initialize an EnumMap with `Color.class` and then `putAll` the source. Run with an empty source and with a source containing only BLUE.

Reference result: the empty case returns a map of size 0; the case with BLUE returns a single BLUE mapping. No dummy data needs to be inserted to determine the key type.

### Exercise 4: Grouping Data When Input Is Empty

In Program 5, replace `events` with an empty list and predict `counts`, `groups`, and the output printed for every Severity.

Reference result: `counts` still has LOW=0, MEDIUM=0, HIGH=0 because the entire domain was initialized; `groups` is empty because no level needed a list. Each printed line has `count=0` and `messages=[]`. This confirms the difference between pre-populating default values and creating groups on demand.

## 18. Runtime Environment and Documentation

The five programs in this lesson are standalone and use syntax and APIs compatible with Java 17. They were compiled with `javac --release 17 -encoding UTF-8` and run on JDK 24.0.2; stdout was verified from those runs. Each public class is saved in a matching file name, with no external libraries.

- [EnumMap — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumMap.html): enum key domain, constructors, order, null handling, views, and iterators.
- [Enum — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Enum.html): constant identity, declaration order, ordinal, and getDeclaringClass.
- [EnumSet — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumSet.html): specialized constant set and full-domain creation.
- [Map — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): mappings, null handling, getOrDefault, putIfAbsent, computeIfAbsent, and merge.
