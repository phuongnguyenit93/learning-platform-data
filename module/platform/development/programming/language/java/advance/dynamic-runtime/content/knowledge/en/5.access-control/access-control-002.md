# 5.2 Checking `public`, `protected`, package-private, and `private` in dynamic calls

**Context:** Java Advance → dynamic-runtime → 5. Access Control.

Calling a method via reflection, proxies, or dynamic loading mechanisms does not make Java's access rules disappear. A program can **find** a `Method` representing a `private` member, yet still be denied when calling it; a method declared `public` can still fail to be called if its **declaring class** is not accessible; and `setAccessible(true)` only works when module boundaries allow it. This lesson focuses on access checks when performing dynamic calls in Java 17+.

## 1. Two independent tasks: discovering a member and being allowed to use the member

Two questions must be separated:

1. **Can the member's metadata be found?** `Class.getMethod(...)`, `getDeclaredMethod(...)`, `getMethods()`, and `getDeclaredMethods()` allow finding members according to different scope sets.
2. **Does the calling code have permission to access that member?** When executing `Method.invoke(receiver, args...)`, reflection checks the access permission of the **caller performing the call**, the class declaring the method, the member's visibility, the package/module context, and an appropriate receiver. If permission is insufficient, the call may throw `IllegalAccessException`.

Example of a declaring class:

```java
package api;

public class AccessTarget {
    public String everyone() { return "public"; }
    protected String descendants() { return "protected"; }
    String neighbors() { return "package"; }
    private String secret() { return "private"; }
}
```

The two lookup APIs have different meanings:

| API | What does it find? | What does it not guarantee? |
| --- | --- | --- |
| `getMethod(name, types...)` | A `public` method visible in the type hierarchy; may be an inherited method | Does not guarantee that the declaring class and method are **accessible from the caller** |
| `getMethods()` | List of `public` methods, including matching inherited methods | Does not mean those methods will definitely `invoke` successfully |
| `getDeclaredMethod(name, types...)` | A method declared **directly** on the class, regardless of `public`/`protected`/package-private/`private` | Does not find methods only present in a superclass; also does not automatically grant permission to call |
| `getDeclaredMethods()` | List of directly declared methods, at all visibility levels | Readable metadata does not mean allowed to execute |
| `Method.invoke(receiver, args...)` | Performs the call on the **selected** `Method` | Performs runtime access checks unless permitted to suppress access checks |

Example:

```java
Method visible = AccessTarget.class.getMethod("everyone");
Method privateMethod = AccessTarget.class.getDeclaredMethod("secret");
```

The snippet above is an **illustrative snippet** in a program that has already imported `java.lang.reflect.Method` and `api.AccessTarget`. It finds both methods, but the `private` member does not automatically become callable.

**Key point:** The lookup `getMethod("secret")` fails with `NoSuchMethodException` because `secret` is not `public`; the lookup `getDeclaredMethod("secret")` succeeds because the class declares that method directly. Failing during **lookup** and failing during **invocation** are two different stages.

## 2. Four access levels in dynamic calls

Assume the class `api.AccessTarget` is `public` and the calling classes are in the `api` package or in another package `client`.

| Method modifier | Called from another class in the same runtime package | Called from a non-subclass in another package | Called from a subclass in another package |
| --- | --- | --- | --- |
| `public` | Allowed, if the class and module allow it | Allowed, if the class and module allow it | Allowed, if the class and module allow it |
| `protected` | Allowed | Not allowed if merely a caller with no inheritance relationship | Conditional: the caller is a subclass; for an instance member, **the receiver must satisfy the protected rule** |
| No modifier written (package-private) | Allowed | No | No, inheritance alone does not grant package-private access across packages |
| `private` | No, unless the caller has appropriate private access (for example, same nest) | No | No: a subclass does not automatically have access to the parent's `private` members |

The columns assume `setAccessible(true)` is not enabled and no additional module restrictions are encountered. Two principles to remember:

- **Package-private** (also called package access) is the case where **no** visibility modifier is written before the member. It is not a `package-private` keyword in source code.
- **`protected` when in another package does not mean "a subclass can call it on any receiver"**. For an instance method of a superclass, a subclass caller can only access it through a receiver of an appropriate type (typically that subclass itself or a subtype); one cannot take an arbitrary superclass instance and call it freely.

