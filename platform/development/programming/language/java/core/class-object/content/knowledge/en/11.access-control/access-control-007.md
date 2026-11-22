# `private` Access Between Nested Classes in the Same Enclosing Class in Java

In Java, `private` is often explained as "only the declaring class can access it." This explanation is helpful when first learning, but **incomplete when nested classes are involved**. Within the same **top-level enclosing class**, Java allows the enclosing class and the classes declared nested inside it to access each other's `private` members according to the language's access rules. That access also applies to sibling nested classes within the shared scope, provided the access expression has the right type and the right instance/static context.

For example, a nested class can read a `private` field of the enclosing class. Conversely, the enclosing class can invoke a `private` constructor of a nested class and read a `private` field of a nested class object. Two sibling nested classes can also access each other's `private` members. **There is no need to change `private` to package-private or `public` just so components within the same enclosing class structure can collaborate.**

This article belongs to Java Core — *class-object*, in the **Access Control** group. The examples use **Java 17+**, distinguishing `static nested class`, *inner class*, local/anonymous classes, restrictions on independent external classes, along with misconceptions related to `this` and the *nestmates* mechanism.

## 1. Reviewing `private` and Nested Class Structure

A **private member** can be a field, method, constructor, member type, or another member that Java allows to be declared `private`. `private` restricts access from code outside the permitted scope; it **does not mean** that all code inside the nested structure is blocked from accessing each other's private members.

Example structure:

~~~java
public class Container {
    private int secret = 10;

    private static class StaticHelper {
        private int helperCode = 5;
    }

    private class InnerHelper {
        private String label = "inside";
    }
}
~~~

The snippet above is a **valid illustrative class**, without `main` yet. Here:

- `Container` is the enclosing *top-level class*.
- `StaticHelper` is a **static nested class**: a member type declared `static`.
- `InnerHelper` is a **non-static member class**, often called an *inner class* for short.
- Both member types are declared `private`; independent code outside `Container` cannot arbitrarily write `Container.StaticHelper` to use this private type.
- However, code inside `Container` and the classes nested within that structure can access the appropriate `private` members.

**Note on scope:** "Same `.java` file" and "same package" are **not** conditions that grant `private` access. The important rule is the **enclosing/nested class relationship** within the same top-level structure, not the physical location of the file.

## 2. Access Rule: Within the Same Top-Level Enclosing Class

For a `private` member declared in class `C`, Java determines access within the scope of the **top-level class or interface enclosing the declaration of `C`**, according to the accessibility rules in JLS §6.6.1.

This can be remembered with a diagram:

~~~text
Outer (top-level)
|
+-- private field / method of Outer
|
+-- private static class A
|     +-- private field / method of A
|
+-- private class B (inner)
|     +-- private field / method of B
|
+-- class C
      +-- code can access private members of A, B, Outer
          if there is an appropriate object/context

Code belonging to top-level class Khac outside the Outer structure
does not have this private privilege merely from being in the same package or same file.
~~~

Four access directions to distinguish:

| Direction | Allowed by Java? | Practical condition |
| --- | --- | --- |
| Nested class reads `Outer.privateField` | Yes | Must have an **Outer object** if it is an instance field |
| Enclosing class reads `Nested.privateField` | Yes | Must have a **Nested object** if it is an instance field |
| Nested class `A` calls `B.privateMethod()` | Yes | Must have an instance of `B` if the method is non-static |
| Independent top-level class reads `Outer.privateField` | No | Not automatically allowed even in the same package/file |

**Being allowed access** does not mean an expression will always compile. If the field is an instance field, the rule requiring a **receiver object** must still be satisfied. If the member is not within the accessible scope according to the expression's type, the compiler will still reject it.

## 3. Complete Example: Enclosing, Static Nested, and Inner Classes Collaborating

Create the file **`PrivateNestDemo.java`**. This example demonstrates all three directions: the enclosing class uses private members of nested classes; a nested class uses private members of the enclosing class; and two nested classes use each other's private members.

~~~java
public class PrivateNestDemo {
    private static final String PREFIX = "NEST";
    private final String owner;
    private int score;

    private PrivateNestDemo(String owner, int score) {
        this.owner = owner;
        this.score = score;
    }

    private String summary() {
        return owner + ":" + score;
    }

    private static class Inspector {
        private final int offset;

        private Inspector(int offset) {
            this.offset = offset;
        }

