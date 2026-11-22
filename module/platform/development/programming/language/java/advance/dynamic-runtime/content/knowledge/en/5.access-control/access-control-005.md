# 5.5. Using canAccess, trySetAccessible, and setAccessible Based on Access Results

## Learning Objectives

After this lesson, you can:

- Check whether a **Method**, **Field**, or **Constructor** can be accessed via Reflection **at the time of the check** using `canAccess`.
- Distinguish **checking existing permissions** from **requesting to bypass Java language access checks** using `trySetAccessible` or `setAccessible(true)`.
- Choose how to handle results based on **true/false values**, exceptions, valid receivers, and **Java Platform Module System (JPMS)** rules.
- Explain why a `private` member can be accessed via Reflection in some cases but is denied in a **module that does not open the package**.
- Write Java 17+ code that handles results properly and knows when to use a public API instead of forcing access.

> Scope: this lesson focuses on **Reflection access-permission decisions**, does not use Reflection as a security sandbox, and does not present `setAccessible(true)` as a way to always bypass every restriction.

## 1. First: “Finding a Member” Is Different from “Being Allowed to Access It”

Reflection can obtain metadata for a `private` member using:

~~~java
// Illustrative fragment: assumes SecretBox has a private method "secret".
Method method = SecretBox.class.getDeclaredMethod("secret");
~~~

`getDeclaredMethod` returns the metadata of the method declared in the class; it **does not automatically grant permission to invoke** that method. Similarly, `getDeclaredField` or `getDeclaredConstructor` can find a field/constructor, but `get`, `set`, and `newInstance` operations must still obey access checks unless Reflection is permitted to enable the mechanism that suppresses those checks.

All three commonly used APIs are on `java.lang.reflect.AccessibleObject`:

| API | Question it answers | Result/effect | If permissions are insufficient |
| --- | --- | --- | --- |
| `canAccess(Object obj)` | “**From the current calling context**, can I access this member with receiver `obj`?” | `boolean`; **does not attempt to enable** bypassing access checks | Usually returns `false` if the receiver is valid |
| `trySetAccessible()` | “Can I **enable the accessible flag** of this Reflection object?” | `boolean`; `true` when the flag can be enabled, `false` when it cannot | Returns `false` for many cases denied by JPMS |
| `setAccessible(boolean flag)` | “Set the accessible flag to the requested value.” | `void`; `true` requests bypassing Java access checks on applicable Reflection operations; `false` disables that request | `setAccessible(true)` may throw `InaccessibleObjectException` |

`trySetAccessible()` and `setAccessible(true)` **do not have unconditional power**. Module rules (and on runtimes that have related security checks, those checks) still decide whether enabling the flag is allowed.

The `canAccess`, `trySetAccessible`, and `setAccessible` methods operate on a specific Reflection object, such as the `Method` object you hold; they do not directly change a `private` declaration to `public` in the class.

## 2. How to Make Decisions Based on Results

A practical workflow should start from a **known and permitted member**:

~~~text
Look up valid Method / Field / Constructor
                  |
                  v
Determine the right receiver for canAccess(...)
                  |
                  v
           canAccess(receiver)?
               /       \
             true      false
              |          |
   Invoke via Reflection v
                   Is deep reflective
                   access actually needed?
                     /         \
                    no         yes
                    |            |
              Choose public   trySetAccessible()
                  API           /        \
                             true        false
                               |           |
                             Invoke     Fallback / report
                             member     access restriction
~~~

Code snippet illustrating the decision for an **instance Method**:

~~~java
// Fragment: method looked up beforehand, receiver of the right type, trusted caller.
if (!method.canAccess(receiver)) {
    if (!method.trySetAccessible()) {
        throw new IllegalStateException(
                "Not allowed to access this method via Reflection");
    }
}
Object result = method.invoke(receiver);
~~~

This is a **fragment**, not a standalone program: `method` and `receiver` must be declared; the invoke branch needs to handle checked exceptions such as `IllegalAccessException` and `InvocationTargetException`. On environments that still enforce SecurityManager checks, `trySetAccessible()` can also throw `SecurityException`; therefore `false` is not the only kind of failure that can occur.

**Why check first?** If `canAccess` is already `true`, the code can use the member immediately without modifying the accessible flag. If `false`, you must decide whether accessing a non-public member is genuinely a valid requirement; only then should you try enabling the flag and check the result.

