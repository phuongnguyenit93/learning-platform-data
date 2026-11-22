# Distinguishing Name Scope and Access Control in Java

## Objectives

After this lesson, you will be able to:

- Independently answer two questions: **"Where can this name be used?"** (*scope/name resolution*) and **"Does this code have permission to access that declaration?"** (*accessibility*).
- Identify the scope of local variables, parameters, loop variables, fields, methods, nested classes, and type names.
- Predict the effect of `this.field`, `Outer.this.field`, `super.field`, and shadowing when multiple declarations share the same name.
- Properly apply `private`, package-private (no modifier), `protected`, and `public` to classes, members, and constructors.
- Understand why `import` does not grant additional access, why `public` does not by itself bypass the limits of the class/module containing the member, and why subclasses in a different package face special rules with `protected`.
- Distinguish between errors related to scope, accessibility, static context, definite assignment, type checking, and runtime errors.
- Understand that nested classes can access private members within the same nest and why two top-level classes placed in the same file do not automatically gain private access to each other.
- Write Java 17+ examples, verify exact stdout, and choose appropriate API designs that encapsulate state.

## 1. Scope and accessibility are not the same concept

In Java source code, there are two concerns that often appear together but must not be conflated:

**Scope (scope of a name declaration):** A declaration of a variable, parameter, field, method, type parameter, class, or interface has regions of source code in which its name can be used/resolved according to Java rules. Scope depends on the structure of classes, methods, blocks, loops, declarations, imports, and name shadowing.

**Accessibility:** Whether code at a given location is permitted to use a type, field, method, or constructor, taking into account Java rules regarding the enclosing class, modifiers, packages, subclasses, nests, and modules.

Comparison table:

| Question | Scope / name resolution | Accessibility |
| --- | --- | --- |
| Goal | Find **which declaration** corresponds to the name being used | Check whether there is **permission to use** that declaration |
| Example | Variable `x` is outside the block, so it cannot be used | Field `secret` exists, but `private` forbids the caller from accessing it |
| Primary basis | Lexical nesting, declaration position, imports, shadowing | `private`/package-private/`protected`/`public` modifiers and caller context |
| Local variables | Have block/method scope | Are not declared `public`/`private` like class members |
| Field/method | Has a name, name resolution rules, and a receiver | Can be blocked by access checks |
| How to fix | Move the declaration, pass a parameter, use the right name/qualification | Design the API, use proper access control, fix the caller/package |

For example, the following two errors **do not have the same cause**:

~~~java
static void demo() {
    if (true) {
        int local = 5;
    }
    // System.out.println(local); // Wrong: local is out of scope.
}
~~~

and:

~~~java
class User {
    private int pin = 1234;
}

class Other {
    void read(User user) {
        // System.out.println(user.pin); // Wrong: private access.
    }
}
~~~

These snippets are **illustrative**; the intentionally invalid lines are commented out so the rest can compile. In the first example, `local` is no longer within name scope. In the second example, the field `User.pin` **does exist**, but `Other` does not have direct access to it.

**Key takeaway:** a name being **recognized** does not necessarily mean it is **permitted to be used**; conversely, a `public` member does not suddenly give a local variable of the same name a wider scope.

## 2. Scope of local variables and parameters

### 2.1. Parameters have method scope

~~~java
static int total(int price, int quantity) {
    int subtotal = price * quantity;
    return subtotal;
}
~~~

Inside the method:

- `price` and `quantity` are **parameters**. Code inside the method body can use their names.
- `subtotal` is a **local variable** declared inside the method body block.
- Code outside the method **cannot directly reference** the names `price`, `quantity`, or `subtotal`.
- That is not because they are `private`: parameters/local variables do not have access modifiers like fields do.

If another method also declares a `price` parameter, it is **a separate variable belonging to that other method**, not the same variable.

### 2.2. Block scope

~~~java
static void run() {
    int outer = 5;

    {
        int inner = 7;
        System.out.println(outer + inner);
    }

    System.out.println(outer);
    // System.out.println(inner); // Invalid here.
}
~~~

