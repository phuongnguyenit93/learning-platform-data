# Inheritance Chains Across Multiple Abstract Classes in Java

When one abstract class extends another abstract class, Java forms a **multilevel inheritance chain** (*multilevel inheritance*). Each level can inherit state, implemented behavior, and abstract methods that still remain to be completed. The final level only becomes a concrete class once it fulfills all inherited abstract obligations.

This article focuses on the **abstract class → abstract class → concrete class** chain, how Java determines which methods must be implemented, initialization order, polymorphism, and how to design maintainable chains.

## 1. Core Model and Rules

```java
abstract class A {
    abstract void stepA();
}

abstract class B extends A {
    abstract void stepB();
}

class C extends B {
    @Override
    void stepA() {
        System.out.println("A");
    }

    @Override
    void stepB() {
        System.out.println("B");
    }
}
```

Relationship diagram:

```text
A (abstract): stepA() not yet implemented
    ↑ extends
B (abstract): inherits stepA(), adds stepB()
    ↑ extends
C (concrete): implements stepA() and stepB()
```

Reading the diagram from bottom to top: `C extends B`, `B extends A`, so `C` is also an `A` under the *is-a* relationship. Java allows multiple **levels** of inheritance, but each class can only `extends` **one direct superclass**; there is no multiple class inheritance such as `class C extends A, B`.

Key points to remember:

- An `abstract` class can inherit from an `abstract` class or a regular class; its subclass can also continue to be `abstract`.
- An abstract class is **not required** to immediately implement all inherited abstract methods. It can implement some of them, add new obligations, or add nothing.
- A class **not declared `abstract`** must provide valid implementations for **every** remaining abstract method across the entire chain. Implementations can be inherited from an intermediate superclass; they do not necessarily have to be rewritten in the final class.
- You cannot use `new A()` or `new B()`, even though they have constructors. You can create `new C()` and hold the object with a variable of type `A`, `B`, or `C`.
- `abstract` designates a class that cannot be directly instantiated or a method without a body yet. A class can be `abstract` even if it **contains no abstract methods at all**.

**Rule for determining obligations:** start from the root superclass and track the abstract methods; each valid concrete implementation resolves an obligation, and each new `abstract` declaration adds an obligation. At the first concrete class, the list of unresolved obligations must be empty.

## 2. What Does Each Level Contribute?

| Level | Role | Can leave abstract methods? | Can be instantiated directly? |
| --- | --- | --- | --- |
| Abstract `A` | Defines the common contract, provides reusable data/behavior | Yes | No |
| Abstract `B extends A` | Specializes, provides partial implementations, adds to the contract | Yes | No |
| Concrete `C extends B` | Completes the remaining parts, produces usable objects | No | Yes |

An intermediate level is not just a name to lengthen the inheritance tree. It should group a meaningful set of common rules or behaviors for **multiple** concrete classes—for example, a digital resource extending a general resource and then being specialized into PDF, image, or audio.

A method that already has a body in `A` is inherited normally by `B` and `C`, unless validly overridden. A method that is still `abstract` in `A` can be implemented by `B`, in which case `C` does not need to implement it again.

## 3. Runnable Example: Three Levels and Incremental Implementation

Save the entire following program into a file named **`Main.java`**. The auxiliary classes are placed in the same file and only `Main` is `public` so that the example can compile standalone on Java 17+.

```java
abstract class Resource {
    private final String code;

    protected Resource(String code) {
        this.code = code;
        System.out.println("Resource -> " + code);
    }

    protected String code() {
        return code;
    }

    public abstract String kind();

    public abstract int units();

    public String description() {
        return kind() + ":" + code() + ":" + units();
    }
}

abstract class DigitalResource extends Resource {
    protected DigitalResource(String code) {
        super(code);
        System.out.println("DigitalResource");
    }

    @Override
    public String kind() {
        return "digital";
    }

    public abstract String format();

    public String fullDescription() {
        return description() + ":" + format();
    }
}

final class PdfResource extends DigitalResource {
    private final int pages;

    public PdfResource(String code, int pages) {
        super(code);
        this.pages = pages;
        System.out.println("PdfResource");
    }

    @Override
    public int units() {
        return pages;
    }

    @Override
    public String format() {
        return "PDF";
    }
}

public class Main {
    public static void main(String[] args) {
        DigitalResource digital = new PdfResource("R-07", 12);
        Resource general = digital;

        System.out.println(digital.fullDescription());
        System.out.println(general.description());
    }
}
```

Compile and run in the directory containing `Main.java`:

```bash
javac Main.java
java Main
```

Expected output:

```text
Resource -> R-07
DigitalResource
PdfResource
digital:R-07:12:PDF
digital:R-07:12
```

**Level-by-level analysis:**

