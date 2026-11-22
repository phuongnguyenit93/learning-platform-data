# Inheriting and Forwarding Type Parameters in Java Generics

When designing a system of generic classes and interfaces, you often do not just write `class Box<T>` and use `Box<String>` directly. A subclass can **preserve the superclass's type parameter**, **fix a type argument**, **swap the positions of type arguments**, or **construct a nested generic type** to pass upward. Similarly, a generic interface can be extended by another interface or implemented by a class with an appropriate type argument.

This is what **generic inheritance / forwarding type parameters** means: Java's subtyping rules must go hand in hand with consistent type substitutions. This article explains how to read those relationships, why you must not equate `Parent<ChildType>` with `Parent<ParentType>`, how to override after a type argument has been specialized, and common errors caused by type erasure.

All complete programs use **Java 17+**. Each example has a public class saved in a file of the same name; snippets that only illustrate signatures will be noted separately.

## 1. Quick Review: Type Parameter and Type Argument Are Not the Same

Consider two declarations:

```java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

class StringBox extends Box<String> {
    StringBox(String value) {
        super(value);
    }
}
```

These are valid Java declarations, though without a `main` method yet.

- `T` in `Box<T>` is a **type parameter** declared by class `Box`.
- `String` in `Box<String>` is a **type argument** passed to `Box` when declaring the superclass of `StringBox`.
- `StringBox` **does not declare** a type parameter of its own; it inherits from a specific parameterization of `Box`.
- In source code, `StringBox.get()` is treated by the compiler as returning `String` because `T` of `Box` has been bound to `String`.
- Java still creates a superclass/subclass with ordinary runtime semantics; generic type arguments do not create a new JVM class variant.

Read `extends Box<String>` as: "the current class is a subtype of `Box` with type argument `String`". Do not read `<String>` as "declaring a type parameter String".

## 2. Core Rule of Forwarding

A subclass **can declare a new type parameter** and use it as a type argument for its parent:

```java
class Parent<T> {
    T value;
}

class Child<U> extends Parent<U> {
}
```

Here:

1. `Parent<T>` declares type variable `T`.
2. `Child<U>` declares its **own** type variable `U`.
3. `extends Parent<U>` passes `Child`'s `U` as a **type argument** to parameterize `Parent<T>`.
4. For `Child<String>`, the inherited type is `Parent<String>`. Therefore, `Parent`'s field `value` has static type `String` when accessed through an appropriate reference.

You can also write `class Child<T> extends Parent<T>`. In that case, the two `T`s belong to **two different declarations**, and the `extends Parent<T>` clause maps the parent's type parameter to the child's type parameter. Using the same name is just a convention, whereas **the relationship resides in the `extends` clause**.

A way to verify using a table:

| Declaration | Who owns the type parameter? | Mapping in the extends clause |
| --- | --- | --- |
| `Parent<T>` | `Parent` owns `T` | No mapping yet |
| `Child<U>` | `Child` owns `U` | `Parent.T ← Child.U` |
| `Child<String>` | Uses `String` as Child's argument | Infers `Parent.T = String` |
| `Child<Integer>` | Uses `Integer` as Child's argument | Infers `Parent.T = Integer` |

The compiler applies this mapping across all fields, methods, and interfaces of the superclass. If the superclass has `T get()`, then a `Child<String>` has an inherited method that callers use as returning `String`.

## 3. Forwarding a Type Parameter Directly: Runnable Example

Create the file `ForwardingDemo.java`:

```java
public class ForwardingDemo {
    static class Storage<T> {
        private T value;

        Storage(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        void set(T value) {
            this.value = value;
        }
    }

    static final class AuditedStorage<E> extends Storage<E> {
        private int updates;

        AuditedStorage(E value) {
            super(value);
        }

        @Override
        void set(E value) {
            super.set(value);
            updates++;
        }

        int updates() {
            return updates;
        }
    }

    public static void main(String[] args) {
        AuditedStorage<String> names = new AuditedStorage<>("An");
        names.set("Binh");

        String name = names.get();
        Storage<String> baseView = names;

        System.out.println(name);
        System.out.println(baseView.get());
        System.out.println(names.updates());
    }
}
```

Compile and run:

```bash
javac ForwardingDemo.java
java ForwardingDemo
```

`stdout` output:

```text
Binh
Binh
1
```

Key points:

- `Storage<T>` declares the type contract for `value`, `get()`, and `set(T)`.
- `AuditedStorage<E>` declares its own type `E` and **forwards** it into `Storage<E>`.
- With `AuditedStorage<String>`, the compiler sees `get()` returning `String` and `set(...)` accepting `String`.
- `@Override void set(E value)` continues to follow the parent's contract with the applied type argument.
- `Storage<String> baseView = names` is valid: a subtype can be upcast to a **supertype with the same parameterization**.
- If you write `names.set(123)`, compilation fails because `String` is required.

Note: generic inheritance does not mean the parent's constructors are automatically inherited. The constructor `AuditedStorage(E)` calls `super(value)` to initialize the parent's state. `Storage<T>` can define its own constructors and generic methods; those two concepts do not replace each other.

