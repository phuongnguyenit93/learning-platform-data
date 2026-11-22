# Generic Interfaces and the Limitation of Generic Functional Methods with Lambdas in Java

Java supports **functional interfaces** and **lambda expressions** to treat behavior as a typed value. When combined with generics, there is an easily confused distinction:

- **The functional interface is generic:** the type parameter is declared at the interface level, and the single abstract method uses that type parameter. In this case, **lambdas can be used** once Java determines an appropriate target type.
- **The single abstract method itself is generic:** that method declares its own type parameter, such as a method with signature <T> T identity(T value). The interface can still be a functional interface, but **a Java lambda cannot directly implement this generic abstract method**.

This lesson explains the boundary between the two kinds of generics, how the compiler infers types, why certain lambdas are invalid, the right solutions in Java 17+, and the impact of wildcards, erasure, and method references on API design.

## 1. Recap: Functional Interfaces and Lambda Target Types

A functional interface has **one effective abstract method** (single abstract method, SAM). You can use @FunctionalInterface so the compiler verifies this constraint. The interface is still allowed to have default, static, and private methods; methods whose signatures match public methods of Object do not create an extra SAM. Certain inheritance cases with equivalent methods merge under Java's rules, so the exact definition is not simply counting declaration lines.

Example:

~~~java
@FunctionalInterface
interface Formatter {
    String format(int value);
}

Formatter formatter = n -> "N=" + n;
System.out.println(formatter.format(3)); // N=3
~~~

This is an **illustrative snippet**, not a standalone program. The lambda n -> "N=" + n does not carry a general function type on its own; in Java, a lambda expression is type-checked against its **target type**, inferred from an assignment, method argument, cast, or return context. Here, the target type Formatter tells us the SAM takes int and returns String.

Java does not infer an independent function type and then automatically convert it to any interface; compatibility is determined by the SAM signature and the context's type constraints.

## 2. Generic Interfaces: Type Parameters Belong to the Interface

Declaration:

~~~java
@FunctionalInterface
interface Mapper<T, R> {
    R map(T value);
}
~~~

T and R are declared **at the Mapper level**, not inside the map method. Each time a concrete parameterized type is used, we get a concrete SAM signature:

| Target type | Behavior signature of map after substituting type arguments | Lambda or method reference |
| --- | --- | --- |
| Mapper<String, Integer> | Integer map(String value) | String::length |
| Mapper<Integer, String> | String map(Integer value) | n -> "value=" + n |
| Mapper<String, String> | String map(String value) | String::trim |
| Mapper<Long, Boolean> | Boolean map(Long value) | n -> n > 0 |

Example:

~~~java
Mapper<String, Integer> length = s -> s.length();
Mapper<Integer, String> label = n -> "length=" + n;

System.out.println(length.map("Java")); // 4
System.out.println(label.map(4));       // length=4
~~~

When checking the first lambda, the compiler already knows T = String and R = Integer. The map method does not declare its own type parameter, so the lambda only needs behavior compatible with **one specialized signature**.

Standard functional interfaces such as java.util.function.Function<T, R>, Predicate<T>, Consumer<T>, Supplier<T>, and UnaryOperator<T> work by the same principle:

~~~java
java.util.function.Function<String, Integer> parse = Integer::parseInt;
java.util.function.Predicate<String> nonBlank = s -> !s.isBlank();
java.util.function.UnaryOperator<String> normalize = String::trim;
~~~

An interface can have multiple type parameters, type bounds, or extend another generic interface; the key factor remains **whether the single abstract method specialized by the target type can be represented by a lambda**.

### 2.1. A Generic Interface Can Still Contain Other Generic Methods

Example:

~~~java
@FunctionalInterface
interface Transform<T, R> {
    R apply(T input);

    default <V> Transform<T, V> andThen(
            Transform<? super R, ? extends V> next) {
        return input -> next.apply(apply(input));
    }

    static <T> Transform<T, T> identity() {
        return input -> input;
    }
}
~~~

The **apply** method is the SAM and does not declare its own type parameter. The andThen method declares V but is **default**, and identity declares T but is **static**; they do not break the functional interface property. Lambdas can still be used for Transform<String, Integer>.

Example of composing functions:

~~~java
Transform<String, Integer> length = String::length;
Transform<Integer, String> toLabel = n -> "size=" + n;
Transform<String, String> composed = length.andThen(toLabel);

