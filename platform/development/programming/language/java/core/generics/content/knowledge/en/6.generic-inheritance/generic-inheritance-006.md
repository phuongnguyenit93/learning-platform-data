# How Member Types Are Substituted Across Inheritance Levels in Java Generics

## 1. The Core Problem

When a generic class is inherited, **the superclass's type parameter** can be filled with a concrete type, with the subclass's type parameter, or with a more complex parameterized type. The Java compiler uses **extends** / **implements** relationships to determine the static types of inherited members at each level.

A simple example:

~~~java
class Parent<T> {
    protected T value;

    T get() {
        return value;
    }

    void set(T value) {
        this.value = value;
    }
}

class Child extends Parent<String> {}
~~~

In the context of **Child**, inherited members are viewed as:

- Field **value** has static type **String** in valid access expressions.
- Method **get()** has return type **String**.
- Method **set(String value)** accepts `String`, not an arbitrary `Object`.

This is **type substitution** according to the declaration **Child extends Parent<String>**. `Parent<T>` is not copied into a new runtime class `Parent<String>`; Java performs type checking and relationship inference at compile time.

This lesson clarifies:

1. How `T` is substituted with a type argument at a single inheritance level.
2. How substitutions compose when passing through **multiple levels**.
3. Why an inherited member can be **List<String>** or **Map<String, Integer>** rather than just `String` or `Integer`.
4. Effects on fields, getters/setters, overrides, overloaded methods, and separate generic methods.
5. Inheriting partial type parameters, renaming, reordering parameters, bound constraints, and implementing interfaces.
6. Limitations of raw types, invariance, erasure, bridge methods, and how to read APIs accurately.

All complete programs below use Java 17 or higher. Snippets labeled "illustrating an error" are not compiled as runnable programs.

## 2. Distinguishing Type Parameter Declaration from Type Argument Usage

In the snippet:

~~~java
class Parent<T> {}
class Middle<U> extends Parent<U> {}
class Leaf extends Middle<String> {}
~~~

There are three positions with distinct meanings:

- **<T>** right after `Parent`: `Parent` declares type parameter **T**.
- **<U>** right after `Middle`: `Middle` declares its own type parameter **U**.
- **Parent<U>** in **extends Parent<U>**: `Middle` uses `U` as a **type argument** to fill `Parent`'s `T` slot.
- **Middle<String>** in `Leaf`'s `extends`: `Leaf` uses **String** as a type argument to fill `U`.

Moving upward from `Leaf` to `Parent`, we perform two steps:

~~~text
Leaf extends Middle<String>
Middle<U> extends Parent<U>

At Leaf:
  U := String
  T := U := String

Therefore Leaf inherits Parent<String>.
~~~

The fact that `T` and `U` have different names does not affect the result. Type variable names are declared at each level, whereas what matters is **position** and the type argument expression in the `extends` clause.

Do not read **extends Parent<U>** as "Parent declares U itself" or "U is permanently renamed to T". It is merely a relationship between two generic declarations. `Parent` still has its own type parameter `T`; `Middle` chooses a way to express `T` through `U`.

## 3. Type Substitution at One Level: Fields and Regular Methods

Consider:

~~~java
class Box<T> {
    protected T item;

    Box(T item) {
        this.item = item;
    }

    T get() {
        return item;
    }

    void replace(T value) {
        item = value;
    }
}

class StringBox extends Box<String> {
    StringBox(String value) {
        super(value);
    }

    void printUppercase() {
        System.out.println(get().toUpperCase());
    }
}
~~~

When the compiler checks **StringBox**, it knows `Box` is used with **T = String**. Therefore `get()` returns `String`, and **toUpperCase()** can be called without casting. **replace(T)** is seen through `StringBox` as a method taking `String`.

`Box`'s constructor also uses `T`. At **super(value)** in `StringBox`, the compiler checks the constructor parameter against `String`; however, **constructors are not inherited**, so `StringBox` must declare its own constructor or rely on another valid constructor.

The source code of `Box<T>` is declared only once. Java does not need to generate a separate source version of `Box` for each type. When referenced as **Box<String>**, `get` is still checked as having return type `String`.

Not every member is "substituted" in the same way:

| Member declared in Box<T> | Viewed from StringBox extending Box<String> |
| --- | --- |
| Instance field **T item** | Field value has static type `String` |
| Instance method **T get()** | Return type is `String` |
| Instance method **void replace(T)** | Parameter is `String` |
| Method **List<T> all()** | Return type is `List<String>` |
| Method **Map<String,T> map()** | Return type is `Map<String,String>` |
| Generic method **<R> R convert(Function<T,R>)** | `T` is substituted with `String`; `R` remains a type parameter per method call |
| Static method **static <U> U echo(U)** | `U` is independent, unaffected by `T = String` |

A **private** field also has its type established in the parent class definition, yet the subclass is not permitted to access that field directly due to Java access rules. Type substitution relationships and **access rights** are two separate concerns.

## 4. Multiple Inheritance Levels: Type Substitutions Compose

This case often causes confusion:

~~~java
import java.util.List;

