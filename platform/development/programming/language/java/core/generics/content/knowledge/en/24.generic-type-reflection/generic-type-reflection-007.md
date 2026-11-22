# Reading `getGenericSuperclass`, `getGenericInterfaces`, and Member Signatures in Java Reflection

## 1. Goal: Observing **Type Declarations** Instead of Guessing Runtime Types

When inspecting Java Generics with Reflection, three common groups of questions arise:

1. Which generic superclass does a class **extend**, and with what type arguments?
2. Which generic interfaces does a class **implement**, and with what type arguments?
3. With what generic type is a field, method, constructor, or type parameter **declared**?

Key APIs:

~~~java
Class<?> clazz = SomeClass.class;

Type parent = clazz.getGenericSuperclass();
Type[] directInterfaces = clazz.getGenericInterfaces();

Type fieldType = field.getGenericType();
Type returnType = method.getGenericReturnType();
Type[] parameters = method.getGenericParameterTypes();
Type[] thrown = method.getGenericExceptionTypes();
~~~

The lines above are **API illustrations**: `SomeClass`, `field`, and `method` must be supplied by a concrete program. A complete, immediately runnable Java 17 program is in Section 9.

Crucially, generics reflection primarily reads **type signature metadata stored in the class file**. It does **not** mean the JVM maintains distinct runtime versions of `List<String>` and `List<Integer>`, and it does **not** automatically verify the type of every element in a collection.

This topic is part of **generic type reflection**, distinct from reading ordinary object data. We must distinguish:

- **`Class<?>`**: describes a runtime class or interface.
- **`java.lang.reflect.Type`**: describes a form of type in the Reflection system, which may contain type arguments, wildcards, type variables, or generic arrays.
- **`Field` / `Method` / `Constructor<?>`**: Reflection objects representing member declarations, from which generic type signatures can be read.

## 2. Running Example Framework

Suppose a subclass binds `T = String` for its generic superclass and implements a generic interface:

~~~java
interface Source<K, V> {
    V get(K key);
}

class Parent<T> {
    public T item;
    public List<T> items;
    public T[] buffer;
    public List<? extends Number> upper;

    public <E extends Exception> List<? super T> transform(
            List<? extends T> input, E problem) throws E {
        throw problem;
    }
}

final class Child extends Parent<String>
        implements Source<String, List<Integer>>, Serializable {

    @Override
    public List<Integer> get(String key) {
        return List.of(key.length());
    }
}
~~~

This snippet assumes imports for `java.io.Serializable` and `java.util.List`; in the standalone program in Section 9, these are nested types.

These classes contain multiple layers of generic information:

- `Parent<T>` declares a **class type variable** `T`.
- `Child extends Parent<String>` supplies the **type argument String** in the superclass signature.
- `Child implements Source<String,List<Integer>>` supplies **two type arguments**, where the second type argument is itself a nested parameterized type.
- `Serializable` is a non-generic interface, so it has no type arguments.
- Field `item` has type `T`, `items` has `List<T>`, `buffer` has `T[]`, and `upper` has wildcard `? extends Number`.
- `transform` has a **method type variable** `E extends Exception`, a parameter `List<? extends T>`, and return type `List<? super T>`.

There is no single API that immediately returns "the type diagram with every variable resolved" for all of these declarations. We must read the appropriate components of `Type` while understanding the original declaration context.

## 3. How Do `Class.getSuperclass` and `getGenericSuperclass` Differ?

Both APIs concern the **direct superclass**, yet their return types and amount of information differ greatly.

~~~java
Class<?> erased = Child.class.getSuperclass();
Type generic = Child.class.getGenericSuperclass();
~~~

For `Child extends Parent<String>`:

- `getSuperclass()` returns a **`Class<?>` representing Parent**. It does not represent the type argument String.
- `getGenericSuperclass()` returns a **`Type`**, specifically usually a `ParameterizedType` describing `Parent<String>`.

Reading type arguments with a type check:

~~~java
Type type = Child.class.getGenericSuperclass();

if (type instanceof ParameterizedType parameterized) {
    Type raw = parameterized.getRawType();
    Type[] arguments = parameterized.getActualTypeArguments();

    System.out.println(((Class<?>) raw).getSimpleName()); // Parent
    System.out.println(arguments[0].getTypeName());       // java.lang.String
}
~~~

**Do not blindly cast** the return value to ParameterizedType. If a class extends a non-generic superclass or uses a raw parent type, the result may be `Class<?>`; if there is no superclass per the API rules, it may be `null`.

A helpful table:

| Class Declaration | `getSuperclass()` | `getGenericSuperclass()` |
| --- | --- | --- |
| `class A extends Parent<String>` | Class of Parent | ParameterizedType of Parent<String> |
| `class B extends Parent` (raw) | Class of Parent | May be Class of raw Parent |
| `class C extends Object` | Class of Object | Class of Object |
| `java.lang.Object` | null | null |
| Interface type | Has no class superclass the way a class does | Usually null for `getGenericSuperclass()` |

Exceptions such as `TypeNotPresentException` or `MalformedParameterizedTypeException` can occur when a generic signature contains an unloadable type or invalid metadata; check the API contract if handling unusual bytecode or incomplete classes.

### 3.1. `getGenericSuperclass` Only Examines the **Direct `extends` Relationship**

If `Grandchild extends Child`, reading `Grandchild.class.getGenericSuperclass()` directly will describe Child, not walk all the way up the ancestor chain to `Parent<String>`.

To retrieve generic arguments of a multi-level ancestor, you must walk the generic superclass edges and substitute type variables at each level. That is a separate type-resolution problem, not an automatic feature of a single `getGenericSuperclass()` call.

## 4. `Class.getInterfaces` and `getGenericInterfaces`

