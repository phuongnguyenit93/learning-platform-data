# Risks of Duplicate Loading of APIs, Annotations, or Exception Types in Java ClassLoaders

## 1. Core Concept: The Same Name Is Not Enough to Be the Same Type

In the JVM, the runtime identity of a regular class/interface is based on the **pair (binary name, defining class loader)**. Therefore, if two loaders actually define a class with the same name `shared.Api` themselves from the same bytecode, the JVM can still treat them as **two distinct types**.

~~~text
HostLoader    defines shared.Api -> Class A
PluginLoader  defines shared.Api -> Class B

A.getName().equals(B.getName()) = true
A == B                          = false
~~~

This risk arises when the host and the plugin package copies of the same API JAR, or when a container uses an isolated class loader with an overly broad child-first policy. Three groups are most susceptible:

- **Interface/API:** Although the plugin declares `implements shared.Api`, it implements the plugin loader's copy of the API, not the one the host uses. Casting or `isAssignableFrom` can fail.
- **Annotation:** A class is annotated with the plugin's `shared.Marker`, while the host checks using the host's `Marker.class`. `isAnnotationPresent` can return false even though the annotation name is identical.
- **Exception:** The plugin throws `shared.Problem` from the plugin's namespace; the host's `catch (shared.Problem e)` uses a different runtime Class and therefore fails to catch that type.

Other consequences include `ClassCastException`, `ServiceConfigurationError` (provider not a subtype), `LinkageError` due to loading constraints, duplicated static state, callback/DTO errors, and unrecognized framework metadata.

**Do not conclude that two types are different merely because there are two ClassLoader objects.** If both loaders delegate the lookup of `shared.Api` to the same parent and the parent defines it, they can receive **the exact same runtime Class**. What you need to inspect is the **defining loader** of the resulting Class.

## 2. How Does a Duplicated API/Interface Cause Errors?

The host has an interface:

~~~java
package shared;

public interface Api {
    String message();
}
~~~

Plugin:

~~~java
package plugin;

import shared.Api;

public final class PluginImpl implements Api {
    @Override
    public String message() {
        return "hello";
    }
}
~~~

These are two illustrative snippets; the hands-on exercise in a later section provides the complete Java files.

Two models:

~~~text
CORRECT: shared API
HostLoader -- defines shared.Api
      ^
      | delegation shared.*
PluginLoader -- defines plugin.PluginImpl
      implements shared.Api (from parent)

WRONG: duplicate API loading
HostLoader -- defines shared.Api [H]
PluginLoader -- defines shared.Api [P]
PluginLoader -- defines plugin.PluginImpl
      implements shared.Api [P] != [H]
~~~

In the wrong model, an object created from `plugin.PluginImpl` is not necessarily castable to the `shared.Api` that the host resolved. `Api.class.getName().equals(pluginApi.getName())` is still true, but `Api.class == pluginApi` is false.

A message such as "`shared.Api cannot be cast to shared.Api`" is not a contradiction; it is referring to two types with the same binary name defined by two different defining loaders.

## 3. Duplicated Annotations Cause Reflection or Frameworks to Miss Them

An annotation is also a Java runtime type. For example:

~~~java
package shared;

import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
public @interface Marker {}
~~~

If the plugin applies `@Marker` but that annotation Class itself is defined by the plugin loader, the host calling:

~~~java
boolean found = pluginType.isAnnotationPresent(Marker.class);
~~~

with `Marker.class` from the host will not automatically match the plugin's copy of Marker. `found` can be false even when `pluginType.getDeclaredAnnotations()` shows an annotation named `shared.Marker`.

It is necessary to distinguish **three different errors**:

1. Failing to declare `RetentionPolicy.RUNTIME`: the annotation may not appear in Java runtime reflection.
2. The runtime annotation exists, but **Class identity does not match**: the host uses a Class from another loader.
3. The framework scans the wrong scope, a module package is not `opens` when deep reflection is needed, or a proxy different from the actual class is being scanned.

Annotation failures can cause the host to skip controllers/routes, validators, transaction markers, dependency injection components, or authorization metadata. For annotations carrying policy semantics, the consequence is not merely a check returning false.

**Proper policy:** annotations that the host/framework needs to read from plugins must be defined in the **shared contract loader**. Do not work around the issue by comparing annotation name strings and accepting any type with the same name.

## 4. Duplicated Exceptions Cause Catch Blocks to Miss

