# Access Control for Top-Level Classes and Member Classes in Java

## 1. Why Distinguish Between Top-Level Classes and Member Classes?

In Java, the keywords `public`, `protected`, `private`, and the case of **omitting an access modifier** affect where source code is allowed to **refer to a type name, call a constructor, and access members**. However, not every type declaration location can use all four access levels.

Two cases need to be distinguished:

- **Top-level class**: a class declared directly at the compilation unit level, not inside the body of another class or interface.
- **Member class**: a class declared directly inside the body of another class, such as `Outer.Inner` or `Outer.Nested`. It can be a **non-static inner class** or a **static nested class**.

**Most important rule:**

> **A top-level class may only use `public` or package-private (omitting the access modifier). A member class declared inside a class may use `public`, `protected`, package-private, or `private`.**

Therefore, `protected class Account { }` and `private class Account { }` are **invalid if `Account` is declared at the top level**; however, `protected class Helper { }` or `private class Helper { }` can be valid when `Helper` is a **member class** inside an appropriate class.

### Visualizing the Declaration Structure

```text
File Outer.java
┌─────────────────────────────────────────────────────────┐
│ package sample;                                         │
│                                                         │
│ public class Outer {         ← top-level class          │
│     public class A { }       ← public member class      │
│     protected class B { }    ← protected member class   │
│     class C { }              ← package-private member   │
│     private class D { }      ← private member class     │
│                                                         │
│     public static class E { } ← static member class     │
│ }                                                       │
│                                                         │
│ class PackageHelper { }      ← package-private top-level│
└─────────────────────────────────────────────────────────┘
```

This is **a valid Java code snippet**. `Outer` and `PackageHelper` are both top-level classes, even though they reside in the same file; whereas classes `A`, `B`, `C`, `D`, `E` are member classes of `Outer`.

**The word "member" is not synonymous with "static".** A `static nested class` is a member class, but a non-static `inner member class` is also a member class. A type's access modifier and the `static` modifier serve **two different purposes**.

## 2. Comparison Table of the Four Access Levels by Declaration Location

| Declaration modifier | Top-level class | Member class inside a class | General meaning |
| --- | --- | --- | --- |
| `public` | **Valid** | **Valid** | Can be accessed from elsewhere subject to the visibility conditions of the enclosing type and module/package |
| `protected` | **Invalid** | **Valid** | Accessible within the same package and in certain subclass contexts in other packages |
| No modifier specified | **Valid** | **Valid** | **Package-private**: accessible from within the same package |
| `private` | **Invalid** | **Valid** | Restricted to the appropriate enclosing top-level type / nest context |
| `static` | **Invalid for a top-level class** | Can be used for a static nested class | Does not create an implicit enclosing instance relationship |
| `final` | Can be used | Can be used | Prevents the class from being subclassed; **not an access modifier** |
| `abstract` | Can be used | Can be used | Cannot be instantiated directly; **not an access modifier** |

For **member interfaces, member enums, and member records**, there are also separate rules regarding `static` status; within the scope of this article, let us focus on **member classes** declared inside a class.

Three questions need to be kept separate:

1. **Is the type name accessible?** For example, from another package, is it permitted to write `Outer.PublicNested`?
2. **Is the constructor accessible?** Having access to refer to the type name **does not necessarily** grant access to write `new` with its constructor.
3. **Are the members inside the type accessible?** A `public` type **does not automatically make all of its fields and methods `public`**.

## 3. What Is a Top-Level Class?

A top-level class is declared directly in a compilation unit, outside the body of any other class or interface:

```java
package school;

public class Student {
    private final String name;

    public Student(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }
}
```

If this public class is saved in **`Student.java`**, the code belongs to the `school` package. The `public` modifier states that the type name `school.Student` can be accessed from contexts outside the package subject to Java's conditions.

Another top-level class may **omit the access modifier**:

```java
package school;

class StudentValidator {
    static boolean valid(String name) {
        return name != null && !name.isBlank();
    }
}
```

`StudentValidator` is a **package-private top-level class**: types in the `school` package can use it, whereas code in the `app` package cannot refer to `school.StudentValidator` in the usual way.

### Not Every Modifier Is an Access Modifier

`final class Utility { }` is a **package-private and final** top-level class; `final` affects inheritance, and does **not** make the class name public.

`public abstract class Shape { }` is a **public and abstract** top-level class; `abstract` affects instance instantiation, and does **not** turn the access level into protected.

**What to remember:** when examining the access level of a top-level class, the only two choices are `public` or **omitting the access modifier**.

## 4. Why Can't a Top-Level Class Be `private` or `protected`?

The following two declarations are **intentionally invalid and do not compile** when placed at the file level:

```java
// private class Secret {
// }
//
// protected class ProtectedSecret {
// }
```

In Java, `private` describes an access level tied to an enclosing context that can be restricted from the outside; whereas a top-level class has no **enclosing class** to which that modifier can be applied like a member class. `protected` serves member access rules in package and inheritance relationships, rather than being a declaration option for a top-level class.

