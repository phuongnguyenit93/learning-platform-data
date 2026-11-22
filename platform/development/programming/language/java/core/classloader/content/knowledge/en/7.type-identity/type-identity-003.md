# Comparing `Class`, `instanceof`, `isInstance`, and `isAssignableFrom`

> **Context:** Java Core → ClassLoader → Type Identity. The goal of this article is to know precisely whether you are asking about **two runtime types**, **an object and a runtime type**, or **a class name**; from there, choose the appropriate comparison, understand the impact of the **defining class loader**, and avoid confusion with generic types, primitive conversions, and array covariance. Examples use Java 17 or later, unless explicitly noted otherwise.

## 1. The Four Tools Answer Different Questions

Suppose `Dog extends Animal`, and a variable `value` holds the object `new Dog()`.

| Syntax/API | Question it answers | Result with `Dog` and `Animal` |
| --- | --- | --- |
| `value.getClass() == Dog.class` | Is the **exact runtime class** of the object specifically `Dog`? | `true` |
| `value instanceof Animal` | Is the non-null object of type `Animal` (including subtypes)? | `true` |
| `Animal.class.isInstance(value)` | Equivalent to the object-vs-type check, but with the type supplied **dynamically** via `Class<?>`? | `true` |
| `Animal.class.isAssignableFrom(Dog.class)` | Can a value with runtime type `Dog` be **assigned via widening reference** to a variable of type `Animal`? | `true` |
| `Dog.class.isAssignableFrom(Animal.class)` | Is *any* object with static type `Animal` guaranteed to be assignable to `Dog`? | `false` |
| `Dog.class == Animal.class` | Are the two runtime types the exact same `Class`? | `false` |

**Rule of thumb:** For `T.class.isAssignableFrom(S.class)`, read it as **"Can S be assigned to T?"**, meaning target `T` is **on the left**. For `T.class.isInstance(object)`, read it as **"Is object an instance of T?"**. For `==` between `Class` objects, we ask **"Are these the exact same runtime type?"**, without considering polymorphism.

Illustrating the relationships:

~~~text
Animal                  object = new Dog()
  ^
  | extends                   |
 Dog                          v
  |                 getClass() == Dog.class  --> true
  +----------------> object instanceof Animal --> true

Animal.class.isAssignableFrom(Dog.class)  --> true
Dog.class.isAssignableFrom(Animal.class)  --> false
~~~