The name `outer` can still be used inside the nested block, but the name `inner` can no longer be used once its enclosing block ends. **Scope differs from object lifetime**: an object created inside a block can still stay alive after the block ends if there is a reachable reference to it from elsewhere.

### 2.3. Scope of `for` loop variables

~~~java
for (int i = 0; i < 2; i++) {
    System.out.println(i);
}
// System.out.println(i); // Out of scope for i.
~~~

`i` is declared in the initialization part of the `for` statement. After the loop construct, this declaration can no longer be used by name.

In an enhanced `for` loop:

~~~java
for (String element : new String[] {"A", "B"}) {
    System.out.println(element);
}
// System.out.println(element); // Out of scope.
~~~

Similarly, the variable `element` resides within the appropriate region of the loop and does not automatically become a field of the class.

### 2.4. Cannot declare duplicate local names in overlapping scopes

~~~java
static void example() {
    int count = 1;
    {
        // int count = 2; // Wrong: local declaration with a name already in scope.
        int other = 2;
        System.out.println(count + other);
    }
}
~~~

This is a **name declaration** error and has nothing to do with `public` or `private`. However, a **parameter** having the same name as a class field is a different case: a parameter can **shadow** a field.

### 2.5. Scope differs from definite assignment

~~~java
static int sample(boolean flag) {
    int result;
    if (flag) {
        result = 10;
    }

    // return result; // Wrong: there is an execution path where result has not been assigned.
    return 0;
}
~~~

`result` is within the scope of the method body at the `return` statement, yet the compiler still prevents reading a local variable that has not been **definitely assigned**. This is an **initialization-before-read** rule, not access control. It cannot be fixed by writing `public int result` inside the method.

## 3. Fields, parameters, and local variables with the same name: shadowing

An instance field belongs to the **object**; a parameter/local variable belongs to the scope of a method call or block. They can share the same name without becoming the same variable.

Example:

~~~java
class Counter {
    private int value = 5;

    void set(int value) {
        this.value = value;
    }

    int current() {
        return value;
    }
}
~~~

In `set(int value)`:

- `value` without a prefix refers to the parameter when it shadows the field.
- `this.value` refers to the field of the current `Counter` object.
- `this.value = value;` assigns the **parameter value** to the **instance field**.
- Because `set` is inside the class that declares the field, the code has permission to access the private member. `this` clarifies the **reference target**, not a "privilege to bypass private".

If you write `value = value;`, you only assign the parameter to itself, which is usually a logic bug.

### 3.1. A complete Java 17 program on scope and shadowing

Save **`ScopeAndShadowingDemo.java`**:

~~~java
public class ScopeAndShadowingDemo {
    private String label = "FIELD";

    void show(String label) {
        System.out.println("parameter=" + label);
        System.out.println("field=" + this.label);

        {
            String blockValue = "BLOCK";
            System.out.println("block=" + blockValue);
        }

        for (int i = 0; i < 2; i++) {
            System.out.println("loop=" + i);
        }

        // blockValue and i cannot be used here.
        System.out.println("field again=" + this.label);
    }

    public static void main(String[] args) {
        new ScopeAndShadowingDemo().show("PARAM");
    }
}
~~~

Compile and run:

~~~bash
javac ScopeAndShadowingDemo.java
java ScopeAndShadowingDemo
~~~

Output:

~~~text
parameter=PARAM
field=FIELD
block=BLOCK
loop=0
loop=1
field again=FIELD
~~~

**Analysis:** the parameter `label` shadows the field. `this.label` is used to read the private field; both the block variable `blockValue` and the loop variable `i` go out of scope before the final print statement. There is no access issue in this program even though the field is `private`.

### 3.2. Field hiding and `super`

If a subclass declares a field with the same name as the superclass:

~~~java
class Parent {
    protected int value = 1;
}

class Child extends Parent {
    int value = 2;

    void show() {
        System.out.println(value);
        System.out.println(this.value);
        System.out.println(super.value);
    }
}
~~~

This is an illustrative class snippet without `main`. In `Child.show()`:

- `value` or `this.value` selects the `Child` field.
- `super.value` selects the inherited/corresponding field of the superclass, if access is valid.
- `super` is tied to **inheritance**; it does not mean "local variable in an outer block".

