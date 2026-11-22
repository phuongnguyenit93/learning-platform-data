# var with Diamond and Cases Where Java Infers Type Arguments as Object

## 1. The problem to understand

In Java Generics, two syntaxes often appear together:

- **var**: since Java 10, allows the compiler to infer the type **of a local variable** from its initializer expression.
- **Diamond operator (<>)**: since Java 7, allows omitting type arguments when creating a generic object; the compiler infers the type arguments based on existing constraints and context.

When writing:

~~~java
var items = new ArrayList<>();
~~~

many people assume items will automatically become a list of Strings after adding a string. In reality, since ArrayList<E> has no specific constraint on E in this statement, Java infers **E = Object**. The static type of items is **ArrayList<Object>**. Subsequent calls adding elements **do not cause Java to re-infer the type**.

Key point: **var infers from the initializer expression, while diamond must solve the generic parameter inference problem right when the object is created.** If both sides lack concrete type information, an unconstrained generic parameter is typically inferred as Object.

## 2. Distinguishing variable types from generic type arguments

Look at three declarations:

~~~java
List<String> first = new ArrayList<>();
var second = new ArrayList<String>();
var third = new ArrayList<>();
~~~

| Declaration | Variable's static type | ArrayList's type argument | Why? |
| --- | --- | --- | --- |
| first | List<String> | String | Left-hand side has target type List<String>, so diamond infers String. |
| second | ArrayList<String> | String | Right-hand side explicitly states String; var infers the initializer expression's type. |
| third | ArrayList<Object> | Object | var provides no specific target type for diamond, and the empty constructor does not constrain E. |

In the first declaration, the variable's type is **List<String>**, not ArrayList<String>, even though the created object is an ArrayList<String>. In the two declarations using var, the variable's static type matches the initializer expression's type **ArrayList<...>**, so ArrayList-specific methods can be called on it.

**var does not mean dynamic, Object, or any arbitrary type.** Once the compiler determines the type, the variable is still statically type-checked like any other Java declaration.

## 3. Why can var + diamond produce Object?

The following example is valid code:

~~~java
import java.util.ArrayList;

class Example {
    public static void main(String[] args) {
        var values = new ArrayList<>();
        values.add("Java");
        values.add(21);
    }
}
~~~

Inference mechanism of the declaration statement:

1. The compiler encounters the expression new ArrayList<>().
2. The no-arg constructor supplies no arguments to determine E.
3. With a var declaration, the left-hand side has no declared type such as List<String> to impose a String constraint on the initializer expression.
4. E of ArrayList<E> has no concrete constraint; the default upper bound is Object, so diamond is inferred as ArrayList<Object>.
5. var receives the static type ArrayList<Object>. Subsequent add calls are checked against the already-inferred type; they do not revise the decision made in step 4.

Because Object is a supertype of both String and Integer, both add calls above are valid. Nevertheless, this list **is not equivalent to List<String>** and cannot be used where a List<String> is required.

If a generic parameter has an upper bound other than Object, the default result can be affected by that bound. Therefore, do not turn "diamond always gives Object when paired with var" into an absolute rule: **Object is the typical outcome when a type parameter lacks specific information and its default upper bound is Object**.

## 4. Complete runnable example on Java 17+

Save the following snippet as **`VarDiamondDemo.java`**.

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;

public class VarDiamondDemo {
    public static void main(String[] args) {
        // No target type or argument constraining E:
        var mixed = new ArrayList<>(); // ArrayList<Object>
        mixed.add("Java");
        mixed.add(17);

        // Left-hand side provides target type:
        List<String> words = new ArrayList<>();
        words.add("Java");

        // When using var, specify generic type argument on the right:
        var explicit = new ArrayList<String>();
        explicit.add("Generics");

        // Constructor argument provides information to infer E:
        var inferred = new ArrayList<>(List.of("Java", "Kotlin"));
        inferred.add("Scala");

        // Both K and V lack specific constraints:
        var attributes = new HashMap<>(); // HashMap<Object, Object>
        attributes.put("version", 17);
        attributes.put(99, true);

        System.out.println("mixed = " + mixed);
        System.out.println("words = " + words);
        System.out.println("explicit = " + explicit);
        System.out.println("inferred = " + inferred);
        System.out.println("version = " + attributes.get("version"));
        System.out.println("key 99 = " + attributes.get(99));
    }
}
~~~

Compile and run:

~~~bash
javac VarDiamondDemo.java
java VarDiamondDemo
~~~

Exact output:

~~~text
mixed = [Java, 17]
words = [Java]
explicit = [Generics]
inferred = [Java, Kotlin, Scala]
version = 17
key 99 = true
~~~

In the **inferred** case, List.of("Java", "Kotlin") creates a List<String>, so the constructor argument enables ArrayList<E> to infer E as String right at initialization. Using var does not force type parameters to become Object; Java still leverages type information appearing **within the initializer expression itself**.

The following statements **intentionally cause compile errors** and do not belong to the runnable program above:

~~~java
var mixed = new ArrayList<>();  // ArrayList<Object>
List<String> wrong = mixed;     // Error: ArrayList<Object> cannot convert to List<String>

var inferred = new ArrayList<>(List.of("Java"));
inferred.add(42);              // Error: add requires String, does not accept int
~~~

In Java, generics are **invariant**: ArrayList<Object> is not a subtype of List<String>. Even though String is a subtype of Object, this relationship does not automatically extend to List<String> being a subtype of List<Object> or vice versa.

## 5. When a target type exists vs. when it does not

### 5.1. Left-hand side declares an explicit type

~~~java
List<String> names = new ArrayList<>();
~~~

The left-hand side supplies the **target type** List<String>. Diamond uses that information to infer the String type argument for ArrayList. This is usually the preferred style when you want to express the contract through the List interface.

### 5.2. var does not automatically create a String target type

~~~java
var names = new ArrayList<>(); // ArrayList<Object>
~~~

The var keyword itself tells the compiler to find the type from the initializer; it does not suggest String or Number. Calling names.add("Alice") afterwards does not turn names into ArrayList<String>.

### 5.3. Constructor arguments still help inference

~~~java
var names = new ArrayList<>(List.of("Alice", "Bob"));
// ArrayList<String>
~~~

The constructor ArrayList(Collection<? extends E>) receives a Collection of String elements, creating a constraint to infer E as String. The source of information comes from the constructor argument, not from later add calls.

Distinguish:

~~~java
var fixed = new ArrayList<>(List.of("Alice")); // ArrayList<String>
var empty = new ArrayList<>(List.of());        // ArrayList<Object>
~~~

List.of() has no elements, and here there is no additional information forcing the type parameter to be String. If the goal is an empty list of Strings, provide explicit type information.

### 5.4. Generic method calls can also infer Object

~~~java
var first = java.util.Collections.emptyList();            // List<Object>
List<String> second = java.util.Collections.emptyList();  // List<String>
var third = java.util.Collections.<String>emptyList();    // List<String>
~~~

On the second line, the target type List<String> helps the generic method infer String. On the third line, the **type witness** <String> directly specifies the method call's type parameter. This is a general generic inference phenomenon, not unique to constructors using diamond.

## 6. Ways to declare that match your intent

When you need an empty list of Strings, you can choose one of three ways:

~~~java
// Prefer interface type when only the List contract is needed:
List<String> a = new ArrayList<>();

// Want to use var while still keeping String:
var b = new ArrayList<String>();

// Want to keep diamond and have an argument carrying String info:
var c = new ArrayList<>(List.<String>of());
~~~

All of a, b, and c enforce that the element type is String. Here a has variable type List<String>; b and c have variable type ArrayList<String>. For c, the call List.<String>of() creates an empty List<String> so the constructor has a type constraint.

With an empty HashMap, the same issue applies across **two** type parameters:

~~~java
var unsafeForIntent = new java.util.HashMap<>(); // HashMap<Object, Object>
java.util.Map<String, Integer> byInterface = new java.util.HashMap<>();
var explicit = new java.util.HashMap<String, Integer>();
~~~

If you need Map<String, Integer>, choose byInterface or explicit. Initially calling put("level", 1) on unsafeForIntent **does not re-infer** String keys and Integer values.

Another approach is initializing from a typed source, for example:

~~~java
var copy = new ArrayList<>(List.of("A", "B")); // ArrayList<String>
~~~

Do not intentionally insert dummy elements just to force a type: if the list is required to be empty, declaring generic arguments explicitly is more readable and true to intent.

## 7. Real-world errors and how to spot them

### Error A: Discovering after initialization that it cannot be passed to an API

~~~java
import java.util.ArrayList;
import java.util.List;

class Service {
    static void saveNames(List<String> names) {
        // Process the names.
    }

