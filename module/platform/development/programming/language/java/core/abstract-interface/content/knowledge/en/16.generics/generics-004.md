# Bounding Generic Types with Abstract Classes and Interfaces

## 1. Why Do We Need Type Bounds?

Without a bound, a type parameter T can represent many different reference types. The compiler only allows calling methods guaranteed by the known type. If an algorithm needs to retrieve an ID, an arbitrary T does not provide enough information:

~~~java
static <T> String idOf(T value) {
    // value.id() does not compile: T is not guaranteed to have id().
    return value.toString();
}
~~~

Declaring a bound tells the compiler which types are accepted and which members can be called safely. Java uses the **extends** keyword for both class and interface bounds.

## 2. Bounding with an Abstract Class

Use an abstract class as a bound when the algorithm genuinely needs shared state or behavior within an inheritance hierarchy:

~~~java
abstract class NamedEntity {
    private final String name;

    protected NamedEntity(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }

    public abstract String category();
}

static <T extends NamedEntity> String labelOf(T value) {
    return value.name() + " (" + value.category() + ")";
}
~~~

With **T extends NamedEntity**, every valid type argument must be NamedEntity or a valid subclass of it. Therefore, labelOf can call name() and category() without casting. NamedEntity cannot be instantiated directly because it is abstract; a concrete class must provide category() before an object can be created.

A class bound is appropriate when the base class represents a true inheritance relationship. As a trade-off, Java allows only one direct superclass, so a class bound can exclude types that do not belong to that hierarchy.

## 3. Bounding with an Interface

If an algorithm only requires a capability, an interface is usually a more flexible bound:

~~~java
interface Identifiable {
    String id();
}

static <T extends Identifiable> String idOf(T value) {
    return value.id();
}
~~~

Any class that implements Identifiable can be passed to idOf, even if those classes extend different superclasses. The bound describes the capability the algorithm requires instead of forcing all objects to share a common superclass.

**Syntax to distinguish:** `class Account extends NamedEntity implements Identifiable` specifies the superclass and the interface that `Account` commits to implementing; the concrete class must also have a valid constructor and implement the required abstract methods. In `<T extends Identifiable>` of a generic method, `extends` sets the bound for T, even though `Identifiable` is an interface. Writing **&lt;T implements Identifiable&gt;** is a syntax error. The runnable example in section 5 shows both places.

## 4. Combining a Class Bound and an Interface Bound

A type parameter can require a type to both belong to a class hierarchy and implement an interface:

~~~java
abstract class NamedEntity {
    public abstract String name();
}

interface Identifiable {
    String id();
}

static <T extends NamedEntity & Identifiable> String describe(T value) {
    return value.name() + ", id=" + value.id();
}
~~~

If a class bound is present, it must come first; interfaces follow and are separated by &. At most one class bound is allowed. Details on multiple interfaces, intersection types, and intersection casts belong to the next lesson; here, you need to understand that T must satisfy all stated bounds.

## 5. Complete Example

Save the code to **TypeBoundsDemo.java**:

~~~java
abstract class NamedEntity {
    private final String name;

    protected NamedEntity(String name) {
        this.name = name;
    }

    public final String name() {
        return name;
    }
}

interface Identifiable {
    String id();
}

final class Account extends NamedEntity implements Identifiable {
    private final String id;

    Account(String name, String id) {
        super(name);
        this.id = id;
    }

    @Override
    public String id() {
        return id;
    }
}

public class TypeBoundsDemo {
    static <T extends NamedEntity & Identifiable> String describe(T value) {
        return value.name() + ", id=" + value.id();
    }

    static <T extends Identifiable> String idOf(T value) {
        return value.id();
    }

    public static void main(String[] args) {
        Account account = new Account("Lan", "U-17");
        System.out.println(describe(account));
        System.out.println(idOf(account));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac TypeBoundsDemo.java
java TypeBoundsDemo
~~~

Output:

~~~text
Lan, id=U-17
U-17
~~~

Account extends NamedEntity and implements Identifiable, so it satisfies both bounds of describe. idOf only needs Identifiable, so it can accept types that do not extend NamedEntity. Set bounds according to the exact operations the method needs to call.

## 6. Type Bounds Differ from Wildcard Bounds

~~~java
static <T extends Identifiable> T requireId(T value) {
    return value;
}

static void printIds(java.util.List<? extends Identifiable> values) {
    for (Identifiable value : values) {
        System.out.println(value.id());
    }
}
~~~

**&lt;T extends Identifiable&gt;** names T to link multiple positions in the signature, such as the input and the return type. **? extends Identifiable** describes an unknown element type that can be read as Identifiable. Wildcards fit data-reading APIs; named type parameters are useful when you need to preserve type relationships between positions. The lesson on invariance and wildcards presents this choice in greater detail.

## 7. Common Mistakes

- Using **implements** in a bound instead of **extends**.
- Placing an interface before a class bound, for example **&lt;T extends Identifiable & NamedEntity&gt;** when NamedEntity is a class.
- Declaring two class bounds for the same T.
- Calling a method specific to an implementing class when the bound does not guarantee that method exists.
- Setting a bound too narrow and excluding usable types, or too wide so the compiler does not allow calling the required operations.

Type erasure uses the first bound to determine the erased type of a type variable; this does not discard the remaining constraints at compile time. The lesson on type erasure explains the bytecode/runtime consequences.
