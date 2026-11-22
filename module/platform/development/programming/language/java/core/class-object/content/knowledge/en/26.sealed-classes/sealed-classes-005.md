# Same-Module or Same-Package Constraint of Sealed Classes in Java 17

## Learning Objectives

After completing this lesson, you will be able to:

- Understand how `sealed` restricts the **direct subclasses** of a sealed class and the **direct implementations/subinterfaces** of a sealed interface via `permits`.
- Accurately apply the Java 17 rule: when a sealed type belongs to a **named module**, all permitted direct subtypes must belong to the **same named module**; when a sealed type belongs to an **unnamed module**, they must belong to the **same package**.
- Distinguish the concepts of **named module**, **unnamed module**, **package**, **compilation unit**, **classpath**, **module path**, same Maven/Gradle project, and same physical directory.
- Organize code and compile a **same-package classpath** sealed class project, even when each class resides in its own separate source file.
- Organize code and compile a JPMS project that has a sealed interface in an API package and permitted implementations in **two different packages within the same named module**.
- Diagnose errors when a declared permitted subtype is in a different package in an unnamed module, in a different named module, not accessible, or does not directly extend/implement the parent.
- Explain that `permits` **only lists direct subtypes**, not grandchildren, and how a `non-sealed` child can serve as an extension point across packages/modules.
- Understand that a direct child must explicitly declare `final`, `sealed`, or `non-sealed` according to the rules; records are implicitly final and can implement sealed interfaces.
- Grasp `permits` inference when omitted: only direct types in the **same compilation unit** are considered, without scanning every source file in the package or module.
- Know how to use `Class.isSealed()`, `Class.getPermittedSubclasses()`, `Class.getModule()`, and `Module.isNamed()` to inspect a running program, without mistaking reflection for the ability to bypass compiler rules.
- Explain the separate effects of `exports`, `requires`, accessibility, package-private visibility, and JPMS, while choosing a maintainable hierarchy architecture.
- Run complete Java 17+ programs yourself with full source code and accurate results; recognize that snippets marked as intentionally invalid are only for studying error messages and should **not** be pasted into a valid demo.

> **Scope:** This lesson belongs to the **Sealed Classes** topic in Java Core. Sealed classes/interfaces have been a standard feature since Java 17 (JEP 409), without requiring `--enable-preview`. The focus is on the **same-module/same-package constraint for permitted direct types**, along with adjacent rules to explain cases where the compiler accepts or rejects code.

## 1. The First Rule to Remember

| Sealed parent location | Location requirement for each permitted **direct** subtype | Different package? |
| --- | --- | --- |
| **Named module** (JPMS) | **The same named module** | **Possible**, if access and other rules are satisfied |
| **Unnamed module** (typically classpath) | **The same package** | **No**, even if in the same JAR/project |
| Two **different named modules** | Cannot be each other's parent/permitted direct child | Invalid |
| Merely “same project/same folder/same JAR” | Not sufficient to confirm module association | Must determine the actual named/unnamed module |

For a sealed class, the direct subtypes in `permits` are **classes that directly `extends` the parent**. For a sealed interface, they can be **classes that directly `implements`** or **interfaces that directly `extends` the parent**.

**Quick takeaway:**

- **Named → same module.**
- **Unnamed → same package.**
- **Only direct permitted subtypes are checked; this is not mechanically applied to every descendant.**

The rules are specified in JLS 17 [`8.1.6](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.6) (sealed class) and [`9.1.4](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.4) (sealed interface).

## 2. Why Does Java Have This Constraint?

A sealed parent restricts **which types may directly inherit from it** so that the set of immediate variants is managed by the same code maintenance group. For example:

~~~java
sealed interface PaymentResult permits Success, Failure {
}

record Success(String receipt) implements PaymentResult {
}

record Failure(String reason) implements PaymentResult {
}
~~~

This is a **snippet**: the declarations can be placed in the same Java source file/package or in the same valid module. `Success` and `Failure` are direct implementations, and records are already implicitly final.

If any library in an independent module could directly implement `PaymentResult`, the permitted list would no longer serve as a boundary managing a consistent set of domain variants. A JPMS named module forms a **unit of maintenance**, which is why Java requires the sealed parent and its direct children to be in the same module. For classpath/unnamed module code without a named boundary, Java uses the **package boundary** instead.

This is a **language rule**, not a style convention; the compiler rejects any program that violates it.

### 2.1. Why Are Cross-Module Direct Subtypes Disallowed?

A direct child needs to know about the parent via `extends`/`implements`, while the parent declares the child's name in `permits`. If the two types resided in two independent named modules, this relationship would create a **bidirectional** reference requirement, which does not fit the JPMS module dependency graph or maintenance goals. The JLS forbids this before one even tries to “fix” it with `requires transitive` or `opens`.

### 2.2. Must Every Descendant Be in the Same Module?

**No.** A sealed parent restricts its **direct** children. If a direct child is `non-sealed`, that branch opens up for extension under normal rules, allowing grandchildren in other packages/modules if accessibility and module readability permit.

## 3. Distinguishing Modules, Packages, and Source Files

| Term | Practical definition | What **cannot** be inferred |
| --- | --- | --- |
| Package | Namespace declared by `package x.y;` | Does not identify which named module |
| Compilation unit | A single source file per JLS `7.3` | Not synonymous with an entire package |
| Named module | A JPMS module with a name, e.g., `com.example.domain` | Can contain multiple packages |
| Unnamed module | A module assigned by the runtime/classloader to code outside named modules, typically via classpath | Being in the same unnamed module **does not waive** the same-package rule |
| Module path | `--module-path` used to locate modules | Not simply any directory whose name contains “module” |
| Classpath | Traditional `-cp`/`--class-path` | A classpath JAR is not automatically a named module |
| JAR | Archive file packaging classes/resources | Being in the same JAR is not enough to determine the location rule |
| Maven/Gradle project | Build/dependency unit | Does not necessarily correspond to a single JPMS named module |

