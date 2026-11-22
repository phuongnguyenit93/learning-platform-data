# `TypeVariable` and `GenericDeclaration` in Java Reflection

Java generics allow declaring `class Box<T>`, `interface Pair<K,V>`, a method `<U> U convert(U value)`, or a constructor with its own type parameters. When analyzing these declarations with Reflection, two interfaces `java.lang.reflect.TypeVariable` and `java.lang.reflect.GenericDeclaration` answer two different questions:

- **`TypeVariable<D extends GenericDeclaration>`** represents a **declared type variable**, such as `T` or `U`, along with its name, upper bounds, annotations, and declaring entity.
- **`GenericDeclaration`** represents **a place permitted to declare type parameters**: `Class<?>`, `Method`, and `Constructor<?>` all implement this interface. The common method `getTypeParameters()` returns the type variables declared directly there.

This is metadata of the **generic declaration**, not where Java separately stores every argument type on each runtime object. Distinguishing declarations, usage sites, and concrete type arguments is central to avoiding mistakes caused by *type erasure*.

## 1. Type Variables vs. Concrete Type Arguments

Consider:

```java
class Box<T extends Number> {
    T value;
}

class IntegerBox extends Box<Integer> {}
```

`T` belonging to `Box<T extends Number>` is a **type variable**. It is represented in Reflection by `TypeVariable`, whose upper bound is `Number`. By contrast, `Integer` in `extends Box<Integer>` is a **type argument** of a parameterized type, read from `ParameterizedType` on `IntegerBox`'s superclass.

`Box.class.getTypeParameters()` returns the declaration of `T`. `IntegerBox.class.getTypeParameters()` is an empty array because the subclass does not **itself** declare any type parameter. `IntegerBox.class.getGenericSuperclass()`, meanwhile, provides information equivalent to `Box<Integer>`.

`new Box<Integer>().getClass()` is `Box.class`, just like `new Box<Long>().getClass()`. The generic argument `Integer` or `Long` is generally not reified in the runtime class of an ordinary `Box` object. `TypeVariable.getBounds()` does not automatically supply `Integer` for a particular object.

## 2. `TypeVariable` in the `Type` Hierarchy

`java.lang.reflect.Type` is the common interface representing types returned by Reflection APIs when reading generic metadata.

| `Type` form | Example | Meaning |
| --- | --- | --- |
| `Class<?>` | `String`, `int`, `String[]` | Ordinary class/interface/primitive/array type |
| `ParameterizedType` | `List<String>`, `Map<K,V>` | Parameterized type with type arguments |
| `TypeVariable<?>` | `T` of `class Box<T>` | Type variable with its own declaration |
| `WildcardType` | `? extends Number`, `? super T` | Wildcard in a generic usage |
| `GenericArrayType` | `T[]` | Array with a generic component type that is not an ordinary array class |

`TypeVariable<D>` implements `Type` and `AnnotatedElement`. The `GenericDeclaration` interface is not a kind of `Type`: it describes where type variables are declared. However, `Class<?>` is both a `Type` and implements `GenericDeclaration`; `Method` and `Constructor<?>` implement `GenericDeclaration` but are not `Type`s.

There is no `T.class` for a type variable `T` in source code. If you want to query a type variable in a declaration, use `TypeVariable`; if you want to know the type `List<T>` at a field site, use `ParameterizedType` and continue inspecting the `Type` elements inside.

## 3. `GenericDeclaration.getTypeParameters()`

Core API:

```java
TypeVariable<?>[] variables = declaration.getTypeParameters();
```

In the illustration above, `declaration` is a provided variable of type `GenericDeclaration`. The result is an array in **declaration order**; if the entity does not directly declare type parameters, the array is empty.

**Generic class/interface:**

```java
class Pair<K, V> {}
```

`Pair.class.getTypeParameters()` returns two variables `K`, `V`, both owned by class `Pair`.

**Generic method:**

```java
class Util {
    public <U extends CharSequence> U echo(U input) {
        return input;
    }
}
```

`Util.class.getMethod("echo", CharSequence.class).getTypeParameters()` returns `U`, whose owner is the `Method` `echo`. When looking up the method, the runtime parameter after erasure is `CharSequence.class`: there is no `U.class`.

**Generic constructor:**

```java
class Handler {
    public <C extends Runnable> Handler(C action) {}
}
```

