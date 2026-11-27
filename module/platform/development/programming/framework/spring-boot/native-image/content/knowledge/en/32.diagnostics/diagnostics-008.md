# Class Initialization Errors and Invalid Objects in the Image Heap

## 1. Understand the Error Before Changing Configuration

In the **SPRING_BOOT_NATIVE_IMAGE** module, Spring Boot uses **Spring AOT** to prepare code and metadata, and then GraalVM **Native Image** performs static analysis and compiles the application into an executable. During the build, Native Image can execute a portion of Java code, including the static initializers of classes initialized at build time. Objects created during this phase that remain reachable from the application can be persisted into the executable's **image heap**.

A common error looks like:

~~~text
UnsupportedFeatureException:
An object of type 'com.example.RuntimeCache' was found in the image heap.
This type, however, is marked for initialization at image run time.
This is not allowed for correctness reasons:
All objects that are stored in the image heap must be initialized at build time.
~~~

The exception name and wording may vary by GraalVM release. The core meaning is: the build created an object of a type designated for runtime initialization, yet that object ended up in the initial state packaged into the image. This violates Java's class initialization rules.

Do not add **--initialize-at-build-time** immediately upon seeing this message. First determine whether that object is truly immutable, environment-independent data safe to snapshot into the binary. If the object holds runtime state, find where it was instantiated during the build and move creation to runtime.

After this lesson, learners can:

1. Explain build time, runtime, class initialization, and the image heap.
2. Read UnsupportedFeatureException errors related to objects in the image heap.
3. Trace an object from static fields or the object graph back to the initializer that created it.
4. Use **-H:+PrintClassInitialization** and **--trace-object-instantiation** to gather evidence.
5. Choose **--initialize-at-build-time** or **--initialize-at-run-time** based on data semantics.
6. Refactor static state into runtime-created dependencies in Spring Boot.
7. Check the impact of superclasses, subclasses, and initialization order.
8. Distinguish Spring AOT bean-definition generation from bean instance creation.
9. Check whether secrets, random seeds, paths, and configuration were snapshotted into the executable.
10. Write regression tests confirming the native executable behaves properly in the deployment environment.

> **Important rule:** every object placed in the image heap must belong to a type initialized at build time. If a type must initialize at runtime, no instance of that type may appear in the image heap.

## 2. Build Time, Runtime, and the Image Heap

### 2.1. Native Image Can Execute Java Code at Build Time

When running native-image, the builder does not merely read bytecode and translate each method into machine code. It also runs static analysis and can execute parts of application code to establish initial state for the executable.

Distinguish between:

- **Class loading:** the builder loads the class definition. Loading a class does not necessarily execute its static initializer.
- **Class initialization:** executing static field initializers and static blocks per Java rules.
- **Build-time initialization:** the class initializer runs inside the JVM performing the native-image build.
- **Runtime initialization:** the class initializer runs only when the native executable starts and the class is first used.
- **Image heap:** the region storing objects created during the build and retained because they are reachable from the application, along with certain class objects and object constants.

If a class is initialized at build time, assigned static field values are snapshotted into the executable. At native runtime, that class is already marked initialized; its static initializer does not run again.

### 2.2. Where Can Objects Enter the Image Heap From?

The most common source is static fields of classes initialized at build time:

~~~java
public final class CatalogDefaults {
    static final Map<String, String> LABELS = createLabels();

    private static Map<String, String> createLabels() {
        Map<String, String> labels = new HashMap<>();
        labels.put("SKU-1", "Standard");
        labels.put("SKU-2", "Express");
        return Map.copyOf(labels);
    }
}
~~~

If CatalogDefaults is initialized during the build, the map and the objects referenced by that map can become part of the image heap.

Objects can also be retained transitively. For instance, a static singleton references a cache, the cache references a client, and the client references connection configuration or resources. When a root remains reachable, objects retained in that graph by the builder can be persisted alongside it.

~~~mermaid
flowchart TD
    A[Build-time initialized class] --> B[Static field]
    B --> C[Singleton object]
    C --> D[Cache]
    D --> E[Client]
    E --> F[Runtime resource or state]
    F --> G[Object graph reaches image heap]
