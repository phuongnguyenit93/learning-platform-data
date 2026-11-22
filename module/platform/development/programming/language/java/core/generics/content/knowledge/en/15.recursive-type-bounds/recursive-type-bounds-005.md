# Self-Referential Pattern in Builders with Inheritance — Java Generics

## 1. The Problem: Inheritance Loses the Concrete Type When Chaining Calls

A **Builder** is an object that collects configuration options and then creates a complete object via `build()`. A *fluent* API typically allows chained calls:

```java
new EmailBuilder()
        .text("Hello")
        .to("team@example.com")
        .build();
```

If a child builder inherits methods from a parent builder, the following naive design fails:

```java
class MessageBuilder {
    MessageBuilder text(String value) {
        return this;
    }
}

class EmailBuilder extends MessageBuilder {
    EmailBuilder to(String address) {
        return this;
    }
}

// Compile error example, not a standalone program:
new EmailBuilder().text("Hello").to("team@example.com");
```

Although the **actual runtime object** is still `EmailBuilder`, the static type of the expression after `.text("Hello")` is `MessageBuilder`, because that is the return type declared in the parent class. The `MessageBuilder` class does not declare `to(...)`; the compiler cannot call that method.

Swapping the order to `.to(...).text(...)` might compile in this case, yet it does not solve the problem: after calling a method from the parent class, the static type narrows to the parent builder type. With multiple levels of inheritance, this causes errors in longer call chains.

**The goal of the self-referential pattern** is to make setters defined in the parent class still return **the concrete child builder type**, so child setters can be chained afterward in any valid order.

## 2. Recursive Bounds and the Meaning of the `SELF` Type

The classic solution uses a self-referential generic type parameter (*self-referential generic type*, commonly called **F-bounded polymorphism** or an emulation of the *Curiously Recurring Template Pattern — CRTP*):

```java
abstract class BaseBuilder<SELF extends BaseBuilder<SELF>> {
    protected abstract SELF self();

    public SELF label(String value) {
        // Store value into builder state...
        return self();
    }
}

final class ConcreteBuilder extends BaseBuilder<ConcreteBuilder> {
    @Override
    protected ConcreteBuilder self() {
        return this;
    }
}
```

The key part is:

```java
SELF extends BaseBuilder<SELF>
```

Read it step by step:

1. `BaseBuilder` has a type parameter named `SELF`.
2. `SELF` is bounded to be a subtype of `BaseBuilder<SELF>`; the bound on the right mentions `SELF` itself again, so it is called a **recursive bound**.
3. The concrete class declares `extends BaseBuilder<ConcreteBuilder>`, making `SELF` correspond to `ConcreteBuilder` in inherited methods.
4. Since `label(...)` returns `SELF`, when called on `ConcreteBuilder`, the compile-time return type is `ConcreteBuilder`.

In Java, the identifier `SELF` is **not** a special keyword, nor a built-in type. You can use `B`, `T`, or `ThisBuilder`; what matters is the recursive relationship in the generic declaration.

Example:

```java
ConcreteBuilder b = new ConcreteBuilder().label("x");
```

The right-hand expression has type `ConcreteBuilder` right at compile time.

### Why Is `self()` Needed?

The parent class only knows `this` has static type `BaseBuilder<SELF>`. You cannot directly assign `this` to a variable of type `SELF`:

```java
// Inside BaseBuilder<SELF>:
public SELF label(String value) {
    return this; // Error: this has type BaseBuilder<SELF>, not guaranteed to be SELF
}
```

Some examples use:

```java
@SuppressWarnings("unchecked")
protected SELF self() {
    return (SELF) this;
}
```

This snippet contains an **unchecked cast**: the API author must personally guarantee that the object actually conforms to `SELF`. A mismatched self-referential type can cause a `ClassCastException` when a client receives the return value. A safer, easier-to-verify approach in a multi-layer builder hierarchy is to make `self()` `abstract` and let leaf builders implement it with `return this` **without casting**.

The bound `SELF extends BaseBuilder<SELF>` helps restrict incorrect type argument choices, yet it **does not strictly prove** that `SELF` is always the runtime class of `this`. Therefore, you still need to design a consistent hierarchy and verify concrete classes.

