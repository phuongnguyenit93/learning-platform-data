# Constructor<T> and Non-Inherited Constructors in Java Reflection

In Java Reflection, **java.lang.reflect.Constructor<T>** represents a constructor declared by a class, allowing you to inspect parameters, access levels, annotations, and create instances via **newInstance(...)**. The `<T>` notation in `Constructor<T>` denotes **the type of object that the constructor creates**, typically tied to the `Class<T>` being looked up.

An easy point of confusion is that **a superclass constructor is not inherited by a subclass**. When creating a subclass, the superclass constructor is still **invoked** in the initialization chain (`super(...)`), but it does not become a constructor belonging to the subclass. Reflection reflects this rule: `Child.class.getConstructors()` does not list constructors of `Parent`; `Child.class.getConstructor(...)` also does not find constructors declared only on `Parent`.

This lesson analyzes both parts: how to understand `Constructor<T>` along with generic constructors, and how to properly look up/instantiate according to the superclass–subclass relationship.

## 1. What Does Constructor<T> Represent?

The related types in Java 17:

~~~java
Class<StringBuilder> type = StringBuilder.class;
Constructor<StringBuilder> constructor = type.getConstructor();
StringBuilder value = constructor.newInstance();
~~~

This is an illustrative snippet placed inside a method with `throws ReflectiveOperationException` (or handling checked exceptions); it requires `import java.lang.reflect.Constructor;`.

- `StringBuilder.class` has type `Class<StringBuilder>`.
- `getConstructor()` returns `Constructor<StringBuilder>` because the constructor is requested from `Class<StringBuilder>`.
- `constructor.newInstance()` returns an object of type `StringBuilder`.
- The type argument `T` in `Constructor<T>` **is not the type of an individual constructor parameter** and **is not the constructor's own generic type parameter**.
- `Constructor<T>` extends `Executable`; it has APIs such as `getParameterTypes()`, `getGenericParameterTypes()`, `getTypeParameters()`, `getModifiers()`, `getExceptionTypes()`, `isVarArgs()`, `getDeclaringClass()`.

For example, `Constructor<Child>` represents a constructor of **Child**; it does not describe a constructor inherited from Parent and cannot be used to create an arbitrary other object type.

| Expression | Meaning |
| --- | --- |
| `Class<T>` | An object describing a runtime class; `T` is the class type in the Java generic system |
| `Constructor<T>` | A constructor of the class with type `T`, used to create `T` via `newInstance` |
| `Constructor<?>` | Holds a constructor whose exact class is unknown at compile time; `newInstance` only infers `Object` |
| `Constructor.getTypeParameters()` | Declares type variables **specific to the constructor** such as `<U>`, not `T` of `Constructor<T>` |
| `Class.getTypeParameters()` | Type variables declared by the class, for example `E` in `Box<E>` |

In the generic class `Box<E>`, the expression `Box.class` represents the raw runtime class `Box`; there is no `Box<String>.class` separate from `Box<Integer>.class`. The `String` and `Integer` arguments of an instance normally undergo **type erasure**.

## 2. Constructors Are Not Inherited: Distinguishing "Calling" and "Owning"

According to **Java Language Specification §8.2 and §8.8**, a constructor **is not a class member** in the sense of being inherited; constructors are not inherited, not hidden, and not overridden.

~~~java
class Parent {
    protected Parent(int code) {}
}

class Child extends Parent {
    public Child(String name) {
        super(7);
    }
}
~~~

- `Child(String)` is a constructor **declared by Child**.
- `Parent(int)` belongs to **Parent**, not an overload `Child(int)`.
- `super(7)` is a **constructor invocation** used to initialize the superclass state portion within the same Child object; it does not turn `Parent(int)` into a constructor of Child.
- The fact that `Parent(int)` is `protected` allows calling it via `super` from an appropriate subclass, but does not mean it is `public Child(int)`.
- Constructors have no return type and do not participate in overriding/polymorphic dispatch like instance methods.

