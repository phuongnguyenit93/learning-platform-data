# Collections.unmodifiableList, unmodifiableSet, and unmodifiableMap

## 1. Providing Read Access Through a Reference Path

A class holds a mutable list, set, or map, but wants receivers to only read through the returned result. The three methods in this lesson create views that disallow modification through their interfaces:

| Method | Argument | Result |
|---|---|---|
| Collections.unmodifiableList(...) | List | List that disallows modification through the wrapper |
| Collections.unmodifiableSet(...) | Set | Set that disallows modification through the wrapper |
| Collections.unmodifiableMap(...) | Map | Map that disallows modification through the wrapper |

A wrapper is a decorating layer: it provides another access path to the same source data. Read operations rely on the source; modification operations through the wrapper are rejected with UnsupportedOperationException.

The key point to grasp from the start is that **disallowing modification through the wrapper does not mean the source data never changes**. If another place still holds a mutable reference to the source, that place can still modify the source. The view will read the source data according to its contract.

A simple model:

```text
Owner    ──→ mutable source collection
                         ↑
Receiver ──→ wrapper reading source data
              add/remove/... rejected through this path
```

The complete examples in this lesson use Java 17 or later. List is illustrated with ArrayList; Set and Map use LinkedHashSet/LinkedHashMap so that stdout order is deterministic.

### 1.1. Why Use a Wrapper?

A wrapper is useful when you want to let others observe current data while keeping update operations inside the owning class. It also helps express that a returned result must not be modified directly.

For example, a registry allows registration through a method that validates conditions. Returning the internal List directly would let callers add elements while bypassing those checks. Returning an unmodifiable view forces collection updates to go through the API exposed by the registry.

However, you still need to consider other references and element state. A List that disallows add does not by itself prevent a receiver from modifying a mutable object obtained via get from the List.

## 2. General Contract to Distinguish

### 2.1. Reads from the Source, Does Not Copy All Data

The three unmodifiable methods in this lesson create views backed by the argument. They do not have a contract to collect all elements into a separate backing collection like new ArrayList<>(source).

If the source adds an element, removes an element, or changes a valid mapping, reading the wrapper reflects the source according to its contract. Do not call a wrapper a fixed snapshot taken at the time of wrapping.

Do not rely on wrapper object identity. The API may return an argument that is already appropriately unmodifiable; what you should rely on is the contract, not an expectation that each wrap call necessarily creates a distinct object under ==.

Reference: [Collections — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html), sections for unmodifiableList, unmodifiableSet, and unmodifiableMap.

### 2.2. Modification Methods Still Appear at the Type Level

List still declares add, set, and remove; Map still declares put and compute. The wrapper does not create a new Java interface that only has read methods.

Therefore, code calling view.add can compile and then throw UnsupportedOperationException at runtime. Changing the reference type or adding final before a variable does not restore modification rights on the wrapper.

final only prevents reassigning the reference variable under language rules. It does not turn the source collection into an immutable object and does not replace the role of an unmodifiable wrapper.

### 2.3. Indirect Modification Paths Must Also Be Blocked

Blocking only view.add is not enough for an unmodifiable contract. Iterator has remove, List has ListIterator and subList, and Map has keySet, values, entrySet, and Entry objects.

The standard wrappers in this lesson also protect modification paths through the views or iterators they return. Do not treat iterator.remove or entry.setValue as valid modification workarounds for a forbidden add/put call.

The following examples test specific paths with actual calls, then print the source for comparison.

### 2.4. The Source Contract Still Matters

A wrapper does not automatically sort data, filter out null, or establish a different uniqueness rule for the source.

A wrapper over a LinkedHashSet reflects the iteration order of the LinkedHashSet. Wrapping a HashSet does not create an insertion-order guarantee. Similarly, unmodifiableMap does not turn a HashMap into a key-sorted map.

A null collection/map argument is rejected with NullPointerException. That is different from null elements, keys, or values already permitted by a valid source.

