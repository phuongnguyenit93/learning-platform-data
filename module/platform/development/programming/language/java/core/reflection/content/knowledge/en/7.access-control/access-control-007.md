# Packages, declaring classes, and public members in non-public types (Java Reflection)

## 1. Problem: a member being `public` is not enough for access

In Java, the `public` keyword placed on a **method or field** describes the access level of **that member**. It does not automatically turn **the class declaring the member** into a class visible from every package.

For example, Java allows declaring a top-level class without `public`:

```java
package demo.api;

class HiddenGreeting {
    public String greet() {
        return "Hello";
    }
}
```

`HiddenGreeting` has **package-private** access because the class declaration lacks the `public` keyword. The `greet()` method is `public`, yet code in `demo.client` cannot directly declare a variable of type `demo.api.HiddenGreeting` or import that class. When using Reflection, external code can **find the metadata** of `greet()` and still be blocked when **invoking the method**.

Three questions must be kept separate:

1. **Which package is the calling code's context?** Are the two classes in the same package or different packages? Are there module or class loader boundaries?
2. **On which class/interface is the member declared?** Check `Method.getDeclaringClass()` or `Field.getDeclaringClass()`; do not assume the runtime type is the declaring class.
3. **Are both the declaring class and the member accessible from the call site?** `Modifier.isPublic(method.getModifiers())` only answers the **member** part; it does not check class visibility, package/module, and the full access rules.

Principle: **Being able to look up metadata does not mean having permission to use the member via Reflection.**

## 2. Packages and class access levels

A *top-level class* (a class declared directly in a file, not inside another class) can only be `public` or **package-private** in terms of access modifiers; Java does not allow top-level `private` or `protected`.

| Class declaration | Code in the same package | Code in a different package |
| --- | --- | --- |
| `public class Api` | Referenceable if module boundaries are satisfied | Referenceable if the package is properly exported and the API is reachable |
| `class Implementation` | Referenceable under package rules | Cannot directly reference the class in normal Java code |

Java uses the package name declared by `package ...;` to determine access relationships, not accidentally matching directory names. At runtime, package identity also depends on the class loader and module; **two classes with the same package name string do not automatically share package-private access** if they are in different runtime packages.

A `public` member can reside in a package-private class; this is valid. Within the same package, calling code can usually use that class and method. Outside the package, direct access by class name fails at compile time. With Reflection, the error may only appear when `Method.invoke(...)` performs access checks.

For **nested classes**, consider both the chain of enclosing classes and the nested class's modifier. For example, `private static class Impl` can contain `public void run()`, yet the `public` on `run()` does not make `Impl` a type referenceable from outside code. Accessibility is not just the method's modifier.

## 3. Complete Java 17+ example: public method blocked on reflective call

The following example has **two packages** to demonstrate the boundary accurately: `demo.api` keeps the implementation class internal, while `demo.client` is the API consumer. The implementation class is package-private, the implementation method is public; the interface provides a public contract for safe invocation.

Create the structure:

```text
src/
  demo/
    api/
      GreetingService.java
      Services.java
    client/
      Main.java
```

### File `src/demo/api/GreetingService.java`

```java
package demo.api;

public interface GreetingService {
    String greet();
}
```

### File `src/demo/api/Services.java`

```java
package demo.api;

public final class Services {
    private Services() {}

    public static GreetingService create() {
        return new HiddenGreeting();
    }
}

class HiddenGreeting implements GreetingService {
    @Override
    public String greet() {
        return "Hello";
    }
}
```

`Services` is a public factory; `HiddenGreeting` lacks `public`, so it is only a package-private type. `GreetingService` exposes the needed behavior without exposing the implementation class name.

### File `src/demo/client/Main.java`

