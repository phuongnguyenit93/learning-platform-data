# Dependencies Using Unsupported Bytecode Generation or Dynamic Class Loading

## 1. Why Does a Dependency Run on the JVM but Fail in Native Image?

Some Java libraries generate new classes at runtime, define classes via classloaders, or look up classes by name from configuration. On the HotSpot JVM, these techniques rely on dynamic class loading and runtime bytecode generation. GraalVM Native Image analyzes reachable code at build time and produces an executable for that closed set. The runtime does not include the full compiler/classloader flexibility of a traditional JVM.

Consequently, a dependency can work properly when running as a JAR yet fail inside a native executable. Common cases include proxy/code generation, bytecode enhancement, plugin loading, script engines, classpath scanning, and class names known only at runtime.

In the **SPRING_BOOT_NATIVE_IMAGE** module, clearly distinguish which mechanisms are supported by Spring AOT or Native Image, which require metadata, and which genuinely rely on generating/loading arbitrary classes after the build. This lesson guides identifying problematic dependencies, reading errors, finding official native support, choosing alternative designs, and testing on the native executable.

## 2. Distinguish Reflection, Proxies, and Runtime Bytecode Generation

Three mechanisms are often lumped together as "dynamic", yet they have different requirements:

| Mechanism | Examples | Common native issue |
|---|---|---|
| Reflection | `Class.forName`, `Method.invoke`, constructor lookup | Types/members must be described by reachability metadata |
| Dynamic proxy | `Proxy.newProxyInstance` or framework proxies | Interface combinations must be known and registered beforehand where required |
| Bytecode generation | ASM, Byte Buddy, CGLIB, Javassist | Generating new class bytecode while the process runs may not be supported as on the JVM |
| Dynamic class loading | `URLClassLoader`, plugin JARs, `defineClass` | Classes/resources outside the build-time universe may fail to load |
| Script/eval | Engines compiling scripts into classes/bytecode | Engines may depend on a runtime compiler or class definition |
| Classpath scanning | Scanning packages/JARs to discover implementations | Class set is unknown or resource metadata is incomplete |

Reflection and proxies have specific Native Image support mechanisms. Do not conclude that every API containing the word "dynamic" is unusable. Conversely, adding reflection hints does not turn an arbitrary runtime bytecode compiler into a supported capability.

## 3. Native Image Operates Under a Closed-World Model

Native Image analyzes reachable code and data at build time. Required classes and access paths must be known to the compiler via static code, Spring AOT, metadata, or framework support mechanisms.

This means:
- Classes already on the build classpath can be included in the executable if reachable and properly described.
- Reflection on known classes can work when type/member hints are complete.
- Dynamic proxies can be supported when the interface set is known upfront and matching metadata is provided.
- New classes loaded from plugin JARs introduced after the executable was built will not automatically exist in the image.
- Bytecode generated arbitrarily at runtime cannot automatically be pre-analyzed by the compiler.

Closed-world does not mean every class name must be hard-coded manually. Spring AOT, library reachability metadata, and Native Image tracing provide substantial information automatically. However, mechanisms generating new code/classes at runtime must be evaluated separately.

## 4. Identify Bytecode-Generating Dependencies

Look for libraries or APIs capable of generating dynamic classes:

- CGLIB and Spring AOP class-based proxies.
- Byte Buddy.
- ASM.
- Javassist.
- Hibernate bytecode enhancement/proxies.
- Mocking frameworks generating subclasses/proxies.
- Serialization/mapper frameworks with runtime code generation.
- Expression/script engines compiling code at runtime.
- Dependency injection or RPC frameworks generating stubs dynamically.
- Plugin frameworks loading modules/JARs outside the build classpath.

You can locate dependencies in the Maven/Gradle graph and source usages. However, a dependency's name alone is not enough to conclude there is a problem. A library may provide an AOT/pre-generated mode or only use bytecode generation in JVM test scope.

