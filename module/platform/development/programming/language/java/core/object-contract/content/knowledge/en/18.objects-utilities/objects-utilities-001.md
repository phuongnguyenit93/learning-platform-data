# `Objects.equals()` handles `null` and delegates to `equals()`

## Lesson Objectives

`java.util.Objects.equals(Object a, Object b)` is a small but very common utility when writing Java. This method helps compare two references **without having to manually check whether the reference receiving the `equals()` call is `null`**. When both objects exist and are not the same reference, the result is determined by the `equals()` method of **the first argument**.

After completing this lesson, you can:

- Predict the result of `Objects.equals(a, b)` when one or both arguments are `null`.
- Explain the `a == b` check first and the short-circuit mechanism before calling `a.equals(b)`.
- Distinguish identity comparison using `==` from logical comparison using `equals()`.
- Understand accurately that `Objects.equals()` delegates to `a.equals(b)`, does not compare fields on its own, and does not call `b.equals(a)` for a two-way check.
- Use this utility when writing `equals(Object)` for a class with nullable reference fields.
- Choose the appropriate comparison for `String`, records, wrappers, arrays, and objects with specialized `equals()` contracts.

## 1. Purpose and method signature

`Objects` is a utility class in the `java.util` package. The two arguments of `Objects.equals` are declared as `Object`:

```java
public static boolean equals(Object a, Object b)
```

The method returns `true` if the two arguments are considered equal and `false` otherwise according to the following logic:

```java
return (a == b) || (a != null && a.equals(b));
```

This is an **equivalent expression to the implementation in the Java library**, used to explain the mechanism; it is not asking you to redefine the `Objects.equals()` method yourself.

The expression has three parts:

1. **`a == b`**: if they are the same reference, including both arguments being `null`, return `true` immediately.
2. **`a != null`**: if the first argument is `null` and did not pass the first branch, do not call a method on `a`; the result is `false`.
3. **`a.equals(b)`**: when `a` is non-`null` and the two references differ, call the `equals` method provided by the actual runtime type of `a`. It may be the default `Object.equals()` or an overridden method of a class such as `String`, `Integer`, a record, or a class you designed.

The two operators `||` and `&&` **short-circuit evaluate** from left to right: when `a == b` is already `true`, the right side of `||` is not evaluated; when `a != null` is `false`, `a.equals(b)` is not evaluated. Thanks to this, `Objects.equals(null, x)` does not throw `NullPointerException` from calling a method on a `null` first argument.

Note the scope of this guarantee: this utility **avoids dereferencing argument `a` when it is `null`**. It does not prevent a custom `equals()` implementation from throwing an exception internally, nor does it fix violations of a class's `equals()` contract.

## 2. Four fundamental `null` cases

For classes whose `equals()` follows the standard contract (a non-`null` object must not be equal to `null`), the result table is:

| Argument `a` | Argument `b` | `Objects.equals(a, b)` | Why? |
| --- | --- | --- | --- |
| `null` | `null` | `true` | `a == b` is `true`. |
| `null` | `"Java"` | `false` | `a == b` is false; `a != null` is false; `equals()` is not called. |
| `"Java"` | `null` | `false` | Calls `"Java".equals(null)` and gets `false`. |
| `"Java"` | `"Java"` | `true` | Same reference or same content according to `String.equals()`. |

Example:

```java
import java.util.Objects;

// Statements inside a method:
System.out.println(Objects.equals(null, null));     // true
System.out.println(Objects.equals(null, "Java"));   // false
System.out.println(Objects.equals("Java", null));   // false
System.out.println(Objects.equals("Java", "Java")); // true
```

This snippet illustrates statements inside a method; a standalone program is in section 4.