## 4. Distinguishing Forwarding from Fixing a Type Argument

A subclass **does not have to** be generic. If it is always dedicated to handling strings, instead of declaring `<U>` and passing `U` to the parent, it can fix the type argument once:

```java
// Assuming Storage<T> has constructor Storage(T) and T get() as in section 3.
class TextStorage extends Storage<String> {
    TextStorage(String initial) {
        super(initial);
    }
}
```

With `TextStorage`, the inherited type is `Storage<String>`; `get()` returns String at the source level. Conversely, `AuditedStorage<E> extends Storage<E>` in section 3 keeps E so that each use of `AuditedStorage<String>` or `AuditedStorage<Integer>` has its own contract.

The difference should be read directly from the inheritance clause: `Storage<String>` is a **fixed type**, whereas `Storage<E>` is **forwarding a type parameter**. The subclass constructor still needs to initialize the superclass part via `super(initial)` if the parent has no suitable no-argument constructor. Inheritance does not automatically generate new constructors.

This article uses those two forms to compare the *forwarding* mechanism; when you need to design a specialized fixed-type class yourself, identify what real behavior/domain invariant it carries rather than creating a subclass just to rename `Storage<String>`.

## 5. Transforming a Type Argument When Passing It to the Superclass

A subclass can use its own type parameter inside a **parameterized type** passed to the parent:

```java
class Parent<T> {
    T value;
}

class Group<E> extends Parent<java.util.List<E>> {
}
```

The mapping is no longer `Parent.T ← E` but **`Parent.T ← List<E>`**.

With `Group<String>`, the inherited type is `Parent<List<String>>`. Therefore, the parent's field `value` has static type `List<String>`, not `String`.

Create `NestedForwardingDemo.java`:

```java
import java.util.List;

public class NestedForwardingDemo {
    static class Container<T> {
        private final T data;

        Container(T data) {
            this.data = data;
        }

        T get() {
            return data;
        }
    }

    static final class Batch<E> extends Container<List<E>> {
        Batch(List<E> items) {
            super(List.copyOf(items));
        }

        int count() {
            return get().size();
        }
    }

    public static void main(String[] args) {
        Batch<String> batch = new Batch<>(List.of("A", "B"));

        List<String> items = batch.get();
        Container<List<String>> base = batch;

        System.out.println(items);
        System.out.println(batch.count());
        System.out.println(base.get().get(0));
    }
}
```

Run:

```bash
javac NestedForwardingDemo.java
java NestedForwardingDemo
```

`stdout`:

```text
[A, B]
2
A
```

Analysis:

1. `Batch<E>` owns `E`.
2. `extends Container<List<E>>` uses the entire `List<E>` type as the type argument for `Container<T>`.
3. With `Batch<String>`, the compiler infers `Container<List<String>>`.
4. `get()` therefore has return type `List<String>`; only then can the caller chain `get(0)` to obtain a `String`.
5. `List.copyOf` makes the component list unmodifiable and rejects null elements; this is an implementation choice of `Batch`, **not** an automatic rule of generic inheritance.

How to read nested types: **start at the parent type parameter, substitute the passed type argument expression, and then continue substituting each parameter of the child**.

## 6. Multiple Type Parameters: Forwarding, Swapping, and Partial Fixing

With a parent type `Pair<K,V>`, a subclass has several ways to supply type arguments:

```java
class Pair<K, V> {
    K key;
    V value;
}

// Keep the same order but use different names:
class Same<A, B> extends Pair<A, B> {
}

// Swap positions:
class Swapped<X, Y> extends Pair<Y, X> {
}

// Fix key to String, leaving only value generic:
class NamedValue<T> extends Pair<String, T> {
}

// Wrap value into a list:
class MultiValue<T> extends Pair<String, java.util.List<T>> {
}
```

These are illustrative declarations, without separate constructors or `main`.

Mapping table:

| Subclass | Type arguments applied to `Pair<K,V>` |
| --- | --- |
| `Same<Integer,String>` | `K=Integer`, `V=String` |
| `Swapped<Integer,String>` | `K=String`, `V=Integer` |
| `NamedValue<Double>` | `K=String`, `V=Double` |
| `MultiValue<Long>` | `K=String`, `V=List<Long>` |

The **swapping** lies in `extends Pair<Y,X>`, not in the names `X` or `Y`. Do not assume `K` is always "the subclass's first type parameter": the order and expressions written in the type argument list are what decide.

### Complete Example of Swapping Type Arguments

Create `SwappedDemo.java`:

```java
public class SwappedDemo {
    static class Pair<K, V> {
        private final K key;
        private final V value;

        Pair(K key, V value) {
            this.key = key;
            this.value = value;
        }

        K key() {
            return key;
        }

        V value() {
            return value;
        }
    }

    static final class Swapped<X, Y> extends Pair<Y, X> {
        Swapped(Y key, X value) {
            super(key, value);
        }
    }

    public static void main(String[] args) {
        Swapped<Integer, String> item =
                new Swapped<>("code", 42);

        String key = item.key();
        Integer value = item.value();

        System.out.println(key);
        System.out.println(value);
    }
}
```