If both the host and the plugin define `shared.Problem extends Exception` under two different loaders, they are still two independent exception types. A typed handler such as:

~~~java
try {
    pluginCall();
} catch (Problem e) {
    handle(e);
}
~~~

is an **illustrative snippet** with suitably declared variables, methods, and `Problem` type. It relies on runtime type compatibility, not on `getClass().getName()`. An object created by `PluginProblem` can escape `catch (HostProblem)` even though the binary name is the same.

When the host invokes a plugin via reflection, remember that Java reflection **wraps exceptions thrown by the method**:

~~~java
try {
    method.invoke(null);
} catch (java.lang.reflect.InvocationTargetException wrapper) {
    Throwable cause = wrapper.getCause();
    // Inspect the defining loader and Class of cause rather than wrapper.
}
~~~

This is **illustrative code**, not a program with `main`. `wrapper` is `InvocationTargetException`, while `cause` may be the `shared.Problem` copy defined by the plugin loader.

Solution: place exception types in the host-plugin contract in the shared parent loader; or use an adapter to convert plugin-private exceptions into a **shared exception type** or an error DTO before returning across the boundary. Do not catch all `Throwable` and wipe out the entire root cause.

## 5. Type Identity Rules and Useful Inspection APIs

| Check | Question Answered |
| --- | --- |
| `a.getName().equals(b.getName())` | Are the binary names the same? |
| `a == b` for `Class<?>` | Are they the same runtime Class? |
| `a.getClassLoader()` | Who is the defining loader of `a`? |
| `a.isAssignableFrom(b)` | Can an object of type `b` be assigned to `a` according to type rules? |
| `a.isInstance(object)` | Is the object compatible with `a`? |
| `annotation.annotationType()` | Which exact runtime annotation Class does the annotation instance belong to? |
| `cause instanceof HostProblem` | Is the exception actually compatible with the host type? |
| `clazz.getModule()` | What is the runtime module of the class (Java 9+)? |

Do not just compare `toString()` of a Class or loader, because descriptive strings are not a standard type-identity check mechanism. When printing the loader of core classes like `java.lang.String`, `getClassLoader()` can be `null`, representing the bootstrap loader.

## 6. Why Do Duplicate Contracts Slip Past Loader Policy?
With `shared.Api`, `shared.Marker`, and `shared.Problem`, the same design mistake is letting the child redefine the **host's contract**. Parent-first only helps when the parent actually has those classes; selective child-first must exclude contract packages.

| Group | Required Check |
| --- | --- |
| Service/API | `HostApi.class.isAssignableFrom(pluginImpl)` |
| Annotation read by host | `impl.isAnnotationPresent(HostMarker.class)` and `RUNTIME` retention |
| Exception caught by host | Root cause's Class is assignable to `HostProblem.class` |
| Implementation/private dependency | Class source and defining loader match the expected plugin |

The checks above answer **different questions**; you cannot check `getName()` once and assume the entire contract is valid. The following hands-on exercise intentionally duplicates all three kinds to observe each failure.

## 7. Java 17+ Experiment: Duplicate Loading and Then Fixing the Same Plugin

The following example intentionally compiles `shared.*` into **both `host-classes` and `plugin-classes`**. The host will run two configurations:

- `isolated`: child-first for `plugin.*` and `shared.*`, duplicating the interface, annotation, and exception.
- `shared`: child-first only for `plugin.*`, while `shared.*` delegates to the parent, unifying the contract.

### 7.1. File Structure

~~~text
duplicate-types-demo/
├── src-shared/
│   └── shared/
│       ├── Api.java
│       ├── Marker.java
│       └── Problem.java
├── src-plugin/
│   └── plugin/
│       └── PluginImpl.java
└── src-host/
    └── HostMain.java
~~~

### 7.2. src-shared/shared/Api.java

~~~java
package shared;

public interface Api {
    String message();
}
~~~

### 7.3. src-shared/shared/Marker.java

~~~java
package shared;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Marker {
}
~~~

`@Retention(RUNTIME)` ensures the annotation can be observed via reflection. `@Target(TYPE)` specifies that it is used on class/interface declarations.

### 7.4. src-shared/shared/Problem.java

~~~java
package shared;

public class Problem extends Exception {
    public Problem(String message) {
        super(message);
    }
}
~~~

### 7.5. src-plugin/plugin/PluginImpl.java