        private String examine(PrivateNestDemo host) {
            return host.owner + ":" + (host.score + offset)
                    + ":" + PREFIX;
        }
    }

    private class Editor {
        private int setScore(int next) {
            if (next < 0) {
                throw new IllegalArgumentException("score âm");
            }
            PrivateNestDemo.this.score = next;
            return score;
        }

        private String detail() {
            return owner + "/" + score;
        }
    }

    private static class Peer {
        private int offsetOf(Inspector inspector) {
            return inspector.offset;
        }

        private int update(Editor editor) {
            return editor.setScore(23);
        }
    }

    public static void main(String[] args) {
        PrivateNestDemo host = new PrivateNestDemo("An", 10);
        Inspector inspector = new Inspector(4);
        PrivateNestDemo.Editor editor = host.new Editor();
        Peer peer = new Peer();

        System.out.println("outer=" + host.summary());
        System.out.println("inspector=" + inspector.examine(host));
        System.out.println("offset=" + peer.offsetOf(inspector));
        System.out.println("updated=" + peer.update(editor));
        System.out.println("outer now=" + host.summary());
        System.out.println("editor=" + editor.detail());
    }
}
~~~

Run from the directory containing the file:

~~~bash
javac -encoding UTF-8 PrivateNestDemo.java
java PrivateNestDemo
~~~

**Stdout:**

~~~text
outer=An:10
inspector=An:14:NEST
offset=4
updated=23
outer now=An:23
editor=An/23
~~~

### Which Accesses Are Notable in This Example?

1. `PrivateNestDemo` calls its own `private PrivateNestDemo(...)` constructor and `private summary()` method.
2. `main`, although declared in the enclosing class, can still create `new Inspector(4)`, **calling the private constructor** of class `Inspector`.
3. `Inspector.examine(host)` is a **private method of Inspector**. The enclosing class calls it validly because they belong to the same nested structure.
4. Inside `Inspector.examine`, the code reads **`host.owner` and `host.score`**, even though those are two `private` fields of the enclosing class. Because `Inspector` is a static nested class, it explicitly receives the `host` reference to read instance fields.
5. `Inspector` directly reads `PREFIX`, which is a **private static field** of the enclosing class; static members do not require an Outer object.
6. `Peer.offsetOf(inspector)` reads **`inspector.offset`**, a private field of the **sibling nested class `Inspector`**.
7. `Peer.update(editor)` calls **`Editor.setScore(23)`**, a private method of the sibling nested class `Editor`.
8. `Editor.setScore` writes `PrivateNestDemo.this.score`, which is the field of the **outer instance enclosing Editor**. `editor` is linked to `host` by the expression `host.new Editor()`.
9. After `Editor` updates the field, `host.summary()` sees `score=23` because both operate on the **same outer object**.

Key takeaway: no operation had to relax visibility to `public`. These calls succeed because they are in the **same enclosing scope**, and every instance field access has an appropriate receiver.

## 4. First Direction: Nested Class Accessing `private` Members of the Enclosing Class

In the `PrivateNestDemo` program, there are two very different kinds of access:

~~~java
private String examine(PrivateNestDemo host) {
    return host.owner + ":" + (host.score + offset)
            + ":" + PREFIX;
}
~~~

This is an excerpt of a **method from the static nested class `Inspector`**, not a standalone file. It accesses:

- `host.owner`, `host.score`: **private instance fields** of a `PrivateNestDemo` object.
- `PREFIX`: **private static field** of the enclosing class.
- `offset`: private instance field of the current `Inspector`.

Because `Inspector` is a **static nested class**, it **does not have an implicit outer instance**. Therefore:

~~~java
private int read(PrivateNestDemo host) {
    return host.score;
}
~~~

is a valid way to read a private instance field of a passed-in `host`. However, writing `return score;` directly inside a static nested class **without an Outer object from which to select the field** does not automatically become valid just because the class is nested inside `PrivateNestDemo`.

**Rule to remember:** `private` determines *who has permission to read*; `static` and the receiver mechanism determine *which object to read from*.

## 5. Second Direction: Enclosing Class Accessing `private` Members of a Nested Class

Also in the same program:

~~~java
Inspector inspector = new Inspector(4);
System.out.println(inspector.examine(host));
~~~

Both the `Inspector(int)` constructor and `Inspector.examine(PrivateNestDemo)` are **private**, yet code in the enclosing class is allowed to use them.

To understand this precisely, distinguish between:

- **Visibility of the type** `Inspector`: the type is declared as a private member inside `PrivateNestDemo`.
- **Permission to call the constructor** `Inspector(int)`: the constructor is also private.
- **Permission to call the method** `examine(...)`: a private method.
- **Ability to provide a valid argument**: the call requires a `PrivateNestDemo host`.

When the enclosing class reads an **instance field of a nested class**, it also requires a nested class object: `inspector.offset`, rather than attempting to read `Inspector.offset`, since `offset` is non-static.

This coordination is useful when a large structure needs multiple internal helpers but **does not want to expose implementation details** to the package or public API.

## 6. Third Direction: Two Sibling Nested Classes Reading Each Other's `private` Members

In the example:

~~~java
private static class Peer {
    private int offsetOf(Inspector inspector) {
        return inspector.offset;
    }

    private int update(Editor editor) {
        return editor.setScore(23);
    }
}
~~~

The snippet above is the definition of the **nested class `Peer`** excerpted from the complete program. `Peer` is neither a superclass nor a subclass of `Inspector` or `Editor`. The three nested classes are **member types belonging to the same top-level `PrivateNestDemo`**.

This is sufficient for code in `Peer` to access the private members of `Inspector` and `Editor`, provided there is a valid object on which to call the method or read the field.

**No inheritance relationship is needed** to permit private access within the same nest. Nor does `private` become `public`: an independent class outside `PrivateNestDemo` still does not have that privilege.

If the `Inspector` type is declared `private`, an external class cannot arbitrarily name `PrivateNestDemo.Inspector` either; that is a restriction distinct from the internal access seen above.

## 7. How Static Nested Classes and Inner Classes Differ on the Outer Instance

Two declarations:

~~~java
class Outer {
    private int value = 10;

    static class StaticReader {
        int read(Outer target) {
            return target.value;
        }
    }

    class InnerReader {
        int read() {
            return value;
        }
    }
}
~~~

This is a **valid illustrative class**. Both `StaticReader` and `InnerReader` access `Outer.value` even though it is private. However, how they obtain the object differs:

| Aspect | `static class StaticReader` | `class InnerReader` |
| --- | --- | --- |
| Has an implicit outer instance? | No | Yes, for a non-static member inner class |
| How to access `private static` members of Outer | `Outer.staticField` or a valid simple name | Same |
| How to access `private int value` | `target.value` with `Outer target` | Can write `value` or `Outer.this.value` |
| How to instantiate from another static method | `new Outer.StaticReader()` if the type is accessible | `outer.new InnerReader()`, requires an outer instance |
| `this` inside a nested class method | `StaticReader` object | `InnerReader` object |
| Can `Outer.this` be used? | No enclosing Outer instance | Yes, in an appropriate inner context |

Being `static` **does not cancel private access rights** between two nested types in a top-level class. It primarily determines **whether an instance of the enclosing class is attached**.

Do not confuse `Outer.this` with `this`: inside `InnerReader`, `this` is the **inner object**, whereas `Outer.this` is the **outer object** enclosing it.

## 8. Runnable Example of `Outer.this` and Shadowed Field Names

An inner class can declare its own field with the same name as a field in Outer. In that case, `this.value` and `Outer.this.value` yield two different values.

Create the file **`OuterThisPrivateDemo.java`**:

~~~java
public class OuterThisPrivateDemo {
    private final int value = 10;

    private class Inner {
        private final int value = 3;

        private int sum() {
            return this.value + OuterThisPrivateDemo.this.value;
        }

        private String detail() {
            return "inner=" + this.value
                    + ",outer=" + OuterThisPrivateDemo.this.value;
        }
    }

    private static class StaticReader {
        private int read(OuterThisPrivateDemo target) {
            return target.value;
        }
    }