## 3. unmodifiableList: Still Readable by Index, Not Modifiable Through List

unmodifiableList preserves the List interface: you can use get, size, contains, iterate, and take a subrange. Read access by index does not imply permission to set at that index.

Modification operations to consider include add, remove, set, clear, bulk element replacements, and modification paths from iterator/ListIterator. A subList of the wrapper also does not grant permission to delete a range from the source.

### 3.1. Program 1: Source Changes, Wrapper Sees the Changes

Save to `UnmodifiableListDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;

public class UnmodifiableListDemo {
    static void expectUnsupported(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A", "B"));
        List<String> view = Collections.unmodifiableList(source);
        source.add("C");
        source.set(0, "A2");
        System.out.println("viewAfterSourceEdits=" + view);
        System.out.println("first=" + view.get(0));
        expectUnsupported("add", () -> view.add("D"));
        expectUnsupported("set", () -> view.set(0, "changed"));
        Iterator<String> cursor = view.iterator();
        System.out.println("iteratorNext=" + cursor.next());
        expectUnsupported("iteratorRemove", () -> cursor.remove());
        expectUnsupported("subListClear", () -> view.subList(1, 3).clear());
        expectUnsupported("removeIf", () -> view.removeIf(value -> value.equals("B")));
        System.out.println("sourceAfterRejectedEdits=" + source);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 UnmodifiableListDemo.java
java UnmodifiableListDemo
```

Stdout:

```text
viewAfterSourceEdits=[A2, B, C]
first=A2
add=UnsupportedOperationException
set=UnsupportedOperationException
iteratorNext=A2
iteratorRemove=UnsupportedOperationException
subListClear=UnsupportedOperationException
removeIf=UnsupportedOperationException
sourceAfterRejectedEdits=[A2, B, C]
```

### 3.2. Two Access Paths with Different Permissions

source.add(C) and source.set(0,A2) are called through the source ArrayList, so they succeed. viewAfterSourceEdits is `[A2, B, C]`; get(0) returns A2.

view.add and view.set throw UnsupportedOperationException because they are called through the wrapper. The same source data has different modification permissions depending on the access path.

### 3.3. Iterator and Subrange Do Not Bypass the Restriction

cursor.next still reads A2, but cursor.remove is rejected. An Iterator obtained from the wrapper does not restore the removal permission of the source ArrayList.

view.subList(1,3).clear is also rejected. Creating a subview from the wrapper does not make that subrange modifiable.

removeIf is a conditional modification operation and is also rejected in the example. The source after those blocked calls remains A2,B,C.

The expectUnsupported helper is only for verification: if the call does not throw an exception, it raises AssertionError. Business code should choose the right operation permissions from the start, rather than using exceptions to probe and then ignore modification requests.

## 4. unmodifiableSet: Preserving the Set Contract and Blocking Modification

Set has no indices like List. The wrapper still provides size, contains, iteration, and set semantics based on the source. It does not allow add, remove, or clear through the wrapper.

If the source uses mutable objects as elements, the wrapper does not freeze the state of those objects. In particular, do not rely on the wrapper to protect the equals/hashCode contract of an element currently inside a hash-based set.

The Set contract is described in [Set — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html).

### 4.1. Program 2: Source and Null Policy

Save to `UnmodifiableSetDemo.java`:

```java
import java.util.Collections;
import java.util.Iterator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class UnmodifiableSetDemo {
    static void expectUnsupported(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        Set<String> source = new LinkedHashSet<>(List.of("red", "blue"));
        Set<String> view = Collections.unmodifiableSet(source);
        System.out.println("containsRed=" + view.contains("red"));
        source.add("green");
        System.out.println("viewAfterSourceAdd=" + view);
        expectUnsupported("setAdd", () -> view.add("yellow"));
        expectUnsupported("setRemove", () -> view.remove("red"));
        expectUnsupported("setClear", () -> view.clear());
        Iterator<String> cursor = view.iterator();
        System.out.println("setIteratorNext=" + cursor.next());
        expectUnsupported("setIteratorRemove", () -> cursor.remove());
        source.add(null);
        System.out.println("viewAfterSourceNull=" + view);
        System.out.println("viewContainsNull=" + view.contains(null));
        System.out.println("sourceSize=" + source.size());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 UnmodifiableSetDemo.java
java UnmodifiableSetDemo
```

