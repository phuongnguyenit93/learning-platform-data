# Package-private methods when a subclass is in a different package in Java

When a superclass declares an `abstract` method with **package-private** access (without writing `public`, `protected`, or `private`), a subclass in a **different package** cannot implement/override that abstract method in the usual way. This is a common point of confusion: **a method in a subclass with the same name, same parameters, and same return type is not necessarily an overriding method**.

With cross-package inheritance, the issue is not just whether the subclass can call the method. It also determines whether the subclass can become a concrete class (`concrete class`) or must remain an `abstract` class. This article explains the mechanism, presents cases that compile and cases that do not compile, and then shows how to design it properly.

## 1. Recap of package-private and abstract

A method in a class is declared **package-private** when all three access modifiers `public`, `protected`, `private` are omitted:

```java
package academy.base;

public abstract class Task {
    abstract String auditCode(); // package-private + abstract
    public abstract String execute();
}
```

- `abstract String auditCode();` has no method body, requiring a suitable implementation to be provided before an object of a concrete class can be created.
- Omitting an access modifier means **package-private**, sometimes called *default access*. Do not confuse this with the `default` keyword for interface methods.
- Package-private access is tied to **the package where the class/method is declared**, not based on whether two classes have similar names or belong to the same root directory.
- Classes in the **same package** can access the package-private method (provided other member rules are satisfied). Classes in a **different package** do not have access to that member through the normal mechanism.
- `public abstract String execute();` is declared public, so an appropriate subclass in another package can override it with a public method.

An abstract method in a class can be `public`, `protected`, or package-private. `abstract` cannot be combined with `private`, `final`, or `static`: they contradict the overriding requirement of an abstract method.

### Overriding is not based solely on signature

When determining whether two methods have an **overriding** relationship, Java considers their positions in the inheritance hierarchy, signatures, return-type rules, access privileges, and packages. In particular, a package-private method in a superclass **is not overridden by a subclass in a different package merely by redeclaring a method with the same signature**. The new method can exist in the subclass, but it is not a valid implementation for the original package-private abstract method.

This differs from `protected`: a `protected abstract` method can be properly overridden by a subclass in another package, as long as the remaining conditions are met.

## 2. Error example: subclass in a different package

Consider two separate Java files:

**`src/academy/base/Task.java`**

```java
package academy.base;

public abstract class Task {
    protected Task() {}

    abstract String auditCode(); // Package academy.base only
    public abstract String execute();
}
```

**`src/academy/app/BadRemoteTask.java`**

```java
package academy.app;

import academy.base.Task;

public final class BadRemoteTask extends Task {
    public String auditCode() {
        return "attempt";
    }

    @Override
    public String execute() {
        return "remote";
    }
}
```

`Task` is in package `academy.base` and `BadRemoteTask` is in package `academy.app`. Even though `BadRemoteTask.auditCode()` has the same name, no parameters, and the same `String` return type, this method **does not override** `Task.auditCode()`. Adding `public` does not change that relationship. Therefore, a `BadRemoteTask` that is **not abstract** has not finished implementing the abstract method it must satisfy.

Compile the error example on its own from the directory containing `src`:

```bash
javac -encoding UTF-8 -d out src/academy/base/Task.java src/academy/app/BadRemoteTask.java
```

Result: **compilation fails**. A typical diagnostic from `javac` is that `BadRemoteTask` is not abstract and does not override the abstract method `auditCode()` in `Task`. The wording or line position of the error may vary depending on the compiler version.

If you add `@Override` directly above `public String auditCode()` in `BadRemoteTask`, the compiler will also directly detect that the method **does not override/implement a method from a supertype**. `@Override` cannot "force" Java to change its package and visibility rules.

### Why is an abstract subclass different?

If `BadRemoteTask` is declared as an `abstract class`, it can exist as an intermediate class that has not yet fulfilled `Task`'s abstract requirement; the implementation issue will still remain when you want to create a concrete class later. You cannot fix the error simply by changing `final class` to another concrete class in an external package while leaving the package-private abstract method without a proper implementation.

A clearer example of a declaration that **does not override** (placed in an abstract class in another package):

```java
// In package academy.app; illustrative snippet only.
public abstract class ExternalTask extends academy.base.Task {
    public String auditCode() { // Does not override Task.auditCode()
        return "another method";
    }

    @Override
    public String execute() {
        return "external";
    }
}
```