1. `Resource` declares two obligations: `kind()` and `units()`. It also defines a constructor, the `code` field, and the concrete method `description()`. Inside `description()`, the calls to `kind()` and `units()` can resolve to implementations in subclasses.
2. `DigitalResource` remains `abstract`, but it already implements `kind()`. It inherits the unresolved `units()` obligation and adds the `format()` obligation. The `fullDescription()` method reuses `description()` from the root level.
3. `PdfResource` resolves `units()` and `format()`. Because `kind()` was already implemented by the middle level, it becomes a valid concrete class. Using `final` here is a design choice to prevent other classes from further extending `PdfResource`; it is not a requirement of the abstract chain.
4. The line `DigitalResource digital = new PdfResource(...)` demonstrates polymorphism: the **reference type** is `DigitalResource`, and the **actual object type** is `PdfResource`. The line `Resource general = digital` does not create an additional object; it only creates another reference to the same object.

Both description printouts use `DigitalResource`'s `kind()` and `PdfResource`'s `units()` through **dynamic dispatch**. Code at the `Resource` level does not need to know the name of the specific concrete class that will execute those methods.

## 4. How Are Abstract Methods "Passed Down" Through Levels?

Consider the chain of obligations from the example:

```text
Resource:
    kind()    -> abstract
    units()   -> abstract

DigitalResource:
    kind()    -> implemented
    units()   -> inherited abstract
    format()  -> new abstract

PdfResource:
    kind()    -> inherited implementation
    units()   -> implemented
    format()  -> implemented
```

Do not mistakenly assume that only `abstract` methods **written directly** in the immediate superclass need to be implemented. `PdfResource` is also bound by the `units()` obligation originating from `Resource`, even though `DigitalResource` does not redeclare that method.

If you remove `units()` from `PdfResource` while keeping `PdfResource` as a concrete class, the program **will not compile**: the class has not implemented the full abstract contract. The two valid fixes are either providing `units()` in `PdfResource` or keeping this class `abstract` so another subclass can complete it; the choice depends on the design intent.

An intermediate level can also implement **all** inherited abstract methods while still declaring itself `abstract`: this is valid, for example when you want to prevent direct instantiation or intend to add rules in subclasses. The `abstract` keyword on a class and the number of `abstract` methods do not have a one-to-one relationship.

## 5. Overriding and Re-abstracting Within the Chain

Overriding rules still apply at every level: signatures must be compatible, access privileges cannot be narrowed, and checked exceptions cannot be broadened contrary to the rules; `@Override` helps catch signature mismatches. A `final` method cannot be overridden, `private` methods do not create inheritance hooks, and `static` methods use hiding rather than dynamic dispatch. Concrete class responsibilities and the signature checklist are analyzed further in the article on completing implementations.

A notable case is that an intermediate class can **re-abstract** a method that already has a body in the superclass (provided that method is not `final`) to force concrete classes below to supply their own implementation:

```java
abstract class Base {
    String status() {
        return "DEFAULT";
    }
}

abstract class Specialized extends Base {
    @Override
    abstract String status();
}

final class Ready extends Specialized {
    @Override
    String status() {
        return "READY";
    }
}
```

The snippet only illustrates class declarations and has no `main`. `Ready` must implement `status()` because `Specialized` redeclared that method as `abstract`, even though `Base` previously had a body. Use this technique deliberately, as it makes the contract stricter.

## 6. Constructors Still Run Throughout the Chain

`abstract` does not forbid constructors. When creating `new PdfResource("R-07", 12)`, constructors execute in sequence from `Object` to `Resource`, `DigitalResource`, and then `PdfResource`; the stdout lines in the Section 3 example demonstrate this exact order. Each level must be able to invoke a suitable superclass constructor, explicitly with `super(...)` or via an implicit `super()` when an accessible no-argument constructor exists.

Initialization-trap examples are not repeated here: rules on initializer order and the risk of calling an overridden method when subclass fields are not yet ready belong to the dedicated article on constructors. In an inheritance chain, let constructors initialize state and perform polymorphic behavior after the object has been fully constructed.

## 7. Reference Types, Visible Methods, and Casting

Given an object declared as follows:

```java
PdfResource pdf = new PdfResource("R-08", 8);
DigitalResource digital = pdf;
Resource resource = pdf;
```

The lines above are an illustrative snippet in the context of the classes in Section 3. All three variables point to **one** `PdfResource` object, but the reference type determines which members the compiler allows to be called:

| Variable | Callable via declared type | Not directly callable |
| --- | --- | --- |
| `pdf` | `description()`, `fullDescription()`, `format()`, `units()` | — |
| `digital` | `description()`, `fullDescription()`, `format()`, `units()` | — |
| `resource` | `description()`, `kind()`, `units()` | `format()`, `fullDescription()` |

`resource.description()` still executes the overridden implementations on the `PdfResource`/`DigitalResource` object, even though `resource` cannot call `format()` directly. **Compile-time call permission** and **the implementation selected at runtime** are two different matters.

If you truly need an operation specific to the middle level, you can check the type before casting:

```java
if (resource instanceof DigitalResource digitalResource) {
    System.out.println(digitalResource.format());
}
```