**One package can contain multiple Java files**; one **named module can contain multiple packages**. These two facts explain why “same module” and “same package” are two distinct boundary levels.

### 3.1. Illustrative Named Module Structure

~~~text
com.example.geometry       ← named module
├── geometry.api           ← package 1
├── geometry.circle        ← package 2
├── geometry.rect          ← package 3
└── geometry.app           ← package 4
~~~

A sealed interface `geometry.api.Shape` can permit `geometry.circle.Circle` and `geometry.rect.Rectangle` if the declarations belong to the same **com.example.geometry** module and are legal under Java access rules.

Conversely, when all classes are run as classpath code (unnamed module), the two implementations in `geometry.circle`/`geometry.rect` **cannot** be direct permitted children of the `geometry.api.Shape` parent.

## 4. Syntax of a Sealed Superclass and Direct Children

~~~java
sealed abstract class Animal permits Dog, Cat {
    abstract String sound();
}

final class Dog extends Animal {
    @Override
    String sound() {
        return "woof";
    }
}

non-sealed class Cat extends Animal {
    @Override
    String sound() {
        return "meow";
    }
}
~~~

All three declarations are in the same compilation unit/package in this example, so they are legal with respect to location. `Animal` is sealed; `Dog` is final, and `Cat` is non-sealed.

- `Dog` directly `extends Animal`.
- `Cat` directly `extends Animal`.
- `Animal.permits` **cannot** list an unrelated class.
- `abstract` is used because `sound()` is abstract; sealed **does not automatically make a class abstract**.
- `final` forbids subclassing Dog.
- `non-sealed` allows future subclasses to inherit from Cat according to access rules.

## 5. Multi-File Classpath Example — **Same Package** Across Different Files

Create a new project:

~~~text
classpath-animals/
└── src/
    └── animals/
        ├── Animal.java
        ├── Dog.java
        ├── Cat.java
        └── Main.java
~~~

All files below use `package animals;`.

**`src/animals/Animal.java`**

~~~java
package animals;

public abstract sealed class Animal permits Dog, Cat {
    public abstract String sound();
}
~~~

**`src/animals/Dog.java`**

~~~java
package animals;

public final class Dog extends Animal {
    @Override
    public String sound() {
        return "woof";
    }
}
~~~

**`src/animals/Cat.java`**

~~~java
package animals;

public non-sealed class Cat extends Animal {
    @Override
    public String sound() {
        return "meow";
    }
}
~~~

**`src/animals/Main.java`**

~~~java
package animals;

public class Main {
    public static void main(String[] args) {
        Animal dog = new Dog();
        Animal cat = new Cat();

        System.out.println("named module=" +
                Animal.class.getModule().isNamed());
        System.out.println("dog=" + dog.sound());
        System.out.println("cat=" + cat.sound());
        System.out.println("sealed=" + Animal.class.isSealed());
        System.out.println("permitted=" +
                Animal.class.getPermittedSubclasses().length);
    }
}
~~~

### 5.1. Compiling and Running on Java 17

From inside the `classpath-animals` directory you just created:

~~~bash
mkdir out
javac --release 17 -d out src/animals/Animal.java src/animals/Dog.java src/animals/Cat.java src/animals/Main.java
java -cp out animals.Main
~~~

**Stdout:**

~~~text
named module=false
dog=woof
cat=meow
sealed=true
permitted=2
~~~

### 5.2. Explanation

- `-cp out` runs on the classpath; `Animal.class.getModule().isNamed()` returns false in this project.
- Animal, Dog, and Cat are all in **the same package animals**, so this is valid under the unnamed-module rule.
- They are not in the same source file: `permits Dog, Cat` **explicitly** declares the list when direct children reside in different compilation units.
- Dog/Cat are direct children, satisfying the final/non-sealed rule.
- Reflection `getPermittedSubclasses()` counts **the two direct children**, not all future subtypes.

Do not remove `permits` while keeping each type in a separate file and expect Java to discover them automatically: inferred permits only apply within the same compilation unit (section 12).

## 6. Intentionally Invalid: Unnamed Module with **Different Packages**

Create two files in a **separate** project (the code in this section intentionally fails to compile).

**`src/p/core/Base.java`**

~~~java
package p.core;

public sealed interface Base permits p.ext.Child {
}
~~~

**`src/p/ext/Child.java`**

~~~java
package p.ext;

public final class Child implements p.core.Base {
}
~~~

Try compiling in classpath-style:

~~~bash
mkdir out
javac --release 17 -d out src/p/core/Base.java src/p/ext/Child.java
~~~

**Result:** `javac` rejects this at compile time: the direct permitted Child belongs to `p.ext`, while the sealed Base belongs to `p.core` of the unnamed module. There is no stdout from a successfully running application; the exact stderr wording depends on the JDK version.

### 6.1. Why Can't `public` Save It?

`public` addresses one layer of **accessibility**. However, Java simultaneously checks the sealed location rule: **an unnamed module requires the same package**. A public child in a different package is still not sufficient.

### 6.2. Why Can't Moving the Files Into the Same Folder Save It?

