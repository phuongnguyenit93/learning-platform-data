# UnsupportedOperationException and Optional Operations in Java

> **Java Core – Exception** · Group: **Runtime Exceptions** · Primary scope: optional operations on Collection, List, Iterator, Map and the differences between mutable lists, fixed-size lists, unmodifiable views, and unmodifiable lists. Examples compiled and run with **Java 17**.

## 1. What is UnsupportedOperationException?

`java.lang.UnsupportedOperationException` (UOE) is an **unchecked exception** that extends `RuntimeException`. It indicates that the requested operation **is not supported by the specific object or API**.

~~~text
java.lang.Throwable
└── java.lang.Exception
    └── java.lang.RuntimeException
        └── java.lang.UnsupportedOperationException
~~~

A very common example:

~~~java
List<String> names = List.of("Lan", "Mai");
names.add("An"); // Throws UnsupportedOperationException.
~~~

This snippet is illustrative Java code inside a method and requires importing `java.util.List`. The object returned by `List.of(...)` is an **unmodifiable list**, so adding an element with `add` is not supported.

**Key point:** UOE **does not necessarily** mean "Java hasn't finished implementing the method." In many APIs of the Java Collections Framework, certain mutating operations are specified as **optional operations**: the interface has the method, but a valid implementation **is allowed not to support** that operation. When asked to perform an unsupported operation, it may throw UOE according to its contract.

Therefore, you must distinguish between:

- **The method exists in the interface:** for example, a variable of type `List<String>` can always syntactically call `add()`.
- **Whether the runtime object supports that operation:** `ArrayList` allows adding, whereas `List.of(...)` does not.
- **Whether the data is valid for the operation:** a list that supports `add` can still reject invalid elements, such as under a policy disallowing `null`, leading to a different exception.
- **Whether the result fits business requirements:** an operation permitted at runtime can still be wrong with respect to business rules.

### Learning Objectives

1. Understand why `UnsupportedOperationException` is unchecked and why the same `List` type can have different sets of supported operations.
2. Accurately distinguish `Arrays.asList` (**fixed-size, backed by array**), `Collections.unmodifiableList` (**unmodifiable view**), and `List.of` (**unmodifiable list**).
3. Predict UOE with `add`, `remove`, `set`, `clear`, operations via `Iterator`, `Map`, and factories.
4. Know that a **no-op** operation is not guaranteed to be accepted by every implementation.
5. Write APIs that clearly declare data mutability, know how to create a mutable copy, and avoid catching UOE as a substitute for contract design.
6. Verify output from a standalone Java 17 program.

## 2. What Does “Optional Operation” Mean Exactly?

Interfaces such as `Collection<E>`, `List<E>`, `Iterator<E>`, and `Map<K,V>` define common methods. However, not every implementing object is required to support **every update operation**.

Example:

~~~java
List<String> first = new ArrayList<>();
List<String> second = List.of();
first.add("A");  // Valid.
second.add("A"); // Throws UnsupportedOperationException.
~~~

This illustrative snippet requires importing `List` and `ArrayList`. Both variables have the **same static type** `List<String>`, but different implementations and mutation contracts.

This still follows Java rules: the interface defines an operation that can be called; the Collections Framework contract allows an implementation **not to support** certain update operations and to signal that with UOE.

### 2.1. Operation Groups That Are Commonly Optional

| API | Operations that may be unsupported | Example |
| --- | --- | --- |
| `Collection` | `add`, `addAll`, `remove`, `removeAll`, `retainAll`, `clear` | Unmodifiable collection |
| `List` | `set`, `add(index,...)`, `remove(index)`, and structural operations | Fixed-size or unmodifiable list |
| `Iterator` | `remove()` | Read-only iterator |
| `ListIterator` | `remove()`, `set(...)`, `add(...)` | Iterator that does not allow updates |
| `Map` | `put`, `putAll`, `remove`, `clear` | Unmodifiable map |
| `Map.Entry` | `setValue(...)` may be unsupported | Read-only entry |

These are **example groups**; it does not mean every method of every implementation in the table must throw UOE. Depending on the implementation, how it is called, and its specific contract, the same method name may succeed or reject the call.

### 2.2. Unchecked Does Not Mean It Can Be Ignored

UOE extends `RuntimeException`, so the compiler **does not require** declaring `throws UnsupportedOperationException` or catching it with `catch`. However, if it occurs and is unhandled, the current operation still terminates abnormally.

A method:

~~~java
static void appendName(List<String> list, String name) {
    list.add(name);
}
~~~

compiles without `throws`. However, **the method's contract is incomplete** if it does not state clearly that it requires a list supporting element addition. When a caller passes `List.of("A")`, the method will throw UOE at runtime.

If an API is designed to accept a read-only list, it **should not silently call `add`**. If modification is needed, document the requirement or create a mutable copy.