An important technical nuance: the fact that `Objects.equals(a, b)` with a non-`null` `a` ultimately calls `a.equals(b)` means that **a class that overrides `equals(null)` to return `true` has already violated the `equals` contract**, and the utility does not automatically correct that mistake. In contract-compliant code, when one side is `null` and the other is non-`null`, they will not be equal. Therefore, do not treat this utility as a mechanism to check or "fix" every buggy `equals` implementation.

### `Objects.equals(a, b)` does not necessarily call `equals()`

If `a` and `b` are the same reference:

```java
Object one = new Object();
Object alias = one;

System.out.println(Objects.equals(one, alias)); // true
```

The result comes directly from `a == b`. There is no need to call `one.equals(alias)`, even though that method on `Object` also returns `true` for the same reference. This is both an optimization and the reason why a test using `Objects.equals(x, x)` cannot by itself prove that `x.equals(x)` is overridden correctly.

## 3. Why is it important to understand "delegation"?

`Objects.equals(a, b)` **does not know on its own** whether two objects should be considered equal by ID, name, amount, fields, or identity. It delegates the decision to `a.equals(b)` (after the fast checks).

Compare three examples:

```java
String a = new String("Java");
String b = new String("Java");

System.out.println(a == b);                  // false
System.out.println(Objects.equals(a, b));    // true

Object x = new Object();
Object y = new Object();
System.out.println(Objects.equals(x, y));    // false
```

- `a == b` compares references. Two `new String(...)` statements create two separate objects.
- `Objects.equals(a, b)` ultimately calls `String.equals(b)`, comparing string content; both strings contain `"Java"`, so the result is `true`.
- Default `Object` does not compare fields by content and instead uses object identity. The two new objects `x` and `y` are different, so `Objects.equals(x, y)` is still `false`.

This example shows that "safe with `null`" **does not mean** "every object will be compared by value". When data needs to be compared according to a custom definition, the data type must implement `equals()` appropriately.

### Which side decides?

Pay attention to the call direction:

```text
Objects.equals(a, b)

  if a == b
      → true
  else if a == null
      → false
  else
      → a.equals(b)
```

There is no step that automatically calls `b.equals(a)`, checks the result in both directions, or normalizes the two objects to the same type.

If a class writes `equals()` incorrectly so that `a.equals(b)` and `b.equals(a)` differ, `Objects.equals` can produce different results when the argument order is swapped. **The bug lies in violating the symmetry of the `equals` contract**, not in the `Objects.equals` method.

For `String` and standard types with a proper contract, users usually do not notice the call direction difference because symmetry is already guaranteed.

## 4. Compilable and runnable Java 17+ program

To observe exactly when `equals()` is called, the example uses an `Observed` class with a counter for how many times `equals()` is entered. The counter **does not participate** in defining equality or the hash code.

Save the file `ObjectsEqualsDemo.java`:

```java
import java.util.Objects;

public class ObjectsEqualsDemo {
    static final class Book {
        private final int id;
        private final String title;

        Book(int id, String title) {
            this.id = id;
            this.title = title;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Book other)) {
                return false;
            }
            return id == other.id
                    && Objects.equals(title, other.title);
        }

        @Override
        public int hashCode() {
            return Objects.hash(id, title);
        }
    }

    static final class Observed {
        private final int value;
        private int equalsCalls;

        Observed(int value) {
            this.value = value;
        }

        @Override
        public boolean equals(Object obj) {
            equalsCalls++;
            return obj instanceof Observed other
                    && value == other.value;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(value);
        }

        int equalsCalls() {
            return equalsCalls;
        }
    }

    public static void main(String[] args) {
        System.out.println("both null: "
                + Objects.equals(null, null));
        System.out.println("left null: "
                + Objects.equals(null, "Java"));
        System.out.println("right null: "
                + Objects.equals("Java", null));

        String first = new String("Java");
        String second = new String("Java");
        System.out.println("string identity: " + (first == second));
        System.out.println("string equality: "
                + Objects.equals(first, second));

        Book book1 = new Book(7, "Effective Java");
        Book book2 = new Book(7, "Effective Java");
        Book book3 = new Book(7, null);
        Book book4 = new Book(7, null);
        System.out.println("book identity: " + (book1 == book2));
        System.out.println("book equality: "
                + Objects.equals(book1, book2));
        System.out.println("nullable field: "
                + Objects.equals(book3, book4));
        System.out.println("different book: "
                + Objects.equals(book1, book3));

        Observed left = new Observed(4);
        Observed right = new Observed(4);
        System.out.println("delegated: "
                + Objects.equals(left, right));
        System.out.println("left calls: " + left.equalsCalls());
        System.out.println("right calls: " + right.equalsCalls());

        System.out.println("same reference shortcut: "
                + Objects.equals(left, left));
        System.out.println("left calls after shortcut: "
                + left.equalsCalls());
        System.out.println("null shortcut: "
                + Objects.equals(null, right));
        System.out.println("right calls after null: "
                + right.equalsCalls());

        System.out.println("reverse delegation: "
                + Objects.equals(right, left));
        System.out.println("right calls after reverse: "
                + right.equalsCalls());
    }
}
```