If you want to hide a class at the package level, you typically use:

```java
class InternalCodec {
}
```

If you want to hide a class inside an API class, use a **private member class**:

```java
public class CodecService {
    private static class InternalCodec {
    }
}
```

These are **two different design approaches**:

- A package-private top-level `InternalCodec` can still be accessed by **any class in the same package**.
- The private member type `CodecService.InternalCodec` does not become a public type just because `CodecService` is public.

Beyond access control in Java, library distribution also depends on package/module boundaries; **package-private is not a security mechanism against all forms of reflection or non-standard access**, but rather an access-checking rule of the language.

## 5. Top-Level `public`: A Visible Class Name Does Not Mean Everything Is Public

Consider the file `src/catalog/Item.java`:

```java
package catalog;

public class Item {
    private final String code;

    Item(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    private String secret() {
        return "hidden";
    }
}
```

Another class in the `client` package can **refer to the type name** `catalog.Item` if the appropriate package/module permits it. However, it **cannot** call `new Item("A")` because the `Item(String)` constructor is **package-private**. Nor can it call `item.secret()` because that method is private.

A `public` class **does not automatically make its constructors and fields/methods public**. If you want API clients to create an Item themselves in another package, an accessible constructor or factory is needed:

```java
package catalog;

public class Item {
    private final String code;

    public Item(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }
}
```

The two `Item` snippets above are **two alternative versions**, not placed simultaneously in the same source set. In the second version, `new Item("A")` is valid from another package if the class/package/module is accessible.

### The Default Constructor Also Has an Access Modifier

If the top-level `public class A { }` declares no constructors, Java implicitly declares a **default constructor** with an access level matching the class, which is `public` in this example.

Conversely:

```java
public class A {
    A() {
    }
}
```

The line `A() { }` is an **author-declared constructor**, which is package-private because `public` is not written. From another package, the name `A` is visible, but you **cannot call `new A()`**.

Therefore, do not assume that every no-argument constructor is public.

## 6. Package-Private Top-Level Class: Same-Package Access

The concept of **package-private** has no dedicated `package-private` keyword. It arises when **no access modifier is written** for a type or member in an appropriate context.

Example:

```java
package store.core;

class LocalParser {
    static String parse(String input) {
        return input.trim();
    }
}
```

Within the same package `store.core`, another class is allowed to reference `LocalParser`. However, in the `store.app` package, even though the code is in **the same project**, it **cannot** directly use `LocalParser` because the two packages are different.

### Subpackages Do Not Count as the Same Package

- `store.core` is **one package**.
- `store.core.tools` is **another package**.
- `store.app` is **another package**.

Having package names with a common prefix **does not cause package-private access to be inherited by a subpackage**.

Placing two files in the same physical directory while declaring different packages does not automatically grant access either. The rule relies on the **package declaration and compilation context**, not on "files being close to each other".

## 7. Multi-Package Example: Top-Level public and package-private

Create the file structure:

```text
project/
└── src/
    └── sample/
        ├── core/
        │   ├── PublicGate.java
        │   └── InternalClient.java
        └── app/
            └── ExternalClient.java
```

**File `src/sample/core/PublicGate.java`:**

```java
package sample.core;

public class PublicGate {
    public static String greet() {
        return "public gate";
    }
}

class PackageHelper {
    static String message() {
        return "package helper";
    }
}
```

`PublicGate` is a top-level public class. `PackageHelper` is also a top-level class, but **package-private**. Both reside in the same compilation unit; only `PublicGate` is the public top-level class of the file.

**File `src/sample/core/InternalClient.java`:**

```java
package sample.core;

public class InternalClient {
    public static void main(String[] args) {
        System.out.println(PublicGate.greet());
        System.out.println(PackageHelper.message());
    }
}
```

Because `InternalClient` is in **the same package `sample.core`**, it can refer to `PackageHelper`.

**File `src/sample/app/ExternalClient.java`:**

```java
package sample.app;

import sample.core.PublicGate;
// import sample.core.PackageHelper; // Error if uncommented: class is not public.

public class ExternalClient {
    public static void main(String[] args) {
        System.out.println(PublicGate.greet());

        // System.out.println(PackageHelper.message());
        // Cannot access PackageHelper from another package.
    }
}
```

Compile all three files from the `project` directory:

```bash
javac -encoding UTF-8 -d out src/sample/core/PublicGate.java src/sample/core/InternalClient.java src/sample/app/ExternalClient.java
java -cp out sample.core.InternalClient
java -cp out sample.app.ExternalClient
```

Output from running `InternalClient`:

```text
public gate
package helper
```

Output from running `ExternalClient`:

```text
public gate
```

The `javac -d out` command writes class files according to the package path. Each `java -cp out ...` runs an independent main class. The commented-out error line in `ExternalClient` is meant to show the package-private restriction, not code that needs to be uncommented to run the example.

## 8. File Naming Rule for a Top-Level `public class`

