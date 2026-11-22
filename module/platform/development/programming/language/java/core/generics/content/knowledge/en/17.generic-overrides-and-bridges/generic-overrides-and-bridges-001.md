# Type Parameter Substitution When Overriding Methods in Java Generics

## 1. Purpose and Context

When a subclass extends a class or implements an interface with type parameters, Java needs to determine whether **the method after type parameter substitution** actually overrides (*override*) the superclass method.

For example:

```java
class Box<T> {
    T get() {
        return null;
    }

    void put(T value) {
    }
}

class StringBox extends Box<String> {
    @Override
    String get() {
        return "Java";
    }

    @Override
    void put(String value) {
        System.out.println(value);
    }
}
```

In `Box<T>`, `get()` returns `T` and `put(...)` accepts `T`. With the direct supertype `Box<String>`, the compiler treats the types in the **inheritance contract** as having `T` substituted with `String`:

```text
Box<T> declared             When viewed from Box<String>
--------------------------  ----------------------------
T get()                     String get()
void put(T value)           void put(String value)
```

Therefore, `StringBox.get()` and `StringBox.put(String)` are valid overriding methods. `@Override` helps the compiler confirm this.

However, after **type erasure**, the bytecode of `Box<T>` may still carry the signatures `Object get()` and `put(Object)`. To preserve polymorphism, the compiler may generate a **bridge method** in the subclass. Three steps need to be distinguished:

1. **Type parameter substitution during source checking:** from `Box<T>` to `Box<String>`, occurrences of `T` in the contract are specialized to `String`.
2. **Determining the override relationship:** name, parameters, access level, return type, and generic bounds must obey language rules.
3. **Bytecode generation:** Java erases much of the generic information from descriptors and adds bridges when needed to maintain dispatch.

This lesson is about **type parameter substitution in overrides**. Recursive bounds, wildcards, and erasure are mentioned only to the extent needed to read the override contract correctly.

## 2. Two Kinds of Type Parameters to Distinguish

### 2.1. Type parameter belonging to a class or interface

```java
class Repository<T> {
    T save(T value) {
        return value;
    }
}

class StringRepository extends Repository<String> {
    @Override
    String save(String value) {
        return value.strip();
    }
}
```

In the superclass, `T` is declared directly on `Repository<T>`. The subclass chooses `String` via `extends Repository<String>`, so both the parameter and the return type of `save` in the inheritance contract are substituted accordingly.

This **does not create a separate `Repository<String>` copy with its own bytecode**. It is a specialization at the source type level, while `Repository` remains a generic class compiled under the erasure model.

### 2.2. Type parameter belonging to the method itself

```java
class Repository<T> {
    <N extends Number> N number(N value) {
        return value;
    }
}
```

`N` is declared on the **method** `number`; it is independent of the class's `T`. When extending `Repository<String>`, we only substitute occurrences of the class's `T`. We must not arbitrarily infer that `N` also becomes `String`.

A subclass can override using a **renamed** method type parameter:

```java
class StringRepository extends Repository<String> {
    @Override
    <X extends Number> X number(X value) {
        return value;
    }
}
```

`X` and `N` are different names for the same method type parameter position and have corresponding bounds. This renaming is similar to alpha-renaming a bound variable in a generic expression; it does not change the contract.

Conversely:

```java
// Illustrates error when using @Override:
class Base {
    <N> void accept(N value) {
    }
}

class Child extends Base {
    @Override
    void accept(String value) {
    }
}
```

`accept(String)` **does not override** the generic method `<N> accept(N)`: the superclass method must accept any valid type `N`, whereas the subclass method only accepts `String`. With `@Override`, the compiler reports that the method does not override a method from a supertype. If `@Override` is removed, this is an overload with a concrete parameter, while the inherited generic method still exists.

**Rule:** **class** type parameters are substituted according to inheritance; **method** type parameters remain declared independently on each generic method. You cannot turn a superclass generic method into a `String`-only version simply by overriding it with a `String` parameter.

