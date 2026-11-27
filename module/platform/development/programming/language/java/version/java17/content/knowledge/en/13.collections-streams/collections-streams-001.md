# Collection Factories and Unmodifiable Data in Java 17

Java 9 added factory methods such as `List.of(...)`, `Set.of(...)`, and `Map.of(...)` to create collections concisely. Java 10 added `List.copyOf(...)`, `Set.copyOf(...)`, and `Map.copyOf(...)` to create unmodifiable collections from an existing collection. These APIs are all stable in Java 17.

When using them, it is important to understand two distinct concepts:

- **Factory methods** help create a collection from elements or key/value pairs.
- **Unmodifiable collections** do not allow changing the collection structure through mutator methods. That does not automatically make every object inside them immutable.

In addition, `Collections.unmodifiableList(...)` and similar wrappers also create unmodifiable collections, but they act as a **view** over the original collection. The difference between a view and a copy is crucial when data is shared across multiple parts of an application.

## 1. What Is a Collection Factory?

Collection factories are static methods that create collections without needing multiple `new ArrayList<>()`, `add(...)`, or `put(...)` statements.

For example:

~~~java
import java.util.List;
import java.util.Set;
import java.util.Map;

List<String> names = List.of("An", "Bình", "Chi");
Set<Integer> ids = Set.of(10, 20, 30);
Map<String, Integer> scores = Map.of(
        "An", 90,
        "Bình", 85
);
~~~

These collections can be read, iterated, searched, and used like regular collections:

~~~java
System.out.println(names.get(0));       // An
System.out.println(ids.contains(20));   // true
System.out.println(scores.get("An"));   // 90
~~~

However, they **do not allow adding, removing, or replacing elements**. For example:

~~~java
names.add("Dung");          // UnsupportedOperationException
ids.remove(10);             // UnsupportedOperationException
scores.put("Chi", 95);      // UnsupportedOperationException
~~~

The exception is `UnsupportedOperationException`, indicating that the modification operation is not supported by the collection.

### 1.1. Main Factory Methods

| API | Used to create | Characteristics |
|---|---|---|
| `List.of(e1, e2, ...)` | List | Preserves order, allows duplicate elements |
| `Set.of(e1, e2, ...)` | Set | Does not allow duplicate elements |
| `Map.of(k1, v1, ...)` | Map | Unique keys, pass key/value in pairs |
| `Map.ofEntries(entry1, ...)` | Map | Creates a map from `Map.Entry` instances |
| `List.copyOf(collection)` | List | Creates an unmodifiable collection from a source |
| `Set.copyOf(collection)` | Set | Creates an unmodifiable set from a source |
| `Map.copyOf(map)` | Map | Creates an unmodifiable map from a source |

`List.of`, `Set.of`, `Map.of`, and `Map.ofEntries` were introduced in Java 9. The `copyOf` methods were added in Java 10. Java 17 includes all of these APIs.

## 2. Creating a List with `List.of(...)`

`List.of(...)` creates an unmodifiable list:

~~~java
import java.util.List;

public class ListFactoryDemo {
    public static void main(String[] args) {
        List<String> languages = List.of(
                "Java",
                "Kotlin",
                "Scala"
        );

        System.out.println(languages);
        System.out.println(languages.get(1));
        System.out.println(languages.size());
    }
}
~~~

Output:

~~~text
[Java, Kotlin, Scala]
Kotlin
3
~~~

A List preserves the order of passed elements and allows duplicate values:

~~~java
List<String> tags = List.of("java", "backend", "java");

System.out.println(tags); // [java, backend, java]
~~~

However, the list cannot be modified:

~~~java
tags.add("database");       // UnsupportedOperationException
tags.set(0, "spring");      // UnsupportedOperationException
tags.remove("backend");     // UnsupportedOperationException
tags.clear();               // UnsupportedOperationException
~~~

### 2.1. Empty List and Single-Element List

You can use the factory for small cases:

~~~java
List<String> empty = List.of();
List<String> one = List.of("Java");
List<String> several = List.of("Java", "SQL", "HTTP");
~~~

There is no need to create an `ArrayList` and add elements one by one just to represent a fixed list.

### 2.2. List.of Does Not Accept null

Elements of `List.of(...)` cannot be `null`:

~~~java
List<String> values = List.of("A", null, "B");
// Throws NullPointerException.
~~~

If the data may contain null, define the data contract clearly. You can use an appropriate modifiable collection, or validate and normalize the data before creating an unmodifiable list.

Validation example:

~~~java
String input = null;

if (input == null) {
    throw new IllegalArgumentException("Name must not be null");
}

List<String> names = List.of(input);
~~~

Rejecting null at collection creation time makes errors surface close to where data enters the system.

## 3. Creating a Set with `Set.of(...)`

A Set does not store multiple equal elements. The `Set.of(...)` factory requires all passed elements to be distinct according to `equals`.

~~~java
import java.util.Set;

Set<String> roles = Set.of(
        "ADMIN",
        "EDITOR",
        "VIEWER"
);

System.out.println(roles.contains("ADMIN")); // true
System.out.println(roles.size());            // 3
~~~

### 3.1. Duplicate Elements Cause an Error

Unlike `List.of(...)`, the following throws `IllegalArgumentException`:

~~~java
Set<String> roles = Set.of("ADMIN", "USER", "ADMIN");
// IllegalArgumentException: duplicate element
~~~

The factory does not silently remove duplicates. If the input can contain duplicates and the goal is deduplication, use an explicit conversion step:

~~~java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

List<String> input = List.of("ADMIN", "USER", "ADMIN");
Set<String> unique = Set.copyOf(new LinkedHashSet<>(input));
~~~

Note: `Set.copyOf` creates an unmodifiable set, but **does not guarantee iteration order**. If ordering is a business requirement, choose a structure with a clear ordering contract and design how the data is exposed accordingly.

### 3.2. Set.of Does Not Accept null

~~~java
Set<String> codes = Set.of("A", null, "B");
// Throws NullPointerException.
~~~

A Set factory cannot be used to represent a set containing a null element.

### 3.3. Do Not Rely on the Iteration Order of Set.of

A Set is not an indexed collection. You should not rely on the order in which elements are printed or iterated in a `for-each` loop:

~~~java
Set<String> values = Set.of("A", "B", "C");

for (String value : values) {
    System.out.println(value);
}
~~~

The set of elements is `A`, `B`, `C`, but the iteration order is not a contract a program should depend on. If insertion order is needed, consider `LinkedHashSet`; if sorting is needed, consider `TreeSet`.

## 4. Creating a Map with `Map.of(...)`

The Map factory takes alternating key/value pairs:

~~~java
import java.util.Map;

Map<String, Integer> scores = Map.of(
        "An", 90,
        "Bình", 85,
        "Chi", 95
);

System.out.println(scores.get("An")); // 90
System.out.println(scores.containsKey("Chi")); // true
~~~

Remember that arguments are passed in the order:

~~~java
Map.of(key1, value1, key2, value2, key3, value3)
~~~

Not a list of single elements.

### 4.1. Map.of Is Limited to at Most 10 Key/Value Pairs

The overloads of `Map.of(...)` support from 0 to 10 key/value pairs. If you need more than 10 pairs, use `Map.ofEntries(...)`:

~~~java
import java.util.Map;

Map<String, Integer> statusCodes = Map.ofEntries(
        Map.entry("OK", 200),
        Map.entry("CREATED", 201),
        Map.entry("ACCEPTED", 202),
        Map.entry("NO_CONTENT", 204),
        Map.entry("BAD_REQUEST", 400),
        Map.entry("UNAUTHORIZED", 401),
        Map.entry("FORBIDDEN", 403),
        Map.entry("NOT_FOUND", 404),
        Map.entry("CONFLICT", 409),
        Map.entry("SERVER_ERROR", 500),
        Map.entry("UNAVAILABLE", 503)
);
~~~

`Map.entry(key, value)` creates an unmodifiable entry. `Map.ofEntries(...)` accepts those entries to create a map.

### 4.2. Map Does Not Accept Duplicate Keys or null

Keys must be unique:

~~~java
Map<String, Integer> map = Map.of(
        "A", 1,
        "A", 2
);
// IllegalArgumentException: duplicate key
~~~

Both keys and values must not be null:

~~~java
Map<String, Integer> map1 = Map.of(null, 1); // NullPointerException
Map<String, Integer> map2 = Map.of("A", null); // NullPointerException
~~~

Unlike List, Map does not allow duplicate keys. If you need to update a value by key, create a modifiable map or build a new map with the merged data.

### 4.3. Do Not Rely on the Iteration Order of Map.of

`Map.of(...)` does not guarantee iteration order. You should not write business logic that depends on key order during iteration:

~~~java
for (Map.Entry<String, Integer> entry : scores.entrySet()) {
    System.out.println(entry.getKey() + ": " + entry.getValue());
}
~~~