**Do not treat `false` as a signal that “calling `setAccessible(true)` will definitely succeed.”** For a package not opened by its module, that call will still be denied.

## 3. canAccess Checks Currently Available Access Permissions

`AccessibleObject.canAccess(Object obj)` was added in Java 9 and answers whether access is available via Reflection from the current calling context.

- If the member is already `public` and the enclosing type/access path is valid, `canAccess` can return `true` even when the accessible flag is **false**.
- If a `private` member cannot be called by the caller under normal Java access rules, `canAccess` returns `false` when suppression has not been enabled.
- After `trySetAccessible()` or `setAccessible(true)` succeeds, `canAccess` normally returns `true` with the right receiver.
- `canAccess` does not try to turn `false` into `true`; it is a **check**, not a request to open access.

### 3.1. Passing the Right Receiver for Each Member Kind

The `obj` argument of `canAccess` is not always the same:

| Reflection Member | Value passed to `canAccess` |
| --- | --- |
| Instance `Method` | Receiver object belonging to the declaring class or an appropriate subclass |
| Instance `Field` | Receiver object compatible with the declaring class |
| `static Method` or `static Field` | `null` |
| `Constructor` | `null` |

Example:

~~~java
// Fragment assuming valid variables already exist:
instanceMethod.canAccess(service); // instance method: use receiver
staticMethod.canAccess(null);      // static method: use null
constructor.canAccess(null);       // constructor: use null
~~~

This is **illustrative code** and does not compile standalone. Passing `null` for an instance member, passing an object of the wrong receiver type, or passing a non-null value for a static member/constructor can cause `canAccess` to throw `IllegalArgumentException`. Therefore, a receiver error is **different from** a `false` result caused by missing permissions.

When using `Field.get(receiver)`, `Field.set(receiver, value)`, or `Method.invoke(receiver, args...)`, you must also obey the receiver and argument-type contract of that API.

### 3.2. canAccess Depends on the Caller and Context

Normal access permissions depend on modifiers (`public`, `protected`, package-private, `private`), the declaring type, package/subclass relationships, **nestmates**, and module constraints. The same member may be validly accessible by code at one call site but not by code at another call site if suppression has not been enabled.

Therefore, you should not take a `canAccess` check from a helper in another module and treat it as universal proof for every caller. A helper function that checks and invokes within the same context is easier to reason about. In addition, the state of the accessible flag belongs to a specific Reflection object; you should not infer that all `Method` objects obtained from the same class share the same override state.

## 4. trySetAccessible: Attempt to Open Access and Return a boolean

`trySetAccessible()` requests setting the accessible flag to `true` **if the environment permits it**.

~~~java
// Fragment: field was obtained via getDeclaredField(...).
if (field.trySetAccessible()) {
    Object value = field.get(receiver);
    // Handle value according to the application contract.
} else {
    // No permission to enable suppress-access-checks in the current context.
    // Choose a public API, request the module to open the package, or reject the operation.
}
~~~

This is a fragment assuming `field` and `receiver` already exist; appropriate checked exceptions must be handled.

If `trySetAccessible()` returns `true`, the flag is in the state that allows suppressing access checks. If `false`, you must **respect the result** and not continue calling `get`/`invoke` hoping access will somehow open on its own. However, if a member is already public-accessible and does not need access opened, use `canAccess` first to avoid changing the flag unnecessarily.

Some conditions that can allow `trySetAccessible()` to succeed:

- The caller and declaring class are in the **same module**; enabling suppression may be permitted even for private members.
- The member belongs to a public class, has public visibility, and its package is appropriately **exported** to the caller.
- The package is appropriately **opened** to the caller's module, allowing deep reflection under JPMS rules.
- The member falls under other cases permitted by the API, such as certain `protected static` members with an appropriate subclass relationship.

Conversely, a `private` member of a class in **another named module** whose package only `exports` but **does not `opens`** to the caller usually cannot have suppression enabled. `trySetAccessible()` can then return `false`.

**Note:** `trySetAccessible()` avoids having to rely on `InaccessibleObjectException` for common JPMS denial cases; it **does not** guarantee “never throws any exception”—for example, security checks can still throw `SecurityException` on runtimes that support that mechanism.

## 5. setAccessible(true/false): Request Changing the accessible Flag

