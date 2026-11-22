# Checking `null` and Object Type Before Reading Data in `equals()`

## Objectives

When overriding `equals(Object obj)`, the argument has declared type `Object`: a call can pass in an object of the same type, an object of a different type, or `null`. Therefore, before reading the argument's fields and comparing data, you must ensure that the argument is **non-`null` and of an appropriate type**. After this lesson, you will be able to:

- Explain why accessing fields or casting too early causes `NullPointerException` or `ClassCastException`.
- Write the correct order of checking reference identity, `null`, and type before reading data in `equals()`.
- Distinguish between checking with `getClass()` and `instanceof`, and know the impact of inheritance on symmetry.
- Use `Objects.equals()` to compare nullable reference fields, without confusing it with the argument type-checking step.
- Verify `equals()` on same reference, two objects with the same data, `null`, different type, and different data.

## 1. Why Check Before Reading Fields?

The method overridden with the correct signature is:

```java
@Override
public boolean equals(Object obj) {
    // Decide whether the current object equals obj.
}
```

`obj` has declared type `Object`. The compiler cannot assume that `obj` always belongs to the class implementing `equals()`. For instance, a `Contact` object can perfectly well receive calls like `contact.equals("hello")` or `contact.equals(null)`; the comparison must return `false` under the `equals` contract in these two situations.

The snippet below is **wrong and only illustrates the bug**, not a method to use:

```java
@Override
public boolean equals(Object obj) {
    Contact other = (Contact) obj;       // Casting before checking
    return id == other.id;               // Reading data immediately
}
```

There are two independent risks:

1. If `obj` is an object that cannot be cast to `Contact` (for example `String`), the cast throws `ClassCastException`.
2. If `obj == null`, the cast `(Contact) null` still yields `null`; the error occurs when accessing `other.id`, causing `NullPointerException`.

Another wrong way of writing it is calling `obj.getClass()` immediately. If `obj` is `null`, calling a method on `null` causes `NullPointerException`.

**Principle:** `equals()` should not throw an exception just because the argument is `null` or of an unrelated type. Confirm validity conditions before accessing class-specific data.

## 2. Safe Checking Order with `getClass()`

A common pattern, suitable when the equality policy requires **the exact same runtime class**, is:

```java
@Override
public boolean equals(Object obj) {
    if (this == obj) {
        return true;
    }
    if (obj == null || getClass() != obj.getClass()) {
        return false;
    }

    Contact other = (Contact) obj;  // Safe cast after checking
    return id == other.id
            && java.util.Objects.equals(email, other.email);
}
```

Explanation of the sequence:

1. **`this == obj`:** same reference means same object, return `true` immediately; this is a common optimization and expresses reflexivity (`x.equals(x)` must be `true` for a non-null object).
2. **`obj == null`:** if the argument does not exist, return `false`. `this` itself cannot be `null` while an instance method is validly executing.
3. **`getClass() != obj.getClass()`:** rejects objects with a different actual runtime class, including other classes with identically named fields.
4. **Cast `(Contact) obj`:** after passing the class check, we can use the `Contact` type to read fields.
5. **Compare data:** for `id` of type `int`, use `==` to compare primitive values; for `email` of type `String` which can be `null`, use `Objects.equals` to compare content safely with `null`.

The expression `obj == null || getClass() != obj.getClass()` relies on **short-circuiting** (`||`): when the left-hand side is `true`, Java **does not evaluate** the right-hand side. Thanks to this, `obj.getClass()` is only called when `obj` is guaranteed not to be `null`.

The cast line is only safe because the preceding condition has guaranteed the argument has the exact required class. If the type-checking condition is changed, the validity of the cast must also be re-examined.

## 3. Complete Java 17+ Example

