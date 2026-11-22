# Designing a Multi-Type-Parameter Class with `Pair<K, V>` in Java Generics

A generic class is not limited to a single type parameter `T`. When an object needs to store or coordinate **two values that may belong to two different types**, we can declare `class Pair<K, V>`. The symbol `K` typically suggests *key*, and `V` suggests *value*. The two types are chosen independently when using the class; from there, the compiler checks the type of each component without manual casting.

This lesson moves from `<K, V>` syntax, how to design the `Pair` class, instantiation and type inference, to factory methods, transformation operations, immutability, the `equals()/hashCode()` contract, and deciding when to use a general-purpose pair type.

## 1. Why Do We Need Two Type Parameters?

A `Box<T>` holds a single value of type `T`; whereas a `Pair<K, V>` describes **two positions with distinct roles and types**:

```java
class Pair<K, V> {
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
```

This is **an illustrative class definition** (without `main`). In the declaration:

- `<K, V>` declares **two type parameters** belonging to class `Pair`, which can appear in fields, constructors, and instance methods of the class.
- `K key` indicates the first component carries type `K`; `V value` indicates the second component carries type `V`.
- When writing `Pair<String, Integer>`, we substitute `K = String` and `V = Integer`; thus `key()` has static type `String`, and `value()` has static type `Integer`.
- With `Pair<Long, Long>`, two identical type arguments are also valid. Having **two type parameters** does not mean the two types must be different.
- The names `K` and `V` are conventions. If the pair merely represents "left/right" without a key–value role, `Pair<L, R>` or clearer meaningful names may be appropriate.

If `Pair<Object, Object>` were used to store arbitrary types, readers would have to cast whenever using type-specific methods; type errors might only surface at runtime. If `Pair<String, Integer>` is used, the compiler already knows the type of each component and detects many errors before execution.

## 2. Syntax for Declaring and Using `Pair<K, V>`

With the `Pair` example above, instantiation syntax includes concrete types for both parameters:

```java
Pair<String, Integer> age = new Pair<>("Ada", 36);
Pair<Integer, String> code = new Pair<>(404, "Not Found");
Pair<String, String> labels = new Pair<>("vi", "Xin chào");
```

The lines above need to be placed inside a valid method or declaration scope where the `Pair` class is visible. These are **three uses of the same class definition**, not creating three different source classes.

- **Order matters:** `Pair<String, Integer>` is different from `Pair<Integer, String>`. Swapping the type arguments means swapping the roles of the returned methods.
- **Diamond operator `<>`:** in `new Pair<>("Ada", 36)`, the compiler infers `K` and `V` based on the target type and argument expressions. You can write out `new Pair<String, Integer>("Ada", 36)` in full, though it is usually verbose.
- **Wrappers for primitives:** `Integer` is a reference type, suitable for a type argument. `36` is an `int` literal and is boxed into `Integer` when needed. `Pair<String, int>` is invalid in Java 17.
- **Two types have independent relationships:** declaring `Pair<String, Integer>` does not state that `String` must extend `Integer` or vice versa.
- **Using the exact return types:** `String name = age.key(); Integer years = age.value();` is valid; `String years = age.value();` does not compile.

Standard Java generics uses **type erasure**, so `Pair<String, Integer>` and `Pair<Integer, String>` share the same `Pair` class at runtime; the type parameters primarily serve compile-time type checking. Do not use `instanceof Pair<String, Integer>` to test a concrete type, because that parameterized type test is invalid.

## 3. Recommended Design: Immutability and Small API

A `Pair` can be written in mutable style with setters, but when it represents a composite value, an **immutable** design is usually more predictable and easier to use as a result or key:

1. `final class` prevents subclasses from altering the contract via overriding.
2. `private final` fields disallow reassigning references after construction.
3. No setters are exposed.
4. The constructor initializes both components completely.
5. Accessors `key()` and `value()` return the exact declared generic types.
6. `equals` and `hashCode` compare both components by value and stay consistent with each other.
7. `toString` helps with debugging and logging; avoid relying on its string format as a long-term data exchange protocol.