The superclass field remains a distinct member. Name resolution and access control are related yet separate steps.

## 4. Java's four member access levels

Typically, fields, methods, and constructors have the following access modifiers:

| Access level | Declaration | General rule |
| --- | --- | --- |
| **private** | `private int secret;` | Code within the class/nest is permitted; unrelated classes cannot directly access it |
| **package-private** | `int count;` (no modifier written) | Code in the same package has access under standard rules |
| **protected** | `protected int value;` | Same package; outside the package, accessible from an appropriate subclass context, subject to receiver restrictions |
| **public** | `public int value;` | External code can access it if the enclosing class, package/module, and other expressions are all valid |

**Package-private is not a modifier written with the `default` keyword.** Omitting any modifier is what makes it package-private. `default` has a different meaning in interface default methods.

In real-world library classes, it is common to use **`private` for mutable state** and provide public/protected/package-private methods with clear responsibilities instead of exposing every field. This protects the object's **invariants** and makes it possible to change the implementation without breaking callers.

### 4.1. A modifier alone is not enough to determine validity

A call `obj.method()` may also depend on:

1. Is `obj` in scope, and what is its static type?
2. Is the type containing the method accessible?
3. Does the caller have permission to access the method?
4. Is it a static or instance member, and is there an appropriate receiver?
5. Is the method signature applicable to the arguments?
6. Is the package exported from a named module to the caller's module?
7. At runtime, is `obj` `null` or does the method throw an exception?

Among these, (1) belongs to name/scope; (2)(3)(6) belong to accessibility; (4)(5) belong to context/type checking; and (7) is runtime behavior.

## 5. Top-level classes and nested classes have different access declaration rules

For a **top-level class/interface**, a declaration directly at the package level can only use `public` or **no access modifier** (package-private). A top-level class cannot be declared `private` or `protected`.

Example in the file **`LibraryType.java`**:

~~~java
public class LibraryType {
    public String label() {
        return "API";
    }
}

class InternalType {
}
~~~

Both top-level classes are valid in the same file, because there is only one `public` top-level class matching the file name. `InternalType` is package-private: code in another package cannot directly access it by name, even if the file is in the same repository.

For **nested member classes**, other access modifiers can be used:

~~~java
public class Container {
    public static class PublicNested { }
    protected static class ProtectedNested { }
    static class PackageNested { }
    private static class PrivateNested { }
}
~~~

This is a valid `Container.java` class. `Container` being public does not make `PrivateNested` public. If code is in a location without permission to access `Container.PrivateNested`, writing a fuller name or adding an `import` will not solve the problem.

**Note:** non-static member classes also have corresponding access modifiers. Being `static` or non-`static` determines the enclosing instance relationship; it **does not directly change the access level**.

## 6. A private example: the field name exists, but an external class has no access

Save **`PrivateMemberDemo.java`**:

~~~java
public class PrivateMemberDemo {
    private final int secret = 42;

    public int readSecret() {
        return secret;
    }

    public static void main(String[] args) {
        PrivateMemberDemo item = new PrivateMemberDemo();

        System.out.println("same class=" + item.secret);
        System.out.println("external via API=" + Reader.read(item));
    }
}

class Reader {
    static int read(PrivateMemberDemo item) {
        // return item.secret; // Invalid: private access.
        return item.readSecret();
    }
}
~~~

Compile/run:

~~~bash
javac PrivateMemberDemo.java
java PrivateMemberDemo
~~~

Output:

~~~text
same class=42
external via API=42
~~~

**Why the difference?**

- `main` is inside `PrivateMemberDemo` itself, so it has permission to read the `secret` field of a `PrivateMemberDemo` instance.
- `Reader` is a **separate top-level class**. Even though it is placed in the same Java file, it does **not** belong to the same nest as `PrivateMemberDemo`, so it has no permission to read the private field directly.
- `Reader.read` can still use the parameter `item`: **the parameter name is in scope**, and the public method `item.readSecret()` is accessible. The commented-out line `item.secret` is blocked due to **accessibility**, not because the name `item` went out of scope.

