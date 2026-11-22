# Choosing Copy Scope Based on Data Ownership in Java

**Context:** Java core → object-contract → copying and independence. When creating a copy of an object, the deciding question is not immediately “shallow or deep copy?”, but rather **who owns which data, who is allowed to change that data, and after copying, which changes must be independent?** Ownership here is a **design/API convention**, not an ownership mechanism enforced by the Java compiler.

## 1. Copying to Protect Ownership Boundaries

Java reference variables point to objects; assignment only copies the reference value. Two variables can point to the same object and observe its mutations (*aliasing*). Example:

~~~java
List<String> input = new ArrayList<>(List.of("A"));
List<String> alias = input;                 // Same list
List<String> separate = new ArrayList<>(input); // Different list
input.add("B");
// alias sees ["A", "B"]; separate is still ["A"].
~~~

The example above is independent in **list structure** because the `String` elements are immutable. If the list contains mutable objects, `new ArrayList<>(input)` only copies the list, **still sharing each element**.

An object can be described as a graph: a root node references child objects; child objects can continue referencing other objects. **Copy scope** is the set of nodes that must be newly created to ensure the right independence contract, not necessarily the entire reachable graph.

Three common outcomes:

- **Intentional sharing:** both sides use an immutable value or shared resource; no copy needed.
- **Selective copying:** recreate privately owned mutable nodes while sharing immutable values or shared dependencies.
- **Snapshot:** capture state at a point in time; you must specify whether the snapshot fixes only structure or also element states.

A copy can be equal under `equals()` yet differ in identity (`original != copy`). If identity itself carries business meaning (for example an entity managed by an ORM), creating a copy as a new entity on your own may be wrong, even if the data fields match.

## 2. Determine Ownership Before Choosing a Technique

For each field, parameter, and return value, answer:

1. **Who creates it, who manages its lifecycle?** Is the object stored internally, supplied temporarily by the caller, or managed by a framework/external resource?
2. **Who has write permission?** Can the caller mutate it after passing it in? Can the recipient of the return value mutate it?
3. **Which changes must be isolated?** Only adding/removing list elements, or also modifying attributes of each element?
4. **Is the object truly immutable?** Not just `final` fields; all observable state through that object must also be unmodifiable via any exposed reference paths.
5. **Do graph sharing/cycles/identity matter?** Must two paths pointing to the same node still point to the same node in the copy?
6. **Is the cost acceptable?** Large objects, binary data, high load, and concurrent threads may need snapshots, immutable values, or copy-on-write instead of deep copying everything.

### Ownership-Based Decision Matrix

| Data at the boundary | Usually suitable policy | Why |
| --- | --- | --- |
| `String`, `BigInteger`, `LocalDate`, genuine immutable value objects | Share reference | No observable mutation to leak |
| `byte[]`, mutable arrays passed in by caller that the object must own | `array.clone()` or `Arrays.copyOf()` | Separates array storage; if multidimensional, examine inner elements |
| `List<String>` belonging to internal state | `List.copyOf(input)` or equivalent structural copy | Separates list structure; `String` is immutable so elements can be shared |
| `List<MutableItem>` owned by the object | Create a new list **and copy each element** | Copying only the list leaks mutable items |
| Graph of privately owned mutable nodes | Copy constructor/factory with a map of already-copied nodes | Ensures independence, preserves aliases/cycles when contract requires |
| Repository, logger, service, pool, socket, file handle | Keep shared reference per contract or manage lifecycle separately | These are dependencies/resources, not value data to deep-copy arbitrarily |
| JPA/ORM entity, aggregate with business identity | Use DTO/value snapshot or operate via entity-management APIs | Copying an object does not automatically create a valid business entity |
| Intentionally shared cache or state structure | Clearly define write permissions and consistency | Unconditional copying can break sharing semantics |

**Useful rule:** only create copies of **mutable objects that the new boundary must own independently**; immutables can be shared safely. For intentionally shared mutables, the contract must specify which side may mutate and when.

## 3. Three Commonly Confused Levels of Independence

Suppose `Order` contains a `List<Line>`, and each `Line` contains a `Price`:

- **Reference copy:** `Order second = first`. Both variables point to the same object.
- **Shallow copy:** has a new `Order` and a new `List`, yet still references the old `Line`s. Modifying one list (add/remove) does not directly change the other's list structure; mutating a `Line` can appear in both.
- **Deep/ownership copy:** has privately owned `Order`, `List`, and `Line`s; `Price` only needs copying if mutable. If `Price` is an immutable value, sharing still gives the desired independence.

Do not call a solution “deep copy” without specifying **how deep**. A mutable tree, a cyclic graph, and a set of objects holding live resources are three different cases. Correctness is measured by invariants and mutation scenarios, not by the number of `clone()` calls.

Ownership-based copying is usually needed in two directions:

- **Input defensive copy:** constructors/setters receiving mutables from callers create privately owned parts so callers cannot silently mutate internal state afterward.
- **Output defensive copy:** getters/APIs returning mutable data must return a copy/snapshot or appropriate read-only interface so outsiders cannot mutate internally owned state.

Copying only on input while returning mutables directly still leaves a hole. Copying only on output while retaining the input reference does too.

## 4. Process for Choosing Copy Scope

**Step 1 — Write the independence contract.** For example: “After creating `Team` from a member list, the caller can mutate the list, members, and original addresses without altering `Team`. The caller can mutate the returned snapshot without altering `Team`.”

**Step 2 — Sketch the important reference edges.** For example: `Team → List<Member> → Member → Address`. Mark `List`, `Member`, `Address` as mutable; `String` as immutable.

**Step 3 — Mark the owners.** `Team` owns its own list, elements, and addresses. The caller continues to own the objects passed in. Both sides must not hold shared mutable nodes.

**Step 4 — Specify behavior at each boundary.** The `Team` constructor copies the list, each member, and address. The snapshot export method repeats that policy. Internal operations are allowed to mutate objects that `Team` owns.

**Step 5 — Verify in both directions.** Mutate original data then observe the copy; mutate the copy then observe original data. Check both structure and nested elements, because checking only `==` or list size is not enough.

## 5. Standalone Java 17 Example: Copying by Ownership

Save to **`OwnershipCopyDemo.java`**. `Team` independently owns the `List<Member> → Member → Address` tree. String data is shared safely because `String` is immutable. The returned snapshot has an unmodifiable list structure and separated members; **members inside the snapshot are still mutable**, so this snapshot is detached data rather than an immutable value yet.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class OwnershipCopyDemo {
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

    static final class Member {
        private String name;
        private final Address address;

        Member(String name, Address address) {
            this.name = Objects.requireNonNull(name);
            this.address = new Address(Objects.requireNonNull(address));
        }

        Member(Member source) {
            this(Objects.requireNonNull(source).name, source.address);
        }

        String name() {
            return name;
        }

        String city() {
            return address.city();
        }

        void rename(String name) {
            this.name = Objects.requireNonNull(name);
        }

        void move(String city) {
            address.setCity(city);
        }
    }

    static final class Team {
        private final List<Member> members;

        Team(List<Member> suppliedMembers) {
            Objects.requireNonNull(suppliedMembers);
            List<Member> copies = new ArrayList<>(suppliedMembers.size());
            for (Member member : suppliedMembers) {
                copies.add(new Member(Objects.requireNonNull(member)));
            }
            members = List.copyOf(copies);
        }

        List<Member> membersSnapshot() {
            List<Member> copies = new ArrayList<>(members.size());
            for (Member member : members) {
                copies.add(new Member(member));
            }
            return List.copyOf(copies);
        }

        void renameFirst(String newName) {
            members.get(0).rename(newName);
        }

        String describe() {
            Member first = members.get(0);
            return first.name() + "@" + first.city();
        }
    }

    public static void main(String[] args) {
        Address originalAddress = new Address("Ha Noi");
        Member originalMember = new Member("Lan", originalAddress);
        List<Member> supplied = new ArrayList<>();
        supplied.add(originalMember);

        Team team = new Team(supplied);

        originalAddress.setCity("Da Nang");
        originalMember.move("Hue");
        supplied.clear();
        System.out.println("Team after caller changes: " + team.describe());

        List<Member> snapshot = team.membersSnapshot();
        snapshot.get(0).rename("Minh");
        snapshot.get(0).move("Can Tho");
        System.out.println("Team after snapshot changes: " + team.describe());
        System.out.println("Snapshot: "
                + snapshot.get(0).name() + "@" + snapshot.get(0).city());

        try {
            snapshot.add(new Member("Mai", new Address("Hue")));
        } catch (UnsupportedOperationException ex) {
            System.out.println("List structure is unmodifiable");
        }

        team.renameFirst("Hoa");
        System.out.println("Team now: " + team.describe());
        System.out.println("Old snapshot remains: "
                + snapshot.get(0).name() + "@" + snapshot.get(0).city());
    }
}
~~~