`Handler.class.getConstructor(Runnable.class).getTypeParameters()` returns `C` belonging to the constructor, even though `Handler.class.getTypeParameters()` is empty.

`Field` does not implement `GenericDeclaration`: a field **uses** a `T` declared by the appropriate class/method, rather than declaring type parameters the way `Class`, `Method`, or `Constructor` does. Read a field's generic type with `Field.getGenericType()`.

## 4. Important Methods of `TypeVariable`

| API | Return type | How to understand it |
| --- | --- | --- |
| `getName()` | `String` | Name such as `T`, `E`, `K` |
| `getTypeName()` | `String` | Descriptive type name; for a type variable, usually the variable name |
| `getGenericDeclaration()` | `D extends GenericDeclaration` | Class, method, or constructor **owning the declaration** |
| `getBounds()` | `Type[]` | Upper bounds in declaration order |
| `getAnnotatedBounds()` | `AnnotatedType[]` | Upper bounds along with type-use annotations |
| `getAnnotations()` / `getDeclaredAnnotations()` | `Annotation[]` | Annotations attached to **the type parameter itself** |

For example, `<T>` has an implicit upper bound of `Object`, so `getBounds()` returns a single element equivalent to `Object.class`, not an empty array.

For `<T extends Number & Comparable<T>>`, `getBounds()` contains two elements: `Number` (usually `Class<?>`) and `Comparable<T>` (a `ParameterizedType`). Therefore **do not cast all elements of `getBounds()` to `Class<?>`**.

The first bound determines the erasure of the type variable: `T extends Number & Comparable<T>` erases to `Number`; `U extends CharSequence` erases to `CharSequence`; unbounded `T` erases to `Object`. Every bound contributes to constraining valid type arguments, not just the first bound.

## 5. Standalone Runnable Java 17+ Example

Save the following to `TypeVariableDemo.java`. The program features a generic class with intersection bounds, a method with a type variable of the same name as the class's, a generic constructor, and a subclass fixing a type argument.

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.TypeVariable;
import java.util.Arrays;
import java.util.List;

public class TypeVariableDemo<T extends Number & Comparable<T>> {
    public List<T> items;

    public TypeVariableDemo() {}

    public <C extends Runnable> TypeVariableDemo(C action) {}

    // The method's T is a new variable, not the class's T.
    public <T extends CharSequence> T echo(T value) {
        return value;
    }

    public static class Fixed extends TypeVariableDemo<Integer> {}

