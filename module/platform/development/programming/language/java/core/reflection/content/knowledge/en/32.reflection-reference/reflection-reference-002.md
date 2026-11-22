# Reference Table: Class, Member, Executable, Field, Method, and Constructor (Java Reflection)

## 1. Objective and How to Read the Table

Java Reflection uses metadata objects to describe a program's types and members at runtime. The six names in the title **do not sit at the same level of the type hierarchy**:

- `Class<T>`: describes **a Java type** (class, interface, enum, annotation, record, array, primitive type, or `void`).
- `Member`: common **interface** for field, method, and constructor members in reflection.
- `Executable`: common **abstract class** for methods and constructors; shares APIs for parameters, exceptions, and annotations.
- `Field`: metadata of a **data field**.
- `Method`: metadata of a **method**.
- `Constructor<T>`: metadata of a **constructor** of a class.

The main purpose of the table is to determine: **which object holds what information, which API performs lookup, and which API executes or accesses values**. You should not memorize a list of methods while ignoring the relationships among the types.

## 2. Exact Relationship Diagram

~~~text
java.lang.Object
  |
  +-- java.lang.Class<T>
  |     implements Type, AnnotatedElement, GenericDeclaration, ...
  |     (DOES NOT implement java.lang.reflect.Member)
  |
  +-- java.lang.reflect.AccessibleObject
        implements AnnotatedElement
        |
        +-- java.lang.reflect.Field
        |     implements Member
        |
        +-- java.lang.reflect.Executable (abstract)
              implements Member, GenericDeclaration
              |
              +-- java.lang.reflect.Method
              |
              +-- java.lang.reflect.Constructor<T>

java.lang.reflect.Member  (interface)
  |-- Field implements Member
  |-- Executable implements Member
      |-- Method inherits Member
      +-- Constructor<T> inherits Member
~~~

**Three key takeaways:**

1. `Class<T>` is the entry point for finding metadata and can represent a **nested class**, yet `Class<T>` itself **does not implement the `Member` interface**. Do not confuse the Java language concept of a "member class" with the `java.lang.reflect.Member` type.
2. `Field` and `Executable` are both `AccessibleObject`s and both implement `Member`, but `Field` **does not** extend `Executable`.
3. `Method` and `Constructor<T>` inherit parameter APIs from `Executable`; however, **they do not use the same execution API**: a method calls `invoke`, while a constructor creates an instance via `newInstance`.

`AccessibleObject` does not mean "allowed to access everything by default": it is the base class supporting reflection access checking/adjustment within Java/JPMS limits. `AnnotatedElement` is the interface for annotation-reading methods.

## 3. Comparison Table of the Six Core APIs

| Type | Nature | Represents | Common Ways to Obtain | Characteristic APIs |
| --- | --- | --- | --- | --- |
| `Class<T>` | Class in `java.lang` | A type | `User.class`, `obj.getClass()`, `Class.forName(name)` | `getName`, `getSuperclass`, `getInterfaces`, `getDeclaredMethod`, `getDeclaredField`, `getDeclaredConstructor` |
| `Member` | Interface in `java.lang.reflect` | Common contract for field/method/constructor | Receiving a `Field`/`Method`/`Constructor` as type `Member` | `getDeclaringClass`, `getName`, `getModifiers`, `isSynthetic` |
| `Executable` | Abstract class in `java.lang.reflect` | Common part of method/constructor | Receiving a `Method` or `Constructor` as type `Executable` | `getParameterCount`, `getParameters`, `getParameterTypes`, `getExceptionTypes`, `isVarArgs` |
| `Field` | Class in `java.lang.reflect` | A field declared in a class/interface | `clazz.getField` / `getDeclaredField` | `getType`, `getGenericType`, `get`, `set`; primitive getters/setters like `getInt`/`setInt` |
| `Method` | Class extending `Executable` | A method with name + parameter types + return type | `clazz.getMethod` / `getDeclaredMethod` | `getReturnType`, `getGenericReturnType`, `invoke`, `isBridge`, `isDefault` |
| `Constructor<T>` | Class extending `Executable` | A constructor of class `T` | `clazz.getConstructor` / `getDeclaredConstructor` | `newInstance`, `getDeclaringClass`, parameter APIs from `Executable` |