A Child object is typically initialized along the constructor chain of its superclasses before running the Child constructor body. However, **the result of `Parent.class.getDeclaredConstructor(int.class)` always describes the constructor of Parent**.

### Why Doesn't a No-Arg Constructor Automatically Appear?

Java only provides a **default constructor** when a class **declares no constructors**. If a class has already declared `Child(String)`, the compiler **does not generate `Child()`**. When a subclass declares no constructors, the subclass's default constructor attempts to call `super()` according to language rules; if the superclass has no available no-arg constructor, compilation fails.

An intentionally uncompilable example:

~~~java
class Base {
    Base(int id) {}
}
class MissingConstructor extends Base {
    // No constructor is declared.
    // The default constructor will attempt to call super(), but Base() does not exist.
}
~~~

The fix is to declare a constructor on the subclass and call super with matching arguments:

~~~java
class Base {
    Base(int id) {}
}
class ValidChild extends Base {
    ValidChild() {
        super(10);
    }
}
~~~

The snippet above only illustrates the constructor relationship in a single compilation unit; it is not a standalone program with `main`. Having a `public`/`protected`/package-private constructor in the superclass does not cause the subclass to inherit them.

## 3. Reflection APIs for Constructor Lookup

The methods on `Class<T>` differ in access level, **with no branch that searches for inherited constructors**:

| API on Class<T> | Result | Searches superclass? |
| --- | --- | --- |
| `getConstructor(Class<?>... parameterTypes)` | `Constructor<T>`: a **public** constructor of the class itself matching the parameter list | **No** |
| `getConstructors()` | `Constructor<?>[]`: all public constructors of the class itself | **No** |
| `getDeclaredConstructor(Class<?>... parameterTypes)` | `Constructor<T>`: a constructor of the class itself, including private/protected/package-private/public | **No** |
| `getDeclaredConstructors()` | `Constructor<?>[]`: all constructors declared in the class, of any access level | **No** |

For `Child` in the previous section:

~~~java
Child.class.getConstructor(String.class);       // valid: public Child(String)
Child.class.getDeclaredConstructor(String.class); // valid
Child.class.getConstructor(int.class);          // NoSuchMethodException
Parent.class.getDeclaredConstructor(int.class); // valid: Parent(int)
~~~

In this API, `parameterTypes` is matched by **order, count, and exact runtime parameter `Class<?>`**. Java Reflection does not apply javac's overload resolution mechanism to automatically find a "closest" constructor; for example, `int.class` differs from `Integer.class`, and `List<String>` is erased to `List.class`. When there is no match, `getConstructor`/`getDeclaredConstructor` throws `NoSuchMethodException`.

When the list is empty, `getConstructor()` looks for a **public no-arg** constructor. You cannot assume every class has this constructor. `getDeclaredConstructor()` can find a private no-arg constructor if declared/actually present; permissions may be required to invoke it.

### Reading Constructor Information

~~~java
Constructor<?> c = Child.class.getDeclaredConstructor(String.class);
System.out.println(c.getDeclaringClass()); // class Child
System.out.println(c.getParameterCount()); // 1
System.out.println(c.isVarArgs());         // false
~~~

This snippet uses `Child` from section 2, after importing `java.lang.reflect.Constructor`; the comments show the meaning, and the output when run in the default package may carry a different class name depending on nesting. `getDeclaringClass()` is the way to verify **which class** a constructor belongs to; the result does not automatically change to the subclass when you use a Parent constructor.

## 4. Standalone Runnable Java 17+ Example

The following example illustrates the `super(...)` chain, lookup failure because constructors are not inherited, and the difference between a generic class's type variable and a generic constructor's type variable.

Save verbatim to **ConstructorInheritanceDemo.java**:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Modifier;
import java.lang.reflect.Type;

public class ConstructorInheritanceDemo {
    public static class Parent {
        public Parent() { this(0); }