## 3. Sequence for Deriving the Override Signature

Consider:

```java
import java.util.List;

class Repository<T> {
    T save(T value) {
        return value;
    }

    List<T> items(T value) {
        return List.of(value);
    }

    <N extends Number> N number(N value) {
        return value;
    }
}

class StringRepository extends Repository<String> {
    @Override
    String save(String value) {
        return value.strip();
    }

    @Override
    List<String> items(String value) {
        return List.of(save(value));
    }

    @Override
    <X extends Number> X number(X value) {
        return value;
    }
}
```

Read in this sequence:

1. **Find the generic declaration of the superclass**: `Repository<T>`.
2. **Find the concrete inheritance clause**: `extends Repository<String>`, i.e., the substitution `T := String`.
3. **Apply the substitution to occurrences of the class's `T`**: `save(T)` becomes `save(String)`, `List<T> items(T)` becomes `List<String> items(String)`.
4. **Keep the method's type parameter separate**: `<N extends Number> N number(N)` remains a generic method. A new name `<X extends Number> X number(X)` with matching bounds may be used.
5. **Check `@Override`** and Java rules: parameter types, return-type substitutability, access, `final`, `static`, checked exceptions, etc.
6. After the override is valid, **inspect erasure** to understand why the compiler may generate bridge methods.

Comparison table:

| Method declared in `Repository<T>` | Contract viewed from `Repository<String>` | Declaration in subclass |
| --- | --- | --- |
| `T save(T)` | `String save(String)` | `String save(String)` |
| `List<T> items(T)` | `List<String> items(String)` | `List<String> items(String)` |
| `<N extends Number> N number(N)` | Still generic with `N extends Number` | `<X extends Number> X number(X)` |

The decisive point here is that **the same class-level `T`** appearing in multiple positions is substituted consistently. You must not substitute only the parameter type while mistakenly keeping the return type, or substitute a type variable belonging to a different declaration scope.

## 4. Parameter Types Must Match the Inheritance Contract

### 4.1. `put(Object)` does not automatically override `put(String)`

```java
class Base<T> {
    void put(T value) {
    }
}

class Wrong extends Base<String> {
    // Invalid; javac may report "name clash":
    void put(Object value) {
    }
}
```

After substituting `T := String`, the superclass method viewed under the source contract is `put(String)`. The subclass's `put(Object)` does not become `put(String)` merely because `String` is a subtype of `Object`.

The example above is especially treacherous: `put(Object)` and the superclass method have the **same erasure** `put(Object)` yet do not form a valid override. `javac` rejects it with an error of the form:

```text
name clash: put(Object) in Wrong and put(String) in Base
have the same erasure, yet neither overrides the other
```

This is different from a regular overload error. When seeing “same erasure, yet neither overrides the other”, compare **the inherited signature after substitution** and **the JVM signature after erasure**, instead of trying to add casts in the body.

Correct fix:

```java
class Correct extends Base<String> {
    @Override
    void put(String value) {
        System.out.println(value);
    }
}
```

### 4.2. Different type arguments in parameters do not mean override

```java
import java.util.List;

class Base {
    void publish(List<String> values) {
    }
}

// Not a valid override:
class Wrong extends Base {
    // void publish(List<Integer> values) {} // Name clash
}
```

`List<String>` and `List<Integer>` are erased to the same type `List`. Java does not allow creating a new method with the same name and same erased parameter list but different type arguments in an incompatible inheritance relationship like this. If the intent is to handle different kinds of data, choose an appropriate different signature or API name.

**Overloading** selects a method based on the parameter list and overload resolution rules; **overriding** replaces the implementation of an inherited method. Java does not allow “overloading by generic type argument” simply by changing `List<String>` to `List<Integer>`.

### 4.3. Renaming a method's type parameter is different

This is a valid case:

```java
class Base {
    <T extends Number> T echo(T input) {
        return input;
    }
}

class Child extends Base {
    @Override
    <U extends Number> U echo(U input) {
        return input;
    }
}
```