`setAccessible(true)` requests bypassing normal Java access checks during Reflection operations, **only if the API and module allow it**. When it fails because of JPMS, the API throws `java.lang.reflect.InaccessibleObjectException` (unchecked). Unlike `trySetAccessible`, it **does not return a boolean**.

~~~java
// Fragment: for an intentional "fail fast" path.
try {
    method.setAccessible(true);
    Object result = method.invoke(receiver);
} catch (java.lang.reflect.InaccessibleObjectException ex) {
    // Package/module does not allow enabling the accessible flag.
    // Choose a public API, change to a valid module configuration, or report a clear error.
}
~~~

`method` and `receiver` are illustrative variables, and the snippet is not standalone runnable; `invoke` also has checked exceptions.

`setAccessible(false)` **disables the accessible flag** on that Reflection object, restoring normal Java access checks on subsequent uses. It **does not force `canAccess` to return false**: a valid public member can still be accessed under normal permissions. Enabling/disabling does not turn a class into public, does not open a module, and does not modify the class's metadata or bytecode.

An operational note: If a `Method`/`Field` is shared across multiple threads, enabling and then disabling the accessible flag around each `invoke` call can cause races with other threads. Control the lifecycle of Reflection objects and avoid sharing unsynchronized mutable access state; it is best to choose a valid and stable access mechanism for the entire processing flow upfront.

### 5.1. The Legacy isAccessible() API Easily Causes Misunderstanding

`AccessibleObject.isAccessible()` has been **deprecated** since Java 9. It reflects the state of the **accessible flag** (the suppress-checks flag), which is not synonymous with the question “can this caller currently access the member validly?”.

Specifically:

~~~text
public member, normal Java access rights valid
accessible flag = false
canAccess(correctReceiver) = true
~~~

Use `canAccess` to check actual accessibility; only use `trySetAccessible`/`setAccessible` when you truly want to change the check-suppression state of the Reflection object.

## 6. Runnable Example: Observing All Three APIs on Method, Field, Static Method, and Constructor

Create the file **AccessDecisionDemo.java** in an empty directory. The two top-level classes below are compiled from the **same file**; `Vault` is a top-level class separate from `AccessDecisionDemo`, not a nested class/nestmate. This makes the private access check genuinely meaningful.

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class AccessDecisionDemo {
    public static void main(String[] args) throws Exception {
        Vault vault = Vault.create();
        Method visible = Vault.class.getMethod("view");
        Method secret = Vault.class.getDeclaredMethod("secret");
        Field count = Vault.class.getDeclaredField("count");
        Method twice = Vault.class.getDeclaredMethod("twice", int.class);
        Constructor<Vault> constructor = Vault.class.getDeclaredConstructor();

        System.out.println("public.canAccess=" + visible.canAccess(vault));
        System.out.println("private.canAccess.before=" + secret.canAccess(vault));
        try {
            secret.invoke(vault);
        } catch (IllegalAccessException ex) {
            System.out.println("private.invoke.before=denied");
        }
        System.out.println("private.try=" + secret.trySetAccessible());
        System.out.println("private.canAccess.after=" + secret.canAccess(vault));
        System.out.println("private.invoke.after=" + secret.invoke(vault));
        secret.setAccessible(false);
        System.out.println("private.canAccess.reset=" + secret.canAccess(vault));
        System.out.println("public.canAccess.withFlagFalse=" + visible.canAccess(vault));

        System.out.println("field.canAccess.before=" + count.canAccess(vault));
        System.out.println("field.try=" + count.trySetAccessible());
        System.out.println("field.getInt=" + count.getInt(vault));

        System.out.println("static.canAccess.before=" + twice.canAccess(null));
        System.out.println("static.try=" + twice.trySetAccessible());
        System.out.println("static.invoke=" + twice.invoke(null, 21));

        System.out.println("ctor.canAccess.before=" + constructor.canAccess(null));
        System.out.println("ctor.try=" + constructor.trySetAccessible());
        System.out.println("ctor.new=" + constructor.newInstance().getClass().getSimpleName());
    }
}

class Vault {
    private int count = 7;
    private Vault() {}
    static Vault create() { return new Vault(); }
    public String view() { return "public"; }
    private String secret() { return "secret"; }
    private static int twice(int n) { return n * 2; }
}
~~~

Compile and run with **JDK 17+**:

~~~bash
javac -encoding UTF-8 AccessDecisionDemo.java
java AccessDecisionDemo
~~~

