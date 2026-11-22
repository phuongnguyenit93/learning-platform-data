# Copy Constructors and Named Copy Methods in Java

## 1. The Problem: Is a New Object Independent of the Original Object?

In Java, reference-type variables hold a **reference to an object**, not the entire object itself. Therefore, assigning `Profile b = a;` only creates another name pointing to object `a`. Mutating state through `b` is also mutating the state visible through `a`.

When you need two objects with equivalent initial data that can evolve independently, you **create a new object** and explicitly define how each component is copied. Two common approaches in Java are:

- **Copy constructor:** `new Profile(existing)`. A constructor takes an object of the same type and initializes the new object's state from it.
- **Named copy method / named copy factory:** `Profile.copyOf(existing)`, `Profile.from(existing)`, or `existing.copy()`. The method name expresses intent, while the implementation decides whether a new object is created and how deep the copy goes.

Java **does not automatically generate a copy constructor** for a class. Unlike some languages, passing an object into a constructor of the same type does not automatically mean “copy”: the class author must define that behavior.

Short example of the difference between **reference assignment** and **creating a copy**:

```java
Profile alias = original;                   // Same object.
Profile copy = new Profile(original);       // New object per the copy contract.
boolean sameObject = alias == original;     // true
boolean copiedObject = copy == original;    // false if constructor creates a new object.
```

The snippet above uses the `Profile` class defined in the full program in section 4.

## 2. How Does a Copy Constructor Work?

Basic pattern:

```java
public final class Point {
    private final int x;
    private final int y;

    public Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    public Point(Point source) {
        this(source.x, source.y);
    }
}
```

- `Point(Point source)` is a **constructor**, with no return type.
- `new Point(source)` always allocates a new `Point` if construction succeeds.
- The line `this(source.x, source.y)` reuses the primary constructor, reducing the risk of missing a field or applying different validation rules.
- `int` is copied by value. For reference fields, what must be decided is **whether to copy the reference, copy the container, or also copy the inner objects**.

A good copy constructor should state its contract clearly: after copying, which changes to the original or the copy can affect the other? That contract matters more than “having a constructor that accepts the same type”.

## 3. Shallow Copy, Deep Copy, and Intentional Sharing

Suppose `Person` holds an `Address` whose `city` can change and a `List<String>` to which elements can be added.

| Approach | Component created anew | Consequence |
| --- | --- | --- |
| `this.address = source.address;` | No new `Address` created | Both `Person`s see address changes: **shallow copy** for this field |
| `this.address = new Address(source.address);` | New `Address` created | Changing `city` on one side does not affect the other |
| `this.tags = source.tags;` | No new list created | Adding/removing elements on one side affects the other's list |
| `this.tags = new ArrayList<>(source.tags);` | New list created, keeps references to elements | Both lists are independent for add/remove; **elements** are not automatically deep-copied |

**Shallow copy** creates a new outer object while still sharing one or more inner references. **Deep copy** goes further to copy the mutable objects that the contract requires to be independent. “Deep” is scoped by the object graph: there is no rule that every reference must always be recreated. `String`, enums, and immutable value types are usually safe to share.

For example, `new ArrayList<>(source.tags)` suffices to separate two `String` lists because strings are immutable. If changed to `List<MutableTask>`, both lists can still contain **the same `MutableTask` instances**. In that case, a new `MutableTask` must be created for each element if independent task mutations are required.

**Independence must be considered in both directions**: mutating the original does not corrupt the copy, and mutating the copy does not corrupt the original. In addition, a constructor receiving external data may need a **defensive copy** right at the start to prevent the caller from retaining and mutating an internal reference.

## 4. Complete Java 17+ Example: Three Ways to Copy, One Independence Contract