This is one of the clearest examples distinguishing the two concepts: **`item` has valid scope**, whereas **`secret` is an inaccessible member** from the call site.

## 7. Nested classes can access private members within the same nest

The `private` rule permits access between classes within the same **nest** under Java's model. An inner class can use a private field of its enclosing class; an outer class can use a private field of an inner class when the corresponding relationship is satisfied.

Save **`NestedPrivateAccessDemo.java`**:

~~~java
public class NestedPrivateAccessDemo {
    private final String owner = "OUTER";

    private class Inner {
        private final String value = "INNER";

        void showOwner() {
            System.out.println("inner reads=" +
                    NestedPrivateAccessDemo.this.owner);
        }
    }

    void run() {
        Inner inner = new Inner();
        inner.showOwner();
        System.out.println("outer reads=" + inner.value);
    }

    public static void main(String[] args) {
        new NestedPrivateAccessDemo().run();
    }
}
~~~

Commands:

~~~bash
javac NestedPrivateAccessDemo.java
java NestedPrivateAccessDemo
~~~

Output:

~~~text
inner reads=OUTER
outer reads=INNER
~~~

- `Inner` is a nested class located inside the lexical context of the outer class.
- `NestedPrivateAccessDemo.this` refers to the **enclosing outer instance**; it is neither a superclass nor a static class literal.
- `inner.value` accesses the nested class's private field from the enclosing class under nest access rules.
- `private` still prevents **classes outside the nest relationship** from arbitrarily accessing those fields.

**Do not infer that two top-level classes in the same file or the same package automatically have private access to each other.** Nest access does not mean file-level access.

## 8. Package-private and same-package access

Package-private access is created by **not declaring an access modifier** on the corresponding member or top-level class.

~~~java
package store;

public class Item {
    int quantity = 5;               // package-private
    protected String type = "BOOK"; // protected
    public String code = "J17";     // public
    private int pin = 12;           // private

    public int showPinForDemo() {
        return pin;
    }
}
~~~

This is the `store/Item.java` source example, used in the following three-file example.

### 8.1. A standalone runnable multi-file example

Create the structure:

~~~text
project/
  store/
    Item.java
    Peer.java
  app/
    Main.java
~~~

**`store/Item.java`**:

~~~java
package store;

public class Item {
    int quantity = 5;
    protected String type = "BOOK";
    public String code = "J17";
    private int pin = 12;

    public int showPinForDemo() {
        return pin;
    }
}
~~~

**`store/Peer.java`**:

~~~java
package store;

public class Peer {
    public static String describe(Item item) {
        return item.quantity + "," + item.type + "," +
                item.code + "," + item.showPinForDemo();
    }
}
~~~

**`app/Main.java`**:

~~~java
package app;

import store.Item;
import store.Peer;

public class Main {
    public static void main(String[] args) {
        Item item = new Item();
        System.out.println("public=" + item.code);
        System.out.println("same package helper=" + Peer.describe(item));

        // System.out.println(item.quantity); // package-private: not allowed.
        // System.out.println(item.type);     // protected: not allowed from app.Main.
        // System.out.println(item.pin);      // private: not allowed.
    }
}
~~~

From the `project` directory, run:

~~~bash
javac -d out store/Item.java store/Peer.java app/Main.java
java -cp out app.Main
~~~

**Stdout:**

~~~text
public=J17
same package helper=5,BOOK,J17,12
~~~

**Explanation:**

1. `Item` is a public top-level class, so `Main` can use the type when no other module restriction applies.
2. `Item.code` is public and can be read directly from `app.Main`.
3. `Item.quantity` is package-private: `store.Peer` in the same package can read it, while `app.Main` in a different package cannot.
4. `Item.type` is protected: `store.Peer` has access because it is in the same package. `app.Main` is in a different package and is not a subclass, so it cannot read it directly.
5. `Item.pin` is private: even `store.Peer` in the same package cannot read it directly. It must go through the public method that `Item` intentionally provides.
6. The two `import` lines in `app.Main` allow using the shorter type names `Item` and `Peer`. They **do not grant new access permissions** to fields.