~~~java
package plugin;

import shared.Api;
import shared.Marker;
import shared.Problem;

@Marker
public final class PluginImpl implements Api {
    @Override
    public String message() {
        return "hello";
    }

    public static void fail() throws Problem {
        throw new Problem("plugin problem");
    }
}
~~~

The plugin implementation implements the API, has a runtime annotation, and has a method that throws a checked exception.

### 7.6. src-host/HostMain.java

~~~java
import java.io.IOException;
import java.lang.annotation.Annotation;
import java.lang.reflect.InvocationTargetException;
import java.nio.file.Files;
import java.nio.file.Path;

import shared.Api;
import shared.Marker;
import shared.Problem;

public class HostMain {
    static final class PluginLoader extends ClassLoader {
        private final Path root;
        private final boolean duplicateShared;

        PluginLoader(Path root, boolean duplicateShared) {
            super(HostMain.class.getClassLoader());
            this.root = root;
            this.duplicateShared = duplicateShared;
        }

        private boolean local(String name) {
            return name.startsWith("plugin.")
                    || (duplicateShared && name.startsWith("shared."));
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!local(name)) {
                return super.loadClass(name, resolve);
            }
            synchronized (getClassLoadingLock(name)) {
                Class<?> result = findLoadedClass(name);
                if (result == null) {
                    result = findClass(name);
                }
                if (resolve) {
                    resolveClass(result);
                }
                return result;
            }
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            Path file = root.resolve(
                    name.replace('.', '/') + ".class");
            try {
                byte[] bytes = Files.readAllBytes(file);
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException error) {
                throw new ClassNotFoundException(name, error);
            }
        }
    }

    static void demonstrate(String label, Path root,
                            boolean duplicateShared) throws Exception {
        PluginLoader loader = new PluginLoader(root, duplicateShared);
        Class<?> impl = loader.loadClass("plugin.PluginImpl");
        Object object = impl.getConstructor().newInstance();

        Class<?> pluginApi = loader.loadClass("shared.Api");
        Class<?> pluginMarkerType = loader.loadClass("shared.Marker");
        Class<?> pluginProblem = loader.loadClass("shared.Problem");
        Class<? extends Annotation> pluginMarker =
                pluginMarkerType.asSubclass(Annotation.class);

        System.out.println(label + " API name equal: "
                + Api.class.getName().equals(pluginApi.getName()));
        System.out.println(label + " API same Class: "
                + (Api.class == pluginApi));
        System.out.println(label + " host Api instance: "
                + (object instanceof Api));
        System.out.println(label + " host Marker present: "
                + impl.isAnnotationPresent(Marker.class));
        System.out.println(label + " plugin Marker present: "
                + impl.isAnnotationPresent(pluginMarker));

        try {
            impl.getMethod("fail").invoke(null);
        } catch (InvocationTargetException wrapper) {
            Throwable cause = wrapper.getCause();
            System.out.println(label + " exception same name: "
                    + cause.getClass().getName()
                           .equals(Problem.class.getName()));
            System.out.println(label + " exception same Class: "
                    + (cause.getClass() == Problem.class));
            System.out.println(label + " exception is host Problem: "
                    + (cause instanceof Problem));
            System.out.println(label + " exception is plugin Problem: "
                    + pluginProblem.isInstance(cause));
        }

        try {
            Api api = (Api) object;
            System.out.println(label + " message: " + api.message());
        } catch (ClassCastException wrongApi) {
            System.out.println(label + " cast: ClassCastException");
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: HostMain <plugin-classes-directory>");
        }
        Path root = Path.of(args[0]);
        demonstrate("isolated", root, true);
        demonstrate("shared", root, false);
    }
}
~~~

Because `HostMain` does not directly import or reference `plugin.PluginImpl` at compile time, the parent loader is not automatically provided with the plugin implementation if the classpath only contains `host-classes`.

`PluginLoader` routes `plugin.*` names local-first in both cases; only when `duplicateShared=true` does it route `shared.*` local-first. Other names (such as `java.lang.String`) still go through the parent. Inside the loader, `getClassLoadingLock` and `findLoadedClass` prevent defining the same name twice across multiple calls.

**Demo limitation:** `findClass` reads classfiles from a prepared directory without checking symlinks, file size, an allowlist, or a trusted directory. Use it only to observe type identity in a learning environment; **do not use it as-is as a plugin loader for untrusted code**.