~~~

Therefore, reading only the fields of the class named in the error is sometimes insufficient. Trace the full object graph and identify which root keeps the instance reachable.

### 2.3. static final Does Not Mean Safe

The final keyword only prevents reassigning the reference after initialization. It does not turn a mutable object into an immutable one and does not guarantee environment independence.

Example:

~~~java
static final Map<String, String> CACHE = new HashMap<>();
static final Path HOME = Path.of(System.getProperty("user.home"));
static final Instant STARTED_AT = Instant.now();
static final SecureRandom RANDOM = new SecureRandom();
~~~

These fields have different properties:

- CACHE is a mutable map.
- HOME depends on a build machine system property.
- STARTED_AT freezes the build timestamp.
- RANDOM holds entropy/runtime state and must not be snapshotted arbitrarily.

A static final formatter or immutable lookup table constructed from environment-independent constants may suit build-time initialization. Still, verify the object graph and the specific library's behavior.

## 3. Why Does a Runtime Object Appear in the Image Heap?

This error usually appears when the builder detects an instance of a runtime-initialized class retained in the image heap.

Common causes:

| Object creation source | Example | Risk |
| --- | --- | --- |
| Static initializer | static final Client CLIENT = new Client() | Client is created at build time instead of application runtime. |
| Static singleton holder | Holder.INSTANCE holds a cache or registry | Object is retained through a static root. |
| Static factory call | Static field calls createDefault() | Factory constructs a runtime object during the build. |
| Transitive initializer | Class A calls class B, B creates object C | The root is not in the class mentioned in the error. |
| Third-party library | Logging, crypto, driver, serializer, or native integration | Dependency builds inappropriate state when its class initializes. |
| Build-time feature/plugin | Native Image Feature or AOT processor creates an object | Object is created inside the builder's hosted JVM. |

### 3.1. Example of Runtime-Dependent Static State

~~~java
public final class RuntimeEnvironment {
    static final String REGION = System.getenv("APP_REGION");
    static final Path DATA_DIR =
        Path.of(System.getProperty("app.data-dir", "./data"));
    static final Instant CREATED_AT = Instant.now();

    private RuntimeEnvironment() {
    }
}
~~~

If this class initializes at build time, the values will reflect the build environment. When running the same executable in another container, changing APP_REGION, app.data-dir, or the execution time does not recompute those static fields.

This might not trigger an image heap error directly, yet it is a semantic and configuration bug. If the static initializer also creates an object of a runtime-initialized class, the builder may abort with an image heap error.

### 3.2. Examples of Resources That Must Not Be Snapshotted

Objects tied to the current process's resources usually must be created at runtime:

- Open file descriptors or streams.
- Sockets or network connections.
- Running threads or started executors.
- Native handles or objects tied to native libraries.
- Clients holding connection pools and session state.
- Caches depending on deployment configuration, data, or tenants.

Do not place these resources inside static initializers executed at build time. Create and close them within the lifecycle of the application context or runtime components.

## 4. Read the Structure of the Error Message

An image heap error message usually conveys three key pieces of information:

~~~text
An object of type 'com.example.RuntimeCache' was found in the image heap.
This type, however, is marked for initialization at image run time
for the following reason: classes are initialized at run time by default.
This is not allowed for correctness reasons.
~~~

Interpretation:

1. **Object type:** the class of the instance found in the image heap, e.g., RuntimeCache.
2. **Initialization policy:** that class is configured or defaulted to runtime initialization.
3. **Correctness constraint:** an instance of a runtime-initialized class cannot exist in the image heap because it would exist before the class initializer runs at runtime.

The builder may suggest two directions:

- If the object truly belongs as initial executable data, consider marking the corresponding type for build-time initialization after verifying safety.
- If the object must be created when the service runs, find the initializer or factory that created it during the build and move that initialization to runtime.

The error message is the first clue, not sufficient proof to choose either direction. Trace the object creation source and inspect the data the object holds.

## 5. Controlled Diagnostic Workflow

### 5.1. Record the Exact Toolchain and Build Command

Before investigating, record:

~~~bash
java -version
native-image --version
native-image --help
~~~

Also record:

- Spring Boot and Spring Framework versions.
- GraalVM distribution and JDK version.
- Native Build Tools Maven/Gradle plugin version.
- Application dependency graph.
- Native build arguments being passed.
- Build profile/environment and relevant system properties.

Options and output can change across GraalVM releases. Run native-image --help, native-image --expert-options, or native-image --print-options from the exact toolchain building the project to confirm available options.

### 5.2. Enable Class Initialization Reporting

Use:

~~~bash
native-image \
  -H:+PrintClassInitialization \
  -jar target/orders-service.jar \
  -o orders-diagnostic
~~~

-H:+PrintClassInitialization helps track which classes were initialized at build time and why they were chosen. Inspect the lists/reports indicated by the build log, focusing on:

- Classes initialized before the error appeared.
- Classes automatically initialized because they were proven safe.
- Classes pulled in via superclasses or superinterfaces with default methods.
- Classes initialized because another static initializer called into them.
- Classes with a runtime policy whose instance was nonetheless created from a build-time initializer.

The goal is to understand why the class initialized and the dependency chain leading to it. There is no need to force every class in a package onto a single blanket policy.

### 5.3. Trace Where the Object Was Created

When the message identifies an object of type com.example.RuntimeCache, add:

~~~bash
native-image \
  --trace-object-instantiation=com.example.RuntimeCache \
  -H:+PrintClassInitialization \
  -jar target/orders-service.jar \
  -o orders-traced
~~~

--trace-object-instantiation instructs the builder to trace where instances of the specified type are allocated during image generation. Use the fully qualified class name and verify output for your exact GraalVM version.

If multiple types must be traced, some versions accept a comma-separated list of class names:

~~~bash
native-image \
  --trace-object-instantiation=com.example.RuntimeCache,com.example.RuntimeClient \
  -H:+PrintClassInitialization \
  -jar target/orders-service.jar \
  -o orders-traced
~~~

Trace only the types under investigation. Enabling too many traces clutters logs and increases diagnostic overhead.

### 5.4. Trace Back from Constructor to Static Initializer

Once you have the trace, identify:

1. The constructor or factory method that created the instance.
2. The direct caller of that constructor/factory.
3. The static field initializer or static block that invoked that caller.
4. Which classes initialized earlier and why.
5. Whether the object remains reachable from any other static root.

If the trace shows the object was created by RuntimeConfig's initializer, inspect all static fields of RuntimeConfig and the methods called by its static initializer. If created by a dependency, check the dependency's version and provided initialization configuration before adding custom flags for that dependency.

### 5.5. Isolation Diagram

~~~mermaid
flowchart TD
    A[Build reports runtime-init object in image heap] --> B[Read type and initialization reason]
    B --> C[Enable PrintClassInitialization]
    C --> D[Enable trace-object-instantiation for type]
    D --> E[Find constructor/factory and caller]
    E --> F{Does object need to exist from build time?}
    F -->|Yes, immutable and env-independent| G[Evaluate build-time initialization]
    F -->|No, runtime state/resource| H[Move object creation to runtime]
    G --> I[Inspect static fields and object graph]
    H --> J[Runtime-init the creating class or refactor static state]
    I --> K[Rebuild and run regression tests]
    J --> K
    K --> L{Native behavior correct?}
    L -->|No| E
    L -->|Yes| M[Document policy and evidence]
~~~

## 6. Approach One: The Object Genuinely Fits the Image Heap

Use this approach only when the object is initialization data safe to snapshot:

- Contains no secrets or credentials.
- Does not depend on the build machine's hostname, user home, working directory, or filesystem.
- Does not depend on environment variables/system properties that must be read at deploy time.
- Contains no timestamps or random seeds that must vary per process.
- Holds no file descriptors, sockets, threads, native handles, or runtime resources.
- Holds no mutable global state requiring isolation across processes/tenants.
- Has no side effects that must execute when the application runs.

Once verified, you can mark that specific class for build-time initialization:

~~~bash
native-image \
  --initialize-at-build-time=com.example.CatalogDefaults \
  -jar target/orders-service.jar \
  -o orders-service