The operations above belong to **runtime type checking**. They are not mechanisms for comparing business data (an object's `equals`), and they do not replace the compiler checking Java source code before the program runs.

## 2. `Class<?>` Represents a **Runtime Type**, Not Just a Name String

Each class/interface defined by the JVM has a `java.lang.Class` object representing it in the VM. Other kinds also have a corresponding `Class`, such as arrays, primitives, and `void`:

~~~java
Class<String> textType = String.class;
Class<Integer> boxedType = Integer.class;
Class<?> primitiveType = int.class;
Class<?> arrayType = String[].class;
Class<?> voidType = void.class;
~~~

Ways to obtain a `Class`:

- `MyType.class`: class literal, a type written in Java code, requiring no instance creation.
- `someObject.getClass()`: the **exact** runtime class of the existing object; if `someObject` is `null`, it throws `NullPointerException`.
- `Class.forName("pkg.MyType")`: looks up a class by name via the caller's loader, and **may trigger initialization** under the default overload.
- `Class.forName(name, false, loader)`: looks up using the chosen loader while **not requiring** initialization at that time.
- `loader.loadClass(name)`: obtains a `Class<?>` from a loader; the result may have been **defined** by a parent.

### 2.1. A Class Name Is Not Enough to Identify a Runtime Type

For ordinary classes/interfaces, the JVMS defines identity by:

`(binary name, defining class loader)`

A name such as `com.example.Plugin` can be defined by two different loaders; the two corresponding `Class` objects are **not equal**, even if they read identical bytecode. If the two loaders merely **delegate to the same parent**, they can return the **exact same `Class`**.

Therefore:

~~~java
left.getName().equals(right.getName())
~~~

does not imply:

~~~java
left == right
~~~

nor does it imply:

~~~java
left.isAssignableFrom(right)
~~~

This is at the heart of every "`X cannot be cast to X`" error in plugins/containers. Include `getClassLoader()`, `getModule()`, runtime package, and dependency provenance when debugging; do not only print `getName()`.

### 2.2. When to Use `==`, `equals`, and `getName`?

Given two variables `Class<?> left, right`:

- `left == right` checks for the **exact same `Class` object**. Use when strict runtime identity is needed.
- `left.equals(right)` has the same identity meaning in `Class` (it does not compare names alone); `Class` does not define value equality based on `getName()`.
- `left.getName().equals(right.getName())` compares the **text binary name** (or the specialized name form of array/hidden classes), which does not prove compatibility.
- `left.getSimpleName()` and `getCanonicalName()` can collide or be absent in local/anonymous/hidden classes; they are also not reliable identity keys for plugins.

**Do not use:** `clazz.toString().contains("...")` to decide assignability. Business code must express contracts using a type hierarchy or explicit plugin metadata, not by parsing class names.

## 3. `instanceof`: Checking an Object Against a Reference Type

Java 17 syntax:

~~~java
Object value = "hello";

boolean isText = value instanceof String;      // true
boolean isNumber = value instanceof Number;    // false
boolean isObject = value instanceof Object;    // true
boolean nullMatches = (null instanceof Object); // false
~~~

Key points to remember:

1. The left-hand operand is evaluated as **an expression**; if its value is `null`, the reference type check always returns `false`, without throwing `NullPointerException`.
2. If non-null, the runtime checks whether the object is compatible with the right-hand reference type according to Java semantics (class, interface, or array).
3. Subtypes are accepted. `instanceof Animal` is true for `Dog` if `Dog extends Animal`; it does **not** require the runtime class to be strictly equal to `Animal.class`.
4. The right-hand type must be valid at **compile** time. Java 17 does not allow you to dynamically pass a `Class<?>` variable into the `instanceof` syntax.
5. The compiler also checks cast validity. For example, `String s = "x"; boolean b = s instanceof Integer;` is a compile-time error in Java 17 because the two final types have no compatible type relationship; changing `s` to `Object` makes the runtime check valid and return `false`.

### 3.1. Pattern Matching for `instanceof` Since Java 16

~~~java
static String describe(Object value) {
    if (value instanceof String text) {
        return "text length=" + text.length();
    }
    if (value instanceof Number number) {
        return "number=" + number;
    }
    return "other";
}
~~~

This is an **illustrative method** placed inside a class, not a standalone file. The pattern variable `text` can only be used in scopes where the compiler determines that the check succeeded. Null behavior and runtime assignability remain the same as traditional `instanceof`: `null` does not match the pattern.

**Choose `instanceof` when:** the target type is known at compile time and you are branching on the object's type. If you only need to invoke polymorphic behavior, an interface/virtual method is usually cleaner than a long chain of `if (obj instanceof ...)`.

### 3.2. `instanceof` vs. Type Casting

~~~java
Object candidate = "hello";
System.out.println(candidate instanceof Integer); // false

// ((Integer) candidate) compiles, but will throw ClassCastException
// when the program attempts to execute this cast.
~~~

`instanceof` returns `false` for an incompatible object, whereas an invalid cast throws `ClassCastException`. Having been typed as `Object` does not actually change the object into an `Integer`. Code validity at compile time also does not guarantee that the cast will succeed at runtime.

## 4. `Class.isInstance(Object)`: `instanceof` with a Dynamically Selected Target Type

API signature:

~~~java
public boolean isInstance(Object obj)
~~~

Suppose a user or plugin selects a `Class<?> selectedType` from a registry. Then:

~~~java
boolean accepted = selectedType.isInstance(value);
~~~

is equivalent to checking `value instanceof SelectedType` **if you could write `SelectedType` in source code** (for reference type checks). The API reflects the runtime hierarchy of classes, interfaces, and arrays.

Properties:

- `String.class.isInstance("hi")` → `true`.
- `CharSequence.class.isInstance("hi")` → `true`.
- `Number.class.isInstance("hi")` → `false`.
- `String.class.isInstance(null)` → `false`; null is a permitted value and does not throw an exception.
- `int.class.isInstance(Integer.valueOf(1))` → `false`. A primitive class has no object instances of a primitive type; the wrapper object has runtime class `Integer`.
- `String[].class.isInstance(new String[2])` → `true`.
- `Object[].class.isInstance(new int[2])` → `false` (a primitive array is not an `Object[]`).

**Use cases:** frameworks that need to check objects against a runtime-configured type, annotation metadata, SPI, serializers, or plugin contracts. If you already have `Class<T>`, you can use `type.cast(value)` to perform a runtime cast with the corresponding check; `cast` **throws `ClassCastException`** when the object is non-null and incompatible, whereas `isInstance` only returns a boolean.

### 4.1. Experiment: Dynamic `Class<?>` and `isInstance`

File **`DynamicTypeCheck.java`**:

~~~java
public class DynamicTypeCheck {
    public static void main(String[] args) throws Exception {
        Class<?> requested = Class.forName("java.lang.Number");
        Object first = Integer.valueOf(7);
        Object second = "seven";

        System.out.println("first: " + requested.isInstance(first));
        System.out.println("second: " + requested.isInstance(second));
        System.out.println("null: " + requested.isInstance(null));
        System.out.println("Integer type: "
                + requested.isAssignableFrom(Integer.class));
        System.out.println("String type: "
                + requested.isAssignableFrom(String.class));
    }
}
~~~

~~~bash
javac --release 17 DynamicTypeCheck.java
java DynamicTypeCheck
~~~

Stdout:

~~~text
first: true
second: false
null: false
Integer type: true
String type: false
~~~

Explanation: `requested` is the class token for `Number`. `Integer` extends `Number`, while `String` does not; the object checks return true/false accordingly. The `null` check line is always `false`. The last two lines compare **two types**, unlike the first three lines, which compare a **type and an object**.

## 5. `Class.isAssignableFrom(Class<?>)`: Assignment Relationship Between **Two Types**

Signature:

~~~java
public boolean isAssignableFrom(Class<?> cls)
~~~

Read:

~~~java
Target.class.isAssignableFrom(Source.class)
~~~

as the question: **"Can a value of type Source be assigned to a variable of type Target via identity/widening reference conversion?"**

~~~java
Number n = Integer.valueOf(1); // valid
// Integer i = (Number) ...;    // cannot be implicitly assigned in the reverse direction
~~~

Correspondingly:

~~~java
Number.class.isAssignableFrom(Integer.class); // true
Integer.class.isAssignableFrom(Number.class); // false
Object.class.isAssignableFrom(String.class);  // true
CharSequence.class.isAssignableFrom(String.class); // true
Runnable.class.isAssignableFrom(String.class); // false
String.class.isAssignableFrom(String.class);  // true
~~~

Every type is assignable from **itself**, including interfaces, arrays, and primitives. A target interface can accept a class that implements it; a target class can accept a subtype. Two interfaces with an `extends` relationship are checked in the proper direction; two interfaces without an explicit relationship are **not** automatically compatible just because a class happens to implement both.

**Easily confused direction:**

~~~java
Animal.class.isAssignableFrom(Dog.class) // true: Dog → Animal
Dog.class.isAssignableFrom(Animal.class) // false: Animal → Dog is not automatic
~~~

The name `isAssignableFrom` describes the **receiver**: the class on the left must be able to "be assigned from" the argument. This is a **type-level** check that does not require creating an object at all.

### 5.1. How Do `isAssignableFrom` and `isInstance` Relate?

For an object `obj != null`, given `source = obj.getClass()`:

~~~java
target.isInstance(obj)
target.isAssignableFrom(obj.getClass())
~~~

have the same result regarding reference convertibility in ordinary class/interface/array cases. However, **they cannot be substituted mechanically**:

- `obj == null`: `target.isInstance(null)` returns `false`, whereas `obj.getClass()` throws `NullPointerException`.
- `isAssignableFrom` requires a `Class<?>` input, not an object.
- `isInstance` requires an object and does not accept a primitive value directly without boxing.
- Both check runtime class identity; having the same binary name across two defining loaders does **not** make the result true.

If `cls == null`, calling `target.isAssignableFrom(null)` throws `NullPointerException` per the API rather than returning false. This behavior differs from `target.isInstance(null)`.

### 5.2. Typical Truth Table

| Target on the left | Source on the right | `target.isAssignableFrom(source)` | Reason |
| --- | --- | --- | --- |
| `Object.class` | `String.class` | `true` | `String` is a subtype of `Object` |
| `Number.class` | `Integer.class` | `true` | Inheritance |
| `Integer.class` | `Number.class` | `false` | No widening reference in this direction |
| `CharSequence.class` | `String.class` | `true` | `String implements CharSequence` |
| `Runnable.class` | `String.class` | `false` | `String` does not implement `Runnable` |
| `Object.class` | `Object.class` | `true` | Same type |
| `Object.class` | `int.class` | `false` | Does not automatically perform boxing |
| `long.class` | `int.class` | `false` | Does not perform primitive widening |
| `int.class` | `int.class` | `true` | Exact same primitive type |
| `Object.class` | `int[].class` | `true` | An array is a reference object |
| `Object[].class` | `int[].class` | `false` | A primitive array is not an object array |

**Do not reason backward:** `target.isAssignableFrom(source) == false` does not mean you can *never* cast an object whose compile-time type is source to target. For example, an `Animal` variable whose actual runtime object is a `Dog` can be cast to `Dog` after a runtime check; however, `Dog.class.isAssignableFrom(Animal.class)` is still false because it is not true for every `Animal`.

## 6. A Complete Runnable Example Comparing All Four Checks

File **`TypeCheckComparison.java`**:

~~~java
public class TypeCheckComparison {
    interface Tagged { }

    static class Animal { }

    static class Dog extends Animal implements Tagged { }

    static class Cat extends Animal { }

    public static void main(String[] args) {
        Object pet = new Dog();
        Object absent = null;

        System.out.println("exact Dog: "
                + (pet.getClass() == Dog.class));
        System.out.println("exact Animal: "
                + (pet.getClass() == Animal.class));

        System.out.println("instanceof Animal: "
                + (pet instanceof Animal));
        System.out.println("instanceof Tagged: "
                + (pet instanceof Tagged));
        System.out.println("instanceof Cat: "
                + (pet instanceof Cat));
        System.out.println("null instanceof Animal: "
                + (absent instanceof Animal));

        System.out.println("isInstance Animal: "
                + Animal.class.isInstance(pet));
        System.out.println("isInstance Cat: "
                + Cat.class.isInstance(pet));

        System.out.println("Animal <- Dog: "
                + Animal.class.isAssignableFrom(Dog.class));
        System.out.println("Dog <- Animal: "
                + Dog.class.isAssignableFrom(Animal.class));
        System.out.println("Tagged <- Dog: "
                + Tagged.class.isAssignableFrom(Dog.class));
        System.out.println("Dog <- Dog: "
                + Dog.class.isAssignableFrom(Dog.class));
    }
}
~~~

~~~bash
javac --release 17 TypeCheckComparison.java
java TypeCheckComparison
~~~

Stdout:

~~~text
exact Dog: true
exact Animal: false
instanceof Animal: true
instanceof Tagged: true
instanceof Cat: false
null instanceof Animal: false
isInstance Animal: true
isInstance Cat: false
Animal <- Dog: true
Dog <- Animal: false
Tagged <- Dog: true
Dog <- Dog: true
~~~

Because `pet` references `new Dog()`, `pet.getClass()` is **precisely `Dog.class`**. That does not prevent `Dog` from becoming an instance of its superclass `Animal` and interface `Tagged`. `Cat` is a sibling subtype, incompatible with `Dog`. The `isAssignableFrom` operation in the last four lines does not read `pet`: it checks the static relation between type tokens.

## 7. Null: Four Perspectives That Must Be Kept Distinct

| Operation | With `null` | Result |
| --- | --- | --- |
| `null instanceof String` | The `null` expression is a null reference | `false` |
| `String.class.isInstance(null)` | Null object argument | `false` |
| `String.class.cast(null)` | Casting null to a reference type | Returns `null` |
| `((Object) null).getClass()` | Calling an instance method on null | `NullPointerException` |
| `String.class.isAssignableFrom(null)` | The `Class<?>` argument is null | `NullPointerException` |
| `String.class == null` | A class literal is non-null | `false` |

Note that `Class<?> target = null; target.isInstance(value)` also throws `NullPointerException` because the **receiver** is null, not because of `value`.

In a dynamic validator, type checking often needs to distinguish "`null` is accepted according to a business rule" from "does the object have the right type":

~~~java
static boolean matches(Class<?> target, Object value, boolean nullable) {
    if (target == null) {
        throw new IllegalArgumentException("target required");
    }
    return value == null ? nullable : target.isInstance(value);
}
~~~

This is an **illustrative method**, not a standalone Java file. `isInstance(null)` returning false by default is a Java rule; accepting null is an **application policy** that must be handled separately.

## 8. Interfaces, Abstract Classes, and Polymorphism

Class/interface checking methods do not require the target to be a concrete class:

~~~java
interface Service { }
abstract class BaseService implements Service { }
final class LiveService extends BaseService { }
~~~

In the context of the declarations above:

~~~java
Service.class.isAssignableFrom(LiveService.class);     // true
BaseService.class.isAssignableFrom(LiveService.class); // true
LiveService.class.isAssignableFrom(BaseService.class); // false
~~~

`Service.class.isInstance(new LiveService())` → `true`, even though an object of interface `Service` cannot be instantiated directly. A class can implement multiple interfaces; the assignability relationship follows **type**, not whether the target itself can be instantiated.

For interfaces `A` and `B` with no `extends` between them, even if there is `class C implements A, B`, `A.class.isAssignableFrom(B.class)` is still `false`. However, `A.class.isInstance(new C())` and `B.class.isInstance(new C())` are both `true`.

Avoid using `getClass() == BaseService.class` to check "is this a service of type BaseService?", because all subclasses are excluded. If you want to accept subclasses, use `instanceof` or `isInstance`.

## 9. Arrays: Covariance, Marker Interfaces, and Primitive Arrays

Arrays in Java are **reference types**, but their **component type** must be considered.

### 9.1. Object Arrays Are Covariant by Component Reference Type

~~~java
Object[].class.isAssignableFrom(String[].class); // true
Number[].class.isAssignableFrom(Integer[].class); // true
String[].class.isAssignableFrom(Object[].class); // false
~~~

Because `String` is a subtype of `Object` and `Integer` is a subtype of `Number`, the reference component relationship allows covariance in arrays. This rule does not imply that any object can be written into the array:

~~~java
Object[] data = new String[1];
// The following line compiles, but throws ArrayStoreException at runtime:
// data[0] = Integer.valueOf(10);
~~~

The array still remembers its runtime component type `String`. The compile-time type `Object[]` does not allow overriding that runtime constraint.

### 9.2. Primitive Arrays Are Not `Object[]`

~~~java
Object.class.isAssignableFrom(int[].class);       // true
Cloneable.class.isAssignableFrom(int[].class);    // true
java.io.Serializable.class.isAssignableFrom(int[].class); // true
Object[].class.isAssignableFrom(int[].class);     // false
int[].class.isAssignableFrom(long[].class);       // false
~~~

Every array class extends `Object` and implements the marker interfaces `Cloneable` and `Serializable`. However, `int[]` is an array holding **primitive int** values, not `Object[]`, and primitive arrays with different component types are not covariant like reference arrays.

### 9.3. Runnable Example

File **`ArrayTypeChecks.java`**:

~~~java
import java.io.Serializable;

public class ArrayTypeChecks {
    public static void main(String[] args) {
        Object textArray = new String[2];
        Object numbers = new int[2];

        System.out.println(textArray instanceof Object[]);
        System.out.println(textArray instanceof Cloneable);
        System.out.println(Object[].class.isInstance(numbers));
        System.out.println(Object.class.isAssignableFrom(int[].class));
        System.out.println(Cloneable.class.isAssignableFrom(int[].class));
        System.out.println(Serializable.class.isAssignableFrom(int[].class));
        System.out.println(Number[].class.isAssignableFrom(Integer[].class));
        System.out.println(Object[].class.isAssignableFrom(int[].class));
        System.out.println(int[].class.isAssignableFrom(long[].class));
    }
}
~~~

~~~bash
javac --release 17 ArrayTypeChecks.java
java ArrayTypeChecks
~~~

Stdout in order:

~~~text
true
true
false
true
true
true
true
false
false
~~~

Important point: `int[]` is an `Object`, `Cloneable`, and `Serializable`, yet it is not an `Object[]`. Do not use the reasoning "every array is an Object[]" when writing APIs that accept dynamic data.

## 10. Primitives, Wrappers, Boxing, and Widening: Why Do Results Differ from Java Source Assignments?

This is where the name `isAssignableFrom` most easily causes misunderstandings. This method checks **identity/widening reference conversion**, or the **exact same primitive type**; it does **not** automatically perform boxing, unboxing, primitive widening, or compile-time conversion chains to turn a primitive `int` into `long`/`Object`.

**Valid** Java source examples:

~~~java
long wide = 12;     // primitive widening: int -> long
Object boxed = 12;  // boxing int -> Integer, then widening reference
Number n = 12;      // boxing int -> Integer -> Number
~~~

Yet the type token checks:

~~~java
long.class.isAssignableFrom(int.class);       // false
Object.class.isAssignableFrom(int.class);     // false
Number.class.isAssignableFrom(int.class);     // false
Integer.class.isAssignableFrom(int.class);    // false
int.class.isAssignableFrom(int.class);        // true
Object.class.isAssignableFrom(Integer.class); // true
Number.class.isAssignableFrom(Integer.class); // true
~~~

`int.class.isInstance(Integer.valueOf(12))` → `false`, because `Integer` is a **reference object**, not a primitive value object of `int.class`. Conversely, `Integer.class.isInstance(Integer.valueOf(12))` → `true`.

**Do not broaden the interpretation of `isAssignableFrom` to mean "every assignment that can be written in Java code".** The compiler has its own conversion rules (boxing/unboxing, primitive widening, constant narrowing in certain cases); `Class.isAssignableFrom` does not simulate all of them.

## 11. Generics and Type Erasure: `Class` Does Not Carry a `List<String>` Runtime Token

Most generic type arguments are not reified as a separate runtime class:

~~~java
java.util.List<String> names =
        new java.util.ArrayList<>();
java.util.List<Integer> ages =
        new java.util.ArrayList<>();

System.out.println(names.getClass() == ages.getClass()); // true
System.out.println(java.util.List.class.isInstance(names)); // true
System.out.println(java.util.List.class.isInstance(ages));  // true
~~~

The three print statements above belong to **an illustrative snippet** that can be placed inside `main`, not a standalone file.

- `List.class` represents the **raw class/interface** at runtime; there is no `List<String>.class`.
- `value instanceof List<String>` cannot be used in Java 17 because a concrete parameterized type is not reifiable; `value instanceof List<?>` is valid.
- `List.class.isAssignableFrom(ArrayList.class)` returns `true` for the raw types hierarchy, without checking whether elements are `String` or `Integer`.
- `Class<?>` does not distinguish `List<String>` and `List<Integer>` from an actual object; the generic signature may be stored in **declaration metadata** (for example, `Field.getGenericType()` returns `Type`), without turning into runtime element-type validation.

If a serializer/validator needs to distinguish between `List<String>` and `List<Integer>`, pass a token of the **full type** using a mechanism such as `ParameterizedType`/type reference, and then **validate each element** when policy requires. Do not infer runtime generic arguments solely from the `getClass()` of `ArrayList`.

**Point of distinction:** Arrays have a real runtime component type (for example, `String[]`), so a store check produces `ArrayStoreException`. A generic `List<String>` does not check runtime type arguments in the same way as array covariance.

## 12. ClassLoader Impact: Two Classes with the **Same Name** Are Still Incompatible

When a plugin loader and a host loader define a class with the same binary name, each class is a different runtime type. In that case:

~~~java
hostType.getName().equals(pluginType.getName()); // may be true
hostType == pluginType;                          // false
hostType.isAssignableFrom(pluginType);           // usually false
hostType.isInstance(pluginObject);               // usually false
~~~

The assignability/instance results also depend on the actual hierarchy of the plugin class; the illustrative case below intentionally uses only two separate copies of the same class **with no inheritance connecting the two**.

### 12.1. Example with Two Defining Loaders, Runnable on Java 17+

Create two files side by side.

**`Widget.java`**:

~~~java
public class Widget {
    public Widget() { }
}
~~~

**`LoaderIdentityDemo.java`**:

~~~java
import java.io.IOException;
import java.io.InputStream;

public class LoaderIdentityDemo {
    static final class IsolatedWidgetLoader extends ClassLoader {
        IsolatedWidgetLoader() {
            super(LoaderIdentityDemo.class.getClassLoader());
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!name.equals("Widget")) {
                return super.loadClass(name, resolve);
            }
            synchronized (getClassLoadingLock(name)) {
                Class<?> result = findLoadedClass(name);
                if (result == null) {
                    result = findClass(name);
                }
                if (resolve) {
                    resolveClass(result);
                }
                return result;
            }
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!name.equals("Widget")) {
                throw new ClassNotFoundException(name);
            }
            try (InputStream in = LoaderIdentityDemo.class
                    .getClassLoader().getResourceAsStream("Widget.class")) {
                if (in == null) {
                    throw new ClassNotFoundException(name);
                }
                byte[] bytes = in.readAllBytes();
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException ex) {
                throw new ClassNotFoundException(name, ex);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Widget hostObject = new Widget();
        Class<?> hostType = Widget.class;

        Class<?> pluginType =
                new IsolatedWidgetLoader().loadClass("Widget");
        Object pluginObject =
                pluginType.getDeclaredConstructor().newInstance();

        System.out.println("same name: "
                + hostType.getName().equals(pluginType.getName()));
        System.out.println("same Class: " + (hostType == pluginType));
        System.out.println("same defining loader: "
                + (hostType.getClassLoader()
                        == pluginType.getClassLoader()));
        System.out.println("host type accepts plugin: "
                + hostType.isInstance(pluginObject));
        System.out.println("plugin type accepts host: "
                + pluginType.isInstance(hostObject));
        System.out.println("assignable across loaders: "
                + hostType.isAssignableFrom(pluginType));
        System.out.println("plugin accepts own object: "
                + pluginType.isInstance(pluginObject));
        System.out.println("pluginObject instanceof Widget: "
                + (pluginObject instanceof Widget));
    }
}
~~~

~~~bash
javac --release 17 Widget.java LoaderIdentityDemo.java
java -cp . LoaderIdentityDemo
~~~

Stdout:

~~~text
same name: true
same Class: false
same defining loader: false
host type accepts plugin: false
plugin type accepts host: false
assignable across loaders: false
plugin accepts own object: true
pluginObject instanceof Widget: false
~~~

**Why?** The custom loader chooses to **define separately** only for `Widget`; for the remaining names, it delegates to the parent as usual. When Java code uses `Widget.class` or `new Widget()` on the host side, they belong to the application loader. When `IsolatedWidgetLoader` reads the `Widget.class` bytes and calls `defineClass`, the VM creates a **new** type in the new loader namespace. Both have the same `getName()`, yet `==`/`isInstance`/`isAssignableFrom` according to runtime identity differ.

**Demo limitations:** This class loader is only to demonstrate identity, not a production plugin implementation. Real plugins require designing package ownership, dependency delegation, exception/linking, concurrent loading, resource lookup, module access, lifecycle/unloading, and trust boundaries. Do not blindly make every class child-first: a shared interface/API from the host usually must be visible to both sides under the **same defining loader**.

### 12.2. The "`Widget cannot be cast to Widget`" Error

Suppose the plugin creates `pluginObject`. The cast below can compile because the source variable is `Object`, but at runtime it throws `ClassCastException`:

~~~java
// Widget hostView = (Widget) pluginObject;  // fails at runtime
~~~

The error message sometimes displays duplicate class names along with loader/module information. This is not a paradox: the same name does **not** mean the two runtime types are the same. The fix is usually to share the right interface/DTO/contract with the parent, or avoid casting objects across a classloader boundary; check for duplicate dependency copies between host/plugin and deployment locations.

## 13. `Class.cast` and `Class.asSubclass`: When You Need to Move from Checking to Action

Two related APIs, very useful in registry/plugin frameworks:

~~~java
Class<? extends Number> accepted =
        Integer.class.asSubclass(Number.class);

Number n = accepted.cast(Integer.valueOf(5));
~~~

- `Class.cast(Object)` performs a checked cast from an object according to the runtime class, **returns `null` if the argument is null**, or throws `ClassCastException` if the object is incompatible.
- `Class.asSubclass(Class<U>)` verifies **whether a `Class` is a subtype of U**; if so, it returns a typed token `Class<? extends U>`; if not, it throws `ClassCastException`.
- `isInstance`/`isAssignableFrom` return a boolean for branching; `cast`/`asSubclass` are useful when you need to continue with a safer static generic type.

Example generic method for filtering:

~~~java
static <T> T castOrNull(Class<T> target, Object candidate) {
    return target.isInstance(candidate)
            ? target.cast(candidate)
            : null;
}
~~~

This is a non-standalone illustrative method. If the business domain gives a null candidate a different meaning from "type mismatch", do not collapse both situations into `null`; use `Optional`, a result with status, or an explicit null check.

### 13.1. Choosing the Right API in a Registry

Suppose a plugin registry receives `Class<?> providedType` and the contract `Service.class`:

~~~java
if (!Service.class.isAssignableFrom(providedType)) {
    throw new IllegalArgumentException("Expected Service subtype");
}
Class<? extends Service> serviceType =
        providedType.asSubclass(Service.class);
~~~

This is a **snippet depending on the project-defined `Service` interface**. This check only verifies inheritance/interface identity. It does **not guarantee** that the class has a public constructor, that the class is non-abstract, that the module allows reflective invocation, that dependencies are present, or that the plugin is trustworthy.

Once you have an instance returned by a plugin:

~~~java
if (Service.class.isInstance(pluginObject)) {
    Service service = Service.class.cast(pluginObject);
}
~~~

These snippets depend on the exact **same `Service.class`** across the loader boundary. If the host and plugin each define their own `Service`, `isAssignableFrom` can return `false` even though the `Service` name on both sides is identical.

## 14. Common Misconceptions

| Misconception | What is true |
| --- | --- |
| `getClass() == Parent.class` accepts all subtypes | Only true for the **exact runtime class**; use `instanceof`/`isInstance` for subtypes |
| `a.getClass().getName().equals(b.getClass().getName())` means the same type | False if the defining class loader differs |
| `Target.isAssignableFrom(Source)` reads as "Target can be assigned to Source" | Wrong direction; it must be read as **"Source can be assigned to Target"** |
| `isAssignableFrom` simulates all Java assignment conversions | False: no boxing/unboxing or widening primitives |
| `int.class.isInstance(1)` should be true | False: when passed to an `Object` API, `1` is boxed; a primitive `Class` has no object instances |
| `List.class.isInstance(list)` verifies that elements are all String | False: type erasure |
| `null instanceof T` throws an error | False: it returns false; errors occur when dereferencing null |
| `isAssignableFrom(null)` returns false | False: `NullPointerException` |
| `Object[].class.isAssignableFrom(int[].class)` is true because `int[]` is an Object | False: a primitive array is an Object, but not an `Object[]` |
| Two different loaders always create two different `Class` objects | False if both delegate to the same defining loader |
| Does `instanceof` also compare classloaders? | Checking a runtime type uses the identity determined by the loader; it does not directly compare loader objects as values |
| `Class.forName` never initializes the class | False: the default single-string overload requests initialization; the overload with `initialize=false` can avoid that requirement |

## 15. Diagnostic Procedure When a Type Comparison Unexpectedly Returns `false`

1. **Verify the actual object:** `obj == null`? If not, print `obj.getClass().getName()` and `obj.getClass().getClassLoader()`.
2. **Verify the target:** print `target.getName()`, `target.getClassLoader()`, and `target.getModule()`, compared against the source/runtime object.
3. **Check the assignability direction:** `Target.class.isAssignableFrom(Source.class)`, avoiding writing it backward.
4. **Check the classpath/plugin graph:** Are there JARs with duplicate FQCNs? Is there a child-first loader or a new module layer? Does parent delegation return a different type than expected?
5. **Check arrays/primitives/generics:** primitive wrappers, boxing/unboxing, `Object[]` vs `int[]`, and erased generic arguments.
6. **Check compilation vs. runtime:** the compiler may forbid `instanceof` due to an inconvertible cast, whereas a dynamic API checking runtime class tokens may return false; this is not necessarily a bug.
7. **Prefer contracts over guessing names:** identify a common interface/abstract parent actually defined by the same loader; use `==` when an exact class check is needed, and use `instanceof`/`isInstance` when polymorphism is needed.

Helper logging snippet:

~~~java
static void explain(Class<?> target, Object source) {
    if (source == null) {
        System.out.println("source is null");
        return;
    }
    Class<?> actual = source.getClass();
    System.out.println("actual: " + actual.getName());
    System.out.println("actual loader: " + actual.getClassLoader());
    System.out.println("target: " + target.getName());
    System.out.println("target loader: " + target.getClassLoader());
    System.out.println("exact: " + (actual == target));
    System.out.println("instance: " + target.isInstance(source));
    System.out.println("assignable: " + target.isAssignableFrom(actual));
}
~~~

This illustrative method must be placed inside a class and passed `target != null`. When logging in production, restrict printing object values/paths that may contain sensitive information; loader metadata is used to diagnose type identity relationships.

## 16. Self-Check Exercises

Given:

~~~java
interface Pet { }
class Animal { }
class Dog extends Animal implements Pet { }
class Cat extends Animal { }
Object dog = new Dog();
~~~

The declarations above are placed in the same appropriate Java scope.

1. `dog instanceof Animal` → **true**, because Dog extends Animal.
2. `dog.getClass() == Animal.class` → **false**, because the exact class is Dog.
3. `Pet.class.isInstance(dog)` → **true**, because Dog implements Pet.
4. `Animal.class.isAssignableFrom(Dog.class)` → **true**; reversing the direction → **false**.
5. `Cat.class.isInstance(dog)` → **false**; sharing a superclass does not make two sibling classes compatible.
6. `Object[].class.isAssignableFrom(String[].class)` → **true**, but `Object[].class.isAssignableFrom(int[].class)` → **false**.
7. `long.class.isAssignableFrom(int.class)` → **false**, even though `long x = 1` is valid.
8. If `Dog` is defined separately in two loaders, and the `Dog` tokens on both sides have the same `getName()`, is `==` true? **No**.
9. If `Class<?> runtimeType = Dog.class`, what should be used to check `dog`? **`runtimeType.isInstance(dog)`**.
10. If you only have `Class<?> source, target`, what should you check before accepting the source type? **`target.isAssignableFrom(source)`**.

## 17. Official References

- [`java.lang.Class` API (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html) — official contract for `isInstance`, `isAssignableFrom`, `getClassLoader`, `cast`, `asSubclass`, primitive, and array class tokens.
- [JLS `15.20.2` — Type Comparison Operator `instanceof` (Java SE 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2) — compile-time rules, null, and runtime checks in Java 17.
- [JLS `5` — Conversions and Contexts (Java SE 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html) — identity, widening reference, boxing/unboxing, and casting.
- [JLS `4.7` — Reifiable Types (Java SE 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7) — why `List<String>` cannot be used as a runtime token and `List<?>` can be checked.
- [JVMS `5.3` — Creation and Loading (Java SE 25)](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3) — type identity by **binary name + defining loader**, array classes, and initiating/defining loaders.
- [`ClassLoader` API (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html) — delegation and `defineClass`, context for plugin isolation.

**Remember three sentences:** `==` between `Class` checks **exact type identity**; `instanceof`/`Class.isInstance` checks **whether an object belongs to a type (including subtypes)**; `Target.class.isAssignableFrom(Source.class)` checks **the assignment relationship Source → Target**. All three rely on **runtime type identity**, which for ordinary classes includes the **defining class loader**.
