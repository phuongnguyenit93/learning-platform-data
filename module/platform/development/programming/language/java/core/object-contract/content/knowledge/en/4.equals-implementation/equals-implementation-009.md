# Implementing equals: Avoid Comparing via toString() or hashCode()

## 1. The Core Problem

When overriding **equals(Object)** in Java, the goal is to answer: *should two objects be considered the same value according to this class's rules?* That rule must be based on the attributes that constitute the object's equality meaning.

Two error-prone shortcuts are:

~~~java
// Wrong in design: using display string as the equality criterion.
return this.toString().equals(other.toString());

// Wrong in logic: treating matching hash codes as proof of equality.
return this.hashCode() == other.hashCode();
~~~

The snippets above **only illustrate wrong expressions** in a context where an `other` variable already exists, not complete methods. The issue does not lie in Java syntax, but in misusing the role of the methods:

| Method | Purpose | What is NOT guaranteed |
| --- | --- | --- |
| equals(Object) | Determines whether two objects are logically equal under the class's contract | Does not know business criteria on its own; the designer must define them |
| toString() | Produces a string representation for humans, logging, or debugging | Not guaranteed to be unique, complete, stable, or to accurately reflect `equals` criteria |
| hashCode() | Produces a hash integer to support structures like HashMap, HashSet | Not guaranteed that every distinct object or value has a distinct hash integer |

**Main rule:** compare fields carrying value meaning using equals/Objects.equals or a comparison suitable for the data type; implement a compatible hashCode based on those exact fields. Do not infer the result of equals backwards from display text or hash integers.

## 2. Why Not Use toString() to Decide equals?

### 2.1. Two different objects can print the exact same string

Suppose class Account has an account ID `id` and a display name `displayName`. The business requirement is **two Accounts are equal when they have the same id**. toString, however, is designed to print only the name:

~~~java
@Override
public String toString() {
    return "Account{name='" + displayName + "'}";
}
~~~

Account(id = "A-01", displayName = "Lan") and Account(id = "A-02", displayName = "Lan") both print the string Account{name='Lan'}, yet they are **not equal** by id. If equals compares the two toString strings, it falsely returns true.

Reason: human-readable text often omits attributes, masks sensitive data, rounds numbers, truncates lists, or picks a generic label. Those presentation choices are not equality criteria.

### 2.2. Two equal objects can print different strings

Account(id = "A-01", displayName = "Lan") and Account(id = "A-01", displayName = "Linh") share the same identifier so equals must be true under the chosen rule, even though their toString strings differ.

The displayName field can change at the user's discretion and **does not participate in equals**. If toString is used for comparison, editing the display name accidentally changes logical identity.

Neither direction holds:

- Having x.toString().equals(y.toString()) be true **does not imply** x.equals(y) is true.
- Having x.equals(y) be true **does not require** x.toString().equals(y.toString()) to be true.

### 2.3. toString is a presentation interface that can change

Changing log formatting from Account{name='Lan'} to Account(Lan), adding a timestamp, changing number/date formatting, changing language, or merely reordering fields in the string must not alter the meaning of equals. If equals depends on toString, a presentation tweak can turn into a logic bug in sets, data comparisons, or tests.

In addition, the default Object.toString returns a representation formatted as class name, the @ character, and the hex representation of hashCode (for classes that do not override toString). This string **is not a business identifier or uniqueness guarantee**, and the hex value should not be interpreted as a guaranteed memory address. Using the default toString as a comparison even indirectly suffers from the hashCode problem.

For Java arrays, calling toString directly is also not a content comparison; to compare elements, Arrays.equals or Arrays.deepEquals must be used according to structure.

## 3. Why Not Use hashCode() to Decide equals?

### 3.1. The contract is strictly one-way

Java specifies:

> If two objects are equal according to equals, they **must** have the same hashCode.

Written symbolically:

**x.equals(y) == true ⇒ x.hashCode() == y.hashCode().**

**The converse is false:** from equal hashCodes, **you cannot conclude** equals is true.

Reason: hashCode returns a 32-bit int value, whereas the set of object values can be much larger. A **hash collision** occurs when two different values share the same hashCode. This is normal, not evidence that two values are equal.

### 3.2. Collisions can be observed immediately with String

A well-known and reproducible example in Java:

~~~java
System.out.println("Aa".hashCode()); // 2112
System.out.println("BB".hashCode()); // 2112
System.out.println("Aa".equals("BB")); // false
~~~

The strings "Aa" and "BB" differ in content yet share the hash code 2112. If you write equals by only checking this.hashCode() == other.hashCode(), two objects using those two strings as identifiers can be falsely considered equal.

A check like the following can short-circuit some cases in a design with a correct and stable hashCode:

~~~java
if (hashCode() != other.hashCode()) {
    return false;
}
// Matching hashes still require comparing the actual fields.
~~~

That is only an illustrative snippet, not a complete equals method. That optimization is usually unnecessary for ordinary equals; calling hashCode can add overhead and increase complexity. Most importantly, **matching hashes are not enough to return true**.

### 3.3. HashMap/HashSet still distinguish colliding keys

HashMap and HashSet use hash values to assist lookup, while also having to use proper equality comparison to distinguish keys when collisions occur. Two distinct keys with the same hashCode **can still coexist separately** in a HashSet or HashMap.

If you define equals as “hashes are equal”, the broken equals itself will cause the collection to treat keys of different values as one. Tweaking the hashCode algorithm to “collide less” cannot turn hash comparison into a generally valid equals implementation.

## 4. Proper Implementation: Choose Identity Fields and Compare Directly

Consider the business rules for Account:

- The id field is non-null and serves as the **logical identity**.
- The displayName field is for display only; two accounts with the same id remain equal even with different display names.
- When overriding equals, the class also overrides hashCode using the exact id attribute.
- toString uses displayName to illustrate the independence between the display string and value comparison.
- Keeping fields final helps state used as hash keys stay stable after initialization.

Core template:

~~~java
@Override
public boolean equals(Object obj) {
    if (this == obj) {
        return true;
    }
    if (!(obj instanceof Account that)) {
        return false;
    }
    return id.equals(that.id);
}

@Override
public int hashCode() {
    return id.hashCode();
}
~~~

Here, Account is a final class so the instanceof check creates no symmetry issues between superclass and subclass. In an inheritance hierarchy that can override equals, object type policy, symmetry, and transitivity must be examined carefully; one formula must not be copied blindly across every class structure.

Use Objects.equals(a, b) when fields are allowed to be null, or call equals directly after guaranteeing non-null. With multiple fields participating in equality, compare **each relevant field** consistently and build hashCode from those fields. Do not include displayName in hashCode if equals does not use it: two Accounts with the same id but different displayName must have equal hashCodes.

## 5. Runnable Java 17+ Program and Exact Output

Save as file **EqualsWithoutShortcutsDemo.java**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class EqualsWithoutShortcutsDemo {
    public static void main(String[] args) {
        Account a = new Account("A-01", "Lan");
        Account b = new Account("A-02", "Lan");
        Account c = new Account("A-01", "Linh");

        System.out.println("Same text: " + a.toString().equals(b.toString()));
        System.out.println("Equals, different id: " + a.equals(b));
        System.out.println("Different text: " + !a.toString().equals(c.toString()));
        System.out.println("Equals, same id: " + a.equals(c));

        System.out.println("Aa hash: " + "Aa".hashCode());
        System.out.println("BB hash: " + "BB".hashCode());
        System.out.println("Strings equal: " + "Aa".equals("BB"));

        Account keyA = new Account("Aa", "First");
        Account keyB = new Account("BB", "Second");
        System.out.println("Same hash: " + (keyA.hashCode() == keyB.hashCode()));
        System.out.println("Equals, collision: " + keyA.equals(keyB));

        Set<Account> set = new HashSet<>();
        set.add(keyA);
        set.add(keyB);
        System.out.println("HashSet size: " + set.size());
    }

    static final class Account {
        private final String id;
        private final String displayName;

        Account(String id, String displayName) {
            this.id = Objects.requireNonNull(id);
            this.displayName = Objects.requireNonNull(displayName);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Account that)) {
                return false;
            }
            return id.equals(that.id);
        }

        @Override
        public int hashCode() {
            return id.hashCode();
        }

        @Override
        public String toString() {
            return "Account{name='" + displayName + "'}";
        }
    }
}
~~~

Run in the directory containing the file:

~~~bash
javac EqualsWithoutShortcutsDemo.java
java EqualsWithoutShortcutsDemo
~~~

Output:

~~~text
Same text: true
Equals, different id: false
Different text: true
Equals, same id: true
Aa hash: 2112
BB hash: 2112
Strings equal: false
Same hash: true
Equals, collision: false
HashSet size: 2
~~~

Interpretation by group:

1. **Same text: true** yet **Equals, different id: false** proves matching strings are not enough to conclude two Accounts are equal.
2. **Different text: true** yet **Equals, same id: true** proves differing display strings are also not enough to conclude two Accounts are different.
3. "Aa" and "BB" both have hash 2112, yet String.equals is false. The two corresponding Accounts also share the same hashCode and are not equal.
4. HashSet holds both **two** Accounts with different ids even though a hashCode collision occurred, because equals is properly built from id.

This is a complete standalone program. The short examples in earlier sections are illustrative excerpts only, so each fragment should not be compiled on its own.

## 6. Common Mistakes and How to Avoid Them

### Mistake A — comparing display strings instead of values