~~~

This option also affects superclasses under class initialization rules. Inspect all related classes and static fields after making the change.

### 6.1. Inspect the Object Graph Before Allowing Build-Time Init

Example of an immutable configuration table:

~~~java
public final class CatalogDefaults {
    static final Map<String, String> LABELS = Map.of(
        "SKU-1", "Standard",
        "SKU-2", "Express"
    );

    private CatalogDefaults() {
    }
}
~~~

If the data consists strictly of non-sensitive, environment-independent constants used as initialization data, build-time initialization may be appropriate.

However, if a map holds service objects:

~~~java
static final Map<String, Object> COMPONENTS = createComponents();
~~~

then you must inspect every value and every transitive reference. An immutable map can still point to clients, caches, or runtime resources.

### 6.2. Do Not Snapshot Secrets or Environment Data

Build-time initializers can read environment variables, system properties, files, and build-machine state. Those values can become embedded in the executable.

Examples never to snapshot:

~~~java
static final String API_TOKEN = System.getenv("PAYMENT_API_TOKEN");
static final String HOST = System.getenv("HOSTNAME");
static final Path CONFIG =
    Path.of(System.getProperty("user.home"), ".app", "config");
~~~

If a build pipeline has secrets, a static initializer reading them can bake those secrets into the image. Run the native-image builder in a dedicated build environment without unnecessary sensitive data, and move sensitive configuration reads to runtime.

## 7. Approach Two: The Object Must Be Created at Runtime

If the object represents process state or runtime resources, do not try to keep it in the image heap. Find the initializing class that created the object during the build and move that initializer to runtime.

Example:

~~~java
public final class RuntimeRegistry {
    static final RuntimeCache CACHE = new RuntimeCache();

    private RuntimeRegistry() {
    }
}
~~~

If RuntimeRegistry initializes at build time, CACHE gets instantiated during image generation. Once tracing confirms this is the allocation source, you can require the registry class to initialize at runtime:

~~~bash
native-image \
  --initialize-at-run-time=com.example.RuntimeRegistry \
  -jar target/orders-service.jar \
  -o orders-service
~~~

This defers RuntimeRegistry's static initializer to runtime. Re-verify that no other static root allocates the same object during the build.

### 7.1. Runtime Initialization Has Overhead and Hierarchy Rules

Runtime initialization forces the builder to preserve initialization work for application execution. This can:

- Increase startup work.
- Add initialization-state checks before static field accesses, static method calls, and object allocations.
- Pull subclasses into runtime initialization under GraalVM rules.
- Require rechecking initialization order and superclasses/superinterfaces.

The hierarchy rule has a concrete implication: when a class initializes at build time, its relevant supertypes must also initialize at build time; when a class initializes at runtime, its relevant subtypes must also initialize at runtime. Thus a policy can affect additional classes beyond the name written in the flag. Re-read the class initialization report after every change to verify the actual scope.

Do not switch an entire package to runtime just to resolve one object when you can pinpoint the exact class creating the object.

### 7.2. Do Not Mark the Wrong Class Holding the Object

Suppose RuntimeCache is created from ApplicationDefaults's static initializer:

~~~java
public final class ApplicationDefaults {
    static final RuntimeCache CACHE = CacheFactory.create();

    private ApplicationDefaults() {
    }
}
~~~

If RuntimeCache must be created at runtime, the key is preventing ApplicationDefaults from calling the factory during the build. Marking the creating class (ApplicationDefaults) as runtime-initialized addresses the allocation source; marking a different class does not stop the offending static initializer from running.

Use tracing to confirm which class actually creates the instance. After changing the policy, rebuild and verify the object is no longer snapshotted.

## 8. Refactor Static State into Runtime Dependencies

For Spring Boot applications, lifecycle control is usually much cleaner when converting clients/caches/clocks into beans managed by the ApplicationContext instead of static singletons.

### 8.1. From Static Singleton

~~~java
public final class PaymentClientHolder {
    static final PaymentClient CLIENT = PaymentClient.connect(
        System.getenv("PAYMENT_URL")
    );

    private PaymentClientHolder() {
    }
}
~~~

