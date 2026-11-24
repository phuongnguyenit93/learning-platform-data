# Handling Failing Providers and Limits of Continuing Iteration After Configuration Errors

In Java runtime-extensibility systems, ServiceLoader helps find providers implementing an SPI (Service Provider Interface). When one provider is broken, the host often wants to keep the remaining providers working. This can work in some situations, but **there is no guarantee that simply catching ServiceConfigurationError and calling Iterator.next() again will skip the failing provider**.

This lesson explains ServiceLoader's recovery boundaries on the classpath, compares fail-fast with bounded retry strategies, provides a Java 17+ experiment, and guides policy selection for real-world plugin systems.

## 1. Three Error Categories to Distinguish When Selecting Providers

A provider selection cycle typically passes through three stages:

1. **Discovery:** locate the META-INF/services/<fully-qualified-SPI-name> file, read, and parse the list of provider names.
2. **Loading and instantiation:** resolve the class, verify it properly implements the SPI, and instantiate the provider object.
3. **Execution:** invoke business methods, open resources, connect to services, or process data.

| Situation | Observable error | Nature |
| --- | --- | --- |
| Descriptor has invalid syntax or is unreadable | ServiceConfigurationError during iteration | Invalid service configuration |
| Descriptor points to a non-existent class or one not implementing the SPI | ServiceConfigurationError | Unloadable/unusable provider declaration |
| Classpath provider lacks a public no-arg constructor | ServiceConfigurationError | Fails the instantiation contract |
| Provider constructor throws an error | Usually ServiceConfigurationError with relevant cause | Failed to instantiate provider object |
| Provider constructs fine, but process() throws RuntimeException | The implementation's own RuntimeException, unless it throws another type | Error while using the provider, after discovery |
| No descriptor for the requested service | May iterate 0 providers without automatically throwing ServiceConfigurationError | No registered providers discovered |

**ServiceConfigurationError is a subclass of java.lang.Error**, not Exception. Doing catch (Exception ex) will not catch it. You can catch **the exact ServiceConfigurationError type** at the SPI iteration boundary to handle expected configuration errors, but you should not broadly catch Throwable or Error and treat everything as an ordinary plugin error: VirtualMachineError, ThreadDeath, and severe failures do not fit a "skip and keep trying" policy.

A provider that runs fine yet returns business-unsatisfactory results does not become a "configuration-error provider". Filtering by capability, priority, input format, or health checks must be designed separately after confirming the provider loaded.

## 2. ServiceLoader's Contract on Error Recovery

The Java SE 17 documentation clearly states:

- ServiceLoader.load(...) creates a loader object, but locating and instantiating providers is largely **lazy**. Calling load(...) alone does not prove all providers are valid.
- When using ServiceLoader.iterator(), both **hasNext() and next()** can throw ServiceConfigurationError if an error occurs while locating, loading, or instantiating a provider.
- If a traversal step fails, subsequent calls on the iterator make a **best-effort** attempt to locate/instantiate the next provider. **There is no general guarantee that it will recover.**
- With ServiceLoader.stream(), errors can also surface in operations that actually locate or load providers, including during terminal operations.

As a direct consequence, the following code has no basis for safe execution:

~~~java
// Anti-pattern: DO NOT use in programs requiring correctness.
while (iterator.hasNext()) {
    try {
        Service provider = iterator.next();
        use(provider);
    } catch (ServiceConfigurationError error) {
        // "Skip and continue" is not guaranteed by the API.
    }
}
~~~

There are at least three problems. First, **hasNext() sits outside try**, so errors from reading configuration still escape. Second, an error may prevent the iterator from advancing, causing repeated errors or premature termination. Third, swallowing errors makes the host claim plugins are healthy when the system is only partially running.

A corrected version with proper catch scope must still have a **retry limit**, error reporting, and a stopping condition. Without a bound, the loop could spin forever on the same error if the iterator fails to advance.

## 3. Two Primary Handling Policies