## 3. Multi-Level Inheritance: Keeping `SELF` Intact Throughout

Suppose the product model consists of:

```text
Message
  └── Email
       └── UrgentEmail
```

Each product has a builder. The root builder provides `text(...)`; `Email`'s builder adds `to(...)`; `UrgentEmail`'s builder adds `priority(...)`.

We want the following expression to be **valid**:

```java
new UrgentEmail.Builder()
        .priority(2)
        .text("Alert")
        .to("admin@example.com")
        .build();
```

The key at the intermediate level is **passing the `B` parameter unchanged down to the parent class**:

```java
abstract static class Builder<B extends Builder<B>>
        extends Message.Builder<B> {
    // ...
}
```

In this context, `Builder` is `Email.Builder`; the constraint `B extends Email.Builder<B>` also makes `B` compatible with the parent class's bound `B extends Message.Builder<B>`. When the leaf builder is `UrgentEmail.Builder`, `B` is bound to that leaf class across **both levels**, so both `text(...)` and `to(...)` have return type `UrgentEmail.Builder`.

A common mistake is having an intermediate class decide to return its own fixed intermediate builder type, losing fluent capability for the next level. If the hierarchy may still be subclassed, keep the intermediate builder **generic and abstract**, fixing the self-referential type only in the final concrete builder.

## 4. Complete, Compilable, Runnable Java 17 Example

Create the file **`BuilderInheritanceDemo.java`**:

```java
import java.util.Objects;

public class BuilderInheritanceDemo {
    static class Message {
        protected final String text;

        protected Message(Builder<?> builder) {
            this.text = Objects.requireNonNull(builder.text, "text");
        }

        public String summary() {
            return text;
        }

        static abstract class Builder<B extends Builder<B>> {
            private String text;

            public B text(String value) {
                this.text = Objects.requireNonNull(value, "text");
                return self();
            }

            protected abstract B self();

            public Message build() {
                return new Message(this);
            }
        }
    }

    static class Email extends Message {
        protected final String to;

        protected Email(Builder<?> builder) {
            super(builder);
            this.to = Objects.requireNonNull(builder.to, "to");
        }

        @Override
        public String summary() {
            return text + " -> " + to;
        }

        static abstract class Builder<B extends Builder<B>>
                extends Message.Builder<B> {
            private String to;

            public B to(String value) {
                this.to = Objects.requireNonNull(value, "to");
                return self();
            }

            @Override
            public Email build() {
                return new Email(this);
            }
        }
    }

    static final class UrgentEmail extends Email {
        private final int priority;

        private UrgentEmail(Builder builder) {
            super(builder);
            this.priority = builder.priority;
        }

        @Override
        public String summary() {
            return super.summary() + " [P" + priority + "]";
        }

        static final class Builder extends Email.Builder<Builder> {
            private int priority = 1;

            public Builder priority(int value) {
                if (value < 1) {
                    throw new IllegalArgumentException("priority must be positive");
                }
                this.priority = value;
                return this;
            }

            @Override
            protected Builder self() {
                return this;
            }

            @Override
            public UrgentEmail build() {
                return new UrgentEmail(this);
            }
        }
    }

    static final class PlainMessageBuilder
            extends Message.Builder<PlainMessageBuilder> {
        @Override
        protected PlainMessageBuilder self() {
            return this;
        }
    }

    static final class StandardEmailBuilder
            extends Email.Builder<StandardEmailBuilder> {
        @Override
        protected StandardEmailBuilder self() {
            return this;
        }
    }

    public static void main(String[] args) {
        Message plain = new PlainMessageBuilder()
                .text("Hi").build();

        Email standard = new StandardEmailBuilder()
                .text("Hello").to("team@example.com").build();

        UrgentEmail urgent = new UrgentEmail.Builder()
                .text("Outage").to("ops@example.com")
                .priority(1).build();

        UrgentEmail reverse = new UrgentEmail.Builder()
                .priority(2).to("admin@example.com")
                .text("Alert").build();

        System.out.println(plain.summary());
        System.out.println(standard.summary());
        System.out.println(urgent.summary());
        System.out.println(reverse.summary());
    }
}
```

