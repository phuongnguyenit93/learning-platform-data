# Roles of `Class` and `java.lang.reflect` in Java

## 1. What Is Reflection, and How Do These Two Components Work Together?

In Java, regular code already knows types and methods at compile time: `user.greet("Hello")`. **Reflection** provides a way to **discover the structure of a type at runtime**, and then (if permitted) create objects, read/write fields, or invoke methods through metadata. A typical scenario is a framework that only knows a class name or annotation from configuration, yet must locate a constructor, instantiate an object, and invoke a method when the program runs.

Two conceptual layers have distinct responsibilities:

- **`java.lang.Class<T>`**: an object describing a **runtime type**; it is the entry point for finding information about names, inheritance, interfaces, annotations, fields, methods, and constructors.
- **`java.lang.reflect`**: the API package providing objects that describe **members and type signatures** (`Field`, `Method`, `Constructor`, `Type`...) and reflective operations on them.

`Class` **belongs to `java.lang`**, not `java.lang.reflect`. The general flow is: **obtain `Class<?>` → look up `Method`/`Field`/`Constructor` → check access permissions and types → perform operation → handle exceptions**. Finding a member via metadata does not mean the program automatically has permission to use that member.

## 2. `Class<T>`: Identity and Information of a Runtime Type

A `Class` object is not an instance of the described type. `String.class` is the metadata object of type `Class<String>`; whereas `"abc"` is a `String` instance. Every type known to the JVM has a `Class` representation, including classes, interfaces, enums, records, arrays, primitive types, and `void`.

Ways to obtain `Class`:

```java
Class<String> byLiteral = String.class;

String text = "Java";
Class<? extends String> byObject = text.getClass();

Class<?> byName = Class.forName("java.lang.String");

Class<?> primitiveType = int.class;
Class<?> arrayType = String[].class;
```

The snippet above is only an **illustration within method scope**; the `Class.forName(...)` call must handle `ClassNotFoundException`. `obj.getClass()` reflects the actual runtime type and throws `NullPointerException` if `obj` is `null`. `Class.forName(String)` may trigger class initialization by default; the overload `Class.forName(name, false, loader)` requests loading without immediate initialization.

| `Class` Method | Question Answered |
| --- | --- |
| `getName()`, `getSimpleName()`, `getCanonicalName()` | Corresponding name forms; nested classes have `$` in their binary name |
| `getSuperclass()`, `getInterfaces()` | Direct superclass and direct interfaces |
| `isInterface()`, `isEnum()`, `isRecord()`, `isArray()`, `isPrimitive()` | What kind of type is this? |
| `getComponentType()` | Element type of an array, or `null` if not an array |
| `getModifiers()` | Class modifiers, decoded with `Modifier` |
| `getAnnotations()`, `getDeclaredAnnotations()` | Annotations observable at runtime |
| `isInstance(obj)`, `cast(obj)`, `asSubclass(Base.class)` | Safely checking/expressing type relationships |
| `getClassLoader()`, `getModule()` | Class-loading and module context |

The generic parameter of `Class<T>` provides compile-time type checking: when the exact class is known, prefer `Class<User>`; when accepting a dynamic type, use `Class<?>` instead of the raw type `Class`. Note that **a class's JVM identity also depends on its class loader**: two loaders can define the same class name yet produce two incompatible types. Therefore, comparing only the `getName()` string is not enough to confirm two classes share the same identity.

## 3. `java.lang.reflect`: From Metadata to Operations

| API | Role |
| --- | --- |
| `Constructor<T>` | Describes a constructor; `newInstance(args...)` creates an object |
| `Method` | Describes a method; `invoke(receiver, args...)` calls the method |
| `Field` | Describes a field; `get(receiver)` / `set(receiver, value)` when permitted |
| `Modifier` | Decodes modifier bits, e.g., `Modifier.isPublic(...)` |
| `Executable`, `Parameter` | Shared metadata for methods/constructors and parameters |
| `Type`, `ParameterizedType`, `TypeVariable`, `WildcardType` | Declared generic type signatures |
| `Array` | Dynamically creates or accesses arrays via reflection |
| `Proxy`, `InvocationHandler` | Interface-based dynamic proxies |
| `RecordComponent` | Metadata of each record component |

`Class` returns these metadata objects—for example, `User.class.getDeclaredFields()` returns a `Field[]` array. Reflective objects can hold names, types, modifiers, and annotations; some can also act on instances when access checks permit.