**Fail fast / fail closed:** a single ServiceConfigurationError halts loading the provider set; the host logs the cause and refuses to enable features depending on that provider set. Choose this when providers are mandatory components, the list must be complete, or misconfiguration makes results untrustworthy.

**Bounded best effort:** the host logs the error, retries calling the iterator up to a predefined step/error limit, still processes providers that successfully load, and finishes in a complete or partial state. Choose this when plugins are optional, can be independently disabled, and the product accepts skipping a broken plugin. This is a **recovery attempt**, not a promise that every valid provider behind a broken one will be found.

| System requirement | Appropriate policy | What must be verified |
| --- | --- | --- |
| Authorization, authentication, security policy, or mandatory processor | Fail closed | A provider set missing components cannot be treated as valid |
| Decorative plugins / optional features | Bounded best effort if controlled | Explicitly record rejected plugins; never skip silently |
| Multiple independently installed plugin JARs | Discover and validate per package, isolate loaders when architecture allows | One broken JAR must not obscure other packages |
| Reconfigurable and redeployable | Fix artifact/descriptor then create a new verified load session | reload() does not automatically fix old errors |
| Features with provider priority ordering | Explicitly decide whether fallback is allowed | Do not assume a broken provider is skipped only once |

## 4. Java 17+ Experiment: Good Provider, Broken-Constructor Provider, and Trailing Good Provider

The goal of the lab is to observe **where errors occur** and demonstrate that fail-fast outcomes are deterministic, whereas continuing iteration is merely best effort.

Directory layout from the lab/ root:

~~~text
lab/
├── src/
│   ├── api/demo/spi/Processor.java
│   ├── providers/demo/providers/Alpha.java
│   ├── providers/demo/providers/Broken.java
│   ├── providers/demo/providers/Omega.java
│   └── host/demo/host/Run.java
├── descriptors/
│   ├── good/META-INF/services/demo.spi.Processor
│   └── broken/META-INF/services/demo.spi.Processor
└── build/                        (created by the build command)
~~~

### 4.1. Defining the SPI

File **src/api/demo/spi/Processor.java**:

~~~java
package demo.spi;

public interface Processor {
    String id();
    String process(String value);
}
~~~

The interface is the contract provided by the host. Compiling providers references the exact API artifact, and at runtime the host puts the API on the shared classpath.

### 4.2. First Good Provider

File **src/providers/demo/providers/Alpha.java**:

~~~java
package demo.providers;

import demo.spi.Processor;

public final class Alpha implements Processor {
    public Alpha() {}

    @Override
    public String id() {
        return "alpha";
    }

    @Override
    public String process(String value) {
        return "A:" + value;
    }
}
~~~

### 4.3. Provider with a Failing Constructor

File **src/providers/demo/providers/Broken.java**:

~~~java
package demo.providers;

import demo.spi.Processor;

public final class Broken implements Processor {
    public Broken() {
        throw new IllegalStateException("constructor failed");
    }

    @Override
    public String id() {
        return "broken";
    }

    @Override
    public String process(String value) {
        return "B:" + value;
    }
}
~~~

Broken satisfies the **public no-arg constructor** requirement, but its constructor intentionally throws. This is a **provider instantiation** error, not a process-method error. For classpath provider configuration, ServiceLoader surfaces instantiation failures via ServiceConfigurationError; the original exception is visible in the cause chain.

### 4.4. Trailing Good Provider

File **src/providers/demo/providers/Omega.java**:

~~~java
package demo.providers;

import demo.spi.Processor;

public final class Omega implements Processor {
    public Omega() {}

    @Override
    public String id() {
        return "omega";
    }

    @Override
    public String process(String value) {
        return "Z:" + value;
    }
}
~~~

### 4.5. Two Independent Descriptor Files

File **descriptors/good/META-INF/services/demo.spi.Processor**:

~~~text
demo.providers.Alpha
demo.providers.Omega
~~~