## 3. Distinguishing Three Common Models

Many UOE bugs come from confusing the following three kinds of objects:

| Creation method | Replace element via `set`? | Add/remove changes size? | Relationship to source data |
| --- | --- | --- | --- |
| `new ArrayList<>(...)` | Yes | Yes | Creates a new list containing the element references |
| `Arrays.asList(array)` | **Yes** | **No** | **Backed by** the passed-in array |
| `Collections.unmodifiableList(source)` | No (via view) | No (via view) | **View** reflecting changes from source |
| `List.of(...)` | No | No | Unmodifiable list created by factory |
| `List.copyOf(source)` | No | No | Provides an unmodifiable list, may reuse a suitable instance |
| `Stream.of(...).toList()` in Java 17 | No | No | Result is an unmodifiable list |

**Note:** "unmodifiable through one reference" is different from "the underlying data cannot be changed from elsewhere," and both are different from "the element objects held inside are immutable."

## 4. Arrays.asList: A Fixed-Size List, Not a Regular ArrayList

The method `java.util.Arrays.asList(T... a)` returns a fixed-size `List` **backed by an array**.

~~~java
String[] colors = {"red", "blue"};
List<String> list = Arrays.asList(colors);

list.set(0, "green");    // Supported.
list.add("gold");        // UnsupportedOperationException.
list.remove(0);         // UnsupportedOperationException.
~~~

This illustrative snippet requires importing `Arrays` and `List`. After `set(0, "green")`, the first element of the **original array** also becomes `"green"` because the list and array share the same element storage.

Common pitfalls:

- `Arrays.asList` **does not return `java.util.ArrayList`**, despite the similar name.
- The `set` method is supported because it **replaces** an element at an existing position without changing the size.
- `add/remove` in the usual sense would change the number of elements, so they are not supported.
- Changes to elements in the original array are observable through the list, and changes made via the list's `set` are observable through the array.
- A **fixed-size list is not the same as immutable/unmodifiable**: replacing elements is still allowed.
- An array can still contain `null`; the resulting list can contain `null` if the corresponding array contains null.

An option if you want to add/remove:

~~~java
List<String> editable = new ArrayList<>(Arrays.asList("red", "blue"));
editable.add("gold");  // Valid.
editable.remove("red"); // Valid.
~~~

This is an illustrative snippet requiring imports for `ArrayList`, `Arrays`, and `List`. The `ArrayList` constructor creates a **new resizable list**. It copies **the element references**, without automatically deep-cloning the objects inside.

### 4.1. Another Pitfall: Primitive Arrays

~~~java
int[] numbers = {1, 2, 3};
List<int[]> list = Arrays.asList(numbers);
System.out.println(list.size()); // 1
~~~

This is a valid Java example with appropriate imports. With a single `int[]` argument, the resulting list has one **element of type `int[]`**, not a `List<Integer>` of three numbers. This is a separate generics/varargs issue, not a direct cause of UOE, though it often appears in code that uses `Arrays.asList` and then tries to add/remove.

## 5. Collections.unmodifiableList: An Unmodifiable View

An unmodifiable wrapper is created with:

~~~java
List<String> source = new ArrayList<>(List.of("one", "two"));
List<String> view = Collections.unmodifiableList(source);
~~~

This illustrative snippet requires importing `Collections`, `ArrayList`, and `List`.

With `view`:

~~~java
view.add("three");       // UnsupportedOperationException.
view.set(0, "changed");  // UnsupportedOperationException.
~~~

However, the wrapper **retains a link to the underlying list**:

~~~java
source.add("three");
System.out.println(view); // [one, two, three]
~~~

When the source changes through the `source` reference, reading `view` reflects that change. This is an **unmodifiable view**, not an **immutable snapshot of the data at creation time**.

**Design consequences:**

- If a method returns `Collections.unmodifiableList(internal)` while still keeping and modifying `internal`, the caller can see the data change over time.
- If you want to provide a result that is **structurally stable** against subsequent changes to the source list, consider an unmodifiable copy such as `List.copyOf(source)` (given suitable data conditions and null contract).
- An unmodifiable wrapper **does not protect you** from another thread mutating the underlying list without synchronization. Nor does it automatically make the backing collection thread-safe.
- If elements in the list are mutable objects, callers can still modify **the internal state of elements** if they hold references to them. Being unable to modify **list structure** does not mean deep immutability.

Do not expose a view over a mutable internal structure if you need to avoid unpredictable side effects; choose explicitly between a "live read-only view" and a "detached snapshot."

## 6. List.of and List.copyOf: Unmodifiable List Structures

Since Java 9, `List.of(...)` creates unmodifiable lists (*unmodifiable lists*).

