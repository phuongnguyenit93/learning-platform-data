# Shared Loader for Contracts and Dedicated Loaders per Plugin

A Java system that supports plugins typically must satisfy two requirements simultaneously: **the host and all plugins share a common understanding of an extension contract**, yet **each plugin is allowed to use different versions of internal libraries**. If all plugins and dependencies are placed on a single classpath with a single application class loader, classes with the same binary name can suffer version conflicts. Conversely, if the contract interface itself is loaded as multiple independent copies, providers may no longer be castable to the interface used by the host.

The foundational solution is to **share the class loader that defines the contract types**, while **creating a dedicated class loader for each plugin** to load that plugin's implementation and dependencies. This structure establishes clear dependency boundaries, well-suited for building runtime extensibility in Java 17+.

## 1. Why Are Two Class-Loading Scopes Needed?

Suppose the host publishes the GreetingPlugin interface. Plugins Alpha and Beta both implement GreetingPlugin, but each plugin packages a library containing the class com.example.dep.Utility:

- Alpha needs a version of Utility that behaves by returning the string library-alpha-v1.
- Beta needs a version of Utility that behaves by returning the string library-beta-v2.
- The host only wants to call GreetingPlugin.id() and GreetingPlugin.message(); the host does not need to know about Utility.

If both JARs are combined into **the same classpath** and loaded by **the same class loader**, the JVM defines only one class with the binary name com.example.dep.Utility in that loader. It cannot use two different definitions with the same name inside one loader merely according to each plugin's preference. Depending on classpath order and dependency resolution, one version of Utility may be selected for both plugins, leading to incorrect behavior or linkage errors when the library APIs are incompatible.

Conversely, if the host loads GreetingPlugin with loader A, while a plugin defines another copy of GreetingPlugin with loader B, Java treats them as **two distinct types**, even when they have the same package name, the same source code, and the same method signatures. Casting the plugin to the host's type can fail.

It is necessary to preserve **a single shared identity for the contract**, while **isolating identities for internal classes**.

## 2. Class Identity in the JVM: Class Name Plus Defining Loader

A Java class in the JVM is identified by the pair:

~~~text
(binary class name, defining class loader)
~~~

For example:

~~~text
(com.example.spi.GreetingPlugin, SharedLoader)  ← shared contract

(com.example.dep.Utility, PluginAlphaLoader)     ← Alpha's Utility
(com.example.dep.Utility, PluginBetaLoader)      ← Beta's Utility
~~~

The two Utility classes above are two distinct Class objects despite having the same binary name. They can have different bytecode, static fields, singletons, and dependencies. This is the basis of **per-plugin library version isolation**.

In contrast, the host and both plugins must reference the **exact same Class object** for GreetingPlugin. Any DTO, exception, enum, callback, and interface types that **cross the boundary between the host and plugins** must also share the same class definition or be converted through a neutral format.

The class-loading layout can be visualized as follows:

~~~text
       Bootstrap / Platform Class Loaders (JDK)
                         |
             Shared/API Parent Loader
             holds plugin-api and shared types
                  /              \
                 /                \
       PluginAlphaLoader       PluginBetaLoader
       alpha.jar + libs A      beta.jar + libs B
       Utility v1              Utility v2

The host communicates through GreetingPlugin belonging to Shared/API Loader.
Plugin Alpha and Beta do not see each other's private classes.
~~~

In larger systems, the host itself may be loaded by a separate loader that also sees the API parent. In the minimal example below, the **application class loader** containing the host and api.jar is used as the common parent for two URLClassLoader instances. This accurately demonstrates API sharing and dependency isolation, though it **does not hide the host's internal classes from plugins**: any class present in the parent can still be found by a child loader.

## 3. Dependency Diagram and Sharing Principles

| Component | Where it is loaded | What it should contain |
| --- | --- | --- |
| plugin-api.jar | Shared/API parent loader | GreetingPlugin and all contract types exchanged between host and plugins |
| host.jar | Application/host loader | Orchestration, version checking, plugin selection, loader and lifecycle management |
| alpha.jar | PluginAlphaLoader | AlphaPlugin along with Alpha's Utility version and private dependencies |
| beta.jar | PluginBetaLoader | BetaPlugin along with Beta's Utility version and private dependencies |
| Types in java.lang, java.util... | JDK platform loaders | String, List, ServiceLoader, ClassLoader, URLClassLoader... |

