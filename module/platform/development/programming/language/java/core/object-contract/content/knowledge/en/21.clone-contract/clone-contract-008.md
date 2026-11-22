# Distinguishing copying conventions from absolute API guarantees

## 1. The problem: what promises actually exist when calling clone()?

In Java, the `clone()` method is often introduced as a way to create "a copy identical to the original object". That phrasing is convenient to start with, but it easily leads to three overly strong inferences:

- `x.clone() != x` is always true.
- `x.clone().getClass() == x.getClass()` is always true.
- `x.clone().equals(x)` is always true.

These are **expectations or design conventions** mentioned in the `Object.clone()` documentation, rather than **three absolute propositions applying to every `clone()` method a class overrides itself**. The Java documentation describes "general intent" for the first two expectations and remarks that the third is "typically" true; these are not strictly required.

To understand accurately, separate three layers:

1. **Language/API contract of `Object.clone()`**: how the original method behaves when validly called.
2. **Conventions for subclasses implementing `clone()` cleanly**: public/covariant method, calling `super.clone()` when appropriate, returning a meaningful copy, and protecting invariants.
3. **Copying policy of each class**: shallow or deep copy, which fields are shared, which exceptions are declared, and whether the class provides another copying mechanism.

Do not look at the name `clone()` and jump to the conclusion that the returned object is completely independent, all fields are equivalent, the constructor is re-called, or all Java classes support the operation.

## 2. What is defined by the Object.clone() API

Signature of the original method in `java.lang.Object`:

```java
protected native Object clone() throws CloneNotSupportedException;
```

This is an **illustrative API declaration**, not a code snippet to compile standalone. There are three details right from the signature:

- `protected`: a call `someObject.clone()` is usually **inaccessible from external code** unless the class exposes this method publicly. `Cloneable` by itself does not create `public clone()`.
- `Object` is the initial declared return type; a subclass can override and return a more specific type (*covariant return type*), such as `public Employee clone()`.
- `CloneNotSupportedException` is the checked exception declared by `Object.clone()`. An override can handle it internally and omit declaring that exception.

For the **default `Object.clone()`** implementation, according to the documentation:

1. When the runtime class does not implement `Cloneable`, calling the standard `Object.clone()` mechanism throws `CloneNotSupportedException`. **Arrays are a special case**: arrays are considered to support cloning.
2. When cloning succeeds, the original mechanism creates a new object of **the same runtime class** as the original object.
3. The new object's fields are initialized from the values of the corresponding fields of the source object, **like field-by-field assignment**.
4. The contents of objects referenced by those fields **are not automatically cloned further**: this is a *shallow copy*.
5. Creating an object via `Object.clone()` does not follow the class's regular constructor call path like `new`.

The points above describe **the behavior of the original mechanism** when invoked and returning successfully. A class can provide **its own `clone()` override**, in which Java does not automatically insert a `super.clone()` call, does not automatically verify each design expectation, and does not automatically add deep copying.

### Understanding Cloneable accurately

`java.lang.Cloneable` is a **marker interface**, meaning it declares no methods at all. It is the signal checked by `Object.clone()` to decide whether original copying is permitted.

```java
final class MarkerOnly implements Cloneable {
    private final int id = 1;
}
```

*This is an illustrative class definition.* Class `MarkerOnly` has `Cloneable`, yet external caller code **cannot automatically call** `new MarkerOnly().clone()`, because the `clone()` method inherited from `Object` remains `protected`. To expose a clone API, the class must proactively declare a `public` override or another copy method.

Conversely, a `clone()` override that constructs an object itself via a constructor **without using `super.clone()`** can run without needing the `Cloneable` marker. Therefore, one should not say `implements Cloneable` is a mandatory condition for *every method named clone* to run; it is the condition checked by the default `Object.clone()` mechanism (excluding arrays).

## 3. Three common expectations: convention or guarantee?

| Statement | With successful original Object.clone() | With arbitrary clone() override | Accurate phrasing |
| --- | --- | --- | --- |
| `copy != original` | A new object is created, so true | Override can return `this` | General intent of clone, **not an absolute guarantee** of every override. |
| `copy.getClass() == original.getClass()` | True because the new object has the same runtime class | Override can return an object of another class if the return type allows | Natural expectation, yet **not enforced** for every override. |
| `copy.equals(original)` | Not necessarily: `Object.equals()` defaults to identity | Depends on `equals()` rules and clone decisions | Usually expected for value objects, **not a mandatory condition**. |
| Copy's fields are completely independent | No: only shallow copy | Depends on whether override copies shallowly/deeply | Must read the class's copying policy. |
| Calls class constructor | Not via `Object.clone()`'s normal constructor path | Override using `new` can call constructor | Do not generalize across strategies. |
| Always supports external calls | No: original method is `protected` | Can override `public` | Check the API signature of the class in use. |

