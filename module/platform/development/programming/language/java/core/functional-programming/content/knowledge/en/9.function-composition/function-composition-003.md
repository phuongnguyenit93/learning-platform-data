# `Function.identity()` and the Role of the Identity Function in Java

## 1. What is the identity function?

In mathematics and functional programming, the **identity function** is a function that returns the exact value it receives, without transforming it:

\[
\operatorname{id}(x)=x.
\]

In Java, the interface `java.util.function.Function<T, R>` describes a mapping from type `T` to type `R` via the single abstract method `R apply(T value)`. When both the input and output types are `T`, Java provides the utility method:

~~~java
static <T> Function<T, T> identity()
~~~

We call this method via `Function.identity()`. It returns a `Function<T,T>` whose `apply(x)` returns `x` itself. The behaviorally equivalent explicit form is:

~~~java
Function<String, String> identityA = Function.identity();
Function<String, String> identityB = s -> s;
~~~

For example, both `identityA.apply("Java")` and `identityB.apply("Java")` return `"Java"`. This is **not a string transformation** like `trim()` or `toUpperCase()`, nor a comparison function or a new-object creator: the output is the input itself.

The importance of the identity function lies not in "doing a useless operation" but in its role as the **neutral element** when composing functions. It helps express the intent to preserve data in pipelines that require passing in a `Function`.

## 2. Syntax, generic types, and generic inference

The API signature is:

~~~java
public static <T> Function<T, T> identity()
~~~

- `<T>` is the generic type parameter of the *static method*.
- `Function<T,T>` has the same input and output type.
- `identity()` takes no arguments; data only enters later when `apply(value)` is called.
- The compiler can infer `T` from the variable assignment context or parameter-passing context.

~~~java
Function<String, String> stringId = Function.identity();
Function<Integer, Integer> integerId = Function.identity();
Function<List<String>, List<String>> listId = Function.identity();

String text = stringId.apply("Java");
Integer number = integerId.apply(42);
~~~

When you want to specify the type explicitly, use a *type witness*:

~~~java
Function<String, String> id = Function.<String>identity();
~~~

In the snippet above, both `Function.identity()` and `Function.<String>identity()` are valid. A type witness is useful when the type inference context is ambiguous or when you want to make the intermediate type clear to the reader.

Do not confuse `Function.identity()` with `Function<String, String>`: the first is **a method that returns a function**; the second is **the type of the function**. Nor should you assign it to an output type different from the input type:

~~~java
Function<String, String> ok = Function.identity();
// Function<String, Integer> wrong = Function.identity(); // Incompatible.
~~~

The identity function can be used with object references or wrappers like `Integer`; Java generics cannot directly take primitive types like `int` as the type parameter `T`.

## 3. Role as the neutral element in function composition

Suppose there is a function `f: A -> B` and two identity functions `idA: A -> A`, `idB: B -> B`. When composing functions:

\[
f \circ id_A = f,\qquad id_B \circ f = f.
\]

This means placing the identity function **before** or **after** `f` yields the same input/output result as `f`. In Java:

- `f.compose(before)` creates a function that executes `before` **first**, then executes `f`: `f(before(x))`.
- `f.andThen(after)` creates a function that executes `f` **first**, then executes `after`: `after(f(x))`.
- `f.compose(Function.identity())` is equivalent in mapping to `f` when generics and context match.
- `f.andThen(Function.identity())` is also equivalent in mapping to `f`.

Let `Function<String, Integer> length = String::length;`. The following forms all compute the length of the string:

~~~java
Function<String, Integer> length = String::length;

Function<String, Integer> first =
        length.compose(Function.<String>identity());
Function<String, Integer> second =
        length.andThen(Function.<Integer>identity());

System.out.println(length.apply("Java")); // 4
System.out.println(first.apply("Java"));  // 4
System.out.println(second.apply("Java")); // 4
~~~

Notice the **two different types** in the example: `identity` placed before `length` accepts/returns `String`, whereas `identity` placed after `length` accepts/returns `Integer`. With a `Function<String,String>` such as `String::trim`, both sides are `Function<String,String>`.

Execution diagram:

~~~text
compose:
x ──> identity<A> ──> f ──> y