    public static void main(String[] args) throws Exception {
        TypeVariable<?> classVar =
                TypeVariableDemo.class.getTypeParameters()[0];

        System.out.println("Class variable: " + classVar.getName());
        System.out.println("Class owner: "
                + ((Class<?>) classVar.getGenericDeclaration())
                        .getSimpleName());
        System.out.println("Class bounds: "
                + Arrays.toString(classVar.getBounds()));
        System.out.println("Annotated bounds count: "
                + classVar.getAnnotatedBounds().length);

        Method method = TypeVariableDemo.class.getMethod(
                "echo", CharSequence.class);
        TypeVariable<?> methodVar = method.getTypeParameters()[0];

        System.out.println("Method variable: " + methodVar.getName());
        System.out.println("Method bounds: "
                + Arrays.toString(methodVar.getBounds()));
        System.out.println("Same T variable: "
                + classVar.equals(methodVar));
        System.out.println("Method owner equals: "
                + methodVar.getGenericDeclaration().equals(method));

        Constructor<?> constructor =
                TypeVariableDemo.class.getConstructor(Runnable.class);
        TypeVariable<?> ctorVar = constructor.getTypeParameters()[0];

        System.out.println("Constructor variable: " + ctorVar.getName());
        System.out.println("Constructor bounds: "
                + Arrays.toString(ctorVar.getBounds()));
        System.out.println("Constructor owner equals: "
                + ctorVar.getGenericDeclaration().equals(constructor));

        Field field = TypeVariableDemo.class.getField("items");
        ParameterizedType fieldType =
                (ParameterizedType) field.getGenericType();

        System.out.println("Field generic type: "
                + fieldType.getTypeName());
        System.out.println("Field argument equals class T: "
                + fieldType.getActualTypeArguments()[0]
                        .equals(classVar));
        System.out.println("Field raw type: "
                + field.getType().getTypeName());

        System.out.println("Fixed type parameters: "
                + Fixed.class.getTypeParameters().length);
        ParameterizedType superclass =
                (ParameterizedType) Fixed.class.getGenericSuperclass();
        System.out.println("Fixed raw superclass: "
                + ((Class<?>) superclass.getRawType()).getSimpleName());
        System.out.println("Fixed type argument: "
                + superclass.getActualTypeArguments()[0].getTypeName());
    }
}
```

Compile and run:

```bash
javac TypeVariableDemo.java
java TypeVariableDemo
```

Output:

```text
Class variable: T
Class owner: TypeVariableDemo
Class bounds: [class java.lang.Number, java.lang.Comparable<T>]
Annotated bounds count: 2
Method variable: T
Method bounds: [interface java.lang.CharSequence]
Same T variable: false
Method owner equals: true
Constructor variable: C
Constructor bounds: [interface java.lang.Runnable]
Constructor owner equals: true
Field generic type: java.util.List<T>
Field argument equals class T: true
Field raw type: java.util.List
Fixed type parameters: 0
Fixed raw superclass: TypeVariableDemo
Fixed type argument: java.lang.Integer
```

Points to observe:

1. The class variable `T` is declared by `TypeVariableDemo.class`; its bounds are `Number` and `Comparable<T>`.
2. The method also uses the name `T` but owns a separate declaration. Hence `classVar.equals(methodVar) == false`. The call `getMethod("echo", CharSequence.class)` uses the erased signature.
3. The generic constructor declares `C extends Runnable`; `getGenericDeclaration()` points to the corresponding `Constructor` object.
4. For the field `List<T>`, reading `Field.getGenericType()` produces a `ParameterizedType` whose actual type argument is the same class variable `T`. However, `Field.getType()` is only `List.class`.
5. `Fixed.class.getTypeParameters()` is empty because `Fixed` declares no type variable of its own. Instead, `Fixed.class.getGenericSuperclass()` holds the metadata `TypeVariableDemo<Integer>`; from `getActualTypeArguments()`, we read `Integer`.

These values are metadata from Java declarations, not a general type inference result from arbitrary runtime instances.

## 6. Same Name Does Not Mean the Same Type Variable

Example:

```java
class Outer<T> {
    public <T> T convert(T value) {
        return value;
    }
}
```

Both variables have `getName()` equal to `"T"` but are declared in two different places:

- `Outer.class.getTypeParameters()[0]` is the class variable `T`.
- `Outer.class.getDeclaredMethod("convert", Object.class).getTypeParameters()[0]` is the method variable `T`.

The method type parameter shadows the class type parameter name within its scope. By `equals()` semantics, the two `TypeVariable` instances are distinct because they represent two different declarations.

Do not use simple map keys like `"T" -> someType` when building a generic resolver: `T` from another class, method, or constructor can share the same name. Use the pair **declaration + name**, or use `TypeVariable` itself with `equals()` and `hashCode()`.

The API does not require Reflection to return a **single unique object instance** every time the same type variable is read; do not rely on `==` for identity. `equals()` identifies a type variable by its declaration, which is what matters.

## 7. Reading a Type Variable's Bounds

`TypeVariable.getBounds()` returns all **upper bounds** in order: `<T>` gives `Object`; `<T extends Number>` gives `Number`; `<T extends Number & Comparable<T>>` gives `Number` and `Comparable<T>`. The first bound determines erasure; the remaining bounds still constrain valid types. Each element is a `Type`, so `Comparable<T>` is a `ParameterizedType` and must not all be cast to `Class`. Self-referential cycles such as `T extends Comparable<T>` need tracking during recursive traversal.

What must be distinguished in this lesson is that **bounds belong to the declaration**, not actual type arguments. Rules for class/interface bounds, wildcard upper/lower bounds, annotations on bounds, and edge cases are practiced in depth in the next lesson on `getBounds()`.

## 8. Annotations on Type Parameters and on Bounds

`TypeVariable` implements `AnnotatedElement` to read annotations on **the type variable itself**; `getAnnotatedBounds()` lets you read annotations at **the type-use positions in bounds**.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
@interface ParameterHint {}

@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface BoundHint {}

class AnnotatedExample<
        @ParameterHint T extends @BoundHint Number> {}
```

In the example:

- `AnnotatedExample.class.getTypeParameters()[0].getAnnotations()` finds the `@ParameterHint` annotation.
- `getAnnotatedBounds()[0]` describes the `Number` bound along with the type-use annotation `@BoundHint`.
- `getBounds()[0]` describes the `Number` type itself, without the type-use annotation details on the bound.

`RetentionPolicy.RUNTIME` is required if you want these annotations to appear through Reflection at runtime. Do not mix annotations on a type parameter with annotations on a type inside a bound.

## 9. Where a `TypeVariable` Can Be Encountered at Usage Sites

Besides `getTypeParameters()`, many APIs return `Type` and can contain a `TypeVariable`:

```java
class Holder<T> {
    T value;

    T get() { return value; }

    void set(T input) { value = input; }
}
```

In the context of class `Holder`, we can inspect:

```java
TypeVariable<?> declared = Holder.class.getTypeParameters()[0];

Field field = Holder.class.getDeclaredField("value");
java.lang.reflect.Type fieldType = field.getGenericType();

Method getter = Holder.class.getDeclaredMethod("get");
java.lang.reflect.Type returnType = getter.getGenericReturnType();

Method setter = Holder.class.getDeclaredMethod("set", Object.class);
java.lang.reflect.Type parameterType =
        setter.getGenericParameterTypes()[0];
```

This is an illustrative snippet with imports `TypeVariable`, `Field`, `Method` and a `throws Exception` context. `T` has no explicit bound, so the erasure of the setter parameter is `Object`.

All three usage sites above refer to the variable `T` declared by `Holder`. You can cast to `TypeVariable<?>` once the actual kind is verified and use `getGenericDeclaration()`/`equals()` to identify the declaration.

Conversely, `Field.getType()` and `Method.getReturnType()` return raw/erased types without preserving the full generic structure. When you need to read the structure, use the appropriate `getGeneric...` methods.

## 10. Resolving `T` in the Context of a Subclass

Consider:

```java
class Base<T> {
    T item;
}

class Child extends Base<String> {}
```

`Base.class.getTypeParameters()[0]` remains a type variable `T`; it does not transform into `String` when accessed from `Child`. To know what type `T` corresponds to in the context of `Child`, you must:

1. Read `Child.class.getGenericSuperclass()` and verify the result is a `ParameterizedType` representing `Base<String>`.
2. Read the type arguments via `getActualTypeArguments()`.
3. Map the type variable `T` of declaration `Base` to the type argument `String` at the corresponding position.
4. Apply the mapping to the generic field/method type if you want to know the effective type in `Child`'s context.

With multiple levels such as `Middle<U> extends Base<List<U>>` and then `Leaf extends Middle<Integer>`, you must process the `ParameterizedType`s sequentially, potentially mapping from one type variable to a generic structure containing another type variable. Java Reflection supplies the metadata, but does not provide a single core method that automatically resolves all generic variables for a receiver subclass.

This is completely different from `getBounds()`: an upper bound describes *a constraint a type argument must satisfy*, whereas a subclass mapping tells *the type argument declared* in a specific inheritance relationship.

## 11. `TypeVariable` vs. Wildcard and Parameterized Type

Example inside a class `<T>`:

```java
java.util.Map<String, java.util.List<? extends T>> values;
```

If reading `Field.getGenericType()`:

1. The outer `Map<...>` is a `ParameterizedType`.
2. `String` is a `Class<?>`.
3. `List<? extends T>` is another `ParameterizedType`.
4. `? extends T` is a `WildcardType`.
5. The wildcard's upper bound is `T`, a `TypeVariable<?>` declared by the class or method.

Wildcard `?` **does not create a new declaration** like `T`; it is a construct at a usage site. `WildcardType.getUpperBounds()` describes the wildcard's bound, whereas `TypeVariable.getBounds()` describes the type variable's upper bounds at its declaration.

When a generic parser returns `Type`, use `instanceof` to branch on `Class`, `ParameterizedType`, `TypeVariable`, `WildcardType`, and `GenericArrayType`. Casting every value to `Class<?>` easily triggers `ClassCastException` or loses information.

