# Type Checking in Java

## Objectives

After this lesson, you will be able to explain how the compiler checks data types at compile time; distinguish a variable's static type from an object's runtime class; understand assignment, type conversion, overloading, generics, and type inference; recognize whether an error is detected at compile time or runtime; and read `javac` diagnostics and warnings to fix errors safely.

## 1. What is type checking?

**Type checking** is the process of verifying that values, expressions, variables, parameters, and method calls are used according to Java's type rules.

Java is a **statically typed** language: most type information is determined and checked at compile time. The compiler needs to know the type of expressions to decide:

- Whether a value can be assigned to a variable.
- Whether an argument is compatible with a method/constructor parameter type.
- Which method or constructor overload can be called.
- Whether an operation is valid for its operands.
- Which generic types are inferred and whether they are compatible with each other.
- Whether a cast can be accepted at compile time or requires an additional runtime check.

Example:

~~~java
int age = 20;
String name = "An";

age = name;
~~~

The last line causes a compile-time error because `String` cannot be assigned directly to an `int` variable. The compiler catches the problem before the program runs.

Conversely:

~~~java
String name = null;
System.out.println(name.length());
~~~

This code is type-valid, so the compiler allows compilation. However, at runtime, calling `length()` on `null` causes a `NullPointerException`. Type checking does not prove that every runtime value is valid; it verifies the type rules that the language can check statically.

## 2. Where does type checking sit in the compilation pipeline?

A high-level view of the Java compilation process:

~~~text
Java source (.java)
       |
       v
Lexical analysis / parsing
       |
       v
Enter symbols and resolve declarations
       |
       v
Annotation processing (if any)
       |
       v
Attribution / type checking
       |
       v
Flow analysis
       |
       v
Desugaring and code generation
       |
       v
Bytecode (.class)
~~~

Steps may be interleaved or repeated by `javac` as needed for annotation processing and dependencies. The diagram describes conceptual roles, not an internal ordering contract for every compiler.

- **Parsing:** checks tokens and syntactic structure. For example, a missing semicolon or closing parenthesis is a syntax error.
- **Enter symbols:** records classes, interfaces, methods, fields, type parameters, and declarations so the compiler can look them up.
- **Attribution/type checking:** determines expression types, looks up members, selects overloads, infers generics, and checks conversions.
- **Flow analysis:** checks conditions such as definite assignment, whether a variable is initialized before being read, and certain control-flow rules.
- **Code generation:** produces bytecode once the required checks succeed.

A type-checking error is usually reported by `javac` with line/column locations and expected/actual type information. When the compiler reports `incompatible types`, `no suitable method found`, or `reference to ... is ambiguous`, treat it as a type-rule or method-selection issue rather than a simple syntax error.

## 3. Static type and runtime type

Every Java variable and expression has a **static type** that the compiler uses to check the code. An object has a **runtime class** corresponding to the class that created that object.

Example:

~~~java
class Animal {
    void speak() {
        System.out.println("Animal sound");
    }
}

class Dog extends Animal {
    @Override
    void speak() {
        System.out.println("Woof");
    }

    void fetch() {
        System.out.println("Fetching");
    }
}

public class TypeExample {
    public static void main(String[] args) {
        Animal pet = new Dog();

        pet.speak();
        // pet.fetch(); // Compile-time error
    }
}
~~~

The variable `pet` has static type `Animal`, while the object it references has runtime class `Dog`.

- The compiler only allows calling members accessible through the `Animal` type. Therefore `pet.fetch()` is invalid: `Animal` does not declare `fetch()`.
- For overridden instance methods, the JVM selects the implementation based on the object's runtime class. Hence `pet.speak()` runs `Dog.speak()` and prints `Woof`.

This is the difference between **overload resolution** and **dynamic dispatch**: overloads are chosen at compile time based on static types; the implementation of the chosen method can be dispatched at runtime based on the actual object.

To call behavior specific to `Dog`, you need to check or cast:

~~~java
if (pet instanceof Dog dog) {
    dog.fetch();
}
~~~

The pattern variable `dog` can only be used in the scope where the compiler determines the `instanceof` condition succeeded. Pattern matching for `instanceof` has been a standard feature since Java 16.

## 4. Assignment checking and type compatibility

For an assignment, the type of the right-hand expression must have a valid conversion to the type of the left-hand variable. Java calls this **assignment conversion**.