**Do not apply this PIN-exposure example in a real system**: a public method exposing secret data is only a way to illustrate access control in this lesson. Business APIs require an independent security design.

### 8.2. Two packages with similar dot-separated names are still two different packages

`com.demo` and `com.demo.internal` do not have an "inheritance relationship for package-private access". They are **two separate packages**. You cannot conclude that package-private members are accessible merely from adjacent directory names or being in the same project.

## 9. `protected`: hardest when the subclass is in a different package

`protected` does not mean "only subclasses are allowed to use it", because code in the **same package** can also access a protected member under normal rules.

In a **different package**, protected instance members are subject to additional conditions: the code must be in an **appropriate subclass context**, and the type of the **receiver expression** must satisfy Java's rules. Not every object of the superclass type can be used as a receiver merely because the calling code is a subclass.

### 9.1. A runnable example with two packages

Create:

~~~text
project/
  base/
    Base.java
  child/
    Child.java
~~~

**`base/Base.java`**:

~~~java
package base;

public class Base {
    protected int level = 7;

    protected void ping() {
        System.out.println("Base.ping");
    }
}
~~~

**`child/Child.java`**:

~~~java
package child;

import base.Base;

public class Child extends Base {
    void test() {
        System.out.println("this.level=" + this.level);

        Child other = new Child();
        System.out.println("other.level=" + other.level);

        ping();

        Base arbitraryBase = new Base();
        // System.out.println(arbitraryBase.level); // Not allowed.
        // arbitraryBase.ping(); // Not allowed.
    }

    public static void main(String[] args) {
        new Child().test();
    }
}
~~~

From `project`:

~~~bash
javac -d out base/Base.java child/Child.java
java -cp out child.Child
~~~

**Stdout:**

~~~text
this.level=7
other.level=7
Base.ping
~~~

Explanation:

- `Child` is a subclass of `Base` and is in a different package.
- From an instance method of `Child`, `this.level` and `ping()` are allowed under protected rules.
- `other` has the **static type `Child`**. In this context, `other.level` is valid.
- `arbitraryBase` has the static type `Base`. Even though the code is written inside a subclass, an **arbitrary receiver of type Base** does not satisfy the rule for accessing a protected instance member across packages.
- `import base.Base` only makes the name Base more convenient; it does not make `arbitraryBase.level` valid.

**The protected constructor case:** constructors have their own detailed rules. A subclass in a different package can use the parent constructor in a permitted `super(...)` constructor invocation; do not assume that a protected constructor allows any external caller to instantiate Base with `new Base()`.

To accurately determine complex inheritance cases, refer to JLS 6.6.2 rather than just using the phrase "protected = subclass".

## 10. `import` resolves names, it does not unlock members

An import declares the ability to use a type name:

~~~java
import java.util.ArrayList;
~~~

Afterward, you can write `ArrayList<String>` instead of `java.util.ArrayList<String>` when the context is valid.

However, **import does not**:

- Turn a top-level package-private class into public.
- Make a `private`, package-private, or `protected` field accessible.
- Guarantee that a public member has a valid receiver.
- Change class inheritance, nest membership, or package membership.
- Bypass package export restrictions of named modules.

If a class in another package is **not public**, changing `import package.Internal;` to `package.Internal` does not fix the accessibility error. A fully qualified name only selects the right type name; access permissions must still be satisfied.

Similarly, a wildcard import `import java.util.*;` does **not** automatically import subpackages such as `java.util.concurrent` and does not open private access to any class.

## 11. `static context` differs from accessibility

A static method in the same class has permission to read **private instance fields** of an explicitly provided object, but it does not have a `this` reference to a calling object the way an instance method does.

Save **`StaticMemberContextDemo.java`**:

~~~java
public class StaticMemberContextDemo {
    private int count = 3;
    private static int global = 10;

    private void increase() {
        count++;
    }

    static void print(StaticMemberContextDemo target) {
        // System.out.println(count); // Wrong: missing instance receiver.
        System.out.println("before=" + target.count);
        target.increase();
        System.out.println("after=" + target.count);
        System.out.println("global=" + global);
    }

