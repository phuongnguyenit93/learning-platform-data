# canAccess, trySetAccessible, and Handling Access Denial in Java 17

Reflection allows a program to discover classes, fields, methods, and constructors at runtime. However, finding a member via `getDeclaredField()` or `getDeclaredMethod()` does not mean the program is permitted to read or invoke that member. Java still enforces access rules such as `private`, `protected`, package-private, `public`, and module boundaries.

Since Java 9, `AccessibleObject` provides `canAccess(Object)` and `trySetAccessible()` to check access permission and attempt to enable bypassing access checks. These are the current APIs in Java 17. They are especially important when an application runs under the Java Platform Module System (JPMS), because a package may not be opened for deep reflection even though the class or member was found.

This lesson focuses on the proper use of `canAccess`, `trySetAccessible`, and `setAccessible`, how to choose the receiver object, how to interpret `false` and exceptions, the difference between `exports` and `opens`, and how to handle module access denials.

## 1. Finding a member does not mean being able to access it

Reflection has two groups of operations to distinguish:

- **Discovering metadata:** obtaining `Class`, `Field`, `Method`, `Constructor`, modifiers, annotations, and types.
- **Executing or reading/writing:** invoking methods, instantiating objects, reading fields, or modifying fields.

Example:

~~~java
import java.lang.reflect.Field;

class Account {
    private String owner = "Lan";
}

public class ReflectionLookupDemo {
    public static void main(String[] args) throws Exception {
        Field ownerField = Account.class.getDeclaredField("owner");
        System.out.println(ownerField.getName()); // owner
    }
}
~~~

`getDeclaredField("owner")` locates the private field. However, if read directly:

~~~java
Account account = new Account();
Field ownerField = Account.class.getDeclaredField("owner");

Object value = ownerField.get(account); // IllegalAccessException
~~~

the call can be rejected because the code calling reflection does not have permission to access private members of `Account`.

The `canAccess` and `trySetAccessible` APIs help programs handle this situation intentionally rather than assuming reflection always bypasses all limits.

## 2. AccessibleObject and the access-check override flag

`Field`, `Method`, and `Constructor` extend `java.lang.reflect.AccessibleObject`. This base class provides methods to manage access checks:

| API | Meaning |
| --- | --- |
| `canAccess(Object obj)` | Checks whether the current caller can access the member on the given receiver, according to Java access rules and the current override state. |
| `trySetAccessible()` | Attempts to enable the flag to bypass access checks; returns `true` if successful, `false` if not possible. |
| `setAccessible(boolean flag)` | Sets the override flag; when enabling is requested but not permitted, may throw `InaccessibleObjectException` or `SecurityException`. |
| `isAccessible()` | Legacy API checking the override flag state, deprecated since Java 9. Do not use it instead of `canAccess`. |

`canAccess` does not change access permissions by itself. `trySetAccessible` is the operation that requests enabling override mode.

### 2.1. Distinguishing canAccess and isAccessible

The two method names are easy to confuse:

- `canAccess(obj)` answers the question: **can the caller access this member on that receiver?**
- `isAccessible()` answers the legacy question: **is the access-check override flag on this reflection object currently enabled?**

`isAccessible()` does not check full Java access control rules. A member may be accessible under normal rules even when the override flag is off; in that case `isAccessible()` returns `false`, whereas `canAccess(...)` can return `true`.

From Java 9 onward, use `canAccess` when you need to check accessibility. `isAccessible()` is retained for compatibility but is deprecated.

## 3. Using canAccess with the right receiver

Signature:

~~~java
boolean canAccess(Object obj)
~~~

The value of `obj` depends on the member kind:

| Member being checked | Value of `obj` |
| --- | --- |
| Instance field | The object on which the field is read/written |
| Instance method | The object on which the method is invoked |
| Static field | `null` |
| Static method | `null` |
| Constructor | `null` |

For instance members, the object passed in must be an instance of the member's declaring class or an appropriate subclass. Passing `null` for an instance member, or passing an object of the wrong type, can cause `canAccess` to throw `IllegalArgumentException`; the method does not simply return `false` for all invalid-receiver cases.

### 3.1. Checking an instance field

~~~java
import java.lang.reflect.Field;