The names `T` and `U` differ, but the generic structure corresponds. Changing it to `<U extends CharSequence>` no longer has the same contract; you cannot arbitrarily change the bounds of an overriding method.

Do not confuse **renaming a type variable** (`T` → `U`) with **specializing a type variable** (`T` → `String`). The former is generally valid when bounds match; the latter depends on whether that variable is declared on the class or on the method.

## 5. Return Types: Covariant, Invariant, and Return-Type Substitutability

An overriding method must have a valid return type according to the *return-type substitutability* rule. In common reference-type cases, the return type can be an appropriate subtype of the superclass's type after type parameter substitution.

Valid example:

```java
class Base<T> {
    T load() {
        return null;
    }
}

class Child extends Base<Number> {
    @Override
    Integer load() {
        return 10;
    }
}
```

After the substitution `T := Number`, `Base<Number>.load()` has a contract returning `Number`; `Integer` is a subtype of `Number`, so narrowing the return type is permitted. This is a **covariant return**.

An easily confused case with a generic parameterized return:

```java
import java.util.List;

class Base {
    List<Number> values() {
        return List.of(1);
    }
}

class Wrong extends Base {
    // @Override List<Integer> values() { return List.of(1); } // Invalid
}
```

Even though `Integer extends Number`, `List<Integer>` is **not a subtype** of `List<Number>`: Java generics are invariant. The compiler does not allow overriding with this return type.

If the API really only promises to return elements of any numeric type, a more flexible contract can be:

```java
import java.util.List;

class Base {
    List<? extends Number> values() {
        return List.of(1, 2);
    }
}

class Child extends Base {
    @Override
    List<Integer> values() {
        return List.of(4, 5);
    }
}
```

`List<Integer>` is compatible with `List<? extends Number>` in the role of **a result for reading `Number` values**. However, that is a **design decision of the superclass API**, not a trick that can be applied unilaterally from the subclass once the superclass signature is fixed.

### 5.1. `void` and primitive return types

You cannot arbitrarily change `void` to another type when overriding. For primitive types, widening such as `int` to `long` does not produce a covariant return as it does for reference subtypes:

```java
class Base {
    int size() { return 0; }
}

class Wrong extends Base {
    // @Override long size() { return 0L; } // Invalid
}
```

When debugging override errors, do not look only at the parameter list; the return type must still be valid even though it does not participate in source-level overloading.

## 6. After Substitution, Type Erasure and Bridges Still Apply

Returning to:

```java
class Repository<T> {
    T save(T value) {
        return value;
    }
}

class StringRepository extends Repository<String> {
    @Override
    String save(String value) {
        return value.strip();
    }
}
```

The compiler knows `StringRepository.save(String)` is a valid override. But the descriptor of `Repository.save` after erasing unbounded `T` is:

```text
(Ljava/lang/Object;)Ljava/lang/Object;
```

Meanwhile, the method written in the subclass has the descriptor:

```text
(Ljava/lang/String;)Ljava/lang/String;
```

To ensure a `save` call made through a reference of type `Repository<String>` still dispatches to the subclass's overriding method, the compiler may generate a **bridge** in `StringRepository`, conceptually resembling:

```java
// CONCEPTUAL CODE GENERATED BY COMPILER, DO NOT ADD TO SOURCE:
Object save(Object input) {
    return save((String) input);
}
```

For `@Override List<String> items(String)`, the erasure of return type `List<String>` becomes `List`, and because the parameter type `T` becomes `Object` in the superclass, the compiler may also generate:

```text
items(Object) -> List
```

Bridges are normally marked with `ACC_BRIDGE` and `ACC_SYNTHETIC` in the class file. They are part of supporting polymorphism after erasure; they are **not** an overload written by the programmer.

Not every method after substitution needs a bridge. In the example:

```java
<N extends Number> N number(N value)
```

both the superclass method and the subclass method (renaming the type variable to `X`) have the post-erasure descriptor:

```text
(Ljava/lang/Number;)Ljava/lang/Number;
```

