# Constructors and Access Scope Selection in Abstract Classes (Java)

## 1. Why Do Abstract Classes Still Have Constructors?

In Java, a class declared `abstract` cannot be instantiated directly with `new`, yet it **still has constructors**. An abstract class constructor performs the shared initialization for all objects of concrete subclasses.

For example, every type of job might require a non-empty identifier. Instead of having each subclass repeat checking and storing the identifier, the abstract class receives the identifier through its constructor, validates it, and assigns it to a shared field.

Distinguish between three concepts:

- **Cannot instantiate an abstract class directly:** `new AbstractJob(...)` is a compilation error.
- **The abstract class constructor still runs:** when `new ExportJob(...)` is called, the `AbstractJob(...)` constructor is invoked in the initialization chain before the `ExportJob(...)` constructor completes.
- **Constructors are not inherited:** a subclass must declare its own constructor if it needs to pass arguments to the superclass, and it can call the superclass constructor using `super(...)`.

A constructor **has no return type**, not even `void`; its name must match the class name; and it cannot be declared `abstract`, `static`, or `final`. An abstract class can have multiple constructors (constructor overloading) just like a regular class.

## 2. Runnable Example: `protected` Constructor and Subclass in a Different Package

The Java 17+ example below shows an abstract superclass holding shared data, a subclass in another package calling `super(jobId)`, and external code instantiating the subclass via a `public` constructor.

File structure:

```text
src/
└── demo/
    ├── base/
    │   └── AbstractJob.java
    └── app/
        ├── ExportJob.java
        └── Main.java
```

**`src/demo/base/AbstractJob.java`**

```java
package demo.base;

public abstract class AbstractJob {
    private final String jobId;

    protected AbstractJob(String jobId) {
        if (jobId == null || jobId.isBlank()) {
            throw new IllegalArgumentException("jobId must not be blank");
        }
        this.jobId = jobId;
        System.out.println("AbstractJob: " + jobId);
    }

    protected final String jobId() {
        return jobId;
    }

    public abstract String execute();
}
```

**`src/demo/app/ExportJob.java`**

```java
package demo.app;

import demo.base.AbstractJob;

public final class ExportJob extends AbstractJob {
    public ExportJob(String jobId) {
        super(jobId);
        System.out.println("ExportJob ready");
    }

    @Override
    public String execute() {
        return "Export " + jobId();
    }
}
```

**`src/demo/app/Main.java`**

```java
package demo.app;

public class Main {
    public static void main(String[] args) {
        ExportJob job = new ExportJob("JOB-7");
        System.out.println(job.execute());
    }
}
```

From the directory containing `src`, compile and run:

```bash
mkdir out
javac -d out src/demo/base/AbstractJob.java src/demo/app/ExportJob.java src/demo/app/Main.java
java -cp out demo.app.Main
```

Exact output:

```text
AbstractJob: JOB-7
ExportJob ready
Export JOB-7
```

Explanation:

1. `new ExportJob("JOB-7")` allocates an `ExportJob` object; it does not create a separate `AbstractJob` object.
2. The `ExportJob(String)` constructor calls `super(jobId)`. The `AbstractJob(String)` constructor validates the input, initializes the `private final jobId` field, and then prints the first line.
3. After the superclass constructor finishes, the subclass constructor body prints `ExportJob ready`.
4. The subclass's `execute()` reads the identifier via the `protected final jobId()` method and prints the final line.

`private final` keeps the field internal and allows assignment only during valid initialization. `protected` lets subclasses use the necessary extension points; `public` on `ExportJob` serves as the instantiation interface for code using the subclass. The `execute()` method is `public abstract`, so the subclass implements it with the corresponding `public` scope.

## 3. Choosing Access Scope for an Abstract Class Constructor

Access scope applies to **constructor calls**, independently of whether the class itself can be instantiated directly.

| Declaration | Who can invoke the constructor? | When should you choose it? |
| --- | --- | --- |
| `public AbstractBase(...)` | Code with access to the class, including subclasses and valid constructor calls | Only when you want to publicly expose construction of the base part; for an abstract class, it usually does not need to be that broad |
| `protected AbstractBase(...)` | Code in the same package; subclasses in other packages can call it via `super(...)` (or `this(...)` leading to `super(...)`) according to Java rules | Common choice when designing an abstract class as a foundation for subclasses across multiple packages |
| `AbstractBase(...)` (package-private, no explicit modifier) | Classes in the same package | Restricts the hierarchy and construction access to a single package |
| `private AbstractBase(...)` | The class itself and classes in the same nest with private access, such as an appropriate nested class | Intentionally blocks external subclassing; only internal implementations can chain constructors |

