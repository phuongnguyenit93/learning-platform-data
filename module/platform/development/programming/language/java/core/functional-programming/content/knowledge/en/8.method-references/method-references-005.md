# The Receiver Object Becomes the First Parameter of the Functional Type

In Java, a method reference of the form `TypeName::instanceMethod` (an unbound instance method reference) lets you represent a call to an **instance** method without fixing the receiver object beforehand. When this reference is assigned to a functional interface, **the first parameter of the single abstract method (SAM)** is the receiver object. Any subsequent parameters are passed into the instance method's actual parameter list.

This is an essential rule when reading expressions like `String::length`, `String::startsWith`, `String::substring`, or `String::compareToIgnoreCase`. The `::` notation does not call the method by itself; it creates a value whose type is a contextually matching functional interface.

## 1. The receiver-first mapping rule

Suppose type `T` has an instance method:

~~~java
R method(P1 p1, P2 p2);
~~~

A functional interface with an equivalent SAM:

~~~java
R apply(T receiver, P1 p1, P2 p2);
~~~

can accept the reference `T::method`, provided the parameter types, return type, accessibility, and Java type-conversion rules are compatible. The meaning when invoked is:

~~~java
(receiver, p1, p2) -> receiver.method(p1, p2)
~~~

Note: `receiver` is **not** an extra parameter in `method`'s declaration. It is simply the first parameter of the SAM, used as the object on the left side of the dot when executed.

| Instance method | Target functional interface | Equivalent lambda | SAM call |
| --- | --- | --- | --- |
| `String.length()` | `ToIntFunction<String>` | `s -> s.length()` | `applyAsInt(s)` |
| `String.startsWith(String)` | `BiPredicate<String, String>` | `(s, prefix) -> s.startsWith(prefix)` | `test(s, prefix)` |
| `String.substring(int)` | `BiFunction<String, Integer, String>` | `(s, from) -> s.substring(from)` | `apply(s, from)` |
| `String.compareToIgnoreCase(String)` | `Comparator<String>` | `(a, b) -> a.compareToIgnoreCase(b)` | `compare(a, b)` |

In the table, `s`/`a` is the receiver object; `prefix`, `from`, and `b` are the declared arguments of the original method. Both `a` and `b` are `String`s, yet they have different roles in `Comparator.compare`.

## 2. Complete example on Java 17+

Save the following code to `UnboundMethodReferenceDemo.java`:

~~~java
import java.util.Comparator;
import java.util.function.BiFunction;
import java.util.function.BiPredicate;
import java.util.function.Function;
import java.util.function.ToIntFunction;

public class UnboundMethodReferenceDemo {
    static class Animal {
        String sound() {
            return "animal";
        }
    }

    static class Dog extends Animal {
        @Override
        String sound() {
            return "dog";
        }
    }

    @FunctionalInterface
    interface Slice {
        String apply(String text, int from, int to);
    }