Run `javac SwappedDemo.java` and `java SwappedDemo`:

```text
code
42
```

In `Swapped<Integer,String>`, `X=Integer` and `Y=String`. Because of `extends Pair<Y,X>`, the inherited method `key()` returns `String` and `value()` returns `Integer`. Writing the constructor as `Swapped(Y key, X value)` is one way to stay consistent with the mapping; in real APIs, a name like `Swapped` should only be used when the semantic order has a clear reason.

## 7. Multi-Level Inheritance Chains: Composing Mappings Bottom-Up

When there are three levels, you must compose the type substitutions. Consider:

```java
class Base<A> {
}

class Middle<B> extends Base<java.util.List<B>> {
}

class Leaf<C> extends Middle<C> {
}
```

For `Leaf<String>`:

1. `Leaf.C = String`.
2. `Leaf<C> extends Middle<C>` → `Middle.B = String`.
3. `Middle<B> extends Base<List<B>>` → `Base.A = List<String>`.
4. `Leaf<String>` is therefore a subtype of `Middle<String>` **and** `Base<List<String>>`.

If the next level fixes `C=Integer`, that non-generic class will be a subtype of `Base<List<Integer>>`.

### Runnable Three-Level Program

Create `InheritanceChainDemo.java`:

```java
import java.util.List;

public class InheritanceChainDemo {
    static class Base<T> {
        private final T value;

        Base(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static class Middle<E> extends Base<List<E>> {
        Middle(List<E> value) {
            super(List.copyOf(value));
        }
    }

    static final class Leaf<X> extends Middle<X> {
        Leaf(List<X> value) {
            super(value);
        }
    }

    public static void main(String[] args) {
        Leaf<String> leaf = new Leaf<>(List.of("one", "two"));
        Middle<String> middle = leaf;
        Base<List<String>> base = leaf;

        System.out.println(leaf.get());
        System.out.println(middle.get().size());
        System.out.println(base.get().get(1));
    }
}
```

Run:

```bash
javac InheritanceChainDemo.java
java InheritanceChainDemo
```

`stdout`:

```text
[one, two]
2
two
```

Code-reading tip: draw a chain `Leaf<X> → Middle<X> → Base<List<X>>`; then substitute `X=String`. Do not jump straight from `Leaf<String>` to `Base<String>` — that is a wrong conclusion because the `Middle` layer wraps the type argument in `List`.

## 8. How Are Generic Interfaces Extended and Forwarded?

Java allows an interface to extend another generic interface. It can keep the parameter as-is, fix the parameter, or transform it into another type expression.

```java
interface Source<T> {
    T read();
}

interface MutableSource<E> extends Source<E> {
    void write(E value);
}

interface TextSource extends Source<String> {
}

interface BatchSource<E> extends Source<java.util.List<E>> {
}
```

Meaning:

- `MutableSource<Integer>` is a subtype of `Source<Integer>`; `read()` returns `Integer` and `write(...)` takes `Integer`.
- `TextSource` is not generic, yet every implementation of it must satisfy `Source<String>`.
- `BatchSource<Double>` is a subtype of `Source<List<Double>>`, because `E` is wrapped into `List<E>` before being forwarded.

Note: an interface inherits from another interface using `extends`, not `implements`. Only a class uses `implements` when implementing an interface.

### Multi-Level Interface and Implementation Example

Create `InterfaceForwardingDemo.java`:

```java
public class InterfaceForwardingDemo {
    interface Reader<T> {
        T read();
    }

    interface NamedReader<T> extends Reader<T> {
        String name();
    }

    static final class IntReader implements NamedReader<Integer> {
        @Override
        public Integer read() {
            return 7;
        }

        @Override
        public String name() {
            return "counter";
        }
    }

    static <T> void print(Reader<T> reader) {
        System.out.println(reader.read());
    }

    public static void main(String[] args) {
        IntReader reader = new IntReader();
        Reader<Integer> general = reader;

        System.out.println(reader.name());
        print(general);
    }
}
```

Run `javac InterfaceForwardingDemo.java` then `java InterfaceForwardingDemo`:

```text
counter
7
```

The type mapping flow is `IntReader implements NamedReader<Integer> extends Reader<Integer>`. Method `read()` has return type `Integer` in the implementation and when accessed through `Reader<Integer>`.

## 9. Generic Class Implementing a Generic Interface and Extending a Generic Class

A class can both extend a superclass and implement an interface, using **the same type parameter** to guarantee a consistent type relationship across both branches.

Create `RepositoryDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class RepositoryDemo {
    interface Repository<T> {
        void add(T value);
        List<T> all();
    }

    static class Named<T> {
        private final String name;

        Named(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }
    }

    static final class MemoryRepository<E>
            extends Named<E> implements Repository<E> {

        private final List<E> values = new ArrayList<>();

        MemoryRepository(String name) {
            super(name);
        }

        @Override
        public void add(E value) {
            values.add(value);
        }

        @Override
        public List<E> all() {
            return List.copyOf(values);
        }
    }

    public static void main(String[] args) {
        MemoryRepository<String> repo =
                new MemoryRepository<>("languages");

        repo.add("Java");
        repo.add("Kotlin");

        Repository<String> api = repo;

        System.out.println(repo.name());
        System.out.println(api.all());
    }
}
```

