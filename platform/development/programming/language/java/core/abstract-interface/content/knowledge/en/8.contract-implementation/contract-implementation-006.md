# Multiple Interfaces with Incompatible Return Type Requirements in Java

## 1. The Problem When Implementing Multiple Contracts Simultaneously

A Java class can `implements` multiple interfaces. However, if the interfaces require a method with the **same signature** while demanding **incompatible return types**, an implementing class cannot satisfy those contracts simultaneously.

Consider two interfaces:

~~~java
interface TextId {
    String id();
}

interface NumericId {
    Integer id();
}
~~~

Both declare the method `id()`, with no parameters. The difference is that `TextId.id()` requires returning `String`, whereas `NumericId.id()` requires returning `Integer`.

If you write:

~~~java
// INTENTIONALLY INCORRECT example: does not compile.
final class BrokenRecord implements TextId, NumericId {
    @Override
    public String id() {
        return "42";
    }
}
~~~

The compiler rejects this because `String id()` cannot implement the `Integer id()` requirement. Changing it to `Integer id()` violates `TextId` instead. `String` and `Integer` are two class types without a subclass relationship that would allow a single method's return type to substitute for both. The exact error message may vary depending on the `javac` version and code form, but this is a **compile-time error**, not an error that only occurs at runtime.

An interface extending two incompatible contracts simultaneously also encounters an error:

~~~java
// INTENTIONALLY INCORRECT example: does not compile.
interface CombinedId extends TextId, NumericId {
}
~~~

The problem arises directly within the contract inheritance relationship; resolving it cannot be deferred by waiting for another class to implement it.

## 2. Why Do Different Return Types Still Count as Duplicate Methods?

In Java, the method signature used to evaluate overloading/overriding is based on the **method name** and **parameter type list** (along with rules related to generic methods). **The return type is not used to distinguish two overloads.**

Therefore:

~~~java
// INTENTIONALLY INCORRECT example: does not compile.
class InvalidOverload {
    String read() {
        return "text";
    }

    int read() {
        return 123;
    }
}
~~~

The two `read()` methods do not differ in name or parameters; they cannot coexist simply because one method returns `String` and the other returns `int`.

Conversely, when parameters differ, we have a valid overload:

~~~java
// Two different signatures: convert(String) and convert(int).
class Converter {
    int convert(String value) {
        return Integer.parseInt(value);
    }

    String convert(int value) {
        return Integer.toString(value);
    }
}
~~~

This is an **illustrative snippet** without `main`; if used, pass arguments of the matching types. You should not arbitrarily change parameters just to avoid conflicts when the business logic requires the same no-argument operation.

## 3. Return Type Compatibility Rules When Overriding

Java applies the **return-type-substitutability** rule: the return type of the implementing method must validly substitute for the return type required by the contract. Three important categories for beginners are:

| Return type in the contract | Compatible implementing method | Incompatible |
| --- | --- | --- |
| `void` | `void` | `String`, `int`, ... |
| Primitive type `int` | `int` | `long`, `Integer` |
| Reference type `CharSequence` | `CharSequence` or a subtype such as `String` | A broader type such as `Object` |

For **primitive types**, the same signature must use the exact same primitive return type; automatic conversion from `int` to `long` in expressions does not turn an `int get()` method into an implementation of `long get()`. Autoboxing likewise does not turn `int get()` into a valid implementation of `Integer get()`.

For **reference types**, Java supports **covariant return types**: the implementing method can return a more specific type, as long as it satisfies the return-type-substitutability rule. For example, `String` implements `CharSequence`, so `String` can substitute for a `CharSequence` requirement. Certain generic/unchecked cases are specified separately in the Java Language Specification; you should not interpret the rule merely by looking at the names of the two types.

### Valid Example: Covariant Return Type

Save the entire following program to `CovariantReturnDemo.java`:

~~~java
interface TextView {
    CharSequence render();
}

interface StringView {
    String render();
}

final class MarkdownView implements TextView, StringView {
    @Override
    public String render() {
        return "Học Java";
    }
}