Compile and run on JDK 17 or newer:

```bash
javac ObjectsEqualsDemo.java
java ObjectsEqualsDemo
```

Output:

```text
both null: true
left null: false
right null: false
string identity: false
string equality: true
book identity: false
book equality: true
nullable field: true
different book: false
delegated: true
left calls: 1
right calls: 0
same reference shortcut: true
left calls after shortcut: 1
null shortcut: false
right calls after null: 0
reverse delegation: true
right calls after reverse: 1
```

**Important explanation:**

- The first three lines demonstrate `null` handling. They do not throw `NullPointerException` from calling a method on the first argument.
- Two `String` objects have the same content but different references; `Objects.equals` delegates to `String.equals`, so they are equal.
- Two different `Book` instances can be equal because `Book.equals` compares `id` and `title`; when both `title` fields are `null`, `Objects.equals(title, other.title)` returns `true`.
- In `Objects.equals(left, right)`, the two references differ and `left` exists, so `left.equals(right)` runs exactly once. The counter on `right` stays 0.
- In `Objects.equals(left, left)`, the two references match, so the `a == b` fast branch is used; the counter is not incremented.
- In `Objects.equals(null, right)`, the first argument is `null`, so `right.equals(...)` is not called. The counter on `right` stays 0.
- Reversing the order to `Objects.equals(right, left)` invokes `right.equals(left)`; the counter on `right` becomes 1.

The counter inside the object is only for observation and does not determine the value of `equals` or `hashCode`. In production models, `equals` is typically designed without side effects to keep behavior predictable.

## 5. Applying this when writing `equals(Object)` for a class with nullable fields

A common situation is a class with reference fields that may hold `null`. For example, `Book` in the program above has a nullable `title`:

```java
@Override
public boolean equals(Object obj) {
    if (this == obj) {
        return true;
    }
    if (!(obj instanceof Book other)) {
        return false;
    }
    return id == other.id
            && Objects.equals(title, other.title);
}
```

This is **a method body inside the `Book` class**, not a standalone Java program.

Different responsibilities:

1. `this == obj` handles the same-object case and provides an early-exit optimization.
2. `instanceof Book other` checks that the argument is not `null` and has a matching type; in Java 17, pattern matching creates the correctly typed `other` variable.
3. `id == other.id` compares two primitive `int` values.
4. `Objects.equals(title, other.title)` compares two `String` references, including the case where both are `null`.

Do not confuse `Objects.equals(title, other.title)` with a type check for the entire `obj` argument. Without verifying that `obj` has the appropriate type first, you still cannot safely access `other.title`. Always validate the argument first before reading its fields.

### Why not use `title.equals(other.title)` directly?

Suppose `title == null`. Then:

```java
// May throw NullPointerException:
boolean same = title.equals(other.title);
```

