# Implementing Interfaces Using the Class's Type Parameters in Java Generics

## 1. Objective

Java allows a **generic class** to pass the type parameters declared by the class itself into a **generic interface** that it implements. This mechanism connects the interface's contract to how the class is used with each concrete type: when a class is used as Implementation<String>, the compiler knows it also implements Interface<String> if the class declares that relationship properly.

Foundational example:

~~~java
interface Store<T> {
    void save(T value);
    T load();
}

class MemoryStore<E> implements Store<E> {
    private E item;

    @Override
    public void save(E value) {
        item = value;
    }

    @Override
    public E load() {
        return item;
    }
}
~~~

In **MemoryStore<E>**, E is a *type parameter* declared by the class. In **implements Store<E>**, E is a *type argument* taken from the class's type parameter to fill the T position of Store<T>. These two positions use the same name E yet assume different syntactic roles. **implements does not declare a new type parameter**.

After this lesson, you should be able to explain and apply how to forward one or more type parameters through implements, write `@Override` with exact signatures, implement interfaces with fixed or mixed types, preserve generic relationships across extends, handle bounds, and avoid raw types, invalid wildcards, and conflicts caused by type erasure.

## 2. Syntax Pattern and Type Parameter Scope

Common syntax:

~~~java
interface Contract<T> {
    T process(T input);
}

class GenericImplementation<U> implements Contract<U> {
    @Override
    public U process(U input) {
        return input;
    }
}
~~~

Interpreting in order:

1. **interface Contract<T>** declares an interface type parameter T, using it for the input parameter and result.
2. **class GenericImplementation<U>** declares a new type parameter U, scoped to the implementing class.
3. **implements Contract<U>** supplies U for the type parameter T declared by Contract. Every use of GenericImplementation<String> simultaneously satisfies Contract<String>.
4. **public U process(U input)** implements the method contract after substituting the type argument; both input and output still keep the same U.
5. **@Override** forces the compiler to verify that the method genuinely overrides a supertype method; if the name, parameters, or type relationships are wrong, an error is detected at compile time.

There is no requirement that the type parameter names on the class and interface match: **Store<T>** and **MemoryStore<E>** use two different names yet are linked at **Store<E>**. You can also use **class MemoryStore<T> implements Store<T>** if you find it easier to read.

A general representation:

~~~text
interface InterfaceName<P> { ... }

class ClassName<Q> implements InterfaceName<Q> {
    // Methods are implemented in terms of Q.
}
~~~

The **<Q>** after ClassName is the *declaration site*; the **<Q>** after InterfaceName is the *use site*. With multiple types:

~~~text
class ClassName<K, V> implements InterfaceName<K, V> { ... }
~~~

Commas separate independent type parameters. Each type argument in implements must be valid for the corresponding position and bounds on the interface.

## 3. Standalone Runnable Example: Passing the Class's Type Parameter to the Interface

Save into **GenericImplementationDemo.java**:

~~~java
public class GenericImplementationDemo {
    interface Store<T> {
        void save(T value);
        T load();
    }

    static final class MemoryStore<E> implements Store<E> {
        private E item;

        @Override
        public void save(E value) {
            item = value;
        }

        @Override
        public E load() {
            return item;
        }
    }

    interface Converter<I, O> {
        O convert(I input);
    }

    static final class LabelConverter<T>
            implements Converter<T, String> {
        @Override
        public String convert(T input) {
            return "value=" + input;
        }
    }

