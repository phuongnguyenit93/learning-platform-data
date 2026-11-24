# Defining a Service and Creating Multiple Independent Implementations on the Classpath

When building an extensible Java application, we often want to add a new way of handling logic without having to modify every place that uses that functionality. One design approach is to **define a service contract** and let multiple independent libraries implement the contract. On the Java classpath, `ServiceLoader` helps the application discover registered implementations (service providers).

This lesson builds **one SPI, two providers in two separate JARs, and an application that calls them**. Through it, you will see what is shared at compile time, what can be added or removed at runtime, and the conditions required for Java to actually find the providers.

## 1. The Model to Understand Before Writing Code

Suppose the application needs greetings in multiple languages. An approach that depends directly on implementations usually looks like this:

```java
// Illustrates hardcoded logic, not a complete program.
if (language.equals("en")) {
    return new EnglishGreetingService().greet(name);
}
return new VietnameseGreetingService().greet(name);
```

Every time a language is added, the class-selection block risks needing modification. Moreover, the application must know the implementation class names at compile time.

The SPI model separates three responsibilities:

1. **Service contract:** describes the functionality and rules that all providers must follow.
2. **Independent providers:** each provider implements the same contract while deciding its own algorithm and packaging; provider A does not need to import provider B.
3. **Consumer and discovery mechanism:** the application knows only the contract, letting `ServiceLoader` find providers that are present and registered in the runtime environment.

```text
                 Depends on shared contract
                              |
                 +------------v------------+
                 | GreetingService (SPI)   |
                 | languageTag(), greet()  |
                 +------------+------------+
                              |
          +-------------------+-------------------+
          |                                       |
+---------v---------------+          +------------v------------+
| greeting-en.jar         |          | greeting-vi.jar         |
| EnglishGreetingService  |          | VietnameseGreetingService|
| + META-INF/services     |          | + META-INF/services     |
+-------------------------+          +-------------------------+
          |                                       |
          +-------------------+-------------------+
                              |
             ServiceLoader finds providers
                              |
                 +------------v------------+
                 | greeting-app.jar        |
                 | Main uses SPI contract  |
                 +-------------------------+
```

The `GreetingService` interface is the **SPI for provider authors** and simultaneously the service type that consumers can call. The terms API/SPI describe *the role in using the contract*, and do not require each role to have a separate interface.

**"Independent" here means:** the two providers have their own source code, release lifecycle, and JARs; they depend only on the shared contract, not on each other. This does not mean providers are process-isolated, automatically hot-updated, or exempt from SPI version management.

## 2. Designing the Service Contract

Before writing providers, we need to determine what must remain stable. In this example:

- `languageTag()` returns a language code so the consumer can identify the service. Each provider uses a unique code, such as `en` or `vi`.
- `greet(name)` takes a user's name and returns a greeting.
- For the demo to produce clear output, the convention is that `name` is non-`null` and non-empty; the returned greeting is non-`null`. This is a **contract convention**; a Java interface by itself does not enforce these conditions.
- Providers do not maintain mutable state between calls, so instances can be reused in this example. For services with state or resources, the contract must specify thread safety and how resources are closed.

File `contract/src/com/example/spi/GreetingService.java`:

```java
package com.example.spi;

public interface GreetingService {
    String languageTag();

    String greet(String name);
}
```

This is a valid **service type** for `ServiceLoader`. The interface specifies only the operations that implementations must provide. It does not know about the English class, the Vietnamese class, the directory storing JARs, or the provider selection mechanism. Keeping the contract small with clear semantics helps independent provider authors fulfill the exact same expectations.

## 3. Project Structure: Four Separate Components

To make it easy to follow, we use four source directories. You can create the following file tree in the `spi-demo` directory:

```text
spi-demo/
├── contract/
│   └── src/com/example/spi/GreetingService.java
├── provider-en/
│   ├── src/com/example/provider/en/EnglishGreetingService.java
│   └── resources/META-INF/services/com.example.spi.GreetingService
├── provider-vi/
│   ├── src/com/example/provider/vi/VietnameseGreetingService.java
│   └── resources/META-INF/services/com.example.spi.GreetingService
└── app/
    └── src/com/example/app/Main.java
```