In a typical Java project structure, a compilation unit is named after its top-level public class:

```java
public class Report {
}
```

Save it in **`Report.java`**. If the file is named `Other.java` yet declares `public class Report`, `javac` normally reports that the public class `Report` must be declared in `Report.java`.

There may be additional **top-level package-private classes** in the same source file:

```java
public class Report {
}

class ReportFormatter {
}
```

This is valid content for `Report.java`. `ReportFormatter` is not a member class of `Report` because it is declared **outside the curly braces of `Report`**.

Do not confuse "in the same file" with "in the same class". The `{ ... }` brace structure is what determines whether a type is top-level or a member.

## 9. Member Class: Four Access Levels Inside an Enclosing Class

Consider:

```java
public class Library {
    public static class PublicShelf {
    }

    protected static class ProtectedShelf {
    }

    static class PackageShelf {
    }

    private static class PrivateShelf {
    }
}
```

All of `PublicShelf`, `ProtectedShelf`, `PackageShelf`, and `PrivateShelf` are **member classes** of `Library`.

- `PublicShelf` has **public** access, when the name `Library` is also accessible and other conditions allow.
- `ProtectedShelf` has **protected** access, for code in the same package and subclasses in other packages according to the protected rules.
- `PackageShelf` omits the access modifier, so it is **package-private**.
- `PrivateShelf` has **private** access, not a type that an unrelated outside class can freely name.

The `static` modifier on all four declarations only means that these are **static nested classes**, not depending on an enclosing `Library` instance when creating an object. If `static` is removed from an allowed member class, that class becomes a **non-static inner member class**, while **its access level still follows the declared modifier**.

## 10. Complete Example: All Four Access Modifiers on Member Classes

Let us use a multi-file example to observe the same package, another package, and a subclass.

```text
project/
└── src/
    └── demo/
        ├── api/
        │   ├── Outer.java
        │   └── PackageFriend.java
        └── client/
            ├── Outside.java
            └── OuterChild.java
```

**File `src/demo/api/Outer.java`:**

```java
package demo.api;

public class Outer {
    public static class PublicMember {
        public PublicMember() {
        }

        public String name() {
            return "public member";
        }
    }

    protected static class ProtectedMember {
        public ProtectedMember() {
        }

        public String name() {
            return "protected member";
        }
    }

    static class PackageMember {
        PackageMember() {
        }

        String name() {
            return "package member";
        }
    }

    private static class PrivateMember {
        private String name() {
            return "private member";
        }
    }

    public class InnerMember {
        public InnerMember() {
        }

        public String name() {
            return "inner member";
        }
    }

    public String describePrivate() {
        return new PrivateMember().name();
    }
}
```

In this file:

- Four static nested classes have four different access levels.
- `InnerMember` is a **public non-static member class**, requiring an enclosing `Outer` instance when created from the outside.
- `Outer.describePrivate()` is allowed to use `PrivateMember` and its private `name()` method because the code is within the scope of the appropriate enclosing type.

**File `src/demo/api/PackageFriend.java`:**

```java
package demo.api;

public class PackageFriend {
    public static void main(String[] args) {
        System.out.println(new Outer.PublicMember().name());
        System.out.println(new Outer.ProtectedMember().name());
        System.out.println(new Outer.PackageMember().name());

        Outer outer = new Outer();
        System.out.println(outer.describePrivate());

        Outer.InnerMember inner = outer.new InnerMember();
        System.out.println(inner.name());
    }
}
```

`PackageFriend` is in **the same package `demo.api`** as `Outer`, so it can access the public, protected, and package-private member classes. However, it **cannot directly name `Outer.PrivateMember`** because that class is private; it calls the public method `describePrivate()` on `Outer` to receive the result.

**File `src/demo/client/Outside.java`:**

```java
package demo.client;

import demo.api.Outer;

public class Outside {
    public static void main(String[] args) {
        Outer.PublicMember shelf = new Outer.PublicMember();
        System.out.println(shelf.name());

        Outer outer = new Outer();
        Outer.InnerMember inner = outer.new InnerMember();
        System.out.println(inner.name());

        // new Outer.ProtectedMember(); // Invalid here.
        // new Outer.PackageMember();   // Invalid here.
        // new Outer.PrivateMember();   // Invalid here.
    }
}
```

`Outside` is in another package and is **not a subclass** of `Outer`, so among the example nested types it can only use the **public member classes** with appropriate constructors and members.

**File `src/demo/client/OuterChild.java`:**

```java
package demo.client;

import demo.api.Outer;

public class OuterChild extends Outer {
    public static void main(String[] args) {
        ProtectedMember item = new ProtectedMember();
        System.out.println(item.name());
    }
}
```

`OuterChild` is a **subclass** of `Outer` in another package. In an appropriate subclass context, it can access the inherited **protected member type** by the name `ProtectedMember`. The constructor of `ProtectedMember` is declared **explicitly `public`** to avoid mixing a class-name access error with a constructor access error.

Compile:

```bash
javac -encoding UTF-8 -d out src/demo/api/Outer.java src/demo/api/PackageFriend.java src/demo/client/Outside.java src/demo/client/OuterChild.java
```

Run the programs:

```bash
java -cp out demo.api.PackageFriend
java -cp out demo.client.Outside
java -cp out demo.client.OuterChild
```

Output of `PackageFriend`:

```text
public member
protected member
package member
private member
inner member
```

Output of `Outside`:

```text
public member
inner member
```

Output of `OuterChild`:

```text
protected member
```

**Key takeaway:** a protected member class has access **different from** a public member class and a package-private member class. You cannot simply say "protected is a smaller public" or "protected means only subclasses can use it"; **code in the same package can also access a protected member**, while access from another package has specific inheritance conditions.

## 11. `protected` in Another Package: Pay Attention to Subclass Context

`protected` is the most easily misunderstood part of Java access control.

In general, a **protected member**:

1. Can be accessed from appropriate code in the **same package** as the class that declares it.
2. In **another package**, access is tied to a **subclass context** according to JLS rules; not all code holding a superclass reference variable automatically gains access to a protected member.
3. For **protected instance fields/methods**, receiver expressions in another package are also subject to specific receiver-type restrictions. This rule **cannot be simplified** to "as long as you are inside a subclass, you can access it through any superclass object".
4. For a **protected member class**, in addition to access to the **type name**, you must separately check its **constructor** and the members inside the type.

### Protected Instance Member Example to Distinguish

File `Base.java`:

```java
package access.base;

public class Base {
    protected int number = 7;
}
```

File `Child.java` in another package:

```java
package access.child;

import access.base.Base;

public class Child extends Base {
    public int valid() {
        return this.number;
    }

    public int invalid(Base other) {
        // return other.number; // Invalid from another package.
        return this.number;
    }
}
```

These are **two compilable class files** because the invalid access line has been commented out. `Child` is allowed to read `this.number` of the superclass part on a suitable subclass object itself. However, `other.number` with a receiver of static type `Base` is not automatically valid just because the method is inside `Child`; cross-package protected access has its own receiver rules.

This example is about a **protected field**, used to help understand the subclass relationship. When reading `protected class Member` in the `OuterChild` example, still apply the proper access rules for the **member type** and its own constructor; do not carry over every receiver detail of an instance field to accessing a static nested type.

### Why Does `protected static class Nested` Not Necessarily Allow Object Creation Everywhere?

Given:

```java
public class Host {
    protected static class Nested {
        protected Nested() {
        }
    }
}
```

A subclass of `Host` in another package can access the name of the protected member type in an appropriate context, yet `new Nested()` is also subject to the **access rules for `Nested`'s protected constructor**, which is **a separate constructor**. If the subclass of `Host` is not a subclass of `Nested`, calling Nested's protected constructor from another package may be rejected. This is why the complete example in section 10 uses **`public ProtectedMember()`**.

**Diagnostic workflow:** check "is the class accessible?" first, and then check "is the constructor accessible?"; do not treat the two answers as one.

## 12. `private member class`: Hiding Details Inside the Enclosing Type

A **private member class** is commonly used to hide an implementation, helper, state machine, or object that serves only the enclosing class.

Create the file **`PrivateNestedDemo.java`**:

```java
public class PrivateNestedDemo {
    private final String prefix;

    public PrivateNestedDemo(String prefix) {
        this.prefix = prefix;
    }

    private static class Token {
        private final String text;

        private Token(String text) {
            this.text = text;
        }
    }

    private class Renderer {
        private String render(Token token) {
            return prefix + ":" + token.text;
        }
    }

    public String render(String text) {
        Token token = new Token(text);
        Renderer renderer = new Renderer();
        return renderer.render(token);
    }

    public static void main(String[] args) {
        PrivateNestedDemo demo = new PrivateNestedDemo("item");
        System.out.println(demo.render("42"));

        // Token token = new Token("x"); // Inside main of the enclosing class,
        // this access can be valid, because it still belongs to the enclosing type.
    }
}
```

```bash
javac PrivateNestedDemo.java
java PrivateNestedDemo
```

```text
item:42
```

Within the same enclosing top-level class `PrivateNestedDemo`:

- `render` can create `Token` and `Renderer`, even though those member classes are private.
- `Renderer` is a non-static inner class, so it has an enclosing `PrivateNestedDemo` instance and can use the `prefix` field.
- `Token` is a static nested class and does **not** have an implicit enclosing instance; it only holds the `text` data passed to it.
- The private member `Token.text` is still validly accessed from `Renderer` within the same appropriate **nest**.

**Important:** `private` does not mean "only lines directly inside the private class itself may refer to its name". The enclosing class and nestmates in relationships permitted by the language can access each other's private members. In modern Java, the JVM has a *nestmates* mechanism to support these access relationships; for learners of Java source code, it is sufficient to remember the appropriate lexical/enclosing rules.