Stdout:

~~~text
public.canAccess=true
private.canAccess.before=false
private.invoke.before=denied
private.try=true
private.canAccess.after=true
private.invoke.after=secret
private.canAccess.reset=false
public.canAccess.withFlagFalse=true
field.canAccess.before=false
field.try=true
field.getInt=7
static.canAccess.before=false
static.try=true
static.invoke=42
ctor.canAccess.before=false
ctor.try=true
ctor.new=Vault
~~~

### 6.1. Interpreting the Results

1. `view()` is **public** and the caller is in a context allowed to access it, so `visible.canAccess(vault)` returns `true` even without enabling suppression.
2. `secret()` is **private** on **top-level Vault**. `AccessDecisionDemo` is neither the declaring class nor a nestmate of Vault, so the initial check returns `false`. Calling `invoke` immediately throws `IllegalAccessException`.
3. Both classes are in the **same unnamed module**, so `secret.trySetAccessible()` can enable the accessible flag successfully and returns `true`; afterwards `invoke` returns the string **secret**.
4. `secret.setAccessible(false)` disables suppression; because private still does not belong to the caller's normal permissions, `canAccess` goes back to `false`.
5. On the public method `view()`, an accessible flag of false **does not prevent** normal access: `visible.canAccess(vault)` remains `true`.
6. For the instance field `count`, use **receiver `vault`** when checking and reading; for the static method `twice`, use **`null`** when checking/invoking.
7. For the constructor, `canAccess(null)` uses `null`, and only after enabling access can `newInstance` be called via Vault's private constructor from this caller.

**Why use a separate `Vault` class?** If the code checking the private method were inside the declaring class itself, or in a nestmate that has private access in Java, the initial `canAccess` **might already be true**. To demonstrate the before/after suppression difference, you need a caller context without normal private access.

This example reflects a classpath/unnamed-module environment that allows enabling the accessible flag for those members. **Do not infer** from this result that private members in all named modules can be opened.

## 7. With Named Modules: exports Is Different from opens

When the Java module system is in effect, a class can be **public** and its package can be **exported** so other modules can call its public API, yet Reflection attempting to bypass checks to touch a **private member** is still denied because the package is **not opened**.

- `exports p;`: allows eligible modules to use the **public types/public members** of the package under module rules; does not automatically allow deep reflection into private members.
- `opens p;`: opens the package for deep reflective access at runtime to modules with the corresponding access; you still need to call `trySetAccessible`/`setAccessible` when you want to bypass member access checks.
- `opens p to some.module;`: opens the package only to the named module; useful for narrowing the reflection surface.
- `--add-opens source.module/package=target.module`: a runtime option to purposefully open a package when the module configuration cannot be edited; should be used in a controlled manner.

### 7.1. Building Two Standalone Named Modules

Create the following structure:

~~~text
src/
  demo.lib/
    module-info.java
    sample/api/PortalApi.java
  demo.client/
    module-info.java
    sample/client/CheckModules.java
~~~

**src/demo.lib/module-info.java**

~~~java
module demo.lib {
    exports sample.api;
}
~~~

The public package is exported, but not yet opened.

**src/demo.lib/sample/api/PortalApi.java**

~~~java
package sample.api;

public class PortalApi {
    public String view() { return "visible"; }
    private String secret() { return "hidden"; }
}
~~~

**src/demo.client/module-info.java**

~~~java
module demo.client {
    requires demo.lib;
}
~~~

**src/demo.client/sample/client/CheckModules.java**

~~~java
package sample.client;

import java.lang.reflect.InaccessibleObjectException;
import java.lang.reflect.Method;
import sample.api.PortalApi;

public class CheckModules {
    public static void main(String[] args) throws Exception {
        PortalApi api = new PortalApi();
        Method publicMethod = PortalApi.class.getMethod("view");
        Method privateMethod = PortalApi.class.getDeclaredMethod("secret");

        System.out.println("public.canAccess=" + publicMethod.canAccess(api));
        System.out.println("private.canAccess.before=" + privateMethod.canAccess(api));
        System.out.println("private.try=" + privateMethod.trySetAccessible());
        try {
            privateMethod.setAccessible(true);
            System.out.println("private.set=ok");
        } catch (InaccessibleObjectException ex) {
            System.out.println("private.set=blocked");
        }
        System.out.println("public.invoke=" + publicMethod.invoke(api));
        if (privateMethod.canAccess(api)) {
            System.out.println("private.invoke=" + privateMethod.invoke(api));
        } else {
            System.out.println("private.invoke=skipped");
        }
    }
}
~~~