Note on `protected` across **different packages**: constructor access for subclasses is primarily used inside a subclass constructor declaration via `super(...)`. It does **not** allow another class to freely call `new AbstractBase(...)`. Furthermore, `new AbstractBase(...)` is already prohibited by `abstract` even if the constructor is `public`.

Before choosing a modifier, you must distinguish **class visibility** (for example, whether a top-level class is `public` or only package-private) from **constructor accessibility**. A `protected` constructor does not enable a subclass outside the package to access a package-private top-level superclass.

### Why Is `protected` Often Appropriate?

An abstract class designed for external inheritance typically has a `protected` constructor to affirm: “This is an initialization operation for subclasses.” A `public` constructor is still valid, but rarely brings additional benefit if end users are only meant to instantiate concrete subclasses.

If only classes in the same package are allowed to extend the class and construct objects, a package-private constructor has a narrower scope. When you want exact control over every implementation class using nested classes, `private` can be appropriate, though it should not be chosen if regular subclasses outside the nest are needed.

## 4. `super(...)`, `this(...)`, and the Default Constructor

### 4.1. No Constructors Are Inherited

Suppose the abstract class only has a constructor that accepts parameters:

```java
abstract class Base {
    protected Base(String name) {
        System.out.println(name);
    }
}

class Child extends Base {
    Child() {
        // Does not explicitly call the superclass constructor.
    }
}
```

**This example intentionally fails to compile.** In Java 17, the compiler automatically inserts a no-argument `super()` call at the beginning of the `Child()` constructor. However, `Base` does not define a no-argument constructor, so that call is invalid.

Fix it by passing an argument explicitly:

```java
class Child extends Base {
    Child() {
        super("child");
    }
}
```

The fix above illustrates **the subclass declaration**; it shares the `Base` definition immediately above and is not a standalone program. If a parameter is needed from the caller, the subclass can define `Child(String name) { super(name); }`.

### 4.2. When Does Java Generate a Default Constructor?

If a class (including an abstract class) **declares no constructors**, the compiler provides a default no-argument constructor. This constructor calls the superclass's `super()`; therefore, the next superclass must have an accessible no-argument constructor. Once **any constructor** is declared, Java no longer automatically adds a no-argument constructor.

Two cases need to be distinguished:

- `abstract class Base {}`: has a default constructor, even though `new Base()` is still invalid.
- `abstract class Base { protected Base(int id) {} }`: has only the declared constructor; subclasses are required to chain to the constructor that takes an `int`.

### 4.3. `this(...)` and `super(...)`

In a Java 17 constructor, an explicit constructor call `this(...)` (another constructor of the **same class**) or `super(...)` (a constructor of the **superclass**) must be the first statement. A constructor cannot directly call both; when chaining through `this(...)`, it must eventually reach a superclass constructor call. You must not create a `this(...)` cycle.

Short example (illustrating the superclass only):

```java
abstract class Base {
    private final String name;

    protected Base() {
        this("unnamed");
    }

    protected Base(String name) {
        this.name = name;
    }

    protected final String name() {
        return name;
    }
}
```

A subclass can use `super()` or `super("custom")` if the corresponding constructor is accessible. You cannot write a statement like `System.out.println("start");` before `super(...)` in a constructor when using Java 17.

## 5. Initialization Order and the Pitfall of Calling Overridable Methods

When instantiating a subclass, the constructor call chain climbs up to `Object` and then processes each superclass in turn down toward the subclass. Superclass field initialization and initializers run before subclass field initialization and initializers; the superclass constructor body finishes before the subclass constructor body.

**You should not call overridable methods from an abstract class constructor.** Java uses dynamic dispatch: a call to an overridden method in the superclass constructor can still execute the subclass implementation while the subclass's own initialization state is not yet ready.

The following example is standalone and runnable (save as `Main.java`):

```java
abstract class Parent {
    protected Parent() {
        System.out.println("In parent: " + description());
    }

    protected abstract String description();
}

final class Child extends Parent {
    private String label = "ready";

    @Override
    protected String description() {
        return label;
    }
}

public class Main {
    public static void main(String[] args) {
        new Child();
    }
}
```

Run:

```bash
javac Main.java
java Main
```

Output:

```text
In parent: null
```