### Expectation 1: are the two objects different?

With code using `super.clone()` properly, there is normally a new object so `copy != source`. However, a class can define:

```java
@Override
public SomeType clone() {
    return this; // Violates independent copy intent, but is valid override code.
}
```

*This snippet only illustrates an override inside class `SomeType`.* The JVM does not enforce calling `super.clone()` inside an overriding method. This is usually a **poor clone design** because callers may expect a separate object; yet it illustrates why the "distinct reference" convention must not be treated as an absolute guarantee of any API named `clone()`.

### Expectation 2: does it preserve the runtime class?

Original `Object.clone()` creates a copy of the exact runtime class. But an override declaring return type `Object` can return any object:

```java
@Override
public Object clone() {
    return new Object(); // Does not preserve runtime class of this.
}
```

*This is an illustrative override inside a class; not a design to use in applications.* Java checks return types according to method signatures and override rules, without automatically requiring `result.getClass() == this.getClass()` for all overrides.

An override with a more specific return type, such as `public Employee clone()`, narrows possible return types at compile time, yet if `Employee` permits inheritance, the returned object can still be a different subtype. Thus you must understand the class semantics clearly rather than taking a method named `clone` as proof.

### Expectation 3: does the clone equal the original according to equals()?

Even when using `super.clone()` and receiving an object with a different reference and **identical fields**, `clone.equals(original)` can still be `false` if the class does not override `equals()`, because `Object.equals()` defaults to comparing identity.

For a value object implementing `equals()` based on value fields, copying while preserving values usually leads to `equals() == true`. But that is a consequence of **the class's equality definition**, not a property imposed automatically by the name `clone()`.

You must check the reverse direction as well: `copy.equals(original)` and `original.equals(copy)` must obey the symmetry contract of `equals()` if the class defines equality. A clone cannot rescue an `equals()` design that already lacks consistency.

## 4. Shallow copy: copying fields rather than automatically copying the whole object graph

A successful `Object.clone()` works similarly to copying each field's value:

- For `int`, `boolean`, `double`...: primitive values are copied.
- For reference fields like `String`, `Address`, `List`: **references** are copied. Two objects can point to the same child object.
- If a field is declared `final` and holds a `List` or mutable object, `final` only prevents reassigning the field, **not** making the pointed-to object immutable.

Diagram:

```text
Before clone:
source -------> Employee A ------address------> Address X

After super.clone():
source -------> Employee A ------address------┐
                                             ├--> Address X
shallow ------> Employee B ------address------┘

After copy method additionally copies Address:
source -------> Employee A ------address------> Address X
isolated -----> Employee C ------address------> Address Y
```

When `Address X.city` is changed through `shallow.address`, `source.address.city` also changes because they share one `Address`. `isolated` has its own `Address Y` and is unaffected by that change.

A true **deep copy** needs to define which child objects must be copied, whether some immutable references are shared, how circular relationships are handled, and how resources like files/sockets/locks are handled. Java has no standard `Object.deepClone()` that solves all of these automatically.

## 5. Runnable Java 17+ example: illustrating both original mechanism and unusual overrides

Create file `CloneGuaranteeDemo.java`:

```java
public class CloneGuaranteeDemo {

    static final class Address {
        String city;

        Address(String city) {
            this.city = city;
        }
    }

    static final class Employee implements Cloneable {
        private final String name;
        private final Address address;

        Employee(String name, Address address) {
            this.name = name;
            this.address = address;
        }

        @Override
        public Employee clone() {
            try {
                return (Employee) super.clone();
            } catch (CloneNotSupportedException ex) {
                // Employee implements Cloneable, so exception is not expected.
                throw new AssertionError(ex);
            }
        }

        Employee copyWithIndependentAddress() {
            return new Employee(name, new Address(address.city));
        }
    }

    static final class NotCloneable {
        @Override
        public NotCloneable clone() throws CloneNotSupportedException {
            return (NotCloneable) super.clone();
        }
    }

    static final class ReturnsSelf implements Cloneable {
        @Override
        public ReturnsSelf clone() {
            return this; // Intentionally violates clone convention; for illustration only.
        }
    }

    static final class ReturnsOtherType implements Cloneable {
        @Override
        public Object clone() {
            return new Object(); // Intentionally violates same-runtime-class expectation.
        }
    }

    public static void main(String[] args) {
        Employee original = new Employee("An", new Address("Hà Nội"));
        Employee shallow = original.clone();
        Employee isolated = original.copyWithIndependentAddress();

        System.out.println(original != shallow);
        System.out.println(original.getClass() == shallow.getClass());
        System.out.println(original.equals(shallow));
        System.out.println(original.address == shallow.address);
        System.out.println(original.address == isolated.address);

        shallow.address.city = "Huế";
        System.out.println(original.address.city);
        System.out.println(isolated.address.city);

        try {
            new NotCloneable().clone();
        } catch (CloneNotSupportedException ex) {
            System.out.println("CloneNotSupportedException");
        }

        ReturnsSelf self = new ReturnsSelf();
        System.out.println(self.clone() == self);

        ReturnsOtherType odd = new ReturnsOtherType();
        System.out.println(odd.clone().getClass() == odd.getClass());

        int[][] matrix = {{1, 2}};
        int[][] arrayCopy = matrix.clone();
        System.out.println(matrix != arrayCopy);
        System.out.println(matrix[0] == arrayCopy[0]);
    }
}
```

Compile and run from the directory containing the file using JDK 17 or later:

```bash
javac CloneGuaranteeDemo.java
java CloneGuaranteeDemo
```

Exact stdout:

```text
true
true
false
true
false
Huế
Hà Nội
CloneNotSupportedException
true
false
true
true
```

Explanation:

1. `Employee` implements `Cloneable`, exposes `public clone()`, and calls `super.clone()`. The `shallow` copy has a different reference yet keeps the same runtime class.
2. `Employee` does not override `equals()`. Although the shallow copy preserves initial field values, `original.equals(shallow)` remains `false` under default identity equality.
3. `original.address == shallow.address` is `true`; only the `address` reference was copied. Conversely, `copyWithIndependentAddress()` creates a new `Address`, so reference comparison returns `false`.
4. After changing `shallow.address.city` to `"Huế"`, the original also sees `"Huế"` due to sharing the child object; `isolated` stays `"Hà Nội"`.
5. `NotCloneable` tries calling `super.clone()` without implementing `Cloneable`: the original method throws `CloneNotSupportedException`. The class can still declare a `public` override; the marker affects **the original mechanism**, not whether the method name/signature exists.
6. `ReturnsSelf` has an override returning `this`; checking `self.clone() == self` prints `true`. This is a syntactically valid method, yet **does not fulfill the intent of creating a new copy**.
7. `ReturnsOtherType` overrides `clone()` to return `new Object()`; checking same runtime class prints `false`. Thus "clone always keeps the right class" is also not imposed on arbitrary overrides.
8. A two-dimensional array `int[][]` still has public clone via the array mechanism. `matrix != arrayCopy` is `true`, yet `matrix[0] == arrayCopy[0]` is also `true`: new outer array, sub-arrays remain shared.

The two classes `ReturnsSelf` and `ReturnsOtherType` only serve to demonstrate API boundaries. **Do not implement clone in these two styles in regular application code**: they break expectations callers easily rely on.

## 6. What makes a good clone() implementation convention?

A class actively supporting clone should have an understandable and verifiable policy. Common choices:

1. **Clear public API:** if external users need to call clone, provide `public clone()` with a specific return type, rather than passively relying on `protected Object.clone()`.
2. **Call super.clone when using the standard mechanism:** an override of a `Cloneable` class usually starts with `super.clone()` to obtain a shallow copy of the exact runtime class. This is especially important with inheritance; you cannot always safely replace it with `new Base(...)` because the actual object may be a subclass.
3. **Copy mutable components per policy:** share only immutable objects (such as `String`) or resources designed for sharing; copy additionally when independence is required.
4. **Preserve invariants:** determine whether mutable `final` fields, caches, locks, file handles, threads, and runtime resources can be copied. A field-by-field copy does not automatically possess safe semantics.
5. **Check postconditions:** for a class with a clone contract, you can verify `copy != source`, compatible runtime class, data that must stay intact, child objects that must be independent, and fields allowed to be shared.
6. **Document copy depth explicitly:** "shallow", "deep for Address", "shares cache", or "clone not supported" saves callers from guessing.

An implementation template in a simple `final` class:

```java
final class Point implements Cloneable {
    private final int x;
    private final int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    @Override
    public Point clone() {
        try {
            return (Point) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}
```

