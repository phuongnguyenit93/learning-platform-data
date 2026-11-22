# Type Name Shadowing and Why Reusing the Name T Should Be Avoided in Java Generics

In Java Generics, `T` is the **name of a type variable (type parameter)**, not a fixed type or a variable storing data. That name has **scope** just like other names in a program. A generic class can declare `T`, and then a generic method or inner class inside it can declare **a new `T`**. Within the inner scope, the new `T` *shadows* the outer `T`.

This syntax may be valid, yet it easily leads readers to assume the two `T` symbols denote a single type. The result is broken API contracts, assignments rejected by the compiler, or unnecessary casts added to "fix" errors. This lesson focuses on the **shadowing mechanism of type parameters**, how to recognize scope, distinguish identically named `T`s, understand type bounds, and choose naming that keeps generic code clear and safe.

Standalone runnable examples use Java 17 or later. Lines intentionally causing compilation errors are commented out and explained separately.

## 1. Recap: Where Does the Name T Appear?

A simple generic class:

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
```

`T` is declared immediately after the class name in `Box<T>`. Every occurrence of `T` in the instance members above points to **the class's own type parameter**. For `Box<String>`, the compiler sees `Box.get()` as returning `String`, while `Box<Integer>` produces a result of type `Integer`.

Compare with:

```java
class Utilities {
    static <T> T identity(T value) {
        return value;
    }
}
```

Here `<T>` sits before the method's return type. `T` is **the method's type parameter**; the `Utilities` class declares no `T` at all. There is no shadowing because no identically named type parameter exists in an accessible enclosing scope.

Now consider this example:

```java
class Box<T> {
    <T> T echo(T input) {
        return input;
    }
}
```

The two `<T>` tokens are **two different declarations**:

- `Box<T>` declares a `T` belonging to the class.
- `<T> T echo(T input)` declares a new `T` belonging to the method, causing single-name uses of `T` within the method's scope to denote **the method's `T`**.
- The method's `T` is inferred per call to `echo`, independent of the type argument of a `Box<T>` instance.
- There is no mechanism where "the compiler automatically treats two `T`s as the same" simply due to matching names.

Understanding the exact **declaration site** matters more than memorizing the name `T`.

## 2. What Is Shadowing, and How Does It Differ from Reusing a Name in Disjoint Scopes?

Shadowing occurs when a name declaration in an inner scope hides an identically named declaration in an enclosing scope. With generic type parameters, the following structure is very easy to misread:

```java
class Holder<T> {
    <T> T echo(T input) {
        return input;
    }
}
```

The name `T` in the method declaration hides the class's `T` in the region where the method's type parameter is in effect. When the compiler resolves `T input` or the return type `T` of `echo`, it looks up `T` in the method scope first.

Seeing two `T`s in a project does not automatically mean shadowing is occurring. Two independent generic methods in the same class, such as `<T> T first(T x)` and `<T> T last(T x)`, have separate, **non-nested** type-parameter scopes. Having each method use the conventional name `T` is completely normal. The issue arises when **two declarations share the same name with overlapping scopes**, causing readers to misidentify which level a `T` belongs to.

A type argument is not a new declaration either:

```java
class Holder<T> {
    java.util.List<T> asList(T item) {
        return java.util.List.of(item);
    }
}
```

`List<T>` here is **using** `T` from `Holder<T>`; `List<T>` does not declare another `T` that shadows the name. Angle brackets `<...>` in Java can either *declare a type parameter* (after class/method) or *pass a type argument* (after a generic type name), so you must check the **syntactic position** before drawing conclusions.

## 3. Runnable Example: Two Identically Named Yet Independent T's

Create `ShadowingDemo.java`:

```java
public class ShadowingDemo {
    static final class Holder<T> {
        private final T stored;

        Holder(T stored) {
            this.stored = stored;
        }

        T get() {
            return stored;
        }

        <T> T echo(T input) {
            return input;
        }
    }