Similarly for **directly declared interfaces**:

~~~java
Class<?>[] erased = Child.class.getInterfaces();
Type[] generic = Child.class.getGenericInterfaces();
~~~

For:

~~~java
final class Child extends Parent<String>
        implements Source<String, List<Integer>>, Serializable {
    // ...
}
~~~

`getInterfaces()` returns the `Class<?>` objects for `Source` and `Serializable`, without type arguments.

`getGenericInterfaces()` returns a `Type[]` array that may include:
- `ParameterizedType` for `Source<String,List<Integer>>`;
- `Class<?>` for the non-generic interface `Serializable`.

Therefore:

~~~java
Type[] interfaces = Child.class.getGenericInterfaces();

for (Type type : interfaces) {
    System.out.println(type.getTypeName());
}
~~~

You can observe the generic interface along with its type arguments, while the marker interface Serializable is represented as a normal class/interface token.

**Important:** these are the **interfaces directly declared by the class or interface**, not every interface inherited indirectly. To gather all generic interfaces across an entire type hierarchy, you must traverse superclasses/interfaces appropriately and resolve type variables across multiple inheritance levels.

### 4.1. Unwrapping an Interface with Nested Type Arguments

~~~java
Type[] interfaces = Child.class.getGenericInterfaces();

if (interfaces[0] instanceof ParameterizedType sourceType) {
    Type[] arguments = sourceType.getActualTypeArguments();

    Type keyType = arguments[0];    // String.
    Type valueType = arguments[1];  // List<Integer>.

    System.out.println(keyType.getTypeName());
    System.out.println(valueType.getTypeName());
}
~~~

Output from `getTypeName()` can be:

~~~text
java.lang.String
java.util.List<java.lang.Integer>
~~~

For `arguments[1]`, do not cast directly to `Class<List>`. `List<Integer>` is a **ParameterizedType**, because it has raw type List and actual type argument Integer.

You can unwrap one layer deeper:

~~~java
ParameterizedType listType = (ParameterizedType) valueType;

Type listRawType = listType.getRawType(); // Class of List.
Type itemType = listType.getActualTypeArguments()[0]; // Integer.
~~~

Not every generic argument is a `Class<?>`. A type argument can itself be a `TypeVariable<?>`, a `WildcardType`, another `ParameterizedType`, or a `GenericArrayType`.

## 5. The `Type` System: Always Check the Kind Before Casting

`java.lang.reflect.Type` is the common abstraction. A practical classification:

| Reflection Type | Declaration Example | Data to Read |
| --- | --- | --- |
| `Class<?>` | `String`, `Integer`, raw `List` | Class name, superclass, interfaces, members |
| `ParameterizedType` | `List<String>`, `Map<String,List<Integer>>` | `getRawType`, `getActualTypeArguments`, `getOwnerType` |
| `TypeVariable<?>` | `T` in Parent<T>, `E` of generic method | `getName`, `getBounds`, `getGenericDeclaration` |
| `WildcardType` | `?`, `? extends Number`, `? super T` | `getUpperBounds`, `getLowerBounds` |
| `GenericArrayType` | `T[]`, `List<String>[]` in generic signature | `getGenericComponentType` |

These are branches of *kinds of `Type` descriptions*, not runtime object types corresponding to every generic instantiation.

A simple visitor:

~~~java
static void describe(Type type) {
    if (type instanceof Class<?> clazz) {
        System.out.println("Class: " + clazz.getName());
    } else if (type instanceof ParameterizedType p) {
        System.out.println("Parameterized: " + p.getTypeName());
    } else if (type instanceof TypeVariable<?> v) {
        System.out.println("Variable: " + v.getName());
    } else if (type instanceof WildcardType w) {
        System.out.println("Wildcard: " + w.getTypeName());
    } else if (type instanceof GenericArrayType a) {
        System.out.println("Array: " + a.getTypeName());
    }
}
~~~

The snippet above is an illustrative helper requiring `import java.lang.reflect.*;`. To print nested trees, the visitor must **recurse** into raw/owner/arguments/bounds/component types, while avoiding cycles caused by self-bounded generics like `T extends Comparable<T>`.

### 5.1. Do Not Rely on Internal Implementation Class Names of `Type`

A `ParameterizedType` may be represented by the JDK via an internal class, yet that implementation class name is not a stable public contract for comparisons. Use:

~~~java
type instanceof ParameterizedType
~~~

and the standard interface methods. Do not call `type.getClass().getSimpleName()` and assume the result is identical across JDKs.

## 6. `ParameterizedType`: Raw Type, Actual Arguments, Owner

For example, a generic type:

~~~java
Map<String, List<Integer>>
~~~

has:
- raw type `Map`;
- first argument `String`;
- second argument `List<Integer>`, itself a ParameterizedType.

With:

~~~java
ParameterizedType p = (ParameterizedType) someType;

Type raw = p.getRawType();
Type[] args = p.getActualTypeArguments();
Type owner = p.getOwnerType();
~~~

**`getRawType()`** describes the underlying generic class/interface (`Map`). It is a `Type`, usually a `Class<?>` in common cases.

**`getActualTypeArguments()`** returns the type arguments written in the generic signature at that declaration level; for Map, two values. Do not assume every element is a Class.

**`getOwnerType()`** reports the enclosing/owner type when the generic type is a member type with an applicable owner. For instance, constructs like `Outer<String>.Inner<Integer>` may need information about both owner Outer<String> and Inner<Integer>. For ordinary top-level Map, owner is null.

Do not equate a member type's owner with its superclass. These are two different relationships:
- `getGenericSuperclass` reads **extends**;
- `getOwnerType` reads the **owner/enclosing type** in a member type's name structure.

