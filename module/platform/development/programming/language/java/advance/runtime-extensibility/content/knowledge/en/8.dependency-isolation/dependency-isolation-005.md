# Diagnosing ClassCastException Even When Two Classes Have the Same Name

## 1. Symptom: Same Name Yet the JVM Still Refuses to Cast

In a Java application with plugins, two classes can have the exact same fully qualified name, the same source code, and even identical bytecode, yet the JVM still treats them as **two distinct types**. The usual cause is that they were **defined by two different class loaders**.

A typical exception:

```text
java.lang.ClassCastException:
  class com.example.api.Message cannot be cast to class com.example.api.Message
  (com.example.api.Message is in unnamed module of loader 'plugin-loader' @...;
   com.example.api.Message is in unnamed module of loader 'app'...)
```

At first glance, `Message` is being cast to `Message` itself. However, in the JVM, **class identity** is determined by the pair:

```text
(binary name of the class, defining class loader of the class)
```

Therefore:

```text
(com.example.api.Message, HostClassLoader)
    !=
(com.example.api.Message, PluginClassLoader)
```

Having the same class name is not enough for a cast to succeed. This is a common issue when the host and a plugin package copies of the same API library, or when a system creates separate class loaders per plugin, module, deployment, or hot reload.

## 2. How Do Loading a Class and Defining a Class Differ?

A class loader can **receive a request to load a class** via `loadClass(name)`, and then delegate to its parent class loader. The loader that was called is not necessarily the loader that **defines** the class.

- **Initiating loader:** the loader through which the class-loading process is requested or initiated.
- **Defining loader:** the loader that actually invokes the mechanism to define the class from bytecode. `Class.getClassLoader()` reveals the defining loader of that class (for the bootstrap class loader it typically returns `null`).
- **Parent delegation:** `ClassLoader.loadClass` by default checks for already-loaded classes, then asks its parent before attempting `findClass` itself. This is the mechanism that enables the host and plugins to share an API when implemented properly.

Suppose the host has `com.example.api.Plugin` on the main classpath, and the plugin also packages a copy of `com.example.api.Plugin` in its own JAR. If the plugin loader follows child-first rules for the API package, it can define a different `Plugin`. When the host casts the plugin instance to the `com.example.api.Plugin` known to the host, the cast fails, even though the interface names on both sides are completely identical.

**Note:** having the same package name does not establish a type relationship. The JVM still checks class/interface identity, inheritance hierarchy, and linkage rules.

## 3. Cause Model in a Plugin System

```text
                     Host application
                           |
                    AppClassLoader
                           |
             com.example.api.Plugin (A)
                           |
                         cast
                           |
                 Plugin implementation
                           |
                 PluginClassLoader
                           |
             com.example.api.Plugin (B)
```

If `PluginClassLoader` defines `Plugin (B)` itself, an instance implementing B is not necessarily an instance of A. They share the name string `com.example.api.Plugin`, but not the same `Class<?>` object.

Common causes:

1. **API JAR packaged twice:** the same interface exists in both the host and the plugin JAR, and each side is loaded by a separate loader.
2. **Unselective child-first:** the plugin loader prioritizes loading all packages from the plugin, including shared contract packages.
3. **Two dependency versions:** two loaders load libraries with the same class names but different versions; besides `ClassCastException`, this can also produce `NoSuchMethodError`, `AbstractMethodError`, or `LinkageError` depending on the situation.
4. **Hot reload:** a new loader redefines the same class names; surviving objects from the old loader are incompatible with types in the new loader.
5. **Containers or frameworks:** application servers, OSGi, test runners, or module environments have their own loader boundaries.
6. **Serialization/caching:** objects stored in a cache or session from an old deployment/loader are passed through the API of a new loader.

Not every `ClassCastException` is caused by class loaders; there are also cases of straightforwardly casting between two unrelated types. Always check both the class name **and the defining loader**.

## 4. Systematic Diagnosis

### Step 1: Read Both Sides of the Error Accurately

From the stack trace, identify:

- The actual runtime type of the object.
- The target type the code is attempting to cast to.
- The code line performing the cast or the bridge/proxy/framework site causing the cast.
- Module and loader details if provided by the JVM.

For example:

```java
Plugin plugin = (Plugin) instance;
```

If the error occurs here, the two `Plugin` classes may differ in identity despite having the same name. Conversely, if the error is `Foo cannot be cast to Bar`, check the `extends`/`implements` relationship before concluding it is a duplicate class issue.

### Step 2: Log Class Identity and Defining Loader

The following diagnostic snippet works inside a program that has `Object instance` and `Class<?> apiType`:

```java
// Integration snippet, not a standalone program.
Class<?> actual = instance.getClass();

System.out.println("actual = " + actual.getName());
System.out.println("actual loader = " + actual.getClassLoader());
System.out.println("expected = " + apiType.getName());
System.out.println("expected loader = " + apiType.getClassLoader());
System.out.println("same Class object = " + (actual == apiType));
System.out.println("assignable = " + apiType.isAssignableFrom(actual));
System.out.println("instanceof expected = " + apiType.isInstance(instance));
```