Stdout:

```text
containsRed=true
viewAfterSourceAdd=[red, blue, green]
setAdd=UnsupportedOperationException
setRemove=UnsupportedOperationException
setClear=UnsupportedOperationException
setIteratorNext=red
setIteratorRemove=UnsupportedOperationException
viewAfterSourceNull=[red, blue, green, null]
viewContainsNull=true
sourceSize=4
```

### 4.2. Output Order Comes from the LinkedHashSet Source

source adds red,blue, then green. viewAfterSourceAdd is `[red, blue, green]`. The wrapper does not sort alphabetically; it reads the order of the source.

setAdd, setRemove, setClear, and setIteratorRemove are all rejected. contains and iterator.next still read the data.

### 4.3. Wrapper Does Not Turn a Null-Permitting Source into a Null-Forbidding Source

The source LinkedHashSet allows null, so source.add(null) succeeds. The wrapper subsequently sees null and contains(null) returns true; sourceSize is 4.

Do not apply the rule “every unmodifiable collection forbids null” to these three wrappers. Factories such as Set.of or Set.copyOf have their own null contracts; they are not equivalent to wrapping an existing Set with unmodifiableSet.

Nor should you infer that every source accepts null queries. The permissions and restrictions of the actual source still need to be read from its API.


## 5. unmodifiableMap Must Protect All Three Collection Views

A Map can be modified not only through put/remove. keySet.remove can remove a mapping by key; values.remove can remove a mapping carrying a matching value; entrySet and Entry.setValue also have modification operations.

unmodifiableMap blocks modifications through the Map itself and through the collection views it provides. This prevents a receiver from obtaining a subview and modifying the source map through that path.

| Access path | Example read operations | Example blocked modification operations |
|---|---|---|
| Map | get, containsKey, size | put, remove, clear, compute |
| keySet() | contains, iterator.next | remove, clear, iterator.remove |
| values() | contains, iterate values | remove, clear |
| entrySet() | iterate key–value pairs | remove, clear |
| Entry from wrapper's entrySet | getKey, getValue | setValue |

Do not equate blocking setValue with making every value object immutable. getValue can return a mutable List; changing the contents of that List is different from requesting a mapping change in the Map.

The Map contract and its views are described in [Map — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html). The specific wrapper contract is in [Collections.unmodifiableMap — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html).

### 5.1. Methods with Callbacks Are Still Modification Operations

compute, merge, replaceAll, and similar update methods do not become read operations just because the caller passes a function.

If the intent is to compute a different result from the data, create a separate result. If the intent is to update the map, go through an API with appropriate modification permissions. Do not try to use another update method to bypass a rejected put.

### 5.2. Do Not Rely on a Modification That “Probably Does Nothing”

Collection/map interfaces have specific rules regarding optional operations and calls that have no actual effect. Algorithms such as sort can also have different implementations.

Therefore, do not use removing a nonexistent key, an empty putAll, or sorting an already-ordered list as harmless read checks. Write code according to read or write intent; do not use the outcome of a no-op case to conclude general modification permissions.

The next example uses explicit modification calls on existing data to verify the wrapper contract.

## 6. Program 3: Blocking Modification Through Map, Views, and Entry

Save to `UnmodifiableMapDemo.java`. LinkedHashMap is used so that the order of mappings when printed is deterministic.

