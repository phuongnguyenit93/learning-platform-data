# Sealed in Java 17: Same *Named Module* or Same Package in an *Unnamed Module*

In Java 17, `sealed` lets a class or interface **directly restrict which types may inherit or implement it**. The list of permitted types usually follows the `permits` keyword. However, listing a type in `permits` **is not enough**: its location within a **module** or **package** must also be valid.

The core rule:

> If the `sealed` type belongs to a **named module**, all permitted **direct** inheriting/implementing types must reside in that **same named module**. If the `sealed` type belongs to an **unnamed module**, all permitted direct types must reside in the **same package** as the `sealed` type.

This rule applies to both `sealed class` and `sealed interface`. It is a Java 17 language constraint checked by the compiler, not a setting you can bypass by adding `import`, `exports`, or modifying `PATH`.

## 1. Concepts to distinguish

### `sealed` and `permits`

Example of an interface permitting strictly two direct implementations:

```java
package example.payment;

public sealed interface Payment permits CashPayment, CardPayment {
    String description();
}
```

`CashPayment` and `CardPayment` are **permitted direct subtypes**. They must actually `implements Payment`, not merely appear in `permits`. With a `sealed` class, permitted types must directly `extends` that class; with a `sealed` interface, permitted types must directly `extends` (subinterface) or `implements` (implementing class) that interface.

Direct subtypes must also declare how the hierarchy continues, for instance:

```java
package example.payment;

public final class CashPayment implements Payment {
    @Override
    public String description() {
        return "Cash payment";
    }
}
```

A direct subclass must generally use one of the three modifiers `final`, `sealed`, or `non-sealed` (syntactic exceptions for types with special properties like `record` are handled by Java accordingly). A direct subinterface may use `sealed` or `non-sealed`, because interfaces cannot be `final`.

### Packages and modules are two different organizational levels

| Concept | Meaning | Example |
| --- | --- | --- |
| **Package** | Groups Java types by their `package` declaration name. | `example.payment` and `example.payment.impl` are **two different packages**. |
| **Named module** | A module with a name, typically declared in `module-info.java` of a JPMS project. One module can contain multiple packages. | `module example.billing { ... }` |
| **Unnamed module** | A module without a name, typically holding classes loaded from the **classpath** in applications not using named modules. | `.class` files run via `java -cp out ...` without a module descriptor. |

**Do not confuse an *unnamed module* with the *unnamed/default package*.** You can still declare `package example.payment;` and run code in the unnamed module. Conversely, structured package names do not automatically turn a project into a named module: module membership depends on how code is organized, compiled, and loaded.

## 2. Rule table for direct subtypes

| Where the `sealed` type is declared | Where types listed in `permits` must reside | Can they be in different packages? | Can they be in different modules? |
| --- | --- | --- | --- |
| **Named module** | **Same named module** as the `sealed` type. | **Yes**, provided Java type accessibility remains valid. | **No**. |
| **Unnamed module** | **Same package** as the `sealed` type. | **No**. | Being in another module cannot bypass the same-package requirement. |

Illustration:

```text
Named module: example.billing
├── package example.billing.api
│   └── Payment (sealed)
└── package example.billing.impl
    ├── CashPayment (final)   ✓ different package, same module
    └── CardPayment (final)   ✓ different package, same module

Unnamed module (classpath)
├── package example.payment
│   ├── Payment (sealed)
│   ├── CashPayment (final)   ✓ same package
│   └── CardPayment (final)   ✓ same package
└── package example.payment.impl
    └── MobilePayment (final) ✗ cannot be a direct subtype
                                    permitted by Payment
```

These restrictions apply only to **direct inheritance/implementation relationships** controlled by the `sealed` type. A `non-sealed` subtype can reopen inheritance for subsequent levels; those deeper types do not need to be listed in the `sealed` ancestor's `permits`.

## 3. Valid example: named module, different packages in the same module