The package is determined by `package p.ext;` in the source code, not solely by where the file is placed. Changing the folder without changing the package declaration does not turn p.ext into p.core.

### 6.3. What Are the Valid Ways to Fix This?

- Place the direct child and parent in **the same package** (updating declarations/imports accordingly).
- Or put them into **the same properly configured named module** if separating packages is intentional.
- Or use a `non-sealed` extension point in the same package for indirect descendants in other packages.
- Do not use reflection, `exports`, `opens`, or adding the public modifier as tricks to bypass a language rule.

## 7. Named Module: Valid Across **Different Packages**

A named module can contain multiple packages. Let's build a project with a sealed interface `geometry.api.Shape` and two direct implementing classes belonging to `geometry.circle` and `geometry.rect`, yet in **the same module**.

Structure:

~~~text
modular-shapes/
└── src/
    └── com.example.geometry/
        ├── module-info.java
        └── geometry/
            ├── api/
            │   └── Shape.java
            ├── circle/
            │   └── Circle.java
            ├── rect/
            │   └── Rectangle.java
            └── app/
                └── Main.java
~~~

**`src/com.example.geometry/module-info.java`**

~~~java
module com.example.geometry {
    exports geometry.api;
}
~~~

**`src/com.example.geometry/geometry/api/Shape.java`**

~~~java
package geometry.api;

public sealed interface Shape
        permits geometry.circle.Circle, geometry.rect.Rectangle {
    String describe();
}
~~~

**`src/com.example.geometry/geometry/circle/Circle.java`**

~~~java
package geometry.circle;

import geometry.api.Shape;

public final class Circle implements Shape {
    private final int radius;

    public Circle(int radius) {
        this.radius = radius;
    }

    @Override
    public String describe() {
        return "circle(r=" + radius + ")";
    }
}
~~~

**`src/com.example.geometry/geometry/rect/Rectangle.java`**

~~~java
package geometry.rect;

import geometry.api.Shape;

public final class Rectangle implements Shape {
    private final int width;
    private final int height;

    public Rectangle(int width, int height) {
        this.width = width;
        this.height = height;
    }

    @Override
    public String describe() {
        return "rect(" + width + "x" + height + ")";
    }
}
~~~

**`src/com.example.geometry/geometry/app/Main.java`**

~~~java
package geometry.app;

import geometry.api.Shape;
import geometry.circle.Circle;
import geometry.rect.Rectangle;

public class Main {
    public static void main(String[] args) {
        Shape a = new Circle(2);
        Shape b = new Rectangle(3, 4);

        System.out.println("module=" +
                Shape.class.getModule().getName());
        System.out.println(a.describe());
        System.out.println(b.describe());
        System.out.println("permitted=" +
                Shape.class.getPermittedSubclasses().length);
    }
}
~~~

### 7.1. Compiling and Running in Module Mode

From inside `modular-shapes`:

~~~bash
mkdir out
javac --release 17 --module-source-path src -d out -m com.example.geometry
java --module-path out -m com.example.geometry/geometry.app.Main
~~~

**Stdout:**

~~~text
module=com.example.geometry
circle(r=2)
rect(3x4)
permitted=2
~~~

### 7.2. Why Is This Project Valid?

1. The module descriptor declares **com.example.geometry**.
2. Shape, Circle, and Rectangle all belong to **the named module com.example.geometry**.
3. `Shape` is directly implemented by Circle/Rectangle.
4. Circle and Rectangle are public, so they are accessible when Shape is in a different package.
5. Both are final classes, valid as direct children of a sealed interface.
6. `permits` uses fully qualified names explicitly specifying the two different packages.
7. Main is in the same module, so it can use public classes from the module's packages; `exports geometry.api` is for external module consumers and does not grant cross-module permit permission.
8. `getPermittedSubclasses().length` returns 2.

### 7.3. Are `exports geometry.circle` and `exports geometry.rect` Needed?

**Not to make the permit valid.** Exports control public accessibility **from other modules**. Inside the com.example.geometry module itself, Main uses Circle/Rectangle normally because the classes are public, even though these packages are not exported.

An external module can use `Shape` if it reads com.example.geometry and the shape API is exported, but it cannot directly `implements Shape` in the external module due to the sealed location rule.

## 8. Comparing Module Mode and Classpath Mode

| Question | Classpath/unnamed | JPMS named |
| --- | --- | --- |
| Parent and child in the same package? | Allowed if other rules hold | Allowed if in the same module |
| Parent and child in different packages? | **Not allowed** as direct permit | **Allowed** if in the same module/access is valid |
| Parent and child in different named modules? | Not this organization model | **Not allowed** as direct permit |
| Can explicit multi-file `permits` be used? | Yes | Yes |
| Omit permits and infer from other files? | No | No |
| Does `exports` override the sealed restriction? | No | No |
| Is `final/sealed/non-sealed` still required? | Yes | Yes |
| Does `getPermittedSubclasses()` only return direct subtypes? | Yes | Yes |

**Do not infer:** “Two files belong to the same Gradle subproject” → same named module. Build tool names do not define module association; `module-info.java`, compiler mode, module path/classpath, and the actual module graph are what matter.

## 9. Sealed Class and Sealed Interface: Same Location Rule

For a sealed **class**:

~~~java
sealed class Parent permits First, Second {
}

final class First extends Parent {
}

non-sealed class Second extends Parent {
}
~~~

`First` and `Second` are classes whose direct superclass is Parent.

For a sealed **interface**:

~~~java
sealed interface Result permits Success, Failure, Extensible {
}

record Success(String value) implements Result {
}

final class Failure implements Result {
}