~~~java
List<String> names = List.of("Lan", "Mai");
names.add("An");      // UnsupportedOperationException.
names.set(0, "Hoa");  // UnsupportedOperationException.
names.remove(0);      // UnsupportedOperationException.
~~~

Here, not only is resizing forbidden; **element replacement** is also forbidden.

Important characteristics of `List.of`:

- Disallows adding/removing/replacing elements via update operations.
- Does not accept `null` elements; for example, `List.of("A", (String) null)` throws `NullPointerException` **at creation time**, not UOE from calling add.
- Element order reflects the declared argument order; you can access elements with `get(index)` for valid indices.
- Objects held inside **can still be mutable**. The list not supporting `set` does not prevent changing the state of an element object if the element class allows it.
- Do not rely on object identity (`==`) or synchronization locks on lists from these factories without understanding the *value-based* nature of instances from this factory family.

Since Java 10, `List.copyOf(source)` creates or returns an **unmodifiable** list structurally containing the elements of `source` at creation time:

~~~java
List<String> source = new ArrayList<>(List.of("A", "B"));
List<String> snapshot = List.copyOf(source);
source.add("C");
System.out.println(snapshot); // [A, B]
~~~

This example assumes `source` is a mutable `ArrayList`. The `snapshot` result **does not reflect the addition of C to source**. However:

- `List.copyOf` is not a **deep copy** of elements.
- It **rejects null elements** in the input; it may throw NPE if the collection contains null.
- The API is allowed to reuse a suitable unmodifiable list; you must not assume two calls always create two distinct instances.
- If an element is a mutable object, changing that object's state is still visible through both `source` and `snapshot`.

**Summary:** `Arrays.asList` = fixed-size backed by array; `Collections.unmodifiableList` = wrapper view; `List.of/List.copyOf` = structurally unmodifiable lists with specific contracts. They **cannot be substituted for one another unconditionally**.

## 7. Map.of and Optional Update Operations

Lists are not the only ones with optional operations. `Map` also defines several update operations:

~~~java
Map<String, Integer> quantities = Map.of("apple", 2);
quantities.put("banana", 3); // UnsupportedOperationException.
quantities.remove("apple");  // UnsupportedOperationException.
~~~

This illustrative snippet requires importing `java.util.Map`.

With `Map.of`, the map is unmodifiable. If updates are needed, create a mutable copy:

~~~java
Map<String, Integer> editable = new HashMap<>(Map.of("apple", 2));
editable.put("banana", 3); // Valid.
~~~

Requires importing `HashMap` and `Map`. `Map.of` also does not accept null keys or values; passing null to the factory can throw NPE instead of UOE.

**Do not overgeneralize:** Having a `put` method on `Map` does not prove every `Map` instance supports `put`. An unmodifiable view can also be created via `Collections.unmodifiableMap(source)`, with the same distinction between view and snapshot as with `List`.

### 7.1. Be Careful with keySet, values, and entrySet Views

A `Map` commonly provides views such as `keySet()`, `values()`, and `entrySet()`. Whether removing/modifying through these views is possible **depends on the source map's contract**.

An example:

~~~java
Map<String, Integer> mutable = new HashMap<>();
mutable.put("A", 1);
mutable.keySet().remove("A"); // Operation typically supported on HashMap.
~~~

However, the same method name on a view of an unmodifiable map can throw UOE. Do not assume "keySet is a Set so add/remove must work": a view API can disallow or allow individual operations.

For entries from different maps, `Map.Entry.setValue(...)` may or may not be supported. Read the implementation's Javadoc.

## 8. Iterator.remove and ListIterator: Optional Operations

`Iterator<E>` provides a `remove()` method to remove the last element returned by `next()`, **if the iterator supports it**.

Example with `ArrayList`:

~~~java
List<String> words = new ArrayList<>(List.of("first", "second"));
Iterator<String> iterator = words.iterator();

iterator.next();
iterator.remove(); // Supported for ArrayList's iterator.
System.out.println(words); // [second]
~~~

This snippet requires importing `ArrayList`, `Iterator`, and `List`. However:

~~~java
Iterator<String> iterator = List.of("first").iterator();
iterator.next();
iterator.remove(); // UnsupportedOperationException.
~~~

An iterator of an unmodifiable list cannot be used to structurally remove elements.

**Distinguish from IllegalStateException:** Even on an iterator **that supports remove**, calling `remove()` before `next()` or calling `remove()` repeatedly without another `next()` can throw `IllegalStateException` per the Iterator contract. By contrast, UOE indicates **the remove operation itself is not supported**. The two errors have different causes.

`ListIterator` adds `add` and `set` in addition to `remove`, but those update operations can also be optional. Using a `ListIterator` of an unmodifiable list does not make it editable.

### 8.1. Do Not Confuse Fail-Fast Iterators with Unsupported Operations

