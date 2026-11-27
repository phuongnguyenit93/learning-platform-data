# Distinguishing Accessibility from Inheritance Permission in Java 17

## 1. Two different questions when designing a type

When reading a Java declaration, separate two questions:

1. **Who can see and use this type or member?** This is a question of **accessibility**, controlled by `public`, `protected`, `private`, package-private default access, and, across module boundaries, `exports` declarations.
2. **Which types are allowed to directly inherit or implement this type?** This is a question of **inheritance permission**, controlled by `final`, `sealed`, `permits`, `non-sealed`, along with other Java rules on supertypes and subtypes.

Both sets of rules must be satisfied. A class can **see** a `public` class or interface and still **not be allowed to `extends`/`implements`** that `sealed` type. Conversely, having a subtype listed in `permits` does not exempt it from accessibility requirements, inheritance validity rules, or package/module scope constraints.

Mental model:

> A library publishes `public sealed interface Result` so any application can use `Result`. Yet the library permits only a few result types listed in `permits` to implement this interface directly. **Public for consumption** does not mean **open for arbitrary extension**.

That is the core purpose of `sealed` in Java 17: letting the model author control the **set of direct subtypes** while still exposing the API externally as needed.

## 2. What does accessibility control?

### 2.1. Familiar access levels

| Access level | Where applicable? | Main rule |
|---|---|---|
| `public` | Top-level types, nested types, members | Accessible from elsewhere if enclosing types and module boundaries also allow it |
| `protected` | Members and nested member types (not top-level types) | Accessible within the same package; outside the package, accessible to subclasses with restrictions on how it is accessed |
| *package-private* (no modifier) | Top-level types, nested types, members | Accessible from classes in the same package |
| `private` | Members and nested types (not top-level types) | Accessible only within the enclosing declaration/nest per language rules |

**Note:** this is a table of *access to type or member names*, not a table governing who has the right to become a subtype.

Example regular class:

```java
package demo.api;

public class Account {
    private long balance;

    public long balance() {
        return balance;
    }

    protected void validateChange(long amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("Negative amount");
        }
    }
}
```

Code outside the package can use `Account` because the class is `public` (assuming the module is accessible). It cannot read `balance` directly because that field is `private`. A valid subclass in another package can call `validateChange` under `protected` rules; however, `protected` does not allow calling that method on arbitrary `Account` instances from outside the package.

### 2.2. `public` is also affected by the Java Platform Module System

In projects using **named modules** (`module-info.java`), declaring a type `public` is not enough for other modules to use it. The package containing that type must also be exported by the module via `exports` (or another appropriate access mechanism).

```java
module example.api {
    exports demo.api;
}
```

Only modules depending on `example.api` can use `public` types in `demo.api` under module rules. The `exports` directive controls **API accessibility across module boundaries**; it does not replace `sealed` or automatically grant inheritance permission.

For applications running on the **classpath** (unnamed module), package rules and modifiers still apply; `module-info.java` is not required to learn basic `sealed` concepts.

## 3. Inheritance permission: `final`, `sealed`, `non-sealed`

Java 17 supports `sealed` on **classes** and **interfaces** as a standard language feature. Three common design options:

| Declaration | Meaning for creating subtypes |
|---|---|
| Regular class, neither `final` nor `sealed` | Can be inherited if the subclass has access and meets other Java rules |
| `final class` | No class may extend that class |
| `sealed class` or `sealed interface` | Only permitted types may directly `extends`/`implements` it |
| `non-sealed class` or `non-sealed interface` | Reopens subtype creation on that branch; valid only when directly extending/implementing a `sealed` type |

With `sealed`, the `permits` keyword lists **permitted direct subtypes**. Each direct subtype must explicitly state its next direction:

- **`final`**: closes the branch at that subclass. Applies to classes; interfaces cannot be declared `final`.
- **`sealed`**: continues restricting the branch's subtype set.
- **`non-sealed`**: opens the branch so subsequent subtypes can inherit/implement it under standard Java rules.

Record classes are implicitly `final`; therefore a record can directly implement a sealed interface without an extra branch-closing modifier. However, a record cannot extend an arbitrary domain class because records already extend `java.lang.Record`.

General example:

```text
Payment (public sealed interface)
├── CashPayment (final class)
├── CardPayment (sealed interface)
│   ├── CreditCard (final class)
│   └── DebitCard (final class)
└── ExtensionPayment (non-sealed interface)
    └── ExternalPayment (any class implementing ExtensionPayment)
```

`Payment`'s `permits` list needs only name the **three direct branches**. `CreditCard`, `DebitCard`, and `ExternalPayment` are not direct subtypes of `Payment`.

