# Separating Shared Data Types and APIs from Plugin Implementations

When an application allows adding plugins, a key design question is: **what must the host and plugins both know, and what must stay private inside each plugin?** If the host directly references an implementation class like UppercaseTransformer, or if the shared API returns a class that exists only inside a specific plugin, adding or replacing a plugin will force modifying and recompiling the host. The solution is to define a small, stable **extension contract** and have both the host and each plugin depend on that contract.

## 1. Three Parts and Dependency Direction

Suppose the host receives text and needs to invoke one of several transformers provided by plugins:

~~~text
             compile-time dependency
host-app --------------------------> plugin-api
                                           ^
                                           |
plugin-uppercase --------------------------+
      |
      +-- registers implementation for the host to discover at runtime

host-app -- runtime discovery --> plugin-uppercase
~~~

| Component | Contains | Depended on by / Depends on |
| --- | --- | --- |
| **plugin-api** | SPI interfaces, input/output data types, error rules, or capabilities to expose | JDK and truly essential shared libraries |
| **host-app** | Orchestration, configuration, plugin selection, lifecycle control, error handling | plugin-api; may load plugins at runtime |
| **plugin-uppercase** | Implementation classes, algorithms, internal dependencies, service registration metadata | plugin-api and its own dependencies |

An SPI (*Service Provider Interface*) is the contract surface a plugin must implement so the host can invoke it. The shared API defines **observable promises**, not **how a plugin fulfills those promises**.

A clean dependency diagram has both compile-time arrows pointing toward plugin-api. In the example below, the host neither imports nor directly instantiates UppercaseTransformer; it knows only the Transformer interface. A plugin can change its algorithm without modifying the host, as long as it continues to satisfy the contract.

Distinguish two concerns: **separating compile-time dependencies** prevents the host from knowing implementation classes; **loading/discovering plugins at runtime** is a separate mechanism (ServiceLoader, DI container, custom class loader...). This article demonstrates both the boundary and a simple discovery mechanism using Java SE.

## 2. Which Data Types and APIs Belong in the Shared Contract?

A good API should contain only concepts that all plugins and the host genuinely share an understanding of:

- **Shared input/output:** DTOs that are meaningful independently of any plugin, such as TransformRequest and TransformResult. Java records fit small data whose component references are immutable; note that records do not automatically make mutable objects stored inside them immutable.
- **Extension behavior:** the Transformer interface with id() and transform(...). Signatures use only types from the JDK or plugin-api.
- **Contract semantics:** id must be stable/unique within a plugin set; transform returns a result for valid input; clearly specify errors, null handling, resources, and thread safety when required by the system.
- **Version or capabilities when needed:** the host can check capabilities/versions before calling newer features, instead of forcing every plugin to immediately understand a changed API.

Do not place into plugin-api classes such as UppercaseTransformer, plugin-specific database configurations, custom HTTP clients, repositories, internal entities, or return types from a library used by only one plugin. A signature such as a method returning com.vendor.plugin.InternalResult forces the host to understand and load that specific data type, breaking the shared boundary.

Nor should the API become a grab bag of every conceivable feature. If two groups of plugins have genuinely different contracts, consider two narrow SPIs or an explicitly declared capability instead of one large interface forcing every plugin to implement unrelated methods.

## 3. Runnable Java 17+ Example: API JAR, Plugin JAR, and Host JAR

This example uses the standard **classpath**, without using the Java Platform Module System (JPMS). Create the files following this structure:

~~~text
src/
  api/
    com/example/spi/
      TransformRequest.java
      TransformResult.java
      Transformer.java
  plugin/
    com/example/plugin/
      UppercaseTransformer.java
    META-INF/services/
      com.example.spi.Transformer
  host/
    com/example/host/
      Main.java
~~~

### Step 1: Write DTOs and SPI in plugin-api

**src/api/com/example/spi/TransformRequest.java**

~~~java
package com.example.spi;

import java.util.Objects;

public record TransformRequest(String text) {
    public TransformRequest {
        Objects.requireNonNull(text, "text");
    }
}
~~~

