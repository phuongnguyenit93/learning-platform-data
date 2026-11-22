# Inherited Members and the Limits of `private` Members in Java

## Learning Objectives

After this lesson, you will be able to:

- Distinguish between **members of a class**, **members inherited by a subclass**, **members declared by the subclass itself**, and **superclass members to which the subclass does not have direct access**.
- Explain the roles of the `public`, `protected`, *package-private* (no modifier written), and `private` access levels in Java inheritance.
- Understand why a `Child` object has **`Parent`'s own state**, even when the field is `private`, yet code in Child is not allowed to read/write the field directly by name.
- Grasp the rule that **constructors are not inherited**, the use of `super(...)`, and the case where a superclass constructor is not accessible.
- Distinguish between **overriding** instance methods, **hiding** static methods and fields, and the case where **a private method cannot be overridden**.
- Understand that a method declared in Child with the same signature as a private method in Parent is **a new method**, not an override of that private method.
- Analyze the difference between **`protected` access in the same package and in a different package**, especially the rule regarding the type of the receiver expression in a subclass in another package.
- Understand member inheritance in classes and interfaces, including instance default methods, static interface methods, and private interface helpers in Java 17.
- Write superclass designs that protect invariants with private state and public/protected methods with contracts, limiting the exposure of mutable fields to subclasses.
- Read, compile, and run Java 17+ programs with exact output; identify compile-time errors to avoid.

## 1. Inheritance Is Not Copying All Parent Source Code into the Child

A class can inherit from another class using `extends`:

~~~java
class Animal {
    public void eat() {
        System.out.println("eating");
    }
}

class Dog extends Animal {
    public void bark() {
        System.out.println("woof");
    }
}
~~~

In an appropriate method, `new Dog().eat()` is a valid call. `Dog` can use the public method `eat` declared by `Animal` according to inheritance/accessibility rules. However, `Dog` does not have its own separate copy of the source code of `eat`.

In Java, *inheritance* is a language-defined relationship of **types and members**, not a copy-paste operation of fields and methods. On a `Dog` object, methods are resolved/invoked according to Java rules and polymorphism.

A class inherits **directly from one class** (or implicitly `Object`), and can implement multiple interfaces. The constructor chain participates in initializing a subclass object. In the subclass body, private members of the superclass **do not automatically become accessible**.

### 1.1. Four Easily Confused Groups

| Group | Example in Parent | What to Remember in Child |
| --- | --- | --- |
| Public/protected/package-visible member inherited according to rules | `public void run()` | Can be used under appropriate access conditions |
| Private member of Parent | `private int balance` | Not inherited as an accessible member of Child; still belongs to Parent's state/behavior |
| Member declared by Child itself | `String label` | Belongs to Child; may have the same name as a Parent member |
| Parent constructor | `Parent(int id)` | **Not inherited**; a Child constructor can call `super(id)` if accessible |

**Note:** The phrase "members of a class" in the JLS has a detailed definition regarding declared/inherited members. Use the phrasing **"a private field remains the state of the superclass part within the object, but is not inherited by the subclass for direct access"** instead of "the private field is deleted when creating a subclass".

## 2. Rules for Inherited Members

In typical class scenarios, a subclass can inherit eligible **non-private** fields, instance methods, and nested member types according to the superclass/interfaces relationship and **accessibility rules**.

Not every member appearing in Parent becomes a valid name for direct use in Child. You need to consider:

1. Which **declaring class/interface** does the member belong to?
2. Which access modifier does the member have?
3. Is Child in **the same package**?
4. Does Child **declare a member with the same name/signature** to hide/override it?
5. Is the member an **instance method**, **static method**, **field**, **nested type**, or **constructor**?
6. If there are multiple supertypes/interfaces, are there conflicts among names/default methods?

### 2.1. Access Navigation Table in Typical Scenarios

| Declaration in Parent | Child in same package | Child in different package | Any code in different package |
| --- | --- | --- | --- |
| `public` | Accessible | Accessible | Accessible if owner type is accessible |
| `protected` | Accessible within package | Accessible under special subclass rules | Usually not accessible |
| No modifier (*package-private*) | Accessible within package | Not accessible via subclass status | No |
| `private` | **Not** directly, even in the same package | **Not** directly | No |

The table represents **the model of public top-level classes in ordinary packages**. When applied, there are also exceptions/rules regarding nested classes, nestmates, modules, access to types, protected qualified receivers, and reflection. Those exceptions **do not change the principle**: being a subclass alone does not grant permission to read a private member of the superclass.

### 2.2. Package-private Is Not `protected`

Writing:

~~~java
class Parent {
    int packageValue = 1;
}
~~~

without an access modifier keyword means **package-private**. It is accessible within the same package according to the rules, but **does not automatically open up to subclasses in other packages**.

The name "default access" is often used informally for package-private, but it should not be confused with **the `default` keyword in interface methods**. The two meanings are different.

## 3. A Private Field Still Contributes to the State of a Child Object

Consider:

~~~java
class Account {
    private long balanceCents;
}

class SavingsAccount extends Account {
}
~~~

A `SavingsAccount` object still has the state portion defined by `Account`. The private field `balanceCents` **does not disappear**, does not have an "undefined" value, and cannot be accessed by the subclass itself using `balanceCents` or `super.balanceCents`.

The superclass can provide public or protected methods for controlled observation/updating:

~~~java
class Account {
    private long balanceCents;

    public long balanceCents() {
        return balanceCents;
    }

    public void deposit(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        balanceCents = Math.addExact(balanceCents, amount);
    }
}

class SavingsAccount extends Account {
    public void addInterestBonus(long bonus) {
        deposit(bonus);
    }
}
~~~

These two classes are a valid illustrative example in the same package. `SavingsAccount` calls the **public method `deposit`** that is inherited/accessible, rather than being allowed to write `balanceCents += bonus` itself to break the invariant.

Such a design keeps the responsibility for state control in **the class that owns the field**, without granting direct write permission to every subclass.

## 4. First Program: Inheriting the API While Protecting Private State

Save **`PrivateStateInheritanceDemo.java`**:

~~~java
public class PrivateStateInheritanceDemo {
    static class Account {
        private long balance;

        Account(long openingBalance) {
            if (openingBalance < 0) {
                throw new IllegalArgumentException("negative opening");
            }
            balance = openingBalance;
        }

        public final long balance() {
            return balance;
        }

        public final void deposit(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("invalid deposit");
            }
            balance = Math.addExact(balance, amount);
        }

