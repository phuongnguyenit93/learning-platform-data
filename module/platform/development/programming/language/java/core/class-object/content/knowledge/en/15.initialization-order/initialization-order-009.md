# Calling an Overridden Method When an Object Is Not Yet Fully Initialized in Java

When creating an object of a **subclass**, Java must execute the initialization process in sequence from the superclass to the subclass. One error-prone point is that **a superclass constructor may call an instance method overridden by a subclass**. Java still performs **dynamic dispatch** according to the actual class of the object, even when that object's initialization process **has not yet completed**.

Consequence: the subclass's overriding method may run **before the subclass's field initializers, instance initializer blocks, and constructor body execute**. The subclass's instance fields at that moment may still hold default values such as `null`, `0`, or `false`, even when the source code declares an initializer or a `final` field that will be assigned in the constructor. This can violate invariants, read invalid state, throw `NullPointerException`, or cause side effects whose root cause is very hard to find.

**Design principle:** **do not call an overridable method from a constructor or instance initializer when the method's behavior depends on subclass state that has not yet finished initializing**. Prefer having the constructor only validate/assign the state of that class itself, using appropriate `private`/`final` helpers, or separating polymorphic operations into a phase **after the object has been completely constructed**.

This Java 17+ lesson explains initialization order, dynamic dispatch inside constructors, the difference between field initializers and default values, direct/indirect calls, runnable bug examples, fixing the design with safe APIs, constructor chaining, `final`/`private`/`static`, `this` escape, the impact on records and concurrency, along with a review checklist.

## 1. Why is the same method dangerous inside a constructor yet valid afterward?

Consider two classes:

~~~java
class Parent {
    Parent() {
        describe(); // Can dispatch into the subclass
    }

    void describe() {
        System.out.println("Parent");
    }
}

class Child extends Parent {
    private String name = "Ready";

    @Override
    void describe() {
        System.out.println("Child name = " + name);
    }
}
~~~

This is an **illustrative declaration snippet** without a standalone runnable `main`.

If you execute `new Child()`, the `Parent()` constructor calls `describe()`. The object being created **actually belongs to class Child**, so the invocation of the overridable method can run `Child.describe()`. However, the initializer `name = "Ready"` **has not run yet**, because the superclass constructor has not finished. Therefore, the overriding method can print:

~~~text
Child name = null
~~~

Only after `Parent()` returns does Child's instance initialization run, and `name` receives `"Ready"`. If you call `child.describe()` **after `new Child()` completes**, the result instead is:

~~~text
Child name = Ready
~~~

**Both calls use the same `Child.describe()` implementation, but they run at two different points in the object's lifecycle.** Java does not randomly pick the superclass at first and the subclass later: **dynamic dispatch still selects the subclass implementation**, whereas it is the subclass's state that differs.

### 1.1. This is a lifecycle design flaw, not just a syntax error

Classes can **compile successfully** even if a constructor calls an overridable method. Java does not strictly forbid this kind of call at compile time. However, the compiler does not guarantee that overrides in future subclasses will only read already-initialized fields.

A subclass written by another library or developer might change behavior, use dependencies, register listeners, publish notifications, or access an unassigned `final` field. Therefore, the main issue is the **contract of the constructor and extension point**, not just a special exception in the example.

## 2. Instance initialization order in Java 17

When creating an instance with `new Child(...)`, considering a simple superclass chain `Object → Parent → Child`, Java performs the following conceptual steps:

1. Allocate the object with runtime type **Child**; the instance fields of the entire object start with **default values** according to their Java types.
2. Execute the superclass constructor chain (eventually passing through `Object`) according to the rules for explicit/implicit constructor invocations.
3. During **Parent** initialization, execute Parent's instance field initializers and instance initializer blocks in the appropriate source order, followed by Parent's constructor body.
4. After the Parent initialization path succeeds, execute **Child's instance field initializers and instance initializer blocks** in their corresponding declaration order.
5. Execute the remainder of the **Child constructor body** after the superclass/constructor chaining call.
6. If these steps complete normally, the `new Child(...)` call then returns the reference to the caller.

The rules above are meant to explain the normal initialization path; `this(...)` constructor chaining cases have additional rules to avoid running instance initializers twice, and exceptions can terminate the process before completion.

~~~text
new Child(...)
    |
    v
Object is allocated, all instance fields have default values
    |
    v
Object / superclass constructor chain
    |
    v
Parent field initializers + Parent instance initializers
    |
    v
Parent constructor body
    |       |
    |       +--> calls virtualMethod()
    |                  |
    |                  +--> dispatches to Child.override()
    |                              Child fields may still be null / 0
    |
    v
Child field initializers + Child instance initializers
    |
    v
Child constructor body
    |
    v
new Child(...) completes normally
~~~

**Important:** class Child is already the **runtime class** of the object from the moment it is created. There is no separate Parent object that later "transforms" into a Child object. The Parent constructor runs **on the same object being constructed**, while Child's initialization has not yet executed.

### 2.1. Distinguishing static initialization

Static field initializers/static initializer blocks belong to **class initialization**, not to each instance. When a class is used under active-use conditions, the JVM initializes the class and its superclasses according to the relevant rules. Do not conflate "a static initializer runs once per runtime class" with "Child's instance initializer only runs after the Parent constructor".

This lesson focuses on **subclass instance state**. A ready static field does not prove that the final/instance fields of a Child object have been initialized.

### 2.2. Default values at allocation

| Instance field kind | Default value before initializer/constructor assignment |
| --- | --- |
| `byte`, `short`, `int`, `long` | `0` corresponding to the type |
| `float`, `double` | `0.0` corresponding to the type |
| `boolean` | `false` |
| `char` | the `'\u0000'` character |
| References such as `String`, `List<?>`, other classes, arrays | `null` |

A field with an initializer such as `int size = 10;` **does not receive 10 immediately at object allocation time before any constructor**. It starts with the default value and is only assigned later by the corresponding instance initialization.

This is why an overriding method called from a superclass constructor can observe **`0` instead of 10** or **`null` instead of the initialized string in the source code**.

## 3. Dynamic dispatch still occurs inside a superclass constructor

Normal overridable instance methods are called through a receiver. Inside the Parent constructor, the implicit receiver of `describe()` is **`this`**, the very object currently being initialized.

~~~java
class Base {
    Base() {
        announce();      // Invocation with implicit receiver this
        this.announce(); // Same receiver semantics, if code chooses to call it again
    }

    void announce() {
        System.out.println("Base");
    }
}
~~~

If the object being created belongs to subclass `Derived` and Derived overrides `announce()`, **both valid invocations above can dispatch to the Derived implementation**. `this` in the Base constructor is not a separate Base object; it is a reference to the **actual runtime object**, which may be Derived.