The compile-time dependency direction should be:

~~~text
host --------------------> plugin-api
alpha implementation ----> plugin-api
beta implementation -----> plugin-api

host -- runtime discovery --> alpha / beta (via shared interface)
~~~

**Do not** import AlphaPlugin or BetaPlugin directly into the host. **Do not** let a GreetingPlugin signature return com.example.dep.Utility or a class that exists only in plugin Alpha. If the host needs data, define a shared DTO in plugin-api or exchange via common JDK types, and convert from the plugin's internal type before returning the result.

When deploying, provide only **one copy of the contract API** via the parent. Do not put dependencies that need isolation into the parent, because Java's default loader delegates to the parent first; a Utility class already present in the parent will be shared instead of loaded separately in the two children.

## 4. Parent-First Delegation and Limitations of URLClassLoader

Standard Java class loaders use the **parent-first** rule: when asked to load a class, the loader asks its parent first; only if the parent cannot find it does the loader try its own sources. URLClassLoader also follows this delegation direction by default.

With a parent containing plugin-api but **not containing** alpha.jar, beta.jar, or internal libraries:

1. PluginAlphaLoader needs GreetingPlugin: the parent returns the exact shared API class.
2. PluginAlphaLoader needs AlphaPlugin: the parent does not have this class; the Alpha loader loads it from alpha.jar.
3. PluginAlphaLoader needs Utility: the parent does not have Utility; the Alpha loader defines the version from alpha.jar.
4. PluginBetaLoader needs Utility: the parent does not have Utility; the Beta loader defines the version from beta.jar.
5. The host receives AlphaPlugin and BetaPlugin through the GreetingPlugin interface that has the same type identity in the parent.

A common pitfall: merely creating two URLClassLoader instances **does not guarantee isolation** if the parent already carries the plugin JARs or libraries that need to be separated. For example, if the host runs with alpha.jar and beta.jar on the system classpath, the parent can define Utility first, causing both children to receive the same copy. Therefore, **the host startup classpath should carry only the API and the host**, while plugin JARs are passed into the URLs of each child loader.

A **child-first** variant can be used in complex plugin engines to prioritize private dependencies. However, it must still delegate contract types, JDK types, and designated shared packages to the parent; if a child-first loader redefines GreetingPlugin itself, the SPI boundary breaks. The URLClassLoader in this example **is not a custom child-first loader**.

## 5. Java 17+ Example: Two Plugins with Same-Named Library Classes but Different Behavior

The example below creates **four JARs**: api.jar, host.jar, alpha.jar, and beta.jar. Each plugin JAR has its own com.example.dep.Utility class with different contents. Two child loaders share a common parent containing GreetingPlugin. The host uses ServiceLoader to discover the provider in each plugin.

Files to create:

~~~text
src/
  api/com/example/spi/GreetingPlugin.java
  host/com/example/app/Main.java
  alpha/com/example/dep/Utility.java
  alpha/com/example/plugins/AlphaPlugin.java
  beta/com/example/dep/Utility.java
  beta/com/example/plugins/BetaPlugin.java
resources/
  alpha/META-INF/services/com.example.spi.GreetingPlugin
  beta/META-INF/services/com.example.spi.GreetingPlugin
~~~

### 5.1. Shared Contract API

**src/api/com/example/spi/GreetingPlugin.java**

~~~java
package com.example.spi;

public interface GreetingPlugin {
    String id();
    String message();
}
~~~

The signatures use only String, a JDK type known to both the host and plugins. The API declares no dependencies on Utility, AlphaPlugin, or BetaPlugin. When designing a real system, public input/output types, contract exceptions, and callback-passing APIs should also reside in the shared artifact.

### 5.2. Plugin Alpha and Its Private Dependency Version

**src/alpha/com/example/dep/Utility.java**

~~~java
package com.example.dep;

public final class Utility {
    private Utility() {}

    public static String label() {
        return "library-alpha-v1";
    }
}
~~~

**src/alpha/com/example/plugins/AlphaPlugin.java**

~~~java
package com.example.plugins;

import com.example.dep.Utility;
import com.example.spi.GreetingPlugin;