    public static void main(String[] args) {
        StaticMemberContextDemo object = new StaticMemberContextDemo();
        print(object);
    }
}
~~~

Run:

~~~bash
javac StaticMemberContextDemo.java
java StaticMemberContextDemo
~~~

Output:

~~~text
before=3
after=4
global=10
~~~

- Private accessibility **is satisfied** because `print` is inside the class itself.
- Reading `count` by its simple name as an instance field in a static context lacks an appropriate receiver, so it fails even though the private field is accessible in terms of access control.
- `target.count` and `target.increase()` are valid because there is a `target` receiver.
- `global` is a static field, so it can be used inside a static method without an instance receiver.

If `target == null`, the code can throw a `NullPointerException` when accessing the instance field; **an NPE is a runtime issue**, not a compiler error about scope or private access.

## 12. Constructors and object creation access

A constructor also has an access modifier, independent of the visibility of the class name.

~~~java
public final class Token {
    private final String value;

    private Token(String value) {
        this.value = value;
    }

    public static Token of(String value) {
        return new Token(value);
    }

    public String value() {
        return value;
    }
}
~~~

This is a compilable `Token.java` file. Callers without private access can:

~~~java
Token token = Token.of("A");
~~~

but cannot directly write `new Token("A")` because the `Token(String)` constructor is private, even though **the `Token` type is public** and the name is recognized.

**Note:** if a public class has an explicit constructor **with no modifier**, that constructor is package-private, not automatically public. When a class declares no constructors at all, the compiler applies rules for an implicit default constructor; that is a constructor existence/generation concern and should be kept separate from access.

## 13. Field scope, declaration order, and forward references

Fields are scoped to the class body, unlike local variables which are scoped to a block. Therefore, instance methods of the same class can all access the field:

~~~java
class Counter {
    int total = 5;

    void first() {
        System.out.println(total);
    }

    void second() {
        System.out.println(total);
    }
}
~~~

However, scope **does not guarantee** that every way of reading a field before its declaration is valid. Java has **illegal forward reference rules** for certain cases inside field initializers and initializer blocks.

Intentionally invalid example:

~~~java
// class IllegalForward {
//     int copy = value; // Illegal forward reference.
//     int value = 5;
// }
~~~

You can read a field inside an instance method even if the field is declared later in the source file than the method, whereas in an **initializer context** certain forms of early simple-name reads may be forbidden.

This illustrates additional layers of rules beyond scope and access:

- **Name scope:** the member is declared within the class body.
- **Forward reference restrictions:** certain early read positions are invalid.
- **Initialization order:** default values and field initializers execute in a specific order when an object is created.

Do not fix such errors by changing the field to `public`.

## 14. `public` is still subject to class and module conditions

Suppose:

~~~java
// In package service:
class InternalEngine {
    public void execute() { }
}
~~~

`InternalEngine` is a **package-private** top-level class, even though the `execute()` method is `public`. Callers in another package **cannot** normally use the name `InternalEngine` directly.

In a project using JPMS (`module-info.java`), public types in a package belonging to a named module also depend on **module readability** and whether the package is **exported** to the appropriate caller module.

Illustrative module declaration example:

~~~java
module com.example.library {
    exports com.example.api;
}
~~~

This exports `com.example.api`, without automatically exporting all implementation packages. `exports` controls type/member accessibility at the module level; `opens` relates to *deep reflection* access under JPMS rules and is not a synonym.

## 15. Distinguishing scope, access, type, and runtime errors

| Situation | Primary issue category | How to handle |
| --- | --- | --- |
| Using local `x` after exiting its block | **Scope** | Move the declaration to an appropriate block, pass the value, or return the result |
| Method B directly using a local variable of method A | **Scope** | Pass a parameter or use state with clear ownership |
| Parameter `value` shadows a field of the same name | **Shadowing** | Use `this.value` |
| Top-level class B accesses a private field of A | **Accessibility** | Use an appropriate public API |
| A class in another package reads a package-private field | **Accessibility** | Respect package boundaries, use an accessible method |
| A subclass in another package reads protected on an arbitrary Base receiver | **Protected access** | Use a valid receiver/context or public API |
| A static method accesses an instance field by its simple name | **Static/instance context** | Use an instance receiver |
| An unassigned local variable is read | **Definite assignment** | Assign on every relevant execution path |
| A public method accepts int, but the caller passes String | **Type checking / overload** | Use the right argument/signature |
| An instance reference is null when calling a method | **Runtime NPE** | Check value contracts, avoid invalid null |
| A public class in a non-exported module package | **Module accessibility** | Design exports/readability appropriately |
| A field declared later is read early in an initializer | **Forward reference** | Order initialization according to the rules |

