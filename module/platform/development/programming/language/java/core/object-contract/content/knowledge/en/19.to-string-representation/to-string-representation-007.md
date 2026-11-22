# Do Not Use `toString()` to Determine `equals()` or `hashCode()`

## 1. Three Methods, Three Different Responsibilities

Every Java class inherits directly or indirectly from `java.lang.Object`. The three methods `toString()`, `equals(Object)`, and `hashCode()` can appear together in a class, yet **they do not serve the same purpose**:

| Method | Question It Answers | Where Typically Used |
| --- | --- | --- |
| `toString()` | How should the object be represented as a readable string? | Logs, debugging, display, diagnosis |
| `equals(Object)` | When are two objects considered logically equal? | Value comparison, `contains`, `HashSet`, `HashMap` |
| `hashCode()` | Which hash code is consistent with the object's equality relation? | Hash structures, `HashMap`, `HashSet` |

**Principle:** `toString()` is how an object is **presented**. `equals()` and `hashCode()` define the **equality and hashing contract**. You should not derive equality or hash codes from a string meant for presentation.

For example, an account has `id = "A-100"`, `displayName = "Minh"`. If the system treats `id` as the identifier, then two accounts with the same display name but different `id`s are **not equal**. Conversely, two records with the same `id` yet different display names can be considered the same logical account. Whatever information `toString()` prints must not alter these rules.

## 2. The Actual Contract of Each Method

### `Object.toString()`: String Representation, Not Identity

The default `Object.toString()` returns a string consisting of the class name, the `@` character, and the hex representation of the hash code returned by `hashCode()`. For instance, an illustrative string has the form:

```text
com.example.Customer@5e2de80c
```

The hex sequence above **is only a format example**, not a fixed output; there is no requirement that two different objects always have different default strings. Nor is the hash code **a memory address or unique ID**. A class can override `toString()` to return any suitable description, such as a display name, summary state, or fields convenient for logging.

The Java API does **not** stipulate that `toString()` is by default a canonical, immutable, unique representation, parseable back into an object, or always suitable as a data key. When upgrading application versions, developers can reasonably change the `toString()` format to improve logs.

### `Object.equals(Object)`: Logical Equality Rules

The default `Object.equals(Object)` considers two references equal only if they point to the same object. A value class can override it to compare business-meaningful components. For example, `String.equals()` compares string content, while a `Customer` class might compare customer IDs.

The `equals` contract requires:

1. **Reflexive:** `x.equals(x)` is `true` for non-`null` `x`.
2. **Symmetric:** `x.equals(y)` and `y.equals(x)` return the same result.
3. **Transitive:** if `x` equals `y` and `y` equals `z`, then `x` equals `z`.
4. **Consistent:** while relevant information does not change, the result does not change.
5. **Non-null:** `x.equals(null)` is `false`.

Override with the exact signature `public boolean equals(Object obj)` and place `@Override`. `equals(MyType)` is merely an overload in ordinary cases and does not replace the `Object.equals(Object)` contract.

### `Object.hashCode()`: Must Match `equals`

Mandatory rule:

```text
x.equals(y) == true  =>  x.hashCode() == y.hashCode()
```

The converse is not required: two objects with the same hash can still be unequal (hash collision). While the fields used in `equals` do not change, `hashCode` must also remain stable within a single run of the application.

**There is no rule requiring the `toString()` of two equal objects to be identical.** Bringing `toString()` into `equals/hashCode` risks accidentally turning a display change into an identity change.

## 3. Why Comparing `toString()` Easily Goes Wrong

Suppose `User.toString()` only displays the user's name. Two distinct accounts with the same name `"An"` can produce **identical strings**. If you write:

```java
@Override
public boolean equals(Object obj) {
    return obj instanceof User other
            && toString().equals(other.toString());
}
```

This is an **illustrative snippet placed inside class `User`**, not a standalone program. The bug is not in string-comparison syntax: the bug is that **the display string does not accurately represent business identity**.

Common causes:

- **Missing information:** `toString()` only prints a name, a few fields, or a summary. Two different objects can produce the same string.
- **Extra information:** `toString()` prints an update timestamp, cache, debug flag, or transient state even though those data do not participate in equality.
- **Format changes:** adding prefixes, separators, reordering fields, localizing dates/times, or masking sensitive data can change the string without changing logical value.
- **No uniqueness guarantee:** two unequal objects are not forced to have two different `toString()` values; two equal objects are also not forced to have identical strings.
- **Resource cost or side effects:** a `toString()` implementation might traverse large structures, call other methods, or even be affected by external state. Hash codes should be designed around the state used for equality, not presentation work.

Even if `toString()` happens to contain enough fields in the current version, a refactoring meant solely to change log formatting can break lookup and comparison logic. This is a kind of dependency that is hard to spot in code review.

## 4. Java 17+ Example: Using `toString` Leads to Confusing Accounts

Create the file `BadToStringEqualityDemo.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class BadToStringEqualityDemo {
    static final class Account {
        private final String accountId;
        private final String displayName;

        Account(String accountId, String displayName) {
            this.accountId = accountId;
            this.displayName = displayName;
        }

        @Override
        public String toString() {
            return displayName; // For display only.
        }

        @Override
        public boolean equals(Object obj) {
            return obj instanceof Account other
                    && toString().equals(other.toString()); // Wrong for business logic.
        }

        @Override
        public int hashCode() {
            return toString().hashCode(); // Depends on display string.
        }
    }

    public static void main(String[] args) {
        Account a = new Account("A-100", "Minh");
        Account b = new Account("B-200", "Minh");
        Account c = new Account("A-100", "Minh new");

        System.out.println(a.equals(b));
        System.out.println(a.equals(c));

        Set<Account> unique = new HashSet<>();
        unique.add(a);
        unique.add(b);
        unique.add(c);
        System.out.println(unique.size());

        Map<Account, String> balances = new HashMap<>();
        balances.put(a, "old");
        balances.put(b, "new");
        System.out.println(balances.size());
        System.out.println(balances.get(a));
    }
}
```

Compile and run:

```bash
javac BadToStringEqualityDemo.java
java BadToStringEqualityDemo
```

Output:

```text
true
false
2
1
new
```

**Explanation:**

1. `a` and `b` have different account IDs but both print `"Minh"`. The faulty `equals` returns `true`; `HashSet` treats them as one element and `HashMap` treats them as one key.
2. `a` and `c` have the same ID `"A-100"` but different display names, so the faulty `equals` returns `false`.
3. The set ends up with two elements because it merges `a` with `b` while keeping `c`. For the map, `put(b, "new")` replaces the value associated with logical key `a`, so `get(a)` returns `"new"`.

Note on correctness: this implementation **can still satisfy the formal laws** of `equals` when display names are immutable, because it compares `String` and hashes by `String`. What is wrong is that **the equality definition does not match business requirements**: the account ID was ignored. Calling `equals(toString())` does not automatically violate symmetry or transitivity; the bug is picking the wrong data source and making the contract depend on presentation.

## 5. The Right Way: Compare the Identity-Defining Fields and Hash from Those Same Fields

If an account is identified by `accountId`, use that exact field in `equals` and `hashCode`. `toString` is free to display the name, ID, or another summary independently of equality.

Create the file `GoodAccountEqualityDemo.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class GoodAccountEqualityDemo {
    static final class Account {
        private final String accountId;
        private final String displayName;

        Account(String accountId, String displayName) {
            this.accountId = Objects.requireNonNull(accountId);
            this.displayName = Objects.requireNonNull(displayName);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Account other)) {
                return false;
            }
            return accountId.equals(other.accountId);
        }

        @Override
        public int hashCode() {
            return accountId.hashCode();
        }

        @Override
        public String toString() {
            return "Account{id=" + accountId
                    + ", displayName=" + displayName + "}";
        }
    }

    public static void main(String[] args) {
        Account a = new Account("A-100", "Minh");
        Account b = new Account("B-200", "Minh");
        Account c = new Account("A-100", "Minh new");

        System.out.println(a.equals(b));
        System.out.println(a.equals(c));
        System.out.println(a.toString().equals(c.toString()));

        Set<Account> unique = new HashSet<>();
        unique.add(a);
        unique.add(b);
        unique.add(c);
        System.out.println(unique.size());

        Map<Account, String> balances = new HashMap<>();
        balances.put(a, "old");
        balances.put(c, "updated");
        System.out.println(balances.size());
        System.out.println(balances.get(a));
    }
}
```