    public static void main(String[] args) {
        Holder<String> holder = new Holder<>("Java");

        String stored = holder.get();
        Integer echoedNumber = holder.echo(42);
        Boolean echoedBoolean = holder.echo(true);

        System.out.println(stored);
        System.out.println(echoedNumber);
        System.out.println(echoedBoolean);
    }
}
```

Compile and run with JDK 17+:

```bash
javac ShadowingDemo.java
java ShadowingDemo
```

`stdout`:

```text
Java
42
true
```

Analysis across the two scopes:

| Symbol in source | Declared at | Type in the call under consideration |
| --- | --- | --- |
| `T` in `Holder<T>` | Class `Holder` | `String` because the receiver is `Holder<String>` |
| `T stored` | Uses class's `T` | `String` |
| `T get()` | Uses class's `T` | Returns `String` |
| `<T>` on `echo` | Declares new `T` belonging to method | Re-inferred on each call |
| `T input` in `echo` | Uses method's `T` | `Integer` for `echo(42)`, `Boolean` for `echo(true)` |
| Return `T` from `echo` | Uses method's `T` | Correspondingly `Integer`, `Boolean` |

Neither call to `echo` changes the type argument of `Holder<String>`. The object still stores `String` in `stored`. The `echo` method simply accepts and returns a value of **its own method-inferred type**.

If a reader sees `Holder<String>` and thinks `echo` "only accepts String", they have confused the class's `T` with the method's `T`. This is one reason to avoid redeclaring the name `T` in an inner scope when two kinds of data are independent.

## 4. A More Dangerous Mistake: Assuming T in the Method Is the Field's T

Consider the illustrative class:

```java
class ConfusingStore<T> {
    private T stored;

    ConfusingStore(T stored) {
        this.stored = stored;
    }

    <T> void replace(T incoming) {
        // this.stored = incoming; // Compilation error.
    }
}
```

The author might think `replace` accepts the same type as `stored`. However:

1. `stored` is declared using the **class's** type parameter `T`.
2. `<T>` right before `void replace` declares a **different** type parameter.
3. `incoming` has the **method's** `T`, because that name shadows the class's `T` here.
4. From the compiler's perspective, there is no constraint guaranteeing that a value of the method's `T` can be assigned to a field of the class's `T`.
5. The compiler rejects `this.stored = incoming` even though both letters in the source code are written `T`.

This does not depend on whether the same kind of object happens to be passed at runtime. A method body must be valid for all type arguments permitted by its declaration.

### Proper Fix When the Method Must Accept the Same Type as the Field

Remove the redundant `<T>` declaration:

```java
class Store<T> {
    private T stored;

    Store(T stored) {
        this.stored = stored;
    }

    void replace(T incoming) {
        this.stored = incoming;
    }

    T get() {
        return stored;
    }
}
```

Now `T incoming` refers directly to the class's `T`. With `Store<String>`, the compiler only allows `replace` to accept values compatible with `String`.

Also remember: `this.` selects an **object's field/member**, but **it does not turn the method's type name `T` into the class's `T`**. In the failing example, `this.stored` still has the class's type, and `incoming` still has the method's type. Adding `this.` does not mend a type relationship that has already been split.

## 5. How to Fix When the Method Truly Has an Independent Type

Sometimes a method intentionally accepts a different type from the data the class holds. In that case keeping a generic method is right, but **rename the type parameter** for clarity.

Create `ClearNamesDemo.java`:

```java
import java.util.function.Function;

public class ClearNamesDemo {
    static final class Holder<T> {
        private final T stored;

        Holder(T stored) {
            this.stored = stored;
        }

        T get() {
            return stored;
        }

        <R> R map(Function<? super T, ? extends R> mapper) {
            return mapper.apply(stored);
        }

        <U> U echo(U input) {
            return input;
        }
    }

    public static void main(String[] args) {
        Holder<String> holder = new Holder<>("Java");

        Integer length = holder.map(String::length);
        Boolean yes = holder.echo(true);

        System.out.println(holder.get());
        System.out.println(length);
        System.out.println(yes);
    }
}
```

Run:

```bash
javac ClearNamesDemo.java
java ClearNamesDemo
```

`stdout`:

```text
Java
4
true
```

Now the role of each type variable is crystal clear:

- `T` of `Holder<T>` is the **type of the stored value**, e.g., `String`.
- `R` of `<R> R map(...)` is the **result type of the transformation**. `Function<? super T, ? extends R>` connects the class's input `T` to the method's output `R`.
- `U` of `<U> U echo(U input)` is the input/output type specific to the `echo` method, completely independent of `T`.
- No name is shadowed. Readers easily see that `map` depends on the data inside the object while `echo` does not.

In many APIs, names more meaningful than `T`/`U` are also very helpful: `<ID, ENTITY>`, `<INPUT, OUTPUT>`, or `<SOURCE, RESULT>`. Still, short conventional names like `T`, `E`, `K`, `V`, `R`, `U` remain appropriate when signatures are simple. What should be avoided is **redeclaring the same name in nested scopes**, not banning the letter `T` altogether.

## 6. Bounds on Two T's Do Not Merge into One Shared Bound

When type parameters have `extends` bounds, reusing the same name becomes even more misleading.

```java
class NumberHolder<T extends Number> {
    private final T number;