**src/api/com/example/spi/TransformResult.java**

~~~java
package com.example.spi;

import java.util.Objects;

public record TransformResult(String text) {
    public TransformResult {
        Objects.requireNonNull(text, "text");
    }
}
~~~

**src/api/com/example/spi/Transformer.java**

~~~java
package com.example.spi;

public interface Transformer {
    String id();
    TransformResult transform(TransformRequest request);
}
~~~

Both the host and plugins compile against these three types. The contract makes no mention of the word "uppercase", any implementation class, or how text is processed. Checking null at the DTO boundary catches bad data early; a real project may add other rules such as input size limits.

### Step 2: Write a Separate Implementing Plugin

**src/plugin/com/example/plugin/UppercaseTransformer.java**

~~~java
package com.example.plugin;

import com.example.spi.TransformRequest;
import com.example.spi.TransformResult;
import com.example.spi.Transformer;
import java.util.Locale;

public final class UppercaseTransformer implements Transformer {
    @Override
    public String id() {
        return "uppercase";
    }

    @Override
    public TransformResult transform(TransformRequest request) {
        return new TransformResult(request.text().toUpperCase(Locale.ROOT));
    }
}
~~~

Here Locale.ROOT makes uppercasing independent of the machine's default locale. More importantly, the plugin uses only DTOs and interfaces from plugin-api to communicate with the host. Private helper classes, if any, can stay inside the plugin's own packages.

For Java ServiceLoader to find the provider on the classpath, create a **text file** with the exact name:

**src/plugin/META-INF/services/com.example.spi.Transformer**

~~~text
com.example.plugin.UppercaseTransformer
~~~

The filename is the fully qualified binary name of the SPI; the content is the provider class name implementing the SPI, one class per line. This example uses a public class with a default no-arg constructor and requires no auxiliary libraries.

### Step 3: Host Calls Only Through the Shared Interface

**src/host/com/example/host/Main.java**

~~~java
package com.example.host;

import com.example.spi.TransformRequest;
import com.example.spi.Transformer;
import java.util.Map;
import java.util.ServiceLoader;
import java.util.TreeMap;

public final class Main {
    public static void main(String[] args) {
        Map<String, Transformer> plugins = new TreeMap<>();
        for (Transformer plugin : ServiceLoader.load(Transformer.class)) {
            if (plugins.putIfAbsent(plugin.id(), plugin) != null) {
                throw new IllegalStateException("Duplicate plugin id: " + plugin.id());
            }
        }

        System.out.println("Plugins: " + plugins.keySet());
        Transformer selected = plugins.get("uppercase");
        if (selected == null) {
            throw new IllegalStateException("Missing plugin: uppercase");
        }
        System.out.println(selected.transform(new TransformRequest("hello Java")).text());
    }
}
~~~

The host imports only types in com.example.spi. ServiceLoader reads service metadata from JARs visible to the relevant class loader and instantiates providers. TreeMap keeps the id listing order deterministic for the example; putIfAbsent detects duplicate ids. In a real system, the host should also check for null/blank ids, compatibility, and policies when a provider fails.

### Step 4: Compile into Three JARs and Run

Run from the directory containing src, with **JDK 17 or newer**. The following commands use **PowerShell on Windows**; the --release 17 flag compiles the example code for Java 17:

~~~powershell
New-Item -ItemType Directory -Force -Path 'out/api','out/plugin','out/host','dist' | Out-Null

javac --release 17 -encoding UTF-8 -d out/api src/api/com/example/spi/TransformRequest.java src/api/com/example/spi/TransformResult.java src/api/com/example/spi/Transformer.java
jar --create --file dist/plugin-api.jar -C out/api .

javac --release 17 -encoding UTF-8 -cp dist/plugin-api.jar -d out/plugin src/plugin/com/example/plugin/UppercaseTransformer.java
jar --create --file dist/uppercase-plugin.jar -C out/plugin . -C src/plugin META-INF/services