Save as **`CopyPatternsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class CopyPatternsDemo {
    static final class Address {
        private String city;

        Address(String city) {
            this.city = Objects.requireNonNull(city, "city");
        }

        Address(Address source) {
            this(Objects.requireNonNull(source, "source").city);
        }

        String city() {
            return city;
        }

        void setCity(String city) {
            this.city = Objects.requireNonNull(city, "city");
        }
    }

    static final class Profile {
        private final String name;
        private final Address address;       // Final reference, Address is still mutable.
        private final List<String> tags;     // Final reference, List is still mutable.

        Profile(String name, Address address, List<String> tags) {
            this.name = Objects.requireNonNull(name, "name");
            this.address = new Address(
                    Objects.requireNonNull(address, "address"));
            this.tags = new ArrayList<>(
                    Objects.requireNonNull(tags, "tags"));
        }

        // (1) Copy constructor: reuses the primary constructor.
        Profile(Profile source) {
            this(Objects.requireNonNull(source, "source").name,
                    source.address,
                    source.tags);
        }

        // (2) Named static factory: clearly expresses intent at the call site.
        static Profile copyOf(Profile source) {
            return new Profile(source);
        }

        // (3) Named instance method: convenient when an object is already held.
        Profile copy() {
            return new Profile(this);
        }

        void moveTo(String city) {
            address.setCity(city);
        }

        void addTag(String tag) {
            tags.add(Objects.requireNonNull(tag, "tag"));
        }

        String describe() {
            return name + " / " + address.city() + " / " + tags;
        }
    }

    public static void main(String[] args) {
        Address inputAddress = new Address("Ha Noi");
        List<String> inputTags = new ArrayList<>(List.of("java"));

        Profile original = new Profile("An", inputAddress, inputTags);
        Profile byConstructor = new Profile(original);
        Profile byFactory = Profile.copyOf(original);
        Profile byMethod = original.copy();

        // Only mutate the original and the inputs still held by the caller.
        original.moveTo("Da Nang");
        original.addTag("oop");
        inputAddress.setCity("Hue");
        inputTags.add("external");

        System.out.println("original: " + original.describe());
        System.out.println("constructor: " + byConstructor.describe());
        System.out.println("factory: " + byFactory.describe());
        System.out.println("method: " + byMethod.describe());
        System.out.println("distinct objects: "
                + (original != byConstructor
                && original != byFactory
                && original != byMethod));
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac CopyPatternsDemo.java
java CopyPatternsDemo
```

Exact output:

```text
original: An / Da Nang / [java, oop]
constructor: An / Ha Noi / [java]
factory: An / Ha Noi / [java]
method: An / Ha Noi / [java]
distinct objects: true
```

Flow explanation:

1. The primary constructor **defensively copies** `Address` and the list from the inputs. Therefore, mutating `inputAddress` or `inputTags` afterward does not change `original`.
2. The copy constructor calls the primary constructor; the address is copied via `new Address(...)`, and the list is created via `new ArrayList<>(...)`. Since the list elements are immutable `String`s, this level of copying suffices for the example.
3. `copyOf` and `copy()` **delegate to a single implementation point**, avoiding three diverging copies of the copy logic.
4. When `original` moves to “Da Nang” and gets the `"oop"` tag added, all three copies still retain the pre-mutation data snapshot.
5. `!=` only proves the outer objects have different references. Independence of **inner fields** is demonstrated by the address and list outputs.

The `final` modifier on `address` and `tags` only prevents **reassigning the field reference**; `Address` and `List` themselves remain mutable. Thus you cannot rely on `final` to skip the defensive copy step.

## 5. Named Copy Methods: When to Use and What to Name Them?

Two common forms:

```java
Profile a = new Profile(original);  // Constructor accepting Profile.
Profile b = Profile.copyOf(original); // Named static factory.
Profile c = original.copy();         // Named instance method.
```

| API | Main advantage | Must be stated clearly in documentation |
| --- | --- | --- |
| `new T(source)` | Easy to find, close to object-creation syntax, forced to create a new `T` object if it succeeds | Is it a deep copy or only field copy? Valid input conditions? |
| `T.copyOf(source)` | Readable intent, can hide construction details, centralizes validation/normalization | **The name does not guarantee** always returning a new object: some immutable APIs may reuse instances |
| `source.copy()` | Natural when operating on an instance; can support type-specific behavior | Returns the same type or a base type? Degree of independence? |
| `T.from(source)` | Useful when converting from another source type or representation | `from` usually leans toward **conversion**, and does not inherently mean deep copy |
| `withX(newValue)` | Expresses a copy with one property changed, fitting immutable value objects | Are unchanged fields shared or not? |

In the example, `Profile.copyOf` **always** calls `new Profile(source)`, so it returns a new object. Do not generalize this rule to every library: for example, a factory for an immutable type may return the input itself under its own contract. If the caller strictly needs a **new object identity** (`result != source`), document it in the API and verify it with tests.

A useful variant when you want to “copy and change one field” is a `withName` method:

```java
// Method added to class Profile in section 4 (not a standalone program).
Profile withName(String newName) {
    return new Profile(newName, address, tags);
}
```

Because the primary constructor already copies `Address` and the list, `withName` still upholds the independence contract in the example. For truly immutable classes, immutable values can usually be shared safely to reduce allocations.

## 6. Designing an Accurate Copy Contract

Before writing a copy constructor or copy method, determine the following points:

**(a) Which fields are values, and which fields are mutable?** Primitives, `String`, enums, and immutable value objects can have their value/reference copied. Mutable objects must be evaluated according to data ownership and the desired degree of independence.

**(b) Are class invariants preserved?** Reuse the constructor or a single internal validation helper so copies satisfy the same conditions: required fields are non-null, collections have valid elements, and data is in a consistent state. A copy constructor should not bypass rules that normal constructors enforce.

**(c) Is child object sharing intentional or accidental?** If two copies are **allowed** to look at the same immutable cache, service, or shared data source, document that as a shared relationship. Do not try to copy file handles, threads, locks, sockets, connections, or external resources just to “deep copy everything”. For resources, separate lifecycle and ownership contracts are needed.

