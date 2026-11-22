# Why Is `List<Integer>` Not a `List<Number>`? Choosing the Right Solution

**`Integer extends Number` does not imply `List<Integer> extends List<Number>`.** Java Generics are *invariant* with respect to concrete type arguments: a `List<Integer>` cannot automatically be used as a `List<Number>`, even though each individual Integer can still be used as a Number.

This lesson answers the question **"when I have a `List<Integer>` and an API wants to handle Number, what do I actually need to do?"** by distinguishing three outcomes: *reading data only*, *writing into a data destination*, and *owning an actual List<Number>*. Each need requires a different signature; instead of writing casts, we adjust **the API design or the storage structure**.

## 1. Which Assignments Are Valid and Which Are Not?

Consider:

~~~java
Integer n = 7;
Number number = n; // Valid: Integer is a subtype of Number.

List<Integer> ids = List.of(10, 20);

// List<Number> direct = ids; // COMPILE ERROR.
List<? extends Number> view = ids; // Valid.
~~~

When seeing the error `incompatible types: List<Integer> cannot be converted to List<Number>`, separate two questions:

1. **Can the elements be used as Number?** Yes. Integer is a subtype of Number.
2. **Can the entire list uphold every guarantee of List<Number>?** No. List<Number> allows `add(3.5)`, whereas List<Integer> cannot accept a Double.

If a List<Number> variable were allowed to reference a List<Integer>, other code could insert a Double into a list where the caller expected only Integer values. Java rejects **the unsafe assignment at compile time**, preserving the relationship between the element type written in and the type `get` promises to return.

This prohibition does not depend on whether the list is currently empty or already populated. A `List<Integer>` may be immutable, yet *invariance* and *immutability* remain two independent concepts.

## 2. Before Fixing the Error, Identify the Real Goal

| Actual need | Right choice | Creates a new list? |
| --- | --- | --- |
| Only compute/read as Number | `Collection<? extends Number>` or `List<? extends Number>` | No |
| Only iterate elements without indices | `Iterable<? extends Number>` | No |
| Put Integer values into a caller-owned destination | `Collection<? super Integer>` | Not required |
| Have a new list capable of holding both Integer and Double | `List<Number> copy = new ArrayList<>(ids)` | Yes |
| Only want to count elements of any List | `List<?>` | No |
| Need consistent read-write of an exact caller-defined type | `List<T>` in a generic method | Not required |
| An API *genuinely* requires a list with type argument Number | Create/maintain a `List<Number>` | Depends on the API |

The two options most easily confused are **a read-only view `List<? extends Number>`** and **an actual `List<Number>`**. A view does not convert or copy objects. A copy creates a new collection, to which other Number types can be added without modifying the original Integer list.

## 3. Case A — Method Only Needs to Read Number

A method computing a sum does not need to know whether the list holds Integer, Double, or Long:

~~~java
static double average(Collection<? extends Number> source) {
    double total = 0;
    int count = 0;

    for (Number value : source) {
        total += value.doubleValue();
        count++;
    }

    return count == 0 ? 0 : total / count;
}
~~~

`? extends Number` means **an unknown concrete type argument**, which is guaranteed to be within the Number family. When iterating, each value can be used as Number.

Many source types are valid:

~~~java
average(List.of(10, 20));   // Can accept List<Integer>.
average(List.of(1.5, 2.5)); // Can accept List<Double>.
~~~

The signature `Collection<? extends Number>` is more general than `List<? extends Number>` if the method does not need `get(index)`, because it works with more collection implementations. When only iteration is needed, `Iterable<? extends Number>` is even broader; choose the lowest abstraction that supports the algorithm's operations.

### Why Not Use `List<Number>` for a Read-Only Method?

~~~java
static double sumTooStrict(List<Number> values) {
    double total = 0;
    for (Number n : values) {
        total += n.doubleValue();
    }
    return total;
}

// List<Integer> ids = List.of(10, 20);
// sumTooStrict(ids); // ERROR: the method requires List<Number>.
~~~

This is an **overly strict contract** for the actual task: the method does not call `add`, yet requires a list that, by its type, **could** accept any Number. Fix the method signature if you own that API, rather than copying values just to work around invariance.

### The Upper Bound Still Does Not Allow Adding Arbitrary Numbers

~~~java
List<Integer> ids = new ArrayList<>(List.of(10, 20));
List<? extends Number> readable = ids;

Number first = readable.get(0); // Valid.
// readable.add(30);             // COMPILE ERROR.
// readable.add(2.5);            // COMPILE ERROR.
~~~

The compiler does not know whether the exact type argument represented by `?` is Integer, Double, or Number. Therefore, an arbitrary Number or Integer **is not guaranteed to be writable** into that list. `add(null)` may be valid at the type level, though it still depends on the implementation's mutability and null policy.

## 4. Case B — Method Needs to Put Integer into a Broader Destination

This is the opposite direction:

~~~java
static void appendIds(
        Collection<? super Integer> destination,
        Collection<Integer> ids) {

    for (Integer id : ids) {
        destination.add(id);
    }
}
~~~