How the JVM understands **the same runtime package** also depends on the defining class loader: essentially using **(package name, defining class loader)**. Two classes that both declare `package api;` but are defined by two different defining loaders do not automatically have package-private privileges with each other. In JPMS, module exports/opens add cross-module access barriers.

### `public`: public member, but the class may be hidden

When the class `PackageHidden` is package-private while the method `display()` is `public`, code in another package can receive an `Object` and use `getClass().getMethod("display")` to obtain metadata. However, `Method.invoke` can still throw `IllegalAccessException`, because the **declaring class** of the method is not public to the caller. Putting `public` before a method does not make its enclosing class `public`.

### `protected`: checking subclass permission and receiver

With `AccessTarget.descendants()` declared `protected`:

- Another class in the `api` package can call it via an appropriate `AccessTarget` instance.
- `client.Demo` is not a subclass, so it is denied.
- `client.SubclassProbe extends AccessTarget` can use `descendants()` on `this` itself.
- Even inside the subclass, attempting to call the same method via a **`new AccessTarget()`** object can still be denied because the receiver does not belong to an appropriate subclass.

Distinguish between **method inheritance**, **being allowed to access the method**, and **receiver type**. For `protected static`, corresponding access rules apply, but there is no receiver instance; the example in this lesson uses an instance method to make the receiver constraint clear.

### `private`: restricted to class/nest, not the entire package

`private` cannot be accessed merely because the caller is in the same package or is a subclass. Java 11+ has the concept of **nestmates** (classes in the same nest, such as an outer class and appropriate nested classes), which have private access to each other without needing to call `setAccessible`. Therefore, the accurate phrasing is "private is for the class and permitted nest members", rather than "all other classes can absolutely never access it".

For ordinary classes outside the nest, `getDeclaredMethod` can read the metadata of a `private` method, but `invoke` is not yet allowed to execute unless valid permission to suppress checks has been granted.

## 3. Standalone Java 17 program: testing all four access levels

Create the directory structure and five files as follows. The example intentionally uses **two packages** on the **classpath (unnamed module)** to separate Java language access rules from module restrictions; the JPMS part will be verified separately in section 6.

```text
access-demo/
├── api/
│   ├── AccessTarget.java
│   ├── SamePackage.java
│   └── PublicFactory.java
└── client/
    ├── SubclassProbe.java
    └── Demo.java
```

### File `api/AccessTarget.java`

```java
package api;

public class AccessTarget {
    public String everyone() { return "public"; }
    protected String descendants() { return "protected"; }
    String neighbors() { return "package"; }
    private String secret() { return "private"; }
}
```

### File `api/SamePackage.java`

Calling code is in the **same package `api`** as the target class:

```java
package api;

import java.lang.reflect.Method;

public final class SamePackage {
    public static void check(AccessTarget target) throws Exception {
        Method protectedMethod = AccessTarget.class.getDeclaredMethod("descendants");
        Method packageMethod = AccessTarget.class.getDeclaredMethod("neighbors");
        Method privateMethod = AccessTarget.class.getDeclaredMethod("secret");

        System.out.println("same-package protected=" + protectedMethod.invoke(target));
        System.out.println("same-package package=" + packageMethod.invoke(target));
        try {
            privateMethod.invoke(target);
        } catch (IllegalAccessException expected) {
            System.out.println("same-package private=IllegalAccessException");
        }
    }
}
```

### File `client/SubclassProbe.java`

A subclass in **another package** uses `protected` access validly with `this` as the receiver, but cannot use that permission to call on an arbitrary `AccessTarget` instance:

```java
package client;

import api.AccessTarget;
import java.lang.reflect.Method;

public class SubclassProbe extends AccessTarget {
    public void check() throws Exception {
        System.out.println("subclass direct=" + descendants());

        Method method = AccessTarget.class.getDeclaredMethod("descendants");
        System.out.println("subclass this=" + method.invoke(this));
        try {
            method.invoke(new AccessTarget());
        } catch (IllegalAccessException expected) {
            System.out.println("subclass base-instance=IllegalAccessException");
        }
    }
}
```

### File `api/PublicFactory.java`

A `public` method inside a class `PackageHidden` that is **not `public`**:

```java
package api;

class PackageHidden {
    public String display() {
        return "public method in package-private class";
    }
}

public class PublicFactory {
    public static Object hidden() {
        return new PackageHidden();
    }
}
```

### File `client/Demo.java`

