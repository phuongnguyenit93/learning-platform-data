# NoSuchMethodError After Module Version Mismatch

In a modular Java application, a module can resolve successfully yet the application still fails when invoking a method at runtime. A common cause is that the consumer was compiled against one API version, while runtime loads another module version that no longer has the method requested by the bytecode.

The error typically looks like:

~~~text
java.lang.NoSuchMethodError:
  'java.lang.String com.example.library.api.GreetingApi.greet(java.lang.String)'
~~~

This is a binary linkage error. The JVM found the class yet could not find a method with the name and descriptor invoked by bytecode. JPMS manages module resolution, readability, and package access permissions; it does not automatically verify semantic version compatibility between compile-time and runtime library versions.

## 1. When does NoSuchMethodError occur?

NoSuchMethodError is a subclass of IncompatibleClassChangeError and LinkageError. It occurs when bytecode invokes a method yet the JVM cannot find the matching method in the loaded class or interface.

For example, the consumer was compiled against the API:

~~~java
package com.example.library.api;

public class GreetingApi {

    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

The consumer's bytecode contains a call to the method named greet with a descriptor matching a String parameter and a String return type.

Yet runtime loads an older version:

~~~java
package com.example.library.api;

public class GreetingApi {

    public String greet() {
        return "Hello";
    }
}
~~~

The runtime version lacks greet(String). When the consumer executes the compiled call, the JVM cannot link the method and throws NoSuchMethodError.

Key points:

- The class may exist and load successfully.
- The module may resolve successfully.
- The consumer module may read the library module.
- The API package may be exported properly.
- Yet the method descriptor required by bytecode can still be absent in the runtime class.

Therefore, this error usually surfaces only when execution reaches the affected call site, rather than immediately at JVM startup.

## 2. Why do module versions not automatically prevent the error?

A module descriptor can carry version metadata. When packaging a module, the JAR tool allows recording a version via the --module-version option. Runtime can read this metadata via ModuleDescriptor.version().

However, dependency declarations in module-info.java specify only the module name:

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

The declaration above requests a module named com.example.library. It does not express a version range like >= 2.0 and < 3.0, nor does it guarantee that a given method exists.

JPMS performs these primary tasks:

- Finding observable modules on configured module sources.
- Resolving the module graph based on module names and requires relationships.
- Establishing readability between modules.
- Enforcing exports, opens, and access rules.

JPMS is not a dependency version manager. A module version is descriptive metadata; the metadata itself does not enforce an API compatibility policy.

Consequently, an application can be compiled against com.example.library version 2.0 yet load version 1.0 of the same-named module at runtime. If version 1.0 lacks a method the consumer needs, a linkage error can occur.

## 3. Reproduction example between two module versions

Let us create a library with two versions. Both use the same module name, com.example.library.

### Version 1.0

File module-info.java:

~~~java
module com.example.library {
    exports com.example.library.api;
}
~~~

File GreetingApi.java:

~~~java
package com.example.library.api;

public class GreetingApi {

    public String greet() {
        return "Hello";
    }
}
~~~

Version 1.0 only has a zero-argument greet() method.

### Version 2.0

The module descriptor keeps the same name and exported package:

~~~java
module com.example.library {
    exports com.example.library.api;
}
~~~

GreetingApi.java in version 2.0:

~~~java
package com.example.library.api;

public class GreetingApi {

    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

Version 2.0 provides greet(String), which the new consumer will use.

### Consumer module

File module-info.java:

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

File Main.java:

~~~java
package com.example.app;

import com.example.library.api.GreetingApi;

public class Main {