`? super Integer` allows the destination to have type argument Integer, Number, or Object. An Integer can be inserted into any of those three lists while still preserving the contract.

~~~java
List<Integer> ids = List.of(10, 20);
List<Object> audit = new ArrayList<>();

appendIds(audit, ids);
System.out.println(audit); // [10, 20]
~~~

However, when reading through a `Collection<? super Integer>`/`List<? super Integer>` variable, elements are only guaranteed as Object. A `List<Object>` destination could certainly contain String or other objects added by other components.

**PECS** (*Producer Extends, Consumer Super*) is the mnemonic for this one-way design: a producer supplying data uses an upper wildcard, and a consumer receiving data uses a lower wildcard. It is not a mandate to put wildcards on every parameter.

When needing to copy **any compatible type T** from source to destination, libraries commonly write a generic method:

~~~java
static <T> void appendAll(
        Collection<? extends T> source,
        Collection<? super T> destination) {

    for (T item : source) {
        destination.add(item);
    }
}
~~~

At a call site, the compiler infers T so that the source provides T values and the destination accepts T. With a List<Integer> source and a List<Number> destination, the operation is safe and does not require turning List<Integer> into List<Number>.

## 5. Case C — Needing to Create an Actual `List<Number>`

When you genuinely **need to own** a list that allows storing different Number types, create a new collection:

~~~java
List<Integer> ids = List.of(10, 20);

List<Number> report = new ArrayList<>(ids);
report.add(2.5); // Valid: the destination list has type argument Number.

System.out.println(report); // [10, 20, 2.5]
System.out.println(ids);    // [10, 20]
~~~

The constructor `ArrayList(Collection<? extends E>)` accepts elements from a source whose type is compatible with E. In this example, the left-hand context determines E as Number, so the constructor can copy Integer values into List<Number>.

**This is not a type cast.** It creates a new list object; the two lists do not share add/remove/set structure. If the elements are mutable objects, ArrayList's copy is still a **shallow copy** at the element-reference level. With Integer (immutable), we do not face element contents changing through aliases, but you should not generalize that this copy performs a deep copy of every object.

If you need an initially empty collection to hold different numeric types:

~~~java
List<Number> numbers = new ArrayList<>();
numbers.add(1);
numbers.add(2.5);
~~~

This expresses the intent to **own a mixed Number list** more clearly than using a raw cast to "upgrade" an existing List<Integer>.

### When to Change the Signature, and When to Copy?

- **You control a read-only method**: replacing `List<Number>` with `List<? extends Number>` is usually optimal and performs no copy.
- **You control a method that only accepts Integer**: accept `List<? super Integer>` when compatible with the operations.
- **You do not control an API that strictly requires `List<Number>`**: create your own `List<Number>` to adapt to the API.
- **You need to keep and mutate two independent collections**: copying is an **ownership** decision, not merely a compiler-error fix.
- **You genuinely need bidirectional element exchange**: use an appropriate named type parameter T; two independent wildcards do not promise matching element types.

## 6. A Subtle Type Inference Detail: Target Typing

The following two expressions must be distinguished:

~~~java
List<Integer> ids = List.of(1, 2);

// List<Number> wrong = ids; // Error: the variable ids already has type List<Integer>.

List<Number> directFactory = List.of(1, 2); // Valid.
~~~

Why is the last line valid? The generic factory call `List.of` can be inferred by the compiler using the left-hand **target type**, choosing E=Number; the supplied Integer values are all compatible with Number. That **does not suddenly turn an existing `List<Integer>` into `List<Number>`**.

Note that `List.of` returns an **unmodifiable** list. Writing `List<Number> directFactory = List.of(1, 2)` does not mean calling `directFactory.add(2.5)` will succeed. That is a runtime mutability issue, completely distinct from generic *invariance*.

If you need a modifiable `List<Number>` from an Integer source, `new ArrayList<>(ids)` is the clearer choice.

## 7. Complete Java 17 Program: Three Approaches

Save as **NumberListMigrationDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class NumberListMigrationDemo {
    static double average(Collection<? extends Number> source) {
        double total = 0;
        int count = 0;

        for (Number value : source) {
            total += value.doubleValue();
            count++;
        }
        return count == 0 ? 0 : total / count;
    }

    static void appendIds(
            Collection<? super Integer> destination,
            Collection<Integer> ids) {
        for (Integer id : ids) {
            destination.add(id);
        }
    }

    static List<Number> copyAsNumbers(
            Collection<? extends Number> source) {
        List<Number> answer = new ArrayList<>();
        answer.addAll(source);
        return answer;
    }

    public static void main(String[] args) {
        List<Integer> ids = List.of(10, 20);

        System.out.println("average=" + average(ids));

        List<Number> report = copyAsNumbers(ids);
        report.add(2.5);
        System.out.println("report=" + report);
        System.out.println("original=" + ids);

        List<Object> audit = new ArrayList<>();
        appendIds(audit, ids);
        System.out.println("audit=" + audit);

        List<Number> targetTyped = List.of(1, 2);
        System.out.println("targetTyped=" + targetTyped);
    }
}
~~~

Run:

~~~bash
javac --release 17 -Xlint:all NumberListMigrationDemo.java
java NumberListMigrationDemo
~~~

**Verified stdout:**

~~~text
average=15.0
report=[10, 20, 2.5]
original=[10, 20]
audit=[10, 20]
targetTyped=[1, 2]
~~~

Explanation:
- `average(ids)` accepts List<Integer> without copying thanks to the read-only wildcard.
- `copyAsNumbers(ids)` builds a new List<Number>; adding a Double modifies only the new list.
- `appendIds(audit, ids)` writes Integer into List<Object> thanks to the lower bound.
- `targetTyped` demonstrates that the `List.of` factory can use target typing to produce an expression of type List<Number>; it is still a list that does not support add/set.

### A Mathematical Caveat

`average` converts Number to `double`, so it may lose precision for very large integers or financial requirements. **Compatibility of type bounds does not guarantee numerical precision**. When handling currency, you should normally model the domain and arithmetic with BigDecimal or an appropriate type.

The method returns 0 for an empty collection by **illustrative convention**. A production API might throw an exception or return OptionalDouble instead of that convention; this is independent of invariance.

## 8. Testing Compile Errors Before Fixing the API

The following cases are written to **inspect errors**, not to be placed inside the runnable program:

~~~java
List<Integer> ids = List.of(10, 20);

// List<Number> a = ids;          // Invalid: invariant List<E>.
// List<Object> b = ids;          // Invalid: invariant List<E>.

List<? extends Number> readable = ids;
// readable.add(30);             // Invalid: unknown captured subtype.

List<? super Integer> writable = new ArrayList<Number>();
writable.add(30);                 // Valid.
// Integer x = writable.get(0);   // Invalid: reading only guarantees Object.

List<Number> independent = new ArrayList<>(ids);
independent.add(3.5);             // Valid: separate Number list.
~~~

**Do not fix with a raw/unchecked cast** like `(List<Number>) (List<?>) ids`. A cast does not change the element type the collection actually promises, and can allow adding a Double to a list that other code reads as Integer. A proper solution must preserve the type relationship at compile time or create a new collection with an appropriate type argument.

## 9. Final Decision Table

| Issue you are facing | Solution |
| --- | --- |
| `sum(List<Number>)` does not accept `List<Integer>` | Change the API to `List<? extends Number>` if it only reads. |
| Want to store Integer into `List<Number>` or `List<Object>` | Accept `List<? super Integer>` if the method only writes Integer. |
| Need to mix Integer, Double, Long in one list | Construct/copy into an actual `List<Number>`. |
| Want to count `List<String>` and `List<Integer>` | Use `List<?>`; no need for `List<Object>`. |
| Want to transfer collections flexibly between producer and consumer | Method `<T>` + `? extends T`/`? super T`. |
| Signature is right but calling `add` throws UnsupportedOperationException | Check mutability; replace `List.of` with a mutable list if needed. |
| `List<Number> x = List.of(1,2)` compiles | Factory target typing, not covariance. |
| `List<Number> x = existingListOfInteger` does not compile | Invariance: two parameterized types were already fixed differently. |

## 10. Self-Check

**Question 1.** Why is `Number value = Integer.valueOf(10)` valid while `List<Number> values = ids` (where ids is List<Integer>) is invalid?

**Answer:** Assigning to Number accepts an Integer object as a normal subtype; whereas List<Number> also grants the ability to add any Number, which List<Integer> cannot fulfill.

**Question 2.** If you only compute the average from List<Double> and List<Integer>, should you use `List<Number>` or `List<? extends Number>`?

**Answer:** `List<? extends Number>` (or Collection<? extends Number>) because the method only reads Number-compatible values.

**Question 3.** How do you create a modifiable list that accepts both Integer and Double from an existing List<Integer>?

**Answer:** `List<Number> copy = new ArrayList<>(ints);` and then add Double to copy. This is a different list object, not a type cast.

**Question 4.** Why can `List<Number> x = List.of(1,2)` compile?

**Answer:** The generic factory method receives target typing from the left-hand side and infers Number; this is not assigning an already-typed List<Integer> variable to List<Number>.

**Question 5.** Does a generic source bounded by extends Number allow adding an Integer directly?

**Answer:** No. The actual subtype of the wildcard is unknown and could be Double; only null is an exception at the type-system level, while mutability is a separate issue.

**Question 6.** Why do we use `? super Integer` to allow both List<Number> and List<Object> to receive Integer?

**Answer:** Both Number and Object are supertypes of Integer, so both kinds of collections accept writing Integer.

**Question 7.** Should you use `List<Number> forced = (List<Number>) (List<?>) ids` to eliminate the compiler error?

**Answer:** No. That bypasses generic type checking without changing the data structure; it can cause heap pollution and ClassCastException in code that reads as Integer.

**Takeaway:** the issue is not "finding cast syntax to turn List<Integer> into List<Number>," but **identifying which capabilities the method actually needs**. To read data as Number use an upper bounded wildcard, to write Integer use a lower bounded wildcard, and to own a mixed-numeric list **create a separate List<Number>**.