public class CovariantReturnDemo {
    public static void main(String[] args) {
        MarkdownView view = new MarkdownView();

        TextView general = view;
        StringView specific = view;

        System.out.println(general.render());
        System.out.println(specific.render().length());
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac -encoding UTF-8 CovariantReturnDemo.java
java CovariantReturnDemo
~~~

Exact output:

~~~text
Học Java
8
~~~

Explanation: `MarkdownView.render()` has only **one** implementing method, returning `String`. This value satisfies both the `CharSequence render()` and `String render()` requirements. The variable `general` only sees the `CharSequence` contract; the variable `specific` knows the return type is `String` and can call `length()`. The string `Học Java` has eight characters.

This is the key point: **different return types do not necessarily conflict**. A conflict only becomes an issue when there is no valid return type for the implementing method under Java's rules.

### Extending an Interface with a More Specific Return Type

A subinterface can also redeclare the method with a covariant return type:

~~~java
interface GeneralResult {
    Number value();
}

interface IntegerResult extends GeneralResult {
    @Override
    Integer value();
}

final class Counter implements IntegerResult {
    @Override
    public Integer value() {
        return 7;
    }
}
~~~

This is a valid declaration snippet, though it does not yet include a `main` program. Because `Integer` is a subclass of `Number`, `IntegerResult.value()` adheres to the contract from `GeneralResult`. A `Counter` instance can be used through both interfaces.

## 4. True Conflicts That Cannot Be Resolved with a Single Method

### Two Reference Types That Cannot Both Be Satisfied

~~~java
interface TextReader {
    String read();
}

interface NumericReader {
    Integer read();
}

// INTENTIONALLY INCORRECT.
class DualReader implements TextReader, NumericReader {
    @Override
    public Object read() {
        return "data";
    }
}
~~~

`Object` can hold either a `String` or an `Integer` value at runtime, but the **declared return type** `Object` is too broad compared to both `String` and `Integer`. Therefore, the method above does not properly implement the two contracts. Replacing `Object` with either `String` or `Integer` would also satisfy only one side.

You cannot declare an additional `Integer read()` alongside `String read()`, because Java does not overload by return type. Casting inside the method body, changing the return value at runtime, adding `@Override`, or using `default` does not eliminate the incompatibility of the declared types.

### Primitive and void Conflicts

~~~java
interface IntMetric {
    int measure();
}

interface LongMetric {
    long measure();
}

// INTENTIONALLY INCORRECT.
interface ConflictingMetric extends IntMetric, LongMetric {
}
~~~

`int` and `long` are different; a single `measure()` method cannot satisfy both simply through widening conversion. Similarly, `void execute()` and `boolean execute()` have the same signature but incompatible return types. The `int` and `Integer` case is not resolved by autoboxing either.

### Note on Generics

Parameterized types such as `List<String>` and `List<Integer>` do not have a subtype relationship with each other just because they both start with `List`:

~~~java
interface Names {
    java.util.List<String> items();
}

interface Counts {
    java.util.List<Integer> items();
}

// INTENTIONALLY INCORRECT.
interface ImpossibleCatalog extends Names, Counts {
}
~~~

This example also fails because methods with the same signature have incompatible generic return type requirements. Generics in Java do not automatically make `List<String>` a subtype of `List<Integer>`. You should consider redesigning the contracts, the data types, or giving the behaviors different names; using raw types/unsafe casts to bypass the error only loses type checking.

**Advanced note:** Two *different* interface return types do not automatically mean they cannot be implemented simultaneously. A concrete class can implement both of those return-type interfaces; if the class's method returns a concrete type compatible with both, both contracts can be satisfied together. Analyze actual type substitutability rather than inferring from the fact that the return type names differ. However, inheriting multiple declarations simultaneously in a subinterface has its own rules regarding inherited methods; do not assume a solution for a class will make every `interface extends A, B` valid.

## 5. How to Resolve Incompatible Contracts

### Approach A: Adjust Method Names or Semantics If You Control the API

If the two behaviors are inherently different in meaning, separate the contract names clearly:

~~~java
interface TextIdentifier {
    String textId();
}

interface NumericIdentifier {
    int numericId();
}

final class Product implements TextIdentifier, NumericIdentifier {
    private final int number;

    Product(int number) {
        this.number = number;
    }

    @Override
    public String textId() {
        return "P-" + number;
    }

    @Override
    public int numericId() {
        return number;
    }
}
~~~

The two methods `textId()` and `numericId()` have different signatures. This naming also clarifies that one value serves as a display code and the other serves as an internal numeric code. This is an illustrative implementation snippet; there is no `main`.

### Approach B: Unify Contracts Around Return Types with a Subtype Relationship

If the two interfaces genuinely describe the same operation, you can update your APIs to use compatible types, such as one contract returning `Number` and another returning `Integer`. Then a method returning `Integer` can satisfy both, as in the `GeneralResult` / `IntegerResult` example above.

You should not force contracts to use an overly broad common type like `Object` just to compile: doing so shifts the burden of type checking onto call sites. Changing the return type of a public API can also affect dependent source/binary code, so compatibility scope should be considered when modifying a released library.

### Approach C: Use Two Adapters When Original Interfaces Cannot Be Modified

If `TextId` and `NumericId` are contracts from an external library, a shared data object can be wrapped by **two different adapter classes**. Each adapter implements only its own contract, avoiding forcing a single class to have two `id()` methods with incompatible return types.

The following example is a complete program. Save it as `IdAdapterDemo.java`:

~~~java
interface TextId {
    String id();
}

interface NumericId {
    Integer id();
}

final class RecordData {
    private final int value;

    RecordData(int value) {
        this.value = value;
    }

    int number() {
        return value;
    }
}

final class TextIdAdapter implements TextId {
    private final RecordData data;

    TextIdAdapter(RecordData data) {
        this.data = data;
    }

    @Override
    public String id() {
        return "ID-" + data.number();
    }
}

final class NumericIdAdapter implements NumericId {
    private final RecordData data;

    NumericIdAdapter(RecordData data) {
        this.data = data;
    }

    @Override
    public Integer id() {
        return data.number();
    }
}

public class IdAdapterDemo {
    public static void main(String[] args) {
        RecordData data = new RecordData(42);
        TextId textApi = new TextIdAdapter(data);
        NumericId numericApi = new NumericIdAdapter(data);

        System.out.println(textApi.id());
        System.out.println(numericApi.id() + 1);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 IdAdapterDemo.java
java IdAdapterDemo
~~~

Output:

~~~text
ID-42
43
~~~

`TextIdAdapter` and `NumericIdAdapter` both use `RecordData`, but each adapter has its own responsibility and contract. The underlying data is `42`; the text side receives `"ID-42"`, and the numeric side receives an `Integer` with value `42`, which becomes `43` when 1 is added. When changing the data-providing class, you only need to update the corresponding adapter.

If a requirement mandates that a single class must directly `implements TextId, NumericId` with the two types `String`/`Integer` for the same `id()`, then **there is no way to write a valid Java method** that preserves both contracts simultaneously. You must change the model or use separate intermediary classes.

## 6. Distinguishing Return Type Conflicts from Default Method Conflicts

It is important to identify the exact cause:

- **Return type conflict:** same signature, but the return types are not mutually substitutable. Rewriting the body, adding `@Override`, or picking one `default` cannot fix a type contradiction.
- **Default method conflict:** two interfaces provide default implementations with the same signature. When the return types are compatible, the implementing class may need to explicitly override to select or combine behaviors; this is an implementation precedence problem, distinct from a type contract problem.

For example, if `interface A { default String label() { return "A"; } }` and `interface B { default String label() { return "B"; } }`, a class implementing both must define `public String label()` itself (and may call `A.super.label()` or `B.super.label()` when valid). The fact that both return `String` does not automatically determine which method body the class selects.

## 7. Compile Error Diagnosis Workflow

When `class X implements First, Second` or `interface Combined extends First, Second` encounters an error around a method, proceed step by step:

1. **Compare names and parameters:** do they have the same signature or are they *override-equivalent*? If their parameter lists differ, they may simply be two regular overloads.
2. **Compare declared return types:** identical, covariant, or non-substitutable? Remember to distinguish primitives, `void`, reference types, and generics.
3. **Inspect the implementing method:** does it have `public` access and a return type that is validly substitutable for **each** interface being implemented?
4. **Determine API ownership:** if you own the interfaces, you can rename methods or standardize types; for third-party interfaces, composition/adapters are typically used.
5. **Recompile on the spot:** the error occurs at compile time, so `instanceof` or catching runtime exceptions cannot substitute for fixing the declarations.

Error messages may take forms such as “return type is not compatible” or “inherits abstract and default / unrelated defaults” in different cases. Read the method name, the requested types, and the inheritance point to distinguish the actual cause.

## 8. Self-Check Questions

1. Two interfaces declare `String fetch()` and `Integer fetch()` respectively: can a class implementing both add two methods that differ only in return type?
2. Why can `String render()` implement `CharSequence render()`?
3. If a contract requires `long total()`, is returning `int total()` valid because int can be converted to long?
4. Are `List<String> items()` and `List<Integer> items()` automatically compatible because both are `List`?
5. If two libraries provide interfaces with `id()` returning two irreconcilable types and the libraries cannot be modified, what design approach preserves both contracts?

**Suggested answers:** (1) No; Java does not overload by return type. (2) Because `String` is a subtype of `CharSequence` (covariant return). (3) No, primitive returns must have the same type. (4) No, different generic types do not automatically have a subtype relationship. (5) Use separate adapters sharing the underlying data/processing core, or revise the architecture at the integration point.

## 9. Further Reading from the Java Language Specification

- [JLS `8.4.2` — Method Signature](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.2): method signature and overloading rules.
- [JLS `8.4.5` — Method Result](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.5): return types and return-type-substitutability rules.
- [JLS `9.4.1.3` — Inheriting Methods with Override-Equivalent Signatures](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.4.1.3): inherited methods with the same signature in interfaces.

**Takeaway:** multiple interfaces can only be combined safely when a valid implementation can satisfy all of their methods with the same signature. When return type requirements genuinely conflict, fix the contracts or separate out adapter classes instead of trying to overload by return type.