Outside the permitted scope, an unrelated class cannot write `new PrivateNestedDemo.Token("x")` because `Token` is private, even though `PrivateNestedDemo` is public.

## 13. How a Static Member Class Differs from a Non-Static Inner Member Class

Let us separate the **access modifier** from **static**:

| Characteristic | `public static class Nested` | `public class Inner` |
| --- | --- | --- |
| Is it a member class? | Yes | Yes |
| Type name accessibility | Follows `public`, enclosing type, module | Follows `public`, enclosing type, module |
| Has an implicit enclosing outer instance? | No | Yes |
| Instantiation from external code | `new Outer.Nested()` when constructor is accessible | `outer.new Inner()` when constructor is accessible |
| `this` inside an instance method | Only the Nested instance | Only the Inner instance |
| `Outer.this` | No implicit outer instance | Can be used in an appropriate inner context |
| Accessing private outer state | Through a specific Outer reference or appropriate static member | Can use the enclosing instance |
| Typical purpose | Helper type tied to the API name, not tied to an outer object | Type tied to each outer instance |

### Runnable Example: Both Public, Different Instantiation

File **`NestedVsInnerDemo.java`**:

```java
public class NestedVsInnerDemo {
    private final String title;

    public NestedVsInnerDemo(String title) {
        this.title = title;
    }

    public static class Id {
        private final int value;

        public Id(int value) {
            this.value = value;
        }

        public String display() {
            return "ID=" + value;
        }
    }

    public class Description {
        private final String detail;

        public Description(String detail) {
            this.detail = detail;
        }

        public String display() {
            return NestedVsInnerDemo.this.title + "/" + detail;
        }
    }

    public static void main(String[] args) {
        Id id = new NestedVsInnerDemo.Id(3);

        NestedVsInnerDemo outer = new NestedVsInnerDemo("Java");
        NestedVsInnerDemo.Description description =
                outer.new Description("access");

        System.out.println(id.display());
        System.out.println(description.display());
    }
}
```

```bash
javac NestedVsInnerDemo.java
java NestedVsInnerDemo
```

```text
ID=3
Java/access
```

`Id` and `Description` are both **public**, but only `Description` is an inner class that requires a `NestedVsInnerDemo` instance. Therefore, the syntax `new NestedVsInnerDemo.Description(...)` from a static method is not valid without an enclosing instance.

Conversely, `Id` being static nested does **not** make `Id.display()` a static method: each `Id` instance still has its own `value` and can use `this` inside an instance method.

## 14. Package-Private Outer Class: A Public Nested Type Is Not Necessarily Usable Outside the Package

Consider:

```java
package internal;

class HiddenOuter {
    public static class VisibleInside {
        public String value() {
            return "visible name inside hidden outer";
        }
    }
}
```

`VisibleInside` is declared **public**, yet `HiddenOuter` is a **top-level package-private class**. From another package, code cannot refer to `internal.HiddenOuter` via ordinary Java access, and therefore **cannot directly name `internal.HiddenOuter.VisibleInside`** either.

In other words:

> To write `Outer.Member` from an external location, the access conditions of **both `Outer` and `Member`** must be satisfied, along with related factors such as constructor/module/package.

A member's modifier does not "pierce through" an inaccessible enclosing class to automatically become a public API via that qualified name.

### Multi-Level Nesting

```java
public class PublicOuter {
    private static class PrivateMiddle {
        public static class PublicLeaf {
        }
    }
}
```

`PublicLeaf` may be public **relative to its declaration inside `PrivateMiddle`**, but unrelated outside code cannot use `PublicOuter.PrivateMiddle.PublicLeaf` when `PrivateMiddle` is private. The name at every step in the qualification chain must be accessible.

**Advanced note:** It is still possible to provide an object under a **public supertype** or through another public API without letting clients name the private runtime implementation. That does not turn the implementation type into an accessible class.

## 15. Public Member Class with a Package-Private Constructor: A Common Mistake

Example:

```java
package library;

public class Catalog {
    public static class Entry {
        Entry() {
        }

        public String name() {
            return "entry";
        }
    }
}
```

From the `app` package, a caller can **write the type `Catalog.Entry`** because both `Catalog` and `Entry` are public, yet:

```java
// Catalog.Entry entry = new Catalog.Entry();
// Error if in another package: Entry() is not public.
```

The `Entry()` constructor is **programmer-declared** without writing `public`, so it is package-private. The fix (if the API intends for callers to instantiate the object):

```java
public static class Entry {
    public Entry() {
    }
}
```

This is an **alternative version** of the inner declaration, not to be duplicated inside the same class.

If **no constructor is explicitly declared** for a public member class, the default constructor gets its access level according to the corresponding rules. However, when a library API needs to clearly guarantee constructor callability, writing an explicit public constructor helps readers see the contract.

### Method Access Is Another Separate Step

```java
public static class Entry {
    public Entry() {
    }

    String internalName() {
        return "hidden to other package";
    }

    public String name() {
        return "public name";
    }
}
```