The commands below use a POSIX shell (macOS/Linux/Git Bash), run in the directory containing **src**; on Windows PowerShell, create the two corresponding directories **mods/demo.lib** and **mods/demo.client** before running the same javac/java commands:

~~~bash
mkdir -p mods/demo.lib mods/demo.client
javac -encoding UTF-8 -d mods/demo.lib src/demo.lib/module-info.java src/demo.lib/sample/api/PortalApi.java
javac -encoding UTF-8 --module-path mods -d mods/demo.client src/demo.client/module-info.java src/demo.client/sample/client/CheckModules.java
java --module-path mods -m demo.client/sample.client.CheckModules
~~~

Stdout when only **exports** is present, without **opens**:

~~~text
public.canAccess=true
private.canAccess.before=false
private.try=false
private.set=blocked
public.invoke=visible
private.invoke=skipped
~~~

Note the differences:

1. `publicMethod` is invoked because **public type + public method + exported package** match.
2. `getDeclaredMethod("secret")` finding private metadata **is not synonymous** with permission to invoke the private method.
3. `privateMethod.trySetAccessible()` returns `false`, because **demo.lib** has not opened `sample.api` to **demo.client**.
4. `privateMethod.setAccessible(true)` throws `InaccessibleObjectException`; the program catches it and turns it into **private.set=blocked**.
5. The program skips invoking the private method when permission is absent; this is a valid handling branch instead of forcing access.

### 7.2. Opening the Package to the Calling Module

One way is to replace the library's module descriptor with:

~~~java
// Replacement version of src/demo.lib/module-info.java
module demo.lib {
    exports sample.api;
    opens sample.api to demo.client;
}
~~~

This is a **replacement for the module-info.java file** shown above, not an additional module declaration. Recompile the library module after replacing the file and re-run the application with the same module path. Some ways of compiling the library separately may warn if the compiler does not yet see the target module **demo.client**; you can provide an appropriate module path when compiling. `opens ... to demo.client` remains a rule that opens the package by module name at runtime.

A second way, **without changing the module-info.java source**, is to run the already compiled application from section 7.1 with an explicit option to open the package:

~~~bash
java --module-path mods --add-opens demo.lib/sample.api=demo.client -m demo.client/sample.client.CheckModules
~~~

In both situations when the package is properly opened to the caller module, the program's stdout is:

~~~text
public.canAccess=true
private.canAccess.before=false
private.try=true
private.set=ok
public.invoke=visible
private.invoke=hidden
~~~

Explanation: Initially the private method still does not belong to the caller's normal Java permissions, so `canAccess` is `false`. However, the package is **opened** to the caller, so `trySetAccessible` enables the flag successfully; `setAccessible(true)` is also permitted, after which `canAccess` is `true` and `invoke` runs `secret()`.

**Opening a package does not turn `private` into `public`.** Normal Java source code in demo.client still cannot call `api.secret()`. Only the reflective access path is allowed to enable suppression under the appropriate configuration.

### 7.3. An Exported Package Is Not Enough for Private Reflection

With named modules, the check must distinguish:

| Condition from caller module | Public exported member | Private member via trySetAccessible |
| --- | --- | --- |
| `demo.lib exports sample.api` but does not open it | Accessible with normal permissions | Denied unless other special permissions apply |
| `demo.lib opens sample.api to demo.client` | Public API still works | Can enable suppression from demo.client |
| Runtime `--add-opens demo.lib/sample.api=demo.client` | Public API still works | Can enable suppression from demo.client |
| Package neither exported nor opened to caller module | Normal access is also restricted | Cannot be bypassed by setAccessible |

In a classpath environment, unnamed modules have different package-opening rules than named modules; therefore the same reflection example may run on the classpath but fail after switching to the module path. Always test on the **actual deployment setup**.

**Limitations of add-opens:** A runtime option is a configuration decision that affects encapsulation; you should not add broad openings just to avoid handling errors. For production applications, prefer a public API or configure **opens ... to** for the specific framework/module that needs deep reflection.

## 8. Comparing How to Handle Each Result

