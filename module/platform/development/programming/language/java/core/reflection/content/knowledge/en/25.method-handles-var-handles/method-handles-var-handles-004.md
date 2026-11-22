# Converting `Method`, `Constructor`, and `Field` to Handles with `unreflect`

## 1. Why Is `unreflect` Needed?

In Java, `java.lang.reflect` helps discover class structure at runtime. `Method`, `Constructor<?>`, and `Field` are **metadata** objects describing members; finding the metadata alone has not invoked the method, created an instance, or read/written the field.

`java.lang.invoke` provides `MethodHandle` to represent an invocation operation with a specific signature and `VarHandle` to access variables through access modes. Once a framework already has reflection metadata (for example, after looking up by name, annotation, or configuration), a `MethodHandles.Lookup` object can convert that metadata into a handle:

| Input Metadata | `MethodHandles.Lookup` API | Resulting Handle |
| --- | --- | --- |
| `Method` | `unreflect(Method)` | `MethodHandle` invoking the method |
| `Constructor<?>` | `unreflectConstructor(Constructor<?>)` | `MethodHandle` creating an instance |
| `Field` to read | `unreflectGetter(Field)` | `MethodHandle` reading the value |
| `Field` to write | `unreflectSetter(Field)` | `MethodHandle` writing the value if permitted |
| `Field` needing access modes | `unreflectVarHandle(Field)` | `VarHandle` (Java 9+) |

There is no single generic `unreflect(Field)` overload: you must choose getter, setter, or VarHandle according to your purpose. The word "unreflect" means **converting a reflection representation into an invocable handle**, not "bypassing access control".

Usage flow:

```text
Class<?> -> Method / Constructor<?> / Field
                 |
                 v
         MethodHandles.Lookup
                 |
        check access permissions
                 |
                 v
     MethodHandle or VarHandle
                 |
                 v
       invokeExact / invoke / get / set ...
```

**Two moments to distinguish:** `lookup.unreflect(method)` creates the handle; `handle.invokeExact(...)` actually executes the target method. Similarly, `unreflectConstructor` does not create an object until the handle is invoked.

## 2. Handle Signatures and the Role of the Receiver

`MethodHandle.type()` returns a `MethodType` describing the return type along with the actual parameter types when invoking the handle. Instance members require the target object receiving the call (**receiver**) in the first parameter slot; static members do not take a receiver. Constructors also do not take a receiver because they create the new instance themselves.

Suppose we have:

```java
public static class Person {
    public String name;

    public Person(String name) {
        this.name = name;
    }

    public String greet(String prefix) {
        return prefix + ", " + name;
    }

    public static String language() {
        return "Java";
    }
}
```

This is an illustrative declaration snippet; a complete standalone program follows in the next section.

| Member | Handle signature after `unreflect` |
| --- | --- |
| `Person.greet(String)` | `(Person, String)String` |
| `Person.language()` static | `()String` |
| `Person(String)` constructor | `(String)Person` |
| Getter of `Person.name` | `(Person)String` |
| Setter of `Person.name` | `(Person, String)void` |

Looking up a method via reflection uses its **declared signature**, such as `getMethod("greet", String.class)`, without a receiver parameter. Conversely, when invoking an instance method's MethodHandle, `person` must be the first argument. A setter returns `void`, whereas a constructor handle returns the new instance. For a `static` `Field`, the getter takes no parameters and the setter takes only the new value.

## 3. Complete Java 17+ Program: Method, Constructor, Field

Save the file **`UnreflectDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class UnreflectDemo {
    public static class Person {
        public String name;

        public Person(String name) {
            this.name = name;
        }

        public String greet(String prefix) {
            return prefix + ", " + name;
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        Constructor<Person> constructor =
                Person.class.getConstructor(String.class);
        Method method = Person.class.getMethod("greet", String.class);
        Field field = Person.class.getField("name");

        MethodHandle create = lookup.unreflectConstructor(constructor);
        MethodHandle greet = lookup.unreflect(method);
        MethodHandle getter = lookup.unreflectGetter(field);
        MethodHandle setter = lookup.unreflectSetter(field);
        VarHandle variable = lookup.unreflectVarHandle(field);

        Person person = (Person) create.invokeExact("Lan");
        System.out.println((String) greet.invokeExact(person, "Hello"));

        setter.invokeExact(person, "Mai");
        System.out.println((String) getter.invokeExact(person));

        variable.set(person, "An");
        System.out.println((String) variable.get(person));
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac UnreflectDemo.java
java UnreflectDemo
```