Outside the package, a caller can create an `Entry` and call `name()`, but cannot call `internalName()` (because the method is package-private). The access rights of the type, constructor, and methods must be checked **at each level**.

## 16. Inheriting a Public/Protected Nested Type Does Not Mean Inheriting an Enclosing Instance

If `Child extends Outer`, member types can participate in inheritance/name resolution according to Java's rules, but that **does not turn a `Child` object into an `Outer.Nested` object**.

Example:

```java
class Outer {
    protected static class Helper {
        static String name() {
            return "helper";
        }
    }
}

class Child extends Outer {
    String call() {
        return Helper.name();
    }
}
```

The two classes are in the same package and are **valid declarations**. `Helper` is a static nested class of `Outer`; `Child` can access the member type name through the inheritance relationship and appropriate protected access. However, `Helper` is not a superclass of `Child`; therefore:

- `new Child()` does **not** automatically create a `Helper` instance.
- `Helper` can be instantiated separately if it has an accessible constructor and it is needed.
- `Child` does not have an "is-a Helper" relationship.
- `Helper` is a **member type**, not an instance field or an object automatically contained in every `Outer`.

For a **non-static inner class**, the matter of the enclosing instance is separate: each inner instance is bound to an appropriate outer instance; public/protected/private access modifiers do not automatically change that binding.

## 17. Member Classes Inside an Interface Have Different Rules

A member type declared inside an **interface** has its own modifier rules; you should not apply the member class table for an enclosing class verbatim to an interface.

Example:

```java
interface Api {
    class Result {
        public String status() {
            return "ok";
        }
    }
}
```

`Api.Result` is a **member class of the interface**, having **public static** characteristics according to the language rules. It does **not** need an enclosing `Api` instance to be created (and an interface generally does not have an instance of its own to provide like an outer class).

A class inside an interface cannot arbitrarily be declared `private` or `protected` like a member class inside the body of a class. The rules for nested types of an interface serve the API contract and differ from ordinary inner member classes.

To avoid confusion, in exercises check whether the declaration location is actually:

1. **Top-level class**.
2. **Member class inside a class**.
3. **Member type inside an interface**.
4. **Local class** inside a block/method.
5. **Anonymous class**.

These positions **do not share an identical set of access modifiers**.

## 18. Local Classes and Anonymous Classes Are Not Member Classes

A **local class** is declared inside a block, usually inside a method:

```java
class Service {
    void run() {
        class LocalTask {
            void execute() {
                System.out.println("run");
            }
        }

        new LocalTask().execute();
    }
}
```

`LocalTask` is **not** a member class of `Service`; it is a local class, whose name scope is tied to the block. You cannot use `public class LocalTask`, `protected class LocalTask`, or `private class LocalTask` at a local class position like member class access modifiers. Other constraints on capturing local variables may also apply.

An **anonymous class** has no source name like `Outer.Nested`:

```java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("run");
    }
};
```

This is a **code snippet inside a method**. An anonymous class cannot be assigned a class declaration access modifier such as `private class ...` because it does not have a declaration of the same form as a member class.

Thus, identifying the **syntactic structure** (top-level/member/local/anonymous) is the first step before deciding whether a modifier is valid.

## 19. Packages, Modules, and Accessibility in Java 9+

In a project using the **Java Platform Module System (JPMS)**, a `public` top-level class can still be **inaccessible from another module** if the package containing it is not appropriately exported.

Example module declaration:

```java
module academy.core {
    exports academy.api;
}
```

Suppose this module contains:

- `academy.api.PublicCourse`: a public top-level class in an exported package.
- `academy.internal.InternalService`: a public top-level class in a **non-exported** package.

A client module:

```java
module academy.client {
    requires academy.core;
}
```

Code in `academy.client` can reference `academy.api.PublicCourse` if other conditions are met, yet it is **not automatically allowed** to access `academy.internal.InternalService` just because that class carries the `public` modifier. The reason is that the `academy.internal` package is not exported to the client module.

The two `module-info.java` snippets above are **illustrative configuration snippets**, not standalone runnable Java programs. On a classpath without a corresponding named-module boundary, package visibility resolution behaves differently. When encountering a module access error, inspect `module-info.java`, `requires`, `exports`, and the actual compile/run mode.

### How `exports` Differs from `opens`

- `exports` primarily permits access to **public types/public members** of a package from another module according to module rules.
- `opens` primarily serves **deep reflection** under appropriate module conditions, rather than making every package-private/private type public in ordinary source code.
- Reflection has its own access and module checks; the existence of reflection techniques **does not change** the source-level access modifier rules being studied.

Do not immediately label "Java cannot see the public class" as a modifier error without first checking the **package/module** in a project using JPMS.

## 20. When Should You Use Which Access Level?

### Public top-level class

Use when a type represents a **public API** that users in other packages need to name directly, such as `public class Order` or `public interface PaymentGateway`. However, this does not mean every method/field must be public.

### Package-private top-level class