*This is an illustrative class definition, not a program with `main`.* `Point` only holds two primitive fields, so a shallow copy already suffices for independence regarding those values. However, the class **has not overridden `equals()`**, so even though both have identical `x/y`, `clone.equals(original)` remains `false`. If the domain wants value equality, define compatible `equals()/hashCode()` or consider using an immutable `record Point(int x, int y)`.

### Does every class need to implement Cloneable?

No. Some classes should not allow copying: open connections, lock-managing objects, components holding uniquely owned resources, objects coordinating special lifecycles. Some classes want copying without using `Cloneable` because this historical API has limitations around access permissions, checked exceptions, invariants, and shallow copying. A copy constructor or factory usually describes the policy more clearly:

```java
Employee duplicate = original.copyWithIndependentAddress();
```

In the case of the section 5 example, this method proactively creates a new `Address`, clearly informing callers of the copy's independence scope. However, this **is not a general deep clone**: if `Employee` gains another mutable object graph, handling it must be defined separately.

## 7. Array.clone() is an API exception worth knowing

Java array types are objects. Arrays are treated as implementing `Cloneable` and supporting a public `clone()` method; an expression like:

```java
int[] values = {1, 2, 3};
int[] copy = values.clone();

System.out.println(values == copy); // false
System.out.println(java.util.Arrays.equals(values, copy)); // true
```

*The snippet above shows illustrative statements inside a method.* Primitive elements are copied by value, so modifying `copy[0]` does not alter `values[0]`.

For arrays containing references such as `StringBuilder[]` or `Address[]`, only **the outer array** is a new object; elements in the array still point to the old objects:

```java
StringBuilder[] a = {new StringBuilder("A")};
StringBuilder[] b = a.clone();

System.out.println(a != b);       // true
System.out.println(a[0] == b[0]); // true
```

Two-dimensional arrays are also arrays of arrays; `matrix.clone()` does not automatically copy each row. If a copy without shared sub-arrays is needed, you must clone each row or convert using an appropriate data structure. **Do not jump from "arrays have clone" to concluding "array clone is always deep".**

## 8. Copy constructors, factory methods, and immutable objects

In new code, sometimes `clone()` is unnecessary:

| Need | Approach | Note |
| --- | --- | --- |
| Copy a small value object | Copy constructor or `static copyOf(...)` | Copying policy is clearly stated inside the constructor/factory. |
| Immutable object | Can usually keep the same object; create a new copy when wanting to change values | Avoids unnecessary copying; depends on API contract. |
| Object with mutable reference fields | Copy method proactively copies fields needing separation | Must protect invariants and avoid unwanted sharing. |
| Existing class with documented `public clone()` | Call according to the class's policy | Check specific shallow/deep behavior and exceptions. |
| Complex graphs, resources, or circular relationships | Domain-specific copying | Default clone cannot infer ownership or lifecycle. |

A copy constructor has the advantage of expressing **clearly which constructor is called and which fields are recreated**. However, with an open hierarchy, a superclass constructor does not automatically create a copy of the right subtype without a dedicated mechanism; conversely, `super.clone()` creates an object of the same runtime class yet risks copying state too mechanically. There is no single solution that works well for every kind of object.

An immutable class can choose to return `this` from a method named `copy()` if the method's contract explicitly states so. However, if the API promises "creates an object with a different reference", returning `this` fails to meet the requirement. Therefore **the language describing a method's contract matters more than its name itself**.

## 9. Common mistakes when inferring guarantees from clone()

### Mistake 1: implements Cloneable means having public clone()

`Cloneable` declares no methods. The class still has to expose a `public clone()` if external code needs to call it; original `Object.clone()` is `protected`.

### Mistake 2: clone always returns a new object with a different reference

`super.clone()` succeeding creates a new object, yet an override can return `this`. The `Object.clone()` documentation calls this a general intent, **not an absolute requirement on every override**.

### Mistake 3: clone always has the same class and equals the original per equals()

Same runtime class is a property of original `Object.clone()` when successful; an override can return a different type. `equals()` is usually identity equality if the class does not override it, so a distinct-reference copy will be `false` even when fields have identical values.

### Mistake 4: clone automatically calls the constructor and re-runs validation

`Object.clone()` copies state at the field level, without going through the regular constructor. If invariants depend on fresh initialization, the copy may be invalid. An override constructing via `new` has different semantics, so one cannot state generally that every `clone()` skips constructors.

### Mistake 5: clone is always a deep copy

No. `Object.clone()` only shallow-copies. `final List<Address>` or `final Address` can still share mutable contents. To achieve independence, relevant levels must be copied according to the class's policy.