    NumberHolder(T number) {
        this.number = number;
    }

    <T extends CharSequence> int lengthOf(T text) {
        return text.length();
    }

    Number asNumber() {
        return number;
    }
}
```

Here the two `T`s are different:

- The class's `T extends Number` constrains the value stored in `number`; the compiler allows treating it as `Number`.
- The method's `T extends CharSequence` constrains the `text` parameter; the compiler allows calling `text.length()`.
- The `Number` bound does not "flow" into the method's `T`; nor does the `CharSequence` bound apply back to the field.
- If the method tries to assign `text` to `number`, the compiler has no reason to permit it.

Runnable program `BoundShadowingDemo.java`:

```java
public class BoundShadowingDemo {
    static final class NumberHolder<T extends Number> {
        private final T number;

        NumberHolder(T number) {
            this.number = number;
        }

        <T extends CharSequence> int lengthOf(T text) {
            return text.length();
        }

        double doubleValue() {
            return number.doubleValue();
        }
    }

    public static void main(String[] args) {
        NumberHolder<Integer> holder = new NumberHolder<>(12);

        System.out.println(holder.doubleValue());
        System.out.println(holder.lengthOf("Java"));
    }
}
```

Run:

```bash
javac BoundShadowingDemo.java
java BoundShadowingDemo
```

`stdout`:

```text
12.0
4
```

This code compiles, yet in readability it is inferior to naming `<S extends CharSequence>` on the method. Having two very different bounds share the name `T` does not help convey meaning; it creates pointless name collision.

**Clearer version:**

```java
class NumberHolder<N extends Number> {
    private final N number;

    NumberHolder(N number) {
        this.number = number;
    }

    <S extends CharSequence> int lengthOf(S text) {
        return text.length();
    }
}
```

Using `N` for the number type and `S` for the sequence type eliminates guessing about scope.

## 7. Inner Classes Can Also Shadow an Outer Class's Type Parameter

Nested scopes are not limited to class–method. A **non-static inner class** can declare a type parameter with the same name as the outer class. This form of shadowing is especially easy to confuse when writing multiple generic layers.

Create `NestedShadowingDemo.java`:

```java
public class NestedShadowingDemo {
    static class Outer<T> {
        private final T outerValue;

        Outer(T outerValue) {
            this.outerValue = outerValue;
        }

        class Inner<T> {
            private final T innerValue;

            Inner(T innerValue) {
                this.innerValue = innerValue;
            }

            String describe() {
                return outerValue + " / " + innerValue;
            }

            T inner() {
                return innerValue;
            }
        }
    }