        protected Parent(int id) {
            System.out.println("Parent(" + id + ")");
        }
    }

    public static class Child extends Parent {
        public Child(String name) {
            super(7);
            System.out.println("Child(" + name + ")");
        }
    }

    public static class Box<E> {
        private final E value;

        public <U> Box(E value, U marker) {
            this.value = value;
        }

        public E value() { return value; }
    }

    public static void main(String[] args) throws Exception {
        Constructor<Child> childCtor = Child.class.getConstructor(String.class);
        Child child = childCtor.newInstance("Ada");
        System.out.println("child type=" + child.getClass().getSimpleName());
        System.out.println("child public constructors=" + Child.class.getConstructors().length);

        try {
            Child.class.getConstructor(int.class);
        } catch (NoSuchMethodException e) {
            System.out.println("Child(int)=not found");
        }

        Constructor<Parent> parentCtor = Parent.class.getDeclaredConstructor(int.class);
        System.out.println("parent int protected="
                + Modifier.isProtected(parentCtor.getModifiers()));
        System.out.println("parent declaring=" + parentCtor.getDeclaringClass().getSimpleName());

        Constructor<Box> boxCtor = Box.class.getConstructor(Object.class, Object.class);
        Box<?> box = boxCtor.newInstance("payload", 123);
        System.out.println("box value=" + box.value());
        Type[] generic = boxCtor.getGenericParameterTypes();
        System.out.println("box erased=" + boxCtor.getParameterTypes()[0].getSimpleName()
                + "," + boxCtor.getParameterTypes()[1].getSimpleName());
        System.out.println("box generic=" + generic[0].getTypeName()
                + "," + generic[1].getTypeName());
        System.out.println("constructor type parameter="
                + boxCtor.getTypeParameters()[0].getName());
        System.out.println("class type parameter=" + Box.class.getTypeParameters()[0].getName());
        System.out.println("box declaring=" + boxCtor.getDeclaringClass().getSimpleName());
    }
}
~~~

From the directory containing the file, compile with Java 17 and run:

~~~bash
javac --release 17 -encoding UTF-8 ConstructorInheritanceDemo.java
java ConstructorInheritanceDemo
~~~

Stdout (executed with `javac --release 17` on JDK 21):

~~~text
Parent(7)
Child(Ada)
child type=Child
child public constructors=1
Child(int)=not found
parent int protected=true
parent declaring=Parent
box value=payload
box erased=Object,Object
box generic=E,U
constructor type parameter=U
class type parameter=E
box declaring=Box
~~~

Interpretation:

1. `childCtor.newInstance("Ada")` creates **Child**, runs `Parent(int)` due to `super(7)`, then runs the Child constructor body. That **is not constructor inheritance**.
2. `Child.class.getConstructors().length` is 1 because Child only declares one public constructor `Child(String)`; public `Parent()` is not listed for Child.
3. `Child.class.getConstructor(int.class)` fails because Child does not own `Child(int)`, even though Parent has `Parent(int)`.
4. `Parent.class.getDeclaredConstructor(int.class)` finds the protected constructor declared by Parent. `getDeclaringClass()` returns Parent.
5. `Box<E>` has a generic constructor `<U> Box(E value, U marker)`. After erasure, both runtime parameter types are `Object`, so lookup takes `Object.class, Object.class`.
6. `getGenericParameterTypes()` reflects the declared signature `E,U`; `getTypeParameters()` **on Constructor** returns only `U`, whereas `Box.class.getTypeParameters()` returns `E`. `Constructor<Box>` represents the type of class being created (raw Box in the example), **not U**.

The example uses raw `Constructor<Box>` to query `Box.class` directly; in strict generic library code, manage type safety separately and avoid assuming Reflection knows `Box<String>` from runtime `Box.class`. The fact that `newInstance("payload", 123)` accepts String/Integer does not change the erased parameter types.