Suppose we build a Java 17 application with the module `demo.sealed`. The subtypes live in package `demo.impl`, while the root interface is in `demo.api`.

### Directory structure

```text
project/
└── src/
    └── demo.sealed/
        ├── module-info.java
        └── demo/
            ├── Main.java
            ├── api/
            │   └── Payment.java
            └── impl/
                ├── CashPayment.java
                └── CardPayment.java
```

**`src/demo.sealed/module-info.java`**

```java
module demo.sealed {
    exports demo.api;
}
```

The module only exports the API package for other modules to use. `demo.impl` does not need `exports` for `Payment` to permit two classes inside the **same module**.

**`src/demo.sealed/demo/api/Payment.java`**

```java
package demo.api;

public sealed interface Payment
        permits demo.impl.CashPayment, demo.impl.CardPayment {
    String description();
}
```

`permits` here uses the **fully qualified names** of the two types in the other package. That clarifies where they reside; it does not replace the same-module requirement.

**`src/demo.sealed/demo/impl/CashPayment.java`**

```java
package demo.impl;

import demo.api.Payment;

public final class CashPayment implements Payment {
    @Override
    public String description() {
        return "Cash";
    }
}
```

**`src/demo.sealed/demo/impl/CardPayment.java`**

```java
package demo.impl;

import demo.api.Payment;

public final class CardPayment implements Payment {
    @Override
    public String description() {
        return "Card";
    }
}
```

**`src/demo.sealed/demo/Main.java`**

```java
package demo;

import demo.api.Payment;
import demo.impl.CashPayment;

public class Main {
    public static void main(String[] args) {
        Payment payment = new CashPayment();
        System.out.println(payment.description());
    }
}
```

From the `project` directory, compile the entire named module and run `Main`:

```bash
javac --module-source-path src -d out -m demo.sealed
java --module-path out -m demo.sealed/demo.Main
```

Output:

```text
Cash
```

**Why is this valid?** `Payment`, `CashPayment`, and `CardPayment` all belong to **module `demo.sealed`**, even though `demo.api` and `demo.impl` are separate packages. Every permitted subclass directly `implements Payment` and is marked `final`. Within the same module, `Main` can also use `demo.impl` even though that package is not exported to external modules.

### What does `exports` do in this example?

`exports demo.api` controls access to **public types** in `demo.api` from other modules. It **does not grant permission** for a class in another module to become a direct subtype of a `sealed` type in `demo.sealed`. Similarly, `requires` lets a module read another module, without changing `permits` rules.

If code in other modules needs to call `demo.impl` directly, exporting that package may be part of the API design. Still, exporting `demo.impl` is **not required** just to let two subtypes in the **same module** implement `Payment`.

## 4. Valid example: unnamed module, subtypes in the same package

For Java 17 applications running on the **classpath** without `module-info.java`, subtypes listed in `permits` must be in the same package as the `sealed` type.

### Directory structure

```text
project/
└── src/
    └── sample/
        └── payment/
            ├── Payment.java
            ├── CashPayment.java
            ├── CardPayment.java
            └── Main.java
```

**`src/sample/payment/Payment.java`**

```java
package sample.payment;

public sealed interface Payment permits CashPayment, CardPayment {
    String description();
}
```

**`src/sample/payment/CashPayment.java`**

```java
package sample.payment;

public final class CashPayment implements Payment {
    @Override
    public String description() {
        return "Cash";
    }
}
```

**`src/sample/payment/CardPayment.java`**

```java
package sample.payment;

public final class CardPayment implements Payment {
    @Override
    public String description() {
        return "Card";
    }
}
```

**`src/sample/payment/Main.java`**

```java
package sample.payment;

public class Main {
    public static void main(String[] args) {
        Payment payment = new CardPayment();
        System.out.println(payment.description());
    }
}
```

From the `project` directory, use `-cp` to run on the classpath:

```bash
javac -d out src/sample/payment/Payment.java src/sample/payment/CashPayment.java src/sample/payment/CardPayment.java src/sample/payment/Main.java
java -cp out sample.payment.Main
```

Output:

```text
Card
```

**Why is this valid?** `Payment`, `CashPayment`, and `CardPayment` all declare `package sample.payment;`. This project defines no named module, so the **same-package** requirement is met. Files can sit in different disk locations under complex build configurations, but the rule checks the **package declared in Java code**, not merely folder names.

Note: `sample.payment` and `sample.payment.impl` are **two independent packages**. In Java, a package sharing a name prefix is not considered "inside" a parent package at the language level; sharing a prefix is not enough to satisfy `sealed`'s requirement.

## 5. Invalid cases and how to fix them

### Case A: unnamed module with subclass in a different package

**`sample/api/Action.java`**

```java
package sample.api;

public sealed interface Action permits sample.impl.RunAction {
}
```

**`sample/impl/RunAction.java`**

```java
package sample.impl;

import sample.api.Action;

public final class RunAction implements Action {
}
```

The two files are in different packages (`sample.api` and `sample.impl`). If compiled in an unnamed module on the classpath, this declaration is **invalid**, even when `RunAction` is `public`, has a valid `import`, and is listed in `permits`.

**Fix:** Move `RunAction` into the same `package sample.api` **or** organize them into a single **named module** if the project genuinely needs separate packages. There is no need to remove `sealed` just to keep a subclass in a different package when an appropriate named module can be used.

### Case B: two different named modules

Suppose:

```text
module sales.core
└── package sales.api
    └── sealed interface Order

module sales.extensions
└── package sales.impl
    └── class OnlineOrder implements Order
```

Even if `sales.extensions` declares `requires sales.core` and `sales.core` exports `sales.api`, `OnlineOrder` **cannot be a direct subtype permitted by `Order`** because the two types live in two different named modules. `requires`/`exports` governs inter-module API visibility, not relaxing `sealed` boundaries.

**Fix:** Place permitted direct subtypes in the same named module as `Order`. If external modules need to define new subtypes, redesign the extension point—for example, place a permitted `non-sealed` intermediate class/interface **inside `sales.core`**, then let types in external modules inherit/implement that intermediate type when access rules allow:

```java
// In named module sales.core, package sales.api
public sealed interface Order permits ExtensibleOrder {
}

// In the same named module sales.core, package sales.api
public non-sealed interface ExtensibleOrder extends Order {
}
```

A class in another module can `implements ExtensibleOrder` if the module and type are properly exported/accessible. That class is **not a direct subtype of `Order`**, so it neither needs to be nor can be added directly to `Order`'s `permits` from another module.

### Case C: declaring `permits` without a direct inheritance relationship

```java
package sample.payment;

public sealed interface Payment permits VoucherPayment {
}

final class VoucherPayment { // Error: does not implement Payment
}
```

Both types are in the same package, yet `VoucherPayment` does not `implements Payment`; appearing in `permits` does not create an inheritance relationship automatically. The fix is to add `implements Payment` to `VoucherPayment` (and implement any required methods).

### Case D: missing `final`, `sealed`, or `non-sealed` on a direct subtype

```java
package sample.payment;

public sealed interface Payment permits VoucherPayment {
}

class VoucherPayment implements Payment { // Error: further extensibility unspecified
}
```

A regular class directly implementing a `sealed interface` must explicitly state its choice: `final class VoucherPayment`, `sealed class VoucherPayment permits ...`, or `non-sealed class VoucherPayment`. Having the right module/package location is still insufficient if the modifier rule is not satisfied.

## 6. Explicit `permits` vs. compiler inference

For clarity, previous examples declared `permits` explicitly. In Java 17, if direct subtypes are declared **in the same compilation unit (the same Java source file)** as the `sealed` type, the compiler can **infer the list of permitted subtypes** without writing `permits`.

Example single file `Vehicle.java`:

```java
package sample.transport;

public sealed interface Vehicle {
}

final class Bicycle implements Vehicle {
}

final class Scooter implements Vehicle {
}
```

Both classes are in `Vehicle.java` and in the same package, so `Vehicle` can omit `permits`. This is syntactic convenience, **not an exception to the module/package rule**. When subtypes are placed in separate files, you generally need to list them in the `sealed` type's `permits` clause.

## 7. When does the constraint apply to the next level down?

Consider the hierarchy:

```java
package app.api;

public sealed interface Event permits InternalEvent, ExternalEvent {
}

final class InternalEvent implements Event {
}

non-sealed interface ExternalEvent extends Event {
}
```

`InternalEvent` and `ExternalEvent` are **two direct subtypes** of `Event`, so they obey the same-module/same-package rule. Once `ExternalEvent` is declared `non-sealed`, classes **implementing `ExternalEvent`** at the next tier can be extended under normal module, package, and accessibility rules. If `ExternalEvent` is accessible from another module, classes in that module can implement `ExternalEvent` even without appearing in `Event`'s `permits`.

Conversely, if `ExternalEvent` is also declared `sealed`, it must define its own set of permitted direct subtypes, and those subtypes must obey the named-module or unnamed-module rule corresponding to where `ExternalEvent` is declared.

Thus, always ask **"Which `sealed` type does this type directly inherit from?"** when determining whether the rule still applies at a given level.

## 8. Diagnosing and fixing errors in practice

| Situation | What to check | How to resolve |
|---|---|---|
| Class is listed in `permits` yet reported as wrong package. | Is `module-info.java` actually compiled as a named module, or is code running on the classpath/unnamed module? | When using an unnamed module, move the direct subtype into the **same package** as the sealed type. |
| Two types share a package prefix yet are rejected. | `a.b` and `a.b.impl` are two distinct packages. | Use the **exact same** package name or place both in one named module. |
| Subtype in another package within a named module is inaccessible. | Is the type `public`, is the name in `permits` correct, is the import valid? | Fix visibility and type names; **same module** allows different packages without bypassing `public`/package-private rules. |
| Type in another module is still disallowed despite `exports` and `requires`. | Are both types truly in the same named module? | Move the direct subtype to the same module or design an extension point via `non-sealed`. |
| Subtype is in the right place yet still fails. | Does it have direct `extends`/`implements` and the right modifier? | Add the direct inheritance relationship and declare `final`, `sealed`, or `non-sealed`. |
| Unclear why a `-cp` example differs from a `--module-path` example. | Is the type in an unnamed module or a named module? | Use `module-info.java` and compile/run modularly if you want a named-module model; use classpath for unnamed-module examples. |

**Note on runtime paths:** `-cp`/`--class-path` specifies the classpath; `--module-path` specifies where to find modules. Some JARs without `module-info.class` can become **automatic modules** when placed on the module path, so never deduce a type's module solely from a JAR name or package name. The two main examples above deliberately use a named module with `module-info.java` and a classpath application to keep the rules distinct.

## 9. Remembering via three questions

**1. Can a `sealed interface` in named module A `permits` a class in a different package that is still inside module A?** Yes, if the subtype has valid access and directly `implements`/`extends` the interface; different packages do not block this within the same named module.

**2. Can a `sealed class` on the classpath in package `com.shop.core` permit a subclass in `com.shop.core.impl`?** No. Those are two different packages; in an unnamed module, direct subtypes must be in `com.shop.core`.

**3. Does adding `exports`, `requires`, or `import` let you `permits` a direct subtype in another module?** No. Those affect type visibility and usage, not `sealed`'s same-named-module constraint.

### References

- [JEP 409 — Sealed Classes (finalized in Java 17)](https://openjdk.org/jeps/409)
- [Java Language Specification 17 — §8.1.6 Sealed Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.6)
- [Java Language Specification 17 — §9.1.4 Sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.4)
- [Java Language Specification 17 — Modules](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7)