Run commands:

```bash
javac GoodAccountEqualityDemo.java
java GoodAccountEqualityDemo
```

Output:

```text
false
true
false
2
1
updated
```

In the correct version:

- `a` and `b` share the same name but have different `accountId`s, so `equals` returns `false`.
- `a` and `c` share the same `accountId`, so `equals` returns `true`, even though `toString()` differs because the display names differ.
- `hashCode` relies solely on `accountId`, matching the equality definition; equal objects have the same hash.
- `HashSet` keeps the two logical accounts `A-100` and `B-200`. `HashMap` treats `a` and `c` as the same logical key and updates the value to `"updated"`.

`Account` in the example is a `final` class, `accountId` is `final`, and `String` is immutable. This keeps the hash code stable while the object sits in a set or acts as a map key. Choosing a single field as identity is a **business assumption of the example**; in real applications, determine the natural key, composite key, or full set of value fields as appropriate.

## 6. A Dependency Cycle That Easily Causes `StackOverflowError`

A specific risk arises when a developer uses `toString()` to compute `hashCode()`, and then uses `hashCode()` inside `toString()`:

```java
@Override
public String toString() {
    return "Node#" + hashCode();
}

@Override
public int hashCode() {
    return toString().hashCode();
}
```

This is a **faulty code snippet illustrated inside a `Node` class**, not a standalone program. `hashCode()` calls `toString()`, and `toString()` calls `hashCode()` back without a base case. When executed, the recursion leads to `StackOverflowError` instead of a useful hash code.

Even the default `Object.toString()` involves `hashCode()` in its hex representation, so converting an object to a string cannot be treated as a neutral operation for redefining `hashCode`. Separate the methods by responsibility right from the design stage.

## 7. When `toString` Changes or Display State Is Mutable

Suppose an object holds an immutable customer ID while its display name can be edited. If `hashCode()` is computed from a `toString()` that contains the name, then after editing the name:

1. The object is sitting in the old hash bucket in a `HashSet` or `HashMap`.
2. Calling `hashCode()` again may return a different number.
3. `contains`, `remove`, or `get` may search the new bucket and miss the stored object.

This bug is hard to track down because the object still exists in the collection, yet lookups stop working as expected.

**How to prevent it:** use immutable and stable state for fields participating in equality/hashing. If a logical key must change, remove the element or map entry **before mutating state**, then update and re-insert; or create a new immutable key object.

A completely harmless presentation-layer change, such as changing `toString()` from `"A-100"` to `"Account A-100"`, must never alter the object's identity or hash code in a proper design.

## 8. What If a String Itself Is the Business Value?

Using string data is not always wrong. **If the business identifier truly is a string**, such as `accountId` or a normalized code, compare the **identifier string field** directly:

```java
return accountId.equals(other.accountId);
```

and use:

```java
return accountId.hashCode();
```

The two snippets above illustrate method bodies inside an `Account` class that has already checked the type of `other`, not standalone programs.

If designing a wrapper type for a normalized string, express the normalization rule with a clearly named component or method (for example `normalizedKey()`), and ensure `equals/hashCode` always apply that same criterion. Do not use `toString()` as a "shortcut" because its conventional meaning is merely **display**.

