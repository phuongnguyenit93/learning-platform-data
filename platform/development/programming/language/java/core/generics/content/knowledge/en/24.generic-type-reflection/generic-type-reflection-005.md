# `TypeVariable`: Declaration Site and Bounds in Java Reflection

In Java Generics, a type parameter such as `T`, `E`, or `U` can be **declared by a class, interface, method, or constructor**. When using reflection to inspect that type parameter, Java represents it with the **`java.lang.reflect.TypeVariable<D extends GenericDeclaration>`** interface.

For example:

```java
class Box<T extends Number> {
    T value;

    <U extends CharSequence> U echo(U input) {
        return input;
    }
}
```

Here:

- `T` is a **type variable declared by class `Box`**, with upper bound `Number`.
- `U` is a **type variable declared by method `echo`**, with upper bound `CharSequence`.
- `T` and `U` are not names of concrete runtime classes. They represent **type variables of declarations**; how type arguments are bound at use sites is checked by the compiler under the generic contract.

Using reflection:

```java
java.lang.reflect.TypeVariable<?> t =
        Box.class.getTypeParameters()[0];

System.out.println(t.getName()); // T
System.out.println(t.getBounds()[0].getTypeName());
// java.lang.Number
```

**The two core questions when encountering a `TypeVariable` are: "Who declared this type variable?" and "What are its upper bounds?"** The answers come from `getGenericDeclaration()` and `getBounds()`, not from guessing based on the name `T` or a runtime object.

## 1. Position of `TypeVariable` in the `Type` System

`java.lang.reflect.Type` is the common interface for type descriptions provided by reflection. Typical forms:

| Reflection Object | Represents | Example |
| --- | --- | --- |
| `Class<?>` | Runtime class/interface/primitive/array with an appropriate component type | `String.class`, `Number.class`, `String[].class` |
| `ParameterizedType` | Parameterized type of a declaration | `List<String>`, `Comparable<T>` |
| **`TypeVariable<D>`** | **Type variable declared by a generic declaration** | `T` in `Box<T>`, `U` in `<U> U echo(U)` |
| `WildcardType` | Wildcard type argument | `? extends Number`, `? super Integer` |
| `GenericArrayType` | Array with a non-reifiable generic component type | `T[]`, `List<String>[]` |

`TypeVariable` is also related to `AnnotatedElement`, since annotations on a **type parameter declaration** can be read (when the annotation has appropriate retention).

Do not conflate:

```java
class Example<T extends Number> {
    java.util.List<T> values;
}
```

- `T` is a **`TypeVariable`**.
- `List<T>` is a **`ParameterizedType`** on the outside; the element of `getActualTypeArguments()` is the `TypeVariable` for `T`.
- `Number.class` is a **`Class`** describing the stated upper bound.
- `T[]` in a declaration is a **`GenericArrayType`** on the outside, and the generic component type inside is the `TypeVariable`.

A reflection tree can contain multiple nested kinds of `Type`. Do not cast every `Type` value to `Class`.

## 2. What Does the Signature `TypeVariable<D extends GenericDeclaration>` Say?

You can picture the key members of the interface:

```java
// API SKETCH, not source code redefining TypeVariable:
interface TypeVariable<D extends java.lang.reflect.GenericDeclaration>
        extends java.lang.reflect.Type,
                java.lang.reflect.AnnotatedElement {

    java.lang.reflect.Type[] getBounds();
    D getGenericDeclaration();
    String getName();
    java.lang.reflect.AnnotatedType[] getAnnotatedBounds();
}
```

The parameter `D` on the **`TypeVariable<D>` interface itself** specifies **the kind of reflection object representing the declaration site**. `GenericDeclaration` is implemented by `Class`, `Method`, and `Constructor` for the corresponding cases.

For example, you may encounter `TypeVariable<Class<MyBox>>` when reading a class's type parameters and `TypeVariable<Method>` when reading from a method. In general processing code, `TypeVariable<?>` suffices if you do not need to retain the exact declaration kind at compile time.

The members play different roles:

- `getName()`: source name of the type variable, e.g. `T`, `E`, `K`.
- `getGenericDeclaration()`: the **Class/Method/Constructor object that declared** the type variable, not a runtime generic instance.
- `getBounds()`: list of **upper bounds** as `Type[]`, in the order expressed in the declaration.
- `getAnnotatedBounds()`: upper bounds as **`AnnotatedType[]`**, for reading type-use annotations on bounds.
- APIs from `AnnotatedElement`, such as `getAnnotation(...)`, allow reading annotations placed on the **type parameter declaration itself**, when compatible with `@Target` and `@Retention`.

**Note:** the snippet above only illustrates the shape of the API. In real programs, you import and use the built-in `java.lang.reflect.TypeVariable`, rather than defining an interface of the same name.

## 3. Who Can Declare a Type Variable?

A notable feature of Java reflection: a **generic declaration** can be a class/interface, a method, or a constructor.

### 3.1. Generic Class/Interface

```java
class Pair<K, V> {
    K key;
    V value;
}
```

Reading the type variables declared by the class:

```java
java.lang.reflect.TypeVariable<?>[] variables =
        Pair.class.getTypeParameters();

for (java.lang.reflect.TypeVariable<?> variable : variables) {
    System.out.println(variable.getName());
}
```

Output:

```text
K
V
```

`Pair.class.getTypeParameters()` returns the type parameters **declared directly on `Pair`**, in order; it does not return the concrete type arguments of a `Pair<String, Integer>` instance.

A generic interface is also a generic declaration:

```java
interface Repository<ID, ENTITY> {
    ENTITY find(ID id);
}
```

`Repository.class.getTypeParameters()` yields the two variables `ID` and `ENTITY`.

### 3.2. Generic Method

```java
class Utilities {
    static <T extends Number> T same(T value) {
        return value;
    }
}
```

Reading from the `Method` object itself:

```java
java.lang.reflect.Method method =
        Utilities.class.getDeclaredMethod("same", Number.class);

java.lang.reflect.TypeVariable<?> t =
        method.getTypeParameters()[0];

System.out.println(t.getGenericDeclaration().equals(method)); // true
```

**Why look up the method using `Number.class` instead of `T.class`?** Because `T` has bound `Number`, so the erasure of parameter `T` in the descriptor used to look up `getDeclaredMethod` is `Number`.

### 3.3. Generic Constructor

A class's constructor can declare its own type parameter:

```java
class Message {
    <T extends CharSequence> Message(T text) {
        System.out.println(text);
    }
}
```

Reflection example:

```java
java.lang.reflect.Constructor<?> ctor =
        Message.class.getDeclaredConstructor(CharSequence.class);

java.lang.reflect.TypeVariable<?> t =
        ctor.getTypeParameters()[0];

System.out.println(t.getGenericDeclaration().equals(ctor)); // true
```

A constructor's type parameter is **distinct from** the class's type parameters, even when the constructor resides in a generic class. A constructor's `getTypeParameters()` returns only the parameters that the **constructor itself declares**.

**Important:** when comparing `Method`/`Constructor` objects returned by reflection, use `.equals()` rather than relying on reference equality `==`. Two reflection queries can return different wrapper objects representing the same declaration. For a class object such as `Box.class`, the `Class` object represents the same class identified by a given class loader.

## 4. `getGenericDeclaration()`: Same Name Does Not Mean the Same Type Variable

Java allows a generic method to reuse the class's name `T`; the method-level `T` shadows the class-level `T` within the method scope:

```java
class Container<T extends Number> {
    T classValue;

    <T extends CharSequence> T echo(T value) {
        return value;
    }
}
```

Here there are **two independent type variables**:

- `T` of `Container<T extends Number>`, declared by **class `Container`**.
- `T` of `<T extends CharSequence> T echo(T)`, declared by **method `echo`**.

Comparing by name is wrong:

```java
// Two TypeVariables read from class and method:
// classT.getName().equals(methodT.getName()) -> true
// classT.equals(methodT)                   -> false
```

There is no contradiction here: **the name `T` is just a label**, like two different methods having local variables both named `value`. To understand a type variable, you must examine its **generic declaration** and declaration site.

If you are building a map of generic types for a framework, do not use the string `"T"` as a global key. Type variables sharing a name across two classes, two methods, or two constructors have separate identities and bounds.

### The Right Way to Compare

```java
boolean sameDeclaration =
        classT.getGenericDeclaration()
              .equals(methodT.getGenericDeclaration());

boolean sameVariable = classT.equals(methodT);
```

