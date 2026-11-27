# Missing Reflection, Proxy, Serialization, or JNI Metadata

## 1. Why Does an Application Run on the JVM but Fail in Native Image?

In the **SPRING_BOOT_NATIVE_IMAGE** module, Spring AOT analyzes the ApplicationContext at build time, generating initialization code and runtime hints; GraalVM Native Image then performs static analysis to build the executable. Native Image retains only the classes, methods, fields, and resources it determines are needed.

Some libraries still access Java elements using information known only at runtime, such as:

- Class names read from configuration or a database and passed to **Class.forName**.
- Frameworks invoking constructors, methods, or fields via reflection.
- Code creating JDK dynamic proxies from a list of interfaces.
- Libraries reading/writing objects via Java serialization.
- Native code calling back into Java through JNI.

On a standard JVM, the classloader and runtime can discover many elements on the classpath. Native Image cannot infer every dynamic access automatically. If the build lacks reachability metadata, the application may start up normally yet fail when exercising a specific feature.

Metadata is not an arbitrary list of classes to keep. It precisely describes the dynamic access that must be supported: which types are looked up via reflection, which constructors/methods/fields are invoked, which interface combinations form proxies, which classes are serialized, or which Java elements native code accesses.

## 2. Distinguish the Types of Metadata

| Mechanism | Who performs the dynamic access? | What must be declared |
| --- | --- | --- |
| Reflection | Java code using Class, Method, Constructor, Field, MethodHandles | Type, constructor, method, field, and corresponding access permissions |
| JDK dynamic proxy | Java code using Proxy.newProxyInstance or libraries creating interface proxies | Interface list in the exact combination and order |
| Spring AOP/CGLIB proxy | Spring creating proxies to apply transactions, security, async, or advice | Spring AOT must recognize the bean/proxy at build time; Spring CGLIB proxies follow a separate AOT path |
| Java serialization | ObjectOutputStream/ObjectInputStream | Serializable classes and serialization metadata |
| JSON binding | Jackson or codecs reading/writing DTOs via reflection | Constructors, fields, properties, record components, and nested types to bind |
| JNI | C/C++ native code looking up classes, methods, fields, or creating Java objects | Corresponding JNI type/member access |

Spring Framework provides **RuntimeHints** for reflection, resources, Java serialization, proxies, and JNI. JNI remains a separate metadata category in GraalVM output, though it can be registered via the **hints.jni()** accessor or declared directly in the **jni** section of **reachability-metadata.json**.

## 3. Identify Errors from Symptoms

| Symptom | Area to check first |
| --- | --- |
| MissingReflectionRegistrationError | Reflection lookup, method invocation, constructor, field access, or JDK proxy |
| MissingJNIRegistrationError | Native code calling FindClass, GetMethodID, GetFieldID, or manipulating Java objects |
| ClassNotFoundException | Class missing from dependencies/classpath, wrong class name, or wrong classloading config |
| NoSuchMethodException in native while JVM works | Dynamically invoked method/constructor is unregistered or signature does not match |
| ClassCastException when calling a service via proxy | Proxy/interface created differs from the type expected by the caller |
| Error occurs only when serializing/deserializing one object type | Distinguish Java serialization from JSON/XML binding; check metadata for the right mechanism |
| UnsatisfiedLinkError | Native library missing, symbol missing, or ABI incompatible; this is not automatically a JNI metadata bug |
| Cannot read config/resource file in native | Resource not included in the image or code treats a resource URL as a filesystem path |

MissingReflectionRegistrationError and MissingJNIRegistrationError are reachability registration errors. Do not catch broad Throwable and swallow them. Doing so hides the error and can cause the application to return wrong results without reporting the root cause.

A missing metadata error often surfaces only when executing the specific code path that uses the dynamic element. Therefore, a passing health endpoint or ApplicationContext startup does not prove metadata is complete.

## 4. General Diagnostic Workflow