non-sealed interface Extensible extends Result {
}
~~~

`Success`/`Failure` are direct implementing classes; `Extensible` is a direct subinterface. All of them must satisfy the same named module or same package rule (if unnamed).

These examples are standalone **source snippets** that can be placed in an appropriate compilation unit; they have no separate main method. A record is implicitly final, so the permitted implementation Success does not need `final` written before `record`.

## 10. Program: Sealed Interface with Record Implementations

Save **`SealedRecordsDemo.java`**:

~~~java
public class SealedRecordsDemo {
    sealed interface Answer permits Yes, No {
        String text();
    }

    record Yes(String reason) implements Answer {
        @Override
        public String text() {
            return "yes:" + reason;
        }
    }

    record No(String reason) implements Answer {
        @Override
        public String text() {
            return "no:" + reason;
        }
    }

    public static void main(String[] args) {
        Answer a = new Yes("valid");
        Answer b = new No("missing");

        System.out.println(a.text());
        System.out.println(b.text());
        System.out.println("sealed=" + Answer.class.isSealed());
        System.out.println("direct=" +
                Answer.class.getPermittedSubclasses().length);
    }
}
~~~

Run:

~~~bash
javac --release 17 SealedRecordsDemo.java
java SealedRecordsDemo
~~~

Output:

~~~text
yes:valid
no:missing
sealed=true
direct=2
~~~

The member records reside in the same compilation unit as the sealed interface. They are final types, cannot be subclassed, and do not need `final` written explicitly.

## 11. Every Direct Child Must Choose Its Extension Status

If a **normal class** directly extends a sealed class or directly implements a sealed interface, it must declare:

- `final`: no further subclasses allowed.
- `sealed`: restricts the child's direct subclasses via its own `permits`.
- `non-sealed`: explicitly opens the branch to ordinary inheritance rules.

For an interface that directly extends a sealed interface, the appropriate status is `sealed` or `non-sealed`, not final. For records: `final` is implicit; enums have implicit final/sealed rules depending on constant-specific bodies.

### 11.1. Missing Modifier Example (Invalid)

~~~java
sealed interface Task permits Worker {
}

// class Worker implements Task {} // Invalid: missing final/sealed/non-sealed.

final class Worker implements Task {
}
~~~

If you remove final from Worker without replacing it with sealed or non-sealed, the compiler rejects it, even in the same package/module.

### 11.2. `non-sealed` Is Not a Modifier for Just Any Class

~~~java
// non-sealed class Independent {} // Invalid if there is no
// sealed direct superclass or sealed direct superinterface.
~~~

`non-sealed` is valid when it **responds to a direct sealed boundary**. A class that merely extends a non-sealed parent does not need it and generally may not declare `non-sealed` without a sealed direct parent/interface.

## 12. `permits` Only Allows **Direct** Types

Suppose:

~~~text
Base (sealed)
 ├── Closed (final)
 └── Gateway (non-sealed)
       └── Plugin (ordinary subclass)
~~~

`Base.permits` contains Closed/Gateway, **not Plugin**. Plugin is an indirect descendant through Gateway.

~~~java
sealed class Base permits Closed, Gateway {
}

final class Closed extends Base {
}

non-sealed class Gateway extends Base {
}

class Plugin extends Gateway {
}
~~~

The declarations can be in the same file/package. `Plugin` does not directly extend Base and is not an element of `Base.permits`.

### 12.1. What If Gateway Is Also Sealed?

If Gateway is `sealed class Gateway extends Base permits Plugin`, then Plugin must satisfy **Gateway's own permits location rule**. Each sealed node controls **one layer of direct children**.

### 12.2. Invalid When Listing a Grandchild

~~~java
// sealed class Base permits Plugin {} // Invalid if Plugin only extends Gateway.
~~~

A name in the same module/package is still **not enough** if it is not a direct subtype.

## 13. Program: Direct Subtype and Indirect Subtype

Save **`SealedDirectDemo.java`**:

~~~java
public class SealedDirectDemo {
    static abstract sealed class Base permits Closed, Open {
        abstract String label();
    }

    static final class Closed extends Base {
        @Override
        String label() {
            return "closed";
        }
    }

    static non-sealed class Open extends Base {
        @Override
        String label() {
            return "open";
        }
    }

    static class Extension extends Open {
        @Override
        String label() {
            return "extension";
        }
    }

    public static void main(String[] args) {
        Base value = new Extension();

        System.out.println("label=" + value.label());
        System.out.println("base sealed=" + Base.class.isSealed());
        System.out.println("permits=" +
                Base.class.getPermittedSubclasses().length);
        System.out.println("open sealed=" + Open.class.isSealed());
        System.out.println("extension instance=" +
                (value instanceof Base));
    }
}
~~~

Run:

~~~bash
javac --release 17 SealedDirectDemo.java
java SealedDirectDemo
~~~

Output:

~~~text
label=extension
base sealed=true
permits=2
open sealed=false
extension instance=true
~~~

`Extension` is still a Base instance through the subtype chain, yet it is not listed in Base permits, and `getPermittedSubclasses()` returns the count of **direct** subtypes, which is 2.

## 14. Special Case: `non-sealed` Opening Into Another Package in an Unnamed Module

If the sealed parent belongs to an unnamed module:

- The parent and the **direct Gateway** must be in the same package.
- However, the descendant `Plugin extends Gateway` can reside in a different package if Gateway is **non-sealed** and public/access rules are satisfied.

Create a project:

~~~text
extension-demo/
└── src/
    ├── p/
    │   ├── Root.java
    │   └── Gateway.java
    └── q/
        ├── Plugin.java
        └── Main.java
~~~

**`src/p/Root.java`:**

~~~java
package p;

public abstract sealed class Root permits Gateway {
    public abstract String kind();
}
~~~

**`src/p/Gateway.java`:**

~~~java
package p;

public non-sealed class Gateway extends Root {
    @Override
    public String kind() {
        return "gateway";
    }
}
~~~

**`src/q/Plugin.java`:**

~~~java
package q;

public final class Plugin extends p.Gateway {
    @Override
    public String kind() {
        return "plugin";
    }
}
~~~

**`src/q/Main.java`:**

~~~java
package q;

public class Main {
    public static void main(String[] args) {
        p.Root value = new Plugin();

        System.out.println(value.kind());
        System.out.println("root permits=" +
                p.Root.class.getPermittedSubclasses().length);
    }
}
~~~

Run from the project root:

~~~bash
mkdir out
javac --release 17 -d out src/p/Root.java src/p/Gateway.java src/q/Plugin.java src/q/Main.java
java -cp out q.Main
~~~

**Stdout:**

~~~text
plugin
root permits=1
~~~

Explanation: Root and Gateway are both in `package p` (same package); Plugin in `package q` only extends Gateway (non-sealed). Plugin does **not** directly extend Root, so the parent's sealed package restriction does not apply directly to Plugin.

**Avoid this misconception:** you must not write `Root permits q.Plugin`. Plugin is only a grandchild and is in a different package.

## 15. `non-sealed interface` as an Extension Point for Plugins

A sealed interface can directly permit a `non-sealed interface`, and then plugins in other packages/modules can implement that interface.

~~~java
sealed interface Event permits BuiltIn, PluginEvent {
}

record BuiltIn(String name) implements Event {
}

non-sealed interface PluginEvent extends Event {
}

final class CustomEvent implements PluginEvent {
}
~~~

PluginEvent is a **direct subinterface** of Event; CustomEvent is an **indirect implementation** through PluginEvent. Because the PluginEvent branch is non-sealed, subclassing is reopened under normal Java access rules.

### 15.1. Runnable Program

Save **`SealedPluginGatewayDemo.java`**:

~~~java
public class SealedPluginGatewayDemo {
    sealed interface Event permits BuiltIn, PluginEvent {
        String kind();
    }

    record BuiltIn(String kind) implements Event {
    }

    non-sealed interface PluginEvent extends Event {
    }

    static final class CustomEvent implements PluginEvent {
        @Override
        public String kind() {
            return "custom";
        }
    }

    public static void main(String[] args) {
        Event a = new BuiltIn("builtin");
        Event b = new CustomEvent();

        System.out.println(a.kind());
        System.out.println(b.kind());
        System.out.println("permits=" +
                Event.class.getPermittedSubclasses().length);
        System.out.println("gateway sealed=" +
                PluginEvent.class.isSealed());
    }
}
~~~

Run:

~~~bash
javac --release 17 SealedPluginGatewayDemo.java
java SealedPluginGatewayDemo
~~~

Output:

~~~text
builtin
custom
permits=2
gateway sealed=false
~~~

If PluginEvent is public and exported from a provider named module, a consumer module can directly implement PluginEvent (given sufficient accessibility), while still only **indirectly** being an Event. That is a valid extension point architecture; it does not circumvent the direct sealed restriction.

## 16. Explicit `permits` and Inferred permits Are Two Distinct Mechanisms

Java allows a sealed class/interface to **omit `permits`** in certain cases. The compiler can infer the permitted direct subclasses/subinterfaces from declarations within the **same compilation unit**.

**Same compilation unit ≈ same Java source file**, not all files in the same package or all files passed to a single `javac` command.

If a direct child resides in a **separate file**, even in the same named module or the same package, do not expect the compiler to scan files to infer it. Use explicit `permits`.

### 16.1. Inference Program in the Same Source File

Save **`InferredPermitsDemo.java`**:

~~~java
public class InferredPermitsDemo {
    sealed interface Action {
        String execute();
    }

    record Start() implements Action {
        @Override
        public String execute() {
            return "start";
        }
    }

    record Stop() implements Action {
        @Override
        public String execute() {
            return "stop";
        }
    }

    public static void main(String[] args) {
        Action a = new Start();
        Action b = new Stop();

        System.out.println(a.execute());
        System.out.println(b.execute());
        System.out.println("inferred=" +
                Action.class.getPermittedSubclasses().length);
    }
}
~~~

Run:

~~~bash
javac --release 17 InferredPermitsDemo.java
java InferredPermitsDemo
~~~

Output:

~~~text
start
stop
inferred=2
~~~

Both Start/Stop reside in the same source file as Action and directly implement Action, so the compiler infers the permits list even though Action does not declare a permits clause.

### 16.2. Separate Files Require Explicit permits

~~~text
Action.java: sealed interface Action permits Start, Stop { ... }
Start.java:  final class Start implements Action { ... }
Stop.java:   final class Stop implements Action { ... }
~~~

This is a diagram, not a single valid Java file. If Action.java only has `sealed interface Action {}` while the direct types are in other files, the compiler will not infer them just because they are in the same package.

### 16.3. Are Local/Anonymous Classes Inferred?

No. Inference requires direct subtypes with a canonical name in the same compilation unit. Local classes and anonymous classes are not inferred into the list to open up a sealed hierarchy.

## 17. `permits` Is Not an Arbitrary List

A permits clause must use accessible type names, must not contain duplicate entries, and each type must be a **direct subtype** of the parent.