~~~java
// Do not do this: printed string does not fully represent logical equality.
return this.toString().equals(that.toString());
~~~

**How to fix:** identify the attributes that genuinely determine equality; compare those fields directly. In the Account example, use id.equals(that.id) after the type verification step.

### Mistake B — treating identical hashCodes as equal

~~~java
// Wrong: hash collisions cause false positives.
return this.hashCode() == that.hashCode();
~~~

**How to fix:** hashCode only assists hash-based partitioning/lookup; equals must inspect actual values. In particular, avoid using Objects.hash(...) as a “unique signature” to compare two objects.

### Mistake C — correct equals but mismatched hashCode

~~~java
// Wrong idea: equals uses only id while hashCode also uses displayName.
@Override
public int hashCode() {
    return Objects.hash(id, displayName);
}
~~~

If two Accounts share the same id but have different displayName, they are equal by equals yet can have different hashCodes, violating the mandatory contract. **How to fix:** compute the hash only from the fields used in equals, for example return id.hashCode();. This is an erroneous illustrative code snippet, not a standalone class.

### Mistake D — confusing equals with reference comparison

For String objects or value classes, the == operator asks whether two variables point to the **same object**. It does not substitute for value comparison:

~~~java
Objects.equals(left.id, right.id)
~~~

In cases where id is guaranteed non-null, left.id.equals(right.id) is also suitable. For primitive types such as int, use == to compare values; for arrays, use Arrays.equals or Arrays.deepEquals depending on structure. Choose the right comparison for each type instead of serializing through toString.

### Mistake E — mutating an identity field of a key currently stored in HashSet/HashMap

If a field participating in equals/hashCode is modified after the object is inserted as a key into a hash collection, lookup operations can fail because the original hash bucket is not automatically updated. The template above uses a final id field to avoid this common issue; keep in mind that final on a reference **does not** make a mutable object it points to immutable.

### Mistake F — thinking toString, hashCode, and equals must yield the same “identifier”

There is no contract requiring toString to contain all equal fields, match hashCode, or have identical content across objects considered equal. The real contract concerns **equals and hashCode**: equal ⇒ same hash. toString is a separate presentation responsibility.

## 7. Important Tests for Classes with Custom equals

With the choice “equal when sharing the same id”, both cases that break the two shortcuts must be covered:

| Case | Expected equals | What is verified |
| --- | --- | --- |
| Same id, different displayName | true | Different toString does not affect equality |
| Different id, same displayName | false | Identical toString does not create false equality |
| Different id but colliding hashCode | false | Hash collision does not create false equality |
| Same id, corresponding hashCode | Equal and same hashCode | The equals/hashCode contract |
| One reference compared to itself | true | Reflexivity |
| Any Account compared to null | false | The null condition |
| Swapping comparison order of two Accounts | Same result | Symmetry |
| Three Accounts with the same id | Transitive result | Transitivity |

A quick check for three immutable Accounts:

~~~java
Account x = new Account("A-01", "Lan");
Account y = new Account("A-01", "Linh");
Account z = new Account("A-02", "Lan");

if (!x.equals(y) || x.hashCode() != y.hashCode()) {
    throw new AssertionError("Same id must be equal and have the same hash");
}
if (x.equals(z)) {
    throw new AssertionError("Different id must not be equal");
}
~~~

This snippet is an example **placed within scope where the Account class is already declared**; in the full program in section 5, Account is nested inside EqualsWithoutShortcutsDemo, so this test snippet cannot be compiled as a standalone file. For real testing, place it in the same enclosing class/appropriate method or use a framework like JUnit. The checks in the table above must be combined to protect the entire contract, not just one test case.

With a Java record, the compiler can generate equals/hashCode/toString from the record components. That is convenient when **all components** genuinely match the desired equality definition; data components must still be designed according to domain semantics. Even though a record provides a generated toString, do not use that string result as a custom equals implementation.

## 8. Implementation Selection Process

1. **Define logical equality:** which identity key or full set of values makes two objects considered equivalent? For example, Account uses id.
2. **Check type and null:** comparing with itself returns true, incompatible type/null returns false; be careful with inheritance.
3. **Compare relevant fields directly:** use Objects.equals, value-type equals methods, Arrays.equals for arrays, or appropriate operators for primitives.
4. **Compute hashCode from the same data:** ensure that if equals is true then hashCode is equal, while accepting collisions between two different values.
5. **Keep toString for display:** editing logs/formatting must not accidentally alter equality results.
6. **Evaluate immutability and test:** especially cases with same text but different values, different text but same value, same hash but different values, symmetry, transitivity, and null.

**Key takeaway:** toString() produces a representation; hashCode() provides a hash integer that can collide; only **equals() based on meaningful attributes** determines whether two objects are logically equal.