    public static void main(String[] args) {
        Outer<String> outer = new Outer<>("outer");
        Outer<String>.Inner<Integer> inner = outer.new Inner<>(7);

        System.out.println(inner.describe());
        System.out.println(inner.inner());
    }
}
```

Run:

```bash
javac NestedShadowingDemo.java
java NestedShadowingDemo
```

`stdout`:

```text
outer / 7
7
```

Tracing the two `T`s:

1. `Outer<T>` declares a type parameter of the outer class.
2. `Inner<T>` declares **its own type parameter** for the inner class; within `Inner`'s declaration scope, the inner `T` hides the outer `T`.
3. The `outerValue` field was already declared with the outer `T`; it does not automatically change type just because an inner method references it.
4. The `innerValue` field belongs to `Inner<T>`, so it uses the inner `T`.
5. With `Outer<String>.Inner<Integer>`, the outer value has type `String` and the inner value has type `Integer`.

The type syntax `Outer<String>.Inner<Integer>` is especially revealing: it makes explicit that outer and inner have **two independent type argument choices**.

### Fixing to Avoid Shadowing

```java
class Outer<T> {
    class Inner<U> {
        private U innerValue;
    }
}
```

This is an illustrative declaration. `T` belongs to outer, `U` belongs to inner; every subsequent use is clear. When interacting with outer, inner can use outer fields or methods according to the already-declared type relationship.

### Static Nested Classes Are Not the Exact Same Case

A `static class Nested<U>` placed inside a generic outer class **does not** carry the type argument context of an outer instance. Therefore, declaring a type parameter on a static nested class should not be called a completely equivalent example to non-static inner class shadowing. If a static nested class needs to hold a different kind of data, declare its own type parameters and pass the required data into its constructor.

## 8. Static Methods and a Generic Class's Name T

A class's type parameter is tied to parameterizing objects, whereas `static` members belong to the class itself, not to a specific `Box<String>` or `Box<Integer>`. Therefore, a static method cannot directly use the class-level `T` as if it already had a concrete type argument.

```java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    // static T wrong(T input) { return input; } // Invalid.

    static <U> Box<U> of(U input) {
        return new Box<>(input);
    }
}
```

In `static <U> Box<U> of(U input)`, `U` is a type parameter **of the static method**. It does not point to the type parameter `T` of any `Box<T>` object. Choosing the name `U` helps readers clearly see its origin.

You could also write `static <T> Box<T> of(T input)`, which is a valid generic method with `T` belonging to the method, but using `U` avoids giving the impression of accidentally reusing the class's `T`. When reading code, separate these two levels, especially in factory methods.

## 9. Shadowing Differs from Type Inference and Type Erasure

These three concepts are sometimes conflated:

| Concept | Where it occurs | Effect |
| --- | --- | --- |
| **Shadowing** | Declaration syntax and scope | The name `T` in an inner scope refers to the new type parameter instead of the outer type parameter |
| **Type inference** | Compile-time call checking | Finds type arguments satisfying the constraints of a generic method/class |
| **Type erasure** | How generics compile to bytecode | Most type arguments are not present as runtime specializations; the compiler inserts casts/bridges when needed |

A method `<T> T echo(T)` can hide an outer class's `T` right in source code, and then at the invocation `echo(123)` the compiler infers the **method's** `T` as matching `Integer`. The erasure of an unbounded method `T` is typically `Object`. Each concept answers a different question:

- Shadowing: **where is this name `T` declared?**
- Inference: **what type is `T` inferred to be for a specific call?**
- Erasure: **how is the generic type represented at runtime?**

Reusing the name `T` neither causes the JVM to generate two new runtime classes nor forces two type parameters to share the same type argument.

## 10. Signs in the IDE and Compiler Errors

### 10.1. Assigning Method T to Class T Fails

```java
class Store<T> {
    private T stored;

    <T> void set(T incoming) {
        // stored = incoming; // Incompatible types.
    }
}
```

The compiler cannot guarantee the assignment: method-level `T` and class-level `T` are two independent declarations. A specific method call might infer the same type, yet the implementation must hold for every valid call. Fix it with `void set(T incoming)` if the same class `T` is genuinely needed.

### 10.2. Return Type Looks Like T but Does Not Match the Object's Type

```java
class Holder<T> {
    T saved;