### 6.1. Type Arguments Do Not Guarantee Runtime Element Types

A `ParameterizedType` describing `List<String>` does not iterate every element of a `List` object. Nor is it proof that a raw alias has never inserted an Integer. Generic metadata can be completely intact at the **declaration** while a runtime object holds data violating compile-time expectations if code used raw/unchecked operations.

## 7. `TypeVariable`: Which **Declaration** Does a Type Variable Belong To?

In:

~~~java
class Parent<T> {
    T item;

    <E extends Exception> void act(E problem) throws E {
        throw problem;
    }
}
~~~

there are two different type variables:

- `T` belongs to the **declaration of class Parent<T>**.
- `E` belongs to the **declaration of method act<E>**.

Reading type variables on the class:

~~~java
TypeVariable<?>[] vars = Parent.class.getTypeParameters();
System.out.println(vars[0].getName()); // T
~~~

Reading on the method:

~~~java
Method m = Parent.class.getDeclaredMethod("act", Exception.class);
TypeVariable<Method>[] methodVars = m.getTypeParameters();
System.out.println(methodVars[0].getName()); // E
~~~

`getGenericDeclaration()` indicates **where the type variable was declared**. This matters because two different classes can both use the name T while still having **two distinct type variables**. Do not map type variables solely by the string `"T"` in a complex type resolver.

Reading bounds:

~~~java
for (Type bound : methodVars[0].getBounds()) {
    System.out.println(bound.getTypeName());
}
~~~

If E extends Exception, the relevant upper bound is `java.lang.Exception`. For T with no explicit bound, the default bound is Object.

### 7.1. Raw Erasure and `TypeVariable` Are Not the Same

When `T` has no explicit bound, the erasure of T is usually Object; yet `field.getGenericType()` can still return **TypeVariable T**, because declaration metadata preserves the signature `T`.

Thus:

~~~java
Field f = Parent.class.getDeclaredField("item");

Class<?> erased = f.getType(); // Object.class.
Type generic = f.getGenericType(); // TypeVariable T.
~~~

Do not conclude: "Since runtime erasure is Object, `getGenericType()` must also return Object." The two APIs intentionally expose **two different layers of information**.

## 8. `WildcardType`: Reading `? extends` and `? super` Bounds

Consider:

~~~java
class Parent<T> {
    List<? extends Number> upper;
    List<? super T> lower;
}
~~~

The field types are ParameterizedTypes, with wildcards inside:

~~~java
Field field = Parent.class.getDeclaredField("upper");
ParameterizedType p = (ParameterizedType) field.getGenericType();

WildcardType wildcard =
        (WildcardType) p.getActualTypeArguments()[0];

Type[] uppers = wildcard.getUpperBounds();
Type[] lowers = wildcard.getLowerBounds();
~~~

For `? extends Number`:
- upper bound is Number;
- lower bounds list is empty.

For `? super T`:
- lower bound is **TypeVariable T**;
- default upper bound is Object.

For `?` with no explicit bound:
- default upper bound is Object;
- lower bounds list is empty.

Reading wildcard bounds accurately helps serializers, schema generators, and API analyzers; however, do not turn them into a runtime claim that "the collection always contains Numbers" merely because Reflection sees `? extends Number` on the field declaration.

### 8.1. Wildcards and Generic Arrays Can Nest

A field can declare:

~~~java
List<? extends T[]>[] arrays;
~~~

This is a multi-level type combining generic array, parameterized type, and wildcard. Proper type traversal must classify and recurse through each level rather than forcing everything to `Class<?>`.

Do not write a utility that only handles `Class` and `ParameterizedType` and treats all remaining types as "invalid"; Java Generics has several valid Type forms.

## 9. Complete Java 17+ Program

Save the file **ReflectionSignaturesDemo.java**:

~~~java
import java.io.Serializable;
import java.lang.reflect.Field;
import java.lang.reflect.GenericArrayType;
import java.lang.reflect.Method;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.WildcardType;
import java.util.Arrays;
import java.util.List;

public class ReflectionSignaturesDemo {
    interface Source<K, V> {
        V get(K key);
    }

    static class Parent<T> {
        public T item;
        public List<T> items;
        public T[] buffer;
        public List<? extends Number> upper;

        public <E extends Exception> List<? super T> transform(
                List<? extends T> input, E problem) throws E {
            throw problem;
        }
    }