If there is no descriptor difference to bridge, the compiler does not need to generate a separate bridge for that method.

### 6.1. A bridge can throw `ClassCastException` if the contract is violated via raw types

If legacy code uses a raw type:

```java
// Not recommended:
Repository raw = new StringRepository();
raw.save(123);
```

The call compiles with a raw type (usually with an unchecked warning). The subclass's `save(Object)` bridge attempts to cast `123` to `String`, throwing `ClassCastException` at runtime. This does not prove generics are “just fake checks”: the error occurs because raw/unchecked code bypassed the `Repository<String>` contract that the compiler is meant to enforce.

In new code, use parameterized references:

```java
Repository<String> safe = new StringRepository();
safe.save("Java");
```

Calling `safe.save(123)` will be rejected at compile time.

## 7. Complete Java 17 Example

Create the file **`OverrideSubstitutionDemo.java`**:

```java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class OverrideSubstitutionDemo {
    static class Repository<T> {
        public T save(T value) {
            return value;
        }

        public List<T> items(T value) {
            return List.of(value);
        }

        public <N extends Number> N number(N value) {
            return value;
        }
    }

    static final class StringRepository extends Repository<String> {
        @Override
        public String save(String value) {
            return value.strip();
        }

        @Override
        public List<String> items(String value) {
            return List.of(save(value));
        }

        @Override
        public <X extends Number> X number(X value) {
            return value;
        }
    }

    static class NumberSource {
        public List<? extends Number> values() {
            return List.of(1, 2);
        }
    }

    static final class IntegerSource extends NumberSource {
        @Override
        public List<Integer> values() {
            return List.of(4, 5);
        }
    }

    public static void main(String[] args) {
        Repository<String> repository = new StringRepository();

        System.out.println(repository.save("  Java  "));
        System.out.println(repository.items("  Generics "));
        System.out.println(repository.number(42));
        System.out.println(new IntegerSource().values());

        Arrays.stream(StringRepository.class.getDeclaredMethods())
                .filter(Method::isBridge)
                .map(m -> m.getName() + "("
                        + Arrays.stream(m.getParameterTypes())
                                .map(Class::getSimpleName)
                                .collect(Collectors.joining(", "))
                        + ") -> " + m.getReturnType().getSimpleName())
                .sorted()
                .forEach(System.out::println);
    }
}
```

Compile with Java 17, or a newer JDK that supports `--release 17`:

```bash
javac --release 17 OverrideSubstitutionDemo.java
java OverrideSubstitutionDemo
```

Stdout:

```text
Java
[Generics]
42
[4, 5]
items(Object) -> List
save(Object) -> Object
```

The first part confirms the return values preserve the generic contract of `Repository<String>`. The last two lines are produced via reflection by filtering `Method.isBridge()`, formatting name/parameters/return type, and sorting by name: the compiler generated bridges for `items` and `save`. The generic method `number` only renamed its type variable and needed no bridge because its underlying descriptor did not change.

### 7.1. Inspecting bytecode signatures

After `javac`, run:

```bash
javap -p -s 'OverrideSubstitutionDemo$StringRepository'
```

Single quotes preserve the `$` character in shells that perform variable expansion. In the corresponding output, you can see:

```text
public java.lang.String save(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/lang/String;

public java.util.List<java.lang.String> items(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/util/List;

public <X extends java.lang.Number> X number(X);
  descriptor: (Ljava/lang/Number;)Ljava/lang/Number;

public java.util.List items(java.lang.Object);
  descriptor: (Ljava/lang/Object;)Ljava/util/List;

public java.lang.Object save(java.lang.Object);
  descriptor: (Ljava/lang/Object;)Ljava/lang/Object;
```

To inspect the bridge flags:

```bash
javap -p -v 'OverrideSubstitutionDemo$StringRepository'
```

Look for `ACC_BRIDGE` and `ACC_SYNTHETIC` on the two forwarding methods. `javap -s` displays descriptors; `javap -v` lets you inspect flags, the `Signature` attribute, and the call target in bytecode.