File **descriptors/broken/META-INF/services/demo.spi.Processor**:

~~~text
demo.providers.Alpha
demo.providers.Broken
demo.providers.Omega
~~~

Each run places only **one** JAR containing a descriptor on the classpath. The descriptor uses the SPI's exact name; it lists providers by fully qualified class name, one per line. The broken package contains three names in order Alpha → Broken → Omega; Broken's failure may affect finding Omega depending on iterator state and how the failure occurs.

### 4.6. Host: Strict (Fail-Fast) and Bounded-Retry Modes

File **src/host/demo/host/Run.java**:

~~~java
package demo.host;

import demo.spi.Processor;
import java.util.Iterator;
import java.util.ServiceConfigurationError;
import java.util.ServiceLoader;

public final class Run {
    private static final int MAX_STEPS = 8;
    private static final int MAX_CONFIG_ERRORS = 2;

    public static void main(String[] args) {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: Run strict|bounded");
        }

        ServiceLoader<Processor> loader = ServiceLoader.load(Processor.class);

        switch (args[0]) {
            case "strict" -> strict(loader);
            case "bounded" -> bounded(loader);
            default -> throw new IllegalArgumentException(
                    "Unknown mode: " + args[0]);
        }
    }

    private static void use(Processor provider) {
        try {
            System.out.println(
                    "USE " + provider.id() + " -> " + provider.process("x"));
        } catch (RuntimeException ex) {
            System.out.println("PROCESS_ERROR: " + provider.id());
        }
    }

    private static void strict(ServiceLoader<Processor> loader) {
        try {
            for (Processor provider : loader) {
                use(provider);
            }
            System.out.println("DONE");
        } catch (ServiceConfigurationError error) {
            System.out.println("STOP CONFIG_ERROR");
            // In a real application: log both error and getCause().
        }
    }

    private static void bounded(ServiceLoader<Processor> loader) {
        Iterator<Processor> iterator = loader.iterator();
        int configErrors = 0;

        for (int step = 0; step < MAX_STEPS; step++) {
            Processor provider;
            try {
                // BOTH hasNext and next can report configuration errors.
                if (!iterator.hasNext()) {
                    System.out.println("DONE");
                    return;
                }
                provider = iterator.next();
            } catch (ServiceConfigurationError error) {
                configErrors++;
                System.out.println("CONFIG_ERROR #" + configErrors);

                if (configErrors >= MAX_CONFIG_ERRORS) {
                    System.out.println("STOP ERROR_LIMIT");
                    return;
                }
                continue; // Retry only; NO guarantee that the error can be skipped.
            }

            use(provider);
        }

        System.out.println("STOP STEP_LIMIT");
    }
}
~~~

Notable details in the code:

- **strict**'s try/catch wraps the entire for-loop; thus errors raised in both iterator.hasNext() and iterator.next() are caught.
- **bounded**'s try/catch wraps both iterator calls; it does not catch all Errors indiscriminately.
- MAX_CONFIG_ERRORS prevents infinite looping if the iterator keeps reporting errors; MAX_STEPS is a **second bound** to avoid overly long loops even without consecutive config errors. These are examples for a small plugin set, not optimal default thresholds for every system.
- Errors from process() are separated into PROCESS_ERROR. A provider that initializes fine but fails to process data must not be mistaken for a descriptor error.
- The code prints short messages for deterministic stdout. In real applications, log the exception, root cause, artifact info, and provider-disabling decision.

**Intentional limitation:** If provider.id() itself throws a RuntimeException inside use()'s catch block, calling provider.id() in the catch branch could throw again. In real applications, fetch the verified ID from metadata/registration beforehand instead of relying on calling a method on the failing provider itself. The lab's providers all have stable id() implementations to keep focus on ServiceConfigurationError.

### 4.7. Building and Running from Release JARs

From the lab/ directory, using JDK 17+ and a bash/POSIX shell:

~~~bash
mkdir -p build/api build/providers build/host dist

