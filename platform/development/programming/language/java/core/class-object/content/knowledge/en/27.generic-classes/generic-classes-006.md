# Generic Methods and Separate Type Parameters in Java 17+

## 1. The Problem: A Method's Type Does Not Have to Be the Class's Type

A **generic class** declares type parameters in the class declaration:

~~~java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
~~~

Here, `T` belongs to the **Box type scope**: when writing `Box<String>`, the `get()` method returns String; with `Box<Integer>`, it returns Integer. However, sometimes a method needs to handle **a separate type, independent of T** of the class. For example, a Box<String> can accept an Integer, Boolean, or another object to create a description string. In that case, the method can declare **its own type parameter**, typically named `U` or `R`.

~~~java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    <U> String describeWith(U extra) {
        return value + ":" + extra;
    }
}
~~~

This is a complete, valid class declaration. `<U>` stands **before the return type** `String`, showing that `describeWith` is a **generic method**. `T` still belongs to the class; `U` belongs only to that method declaration. When calling `new Box<>("java").describeWith(17)`, the compiler infers `U` as Integer, while the Box's `T` remains String.

**Key point:** a generic method does not need to reside in a generic class. And a method declared in a generic class does **not automatically become a generic method** if it does not have its own type parameter list.

This article belongs to **Java core – class-object**, group **Generic classes**, section **Generic methods and separate type parameters**. All standalone programs below target **Java 17+**, without preview features enabled, and have specified file names, compile/run commands, and stdout. Illustrative snippets or intentionally non-compiling fragments will be clearly noted.

## 2. Three Levels to Distinguish

| Level | Example | Who owns the type parameter? |
| --- | --- | --- |
| Generic class | `class Box<T> { ... }` | `T` of class Box |
| Method using the class's T | `T get() { ... }` | Still the class's `T`, **does not declare a new T** |
| Generic method | `<U> U echo(U value) { ... }` | The method's own `U` |
| Generic static method | `static <X> X identity(X x) { ... }` | The static method's own `X` |
| Method with multiple type parameters | `<A,B> Pair<A,B> pair(A a,B b)` | The method's own `A` and `B` |

A method like `String toString()` in `Box<T>` is a normal method; `T get()` may depend on T, yet it is **not a generic method in JLS terminology**, because it does not declare method type parameters.

Reason for the distinction: `T` of `Box<T>` is determined when looking at the type of the receiver `Box<String>`; whereas `U` of `<U> U echo(U x)` is determined **separately for each invocation**, based on arguments, target type, and the compiler's constraints.

## 3. Standard Syntax of a Generic Method

Declaration form:

~~~java
[modifiers] <TypeParameters> ReturnType methodName(parameters) {
    // method body
}
~~~

The line above is a **descriptive syntax template**, not Java source used directly for compilation: the square brackets and placeholders merely represent the components.

A concrete declaration:

~~~java
public static <T> T identity(T value) {
    return value;
}
~~~

This is a **valid method if placed in a class**. Note the order: the `public static` modifiers, then `<T>`, followed by the return type `T` and the name `identity`.

- `<T>` **declares** a type parameter named T.
- The first `T` after `<T>` is the **return type**.
- `T value` is a regular value parameter of type T.
- `return value;` is valid because value has type T.

Compare with:

~~~java
public static T identity(T value) {
    return value;
}
~~~

The second snippet **intentionally fails to compile** if placed in a class that does not declare T appropriately: T is not declared. If placed in `class C<T>`, a static method is still **not allowed** to use the class-level T in a static context. You must declare `static <T>` or another type parameter for the static method itself.

## 4. Complete Program 1 — Generic Method in a Non-Generic Class

File **`GenericIdentityDemo.java`**:

~~~java
public class GenericIdentityDemo {
    static <T> T identity(T input) {
        return input;
    }