Run:

```bash
javac RepositoryDemo.java
java RepositoryDemo
```

`stdout`:

```text
languages
[Java, Kotlin]
```

`MemoryRepository<E>` declares a single type variable `E`. It is used in **two places**: `extends Named<E>` and `implements Repository<E>`. Thus, when creating `MemoryRepository<String>`, both the inheritance contract and the interface contract use `String`. `List.copyOf` in `all()` is an implementation decision to return an unmodifiable snapshot; the type parameter `E` itself does not enforce immutability or any null policy.

A class can also forward different type arguments to the superclass and the interface if the design requires it—for instance, one type for keys and one type for data—as long as method signatures are compatible and do not create an inheritance conflict.

## 10. Type Parameter Bounds When Forwarding

If a superclass requires its type parameter to satisfy an **upper bound**, the subclass must supply a type argument meeting that bound at the `extends` declaration.

Example:

```java
class NumericBox<N extends Number> {
    private final N number;

    NumericBox(N number) {
        this.number = number;
    }

    double asDouble() {
        return number.doubleValue();
    }
}
```

A valid forwarding subclass:

```java
class Measured<T extends Number> extends NumericBox<T> {
    Measured(T number) {
        super(number);
    }
}
```

`T extends Number` on `Measured` guarantees that every type argument of `Measured<T>` satisfies `NumericBox`'s requirement `N extends Number`. You cannot write a general subclass `class Bad<T> extends NumericBox<T>` if `Bad`'s `T` lacks an appropriate bound: the compiler cannot prove that every `T` satisfies `Number`.

### Complete Example

Create `BoundedInheritanceDemo.java`:

```java
public class BoundedInheritanceDemo {
    static class NumericBox<N extends Number> {
        private final N number;

        NumericBox(N number) {
            this.number = number;
        }

        double twice() {
            return number.doubleValue() * 2;
        }
    }

    static final class Measured<T extends Number>
            extends NumericBox<T> {
        Measured(T value) {
            super(value);
        }
    }

    public static void main(String[] args) {
        Measured<Integer> items = new Measured<>(5);
        Measured<Double> weight = new Measured<>(1.25);

        System.out.println(items.twice());
        System.out.println(weight.twice());
    }
}
```

Run `javac BoundedInheritanceDemo.java` and `java BoundedInheritanceDemo`:

```text
10.0
2.5
```

Bounds **do not need to be written character-for-character identically**, but the type argument must actually satisfy all relevant constraints. A subclass can use a **narrower** bound if needed, provided it satisfies the superclass bound. For example, `<T extends Integer>` is valid even though `Integer` is a `final` class: since there are no subclasses of `Integer`, `T` can only be `Integer`. However, when generalization is unnecessary, using `Integer` directly is usually clearer. With interface bounds, multiple contracts can be combined with `&` when needed.

### Inheriting a Type Whose Bound Is Already Fixed

`class IntegerBox extends NumericBox<Integer>` is valid, because `Integer` extends `Number`. This class does not need to declare its own type variable if the goal is only to use `Integer`.

## 11. Overriding Methods When T Has Been Applied

When a superclass declares a method using type parameter `T`, the subclass must override **the exact type contract after applying the type argument**.

Create `OverrideGenericDemo.java`:

```java
public class OverrideGenericDemo {
    static class Formatter<T> {
        String format(T value) {
            return "base:" + value;
        }
    }

    static final class IntegerFormatter extends Formatter<Integer> {
        @Override
        String format(Integer value) {
            return "int:" + value;
        }
    }

    public static void main(String[] args) {
        Formatter<Integer> format = new IntegerFormatter();

        System.out.println(format.format(12));
    }
}
```

Run:

```bash
javac OverrideGenericDemo.java
java OverrideGenericDemo
```

`stdout`:

```text
int:12
```

- `Formatter<T>` declares `format(T)`.
- `IntegerFormatter extends Formatter<Integer>` specializes `T = Integer`.
- `format(Integer)` is a valid override at the source level. Using `@Override` helps the compiler detect incompatible signatures.
- The variable `Formatter<Integer>` holds an `IntegerFormatter` object, so dynamic dispatch invokes the subclass's implementation.

**Common mistake:** writing `format(Object)` in `IntegerFormatter` and thinking it definitely overrides `format(T)` after erasure. At the source level, when the superclass is viewed as `Formatter<Integer>`, the signature to satisfy is `format(Integer)`; an additional `format(Object)` declaration may not override as the author expects, and can even cause a name clash depending on the signature. Always use `@Override` and let the compiler verify rather than guessing from erased bytecode.

### Return Types Are Also Specialized

