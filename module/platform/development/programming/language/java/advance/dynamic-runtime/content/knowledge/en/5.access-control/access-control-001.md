# 5.1 Distinguishing between seeing a component and being allowed to use it

When analyzing access control in Java, two questions must be separated:

1. **Can the component be found, identified, or retrieved information about?** For example: finding a `Class<?>` using `Class.forName(...)`, listing a `private` field using `getDeclaredField(...)`, or seeing a method name in bytecode.
2. **Is the code at the current location allowed to use that component?** For example: writing an access expression in Java source, reading a field using `Field.get(...)`, calling a method using `Method.invoke(...)`, or creating a `MethodHandle` to that member.

The two questions can have different answers. **Finding metadata does not automatically grant permission to read, write, invoke, or instantiate.** A `public` method of a non-`public` class is not necessarily accessible from elsewhere either. In Java 9+ (including Java 17), the module system also adds `requires`, `exports`, and `opens` boundaries.

This lesson belongs to the **Access Control** group of Java dynamic runtime, so the focus is on the boundary between *discovering a component* and *executing an operation* in Java source, Reflection, Method Handles, and the Java Platform Module System (JPMS).

## 1. Using precise terminology: what is "seeing"?

In technical discussions, "seeing" (*visible/discoverable*) has at least three contexts:

- **Seeing a name in source:** a name is within a *scope* that can be resolved, imported, or referenced from the code being compiled. However, Java still has to check *accessibility*, such as whether the type is `public`, in the same package, or whether the module exports the package.
- **Finding a class at runtime:** a class loader can find/define the class, or `Class.forName("pkg.Type")` returns `Class<?>`. That does not prove the caller is allowed to invoke a constructor or method.
- **Finding metadata via Reflection:** `getDeclaredFields()`, `getDeclaredMethods()`, `getDeclaredConstructor()` can return `private`/package-private/protected members. Receiving a `Field`/`Method`/`Constructor` does not mean being allowed to use them.

Therefore, in this lesson **"seeing" is used in the broad sense of discovering a name/type/metadata**; do not assume it is the sole official JLS term. The JLS clearly distinguishes **scope** (the region where a name can be used) from **access control** (permission to access a declaration); the condition to see a name and the condition to be allowed to use it usually both have to be satisfied.

**"Being allowed to use"** also takes many forms: compile-time access, runtime link/access check, Reflection permissions, and `MethodHandles.Lookup` permissions. A check succeeding at one layer does not automatically replace all checks at other layers.

| Question | Example check or operation | What can happen |
| --- | --- | --- |
| Can source code reference the type? | `import api.Service`, `new Service()` | The compiler rejects it if the type is not accessible or the package is not exported |
| Can runtime load/find the class? | `Class.forName("internal.Helper")` | Returns `Class<?>` even if the type is package-private; may fail if it cannot be found/initialized |
| Can Reflection list the member? | `type.getDeclaredField("secret")` | Returns `Field` for a private field |
| Can the caller use the member directly? | `obj.secret` | The compiler rejects it if `secret` is private outside a valid scope |
| Can the caller use the member via Reflection? | `field.get(obj)` | May throw `IllegalAccessException` |
| Can Reflection access checks be bypassed? | `field.trySetAccessible()` | Returns `true` if possible, `false` if blocked by module/permission rules |
| Can Method Handles create a handle? | `lookup.findGetter(...)` | May throw `IllegalAccessException` even though metadata exists |

Practical rule: **you must ask "who is accessing, what operation is being performed, on which type and member, in which package/module?"** A member's `public` level is only part of the answer.

## 2. Access checks in Java source: both the type and the member must be accessible

Java has four common access levels for class members:

| Modifier | Member access rule | Common point of confusion |
| --- | --- | --- |
| `public` | Allowed from code that can access the declaring type, with module constraints when crossing to another module | `public` on a member **does not** turn a package-private declaring class into public |
| `protected` | Within the same package; or from a subclass outside the package with rules restricting the receiver expression for instance members | Does not mean any superclass object can be called from a subclass in another package |
| *No modifier* (package-private) | Code belonging to the same **valid runtime package**; in source, usually called "same package" | Packages with the same name in different class loaders/modules may not be treated by the JVM as the same runtime package |
| `private` | Code within a valid private-access scope; Java 11+ supports nestmates with private access | `private` does not mean metadata cannot be discovered |