### 8.2. To Spring Bean

~~~java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    PaymentClient paymentClient(
            @Value("${payment.url}") URI paymentUrl) {
        return PaymentClient.connect(paymentUrl);
    }
}
~~~

Spring creates the bean according to the application context lifecycle at runtime. Runtime configuration can be read from the deployment environment, and the client is closed with the proper lifecycle.

Ensure the client has proper cleanup, such as a bean destroy method or lifecycle interface. Never open network connections inside static initializers.

### 8.3. Inject Clock Instead of Static Timestamps

~~~java
@Configuration(proxyBeanMethods = false)
class TimeConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}

@Service
class InvoiceService {
    private final Clock clock;

    InvoiceService(Clock clock) {
        this.clock = clock;
    }

    Instant createdAt() {
        return Instant.now(clock);
    }
}
~~~

This keeps time evaluation at runtime and simplifies testing with Clock.fixed(...). Do not snapshot Instant.now() in a static field if the application needs the actual time when processing occurs.

### 8.4. Inject Entropy and Random Generators

Do not initialize random seeds inside static initializers executed at build time. Use an API suited to the application's security and runtime needs, and create the dependency at runtime. For sensitive data, consult the JCA/SecureRandom guidance for your GraalVM release and configure the appropriate provider.

Never replace SecureRandom with Random just to avoid a build error. That alters semantics and can weaken security.

## 9. Relationship to Spring AOT

Spring AOT and Native Image build time are related but distinct phases.

According to current Spring Boot documentation:

- Spring AOT starts the application just far enough to determine bean definitions.
- AOT generates source code, proxy bytecode, and GraalVM hints.
- Bean instances are not created during AOT processing itself.
- The Native Image builder continues analysis and may run class initializers or build-time code.

Therefore, when encountering an object in the image heap, do not immediately assume Spring AOT instantiated that bean. Inspect static initializers, Native Image Features, dependencies, and actual build-time code that allocated the object.

### 9.1. Inspect Generated AOT Code

Paths described by current Spring Boot documentation:

| Build tool | Generated AOT sources | Generated AOT resources |
| --- | --- | --- |
| Maven | target/spring-aot/main/sources | target/spring-aot/main/resources |
| Gradle | build/generated/aotSources | build/generated/aotResources |

Paths can vary across Spring Boot/plugin versions. Use them to read generated code and understand generated bean definitions/hints; never edit generated output directly because the next build will overwrite it.

### 9.2. Static Initialization in Dependencies

The error may originate in a dependency rather than application code. For instance, a library may instantiate a logger factory, registry, or provider in a static initializer. When this happens:

1. Identify the artifact and version owning the class.
2. Check the dependency's release notes and Native Image support.
3. Upgrade the dependency if a compatible fix exists.
4. Check metadata/configuration bundled by the library.
5. Add initialization policies only after understanding the initializer and the state it creates.

Do not mark an entire dependency package as build-time initialized just because one class throws an error.

## 10. Configure Diagnostics in Maven and Gradle

The examples below use Native Build Tools. Integrate them into your existing plugin/profile and check the DSL for your project's version.

### 10.1. Maven

You can add diagnostic build arguments:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>-H:+PrintClassInitialization</buildArg>
            <buildArg>--trace-object-instantiation=com.example.RuntimeCache</buildArg>
        </buildArgs>
    </configuration>
</plugin>
~~~

Run the native build with your project profile:

~~~bash
./mvnw -Pnative package
~~~

Once the required policy is determined, add the appropriate runtime/build-time options to the production profile. Keep trace options in a separate diagnostic profile to avoid massive logs on every build.

### 10.2. Gradle Kotlin DSL

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add("-H:+PrintClassInitialization")
            buildArgs.add(
                "--trace-object-instantiation=com.example.RuntimeCache"
            )
        }
    }
}
~~~

Run:

~~~bash
./gradlew nativeCompile
~~~

After identifying the root cause, replace trace options with the appropriate initialization policy, for example:

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add(
                "--initialize-at-run-time=com.example.RuntimeRegistry"
            )
        }
    }
}
~~~