    <T> T echo(T input) {
        return input;
    }
}
```

With `Holder<String> holder`, `holder.echo(1)` can produce an `Integer` result. If the API author promised "echo returns the same type as the stored data", the signature violates that intent even though it compiles.

### 10.3. A Method Declared with a Misleading Type Variable Name

```java
class Cache<K, V> {
    <V> V convert(V input) {
        return input;
    }
}
```

`<V>` on the method hides `V` of `Cache<K,V>`. `convert` does not necessarily relate to values of type `V` in the cache. Change it to `<R> R convert(R input)` if completely independent, or remove the new type parameter if the method must use the cache's value type.

### 10.4. Errors "Fixed" with Unsound Casts

When encountering incompatible types caused by shadowing, do not add an unchecked cast such as `(T) incoming` to silence the compiler. Type erasure can prevent the cast from verifying the intended type argument, deferring failure until data is read. Fix the **scope declaration** and API contract first.

### 10.5. Tooling Suggests the Same Name T Twice

In an IDE, use "go to declaration" on each `T`. If it jumps to `<T>` on the method instead of `class Box<T>`, you have identified shadowing. Displaying types on expressions, inspecting generic signatures, and enabling compiler warnings can help catch the issue early. A linter may warn about hidden type parameters depending on configuration, though such a warning should not be treated as mandatory across every Java build.

## 11. Why Avoid Shadowing Type Parameter Names?

### 11.1. Prevents Misreading the API Contract

Someone reading `class Service<T> { <T> T transform(T x) ... }` tends to assume `transform` depends on `Service<T>`'s type. In reality the method's `<T>` severed that relationship. Using a different name like `<R>` lets readers recognize the relationship (or independence) faster.

### 11.2. Easier to Track Constraints When Extending a Method

A small method might only contain `return input`, but when adding fields, mappers, or collections, you need to distinguish the type stored in the class from a new input type. Duplicate names make adding code prone to incompatible types and unsafe casts.

### 11.3. Refactoring with Fewer Scope Mistakes

Changing `<T> T echo(T)` to "store the value in field `T`" can be tripped up by the new method-level `T`. If named clearly from the start as `<U> U echo(U)`, adding code makes it immediately obvious that `U` cannot be assigned directly to field `T`.

### 11.4. Code Reviews Accurately Identify Generic Bounds

When a class has `<T extends Number>` while a method has `<T extends CharSequence>`, using `T` for both obscures two completely different capabilities. Using `N` and `S`, or `NUMBER` and `TEXT`, exposes the real contracts.

### 11.5. Easier to Verify the Link Between Input and Output

In a transformation API, `<R> R convert(Function<? super T,? extends R> f)` shows that the class's data `T` is transformed into `R`. When both variables are written `T`, this independence is obscured.

What needs to be avoided is **ambiguity caused by duplicate names in nested scopes**. There is no need to invent long, complicated names or replace every `T` in a project with one rigid naming scheme.

## 12. When Is Reusing the Name T Still Fine?

`T` is a very common convention for "an unknown type". Using `T` across independent scopes is natural:

```java
class Utilities {
    static <T> T first(java.util.List<T> values) {
        return values.get(0);
    }

    static <T> T last(java.util.List<T> values) {
        return values.get(values.size() - 1);
    }
}
```

Both methods declare their own `<T>`, without nesting; each method has only one type variable, and every position of `T` inside that method links together as intended. The name `T` is valuable for its simplicity.

Likewise, `class Box<T>` and `class Queue<T>` in two different top-level classes use `T` independently; there is no conflict. Shadowing is worth avoiding when **an inner-scope declaration of `T` hides an outer-scope `T`** and readers can easily mistake them as having the same meaning.

Practical rules:

- A single type variable in a short scope: `T` is usually clear enough.
- Two independent type variables in the same signature: `T,R` or role-based names.
- A generic class and a generic method inside that class: use a different name if the method declares a new type variable.
- Nested non-static generic class: do not reuse the enclosing generic class's name.
- When a method needs the class's own `T`: **do not** add another `<T>`.
- When a method is unrelated to the class's `T`: name it `<U>`, `<R>`, or a meaningful identifier.

## 13. Distinguishing Shadowing from Easily Confused Concepts

### 13.1. Type Parameter Shadowing vs. Local Variable Shadowing

```java
class Example<T> {
    private int size = 5;

    void print(int size) {
        System.out.println(size);
        System.out.println(this.size);
    }
}
```

The illustration above has a **parameter named `size`** hiding a **field named `size`**. `this.size` can be used to refer to the field. However, when a method declares `<T>` hiding the class's `T`, `this.T` is **not valid Java syntax** to refer to the class's type variable. The usual fix is not to reuse the type parameter name or to redesign the type relationship; `this` does not open a direct access path to "the class's type `T`" under another name.

### 13.2. Shadowing Differs from Method Overriding

Overriding is when a subtype provides an implementation of an inherited method according to signature/return-type rules. Shadowing `T` is **name resolution in source code**, not overriding, not overloading, and does not directly affect dynamic dispatch.

### 13.3. Shadowing Differs from Naming a Subclass Type Parameter the Same

```java
class Parent<T> {
    T value;
}