### 7.7. Compile and Run

In the `duplicate-types-demo` directory, using JDK 17+:

~~~bash
javac --release 17 -d host-classes src-shared/shared/Api.java src-shared/shared/Marker.java src-shared/shared/Problem.java src-host/HostMain.java
javac --release 17 -d plugin-classes src-shared/shared/Api.java src-shared/shared/Marker.java src-shared/shared/Problem.java src-plugin/plugin/PluginImpl.java
java -cp host-classes HostMain plugin-classes
~~~

**Expected stdout** when running the exact files and commands:

~~~text
isolated API name equal: true
isolated API same Class: false
isolated host Api instance: false
isolated host Marker present: false
isolated plugin Marker present: true
isolated exception same name: true
isolated exception same Class: false
isolated exception is host Problem: false
isolated exception is plugin Problem: true
isolated cast: ClassCastException
shared API name equal: true
shared API same Class: true
shared host Api instance: true
shared host Marker present: true
shared plugin Marker present: true
shared exception same name: true
shared exception same Class: true
shared exception is host Problem: true
shared exception is plugin Problem: true
shared message: hello
~~~

### 7.8. Why Did Changing Only the Policy Fix It?

In the `isolated` configuration, the plugin loader defines `Api`, `Marker`, and `Problem` itself. The names and bytes may match the host, but the runtime Classes are different. The plugin executes against its own versions; the host's cast and annotation lookup use the host's versions, so they fail.

In the `shared` configuration, the `shared.*` package is delegated to the host loader. The plugin implementation is defined separately, but the shared contract types in its bytecode resolve to the parent's Classes. As a result, casting to the host `Api` succeeds; the host can read the `Marker` annotation; and the `Problem` exception is the exact runtime type the host expects.

Reflection in this example does not bypass type identity. It merely allows the host to inspect the plugin's Class/annotation/exception when the object cannot yet be cast to the host interface.

## 8. Exception Matching and Reflection Wrappers

One thing easily obscured: the plugin method throws `Problem`, but `Method.invoke` throws `InvocationTargetException` to the caller. Therefore, to find out the **actual exception type**, you need to retrieve `getCause()`.

If host code on a direct call path has a typed catch `catch (Problem e)`, the JVM checks type compatibility against the linked **host Problem**. An object of **plugin Problem** from a different defining loader does not automatically become a host Problem just because it has the same name.

In a plugin architecture, it is best to categorize clearly:

- **Contract exception:** part of the shared API and defined by the parent loader.
- **Plugin-private exception:** exists only inside the plugin and should be converted by an adapter into a contract exception or error DTO.
- **Framework wrapper:** `InvocationTargetException`, `ExecutionException`, `CompletionException`, etc.; must be unwrapped according to the corresponding API contract.
- **VM/linkage errors:** do not automatically convert all of them into `ClassNotFoundException` or a domain error, as that loses the root cause.

In logs, print both `exception.getClass()` and `exception.getClass().getClassLoader()` to distinguish two exceptions with the same name.

## 9. How Annotation Scanning and ServiceLoader Are Affected

Frameworks (DI, web routing, ORM, validation, AOP, testing) may look up annotations using `getAnnotation`, `getAnnotationsByType`, or `isAnnotationPresent`. If the annotation type is duplicated, the host scanner may fail to recognize the marker even though the plugin metadata contains an annotation with the same name.

Do not misdiagnose this as "forgot `@Retention(RUNTIME)`" without printing `annotation.annotationType()` and its defining loader.

`ServiceLoader` operates on the **exact service type Class**. A provider implementing the interface copy from the plugin loader may not be a subtype of the service interface used by the host, leading to `ServiceConfigurationError`, for example "provider not a subtype". Changing the Thread Context ClassLoader can affect where providers are searched, **it does not automatically merge two runtime types** that have already been defined.

The fix is for both provider and consumer to reference a single **shared service API Class**; when using named modules, also check `uses`, `provides...with`, and module readability.

## 10. Loading Constraints and Errors That Happen Before Casting

The JVM enforces **loading constraints** to ensure that reference types used across method descriptors, inheritance, and other linkage points have consistent type semantics.

Two Classes with the same name defined by two loaders **can** coexist independently. However, if the JVM requires the same `shared.Dto` type in an override/interface relationship or communication descriptor and the two loaders resolve it to different Classes, a **`LinkageError` due to a loader constraint violation** can occur at the linking/resolution stage, before the application ever reaches a cast.