```java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

public class UnmodifiableMapDemo {
    static void expectUnsupported(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        Map<String, Integer> source = new LinkedHashMap<>();
        source.put("a", 1);
        source.put("b", 2);
        Map<String, Integer> view = Collections.unmodifiableMap(source);
        source.put("b", 20);
        source.put("c", 3);
        System.out.println("viewAfterSourcePut=" + view);
        System.out.println("getB=" + view.get("b"));
        expectUnsupported("mapPut", () -> view.put("d", 4));
        expectUnsupported("mapRemove", () -> view.remove("a"));
        expectUnsupported("mapCompute", () -> view.compute("a", (key, value) -> value + 1));
        expectUnsupported("keySetRemove", () -> view.keySet().remove("a"));
        expectUnsupported("valuesRemove", () -> view.values().remove(20));
        expectUnsupported("entrySetClear", () -> view.entrySet().clear());
        Map.Entry<String, Integer> entry = view.entrySet().iterator().next();
        System.out.println("entryBeforeSet=" + entry);
        expectUnsupported("entrySetValue", () -> entry.setValue(99));
        System.out.println("sourceAfterRejectedMapEdits=" + source);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 UnmodifiableMapDemo.java
java UnmodifiableMapDemo
```

Stdout:

```text
viewAfterSourcePut={a=1, b=20, c=3}
getB=20
mapPut=UnsupportedOperationException
mapRemove=UnsupportedOperationException
mapCompute=UnsupportedOperationException
keySetRemove=UnsupportedOperationException
valuesRemove=UnsupportedOperationException
entrySetClear=UnsupportedOperationException
entryBeforeSet=a=1
entrySetValue=UnsupportedOperationException
sourceAfterRejectedMapEdits={a=1, b=20, c=3}
```

### 6.1. Source Updates Are Read Through the Wrapper

After source.put(b,20) and source.put(c,3), the wrapper reads `{a=1, b=20, c=3}`. get(b) returns 20.

Changing the value of b in the source is not prevented by the wrapper. The wrapper only controls operations called through itself and the protected views it returns.

### 6.2. Different Update Mechanisms Are All Rejected

mapPut, mapRemove, and mapCompute all throw UnsupportedOperationException. You cannot use compute to reopen modification permissions on a wrapped map.

keySetRemove, valuesRemove, and entrySetClear are also rejected. Those are paths that can modify a normal Map, so you cannot protect only the direct methods on Map and ignore them.

### 6.3. Entry Can Be Read, but setValue Cannot Be Called

The first entry in the example is a=1. entry.setValue(99) is blocked; sourceAfterRejectedMapEdits remains `{a=1, b=20, c=3}`.

This entry is obtained from the wrapper's entrySet and used immediately in the demonstration. Do not automatically assume every Entry is a snapshot with an unlimited lifetime: an Entry's contract also depends on how it was obtained. The takeaway here is that the wrapper does not grant permission to modify the mapping via setValue.

## 7. Read-Only at the Outer Layer Is Not Read-Only for All State

### 7.1. A Mutable Element Can Still Be Modified

A wrapped List<StringBuilder> still returns a StringBuilder when get is called. Appending on a StringBuilder does not call add/remove/set on the List.

The wrapper cannot automatically alter the entire API of every element type E. To control such state modifications, you need an immutable element model, element copies, or another appropriate way of supplying data.

Similarly, a Map that disallows put can still hold values that are mutable Lists. Calling map.get(key).add(x) modifies the value List, not the Map's mapping.

### 7.2. Copying Before Wrapping Only Separates the Copied Layer

Collections.unmodifiableList(new ArrayList<>(source)) creates a separate backing List structure and then wraps it. Subsequent additions or removals on source do not automatically change the resulting structure.

However, the new ArrayList still holds the existing element references. If the elements are StringBuilder, both the source and the result can observe the same append.

Do not call this construct a general deep copy. Data layers with mutable state must be considered individually.

### 7.3. Nested Collections Require Decisions at Each Layer

