# `getClass()` and Distinguishing the Actual Class from the Declared Type in Java

One of the core ideas of Java is that **a reference variable has a type known by the compiler**, whereas **the object the variable points to has an actual class at runtime**. Those two pieces of information are related, yet **not necessarily the same**.

Example:

~~~java
Object value = "Java";
~~~

Here, the declared type of `value` is `Object`, but the actual object is a `String`. Therefore, `value.getClass()` returns the `Class` object describing **`java.lang.String`**, not `java.lang.Object`.

The `getClass()` method is declared in `java.lang.Object`:

~~~java
public final native Class<?> getClass();
~~~

This is an **illustrative API signature** of the method, not a method body that we implement ourselves. `final` means subclasses **cannot override** `getClass()`. Every regular Java instance inherits the ability to retrieve runtime class information from `Object`, and the JVM returns the `Class` corresponding to the object receiving the call.

This lesson belongs to Java Core — **class-object**, the **Object Class** section. We will learn the mechanics of static and dynamic types, their relationship with polymorphism, `Class` literals, `instanceof`, reflection, interfaces, arrays, generic type erasure, `null`, class comparison rules, and pitfalls when using `getClass()` in `equals()` or library design. The standalone programs use **Java 17+**, accompanied by run commands and deterministic stdout.

## 1. Two concepts that must be separated

Consider:

~~~java
Animal animal = new Dog();
~~~

This is an **illustrative statement** assuming `Dog extends Animal`, and that both types are accessible.

- The **declared/static type** of the variable `animal` is `Animal`. The compiler uses this information to check whether expressions such as `animal.eat()` are valid, and to select the appropriate method signature.
- The **actual class (runtime class)** of the object is `Dog`, because the expression `new Dog()` creates an object of class `Dog`.
- `animal.getClass()` returns `Dog.class`, not `Animal.class`.
- For an overridable instance method, a call through `animal` can dispatch to `Dog`'s implementation.

There are no “two objects” in this example. There is only **one Dog object**, held via a variable of type Animal.

Because Java allows **upcasting** from a subclass to a superclass/interface, having the two types differ is normal, not some kind of data error.

## 2. Complete program 1 — variable type and object class

Create the file **`RuntimeClassDemo.java`**:

~~~java
class Vehicle {
    String kind() {
        return "vehicle";
    }
}

class Bicycle extends Vehicle {
    @Override
    String kind() {
        return "bicycle";
    }

    void ringBell() {
        System.out.println("ring");
    }
}