Two important points:

- `actual == apiType` only checks whether they are the **exact same class**. For an implementation and an interface with different names, this comparison is naturally `false`; in that case use `isAssignableFrom` or `isInstance`.
- `ClassLoader.toString()` can be customized and is not a unique security identifier. When deeper investigation is needed, also log `System.identityHashCode(loader)` and parent relationships, though hash codes are not globally unique IDs either.

### Step 3: Check the Bytecode Source

For an already-loaded class, you can retrieve its code origin when metadata permits:

```java
// Integration snippet, not a standalone program.
java.security.ProtectionDomain domain = actual.getProtectionDomain();
java.security.CodeSource source = domain == null ? null : domain.getCodeSource();
System.out.println(source == null ? "<unknown>" : source.getLocation());
```

`CodeSource` may be `null`; the returned URL is not always the original JAR path. With custom `ClassLoader` implementations, information may be incomplete. In addition, `Class.getResource` and other resource lookups are affected by loader policies.

### Step 4: Verify Dependencies and Duplicate Packages

Inspect how the plugin is packaged:

```bash
jar --list --file plugin.jar
```

Look for signs like `com/example/api/Plugin.class` appearing in both the host API JAR and the plugin JAR. Check the build configuration (Gradle/Maven) to see if the shared API was accidentally bundled into a fat JAR or shaded artifact. If the plugin requires an API supplied by the host, you should usually declare this dependency as compile-only/provided to match the packaging workflow.

Note: merely having a copy of the class in both JARs is **not enough** to conclude an error will happen; if the plugin loader delegates to the parent for the API package, both sides can still share the same `Class`.

### Step 5: Inspect the Class-Loading Path

You can use JVM logging to assist in analyzing load sources:

```bash
java -Xlog:class+load=info -jar host.jar
```

Depending on the environment and JVM version, logs can reveal class names, class origins, and involved loaders. Increase log levels selectively when needed, avoiding excessive output in production. Combine this with class-loader identity logs emitted by the application itself to pinpoint where identity splits.

## 5. Java 17+ Example Reproducing the Same-Class-Name Error

The example creates the same class name `example.Shared` from identical bytecode, then defines it twice in two different loaders. It requires no external JARs and directly demonstrates the nature of class identity.

Create **`ClassLoaderIdentityDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;

public class ClassLoaderIdentityDemo {
    public static class Shared {
        public String value() {
            return "hello";
        }
    }

    static final class IsolatedLoader extends ClassLoader {
        private final String target;

        IsolatedLoader(String target) {
            super(ClassLoaderIdentityDemo.class.getClassLoader());
            this.target = target;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            synchronized (getClassLoadingLock(name)) {
                Class<?> loaded = findLoadedClass(name);
                if (loaded == null) {
                    if (name.equals(target)) {
                        loaded = findClass(name);
                    } else {
                        loaded = super.loadClass(name, false);
                    }
                }
                if (resolve) {
                    resolveClass(loaded);
                }
                return loaded;
            }
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!name.equals(target)) {
                throw new ClassNotFoundException(name);
            }

            String resource = name.replace('.', '/') + ".class";
            try (InputStream in =
                    ClassLoaderIdentityDemo.class.getClassLoader()
                        .getResourceAsStream(resource)) {
                if (in == null) {
                    throw new ClassNotFoundException(name);
                }
                byte[] bytes = in.readAllBytes();
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException e) {
                throw new ClassNotFoundException(name, e);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        String name = Shared.class.getName();
        ClassLoader isolated = new IsolatedLoader(name);

        Class<?> another = isolated.loadClass(name);
        Object pluginValue = another.getDeclaredConstructor().newInstance();

        System.out.println("same name: " +
            Shared.class.getName().equals(another.getName()));
        System.out.println("same class: " + (Shared.class == another));
        System.out.println("assignable: " +
            Shared.class.isAssignableFrom(another));
        System.out.println("host loader == plugin loader: " +
            (Shared.class.getClassLoader() == another.getClassLoader()));

        try {
            Shared value = (Shared) pluginValue;
            System.out.println(value.value());
        } catch (ClassCastException e) {
            System.out.println("cast failed: ClassCastException");
        }
    }
}
```

Compile and run:

```bash
javac ClassLoaderIdentityDemo.java
java ClassLoaderIdentityDemo
```

Output:

```text
same name: true
same class: false
assignable: false
host loader == plugin loader: false
cast failed: ClassCastException
```

Why did the error occur?

1. The host's `Shared.class` is defined by the application class loader.
2. `IsolatedLoader` specifically intercepts the nested class name `ClassLoaderIdentityDemo$Shared`; when asked to load that exact name, it reads the `.class` resource and calls `defineClass` itself.
3. The JVM sees two definitions with the same binary name but different defining loaders, and thus creates two `Class` objects with distinct identities.
4. `pluginValue` is an instance of the class defined by `IsolatedLoader`, so it cannot be cast to the `Shared` defined by the host loader.

