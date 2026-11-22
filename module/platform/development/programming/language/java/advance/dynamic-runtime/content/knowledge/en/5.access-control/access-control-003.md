# 5.3 Comparing `exports`, `opens`, Named Modules, and Unnamed Modules

The Java module system (*Java Platform Module System* – JPMS, since Java 9) controls **which module can read which module** and **which packages of a module are allowed to be used from outside**. For dynamic programs, reflection, and frameworks such as dependency injection, serialization, or ORM, distinguishing between `exports` and `opens` is essential to understanding why a `public` class can still be denied access.

This lesson focuses on access permissions between **different modules** on **Java 17+**: how `exports` supports public APIs, how `opens` supports deep reflection, the differences between a *named module* and an *unnamed module* (class path), how to inspect them using `java.lang.Module`, and how to diagnose errors.

## 1. Three Factors to Consider Separately

A call from module A to a type located in module B has multiple layers of control:

1. **Readability (read relationship):** Can A read B? For explicit modules, `requires B;` in `module-info.java` usually creates this relationship. `Module.canRead(other)` checks this relationship at runtime.
2. **Package boundary:** Does B **export** the package so A can reference public types using normal Java code, or **open** the package so A can access it via reflection?
3. **Java access modifiers at the class/member level:** `public`, `protected`, package-private, and `private` still matter. `exports` does not automatically make a `private` field public; `opens` allows appropriate reflection APIs to *request bypassing* access checks via `setAccessible(true)` or `trySetAccessible()`.

For example, if you have `module shop.app { requires shop.core; }` and `shop.core` does **not** `exports shop.core.api;`, then `shop.app` still cannot write `import shop.core.api.Product;`, even though `Product` is declared `public`. Being able to read a module **does not mean** being able to access every package in that module.

Conversely, `exports` **does not create a readability relationship**. To statically reference across named modules, both a readability relationship and export permission to the calling module are normally required. For core reflection, Java has its own rule: access checking on reflection objects assumes the caller already reads the module containing the member; this **does not replace** the readability rules of normal Java code.

## 2. Comparison Table of `exports` and `opens`

Assume `p` is in named module B, the calling code is in a **named module A different from B**, and A reads B when static API usage is needed:

| Declaration in B | Can A `import` and call `public` APIs in `p` at compile time? | Can A use reflection on `public` members of `public` types? | Can A enable `setAccessible(true)` for `private` members of `p`? |
| --- | --- | --- | --- |
| `exports p;` | Yes | Yes | No, unless other open permissions exist |
| `opens p;` | No | Yes, at runtime | Yes, according to reflection rules |
| `exports p;` and `opens p;` | Yes | Yes | Yes |
| Neither declared | No | Cannot access members from another module through normal means | No |

**Understanding the table correctly:** `exports` grants permission for developers to **use public APIs with normal Java code**. `opens` grants permission for **runtime tools to inspect and perform deep access via reflection** without forcing the package to become a compile-time API. Special rules for code within **module B itself** (which has its own internal access) are not shown in the table.

`opens` is not a command to “turn off” all JVM controls: the right API, the right opened module, and the right reflection target are still required; other security checks and restrictions on writing to certain `final` fields still apply.

## 3. `exports`: Publishing a Public API

Example `module-info.java` of a library:

~~~java
module shop.core {
    exports shop.core.api;
}
~~~

Modules that **read** `shop.core` can reference `public` types in `shop.core.api` and members with appropriate access permissions. Package-private types, `private` fields, and other internal packages **are not automatically exposed**.

`exports` is suitable for APIs that you actively commit to letting other modules call: service interfaces, public models, or facade classes. Keep internal implementation packages unexported if callers do not need to `import` them.

To restrict which targets are allowed to use the API, use a **qualified export**:

~~~java
module shop.core {
    exports shop.core.spi to shop.app;
}
~~~

Only the named module `shop.app` is exported the `shop.core.spi` package by this declaration. The name after `to` is a **module name**, not a package name or class name. Qualified exports still require an appropriate readability relationship for static imports. An unnamed module cannot be named directly in `to` inside `module-info.java`.

## 4. `opens`: Opening a Package for Deep Reflection

Example of a library allowing a framework to analyze internal objects:

~~~java
module shop.core {
    exports shop.core.api;
    opens shop.core.entity;
}
~~~

- `shop.core.api` is an API used directly from Java code.
- `shop.core.entity` does **not** become a package that can be imported from another module at compile time.
- At runtime, code in another module can locate classes in `shop.core.entity` via reflection and, if API conditions are met, enable access to non-`public` constructors, fields, or methods.

The difference between *seeing metadata* and *actually accessing a member* is very important. `Class.forName(...)`, `getDeclaredFields()`, or `getDeclaredConstructor()` can retrieve metadata without using the member yet. Errors usually occur at `setAccessible(true)`, `newInstance()`, `Field.get(...)`, or `Method.invoke(...)` when the actual access check happens.

The two APIs handle failure differently:

- `field.trySetAccessible()` returns `false` if access cannot be enabled (in the common case where the package is not open to the reflecting module).
- `field.setAccessible(true)` can throw `java.lang.reflect.InaccessibleObjectException` if access cannot be enabled.

To open only to a designated framework, use **qualified opens**:

~~~java
module shop.core {
    exports shop.core.api;
    opens shop.core.entity to shop.app;
}
~~~

At this point, only reflection code in the named module `shop.app` receives the open permission from that directive; **not** every module. With real-world frameworks, you need to identify the **module containing the code that performs reflection**, which is sometimes different from the module containing the application or model.

A package can be both `exports` and `opens`. If many packages need to be opened, the syntax `open module shop.core { ... }` opens **all** packages of the module for reflection; you still must declare `exports` for APIs needed at compile time. Inside an `open module`, do not add an `opens package;` directive because it is invalid. There is no `opens shop.core.*;` syntax to open packages using a wildcard.

## 5. Named Module, Unnamed Module, and Automatic Module

| Type | How is it formed? | `Module.isNamed()` | Reading other modules | Exporting/opening packages |
| --- | --- | --- | --- | --- |
| **Explicit named module** | Has `module-info.java`, placed on the module path | `true` | According to `requires`/module graph rules | According to `exports`, `opens`, and additional open permissions |
| **Unnamed module** | Classes/JARs on the class path; each class loader has its own unnamed module | `false` | Reads every module **that has been added to the module graph** | Exports and opens all of its packages |
| **Automatic module** | JAR without an explicit module descriptor, placed on the module path | `true` | Compatibility rules apply: reads resolved modules and unnamed modules | At runtime, exports and opens its own packages |

**Do not confuse the class path with the module path:** The same JAR without `module-info.class` can belong to an **unnamed module** when placed on the class path, or become an **automatic named module** when placed on the module path. A modular JAR with a descriptor placed on the module path can be an explicit named module. This is why access permissions and reflection errors can change when switching how the application is run.

For an unnamed module:

- `SomeClasspathClass.class.getModule().isNamed()` is `false`; `getName()` and `getDescriptor()` return `null`.
- Its packages are **exported and open** by default. Therefore, deep reflection into class path classes themselves usually does not hit cross-module `opens` barriers, though other Java rules still apply.
- It reads named modules **that have been resolved** in the module graph, but having a JAR on the module path **does not automatically guarantee** that the module is resolved for an application run solely from the class path. Depending on how it is launched, `--add-modules` may be required.
- A named module **cannot declare `requires` on an unnamed module** (because an unnamed module has no name). When migrating gradually to JPMS, dependencies must be actively organized; `--add-reads some.named.module=ALL-UNNAMED` can be used for appropriate compatibility scenarios.

**An automatic module is still a named module**: it has a module name and can be `requires`-ed by another named module. Do not equate “no `module-info.java` in the JAR” with “unnamed” if the JAR is on the module path.

## 6. Checking Actual Permissions with `java.lang.Module`

Core APIs on Java 17:

| API | What it checks |
| --- | --- |
| `SomeClass.class.getModule()` | Module containing the class |
| `module.isNamed()` / `module.getName()` | Whether it has a module name / the module name (`null` for unnamed) |
| `module.getDescriptor()` | Descriptor when present (`null` for unnamed) |
| `caller.canRead(target)` | Whether the runtime caller module reads target |
| `target.isExported("p")` | Whether `p` is considered unconditionally exported **at runtime** |
| `target.isExported("p", caller)` | Whether `p` is considered exported to caller **at runtime** |
| `target.isOpen("p")` | Whether `p` is unconditionally open at runtime |
| `target.isOpen("p", caller)` | Whether `p` is open to caller at runtime |
| `target.getDescriptor().exports()` | Export directives **declared in the descriptor** |
| `target.getDescriptor().opens()` | Opens directives **declared in the descriptor** |