### 17.1. Named in permits Without Extending

~~~java
sealed class Root permits Child {
}

// final class Child { } // Invalid if it does not extend Root.
final class Child extends Root {
}
~~~

Even with the right location, an **inheritance relation** is still required.

### 17.2. Do Not List a Type Twice

~~~java
// package p;
// sealed class Root permits Child, p.Child { } // Invalid: duplicate type.
// final class Child extends Root { }
~~~

A simple name and a fully qualified name pointing to the same Child do not create two separate permissions.

### 17.3. Package-Private Types Across Package Boundaries

In an unnamed module, a parent and child in the same package can use package-private declarations. In a named module, if the child is in a **different package**, the parent generally requires the child to be public/accessible to refer to it by name in `permits`. Being in the same module **does not eliminate** Java access restrictions.

## 18. How Do `exports` and `requires` Differ from `permits`?

In JPMS:

- `requires other.module;` establishes a dependency/readability according to the module descriptor.
- `exports api.package;` opens access to public types in this package for valid readers.
- `opens some.package;` pertains to reflective access; it does not grant permission to extend a sealed type.
- `permits MyChild` belongs to the Java sealed declaration, specifying the allowed direct subtypes.

Provider module example:

~~~java
module com.example.geometry {
    exports geometry.api;
}
~~~

A consumer can do:

~~~java
module consumer.module {
    requires com.example.geometry;
}
~~~

And then use `geometry.api.Shape` as a parameter/return type through the public API. However, a `consumer.impl.CustomShape` in **consumer.module** cannot directly `implements Shape`, even when Shape is public/exported. The **same named module** requirement still applies.

### 18.1. Why Can't `requires transitive` Solve This?

`requires transitive` changes readability between modules; it does not change where a class is declared. A cross-module direct sealed subclass remains a compile-time error.

### 18.2. Exporting a Package Is Not Required for Internal Permits

In the modular-shapes project, `geometry.circle` is not exported. Shape still permits Circle because they are in the **same named module**, and the compiler sees Circle as public/accessible. Exports are only needed when another module must access that package.

## 19. Are Different Named Modules with the Same Package Name Allowed?

**No.** The named module rule checks **same named module association**, not just the package string. If Root belongs to named module A and the direct child belongs to named module B, even if the package names match or the build attempts to organize a split package, the direct permit is still invalid.

JPMS also has its own constraints around split packages/readability. Do not design a cross-module hierarchy by naming both packages `api` and assuming Java will treat them as a single shared namespace.

**Principle:** a named-module branch must genuinely reside within **one** named module, not two modules whose names appear related.

## 20. Same JAR, Automatic Modules, and Runtime Mode

A JAR placed on the **classpath** undergoes classpath loading, typically into the **unnamed module**. Multiple packages inside the same JAR are **not automatically** allowed to form a cross-package direct sealed hierarchy.

A JAR placed on the **module path** can become an explicit named module (if it has a descriptor), or an automatic module under module-system rules if applicable. An automatic module counts as a **named module** with respect to module association, though the actual code/build layout and constraints must still be verified properly. You should not rely on “same artifact” and overlook module configuration.

Observing the runtime module type:

~~~java
System.out.println(SomeType.class.getModule().isNamed());
System.out.println(SomeType.class.getModule().getName());
~~~

In the classpath demo, isNamed is false; in the modular-shapes demo, the name is `com.example.geometry`. This is a runtime diagnostic and does not replace compiler source checks.

## 21. Reflection: Inspecting Sealed Metadata in Java 17

Useful APIs:

- `Class.isSealed()`: runtime status of whether the class/interface is sealed.
- `Class.getPermittedSubclasses()`: returns the **permitted direct types**. For a non-sealed class/interface it may return null, so do not call `.length` carelessly.
- `Class.getModule()` and `Module.isNamed()`: module association.
- `Class.getPackageName()`: Java package name, useful when checking the unnamed-module same-package case.
- `Class.getSuperclass()`/`getInterfaces()`: inspect relations; distinguish direct from indirect.

**Do not confuse these:** reflection allows **reading metadata**. It does not grant permission to create a direct subclass outside the permitted list/module/package.

### 21.1. Runnable Program Without a Named Package

Save **`SealedReflectionDemo.java`**:

~~~java
public class SealedReflectionDemo {
    sealed interface Node permits Leaf, Branch {
    }

    record Leaf(int value) implements Node {
    }

    non-sealed interface Branch extends Node {
    }

    public static void main(String[] args) {
        Class<?> type = Node.class;

        System.out.println("sealed=" + type.isSealed());
        System.out.println("named=" +
                type.getModule().isNamed());
        System.out.println("package=" + type.getPackageName());
        System.out.println("direct=" +
                type.getPermittedSubclasses().length);
        System.out.println("branch sealed=" +
                Branch.class.isSealed());
    }
}
~~~

Run:

~~~bash
javac --release 17 SealedReflectionDemo.java
java SealedReflectionDemo
~~~

Output:

~~~text
sealed=true
named=false
package=
direct=2
branch sealed=false
~~~

`package=` has nothing after the equals sign because the demo program declares no package and `getPackageName()` returns an empty string. Production code should use named packages, though the default package is valid for demonstrating unnamed-module behavior.

## 22. Proactive Contract Test Program

Save **`SealedLocationTest.java`**:

~~~java
public class SealedLocationTest {
    sealed interface Animal permits Dog, Cat {
        String sound();
    }

    record Dog() implements Animal {
        @Override
        public String sound() {
            return "woof";
        }
    }