public final class AlphaPlugin implements GreetingPlugin {
    public String id() {
        return "alpha";
    }

    public String message() {
        return Utility.label();
    }
}
~~~

**resources/alpha/META-INF/services/com.example.spi.GreetingPlugin**

~~~text
com.example.plugins.AlphaPlugin
~~~

The META-INF/services file announces the implementation class to ServiceLoader. When using the classpath, the file must have a **name matching the binary name of the service** and contain the **binary name of the provider**, saved as UTF-8 text.

### 5.3. Plugin Beta and a Different Dependency Version

**src/beta/com/example/dep/Utility.java**

~~~java
package com.example.dep;

public final class Utility {
    private Utility() {}

    public static String label() {
        return "library-beta-v2";
    }
}
~~~

**src/beta/com/example/plugins/BetaPlugin.java**

~~~java
package com.example.plugins;

import com.example.dep.Utility;
import com.example.spi.GreetingPlugin;

public final class BetaPlugin implements GreetingPlugin {
    public String id() {
        return "beta";
    }

    public String message() {
        return Utility.label();
    }
}
~~~

**resources/beta/META-INF/services/com.example.spi.GreetingPlugin**

~~~text
com.example.plugins.BetaPlugin
~~~

The two Utility.java files have the **same package and the same class name**, but reside in two separate compilation sources and two separate JARs. They intentionally represent two versions that cannot be defined simultaneously in a single loader. Using two separate URLClassLoader instances resolves this exact name collision.

### 5.4. Host Creating Two Plugin Loaders Sharing the API Parent

**src/host/com/example/app/Main.java**

~~~java
package com.example.app;

import com.example.spi.GreetingPlugin;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.Iterator;
import java.util.ServiceLoader;

public final class Main {
    private static GreetingPlugin onlyProvider(ClassLoader loader) {
        Iterator<GreetingPlugin> it =
                ServiceLoader.load(GreetingPlugin.class, loader).iterator();

        if (!it.hasNext()) {
            throw new IllegalStateException("No provider");
        }
        GreetingPlugin provider = it.next();
        if (it.hasNext()) {
            throw new IllegalStateException("Multiple providers");
        }
        return provider;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: Main <alpha.jar> <beta.jar>");
        }

        ClassLoader shared = GreetingPlugin.class.getClassLoader();
        URL alphaUrl = Path.of(args[0]).toUri().toURL();
        URL betaUrl = Path.of(args[1]).toUri().toURL();

        try (URLClassLoader alphaLoader =
                    new URLClassLoader(new URL[]{alphaUrl}, shared);
             URLClassLoader betaLoader =
                    new URLClassLoader(new URL[]{betaUrl}, shared)) {

            GreetingPlugin alpha = onlyProvider(alphaLoader);
            GreetingPlugin beta = onlyProvider(betaLoader);

            System.out.println(alpha.id() + ": " + alpha.message());
            System.out.println(beta.id() + ": " + beta.message());

            Class<?> apiFromAlpha = Class.forName(
                    "com.example.spi.GreetingPlugin", false, alphaLoader);
            Class<?> apiFromBeta = Class.forName(
                    "com.example.spi.GreetingPlugin", false, betaLoader);

            System.out.println("API shared: " +
                    (apiFromAlpha == GreetingPlugin.class &&
                     apiFromBeta == GreetingPlugin.class));

            Class<?> depFromAlpha = Class.forName(
                    "com.example.dep.Utility", false, alphaLoader);
            Class<?> depFromBeta = Class.forName(
                    "com.example.dep.Utility", false, betaLoader);

            System.out.println("Dependency isolated: " +
                    (depFromAlpha != depFromBeta));
        }
    }
}
~~~

Key points:

- **GreetingPlugin.class.getClassLoader()** returns the loader that actually loaded the contract interface into the host. In this classpath-run example, that is the application class loader containing api.jar and host.jar. Both URLClassLoader instances use it as their parent.
- **Each URLClassLoader receives the URL of a separate plugin JAR.** Do not put both alpha.jar and beta.jar into the same child.
- **ServiceLoader.load(GreetingPlugin.class, loader)** explicitly specifies the loader used to discover providers. The ServiceLoader.load(GreetingPlugin.class) overload without a loader argument uses the thread context class loader; in this example it normally cannot see the plugin JARs.
- **onlyProvider** verifies that each loader finds exactly one provider; if none or more than one provider is found, it throws a clear error. In a real system there may be multiple providers in a single JAR, in which case a registry with distinct IDs and a selection policy is used.
- **Class.forName(name, false, loader)** asks for the class visible to the supplied loader; the false parameter avoids eagerly initializing the class just to check identity. The == operator compares Class objects, not name strings.
- **try-with-resources** calls close() on the URLClassLoader once the providers are no longer used in the example. Closing a loader does not mean classes are immediately unloaded; section 7 explains the lifecycle.

### 5.5. Compiling and Packaging the JARs

From the directory containing src and resources, use **PowerShell on Windows**, JDK 17 or later. The .java files and META-INF/services resources must be created beforehand at the exact paths shown above:

~~~powershell
New-Item -ItemType Directory -Force -Path out/api,out/host,out/alpha,out/beta,dist | Out-Null

javac --release 17 -encoding UTF-8 -d out/api src/api/com/example/spi/GreetingPlugin.java
jar --create --file dist/api.jar -C out/api .

javac --release 17 -encoding UTF-8 -cp dist/api.jar -d out/alpha src/alpha/com/example/dep/Utility.java src/alpha/com/example/plugins/AlphaPlugin.java
jar --create --file dist/alpha.jar -C out/alpha . -C resources/alpha META-INF/services

javac --release 17 -encoding UTF-8 -cp dist/api.jar -d out/beta src/beta/com/example/dep/Utility.java src/beta/com/example/plugins/BetaPlugin.java
jar --create --file dist/beta.jar -C out/beta . -C resources/beta META-INF/services

javac --release 17 -encoding UTF-8 -cp dist/api.jar -d out/host src/host/com/example/app/Main.java
jar --create --file dist/host.jar -C out/host .

java -cp "dist/api.jar;dist/host.jar" com.example.app.Main dist/alpha.jar dist/beta.jar
~~~

On Linux/macOS, you can create the directories with mkdir -p out/api out/host out/alpha out/beta dist and change the semicolon **only in the runtime classpath** to a colon. The remaining javac and jar commands stay the same. In environments using build tools, organize each API/host/plugin as a separate module/artifact and ensure plugin-private packages are not placed on the host's runtime classpath.

**Exact stdout when running:**

~~~text
alpha: library-alpha-v1
beta: library-beta-v2
API shared: true
Dependency isolated: true
~~~

The output was verified using javac --release 17, separate JAR packaging, and running on a newer JDK. The first two lines prove that each plugin receives **its own version of Utility**. The line API shared: true proves that both loaders delegate to the same Class object for GreetingPlugin. The line Dependency isolated: true proves that the two com.example.dep.Utility classes do not have the same Class identity, even though their binary names are identical.

**Why are alpha.jar and beta.jar omitted from the -cp argument of java?** These JARs are loaded by the URLClassLoader instances created by Main.java from the two program arguments. If they were added to -cp, the application class loader could load the plugin classes before the child loaders, invalidating the isolation test. Here, only api.jar and host.jar are present on the startup classpath.

You can inspect the Alpha JAR:

~~~powershell
jar tf dist/alpha.jar
~~~

The listing must include the following entries (along with the manifest and directories):

~~~text
com/example/dep/Utility.class
com/example/plugins/AlphaPlugin.class
META-INF/services/com.example.spi.GreetingPlugin
~~~

You should not see com/example/spi/GreetingPlugin.class packaged inside alpha.jar. The contract must be supplied centrally from api.jar. Likewise, beta.jar contains its own version of Utility.class, BetaPlugin.class, and the corresponding descriptor.

## 6. When a Plugin Has Multiple Private Dependency JARs

In practice, a plugin may use multiple libraries, not just a single Utility.class packaged in the same JAR. Create the URLClassLoader with a URL list containing **plugin.jar and every dependency JAR private to that plugin**:

~~~java
URL[] pluginUrls = {
    Path.of("plugins/alpha/alpha.jar").toUri().toURL(),
    Path.of("plugins/alpha/lib/vendor-a.jar").toUri().toURL(),
    Path.of("plugins/alpha/lib/vendor-b.jar").toUri().toURL()
};
ClassLoader apiParent = GreetingPlugin.class.getClassLoader();
URLClassLoader pluginLoader = new URLClassLoader(pluginUrls, apiParent);
~~~

This is an **illustrative snippet used inside a method that handles Exception** and imports java.net.URL, java.net.URLClassLoader, and java.nio.file.Path; it is not a standalone source file. URLClassLoader loads classes from the JAR URLs it manages. These JARs should be managed as a unified deployment set, with version verification and without duplicating the contract API. Each other plugin can use its own separate JAR list, as long as the parent does not contain the libraries that need isolation.

For internal dependencies with the **same binary name** where two plugins need **different versions**, two separate loaders produce different Class identities. However, if a library resides in the parent and the child also has another version, the parent-first rule prioritizes the copy in the parent. When classifying dependencies, do not look only at Maven/Gradle dependencies on paper: you must inspect the **actual runtime classpath and delegation**.

If a plugin's library needs to call into the host, define a narrow API in the shared artifact, such as a PluginContext provided by the host, and pass an instance through that interface; avoid having private dependencies directly import internal host classes.

## 7. Loader Lifecycle, Caching, and Resource Release

A URLClassLoader is typically the **unit of class and resource loading** that lives alongside the plugin. When a plugin stops or is replaced, the host must perform the appropriate steps:

1. Stop dispatching new requests or jobs to the stopping plugin.
2. Wait for or cancel running operations according to application policy.
3. Invoke the plugin's cleanup/close method if published by the contract; interrupt threads, unregister listeners, close connections, and release resources the plugin created.
4. Release any registries, ServiceLoader instances, Class objects, and plugin instances still held by the host.
5. Call URLClassLoader.close() to close the JAR/URL resources managed by the loader.
6. Drop any references holding onto the plugin loader if you want it to become eligible for JVM garbage collection.

**close() does not force the JVM to unload classes immediately.** Class unloading depends on the garbage collectability of the class loader and related objects. Live threads, thread context class loaders (TCCL), static registries, ThreadLocal variables, loggers, JDBC drivers, callbacks, or caches in the host can continue holding references. You cannot claim to have hot-unloaded a plugin merely because the close() method finished.

A ServiceLoader caches discovered providers; reload() clears its internal cache and starts discovery anew, but **does not replace the class loader** and does not reopen a closed URLClassLoader. If implementing hot reload with a new JAR, create a new loader, verify compatibility, shift traffic, and release the old loader in a controlled manner. These steps belong to the **plugin lifecycle**, not merely to loadClass behavior.

## 8. Thread Context Class Loader and ServiceLoader

Many frameworks and JDK APIs can use the **thread context class loader** to locate resources or providers instead of using the calling class's loader. For instance, the ServiceLoader.load(GreetingPlugin.class) overload uses the current thread's context class loader to discover providers.

In a host managing multiple loaders, **prefer passing the loader explicitly** when the API allows it, as in the Main.java example. If a library inside a plugin relies on the TCCL, the host may need to set the context loader around the plugin call and then **restore it with finally**:

~~~java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(alphaLoader);
    System.out.println(alpha.message());
} finally {
    thread.setContextClassLoader(previous);
}
~~~

This is an illustrative snippet placed **inside main while alphaLoader and alpha are still alive**; do not add it to the example's Main.java if you want to preserve the exact verified stdout. Setting the TCCL must be narrowly scoped and fully restored; if a thread pool accidentally retains a loader, it can leak the old loader when swapping plugins. The TCCL does not alter class definitions already determined by parent/child delegation and does not turn two copies of an API into the same type.

Also remember that ServiceLoader.load(service, pluginLoader) can see service descriptors in the **parent** if the parent contains matching resources. The example intentionally leaves the host without a GreetingPlugin descriptor, so each loader discovers only the provider from its own JAR. If the host also publishes providers, you must filter or design discovery by specific source/plugin to avoid accidentally picking a parent provider.