Distinguish between:

| Error | Symptom |
| --- | --- |
| `ClassCastException` | The object is incompatible with the target Class of the cast |
| `LinkageError` / loading constraint | The JVM cannot guarantee type consistency when linking related classes |
| `ServiceConfigurationError` | The provider is incompatible or the service is misconfigured |
| `InvocationTargetException` | Reflection wrapper around an exception thrown by the invoked method |
| `NoSuchMethodError` / `NoSuchFieldError` | Symbol/version mismatch, not necessarily caused solely by loader duplication |
| `ClassNotFoundException` | The loader cannot find the class by name within its search scope |

Do not say "duplicating an API always causes a LinkageError", nor say "every problem is just a ClassCastException": the error type depends on how the classes are used.

## 11. Distinguishing API Contracts from Private Dependencies

The **shared contract** set typically includes:

- Service interfaces, abstract base types, and shared superinterfaces.
- Parameter/return types appearing in method signatures, and DTOs/records/enums used across the boundary.
- Checked/unchecked exception types that the host handles by Class.
- Annotation types that the host needs to scan.
- Listener/callback types and service provider contracts.

A plugin can have private implementation classes and library versions of its own **that are not exposed at the boundary**. If a private library appears in the public API, the boundary is no longer cleanly separated; an adapter must be built or the contract standardized.

For example, if a plugin uses a different version of a JSON library than the host, pass data via a shared DTO or strings/bytes with a clear schema, rather than returning a parser implementation object from the plugin and casting it to the host's implementation version.

## 12. Packaging and Build Configuration

The root cause of duplication often lies in the artifacts rather than the Java source itself:

- A plugin fat JAR/uber JAR contains a copy of `shared/Api.class` and a child-first loader defines that copy.
- The container already provides the API, yet the plugin still bundles its own copy of the API.
- Maven/Gradle dependency scopes cause the API to be shipped twice at deployment time.
- Shading/relocation changes the package names of a dependency that the host expects to share.
- App server isolation, a test class loader, or hot reload creates a new loader with its own copy of the contract.

In systems where the host provides the contract JAR at runtime, plugins typically compile against the API without packaging a duplicate copy; Maven `provided` or Gradle `compileOnly` **may** be appropriate depending on the build/deploy environment. You must inspect the actual artifacts and runtime class loaders.

You can inspect entries with:

~~~bash
jar --list --file plugin.jar
~~~

When `plugin.jar` exists, look for `shared/Api.class`, `shared/Marker.class`, and `shared/Problem.class`. **Having duplicate files does not prove the Class is defined twice**, because parent-first may still use the parent's copy. To be certain, compare `Class<?>` and the defining loader at runtime.

## 13. Systematic Debugging

A simple helper:

~~~java
static void describe(Class<?> type) {
    System.out.println(type.getName());
    System.out.println(type.getClassLoader());
    System.out.println(type.getModule());
}
~~~

This is an illustrative snippet to place in any class, not a standalone runnable file.

Procedure when seeing "X cannot be cast to X", missing annotations, or an exception handler not running:

1. Obtain the **two specific Classes** being compared, e.g., the host's `Api.class` and `pluginLoader.loadClass("shared.Api")`.
2. Print their names, defining loaders, and modules; compare `Class<?>` using `==`.
3. Inspect the parent chain and parent-first/child-first policy **per package**.
4. Check whether artifacts contain copies of `shared.*` and whether the runtime deployment uses the right loader type.
5. For annotations, verify `RetentionPolicy.RUNTIME`, inspect `annotation.annotationType()` and its loader.
6. For exceptions, unwrap any wrapper, print `cause.getClass()` and its loader, and check `instanceof HostProblem`.
7. For ServiceLoader, check the service Class, the provider Class, and `isAssignableFrom`.
8. For LinkageError, inspect method descriptors, shared types in signatures, versions, and loader constraints.
9. Move the shared contract to a common parent, keep plugin-private implementations in the child, and re-run tests.
10. Test in the actual container/plugin/module layer environment; succeeding in an IDE does not prove the packaged artifact is correct.

You can enable class loading logs in OpenJDK/HotSpot:

~~~bash
java -Xlog:class+load=info -cp host-classes HostMain plugin-classes
~~~