Run from the directory containing the file:

```bash
javac --release 17 BuilderInheritanceDemo.java
java BuilderInheritanceDemo
```

Exact output:

```text
Hi
Hello -> team@example.com
Outage -> ops@example.com [P1]
Alert -> admin@example.com [P2]
```

The example uses static nested classes to package all source into a single file; in real applications, each product class can reside in its own file with appropriate visibility. The `main` method demonstrates both orders: calling parent setters before child setters and vice versa.

### 4.1. Reading the Return Type of Each Call

Given:

```java
UrgentEmail urgent = new UrgentEmail.Builder()
        .text("Outage")
        .to("ops@example.com")
        .priority(1)
        .build();
```

The compiler views the types as follows:

| Expression | Static type |
| --- | --- |
| `new UrgentEmail.Builder()` | `UrgentEmail.Builder` |
| `.text("Outage")` | `UrgentEmail.Builder` |
| `.to("ops@example.com")` | `UrgentEmail.Builder` |
| `.priority(1)` | `UrgentEmail.Builder` |
| `.build()` | `UrgentEmail` |

Because `UrgentEmail.Builder extends Email.Builder<UrgentEmail.Builder>` and the `Email.Builder<B> extends Message.Builder<B>` layer forwards `B`, both the `text` setter from the grandparent and the `to` setter from the parent return the same type `UrgentEmail.Builder`. The `build()` method in the leaf class overrides with the covariant return type `UrgentEmail`, allowing direct assignment without casting.

### 4.2. Why Does the Constructor Take `Builder<?>`?

In the example:

```java
protected Email(Builder<?> builder) {
    super(builder);
    this.to = Objects.requireNonNull(builder.to, "to");
}
```

`Email` only needs to **read shared state** from any `Email.Builder` instance, without needing to know the concrete `B` parameter. Hence `Builder<?>` sufficiently expresses the intent. In `Message`, the corresponding constructor takes `Message.Builder<?>`; every `Email.Builder<B>` inherits from `Message.Builder<B>`, so the argument passed to `super(builder)` is valid.

The `?` on the constructor does not break type inference for the fluent chain: it appears only at the **state-reading site during build**, and does not alter the return types of setters.

### 4.3. Why Is `self()` Implemented Only in Leaf Builders?

`Message.Builder<B>` and `Email.Builder<B>` are `abstract`; they do not try to return a single concrete builder type for all descendants. The two concrete classes `PlainMessageBuilder`, `StandardEmailBuilder`, and the nested builder inside `UrgentEmail` declare their own generic argument and `return this`.

With this pattern, each concrete builder needs a very short `self()` implementation, and in return all inherited setters return the exact right type. This is especially beneficial when the number of shared properties exceeds the number of properties specific to each subclass.

## 5. Easy Confusions Between Generics, Overriding, and Constructors

### 5.1. `build()` and `self()` Do Two Different Jobs

- `self()` returns **the builder** in order to continue configuring properties.
- `build()` returns **the constructed product**.

The following are two different return types serving different purposes:

```java
@Override
protected UrgentEmail.Builder self() {
    return this;
}

@Override
public UrgentEmail build() {
    return new UrgentEmail(this);
}
```

Java allows `UrgentEmail build()` to override `Email build()` because `UrgentEmail extends Email`: that is a **covariant return type**. This mechanism is independent of `B`'s recursive bound.

### 5.2. Do Not Drop the Type Parameter in Intermediate Classes

Writing a raw type:

```java
// Illustrates an anti-pattern to avoid:
abstract static class Builder<B extends Builder<B>>
        extends Message.Builder {
}
```

loses the bound that needs to be forwarded to `Message.Builder`, produces raw-type warnings, and prevents inherited signatures from preserving `B` accurately. In a system requiring strong typing, keep:

```java
abstract static class Builder<B extends Builder<B>>
        extends Message.Builder<B> {
}
```

### 5.3. Do Not Lock a Parent Builder to a Concrete Type Too Early