**Immutability here is shallow immutability.** If `V` is a mutable `ArrayList<String>`, the fact that `Pair` holds a `final` field does not prevent callers from mutating that list's contents. If the API needs deeper immutability, restrict component types, make defensive copies, or use suitable immutable component objects.

Whether to allow `null` is a **design decision**, not a rule of `Pair<K, V>`. `new Pair<>(null, 3)` can be valid if the constructor does not check. If business logic requires both components to be non-null, use `Objects.requireNonNull(key, "key")` and `Objects.requireNonNull(value, "value")` in the constructor; document that contract clearly in the API.

## 4. Standalone Runnable Java 17 Example: Complete `Pair<K, V>`

Save the entire following program into the file **`PairDemo.java`** (Java 17+):

```java
import java.util.List;
import java.util.Objects;
import java.util.function.Function;

public class PairDemo {
    public static final class Pair<K, V> {
        private final K key;
        private final V value;

        private Pair(K key, V value) {
            this.key = key;
            this.value = value;
        }

        public static <K, V> Pair<K, V> of(K key, V value) {
            return new Pair<>(key, value);
        }

        public K key() {
            return key;
        }

        public V value() {
            return value;
        }

        public Pair<V, K> swapped() {
            return Pair.of(value, key);
        }

        public <NEW_VALUE> Pair<K, NEW_VALUE> mapValue(
                Function<? super V, ? extends NEW_VALUE> mapper) {
            Objects.requireNonNull(mapper, "mapper");
            return Pair.of(key, mapper.apply(value));
        }

        @Override
        public boolean equals(Object object) {
            if (this == object) {
                return true;
            }
            if (!(object instanceof Pair<?, ?> other)) {
                return false;
            }
            return Objects.equals(key, other.key)
                    && Objects.equals(value, other.value);
        }

        @Override
        public int hashCode() {
            return Objects.hash(key, value);
        }

        @Override
        public String toString() {
            return "(" + key + ", " + value + ")";
        }
    }

    public static void main(String[] args) {
        Pair<String, Integer> person = Pair.of("Ada", 36);
        Pair<Integer, String> reversed = person.swapped();
        Pair<String, String> ageText =
                person.mapValue(age -> age + " years");
        Pair<String, Integer> same = Pair.of("Ada", 36);
        Pair<String, Integer> different = Pair.of("Ada", 37);
        Pair<String, List<Integer>> scores =
                Pair.of("scores", List.of(2, 4, 6));

        System.out.println("person: " + person);
        System.out.println("key upper: " + person.key().toUpperCase());
        System.out.println("next age: " + (person.value() + 1));
        System.out.println("swapped: " + reversed);
        System.out.println("mapped: " + ageText);
        System.out.println("equal: " + person.equals(same));
        System.out.println("different: " + person.equals(different));
        System.out.println("nested: " + scores);
        System.out.println("same type: " + Pair.of(1, 2));
    }
}
```

Compile and run in the directory containing the file:

```bash
javac PairDemo.java
java PairDemo
```

**Expected stdout:**

```text
person: (Ada, 36)
key upper: ADA
next age: 37
swapped: (36, Ada)
mapped: (Ada, 36 years)
equal: true
different: false
nested: (scores, [2, 4, 6])
same type: (1, 2)
```

Explaining the results by mechanism:

- `Pair.of("Ada", 36)` is a **generic static factory method**. The compiler infers `K = String`, `V = Integer` (boxing `36` as needed). The resulting value has type `Pair<String, Integer>`.
- `person.key().toUpperCase()` is valid because `key()` has type `String`. `person.value() + 1` unboxes `Integer` to `int` to add and produce `37`.
- `swapped()` has return type `Pair<V, K>`, which is `Pair<Integer, String>` in this case. **Swapping the values goes together with swapping the type parameter positions**; keeping `Pair<K, V>` as the return type would be wrong.
- `mapValue(...)` keeps `K` unchanged while allowing `V` to change to a new type `NEW_VALUE`. The lambda turns `36` into `"36 years"`, so the result is `Pair<String, String>`.
- `equals` checks the contents of both components, so `person` equals `same` but differs from `different`. `hashCode` is consistent with `equals`; the program does not print a specific hash value because there is no need to depend on that representation.
- `Pair<String, List<Integer>>` illustrates **nested generic types**: `K` is `String`, `V` is `List<Integer>`. The program uses `List.of(...)` which returns a list whose elements cannot be modified via mutating commands; however, the `Pair` type itself does not require `V` to be an immutable list.
- `Pair.of(1, 2)` is valid when both `K` and `V` are inferred as `Integer`. The two positions remain independent in role despite having the same type.