    static void run() {
        var names = new ArrayList<>();
        names.add("Lan");
        // saveNames(names); // Compile error: names is ArrayList<Object>.
    }
}
~~~

**Cause:** saveNames's parameter requires List<String>, while names was inferred as ArrayList<Object> at declaration. **Fix:** use List<String> names = new ArrayList<>(); or var names = new ArrayList<String>(); from the start.

### Error B: Assuming diamond and var have the same job

~~~java
var numbers = new ArrayList<>();
numbers.add(10);
numbers.add("ten"); // Still valid because numbers is ArrayList<Object>.
~~~

var infers the **variable's** type; diamond infers the type arguments of the **created type**. The two mechanisms are related, not interchangeable. The compiler does not treat the first added element as the standard type for subsequent elements.

### Error C: Confusing List<Object>, raw List, and List<?>

~~~java
List<Object> objects = new ArrayList<>();
List raw = new ArrayList(); // Raw type: skips type argument checks, prone to warnings.
List<?> unknown = List.of("a", "b");
Object item = unknown.get(0);
// unknown.add("c");       // Error: exact element type of List<?> is unknown.
~~~

- **List<Object>**: has the concrete type argument Object; can accept objects of many subtypes.
- **Raw List**: uses generics while omitting type arguments; prone to unsafe operations and unchecked warnings.
- **List<?>**: a list with an unknown element type; can be read as Object, but cannot freely accept arbitrary elements (except null).

ArrayList<Object> inferred by var + diamond is a **generic type parameterized by Object**, not a raw ArrayList.

### Error D: Confusing type inference with runtime type checking

Java uses **type erasure** for most generic type argument information at runtime. The compiler still knows whether a variable is ArrayList<String> or ArrayList<Object> when checking add calls, assignments, and method parameters. Do not deduce that because type arguments cannot be read directly from an ArrayList object at runtime, var has dynamic typing.

### Error E: Thinking var is valid everywhere

var has usage conditions. For instance, a local variable using var must have an initializer to infer the type, and cannot be initialized with just null:

~~~java
// var data;       // Error: no initializer.
// var data = null; // Error: no concrete type to infer.
// var data = new ArrayList<>(); // Valid but infers ArrayList<Object>.
~~~

The commented statements in this example illustrate invalid syntax; they are not declarations meant to be executed.

## 8. Which style should you choose in real code?

- **Declare the type explicitly on the left** when you need a stable contract via an interface or when a short initializer might lose generic information: List<String> names = new ArrayList<>();.
- **Use var with explicit generic arguments on the right** if you want to highlight the concrete instantiation: var names = new ArrayList<String>();.
- **Use var and diamond together** when constructor input data or other constraints already provide the exact desired type, e.g., new ArrayList<>(List.of("A", "B"));.
- **Do not automatically assume Object** if concrete arguments or generic bounds are present; examine all constraints at the initializer.
- **Check the variable's inferred type immediately** in your IDE or by testing assignment to an expected type; do not rely solely on whether adding one element compiles.

In particular, a list created with List.of(...) is a **fixed-size unmodifiable** list; it differs from a new ArrayList created from List.of(...). Even though both may be inferred as List<String>/ArrayList<String>, only ArrayList in the example above permits add. This is a difference in collection behavior, not a difference in generic inference.

## 9. Self-check questions

**1.** var a = new ArrayList<>(); a.add("x"); what is the type of a?

**Answer:** ArrayList<Object>. The call add("x") does not change the inference result made at declaration.

**2.** Is var b = new ArrayList<>(List.of("x")); b.add(1); valid?

**Answer:** No. b is ArrayList<String> because the List.of("x") argument helps infer String; add(1) does not satisfy String.

**3.** What is the difference between List<String> c = new ArrayList<>(); and var c = new ArrayList<String>();?

**Answer:** Both hold String elements; in the first form the variable's static type is the interface List<String>, while in the second form it is the concrete class ArrayList<String>.

**4.** Why does var map = new HashMap<>(); not automatically get type HashMap<String, Integer> after calling put("x", 1)?

**Answer:** K and V are inferred at initialization, typically as Object when unconstrained; subsequent put calls do not re-infer them.

**Remember:** To give a generic type concrete type arguments, provide that information **right at the initialization statement** via a target type, explicitly written generic arguments, or arguments/return types with appropriate constraints. var eliminates type repetition, but cannot guess intent that has not appeared in the expression.