### 7.2. Static type and runtime type of the same object

```java
Repository<String> repository = new StringRepository();
String name = repository.save("  Java  ");
```

- The compiler views `repository` as `Repository<String>`; `save` accepts and returns `String`.
- The actual object is `StringRepository`.
- When needed, the subclass's bridge ensures calls to the erased descriptor are forwarded to `save(String)`.
- The resulting value is `"Java"` thanks to `.strip()`.
- Substituting `T := String` **does not create** a specialized instance with a runtime field holding the type argument `String`.

These layers work together so code retains compile-time type safety at the source level and polymorphism at runtime.

## 8. Generic Interfaces: Substituting Type Parameters via `implements`

The same mechanism applies to interfaces:

```java
interface Transformer<I, O> {
    O transform(I input);
}

final class LengthTransformer implements Transformer<String, Integer> {
    @Override
    public Integer transform(String input) {
        return input.length();
    }
}
```

With the substitution `I := String`, `O := Integer`, the inheritance contract is `Integer transform(String)`. If you declare `Object transform(Object)` in the implementing class, it does not become the intended override just because the erased types of the original interface are also `Object`. Source checking still relies on **the contract after type parameter substitution**.

A class can inherit type parameters across multiple levels:

```java
interface Sink<T> {
    void accept(T value);
}

abstract class BaseSink<U> implements Sink<U> {
}

final class StringSink extends BaseSink<String> {
    @Override
    public void accept(String value) {
        System.out.println(value);
    }
}
```

Tracing `StringSink -> BaseSink<String> -> Sink<String>` reveals `accept(String)`. Substitutions can occur successively across multiple classes without `StringSink` directly declaring `implements Sink<String>`.

When debugging a complex hierarchy, draw the inheritance path and **record the type arguments along each edge** before reading method bodies or trying casts.

### 8.1. Cannot implement the same generic interface with two different type arguments

A class cannot simultaneously inherit two incompatible specializations of the same generic interface along different inheritance branches, for example `Sink<String>` on one branch and `Sink<Integer>` on another:

```java
interface Sink<T> {
    void accept(T value);
}

interface StringSink extends Sink<String> {
}

interface IntegerSink extends Sink<Integer> {
}

// Invalid:
// class Both implements StringSink, IntegerSink { ... }
```

The compiler rejects `Both` because the same generic superinterface cannot be inherited with different type arguments within a single hierarchy. This is a constraint to account for when organizing interfaces with multiple inheritance.

## 9. Generic Return Types and Wildcards in Overrides

Wildcards are not a tool for freely changing parameter types in overriding methods. They are most useful when the **superclass API is intentionally designed** to permit a narrower return type:

```java
import java.util.List;

interface NumberProvider {
    List<? extends Number> get();
}

final class IntProvider implements NumberProvider {
    @Override
    public List<Integer> get() {
        return List.of(1, 2);
    }
}
```

Here `List<Integer>` is an appropriate subtype of `List<? extends Number>` under wildcard generic type relationships. However, for a method taking `List<Number>` as a parameter, a subclass cannot override it with `List<Integer>`: a `NumberProvider` must be allowed to accept a list of `Number` if the parent contract demands it; narrowing accepted arguments breaks the substitution principle.

Therefore, distinguish **covariant return** (returning a narrower type when valid) from **narrowing a parameter** (you cannot create an override merely by using a subtype of the parent parameter).

## 10. Other Override Rules Still Apply

Substituting `T` with `String` is not enough by itself for an override contract to be valid in all situations. Other Java rules still apply:

- **`static`**: static methods are not instance overrides; a subclass can *hide* a static method under language-permitted conditions.
- **`final`**: `final` instance methods cannot be overridden even if the post-substitution signature matches.
- **`private`**: `private` superclass methods are not inherited for overriding.
- **Access visibility**: visibility cannot be reduced (e.g., overriding `public` with `protected`).
- **Checked exceptions**: an overriding method must not add broader checked exceptions violating the inherited contract; substitution involving generic type variables in `throws` clauses must also satisfy this rule.
- **Return type**: must be return-type-substitutable; you cannot arbitrarily change `List<Number>` to `List<Integer>` or change primitive return types.
- **`@Override`**: helps detect immediately when an intended override is actually an overload, a name clash, or an invalid return type.