```java
package client;

import api.AccessTarget;
import api.PublicFactory;
import api.SamePackage;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class Demo {
    private static void attempt(String label, Method method, Object receiver)
            throws InvocationTargetException {
        try {
            System.out.println(label + "=" + method.invoke(receiver));
        } catch (IllegalAccessException expected) {
            System.out.println(label + "=IllegalAccessException");
        }
    }

    public static void main(String[] args) throws Exception {
        AccessTarget target = new AccessTarget();
        Method publicMethod = AccessTarget.class.getMethod("everyone");
        Method protectedMethod = AccessTarget.class.getDeclaredMethod("descendants");
        Method packageMethod = AccessTarget.class.getDeclaredMethod("neighbors");
        Method privateMethod = AccessTarget.class.getDeclaredMethod("secret");

        attempt("other-package public", publicMethod, target);
        attempt("other-package protected", protectedMethod, target);
        attempt("other-package package", packageMethod, target);
        attempt("other-package private", privateMethod, target);

        try {
            AccessTarget.class.getMethod("secret");
        } catch (NoSuchMethodException expected) {
            System.out.println("getMethod private=NoSuchMethodException");
        }

        SamePackage.check(target);
        new SubclassProbe().check();

        System.out.println("private canAccess before=" + privateMethod.canAccess(target));
        System.out.println("private trySetAccessible=" + privateMethod.trySetAccessible());
        System.out.println("private canAccess after=" + privateMethod.canAccess(target));
        attempt("private after override", privateMethod, target);

        System.out.println("package trySetAccessible=" + packageMethod.trySetAccessible());
        attempt("package after override", packageMethod, target);

        Object hidden = PublicFactory.hidden();
        Method onHidden = hidden.getClass().getDeclaredMethod("display");
        attempt("public method on hidden class", onHidden, hidden);
        System.out.println("hidden trySetAccessible=" + onHidden.trySetAccessible());
        attempt("hidden after override", onHidden, hidden);
    }
}
```

From the `access-demo/` directory, use JDK 17+ and compile at Java 17 level:

```bash
javac --release 17 -encoding UTF-8 -d out api/AccessTarget.java api/SamePackage.java api/PublicFactory.java client/SubclassProbe.java client/Demo.java
java -cp out client.Demo
```

**Exact stdout:**

```text
other-package public=public
other-package protected=IllegalAccessException
other-package package=IllegalAccessException
other-package private=IllegalAccessException
getMethod private=NoSuchMethodException
same-package protected=protected
same-package package=package
same-package private=IllegalAccessException
subclass direct=protected
subclass this=protected
subclass base-instance=IllegalAccessException
private canAccess before=false
private trySetAccessible=true
private canAccess after=true
private after override=private
package trySetAccessible=true
package after override=package
public method on hidden class=IllegalAccessException
hidden trySetAccessible=true
hidden after override=public method in package-private class
```

**Reading the output by boundary:**

1. `client.Demo` outside `api` can only call `everyone()` under normal access permissions. Reflection finds the metadata of the remaining three methods, but `invoke` from `Demo` throws `IllegalAccessException`.
2. `getMethod("secret")` throws `NoSuchMethodException`, because this API looks for `public` methods. The existence of `secret` is confirmed with `getDeclaredMethod("secret")`; the two lookup operations have different scopes.
3. `api.SamePackage` can call `protected` and package-private via reflection thanks to being in the same runtime package; it still cannot call `private` because it is not the same nest/authorized caller.
4. `client.SubclassProbe` can call `descendants()` on `this` both via direct Java syntax and `Method.invoke`. However, a receiver of `new AccessTarget()` does not satisfy the condition for a `protected` instance method in another package.
5. `privateMethod.canAccess(target)` is initially `false`. In the **unnamed module** example, `trySetAccessible()` is allowed to enable suppressing access checks, after which `canAccess(target)` is `true` and the `private` call succeeds.
6. `PublicFactory.hidden()` returns an instance of a package-private class. The `display()` method has the `public` modifier, but an external caller cannot access the **class** `PackageHidden`, so `invoke` initially fails. With `trySetAccessible()` allowed in the unnamed module, the subsequent call succeeds.

This is an example of **language access checks** and suppressing access checks in a classpath environment. The result `trySetAccessible=true` will not hold in every JPMS program: the `opens`/`exports` permissions of a named module must be considered.

## 4. Using `canAccess`, `trySetAccessible`, and `setAccessible` for their intended purpose