If the superclass has `T get()` and the subclass extends `Parent<String>`, the subclass can override with `String get()`. If a generic method or superclass contract has another return type, Java permits covariant returns according to applicable override rules, but incompatible return types are not allowed.

For example, `Object get()` is not a valid override of `String get()` when the subtype's contract requires returning `String`; the return type is widened in the wrong direction.

## 12. Bridge Methods: Why Does the JVM Still Call the Right Override After Erasure?

This section explains the mechanism behind the scenes and is not required for writing everyday generic classes.

In source code, `Formatter<T>.format(T)` is specialized in the subclass to `format(Integer)`. After **type erasure**, the superclass's method looks closer to `format(Object)` in bytecode, while the method written by the subclass accepts `Integer`. To preserve the override/dynamic dispatch relationship, the compiler can generate a synthetic **bridge method** `format(Object)` in the subclass that performs a cast and delegates the call to `format(Integer)`.

From Java source code, you simply override with the exact type. You should not write bridge methods manually.

### Observing a Bridge Method via Reflection

Create `BridgeMethodDemo.java`:

```java
import java.lang.reflect.Method;

public class BridgeMethodDemo {
    static class Parent<T> {
        T echo(T input) {
            return input;
        }
    }

    static final class Child extends Parent<String> {
        @Override
        String echo(String input) {
            return input.toUpperCase();
        }
    }

    public static void main(String[] args) {
        Parent<String> view = new Child();
        System.out.println(view.echo("java"));

        boolean bridgeFound = false;
        for (Method method : Child.class.getDeclaredMethods()) {
            if (method.getName().equals("echo") && method.isBridge()) {
                bridgeFound = true;
            }
        }
        System.out.println(bridgeFound);
    }
}
```

Run:

```bash
javac BridgeMethodDemo.java
java BridgeMethodDemo
```

`stdout` with `javac` from JDK 17:

```text
JAVA
true
```

`Child` overrides `echo(String)`. In the subclass bytecode generated by `javac`, the bridge `echo(Object)` preserves proper dispatch through a `Parent<String>` reference. Use `isBridge()` to recognize compiler-generated methods; the example prints only a boolean to avoid depending on the return order of `getDeclaredMethods()`.

If you want to inspect manually, you can run `javap -p -c BridgeMethodDemo$Child` in an appropriate shell environment; how to quote class names containing `$` depends on your shell. Bridges are a consequence of erasure, not a new type parameter to forward in source code.

## 13. Generic Methods with Their Own Type Parameter: Do Not Confuse with Inherited T

A generic class can inherit a type parameter from its parent **and** declare independent generic methods.

```java
class Repository<T> {
    T get() {
        return null;
    }

    <R> R convert(java.util.function.Function<? super T, ? extends R> fn) {
        return fn.apply(get());
    }
}
```

Here:

- `T` belongs to the class and is fixed when a subclass extends `Repository<String>`.
- `R` belongs specifically to the `convert` method. Each call site can infer a different type `R`.
- `Function<? super T, ? extends R>` connects the stored data `T` to the result type `R`.
- If the subclass is `StringRepository extends Repository<String>`, then `convert(String::length)` can return `Integer`, even though the subclass is not generic.

**Do not redeclare `<T>` on a method if you intend to use the class's T.** For example:

```java
class Box<T> {
    private T value;

    // <T> void set(T x) { value = x; } // Method's T shadows the class's T.
    void set(T x) {
        value = x;
    }
}
```

This situation involves **scope/shadowing**, not forwarding type parameters between parent and child. Still, it frequently shows up in the same codebase and needs to be distinguished.

## 14. Forwarding Type Arguments Does Not Make Generics Covariant

When declaring `Child<T> extends Parent<T>`, `Child<Integer>` is a subtype of **`Parent<Integer>`**. It does not automatically become a subtype of `Parent<Number>` just because `Integer` extends `Number`: parameterizations of the same generic type are **invariant** by default.

```java
class Parent<T> {}
class Child<T> extends Parent<T> {}

// Inside a method:
Child<Integer> child = new Child<>();
Parent<Integer> exact = child;
Parent<? extends Number> readView = child;
// Parent<Number> wrong = child; // Invalid.
```

`Parent<? extends Number>` is suitable for an API that **observes** a `Number` value if `Parent` has a getter returning `T`, but does not allow arbitrarily writing a `Number` into a slot whose actual element type is unknown. Do not use raw types or unchecked casts to turn `Parent<Integer>` into `Parent<Number>`: doing so breaks the type safety that forwarding just preserved.

## 15. Cannot Inherit the Same Generic Interface with Two Incompatible Arguments

A class cannot simultaneously become a subtype of **the same generic interface** with two different type arguments through two inheritance paths.

Intentionally invalid example:

```java
interface Consumer<T> {
    void accept(T item);
}

class TextConsumer implements Consumer<String> {
    public void accept(String item) {}
}

// Invalid: one path inherits Consumer<String>,
// the other requires Consumer<Integer>.
// class Bad extends TextConsumer implements Consumer<Integer> {
//     public void accept(Integer item) {}
// }
```