Another still-valid alternative is manual null checking:

```java
boolean same =
        title == null ? other.title == null
                      : title.equals(other.title);
```

Both snippets above are illustrations inside a class that has a `title` field and an `other` variable. For most nullable comparisons, `Objects.equals(title, other.title)` is more concise and expresses the intent directly.

### Remember to override `hashCode()` consistently

If `equals()` is overridden using `id` and `title`, two equal objects must have the same hash. For example:

```java
@Override
public int hashCode() {
    return Objects.hash(id, title);
}
```

`Objects.hash(...)` is a utility for computing a hash code that combines multiple values; it is **different** from `Objects.equals(...)` and does not by itself decide which class instances are considered equal. Compatibility between `equals` and `hashCode` remains the implementer's responsibility.

If the fields participating in equality can change after an object has been inserted into a `HashSet` or used as a `HashMap` key, lookup results may no longer behave as expected; consider an immutable object design or an appropriate key lifecycle.

## 6. Comparing `Objects.equals`, `==`, and direct `equals` calls

| Form | Safe when the left argument is `null`? | What does it check? | When should it be used? |
| --- | --- | --- | --- |
| `a == b` | Yes | Reference identity, or value if primitive | Same-instance checks, `null` checks, enums |
| `a.equals(b)` | No | Depends on object `a`'s `equals` definition | When `a` is already known to be non-`null` |
| `Objects.equals(a, b)` | Yes, for dereferencing `a` | Same reference or delegates to `a.equals(b)` | Logical comparison of potentially `null` references |
| `"OK".equals(a)` | Yes for the `"OK"` literal | Content comparison via `String.equals()` | Comparing a string against a known constant |

Situations that only need a `null` check should use `a == null` or `a != null`. There is no need to write `Objects.equals(a, null)`, because the direct expression is clearer and does not depend on an `equals(null)` implemented against the contract.

For primitive types, use `==` to compare their values. `Objects.equals` accepts `Object`, so primitive values have to be boxed into wrappers; this provides no benefit when comparing simple primitive values.

### Wrappers: value equality still depends on type

`Objects.equals(Integer.valueOf(5), Integer.valueOf(5))` is `true` because `Integer.equals` compares the int value. However, `Objects.equals(Integer.valueOf(5), Long.valueOf(5))` is `false` because `Integer.equals` does not consider a `Long` object equal to an `Integer` even though the numeric values look identical.

There is no mechanism that automatically converts any two objects to a "common numeric type" just because you call `Objects.equals`. If business logic needs to compare numbers across multiple types, conversion rules and precision must be defined and implemented explicitly.

### `BigDecimal`: the same mathematical number is not necessarily `equals`

```java
import java.math.BigDecimal;
import java.util.Objects;

// Inside a method:
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(Objects.equals(a, b)); // false
System.out.println(a.compareTo(b) == 0);  // true
```

`BigDecimal.equals` considers both the unscaled value and the scale; `compareTo` uses numeric value ordering. `Objects.equals` does not turn `equals` into `compareTo == 0`. This reinforces that the utility simply delegates to the specific type's contract.

## 7. Array pitfall: `null`-safe does not mean deep comparison

Java arrays do not override `Object.equals()` to compare elements. Therefore, two separately created `int[]` arrays still yield `Objects.equals(a, b) == false` even when they have the same contents. For one-dimensional arrays, `Arrays.equals` usually expresses the goal most clearly; for nested arrays, choose `Arrays.deepEquals` or `Objects.deepEquals` depending on the required semantics.

```java
int[] a = {1, 2};
int[] b = {1, 2};
System.out.println(Objects.equals(a, b));     // false
System.out.println(Objects.deepEquals(a, b)); // true
```