System.out.println(composed.apply("ABC")); // size=3
~~~

These are illustrative snippets; the standalone program in section 9 has a corresponding compiled and runnable example.

## 3. Generic Abstract Methods: Type Parameters Belong to the Method

Consider a different interface:

~~~java
@FunctionalInterface
interface UniversalIdentity {
    <T> T same(T value);
}
~~~

**UniversalIdentity is a valid functional interface:** it has a single abstract method named same. Unlike Mapper<T, R>, the same method **declares its own** type parameter T. Each call to same can choose a new T:

~~~java
class IdentityImpl implements UniversalIdentity {
    @Override
    public <T> T same(T value) {
        return value;
    }
}

UniversalIdentity identity = new IdentityImpl();

String text = identity.same("Java");    // T = String
Integer number = identity.same(123);   // T = Integer
~~~

Within the same UniversalIdentity object, the same method must have semantics compatible with **every type T that the caller is allowed to use** according to the signature. This is method-level polymorphism (*generic method* or *method-level polymorphism*).

Read the two signatures carefully:

~~~java
interface PerInstance<T> {
    T same(T value);            // T of the interface
}

interface PerInvocation {
    <T> T same(T value);        // T of the method itself
}
~~~

PerInstance<String> fixes T = String for that instance, so calls use String. PerInvocation allows each call to have a new type argument. The two designs serve different purposes even though both contain the name T.

### 3.1. Why Can @FunctionalInterface Still Be Used?

The single-SAM condition does not exclude generic methods. The @FunctionalInterface annotation only verifies the count and validity of abstract methods under interface rules; it **does not guarantee that every lambda expression is compatible** with that interface.

A takeaway to remember: **every lambda requires a functional interface as its target type, but not every functional interface is a valid target type for a lambda**. A generic SAM is a classic example of the converse.

## 4. The Specific Limitation: Lambdas Cannot Directly Implement a Generic SAM

Try writing:

~~~java
@FunctionalInterface
interface UniversalIdentity {
    <T> T same(T value);
}

// DOES NOT COMPILE — error illustration only:
UniversalIdentity identity = value -> value;
~~~

Java rejects this lambda expression because **the function descriptor is generic**. A lambda has no syntax to declare its own type parameters to represent a function applicable to every T of the same method.

Generics on the functional method differ from the compiler inferring a concrete T for Mapper<String, String>. If the lambda above were accepted as a function specialized for some arbitrary type, it would fail the contract of calling same with any T. If treated as a polymorphic function for all T, Java provides no corresponding syntax/type-checking model for lambdas.

You cannot work around the issue by adding a lambda parameter type:

~~~java
// STILL INVALID for UniversalIdentity:
UniversalIdentity identity = (Object value) -> value;
~~~

Writing (Object value) only specifies the parameter type **Object**, not <T> for the same method itself. The issue here is not simply that Java failed to infer String or Integer.

### 4.1. Do Not Confuse This Error with a Generic Interface

The following two examples are **valid**:

~~~java
Mapper<String, String> echoString = value -> value;
Mapper<Integer, Integer> echoNumber = value -> value;
~~~

They are two Mapper objects with two separate target types. They are **not** a single object with a generic method applicable to all types like UniversalIdentity.

### 4.2. The Limitation Still Applies When the Generic Method Has Bounds

Example:

~~~java
@FunctionalInterface
interface NumberIdentity {
    <N extends Number> N same(N value);
}
~~~

The same method is still generic because it declares N itself. Bounding N extends Number does not remove the lambda limitation. If the domain only needs one fixed type, you can redesign it:

~~~java
@FunctionalInterface
interface NumberTransform<N extends Number> {
    N apply(N value);
}

NumberTransform<Integer> keep = n -> n;
~~~

Here N is a type parameter of the interface and is already chosen as Integer at the target type. However, this choice changes the contract: **one instance holds one type N**, rather than **each call choosing N**.

## 5. Correct Ways to Implement a Generic SAM

### Approach 1: Use a Class or Anonymous Class Implementing the Generic Method

~~~java
UniversalIdentity identity = new UniversalIdentity() {
    @Override
    public <T> T same(T value) {
        return value;
    }
};
~~~

This code is valid because an anonymous class's method **can declare <T> itself**. A named class implementing the generic SAM works the same way:

~~~java
final class IdentityImpl implements UniversalIdentity {
    @Override
    public <T> T same(T value) {
        return value;
    }
}
~~~

Suitable when the behavior truly must apply uniformly across many types in the same instance, or when a clear class name is needed for testing and dependency management.

### Approach 2: Use a Method Reference to a Compatible Generic Method

Java allows certain **method references** to generic methods to adapt to a generic SAM:

~~~java
final class Helpers {
    static <T> T identity(T value) {
        return value;
    }
}

UniversalIdentity identity = Helpers::identity;
System.out.println(identity.same("abc")); // abc
System.out.println(identity.same(42));    // 42
~~~

The case above is **valid**, even though writing identity = x -> x is invalid. The method reference points to an actual generic method that already declares <T>, so the compiler can verify that the referenced method satisfies the SAM's generic signature.

This does **not** mean every method reference can be used with a generic SAM. A method reference to a method taking only String, such as String::trim, cannot satisfy the contract <T> T same(T value) for all T. Return type, parameters, bounds, and checked exceptions must all match.

### Approach 3: If Each Call Does Not Need to Change Types, Move Generics to the Interface

Many practical problems only need to operate on **a single type determined at the use site**, such as parsing strings, normalizing names, or calculating prices:

~~~java
@FunctionalInterface
interface Converter<T, R> {
    R convert(T input);
}

Converter<String, Integer> toInteger = Integer::parseInt;
Converter<Integer, String> toText = n -> "ID-" + n;
~~~

This approach is usually simpler, uses lambdas directly, and preserves strong type checking.

### Approach 4: Use Standard Functional Interfaces When Contracts Match

~~~java
java.util.function.Function<String, Integer> parse = Integer::parseInt;
java.util.function.UnaryOperator<String> trim = String::trim;
java.util.function.Predicate<String> hasText = s -> !s.isBlank();
~~~

Function<T,R> is a generic interface, yet apply(T) is not a generic method. If the goal is taking T and returning R known from context, there is no need to invent a custom interface. Only create a custom interface when the behavior name, contract documentation, or helper methods add real value.

## 6. How Do Regular Generic Methods Combine with Lambdas?

A Java method can declare type parameters **on the method containing the lambda call**, while the lambda still targets a non-generic SAM:

~~~java
static <T> T choose(T first, T second,
                    java.util.function.Predicate<T> preferFirst) {
    return preferFirst.test(first) ? first : second;
}
~~~

When called:

~~~java
String longer = choose("Java", "Go",
    s -> s.length() > 2);
~~~

The compiler infers T = String for **a single call to choose**; then Predicate<String> is the lambda's target type. This is a completely valid use of a generic method with a lambda, because **the SAM Predicate.test(T) does not declare its own type parameter**.

Distinguish two cases:

1. The enclosing/called method (choose) is generic, while the lambda targets an inferred Predicate<T>: **valid**.
2. The single abstract method that the lambda is trying to implement **declares <T> itself**: **invalid**.

### 6.1. Generic Method References Specialized by Target

~~~java
class Helpers {
    static <T> T identity(T value) {
        return value;
    }
}

java.util.function.Function<String, String> stringId =
    Helpers::identity;
java.util.function.Function<Integer, Integer> intId =
    Helpers::identity;
~~~

The same generic method identity can serve as a method reference for target types that are **not generic at the SAM level**. The compiler checks applicability after inferring T from the target. A generic Java method and a generic abstract method are two different things.

## 7. Bounds and Wildcards: Type Safety When Passing Generic Functional Interfaces

In API design, distinguish **type parameters T, R** from **bounded wildcards**:

~~~java
@FunctionalInterface
interface Transformer<T, R> {
    R transform(T value);
}
~~~

A method accepting Transformer can be declared:

~~~java
static <T, R> java.util.List<R> mapAll(
        java.util.List<T> values,
        Transformer<? super T, ? extends R> transformer) {

    return values.stream()
        .<R>map(transformer::transform)
        .toList();
}
~~~

This is an **illustrative snippet** that can be placed alongside the Transformer declaration; the full program in section 9 uses this exact signature.