An iterator of a mutable collection may detect that the collection was structurally modified externally during iteration and throw `ConcurrentModificationException` according to the implementation's policy. That is **not** the same condition as `UnsupportedOperationException`.

- UOE: the requested iterator operation is not supported.
- `IllegalStateException`: calling an operation in an invalid state according to the Iterator protocol.
- `ConcurrentModificationException`: the implementation detected an improper structural modification during iteration.

Do not rely on fail-fast detection as a thread synchronization mechanism. This is a different topic from UOE, though it is often confused when code mutates a collection inside a loop.

## 9. Stream.toList and Collectors.toList Do Not Have the Same Mutability Guarantee

Since Java 16, `Stream.toList()` returns an **unmodifiable** `List`:

~~~java
List<String> items = Stream.of("A", "B").toList();
items.add("C"); // UnsupportedOperationException.
~~~

This example requires importing `java.util.stream.Stream` and `java.util.List`. In Java 17, this behavior is the explicit contract of `Stream.toList()`.

In contrast, with:

~~~java
List<String> items = stream.collect(Collectors.toList());
~~~

this is an illustrative snippet requiring a `stream` variable and importing `Collectors`. The Javadoc of `Collectors.toList()` **makes no guarantees** on the type, mutability, serializability, or thread safety of the returned `List`. Therefore, you should not treat the incidental current behavior as a long-term contract.

If you require a result that is **guaranteed to be a mutable ArrayList**, you can use:

~~~java
List<String> editable =
        Stream.of("A", "B").collect(Collectors.toCollection(ArrayList::new));
editable.add("C");
~~~

Requires importing `ArrayList`, `List`, `Collectors`, and `Stream`. Here you explicitly choose the collection supplier instead of guessing from the collector's name.

**Tip:** Read the Javadoc of the factory/collector carefully to distinguish "unmodifiable by specification" from "currently modifiable in a specific JDK release."

## 10. Complete Java 17 Program, Verified Stdout

Create the file **`OptionalOperationsDemo.java`**. The program tests several different APIs. Calls expected to throw UOE are placed in the `attempt` helper so subsequent cases continue to run; **this is a verification technique for this lesson, not a recommendation to catch and ignore UOE in production applications**.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;

public class OptionalOperationsDemo {
    private static void attempt(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + "=supported");
        } catch (UnsupportedOperationException ex) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        System.out.println("== fixed-size list backed by array ==");
        String[] words = {"red", "blue"};
        List<String> fixed = Arrays.asList(words);
        fixed.set(0, "green");
        System.out.println("fixed=" + fixed);
        System.out.println("array=" + Arrays.toString(words));
        attempt("fixed.add", () -> fixed.add("gold"));
        attempt("fixed.remove", () -> fixed.remove(0));
        System.out.println("fixed-after=" + fixed);

        System.out.println("== unmodifiable view ==");
        List<String> source = new ArrayList<>(List.of("one", "two"));
        List<String> view = Collections.unmodifiableList(source);
        System.out.println("view-before=" + view);
        attempt("view.add", () -> view.add("four"));
        attempt("view.set", () -> view.set(0, "changed"));
        source.add("three");
        System.out.println("view-after-source-change=" + view);

        System.out.println("== unmodifiable factories ==");
        List<String> immutable = List.of("a", "b");
        attempt("List.of.add", () -> immutable.add("c"));
        attempt("List.of.set", () -> immutable.set(0, "c"));
        List<String> copied = List.copyOf(source);
        attempt("List.copyOf.clear", copied::clear);
        List<String> streamList = Stream.of("x", "y").toList();
        attempt("Stream.toList.add", () -> streamList.add("z"));
        Map<String, Integer> map = Map.of("key", 1);
        attempt("Map.of.put", () -> map.put("other", 2));

        System.out.println("== iterator capabilities ==");
        List<String> editable = new ArrayList<>(List.of("first", "second"));
        Iterator<String> it = editable.iterator();
        it.next();
        it.remove();
        System.out.println("editable-after-remove=" + editable);
        Iterator<String> readOnlyIt = List.of("first").iterator();
        readOnlyIt.next();
        attempt("List.of.iterator.remove", readOnlyIt::remove);

        System.out.println("== explicitly mutable copy ==");
        List<String> mutableCopy = new ArrayList<>(immutable);
        mutableCopy.add("c");
        System.out.println("mutable-copy=" + mutableCopy);
        System.out.println("original=" + immutable);

        System.out.println("== null contract ==");
        System.out.println("Arrays.asList-null=" + Arrays.asList("ok", null));
        try {
            List.of("ok", (String) null);
        } catch (NullPointerException ex) {
            System.out.println("List.of-null=NullPointerException");
        }
    }
}
~~~

### Compile and Run

~~~bash
javac --release 17 -encoding UTF-8 OptionalOperationsDemo.java
java OptionalOperationsDemo
~~~