Classify by the actual production path: which class is generated, when it is generated, which API creates the class, and which feature invokes it.

## 5. CGLIB and Spring AOP

Spring AOP can use JDK dynamic proxies or class-based proxies. JDK proxies are interface-based; class-based proxies typically involve CGLIB/subclass generation.

Example class-based proxy configuration:

```java
@EnableAspectJAutoProxy(proxyTargetClass = true)
@Configuration
class AopConfiguration {
}
```

In a native application, Spring AOT can handle many proxies needed for the known bean graph. However, you cannot assume arbitrary proxies created from runtime data are already prepared.

When failures occur:
1. Determine whether the proxy is a JDK interface proxy or a class-based proxy.
2. Check whether the bean and advisor were discovered in the AOT context.
3. Verify your Spring Framework/Spring Boot version has native support for that proxy path.
4. Check final classes/interfaces, constructors, and method visibility.
5. Run a native integration test invoking the method through the real proxy.

Do not add JDK proxy hints to fix CGLIB subclass generation failures; the two mechanisms are distinct.

## 6. Byte Buddy, ASM, and Javassist

Byte Buddy, ASM, and Javassist are bytecode manipulation tools. On the JVM, an application can synthesize a byte array representing a new class and define it via a classloader. Certain Native Image modes do not support defining arbitrary classes at runtime the way HotSpot does.

Examine how the dependency uses the library:
- Reading/writing bytecode only inside a build plugin?
- Generating code prior to native compilation?
- Creating classes only during test execution?
- Creating new classes along the production request path?
- Attaching an agent/instrumentation to the JVM?
- Defining classes from byte arrays via a custom classloader?

If code generation runs at build time, generated classes can be compiled and fed into the native build like regular classes. If generation occurs strictly at runtime, verify whether Native Image supports that exact API/feature; do not infer support merely because the library compiles.

## 7. ClassLoaders and Plugin Architectures

Plugin-based applications often load JARs or classes from external locations:

```java
URLClassLoader loader = new URLClassLoader(
        pluginUrls,
        getClass().getClassLoader());

Class<?> pluginType =
        loader.loadClass(configuredClassName);
```

On the JVM, this can load new plugins after the process starts. With Native Image, plugin classes outside the build-time universe do not magically appear in the executable. Dropping a JAR onto the filesystem after building does not cause the Native Image compiler to analyze and bundle those classes into the binary.

If the plugin set is fixed, place all implementations on the build classpath and select an implementation via a static registry/factory. If plugins must be installed independently post-release, consider keeping that module on the JVM or isolating it into a separate service/process with an appropriate runtime.

Never promise "drop-in plugin JAR" support simply by adding reflection hints. Hints describe access to classes already present in the image; they do not package arbitrary code arriving after the build.

## 8. Class.forName with Class Names from Configuration

The following code can fail in native if the class name is only known at runtime:

```java
String implementation =
        environment.getRequiredProperty("handler.class");

Class<?> type = Class.forName(implementation);
Object handler = type.getDeclaredConstructor().newInstance();
```

If the list of implementations is finite and known at build time, model the choices explicitly:

```java
@Component
class HandlerRegistry {

    private final Map<String, OrderHandler> handlers;

    HandlerRegistry(List<OrderHandler> discoveredHandlers) {
        this.handlers = discoveredHandlers.stream()
                .collect(Collectors.toUnmodifiableMap(
                        OrderHandler::name,
                        Function.identity()));
    }

    OrderHandler get(String name) {
        OrderHandler handler = handlers.get(name);
        if (handler == null) {
            throw new IllegalArgumentException(
                    "Unknown handler: " + name);
        }
        return handler;
    }
}
```

Spring can discover the implementation beans in the AOT context, and the registry picks a bean by key at runtime. The implementation set is known ahead of time, while configuration selection can still change without loading new classes.