    public static void main(String[] args) {
        String name = identity("An");
        Integer number = identity(42);
        Boolean flag = identity(true);

        System.out.println("name=" + name);
        System.out.println("number=" + number);
        System.out.println("flag=" + flag);
        System.out.println("name length=" + name.length());
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 GenericIdentityDemo.java
java GenericIdentityDemo
~~~

**Stdout:**

~~~text
name=An
number=42
flag=true
name length=2
~~~

There is no `class GenericIdentityDemo<T>`: only the `identity` method owns T. The compiler infers T as String, Integer, and Boolean respectively. Passing `42` and `true` uses **autoboxing** from primitives to their corresponding wrapper types; generic type arguments cannot be primitives such as `int` or `boolean`.

`identity` does not automatically convert an object into any arbitrary type the caller wants. It returns the exact value it received according to the type relationship inferred by the compiler; assigning it to a variable of a specific type must still be valid at compile time.

## 5. Scope of a Method Type Parameter

A method type parameter is scoped to **its corresponding method declaration**: it can be used as the return type, parameter types, generic bounds/throws clauses according to Java rules, and in the method body.

~~~java
class TextService {
    <U> U echo(U input) {
        return input;
    }

    String upper(String input) {
        return input.toUpperCase();
    }
}
~~~

This is a valid class. `echo`'s `U` **does not appear** in `upper`. Each method can choose its own set of type parameters.

**Intentionally non-compiling fragment** if added to TextService:

~~~java
// U invalid(U value) {
//     return value;
// }
~~~

There is no U in scope for `invalid`. Do not confuse a generic type declared on method A with a type name that can be used everywhere in the class.

If methods need to use **the same type determined by the instance**, consider declaring the type parameter on the **class**. If each method call needs an independent type, declare it on the **method**.

## 6. Complete Program 2 — Class Type `T` and Method Type `U`

File **`BoxAndMethodTypeDemo.java`**:

~~~java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    <U> String combine(U extra) {
        return value + " / " + extra;
    }

    <U> U echoExtra(U extra) {
        return extra;
    }
}

public class BoxAndMethodTypeDemo {
    public static void main(String[] args) {
        Box<String> box = new Box<>("Java");

        System.out.println("value=" + box.get());
        System.out.println("number=" + box.combine(17));
        System.out.println("boolean=" + box.combine(true));

        Integer extra = box.echoExtra(25);
        System.out.println("extra=" + extra);
        System.out.println("value again=" + box.get());
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 BoxAndMethodTypeDemo.java
java BoxAndMethodTypeDemo
~~~

**Stdout:**

~~~text
value=Java
number=Java / 17
boolean=Java / true
extra=25
value again=Java
~~~

`Box<String>` determines the class-level `T=String`. The two calls to `combine` use `U=Integer` and then `U=Boolean`; neither call changes T. `echoExtra` can return U, independent of the String value stored in Box.

The method `T get()` **uses the class's T**, even without a `<T>` prefix. This is an important distinction when reading generic APIs.

## 7. When the Class's `T` and a Method's Type Parameter Meet

A generic class often needs a method that both uses **state of type T** and accepts **a type U from the caller**.

~~~java
final class Store<T> {
    private final T item;

    Store(T item) {
        this.item = item;
    }

    <U> String describe(U note) {
        return "item=" + item + ", note=" + note;
    }
}
~~~

This is a valid class. `describe` uses T through `item` and uses U through `note`.

**Design example:** a repository storing `Entity` might have a method `<R> R map(Function<? super Entity,? extends R>)`: Entity is the data type managed by the repository instance; R is the output type specific to **each transformation**. The two levels of type parameters exist because they solve two independent problems.

If you put both T and R on the class just because one method returns R, every caller may have to carry R unnecessarily across the entire class type. Place a type parameter in the **narrowest meaningful scope**.

## 8. Complete Program 3 — Mapping from the Class's `T` to the Method's `R`

File **`GenericMapMethodDemo.java`**:

~~~java
import java.util.function.Function;

final class Holder<T> {
    private final T value;

    Holder(T value) {
        this.value = value;
    }

    <R> R map(Function<? super T, ? extends R> mapper) {
        return mapper.apply(value);
    }
}

public class GenericMapMethodDemo {
    public static void main(String[] args) {
        Holder<String> holder = new Holder<>("hello");

        Integer length = holder.map(String::length);
        String upper = holder.map(String::toUpperCase);
        Boolean longText = holder.map(s -> s.length() > 3);

        System.out.println("length=" + length);
        System.out.println("upper=" + upper);
        System.out.println("long=" + longText);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 GenericMapMethodDemo.java
java GenericMapMethodDemo
~~~

**Stdout:**

~~~text
length=5
upper=HELLO
long=true
~~~

`Holder<String>` keeps T as String; each `map` has a different R: Integer, String, Boolean. `Function<? super T, ? extends R>` expresses a useful variance relationship: the mapper **consumes a T** and **produces an R**.

`map` only *returns* an R value; it does not convert Holder<String> into Holder<R>. That is why R belongs to the method, not the entire class.

## 9. `static` Methods Cannot Use Instance Type Parameters

Consider:

~~~java
class Container<T> {
    private final T item;

    Container(T item) {
        this.item = item;
    }
}
~~~

In a generic class, the type parameter `T` belongs to the **instance-level generic type context**; static members cannot directly depend on the `T` of a specific instance.

**Intentionally fails to compile** if written inside Container:

~~~java
// static T invalid(T value) {
//     return value;
// }
~~~

Fix it with a method that declares its own type parameter:

~~~java
static <U> Container<U> of(U item) {
    return new Container<>(item);
}
~~~

This is a valid **method snippet** when placed inside Container. `U` belongs to the static method, and the compiler can infer U at each call site.

There is no contradiction: `Container<String>` and `Container<Integer>` can use the same static generic factory because type U is chosen when calling the method, rather than being "read" from a class-level T used in the wrong context by a static member.

## 10. Complete Program 4 — Static Generic Factory Method

File **`StaticGenericFactoryDemo.java`**:

~~~java
final class Container<T> {
    private final T item;

    private Container(T item) {
        this.item = item;
    }

    static <U> Container<U> of(U value) {
        return new Container<>(value);
    }

    T get() {
        return item;
    }
}

public class StaticGenericFactoryDemo {
    public static void main(String[] args) {
        Container<String> title = Container.of("Java");
        Container<Integer> count = Container.of(3);

        System.out.println("title=" + title.get());
        System.out.println("count=" + count.get());
        System.out.println("same raw class="
                + (title.getClass() == count.getClass()));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 StaticGenericFactoryDemo.java
java StaticGenericFactoryDemo
~~~

**Stdout:**

~~~text
title=Java
count=3
same raw class=true
~~~

The factory `of` declares its own U. The `Container<U>` type in the return type matches the argument received. Because of **type erasure**, `Container<String>` and `Container<Integer>` do not create two separate runtime classes; the `getClass()==` comparison returns true.

The `same raw class` output does not say the two Container objects are the same: it only says they have the same runtime class after erasure.

## 11. Type Inference When Calling a Generic Method

With:

~~~java
static <T> T choose(T first, T second) {
    return first;
}
~~~

placed in a class, the compiler needs to decide **what T is for a specific invocation**. It uses constraints from the arguments and sometimes the **target type** (the type of the assigned variable, target parameter, or return context).

~~~java
String first = choose("A", "B");
Number second = choose(10, 2.5);
~~~

This is a valid snippet when the method is in an appropriate scope. With two Strings, T can be String; with Integer and Double, a suitable common type such as Number/superinterfaces may participate in inference. Avoid relying on complex inference as if it "picks a single parent class" as the reader expects; the compiler applies the JLS inference rules.

**Do not infer from the name T that only one T exists for the entire program.** The type variable T in the declaration is a symbol that is **substituted according to constraints** separately for each invocation.

If inference is hard to read, you can declare a local variable with an explicit type or provide explicit type arguments.

## 12. Type Witness: Passing Type Arguments Explicitly

Normally, calling:

~~~java
String text = GenericIdentityDemo.identity("A");
~~~

This is a valid statement when using the GenericIdentityDemo class from the previous program. The compiler infers T = String.

You can also use an **explicit type witness**:

~~~java
String text = GenericIdentityDemo.<String>identity("A");
~~~

`<String>` appears **after the dot and before the method name**, not after the method name and not as a runtime parameter.

For a static method in the same class, you can call it as `ClassName.<Type>method(args)`; for an instance method, `receiver.<Type>method(args)` is also valid. Do not confuse this with the method declaration `<T> T identity(...)`: the declaration places it before the return type, whereas an invocation has the type witness positioned after the qualifier.

A type witness is useful when the compiler cannot infer the desired type or to express intent; **do not use it merely out of habit of writing generic types inside `<>`**, when inference is already clear.

## 13. Complete Program 5 — Inference and Type Witness

File **`GenericTypeInferenceDemo.java`**:

~~~java
public class GenericTypeInferenceDemo {
    static <T> T first(T a, T b) {
        return a;
    }

    static <T> T defaultValue(T fallback) {
        return fallback;
    }

    public static void main(String[] args) {
        String inferred = first("An", "Binh");
        String explicit =
                GenericTypeInferenceDemo.<String>first("A", "B");
        Number number =
                GenericTypeInferenceDemo.<Number>first(7, 2.5);

        System.out.println("inferred=" + inferred);
        System.out.println("explicit=" + explicit);
        System.out.println("number=" + number);

        String defaultName =
                GenericTypeInferenceDemo.<String>
                        defaultValue("guest");
        System.out.println("default=" + defaultName);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 GenericTypeInferenceDemo.java
java GenericTypeInferenceDemo
~~~

**Stdout:**

~~~text
inferred=An
explicit=A
number=7
default=guest
~~~

`<Number>` specifies T as Number and allows Integer/Double objects to be passed in through the subtype relationship. The `first` method returns the first parameter; `System.out.println` prints the Integer 7 as the character `7`.

An explicit call helps make intent readable, but **does not create an arbitrary runtime cast**. If you write `<String>first(7,8)`, the compiler will not accept Integer arguments as String.

## 14. A Generic Method with Multiple Type Parameters

When input and output do not necessarily have the same type, a method can declare `<A, B>`, `<K, V>`, `<T, R>`:

~~~java
static <A, B> Entry<A, B> entry(A first, B second) {
    return new Entry<>(first, second);
}
~~~

This is a method snippet, assuming `record Entry<A,B>(A first,B second) {}` is in the same scope.

`A` and `B` are **two separate type variables**. A call `entry("id", 10)` can have the type `Entry<String,Integer>`. This differs from a `<T> Pair<T,T>` method, which constrains both fields to the same type variable, even though the compiler might infer a common supertype for arguments of different types.

However, seeing two parameters in a method does not automatically mean you must use two type variables. If they truly must share the same domain type, use a single `T` to express that constraint.

## 15. Complete Program 6 — Generic Method Returning a Record with Two Type Parameters

File **`TwoMethodTypesDemo.java`**:

~~~java
record Entry<A, B>(A key, B value) {
}

public class TwoMethodTypesDemo {
    static <K, V> Entry<K, V> pair(K key, V value) {
        return new Entry<>(key, value);
    }

    public static void main(String[] args) {
        Entry<String, Integer> score = pair("An", 90);
        Entry<Integer, Boolean> flag = pair(1, true);

        System.out.println("score=" + score);
        System.out.println("flag=" + flag);
        System.out.println("key uppercase="
                + score.key().toUpperCase());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 TwoMethodTypesDemo.java
java TwoMethodTypesDemo
~~~

**Stdout:**

~~~text
score=Entry[key=An, value=90]
flag=Entry[key=1, value=true]
key uppercase=AN
~~~

Type inference determines K/V for each call. The record type and method type parameters are **two independent declaration levels**: record Entry<A,B> defines the container structure; method pair<K,V> defines a generic factory that can create different instantiations.

## 16. Naming Type Parameters for Clarity

By common Java convention:

| Name | Common meaning |
| --- | --- |
| `T` | General type |
| `E` | Element |
| `K` | Key |
| `V` | Value |
| `R` | Result/return |
| `U` | Additional type, independent of T |
| `N` | Number subtype |
| `S` | Source |

Single-letter names work well for short generic algorithms. For complex APIs, sometimes a longer name is still valid and easier to read, but avoid confusing names such as using `T` as both a class parameter and a method parameter.

**There is no magic constraint based on naming.** `<N>` by itself **does not mean N extends Number**. To restrict it, you must declare `<N extends Number>`.

## 17. Bounded Generic Methods: `<T extends SomeType>`

A generic method without an explicit bound essentially has an upper bound of `Object`. If you need to call APIs of Number or Comparable, declare an **upper bound**.

~~~java
static <N extends Number> double doubleValue(N number) {
    return number.doubleValue();
}
~~~

The method snippet above is valid inside a class. It accepts Integer, Long, Double, BigDecimal, and compatible subclasses of Number; it does not accept String as a valid argument.

Inside the method, the compiler knows N **is a subtype of Number**, so it permits `number.doubleValue()`.

**What a bound does not do:** `<N extends Number>` does not allow adding `N + N` like general primitive arithmetic; nor does it guarantee every Number subtype is accurately represented as a double without losing precision. `doubleValue()` is only a conversion method that may lose information for large numbers/BigDecimal.

Because Java generics do not accept primitive type arguments, `<Integer>` is the wrapper form when passing `int`.

## 18. Complete Program 7 — Method with a Number Bound

File **`BoundedGenericNumberDemo.java`**:

~~~java
public class BoundedGenericNumberDemo {
    static <N extends Number> double twice(N number) {
        return number.doubleValue() * 2;
    }

    static <N extends Number> String typeAndValue(N number) {
        return number.getClass().getSimpleName()
                + ":" + number.doubleValue();
    }

    public static void main(String[] args) {
        System.out.println("int twice=" + twice(4));
        System.out.println("double twice=" + twice(1.5));
        System.out.println("long=" + typeAndValue(7L));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 BoundedGenericNumberDemo.java
java BoundedGenericNumberDemo
~~~

**Stdout:**

~~~text
int twice=8.0
double twice=3.0
long=Long:7.0
~~~

`twice(4)` receives an Integer via boxing, and `twice(1.5)` receives a Double. Both satisfy `N extends Number`. This is an example of a generic algorithm using the Number API, not a way to perform exact arithmetic for every numeric domain.

## 19. A Method with Multiple Upper Bounds

Java allows intersection bounds:

~~~java
static <T extends Number & Comparable<T>> boolean atLeast(
        T value, T minimum) {
    return value.compareTo(minimum) >= 0;
}
~~~

This method snippet is valid inside a class. `Number` is the leading **class bound**; `Comparable<T>` is the interface bound following it. The type argument must satisfy **both**.

General rules:
- A class bound (if any) must come before interface bounds.
- Multiple interface bounds can be used, separated by `&`.
- Two independent class bounds cannot be listed because Java does not have multiple class inheritance.
- The bound determines which operations are allowed to be called inside the method; it does not turn T into a primitive.

For example, Integer both extends Number and implements Comparable<Integer>, so it can be used. However, this does not mean every Number subclass is Comparable with its own type.

## 20. Complete Program 8 — Intersection Bounds

File **`IntersectionBoundDemo.java`**:

~~~java
public class IntersectionBoundDemo {
    static <T extends Number & Comparable<T>>
            T larger(T first, T second) {
        return first.compareTo(second) >= 0
                ? first : second;
    }

    public static void main(String[] args) {
        Integer a = larger(3, 7);
        Long b = larger(10L, 4L);
        Double c = larger(2.5, 2.5);

        System.out.println("integers=" + a);
        System.out.println("longs=" + b);
        System.out.println("doubles=" + c);
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 IntersectionBoundDemo.java
java IntersectionBoundDemo
~~~

**Stdout:**

~~~text
integers=7
longs=10
doubles=2.5
~~~

When two values are equal according to `compareTo`, the method returns first; the result `2.5` is deterministic. `Number` provides numeric operations if needed, while `Comparable<T>` enables ordering comparisons with the same T.

If the problem only needs Comparable and does not need Number, the Number bound is **unnecessary**; constrain the API just enough.

## 21. Generic Methods and Wildcards: Both Type-Related, Different Roles

Two methods:

~~~java
static void printAll(java.util.List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
~~~

~~~java
static <T> void printTyped(java.util.List<T> values) {
    for (T value : values) {
        System.out.println(value);
    }
}
~~~

These are two separate valid method snippets when placed in a class.

`List<?>` uses a **wildcard**: the caller can pass List<String> or List<Integer>, but the method does not declare a named type parameter T to link with the return type or another parameter.

`<T> void printTyped(List<T>)` has a **named type variable T** for the entire method. In the case where you only need to read each value and print it, the generic T **adds no useful type relationship**; `List<?>` is usually simpler.

Selection rules:
- Use a wildcard when you only need to **accept a range of types** and do not need to relate multiple positions.
- Use a method type parameter when you want to express a **relationship** between input–input, input–output, or across multiple generic parameters.

Do not assume that adding `<T>` always makes an API "safer" than a wildcard: each approach solves a different problem.

## 22. Relating Multiple Parameters Using the Same Type Variable

Consider:

~~~java
static <T> void copy(
        java.util.List<? super T> destination,
        java.util.List<? extends T> source) {
    for (T value : source) {
        destination.add(value);
    }
}
~~~

This is a valid generic method snippet inside a class. The method type T **links** the two Lists: source produces T-compatible values; destination accepts T values.

`? extends T` expresses a **producer**, and `? super T` expresses a **consumer** — a rule commonly remembered as **PECS** (*Producer Extends, Consumer Super*).

For example, List<Integer> can serve as the source and List<Number> as the destination, even though `List<Integer>` is **not** a subtype of `List<Number>`. There is no unsafe cast here.

The bounds in a generic method allow the compiler to check type relationships that an independent pair of `List<?>` parameters cannot express.

## 23. Complete Program 9 — PECS with a Separate Type Parameter

File **`GenericCopyMethodDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class GenericCopyMethodDemo {
    static <T> void copy(
            List<? super T> target,
            List<? extends T> source) {
        for (T element : source) {
            target.add(element);
        }
    }

    public static void main(String[] args) {
        List<Integer> source = List.of(2, 4, 6);
        List<Number> destination = new ArrayList<>();

        copy(destination, source);

        System.out.println("destination=" + destination);
        System.out.println("size=" + destination.size());
        System.out.println("sum="
                + (destination.get(0).intValue()
                   + destination.get(1).intValue()
                   + destination.get(2).intValue()));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 GenericCopyMethodDemo.java
java GenericCopyMethodDemo
~~~

**Stdout:**

~~~text
destination=[2, 4, 6]
size=3
sum=12
~~~

Integers are boxed into List<Integer>. During the copy, generic constraints ensure that the Integer values can be added to List<Number>. This is not a "cast of List<Integer> to List<Number>" (such a cast has incorrect semantics).

**Practical note:** this simple method does not attempt to handle cases where `source == destination`, concurrently modified collections, or rollback when add fails. Generic type safety does not by itself provide transaction or concurrency guarantees.

## 24. Invariance and Common Type Errors

Java generic classes such as `List<E>` are **invariant** in E: even though Integer extends Number, `List<Integer>` is not a subtype of `List<Number>`.

**Intentionally fails to compile:**

~~~java
// List<Number> values = new ArrayList<Integer>();
~~~

If this were allowed, a caller could add a Double to an ArrayList<Integer>, breaking the element type contract.

Use a wildcard if you want to accept a group of lists:

~~~java
List<? extends Number> readable =
        new ArrayList<Integer>();
~~~

This is a valid snippet with imports. Elements can be read as Number, but you cannot arbitrarily call `readable.add(3)` because the actual type of the list might be another Number subtype.

If you need to both read from List<Integer> and write to List<Number>, the method can declare a type relationship as in the copy example with `<T>`, `? extends T`, and `? super T`.

## 25. Generic Type Parameter Shadowing in a Generic Class

Java allows a **method type parameter with the same name** as a class type parameter; the type name inside the method **shadows** the class's type name. Although it compiles in appropriate situations, this is a source of confusion.

~~~java
class Outer<T> {
    private final T value;

    Outer(T value) {
        this.value = value;
    }

    <T> T echo(T input) {
        return input;
    }
}
~~~

This is a **valid class**. `T` in the declaration `<T> T echo(T input)` is the **method's T**, not Outer's T. Meanwhile, the `value` field keeps the class's T.

For example, with `Outer<String> outer`, you can call `Integer n = outer.echo(5)`, because echo's T is inferred as Integer.

**Recommendation:** if a method uses a type different from the class-level T, name it `<U>` or `<R>` instead of redeclaring `<T>`. That way `T` always has a consistent meaning during code review, and the difference in level is not hidden.

## 26. Complete Program 10 — Same Name T but Two Scopes

File **`TypeParameterShadowDemo.java`**:

~~~java
final class Outer<T> {
    private final T value;

    Outer(T value) {
        this.value = value;
    }

    T stored() {
        return value;
    }

    <T> T echo(T input) {
        return input;
    }
}

public class TypeParameterShadowDemo {
    public static void main(String[] args) {
        Outer<String> outer = new Outer<>("text");
        Integer result = outer.echo(99);

        System.out.println("stored=" + outer.stored());
        System.out.println("echo=" + result);
        System.out.println("stored class="
                + outer.stored().getClass().getSimpleName());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 TypeParameterShadowDemo.java
java TypeParameterShadowDemo
~~~

**Stdout:**

~~~text
stored=text
echo=99
stored class=String
~~~

The run proves that `echo`'s `T` is not constrained to String by `Outer<String>`. However, even though Java allows it, writing `<U> U echo(U input)` is usually a more readable choice.

## 27. How Does Type Erasure Affect Generic Methods?

Java generics are primarily checked at **compile time**. During compilation, type parameters undergo **type erasure**:

- An unbounded T typically has Object as its erasure.
- `T extends Number` has Number as its erasure.
- Parameterized types are represented by their corresponding raw runtime class; there may be casts inserted by the compiler at call sites.
- Type arguments such as `String` and `Integer` do not become a separate runtime method/class copy for each case.

For example, `static <T> T identity(T input)` has an erased form close to `Object identity(Object input)`. This is a mental model for the bytecode signature, not a requirement for learners to write raw Object APIs as a replacement.

Compilation error cases caused by erasure:
- Two generic overloads have the **same erasure**.
- Attempting to check `instanceof T` with a regular method type variable.
- Attempting to instantiate `new T()` from the type parameter alone.
- Attempting to create `new T[10]` when T is non-reifiable.

Because Java checks at compile time and then erases, a generic method does not allow full direct inspection of T at runtime.

## 28. Complete Program 11 — Looking at the Runtime Class After Erasure

File **`MethodErasureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class MethodErasureDemo {
    static <T> String inspect(T value) {
        return value.getClass().getSimpleName();
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        List<Integer> numbers = new ArrayList<>();

        System.out.println("name type=" + inspect("Java"));
        System.out.println("number type=" + inspect(12));
        System.out.println("same list class="
                + (names.getClass() == numbers.getClass()));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 MethodErasureDemo.java
java MethodErasureDemo
~~~

**Stdout:**

~~~text
name type=String
number type=Integer
same list class=true
~~~

The `inspect` method does not know "generic T=String" through any runtime token T: it simply calls `getClass()` on the actual object passed in. Both ArrayList instantiations share the same runtime class despite having different compile-time element types.

**Limitation of the demo:** `inspect(null)` will throw an NPE due to `value.getClass()`, not because generics forbid null. When using generic methods with nullable values, you must define a separate null policy.

## 29. The `new T()` Limitation and Passing a Factory

A method type parameter is **not enough** to create an instance of type T:

~~~java
// INTENTIONALLY DOES NOT COMPILE:
// static <T> T create() {
//     return new T();
// }
~~~

Java does not know which constructor of T is valid at runtime from an erased type variable alone.

If the caller is able to supply the object, you can pass a **factory function** such as `Supplier<T>`:

~~~java
static <T> T create(java.util.function.Supplier<? extends T> factory) {
    return factory.get();
}
~~~

This is a valid method snippet. The caller explicitly specifies how to construct it:

~~~java
StringBuilder buffer = create(StringBuilder::new);
~~~

This is a valid snippet if create is in scope; `StringBuilder::new` is a constructor reference. The generic method's T is inferred as StringBuilder based on the supplier and the target type.

If you need runtime reflection via `Class<T>`, accept an explicit class token and handle constructor accessibility/checked exceptions according to the API's policy; **do not assume every class has a public no-arg constructor**.

## 30. Complete Program 12 — Creating T via `Supplier`

File **`GenericSupplierDemo.java`**:

~~~java
import java.util.function.Supplier;

public class GenericSupplierDemo {
    static <T> T create(Supplier<? extends T> factory) {
        return factory.get();
    }

    static <T> T build(
            Supplier<? extends T> factory,
            java.util.function.Consumer<? super T> setup) {
        T object = factory.get();
        setup.accept(object);
        return object;
    }

    public static void main(String[] args) {
        StringBuilder empty = create(StringBuilder::new);
        StringBuilder configured = build(
                StringBuilder::new,
                builder -> builder.append("Java"));

        System.out.println("empty length=" + empty.length());
        System.out.println("configured=" + configured);
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 GenericSupplierDemo.java
java GenericSupplierDemo
~~~

**Stdout:**

~~~text
empty length=0
configured=Java
~~~

`Supplier<? extends T>` produces a T-compatible object. `Consumer<? super T>` accepts T to configure it. Using this method type parameter does not require the enclosing class to declare T.

**Do not treat the create function as safe construction in all cases:** the factory may throw an exception, return null, or create a mutable object; generic constraints only check type relationships.

## 31. The `Class<T>` Token Helps Link Compile-Time and Runtime Types

When you need to check/cast an object against a class provided by the caller, accept a `Class<T>`:

~~~java
static <T> T checkedCast(Class<T> type, Object value) {
    return type.cast(value);
}
~~~

This is a valid method snippet. `type.cast(value)` checks whether the runtime object is compatible with the Class token; otherwise, it throws ClassCastException.

Compared to `(T) value`, `Class<T>.cast` has a runtime check tied to an explicit token and avoids an arbitrary unchecked cast. However, `Class<List<String>>` in the sense of a class literal carrying full generic arguments **does not exist**. A class token typically knows only the raw runtime class, not the deep element type of List<T> after erasure.

**Intentionally fails to compile:**

~~~java
// Class<java.util.List<String>> type =
//         java.util.List<String>.class;
~~~

Do not expect `Class<T>` to handle all validation of nested generic values.

## 32. Complete Program 13 — Checked Cast with a Class Token

File **`GenericClassTokenDemo.java`**:

~~~java
public class GenericClassTokenDemo {
    static <T> T checkedCast(Class<T> type, Object value) {
        return type.cast(value);
    }

    public static void main(String[] args) {
        Object source = "hello";

        String text = checkedCast(String.class, source);
        System.out.println("text=" + text);

        try {
            Integer number =
                    checkedCast(Integer.class, source);
            System.out.println("number=" + number);
        } catch (ClassCastException ex) {
            System.out.println("mismatch="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 GenericClassTokenDemo.java
java GenericClassTokenDemo
~~~

**Stdout:**

~~~text
text=hello
mismatch=ClassCastException
~~~

String.class and Integer.class are two different class tokens. If the object does not belong to the requested type, `Class.cast` reports a runtime error; the compiler still infers the corresponding return type T from Class<T>.

## 33. Generic Method Overloads and Type Erasure

Overloading is based on **method signatures**, not just on names. A generic method and a regular method can validly overload each other when their parameters differ after erasure:

~~~java
static String describe(String text) {
    return "string:" + text;
}

static <T> String describe(T value) {
    return "generic:" + value;
}
~~~

These are two valid method snippets inside a class. The String overload is more specific for a String argument; the generic overload can be called with Integer or Boolean.

However, the following declarations **intentionally fail to compile if they appear together**:

~~~java
// static <T> void consume(T value) {}
// static void consume(Object value) {}
~~~

The first generic method has an erasure accepting Object; the second method also accepts Object, causing a name clash.

Another pair that **intentionally fails to compile**:

~~~java
// static void use(java.util.List<String> x) {}
// static void use(java.util.List<Integer> x) {}
~~~

After erasure, both accept List. You cannot overload solely by generic type arguments.

## 34. Complete Program 14 — Specific and Generic Overloads

File **`GenericOverloadDemo.java`**:

~~~java
public class GenericOverloadDemo {
    static String describe(String text) {
        return "string:" + text;
    }

    static <T> String describe(T value) {
        return "generic:" + value;
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(10));
        System.out.println(describe(true));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 GenericOverloadDemo.java
java GenericOverloadDemo
~~~

**Stdout:**

~~~text
string:Java
generic:10
generic:true
~~~

The line with String selects the overload taking String because it is more specific. The lines with Integer and Boolean use the generic overload.

**Do not assume the generic overload is always chosen for being "more flexible".** Java has overload resolution rules based on applicable methods, invocation phases, and specificity; when an API has multiple overloads alongside generic inference, write compile-time tests for important call sites.

## 35. Generics and Primitive Values

Java does not allow using primitive types directly as generic type arguments:

~~~java
// INTENTIONALLY DOES NOT COMPILE:
// List<int> values = new ArrayList<int>();
// GenericIdentityDemo.<int>identity(5);
~~~

You need wrapper types:

~~~java
java.util.List<Integer> values =
        java.util.List.of(1, 2, 3);
~~~

This is a valid snippet; int literals are boxed into Integer. With the generic method `<T> T identity(T input)`, a caller can still pass the primitive `5` because **autoboxing** creates an Integer.

However, boxing/unboxing has overhead and can throw NullPointerException when unboxing a null wrapper. In code processing millions of primitive elements, specializing with `int[]`, primitive streams, or dedicated primitive APIs may be more suitable than generic containers.

A generic method type parameter does not "support primitives" merely because the compiler accepts an integer expression.

## 36. Generic Varargs and Heap Pollution

A generic method can accept varargs:

~~~java
@SafeVarargs
static <T> java.util.List<T> immutable(T... elements) {
    return java.util.List.of(elements);
}
~~~

This is a **valid method snippet if placed inside a class**. `T...` is represented by an array parameter. Generic varargs can produce **compiler warnings** because arrays have runtime component types whereas most parameterized generic types are non-reifiable.

`@SafeVarargs` is a commitment by the author that the implementation **does not perform unsafe operations** on the generic varargs array, such as writing an object of the wrong type through an Object[] alias. The annotation does not by itself make a method safe if the body actually violates the contract. In Java 17, this annotation is allowed on static, final, and appropriate private instance methods; do not use it arbitrarily on overridable instance methods.

At the call site, `immutable("A","B")` infers T=String and creates a List that does not support mutation. If the method receives null elements, `List.of` throws NullPointerException as part of its contract.

## 37. Complete Program 15 — Safe Generic Varargs

File **`GenericVarargsDemo.java`**:

~~~java
import java.util.List;

public class GenericVarargsDemo {
    @SafeVarargs
    static <T> List<T> immutable(T... elements) {
        return List.of(elements);
    }

    public static void main(String[] args) {
        List<String> names = immutable("An", "Binh");
        List<Integer> numbers = immutable(1, 2, 3);

        System.out.println("names=" + names);
        System.out.println("numbers=" + numbers);
        System.out.println("count=" + numbers.size());

        try {
            names.add("Chi");
        } catch (UnsupportedOperationException ex) {
            System.out.println("mutation blocked=true");
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 GenericVarargsDemo.java
java GenericVarargsDemo
~~~

**Stdout:**

~~~text
names=[An, Binh]
numbers=[1, 2, 3]
count=3
mutation blocked=true
~~~

`List.of` preserves the order of the input elements. In this method, we do not assign elements of another type into the varargs array and do not expose the mutable array; the annotation fits that simple implementation.

`@SafeVarargs` is **not** a way to silence warnings regardless of how dangerous the code is. If the body converts `T[]` to `Object[]` and then writes the wrong runtime type, it can lead to an ArrayStoreException or heap pollution even though the method is annotated.

## 38. Generic Methods in a `record`

A record can be generic or non-generic. It can still declare methods with their own type parameters:

~~~java
record Pair<A, B>(A first, B second) {
    <R> R combine(
            java.util.function.BiFunction<
                    ? super A, ? super B, ? extends R> mapper) {
        return mapper.apply(first, second);
    }
}
~~~

This is a valid record. A/B belong to the **Pair record**, while R belongs to the **combine method**. Callers can combine the same Pair<String,Integer> in multiple ways returning String, Boolean, or another DTO.

With a non-generic record `record Point(int x,int y)`, you can still declare `<R> R map(BiFunction<Integer,Integer,R> mapper)`, because a generic method does not require a generic class.

**Do not confuse a generic method with a generic constructor:** a record's constructor has a canonical signature matching the record components, with its own JLS constraints. If the learning problem is simply processing/transforming values, a method type parameter is the more straightforward solution.

## 39. Complete Program 16 — Generic Method of a Generic Record

File **`GenericRecordMethodDemo.java`**:

~~~java
import java.util.function.BiFunction;

record Pair<A, B>(A first, B second) {
    <R> R combine(
            BiFunction<? super A, ? super B, ? extends R> mapper) {
        return mapper.apply(first, second);
    }
}

public class GenericRecordMethodDemo {
    public static void main(String[] args) {
        Pair<String, Integer> score = new Pair<>("An", 90);

        String label =
                score.combine((name, points) ->
                        name + "=" + points);
        Boolean passed =
                score.combine((name, points) -> points >= 50);
        Integer doubled =
                score.combine((name, points) -> points * 2);

        System.out.println("label=" + label);
        System.out.println("passed=" + passed);
        System.out.println("doubled=" + doubled);
        System.out.println("pair=" + score);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 GenericRecordMethodDemo.java
java GenericRecordMethodDemo
~~~

**Stdout:**

~~~text
label=An=90
passed=true
doubled=180
pair=Pair[first=An, second=90]
~~~

A=String and B=Integer are determined by the Pair instance. `combine`'s R is String, Boolean, and Integer respectively; none of the calls modifies score's components.

## 40. Methods with Separate Type Parameters and Generic Constructors Are Two Different Mechanisms

A generic class can have a constructor that uses the class-level T:

~~~java
final class Wrapper<T> {
    private final T value;

    Wrapper(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
~~~

This is a valid class. The constructor accepts the **class's** T; it does not declare a new type parameter of its own.

A **generic constructor** can also exist in a regular class, by declaring a type parameter before the constructor name:

~~~java
final class TaggedValue<T> {
    private final T value;
    private final String tag;

    <U> TaggedValue(T value, U tag) {
        this.value = value;
        this.tag = String.valueOf(tag);
    }

    T get() {
        return value;
    }

    String tag() {
        return tag;
    }
}
~~~

This is a valid class. T belongs to the class, and U belongs to the constructor. Each constructor call can infer U separately, similar to a generic method, except a constructor does not declare a return type. Recognizing generic constructors helps avoid mistaking `<U>` before the constructor name for a method with a missing return type.

## 41. Complete Program 17 — Class Type and Separate Constructor Type

File **`GenericConstructorScopeDemo.java`**:

~~~java
final class TaggedValue<T> {
    private final T value;
    private final String tag;

    <U> TaggedValue(T value, U tag) {
        this.value = value;
        this.tag = String.valueOf(tag);
    }

    T value() {
        return value;
    }

    String tag() {
        return tag;
    }
}

public class GenericConstructorScopeDemo {
    public static void main(String[] args) {
        TaggedValue<String> first =
                new TaggedValue<>("Java", 17);
        TaggedValue<Integer> second =
                new TaggedValue<>(5, true);

        System.out.println("first="
                + first.value() + ":" + first.tag());
        System.out.println("second="
                + second.value() + ":" + second.tag());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 GenericConstructorScopeDemo.java
java GenericConstructorScopeDemo
~~~

**Stdout:**

~~~text
first=Java:17
second=5:true
~~~

TaggedValue's T is determined by the declared type/diamond inference of each instance; the constructor's U is inferred from the argument `17` or `true`. A generic constructor can use its own type parameter even when the enclosing class is also generic.

**Key distinction:** a generic method declares `<U>` before the **return type**; a generic constructor declares `<U>` before the **constructor name** and has no return type.

## 42. Wildcard Capture and a Helper Method Using `<T>`

There are APIs that accept `List<?>` yet need to operate on **a specific element type within the same list**. A private generic helper can **capture the wildcard** into a named type variable T to link the relationship across operations.

For example:

~~~java
static void swapFirstTwo(java.util.List<?> list) {
    swapFirstTwoCaptured(list);
}

private static <T> void swapFirstTwoCaptured(
        java.util.List<T> list) {
    T first = list.get(0);
    list.set(0, list.get(1));
    list.set(1, first);
}
~~~

These two method snippets are valid in a class; they assume the list has at least two elements and supports `set`. If the list is `List.of(...)`, `set` will throw UnsupportedOperationException; if the list has fewer than two elements, `get` will throw IndexOutOfBoundsException.

The generic helper establishes that `get(0)` and `set(1,...)` both use **the same captured element type T**. This is a case where a method type parameter is useful even when the public API only exposes `List<?>`.

**Do not use a raw List and arbitrary Object casts** to "solve" wildcards not allowing add/set easily: raw types bypass the type checking that the compiler is protecting.

## 43. Complete Program 18 — Wildcard Capture with a Helper

File **`WildcardCaptureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class WildcardCaptureDemo {
    static void swapFirstTwo(List<?> items) {
        if (items.size() < 2) {
            throw new IllegalArgumentException(
                    "need at least two");
        }
        swapCaptured(items);
    }

    private static <T> void swapCaptured(List<T> items) {
        T first = items.get(0);
        items.set(0, items.get(1));
        items.set(1, first);
    }

    public static void main(String[] args) {
        List<String> names =
                new ArrayList<>(List.of("An", "Binh"));
        List<Integer> numbers =
                new ArrayList<>(List.of(1, 2));

        swapFirstTwo(names);
        swapFirstTwo(numbers);

        System.out.println("names=" + names);
        System.out.println("numbers=" + numbers);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 WildcardCaptureDemo.java
java WildcardCaptureDemo
~~~

**Stdout:**

~~~text
names=[Binh, An]
numbers=[2, 1]
~~~

The public method uses a wildcard to accept any List element type; the private helper uses generic T so the compiler knows the two `set` calls do not accidentally insert a new type into the list.

## 44. Methods with Separate Type Parameters and Inheritance/Overriding

A generic method can be declared in a superclass or interface. When a subclass overrides it, it must conform to the appropriate **method signature and type parameter bounds**; you cannot arbitrarily replace a generic method with an overload differing only in type name and expect it to be an override.

For example:

~~~java
interface Converter {
    <T> T same(T value);
}

final class SimpleConverter implements Converter {
    @Override
    public <U> U same(U value) {
        return value;
    }
}
~~~

This is a valid declaration. The type parameter name T/U **is not what determines the identity of the method**; the signatures are compatible after renaming type variables according to Java rules.

A separate `String same(String s)` method does not replace `<T> T same(T)`: the generic method must accept many types T, not only String.

Add `@Override` so the compiler verifies that you are actually overriding; do not use raw types to force the compiler to bypass the generic contract.

## 45. Complete Program 19 — Overriding a Generic Method

File **`GenericOverrideDemo.java`**:

~~~java
interface Converter {
    <T> T same(T value);
}

final class SimpleConverter implements Converter {
    @Override
    public <U> U same(U value) {
        return value;
    }
}

public class GenericOverrideDemo {
    public static void main(String[] args) {
        Converter converter = new SimpleConverter();

        String text = converter.same("Java");
        Integer number = converter.same(17);

        System.out.println("text=" + text);
        System.out.println("number=" + number);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 GenericOverrideDemo.java
java GenericOverrideDemo
~~~

**Stdout:**

~~~text
text=Java
number=17
~~~

The compiler treats the generic method `<U> U same(U)` as a valid implementation of `<T> T same(T)`, even though the symbol names differ. The interface type Converter preserves the generic contract for each invocation.

## 46. Anti-Patterns to Avoid

| Common mistake | Why it is wrong or hard to maintain | How to fix |
| --- | --- | --- |
| Writing `T method(...)` without declaring T in scope | The compiler cannot find the type variable | Declare `<T>` in the right place or use the class's T |
| Using the class's T in a static method | Static context has no class-level T | Use `static <U>` |
| Declaring `<T>` on a method when the class's T is enough | The new T can shadow the old T | Omit `<T>` if only using the class's type |
| Using the same name T for the class and an independent method | Easy to confuse the two scopes when reading | Name the method's parameter U/R |
| Declaring a generic method just to print `List<?>` | Does not link any other types | Use a simple wildcard |
| Writing `new T()` | No runtime constructor token for T | Pass a `Supplier<T>` or factory |
| Writing `new T[n]` | Array creation with non-reifiable T is invalid | Accept an array factory or another safe API |
| `instanceof T` | T undergoes erasure, so there is no direct runtime T class test | Use `Class<T>.isInstance` |
| Overloading `List<String>` and `List<Integer>` | Erasure causes a name clash | Use different method names or a single generic method |
| Assigning `List<Integer>` to `List<Number>` | Generic invariance | Use PECS/wildcards when appropriate |
| `<T extends Number>` yet writing `T + T` | T is a reference type with no general numeric operator | Use a numeric API/define the operation |
| Expecting generic T to be a primitive | Java generics accept reference types | Boxing/wrappers or a primitive API |
| Using `@SafeVarargs` to hide an unsafe implementation | The annotation is a promise, not a bug fix | Use only when the body is genuinely safe |
| Forcing unchecked casts because inference is hard | Risks ClassCastException when using the result | Design a clearer API or pass a Class token |
| Reading a generic signature as a runtime reified type | Erasure strips away regular type arguments | Distinguish compile-time vs runtime clearly |
| Using multiple unrelated method type params | Verbose API, hard to infer | Use wildcards or concrete types |
| Using a raw List to "solve" wildcards | Bypasses type checking | A generic helper capturing the wildcard |
| Assuming a generic method guarantees non-null input | Generics do not forbid null | Validate according to the domain |
| Assuming a generic method automatically makes objects immutable/thread-safe | Unrelated concerns | Handle ownership/concurrency separately |

## 47. How to Read a Generic Method Signature

When encountering the signature:

~~~java
public static <T, R> java.util.List<R> transform(
        java.util.List<? extends T> source,
        java.util.function.Function<? super T, ? extends R> mapper)
~~~

This is an **illustrative signature**, not a standalone program (it has no body yet).

Analyze it in order:

1. `public static`: modifiers.
2. `<T, R>`: **declares method type parameters** T and R; they are not type arguments passed from `class`.
3. `List<R>`: return type, a list of elements of type R.
4. `source`: a List whose elements belong to some subtype of T.
5. `mapper`: a Function that can accept T or a supertype of T and return R or a subtype of R.
6. `transform`: the method name.
7. The compiler infers T/R at each invocation, from source, mapper, and the target type.
8. T/R are checked at compile time; they do not become two separate runtime Class objects just because generics are used.

This way of reading is useful for the Java Collections API, Streams, Optional, Comparators, and collection transformation methods.

## 48. Complete Program 20 — Generic Transform with Independent Source/Output

File **`GenericTransformDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;

public class GenericTransformDemo {
    static <T, R> List<R> transform(
            List<? extends T> source,
            Function<? super T, ? extends R> mapper) {
        List<R> result = new ArrayList<>();
        for (T value : source) {
            result.add(mapper.apply(value));
        }
        return result;
    }

    public static void main(String[] args) {
        List<String> words = List.of("java", "code");
        List<Integer> lengths =
                transform(words, String::length);
        List<String> upper =
                transform(words, String::toUpperCase);

        System.out.println("words=" + words);
        System.out.println("lengths=" + lengths);
        System.out.println("upper=" + upper);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 GenericTransformDemo.java
java GenericTransformDemo
~~~

**Stdout:**

~~~text
words=[java, code]
lengths=[4, 4]
upper=[JAVA, CODE]
~~~

T is String in both calls; R is Integer and String respectively. The method can be reused for many source and output types without modifying its body.

The result is a mutable ArrayList, because the implementation chooses `new ArrayList<>()`. Generics **do not determine** the mutability of a collection.

## 49. Constraints on API, Null, Errors, and Concurrency

Generic methods primarily express **type constraints**; they do not replace other operational contracts:

- **Null:** `<T> T identity(T x)` still accepts null in valid inference contexts; calling a method on x may throw an NPE.
- **Exceptions:** generic bounds do not automatically convert checked exceptions into unchecked ones. The API must still declare/handle them according to Java rules.
- **Mutability:** a method returning `List<T>` might return a mutable ArrayList or an unmodifiable List; it must be documented.
- **Thread safety:** `<T> void add(List<T>, T)` does not make ArrayList thread-safe.
- **Side effects:** the mapper in `transform` may mutate external state or throw an exception; the generic contract does not roll back.
- **Numeric precision:** a Number bound does not make double results exact for all BigDecimal/BigInteger values.
- **Ownership:** returning a T reference may allow the caller to mutate the original object; generic identity does not clone.
- **Unchecked casts:** avoid them without a valid runtime basis, even when simple test cases run.

When designing a generic API, clearly document collection ownership, nullability, exception behavior, and target mutability alongside the generic type signature.

## 50. A Set of Practice Exercises by Level

### Level 1 — Reading Notation

**1.** In `class Box<T> { T get() { ... } }`, does `get` declare its own method type parameter?

**2.** In `<U> U echo(U x)`, does U belong to the class or the method?

**3.** Can you declare `static T get()` inside `class Box<T>` and use the class's T?

**4.** Is the correct order `public <T> T identity(T x)` or `public T <T> identity(T x)`?

**5.** Is `<T> String describe(T x)` a generic method even though the return type does not use T?

**6.** How do `static <T> void print(List<T>)` and `static void print(List<?>)` differ in terms of naming T?

**7.** Where is the type witness `<String>` placed when calling `Util.identity(...)`?

**8.** Does `<N>` automatically guarantee that N extends Number?

### Level 2 — Predicting Type Inference

**9.** Given `static <T> T identity(T x)`, is `Integer x = identity(3)` valid?

**10.** Is `String x = identity(3)` valid if there is no other overload and identity simply returns its parameter?

**11.** Can `Box<String>` call `<U> U echo(U x)` with an Integer argument?

**12.** When `Holder<String>.map(String::length)` returns Integer, does the class-level T change to Integer?

**13.** Can `<K,V> Entry<K,V> pair(K,V)` create an Entry<String,Boolean>?

**14.** Can `List<Integer>` be assigned directly to `List<Number>`?

**15.** Is `List<Integer>` compatible with `List<? extends Number>`?

### Level 3 — Bounds, Erasure, API

**16.** Why does `<N extends Number>` allow `n.doubleValue()`?

**17.** Why does `<N extends Number>` not allow adding `n + n` as an operation for any N?

**18.** In `<T extends Number & Comparable<T>>`, is placing Number after Comparable always valid?

**19.** Why do the overloads `use(List<String>)` and `use(List<Integer>)` cause an error?

**20.** Why is `new T()` invalid inside a generic method?

**21.** Can `Class<T>.cast` check whether List<String> elements are actually Strings using a class token?

**22.** Does a generic method declaring `<T> T method(T x)` mean T is reified into a runtime type argument object?

**23.** Does a `@SafeVarargs` method automatically become safe if its body assigns the wrong type into the varargs array?

**24.** When is `Supplier<T>` more appropriate than `new T()`?

### Level 4 — Design

**25.** If a class holds `T value` and each method call needs to return a different type R, at which level should R be declared?

**26.** If an API only reads a List<?> and prints it, is `<T>` strictly necessary?

**27.** If an API copies List<Integer> to List<Number>, which wildcard relationship should the source/destination parameters use?

**28.** Why should you avoid declaring `<T>` on a method when the class also has T and the two Ts are independent?

**29.** When can a private generic helper solve a wildcard capture problem?

**30.** Can a generic record Pair<A,B> declare a `<R> R combine(...)` method?

**31.** How does a generic constructor `<U> TaggedValue(T value,U tag)` differ from a generic method?

**32.** When introducing generic code into concurrency or mutable collections, do type constraints replace synchronization/defensive copying?

### Answers and Explanations

1. No; get uses the class's T and has no type parameter list of its own.
2. It belongs to the method; it is distinct from a type variable of the same name elsewhere.
3. No; a static context cannot use the class-level T. You need `static <U>` or a concrete type.
4. `public <T> T identity(T x)` has the correct order.
5. Yes; the method owns the type parameter T even though it returns String.
6. The version with `<T>` names a type to link positions; the wildcard has no named T.
7. After the qualifier and before the method name: `Util.<String>identity(x)`.
8. No; you must write `<N extends Number>`.
9. Yes; int is boxed into Integer.
10. No; an int/Integer argument cannot make identity return an arbitrary String.
11. Yes; U belongs to the method, independent of Box's T=String.
12. No; Holder still keeps T=String; map's own R is Integer.
13. Yes; K=String and V=Boolean by inference.
14. No; generic List is invariant.
15. Yes; Integer is a subtype of Number, so the extends wildcard accepts that list.
16. The compiler knows N has Number's methods.
17. Generics do not have a general numeric operator on reference types.
18. No, if Number is a class bound; a class bound must precede any interface bounds.
19. Erasure turns both parameter lists into List.
20. T does not provide a runtime constructor and undergoes type erasure.
21. No; the Class token of raw List does not contain the String element type at runtime.
22. No; erasure does not create a separate instantiated method class for each T.
23. No; the annotation is only a promise by the author.
24. When the caller knows how to instantiate T via a constructor reference/factory function.
25. At the method level: `<R> R map(...)`.
26. Not necessarily; `List<?>` is usually sufficient.
27. `List<? extends T>` for source and `List<? super T>` for destination, with method `<T>`.
28. The method's T shadows the class's T, causing confusion in meaning.
29. When the method needs to read/write consistently using the same captured element type of `List<?>`.
30. Yes. A/B belong to the record, and R belongs to the method.
31. A constructor has no return type and uses the class name; a method has its own return type and name.
32. No; generic type safety does not replace ownership, mutability, or thread safety.

## 51. Checklist When Writing or Reviewing a Generic Method

- [ ] Have you identified whether each type variable belongs to the class or the method?
- [ ] Does the method need a separate type parameter, or does it just use the class's T?
- [ ] If the method is not generic, did you accidentally declare `<T>` and shadow the class's T?
- [ ] Is `<T>` placed **before the return type**, after the modifiers?
- [ ] For a static method, does it avoid referencing the class-level T out of context?
- [ ] Are all type parameters declared and in scope?
- [ ] If multiple type variables are needed, do names like K/V/T/R express the relationships clearly?
- [ ] Is `extends` used appropriately for upper bounds, without confusing them with primitive types?
- [ ] If there are both a class bound and interface bounds, does the class bound come first?
- [ ] Does the method genuinely need a named T, or is a wildcard enough?
- [ ] For producers/consumers, have `? extends T`/`? super T` been chosen according to PECS?
- [ ] Have raw types and unnecessary unchecked casts been avoided?
- [ ] Have overloads that collide after type erasure been avoided?
- [ ] Is type inference understood at key call sites?
- [ ] Are type witnesses used only where they clarify intent or resolve inference?
- [ ] Have `new T()`, `new T[]`, and `instanceof T` been avoided where unsupported?
- [ ] If a runtime type check is needed, is an appropriate Class<T> token provided and are erasure limits understood?
- [ ] For generic varargs, is the implementation genuinely safe before adding @SafeVarargs?
- [ ] Are generic methods distinguished from generic constructors?
- [ ] When overriding, do `@Override` and the generic signature preserve a compatible contract?
- [ ] Do runnable examples have imports, the right file/class names, and the expected stdout?
- [ ] Are null, exception, mutability, and concurrency considerations documented separately?
- [ ] Does the method type parameter reflect a useful type relationship rather than just adding notation?

## 52. Official Java 17 Documentation

- [JLS 17 §8.4.4 — Generic Methods](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.4): syntax and semantics of generic method declarations.
- [JLS 17 §8.4.2 — Method Signature](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.2): method signature, subsignature, and method type parameters.
- [JLS 17 §8.4.8 — Inheritance, Overriding, and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8): overriding generic methods.
- [JLS 17 §8.8.4 — Generic Constructors](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8.4): constructor type parameters.
- [JLS 17 §4.4 — Type Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.4): type variables and upper bounds.
- [JLS 17 §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): erasure of type variables and parameterized types.
- [JLS 17 §4.5 — Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5): invariance and generic types.
- [JLS 17 §5.1.10 — Capture Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.10): wildcard capture.
- [JLS 17 §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): method invocation/overloading.
- [JLS 17 §18 — Type Inference](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html): generic method inference.
- [Java SE 17 API — Function](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Function.html): Function<? super T,? extends R>.
- [Java SE 17 API — Supplier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Supplier.html): factory callback returning T.
- [Java SE 17 API — Class.cast](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#cast(java.lang.Object)): runtime cast with a token.
- [Java SE 17 API — List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): generic collection and factory.
- [Java SE 17 API — Arrays](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): operations on arrays.
- [Java SE 17 API — SafeVarargs](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SafeVarargs.html): contract for generic/reifiable varargs.
- [Oracle Java Tutorials — Generic Methods](https://docs.oracle.com/javase/tutorial/java/generics/methods.html): explanation of method type parameter syntax.
- [Oracle Java Tutorials — Bounded Type Parameters](https://docs.oracle.com/javase/tutorial/java/generics/bounded.html): upper bounds and multiple bounds.
- [Oracle Java Tutorials — Wildcard Capture and Helper Methods](https://docs.oracle.com/javase/tutorial/java/generics/capture.html): examples solving wildcard capture.

## 53. Summary

**Generic methods declare their own set of type parameters with `<T>`, `<U>`, `<R>`, ... placed before the return type**, and they are inferred or specified for **each call**. A generic class `Box<T>` can use T for its state, while a method `<U> U echo(U)` or `<R> R map(...)` uses its own completely independent type. A static method cannot use the class-level T directly; it must declare its own type parameters when it wants to be generic.

The key advantages are **algorithm reuse**, **compile-time type safety**, and the ability to express relationships between type positions: `<K,V>` for key/value pairs, `<T,R>` for transformations, and `<T>` with PECS for copying lists. Choose a wildcard if you do not need a named type variable linking positions.

Finally, **generics do not fully reify type arguments at runtime**. Type erasure explains why you cannot overload differing only in `List<String>`/`List<Integer>`, why there is no `new T()` by default, and why you need a factory/Class token when runtime operations require a concrete type. A good generic method is not one with many T letters, but one that declares **correct, minimal, and meaningful** constraints.