andThen:
x ──> f ──> identity<B> ──> y
~~~

"Neutral" should be understood as **equivalence in mapping/behavior observed by the caller when applying the function**, not as a guarantee that `f.compose(identity) == f` under the reference operator `==`. `compose` and `andThen` return an object implementing `Function`; the API does not promise that object is the same object as the original `f`.

### 3.1. Why does the name "identity" make sense?

Function composition is associative: for compatible functions `(h ∘ g) ∘ f = h ∘ (g ∘ f)`. The identity function plays a role similar to `0` in addition or `1` in multiplication: composing it does not change the final value. That property helps us reason about pipelines regardless of how many transformation steps a processing block has.

In Java, `Function.compose` and `Function.andThen` perform simple two-function compositions. For logic with side effects, when reasoning with broader algebraic rules you must consider execution count and order, exceptions, and mutable state; do not assume all functions are pure.

## 4. Using `Function.identity()` in Streams

`Stream.map` requires a function mapping each input element to an output element. When you want to keep each element unchanged, you can pass `Function.identity()`:

~~~java
List<String> words = List.of("Java", "Lambda");

List<String> sameValues = words.stream()
        .map(Function.identity())
        .toList();
System.out.println(sameValues); // [Java, Lambda]
~~~

`map(Function.identity())` does not transform the elements. For a plain Stream, this step can be redundant; for instance `words.stream().toList()` also obtains the same values in the same encounter order. However, `identity()` is very useful when an API requires a `Function` object or when building a dynamic pipeline where one branch needs to leave values unchanged.

**Do not confuse "elements remain unchanged" with "the list remains unchanged".** `toList()` creates a resulting list (unmodifiable per the `Stream.toList()` contract), while the elements themselves may still be the exact objects from the source. If an element is mutable, mutating the object's state through one reference will be visible through other references pointing to it.

In cases such as:

~~~java
List<String> upper = words.stream()
        .map(String::toUpperCase)
        .toList();
~~~

We need an actual transformation; here `Function.identity()` cannot replace `String::toUpperCase`.

## 5. Very common application: `Collectors.toMap`

`Collectors.toMap(keyMapper, valueMapper)` requires **two functions**: one to produce the key, one to produce the value. When you want the map to keep the **original element itself** as the value, `Function.identity()` is a clear choice:

~~~java
record User(String id, String name) {}

List<User> users = List.of(
        new User("u01", "An"),
        new User("u02", "Binh"));

Map<String, User> byId = users.stream()
        .collect(Collectors.toMap(
                User::id,
                Function.identity()));

System.out.println(byId.get("u02").name()); // Binh
~~~

How to read `Collectors.toMap(User::id, Function.identity())`:

1. For each `User u`, take `u.id()` as the key.
2. Use `u` itself as the value (without converting to `u.name()` or creating another `User`).
3. Put that key/value pair into the resulting Map.

The equivalent lambda for value mapping is `u -> u`:

~~~java
Map<String, User> byId = users.stream()
        .collect(Collectors.toMap(User::id, u -> u));
~~~

There is no academic or performance reason forcing one over the other. `Function.identity()` often expresses the intent "keep the object as-is" clearly and reduces repeating variable names.

**Limitation to remember:** the two-argument overload of `Collectors.toMap` throws `IllegalStateException` if elements produce duplicate keys; `Function.identity()` does not resolve key collisions. Choose a reasonable merge policy, such as keeping the record that appears first:

~~~java
Map<String, User> firstById = users.stream()
        .collect(Collectors.toMap(
                User::id,
                Function.identity(),
                (first, later) -> first));
~~~

The example above assumes `User` is already defined and `users` is available as above. With a parallel stream or when encounter order is not guaranteed, do not assume a specific order to decide which record is "first".

In `toMap`, the value mapper must not return `null` for standard `Collectors.toMap` collection paths; therefore `Function.identity()` does not make collecting `null` elements safe. For collections that may contain null, define a clear filtering/handling rule before collecting.

## 6. Standalone runnable Java 17+ example

Create `IdentityFunctionDemo.java`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

public class IdentityFunctionDemo {
    record User(String id, String name) {}