These are illustrative statements inside a method and require `import java.util.Objects;`. `Objects.deepEquals` handles array contents and `null`, but **does not automatically deep-compare arbitrary classes or a List containing arrays**. The lesson **Objects.deepEquals() differs from Objects.equals() on array arguments** goes deeper into multidimensional arrays, records/Lists wrapping arrays, and compatible hash functions.

## 8. `Objects.equals` cannot fix a broken `equals`

Suppose a class implements `equals()` off-contract, for example considering users with the same ID equal in one direction but not the other. `Objects.equals` does not call both directions to "reconcile" them. It only calls `a.equals(b)` when needed.

Some common mistakes in a class's `equals` method:

- **Not symmetric:** `a.equals(b) == true` while `b.equals(a) == false`.
- **Not transitive:** `a.equals(b)` and `b.equals(c)` are both `true` while `a.equals(c)` is `false`.
- **Not consistent:** same data, yet the result changes across calls due to external state or side effects.
- **Throws an exception on wrong-type arguments:** casting before checking with `instanceof` or `getClass()`.
- **Returns `true` for `null`:** violates the `equals` contract.
- **Overrides `equals` without updating `hashCode`:** causes failures in hash-based structures when two equal objects have incompatible hash codes.

`Objects.equals` only provides a `null`-safe outer branch and calls the appropriate object's method. To get logically sound equality behavior, the class's `equals(Object)` must be implemented and tested in accordance with the contract.

### Important detail about the same-reference shortcut

The expression `Objects.equals(a, a)` returns `true` without calling `a.equals(a)`. Therefore, if you are **testing the class's own `equals` implementation**, call `a.equals(a)` directly to test reflexivity, and use two different equivalent instances to test data comparison.

Do not use the `Objects.equals(a, a)` shortcut to "prove" that a class overrode `equals` properly.

## 9. Quick comparison with other `Objects` utilities

The `java.util.Objects` class has several similarly named methods with different purposes:

- **`Objects.equals(a, b)`:** compares two references in a `null`-safe way at the call level.
- **`Objects.deepEquals(a, b)`:** deep-compares when both arguments are arrays; for ordinary objects, relies on `equals` as appropriate.
- **`Objects.isNull(a)`:** semantically equivalent to checking `a == null`, often used as a method reference like `Objects::isNull`.
- **`Objects.nonNull(a)`:** semantically equivalent to `a != null`, usable as a predicate.
- **`Objects.requireNonNull(a)`:** returns the reference if non-`null`, or **throws `NullPointerException`** if `null`; useful for enforcing preconditions, not equality comparison.
- **`Objects.hashCode(a)`:** returns 0 if `a` is `null`, otherwise calls `a.hashCode()`.
- **`Objects.hash(values...)`:** combines hashes from multiple values via varargs; used when implementing `hashCode` for multi-field classes.

In particular, `Objects.requireNonNull(a)` is meant to **reject `null`**, in contrast to `Objects.equals`, which **accepts `null` as an argument for comparison**. Use the right tool for the right data contract.

## 10. Usage in application code

### Comparing two nullable fields

```java
String oldEmail = null;
String newEmail = "a@example.com";

boolean changed = !Objects.equals(oldEmail, newEmail); // true
```

This is an illustrative snippet inside a method with `import java.util.Objects;`. When you only need to know whether two nullable values differ, this form is clear and does not require the left-hand string to exist.

### Comparing values during search or update

```java
static boolean sameLabel(String current, String expected) {
    return Objects.equals(current, expected);
}
```

This is a method declaration inside a class that has imported `Objects`. It follows the policy that **two `null` values are considered equal**. If business rules do not want "both missing data" to count as equal, write a custom policy instead of assuming `Objects.equals` fits every situation.

### With records

```java
record Point(int x, int y) {}

Point p1 = new Point(1, 2);
Point p2 = new Point(1, 2);

// Inside a method:
boolean equal = Objects.equals(p1, p2); // true
```