## 9. Typical Errors and How to Fix Them

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| ClassCastException or ServiceConfigurationError: not a subtype | The SPI was redefined in the plugin loader or class loaders do not share the same type | Move the SPI, DTOs, and contract exceptions to the API parent; verify Class objects |
| NoSuchMethodError/NoClassDefFoundError in a plugin | The dependency was actually loaded from the parent or an internal JAR is missing | Check runtime URLs, host classpath, and dependency versions |
| Both plugins exhibit the same Utility behavior | Utility is already present in the parent or plugins share a single child loader | Remove the private dependency from the parent and create one loader per plugin |
| Host cannot find provider | Incorrect META-INF/services, missing JAR, or calling a ServiceLoader overload that cannot see the child | Check the descriptor and pass the proper class loader to ServiceLoader.load |
| Plugin A unexpectedly sees B's classes | Both JARs are in the same loader or a shared loader contains implementations | Separate URLs and avoid sharing implementations via the parent |
| Metaspace grows after multiple reloads | Threads, caches, TCCL, classes/instances, or resources still retain the old loader | Perform cleanup and drop references according to the lifecycle |
| Calling only URLClassLoader.close() leaves tasks still running | The loader was closed while the provider had not stopped using resources | Stop accepting work, drain/cancel tasks, clean up the plugin, and then close |

**A subtle pitfall: classpath containing two copies of the API.** With a parent-first URLClassLoader like in the example, a copy of the API accidentally packaged into plugin.jar usually still yields definition rights to the API in the parent; however, if using child-first loading, custom module layers, or an improperly delegating loader, the plugin can define a second copy itself. Therefore, you should still **avoid packaging plugin-api inside plugin JARs** and protect the contract namespace so it is delegated to the parent.

**The genuinely shared library problem:** Some libraries are part of the contract and must be shared (for example, an API DTO containing a third-party library type in its signature). In that case, they must have an agreed-upon compatible version in the API parent. Do not blindly isolate every library and forget that types appearing in signatures must preserve the same identity on both host and plugin sides.

**Security boundary:** URLClassLoader separates **namespaces/dependencies**, not a security sandbox. A Java plugin running in the same JVM can execute code, open files/network connections, create threads, and affect process state according to environment permissions. For untrusted plugins, proper process/OS/container boundaries and exchange protocols are required, rather than assuming a child class loader alone prevents dangerous behavior.

## 10. Mandatory Checks Before Deploying to a Plugin Runtime

- **Contract identity:** GreetingPlugin.class == Class.forName("com.example.spi.GreetingPlugin", false, pluginLoader) must be true for every plugin. Do the same for DTOs and callbacks that cross the boundary.
- **Dependency identity:** When intentionally using two versions with the same binary name, comparing the Class objects loaded from AlphaLoader and BetaLoader must show they are different.
- **JAR distribution:** The host compiles/depends only on the API; implementation JARs must not appear on the startup classpath if a dedicated loader is meant to load them.
- **ServiceLoader metadata:** Each plugin JAR has the exact resource META-INF/services/<service binary name> and a compatible provider class.
- **No internal type leakage:** Public methods in the SPI must not accept/return classes that exist only in a plugin-private loader. Convert to shared types before crossing the boundary.
- **Dependency overlap:** Audit same-named classes between plugins and the parent. Parent-first favors the parent; two children isolate a class only if the parent does not define it.
- **Lifecycle:** Test stop/reload, resource closing, instance/thread/TCCL release; define a policy when provider loading fails.
- **API compatibility:** Test plugins built against the versions of plugin-api that the host commits to support. Loader isolation does not automatically handle changes to signatures, constructors, DTOs, or contract semantics.

To verify the principle yourself, run the exact example in section 5, observe **API shared: true** and **Dependency isolated: true**, and then try putting alpha.jar on the host's runtime classpath or using a single URLClassLoader containing both JARs. Analyze why the same loader cannot define two versions of Utility with the same name in parallel, and why putting a dependency into the parent forfeits the benefit of parent-first isolation.

**References:** Java SE 17 API Specification for java.lang.ClassLoader, java.net.URLClassLoader, and java.util.ServiceLoader:
- https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html

The design mindset to uphold is **share what crosses the boundary; isolate what stays inside a plugin**: contracts and exchange types require a shared JVM identity; implementation classes and private dependencies require an independent namespace. The class loader is the mechanism that enforces that boundary, while managing compatibility, discovery, lifecycle, and security is the responsibility of the plugin host.