**There is no common `Member.invoke()` or `Executable.invoke()` for all subtypes.** If you only hold a variable of type `Member`, you can read universal metadata, but you cannot immediately call `get`/`set`/`invoke`/`newInstance` without branching by subtype.

### 3.1. Notes on Other Intermediate Types and Interfaces

- `java.lang.reflect.Type` is the interface representing a **type** in generic reflection. `Class<?>` is one kind of `Type`, whereas `ParameterizedType` and `TypeVariable` are other variants; do not assume every `Type` can be cast to `Class`.
- `GenericDeclaration` applies to `Class`, `Method`, and `Constructor` via `Executable`; it provides `getTypeParameters()` for type variable declarations such as `<T>`.
- `AnnotatedElement` enables reading annotations on classes, fields, methods, and constructors. Annotations on **parameters** can also be retrieved from `Parameter`.
- `Parameter` is metadata for **each individual parameter** of an `Executable`; it is not one of the six types in the table, but is very frequently encountered when calling `getParameters()`.
- `Modifier` is a utility class with `Modifier.isPublic(int)`, `isPrivate(int)`, `isStatic(int)`, etc. It helps interpret the bitmask returned by `Member.getModifiers()`.

## 4. From `Class<?>` to Member: Choosing the Lookup Scope

`Class<?>` is the starting point for obtaining `Field`, `Method`, and `Constructor`. The `getX`/`getDeclaredX` pairs do not change **the resulting object type**; they change **the lookup scope**:

| Kind | Public/member lookup | Directly declared at any access level |
| --- | --- | --- |
| Field | `getField(name)`, `getFields()` | `getDeclaredField(name)`, `getDeclaredFields()` |
| Method | `getMethod(name, types...)`, `getMethods()` | `getDeclaredMethod(name, types...)`, `getDeclaredMethods()` |
| Constructor | `getConstructor(types...)`, `getConstructors()` | `getDeclaredConstructor(types...)`, `getDeclaredConstructors()` |

For fields and methods, public lookup can see inherited members; the declared version only sees declarations directly on the current type. **Constructors are not inherited**, so both constructor groups belong to the queried class itself. Array results do not guarantee order; a method signature requires **name + exact parameter types after erasure**, for instance `int.class` differs from `Integer.class`.

This distinction is a **metadata lookup rule**, not permission to use metadata. A private `Method` may appear from `getDeclaredMethod`, yet `invoke` still requires appropriate access. If you need to know where it was declared, read `member.getDeclaringClass()`; it does not necessarily match the runtime class of the receiver. The program in Section 7 clearly demonstrates `Field`/`Method`/`Constructor` and the corresponding actions of each subtype.

## 5. Member and Executable: Shared APIs and Differences

### 5.1. Member — Minimal Interface

Every `Field`, `Method`, and `Constructor` implements `Member` and provides:

| Method | Interpretation | Notes |
| --- | --- | --- |
| `getDeclaringClass()` | Class/interface declaring the member | Not by default the subclass of the object receiving the call |
| `getName()` | Member name | For `Constructor`, the name is the **binary name of the declaring class** (not a method named `<init>`) |
| `getModifiers()` | Modifier bitmask | Use `Modifier.isPublic/isStatic/isFinal`... |
| `isSynthetic()` | Compiler-generated member with synthetic semantics | Useful when scanning bridge/synthetic members |

**Do not cast every subtype to `Method`.** If scanning code receives a `Member member`, check the kind using `instanceof Field`, `instanceof Method`, `instanceof Constructor<?>` when specialized behavior is needed.

### 5.2. Executable — Parameters Shared by Methods and Constructors

With a variable of type `Executable executable`, the following apply to both methods and constructors:

- `getParameterCount()` and `getParameterTypes()`: count and runtime parameter types (after type erasure).
- `getParameters()`: `Parameter` array with `getName()`, `isNamePresent()`, `getType()`, `getAnnotations()`, etc.
- `getGenericParameterTypes()`, `getAnnotatedParameterTypes()`: generic representations and type-use annotations of parameters.
- `getExceptionTypes()` / `getGenericExceptionTypes()`: exception types declared in the `throws` clause.
- `getParameterAnnotations()`: annotations at each parameter position.
- `isVarArgs()`, `getTypeParameters()`: varargs methods/constructors and type variable declarations.
- `toGenericString()`: signature description including generic information; use for diagnostics, not as a stable parser API.

Original parameter names **are not guaranteed to be preserved** in bytecode when not compiled with `javac -parameters`. In that case, `Parameter.getName()` may be `arg0`, `arg1`, and `isNamePresent()` is false. Parameter counts and types can still be queried as usual.

## 6. Field, Method, and Constructor: Specific APIs and Effects

| Kind | Information Exposed | Action | Important Notes |
| --- | --- | --- | --- |
| `Field` | Field name, modifiers, type (raw/generic), annotations | `field.get(receiver)`, `field.set(receiver, value)`, primitive getters/setters | Accessing a field does not call a getter/setter; an instance field needs an appropriate receiver |
| `Method` | Return type, parameter types, exceptions, bridge/default/synthetic flags | `method.invoke(receiver, args...)` | Exceptions thrown by the target method are wrapped in `InvocationTargetException` |
| `Constructor<T>` | Parameters, exceptions, constructor modifiers/annotations | `constructor.newInstance(args...)` | Creates an object of the declaring class; errors inside the constructor may be wrapped in `InvocationTargetException` |

Commonly asked distinctions:

- `Field.getType()` returns a `Class<?>` of the field type after erasure; `Field.getGenericType()` returns a `Type`, which can be a `ParameterizedType` for `List<String>`.
- `Method.getReturnType()` returns `Class<?>`. `Method.getGenericReturnType()` can return a `ParameterizedType`/`TypeVariable`; constructors **do not** have a return type like methods and **do not have** a `getReturnType()` API.
- `Method.isBridge()` identifies compiler-generated bridge methods, usually to preserve polymorphism with generics/covariant return types; `Method.isDefault()` confirms an interface default method.
- `Constructor.newInstance(...)` should be used instead of `Class.newInstance()` (deprecated old API) because the constructor is explicit and error wrapping is more consistent.
- `Field.get`/`set` and `Method.invoke` for static members take a `null` receiver; instance members require a compatible receiver.
- Being found by `getDeclaredXxx` does not mean you can immediately invoke/get/set: Java access checks and JPMS restrictions still apply.

### 6.1. Access Checks and JPMS

`Field`, `Method`, and `Constructor` extend `AccessibleObject`:

- `canAccess(receiver)` checks accessibility with an appropriate receiver; for static members or constructors, pass `null` as the receiver.
- `trySetAccessible()` attempts to enable bypassing certain Java access checks, returning true/false depending on capability; `setAccessible(true)` can throw `InaccessibleObjectException` if the module does not open the required access.
- Do not automatically call `setAccessible(true)` on every member when scanning: only request permissions actually needed, handle errors, and respect module `exports`/`opens`.

**Reflection access does not replace business authorization.** Being `public` or having readable metadata does not mean the current HTTP request is permitted to invoke the method.

## 7. Complete Java 17+ Example: Six Types in One Program

Save as **MemberTableDemo.java**. The example uses lookup by name/signature to avoid relying on reflection array order, illustrating one private field, one generic field, one method, and one public constructor.

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Executable;
import java.lang.reflect.Field;
import java.lang.reflect.Member;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.lang.reflect.ParameterizedType;
import java.util.List;

public class MemberTableDemo {
    public static final class Sample {
        private final String title;
        public List<String> tags = List.of("reflection");

        public Sample(String title) {
            this.title = title;
        }