`label` still has its default value `null` when the `Parent` constructor calls `description()`; the subclass's assignment of `"ready"` happens afterward. This is why a superclass constructor should validate/assign **state owned by the superclass itself**, and only call non-overridable methods such as `private` or `final` methods when appropriate. If subclass-dependent behavior is needed, execute it after the object finishes initializing.

## 6. The `private` Case: Nested Implementations Only

A `private` constructor on an abstract class generally makes top-level subclasses unable to call `super(...)`. However, nested classes in the same nest have private access, so it can be used to restrict the family of implementations. The following example is a standalone `Main.java` file:

```java
abstract class Token {
    private Token() {
    }

    public static Token create() {
        return new InternalToken();
    }

    public abstract String value();

    private static final class InternalToken extends Token {
        @Override
        public String value() {
            return "internal";
        }
    }
}

public class Main {
    public static void main(String[] args) {
        Token token = Token.create();
        System.out.println(token.value());
    }
}
```

Compile/run with `javac Main.java` and `java Main`; output:

```text
internal
```

`Token.create()` is a factory that creates the internal subclass. External code cannot call `new Token()` because the class is abstract, and ordinary top-level subclasses cannot call the `private Token()` constructor either. This is a technique for controlling implementations, not the default approach for every abstract class.

## 7. Practical Rules for Choosing Constructors in Design

- **Need to guarantee shared invariants:** put required parameters in the abstract class constructor, validate data at creation time, and store shared state in `private final` fields when appropriate.
- **Allow extension outside the package:** typically choose a `protected` constructor; the subclass decides whether to declare a `public` constructor for client code.
- **Implement only within the same package:** consider a package-private constructor; you still must examine the access scope of the class and its other members.
- **Allow only nested classes to implement:** consider `private` along with an explicit factory; ensure the design genuinely needs to close the hierarchy.
- **Have multiple valid ways to initialize:** overload constructors and use `this(...)` to consolidate initialization logic into one consistent path.
- **Want to hide instantiation details in the public API:** a factory method can return the abstract type; the concrete subclass constructor must still form a valid constructor chain.
- **Guard against partially initialized objects:** avoid accessing subclass state through overridden methods in the superclass constructor.

## 8. Common Errors and How to Diagnose Them

| Scenario | Cause | Fix |
| --- | --- | --- |
| `Base is abstract; cannot be instantiated` | Using `new Base(...)` with an abstract class | Instantiate a concrete subclass or use a factory returning type `Base` |
| `constructor Base ... cannot be applied to given types` | The compiler inserts `super()`, but the superclass only has parameterized constructors | Call the appropriate `super(thamSo)` |
| `Base(...) has private access` | A subclass not in the same nest tries to call a `private` constructor | Choose `protected` / package-private according to the design scope, or use an internal implementation |
| `Base(...) has protected access` in code from another package | Code directly uses a `protected` constructor outside the allowed context | Give the concrete subclass constructor an appropriate scope and call `super(...)` from the subclass |
| “call to super must be first statement” on Java 17 | Another statement is placed before `super(...)` or `this(...)` | Move the explicit constructor call to the beginning |
| Subclass value is `null` / `0` in the superclass constructor | The superclass constructor calls an overridden method before the subclass has initialized its fields | Remove the overridden method call from the superclass constructor; defer the behavior until after initialization |

Actual compiler error messages may vary depending on the compiler and context; the table focuses on the causes to check.

## 9. Self-Check

1. If `abstract class A` has a constructor `protected A(int x)`, what must `class B extends A` in another package do? → Declare a constructor for `B` and call `super(x)`; Java does not automatically forward arguments to the superclass.
2. Why does a `public` constructor not allow writing `new A(...)` when `A` is abstract? → The rule prohibiting instantiation of an abstract class is independent of constructor accessibility.
3. When is a package-private constructor more appropriate than `protected`? → When the intent is to allow only code in the same package to call the constructor, without supporting subclasses in other packages through that constructor.
4. Why should a superclass constructor not call an abstract method implemented by a subclass? → Dynamic dispatch can run subclass code before subclass fields are initialized.
5. If the superclass constructor has parameters and there is no no-argument constructor, what error can occur in a subclass? → The implicit `super()` does not match; an explicit `super(...)` is required.

**Key takeaway:** An abstract class constructor is the mechanism for initializing shared state through the subclass constructor chain. Choose the modifier based on who is permitted to extend the class, invariant preservation requirements, and API scope, while ensuring every constructor path reaches a valid `super(...)`.