The snippet `if (!(object instanceof Pair<?, ?> other))` uses *pattern matching for instanceof* available in Java 17. `Pair<?, ?>` only checks that the object is a `Pair` without assuming concrete runtime type arguments. Comparing each component with `Objects.equals` works properly when components may be `null` and avoids unsafe casts.

## 5. Static Factory and Type Limits of `static` Members

A factory like `Pair.of(...)` makes instantiation more concise while preserving types at both positions. Signature:

```java
public static <K, V> Pair<K, V> of(K key, V value) {
    return new Pair<>(key, value);
}
```

This is a method **inside the `Pair<K, V>` class** of the complete example, not a free-standing Java function.

The `<K, V>` after `static` **declares two type parameters belonging to the method itself**. It does not directly use the `K` and `V` of a `Pair<K, V>` instance, because a static method belongs to the class rather than a parameterized instance. Naming the method's parameters the same as the class's parameters is allowed; the declaration scopes are different. To avoid confusion while reading, you can declare the factory as `static <A, B> Pair<A, B> of(A a, B b)`; the meaning is unchanged.

Invalid scoping pattern (does not compile when placed in `class Pair<K, V>`):

```java
// static Pair<K, V> create(K key, V value) { ... }
// Invalid because static cannot directly use the class's type parameters.
```

The correct pattern includes the method's type parameter declaration: `static <K, V> Pair<K, V> create(K key, V value)`.

The call syntax can be written explicitly with type witnesses `Pair.<String, Integer>of("Ada", 36)`, though in most situations `Pair.of("Ada", 36)` is enough for the compiler to infer. One important note: **type inference depends on context**. If you write `var pair = Pair.of("Ada", 36)`, the type is inferred from the argument expressions; if you need a broader contract (for example `Pair<CharSequence, Number>`), declare an explicit target type or call the factory with appropriate type witnesses. The compiler does not automatically guess API intent in every situation.

## 6. Transforming Two Components While Preserving Types

A major benefit of multiple type parameters is that **methods can transform one component while keeping the other unchanged**:

| Method | Return Type | Meaning |
|---|---|---|
| `K key()` | `K` | Read the first component with the exact type |
| `V value()` | `V` | Read the second component with the exact type |
| `Pair<V, K> swapped()` | `Pair<V, K>` | Swap both components and both type parameters |
| `<R> Pair<K, R> mapValue(Function<? super V, ? extends R> f)` | `Pair<K, R>` | Keep `K`, transform only `V` |
| `<R> Pair<R, V> mapKey(Function<? super K, ? extends R> f)` | `Pair<R, V>` | Keep `V`, transform only `K` |

`mapKey` is a **parallel design suggestion**, not included in the `PairDemo` program. If added to the body of the `Pair` class, it can be implemented as:

```java
public <NEW_KEY> Pair<NEW_KEY, V> mapKey(
        Function<? super K, ? extends NEW_KEY> mapper) {
    Objects.requireNonNull(mapper, "mapper");
    return Pair.of(mapper.apply(key), value);
}
```

The snippet above uses `Function` and `Objects` already imported in the complete example, and **needs to reside inside class `Pair<K, V>`**. For `Pair<String, Integer> p`, calling `p.mapKey(String::length)` has type `Pair<Integer, Integer>`.