class UserProfile {
    private String email = "lan@example.test";
}

public class CanAccessFieldDemo {
    public static void main(String[] args) throws Exception {
        UserProfile profile = new UserProfile();
        Field email = UserProfile.class.getDeclaredField("email");

        System.out.println(email.canAccess(profile));
    }
}
~~~

If the caller is outside the declaring class and the field is private, the result is typically `false` when override has not been enabled.

### 3.2. Checking a static field

~~~java
import java.lang.reflect.Field;

class AppConfig {
    private static String secret = "internal";
}

public class CanAccessStaticDemo {
    public static void main(String[] args) throws Exception {
        Field secret = AppConfig.class.getDeclaredField("secret");

        boolean accessible = secret.canAccess(null);
        System.out.println(accessible);
    }
}
~~~

For a static field, pass `null`; do not pass an instance of `AppConfig`.

### 3.3. Checking methods and constructors

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;

class Worker {
    private Worker() {
    }

    private void execute() {
    }

    private static void reset() {
    }
}

public class CanAccessExecutableDemo {
    public static void main(String[] args) throws Exception {
        Method execute = Worker.class.getDeclaredMethod("execute");
        Method reset = Worker.class.getDeclaredMethod("reset");
        Constructor<Worker> constructor =
                Worker.class.getDeclaredConstructor();

        Worker instance = createForDemo();

        System.out.println(execute.canAccess(instance));
        System.out.println(reset.canAccess(null));
        System.out.println(constructor.canAccess(null));
    }

    private static Worker createForDemo() throws Exception {
        Constructor<Worker> constructor =
                Worker.class.getDeclaredConstructor();
        if (!constructor.trySetAccessible()) {
            throw new IllegalStateException("Cannot access constructor");
        }
        try {
            return constructor.newInstance();
        } finally {
            constructor.setAccessible(false);
        }
    }
}
~~~

This example illustrates the receiver rules. In production code, do not enable constructor access just to instantiate objects if a public constructor or factory method already serves the need.

## 4. trySetAccessible: attempting to enable reflective access

`trySetAccessible()` attempts to turn on the access-check override flag for a reflection object. If successful, subsequent reflective operations can access the member bypassing ordinary Java language checks.

~~~java
boolean enabled = field.trySetAccessible();
if (enabled) {
    // Can try reading the field via reflection.
} else {
    // Runtime/module does not allow enabling override.
}
~~~

Unlike `setAccessible(true)`, `trySetAccessible()` represents the disallowed case with `false` instead of throwing `InaccessibleObjectException` when permission cannot be opened across module boundaries.

The method can still throw `SecurityException` if a Security Manager is configured and denies `ReflectPermission("suppressAccessChecks")`. The Security Manager has been deprecated for removal since Java 17; new applications should not rely on it as a primary security mechanism.

### 4.1. Example reading a private field

~~~java
import java.lang.reflect.Field;

class Customer {
    private final String name;

    Customer(String name) {
        this.name = name;
    }
}

public class TrySetAccessibleDemo {
    public static void main(String[] args) throws Exception {
        Customer customer = new Customer("Nguyen An");
        Field nameField = Customer.class.getDeclaredField("name");

        if (!nameField.canAccess(customer)) {
            if (!nameField.trySetAccessible()) {
                throw new IllegalStateException(
                        "Runtime does not allow access to Customer.name");
            }
        }

        try {
            Object value = nameField.get(customer);
            System.out.println(value);
        } finally {
            nameField.setAccessible(false);
        }
    }
}
~~~

In a simple classpath example, the application's packages belong to the unnamed module. Packages in the unnamed module are open to deep reflection, so `trySetAccessible()` typically succeeds. With named modules, the result also depends on whether the package is opened to the caller's module.

`trySetAccessible()` does not make the member `public`, does not alter modifiers in bytecode, and does not grant global access to all code. It sets the override state on the specific reflection object held by the program.

### 4.2. Do not enable override unnecessarily

If `canAccess` already returns `true`, the reflective operation can proceed under current access permissions. There is no need to call `trySetAccessible()` just to "be sure".

Good handling pattern:

1. Locate the member.
2. Determine the right receiver.
3. Check `canAccess`.
4. Only when deep reflection is needed and justified, call `trySetAccessible`.
5. If it returns `false`, handle according to application policy.
6. Perform the operation and close the override scope by resetting to `false` when appropriate.