public class RuntimeClassDemo {
    public static void main(String[] args) {
        Vehicle vehicle = new Bicycle();

        System.out.println("declared=Vehicle");
        System.out.println("actual="
                + vehicle.getClass().getSimpleName());
        System.out.println("name="
                + vehicle.getClass().getName());
        System.out.println("literal="
                + Vehicle.class.getSimpleName());
        System.out.println("same Vehicle="
                + (vehicle.getClass() == Vehicle.class));
        System.out.println("same Bicycle="
                + (vehicle.getClass() == Bicycle.class));
        System.out.println("kind=" + vehicle.kind());
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac -encoding UTF-8 RuntimeClassDemo.java
java RuntimeClassDemo
~~~

**Exact stdout:**

~~~text
declared=Vehicle
actual=Bicycle
name=Bicycle
literal=Vehicle
same Vehicle=false
same Bicycle=true
kind=bicycle
~~~

### Analysis

- `declared=Vehicle` is a line we intentionally print to illustrate **the declared type in source**. `getClass()` has no function to “read back the declared type of a variable”.
- `vehicle.getClass().getSimpleName()` returns the simple name `Bicycle`.
- `getName()` returns `Bicycle` here because the class is in the **unnamed package** and is not a nested class. With a named package, the result will be the appropriate full binary name.
- `Vehicle.class` describes **the Vehicle type itself**, not the object that the `vehicle` variable is holding.
- `kind()` is an overridden instance method, so at runtime `Bicycle.kind()` is called even though the variable is declared as type `Vehicle`.

If you want to call `vehicle.ringBell()` directly, the compiler will reject it because the API of type `Vehicle` does not declare that method. You can check the dynamic type with `instanceof` and use a **pattern variable** or a safe cast.

## 3. Reference type determines the API visible at compile time

Try the following lines:

~~~java
Vehicle vehicle = new Bicycle();
vehicle.kind();       // Valid.
vehicle.getClass();   // Valid: Object.getClass().
~~~

But:

~~~java
// vehicle.ringBell(); // Invalid for the declared type Vehicle.
~~~

`ringBell()` is a method specific to `Bicycle`; the fact that the actual object has this method **does not cause the compiler to automatically add** it to the API of a `Vehicle` variable.

The safe approach in Java 17:

~~~java
if (vehicle instanceof Bicycle bike) {
    bike.ringBell();
}
~~~

This is an **illustrative snippet** placed where `vehicle` has type `Vehicle` and an appropriate `Bicycle` definition exists. `instanceof Bicycle bike` checks the object at runtime and, when true, creates a pattern variable `bike` of type `Bicycle` within the valid scope.

If the program only needs to call the common behavior `kind()`, you should not downcast to the subclass unnecessarily. The value of polymorphism is writing algorithms against a **superclass/interface contract** rather than frequently inspecting concrete classes.

## 4. `getClass()` returns a `Class` object, not a string

The result of `getClass()` is a `java.lang.Class` object, not a `String`. To get the name, call methods on `Class`.

~~~java
Class<?> type = value.getClass();
String name = type.getName();
String simple = type.getSimpleName();
~~~

These are **illustrative statements**, assuming `value` is a non-null reference. `Class<?> ` is a common way to hold a class token when a specific generic type bound is not yet needed.

Basic operations:

| Expression | Type of information | Example for `String.class` |
| --- | --- | --- |
| `getClass()` | `Class` of the runtime object | `String.class` |
| `String.class` | Class literal of the type stated in source | `String.class` |
| `getName()` | Binary name/JVM name format depending on the kind of type | `java.lang.String` |
| `getSimpleName()` | Short name according to the API | `String` |
| `getCanonicalName()` | Canonical name if available | `java.lang.String` |
| `getPackageName()` | Package name according to the API | `java.lang` |
| `isInterface()` | Is it an interface? | `false` |
| `isArray()` | Is it an array class? | `false` |
| `getSuperclass()` | `Class` of the direct superclass if any | `Object.class` |

**Not every class has a canonical name.** Anonymous classes and local classes can return `null` when calling `getCanonicalName()`. Therefore, avoid writing code that assumes `getCanonicalName()` is always a non-null string.

## 5. Is a `Class` object unique for a runtime class?

For a specific runtime class definition, references to the same class object can be compared using `==`. For example, `new String("x").getClass() == String.class` is `true`.

~~~java
Class<?> first = "hello".getClass();
Class<?> second = String.class;
boolean same = first == second;
~~~

The result `same` is `true` because both point to the `Class` object representing **the same runtime class**.

However, the JVM identifies a class not only by its binary name; the **defining class loader** is also part of its identity. In a plugin architecture or application server, two classes with the **same binary name** but defined by **two different class loaders** can be two separate runtime classes, having different `Class` objects.

Therefore:

- `typeA == typeB` checks whether they describe **the same runtime type**.
- `typeA.getName().equals(typeB.getName())` only compares **string names**; the two runtime types are not necessarily the same.
- `getClass()` is not used to discover “which line in the source code the object was declared on”.

In typical application code without custom class loaders, this difference rarely surfaces, but it is very important when debugging a puzzling `ClassCastException` in plugin systems.

## 6. Complete program 2 — an `Object` variable holding multiple types

Create the file **`ObjectRuntimeTypesDemo.java`**:

~~~java
public class ObjectRuntimeTypesDemo {
    private static void inspect(Object value) {
        System.out.println("actual="
                + value.getClass().getSimpleName());
    }

    public static void main(String[] args) {
        Object text = "Java";
        Object number = Integer.valueOf(42);
        Object flag = Boolean.TRUE;

        inspect(text);
        inspect(number);
        inspect(flag);

        System.out.println("text is String="
                + (text instanceof String));
        System.out.println("number is Number="
                + (number instanceof Number));
        System.out.println("text is Object="
                + (text instanceof Object));
        System.out.println("exact Integer="
                + (number.getClass() == Integer.class));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ObjectRuntimeTypesDemo.java
java ObjectRuntimeTypesDemo
~~~

**Stdout:**

~~~text
actual=String
actual=Integer
actual=Boolean
text is String=true
number is Number=true
text is Object=true
exact Integer=true
~~~

The `inspect(Object)` method accepts a general reference, so the same source method can handle different objects. `getClass()` accurately observes the runtime class of each object.

`number instanceof Number` returns true even though `number.getClass() == Number.class` would be false, because **Integer extends Number**, whereas `getClass()` reports the **exact** type of the object.

This is the key difference when choosing between `getClass() == SomeType.class` and `instanceof SomeType`.

## 7. `getClass() == Type.class` differs from `instanceof Type`

The syntax:

~~~java
object.getClass() == Parent.class
~~~

is true only when the object's runtime class **is exactly `Parent`**. It does not accept an object of a subclass.

Whereas:

~~~java
object instanceof Parent
~~~

is true when the runtime object is **type-compatible with `Parent`** according to the checked type relationship, including objects of a subclass. For interfaces, `instanceof Interface` can also be true when the object implements that interface.

| Object state | `getClass() == Parent.class` | `instanceof Parent` |
| --- | ---: | ---: |
| Direct object `new Parent()` | true | true |
| Object `new Child()` where `Child extends Parent` | false | true |
| `null` object | **Throws NPE if `getClass()` is called** | false |
| Object of another, unrelated type | false (if the reference is non-null) | false |

**Choice:** when you need **an exact class**, compare class tokens; when you need **a type family/implementations of a contract**, prefer `instanceof`/polymorphism.

Additionally, choosing to use an exact class test in the middle of a polymorphic API can accidentally exclude valid subclasses; you should not use `getClass()` to replace every `instanceof` in code.

## 8. Complete program 3 — exact class and inheritance

Create the file **`ExactClassVersusInstanceofDemo.java`**:

~~~java
class Document {
}

class PdfDocument extends Document {
}

public class ExactClassVersusInstanceofDemo {
    static void check(Document document) {
        System.out.println(
                "actual=" + document.getClass().getSimpleName()
                + ", exactDocument="
                + (document.getClass() == Document.class)
                + ", isDocument="
                + (document instanceof Document)
                + ", isPdf="
                + (document instanceof PdfDocument));
    }

    public static void main(String[] args) {
        check(new Document());
        check(new PdfDocument());

        Document none = null;
        System.out.println("null instanceof="
                + (none instanceof Document));
        System.out.println("null test=" + (none == null));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ExactClassVersusInstanceofDemo.java
java ExactClassVersusInstanceofDemo
~~~

**Stdout:**

~~~text
actual=Document, exactDocument=true, isDocument=true, isPdf=false
actual=PdfDocument, exactDocument=false, isDocument=true, isPdf=true
null instanceof=false
null test=true
~~~

Analysis:

1. A direct `Document` object has the exact class `Document`.
2. A `PdfDocument` object is still a `Document` under the inheritance relationship, but its class is not equal to `Document.class`.
3. `null instanceof Document` is always false; this is **not** a way to distinguish subclasses.
4. Do not call `document.getClass()` if `document` may be null without a guard. The program only calls `check` with non-null objects.

From a design perspective, if `check` only needs to see whether an object is a Document, use the `Document` API instead of querying the actual class. An exact class check is suited for specific purposes, not as the default for every algorithm.

## 9. Why is `getClass()` `final`?

`Object.getClass()` is `final`; subclasses are not allowed to alter how an object reports its own runtime class. Therefore:

~~~java
class Example {
    // @Override
    // public Class<?> getClass() { return Object.class; }
    // Intentionally invalid: Object.getClass() is final.
}
~~~

This is an **illustrative snippet**; the commented lines are an intentionally non-compiling example if enabled. If a framework wants to expose a logical type or domain type different from the implementation class, it must use **its own API** such as `entityType()`, `category()`, or metadata, instead of overriding `getClass()`.

This does **not** mean every method in `Object` is final. For example, `toString()`, `equals(Object)`, and `hashCode()` are commonly overridden according to the appropriate contract.

Even if a subclass wants to “act as” its superclass, `getClass()` still returns the true runtime class of the object, rather than returning the superclass for business convenience.

## 10. `getClass()` is not the same as dynamic dispatch

These are two related topics, but they are not identical:

- **`getClass()`**: a final method that returns the `Class` of the actual object.
- **Virtual method dispatch**: when calling an overridable instance method, the JVM selects the implementation according to the runtime class/object after compile-time checking and signature selection.
- **Static method hiding**: static methods do not undergo instance-style virtual dispatch.
- **Field access**: selects the field based on the compile-time type of the expression, without dispatching like an overridden instance method.
- **Overloading**: the compiler selects the signature based on the types and arguments at compile time.

A variable `Base ref = new Child();` can produce:

~~~text
ref.getClass()          -> Child.class
ref.overriddenMethod()  -> body in Child
ref.staticMethod()      -> static binding by compile-time type
ref.hiddenField         -> field resolved via type Base
~~~

The lines above are a **semantic diagram**, not a Java snippet with complete class definitions. Conclusion: “`getClass()` returns Child” **does not imply** that every expression with the syntax `ref.member` uses the member declared in Child.

## 11. Complete program 4 — runtime class, static hiding, and field hiding

Create the file **`RuntimeClassAndBindingDemo.java`**:

~~~java
class BaseItem {
    String label = "base field";

    static String category() {
        return "base static";
    }

    String description() {
        return "base method";
    }
}

class SpecialItem extends BaseItem {
    String label = "child field";

    static String category() {
        return "child static";
    }

    @Override
    String description() {
        return "child method";
    }
}

public class RuntimeClassAndBindingDemo {
    public static void main(String[] args) {
        BaseItem item = new SpecialItem();

        System.out.println("actual="
                + item.getClass().getSimpleName());
        System.out.println("instance=" + item.description());
        System.out.println("field=" + item.label);
        System.out.println("static=" + BaseItem.category());
        System.out.println("child static=" + SpecialItem.category());
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 RuntimeClassAndBindingDemo.java
java RuntimeClassAndBindingDemo
~~~

**Stdout:**

~~~text
actual=SpecialItem
instance=child method
field=base field
static=base static
child static=child static
~~~

The actual class is `SpecialItem`. However, the `label` field is resolved through the declared type `BaseItem`, while the static method `category()` is called with a **specific class name** to avoid causing confusion. Only the instance method `description()` is overridden, so it dispatches to `SpecialItem`'s implementation.

This shows that `getClass()` cannot be treated as “the type used for every member access”. Compile-time and runtime types participate together under different rules.

## 12. Interfaces: objects have a concrete class, not an “interface class” as their runtime class

Example:

~~~java
Runnable task = () -> { };
~~~

The variable `task` has the declared type `Runnable`, but the actual object is an implementation generated by the runtime. `task.getClass()` returns the **concrete** class of the actual object, not `Runnable.class`.

**Do not predict the name of a lambda class** as a fixed string. The name/generation details of a lambda class are an implementation detail and may vary by JVM, version, or context.

An example using `List`:

~~~java
java.util.List<String> names = java.util.List.of("An");
boolean exactInterface = names.getClass()
        == java.util.List.class;
boolean implementsList = names instanceof java.util.List;
~~~

This is an **illustrative snippet**. `exactInterface` is `false`, because `List` is an interface rather than the concrete class of the list object. `implementsList` is `true`.

Even for a variable declared via an interface, `getClass()` still provides the concrete runtime class. However, typical business code should operate through the `List` contract rather than comparing the internal implementation class name of `List.of`.

## 13. Complete program 5 — interfaces and the reflection API

Create the file **`InterfaceRuntimeDemo.java`**:

~~~java
interface Messenger {
    String send();
}

class EmailMessenger implements Messenger {
    @Override
    public String send() {
        return "email";
    }
}

public class InterfaceRuntimeDemo {
    public static void main(String[] args) {
        Messenger messenger = new EmailMessenger();

        Class<?> actual = messenger.getClass();

        System.out.println("actual=" + actual.getSimpleName());
        System.out.println("declared interface="
                + Messenger.class.isInterface());
        System.out.println("actual is interface="
                + actual.isInterface());
        System.out.println("exact interface="
                + (actual == Messenger.class));
        System.out.println("compatible="
                + Messenger.class.isAssignableFrom(actual));
        System.out.println("message=" + messenger.send());
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 InterfaceRuntimeDemo.java
java InterfaceRuntimeDemo
~~~

**Stdout:**

~~~text
actual=EmailMessenger
declared interface=true
actual is interface=false
exact interface=false
compatible=true
message=email
~~~

`Messenger.class.isInterface()` returns true because this class token represents an **interface**. Conversely, `actual` describes `EmailMessenger`, which is a concrete class, so `isInterface()` is false.

`Messenger.class.isAssignableFrom(actual)` is true: an object of type `EmailMessenger` can be used where a `Messenger` is required. Do not reverse the direction of this method without thinking carefully about **the assignment target**.

## 14. `isInstance`, `isAssignableFrom`, `cast`, and `getClass`

Methods on `Class` answer different questions:

| API | Question |
| --- | --- |
| `obj.getClass()` | Which runtime class does the current object belong to? |
| `Type.class.isInstance(obj)` | Is the object runtime-compatible with Type? |
| `Type.class.isAssignableFrom(Subtype.class)` | Can a value of Subtype be assigned to a variable of type Type? |
| `Type.class.cast(obj)` | Casts the reference to Type with a runtime check; may throw ClassCastException |
| `obj instanceof Type` | Is the object compatible with Type according to the `instanceof` check? |
| `obj.getClass() == Type.class` | Does the object have the **exact** runtime class Type? |

Pay attention to the direction of `isAssignableFrom`: **the receiver is the target type**.

~~~java
Number.class.isAssignableFrom(Integer.class) // true
Integer.class.isAssignableFrom(Number.class) // false
~~~

These are **two illustrative expressions**, following the relationship `Integer extends Number`. To avoid confusion, read the first one as “Number can accept an Integer object”.

Unlike `getClass()`, `Type.class.isInstance(null)` returns `false` **without throwing NullPointerException**. `Type.class.cast(null)` returns null, because casting a null reference is valid, whereas calling `null.getClass()` is invalid at runtime.

## 15. Complete program 6 — checking objects with a class token

Create the file **`ClassTokenChecksDemo.java`**:

~~~java
public class ClassTokenChecksDemo {
    public static void main(String[] args) {
        Object value = Integer.valueOf(7);

        System.out.println("actual="
                + value.getClass().getSimpleName());
        System.out.println("number instance="
                + Number.class.isInstance(value));
        System.out.println("integer instance="
                + Integer.class.isInstance(value));
        System.out.println("exact Number="
                + (value.getClass() == Number.class));
        System.out.println("Number from Integer="
                + Number.class.isAssignableFrom(Integer.class));
        System.out.println("Integer from Number="
                + Integer.class.isAssignableFrom(Number.class));

        Number number = Number.class.cast(value);
        System.out.println("cast=" + number.intValue());
        System.out.println("null instance="
                + Number.class.isInstance(null));
        System.out.println("null cast="
                + (Number.class.cast(null) == null));

        try {
            String.class.cast(value);
        } catch (ClassCastException ex) {
            System.out.println("wrong cast="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ClassTokenChecksDemo.java
java ClassTokenChecksDemo
~~~

**Stdout:**

~~~text
actual=Integer
number instance=true
integer instance=true
exact Number=false
Number from Integer=true
Integer from Number=false
cast=7
null instance=false
null cast=true
wrong cast=ClassCastException
~~~

`getClass() == Number.class` is false, because the runtime object is `Integer`, even though it **is a `Number`**. `Number.class.cast(value)` succeeds; `String.class.cast(value)` fails and throws `ClassCastException`.

In a factory or plugin system, `isInstance`/`cast` can help work with a type held in a `Class<T>` token. However, if the code only needs polymorphism of a known interface, calling methods through the interface is still simpler than reflection.

## 16. `null`: the case where `getClass()` cannot answer

The `getClass()` method requires a **non-null receiver object**. Example:

~~~java
Object value = null;
// Class<?> type = value.getClass(); // Throws NPE at runtime.
~~~

The comment above is an explanation, not a line to run in the complete example below.

Create the file **`NullGetClassDemo.java`**:

~~~java
public class NullGetClassDemo {
    public static void main(String[] args) {
        Object absent = null;

        System.out.println("is null=" + (absent == null));
        System.out.println("instanceof String="
                + (absent instanceof String));

        try {
            absent.getClass();
        } catch (NullPointerException ex) {
            System.out.println("getClass throws="
                    + ex.getClass().getSimpleName());
        }

        Object present = "ok";
        System.out.println("present="
                + present.getClass().getSimpleName());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 NullGetClassDemo.java
java NullGetClassDemo
~~~

**Stdout:**

~~~text
is null=true
instanceof String=false
getClass throws=NullPointerException
present=String
~~~

When the receiver is null, the JVM has no object to ask “what is the actual class”. You should **check for null first**, or choose `instanceof`/`Class.isInstance` if the goal is only a compatibility check where null should yield false.

You should not overuse exception handling for null in business code. The example uses `try/catch` only to demonstrate the behavior; a clearer approach is `if (absent != null) { ... }` when a valid operation requires the object to exist.

## 17. Primitives, wrappers, and class literals

Primitive values such as `int`, `double`, and `boolean` **are not references to objects**. You cannot write `int x = 7; x.getClass();`: the compiler rejects it because primitives do not have instance methods.

However, Java has **class literals** for primitive types:

~~~java
Class<Integer> primitive = int.class;
Class<Integer> boxed = Integer.class;
~~~

This is a valid illustrative snippet. The two `Class` objects are different:

- `int.class` describes the primitive type `int`.
- `Integer.class` describes the wrapper reference type `java.lang.Integer`.
- `Integer.valueOf(7).getClass()` is `Integer.class`, not `int.class`.
- `int.class.isPrimitive()` returns true, whereas `Integer.class.isPrimitive()` is false.

**Autoboxing** can convert a primitive value into a wrapper object when passed into an `Object` variable or `Object` parameter, but that action does not turn `int` into a subclass of `Object`.

## 18. Complete program 7 — primitives and wrappers

Create the file **`PrimitiveClassDemo.java`**:

~~~java
public class PrimitiveClassDemo {
    public static void main(String[] args) {
        int primitiveValue = 7;
        Object boxedValue = primitiveValue;

        System.out.println("primitive name="
                + int.class.getName());
        System.out.println("primitive type="
                + int.class.isPrimitive());
        System.out.println("wrapper name="
                + Integer.class.getName());
        System.out.println("wrapper primitive="
                + Integer.class.isPrimitive());
        System.out.println("boxed actual="
                + boxedValue.getClass().getSimpleName());
        System.out.println("same types="
                + (int.class == Integer.class));
        System.out.println("void primitive="
                + void.class.isPrimitive());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 PrimitiveClassDemo.java
java PrimitiveClassDemo
~~~

**Stdout:**

~~~text
primitive name=int
primitive type=true
wrapper name=java.lang.Integer
wrapper primitive=false
boxed actual=Integer
same types=false
void primitive=true
~~~

`void.class` is a special class token describing `void`; according to the Java API, `Class.isPrimitive()` returns true for primitive types **and void**. Do not infer that there is a `void` value object on which you can call `getClass()`.

The statement `Object boxedValue = primitiveValue;` uses autoboxing to produce an `Integer`. Therefore `boxedValue.getClass()` returns `Integer.class`.

## 19. Arrays are also objects and have a runtime class

Every Java array object has its own runtime class describing the **array type**, for example `int[]`, `String[]`, `String[][]`. `getClass()` on an array object returns the array class rather than the type of the **first element**.

Example:

~~~java
Object values = new String[2];
Class<?> type = values.getClass();
~~~

The resulting `type` describes `String[]`. You can use:

- `type.isArray()` to determine whether it is an array class.
- `type.getComponentType()` to obtain the class token of the **direct element type**.
- `type.getName()` to see the binary-style name of the array class (for example `[Ljava.lang.String;`).
- `type.getCanonicalName()` when a canonical name exists (for example `java.lang.String[]`).

An array of primitives differs from a wrapper array: `int[].class` is not equal to `Integer[].class`. Multidimensional arrays also differ: `int[][].class.getComponentType()` is `int[].class`, not `int.class`.

## 20. Complete program 8 — array classes

Create the file **`ArrayRuntimeClassDemo.java`**:

~~~java
public class ArrayRuntimeClassDemo {
    public static void main(String[] args) {
        Object ints = new int[3];
        Object texts = new String[2];
        Object matrix = new int[2][3];

        System.out.println("ints class="
                + ints.getClass().getName());
        System.out.println("ints component="
                + ints.getClass().getComponentType().getName());
        System.out.println("texts class="
                + texts.getClass().getName());
        System.out.println("texts canonical="
                + texts.getClass().getCanonicalName());
        System.out.println("matrix class="
                + matrix.getClass().getName());
        System.out.println("matrix component="
                + matrix.getClass().getComponentType().getName());
        System.out.println("array superclass="
                + (ints.getClass().getSuperclass() == Object.class));
        System.out.println("array is Object="
                + (ints instanceof Object));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ArrayRuntimeClassDemo.java
java ArrayRuntimeClassDemo
~~~

**Stdout:**

~~~text
ints class=[I
ints component=int
texts class=[Ljava.lang.String;
texts canonical=java.lang.String[]
matrix class=[[I
matrix component=[I
array superclass=true
array is Object=true
~~~

Names starting with `[` are **JVM array name notation** per the `Class.getName()` API: `[I` is one-dimensional `int[]`, `[[I` is two-dimensional `int[][]`, and `[Ljava.lang.String;` is an array of references to `String`.

`getComponentType()` removes only **one array dimension**. Therefore, the component of `int[][]` is `int[]`. You should not write custom string-splitting logic on `getName()` when you can use the official `isArray()` and `getComponentType()` methods.

## 21. Generic type arguments usually do not exist in `getClass()`

Java generics primarily use **type erasure**. Two objects that are both `ArrayList` at runtime will have the **same runtime class**, even if the variables are declared as `List<String>` and `List<Integer>`.

Create the file **`GenericErasureClassDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class GenericErasureClassDemo {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>();
        List<Integer> numbers = new ArrayList<>();

        words.add("Java");
        numbers.add(17);

        System.out.println("words class="
                + words.getClass().getSimpleName());
        System.out.println("numbers class="
                + numbers.getClass().getSimpleName());
        System.out.println("same class="
                + (words.getClass() == numbers.getClass()));
        System.out.println("words first=" + words.get(0));
        System.out.println("numbers first=" + numbers.get(0));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 GenericErasureClassDemo.java
java GenericErasureClassDemo
~~~

**Stdout:**

~~~text
words class=ArrayList
numbers class=ArrayList
same class=true
words first=Java
numbers first=17
~~~

`getClass()` **cannot distinguish** `ArrayList<String>` and `ArrayList<Integer>` in this case. Generic arguments in source code do not create two separate concrete runtime classes.

You also cannot use `instanceof List<String>` in the usual direct way because `List<String>` is a non-reifiable generic type in that check. You can check `instanceof List<?>`, and then check each element or use a token/schema model for generic data if type information is genuinely needed.

Some reflective types such as `ParameterizedType` allow reading the **generic declaration** of a field, superclass, or method when metadata exists; that does **not** mean `someList.getClass()` knows the type arguments the caller variable used when creating the object.

## 22. `getClass()` and compile-time type information in generics

The method itself is declared in `Object` with the return type `Class<?> `, but Java has a special typing rule for expressions calling `getClass()` to provide a tighter `Class` token type based on the **static type of the receiver**.

Example:

~~~java
Number value = Integer.valueOf(7);
Class<? extends Number> actual = value.getClass();
~~~

This is a valid illustrative snippet in Java 17. The variable `actual` has the type `Class<? extends Number>` at compile time, while the `Class` object it points to at runtime is still **`Integer.class`**.

If the receiver at compile time is `Object`, the result is typed as `Class<? extends Object>` (equivalent to a very wide bound). If the receiver type is an interface, the typing rule uses the appropriate erasure per the JLS, rather than turning the interface into the object's runtime class.

**Do not equate the generic type of a variable holding a `Class` token with the runtime class object it represents.** `Class<? extends Number>` is a static constraint; the token inside can represent `Integer`, `Double`, or another `Number` subclass.

For a factory API, you can pass `Class<T>` as a parameter if you want to constrain the result type. However, `getClass()` does not remember every generic type argument in source expressions.

## 23. Class names: `getName`, `getSimpleName`, `getCanonicalName`

These names are useful for logging, but they are not synonymous:

- **Simple name**: the short name, for example `Entry`.
- **Binary name**: the name the JVM uses for member classes with the appropriate notation, for example `java.util.Map$Entry`.
- **Canonical name**: the canonical naming form if it exists, for example `java.util.Map.Entry`.
- **Anonymous/local classes**: may have no canonical name; an anonymous class has an empty simple name.

Complete program **`ClassNameFormsDemo.java`**:

~~~java
public class ClassNameFormsDemo {
    static class Nested {
    }

    public static void main(String[] args) {
        Class<?> nested = Nested.class;

        System.out.println("simple="
                + nested.getSimpleName());
        System.out.println("binary="
                + nested.getName());
        System.out.println("canonical="
                + nested.getCanonicalName());

        class Local {
        }
        Class<?> local = Local.class;
        System.out.println("local canonical null="
                + (local.getCanonicalName() == null));

        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
            }
        };

        System.out.println("anonymous simple empty="
                + anonymous.getClass().getSimpleName().isEmpty());
        System.out.println("anonymous canonical null="
                + (anonymous.getClass().getCanonicalName() == null));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ClassNameFormsDemo.java
java ClassNameFormsDemo
~~~

**Stdout:**

~~~text
simple=Nested
binary=ClassNameFormsDemo$Nested
canonical=ClassNameFormsDemo.Nested
local canonical null=true
anonymous simple empty=true
anonymous canonical null=true
~~~

Do not use generated names for local/anonymous classes such as `$1` as business keys or test assertions; specific binary names can depend on declaration position and the compiler. The program only prints properties **specified stably by the API**: local/anonymous classes have no canonical name, and an anonymous simple name is an empty string.

## 24. What do `getSuperclass` and `getInterfaces` return?

From a class token, you can query type relationships.

~~~java
Class<?> superclass = Integer.class.getSuperclass();
Class<?>[] interfaces = String.class.getInterfaces();
~~~

This is an illustrative snippet. `Integer.class.getSuperclass()` is `Number.class`. `getInterfaces()` returns an array of interfaces **directly declared** according to the API, not the result of “traversing the entire graph and returning every interface”.

Special cases:

- `Object.class.getSuperclass() == null`.
- `SomeInterface.class.getSuperclass() == null` because an interface is not a class with a regular superclass.
- Primitive class tokens also have `getSuperclass() == null`.
- An array class has `Object.class` as its direct superclass and also implements special interfaces such as `Cloneable` and `Serializable`.

To check whether a class **is compatible** with an interface/superclass, `isAssignableFrom` or `isInstance` is usually more appropriate than manually stepping through one level of `getSuperclass()`, because inheritance can have multiple levels and interfaces form a non-linear graph.

## 25. Reflection: `Class` is metadata, not a substitute for polymorphic design

From a `Class` token, the Java Reflection API allows querying extensive metadata such as names, superclasses, interfaces, methods, and fields. In valid contexts, you can also invoke methods or create instances via reflection with appropriate access permissions.

However, **just because `getClass()` exists does not mean reflection should be used for all business logic**.

An example you should not write:

~~~java
if (service.getClass().getSimpleName().equals("EmailService")) {
    // Behavior for EmailService.
} else if (service.getClass().getSimpleName().equals("SmsService")) {
    // Behavior for SmsService.
}
~~~

This is **pseudocode illustrating an anti-pattern**, not a program with complete class definitions. Branches that depend on class names are fragile when changing packages, renaming implementations, generating proxies, or introducing new subclasses.

A usually better object-oriented approach is to define a contract:

~~~java
interface Service {
    void execute();
}
~~~

and let implementations override/implement `execute()`. The caller only needs `service.execute()`, without having to inspect the class name first.

**Reflection has its own place** in dependency injection, serialization, testing tools, plugin frameworks, and mapping mechanisms. Use it when genuinely handling metadata/dynamic types, rather than replacing regular polymorphic calls.

## 26. How does `Class.forName` differ from `getClass()`?

`obj.getClass()` starts from an **existing object**, returning its runtime class.

`SomeType.class` starts from a **type name written in source code**, returning the corresponding class token.

`Class.forName("package.Type")` starts from a **type name as a string**, asking the class loader to locate the class and — in the single-parameter overload — **initializing the class according to the API rules**.

These are three different questions:

| API | Input | What to remember |
| --- | --- | --- |
| `obj.getClass()` | Non-null object reference | Discovers the runtime class of the object |
| `Type.class` | Type name known at compile time | Does not need a Type object and does not automatically trigger initialization merely via a class literal |
| `Class.forName(name)` | Name string + loader mechanism | Locates the class and requests class initialization |
| `Class.forName(name, false, loader)` | Name + loader + initialize flag | Does not request class initialization when initialize=false |

**Do not confuse obtaining a `Class` object with having created an instance of that class.** `Class.forName` does not automatically call the `new Type()` constructor just to return metadata.

## 27. Complete program 9 — class literals and `forName`

Create the file **`ClassLookupDemo.java`**:

~~~java
class LazyPart {
    static {
        System.out.println("LazyPart initialized");
    }

    LazyPart() {
        System.out.println("LazyPart constructed");
    }
}

public class ClassLookupDemo {
    public static void main(String[] args) throws Exception {
        System.out.println("begin");

        Class<?> literal = LazyPart.class;
        System.out.println("literal="
                + literal.getSimpleName());

        ClassLoader loader =
                ClassLookupDemo.class.getClassLoader();
        Class<?> metadata =
                Class.forName("LazyPart", false, loader);
        System.out.println("metadata same="
                + (metadata == literal));

        System.out.println("before forName");
        Class.forName("LazyPart");
        System.out.println("after forName");

        Object created = new LazyPart();
        System.out.println("runtime same="
                + (created.getClass() == literal));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ClassLookupDemo.java
java ClassLookupDemo
~~~

**Stdout:**

~~~text
begin
literal=LazyPart
metadata same=true
before forName
LazyPart initialized
after forName
LazyPart constructed
runtime same=true
~~~

`LazyPart.class` and `Class.forName(..., false, loader)` can obtain the class token **without running the static block**. Only when calling `Class.forName("LazyPart")` does the class need to be initialized and the static block prints the message.

The statement `new LazyPart()` then creates an instance, printing the constructor message. `created.getClass() == literal` is true because the token describes the true runtime class of that object.

From this stdout alone, one cannot determine the exact moment the class was **loaded/linked**; the code only observes static initialization and object construction.

## 28. `getClass()` inside a superclass method

Even when `getClass()` is called from a method declared in a superclass, it still returns the class of the **actual object**. This is not a method overridden by a subclass; `getClass()` is final, yet the receiver object still carries its true runtime identity.

Create the file **`InheritedGetClassDemo.java`**:

~~~java
class BaseNode {
    String runtimeName() {
        return getClass().getSimpleName();
    }

    String staticName() {
        return BaseNode.class.getSimpleName();
    }
}

class ChildNode extends BaseNode {
}

public class InheritedGetClassDemo {
    public static void main(String[] args) {
        BaseNode first = new BaseNode();
        BaseNode second = new ChildNode();

        System.out.println("first runtime="
                + first.runtimeName());
        System.out.println("second runtime="
                + second.runtimeName());
        System.out.println("first static="
                + first.staticName());
        System.out.println("second static="
                + second.staticName());
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 InheritedGetClassDemo.java
java InheritedGetClassDemo
~~~

**Stdout:**

~~~text
first runtime=BaseNode
second runtime=ChildNode
first static=BaseNode
second static=BaseNode
~~~

The `runtimeName()` method is written in BaseNode, but `getClass()` queries **the receiver running that method**, not “which class the method was declared in”. For a ChildNode object, it returns ChildNode.

Conversely, `BaseNode.class` is a **fixed literal in source code**, so `staticName()` always returns BaseNode even when the method is called through an object of the subclass.

## 29. Using `getClass()` in `equals()`: exact-type equality

In `equals(Object)`, two strategies are commonly discussed:

**Exact runtime type strategy:**

~~~java
if (other == null || getClass() != other.getClass()) {
    return false;
}
~~~

This accepts only two objects with the **exact same runtime class**. It excludes subclass objects even if the fields in the superclass are equal.

**Family-of-types strategy:**

~~~java
if (!(other instanceof BaseValue)) {
    return false;
}
~~~

This accepts objects belonging to a compatible subtype. If a subclass adds fields that matter for equality, the design must be very careful to preserve the **symmetry and transitivity** of `equals`; you cannot mechanically replace `getClass` with `instanceof`.

The choice must depend on the **equality contract** of the type. For immutable value objects where each class has its own value domain, an exact-class check can be useful. For entities where an ORM generates proxy subclasses or a framework uses dynamic proxies, an exact runtime class comparison may **not accurately reflect** domain identity; you need to check the framework's identity/equality and proxy strategy.

## 30. Complete program 10 — `equals` checking the exact class

Create the file **`ExactClassEqualityDemo.java`**:

~~~java
class Badge {
    private final int id;

    Badge(int id) {
        this.id = id;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (other == null || getClass() != other.getClass()) {
            return false;
        }
        Badge badge = (Badge) other;
        return id == badge.id;
    }

    @Override
    public int hashCode() {
        return Integer.hashCode(id);
    }
}

class PremiumBadge extends Badge {
    PremiumBadge(int id) {
        super(id);
    }
}

public class ExactClassEqualityDemo {
    public static void main(String[] args) {
        Badge first = new Badge(7);
        Badge second = new Badge(7);
        Badge premium = new PremiumBadge(7);
        Badge premiumAgain = new PremiumBadge(7);

        System.out.println("base equals base="
                + first.equals(second));
        System.out.println("base equals child="
                + first.equals(premium));
        System.out.println("child equals base="
                + premium.equals(first));
        System.out.println("child equals child="
                + premium.equals(premiumAgain));
        System.out.println("same reference="
                + (first == second));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ExactClassEqualityDemo.java
java ExactClassEqualityDemo
~~~

**Stdout:**

~~~text
base equals base=true
base equals child=false
child equals base=false
child equals child=true
same reference=false
~~~

`Badge.equals` calls `getClass()` on **both objects**. A direct Badge and a PremiumBadge have different runtime classes, so they are not equal even when `id` matches. Two PremiumBadge instances with the same id are still considered equal according to the implementation inherited from Badge.

This is an example **illustrating the exact-class strategy**, not an equality recipe for every entity. If `PremiumBadge` has additional domain information that affects equality, the contract needs to be redesigned; do not let a subclass add equality-significant state while accidentally inheriting a comparison based solely on `id`.

Note that `hashCode` in the example is based only on id: two objects of different classes can share the same hash code, which **is permitted** because two unequal objects may still have colliding hashes. The contract requires that **if equals is true then hashCode must be equal**, not the converse.

## 31. Proxies, frameworks, and cases where exact class is too strict

Some tools can generate subclasses/proxy classes or dynamic implementations:

- ORM proxies may carry a runtime class different from the entity class you declared.
- A dynamic proxy for an interface has a runtime class generated by the proxy mechanism, not the interface class token itself.
- Mocking libraries may alter the runtime class depending on the mocking technique.
- Some implementations of `List.of` use internal classes that the API does not guarantee to keep identical across JDK versions.

If code writes:

~~~java
if (repository.getClass() == MyRepository.class) {
    // handle only this exact class
}
~~~

then it may skip a valid proxy/wrapper even though it implements the proper interface. This is **illustrative pseudocode**, assuming the corresponding variable and class exist.

Instead of relying on an exact class, consider:

- `repository instanceof Repository` if only the type relationship is needed.
- Calling methods of the `Repository` interface directly if possible.
- Using `Class.isAssignableFrom` when holding class tokens rather than objects.
- Using the framework's official API to retrieve the **user class** or logical entity type if the application genuinely needs it, because `getClass()` returns the runtime proxy class as seen by the JVM.

**Do not claim** that every ORM/mocking framework always creates subclasses: the exact mechanism depends on the tool, version, and configuration. The lesson simply points out the limits of exact runtime class checks.

## 32. Common compile-time and runtime errors

| Situation | Cause | Fix |
| --- | --- | --- |
| `Object x = "a"; x.length();` | Declared type `Object` does not have `length()` | Use the proper contract or check/cast to `String` |
| `int value = 1; value.getClass();` | Primitives do not have instance methods | Use `int.class` or boxing if needed |
| `Object obj = null; obj.getClass();` | Null receiver | Check for null or use `instanceof`/`isInstance` |
| `obj.getClass() == Parent.class` skips subclasses | Exact runtime class comparison | Use `instanceof` if subtypes must be accepted |
| `obj instanceof Parent` while assuming exact Parent | `instanceof` accepts subclasses | Compare exact class if the contract requires it |
| Expecting `List<String>` and `List<Integer>` to differ in `getClass` | Erasure and same implementation class | Track separate schema/type tokens |
| Comparing `getName()` and treating it as runtime class identity | Two loaders may define classes with the same name | Compare `Class` tokens or resolve loader identity |
| Using `getSimpleName()` as a durable identifier | Simple names can collide and change on refactoring | Use a stable domain ID |
| Calling `getCanonicalName().length()` on an anonymous class | Canonical name may be null | Check for null |
| Predicting the specific class name of a lambda/`List.of` | Implementation details are not guaranteed | Log characteristics/contract, do not hard-code names |
| Using `getSuperclass()` to discover all interfaces | Only inspects the direct superclass | Use `isAssignableFrom`/reflection as appropriate |
| Using `getClass()` across every business branch | Bypasses polymorphism, hard to extend | Use interfaces/overriding/behavior-based dispatch |
| Exact `getClass()` in `equals` when proxies exist | Proxy class may differ from entity class | Define equality suited to the framework |
| Thinking `Type.class` invokes the constructor automatically | A class literal does not create an instance | Use `new` or a factory if an object is needed |
| Thinking `Class.forName` always loads without initializing | The single-parameter overload requests initialization | Check the API's `initialize` flag |

## 33. Decision workflow for choosing which API to use

When asking “what kind of object is this?”, determine the purpose first.

**If you need business behavior:** use interface/superclass methods and overriding instead of repeatedly querying the class.

**If you need to know the exact runtime implementation:** use `obj.getClass()`, then you can print `getName()` or compare tokens with `Type.class`, keeping in mind that proxies and class loaders can make the result differ from business intent.

**If you need to check compatibility with a contract:** use `obj instanceof Interface` or `Interface.class.isInstance(obj)`. When you already have a compile-time variable of the right type and a sufficient API, a type check is usually unnecessary.

**If you are holding class tokens:** `Parent.class.isAssignableFrom(actualClass)` expresses “Can Parent accept type actualClass?”.

**If you only need a null check:** use `obj == null` or `obj != null`, do not call `getClass()`.

**If you need to create an object from metadata:** `Class` and reflection provide APIs for specific cases, but you must handle constructors, access permissions, and errors; do not infer a default object instantiation command from `getClass()`.

**If comparing for equality:** write the `equals/hashCode` contract deliberately; exact `getClass` and `instanceof` represent two different notions of the scope of values that can be equal.

## 34. Output prediction exercises

**Exercise 1.** `Object x = "Java";`. What does `x.getClass() == String.class` return? Does the compiler allow `x.length()` directly?

**Exercise 2.** `Number n = Integer.valueOf(8);`. What are `n.getClass().getSimpleName()`, `n instanceof Number`, and `n.getClass() == Number.class` respectively?

**Exercise 3.** Given `class A {}` and `class B extends A {}`, `A a = new B();`, what differs between `a.getClass() == A.class` and `a instanceof A`?

**Exercise 4.** `Object x = null;`. Compare `x instanceof String`, `String.class.isInstance(x)`, and `x.getClass()`.

**Exercise 5.** Why can `List<String> a = new ArrayList<>(); List<Integer> b = new ArrayList<>();` satisfy `a.getClass() == b.getClass()`?

**Exercise 6.** `int x = 10;`. Can you call `x.getClass()`? What is `int.class == Integer.class`? With `Object boxed = x;`, what does `boxed.getClass()` return?

**Exercise 7.** `Object x = new String[2];`. What is `x.getClass().isArray()`? Which type does `getComponentType()` return?

**Exercise 8.** `Object x = new int[2][3];`. What do `x.getClass().getName()` and `getComponentType().getName()` return?

**Exercise 9.** `Runnable r = () -> { };`. Should you compare `r.getClass().getName()` against a hard-coded lambda name? Why?

**Exercise 10.** What does `Parent.class.isAssignableFrom(Child.class)` mean? Is it symmetric with `Child.class.isAssignableFrom(Parent.class)`?

**Exercise 11.** A method declared in `Base` returns `getClass().getSimpleName()`. If executed on an instance of `Child extends Base`, must it return `Base` because the method resides in Base?

**Exercise 12.** Can `getClass()` be overridden by a subclass to return superclass `Base.class` instead of actual `Child.class`?

**Exercise 13.** Why does reading `SomeType.class` not necessarily run the static initializer, whereas `Class.forName("SomeType")` may request initialization?

**Exercise 14.** If `Employee.equals` uses `getClass()` exact comparison, is a proxy subclass representing the same entity guaranteed to be considered equal? Should you immediately switch to `instanceof` in every system?

**Exercise 15.** Compare `getSimpleName`, `getName`, and `getCanonicalName` for nested classes, local classes, and anonymous classes. Which name can be null?

**Exercise 16.** Why with `Base ref = new Child();` can `ref.field` read the Base field, while `ref.method()` calls the Child override, and `ref.getClass()` is still Child?

### Reference answers

1. `true`; `x.length()` does not compile because the declared type is `Object`.
2. `Integer`, `true`, `false`. Number is the superclass of Integer but not the exact class.
3. `false` and `true`: exact runtime class differs from compatibility.
4. `false`, `false`, while `x.getClass()` throws `NullPointerException`.
5. Because both actual objects are `ArrayList`; generic type arguments undergo erasure at runtime.
6. Primitives do not have `getClass()`; comparing the class tokens is false; boxing creates an Integer reference so `boxed.getClass() == Integer.class`.
7. `true`; the component is `String.class`.
8. `[[I` and `[I` because the component of int[][] is int[].
9. No; the lambda class name is an implementation detail that should not be hard-coded.
10. Parent can accept Child, but Child does not necessarily accept Parent; the call direction is not symmetric.
11. No. The runtime receiver is Child so `getClass()` returns `Child.class`.
12. No. `Object.getClass()` is final.
13. A class literal does not automatically request initialization; single-parameter `Class.forName(name)` requests class initialization per the API.
14. Not necessarily; exact class comparison may reject a proxy subclass. Do not replace mechanically: you must determine the equality contract and specific proxy mechanism.
15. A nested class has different simple/binary/canonical names; local/anonymous classes usually have no canonical name, so `getCanonicalName()` returns null; an anonymous simple name is empty.
16. Field/static binding and virtual method dispatch follow different rules; `getClass()` always reflects the runtime object.

## 35. Knowledge self-check checklist

- Have you distinguished **declared type** from **actual runtime class**?
- When using a superclass/interface variable, do you recognize that the compiler only sees the API exposed by the declared type?
- Does `getClass()` return a `Class` token rather than directly returning a string?
- Have you distinguished `obj.getClass()`, `Type.class`, and `Class.forName`?
- Do you know that `Object.getClass()` is `final` and cannot be overridden?
- With subclasses, do you distinguish `getClass()==Parent.class` from `instanceof Parent`?
- Do you remember to check for null before calling `getClass()`?
- Do you know that primitives cannot invoke instance methods, yet have the `int.class` class literal?
- Do you understand that `Object boxed=intValue` leads to a wrapper runtime class?
- Do you know that arrays are objects, and what `isArray`/`getComponentType` return?
- Do you understand that generic erasure means two `ArrayList<T>` instances can have the same runtime class?
- Do you understand `isAssignableFrom` in the direction “the receiver is the target type”?
- Do you avoid predicting the internal class names of lambdas, proxies, and `List.of`?
- Do you know that local/anonymous classes may not have a canonical name?
- When writing `equals()`, have you clearly defined exact-type or family-of-types equality?
- Do you avoid confusing the existence of a `Class` object with an object instance having been created?
- Do you use interfaces/polymorphism for behavior instead of a chain of `if` statements checking simple class names?
- With framework proxies and class loaders, have you avoided treating a class name string as absolute runtime identity?

## 36. Official documentation for reference

- [Java SE 17 API — Object.getClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#getClass()): final method and return type rules.
- [Java SE 17 API — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): class tokens, `getName`, `getSimpleName`, `getCanonicalName`, `isInstance`, `isAssignableFrom`, `cast`, `getComponentType`.
- [Java SE 17 API — Class.forName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)): class lookup and initialization flag.
- [JLS 17 §4.3 — Reference Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.3): objects/references and reference types.
- [JLS 17 §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): why generic type arguments do not give each ArrayList a separate runtime class.
- [JLS 17 §5 — Conversions and Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html): upcasting, boxing, and conversion kinds.
- [JLS 17 §15.20.2 — Type Comparison Operator instanceof](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): type compatibility check.
- [JLS 17 §15.8.2 — Class Literals](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.8.2): `Type.class`.
- [JLS 17 §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): signature selection and method dispatch.
- [JLS 17 §12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): when a class/interface is initialized.
- [JVMS 17 §5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3): runtime class identity and defining loader.

**Conclusion:** `getClass()` returns the **exact runtime class of the object**, regardless of whether the variable holding the object is declared using a superclass or an interface. The declared type still determines the API the compiler sees, overload selection, and many access rules; the runtime class participates in the dispatch of overridable instance methods. Use `getClass()` when you need **exact class identity/metadata**, use `instanceof` or `Class.isInstance/isAssignableFrom` when you need **type compatibility**, and prefer **polymorphism** when you need behavior. Do not call `getClass()` on null, do not expect to obtain generic type arguments from it, and do not turn runtime class names into business keys.