Why `Function<? super V, ? extends R>` instead of just `Function<V, R>`? Wildcards allow broader acceptance: the transformation can consume a **supertype of `V`** and produce a **subtype of `R`**. The pattern "input `? super`, output `? extends`" is useful for APIs accepting functions. If you are just starting out, you can begin with `Function<V, R>` and expand once you understand PECS.

The method implementation must match what the return type expresses. The following example is a **design bug**:

```java
// Inside class Pair<K, V>:
// Pair<K, V> swapped() { return Pair.of(value, key); }
// Violates the general principle: Pair.of(value, key) has roles V, K.
```

It might happen to compile when `K` and `V` are the same, yet declaring `Pair<K, V>` is wrong for general parameterizations. The exact signature is `Pair<V, K> swapped()`.

## 7. Checking `equals`, `hashCode`, and `toString` for Pair

When two `Pair` objects are used as **values**, comparisons usually need to account for **both key and value**. For example, `Pair.of("A", 1)` should equal another `Pair.of("A", 1)` if they share the same value semantics.

- `equals(Object)` checks that the object is the same pair type and uses `Objects.equals` on each component. `Objects.equals(x,y)` returns a sensible result if one or both components are `null`, while delegating to each component's `equals`.
- `hashCode()` must satisfy: if `a.equals(b)` then `a.hashCode() == b.hashCode()`. `Objects.hash(key, value)` is one implementation; not every different hash necessarily indicates different objects.
- `toString()` should represent the two elements readably; `(Ada, 36)` in the example is an **arbitrary chosen format**, not a mandatory Java rule.

**Do not check only `key` in `equals`** if the pair is described as two value-bearing components: in that case `Pair.of("A", 1)` and `Pair.of("A", 2)` would be treated as equal despite having different contents. In cases where the domain identifies an entity by a single field, use a domain class/record with a clearly named equality contract.

If a component is an array (for example `Pair<String, int[]>`), `Objects.equals` on arrays uses array `equals` semantics (not element-by-element comparison like `Arrays.equals`). If **deep equality** or content-based array comparison is needed, design specifically for that value type. Therefore, a generic Pair cannot automatically know every domain-specific comparison rule.

The immutable pattern helps keep `hashCode` more stable when components are also immutable. If `V` is a mutable list or an object whose `equals/hashCode` changes with state, using `Pair` as a `HashMap` key can still cause lookup failures after mutating the component. `final` on the field does not solve internal mutability.

## 8. Generic Limitations: Type Invariance and Wildcards

Java does not allow inferring `Pair<CharSequence, Number>` from `Pair<String, Integer>` even though `String` implements `CharSequence` and `Integer` is a subtype of `Number`.

Example that **does not compile**:

```java
Pair<String, Integer> exact = Pair.of("A", 1);
// Pair<CharSequence, Number> wider = exact; // Invalid.
```

Here `Pair` is a class with two **invariant** type parameters. The solution depends on what you want to do with the pair:

```java
static void show(
        Pair<? extends CharSequence, ? extends Number> pair) {
    System.out.println(pair.key() + " = " + pair.value());
}
```

This is an **illustrative method**, which needs to be placed inside a class where `Pair` is visible. A parameter of form `Pair<? extends CharSequence, ? extends Number>` can accept `Pair<String, Integer>` and read through the broader type interface. In the immutable `Pair` example, there are no setters; with a mutable Pair, wildcards would also determine which values can be safely written.

**Do not confuse `Pair<?, ?>` with `Pair<Object, Object>`.** `Pair<?, ?>` accepts a pair with two unknown type arguments, suitable for observing values as `Object`. `Pair<Object, Object>` is a pair with two concrete `Object` type arguments; the two declarations do not share the same assignability relationship.

Bounds can be placed on individual parameters when a specialized kind of pair needs constraints, for example:

```java
class ScoredPair<K, V extends Number> {
    private final K key;
    private final V score;

    ScoredPair(K key, V score) {
        this.key = key;
        this.score = score;
    }

    double scoreAsDouble() {
        return score.doubleValue();
    }
}
```

This is a **separate illustrative class**, not part of `PairDemo`. The bound `V extends Number` grants access to `doubleValue()` and rejects type arguments that do not satisfy `Number`. Do not add a bound merely because the type parameter is named `V`: a general-purpose `Pair<K, V>` may need to hold any reference type.