    public static void main(String[] args) {
        OuterThisPrivateDemo outer = new OuterThisPrivateDemo();
        Inner inner = outer.new Inner();
        StaticReader reader = new StaticReader();

        System.out.println(inner.detail());
        System.out.println("sum=" + inner.sum());
        System.out.println("static=" + reader.read(outer));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 OuterThisPrivateDemo.java
java OuterThisPrivateDemo
~~~

**Stdout:**

~~~text
inner=3,outer=10
sum=13
static=10
~~~

`Inner.sum()` takes the `value=3` field of the **inner object itself** and adds it to the `value=10` field of the **outer object**. `StaticReader.read(outer)` does not use `OuterThisPrivateDemo.this`; it must receive `outer` as an argument.

If you simply write `value` inside `Inner`, the inner class's field name shadows the field of the same name in Outer. To access Outer's field when it is shadowed, explicitly write `OuterThisPrivateDemo.this.value`.

## 9. Local Classes and Anonymous Classes Can Also Access Private Members

Nested classes do not consist only of member classes. Java also has **local classes** declared inside a block and **anonymous classes** created via anonymous class expressions. They can also use private members of the enclosing context when scope and receiver rules allow it.

Create the file **`LocalAnonymousPrivateDemo.java`**:

~~~java
public class LocalAnonymousPrivateDemo {
    private final int secret = 7;

    private int addSecret(int input) {
        return secret + input;
    }

    void demonstrate(int amount) {
        class LocalReader {
            int read() {
                return addSecret(amount);
            }
        }

        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println("anonymous=" + secret);
            }
        };

        System.out.println("local=" + new LocalReader().read());
        anonymous.run();
    }

