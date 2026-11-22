# Distinguishing Two Objects Using the `==` and `!=` Operators in Java

When working with classes and objects, the question "are two variables equal?" has **two very different meanings**: do they both point to **the same object**, or are they two objects containing the **same data**? In Java, the `==` and `!=` operators apply to **references** to check the first meaning: **reference identity**. To compare content or business values, you usually need to use `equals()` or a comparison designed appropriately for the data type.

This lesson belongs to Java Core — *class-object*, in the **References** group. The examples run on **Java 17 or later**, clearly distinguishing logic errors, compilation errors, `null` cases, `String`, arrays, wrappers, and custom classes that define `equals()`.

## 1. References and Objects Are Not the Same Thing

Consider this code:

~~~java
Account first = new Account("A-01");
Account second = first;
~~~

This is an **illustrative snippet**; assume the `Account` class has a constructor accepting a `String`. Here:

- `new Account("A-01")` creates an **object** of type `Account`.
- `first` is a **reference variable** holding a reference to that object.
- `second = first` **copies the reference value** from the `first` variable to the `second` variable.
- **There is no second `new`**, so the two variables point to **the same object**.

Diagram:

~~~text
first  -----+
            +----> Account object #1
second -----+        number = "A-01"
~~~

A reference variable can also hold `null`, meaning it **points to no object**. Conversely, two variables can point to two **different** objects whose fields have the same values.

**Key takeaway:** counting **the number of variables** is not the same as counting **the number of objects**. To understand `==`, you must determine **which object** a reference points to, rather than looking only at the data inside the object.

## 2. How Do `==` and `!=` Compare References?

For two **reference-type** operands that are compatible for comparison, Java uses:

| Expression | When is the result `true`? | Meaning |
| --- | --- | --- |
| `a == b` | `a` and `b` point to **the same object**, or **both are null** | Reference identity |
| `a != b` | `a` and `b` do not hold the same reference value | Negation of `==` |
| `a == null` | `a` does not point to any object | Null reference check |
| `a != null` | `a` points to an object | Non-null check |

The two expressions `a == b` and `a != b` **do not execute** the `equals()` method. Nor do they **automatically inspect the fields** of the object. These are built-in language operators, not methods that can be overridden on a class.

For the same pair of valid references, `a != b` has the opposite logical value to `a == b`. For example, if `a == b` is `true`, then `a != b` is `false`.

### When Are Two References Considered the Same Object?

A practical way to think about it:

~~~text
If a --------> Object #1
   b --------> Object #1
=> a == b is true

If a --------> Object #1
   b --------> Object #2
=> a == b is false
   even when Object #1 and Object #2 have the same data
~~~

Reference comparison does not depend on whether the two objects belong to the same class or have the same field values. It only checks the **identity of the referenced object**.

## 3. Runnable Program: Same Object and Two Different Objects

Create the file **`ReferenceIdentityDemo.java`**:

~~~java
class Box {
    private final String label;
    private int count;

    Box(String label, int count) {
        if (label == null || label.isBlank() || count < 0) {
            throw new IllegalArgumentException("Box không hợp lệ");
        }
        this.label = label;
        this.count = count;
    }

    int count() {
        return count;
    }

    void add(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Số cộng phải dương");
        }
        count = Math.addExact(count, amount);
    }

    String label() {
        return label;
    }
}

public class ReferenceIdentityDemo {
    public static void main(String[] args) {
        Box first = new Box("X", 10);
        Box alias = first;
        Box second = new Box("X", 10);

        System.out.println("first == alias: " + (first == alias));
        System.out.println("first != alias: " + (first != alias));
        System.out.println("first == second: " + (first == second));
        System.out.println("first != second: " + (first != second));
        System.out.println("same count: " + (first.count() == second.count()));
        System.out.println("equals second: " + first.equals(second));

        alias.add(3);
        System.out.println("first count: " + first.count());
        System.out.println("second count: " + second.count());

        Box maybe = null;
        System.out.println("maybe == null: " + (maybe == null));
        System.out.println("first != null: " + (first != null));

        maybe = first;
        System.out.println("maybe == alias: " + (maybe == alias));
    }
}
~~~

In the directory containing the file, run:

~~~bash
javac -encoding UTF-8 ReferenceIdentityDemo.java
java ReferenceIdentityDemo
~~~

**Stdout:**

~~~text
first == alias: true
first != alias: false
first == second: false
first != second: true
same count: true
equals second: false
first count: 13
second count: 10
maybe == null: true
first != null: true
maybe == alias: true
~~~

### Analyzing Each Group of Results

1. `Box first = new Box("X", 10)` creates object #1.
2. `Box alias = first` only copies the reference, so `first == alias` is `true` and `first != alias` is `false`.
3. `Box second = new Box("X", 10)` creates object #2, so `first == second` is `false`, **even though the initial label and count are the same**.
4. `first.count() == second.count()` compares two **`int`** values, both equal to 10, so it is `true`. This is a **primitive value comparison**, unlike `first == second`.
5. `Box` does not override `equals()`, so `first.equals(second)` uses the version inherited from `Object`, which also returns `false` for two separate objects.
6. `alias.add(3)` mutates **object #1 itself**, which `first` also points to. Therefore `first.count()` becomes 13, while `second.count()` remains 10.
7. `maybe == null` is `true` before the assignment `maybe = first`; after the assignment, `maybe == alias` becomes `true` because they point to the same object.

The example shows that a **reference** assignment does not create a new object. Conversely, a typical `new` expression creates a separate object, so identity cannot be inferred merely from having the same class and data.

## 4. Reassigning a Variable Does Not Modify the Old Object

Consider a conceptually standalone snippet, assuming the `Box(String,int)` constructor from the previous section:

~~~java
Box a = new Box("A", 1);
Box b = a;

b = new Box("B", 2);
~~~

Before the final assignment:

~~~text
a ----+
      +----> Box #1 ("A", 1)
b ----+
~~~

After the final assignment:

~~~text
a --------> Box #1 ("A", 1)
b --------> Box #2 ("B", 2)
~~~

`b = new Box(...)` makes **variable `b` point to the new object**; it does not turn `Box #1` into `Box #2` and does not automatically change the reference value in `a`.

If you then write `a = null;`, variable `a` stops holding a reference to `Box #1`; that object can become a candidate for garbage collection if no other reference paths to it remain. **Assigning `null` does not mean the object is deleted immediately**.

The case of passing a reference into a method is similar: Java **passes arguments by value**. The method receives a copy of the reference value; it can mutate the shared object if permitted, but reassigning the parameter variable does not cause the caller's variable to switch to a different object.

## 5. Safe and Common Comparison with `null`

`null` is a special reference value, not an instance of a class. Comparing against null is a case where `==` and `!=` should be used:

~~~java
String name = null;

System.out.println(name == null); // true
System.out.println(name != null); // false
~~~

This is an illustrative snippet inside a method. The two comparisons **do not invoke a method on `name`**, so they do not throw a `NullPointerException` simply because `name` is `null`.

Conversely:

~~~java
String name = null;
System.out.println(name.equals("An")); // NullPointerException.
~~~

The snippet above **compiles, but fails at runtime**, because it invokes the instance method `equals` through a `null` reference.

Distinguishing the cases:

| Expression | Result when `name == null` |
| --- | --- |
| `name == null` | `true` |
| `name != null` | `false` |
| `name == "An"` | `false` |
| `name.equals("An")` | Throws `NullPointerException` |
| `"An".equals(name)` | `false` |
| `java.util.Objects.equals(name, "An")` | `false` |

Checking `if (obj != null)` before invoking a method on `obj` is a common technique. For content comparisons where values may be null, `Objects.equals(a,b)` is convenient because it also handles the case where both references are null.

## 6. How Does `==` Differ from `equals()`?

In Java:

- `a == b` with two **references** asks: "Is this **the same object**?"
- `a.equals(b)` is **a method call**; the meaning of "equal" depends on the **`equals()` implementation** of the class that `a` references.
- If a class does not override `equals()`, the default implementation in `java.lang.Object` is based on **reference identity**.
- Many library classes such as `String`, wrappers, and many collections define `equals()` to compare **values/content** according to their own contracts.
- `java.util.Objects.equals(a,b)` handles null safely: if both are null, it returns `true`; if one is null, `false`; if both are non-null, it calls `a.equals(b)`.