### How Do `get...` and `getDeclared...` Differ?

| Lookup | Public only or all visibilities? | Searches inherited members? |
| --- | --- | --- |
| `getMethod(name, parameterTypes...)` / `getMethods()` | Public | Yes, inherited public methods |
| `getDeclaredMethod(...)` / `getDeclaredMethods()` | All visibilities | No: direct declarations only |
| `getField(name)` / `getFields()` | Public | Yes, inherited public fields |
| `getDeclaredField(name)` / `getDeclaredFields()` | All visibilities | No: direct declarations only |
| `getConstructor(...)` / `getConstructors()` | Public | No: constructors are not inherited |
| `getDeclaredConstructor(...)` / `getDeclaredConstructors()` | All visibilities | No: constructors are not inherited |

**Lookup signatures must be exact.** If there is `setAge(int)`, you must use `getMethod("setAge", int.class)`; `Integer.class` is a different type. Method lookup does not guess overloads from passed-in values; method lookup uses the method name and declared parameter types. The order of arrays returned by `getDeclaredMethods()`, `getMethods()`, etc. **is not guaranteed**, so if deterministic output is needed, sort them by a clear criterion.

## 4. Complete, Runnable Java 17+ Example

This program demonstrates the typical sequence: `Class` → find constructor → instantiate → find method → invoke dynamically → inspect a private field via metadata. To remain portable, the example **does not access private data**, only inspecting the field's name and type.