These results reflect **declaration identity**, not just the name. `TypeVariable` implements an `equals`/`hashCode` contract representing type variables of the same generic declaration; do not rely on `==` object identity of reflection wrappers.

## 5. `getBounds()`: Reading Upper Bounds and the Default `Object`

Consider:

```java
class Simple<T, N extends Number> {}
```

If `T` has no explicit `extends`, it has an **implicit upper bound of `Object`**. When read via reflection:

```java
java.lang.reflect.TypeVariable<?>[] vars =
        Simple.class.getTypeParameters();

System.out.println(vars[0].getBounds()[0].getTypeName());
System.out.println(vars[1].getBounds()[0].getTypeName());
```

Output:

```text
java.lang.Object
java.lang.Number
```

Therefore, `getBounds()` does not return an empty array merely because you omitted `extends`.

### Upper Bounds Differ from Actual Type Arguments

With `N extends Number`:

- **Bound:** `Number`, describing the upper limit on type arguments that can be bound to `N`.
- **Actual type argument:** e.g. `Integer` at the use site `Simple<String, Integer>`.
- **Type variable:** `N`, still represented as a `TypeVariable` when reading the `Simple` declaration.

Reflection does not turn `getBounds()` into `Integer.class` just because an instance `Simple<String, Integer>` exists somewhere.

Similarly, `T extends Number` does not mean `T` always equals `Number`: `Integer`, `Double`, and suitable subclasses can also be type arguments.

## 6. Multiple Bounds: `T extends A & B & C`

Java allows declaring a type variable with **intersection bounds**:

```java
class Numeric<T extends Number & Comparable<T>> {
    T value;
}
```

`T` must satisfy both constraints:

1. Be a subtype of `Number`.
2. Implement `Comparable<T>` appropriately.

Reflection:

```java
java.lang.reflect.TypeVariable<?> variable =
        Numeric.class.getTypeParameters()[0];

for (java.lang.reflect.Type bound : variable.getBounds()) {
    System.out.println(bound.getTypeName());
}
```

Output:

```text
java.lang.Number
java.lang.Comparable<T>
```

`getBounds()` returns **each bound in order**. There is no separate `Class` named `Number & Comparable<T>`. The intersection structure is stored as **multiple `Type` elements**, where:

- `Number` is typically a `Class`.
- `Comparable<T>` is typically a `ParameterizedType` whose type argument `T` is a `TypeVariable` referencing itself.

### Position of Class Bound and Interface Bounds

If there is a class bound, it comes first; interface bounds follow, joined by `&`. You cannot declare multiple independent class bounds such as `T extends Number & String`.

If the first bound is an interface, the erasure of `T` is based on that **first bound**. For example:

```java
class Task<T extends Runnable & AutoCloseable> {
    T task;
}
```

The erasure of `T` uses `Runnable`, rather than automatically becoming `Object` simply because both bounds are interfaces.

**The order of bounds affects erasure** and can affect bytecode signatures/source compatibility constraints. Do not reorder bounds just because they look equivalent in terms of subtyping without considering the impact on compiled APIs.

### Bound Constraints Do Not Become Type Arguments

If `T extends Comparable<T>`, `getBounds()[0]` can be a `ParameterizedType` representing `Comparable<T>`. Do not cast it to `Class` and do not mistake the `T` inside for a concrete runtime class.

## 7. Type Erasure: The First Bound Determines the Runtime View

When generic types are erased, Java uses the erasure of the **leftmost bound** for a type variable. With:

```java
class Envelope<T extends Number & Comparable<T>> {
    T number;
}
```

You can observe two layers of information:

```java
java.lang.reflect.Field f =
        Envelope.class.getDeclaredField("number");

System.out.println(f.getType().getTypeName());
System.out.println(f.getGenericType().getTypeName());
```

Output:

```text
java.lang.Number
T
```

- `Field.getType()` returns the `Class` of the erased type: `Number`.
- `Field.getGenericType()` retains the declaration description as a `TypeVariable`: `T`.

This is a critical boundary: **preserving the generic signature via reflection does not mean an `Envelope<Integer>` instance has a separate runtime field class `Integer`**. The normal runtime class still uses the erasure `Number`.