If insertion order is needed, consider `LinkedHashMap`; if sorting by key is needed, consider `TreeMap`. Map factories are suitable for fixed lookup data where iteration order is not a requirement.

## 5. Creating an Unmodifiable Collection from an Existing Collection: copyOf

The `copyOf` methods let you create an unmodifiable collection from existing data:

~~~java
List<String> source = new ArrayList<>();
source.add("Java");
source.add("SQL");

List<String> snapshot = List.copyOf(source);
~~~

Once created, `snapshot` does not allow adding, removing, or replacing elements.

~~~java
snapshot.add("HTTP"); // UnsupportedOperationException
~~~

### 5.1. copyOf Creates a Collection Independent of Structural Changes to the Source

~~~java
List<String> source = new ArrayList<>();
source.add("Java");
source.add("SQL");

List<String> snapshot = List.copyOf(source);

source.add("HTTP");

System.out.println(source);   // [Java, SQL, HTTP]
System.out.println(snapshot); // [Java, SQL]
~~~

`snapshot` reflects the elements at the time of creation. Adding a new element to the source list afterward does not modify the snapshot list.

This is a useful way to store a validated copy of input data, preventing callers from altering the list structure after passing it in.

### 5.2. copyOf Also Rejects null

If the source collection contains a null element, the `copyOf` factory methods throw `NullPointerException`:

~~~java
List<String> source = new ArrayList<>();
source.add("Java");
source.add(null);

List<String> snapshot = List.copyOf(source); // NullPointerException
~~~

Similarly, `Set.copyOf` does not accept null elements and `Map.copyOf` does not accept null keys or values.

### 5.3. How Does Set.copyOf Handle Duplicate Elements?

`Set.copyOf(collection)` accepts a source collection that may contain duplicate elements; since the result is a Set, it keeps only one element from each group of equal elements. If the source has duplicates, one representative element is retained.

This differs from `Set.of(a, a)`, which throws `IllegalArgumentException` when arguments are duplicated:

~~~java
Set<String> fromFactory = Set.of("A", "A"); // IllegalArgumentException

List<String> input = List.of("A", "B", "A");
Set<String> copied = Set.copyOf(input);     // Valid: contains only A and B
~~~

If you need to preserve input order while removing duplicates, explicitly design an ordered structure such as `LinkedHashSet` and expose it in an appropriate unmodifiable manner.

### 5.4. Map.copyOf Creates an Unmodifiable Map

~~~java
Map<String, Integer> source = new HashMap<>();
source.put("A", 1);
source.put("B", 2);

Map<String, Integer> snapshot = Map.copyOf(source);

source.put("C", 3);

System.out.println(source);   // Contains A, B, C
System.out.println(snapshot); // Contains only A, B
~~~

`Map.copyOf` does not allow modifying the structure of the resulting map. The source map can still be modified independently.
The iteration order of the resulting map is also not guaranteed; if ordering is a requirement, use a map type with the appropriate ordering contract and expose it in an unmodifiable way.

## 6. Distinguishing factory, copyOf, and Collections.unmodifiable*

These are three ways to create collections that are frequently confused:

1. `List.of(...)`: creates an unmodifiable collection from the passed elements.
2. `List.copyOf(source)`: creates an unmodifiable collection from the current elements of a source.
3. `Collections.unmodifiableList(source)`: creates an **unmodifiable view** over the source list.

### 6.1. An Unmodifiable View Is Not a Snapshot

For example:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> source = new ArrayList<>();
source.add("Java");
source.add("SQL");

List<String> view = Collections.unmodifiableList(source);

source.add("HTTP");

System.out.println(view); // [Java, SQL, HTTP]
~~~

`view` does not allow its holder to modify the list:

~~~java
view.add("Python"); // UnsupportedOperationException
~~~

However, because `view` references the source collection, changes made through `source` still appear when reading through `view`.

### 6.2. Comparison with copyOf

~~~java
List<String> source = new ArrayList<>();
source.add("Java");
source.add("SQL");

List<String> view = Collections.unmodifiableList(source);
List<String> snapshot = List.copyOf(source);

source.add("HTTP");

System.out.println(view);     // [Java, SQL, HTTP]
System.out.println(snapshot); // [Java, SQL]
~~~

| Criterion | `Collections.unmodifiableList(source)` | `List.copyOf(source)` |
|---|---|---|
| Modifiable through the resulting variable? | No | No |
| Structural changes via source visible in result? | Yes | No |
| Creates a structural snapshot? | No | Yes |
| Accepts null from source? | Yes, the wrapper does not check for null itself | No |
| Common purpose | Provide a read-only view of an existing collection | Publish/store an unmodifiable copy of a collection |