If reflection by class name is genuinely required, register type/member metadata for the entire set of valid classes and verify the AOT/native path. Never accept arbitrary class names from requests or uncontrolled configuration.

## 9. Distinguish Class Reachability from Class Definition

This distinction is critical when troubleshooting:

- **Reachability:** a class already present in build inputs that the compiler must retain.
- **Reflection metadata:** describes reflective access to known types/members.
- **Proxy metadata:** describes interface combinations required for supported proxies.
- **Class definition:** creating a new class from bytecode at runtime.
- **Class loading:** locating and loading classes from sources that may appear after the build.

Reachability metadata does not automatically turn newly synthesized bytecode into a reachable class. Reflection hints are likewise not equivalent to running an arbitrary Java/bytecode compiler inside the native process.

When encountering `ClassNotFoundException`, `NoClassDefFoundError`, `UnsupportedFeatureError`, or class-definition errors, determine which category applies before altering metadata.

## 10. Script Engines and Eval

Some applications allow users or administrators to supply scripts. Engines may parse, compile, or emit bytecode at runtime.

Distinguish between:
- Engines that purely interpret ASTs/interpreters.
- Engines that compile scripts into JVM bytecode.
- Engines that use a classloader to load generated classes.
- Engines running on a dedicated runtime such as GraalVM Polyglot.
- Engines depending on native libraries or external runtimes.

Do not assume every JavaScript/Groovy/Kotlin scripting engine behaves identically in Native Image. Just because an engine runs on HotSpot does not prove its compiler/runtime mode can be packaged natively.

If the script set is finite and known upfront, consider compiling scripts into artifacts at build time. If scripts must change arbitrarily after deployment, check whether the engine has a supported native-compatible interpreter/runtime; otherwise, offload execution to a JVM or dedicated service.

## 11. Hibernate Enhancement and Proxies

Hibernate uses proxy/lazy-loading and bytecode enhancement mechanisms. Usage depends on Hibernate version, build-time enhancement plugins, runtime providers, and entity configuration.

Distinguish between:
- Build-time enhancement: classes are transformed prior to Native Image compilation.
- Runtime proxy generation: proxy classes are generated while the process runs.
- Lazy associations: the provider may use proxies/interceptors to defer loading.
- Entity materialization: constructing entities from data via constructors/property access.

Spring Boot/Hibernate offer Native Image support varying by version; consult matching documentation. If an error occurs on a lazy proxy, do not conclude Hibernate is entirely unsupported. Verify provider version, enhancement mode, proxy strategy, and native tests on actual associations.

One design option is avoiding lazy loading outside transactions and using explicit projections/queries at API boundaries. This improves both data-access predictability and native compatibility.

## 12. Mocking and Bytecode Generation Strictly in Test Scope

Mocking frameworks may generate subclasses/proxies at runtime. Tests running on the JVM can pass even though the production executable never uses that framework. Never include test-only dependencies in the native application just to satisfy mocks.

If a native test executable requires a mocking framework, verify native support for that specific framework/version. Alternatively, replace dynamic mocks with static fake implementations for tests or verify production behavior via black-box integration tests.

Distinguish:
- Dependencies present only in test scope.
- Dependencies packaged in production.
- Test code compiled into the native test executable.
- Production code paths generating proxies/bytecode at runtime.

A native test failing due to a mocking framework does not automatically mean the production application fails. However, if a production dependency also generates bytecode, test that exact path.

## 13. Build-Time Code Generation Is Often the Right Alternative

If the code to generate is known beforehand, shift generation to build time:

1. Read schemas/configuration during the build.
2. Generate Java source or class files.
3. Compile the generated output alongside the application.
4. Let Spring AOT analyze the ApplicationContext.
5. Build the Native Image from generated classes and metadata.
6. Test the executable against the same contract.

For example, OpenAPI/protobuf/mapper generators normally emit sources during the build lifecycle. Generated sources become ordinary code for the compiler to analyze, unlike generating new classes per request in production.