    record Cat() implements Animal {
        @Override
        public String sound() {
            return "meow";
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        check(Animal.class.isSealed(), "sealed");
        check(!Animal.class.getModule().isNamed(), "unnamed");
        check(Animal.class.getPermittedSubclasses().length == 2,
                "direct permits");
        check(Dog.class.getModule() == Animal.class.getModule(),
                "same runtime module");
        check(Dog.class.getPackageName().equals(
                Animal.class.getPackageName()), "same package");

        Animal dog = new Dog();
        Animal cat = new Cat();
        check("woof".equals(dog.sound()), "dog");
        check("meow".equals(cat.sound()), "cat");

        System.out.println("sealed location tests passed");
    }
}
~~~

Run in a new directory on the classpath:

~~~bash
javac --release 17 SealedLocationTest.java
java SealedLocationTest
~~~

Output:

~~~text
sealed location tests passed
~~~

The `check` method performs explicit checks instead of using `assert` (which is disabled by default unless `-ea` is passed). The test only confirms **a valid program**. For scenarios **forbidden by the Java compiler**, you need to analyze the JLS or compile the invalid examples separately; there is no valid runtime test to “prove” that a class was rejected by the compiler.

## 23. Common Mistakes About Same Module/Package

| Misconception | Correct rule |
| --- | --- |
| “In the same Gradle module, different packages can still be permitted.” | Must verify the **JPMS named module**, not rely on build-tool naming. |
| “Being in the same classpath JAR is enough.” | Unnamed module → direct children must be in the same package. |
| “In JPMS every permitted child must be in the same package.” | Named module → can be in a different package if in the same module and accessible. |
| “Having the same package in two named modules is enough.” | Must be in the same named module; a package name does not replace a module boundary. |
| “`public` lifts the cross-package restriction on the classpath.” | Public only resolves access; it does not lift the sealed location rule. |
| “`exports` allows downstream direct implementations.” | Exports do not grant cross-module direct sealed subtype permission. |
| “`opens` or reflection can add a permitted class.” | Cannot override the JLS sealed declaration. |
| “`permits` contains every descendant.” | Only direct children. |
| “A grandchild must be in the same package as the sealed ancestor.” | Not necessarily, if going through a non-sealed branch. |
| “A non-sealed branch means Root is no longer sealed.” | Root remains sealed and has fixed direct permits. |
| “A `final` child can be extended via `extends` in another package.” | Final forbids subclassing. |
| “A `sealed` child does not need its own permits.” | If the child is sealed, it must declare/infer valid direct permits. |
| “A class listed in `permits` does not need to extend the parent.” | It must be a direct subtype. |
| “Listing the same type twice in permits is valid.” | Duplicate types are forbidden. |
| “A `sealed interface` cannot permit a record.” | A record is implicitly final and can implement it. |
| “Forgetting final/sealed/non-sealed is fine if in the same package.” | A direct normal child must have a suitable status modifier. |
| “Being in the same package in another file is enough for the compiler to infer permits.” | Inferred permits only come from the same compilation unit. |
| “An anonymous/local class can be inferred into permits.” | Canonical named declarations are required; local/anonymous classes are not inferred. |
| “The package name is taken from any folder.” | The source `package` declaration determines the namespace; the build layout must align with it. |
| “All modules on the module path are the same module.” | Each named module has its own identity. |

## 24. Design and Build Verification Checklist

1. Is the sealed parent in a **named module** or an **unnamed module**?
2. Is the parent a **sealed class** or a **sealed interface**?
3. Has every direct permitted subtype been identified by actual `extends`/`implements`/`extends interface` arrows?
4. Named → do all direct children belong to **the exact same named module**?
5. Unnamed → do all direct children have **the same `package` declaration**?
6. If named and the child is in a different package, is the child's accessibility appropriate?
7. Are the public/protected constructors accessible when extending a cross-package class?
8. Are any names in `permits` duplicated, inaccessible, or unrelated?
9. Do direct normal classes have the proper final/sealed/non-sealed modifier?
10. Do direct interfaces have the appropriate sealed/non-sealed modifier?
11. Is the implicit status of records/enums understood properly?
12. Does a sealed child have its own permits hierarchy?
13. If permits is omitted, are the children in the same compilation unit with canonical names?
14. If children are in separate files, has explicit permits been declared?
15. Are grandchildren being confused with permitted direct subclasses?
16. Has the `non-sealed` extension point been chosen intentionally?
17. Is classpath code being confused with module path code when running tests?
18. Does `module-info.java` have the right module name and exports/access?
19. Are there any dependency cycles, split packages, or JPMS readability issues?
20. Are tests run in the exact same mode as the actual application?
21. Should consumer extension go through a non-sealed interface instead of directly implementing the sealed root?
22. Are you using Java 17+ without unnecessarily enabling preview features?
23. Are `javac` error messages understood by their root cause rather than forcing an exact line-by-line stderr match?
24. Have you verified that `Class.getPermittedSubclasses()` only reports direct permitted types?

## 25. Practice Exercises and Answers

**Question 1.** A sealed parent is in named module M, and the child is in a different package but still in M—is this allowed?  
**Answer:** Yes, if the child is accessible/directly permitted and satisfies all other rules.

**Question 2.** The parent is in unnamed module package p, and the child is in package q on the same classpath—is this allowed?  
**Answer:** Not for a direct child. An unnamed module requires the same package.

**Question 3.** Can two source files in package p in an unnamed module, but in different files, be permitted?  
**Answer:** Yes, if `permits` is explicit and the direct relationship/modifier rules are satisfied.

**Question 4.** In the same package p, but in two different named modules—is this allowed?  
**Answer:** No, the named module location rule requires the same module.

**Question 5.** Why can't `public` alone fix a cross-package unnamed-module error?  
**Answer:** Public access and the same-package sealed restriction are two separate checks.

**Question 6.** Does `module-info.java` allow using `exports` so a consumer can implement a sealed root directly?  
**Answer:** No; exports only determine public API access.

**Question 7.** Can a sealed class permit an interface?  
**Answer:** No; a direct subclass of a class must be a class that extends it.

**Question 8.** Can a sealed interface permit another interface?  
**Answer:** Yes, that interface directly extends the parent.

**Question 9.** Can a sealed interface permit a record?  
**Answer:** Yes, a record directly implements the sealed interface, and a record is implicitly final.

**Question 10.** Why must a direct normal class be `final`/`sealed`/`non-sealed`?  
**Answer:** To decide whether further extension is allowed; Java requires an explicit posture at the sealed boundary.

**Question 11.** Is `sealed Root permits Grandchild` valid if Grandchild only extends Middle which extends Root?  
**Answer:** Invalid; Grandchild is not a direct subtype.

**Question 12.** A sealed parent class permits a non-sealed class in the same package; can a grandchild be in a different package?  
**Answer:** Yes, because the grandchild only extends the non-sealed child and follows normal visibility rules.

**Question 13.** If a child is itself sealed, how are grandchildren controlled?  
**Answer:** By the sealed child's own permits list and location rules.

**Question 14.** Does inferred permits scan all source files in the same module?  
**Answer:** No. Only the same compilation unit.

**Question 15.** Why is directly implementing/extending still required even when placed in the same Java file?  
**Answer:** Being in the same compilation unit enables the inferred list; it does not waive the direct subtype requirement.

**Question 16.** What does `Class.isSealed()` return for a `non-sealed` branch?  
**Answer:** False; the parent remains sealed.

**Question 17.** Does `getPermittedSubclasses()` count grandchildren?  
**Answer:** No, only permitted direct types.

**Question 18.** Can every direct subtype in a named module be package-private across different packages?  
**Answer:** Not by default; the type must be accessible from the sealed parent. A cross-package top-level type generally needs to be public.

**Question 19.** Does a public module API in an exported package allow downstream modules to directly extend a sealed parent?  
**Answer:** No, because the parent still requires direct subtypes to be in the same named module.

**Question 20.** What is `non-sealed interface Gateway extends SealedRoot` useful for?  
**Answer:** It enables an open extension branch without opening the direct variants of SealedRoot.

**Question 21.** Can a JLS violation be fixed with `requires transitive`?  
**Answer:** No; that governs module readability and does not alter the sealed direct location rule.

**Question 22.** Does being in the same JAR imply being in the same named module?  
**Answer:** No; check whether the JAR is on the classpath or module path, along with its descriptor/automatic module handling.

**Question 23.** Does Java 17 require `--enable-preview` for sealed types?  
**Answer:** No, it has been an official standard feature since Java 17.

**Question 24.** What is the first step when the compiler reports a sealed location error?  
**Answer:** Identify the actual named/unnamed module and the package declarations of the parent and direct child.

## 26. Official References

- [JLS Java SE 17 `8.1.6 — Permitted Direct Subclasses](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.6): same named module or same package condition for sealed classes, and inferred permits.
- [JLS Java SE 17 `9.1.4 — Permitted Direct Subclasses and Subinterfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.4): corresponding rules for sealed interfaces.
- [JLS Java SE 17 `8.1.1.2 — sealed, non-sealed, final Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.2): behavior of direct classes.
- [JLS Java SE 17 `9.1.1.4 — sealed and non-sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.1.4): behavior of direct subinterfaces.
- [JLS Java SE 17 `7.3 — Compilation Units](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.3): the unit for permits inference.
- [JLS Java SE 17 `7.7 — Module Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7) and [`7.7.5 — Unnamed Modules](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.5): module associations.
- [JLS Java SE 17 `6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6): accessible types and package boundaries.
- [OpenJDK JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): design goals and standardization of sealed types in Java 17.
- [Java 17 API Class.isSealed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isSealed()): metadata introspection.
- [Java 17 API Class.getPermittedSubclasses](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getPermittedSubclasses()): direct permitted classes/interfaces.
- [Java 17 API Class.getModule](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getModule()) and [Module.isNamed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html#isNamed()): runtime module identity.
- [Java 17 javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html) and [java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `--release`, `--module-source-path`, `-cp`, `--module-path`, and `-m`.

## Summary

**A sealed class/interface restricts the set of direct permitted subtypes.** In Java 17, valid placement depends on module association:

- **Named module:** the sealed parent and each direct permitted subtype are in **the same named module**, and may be in different packages when accessibility and inheritance rules are satisfied.
- **Unnamed module:** the sealed parent and direct permitted subtypes are in **the same package**, even when they reside in the same classpath, JAR, or project.
- **Direct subtypes only:** a grandchild through a `non-sealed` gateway does not need to be in the sealed ancestor's `permits`; it follows the rules of its branch along with normal access/module rules.
- **Not inferred across all files:** the compiler only infers permits when direct types are declared in **the same compilation unit**; if the source files differ, write explicit `permits`.

When encountering an error, check in order: **named/unnamed module → package → direct extends/implements → permits list → final/sealed/non-sealed → accessibility/readability**. This approach both ensures the code compiles and preserves the design intent of keeping sealed hierarchies within a clear maintenance boundary.