Top-level classes/interfaces can only be `public` or package-private; top-level classes cannot be declared `private`/`protected`. Member classes can carry the appropriate modifiers.

**Two mandatory layers:** to call `Type.member` from elsewhere, **`Type`** must be accessible first, and then **`member`** is checked. A `public` method inside a package-private class still does not become a global public API.

### Example 1: seeing a private member via Reflection but not being able to read it immediately

Create three files belonging to a project run on the classpath, in which the calling code and the class containing the field are in **two different packages** to avoid private access within the same nest:

**`src/catalog/PublicTool.java`**

~~~java
package catalog;

public class PublicTool {
    private String secret = "inside";

    public String greet() {
        return "hello";
    }
}
~~~

**`src/client/ReflectionAccessDemo.java`**

~~~java
package client;

import catalog.PublicTool;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class ReflectionAccessDemo {
    public static void main(String[] args) throws Exception {
        PublicTool tool = new PublicTool();

        Method method = PublicTool.class.getMethod("greet");
        Field field = PublicTool.class.getDeclaredField("secret");

        System.out.println("found=" + field.getName());
        System.out.println("method.canAccess=" + method.canAccess(tool));
        System.out.println("method.invoke=" + method.invoke(tool));
        System.out.println("field.canAccess.before=" + field.canAccess(tool));

        try {
            field.get(tool);
        } catch (IllegalAccessException ex) {
            System.out.println("field.get=IllegalAccessException");
        }

        System.out.println("trySetAccessible=" + field.trySetAccessible());
        System.out.println("field.canAccess.after=" + field.canAccess(tool));
        System.out.println("field.get=" + field.get(tool));
    }
}
~~~

At the root directory of the project, compile/run with JDK 17+:

~~~sh
javac --release 17 -d out src/catalog/PublicTool.java src/client/ReflectionAccessDemo.java
java -cp out client.ReflectionAccessDemo
~~~

**Exact stdout in the classpath (unnamed module) example:**

~~~text
found=secret
method.canAccess=true
method.invoke=hello
field.canAccess.before=false
field.get=IllegalAccessException
trySetAccessible=true
field.canAccess.after=true
field.get=inside
~~~

What happens?

1. `PublicTool` is `public`, and the `greet()` method is also `public`, so `client.ReflectionAccessDemo` can reference and call `greet()`.
2. `getDeclaredField("secret")` **finds the declaration** of the `private` field, even though the caller is outside the package. The API returns a `Field` to describe the field.
3. `field.canAccess(tool)` is initially `false`, and `field.get(tool)` throws `IllegalAccessException`: Reflection still checks access permissions when using the member.
4. `field.trySetAccessible()` succeeds in this example because both classes are in the unnamed module, where packages are open for reflective access. Afterward, this specific `Field` can read the field.
5. `trySetAccessible()` **does not change the source modifier** from `private` to `public`. The Java line `tool.secret` in class `client.ReflectionAccessDemo` still does not compile. If the package is in a named module without an appropriate `opens`, `trySetAccessible()` can return `false`.

**Do not apply the `trySetAccessible=true` result of the classpath example to all modular applications.** Reflection access permissions depend on the caller's location, module, and package opening configuration; we will verify this with a JPMS example.

### Compile-time access and Reflection are two different paths

The following line intentionally **does not compile** when added to class `client.ReflectionAccessDemo` above:

~~~java
System.out.println(tool.secret); // error: secret has private access
~~~

There is no way to turn a Java source access rejected by the compiler into a valid one merely by having Reflection call `setAccessible(true)` beforehand. Reflection is a runtime operation on `Field`/`Method`, not something that modifies JLS access rules of other source code.

Conversely, a `public` method accepted by the compiler does not mean a framework can always invoke it on any arbitrary `Object`: invoking requires the right receiver, number/types of arguments, and may throw an exception from the method body. **Access permission is a necessary condition, not the entire contract for using a component.**

## 3. "Seeing the class" but not being allowed to use it: package-private type

A top-level class not declared `public` only has package access. Even so, its `.class` file can still be found by the class loader, and Reflection can observe much of the metadata inside.

**`src/internal/PackageTool.java`**

~~~java
package internal;

class PackageTool {
    public PackageTool() {}

    public String run() {
        return "ok";
    }
}
~~~

Class `PackageTool` is **package-private**, even though its constructor and `run()` are declared `public`. Create a caller in another package.

**`src/client/PackageVisibilityDemo.java`**