    public static void main(String[] args) {
        GreetingApi api = new GreetingApi();
        System.out.println(api.greet("Ada"));
    }
}
~~~

The consumer is compiled against version 2.0 of the library module:

~~~shell
javac --module-path artifacts/com.example.library-2.0.jar -d build/app src/app/module-info.java src/app/com/example/app/Main.java
~~~

After compilation, Main's bytecode contains a call to greet(String).

### Accidentally running version 1.0

Suppose runtime is configured with library version 1.0:

~~~shell
java --module-path "build/app;artifacts/com.example.library-1.0.jar" --module com.example.app/com.example.app.Main
~~~

On Windows, semicolons separate module path entries. On Linux or macOS, replace the semicolon with a colon:

~~~shell
java --module-path "build/app:artifacts/com.example.library-1.0.jar" --module com.example.app/com.example.app.Main
~~~

The output will look like:

~~~text
Exception in thread "main" java.lang.NoSuchMethodError:
  'java.lang.String com.example.library.api.GreetingApi.greet(java.lang.String)'
    at com.example.app/com.example.app.Main.main(Main.java:...)
~~~

Module com.example.library version 1.0 still has the exact name app requires. Therefore module resolution can succeed. Yet the GreetingApi class in version 1.0 lacks greet(String), so the call in bytecode fails.

This is a classic example of module names matching while the binary API is incompatible.

## 4. Distinguishing module resolution errors from linkage errors

Both errors can appear in the same application yet occur at different stages.

| Scenario | Stage | Common symptom |
| --- | --- | --- |
| Required module not found | Module resolution | FindException or module not found error |
| Module cannot read another module | Readability / access check | Compilation error or corresponding access error |
| Package not exported | Cross-module API access | Compilation error or runtime access error |
| Package not open for deep reflection | Reflection | InaccessibleObjectException or trySetAccessible() returning false |
| Method absent from runtime class | Binary linkage | NoSuchMethodError |

NoSuchMethodError does not mean the module path is wrong in every case. The module path may find a module with the right name, yet the loaded artifact is incompatible with the consumer.

Also distinguish NoSuchMethodError from several other linkage errors:

- NoClassDefFoundError: a required class could not be found or initialized under the circumstances.
- NoSuchFieldError: a field requested by bytecode does not exist.
- IllegalAccessError: the member exists yet access violates access rules.
- AbstractMethodError: the call needs a concrete implementation yet the runtime class provides no suitable implementation.
- IncompatibleClassChangeError: the class structure or usage changed incompatibly, such as certain static/instance changes.

Do not alter exports or opens just because you see an error involving modules. Those options cannot recreate a removed method or change a descriptor.

## 5. Inspecting the actual loaded module and artifact

When encountering the error, determine where the runtime class came from. Do not rely solely on the version in build files or the JAR filename.

### Inspecting a class's module

For a class in a named module:

~~~java
import java.lang.module.ModuleDescriptor;

public class ModuleDiagnostics {