Do not call `setAccessible(true)` in bulk on every field or method of a class. That tightly couples code to internal details and is easily blocked by modules.

## 5. How do setAccessible(true) and trySetAccessible differ?

Both methods deal with enabling access-check overrides, but they report failure differently:

| Situation | `trySetAccessible()` | `setAccessible(true)` |
| --- | --- | --- |
| Override can be enabled | Returns `true` | Completes normally |
| Cannot enable because named module package is not open | Returns `false` | Throws `InaccessibleObjectException` |
| Security Manager denies `suppressAccessChecks` | May throw `SecurityException` | May throw `SecurityException` |
| Caller does not need override | Can be skipped | Should not be called |

`trySetAccessible()` is better suited when an application needs controlled handling of whether access can be opened. `setAccessible(true)` still exists in Java 17 and may be needed for legacy compatibility, but it does not help bypass module restrictions.

### 5.1. setAccessible(false) to disable override

After completing the operation, you can restore the state:

~~~java
if (!field.trySetAccessible()) {
    throw new IllegalStateException("Access denied");
}

try {
    Object value = field.get(target);
    use(value);
} finally {
    field.setAccessible(false);
}
~~~

`setAccessible(false)` does not require the package to be open in order to restore access checks. This keeps the code scope using override privileges short and easier to read.

However, do not assume resetting the flag makes any data already read safe. Once sensitive values have been retrieved, the application must still protect those values according to its own policies.

## 6. The module system: why can reflection be denied?

Since Java 9, applications can run under the Java Platform Module System (JPMS). A module declares which packages are exported to other modules and which packages are opened for deep reflection.

Two key concepts:

- `exports`: allows other modules to access `public` types and members of the package under Java access control rules.
- `opens`: allows deep reflection into the package, including accessing non-public members when the caller uses reflection and satisfies the remaining conditions.

`exports` is not synonymous with `opens`. An exported package may allow other code to call public APIs while still denying reflection from enabling access to private fields.

### 6.1. Example module exporting only public APIs

Suppose module `com.example.model`:

~~~java
module com.example.model {
    exports com.example.model.api;
}
~~~

Package `com.example.model.api` provides the public API to other modules. An internal package such as `com.example.model.internal` is neither exported nor opened.

Other modules can use the exported public types, but cannot by default use deep reflection to read private fields in the internal package.

### 6.2. Selectively opening a package with opens

If an authorized framework or module needs deep reflection into a specific package, the module can declare:

~~~java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.internal to com.example.reflector;
}
~~~

Here:

- `com.example.model.api` is exported for ordinary API access.
- `com.example.model.internal` is opened for deep reflection by module `com.example.reflector`.
- Other modules do not automatically receive deep reflection permission just because the package was selectively opened to a specific module.

The target module must read the source module according to the corresponding module configuration, for example declaring `requires com.example.model;`.

### 6.3. Opening an entire module

A module can be declared as `open module` to open all of its packages for deep reflection. This is broader than `opens package to module` and increases internal access exposure.

Only choose it when the module design genuinely requires all packages to be open. For new applications, prefer opening only the required packages to the required modules.

## 7. Using --add-opens when you cannot modify the source module

At runtime, a package can be opened using the JVM option `--add-opens`:

~~~bash
java --add-opens com.example.model/com.example.model.internal=com.example.reflector \
     -m com.example.reflector/com.example.reflector.Main
~~~

General syntax:

~~~text
--add-opens source.module/package=target.module
~~~

If the caller is on the classpath (unnamed module), the target is usually `ALL-UNNAMED`:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

The last example opens package `java.lang` of module `java.base` to all code on the classpath. This is a very broad permission on a core JDK package; only use it when a dependency genuinely requires it and with a plan to phase out that compatibility configuration.

Do not add `--add-opens` arbitrarily just to silence errors. Identify the source module, package, target module, and why the framework needs deep reflection. Broadly opening packages can mask the fact that the application depends on internal implementations of libraries or the JDK.

### 7.1. Distinguishing --add-opens and --add-exports