| Result | Accurate meaning | How to handle |
| --- | --- | --- |
| `canAccess(receiver) == true` | The Reflection operation is currently permitted | Invoke directly; still catch business/runtime errors during execution |
| `canAccess(receiver) == false` | The caller cannot currently access the member as-is | Check whether private access is needed or a public API alternative exists |
| `trySetAccessible() == true` | Managed to set the accessible flag to true | Can invoke the member with valid receiver/args; watch for other errors |
| `trySetAccessible() == false` | Cannot enable the flag under current rules | Fall back, report the restriction, or deliberately adjust module configuration |
| `setAccessible(true)` succeeds | Requested enabling the flag successfully | Invoke the member and manage the flag lifecycle per contract |
| `setAccessible(true)` throws `InaccessibleObjectException` | Module mechanism blocks suppression | Do not force-invoke; use a public API or open the package appropriately |
| `setAccessible(false)` succeeds | Disabled the override on the Reflection object | Normal permissions remain; check `canAccess` if needed |

### 8.1. Cases Where false Is Not Enough to Diagnose the Entire Failure

`canAccess` is a boolean about permission at the time of the check; it **does not prove** that the code will execute successfully:

- A wrong receiver or invalid `null` can cause `IllegalArgumentException` right inside `canAccess`.
- `Method.invoke` can fail due to argument count/types, or the target method itself throwing an exception.
- A field may be `final` or non-modifiable final under API constraints; **enabling the accessible flag does not guarantee write permission**.
- A shared Reflection object whose flag is modified concurrently can make an earlier check result invalid by the time of invocation.
- Changes in class loader, version, or module graph in a plugin architecture can invalidate assumptions about a class/member.

**Especially for final fields:** `setAccessible(true)` is not a tool that allows modifying every `final`; strong restrictions exist for static final, certain final fields in records, and hidden classes. Consult the specific member API and design immutable objects instead of relying on mutating final fields via Reflection.

## 9. Distinguishing Exceptions by Stage

| Step | Error type | Meaning/handling |
| --- | --- | --- |
| `getDeclaredMethod(...)` | `NoSuchMethodException` | Wrong name/signature; not an access error yet |
| `canAccess(receiver)` | `IllegalArgumentException` | Receiver violates the instance/static/constructor contract |
| `trySetAccessible()` | `false` | Cannot open access under current constraints; handle the branch |
| `trySetAccessible()` or `setAccessible(...)` | `SecurityException` in environments with related checks | Requires appropriate permission policy; do not assume only false occurs |
| `setAccessible(true)` | `InaccessibleObjectException` | Package/module does not allow suppressing access checks |
| `Method.invoke(...)` | `IllegalAccessException` | Lacks the required reflective access permission |
| `Method.invoke(...)` | `IllegalArgumentException` | Incompatible receiver or arguments |
| `Method.invoke(...)` | `InvocationTargetException` | Target method ran but threw an exception; inspect `getCause()` |

You should not catch every `Exception` and report “private method is locked”: access errors, data errors, missing members, and business errors have different causes.

For example, when a valid method throws `IllegalStateException`, `Method.invoke` typically wraps it in `InvocationTargetException`; `canAccess` may still have been true before the call. Surface the cause and control sensitive information when logging.

## 10. Real-World Applications and Safe Design

Reflection accessing non-public members appears in serializers, ORMs, dependency injection, plugin systems, or testing tools. With Java 17+, explicit module encapsulation requires framework and application authors to agree on contracts rather than relying on the assumption that every private member can be opened.

Principles:

1. **Prefer public APIs and clear contracts.** If the class owner can provide the necessary constructor, getter, setter, or interface, those approaches are usually easier to maintain than deep reflection.
2. **Check the right member and receiver.** Do not run `canAccess(null)` for an instance method; do not pick the wrong method overload.
3. **Only enable suppression when truly needed.** When `canAccess` is already true, invoke directly; when false, determine whether attempting to open access is allowed.
4. **Handle the result of `trySetAccessible`.** Have a clear fallback/unsupported branch; do not swallow false and then invoke only to let an error blow up elsewhere.
5. **If `setAccessible(true)` is required, catch the right error.** Use `InaccessibleObjectException` to handle JPMS denials; do not use a catch-all that hides business errors.
6. **Limit the deep reflection surface.** For modules you own, consider `opens package to framework.module`; avoid broad `opens` or `--add-opens` to all modules without reason.
7. **Do not use accessibility as a sandbox boundary.** Class loaders, `private`, and access flags do not replace execution permission controls for untrusted code.
8. **Account for actual deployment.** Java classpath, module path, container runtime images, and plugin class loaders can differ in accessibility. Write integration tests on the real production configuration.
9. **Do not rely on isAccessible() as a permission check.** `isAccessible()` only reflects the override flag; `canAccess` answers the right question.
10. **Avoid sharing mutable accessible flag state across threads.** Cache verified members per appropriate module/loader context; do not arbitrarily reset the flag while other components are still using it.