If `Email.Builder` were a concrete class returning `Email.Builder` directly from `to(...)`, `UrgentEmail`'s builder would lose the ability to call `.priority(...)` immediately after `.to(...)`. The intermediate builder needs parameter `B`, while only the leaf builder binds `B = UrgentEmail.Builder`.

### 5.4. `return this` Does Not Automatically Have Type `B`

Calling in a generic class:

```java
public B to(String value) {
    // ...
    return self(); // Correct: abstract method implemented by leaf builders
}
```

differs from `return this;` in the same class: `this` is only known to be `Email.Builder<B>`, not guaranteed to be `B`. Avoid casting `(B) this` to paper over the gap without proof of the runtime relationship.

### 5.5. Builder Names and Visibility

In the example, multiple classes are named `Builder` because they are nested under `Message`, `Email`, and `UrgentEmail`. They are **distinct classes**, and must be qualified like `Email.Builder<B>` when declaring inheritance. Making builder fields `private` helps keep state encapsulated; an enclosing class's constructor can access private fields of its corresponding nested class under Java's access rules.

When splitting them into top-level classes in separate files, you must redesign field visibility or provide suitable accessors; private access of a nested class does not automatically extend to classes outside the nesting relationship.

## 6. Design Sequence for a Builder Hierarchy

A reliable workflow is designing from the product contract to the builder:

1. **Sketch the product class tree** and identify shared vs. specific properties. If two product types do not genuinely have an `is-a` relationship, consider composition.
2. In the root builder, declare `abstract Builder<B extends Builder<B>>`, have each shared setter return `B`, and return via `self()`.
3. In intermediate builders that still allow inheritance, declare `abstract Builder<B extends Builder<B>> extends Parent.Builder<B>`; added setters also return `B` via `self()`.
4. In the leaf builder, bind the leaf class itself to the generic parameter: `extends Parent.Builder<ConcreteBuilder>`, and implement `self() { return this; }`.
5. If the leaf product class is a narrower subtype than the parent product, override `build()` with the corresponding return type.
6. Compile setter chains in **multiple orders** and inspect the built product values, rather than testing only child-before-parent setter order.

An example of a useful type check:

```java
// Excerpt from the runnable example above:
UrgentEmail.Builder b = new UrgentEmail.Builder()
        .text("A")
        .priority(3)
        .to("a@example.com");
```

If that line fails to compile and forces changing `UrgentEmail.Builder b` to `Email.Builder<?>`, the fluent contract is still failing to preserve the concrete type throughout.

## 7. Limitations and Trade-Offs to Understand Clearly

**A recursive bound does not mean Java has a true "self type".** F-bound syntax mainly creates a relationship between types during static checking. It does not force every subclass to pass itself as `B` in all possible constructs you can write, especially with non-`final` hierarchies or intentional casts. Therefore:

- Allow **intermediate builders** to stay extensible via generics, but usually mark **leaf builders** `final` if no further subclasses are planned.
- Write concrete `self()` implementations returning `this` only when the object actually has the declared type.
- Avoid raw types, unchecked casts, or returning a different builder instance in `self()`.
- Do not infer that a `B` type with an F-bound guarantees every runtime invariant about identity or state.

**Builders usually hold mutable state.** Fluent chaining updates the same instance. If a builder is saved and reused, subsequent products may carry configuration from earlier uses. Do not share mutable builders across threads without an explicit synchronization policy. In the example, `Message`, `Email`, and `UrgentEmail` keep their fields `final`, and constructors copy values from the builder; mutating the builder afterward does not change those fields on already-created objects. For lists, maps, or other mutable objects, defensive copies are needed if you want immutable products.

**Data validation is a separate responsibility.** The generic pattern only solves the static typing of the fluent API. It does not guarantee `text` or `to` was set; the example calls `Objects.requireNonNull` in constructors to catch missing values and checks `priority > 0` in the setter. An application can use `build()` to validate whole-object invariants and provide clearer error messages.

**Weigh complexity.** For a small hierarchy, covariant overrides for a few setters in the child builder may suffice. F-bounds fit better when there are many shared setters, multiple child builders, or multiple inheritance levels. If the model does not require product subclasses, a simple non-generic builder is usually easier to read and maintain.