~~~java
package client;

import java.lang.reflect.Constructor;
import java.lang.reflect.Method;

public class PackageVisibilityDemo {
    public static void main(String[] args) throws Exception {
        Class<?> type = Class.forName("internal.PackageTool");
        System.out.println("found=" + type.getSimpleName());

        Constructor<?> constructor = type.getDeclaredConstructor();
        System.out.println("constructor.canAccess=" +
                           constructor.canAccess(null));

        try {
            constructor.newInstance();
        } catch (IllegalAccessException ex) {
            System.out.println("newInstance=IllegalAccessException");
        }

        System.out.println("openConstructor=" +
                           constructor.trySetAccessible());
        Object value = constructor.newInstance();

        Method method = type.getMethod("run");
        System.out.println("methodFound=" + method.getName());
        System.out.println("method.canAccess=" + method.canAccess(value));

        try {
            method.invoke(value);
        } catch (IllegalAccessException ex) {
            System.out.println("invoke=IllegalAccessException");
        }

        System.out.println("methodOpen=" + method.trySetAccessible());
        System.out.println("result=" + method.invoke(value));
    }
}
~~~

~~~sh
javac --release 17 -d out src/internal/PackageTool.java src/client/PackageVisibilityDemo.java
java -cp out client.PackageVisibilityDemo
~~~

**Stdout:**

~~~text
found=PackageTool
constructor.canAccess=false
newInstance=IllegalAccessException
openConstructor=true
methodFound=run
method.canAccess=false
invoke=IllegalAccessException
methodOpen=true
result=ok
~~~

Analysis:

- `Class.forName("internal.PackageTool")` finds the runtime type on the classpath, **without turning that type into an accessible type** for package `client`.
- `constructor` is obtained via `getDeclaredConstructor()`; `method` is obtained via `getMethod("run")` because `run()` is a `public` method. These two metadata lookup results do not guarantee valid instantiation or invocation.
- `Constructor.newInstance()` and `Method.invoke()` both check permissions, including **access permission to the declaring class**. They are rejected before suppression is enabled.
- `trySetAccessible()` succeeds in the experiment because the packages are in the unnamed module. Afterward, Reflection can operate on those reflective objects.
- If `import internal.PackageTool;` is added or `new internal.PackageTool()` is written in source in `client`, the compiler still reports an error because the class is not `public`.

**Key takeaway:** a class/method "being present" and having a "public member" is still not enough; the declaring type must be accessible from the caller. Receiving `Class<?>` is proof of existence, not a license to use every component of the class.

## 4. `getMethod` vs. `getDeclaredMethod`: search scope, not permission

Reflection has two groups of APIs that are often misunderstood:

| API | Typical search scope | What does it NOT prove? |
| --- | --- | --- |
| `Class.getMethod(name, types...)` | Visible `public` methods in the class and matching inherited `public` methods | That the caller has permission to `invoke` with any receiver |
| `Class.getMethods()` | List of `public` methods of the class and inherited `public` methods | That the declaring class of every method is accessible from the caller |
| `Class.getDeclaredMethod(name, types...)` | Methods declared directly in the class, including `private`/protected/package-private; does not traverse inherited methods | That the caller is allowed to invoke the method body |
| `Class.getDeclaredMethods()` | Set of directly declared methods, any access modifier | That every method in the array is allowed to be invoked |
| `Class.getField(...)` / `getDeclaredField(...)` | Similar for fields: visible `public` vs. directly declared | That the caller is allowed to read/write the field |
| `Class.getConstructor(...)` / `getDeclaredConstructor(...)` | `public` constructors vs. directly declared constructors | That the caller is allowed to create an instance |

The statement **"`getDeclaredMethod` can retrieve a private method"** only talks about *querying metadata*. Permission to call it is a separate step. If `getMethod` is used and does not find a `private` method, `NoSuchMethodException` does not prove that the method does not exist; it may simply be that the wrong search scope was chosen.

In addition to Java access, metadata lookups can throw other exceptions (such as `SecurityException` in environments enforcing relevant policies); do not claim "everyone can always view all metadata."

### Runtime checks must be used for their intended purpose

For `Field`, `Method`, and `Constructor` (all inheriting from `AccessibleObject`):