For a method:

```java
<T extends CharSequence & Comparable<T>> T echo(T value)
```

`Method.getReturnType()` can return `CharSequence.class`; `Method.getGenericReturnType()` returns the `TypeVariable` named `T`. Likewise, `getParameterTypes()` uses erasure, while `getGenericParameterTypes()` can represent `T`.

**Do not equate a bound with an actual type argument:** `CharSequence` is an upper bound, which does not mean every call to `echo` returns an object of runtime class `CharSequence` (which is an interface).

## 8. `getAnnotatedBounds()` vs. Annotations on the Type Parameter Itself

Java supports placing annotations in two positions with different meanings:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_PARAMETER)
@interface NamedParameter {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NumberBound {}

class Box<@NamedParameter T extends @NumberBound Number> {}
```

`@NamedParameter` is placed **on the declaration of type parameter `T`**. `@NumberBound` is placed **on the type use `Number` serving as a bound**.

Reflection:

```java
java.lang.reflect.TypeVariable<?> variable =
        Box.class.getTypeParameters()[0];

boolean onParameter =
        variable.isAnnotationPresent(NamedParameter.class);

boolean onFirstBound =
        variable.getAnnotatedBounds()[0]
                .isAnnotationPresent(NumberBound.class);
```

Both are `true` in the example above.

Distinguish:

- `TypeVariable.getAnnotations()` and methods from `AnnotatedElement` report annotations on the **type parameter declaration**.
- `getAnnotatedBounds()` returns `AnnotatedType[]` containing annotations on **the types used as bounds**.
- `getBounds()` returns `Type[]`, which has no API to directly read annotations per type-use position.

To reflect annotations at runtime, an appropriate `RetentionPolicy.RUNTIME` is required. If an annotation exists only in source or class files without runtime retention, do not expect reflection calls like the above to see it.

### An Annotated Bound Does Not Replace the Bound

An `AnnotatedType` provides extra annotation metadata at a type position, while you can still call `getType()` to get the underlying `Type`. For instance:

```java
java.lang.reflect.AnnotatedType annotated =
        variable.getAnnotatedBounds()[0];

java.lang.reflect.Type underlying = annotated.getType();
```

`underlying` can be `Number.class`. When building a schema or framework that needs annotations, preserve both the **`Type` structure** and the **annotations at their exact positions**.

## 9. Complete Java 17+ Program: Class, Method, Constructor, and Bounds

Save the code below into **`TypeVariableDemo.java`**:

```java
import java.lang.annotation.*;
import java.lang.reflect.*;
import java.util.*;

public class TypeVariableDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_PARAMETER)
    @interface NamedParameter {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface NumberBound {}

    static class Envelope<
            @NamedParameter T extends @NumberBound Number & Comparable<T>,
            E> {
        T number;
        List<T> numbers;
        E other;

        public <U extends CharSequence> Envelope(U label) {}

        // echo's T is declared by the method, not Envelope.
        public <T extends CharSequence & Comparable<T>> T echo(T value) {
            return value;
        }
    }

    static class IntegerEnvelope extends Envelope<Integer, String> {
        IntegerEnvelope() {
            super("ok");
        }
    }

    static String bounds(TypeVariable<?> variable) {
        return String.join(
                " & ",
                Arrays.stream(variable.getBounds())
                        .map(Type::getTypeName)
                        .toArray(String[]::new));
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        TypeVariable<?> classT =
                Envelope.class.getTypeParameters()[0];
        TypeVariable<?> classE =
                Envelope.class.getTypeParameters()[1];

        // Reflective lookup by erased parameter type CharSequence.
        Method method = Envelope.class.getDeclaredMethod(
                "echo", CharSequence.class);
        TypeVariable<?> methodT = method.getTypeParameters()[0];

        Constructor<?> ctor = Envelope.class.getDeclaredConstructor(
                CharSequence.class);
        TypeVariable<?> ctorU = ctor.getTypeParameters()[0];

        System.out.println("Class T belongs to Envelope: "
                + classT.getGenericDeclaration().equals(Envelope.class));
        System.out.println("Class T bounds: " + bounds(classT));
        System.out.println("Class T annotation: "
                + classT.isAnnotationPresent(NamedParameter.class));
        System.out.println("First bound annotation: "
                + classT.getAnnotatedBounds()[0]
                        .isAnnotationPresent(NumberBound.class));

        System.out.println("Class E implicit bound: "
                + bounds(classE));

        System.out.println("Method T belongs to echo: "
                + methodT.getGenericDeclaration().equals(method));
        System.out.println("Method T bounds: " + bounds(methodT));
        System.out.println("Same type variable name: "
                + classT.getName().equals(methodT.getName()));
        System.out.println("Same type variable identity: "
                + classT.equals(methodT));

        System.out.println("Constructor U belongs to ctor: "
                + ctorU.getGenericDeclaration().equals(ctor));
        System.out.println("Constructor U bound: " + bounds(ctorU));

        Field field = Envelope.class.getDeclaredField("number");
        System.out.println("Field erased type: "
                + field.getType().getTypeName());
        System.out.println("Field generic type: "
                + field.getGenericType().getTypeName());

        ParameterizedType list = (ParameterizedType)
                Envelope.class.getDeclaredField("numbers")
                        .getGenericType();
        System.out.println("List argument is class T: "
                + list.getActualTypeArguments()[0].equals(classT));

        ParameterizedType parent = (ParameterizedType)
                IntegerEnvelope.class.getGenericSuperclass();
        System.out.println("Subclass argument T: "
                + parent.getActualTypeArguments()[0].getTypeName());
        System.out.println("Subclass argument E: "
                + parent.getActualTypeArguments()[1].getTypeName());

        System.out.println("Method erased return: "
                + method.getReturnType().getTypeName());
        System.out.println("Method generic return: "
                + method.getGenericReturnType().getTypeName());
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac -encoding UTF-8 TypeVariableDemo.java
java TypeVariableDemo
```

**Standard output:**

```text
Class T belongs to Envelope: true
Class T bounds: java.lang.Number & java.lang.Comparable<T>
Class T annotation: true
First bound annotation: true
Class E implicit bound: java.lang.Object
Method T belongs to echo: true
Method T bounds: java.lang.CharSequence & java.lang.Comparable<T>
Same type variable name: true
Same type variable identity: false
Constructor U belongs to ctor: true
Constructor U bound: java.lang.CharSequence
Field erased type: java.lang.Number
Field generic type: T
List argument is class T: true
Subclass argument T: java.lang.Integer
Subclass argument E: java.lang.String
Method erased return: java.lang.CharSequence
Method generic return: T
```

Explanation of the output groups:

1. **Class-level `T`** belongs to `Envelope.class`, has two upper bounds `Number` and `Comparable<T>`; the first bound has its own annotation.
2. **Class-level `E`** has no explicit `extends`, yet `getBounds()` still reflects the implicit upper bound `Object`.
3. **Method-level `T`** belongs to `echo`; it has the same name as class-level `T`, but is a **different declaration's** type variable so `equals` returns `false`.
4. **Constructor-level `U`** belongs to the constructor, with upper bound `CharSequence`. `getDeclaredConstructor(CharSequence.class)` relies on the erasure of parameter `U`.
5. **Field `T number`** has erased type `Number`, while its generic type is `T`. Field `List<T> numbers` has its reflected type argument pointing directly to class-level `T`.
6. **Subclass `IntegerEnvelope`** explicitly declares `extends Envelope<Integer, String>`, so `getGenericSuperclass()` gives a `ParameterizedType` with two concrete actual type arguments. That **does not alter** the `TypeVariable` declared on `Envelope`.
7. **The return type of method `echo`** has erasure `CharSequence`, while generic return `T` is the method's own type variable.

The program uses APIs built into Java 17 and needs no external libraries.

## 10. When a Subclass Chooses a Concrete Type: Do Not Confuse `TypeVariable` with Actual Type Argument

Consider:

```java
class Base<T> {}
class Child extends Base<String> {}
```

There are two **different** sources of information:

```java
java.lang.reflect.TypeVariable<?> parameter =
        Base.class.getTypeParameters()[0];

java.lang.reflect.Type actual =
        ((java.lang.reflect.ParameterizedType)
                Child.class.getGenericSuperclass())
                .getActualTypeArguments()[0];
```

- `parameter` is **`T` declared by `Base`**. `parameter.getGenericDeclaration()` points to `Base`.
- `actual` is **`String` used by `Child` when extending `Base<String>`**. In this example it is the `Class` corresponding to `String.class`.

If a framework wants to know which type argument was bound to `T` in the context of `Child`, it must **map `Base`'s declared type variable to the type argument on the inheritance edge**. A standalone `TypeVariable` does not hold a single `String` answer for every usage of `Base`.

### Multiple Inheritance Levels Require Resolving Type Bindings

```java
class Base<T> {}
class Middle<U> extends Base<java.util.List<U>> {}
class Child extends Middle<String> {}
```

To deduce the type argument of `Base<T>` from `Child`, a tool must follow the chain:

```text
Child
  extends Middle<String>
      U -> String
  Middle<U> extends Base<List<U>>
      T -> List<U>
  => in Child context: T -> List<String>
```

You cannot just read `Base.class.getTypeParameters()[0].getBounds()` and immediately get `List<String>`. `getBounds()` only gives the upper constraint of `T`, not the **actual type argument chosen by a subtype**.

Libraries such as ORMs, serializers, and dependency-injection frameworks often need to resolve these mappings to infer schemas or property types in an inheritance context.

## 11. Limitations of `TypeVariable` and Type Erasure

Several conclusions to remember:

**Cannot recover type arguments from an ordinary instance.**

```java
class Box<T> {}

Box<String> a = new Box<>();
Box<Integer> b = new Box<>();

boolean same = a.getClass() == b.getClass(); // true
```

Both instances share the same runtime class `Box`. Even though `Box.class.getTypeParameters()` returns variable `T`, it cannot answer "instance `a` chose `String` while instance `b` chose `Integer`".

**No ordinary `T.class` or `new T[]`.**

```java
class Holder<T> {
    void inspect(Object value) {
        // Class<?> type = T.class;        // DOES NOT COMPILE
        // boolean ok = value instanceof T; // DOES NOT COMPILE
        // T[] items = new T[3];          // DOES NOT COMPILE
    }
}
```

These are limitations of non-reifiable type variables, not solved by reflecting `T` into a `TypeVariable`.

**Bounds only give an upper limit.** With `T extends Number`, the fact that an object is a `Number` does not prove it is the specific subtype `T` the caller expects. A cast to the erasure might succeed on a `Double` while the caller expects `Integer`, causing the failure to surface later.

**Generic signatures are declaration metadata.** Reflection preserves `T` or `Comparable<T>` on declarations, yet does not scan data or validate every element of a generic collection at runtime.

If you need to check a concrete class supplied by the caller, you can accept a `Class<T>` token:

```java
static <T> boolean accepts(Class<T> expected, Object value) {
    return expected.isInstance(value);
}
```

A token helps check a concrete runtime class, though it does not carry nested generic type arguments like `Map<String, List<Integer>>` via a single `Class` mechanism.

## 12. `TypeVariable` vs. `WildcardType`: Two Different Meanings

It is easy to confuse `T extends Number` with `? extends Number` because both contain `extends`.

```java
class Example<T extends Number> {
    T value;
    java.util.List<? extends Number> readings;
}
```

They differ:

- **`T extends Number`** is a **type parameter declaration**, naming `T` so multiple positions within the same generic declaration can relate to one another. Reflection represents `T` as a `TypeVariable`.
- **`? extends Number`** is a **wildcard type argument** at the use site of a parameterized type. Reflection represents that wildcard as a `WildcardType`.

Field `value` has `getGenericType()` as `TypeVariable`. Field `readings` has `getGenericType()` as `ParameterizedType` for `List<? extends Number>`, and only the element `getActualTypeArguments()[0]` is a `WildcardType`.

| Question | `TypeVariable` | `WildcardType` |
| --- | --- | --- |
| Has a programmer-declared name? | Yes, such as `T`, `U` | No type parameter name |
| Has `getGenericDeclaration()`? | Yes | No |
| Has `getBounds()`? | Yes, upper bounds | Uses `getUpperBounds()` and `getLowerBounds()` |
| Can link multiple positions via the same name/declaration? | Yes, the same type variable | A wildcard is a type argument at a use site |
| Example | `<T extends Number>` | `List<? extends Number>` |

Do not apply `((TypeVariable<?>) type)` to anything that has `extends`. Check the actual `Type` kind.

## 13. Not Every `Type[]` from Reflection Contains `Class`

Common buggy code:

```java
java.lang.reflect.TypeVariable<?> t =
        SomeClass.class.getTypeParameters()[0];

for (java.lang.reflect.Type bound : t.getBounds()) {
    // Class<?> boundClass = (Class<?>) bound; // UNSAFE
}
```

With `T extends Number & Comparable<T>`, the bound `Number` is a `Class`, whereas `Comparable<T>` is a `ParameterizedType`.

If you only want to print names:

```java
for (java.lang.reflect.Type bound : t.getBounds()) {
    System.out.println(bound.getTypeName());
}
```

If structural analysis is needed, branch by kind:

```java
static void inspectBound(java.lang.reflect.Type bound) {
    if (bound instanceof Class<?> c) {
        System.out.println("Class bound: " + c.getName());
    } else if (bound instanceof java.lang.reflect.ParameterizedType p) {
        System.out.println("Parameterized bound: "
                + p.getRawType().getTypeName());
    } else if (bound instanceof java.lang.reflect.TypeVariable<?> v) {
        System.out.println("Variable bound: " + v.getName());
    } else {
        System.out.println("Other bound: " + bound.getTypeName());
    }
}
```

When encountering recursive structures like `T extends Comparable<T>`, a type-graph walker must perform **cycle detection**: if it keeps following type argument `T` and reading `T`'s `getBounds()` without recording visited nodes, the algorithm can loop forever. Use a set of visited nodes/declarations keyed by `TypeVariable.equals` semantics, not merely the string name `"T"`.

## 14. Caution When Building a Framework Handling Generic Type Variables

A schema resolver or serializer using reflection typically solves a larger problem than printing the name `T`:

1. **Read declarations:** obtain `TypeVariable` from `Class.getTypeParameters()`, `Method.getTypeParameters()`, or `Constructor.getTypeParameters()`.
2. **Maintain scope:** identify `getGenericDeclaration()` for each type variable. Two variables named `T` on two declarations cannot be merged into one.
3. **Read bounds as `Type` structures:** do not assume all bounds are `Class`; they can have parameterized arguments.
4. **Resolve across inheritance or method context:** retrieve actual type arguments from the `ParameterizedType` of superclasses/interfaces/owners where available, and apply `TypeVariable -> Type` mappings.
5. **Preserve annotations:** if the schema needs `@TYPE_PARAMETER` and `@TYPE_USE` annotations, read the proper APIs and positions.
6. **Detect cycles:** e.g. `Comparable<T>` referring back to `T` itself.
7. **Handle unavailable metadata:** reflected `Type` may still be a type variable or raw type; do not invent concrete type arguments for runtime objects.
8. **Separate declarations from data:** a field declared as `List<String>` does not prove the current collection contains only `String`s if the system allows raw/unchecked operations.

Deep reflection calls can throw exceptions such as `TypeNotPresentException` or `MalformedParameterizedTypeException` when parsing unresolvable/corrupt type metadata. Framework code should have an error-handling strategy rather than assuming reflected generic signatures from arbitrary external classes are always intact.

## 15. Common Mistakes

**Mistake 1 — "`TypeVariable` is the runtime class chosen for `T`."** False. It describes the type variable at its declaration site, not per-instance type arguments.

**Mistake 2 — "`getBounds()` returns actual type arguments."** False. `Number` is an upper bound, not `Integer` chosen by a caller.

**Mistake 3 — "If `extends` is omitted, `getBounds()` is empty."** False. The implicit upper bound is normally `Object`.

**Mistake 4 — "Two type variables named `T` are always equal."** False. Class-level `T` and method-level `T` have different generic declarations.

**Mistake 5 — "`getGenericDeclaration()` always returns a `Class`."** False. Methods and constructors can also declare type parameters.

**Mistake 6 — "Using `==` on `Method` objects returned by reflection is enough."** Not recommended. Compare declaration wrappers with `.equals()` when checking logical equivalence.

**Mistake 7 — "Bounds are always `Class`es."** False. `Comparable<T>` is a parameterized bound, usually represented as `ParameterizedType`.

**Mistake 8 — "The erasure of `T` is always `Object`."** False. It follows the erasure of the first bound; `T extends Number` erases to `Number`.

**Mistake 9 — "`T extends Number & Comparable<T>` creates a runtime intersection class."** False. Reflection stores two bounds; no runtime class named after the intersection is generated.

**Mistake 10 — "`getAnnotatedBounds()` and `TypeVariable.getAnnotations()` inspect the same position."** False. One reads type-use annotations on bounds; the other reads annotations on the type parameter declaration itself.

**Mistake 11 — "Having a `TypeVariable` lets you use `T.class` or `new T[]`."** False. `T` remains a non-reifiable type variable in the Java language.

**Mistake 12 — "`T extends Comparable<T>` can be walked recursively without a visited set."** False. Bounds can point back to the starting type variable; a guard is required when walking the type graph.

## 16. Self-Check Exercises

**Question 1.** In `class Box<T extends Number>`, who is the generic declaration of `T`?

**`Box.class`** itself. `getGenericDeclaration()` returns the declaration on the class, not a `Box<Integer>` instance.

**Question 2.** For `<T> T identity(T x)`, what is the declaration site of `T`?

The **`Method`** object of `identity`. `getBounds()` has the implicit upper bound `Object` if `extends` is omitted.

**Question 3.** Can a constructor have its own type parameters?

Yes. For example `<U extends CharSequence> Box(U text)`; reflected via `Constructor.getTypeParameters()`.

**Question 4.** How many upper bounds does `T extends Number & Comparable<T>` have?

Two: `Number` and `Comparable<T>`, in order; erasure uses the first bound `Number`.

**Question 5.** Are a class's `T` and a method's `T` with the same name the same type variable?

No. You must check `getGenericDeclaration()` and `TypeVariable.equals` semantics, not just `getName()`.

**Question 6.** Why is `Field.getType()` of field `T value` in `Box<T extends Number>` equal to `Number.class`?

Because `getType()` provides the erased/runtime view of the field, and the erasure of `T` based on its first upper bound is `Number`. `getGenericType()` can still return `TypeVariable` `T`.

**Question 7.** How do `getBounds()` and `getAnnotatedBounds()` differ?

`getBounds()` returns the `Type[]` structure; `getAnnotatedBounds()` returns `AnnotatedType[]` to inspect type-use annotations on the bounds.

**Question 8.** If `class Child extends Base<String>`, does `Base.class.getTypeParameters()` return `String`?

No. It returns the type parameter declared by `Base`. `Child.class.getGenericSuperclass()` is what describes `Child` binding `String` to the generic superclass.

**Question 9.** When using `TypeVariable` as a key while resolving generics, should you just use the string `"T"`?

No. You must preserve the identity of the declaration and type variable; identical names in multiple scopes do not mean the same type variable.

**Question 10.** Why must a Type parser detect cycles when processing `T extends Comparable<T>`?

Because the bound references the type variable `T` itself; if it keeps expanding without recording visited nodes, traversal may not terminate.

## 17. Quick Application Checklist

When reading a `TypeVariable<?> variable`, follow this sequence:

```text
TypeVariable<?> variable
    |
    +-- getName()                    -> Display name of the type parameter
    |
    +-- getGenericDeclaration()      -> Declaring Class / Method / Constructor
    |
    +-- getBounds()                  -> List of upper bound Types
    |     +-- Class?
    |     +-- ParameterizedType?     -> May contain T itself
    |
    +-- getAnnotatedBounds()         -> Annotations on bound type uses
    |
    +-- getAnnotations()             -> Annotations on parameter declaration
    |
    +-- Actual type arguments?       -> Look in generic superclass/interface
          and map in context, do not infer from bounds
```

**Conclusion:** `TypeVariable` does not represent a new runtime class; it represents a **declared type parameter**. To interpret it accurately, examine the **declaration site** via `getGenericDeclaration()`, **name** via `getName()`, **upper bounds** via `getBounds()`, and **type-use annotations** via `getAnnotatedBounds()`. Two variables with the same name remain distinct if declared in different scopes. Bounds constrain valid type arguments and determine erasure, yet do not replace actual type arguments supplied by a class/method/constructor in a specific context. This is an essential foundation for handling reflection, serialization, schema resolution, and Java Generics reliably.