Detailed logs vary by JDK and environment, so there is no fixed transcript. Combine logs with `getClassLoader()`; do not infer the entire identity solely from JAR paths.

## 14. Mistakes to Avoid

| Mistake | How to Understand/Fix |
| --- | --- |
| "Same full name means same Class" | Runtime identity includes the defining loader |
| "Two different loaders definitely load duplicates" | Delegation can return the same parent Class |
| "Identical bytecode means it can be cast" | Identical bytes do not erase loader namespaces |
| "Annotation with the right name will be found by reflection" | Must be the same annotation Class with appropriate retention |
| "Catching the same name will catch all exceptions with that name" | Typed catch checks runtime Class compatibility |
| "Enable child-first for all packages to isolate" | Only isolate plugin implementations/private dependencies |
| "A new TCCL fixes all duplication" | TCCL changes lookup context; it does not merge Classes |
| "ServiceLoader not a subtype is only caused by a bad provider" | It can be caused by a copy of the service interface in the child |
| "LinkageError occurs on every duplicate" | It only occurs when specific constraints/linkage rules are violated |
| "Reflection bypasses type safety" | Reflection still checks receiver/argument/type compatibility; exceptions are wrapped |
| "Moving JARs to the module path fixes it automatically" | JPMS has its own rules; class identity still matters |
| "Just put all dependencies in the parent" | Only contracts need to be shared; private libs need an explicit policy |

## 15. Recommended Test Suite for Plugin Boundaries

1. `hostApiClass.isAssignableFrom(pluginImplClass)` is true when the plugin declares it implements the shared API.
2. The `shared.Marker` annotation can be found by the host via `isAnnotationPresent`.
3. When the plugin throws a shared exception, the host's handler/type check receives the exact Class.
4. A ServiceLoader provider is a subtype of the service interface provided by the host.
5. Method parameter/return DTO classes at the boundary are defined by the common loader.
6. Plugin A and Plugin B can keep different versions of private dependencies without duplicating the API.
7. API/annotation/exception classes are not redundantly defined via child-first.
8. Hot reload creates a new implementation Class while the shared API Class remains stable.
9. Test missing-dependency and loader-constraint cases, not just whether classes can be found.
10. Verify the actual packaged JAR/WAR and the application server's loader policy.
11. When using annotations with named modules, check exports/opens as required by the API scanner.
12. Ensure error logs include both the binary name **and** the defining loader to avoid misdiagnosis.

## 16. Knowledge Self-Check

**Q1.** Are two interfaces with the same `getName()` but different defining loaders equivalent?  
No. The JVM can treat them as two independent runtime types.

**Q2.** What happens if two plugin loaders both delegate `shared.Api` to the parent?  
They can use the same `Class<?>` defined by the parent, without duplicating the API.

**Q3.** Why does the host's `(Api) plugin` fail even though the plugin code has `implements Api`?  
Because `Api` in the plugin may be a copy defined by a different loader.

**Q4.** What can cause an annotation to be invisible to the host?  
Retention is not RUNTIME, the annotation Class comes from a different loader, the wrong class is being scanned, or module access restrictions.

**Q5.** Will a plugin's `Problem` object with the same name automatically be caught by the host's `catch(Problem)`?  
No, if the two runtime Classes are different and lack an appropriate assignable relationship.

**Q6.** When `Method.invoke` throws a plugin exception, where do you find the original exception?  
In `InvocationTargetException.getCause()`.

**Q7.** When ServiceLoader reports "provider not a subtype", what should you check first?  
Whether the provider implements the host's exact service `Class<S>`, with the same defining loader.

**Q8.** Should shared annotations and exceptions be kept local-first with the plugin implementation?  
No, if the host needs to recognize them via a typed contract; delegate these types to the shared parent.

**Q9.** Does a loader constraint violation always occur immediately when a loader defines two classes with the same name?  
No; it depends on the specific linkage relationships between the classes involved.

**Q10.** Does the module path turn two Classes from two different defining loaders into one type?  
No. Module configuration does not erase class identity.

## 17. References

- JVM Specification Java 17 `5.3, runtime class identity and defining loader: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- JVM Specification Java 17 `5.3.4, Loading Constraints: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.4
- Java SE 17, ClassLoader API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17, Class API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17, Annotation API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Annotation.html
- Java SE 17, ServiceLoader API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Java SE 17, InvocationTargetException: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html
- JLS Java 17 `12.2, Loading of Classes and Interfaces: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2
