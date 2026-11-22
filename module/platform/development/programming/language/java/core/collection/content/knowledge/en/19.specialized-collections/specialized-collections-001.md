# EnumSet: Enum Sets and Compact Representation

An enum defines a finite set of constants, such as the modes READ, WRITE, EXECUTE, DELETE, and SHARE. An object may select no constants, a few constants, or all of them. When you need to hold such a subset, EnumSet is the appropriate specialized structure to consider.

`EnumSet` still has Set semantics: it holds no duplicates and supports membership checks, addition, removal, union, intersection, and difference. What makes it specialized is that all elements belong to the same enum type; the set knows the universe of constants that can appear, so it can represent membership using bits.

This lesson uses Java 17. The goal is to understand the finite-subset model, use the right factories, explain the compactness of the representation without assigning a fixed byte count, and understand the limits regarding data mutation, ordering, and concurrency.

## 1. From an Enum Constant to a Subset

Suppose we have the following illustrative declaration:

~~~java
enum Permission {
    READ, WRITE, EXECUTE, DELETE, SHARE
}
~~~

A `Permission` variable holds one constant from that universe. An `EnumSet<Permission>` holds a subset of the universe: for example, READ and DELETE.

~~~text
available constant universe:
{READ, WRITE, EXECUTE, DELETE, SHARE}

a subset:
{READ, DELETE}

empty set:
{}
~~~

Let the available constant universe be U. If U has 5 constants, the number of distinct subsets is 2^5. There is no need to create another enum for each combination; a single EnumSet can represent any chosen combination over the same universe.

### 1.1. Why Not Use Multiple Booleans?

Five separate booleans can work in a small class, but they do not natively provide union/intersection operations, iteration over enabled options, or a way to pass a set of options across an API.

EnumSet puts those operations into a unified set structure. Constant names convey meaning; the element type lets the compiler prevent adding a constant from another enum into the same set.

This does not mean every boolean must be replaced with an EnumSet. If the data has only a single independent attribute, a boolean remains clear. EnumSet is valuable when multiple constants from the same universe are selected as a subset.

### 1.2. One Enum Type per Set

`EnumSet<Permission>` is not a bag for arbitrary enums. The element universe is fixed when the set is created, even when the set is empty.

Different enum types may have constants with the same name READ, yet they still do not become the same universe. Keeping generics accurate helps avoid mixing them through raw types or unsafe casts.

EnumSet is an abstract class; application code creates instances through factory methods, not `new EnumSet<>()`. You can expose the variable using the Set interface if the API only needs set operations:

~~~java
Set<Permission> enabled =
        EnumSet.of(Permission.READ, Permission.WRITE);
~~~

This is a partial illustrative snippet. The object is still an EnumSet, so its iteration order and characteristics still apply. [Java 17: EnumSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumSet.html)

## 2. Compact Representation via Membership

### 2.1. Each Constant Is a Position

With five constants, we can model it as:

~~~text
position: 4       3       2        1      0
constant: SHARE   DELETE  EXECUTE  WRITE  READ

set {READ, DELETE}:
bit:      0       1       0        0      1
~~~

A bit of 1 means the corresponding constant belongs to the set; a bit of 0 means it does not. The diagram is an explanatory model, not the format printed by EnumSet's toString.

There is no need to allocate a separate node to record each time an already-present constant is added. Membership is simply present or absent, matching Set's no-duplicates semantics.

### 2.2. Set Operations Map to Bitwise Operations

If two sets over the same universe have corresponding bit vectors:

~~~text
A = {READ, DELETE} -> 01001
B = {READ, WRITE}  -> 00011

union A ∪ B:        01011 -> READ, WRITE, DELETE
intersection A ∩ B: 00001 -> READ
difference A \ B:   01000 -> DELETE
~~~

This is why the specialized structure can efficiently handle set operations over the same universe. Applications still call addAll, retainAll, and removeAll; there is no need to write bit masks manually.

The complement must be bounded within the enum universe:

~~~text
5-constant universe: 11111
A:                   01001
U \ A:               10110 -> WRITE, EXECUTE, SHARE
~~~

The complement must not be interpreted as all bits of an integer or all other Java values. The enum universe determines which members are meaningful.

### 2.3. Compact Does Not Mean the Entire Object Is Only a Few Bytes