- `canAccess(Object target)`: asks whether the **current caller** can use this reflected object on the corresponding target, taking into account the suppression state of the reflected object itself. For an **instance field/method**, target must be an appropriate instance; for a **static field/method** and constructor, pass `null`. Calling with the wrong target kind may yield `IllegalArgumentException`; do not use `canAccess` as a function that returns `false` for every wrong target.
- `trySetAccessible()`: **attempts to enable** suppression of Java access checks; returns `true`, or `false` when not possible under module rules. It is not a side-effect-free query: when successful it **mutates the accessible flag** of the reflected object.
- `setAccessible(true)`: requests enabling suppression; may throw `InaccessibleObjectException` when blocked by a module, and in some cases also `SecurityException`.
- `isAccessible()`: deprecated since Java 9. Its name is misleading; it only reads the **suppression flag**, not whether the caller actually has permission. Prefer `canAccess(target)` for the question "can it be used right now?".
- `getModifiers()` with `Modifier.isPublic/isPrivate/isProtected(...)`: describes the **declared modifier**, not a full confirmation of a specific caller's permissions. One must also consider declaring class, package, receiver, and module.

**Important example:** a `public Method` has `isAccessible() == false` by the default value of the accessible flag, yet `canAccess(obj) == true` if the caller has public access permission. Therefore `isAccessible() == false` must not be interpreted as "forbidden to invoke."

### Access does not mean ability to mutate a value

Even when `trySetAccessible()` returns `true`, certain final fields still cannot be written via reflection, such as `static final` fields, final fields in records, and hidden classes per the Java 17 API. Changing the suppression flag **does not abolish all immutability and operation-validity constraints**. Likewise, an authorized reflective method call still needs the right receiver and argument types.

## 5. JPMS (Java 9+): `requires`, `exports`, and `opens` determine different permissions

Since Java 9, with **named modules**, a `public` type or member is not enough for an API to be used across modules. The module graph and package directives must be examined.

| Mechanism | Primary meaning | What must NOT be inferred |
| --- | --- | --- |
| `requires another.module;` | Creates a module readability relationship for the current module's code; supports using exported public APIs | That the read module automatically opens private members |
| `exports p;` | Exposes the public/protected API of package `p` to modules allowed to read the source module | That it allows accessing private members of `p` via `setAccessible(true)` |
| `exports p to consumer.mod;` | Exports the package only to the specified module | That other modules can also see the API to compile |
| `opens p;` | Allows deep reflection into package `p` at runtime for other modules | That it allows source in another module to import types of that package without `exports` |
| `opens p to consumer.mod;` | Opens the package for deep reflection only to the specified module | That it opens to all modules on the module path |
| `open module m { ... }` | Opens the module's packages for Reflection per the open module contract | That it automatically turns every public API or encapsulation design into safe |
| `--add-opens source.module/pkg=target.module` | Adds runtime package-opening permission for the specified target module | That it alters source modifiers, inheritance relationships, or compile-time permissions |
| `--add-exports source.module/pkg=target.module` | Adds an export for the target module under appropriate run/compile configuration | That it automatically allows private-field deep reflection like `--add-opens` |

**Core distinction:**

- **`exports`** supports compiling/linking and normal reflective access to `public` APIs whose declaring type is accessible. It **does not** by itself allow deep reflection into private members.
- **`opens`** supports reflective access at runtime, including non-public components when appropriate APIs/permissions are present; `opens` alone **does not** grant direct import/usage permission like `exports`.
- With named modules, `public` on a class/method is only a **language-level** condition, whereas export/open belongs to **module boundaries**.
- The unnamed module (typical classpath applications) has different openness properties from named modules: packages of the unnamed module are open for reflective access, so the results of the classpath examples above may differ from applications deployed on the module path.

For Reflection, the `AccessibleObject` documentation also notes a subtlety: when performing access checks on a reflected object, the runtime **assumes a module readability relationship** for the purpose of this check. Therefore `field.canAccess(...)` should not be used as the sole substitute for checking `requires` in source. When needing to confirm that a module reads another module, use `Module.canRead(...)` and evaluate the actual module graph; when needing to check package export/open, use `Module.isExported(...)` / `Module.isOpen(...)` with the appropriate target module.

### Example 3: `public` type is usable, private field is visible, but Reflection is blocked by the module

Create an application consisting of two named modules. Directory and file names:

~~~text
src/
├── com.example.library/
│   ├── module-info.java
│   └── example/library/api/Account.java
└── com.example.app/
    ├── module-info.java
    └── example/app/Main.java
~~~

**`src/com.example.library/module-info.java`**