Ensure generated output is deterministic, stored in build artifacts or reproducible from versioned sources/schemas. Never manually edit generated files if the build tool will overwrite them.

## 14. Choose a Registry/Factory Instead of Arbitrary Plugin Loading

When the implementation set is fixed, a registry is an easily analyzable design:

```java
interface PaymentProcessor {
    String provider();
    PaymentResult process(PaymentCommand command);
}

@Component
class PaymentProcessorRegistry {

    private final Map<String, PaymentProcessor> processors;

    PaymentProcessorRegistry(List<PaymentProcessor> processors) {
        this.processors = processors.stream()
                .collect(Collectors.toUnmodifiableMap(
                        PaymentProcessor::provider,
                        Function.identity()));
    }

    PaymentProcessor get(String provider) {
        PaymentProcessor result = processors.get(provider);
        if (result == null) {
            throw new IllegalArgumentException(
                    "Unsupported provider: " + provider);
        }
        return result;
    }
}
```

Spring AOT sees the implementation beans registered in the context. Runtime simply selects a bean from the registry; there is no need to load classes from arbitrary names.

If providers must be added independently post-deployment, a static registry does not satisfy that requirement. In that case, adopt a separate plugin/service architecture or keep the extensible component on the JVM. Choose according to product requirements rather than forcing Native Image into an unsupported runtime class-loading model.

## 15. Check Dependency Native Support

Before introducing workarounds, check:
- Does the dependency version document Native Image support?
- Is official reachability metadata or repository metadata available?
- Do Spring Boot/Spring Data starters provide AOT contributions?
- Does the dependency use reflection or runtime bytecode generation?
- Is there a build-time generation/precompiled proxy mode?
- Are there known issues/limitations for that exact version/architecture?
- Are there specific license/edition conditions?

Prefer library/vendor-provided metadata and integrate via supported Native Image mechanisms. Never copy reflect-config/proxy-config files from another version without verifying APIs, class names, and runtime behavior.

A dependency may support Native Image only partially. Verify the exact features your application uses rather than judging an entire library by a single "compatible" label.

## 16. Use the Tracing Agent to Discover Dynamic Access — Within Scope

The Native Image tracing agent can observe operations such as reflection, resources, proxies, and serialization during JVM runs and emit suggested metadata. The agent is useful when a dependency dynamically accesses classes/members already on the classpath.

However, the tracing agent does not solve all runtime code generation:
- It cannot make plugin classes introduced after the build appear in the image.
- It does not guarantee every logic branch executed during tracing.
- It does not by itself make `defineClass` or instrumentation APIs supported by Native Image.
- It can emit overly broad metadata if the traced workload is uncontrolled.

Use the agent to uncover missing metadata accesses, then review generated files and write tests. If the error is a dependency generating new bytecode at runtime, look for an AOT/pre-generation mode or change the architecture instead of merely re-running the agent.

## 17. Read Native Errors to Pinpoint the Problematic Dependency

Some indicators:

| Error | Investigation direction |
|---|---|
| `ClassNotFoundException` | Is the class name on the build classpath/image? Is an external plugin JAR being loaded? |
| `NoClassDefFoundError` | Missing dependency/class, initialization failure, or reachability issue? |
| `UnsupportedFeatureError` | Which API/feature did Native Image block? Read the stack trace and version docs |
| `defineClass` error | Is a dependency creating classes from bytecode at runtime? |
| CGLIB/Byte Buddy/ASM error | Which proxy/code generation mode was called and when? |
| Proxy interface error | Is the interface combination known and registered accurately? |
| Script compilation error | Does the engine require a JVM compiler/classloader? |
| Plugin load failure | Was the plugin in the image at build time or added post-deploy? |

Capture the full stack trace and identify the first frame belonging to the dependency. Record dependency coordinates/version and the feature invoked. Do not add hints before knowing whether the error is reflection, proxy, class loading, or bytecode definition.

