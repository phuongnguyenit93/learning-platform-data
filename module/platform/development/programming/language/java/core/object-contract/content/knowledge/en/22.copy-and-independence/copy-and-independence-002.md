# Fields Pointing to Immutable Objects Can Be Safely Shared

## 1. Meaning in Object Copying

When creating a copy of a Java object, “independence” usually means **changing the state of the original does not change the observable state of the copy, and vice versa**. This does not require every reference field to point to a new object.

If a field points to an **immutable** object, the original and the copy can hold **the same reference**: neither side can modify the state of the shared object. Copying the reference in this case is both semantically accurate and avoids creating unnecessary objects.

For example, two profiles pointing to the same `String` representing a name or pointing to the same `LocalDate` representing a join date. If the mutable parts of one profile are modified separately, the other profile remains independent.

Distinguish between:

- **Reference copy:** `copy.name = original.name`; both fields point to the same object.
- **State copy:** creating a new object containing equivalent data; usually needed when the data is mutable.
- **State independence:** two objects do not accidentally share *mutable* state. Two copies do not necessarily need to differ in identity across every child object.

## 2. When Is Reference Sharing Safe?

An object suitable for sharing must have observable state that does not change after creation, including through any child objects it references. There must be no public access path that modifies that state.

In Java, typical examples include:

- `String`: the string content does not change; string concatenation produces a new result.
- `LocalDate`, `LocalDateTime`, `Instant`: methods such as `plusDays` return a new value instead of mutating the existing object.
- `BigInteger` and `BigDecimal`: operations return a new result object.
- `UUID`: the identifier value does not change after creation.

**Rule:** if a field has a type and *actual value* that are truly immutable, a copy constructor, copy factory, or `copy` method can assign the exact same reference.

~~~java
this.name = source.name;                 // Immutable String: safe to share
this.joinedDate = source.joinedDate;     // Immutable LocalDate: safe to share
~~~

The two lines above are an **illustrative snippet inside a copy constructor**, not a standalone Java program.

Reference diagram:

~~~text
original.name ---------+
                       +----> String "An" (immutable)
copy.name -------------+

original.skills -----------> List A (mutable)
copy.skills ---------------> List B (mutable)
~~~

In the diagram, sharing the `String` object is safe; the two `List`s are separated so that modifying list A does not affect list B.

## 3. Java 17 Example: Sharing Immutable, Copying Mutable

The following example uses a copy constructor. Two immutable fields (`String` and `LocalDate`) are shared. The skill list is mutable, so each `Profile` owns its own `ArrayList`. The constructor also makes a defensive copy of the input list so the caller does not retain implicit permission to mutate internal state.

Create the file `SafeImmutableSharingDemo.java`:

~~~java
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class SafeImmutableSharingDemo {
    static final class Profile {
        private final String name;
        private final LocalDate joinedDate;
        private final List<String> skills;

        Profile(String name, LocalDate joinedDate, List<String> skills) {
            this.name = Objects.requireNonNull(name);
            this.joinedDate = Objects.requireNonNull(joinedDate);
            this.skills = new ArrayList<>(Objects.requireNonNull(skills));
        }

        Profile(Profile source) {
            Objects.requireNonNull(source);
            this.name = source.name;             // Share immutable String
            this.joinedDate = source.joinedDate; // Share immutable LocalDate
            this.skills = new ArrayList<>(source.skills); // Separate mutable List
        }

        void addSkill(String skill) {
            skills.add(Objects.requireNonNull(skill));
        }

        List<String> getSkills() {
            return List.copyOf(skills); // Return an unmodifiable snapshot
        }
    }

    public static void main(String[] args) {
        Profile original = new Profile(
                "An",
                LocalDate.of(2026, 10, 23),
                List.of("Java", "SQL")
        );
        Profile copy = new Profile(original);

        System.out.println("Cùng name: " + (original.name == copy.name));
        System.out.println("Cùng joinedDate: "
                + (original.joinedDate == copy.joinedDate));
        System.out.println("skills độc lập: "
                + (original.skills != copy.skills));

        original.addSkill("Spring");

        System.out.println("Original skills: " + original.getSkills());
        System.out.println("Copy skills: " + copy.getSkills());
    }
}
~~~

Compile and run with JDK 17 or higher:

~~~bash
javac SafeImmutableSharingDemo.java
java SafeImmutableSharingDemo
~~~

Expected output:

~~~text
Cùng name: true
Cùng joinedDate: true
skills độc lập: true
Original skills: [Java, SQL, Spring]
Copy skills: [Java, SQL]
~~~

**Output explanation:**

1. `original.name == copy.name` is `true` because the copy constructor assigns the same `String` reference. Immutability ensures sharing causes no mutation leaks.
2. `original.joinedDate == copy.joinedDate` is also `true` because both hold the same `LocalDate` reference; calling `plusDays` on this date yields another date object.
3. `original.skills != copy.skills` is `true` because `new ArrayList<>(source.skills)` creates a **new list**.
4. Adding `"Spring"` to the original's list does not change the copy.
5. `getSkills()` returns a snapshot that disallows direct modification of the internal list. Since the elements here are immutable `String`s, no mutable state is shared through the elements.