Stdout:

```text
Hello, Lan
Mai
An
```

Explanation in order:

1. `getConstructor(String.class)`, `getMethod("greet", String.class)`, and `getField("name")` retrieve **public** metadata. These calls do not execute the constructor or method.
2. `unreflectConstructor` creates a `(String)Person` handle. Only `create.invokeExact("Lan")` creates the `Person` holding the name `Lan`.
3. `unreflect(method)` creates a `(Person, String)String` handle. `person` is the receiver, and `"Hello"` is the method's declared parameter.
4. `unreflectGetter(field)` produces `(Person)String`. `unreflectSetter(field)` produces `(Person, String)void`. After the setter, `person`'s name changes to `Mai`.
5. `unreflectVarHandle(field)` also obtains a handle for the `name` field. Calling `variable.set(person, "An")` and then `variable.get(person)` causes the last line to print `An`.
6. The example uses a `public` class, constructor, method, and field so it works on the classpath without opening private access.

`main` declares `throws Throwable` because `MethodHandle.invokeExact` calls can propagate errors from the target operation. In production code, handle appropriate error types instead of ignoring all exceptions.

## 4. `invokeExact`, `invoke`, and `MethodType`

`MethodHandle.invokeExact` is a **signature-polymorphic** method. The parameter types **and the expected return type at the call site** must be *exactly* compatible with `handle.type()`. In the program above:

```java
Person person = (Person) create.invokeExact("Lan");
String text = (String) greet.invokeExact(person, "Hello");
```

These are two illustrative lines placed inside `main` of the full example.

The `(Person)` and `(String)` casts are not merely cosmetic: they establish the proper return-type context for `invokeExact`. If you try to receive the constructor result as `Object` while the handle returns `Person`, or pass an `Integer` for a `String` parameter, `WrongMethodTypeException` can occur.

`invoke(...)` permits certain checked type conversions according to method handle rules; `asType(...)` creates a signature-adapted handle when needed. `invokeWithArguments(...)` serves invocations with a dynamic argument list, which is more convenient but typically adds conversion/boxing overhead. Neither form lets you turn an incompatible argument into an arbitrary type.

In another illustrative snippet, a static method requires no receiver:

```java
Method m = Math.class.getMethod("abs", int.class);
MethodHandle abs = MethodHandles.lookup().unreflect(m);
int result = (int) abs.invokeExact(-7);  // 7
```

This snippet must be placed in a method that handles the corresponding checked exceptions and declares `throws Throwable` for `invokeExact`. The signature of `abs` is `(int)int`, not `(Math, int)int`.

For overloaded methods, before converting you must locate the `Method` with the **exact declared parameter types**; `getMethod("f", int.class)` does not automatically resolve to `f(Integer)`. `handle.type()` helps verify the final call structure. For varargs methods, the handle may carry variable-arity behavior; if a fixed signature is needed, consider `asFixedArity()`.

## 5. How Does `unreflect(Method)` Differ from `Method.invoke`?

Both can invoke a method at runtime, but their execution models differ:

| `Method.invoke(receiver, args...)` | `MethodHandle.invokeExact(args...)` |
| --- | --- |
| Invoked through a reflection metadata object | Invoked through a handle with a specific `MethodType` |
| Dynamic arguments via reflection; return value is usually `Object` | Receiver (if an instance member) sits at the front of the handle's parameter list |
| Exceptions thrown by the target method are wrapped in `InvocationTargetException` | Exceptions thrown by target code generally propagate directly through the handle |
| Handling the result may require casting and unboxing | `invokeExact` demands an exact call-site signature |

Converting from `Method` to `MethodHandle` **does not automatically guarantee faster execution**. Efficiency also depends on the JVM/JIT, inlining capability, call site, workload volume, warm-up, and benchmarking methodology. For repeated call paths, avoid repeatedly calling `getDeclaredMethod` and `unreflect` if you can look up once, retain the handle, and reuse it.

## 6. `unreflectConstructor(Constructor<?>)`: Creating Instances from a Constructor

Once you have located the right constructor:

```java
Constructor<Person> constructor =
        Person.class.getConstructor(String.class);
MethodHandle create =
        MethodHandles.lookup().unreflectConstructor(constructor);
Person person = (Person) create.invokeExact("Lan");
```