javac -encoding UTF-8 -d build/api src/api/demo/spi/Processor.java
jar --create --file build/api.jar -C build/api .

javac -encoding UTF-8 -cp build/api.jar -d build/providers src/providers/demo/providers/Alpha.java src/providers/demo/providers/Broken.java src/providers/demo/providers/Omega.java

javac -encoding UTF-8 -cp build/api.jar -d build/host src/host/demo/host/Run.java

jar --create --file dist/good.jar -C build/providers . -C descriptors/good .
jar --create --file dist/broken.jar -C build/providers . -C descriptors/broken .

java -cp "build/host:build/api.jar:dist/good.jar" demo.host.Run strict
java -cp "build/host:build/api.jar:dist/broken.jar" demo.host.Run strict
java -cp "build/host:build/api.jar:dist/broken.jar" demo.host.Run bounded
~~~

On Windows when invoking Java directly from PowerShell/CMD, the classpath separator is **;** instead of **:**. The mkdir -p syntax and line continuations above are for bash.

Each JAR contains the full classes of Alpha, Broken, and Omega; the only difference between the two builds is **the list of provider names in META-INF/services**. This cleanly isolates the effect of service configuration from class compilation.

Command to inspect the JARs:

~~~bash
jar --list --file dist/good.jar
jar --list --file dist/broken.jar
~~~

You should see the **META-INF/services/demo.spi.Processor** entry and the .class files under demo/providers. Merely having classes in the JAR is not enough: ServiceLoader only knows about providers declared for the exact SPI in the descriptor.

## 5. Interpreting the Experimental Results

**Running strict with good.jar** produces exact stdout:

~~~text
USE alpha -> A:x
USE omega -> Z:x
DONE
~~~

**Running strict with broken.jar** produces exact stdout:

~~~text
USE alpha -> A:x
STOP CONFIG_ERROR
~~~

Alpha is instantiated and processed first. Upon reaching Broken, its constructor throws IllegalStateException; the iterator's attempt to instantiate that provider fails and the strict loop stops. Omega is declared in the file, yet **is not used** in the strict run because the host decided to terminate immediately after a configuration error.

**Running bounded with broken.jar** may produce the following illustrative output on a Java 17 runtime:

~~~text
USE alpha -> A:x
CONFIG_ERROR #1
USE omega -> Z:x
DONE
~~~

In that scenario, the iterator advanced past Broken and continued to find Omega. **Do not treat those four lines as guaranteed output across every runtime, every error type, or every config file.** The API contract only states best effort. For unrecoverable errors, multiple consecutive errors may occur; upon hitting MAX_CONFIG_ERRORS, the program prints STOP ERROR_LIMIT. If it fails to reach the end within MAX_STEPS, it prints STOP STEP_LIMIT. Both stopping branches must be treated as an **incomplete** provider-set state.

What can be asserted independently of implementation details is: bounded will not try more than MAX_STEPS iterations, will stop after MAX_CONFIG_ERRORS caught configuration errors, and makes no promise that providers behind Broken are guaranteed to load.

One subtlety: **hasNext() can also report an error** (for instance when reading a corrupted descriptor file), not only next() when instantiating Broken. In some cases, even determining "are there any providers left?" cannot complete. Hence there is no guarantee that a specific provider will always exist to "skip" to after encountering ServiceConfigurationError.

## 6. Provider Selection and Fallback Mechanisms: What Is Controllable?

Many hosts do not need every provider; they just want one matching implementation, such as by ID, media type, or capability. There are three distinct options:

**Selection after instantiation:** iterate each provider and call id() or supports(...), then pick the first provider meeting the criteria. This can trigger side effects in constructors of preceding providers and can be blocked by configuration errors in unneeded providers.

**Filtering by provider type metadata:** ServiceLoader.stream() returns ServiceLoader.Provider<S>. You can inspect Provider.type() to check the declared type before calling Provider.get() to instantiate; this sometimes avoids instantiating unselected providers. However, locating and resolving the type itself can still throw ServiceConfigurationError. stream().filter(...).findFirst() **does not turn a broken descriptor set into an always-safely-filterable collection**.