**Note:** `Collections.unmodifiableList` does not make the underlying collection unmodifiable. If other code still holds a reference to `source`, that code can add/remove elements and the view will reflect the changes.

### 6.3. Similar Wrappers for Set and Map

Java provides:

~~~java
Collections.unmodifiableSet(sourceSet);
Collections.unmodifiableMap(sourceMap);
~~~

They follow the same unmodifiable view principle: no modifications through the wrapper, but changes to the underlying collection are still reflected.

If you want a structural snapshot, consider:

~~~java
Set.copyOf(sourceSet);
Map.copyOf(sourceMap);
~~~

## 7. Unmodifiable Structure Does Not Mean Immutable Objects Inside

A very important point: collection factories only prevent changing the **collection structure**. If an element is a mutable object, that object's state can still change.

For example:

~~~java
import java.util.List;

class User {
    private String name;

    User(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}

List<User> users = List.of(new User("An"));

users.get(0).setName("Bình"); // Valid
System.out.println(users.get(0).getName()); // Bình
~~~

You cannot call `users.add(...)` or `users.set(0, ...)`, but you can call a setter on the object returned by `get(0)`.

This is **shallow unmodifiability**: the collection structure cannot be changed, but referenced objects may still be mutable.

### 7.1. Immutable Elements Make Data Safer

Types like `String`, primitive wrappers (`Integer`, `Long`, `Boolean`), and records designed with immutable components are usually well suited for unmodifiable collections.

For example:

~~~java
record UserInfo(String id, String name) {
}

List<UserInfo> users = List.of(
        new UserInfo("U01", "An"),
        new UserInfo("U02", "Bình")
);
~~~

Records do not automatically guarantee every component is immutable if a component holds a mutable object. For example, a record with a `List<String>` component still needs a defensive copy in its constructor:

~~~java
record Team(String name, List<String> members) {
    public Team {
        members = List.copyOf(members);
    }
}
~~~

This way, structural changes to the input list do not alter the list stored in the record. However, if elements in the list are mutable objects, copying the list is still a shallow copy.

### 7.2. Copying Nested Collections

If a map holds lists, `Map.copyOf` only makes the outer map unmodifiable. The inner lists can still be modified:

~~~java
Map<String, List<String>> source = new HashMap<>();
source.put("backend", new ArrayList<>(List.of("Java", "SQL")));

Map<String, List<String>> copy = Map.copyOf(source);

copy.get("backend").add("HTTP"); // Valid: inner list is mutable
~~~

If you want to prevent changes to the inner collections as well, copy each layer:

~~~java
Map<String, List<String>> immutableStructure = source.entrySet()
        .stream()
        .collect(java.util.stream.Collectors.toUnmodifiableMap(
                Map.Entry::getKey,
                entry -> List.copyOf(entry.getValue())
        ));
~~~

Both the map structure and the inner lists are unmodifiable. However, element objects inside the lists, if mutable, still do not automatically become immutable.

## 8. Are Factory Collections Thread-Safe?

You should not infer that an unmodifiable collection is a synchronization mechanism or guarantees safety for all referenced state.

- Factory collections do not provide structural modification operations.
- Concurrent reading of an unmodifiable collection is generally simpler when its structure cannot be modified.
- However, if elements inside are mutable, multiple threads can still contend when modifying those elements' state.
- If the source collection or element objects are still shared and mutated elsewhere, proper synchronization and safe publication must be designed.

For example:

~~~java
List<String> names = List.of("An", "Bình", "Chi");
~~~

This list cannot have elements added, removed, or modified, making it suitable to share as fixed configuration data. But if a collection holds mutable objects, protect those objects' state according to proper synchronization rules.

Additionally, collections created by factories may be **value-based**. Do not rely on their identity, do not compare with `==` to infer contents, and do not use an instance as a monitor for synchronization. Use `equals` to compare contents and a separate lock if synchronization is needed.

## 9. Comparison with Arrays.asList and Modifiable Collections

Not every concise way to create a list produces an unmodifiable collection.

### 9.1. Arrays.asList Is a Fixed-Size List

~~~java
import java.util.Arrays;
import java.util.List;

String[] array = {"Java", "SQL"};
List<String> list = Arrays.asList(array);

list.set(0, "Kotlin"); // Valid
list.add("HTTP");      // UnsupportedOperationException
~~~

`Arrays.asList` returns a fixed-size list, but still allows replacing elements. Changes between the array and the list are reflected bidirectionally because they share the same backing data.

Therefore, it differs from `List.of(...)`, which disallows even `set`.

### 9.2. Modifiable ArrayList

If you need to add, remove, or replace elements, use a mutable collection:

~~~java
List<String> names = new ArrayList<>(List.of("An", "Bình"));

names.add("Chi");
names.set(0, "Anh");

System.out.println(names); // [Anh, Bình, Chi]
~~~

Here `List.of(...)` only serves as the initial source; `new ArrayList<>(...)` creates a new modifiable list.

### 9.3. Choosing the Right Way to Create a Collection

| Need | Suitable API |
|---|---|
| Fixed, unmodifiable list | `List.of(...)` |
| Unique, unmodifiable set of values | `Set.of(...)` |
| Fixed, unmodifiable key/value map | `Map.of(...)` / `Map.ofEntries(...)` |
| Publish an unmodifiable copy from a source | `List.copyOf`, `Set.copyOf`, `Map.copyOf` |
| Create a read-only view that reflects source changes | `Collections.unmodifiableList/Set/Map` |
| Need a list that supports add/remove/replace | `new ArrayList<>(...)` |
| Need a mutable set preserving insertion order | `new LinkedHashSet<>(...)` |
| Need a mutable map preserving insertion order | `new LinkedHashMap<>(...)` |
| Need a fixed-size list that allows element replacement | `Arrays.asList(...)` |

## 10. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| `List.of(...).add(...)` throws UnsupportedOperationException | Factory list is unmodifiable | Create an `ArrayList` if adding elements is needed |
| `Set.of("A", "A")` throws IllegalArgumentException | Arguments contain duplicate elements | Deduplicate beforehand or use `Set.copyOf` if appropriate |
| `List.of("A", null)` throws NullPointerException | Factory does not accept null | Validate/normalize nulls or choose a collection with an appropriate contract |
| `Map.of(...)` has duplicate keys | Map requires unique keys | Merge data before creating the map |
| `Map.of` has more than 10 pairs | `Map.of` overloads only support up to 10 pairs | Use `Map.ofEntries` |
| Assuming `unmodifiableList` is a snapshot | Wrapper is only a view | Use `List.copyOf` when a structural copy is needed |
| Assuming an unmodifiable collection makes elements immutable | Only the collection structure is locked | Use immutable elements or appropriate defensive copies |
| Relying on iteration order of Set/Map factories | API does not guarantee that order | Use a structure with an explicit ordering contract |
| Using `==` to compare two factory collections | Should not rely on identity/value-based semantics | Use `equals` |

## 11. Complete Example Running on Java 17

Create file **`CollectionFactoryDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class CollectionFactoryDemo {
    public static void main(String[] args) {
        // Factory: list preserves order and allows duplicates.
        List<String> languages = List.of("Java", "SQL", "Java");

        // Factory: set does not allow duplicate elements.
        Set<String> roles = Set.of("ADMIN", "EDITOR", "VIEWER");

        // Factory: small map.
        Map<String, Integer> statusCodes = Map.of(
                "OK", 200,
                "NOT_FOUND", 404
        );

        // Factory: map with more than 10 pairs.
        Map<String, String> headers = Map.ofEntries(
                Map.entry("Content-Type", "application/json"),
                Map.entry("Cache-Control", "no-cache"),
                Map.entry("X-Application", "demo")
        );

        // copyOf: unmodifiable snapshot.
        List<String> source = new ArrayList<>(List.of("An", "Bình"));
        List<String> snapshot = List.copyOf(source);
        source.add("Chi");

        // unmodifiableList: view reflecting source.
        List<String> view = Collections.unmodifiableList(source);
        source.add("Dung");

        // Mutable copy: modifiable.
        List<String> editable = new ArrayList<>(languages);
        editable.add("Kotlin");

        System.out.println(languages);
        System.out.println(roles.contains("ADMIN"));
        System.out.println(statusCodes.get("OK"));
        System.out.println(headers.get("Content-Type"));
        System.out.println(snapshot); // [An, Bình]
        System.out.println(view);     // [An, Bình, Chi, Dung]
        System.out.println(editable);
    }
}
~~~

Compile and run with JDK 17:

~~~bash
javac --release 17 CollectionFactoryDemo.java
java CollectionFactoryDemo
~~~

Key output:

~~~text
[Java, SQL, Java]
true
200
application/json
[An, Bình]
[An, Bình, Chi, Dung]
[Java, SQL, Java, Kotlin]
~~~

The example illustrates three data patterns:

- Collection factories create unmodifiable data right from the start.
- `copyOf` creates an unmodifiable structural copy.
- The `unmodifiableList` wrapper creates a read-only view reflecting changes from the source.
- `ArrayList` creates a mutable copy when the application needs to update data.

## 12. Practice Exercises

### Exercise 1: Choose the Right Factory

Create:

1. A List of days of the week, preserving order.
2. A Set of permissions `READ`, `WRITE`, `ADMIN`.
3. A Map mapping HTTP codes to labels, with 12 pairs.

**Suggested solution:**

~~~java
List<String> days = List.of(
        "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"
);

Set<String> permissions = Set.of("READ", "WRITE", "ADMIN");

Map<Integer, String> labels = Map.ofEntries(
        Map.entry(200, "OK"),
        Map.entry(201, "Created"),
        Map.entry(202, "Accepted"),
        Map.entry(204, "No Content"),
        Map.entry(301, "Moved"),
        Map.entry(302, "Found"),
        Map.entry(400, "Bad Request"),
        Map.entry(401, "Unauthorized"),
        Map.entry(403, "Forbidden"),
        Map.entry(404, "Not Found"),
        Map.entry(409, "Conflict"),
        Map.entry(500, "Server Error")
);
~~~

### Exercise 2: Why Does This Throw an Exception?

~~~java
List<String> names = List.of("An", "Bình");
names.add("Chi");
~~~

**Answer:** `List.of` returns an unmodifiable list. `add` is a structural modification operation, so it throws `UnsupportedOperationException`. If a mutable list is needed:

~~~java
List<String> names = new ArrayList<>(List.of("An", "Bình"));
names.add("Chi");
~~~

### Exercise 3: Compare View and Snapshot

~~~java
List<String> source = new ArrayList<>(List.of("A", "B"));
List<String> view = Collections.unmodifiableList(source);
List<String> snapshot = List.copyOf(source);

source.add("C");
~~~

What are the values of `view` and `snapshot`?

**Answer:**

- `view`: `[A, B, C]`, because the wrapper views the source list.
- `snapshot`: `[A, B]`, because `copyOf` preserves the structure at creation time.

### Exercise 4: Does an Unmodifiable Collection Make Objects Inside Immutable?

~~~java
List<StringBuilder> values = List.of(new StringBuilder("Java"));
values.get(0).append(" 17");
~~~

**Answer:** The `append` call is valid. The list does not allow adding/removing/replacing elements, but `StringBuilder` is a mutable object. After the call, the element's content is `Java 17`.

### Exercise 5: Choose a Structure When Ordering Is Required

An application needs a unique set of permissions that preserves declaration order and cannot be modified by callers.

**Hint:** You can build a `LinkedHashSet` to maintain insertion order, then provide an unmodifiable view or a copy with an appropriate ordering contract. Do not rely on the iteration order of `Set.of` or `Set.copyOf`.

## 13. Key Takeaways

When choosing a collection factory in Java 17, clarify three things:

1. **Which collection type is needed?** List preserves order and allows duplicates; Set disallows duplicates; Map maps key/value pairs.
2. **Where is the data created from?** Use `of(...)` for known elements; use `copyOf(...)` to create an unmodifiable collection from a source.
3. **Do you need a snapshot or a view?** `copyOf` creates a structural copy; `Collections.unmodifiable...` creates a read-only view reflecting changes to the source.

Finally, remember that **unmodifiable does not mean deep immutable**. A structurally unmodifiable collection can still contain mutable objects. If data needs full protection across multiple levels, use immutable elements and appropriate defensive copies for nested collections.

## 14. References

- [Oracle Java SE 17 — List API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): `List.of`, `List.copyOf`, and unmodifiable/value-based characteristics.
- [Oracle Java SE 17 — Set API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html): `Set.of`, `Set.copyOf`, duplicates, and iteration order.
- [Oracle Java SE 17 — Map API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): `Map.of`, `Map.ofEntries`, `Map.copyOf`, and key/value pair limits.
- [Oracle Java SE 17 — Collections API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html): `unmodifiableList`, `unmodifiableSet`, and `unmodifiableMap` wrappers.
- [OpenJDK JEP 269 — Convenience Factory Methods for Collections](https://openjdk.org/jeps/269): design of the collection factories introduced in Java 9.