With Map<String,List<String>>, if you want to detach from the source and block modifications through both the Map and the inner Lists, you can:

1. Create a new backing Map.
2. Create a new List for each value.
3. Wrap each inner List.
4. Wrap the outer Map.
5. Manage modification permissions of the new backing structures, without exposing mutable references to them.

String in this example is immutable, so you do not need to create another String just to block modifying its contents. If changed to List<MutablePermission>, copying and wrapping the List still does not protect MutablePermission by itself.

This is a model-specific policy. There is no automatic rule that adding an outermost wrapper makes every nested data path read-only.

## 8. Program 4: Detaching Backing Structures and Wrapping Protected Layers

Save to `UnmodifiableLayersDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class UnmodifiableLayersDemo {
    static void expectUnsupported(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        List<StringBuilder> source = new ArrayList<>(List.of(new StringBuilder("draft")));
        List<StringBuilder> detachedOuter =
                Collections.unmodifiableList(new ArrayList<>(source));
        source.add(new StringBuilder("extra"));
        detachedOuter.get(0).append("!");
        System.out.println("sourceSize=" + source.size());
        System.out.println("detachedSize=" + detachedOuter.size());
        System.out.println("sharedMutableElement=" + source.get(0));
        System.out.println("sameElement=" + (source.get(0) == detachedOuter.get(0)));

        Map<String, List<String>> roles = new LinkedHashMap<>();
        roles.put("admin", new ArrayList<>(List.of("read")));
        Map<String, List<String>> outerView = Collections.unmodifiableMap(roles);
        outerView.get("admin").add("write");
        System.out.println("sourceRolesAfterInnerEdit=" + roles.get("admin"));

        Map<String, List<String>> copied = new LinkedHashMap<>();
        roles.forEach((key, values) -> copied.put(key,
                Collections.unmodifiableList(new ArrayList<>(values))));
        Map<String, List<String>> readOnlyCopy = Collections.unmodifiableMap(copied);
        roles.get("admin").add("owner");
        System.out.println("sourceRolesAfterLaterEdit=" + roles.get("admin"));
        System.out.println("copiedRoles=" + readOnlyCopy.get("admin"));
        expectUnsupported("nestedListAdd", () -> readOnlyCopy.get("admin").add("blocked"));
        expectUnsupported("outerMapPut", () -> readOnlyCopy.put("guest", List.of("read")));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 UnmodifiableLayersDemo.java
java UnmodifiableLayersDemo
```

Stdout:

```text
sourceSize=2
detachedSize=1
sharedMutableElement=draft!
sameElement=true
sourceRolesAfterInnerEdit=[read, write]
sourceRolesAfterLaterEdit=[read, write, owner]
copiedRoles=[read, write]
nestedListAdd=UnsupportedOperationException
outerMapPut=UnsupportedOperationException
```

### 8.1. Outer List Is Detached, StringBuilder Is Still Shared

detachedOuter is created from a new ArrayList. After source.add(extra), sourceSize is 2 while detachedSize remains 1.

However, appending through detachedOuter.get(0) causes source.get(0) to print draft!. sameElement is true. A separate backing structure does not automatically clone element objects.

### 8.2. Outer Map Disallows put, but Value List Is Still Modifiable

outerView wraps roles. outerView.get(admin).add(write) succeeds because the returned value is an unwrapped ArrayList.

sourceRolesAfterInnerEdit is read,write. No put was called on outerView in this operation; the Map's unmodifiable contract was not bypassed—rather, a different object was modified.

### 8.3. Two-Layer Copy Does Not Follow Changes in the Old Source

copied creates new value Lists from the current contents, and each List is wrapped. readOnlyCopy wraps the Map containing those Lists.

After roles.get(admin).add(owner), the old source has read,write,owner while copiedRoles still has only read,write. The result's value List is no longer the source's value List.

nestedListAdd is blocked by the inner List wrapper; outerMapPut is blocked by the outer Map wrapper. You must protect the exact layers that receivers can access.