The API documents that EnumSet uses bit vectors. In OpenJDK 17's factory code, a universe with at most 64 constants selects the RegularEnumSet implementation; a larger universe selects JumboEnumSet. This decision is based on the number of constants in the enum type, not merely the number of currently selected members. [OpenJDK 17: EnumSet.java](https://github.com/openjdk/jdk/blob/jdk-17%2B35/src/java.base/share/classes/java/util/EnumSet.java)

Two points to keep in mind:

- EnumSet is not limited to a maximum of 64 enum constants.
- You should not rely on private implementation class names for business logic or casting.

The bit model shows that a larger universe may require multiple groups of bits to represent. However, total memory also includes the set object itself, type information, and related references; you should not claim that "an entire EnumSet always takes only 8 bytes."

Nor does each set recreate all the enum constant objects. Enum constants are already existing objects of the type; the structure simply represents which constants belong to the set.

Obtaining exact byte counts or timings requires a specific environment and measurement. This lesson does not use printed member names to infer speed or memory footprint.

## 3. Creating Sets by Intent

| Factory | Meaning |
|---|---|
| noneOf(Permission.class) | An empty set that still knows the Permission universe |
| allOf(Permission.class) | All constants of Permission |
| of(READ, WRITE, ...) | Explicitly selected constants |
| range(WRITE, DELETE) | Constants from WRITE to DELETE in declaration order, inclusive of both ends |
| copyOf(enumSet) | A new set with the same type and initial members |
| copyOf(collection) | Infers the universe according to the source Collection contract |
| complementOf(enumSet) | A new set containing the constants of the same universe not in the source |

Factories produce an EnumSet whose membership can be modified. The name `of` does not give it the same immutability as `Set.of`.

### 3.1. An Empty Set Must Know Its Type

Illustrative snippet:

~~~java
EnumSet<Permission> selected =
        EnumSet.noneOf(Permission.class);
~~~

Even though there are no elements to inspect yet, the set already knows the Permission universe. Therefore, you can later add READ, or create its complement containing all of Permission.

There is no zero-argument `EnumSet.of()` form to replace noneOf. Passing the class token is how you specify the universe when no constants are selected yet.

### 3.2. Of Does Not Keep Duplicates or Insertion Order

`EnumSet.of(DELETE, READ, READ)` contains only READ and DELETE. Adding READ again returns false because the set does not change.

This factory differs from `Set.of` in that duplicate arguments are not treated as an immutable-set declaration error. However, you should not pass duplicates to try to record counts or priority levels. If you need counts, the problem is no longer just a Set.

### 3.3. Range Is Inclusive on Both Ends

With the order READ, WRITE, EXECUTE, DELETE, SHARE:

~~~text
range(WRITE, DELETE) -> WRITE, EXECUTE, DELETE
range(READ, READ)    -> READ
~~~

Range follows declaration order, not alphabetical order and not a custom numeric field inside the enum. Passing a start that comes after the end throws IllegalArgumentException.

It creates a set with initial members, not a view that automatically updates with another source set. Do not carry over the view intuition from some ordered structures to EnumSet's range factory.

## 4. CopyOf and Empty Sources

### 4.1. An Empty EnumSet Still Retains Its Universe

CopyOf accepts an EnumSet and can copy it even when the source is empty. The element universe is already part of the set's information.

The Collection case requires careful reading: if the source object is actually an EnumSet, the Collection factory handles it as copying an EnumSet. That still holds when the source variable is declared with type Collection.

Illustrative example:

~~~java
Collection<Permission> source =
        EnumSet.noneOf(Permission.class);

EnumSet<Permission> copy = EnumSet.copyOf(source);
copy.add(Permission.READ);
~~~

You should not conclude solely from the Collection variable type that an empty source will always fail.

### 4.2. A Regular Empty Collection Provides No Universe to Infer

For an empty List that is not an EnumSet, `EnumSet.copyOf(list)` throws IllegalArgumentException. The factory has no elements from which to infer a new universe under its contract.

This is not because "EnumSet does not support empty sets." NoneOf and copying from an empty EnumSet already show that empty sets are completely valid.

If an API knows the type and accepts a Collection that may be empty, it can create noneOf first and then call addAll:

~~~java
EnumSet<Permission> result =
        EnumSet.noneOf(Permission.class);
result.addAll(input);
~~~

This snippet illustrates an existing, non-null input containing only valid elements. It establishes the universe regardless of whether input has any members.