Use for an implementation that only serves **classes in the same package**, such as an internal parser, mapper, or helper. This allows better control over the API surface instead of exposing every type just so it can be used within the project.

### Public member class

Use when an auxiliary type is genuinely part of the public model tied to the enclosing type, such as `Map.Entry` or an appropriately designed result/configuration type. Also consider static vs. inner so users have a clear way to instantiate the object.

### Protected member class

Use when designing an **extension point** for intentionally supported subclasses. Write a clear inheritance contract and think through the constructor/method visibility of the nested type; do not assume this is a general API for all clients.

### Package-private member class

Use for a helper type tied to the enclosing type that **only classes in the same package** need to see. Avoid exposing it to code in other packages in public signatures if callers cannot refer to its name.

### Private member class

Use to hide an **implementation detail**, helper class, internal iterator, or state serving only the enclosing class. It keeps clients from depending on internal types, though it does not by itself make data immune to all forms of reflection/serialization/other libraries.

**Design principle:** choose the **narrowest access level that fits the actual contract**, and then intentionally widen it when needed. Once a `public` type is used by external libraries, narrowing its access level can be difficult without breaking client compilation.

## 21. Common Compilation Errors and Reasoning Mistakes

| Error or misconception | Correct explanation |
| --- | --- |
| "Top-level classes can use `private` and `protected` too" | No; only `public` or package-private |
| "Omitting a modifier means `public`" | No; that case is package-private |
| "A subpackage is the same package" | No; `a.b` and `a.b.c` are two different packages |
| "Two files in the same folder share package-private access" | You must check the package declaration, not just the directory path |
| "Every nested class is an inner class" | A static nested class does **not** have an implicit enclosing instance |
| "`static` on a nested class is an access level" | `static` is not an access modifier |
| "A public outer class means every member class is public" | Each member class has its own access modifier |
| "A public member class is visible even if the enclosing class is private" | You must check the entire enclosing type accessibility chain |
| "Permission to name a nested type means permission to call its constructor" | The constructor also has its own access level |
| "`protected` is only for subclasses; same-package code cannot use it" | Code in the same package also has appropriate protected access |
| "Extending a class allows calling any protected member through any Base receiver" | Cross-package protected access also has specific subclass/receiver rules |
| "A private member class can never be accessed by the outer class" | The enclosing type/nestmates have appropriate private access |
| "A local class inside a method is a member class" | A local class has different scope and modifier rules |
| "A public top-level class can automatically be instantiated with `new` everywhere" | You must consider its constructor, abstract modifier, package, and module |
| "Member classes and top-level classes differ only by a dot in the name" | They also differ in access, enclosing instance, and naming rules |
| "A protected member class has a public default constructor for clients" | Constructor access must be checked separately; it may not be accessible |
| "A `public` class in an unexported module package is automatically accessible" | JPMS adds a module exports boundary |
| "`final` and `abstract` are access modifiers" | They affect inheritance/instantiation, not public/private visibility |
| "A compilation unit may have only one top-level class" | Additional appropriate package-private top-level types may be included |
| "A file `Outer.java` with class `Helper` at the end means Helper is nested in Outer" | It is only nested if declared inside the braces of Outer |

## 22. Diagnostic Checklist for "class is not public" or "has private access"

When the compiler reports a type/constructor access error, check in order:

1. **Determine whether the target class is top-level, member, local, or anonymous**. For a member class, is the enclosing declaration a class or an interface?
2. **Check the package names of both sides**. Are they truly the same package, or do they only share a prefix?
3. **Check the access modifiers of the top-level/enclosing types**. Is every segment of `Outer.Inner` accessible?
4. **Check the access modifier of the member class**: `public`, `protected`, package-private, `private`.
5. **If it is `protected` in another package**, verify that the code is in a valid subclass context and check the corresponding receiver/qualification conditions.
6. **Check the target constructor**: does one exist with the right parameters, and is it accessible? An accessible class alone is not enough.
7. **Check the fields/methods inside the class**: they can be private or package-private even when the class is public.
8. **If the member class is non-static**, check the enclosing instance and the `outer.new Inner()` syntax in the appropriate context.
9. **If the member class is static**, use the `new Outer.Nested()` syntax when valid; no outer object is needed.
10. **Check the public top-level class and source file name**, especially when the compiler reports that the public class must be in the corresponding file.
11. **If using named modules**, check `requires` and `exports` to avoid confusing module boundaries with access modifiers.
12. **Choose a fix that fits the design**: do not automatically turn every class/method/constructor into `public` just to get past a compile error.

### Access Errors and Instantiation Errors Are Two Different Kinds

Example:

```java
public abstract class AbstractService {
}
```

This class may be **public**, yet `new AbstractService()` is still **invalid** because it is abstract. If the constructor is `private` or an inaccessible package-private constructor, the error is instead a constructor access error. If the top-level class is package-private in another package, the error may be in **type-name access**.