`AccessibleObject` is the superclass of `Method`, `Constructor`, and `Field`. The three commonly used operations have different meanings:

| API | Meaning | Result/exception |
| --- | --- | --- |
| `method.canAccess(receiver)` | Asks **right at the current caller** whether the method can be accessed with this receiver, taking the current suppress-checks state into account | Returns `boolean`; may throw `IllegalArgumentException` if the receiver is invalid |
| `method.trySetAccessible()` | **Attempts to enable** suppressing Java language access checks if the module and current permissions allow it | `true` if successful; `false` when it cannot be enabled because the module is not appropriately opened; may throw `SecurityException` in an environment with a SecurityManager applied |
| `method.setAccessible(true)` | Requests enabling suppress checks | Succeeds if allowed; if it violates module encapsulation, may throw `InaccessibleObjectException` (unchecked); security-controlled environments may throw `SecurityException` |

Do not use `setAccessible(true)` merely to **discover** permissions; try `canAccess(receiver)` when you need to know whether a normal call is allowed. `trySetAccessible()` is usually better when attempting reflective access that is not guaranteed in advance, because it clearly expresses the outcome when the module does not allow it.

Example usage for handling errors in existing code (snippet, **not a standalone program**):

```java
Method method = target.getClass().getDeclaredMethod("secret");
if (method.canAccess(target)) {
    Object result = method.invoke(target);
    System.out.println(result);
} else if (method.trySetAccessible()) {
    Object result = method.invoke(target);
    System.out.println(result);
} else {
    throw new IllegalStateException("Module/package does not allow deep reflection");
}
```

**Do not draw wrong conclusions from `canAccess`:** for an instance method, the passed receiver must be a compatible object; for a static method, the `receiver` argument to `canAccess` is `null`. Neither `setAccessible` nor `trySetAccessible` modifies bytecode, changes the original modifiers, or grants unconditional access across named modules. Suppressing checks applies to that specific `Method`/`Field`/`Constructor` object; it does not mean the entire program is automatically granted the same permission.

**A special corner case with `private`:** if the caller and the declaring class are nestmates, `canAccess` can be `true` even before calling `trySetAccessible`. Conversely, in the `SamePackage` example, the two classes only share a package, so `private` is still denied.

## 5. Each check occurs at a different time

The typical sequence when calling a method via reflection:

```text
Class<?> / class name
      |
      v
getMethod / getDeclaredMethod
      |  name + signature lookup: NoSuchMethodException if not found
      v
Method metadata
      |
      v
canAccess / trySetAccessible (if needed)
      |  checks caller, visibility, runtime package, module
      v
method.invoke(receiver, args...)
      |  IllegalAccessException if no permission
      |  IllegalArgumentException if receiver/arguments are incompatible
      |  NullPointerException if instance receiver is null
      v
Method body executes
      |  exception thrown by target code -> InvocationTargetException
      v
Return value (boxed if returning primitive)
```

Error distinction table:

| Error | Stage | Practical meaning |
| --- | --- | --- |
| `NoSuchMethodException` | Lookup | No member matches the name, lookup kind, and parameter type list; **not** a missing invoke permission error |
| `IllegalAccessException` | `Method.invoke` / `Constructor.newInstance` | Caller lacks sufficient permission by visibility or module |
| `InaccessibleObjectException` | `setAccessible(true)` | The Java module system does not allow suppressing checks for this member/package |
| `IllegalArgumentException` | `invoke` | Receiver is not of an appropriate type, wrong argument count/types, or invalid argument conversion |
| `NullPointerException` | `invoke` instance method with null receiver | No target instance; for a static method, a null receiver is allowed |
| `InvocationTargetException` | Body of method/constructor has executed | Exception thrown by target code is wrapped; check `getCause()` |
| `IllegalAccessError` | Linkage of compiled bytecode | A linkage error in direct access/JVM, **different** from core reflection's checked `IllegalAccessException` |

The difference between `IllegalAccessException` and `InvocationTargetException` is very useful: `IllegalAccessException` is a lack of permission **before executing the method body**; if the method body itself throws `IllegalArgumentException`, the reflection caller will see `InvocationTargetException` with cause `IllegalArgumentException`.

A `public` method can be looked up successfully, yet `invoke` still fails because the declaring class is not public or the package is not exported by the module. Therefore, do not infer solely from `Modifier.isPublic(method.getModifiers())`; one must consider **class**, **caller**, **receiver**, **runtime package**, and **module**.