### Same-type assignment

~~~java
int count = 10;
int anotherCount = count;
~~~

Both sides have the same type, so the assignment is valid.

### Widening primitive conversion

Some smaller primitive types can be converted to wider types without a cast:

~~~java
int count = 10;
long total = count;
double average = total;
~~~

Conversions such as `int` to `long`, `long` to `double`, and `float` to `double` are called widening primitive conversions. However, widening does not guarantee that every value is represented exactly: `long` to `float` can lose precision because `float` has fewer significand bits.

### Narrowing primitive conversion

Converting from a wider type to a narrower type usually requires an explicit cast:

~~~java
double price = 19.95;
int wholePrice = (int) price;

System.out.println(wholePrice);
~~~

Output:

~~~text
19
~~~

The fractional part is discarded. A cast only tells the compiler to allow the conversion; it does not guarantee that data is preserved.

### Integer constant expressions can be narrowed in certain assignments

Java allows a constant expression of type `int` to be assigned to `byte`, `short`, or `char` if the value fits within the target type's range:

~~~java
byte first = 10;
byte second = 1 + 2;
~~~

However, the following example is invalid:

~~~java
byte first = 10;
byte second = first + 1; // Compile-time error
~~~

The expression `first + 1` has type `int` due to binary numeric promotion. The variable `first` is not a constant variable, so the compiler cannot apply the narrowing exception for constant expressions. You can write:

~~~java
byte second = (byte) (first + 1);
~~~

Or use compound assignment:

~~~java
first += 1;
~~~

Compound assignment includes an implicit conversion rule to the left-hand type. This is convenient, though it can still lose data if the operation exceeds the representable range of `byte`.

### Widening and narrowing reference conversion

If `Dog` extends `Animal`, you can assign a `Dog` to an `Animal`:

~~~java
Dog dog = new Dog();
Animal animal = dog;
~~~

This is a widening reference conversion, which is generally safe because every `Dog` is an `Animal`.

The reverse direction requires checking:

~~~java
Animal animal = new Dog();
Dog dog = (Dog) animal;
~~~

The cast succeeds when the actual object is a `Dog`. If the actual object is another kind of `Animal`, the JVM throws `ClassCastException`.

## 5. Boxing, unboxing, and null

Java can convert between primitive types and wrapper types:

| Primitive | Wrapper |
|---|---|
| boolean | Boolean |
| byte | Byte |
| short | Short |
| char | Character |
| int | Integer |
| long | Long |
| float | Float |
| double | Double |

**Boxing** converts a primitive into a wrapper:

~~~java
int count = 5;
Integer boxed = count;
~~~

**Unboxing** converts a wrapper into a primitive:

~~~java
Integer boxed = 5;
int count = boxed;
~~~

The compiler automatically inserts these conversions in contexts permitted by Java. They can be convenient, but they are not always free in performance or risk-free.

Example:

~~~java
Integer value = null;
int count = value;
~~~

The code above compiles, but throws a `NullPointerException` during unboxing because `null` cannot become an `int` value. When using a nullable wrapper, check for `null` before converting to a primitive.

## 6. Type checking in method and constructor calls

The compiler must determine whether arguments are compatible with parameter types. This is called **invocation conversion**.

Example:

~~~java
static void printLength(String text) {
    System.out.println(text.length());
}

printLength("Java"); // Valid
printLength(123);    // Compile-time error
~~~

An argument can be converted in permitted contexts, such as widening primitive, widening reference, boxing, or unboxing. Not every conversion is automatically accepted in every position.

### Overload resolution

If multiple methods share the same name, the compiler picks the most suitable overload based on the static types of the arguments and overload resolution rules.

~~~java
public class OverloadDemo {
    static void show(Object value) {
        System.out.println("Object overload");
    }

    static void show(String value) {
        System.out.println("String overload");
    }

    public static void main(String[] args) {
        show("Java");
    }
}
~~~

Output:

~~~text
String overload
~~~

`String` is a more specific type than `Object` in this case, so the overload taking `String` is chosen.

### Overloads can be ambiguous

~~~java
static void show(String value) { }
static void show(Integer value) { }

show(null); // Compile-time error: ambiguous
~~~

`null` can be assigned to both `String` and `Integer`. Neither type is a subtype of the other, so the compiler has no single more specific overload to choose.