~~~mermaid
flowchart TD
    A["Native executable fails on a feature"] --> B["Capture full error and stack trace"]
    B --> C{"Which dynamic access?"}
    C -->|Class / method / field| R["Inspect reflection"]
    C -->|Proxy.newProxyInstance| P["Inspect ordered interfaces"]
    C -->|Object streams| S["Inspect Java serialization"]
    C -->|Native C/C++ call| J["Inspect JNI registrations"]
    C -->|Resource lookup| F["Inspect resource inclusion and URL usage"]
    R --> V["Add the smallest matching hint"]
    P --> V
    S --> V
    J --> V
    F --> V
    V --> T["Test hint registration and rebuild"]
    T --> N["Run the same scenario on native executable"]
    N --> Q{"All relevant paths pass?"}
    Q -->|No| B
    Q -->|Yes| D["Keep regression test and metadata"]
~~~

Follow this order:

1. Reproduce the failure with the native executable and capture the full stack trace.
2. Identify the library and call site performing the dynamic access.
3. Determine whether it is reflection, JDK proxy, Java serialization, JSON binding, or JNI.
4. Check whether Spring AOT or the dependency already provides hints.
5. Add metadata only for the elements actually accessed.
6. Write a test for the hint and re-run the exact business flow on the native executable.

Do not start by registering all constructors, methods, and fields across entire packages. That bloats the image, obscures the root cause, and retains unnecessary elements.

## 5. Check Reflection

### 5.1. Cases That Commonly Need Reflection Metadata

Reflection can arise from:

- Class.forName(className) when className comes from a config file or database;
- getDeclaredConstructor() followed by newInstance();
- getDeclaredMethod() followed by Method.invoke();
- accessing fields via Field.get()/Field.set();
- MethodHandles.Lookup;
- frameworks scanning annotations or invoking private methods;
- mapping, ORM, serializer, or plugin loader libraries.

Native Image can resolve certain reflection calls automatically when the class and arguments are statically known. For example, Class.forName("com.example.InvoiceHandler") with a constant class name can be analyzed at build time. If the class name is only known when reading runtime configuration, corresponding metadata must be declared.

Identify the exact access level required:

- only looking up the class;
- listing constructors or methods;
- invoking a specific constructor/method;
- reading/writing a field;
- allocating an object without calling a constructor.

These requirements are not equivalent. Registering a type does not automatically mean every method and field can be invoked or accessed via reflection.

### 5.2. Using RuntimeHintsRegistrar

For application-managed components, you can register hints with the Spring API. For example, a legacy library invoking readPayload(String) via reflection:

~~~java
import java.lang.reflect.Method;

import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.util.ReflectionUtils;

public class BillingRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        Method method = ReflectionUtils.findMethod(
            LegacyInvoiceAdapter.class,
            "readPayload",
            String.class
        );
        hints.reflection().registerMethod(method, ExecutableMode.INVOKE);
    }
}
~~~

Activate the registrar with ImportRuntimeHints:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(BillingRuntimeHints.class)
class NativeHintsConfiguration {
}
~~~

Place ImportRuntimeHints near the component needing the hint when possible. The registrar is invoked by Spring AOT at build time; it is not code meant to run on every incoming request.

If multiple members need registration, use the hints.reflection() API to declare specific types, constructors, methods, or fields. Choose ExecutableMode.INVOKE when calling methods/constructors; register introspection-only permissions if the library only inspects metadata without invoking executables.

### 5.3. DTOs Bound Outside Spring MVC

Spring Boot usually infers reflection hints for controller request/response types. However, if the application calls WebClient, RestClient, Jackson, or a codec directly inside a method body, the AOT engine might not infer all DTOs.

Use RegisterReflectionForBinding for data types needing binding:

~~~java
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.stereotype.Component;

@Component
@RegisterReflectionForBinding(PartnerInvoiceResponse.class)
class PartnerInvoiceClient {

    PartnerInvoiceResponse fetchInvoice(String invoiceId) {
        // Call HTTP client and deserialize response into DTO.
        return callPartner(invoiceId);
    }
}
~~~

This annotation registers members needed for binding such as constructors, fields, properties, and record components; nested types used inside are also considered. Check the annotation API for your project's Spring Boot/Spring Framework version.