When compiled, we will produce four JARs:

| JAR | What does it contain? | Compile-time dependencies |
|---|---|---|
| `greeting-spi.jar` | `GreetingService` interface | No provider dependencies |
| `greeting-en.jar` | English provider and its registration | `greeting-spi.jar` |
| `greeting-vi.jar` | Vietnamese provider and its registration | `greeting-spi.jar` |
| `greeting-app.jar` | Consumer `Main` | `greeting-spi.jar` |

The two providers **do not need to see each other's code or JAR** at compile time. The consumer also does not need to import concrete provider classes. This is the most important dependency boundary in this lesson.

## 4. Two Independent Implementations

### 4.1. English Provider

File `provider-en/src/com/example/provider/en/EnglishGreetingService.java`:

```java
package com.example.provider.en;

import com.example.spi.GreetingService;

public final class EnglishGreetingService implements GreetingService {
    @Override
    public String languageTag() {
        return "en";
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

`EnglishGreetingService` implements the two SPI methods on its own. Because the class is `public` and declares no explicit constructor, Java provides a no-argument constructor with public access, satisfying how classpath providers are instantiated in this example.

### 4.2. Vietnamese Provider

File `provider-vi/src/com/example/provider/vi/VietnameseGreetingService.java`:

```java
package com.example.provider.vi;

import com.example.spi.GreetingService;

public final class VietnameseGreetingService implements GreetingService {
    @Override
    public String languageTag() {
        return "vi";
    }