Compile and run from the directory containing the file:

~~~bash
javac OwnershipCopyDemo.java
java OwnershipCopyDemo
~~~

Exact stdout:

~~~text
Team after caller changes: Lan@Ha Noi
Team after snapshot changes: Lan@Ha Noi
Snapshot: Minh@Can Tho
List structure is unmodifiable
Team now: Hoa@Ha Noi
Old snapshot remains: Minh@Can Tho
~~~

**Why does the example work?**

1. The constructor `Member(String, Address)` copies `Address`, so mutating `originalAddress` does not affect the member.
2. The constructor `Team(List<Member>)` copies each `Member`, and the `Member(Member)` constructor in turn copies `Address`. Therefore mutating `originalMember` or clearing elements in the input list does not affect `Team`.
3. `List.copyOf(copies)` prevents adding/removing elements through the stored list, but **does not lock Member state**; `Team.renameFirst()` can still change the internal member.
4. `membersSnapshot()` creates copies of all mutable elements before returning. The caller mutating the snapshot does not affect `Team`; `Team` changing later does not affect the old snapshot either.
5. If only `List.copyOf(suppliedMembers)` were written in the constructor, the list structure would be separate yet elements would still be objects owned by the caller — violating the independence requirement.

This example uses a single execution thread. Copy/rename/move operations do not automatically provide thread safety; the concurrency section below shows how to obtain a consistent snapshot.

## 6. Understanding Tools in Java Accurately

### Copy Constructor or Static Factory

For mutable values with clear ownership rules, a copy constructor like `new Member(source)` or a factory like `Member.copyOf(source)` is an easy place to express the copy policy for each field. Implement this explicitly in the data-managing class, validating parameters and invariants so callers do not need to know internal structure. A hand-written copy constructor **is not automatically deep**: if it assigns references of mutable fields, it is still a shallow copy.

### Arrays

- `byte[] result = input.clone();` copies bytes into a new array — enough for independence because `byte` is primitive.
- `Address[] result = input.clone();` only copies the array holding references; each `Address` is still shared.
- `int[][] result = input.clone();` only copies the outer array; the row arrays are still shared. To make two-dimensional data independent, copy each row and specify how `null` rows are handled if permitted.

### Collections

~~~java
List<StringBuilder> source = new ArrayList<>();
source.add(new StringBuilder("A"));

List<StringBuilder> structuralCopy = new ArrayList<>(source);
List<StringBuilder> unmodifiableStructure = List.copyOf(source);

source.get(0).append("B");
// Both structuralCopy.get(0) and unmodifiableStructure.get(0) are "AB".
~~~

- `new ArrayList<>(source)` separates structure, without copying elements.
- `List.copyOf(source)` creates a list **not supporting structural mutation operations**, yet mutable elements can still be modified; this API rejects `null` and may return the same instance if the input is already a suitable unmodifiable list.
- `Collections.unmodifiableList(source)` creates a **view** disallowing edits through the view, yet if `source` changes then the view reflects those changes; it is not a snapshot.
- `Stream.toList()` yields a list not supporting structural mutation operations, yet also does not copy mutable items inside.
- `Map.copyOf()`, `Set.copyOf()` likewise do not automatically deep-copy keys/values/elements. If a mutable key affects `equals()/hashCode()`, mutating the key after inserting it into a map can break lookups.

If you want a truly immutable snapshot, **convert each element into an immutable DTO/value** (for example a record containing only `String`, `int`, `LocalDate`, or genuine immutable values) and then use an immutable list.

### Java Records Do Not Automatically Deep-Copy

A record makes component references `private final` and generates accessors, but does not make referenced objects immutable. The following example **only protects list structure** when elements are `String` (immutable):