~~~java
module com.example.library {
    exports example.library.api;
}
~~~

**`src/com.example.library/example/library/api/Account.java`**

~~~java
package example.library.api;

public class Account {
    private String pin = "4242";

    public String status() {
        return "READY";
    }
}
~~~

**`src/com.example.app/module-info.java`**

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

**`src/com.example.app/example/app/Main.java`**

~~~java
package example.app;

import example.library.api.Account;
import java.lang.reflect.Field;
import java.lang.reflect.InaccessibleObjectException;

public class Main {
    public static void main(String[] args) throws Exception {
        Account account = new Account();
        System.out.println("public=" + account.status());

        Field field = Account.class.getDeclaredField("pin");
        System.out.println("fieldFound=" + field.getName());
        System.out.println("canAccess=" + field.canAccess(account));

        boolean enabled = field.trySetAccessible();
        System.out.println("trySetAccessible=" + enabled);
        if (enabled) {
            System.out.println("fieldValue=" + field.get(account));
        } else {
            System.out.println("fieldValue=DENIED");
        }

        try {
            field.setAccessible(true);
            System.out.println("setAccessible=enabled");
        } catch (InaccessibleObjectException ex) {
            System.out.println("setAccessible=InaccessibleObjectException");
        }
    }
}
~~~

Compile with JDK 17 or higher from the directory containing `src`:

~~~sh
javac --release 17 -d mods --module-source-path src src/com.example.library/module-info.java src/com.example.library/example/library/api/Account.java src/com.example.app/module-info.java src/com.example.app/example/app/Main.java
java --module-path mods -m com.example.app/example.app.Main
~~~

**Stdout when library only `exports`, without `opens`:**

~~~text
public=READY
fieldFound=pin
canAccess=false
trySetAccessible=false
fieldValue=DENIED
setAccessible=InaccessibleObjectException
~~~

Explanation:

1. Module `com.example.app` has `requires com.example.library` and package `example.library.api` is exported. Therefore the caller compiles and invokes `account.status()` normally.
2. `getDeclaredField("pin")` still retrieves the `Field` metadata for the private field.
3. `field.canAccess(account)` is `false`. When the package is not opened, `trySetAccessible()` cannot enable suppression across the module boundary and returns `false`.
4. `setAccessible(true)` makes a similar request, but instead of returning `false` it throws `InaccessibleObjectException`. Catching the exception above only helps display the module-denial case; not all causes of Reflection denial produce the same exception type.
5. Field `pin` is marked `private` and belongs to a named module that has not opened the package. `exports` provides the public API, not deep reflection into this field.

**Try granting package-opening permission at runtime**, keeping all source and class files unchanged:

~~~sh
java --module-path mods --add-opens com.example.library/example.library.api=com.example.app -m com.example.app/example.app.Main
~~~

**Stdout of the run with `--add-opens`:**

~~~text
public=READY
fieldFound=pin
canAccess=false
trySetAccessible=true
fieldValue=4242
setAccessible=enabled
~~~

An alternative in the library module source is to add:

~~~java
module com.example.library {
    exports example.library.api;
    opens example.library.api to com.example.app;
}
~~~

After **recompiling**, the target module `com.example.app` can deep-reflect into the opened package. If a framework does not need Java source to directly import the API, sometimes the design uses only `opens`, though each specific API and module resolution must be examined.

**Design choice:** open the exact package to the exact consumer module if truly needed, rather than opening the entire module unconditionally. Do not use `--add-opens` to replace public API design everywhere.

## 6. Method Handles: receiving `Class` is not enough to have an appropriate `Lookup`

`java.lang.invoke.MethodHandles.Lookup` is an object carrying an **access permission context**. With `findVirtual`, `findStatic`, `findGetter`, `findSetter`, or `findConstructor`, the runtime checks the lookup's permissions and the declaring type/member before returning a `MethodHandle`.

That means:

- `Class<?>` and the member name describe **what to look up**.
- `MethodHandles.Lookup` describes **who is requesting access and with what modes**.
- One cannot infer "obtained `Class<?>`" → "can create any method handle on that class."

`MethodHandles.lookup()` creates a lookup with permissions according to the **calling class**; `MethodHandles.publicLookup()` is very restricted, only using public members/types in packages exported under the API's conditions. `MethodHandles.privateLookupIn(targetClass, callerLookup)` can create a lookup with private access for the target when the caller has corresponding rights; across **two different named modules**, it also requires a reads relationship and the source package `opens` to the caller's module. It is not a command that bypasses all module boundaries.