    public static void main(String[] args) {
        Store<String> words = new MemoryStore<>();
        words.save("Java");
        System.out.println(words.load());

        Store<Integer> score = new MemoryStore<>();
        score.save(42);
        System.out.println(score.load());

        Converter<Integer, String> converter = new LabelConverter<>();
        System.out.println(converter.convert(score.load()));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 GenericImplementationDemo.java
java GenericImplementationDemo
~~~

Stdout:

~~~text
Java
42
value=42
~~~

Takeaways:

- **MemoryStore<E> implements Store<E>** binds E in the class to T in the interface; when used via Store<String>, the save method accepts String and load returns String.
- **new MemoryStore<>()** uses the diamond operator to infer the type argument from context. The diamond does not declare a new type parameter.
- **Converter<I, O>** declares two independent types: input type I and output type O.
- **LabelConverter<T> implements Converter<T, String>** only forwards T into the first type parameter; the second type argument is fixed to String.
- **Converter<Integer, String>** therefore accepts Integer and returns String. String concatenation in convert produces the exact `"value=42"` on the last call.

The nested interfaces/classes in the program allow a single file to compile standalone. When building large projects, they can be moved into separate files while keeping the exact same implements syntax.

## 4. Forwarding `T` Preserves the Type Relationship Between Class and Interface

When writing `class MemorySource<E> implements Source<E>`, `E` is declared **once by the class** and then passed into the interface contract. For example:

~~~java
interface Source<T> { T read(); }

class MemorySource<E> implements Source<E> {
    private final E value;
    MemorySource(E value) { this.value = value; }
    @Override public E read() { return value; }
}
~~~

Inside a method, `Source<String> source = new MemorySource<>("hello");` allows `String text = source.read();` without a cast. If only `Object read()` were declared, the compiler could not promise the result is `String`.

An important difference of a **generic implementing class** is that the same class can maintain contracts `Source<String>`, `Source<Integer>`, and other type arguments at each use site. Forwarding `E` via `implements` allows override signatures to be checked from input to output, without creating separate runtime classes per `E`.

## 5. Comparison: Fixed Type or Forwarding Type Parameter?

Not every implementation of a generic interface needs to be generic. The following two forms have different reuse scopes:

~~~java
interface Reader<T> { T read(); }

class TextReader implements Reader<String> {
    @Override public String read() { return "text"; }
}

class MemoryReader<E> implements Reader<E> {
    private final E item;
    MemoryReader(E item) { this.item = item; }
    @Override public E read() { return item; }
}
~~~

| Implementation Approach | Meaning |
|---|---|
| `TextReader implements Reader<String>` | Class specialized for handling `String`; has no type parameter of its own |
| `MemoryReader<E> implements Reader<E>` | Class carries `E` and passes `E` to the interface; the same declaration works with many types |

When a class has business logic fixed to one concrete type, choose specialization. When the logic is identical across many types and needs to preserve the `E` relationship throughout, choose a generic class. The focus of subsequent sections is **partially or fully forwarding type parameters across contract layers**, not repeating fixed-type implementations.

## 6. Implementing Interfaces with Multiple Type Parameters

Consider a contract that accepts a key K and returns data V:

~~~java
interface Lookup<K, V> {
    V find(K key);
}
~~~

An implementing class can forward both K and V:

~~~java
class MapLookup<K, V> implements Lookup<K, V> {
    private final java.util.Map<K, V> map;

    MapLookup(java.util.Map<K, V> map) {
        this.map = map;
    }

    @Override
    public V find(K key) {
        return map.get(key);
    }
}
~~~

In class MapLookup, K and V are declared separately and used as type arguments to Lookup. When using MapLookup<String, Integer>, the contract becomes **Integer find(String key)**.

Usage example:

~~~java
// Illustrated inside a method:
java.util.Map<String, Integer> data =
        java.util.Map.of("spring", 21);
Lookup<String, Integer> lookup = new MapLookup<>(data);
Integer value = lookup.find("spring");
~~~

You must keep **the exact order of type arguments**: Lookup<K, V> has K for key and V for value. If you write **implements Lookup<V, K>**, the signature to implement becomes **K find(V key)**, which alters the contract.

### Partial Forwarding and Partial Fixing

~~~java
class StringKeyLookup<V> implements Lookup<String, V> {
    private final java.util.Map<String, V> map;

    StringKeyLookup(java.util.Map<String, V> map) {
        this.map = map;
    }

    @Override
    public V find(String key) {
        return map.get(key);
    }
}
~~~

This class only declares V, fixing the key type to String. **StringKeyLookup<Integer>** implements Lookup<String, Integer>; **StringKeyLookup<Long>** implements Lookup<String, Long>.

The reverse direction also works:

~~~java
class BooleanLookup<K> implements Lookup<K, Boolean> {
    @Override
    public Boolean find(K key) {
        return key != null;
    }
}
~~~

**BooleanLookup<K>** keeps the key flexible and fixes the result to Boolean. The number of type parameters declared on the class does not have to equal the number of type parameters on the interface; the type arguments in the implements clause simply need to be complete, compatible, and consistent with the method contracts.

## 7. Implementing Multiple Interfaces Simultaneously

Java allows a class to implement multiple superinterfaces, each able to use the class's own type variables.

~~~java
interface Identified<ID> {
    ID id();
}

interface Valued<V> {
    V value();
}

class Entry<K, V> implements Identified<K>, Valued<V> {
    private final K key;
    private final V data;

    Entry(K key, V data) {
        this.key = key;
        this.data = data;
    }

    @Override
    public K id() {
        return key;
    }

    @Override
    public V value() {
        return data;
    }
}
~~~

**Entry<K, V>** passes K into Identified and V into Valued. An instance of **Entry<Long, String>** fulfills both contracts Identified<Long> and Valued<String>.

One type variable can also be shared across multiple interfaces:

~~~java
interface Input<T> {
    void accept(T value);
}

interface Output<T> {
    T produce();
}

class Channel<T> implements Input<T>, Output<T> {
    private T current;

    @Override
    public void accept(T value) {
        current = value;
    }

    @Override
    public T produce() {
        return current;
    }
}
~~~

With Channel<String>, both accept and produce use String. Using the same T describes the relationship between input and output types of a channel.

The syntax for multiple interfaces on a class is **implements I<T>, J<T>**, separated by commas. If the class also extends a superclass, the order is **extends Base<...> implements I<...>, J<...>**.

## 8. Rules for Overriding Generic Interface Methods

An interface can have regular methods using the interface's type variables:

~~~java
interface Transformer<I, O> {
    O transform(I input);
}

class FunctionTransformer<I, O> implements Transformer<I, O> {
    private final java.util.function.Function<? super I, ? extends O> function;

    FunctionTransformer(
            java.util.function.Function<? super I, ? extends O> function) {
        this.function = function;
    }

    @Override
    public O transform(I input) {
        return function.apply(input);
    }
}
~~~

The implementing method must match the signature **O transform(I input)** after applying the type arguments. Important points:

- Interface methods are public, so the implementation needs to be **public**; reducing visibility to package-private is invalid.
- @Override helps catch methods that do not truly override due to wrong name, wrong parameters, wrong signature, or wrong type relationship.
- Return types must be compatible; Java supports covariant returns for reference types when overriding rules are met.
- Checked exceptions cannot be broadened beyond the interface method's contract.
- When a method needs to use I and O declared on the class, you must not redeclare **<I, O>** right before the method's return type.

Error example:

~~~java
// Intentionally invalid, does not compile:
interface Holder<T> {
    T read();
}

// class Wrong<T> implements Holder<T> {
//     T read() { return null; }
// }
~~~

In Wrong, read() is missing public. The fix is **public T read()**. If a method differs completely in parameter or return types, the compiler reports a missing required method or a name clash.

### Distinguishing Class Type Parameters from Generic Methods

~~~java
interface Copier {
    <U> U copy(U input);
}

class IdentityCopier implements Copier {
    @Override
    public <U> U copy(U input) {
        return input;
    }
}
~~~

In this example **Copier** is not generic; the **copy** method itself declares the type parameter U. That is why the implementation must keep a compatible generic method signature.

Conversely:

~~~java
interface Consumer<T> {
    void accept(T item);
}

class ConsumerImpl<T> implements Consumer<T> {
    @Override
    public void accept(T item) {
        System.out.println(item);
    }
}
~~~

The accept method uses T **already declared by the class**. Writing **public <U> void accept(U item)** would declare a different generic method, failing to fulfill the accept(T) contract that the class is obligated to implement. Distinguish the origin of each type variable when reading signatures.

## 9. Extending a Generic Interface and Then Implementing It

An interface can extend a generic interface and continue forwarding its own type variable:

~~~java
interface Identified<ID> {
    ID id();
}

interface Labeled<ID> extends Identified<ID> {
    String label();
}
~~~

Labeled<ID> extends Identified<ID>. A class implementing **Labeled<K>** must implement both id() returning K and label() returning String, unless a valid implementation has already been inherited from a superclass.

~~~java
class LabeledItem<K> implements Labeled<K> {
    private final K key;
    private final String text;

    LabeledItem(K key, String text) {
        this.key = key;
        this.text = text;
    }

    @Override
    public K id() {
        return key;
    }

    @Override
    public String label() {
        return text;
    }
}
~~~

Only **implements Labeled<K>** is needed; there is no requirement to repeat **implements Identified<K>**, since it is already a superinterface of Labeled<K>.

A subinterface can declare more parameters than its superinterface:

~~~java
interface KeyValue<K, V> extends Identified<K> {
    V value();
}
~~~

K is passed up to Identified; V is used in the new method. A class wanting to implement KeyValue<K, V> must have both **K id()** and **V value()**. This is how type variables are forwarded across multiple inheritance layers.

## 10. Combining `extends` on a Class with `implements` on an Interface

A generic subclass can forward the same type variable to both its superclass and its interface:

~~~java
interface Printable<T> {
    String render(T input);
}

class Container<T> {
    private final T value;

    Container(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

class PrintableContainer<U> extends Container<U>
        implements Printable<U> {

    PrintableContainer(U value) {
        super(value);
    }

    @Override
    public String render(U input) {
        return "[" + input + "]";
    }
}
~~~

Class **PrintableContainer<U>** both extends Container<U> and implements Printable<U>. U is a type parameter declared by the subclass; both supertypes receive U as a type argument. Inheritance does not break type relationships among members, provided type arguments are passed properly.

A non-generic subclass can fix the type argument:

~~~java
class TextContainer extends PrintableContainer<String> {
    TextContainer(String text) {
        super(text);
    }
}
~~~

TextContainer inherits the implementation of Printable<String> through PrintableContainer<String>. You do not need to rewrite implements if the superclass already implements the interface.

In addition, a subclass can continue declaring a type parameter and forwarding it:

~~~java
class CustomContainer<X> extends PrintableContainer<X> {
    CustomContainer(X value) {
        super(value);
    }
}
~~~

In a large inheritance hierarchy, trace the type arguments through each extends/implements to know the exact method contract satisfied by the final object.

## 11. Bounds When an Interface Requires a Constrained Type

If a generic interface has a bounded type parameter, an implementing class using a type variable must also guarantee that bound.

~~~java
interface NumericView<N extends Number> {
    N value();
    double asDouble();
}

class NumericBox<T extends Number> implements NumericView<T> {
    private final T number;

    NumericBox(T number) {
        this.number = number;
    }

    @Override
    public T value() {
        return number;
    }

    @Override
    public double asDouble() {
        return number.doubleValue();
    }
}
~~~

**NumericBox<T extends Number>** guarantees T satisfies Number; therefore **implements NumericView<T>** is valid. If you write **class NumericBox<T> implements NumericView<T>**, the compiler cannot prove every T is a Number.

With an interface requiring Comparable:

~~~java
interface OrderedValue<T extends Comparable<T>> {
    T get();
}

class OrderedBox<T extends Comparable<T>>
        implements OrderedValue<T> {
    private final T value;

    OrderedBox(T value) {
        this.value = value;
    }

    @Override
    public T get() {
        return value;
    }
}
~~~

If a type parameter needs multiple bounds, use **&**:

~~~java
class NumberOrder<T extends Number & Comparable<T>>
        implements Comparable<NumberOrder<T>> {

    private final T number;

    NumberOrder(T number) {
        this.number = number;
    }

    @Override
    public int compareTo(NumberOrder<T> other) {
        return number.compareTo(other.number);
    }
}
~~~

Here **Comparable<NumberOrder<T>>** has **the entire parameterized type NumberOrder<T>** as its type argument; therefore the override signature is **compareTo(NumberOrder<T> other)**, not compareTo(T). The bound on T enables the body to call number.compareTo(other.number).

Even though Number is a class and Comparable is an interface, the type parameter declaration still uses **extends**. If there is a class bound, it comes before interface bounds, separated by **&**.

## 12. Runnable Example: Generic Interface Inheritance, Multiple Types, and a Fixed Subclass

Save into **GenericHierarchyDemo.java**:

~~~java
public class GenericHierarchyDemo {
    interface Identified<ID> {
        ID id();
    }

    interface Labeled<ID> extends Identified<ID> {
        String label();
    }

    static class Item<K, V> implements Labeled<K> {
        private final K key;
        private final V value;
        private final String label;

        Item(K key, V value, String label) {
            this.key = key;
            this.value = value;
            this.label = label;
        }

        @Override
        public K id() {
            return key;
        }

        @Override
        public String label() {
            return label;
        }

        V value() {
            return value;
        }
    }

    static class StringItem extends Item<String, Integer> {
        StringItem(String id, Integer value) {
            super(id, value, "fixed");
        }
    }

    public static void main(String[] args) {
        Labeled<String> a = new Item<>("A-1", 7, "item");
        System.out.println(a.id() + " / " + a.label());

        Item<Long, String> b = new Item<>(42L, "done", "task");
        System.out.println(b.id() + " -> " + b.value());

        StringItem c = new StringItem("S", 9);
        System.out.println(c.id() + ":" + c.value());
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 GenericHierarchyDemo.java
java GenericHierarchyDemo
~~~

Stdout:

~~~text
A-1 / item
42 -> done
S:9
~~~

In this program:

1. **Labeled<ID> extends Identified<ID>** forwards ID from the subinterface up to the superinterface.
2. **Item<K, V> implements Labeled<K>** passes only K to the interface; V is an additional type parameter used for the payload.
3. **Labeled<String> a** only exposes methods guaranteed by Labeled<String> and Identified<String>. Thus a.id() returns String and a.label() returns String; Item's own value() method is not part of variable a's API.
4. **Item<Long, String>** applies K = Long and V = String; only K participates in the Labeled<K> contract.
5. **StringItem extends Item<String, Integer>** fixes the type arguments while inheriting the implementation of Labeled<String>.

## 13. Invariance When Using Generic Interfaces

If a class implements Service<T>, using Class<String> establishes a relationship with Service<String>. However, Java does not automatically consider **Service<String>** a subtype of **Service<Object>**, even though String is a subtype of Object.

~~~java
interface Service<T> {
    T result();
}

class ServiceImpl<T> implements Service<T> {
    private final T value;

    ServiceImpl(T value) {
        this.value = value;
    }

    @Override
    public T result() {
        return value;
    }
}
~~~

Valid assignments:

~~~java
// Illustrated inside a method:
Service<String> text = new ServiceImpl<>("ok");
String a = text.result();

Service<Integer> count = new ServiceImpl<>(123);
Integer b = count.result();
~~~

The following assignment is invalid:

~~~java
// Intentionally invalid, does not compile:
// Service<Object> everything = new ServiceImpl<String>("ok");
~~~

**Service<String>** is not a subtype of Service<Object>. This is the **invariance** of generic type arguments. If you only need to read a Number from a service holding a subtype of Number, use a wildcard at the reference declaration site:

~~~java
Service<? extends Number> numeric = new ServiceImpl<>(10);
Number n = numeric.result();
~~~

This is using a wildcard **at the type use site**. It differs from the implements clause in a class declaration.

## 14. Why Can't You Write `implements Interface<?>`?

The following code is invalid:

~~~java
interface Receiver<T> {
    void accept(T input);
}

// Intentionally invalid:
// class UnknownReceiver implements Receiver<?> {
//     public void accept(Object input) {}
// }
~~~

The **?** is a wildcard type argument suitable in many **use sites** of parameterized types; it cannot be used directly as a type argument in a superinterface declaration **implements Receiver<?>**. A class must specify the contract it will implement using appropriate type arguments.

If you want the class to be flexible:

~~~java
class GenericReceiver<T> implements Receiver<T> {
    @Override
    public void accept(T input) {
        System.out.println(input);
    }
}
~~~

If you want the class to accept only Object:

~~~java
class AnyObjectReceiver implements Receiver<Object> {
    @Override
    public void accept(Object input) {
        System.out.println(input);
    }
}
~~~

**Receiver<T>** and **Receiver<Object>** cannot be arbitrarily interchanged: T can be String, Integer, or another reference type. **Receiver<?>** can be a variable type at a use site when you do not yet know the type argument, yet it does not mean the same thing as Receiver<Object>.

## 15. Cannot Implement Two Different Specializations of the Same Generic Interface

Example:

~~~java
interface Action<T> {
    void run(T value);
}

interface TextAction extends Action<String> {}
interface CountAction extends Action<Integer> {}

// Intentionally invalid, does not compile:
// class Impossible implements TextAction, CountAction {}
~~~

A class cannot simultaneously inherit Action<String> and Action<Integer> through two superinterface paths as shown above. The generic interface has been specialized with two different type arguments; Java forbids this type contract conflict. This is not merely an issue of missing methods, but a limitation of the generic type system and erasure.

You can use **composition** so one class coordinates two distinct responsibilities:

~~~java
class ActionCoordinator {
    private final Action<String> text;
    private final Action<Integer> count;

    ActionCoordinator(Action<String> text, Action<Integer> count) {
        this.text = text;
        this.count = count;
    }

    void text(String value) {
        text.run(value);
    }

    void count(Integer value) {
        count.run(value);
    }
}
~~~

ActionCoordinator holds two clearly typed dependencies without implementing Action twice. If the two roles are genuinely separate, designing two distinct interfaces can also be appropriate.

## 16. Raw Types, Erasure, and Bridge Methods

An implements clause can use a *raw type* of a generic interface in legacy code:

~~~java
interface DataHolder<T> {
    void set(T value);
    T get();
}

// Raw type: only illustrates legacy code compatibility.
class RawHolder implements DataHolder {
    private Object data;

    @Override
    public void set(Object value) {
        data = value;
    }

    @Override
    public Object get() {
        return data;
    }
}
~~~

**implements DataHolder** omits the type argument, resulting in using erased signatures such as Object when the type variable is unbounded. Raw types lose much type-safety checking and can generate *unchecked* warnings when converting between raw and parameterized references.

In new code, clearly express one of two intentions:

- **class Holder<T> implements DataHolder<T>**: generic class keeping the same type variable.
- **class ObjectHolder implements DataHolder<Object>**: specialized implementation for Object.

A related runtime limitation is **type erasure**: generic type variables are typically erased to their upper bound (Object if unbounded). If a class implements an interface with a concrete type and overrides a method, the compiler can generate a **bridge method** to maintain proper dispatch after erasure.

~~~java
interface Provider<T> {
    T supply();
}

class TextProvider implements Provider<String> {
    @Override
    public String supply() {
        return "Java";
    }
}
~~~

TextProvider writes the supply() method returning String. The compiler can generate a bridge method with an erased signature returning Object to satisfy the JVM mechanism. Programmers do not write this bridge manually; in Java source, a **Provider<String>** reference still returns String with compile-time type checking.

That does not mean calling **getClass()** will reveal the type arguments of a generic object: generic metadata may appear on declarations, yet the type arguments associated with an arbitrary runtime variable/reference cannot always be recovered from the runtime class.

## 17. Default Methods and Static Methods in Generic Interfaces

A generic interface can define default methods using the interface's type parameter:

~~~java
interface Mapper<T> {
    T map(T value);

    default java.util.List<T> mapAll(java.util.List<T> source) {
        java.util.List<T> output = new java.util.ArrayList<>();
        for (T value : source) {
            output.add(map(value));
        }
        return output;
    }

    static <U> U identity(U input) {
        return input;
    }
}

class EchoMapper<T> implements Mapper<T> {
    @Override
    public T map(T value) {
        return value;
    }
}
~~~

EchoMapper<T> provides an implementation of map(T) while inheriting the default method mapAll(List<T>). With EchoMapper<String>, mapAll accepts List<String> and returns List<String>.

**Mapper.identity** is a static generic method declaring its own U. It does not use the interface's T because a static method is not tied to a Mapper<String> instance. You can call **Mapper.identity("hello")** or **Mapper.<String>identity("hello")**.

If multiple superinterfaces carry conflicting default methods, the implementing class may have to override explicitly to resolve the conflict under Java rules. The type argument mechanism does not bypass default method conflict rules.

## 18. Standalone Runnable Example: Multiple Superinterfaces and Bounds

Save into **GenericContractsDemo.java**:

~~~java
public class GenericContractsDemo {
    interface Named<T> {
        T value();
    }

    interface TextView {
        String render();
    }

    interface Formatter<T> {
        String format(T input);

        default String formatNonNull(T input) {
            return input == null ? "(missing)" : format(input);
        }
    }

    static final class Ranked<T extends Number & Comparable<T>>
            implements Named<T>, TextView, Comparable<Ranked<T>> {

        private final T rank;

        Ranked(T rank) {
            this.rank = rank;
        }

        @Override
        public T value() {
            return rank;
        }

        @Override
        public String render() {
            return "rank=" + rank.doubleValue();
        }

        @Override
        public int compareTo(Ranked<T> other) {
            return rank.compareTo(other.rank);
        }
    }

    static final class SimpleFormatter<T> implements Formatter<T> {
        @Override
        public String format(T input) {
            return "[" + input + "]";
        }
    }

    public static void main(String[] args) {
        Ranked<Integer> low = new Ranked<>(3);
        Ranked<Integer> high = new Ranked<>(8);

        System.out.println(low.compareTo(high) < 0);
        System.out.println(low.render());
        System.out.println(high.value());

        Formatter<String> format = new SimpleFormatter<>();
        System.out.println(format.formatNonNull("Java"));
        System.out.println(format.formatNonNull(null));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 GenericContractsDemo.java
java GenericContractsDemo
~~~

Stdout:

~~~text
true
rank=3.0
8
[Java]
(missing)
~~~

The program illustrates:

- **Ranked<T>** passes T into Named<T>, while implementing TextView which is a non-generic interface.
- **Comparable<Ranked<T>>** takes the entire Ranked<T> type as its type argument; compareTo accepts another Ranked<T>.
- The bound **T extends Number & Comparable<T>** allows both calling doubleValue() and comparing two T values.
- **SimpleFormatter<T> implements Formatter<T>** provides the format(T) method, while the default method formatNonNull(T) comes from the interface.
- In the null branch, formatNonNull returns `"(missing)"` without calling format.

## 19. Common Compilation Errors and How to Fix Them

**1. Not declaring T on the class**

~~~java
interface Source<T> {
    T get();
}

// Invalid because T does not yet exist in scope:
// class BrokenSource implements Source<T> {}
~~~

Fix by changing to **class FixedSource<T> implements Source<T>** and implementing get(), or using **Source<String>** with a fixed type.

**2. Swapping the order of type arguments**

~~~java
interface PairService<K, V> {
    V get(K key);
}

// Intentionally invalid if the method is written as K -> V:
// class Wrong<K, V> implements PairService<V, K> {
//     public V get(K key) { return null; }
// }
~~~

With **PairService<V, K>**, the real contract is **K get(V key)**; to keep V get(K key), you must use **implements PairService<K, V>**.

**3. Wrong visibility on the overridden method**

~~~java
interface Writer<T> {
    void write(T value);
}

// Invalid:
// class WriterImpl<T> implements Writer<T> {
//     void write(T value) {}
// }
~~~

Methods in an interface are public. The implementation must be **public void write(T value)** and should use @Override.

**4. Replacing T with Object arbitrarily**

~~~java
interface Returner<T> {
    T run();
}

// Invalid:
// class ReturnerImpl<T> implements Returner<T> {
//     public Object run() { return new Object(); }
// }
~~~

Object is not guaranteed to be T. You must implement **public T run()** or fix the type argument to Object if the API truly wants that.

**5. Using a bounded interface without the class satisfying the bound**

~~~java
interface NumberView<T extends Number> {
    T get();
}

// Invalid:
// class AnyView<T> implements NumberView<T> {}
~~~

Fix by writing **class NumberViewImpl<T extends Number> implements NumberView<T>** and implementing get().

**6. Using a wildcard in implements**

**implements Receiver<?>** is invalid; use **implements Receiver<T>** when the class declares T or **implements Receiver<Object>** for a fixed implementation.

**7. Implementing the same interface with two different type arguments**

**implements Action<String>, Action<Integer>** is invalid. Change the design so each class does not inherit the same generic interface under two different specializations.

**8. Using a raw type to omit type arguments**

**implements Holder** with a generic Holder loses type relationships. Choose **Holder<T>** or a concrete specialization and review unchecked warnings.

**9. Assuming class type parameters can be used in static methods**

~~~java
class Util<T> {
    // static T echo(T value) { return value; } // Invalid.
    static <U> U echo(U value) {
        return value;
    }
}
~~~

A static method declares its own U. The class's T does not belong to the static portion in that manner.

**10. Thinking T extends Object allows arbitrary casts**

Even though an unbounded T has an Object bound, **Service<String>** is not Service<Object>. Do not cast via Object to bypass generic type checking; review the contract and consider wildcards at use sites.

## 20. When Should You Design a Class That Implements a Generic Interface?

Typical scenarios:

| Situation | Suggested Design | Reason |
| --- | --- | --- |
| A store holding any type E | MemoryStore<E> implements Store<E> | Keeps the E contract throughout |
| Lookup with independent key and value | MapLookup<K, V> implements Lookup<K, V> | Preserves both type relationships |
| Key is always String, value varies | StringKeyLookup<V> implements Lookup<String, V> | Keeps only the needed position flexible |
| Converting any T to a string | LabelConverter<T> implements Converter<T, String> | Fixes the output to String |
| Only reading strings from a fixed source | TextReader implements Reader<String> | No generic class needed |
| Needing the same T between two interfaces | Channel<T> implements Input<T>, Output<T> | Connects read/write contracts |
| Multiple independent behaviors for the same object | Entity<K,V> implements Identified<K>, Valued<V> | Each interface receives the type argument matching its role |

A helpful design workflow:

1. Start from the interface contract and identify what each type parameter represents.
2. Decide which type arguments need to remain flexible through the class and which should be fixed.
3. Place the exact **<...>** list right after the class name and write all arguments in implements.
4. From the interface, substitute type parameters with the corresponding type arguments to derive the exact signatures for @Override.
5. Check bounds, visibility, return types, and inherited superinterfaces.
6. Try declaring a variable of the parameterized interface type and assigning an appropriate implementation. The compiler will catch mismatched type relationships.
7. Handle null, exceptions, and mutable state under separate contracts; generics does not enforce those runtime properties.

For example, **Lookup<K, V>** using Map.get can return null if the key is missing. Properly implementing Lookup<K,V> guarantees return type V statically, yet does not by itself promise non-null values; the API should document that clearly.

## 21. Review Questions

**Question 1.** In **class DataSource<U> implements Source<U>**, which position declares U and which position uses U as a type argument?

**Answer:** DataSource<U> declares the class's type parameter U; Source<U> in implements uses the already-declared U as the type argument to Source.

**Question 2.** Must the type parameter names on the interface and the class be the same?

**Answer:** No. Interface<A> and Implementation<T> can be linked via implements Interface<T>.

**Question 3.** If interface **Mapper<I, O>** has method **O map(I value)** and class **MapperImpl<T> implements Mapper<T, String>**, what is the signature of the implementing method?

**Answer:** **public String map(T value)**.

**Question 4.** Why is **class Bad implements Source<T>** invalid when the class has not declared T?

**Answer:** T is not in scope inside Bad. You must declare **class Bad<T>** or pick a concrete type argument.

**Question 5.** If interface **Bounded<N extends Number>**, can you write **class Holder<T> implements Bounded<T>**?

**Answer:** No, if T does not have a compatible bound. You need e.g. **class Holder<T extends Number> implements Bounded<T>** and the required methods.

**Question 6.** With **class Entry<K,V> implements Identified<K>, Valued<V>**, which interface uses K and which uses V?

**Answer:** Identified receives K, Valued receives V. Entry<Long, String> implements Identified<Long> and Valued<String>.

**Question 7.** Does a class implementing **Labeled<T>** where **Labeled<T> extends Identified<T>** have to implement id()?

**Answer:** Yes, if id() is still abstract and has not already been provided by a superclass; because Labeled<T> inherits Identified<T>'s contract.

**Question 8.** Can **Service<String>** be automatically assigned to **Service<Object>**?

**Answer:** No. Java generic types are invariant by default; use wildcards at use sites if the read/write model permits.

**Question 9.** Why is **implements Receiver<?>** invalid?

**Answer:** Wildcards cannot be direct type arguments to a superinterface declared in implements. Use Receiver<T> with T declared by the class, or Receiver<ConcreteType>.

**Question 10.** Can a class implement Action<String> and Action<Integer> simultaneously?

**Answer:** No, because the same generic interface Action is inherited with two different type arguments; composition can be used for the two responsibilities.

**Question 11.** In **class Ranked<T> implements Comparable<Ranked<T>>**, is the parameter type of compareTo T or Ranked<T>?

**Answer:** Ranked<T>. The type argument to Comparable is the entire Ranked<T> type, so the method takes another Ranked<T> object.

**Question 12.** Why might a concrete implementation of Reader<String> have a bridge method in bytecode?

**Answer:** The compiler can generate a bridge to preserve dispatch and signature compatibility after type erasure; developers only need to write a proper @Override in Java source.

## 22. Summary

**class Implementation<T> implements Interface<T>** is the standard syntax for a class to use its own type parameter to implement a generic interface. It creates an explicit type binding between the class and the contract, allowing callers to use Implementation<String> as Interface<String> and receive compile-time type checking.

When an interface has multiple type parameters, a class can forward all of them, forward some of them, or combine type variables with concrete type arguments. Trace type arguments across every extends/implements layer, implement methods with `@Override` and exact signatures, satisfy bounds, and avoid raw types, wildcards in superinterfaces, and inheritance conflicts across different specializations.