### 8.4. Ownership of the New Structures Still Matters

copied is still a mutable LinkedHashMap within the program's scope. If owning code continues to modify copied, readOnlyCopy will see those changes.

The example does not retain a mutable reference to the inner ArrayLists created in the expression before wrapping. In real APIs, control those references rather than relying merely on a variable name like readOnly.

The four examples do not use multiple threads; detaching and wrapping data does not automatically provide a concurrent access contract.


## 9. Choosing a Source-Tracking View vs. a Source-Detached Result

### 9.1. When You Need to Observe Current Data

Use unmodifiableList(source), unmodifiableSet(source), or unmodifiableMap(source) when receivers are allowed to see updates from the source but must not modify it through the provided result.

The owner still needs to retain update permissions in appropriate methods. For example, adding a name through a register method can check for duplicates or business conditions before modifying the source.

If you also expose the mutable source elsewhere, a wrapper on a getter does not revoke the modification rights that the other source reference already has. You must examine all data-providing paths.

### 9.2. When You Need an Independent Backing Result

You can copy the backing structure first and then wrap it. The snippets below are illustrations placed inside a method that already has listSource of type List<String>, setSource of type Set<String>, mapSource of type Map<String,Integer>, and the corresponding java.util imports; they are not standalone Java files.

```java
List<String> listResult =
        Collections.unmodifiableList(new ArrayList<>(listSource));

Set<String> setResult =
        Collections.unmodifiableSet(new LinkedHashSet<>(setSource));

Map<String, Integer> mapResult =
        Collections.unmodifiableMap(new LinkedHashMap<>(mapSource));
```

The new ArrayList separates the List positions from the source. The new LinkedHashSet and LinkedHashMap collect data in the source's iteration order at the time of copying. They do not infer an insertion order that the source discarded, nor do they sort by key or value.

Subsequent changes to the old source collection do not automatically update the new backing structure. However, elements, keys, and values are copied by reference; if they are mutable, you must still consider that data layer.

### 9.3. Comparison with copyOf Factories

List.copyOf, Set.copyOf, and Map.copyOf also provide unmodifiable results with a contract that their contents do not follow subsequent changes to the source collection. They are not live views like the three wrappers that directly wrap a source in this lesson.

However, do not substitute them mechanically:

| Option | Relationship to source structure afterward | Nulls and order to consider |
|---|---|---|
| Wrap directly with unmodifiable | Reads from the wrapped source | Depends on the source; does not automatically sort or filter null |
| Copy into a chosen structure then wrap | New structure detached from the old source | Follows the chosen container type; still a shallow copy of elements |
| List.copyOf | Resulting List contents do not follow subsequent source structure edits | Forbids null elements, preserves order of the input collection |
| Set.copyOf | Resulting set does not follow subsequent source structure edits | Forbids null, does not promise LinkedHashSet-like order |
| Map.copyOf | Resulting mappings do not follow subsequent source structure edits | Forbids null keys/values, does not promise LinkedHashMap-like order |

These factories can still hold shared mutable objects. They can also reuse an already suitable unmodifiable result, so they do not promise to always allocate a new object by identity.

Reference: [List — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html), [Set — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html), [Map — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).

### 9.4. Preserve the Interface Required by the API

The three methods in this lesson return List, Set, and Map. If the API also needs the SortedSet, NavigableSet, SortedMap, or NavigableMap contract, choose the corresponding specialized wrapper instead of wrapping as Set/Map and casting to call specialized methods.

Do not cast a wrapper to ArrayList, LinkedHashSet, or LinkedHashMap to modify it. The wrapper does not have a contract to be that concrete class. If a receiver needs a modifiable copy, create a separate container as requested instead of trying to unlock modification on the view.

### 9.5. The Wrapper Follows the Source Object, Not the Variable Name

From the object-wrapping relationship, it follows that reassigning the source variable to another collection does not automatically make the old wrapper switch to the new object.