If you also declare an overload taking `Object`, does `show(null)` pick the `String` or `Integer` overload? Neither is more specific than the other; `Object` is less specific than both, so it does not resolve the ambiguity.

You can clarify your intent with a cast:

~~~java
show((String) null);
~~~

### Overloading vs. overriding

- **Overload:** same method name with different parameter lists. The compiler decides which method signature is called based on static types.
- **Override:** a subclass replaces the implementation of an inherited method. For instance methods, the JVM dispatches to the appropriate implementation based on the runtime class.

Example:

~~~java
class Parent {
    void display(Object value) {
        System.out.println("Parent Object");
    }
}

class Child extends Parent {
    @Override
    void display(Object value) {
        System.out.println("Child Object");
    }

    void display(String value) {
        System.out.println("Child String");
    }
}

Parent ref = new Child();
ref.display("Java");
~~~

Output:

~~~text
Child Object
~~~

The compiler sees the static type `Parent`, so only the `display(Object)` overload is eligible to be selected. The JVM then invokes the overridden implementation in `Child`. `Child`'s `display(String)` overload does not participate because it does not exist on the static type `Parent`.

## 7. Generic type checking

Generics let the compiler check element types of collections and generic classes/methods at compile time.

~~~java
List<String> names = new ArrayList<>();
names.add("An");
names.add("Binh");

String first = names.get(0);
~~~

The compiler knows `names` only accepts `String` and `get(0)` returns `String`. The following statement is rejected:

~~~java
names.add(100); // Compile-time error
~~~

If you use a raw type:

~~~java
List raw = new ArrayList();
raw.add("Java");
raw.add(100);

List<String> names = raw; // Unchecked conversion warning
String value = names.get(1); // May throw ClassCastException
~~~

Raw types weaken generic type checking. The compiler emits an unchecked warning because it cannot prove the data in the collection is actually of type `String`. When reading the `Integer` element and casting it to `String`, an error can occur at runtime.

### Generic invariance

`List<String>` is not a subtype of `List<Object>`, even though `String` is a subtype of `Object`:

~~~java
List<String> strings = new ArrayList<>();
List<Object> objects = strings; // Compile-time error
~~~

If that assignment were allowed, code could add an `Integer` to a list originally declared as `List<String>`. Later, other code reading elements and expecting `String` would fail.

To represent a collection that can hold subtypes of `Number`, use a wildcard:

~~~java
List<? extends Number> values;
~~~

This is a producer type: you can read elements as `Number`, but you cannot add an arbitrary `Number` because the compiler does not know the exact subtype being held.

With:

~~~java
List<? super Integer> values;
~~~

This is a consumer type: you can add `Integer`, but when reading an element, the only common safe type is `Object`.

A common mnemonic is PECS: Producer Extends, Consumer Super. This is a guideline for designing generic APIs, not a replacement for the full type rules.

### Type erasure

Java implements generics via type erasure: most type argument information does not exist as a distinct runtime type after compilation. The compiler checks generics at compile time and inserts necessary casts into the bytecode.

Therefore, you cannot write:

~~~java
if (value instanceof List<String>) {
    // Compile-time error
}
~~~

The JVM cannot directly check the `String` type argument of `List` at runtime. You can check:

~~~java
if (value instanceof List<?>) {
    // Checks whether the object is a List
}
~~~

If you need to guard element types, you must check each element individually or use a data mechanism with an appropriate schema.

## 8. Type inference and target typing

The compiler can infer types in certain contexts instead of requiring the programmer to write out full type arguments.

### Generic method type inference

~~~java
static <T> T identity(T value) {
    return value;
}

String name = identity("An");
Integer count = identity(10);
~~~

From the arguments and usage context, the compiler infers `T` as `String` and `Integer`, respectively.

You can specify the type argument explicitly:

~~~java
String name = TypeInferenceDemo.<String>identity("An");
~~~

Usually, writing it explicitly is unnecessary if the compiler has enough information.

### Diamond operator

~~~java
List<String> names = new ArrayList<>();
~~~

The compiler infers the type argument of `ArrayList` from the target type `List<String>`. This is an example of target typing.

### Lambda expressions require a target type

~~~java
Runnable task = () -> System.out.println("Running");
~~~

A lambda does not stand alone as an object of an arbitrary type. The compiler needs a target type that is a functional interface—here, `Runnable`—to check the lambda's parameters and return type.