Compiler messages typically look like `is not public in ...; cannot be accessed from outside package`, `has private access`, `has protected access`, or `constructor ... is not applicable`. The exact wording may vary by JDK/context, but diagnosis should identify **which access step failed**.

## 23. Self-Check Exercises with Answers

**Question 1.** Is `private class X {}` valid at the top level of a Java file?

**Answer:** No. Top-level classes only allow `public` or package-private.

**Question 2.** What access level does `class X {}` have at the top level of a file?

**Answer:** Package-private, because there is no access modifier.

**Question 3.** Is `public class Outer { private static class Hidden {} }` valid?

**Answer:** Yes. `Hidden` is a **private member class**, not a top-level class.

**Question 4.** Can a class in `app.client` use a package-private class in `app.core`?

**Answer:** Not through ordinary Java source access. These are two different packages, even though they share the `app` prefix.

**Question 5.** Within the same package as `Outer`, can you use `Outer`'s `protected static class Helper`?

**Answer:** Yes, provided other applicable conditions such as constructor/member access are met; protected allows access from the same package.

**Question 6.** Can a subclass in another package automatically call every protected constructor of a nested type?

**Answer:** No. Access to the **member type** and permission to call the **constructor** are two separate steps, with specific protected constructor rules.

**Question 7.** How do `public static class Id` and `public class Description` inside `Outer` differ in terms of access?

**Answer:** Both are public member classes, but `Id` is static nested and does not require an enclosing instance; `Description` is a non-static inner class and requires an appropriate outer instance.

**Question 8.** If `Outer.Nested` is public but `Outer` is not accessible from the call site, can that qualified name be used directly?

**Answer:** No; the enclosing type's access conditions must also be satisfied.

**Question 9.** Can the class `public class A { A(){} }` be instantiated with `new A()` from another package?

**Answer:** No; the explicit constructor `A()` is package-private because `public` is not written.

**Question 10.** Inside a public class, can a private member class contain a public method?

**Answer:** Syntactically yes. However, external code cannot directly name or instantiate the private nested type; its public method does not turn the nested type itself into a public API.

**Question 11.** Can a top-level public class be declared together with a top-level package-private class in the same file?

**Answer:** Yes; they remain **two top-level types**, not a member class relationship.

**Question 12.** Can a static nested class use `this` inside its own instance method?

**Answer:** Yes. That `this` refers to the instance of the static nested class. It has no implicit `Outer.this` like a non-static inner class.

**Question 13.** If a public type resides in an unexported package of a named module, can another module automatically refer to its name?

**Answer:** Not through ordinary module access, because the package has not been appropriately exported.

**Question 14.** Are `protected` and `final` the same kind of modifier?

**Answer:** No. `protected` controls member access; `final` restricts inheritance/overriding or assignment depending on where it is used.

**Question 15.** Can a local class inside a method be declared as `private class Local {}`?

**Answer:** No. Local classes do not use the four access modifiers like member classes.

## 24. Maintainable API Organization Pattern

A common organizational approach is to have a **top-level public API** serve as the external entry point, while helper types are exposed only as needed.

Single-file example **`OrderService.java`**:

```java
public class OrderService {
    public static final class Result {
        private final String message;

        public Result(String message) {
            this.message = message;
        }

        public String message() {
            return message;
        }
    }

    private static final class Validator {
        private Validator() {
        }

        static void requireNonBlank(String text) {
            if (text == null || text.isBlank()) {
                throw new IllegalArgumentException("text required");
            }
        }
    }

    public Result create(String code) {
        Validator.requireNonBlank(code);
        return new Result("created:" + code);
    }

    public static void main(String[] args) {
        OrderService service = new OrderService();
        Result result = service.create("A1");
        System.out.println(result.message());
    }
}
```

```bash
javac OrderService.java
java OrderService
```

```text
created:A1
```

**Notable points:**

- `OrderService` is a public top-level class, serving as the API entry point.
- `Result` is a public static member class so callers receive a clearly named result type. `final` prevents subclassing `Result` without affecting `public`.
- `Validator` is a private static member class; clients do not need to know about or depend directly on this type name.
- `create` is a public instance method that uses the private helper to validate and return a public result.
- No outer instance is needed just to create a `Result` elsewhere, because Result is static nested; conversely, calling `create` requires an `OrderService` instance in this example.
- Designing a public API surface with private helpers makes it easier to change the implementation later with minimal impact on clients.

**Design note:** placing a private helper inside a public outer class is not always optimal. If multiple classes in the package need to reuse the helper, consider a top-level package-private helper instead of trying to nest all logic inside a single class.

---

**Final takeaway:** Access control for a **top-level class** has exactly two choices: **`public`** or **package-private**. A **member class inside a class** may be **`public`, `protected`, package-private, or `private`**; `static` determines whether there is an implicit enclosing instance, **not** the access level. To use a nested type from elsewhere, you must check **enclosing type → member type → constructor → method/field**, along with package, subclass, and module boundaries. Choose the narrowest scope that satisfies the API so the code both compiles properly and avoids exposing unnecessary implementation details.