This is an example intentionally using **child-first for a single class** to reproduce the error. It is not a recommended class-loader architecture for production environments.

## 6. How to Fix: Share the API, Isolate Implementations

A standard principle in plugin systems:

**The shared API is defined by a stable host loader; implementations and private dependencies are defined by plugin loaders.**

```text
              Bootstrap / Platform
                       |
                Host API loader
                 |           |
          PluginLoader A  PluginLoader B
          impl + lib A    impl + lib B
```

Both plugin loaders **delegate to the parent** for shared API packages such as `com.example.plugin.api.*`. As a result, `Plugin`, `Context`, DTOs, and contract exceptions are defined once; the host can cast implementations to the host's interface.

Practical fixes:

- **Remove duplicate APIs** from plugin JARs if the build system already supplies the API from the host.
- **Configure per-package delegation:** parent-first for `java.*`, shared APIs, and libraries that must be shared; isolate only identified implementations/dependencies.
- **Version APIs explicitly:** do not mix a plugin compiled against API v1 with a host running API v2 when they are binary-incompatible.
- **Do not pass plugin-internal objects across the API boundary** unless that type belongs to the shared contract or is converted to an agreed-upon plain DTO.
- **Hot reload:** route new requests to the new loader; avoid directly using surviving objects/proxies from the old loader; close resources when no references remain.
- **Packaging tooling:** inspect artifact contents to prevent accidentally embedding `com.example.plugin.api` via fat JARs/shading.

Gradle example (illustrating configuration for a plugin module only):

```groovy
dependencies {
    compileOnly project(':plugin-api')
    // Libraries that genuinely require separate packaging must be reviewed per runtime.
}
```

`compileOnly` enables compilation without automatically placing the dependency onto the plugin module's runtime classpath. The host/deployment loader must provide the shared API at the proper version at runtime. This configuration does not automatically resolve all dependency conflicts.

**Do not blindly apply child-first to the entire classpath.** If the shared API itself gets redefined, plugin classes may no longer implement the interface the host is checking against.

## 7. When Two Loaders Use the Same Library but Need Version Isolation

Sometimes isolating a dependency is the exact goal: plugin A uses `lib-x` v1, and plugin B uses `lib-x` v2. Versions can be loaded into different loaders, provided the API exchanged between plugin and host **does not expose types from lib-x**.

Example of a good contract:

```java
// Shared API - illustrative idea, not a standalone program.
public interface TextExtractor {
    String extract(byte[] documentBytes);
}
```

Host and plugin exchange only `String` and `byte[]` (JDK types shared by bootstrap/platform/host in normal loading). Plugins can use different parser versions inside their implementations.

A conflict-prone contract:

```java
// Avoid using if Document belongs to a private library inside the plugin loader.
public interface TextExtractor {
    third.party.Document extract(byte[] documentBytes);
}
```

When `third.party.Document` is defined separately in multiple loaders, method signatures, the linker, and casts can run into trouble. Separate the boundary using shared DTOs, primitives/JDK data, JSON/protobuf processed per contract, or even process boundaries when needed.

## 8. Related Errors to Distinguish

| Symptom | Diagnostic direction |
|---|---|
| `ClassCastException` with two identical names | Check the defining loader of both classes |
| `ClassNotFoundException` | The loader could not find the requested name |
| `NoClassDefFoundError` | The JVM could not define/link a dependent class or a class failed initialization earlier |
| `NoSuchMethodError` | Code invokes a method absent from the class linked at runtime |
| `AbstractMethodError` | The runtime implementation does not provide a method required by the binary interface |
| `LinkageError: loader constraint violation` | Loaders violated type identity constraints during linking |
| `IllegalAccessError` or `InaccessibleObjectException` | Check access scopes, JPMS modules, and reflective access |

A `ClassCastException` does not by itself prove that Java "loaded the wrong JAR"; the error may stem from loader design, API packaging, incompatible versions, caches, or provider selection logic. Gather evidence on defining loaders and class sources before changing configuration.

## 9. Practical Checklist When Encountering the Error

1. Record the full stack trace and casting line; identify the actual type and expected type.
2. Log `getName()`, `getClassLoader()`, `isAssignableFrom()`, and `isInstance()`.
3. Map out the classloader graph: parent, child-first exceptions, and which loader defines the API vs. implementation.
4. Inspect the actual JARs and class resources; look for duplicate API package classes or different library versions.
5. Check hot reloads, caches, static singletons, thread context class loaders, or proxies retaining old objects.
6. Ensure the shared API uses a single `Class` definition from the parent/host; restrict isolated packages.
7. Test the real path: load the plugin, cast to the host's interface, invoke methods, release, and replace the plugin.
8. Add packaging and compatibility checks at the pre-activation step so errors are caught before serving requests.

**Remember:** in the JVM, *a class name is not the entirety of a type's identity*. When two "same-named" classes cannot be cast to one another, compare their **defining class loaders**. A durable plugin architecture **shares the contract** at the host boundary and **isolates implementation dependencies** deliberately.