Placing `@Override` on `auditCode()` in this snippet will produce a compilation error. Even without the annotation, a matching method name does not mean that the abstract method in package `academy.base` has been implemented.

## 3. Correct example: implementing the method in the superclass's own package

You can keep `auditCode()` as package-private if the design wants the internal implementation to stay inside `academy.base`. Create an intermediate class in the **same package as `Task`** to override that method, and then have the class in the other package extend that intermediate class.

Complete file structure:

```text
src/
└── academy/
    ├── base/
    │   ├── Task.java
    │   └── VerifiedTask.java
    └── app/
        ├── RemoteTask.java
        └── Main.java
```

**File `src/academy/base/Task.java`**

```java
package academy.base;

public abstract class Task {
    protected Task() {}

    abstract String auditCode();

    public abstract String execute();

    public final String report() {
        return auditCode() + " | " + execute();
    }
}
```

**File `src/academy/base/VerifiedTask.java`**

```java
package academy.base;

public abstract class VerifiedTask extends Task {
    protected VerifiedTask() {
        super();
    }

    @Override
    String auditCode() {
        return "verified";
    }
}
```

**File `src/academy/app/RemoteTask.java`**

```java
package academy.app;

import academy.base.VerifiedTask;

public final class RemoteTask extends VerifiedTask {
    @Override
    public String execute() {
        return "remote";
    }
}
```

**File `src/academy/app/Main.java`**

```java
package academy.app;

import academy.base.Task;

public class Main {
    public static void main(String[] args) {
        Task task = new RemoteTask();

        System.out.println(task.report());
        System.out.println(task.execute());

        // task.auditCode(); // Does not compile: package-private in academy.base
    }
}
```

From the directory containing `src`, compile with Java 17+:

```bash
javac -encoding UTF-8 -d out src/academy/base/Task.java src/academy/base/VerifiedTask.java src/academy/app/RemoteTask.java src/academy/app/Main.java
java -cp out academy.app.Main
```

**Exact standard output:**

```text
verified | remote
remote
```

**Analysis:**

1. `Task.auditCode()` is package-private abstract. `VerifiedTask` is declared in the **same package `academy.base`** and overrides it with `String auditCode()` having the same access level. Therefore, the abstract requirement of `auditCode()` now has a valid implementation.
2. `VerifiedTask` remains abstract because it has not implemented `execute()`. An abstract intermediate class is a design choice, not an error.
3. `RemoteTask` in package `academy.app` extends `VerifiedTask`, provides `public String execute()` for the missing public abstract method, and becomes a concrete class.
4. When `Task.report()` calls `auditCode()`, the JVM runs the `VerifiedTask.auditCode()` implementation. Polymorphism through an overridden instance method still works; **source-code access restrictions do not mean the JVM cannot dispatch internally**.
5. The statement `task.auditCode()` in `Main` is still invalid, because `Main` belongs to package `academy.app` and the method remains package-private.
6. `Task task = new RemoteTask();` uses a superclass-type reference with an actual object of the subclass; the call to `execute()` runs the implementation in `RemoteTask`.

Note that the two directories `base` and `app` are separated into **two different Java packages** by the statements `package academy.base;` and `package academy.app;`. The package `academy.base.internal` is also a **different** package from `academy.base`; Java does not grant package-private access based on a hierarchical naming structure.

## 4. The right approach if a class outside the package needs to implement the method itself

If the business requirement is "each subclass outside the package must implement `auditCode()` itself", declaring it as package-private abstract is an unsuitable design. Use **`protected abstract` or `public abstract`**.

### Option A — `protected abstract`

File `src/academy/base/Task.java` in the alternative approach:

```java
package academy.base;

public abstract class Task {
    protected Task() {}

    protected abstract String auditCode();

    public final String report() {
        return auditCode();
    }
}
```

File `src/academy/app/RemoteTask.java` in the alternative approach:

```java
package academy.app;

import academy.base.Task;

public final class RemoteTask extends Task {
    @Override
    protected String auditCode() {
        return "remote-audit";
    }
}
```