**Exact stdout verified by compiling and running:**

~~~text
== fixed-size list backed by array ==
fixed=[green, blue]
array=[green, blue]
fixed.add=UnsupportedOperationException
fixed.remove=UnsupportedOperationException
fixed-after=[green, blue]
== unmodifiable view ==
view-before=[one, two]
view.add=UnsupportedOperationException
view.set=UnsupportedOperationException
view-after-source-change=[one, two, three]
== unmodifiable factories ==
List.of.add=UnsupportedOperationException
List.of.set=UnsupportedOperationException
List.copyOf.clear=UnsupportedOperationException
Stream.toList.add=UnsupportedOperationException
Map.of.put=UnsupportedOperationException
== iterator capabilities ==
editable-after-remove=[second]
List.of.iterator.remove=UnsupportedOperationException
== explicitly mutable copy ==
mutable-copy=[a, b, c]
original=[a, b]
== null contract ==
Arrays.asList-null=[ok, null]
List.of-null=NullPointerException
~~~

The output deliberately prints the **exception class name** without relying on `getMessage()` of UOE (which may have no message or differ across implementations). The code requires no files, network, or external dependencies, and is compatible with Java 17 source level. Operations expected to fail are caught in the helper so the process does not abort midway.

### 10.1. Interpreting the Fixed-Size List Group

- `fixed.set(0,"green")` succeeds, replacing the element in the list and the **underlying array**. Thus both `fixed` and `array` lines output `[green, blue]`.
- `fixed.add("gold")` is not supported because it would change the size.
- `fixed.remove(0)` is not supported because removing an element changes the size.
- After the two exceptions, the list contents remain `[green, blue]` in the example. No elements were added or removed.

**Note:** If another implementation throws UOE when you try `set`, there is no contradiction: `set` itself is an optional operation on `List`; `Arrays.asList` supporting `set` is that list's own contract.

### 10.2. Interpreting the Unmodifiable View

`Collections.unmodifiableList(source)` disallows `view.add` and `view.set`. However, another reference `source` can still add `"three"`, so reading `view` produces `[one, two, three]`.

This demonstrates:

- **Disallowing modification through a view** does not mean disallowing other references from modifying the backing object.
- An API can return a read-only view to prevent the caller from actively mutating the collection through that reference, without automatically creating a snapshot.
- If you need to decouple the structure from the source, consider creating a snapshot according to a specific contract.

### 10.3. Interpreting Factories and Stream

`List.of`, `List.copyOf`, `Stream.toList()`, and `Map.of` all produce values where **the tested update operations are not supported**. The program prints UOE for `add`, `set`, `clear`, or `put`, respectively.

Do not treat this as proof that every `List` or `Map` API is immutable. **The creation source and object contract** determine which operations are supported.

### 10.4. Interpreting Iterator

The `ArrayList` iterator allows `remove` after `next`. The `List.of` iterator does not allow modifying the list, so `remove` throws UOE. A reference declared as `Iterator<String>` does not by itself determine whether `remove` is supported.

### 10.5. Interpreting Mutable Copy and Null

`new ArrayList<>(immutable)` creates a new list that allows adding elements, while the original `immutable` list remains unchanged. `Arrays.asList("ok", null)` can contain null, whereas `List.of("ok", (String)null)` throws **NPE at the factory** because it does not accept null.

These are two different kinds of errors: **UOE** when an unsupported update operation is requested; **NPE** when null input is disallowed. Do not catch UOE to handle null data, or vice versa.

## 11. Optional Does Not Mean Every Call Must Throw

A subtle point in the Collections Framework: for optional operations, behavior **when the operation has no actual effect** can depend on the implementation's contract.

An example you can try:

~~~java
Collection<String> items = Collections.unmodifiableCollection(source);
items.addAll(Collections.emptyList());
~~~

This illustrative snippet requires importing `Collection`, `Collections`, and a compatible `source` variable. Because the collection being added is empty, if the operation were performed, the size would not change. **You must not universally assume** that this case always succeeds or always throws UOE for every `Collection` implementation.

Under the general `Collection` contract, some optional operations **may** throw an exception even when the call causes no change. Another implementation may choose to return a result such as `false` when no elements were added.

Practical consequences:

- Do not write business logic based on the trick "try `addAll(empty)` to see if a Collection is editable."
- Do not infer mutability from a call that makes no structural change.
- Do not try to **probe mutability by attempting to mutate a shared object**: the probe could cause side effects if supported.
- Read the **Javadoc and API contract** of the provided object, or proactively create a mutable copy as needed.

Similarly, `removeIf(predicate)` may return `false` when no element matches the condition in one implementation, while the update operation is unsupported in another implementation. The outcome depends on the class's policy and method implementation; do not use "no elements were removed" as proof of permission to modify the collection.