    public static void main(String[] args) {
        String original = new String("  Java  ");
        Function<String, String> identity = Function.identity();

        String retained = identity.apply(original);
        System.out.println("same reference=" + (retained == original));
        System.out.println("null stays null=" + (identity.apply(null) == null));

        Function<String, String> trim = String::trim;
        Function<String, String> before =
                trim.compose(Function.identity());
        Function<String, String> after =
                trim.andThen(Function.identity());

        System.out.println("compose=" + before.apply(original));
        System.out.println("andThen=" + after.apply(original));

        Function<String, Integer> length = String::length;
        Function<String, Integer> lengthBefore =
                length.compose(Function.<String>identity());
        Function<String, Integer> lengthAfter =
                length.andThen(Function.<Integer>identity());
        System.out.println("length before=" + lengthBefore.apply("Java"));
        System.out.println("length after=" + lengthAfter.apply("Java"));

        List<String> labels = List.of("Java", "Stream");
        System.out.println("map=" + labels.stream()
                .map(Function.identity()).toList());

        List<User> users = List.of(
                new User("u01", "An"),
                new User("u02", "Binh"));
        Map<String, User> byId = users.stream()
                .collect(Collectors.toMap(
                        User::id,
                        Function.identity()));
        System.out.println("user=" + byId.get("u02").name());
        System.out.println("same user=" + (byId.get("u01") == users.get(0)));
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac IdentityFunctionDemo.java
java IdentityFunctionDemo
~~~

Expected stdout:

~~~text
same reference=true
null stays null=true
compose=Java
andThen=Java
length before=4
length after=4
map=[Java, Stream]
user=Binh
same user=true
~~~

Explanation:

- `original` is a `String` object; `identity.apply(original)` returns that exact object, so `retained == original` is `true`.
- The identity function does not check for null on its own; when the input is `null`, the output is also `null`.
- Composing `identity` before or after `trim` does not change the result `"Java"`.
- The `String` and `Integer` types of identity are clearly distinguished in the two composition directions with `length`.
- `map(Function.identity())` preserves the elements `"Java"` and `"Stream"`.
- `toMap(User::id, Function.identity())` uses the ID as the key and the `User` itself as the value; `byId.get("u01") == users.get(0)` is `true`.

## 7. Identity function does not mean copying

This is an important point when working with mutable objects. The same object can be referenced by multiple variables:

~~~java
List<String> mutable = new java.util.ArrayList<>();
mutable.add("first");

Function<List<String>, List<String>> id = Function.identity();
List<String> alias = id.apply(mutable);
alias.add("second");

System.out.println(mutable);        // [first, second]
System.out.println(alias == mutable); // true
~~~

`identity()` **does not create a shallow copy or deep copy**; it returns the exact same object. If a new list is needed, it must be created explicitly:

~~~java
Function<List<String>, List<String>> copy =
        source -> new java.util.ArrayList<>(source);
~~~

The copy operation above only creates a new list and copies the **element references**; if the elements are mutable objects, that is still only a shallow copy.

Nor should `Function.identity()` be understood as an **object identity** check or equality check: `identity` here is the name of the *mapping x → x*. For reference checks, use `==`; for value comparison per the `equals` contract, use `equals`/`Objects.equals`. Those three concepts have different roles.

## 8. Technical points easily misunderstood

### 8.1. `identity()` does not execute processing when created

~~~java
Function<String, String> id = Function.identity(); // Create/obtain a Function.
String result = id.apply("x");                      // Apply Function: returns "x".
~~~

Calling `Function.identity()` only obtains a function. It does not accept a string or process a string at that moment.

### 8.2. Do not rely on the object identity of the returned functions themselves

~~~java
Function<String, String> a = Function.identity();
Function<String, String> b = Function.identity();
~~~

The API guarantees the behavior that applying `a.apply(x)` and `b.apply(x)` both return `x`; it **does not promise** that `a == b` is `true` or `false` across all JDKs. Implementations may reuse a lambda object or create different objects, and that is not a condition for writing correct code.

### 8.3. `null` handling does not appear automatically

`Function.identity()` accepts `null` and returns `null`. It does not throw `NullPointerException` solely because of `apply(null)`, but a preceding or succeeding function might throw an error:

~~~java
Function<String, String> id = Function.identity();
Function<String, String> trim = String::trim;

// id.apply(null) returns null.
// trim.compose(id).apply(null) throws NullPointerException at trim.
~~~

Similarly, a collection/collector or API accepting the function may enforce its own null constraints; do not take the behavior of identity as a guarantee for the entire pipeline.

### 8.4. `Function.identity()` differs from `UnaryOperator.identity()`

`UnaryOperator<T>` is a specialized functional interface extending `Function<T,T>` and provides the static method `UnaryOperator.identity()`. If an API requires `UnaryOperator<T>`, use:

~~~java
import java.util.function.UnaryOperator;

UnaryOperator<String> id = UnaryOperator.identity();
System.out.println(id.apply("Java")); // Java
~~~

`Function.identity()` has a declared return type of `Function<T,T>`; it cannot be arbitrarily assigned to a `UnaryOperator<T>` variable because `Function<T,T>` is not a subtype of `UnaryOperator<T>`, even though both functions are identical in behavior.

### 8.5. Identity can be redundant or hurt readability when overused

~~~java
List<String> items = List.of("a", "b");

List<String> a = items.stream().toList();
List<String> b = items.stream().map(Function.identity()).toList();
~~~

In this situation, adding `map(identity())` does not clarify the processing intent. However, in `Collectors.toMap(KeyExtractor, Function.identity())`, it is a necessary expression because the collector genuinely requires a **value mapper**.

Do not add identity just to make code look more "functional"; choose it when you want to express or provide a data-preserving mapping.

### 8.6. Method references, lambdas, and identity

- `x -> x` is a lambda expressing the identity function.
- `Function.identity()` is a static method returning an identity function.
- A method reference of the form `SomeType::someMethod` expresses forwarding to the specified method. It only acts as identity if that method actually returns the input unchanged in the relevant sense.
- `Objects::toString` or `String::toString` cannot generally substitute for `Function.identity()`: accepted/returned types, behavior on null, and applicability to different types may differ.

## 9. Comprehension exercises

**Exercise 1 — Function composition.** Given `Function<Integer, Integer> square = x -> x * x;`, what are the results of `square.compose(Function.identity()).apply(5)` and `square.andThen(Function.identity()).apply(5)`?

Answer: both equal `25`. Identity is the neutral element when composing two functions, so composing before or after does not change the value.

**Exercise 2 — Keeping the object or copying?** After creating `Function<List<String>,List<String>> f = Function.identity();`, what does calling `f.apply(list) == list` return if `list` is non-null?

Answer: `true`; it is the same reference, not a new list.

**Exercise 3 — Values in a Map.** With `users.stream().collect(Collectors.toMap(User::id, Function.identity()))`, what is the value type of the Map and what happens when IDs collide?

Answer: the value is the original `User`. The two-argument collector form throws `IllegalStateException` when two elements share the same key; a merge policy or prior deduplication is needed.

**Exercise 4 — Null.** What does `Function.<String>identity().apply(null)` give?

Answer: returns `null`; identity does not validate null itself. However, `String::trim` on a null receiver will throw `NullPointerException`.

**Exercise 5 — Generic types.** Given `Function<String, Integer> length = String::length;`, what type mappings are needed for identity placed before and after it?

Answer: before `length` is `String -> String`; after `length` is `Integer -> Integer`. This can be written explicitly as `Function.<String>identity()` and `Function.<Integer>identity()`.

## 10. Takeaways

`Function.identity()` represents the **input-preserving mapping** of type `Function<T,T>`. It acts as the neutral element of function composition: `f.compose(id)` and `f.andThen(id)` give the same mapping as `f` when target types match. In practical Java, it is especially useful when a `Stream` or `Collector` requires a mapper while the data must remain unchanged, notably `Collectors.toMap(keyMapper, Function.identity())`.

Always distinguish **preserving the object** from **creating a copy**, **identity mapping behavior** from **reference identity of the Function object**, and remember that null, duplicate keys, side effects, or external API constraints still need to be handled according to their specific contracts.