        protected final void withdraw(long amount) {
            if (amount <= 0 || amount > balance) {
                throw new IllegalArgumentException("invalid withdrawal");
            }
            balance -= amount;
        }
    }

    static final class SavingsAccount extends Account {
        SavingsAccount(long initialBalance) {
            super(initialBalance);
        }

        void useForPurchase(long amount) {
            withdraw(amount);
        }

        void creditReward(long amount) {
            deposit(amount);
        }
    }

    public static void main(String[] args) {
        SavingsAccount account = new SavingsAccount(1000);
        System.out.println("initial=" + account.balance());

        account.creditReward(250);
        account.useForPurchase(400);
        System.out.println("after=" + account.balance());

        try {
            account.useForPurchase(2000);
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid purchase rejected");
        }

        System.out.println("final=" + account.balance());
    }
}
~~~

Compile/run:

~~~bash
javac PrivateStateInheritanceDemo.java
java PrivateStateInheritanceDemo
~~~

**Stdout:**

~~~text
initial=1000
after=850
invalid purchase rejected
final=850
~~~

Analysis:

- `Account.balance` is private. It still belongs to the state of the `SavingsAccount` object.
- The subclass constructor calls `super(initialBalance)` so that the superclass sets a valid balance.
- The subclass calls `deposit` and `withdraw`, which have value-checking contracts, rather than assigning directly to the private field.
- `balance()`, `deposit`, and `withdraw` are `final` methods in the example so that subclasses cannot override the designed invariant-protection steps.
- `withdraw` is declared `protected`, so a Child belonging to a subclass can call it in an appropriate context. This does not mean every client in another package also has permission to call it.
- The withdrawal of 2000 is rejected before updating, so the balance stays at 850.

### 4.1. Why Is Using `private` Better Than `protected long balance` in Many Cases?

If the field is `protected`, a subclass can do:

~~~java
// balance = -900; // If the field is protected and accessible, this assignment
//                  // can bypass Account's validation.
~~~

A faulty subclass breaks Parent's invariant, forcing every method of Account to deal with invalid state.

Encapsulating state as private along with **protected methods with business meaning** (such as `withdraw`) helps extensions avoid needing to touch the representation directly. `protected` is suited for well-considered extension points, not as the default solution for sharing all fields.

## 5. `private` Differs from `final` and `static`

The modifiers answer different questions:

- `private`: **who is allowed to access the member under the language rules**?
- `final` on a field: can the field be **reassigned** after valid initialization?
- `final` on a method: can the method be **overridden** by a subclass?
- `static`: the member is associated with **the class** rather than each instance, along with the corresponding rules.
- `abstract`: the class/method has an obligation requiring a subclass implementation along the type hierarchy (subject to language constraints).

Example:

~~~java
class Base {
    private final String id = "A";
    protected final int version = 1;
    private static int privateCounter;
}
~~~

The fields `id` and `privateCounter` do not become directly accessible members from subclasses just because of `final` or `static`. `version` is declared protected final and can be accessed in a subclass according to the rules; it cannot be reassigned from ordinary code.

### 5.1. A Final Reference Does Not Make an Object Immutable

~~~java
class Base {
    private final java.util.ArrayList<String> items =
            new java.util.ArrayList<>();
}
~~~

`items` is a final reference field, yet the held `ArrayList` object remains mutable inside methods that have access. Private hides the field from subclasses, while API getters/setters must be designed to avoid exposing a mutable reference.

**Do not use a `protected` getter that directly returns a mutable internal list** if a subclass can call `clear()` and break the invariant.

## 6. Why Is `super.privateField` Invalid?

`super.field` is not a mechanism to "bypass" access control. It helps the expression select an appropriate field/member from the superclass according to the JLS, but it must still obey **accessibility**.

Intentionally incorrect example:

~~~java
class Parent {
    private int secret = 5;
}

class Child extends Parent {
    void show() {
        // System.out.println(secret);       // Not accessible.
        // System.out.println(super.secret); // Also not accessible.
    }
}
~~~

Even though a Child object has a Parent part containing `secret`, code in Child does not have permission to read that field. The solution is to provide a meaningful API from Parent:

~~~java
class Parent {
    private int secret = 5;

    protected int secretValue() {
        return secret;
    }
}

class Child extends Parent {
    int read() {
        return secretValue();
    }
}
~~~

The two sets of classes above are illustrative **alternative versions**. Do not place both `Parent` declarations in the same package/file and compile them together.

**You should not** use reflection to open up a private field just to bypass API design; besides the risk of breaking invariants, there are also module encapsulation, security, and portability concerns.

## 7. `private` Methods Are Not Overridden

This is a very important point for polymorphism.

A **private instance method** of Parent **is not inherited** as an override target in Child. When Child declares a method **with the same name and parameter types**, it can be **a new method**, not an override of Parent.privateMethod.

### 7.1. Standalone Example

Save **`PrivateMethodDispatchDemo.java`**:

~~~java
public class PrivateMethodDispatchDemo {
    static class Parent {
        private String label() {
            return "Parent.private";
        }

        public String describeInsideParent() {
            return label();
        }
    }

    static class Child extends Parent {
        public String label() {
            return "Child.public";
        }
    }

    public static void main(String[] args) {
        Child child = new Child();

        System.out.println(child.describeInsideParent());
        System.out.println(child.label());

        Parent asParent = child;
        System.out.println(asParent.describeInsideParent());
    }
}
~~~

Compile/run:

~~~bash
javac PrivateMethodDispatchDemo.java
java PrivateMethodDispatchDemo
~~~

Output:

~~~text
Parent.private
Child.public
Parent.private
~~~

**Why is that?**

- `Parent.describeInsideParent()` calls the `label()` **declared private by Parent**. That call does not dispatch to `Child.label()` as an overridden method.
- `Child.label()` is a new public method with the same name and signature, declared in Child.
- A reference of type `Parent` does not have a public `label()` to call directly. `asParent.describeInsideParent()` still runs the Parent method that calls Parent's private helper.
- Replacing `Child.label()` with a method having the `@Override` annotation in this situation causes a compile-time error: it **does not actually override a method from the superclass**.

### 7.2. Why Can't Private Methods Be Dynamic Extension Points?