**(d) Is there derived state or internal secrets?** Cache fields derived from primary data should usually be recomputed or intentionally cleared; identity, version, creation timestamp, business IDs, and event-subscription state require explicit decisions on whether to **preserve** or **mint anew**. Mechanically copying every field can break invariants.

**(e) Are there nulls or nested mutable elements?** `Objects.requireNonNull(source, "source")` keeps input failures clear. For nullable fields, define the null case explicitly instead of invoking a copy constructor on null. For `List<MutableItem>`, copy each item if each item needs independence. Graphs with **circular references** or multiple branches pointing to the same object need an identity-tracking mechanism during deep copying to avoid infinite recursion and avoid losing internal sharing relationships.

**(f) Are multiple threads mutating data concurrently?** Copying multiple mutable fields step by step **does not automatically produce an atomic snapshot**. If another thread can mutate the source mid-way, use locks, immutable snapshots, or an appropriate synchronization strategy. A copy constructor does not automatically solve thread safety.

### JavaDoc Suggestion for the Contract

```java
/**
 * Creates a new Profile with the same name, a separate Address,
 * and a separate mutable list of immutable String tags.
 * Later mutations of either Profile do not affect the other.
 *
 * @throws NullPointerException if source is null
 */
Profile(Profile source) {
    this(Objects.requireNonNull(source, "source").name,
            source.address, source.tags);
}
```

This JavaDoc snippet illustrates how to describe a specific **independence scope**; the full constructor appeared in section 4.

## 7. On Inheritance, Records, and `clone()`

**Classes with inheritance:** A copy constructor in a parent class only knows the parent class's slice of state; if you call `new Base(subclassInstance)`, the resulting object is a `Base`, and the subclass-specific part is not preserved. For complex hierarchies, consider a copy method with a polymorphic contract, a protected copy hook, or an immutable/non-inherited design. Avoid calling overridable methods from a constructor because subclass state may not yet be fully initialized.

**Java records:** Records are often a good choice for rarely changing value-like data; records do not automatically deep-copy mutable references. A record holding a `List` still needs a snapshot/defensive copy if stable state is desired. A non-canonical constructor in a record must delegate to the canonical constructor:

```java
record Coordinate(int x, int y) {
    Coordinate(Coordinate source) {
        this(source.x(), source.y());
    }
}
```

For an immutable `Coordinate`, creating a new copy is usually **behaviorally unnecessary**; sharing the same instance is safe if the API does not require distinct identities.

**`Object.clone()`:** The `Cloneable`/`clone()` mechanism carries its own conventions and edge cases, and `Object.clone()`'s default copy is shallow. A copy constructor or named factory usually expresses input validation, invariants, and ownership more clearly. There is no need to use `clone()` just because the problem mentions the word “copy”.

## 8. Common Mistakes and How to Avoid Them

1. **Confusing reference assignment with copying:** `b = a` does not create a new object. Use a constructor or factory with a clearly defined contract.
2. **Copying the outer shell while sharing mutable objects:** `this.address = source.address` couples the two records. Copy `Address` when independence is needed.
3. **Assuming `new ArrayList<>(list)` deep-copies all elements:** this only creates a new list; individual mutable elements may still share references.
4. **Creating two separate copy logics:** one logic in the constructor and another in `copyOf` causes different paths to produce different results. Pick one implementation point and delegate from the other APIs.
5. **Forgetting to update copying when adding a field to the class:** copies lose data or break invariants. Audit all state and tests whenever adding a new field.
6. **Copying an inconsistent source in a multithreaded environment:** the snapshot may contain data from different points in time. Arrange synchronization before copying.
7. **Using `==` to conclude two copies have the same value:** `==` compares object identity; verify values per the contract (accessors, appropriate `equals()`) and verify independence by mutating state.
8. **Naming a method `copyOf` without describing its behavior:** readers may expect a new object or a deep copy. Clearly document whether instances are reused, whether copying is shallow/deep, and how null is handled.

## 9. How to Test Copies

A meaningful test suite must prove both **initial values** and **independence after mutation**, rather than only checking that objects have different references:

- Create a source with at least one nested mutable field and one collection; copy using each exposed API.
- Compare observable data immediately after copying.
- Mutate the mutable field on the source; check that the copy retains its old value.
- Mutate the mutable field on the copy; check that the source does not change.
- Test null, invalid data, and mutable elements inside collections according to the published contract.
- For objects preserving circular references or aliasing across branches, check structural relationships after deep copying, if required by the contract.

**Rule for choosing which style to use:** `new T(existing)` is concise when you need to create a copy of type `T` directly. `T.copyOf(existing)` is readable when you want a named API, control over instantiation, and a unified copy policy. `existing.copy()` is convenient for instance-level operations. Whichever style you choose, what decides correctness is **the contract for what data is copied and what data is shared**, backed by implementation and tests.