**Key point:** `private final List<String> skills` only prevents reassigning the `skills` field after initialization; the `ArrayList` itself can still be modified via `addSkill`. It is creating a separate list that ensures the two `Profile`s do not mutate the same list.

## 4. Counterexample: Accidentally Sharing Mutable State

If the copy constructor is written as:

~~~java
this.skills = source.skills; // WRONG if this List is mutable
~~~

then both `Profile`s point to **the same list**. Adding/removing elements through one will appear in the other. This is a *shallow copy* causing aliasing bugs when two independent profiles are required.

How to fix it depends on the data contract:

- The list is allowed to mutate within each `Profile`: use `new ArrayList<>(source.skills)` as in the main example.
- The list must be immutable from initialization and the elements are also immutable: `List.copyOf(source.skills)` can be used to obtain an unmodifiable snapshot and share that snapshot across copies.
- The list contains mutable objects: copy each mutable element appropriately; merely creating a new `ArrayList` still leaves both lists pointing to **the same elements**.

Example of the last point: with `List<Address>` where `Address` has a setter, the expression `new ArrayList<>(originalAddresses)` creates a new list but does *not* create new `Address` instances. If address details also need independence, copy each `Address`. This is a mechanism description, not a standalone program snippet.

## 5. Do Not Confuse “Unmodifiable Through This Variable” with “Immutable”

| Field/value | Can it be shared when copying? | Reason/how to handle |
| --- | --- | --- |
| `String`, `LocalDate`, `Instant` | Yes | Immutable objects. |
| `BigDecimal`, `BigInteger` | Yes | Operations create new values. |
| Mutable `int[]`, `byte[]` | No, if an independent copy is needed | Mutable arrays; use `clone()` or `Arrays.copyOf(...)`. |
| Mutable `ArrayList<String>` | No | Create a new list; `String` elements can be shared. |
| `List.copyOf(values)` with immutable elements | Yes, if there is no hidden state-mutation path | Unmodifiable snapshot list; nested values are also immutable. |
| `Collections.unmodifiableList(backing)` | Not necessarily | This is a read-only view; anyone holding `backing` can still mutate the data and the view reflects those changes. |
| `List<MutableAddress>` | No, if element independence is also needed | Create a new list and copies of the mutable elements. |
| `Date`, `StringBuilder` | No | These are mutable classes; consider copying or switching to immutable types. |

Some common traps:

### 5.1. `final` Does Not Make an Object Immutable

~~~java
final int[] scores = {10, 20};
scores[0] = 99; // Valid: only the array contents change
~~~

`final` only prevents `scores` from pointing to another array. Even if the enclosing class is also declared `final`, the array remains mutable.

### 5.2. `record` Only Guarantees Component Fields Cannot Be Reassigned

~~~java
record Report(int[] totals) {}

int[] data = {1, 2};
Report report = new Report(data);
data[0] = 99; // report.totals()[0] is now 99
~~~

`record` auto-generates the constructor/accessor but does not automatically deep-copy arrays or collections. To make a record state-immutable, defensive copying is needed in the constructor and accessor for mutable components.

### 5.3. “Unmodifiable” Is Not Enough If Elements Are Mutable

`List.copyOf` creates a collection that cannot have elements added, removed, or replaced through that interface. However, it **does not automatically deep-copy** the element objects. If the list contains a mutable `Address` object and an external reference to `Address` still exists, changes to the address will still show up when reading from the list.

### 5.4. Immutable Values Are Shared; Changing a Field Is a Different Matter

For a reassignable (`non-final`) field, `copy.name = "Tên mới"` only changes the **reference in the copy**, without modifying the old `String` object or changing `original.name`. Distinguish *reassigning a reference* from *mutating the state of the referenced object*.

### 5.5. Sharing Across Threads Requires Considering Object Publication

Immutability eliminates contention over *mutating the state of the immutable object itself*. However, when passing an enclosing object between threads, you must still ensure proper initialization and object publication under Java Memory Model rules; other mutable fields still need appropriate synchronization strategies. Do not infer that an entire object graph is automatically thread-safe merely from a `String` or `LocalDate` field.

## 6. How to Decide When Writing a Copy Constructor

For each reference field, check in order:

1. **Is it mutable?** Consider the concrete object, nested elements, and existing aliases, not just the declared type or `final` modifier.
2. **How much independence does the copy contract require?** If state independence is required, immutables can be shared. If the API requires every component to have a distinct identity, that identity condition must be obeyed.
3. **If definitely immutable:** assign the same reference; no need to pointlessly create an equivalent object.
4. **If mutable:** create an appropriate copy (array, collection, or each child object). For object graphs with reference cycles or multiple aliases, design deep copying carefully to preserve the intended structure.
5. **Block covert mutation paths:** defensively copy in constructors/getters when needed; do not let an external alias continue mutating data assumed to be immutable.

Quick example: a `Person` contains `String fullName`, `LocalDate birthDate`, `int[] scores`, and `List<Address> addresses`, where `Address` is mutable. To copy with state independence:

- Reuse the `fullName` and `birthDate` references.
- Use `scores.clone()` to create a new array.
- Create a new `addresses` list **and** copy the `Address` objects; copying only the list is not enough.

**Takeaway:** *State independence does not mean creating every object anew.* Share objects that are **truly immutable**, and copy every part of **mutable** state that the copy contract requires to be independent.