The copyOf(Collection) contract clearly distinguishes an EnumSet source from a regular empty source. [Java 17: copyOf factories](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumSet.html)

### 4.3. Independent Copies of Membership

CopyOf and clone create a new set; later additions or removals on the source set do not automatically change the copy's membership.

The elements are still the corresponding enum constants, not new clones. If an enum is designed with internal mutable state, copying the set does not automatically copy that state.

In typical designs, constant meanings and any associated data should remain stable. A collection structure does not manage the immutability of every object it references.

## 5. Iteration in Declaration Order

EnumSet iterates over its members in the natural order of the enum, meaning the order in which the constants are declared. It is neither insertion order nor alphabetical order.

With Permission in this lesson:

~~~text
of(SHARE, WRITE, READ)
iteration -> READ, WRITE, SHARE
~~~

EnumSet is not a SortedSet and does not accept a custom comparator to change its iteration order. If you need a different display order, build a result list and sort it as needed, rather than assuming renaming constants will give you the desired organization.

Declaration order is also the basis for Enum's compareTo and ordinal. Ordinal starts at 0 and reflects declaration position; the API notes that it is mainly intended for specialized structures like EnumSet and EnumMap. [Java 17: Enum](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Enum.html)

### 5.1. Do Not Use Ordinal as a Persistent Storage Code

If you insert a constant in the middle or change declaration order, positions can shift. Bits stored externally by ordinal could be misinterpreted after a version change.

Applications that need a storage or interchange format must design appropriate stable identifiers. Do not turn EnumSet's internal model into a custom protocol just because it looks compact in one enum version.

Constant names or explicit codes also require a compatibility policy when renaming or adding values; the main point is to decouple external data design from declaration positions in source code.

### 5.2. AllOf and ComplementOf Depend on the Current Universe

When a new constant is added to an enum and the new version runs, allOf includes the new constant. ComplementOf also considers the new universe, not just the list of constants that existed in the old version.

If a set represents allowed capabilities, "all except a few constants" differs from "only the listed constants." Choose the factory based on business policy, not just code brevity.

This is a consequence of the finite-subset model: changing U can change U minus A even when the list A stays the same.

## 6. Set Operations and Mutating the Receiver

Familiar Set operations retain their meaning:

| Method | Semantics |
|---|---|
| add(e) | Adds the member if not already present |
| remove(e) | Removes the member if present |
| contains(e) | Checks for a single member |
| addAll(B) | Turns the receiver set A into A union B |
| retainAll(B) | Turns the receiver set A into A intersection B |
| removeAll(B) | Turns the receiver set A into A minus B |
| containsAll(B) | Asks whether B is a subset of A |
| clear() | Removes all members |

The three bulk-update operations mutate the receiver object itself. If you want to preserve A and B, copy A first and apply the operation to the copy.

Illustrative example:

~~~java
EnumSet<Permission> allowed =
        EnumSet.of(Permission.READ, Permission.DELETE);
EnumSet<Permission> required =
        EnumSet.of(Permission.READ, Permission.WRITE);

EnumSet<Permission> missing = EnumSet.copyOf(required);
missing.removeAll(allowed);
~~~

Missing is WRITE: the requirements not yet in allowed. If you did the reverse `allowed.removeAll(required)`, the result would be the allowed permissions not in required, which answers a different question.

Set difference is not commutative. Clear variable names help readers see which set is being subtracted from.

### 6.1. ContainsAll Asks for Completeness, Not Overlap

If required has READ and WRITE, and allowed has only READ, containsAll returns false. Having one member in common is not enough.

If you want to ask "is there at least one common element?", that is a non-empty intersection question. Do not substitute containsAll for it.

### 6.2. Set Semantics Are Preserved

An EnumSet can equal another Set implementation if they have the same members under the Set contract. Two objects do not need the same class name for the sets to be equal.

Conversely, different print orders do not make two sets have different contents. Do not compare toString strings instead of calling Set's equals. [Java 17: Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html)

## 7. Null, Mutability, and Ownership

### 7.1. Null Elements Are Not Allowed

Adding null to an EnumSet throws NullPointerException. Contains(null) and remove(null) work normally and find no null element.

This helps distinguish "no constant selected" from "adding a null element." To represent no selection, use an empty set.

