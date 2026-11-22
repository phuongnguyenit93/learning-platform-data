# Designing a Selective Package-Based Policy in Java ClassLoader

## 1. Problem to Solve

In a host–plugin system, not every class should follow the same lookup order. **Parent-first** is suitable for JDK types and shared API contracts. Conversely, a plugin sometimes needs its own class or library version so that it is not shadowed by the version on the host's application classpath.

**Selective package-based policy** (*selective package-based class loading*) means classifying the **binary name** of a class before deciding the lookup order:

- `java.lang.String` and platform classes: use the appropriate parent/Bootstrap/Platform mechanism.
- `api.Service`: use the shared API defined by the parent so that both host and plugin see the same type.
- `plugin.impl.Version` and `plugin.impl.ServiceImpl`: prioritize bytecode from the child source.
- Unselected packages: keep normal **parent-first delegation**.

Example:

~~~text
Application ClassLoader (parent)
├── api.Service                  [shared API]
├── plugin.impl.Version          [host version]
└── PolicyDemo
          ^
          | delegate for shared names
          |
Selective URLClassLoader (child)
├── plugin.impl.Version          [plugin version]
└── plugin.impl.ServiceImpl      [plugin implementation]
~~~

The goal is **implementation isolation**, without breaking the consistency of the API contract. A class can have the same binary name yet be defined by two different loaders, making it **two different runtime types**.

## 2. Distinguishing parent-first, child-first, and child-only

The **default parent-first** behavior of `ClassLoader.loadClass(String, boolean)` works in the following sequence:

1. `findLoadedClass(name)`: has this name already been recorded as loaded?
2. Ask the parent loader (or the bootstrap mechanism when the parent is `null`).
3. When the parent cannot find it, call `findClass(name)` on the current loader.
4. If `resolve=true`, call `resolveClass(result)` to link if needed.
5. Return `Class<?>`, or throw `ClassNotFoundException`.

When you only want to read bytes from a new source while staying parent-first, you should override **`findClass`**, without needing to rewrite `loadClass`.

**Child-first with parent fallback** reverses the order of steps 2 and 3 **only for names in the selected package set**. When the child does not have that class, the loader still asks the parent. This is flexible, but it can accidentally pick up an older class version from the host.

**Child-only/fail closed** for a private namespace throws `ClassNotFoundException` when the child does not have that name, instead of asking the parent. This approach provides stricter isolation, but requires the plugin to package every class belonging to the namespace you own.

| Policy | First lookup | When not found | Suitable for |
| --- | --- | --- | --- |
| Parent-first | Parent | Child `findClass` | JDK, shared API, default classes |
| Child-first + fallback | Child `findClass` | Parent-first | Plugin implementations needing their own version while still allowing fallback |
| Child-only | Child `findClass` | Report not found | Namespaces that must remain private and must not use the host version |

There is no single right policy for every project. Choosing a policy is a decision at the **contract and dependency boundary**, not merely because a package name looks familiar.

## 3. Selecting Packages with Exact Prefixes

A simple filter:

~~~java
private static boolean childFirst(String binaryName) {
    return binaryName.startsWith("plugin.impl.");
}
~~~

Keep the **trailing dot** to distinguish package boundaries:

| Binary name | Matches `plugin.impl.`? |
| --- | --- |
| `plugin.impl.Version` | Yes |
| `plugin.impl.ServiceImpl` | Yes |
| `plugin.impl.internal.Helper` | Yes |
| `plugin.impl.Version$Nested` | Yes |
| `plugin.implx.Version` | No |
| `plugin.implementation.Service` | No |
| `api.Service` | No |

If you use `startsWith("plugin.impl")` (missing the trailing dot), you may accidentally match `plugin.implx` as well. If you use `startsWith("plugin.")`, which is too broad, contract classes such as `plugin.api.Contract` could also be selected into child-first loading and cause duplicate API definitions.

For multiple prefixes, you should represent the policy as an **approved package list**, with tests for similar-looking names and nested names. Distinguish between host-owned packages, plugin-owned packages, shared packages, and platform packages. Do not assume all of `javax.*` or `jakarta.*` are JDK classes in every environment: some APIs may come from external dependencies outside the JDK.