Comparison table:

| Practical question | Typically used | Reason |
| --- | --- | --- |
| Are they **the exact same instance**? | `a == b` | Compares reference identity |
| Are they **two different instances**? | `a != b` | Negates reference equality |
| Is a reference null? | `a == null` | Checks for a null value |
| Do two strings have the same content? | `a.equals(b)` or `Objects.equals(a,b)` | `String.equals` has character-comparison semantics |
| Do two domain objects have equivalent values? | `a.equals(b)` if the class defines it properly | Evaluates the domain's equality contract |
| Do two arrays have the same elements? | `Arrays.equals` / `Arrays.deepEquals` as appropriate | `==` only compares whether it is the same array object |
| Are two `int` values equal? | `x == y` | Operator comparing **primitive values** |

It is **incorrect** to say that `equals()` "always compares all fields". The class author decides which components participate in the comparison and must adhere to the `equals` contract. For a class that does not override it, `equals` can produce the same result as `==`; for a class that overrides it, the result may differ.

## 7. `String`: Why Does `==` Sometimes Print `true` Even with Different Variables?

`String` is a classic case that easily causes misunderstandings. Java has a **string pool** and an interning mechanism for string literals and constant expressions. Therefore, two variables assigned the same literal can point to the same instance, yet that does not turn `==` into a content comparison.

Example:

~~~java
String a = "java";
String b = "java";
String c = new String("java");

System.out.println(a == b);      // true: same interned literal
System.out.println(a == c);      // false: c references a new object
System.out.println(a.equals(c)); // true: same content
~~~

This is an illustrative snippet inside a method. `new String("java")` creates a separate `String` object according to `new` semantics, whereas the `"java"` literal uses the interned representation.

**Mistake to avoid:** observing that `"a" == "a"` is `true` and concluding that `==` compares strings character by character. That result is a consequence of **reference identity of interned literals**, not the general semantics of the operator.

### String and Array Program with Deterministic Output