**Reading a host-controlled registry/manifest before putting JARs into a loader:** when each plugin carries independently verified metadata, the host can decide which loader to create and which plugins to load. This is a clearer control boundary for products requiring provider selection by version, priority, permissions, and compatibility.

An example selecting a provider by **class name** using stream() for illustration only (not a standalone program):

~~~java
ServiceLoader<Processor> loader = ServiceLoader.load(Processor.class);

try {
    Processor selected = loader.stream()
            .filter(p -> p.type().getName().equals("demo.providers.Omega"))
            .findFirst()
            .orElseThrow()
            .get();
    System.out.println(selected.process("x"));
} catch (ServiceConfigurationError error) {
    // Scanning metadata or Provider.get() can still fail.
    // Record the plugin set as invalid instead of assuming everything was filtered.
}
~~~

This snippet assumes the lab's Processor interface and corresponding classes exist. If no provider is found, orElseThrow() throws NoSuchElementException; this is distinct from ServiceConfigurationError. Likewise, if selected.process("x") throws RuntimeException, that is an implementation execution error, not automatically caught by the catch block above.

**Do not use stream().findFirst() as an “automatic fallback” after configuration errors.** If fetching the first provider fails, the terminal operation can terminate with an exception; there is no guarantee of automatically excluding the failing provider and trying the next element.

## 7. When to Continue, When to Stop?

Below is a risk-based boundary:

| Observed outcome | Assessment | Action |
| --- | --- | --- |
| An optional provider throws RuntimeException while processing input, but the host already knows its ID and contract | Provider-specific business/lifecycle error | May mark provider unhealthy, use a **defined** fallback, log, and limit retries |
| ServiceConfigurationError while iterating a mandatory SPI | Provider-set configuration is untrustworthy | Halt feature initialization, report config error, and require artifact fix |
| ServiceConfigurationError in an optional plugin set | Usable providers might remain, but iterator does not promise recovery | Continue only if policy allows degraded mode, with bounds and notifications |
| Multiple consecutive config errors, or the same error repeating | Risk of failing to make progress | Stop by error budget/step budget; mark discovery incomplete |
| Class linkage/version errors such as NoClassDefFoundError, NoSuchMethodError | Likely incompatible JAR/class loader set | Check dependencies/API/classpath; do not catch Error broadly as a normal error |
| Loss of plugin integrity, signature, permissions, or security policy | Not merely a ServiceLoader issue | Refuse to load per security policy; do not fall back to arbitrary plugins |

Especially in systems with multiple plugins from different teams, **"continuing after an error" does not mean "having inspected the entire list"**. Outcome reports should distinguish loaded, rejected, failed discovery, and not examined. A generic SUCCESS status when the full provider set has not been verified often misleads.

If the business contract requires exactly one implementation capable of handling the request, selection should return a structured result such as selected, unsupported, invalid configuration, or ambiguous selection. Never let an empty catch implicitly decide that a missing provider is valid.

## 8. Error-Handling Patterns for Real Hosts

The lab uses System.out for readability. When implementing in production, structure the steps as follows:

1. **Identify artifact and load source:** log service, plugin ID/version if metadata exists, JAR path, hash/release source, and chosen class loader.
2. **Pre-load verification:** check file existence, exact descriptor name, API version, dependencies, and compatibility conditions. Static preflight does not replace runtime discovery, but it catches many packaging errors early.
3. **Decide error-handling policy upfront:** mandatory SPI → fail closed; optional SPI → bounded best effort with partial status.
4. **Catch errors at the right boundaries:** ServiceConfigurationError around hasNext()/next(); process() errors around provider calls; I/O and timeouts per dedicated APIs; avoid catching Throwable.
5. **Preserve full cause:** record stack trace and getCause() when present, along with the stage type. Do not merely log a CONFIG_ERROR label and discard details.
6. **Stop under explicit budgets:** total configuration errors, iteration steps, and overall deadline (if needed). The step budget in the demo does not stop a single hanging call; production may need process isolation or timeouts at appropriate boundaries.
7. **Never use a provider that failed initialization:** a provider that failed to instantiate cannot be added to the registry. For providers that instantiated yet failed health checks, close resources and unregister per lifecycle.
8. **Return startup status with completeness level:** fully ready / degraded / failed, accepted or rejected providers, reasons, and remediation actions.