**Clear priority:** types used in method signatures or interfaces between the host and the plugin must be consistently defined by the shared loader. Do not let a plugin arbitrarily redefine those APIs.

## 4. When Do You Need to Override loadClass?

Overriding only `findClass` remains **parent-first**. To prioritize the child for certain packages, we must control the lookup order, so we can override:

~~~java
@Override
protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException {
    synchronized (getClassLoadingLock(name)) {
        Class<?> found = findLoadedClass(name);

        if (found == null && childFirst(name)) {
            try {
                found = findClass(name);
            } catch (ClassNotFoundException missingLocally) {
                // Allow fallback to the normal algorithm.
            }
        }

        if (found == null) {
            found = super.loadClass(name, false);
        }
        if (resolve) {
            resolveClass(found);
        }
        return found;
    }
}
~~~

This is **a method inside a subclass**, not a standalone program. Section 5 provides complete runnable code using `URLClassLoader`.

Explanation of the essential parts that must not be omitted:

1. **`getClassLoadingLock(name)`:** holds the appropriate lock throughout the entire class loading process. Prevents two threads from simultaneously attempting to define the same binary name.
2. **`findLoadedClass(name)`:** checks whether the class has already been loaded/recorded by the loader, avoiding redefining the same name.
3. **`childFirst(name)`:** applies the policy only to the selected namespace.
4. **`findClass(name)`:** locates bytecode in the child source. For a `URLClassLoader` subclass, this method already knows how to read the provided directory/JAR URLs.
5. **Catching `ClassNotFoundException` specifically:** allows fallback when the class file does not exist in the child. Do not swallow `ClassFormatError`, `LinkageError`, or `SecurityException` as if they were merely missing files.
6. **`super.loadClass(name, false)`:** performs the default parent-first lookup when the class is not yet found. Passes `false` because this override itself handles `resolveClass` at the end.
7. **`resolveClass(found)` if the `resolve=true` flag is set:** preserves the contract of the two-parameter overload. This flag **does not require initialization**.

The code holds the lock and then calls `super.loadClass`: Java monitor locks are *reentrant*, so the same thread can re-enter the lock. However, for loaders with complex delegation graphs (sibling or circular delegation), you still need to check for deadlocks and *parallel capable* rules.

**Important:** the code above is **child-first with fallback**, not child-only. If the `plugin.impl.*` namespace must strictly never use host classes, do not ignore failures from `findClass`: propagate `ClassNotFoundException` for names belonging to that namespace.

## 5. Complete Java 17+ Example: Same Binary Name, Two Versions

Experiment goal: the parent has `plugin.impl.Version` returning `"parent"`, and the child has `plugin.impl.Version` returning `"child"`. The plugin class `ServiceImpl` implements the shared interface `api.Service` defined by the parent.

### Source Structure

~~~text
example/
└── src/
    ├── parent/
    │   ├── api/
    │   │   └── Service.java
    │   ├── plugin/
    │   │   └── impl/
    │   │       └── Version.java
    │   └── PolicyDemo.java
    └── child/
        └── plugin/
            └── impl/
                ├── Version.java
                └── ServiceImpl.java
~~~

The two `Version.java` files have the same name and package, but belong to two different compilation/output areas. Do **not** compile them into the same directory.

### File `src/parent/api/Service.java`

~~~java
package api;

public interface Service {
    String execute();
}
~~~

### File `src/parent/plugin/impl/Version.java`

~~~java
package plugin.impl;

public class Version {
    public static String who() {
        return "parent";
    }
}
~~~

### File `src/child/plugin/impl/Version.java`

~~~java
package plugin.impl;

public class Version {
    public static String who() {
        return "child";
    }
}
~~~

### File `src/child/plugin/impl/ServiceImpl.java`

~~~java
package plugin.impl;

import api.Service;

public class ServiceImpl implements Service {
    @Override
    public String execute() {
        return Version.who();
    }
}
~~~

### File `src/parent/PolicyDemo.java`

~~~java
import api.Service;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import plugin.impl.Version;

public class PolicyDemo {
    static final class PackagePolicyLoader extends URLClassLoader {
        PackagePolicyLoader(URL[] urls, ClassLoader parent) {
            super(urls, parent);
        }