This is **an independent alternative** that replaces the `Task` definition in the main example; do not compile both `Task` definitions at the same time. `RemoteTask` can validly override it because the superclass method is `protected`. Outside the package, an arbitrary class is **not automatically** allowed to call `task.auditCode()`: `protected` has its own access rules for packages and subclasses. The right to override in a subclass is also **different** from the right to invoke through an arbitrary reference variable from external code.

You should use `protected abstract` for **extension points intended for subclasses** without necessarily exposing them publicly as an API for all client code.

### Option B — `public abstract`

When both subclasses and client code need public access:

```java
package academy.base;

public abstract class Task {
    public abstract String auditCode();
}
```

```java
// In another file belonging to package academy.app
package academy.app;

public final class RemoteTask extends academy.base.Task {
    @Override
    public String auditCode() {
        return "remote-audit";
    }
}
```

The two snippets above represent **two separate files**; do not combine multiple `package` declarations into a single Java file. When overriding a public method, the implementing method must also be public; you cannot reduce visibility to `protected` or package-private.

`public` is appropriate when this is behavior you want to expose in the **public interface**. Consider API stability, since code outside the package can depend on the method.

### Option C — Completing the internal part within the same package

Keep it package-private abstract when a hook is an internal detail that only classes in the owning package are permitted to override. Create an intermediate class in the same package as demonstrated with `VerifiedTask`, and then provide other public/protected extension points for classes in external packages.

## 5. Comparing access levels for cross-package overriding

Suppose `Child` in `academy.app` extends `Parent` in `academy.base`, and there is no intermediate class that already implemented the abstract method beforehand:

| Method in `Parent` | Can `Child` validly override it? | Can `Child` fulfill the abstract requirement on its own to become concrete? |
| --- | --- | --- |
| `abstract void work();` (package-private) | **No**, via a same-signature declaration in another package | **No**; requires a valid implementation from a class in the same package as the parent or a design change |
| `protected abstract void work();` | **Yes**, with valid visibility | **Yes** |
| `public abstract void work();` | **Yes**, with a `public` method | **Yes** |
| `private void work() { ... }` | **No**, private methods are not overridden | Imposes no abstract requirement; `private abstract` is an illegal declaration |
| `final void work() { ... }` | **No**, final prevents overriding | Has no abstract requirement because `final abstract` is illegal |

**General rule:** an overriding subclass method must not reduce access privileges compared to the method it actually overrides. However, **increasing the visibility of a same-named method in a different package does not by itself create an overriding relationship** for an inaccessible package-private method.

Within the same package, a package-private method can be overridden with package-private, `protected`, or `public` access, provided other rules are met. When widening visibility, the new method genuinely overrides because the subclass in the same package has the right to do so.

## 6. Distinguishing between abstract class and interface

An interface is often used as a contract for many implementing classes across different packages. In Java, an **abstract method of a regular interface is always public** even if you do not write the public keyword:

```java
package academy.base;

public interface Auditable {
    String auditCode(); // implicitly public abstract
}
```

```java
package academy.app;

public final class RemoteAudit implements academy.base.Auditable {
    @Override
    public String auditCode() {
        return "remote-audit";
    }
}
```

The two snippets are two separate files, each public type having a file of the same name. `RemoteAudit` in a different package can still implement `auditCode()` because the interface method is public. You cannot implement a public interface method with a package-private method; the compiler will report reduced visibility.

Do not infer from the syntax `String auditCode();` that it is always package-private: **in a class**, omitting an access modifier makes it package-private, whereas **in an interface**, an abstract method declared without an access modifier is public. Java 9+ also allows private methods **with a body** in an interface to reuse internal logic; they are not abstract methods to be implemented from outside.

## 7. Distinguishing "inaccessible" from "not executed"

There are three independent questions:

- **Can subclass code in another package see/call `Task.auditCode()`?** No, because it is package-private.
- **Can that subclass directly override the package-private abstract method?** No; a method with a matching signature does not fulfill the overriding requirement.
- **After a same-package class implements the method, can a public method of `Task` invoke that implementation for an object of a subclass in another package?** Yes, as seen with `report()` in the working example. The call occurs inside a method that already has access and dynamically dispatches to the valid implementation.

This is why you cannot simply say "package-private is inaccessible, so the JVM cannot run the method". The rules for **source-code access** and **runtime instance method resolution** serve different roles.

In addition, merely changing the type of the reference variable cannot open up package-private access:

```java
// In package academy.app; using the classes from the working example
academy.base.Task task = new RemoteTask();
academy.base.VerifiedTask bridge = new RemoteTask();

// task.auditCode();   // Not allowed to call
// bridge.auditCode(); // Still not allowed to call
System.out.println(task.report()); // Valid
```

A reference variable of the superclass type or intermediate class type does not change the package of the calling code. Casting down to the subclass also does not open up access to a package-private method from another package.

## 8. Common mistakes and how to check

**Mistake 1 — Same signature must mean it overrides.** With package-private across different packages, this reasoning is wrong. Add `@Override` whenever you intend to override so the compiler verifies it. If the annotation reports an error, check the package and access modifier before assuming a compiler bug.

**Mistake 2 — Adding `public` in the subclass is enough.** It is not enough for a package-private abstract method in a superclass from a different package. You need to change the visibility **in the superclass** (when you control the API), or have a class in the superclass's exact package implement it first.

**Mistake 3 — Making the subclass `abstract` and assuming the issue is fixed.** This only postpones the obligation to provide an implementation. If you want a concrete class from that branch, a valid implementation of the remaining abstract method is still required.

**Mistake 4 — Confusing a subpackage with the same package.** `academy.base` and `academy.base.impl` are two different packages. There are no package-private privileges across dots in package names.

**Mistake 5 — Forgetting constructor requirements.** To extend a class from another package, the superclass must also have a constructor that the subclass can invoke (typically `protected` or `public`). If the constructor is inaccessible, an error will occur independently of the abstract method. The examples above use `protected Task() {}` to separate the two issues.

**Mistake 6 — Confusing a class with an interface.** `void run();` in an interface is `public abstract`; `abstract void run();` without an access modifier in a class is package-private. Implementing a public interface method with a package-private method will be rejected by the compiler.

**Mistake 7 — Calling a package-private method from outside via a public method returning the same object.** Having a reference to an object does not grant permission to invoke an inaccessible member. Provide a public method as a valid API, such as `Task.report()`, if you want to allow an operation that uses the internal implementation.

### Diagnostic procedure when code does not compile

1. Open the abstract method declaration **in the class or interface**; determine its exact visibility.
2. Check the exact `package ...;` statement of the superclass, intermediate class, and subclass. Only identical package name strings count as the same package in this context (in a typical classpath/module layout).
3. Check whether a class in the **same package as where the method is declared** already provides a valid override along the inheritance branch.
4. Check `@Override` on the intended implementation, along with the signature, return type, and access privileges. If the compiler says it does not override, do not remove the annotation as a way to hide the problem.
5. Check whether the class you intend to instantiate with `new` has implemented all remaining abstract methods; a concrete class cannot carry unfulfilled abstract obligations.
6. Check whether the superclass constructor is accessible from a subclass in a different package. After modifying visibility, re-run `javac` across the entire set of related files.

## 9. Self-check

**Question 1.** `package a; public abstract class Base { abstract void f(); }`. In `package b`, a concrete class `Derived extends Base` declares `public void f() {}`. Does it compile?

**Answer:** No. The new `f()` method in `b` does not override the package-private `Base.f()`; the concrete class still has not fulfilled the abstract method in the superclass.

**Question 2.** What if you only change `Base.f()` to `protected abstract void f();` and keep `Derived.public void f() {}`?

**Answer:** It can validly override, because `protected` allows a subclass in another package to override it and `public` does not reduce access privileges. Other conditions such as constructor access, file name, and signature must still be valid.

**Question 3.** What if you keep `Base.f()` package-private, add `Bridge extends Base` in package `a` to override `f()`, and then have `Derived extends Bridge` in package `b` implement the remaining abstract methods?

**Answer:** A concrete `Derived` can be created once all abstract methods have been validly implemented. This is the pattern that ran in section 3.

**Question 4.** In the interface `I { void f(); }`, is the method `f()` package-private?

**Answer:** No. Such an abstract method of an interface is implicitly `public abstract`; an implementing class in another package is permitted and required to provide a `public` method.

**Key takeaway:** For a **package-private abstract method in a class**, *the package of the implementing class* determines whether overriding is possible. A subclass in a different package cannot "complete" that abstract method by declaring the same signature. To create a cross-package extension point, use `protected/public abstract`; to keep an internal hook, implement it in the superclass's package before extending it externally.
