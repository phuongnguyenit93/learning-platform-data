# Generic Methods and Differences from Generic Types in Java

## 1. Two Places to Declare Type Parameters

A **generic type** declares type parameters after the class or interface name. A **generic method** declares its own type parameters directly in the method signature, before the return type.

~~~java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    <U> U echo(U input) {
        return input;
    }
}

class Utility {
    static <T> T identity(T input) {
        return input;
    }
}
~~~

In **`Box<T>`**, T belongs to the class scope; get() uses T, but get() itself is not a generic method. The **echo** method declares its own U, so the same `Box<String>` can still call echo(42) and receive an Integer. **Utility.identity** shows that a generic method does not require the enclosing class to be generic.

## 2. Syntax and Type Inference

General form:

~~~java
static <T> T first(List<T> values) {
    return values.get(0);
}
~~~

The **`<T>`** part declares the method's type parameter; the following T is the return type; `List<T>` links the input element type to the result type. When calling first(List.of("red", "blue")), the compiler infers T as String, so the result has type String without needing a cast.

You can explicitly specify a type argument using a type witness when you want to make the intent clearer:

~~~java
String inferred = first(List.of("red", "blue"));
String explicit = Utility.<String>identity("Java");
~~~

Normally, the compiler infers the type automatically from the arguments and context. A type witness is optional when inference is already clear enough; it does not make incompatible types valid.

## 3. Complete Example: Multiple Generic Methods in a Regular Class

Save the code to **GenericMethodDemo.java**:

~~~java
import java.util.List;

final class TextTools {
    private TextTools() {
    }

    static <T> T first(List<T> values) {
        if (values.isEmpty()) {
            throw new IllegalArgumentException("values must not be empty");
        }
        return values.get(0);
    }

    static <T> void showPair(T left, T right) {
        System.out.println(left + " | " + right);
    }

    static <T extends Number> double sum(List<T> values) {
        double total = 0.0;
        for (T value : values) {
            total += value.doubleValue();
        }
        return total;
    }
}

public class GenericMethodDemo {
    public static void main(String[] args) {
        TextTools.showPair("Java", "17");
        TextTools.showPair(10, 20);

        String first = TextTools.first(List.of("alpha", "beta"));
        System.out.println(first);
        System.out.println(TextTools.sum(List.of(1, 2, 3)));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 GenericMethodDemo.java
java GenericMethodDemo
~~~

Output:

~~~text
Java | 17
10 | 20
alpha
6.0
~~~

The first call to showPair infers T as String; the second call infers T as Integer. Each invocation can infer a different type. For sum, the bound T extends Number allows calling doubleValue() safely because the compiler knows every valid T is Number or a subtype of Number.

## 4. When a Generic Class and a Generic Method Coexist

~~~java
final class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    void set(T value) {
        this.value = value;
    }

    <U> U echo(U input) {
        return input;
    }

    static <U> U identity(U input) {
        return input;
    }
}
~~~

**T** belongs to `Box<T>`; get() and set() use the box's type. **U** belongs to echo(), independent of the object's T. Therefore, `Box<String>` can store a String yet still call echo(42). The static method identity also declares its own U, so it does not depend on a specific `Box<T>`.

Conversely, a static member cannot directly use the class's T as if an instance defining T already existed. If you need a generic static method, declare its own type parameter, such as **`static <U> U identity(U input)`**.

## 5. Multiple Type Parameters and Bounds

A method can link multiple type parameters to preserve the relationship between input and output:

~~~java
static <S, T> T convert(S source, java.util.function.Function<S, T> converter) {
    return converter.apply(source);
}
~~~

Here S is the source type, and T is the result type. When passing a String and a function that converts it to Integer, the compiler can preserve that relationship in the signature. If the method only needs a type already known from the class, there is no need to redeclare a separate type parameter.

You can add bounds to a method:

~~~java
static <T extends Number> double asDouble(T value) {
    return value.doubleValue();
}
~~~

Without a bound, the compiler cannot allow calling doubleValue() on an arbitrary T. If there are multiple bounds, the syntax and class/interface ordering are explained in the lesson on type bounds and intersection types.

## 6. How Do Generic Methods Differ from Wildcards?

~~~java
static <T> T first(List<T> values) {
    return values.get(0);
}

static void printAll(List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
~~~

first uses a named T to link the element type to the return type: passing `List<String>` yields a String result. printAll only needs to iterate through the list without needing to know the element type, so List<?> expresses the intent more simply. Bounded wildcards such as ? extends Number are often useful when reading multiple numeric types; ? super Integer is suitable when you need to write Integer values into a list.

Use a named type parameter when multiple positions must share the same type or when the return type needs to preserve a relationship with the input. Use a wildcard when the specific element type does not matter for the operation being performed.

## 7. Common Mistakes

- **Forgetting to declare the type parameter:** in a non-generic class, T is valid only if the method declares `<T>` or another scope has already declared T.
- **Confusing a method that uses the class's T with a generic method:** T get() in `Box<T>` does not have its own type parameter.
- **Using the class's T in a static context:** a static method needs to declare its own type parameter to be generic.
- **Assuming all arguments in the same call can have arbitrarily different types:** positions using the same T must satisfy the same inference constraints.
- **Adding generics without creating a useful type relationship:** if a type parameter does not help link parameters, the result, or constrain behavior, a simpler signature may be clearer.

Type erasure also affects overloads that differ only in type arguments; that topic belongs to the lesson on name clash. This lesson focuses on type parameter scope, type inference, and how to preserve relationships between input and output.
