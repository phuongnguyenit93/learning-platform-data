# Two Independent Objects Can Represent the Same Value

In Java, **object identity** and **the value an object represents** are two different concepts. Two independently created objects can contain the same data and carry the same meaning in the problem domain, yet remain two separate objects. Therefore, the questions “are they the same object?” and “do they represent the same value?” must be answered by two different checks.

## 1. Distinguishing Identity, Reference, and Value

- An **object** is an entity created at runtime. Each time a `new` expression succeeds in creating a new object, that object has its own identity.
- A **reference** is the value held by a reference-type variable to point to an object. Two variables can hold references to **the same object**; those are two names (aliases) for the same entity.
- **State** is the data inside an object. Two different objects can have identical state.
- **Equality by value** depends on the definition of the data type: for coordinates, it might be the same `x, y`; for money, it might be the same amount and currency unit. In Java, the `equals(Object)` method typically expresses that definition, **if the data type has implemented it appropriately**.

| Check | Meaning for Object References |
| --- | --- |
| `a == b` | Do the two references point to **the exact same object**? |
| `a.equals(b)` | According to the `equals` implementation of `a`'s type, are the two objects considered equal? |
| `Objects.equals(a, b)` | Safely checks equality when one or both references may be `null`; if both are non-`null`, uses `a.equals(b)`. |

**Boundary to remember:** for primitive types such as `int`, the `==` operator compares values; the identity interpretation in the table above applies to **references to objects**. Do not confuse a reference or the result of `==` with a memory address that can be directly observed or managed.

## 2. Experiment: Same Value, Different Objects

File **`IdentityAndValueDemo.java`**, runnable on Java 17+:

~~~java
import java.util.Objects;

public class IdentityAndValueDemo {
    record Point(int x, int y) {}

    static final class Label {
        private final String text;

        Label(String text) {
            this.text = text;
        }
    }

    public static void main(String[] args) {
        Point first = new Point(2, 3);
        Point second = new Point(2, 3);
        Point alias = first;

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(first == alias);
        System.out.println(first.hashCode() == second.hashCode());

        Label left = new Label("Java");
        Label right = new Label("Java");
        System.out.println(left == right);
        System.out.println(left.equals(right));
        System.out.println(Objects.equals(left.text, right.text));
    }
}
~~~

Compile and run:

~~~bash
javac IdentityAndValueDemo.java
java IdentityAndValueDemo
~~~

Standard output:

~~~text
false
true
true
true
false
false
true
~~~

Step-by-step explanation:

1. `first` and `second` come from **two `new Point(...)` calls**, so `first == second` is `false`, even though both contain the coordinates `(2, 3)`.
2. `Point` is a **record**. With components `int x, int y`, the automatically generated `equals` method compares the component values; the result is `true`. A record also generates `hashCode` consistent with `equals`, so two equal values must have equal hash codes.
3. `alias = first` copies the **reference**; it does not create a third object. Thus `first == alias` is `true`.
4. `Label` is a regular class that **does not override `equals`**. It inherits `Object.equals`, which compares identity. Therefore two independent `Label`s still return `false` from `equals`, even though the two `text` fields have equal content.
5. `Objects.equals(left.text, right.text)` uses `String.equals` semantics: two strings with the same content are equal. This **does not turn** the two `Label` objects into one.

Key lesson: **having the same data does not automatically make two instances equal according to `equals`**. The outcome depends on the type's contract. And **`equals` returning `true` does not make two instances the same object**.

## 3. Why Does Default `Object.equals` Not Express “Same Value”?

Every class inherits from `java.lang.Object`. Without an override, `Object.equals` performs a check equivalent to `this == obj`. Therefore:

- A class can have two independent instances whose fields are all identical, yet default `equals` still returns `false`.
- `String`, wrapper classes such as `Integer`, many library classes such as `List`, and records each define `equals` by value/content as appropriate for their type.
- A class defining an **entity** may also intentionally keep identity semantics, or define equality by a business identifier. There is no universal rule that “comparing all fields is always right” for every data domain.

For example, two `Customer` records with the same name are not necessarily the same customer; conversely, two `Money(100, "VND")` objects can reasonably be considered the same value. You must clearly decide which fields constitute **meaningful value** before implementing `equals`.

## 4. Creating a Custom Value Object: `equals` Goes with `hashCode`

When you want two independent objects with the same data to be considered equal, you can override `equals` and `hashCode` yourself. Here is an example of a value object using only two immutable components, `amount` and `currency`.

File **`MoneyDemo.java`**, runnable on Java 17+:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class MoneyDemo {
    static final class Money {
        private final long amount;
        private final String currency;

        Money(long amount, String currency) {
            this.amount = amount;
            this.currency = Objects.requireNonNull(currency);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof Money that)) {
                return false;
            }
            return amount == that.amount && currency.equals(that.currency);
        }

        @Override
        public int hashCode() {
            return Objects.hash(amount, currency);
        }
    }

    public static void main(String[] args) {
        Money first = new Money(100, "VND");
        Money second = new Money(100, "VND");
        Money third = new Money(200, "VND");

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(first.equals(third));
        System.out.println(first.hashCode() == second.hashCode());

        Set<Money> values = new HashSet<>();
        values.add(first);
        values.add(second);
        values.add(third);
        System.out.println(values.size());
    }
}
~~~

Compile and run:

~~~bash
javac MoneyDemo.java
java MoneyDemo
~~~

Standard output:

~~~text
false
true
false
true
2
~~~

Here, `first` and `second` are two different objects that both represent “100 VND”, so `equals` is `true`. `third` represents “200 VND”, so it is not equal to the other two. `HashSet` keeps only **two distinct values** according to the `equals` and `hashCode` contract.

To read the implementation:

- `this == other` returns early when both references point to the same instance.
- `instanceof Money that` confirms the right-hand object is of the expected type and introduces the variable `that` (Java 17 pattern matching).
- Comparing `amount` and `currency` is the **value decision**: the same amount with different currencies is not equal.
- `hashCode` is computed from **the exact same fields used in `equals`**; if two objects are equal, their hash codes must be equal.

The example intentionally uses a `final` class and `private final` fields so the value cannot change after creation. This keeps `equals` more stable when the object is placed in hash-based data structures. In a real project, you also need to clarify `currency` normalization, the unit of `amount`, and business rules; Java does not decide these for the programmer.

## 5. The `equals` and `hashCode` Contract

When overriding `equals`, Java requires adhering to the following properties (assuming state involved in the comparison does not change during the checks):

| Property | Requirement |
| --- | --- |
| Reflexive | `x.equals(x)` is `true` for `x != null`. |
| Symmetric | `x.equals(y)` and `y.equals(x)` must give the same result. |
| Transitive | If `x.equals(y)` and `y.equals(z)` are `true`, then `x.equals(z)` must be `true`. |
| Consistent | When the relevant data has not changed, repeated calls to `x.equals(y)` must give the same result. |
| Non-nullity | `x.equals(null)` must be `false` for `x != null`. |

Key hash rule: **if `x.equals(y) == true`, then `x.hashCode() == y.hashCode()`**. The converse is **not true**: two unequal objects can still have the same hash code (a hash collision). `hashCode` is not a unique identifier. Likewise, `System.identityHashCode(obj)` is an identity-based hash code, is **not guaranteed unique**, and is not a memory address.

If you override `equals` while omitting `hashCode`, a `HashSet` may retain two elements that should be considered duplicates; a `HashMap` may fail to find a key with an equal value. When writing a class representing a value, test both methods and the data structures that consume them.

## 6. Easily Confused Cases

### `String`: Value Is Content, Not Same Reference

~~~java
String a = new String("java");
String b = new String("java");
System.out.println(a == b);      // false
System.out.println(a.equals(b)); // true
~~~

The two `new` expressions intentionally create two different objects; `String.equals` compares character sequences. In everyday code there is no need to explicitly create `new String(...)` like this. Two literals can point to the same string thanks to the **string pool**, so `==` is sometimes `true`; that is not a reason to use `==` to check string content.

### Arrays: Default `equals` Does Not Compare Element by Element

~~~java
int[] a = {1, 2};
int[] b = {1, 2};
System.out.println(a == b);                // false
System.out.println(a.equals(b));           // false
System.out.println(java.util.Arrays.equals(a, b)); // true
~~~

Arrays do not override `Object.equals` to compare content. For one-dimensional primitive arrays, use `Arrays.equals` when you want to compare elements; for nested arrays, consider `Arrays.deepEquals`. A record with an array-typed field also **does not automatically compare array contents** in its generated `equals`: the array field still has reference-comparison semantics unless you design a different comparison yourself.

### “Same Value” Is Each Type's Convention

`new java.math.BigDecimal("1.0")` and `new java.math.BigDecimal("1.00")` have equivalent numerical value according to `compareTo(...) == 0`, yet `BigDecimal.equals` returns `false` because it also considers **scale**. Do not assume that “looks the same”, “numerically equivalent”, and “equal by `equals`” are always the same thing.

### The Same Object Can Change State

If `alias = original` and then a method mutating state is called on `alias`, `original` also observes the change, because both reference the same instance. `original == alias` remains `true`. Conversely, two objects that are equal by value can **cease to be equal** after one object has a field participating in `equals` modified.

In particular, avoid modifying fields that affect `equals`/`hashCode` on an object **currently acting as a key in a `HashMap` or an element in a `HashSet`**. If the hash code changes after insertion, lookup/contains/removal operations can produce unexpected results. Prefer immutable value objects.

## 7. How to Apply This When Programming

1. Identify the actual question: do you need to know **same instance**, or **same value according to business semantics**?
2. When you need identity/reference (for example, verifying two variables point to one object), use `==`.
3. When you need equality by content/value, use `equals` according to the type's contract; when references may be `null`, consider `Objects.equals(a, b)`.
4. When creating your own value object, determine which fields participate in equality, override **both `equals` and `hashCode`**, and test equal, unequal, `null`, and `HashSet`/`HashMap` usage scenarios.
5. When appropriate for the data model, consider a **record** to get value semantics for its components out of the box; still understand the limitations with mutable components, especially arrays.
6. Avoid relying solely on `hashCode`, `identityHashCode`, guessed addresses, or `toString` output to conclude that two objects “are one” or “are equal”.

**Self-check:** Given `Point p = new Point(2, 3);` and `Point q = new Point(2, 3);`, why is `p == q` `false` while `p.equals(q)` is `true`? If you write `Point r = p;`, how does the result of `p == r` change? If you replace `Point` with a class that does not override `equals`, what will the value comparison return?

**Remember:** *Two objects can have different identities yet be equal by value. Identity is reflected by references and the `==` operator; value equality must rely on the data type's `equals` contract, along with a consistent `hashCode` when using hash-based collections.*