```java
package demo.client;

import demo.api.GreetingService;
import demo.api.Services;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public class Main {
    public static void main(String[] args) throws ReflectiveOperationException {
        GreetingService service = Services.create();
        Method impl = service.getClass().getMethod("greet");

        System.out.println("Runtime class: " + service.getClass().getName());
        System.out.println("Class public: "
                + Modifier.isPublic(service.getClass().getModifiers()));
        System.out.println("Method public: "
                + Modifier.isPublic(impl.getModifiers()));
        System.out.println("Declared by: " + impl.getDeclaringClass().getName());
        System.out.println("Normal call: " + service.greet());

        try {
            System.out.println("Reflect impl: " + impl.invoke(service));
        } catch (IllegalAccessException e) {
            System.out.println("Reflect impl: IllegalAccessException");
        }

        Method api = GreetingService.class.getMethod("greet");
        System.out.println("Reflect API: " + api.invoke(service));
    }
}
```

In the root directory containing `src`, create directory `out` before running; the following commands use explicit paths, suitable for both standard shells and PowerShell:

```bash
mkdir out
javac --release 17 -d out src/demo/api/GreetingService.java src/demo/api/Services.java src/demo/client/Main.java
java -cp out demo.client.Main
```

Stdout result (verified by compiling and running):

```text
Runtime class: demo.api.HiddenGreeting
Class public: false
Method public: true
Declared by: demo.api.HiddenGreeting
Normal call: Hello
Reflect impl: IllegalAccessException
Reflect API: Hello
```

**Exact analysis of each output line:**

- `service.getClass()` returns `HiddenGreeting.class` because that is the runtime class of the object created by the factory, even though the variable is declared with interface `GreetingService`.
- `Modifier.isPublic(service.getClass().getModifiers())` returns `false` because the implementation class is package-private.
- `getMethod("greet")` **finds the public method**: it only searches metadata of public methods within the API scope, without guaranteeing the caller has permission to invoke the method.
- `impl.getDeclaringClass()` is `HiddenGreeting.class`. The method has the `public` modifier, but its declaring class is not accessible from `demo.client.Main`, so `impl.invoke(service)` throws `IllegalAccessException`.
- The normal Java call `service.greet()` is valid because the static type `GreetingService` is a public interface, the method in the interface is public, and the JVM dispatches to the implementation.
- `GreetingService.class.getMethod("greet")` gets the `Method` **declared on the public interface**. Calling `api.invoke(service)` can access the interface method and then dispatch to the implementation; the result is `Hello`.

This example uses only **classpath/unnamed module**, without needing `module-info.java`. With named modules, `exports`/`opens` rules also need to be considered as discussed later.

## 4. "Runtime class" and "declaring class" are two different concepts

Consider a variable `GreetingService service`:

- **Compile-time type of the variable:** `GreetingService` (public interface).
- **Runtime type of the object:** `HiddenGreeting` (package-private class).
- **Declaring class of a `Method` object:** what `method.getDeclaringClass()` returns. If obtained from `HiddenGreeting`, it is `HiddenGreeting`; if obtained from `GreetingService`, it is `GreetingService`.

Especially with inheritance, `SomeSubclass.class.getMethod("action")` can return a `Method` declared on a superclass or interface instead of on `SomeSubclass`. Compilers and class-generation tools can also add bridge/forwarding methods, so **do not guess the declaring class solely from the class name used when calling `getMethod`**. Always check `getDeclaringClass()` of the actual `Method` object.

Do not confuse these two APIs:

- `method.getDeclaringClass()`: the type **declaring the method**.
- `someClass.getDeclaringClass()`: when called on a `Class` object of a nested/member class, provides information about the enclosing class that declares that type (not "the class declaring a method").

`Field` and `Constructor` also have `getDeclaringClass()`. The declaring class may be non-public even though the constructor/method/field member appears public in metadata.

## 5. `getMethod`, `getDeclaredMethod`, and access checks