Create the file **`ContentEqualityDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

record Pixel(int x, int y) {
}

public class ContentEqualityDemo {
    public static void main(String[] args) {
        String literal = "java";
        String folded = "ja" + "va";
        String created = new String("java");

        System.out.println("literal == folded: " + (literal == folded));
        System.out.println("literal == created: " + (literal == created));
        System.out.println("literal.equals(created): "
                + literal.equals(created));
        System.out.println("literal == created.intern(): "
                + (literal == created.intern()));

        int[] first = {1, 2};
        int[] second = {1, 2};
        int[] alias = first;

        System.out.println("arrays same reference: " + (first == alias));
        System.out.println("arrays different reference: " + (first == second));
        System.out.println("Arrays.equals: " + Arrays.equals(first, second));
        System.out.println("Objects.equals(arrays): "
                + Objects.equals(first, second));

        int[][] left = {{1, 2}, {3}};
        int[][] right = {{1, 2}, {3}};
        System.out.println("Arrays.deepEquals: "
                + Arrays.deepEquals(left, right));

        Pixel p1 = new Pixel(2, 3);
        Pixel p2 = new Pixel(2, 3);
        System.out.println("record reference: " + (p1 == p2));
        System.out.println("record equals: " + p1.equals(p2));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ContentEqualityDemo.java
java ContentEqualityDemo
~~~

**Exact stdout:**

~~~text
literal == folded: true
literal == created: false
literal.equals(created): true
literal == created.intern(): true
arrays same reference: true
arrays different reference: false
Arrays.equals: true
Objects.equals(arrays): false
Arrays.deepEquals: true
record reference: false
record equals: true
~~~

Explanation:

1. `folded = "ja" + "va"` is a **constant expression** concatenated at compile time and interned, so it has the same reference as the `"java"` literal.
2. `created = new String("java")` creates a different instance, so `literal == created` is `false`, while `literal.equals(created)` is `true`.
3. `String.intern()` returns a reference to the interned representation of the content, so `literal == created.intern()` is `true`.
4. `first == alias` is `true` because the two variables point to the same array; `first == second` is `false` because two separate arrays were created.
5. `Arrays.equals(first, second)` iterates over the `int` elements, compares them by value, and returns `true`.
6. `Objects.equals(first, second)` **does not compare array contents**: it calls `first.equals(second)` when both are non-null, and arrays do not override `Object.equals`; the result is `false`.
7. `Arrays.deepEquals(left,right)` performs a nested comparison of the arrays and elements appropriately; in the example, both matrices have the same data, so it is `true`.
8. The two `Pixel` records are created by two different `new` expressions, so `p1 == p2` is `false`. A record auto-generates `equals` based on its components; here both `x` and `y` are equal, so `p1.equals(p2)` is `true`.

**Note:** do not use `new String(...)` in application code merely for comparisons; this is a technique to illustrate the difference between identity and content equality. For user-entered strings, runtime-concatenated strings, or strings read from files/APIs, use `equals` to check content rather than relying on interning.

## 8. Arrays: `==` Compares Array Objects, Does Not Traverse Elements

Arrays are **objects** in Java. Two arrays with the same number of elements and the same values **can still have different references**:

~~~java
int[] a = {1, 2};
int[] b = {1, 2};

System.out.println(a == b);                 // false
System.out.println(java.util.Arrays.equals(a, b)); // true
~~~

This is an illustrative snippet. `a` and `b` are produced by two array creations, so `a == b` is `false`. It is `Arrays.equals(int[],int[])` that performs an **element-by-element** comparison.

Distinguishing the approaches:

| Situation | Common comparison approach |
| --- | --- |
| Do two variables point to the same array? | `a == b` |
| Do two `int[]` arrays have the same elements? | `Arrays.equals(a,b)` |
| Do two `String[]` arrays have the same elements by `String.equals`? | `Arrays.equals(a,b)` |
| Do two nested array structures have matching data? | `Arrays.deepEquals(a,b)` when the API shape is suitable |
| Is an array null? | `a == null` |

Do not use `a.equals(b)` or `Objects.equals(a,b)` expecting a deep comparison of array elements. If you have an array of **mutable objects**, `Arrays.equals(Object[],Object[])` uses each element's `equals` (with null handling), rather than automatically comparing every field reflectively.

For multidimensional arrays, `Arrays.deepEquals` is useful, but you need to consider **jagged arrays**, null elements, and arrays containing references to objects with special `equals` behavior. Appropriate usage depends on the data type and semantics.

## 9. Custom Classes: Why Does the Default `equals()` Behave Like Identity?

Every ordinary Java class inherits `equals(Object)` from `java.lang.Object` unless it overrides it. The default version of `Object.equals` considers two references equal only when they denote **the same object**.

For example, `Box` in the first program did not override `equals`. Therefore:

~~~java
Box a = new Box("X", 10);
Box b = new Box("X", 10);

System.out.println(a == b);      // false
System.out.println(a.equals(b));  // false
~~~

The two objects have the **same state**, yet the class has not defined "two Boxes with the same content are equal".

There are two different design choices:

1. **Objects with their own identity**, such as a network connection, a UI window, or an active session: sometimes identity alone makes sense.
2. **Value objects**, such as identifiers, coordinates, or value ranges: you typically want different instances with the same component values to be considered equal.

**You should not automatically override `equals` in every class.** Determine the **domain meaning of equality** before implementing it. For an entity with an ID, comparing two objects with the same ID may make sense in the domain, but you still have to consider the ID lifecycle, persistence, proxies, state mutations, and the `equals/hashCode` contract.

## 10. Implementing `equals()` and `hashCode()` for a Value Object

When a class needs to define **data-based equality**, override `equals(Object)` and `hashCode()` consistently. For example, a user key identified by the `(system, number)` pair.

Create the standalone file **`EqualsContractDemo.java`**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

final class MemberId {
    private final String system;
    private final long number;

    MemberId(String system, long number) {
        if (system == null || system.isBlank() || number < 0) {
            throw new IllegalArgumentException("ID không hợp lệ");
        }
        this.system = system;
        this.number = number;
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        if (!(obj instanceof MemberId other)) {
            return false;
        }
        return number == other.number && system.equals(other.system);
    }

    @Override
    public int hashCode() {
        return Objects.hash(system, number);
    }
}

public class EqualsContractDemo {
    public static void main(String[] args) {
        MemberId first = new MemberId("app", 42);
        MemberId second = new MemberId("app", 42);
        MemberId third = new MemberId("app", 43);

        System.out.println("first == second: " + (first == second));
        System.out.println("first.equals(second): " + first.equals(second));
        System.out.println("first.equals(third): " + first.equals(third));
        System.out.println("hashes match: "
                + (first.hashCode() == second.hashCode()));

        Set<MemberId> ids = new HashSet<>();
        ids.add(first);
        System.out.println("contains second: " + ids.contains(second));
        System.out.println("contains third: " + ids.contains(third));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 EqualsContractDemo.java
java EqualsContractDemo
~~~

**Stdout:**

~~~text
first == second: false
first.equals(second): true
first.equals(third): false
hashes match: true
contains second: true
contains third: false
~~~

### Why Is This Code Correct Regarding the Basic Contract?

- `if (this == obj) return true;`: optimization when both references point to the same object. Using `==` **inside `equals()` is completely reasonable** to recognize the same instance.
- `instanceof MemberId other` (Java 17 pattern matching) rules out null or different types, while also declaring the `other` variable.
- `number == other.number` compares two **primitive `long`** values.
- `system.equals(other.system)` compares the two `String` contents, not string identity.
- `hashCode()` is based on the exact same two components used in `equals`, so if two `MemberId` instances are equal, their hash codes are equal.
- `HashSet.contains(second)` relies on the `equals/hashCode` contract, so it finds an object by value even though its reference differs from the added object.

Two objects that are **not equal** **can** still have the same hash code: collisions are valid. Therefore, **do not use `a.hashCode() == b.hashCode()` as an equality check**.

Using immutable fields such as `final String system` and `final long number` helps avoid the problem of mutating components involved in `hashCode` after the object has already been inserted into a `HashSet` or used as a `HashMap` key.

## 11. The `equals()` Contract Is Not Just "Compare All Fields"

According to `Object.equals`, a proper implementation needs these fundamental properties:

1. **Reflexive:** `x.equals(x)` is `true` for any non-null reference `x`.
2. **Symmetric:** `x.equals(y)` and `y.equals(x)` yield the same result.
3. **Transitive:** if `x.equals(y)` and `y.equals(z)`, then `x.equals(z)`.
4. **Consistent:** when the data used in equality comparisons is not modified, repeated invocations produce consistent results.
5. **Non-null:** `x.equals(null)` is `false` for any non-null `x`.

Alongside it is the `hashCode` contract: **two objects considered equal by `equals` must have the same hash code**. The converse is not required.

In practice, there are stateful classes that still use identity equality, and classes that use only a subset of stable fields to determine equality. Therefore, do not mechanically apply "compare all fields" without identifying the role of each field.

### The Equality Contract and `record`

A `record` in Java automatically generates `equals`/`hashCode` based on its components. With `record Pixel(int x, int y)` in the earlier example, `new Pixel(2,3).equals(new Pixel(2,3))` is `true` even though they are two different objects.

**You should not assume that a record automatically deep-compares all nested data.** If a component is an **array**, the equality generated for the array component is inherently based on the equality appropriate for the array's reference type, without automatically calling `Arrays.deepEquals` at every level. For mutable nested data, consider defining appropriate value types and ownership.

## 12. With Primitives, `==` Compares Values, Not Objects

The `==` operator does not exist only for references. When two operands are appropriate **primitive values**, Java compares their values according to the corresponding type rules:

~~~java
int a = 5;
long b = 5L;
System.out.println(a == b); // true: compares numeric values after appropriate conversion

boolean ready = true;
System.out.println(ready == true); // true
~~~

This is an illustrative snippet. `a` and `b` are not references to two objects; saying "the same object" here is incorrect.

A few details when comparing floating-point numbers:

- `Double.NaN == Double.NaN` is `false`, because floating-point comparison with NaN is not equal even to itself.
- `0.0 == -0.0` is `true` under primitive floating-point comparison.
- Comparing floating-point numbers using `==` may not be appropriate for checking approximate calculation results; when needed, define an error tolerance rule according to requirements.

The floating-point examples above are about **primitive equality**, not `Double` references. Two `Double` wrappers are objects; `==` when directly comparing two `Double` variables is still reference identity.

## 13. Wrappers and Autoboxing: Same Value Does Not Guarantee Same Reference

Wrappers such as `Integer`, `Long`, and `Boolean` are **reference types**. For two variables of type `Integer`, `==` checks **identity**, and does not automatically perform `Integer.equals`.

~~~java
Integer a = Integer.valueOf(7);
Integer b = Integer.valueOf(7);

System.out.println(a.equals(b)); // true: same Integer value
~~~

Java allows implementations to cache certain wrapper objects; for `Integer.valueOf`, the range -128 to 127 is cached per the API contract. Therefore, some `a == b` comparisons can evaluate to `true` for cached values. **Do not conclude that `==` is valid for comparing the contents of all wrappers.**

For values outside the required range, object reuse may depend on the implementation or how the object was created. For example, `Integer x = 1000; Integer y = 1000;` should not be used to assert a fixed stdout for `x == y` across all runtimes. Use `x.equals(y)` to compare `Integer` values.

### Primitives and Wrappers Together in `==`

If one operand is a primitive number and the other operand is the corresponding numeric wrapper, Java can **unbox** the wrapper to perform a numeric comparison:

~~~java
Integer boxed = Integer.valueOf(5);
int primitive = 5;
System.out.println(boxed == primitive); // true: compares two numeric values
~~~

Unlike `Integer boxedA == Integer boxedB`, the expression above uses conversion according to primitive numeric rules. **Be cautious with null**:

~~~java
Integer missing = null;
int expected = 0;
// System.out.println(missing == expected); // Running this throws NullPointerException.
~~~

When `missing` needs to be unboxed, Java has no primitive value to extract from `null`. However, the expression `missing == null` is safe because it is a reference comparison.

**Conclusion:** to explain `==` accurately, you must know the **static types of both operands at the comparison site**, not just look at how they are printed to the screen.

## 14. Not Any Two Reference Types Can Be Compared with `==`

The Java compiler enforces **type compatibility rules** when comparing two references. Example illustrating a compilation error:

~~~java
String text = "7";
Integer number = 7;

// boolean same = (text == number); // ERROR: incomparable types.
~~~

`String` and `Integer` are types that are not directly compatible with each other for this reference comparison. Even though at runtime the two objects obviously cannot be the same object, Java **does not necessarily allow writing every `==` between two unrelated reference types**.

A valid case:

~~~java
Object text = "7";
Object number = Integer.valueOf(7);
System.out.println(text == number); // false
~~~

Because both expressions have type `Object`, the reference comparison is valid and returns `false`: they point to two different objects.

Using a cast merely to force two expressions past the compiler is generally **not good design**. If the goal is to check data equivalence across different types, convert them to a **meaningful common value type** in the domain, rather than substituting reference identity.

## 15. `Objects.equals` Is Null-Safe, but Does Not Perform Deep Comparison

`java.util.Objects.equals(a,b)` is very convenient when the two references **may be null**:

~~~java
String left = null;
String right = null;

System.out.println(java.util.Objects.equals(left, right)); // true

right = "An";
System.out.println(java.util.Objects.equals(left, right)); // false
~~~

In terms of result, this method is conceptually equivalent to:

~~~java
return a == b || (a != null && a.equals(b));
~~~

This is **an expression illustrating the method body**, not a standalone program. Calling `a.equals(b)` still depends on the implementation of the left-hand side's class.

Therefore:

- `Objects.equals("A", new String("A"))` is `true` based on String content.
- `Objects.equals(null, null)` is `true`.
- `Objects.equals(array1, array2)` for two separate arrays is normally **`false`**, even if their elements are identical.
- If a class does not override `equals`, `Objects.equals` **does not automatically compare every field** of the object.

When working with arrays, choose `Arrays.equals` or `Arrays.deepEquals`. When working with domain objects, rely on the **class's `equals` contract**, rather than expecting `Objects.equals` to resolve all semantic differences.

## 16. Reference Identity Says Nothing About Business Relationships

Two references can differ while representing the **same business entity**, such as two snapshots of a database record with the same ID. Conversely, two references can point to the same object while that object **has changed state** over time.

Conceptual example:

~~~text
On the first read:
  snapshotA  ---> User{id=42, displayName="An"}

On the second read:
  snapshotB  ---> User{id=42, displayName="Anh"}

snapshotA == snapshotB can be false because they are two different objects,
even though both refer to the user with id=42.
~~~

This is a **domain diagram**, without specifying how any particular ORM or cache operates. To conclude that two objects represent the same user, you must define business criteria — such as a valid ID within a given system — rather than using `==` as a substitute.

**Important:** many ORMs have complex rules for identity maps, proxies, entity equality, and ID lifecycles. There is no universal rule that every entity should compare `equals` solely by ID at all times; you must consider unassigned IDs, lazy loading, and sessions. In Java Core, keep these three concepts distinct:

1. **Reference identity:** the exact same object in JVM logical memory.
2. **Value equality:** data defined as equal by the class.
3. **Business identity:** the same business entity according to system rules.

These three questions can produce three different answers.

## 17. `==`, `equals()`, and Safety When Data Mutates

Comparing identity **does not create a copy** and **does not make an object immutable**. If:

~~~java
Box first = new Box("X", 10);
Box alias = first;

alias.add(1);
~~~

then `first == alias` remains `true` before and after the call; the target object has changed state, yet the references still point to the same object.

For content-based `equals()`, the comparison result can **change over time** if the fields participating in equality are mutable. This is especially important when the object is used as a `HashMap` key or a `HashSet` element. If the hash code depends on mutable values and a value changes while the object is stored in a hash-based structure, lookup behavior may break expectations.

Simple value objects should generally have stable fields assigned through the constructor, such as `MemberId` in the previous section. If an API intentionally uses identity equality, state it clearly, especially when users could easily confuse it with content equality.

## 18. When Should You Use `==` and When Should You Not?

A practical decision table:

| You want to know... | Typically appropriate Java expression |
| --- | --- |
| Do two variables point to **the exact same object**? | `a == b` |
| Do two variables point to **two different objects**? | `a != b` |
| Is a reference null? | `a == null` or `a != null` |
| Are two primitive values equal? | `x == y` per primitive rules |
| Do two `String` values have the same characters? | `a.equals(b)`, or `Objects.equals(a,b)` when null is possible |
| Do two `Integer` objects have the same number? | `a.equals(b)` or `Objects.equals(a,b)` |
| Do two arrays have the same elements? | `Arrays.equals(a,b)` |
| Do two nested arrays have equal structure? | Appropriate `Arrays.deepEquals(a,b)` |
| Are two domain value objects equivalent? | Override `equals/hashCode` according to invariants |
| Do two entities represent the same business ID? | Domain-specific identity rules; do not default to `==` |

A good habit is to **ask the right question before choosing an operator**. Determine whether you need to compare **references** or **values**. If your goal is string content, do not rely on a few `==` checks that happen to return `true` due to interning or caching.

## 19. Common Mistakes and How to Fix Them

| Misconception or error | Why it is wrong | How to handle it |
| --- | --- | --- |
| `new Person("An") == new Person("An")` must be true | Two `new` calls create two objects | Use `equals` if the class defines content comparison |
| Two variables have different names so `!=` is true | `b = a` copies the reference | Track aliases and the number of object creations |
| Comparing `String` content with `==` | `==` only compares references | Use `String.equals` or `Objects.equals` |
| `"abc" == "abc"` being true proves `==` compares characters | Literals are interned | Do not generalize from the string pool |
| `array1 == array2` compares elements | Arrays are objects; `==` compares identity | Use `Arrays.equals` |
| `Objects.equals` automatically deep-compares arrays | It invokes the class's `equals` | Use `Arrays.deepEquals` when needed |
| `obj.equals(null)` is always safe | If `obj == null`, calling the method fails | Use `Objects.equals` or check for null first |
| Every `equals` compares all fields | The class defines equality semantics | Read or implement the contract properly |
| `Integer` always gives `==` false when creating two variables | Wrappers have caching mechanisms | Use `equals` to compare values |
| Equal `hashCode` means equal objects | Hash collisions are valid | Rely only on `equals` per the contract |
| `==` always compares values across all types | For references, it compares identity; for primitives, it compares values | Check the static types of both operands |
| Any two references can be compared with `==` | Java has type compatibility rules | Use operands of compatible types |
| `!=` and `!equals()` always mean the same thing | One negates identity, the other negates class-defined equality | Choose the right question you are checking |

## 20. Self-Check Exercises

**Exercise 1 — Alias.** Given:

~~~java
Box x = new Box("A", 2);
Box y = x;
Box z = new Box("A", 2);
~~~

Determine `x == y`, `x != z`, and `x.count() == z.count()`, and explain each result.

**Exercise 2 — Reassigning a Variable.** Continuing Exercise 1 with `y = z;`. Now what are `x == y` and `y == z`? Is any object deleted or modified solely because of the assignment?

**Exercise 3 — Null.** With `String s = null;`, which expressions are safe: `s == null`, `s.equals("a")`, `Objects.equals(s,"a")`? State the result or exception.

**Exercise 4 — String.** Explain why `String a = "hi"; String b = new String("hi");` normally produces `false` for `a == b` yet `true` for `a.equals(b)`.

**Exercise 5 — Arrays.** Two `int[]` arrays contain `{1,2,3}` but were created in two separate statements. What results will `==`, `Arrays.equals`, and `Objects.equals` produce?

**Exercise 6 — Wrappers.** Why should you not use `Integer x = 1000, y = 1000; System.out.println(x == y);` to check whether two numbers are equal? How is comparing `Integer x` with primitive `int n` different?

**Exercise 7 — Equals Contract.** If two `MemberId` objects have the same `system` and `number`, what `equals` result and `hashCode` relationship are required? Are equal hash codes sufficient to establish equality?

**Exercise 8 — Static Types.** Why does `String s = "a"; Integer i = 1; s == i` fail to compile, whereas `Object a = s; Object b = i; a == b` is valid?

**Exercise 9 — Record.** With `record Point(int x,int y) {}`, how do `new Point(1,2) == new Point(1,2)` and `new Point(1,2).equals(new Point(1,2))` differ?

**Exercise 10 — Purpose of Comparison.** You are implementing an account management system: two Java objects are loaded at two different times, both carrying the account code `"A-01"`. Does `==` reliably answer the question "same business account"? What else needs to be defined?

### Short Answers

1. `x == y` is true; `x != z` is true; comparing primitive `count()` returns true because both are 2.
2. `x == y` is false and `y == z` is true; the assignment changes the reference held in `y`, without modifying any object.
3. `s == null` is true; `s.equals("a")` throws `NullPointerException`; `Objects.equals(s,"a")` is false.
4. `new String` creates a new object, while a literal has an interned representation; `equals` compares content.
5. `==` is false, `Arrays.equals` is true, and `Objects.equals` is false.
6. Two `Integer` objects compare identity when using `==`; caching is not a value-comparison rule. Comparing against a primitive can trigger unboxing, and if the wrapper is null it can throw an exception.
7. `equals` is true; their hash codes must be equal. Matching hashes do **not** prove two objects are equal.
8. The `String` and `Integer` type pair is not directly compatible for that reference comparison; two `Object` expressions can be compared for identity.
9. `==` is false due to being two objects; `equals` is true because the record compares the corresponding `int` components.
10. No; you need a rule based on **business identity**, such as an account code within the system's proper uniqueness scope.

## 21. References

- [Java Language Specification 17, §15.21 — Equality Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.21): `==`, `!=` for numbers, booleans, and references.
- [Java SE 17 API — Object.equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object)): the equals contract and its relationship with hashCode.
- [Java SE 17 API — Objects.equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#equals(java.lang.Object,java.lang.Object)): null-safe comparison based on equals.
- [Java SE 17 API — Arrays.equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): comparing array contents using the appropriate overload.
- [Java SE 17 API — String.intern](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#intern()): interned string representation.
- [Java Language Specification 17, §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): derived methods for records, including equals.

**Remember:** for two **references**, `==` means **the same object** and `!=` means **not the same object**; these operators never automatically compare fields. To compare **content**, use `equals()` or an appropriate API such as `Arrays.equals`; to compare **business identifiers**, specific domain criteria are required. Checking for `null` is a completely valid reason to use `==` and `!=`.