Create the file `ReflectionDemo.java`:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class ReflectionDemo {
    public static class User {
        private final String name;

        public User(String name) {
            this.name = name;
        }

        public String greet(String prefix) {
            return prefix + ", " + name;
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<User> type = User.class;

        System.out.println(type.getName());
        System.out.println(type.getSuperclass().getSimpleName());

        Constructor<User> constructor =
                type.getDeclaredConstructor(String.class);
        User user = constructor.newInstance("Lan");

        Method greet = type.getMethod("greet", String.class);
        Object result = greet.invoke(user, "Hello");
        System.out.println(result);

        Field field = type.getDeclaredField("name");
        System.out.println(field.getName() + ": " +
                field.getType().getSimpleName());

        System.out.println(type.isInstance(user));
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac ReflectionDemo.java
java ReflectionDemo
```

Stdout:

```text
ReflectionDemo$User
Object
Hello, Lan
name: String
true
```

Exact breakdown of each part:

1. `User.class` returns `Class<User>`; because this is a static nested class, its binary name is `ReflectionDemo$User`. Its direct superclass is `Object`.
2. `getDeclaredConstructor(String.class)` finds the constructor taking exactly one `String`. `newInstance("Lan")` actually runs the constructor to create `User`.
3. `getMethod("greet", String.class)` looks up the public method taking `String`. `invoke(user, "Hello")` calls the method on the `user` instance, returning an `Object` containing the resulting string.
4. `getDeclaredField("name")` returns metadata for the private field even without a getter. `getName()` and `getType()` do not need to read the field's value.
5. `isInstance(user)` checks actual type compatibility of the object.

Here the `User` type is already known at compile time, so direct code `new User("Lan")` and `user.greet("Hello")` remains simpler, easier to refactor, and better type-checked. Reflection is valuable when the type or method is only determined **at runtime**.

## 5. Access Boundaries, Modules, and Exceptions

Reflection is still subject to Java's access rules:

- `getDeclaredField("name")` can locate metadata for a private field, but `field.get(user)` normally throws `IllegalAccessException` when the caller lacks access permission.
- `AccessibleObject.trySetAccessible()` or `setAccessible(true)` lets you **attempt** deep access in cases permitted by the JVM/module. `trySetAccessible()` may return `false`, and `setAccessible(true)` may throw `InaccessibleObjectException`; it is not a mechanism to bypass all module boundaries.
- Under **JPMS**, `exports` allows code outside a module to access a package's public API according to module rules; `opens` allows deep reflection into non-public members for designated modules. Frameworks may need appropriate `opens` packages rather than elevating permissions application-wide.
- For static methods, `method.invoke(null, args...)` uses a `null` receiver; static fields also use `field.get(null)`. Instance members require a receiver of the proper type.
- Do not use reflection to modify `final` fields as a state-update mechanism: writing has its own restrictions, and behavior like a normal setter is not guaranteed.

Errors to recognize:

| Issue | Exception / Cause |
| --- | --- |
| Wrong class name in `Class.forName` | `ClassNotFoundException`; check binary name and class loader |
| Wrong method or field name/signature | `NoSuchMethodException` / `NoSuchFieldException` |
| Caller is not permitted to use the member | `IllegalAccessException` |
| Deep reflection request is rejected | `InaccessibleObjectException` (runtime) |
| Invalid receiver, argument count, or argument types | `IllegalArgumentException` |
| Target constructor/method itself threw an exception | `InvocationTargetException` wraps the real error; inspect `getCause()` |

`ReflectiveOperationException` is a common superclass for many checked exceptions in reflection, but **does not include all runtime errors** such as `IllegalArgumentException` or `InaccessibleObjectException`. At the reflection boundary, log/propagate the original error with context; never silently swallow `InvocationTargetException`. `Class.newInstance()` is deprecated: replace it with `type.getDeclaredConstructor(...).newInstance(...)` to select the constructor explicitly and handle errors better.

## 6. Reflection, Generics, and Annotations

**Type erasure** causes generic type parameter information not to produce a separate runtime class per type argument: for instance, `ArrayList<String>` and `ArrayList<Integer>` share the same runtime class `ArrayList`; `obj instanceof List<String>` is invalid when `obj` has static type `Object` because an unchecked conversion would be needed. Since Java 16, checking against a parameterized type can be valid if the expression's static type already carries enough information, such as checking `List<String> values` with `values instanceof ArrayList<String>`; this still does not check each element's type at runtime. However, **declared signature** metadata can still be retrieved via `Type`: `Field.getType()` typically returns the raw type `List.class`, while `Field.getGenericType()` can return a `ParameterizedType` describing `List<String>` if the field is declared that way. That does not confirm each runtime element is actually a `String`.

**Annotations** are a common reason for reflection in frameworks. `getAnnotation(MyAnnotation.class)` and `isAnnotationPresent(MyAnnotation.class)` look up annotation metadata when the annotation has `@Retention(RetentionPolicy.RUNTIME)`. With `SOURCE` or `CLASS` retention, you cannot assume reflection sees that annotation at runtime. `@Inherited` only affects how class annotations are inherited under specific rules; it does not make method/field annotations automatically inherit in the same way.

**Dynamic proxies:** `java.lang.reflect.Proxy` and `InvocationHandler` can create an implementation for one or more interfaces at runtime to intercept or route calls (for example, RPC, mocks, interceptors). JDK dynamic proxies are not a mechanism to automatically subclass arbitrary concrete classes.

## 7. Practical Applications and Alternatives

Reflection is commonly found in:

- **Dependency injection:** reading constructors, annotations, and parameter types to create and wire dependencies.
- **ORMs, serializers/deserializers:** mapping fields or properties based on metadata under permitted access rights.
- **Test frameworks:** discovering methods with runtime annotations and invoking them by convention.
- **Plugins, metadata explorers, and diagnostic tools:** loading, inspecting, or interacting with types unknown at compile time.

Trade-offs to weigh: reflection weakens compile-time error detection, is fragile to renames/signatures and module boundaries, introduces runtime exceptions, and can incur dynamic lookup/invocation costs. There is no single fixed performance multiplier across all JVMs; avoid repeated metadata lookups on hot paths, cache in a controlled way, and measure performance when needed. If the main goal is dynamic invocation with better performance or clearer access control, look into `MethodHandle` and `MethodHandles.Lookup` in **`java.lang.invoke`** (this package is separate from `java.lang.reflect`).

**Practical rule:** if the type and method are known at compile time, prefer direct Java calls; if only metadata is available at runtime, start with `Class<?>`, locate the right reflective member, check accessibility, invoke deliberately, and handle the underlying error cause.

## 8. Self-Check Questions

1. What does `Class` describe; why does it not belong to the `java.lang.reflect` package?
2. Why can `getDeclaredField("secret")` find a private field while `Field.get(obj)` may still fail?
3. How do `getMethod` and `getDeclaredMethod` differ when a method is declared in a superclass?
4. When looking up `f(int)` with `getMethod`, must you pass `int.class` or `Integer.class`?
5. Why is `exports` in JPMS not enough for a framework to access a package's private fields?
6. Does `getGenericType()` guarantee that the actual data inside a `List<String>` are all `String`?

If you can answer these, you have grasped the two-layer role: **`Class` identifies/discovers types; `java.lang.reflect` describes and operates on members; the JVM still enforces types and access permissions.**