## 12. Practical Mistakes When Using Generic Reflection

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Two variables both named `T` are the same | Different scopes/declarations | Check `getGenericDeclaration()` and `equals()` |
| `getBounds()` contains the actual type argument | Bounds are declaration constraints | Read `ParameterizedType.getActualTypeArguments()` when needed |
| `getBounds()` of `<T>` is an empty array | Implicit bound is `Object` | Expect `Object.class` |
| Every bound is a `Class` | `Comparable<T>` is a `ParameterizedType` | Classify each `Type` |
| A subclass automatically has its parent's type parameters | `getTypeParameters()` returns only directly declared variables | Also read generic superclass/interfaces |
| `getClass()` of `Box<Integer>` contains `Integer` | Erasure drops runtime type arguments on instances | Use subclass/type-token metadata or explicit input |
| `Field.getType()` shows `List<T>` | It returns raw class `List` | Use `Field.getGenericType()` |
| `getAnnotations()` returns annotations on bounds | Type-parameter annotations differ from type-use annotations | Use `getAnnotatedBounds()` |
| Using `==` to compare two `TypeVariable`s | Instance identity is not guaranteed | Use `equals()` |
| Traversing `T extends Comparable<T>` infinitely | Bounds can be self-referential | Track visited variables/declarations |

Metadata can also fail if a generic signature references a missing type or an invalid parameterized model; generic APIs may throw `TypeNotPresentException` or `MalformedParameterizedTypeException`. A serious metadata analyzer should report the real cause rather than treating any failure as an empty type variable.

For bridge methods generated by the compiler when generics are erased, `Method.isBridge()` and `isSynthetic()` help a method scanner distinguish actual declarations from compiler-generated support code. Do not group solely by method name or `T` name as a key while ignoring signatures and declarations.

## 13. Workflow for Using `TypeVariable` in a Framework

When building a mapper, serializer, schema inspector, or documentation tool:

1. **Identify the `GenericDeclaration`.** Is this a `Class`, `Method`, or `Constructor`? Call `getTypeParameters()` on the right entity.
2. **Identify the type variable.** Use `getName()` and `getGenericDeclaration()`, or `equals()`; note that a method can declare a variable with the same name as the class's.
3. **Read all bounds.** Use `getBounds()`, properly handling `ParameterizedType`, `TypeVariable`, and nested structures.
4. **Read annotations at the right place.** Use `getAnnotations()` for the type parameter, and `getAnnotatedBounds()` for annotations on bounds.
5. **Read usage sites.** Use `getGenericType()`, `getGenericReturnType()`, `getGenericParameterTypes()`, `getGenericSuperclass()`, or `getGenericInterfaces()` depending on the target.
6. **Resolve type arguments in context if needed.** From a subclass's `ParameterizedType` or a type token, build a mapping from declaration variables to concrete type arguments. Do not mutate the original `TypeVariable` into another type.
7. **Account for erasure and missing metadata.** Do not try to deduce `Integer` from an ordinary `new Box<Integer>()` when that information no longer exists in the runtime class; handle cycles when bounds are self-referential.

### Self-Check

**Question 1.** `class A<T>` and `class B<T>` both declare the name `T`. Are the two type variables equal?  
No. They belong to two different `GenericDeclaration`s.

**Question 2.** `class Child extends Parent<String>`. Why is `Child.class.getTypeParameters()` empty?  
Because `Child` declares no new type parameter. The `String` type resides in the `ParameterizedType` of `getGenericSuperclass()`.

**Question 3.** Why should `getBounds()` of `T extends Number & Comparable<T>` not all be cast to `Class`?  
Because `Comparable<T>` is a `ParameterizedType`.

**Question 4.** If method `<U> U echo(U x)` declares `U`, what does `U`'s `getGenericDeclaration()` return?  
The `Method` object that owns the declaration of `U`, not automatically the class containing the method.

**Question 5.** Does `TypeVariable.getBounds()` tell you the exact type argument of every `Box<T>` instance?  
No. Bounds are constraints; concrete type arguments are usually erased on instances and can only be read when suitable metadata exists.

## Takeaways

- **`GenericDeclaration`** is where type parameters are declared: class/interface, method, or constructor; read with `getTypeParameters()`.
- **`TypeVariable`** represents a declaration's type variable, with a name, owner, upper bounds, and annotations.
- **The name `T` is not enough to identify a variable.** Check the owner and use `equals()`.
- **Upper bounds differ from actual type arguments.** `getBounds()` does not replace `ParameterizedType.getActualTypeArguments()`.
- **Type erasure** means runtime generic inference depends on metadata that still exists in declarations.

Once you clearly understand the order **declaration → type variable → usage site → contextual type arguments**, you can read and process the generic system with Java Reflection without confusing type variables with concrete types.