class Child<T> extends Parent<T> {
}
```

This is an example of type argument forwarding: `Child<T>` declares **Child's** type parameter, then uses that very parameter as the type argument for `Parent<T>`. The two type parameter declarations of `Parent` and `Child` are independent, yet the subclass **binds them together in the `extends Parent<T>` clause**. You should not look at the two `T` names and treat this as a shadowing mistake with the same structure as a method inside a class.

If written `class Child<U> extends Parent<U>`, the meaning stays the same while the distinction between declarations can be clearer. Choose naming suited to the context; do not judge from names alone.

### 13.4. Different Type Parameter Names Do Not Create Different Overloads

Two generic methods:

```java
// Cannot be declared together in the same class:
static <T> void log(T value) {}
static <U> void log(U value) {}
```

will conflict because after type erasure they have the same runtime signature corresponding to `log(Object)`. Renaming `T` to `U` does not create a new overload, nor is it related to shadowing between a class and a method.

### 13.5. Type Parameter vs. Type Argument

In `class Box<T>`, `<T>` declares. In `Box<String>`, `<String>` passes a type argument. In `List<T>` inside `Box<T>`, `T` is only **used**, not newly declared. These similar-looking syntaxes play different roles, so you must determine the position before talking about shadowing.

## 14. Type Parameter Shadowing and Generic Interfaces

A generic class can use its own type parameter to implement an interface:

```java
interface Container<E> {
    E read();
}

class ValueContainer<T> implements Container<T> {
    private final T stored;

    ValueContainer(T stored) {
        this.stored = stored;
    }

    @Override
    public T read() {
        return stored;
    }
}
```

`T` of `ValueContainer<T>` is the type argument passed to `Container<E>`. The `implements Container<T>` clause **does not create a new type variable**. In this class, `read()` returns `ValueContainer`'s `T` matching `Container`'s contract.

If a generic method is added:

```java
class ValueContainer<T> implements Container<T> {
    private final T stored;

    ValueContainer(T stored) {
        this.stored = stored;
    }

    @Override
    public T read() {
        return stored;
    }

    <R> R convert(java.util.function.Function<? super T, ? extends R> f) {
        return f.apply(stored);
    }
}
```

Now the class's `T` connects to the interface and the mapper's input; the method's `R` carries the result type. There is no shadowing; type relationships in the signature are expressed accurately and remain maintainable.

## 15. Reflection Can Distinguish Two TypeVariables Named T

This section is for readers already familiar with reflection; it clarifies that two identically named type variables **do not have identical declarations**. Java reflection provides `TypeVariable<?>` with its corresponding name and `GenericDeclaration`.

Create `TypeVariableIdentityDemo.java`:

```java
import java.lang.reflect.Method;
import java.lang.reflect.TypeVariable;

public class TypeVariableIdentityDemo {
    static class Holder<T> {
        <T> T echo(T value) {
            return value;
        }
    }

    public static void main(String[] args) throws Exception {
        TypeVariable<?> classT = Holder.class.getTypeParameters()[0];
        Method method = Holder.class.getDeclaredMethod("echo", Object.class);
        TypeVariable<?> methodT = method.getTypeParameters()[0];

        System.out.println(classT.getName());
        System.out.println(methodT.getName());
        System.out.println(
                classT.getGenericDeclaration().equals(
                        methodT.getGenericDeclaration()));
    }
}
```

Run:

```bash
javac TypeVariableIdentityDemo.java
java TypeVariableIdentityDemo
```

`stdout`:

```text
T
T
false
```

Both type variables have `getName()` equal to `"T"`. Yet their originating declarations differ: `classT` belongs to `Holder.class`, and `methodT` belongs to the `echo` method. The `false` result in the comparison shows they are not the same generic declaration. The `echo(T)` method has an unbounded type parameter so its runtime parameter is erased to `Object`, which is why `getDeclaredMethod("echo", Object.class)` finds the right method.

Reflection does not turn generic type arguments into separate per-object runtime types. It only allows inspecting metadata of **declarations** retained in the class file. You do not need reflection to use generics normally; this example only reinforces why two identically named type variables must not be treated as one.

## 16. Exercises: Identifying and Fixing Shadowing

### Exercise 1 — Predict the Types

Given:

```java
class Container<T> {
    T get() { return null; }

    <T> T identity(T x) {
        return x;
    }
}
```

For a variable `Container<String> c`:

- What is the expression type of `c.get()`?
- What can `c.identity(123)` return?
- Do the two `T`s in the class and method belong to the same declaration?

**Answer:** `get()` has static type `String`; `identity(123)` can infer the method's `T` as `Integer`; the two `T`s belong to two different declarations. `get()` in the snippet returns null, so do not assume it is a store holding real data.

### Exercise 2 — Find the Error in the Setter

```java
class Store<T> {
    private T value;

    <T> void set(T v) {
        // value = v; // Why does this fail to compile?
    }
}
```

**Answer:** `v` has the type variable `T` belonging to the method, while `value` belongs to the class. To make the setter accept the same type as the field, remove `<T>` from the method and write `void set(T v) { value = v; }`.

### Exercise 3 — Method with a New Result Type

Instead of:

```java
class Box<T> {
    T value;