The snippet has a valid `TextConsumer` declaration, while `Bad` is commented out because it causes a compile error. A subtype cannot have two distinct instantiations of the same generic interface in its supertype hierarchy at the same time.

Another form of conflict:

```java
interface StringSource extends java.util.function.Supplier<String> {}
interface IntegerSource extends java.util.function.Supplier<Integer> {}

// Invalid:
// class Both implements StringSource, IntegerSource {
//     ...
// }
```

Even if you could write separate methods accepting or returning different kinds of data, the two branches `Supplier<String>` and `Supplier<Integer>` both describe the same generic interface inherited with different type arguments; Java rejects this.

Similarly, do not expect method overloads to distinguish two type arguments of the same raw generic type:

```java
// Invalid due to same erasure:
// void use(java.util.List<String> xs) {}
// void use(java.util.List<Integer> xs) {}
```

Both signatures erase to parameter type `List`, causing a name clash.

## 16. Type Erasure and Raw Types: Keeping Relationships at Compile Time

Generic inheritance is checked in source code, yet the JVM does not create separate classes like `ChildOfParentString` just because of `extends Parent<String>`. Java generics primarily use **type erasure**:

- Unbounded type parameters typically erase to `Object`.
- Bounded type parameters erase to their first bound.
- The compiler may insert casts and bridge methods.
- Type arguments may still appear as **generic declaration metadata**; that does not mean every instance carries fully checked type arguments at runtime.

### Avoid Extending a Raw Superclass

```java
class Box<T> {
    T value;
}

// Not recommended:
class RawChild extends Box {
}
```

The raw type `Box` loses `T`'s information in the subtype declaration. Operations on fields/methods can become weakly type-checked, emit warnings, and introduce `ClassCastException` at read sites.

Fix it using one of two approaches, depending on the desired API:

```java
class TypedChild<U> extends Box<U> {
}

class StringChild extends Box<String> {
}
```

- `TypedChild<U>` forwards `U`.
- `StringChild` fixes the type argument.
- Both preserve a type relationship that the compiler can verify.

Do not use `@SuppressWarnings("unchecked")` to hide warnings from a raw superclass if the real relationship can be expressed with type arguments.

### Runtime Boundaries

A `Parent<String>` variable does not strictly guarantee that data is always a `String` if raw aliases, unchecked casts, or unverified external sources are present. Generics protect most operations **when APIs adhere to static types**. For deserialized data or reflection, proper runtime validation is needed; type arguments are not a standalone business validation system.

## 17. Reflection: Inspecting Declared Superclass Type Arguments

Generic information in a **superclass declaration** can often be read via reflection, even though an object at runtime does not carry a separate specialized class for every type argument.

Create `GenericSuperclassDemo.java`:

```java
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;

public class GenericSuperclassDemo {
    static class Parent<T> {
    }

    static final class StringChild extends Parent<String> {
    }

    static class ForwardChild<U> extends Parent<U> {
    }

    public static void main(String[] args) {
        Type fixed = StringChild.class.getGenericSuperclass();
        Type forwarded = ForwardChild.class.getGenericSuperclass();

        System.out.println(fixed.getTypeName());
        System.out.println(forwarded.getTypeName());
        System.out.println(fixed instanceof ParameterizedType);
    }
}
```

Run:

```bash
javac GenericSuperclassDemo.java
java GenericSuperclassDemo
```

`stdout` on JDK 17, with nested classes as shown:

```text
GenericSuperclassDemo$Parent<java.lang.String>
GenericSuperclassDemo$Parent<U>
true
```

Explanation:

- `StringChild` explicitly writes superclass `Parent<String>`, so the generic superclass metadata reflects `String`.
- `ForwardChild<U>` passes a **type variable U** to `Parent`; the declaration's metadata represents `Parent<U>`.
- `getGenericSuperclass()` returns a `Type` descriptor; when it contains type arguments, it is typically a `ParameterizedType`.
- This reads the **declaration**, not runtime type arguments of every instance via `getClass()`.

For example, `new ForwardChild<String>().getClass()` returns `ForwardChild.class`. The `String` type is not stored as a new runtime subclass. If a framework needs to know type arguments across multiple inheritance levels, it must analyze generic metadata combined with mapping type variables across each level, or require explicit type information at runtime.

## 18. Common Generic Inheritance Patterns in Java Core

### 18.1. Generic Base + Specialized Subclass

Pattern:

```java
class Response<T> {
    // Holds T
}

class TextResponse extends Response<String> {
}
```

Suitable when the subtype `TextResponse` has specialized behavior, domain meaning, or invariants. If it adds no design value, you can use `Response<String>` directly to avoid an excess of classes.

### 18.2. Generic Base + Forwarding Generic Subclass

Pattern:

```java
class BaseRepository<ID, E> {
}

class CachedRepository<K, V> extends BaseRepository<K, V> {
}
```

`CachedRepository<Long,User>` becomes a subtype of `BaseRepository<Long,User>`. This pattern is useful when the subclass adds caching, logging, or instrumentation without **changing the data's type contract**.