## 5. Generic Class and Generic Constructor: Three Different Types

Consider:

~~~java
class Packet<E> {
    public <U extends Number> Packet(E payload, U version) {}
}
~~~

There are three concepts:

- `E` belongs to **Packet<E>**, queried by `Packet.class.getTypeParameters()`.
- `U` belongs to **the constructor itself**, queried by `Constructor.getTypeParameters()`; U's bound is Number.
- `T` in the `Constructor<T>` API is **the class being created** (such as Packet), unrelated to the E/U type variable names in the declaration code.

With `Packet.class.getConstructor(Object.class, Number.class)`, the lookup uses **erasure**: E becomes Object because E is unbounded, and U becomes Number because of its bound. Querying `getGenericParameterTypes()` reads the symbols E, U if metadata is preserved in the class file. Note that `Class<Packet>` and `Constructor<Packet>` use **raw Packet** because Java has no `Packet<String>.class` literal.

If you need to describe a parameterized type of a class at runtime, you must hold a `Type`/`ParameterizedType` from a field, method, superclass, or an appropriate type token. `Constructor<T>` alone cannot reconstruct the type arguments of every instance the constructor creates.

### From Generic Signature to Actual Lookup

| Constructor Declaration | `getDeclaredConstructor(...)` accepts |
| --- | --- |
| `Box(E value, U tag)` with unbounded E, U | `Object.class, Object.class` |
| `Packet(E value, U num)`, U extends Number | `Object.class, Number.class` |
| `Child(String name)` | `String.class` |
| `Sample(int count, List<String> values)` | `int.class, List.class` |
| `Logger(String... messages)` | `String[].class` |

These are examples of constructor lookup rules; the classes `Packet`, `Sample`, `Logger` are names describing the corresponding scenarios rather than a fully defined program.

Do not pass wildcards or `ParameterizedType` as arguments to `getDeclaredConstructor`: this API takes `Class<?>...`, matching the post-erasure types.

## 6. Invoking Constructors and Distinguishing Error Categories

After finding `Constructor<T>`, `newInstance(Object... initargs)` creates an object of the declaring class; Reflection does not pass a receiver like `Method.invoke`. Finding metadata is not enough to guarantee access permission or valid arguments.

| Step | Typical Error | Meaning |
| --- | --- | --- |
| Lookup | `NoSuchMethodException` | Wrong runtime type list or no matching constructor |
| Access | `IllegalAccessException`, `InaccessibleObjectException` | Caller lacks permission to invoke or JPMS does not allow opening access |
| Instantiation | `InstantiationException`, `IllegalArgumentException` | Type cannot be instantiated directly or arguments are invalid |
| Constructor execution | `InvocationTargetException` | Code during instance initialization threw an error; inspect `getCause()` |
| Class initialization | `ExceptionInInitializerError` | Static initialization failed before running the constructor |

For a `private` constructor, `getDeclaredConstructor` only retrieves metadata. `trySetAccessible()` can fail if a module does not open the package for deep reflection; `exports` does not replace `opens`. `Class.newInstance()` is a deprecated API, so prefer selecting a signature via `getDeclaredConstructor(...).newInstance(...)` and handling errors by stage.

## 7. Special Cases to Recognize

- **Abstract class** has constructors for subclasses to call, but cannot be instantiated directly; interfaces have no object-creating constructors.
- **Enum** has internal constructors, but `Constructor.newInstance` refuses to create additional enum constants; records have a canonical constructor corresponding to their components, not inherited from `Record`.
- **Non-static inner class** receives the enclosing instance as the first constructor parameter at runtime. For example, `Outer.Inner(Outer, int)` may correspond to the source declaration `Inner(int)`.
- **Varargs** are represented by an array parameter (such as `String[].class`); when calling `newInstance`, pass the entire array as a single argument using an `(Object)` cast when needed.
- **Compiler-generated parameters** can appear with enums, local/anonymous classes, or inner classes. Read `getParameterTypes()` and `Parameter` metadata, rather than inferring from constructor listing order or compiler-generated parameter names.