Save to the file `EqualityGuardsDemo.java`. The `Contact` class is declared `final`, has two data fields, and overrides both `equals` and `hashCode`.

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class EqualityGuardsDemo {
    static final class Contact {
        private final int id;
        private final String email;

        Contact(int id, String email) {
            this.id = id;
            this.email = email;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (obj == null || getClass() != obj.getClass()) {
                return false;
            }

            Contact other = (Contact) obj;
            return id == other.id
                    && Objects.equals(email, other.email);
        }

        @Override
        public int hashCode() {
            return Objects.hash(id, email);
        }
    }

    public static void main(String[] args) {
        Contact a = new Contact(7, "a@example.com");
        Contact b = new Contact(7, "a@example.com");
        Contact c = new Contact(7, "b@example.com");
        Contact n1 = new Contact(9, null);
        Contact n2 = new Contact(9, null);

        System.out.println("same reference: " + a.equals(a));
        System.out.println("same values: " + a.equals(b));
        System.out.println("null candidate: " + a.equals(null));
        System.out.println("other type: " + a.equals("7"));
        System.out.println("different email: " + a.equals(c));
        System.out.println("both email null: " + n1.equals(n2));

        Set<Contact> contacts = new HashSet<>();
        contacts.add(a);
        contacts.add(b);
        System.out.println("HashSet size: " + contacts.size());
    }
}
```

Compile and run on JDK 17 or newer:

```bash
javac EqualityGuardsDemo.java
java EqualityGuardsDemo
```

Output:

```text
same reference: true
same values: true
null candidate: false
other type: false
different email: false
both email null: true
HashSet size: 1
```

Output explanation:

- `a.equals(a)` returns `true` immediately from the same-reference check.
- `a.equals(b)` returns `true` because they are two different objects with the same `id` and `email`. This differs from `a == b`, which is `false`.
- `a.equals(null)` returns `false` at the `null` check step.
- `a.equals("7")` returns `false` at the class check step; it does not attempt to cast `String` to `Contact`.
- `a.equals(c)` returns `false` because `email` differs.
- `n1.equals(n2)` returns `true` because the two objects have equal `id` and both `email` values are `null`; `Objects.equals(null, null)` returns `true`.
- `HashSet` keeps only one element from `a` and `b` because `equals` determines they are equal and `hashCode` is consistent.

The example intentionally uses `final class Contact`, so there are no subclasses of `Contact` making type-checking rules more complex.

## 4. Another Approach: `instanceof` and Pattern Matching

With Java 17+, you can combine the `null` check, type check, and creation of a properly typed variable using **pattern matching for `instanceof`**:

```java
@Override
public boolean equals(Object obj) {
    if (this == obj) {
        return true;
    }
    if (!(obj instanceof Contact other)) {
        return false;
    }
    return id == other.id
            && java.util.Objects.equals(email, other.email);
}
```

This is **an alternative** for the `equals` method body of the `Contact` class in the previous example, not a standalone Java program.

The expression `obj instanceof Contact other` only succeeds if `obj` is not `null` and the object is compatible with `Contact`. In the remaining branch after `return false`, the variable `other` has type `Contact` and is guaranteed by the compiler to be properly assigned. There is no need to call `getClass()`, no need for an explicit cast, and no need to write an extra `obj != null`.

With `Contact` declared `final` in the example above, both strategies accept objects of the same class and reject `null` or other types. But if a class **can be subclassed**, the two strategies no longer share the same policy:

- `getClass() == obj.getClass()` requires **the exact same runtime class**. A superclass object and a subclass object will be treated as different, even when the subclass inherits all fields.
- `obj instanceof Base` accepts objects of type `Base` **and subclasses** of `Base`. This can be useful if all objects in the hierarchy truly follow the same equality definition.
- If a subclass adds fields or writes `equals` with a different rule from the superclass, careless use of `instanceof` can break **symmetry** or **transitivity** of `equals`.

Example of design risk (illustrative pseudocode, not standalone runnable Java): if superclass `Base.equals(child)` only checks the `id` field, while `Child.equals(base)` requires the other side to also be a `Child`, it can happen that `base.equals(child) == true` while `child.equals(base) == false`. This is a violation of the `equals` contract.

Therefore, choosing between `getClass` and `instanceof` is a choice of **equality policy for the entire hierarchy**, not merely a syntax difference. For a `final` immutable value class, both approaches are usually simple and easy to reason about. For entities with proxies or special inheritance models, consider the equality contract specific to the type and library being used.

### Java Before Pattern Matching

Classic code also checks safely with `instanceof` before casting:

```java
if (!(obj instanceof Contact)) {
    return false;
}
Contact other = (Contact) obj;
// Only read other.id, other.email after this step.
```

This is an illustrative method body snippet. For `null`, the `instanceof` check returns `false`, so no separate `obj == null` check is needed in this branch.

## 5. Avoid Confusing “Non-`null` Argument” with “Non-`null` Internal Fields”

Checking `obj != null` only guarantees that the **argument object itself** exists. After a valid cast, internal reference fields can still be `null`.

For example, with a `Contact` object that has `email == null`, the following statement is unsafe:

```java
return email.equals(other.email); // email == null causes NullPointerException
```

Ways to handle this depending on the field's contract:

- If `email` can be `null` and two `null` values are considered equal: `Objects.equals(email, other.email)`.
- If `email` must be non-`null`: check the condition in the constructor using `Objects.requireNonNull(email)` and maintain that invariant; afterward you can call `email.equals(other.email)`.
- If array elements need to be compared: consider `Arrays.equals` or `Arrays.deepEquals` matching the data structure. `Objects.equals` on two arrays still uses the array's default `equals()`, which is array identity comparison.

`Objects.equals(a, b)` behaves equivalently in meaning to `a == b || (a != null && a.equals(b))`. This method **does not check beforehand** that two objects are of the expected type for your `equals` implementation, nor does it automatically choose equality criteria for fields. It only assists in comparing two nullable values.

Note the distinction between two calls:

```java
Contact contact = null;