class Base<T> {
    protected final T data;

    Base(T data) {
        this.data = data;
    }

    T get() {
        return data;
    }
}

class Middle<U> extends Base<List<U>> {
    Middle(List<U> items) {
        super(items);
    }

    U first() {
        return get().get(0);
    }
}

class Final extends Middle<String> {
    Final(List<String> names) {
        super(names);
    }
}
~~~

There are three levels:

~~~text
Base<T>           : T
    ^
    | T := List<U>
Middle<U>         : U
    ^
    | U := String
Final             : declares no new type parameter
~~~

Step 1: **Middle<U> extends Base<List<U>>**. `Base`'s `T` is not `U`, but **List<U>**. Inside `Middle`, **get() returns List<U>**, and **data** carries type `List<U>`.

Step 2: **Final extends Middle<String>**. In `Final`, `Middle`'s `U` is filled with `String`.

Step 3: Substitute `U` further into the expression **List<U>**: the result is **List<String>**. Thus `Final` has an inheritance relationship with **Base<List<String>>**, not `Base<String>`.

Tracking table:

| Member | In Base<T> | Viewed via Middle<U> | Viewed via Final |
| --- | --- | --- | --- |
| **data** | `T` | `List<U>` | `List<String>` |
| **get()** | `T` | `List<U>` | `List<String>` |
| **first()** | Not yet present | `U` | `String` |
| **Middle(List<U>)** | Does not belong to Base | Constructor accepting `List<U>` | `Final`'s constructor calls `super` with `List<String>` |

**Note:** The table describes static types and source-code contracts. This is not the JVM rewriting type parameters inside fields and methods of a new runtime class for `Final`.

## 5. Standalone Runnable Example: Three Levels, Nested Element Types

Save as **MultiLevelTypesDemo.java**:

~~~java
import java.util.List;

public class MultiLevelTypesDemo {
    static class Base<T> {
        private final T data;

        Base(T data) {
            this.data = data;
        }

        T get() {
            return data;
        }

        void show(T value) {
            System.out.println(value);
        }
    }

    static class Middle<U> extends Base<List<U>> {
        Middle(List<U> data) {
            super(data);
        }

        U first() {
            return get().get(0);
        }
    }

    static final class Final extends Middle<String> {
        Final(List<String> data) {
            super(data);
        }

        String upperFirst() {
            return first().toUpperCase();
        }
    }