If a DTO contains a nested type not inferred from known structures, register that type or add the appropriate binding annotation. Do not confuse JSON binding hints with Java serialization metadata covered later.

### 5.4. JSON Metadata for Reflection

When static declarations are needed or a library does not integrate with Spring RuntimeHints, use reachability-metadata.json. Example allowing only a required method and constructors:

~~~json
{
  "reflection": [
    {
      "type": "com.example.billing.LegacyInvoiceAdapter",
      "allDeclaredConstructors": true,
      "methods": [
        {
          "name": "readPayload",
          "parameterTypes": ["java.lang.String"]
        }
      ]
    }
  ]
}
~~~

Declare fields if code actually reads/writes fields via reflection:

~~~json
{
  "reflection": [
    {
      "type": "com.example.billing.LegacyInvoice",
      "fields": [
        {"name": "internalCode"}
      ]
    }
  ]
}
~~~

Options like allDeclaredMethods, allPublicMethods, allDeclaredFields, and allPublicFields are convenient for libraries with broad contracts, but they can inflate image size. Prefer explicit member lists when call sites are known.

## 6. Check Proxies

### 6.1. Distinguish JDK Dynamic Proxies from CGLIB

Spring can use two proxy mechanisms:

| Mechanism | How it is created | What to check |
| --- | --- | --- |
| JDK dynamic proxy | Generates a proxy class from an interface list via Proxy.newProxyInstance | Register the exact interface list in the exact order |
| CGLIB proxy | Generates a subclass of the target class | Verify Spring AOT recognized the bean and generated proxy bytecode |

Spring AOT can generate bytecode for proxies Spring needs when processing the ApplicationContext. Spring ProxyHints registers JDK interface proxies. Class-based CGLIB proxies follow a separate AOT path: Spring must recognize the bean/proxy while analyzing the context and emit the corresponding bytecode. ClassHintUtils helps infer hints for Spring-managed proxy types. JDK proxies created dynamically by other libraries may still need separate proxy hints; do not use JDK proxy hints to fix CGLIB errors.

With CGLIB, final classes, final methods, or private methods cannot be overridden to apply advice. If a proxy is generated by a library using runtime code generation, check the library's AOT compatibility; simply adding an interface list will not solve dynamic subclass generation.

### 6.2. Register JDK Proxies with Spring

Example of a client creating a proxy for two interfaces:

~~~java
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class PartnerProxyHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.proxies().registerJdkProxy(
            PartnerGateway.class,
            AutoCloseable.class
        );
    }
}
~~~

Register the registrar via ImportRuntimeHints as in the reflection examples. The interface list must mirror the exact combination passed to Proxy.newProxyInstance.

### 6.3. JSON Metadata for JDK Proxies

Example reachability metadata:

~~~json
{
  "reflection": [
    {
      "type": {
        "proxy": [
          "com.example.partner.PartnerGateway",
          "java.lang.AutoCloseable"
        ]
      }
    }
  ]
}
~~~

Interface ordering is part of the proxy definition. If code creates a proxy with a different combination or order, this entry may not match. Record the interface list right at the Proxy.newProxyInstance call site.

### 6.4. Inspect Proxies Generated by Spring AOT

If errors involve Transactional, Async, method security, or advisors:

1. Determine whether the bean uses a JDK proxy or a class-based proxy.
2. Confirm the bean definition is present in the AOT context.
3. Check whether the Bean return type is specific enough for Spring AOT to identify the target class.
4. Check that generated proxy bytecode was compiled and packaged.
5. Confirm the advised method can be proxied according to JDK/CGLIB rules.

If a Bean returns an overly broad interface while AOT needs to analyze annotations or lifecycle methods on the implementation, consider declaring a more concrete return type.

## 7. Check Serialization

### 7.1. Distinguish Java Serialization from JSON Binding

Both mechanisms are often casually called "serialization", but their metadata differs:

| Mechanism | Examples | Appropriate hint |
| --- | --- | --- |
| Java object serialization | ObjectOutputStream, ObjectInputStream, class implements Serializable | Serialization metadata |
| JSON binding | Jackson serializing/deserializing DTOs | Reflection/binding hints |
| XML binding | JAXB or XML mappers | Reflection and library-specific metadata |
| Message codec | Codecs converting payloads to objects | Check the codec contract and bound types |