A compiler error can involve **multiple checking layers** at the same time. For example, if a field `private int count` appears inside a static method of an external class: it may lack both access permission and an instance receiver. A good diagnostic approach is to check from name/type to permissions/context, rather than relying solely on a single error message string.

## 16. A process for analyzing a named expression

When reading `object.member` or a simple name `member`, follow this process:

1. **Identify the actual declaration:** is `member` a local variable, parameter, field, method, type, or a package name?
2. **Determine scope:** at this source location, is the simple name still within lexical scope or validly imported/resolved?
3. **Check for shadowing/hiding:** is there a closer parameter/local/field shadowing the declaration you need to use? Use `this.member`, `Outer.this.member`, `super.member`, or an explicit type name when semantically appropriate.
4. **Check the member kind:** static or instance? Is a receiver present if required?
5. **Check accessibility:** modifier, enclosing class, package, nest, subclass, and protected receiver rules.
6. **Check modules:** is the package exported to the caller's module if JPMS is in use?
7. **Check types:** are the receiver's static type, overload, and argument types compatible?
8. **Check initialization:** is the local variable definitely assigned; does the field initializer have a forward-reference restriction?
9. **Distinguish compile-time vs. runtime:** valid code can still throw an exception at runtime, such as a null receiver.

This order helps avoid dangerous "quick fixes" such as changing all fields to `public` or turning per-object instance state into `static` just to make compiler errors go away.

## 17. Common misconceptions

| Misconception | Reality |
| --- | --- |
| "Scope and access modifiers are the same thing." | Scope and accessibility are two distinct sets of rules. |
| "Local variables are private by default." | Local variables do not have `private/public` like members. |
| "A private field does not exist outside its class." | The field still exists; code without permission simply cannot access it directly. |
| "Importing a class lets you read all of its private fields." | Import only enables using the type name; access does not change. |
| "Two top-level classes in the same file can access each other's private members." | Not automatically; a proper nest relationship is required. |
| "Classes in the same package can access every private member." | No; package-private and private are different. |
| "Protected is only for subclasses, not the same package." | The same package also has protected access according to the rules. |
| "Any subclass in another package can read a protected member on any Base object." | No; there are receiver restrictions. |
| "A public field can always be used from anywhere." | The enclosing type, module, receiver, and expression must all be valid. |
| "A static method cannot touch a private instance field." | It can via an object receiver when access is permitted. |
| "Using `this.` bypasses private access." | `this` selects an instance member; it does not grant access on its own. |
| "`Outer.this` is the same as `super`." | One refers to an enclosing instance; the other is tied to inheritance. |
| "If scope is valid, a local variable can definitely be read." | Definite assignment is required before reading. |
| "A field name has class scope, so any forward reference is valid." | Field initializers have their own restrictions. |
| "`public` fixes a local variable going out of its block." | Access modifiers do not alter lexical scope. |
| "If the code compiles, the member cannot cause errors." | Runtime can still produce NPEs, exceptions, or violated invariants. |

## 18. Self-check questions with answers

**Question 1.** A variable `int x` is declared inside a block but read after the closing brace of the block; what kind of error is this?  
**Answer:** Scope. `x` is no longer in scope for use at that location.

**Question 2.** Can `private` be added to a parameter `int value` to narrow its scope?  
**Answer:** No. Parameters/local variables do not have access modifiers like fields; a parameter's scope is determined by the method declaration.

**Question 3.** In `void set(int value) { value = value; }`, why does the field `this.value` not change?  
**Answer:** The parameter shadows the field. The assignment only affects the parameter; to modify the field, you need `this.value = value`.