| Option | Target |
| --- | --- |
| `--add-exports source.module/package=target.module` | Allows ordinary access to public types in an unexported package for the target module. |
| `--add-opens source.module/package=target.module` | Allows deep reflection into the package for the target module. |

If the error is `IllegalAccessError` when code links to a public type in an unexported package, `--add-exports` may be relevant. If `trySetAccessible()` returns `false` or `setAccessible(true)` throws `InaccessibleObjectException` because the package is not open, look at `opens` or `--add-opens`.

Do not use `--add-exports` expecting to read private fields via deep reflection; the two options address different types of access.

## 8. Handling access denial outcomes

When reflection is denied, first classify the cause accurately:

| Outcome/exception | Meaning | How to handle |
| --- | --- | --- |
| `canAccess(obj)` returns `false` | Current caller does not yet have permission to access the member in its current state | Determine whether deep reflection is truly needed. |
| `trySetAccessible()` returns `false` | Unable to enable override, usually due to an unopened module/package boundary | Selectively open the package if you control the configuration; otherwise, use public APIs. |
| `InaccessibleObjectException` | `setAccessible(true)` cannot enable override due to access restrictions, typically module-related | Check module/package and use `opens`/`--add-opens` only when necessary. |
| `IllegalAccessException` | `Field.get`, `Method.invoke`, constructor, or reflection API operation is not permitted to access | Check receiver, override state, and access permissions. |
| `IllegalArgumentException` from `canAccess` | Wrong receiver type, e.g., passing `null` for an instance field | Pass the proper object; static members and constructors use `null`. |
| `SecurityException` | Security Manager policy or runtime security mechanism denies the operation | Check policy/provider/runtime; do not attempt workarounds. |

### 8.1. Pattern for handling trySetAccessible returning false

~~~java
Field field = targetClass.getDeclaredField("internalState");

if (!field.trySetAccessible()) {
    throw new IllegalStateException(
            "Cannot inspect internalState: package is not open to this module");
}

try {
    Object value = field.get(target);
    inspect(value);
} finally {
    field.setAccessible(false);
}
~~~

Error messages should specify the member and the known cause. Do not catch every exception and return `null`, because the caller will not be able to distinguish "the field actually holds null" from "cannot access the field".

### 8.2. Do not swallow InaccessibleObjectException

Bad handling example:

~~~java
try {
    field.setAccessible(true);
} catch (RuntimeException ignored) {
    // Continue as if the field had been opened.
}
~~~

If the subsequent read fails, the actual error is pushed far from the original cause. Catch the specific exception if you need to add context, then rethrow or translate it into a clear configuration error.

~~~java
try {
    field.setAccessible(true);
} catch (java.lang.reflect.InaccessibleObjectException e) {
    throw new IllegalStateException(
            "The target module must open this package for deep reflection",
            e);
}
~~~

In new code, `trySetAccessible()` usually makes the inability to open access a cleaner `false` branch to handle.

## 9. Complete example: reading a private field with access denial handling

The following example separates locating the field, checking the receiver, attempting to open access, and reading the value:

~~~java
import java.lang.reflect.Field;
import java.util.Objects;

class PaymentRecord {
    private final String reference;

    PaymentRecord(String reference) {
        this.reference = reference;
    }
}

public class SafeReflectionRead {
    static Object readField(Object target, String fieldName)
            throws ReflectiveOperationException {
        Objects.requireNonNull(target, "target");
        Objects.requireNonNull(fieldName, "fieldName");

        Field field = target.getClass().getDeclaredField(fieldName);

        if (!field.canAccess(target) && !field.trySetAccessible()) {
            throw new IllegalStateException(
                    "Deep reflection is not permitted for "
                            + field.getDeclaringClass().getName()
                            + "." + fieldName);
        }

        try {
            return field.get(target);
        } finally {
            field.setAccessible(false);
        }
    }

    public static void main(String[] args) throws Exception {
        PaymentRecord record = new PaymentRecord("PAY-2026-001");
        System.out.println(readField(record, "reference"));
    }
}
~~~

In this example, the class and caller are on the classpath in the same unnamed module. With named modules, `trySetAccessible()` can return `false` if the package containing `PaymentRecord` is not opened to `SafeReflectionRead`'s module.

Some notes when adopting this pattern in an application:

- `getDeclaredField` only searches for fields declared on the specific class; it does not automatically look up private fields in superclasses.
- If you need to search an entire hierarchy, walk superclasses intentionally.
- If the field is static, use `field.canAccess(null)` and `field.get(null)`.
- If the field does not exist, `getDeclaredField` throws `NoSuchFieldException`.
- Do not use reflection to read internal data if the class already provides a getter or suitable API.

## 10. Reflection with methods: invoking after opening access

The same rules apply to `Method`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

class ReportGenerator {
    private String buildInternalReport(String code) {
        return "Report: " + code;
    }
}

public class InvokePrivateMethodDemo {
    public static void main(String[] args) throws Exception {
        ReportGenerator generator = new ReportGenerator();
        Method method = ReportGenerator.class.getDeclaredMethod(
                "buildInternalReport", String.class);

        if (!method.canAccess(generator)
                && !method.trySetAccessible()) {
            throw new IllegalStateException(
                    "Cannot access buildInternalReport");
        }

        try {
            Object result = method.invoke(generator, "R-17");
            System.out.println(result);
        } catch (InvocationTargetException e) {
            // The invoked method threw an exception.
            Throwable cause = e.getCause();
            throw new IllegalStateException(
                    "Target method failed", cause);
        } finally {
            method.setAccessible(false);
        }
    }
}
~~~

`Method.invoke` can throw `IllegalAccessException` if permissions are insufficient. If the target method throws an exception, reflection wraps that error in `InvocationTargetException`; inspect `getCause()` to handle the true cause.

Do not confuse exceptions caused by denied access with exceptions thrown by code inside the invoked method.

## 11. Reflection with constructors

Constructors also extend `AccessibleObject`. When checking with `canAccess`, pass `null`:

~~~java
import java.lang.reflect.Constructor;

class InternalClient {
    private InternalClient(String endpoint) {
        System.out.println(endpoint);
    }
}

public class PrivateConstructorDemo {
    public static void main(String[] args) throws Exception {
        Constructor<InternalClient> constructor =
                InternalClient.class.getDeclaredConstructor(String.class);

        if (!constructor.canAccess(null)
                && !constructor.trySetAccessible()) {
            throw new IllegalStateException(
                    "Cannot access InternalClient constructor");
        }

        try {
            InternalClient client =
                    constructor.newInstance("https://example.test");
        } finally {
            constructor.setAccessible(false);
        }
    }
}
~~~

`Constructor.newInstance` can throw `IllegalAccessException`, `InstantiationException`, `IllegalArgumentException`, or `InvocationTargetException`. If the target constructor throws an exception, the cause is wrapped in `InvocationTargetException`.

If the class provides a public factory method, prefer the factory instead of calling a private constructor.

## 12. Inheritance and members declared in superclasses

`getDeclaredField` and `getDeclaredMethod` only return members declared directly on the queried class. `getField` and `getMethod` look up matching public members, including certain inherited members according to API rules.

When handling a hierarchy:

~~~java
Class<?> type = target.getClass();
while (type != null) {
    try {
        Field field = type.getDeclaredField("id");
        // Check permission on the field declared at type.
        break;
    } catch (NoSuchFieldException ignored) {
        type = type.getSuperclass();
    }
}
~~~

If the field is found in a superclass, the receiver is still the actual `target` object, provided that object is a valid instance of the field's declaring class. The module that needs to be opened is the module containing the member's declaring package, not merely the subclass's package.

For protected members, Java access rules also depend on subclass relationships, packages, and the caller. Do not infer access merely from the object being a subclass; use `canAccess` with the proper receiver and handle the result.

## 13. Alternatives to deep reflection

Deep reflection couples code to implementation details. Before calling `trySetAccessible`, consider:

1. **Public API or getters/setters:** use contracts explicitly published by the class.
2. **Constructors/factory methods:** instantiate objects through designed extension points.
3. **Interfaces or service providers:** depend on abstractions rather than internal fields.
4. **Official serialization or mapping APIs:** use libraries with clear module contracts.
5. **MethodHandles:** in certain advanced scenarios, `MethodHandles.Lookup` with appropriate lookup permissions can express method/field access through a well-defined mechanism.