// contact.equals(new Contact(1, null)); // Throws NullPointerException
boolean safe = java.util.Objects.equals(
        contact, new Contact(1, null));   // false
```

This is an illustrative snippet that must be placed in a method with access to the `Contact` class. When the left side of `equals` is `null`, you cannot call an instance method. However, you can still use `Objects.equals` to compare two nullable reference variables.

## 6. Why Does Condition Order Matter?

Consider four ways of writing inside the body of `equals(Object obj)`, with the current class being `Contact`:

| Check expression | When `obj == null` | When `obj` is a different type | Conclusion |
| --- | --- | --- | --- |
| `obj == null || getClass() != obj.getClass()` | Right side does not run; returns `false` | Returns `false` when classes differ | Safe |
| `!(obj instanceof Contact)` | `instanceof` yields `false`; returns `false` | Returns `false` | Safe; subclass-acceptance policy differs from `getClass` |
| `getClass() != obj.getClass() || obj == null` | Throws `NullPointerException` before reaching the `null` check | May return `false` | Wrong order |
| `Contact other = (Contact) obj;` then read fields | May throw `NullPointerException` when reading fields | May throw `ClassCastException` right at the cast | Missing checks |

Sometimes learners add a redundant condition:

```java
if (obj != null && obj instanceof Contact other) {
    // ...
}
```

This condition is valid, but `obj != null` is **unnecessary**, because `null instanceof Contact` is already `false`. When the requirement is simply to guard against `null` and wrong types, a clear `instanceof` pattern is sufficient. However, never use only `obj != null` and then cast: checking existence does not prove the object belongs to the right class.

## 7. Placing the Checks Within the `equals()` Contract

A correct `equals` implementation must follow the main properties for non-`null` references:

1. **Reflexive:** `x.equals(x)` must be `true`.
2. **Symmetric:** `x.equals(y)` and `y.equals(x)` must yield the same result.
3. **Transitive:** if both `x.equals(y)` and `y.equals(z)` are `true`, then `x.equals(z)` must also be `true`.
4. **Consistent:** when the information participating in the comparison does not change, the result of repeated calls must remain stable.
5. **Non-`null`:** `x.equals(null)` must be `false`.

Checking `this == obj` helps optimize the reflexive case; checking `null` and type helps enforce the fifth requirement and handle wrong-type arguments. However, **they are not enough to guarantee the entire contract**: the field comparison expression and subclass policy must also be designed consistently.

When overriding `equals`, you must usually override `hashCode` to ensure: if `a.equals(b)` is `true`, then `a.hashCode() == b.hashCode()`. The converse is not required. This is why the complete example overrides `hashCode` based on the exact `id` and `email` used in `equals`.

For data used as keys in a `HashMap` or elements of a `HashSet`, prefer immutable fields for computing `equals/hashCode`. If these fields change after insertion into a hash-based collection, looking up or removing elements can yield confusing results.

## 8. Type Checking with `getClass()` Does Not Replace Defining Equality Rules

Two objects of the exact same class are not necessarily equal. For example:

```java
Contact first = new Contact(5, "a@example.com");
Contact second = new Contact(5, "b@example.com");