Likewise, do not assign null to the EnumSet variable itself and expect empty-set operations to still work. A null reference variable and an empty set with a known universe are two different states.

### 7.2. Final Does Not Lock Membership

A final field referencing an EnumSet prevents reassigning the reference, not calling add or remove on that object. If you expose it directly, callers can change its membership whenever they can invoke mutating methods.

If the intent is read-only access, you can return an unmodifiable wrapper. However, a wrapper and a copy must be distinguished.

### 7.3. Read-Only Views and Independent Snapshots

Example:

~~~java
Set<Permission> view = Collections.unmodifiableSet(owner);

Set<Permission> snapshot =
        Collections.unmodifiableSet(EnumSet.copyOf(owner));
~~~

View prevents callers from mutating through the view, yet still reflects membership changes made to owner. Snapshot wraps a copy, so it does not follow subsequent add/remove calls on owner.

You must maintain control over the inner copy object if you want to ensure it is not later mutated through another reference. This is a data-ownership issue, not just a matter of the unmodifiable method name.

The unmodifiableSet wrapper is a read-only view through the wrapper itself; it does not detach from the source. [Java 17: Collections.unmodifiableSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableSet(java.util.Set))

## 8. Iterators and Concurrent Access

EnumSet's iterator is weakly consistent: it does not throw ConcurrentModificationException and may or may not reflect modifications made during iteration according to the class contract.

Do not infer from this that EnumSet is thread-safe. It is not synchronized; if multiple threads access it concurrently and at least one modifies it, appropriate external synchronization is required. [Java 17: EnumSet iterator policy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumSet.html)

Two conclusions to avoid:

- "No exception is thrown, so concurrent updates are safe."
- "The iterator is guaranteed to be a complete, immutable snapshot of any EnumSet."

The example program does not try to predict an exact interleaving of modifications during iteration. It uses iterator.remove to illustrate removing a member cleanly in a single-threaded traversal.

If you need to read a stable set of selections, you can use a copy created while properly guarded. Copying while the source is being modified without coordination does not solve the problem.

## 9. When Should You Choose EnumSet?

EnumSet is a natural candidate when the data is a subset of a specific enum and you need membership or set operations.

It does not replace every Set:

| Requirement | Consideration |
|---|---|
| Set of constants from the same enum | EnumSet is appropriate to consider |
| Codes or names added dynamically at runtime | Not a finite declared enum universe |
| Preserving insertion order | EnumSet iterates in declaration order; use another structure if insertion order matters |
| Sorting by a custom comparator | EnumSet has no custom comparator |
| Storing counts or multiple duplicates | Set does not represent frequencies |
| Shared across multiple threads with updates | Requires concurrency design; do not infer safety from bit representation |

The specialized representation often provides structural and operational advantages. Do not treat "always faster than every Set" as a guarantee for all programs. Overall cost also depends on data, copy frequency, usage patterns, and environment.

An enum with more than 64 constants still works. The program intentionally creates a 65-constant universe and selects only three constants at different positions to refute the misconception that "EnumSet only supports 64 enum elements."

## 10. Complete Java Program

Save the following code to `EnumSetCompactDemo.java`. The enums are placed inside the class so the file can compile directly without creating extra source files.

The program verifies membership semantics, iteration order, set operations, copying empty sources, null handling, mutability, and a large universe. It does not access private JDK fields or measure byte counts.

~~~java
import java.util.Collection;
import java.util.Collections;
import java.util.EnumSet;
import java.util.HashSet;
import java.util.Iterator;
import java.util.List;
import java.util.Set;

public class EnumSetCompactDemo {
    enum Permission {
        READ, WRITE, EXECUTE, DELETE, SHARE
    }

    enum Wide {
        F00, F01, F02, F03, F04, F05, F06, F07, F08, F09,
        F10, F11, F12, F13, F14, F15, F16, F17, F18, F19,
        F20, F21, F22, F23, F24, F25, F26, F27, F28, F29,
        F30, F31, F32, F33, F34, F35, F36, F37, F38, F39,
        F40, F41, F42, F43, F44, F45, F46, F47, F48, F49,
        F50, F51, F52, F53, F54, F55, F56, F57, F58, F59,
        F60, F61, F62, F63, F64
    }