Subsequent lessons analyze each case with runnable examples. In this lesson, the main point remains that `Constructor<T>` is tied to the declaring class and a superclass constructor never becomes a constructor of a subclass.

## 8. Practical Application Workflow

When a Reflection-based DI container, serializer, CLI parser, or factory needs to create an instance:

1. **Choose the actual class you intend to instantiate.** If you need Child, look up on `Child.class`, rather than grabbing `Constructor<Parent>` and expecting to create Child.
2. **Choose the access scope.** `getConstructor` when you need public API; `getDeclaredConstructor` when code has a valid reason to use non-public constructors.
3. **Determine exact runtime parameters.** Distinguish primitive/boxed, varargs array, erased types, and an inner class's enclosing instance.
4. **Inspect the constructor list if the signature is unknown.** Use `getDeclaredConstructors()`, `getParameterTypes()`, `getModifiers()`, `getGenericParameterTypes()` and filter by defined criteria; do not guess randomly by order.
5. **Check module access.** If private/package-private lives in another named module, consider a factory API or `opens` for the exact package/caller rather than opening the entire module.
6. **Call `newInstance` and catch errors accurately.** `InvocationTargetException.getCause()` helps find errors thrown by the constructor; `NoSuchMethodException` is usually a signature selection error.
7. **Do not confuse the constructor chain with inheritance.** Java will run the superclass constructor while creating a subclass, but Reflection still keeps each constructor belonging to its declaring class.

## 9. Self-Check Questions

**1.** Parent has `public Parent(int id)`, Child extends Parent and only has `public Child()` calling `super(5)`. Can `Child.class.getConstructor(int.class)` find it?

**Answer:** No. Parent(int) is not inherited; Child only declares Child().

**2.** `Constructor<Child> ctor = Child.class.getConstructor()`; can `ctor.newInstance()` return Parent instead of Child?

**Answer:** No. The generic type T and the Constructor's declaring class are Child. If creation succeeds, the object is Child; the Parent constructor may run as part of initializing the Child object.

**3.** `class Box<E> { public <U extends Number> Box(E value, U version) {} }`. Can it be found with `Box.class.getConstructor(String.class, Integer.class)`?

**Answer:** Not according to the declared signature. Erasure is `Object.class, Number.class`. `String` and `Integer` are the argument types of a specific call, not the parameter types in the constructor descriptor.

**4.** Does `Constructor.getTypeParameters()` on the constructor in question 3 return E?

**Answer:** No. It returns U of the constructor; E is a type variable belonging to Box, see `Box.class.getTypeParameters()`.

**5.** After `getDeclaredConstructor()` finds a private no-arg constructor: can `newInstance()` always be called?

**Answer:** No. Metadata lookup and invocation permission are different; appropriate Java access/JPMS opens is required, or use a public factory.

**6.** Why might `Outer.Inner.class.getDeclaredConstructor(int.class)` fail even though the source has `Inner(int)`?

**Answer:** A non-static inner class has an enclosing instance parameter added to its runtime constructor; `Outer.class, int.class` is needed.

**Key takeaway:** `Constructor<T>` carries the type of the class being instantiated; a generic constructor also has its own type variables and is looked up by erased parameter types. Superclass constructors **are invoked when initializing a subclass, but are never inherited**. Always look up constructors on the class you actually want to create.

### References

- Java Language Specification 17, §8.2 (Class Members) and §8.8 (Constructor Declarations): https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html
- Java SE 17, `Class.getConstructor/getDeclaredConstructor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17, `Constructor<T>` and `newInstance`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html
- Java SE 17, `Executable` (type parameters, generic parameter types): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html
- dev.java — Invoking Constructors: https://dev.java/learn/api/reflection-method-handles/reflection/constructors/