### Mistake 6: clone is guaranteed to throw CloneNotSupportedException if not implementing Cloneable

True when calling the original `Object.clone()` mechanism on an unsupported object, except for the special case of arrays. However, an override constructing an object via a constructor can work without using the marker. You must distinguish the original mechanism from a method provided by the class itself.

### Mistake 7: no need to test because clone just copies the object

A complex object can contain mutable structures, caches, circular references, locks, or resources that cannot be shared unconditionally. Test the exact copying policy—for example, whether modifying one copy affects the other on fields disallowed from sharing.

## 10. Verifying postconditions against a specific policy

For a class with `clone()`, clearly define what conditions constitute a "correct copy" and evaluate each condition separately:

| Question / condition to check | Appropriate check |
| --- | --- |
| Is an object with a different reference needed? | `copy != original`. |
| Is the same runtime class needed? | `copy.getClass() == original.getClass()`. |
| Is logical equality needed at the moment of copying? | `copy.equals(original)` and check `equals/hashCode` contract. |
| Are primitive fields preserved? | Compare each value defined in the contract. |
| Which reference fields are allowed to be shared? | Check `copy.ref == original.ref` when appropriate. |
| Which reference fields must be independent? | Check distinct references and test mutating the copy. |
| Are constructors/invariants guaranteed? | Inspect how the method actually builds the object. |
| Can it return an exception or invalid value? | Read the signature and class documentation; test rejection conditions. |

A single check `copy != original` does not prove contents were copied properly. Similarly, `copy.equals(original)` being `true` also does not prove the two copies have independent child objects: they may hold the same mutable `List` and mutate together later. Each criterion is part of **the class's copying contract**, not an automatic consequence of the name `clone()`.

If a class uses inheritance, test with an actual subclass instance. A superclass override calling `super.clone()` can produce the right runtime class while the subclass's new fields are shallow-copied unexpectedly; in some designs, an additional override is needed to copy those components properly.

## 11. Self-check

**Question 1.** Does `Cloneable` define a public `clone()` method?  
**Answer:** No. It is a marker interface; the inherited `Object.clone()` method remains `protected` unless the class exposes it.

**Question 2.** Does `x.clone() != x` hold for every `clone()` override?  
**Answer:** No. That is the general intent, yet an override can return `this` itself. When original `Object.clone()` succeeds, a new object is created.

**Question 3.** Is `clone.getClass() == original.getClass()` an absolute guarantee of every method named `clone`?  
**Answer:** No. Original `Object.clone()` creates a copy of the same runtime class, yet a custom override can return another type if the signature allows.

**Question 4.** `Employee` does not override `equals()`; if `super.clone()` returns an object with a different reference but identical fields, what is `clone.equals(original)`?  
**Answer:** `false` because `Object.equals()` defaults to comparing identity.

**Question 5.** Does a `private final Address address` field cause `super.clone()` to create a new `Address`?  
**Answer:** No. `final` does not make mutable contents of `Address` immutable; shallow clone shares the same reference.

**Question 6.** Can a class that does not implement `Cloneable` yet writes `public X clone() { return new X(...); }` run?  
**Answer:** Yes, when the method constructs the object itself and does not call original `Object.clone()`. This is a custom clone policy; it should be clearly documented.

**Question 7.** Does cloning a two-dimensional array automatically clone every row?  
**Answer:** No. `int[][]` is an array containing `int[]`; `clone()` creates a new outer array, while row arrays remain shared.

**Question 8.** Is checking a clone with `equals() == true` sufficient to guarantee deep copy?  
**Answer:** Not yet. Equality can hold even when the original and the copy share mutable objects; the independence policy of each component must be tested.

**Question 9.** Why can a copy constructor be easier to understand than `Object.clone()` for objects holding resources?  
**Answer:** A constructor/factory allows explicitly specifying which child objects or resources to recreate, share, or forbid copying, instead of copying every field automatically.

**Question 10.** If an API only says "supports clone", what should be checked before relying on it?  
**Answer:** Access permissions and return type, potential exceptions, whether the method calls the original mechanism or constructs the object itself, shallow/deep level, mutable state sharing policy, and the postconditions the class actually commits to.

**Remember:** Original `Object.clone()` has deterministic behavior when called successfully: creating a new object of the same runtime class and shallow-copying fields. However, statements like "every clone has a different reference", "every clone has the same class", and "every clone equals the original" are **conventions/expectations**, not enforced guarantees for every override. A trustworthy copying API must publish its actual policy, preserve invariants, and be tested according to the class's needs.