**Important subtlety:** In Java 17, **a package that is `opens` to a module is also considered exported at runtime by `Module.isExported(package, thatModule)`**; similarly, an unconditionally `opens` package can cause `isExported(package)` to return `true`. This does **not** mean the package has an `exports` directive for the caller to `import` at compile time.

Therefore, when analyzing configuration:

- To know the **actual static directives declared**, check `module.getDescriptor().exports()` and `opens()` (and also check `ModuleDescriptor.isOpen()` for `open module`).
- To know **current accessibility at runtime**, use `isExported`/`isOpen` with the **actual calling module**.
- To know **readability**, use `caller.canRead(target)` **separately**; `isExported` and `isOpen` do not check the read relationship.
- Avoid passing `target` itself as the `caller` parameter to “test external access”: a module always has access to its **own** packages, so the result does not reflect restrictions placed on other modules.

For an unnamed module, inspect `ClassLoader.getSystemClassLoader().getUnnamedModule()` or `SomeClasspathClass.class.getModule()`. If an application has multiple class loaders, there can be **multiple different unnamed modules**.

## 7. Complete Example: Two Named Modules and Reflection Permissions

Project structure (two modules `demo.lib`, `demo.app`):

~~~text
src/
  demo.lib/
    module-info.java
    demo/api/Message.java
    demo/internal/Secret.java
  demo.app/
    module-info.java
    demo/app/Main.java
~~~

**File `src/demo.lib/module-info.java`**

~~~java
module demo.lib {
    exports demo.api;
    opens demo.internal;
}
~~~

**File `src/demo.lib/demo/api/Message.java`**

~~~java
package demo.api;

public class Message {
    public String text() {
        return "hello";
    }
}
~~~

**File `src/demo.lib/demo/internal/Secret.java`**

~~~java
package demo.internal;

public class Secret {
    private final String code = "deep-ok";

    private Secret() {}
}
~~~

**File `src/demo.app/module-info.java`**

~~~java
module demo.app {
    requires demo.lib;
}
~~~

**File `src/demo.app/demo/app/Main.java`**

~~~java
package demo.app;

import demo.api.Message;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;

public class Main {
    public static void main(String[] args) throws Exception {
        Module lib = Message.class.getModule();
        Module app = Main.class.getModule();

        System.out.println("lib named: " + lib.isNamed());
        System.out.println("lib name: " + lib.getName());
        System.out.println("app reads lib: " + app.canRead(lib));
        System.out.println("api declared exported: "
                + lib.getDescriptor().exports().stream()
                    .anyMatch(e -> e.source().equals("demo.api")));
        System.out.println("internal declared exported: "
                + lib.getDescriptor().exports().stream()
                    .anyMatch(e -> e.source().equals("demo.internal")));
        System.out.println("api runtime exported to app: "
                + lib.isExported("demo.api", app));
        System.out.println("api open to app: "
                + lib.isOpen("demo.api", app));
        System.out.println("internal runtime exported to app: "
                + lib.isExported("demo.internal", app));
        System.out.println("internal open to app: "
                + lib.isOpen("demo.internal", app));
        System.out.println("public call: " + new Message().text());

        Class<?> secretType = Class.forName("demo.internal.Secret");
        Constructor<?> constructor = secretType.getDeclaredConstructor();
        System.out.println("private ctor accessible: "
                + constructor.trySetAccessible());
        Object secret = constructor.newInstance();

        Field field = secretType.getDeclaredField("code");
        System.out.println("private field accessible: "
                + field.trySetAccessible());
        System.out.println("secret value: " + field.get(secret));
    }
}
~~~

From the directory containing `src/`, run with **JDK 17 or later**:

~~~bash
javac --release 17 -d out --module-source-path src -m demo.lib,demo.app
java --module-path out -m demo.app/demo.app.Main
~~~

Exact stdout:

~~~text
lib named: true
lib name: demo.lib
app reads lib: true
api declared exported: true
internal declared exported: false
api runtime exported to app: true
api open to app: false
internal runtime exported to app: true
internal open to app: true
public call: hello
private ctor accessible: true
private field accessible: true
secret value: deep-ok
~~~

**Key takeaways:**

1. `Main` can call `new Message().text()` because `demo.app` `requires demo.lib` and `demo.lib` `exports demo.api`.
2. The descriptor does **not** have `exports demo.internal`, so `internal declared exported: false`. However, `demo.internal` is `opens`, so `isExported("demo.internal", app)` returns `true` **by runtime semantics**. This does not indicate that you can `import demo.internal.Secret` at compile time.
3. Both the constructor and field of `Secret` are `private`; `trySetAccessible()` returns `true` because the `demo.internal` package is open to `demo.app`. If you remove `opens demo.internal;` and recompile, the call attempting to enable access will return `false`; the current program will then encounter an access error when instantiating `Secret` via the private constructor.
4. `getDescriptor().exports()` and `Module.isExported(...)` answer **two different questions**: *declared exports* and *effective export permissions at runtime*.

## 8. Complete Example: An Application on the Class Path Is an Unnamed Module

Create a separate file `classpath/demo/cli/ClasspathMain.java` (without `module-info.java`):

~~~java
package demo.cli;

public class ClasspathMain {
    public static void main(String[] args) {
        Module module = ClasspathMain.class.getModule();

        System.out.println("classpath named: " + module.isNamed());
        System.out.println("classpath name: " + module.getName());
        System.out.println("classpath descriptor: " + module.getDescriptor());
        System.out.println("classpath package exported: "
                + module.isExported("demo.cli"));
        System.out.println("classpath package open: "
                + module.isOpen("demo.cli"));
    }
}
~~~

Run commands at the same root directory:

~~~bash
javac --release 17 -d cpout classpath/demo/cli/ClasspathMain.java
java -cp cpout demo.cli.ClasspathMain
~~~

Exact stdout:

~~~text
classpath named: false
classpath name: null
classpath descriptor: null
classpath package exported: true
classpath package open: true
~~~

This class is loaded from the class path, so it resides in the class loader's unnamed module. There is no explicit module descriptor, yet the packages of the unnamed module are still exported and open.

## 9. Temporary Workarounds with Launch Arguments

If you cannot modify the library's `module-info.java` immediately, Java supports adding permissions at build/run time. For example, with the two modules in section 7:

| Need | Argument | Scope |
| --- | --- | --- |
| Allow `demo.app` to use `public` APIs in an unexported package | `--add-exports demo.lib/demo.internal=demo.app` | May be needed at **compile time and runtime**, depending on the referencing code |
| Allow `demo.app` deep reflection into `demo.internal` | `--add-opens demo.lib/demo.internal=demo.app` | **Runtime**; does not turn the package into an importable compile-time API |
| Allow code from any unnamed module (class path) deep reflection into a package | `--add-opens demo.lib/demo.internal=ALL-UNNAMED` | Runtime, broader scope than a specific target module |
| Add permission for a named module to read unnamed modules | `--add-reads demo.app=ALL-UNNAMED` | Adds readability, does not automatically open packages |

You can try **removing** `opens demo.internal;` in `src/demo.lib/module-info.java`, recompiling, and then running with the open flag at runtime:

~~~bash
javac --release 17 -d out --module-source-path src -m demo.lib,demo.app
java --add-opens demo.lib/demo.internal=demo.app --module-path out -m demo.app/demo.app.Main
~~~

Now the deep reflection part still works because the JVM is instructed to specifically open that package. Without the flag, `trySetAccessible()` on the private constructor returns `false`. If replaced with `setAccessible(true)`, a denied permission case will typically throw `InaccessibleObjectException`.

**Notes on scope and timing:**

- `--add-exports` resolves public access, **not** replacing `--add-opens` when reading `private` fields is needed.
- `--add-opens` is a **runtime** option; it does not grant import permission when `javac` checks Java code.
- `ALL-UNNAMED` is a special target for **command-line options**, not a module name that can be written in `exports ... to` or `opens ... to`.
- For a class path application that needs to find a named module you provide on the module path, you may need to add `--add-modules demo.lib` so that module participates in the module graph; `opens` or `exports` permissions only take effect when the corresponding module has been resolved.
- On Java 17, do not rely on `--illegal-access` as a long-term solution: that legacy compatibility option has become obsolete and no longer opens closed JDK packages en masse. Declare `opens` in the right place or use narrowly scoped `--add-opens` when needed.