## 6. Java Platform Module System: `exports` vs `opens`

With Java 9+ (including Java 17), a **named module** adds access control beyond language visibility:

- `exports p`: allows other modules to access **public types** in package `p` and public/protected members permitted under Java language rules; does not automatically grant permission to call private members via deep reflection.
- `opens p`: allows other modules **deep reflection** into package `p`, within the scope of the corresponding reflective API checks, including non-public declarations when suppressing access checks is valid; does not automatically turn non-public classes into Java APIs for direct reference syntax.
- `opens p to m`: opens package `p` specifically to module `m`.
- In the **unnamed module** (classpath), packages are open for deep reflection by default module mechanics; that is why the demo in section 3 can have `trySetAccessible() == true`.
- With a **named module**, to use `setAccessible(true)` to bypass language access checks of a non-public member in another module, the package must be appropriately opened (or satisfy another condition allowed by the API, such as being in the same module). `exports` alone is not enough.

Example of a module that can express intent:

```java
module inventory.core {
    exports inventory.api;
    opens inventory.internal to inventory.tools;
}
```

This `module-info.java` snippet is **illustrative**; a complete project must actually have the packages/modules mentioned above. `inventory.tools` is allowed deep reflection into `inventory.internal`, while other modules do not have that permission by default. `exports inventory.api` is for the public API.

### Named module experiment: same method, different package opening permissions

Create a second project structure:

```text
modules-demo/
└── src/
    ├── alpha/
    │   ├── module-info.java
    │   └── alpha/
    │       └── PublicApi.java
    └── beta/
        ├── module-info.java
        └── beta/
            └── Main.java
```

**File `src/alpha/module-info.java`:**

```java
module alpha {
    exports alpha;
}
```

**File `src/alpha/alpha/PublicApi.java`:**

```java
package alpha;

class Hidden {
    public String message() { return "hidden"; }
}

public class PublicApi {
    public static Object hidden() { return new Hidden(); }
}
```

**File `src/beta/module-info.java`:**

```java
module beta {
    requires alpha;
}
```

**File `src/beta/beta/Main.java`:**

```java
package beta;

import alpha.PublicApi;
import java.lang.reflect.Method;
import java.lang.reflect.InaccessibleObjectException;

public class Main {
    public static void main(String[] args) throws Exception {
        Object hidden = PublicApi.hidden();
        Method method = hidden.getClass().getMethod("message");
        try {
            System.out.println("invoke=" + method.invoke(hidden));
        } catch (IllegalAccessException expected) {
            System.out.println("invoke=IllegalAccessException");
        }

        System.out.println("trySetAccessible=" + method.trySetAccessible());
        try {
            method.setAccessible(true);
            System.out.println("setAccessible=success");
        } catch (InaccessibleObjectException expected) {
            System.out.println("setAccessible=InaccessibleObjectException");
        }

        if (method.canAccess(hidden)) {
            System.out.println("after-open=" + method.invoke(hidden));
        }
    }
}
```

Compile for Java 17 from the `modules-demo/` directory:

```bash
javac --release 17 --module-source-path src -d out src/alpha/module-info.java src/alpha/alpha/PublicApi.java src/beta/module-info.java src/beta/beta/Main.java
java --module-path out -m beta/beta.Main
```

**Stdout when module `alpha` only `exports alpha`, not `opens`:**

```text
invoke=IllegalAccessException
trySetAccessible=false
setAccessible=InaccessibleObjectException
```

Even though `alpha` exports the package, the `Hidden` class is still package-private. Therefore `getMethod("message")` finds the public method, but cannot invoke it from module `beta` using normal access permissions. At the same time, `beta` does not have deep-open permission for that package, so `trySetAccessible()` returns `false` and `setAccessible(true)` throws `InaccessibleObjectException`.

Run again **without changing the source** by granting package-open permission at JVM launch:

```bash
java --module-path out --add-opens alpha/alpha=beta -m beta/beta.Main
```

**Stdout with `--add-opens`:**

```text
invoke=IllegalAccessException
trySetAccessible=true
setAccessible=success
after-open=hidden
```

`--add-opens` allows `beta` to perform deep reflection into package `alpha`. The first call still lacks language permission, but after `trySetAccessible()` succeeds, the call can execute. In real projects, prefer declaring `opens ... to ...` with an explicit scope according to the module contract rather than opening permissions broadly with JVM flags; `--add-opens` is useful when debugging or integrating legacy libraries.