The following example lacks a sufficient target type:

~~~java
var task = () -> System.out.println("Running"); // Compile-time error
~~~

You cannot use `var` to infer the type of a lambda without a target functional interface. Write instead:

~~~java
Runnable task = () -> System.out.println("Running");
~~~

Type inference makes code more concise, but the compiler still determines a concrete static type; Java does not turn into a dynamically typed language.

## 9. Casts, `instanceof`, and runtime checks

An explicit cast asks the compiler to consider a conversion that normal assignment does not allow. For reference types, some casts require checking the actual object at runtime.

~~~java
Object value = "Java";
String text = (String) value;
~~~

This cast is valid and succeeds because the actual object is a `String`.

~~~java
Object value = 123;
String text = (String) value;
~~~

This example compiles because the compiler cannot rule out the possibility that `value` holds a `String`, but at runtime it throws `ClassCastException` because the actual object is an `Integer`.

Use `instanceof` to check before casting:

~~~java
if (value instanceof String text) {
    System.out.println(text.toUpperCase());
} else {
    System.out.println("Not a String");
}
~~~

For reference types, `instanceof` returns `false` when `value` is `null`. The pattern variable `text` is only in scope in the branch where the check succeeds.

Do not use casts to paper over type-design flaws. If an API frequently requires many casts, consider using interfaces, generic types, or a clearer data model.

## 10. Expression types and target typing

The type of an expression is not always determined solely by its operands. In some cases, a **target type** from the surrounding context helps determine the expression's type. Expressions influenced in this way are called poly expressions.

Example:

~~~java
List<String> names = new ArrayList<>();
~~~

The target type `List<String>` helps the compiler infer the type argument of the `new ArrayList<>()` expression.

With a conditional expression:

~~~java
String result = condition ? "yes" : "no";
~~~

Both branches are `String`, so the expression has type `String`.

With lambdas or method references, the target functional interface determines the parameter types and result type to be checked. This is why a lambda can fit one context while being invalid on its own.

When encountering type inference or `incompatible types` errors in a compound expression, split the expression into variables with explicit types to clarify the target type and narrow down the error location.

## 11. Compile-time errors, warnings, and runtime exceptions

| Kind | Example | When detected |
|---|---|---|
| Syntax error | Missing parenthesis or semicolon | Parsing |
| Type error | Assigning `String` to `int`, calling a nonexistent method | Compile time |
| Unchecked warning | Raw type, unchecked cast/conversion | Compile time |
| `ClassCastException` | Casting an incompatible runtime object | Runtime |
| `NullPointerException` | Dereferencing or unboxing `null` | Runtime |
| `ArrayStoreException` | Assigning an object of the wrong runtime component type to a covariant array | Runtime |

Take unchecked warnings seriously. A warning indicates that the compiler cannot fully verify type safety. Adding `@SuppressWarnings("unchecked")` only hides the message; it does not make the cast or collection safe by itself.

## 12. Reading and improving `javac` diagnostics

Suppose we have `TypeError.java`:

~~~java
public class TypeError {
    public static void main(String[] args) {
        int count = "five";
    }
}
~~~

Compile:

~~~bash
javac TypeError.java
~~~

The compiler reports an error because `String` cannot be converted to `int`. The exact diagnostic text may vary across JDK versions, but the underlying error remains the same.

Useful options:

| Option | Effect |
|---|---|
| `-Xlint:all` | Enables many compiler warning categories |
| `-Xlint:unchecked` | Shows warnings related to generics/unchecked conversions |
| `-Xdiags:verbose` | Requests more detailed diagnostics |
| `-Werror` | Treats warnings as compilation errors |
| `--release 17` | Compiles against Java 17 language, APIs, and bytecode |

Example checking a program against Java 17:

~~~bash
javac --release 17 -Xlint:all -Xdiags:verbose -d out TypeCheckingDemo.java
~~~

If a project wants the build to fail when warnings appear:

~~~bash
javac --release 17 -Xlint:all -Werror -d out TypeCheckingDemo.java
~~~

Avoid enabling `-Werror` on a legacy codebase without reviewing warnings first, as pre-existing warnings can break the current build. In a new project, controlling warnings from the start helps maintain stronger type safety.

## 13. Complete runnable example

Create `TypeCheckingDemo.java`:

~~~java
public class TypeCheckingDemo {
    static <T> T identity(T value) {
        return value;
    }