    public static void main(String[] args) {
        Final child = new Final(List.of("java", "spring"));

        List<String> names = child.get();
        String first = child.first();
        Base<List<String>> parent = child;

        System.out.println(names);
        System.out.println(first);
        System.out.println(child.upperFirst());
        parent.show(List.of("typed"));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 MultiLevelTypesDemo.java
java MultiLevelTypesDemo
~~~

Exact stdout:

~~~text
[java, spring]
java
JAVA
[typed]
~~~

Analysis:

- **child.get()** returns `List<String>`, because `Base`'s `T` is substituted with `List<U>`, and `U` is then substituted with `String`.
- **child.first()** returns `String`, because `first` is declared returning `U` in `Middle<U>`.
- **child.upperFirst()** can call `toUpperCase` because the compiler knows `first()` is `String`.
- **Base<List<String>> parent = child** is valid: `Final` is a subtype of `Base<List<String>>` across two levels of `extends`.
- **parent.show(List.of("typed"))** is valid because `show(T)` on variable `parent` is `show(List<String>)`.
- The statement **Base<String> wrong = child** will not compile; `Final` is not a `Base<String>`.

The demo uses `static` nested classes to package the program in one file. Each class `Base<T>`, `Middle<U>`, `Final` still has normal generic inheritance relationships; `static` here only addresses the relationship with the enclosing program class.

## 6. Computing Type Substitutions Systematically

With the chain:

~~~java
class Root<A> {}
class Middle<B> extends Root<java.util.List<B>> {}
class Lower<C> extends Middle<java.util.Set<C>> {}
class Bottom extends Lower<String> {}
~~~

Walk from bottom to top and substitute step by step:

~~~text
Bottom -> Lower<String>:
    C := String

Lower<C> -> Middle<Set<C>>:
    B := Set<C>
    after C := String, B := Set<String>

Middle<B> -> Root<List<B>>:
    A := List<B>
    after B := Set<String>, A := List<Set<String>>

Result:
    Bottom is a subtype of Root<List<Set<String>>>.
~~~

Substitution operates on **complete type expressions**. If a type parameter sits deep inside `List`, `Map`, or `Set`, substitute it at its corresponding position while preserving the outer type wrappers.

A general way to write it:

~~~text
Root<A>
  Middle<B> extends Root<F(B)>
  Lower<C> extends Middle<G(C)>
  Bottom extends Lower<X>

At Bottom: A := F(G(X)).
~~~

`F` and `G` here are merely notation describing "type expressions" (e.g., `F(B) = List<B>`, `G(C) = Set<C>`), **not syntax for declaring higher-kinded type constructors in Java**.

With multiple type parameters, make a separate table for each name to avoid confusion and prioritize following the actual `extends` clauses rather than guessing from class names.

## 7. Multiple Type Parameters and Changing Order

Consider a superclass taking two type parameters:

~~~java
class Pair<A, B> {
    A left;
    B right;

    Pair(A left, B right) {
        this.left = left;
        this.right = right;
    }

    A left() { return left; }
    B right() { return right; }
}

class Flipped<X, Y> extends Pair<Y, X> {
    Flipped(Y left, X right) {
        super(left, right);
    }
}

class Concrete extends Flipped<Integer, String> {
    Concrete(String left, Integer right) {
        super(left, right);
    }
}
~~~

Read slowly step by step:

1. `Flipped<X,Y> extends Pair<Y,X>`: **A = Y**, **B = X**.
2. `Concrete extends Flipped<Integer,String>`: **X = Integer**, **Y = String**.
3. Combine the two steps: **A = String**, **B = Integer**.
4. `Concrete` therefore has a subtype relationship with **Pair<String,Integer>**.

When reading inherited members via `Concrete`:

- **left()** returns `String`.
- **right()** returns `Integer`.
- **left** is `String`, **right** is `Integer` (subject to access rights).
- `Concrete`'s constructor takes `String` first and `Integer` second due to its own declared signature; it does not automatically inherit `Pair`'s constructor.

Do not deduce that `Concrete` is `Pair<Integer,String>` just because `Concrete` extends `Flipped<Integer,String>`. **The `extends Pair<Y,X>` clause has swapped the two positions**.

A subclass can also **keep one parameter flexible and fix the other parameter**:

~~~java
class KeyValue<K, V> {
    K key;
    V value;
}

class StringKeyValue<V> extends KeyValue<String, V> {}
class LongStringValue extends StringKeyValue<String> {}
~~~

In `StringKeyValue<V>`: `K = String`, `V` remains free. In `LongStringValue`: `V = String`, implying both `K` and `V` of `KeyValue` are `String`. The name `LongStringValue` is just an example name; actual parameterization must be deduced from `extends`, **not from the class name**.

## 8. Runnable Example: Two Type Parameters Through an Intermediate Class

Save as **PermutationDemo.java**:

~~~java
public class PermutationDemo {
    static class Pair<A, B> {
        private final A left;
        private final B right;

        Pair(A left, B right) {
            this.left = left;
            this.right = right;
        }

        A left() { return left; }
        B right() { return right; }
    }

    static class Swapped<X, Y> extends Pair<Y, X> {
        Swapped(Y left, X right) {
            super(left, right);
        }
    }

    static final class Fixed extends Swapped<Integer, String> {
        Fixed(String name, Integer score) {
            super(name, score);
        }
    }

    public static void main(String[] args) {
        Fixed item = new Fixed("Alice", 91);
        Pair<String, Integer> parent = item;

        String name = parent.left();
        Integer score = parent.right();

        System.out.println(name);
        System.out.println(score);
        System.out.println(parent.left() + ":" + parent.right());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 PermutationDemo.java
java PermutationDemo
~~~

Stdout:

~~~text
Alice
91
Alice:91
~~~

**Fixed extends Swapped<Integer,String>**, and `Swapped<X,Y>` extends `Pair<Y,X>`. Therefore `A = String`, `B = Integer`. The assignment **Pair<String,Integer> parent = item** is checked at compile time and requires no cast.

## 9. Methods Accepting the Parent's Type Parameter Are Also Substituted

Suppose the superclass does not only return `T` but also accepts `T`:

~~~java
class Repository<T> {
    private T current;

    void save(T item) {
        current = item;
    }

    T load() {
        return current;
    }
}

class TextRepository extends Repository<String> {}
~~~

In the context of `TextRepository`:

~~~java
TextRepository repo = new TextRepository();
repo.save("ok");
String value = repo.load();
~~~

The compiler views **save** as accepting `String`, and **load** as returning `String`. Writing **repo.save(123)** fails type checking at compile time.

With an intermediate class:

~~~java
class ListRepository<E> extends Repository<java.util.List<E>> {}
class NameRepository extends ListRepository<String> {}
~~~

On `NameRepository`, **save** accepts `List<String>` and **load** returns `List<String>`. It does not accept `String` directly because `Repository`'s `T` is filled with **the entire `List<E>`**.

Distinguish **method parameter types** from **runtime values**. If `save` accepts a `List<String>`, that list can still be mutable or contain `null` depending on the implementation. Generic substitution does not automatically create invariants like "non-empty list", "non-null", or "immutable".

## 10. Overriding: Inherited Signatures Must Be Viewed After Substitution

When a subclass overrides a method, Java checks the contract based on the generic superclass's type after applying type arguments.

~~~java
abstract class Provider<T> {
    abstract T provide();
}

class StringProvider extends Provider<String> {
    @Override
    String provide() {
        return "ready";
    }
}
~~~

`Provider<T>.provide()` has return type `T`. With `StringProvider extends Provider<String>`, the method to implement must return `String` or a compatible return type under override rules.

A multi-level example:

~~~java
abstract class Base<T> {
    abstract T create();
}

abstract class Middle<U> extends Base<java.util.List<U>> {}

class Final extends Middle<String> {
    @Override
    java.util.List<String> create() {
        return java.util.List.of("ok");
    }
}
~~~

`Final` must return **List<String>**, because `Base`'s `T` is substituted with `List<U>`, and `U` with `String`. Writing **String create()** does not properly override the contract and cannot implement the abstract method.

### Covariant Return Types

When a superclass method after substitution returns a broad reference type, an override can return an appropriate subtype:

~~~java
abstract class NumberProvider<T extends Number> {
    abstract T get();
}

class IntegerProvider extends NumberProvider<Number> {
    @Override
    Integer get() {
        return 10;
    }
}
~~~

In `IntegerProvider`, `NumberProvider`'s `T` is chosen as `Number`; **Integer** is a subtype of `Number`, so the `Integer` return type is covariant and valid.

However, **List<Integer>** is not a subtype of **List<Number>**, due to generic invariance. Therefore, you cannot rely solely on `Integer extends Number` to change a return type from **List<Number>** to **List<Integer>** when overriding.

### Access Levels and Checked Exceptions

A subclass cannot reduce the access level of an overridden method. If an interface method is `public`, the implementation must be `public`. For class methods, access levels and checked exceptions must also follow standard Java rules. Generic substitution only replaces type variables in signatures; it does not bypass other override rules.

## 11. Distinguishing Overriding from Overloading and Field Hiding

Two methods with the same name do not necessarily override each other.

~~~java
class Base<T> {
    void set(T value) {
        System.out.println("base");
    }
}

class TextChild extends Base<String> {
    void set(Integer value) {
        System.out.println("integer");
    }
}
~~~

In `TextChild`, there is **set(String)** inherited through `Base<String>` and **set(Integer)** declared by `TextChild`. This is **overloading**: two signatures taking different types.

If `TextChild` wants to override the method accepting `String`, write:

~~~java
class TextChild extends Base<String> {
    @Override
    void set(String value) {
        System.out.println("string");
    }
}
~~~

Using `@Override` helps the compiler verify intent. In cases involving type erasure and name clashes, an apparently valid overload can still lead to an error if two declarations have the same erasure; do not guess solely from variable names or a sense of "different generic type arguments".

**Field hiding** is a different matter. If a subclass declares a field with the same name as a field in the parent, Java can have **two distinct fields**, and field access is resolved according to the static type of the expression, not dynamic dispatch like instance methods. Generic substitution does not turn field hiding into overriding.

Example:

~~~java
class Parent<T> {
    T value;
}

class Child extends Parent<String> {
    Integer value;
}
~~~

`Child` has its own `Integer` field `value`, while **((Parent<String>) child).value** accesses `Parent`'s field of type `String`. Field hiding designs are often confusing, so prefer different names or encapsulation via getters/setters.

## 12. Superclass Generic Methods Have Their Own Scope

A method can declare its own type parameter **R**, independent of the class's `T`:

~~~java
import java.util.function.Function;

class Box<T> {
    private final T item;

    Box(T item) {
        this.item = item;
    }

    <R> R map(Function<? super T, ? extends R> mapper) {
        return mapper.apply(item);
    }
}

class StringBox extends Box<String> {
    StringBox(String value) {
        super(value);
    }
}
~~~

In `StringBox`, the compiler substitutes `T` with `String` in the inherited method. However, **R is not substituted with String**; `R` is still determined by **each call to `map`**.

Through `StringBox`, the logical signature of `map` is:

~~~text
<R> R map(Function<? super String, ? extends R> mapper)
~~~

Example:

~~~java
// Illustration inside a method:
StringBox box = new StringBox("Java");
Integer length = box.map(String::length);
String upper = box.map(String::toUpperCase);
~~~

The first time `R` is inferred as `Integer`; the next time `R` is `String`. Here is the distinction:

- **T** belongs to class `Box<T>`, so when `StringBox extends Box<String>`, `T` is fixed.
- **R** belongs to the generic method `map`, so each invocation still chooses `R` independently.

A superclass generic method such as **<X> X identity(X input)** is unrelated to `T` and retains its ability to accept any `X` across all subclasses. Class type arguments do not "replace every `<...>` appearing in the superclass".

## 13. Runnable Example: Method-Level Type Parameters Remain Independent

Save as **InheritedGenericMethodDemo.java**:

~~~java
import java.util.function.Function;

public class InheritedGenericMethodDemo {
    static class Box<T> {
        private final T item;

        Box(T item) {
            this.item = item;
        }

        <R> R map(Function<? super T, ? extends R> mapper) {
            return mapper.apply(item);
        }

        T value() {
            return item;
        }
    }

    static class WordBox extends Box<String> {
        WordBox(String word) {
            super(word);
        }
    }

    public static void main(String[] args) {
        WordBox box = new WordBox("Java");

        Integer length = box.map(String::length);
        String uppercase = box.map(String::toUpperCase);
        String original = box.value();

        System.out.println(length);
        System.out.println(uppercase);
        System.out.println(original);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 InheritedGenericMethodDemo.java
java InheritedGenericMethodDemo
~~~

Stdout:

~~~text
4
JAVA
Java
~~~

Type relationship: from `WordBox extends Box<String>`, `T` is substituted with `String` in **value()** and the input side of `Function` in **map**. `R` remains independent, able to be `Integer` or `String` depending on the mapper. All three variables are assigned directly without casting.

## 14. Generic Interfaces Across Multiple `extends`/`implements` Levels

Not only superclasses participate in substitution. Generic interfaces can also be parameterized across multiple layers.

~~~java
interface Source<T> {
    T fetch();
}

interface SequenceSource<E> extends Source<java.util.List<E>> {}

abstract class AbstractSequence<U> implements SequenceSource<U> {}

class StringSequence extends AbstractSequence<String> {
    @Override
    public java.util.List<String> fetch() {
        return java.util.List.of("a", "b");
    }
}
~~~

Trace the path:

~~~text
StringSequence
  extends AbstractSequence<String>
  implements SequenceSource<String>
  extends Source<List<String>>
~~~

Method `fetch` declared in `Source<T>` returns `T`. In `StringSequence`, the result becomes **List<String>**. Having the implementation in the final class does not alter the inherited interface contract.

Substitution through interfaces with multiple type parameters can be more intricate:

~~~java
interface Transformer<I, O> {
    O apply(I input);
}

interface TextTransformer<T> extends Transformer<T, String> {}

class NumberFormatter implements TextTransformer<Integer> {
    @Override
    public String apply(Integer input) {
        return "n=" + input;
    }
}
~~~

In `NumberFormatter`, `TextTransformer`'s `T` is substituted with `Integer`. The parent interface becomes `Transformer<Integer,String>`; therefore, `apply` takes `Integer` and returns `String`.

Call sites can use:

~~~java
Transformer<Integer, String> converter = new NumberFormatter();
String text = converter.apply(5);
~~~

No cast is needed because subtype relationships and method signatures have been verified by the compiler.

## 15. Invariance: Subclassing Does Not Mean Subtyping Across Type Arguments

Consider:

~~~java
class Holder<T> {}
class NumberHolder extends Holder<Integer> {}
~~~

Because `NumberHolder extends Holder<Integer>`, the following assignments are valid:

~~~java
NumberHolder direct = new NumberHolder();
Holder<Integer> asIntegerHolder = direct;
Holder<? extends Number> asNumberReader = direct;
~~~

However:

~~~java
// Intentionally invalid:
// Holder<Number> asNumberHolder = direct;
~~~

**Holder<Integer> is not a subtype of Holder<Number>**. Even though `Integer extends Number`, type arguments of generic classes like `Holder` are **invariant** by default.

A multi-level case:

~~~java
class Root<T> {}
class Mid<U> extends Root<java.util.List<U>> {}
class Leaf extends Mid<Integer> {}
~~~

`Leaf` is a subtype of **Root<List<Integer>>**, not **Root<List<Number>>** or **Root<Collection<Integer>>** merely because of subtype relationships among inner types.

If an API needs flexibility at the *use site*, bounded wildcards can be used; for example, **Root<? extends List<? extends Number>>** matches a `Root<List<Integer>>` in many situations. However, when reading/writing through wildcards, allowed operations may be restricted. Do not replace the actual `extends` expression with a broad supertype and assume all write operations remain valid.

## 16. Bounds Must Still Be Satisfied at Every Level

A generic superclass can constrain its type parameter:

~~~java
class NumericBox<T extends Number> {
    protected final T value;

    NumericBox(T value) {
        this.value = value;
    }

    double amount() {
        return value.doubleValue();
    }
}
~~~

A generic subclass must supply a type argument guaranteed to be a subtype of `Number`:

~~~java
class NumericMiddle<U extends Number> extends NumericBox<U> {
    NumericMiddle(U value) {
        super(value);
    }
}

class IntegerBox extends NumericMiddle<Integer> {
    IntegerBox(Integer value) {
        super(value);
    }
}
~~~

Writing **class Invalid<U> extends NumericBox<U>** causes a compiler error because an unbounded `U` is not guaranteed to be a `Number`. Superclass bounds are checked at the point where the type argument is supplied in `extends`.

Sometimes the type argument is a concrete type that always satisfies the bound, so the subclass does not need to declare the same bound:

~~~java
class FixedNumeric<X> extends NumericBox<Integer> {
    FixedNumeric(Integer value) {
        super(value);
    }
}
~~~

In `FixedNumeric<X>`, `X` is independent and does not participate in `extends`; `X` being unbounded does not affect `NumericBox<Integer>`. However, declaring an unused `X` clutters the design if it serves no real purpose.

### Bounds Involving Multiple Type Parameters

~~~java
class OrderedPair<T extends Comparable<? super T>> {
    T left;
    T right;
}

class TextPair extends OrderedPair<String> {}
~~~

`String` satisfies the bound `Comparable<? super String>`, so `TextPair` is valid. When extending generic classes with complex bounds, check **the entire type argument** rather than only looking at the name `T`: forms like `Number`, `Comparable<? super T>`, and `InterfaceA & InterfaceB` can restrict which substitutions are valid.

Bounds do not exclude `null`. If `NumericBox<Integer>` holds `null`, **amount()** can throw `NullPointerException`. That is a runtime value issue, not an invalid type substitution.

## 17. Static Members Do Not Carry Instance Type Parameters

A superclass's type parameter belongs to the generic declaration, yet cannot be used as a type in a static context of that class itself.

~~~java
class Base<T> {
    static int instanceCount;

    // static T last; // Invalid.
    static <U> U echo(U value) {
        return value;
    }
}

class Child extends Base<String> {}
~~~

**Base<String>** and **Base<Integer>** do not have two separate versions of static state. `Child` inherits the relationship from `Base<String>`, yet a static field of `Base` still belongs to the shared `Base`, without having `T` substituted per subtype.

The method **static <U> U echo(U value)** declares its own method `U`. When calling **Base.echo("x")** or **Child.echo(1)**, `U` is inferred independently from the argument, not locked to `String` just because `Child extends Base<String>`.

Static methods undergo **hiding**, not dynamic overriding like instance methods. Do not use superclass parameterization to assume a static method is specialized for `T`.

## 18. Constructors, Private Members, and What Is Actually Inherited

The mental model "everything in the parent has its type substituted" is inaccurate. When analyzing generics, combine it with ordinary inheritance rules:

- **Constructors are not inherited**. Subclasses declare their own constructors and call `super(...)` appropriately.
- `private` fields/methods of the superclass do not become directly accessible members in the subclass. They still exist in the parent class and can be invoked indirectly through appropriate `public`/`protected` APIs.
- A method that is inaccessible due to its access modifier will not become accessible merely because a type argument has been determined.
- Overridden instance methods have dynamic dispatch; field access does not have dynamic dispatch like methods.
- Static fields/methods belong to the class, not to a specific parameterization `T`.

Example:

~~~java
class Base<T> {
    private final T secret;

    Base(T secret) {
        this.secret = secret;
    }

    public T reveal() {
        return secret;
    }
}

class Child extends Base<String> {
    Child(String text) {
        super(text);
    }

    String readSecret() {
        // return secret; // Invalid: private in Base.
        return reveal();  // Valid: inherited public method returns String.
    }
}
~~~

It is true that substitution shows **secret** in `Base<String>` has type `String` and **reveal()** returns `String`. Still, `Child` cannot read the `secret` field directly. That is an access-control restriction, unrelated to an invalid type substitution.

## 19. Type Erasure and Bridge Methods: Source vs. Bytecode Differences

In Java source, when writing:

~~~java
class Base<T> {
    T value() { return null; }
}

class StringBase extends Base<String> {
    @Override
    String value() { return "ok"; }
}
~~~

The compiler understands `StringBase` overrides `Base<String>`'s method returning `String`. However, **type erasure** typically replaces an unbounded type variable `T` with `Object` in `Base`'s bytecode signature.

To preserve JVM dispatch and the override contract after erasure, the compiler may generate a **bridge method** in `StringBase`, effectively having a signature returning `Object` and delegating to the method returning `String`. Bridge methods are generated automatically; Java authors should not manually declare methods with the erased signature.

This explains two facts that are simultaneously true:

1. In Java source, **String s = new StringBase().value()** is valid without manual casting.
2. Runtime **does not create a separate `Base<String>` class** whose `value()` method literally returns `String` at every bytecode position.

Where a bridge method exists, you can observe it with **javap -c -p** on the compiled class file. Specific bridge names/signatures are implementation details and should not be relied upon to write application logic.

### A Warning About Overloading and Erasure

Two methods like **void accept(List<String>)** and **void accept(List<Integer>)** cannot coexist as two distinct overloads in one class because they have the same erasure. Multi-level generic inheritance can also lead to a **name clash** when a subclass declares a method that looks differently typed yet collides with an inherited member after erasure.

Do not use raw types or unchecked casts to "fix" a name clash. Clearly identify the contract to override, adjust signatures appropriately, or choose a different method name when they are genuinely two different operations.

## 20. Raw Types Lose Substitution Accuracy

With:

~~~java
class Base<T> {
    T get() { return null; }
}

class Good extends Base<String> {}
class Legacy extends Base {}
~~~

`Good` extends `Base<String>`, so **Good.get()** is seen from source as `String`. `Legacy` extends **raw `Base`**; type argument information has been dropped, so `get()` is typically viewed via its erased signature as `Object`.

~~~java
Good good = new Good();
String text = good.get();

Legacy legacy = new Legacy();
Object rawValue = legacy.get();
~~~

When casting `rawValue` to `String`, you take on runtime risk yourself. Raw inheritance usually comes from pre-generics legacy Java code or unupdated APIs. In new code, use complete type arguments.

**Raw types are not equivalent to wildcards**. For instance, `Base<?>` is still a parameterized type with an unspecified component type, and the compiler enforces type-safety checks; raw `Base` bypasses many checks. If the type argument is unknown, consider a wildcard at an appropriate reference position, whereas a class's `extends` clause requires a valid supertype under Java rules, not a direct wildcard such as **extends Base<?>**.

## 21. Type Inference in Generic Inheritance Chains

The compiler can infer type arguments of constructors and methods from context, yet **does not automatically make a subclass a subtype of every seemingly compatible parameterization**.

~~~java
class Parent<T> {
    Parent(T value) {}
}

class Child<U> extends Parent<java.util.List<U>> {
    Child(java.util.List<U> values) {
        super(values);
    }
}
~~~

Callers can write:

~~~java
Child<String> child = new Child<>(java.util.List.of("x", "y"));
Parent<java.util.List<String>> parent = child;
~~~

The diamond in **new Child<>(...)** infers `U = String` from the constructor argument and target type. Then the `extends` relationship states `Parent`'s `T` equals `List<U>`, namely `List<String>`.

If using **var child = new Child<>(List.of("x"))** in a sufficiently clear context, the compiler still infers from the constructor argument without losing type safety just because of `var`. However, type inference does not alter the `extends` declaration and cannot cure passing invalid type arguments.

Distinguish **type inference at the call site** from **type substitution during inheritance**:

- Inference selects appropriate type arguments for a generic constructor/method from context.
- Substitution applies the selected type arguments across `extends`/`implements` clauses to determine supertype member types.

Both steps participate in type checking, yet they are not the same mechanism.

## 22. Common Mistakes

### Mistake 1: Seeing `Child extends Middle<String>` and Assuming `Base<T>` Has `T = String`

If **Middle<U> extends Base<List<U>>**, `T` must be `List<String>`, not `String`. Always substitute completely through every `extends` clause.

### Mistake 2: Renaming a Type Parameter and Thinking the Type Changed

~~~java
class Base<T> {}
class Mid<U> extends Base<U> {}
~~~

The names `T` and `U` differ, yet the relationship is `T := U`. Renaming only affects how source code reads; no runtime value conversion occurs.

### Mistake 3: Thinking `List<Integer>` Is `List<Number>`

Ordinary generic types are invariant. A class extending `Base<List<Integer>>` does not simultaneously extend `Base<List<Number>>` just because `Integer extends Number`.

### Mistake 4: Overriding with the Wrong Type After Substitution

~~~java
abstract class Base<T> {
    abstract T read();
}

class Wrong extends Base<String> {
    // String is the type that must be returned:
    // @Override Integer read() { return 1; } // Invalid.
    @Override String read() { return "ok"; }
}
~~~

Return type `Integer` is incompatible with `String`, which the `Base<String>` contract requires.

### Mistake 5: Trying to Treat a Generic Method Parameter as Substituted by the Class

With **<R> R map(Function<T,R>)**, only `T` is substituted via class inheritance; `R` is another type parameter belonging to the method. `R` is still determined by the caller.

### Mistake 6: Treating a Superclass Constructor as an Inherited Constructor

Constructors are not inherited. Even if the superclass declares `Base(T)`, the subclass still needs its own valid constructor and must call **super(...)** appropriately when needed.

### Mistake 7: Accessing a Private Field from a Subclass

Type substitution only determines static types. It does not bypass `private` access; call an appropriate getter or adjust the API according to encapsulation design.

### Mistake 8: Using Raw `Base` Instead of `Base<String>`

Raw types strip away much generic information in source code and fall back to `Object`/erasure. Use a fully parameterized supertype when the type is known.

### Mistake 9: Expecting Generic Static Fields to Be Split per `T`

Static fields do not belong separately to each type argument. `Base<Integer>` and `Base<String>` do not get static fields automatically specialized per `T`.

### Mistake 10: Confusing Field Hiding with Method Overriding

Instance methods can be overridden and dynamically dispatched; a field with the same name in a subclass hides the superclass field rather than overriding it. The static type of the expression determines which field is accessed.

### Mistake 11: Assuming Every Member Is Inherited Directly

Constructors and `private` members do not belong to the same set of inherited accessible members as `public`/`protected` methods. Inheritance and access modifier rules still apply beyond generics.

### Mistake 12: Using Unchecked Casts to Fake a Supertype

A **Base<List<Integer>>** cannot safely be treated as **Base<List<String>>** just because both have class `Base` after erasure. Invalid casts can lead to `ClassCastException` when reading data. Fix the type relationships instead of hiding errors.

## 23. How to Read a Real-World Hierarchy

When encountering an unfamiliar inheritance chain, follow this sequence:

1. **Find the original generic declaration.** Note the type parameter names of the class or interface holding the member of interest, e.g., `Base<T>` with `T get()`.
2. **Read the `extends`/`implements` clause at the level right below.** Write down the exact type argument entering each position, including `List<U>`, `Map<K,V>`, or a deeply nested parameterized type.
3. **Repeat for subsequent levels.** Replace type variables inside the recorded type expression with the type arguments from the lower level.
4. **Do not drop generic wrapper layers.** If `T = List<U>`, then after `U = String`, `T = List<String>`, not `String`.
5. **Identify whether members are inherited or overridden.** Check `private`, `static`, constructors, and access levels; do not assume every member dispatches the same way.
6. **If a method has `<R>`, note `R` separately.** Method type parameters have their own scope and inference.
7. **Check bounds and invariance.** An `extends` clause must satisfy bounds; `List<Integer>` does not automatically convert to `List<Number>`.
8. **Verify output using valid reference types.** Try declaring `Base<CorrectType> parent = child` so the compiler confirms your deduced result.
9. **Check erasure when truly needed.** If you hit a name clash or bridge method, remember source type checking and bytecode erasure are two different layers.
10. **Prefer explicit type arguments in documentation.** A substitution table is often clearer than a long chain of unannotated type declarations.

Example problem:

~~~java
class Root<T> {
    T read() { return null; }
}

class Level1<A> extends Root<java.util.Map<String, A>> {}

class Level2<B> extends Level1<java.util.List<B>> {}

class Final extends Level2<Integer> {}
~~~

Table:

| Level | Substituted type parameter |
| --- | --- |
| `Level2<Integer>` | `B = Integer` |
| `Level1<List<B>>` | `A = List<Integer>` |
| `Root<Map<String,A>>` | `T = Map<String,List<Integer>>` |

Hence **Final.read()** has static type **Map<String,List<Integer>>**. No casts or data conversions occur during this substitution process.

## 24. Self-Check Questions

**Question 1.** `Base<T>` declares `T get()`; `Middle<U> extends Base<List<U>>`; `Leaf extends Middle<String>`. What is the type of `get()` in `Leaf`?

**Answer:** `List<String>`. Substitute `T = List<U>`, then `U = String`.

**Question 2.** Why is **Leaf** in the question above not automatically a `Base<String>`?

**Answer:** The intermediate `extends` clause placed `List<U>` into `Base`'s `T`; ultimately `T` must be `List<String>`, not `String`.

**Question 3.** Given `Pair<A,B>`, `Swapped<X,Y> extends Pair<Y,X>`, `Fixed extends Swapped<Integer,String>`: what types do `left()` and `right()` return?

**Answer:** `left()` returns `String`, `right()` returns `Integer`; because `A = Y = String`, `B = X = Integer`.

**Question 4.** Given `Repository<T>.save(T)`, what parameter does `NameRepo extends Repository<List<String>>` accept in `save`?

**Answer:** `List<String>`, not `String`. Substitution applies to the entire type expression of `T`.

**Question 5.** A parent's generic method **<R> R map(Function<T,R>)** is used from a subclass extending `Base<String>`. Does `R` become `String`?

**Answer:** No. Only `T` is fixed to `String`; `R` is still determined by the generic method and each call site.

**Question 6.** Can a subclass extending `Provider<Number>` override `Number get()` with `Integer get()`?

**Answer:** Yes, provided other override conditions are also satisfied: `Integer` is a subtype of `Number` and covariant return types are valid.

**Question 7.** Why can't a method returning `List<Number>` be overridden with a method returning `List<Integer>` just because `Integer extends Number`?

**Answer:** `List<Integer>` is not a subtype of `List<Number>` due to invariance.

**Question 8.** Is `Base<T>`'s constructor automatically inherited by `Child extends Base<String>`?

**Answer:** No. `Child` must have an appropriate constructor and call `super(...)` when needed under Java's initialization rules.

**Question 9.** Is the static method `<U> U echo(U x)` in `Base<T>` fixed to `U = String` when called via `Child extends Base<String>`?

**Answer:** No. `U` is the static method's own type parameter; `Base`'s `T` is not used in a static context that way.

**Question 10.** Does the raw subclass **class Legacy extends Base** keep `T get()` specialized as `String`?

**Answer:** No. Raw types drop type arguments; for unbounded `T`, the post-erasure type is typically `Object`, and type safety decreases.

**Question 11.** If multiple `extends`/`implements` levels lead to interface `Source<List<Integer>>`, can a `Source<List<Number>>` reference be assigned from that object directly?

**Answer:** No, because `List<Integer>` and `List<Number>` are different parameterized types and generic invariance applies across levels.

**Question 12.** When the compiler generates a bridge method for a generic override, does it mean Java creates a new `Base<String>` runtime class?

**Answer:** No. Bridges support dispatch after erasure; they do not create a separate runtime class per type argument.

## 25. Core Takeaways

To know the type of an inherited member, **do not guess from the subclass name**. Follow every `extends`/`implements` clause accurately, substitute type arguments at each level, and compose substitutions in order. If **Middle<U> extends Base<List<U>>** and **Final extends Middle<String>**, then **Base<T>** is viewed through `Final` with **T = List<String>**; thus field `T`, method `T get()`, and methods taking `T` all use `List<String>` in valid contexts.

Type parameters of generic methods have their own scope, static members are not bound per `T`, constructors are not inherited, `private` members do not become directly accessible, and erasure does not remove compile-time type checking in source code. Clearly separating **type substitution**, **inheritance/override rules**, and **bytecode representation** is the key to reading multi-level generic hierarchies accurately.