## 8. Compilation Errors and Debugging

| Symptom | Common cause | How to check/fix |
| --- | --- | --- |
| `cannot find symbol` when calling child setter after parent setter | Parent setter returns `ParentBuilder` | Have parent setter return `B`, and have child builder pass `B` properly via F-bound. |
| `incompatible types: Parent.Builder<B> cannot be converted to B` | Returning `this` inside generic builder | Use `protected abstract B self()` implemented in leaf builders. |
| `type argument ... is not within bounds` | Wrong self-referential argument or wrong builder level | Check `B extends Builder<B>` and the inheritance path `extends Parent.Builder<B>`. |
| `name clash` or unable to override `build()` | Incompatible method signature/return type | Verify the exact method and covariant return rules; do not arbitrarily alter only the product type's generics. |
| `ClassCastException` after unchecked cast | `self()` casts to wrong runtime type | Remove cast; implement concrete `self()` returning `this`; audit non-`final` classes. |
| Null data or invalid state at `build()` | Missing invariant checks | Validate required fields, value ranges, and copy mutable state when necessary. |

If `javac` diagnostics are long, locate the method called **right before the type is lost** in the chain. You can split the expression:

```java
UrgentEmail.Builder builder = new UrgentEmail.Builder();
UrgentEmail.Builder afterText = builder.text("Alert");
UrgentEmail.Builder afterTo = afterText.to("ops@example.com");
UrgentEmail result = afterTo.priority(2).build();
```

This line-by-line style forces the compiler to check each expected type, making it very helpful for pinpointing which generic layer failed to propagate `B`.

## 9. Practice Exercises

**Exercise 1 — Spot the bug.** Why does the following fail to guarantee calling `.childOption()` after `.common()`?

```java
class ParentBuilder {
    ParentBuilder common() {
        return this;
    }
}
class ChildBuilder extends ParentBuilder {
    ChildBuilder childOption() {
        return this;
    }
}
```

<details>
<summary>Answer</summary>

Because `common()` is declared to return `ParentBuilder`; the static type after the call does not have `childOption()`. Make `ParentBuilder` generic as `ParentBuilder<B extends ParentBuilder<B>>` with `common()` returning `B` via `self()`, and have the child builder pass `ChildBuilder` as the self-referential argument.

</details>

**Exercise 2 — Trace the type.** In the runnable example, what is the static type after `new UrgentEmail.Builder().text("X").to("y")`? Which method needs to be declared `abstract` so shared setters do not have to cast?

<details>
<summary>Answer</summary>

The type is `UrgentEmail.Builder`. `Message.Builder<B>` declares `protected abstract B self()`; leaf builders implement `self()` with `return this`. `Email.Builder<B>` continues inheriting this contract without locking `B` to a fixed intermediate class.

</details>

**Exercise 3 — Extend.** Add `final class ScheduledEmail extends Email` with leaf builder `ScheduledEmail.Builder`, a `scheduledAt` property, and a setter returning the child builder type. Do you need to change `Email.Builder`'s signature?

<details>
<summary>Guidance</summary>

Keep `Email.Builder<B extends Email.Builder<B>> extends Message.Builder<B>` as is. The new builder declares `extends Email.Builder<ScheduledEmail.Builder>` (or `extends Email.Builder<Builder>` when `Builder` is nested), adds the `scheduledAt(...)` setter, implements `self()`, and overrides `build()` to return `ScheduledEmail`. The product constructor accepts that builder and delegates via `super(builder)` to handle shared properties.

</details>

## 10. Key Takeaways

For builders with inheritance, the key is **preserving the leaf builder type across every layer**: the parent declares setters returning `B`, intermediate layers forward `B` down to the parent, and the leaf class chooses itself as `B`. `self()` lets setters return the exact builder without unchecked casts; `build()` is overridden to produce the right product type.

This pattern solves **the static typing of a fluent API**. Correctness regarding validation, mutable state, product immutability, and the choice to use inheritance must still be designed and tested separately.