## 12. Do Not Use Catching UnsupportedOperationException as a Primary Control Mechanism

An anti-pattern:

~~~java
try {
    list.add(value);
} catch (UnsupportedOperationException ex) {
    // Ignore to report completion.
}
~~~

This illustrative snippet assumes `list` and `value` are already defined. If the application needs to **actually add the element** but the error is ignored, the program may falsely report success and lose data.

Better yet, choose a strategy based on the contract:

**If the caller must pass a mutable list:**

~~~java
static void appendRequired(List<String> destination, String value) {
    destination.add(value);
}
~~~

Document clearly that `destination` must support `add`, and let the error propagate if the caller violates the contract. Do not catch UOE and return a fake status.

**If the method accepts any list and always needs a new result:**

~~~java
static List<String> appendCopy(List<String> input, String value) {
    List<String> result = new ArrayList<>(input);
    result.add(value);
    return result;
}
~~~

These illustrative methods require importing `List` and `ArrayList`. The second method creates a mutable copy so **it does not need to modify the input**. If the contract wants an unmodifiable result, it can return `List.copyOf(result)` when elements are non-null and API conditions allow.

**If "task not supported" is a valid framework path:** you can handle UOE at a **well-documented boundary**, for example translating it into a "this feature is not supported" message. However, do not use UOE as a general operation-permission check for all collections, especially when it could hide bugs or be confused with business access errors.

## 13. Designing APIs Intentionally Around Mutability

### 13.1. Reading Data and Modifying Data Are Two Different Contracts

A method that only **reads** a list:

~~~java
static long countNonBlank(List<String> items) {
    return items.stream()
            .filter(s -> s != null && !s.isBlank())
            .count();
}
~~~

This is a valid illustrative method requiring `List` to be imported. It does not need `add/remove/set` capabilities. Callers can pass an `ArrayList`, `Arrays.asList`, or an unmodifiable `List` with suitable data.

Conversely:

~~~java
static void addDefault(List<String> items) {
    items.add("default");
}
~~~

this method **requires a list that supports add**. The type `List<String>` alone cannot express that commitment at compile time. Write Javadoc, use a dedicated type when a stronger contract is needed, or return a new copy.

### 13.2. Snapshots and Defensive Copies

If you want to return a result to the caller that **cannot be structurally modified** and is unaffected by changes from a mutable source list:

~~~java
List<String> result = List.copyOf(source);
return result;
~~~

This illustrative snippet inside an appropriate method requires importing `List`. `List.copyOf` rejects null elements, so check the data contract first.

If the source data may contain null and you still want an unmodifiable copy, another approach is:

~~~java
List<String> snapshot =
        Collections.unmodifiableList(new ArrayList<>(source));
~~~

This creates a new `ArrayList`, then creates an unmodifiable view of **that new copy**; if the code does not retain a mutable alias and does not allow unwanted mutation of internal elements, the list structure stays more stable than wrapping `source` directly. However, the copy is still **shallow**: mutable elements can change state.

### 13.3. Avoid Claiming “Immutable” When Only Unmodifiable

The word "immutable" can be understood as **all observable state cannot change**, whereas an unmodifiable list only has the contract that update operations through the list API are not supported. If elements are `StringBuilder` or objects with setters, anyone holding a reference can still modify them.

A **deeply immutable model** requires designing the entire object graph, not just wrapping a list. UOE helps prevent modifying a list through a reference; **it does not by itself implement an immutable object graph**.

## 14. When Should You Throw UnsupportedOperationException Yourself?

A class implementing an interface with optional operations can throw UOE to explicitly declare **it does not support that operation**:

~~~java
class ReadOnlyIntStore {
    private final List<Integer> values = List.of(1, 2, 3);

    int size() {
        return values.size();
    }

    void add(int value) {
        throw new UnsupportedOperationException("store is read-only");
    }
}
~~~

This is an illustrative class definition requiring `List` to be imported. A cleanly designed API might **not define an `add` method** at all if that operation is not part of the class's capabilities. However, when a method is present due to an interface/abstract class with optional operations or API compatibility requirements, throwing UOE can be appropriate.

**Do not overuse UOE:**

- Do not use UOE instead of `IllegalArgumentException` for invalid arguments if the operation is supported for other values.
- Do not use UOE instead of `IllegalStateException` when the operation **is supported** but the object is temporarily in an unsuitable state.
- Do not use UOE for authorization errors simply because the user is not allowed to act: a business API may need a clear access-permission exception/response.
- Do not use UOE vaguely for "not coded yet" in production if the contract promises the method works; implement the feature properly or change the contract.

Conceptual distinction:

| Condition | Typically more appropriate exception |
| --- | --- |
| Operation is not within the capabilities supported by the object/API | `UnsupportedOperationException` |
| Invalid argument for an otherwise supported operation | `IllegalArgumentException`, NPE, or contract-appropriate type |
| Object is in a state where an otherwise supported operation cannot run | `IllegalStateException` |
| Index outside valid list/array bounds | `IndexOutOfBoundsException` or corresponding subtype |
| `Iterator.remove` is not implemented/supported | `UnsupportedOperationException` |
| `Iterator.remove` is supported but called out of sequence | `IllegalStateException` |

The final condition and specific exception must follow the **Javadoc of the API in use**, not just general heuristics in the table.

## 15. AbstractCollection, AbstractList, and Default Implementations

Some abstract base classes in the Collections Framework provide default implementations for optional operations. For example, `AbstractCollection.add(E)` throws UOE by default unless a subclass overrides it with supporting add behavior.

A subclass may implement all query methods while **not providing a corresponding update mechanism**, leading to UOE when a caller invokes an optional operation. `AbstractList` also provides default implementations that may not support add/remove/replace operations if the subclass does not implement them.

This explains why "implements List" **does not automatically mean** "mutable like ArrayList." Abstract helper classes reduce boilerplate code, but the subclass and its contract determine mutability.

When writing your own collection:

1. Read the contract of query and update methods carefully.
2. Do not claim the collection is editable in Javadoc if it only supports `get` and `size`.
3. If you support an optional operation, implement all of its invariants and required error checks.
4. Check iterator behavior: `remove`, `set`, and `add` do not necessarily appear together.
5. Test successful updates, unsupported operations, and invalid-state cases according to the contract.

## 16. Debugging a Real UnsupportedOperationException

When you see a stack trace containing:

~~~text
java.lang.UnsupportedOperationException
    at ...
    at com.example.Service.updateItems(Service.java:42)
~~~

this is an **illustrative format** example, not a fixed stack trace. Follow these steps:

1. **Find the first method in your code** on the stack trace, e.g., `updateItems` calling `add` or `remove`.
2. **Identify the actual runtime object**: was it created with `new ArrayList`, `Arrays.asList`, `List.of`, `List.copyOf`, `Collections.unmodifiableList`, or obtained from some library?
3. **Check the exact operation**: replacement (`set`), resizing (`add/remove`), or an operation through an iterator?
4. **Read the implementation's Javadoc** to determine whether the optional operation is supported.
5. **Find where the collection is created or passed**; do not just patch the call site if the input contract is the root cause.
6. **Determine whether mutation is actually required**. If not, avoid mutating; if so, decide whether to create a copy or require the caller to provide a mutable collection.
7. **Test with multiple implementations** that satisfy the API contract, not just `ArrayList`.
8. **Check aliasing and threading** if using an unmodifiable view whose backing collection changes elsewhere.

If simply calling `list.get(0)` produces UOE, that is unusual behavior for a standard `List` on this query operation; inspect the actual implementation and stack trace rather than assuming every UOE comes from `add`.

**Do not use UOE's message text for logic:** some implementations may throw UOE with no message, or the message may differ between versions. Relying on the API contract and exception type is more meaningful than parsing the message.

## 17. Common Misconceptions and Mistakes

1. **“If it implements List, add always works.”** False: `add` is an optional operation.
2. **“`Arrays.asList` returns a normal mutable ArrayList.”** False: it returns a fixed-size list backed by an array.
3. **“`Arrays.asList` cannot change size, so all modifications are forbidden.”** False: `set` is supported.
4. **“UnmodifiableList is a snapshot.”** Not necessarily: `Collections.unmodifiableList` returns a view reflecting changes to the source.
5. **“`List.of` only forbids add, while set is allowed.”** False: `set` also throws UOE.
6. **“`List.copyOf` always creates a new list object.”** False: the API may reuse an appropriate unmodifiable instance.
7. **“An unmodifiable list means its elements are completely immutable.”** False: mutable elements can change state.
8. **“An unmodifiable view means thread-safe.”** False: the backing collection can still be modified without synchronization.
9. **“`Stream.toList()` in Java 17 returns an editable ArrayList.”** False: the result is unmodifiable.
10. **“`Collectors.toList()` guarantees an editable list.”** The Javadoc makes no such guarantee.
11. **“`getOrDefault`, `addAll(empty)`, or `removeIf` can always test mutability.”** False: behavior can depend on implementation and state.
12. **“Every Iterator allows remove.”** False: `Iterator.remove` is an optional operation.
13. **“If Iterator.remove throws IllegalStateException, the operation is unsupported.”** Not necessarily: it may be due to calling it out of sequence.
14. **“NPE on `List.of(null)` is also UnsupportedOperationException.”** False: it is a different error type because the factory rejects null.
15. **“Catching UOE and ignoring it is always safe.”** False: it can silently lose data and falsely report success.
16. **“You can determine the mutability of any List with `instanceof List`.”** False: the general type does not describe full update capabilities.
17. **“Creating `new ArrayList<>(source)` deep-copies all objects.”** False: it only copies the structure and element references.
18. **“Map has put, so every map allows put.”** False: `Map.of` and unmodifiable wrappers block mutation.
19. **“UOE is always a bug from a developer who hasn't coded the method yet.”** False: many optional operations are intentionally unsupported by design.
20. **“If there is no actual change, a method on an unmodifiable collection is guaranteed to succeed.”** False: an optional operation can still throw UOE.
21. **“UOE is a checked exception.”** False: `UnsupportedOperationException extends RuntimeException`.
22. **“`Collections.unmodifiableList` protects the source from all other references.”** False: a mutable alias can still modify the source.

