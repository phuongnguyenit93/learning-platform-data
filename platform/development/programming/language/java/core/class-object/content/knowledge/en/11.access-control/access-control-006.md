# The `protected` Rule via a Subclass in a Different Package in Java

In Java, **`protected`** has two access paths that must be clearly distinguished: **access from code in the same package** as the declaring class, and **access through inheritance from a subclass in a different package**. The second path has **its own rule regarding the receiver** (the object before the dot) for **instance fields** and **instance methods**.

This is the part that often surprises learners:

~~~java
// In subclass S in a different package from superclass C:
this.protectedMethod();    // May be valid
otherS.protectedMethod();  // May be valid if otherS has type S
// otherC.protectedMethod(); // Usually an error if otherC has type C
~~~

Even though `S extends C` and even though object `otherC` may point to an S instance at runtime, Java still checks **access permissions based on the code location and the static type of the receiver**. The inheritance relationship **does not automatically grant a subclass permission to manipulate the protected state of every object of the superclass**.

This lesson applies to **Java 17+**. It focuses on the `protected` rule via a subclass in a different package, while also explaining foundational conditions, valid/invalid scenarios, `super`, protected constructors, overriding, reference types, generics, static members, and practical notes.

## 1. Where Does the Difference Between Two Packages Come From?

Consider two packages:

~~~text
src/
├── library/
│   └── model/
│       └── Base.java
└── library/
    └── client/
        └── Derived.java
~~~

A class in package `library.model` is **not in the same package** as a class in `library.client`. Having the same `library` prefix in both package names **does not create a special access relationship**.

In Java, a package is specified by a source declaration such as:

~~~java
package library.model;
~~~

The two package names `library.model` and `library.model.internal` are also **different**. A subpackage by name does not inherit package-private or protected access via the same-package path from the parent package.

Example:

~~~java
// File: src/library/model/Base.java
package library.model;

public class Base {
    protected int points = 10;

    protected String label() {
        return "Base";
    }
}
~~~

~~~java
// File: src/library/client/Derived.java
package library.client;

import library.model.Base;

public class Derived extends Base {
    public String show() {
        return this.label() + ":" + this.points;
    }
}
~~~

In `Derived.show()`, both `this.label()` and `this.points` are permitted because `Derived` is a subclass of `Base` and `protected` access applies under the inheritance rule in the appropriate context. However, this **does not mean** that any `Base` object passed into `Derived` permits accessing those two members.

The two files above are **standalone declaration examples** and do not yet have `main`. A complete multi-package program with well-defined stdout will be presented in section 5.

## 2. Remembering the True Nature of `protected`

Before exploring the receiver rule, it is necessary to place `protected` alongside the other access levels:

| Code location accessing a member of class C | `public` | `protected` | Package-private | `private` |
| --- | :---: | :---: | :---: | :---: |
| Directly inside C | Yes | Yes | Yes | Yes |
| Another class in the same package as C | Yes | Yes | Yes | No |
| Subclass S in a different package | Yes | Conditional | No | No |
| Class in a different package, not a subclass | Yes | No | No | No |

**Protected does not mean “subclasses only”.** When class A and class B are **in the same package**, B can access protected members of A via the same-package path even if B does not `extends A`. Conversely, when B is in a different package, protected access requires a subclass relationship and additional conditions.

**Package-private does not mean protected.** A member written without a modifier in a regular class is package-private; a subclass in a different package cannot access it merely because of inheritance.

**Private is not open to subclasses.** Neither a subclass in a different package nor a subclass in the same package is automatically allowed to directly read a private field of the superclass. If a superclass wants to provide data to subclasses, it can define a protected method (or an appropriate public API) instead of exposing a mutable field.

This lesson assumes **the class declaring the member is also accessible** from the code location under consideration; if the superclass is an inaccessible type, type accessibility must also be checked. With named modules, there are also export/readability requirements beyond the four basic modifiers.

## 3. The Most Important Rule: Receiver Type in a Different-Package Subclass

Suppose:

- `C` is a superclass **declaring** a protected instance field or instance method.
- `S extends C` is a subclass located in a **different package**.
- Code using the protected member is inside a **subclass `S` context** that qualifies under the Java Language Specification (JLS `6.6.2).
- An expression `receiver.member` uses the member declared in C.

When accessing a protected **instance** member through a receiver expression, Java requires the **compile-time** type of the receiver expression to be **`S` or a subclass of `S`** according to the corresponding rules.

Example:

~~~java
// Code located inside S extends C,
// S and C belong to two different packages.
void example(S sameType, C baseType) {
    this.protectedMethod();      // Valid
    sameType.protectedMethod();  // Valid

    // baseType.protectedMethod(); // Compile error
}
~~~

On the line `sameType.protectedMethod()`, the parameter is declared with type `S`, satisfying the receiver restriction. For `baseType`, the compiler sees type `C` — **broader than `S`** — so accessing the protected instance member is rejected in a different-package context.

**The compiler is not guessing which object will actually be passed in.** It checks based on the **type inferred/declared at compile time**. A variable `C baseType` can receive a runtime object of `S`, yet the expression `baseType.protectedMethod()` still does not automatically become valid just because the runtime object is S.

### 3.1. Distinguishing Context Permission and Receiver Type

Cross-package protected access requires considering **two independent questions**:

1. **Where is the code located?** Does it genuinely belong to a subclass S context that has permission to access the member declared in C?
2. **If a receiver expression is used for an instance member, what is the type of the receiver?** Is it S or a subtype of S according to the protected access rule?

If only one of the two is satisfied, the call can still be rejected.

For example, a class `Viewer` in the same package as S that is **not a subclass** of C is not allowed to arbitrarily access a protected instance field **declared in C** merely by having a variable of type S.

### 3.2. Within the Same Package as C, This Subclass-Type Receiver Restriction Does Not Apply

In a class belonging to **the same package as C**, a protected instance member can be accessed through a variable of type `C` via the same-package path:

~~~java
// File: model/Peer.java; same package model as C
class Peer {
    int read(C object) {
        return object.protectedField;
    }
}
~~~

This is an illustrative example of the principle and requires a corresponding class C. `Peer` is not a subclass yet still has permission because it is in **the same package**. Therefore, do not apply the formula “the receiver must have type S” to every protected access: that formula is for the case of a **subclass in a different package** accessing a protected **instance** member through a receiver.

## 4. `this`, `super`, Parameters of Type S, and Parameters of Type C

Consider `Derived extends Base` in a different package:

~~~java
package library.client;

import library.model.Base;

public class Derived extends Base {
    public int readSelf() {
        return this.points;       // Valid
    }

    public int readSuperclassView() {
        return super.points;      // Valid
    }

    public int readPeer(Derived other) {
        return other.points;      // Valid: receiver type is Derived
    }

    public int readBase(Base other) {
        // return other.points;   // Error: receiver type is Base
        return other.publicPoints();
    }
}
~~~

This snippet assumes `Base` has a method `public int publicPoints()`. It is an **illustration of access conditions**; the complete program below provides the full source.

Explanation:

- `this.points`: uses the current subclass object; valid.
- `super.points`: accesses the superclass member on the current object using the `super` syntax; valid under the relevant access/lookup rules.
- `other.points` when other is `Derived`: valid under the receiver restriction.
- `other.points` when other is `Base`: invalid in a different-package subclass because the static type is too broad.
- `other.publicPoints()`: valid because it is part of Base's public API, if both the class and the method are accessible.

**`super` does not point to a separate Base object.** When the actual object is Derived, the inherited fields belong to that object; `super` is a way of accessing superclass members according to the language's mechanism.

### 4.1. Runtime Type Differs from Compile-Time Type

~~~java
Base base = new Derived();

// Inside a Derived method, base.points is still rejected
// if the receiver expression has compile-time type Base.
~~~

The runtime object is Derived, yet the variable `base` has compile-time type Base. How the compiler selects a member and verifies accessibility is based on the expression type and source context; runtime dispatch does not erase the permissions already checked at compile time.

This is a very useful principle even outside the topic of protected: **the static type determines which operations are allowed by the compiler**, whereas the runtime class can determine which implementation runs for an overridden instance method.

## 5. Runnable Multi-Package Program: Covering All Key Cases

This example has four files across two packages. It demonstrates:

- Code in the same package as the superclass can read protected members through `Base`.
- A subclass in a different package can read protected members through `this`, `super`, and a subclass-typed receiver.
- A subclass **cannot** read them through a parameter declared with the superclass type.
- External code **cannot** read the original protected member merely with an object reference.
- A static protected method can be used by a subclass in the appropriate context.
- Overridden protected instance methods are still subject to **dynamic dispatch**.

### 5.1. Directory Structure

~~~text
src/
├── library/
│   └── model/
│       ├── Base.java
│       └── Peer.java
└── library/
    └── client/
        ├── Derived.java
        └── Demo.java
~~~

### 5.2. File `src/library/model/Base.java`

~~~java
package library.model;

public class Base {
    protected final String id;

    protected Base(String id) {
        this.id = id;
    }

    protected String label() {
        return "Base";
    }

    protected static String code() {
        return "STATIC";
    }

    public String description() {
        return "Base#" + id;
    }
}
~~~

Class `Base` is public so that a subclass in a different package can `extends Base`. The constructor `Base(String)` is protected; a subclass outside the package can call it using `super(id)`. The field `id` is a protected instance member; the method `label()` is a protected instance method; the method `code()` is a protected static method. `description()` is a public API.

### 5.3. File `src/library/model/Peer.java`

~~~java
package library.model;

public class Peer {
    public static Base create(String id) {
        return new Base(id);
    }

    public static String inspect(Base object) {
        return object.label() + "/" + object.id;
    }
}
~~~

`Peer` does not inherit from Base, yet it is **in the same package `library.model`**. Therefore, `new Base(id)` can call the protected constructor, and `object.label()` and `object.id` are valid even when the receiver has type Base.

### 5.4. File `src/library/client/Derived.java`

~~~java
package library.client;

import library.model.Base;

public class Derived extends Base {
    public Derived(String id) {
        super(id);
    }

    @Override
    protected String label() {
        return "Derived";
    }

    public String fromThis() {
        return this.label() + "/" + this.id;
    }

    public String fromSuper() {
        return super.label() + "/" + super.id;
    }

    public String fromPeer(Derived other) {
        return other.label() + "/" + other.id;
    }

    public String fromBase(Base other) {
        // return other.label() + "/" + other.id;
        // Invalid: the receiver of the protected member declared in Base
        // has compile-time type Base, not Derived.
        return other.description();
    }

    public static String staticInfo() {
        return code();
    }
}
~~~

Invalid lines are commented out so the program can run. `@Override protected String label()` keeps the protected level and replaces the implementation in the subclass; this is allowed because it does not narrow access. Code in Derived can access the protected members through `this`, `super`, or a receiver of type Derived.

### 5.5. File `src/library/client/Demo.java`

~~~java
package library.client;

import library.model.Base;
import library.model.Peer;

public class Demo {
    public static void main(String[] args) {
        Derived first = new Derived("A");
        Derived second = new Derived("B");
        Base base = Peer.create("X");

        System.out.println("This = " + first.fromThis());
        System.out.println("Peer = " + first.fromPeer(second));
        System.out.println("Super = " + first.fromSuper());
        System.out.println("Base = " + first.fromBase(base));
        System.out.println("Same package = " + Peer.inspect(base));
        System.out.println("Dynamic dispatch = " + Peer.inspect(first));
        System.out.println("Static = " + Derived.staticInfo());
        System.out.println("Public = " + first.description());

        // System.out.println(first.id);    // Invalid in Demo
        // System.out.println(base.label()); // Invalid in Demo
        // new Base("T");                    // Invalid in Demo
    }
}
~~~

`Demo` is in the same package as **Derived**, but **in a different package from Base** and is not a subclass of Base. It is not automatically granted permission to access the **field `id` declared in Base** merely because the variable `first` has type Derived. `Demo` can call public methods on Derived to ask Derived to use the protected members validly from the subclass itself.

An advanced detail: `Derived.label()` is a **new protected overriding declaration in package `library.client`**, so code in the same package as `Derived` can access the method declared on Derived via the same-package path. However, that **does not move field `Base.id` into the client package**, nor does it make protected members **declared in Base** suddenly become package-private for all classes in client.

### 5.6. Compiling and Running with JDK 17+

From the directory containing `src`:

~~~bash
javac -encoding UTF-8 -d out src/library/model/Base.java src/library/model/Peer.java src/library/client/Derived.java src/library/client/Demo.java
java -cp out library.client.Demo
~~~

**Exact stdout:**

~~~text
This = Derived/A
Peer = Derived/B
Super = Base/A
Base = Base#X
Same package = Base/X
Dynamic dispatch = Derived/A
Static = STATIC
Public = Base#A
~~~

Interpreting the results:

1. `first.fromThis()` calls `this.label()` (Derived) and reads `this.id` (the field declared in Base), so it returns `Derived/A`.
2. `first.fromPeer(second)` has a parameter of type Derived and is allowed to access protected members on another Derived object, resulting in `Derived/B`.
3. `first.fromSuper()` uses `super.label()` to select the Base implementation, while `super.id` reads the Base field of the current object, resulting in `Base/A`.
4. `first.fromBase(base)` does not attempt to read protected members through the `Base` parameter and instead uses the public `description()`, returning `Base#X`.
5. `Peer.inspect(base)` is located in the Base package, so using the protected `label()` and `id` on a receiver of type Base is valid; the result is `Base/X`.
6. `Peer.inspect(first)` is still permitted access based on the same-package context where method `Peer.inspect` is declared. The call `object.label()` performs **dynamic dispatch** to the override in Derived, so the result is `Derived/A`.
7. `Derived.staticInfo()` calls the inherited protected static method `code()` in an appropriate subclass context, returning `STATIC`.
8. `first.description()` is a public method inherited from Base, returning `Base#A`.

**Access errors to try:** uncomment **one line at a time** that has `//` in `Derived.fromBase` or `Demo.main`, re-run `javac`, and observe the compiler's rejection. Do not uncomment all lines at the same time if you want to tie an error to one exact rule.

## 6. Why Is `otherDerived.protected` Valid While `otherBase.protected` Is Not?

Consider code inside subclass S in a different package:

~~~java
S sameBranch = new S();
C broadType = sameBranch;

sameBranch.protectedField; // Allowed if other conditions are met
// broadType.protectedField; // Rejected: static type C
~~~

Even though **the two variables may point to the same object**, access to a protected instance member is checked **based on the type of the receiver expression** within the subclass S context.

This is not a runtime security mechanism that verifies each object individually. It is a **source-language-level constraint** that restricts how a subclass in a different package uses the protected state of the superclass.

### 6.1. “Any Subclass Can Call It” Is Too Broad a Statement

Suppose:

~~~text
Base
├── Alpha (package x)
└── Beta  (package y)
~~~

`Alpha` and `Beta` both extend Base, but `Beta` **is not a subtype of Alpha**. Inside a method of Alpha, accessing `beta.protectedField` through a variable declared with type Beta is generally **invalid** under the protected instance receiver rule if the Beta/Alpha packages differ from the package declaring the member in Base.

Example:

~~~java
package app.alpha;

import api.Base;
import app.beta.Beta;

public class Alpha extends Base {
    public int inspect(Beta beta) {
        // return beta.protectedValue; // Invalid: Beta is not a subtype of Alpha
        return 0;
    }
}
~~~

This is an illustrative snippet; it requires the corresponding `api.Base` and `app.beta.Beta` classes. Both child branches **each have permission to access protected members from their own context**, but do not have permission to touch a protected instance member on an object of an incompatible subclass branch.

### 6.2. What About a Subclass of S?

If `SportDerived extends Derived` and the code is inside `Derived`, then `SportDerived` is a subtype of Derived. For a receiver declared with type `SportDerived`, the receiver type condition `Derived or subtype` can be satisfied when accessing a protected member of Base within the Derived context.

In other words, **a subclass in a different package is allowed to operate through its own inheritance branch**, rather than accessing every object of type C or a sibling branch.

## 7. Upcast, Downcast, `instanceof`: What Changes and What Does Not?

**Upcasting** a subclass reference to a superclass type can narrow the access visible to the compiler through that reference at the call site:

~~~java
Derived derived = new Derived("A");
Base upcast = derived;
~~~

Inside a method of Derived in a different package from Base:

~~~java
void check(Base upcast, Derived direct) {
    direct.label(); // Valid
    // upcast.label(); // Error due to Base receiver type
}
~~~

Even though `upcast` may be pointing to the exact same object that `direct` points to, the compile-time type of `upcast` is still Base.

### 7.1. Casting Can Change the Static Type of an Expression, but Does Not Grant Permission to All Code

From a permitted subclass context, if you want to handle a Base parameter **only when it is actually Derived**, you can use pattern matching `instanceof` (Java 17):

~~~java
package library.client;

import library.model.Base;

public class TypeCheckedDerived extends Base {
    public TypeCheckedDerived(String id) {
        super(id);
    }

    public static String inspect(Base candidate) {
        if (candidate instanceof TypeCheckedDerived derived) {
            return derived.id; // Valid in this subclass context
        }
        return "Không phải TypeCheckedDerived";
    }
}
~~~

This is a standalone illustrative class that requires `library.model.Base` from the previous section. The pattern variable `derived` has type `TypeCheckedDerived`, so it satisfies the receiver condition when accessing the protected field `Base.id` from the subclass `TypeCheckedDerived` itself. If `candidate` is not of that runtime type, the branch does not execute.

**Casting does not bypass access control:** code in a class outside the package that is **not an eligible subclass** does not automatically gain permission to read `Base.id` merely by casting the receiver to Derived. At the same time, casting does not actually turn an arbitrary Base object into a Derived: an invalid cast can throw a `ClassCastException`.

### 7.2. Dynamic Dispatch Does Not Replace Access Checking

An overridden instance method may execute in the subclass according to the runtime type, but **the call must still be valid with respect to access permissions** based on the caller's compile-time type/context.

For example, `Peer.inspect(first)` in the main program is valid because Peer's code is in the same package as Base. Once the call is valid, `label()` on the Derived object dispatches to the overriding implementation. By contrast, `upcast.label()` written directly inside a subclass in a different package may **fail to compile**, even though the runtime object is also Derived.

**Two distinct steps:**

1. **Compile time:** locate the member, select the overload, and verify access permissions according to Java rules.
2. **Runtime:** for an overridable instance method, locate the appropriate implementation on the actual object.

## 8. `super.method()` and Protected Members on the Current Object

Inside a subclass, `super.method()` selects the appropriate implementation from the superclass according to the `super` invocation rules. This is not a call on a new Base object.

~~~java
class BaseCounter {
    protected int current() {
        return 1;
    }
}

class AdvancedCounter extends BaseCounter {
    @Override
    protected int current() {
        return 2;
    }

    int both() {
        return this.current() + super.current();
    }
}
~~~

`new AdvancedCounter().both()` returns `3`. `this.current()` selects the override returning 2, and `super.current()` selects the superclass implementation returning 1. This is a declaration snippet within the same package to illustrate the implementation selection mechanism; the relationship between `this` and `super` also applies in a different-package subclass when protected access is valid.

**You cannot write `someOtherObject.super.method()`** as a way to freely use an arbitrary superclass receiver. The `super` syntax has a specific context and meaning; it is not an operation that “unlocks” protected members of every object.

## 9. Protected Constructors in a Different Package

A protected constructor differs from a protected instance field/method in that **there is no existing object on which you can use an arbitrary receiver**. It serves to control instantiation paths:

~~~java
// File: src/api/Task.java
package api;

public class Task {
    private final String name;

    protected Task(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }
}
~~~

~~~java
// File: src/app/CustomTask.java
package app;

import api.Task;

public class CustomTask extends Task {
    public CustomTask() {
        super("custom");       // Valid: subclass constructor
    }

    public static void demo() {
        // new Task("other");  // Invalid here
    }
}
~~~

`CustomTask` belongs to a different package from `Task` but inherits from Task, so its constructor can call `super("custom")` to invoke the protected superclass constructor. However, a method of the subclass **cannot use `new Task("other")` as if the protected constructor were public**.

The rule in JLS `6.6.2.2` also specifies special cases involving **anonymous class instance creation** using a protected constructor; you should not simply assume that a protected constructor can **only** ever be invoked via `super(...)` in all cases. However, for a **regular subclass in a different package**, `super(...)` is the most important mechanism to master.

### 9.1. Do Not Confuse with `this(...)`

In a subclass constructor:

~~~java
public CustomTask() {
    super("custom");
}
~~~

`super(...)` calls the superclass constructor. Meanwhile, `this(...)` — when placed at the start of a constructor in Java 17 — delegates to **another constructor in the same class**. Both are governed by constructor invocation rules, which differ from `this.protectedMethod()`.

## 10. `protected` Static Members: Do Not Mechanically Apply the Instance Receiver Rule

The restriction `receiver is S or a subtype of S` above targets **protected instance fields/methods**. Static members belong to the class at the declaration level and do not execute on a specific instance.

Example:

~~~java
// File: api/BaseConfig.java
package api;

public class BaseConfig {
    protected static String category() {
        return "BASE";
    }
}
~~~

~~~java
// File: client/ClientConfig.java
package client;

import api.BaseConfig;

public class ClientConfig extends BaseConfig {
    public static String readCategory() {
        return category(); // Valid in subclass
    }
}
~~~

The two declaration snippets belong to different files. `ClientConfig.readCategory()` is a public static wrapper so external callers can invoke it through a clear API, while `category()` is used from a valid subclass context.

Static members should be invoked using the appropriate class name, or unqualified when there is a reason to do so, avoiding calling static members through an object reference and mistaking that for instance dispatch. **Do not use the instance receiver table to infer all access syntax for static protected members**, because they have their own access/lookup rules.

## 11. Overriding a Protected Method When the Subclass Is in a Different Package

A subclass in a different package can override an inherited **protected instance method**, provided it satisfies the overriding rules, including **not narrowing the access level**.

~~~java
// In package api:
public class Parent {
    protected String format() {
        return "parent";
    }
}
~~~

~~~java
// In package client:
public class Child extends Parent {
    @Override
    protected String format() {
        return "child";
    }
}
~~~

These declarations must be placed in their corresponding files/packages. `Child.format()` keeps protected, so it is valid. Changing it to `public String format()` also **widens visibility** and is valid. Changing it to `private String format()` is rejected by the compiler because it reduces visibility.

### 11.1. Overriding as Public and the Declared Type at the Caller

This is an advanced scenario well worth remembering. Create three files:

~~~text
src/
├── api/
│   └── Node.java
└── client/
    ├── NamedNode.java
    └── UseNode.java
~~~

**`src/api/Node.java`:**

~~~java
package api;

public class Node {
    protected String tag() {
        return "node";
    }

    public String describe() {
        return tag();
    }
}
~~~

**`src/client/NamedNode.java`:**

~~~java
package client;

import api.Node;

public class NamedNode extends Node {
    @Override
    public String tag() {
        return "named";
    }
}
~~~

**`src/client/UseNode.java`:**

~~~java
package client;

import api.Node;

public class UseNode {
    public static void main(String[] args) {
        NamedNode child = new NamedNode();
        Node widened = child;

        System.out.println("Child = " + child.tag());
        System.out.println("Via public = " + widened.describe());
        System.out.println("Via cast = " + ((NamedNode) widened).tag());

        // widened.tag(); // Compile error: Node.tag() is protected
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 -d out src/api/Node.java src/client/NamedNode.java src/client/UseNode.java
java -cp out client.UseNode
~~~

Stdout:

~~~text
Child = named
Via public = named
Via cast = named
~~~

**Detailed explanation:**

- `NamedNode.tag()` is declared **public** in NamedNode, so `child.tag()` is a valid call in client.
- `widened` has **compile-time type `Node`**, in which method `tag()` is declared **protected** in package `api`. Because `UseNode` is neither an eligible subclass nor in the same package as api, `widened.tag()` is **invalid**, even though the actual object is a NamedNode with a public override.
- `widened.describe()` is valid because `Node.describe()` is public. Inside `describe()`, the call `tag()` dynamically dispatches to NamedNode, so the result is `named`.
- `((NamedNode) widened).tag()` has a receiver with compile-time type `NamedNode` whose method is public, and the actual runtime object is NamedNode so the cast is safe. This is not a way to **bypass** the protected rule; it calls **a public method of the subclass type**.

In summary: **a public override does not automatically make a protected method in the superclass public when accessed through a reference declared with the superclass type**.

## 12. Two “Sibling” Subclasses in Different Packages

Consider:

~~~text
api.Base
   |
   +--- client.a.Alpha
   |
   +--- client.b.Beta
~~~

`Alpha` and `Beta` both inherit from Base, yet **neither is a subclass of the other**. Inside a method of Alpha, a parameter of type Beta generally **does not satisfy Alpha's protected receiver rule** when accessing a protected instance member declared in Base.

~~~java
// File: client/a/Alpha.java
package client.a;

import api.Base;
import client.b.Beta;

public class Alpha extends Base {
    public String read(Beta beta) {
        // return beta.protectedText(); // Error: Beta is not Alpha/subtype
        return "Không được truy cập trực tiếp";
    }
}
~~~

This is an illustrative snippet that requires the corresponding `api.Base` and `client.b.Beta` types; it is not a standalone runnable program. Even though Alpha has permission to read protectedText through its own `this`, it **does not have equivalent permission for every Beta instance**.

If Beta provides a **public method** expressing data that is permitted to be exposed, Alpha can call that public method. This is usually a better design than having two sibling subclasses try to read each other's protected state.

## 13. Classes Outside the Package Can Call a Public Wrapper, Not Directly “Borrow” Subclass Access

A public method in a subclass can call a protected helper in the superclass from a valid context and then return data to the caller:

~~~java
// Inside a valid subclass:
public String formattedLabel() {
    return this.protectedLabel();
}
~~~

A caller in a different package that is not a subclass can write `subclass.formattedLabel()` if the method is public and the class is accessible. That **does not mean the caller automatically gains permission to call `subclass.protectedLabel()`** when the protected member is declared in another package and there is no corresponding access path.

This design separates permissions:

- **The superclass** publishes an extension point for subclasses via a protected API.
- **The subclass** actively uses that extension point in a valid implementation.
- **External callers** only see the public API that the subclass or superclass chooses to expose.

A public wrapper is not a compiler trick: it is a **new API contract published by the class designer**. If a wrapper exposes sensitive data, the design should be reconsidered regardless of whether Java allows it to compile.

## 14. How Do the Rules for a Protected Field Differ from a Protected Method?

In terms of **access scope from a subclass in a different package**, protected instance fields and protected instance methods are both subject to the key receiver rule discussed above. However, **runtime behavior** differs:

- Accessing a field such as `other.value` does not have dynamic dispatch like an overridden method. Field hiding in a subclass does not cause a field access to select the field by runtime type the way a virtual method does.
- Calling an instance method `other.readValue()` can dynamically dispatch to an overriding implementation **after** the call is accepted by the compiler.
- `super.value` and `this.value` can differ if the subclass declares a field with the same name; **field hiding** often makes code confusing and should be avoided.
- `super.readValue()` and `this.readValue()` can select different implementations when the method is overridden.

An illustrative same-package example focusing on field versus method:

~~~java
class Parent {
    protected String name = "field-parent";

    protected String name() {
        return "method-parent";
    }
}

class Child extends Parent {
    protected String name = "field-child";

    @Override
    protected String name() {
        return "method-child";
    }

    String explain() {
        return this.name + "/"
                + super.name + "/"
                + this.name() + "/"
                + super.name();
    }
}
~~~

`new Child().explain()` returns `field-child/field-parent/method-child/method-parent`. This is a declaration snippet and has no `main`. In real projects, you should avoid using confusing field and method names or hiding superclass fields unless there is a specific reason.

## 15. `protected` Does Not Mean a Child Object Controls All Parent State

A superclass can use protected to provide part of an extension API for subclasses. However, it still needs to protect **class invariants**:

~~~java
public class BankAccount {
    private long balance;

    public BankAccount(long opening) {
        if (opening < 0) {
            throw new IllegalArgumentException("Số dư âm");
        }
        balance = opening;
    }

    protected final long currentBalance() {
        return balance;
    }

    protected final void addBalance(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Số tiền phải dương");
        }
        balance = Math.addExact(balance, amount);
    }

    public long balance() {
        return balance;
    }
}
~~~

Save this standalone class example as `BankAccount.java` if you want to compile it. Here:

- `balance` is **private**, so a subclass cannot arbitrarily write `balance = -999`.
- The protected `currentBalance()` and `addBalance(...)` methods provide **controlled extension operations**.
- `final` on the methods ensures subclasses cannot override them and break the validation of these operations themselves; however, it does not automatically protect against all concurrency scenarios.
- A subclass in a different package must still obey the protected access rules: calling `this.addBalance(...)` is valid in the appropriate context, without permission to call it on any arbitrary BankAccount object it sees.

**Prefer protected methods with contracts over protected mutable fields.** A protected field tightly couples subclasses to the internal state structure and makes it easy to break invariants. `protected` is a tool to support behavior extension, not a reason to expose nearly all state to every subclass.

## 16. Does the Protected Access Rule Apply Equally to Every Class?

### 16.1. Top-Level Classes Cannot Be Declared `protected`

~~~java
// Invalid if written at top level:
// protected class Helper { }
~~~

A regular top-level class or interface can only have `public` or package-private access. `protected` can apply to a **member type** in permitted contexts, but does not apply as an access modifier to a top-level class.

### 16.2. Interfaces Do Not Declare Protected Instance Methods Like Classes

Abstract interface methods in Java are normally implicitly `public abstract` if appropriate modifiers are omitted. Do not use `protected void act();` in an interface as an extension point like in a class. If you need a protected implementation detail, consider an abstract class or a different API design.

### 16.3. Nested Classes and Protected Member Types Have Their Own Rules

A class can define a protected nested type:

~~~java
public class Outer {
    protected static class Helper {
        protected Helper() {
        }
    }
}
~~~

This is a valid declaration in the file `Outer.java`. The ability to refer to the name `Helper`, instantiate Helper from a different package, and access its constructor is still subject to the appropriate access rules—it is not simply “if a subclass sees `Helper`, anyone can call `new Helper()`”.

The key learning point of this lesson remains **protected instance fields/methods via a subclass in a different package**; do not mechanically apply the exact same receiver check to all constructor, static, and nested-type cases.

## 17. Java Modules Can Further Restrict Using a Public Superclass

If a program uses **named modules** (Java 9+), a public class `api.Base` in a package that is not exported to other modules may not be usable by client code as in the classpath demo.

For example, in `module-info.java` of the module declaring Base:

~~~java
module example.model {
    exports api;
}
~~~

And in the client module:

~~~java
module example.client {
    requires example.model;
}
~~~

These are **separate module declaration snippets**, not two declarations in the same file. Having `exports api` and `requires example.model` establishes module readability/accessibility under JPMS, yet **does not eliminate the protected receiver rule**.

Check in order:

1. Does the client module read the module containing the superclass?
2. Is the package/type declaring the superclass accessible?
3. Does the member have an appropriate access level?
4. If it is a protected instance member accessed through a subclass in a different package, does the receiver type satisfy `S or subtype of S`?

**Module access and protected access are two layers of conditions; they do not replace each other.** The multi-package example in section 5 runs on the classpath so learners can observe the source-level rules clearly without having to configure modules.

## 18. Common Mistakes

| Mistake | Truth |
| --- | --- |
| Thinking `protected` can only be accessed inside a subclass | Other classes **in the same package** can also access protected members |
| Thinking a subclass in a different package can access protected members on any object C | For instance members, the receiver type must be checked to be S or a subtype of S |
| Thinking package `a.b.c` is in the “same package” as `a.b` | They are two different packages |
| Relying on the runtime type S of a variable declared as C to call a protected member | Access permission is checked according to compile-time type/context |
| Thinking `import C` makes protected members public | Importing does not widen visibility |
| Thinking `super.member` creates a new Base object | `super` selects the superclass member on the current object |
| Thinking any sibling subclasses can read each other's protected fields | Not if the receiver does not satisfy the type rule of the subclass where the code is accessing it |
| Thinking `protected Base(...)` allows `new Base(...)` in any method of a different-package subclass | Protected constructors have their own invocation rules |
| Thinking `protected static` shares the same instance receiver rule | Static members are not instance members; their own rules must be considered |
| Thinking a public override makes access through a Base reference automatically public | Compile-time member lookup/access still follows the receiver/declared type |
| Thinking a `private` field can be read directly from a subclass | Private members are not opened up by `extends` |
| Thinking a `protected` field protects invariants as well as a method | Subclasses can modify the field, making it easy to create invalid state |
| Thinking access checking and dynamic dispatch are the same step | Compilation checks permissions; runtime selects the override after the call is valid |
| Thinking `protected` on a top-level class is valid | Top-level classes cannot use protected |

## 19. Self-Check Exercises

**Question 1.** Classes `A` and `B` are in the same package; `A` has `protected int x`. `B` does not inherit from A. Can `B` read `a.x` on a receiver of type A?

**Answer:** Yes, if other conditions are satisfied. Same-package access allows it without requiring B to extend A.

**Question 2.** `S extends C` is in a different package; a method of S writes `this.protectedField`. Is this valid?

**Answer:** Yes, when the member is actually protected and the subclass/access context is valid; `this` is the current S instance.

**Question 3.** Inside the same method of S, `C c` is a parameter; is writing `c.protectedField` valid like `this.protectedField`?

**Answer:** No. If the protected instance member is declared in C in a different package, the receiver type `C` does not satisfy the restriction that it must be `S or subtype of S`.

**Question 4.** Does changing the parameter declaration from `C c` to `S c` change the access condition?

**Answer:** Yes. The compile-time receiver type becomes S, so an appropriate protected instance access from code in S can be valid.

**Question 5.** If `C c = new S();`, does `c.protectedMethod()` automatically become valid inside S?

**Answer:** No. A runtime object belonging to S does not change the compile-time type `C` of the expression `c`.

**Question 6.** If `Alpha extends C` and `Beta extends C` while Beta is not a subtype of Alpha, can code in Alpha in a different package call `beta.protectedMethod()`?

**Answer:** No, under the receiver rule for a protected instance member declared in C, because `Beta` is not Alpha or a subtype of Alpha.

**Question 7.** Can a subclass in a different package use `super.protectedMethod()`?

**Answer:** Yes, in an appropriate context; `super` allows selecting the superclass implementation on the current object according to Java's rules. It is not calling on an arbitrary superclass object.

**Question 8.** Can a subclass constructor in a different package call `super(args)` to a protected superclass constructor?

**Answer:** Yes, when the constructor is accessible and the invocation rules are met. However, `new Superclass(args)` from an arbitrary method inside the subclass is not automatically valid.

**Question 9.** `S` overrides a protected method of C as public. A caller has a variable `S s` and a variable `C c = s`. Why is `s.method()` valid while `c.method()` may be rejected?

**Answer:** `S.method()` has been declared public in S, whereas through compile-time type C, the member is looked up on C with protected access and the caller lacks an appropriate access path.

**Question 10.** `Peer` is in the same package as C and does not extend C. Why can `Peer.inspect(C c)` call a protected instance method on c?

**Answer:** Because protected same-package access does not have the receiver type restriction of a subclass in a different package.

**Question 11.** Do `this.protectedField` and `this.protectedMethod()` have the same runtime characteristics?

**Answer:** Both must be valid in terms of access, but field access does not perform virtual dispatch like an overridable instance method. An overridden method can select its implementation based on the runtime class.

**Question 12.** A client Java module has `requires` for the module containing C, but C's package is not exported. Is a client subclass guaranteed to be able to use public C?

**Answer:** No. Named modules also enforce readability, export, and type accessibility rules; protected access does not abolish module boundaries.

## 20. Checklist When Encountering a `protected has access` Error

1. **Identify where the member is declared:** in which class C and which package is it located?
2. **Identify the package of the calling code:** is it truly in **the same package** as C? Note that a subpackage is not equivalent.
3. **If in a different package:** is the calling code inside an eligible **subclass S of C** context?
4. **For an instance member:** does the receiver expression have **compile-time type S or a subtype of S**?
5. **Check `this` and `super`:** if you need to use the member on the current subclass object, call it through the proper receiver instead of an arbitrary Base parameter.
6. **Look at the declared type, not just the runtime type:** `C x = new S()` still has compile-time type C.
7. **If inside a different-package subclass and wanting to call through a C reference:** consider C's public API or narrowing to the subclass type after a valid runtime type check.
8. **If there are two subclasses on different branches:** do not assume permission to view protected state on a sibling object.
9. **If the member is static, a constructor, or a nested type:** apply its specific rules properly, rather than mechanically copying the instance rule.
10. **If the method is overridden:** distinguish the visibility of the selected declaration from dispatch to the runtime implementation.
11. **If designing an API:** prefer private state and protected methods with clear contracts, avoiding protected mutable fields.
12. **If the code belongs to named modules:** check readability, package exports, and type accessibility beyond the member.
13. **Use `javac` to verify:** test one invalid expression at a time, examine the access/receiver error, and fix the design properly instead of casting arbitrarily.

**Remember:** `protected` in Java **grants access to code in the same package** and **grants conditional access to subclasses in a different package**. In the different-package subclass path, for a **protected instance field/method** accessed through a receiver expression, the static type of the receiver must be **the subclass S containing the access context itself or a subtype of S** according to the JLS rules. Therefore, `this.member` or `peerS.member` can be valid, whereas `baseC.member` is invalid even though the runtime object may belong to S. Properly understanding *package*, *subclass context*, *receiver type*, and *runtime dispatch* helps you use `protected` accurately and design extensible Java APIs without breaking encapsulation.