| API | What does it return? | Does it bypass access checks automatically? |
| --- | --- | --- |
| `type.getMethod("name", ...)` | Public method within public lookup scope, possibly inherited | No |
| `type.getMethods()` | Array of public methods per the Reflection contract | No |
| `type.getDeclaredMethod("name", ...)` | Method **declared directly** on `type`, regardless of public/private on the method | No |
| `type.getDeclaredMethods()` | Array of directly declared methods, including private/protected/package-private | No |
| `method.invoke(receiver, args...)` | Executes the method if receiver and access permission are valid | **Checks access** when valid suppression is not enabled |
| `method.canAccess(receiver)` | Checks at the current call site whether the member can be accessed on an appropriate receiver | Only checks, does not grant permission |

Seeing a `private` method via `getDeclaredMethod` does not make that method public. Conversely, finding a public method in a non-public class via `getMethod` does not make `invoke` succeed by default.

**The debugging order when encountering an issue** should be: (1) runtime type; (2) `getDeclaringClass()`; (3) modifiers of both declaring class and member; (4) caller's package; (5) module and `exports`/`opens` policy; (6) receiver object, arguments, and execution exceptions.

A cached/stored `Method` object can be invoked from different code locations. Normal access checks are performed against the reflective caller at invocation time; do not assume a `Method` found in a privileged location carries that permission everywhere it is used.

## 6. Clean design solutions

### 6.1. Prefer public contracts

If you control the API, declare the method in a **public interface** or an accessible public class and pass the implementation object through that contract. In the article's example, `GreetingService.class.getMethod("greet")` runs without touching access checks.

This approach also preserves the ability to swap implementations without forcing callers to know package-private class names. Even for public methods in public interfaces/classes, the package still needs to be properly exported when running across named modules.

### 6.2. Expose the method via a public facade

A public facade can **declare** the public method itself and delegate to the internal implementation:

```java
package demo.api;

public final class GreetingFacade {
    public String greet() {
        return new HiddenGreeting().greet();
    }
}
```

This is a **snippet added to the example in section 3**, using `HiddenGreeting` in the same package; save as `GreetingFacade.java` if you want to use it in practice. When the client obtains `GreetingFacade.class.getMethod("greet")`, the declaring class is a public type. This is appropriate if a public class is the desired API form.

Note that if the facade **only inherits** the method from a non-public superclass, you cannot assume the Reflection `Method` obtained will have a public declaring class. Results can be affected by inherited/compiler-generated forwarding methods. For a consistent contract, declare/override the method on the public facade itself and verify `getDeclaringClass()`.

### 6.3. Put calling code in the same package when access is internal

Code in the same runtime package as a package-private class normally has permission to access the class and its public members. Use this for **internal code** when package design allows; do not arbitrarily move client packages just to cross API boundaries. The same package name string with a different class loader/module may not form the same runtime package.

### 6.4. `setAccessible`/`trySetAccessible` only when deep reflection is truly needed

`AccessibleObject.trySetAccessible()` attempts to enable access-check suppression as permitted and returns a boolean; `setAccessible(true)` can throw `InaccessibleObjectException` if disallowed by the Java module system. Whether suppression succeeds depends on the declaring class, caller module, `opens`/`exports` packages, and the specific case.

- On **classpath/unnamed module**, deep reflection on application classes is usually allowed, so `trySetAccessible()` can be observed succeeding.
- Across **named modules**, a package that is only `exports` is not enough for free deep reflection on non-public members/classes; `opens` to the calling module (or equivalent opening configuration) is required for certain suppression cases.
- Do not use trying `setAccessible(true)` as the default fix when a well-designed public interface/facade already exists. There is no guarantee that every access boundary can be crossed on every JDK/module.

## 7. Role of JPMS: `exports` vs `opens`

Since Java 9, in addition to Java language access control, named modules also enforce package boundaries.

- `exports demo.api;` in the providing module: allows modules that read that module to access **public types and public members** of the package per Java rules. It **does not make `HiddenGreeting` public**.
- `opens demo.api;` or `opens demo.api to some.module;`: allows deep reflection within the opened scope; it does not grant compile-time referencing like `exports`.
- A **non-exported** package of a named module can cause Reflection from another module to be blocked even for public classes/methods if corresponding access configuration is missing.
- `--add-exports` and `--add-opens` can be used in controlled integration/analysis scenarios, but must specify the exact source module, package, and target module; do not use them indiscriminately as a long-term API solution.