        public String echo(String prefix) {
            return prefix + ":" + title;
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<Sample> type = Sample.class;

        Field title = type.getDeclaredField("title");
        Field tags = type.getDeclaredField("tags");
        Method echo = type.getDeclaredMethod("echo", String.class);
        Constructor<Sample> ctor = type.getDeclaredConstructor(String.class);

        System.out.println("Class: " + type.getSimpleName());
        System.out.println("Class is Member: "
                + Member.class.isAssignableFrom(Class.class));
        System.out.println("Field: " + title.getName()
                + " | type=" + title.getType().getSimpleName()
                + " | private=" + Modifier.isPrivate(title.getModifiers()));
        System.out.println("Method: " + echo.getName()
                + " | return=" + echo.getReturnType().getSimpleName()
                + " | params=" + echo.getParameterCount());
        System.out.println("Constructor: " + ctor.getDeclaringClass().getSimpleName()
                + " | params=" + ctor.getParameterCount());

        System.out.println("Field is Executable: "
                + Executable.class.isAssignableFrom(Field.class));
        System.out.println("Method is Executable: " + (echo instanceof Executable));
        System.out.println("Constructor is Executable: " + (ctor instanceof Executable));
        System.out.println("Method is Member: " + (echo instanceof Member));

        ParameterizedType generic = (ParameterizedType) tags.getGenericType();
        System.out.println("Generic field raw=" + tags.getType().getSimpleName()
                + ", actual=" + generic.getActualTypeArguments()[0].getTypeName());
        System.out.println("Inherited public method declares="
                + type.getMethod("toString").getDeclaringClass().getSimpleName());

        Sample sample = ctor.newInstance("Java");
        System.out.println("Invoke result: " + echo.invoke(sample, "Hi"));
    }
}
~~~

Run:

~~~bash
javac --release 17 -encoding UTF-8 MemberTableDemo.java
java MemberTableDemo
~~~

Expected output:

~~~text
Class: Sample
Class is Member: false
Field: title | type=String | private=true
Method: echo | return=String | params=1
Constructor: Sample | params=1
Field is Executable: false
Method is Executable: true
Constructor is Executable: true
Method is Member: true
Generic field raw=List, actual=java.lang.String
Inherited public method declares=Object
Invoke result: Hi:Java
~~~

**Reading the output accurately according to the hierarchy:**

1. `Class is Member: false` proves that the `Class` type does not implement the `Member` interface.
2. The private field `title` can still be found via `getDeclaredField`, but the example does **not** read or modify the private field's value via reflection, so it does not need to enable `setAccessible`.
3. `Method` and `Constructor` are `Executable`, whereas `Field` is not.
4. Field `tags` is declared as `List<String>`: `getType()` returns raw `List`, while `getGenericType()` represents a `ParameterizedType` with argument `java.lang.String`.
5. `type.getMethod("toString")` retrieves a public method inherited from `Object`, unlike `getDeclaredMethod` which only searches `Sample`'s methods.
6. `ctor.newInstance("Java")` creates the object; `echo.invoke(sample, "Hi")` executes the method and returns `"Hi:Java"`.

If you use `type.getField("title")` instead of `getDeclaredField("title")`, you get `NoSuchFieldException` because `title` is private. If you use `type.getDeclaredMethod("toString")`, you also get `NoSuchMethodException` because `Sample` does not declare an override of `toString`.

## 8. Choosing the Right API for Practical Questions

| Your Question | Appropriate API | Why? |
| --- | --- | --- |
| What runtime type does this object belong to? | `object.getClass()` | Obtains the `Class<?>` of the object |
| Find a callable public method by type? | `type.getMethod("save", Id.class)` | Allows inherited public methods |
| Find a directly declared method, including private? | `type.getDeclaredMethod(...)` | Scoped to the exact class; invoke permission is a separate step |
| Read name/modifier/declaring class metadata of multiple members? | Variable/collection of type `Member` | Independent of specific subtype |
| Write shared signature-checking logic for methods and constructors? | Variable of type `Executable` | Shares `getParameters/getExceptionTypes/isVarArgs` |
| Find type information of a field? | `Field.getType/getGenericType` | A field has a data type, not a return type |
| Execute a method? | `Method.invoke` | Receiver + arguments; exceptions from the target method are wrapped |
| Create an object using a constructor? | `Constructor.newInstance` | Do not use `Method.invoke` for constructors |
| Read annotations on a member? | `AnnotatedElement.getAnnotation(...)` | `Class` and member classes both support the appropriate interface |
| Find annotations on a parameter? | `Executable.getParameters()` → `Parameter.getAnnotation(...)` | Parameter is a separate component, not a `Member` |

**Generic case:** if `Type t = field.getGenericType()`, check `t instanceof ParameterizedType` before casting. For a field of type `String`, `getGenericType()` can return `Class<String>`, not `ParameterizedType`. When a generic signature is invalid or missing types, generic metadata APIs can throw other specific errors.

## 9. Common Mistakes and Limitations

1. **Confusing Class with Member:** a nested class is a member in the Java language, but its `Class<?>` metadata cannot be cast to `java.lang.reflect.Member`.
2. **Using Executable for Field:** `Field` does not have `getParameters()`, nor does it have `invoke()`.
3. **Calling a Constructor like a Method:** constructors have no return type or `Method.invoke`; use `Constructor.newInstance`.
4. **Confusing public with declared:** `getDeclaredMethod` does not scan inherited members; `getMethod` does not find private methods.
5. **Confusing metadata with usage permission:** `getDeclaredField` finding a private field does not mean `field.get(receiver)` is always valid.
6. **Guessing reflection array order:** `getDeclaredFields()` and `getDeclaredMethods()` do not guarantee returning elements in source order.
7. **Confusing raw type with generic type:** `getType/getReturnType/getParameterTypes` do not preserve the full parameterized type structure; use `getGenericType/getGenericReturnType/getGenericParameterTypes` when needed.
8. **Misunderstanding constructor names:** in reflection, `Constructor.getName()` is the **binary name** of the declaring class, not the `<init>` name in bytecode.
9. **Using reflection on a hot path without caching:** if you must repeat lookups with the same signature, you can cache `Method/Field/Constructor` by the exact declaring class and signature; measure before optimizing.
10. **Not handling exceptions appropriately:** lookup usually throws `NoSuchFieldException`/`NoSuchMethodException`; invoke/newInstance can throw `IllegalAccessException`, `IllegalArgumentException`, `InvocationTargetException`; target-class exceptions must be inspected via `getCause()`.

## 10. Quick Reference Checklist

- `Class` = **type descriptor and lookup entry point**.
- `Member` = **common metadata interface** for field/method/constructor.
- `Executable` = **common class for method + constructor**, specializing in parameters/exceptions information.
- `Field` = **data**: type, get, set.
- `Method` = **named behavior**: return type, invoke, bridge/default.
- `Constructor` = **object instantiation**: parameters, newInstance.
- `getXxx` generally finds matching public members and may include inherited ones for fields/methods; `getDeclaredXxx` finds directly declared members, including non-public ones.
- Choose APIs by **the semantics of the operation**, and only then consider caching, access permissions, errors, and performance.

**Self-check questions:**

1. Why does `Member.class.isAssignableFrom(Class.class)` return false?
2. If you want to check the parameter count of both methods and constructors, which common type should you use?
3. Why can a private field still be found by `getDeclaredField` yet not necessarily be accessible via `Field.get`?
4. How are `Method.getReturnType` and `Field.getType` similar and different?
5. Why does `getMethod("toString")` succeed, while `getDeclaredMethod("toString")` on `Sample` does not?
6. When reflecting on `List<String>`, why should you inspect `Type`/`ParameterizedType` instead of only `Class<?>`?

### Official API Reference Sources

- `Class` (Java SE 21): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html
- `Member`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Member.html
- `Executable`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Executable.html
- `Field`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html
- `Method`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html
- `Constructor`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Constructor.html
- `AccessibleObject`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html
- `Parameter`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Parameter.html