This snippet is based on `Person` in `UnreflectDemo.java`.

`getConstructor(...)` only finds `public` constructors. `getDeclaredConstructor(...)` finds directly declared constructors, including non-public ones; **finding one does not mean you have permission to invoke it**. `unreflectConstructor(...)` creates a handle whose return type is the instantiated type—here `Person`—even though constructors in Java do not declare a return type.

Constructors are not inherited. Abstract classes and interfaces cannot be instantiated directly in the usual way; a suitable constructor may be absent or inaccessible. Handle conversion can fail due to access restrictions, while instantiation can throw exceptions raised by the target constructor.

Do not confuse Reflection's `Constructor.newInstance(...)` with `MethodHandle.invokeExact(...)`. Both can instantiate objects, but argument/type passing and exception propagation differ. `Class.newInstance()` is deprecated; choose a specific constructor and an explicit error-handling strategy.

## 7. `unreflectGetter`, `unreflectSetter`, and `unreflectVarHandle`

`Field` describes a data field; the API must be chosen according to the operation:

```java
Field field = Person.class.getField("name");
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle getter = lookup.unreflectGetter(field);
MethodHandle setter = lookup.unreflectSetter(field);
VarHandle variable = lookup.unreflectVarHandle(field);
```

This is an illustrative snippet on `Person` from `UnreflectDemo.java`; `getField` can throw `NoSuchFieldException`, and unreflecting can throw `IllegalAccessException`.

**Instance vs static:** an instance getter takes a receiver; an instance setter takes a receiver and a value. A static getter takes no receiver; a static setter takes only the value. Check `getter.type()` / `setter.type()` before building a dynamic invocation adapter.

**Final fields:** Do not infer that having a getter implies having a setter. Creating a setter for a final field can be rejected depending on access rights and JVM rules. A `VarHandle` for a final field typically supports only read modes, and write modes may throw `UnsupportedOperationException`. Do not use deep-reflection tricks to build a mechanism that mutates immutable objects.

**VarHandle and memory ordering:** `VarHandle` provides `varType()`, `coordinateTypes()`, and access modes such as `get`/`set`, `getVolatile`/`setVolatile`, or `compareAndSet` when supported. Do not assume ordinary modes are implicitly volatile or atomic. You can check `isAccessModeSupported(...)`; an unsupported mode for a given field type will fail when invoked.

`VarHandle` suits variable operations with explicit access mode and concurrency requirements. `unreflectGetter`/`unreflectSetter` suit cases where you simply need a read/write handle with a specific `MethodType`.

## 8. `Lookup` Permissions, Private Members, and JPMS

`MethodHandles.lookup()` creates a `Lookup` carrying access permissions according to the **calling class**; `publicLookup()` is more restricted. `unreflect*` still checks permissions appropriate to the member and `Lookup`. For instance, `getDeclaredField("secret")` can return the `Field` of a private field, yet `lookup.unreflectGetter(field)` can throw `IllegalAccessException` if access is lacking.

When deep access is genuinely required, `MethodHandles.privateLookupIn(Target.class, callerLookup)` can produce a `Lookup` with appropriate private permissions if conditions are met. On Java 17+, JPMS also requires the target module to open the relevant package to the calling module when across modules: `exports` does not substitute for `opens`. Grant the minimum privilege needed.

The following standalone example uses the same nest and same module to demonstrate valid private access. Create **`PrivateLookupDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;

public class PrivateLookupDemo {
    private static class Vault {
        private String secret;

        private Vault(String secret) {
            this.secret = secret;
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup =
                MethodHandles.privateLookupIn(
                        Vault.class, MethodHandles.lookup());

        Constructor<Vault> constructor =
                Vault.class.getDeclaredConstructor(String.class);
        Field field = Vault.class.getDeclaredField("secret");

        MethodHandle create = lookup.unreflectConstructor(constructor);
        MethodHandle read = lookup.unreflectGetter(field);

        Vault vault = (Vault) create.invokeExact("protected");
        System.out.println((String) read.invokeExact(vault));
    }
}
```

```bash
javac PrivateLookupDemo.java
java PrivateLookupDemo
```

Stdout:

```text
protected
```

`privateLookupIn` in this example is not a permission-bypass shortcut: because `Vault` is in the same nest, the caller has the required rights. For a class in another module, the package must be properly opened; if permissions are missing, the call can be rejected.