    static void select(Object value) {
        System.out.println("Object overload");
    }

    static void select(String value) {
        System.out.println("String overload: " + value);
    }

    private static final class User {
        private final String name;

        User(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }
    }

    public static void main(String[] args) {
        int count = 7;
        long total = count;

        Integer boxed = count;
        int unboxed = boxed;

        System.out.println("widened=" + total);
        System.out.println("boxed=" + boxed + ", unboxed=" + unboxed);

        select("Java");

        Object candidate = new User("Mina");
        if (candidate instanceof User user) {
            System.out.println("user=" + user.name());
        }

        String text = identity("Java");
        System.out.println("inferred=" + text);
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 -Xlint:all -d out TypeCheckingDemo.java
java -cp out TypeCheckingDemo
~~~

Exact output:

~~~text
widened=7
boxed=7, unboxed=7
String overload: Java
user=Mina
inferred=Java
~~~

In this example:

- `int` is widened to `long`.
- `int` is boxed to `Integer` and then unboxed back to `int`.
- The compiler selects the overload taking `String`.
- The variable `candidate` has static type `Object`, while the actual object is `User`; `instanceof` checks the runtime class and binds the pattern variable `user`.
- The generic method `identity` infers `T` as `String` from the argument and target type.

## 14. Workflow for resolving a type-checking error

When `javac` reports a type error:

1. Read the reported line and column, but also inspect surrounding expressions because the error may originate from an earlier method call.
2. Write down the static type of each variable and expression involved.
3. Identify the context: assignment, method invocation, return, cast, numeric operation, or lambda target typing.
4. Check whether the conversion is permitted by Java in that context.
5. For overloads, list the candidate methods and their parameter types; determine why a candidate is not applicable or why multiple candidates match.
6. For generics, check type arguments, wildcards, raw types, and constraints the compiler must infer.
7. For runtime errors like `ClassCastException` or `NullPointerException`, inspect the runtime class/value and do not confuse them with compile-time type errors.
8. Fix the root cause in the declared types, API, or data; only use a cast when you have a sound guarantee of the actual runtime type.

A helpful technique is to introduce an intermediate variable with an explicit type:

~~~java
var result = complicatedExpression();
~~~

You can temporarily replace it with:

~~~java
String result = complicatedExpression();
~~~

If the compiler reports an error on the assignment, you have identified the expected target type and can trace back to the expression producing the incompatible type.

## 15. Type safety checklist

- [ ] Variables and expressions have static types appropriate for their intended use.
- [ ] Assignments only use valid conversions.
- [ ] Primitive or reference casts are not used arbitrarily.
- [ ] Null checks are performed before dereferencing or unboxing when needed.
- [ ] Overloads are selected based on static types as expected.
- [ ] Overload resolution is clearly distinguished from runtime method dispatch.
- [ ] Generics are used instead of raw types whenever possible.
- [ ] Unchecked warnings are addressed rather than merely suppressed.
- [ ] Lambdas and method references have a clear target functional interface.
- [ ] Runtime casts are guarded with `instanceof` where appropriate.
- [ ] The compiler is run with the project's correct `--release` or toolchain.
- [ ] Full diagnostics are read and the root cause is fixed.

## 16. Official references

- [Java Language Specification, Java SE 26 — Chapter 4: Types, Values, and Variables](https://docs.oracle.com/javase/specs/jls/se26/html/jls-4.html) — primitive/reference types, subtypes, generics, erasure, and type usage.
- [Java Language Specification, Java SE 26 — Chapter 5: Conversions and Contexts](https://docs.oracle.com/javase/specs/jls/se26/html/jls-5.html) — widening/narrowing, assignment, invocation, casting, boxing/unboxing, and target typing.
- [Java Language Specification, Java SE 26 — §15.12: Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se26/html/jls-15.html#jls-15.12) — overload resolution and method invocation.
- [Java Language Specification, Java SE 26 — Chapter 18: Type Inference](https://docs.oracle.com/javase/specs/jls/se26/html/jls-18.html) — generic type inference and constraints.
- [javac — Java SE 26 Tool Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html) — compiler options, lint, and release target.

Type checking is an important layer of protection in Java: it catches many errors before the program runs, while helping APIs and code express expected data types clearly. Once you understand static types, conversion contexts, and overload resolution, you can read diagnostics faster and design safer code.