### Example 4: same class, regular lookup is denied, private lookup is allowed

Reuse `src/catalog/PublicTool.java` from example 1, keeping the field `private String secret = "inside";`. Create a new file **`src/client/LookupDemo.java`**:

~~~java
package client;

import catalog.PublicTool;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;

public class LookupDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        try {
            lookup.findGetter(PublicTool.class, "secret", String.class);
        } catch (IllegalAccessException ex) {
            System.out.println("findGetter=IllegalAccessException");
        }

        MethodHandles.Lookup privileged =
            MethodHandles.privateLookupIn(PublicTool.class, lookup);
        MethodHandle getter =
            privileged.findGetter(PublicTool.class, "secret", String.class);

        System.out.println("value=" +
                           (String) getter.invoke(new PublicTool()));
    }
}
~~~

~~~sh
javac --release 17 -d out src/catalog/PublicTool.java src/client/LookupDemo.java
java -cp out client.LookupDemo
~~~

~~~text
findGetter=IllegalAccessException
value=inside
~~~

In the classpath example, `client.LookupDemo` is not allowed to read the private field via the default lookup. `privateLookupIn` succeeds because the two classes belong to the unnamed module, which can deep-reflect per API rules. If `PublicTool` is moved to **another named module** without opening the package to the caller, the `privateLookupIn` operation can throw `IllegalAccessException`.

Unlike `Field.trySetAccessible()`, this is a mechanism for creating a lookup/method handle with corresponding permissions. Do not mix the two APIs or assume changing the accessible flag of a `Field` grants permissions to every existing `Lookup`.

## 7. `protected`: "seen by a subclass" still has receiver conditions

`protected` is especially easy to misunderstand across package boundaries. Within the **same package**, `protected` members are generally accessible under package rules. In a **different package**, a valid subclass context is required, and for instance members, the JLS also applies rules to the **type of the receiver expression**.

Illustrative example (each part in a separate file/package; do not compile lines commented as errors):

**`src/base/Parent.java`**

~~~java
package base;

public class Parent {
    protected String name() {
        return "parent";
    }
}
~~~

**`src/child/Child.java`**

~~~java
package child;

import base.Parent;

public class Child extends Parent {
    public String allowed() {
        return this.name();  // valid: called on this of subclass
    }

    public String alsoAllowed(Child other) {
        return other.name(); // valid: receiver has type Child
    }

    // If uncommented, the line below does not compile:
    // public String forbidden(Parent other) { return other.name(); }
}
~~~

Even when `other` actually references a `Child` instance, the compiler still checks the **type of the expression** when verifying protected access under JLS `6.6.2`. "I am a subclass" is not enough to call `other.name()` on every variable of type `Parent` in another package. With Reflection, access checks also examine the caller and receiver per API rules; `Modifier.isProtected(...) == true` is not the final conclusion.

## 8. What other boundaries exist in the Java runtime?

### Classpath/ClassLoader does not automatically grant Java access

A class loader decides how classes are found and defined. Java access control (source/JVM/Reflection) decides how types/members can be used from a caller's context. A successful `Class.forName(...)` result indicates that the runtime found a class in an appropriate loader context; it does not promise that the caller has permission to call a private constructor, read a field, or invoke any method.

Conversely, a `public` class in an exported package can still fail to load if a dependency is missing, the bytecode version is wrong, a module is not resolved, or class initialization fails. **Being allowed access** does not mean the operation is guaranteed to succeed technically.

### Scope, access, reflection metadata, and security are different questions

- **Scope:** a `local variable` name only exists within a block; not because it has a `private` access modifier.
- **Java access:** `public/protected/package-private/private` together with declaring type and module determine what can be referenced from source/an appropriate context.
- **Reflection metadata:** `getDeclared*` can return nonpublic members; finding them does not confirm the caller can operate on them.
- **Suppression:** `trySetAccessible`/`setAccessible` can allow certain runtime operations under the API and module contract, without modifying the component's declaration.
- **Runtime linkage:** bytecode generated/modified to bypass the compiler can encounter `IllegalAccessError` when the JVM links an invalid reference. This is not the same exception as Reflection's `IllegalAccessException`.
- **Method Handles:** `Lookup` has its own permissions and modes; `privateLookupIn` is constrained by modules and the trust of the caller lookup.
- **Encapsulation:** `private` is an access barrier at the Java language/runtime level, not a data encryption mechanism. With appropriate runtime permissions, some frameworks can still introspect; design and protect secrets according to separate security requirements.