### 10.3. Separate Debug and Production Profiles

Keep two clearly separated configurations:

| Configuration | Options | Purpose |
| --- | --- | --- |
| Diagnostic | -H:+PrintClassInitialization, --trace-object-instantiation | Find root causes during the build. |
| Production | Verified initialization policies | Produce the final executable with accurate semantics. |

Do not leave trace options enabled indefinitely when unneeded. After fixing, rebuild with a production-like configuration and run native tests.

## 11. Security and Correctness Verification

Build-time initialization snapshots state. Therefore, verify both correctness and security.

### 11.1. Data That Must Never Appear in the Image

Do not let static initializers snapshot:

- API keys, passwords, OAuth tokens, or private keys.
- Random seeds that must be freshly generated at runtime.
- User home, hostname, current working directory, or paths valid only on the build machine.
- Timestamps or cache state expected to reflect runtime execution.
- File handles, sockets, threads, and native handles.
- Configuration that differs between staging and production.

Oracle GraalVM security guidance warns that values computed in static initializers can be persisted into the executable, including sensitive data and random seeds. Therefore, run the builder in a dedicated build environment without unnecessary secrets, and move sensitive configuration reads to runtime.

### 11.2. Test the Same Executable with Different Runtime Configurations

A useful regression test:

1. Build the native executable once.
2. Run with APP_REGION=ap-southeast-1.
3. Run the exact same executable with APP_REGION=eu-west-1.
4. Confirm the application reads the corresponding value on each run.
5. Confirm clients/caches/paths are initialized according to runtime configuration.
6. Verify no sensitive data from the build machine is frozen inside the executable.

If both runs still use the same stale value, check for static fields or initializers that snapshotted configuration at build time.

## 12. Common Handling Mistakes

| Wrong approach | Why it is wrong | Proper approach |
| --- | --- | --- |
| Adding --initialize-at-build-time to a whole package | Can accidentally snapshot secrets, environment state, and resource handles. | Trace the object, inspect fields/object graph, and pick the narrowest class. |
| Marking only the object's type as runtime | The allocation source may sit in another class's initializer. | Use --trace-object-instantiation to find the culprit. |
| Assuming static final is always immutable | Final locks only the reference, not the object graph. | Inspect object types and transitive references. |
| Disabling strict image heap or ignoring errors | Can mask semantic divergence and broken resource state. | Fix initialization policy or refactor the allocation source. |
| Marking a whole package as runtime | Increases initialization check and startup overhead; pulls subclasses into the policy. | Use class-level policies when sufficient. |
| Rebuilding without runtime testing | A passing build does not prove runtime configuration is read properly. | Test multiple runtime environments and the native executable. |
| Editing AOT generated files | Subsequent builds overwrite them and leave the source unfixed. | Fix the source/configuration/Feature owning the behavior. |
| Replacing SecureRandom with Random | Changes security guarantees. | Keep the secure API and move initialization to runtime. |
| Blaming Spring bean lifecycle | Spring AOT does not instantiate beans during bean definition processing. | Trace actual static initializers and build-time code. |

## 13. Hands-on Exercise: Resolving RuntimeCache Captured in the Image Heap

**Context:** A Spring Boot service has RuntimeRegistry holding a static singleton. The native build fails because RuntimeCache was found in the image heap while that type is marked for runtime initialization. The cache must read deployment-time configuration and must never share state from the build machine.

### Tasks

1. Record GraalVM/JDK, Spring Boot, Native Build Tools, and dependency versions.
2. Save the verbatim error message, especially the object type and initialization reason.
3. Build with -H:+PrintClassInitialization to identify initialized classes and reasons.
4. Rebuild with --trace-object-instantiation=com.example.RuntimeCache.
5. Locate the static initializer/factory that instantiated RuntimeCache.
6. Inspect RuntimeRegistry's static fields and object graph.
7. Determine whether the cache can be immutable build-time data or must be created from runtime configuration.
8. If the cache is runtime state, refactor it into a Spring bean or switch the creating class to runtime initialization.
9. If any data object genuinely fits the image heap, prove it is immutable, environment-independent, and secret-free before opting into build-time initialization.
10. Rebuild the native executable with the narrowest policy.
11. Run the same executable with two different runtime configurations and confirm the cache initializes per process.
12. Run JVM tests, AOT-on-JVM, and native integration/smoke tests.
13. Archive build logs, traces, initialization policies, and test reports.