### 3.1. Do not confuse compile-time checking with runtime implementation

The compiler verifies that `announce()` is a member callable from the location of the Base constructor. Afterward, for a virtual instance method call, the JVM selects the appropriate implementation based on the receiver's runtime class. A constructor written in Base **does not force a virtual call to always run Base.announce()**.

This ensures consistent polymorphism across many places, but creates a **dangerous phase** while the object is not yet finished being constructed.

### 3.2. Precise terminology

- **Overridable instance method:** a method that can be validly overridden by a subclass, depending on visibility and modifiers such as `final`, `private`, and `static`.
- **Override:** a subclass provides an implementation for an inherited method according to Java rules.
- **Dynamic dispatch:** selecting the implementation of an overridable method based on the runtime receiver.
- **Partially initialized object:** an object currently under construction where part of the initialization code has not yet completed.
- **Invariant:** a state condition that an object commits to maintaining when used according to its contract.

The bug here occurs when **the overriding method expects Child's invariant to already be established**, while the call takes place before that invariant exists.

## 4. Runnable program: observing `null` and `0` despite subclass initializers

Create the file **`PrematureOverrideDemo.java`**:

~~~java
public class PrematureOverrideDemo {
    static class Parent {
        Parent() {
            System.out.println("1. Parent constructor");
            showState();
            System.out.println("3. Parent constructor done");
        }

        void showState() {
            System.out.println("Parent.showState");
        }
    }

    static final class Child extends Parent {
        private final String name;
        private int count = initializeCount();

        private int initializeCount() {
            System.out.println("4. Child field initializer");
            return 7;
        }

        {
            System.out.println("5. Child instance initializer");
        }

        Child(String name) {
            this.name = name;
            System.out.println("6. Child constructor");
        }

        @Override
        void showState() {
            System.out.println("2. Child.showState name="
                    + name + ", count=" + count);
        }

        String summary() {
            return "name=" + name + ", count=" + count;
        }
    }

    public static void main(String[] args) {
        Child child = new Child("Lan");
        System.out.println("7. Ready: " + child.summary());
    }
}
~~~

Compile/run with JDK 17+:

~~~bash
javac -encoding UTF-8 PrematureOverrideDemo.java
java PrematureOverrideDemo
~~~

**Exact stdout:**

~~~text
1. Parent constructor
2. Child.showState name=null, count=0
3. Parent constructor done
4. Child field initializer
5. Child instance initializer
6. Child constructor
7. Ready: name=Lan, count=7
~~~

Reading it step by step:

1. `new Child("Lan")` begins constructing an object of runtime type Child. `name` defaults to `null` and `count` defaults to `0`.
2. The Parent constructor prints line 1, then calls `showState()`.
3. `Child.showState()` is selected **due to overriding**, even though the Child constructor has not run yet. Line 2 reads `name=null` and `count=0`.
4. The Parent constructor prints line 3 and then finishes.
5. Child's instance field initializer calls `initializeCount()`, prints line 4, and then assigns `count=7`.
6. Child's instance initializer block runs and prints line 5.
7. The Child constructor assigns the blank final field `name = "Lan"` and then prints line 6.
8. After the constructor completes, `child.summary()` observes `name=Lan, count=7` and prints line 7.

### 4.1. `final` does not by itself prevent reading the default value during partial initialization

`name` is a `private final String`, and the Java compiler accepts it because the Child constructor assigns it properly under definite assignment upon normal completion. However, **the `showState()` override runs early** and can observe `name=null` before this assignment.

The distinction is very important:

- **Definite assignment** forces final field initialization to reach a valid value before the constructor completes normally.
- It **does not guarantee** that every virtual call made mid-way through object construction will only observe the final value.
- The **Java Memory Model guarantees for final fields** also rely on proper object construction conditions and do not imply that every action taken before the constructor finishes is safe.

**Do not "fix" this bug merely by adding `final` to the subclass's field.** Fix the method call site or the lifecycle contract.

## 5. When the subclass initializer expression has not yet run, the field remains at its default

A common reasoning mistake:

~~~java
class Child extends Parent {
    private String label = "READY";

    @Override
    void printLabel() {
        System.out.println(label.length());
    }
}
~~~

One might assume that `label` is definitely non-null because **the declaration line already specifies `= "READY"`**. However, Child's initializer runs **after** the Parent constructor finishes. If the Parent constructor calls `printLabel()`, dynamic dispatch into Child.printLabel can occur while `label == null`.

That can lead to a `NullPointerException`, not merely printing the wrong label. You should not rely on an initializer at declaration to protect an overriding method that is called prematurely.

### 5.1. Default values are a JVM initialization mechanism, not "business-valid values"

In Java, object fields have default values during initialization. However, a domain class may specify stronger invariants:

- `title` must be non-null and non-blank.
- `count` must be positive.
- `dependency` must be ready.
- `items` must be an already-created list.
- `clock` must be injected.
- `config` has been validated.

A virtual method that uses those invariants **before the subclass finishes initializing** can run on invalid state even though Java permits the call at the language level.

## 6. Runnable program: constructor fails because an override is called on a null field

Create the file **`ConstructorNpeDemo.java`**:

~~~java
import java.util.Objects;

public class ConstructorNpeDemo {
    static abstract class Component {
        Component() {
            printLength(); // Dangerous: calls an abstract/overridable method
        }

        abstract void printLength();
    }

    static final class TextComponent extends Component {
        private final String text;

        TextComponent(String text) {
            this.text = Objects.requireNonNull(text, "text");
        }

        @Override
        void printLength() {
            System.out.println(text.length());
        }
    }

