# Method references and the target type of an expression

A method reference is a concise syntax for turning a method or constructor into an action that can be passed as a value, using the `::` operator. For example, `Integer::parseInt` can replace the lambda `text -> Integer.parseInt(text)`. However, a method reference itself **does not carry an independent function type on its own**: the compiler needs to know the target type to determine the parameters, return type, and which specific method matches.

## 1. What does the target type provide?

A target type is usually a functional interface: an interface with exactly one abstract method to implement (SAM, *single abstract method*). `default` and `static` methods do not increase the number of SAMs.

Example:

~~~java
Function<String, Integer> parser = Integer::parseInt;
~~~

Here, `Function<String, Integer>` is the target type. The abstract method `apply(String)` takes a `String` and returns an `Integer`. Therefore, the compiler looks for an invocation compatible with that signature; `Integer.parseInt(String)` takes a string and returns an `int`, which can be boxed to `Integer`.

The target type usually comes from one of the following contexts:

- **Declaration or assignment:** `Function<String, Integer> parser = Integer::parseInt;`
- **Method parameter:** if `map` accepts `Function<String, Integer>`, the argument `Integer::parseInt` is checked against that type.
- **Return value:** a method returning `Function<String, Integer>` can use `return Integer::parseInt;`.
- **Explicit cast:** `(Function<String, Integer>) Integer::parseInt` provides a target type when a specific interpretation needs to be selected.

Without a target type, an expression such as `var parser = Integer::parseInt;` is invalid: `var` needs to infer the type from the initializer, but a method reference has no independent type to infer in that way. Declare the functional interface type or provide an explicit type context.

## 2. Method reference forms and how to read them

| Form | Example | Possible target type | Meaning |
|---|---|---|---|
| Static method | `Integer::parseInt` | `Function<String, Integer>` | The function parameter is passed as an argument to the static method. |
| Instance method on an existing object (bound) | `System.out::println` | `Consumer<String>` | The object receiving the call is already determined as `System.out`. |
| Instance method on an object taken from the first parameter (unbound) | `String::trim` | `Function<String, String>` | The first parameter becomes the object receiving the call. |
| Constructor | `StringBuilder::new` | `Function<String, StringBuilder>` | Calls the constructor that takes a string. |
| Array constructor | `String[]::new` | `IntFunction<String[]>` | Takes the length and creates a string array. |
| Current or superclass method | `this::validate`, `super::toString` | Compatible functional interface | Calls the method on the current object or the superclass implementation. |

The `String::trim` form requires special attention: even though the syntax contains the class name, this is a reference to an **instance method**. With the target type `Function<String, String>`, the `String` parameter of `apply` becomes the receiver on which `trim()` is called. Similarly, `String::concat` can match `BiFunction<String, String, String>`: the first parameter is the receiver, and the second parameter is the argument passed to `concat`.

The target type also determines the number of parameters the function accepts. A no-argument constructor is commonly used with `Supplier<T>`; a single-argument constructor can be used with `Function<T, R>`; an array constructor is commonly used with `IntFunction<T[]>`. If no standard functional interface fits, a custom functional interface can be defined.

## 3. Runnable Java 17+ example

Save the following code as `TargetTypeMethodReference.java`. The example illustrates multiple forms of method references and shows how the target type affects overload selection.

~~~java
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.IntFunction;

public class TargetTypeMethodReference {
    static String surround(String value) {
        return "[" + value + "]";
    }

    static String render(Object value) {
        return "Object";
    }

    static String render(String value) {
        return "String";
    }

    public static void main(String[] args) {
        Function<String, Integer> parse = Integer::parseInt;
        Function<String, String> trim = String::trim;
        Function<String, String> surrounder =
                TargetTypeMethodReference::surround;
        BiFunction<String, String, String> concat = String::concat;
        Function<String, StringBuilder> builder = StringBuilder::new;
        IntFunction<String[]> arrayFactory = String[]::new;

        Function<String, String> renderString =
                TargetTypeMethodReference::render;
        Function<Object, String> renderObject =
                TargetTypeMethodReference::render;

        System.out.println("parse=" + parse.apply("42"));
        System.out.println("trim='" + trim.apply("  Java  ") + "'");
        System.out.println("surround=" + surrounder.apply("Java"));
        System.out.println("concat=" + concat.apply("Java", " 17"));
        System.out.println("builder=" + builder.apply("code"));
        System.out.println("arrayLength=" + arrayFactory.apply(3).length);
        System.out.println("renderString=" + renderString.apply("x"));
        System.out.println("renderObject=" + renderObject.apply("x"));
    }
}
~~~

Run with JDK 17 or later:

~~~text
javac TargetTypeMethodReference.java
java TargetTypeMethodReference
~~~

Expected output:

~~~text
parse=42
trim='Java'
surround=[Java]
concat=Java 17
builder=code
arrayLength=3
renderString=String
renderObject=Object
~~~

Explanation of the main target types:

- `parse` has type `Function<String, Integer>`, so `Integer::parseInt` is used as a function that takes a string and returns an integer.
- `trim` has type `Function<String, String>`. With `String::trim`, the string parameter becomes the receiver.
- `concat` has type `BiFunction<String, String, String>`, so it requires two parameters: the string receiving the call and the string to concatenate.
- `builder` expects a function taking `String` and returning `StringBuilder`, which matches the `StringBuilder(String)` constructor.
- `arrayFactory` has type `IntFunction<String[]>`, because the array constructor takes a length of type `int`.
- `renderString` and `renderObject` both point to the overloaded method name `render`, but the input parameter types of the functional interfaces differ. With `Function<String, String>`, the `render(String)` overload is a better match; with `Function<Object, String>`, the signature needs to accept `Object`, so the `render(Object)` overload is chosen. Overload selection happens at compile time, based on the static types in context, not on the actual type of the object at runtime.

## 4. Target type and overload resolution

When a method name has multiple overloads, the compiler uses the function signature of the target type to find a matching overload. Important factors include:

1. **Number of parameters:** a target type with one parameter cannot use an overload that requires two parameters, unless another reference form matches.
2. **Parameter types:** the parameter types of the functional interface must be compatible with the parameters/receiver of the referenced method.
3. **Return type:** the result of the method must be compatible with the return type of the SAM, including valid conversions such as boxing, unboxing, and primitive widening.
4. **Ambiguity:** if multiple overloads remain compatible without a most specific choice, the expression does not compile; the target type needs to be clarified.

Example of an ambiguous situation:

~~~java
import java.util.function.Function;
import java.util.function.ToIntFunction;

static void accept(Function<String, Integer> parser) {}
static void accept(ToIntFunction<String> parser) {}

// Potentially ambiguous: Integer::parseInt is compatible with both target types.
accept(Integer::parseInt);

// Clarify the target type with a cast:
accept((Function<String, Integer>) Integer::parseInt);
accept((ToIntFunction<String>) Integer::parseInt);
~~~

`Function<String, Integer>` returns the reference type `Integer`; `ToIntFunction<String>` returns the primitive type `int`. Both can use `Integer.parseInt(String)`, so looking at the method name alone is not enough to choose an overload of `accept`. The two calls with casts clarify the desired functional interface. This snippet is a separate example of overload resolution, not a continuation inside the runnable class in the previous section.

## 5. Target types in generics and method calls

The target type can participate in generic type inference. For example:

~~~java
import java.util.function.Function;

static <T, R> R map(T value, Function<? super T, ? extends R> mapper) {
    return mapper.apply(value);
}

// T is inferred as String; R is inferred as Integer.
Integer result = map("123", Integer::parseInt);
~~~

The `Integer::parseInt` argument is checked against the `mapper` parameter, while the receiving type of `result` provides additional context for the return type `R`. The compiler infers the types so that the entire call is compatible. In Stream pipelines, a similar mechanism appears in calls like `names.stream().map(String::trim)`: the `map` method takes a function, so the element type of the stream helps determine the target type.

If the same intent can be expressed with a lambda, compare their signatures to understand the method reference:

~~~java
Function<String, Integer> a = Integer::parseInt;
Function<String, Integer> b = text -> Integer.parseInt(text);
~~~

The two expressions above are equivalent in purpose in this example. The lambda explicitly shows the parameter and body; the method reference is more concise when the body simply calls a single method with the corresponding parameters.

## 6. Common errors and how to handle them

- **Missing target type:** `var f = String::trim;` does not compile. Declare `Function<String, String> f = String::trim;`.
- **Confusing static and instance:** `Integer::parseInt` calls a static method; `String::trim` is the unbound form of an instance method and requires a string argument as the receiver.
- **Wrong number of parameters:** `String::concat` needs a receiver and an argument to append, so it matches a two-parameter function type such as `BiFunction<String, String, String>`.
- **Ambiguous overload:** multiple methods with the same name may all match the target type. Provide a specific functional interface type or cast the method reference when needed.
- **Incompatible return type:** check the method's return type against the SAM's return type; only conversions allowed by Java are applied.
- **Receiver can be null:** with a bound form like `object::method`, the receiver expression is evaluated when creating the method reference. If the receiver is `null`, creating the reference throws a `NullPointerException`; check the object before creating it.
- **Checked exception:** a referenced method cannot make a checked exception disappear. The SAM type must allow that exception, or the calling code must handle it according to Java rules.

## 7. How to self-check when reading a method reference

When encountering a `TypeOrObject::method` expression, determine in order:

1. Which functional interface provides the target type?
2. How many parameters does the SAM accept, what is each parameter's type, and what type does it return?
3. Is this a static method, an instance method with a fixed receiver, an instance method using the first parameter as the receiver, or a constructor?
4. Are there any overloads compatible with the SAM signature? If there are multiple overloads, do the overload selection rules identify a single unique method?
5. Are the return type, boxing/unboxing, and exceptions compatible?

If you can answer these questions, you can predict how the compiler interprets the method reference before running the program.