RegisterReflectionForBinding is for data-type binding such as JSON. hints.serialization().registerType(...) is for Java serialization. The two mechanisms are not interchangeable.

### 7.2. Register Java Serialization in Spring

Example application reading/writing a legacy class implementing Serializable:

~~~java
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class LegacySerializationHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.serialization().registerType(
            LegacyInvoiceEnvelope.class
        );
    }
}
~~~

Register the registrar with ImportRuntimeHints. Spring Framework provides RuntimeHints.serialization() to declare Java serialization; use this accessor rather than raw reflection hints.

~~~java
hints.serialization().registerType(LegacyInvoiceEnvelope.class);
~~~

The snippet above fits the Spring Framework 6.x API. In newer Spring Framework Javadoc, SerializationHints and RuntimeHints.serialization() are marked deprecated in favor of reflection type hints with the Java serialization flag:

~~~java
hints.reflection().registerType(
    LegacyInvoiceEnvelope.class,
    typeHint -> typeHint.withJavaSerialization(true)
);
~~~

Pick the approach matching your project's actual Spring Framework version; do not call deprecated APIs merely because older examples remain in other docs.

Do the same for every class actually serialized; also check subclasses, field types, and types referenced in the object graph.

### 7.3. JSON Metadata for Java Serialization

For a regular class:

~~~json
{
  "reflection": [
    {
      "type": "com.example.legacy.LegacyInvoiceEnvelope",
      "serializable": true
    }
  ]
}
~~~

If a proxy class is also serialized, the proxy metadata needs the serializable flag:

~~~json
{
  "reflection": [
    {
      "type": {
        "proxy": [
          "com.example.partner.PartnerGateway",
          "java.io.Serializable"
        ]
      },
      "serializable": true
    }
  ]
}
~~~

### 7.4. Do Not Relax ObjectInputFilter to Fix Errors

If the application accepts Java serialized objects from external sources, use ObjectInputFilter to restrict which classes may be deserialized. GraalVM can recognize classes listed in constant filters to register serialization metadata.

Do not use overly broad wildcards or permit all classes just to avoid native errors. Broader metadata enlarges the image and makes the deserialization surface harder to control.

## 8. Check JNI

### 8.1. Which Access Direction Does JNI Metadata Cover?

JNI allows native code to access Java:

- FindClass looks up a class by name;
- GetMethodID/GetStaticMethodID looks up a method;
- GetFieldID/GetStaticFieldID looks up a field;
- NewObject creates an object;
- Call<Type>Method invokes a Java method;
- AllocObject allocates an object without invoking a constructor.

Native Image cannot predict every class/member name that C/C++ code will look up. Those types and members must be declared in JNI metadata.

### 8.2. Distinguish JNI Metadata Errors from Library Loading Errors

| Error | Meaning | What to check |
| --- | --- | --- |
| MissingJNIRegistrationError | Native code accessed an unregistered Java type/member | JNI reachability metadata |
| UnsatisfiedLinkError: no ... in java.library.path | Native library not found | Packaging of .so/.dll/.dylib, paths, and loader configuration |
| undefined symbol | Native library lacks symbol or ABI mismatch | Library version, linker, and native dependencies |
| wrong ELF class or architecture error | Native binary targets the wrong architecture | Build artifact for the target OS/CPU |

JNI metadata does not package native library files and does not fix ABI issues. Before adding hints, verify the native library actually loads successfully.

### 8.3. JNI Example: Looking Up a Class and Invoking a Method

Suppose C code invokes a Java callback:

~~~c
jclass callbackClass = (*env)->FindClass(
    env,
    "com/example/nativebridge/NativeCallback"
);

jmethodID callbackMethod = (*env)->GetMethodID(
    env,
    callbackClass,
    "onComplete",
    "(Ljava/lang/String;)V"
);
~~~

Metadata must allow JNI access to the class and the onComplete(String) method:

~~~json
{
  "jni": [
    {
      "type": "com.example.nativebridge.NativeCallback",
      "jniAccessible": true,
      "methods": [
        {
          "name": "onComplete",
          "parameterTypes": ["java.lang.String"]
        }
      ]
    }
  ]
}
~~~

If native code reads field nativeHandle, add that specific field:

~~~json
{
  "jni": [
    {
      "type": "com.example.nativebridge.NativeCallback",
      "jniAccessible": true,
      "fields": [
        {"name": "nativeHandle"}
      ]
    }
  ]
}
~~~

jniAccessible allows native code to access the type via JNI. It does not automatically grant access to every method and field; declare the members native code actually looks up by ID.

### 8.4. Register JNI via Spring RuntimeHints

Spring Framework provides the RuntimeHints.jni() accessor. This accessor returns a ReflectionHints instance exported as JNI metadata, separate from standard reflection metadata.

Example where native code calls public methods and reads public fields:

~~~java
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class NativeBridgeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.jni().registerType(
            NativeCallback.class,
            MemberCategory.INVOKE_PUBLIC_METHODS,
            MemberCategory.PUBLIC_FIELDS
        );
    }
}
~~~

If native code needs private or package-private methods or fields, choose the corresponding declared categories, such as INVOKE_DECLARED_METHODS or DECLARED_FIELDS. Do not add all member categories if JNI uses only a few members. Register the registrar with ImportRuntimeHints as in earlier examples.

The RuntimeHints.jni() API exists in Spring Framework 6.x; verify the Javadoc for the exact version managed by your project's Spring Boot release. If not using this API or if metadata belongs to a third-party library, declare the jni section directly in GraalVM reachability metadata.

If native code uses AllocObject, declare unsafeAllocated for that type. If native code calls a constructor via NewObject, declare the required constructor in JNI metadata.

## 9. Place Reachability Metadata in the Right Location

For application-managed metadata, place the file on the classpath under META-INF/native-image. Example:

~~~text
src/main/resources/
└── META-INF/
    └── native-image/
        └── com.example/
            └── billing-service-additional-hints/
                └── reachability-metadata.json
~~~

Static metadata directories should avoid colliding with the location where Spring AOT automatically generates hints:

~~~text
META-INF/native-image/{groupId}/{artifactId}/
~~~

Do not edit generated files inside target/ or build/ to patch errors. Those files can be overwritten on the next build. Fix the RuntimeHintsRegistrar, annotations, or source metadata under src/main/resources.

Example file combining mechanisms:

~~~json
{
  "reflection": [
    {
      "type": "com.example.billing.LegacyInvoiceAdapter",
      "methods": [
        {
          "name": "readPayload",
          "parameterTypes": ["java.lang.String"]
        }
      ]
    },
    {
      "type": {
        "proxy": [
          "com.example.partner.PartnerGateway",
          "java.io.Closeable"
        ]
      }
    },
    {
      "type": "com.example.legacy.LegacyInvoiceEnvelope",
      "serializable": true
    }
  ],
  "jni": [
    {
      "type": "com.example.nativebridge.NativeCallback",
      "jniAccessible": true,
      "methods": [
        {
          "name": "onComplete",
          "parameterTypes": ["java.lang.String"]
        }
      ]
    }
  ]
}
~~~

This is an illustrative example. Replace classes, members, and interfaces with actual names; validate JSON against the schema shipped with your GraalVM Native Image version. Do not mix old and new schemas simply because the files share metadata names.

## 10. Collect Hints Using the GraalVM Tracing Agent

When you do not yet know which library performs dynamic access, the Tracing Agent can observe the application on the JVM and generate corresponding metadata.

### 10.1. Run the Application with the Agent

Use a GraalVM JDK containing the Native Image Tracing Agent:

~~~bash
java \
  -Dspring.aot.enabled=true \
  -agentlib:native-image-agent=config-output-dir=target/native-agent \
  -jar target/billing-service.jar
~~~

After the application starts:

1. Invoke endpoints that use reflection and JSON binding.
2. Exercise flows that create JDK proxies or initialize integration adapters.
3. Trigger business flows involving Java serialization or JNI.
4. Execute both success and failure branches that use those components.
5. Shut down the application cleanly so the agent writes configuration files.

The agent records dynamic accesses that occurred during that run. It cannot discover a plugin, serializer, or business branch that was never executed.

### 10.2. Run the Agent via the Test Suite

You can attach the agent to the JVM running integration tests to replay scenarios. This helps gather metadata systematically, though test frameworks also generate many reflection/proxy/resource accesses unnecessary in production.

If using the test suite:

- prioritize tests covering business flows that actually run in the native application;
- use the agent's access-filter/caller-filter to exclude accesses belonging solely to test infrastructure;
- keep application metadata separate from test metadata;
- never copy the entire output without reviewing it first.

### 10.3. Review Agent-Generated Metadata

After the agent finishes:

- identify which entries belong to application libraries versus JUnit/mocking frameworks;
- verify classes and methods actually exist in pinned dependency versions;
- remove overly broad or unrelated entries;
- merge into source metadata at the proper location;
- rebuild the native image and re-run the scenario that produced each entry.

Filenames and agent output formats can change across GraalVM releases. Keep the schema generated by your agent version or convert it to the schema supported by your current Native Image version; do not mechanically rename files and assume the builder can read them.

## 11. Enable Reachability Metadata Diagnostic Modes

Recent GraalVM releases offer stricter metadata checking modes. You can enable --exact-reachability-metadata at build time to catch missing registrations early:

~~~bash
native-image \
  --exact-reachability-metadata \
  -jar target/billing-service.jar \
  billing-service
~~~

If you want to scope checking, some releases support specifying packages:

~~~bash
native-image \
  --exact-reachability-metadata=com.example.billing,com.example.partner \
  -jar target/billing-service.jar \
  billing-service
~~~

When running the executable, use reporting mode:

~~~bash
./billing-service \
  -XX:MissingRegistrationReportingMode=Warn
~~~

Warn helps observe accesses missing metadata during testing. When you want CI to fail even if code accidentally swallows registration errors with catch(Throwable), use:

~~~bash
./billing-service \
  -XX:MissingRegistrationReportingMode=Exit
~~~

These options depend on the GraalVM version. Check native-image --help and your distribution's documentation before adding them to pipelines. Do not enable diagnostic modes only on the JVM and conclude native image metadata is complete; you must run the native executable itself.

## 12. Test Custom Hints

### 12.1. Unit Tests for RuntimeHintsRegistrar

Spring provides RuntimeHintsPredicates to verify a registrar registers the expected hints. Example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class BillingRuntimeHintsTests {

    @Test
    void registersLegacyMethodInvocation() {
        RuntimeHints hints = new RuntimeHints();
        new BillingRuntimeHints().registerHints(
            hints,
            getClass().getClassLoader()
        );

        assertThat(
            RuntimeHintsPredicates.reflection()
                .onMethod(LegacyInvoiceAdapter.class, "readPayload")
                .invoke()
        ).accepts(hints);
    }
}
~~~

This test verifies the registrar produces the right hint. It does not prove the native executable packaged the metadata or that all runtime paths are covered.

### 12.2. Inspect the Executable JAR

After packaging, confirm generated/static hints are inside the artifact:

~~~bash
jar tf target/billing-service.jar | grep META-INF/native-image
~~~

Verify:

- Spring AOT generated hints are in the JAR;
- the application's reachability-metadata.json is on the classpath;
- no stale files were misplaced outside the metadata directory;
- dependencies containing reachability metadata at the expected version are packaged.

Do not inspect only the source directory. Native Image reads metadata from the build classpath; unpackaged files have no effect.

### 12.3. Run Contract Tests on the Native Executable

Choose representative scenarios:

| Category | Scenarios to run |
| --- | --- |
| Reflection | Load class by name, invoke constructor/method, read/write field |
| Proxy | Create exact JDK proxy combination; call method via proxy; verify Spring AOP advice |
| JSON binding | Deserialize request/response DTOs with nested fields, records, and custom serializers |
| Java serialization | Write and read back each permitted legacy class |
| JNI | Call native method, callback from C/C++ to Java, access field/method via JNI |
| Integration | Exercise endpoints or message flows using third-party libraries |