`Objects.equals` uses the `equals` comparison provided by the record; with components like `int`, the result is component-wise equality. However, a record with an array component does not automatically deep-compare array contents just because it is wrapped in `Objects.equals`.

## 11. Common mistakes and fixes

1. **Writing `a.equals(b)` when `a` may be `null`.** When `a == null`, the call throws `NullPointerException`. Use `Objects.equals(a, b)` if two nullable references should be compared via `equals`.
2. **Using `==` to compare string contents.** `==` checks whether two references point to the same object. Use `Objects.equals(a, b)` or `String.equals` with a non-`null` receiver.
3. **Assuming `Objects.equals` compares every field of every object.** It only delegates to the first operand's `equals`. If the class keeps the default `Object.equals`, comparison may still be by identity.
4. **Assuming `Objects.equals(a, b)` calls both `a.equals(b)` and `b.equals(a)`.** There is no such step. The class must ensure symmetry itself.
5. **Treating `Objects.equals(a, a)` as a sufficient test for `a.equals(a)`.** The `a == b` shortcut prevents the object's `equals` method from being called.
6. **Using `Objects.equals` to compare arrays element-by-element.** For ordinary arrays, the result still depends on array identity. Use `Arrays.equals` or an appropriate deep API.
7. **Ignoring the two-`null` equality policy.** `Objects.equals(null, null) == true` is intentional behavior; if business rules require otherwise, add an explicit condition.
8. **Assuming null-safe means exception-safe.** A custom `equals` can throw an exception due to internal bugs, corrupted data, or wrong assumptions. `Objects.equals` does not swallow or automatically fix that exception.
9. **Confusing `Objects.equals` with `Objects.requireNonNull`.** One comparison method accepts `null`, while the other rejects `null` with an exception.

## 12. Self-check exercises

Predict the result of the following expressions. Assume they are inside a method that has imported `java.util.Objects` and `java.util.Arrays`:

```java
String s1 = null;
String s2 = null;
String s3 = "Hello";
String s4 = new String("Hello");

boolean q1 = Objects.equals(s1, s2);
boolean q2 = Objects.equals(s1, s3);
boolean q3 = Objects.equals(s3, s4);
boolean q4 = s3 == s4;

int[] a1 = {1, 2};
int[] a2 = {1, 2};
boolean q5 = Objects.equals(a1, a2);
boolean q6 = Arrays.equals(a1, a2);

Object same = new Object();
boolean q7 = Objects.equals(same, same);
```

**Answers:**

| Expression | Result | Explanation |
| --- | --- | --- |
| `q1` | `true` | Both are `null`, so `a == b` is true. |
| `q2` | `false` | The first argument is `null`, the second is non-`null`. |
| `q3` | `true` | `String.equals` compares the `"Hello"` content. |
| `q4` | `false` | String `s4` was created as a separate instance by `new`. |
| `q5` | `false` | Arrays do not automatically compare element-by-element in `Objects.equals`. |
| `q6` | `true` | `Arrays.equals` compares the elements of the two `int[]` arrays. |
| `q7` | `true` | The `a == b` branch recognizes the same object. |

**Extended practice:** modify the `Book` class in section 4 to add a nullable `String author` field. Update `equals` with `Objects.equals(author, other.author)` and update `hashCode` with `Objects.hash(id, title, author)`. Test two books with both `title` and `author` set to `null`; then change one value and check the result. The goal is to preserve the proper relationship between equality and hash code without dereferencing a `null` field.

## Key Takeaways

`Objects.equals(a, b)` is equivalent to the logic **`a == b || (a != null && a.equals(b))`**. It returns `true` when both are `null`, returns `false` when the first argument is `null` and the second is non-`null`, and delegates to `equals()` of **the first argument** when needed. It is a call-level null-safe comparison utility, not an automatic deep comparator or an `equals` contract repair tool. When working with arrays, numbers with custom comparison rules, or custom business objects, always choose the type's proper equality definition.