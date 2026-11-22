# Comparing with null Must Return false — The equals(Object) Contract

## 1. Rule and Scope

In Java, the java.lang.Object class specifies that: **for any non-null reference x, the expression x.equals(null) must return false**. This is a formal clause in the contract of the equals(Object) method, alongside reflexivity, symmetry, transitivity, and consistency.

Meaning: null represents the absence of an object reference; it is not an object that can be equal to an existing object. Regardless of whether a class defines equality by identifier, business data, or full state, null must never be considered equal to a non-null object.

Distinguish three cases:

| Expression | Result | Reason |
| --- | --- | --- |
| x.equals(null), with non-null x and proper implementation | false | The "non-nullity" clause of equals |
| x.equals(y), with both x and y non-null | Depends on the class's equality rule | Checks data or identity per the contract |
| missing.equals(x), with missing == null | Throws NullPointerException | Cannot invoke an instance method on a null reference |

The rule speaks only about a **null argument when the receiver object is non-null**. It does not mean every comparison involving null must return false: two references that are both null can be deemed "equally absent" by a utility function.

## 2. Correct and Safe Implementation of equals(Object)

In Java 17+, the instanceof type check has a very useful property: **null instanceof SomeType is always false**. Therefore, checking the type before reading object properties both satisfies the null clause and handles arguments of different types.

~~~java
import java.util.Objects;

public class EqualsNullDemo {
    static final class Account {
        private final String number;

        Account(String number) {
            this.number = Objects.requireNonNull(number, "number");
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof Account account)) {
                return false; // Includes other == null
            }
            return number.equals(account.number);
        }

        @Override
        public int hashCode() {
            return number.hashCode();
        }
    }

    public static void main(String[] args) {
        Account a = new Account("A1");
        Account same = new Account("A1");
        Account different = new Account("B2");
        Account missing = null;
        String status = null;

        System.out.println("a.equals(null): " + a.equals(null));
        System.out.println("a.equals(same): " + a.equals(same));
        System.out.println("a.equals(different): " + a.equals(different));
        System.out.println("Objects.equals(a, null): " + Objects.equals(a, null));
        System.out.println("Objects.equals(null, null): " + Objects.equals(null, null));
        System.out.println("constant.equals(status): " + "READY".equals(status));
        System.out.println("missing == null: " + (missing == null));
    }
}
~~~

Save as **EqualsNullDemo.java**, then run on JDK 17 or later:

~~~bash
javac EqualsNullDemo.java
java EqualsNullDemo
~~~

Expected output:

~~~text
a.equals(null): false
a.equals(same): true
a.equals(different): false
Objects.equals(a, null): false
Objects.equals(null, null): true
constant.equals(status): false
missing == null: true
~~~

Step-by-step explanation in the exact order equals executes:

1. When other points to a itself, `this == other` returns true; this ensures reflexivity.
2. When other is null, `this == other` is false; `instanceof` also returns false, so the method stops safely.
3. When other is another Account, comparing number determines whether the two objects are equal.
4. Overriding hashCode is contractually mandatory when overriding equals: equal objects must have the same hashCode value. In the example, the same number always leads to the same hashCode.

Because Account is final, there are no subclasses causing disagreement over equality rules. In a design allowing inheritance, you must deliberately consider the type comparison policy and symmetry: choosing instanceof vs. getClass() can affect compatibility between superclass and subclass, but **does not change** the rule that a null argument must return false.

Another valid implementation is to perform an explicit null check first:

~~~java
@Override
public boolean equals(Object other) {
    if (other == null) {
        return false;
    }
    if (this == other) {
        return true;
    }
    if (!(other instanceof Account account)) {
        return false;
    }
    return number.equals(account.number);
}
~~~

This is a **replacement snippet for the equals method alone inside the Account class above**, not a standalone Java program. The `other == null` branch makes the contract easy for readers to spot; in this case it is technically unnecessary because instanceof already handles null. If the field used as the equality key allows null, you can use `Objects.equals(number, account.number)` instead of `number.equals(account.number)` to compare the field safely.

## 3. equals(Object) Differs from Objects.equals(a, b)

**Objects.equals(a, b)** is a static utility method for comparing two potentially null references. Behaviorally, it is equivalent to:

~~~java
return a == b || (a != null && a.equals(b));
~~~

This is an **illustrative expression showing the logic body of the utility method**, not a self-contained runnable method. When both arguments are null, `a == b` returns true. When only one argument is null, the result is false. If `a` is non-null and the two references are not identical, the utility calls `a.equals(b)`.

Therefore:

- **new Account("A1").equals(null)** → false: an object is not equal to null.
- **Objects.equals(new Account("A1"), null)** → false: only one reference is null.
- **Objects.equals(null, null)** → true: both references are null, without calling equals on null.
- **"READY".equals(status)** when `status == null` → false: a safe comparison idiom when a constant string is on the left.

There is no contradiction between `Objects.equals(null, null)` returning true and the contract of `Object.equals(Object)`: the contract clause applies only to method calls on a **non-null** object.

When you only want to check whether a reference is absent, write **value == null** or **value != null** for clarity. When comparing equality between two potentially null references, use `Objects.equals(left, right)`; when certain the receiver object is non-null, you can use `receiver.equals(value)`.

## 4. Common Mistakes

### 4.1. Returning true for a null Argument

~~~java
@Override
public boolean equals(Object other) {
    if (other == null) {
        return true; // Violates the equals contract
    }
    // ... compare remaining fields
}
~~~

This is **buggy illustrative code**, not a standalone runnable example. Even if a class treats absent data fields as equivalent, an existing object must still never equal the null reference itself. Return false and compare data only after checking the type.

### 4.2. Casting or Accessing Fields Before Checking for null

~~~java
@Override
public boolean equals(Object other) {
    Account account = (Account) other;
    return number.equals(account.number);
}
~~~

This is also **buggy illustrative code** inside Account. When `other == null`, the cast still produces null, and accessing `account.number` throws a NullPointerException. When `other` is an object of a different type, the cast can throw a ClassCastException. Both cases must be excluded via a type check before accessing properties.

### 4.3. Overloading equals(Account) Instead of Overriding equals(Object)

~~~java
public boolean equals(Account other) {
    return number.equals(other.number);
}
~~~

The snippet above declares **an overload**, not an override of `Object.equals(Object)`. Calling `a.equals(null)` can cause the compiler to select the overload accepting Account (because the parameter type is more specific than Object), throwing a NullPointerException; meanwhile, calling through an Object-typed reference routes to a different method. Use the exact signature **public boolean equals(Object other)** along with **@Override** so the compiler checks it.

### 4.4. Confusing This with Calling on null

~~~java
Account missing = null;
Account a = new Account("A1");
// missing.equals(a); // Throws NullPointerException if uncommented
boolean safe = Objects.equals(missing, a); // false
~~~

This is an **illustrative snippet placed in the context of the Account class**, not a standalone program. Writing `equals` properly inside Account cannot make `missing.equals(a)` safe: Java must resolve the receiver object before executing the body of `equals`.

Also, do not write **return Objects.equals(this, other)** inside `equals(Object)` itself: when `this` and `other` are both non-null and not the same reference, the utility method calls `this.equals(other)` again, leading to infinite recursion for unequal pairs and ultimately a StackOverflowError.

## 5. Checking the Contract When Writing equals Yourself

A minimal check, run on any non-null object of the class, is:

~~~java
Account a = new Account("A1");
if (a.equals(null)) {
    throw new AssertionError("equals(null) must return false");
}
~~~

This check needs to be placed inside `main` or a test method that has access to Account. In JUnit 5, the equivalent idea is **assertFalse(a.equals(null))**.

You should also check the other properties of `equals` at the same time: `a.equals(a)` is true; two Accounts with the same `number` must be equal in both directions and have equal `hashCode`; different numbers return false; inputs of another type return false; repeating the comparison while state is unchanged must yield stable results. Especially if objects are used as HashMap keys or HashSet elements, properties participating in `equals`/`hashCode` should remain stable for the entire time they are in the data structure.

**Key takeaway:** For any non-null `x`, **x.equals(null) == false**. Place the null/type check at the beginning of `equals(Object)`, or use `instanceof` safely; use `Objects.equals` only when you need to compare two values where either side may be null.