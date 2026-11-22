# Member Lookup with Java Reflection: `Member`, `Field`, `Method`, `Constructor`, and `Executable`

## 1. Objectives and Overview

Java Reflection allows a program to **explore class structure at runtime**: which fields, methods, and constructors a class declares, what the parameter types and return types are, whether a member is `public` or `private`, and how to invoke or read values. This topic focuses on **member lookup** through `java.lang.Class` and types in `java.lang.reflect`.

API relationship diagram:

```text
java.lang.reflect.Member (interface)
├── Field implements Member
└── Executable (abstract class) implements Member
    ├── Method extends Executable
    └── Constructor<T> extends Executable
```

- `Member` describes a **member declared by a class/interface** at the general information level: name, declaring class, modifiers, synthetic status.
- `Field` represents a data field, including instance variables and `static` variables.
- `Method` represents a method, including instance, `static`, abstract, and interface default methods.
- `Constructor<T>` represents a class constructor, used to create instances.
- `Executable` groups the common API for the two things that **have a parameter list and can be executed**, namely `Method` and `Constructor`.

A point to distinguish: a `Method` or `Field` object is **metadata and a reflective operation gateway**, not the value of a field or a pre-executed method call. You need an appropriate target object for instance members.

## 2. Quick Type Comparison Table

| Type | Common Way to Obtain | Characteristic Information | Main Operations |
|---|---|---|---|
| `Member` | Supertype/interface of `Field`, `Method`, `Constructor` | `getName()`, `getDeclaringClass()`, `getModifiers()`, `isSynthetic()` | Standardize metadata lookup operations |
| `Field` | `getField` / `getDeclaredField` | `getType()`, `getGenericType()`, `isEnumConstant()` | `get(object)`, `set(object, value)`, primitive getters/setters |
| `Method` | `getMethod` / `getDeclaredMethod` | `getReturnType()`, `getGenericReturnType()`, `isBridge()`, `isDefault()` | `invoke(target, args...)` |
| `Constructor<T>` | `getConstructor` / `getDeclaredConstructor` | `getDeclaringClass()`, parameter list | `newInstance(args...)` |
| `Executable` | Cast/assigned from `Method` or `Constructor` | `getParameterTypes()`, `getParameters()`, `getExceptionTypes()`, `isVarArgs()` | Analyze common signatures and parameters |

`Method` and `Constructor` extend `Executable`, so they can be processed in the same flow to list signatures. `Field` is **not** an `Executable` because data fields do not have a parameter list. `Class<?>` is the starting point: `SomeType.class`, `obj.getClass()`, or `Class.forName("package.Type")` when loading by name is needed.

## 3. Choosing an API Family to Find Metadata

When starting from a `Class<?>`, distinguish **looking up a single member** by name/signature from **listing multiple members** for auditing or building tools.

| Member | Public lookup | Declared lookup |
|---|---|---|
| Field | `getField(name)` / `getFields()` | `getDeclaredField(name)` / `getDeclaredFields()` |
| Method | `getMethod(name, types...)` / `getMethods()` | `getDeclaredMethod(name, types...)` / `getDeclaredMethods()` |
| Constructor | `getConstructor(types...)` / `getConstructors()` | `getDeclaredConstructor(types...)` / `getDeclaredConstructors()` |

For fields and methods, the public lookup family can find inherited public members; the declared family only checks declarations **directly on the type under inspection** but includes all access levels. Constructors are not inherited, so both families search only on the target class. Methods and constructors require the exact sequence of declared parameter types; boxing or overload resolution is not applied during **lookup**. Do not rely on the array order of listing APIs.

Subsequent lessons illustrate public/declared scopes, exact signatures, and hierarchy traversal policies in detail; the rest of this lesson focuses on the **metadata objects** returned by those APIs.

## 4. `Member`: Common Information About a Member

`Member` provides:

- `getName()`: the name of the member; for `Constructor`, the name is usually the full name of the declaring class, not the `<init>` symbol.
- `getDeclaringClass()`: **the class or interface that actually declares the member**, which may differ from the class used to look it up. For example, looking up an inherited method on `Child.class` returns `Parent.class` from `getDeclaringClass()`.
- `getModifiers()`: an `int` containing bits representing modifiers. Use `java.lang.reflect.Modifier` such as `Modifier.isPublic(flags)`, `isPrivate`, `isStatic`, `isFinal`, `isAbstract` instead of comparing bit values directly.
- `isSynthetic()`: the compiler/JVM generated the member for implementation purposes rather than a member written directly in the usual sense in source code.

```java
Member member = String.class.getMethod("length");
System.out.println(member.getName());                    // length
System.out.println(member.getDeclaringClass());          // class java.lang.String
System.out.println(Modifier.isPublic(member.getModifiers())); // true
```

The snippet above assumes importing `java.lang.reflect.Member` and `java.lang.reflect.Modifier`, and running in a context that accepts `NoSuchMethodException`.

Do not confuse `getDeclaringClass()` with `getClass()`. For example, `method.getClass()` returns the runtime type of the **metadata object**, whereas `method.getDeclaringClass()` returns the class containing that method.

## 5. `Field`: Looking Up, Reading, and Writing Fields

`Field` provides:

- `getType()`: the field type as a `Class<?>`, for example `int.class` or `List.class`.
- `getGenericType()`: the generic type as a `Type` when generic signature information is available, for example `List<String>` reflected via `ParameterizedType`; this mechanism does **not** recover erased type parameters of every object at runtime.
- `getAnnotations()` / `getDeclaredAnnotations()`: annotation metadata with runtime retention.
- `isEnumConstant()`: whether the field represents an enum constant.
- `get(obj)`, `set(obj, value)`: read and write the field value. There are variants `getInt`, `setInt`, `getBoolean`... for primitives.

For an **instance field**, pass the object containing the field; for a **static field**, pass `null` in `get(null)` or `set(null, ...)`. Java checks access permissions when performing the operation.

```java
Field name = Student.class.getDeclaredField("name");
boolean allowed = name.trySetAccessible();
if (!allowed) {
    throw new IllegalStateException("Not allowed to enable access");
}
Object current = name.get(student);
name.set(student, "An");
```

This is an illustrative snippet requiring an appropriate `Student` class and `student` variable. `trySetAccessible()` may return `false` when access is not permitted by the module system; `setAccessible(true)` may throw `InaccessibleObjectException` in an equivalent situation. In many cases, only a public API/getter/setter is needed and opening access is unnecessary.

For `final` fields, especially `static final`, do not treat Reflection as a runtime configuration update mechanism: modification has restrictions related to optimizations/JVM and does not guarantee expected behavior.

## 6. `Method` and `Executable`: Signature Analysis and Execution

### 6.1. `Method` Information

`Method` inherits general metadata and adds:

- `getReturnType()`: the erased return type as a `Class<?>`; `void` is represented by `void.class`.
- `getGenericReturnType()`: the generic representation of the return type; you should check `instanceof ParameterizedType` before casting.
- `isBridge()`: whether it is a bridge method generated by the compiler to preserve polymorphism after generic erasure or covariant returns.
- `isDefault()`: whether it is an interface `default` method.
- `getDefaultValue()`: the default value of an annotation element, if any; not a "default return value" for arbitrary methods.
- `invoke(receiver, args...)`: reflectively invokes the method; for `static` methods pass `null` as the receiver, for instance methods pass the appropriate object.

`Method.invoke` returns `Object`: primitive returns are boxed; methods returning `void` yield `null`. If code inside the method throws an error, the original exception is **wrapped** in `InvocationTargetException`; inspect `getCause()` to find the actual cause.

### 6.2. Common `Executable` API

Applies to both `Method` and `Constructor`:

| API | Meaning |
|---|---|
| `getParameterCount()` | Number of parameters in the reflective signature |
| `getParameterTypes()` | `Class<?>[]` array of parameter types (after erasure) |
| `getGenericParameterTypes()` | `Type[]` array of generic parameter types |
| `getParameters()` | `Parameter[]` array to read parameter names, annotations, modifiers, and metadata |
| `getExceptionTypes()` | `Class<?>[]` array of exceptions declared in `throws` |
| `getGenericExceptionTypes()` | Generic types of declared exceptions |
| `isVarArgs()` | Whether the last parameter is declared as varargs (`...`) |
| `getAnnotatedParameterTypes()` | Type-use annotations information for parameter types |
| `getAnnotatedExceptionTypes()` | Type-use annotations for declared exception types |

`Parameter.getName()` **does not preserve names written in source by default**. When compiled normally without `-parameters`, names may be `arg0`, `arg1`; use `javac -parameters` when runtime parameter names are genuinely needed and remember to check `Parameter.isNamePresent()`. Parameter names are not part of how `getMethod` distinguishes overloads.

Reusable utility example:

```java
static void printSignature(Executable executable) {
    System.out.println("Name: " + executable.getName());
    for (Class<?> type : executable.getParameterTypes()) {
        System.out.println("  Parameter: " + type.getTypeName());
    }
}
```

This illustrative function requires importing `java.lang.reflect.Executable`; passing either a `Method` or a `Constructor<?>` is valid.

### 6.3. Varargs and Parameter Arrays

`String... args` is represented as the array type `String[]` in metadata; `isVarArgs()` is the indicator for the original varargs syntax. Do not assume that `Method.invoke` always applies the same varargs rules as a compiler-checked Java call. Provide the number of arguments and types according to the reflective API; with varargs, pack the last parameter into an array of the right type when needed and avoid confusing an array as *one argument* with an array containing *all arguments*.

```java
Method join = Example.class.getMethod("join", String[].class);
Object result = join.invoke(example, (Object) new String[] {"A", "B"});
```

Casting the array to `Object` in the illustrative example passes it as **a single argument** to `invoke`; `Example` and `example` are objects in a hypothetical context.

## 7. `Constructor<T>`: Discovery and Instantiation

Constructors have no return type and are not inherited. `Class<T>.getDeclaredConstructor(Class<?>... parameterTypes)` finds the exact constructor declared by that class, regardless of access level; `getConstructor(...)` finds only `public` constructors.

```java
Constructor<Student> ctor = Student.class.getDeclaredConstructor(String.class);
Student student = ctor.newInstance("Lan");
```

`newInstance` executes the actual constructor and may wrap an exception thrown by the constructor in `InvocationTargetException`. If a `private` constructor lies outside the permitted access scope, access permissions must be handled like `Field`/`Method`; another module may deny enabling access even when calling `setAccessible(true)`. Constructors of abstract classes cannot be used to create instances; enums also cannot be arbitrarily instantiated via `Constructor.newInstance`.

For new programs, direct constructor calls, factory methods, or dependency injection are generally preferred; Reflection is appropriate when the choice of type/constructor is only known at runtime, such as in serializers or test frameworks.

## 8. Complete Java 17+ Example: Lookup, Inheritance, Method Invocation, and Field Reading