### 10.1. Quick API Selection Table

| Situation | API to consider |
| --- | --- |
| Only need to know if a method can currently be called or a field read | `canAccess(correctReceiver)` |
| Have a fallback and need to try deep reflection without using exceptions as the module-denial branch | `trySetAccessible()` + boolean check |
| Execution strictly requires deep reflection or an explicit fail fast | `setAccessible(true)` + handle `InaccessibleObjectException` |
| Finished a batch of use and want to disable suppression on your own Reflection object | `setAccessible(false)`, noting public members may still be accessible |
| Do not control package opening in the module owning the class | Use a public API/adapter; report the limitation instead of assuming setAccessible will break through the module |
| Need private access within a module you manage | Design targeted `opens` or a public contract; consider MethodHandles APIs depending on requirements |

## 11. Self-Check

**Question 1.** A public method belongs to a public class in a package exported to the caller. The accessible flag is currently false. Is `canAccess(validReceiver)` necessarily false?

**Answer:** No. If normal Java permissions allow it, `canAccess` is still true even while the suppression flag is false.

**Question 2.** `getDeclaredMethod` finds a private method of another named module. Can it be invoked immediately with `Method.invoke`?

**Answer:** That cannot be inferred. You need to check current permissions with `canAccess`, and if there is a valid need, try `trySetAccessible`. If the module does not open the package and no other special permissions apply, deep reflection may be denied.

**Question 3.** `trySetAccessible()` returns false. Should you immediately call `setAccessible(true)` expecting it to force access open?

**Answer:** No. `setAccessible(true)` is also subject to module constraints; it will usually throw `InaccessibleObjectException` instead of returning false. Choose a fallback or deliberately change the package-opening configuration.

**Question 4.** After `setAccessible(false)`, is `canAccess` on an accessible public method necessarily false?

**Answer:** No. `setAccessible(false)` only disables the suppress-access-checks flag; normal Java permissions for a public method can still make `canAccess` true.

**Question 5.** Does calling `instanceMethod.canAccess(null)` return `false` or can it throw an error?

**Answer:** That is an invalid receiver for an instance method; the API can throw `IllegalArgumentException`. Use a compatible receiver object.

**Question 6.** Why does code succeed on the classpath when calling `trySetAccessible` on a private field, but fail when moved to a named module?

**Answer:** Package-opening rules differ between modules. Unnamed modules generally open packages for deep reflection; another named module may only export without opening the package. You must check the actual module graph and package opens.

**Question 7.** Does `canAccess` returning true mean the target method will never throw an exception?

**Answer:** No. The check is only about access permission. `Method.invoke` can still fail due to receiver/args or report `InvocationTargetException` if the target method throws an exception.

## Key Takeaways

- `canAccess(receiver)` is a **check for whether access is possible right now**, from the current caller context, with a valid receiver.
- `trySetAccessible()` is an **attempt to enable the accessible flag and receive true/false**; false should be handled as a valid branch.
- `setAccessible(true)` is a **request to enable the flag, which can throw InaccessibleObjectException** if JPMS disallows it; `setAccessible(false)` only disables the override flag.
- **Finding a member does not mean being able to invoke the member.** `getDeclaredMethod/getDeclaredField` and access checks are separate steps.
- **exports is different from opens**: an exported public API does not by default permit deep reflection into private members.
- Prefer **public APIs or controlled module opens**; do not write code assuming Reflection always bypasses encapsulation.

## References

- Java SE 17 — **AccessibleObject**, `canAccess`, `trySetAccessible`, `setAccessible`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html
- Java SE 17 — **InaccessibleObjectException**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html
- Java SE 17 — **Method** and `invoke`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html
- Java SE 17 — **Module** and encapsulation: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- OpenJDK Java 17 — **Java Platform Module System / --add-opens**: https://openjdk.org/jeps/261