    <T> T transform(java.util.function.Function<T, T> mapper) {
        return null;
    }
}
```

write a method that converts the type of the field's value from `T` to `R` without modifying the field.

**Sample answer:**

```java
<R> R transform(java.util.function.Function<? super T, ? extends R> mapper) {
    return mapper.apply(value);
}
```

`T` is taken from the generic class, `R` is declared by the method. If you want to return a `Box<R>` instead of `R`, you can create `new Box<R>(...)` with an appropriate constructor. This is an illustrative method snippet to be placed inside a class that has `T value`.

### Exercise 4 — Two Bounds with the Same Name

A class declares `<T extends Number>`, and a method in the class declares `<T extends CharSequence>`. Can the method call `length()` or `doubleValue()` on a parameter having the method's type variable `T`?

**Answer:** It can call `length()` because the method's `T` has bound `CharSequence`; the compiler does not guarantee `doubleValue()`. The `Number` bound belongs to the class's `T` and does not propagate into the method's `T`.

### Exercise 5 — Outer and Inner

With `Outer<String>.Inner<Integer>` in the earlier example, determine the types of `outerValue` and `innerValue`. If the inner declaration is changed to `class Inner<U>`, how should the type annotation be written?

**Answer:** `String` and `Integer`, respectively. With the `Inner<U>` declaration, the use site still has the form `Outer<String>.Inner<Integer>`; inside inner's source code, use `U` instead of `T` to refer to inner's component type.

### Exercise 6 — Two Independent Generic Methods

```java
static <T> T left(T a, T b) { return a; }
static <T> T right(T a, T b) { return b; }
```

Is this a case where reusing the name `T` should be forbidden?

**Answer:** No. The two method-level `T`s have separate scopes, are not nested, and do not shadow an outer class's `T`; sharing the conventional name is readable.

### Exercise 7 — Review an API Before and After

**Before:**

```java
class Holder<T> {
    T stored;
    <T> T echo(T input) { return input; }
}
```

**After:**

```java
class Holder<T> {
    T stored;
    <U> U echo(U input) { return input; }
}
```

Answer: Does the `echo` method in either version have a type relationship with the `stored` field? Does renaming change runtime behavior?

**Answer:** Neither version links the method argument's type to `stored`. Renaming from method `T` to `U` clarifies the source contract without changing logic, without creating a specialized class, and without altering how Java Generics undergo type erasure. The result of calling the method is still inferred by the compiler from the call site as before.

## 17. Checklist When Reading or Reviewing Type Parameter Names

When a generic code snippet has multiple declaration levels, ask in order:

1. **Where is the `T` under consideration declared?** Class, interface, record, method, or constructor?
2. Is there a **new** `<T>` inside the scope of a class/interface that already has `T`?
3. Does this method want to use the type stored in the object, or declare an independent input/result type?
4. Is the same name `T` used at two levels with different bounds?
5. Which fields, parameters, and return types must be bound to the **class's `T`**?
6. Which positions represent a new result type that should be named `R` or `U`?
7. Did anyone use an unchecked cast to "fix" an error originally caused by redeclaring a type parameter?
8. In a nested class, is `<T>` a new declaration or merely a type argument of another generic type?
9. Are type arguments at call sites inferred properly without treating the name `T` as a concrete runtime type?
10. Do the type names help readers recognize data relationships, or do they hide independence between types?

If using the same `T` at two declaration levels could cause readers to answer these questions wrongly, rename the inner-level type parameter or remove the redundant type parameter declaration. Keep the name `T` when it has only one clear meaning in the scope being read.

## 18. Conclusion

**Type parameter shadowing is a compile-time name-scoping rule.** In `class Box<T> { <T> T echo(T value) ... }`, the method's `T` is a new declaration and shadows the class's `T`. Writing the same letter `T` neither makes the two types related nor causes the JVM to store two different runtime types by name.

When a method needs to operate on stored data, **use the class's `T` directly** without redeclaring it. When a method needs its own type, name it `<R>`, `<U>`, or a role-based name to reveal the relationship: `T` for existing input, `R` for a new result, `U` for an independent type. Distinguishing scope, inference, and erasure helps you read generic signatures accurately, avoid unnecessary casts, and maintain clear APIs as a program grows.