// first.getClass() == second.getClass() is true,
// but first.equals(second) must be false by the id + email rule.
```

The snippet above is illustrative code placed within access scope of `Contact`. Type checking only allows the program to **safely proceed to the step of reading fields**. Determining the final result lies in which fields constitute equality.

Conversely, objects of different classes do not necessarily have the same field names or data structures. Do not try to force a cast or use reflection to read fields of a differently typed object just to “make them comparable”; an ordinary `equals` should properly express the contract of the class being implemented.

**Regarding proxies:** Some frameworks may dynamically generate subclasses for domain objects. In that case, the `getClass() != obj.getClass()` condition may reject comparisons with a proxy, even though from a business perspective the author expects the two objects to be equivalent. This issue needs to be addressed in **the specific type/framework's equals contract design**, and cannot be fixed by deleting all type-checking steps.

## 9. Common Mistakes

**Mistake 1 — Casting before checking.** The line `Contact other = (Contact) obj` at the start of the method can throw `ClassCastException`. Check the type before casting.

**Mistake 2 — Touching `obj` before checking `null`.** `obj.getClass()` or `obj.toString()` will throw `NullPointerException` when the argument is absent. Put `obj == null` first, or use `instanceof` to cover the `null` case.

**Mistake 3 — Checking only `null` and skipping the type.** `obj != null` does not guarantee `obj` can be cast to the desired class.

**Mistake 4 — Checking the type and then calling `equals()` on a nullable field.** A valid argument does not mean all fields are valid to call methods on. Use `Objects.equals` or enforce invariants in the constructor.

**Mistake 5 — Adding a `equals(Contact other)` method instead of overriding `equals(Object obj)`.** This is an **overload**, not an override; Java collections still use `equals(Object)`. Use `@Override` and the right signature so the compiler catches mistakes.

**Mistake 6 — Arbitrarily replacing `getClass()` with `instanceof` in a class hierarchy.** The two approaches have different inheritance policies. Consider symmetry and transitivity before deciding.

**Mistake 7 — Overriding `equals` while forgetting `hashCode`.** Objects equal by `equals` can misbehave in hash-based structures if `hashCode` is inconsistent.

## 10. Self-Check Exercise

Assume `Contact` is a `final` class and `equals()` is implemented as in the example in section 3. Predict the results:

```java
Contact a = new Contact(1, "x@example.com");
Contact b = new Contact(1, "x@example.com");
Contact c = new Contact(1, null);
Contact d = new Contact(1, null);
Object other = "x@example.com";

boolean q1 = a.equals(a);
boolean q2 = a.equals(b);
boolean q3 = a.equals(null);
boolean q4 = a.equals(other);
boolean q5 = c.equals(d);
boolean q6 = a == b;
```

The code snippet above is placed inside a method that can access `Contact`.

**Answers:** `q1 = true` (same reference); `q2 = true` (same type and fields have the same values); `q3 = false` (`null` argument); `q4 = false` (different type); `q5 = true` (equal `id` and both `email` values are `null`); `q6 = false` (two `new` calls create two different objects).

Try two more modifications:

- Remove the `obj == null` check from the `getClass()` template and call `a.equals(null)`: an error will occur when calling `obj.getClass()`.
- Replace `Objects.equals(email, other.email)` with `email.equals(other.email)` and then call `c.equals(d)`: an error will occur because `c.email == null`.

These two modifications clearly distinguish **argument safety** from **compared-field safety**. They are two distinct responsibilities in an `equals` implementation.

## Key Takeaway

In `equals(Object obj)`, the safe order is: **check same reference → reject `null` and incompatible types → cast when needed → read and compare fields**. With Java 17+, pattern matching for `instanceof` can combine rejecting `null`, verifying the type, and creating a properly typed variable. Choose `getClass()` or `instanceof` based on the equality contract and inheritance policy; finally, ensure null-safe field comparisons and a matching `hashCode`.