    public static void main(String[] args) {
        ToIntFunction<String> length = String::length;
        BiPredicate<String, String> startsWith = String::startsWith;
        BiFunction<String, Integer, String> suffix = String::substring;
        Comparator<String> ignoringCase = String::compareToIgnoreCase;
        Slice slice = String::substring;
        Function<Animal, String> sound = Animal::sound;

        System.out.println(length.applyAsInt("Java"));
        System.out.println(startsWith.test("method reference", "method"));
        System.out.println(suffix.apply("functional", 4));
        System.out.println(ignoringCase.compare("java", "JAVA"));
        System.out.println(slice.apply("functional", 0, 4));
        System.out.println(sound.apply(new Dog()));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac UnboundMethodReferenceDemo.java
java UnboundMethodReferenceDemo
~~~

Exact output:

~~~text
4
true
tional
0
func
dog
~~~

Explanation of each call:

1. `length.applyAsInt("Java")` is equivalent to `"Java".length()`, so it returns `4`.
2. `startsWith.test("method reference", "method")` is equivalent to `"method reference".startsWith("method")`, so it is `true`.
3. `suffix.apply("functional", 4)` calls `"functional".substring(4)`. Indices start at 0, so the result is `"tional"`.
4. `ignoringCase.compare("java", "JAVA")` calls `"java".compareToIgnoreCase("JAVA")`, yielding `0`.
5. `slice.apply("functional", 0, 4)` calls the `substring(0, 4)` overload, returning `"func"` (start inclusive, end exclusive).
6. `sound.apply(new Dog())` uses `Animal::sound` while the actual object is `Dog`. The overridden method on `Dog` is dynamically dispatched, so it prints `dog`.

This example also shows that the receiver type can be a superclass or compatible interface, while the instance method is chosen at runtime based on the actual object type for dynamically dispatched methods.

## 3. Why does the SAM have more than one parameter?

Consider `String.startsWith(String prefix)`: by itself it has **one** parameter `prefix`. Yet the target type `BiPredicate<String, String>` has the SAM `boolean test(String first, String second)` with **two** parameters.

When you write:

~~~java
BiPredicate<String, String> check = String::startsWith;
boolean result = check.test("functional", "fun");
~~~

Java interprets it according to the equivalent lambda:

~~~java
BiPredicate<String, String> check =
        (receiver, prefix) -> receiver.startsWith(prefix);
~~~

`receiver` receives `"functional"`; `prefix` receives `"fun"`. No parameter is dropped, and Java does not create a `String` object on its own. The receiver value must be passed when the SAM is executed.

Similarly, if an instance method needs two actual arguments, the SAM will need **three** arguments: the receiver plus the two method arguments. Because `java.util.function` does not provide a built-in general three-parameter functional interface, you can declare a custom `@FunctionalInterface` like `Slice` in the example. `String::substring` is then mapped to the `substring(int beginIndex, int endIndex)` overload.

## 4. Distinguishing an unbound reference from a bound reference

Two similar-looking forms have different SAM signatures:

| Syntax | When is the receiver determined? | Target type example |
| --- | --- | --- |
| `TypeName::instanceMethod` | When calling the SAM, via the first argument | `Function<String, Integer> f = String::length;` |
| `object::instanceMethod` | When evaluating the reference expression | `Supplier<Integer> f = "Java"::length;` |

Illustrative example inside a Java method (with `Function` and `Supplier` imported):

~~~java
Function<String, Integer> unbound = String::length;
Supplier<Integer> bound = "Java"::length;

int x = unbound.apply("Hello"); // 5: receiver = "Hello"
int y = bound.get();            // 4: fixed receiver = "Java"
~~~

`unbound` requires the caller to pass a `String`; `bound` no longer requires a receiver parameter, because the `"Java"` object was already captured when creating the reference. If the variable used to create a bound reference were reassigned later (when code is valid under effectively final rules), the receiver already held by the reference would not change.

Additionally, `TypeName::staticMethod` is a reference to a `static` method: a static method **has no receiver** and does not take an extra first parameter. For example, `Function<Integer, String> f = String::valueOf;` is equivalent to `x -> String.valueOf(x)`. The syntax `TypeName::new` refers to a constructor. Therefore, always look at **the selected method and the target functional interface**, rather than mechanically guessing receiver-first from `::`.

## 5. How does the compiler choose the method and target type?

A method reference is a **poly expression**: the expression `String::substring` by itself has no concrete functional-interface type when standing alone. The target type from an assignment, a method call argument, a cast, or a return expression supplies the SAM signature for Java to check compatibility.

Steps to read an unbound reference:

1. Identify the functional interface required by the context and its SAM.
2. For an instance method, take the **first** parameter of the SAM as the receiver type, ensuring that type can be used to invoke the method.
3. Match the remaining SAM parameters with the instance method's parameters; resolve overloads, generic types, and valid conversions.
4. Check the method's return type against the SAM's return type; for a `void`-returning SAM, the call's return value can be discarded according to the appropriate compatibility rules.
5. When the SAM is invoked, evaluate the receiver and pass the arguments, then execute the method, including dynamic dispatch when applicable.

For example, the same `String::substring` in the program above selected two different overloads thanks to the SAM signature: `BiFunction<String, Integer, String>` selected `substring(int)`, whereas `Slice` selected `substring(int, int)`.

Java can perform automatic boxing/unboxing in valid cases: `BiFunction<String, Integer, String>` passes `Integer` to the `int` parameter of `substring(int)` via unboxing. If the receiver or argument types are incompatible, the method reference assignment does not compile; a method reference does not cast types arbitrarily.

## 6. Common mistakes and how to fix them

**Miscounting the functional interface's parameter count.**

~~~java
// Wrong: String::length still needs a receiver; Supplier.get() has no parameters.
java.util.function.Supplier<Integer> wrong = String::length;

// Right: the receiver is passed via Function.apply().
java.util.function.Function<String, Integer> ok = String::length;
~~~

If you want `Supplier<Integer>`, you must bind the receiver: `Supplier<Integer> fixed = "Java"::length;`. The `wrong` and `ok` lines are shown side-by-side for comparison; **do not compile the `wrong` line** in a real program.

**Swapping the receiver with a method argument.** `String::startsWith` with `BiPredicate<String, String>` is called via `test(text, prefix)`, not `test(prefix, text)`. Because both are `String`s, the compiler cannot catch this semantic bug.

**Assuming a receiver is already bound when creating an unbound reference.** `String::length` does not hold any string yet; the string value only appears in `apply` or `applyAsInt`.

**`null` receiver.** Creating `Function<String, Integer> f = String::length;` is valid even if `null` is passed later. Calling `f.apply(null)` will throw `NullPointerException` when attempting to call `length()` on a null object. Conversely, with `String s = null; Supplier<Integer> f = s::length;`, evaluating the bound reference throws `NullPointerException` immediately when creating the reference.

**Confusing static with instance or applying the wrong overload.** `String::valueOf` points to static methods, adding no receiver. With overloaded method names, let the SAM clearly express the parameter count and types; some overload contexts can be ambiguous and fail to compile.

**Forgetting accessibility and checked exceptions.** Method references must still obey access modifiers. If the referenced method declares checked exceptions, the functional interface's SAM must allow a compatible exception; common interfaces like `Function` do not declare checked exceptions on `apply`.

**Confusing reference creation with method execution.** `String::length` does not compute the length when assigned. The call only occurs when the SAM is executed; that is when the receiver is supplied and the result or exception is produced.

## 7. When should you use it?

Unbound references are especially useful when an API passes **the object to be processed** through a SAM parameter, such as with Streams:

~~~java
import java.util.List;

List<String> words = List.of("one", "three", "seven");
List<Integer> lengths = words.stream()
        .map(String::length)
        .toList();
// lengths = [3, 5, 5]
~~~

`Stream.map` expects `Function<? super String, ? extends Integer>`; each element is passed into the SAM as the receiver of `length()`. The code above is a snippet used inside a method and requires importing `java.util.List`.

Another example is case-insensitive sorting:

~~~java
List<String> names = new java.util.ArrayList<>(List.of("beta", "Alpha"));
names.sort(String::compareToIgnoreCase);
// names = [Alpha, beta]
~~~

`List.sort` expects `Comparator<String>` with two parameters; the first parameter is the string receiving `compareToIgnoreCase`, and the second parameter is the argument to that method.

Prefer `TypeName::instanceMethod` when the receiver-first mapping is clear, readable, and matches the SAM signature. When you need to transform arguments, check conditions, handle `null`, or express additional logic, an explicit lambda is usually easier to understand. Either way, the core rule remains: **the first parameter of the SAM supplies the receiver; the remaining parameters go into the instance method**.