    public static void main(String[] args) {
        LocalAnonymousPrivateDemo owner =
                new LocalAnonymousPrivateDemo();
        owner.demonstrate(5);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 LocalAnonymousPrivateDemo.java
java LocalAnonymousPrivateDemo
~~~

**Stdout:**

~~~text
local=12
anonymous=7
~~~

Explanation:

- `LocalReader.read()` calls the **private method `addSecret`** of the outer instance, while also using the `amount` parameter of the enclosing method.
- `anonymous.run()` reads the **private field `secret`** of the outer instance.
- `amount` is **captured** by the local class, so it must be `final` or *effectively final*. Here there is no reassignment to `amount`, so it is valid.
- Both the local class and the anonymous class in this example are inside an **instance method**, so there is an outer instance to access.

Inside a **static method**, a local or anonymous class does not automatically receive an outer instance merely because an enclosing class exists. To read a private instance field of Outer in a static context, a valid Outer reference must be available.

**Do not conflate the two rules:** the nest's private access permission does not waive the *effectively final* requirement for captured local variables.

## 10. Boundary: Same Java File Does Not Mean Same Nest

You can declare **multiple top-level classes** in the same source file (subject to the restrictions on `public`). However, they are **independent classes** and do not receive private access privileges to each other merely by being in the same file.

Create the file **`PrivateBoundaryDemo.java`**:

~~~java
class Vault {
    private final int code = 19;

    private static class Reader {
        private int read(Vault vault) {
            return vault.code;
        }
    }

    static int readThroughOwnNested(Vault vault) {
        return new Reader().read(vault);
    }
}

class Neighbor {
    int askThroughAllowedApi(Vault vault) {
        return Vault.readThroughOwnNested(vault);
    }

    // Cannot use vault.code: code is private to Vault.
    // Cannot use the type Vault.Reader: Reader is private to Vault.
}

public class PrivateBoundaryDemo {
    public static void main(String[] args) {
        Vault vault = new Vault();
        Neighbor neighbor = new Neighbor();
        System.out.println(neighbor.askThroughAllowedApi(vault));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 PrivateBoundaryDemo.java
java PrivateBoundaryDemo
~~~

Stdout:

~~~text
19
~~~

In this example:

- `Reader` is a **nested class of Vault**, so `Reader.read(vault)` is allowed to read the private `vault.code`.
- `Vault` is allowed to call `Reader`'s private constructor (the default constructor generated for this private class has the same access level as the class according to the rules) and the private `Reader.read` method.
- `Neighbor` is a **different top-level class**, even though it resides in the same file. It cannot read `vault.code` or use the `Vault.Reader` type.
- `Neighbor` calls `Vault.readThroughOwnNested`, a **package-private method** designed as a controlled access gateway for the example.
- `PrivateBoundaryDemo` interacts only through the API provided by `Neighbor`.

The example contains complete code to **compile and run**; the invalid operations are described verbally in comments rather than written as executable calls.

The same rule applies to the **same package**: `package-private` can grant access within the package; `private` does not automatically open access to every class in the package.

## 11. How Does `private` on a Nested Type Differ from `private` on a Field?

Both use `private`, but they control different things:

~~~java
class Outer {
    private static class Engine {
        private int capacity = 8;
    }

    private final Engine engine = new Engine();

    int capacity() {
        return engine.capacity;
    }
}
~~~

This is a **valid illustrative class**.

- `private static class Engine` restricts where the **`Engine` type can be named**.
- `private int capacity` restricts where the **`capacity` field can be accessed**.
- `private final Engine engine` restricts where **Outer's `engine` field can be accessed**.
- `Outer.capacity()` is a package-private method that can provide **a piece of information permitted to be exposed**, without directly exposing the Engine object.

Just because the outer class can use `engine.capacity` does not mean every caller of `Outer` is allowed to access `engine.capacity` directly.

**Design practice:** a `private` nested class is well-suited for a helper that is an internal implementation detail. It reduces the public API of the enclosing class, while still allowing parts within the same structure to use private members when needed.

## 12. Why Does Java Allow Nested Types to Access Each Other's Private Members?

The enclosing class and nested classes often form **a single design unit**. For example, a data structure might have:

- `Outer`: the published API.
- `Node`: internal node structure, containing `private` fields.
- `IteratorImpl`: nested class that traverses the nodes.
- `Validator`: nested class that checks invariants.

If every internal helper had to expose its fields just for another helper to use them, the API would be unnecessarily widened. Java lets these types collaborate **without opening private access to independent top-level classes**.

However, having access is not a reason for a helper to arbitrarily mutate every piece of state:

- If a field must always remain positive, code in another nested class can still break the invariant by directly assigning an invalid value.
- Complex modifications should go through validation methods, even though internal code has private access.
- An overly large nested structure with many classes cross-depending on each other's private fields can hurt maintainability.
- Do not think of `private` as an absolute security barrier against reflection, instrumentation, or other privileged mechanisms; it is **language-level access control** for ordinary code.

You can view private access within a nest as **internal collaboration privilege**, not a license to ignore class design rules.

## 13. Compile/Runtime Mechanism: Nestmates in Modern Java

At the source level, Java has long allowed appropriate nested structures to access each other's private members. Interestingly, nested classes are still typically compiled into **separate class files**, such as:

~~~text
PrivateNestDemo.class
PrivateNestDemo$Inspector.class
PrivateNestDemo$Editor.class
PrivateNestDemo$Peer.class
~~~

The filenames above represent the **typical class file structure produced by javac**, not class name syntax in source code. The binary name of a member class uses the `$` character according to Java naming rules.

### Java 8 and Earlier: Compiler-Generated Accessors May Appear

Before Java 11, older JVMs did not have today's runtime nestmate mechanism. The compiler typically generated **synthetic accessors** in bytecode to implement private access for nested classes, while the source program remained valid. This is a compiler implementation detail, not a method that developers need to define themselves.

### Java 11 Onward: Nest-Based Access Control

Since Java 11, the JVM has supported **nestmates**. Class files in the same nest can describe their relationship through metadata such as `NestHost` and `NestMembers`, allowing the JVM to check private access between nestmates. Consequently, with modern `javac`, private access cases between enclosing and nested classes can be represented directly in bytecode without needing synthetic accessors as before.

You can observe this yourself with the following commands after compiling the file in section 3:

~~~bash
javap -p PrivateNestDemo
javap -v -p PrivateNestDemo
javap -v -p 'PrivateNestDemo$Inspector'
~~~

Shell quoting syntax varies across PowerShell, CMD, and Unix shells, so the last line should be adjusted to escape or quote the `$` character appropriately for your actual environment. In PowerShell, use single quotes as in the example to prevent `$` interpolation.

The `javap` output is quite long and depends on the compiler version; therefore, no fixed hypothetical stdout is shown here. Look for `NestMembers`, `NestHost`, the names of private fields, and access instructions in the class files generated by `javac`.

**Most important point:** nestmates are a **JVM mechanism supporting private access**, not a new source-level modifier, and they **do not turn private into package-private**. Two independent top-level classes in the same package do not become nestmates merely by sharing a directory name or Java file.

## 14. Access Rights and Inheritance Relationships Are Not the Same

An ordinary subclass **does not inherit the right to directly use a private member** of its superclass merely through the `extends` relationship. A nested class can access outer's private members **because of nesting scope**, not because it inherits from outer.

Illustrative example:

~~~java
class Parent {
    private int secret = 7;

    int readSecret() {
        return secret;
    }
}

class Child extends Parent {
    int readViaApi() {
        return readSecret();
    }

    // Cannot directly access secret merely because Child extends Parent.
}
~~~

This is a valid declaration snippet without `main`. `Child.readViaApi()` calls a package-private method of `Parent` (in the same package), but as an independent subclass it cannot directly read the private `secret` field.

If a design requires subclasses to use a member, consider an **appropriate protected/public method** that preserves invariants rather than rushing to make the field `protected`. For nested classes, using `private` is still usually the better choice because collaboration happens within the same top-level structure.

## 15. Confusions About `this` and the Receiver When Accessing Private Members

A very common mistake is assuming that "having private access" means "you can write a bare field name anywhere." You must read the context carefully:

| Expression | When is it valid? | Meaning |
| --- | --- | --- |
| `outer.secret` | Code has private access and `outer` is an appropriate Outer object | Reads the field of `outer` |
| `Outer.this.secret` | In a context with an **enclosing Outer instance** | Reads the field of the enclosing outer object |
| `secret` in a non-static inner class | If name resolution finds the outer field and it is not shadowed | Reads the field through the implicit outer instance |
| `secret` in a static nested class | Only when the name fits the context; typically outer instance fields cannot be used this way | Does not automatically have an outer instance |
| `nested.privateMethod()` | Has private access and `nested` is a compatible receiver | Calls a private instance method |
| `Nested.privateStaticMethod()` | Has private access and the method is actually static | Calls the method via the type name |

Inside an **inner class**, `this` is the **inner object**. If you want the outer instance, use `Outer.this` where valid. Inside a **static nested class**, there is no `Outer.this` because there is no implicit enclosing Outer instance.

When accessing a private field of another nested class, **you cannot simply write `fieldName` to read an instance field of that other object** without a corresponding name/receiver relationship; instead, use an object reference such as `peer.fieldName`.

## 16. Rejected or Easily Misunderstood Cases

| Case | What is the issue? | Correct approach |
| --- | --- | --- |
| `private` top-level class | Ordinary top-level classes cannot be declared `private` | Use a top-level class with a valid access level or a nested private class |
| Two top-level classes in the same `.java` file using each other's private members | Being in the same file does not grant private access | Provide an appropriate API or actually nest the helper class |
| Two classes in the same package accessing private members | Private is not package-private | Use package-private members only when intentional |
| Static nested class writes `Outer.this.field` | Has no implicit outer instance | Pass an Outer object and write `outer.field` |
| Static nested class reads Outer instance field by bare name | Has no Outer receiver to read from | Use `outer.field` |
| Outer reads nested's instance field via `Nested.field` | The field is non-static | Create/receive a nested object and use `nested.field` |
| Inner class uses `this.field` thinking it is Outer's field | `this` points to the inner object | Use `Outer.this.field` if an outer instance is available |
| Nested class reads a local variable reassigned after capture | Captured local variables/parameters must be final or effectively final | Avoid reassigning the variable or copy the value appropriately |
| Making every private field public so nested classes can access it | Unnecessarily breaks API boundaries | Keep fields private and rely on access within the nest |
| Assuming every subclass has the same access as a nested class | Inheritance does not grant private access | Distinguish nesting from inheritance |
| Seeing separate class files and thinking private access is disallowed | Java/JVM has a mechanism supporting access between nestmates | Distinguish source access rules from bytecode representation |
| Assuming nested classes need no field validation because they have private access | Any code with access can still break invariants | Validate data and organize a clear internal API |

A program that directly reads fields inside another nested class may compile cleanly, yet **valid access permission does not guarantee valid business logic**. When two nested classes have separate responsibilities, prefer clear, meaningful methods over directly mutating key fields.

## 17. Review Process When the Compiler Reports an Access Error

When encountering messages such as *has private access*, *not an enclosing class*, or *non-static variable cannot be referenced from a static context*, determine:

1. **Who declared the member?** For example, `Outer.secret` or `Outer.Inner.code`.
2. **Where is the accessing code located?** Inside the same top-level enclosing class, inside a nested class in the same nest, or inside an independent top-level class?
3. **Is the member static or instance?** If instance, an appropriate receiver is required.
4. **Is the nested class static or non-static?** Is there an implicit outer instance or not?
5. **Is there name shadowing?** `this.field` might be the inner field, while `Outer.this.field` is the outer field.
6. **Is a private type being used from outside?** A public/package-visible API on the enclosing class may be needed instead of exposing the private type.
7. **Is inheritance being confused with nesting?** An independent subclass does not receive the superclass's private access.
8. **Is a local variable being captured?** Local/anonymous classes require captured variables to be final/effectively final.
9. **If the source is already correct, is there a bytecode/module/class loader configuration issue?** That is an advanced branch to investigate separately rather than arbitrarily changing all fields to public.

These steps help pinpoint the **exact kind of error**: missing permission, missing object, wrong static scope, name shadowing, or invisible type.

## 18. Practice Exercises

**Exercise 1 — Access control.** Given `Outer` containing `private int secret` and `private static class Reader`, can the method `Reader.read(Outer outer)` execute `return outer.secret;`? Why?

**Exercise 2 — Reverse direction.** Can `Outer` call a `private int read()` method on a `Reader` object? When must `reader.read()` be used instead of `Reader.read()`?

**Exercise 3 — Sibling classes.** `Outer.A` and `Outer.B` are two sibling member nested classes that do not inherit from each other. If `A` has a private field `code`, can code in `B` read `a.code` given an instance `A a`?

**Exercise 4 — Static nested.** Why cannot `Outer.StaticReader` use `Outer.this.secret`? Write an alternative way to read it if the method accepts `Outer target`.

**Exercise 5 — Inner and shadowing.** Outer has `private int value=10`; Inner has `private int value=3`. Inside an instance method of Inner, what are `this.value` and `Outer.this.value`?

**Exercise 6 — Same file.** Two top-level classes `A` and `B` are declared in one file. Is `B` allowed to call `A.privateMethod()` merely because they are in the same file? Propose a way to expose the necessary behavior without exposing fields.

**Exercise 7 — Capture.** Inside an instance method of Outer, a local class reads a private field `secret` and a local variable `int extra=5`. After creating the local class, can `extra=6` be reassigned if the local class has already captured `extra`?

**Exercise 8 — Context rules.** Given `Outer` containing an instance field `private String name`. A static nested class has a method `String describe(Outer owner)`. Write the statement returning `owner`'s `name` and explain why that method can still access the private member.

**Exercise 9 — Nestmates.** Why can `javac` emit multiple separate class files for Outer and Inner while the source code is still allowed to access private members across them? Name the modern JVM mechanism that supports this.

**Exercise 10 — Design.** An iterator is declared as a nested class of a collection. It has permission to directly write to the collection's private fields. What should restrict such writes even though the compiler allows them?

### Reference Answers

1. Yes. `Reader` is within the same top-level Outer, and `outer` is an explicit receiver for the private instance field.
2. Yes, if they are in the same nest and a `reader` object is available; `read()` is an instance method, so it must be called as `reader.read()` rather than through the class name.
3. Yes. Both classes are in the same nest; `a.code` uses an appropriate instance receiver.
4. A static nested class has no enclosing Outer instance; use `return target.secret;` with a valid `target` argument.
5. 3 and 10, respectively, assuming it is inside an Inner attached to an outer object with field `value=10`.
6. No. Provide a method with the required access level on `A`, or organize an appropriately nested helper when suitable.
7. No. A variable captured by a local class must be final/effectively final; reassigning `extra` violates this condition.
8. `return owner.name;`. The static nested class receives private access through nesting, but still needs `owner` as the receiver for the instance field.
9. The compiler represents nested classes using separate class files; Java 11+ supports **nest-based access control/nestmates** in the JVM, while older compilers used synthetic accessors.
10. Collection invariants must be preserved, related state must be updated consistently, and the iterator contract must not be broken; private access does not replace validation or separation of responsibilities.

## 19. References

- [Java Language Specification 17, §6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6): access control rules.
- [Java Language Specification 17, §6.6.1 — Determining Accessibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6.1): permitted scope for private members and constructors.
- [Java Language Specification 17, §8.1.3 — Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3): inner classes and enclosing instances.
- [Java Language Specification 17, §15.8.3 — `this`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.8.3): `this` expressions and qualified `Outer.this`.
- [Java Virtual Machine Specification 17, §5.4.4 — Access Control](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.4): nestmates and private access checks at link/runtime.
- [Java SE 17 — javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): inspecting declarations, members, and metadata in class files.

**Key takeaway:** `private` does not completely seal off classes **belonging to the same top-level enclosing class structure**. Outer, inner, static nested, sibling nested, and appropriate local/anonymous classes can access each other's private members under Java's rules. However, access permission **does not automatically create a receiver object**, **does not turn an instance field into a static one**, and **does not open access to every class in the same package or file**. Always distinguish private scope from the `this`/`Outer.this` context, and preserve invariants even when internal code has direct access.