An independent plugin loader design per package can shrink the blast radius of errors: each JAR is inspected, loaded, and tracked separately. However, merely creating multiple URLClassLoaders is insufficient for isolation if the parent loader still sees every plugin, because class/resource lookups can still delegate through the parent. The host must control **parent classpath, SPI ownership, dependencies, and delegation rules**. Also, do not close a loader while providers remain active; keep the loader alive until plugins stop, cancel callbacks, and release resources.

For **untrusted** third-party code, class loaders are not a security sandbox. If a plugin can execute arbitrary code, consider process separation and privilege restriction. Catching ServiceConfigurationError cannot guarantee JVM safety if a plugin executes side effects during initialization.

## 9. Easily Misunderstood Behaviors of ServiceLoader

### 9.1. Caching and reload()

ServiceLoader maintains a cache of already-loaded providers; a subsequent iterator() call may return cached instances before continuing to search for unloaded providers. Therefore, retrying a fresh iteration with **the same ServiceLoader** does not mean "starting from a clean slate". Distinguish retrying to observe from retrying after fixing configuration.

Calling reload() clears ServiceLoader's provider cache, yet **does not repair a broken descriptor/JAR**, does not automatically unload classes, and does not guarantee errors won't recur. Iterators or streams started before reload() must be discarded; using an old iterator after reload() can throw ConcurrentModificationException. Do not call reload() inside catch on every ServiceConfigurationError: that can simply loop the host back into the same broken configuration.

For hot-reloading plugins, ensure the old loader has no live threads, callbacks, references, or resources; then create a new loader/ServiceLoader for the verified artifact. That is lifecycle engineering, not a self-healing feature of ServiceLoader.

### 9.2. Late Errors Due to Lazy Loading

The following statement has not verified the full provider set:

~~~java
ServiceLoader<Processor> loader = ServiceLoader.load(Processor.class);
System.out.println("ServiceLoader created");
~~~

Part of the work only occurs when iterator.hasNext(), iterator.next(), a stream terminal operation, or Provider.get() is called. If a startup check only calls load(...) and reports success, the system can fail on the first request.

### 9.3. Descriptor Configuration and Syntax Errors

On the classpath, the descriptor must reside at **META-INF/services/<fully-qualified-SPI>** and contain valid binary names of implementations. File read errors, bad formatting, wrong class names, incompatible classes, or missing constructors can all cause ServiceConfigurationError during iteration. Do not infer that every error occurs when next() instantiates an object: reading the descriptor can raise an error right in hasNext().

If a descriptor contains a malformed line, valid implementations on subsequent lines are **not guaranteed** to be reached. This is precisely why a bounded approach must have a failure branch and cannot promise complete recovery.

### 9.4. Differences Between Classpath and Module Path

On the classpath, providers are typically declared via META-INF/services; provider classes need a public no-arg constructor so ServiceLoader can instantiate them. On the JPMS module path, module descriptors use uses/provides; provider factory methods and other rules may also appear. Therefore, when logs mention a missing constructor, check the **actual deployment mode** before applying a classpath-specific fix.

### 9.5. Do Not Mutate the Loader While Multiple Threads Iterate

ServiceLoader instances are **not safe for concurrent access by multiple threads**. Do not share a ServiceLoader being reloaded/iterated across threads and treat every ConcurrentModificationException as a provider bug. If a shared registry is needed, build a snapshot of verified providers and manage snapshot replacement with explicit synchronization/lifecycle.