javac --release 17 -encoding UTF-8 -cp dist/plugin-api.jar -d out/host src/host/com/example/host/Main.java
jar --create --file dist/host.jar -C out/host .

java -cp "dist/plugin-api.jar;dist/host.jar;dist/uppercase-plugin.jar" com.example.host.Main
~~~

On Linux/macOS, replace the directory-creation line with the following command and change the classpath separator in the final command from a semicolon to a colon; the remaining javac and jar commands stay the same:

~~~bash
mkdir -p out/api out/plugin out/host dist
java -cp "dist/plugin-api.jar:dist/host.jar:dist/uppercase-plugin.jar" com.example.host.Main
~~~

**Stdout when running with the plugin JAR:**

~~~text
Plugins: [uppercase]
HELLO JAVA
~~~

What to verify in each command: the host compilation step has only **dist/plugin-api.jar** on its compile classpath; **uppercase-plugin.jar is absent**. The plugin also compiles solely against the API. Only at runtime do we place all three JARs on the runtime classpath so ServiceLoader discovers the implementation.

You can use the following command to verify that the provider descriptor is actually packaged inside the plugin JAR:

~~~powershell
jar tf dist/uppercase-plugin.jar
~~~

The listing must contain both com/example/plugin/UppercaseTransformer.class and META-INF/services/com.example.spi.Transformer. If the registration file is missing or the plugin JAR is omitted from the runtime classpath, ServiceLoader will not find this provider and the host will report a missing plugin.

## 4. Applying This Boundary in a Gradle Project

In a multi-module project, you can use three modules: **plugin-api**, **plugin-uppercase**, and **host-app**. Example dependencies written in Gradle Groovy DSL, each block belonging to the corresponding module's build.gradle:

**plugin-uppercase/build.gradle**

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    compileOnly project(':plugin-api')
}
~~~

**host-app/build.gradle**

~~~groovy
plugins {
    id 'application'
}

dependencies {
    implementation project(':plugin-api')
    runtimeOnly project(':plugin-uppercase')
}

application {
    mainClass = 'com.example.host.Main'
}
~~~

With this configuration, the host compiles against the API and can receive the plugin at runtime. The plugin module still needs the registration file at **src/main/resources/META-INF/services/com.example.spi.Transformer** so Gradle packages it into the JAR. Do not bundle a copy of plugin-api classes inside plugin-uppercase; let the host provide the shared contract at runtime.

These dependencies fit a plugin set known at build/deploy time. If users are allowed to drop in new plugin JARs after the application has started, you need additional mechanisms to manage JAR paths, class loaders, re-discovery, resource closing, and lifecycle rules. Simply dropping a JAR into a folder while the JVM is running will **not automatically** make ServiceLoader.load on the existing classpath see it.

## 5. Class Loader Boundaries: Same Class Name Does Not Guarantee Same Type

In the JVM, a class's identity is defined by **its binary name plus its defining class loader**. If the host loads com.example.spi.Transformer with loader A, while a plugin using a custom child-first loader defines its own copy of Transformer with loader B, those two types are not identical. The result can be an inability to cast, provider configuration errors, or baffling class-linkage errors even though the package/class names look identical.

Rules to apply when using custom class loaders:

1. Load **plugin-api** with a shared loader visible to both host and plugin, typically the parent loader.
2. Have the plugin loader delegate contract packages to the parent; load only implementations and private dependencies from the plugin.
3. Avoid bundling/shading shared contract types into plugin JARs. Shading internal libraries can be valid, but never alter the identity of types crossing the API boundary.
4. Verify that the provider can be cast to the exact Transformer.class used by the host, especially when recreating loaders or loading multiple plugin versions.

This example runs all three JARs on the same application classpath, so it does not require creating custom class loaders. In an environment with JPMS, providers can be declared with `provides` and consumers with `uses` in module-info.java; that is a different packaging/discovery mechanism, while the contract boundary remains the same.

## 6. Designing the Contract for Change and Compatibility