### Nestmates and private access

Java 11+ supports *nest-based access control*: classes belonging to the same valid nest (for example, an outer class and some nested classes) can access each other's private members per JVM rules. Therefore, examples that place all classes under a **top-level outer class** sometimes cause `Field.canAccess` to return `true` even when trying to demonstrate forbidden access. The examples in sections 2–3 intentionally separate source into independent packages/classes to observe clear results.

This point does not change the principle: the **actual caller** must be examined. Two pieces of code reading the same `private Field` can yield different `canAccess(...)` results because the callers belong to different nests/packages/modules.

### A `Method` can be retrieved but not invoked, or invoked and its body throws an error

Having a valid `Method` does not guarantee `invoke` will succeed. For an instance method, the receiver must be appropriate; arguments must be correct; access permissions must be valid; the method body may throw an exception and Reflection will wrap it in `InvocationTargetException`. In particular, **dynamic dispatch** may select a subclass override when calling an instance method, but that is independent of whether the caller has sufficient permission to call the method via Reflection. Access errors should not be conflated with implementation-selection errors.

## 9. Classifying errors when investigating real applications

| Symptom | Where does the issue usually lie? | Direction to check |
| --- | --- | --- |
| `cannot find symbol` at compile time | Name, import, scope, dependency | Full name, classpath/module path, scope |
| Compiler reports type/member "not public" or "has private access" | Java source access | Declaring class, modifier, package, subclass |
| `ClassNotFoundException` | Runtime cannot find class by loader/path, or invalid lookup method | Binary name, class loader, module resolution |
| `NoSuchMethodException` / `NoSuchFieldException` | Component not found by lookup API/signature | `get*` vs `getDeclared*`; exact parameter types |
| `IllegalAccessException` at `Field.get`/`Method.invoke`/`Constructor.newInstance` | Reflection access check rejected | `canAccess`, declaring type, caller, module `exports/opens` |
| `trySetAccessible() == false` | Cannot enable suppression under access/module rules | Whether package has `opens` for caller; caller permissions |
| `InaccessibleObjectException` at `setAccessible(true)` | Cannot open access due to module/permission constraints | Named modules, `opens`, `--add-opens` |
| `IllegalAccessException` at `privateLookupIn`/`findGetter` | Lookup lacks permission, mode, or module access | Caller `Lookup`, readability, package `opens` |
| `IllegalAccessError` when executing bytecode | JVM linkage/runtime access check sees invalid reference | Build version, changed modifiers, generated bytecode, modules |
| `InvocationTargetException` after `Method.invoke` | Target method ran and threw an error | `getCause()`; stack trace of the original method |
| `IllegalArgumentException` when calling access API | Inappropriate target/argument | Static vs instance, declaring class, argument types/count |

**Analyze in order** to avoid going in the wrong direction:

1. **Identify where it fails:** source compile, class loading, metadata lookup, access check, invoke, or code inside the target?
2. **Identify the actual caller:** which class/package/module is calling `get`/`invoke`/`Lookup`? Do not look only at the class owning the object.
3. **Identify the declaring type and member:** `getDeclaringClass()`, `getModifiers()`, name, signature, static/instance. A `public` member in an inaccessible declaring class can still be blocked.
4. **Identify the receiver:** for instance members, check runtime type and access/override rules; for `canAccess` on a static member or constructor, pass `null`.
5. **Identify the module boundary:** for named modules, check `requires`/readability, `exports` for public APIs, `opens` for deep reflection.
6. **Choose the verification API:** `canAccess` to ask if it can be used right now; `trySetAccessible` only when genuinely wanting to enable suppression; `Module.isOpen/isExported` for package-level module policy.
7. **Choose the right-sized solution:** prefer public APIs or a method handle proactively provided by the target module; only open packages or bypass checks when there is a clear architectural need. Do not open all JDK internals just to hide a design flaw.

### Metadata inspection pattern for diagnostic tools

The following is an **illustrative snippet**, using existing variables `field` (of type `Field`) and `receiver`; it is not a standalone program:

~~~java
Class<?> owner = field.getDeclaringClass();
Class<?> caller = MyInspector.class;