## 9. When to Use Pair, Map.Entry, or a Record?

`Pair<K, V>` is suitable when **two values are genuinely passed/received together** without needing a separate domain contract yet. However, because it is a general-purpose structure, the names `key`/`value` sometimes obscure actual meaning, such as coordinates, time intervals, or user information.

| Need | Suitable Option | Notes |
|---|---|---|
| Small generic value pair needing its own API | `Pair<K, V>` | Easy to control immutability, null, equals, and transformation contracts |
| Pair tied to a map entry | `Map.Entry<K, V>` | Has key–value semantics; `Map.entry(k,v)` creates an immutable entry and **does not accept null** |
| Only storing two components with domain-specific names | `record Range(int start, int end)` or domain record | Field names `start/end` are more meaningful than `key/value` |
| Very simple generic pair on Java 17+ | `record Pair<K, V>(K key, V value)` | Compiler generates constructor, accessors, `equals`, `hashCode`, `toString`; record is shallowly immutable |
| Multiple fields and business rules | Specific domain class/record | Name properties and validation accurately for the business domain |

**Generic records** allow a shorter implementation. The following example is **a separate file** `Pair.java` and is an alternative to the earlier `Pair<K, V>` class:

```java
public record Pair<K, V>(K key, V value) {
    public static <K, V> Pair<K, V> of(K key, V value) {
        return new Pair<>(key, value);
    }

    public Pair<V, K> swapped() {
        return new Pair<>(value, key);
    }
}
```

`record` automatically generates accessors `key()`, `value()`, and value-based methods from the record components. With `Pair.of("A", 1)`, the record-generated `toString()` has a format like `Pair[key=A, value=1]` (unlike `"(A, 1)"` in `PairDemo`). Do not assume these two `Pair` types have identical output formatting when changing implementations.

Whether using a class or a record, if the pair carries specialized meaning and multiple invariants, such as `start <= end`, a `Range` with concrete component names and validation usually communicates the contract better than `Pair<Integer, Integer>`.

## 10. How to Design an Easy-to-Use Pair API

Before placing `Pair<K, V>` into a library, decide the following points consistently:

1. **Roles:** Are `K` and `V` truly key/value? If they are left/right, consider `Pair<L, R>`; if they are domain attributes, consider a domain type.
2. **Immutability:** Should components be updatable after creation? For value objects, `private final` and no setters are usually appropriate.
3. **Null:** Accept `null` at each position or fail early with `Objects.requireNonNull`? Document clearly in the API docs.
4. **Factory and constructor:** `Pair.of` keeps type inference concise; a private constructor prevents instantiation outside the factory. If you want to support `new Pair<>(...)` from caller code, the constructor must have appropriate visibility.
5. **Equality:** Do both components participate in `equals/hashCode`, or are there domain rules? Avoid half-baked implementations.
6. **Mutability of components:** `final` does not make inner objects deeply immutable; document limitations or use defensive copies when needed.
7. **Transformations:** If providing `swapped`, `mapKey`, `mapValue`, the return types must accurately express the type roles before and after transformation.
8. **Type inference:** Let users normally call `Pair.of("A", 1)`; use type witnesses or explicit target types when widening types is needed.
9. **Avoid overuse:** When there are three or four attributes or business rules are needed, a domain-named class/record is usually easier to maintain than nested `Pair`s.

One note specific to library design: Java does not provide a general-purpose `Pair<K, V>` class directly in `java.lang`. Build a small class yourself when there is a clear need, or use an existing type from a library already in use. Avoid adding a new dependency solely for a simple pair type if it adds no other value.

## 11. Common Mistakes

**Mistake 1 — Using one type parameter for both positions when two independent types are wanted.**

```java
class SameTypePair<T> {
    T first;
    T second;
}
```

This class forces both fields to be viewed through the same `T` at each parameterization. If business logic wants a string and a number with clear types, `Pair<K, V>` expresses that better. A `SameTypePair<Object>` can hold two differently typed objects, yet loses the concrete type information of each field.