    static final class Child extends Parent<String>
            implements Source<String, List<Integer>>, Serializable {

        @Override
        public List<Integer> get(String key) {
            return List.of(key.length());
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {

        Class<Child> clazz = Child.class;

        Type superclass = clazz.getGenericSuperclass();
        ParameterizedType parentType =
                (ParameterizedType) superclass;

        System.out.println(
                "erasedSuperclass=" +
                clazz.getSuperclass().getSimpleName()
        );
        System.out.println(
                "genericSuperclass=" +
                (superclass instanceof ParameterizedType)
        );
        System.out.println(
                "superRaw=" +
                ((Class<?>) parentType.getRawType()).getSimpleName()
        );
        System.out.println(
                "superArg=" +
                parentType.getActualTypeArguments()[0].getTypeName()
        );

        Type[] interfaces = clazz.getGenericInterfaces();
        System.out.println(
                "interfaces=" + interfaces.length
        );

        ParameterizedType source =
                (ParameterizedType) interfaces[0];

        System.out.println(
                "sourceRaw=" +
                ((Class<?>) source.getRawType()).getSimpleName()
        );
        System.out.println(
                "sourceKey=" +
                source.getActualTypeArguments()[0].getTypeName()
        );
        System.out.println(
                "sourceValueNested=" +
                (source.getActualTypeArguments()[1]
                        instanceof ParameterizedType)
        );
        System.out.println(
                "markerClass=" +
                (interfaces[1] instanceof Class<?>)
        );

        System.out.println(
                "declaredT=" +
                Parent.class.getTypeParameters()[0].getName()
        );

        Field item = Parent.class.getDeclaredField("item");
        Field items = Parent.class.getDeclaredField("items");
        Field buffer = Parent.class.getDeclaredField("buffer");
        Field upper = Parent.class.getDeclaredField("upper");

        System.out.println(
                "itemType=" + item.getGenericType().getTypeName()
        );
        System.out.println(
                "itemsType=" + items.getGenericType().getTypeName()
        );
        System.out.println(
                "arrayType=" +
                (buffer.getGenericType()
                        instanceof GenericArrayType)
        );
        System.out.println(
                "wildcard=" +
                (((ParameterizedType) upper.getGenericType())
                        .getActualTypeArguments()[0]
                        instanceof WildcardType)
        );

        Method method = Parent.class.getDeclaredMethod(
                "transform", List.class, Exception.class
        );

        System.out.println(
                "methodReturn=" +
                method.getGenericReturnType().getTypeName()
        );
        System.out.println(
                "parameter0=" +
                method.getGenericParameterTypes()[0].getTypeName()
        );
        System.out.println(
                "parameter1=" +
                method.getGenericParameterTypes()[1].getTypeName()
        );
        System.out.println(
                "exceptionType=" +
                method.getGenericExceptionTypes()[0].getTypeName()
        );
        System.out.println(
                "methodVariable=" +
                method.getTypeParameters()[0].getName()
        );

        System.out.println(
                "inheritedItemType=" +
                clazz.getField("item").getGenericType().getTypeName()
        );
        System.out.println(
                "concreteReturn=" +
                clazz.getMethod("get", String.class)
                        .getGenericReturnType().getTypeName()
        );

        long bridges = Arrays.stream(clazz.getDeclaredMethods())
                .filter(Method::isBridge)
                .count();

        System.out.println("bridges=" + bridges);
    }
}
~~~

Compile at Java 17 language level:

~~~bash
javac --release 17 -Xlint:all ReflectionSignaturesDemo.java
java ReflectionSignaturesDemo
~~~

**Exact stdout:**

~~~text
erasedSuperclass=Parent
genericSuperclass=true
superRaw=Parent
superArg=java.lang.String
interfaces=2
sourceRaw=Source
sourceKey=java.lang.String
sourceValueNested=true
markerClass=true
declaredT=T
itemType=T
itemsType=java.util.List<T>
arrayType=true
wildcard=true
methodReturn=java.util.List<? super T>
parameter0=java.util.List<? extends T>
parameter1=E
exceptionType=E
methodVariable=E
inheritedItemType=T
concreteReturn=java.util.List<java.lang.Integer>
bridges=1
~~~

The program is designed so its output does not depend on internal ParameterizedType implementation class names or arbitrary traversal ordering of `getDeclaredMethods()`; it only **counts** bridge methods. In this example, the compiler generates one bridge for the method implementing the generic interface `Source<K,V>`.

### 9.1. Key Observations in the Output

**`erasedSuperclass=Parent`**: the ordinary API returns the base class without type arguments.

**`genericSuperclass=true` and `superArg=java.lang.String`**: the superclass signature on Child shows that Parent was parameterized with String.

**`interfaces=2`**: Child directly implements Source and Serializable. Source has a generic signature; Serializable is a non-generic interface.

**`sourceValueNested=true`**: Source's second argument is `List<Integer>`, which is itself a ParameterizedType, not a runtime Class<List<Integer>>.

**`itemType=T`, `itemsType=java.util.List<T>`**: field metadata preserves **the declaration in Parent**, rather than automatically turning into String just because we went through Child.

**`arrayType=true`**: `T[]` is described by Reflection as GenericArrayType; unlike `String[]`, which is represented via a Class with component type String.

**`wildcard=true`**: `List<? extends Number>` contains a WildcardType at the type argument slot.

**`methodReturn` and `parameter0`**: the method declaration uses wildcards in both directions, `? super T` and `? extends T`.

**`parameter1=E`, `exceptionType=E`, `methodVariable=E`**: the generic method has a type variable E used in both a parameter and the throws clause.

**`inheritedItemType=T`**: even when looking up the inherited public field through Child, `Field.getGenericType()` still refers to Parent<T>'s declaration.

**`concreteReturn=java.util.List<java.lang.Integer>`**: method `get(String)` is declared directly on Child with return type List<Integer>, so Reflection reads that method's concrete signature.

**`bridges=1`**: the compiler can generate a bridge method due to type erasure to preserve overriding/interface dispatch on the JVM. Synthetic/bridge methods can appear in Reflection listings, so bridges should not be treated as developer-written generic declarations.

## 10. `Field.getType` and `Field.getGenericType`

This is the most important API pair to distinguish when inspecting member signatures:

~~~java
Field field = Parent.class.getDeclaredField("item");

Class<?> erasedType = field.getType();
Type genericType = field.getGenericType();
~~~

For `T item` with no explicit bound:
- `getType()` typically returns `Object.class` due to erasure.
- `getGenericType()` returns **TypeVariable T**.

For `List<T> items`:
- `getType()` returns `List.class`.
- `getGenericType()` returns **ParameterizedType List<T>**.

For `T[] buffer`:
- `getType()` returns the array class corresponding to erasure (`Object[]` when T is unbounded).
- `getGenericType()` returns **GenericArrayType T[]**.

Table:

| Field declaration | `getType()` | `getGenericType()` |
| --- | --- | --- |
| `String name` | String.class | Class of String |
| `T item` | Object.class if T is unbounded | TypeVariable T |
| `List<T> items` | List.class | ParameterizedType List<T> |
| `T[] buffer` | Object[].class if T is unbounded | GenericArrayType T[] |
| `List<? extends Number> upper` | List.class | ParameterizedType containing WildcardType |

Do not ignore `getGenericType()` when building a schema mapper, serializer, or generic metadata reader. At the same time, do not use it to replace `getType()` when you need a runtime class for `isInstance` or `Class.cast`.

## 11. `Method.getReturnType` and `getGenericReturnType`

For:

~~~java
public <E extends Exception> List<? super T> transform(
        List<? extends T> input, E problem) throws E
~~~

`Method.getReturnType()` gives the return type's class after erasure: `List.class`.

`Method.getGenericReturnType()` gives the full declared type:

~~~text
java.util.List<? super T>
~~~

Reading the method:

~~~java
Method method = Parent.class.getDeclaredMethod(
        "transform", List.class, Exception.class
);

Type genericReturn = method.getGenericReturnType();
Class<?> erasedReturn = method.getReturnType();
~~~

Pay attention to how `getDeclaredMethod` is looked up: the passed parameters are **`Class<?>` objects matching the erased parameter types**, not `Type` objects representing `List<? extends T>` or E.

Here:
- `List<? extends T>` erases to List;
- `E extends Exception` erases to Exception;
- hence the Java Reflection lookup uses `List.class, Exception.class`.

If you mistakenly pass `Object.class` for E or `ArrayList.class` instead of List, `getDeclaredMethod` can throw NoSuchMethodException because lookup requires the exact **erased formal parameter types**.

### 11.1. `void` and Primitive Return Types

`Method.getGenericReturnType()` does not mean every method returns ParameterizedType. If a method returns `void`, `int`, or `String`, the corresponding Type may be represented by an appropriate `Class<?>`. Always check the Type kind before casting.

## 12. `getGenericParameterTypes` and `getGenericExceptionTypes`

The method:

~~~java
Method method = Parent.class.getDeclaredMethod(
        "transform", List.class, Exception.class
);
~~~

has:
- `getParameterTypes()`: the erased Class<?> objects (`List.class`, `Exception.class`).
- `getGenericParameterTypes()`: `List<? extends T>` and `E`.
- `getExceptionTypes()`: the Class<?> objects in the throws clause after erasure.
- `getGenericExceptionTypes()`: `E` as a TypeVariable.

Example:

~~~java
Type[] parameters = method.getGenericParameterTypes();
Type[] exceptions = method.getGenericExceptionTypes();

for (Type parameter : parameters) {
    System.out.println(parameter.getTypeName());
}
for (Type exceptionType : exceptions) {
    System.out.println(exceptionType.getTypeName());
}
~~~

Generic signatures let you read the **link between E in the parameter list and E in the throws clause**. Looking only at `getExceptionTypes()` typically shows the Exception bound without knowing both positions share the same type variable E.

### 12.1. Method Type Parameters Differ from Class Type Parameters

Do not call `Parent.class.getTypeParameters()` and assume you found E. E is declared on method `transform`, so you must read:

~~~java
TypeVariable<Method>[] variables = method.getTypeParameters();
~~~

Meanwhile T belongs to class Parent, so it is read via `Parent.class.getTypeParameters()`. The two variables have different declaration scopes and can even share the same name if source code declares them separately in different declarations.

## 13. Declared Members vs. Inherited Members

This is a major source of bugs when walking Reflection.

**Declared APIs**:
- `getDeclaredFields()`, `getDeclaredField(name)`;
- `getDeclaredMethods()`, `getDeclaredMethod(name, parameterTypes...)`;
- `getDeclaredConstructors()`.

They inspect members **declared directly by the reflected class/interface**, including different visibilities within API bounds. They do not automatically climb to superclasses to return inherited members.

**Public/inherited APIs**:
- `getFields()`, `getField(name)`;
- `getMethods()`, `getMethod(name, parameterTypes...)`.

They can see inherited and public members according to each API's contract.

With `Child extends Parent<String>`:
- `Child.class.getDeclaredField("item")` fails if Child does not declare its own field item;
- `Child.class.getField("item")` can find the public field item in Parent;
- The returned Field has `getDeclaringClass() == Parent.class`;
- That Field's `getGenericType()` still describes **T** as written in Parent.

Therefore, simply iterating inherited fields and reading type variables from metadata does not automatically produce a complete schema specialized for Child.

### 13.1. Walking the Class Hierarchy vs. Walking Declared Fields

To build a complete report, you can walk parent classes via `getSuperclass()` or `getGenericSuperclass()`, reading `getDeclaredFields()` on each class. To preserve Child's concrete types, you must maintain a **mapping of type variables → actual type arguments** as you traverse generic superclass edges.

Shadowing, overriding, static fields, visibility, bridge methods, and interfaces must all be handled when building a true production type resolver. This lesson focuses on reading metadata accurately and recognizing when an extra resolution step is needed.

## 14. Important Pitfall: `getGenericType` on an Inherited Field Is Still `T`

With:

~~~java
class Parent<T> {
    public T item;
}

class Child extends Parent<String> {}
~~~

Do not expect:

~~~java
Type type = Child.class.getField("item").getGenericType();
// Does not always return String; here it returns T.
~~~

Why?

1. Field `item` is **declared** in Parent<T>.
2. The Reflection `Field` object represents **that exact declaration**, not a new field copy generated by the compiler per subclass.
3. `Child extends Parent<String>` stores the T→String relationship on the **generic superclass edge**.
4. `Field.getGenericType()` reads the **original field signature** in Parent, so it reports T.
5. To deduce the field's type in **Child's context**, you must apply the T→String mapping to the field's Type.

Diagram:

~~~text
Child
  extends Parent<String>
              │
              └── Parent<T> declares field T item
                             │
                             ▼
                       getGenericType() = T
                             │
               substitute T with String in Child context
                             │
                             ▼
                 resolved contextual type = String
~~~

**Do not confuse a type declaration with a contextually resolved type.** That distinction explains why libraries such as type token utilities or JSON binders need generic supertype resolution logic rather than a single Reflection call.

## 15. Outline of Contextual Type-Variable Resolution Algorithm

To answer "in Child, what type does Parent.item have?", you can proceed as follows:

1. Start at `Child.class` with an empty mapping environment.
2. Read `Child.getGenericSuperclass()`: `Parent<String>`.
3. Take raw type Parent and its declared type parameters: `Parent.class.getTypeParameters()` gives `T`.
4. Pair each type parameter with the corresponding actual argument from the ParameterizedType, creating mapping `T → String`.
5. Read `Parent.class.getDeclaredField("item").getGenericType()`, giving T.
6. Substitute T with the mapped value String.
7. If the type is `List<T>`, substitute **inside** the ParameterizedType to produce `List<String>` as the contextual description.
8. If the type is `T[]`, a wildcard, or a nested generic, descend into its components to substitute type variables appropriately.
9. If a multi-level superclass introduces other type variables, loop and **compose mappings**, rather than resolving only one edge.
10. If you encounter an unmapped `TypeVariable` (or wildcards, owner types, etc.), preserve the unknown information semantically instead of forcing it to Object arbitrarily.

Multi-level example:

~~~java
class Base<T> {
    T value;
}

class Middle<U> extends Base<List<U>> {}

class FinalChild extends Middle<String> {}
~~~

Reasoning in FinalChild's context:

~~~text
Middle<U> receives U = String
Base<T> receives T = List<U>
Substitute U = String
=> T = List<String>
=> Base.value is List<String> in FinalChild context
~~~

`Base.class.getDeclaredField("value").getGenericType()` still returns **T**, whereas the expected contextual resolution result is `List<String>`.

**This is an algorithmic model**, not a promise that the JDK provides a built-in `resolveEverything()` button for every type structure. Writing a general Type resolver requires handling `ParameterizedType`, `TypeVariable`, `WildcardType`, `GenericArrayType`, owner types, interfaces, bounds, and special cases.

## 16. Compiler-Generated Bridge Methods

When a class implements a generic interface:

~~~java
interface Source<K, V> {
    V get(K key);
}

final class Child implements Source<String, List<Integer>> {
    @Override
    public List<Integer> get(String key) {
        return List.of(key.length());
    }
}
~~~

After erasure, the interface method takes the compatible bytecode shape `Object get(Object)`, while the source implementation has `List<Integer> get(String)`. The compiler can generate a **bridge method** to preserve overriding/dispatch after erasure.

Reflection provides the APIs:
- `method.isBridge()`: is it a bridge method?
- `method.isSynthetic()`: is it a compiler-generated synthetic method?
- `method.getGenericReturnType()`: the type signature of the specific method represented by that Reflection object.

If you print all of `Child.class.getDeclaredMethods()` without filtering, you may see:
- the real method `get(String)` with generic return `List<Integer>`;
- the bridge method with erased signature like `get(Object)`.

Do not count a bridge as a new business API declared by the developer, and do not let it duplicate entries when documenting method signatures. In the complete example, `isBridge()` detects **one** bridge method.

### 16.1. Inspecting Bytecode

Use:

~~~bash
javap -p -c ReflectionSignaturesDemo
javap -p -v 'ReflectionSignaturesDemo$Child'
~~~

Quote `$` appropriately in your shell; the second command uses standard Bash single-quote syntax. In Windows PowerShell, single quotes likewise prevent variable interpolation. Note that you cannot use the bare class name `Child` when it is a nested type; the binary name contains `$`.

In the bytecode output, relevant attributes can include:
- `Signature`: generic signature metadata;
- `ACC_BRIDGE` and `ACC_SYNTHETIC` for the bridge method;
- erased descriptors.

`javap -v` is useful for comparing **bytecode descriptors** with **generic signatures**; exact byte offsets and method ordering should not be relied upon.

## 17. Constructors and `ParameterizedType` of Other Members

Member signatures are not limited to fields and methods.

`Constructor<?>` can provide:
- `getGenericParameterTypes()`;
- `getGenericExceptionTypes()`;
- `getTypeParameters()`;
- `getAnnotatedParameterTypes()` when type-use annotations matter.

Example generic constructor:

~~~java
class Factory {
    <X extends Number> Factory(X value) {
        System.out.println(value);
    }
}
~~~

When introspected, the constructor's `getTypeParameters()` can return X. A generic constructor does **not** make the entire Factory class generic.

Distinguish:
- Type parameters **of the class** from `Class.getTypeParameters()`.
- Type parameters **of the method** from `Method.getTypeParameters()`.
- Type parameters **of the constructor** from `Constructor.getTypeParameters()`.

For **non-static inner class constructors**, the JVM may add an enclosing instance parameter in bytecode, and how Reflection reports parameters has subtleties; when writing a production analyzer, understand synthetic/mandated parameters rather than relying solely on source parameter counts.

For type-use annotations (such as annotations on type arguments), `getAnnotatedType` and the `getAnnotatedReturnType` / `getAnnotatedParameterTypes` family add annotation metadata views. However, the `getGeneric*` APIs primarily provide **`Type` structure**, not full annotation metadata.

## 18. Type Erasure: Generic Metadata Does Not Replace Runtime Checks

When writing:

~~~java
List<String> names = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();
~~~

the two `ArrayList` objects do not become two different runtime classes per type argument:

~~~java
boolean sameClass = names.getClass() == numbers.getClass();
~~~

The result is true for the two ArrayList objects created above. Reflection calling `names.getClass()` only sees the runtime class ArrayList; it cannot deduce `String` from the source variable that held the object.

Meanwhile:

~~~java
Field f = SomeHolder.class.getDeclaredField("names");
Type declared = f.getGenericType();
~~~

if `SomeHolder` declares the field `List<String> names;`, Reflection can read the `List<String>` metadata from the **field declaration**. That is the distinction:
- **Object reflection**: a runtime object has a class, without carrying all generic arguments.
- **Declaration reflection**: a class file can record the generic signature of a field/method/supertype written in source code.

Reading `List<String>` from metadata is not validation by itself:
- It does not verify every element in the list.
- It does not cure heap pollution caused by raw/unchecked aliases.
- It does not build a complete schema if the signature contains an unresolved TypeVariable.

If you need to process JSON, API payloads, or untrusted data as `List<String>`, you still must validate/copy data or use a binding library with clear runtime validation rules.

## 19. Where `Type.getTypeName()` Is Useful and Where It Falls Short

`Type.getTypeName()` produces a readable name, very useful for logging and diagnostics:

~~~java
Type type = Parent.class.getDeclaredField("items").getGenericType();
System.out.println(type.getTypeName()); // java.util.List<T>
~~~

However, an application needing **structural analysis** should not rely on this string as the sole way to:
- count type arguments;
- match type variables across scopes;
- read owner types;
- determine wildcard upper/lower bounds;
- detect generic array components;
- attach type-use annotations.

Those operations should use the Reflection interfaces and access components through official methods. String representations are meant for **display**, not as a parser replacing the `Type` AST in systems requiring precision.

### 19.1. Avoid Inferring Too Much from `Type` Implementation Names

Calling `type.getClass().getName()` can return an internal JDK class name. Those names are not a high-level Java Reflection contract. Writing:

~~~java
if (type instanceof ParameterizedType p) {
    // Use p.getActualTypeArguments(), p.getRawType(), ...
}
~~~

is far more resilient than comparing names like `sun.reflect...` or another internal class name.

## 20. Common Mistakes

### Mistake A — Using `getSuperclass` to Get Type Arguments

~~~java
Class<?> parent = Child.class.getSuperclass();
// parent does not contain String as an actual type argument.
~~~

**Fix:** use `getGenericSuperclass()` and classify the Type; when you receive a ParameterizedType, read `getActualTypeArguments()`.

### Mistake B — Casting Every `getGenericSuperclass` to ParameterizedType

~~~java
// ParameterizedType p =
//     (ParameterizedType) SomeClass.class.getGenericSuperclass();
~~~

**Fails when** the superclass is non-generic, uses a raw superclass, or has no corresponding superclass. Check `instanceof ParameterizedType` and null first.

### Mistake C — Thinking `getGenericInterfaces` Automatically Returns Indirectly Inherited Interfaces

`getGenericInterfaces()` reflects **direct interfaces**. If a class inherits an implementation from a parent, you must traverse the hierarchy properly to collect all relevant interfaces.

### Mistake D — Thinking Every Actual Type Argument Is a Class

For `Source<String,List<Integer>>`, the second argument is a ParameterizedType, not a `Class<List<Integer>>`. For `List<? extends Number>`, the argument is a WildcardType; for `List<T>`, the argument is a TypeVariable.

### Mistake E — Thinking `Child.getField("item").getGenericType()` Returns String

In the `Parent<T>` / `Child extends Parent<String>` example, Field represents the declaration in Parent, so it still returns T. You need contextual substitution T→String from the generic superclass edge.

### Mistake F — Looking Up a Method Using Generic Parameterized Types

`getDeclaredMethod` takes `Class<?>` objects matching the **erased parameter types**, not ParameterizedTypes. For `transform(List<? extends T>,E)` with E extends Exception, use `List.class, Exception.class`.

### Mistake G — Treating `getMethods` and `getDeclaredMethods` as Having the Same Semantics

One can include public inherited methods, while the other includes only directly declared members. When building an analyzer, choose the right scope and handle overrides as well as bridge/synthetic members.

### Mistake H — Using `TypeVariable.getName` as a Unique Identifier

Many distinct declarations reuse `T`. You must consider `getGenericDeclaration()` and the binding context, not just the character string T.

### Mistake I — Treating `T[]` as a `Class` Array with Runtime Component `T`

`T[]` can be reflected as a GenericArrayType; its erasure can be Object[]. There is no distinct runtime class `T[]` per generic instantiation.

### Mistake J — Treating Generic Metadata as Trustworthy Runtime Data

A field declared as `List<String>` does not prevent raw/unchecked code from corrupting its contents at runtime. Reflection performs no per-element validation.

### Mistake K — Forgetting Synthetic/Bridge Methods

The compiler can generate bridge methods to maintain generic overriding after erasure. Do not emit API reports with duplicate methods without checking `isBridge()`, `isSynthetic()`, and declaring class.

### Mistake L — Ignoring Practical Limits of Generic Signatures

Some classes generated by bytecode tools or stripped of generic signatures may leave Reflection information incomplete or unresolvable as expected. If analyzing external classes, add fallback strategies and appropriate exception handling.

## 21. Checklist for Reading Generic Signatures in Projects

1. Confirm which class/interface `Class<?>` is being analyzed and whether it is from the expected classloader.
2. Use `getGenericSuperclass()` to read the **direct `extends`** edge; check for null, Class, or ParameterizedType.
3. Use `getGenericInterfaces()` to read **direct `implements`/`extends` interface** edges; do not drop non-generic interfaces.
4. If Type is ParameterizedType, read `getRawType()`, `getActualTypeArguments()`, and `getOwnerType()` when applicable.
5. If Type is TypeVariable, inspect `getName()`, `getBounds()`, and `getGenericDeclaration()`.
6. If Type is WildcardType, inspect `getUpperBounds()` and `getLowerBounds()`.
7. If Type is GenericArrayType, descend into `getGenericComponentType()`.
8. Use `Field.getGenericType()` to read a field declaration; consult `Field.getType()` when erasure is needed.
9. Use `Method.getGenericReturnType()`, `getGenericParameterTypes()`, and `getGenericExceptionTypes()` for method signatures.
10. When needing type parameters of a method/constructor itself, call `getTypeParameters()` on that specific declaration object.
11. When analyzing inherited members, check `getDeclaringClass()` and resolve context mappings from subclass to declaring class.
12. Filter or categorize bridge/synthetic methods if documenting developer-written APIs.
13. Remember generic signatures are **declaration metadata**, not runtime validation of arbitrary objects.
14. Do not build a parser on `getTypeName()` when Type interfaces already navigate the structure.
15. When handling complex bytecode, anticipate missing types, classloader boundaries, and malformed signatures rather than assuming every Type can be loaded.
16. Write tests for `List<T>`, nested `Map<String,List<Integer>>`, `T[]`, `? extends`, `? super`, inherited T substitution, and generic methods with `throws E`.

## 22. Self-Check Questions

**1.** `Child extends Parent<String>`. Which API tells you the superclass type argument String?

**Answer:** `Child.class.getGenericSuperclass()`; if the result is a ParameterizedType, read `getActualTypeArguments()[0]`.

**2.** Why doesn't `getSuperclass()` return a ParameterizedType?

**Answer:** `getSuperclass()` has return type `Class<?>` and only provides the runtime class of the superclass; generic arguments are not encoded into that Class value.

**3.** Does `getGenericInterfaces()` return all inherited interfaces or only direct ones?

**Answer:** Only direct interfaces declared by the class/interface. To get the entire hierarchy, traverse superclasses and interfaces further.

**4.** For `Source<String,List<Integer>>`, what kind is the second type argument?

**Answer:** ParameterizedType for List<Integer>, not `Class<List<Integer>>`.

**5.** For `Parent<T>` with field `T item`, what does `getGenericType()` report?

**Answer:** TypeVariable T of Parent's declaration, whereas `getType()` can return Object.class after erasure if T is unbounded.

**6.** Why is `Child.class.getField("item").getGenericType()` still T?

**Answer:** The Field object describes the declaration in Parent<T>. The T→String relationship is stored on Child's generic superclass edge and must be applied separately when resolving contextual types.

**7.** For `T[] buffer`, which interface can Reflection use to represent its generic type?

**Answer:** GenericArrayType; you can read `getGenericComponentType()` to get TypeVariable T.

**8.** For `List<? extends Number>`, how do you read Number?

**Answer:** Obtain Field.getGenericType() as a ParameterizedType; its type argument is WildcardType; read `getUpperBounds()`.

**9.** Why does `getDeclaredMethod("transform", List.class, Exception.class)` use those two Class arguments?

**Answer:** Lookup uses erased formal parameter types, not generic Type objects for `List<? extends T>` and `E`.

**10.** Does `method.getGenericExceptionTypes()` return E or Exception in the transform example?

**Answer:** E as a TypeVariable, whereas `getExceptionTypes()` reflects the erased class corresponding to Exception.

**11.** How do TypeVariable T and TypeVariable E differ?

**Answer:** T belongs to generic class Parent, while E belongs to generic method transform. `getGenericDeclaration()` reveals which declaration owns each variable.

**12.** Can a bridge method appear even when not written in source code?

**Answer:** Yes. The compiler can generate a bridge after erasure to preserve overriding and polymorphism, detectable via `isBridge()`.

**13.** Does having a Type object for `List<String>` verify that every element of a runtime List is a String?

**Answer:** No. Type is declaration metadata; you still need data validation or invariants enforced by trusted APIs.

**14.** Should `getTypeName()` be parsed with regex to resolve arbitrary generic types?

**Answer:** No. It is meant for display; use Type interfaces and official methods to inspect structure, especially nested types, wildcards, and type variables.

**15.** What steps are needed to infer that Base.value is List<String> in `FinalChild extends Middle<String>` and `Middle<U> extends Base<List<U>>`?

**Answer:** Compose mappings across superclass edges: U→String, T→List<U>, then substitute U to get T→List<String>. `Field.getGenericType()` alone only gives declaration T.

## 23. Takeaways

**Java Reflection can read generic signatures of superclasses, interfaces, and members, yet cannot automatically recover all type arguments of every runtime instance.**

The three most important entry points:

~~~text
Class<?> to analyze
    │
    ├── getGenericSuperclass() → Type of direct superclass
    │
    ├── getGenericInterfaces() → Type[] of direct interfaces
    │
    └── declared/inherited member
            ├── Field.getGenericType()
            ├── Method.getGenericReturnType()
            ├── Method.getGenericParameterTypes()
            └── Method.getGenericExceptionTypes()
~~~

Then **classify the Type** into `Class`, `ParameterizedType`, `TypeVariable`, `WildcardType`, or `GenericArrayType` to navigate further.

When you need a member's type in a **subclass context**, remember that Reflection returns the **signature where the member was declared**: `Parent<T>.item` is still T, even though `Child extends Parent<String>`. To get String in Child's context, perform type-variable substitution across the hierarchy.

Finally, do not confuse **generic metadata in a class file** with **runtime object checks**. Understanding that distinction cleanly is the foundation for using Reflection in serializers, object mappers, dependency injection containers, API analyzers, and Java Generics tooling.