Separating the API from implementations does not mean every API edit is safe. Plugins are often compiled at a different time than the host, so distinguish source, binary, and behavioral compatibility:

| Change | Possible impact | How to handle |
| --- | --- | --- |
| Changing internal algorithm of UppercaseTransformer, keeping SPI intact | Usually no host recompilation needed | Test behavior, repackage plugin |
| Adding an abstract method to Transformer | Older providers may lack the implementation; calling it may cause AbstractMethodError | Consider an appropriate default method or bump the contract version |
| Changing package, name, or signature of the SPI | Pre-built providers may fail to link; old service descriptors no longer match | Plan changes, rebuild/retest plugins, version the API |
| Changing components of a record DTO | Constructor/accessor binary signatures may change; old clients may fail linkage | Add new types, adapters, or version the contract |
| Changing meaning of id, null, errors, or return values | May still compile yet behave incorrectly | Write contract tests and state rules explicitly |

A common strategy is publishing the plugin-api version, documenting the compatibility range, and maintaining a shared **contract test suite** that every provider must pass. If the system needs multiple API generations concurrently, the host must proactively design adapters/version negotiation; you cannot simply hope keeping class names unchanged is enough.

Clarify which errors are input-data errors, provider errors, provider-loading errors, and host errors. Do not force the host to catch custom exception types that exist only in a single plugin's JAR. When handling plugin errors, the host can use an API-defined exception or a consistent error-wrapping mechanism and record the root cause for diagnostics.

## 7. Common Design Mistakes

**Host instantiating implementations directly.** Writing `new UppercaseTransformer()` or importing plugin packages in orchestration code couples the host to the implementation. Replace it with a registry/discovery mechanism returning Transformer, and let the host select by id or capability.

**Using a plugin's DTO in the SPI signature.** A shared interface returning VendorSpecificResponse couples all plugins and the host to one vendor. Put genuinely shared data in plugin-api; convert internal details only on the plugin side. Do not turn a shared DTO into a collection of fields tailored to individual providers.

**Packaging multiple copies of plugin-api across plugin loaders.** Duplicate copies can cause type-identity errors. Ensure a single source supplies the API classes via a parent/common loader and verify the class-loader layout during deployment.

**Having an implementation class without ServiceLoader registration.** Java does not automatically scan all classes just because they implement an interface. With classpath ServiceLoader, you need the exact META-INF/services path and a valid provider; if using a different discovery framework, follow that framework's rules.

**Assuming every plugin is trustworthy or thread-safe.** Plugins running in the same process can hold threads, open files/network connections, throw exceptions, or hang host threads. API documentation must clarify lifecycle, while the host needs appropriate timeouts/isolation per the architecture. A separate class loader helps organize dependencies but **is not a security sandbox**. Hot unload is not guaranteed if objects, threads, or static references still retain the loader.

**Changing the API without testing against previously built plugins.** Successfully building the whole workspace does not prove a previously released plugin is binary-compatible. Test using the actual old JAR against the new API/host whenever compatibility policy requires support.

## 8. How to Self-Check the Boundary on a Real Plugin System

- Temporarily remove implementation JARs from the host's **compile classpath**. The host must still compile if the API is properly separated.
- Open the plugin JAR and verify it contains the provider descriptor and implementation classes, with no duplicate copy of com.example.spi classes.
- Run the host with the plugin JAR to confirm the plugin is discovered and invoked via Transformer; try removing the plugin JAR to ensure the host intentionally reports the missing provider.
- Test two providers with the same id to verify the duplicate policy; test a failing provider and check that the host logs/isolates it according to the contract.
- With dynamic loaders, obtain Transformer.class from the host and cast the provider to that interface; test reloading/resource cleanup, and test plugins built against all still-supported API versions.

**Core principle:** the exchanged data types and APIs genuinely shared by the host and all plugins belong in a stable contract artifact. Algorithms, dependencies, configuration, and implementation classes belong to each plugin. The host manages discovering, selecting, and invoking plugins through that contract; the loading mechanism can evolve without inverting the dependency direction.