This is the *pattern matching for instanceof* syntax supported in Java 17. In good design, prefer placing necessary common operations on the contract of the appropriate level instead of repeatedly using `instanceof`/casting.

## 8. Designing Sound Abstract Chains

A multilevel chain is useful when each level represents **a meaningful specialized concept**:

```text
Resource (all resources)
    └── DigitalResource (digital resources with a format)
            ├── PdfResource
            └── ImageResource
```

For example, `Resource` owns the identifier, `DigitalResource` knows the shared characteristics of digital resources, while `PdfResource` and `ImageResource` implement their own specific details. An intermediate level is worth having if multiple classes share its logic.

When designing, you should:

1. Define invariants and shared data in the root class; use `private` for state that needs protection, and expose `protected`/`public` methods only when genuinely needed.
2. Place abstract methods at the lowest level that can accurately express the **shared obligation**, avoiding forcing unrelated classes to implement meaningless behavior.
3. Implement shared logic once at the appropriate level; use `final` methods when you want to preserve algorithm invariants and prevent subclasses from overriding critical steps.
4. Ensure subclasses honor the superclass contract: anywhere `Resource` is expected must still work properly with `PdfResource`. Do not alter the meaning of `units()` across branches to the point that API users misunderstand it.
5. Avoid creating an `abstract` level merely to name a transitional step or to save a few lines of code. Every level adds dependency, making the inheritance tree harder to read and modify.
6. If object types only need to share a **capability** without a strict *is-a* relationship, consider an `interface`; if you only want to reuse a component, consider **composition**. Java still allows a class to `extends` one class and `implements` multiple interfaces.

A useful pattern is the **Template Method**: the abstract level implements a stable workflow and calls `protected abstract` steps for subclasses to complete. Avoid calling overridable workflows from constructors, and clearly define preconditions and postconditions for each step.

## 9. Common Errors and Misconceptions

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Final class reports an unimplemented abstract method | An obligation at a grandparent/ancestor level still exists | Review the entire chain; implement all required methods or keep the class declared `abstract` |
| Instantiating an intermediate abstract class with `new` fails | An `abstract` class cannot be instantiated directly | Instantiate a concrete class and hold the reference using the abstract type |
| `super()` constructor error | Superclass has no accessible no-argument constructor | Call an appropriate `super(args)` in the subclass constructor |
| Compilation error when overriding | Wrong signature, reduced access level, incompatible return type/`throws`, or colliding with a `final` method | Compare the exact declarations across all involved levels and use `@Override` |
| Calling a subclass-specific method via a superclass variable does not compile | The reference type does not declare that method | Lift shared behavior onto the superclass API, or check the type and cast when necessary |
| Subclass field unexpectedly has value `null`/`0` inside the superclass constructor | Superclass constructor calls an overridden method before subclass fields are initialized | Do not dispatch to overridden methods in constructors |
| Inheritance tree is too deep, with many pass-through classes adding no meaning | Mis-modeled responsibilities, overuse of inheritance | Reduce levels, extract capabilities into interfaces, or use composition components |

A few important boundaries: Java **does not** allow extending multiple classes directly; `abstract` does not mean every method is abstract; and `super` lets you access appropriate superclass behavior, but it cannot turn an `abstract` method without a body into something executable.

## 10. Knowledge Self-Check

**Exercise 1 — identifying obligations.** Suppose `A` declares `abstract void x()` and `abstract void y()`. `B extends A` (still `abstract`) only implements `x()` and adds `abstract void z()`. Which methods must the concrete class `C extends B` implement?

<details>
<summary>Answer and explanation</summary>

`C` must implement `y()` and `z()`. `x()` already has a body provided by `B`, so it is inherited by `C`. Unless `C` wants to change the behavior of `x()`, there is no need to override it again.
</details>

**Exercise 2 — polymorphism.** Using the program in Section 3, replace the declaration with `Resource value = new PdfResource("R-09", 5);`. Does `value.description()` use `Resource.kind()`? Can `value.fullDescription()` be called directly?

<details>
<summary>Answer and explanation</summary>

`Resource` only declares `kind()` as abstract; at runtime, `description()` invokes `DigitalResource`'s `kind()` and `PdfResource`'s `units()`. `value.fullDescription()` cannot be called directly because the declared type `Resource` does not have that method. It can be called through a `DigitalResource` reference or a valid cast.
</details>

**Exercise 3 — extension.** Create `abstract class DocumentResource extends DigitalResource` that adds the method `abstract String category()`. Then create `final class InvoicePdf extends DocumentResource` to complete `units()`, `format()`, and `category()`. Explain why `kind()` does not need to be rewritten. Print the constructor order yourself and verify `description()` when holding the object with a `Resource` variable.

**Checklist before finalizing an inheritance chain:** every level has a clear responsibility; `abstract` obligations are tracked across the entire chain; the final class fulfills the entire contract; constructors invoke `super(...)` validly; no overridden behavior is called inside constructors; and the API preserves proper polymorphism and overriding rules.