The exact conditions for override checking are specified in the Java Language Specification, sections **8.4.2 Method Signature**, **8.4.8 Inheritance, Overriding, and Hiding**, **8.4.5 Method Result**, and the corresponding generic rules. The full rules also consider *subsignature* and *override-equivalent*, so you should not draw conclusions solely from comparing Java names written in source code.

### 10.1. Edge case for legacy code: erasure of generic method signatures

Java allows certain *subsignature* cases to preserve compatibility with generified APIs, where one signature matches the **erasure** of the other. This does not mean every pair of methods with the “same erasure” overrides one another. The `put(Object)` example in `Base<String>` above proved the opposite: the subsignature relationship must be evaluated **after substituting type parameters in the supertype**, not merely by comparing bytecode descriptors.

If you encounter legacy code with raw types, clarify the original API and run the compiler with the relevant warnings enabled:

```bash
javac --release 17 -Xlint:unchecked -Xlint:rawtypes YourFile.java
```

This is an illustrative command to use with an actual project file; replace `YourFile.java` with the exact source filename. Raw type/unchecked warnings are a signal to inspect the generic contract, not default advice to add `@SuppressWarnings`.

## 11. Characteristic Compile Errors

### 11.1. `method does not override or implement a method from a supertype`

Common cause:

```java
class Base {
    <T> void accept(T value) {
    }
}

class Child extends Base {
    @Override
    void accept(String value) {
    }
}
```

The parent method is a **generic method**, with no class type parameter to substitute automatically to `String`. The solution depends on intent:

- To override the generic method: implement the corresponding generic method, such as `<U> void accept(U value)`.
- To make the subclass serve only strings: move the general contract to a **class type parameter** on the parent (`Base<T>`) and have the child `extends Base<String>`.
- To add `String`-specific behavior while keeping the general API: you can write an overload `accept(String)` when the signatures do not clash, while recognizing that it **does not override** the generic method.

### 11.2. `name clash ... same erasure, yet neither overrides the other`

Typical cause:

```java
class Base<T> {
    void accept(T value) {
    }
}

class Child extends Base<String> {
    void accept(Object value) {
    }
}
```

`accept(Object)` in the child does not match `accept(String)` after substituting `T` in the supertype; yet the erased descriptor of the parent method also uses `Object`, causing a clash. The usual fix is `accept(String)`, or renaming/redesigning the API if handling any `Object` is truly required.

### 11.3. `return type ... is not compatible with ...`

Cause:

```java
import java.util.List;

class Base {
    List<Number> read() {
        return List.of(1);
    }
}

class Child extends Base {
    @Override
    List<Integer> read() {
        return List.of(2);
    }
}
```

The child method has a matching parameter list, but `List<Integer>` is not return-type-substitutable for `List<Number>`. The fix is to keep `List<Number>` in the override; or, if you own the parent API and genuinely need flexibility, consider the return type `List<? extends Number>` in the parent contract.

### 11.4. `ClassCastException` in a bridge after using a raw type

Trace the data flow passing through a raw reference or an unchecked cast. If a real `Repository<String>` is used via raw `Repository` to pass an `Integer`, the bridge may have to cast the input to `String` and throw an error. The solution is to fix **the input violating the contract**, not to remove the bridge.

## 12. Review Checklist When Reading Project Code

For a subclass method suspected of failing to override:

1. **Identify the exact parameterized supertype**: for example `extends Repo<String>` or `implements Handler<Long>`.
2. **Trace the inheritance levels** and determine the substitutions for **class/interface** type parameters at each level.
3. **Rewrite the superclass method signature from the subclass's perspective**, including parameters and return type. Distinguish method type parameters from class type parameters.
4. **Check method subsignature and return-type substitutability**; do not rely solely on a subtype relationship of one argument.
5. **Keep `@Override`** on implementations intended to override so the compiler reports mistakes early.
6. If there is a `name clash` error, **compute the erasure of both signatures** and verify whether they share the same JVM parameter descriptor.
7. If the override compiles but bytecode contains unexpected methods, **use `javap -p -s` and `javap -v`**, or `Method.isBridge()`.
8. If a runtime type error occurs, look for raw types, unchecked casts, heap pollution, or contract-violating data, rather than treating compiler-generated bridges as the root cause.

Quick reference table:

| Symptom | What to distinguish | How to handle |
| --- | --- | --- |
| `extends Base<String>` and `Base<T>.set(T)` | Class-level `T` | Override with `set(String)`. |
| `Base.<T> set(T)` | Method-level `T` | Override with the corresponding generic method; `set(String)` is an overload (when valid). |
| Returning `List<Integer>` instead of `List<Number>` | Generic invariance | Keep the exact contract type or design a wildcard in the parent API if allowed. |
| `name clash` with `set(Object)` | Source subsignature differs from erasure | Fix the parameter type after substitution or change the API design. |
| `javap` shows `save(Object)` in subclass | Compiler-generated bridge | Check the bridge flag and dispatch path; do not remove synthetic methods. |
| Raw reference calls subclass via `Object` | Generic contract bypassed | Eliminate raw/unchecked API usage and fix the passed argument. |

## 13. Practice Exercises

**Exercise 1.** Given:

```java
interface Store<T> {
    T add(T value);
}

class IntStore implements Store<Integer> {
    // Which override declaration?
}
```

<details>
<summary>Answer</summary>

```java
@Override
public Integer add(Integer value) {
    return value;
}
```

`T` belongs to the interface `Store<T>`, so it is substituted with `Integer` in `implements Store<Integer>`. Because `Store.add(T)` erases to `add(Object):Object`, the compiler may need a bridge in the implementation.

</details>

**Exercise 2.** Can a superclass method `<X extends Number> X copy(X x)` be overridden by `<Y extends Number> Y copy(Y y)`? Can it be changed to `String copy(String)`?

<details>
<summary>Answer</summary>

Renaming `X` to `Y` with the corresponding bound is valid. `String copy(String)` does not specialize this generic method into an override; if it does not conflict with the inherited method, it is an overload and the generic implementation is still required when demanded by the superclass/interface.

</details>

**Exercise 3.** Why can `StringRepository` contain both `save(String)` and a synthetic `save(Object)` method in the class file, while the Java source code declares only one `save` method?

<details>
<summary>Answer</summary>

`Repository<T>.save(T):T` has the erased descriptor `(Object):Object`, whereas the concrete subclass override has `(String):String`. The compiler generates a `(Object):Object` bridge forwarding the call to `(String):String` to preserve polymorphism after erasure.

</details>

**Exercise 4.** You want `List<Integer>` as the return type of an override. Does a current superclass API returning `List<Number>` allow this? If designing a new API, what choice expresses “a list of elements belonging to Number”?

<details>
<summary>Answer</summary>

You cannot directly override `List<Number>` with `List<Integer>` because of invariance. If you only need to read `Number` values and accept multiple numeric element types, the parent API can expose `List<? extends Number>`; `List<Integer>` is then a compatible return type.

</details>

## 14. Key Takeaways

**Type parameter substitution in overrides** begins at the `extends`/`implements` relationship: when `Base<T>` becomes `Base<String>`, methods using **class-level `T`** must be viewed with `String` when checking overrides. **Method-level type parameters** declared at the method level are not specialized that way; they must retain their generic contract, even though their type variable names can be renamed.

After confirming a valid override at the source level, **erasure** may cause the JVM descriptors of superclass and subclass to differ; the Java compiler generates **bridge methods** to preserve polymorphism. Therefore, diagnosing a generic override error requires clearly distinguishing **source-level substitution**, **override rules**, and **bytecode descriptors/bridges**.