        private static boolean childFirst(String name) {
            return name.startsWith("plugin.impl.");
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            synchronized (getClassLoadingLock(name)) {
                Class<?> found = findLoadedClass(name);

                if (found == null && childFirst(name)) {
                    try {
                        found = findClass(name);
                    } catch (ClassNotFoundException missingLocally) {
                        // Explicit fallback to normal parent-first lookup.
                    }
                }

                if (found == null) {
                    found = super.loadClass(name, false);
                }
                if (resolve) {
                    resolveClass(found);
                }
                return found;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        URL plugin = Path.of(args[0]).toAbsolutePath().toUri().toURL();

        try (PackagePolicyLoader loader = new PackagePolicyLoader(
                new URL[]{plugin}, PolicyDemo.class.getClassLoader())) {
            System.out.println("parent version: " + Version.who());

            Class<?> childVersion = loader.loadClass("plugin.impl.Version");
            System.out.println("child version: "
                    + childVersion.getMethod("who").invoke(null));
            System.out.println("same runtime class: "
                    + (Version.class == childVersion));
            System.out.println("child owns version: "
                    + (childVersion.getClassLoader() == loader));

            Class<?> implementation =
                    loader.loadClass("plugin.impl.ServiceImpl");
            Service service = (Service) implementation
                    .getDeclaredConstructor().newInstance();

            System.out.println("service: " + service.execute());
            System.out.println("api shared: "
                    + (loader.loadClass("api.Service") == Service.class));
            System.out.println("jdk shared: "
                    + (loader.loadClass("java.lang.String") == String.class));
        }
    }
}
~~~

The host code uses `URLClassLoader` so that you do not have to implement bytecode/JAR reading yourself. Overriding `loadClass` only changes the package selection policy and preserves the rest of the standard API.

### Compile and Run on Linux/macOS

From inside `example`:

~~~bash
mkdir -p out/parent out/child

javac --release 17 -d out/parent \
  src/parent/api/Service.java \
  src/parent/plugin/impl/Version.java \
  src/parent/PolicyDemo.java

javac --release 17 -cp out/parent -d out/child \
  src/child/plugin/impl/Version.java \
  src/child/plugin/impl/ServiceImpl.java

java -cp out/parent PolicyDemo out/child
~~~

**Note:** when running, include only `out/parent` on the application `-cp`. `out/child` is passed as a program argument so that `PolicyDemo` creates the URLClassLoader. If you add the child directory to the host classpath, the host/child class versions can conflict depending on classpath order and break the experiment conditions.

### Compile and Run on Windows PowerShell

In the `example` directory:

~~~powershell
New-Item -ItemType Directory -Force out\parent, out\child | Out-Null
javac --release 17 -d out\parent src\parent\api\Service.java src\parent\plugin\impl\Version.java src\parent\PolicyDemo.java
javac --release 17 -cp out\parent -d out\child src\child\plugin\impl\Version.java src\child\plugin\impl\ServiceImpl.java
java -cp out\parent PolicyDemo out\child
~~~

### Verified Stdout on the JDK

~~~text
parent version: parent
child version: child
same runtime class: false
child owns version: true
service: child
api shared: true
jdk shared: true
~~~

Line-by-line explanation:

1. **parent version: parent:** `PolicyDemo` is defined by the application loader, so accessing `Version.who()` directly in the host gets the parent's Version class.
2. **child version: child:** the child loader prioritizes `findClass` for the `plugin.impl.*` package, so it loads the Version class from `out/child`.
3. **same runtime class: false:** a different binary name + defining loader pair creates two distinct runtime classes.
4. **child owns version: true:** verifies class definition via `getClassLoader() == loader`.
5. **service: child:** `ServiceImpl`, defined by the child, resolves `Version` through its own loader and therefore uses the child version.
6. **api shared: true:** `api.Service` is not in the child-first namespace, so it is provided by the parent, allowing the child implementation to be cast to the host interface.
7. **jdk shared: true:** `java.lang.String` is provided by the platform/JVM loader through delegation and is not redefined by the child.

The code was tested with `javac --release 17` and `java` using the two separate classpaths/outputs; the results match completely.

## 6. Why Do Shared API Packages Need Parent-First?

Suppose the child also packages its own `api.Service` and selects child-first for `api.*`. Although the class files bear the same name, Java can create:

~~~text
api.Service @ ParentLoader   !=   api.Service @ ChildLoader
~~~

Those two classes do not share the same JVM identity. An object of `plugin.impl.ServiceImpl` implementing the child's API version may **fail to cast** to `api.Service` on the host side, causing a `ClassCastException`. When method signatures or field types require type consistency across loaders, the JVM may also enforce *loading constraints* and raise a `LinkageError`.

Therefore, place interfaces and types that appear at the **communication boundary** (parameters, return types, exception contracts, shared DTOs) into the parent/shared loader namespace. Isolate only implementation/private dependencies. If a separately versioned library leaks types through the plugin's public API, a package-based policy may not be enough; consider an adapter/serialization layer or a dedicated contract.

## 7. Fallback Can Mask Version Conflicts

Suppose the child is missing `plugin.impl.Helper` while the parent has an older version. Child-first + fallback code will ask the parent and receive the old class, which can cause a `NoSuchMethodError` when the plugin was compiled against the newer version.

Some options to consider:

- **Allow fallback** when that name can genuinely be shared. Test names that exist in the parent but not in the child.
- **Fail closed** for strictly private namespaces: if child `findClass` does not find it, throw `ClassNotFoundException` without falling back to the parent.
- **Separate namespaces** using different packages or shading/relocation for private dependencies to reduce collision risk.
- **Design a bridge API** in the parent for classes that must cross the boundary.

Do not implement a blanket catch like `catch (Throwable ignored)` followed by fallback: it hides corrupted bytecode errors, security errors, and linkage errors, and can cause the application to silently run with a different version.

## 8. Synchronization, Caching, Linking, and Deadlock

A `loadClass` override carries greater responsibility than simply overriding `findClass`:

| Component | Why does it matter? |
| --- | --- |
| `getClassLoadingLock(name)` | Locks loading by name properly for the loader; prevents multiple threads from concurrently defining the class invalidly. |
| `findLoadedClass(name)` | Avoids repeating `defineClass` for an already-recorded name. |
| `super.loadClass(name, false)` | Allows parent-first to work when the namespace is not child-first or during fallback. |
| `resolveClass(found)` | Preserves the contract when `resolve=true`. |
| Distinguishing exceptions | `ClassNotFoundException` differs from `LinkageError` and initialization errors. |

`loadClass(name)` is equivalent to `loadClass(name,false)`; `resolveClass` performs linking if needed and **does not** invoke the static initializer. Java has the concept of a *parallel capable class loader* and appropriate registration to support separate per-name locks. Do not assume every subclass with a complex policy is parallel capable; check the specification as well as the inheritance/registration configuration.

With a non-hierarchical delegation graph or calls across multiple loaders, deadlocks can occur if threads acquire locks in different orders. The example only has one parent and one child, creating no delegation cycles.

Closing a `URLClassLoader` with *try-with-resources* releases I/O resources; it does **not** immediately unload defined classes or destroy all objects currently in use. Do not use `close()` as a way to replace classes of the same name within an existing loader.

## 9. Resource Policy Does Not Automatically Follow Class Policy

Overriding `loadClass` only changes the **class lookup** order. Resources are looked up through different APIs:

~~~java
URL url = loader.getResource("plugin/impl/config.properties");
InputStream stream =
        loader.getResourceAsStream("plugin/impl/config.properties");
~~~

This is illustrative code, assuming a loader is already available. `URLClassLoader.getResource` normally has its own parent-first policy, so you can end up with a class loaded from the child plugin while a resource of the same name comes from the parent. If the resource contains configuration tailored specifically to that version of the class, resolving from different sources causes hard-to-detect bugs.

You may need to define a separate policy for `getResource`/`getResources`/`findResource`, or rename/relocate resource paths to avoid collisions. `META-INF/services/...` and `ServiceLoader` must also be checked: some usages of `ServiceLoader` obtain the loader from the thread context class loader, which differs from the normal JVM bytecode resolution mechanism.

**Similarly**, a package policy does not automatically create a JPMS ModuleLayer or handle exports/opens of named modules. `URLClassLoader` is a tool for finding classes/resources on a URL classpath, not a replacement for the module resolver.

## 10. Practical Risks and How to Handle Them

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| Child still uses the host version | Policy does not match the name, or parent is queried before `findClass`. | Check `childFirst(name)` and `clazz.getClassLoader()`. |
| `ClassCastException` despite identical interface names | Host and child define duplicate API contracts. | Compare `Service.class` with the actual interface class on the plugin side. |
| `NoSuchMethodError` | Fallback to the wrong dependency version. | Inspect the source class and dependency graph. |
| `LinkageError: duplicate class definition` | Cache/lock omitted; redefining the same binary name. | Use `findLoadedClass` and proper locking. |
| `ClassFormatError` or `VerifyError` | Corrupted or incompatible source bytecode. | Read the cause; do not swallow it into `ClassNotFoundException`. |
| Deadlock when loading across multiple loaders | Delegation cycle or overlapping locks. | Review the delegation graph, locking, and parallel capability. |
| Loader constraint violation error | Two loaders share signatures using the same binary name but different runtime classes. | Move communication types to the shared loader. |
| Wrong version of config | Class is child-first, while resource is still parent-first. | Check the corresponding resource policy. |
| Similar-looking package matched by mistake | Prefix is missing the trailing `.`. | Test `plugin.implx.*` and subpackages. |
| Plugin runs without security isolation | A class loader is not a sandbox. | Build a separate security policy or process isolation. |

For untrusted plugins, do not treat a class loader as a security boundary for the filesystem, network, CPU, or OS permissions. It is primarily a mechanism for namespaces, delegation, and class lifecycle.

## 11. Checklist and Self-Check Questions

Before deploying a policy to production:

1. Clearly identify **shared APIs**, **private implementations**, **private dependencies**, and **platform classes**.
2. Use binary names and check package prefix boundaries: `"plugin.impl."`, not `"plugin.impl"`.
3. Only override `loadClass` when you genuinely need to change the **delegation order**; if keeping parent-first, prefer overriding `findClass`.
4. In the override, hold the `getClassLoadingLock` lock, cache with `findLoadedClass`, fall back according to the intended decision, and handle `resolveClass`.
5. Carefully decide between **child-first + fallback** or **child-only** for each namespace; test names that are missing in the child but present in the parent.
6. Verify the same binary name across two loaders: the `Class<?>` objects must be different when isolation is expected.
7. Verify the shared API: `loader.loadClass("api.Service") == Service.class` and casting through the contract succeeds.
8. Test differently versioned libraries, method signatures, exceptions, DTOs, and resource names.
9. Test repeated loading and multi-threaded loading, especially with custom graphs or multiple loaders.
10. Verify resources/providers, the URLClassLoader lifecycle, and plugin security boundaries.

**Question 1.** Why is the prefix `plugin.impl.` better than `plugin.impl`?

**Answer:** It matches exact package boundaries, avoiding similar-looking names such as `plugin.implx.Version`.

**Question 2.** The child has a `plugin.impl.Version` class and the parent also has one with the same name. Which one will child-first load?

**Answer:** The child version if the child's `findClass` succeeds, even though the parent also has it. If the child does not have it, the result depends on whether the policy uses fallback or fails closed.

**Question 3.** Why does `api.Service` reside in the parent and need to preserve the same identity?

**Answer:** The host and plugin must share a single runtime contract; two interfaces with the same binary name but different defining loaders may fail to cast or link.

**Question 4.** Once `loadClass` is overridden to be child-first, does `getResource` automatically become child-first too?

**Answer:** No. Resource lookup has an independent API and policy; it must be handled or tested separately.

**Question 5.** Does the `resolve=true` flag execute `static { ... }`?

**Answer:** No. It requests linking when needed; initialization is triggered by active use or an API with an explicit initialization contract.

## Official Documentation

- [Java SE 21 – ClassLoader.loadClass and getClassLoadingLock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html).
- [Java SE 21 – URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html).
- [JVMS Java SE 21 §5.3 – Loading](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3).
- [JVMS Java SE 21 §5.4 – Linking](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4).