**Do not confuse `--add-exports` and `--add-opens`:** the first flag supports accessing the **public API** of an unexported package in the normal way; the second flag is for **deep reflection**. They have different purposes. The modules in the example are named `alpha` and `beta`; the repeated name in `--add-opens alpha/alpha=beta` is **module/package=target-module**, respectively.

## 7. Cases that easily lead to wrong conclusions

### 7.1 A method's `public` is not enough if the class is not public

`Modifier.isPublic(method.getModifiers())` can return `true` for a method declared in a package-private class. Access permissions of **all required components** must be considered, especially the class declaring the method and the module containing it. The evidence lies in `public method on hidden class=IllegalAccessException` in the first program and the `alpha`/`beta` experiment in the second program.

### 7.2 `protected` does not turn every superclass object into a valid receiver

A subclass in another package can call a `protected` instance method through an appropriate receiver; `this` is valid, whereas `new Superclass()` is not automatically valid. Reflection performs access checks with the caller context at the site calling `invoke`. If executing through a helper that is not a subclass, check whether that helper has `protected` permission; a subclass's permission does not automatically "pass through" an arbitrary helper class.

### 7.3 Passing a `Method` elsewhere does not "carry" access permissions with it

A `Method` object is just metadata and `AccessibleObject` state. When checks are not suppressed, permission is checked at the **caller performing `invoke`**. A helper in the `api` package being able to call a `package-private` method does not mean every caller receiving the same `Method` can call it. If code has successfully enabled `trySetAccessible()` for **that** `Method` itself, subsequent calls have checks suppressed and require reviewing module/security permissions. Avoid using an over-privileged `Method` in a shared API without control.

### 7.4 Different runtime packages despite the same string name

In plugin systems, hot reload, or custom loaders, two classes in a package with the same textual name but defined by different loaders usually belong to **two different runtime packages**. Therefore, package-private/protected within the same runtime package cannot be inferred from source declarations alone. When encountering puzzling errors, also log `getClassLoader()` of the source class and target class.

### 7.5 Reflection does not automatically solve interface/API visibility

A library that wants to let plugins call it dynamically should proactively design a **public API or interface** in an exported package, with the implementation in a separate module/package. If a framework needs to instantiate a private constructor or inject a private field, the library usually requires opening the package with `opens`; the fact that the package has `exports` does not guarantee deep reflection permission.

### 7.6 Method handles have their own permission model and do not bypass access rules

`java.lang.invoke.MethodHandles.Lookup` carries information about the **lookup class** and access modes. `privateLookupIn` can create a lookup with deeper permissions when permission/module conditions are met, especially regarding `opens`. `MethodHandle.invoke`/`invokeExact` have their own signature and invocation type rules; they must not be equated with `Method.invoke` or treated as a way to "bypass security" without access permissions.

## 8. Checklist for diagnosing `IllegalAccessException` in reflection code

When encountering a dynamic call error, check in order:

1. **Identify the exact member and declaring class.** Print `method.getDeclaringClass().getName()`, `method.getName()`, `method.getModifiers()`. `getMethod` may return an inherited member not declared directly on the initial class.
2. **Identify the real caller:** which package/class contains the `invoke` call? Is a third-party helper executing the call on behalf of the expected class?
3. **Check class visibility:** is the declaring class `public` or package-private? Is the declaring class in a package with the same runtime loader?
4. **Check member visibility:** `public`/`protected`/package-private/`private`. If `protected` across packages, check the subclass relationship and **receiver type**.
5. **Check the module:** `method.getDeclaringClass().getModule()`. Is the package `exports` to the caller module? Does it have `opens` for deep reflection?
6. **Use `canAccess(receiver)` to measure normal access** when the receiver is appropriate; if deep reflection is needed, use `trySetAccessible()` and handle `false` intentionally, rather than assuming it always succeeds.
7. **Distinguish error types:** `NoSuchMethodException` is lookup, `IllegalAccessException` is invoke/access, `InaccessibleObjectException` is a failed suppress-checks request, `InvocationTargetException` is an exception thrown by code inside the method.
8. **Fix the access design:** prefer a public exported API, proper receiver, and package boundary; for frameworks that genuinely need private members, grant minimal `opens` to the framework's module.

Observation snippet in code that already has a `Method m` variable (not a standalone program):