- **? super T** on input: the transformer can accept T elements because it accepts T or a supertype of T.
- **? extends R** on output: the transformer returns R or a subtype of R, fitting where R is needed.
- This applies the *producer extends, consumer super* (PECS) principle to a behavior that both consumes and produces values.
- **.<R>map(...)** is an explicit type argument on Stream.map to request a Stream<R> result. If left to compiler inference from the method reference alone, it might infer a capture type CAP#1 extends R, and when calling Stream.toList(), List<CAP#1> does not automatically convert to List<R>, because List is invariant.

Example of variance:

~~~java
Transformer<CharSequence, Integer> countChars =
    CharSequence::length;

java.util.List<String> names =
    java.util.List.of("An", "Binh");

// Transformer accepts CharSequence, so it also accepts each String.
java.util.List<Number> lengths =
    mapAll(names, countChars);
~~~

The call can infer T = String and R = Number (assisted by the assignment's target type); the output Integer is a subtype of Number. Remember that **List<Integer> is not a subtype of List<Number>**. The mapAll signature returns List<R> and is type-checked at the call site, with no arbitrary invariant List conversion.

### 7.1. Do Not Arbitrarily Replace Wildcards with Raw Types

~~~java
Transformer raw = (Object value) -> value;
~~~

Raw-type syntax may compile with warnings in certain contexts, but it loses generic information and easily leads to ClassCastException from compiler-inserted casts when using the result. Using a raw type to “dodge” a generic SAM error also does not allow a lambda to implement a method with its own type parameter. Prefer concrete type parameters/wildcards and check compiler warnings.

### 7.2. Bounds Still Constrain Callability

Example:

~~~java
@FunctionalInterface
interface NumberFunction<N extends Number, R> {
    R apply(N number);
}

NumberFunction<Integer, String> format = n -> "n=" + n;
~~~

NumberFunction<String, String> will be invalid because String does not extend Number. A lambda cannot bypass bounds or make an interface accept arbitrary types. Bounds on a generic SAM (e.g., <N extends Number> N same(N n)) must still be respected even when implemented by a named class or method reference.

## 8. Type Erasure, Overloading, and Runtime Limitations

Java generics are primarily checked at **compile time**; type arguments are usually erased (type erasure) when generating bytecode. For Mapper<T,R>, the post-erasure signature essentially works with Object according to the type parameter's bound, while the compiler ensures appropriate casts at use sites.

Example:

~~~java
interface Mapper<T, R> {
    R map(T value);
}

final class Uppercase implements Mapper<String, String> {
    @Override
    public String map(String value) {
        return value.toUpperCase();
    }
}
~~~

At the bytecode level, the compiler may generate a **bridge method** to preserve polymorphism after erasure. This is normal generic interface execution, not evidence that lambdas/generics lose type safety when written properly.

An important consequence: you cannot overload two methods based solely on different generic type arguments of the same interface because their post-erasure signatures collide:

~~~java
// DOES NOT COMPILE — two overloads with the same erasure:
void run(Mapper<String, String> mapper) { }
void run(Mapper<Integer, Integer> mapper) { }
~~~

Do not “fix” this with raw types or unchecked casts. Rename the method, design a generic method run<T>, or add a meaningful distinguishing parameter.

**Generic interfaces are not reified types:** at runtime, you generally cannot directly inspect a Mapper<String, Integer> instance to retrieve the full String/Integer type arguments like a stored Class<T>. If runtime type information is needed for parsing, serialization, or reflection, design the API to accept a Class<T> or an appropriate type token. This limitation is independent of the rule that lambdas do not implement generic SAMs.

### 8.1. Target Types and Overloading Affect Inference

The following example uses an explicit parameter type to provide clear context:

~~~java
Mapper<String, Integer> length = (String s) -> s.length();
~~~

Normally, you do not need to write String in the lambda when the assignment is clear. However, if an overloaded call has multiple compatible SAM functional interfaces, the compiler may report *ambiguous method call*. In that case, provide a variable with an explicit declared type or cast to the intended functional interface, and consider designing more readable overloads.

Do not confuse an ambiguous overload error with the generic SAM limitation: the two errors have different causes.

## 9. Complete Program: Generic Interfaces, Method References, and Generic SAMs

This example compiles with **Java 17 or later**. It demonstrates:

1. Transformer<T,R> as a generic functional interface using lambdas/method references.
2. andThen as a generic default method, while keeping Transformer a functional interface.
3. mapAll as a generic method taking a transformer with appropriate variance.
4. UniversalIdentity having a **generic SAM**; implemented with a named class and a method reference to a generic method.
5. Specializing a generic method to the target Transformer<String,String>.

Create the file **GenericFunctionalDemo.java**:

~~~java
import java.util.List;

public class GenericFunctionalDemo {
    @FunctionalInterface
    interface Transformer<T, R> {
        R transform(T value);

        default <V> Transformer<T, V> andThen(
                Transformer<? super R, ? extends V> next) {
            return value -> next.transform(transform(value));
        }
    }

    @FunctionalInterface
    interface UniversalIdentity {
        <T> T same(T value);
    }

    static final class IdentityImpl implements UniversalIdentity {
        @Override
        public <T> T same(T value) {
            return value;
        }
    }

    static final class Helpers {
        static <T> T identity(T value) {
            return value;
        }
    }

    static <T, R> List<R> mapAll(
            List<T> values,
            Transformer<? super T, ? extends R> transformer) {
        return values.stream()
            .<R>map(transformer::transform)
            .toList();
    }

    public static void main(String[] args) {
        Transformer<String, Integer> length = String::length;
        Transformer<Integer, String> label = n -> "length=" + n;
        Transformer<String, String> pipeline = length.andThen(label);
        System.out.println(pipeline.transform("Java"));

        System.out.println(
            mapAll(List.of("A", "BC", "DEF"), length)
        );

        Transformer<String, String> specialized = Helpers::identity;
        System.out.println(specialized.transform("typed"));

        UniversalIdentity generic = new IdentityImpl();
        System.out.println(generic.same(7));
        System.out.println(generic.same("seven"));

        UniversalIdentity genericRef = Helpers::identity;
        System.out.println(genericRef.same(42));
    }
}
~~~

In the directory containing the file, compile and run:

~~~bash
javac GenericFunctionalDemo.java
java GenericFunctionalDemo
~~~

Exact stdout:

~~~text
length=4
[1, 2, 3]
typed
7
seven
42
~~~

Group-by-group explanation:

- length is Transformer<String,Integer>: the transform SAM takes String and returns Integer. String::length returns int, which is boxed into Integer according to the target type.
- label is Transformer<Integer,String>; andThen chains two behaviors: "Java" → 4 → "length=4".
- mapAll uses the same length transformer on a list of three strings; .<R>map(...) provides the output target type for wildcard compatibility.
- Helpers::identity is a method reference to a generic static method. When the target is Transformer<String,String>, the compiler specializes it for String.
- IdentityImpl actually has the method public <T> T same(T), so one generic instance handles both Integer 7 and String "seven".
- UniversalIdentity genericRef = Helpers::identity is also valid, because a method reference to a generic method satisfies the generic SAM. The last line prints 42.

The program contains no intentionally invalid examples so that the whole file compiles. Earlier invalid snippets were only for analyzing compile-time rules and should not be pasted into the runnable file.

## 10. Which Generic Design Should You Choose in an API?

| Need | Preferred design | Reason |
| --- | --- | --- |
| One instance transforms a fixed T to R | Mapper<T,R> or Function<T,R> | Natural lambda; clear type inference |
| One instance takes input T and returns the same T | UnaryOperator<T> or custom generic interface | Single T at the target type |
| Each call on the same instance must choose its own T | SAM with method-level <T>, if truly needed | Method-level polymorphism; implement via class/compatible method reference |
| Only one utility method needs generics | static <T> T helper(T value) | No need to create a generic SAM |
| Need pipeline composition with flexible input/output | Function.compose/andThen or custom default method using PECS | Composable functions while preserving type safety |
| Want Java lambdas, but generic SAM contract gets in the way | Check if T can be specialized at the interface level | Change contract if domain allows, avoiding casts/raw types |

### 10.1. Do Not Design a Generic SAM Just for “Maximum Reuse”

An interface with the signature <T> T same(T value) makes a very strong commitment: the caller can request a result of the same T for many different types. Most useful conversions such as parsing String to Integer, reading files, or converting JSON to a DTO **do not satisfy the same contract for every T** without a Class<T>, type token, or extra data.

For example, Converter<T,R> accurately reflects that input and output can have different types. If you use a generic SAM <T> T convert(T), a function that only accepts strings is forced to handle all T; that is usually a flawed design even if an implementation class could be written with dangerous casts.

### 10.2. Generics Can Live on the Enclosing Method

If the need is to apply a callback specialized per call, write a normal generic method:

~~~java
static <T, R> R applyOnce(
        T input,
        java.util.function.Function<? super T, ? extends R> fn) {
    return fn.apply(input);
}
~~~

Each call to applyOnce can choose a new T/R and accept a matching lambda:

~~~java
int size = applyOnce("Java", s -> s.length());
String text = applyOnce(12, n -> "n=" + n);
~~~

Here the lambda still targets **Function<T,R> after type inference for each call**, without needing a SAM with a generic abstract method.

### 10.3. Checked Exception Limits Still Apply

A SAM with a throws declaration allows a lambda whose body throws matching checked exceptions; a SAM without throws does not allow the lambda to freely throw unhandled checked exceptions. Generic type parameters, bounds, or method references do not automatically bypass checked exception rules.

~~~java
@FunctionalInterface
interface Loader<T> {
    T load(String path) throws java.io.IOException;
}
~~~

This is a **generic interface with a non-generic SAM**; a file-reading lambda can use Loader<String> if it returns String and obeys the IOException declaration. Do not solve this by catching all Exceptions and returning null, as that loses error semantics.

## 11. Common Mistakes and How to Diagnose Them

**Mistake 1 — equating generic interfaces with generic SAMs.** Seeing <T> in any position and concluding “lambdas cannot be used” is wrong. Ask specifically: is <T> declared after the interface name, or right before the SAM's return type?

**Mistake 2 — thinking @FunctionalInterface guarantees lambda assignment succeeds.** The annotation confirms one effective abstract method. It does not erase the generic method's type parameter, so UniversalIdentity is still rejected by the compiler when using a lambda directly.

**Mistake 3 — fixing with an Object cast.** For a generic SAM, an Object parameter only describes one specific signature; it does not create a method declaring <T>. If the API truly needs to work for all T, keep the generic method and implement it with a class or compatible generic method reference.

**Mistake 4 — replacing Function<T,R> with Function<Object,Object>.** This design loses the static relationship between input and output types, forcing callers to cast and risking ClassCastException. Keep type parameters on the interface or enclosing generic method.

**Mistake 5 — using List<? extends R> and expecting automatic assignment to List<R>.** A producer wildcard does not mean the two List types are subtypes of each other. Review the return signature, use a transformation that builds a valid List<R>, or use explicit type arguments when inference gets captured.

**Mistake 6 — overloading differing only by type arguments.** Two methods taking Mapper<String,String> and Mapper<Integer,Integer> usually collide due to erasure. Create a single generic method, use clearer names, or change the parameter structure.

**Mistake 7 — expecting a generic lambda to be a “higher-rank polymorphic function”.** Java lambdas have no syntax to declare a new type parameter for their own function descriptor. Generic methods, method references, and different functional types solve different problems; there is no magic cast to replace them.

**Mistake 8 — ignoring the target type's name/bounds when debugging.** When a lambda error occurs, check the target functional interface, the SAM signature after substituting type parameters, the return type, overloaded methods, and checked exceptions. The error may be due to type inference, not necessarily the generic SAM concept itself.

## 12. Self-Check Questions

1. Why does Mapper<T,R> with method R map(T value) accept a lambda when the target is Mapper<String,Integer>?
2. Why is UniversalIdentity with method <T> T same(T value) valid with @FunctionalInterface yet cannot be directly assigned value -> value?
3. Why can a generic method reference Helpers::identity implement UniversalIdentity while the equivalent lambda is rejected?
4. Does a default method <V> Transform<T,V> andThen(...) break the functional interface property? Why or why not?
5. Why does Transformer<? super T,? extends R> fit a transformation function, and why does List<? extends R> not automatically convert to List<R>?
6. If each call operates on a different type T, where should generics be placed to both keep the contract accurate and allow lambdas?
7. Why does generic erasure make two overloads differing only in type arguments of the same Mapper invalid?

**Knowledge takeaway:** Java lambdas work effectively with **functional interfaces that are generic at the interface level** because the compiler determines a concrete SAM from the target type. When **the SAM itself declares type parameters**, the interface can still be a functional interface, but a Java lambda cannot directly express that polymorphic method. Use **an implementing class, anonymous class, or method reference to a compatible generic method** if you need to keep a generic SAM; choose **Function<T,R>, UnaryOperator<T>, or a custom generic functional interface** when the domain only needs types fixed at each use site.