Native tests must invoke the actual business branches. Calling only a health endpoint will not detect missing metadata in a serializer or JNI adapter used only by another feature.

## 13. Other Causes Easily Confused with Missing Metadata

| Symptom | Other possible cause | How to verify |
| --- | --- | --- |
| Class not found | Dependency missing from artifact or wrong class name | Inspect dependency graph and JAR contents |
| Bean does not exist | Profile or Conditional evaluated differently during AOT | Check profiles/properties during AOT processing |
| Proxy does not work | Bean definition not processed by AOT or bean return type too broad | Check generated context and Bean return type |
| JSON missing fields | Wrong naming strategy, constructor binding, or custom serializer | Test JSON contract on JVM and native |
| Java serialization fails | Class lacks Serializable, serialVersionUID, or invalid object graph | Test serialization contract independently |
| JNI fails to load | Missing native library, symbol, or ABI mismatch | Check native files and linker/runtime |
| Resource unreadable | Wrong path or URL treated as filesystem path | Use getResourceAsStream and check resource metadata |
| Fails only on one OS/CPU | Native library or build artifact targets wrong platform | Check OS, architecture, libc, and native dependencies |

If a class is missing from dependencies or a bean was excluded by a build-time condition, adding a reflection hint cannot bring it back. Fix the classpath or AOT configuration first.

## 14. Troubleshooting by Category

| Symptom | Check | Remedy |
| --- | --- | --- |
| MissingReflectionRegistrationError at Class.forName | Does class name come from runtime property/database? | Register type or switch to static class registry if appropriate |
| Failure at Method.invoke | Do method name and parameter types match? | Register exact method signature with INVOKE permission |
| Failure at Field.get/Field.set | Is the field accessed dynamically? | Register exact field or binding hint for DTO |
| JDK proxy cannot be created | Are interface list and order exact? | Add JDK proxy hint for exact interface list |
| Spring transaction/security proxy failure | Did Spring AOT recognize the bean/proxy? | Check bean type, proxy strategy, and generated bytecode |
| JSON codec fails on WebClient DTO | Is DTO among types Spring can infer? | Use RegisterReflectionForBinding or custom hints |
| ObjectInputStream fails in native | Is class registered for Java serialization? | Use registerJavaSerialization or serializable metadata |
| MissingJNIRegistrationError | Which class/member does native code call? | Declare type, method, and field in jni metadata |
| UnsatisfiedLinkError | Are native library and symbols available? | Fix packaging, library path, or ABI; do not merely add JNI hints |
| Agent did not record expected entry | Did the scenario actually execute that code? | Add test/call path and re-run the agent |
| Hint exists in source but native still fails | Is file on the artifact classpath? | Check JAR, build output, and native build command |
| JVM test passes while native test fails | Was the dynamic feature exercised in JVM tests? | Enable exact metadata mode and run same scenario on native |

## 15. Practical Workflow with the Billing Service

Suppose the billing service uses a legacy library to load handlers by class name, calls a partner gateway via a JDK proxy, deserializes legacy payloads, and receives callbacks from a native SDK.

**Step 1 — reproduce each error**

- Call the endpoint using the handler configured by class name.
- Execute a request through the partner gateway proxy.
- Read a legacy payload via Java serialization.
- Call the native SDK to trigger the callback.
- Save the native executable stack traces.

**Step 2 — classify each access**

- Handler by class name: reflection.
- Partner gateway: determine JDK proxy versus CGLIB.
- Legacy payload: Java serialization.
- Native SDK callback: JNI.

**Step 3 — add hints using the right mechanism**

- Use RuntimeHintsRegistrar for application-managed method reflection, JDK proxy, and JNI hints.
- Use RegisterReflectionForBinding if the partner response is a DTO deserialized via JSON.
- Use hints.serialization().registerType (Spring Framework 6.x) or reflection type hint with withJavaSerialization(true) in newer APIs for legacy classes.
- Use hints.jni().registerType or reachability-metadata.json with a jni section for callbacks invoked by native code.

