# Copying Mutable Components When Independence Is Required

## 1. The Problem: Copying an Object Does Not Necessarily Create Independent State

In Java, reference-type variables hold **references to objects**, not the entire contents of the objects. Two outer objects may be distinct while still pointing to **the same inner component**. When that component is mutable, modifying it through one side can cause the observable state of the other side to change.

For example, when creating a profile from an `Address` supplied by the caller, merely assigning `this.address = address` makes the profile and the caller share the same `Address`. If the caller changes the city, the profile also sees the new city. The same happens with arrays, `ArrayList`, `HashMap`, or mutable objects nested inside collections.

**Goal of defensive copying:** at boundaries where the contract requires independence, each side must own its mutable state; valid modifications from one side must not unintentionally alter the state of the other side.

Three ideas must be distinguished:

- **Different references:** `a != b` only states that `a` and `b` are not the same outer object.
- **Value equality:** `a.equals(b)` depends on the `equals()` contract; two independent copies can still be equal by value.
- **Mutable state independence:** no shared mutable component remains that one side can mutate and cause unintended effects. This is what must be tested when the problem requires independence.

Not every component must be copied. `String`, `Integer`, `BigDecimal`, and most types in `java.time` (such as `LocalDate`, `Instant`) are immutable, so they can usually be shared safely. The focus is on **components that are actually mutable and can be modified through a shared reference**.

## 2. Shallow Copy, Deep Copy, and the Level of Copying Actually Needed

Suppose `Order` has `List<OrderLine> lines` and each `OrderLine` has a mutable quantity.

| Approach | What is separated? | Remaining risk |
| --- | --- | --- |
| `Order b = a;` | No copy at all; same `Order` object | All state is shared |
| Copy `Order` but keep the old `lines` | Only the outer `Order` object | Adding/removing/modifying elements can affect both |
| `new ArrayList<>(a.lines)` | Creates a new list, separating element addition/removal | The inner `OrderLine` instances are still shared |
| Create a new list and copy each mutable `OrderLine` | Separates both the list structure and each mutable element | Must continue checking deeper nested mutable components |
| Copy the entire object graph | Separates all mutable objects according to the chosen policy | Costly and must handle aliases, cycles, and special resources |

**Shallow copy** usually only creates a new outer shell, while inner references still point to the old objects. **Deep copy** recursively copies the mutable components that need separation; this concept must be defined by the data model's contract, not simply “copy as much as possible”.

For example, if `OrderLine` holds a `String` product code, there is no need to create a new `String`. If it holds an immutable `DiscountPolicy` shared by design, the reference can be kept. If it holds a mutable `Address` that the order must manage on its own, it must be copied.

**Decision principle:** ask “Who owns and can modify this object?”; then separate only the mutable parts for which the contract requires independence.

## 3. Copying on Both Input and Output

A class that wants to control its own state usually needs **two-way** protection:

1. **When receiving data** via a constructor, setter, or update method: copy mutable input before storing it, preventing the caller from mutating the object after passing it in.
2. **When returning data** via a getter or state-export method: return a copy, or return an appropriate truly immutable interface, preventing the caller from mutating internal state.

Copying only at initialization while having the getter return the internal field directly still leaks state. Conversely, copying only in the getter while the constructor retains the input reference still allows the caller to mutate from the outside.

**Note:** `final` only prevents reassigning the reference field; `private final List<Item> items` can still hold a mutable list or mutable elements. `Collections.unmodifiableList(list)` creates a view that forbids modification through the view, but still reflects changes made through the original `list`. `List.copyOf(list)` provides a structurally unmodifiable list, but **does not deep-copy its elements**.

## 4. Java 17+ Example: Separating Mutable Objects Nested in a List

The example has two classes: `Address` has a mutable city; `Profile` needs to retain a snapshot of the address state at initialization. Therefore `Profile` copies `Address` both for the single field and for each element of `List<Address>`. When returning data, it also creates copies so internal state is not exposed.