The superclass can use a private method to carry out implementation details **without being replaced by a subclass**, protecting internal logic from accidental overriding. To allow subclass customization, design a `protected`/**public** instance method with a clear contract and call it at a safe point.

Do not change a private method to protected just to make it easier to access in tests without considering the impact on the inheritance contract and the ability of subclasses to override it.

## 8. Private Methods and the `@Override` Annotation

A common compiler error:

~~~java
class Parent {
    private void perform() {
    }
}

class Child extends Parent {
    // @Override                 // Invalid in this situation.
    void perform() {
    }
}
~~~

The `@Override` line is commented out because `Parent.perform()` is private, not an inherited override target.

If the Parent method is changed to:

~~~java
protected void perform() {
}
~~~

and the Child method is kept as package-private `void perform()`, then there is **another error**: cannot reduce the visibility of the overridden method. A Child override must be at least `protected` (or `public`) in a valid context.

**Two independent sets of rules:**

1. Is there a valid inherited, overridable method target?
2. If so, does the override match the signature, return type, access level, exceptions, and other rules?

The `@Override` annotation is a very useful compiler check to avoid thinking you are overriding a method when you are actually declaring a new one.

## 9. Comparison with True Overriding: Dynamic Dispatch

Save **`InheritedMethodOverrideDemo.java`**:

~~~java
public class InheritedMethodOverrideDemo {
    static class Animal {
        private final String name;

        Animal(String name) {
            this.name = name;
        }

        public String name() {
            return name;
        }

        public String sound() {
            return "...";
        }

        public String introduction() {
            return name() + " says " + sound();
        }
    }

    static class Dog extends Animal {
        Dog(String name) {
            super(name);
        }

        @Override
        public String sound() {
            return "woof";
        }

        public String parentSound() {
            return super.sound();
        }
    }

    public static void main(String[] args) {
        Animal animal = new Dog("Milo");

        System.out.println(animal.introduction());
        System.out.println(animal.sound());
        System.out.println(((Dog) animal).parentSound());
    }
}
~~~

Commands:

~~~bash
javac InheritedMethodOverrideDemo.java
java InheritedMethodOverrideDemo
~~~

Output:

~~~text
Milo says woof
woof
...
~~~

**Explanation:**

- Animal's `name` remains private state. Dog does not read that field directly; `name()` is an inherited public accessor.
- `sound()` is a public instance method, validly overridden by Dog.
- Inside `animal.introduction()` (whose implementation is declared in Animal), the call to `sound()` uses dynamic dispatch and therefore runs `Dog.sound()` because the runtime object is Dog.
- `super.sound()` in Dog explicitly invokes the superclass implementation (in a valid context), returning `"..."`.
- This is the core difference from the **private method** in the `PrivateMethodDispatchDemo` example.

### 9.1. `super` Is Not a Separate Animal Object

`super.sound()` selects the implementation from the superclass; it does not create another Animal object. The `Dog` object keeps the same identity whether the code runs an Animal method or a Dog method.

Similarly, Animal's private field is the state of the superclass part inside the Dog object, not a field located in a separate Animal object allocated by `super(...)`.

## 10. Constructors Are Not Inherited

In Java, constructors are not inherited methods. A Child class **does not automatically have** constructors with the same signatures as Parent.

If:

~~~java
class Parent {
    Parent(int value) {
    }
}

class Child extends Parent {
}
~~~

this is an **intentionally incorrect example**: the compiler tries to generate a default constructor `Child()` that calls an implicit `super()`, but Parent has no accessible no-argument constructor. Child also does not automatically have a `Child(int)` constructor just because Parent has `Parent(int)`.

Fix it by declaring the subclass constructor explicitly:

~~~java
class Parent {
    Parent(int value) {
    }
}

class Child extends Parent {
    Child(int value) {
        super(value);
    }
}
~~~

The two blocks are alternatives to each other; do not compile them simultaneously due to duplicate names.

### 10.1. Private Constructor of a Superclass

A subclass outside the Parent class cannot call a `private Parent(...)` constructor in the usual way using `super(...)`. This can be used to control instance creation or prevent unintended forms of inheritance.

Example:

~~~java
class Parent {
    private Parent() {
    }
}

class Child extends Parent {
    // Child() { super(); } // Invalid: Parent() is inaccessible.
}
~~~

This is a **compile-time error example**, because even if the explicit Child constructor is omitted, Child's implicit default constructor still needs to call the inaccessible `super()`.

If designing Parent to allow subclasses, consider `protected Parent(...)` according to the contract. No access modifier turns a constructor into an "inherited constructor".

## 11. Constructor and Private State Program

Save **`PrivateConstructorStateDemo.java`**:

~~~java
public class PrivateConstructorStateDemo {
    static class Person {
        private final String name;
        private final int age;

        protected Person(String name, int age) {
            if (name == null || name.isBlank() || age < 0) {
                throw new IllegalArgumentException("invalid person");
            }
            this.name = name;
            this.age = age;
        }

        public final String summary() {
            return name + "(" + age + ")";
        }
    }

    static final class Student extends Person {
        private final String className;

        Student(String name, int age, String className) {
            super(name, age);
            this.className = className;
        }

        String describe() {
            return summary() + ",class=" + className;
        }
    }

    public static void main(String[] args) {
        Student student = new Student("Lan", 17, "12A");
        System.out.println(student.describe());
        System.out.println(student.summary());

        try {
            new Student("Minh", -1, "12B");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid parent state rejected");
        }
    }
}
~~~

Run:

~~~bash
javac PrivateConstructorStateDemo.java
java PrivateConstructorStateDemo
~~~

Output:

~~~text
Lan(17),class=12A
Lan(17)
invalid parent state rejected
~~~

`Person` uses private final fields and a protected constructor. When creating Student, the superclass validates the portion of state that it owns. Student does not access `name`/`age` directly, and instead uses public final `summary()`.

Point to remember: **a private constructor differs from a private field**, yet both are subject to access control. For a subclass to be able to initialize the superclass, Parent must provide an **accessible constructor path**.

## 12. Package-private: Same Package Differs from a Different Package

Java packages are an important part of access control.

- A class and its subclass **in the same package** can use package-private members of the superclass according to inheritance/accessibility rules.
- A subclass **in a different package** cannot rely on `extends` to access package-private fields/methods of Parent.
- Use `public` or `protected` intentionally if part of the API is needed for code outside the package, but do not open up the entire state just for convenience.

### 12.1. Runnable Example in the Same Package/File

Save **`PackageVisibilityDemo.java`**:

~~~java
public class PackageVisibilityDemo {
    static class Parent {
        int packageValue = 7;
        private int secret = 100;

        int packageMethod() {
            return packageValue + secret;
        }
    }

    static class Child extends Parent {
        int inspect() {
            return packageValue;
        }

        int useMethod() {
            return packageMethod();
        }
    }

    public static void main(String[] args) {
        Child child = new Child();

        System.out.println("package field=" + child.inspect());
        System.out.println("package method=" + child.useMethod());
    }
}
~~~

Compile/run:

~~~bash
javac PackageVisibilityDemo.java
java PackageVisibilityDemo
~~~

Output:

~~~text
package field=7
package method=107
~~~

The nested classes `Parent` and `Child` reside in the same top-level class, so they are also in the same package. `packageValue` and `packageMethod` are package-private. The private `secret` is used by **Parent's method** to compute 107; Child does not read the `secret` field itself.

### 12.2. Cross-Package Changes Compile-Time Behavior

A subclass in another package **does not have permission** to directly read package-private `packageValue` from Parent. It can call a `public` method provided by Parent, or use a `protected` member when the appropriate subclass/receiver conditions are satisfied.

Do not equate package-private with Java module visibility. Modules add readability/exports rules, while `private` and `protected` still retain their own language semantics.

## 13. Example with Two Packages and `protected`

Create the directory structure:

~~~text
project/
  api/
    Base.java
  client/
    Child.java
    Main.java
~~~

Contents of **`api/Base.java`**:

~~~java
package api;

public class Base {
    int packageValue = 7;
    protected int protectedValue = 8;
    public int publicValue = 9;
    private int secret = 10;

    protected String format() {
        return "Base-format";
    }

    public int secretValue() {
        return secret;
    }
}
~~~

Contents of **`client/Child.java`**:

~~~java
package client;

import api.Base;

public class Child extends Base {
    public String inspect() {
        return protectedValue + "," + publicValue
                + "," + secretValue();
    }

    public String callProtected() {
        return format();
    }

    public int inspectOtherChild(Child other) {
        return other.protectedValue;
    }
}
~~~

Contents of **`client/Main.java`**:

~~~java
package client;

public class Main {
    public static void main(String[] args) {
        Child first = new Child();
        Child second = new Child();

        System.out.println("values=" + first.inspect());
        System.out.println("format=" + first.callProtected());
        System.out.println("other=" + first.inspectOtherChild(second));
    }
}
~~~

Compile from the `project` directory:

~~~bash
javac -d out api/Base.java client/Child.java client/Main.java
java -cp out client.Main
~~~

Output:

~~~text
values=8,9,10
format=Base-format
other=8
~~~

**Explanation:**

1. `Child` is in package `client`, and `Base` is in package `api`.
2. `protectedValue` and `format()` are protected, so Child can use them in subclass code according to the rules.
3. `publicValue` and `secretValue()` are public, and accessible because Base is public in the package being used.
4. `packageValue` is not accessible from Child; it is package-private in package `api`.
5. The private `secret` cannot be read directly by Child. The value 10 goes through `Base.secretValue()`.
6. `other.protectedValue` is valid in the body of Child because the qualifier `other` has static type `Child`; the next section explains an important receiver restriction.

### 13.1. Protected Pitfall in Another Package: `Base other`

Inside Child in package `client`, this can be valid:

~~~java
int a = this.protectedValue;
int b = otherChild.protectedValue; // otherChild has type Child.
~~~

However, the following snippet can be rejected:

~~~java
void inspectBase(api.Base otherBase) {
    // int x = otherBase.protectedValue; // Invalid here.
}
~~~

In Java, protected access from a subclass **outside the declaring package** has an additional restriction on **the static type of the qualifier expression** when accessing an instance field/method. Simply "being inside a subclass" does not allow accessing a protected member through **any arbitrary Base object**.

This prevents a subclass from arbitrarily using its protected privilege to access the state of a Base object that is not of the permitted receiver type.

### 13.2. Is the Same Package Different?

Yes. Code in **the same package `api`** as Base can access a protected member of Base via package-accessibility even when it is not a subclass, if the other rules allow it.

Therefore, when moving a class to a different package, sometimes access to `protected` begins reporting errors even though the word `protected` has not changed.

## 14. Private Fields Cannot Be Overridden; Same Name Is Only Field Hiding

The concept of **overriding** applies to eligible instance methods, not to fields. Fields can be **hidden** by declarations with the same name in a subclass.

### 14.1. Example of Fields with the Same Name in Superclass/Subclass

Save **`FieldHidingDemo.java`**:

~~~java
public class FieldHidingDemo {
    static class Parent {
        public int value = 10;

        public int parentValue() {
            return value;
        }
    }

    static class Child extends Parent {
        public int value = 20;

        public int childValue() {
            return value;
        }
    }

    public static void main(String[] args) {
        Child child = new Child();
        Parent parentView = child;

        System.out.println("parent view=" + parentView.value);
        System.out.println("child view=" + child.value);
        System.out.println("parent method=" + child.parentValue());
        System.out.println("child method=" + child.childValue());
    }
}
~~~

Compile/run:

~~~bash
javac FieldHidingDemo.java
java FieldHidingDemo
~~~

Output:

~~~text
parent view=10
child view=20
parent method=10
child method=20
~~~

**Why?**

- `Parent.value` and `Child.value` are **two field declarations**, despite having the same name.
- `parentView.value` selects the field based on the static type `Parent`, without dynamic dispatch like a method override.
- `child.value` selects Child's field.
- `parentValue()` executes inside Parent, so the name `value` refers to Parent.value; `childValue()` in Child refers to Child.value.
- Both fields can coexist inside **a single Child object**.

### 14.2. A Private Field with the Same Name Is Not an Override

If Parent declares `private int value` and Child declares `int value`, the two fields are still two different state components. Child cannot write `super.value` to read Parent's private field. Having the same name **does not change** access permissions or turn Parent's state into Child's state.

**Recommendation:** avoid field hiding unless there is a clear reason; it makes code easy to confuse between static-type access and polymorphic dispatch of methods.

## 15. Program with Two Private Fields Sharing the Same Name

Save **`DistinctPrivateFieldsDemo.java`**:

~~~java
public class DistinctPrivateFieldsDemo {
    static class Parent {
        private int value = 10;

        public int parentValue() {
            return value;
        }

        public void incrementParent() {
            value++;
        }
    }

    static class Child extends Parent {
        private int value = 100;

        public int childValue() {
            return value;
        }

        public void incrementChild() {
            value++;
        }
    }

    public static void main(String[] args) {
        Child child = new Child();

        System.out.println("initial parent=" + child.parentValue());
        System.out.println("initial child=" + child.childValue());

        child.incrementParent();
        child.incrementChild();

        System.out.println("after parent=" + child.parentValue());
        System.out.println("after child=" + child.childValue());
    }
}
~~~

Run:

~~~bash
javac DistinctPrivateFieldsDemo.java
java DistinctPrivateFieldsDemo
~~~

Output:

~~~text
initial parent=10
initial child=100
after parent=11
after child=101
~~~

Parent's private `value` and Child's private `value` are two independent fields. `incrementParent()` modifies Parent's field; `incrementChild()` modifies Child's field. This code does not use a single overridden field.

From a design standpoint, reusing the same name can make debugging harder. It should only be done when the two classes genuinely have distinct state meanings and the duplicate name does not cause confusion; normally it is better to choose names that clearly express responsibility.

## 16. Static Methods: Hiding Differs from Overriding

A `static` method is invoked according to static method lookup/hiding rules, **not** polymorphic dynamic dispatch like an instance method override.

Save **`StaticMethodHidingDemo.java`**:

~~~java
public class StaticMethodHidingDemo {
    static class Parent {
        static String label() {
            return "Parent.static";
        }

        public String describe() {
            return label();
        }
    }

    static class Child extends Parent {
        static String label() {
            return "Child.static";
        }
    }

    public static void main(String[] args) {
        Parent p = new Child();
        Child c = new Child();

        System.out.println("via Parent=" + p.label());
        System.out.println("via Child=" + c.label());
        System.out.println("inherited describe=" + c.describe());
    }
}
~~~

Run:

~~~bash
javac StaticMethodHidingDemo.java
java StaticMethodHidingDemo
~~~

Output:

~~~text
via Parent=Parent.static
via Child=Child.static
inherited describe=Parent.static
~~~

**Explanation:**

- `Parent.label` and `Child.label` are static methods with the same signature. The Child method **hides** the Parent method under appropriate conditions, rather than overriding it.
- `p.label()` through an expression of static type Parent binds to Parent's static method.
- `c.label()` through an expression of static type Child selects Child's static method.
- `Parent.describe()` calls `label()` from Parent's context, without dynamic dispatch to Child's static method.
- Java allows using an expression to access a static method in certain contexts, but **you should write `Parent.label()`/`Child.label()`** to make it clear that the method belongs to the class, not an instance.

A private static method of Parent **is not inherited by Child**; Child can declare a static method with the same name without creating a hiding relationship in the sense of that inherited member.

## 17. Cannot Reduce Access Privileges When Overriding

If Parent defines:

~~~java
public void process() {
}
~~~

then a valid Child override must remain public:

~~~java
@Override
public void process() {
}
~~~

You cannot write `protected void process()` or package-private `void process()` when overriding a public Parent method, because doing so reduces the accessibility of the method in the subtype.

If the Parent method is `protected`, Child can override it as `protected` or `public`, but cannot turn it into `private` in a valid override.

### 17.1. Distinguishing "Cannot Be Overridden" from "Cannot Be Accessed"

- `private Parent.method()`: the subclass does not inherit that method as an override target.
- An accessible `final Parent.method()`: can be inherited/called, but the subclass **cannot override it**.
- `static Parent.method()`: not an instance override target; can be hidden by an eligible static method.
- Package-private Parent.method() in another package: not accessible/inherited according to the applicable rules; it must not be assumed that a method with the same name in Child will be an override of that method.
- An accessible `abstract` instance method requires an implementation in a concrete subclass, unless it has already been implemented by an intermediate class.

These cases have different compile-time rules. When the compiler says "attempting to assign weaker access privileges", the error only appears **once an applicable override relationship exists**.

## 18. `final` Methods and Private Helpers: Two Ways to Preserve the Superclass Contract

A superclass can control invariants according to two patterns:

**Pattern A — private implementation:**

~~~java
class Parent {
    private void validateInternal() {
    }

    public void operation() {
        validateInternal();
    }
}
~~~

`validateInternal` is an internal detail that cannot be overridden by subclasses.

**Pattern B — public final operation, protected hook:**

~~~java
abstract class Parent {
    public final void operation() {
        validate();
        performCore();
    }

    private void validate() {
        // Checks owned by Parent.
    }

    protected abstract void performCore();
}
~~~

This is an illustrative skeleton. The final template method `operation()` prevents subclasses from overriding the entire workflow, while `performCore()` is an intentionally placed extension point. However, if an overridable/protected hook is called inside **a constructor** before subclass initialization finishes, there is still a risk of incomplete state.

**Do not provide a `protected` getter that returns a mutable representation solely for extensibility**, unless ownership and invariants are already under control.

## 19. Superclass Constructors Can Call Overridden Methods Too Early

Inheritance and polymorphism also have an initialization-timing pitfall. The object's runtime type is already Child while the Parent constructor code is executing. If the Parent constructor calls a public/protected overridable method, the call can dispatch to the Child implementation **before Child's field initializers have run**.

Save **`ConstructorOverrideRiskDemo.java`**:

~~~java
public class ConstructorOverrideRiskDemo {
    static class Parent {
        Parent() {
            System.out.println("parent begins");
            show();
        }

        protected void show() {
            System.out.println("Parent.show");
        }
    }

    static class Child extends Parent {
        private String label = "READY";

        Child() {
            System.out.println("child constructor");
        }

        @Override
        protected void show() {
            System.out.println("Child.show label=" + label);
        }
    }

    public static void main(String[] args) {
        Child child = new Child();
        child.show();
    }
}
~~~

Run:

~~~bash
javac ConstructorOverrideRiskDemo.java
java ConstructorOverrideRiskDemo
~~~

Output:

~~~text
parent begins
Child.show label=null
child constructor
Child.show label=READY
~~~

Private helper methods in Parent cannot be overridden by Child, so if the Parent constructor **only** uses private/final logic based on already-safe Parent state, this risk of dispatching to Child is reduced. However, **not every call to a private method from a constructor is always safe**: the helper can still perform I/O, publish `this`, read uninitialized state, or cause other side effects.

**Principle:** a superclass constructor should not depend on the behavior of a subclass that has not finished initializing. Reserve callbacks/extension hooks for the stage after the object has been completely constructed.

## 20. Member Nested Types and Inheritance

Besides fields and methods, Java has **member types** (such as static nested classes, non-static inner classes, and member interfaces according to the rules). A nested type declared with appropriate accessibility can also be used via appropriate inheritance/name lookup.

Example:

~~~java
class Parent {
    public static class Token {
        public final int id;

        public Token(int id) {
            this.id = id;
        }
    }
}

class Child extends Parent {
}
~~~

Code can write `Child.Token` to refer to the member type `Token` inherited/looked up from Parent when valid.

### 20.1. Runnable Program

Save **`InheritedMemberTypeDemo.java`**:

~~~java
public class InheritedMemberTypeDemo {
    static class Parent {
        public static class Token {
            private final int id;

            public Token(int id) {
                this.id = id;
            }

            public int id() {
                return id;
            }
        }
    }

    static class Child extends Parent {
        public String useToken() {
            Token token = new Token(7);
            return "token=" + token.id();
        }
    }

    public static void main(String[] args) {
        Child child = new Child();
        Child.Token token = new Child.Token(9);

        System.out.println(child.useToken());
        System.out.println("external=" + token.id());
    }
}
~~~

Run:

~~~bash
javac InheritedMemberTypeDemo.java
java InheritedMemberTypeDemo
~~~

Output:

~~~text
token=7
external=9
~~~

`Token` is declared by Parent as a public static nested type. In the example, Child can use the name `Token`, and `Child.Token` is resolved appropriately. A member type declared `private` in Parent **does not** become a type directly accessible from a subclass; it must still obey access control.

### 20.2. Nested and Inner Classes Have Specific Characteristics

A **non-static inner class** is associated with an enclosing instance. A **static nested class** does not carry an enclosing instance in the same way. Inheritance of a nested *type name* is not inheritance of a constructor, nor does it mean that creating `new Child.Token()` initializes a Child object.

Avoid confusing the levels:

- Inheritance between Parent and Child.
- Lexical nesting of class Token inside Parent.
- Relationship between an instance of an inner class and its enclosing instance.

## 21. Members from an Interface: Default Methods, Private Helpers, and Static Methods

Java interfaces can declare:

- Public abstract methods (per interface semantics).
- **Default instance methods** with an implementation.
- **Static methods** belonging to the interface itself.
- **Private methods** (since Java 9) to help reuse internal implementation within the interface.
- Interface fields, implicitly `public static final`.

A class implementing an interface can inherit/implement the **public abstract/default instance methods** according to interface inheritance rules and conflict resolution. However, **private interface helpers are not inherited by the implementing class** as callable methods; **nor can a static interface method be called as an inherited static member on the implementer**.

### 21.1. Interface Program with a Private Helper

Save **`InterfaceMemberVisibilityDemo.java`**:

~~~java
public class InterfaceMemberVisibilityDemo {
    interface Greeter {
        default String greet(String name) {
            return decorate(name);
        }

        private String decorate(String text) {
            return "Hello " + text;
        }

        static String category() {
            return "greeting";
        }
    }

    static final class FriendlyGreeter implements Greeter {
    }

    public static void main(String[] args) {
        FriendlyGreeter greeter = new FriendlyGreeter();

        System.out.println(greeter.greet("Lan"));
        System.out.println(Greeter.category());
    }
}
~~~

Run:

~~~bash
javac InterfaceMemberVisibilityDemo.java
java InterfaceMemberVisibilityDemo
~~~

Output:

~~~text
Hello Lan
greeting
~~~

**Explanation:**

- `FriendlyGreeter` is used as an implementation of Greeter; `greet` has a default implementation and is called through the object.
- `Greeter.greet` can call the private helper `decorate` because it is inside the interface itself.
- `FriendlyGreeter` **does not have permission to call `decorate` as an inherited method**.
- The static method `category` must be called via the declaring interface name `Greeter.category()`, not `FriendlyGreeter.category()`.
- A private interface method is not an extension hook for implementers. If you need a method that the implementer must provide, declare an appropriate abstract public interface method.

### 21.2. An Interface Field Is Not an Instance Field

If an interface defines `int LIMIT = 10;`, it is a `public static final` field according to the rules, not a separate field of each implementation object. An implementing class cannot change the value by "overriding the field"; fields are not overridden.

Constant name collisions can occur across multiple interfaces. When names are ambiguous, use the qualification `InterfaceName.CONSTANT` to specify clearly. In real APIs, avoid implementing an interface solely to "borrow constants", because doing so unnecessarily introduces implementation details into the type hierarchy.

## 22. A Subclass Can Call a Private Member Indirectly

Not everything that needs a private field requires changing the field to `protected`. Parent can **provide behavior**:

~~~java
class Account {
    private long balance;

    public long balance() {
        return balance;
    }

    protected void debit(long amount) {
        if (amount <= 0 || amount > balance) {
            throw new IllegalArgumentException("invalid debit");
        }
        balance -= amount;
    }
}
~~~

The subclass calls `debit(amount)` to perform the business operation, and Parent still determines the limits. Do not expose a `setBalance(long arbitraryValue)` method that allows breaking the invariant.

### 22.1. Query vs. Command

- **Query** returns meaningful information: `balance()`, `isActive()`, `canWithdraw(amount)`.
- **Command** changes state according to rules: `withdraw(amount)`, `activate()`, `close()`.
- **Raw setter** such as `setBalance(-1000)` is a risk if it exists solely to support a subclass.

When logic in Parent changes (balance limits, auditing, validation), subclasses using the command API still get the correct behavior without modifying the representation.

### 22.2. Protecting Mutable Returned Objects

If Parent holds `private List<Transaction> history` yet the method `protected List<Transaction> history()` directly returns the mutable list, Child can still call `clear()` and corrupt the state.

A `private` field **is not enough** if Parent exposes a mutable reference through an accessor. Immutable entries, a `List.copyOf` snapshot, a method for adding events with validation, or an appropriate ownership contract are needed.

## 23. Abstract Superclass: Private State and Protected Extension Points

An abstract class can hold common private state and require subclasses to implement behavior:

~~~java
abstract class Shape {
    private final String color;

    protected Shape(String color) {
        this.color = color;
    }

    public final String color() {
        return color;
    }

    public abstract double area();
}
~~~

A concrete subclass uses `super(color)` so Parent initializes color and overrides `area()` according to the rules. There is no need to grant permission to reassign the private color field.

### 23.1. Complete Program

Save **`AbstractPrivateStateDemo.java`**:

~~~java
public class AbstractPrivateStateDemo {
    static abstract class Shape {
        private final String color;

        protected Shape(String color) {
            this.color = color;
        }

        public final String color() {
            return color;
        }

        public abstract int area();
    }

    static final class Rectangle extends Shape {
        private final int width;
        private final int height;

        Rectangle(String color, int width, int height) {
            super(color);
            this.width = width;
            this.height = height;
        }

        @Override
        public int area() {
            return Math.multiplyExact(width, height);
        }
    }

    public static void main(String[] args) {
        Shape shape = new Rectangle("red", 3, 4);

        System.out.println("color=" + shape.color());
        System.out.println("area=" + shape.area());
    }
}
~~~

Run:

~~~bash
javac AbstractPrivateStateDemo.java
java AbstractPrivateStateDemo
~~~

Output:

~~~text
color=red
area=12
~~~

Here, the `color` field is private final in Shape, yet exists in the state of the Rectangle object. Shape's public interface only allows reading color via `color()`; the `area()` behavior is overridden by Rectangle. This is an example that clearly separates **state encapsulation** and **polymorphic extension**.

## 24. The `protected` Rule Should Be Used Intentionally

Protected does not simply mean "every inheriting class can read every protected field on any Parent object." As seen in the cross-package section, access permission can depend on the receiver.

When designing a reusable library:

1. Use `private` for representation details and helper methods not intended for subclasses.
2. Only provide `protected` methods for extension points that you genuinely intend to support long term.
3. Prefer methods with contracts over protected mutable fields.
4. Consider `protected` constructors if subclassing is intended but you do not want clients to instantiate Parent directly.
5. Use `public final` methods for important invariant logic that subclasses must not replace.
6. Test a subclass **in a different package** to uncover wrong access assumptions.
7. If Parent is not designed for inheritance, consider a `final class` or factory/composition instead of exposing ambiguous subclass extension points.

### 24.1. Compatibility When Changing Access

Changing a method from `protected` to `private` can cause already-compiled subclasses/new source code to encounter issues, because the API inheritance contract changes. Similarly, changing an instance method to static or making it final can affect overriding/linking.

Do not treat access modifiers as choices made merely to "get it to compile"; they are an important part of the **public/protected API contract**.

## 25. Reflection, Nested Classes, and Private Access

**"Private is inaccessible from a subclass"** does not mean that no Java mechanism can read that information in any situation. Java has separate access rules for:

- Code inside the class that declares the member itself.
- Nestmates/nested classes under Java access control.
- Reflection according to access permissions/module openness, if permitted.
- Serialization frameworks/instrumentation with appropriate execution privileges.

These mechanisms **do not make a private field an inherited accessible field** for an ordinary subclass.

### 25.1. Nested Classes Can Access Private Members of the Enclosing Class

A nested class residing in the same nest can access private members according to Java rules. That is different from a subclass located in a separate top-level class.

Example:

~~~java
class Outer {
    private int secret = 9;

    class Inner {
        int read() {
            return secret;
        }
    }
}
~~~

`Inner` does not access secret because it extends Outer; it is a nested class that has access privileges under Java nesting rules. Do not use this case to infer that "since Child extends Parent, it can read Parent's private members".

### 25.2. Reflection Is Not an Inheritance Plan

The reflection API can list declared fields including private ones depending on the API and allow inspection within valid scopes; attempting `setAccessible(true)` can be rejected by module encapsulation or other restrictions. The fact that a debugger/profiler tool displays a private field does not mean subclass source code can access that field directly.

**Do not use reflection to break invariants** when a clearly defined protected/public method can solve the problem.

## 26. Polymorphism Does Not "Unlock" Private Members

With:

~~~java
Parent ref = new Child();
~~~

dynamic dispatch can select Child's overridden instance method implementation, however:

- The static type `Parent` determines which members can be called according to compile-time rules.
- The runtime type `Child` determines the implementation of a valid overridden instance method.
- Parent's private members do not become accessible from Child just because the runtime object is Child.
- Field access does not dispatch like instance method overriding.
- Static methods are not polymorphic like instance methods.
- Constructors are neither inherited nor overridden.

Therefore, **access control, member inheritance, static type lookup, and dynamic dispatch are four distinct layers of rules**. A valid program must pass compile-time name/type/access checks before runtime method dispatch even comes into play.

## 27. Common Mistakes

| Mistake | Correct Conclusion |
| --- | --- |
| "Child inherits all fields of Parent, including private ones, for direct use." | A private Parent field is not an accessible inherited field in Child. |
| "Because private is not inherited, that field does not exist in a Child object." | Superclass state still exists and is managed by Parent methods. |
| "`super.privateField` bypasses private." | `super` does not bypass access control. |
| "`private` is the same as package-private." | Private is stricter; classes in the same package still do not automatically get access to private. |
| "A package-private method of Parent is always accessible in a subclass in another package." | No. `extends` does not automatically open the package boundary. |
| "Protected means every subclass can read the protected field of any Parent instance." | Cross-package receiver restrictions still apply. |
| "A protected field is always a good extension API." | Exposing mutable representation easily breaks invariants; prefer well-defined protected methods. |
| "A Child method with the same name as a private Parent method is an override." | No; it is a new method under the appropriate conditions. |
| "`@Override` can be used with a private Parent method." | The compiler must report an error if there is no actual override target. |
| "A static method with the same name is a dynamic override." | Static method hiding, not dynamic dispatch. |
| "Fields are overridden based on the runtime object." | Fields are resolved according to compile-time/static type rules; field hiding differs from overriding. |
| "A `final` field makes the referenced object immutable." | Final prevents reassigning the field reference, not deep immutability. |
| "A `final` method cannot be inherited." | A final method can be inherited/called; it just cannot be overridden. |
| "Parent constructors are inherited." | Child must have its own constructor/default constructor and call a valid super path. |
| "A private Parent constructor allows any subclass to call `super()`." | No; the constructor must be accessible. |
| "A private Parent method can be polymorphically dispatched to Child." | A private method is not an override target; Parent calls its own helper. |
| "A subclass can override a public method with protected." | Accessibility cannot be reduced in an override. |
| "A class implementing an interface inherits its private helpers." | Private interface methods are for internal interface use only. |
| "A static interface method is called through the implementation class." | Use `InterfaceName.staticMethod()`. |
| "Nested classes having access to private proves any subclass can do it too." | Nestmate/nesting privileges differ from inheritance. |
| "Reflection seeing private means the compiler allows Child to read it." | Reflection/debug visibility does not change source-level access. |
| "An override called in a Parent constructor is always safe." | Child fields may still be 0/null; avoid overridable callbacks from constructors. |
| "A Child object is two Parent and Child objects joined together." | It is a single object with a superclass/subclass initialization chain. |
| "To use a field, just change `private` to `public`." | Design a behavior-based API; do not break encapsulation. |

## 28. Checklist When Encountering Inheritance/Access Errors

When the compiler reports "has private access", "cannot find symbol", "attempting to assign weaker access privileges", or "method does not override", check:

1. **Who are the superclass and subclass?** Are `extends`/`implements` correct?
2. **Where is the member declared?** Parent, interface, outer/nested type, or Child?
3. **What kind of member is it?** Field, constructor, instance/static method, or nested type?
4. **What is the access modifier?** `private`, package-private, `protected`, or `public`?
5. **What are the packages of Parent/Child?** Do they actually share the same package name?
6. **Is the non-private member truly inherited/accessible as appropriate?**
7. **Is the name hidden or overridden by a Child member?**
8. **Is the method `static` or `final`?** Does it allow overriding?
9. **If overriding, did it change the return type/access/checked exceptions incorrectly?**
10. **If protected across packages, does the receiver have an eligible static type?**
11. **Does the Child constructor call `super(...)` validly?** Is the Parent constructor accessible?
12. **What is the static type of the expression reference?** Runtime type only affects dispatch when applicable.
13. **Does the superclass API already have a query/command instead of direct field access?**
14. **Did you use `@Override` so the compiler verifies the override relationship?**
15. **Instead of inheritance, would composition reflect the domain relationship better?**

Diagnosing the right group of rules helps fix the design properly: exposing the right API, changing signature/visibility, moving responsibility back to the owner class, or using a valid `super(...)` — rather than arbitrarily turning every member public.

## 29. Self-Check Exercises with Answers

**Question 1.** Parent has `private int id`, and Child extends Parent. Can Child read `id` directly?  
**Answer:** No. A private field of Parent is not an inherited accessible member in Child.

**Question 2.** If Child does not read `id` directly, does the Child object have Parent's `id` state?  
**Answer:** Yes. Parent's constructor/methods can still manage the field in the superclass state part.

**Question 3.** Does `super.id` bypass private?  
**Answer:** No. `super` does not break access-control rules.

**Question 4.** Parent has `public int id()` returning the private field. Can Child call `id()`?  
**Answer:** Yes, if the method is accessible/inherited according to the rules; this is an API provided by Parent.

**Question 5.** Parent has `private void f()`, and Child declares `public void f()`. Is this an override?  
**Answer:** No. The Child method is a new declaration; the private Parent method is not overridden.

**Question 6.** Can `@Override` be placed on `Child.f()` in Question 5?  
**Answer:** No; the compiler will report that the method does not override in the described situation.

**Question 7.** When a Parent method calls `private f()`, and the runtime object is Child which has a new `public f()`, which method runs?  
**Answer:** Parent.private f(), without dynamic dispatch to Child f().

**Question 8.** If Parent declares `public void f()` and Child validly overrides it, what runs when calling f() on a reference of type Parent pointing to Child?  
**Answer:** The Child implementation, due to dynamic dispatch of an overridden instance method.

**Question 9.** Can Child call Parent's `final public void f()`?  
**Answer:** It can be inherited/called if accessible, but Child is not allowed to override it.

**Question 10.** Parent declares `static void f()`, and Child also has `static void f()`. Is this an override?  
**Answer:** No; it is static method hiding when valid.

**Question 11.** Both Parent and Child declare `int value`; when a reference of type Parent pointing to Child reads `ref.value`, which field is normally selected?  
**Answer:** Parent's field is selected according to the static type Parent and field lookup rules.

**Question 12.** Are a private Parent field and a private Child field with the same name the same field?  
**Answer:** No. They are two independent declarations/states.

**Question 13.** Are constructors inherited?  
**Answer:** No. A Child constructor must call an accessible superclass constructor according to the rules.

**Question 14.** Parent only has `Parent(int)`, and Child declares no constructor. What is wrong?  
**Answer:** The default Child constructor tries to make an implicit `super()` call, but Parent has no accessible no-arg constructor; compilation error.

**Question 15.** Parent has a private no-arg constructor; can an external top-level Child call `super()`?  
**Answer:** No, the constructor is inaccessible.

**Question 16.** Is a package-private member accessible from a subclass in another package solely because of `extends`?  
**Answer:** No. Package-private scope is confined to its respective package.

**Question 17.** Can a `protected` field in Base in package api be accessed by subclass Child in package client via `this.field`?  
**Answer:** Yes, if the protected subclass access rules are satisfied.

**Question 18.** Also in Child in another package, is `Base other; other.field` with Base's protected field always valid?  
**Answer:** No. Cross-package protected access has receiver restrictions; a `Base` qualifier is usually not sufficient.

**Question 19.** Can a public Parent method be overridden by Child as protected?  
**Answer:** No; you cannot reduce the access privileges of an overridden method.

**Question 20.** Can a protected Parent method be overridden by Child as public?  
**Answer:** Yes, if the other rules (signature/return/throws) are satisfied.

**Question 21.** Can a class implementing an interface call a private helper of the interface by name?  
**Answer:** No; private interface methods are not inherited/exposed to implementers.

**Question 22.** Is calling a static method of an interface through an implementing class valid?  
**Answer:** Not in the sense of an inherited member; call `InterfaceName.method()`.

**Question 23.** Why can `private final List<String> tags` still be mutated if Parent's getter returns the list itself?  
**Answer:** Private/final only restricts field access/reassignment; a caller receiving the mutable reference can modify the list.

**Question 24.** A superclass designing a non-negative balance invariant should expose `protected balance` or protected validated methods?  
**Answer:** Usually prefer a private field + protected/public domain operations with validation.

**Question 25.** If a Parent constructor calls an overridable Child method early, what might it read?  
**Answer:** Child fields may still be default 0/null before Child's field initializers/constructor body execute.

**Question 26.** Why can `Parent.class.getDeclaredFields()` show private fields while Child still fails to compile if it accesses the field?  
**Answer:** Metadata/reflective inspection differs from source-level member inheritance/access rights.

**Question 27.** Can a public member nested type of Parent be looked up through Child?  
**Answer:** Yes, under appropriate type inheritance/name lookup conditions, for example `Child.Token`.

**Question 28.** Does inheritance create two separate Parent and Child objects?  
**Answer:** No. `new Child()` creates a single object with the appropriate superclass constructor chain and state.

**Question 29.** Does `private` fields "not being inherited" mean GC deletes Parent's field?  
**Answer:** No. That is an inheritance/access rule, not a GC mechanism.

**Question 30.** When should composition be used instead of inheritance?  
**Answer:** When A needs to use/collaborate with B without a genuine "A is a kind of B" type relationship; composition via a reference is usually more flexible.

## 30. References

- Java Language Specification (Java SE 17), [`8.2 — Class Members](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.2): declared/inherited members, fields, methods, and member types.
- Java Language Specification, [`6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6): `private`, package-private, `protected`, `public`, and protected qualified access.
- Java Language Specification, [`8.4.8 — Inheritance, Overriding, and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8): inherited/overridden/hidden method relationships.
- Java Language Specification, [`8.3 — Field Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3): declaring and hiding fields.
- Java Language Specification, [`8.8 — Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8): constructors and the non-inheritance of constructors.
- Java Language Specification, [`8.8.7.1 — Explicit Constructor Invocations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8.7.1): `this(...)` and `super(...)` in Java 17.
- Java Language Specification, [`9.4 — Abstract Methods and Interface Methods](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.4): public/default/private interface methods.
- Java Language Specification, [`9.3 — Field Declarations in Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.3): interface fields.
- Java Language Specification, [`15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): method lookup and runtime invocation.
- Java Language Specification, [`12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): superclass/subclass portions in object initialization.

## Conclusion

**Inheritance does not mean that a subclass can directly access every member of the superclass.** Fields, methods, and member types are inherited according to member kind and access rules; **private members do not become members for direct use in a subclass**, yet the superclass's private state **still exists** and is managed by superclass constructors/methods within the same object.

Always separate **access control**, **member inheritance**, **overriding/hiding**, and **runtime dispatch**. Private methods are not overridden; fields are not overridden; static methods hide rather than dynamically override; constructors are not inherited; `protected` has package and receiver-type constraints. A sound design usually keeps the representation `private`, exposes **public/protected behavior with clear contracts**, uses `@Override` when genuinely overriding, and only provides extension points for which the superclass can properly protect its invariants.