**Illustrative** module declaration example, not a standalone runnable program:

```java
module com.example.domain {
    opens com.example.domain.model to com.example.framework;
}
```

In this case, module `com.example.domain` opens the stated package to module `com.example.framework`, in addition to other lookup/module conditions. Avoid opening an entire module just to handle a single field.

`Method`/`Field` also have `trySetAccessible()` and `setAccessible(true)`. Accessibility overrides can influence how `unreflect` checks a member, while still obeying JPMS and special constraints such as final fields; do not assume `setAccessible(true)` always succeeds or turns every private member public.

## 9. Errors and How to Handle Them

| Stage | Common Error | How to Recognize |
| --- | --- | --- |
| Finding `Method`/constructor | Wrong name or signature | `NoSuchMethodException` |
| Finding `Field` | Wrong field name | `NoSuchFieldException` |
| Converting metadata | Lookup lacks permissions | `IllegalAccessException` |
| Invoking handle | Expected signature mismatch | `WrongMethodTypeException` |
| Invoking handle | Incompatible receiver/cast | `ClassCastException` or corresponding runtime error may occur |
| Invoking target method/constructor | Target code throws an exception | The target error can be propagated directly |
| Using `VarHandle` | Unsupported access mode | `UnsupportedOperationException` |
| Deep reflection via `setAccessible` | Denied by module | `InaccessibleObjectException` may occur |

Do not wrap an entire pipeline in `catch (Exception ignored)`. `invokeExact` can propagate `Throwable` from target code. When handling errors, distinguish **member lookup** errors, **handle linking** errors, and **execution** errors; log method name, parameter types, class loader, and module context when diagnosing.

Three common misconceptions:

1. "Once a `Method` is found, `unreflect` always succeeds." False, because `Lookup` must also hold permissions.
2. "`invokeExact` is like `Method.invoke` and takes an arbitrary `Object[]`." False, because the signature must match `MethodType`.
3. "`unreflectGetter(field)` reads the field immediately." False, because the actual operation happens when the handle is invoked.

## 10. Choosing `unreflect` or `findVirtual`/`findStatic`?

`unreflect` fits when you already hold `Method`, `Constructor`, or `Field` metadata—for example, a framework scanning annotations or selecting members dynamically from configuration. If you already know the name and types and want a handle directly, `Lookup` offers methods like `findVirtual`, `findStatic`, `findConstructor`, `findGetter`, and `findSetter`.

Illustrative example with the `Person` class from `UnreflectDemo.java`:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodHandle direct = lookup.findVirtual(
        Person.class,
        "greet",
        java.lang.invoke.MethodType.methodType(
                String.class, String.class));
```

`direct` also represents a `(Person, String)String` handle. Both approaches are still subject to access checks. When used repeatedly, an appropriate handle can be cached; note that a cache retaining `Class<?>` long-term can pin a plugin's class loader. Verify performance gains with benchmarks using warm-up and realistic workloads; do not claim every method handle call is faster than reflection.

## 11. Practical Workflow and Self-Check

1. Identify the member with the exact name/signature, whether it is instance or static, and which loader/module it uses.
2. Choose a `Lookup` with the required permissions; if encountering non-public members, check `privateLookupIn` and `opens`.
3. Use the appropriate `unreflect*` for `Method`/`Constructor`/`Field` and read/write needs.
4. Inspect `MethodHandle.type()` or `VarHandle.varType()` / `coordinateTypes()` to know the exact arguments.
5. Invoke the handle when the operation is needed; use `invokeExact` for fixed types, or `invoke` if valid adaptation is intentional.
6. Handle lookup errors separately from target-code errors, consider handle reuse, and measure performance before optimizing.

Self-check:

- Why does `unreflect(Method)` not execute the method immediately?
- For an instance method taking one `String`, why does the handle need an extra receiver?
- Does `unreflectConstructor` create a handle or an instance? When is the instance created?
- Which APIs do you use to read/write a `Field`? How do they differ from `VarHandle`?
- Why can `getDeclaredField` succeed while `unreflectGetter` fails?
- How does `invokeExact` differ from `invoke`, and why do the examples cast the result?
- Is `exports` in JPMS enough for deep reflection into a private field?

**Remember:** Reflection provides member metadata; `MethodHandles.Lookup.unreflect*` converts that metadata into a handle with the corresponding access rights. The handle performs the operation only when invoked, according to the exact signature, receiver, and access mode.