Save the following snippet as **`ReflectionMembersDemo.java`**. The program thoroughly demonstrates `Class`, `Member`, `Field`, `Method`, `Constructor`, and `Executable`, while verifying the difference between the class used for lookup and the class declaring an inherited method.

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Executable;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public class ReflectionMembersDemo {
    interface Greeter {
        default String salutation() {
            return "Hello";
        }
    }

    static class Parent {
        public String inherited() {
            return "parent";
        }
    }

    static class Student extends Parent implements Greeter {
        private String name;

        public Student(String name) {
            this.name = name;
        }

        public String greet(String prefix) {
            return prefix + ", " + name;
        }

        public static int twice(int number) {
            return number * 2;
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<Student> type = Student.class;

        Constructor<Student> ctor = type.getDeclaredConstructor(String.class);
        Method inherited = type.getMethod("inherited");
        Method greet = type.getDeclaredMethod("greet", String.class);
        Method twice = type.getDeclaredMethod("twice", int.class);
        Field name = type.getDeclaredField("name");

        System.out.println("Constructor belongs to: "
                + ctor.getDeclaringClass().getSimpleName());
        System.out.println("Field name: " + name.getName());
        System.out.println("Method belongs to: "
                + inherited.getDeclaringClass().getSimpleName());

        Student student = ctor.newInstance("Lan");
        System.out.println("Method invocation: " + greet.invoke(student, "Hi"));
        System.out.println("Static method: " + twice.invoke(null, 21));

        if (!name.trySetAccessible()) {
            throw new IllegalStateException("Cannot access field name");
        }
        System.out.println("Private field: " + name.get(student));

        Executable executable = greet;
        System.out.println("Public visibility: "
                + Modifier.isPublic(greet.getModifiers()));
        System.out.println("Parameter count: " + executable.getParameterCount());
        System.out.println("Interface inheritance: "
                + type.getMethod("salutation").invoke(student));
    }
}
```

Compile and run in the directory containing the file:

```bash
javac ReflectionMembersDemo.java
java ReflectionMembersDemo
```

Expected output:

```text
Constructor belongs to: Student
Field name: name
Method belongs to: Parent
Method invocation: Hi, Lan
Static method: 42
Private field: Lan
Public visibility: true
Parameter count: 1
Interface inheritance: Hello
```

Explanation of notable lines:

1. `getDeclaredConstructor(String.class)` finds the constructor declared in `Student`, then `newInstance("Lan")` creates the object.
2. `getMethod("inherited")` finds the public method from `Parent`. Metadata returns `getDeclaringClass() == Parent.class` even though the lookup started at `Student.class`.
3. `getDeclaredMethod("greet", String.class)` finds the method directly in `Student`; `Method.invoke` calls it on `student` with the argument `"Hi"`.
4. The `static` method `twice` is invoked with receiver `null`, so it returns 42.
5. `name` is a `private` field, so `getDeclaredField` is used; `trySetAccessible()` checks enabling access before `get`. The example declares nested classes in a single program, avoiding dependencies on external modules.
6. The variable `Executable executable = greet` shows that methods share the signature API via `Executable`. `Modifier.isPublic` handles modifier bits properly.
7. The `default` method of `Greeter` can be found via `getMethod` on `Student.class`.

## 9. Access Control, Modules, and Practical Limits

Reflection **does not mean unlimited access**. Three questions must be separated:

1. **Is the metadata found?** `getDeclaredField` can find a `private` field.
2. **Is access/execution permitted?** `get`, `set`, `invoke`, or `newInstance` still checks permissions.
3. **Is *expanding* Reflection access permitted?** `trySetAccessible()`/`setAccessible(true)` is constrained by the Java module system (JPMS) and accessibility between modules/packages.

From Java 9+, modules have strong encapsulation. For named modules, deep access to non-public members from another module usually requires the package to be `opens` to the proper target. For example, in `module-info.java` of the module owning the class:

```java
module school.model {
    opens school.model.internal to school.tooling;
}
```

`opens` serves deep reflection into a package; `exports` serves normal access to public types and **does not replace** `opens` for all private Reflection scenarios. Available options depend on modules and package ownership. Consider a public API before expanding reflection access.

Common exceptions and errors:

| Situation | Exception / Result |
|---|---|
| Wrong method name or wrong signature during lookup | `NoSuchMethodException` |
| Non-existent field name during lookup | `NoSuchFieldException` |
| Operating on a member without permission | `IllegalAccessException`, or corresponding access error |
| Attempting `setAccessible(true)` when the package cannot be opened | `InaccessibleObjectException` (runtime) |
| Incompatible receiver or mismatched arguments | `IllegalArgumentException` |
| Method/constructor internally throws an exception | `InvocationTargetException`; trace via `getCause()` |
| Calling an instance method with receiver `null` | `NullPointerException` |
| Creating an instance via constructor of an abstract type | `InstantiationException` |
| `trySetAccessible()` cannot enable access | Returns `false`; other exceptions may occur depending on API and context |

`ReflectiveOperationException` is a useful superclass for many Reflection checked exceptions such as `NoSuchMethodException`, `NoSuchFieldException`, `IllegalAccessException`, `InstantiationException`, and `InvocationTargetException`, but it does **not** cover all runtime errors in the table above.

For errors from the target method, catch the appropriate exception and inspect the cause:

```java
try {
    method.invoke(target);
} catch (java.lang.reflect.InvocationTargetException ex) {
    Throwable original = ex.getCause();
    System.err.println("Error inside method: " + original);
}
```

This is an error-handling example in a context where `method` and `target` already exist, not standalone code. In production, choose an appropriate log/propagate strategy and avoid losing the stack trace.

## 10. Pitfalls to Remember When Writing Reflection Tools

- **Confusing declared with inherited:** declared metadata only reflects the chosen type; you must decide whether to inspect superclasses and interfaces.
- **Confusing public with accessible:** a `public` member is not automatically callable from every module/context; the declaring class and module policy also matter.
- **Wrong signature due to autoboxing/widening:** `getDeclaredMethod("f", int.class)` cannot arbitrarily be changed to `Integer.class`; specify the exact parameter types.
- **Forgetting generic erasure:** `getType()` returns the raw type such as `List.class`; `getGenericType()` returns `Type` and may require handling `ParameterizedType`, `TypeVariable`, `WildcardType`.
- **Relying on parameter names:** source parameter names usually do not exist without `-parameters`.
- **Assuming every reflected method is user-written:** compiler-generated bridge/synthetic methods may appear; check `isBridge()`, `isSynthetic()` when building an API scanner.
- **Relying on listing order:** if deterministic display is needed, sort explicitly by clear rules, such as name, parameter count, and full names of parameter types.
- **Passing the wrong receiver:** instance methods/fields need a compatible object; static ones use receiver `null`.
- **Overusing reading/writing private or final members:** prefer public contracts; Reflection can break encapsulation and make JDK/module upgrades harder.
- **Allowing untrusted input to arbitrarily choose classes/methods:** dynamic tools must restrict allowed classes, members, operation permissions, and argument types; avoid creating an arbitrary execution API.
- **Ignoring cost:** repeated metadata lookups on hot paths can cause overhead; cache `Method`/`Field`/`Constructor` appropriately when justified by measurement, and do not carelessly cache across multiple class loaders.

## 11. Application Checklist and Self-Check Questions

A practical workflow for building a lookup utility:

1. Determine the `Class<?>` of the object/class to inspect.
2. Choose `getXxx` if you want public members that may be inherited; choose `getDeclaredXxx` if you want members declared directly on the class, regardless of access level.
3. For Method/Constructor, determine the **exact** parameter `Class<?>` objects before lookup; for Field, determine the declared name.
4. Inspect `getDeclaringClass()`, `getModifiers()`, `getType()`/`getReturnType()`, and `Executable.getParameterTypes()` to verify the signature.
5. Only execute `invoke`/`newInstance` or read/write `get`/`set` after knowing the receiver, arguments, and access conditions.
6. Handle lookup errors, access errors, argument errors, and errors thrown **inside** the method/constructor separately.
7. If using a scanner/framework, handle bridge/synthetic members, generic metadata, and display ordering intentionally.

Self-check:

- Why can `Child.class.getMethod("parentPublic")` succeed while `Child.class.getDeclaredMethod("parentPublic")` fails?
- When do you use `Field.get(null)`? When `Method.invoke(null, ...)`?
- How does `getReturnType()` differ from `getGenericReturnType()` for `List<String>`?
- Why does `getDeclaredField("secret")` succeeding still not guarantee `field.get(instance)` will succeed?
- Which exception wraps an exception thrown by the real method, and how do you find the root cause?
- What common ground does `Executable` provide to write one signature-printing function usable for both `Method` and `Constructor`?

Standard documentation for API reference: [`Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html), [`Member`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Member.html), [`Field`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html), [`Method`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html), [`Constructor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html), [`Executable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html).