### 18.3. Generic Interface + Fixed-Type Implementation

Pattern:

```java
interface Parser<T> {
    T parse(String input);
}

class IntegerParser implements Parser<Integer> {
    @Override
    public Integer parse(String input) {
        return Integer.parseInt(input);
    }
}
```

`Parser<Integer>` commits the method to returning `Integer`; the implementation can rely on `Integer.parseInt`. This is a clear way to reuse the same general interface for multiple result types.

### 18.4. Interface Inheritance That Transforms the Type Argument Structure

Pattern:

```java
interface Reader<T> {
    T read();
}

interface PageReader<T> extends Reader<java.util.List<T>> {
}
```

`PageReader<String>` is a `Reader<List<String>>`. Wrapping `List<T>` shifts the meaning of `read()` from "read a T" to "read a list of T", while still complying with the parent interface's generic contract.

### 18.5. Generic Inheritance with Multiple Bounds

Pattern:

```java
interface Named {
    String name();
}

class Registry<T extends Named> {
}

class SortedRegistry<U extends Named & Comparable<U>>
        extends Registry<U> {
}
```

The subclass adds the bound `Comparable<U>` while still satisfying the parent's `Named` requirement. Having a new bound does not turn the superclass into a different generic type; `Registry.T` is still mapped from `SortedRegistry.U`.

Do not add bounds merely to complicate signatures. A bound should serve an operation that the compiler needs to prove inside the subclass or API.

## 19. Common Mistakes and How to Fix Them

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Treating `class Child<T> extends Parent<T>` as using **the exact same T declaration** in both classes | Each class declares its own type variable; the `extends` clause creates a mapping | State `Parent.T ← Child.T` explicitly |
| Writing `class Child<T> extends Parent` | Uses a raw superclass, losing type relationships | Write `extends Parent<T>` or fix `Parent<String>` |
| Assuming `Child<String>` is always `Parent<String>` | The subclass may pass `List<T>` or swap positions | Read **type arguments in `extends`** |
| Assigning `Child<Integer>` to `Parent<Number>` | Generic invariance | Keep `Parent<Integer>` or use a `Parent<? extends Number>` view for reading only |
| Omitting the bound when forwarding to a bounded parent | Compiler cannot prove the subtype satisfies the bound | Declare `<T extends Number>` or a concrete type argument satisfying the bound |
| Overriding with `Object` thinking T was erased | Source-level override must match after applying type arguments | Use `@Override` with the specialized type |
| Thinking constructors are inherited like methods | Constructors are not inherited | Declare a subclass constructor and call `super(...)` |
| Expecting to implement the same generic interface with two different types | Two instantiations cannot simultaneously be inherited into the same subtype | Separate abstractions or design a consistent mapping |
| Thinking a generic class has a separate runtime class per T | Java generics use erasure | Distinguish compiler type arguments from runtime classes |
| Confusing a generic method's `<R>` with the class's `T` | The two type parameters belong to different scopes | Name them by role and track where they are declared |
| Unchecked casting to bypass inheritance errors | Can cause heap pollution and `ClassCastException` | Fix the `extends`/`implements` clause and type contract |
| Treating `List<Integer>` as a subtype of `List<Number>` because elements inherit | Generic invariance | Use wildcards according to read/write direction |

## 20. How to Analyze a Generic Inheritance Tree on Paper or in an IDE

When encountering a multi-level real-world class, follow six steps:

1. **List the type parameters at each declaration.** For example `Base<K,V>`, `Middle<T>`, `Leaf<E>`.
2. **Write down the exact expressions in `extends`/`implements`.** Do not simplify `List<E>` to `E` or reorder type arguments.
3. **Build the mapping from child to parent.** For instance, `Middle<T> extends Base<String,List<T>>` means `Base.K=String`, `Base.V=List<T>`.
4. **Apply the caller's type argument.** For `Leaf<Integer>`, deduce step by step up to `Base<String,List<Integer>>`.
5. **Check inherited methods and fields using the mapping.** A method `V get()` on `Base` returns `List<Integer>` on this `Leaf`, not `Integer`.
6. **Review override, bound, and runtime contracts.** A correct static return type is not enough: does the method have side effects, is null allowed, is the data mutable?

Example diagram:

```text
Base<K, V>
    ▲
    | extends Base<String, List<T>>
Middle<T>
    ▲
    | extends Middle<E>
Leaf<E>

Leaf<Integer>
    -> Middle<Integer>
    -> Base<String, List<Integer>>
```

If your IDE shows `Base<String,List<Integer>>` as a supertype of `Leaf<Integer>`, that is the exact result of layer-by-layer forwarding. You only need to trace the type argument expression along each edge to deduce it yourself without guessing.

## 21. Self-Check Exercises with Solutions

### Exercise 1 — Forwarding a Type Parameter Directly

Given:

```java
class P<T> {
    T get() { return null; }
}

class C<U> extends P<U> {
}
```

What type does `C<String>`'s `get()` return at compile time? Is it a subtype of `P<String>`?