Changing the contents of the wrapped collection and changing a variable to point to a different collection are two different actions. When a class replaces an entire data field with a new collection, clearly design whether previously returned views will still see the old object or whether receivers must fetch the new result.

## 10. Lifecycle, Ownership, and Concurrent Access

### 10.1. Read-Only Does Not Guarantee Thread Safety

A wrapper does not automatically add synchronization to the source ArrayList, LinkedHashSet, or LinkedHashMap. If one place reads the wrapper while another modifies the source concurrently, you must still follow the source's access contract and design proper coordination.

Do not treat UnsupportedOperationException as a thread-coordination tool. It rejects an unsupported modification path; it does not replace locks, create atomic snapshots, or turn multiple reads into a transaction.

If consistent point-in-time data is needed, the copy creation process must also read the source under appropriate conditions. Wrapping a changing source does not solve that requirement.

### 10.2. Iterators Are Not Automatically Created Snapshots

An Iterator obtained from a wrapper reads according to the source's mechanism. If the source has a fail-fast iterator, modifying the source's structure while iterating can cause the iteration to fail.

Blocking iterator.remove only restricts removal through that iterator; it does not freeze the source during the loop. Do not hold an iterator, modify the source through another reference, and infer that reading will be safe just because the iterator came from a wrapper.

The complete programs in this lesson modify the source before creating the needed iterator, and do not rely on contention between threads.

### 10.3. Unmodifiable Collection Does Not Protect Mutable Keys

If a mutable object is used as a Set element or Map key, changing state that affects equals/hashCode can violate the container's contract. A wrapper does not automatically lock the fields or mutator methods of that object.

A read-only data design sufficient for real-world needs usually requires both clear source ownership and appropriate element/key types. Do not measure protection solely by whether an add call is rejected.

### 10.4. Cost and Lifetime Must Be Considered

Direct wrapping does not copy all n elements into another backing structure. This is suitable when you want a view that continues to observe data managed by the owner.

Copying before wrapping needs to collect references or mappings into a new backing structure. In return, the resulting structure no longer depends on the positions or mappings of the old source collection.

Do not choose based only on labels like “lightweight” or “safe.” Determine whether receivers are allowed to see subsequent updates, whether they hold the result for a long time, and what state the element objects still share.

## 11. Common Mistakes

| Misconception or practice | Problem | How to handle |
|---|---|---|
| Once wrapped, source can no longer be modified | The source reference still has source permissions | Manage all paths that expose source |
| Wrapper is a snapshot | View reads from the source | Copy first if you need to detach the backing structure |
| Cannot add, so set probably works | set is also a List modification | Read the modification contract, not just size |
| Use iterator.remove instead of view.remove | Wrapper's iterator does not grant removal permission | Use an authorized update API or modify a copy |
| Delete through the wrapper's subList | The subview is still unmodifiable | Do not treat a subview as a bypass path |
| Modify map through keySet/values/entrySet | Those paths are also protected | Update through the owner or a different map |
| Use Entry.setValue because Entry is readable | Changing a mapping's value is still a modification | Do not use the wrapper's Entry to update the map |
| Map disallows put, so value List also disallows add | Two objects have separate permissions | Wrap or copy the layers that need protection |
| Unmodifiable List makes inner StringBuilder immutable | Wrapper does not change the element's API | Choose immutable elements or appropriate copies |
| Every read-only collection forbids null | Wrappers and factories have different contracts | Check the source and how the result is created |
| Wrapper adds stable order to HashSet/HashMap | It does not change the source's ordering policy | Choose an ordered structure when order is required |
| final collection replaces unmodifiable | final only restricts variable reassignment | Separate variable assignment from object mutability |
| Unmodifiable means thread-safe | No automatic synchronization guarantee | Design access according to the source's contract |
| Cast wrapper to source class to modify | Actual class is not guaranteed to be the source class | Create a separate mutable copy when needed |
| Reassigning source to another collection moves the old view | Wrapper is bound to the wrapped object | Manage the lifecycle of views and source fields |
| Check only size after an operation to test immutability | Elements or values can change while size stays the same | Check both state and reference relationships |