## 10. Choosing the Right Design

**Libraries with stable APIs:** place public contract classes in an `api` package and use `exports`. Keep implementations in separate packages and avoid exporting them if callers do not need static code references.

**ORM / serializer / dependency-injection frameworks:** domain objects can reside in an unexported package that is opened **conditionally** to the module containing the reflection code, for example `opens app.model to framework.module;`. Check the **actual module name** of the framework, rather than guessing from the library/JAR name. If the framework is running on the class path, consider `ALL-UNNAMED` compatibility permissions at runtime when necessary.

**Class loading diagnostic tools:** log all of `type.getModule().getName()`, `isNamed()`, `getClassLoader()`, `canRead` relationships, and `isExported`/`isOpen` states. When the cause is unclear, compare `module-info.java`/descriptor against the actual runtime permissions (which may be augmented by JVM options).

**Migrating class path → module path:** inventory dependencies first. A JAR converted to an explicit named module may lose default access to internal packages without `exports`/`opens`; at the same time, the application's named module cannot directly `requires` classes that are in an unnamed module. Move stable contracts into exported packages and clearly identify parts that require reflection.

## 11. Common Misconceptions

| Misconception | What to remember |
| --- | --- |
| “If a class is `public`, other modules can always import it.” | The package also needs to be `exports`-ed to the caller, and the caller needs to read the module containing the type. |
| “`requires` grants access to every package of another module.” | `requires` handles readability; `exports`/`opens` handle package boundaries. |
| “`exports` is enough to read `private` fields with `setAccessible`.” | Normally, the package needs to be `opens` to the reflecting module. |
| “`opens` means the package can be `import`-ed.” | `opens` grants runtime access via reflection; it does not provide static reference permission at compile time. |
| “`Module.isExported(p) == true` proves `module-info.java` has `exports p;`.” | An open package is also treated as exported **at runtime**. Check `getDescriptor().exports()` if you need the declared directives. |
| “`Class.forName` succeeding means all methods/fields are accessible.” | Loading a class/retrieving metadata and accessing members are separate checking steps. |
| “An unnamed module is an automatically named module.” | Unnamed has **no name**; an automatic module is a **named module**. |
| “Every JAR without `module-info` runs in an unnamed module.” | A JAR on the **module path** can be an automatic named module. |
| “`--add-opens` is a way to grant compile-time permissions.” | `--add-opens` is for runtime reflection; static APIs need appropriate exports. |
| “Having a JAR on the module path means class path code can read it immediately.” | For self-provided named modules, `--add-modules` may be needed so the module is resolved first. |
| “You can write `to ALL-UNNAMED` in `module-info.java`.” | `ALL-UNNAMED` is only a special target for JVM options. |

## 12. Self-Check

1. A package only has `exports p;`, in which a `public` class has a `private` field. Can another module import that class? Can it enable `trySetAccessible()` for the private field?
2. A package only has `opens p;`. Why can `isExported("p", otherModule)` be `true` even though `getDescriptor().exports()` does not contain `p`?
3. A program moves a JAR from the class path to the module path, after which reflection on a private field is denied. Identify **which module performs the reflection**, then choose between `opens p to module.name;` and `--add-opens source.module/p=target.module`.
4. Why does placing a JAR on the module path without `--add-modules` not necessarily make it available to an application running from the class path?

**References (Java 17 / JPMS):**

- [`java.lang.Module` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html)
- [`java.lang.reflect.AccessibleObject` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [Open packages for reflection (dev.java)](https://dev.java/learn/modules/opening-for-reflection/)
- [Qualified exports and opens (dev.java)](https://dev.java/learn/organizing/modules/qualified-exports-opens/)
- [The unnamed module (dev.java)](https://dev.java/learn/organizing/modules/unnamed-module/)
- [`--add-exports` and `--add-opens` (dev.java)](https://dev.java/learn/organizing/modules/add-exports-opens/).