**Mistake 2 — Using a primitive in a type argument:** `Pair<String, int>` is invalid; use `Pair<String, Integer>`. Java automatically boxes `int` when needed in valid initialization contexts.

**Mistake 3 — Swapping the order of `K, V` when declaring results:** `Pair<Integer, String>` cannot be assigned to `Pair<String, Integer>` just because both are Pairs. Especially check signatures of methods like `swapped()`.

**Mistake 4 — Assuming `Pair<String, Integer>` is a subtype of `Pair<Object, Object>`.** Generic types are invariant; use wildcards or an API designed for the required operation.

**Mistake 5 — Trying to access the class's `K`, `V` from a static method without declaring its own.** Static factories must write `static <K, V> ...` (or other separate type parameter names).

**Mistake 6 — Writing `equals` comparing only the key or using `==` for wrappers/strings.** If value equality is needed, compare each component with `Objects.equals` and write a consistent `hashCode`.

**Mistake 7 — Believing `final` makes mutable components immutable.** `Pair<String, List<Integer>>` can hold a mutable list; anyone holding a reference to the list can still mutate it.

**Mistake 8 — Forgetting null checks in transformation functions.** If `mapper == null`, calling `mapper.apply` throws `NullPointerException`; `Objects.requireNonNull(mapper, "mapper")` makes the contract clear. If `value` is null, the mapper must also handle null or the API needs to forbid null at creation time.

**Mistake 9 — Using Pair instead of a meaningful domain class.** `Pair<Integer, Integer>` does not tell readers which is the start date and which is the end date; a `DateRange` or `Range` type usually expresses and validates data better.

**Mistake 10 — Thinking type parameters exist intact at runtime.** Checking `pair instanceof Pair<?, ?>` is valid, yet does not verify individual type arguments; do not use raw Pair and unchecked casts to bypass compile-time checks.

## 12. Self-Check Exercises with Answers

1. **How many type parameters and how many type arguments does `Pair<String, Integer>` have?** The definition `Pair<K, V>` declares two type parameters `K`, `V`; at the usage site there are two type arguments `String`, `Integer`.
2. **Is `Pair<Integer, Integer>` valid?** Yes. Two independent type parameters are not required to be different types.
3. **Does `Pair<String, Integer> p = Pair.of("A", 4);` need a cast when calling `p.value()`?** No. The compiler knows the return type is `Integer`; assigning to `int` will unbox it.
4. **If `p` is `Pair<String, Integer>`, what type is `p.swapped()`?** `Pair<Integer, String>`. Both positions and type relationships are swapped.
5. **Why is the factory written `static <K, V> Pair<K, V> of(...)`?** Because a static method must declare its own type parameters and cannot directly use the instance-level type parameters of the class.
6. **Can `Pair<String, Integer>` be assigned to a variable of type `Pair<CharSequence, Number>`?** No, because generics are invariant; when only reading is needed, it can be accepted with `Pair<? extends CharSequence, ? extends Number>`.
7. **What does `Pair.of("x", 1).equals(Pair.of("x", 1))` return with the implementation above?** `true`, because both corresponding components are equal according to `Objects.equals`.
8. **Can `new Pair<>(...)` be called outside the `Pair` class in the complete program?** No, because the constructor is private; use `Pair.of(...)`.
9. **Does `record Pair<K, V>(K key, V value)` automatically make an inner `List` immutable?** No; records are shallowly immutable, and component objects can still be mutable.
10. **When the data represents "x and y coordinates," should you use `Pair<Double, Double>` or `Point(double x, double y)`?** Both can store the data, but `Point` is properly domain-named, makes component meanings clear, and provides a better place to express validation/behavior.

Remember: **`Pair<K, V>` is a single generic class with two independent "type slots."** Good design means assigning the right `K`/`V` roles, returning the right type from each accessor, preserving type relationships when swapping or transforming, and ensuring a clear value contract. Generics helps the compiler maintain type safety; API design determines whether that pair is meaningful and easy to use.