Do not use a broad catch Exception and ignore it to hide a rejected modification operation. UnsupportedOperationException usually indicates that calling code is using a result beyond the modification permissions provided by its contract.

## 12. Self-Check and Practice

### 12.1. Questions with Answers

1. **Does unmodifiableList(source) copy elements into a new independent List?** Not under the wrapper contract; it provides a view that reads the source data.
2. **Is source.add after wrapping prevented by the wrapper?** No. Calls through the source still follow the source's permissions.
3. **Why does view.add compile but fail at runtime?** The List type declares add; the wrapper object does not support that modification operation.
4. **Can an Iterator from the wrapper call remove if the source ArrayList is modifiable?** No. Removal through the wrapper's iterator is also blocked.
5. **Can a Map.Entry from unmodifiableMap's entrySet call setValue to modify the source?** Not through the path provided by the wrapper.
6. **Can get(key).add on a Map<String,List<String>> that disallows put succeed?** Yes, if the value List is still modifiable. It modifies the List object, not by calling put on the Map.
7. **Does wrapping a LinkedHashSet containing null automatically remove null?** No. The wrapper does not filter source data.
8. **Does wrapping a HashMap create ascending key order?** No. Order still follows the source's contract.
9. **Does copying a List and then wrapping clone StringBuilder elements?** No. A separate backing structure can still hold the same element references.
10. **Does unmodifiable automatically make an iteration safe while another thread modifies the source?** No. You must consider the source's access mechanism and separate coordination.

### 12.2. Exercise: Compare a View and a Backing Copy

Create an ArrayList<String> containing one,two. Create a directly wrapped view and a result wrapping an ArrayList copied from the source.

Add three through the source. Expect the view to see one,two,three; the separate backing result remains one,two. Try add on both results and verify the operations are rejected.

Change the element type to StringBuilder and call append through the separate backing result. Explain why the result can still affect the source element even though the slot count is independent.

### 12.3. Exercise: Protect All Map Paths

Create a LinkedHashMap<String,Integer> with two mappings and wrap it with unmodifiableMap. Separately test put, remove, keySet.remove, values.remove, and Entry.setValue from entrySet.

After each rejected test, read the source map to confirm the mappings are unchanged. Read operations get, containsKey, and iterating entries must still work according to the source data.

Do not test invalid-index operations or an Entry outside its valid lifecycle and attribute every exception to the wrapper.

### 12.4. Exercise: Design an API Returning a Map of Lists

A class holds a Map<String,List<String>> containing permission groups. Receivers must not add/remove groups, must not add/remove permissions within a group, and must not observe structural modifications to the source after receiving the result.

Design a result with a separate backing Map and separate value Lists, properly wrapping both layers. Keep ownership of the new mutable structures clear, then modify the old source to verify the result does not follow those changes.

If String is replaced with a mutable Permission object, state what additional state remains unprotected by merely copying and wrapping the collections.

## 13. References and Verification Scope

- [Collections — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html): contract for the three unmodifiable wrappers, source-backed reads, and rejected modifications.
- [List — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): List interface, modification operations, List.copyOf, and limitations with mutable elements.
- [Set — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html): set contract, mutable elements, null, and Set.copyOf.
- [Map — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): collection views, update operations, mutable keys, and Map.copyOf.

The four complete programs compiled with `javac --release 17 -encoding UTF-8` and ran on Corretto JDK 17.0.15, producing the recorded stdout. The examples use LinkedHashSet/LinkedHashMap to fix the iteration order to be printed. The snippet creating three results in the view/copy selection section is illustrative code to be placed in a context with appropriate source variables and imports; it is not presented as a standalone Java file.