## 10. Diagnostic Table and Corresponding Actions

| Symptom | Check immediately | Action |
| --- | --- | --- |
| 0 providers with no ServiceConfigurationError | Exact SPI/descriptor name? Is the JAR on the classpath/loader? | Fix registration and classpath |
| Error thrown from hasNext() | Corrupted descriptor, resource read failure, loader cannot access file | Inspect stack trace/path; avoid while loops with hasNext outside try |
| Error thrown from next() | Provider class, SPI type, public no-arg constructor, dependencies, constructor failure | Fix class/packaging/API compatibility; log cause |
| Alpha runs then Omega is missing | Mid-list provider caused an error; host failed fast or iterator did not recover | Distinguish stopping policy from API recovery capability |
| Same error repeats endlessly when calling next | Iterator not advancing / encountering persistent configuration error | Stop by max errors/max steps; fix package instead of infinite retry |
| Provider loads fine but process fails | Dedicated resource, runtime state, input, I/O/remote service | Catch provider-specific error, mark unhealthy, or use defined fallback |
| Identical error remains after reload | Config/JAR package not yet fixed; old loader still in use | Verify artifact, create a new load session per lifecycle |
| stream().filter(...).findFirst() fails before returning desired provider | Error occurred during lazy discovery or type loading | Catch ServiceConfigurationError at selection boundary; do not trust filter to bypass errors |
| ClassCastException or ServiceConfigurationError "not a subtype" | SPI loaded by two class loaders or implementation genuinely wrong type | Pin shared SPI, check class loaders/dependency versions |
| NoClassDefFoundError / NoSuchMethodError inside plugin | Missing dependency or runtime version mismatch | Inspect dependency graph and actually loaded classes |

To diagnose, run jar --list --file plugin.jar to inspect META-INF/services entries and .class files; run javap -public -classpath plugin.jar <class name> to inspect constructor signatures. When suspecting conflicts, check the SPI artifact at runtime and the class loader defining each class. Never lump all errors under a single "plugin broken" message.

## 11. Exercises to Verify Recovery Limits

**Exercise A — change descriptor order:** in the broken descriptor, place Broken before Alpha. Predict strict: STOP CONFIG_ERROR may appear before any USE line. With bounded, observe whether providers after Broken are still found; the result does not alter the API's best-effort contract.

**Exercise B — fix Broken:** remove the exception from the constructor and rebuild the JAR. Now strict can iterate all three providers; rerun in a fresh Java process so as not to confuse with previously created caches/loaders.

**Exercise C — intentional class typo:** change demo.providers.Broken to demo.providers.DoesNotExist; run strict and bounded. Use the stack trace to confirm the error is a missing provider class, distinct from the main experiment's constructor failure. Do not assume retries behave identically across the two error types.

**Exercise D — invalid descriptor format:** add a line that is not a valid binary name, such as "bad provider name!". Descriptor reading/parsing errors may happen right when the iterator searches for providers; add logs to distinguish hasNext() from next(). Do not treat behavior observed on one JDK version as a universal guarantee.

**Exercise E — business-error provider:** create a provider with a valid constructor whose process() throws IllegalArgumentException. Compare PROCESS_ERROR with CONFIG_ERROR and how the host decides fallback. Crucially, do not turn a method execution error into evidence of a broken descriptor.

**Completion criteria:** be able to explain (1) why catch (Exception) does not catch ServiceConfigurationError, (2) why errors from both hasNext() and next() must be caught, (3) the exact meaning of best effort and retry bounds, (4) the difference between an initialization-failing provider and a business-failing provider, (5) when to choose fail closed vs. degraded mode, and (6) why reload() is not a fix for bad configuration.

**Reference:** [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html), especially the sections on Errors, iterator(), stream(), and reload(). The core principle is: **continuing can help, yet recovery is not guaranteed; the host must bound, record, and handle incomplete load states**.