System.out.println("owner=" + owner.getName());
System.out.println("modifier=" +
    java.lang.reflect.Modifier.toString(field.getModifiers()));
System.out.println("ownerModule=" + owner.getModule().getName());
System.out.println("callerModule=" + caller.getModule().getName());
System.out.println("canRead=" +
    caller.getModule().canRead(owner.getModule()));
System.out.println("packageExported=" +
    owner.getModule().isExported(owner.getPackageName(), caller.getModule()));
System.out.println("packageOpen=" +
    owner.getModule().isOpen(owner.getPackageName(), caller.getModule()));
System.out.println("usableNow=" + field.canAccess(receiver));
~~~

In the snippet, `receiver` must be valid for the kind of field being examined; for a `static Field`, replace it with `null`. `MyInspector` is an illustrative class name where the caller originates; in a real application use the actual class as the inspection point. `Module.getName()` can return `null` for the unnamed module, so output depends on the environment; **do not** present this snippet as a program with fixed stdout.

## 10. Self-check

**Question 1.** `getDeclaredField("secret")` returns the `Field` of a `private` field. Is `Field.get(instance)` guaranteed to succeed?

**Answer:** No. Metadata lookup is different from permission to use the field. Check `canAccess(instance)` and caller/module constraints before operating.

**Question 2.** Class `internal.PackageTool` is package-private but declares `public void run()`. Code outside the package uses `Class.forName` to find the class. Can `new internal.PackageTool().run()` be written in source in another package?

**Answer:** No. The declaring class is not accessible from the outside package. Both the constructor and method can be found by Reflection, but reflective operations still have to pass access checks.

**Question 3.** Why does `method.isAccessible() == false` not necessarily mean the method cannot be invoked?

**Answer:** This deprecated API reports that the suppression flag is off. A `public` method belonging to an accessible declaring type can still be invoked normally with the flag off. Use `canAccess(target)` appropriate to the context.

**Question 4.** Module `lib` declares `exports api;`, and consumer has `requires lib;`. Can a private field of `api.PublicType` be read using `setAccessible(true)` from consumer?

**Answer:** Not by default. `exports` supports public APIs; deep reflection across a module boundary usually requires the package to be `opens` to consumer or an equivalent package-opening configuration.

**Question 5.** If a module only declares `opens api;` without `exports api;`, is consumer automatically allowed to `import api.PublicType`?

**Answer:** No. `opens` primarily serves runtime reflective access; it does not automatically grant the source-level access permission of `exports`.

**Question 6.** Why can `privateLookupIn` throw `IllegalAccessException` even though `Class.forName` already found the class?

**Answer:** `Class.forName` returns metadata/type; `Lookup` carries caller permissions and `privateLookupIn` checks permissions, readability, and package openness per the API.

**Question 7.** In a subclass in another package, is calling `parentReference.protectedMethod()` always valid because the caller is a subclass?

**Answer:** No. For a protected instance member outside the package, the JLS also constrains the type of the receiver expression. `this.protectedMethod()` can be valid while calling on a variable of type `Parent` is not allowed.

**Question 8.** When `Method.invoke` throws `InvocationTargetException`, can we conclude there is a lack of access permission?

**Answer:** No. In most cases this is an exception thrown by the target method and wrapped by Reflection. Inspect `getCause()`; Reflection access errors usually have a different type such as `IllegalAccessException`.

## 11. Standard Java 17 references for cross-checking

- JLS `6.3 (Scope of a Declaration) and `6.6 (Access Control), including `protected` rules across packages: https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html
- JLS `7.7.2 (Exported and Opened Packages): https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.2
- Java SE 17 `Class`: `getMethod`, `getDeclaredMethod`, `getField`, `getDeclaredField`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17 `AccessibleObject`: `canAccess`, `trySetAccessible`, `setAccessible`, and notes on module readability: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html
- Java SE 17 `Field` and `Method`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html and https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html
- Java SE 17 `MethodHandles`, `privateLookupIn`, and `Lookup`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html
- Java SE 17 `java.lang.Module`: `canRead`, `isExported`, `isOpen`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html

**Remember:** *Seeing* a name/`Class`/`Field`/`Method` is an event about **scope, class loading, or metadata lookup**. *Being allowed to use* is the result of **access checks in the exact caller context**, including declaring type, member, receiver, class loader/runtime package, module, and access API. Always check the two questions separately to diagnose accurately and avoid unintentionally widening the application's access permissions.