~~~java
import java.util.List;
import java.util.Objects;

record Tags(List<String> values) {
    Tags {
        values = List.copyOf(Objects.requireNonNull(values));
    }
}
~~~

This is an illustrative record declaration, not a standalone runnable program with `main`. In a compact canonical constructor, reassigning the `values` parameter causes the validated value to be used for assigning the corresponding field when the constructor finishes. If the component is `List<MutableItem>`, items must be deep-copied or converted to immutable snapshots. For mutable arrays, a record's default accessor even returns the internal array itself; override the accessor to return a copy when protecting state.

### `Object.clone()` Is Not an Automatic Solution

The default `Object.clone()` implementation creates a **shallow** copy at the field level. `Cloneable` is a marker interface; it does not define a public `clone()` for callers. Inheritance, `final` fields, mutable nested state, and invariants make clone rules hard to maintain; classes not supporting cloning can throw `CloneNotSupportedException`. For ownership copies with concrete contracts, explicit constructors/factories are usually easier to read and verify. Do not call `clone()` on resource/ORM objects expecting external systems to be copied too.

## 7. When Not to Deep-Copy

**Immutable data:** `String`, `UUID`, `LocalDate`, `BigDecimal`, and immutable domain values can be shared because mutating an instance is impossible via their APIs. Note that a self-proclaimed “immutable” class is still not immutable if it returns arrays, collection views backed by mutables, or holds accessible mutable children.

**Shared services or resources:** loggers, executors, network connections, open streams, transactions, and repositories have their own lifecycles/access rights. Copying a field reference can be right when both sides intentionally share a dependency; “deep-copying” resources is usually undefined. Do not turn a dependency into part of the data tree to be cloned.

**Entities and business identity:** a copy of an entity with an old ID does not automatically become an independent record in the database. Separate immutable DTOs/snapshots when transferring data across APIs or events; entity mutations should go through lifecycle/transactions per the system contract.

**Intentional mutable sharing:** two components may co-own a cache or state store. In that case dependency is by design; arbitrary copying makes the two sides stop observing the same state. Document the mutation owner, synchronization, lifetime, and consistency level.

### Graphs with Aliases or Cycles

For example `left.child == right.child` before copying. If two separate copies are created along the two paths, the invariant “both edges point to the same node” is lost. For graphs with cycles, naive recursion can even loop infinitely. When the contract requires cloning an entire graph and **preserving topology**, use an identity-based mapping table, such as `IdentityHashMap<OriginalNode, CopiedNode>`: create the copy node, record it in the map **before** recursively copying edges, and reuse the existing copy when encountering the node again. Do not apply this as a universal formula if business semantics want to split distinct logical nodes or preserve references to external resources.

## 8. Snapshots, Performance, and Concurrency

Copying costs time and memory proportional to the amount of newly created data. Choosing the right scope helps avoid cloning the entire graph unnecessarily:

- For large read-only data, prefer immutable values/immutable aggregates and share them.
- For rarely modified but frequently read mutable state, consider **copy-on-write** or replacing an entire immutable snapshot upon updates. Evaluate write cost and memory allocation.
- For data exchanged across APIs, consider a DTO snapshot holding only the fields the caller actually needs; do not serialize/deserialize the entire object graph just to make a copy if a clearer approach exists.
- For large arrays such as `byte[]`, copy at trust/ownership boundaries when needed to prevent caller mutation; if zero-copy is intentionally permitted, document lifetime and write permissions.

**Thread safety is a different requirement from ownership independence.** If thread A mutates `Member` right while thread B copies it, the snapshot may observe data from different points in time (especially with multiple fields). Two copies being independent after creation **does not guarantee** the snapshot was created consistently.

For a consistent snapshot, choose a mechanism adhered to by all participating threads: locking during writes and reads/copies, immutable snapshots published via appropriate synchronization, or a versioning/snapshot protocol with proven consistency. `final` protects against reassigning the field reference, without making nested objects thread-safe. Copying a list while another thread mutates that list without synchronization can also lead to inconsistent results or errors.

## 9. Common Bugs and How to Spot Them