For example, if `demo.api` resides in named module `demo.library` and `demo.client` in `demo.app`, proper module relationships (`requires` on the caller, `exports demo.api` on the library) are needed for client Java code to use `GreetingService`. Even when the package is exported, `HiddenGreeting` remains package-private, so invoking a `Method` declared directly on that class from another module can still throw `IllegalAccessException`. An **exported public interface** remains the proper API surface.

## 8. Distinguishing lookup errors, access errors, and runtime errors in the method

| Symptom | Common meaning | How to handle |
| --- | --- | --- |
| `NoSuchMethodException` at `getMethod(...)` | No matching public method found for the searched name/signature | Check `Class<?>...` parameter types, overloads, and `getDeclaredMethod` if needed |
| `IllegalAccessException` at `invoke(...)` | Reflection lacks permission to call the method under current access checks | Check `getDeclaringClass()`, package/module, and choose an appropriate public API |
| `InaccessibleObjectException` at `setAccessible(true)` | Cannot enable suppression due to encapsulation limits | Check `opens` configuration and whether deep reflection is necessary |
| `InvocationTargetException` at `invoke(...)` | Target method was invoked and threw an exception itself; root cause is in `getCause()` | Handle logic/runtime error of the target method; do not immediately blame visibility |
| `IllegalArgumentException` at `invoke(...)` | Wrong receiver type or mismatched arguments/count/types | Check the target object and method signature |

For example, the following statement is logically flawed:

> "The method has the `public` modifier and `getMethod` returned successfully, so `invoke` is guaranteed to succeed."

The runnable example in section 3 is a counterexample: both conditions hold, yet `impl.invoke(service)` still fails with `IllegalAccessException` because `HiddenGreeting` is not public to a caller in another package.

## 9. Practical workflow when writing Reflection utilities

1. Identify the **public API contract** the caller is allowed to use (interface or facade).
2. If you must inspect a runtime class, log `type.getName()` and `Modifier.isPublic(type.getModifiers())`.
3. For each method/field, check `getDeclaringClass()` and modifiers of both the member and the declaring type; consider any enclosing classes if it is a nested type.
4. Clearly separate **metadata discovery** from **member invocation/reading**. Having metadata does not substitute for a valid access check.
5. Preserve package/module boundaries whenever possible. For plugins/frameworks requiring deep reflection, document which packages must be `opens` and handle denied access cleanly.
6. Catch `IllegalAccessException` specifically on invoke, separate from `InvocationTargetException`, which is an error thrown by the target method.

## 10. Self-check

1. `class Worker { public void run() {} }` is in `demo.impl` and is a package-private top-level class. Why can't `demo.client` directly write `new Worker()`?
2. Why is `Modifier.isPublic(method.getModifiers()) == true` insufficient to conclude `method.invoke(...)` will succeed?
3. In the `HiddenGreeting` example, do the `Method` objects from `GreetingService.class.getMethod("greet")` and `service.getClass().getMethod("greet")` have the same `getDeclaringClass()`? How do their `invoke` results differ?
4. For named modules, does `exports` turn a top-level package-private class into `public`? When does `opens` take effect?
5. Does `InvocationTargetException` prove that the caller was denied access to the method?

**Guided answers:** (1) a package-private class is not accessible from another package; (2) access permission also depends on the declaring class, caller, and module; (3) they are public `GreetingService` and package-private `HiddenGreeting` respectively—only the call via the interface succeeds in the sample program; (4) no, `opens` enables controlled deep reflection; (5) no, it wraps an exception thrown by the target method.

**Remember:** When Reflection deals with a `public` member whose declaring class is non-public, ask **"Who is `Method.getDeclaringClass()`, and can the caller access that class?"**. Separating the member's modifier, declaring type's accessibility, package, and JPMS explains exactly why metadata can be read while invocation is blocked; a public interface/facade is the clean solution for APIs used across packages.