## 18. Remediation Workflow Ordered by Intervention Level

Proceed in order:

1. **Upgrade the dependency** to a version with official Native Image support if appropriate.
2. **Enable AOT/pre-generated mode** provided by the dependency.
3. **Generate code at build time** if inputs/schemas are known upfront.
4. **Register metadata** for reflection/resources/proxies on known classes.
5. **Replace runtime discovery** with a static registry/factory when the implementation set is finite.
6. **Extract into a JVM service/process** if the genuine requirement is loading arbitrary plugins or bytecode post-deploy.
7. **Keep the module on the JVM** if a core dependency lacks a compatible native path.

After each change, run JVM regressions, Spring AOT, the native build, and native integration tests for that exact feature. Do not change multiple layers simultaneously, as doing so makes root-cause attribution difficult.

## 19. Diagnosis and Remediation by Example

| Scenario | Initial conclusion | Remedy |
|---|---|---|
| Jackson reflection missing constructor | Metadata access to a known class | Use proper support/hints and test payload |
| Spring AOP proxy fails | Likely wrong proxy type or AOT discovery | Check JDK/CGLIB proxies and Spring version |
| Post-deploy mounted plugin JAR fails to load | Class absent from build-time image | Prepackage plugin or run plugins on the JVM |
| Byte Buddy defines class per request | Runtime bytecode generation | Look for AOT mode or change design |
| Hibernate lazy proxy error | Provider/proxy/enhancement compatibility | Check Hibernate support and association tests |
| Mock test fails in native | Test framework code generation | Use fakes/black-box tests or test framework native support |
| Script engine compiles source at runtime | Engine requires compiler/classloader | Supported interpreter/native runtime or extract to JVM |

These conclusions are triage directions, not automatic diagnoses. Always rely on stack traces, dependency versions, and reproducible tests.

## 20. Hands-on Exercise: Replace Plugin Class Loading with an Implementation Registry

**Context:** Order API reads a processor class name from a property and uses `Class.forName` to instantiate the processor. The JVM JAR works, but the native executable fails at startup or when handling requests.

**Step 1 — Identify implementations.** List all supported production processors and where they are declared.

**Step 2 — Inspect the dependency path.** Determine whether the class is created via reflection, CGLIB, Byte Buddy, or a custom classloader; determine when instantiation occurs.

**Step 3 — Design the registry.** Register processors as Spring beans or factory implementations with explicit types.

**Step 4 — Fix the build structure.** Ensure all valid implementations are on the classpath and in the ApplicationContext when AOT runs.

**Step 5 — Keep runtime selection.** Select the processor using a validated key/property instead of loading arbitrary class names.

**Step 6 — Run JVM tests.** Test each provider, an unknown provider, and default behavior.

**Step 7 — Run AOT/native.** Confirm the bean graph, generated context, and native executable handle all supported providers.

**Step 8 — Validate genuine plugin requirements.** If the product strictly requires post-deploy plugin JAR installation, evaluate extracting a JVM plugin host process/service instead of pretending a static registry meets that requirement.

Completion criteria: the dependency causing dynamic behavior is identified; the code generation/class loading path is classified; native support or alternative design is verified; the native executable runs all committed implementations; plugin/runtime extension limits are clearly documented.

## 21. Conclusion

Dependencies using bytecode generation or dynamic class loading may run fine on HotSpot yet conflict with Native Image's build-time reachability model. Distinguish reflection, proxies, runtime class definition, and plugin loading: metadata can describe access to known classes, but it cannot package new classes arriving after the build or embed a full JVM bytecode compiler inside the executable.

Pinpoint the exact API and dependency causing the failure, verify version-specific Native Image support, and prefer AOT/pre-generated code and static registries when implementations are finite. If product requirements genuinely demand loading arbitrary plugins or generating bytecode post-deploy, keep that portion on the JVM or isolate it into a separate process/service. Validate the decision with a native build and tests along the actual production code path.