### Key takeaway

`sealed` **does not mean** a class is automatically `private`, `final`, or `abstract`. A normal `sealed` class can still be instantiated directly if it is not `abstract` and has an accessible constructor. Conversely, an `abstract` class cannot be instantiated directly, yet can remain open to inheritance if it is not `sealed` or otherwise restricted.

## 4. Core example: `public` type with selectively permitted implementations

Suppose we publish an interface for application event types. The code below goes into **`Event.java`**:

```java
package demo.events;

public sealed interface Event permits Started, Finished {
    String message();

    static Event started() {
        return new Started();
    }

    static Event finished() {
        return new Finished();
    }
}

final class Started implements Event {
    @Override
    public String message() {
        return "Started";
    }
}

final class Finished implements Event {
    @Override
    public String message() {
        return "Finished";
    }
}
```

In this example:

1. `Event` is `public`: code in other packages can declare variables, parameters, and return types of `Event` when the package is accessible.
2. `Event` is `sealed`: only `Started` and `Finished` may **directly** implement `Event`.
3. `Started` and `Finished` are *package-private*: code outside `demo.events` cannot directly access the names of these two classes, even though they are in `permits`.
4. Both subclasses are `final`, satisfying the `sealed` branch declaration requirement and preventing further extension from them.
5. The two factory methods `started()` and `finished()` on `Event` provide instances to external callers without exposing the implementation classes publicly.

In a file **`App.java`** in another package:

```java
package demo.client;

import demo.events.Event;

public class App {
    public static void main(String[] args) {
        Event event = Event.started();     // Valid
        System.out.println(event.message());

        // new Started();                  // Cannot access package-private class
    }
}
```

The output is `Started`. This example clarifies the two independent control layers: API consumers can **receive and process an `Event`**, yet cannot arbitrarily **add their own direct implementation types** to the set closed by the author.

### What happens if a class is `public` but not in `permits`?

Even if created in the **same package**:

```java
package demo.events;

// Compilation error illustration: Unknown is not in Event's permits list.
public final class Unknown implements Event {
    @Override
    public String message() {
        return "Unknown";
    }
}
```

`Unknown` can access `Event`, yet is **not permitted to directly implement** this interface. Being in the same package or declaring `public` does not alter `permits`.

To grant permission, the author of `Event` must update the sealed hierarchy design itself (while obeying package/module rules). No access modifier on `Unknown` can bypass `permits`.

## 5. Type visibility does not grant inheritance permission

Review the following scenario table, assuming no constructor, module, or contextual barriers other than those noted:

| Supertype | Can code outside the package use the type name? | Can it arbitrarily create direct subclasses/implementations? |
|---|---|---|
| Regular `public interface Service` | Yes, if the package is accessible | Normally yes |
| `public sealed interface Service permits A, B` | Yes, if the package is accessible | **No**; only `A`, `B` directly |
| Package-private `interface Service` | No | Only from where the interface is accessible, if not otherwise restricted |
| `public final class Value` | Yes, if the package is accessible | **No**; `final` closes all branches |
| `public non-sealed interface Extension` directly extending a sealed interface | Yes, if the package is accessible | Normally yes; this branch is open |

**Bottom line:** `public` answers "who can use the type?", whereas `sealed` and `permits` answer "who can be a direct subtype?". Type visibility is only a **necessary condition** for creating a subclass; constructors, class/interface kinds, module rules, and other language conditions must also be valid.

### Further distinguishing `protected` from `permits`

`protected` is an access modifier for members and nested types. It is **not** a way to list valid subclasses. A `protected` constructor may allow a subclass to call the superclass constructor, yet the subclass is still rejected if it is not in a `sealed` parent's `permits` list.

```java
package demo.documents;

public sealed abstract class Document permits PdfDocument {
    protected Document() {}
}

final class PdfDocument extends Document {
    PdfDocument() {
        super(); // Can access the protected constructor.
    }
}
```

Here there are **two distinct conditions**:

- `PdfDocument` is permitted to `extends Document` because `Document` lists it in `permits`.
- `PdfDocument`'s constructor can call `super()` due to `protected` accessibility rules.

If another unlisted class tries to `extends Document`, the `protected` constructor does not help it bypass `sealed` control.

## 6. Package and module boundaries for permitted types

Permitted subtypes cannot be placed arbitrarily anywhere. Java 17 requires **permitted direct subclasses/subinterfaces** to reside within a scope tied to the sealed type:

| Where the sealed type is declared | Valid location for permitted direct subtypes |
|---|---|
| In a **named module** | Same **named module** as the sealed type; may be in a different package if parent access is valid |
| In an **unnamed module** (e.g., standard classpath) | Same **package** as the sealed type |

This is a **constraint specific to `sealed`**, not a rule that every regular `public` class faces.

### 6.1. Classpath application: same package

```java
// demo/shapes/Shape.java
package demo.shapes;

public sealed interface Shape permits Circle, Rectangle {}
```

```java
// demo/shapes/Circle.java
package demo.shapes;

public final class Circle implements Shape {}
```

```java
// demo/shapes/Rectangle.java
package demo.shapes;

public final class Rectangle implements Shape {}
```

The classes are in the same package, listed in `permits`, and have valid branch modifiers.

A class in `demo.external` cannot directly implement `Shape` even though `Shape` is `public`. Modifying `permits` to name a class in another package while still running in an **unnamed module** still violates the same-package constraint.

### 6.2. Named module: same module, optionally different packages

In a named module, for example:

```text
src/main/java/
├── module-info.java
├── demo/api/Operation.java
└── demo/internal/DefaultOperation.java
```

`module-info.java`:

```java
module demo.module {
    exports demo.api;
}
```

`demo/api/Operation.java`:

```java
package demo.api;

public sealed interface Operation permits demo.internal.DefaultOperation {
    void run();
}
```

`demo/internal/DefaultOperation.java`:

```java
package demo.internal;

public final class DefaultOperation implements demo.api.Operation {
    @Override
    public void run() {
        System.out.println("Running");
    }
}
```

The two types are in different packages yet in the **same named module**. `Operation` is `public`, so `DefaultOperation` can access it inside the module. A client module can access `demo.api.Operation` via `exports demo.api`, yet cannot register a new direct implementation class: that module's class lies **outside the module declaring `Operation`**.

Subtle detail: `DefaultOperation` is declared `public` so it can participate in `implements` across packages, while package `demo.internal` is not `exports`-ed; code in other modules normally cannot refer to `demo.internal.DefaultOperation` directly. **`public` on a type**, **`exports` on a package**, and **`permits` on a sealed type** are three separate control layers.

If a project does not yet use named modules, you only need to understand and follow the **same-package** rule; there is no need to migrate the entire project to the module system just to use `sealed`.

## 7. `permits` governs only the direct inheritance tier

Suppose an API needs to let third parties write plugin types while keeping the API core closed:

```java
package demo.payments;

public sealed interface Payment permits CashPayment, ExtensionPayment {}

final class CashPayment implements Payment {}

public non-sealed interface ExtensionPayment extends Payment {}
```

The snippet above illustrates the idea; in Java, each `public` top-level type must live in a source file matching its name. Therefore, in real source code, split `Payment` and `ExtensionPayment` into `Payment.java` and `ExtensionPayment.java` (and place `CashPayment` in a valid file or alongside one `public` type).

A class in another package can implement **`ExtensionPayment`**, provided the type is accessible:

```java
package demo.plugins;

import demo.payments.ExtensionPayment;

public final class MobilePayment implements ExtensionPayment {}
```

`MobilePayment` is not declared in `Payment.permits`, because it **does not directly implement `Payment`**; the directly permitted branch is `ExtensionPayment`, which was reopened with `non-sealed`. `MobilePayment` indirectly being a `Payment` is completely valid.

This demonstrates how a sealed hierarchy can lock down the core while intentionally providing an "extension point" on a designated branch. If no further inheritance should be allowed at all, replace the branch with a `final class` (for classes) or another `sealed` interface with an explicit child list.

## 8. Common misconceptions

### Misconception 1: "`public` means anyone can `extends`"

**False.** `public` describes accessibility. A `public final class` cannot be extended; a `public sealed class` permits only types in `permits`; a `public sealed interface` cannot be implemented directly at will.

### Misconception 2: "Just put the name in `permits` and you're done"

**Insufficient.** The subtype must actually `extends`/`implements` **directly**, must be able to access the supertype, must reside in the same package/module per sealed rules, and must carry a branch-status modifier (`final`, `sealed`, or `non-sealed`, with syntax exceptions where applicable for types like records).

### Misconception 3: "`private` or `protected` is equivalent to `sealed`"

**False.** Access modifiers govern whether members can be called, seen, or inherited in a given context; they do not establish a **named list of permitted subtypes**. Even when a constructor is callable, `sealed` can still block declaring an unpermitted subclass.

### Misconception 4: "If a subclass is permitted, every grandchild class must be in `permits`"