    public static void print(Class<?> type) {
        Module module = type.getModule();

        System.out.println("Class: " + type.getName());
        System.out.println("Module: " + module.getName());

        ModuleDescriptor descriptor = module.getDescriptor();

        if (descriptor != null) {
            System.out.println(
                "Module version: "
                    + descriptor.version()
                        .map(Object::toString)
                        .orElse("<not recorded>")
            );
        }

        ModuleLayer layer = module.getLayer();

        if (layer != null) {
            layer.configuration()
                .findModule(module.getName())
                .ifPresent(resolved -> System.out.println(
                    "Module location: "
                        + resolved.reference().location()
                            .map(Object::toString)
                            .orElse("<unknown>")
                ));
        }

        var codeSource = type.getProtectionDomain().getCodeSource();

        System.out.println(
            "Class code source: "
                + (codeSource == null
                    ? "<unknown>"
                    : codeSource.getLocation())
        );
    }
}
~~~

Call the diagnostic method on the class actually causing the error:

~~~java
ModuleDiagnostics.print(GreetingApi.class);
~~~

This information helps identify:

- The module name the class belongs to.
- Version metadata if the module recorded any.
- The module layer holding the module.
- The module reference's location in the configuration.
- The class's code source if the class loader provides this information.

For an unnamed module, Module.getDescriptor() returns null and the module has no name. In applications with custom class loaders or custom ModuleLayers, inspect the exact class used at the call site.

### Inspecting module resolution at startup

You can add the option:

~~~shell
java --show-module-resolution --module-path mods --module com.example.app/com.example.app.Main
~~~

This option displays details about module resolution. It is useful for seeing which modules enter the graph and which dependencies are found.

However, resolution output does not prove every method from the API version the consumer needs exists. You still must check artifacts and binary signatures.

### Inspecting JAR descriptors

Use the jar tool:

~~~shell
jar --describe-module --file artifacts/com.example.library-1.0.jar
jar --describe-module --file artifacts/com.example.library-2.0.jar
~~~

Compare module names, exported packages, and version metadata. If two JARs share the same module name yet differ in version, check which artifact runtime is actually selecting.

## 6. Comparing compile-time and runtime method descriptors

The JVM links methods using binary information, including method name and descriptor. The descriptor encodes parameter types and return type.

Use javap to inspect the class inside each JAR:

~~~shell
javap -classpath artifacts/com.example.library-1.0.jar -p -s com.example.library.api.GreetingApi

javap -classpath artifacts/com.example.library-2.0.jar -p -s com.example.library.api.GreetingApi
~~~

The output for version 1.0 might show:

~~~text
public java.lang.String greet();
  descriptor: ()Ljava/lang/String;
~~~

Version 2.0:

~~~text
public java.lang.String greet(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/lang/String;
~~~

The two descriptors differ. A call to greet(String) cannot link against greet().

You can also inspect the consumer's bytecode:

~~~shell
javap -classpath build/app -c -s com.example.app.Main
~~~

Look for invokevirtual or invokeinterface instructions referencing GreetingApi.greet. The constant pool and descriptor show which method the bytecode requests.

If the consumer was compiled against API version 2.0, while the runtime class has only version 1.0's method, the root cause is identified.

## 7. Common causes in real-world projects

**Different compile-time and runtime dependencies.** Gradle or Maven selects one artifact during compilation, while runtime packaging contains a different version. Check both compile classpath and runtime classpath.

**Stale JARs left behind in deployment directories.** The application was rebuilt, yet the container, libs directory, application server, or deploy directory still holds old artifacts.

**Transitive dependencies selecting an unexpected version.** Another library pulls in an older library version. Build tools resolve conflicts by their own rules; inspect the actual dependency graph.

**Multiple modules or class loaders.** An application may use the boot layer, custom ModuleLayers, plugin class loaders, or an additional classpath. The class loaded at the call site may come from a different artifact than the one the operator is inspecting.

**Module patches or upgrade paths.** Options like --patch-module and --upgrade-module-path can alter runtime module contents or sources. Include them in your inspection if the application uses them.

**Incompatible API changes.** A method was removed, renamed, or had parameter or return types changed. The consumer still retains older bytecode calling a method that no longer exists.

**Packaging the wrong dependency.** The build creates the right JAR, yet the distribution directory, container image, or startup script points to a different JAR file.

## 8. Ordered resolution workflow

When encountering NoSuchMethodError after upgrading a module version, follow this order:

1. Read the full stack trace to identify the failing class and call site.
2. Identify the method name and descriptor in the error message.
3. Check the compile-time dependency the consumer used.
4. Check the actual runtime classpath and module path in the launch command or deployment environment.
5. Print the module name, module version, and code source of the runtime class.
6. Use jar --describe-module to compare module descriptors.
7. Use javap -p -s to compare method signatures between compile-time and runtime artifacts.
8. Inspect the dependency tree to find versions pulled in transitively or overridden.
9. Check custom layers, class loaders, --patch-module, and --upgrade-module-path if the application uses them.
10. Once the right artifact is identified, synchronize dependencies and rebuild the consumer if the API changed intentionally.

### Gradle

Inspect the runtime classpath dependency tree:

~~~shell
./gradlew dependencies --configuration runtimeClasspath
~~~

Find why a specific dependency version was chosen:

~~~shell
./gradlew dependencyInsight --dependency com.example.library --configuration runtimeClasspath
~~~

Inspect the corresponding compile classpath:

~~~shell
./gradlew dependencies --configuration compileClasspath
~~~

Compare the outputs to determine which version the build compiles against and which version enters runtime.

### Maven

Inspect the dependency tree:

~~~shell
mvn dependency:tree -Dincludes=com.example:library
~~~

Check dependency mediation, direct dependencies, and transitive dependencies.

### Synchronizing artifacts

Once the cause is identified:

- Pin or centrally manage dependency versions so compile and runtime use the intended version.
- Remove stale JARs from deployment directories or container images.
- Check whether launch scripts and environment variables append a different module path.
- Clean and rebuild the consumer when the API has changed intentionally.
- Deploy related modules together, avoiding mixing artifacts from different builds.
- If compatibility must be preserved, re-release the library with the old method or provide an appropriate migration path.

## 9. Preventing this during module development

**Maintain binary compatibility for public APIs.** Avoid removing or changing the descriptor of a published method in a minor release if the project commits to binary compatibility.

**Manage versions consistently.** Use dependency constraints, version catalogs, platforms/BOMs, or dependency locking appropriate for your build tool. A module name in JPMS does not replace artifact version management.

**Test against packaged artifacts.** Test the actual JARs, runtime images, or containers rather than running solely on the IDE's classpath.

**Include compatibility tests.** Run consumers compiled against a previous API version on top of the new library if the project requires binary compatibility. An API compatibility checker can be added to CI.

**Avoid ambiguous class sources.** Control the module path, classpath, custom class loaders, and module layers. Log artifact sources when diagnosing.

**Announce API changes with a roadmap.** If a method must be removed or have its signature changed, mark it deprecated first, provide a replacement method, and publish migration instructions. Breaking changes should be managed under the library's versioning policy.

## 10. Misconceptions to avoid

1. **Same module name means compatible API:** the module name only identifies the module dependency; it does not guarantee identical method signatures.
2. **Module version is checked automatically by JPMS:** version metadata is not a version range and does not prevent runtime from resolving an incompatible version.
3. **If the module resolved, linkage errors are impossible:** resolution does not verify that every method the consumer compiled against will exist.
4. **NoSuchMethodError is always caused by exports:** exports govern package access permissions, not missing methods.
5. **Adding --add-reads will fix a missing method:** readability does not alter bytecode or class definitions.
6. **A clean build is always enough:** if runtime still loads an old JAR from a deploy directory or container, the error will persist.
7. **Looking only at the JAR filename tells you the running version:** inspect the class code source, module descriptor, and actual module configuration.

## Conclusion

NoSuchMethodError in a JPMS application usually indicates that the consumer and the runtime class disagree on the binary API. Module resolution can succeed because the module name still matches, while the method requested by bytecode was removed or had its descriptor changed. Identify the exact runtime class loaded, compare method descriptors with javap, inspect the dependency graph, and synchronize compile-time and runtime artifacts. JPMS enforces module boundaries; version management and API compatibility remain the responsibility of your build and release process.