### Evidence Record

| Evidence | Details to archive |
| --- | --- |
| Toolchain | GraalVM/JDK, Spring Boot, Native Build Tools, and dependencies. |
| Error | Full error, object type, and initialization reason. |
| Class initialization | Output of -H:+PrintClassInitialization. |
| Instantiation trace | Output of --trace-object-instantiation. |
| Root cause | Static field, initializer, factory, and object graph. |
| Policy | Class chosen for build-time or runtime init and rationale. |
| Refactor | Source class/bean responsible for creating runtime state. |
| Security | Checks for secrets, random seeds, and environment snapshots. |
| Regression | JVM, AOT-on-JVM, and native tests across distinct runtime configs. |
| Release evidence | Native build log, executable, and known limitations. |

### Completion Criteria

- [ ] Can explain why a runtime-initialized instance cannot reside in the image heap.
- [ ] Identified the object type from the error message.
- [ ] Used -H:+PrintClassInitialization.
- [ ] Used --trace-object-instantiation.
- [ ] Found the static root or initializer creating the object.
- [ ] Chose accurately between build-time initialization and runtime initialization.
- [ ] Did not snapshot secrets, random seeds, or environment-specific state.
- [ ] Refactored runtime resources into lifecycle-managed dependencies.
- [ ] Native executable builds cleanly and runs across multiple runtime configurations.
- [ ] Regression tests confirm behavior after the fix.

## 14. Self-Assessment Questions

1. From what sources does Native Image construct the image heap?
2. How does class loading differ from class initialization?
3. Why cannot an object of a runtime-initialized class appear in the image heap?
4. Does static final guarantee an object is immutable and safe to snapshot?
5. What information does -H:+PrintClassInitialization provide?
6. How does --trace-object-instantiation help locate object allocation sources?
7. When should --initialize-at-build-time be used?
8. When should --initialize-at-run-time be used?
9. Why must you locate the class creating the object rather than only marking the object's type?
10. How do superclass/subclass rules affect initialization policies?
11. How does Spring AOT generating bean definitions differ from creating bean instances?
12. How do you verify secrets or runtime configurations were not snapshotted into the executable?

## 15. Official References

Options and initialization policies depend on the GraalVM release. Always check the documentation and native-image --help for the toolchain in use:

- [GraalVM Native Image — Class Initialization](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/ClassInitialization/): build-time initialization, safe classes, and -H:+PrintClassInitialization.
- [GraalVM Native Image — Specify Class Initialization Explicitly](https://www.graalvm.org/latest/reference-manual/native-image/guides/specify-class-initialization/): --initialize-at-build-time and --initialize-at-run-time.
- [GraalVM Native Image — Basics](https://www.graalvm.org/latest/reference-manual/native-image/basics/): build time, runtime, image heap, and static analysis.
- [GraalVM Native Image — Command-line Options](https://www.graalvm.org/jdk25.5/reference-manual/native-image/overview/Options/): verifying --trace-object-instantiation and option availability by version.
- [Oracle GraalVM — Security Considerations in Native Image](https://docs.oracle.com/en/graalvm/jdk/25/docs/security-guide/native-image/): risks of snapshotting secrets, random seeds, and runtime initialization.
- [Oracle GraalVM SDK — RuntimeClassInitialization](https://docs.oracle.com/en/graalvm/jdk/25/sdk/org/graalvm/nativeimage/hosted/RuntimeClassInitialization.html): API for configuring class initialization in a Native Image Feature.
- [Spring Boot — Introducing GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html): Spring AOT, generated bean definitions, generated sources, and hints.

**Key takeaway:** an image heap error signals that an object was created at build time yet belongs to a type requiring runtime initialization. Trace the allocation source, inspect the object graph and snapshotted data; opt into build-time initialization only for genuinely safe data, while runtime state must be created within the application's runtime lifecycle.