`MethodHandles.privateLookupIn` is also subject to module rules; it is not a backdoor past unopened packages. The proper approach is to design APIs/modules so interacting components are granted the right permissions.

## 14. Security and Java 17 compatibility notes

- Do not open internal JDK packages merely to avoid fixing code that depends on private implementations.
- Do not enable overrides on all members if only a specific field or method is needed.
- Do not log private values that may contain passwords, tokens, keys, or personal data.
- Do not treat `trySetAccessible() == true` as proof that the operation is business-safe; it only indicates that the runtime permits bypassing access checks.
- Do not rely on `isAccessible()` to check whether the caller has access permission.
- Do not use the Security Manager as a new security foundation; the Security Manager is deprecated for removal in Java 17.
- Do not rely on legacy `--illegal-access` flags from earlier JDKs; that compatibility mechanism is no longer the current solution on Java 17.
- If a library requires deep reflection, use a Java 17-compatible version of the library and read that library's own module instructions.

## 15. API selection table by scenario

| Need | API/approach |
| --- | --- |
| Check whether caller can read an instance field | `field.canAccess(target)` |
| Check a static field | `field.canAccess(null)` |
| Check an instance method | `method.canAccess(target)` |
| Check a static method or constructor | `canAccess(null)` |
| Attempt to open a private member and handle failure with a boolean | `trySetAccessible()` |
| Legacy API requesting override and accepting exceptions | `setAccessible(true)` |
| Named module package needs to allow deep reflection | `opens package to caller.module` |
| Runtime-only configuration without modifying the source module | `--add-opens source.module/package=target.module` |
| Need access to public API from an unexported package | Appropriate `exports` or `--add-exports` |
| Only need data via a public contract | Getters, methods, or public APIs; avoid deep reflection |

## 16. Self-check questions

**1. Does finding a private field with `getDeclaredField` mean the field can be read?**  
No. Finding metadata and reading values are two separate steps; access checks still apply.

**2. Does `canAccess` enable access permission by itself?**  
No. It only checks accessibility on the given receiver.

**3. When calling `canAccess` for an instance field, what do you pass?**  
Pass the object on which the field is accessed; the object must have a type compatible with the field's declaring class.

**4. When calling `canAccess` for a static method or constructor, what do you pass?**  
Pass `null`.

**5. When does `trySetAccessible()` return `false`?**  
When the runtime does not allow enabling access-check overrides, usually because a named module's package is not opened to the caller's module.

**6. What is the main difference between `trySetAccessible()` and `setAccessible(true)`?**  
`trySetAccessible()` returns `false` if access cannot be opened due to module restrictions; `setAccessible(true)` can throw `InaccessibleObjectException`.

**7. Can `isAccessible()` replace `canAccess()`?**  
No. `isAccessible()` only reflects the legacy override flag and is deprecated; `canAccess()` checks actual accessibility.

**8. Does `exports` allow reading private fields via deep reflection?**  
No. `exports` grants access to public APIs; deep reflection requires the package to be opened with `opens`.

**9. What is `--add-opens` used for?**  
Opening a package of a source module to a target module to perform deep reflection at runtime.

**10. Why shouldn't you open all JDK packages just to make reflection errors disappear?**  
Because it broadens internal access, creates implementation dependencies, and can mask library compatibility issues.

**11. If `Method.invoke` throws `InvocationTargetException`, where is the error?**  
The target method threw an exception; inspect `getCause()` to obtain the root cause.

**12. When should `trySetAccessible` be avoided?**  
When a public API, getter, factory, or official abstraction already meets the requirement.

## Official references

- [Java SE 17 API — AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `canAccess`, `trySetAccessible`, `setAccessible`, and override state.
- [Java SE 17 API — Field](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html): reading/writing fields via reflection.
- [Java SE 17 API — Method](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): invoking methods via reflection.
- [Java SE 17 API — Constructor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html): instantiating objects via constructor reflection.
- [Java SE 17 API — InaccessibleObjectException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html): error when access-check overrides cannot be enabled.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): modules, exports, opens, and related runtime options.
- [Java SE 17 Documentation — java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `--add-opens` and `--add-exports` options.
- [JEP 411 — Deprecate the Security Manager for Removal](https://openjdk.org/jeps/411): status of the Security Manager from Java 17 onward.