**Question 4.** Class A has a private field `secret`. Class B is another top-level class in the same file. Can B directly read `a.secret`?  
**Answer:** Not automatically. Being in the same source file does not give two top-level classes the same nest/private access.

**Question 5.** Can a class in the same package read a package-private field of another class?  
**Answer:** Yes, when the declaration and expression are appropriate; unlike a private field.

**Question 6.** Does `import store.Item;` make the package-private `Item.quantity` accessible from the `app` package?  
**Answer:** No. Import only affects how type names are resolved.

**Question 7.** Can a class that is not a subclass, but is in the same package, access a protected field of another class?  
**Answer:** Yes, under protected access rules within the same package.

**Question 8.** A subclass `Child` in a different package can use `Base`'s protected `this.level`, but why can `new Base().level` be forbidden?  
**Answer:** Protected instance access across packages has conditions on the subclass context and the receiver's type; an arbitrary Base object does not automatically satisfy those conditions.

**Question 9.** Can a static method in the same class use `target.privateField`?  
**Answer:** Yes, if target has the appropriate type and is non-null at runtime. However, it cannot use an instance field by its simple name as if it had `this`.

**Question 10.** Can a nested inner class read a private field of its enclosing class using `Outer.this.field`?  
**Answer:** Yes, within a valid enclosing instance/nest context; qualified `this` selects the right object.

**Question 11.** What error occurs in `int n; System.out.println(n);` inside a method?  
**Answer:** The local variable is not definitely assigned, not a lack of private/public permission.

**Question 12.** A package-private top-level class has a public method. Can callers from another package always invoke this method with `new Internal().method()`?  
**Answer:** No. The class containing the member may be inaccessible, even though the method is public.

**Question 13.** A `public Account` class declares `Account() { }` with no modifier. Can callers from another package instantiate it with `new Account()`?  
**Answer:** No: this constructor is package-private. A public class does not automatically make all its constructors public.

**Question 14.** Do two packages `com.demo` and `com.demo.internal` share package-private access?  
**Answer:** No. They are two different packages, even though their names look hierarchical.

**Question 15.** A named module does not export a package containing a public class. Can another module automatically use that class?  
**Answer:** Not by default. JPMS readability/exports must be taken into account.

**Question 16.** A field `count` is declared after the method that uses it. Does the method necessarily fail because the declaration appears later?  
**Answer:** No. Fields have class-body scope. However, early reads in initializers have their own forward-reference restrictions.

**Question 17.** A public method `run(int)` is called with `run("text")`, and there is no other overload. Is this an access error?  
**Answer:** No. The method is public, but the call uses the wrong argument type, which falls under type checking/overload resolution.

**Question 18.** Does `this.field` turn a private field into a public one?  
**Answer:** No. `this.field` selects an instance field; accessibility is still checked based on the call site.

## References

- Java Language Specification, [6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3) — scope of declarations.
- Java Language Specification, [6.4 — Shadowing and Obscuring](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.4) — name shadowing/hiding.
- Java Language Specification, [6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6) — access control for types and members.
- Java Language Specification, [6.6.2 — Details on protected Access](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6.2) — protected conditions with subclasses/receivers in different packages.
- Java Language Specification, [8.3 — Field Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3) — fields and certain restrictions on initializers.
- Java Language Specification, [7 — Packages and Modules](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html) — packages/modules and access boundaries.

## Summary

**Name scope (scope)** answers **"which declaration is the name at this source code position recognized as?"**. **Accessibility** answers **"is the caller permitted to use that type/member under Java access control?"**. A local variable can go out of scope even though it is not `private`; a `private` field can exist yet not be directly readable by another class. `import` assists with type names and does not unlock members; `this` distinguishes the receiver or a shadowed field and does not alter permissions; `protected` in another package also carries receiver restrictions.

Check separately: **scope → name resolution/shadowing → access modifier/package/nest/subclass → static/instance context → types/initialization → runtime**. When you understand each layer of rules, you will explain compiler errors more accurately and design class-object APIs that are both easy to use and preserve encapsulation.