    private static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected enum set result");
        }
    }

    private static <E extends Enum<E>> EnumSet<E> copyKnownType(
            Class<E> type, Collection<E> source) {
        EnumSet<E> result = EnumSet.noneOf(type);
        result.addAll(source);
        return result;
    }

    public static void main(String[] args) {
        EnumSet<Permission> empty = EnumSet.noneOf(Permission.class);
        System.out.println("empty=" + empty);

        EnumSet<Permission> selected =
                EnumSet.of(Permission.DELETE, Permission.READ, Permission.READ);
        boolean duplicateAdded = selected.add(Permission.READ);
        require(selected.size() == 2 && !duplicateAdded);
        System.out.println("selected=" + selected
                + ", duplicateAdded=" + duplicateAdded);
        System.out.println("order=" + EnumSet.of(
                Permission.SHARE, Permission.WRITE, Permission.READ));
        System.out.println("all=" + EnumSet.allOf(Permission.class));
        System.out.println("complement=" + EnumSet.complementOf(selected));

        EnumSet<Permission> range =
                EnumSet.range(Permission.WRITE, Permission.DELETE);
        System.out.println("range=" + range);
        boolean reverseRangeRejected = false;
        try {
            EnumSet.range(Permission.DELETE, Permission.WRITE);
        } catch (IllegalArgumentException exception) {
            reverseRangeRejected = true;
        }
        require(reverseRangeRejected);
        System.out.println("range/reversedRejected=" + reverseRangeRejected);

        EnumSet<Permission> required =
                EnumSet.of(Permission.READ, Permission.WRITE);
        EnumSet<Permission> union = EnumSet.copyOf(selected);
        union.addAll(required);
        EnumSet<Permission> intersection = EnumSet.copyOf(selected);
        intersection.retainAll(required);
        EnumSet<Permission> difference = EnumSet.copyOf(selected);
        difference.removeAll(required);
        require(union.equals(EnumSet.of(
                Permission.READ, Permission.WRITE, Permission.DELETE)));
        require(intersection.equals(EnumSet.of(Permission.READ)));
        require(difference.equals(EnumSet.of(Permission.DELETE)));
        System.out.println("algebra/union=" + union);
        System.out.println("algebra/intersection=" + intersection);
        System.out.println("algebra/difference=" + difference);
        System.out.println("algebra/containsRequired="
                + selected.containsAll(required));

        EnumSet<Permission> copy = EnumSet.copyOf(selected);
        selected.add(Permission.SHARE);
        require(!copy.contains(Permission.SHARE));
        System.out.println("copy/source=" + selected + ", copy=" + copy);

        boolean emptyListRejected = false;
        try {
            EnumSet.copyOf(List.<Permission>of());
        } catch (IllegalArgumentException exception) {
            emptyListRejected = true;
        }
        require(emptyListRejected);
        System.out.println("copy/emptyListRejected=" + emptyListRejected);
        Collection<Permission> emptyEnumSet =
                EnumSet.noneOf(Permission.class);
        EnumSet<Permission> fromEnumSet = EnumSet.copyOf(emptyEnumSet);
        fromEnumSet.add(Permission.READ);
        System.out.println("copy/emptyEnumSetAsCollection=" + fromEnumSet);
        System.out.println("copy/knownTypeEmpty="
                + copyKnownType(Permission.class, List.<Permission>of()));

        boolean nullRejected = false;
        try {
            selected.add(null);
        } catch (NullPointerException exception) {
            nullRejected = true;
        }
        require(nullRejected);
        System.out.println("null/addRejected=" + nullRejected
                + ", contains=" + selected.contains(null)
                + ", remove=" + selected.remove(null));

        EnumSet<Permission> removable = EnumSet.copyOf(range);
        Iterator<Permission> iterator = removable.iterator();
        while (iterator.hasNext()) {
            if (iterator.next() == Permission.EXECUTE) {
                iterator.remove();
            }
        }
        require(removable.equals(EnumSet.of(
                Permission.WRITE, Permission.DELETE)));
        System.out.println("iterator/afterRemove=" + removable);
        System.out.println("equality/hashSet=" + copy.equals(
                new HashSet<>(List.of(Permission.READ, Permission.DELETE))));

        EnumSet<Permission> owner = EnumSet.of(Permission.READ);
        Set<Permission> view = Collections.unmodifiableSet(owner);
        Set<Permission> snapshot =
                Collections.unmodifiableSet(EnumSet.copyOf(owner));
        owner.add(Permission.WRITE);
        System.out.println("ownership/view=" + view + ", snapshot=" + snapshot);
        boolean viewAddRejected = false;
        try {
            view.add(Permission.DELETE);
        } catch (UnsupportedOperationException exception) {
            viewAddRejected = true;
        }
        require(viewAddRejected);
        System.out.println("ownership/addRejected=" + viewAddRejected);

        EnumSet<Wide> wide = EnumSet.of(Wide.F64, Wide.F00, Wide.F63);
        require(wide.size() == 3 && wide.contains(Wide.F64));
        require(EnumSet.allOf(Wide.class).size() == 65);
        require(EnumSet.complementOf(wide).size() == 62);
        System.out.println("wide/members=" + wide + ", size=" + wide.size());
        System.out.println("wide/universe=" + Wide.values().length
                + ", complementSize=" + EnumSet.complementOf(wide).size());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~shell
javac --release 17 -encoding UTF-8 EnumSetCompactDemo.java
java EnumSetCompactDemo
~~~

Stdout from the verification run:

~~~text
empty=[]
selected=[READ, DELETE], duplicateAdded=false
order=[READ, WRITE, SHARE]
all=[READ, WRITE, EXECUTE, DELETE, SHARE]
complement=[WRITE, EXECUTE, SHARE]
range=[WRITE, EXECUTE, DELETE]
range/reversedRejected=true
algebra/union=[READ, WRITE, DELETE]
algebra/intersection=[READ]
algebra/difference=[DELETE]
algebra/containsRequired=false
copy/source=[READ, DELETE, SHARE], copy=[READ, DELETE]
copy/emptyListRejected=true
copy/emptyEnumSetAsCollection=[READ]
copy/knownTypeEmpty=[]
null/addRejected=true, contains=false, remove=false
iterator/afterRemove=[WRITE, DELETE]
equality/hashSet=true
ownership/view=[READ, WRITE], snapshot=[READ]
ownership/addRejected=true
wide/members=[F00, F63, F64], size=3
wide/universe=65, complementSize=62
~~~

The code was compiled with `--release 17` and ran successfully. The release option specifies the compatible API level and bytecode target; it does not assert that the executing JVM is specifically JDK 17.

## 11. Interpreting the Output by Meaning

### 11.1. Membership and Order

Selected contains only READ and DELETE even though READ appears twice in the factory call. Adding READ returns false. The order line prints READ, WRITE, SHARE even though the arguments were passed as SHARE, WRITE, READ.

These results come from set semantics and declaration order, not from sorting by name or insertion history.

### 11.2. Complement, Range, and Operations

Complement contains WRITE, EXECUTE, SHARE because that is the part of the five-constant universe not in the initial selected set. Range from WRITE to DELETE includes both WRITE and DELETE.

Union, intersection, and difference are all computed on copies so the source set is not destroyed before it is used for comparison. ContainsRequired returns false because selected is missing WRITE.

### 11.3. Copying and Empty Sources

SHARE is added to source after copying; copy still has only READ and DELETE. An empty List is rejected by copyOf, whereas an empty EnumSet object declared as a Collection can still be copied.

CopyKnownType takes a class token to handle regular empty sources. It establishes the universe first and only then adds the source members.

### 11.4. Null and Mutability

Adding null is rejected; contains/remove for null both return false. The read-only view reflects owner adding WRITE, while snapshot still contains only READ. Attempting to add through the view is rejected.

There is no contradiction between "the view does not allow modification" and "the view's contents change": the owner modified the source that the view reads through to.

### 11.5. The 65-Constant Universe

Wide has 65 constants; the set selecting F00, F63, F64 has three members and is iterated in declaration order. AllOf has 65 members, and the complement of the three-member set has 62.

This output demonstrates API behavior beyond a 64-constant universe. It does not prove a specific memory size and does not require the application to know which private implementation class is used.

## 12. Common Mistakes

| Mistake | Correct Understanding |
|---|---|
| EnumSet can hold mixed enum types together | Each set has one specific enum universe |
| An empty set is a null reference | NoneOf creates an empty object that knows its universe |
| Of always creates an unmodifiable set | EnumSet.of returns a set whose membership can be modified |
| Adding a duplicate constant creates a duplicate entry | Set only has present/absent membership |
| EnumSet preserves insertion order | It iterates in enum declaration order |
| Range excludes endpoints like a half-open interval | EnumSet.range includes both endpoints |
| CopyOf works on any empty Collection | A regular empty source provides no universe to infer |
| CopyOf on an empty Collection always fails | An object that is actually an EnumSet still retains universe info |
| Complement flips infinitely many bits | Complement stays within the enum universe |
| AddAll or retainAll leaves the receiver set unchanged | They mutate the receiver object |
| Final makes the set immutable | It does not prevent add/remove on the object |
| UnmodifiableSet automatically creates a copy | It is a read-only view; copy first if you need detached membership |
| Not throwing CME means thread-safe concurrency | Iterator policy does not replace synchronization |
| EnumSet is limited to 64 constants | The API supports larger universes |
| Compact means the whole object is always just 8 bytes | Bit representation is not the entire object layout |
| Ordinal is suitable as a default persistent code | It is tied to declaration position and should be decoupled from external protocols |

## 13. Exercises and Solutions

### Exercise 1. Set or List?

You need to hold three enum modes, with no duplicates, and frequently check whether a mode is enabled. Where is EnumSet suitable? What if you need to record how many times a mode occurs?

**Solution:** EnumSet is suitable for a subset of one enum and membership operations. If you need counts, a Set does not store frequency information; you must design an appropriate counting structure.

### Exercise 2. Reading the Order

An enum declares A, B, C, D. Create of(D, B, A) and then add B again. In what order does it iterate, what is its size, and what does adding B return?

**Solution:** A, B, D; size is three; adding B returns false because the set already contains B. Declaration order determines the iteration order.

### Exercise 3. Union, Intersection, Difference

A has READ, DELETE; B has READ, WRITE. Compute A union B, A intersection B, and A minus B. Can you call removeAll on A while keeping A intact for a later task?

**Solution:** Union is READ, WRITE, DELETE; intersection is READ; difference is DELETE. RemoveAll mutates the receiver set itself, so you must copy A first if you want to keep A intact.

### Exercise 4. Copying an Empty Source

A method receives a Collection that may be an empty List or an empty EnumSet. Why does copyOf not produce the same outcome for both objects? If the method knows the type Permission, what is a reliable way to handle it?

**Solution:** EnumSet retains its element universe even when empty; a regular empty Collection provides no element for the factory to infer the universe. You can create noneOf(Permission.class) and then call addAll with the valid source. Having a variable of type Collection does not change the fact that the source object is actually an EnumSet.

### Exercise 5. Keeping Data Read-Only

Owner is an EnumSet containing READ. Create unmodifiableSet(owner), then owner adds WRITE. Does the view see WRITE? What should you do if you need a membership snapshot detached from owner's updates?

**Solution:** The view sees WRITE because it reads through to owner. If you need detached membership, copy owner and wrap the copy, while ensuring no other reference continues to mutate the copy unintentionally.

### Exercise 6. Adding a New Constant

An enum previously had A, B, C; A is selected. In a new version, D is added. How do allOf and complementOf on the set containing only A change? How does that affect the intent "allow all capabilities except A"?

**Solution:** AllOf now has A, B, C, D; the complement now has B, C, D. The new constant is automatically included in results based on the full universe. You must distinguish an explicit allowlist policy from an all-constants-except-some policy.

### Exercise 7. Why Not Use an int Manually?

Someone wants to replace EnumSet with an int and manually assign bits by ordinal for saving to a file. Name two issues besides being able to write AND/OR operations.

**Solution:** You must ensure the right universe and avoid mixing flags from different enums, and you also need a compatible format when constants are added or reordered. Ordinal is a declaration position; it is not automatically a persistent code. An int also has its own bit limit, unlike EnumSet's support for large universes.

### Exercise 8. No Exception During Iteration

A program modifies an EnumSet during iteration and no ConcurrentModificationException is thrown. Is that enough to conclude that multi-threaded updates are correct?

**Solution:** No. EnumSet's iterator does not throw that exception by contract and is only weakly consistent. You need proper concurrency design and state protection; do not use the absence of an exception as proof.

## 14. Self-Check Model

Identify the enum universe, the current membership set, and who has permission to mutate the set. Then choose the factory, set operations, and exposure strategy according to those three facts.

The bit representation explains why EnumSet is a compact specialized structure. The Set API lets applications work with constant names and set semantics, while the limits on ordering, copying, and concurrency still need to be understood to use it correctly.