**False.** `permits` lists only **direct** subtypes. If a branch is declared `non-sealed`, indirect subtypes of the sealed root do not need to appear in the root's list.

### Misconception 5: "`sealed` protects all object state"

**False.** `sealed` controls the **inheritance tree**; it does not automatically make fields `private`, guarantee immutability, or replace validation, authorization, or input security. A sealed class can still hold mutable state if designed that way.

### Misconception 6: "Pattern matching for `switch` works by default in Java 17"

**Not true for standard Java 17 programs.** In Java 17, pattern matching for `switch` is still a preview feature; do not include it in examples targeting standard Java 17 without clearly stating the preview flag requirement. Sealed types themselves are a **final** feature in Java 17. When dispatching on objects in Java 17 examples, you can use pattern matching for `instanceof` (standard since Java 16).

## 9. Practice exercises

### Exercise 1: Classify errors by rule category

Assume two types in the same package:

```java
public sealed interface Message permits TextMessage {}

final class TextMessage implements Message {}
```

Consider these cases:

1. A class in another package declares a variable `Message msg;`.
2. A class in another package tries `new TextMessage()`.
3. A class in the same package declares `final class ImageMessage implements Message {}`.
4. A method `public static Message text()` inside `Message` returns `new TextMessage()`.

**Solutions:**

1. Allowed, if `Message` is accessible from that package; declaring a variable of type `Message` creates no new subtype.
2. Not allowed, because `TextMessage` has package-private default access; this is an **accessibility** error.
3. Not allowed, because `ImageMessage` is not in `permits`; this is an **inheritance permission** error, despite being in the same package.
4. Allowed, because the factory is located where `TextMessage` is accessible and returns the public `Message` type.

### Exercise 2: Designing a closed API with an extension point

Requirement: a public `Response` type with strictly two direct groups: `Success` managed by the library, and `CustomResponse` for extensions. Users may implement types under the extension branch without modifying core code.

One approach:

```java
// Response.java
package demo.response;
public sealed interface Response permits Success, CustomResponse {}
```

```java
// Success.java
package demo.response;
public final class Success implements Response {}
```

```java
// CustomResponse.java
package demo.response;
public non-sealed interface CustomResponse extends Response {}
```

```java
// Outside package demo.response, with access to CustomResponse
package client;
import demo.response.CustomResponse;
public final class PartnerResponse implements CustomResponse {}
```

Explanation: `Response` lets everyone **use** the root type; the two branches `Success` and `CustomResponse` are **directly permitted**; `Success` is closed, `CustomResponse` is open. `PartnerResponse` implements `CustomResponse`, becoming an indirect `Response`.

### Exercise 3: Reading declarations before deciding to extend

When encountering a sealed API, answer in order:

1. Is the supertype accessible from the package/module where code is being written?
2. Do you want to `extends`/`implements` **directly** or through a `non-sealed` branch?
3. If directly, is the new type's name in `permits` and in the right package/module?
4. Is the subtype a class, interface, or record; is the branch modifier valid?
5. If it is a class, is the superclass constructor callable?

Answering in sequence helps separate errors caused by **invisible APIs**, errors caused by **disallowed inheritance**, and errors caused by **other language conditions**.

## 10. When should `sealed` be used?

Sealed types fit when a business domain has **a controlled set of core branches**: success/failure processing outcomes, transaction states, AST expressions, or clearly defined message groups. They help readers understand which direct implementations a library recognizes; authors can publish the root API while still controlling how the type structure extends.

`sealed` does not need to be used on every interface. If the real goal is letting users create new implementations in any project, a regular interface or a deliberately public `non-sealed` branch is usually more suitable. And if you need to prevent all subclasses of an implementation, use `final class`.

Consider library evolution: adding a branch to `permits`, changing a branch from `final` to `non-sealed`, or altering public APIs can affect dependent code. Choose a sealed hierarchy based on the domain's long-term contract rather than just new syntax.

## 11. Takeaways and references

- **Access modifiers**: who can access a type, member, or constructor?
- **Module `exports`**: which packages are exposed to other modules?
- **`sealed` + `permits`**: which types are permitted to inherit/implement **directly**?
- **`final` / `sealed` / `non-sealed` on subtypes**: will that branch close, remain restricted, or open up?
- **Java 17 boundary**: the sealed rules covered here are standard features in Java 17; no preview features are required.

To read the original language rules, see [Java Language Specification 17 — Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html), [Java Language Specification 17 — Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html), [Java Language Specification 17 — Modules and Packages](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html), and [OpenJDK JEP 409: Sealed Classes](https://openjdk.org/jeps/409).