## 18. Self-Check Exercises

**Question 1.** Does the following snippet print `[B, A]`?

~~~java
String[] a = {"A", "B"};
List<String> l = Arrays.asList(a);
l.set(0, "B");
System.out.println(Arrays.toString(a));
~~~

*Answer:* It prints `[B, B]`. The `set` operation replaces index 0 of the underlying array; index 1 remains `"B"`.

**Question 2.** What error does `Arrays.asList("A", "B").add("C")` encounter?

*Answer:* `UnsupportedOperationException`, because the list is fixed-size and does not support adding elements.

**Question 3.** Why can `Collections.unmodifiableList(source)` change its observable data even though the caller cannot call `add` through the wrapper?

*Answer:* It is a **view** of `source`. Another reference can still mutate `source`, causing the view to reflect the change.

**Question 4.** Is `List.of("A").set(0, "B")` valid?

*Answer:* It is syntactically valid to call, but it throws UOE at runtime because the list does not allow replacing elements.

**Question 5.** If you want to add elements to the result of `Stream.toList()` in Java 17, what is a clear approach?

*Answer:* Create a mutable copy: `new ArrayList<>(stream.toList())` and then add elements, or use `Collectors.toCollection(ArrayList::new)` from the start.

**Question 6.** Does `List.copyOf(source)` always create a shallow-independent structure from a source `ArrayList`?

*Answer:* When `source` is a mutable `ArrayList`, the resulting list is structurally unaffected by subsequent `add`/`remove` calls on `source`. However, the API may reuse an input that is already suitably unmodifiable, and mutable elements can still change state.

**Question 7.** Why does `List.of("A", (String)null)` throw NPE instead of UOE?

*Answer:* The error occurs **when creating the list** because `List.of` forbids null elements, not from calling an unsupported update operation.

**Question 8.** With an `ArrayList` iterator, what does calling `remove()` before calling `next()` report?

*Answer:* `IllegalStateException` per the Iterator protocol rules, unlike UOE when an iterator does not support `remove`.

**Question 9.** Why should you not "try `addAll(Collections.emptyList())`" to determine whether a collection is modifiable?

*Answer:* For optional operations that have no actual effect, the contract may allow implementations to react differently; the test cannot reliably determine mutation capability.

**Question 10.** What error does `Map.of("A", 1).put("B", 2)` throw?

*Answer:* `UnsupportedOperationException`, because the map is unmodifiable.

**Question 11.** If a method accepts `List<String>` and must append to it, what should be declared?

*Answer:* Document that the parameter must support `add`, or design the method to create/return a mutable copy so it does not depend on input mutability.

**Question 12.** Can `UnsupportedOperationException` be used for "invalid user data"?

*Answer:* No, if the operation itself is supported; an argument or validation error type is more appropriate.

## 19. Official Java 17 References

- [UnsupportedOperationException API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/UnsupportedOperationException.html): unchecked class indicating that the requested operation is not supported.
- [Collection API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html): optional operations and their behavior.
- [List API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): update methods, `List.of`, `List.copyOf`, and unmodifiable lists.
- [Arrays.asList API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)): fixed-size list backed by an array.
- [Collections.unmodifiableList API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): unmodifiable view over a source list.
- [Iterator API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html): optional `remove()` and iterator state.
- [ListIterator API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html): update operations of a bidirectional iterator.
- [Map API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): `put/remove` and unmodifiable map factories.
- [Stream.toList API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()): unmodifiable `List` result.
- [Collectors.toList API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toList()): no guarantee of list mutability.
- [AbstractCollection API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractCollection.html): default implementations of optional operations.
- [AbstractList API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html): support for creating `List` implementations with varying update capabilities.

**Remember:** `UnsupportedOperationException` is an unchecked exception that typically occurs when calling an **optional operation** that the object does not support. Do not equate `List` with `ArrayList`, fixed-size with unmodifiable, view with snapshot, or unmodifiable with deeply immutable. To avoid UOE properly, **identify the mutability contract from where the data is created and from the API**, and if structural modification is needed, create an appropriate mutable copy instead of try-catching and ignoring the error.