| Bug | Symptom | Fix |
| --- | --- | --- |
| Assigning `this.items = input` when separate ownership is needed | Caller mutates input, internal object changes along | Copy the structure and all mutable elements needing separation |
| Using only `new ArrayList<>(input)` with mutable elements | Mutating item properties from caller affects copy | Copy each item or convert to immutable items |
| Returning mutable arrays/lists directly via getters | Caller mutates result, internal state changes | Output defensive copy or immutable representation |
| Thinking `List.copyOf()` makes all elements immutable | List cannot be appended to, yet items are still mutated | Separate or freeze elements |
| Thinking `Collections.unmodifiableList()` is a snapshot | Backing list mutates and view changes | Copy data before creating view |
| Always deep-copying every field | Costly, wrong semantics for services/resources/identities | Classify by ownership and mutability |
| Recursing clone without handling aliases/cycles | Loses sharing structure or loops infinitely | Identity memoization if graph topology must be preserved |
| Only testing `original != copy` | Root differs while nested state is still shared | Test mutations in both directions and across all mutable layers |
| Copying during concurrent writes without coordination | Snapshot holds mixed-time state | Synchronize writers/readers or use an immutable snapshot protocol |

## 10. Copy Contract Review Checklist

When designing a constructor, factory, or snapshot-returning API, check:

1. **Ownership definition:** After the call, who controls each mutable object in the graph? Is any mutable state intentionally shared?
2. **Input:** If the caller mutates the list, array, individual elements, nested objects, or aliases after the call, does the recipient's state remain correct?
3. **Output:** Can the caller mutate the result and accidentally alter the original object? If only returning a view, is there a clear live-view contract?
4. **Identity & invariants:** Must the copied object have a new identity, keep business identity in a DTO, or preserve aliases/cycles? Do `equals()/hashCode()` remain valid?
5. **Special data:** Are there `null`s, collections containing `null`, generic mutable objects, external resources, caches, JPA entities, or subclasses?
6. **Concurrency:** Are there mutations during copying? Where are snapshot consistency and cross-thread visibility guaranteed?
7. **Cost:** How much data needs copying? Can immutable values be shared or only the parts the caller owns be copied?
8. **Testing:** Mutate after copying in both directions; check nested state, alias paths, lists/arrays, and old snapshots after the original object changes.

### Quick Application Scenarios

**Scenario A:** Constructor receives `List<LocalDate>`, and later the caller may mutate the list. Copying the structure once with `List.copyOf(input)` (if `null` is absent) is enough; no need to copy each `LocalDate`.

**Scenario B:** Constructor receives `List<MutableAddress>` and needs independent data. Create a new list and copy each address; using only `List.copyOf(input)` does not meet the contract.

**Scenario C:** A getter returns `byte[]` used to hold a secret inside the object. Return `data.clone()`; the constructor also copies the caller-supplied array. Otherwise, both sides can directly mutate the same memory.

**Scenario D:** Two objects point to an externally passed `ExecutorService`. Share per the contract and clearly decide which side is responsible for `shutdown()`; do not clone the executor like domain data.

## 11. Self-Check

**Question 1.** After running `List.copyOf(mutableList)`, does mutating a mutable object that was an element of `mutableList` show up in the result?  
**Answer:** Yes. Only the collection structure is blocked from mutation; element objects remain shared unless copied separately.

**Question 2.** Must a copy constructor copy all fields to be “correct”?  
**Answer:** No. Copy the mutable values that the copy must own separately; immutable values and shared dependencies can keep the same references per the contract.

**Question 3.** Are two objects having `equals() == true` and `a != b` proof that a deep copy succeeded?  
**Answer:** No. They may share nested mutable state. Mutations must be tested across every ownership boundary; for graphs, aliases/cycles must also be checked.

**Question 4.** Why can a deep-copied snapshot still be wrong after creation in a multithreaded program?  
**Answer:** Because the reading process for copying can overlap with a writing thread, producing inconsistent data. A synchronization protocol is needed for the **snapshot point in time**, in addition to detaching aliases afterward.

**Closing principle:** Choose copy scope based on **ownership, mutability, and a verifiable independence contract**. Deep-copying everything is often redundant or wrong; default shallow copying is often insufficient. A good design copies just the mutable state needing separation and makes all shared parts explicit.