**Step 4 — verify hints**

Write unit tests using RuntimeHintsPredicates for the registrar. Confirm JSON is valid and present on the executable JAR classpath.

**Step 5 — run the Tracing Agent**

Run the application on the JVM with AOT enabled, attach the Tracing Agent, and exercise all flows above. Review the output, filter out test-infrastructure entries, and merge the required metadata.

**Step 6 — build and run native**

Enable --exact-reachability-metadata per your GraalVM version, run the executable with MissingRegistrationReportingMode=Exit in a test environment, and replay all scenarios.

**Step 7 — keep regression tests**

Every category of missing metadata that caused a failure must have a test reproducing that access path. When upgrading Spring Boot, GraalVM, or JNI/serializer dependencies, re-run this suite.

## 16. Checklist Before Concluding the Issue Is Fixed

- [ ] Saved stack traces and identified dynamic access call sites.
- [ ] Distinguished reflection, JDK proxy, CGLIB proxy, Java serialization, JSON binding, and JNI.
- [ ] Checked whether Spring AOT generates hints automatically for that contract.
- [ ] Verified the class/member actually exists in dependencies and on the classpath.
- [ ] Reflection hints include only required constructors, methods, and fields.
- [ ] JDK proxy hints use the exact interface list and order.
- [ ] Did not mechanically use JDK proxy metadata to treat CGLIB proxies.
- [ ] JSON DTOs use appropriate binding hints.
- [ ] Java serialization classes have dedicated serialization metadata.
- [ ] JNI metadata declares the exact classes/members accessed by native code.
- [ ] Native libraries and ABI were verified separately from JNI metadata.
- [ ] Tracing Agent ran through all required business flows.
- [ ] Agent output was reviewed and test-infrastructure-only metadata was stripped.
- [ ] Metadata resides in source resources and is present in the executable artifact.
- [ ] RuntimeHintsRegistrar has unit tests using RuntimeHintsPredicates.
- [ ] Native executable ran reflection/proxy/serialization/JNI contract tests.
- [ ] Tested missing-registration reporting mode in CI or a test environment.
- [ ] No catch(Throwable) block swallows registration errors.

**Takeaway:** metadata must accurately describe the type of dynamic access. Reflection needs types/members; JDK proxies need ordered interface lists; Java serialization needs serializable class registrations; JSON binding needs binding hints; JNI needs dedicated declarations for types/members looked up by native code. Pinpoint the call site, add minimal hints, test the hints, and replay the exact business path on the native executable.

## References

- [Spring Framework — Ahead of Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html): RuntimeHints, RuntimeHintsRegistrar, ImportRuntimeHints, reflection, serialization, proxies, and testing hints.
- [Spring Boot — Advanced Native Images Topics](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html): tracing agent, custom hints, RegisterReflectionForBinding, and static hint file locations.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): differences between JDK dynamic proxies and CGLIB.
- [Spring Framework — RuntimeHints API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/aot/hint/RuntimeHints.html): reflection, proxy, serialization, and JNI accessors.
- [Spring Framework — TypeHint.Builder API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aot/hint/TypeHint.Builder.html): declaring members and Java serialization in type hints.
- [Spring Framework — ProxyHints API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aot/hint/ProxyHints.html): registering JDK interface proxies.
- [Spring Framework — ClassHintUtils API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aot/hint/support/ClassHintUtils.html): inferring hints for Spring-managed JDK proxies and CGLIB subclasses.
- [GraalVM Native Image — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/): reflection, proxy, serialization, JNI, JSON schema, and exact reachability metadata.
- [GraalVM Native Image — Collect Metadata with the Tracing Agent](https://www.graalvm.org/latest/reference-manual/native-image/metadata/AutomaticMetadataCollection/): collecting metadata from a JVM app and filtering agent output.
- [Spring Framework — RuntimeHintsPredicates API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aot/hint/predicate/RuntimeHintsPredicates.html): testing reflection, resource, serialization, and proxy hints.