```java
Class<?> owner = m.getDeclaringClass();
System.out.println("declaringClass=" + owner.getName());
System.out.println("declaringLoader=" + owner.getClassLoader());
System.out.println("declaringModule=" + owner.getModule().getName());
System.out.println("methodModifiers=" + java.lang.reflect.Modifier.toString(m.getModifiers()));
System.out.println("classModifiers=" + java.lang.reflect.Modifier.toString(owner.getModifiers()));
```

For an unnamed module, `owner.getModule().getName()` may be `null`. One can use `owner.getModule().isExported(packageName, callerModule)` and `isOpen(packageName, callerModule)` once the **exact caller module** is identified, but these APIs only verify part of the conditions; they do not replace checking class/member/receiver visibility.

## 9. Self-check questions

**Question 1.** Code in another package calls `Class.getDeclaredMethod("secret")` and gets back a `Method` for `private secret()`. Does it already have permission to call it?

**Answer:** No. The lookup found the metadata; `invoke` still checks Java access. Either a caller with appropriate private access or permission to suppress checks is required.

**Question 2.** A class `A` has a method `public void f()`, but `A` itself is package-private. A caller in another package obtains the `Method` via `getMethod("f")`. Is `invoke` guaranteed to succeed?

**Answer:** No. Access permission to class `A` still matters; the method's `public` alone is not enough.

**Question 3.** `Sub extends Base` is in a different package from `Base`. `Base` declares `protected void p()`. Inside a method of `Sub`, are reflective calls on `this` and on `new Base()` equivalent?

**Answer:** No. `this` has a valid subclass type; `new Base()` does not satisfy the receiver rule for a `protected` instance method when the caller is a subclass in another package.

**Question 4.** Can a package-private method be called merely because two classes both declare `package demo;`?

**Answer:** Not enough to conclude. They must be in the same **runtime package**, tied to both the package name and the defining class loader; JPMS also has additional access controls.

**Question 5.** `trySetAccessible()` returns `false` and `setAccessible(true)` throws `InaccessibleObjectException` when reflecting into a named module. Should one try forcing `invoke` multiple times?

**Answer:** No. Identify the module and package; if the design allows deep reflection, configure `opens package to target.module` or an appropriately scoped permission mechanism. Repeating `invoke` does not change permissions on its own.

**Question 6.** A `private` method throws `IllegalStateException` from its body when it has already been permitted to be called via reflection. What exception does the caller see?

**Answer:** `InvocationTargetException`, with `getCause()` being `IllegalStateException`; this is an error from the method body, not an access error.

**Question 7.** Why does `getDeclaredMethods()` reveal all methods yet does not mean the program can call all methods?

**Answer:** The API lists **declarations**, not grants of invoke permission. Access is checked by caller, member, declaring class, runtime package, receiver, and module.

**Question 8.** If module `core` only has `exports p;` without `opens p;`, can another module enable `setAccessible(true)` for all private methods in package `p`?

**Answer:** No. `exports` is for the public API. Deep reflection from another module across a named module boundary requires satisfying the appropriate package-opening/reflective-access conditions; `exports` does not automatically allow private access.

## 10. Takeaways

- **Found does not equal accessible.** `getDeclaredMethod` finds non-public members too, but `invoke` can still throw `IllegalAccessException`.
- **Consider class, method, caller, runtime package, and module completely.** `public` on a method does not compensate for a non-public declaring class.
- **`protected` across packages requires a subclass and a valid receiver** for instance methods; inheritance does not grant blanket permission to call on superclass instances.
- **Package-private requires the same runtime package**, not just matching package name strings.
- **`private` grants access to the class/nestmates**, not a general privilege for the package or subclasses.
- **`trySetAccessible`/`setAccessible` have JPMS limits.** `exports` is for the public API; `opens` is for appropriate deep reflection.
- **Classify errors by step:** lookup, access, argument binding, and exceptions thrown by target code are different issues.

### Authoritative references

- [Java SE 17 API: `Method.invoke`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html)
- [Java SE 17 API: `AccessibleObject.canAccess`, `trySetAccessible`, `setAccessible`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [JLS Java SE 17 `6.6 Access Control, especially `6.6.2 protected access](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6)
- [Java SE 17 API: `Module` and `isOpen`/`isExported`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html)
- [JLS Java SE 17 `7.7 Module Declarations, `exports` and `opens`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7)