**Answer:** `String`; yes, because `P.T ← C.U` and then `U=String`. Returning null in the illustrative body does not change the static type.

### Exercise 2 — Fixing a Type Argument

Given `class Text extends P<String> {}`. Is `Text` still a generic class, and can `P<Integer>` be used as a variable type pointing to `Text`?

**Answer:** `Text` is not generic; it extends `P<String>`. You cannot assign `Text` to `P<Integer>` because those generic instantiations are incompatible.

### Exercise 3 — Forwarding Type Expressions

```java
class Root<X> {}
class Middle<Y> extends Root<java.util.Map<String, Y>> {}
class End<Z> extends Middle<java.util.List<Z>> {}
```

Deduce the `Root` type of `End<Integer>`.

**Answer:** `End<Integer>` → `Middle<List<Integer>>` → `Root<Map<String,List<Integer>>>`. Do not drop the `List` layer from `End`'s mapping or the `Map` layer from `Middle`.

### Exercise 4 — Swapping Two Parameters

```java
class Pair<K,V> {}
class Flip<A,B> extends Pair<B,A> {}
```

Is `Flip<String,Long>` a subtype of `Pair<String,Long>` or `Pair<Long,String>`?

**Answer:** `Pair<Long,String>`, because `A=String`, `B=Long`, and then the parent is parameterized with `K=B=Long` and `V=A=String`.

### Exercise 5 — Interface Forwarding

```java
interface Source<T> { T read(); }
interface Many<E> extends Source<java.util.List<E>> {}
```

What is the return type of `Many<Double>.read()`?

**Answer:** `List<Double>`. Not `Double`, because `Source.T ← List<E>`.

### Exercise 6 — Bounds

```java
class Numeric<T extends Number> {}
// class GenericBad<U> extends Numeric<U> {}
class GenericGood<U extends Number> extends Numeric<U> {}
```

Why does `GenericBad` cause an error? Because `U` has no bound guaranteeing that `U` is a subtype of `Number`. `GenericGood` establishes that relationship in its declaration.

### Exercise 7 — Overriding

```java
class Base<T> {
    T echo(T x) { return x; }
}

class TextBase extends Base<String> {
    @Override
    String echo(String x) { return x.toUpperCase(); }
}
```

Why is the subclass method a valid override? Because the superclass has `T=String` applied. The compiler can generate a bridge method due to erasure to preserve runtime dispatch.

### Exercise 8 — Invariance

Given `class C<T> extends P<T> {}` and `C<Integer> c = ...`. Distinguish:

- `P<Integer> exact = c;` — **valid**.
- `P<Number> wider = c;` — **invalid**.
- `P<? extends Number> readable = c;` — **valid**.

Reason: the subtype relation to `P<Integer>` is declared directly, whereas `P<Number>` has no subtype relationship via generic arguments; an upper-bounded wildcard fits the data type of `c`.

### Exercise 9 — Design Exercise

Design `interface Loader<T> { T load(); }` and `class ListLoader<E> implements Loader<List<E>>`. Write an implementation storing a `List<E>` and returning a snapshot via `List.copyOf`. Test `ListLoader<String>` and verify that `Loader<List<String>>` is obtained. Explain which part comes from generic mapping and which part comes from choosing an immutable snapshot.

### Exercise 10 — Spotting Raw Types

Given `class Child extends Parent {}` where `Parent<T>` is generic. Write two ways to fix it:

1. `class Child<U> extends Parent<U>` — stay generic.
2. `class Child extends Parent<String>` — fix the type.

Explain why choosing which approach depends on the API contract, not because one syntax is always better.

## 22. Summary of Rules to Remember

- `class Child<U> extends Parent<U>`: **forwards** the child's type parameter to parameterize the parent.
- `class Child extends Parent<String>`: **fixes** the type argument on the superclass; the child does not have to be generic.
- `class Child<T> extends Parent<List<T>>`: **transforms the type argument expression**; for `Child<String>`, the parent type is `Parent<List<String>>`.
- `class Flip<A,B> extends Pair<B,A>`: **swaps** the parent's two type arguments.
- `interface Child<E> extends Parent<E>`: generic interfaces can also forward type parameters.
- `class Impl<E> implements Service<E>`: a class implements a generic interface according to the specified mapping.
- Across multiple levels, substitutions **compose**: read each `extends`/`implements` edge from subtype to supertype.
- Every bound of a supertype must be satisfied where the type argument is passed. `@Override` helps verify methods after specialization.
- `Child<Integer>` can be a `Parent<Integer>`, but **is not automatically a `Parent<Number>`**. Use wildcards when flexible read/write relationships need to be expressed.
- Java generics use erasure: type relationships are compile-time guarantees; bridge methods or casts can maintain runtime compatibility, rather than creating a specialized JVM class for each `T`.

Always ask yourself: **"Which class declares this type parameter, what expression is passed across the inheritance edge, and ultimately what types do the inherited methods have at the call site?"** Answering those three questions accurately lets you read, write, and verify a generic inheritance hierarchy in Java Core without relying on unsafe casts.