    @Override
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

This class knows only `GreetingService`. It does not `extends`, `imports`, or call `EnglishGreetingService`. The two providers are allowed to use different internal libraries as long as they adhere to the shared contract.

**Important distinction:** `implements GreetingService` only satisfies the Java type requirement. For `ServiceLoader` to *find* the provider on the classpath, we still must register the class using a service resource.

## 5. Registering Each Provider via `META-INF/services`

The registration mechanism on the **classpath** uses a configuration file with the exact path:

```text
META-INF/services/<fully-qualified-name-of-service-type>
```

In this example, both JARs have a file at the same path:

```text
META-INF/services/com.example.spi.GreetingService
```

But **the contents of each file differ**.

Contents of `provider-en/resources/META-INF/services/com.example.spi.GreetingService`:

```text
com.example.provider.en.EnglishGreetingService
```

Contents of `provider-vi/resources/META-INF/services/com.example.spi.GreetingService`:

```text
com.example.provider.vi.VietnameseGreetingService
```

`ServiceLoader` reads service configuration resources visible to the class loader. When both JARs are on the classpath together, both resources with the same name are still discovered; **you do not merge the two files into one or keep only one file**. Each JAR carries its own registration. This is what makes adding and removing provider JARs convenient.

Rules to remember:

- The file name after `services/` must be the fully qualified name of the **service interface**, not the provider name.
- Each content line lists the fully qualified name of the **provider class**. There can be multiple providers in one file, but this example intentionally places one provider per JAR.
- Do not add `.txt`, `.java`, or `.properties` extensions to the registration file.
- On the classpath, the provider class must implement the service type and have a public no-argument constructor suitable for `ServiceLoader`'s instantiation mechanism.
- The configuration file must be packaged **inside the provider JAR**, at the exact root path `META-INF/services/...`. Leaving the file outside the JAR without being in a discovered resource path will not be enough.
- Specifying a wrong class name, an incompatible type, or an instantiation error can cause `ServiceConfigurationError` when iterating over providers.

There is no need to use `Class.forName(...)`, no need for manual registration via `new` in the consumer, and no need to change the SPI contract when adding a new implementation that conforms to the existing contract.

## 6. Writing a Consumer That Knows Only the Contract

File `app/src/com/example/app/Main.java`:

```java
package com.example.app;

import com.example.spi.GreetingService;
import java.util.Map;
import java.util.ServiceLoader;
import java.util.TreeMap;

public final class Main {
    public static void main(String[] args) {
        Map<String, GreetingService> byLanguage = new TreeMap<>();

        for (GreetingService provider : ServiceLoader.load(GreetingService.class)) {
            String language = provider.languageTag();

            GreetingService previous = byLanguage.putIfAbsent(language, provider);
            if (previous != null) {
                throw new IllegalStateException(
                        "Duplicate language tag: " + language);
            }
        }

        if (byLanguage.isEmpty()) {
            throw new IllegalStateException("No greeting providers found");
        }

        byLanguage.forEach((language, provider) ->
                System.out.println(language + " => " + provider.greet("Linh")));
    }
}
```

The consumer code does not import `EnglishGreetingService` or `VietnameseGreetingService`. It requests the service via `GreetingService.class`, iterates over discovered providers, checks for duplicate language codes, and then uses the `greet()` method.

Because `ServiceLoader` **does not promise provider ordering**, the example puts them into a `TreeMap` to print in lexicographical order of language codes. This ensures output of `en` then `vi`, even if the actual discovery order differs. Using `putIfAbsent` also avoids silently overwriting when two providers declare the same `languageTag()`.

For a large application, you can write a coordinator class or facade so the consumer only calls `getGreeting("vi")`. `ServiceLoader` is the provider discovery mechanism; the application itself decides how to select, prioritize, handle duplicates, and report errors.

## 7. Compiling, Packaging into JARs, and Running on Java 17+

The example does not use Maven/Gradle in order to directly clarify classpath relationships. You need **JDK 17 or higher** installed with the `javac`, `jar`, and `java` commands available. Run from the `spi-demo` root directory; make sure the files above have been created properly.

### 7.1. Commands on Windows PowerShell

```powershell
New-Item -ItemType Directory -Force -Path out/spi,out/en,out/vi,out/app,dist | Out-Null

javac -encoding UTF-8 -d out/spi contract/src/com/example/spi/GreetingService.java
jar --create --file dist/greeting-spi.jar -C out/spi .

javac -encoding UTF-8 --class-path dist/greeting-spi.jar -d out/en provider-en/src/com/example/provider/en/EnglishGreetingService.java
jar --create --file dist/greeting-en.jar -C out/en . -C provider-en/resources .

javac -encoding UTF-8 --class-path dist/greeting-spi.jar -d out/vi provider-vi/src/com/example/provider/vi/VietnameseGreetingService.java
jar --create --file dist/greeting-vi.jar -C out/vi . -C provider-vi/resources .

javac -encoding UTF-8 --class-path dist/greeting-spi.jar -d out/app app/src/com/example/app/Main.java
jar --create --file dist/greeting-app.jar -C out/app .

java --class-path 'dist/greeting-spi.jar;dist/greeting-en.jar;dist/greeting-vi.jar;dist/greeting-app.jar' com.example.app.Main
```

### 7.2. Commands on Linux/macOS

With the same source files, on Unix systems use `:` to separate classpath elements:

```bash
mkdir -p out/spi out/en out/vi out/app dist

javac -encoding UTF-8 -d out/spi contract/src/com/example/spi/GreetingService.java
jar --create --file dist/greeting-spi.jar -C out/spi .

javac -encoding UTF-8 -cp dist/greeting-spi.jar -d out/en provider-en/src/com/example/provider/en/EnglishGreetingService.java
jar --create --file dist/greeting-en.jar -C out/en . -C provider-en/resources .

javac -encoding UTF-8 -cp dist/greeting-spi.jar -d out/vi provider-vi/src/com/example/provider/vi/VietnameseGreetingService.java
jar --create --file dist/greeting-vi.jar -C out/vi . -C provider-vi/resources .

javac -encoding UTF-8 -cp dist/greeting-spi.jar -d out/app app/src/com/example/app/Main.java
jar --create --file dist/greeting-app.jar -C out/app .

java -cp "dist/greeting-spi.jar:dist/greeting-en.jar:dist/greeting-vi.jar:dist/greeting-app.jar" com.example.app.Main
```

Standard output when both providers are present and the terminal displays Unicode:

```text
en => Hello, Linh!
vi => Xin chào, Linh!
```

In both sets of commands:

1. `greeting-spi.jar` is compiled **first** because the other three components depend on the contract.
2. Each provider is compiled with only `greeting-spi.jar` on the compile classpath; the other provider's JAR is not needed.
3. `jar -C ... . -C provider-.../resources .` puts both the compiled classes and the `META-INF/services/...` resource into the same JAR.
4. The consumer is compiled **only with the SPI contract**, without needing to know about provider JARs yet.
5. At runtime, the classpath contains the contract, app, and **both provider JARs** so `ServiceLoader` sees all services.

To verify that the registration contents actually made it into the JAR, run:

```powershell
jar --list --file dist/greeting-en.jar
jar --list --file dist/greeting-vi.jar
```

In the listing of **both JARs**, `META-INF/services/com.example.spi.GreetingService` and the corresponding class must appear. The order of entries printed by `jar --list` is not part of this example's contract.

## 8. Experimenting with Changing the Classpath Without Modifying the Consumer

### Experiment A: Including Only the English Provider

On Windows:

```powershell
java --class-path 'dist/greeting-spi.jar;dist/greeting-en.jar;dist/greeting-app.jar' com.example.app.Main
```

Output:

```text
en => Hello, Linh!
```

On Linux/macOS replace `;` in the classpath with `:`. The `Main.java` source code and consumer JAR **do not change**: only the runtime environment lacks `greeting-vi.jar`, so the service list has one provider.

### Experiment B: Having No Providers at All

On Windows:

```powershell
java --class-path 'dist/greeting-spi.jar;dist/greeting-app.jar' com.example.app.Main
```

`ServiceLoader` finds no providers through this classpath. `byLanguage` is empty, so the program throws `IllegalStateException` with the message:

```text
No greeting providers found
```

This is an **exception message**, not a stdout line printed by the program; Java also outputs a stack trace on stderr. In a real product, you must explicitly choose a policy for missing providers: fail early, default service, or required configuration.

### Experiment C: Adding a New Provider

You can create `FrenchGreetingService implements GreetingService`, use the code `fr`, package a separate `greeting-fr.jar` containing the class and `META-INF/services/com.example.spi.GreetingService`, and **add this JAR to the classpath at launch**.

If the contract does not change and the provider follows the rules, the compiled consumer still runs without needing imports, editing a `switch`, or recompiling `Main.java`. Remember that "adding a JAR to a new launch command" is different from "dropping a JAR into a directory while the JVM is running": the default classpath does not automatically update to hot-load new plugins.

## 9. What Really Happens When `ServiceLoader` Runs?

For a program run with the **classpath** like this example:

1. `Main` requests `ServiceLoader.load(GreetingService.class)`.
2. The loading mechanism uses the appropriate class loader (the single-parameter overload uses the thread's context class loader) to look up `META-INF/services/com.example.spi.GreetingService` resources.
3. When the program iterates over providers, `ServiceLoader` reads the declarations and loads/instantiates provider classes using the classpath mechanism.
4. The returned objects have type `GreetingService` and are called by the consumer via the two interface methods.

The discovery/instantiation process is usually **lazy**: calling `load` does not pre-instantiate all providers. Iterating with `for` in `Main` is what causes providers to be used. A `ServiceLoader` instance caches already-loaded providers; `reload()` refreshes the cache of that loader object, but **does not add JARs to the classpath or replace already-loaded classes**.

You should not share a single `ServiceLoader` instance across multiple threads without managing synchronization yourself because `ServiceLoader` is not guaranteed to be thread-safe. `ServiceLoader` is also **not a dependency injection container**, does not automatically validate business logic of methods, and does not provide security isolation for provider code.

This lesson applies the **classpath** model. With the Java Platform Module System (JPMS), a named module typically declares `uses` and `provides ... with ...` in `module-info.java`. That is a different registration mechanism; do not confuse classpath JAR packaging here with module path configuration.

## 10. Common Errors and How to Diagnose Them

| Symptom | Common Cause | Check or Resolution |
|---|---|---|
| Provider not found despite class existing | Provider JAR is not on the runtime classpath, or the registration resource is missing | Check `java -cp` and `jar --list --file ...` |
| One provider missing when multiple JARs exist | Only one JAR was put on the classpath or one JAR is missing `META-INF/services` | Verify each JAR packages metadata independently |
| `ServiceConfigurationError` during iteration | Wrong class name in registration file, provider has wrong type, cannot be instantiated | Check fully qualified name, `implements`, visibility, constructor, and error cause |
| `ClassNotFoundException`/`NoClassDefFoundError` | Missing contract JAR or provider dependencies at runtime | Verify all dependencies on the classpath |
| "Not a subtype" in configuration error | Provider does not actually implement the exact `GreetingService`, sometimes because class loaders loaded two different copies of the same interface | Check class loaders and unify the artifact containing the SPI |
| Results not in expected order | Relied on `ServiceLoader` provider discovery order | Select/sort by an explicit key such as `TreeMap` |
| Two providers have the same `languageTag()` | Identification contract does not guarantee uniqueness | Detect duplicates and define handling, such as `putIfAbsent` |
| Added JAR not seen by running JVM | Current classpath/class loader does not update dynamically | Restart or design a dedicated dynamic plugin/class loader mechanism |

**Version compatibility is also part of the design.** If an SPI is upgraded by adding a new abstract method, older providers may no longer be compatible when called; you need version management and a contract evolution strategy. Compatibility checks must examine method signatures, result semantics, exceptions, and lifecycle.

**Security:** providers run in the application's JVM with corresponding access capabilities; going through an SPI does not automatically create a sandbox. Only load trusted provider JARs or design genuine isolation layers if running untrusted code is required.

## 11. Criteria for a Good Extensible Service

When designing a new SPI, ask yourself:

- **Contract:** do the consumer and provider agree on inputs, outputs, errors, immutability/thread safety, and responsibility boundaries?
- **Independence:** does each provider compile needing only the SPI and its own dependencies, without referencing other providers?
- **Registration:** does each JAR carry its own proper `META-INF/services` file and can the provider class be instantiated according to the contract?
- **Discovery:** does the application know what to do when no provider exists, when a provider fails, when there are multiple providers, or when codes collide?
- **Testing:** can it run with 0, 1, and multiple providers by changing the classpath without modifying the consumer?
- **Release:** does the SPI contract have version management and a compatibility test suite for external development teams' providers?

## 12. Reinforcement Exercises

1. **Create a third provider:** implement `GreetingService` for the `fr` code in a separate JAR. Compile it with only `greeting-spi.jar`, package the service resource, and add the new JAR to the run command. Predict why `Main` does not need to be recompiled.
2. **Controlled registration break:** remove the `META-INF/services/...` file from the packaging of `greeting-vi.jar` and run again. Distinguish between "class present in JAR" and "declared provider".
3. **Test duplicate code error:** create another provider returning `"en"` in `languageTag()`. Explain why `Main` reports a duplicate error instead of silently overwriting. Replace it with a rule-based priority selection policy if the product allows multiple providers in the same group.
4. **Mark dependencies:** draw compile-time arrows from the app and each provider to `greeting-spi.jar`; then list the JARs that must be on the runtime classpath. How do these two diagrams differ?
5. **Extended discussion:** when is a small SPI interface like this example sufficient, and when is an additional contract needed for versioning, initialization, resource closing, configuration, errors, and security?

Understanding how to define a service type, package each implementation, and register providers onto the classpath is the foundation for building extension points in Java. The core point is that **providers are independent of each other yet adhere to a single contract**, while the consumer depends only on the contract and decides how to use the discovered providers.