    public static void main(String[] args) {
        try {
            new TextComponent("Java");
        } catch (NullPointerException ex) {
            System.out.println("Caught NullPointerException");
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ConstructorNpeDemo.java
java ConstructorNpeDemo
~~~

**Exact stdout:**

~~~text
Caught NullPointerException
~~~

### 6.1. Why does passing `"Java"` still throw an NPE?

The caller passes a non-null String into the TextComponent constructor. However, according to initialization order:

1. Memory for the TextComponent object is allocated, and the `text` field initially has the default value `null`.
2. The constructor of superclass `Component` runs before the body of the TextComponent constructor.
3. `Component()` calls `printLength()`.
4. The JVM dispatches to `TextComponent.printLength()`, because the object's runtime type is TextComponent.
5. The overriding method calls `text.length()` while `text` is still null → `NullPointerException`.
6. The exception exits the superclass constructor, so **the line `this.text = Objects.requireNonNull(...)` in the TextComponent constructor never executes**.
7. `new TextComponent("Java")` fails; the caller catches the NPE and prints a predefined message.

**Even `final String text` does not help yet:** assigning the final field in the TextComponent constructor happens only *after* the Component constructor completes normally. Because the Parent/Component constructor already threw, execution never reaches the assignment step.

### 6.2. Why doesn't the compiler catch this bug?

The compiler allows `TextComponent.printLength()` to read the `text` field because it is a regular instance method; definite assignment of a final field is checked per constructor, rather than proving across the entire **call graph and dynamic dispatch** that every method call during initialization is safe.

A linter/static analysis tool can warn about an "overridable method call in constructor", yet the Java standard does not turn every call of this form into a compile error. This is why **code can compile yet fail immediately upon `new`**.

## 7. Not only direct calls: a constructor can go through an intermediate method

The danger does not appear only when the constructor directly writes `hook()`:

~~~java
class Base {
    Base() {
        prepare();
    }

    private void prepare() {
        // This private method cannot be overridden by a subclass,
        // but it calls an overridable method:
        validate();
    }

    void validate() {
    }
}

class Child extends Base {
    private String token = "ready";

    @Override
    void validate() {
        System.out.println(token);
    }
}
~~~

This is an illustrative declaration snippet without a `main`. `Base.prepare()` is **private** so it cannot be overridden. Yet when it calls `validate()`, the call **can still dispatch to `Child.validate()`**. While the Base constructor runs, `Child.token` is still null.

**Therefore, replacing `hook()` with `privateHelper()` is not safe enough by itself** if the private helper calls an overridable method deeper down. You must review **the entire call path that can lead to virtual dispatch** during initialization.

### 7.1. Indirect calls through common APIs

Situations that are often overlooked:

- A constructor passes `this` to a logger or concatenates strings so that the object's `toString()` is used.
- A constructor calls `Objects.toString(this)`.
- A constructor puts `this` into a collection, and then the collection/sort/comparator/callback accesses a method of the object.
- A constructor registers a listener receiving `this` and the listener is triggered immediately.
- A constructor calls a hook in the base class to "check subclass state".
- A constructor calls a public method whose body calls an overridable protected method.
- A constructor starts a task/thread that uses `this` before subclass fields are initialized.

Not every API above **always** calls an overriding method in every case; the risk depends on the call path and specific behavior. The common rule is that **a constructor should not pass an incompletely constructed object into an execution path that can invoke polymorphic behavior relying on subclass state**.

## 8. `toString()`, `equals()`, and `hashCode()` are also overridable methods

Three familiar `Object` methods can all be overridden by a subclass (according to valid override rules). A superclass constructor writes:

~~~java
class Base {
    Base() {
        System.out.println(this);
    }
}
~~~

The `println(Object)` call eventually needs a representation of the object; on this normal path, converting the object to a string can call the runtime subclass's `toString()`.

~~~java
class Named extends Base {
    private final String name;

    Named(String name) {
        this.name = name;
    }

    @Override
    public String toString() {
        return "Named(" + name + ")";
    }
}
~~~

With `new Named("Lan")`, the line printed from the Base constructor can be:

~~~text
Named(null)
~~~

because `Named.toString()` runs before the assignment to the final field `name`. Here there is no need to call `toString()` explicitly in Base; printing `this` already created the indirect path.

**Safe approach:** log validated **constructor parameters** or Base's own properly initialized fields, rather than using `this` as a complete object to dump the entire subclass state right inside the superclass constructor.

With `equals()` and `hashCode()`, risks can arise if an uninitialized object is inserted into a hash-based structure or passed to an operation that relies on equality/hash behavior. Do not treat registering the object into a Map/Set mid-constructor as harmless.

## 9. How do `private`, `final`, and `static` affect dispatch?

Not every method call inside a constructor has the same potential to be overridden.

| Called method | Can it be overridden by a subclass as an instance method? | What to watch out for |
| --- | --- | --- |
| `private void check()` declared in Base | No | However, its body can still call another virtual method |
| `final void check()` | No | Its body can call another overridable hook |
| `static void check()` | Does not perform instance overriding; can be hidden | Static has no `this` receiver |
| `void check()` package-private | Depends on package relationship/overridability | Should not rely on package-private as a general safety strategy |
| `protected void check()` | Yes, if the subclass validly overrides it | Very commonly used as a hook; dangerous to call during initialization |
| `public void check()` | Yes, if not final and overridable | Client subclasses can change behavior |
| `super.check()` in an instance method | Selects the superclass implementation per super syntax | Does not mean nested calls inside the superclass implementation will not dispatch |

**Practical rule:** for work that belongs strictly internally to the constructor, prefer logic that **cannot be overridden** (appropriate `private`/`final`) and does not indirectly call overridable methods.

### 9.1. `private` methods are safe against direct overriding

~~~java
class Parent {
    Parent() {
        checkOwnFields();
    }

    private void checkOwnFields() {
        // Only reads Parent state that has been validly initialized.
    }
}
~~~

`checkOwnFields` cannot be overridden by Child to alter the behavior of this call itself. Still, it is only safe if it does not itself transfer control to overridable methods/callbacks that depend on subclass state.

### 9.2. `final` methods prevent overriding of that method itself

~~~java
class Parent {
    Parent() {
        checkOwnFields();
    }

    final void checkOwnFields() {
        // Cannot be overridden by a subclass.
    }
}
~~~

`final` is useful when a constructor needs an inheritable helper while preventing subclasses from modifying its logic. A `final` method can still call a virtual method internally; inspect the call graph deeply before concluding it is safe.

### 9.3. Static methods can help eliminate the implicit receiver

~~~java
class Parent {
    private final String id;

    Parent(String id) {
        this.id = validate(id);
    }

    private static String validate(String candidate) {
        if (candidate == null || candidate.isBlank()) {
            throw new IllegalArgumentException("ID rỗng");
        }
        return candidate;
    }
}
~~~

`validate` takes data explicitly and has no Parent `this` to accidentally call an overridable instance method. This style is usually clearer when validation depends solely on constructor arguments.

However, a static method **can still work with an explicit object**; if you pass `this` of the incomplete object into a static helper and that helper calls virtual methods, the risk remains. `static` is not an automatic safety shield.

## 10. Constructor chaining: `this(...)` does not solve calling overrides too early

A subclass can have multiple constructors:

~~~java
class Child extends Parent {
    private final String name;

    Child() {
        this("Anonymous");
    }

    Child(String name) {
        super();
        this.name = name;
    }
}
~~~

In Java 17, an explicit constructor invocation `this(...)` or `super(...)` must be the first statement of the respective constructor when used. Having `Child()` call `this("Anonymous")` does not cause Child instance fields to be assigned before the superclass constructor runs.

Conceptual chain:

~~~text
Child()
   |
   +--> this("Anonymous") -> Child(String)
                                |
                                +--> super() -> Parent()
                                |                |
                                |                +--> may call override on Child
                                |                     name is still null
                                |
                                +--> Child fields/initializer and body assign name
~~~

What must be avoided is **the virtual method call from the Parent constructor**. Simply "adding a constructor overload for Child" does not fix the lifecycle.

### 10.1. Evaluation order of constructor arguments does not grant access to not-yet-existing subclass state

You can pass already-known constructor parameters into `super(...)` per Java rules, but you must not assume that Child instance fields have been initialized before super. In Java 17, the explicit constructor invocation syntax also imposes restrictions on `this` and instance members, which cannot yet be referenced in the usual way before superclass initialization.

You should turn data needed by the superclass into **constructor parameters**, and let the superclass validate/assign its own fields instead of calling a subclass hook to ask "provide your own data right now".

## 11. Safest design: complete construction before invoking polymorphic behavior

If a method truly needs subclass state, call it **after `new Child(...)` completes successfully**.

~~~java
Child child = new Child(...);
child.start();
~~~

When the caller explicitly invokes `start()` on an object whose constructor has finished, `Child` fields, instance initializers, and the constructor body have already had the opportunity to establish the full invariants.

**However, separating the call after the constructor does not guarantee absolute safety by itself:** code inside `start()` still needs proper validation and a concurrency protocol; repeated calls or out-of-order calls must be controlled according to the API.

### 11.1. Do not require subclasses to call init from their constructors if init uses polymorphism

An easy-to-misjudge alternative is telling subclasses to call `initialize()` at the end of each subclass constructor:

~~~java
class Child extends Parent {
    Child() {
        // superclass has completed
        initialize(); // Can dispatch to a deeper subclass!
    }
}
~~~

If `Child` **is not final** and a `GrandChild extends Child` overrides `initialize()`, then while the Child constructor is running, GrandChild fields are still uninitialized. The risk **is merely shifted down one level**, not eliminated.

To ensure a polymorphic hook runs only after **the entire runtime object** has finished constructing, move the call **outside the constructor chain** or use a properly controlled factory/lifecycle mechanism.

### 11.2. Using a static factory when controlling the constructor

~~~java
final class Worker {
    private final String name;

    private Worker(String name) {
        this.name = name;
    }

    static Worker create(String name) {
        Worker worker = new Worker(name);
        worker.onReady();
        return worker;
    }

    private void onReady() {
        System.out.println(name);
    }
}
~~~

This illustrates a factory for a **final class**: the factory creates the complete object and then calls `onReady`. `Worker` is final, so no subclass can add fields that need initialization after the Worker constructor. In a design with inheritance, a factory that wants to invoke a polymorphic hook must ensure that the **concrete runtime subclass** has truly finished building before calling the hook.

## 12. Runnable program: safe initialization and template method after the constructor

Create the file **`SafeConstructionDemo.java`**:

~~~java
import java.util.Locale;
import java.util.Objects;

public class SafeConstructionDemo {
    static abstract class Component {
        private final String id;

        protected Component(String id) {
            this.id = Objects.requireNonNull(id, "id");
            // Do not call render(), renderContent(), or any hook.
        }

        public final void render() {
            System.out.println("Component " + id);
            renderContent();
        }

        protected abstract void renderContent();
    }

    static final class TextComponent extends Component {
        private final String content;

        TextComponent(String id, String content) {
            super(id);
            this.content = Objects.requireNonNull(content, "content");
        }

        @Override
        protected void renderContent() {
            System.out.println(
                    "Content " + content.toUpperCase(Locale.ROOT));
        }
    }

    public static void main(String[] args) {
        TextComponent text =
                new TextComponent("T-1", "Java");

        System.out.println("Construction complete");
        text.render();
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 SafeConstructionDemo.java
java SafeConstructionDemo
~~~

**Exact stdout:**

~~~text
Construction complete
Component T-1
Content JAVA
~~~

### 12.1. Why is this design safer?

- The `Component` constructor only validates/assigns its `id`. It does not call `renderContent`.
- The `TextComponent` constructor only begins after the `Component` constructor finishes; it validates/assigns the subclass's `content`.
- `new TextComponent(...)` completes normally and the variable `text` receives the reference.
- The caller prints `Construction complete`, then calls `text.render()`. At this point `content` is already non-null if object construction succeeded.
- `render()` is **final** so subclasses cannot bypass Component's orchestration; it invokes the **abstract hook** `renderContent()`, but only when requested by the caller after construction.
- `renderContent()` dispatches to the TextComponent implementation and uses the already-initialized String.

This is a good example of the **template method pattern**: the superclass can define a stable execution flow and the subclass supplies a customization step, while **not starting the customization step inside the constructor**.

**Contract clarification needed:** if another API invokes `render()` during the initialization phase through an escaped `this`, the problem can still reappear. Controlling when public methods are called is part of lifecycle design.

## 13. If the superclass truly needs subclass data at initialization, pass the input via `super(...)`

A superclass constructor sometimes needs a value that the subclass knows. The unsafe way is to **call an overridable method**:

~~~java
abstract class Base {
    final String label;

    Base() {
        label = createLabel(); // Dangerous: abstract hook!
    }

    abstract String createLabel();
}
~~~

The subclass might need fields that are not yet ready in order to build the label. Instead, turn the requirement into a **constructor parameter**:

~~~java
abstract class Base {
    private final String label;

    protected Base(String label) {
        if (label == null || label.isBlank()) {
            throw new IllegalArgumentException("Label trống");
        }
        this.label = label;
    }

    public final String label() {
        return label;
    }
}

final class NamedChild extends Base {
    private final int version;

    NamedChild(String code, int version) {
        super("Child-" + code);
        this.version = version;
    }
}
~~~

This is an illustrative declaration. `NamedChild` can evaluate the expression from **constructor parameters** before calling `super(...)`, without needing to use Child's own uninitialized fields.

### 13.1. Using a static helper to compute a super-argument

If the validation/computation logic is complex:

~~~java
class Base {
    final String token;

    Base(String token) {
        this.token = java.util.Objects.requireNonNull(token);
    }
}

final class Child extends Base {
    Child(String raw) {
        super(normalize(raw));
    }

    private static String normalize(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("raw trống");
        }
        return raw.trim();
    }
}
~~~

`normalize(raw)` is a static helper that only processes the parameter and does not access `this`. This ensures the superclass receives valid data without having to call into virtual subclass behavior inside the constructor.

**Do not use `super(this.someValue())` or an instance method of the uninitialized object** to compute a superclass argument in Java 17; the constructor invocation context is restricted, and such a design runs counter to the goal of avoiding premature use of subclass state.

## 14. Beware of three-level inheritance: calling from the middle can still dispatch downward

It is not only the root superclass that has this problem. With the chain:

~~~text
GrandParent
    ^
    |
  Parent
    ^
    |
  Child
~~~

If the **Parent constructor** calls an overridable method, the runtime object can still be **Child**, and Child's override can run before **Child-specific initialization** completes.

Example:

~~~java
class Root {
    Root() {
    }
}

class Middle extends Root {
    Middle() {
        onReady();
    }

    void onReady() {
        System.out.println("Middle");
    }
}

class Leaf extends Middle {
    private String ready = "YES";

    @Override
    void onReady() {
        System.out.println("Leaf ready = " + ready);
    }
}
~~~

If you create `new Leaf()`, `Middle()` calls `onReady()` before the field initializer `Leaf.ready`; the result can be:

~~~text
Leaf ready = null
~~~

The key point: even though the `Middle` constructor starts **after** the `Root` constructor, `Leaf` is still not finished. Therefore, **the constructor of any class in the inheritance chain** must not assume that all runtime subclass state is ready.

### 14.1. Calling at the end of an intermediate class's constructor is still unsafe

You might write:

~~~java
Middle() {
    initializeMiddle();
    onReady(); // End of Middle constructor, but before Leaf initialization
}
~~~

Moving the hook to the end of the Middle constructor does not change the fact that Leaf initialization runs **after** the Middle constructor. If the intent is to announce "the entire runtime object is ready", **an intermediate constructor lacks sufficient information to guarantee that point in time** for future subclasses.

## 15. Why can a `final class` reduce risk yet not solve everything?

If a class is declared **`final`**, it cannot have valid subclasses, so its own constructor cannot unexpectedly dispatch into an override of an uninitialized subclass.

~~~java
final class FinalCounter {
    private int count;

    FinalCounter() {
        reset();
    }

    void reset() {
        count = 0;
    }
}
~~~

In this example, there is no subclass of FinalCounter to override `reset()`. The call from the constructor does not face the **polymorphic subclass dispatch risk** just analyzed.

Even so, you still need to check:

- Does `reset()` expose `this` through a callback or registry?
- Does it depend on another uninitialized field?
- Does it call external code that throws an exception or creates side effects?
- Does it use a resource that is not yet ready?
- Does a final class actually fit the API's extension needs?

**Do not automatically make every class final just to "fix" a constructor calling an inappropriate method.** If the library needs to support subclassing, fix the lifecycle and clearly declare the hooks.

### 15.1. A `final method` likewise addresses only direct overriding

A `final void check()` method cannot be overridden by subclasses. However, if `check()` calls a non-final `hook()`, virtual dispatch can still occur indirectly. Review the entire call graph before concluding it is safe.

## 16. A superclass `private` method differs from a same-named subclass method

A subclass can declare a method with the same name as a private method in the superclass, but that is **not an override** of the private superclass method under the normal mechanism:

~~~java
class Base {
    Base() {
        helper();
    }

    private void helper() {
        System.out.println("Base private");
    }
}

class Child extends Base {
    void helper() {
        System.out.println("Child helper");
    }
}
~~~

With `new Child()`, the `helper()` call from the Base constructor executes **Base's private helper**, rather than dispatching to Child.helper. A private superclass method is not inherited as an overridable method.

Remember, however: if Base's private helper **goes on to call another overridable method**, the risk still arises. Do not use the `private` keyword as a way to hide an unsafe call path.

## 17. Object lifecycle and exposing `this` before initialization completes

Calling a virtual method prematurely is one symptom of a broader issue: **letting an object under construction become visible too early to external code or callbacks** (*this escape*).

~~~java
class EventSource {
    private static java.util.function.Consumer<Object> observer;

    static void setObserver(
            java.util.function.Consumer<Object> next) {
        observer = next;
    }

    static void publish(Object event) {
        if (observer != null) {
            observer.accept(event);
        }
    }
}

class Dangerous {
    private final String id;

    Dangerous(String id) {
        EventSource.publish(this); // Can invoke callback with an unready object!
        this.id = id;
    }

    String id() {
        return id;
    }
}
~~~

This is an **illustrative declaration** without a `main`. If the observer calls `event.toString()`, casts and calls `id()`, or starts another thread that uses the object, it may observe incomplete state.

Several forms of `this` escape to avoid from constructors:

- Putting `this` into a static collection/registry.
- Registering a listener whose callback may be triggered immediately.
- Sending `this` to an event bus.
- Starting a thread/task that holds a reference to `this`.
- Passing `this` into uncontrolled external code.
- Calling an overridable method through which a subclass might publish `this`.

### 17.1. `final field` and safe publication are related yet distinct issues

The Java Memory Model provides special guarantees for final fields when an object is properly constructed. However, **if `this` escapes before the constructor completes**, those assumptions about complete state can be broken. A final field is not insurance against all premature reads.

A better approach: the constructor builds the object and establishes its invariants, and then the caller/factory **registers the completed object** via a safe protocol.

~~~java
Dangerous item = new Dangerous("A");
// Only after the constructor has completed successfully:
// registry.register(item);
~~~

This is a usage fragment; a corresponding `registry` API is needed in the application. If multiple threads are involved, **safe publication** still needs to follow a concurrency protocol (synchronized/volatile/concurrent data structure or an appropriate mechanism), rather than relying merely on the order of two lines of code in the same thread.

## 18. Initialization order and constructors for abstract classes

An abstract class still has constructors; the constructor runs when initializing a concrete subclass. **An abstract method can be called from an abstract superclass constructor**, and the invocation will dispatch to the subclass implementation.

~~~java
abstract class AbstractProcessor {
    AbstractProcessor() {
        process(); // Dangerous
    }

    abstract void process();
}

final class ConcreteProcessor extends AbstractProcessor {
    private final String data;

    ConcreteProcessor(String data) {
        this.data = data;
    }

    @Override
    void process() {
        System.out.println("Data length = " + data.length());
    }
}
~~~

This is an illustrative declaration. `new ConcreteProcessor("abc")` can throw an NPE inside `process()` before the Child constructor assigns `data`.

**An unsafe design does not become safe merely because the hook is declared `abstract`.** On the contrary, an abstract method *requires* a subclass implementation, and the superclass constructor cannot know what state that implementation needs.

For an abstract base class, use **constructor parameters** for state needed during initialization; reserve abstract/protected hooks for the phase after the object is created.

## 19. Which method calls from a constructor can be considered safer?

Saying "never call any method inside a constructor" is too extreme. Java allows constructors to call methods, and many calls are valid and useful. We should distinguish them by **overridability and state dependencies**.

### 19.1. Static validation helper processing only parameters

~~~java
class UserId {
    private final String value;

    UserId(String raw) {
        this.value = normalize(raw);
    }

    private static String normalize(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("ID rỗng");
        }
        return raw.trim();
    }
}
~~~

The helper does not need `this`; it does not read subclass fields. That is a model easy to reason about, though the validation logic must still satisfy the contract.

### 19.2. Private helper accessing only already-ready base state

~~~java
class Base {
    private final int capacity;

    Base(int capacity) {
        this.capacity = capacity;
        validateOwnState();
    }

    private void validateOwnState() {
        if (capacity < 0) {
            throw new IllegalArgumentException("Capacity âm");
        }
    }
}
~~~

`validateOwnState()` cannot be overridden by a subclass. It only reads the `capacity` field that Base assigned earlier. This avoids a direct **early polymorphic callback**.

However, parameters can be validated **before** assigning state if the contract requires it. Watch out for cases where the method calls external code or exposes `this` itself.

### 19.3. Final helper controlling an inherited invariant

~~~java
class Base {
    Base() {
        establishBaseState();
    }

    final void establishBaseState() {
        // Cannot be overridden; does not call virtual hooks.
    }
}
~~~

This pattern may fit a controlled inheritance API. However, for internal implementation details, `private` usually expresses the hiding intent more clearly. Not every final helper needs to be public/protected.

## 20. Runnable program: indirect calls from a constructor still dispatch

Create the file **`IndirectDispatchDemo.java`**:

~~~java
public class IndirectDispatchDemo {
    static class Base {
        Base() {
            log();
        }

        private void log() {
            System.out.println("Base logging");
            System.out.println(describe());
        }

        String describe() {
            return "Base description";
        }
    }

    static final class Child extends Base {
        private String label = "READY";

        @Override
        String describe() {
            return "label=" + label;
        }
    }

    public static void main(String[] args) {
        Child child = new Child();
        System.out.println("After = " + child.describe());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 IndirectDispatchDemo.java
java IndirectDispatchDemo
~~~

**Exact stdout:**

~~~text
Base logging
label=null
After = label=READY
~~~

**Analysis:**

1. The Base constructor calls `private void log()`; this method itself is not overridden.
2. `log()` calls `describe()`, an overridable instance method of Base.
3. The runtime object is Child, so the call dispatches to `Child.describe()`.
4. Child's field initializer `label = "READY"` has not run yet, so the first call receives `label=null`.
5. After the Base constructor finishes, Child's initializer runs; the `child.describe()` call from `main` receives `label=READY`.

This example shows that **looking only at the first line of the constructor is not enough**. A seemingly safe private helper can conceal a call path to an overridable hook.

## 21. Do not confuse `super.method()` with a virtual call on an arbitrary receiver

Inside a subclass instance method:

~~~java
class Base {
    void describe() {
        System.out.println("Base");
    }
}

class Child extends Base {
    @Override
    void describe() {
        super.describe();
        System.out.println("Child");
    }
}
~~~

`super.describe()` selects the appropriate superclass implementation, not a new Base object. However, if the superclass implementation goes on to call **another virtual method**, that call can still dispatch down to the runtime subclass.

Example:

~~~java
class Base {
    void describe() {
        hook(); // Virtual call
    }

    void hook() {
    }
}

class Child extends Base {
    @Override
    void describe() {
        super.describe();
    }

    @Override
    void hook() {
        // Can be called via super.describe() -> hook()
    }
}
~~~

This is an illustrative declaration. Therefore, `super.describe()` does not mean "every call inside the Base method is forced to use the Base implementation".

Inside a superclass constructor, a `super(...)` call has the meaning of a **constructor invocation** in the initialization context; it should not be equated with `super.method()` in a regular method.

## 22. Limitation in a superclass's API: do not require subclasses to be ready too early

A superclass designed for extension often has a **protected hook**:

~~~java
abstract class Plugin {
    protected abstract void configure();
}
~~~

If the superclass constructor calls `configure()`, every concrete subclass is forced to run the hook before its constructor finishes. This is a difficult contract to use safely.

The API should instead use:

- **Constructor parameters** for data needed to establish the base invariant.
- **A factory or builder** that creates the complete object.
- **An explicit lifecycle method** `start()`, `initialize()`, or `open()` called after construction.
- **A final template method** that orchestrates protected hooks once the object is ready.
- **Composition/injection** when the need is merely swapping strategies and inheritance is unnecessary.
- **An immutable configuration object** validated before being passed into the constructor.

### 22.1. A lifecycle with two states needs documentation

If the API uses `start()`:

~~~text
CREATED -- start() --> STARTED -- close() --> CLOSED
~~~

then you must specify:

- Is calling methods before `start()` allowed?
- Can `start()` be called multiple times?
- When `start()` fails, what valid state does the object remain in?
- Can `close()` be called before `start()`?
- When multiple threads are involved, how is state protected?

Separating the initialization phase from the constructor solves the moment when **the subclass has not finished building**, but the lifecycle must be designed as a real contract rather than merely moving the bug from the constructor to an unguided method.

### 22.2. Do not call virtual hooks from a superclass field initializer

The same risk occurs with **a superclass's instance field initializer or instance initializer block**:

~~~java
class Base {
    final String description = describe(); // Can call override too early

    String describe() {
        return "Base";
    }
}
~~~

If the actual object belongs to Child overriding `describe()` to read Child fields, the call from Base's initializer can run before Child initialization. **Avoid calling overridable instance methods across the entire superclass initialization path, not only inside the constructor body.**

## 23. Inspecting order with a debugger without turning default values into invariants

When encountering a bug like "the field is definitely initialized, why is it still null?", a useful investigation approach is:

1. Set a breakpoint in the superclass constructor.
2. Set breakpoints in the overridable method on both the superclass and subclass.
3. Set a breakpoint in the subclass's instance field initializer (or a helper called by the initializer).
4. Set a breakpoint in the subclass constructor body.
5. Observe the **call stack**, the runtime type of `this`, and the field values at each point in time.

A conceptual call stack looks like:

~~~text
Child.describe()
Base.<init>()
Child.<init>()
Main.main()
~~~

This is a conceptual diagram of frame names; the debugger/JVM may show some compiler frames or operations differently. The key point is that **the subclass override is running inside the superclass constructor chain**.

### 23.1. What must be verified

- Does the call reach the override **directly or through a private/public helper**?
- Is there a field initializer `= ...` that has not yet executed?
- What runtime subclass is the object?
- Does another deeper subclass override the method?
- Is there log/toString/callback handling that receives `this`?
- Is the method being called after `new` has completed?
- Is another thread observing an incomplete object due to early publication?

**Do not merely add a null-check to silence an NPE while ignoring the lifecycle root cause.** An override might survive `null` yet still produce wrong data or side effects before the valid point in time.

## 24. Common fixes: from patching symptoms to fixing the contract

| Approach | Does it solve the root cause? | Commentary |
| --- | --- | --- |
| Add `if (field == null) return;` in the override | Usually **not yet** | Prevents NPE but may skip important work; the invariant still does not exist |
| Assign a field initializer on the declaration line | **Not sufficient** | The subclass initializer still runs after the superclass constructor |
| Mark the field `final` | **Not sufficient** | A blank final still has its default value before assignment; final does not fix timing |
| Move the hook to the end of the superclass constructor | **Not sufficient** | The subclass constructor still has not run |
| Route the superclass call through a `private` helper that calls the hook | **No** | The final call graph still contains virtual dispatch |
| Change a direct helper to `private`/`final`, calling no other hooks | **Possibly** | Reasonable if it only operates on already-ready base state |
| Pass data to the superclass via `super(args)` | **Usually yes** | Eliminates the need to query subclass state prematurely |
| Call the polymorphic operation after `new` completes | **Usually yes** | Must design the lifecycle, exceptions, and concurrency |
| Use a final concrete class when inheritance is not needed | **Possibly** | Eliminates the subclass override path, though initialization/escape issues remain |
| Extract the dependency into an injected interface | **Often helpful** | Controls extension via composition instead of constructor-time overriding |

Choose a fix based on **data responsibility**:

- Superclass needs data to validate/initialize itself → constructor arguments.
- Subclass needs to act after its state is ready → explicit post-construction operation.
- Superclass needs internal self-checking → non-overridable helper on already-initialized state.
- System wants to signal that a new object is ready → publish **after construction**, not from the constructor.

## 25. Scenarios with dependency injection and frameworks

Frameworks with lifecycle callbacks, proxying, or dependency injection can affect how an object is created or used. However, fundamental Java semantics do not change:

- The superclass constructor runs before the corresponding subclass instance initialization.
- An overridable instance method can dispatch according to the runtime subclass.
- You cannot assume a dependency/field set by a subclass or framework in a later phase is already ready inside the superclass constructor.
- Do not call overridable business methods from a constructor merely because a framework normally injects dependencies "early".
- Check framework documentation on constructor injection, field injection, post-construction callbacks, proxies, and lifecycle.

For example, if a dependency is assigned by a framework via a setter/field **after object creation**, then a constructor calling a method that relies on that dependency is even more dangerous: the field does not yet hold the application value. Constructor injection can help provide dependencies when constructing that class itself, yet **a superclass constructor still must not rely on unassigned subclass fields**.

If using `@PostConstruct` or a similar callback in a supported environment, distinguish the **framework phase** from the Java constructor, and do not automatically assume those callbacks guarantee thread safety or run strictly once across all tools.

## 26. `record`, `final class`, and choosing to avoid inheritance-driven initialization hazards

In Java 17, record classes are **implicitly final**. A record cannot be subclassed like an ordinary class:

~~~java
record PersonName(String given, String family) {
    PersonName {
        if (given == null || family == null) {
            throw new IllegalArgumentException("Tên null");
        }
    }

    String fullName() {
        return given + " " + family;
    }
}
~~~

There is no user-defined subclass of record `PersonName` to override `fullName()`. That eliminates a category of bugs related to **a superclass constructor calling a subclass override** on the record type itself.

However:

- A record constructor still needs to validate invariants properly.
- Record components can be mutable references; a record does not deep-freeze automatically.
- Do not let `this` escape inside the constructor.
- Record constructors/canonical/compact constructors have their own rules; do not infer all mechanics from ordinary class inheritance.

When the data is a **value object** that does not need inheritance, a record or final class may fit well. When polymorphic behavior is needed, extend via interfaces/composition or an abstract class with a safe lifecycle.

## 27. Common misconceptions

1. **"The Parent constructor is running, so `Parent.method()` is guaranteed to be called."** False for overridable instance methods: the runtime object can be Child, so dynamic dispatch selects the override.
2. **"The object only gets the runtime type Child after the Child constructor finishes."** False. The object is created with runtime type Child from the very beginning of initialization.
3. **"A field `String label = "READY"` can never be null."** False during the phase before the subclass field initializer runs.
4. **"A `final` field cannot hold a default value mid-way."** False. A constructor-time virtual call can observe unassigned state.
5. **"The compiler will forbid all virtual methods inside constructors."** False. Many cases compile cleanly yet have runtime bugs.
6. **"Only constructors directly calling a hook are dangerous."** False. Private helpers, logging, `toString()`, and callbacks can lead to a hook indirectly.
7. **"Moving the call to the last line of the superclass constructor is safe."** False. Subclass initializers/constructors still have not run.
8. **"Using `this(...)` to chain constructors will assign Child fields before Parent."** False. The chain still follows superclass-first instance initialization.
9. **"Having the subclass constructor call the hook at the end is always enough."** False if a deeper subclass overrides it; you must consider the full runtime class.
10. **"A private method always makes all calls underneath it non-virtual."** False. Its body can still call a virtual method.
11. **"Static methods have dynamic dispatch like instance methods."** False. Static methods do not perform instance overriding like virtual methods.
12. **"`super.method()` locks down every sub-method that implementation calls."** False. Inside the superclass method, other virtual calls still dispatch normally.
13. **"Catching an NPE inside the constructor means the object is completely initialized."** False. An NPE can terminate construction; a half-built object must not be used.
14. **"A null-check inside the override fixes all bugs."** False. It may merely mask unready-state bugs or skip required actions.
15. **"Using a `final class` makes every constructor safe."** False. Subclass overrides are eliminated, yet side effects, `this` escape, field ordering, concurrency, and validation issues still remain.
16. **"Registering a listener in the constructor is fine because the caller has not seen the object yet."** False. The listener/callback can observe `this` before the caller receives the reference.
17. **"Because of the Java Memory Model for final fields, `this` escape is not an issue."** False. Initialization safety is conditional; you should not publish before the constructor completes.
18. **"All methods in constructors are forbidden."** False. Non-overridable helpers that are pure-parameter or operate only on already-ready base state can be valid.

## 28. Self-check exercises with answers

**Question 1.** `Base()` calls `show()`, and `Child extends Base` overrides `show()`. In `new Child()`, which implementation can run?

**Answer:** `Child.show()` via dynamic dispatch of an overridable instance method, even while the Base constructor is running.

**Question 2.** `Child` has `private String text = "Java";`, and `Base()` calls an overridden `show()` that reads text. Why can text be null?

**Answer:** Child's instance field initializer runs after the superclass constructor completes; before then, the reference field has the default value null.

**Question 3.** If `text` is `final String` and assigned in `Child(...)`, does the compiler guarantee the override will not read null when the Base constructor calls early?

**Answer:** No. Definite assignment ensures that a normally completing constructor assigns the field, but it does not guarantee that mid-way virtual method calls observe only the final value.

**Question 4.** If the override calls `text.length()` while text is null, what happens?

**Answer:** It can throw `NullPointerException`, causing construction to abort abnormally before the Child constructor assigns the field.

**Question 5.** If the Base constructor calls private `prepare()`, and `prepare()` calls overridable `hook()`, is it safer just because `prepare` is private?

**Answer:** No. `hook()` can still dispatch to a subclass override before Child state is ready.

**Question 6.** Can `Base()` printing `System.out.println(this)` invoke the subclass `toString()`?

**Answer:** Yes. Converting an object to a string typically uses the runtime `toString()`, which can access uninitialized subclass state.

**Question 7.** Is changing `Child.field` to static an appropriate fix?

**Answer:** Usually no. That shifts state ownership to the class; you must fix the timing/lifecycle or pass appropriate constructor parameters instead of arbitrarily changing modifiers.

**Question 8.** Does calling a `private` method of Base from the Base constructor carry a risk of direct overriding?

**Answer:** A private method cannot be directly overridden by subclasses. However, its body must avoid indirect virtual dispatch, callbacks, and using unready state.

**Question 9.** Can `final void validate()` in Base be overridden by Child?

**Answer:** No. However, if the final method calls another overridable method, the risk can still occur.

**Question 10.** If `Child` is a `final class`, can there be a subclass `GrandChild extends Child` to which a hook in the Child constructor dispatches?

**Answer:** No; a final class prevents inheritance. Nevertheless, other initialization/lifecycle issues must not be ignored for that reason.

**Question 11.** Which approach is appropriate when a superclass needs a caller-supplied name: asking the subclass via an overridable `getName()` in the superclass constructor, or passing `name` to `super(name)`?

**Answer:** Passing the constructor parameter `name` to `super(name)`. The superclass can validate/assign its state directly without depending on an unready subclass.

**Question 12.** If an overriding method needs a dependency injected by the Child constructor, when is it safer to call that method?

**Answer:** After `new Child(...)` completes successfully, through an operation/lifecycle with a clear contract that guarantees the dependency is ready.

**Question 13.** Does calling an overridable hook at the end of an intermediate class's constructor guarantee that all deeper subclasses are initialized?

**Answer:** No. The constructors/initializers of deeper subclasses still have not run.

**Question 14.** What kind of object is `this` inside a Base constructor while creating a Child object?

**Answer:** It refers to the object of runtime type Child currently being constructed, not a separate Parent/Base object.

**Question 15.** Does Java allowing an overriding method to run early mean Java picks the Parent implementation first and switches to Child later?

**Answer:** No. Dynamic dispatch is based on the runtime class; the Child implementation can be selected immediately—only **the state changes according to initialization order**.

**Question 16.** Can a final method call an abstract hook?

**Answer:** Yes; final only prevents overriding that method itself. If a final method is called in a constructor and invokes an abstract hook, the early dispatch risk still exists.

**Question 17.** Is putting `this` into a registry from a constructor before assigning final fields dangerous?

**Answer:** Yes. The object can be observed before it is completely built; Java Memory Model final-field guarantees are not unconditional guarantees in a this escape situation.

**Question 18.** Why is calling `render()` after `new TextComponent(...)` better than calling it inside `Component()`?

**Answer:** When the caller invokes it after construction, TextComponent's field initializers and constructor body have already run successfully; the override can rely on established state.

## 29. Checklist when designing or reviewing constructors with inheritance

1. **Does the superclass constructor call any instance methods?** If so, can any of them be overridden?
2. **Are there indirect call paths?** Inspect private helpers, loggers, formatters, `toString()`, event buses, and callbacks.
3. **Does any superclass field initializer or instance initializer call a hook?** It has the same timing issue.
4. **Is the runtime subclass state ready yet?** Inside a superclass constructor, usually **not yet**.
5. **Are there deeper subclasses?** A hook called at the end of an intermediate class's constructor can still dispatch to an incomplete object.
6. **Does it read a subclass blank final field?** It may still hold a default value during an early call.
7. **Is there a non-final field initializer `= ...` in Child?** It has not run before the superclass constructor.
8. **Does any method dereference an uninitialized String/List/dependency?** Watch for NPE risks.
9. **Are there side effects when a hook runs early?** Side effects can persist even if construction fails.
10. **Does it cause `this` escape?** Do not register observers, threads, registries, or callbacks before construction finishes.
11. **What data does the superclass need immediately?** Prefer constructor parameters and helpers that do not depend on subclass instance state.
12. **What behavior does the subclass need to execute after creation?** Separate it into a post-construction method/lifecycle.
13. **Should the orchestration method be final?** A final template method is useful to protect the protocol; invoke hooks only after construction.
14. **Can a final concrete class/record/composition be used?** Only when it fits the API and extension requirements.
15. **Is there a custom framework lifecycle?** Verify the exact timing of injection/proxies/callbacks.
16. **Is there thread concurrency?** Distinguish constructor completion, safe publication, and synchronization for mutable state.
17. **Do the examples/files run properly on Java 17?** Check public class names, packages, compile commands, stdout, and comments on intentionally broken lines.
18. **When fixing the bug, was the early polymorphic call actually removed?** Do not merely hide it with a null-check or change fields to static/final.

## 30. Conclusion

When a superclass constructor executes during `new Subclass()`, **the object has runtime type Subclass from the very beginning**, so **overridable instance method calls can still dispatch to the subclass implementation**. However, the subclass's instance field initializers and constructor body **have not yet completed**, so the override may see `null`, `0`, `false`, or unready dependencies. `final` fields and inline declaration initializers do not automatically eliminate this problem.

A durable design **avoids calling overridable methods from constructors or from initializers that run before subclass initialization**; it also avoids indirect call paths and premature publication of `this`. **Pass required data through constructors**, validate state inside non-overridable helpers when appropriate, and reserve polymorphic hooks for **methods/lifecycles invoked after the object has initialized successfully**. This preserves the power of inheritance and dynamic dispatch without sacrificing the correctness of object creation.