Save to **`DefensiveCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class DefensiveCopyDemo {
    static final class Address {
        private String city;

        Address(String city) {
            this.city = Objects.requireNonNull(city);
        }

        Address(Address source) {
            this(Objects.requireNonNull(source).city);
        }

        String city() {
            return city;
        }

        void setCity(String city) {
            this.city = Objects.requireNonNull(city);
        }
    }

    static final class Profile {
        private final String name;
        private final Address currentAddress;
        private final List<Address> priorAddresses;

        Profile(String name, Address currentAddress,
                List<Address> priorAddresses) {
            this.name = Objects.requireNonNull(name);
            this.currentAddress = new Address(
                    Objects.requireNonNull(currentAddress));

            Objects.requireNonNull(priorAddresses);
            List<Address> copies = new ArrayList<>(priorAddresses.size());
            for (Address address : priorAddresses) {
                copies.add(new Address(address));
            }
            this.priorAddresses = List.copyOf(copies);
        }

        Address currentAddress() {
            return new Address(currentAddress);
        }

        List<Address> priorAddresses() {
            List<Address> copies = new ArrayList<>(priorAddresses.size());
            for (Address address : priorAddresses) {
                copies.add(new Address(address));
            }
            return copies;
        }

        String describe() {
            List<String> cities = priorAddresses.stream()
                    .map(Address::city)
                    .toList();
            return name + " @ " + currentAddress.city()
                    + ", previous=" + cities;
        }
    }

    public static void main(String[] args) {
        Address current = new Address("Ha Noi");
        Address previous = new Address("Da Nang");
        List<Address> history = new ArrayList<>();
        history.add(previous);

        Profile profile = new Profile("An", current, history);

        // Mutate sources after passing them to the constructor.
        current.setCity("Hue");
        previous.setCity("Can Tho");
        history.clear();
        System.out.println(profile.describe());

        // Mutate copies received from getters.
        profile.currentAddress().setCity("Nha Trang");
        List<Address> exported = profile.priorAddresses();
        exported.get(0).setCity("Hai Phong");
        exported.clear();
        System.out.println(profile.describe());
    }
}
~~~

Compile and run with JDK 17 or higher:

~~~bash
javac -encoding UTF-8 DefensiveCopyDemo.java
java DefensiveCopyDemo
~~~

Output:

~~~text
An @ Ha Noi, previous=[Da Nang]
An @ Ha Noi, previous=[Da Nang]
~~~

**Layer-by-layer protection analysis:**

- `new Address(currentAddress)` prevents external `current.setCity(...)` from mutating `Profile`.
- The loop copying each `Address` element detaches the mutable objects that `history` originally referenced. `new ArrayList<>(history)` alone would not be enough.
- `List.copyOf(copies)` keeps the internal list structure unable to add/remove elements; element independence comes from the preceding `new Address(address)` calls.
- The `currentAddress()` getter returns a copy; the `priorAddresses()` getter creates a new list **and** copies each element. The caller can mutate or clear the returned data without altering the profile.
- `name` uses immutable `String`; there is no need to copy it.

This example chooses a **snapshot-at-creation** policy. If business logic wants `Profile` to always see the updated address of a live external object, forcing deep separation would violate the business meaning. The ownership policy must decide the copy strategy first.

## 5. Common Data Types and Copy Options

### Arrays

For primitive arrays such as `int[]`, `Arrays.copyOf` copies the values and therefore suffices to separate the state of a one-dimensional array.

The following snippet illustrates a class usable in a Java program that imports `java.util.Arrays` and `java.util.Objects` (this is an illustrative snippet, without a standalone `main`):

~~~java
final class ScoreBoard {
    private final int[] scores;

    ScoreBoard(int[] scores) {
        int[] source = java.util.Objects.requireNonNull(scores);
        this.scores = java.util.Arrays.copyOf(source, source.length);
    }

    int[] scores() {
        return java.util.Arrays.copyOf(scores, scores.length);
    }
}
~~~

For `Address[]`, `Arrays.copyOf` only creates a **new array containing the same Address references**; each element must be copied if `Address` is mutable. For `int[][]`, `array.clone()` or `Arrays.copyOf(array, ...)` only separates the outer array; to separate all rows, each inner `int[]` must be copied.

### Collections and Maps

- `new ArrayList<>(source)`, `new HashSet<>(source)`, or `new HashMap<>(source)`: copies the container structure; elements, keys, and values share the same references if they are objects.
- `List.copyOf(source)`, `Set.copyOf(source)`, `Map.copyOf(source)`: creates collections that cannot be updated through their APIs, **does not guarantee mutable elements/keys/values are separated**; these factories also reject null elements or entries.
- If the values of `Map<String, MutableValue>` need independence, create a new map **and copy each MutableValue**. If keys are also mutable, a safe key design is needed: mutating a key currently inside a `HashMap` can break the `hashCode/equals` contract and cause lookups to fail.
- For nested collections, examine each layer in turn: copying the outer list does not mean sublists or the objects inside them have been copied.

### Legacy Date-Time Objects and Immutable Types

`java.util.Date` and `Calendar` are mutable; if still required, copy them on input/output (for example `new Date(original.getTime())`, and for `Calendar` use `clone()` when appropriate). Modern types in `java.time` such as `LocalDate`, `LocalDateTime`, and `Instant` are immutable and are usually a better choice for new data models.

**There is no single formula for all types:** data streams, buffers, sockets, file handles, threads, locks, and objects holding system resources cannot be meaningfully “deep copied” simply by traversing fields; you must define a recreation, controlled sharing, or no-copy policy.

## 6. Copy Constructors, Factories, Clone, and Serialization

A **copy constructor** (for example `new Address(existing)`) or a **factory** (for example `Address.copyOf(existing)`) expresses copy rules clearly. They are readable and allow controlling which fields are kept, copied, normalized, or rejected.

`Object.clone()` only performs basic field-level copying; for reference fields, the copy still shares the inner objects. `Cloneable` and overriding `clone()` do not automatically turn a class into a deep-copying one. If inheritance involves mutable state, ensuring correct copying becomes even more complex.

Serialization followed by deserialization should not be used as a general copy solution: it requires the graph to be serializable, consumes resources, carries security constraints, and can distort the semantics of special objects/resources. Consider it only when the data contract and serialization format themselves were designed for that purpose.

A `copy()` method should document clearly: whether it is shallow or deep per field, whether shared-reference relationships inside the graph are preserved, and how null, cycles, and resources are handled.

## 7. Tricky Points in Complex Object Graphs

### Preserving Shared Structure Inside the Copy

Suppose the original object has `left` and `right` both pointing to **one** `Node`. When deep-copying, there are two different policies: (a) in the copy, `left` and `right` still point to **one new Node**; or (b) create two distinct `Node`s. Both detach from the original, but the internal behavior of the copy differs.

If alias structure must be preserved, use an `IdentityHashMap<Original, Copy>` mapping by **reference identity** and check whether a node has already been copied before creating a new one. This approach also handles cyclic graphs like `a.next = b; b.next = a` without infinite recursion. Do not use a `HashMap` based on `equals()` for distinguishing original nodes that have equal values but different identities.

### Inheritance, Invariants, and Domain Logic

A copy constructor must preserve invariants: validate inputs, avoid unwanted aliases, and avoid calling overridable methods during initialization if doing so breaks correctness. Do not blindly copy caches, listeners, or business IDs: a new copy may require its own ID, recomputed cache, or separate listeners according to business requirements.

### Concurrency and Performance

Copying protects against **mutation through shared references after the copy time**, but does not automatically guarantee a consistent snapshot when another thread mutates the source during copying. For concurrent data, appropriate synchronization, source-provided snapshots, or immutable structures are needed.

Deep copying typically costs time and memory proportional to the number of copied components. For large data or frequent copies, consider immutable models, persistent data structures, updates through encapsulated APIs, or clear ownership design. Optimize only after the independence contract is established.

## 8. Common Bugs and How to Detect Them

| Bug | Why it is wrong | How to fix |
| --- | --- | --- |
| `this.items = input;` when independence is needed | Retains the input list as-is | Copy the structure, and also mutable elements if needed |
| `new ArrayList<>(input)` treated as deep copy | Element objects are still shared | Copy each mutable element |
| Getter returns internal array/list/Date directly | Callers mutate through the getter | Return a defensive copy or an immutable API |
| Relying only on `final` or `record` | Component referencing a mutable object can still be mutated | Normalize/copy in constructor and use defensive accessors if needed |
| Using `Collections.unmodifiableList(input)` to “snapshot” data | The view still sees changes via `input` | Create a snapshot first, then decide whether to deep-copy elements |
| Using `clone()` and assuming all fields are independent | Default clone is shallow | Explicitly define and test every mutable field |
| Blindly deep-copying every object | Costly or breaks business identity/resources | Copy according to ownership and invariant contracts |

**Testing matters more than just comparing `equals()`:**

1. Construct the copy; verify initial data is equivalent.
2. Mutate each mutable component of the **source**; verify the copy remains unchanged.
3. Mutate each mutable component **exported via getters**; verify internal state remains unchanged.
4. If the class supports object copying, mutate the copy and ensure the original does not change.
5. For nested structures, test both adding/removing elements and mutating **element contents**; for graphs with aliases/cycles, check reference relationships per the contract.
6. Test null cases, empty lists, aliased objects, and concurrent access if the class commits to supporting it.

For example, checking `copy != original` only confirms different shells; deeper mutations must be attempted to catch shared mutable state.

## 9. Process for Applying to Design

When designing a Java class requiring independence:

1. **List fields and nested dependencies.** Identify which types are immutable, which are mutable, and which own resources.
2. **Define ownership boundaries.** Is the data a snapshot? Who is allowed to mutate? Should source updates automatically propagate to this object?
3. **Choose a strategy per field.** Share immutables; copy mutables when independence is needed; use controlled update APIs for state that must be shared.
4. **Protect all entry and exit paths.** Constructors, setters, getters, builders, copy constructors, factories, and collection-returning methods can all expose references.
5. **Test with mutations from both sides.** Avoid checking only initial values or outer object identity.
6. **Evaluate performance and consistency.** Ensure copy rules do not break business contracts or concurrency requirements.

**Self-check:** Given `List<MutableAddress> addresses`, is setting `this.addresses = List.copyOf(addresses)` enough for an object to be independent?

**Answer:** No, if the caller still holds the `MutableAddress` instances and can mutate them. `List.copyOf` only controls the list structure; each mutable address must be copied, and then the collection snapshot stored. When exporting the list, also avoid exposing the internal mutable addresses externally if you do not want callers to mutate them.

**Takeaway:** The goal is not to force every object into a deep copy; the goal is **not to accidentally share mutable state where the contract requires independence**.