Similarly, JSON, XML, or CSV strings used for data exchange should be produced by a **serializer with a defined format and version**, rather than treating `toString()` as a canonical data representation by default. If you need a stable cache key, build the key from data normalized under an explicit schema. These considerations remain separate from the object contract that `equals/hashCode` upholds.

## 9. How Do Java Records Help and What Should You Watch Out For?

For simple value data types, Java 17 `record` auto-generates `equals(Object)` and `hashCode()` based on the record components.

```java
record Coordinate(int x, int y) {}
```

This is a standalone type declaration that can be placed at top-level scope in `Coordinate.java`. Two `Coordinate(1, 2)` instances with the same component values will be equal and have compatible hash codes, even though they are not the same object. Java also provides a `toString()` describing components, but **does not use that string as the basis for equality**.

If a record component is a mutable list or object, the record only holds the **reference** in a `final` field; it does not automatically create deep immutability. Users still need to ensure data participating in equality is not mutated while the record acts as a key in a hash structure.

Another note: if business identity depends solely on an `id` code, while the record also holds `displayName`, auto-generating equality across **all components** may not fit. In that case, redesign the data model, use a value object holding only the identity key, or define equality manually according to the business contract.

## 10. Misconceptions to Avoid

| Misconception | Reality and How to Handle It |
| --- | --- |
| "Two identical `toString()` values mean the two objects are equal." | Display strings can omit distinguishing info; use a properly defined `equals`. |
| "Two equal objects must have identical `toString()` values." | There is no such requirement in `Object.equals`; display details may differ. |
| "Having the same hash means it's the same object." | Hash collisions are valid; `equals` determines equality. |
| "`Object.toString()` gives the object's unique ID." | The default representation is hash-based, with no uniqueness or out-of-contract stability guarantee. |
| "Using `toString()` as the hash is easy to maintain." | Changing the display format can change the hash; hash from the fields participating in `equals`. |
| "Having `equals(MyType)` is enough for HashMap." | That is usually an overload; you must properly override `equals(Object)`. |
| "Records make all data inside immutable." | Records do not automatically make referenced mutable objects deeply immutable. |
| "Equal display names mean the same entity." | That depends on the business identity definition; usually a stable ID is needed. |

## 11. Checklist When Designing the Object Contract

1. **Define the type's identity or logical value** first: which fields determine that two objects are equal?
2. **Override `equals(Object)`** using those exact fields; handle `null`, incompatible types, and symmetry/transitivity conditions.
3. **Override `hashCode()`** using the same fields participating in `equals`; two equal objects must have the same hash code.
4. **Write `toString()` for human readers**: useful enough for debugging, avoiding exposing secrets, yet never using it as the source of truth for identity/equality.
5. **Prefer immutable fields** for identity/hashing, especially when the object is a `HashMap` key or `HashSet` element.
6. **Test the three methods independently**: two objects with the same ID but different display names; two objects with different IDs but the same name; changing `toString()` format must not change `equals/hashCode`.
7. **Test through collections**: `HashSet.add` and `HashMap.put/get` must deduplicate or update by business identity, not by display string.
8. **Avoid recursive call cycles** between `toString`, `hashCode`, and the methods they depend on.
9. **If a canonical representation is needed**, create a serializer or `canonicalKey()` with its own contract and format-stability tests; do not mix it with the diagnostic `toString` method.

**Self-check:**

- Must two accounts with different IDs but the same display name be equal? **No.**
- Can two accounts with the same ID but different `toString()` formats be equal? **Yes**, if ID is the equality criterion.
- May changing log content in `toString()` change `hashCode()`? **No**, when the fields participating in equality do not change.
- When must `hashCode()` match between two objects? **When their `equals()` returns `true`.**
- To get a canonical string key for caching, should you use an arbitrary `toString()` or create a `canonicalKey()` with a clear contract? **Create a canonical key with a separate definition and tests.**

**Key takeaway:** `toString()` answers "what does the object look like when printed"; `equals()` and `hashCode()` answer "which objects represent the same logical value". Build equality/hashing from stable business components so that UI or log changes never silently alter the object's contract.