# Generic Signature Lost After Registration or Packaging

## 1. Symptom: Function Is in the Catalog, but Input No Longer Has the Right Type

Suppose a **Spring Cloud Function** application defines an order-accepting function:

~~~java
@Bean
public Function<OrderEvent, OrderReceipt> acceptOrder() {
    return event -> new OrderReceipt(event.orderId(), "ACCEPTED");
}
~~~

When the function is looked up via `FunctionCatalog` and invoked over HTTP, a message broker, or a serverless adapter, the framework typically needs to know `OrderEvent` is the input type to deserialize JSON data into a Java object. Yet after refactoring registration, adding a proxy, changing a packaging plugin, or switching to a native image, several errors can appear:

- `FunctionCatalog.getNames(null)` still contains `acceptOrder`, yet the adapter passes a `LinkedHashMap` instead of `OrderEvent`.
- `ClassCastException` occurs when the lambda accesses `event.orderId()`.
- Input/output metadata in Actuator or logs resolves as `Object` instead of the DTO.
- A composition `normalize|acceptOrder` suddenly fails to convert results between the two steps.
- The program works when started from the IDE, yet fails in a packaged JAR or native executable.
- `Function<Flux<OrderEvent>,Flux<OrderReceipt>>` receives elements of the wrong type and only errors once a subscriber consumes the stream.
- A dynamically registered lambda works fine when invoked directly with a POJO, yet the converter cannot determine the target when receiving JSON bytes.

This lesson belongs to the **Diagnostics** chapter, titled **"Generic Signature Lost After Registration or Packaging"**, within the `SPRING_CLOUD_FUNCTION` module. This module focuses on reusable business logic using `Supplier`, `Function`, and `Consumer`, looked up and composed via `FunctionCatalog`, then deployed over HTTP, events, or serverless runtimes.

**Core principle:** having a bean and a name in the catalog **does not guarantee** that type information for `I` and `O` in `Function<I,O>` is intact. Conversely, receiving a `Map` does not by itself prove the JAR stripped metadata; a native deserializer might have converted the data into a `Map`.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish **Java type erasure** from **generic `Signature` metadata** in bytecode.
2. Explain why `@Bean Function<OrderEvent,OrderReceipt>` normally preserves types whereas raw `@Bean Function` does not.
3. Use `FunctionRegistration` and `FunctionTypeUtils` when registering lambdas during functional startup.
4. Identify differences between generics on a factory method, on a class interface, and on a lambda/proxy runtime class.
5. Preserve nested generic layers in `Message<OrderEvent>`, `Flux<OrderEvent>`, `Supplier<Flux<T>>`, and `List<T>`.
6. Compare type information in source code, the Spring context, the catalog, and the actually deployed JAR.
7. Investigate shading/obfuscation tools, AOP proxies, and AOT/native images without blaming every issue on the same cause.
8. Write tests covering signatures, the catalog, HTTP/Stream/serverless adapters, and packaged artifacts.

## 2. Java Erasure Does Not Erase Every Generic Declaration

Java generics are primarily checked at compile time. In bytecode, calling `Function.apply` fundamentally operates on erased types such as `apply(Object)`. However, the compiler can record generic declarations in the class or method `Signature` attribute.

Therefore, two facts are simultaneously true:

- **A runtime object does not necessarily carry full type arguments.** A synthetic lambda class may appear only as `Function` without `OrderEvent`/`OrderReceipt`.
- **A class or method declaration can still retain type arguments for reflection.** `@Bean Function<OrderEvent,OrderReceipt>` or `class OrderConverter implements Function<OrderEvent,OrderReceipt>` carries metadata for Spring to inspect.

~~~mermaid
flowchart TD
    SOURCE["Declaration Function<OrderEvent,OrderReceipt>"] --> COMPILER["javac"]
    COMPILER --> ERASED["JVM method: apply(Object)"]
    COMPILER --> SIGNATURE["Signature attribute on method/class"]
    SIGNATURE --> SPRING["Spring ResolvableType / SCF type discovery"]
    SPRING --> CATALOG["FunctionCatalog wrapper"]
    CATALOG --> CONVERTER["Convert JSON to OrderEvent"]
~~~

| Concept to distinguish | Example | Meaning |
| --- | --- | --- |
| Erased method signature | `apply(Object)` | Normal in Java |
| Generic declaration | `Function<OrderEvent,OrderReceipt>` | Readable via reflection if preserved |
| Spring bean type | Declared return type of `@Bean` factory | One source for Spring generic inference |
| SCF registration type | `FunctionRegistration.type(...)` | Supplies types during dynamic registration |
| Adapter input runtime type | `Map`, `String`, `byte[]`, or `OrderEvent` | Result after converter/deserializer |

**There is no property to "disable Java type erasure."** The proper fix is declaring or supplying metadata at the boundary the framework inspects.

## 3. Java 17+ Example with Concrete DTOs and Function

Examples in this lesson use record DTOs:

~~~java
package demo.generic;

public record OrderEvent(
    String orderId,
    long amountCents
) {}
~~~

~~~java
package demo.generic;

public record OrderReceipt(
    String orderId,
    String status
) {}
~~~

And an implementation with an explicit generic interface:

~~~java
package demo.generic;

import java.util.function.Function;

public final class OrderConverter
        implements Function<OrderEvent, OrderReceipt> {

    @Override
    public OrderReceipt apply(OrderEvent event) {
        return new OrderReceipt(event.orderId(), "ACCEPTED");
    }
}
~~~

Proper Spring configuration:

~~~java
package demo.generic;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TypedOrderFunctions {

    @Bean
    public Function<OrderEvent, OrderReceipt> acceptOrder() {
        return new OrderConverter();
    }
}
~~~

This is the preferred design when inputs and outputs are fixed DTOs. Metadata exists both on the return type of `acceptOrder()` and on the interface implemented by `OrderConverter`.

### 3.1. Why Does the @Bean Return Type Matter?

Spring Cloud Function lazily registers eligible functional beans from `ApplicationContext` into `FunctionCatalog`. For a bean declared via `@Bean`, the factory method's generic return type is a key source of type inference.

If changed to:

~~~java
@Bean
public Object acceptOrder() {
    return new OrderConverter();
}
~~~

Spring sees only the declared return type `Object` on the factory method. Depending on bean discovery mechanics, type information may be lost or the function may not be recognized early as a functional bean.

If changed to:

~~~java
@SuppressWarnings("rawtypes")
@Bean
public Function acceptOrder() {
    return new OrderConverter();
}
~~~

the method exposes only raw `Function`. The catalog can find the name, yet concrete type arguments are absent from the method signature.

### 3.2. Function<Object,Object> Is a Different Contract

~~~java
@Bean
public Function<Object, Object> acceptAnything() {
    return payload -> payload;
}
~~~

This function genuinely asks to handle `Object`. If it receives a JSON object and the converter produces `LinkedHashMap`, that is valid behavior rather than a Jackson bug.

Do not work around it with an unchecked cast:

~~~java
Function<OrderEvent, OrderReceipt> typed =
    (Function<OrderEvent, OrderReceipt>) raw;
~~~

A cast neither adds registration metadata nor turns a `Map` into a DTO.

## 4. Factory Method Type Declaration Differs from a Lambda's Runtime Class

Consider:

~~~java
Function<OrderEvent, OrderReceipt> lambda =
    event -> new OrderReceipt(event.orderId(), "ACCEPTED");
~~~

The `OrderEvent`/`OrderReceipt` types are known to the compiler at **the variable declaration site**. Yet when passing only the object to a raw API:

~~~java
void register(String name, Function function) {
    // API accepts only raw Function without type arguments.
}
~~~

the variable's generic information does not automatically attach as a runtime token inside `function`.

### 4.1. Why Does getClass() Mislead Diagnostics?

~~~java
System.out.println(lambda.getClass().getName());
System.out.println(
    java.util.Arrays.toString(
        lambda.getClass().getGenericInterfaces()
    )
);
~~~

A lambda can be a synthetic class; its reflected generic interfaces do not necessarily expose full DTO types. That **does not prove the JAR stripped `Signature`**: the generic declaration may reside on a `@Bean` method rather than on the lambda's runtime class.

### 4.2. Named Classes Are Another Metadata Source

~~~java
public final class AcceptOrderFunction
        implements Function<OrderEvent, OrderReceipt> {

    @Override
    public OrderReceipt apply(OrderEvent event) {
        return new OrderReceipt(event.orderId(), "ACCEPTED");
    }
}
~~~

The interface declaration lives in `AcceptOrderFunction`'s class file. When available, Spring `ResolvableType` can read `Function<OrderEvent,OrderReceipt>` from the class hierarchy.

**Rule:** if a function is registered as a dynamic lambda without a generic factory method to inspect, provide type metadata at registration; do not expect the framework to infer types from inside the lambda body.

## 5. Functional Registration: Role of FunctionRegistration

Spring Cloud Function supports declaring functional beans via `FunctionalSpringApplication` and `ApplicationContextInitializer<GenericApplicationContext>`. Official documentation states that `FunctionRegistration` encapsulates **both the function and its type information**, because information ordinarily inferred from a `@Bean` method can be lost under functional registration.

### 5.1. Minimal Example Using the Functional Model

~~~java
package demo.generic;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.SpringBootConfiguration;
import org.springframework.cloud.function.context.FunctionRegistration;
import org.springframework.cloud.function.context.FunctionalSpringApplication;
import org.springframework.cloud.function.context.catalog.FunctionTypeUtils;
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.support.GenericApplicationContext;

@SpringBootConfiguration
public class FunctionalDemoApplication
        implements ApplicationContextInitializer<GenericApplicationContext> {

    public static void main(String[] args) {
        FunctionalSpringApplication.run(
            FunctionalDemoApplication.class, args
        );
    }

    @Override
    public void initialize(GenericApplicationContext context) {
        Function<String, String> uppercase =
            value -> value.toUpperCase(Locale.ROOT);

        context.registerBean(
            "uppercase",
            FunctionRegistration.class,
            () -> new FunctionRegistration<>(uppercase)
                .type(FunctionTypeUtils.functionType(
                    String.class,
                    String.class
                ))
        );
    }
}
~~~

This is an example of the **functional startup model**, not code to inject into every standard `@SpringBootApplication`. When a project needs full Spring Boot autoconfiguration, consult the functional/hybrid mode docs for your dependency version.

### 5.2. Registering OrderEvent → OrderReceipt

Inside an initializer:

~~~java
Function<OrderEvent, OrderReceipt> handler =
    event -> new OrderReceipt(event.orderId(), "ACCEPTED");

context.registerBean(
    "acceptOrder",
    FunctionRegistration.class,
    () -> new FunctionRegistration<>(handler)
        .type(FunctionTypeUtils.functionType(
            OrderEvent.class,
            OrderReceipt.class
        ))
);
~~~

`FunctionTypeUtils.functionType(input,output)` returns `Type` metadata for a function; that differs from passing only `Function.class` or a raw lambda instance.

### 5.3. When Should You Use a Named Class Instead of Passing Class Arguments?

If a function uses nested generics or reactive signatures, a class implementing the full generic interface helps retain metadata.

~~~java
public final class StreamOrderFunction
        implements Function<Flux<OrderEvent>, Flux<OrderReceipt>> {

    @Override
    public Flux<OrderReceipt> apply(Flux<OrderEvent> input) {
        return input.map(event ->
            new OrderReceipt(event.orderId(), "ACCEPTED")
        );
    }
}
~~~

Class-based registration as documented:

~~~java
context.registerBean(
    "streamOrder",
    FunctionRegistration.class,
    () -> new FunctionRegistration<>(new StreamOrderFunction())
        .type(StreamOrderFunction.class)
);
~~~

The class's generic signature carries element types `OrderEvent` and `OrderReceipt`. Passing `FunctionTypeUtils.functionType(Flux.class,Flux.class)` supplies **only raw `Flux` types** without specifying each element's class.

## 6. Preserve Both Outer Generics and Element Types

Signatures vary in generic nesting depth:

~~~java
Function<OrderEvent, OrderReceipt>

Function<Message<OrderEvent>, Message<OrderReceipt>>

Function<Flux<OrderEvent>, Flux<OrderReceipt>>

Function<Flux<OrderEvent>, Mono<Void>>

Supplier<Flux<OrderEvent>>

Consumer<Flux<OrderEvent>>
~~~

Example:

~~~text
Function
 ├─ input: Flux
 │   └─ item: OrderEvent
 └─ output: Flux
     └─ item: OrderReceipt
~~~

If only `Function<Flux,Flux>` is preserved, the adapter is not told `OrderEvent` to convert JSON into individual items. If `Function<Message<?>,Message<?>>` is kept, the payload type inside `Message` remains unknown.

| Signature | Concrete metadata | Risk if lost |
| --- | --- | --- |
| `Function<OrderEvent,OrderReceipt>` | Input/output DTOs | JSON becomes Map or casting fails |
| `Function<Message<OrderEvent>,...>` | Payload type inside Message | Headers survive, payload is untyped |
| `Function<Flux<OrderEvent>,...>` | Publisher element type | Failure on subscribe/consume |
| `Supplier<Flux<OrderEvent>>` | Output item type | Binder/serializer lacks schema |
| `Consumer<Flux<OrderEvent>>` | Input item type | Consumer receives Map/String instead of DTO |
| `Function<List<OrderEvent>,...>` | Collection element type | Jackson builds `List<Map>` |

### 6.1. Do Not Confuse Mono<Void> with Input Payload Type

`Function<Flux<OrderEvent>,Mono<Void>>` takes a Flux of order events as input; `Mono<Void>` only signals completion or error, emitting no payload. Metadata specifying `Mono<Object>` is not equivalent when the output is completion-only.

### 6.2. List<OrderEvent> Differs from List.class

~~~java
List<OrderEvent> orders = mapper.readValue(
    json,
    new TypeReference<List<OrderEvent>>() {}
);
~~~

Whereas:

~~~java
List values = mapper.readValue(json, List.class);
// JSON object items may become LinkedHashMap.
~~~

Thus `FunctionTypeUtils.functionType(List.class,BatchReceipt.class)` is insufficient to represent `Function<List<OrderEvent>,BatchReceipt>`. You need an appropriate `ParameterizedType` or a complete generic method/class declaration.

## 7. FunctionCatalog Has the Name, Yet Converters Can Still Lack the Target Type

~~~java
FunctionCatalog catalog =
    applicationContext.getBean(FunctionCatalog.class);

System.out.println(catalog.getNames(null));

Function<OrderEvent, OrderReceipt> function =
    catalog.lookup(Function.class, "acceptOrder");
~~~

There are three independent questions:

1. Does `getNames(null)` contain `acceptOrder`?
2. Does `lookup` return a wrapper?
3. Do the wrapper and adapter know `OrderEvent` when receiving bytes or a `Message`?

**`lookup != null` only proves the function was found**; it does not prove JSON conversion works. Furthermore, when only one functional bean exists, single-function fallback can return that sole function even for a misspelled name. To verify exact names, pair inventory checks with:

~~~properties
spring.cloud.function.single-function-fallback-enabled=false
~~~

### 7.1. Raw Bean vs. Wrapper

~~~java
Function<OrderEvent, OrderReceipt> raw =
    applicationContext.getBean("acceptOrder", Function.class);

Function<OrderEvent, OrderReceipt> wrapped =
    catalog.lookup(Function.class, "acceptOrder");
~~~

The raw bean executes business logic, while the catalog wrapper may add type conversion and composition. Do not use `assertSame(raw,wrapped)` to validate contracts; inspect names, types, and behavior at the right boundary.

### 7.2. Receiving a Map Does Not Always Mean Generic Metadata Was Lost

If a Kafka native deserializer already returned a `Map`, or an HTTP body was an envelope whose `body` was decoded to a Map before reaching the function, the bug lies in the adapter/input contract. The generic signature may be completely intact. Always identify who constructed the Map.

## 8. Reading Generic Types on Factory Methods with ResolvableType

Spring Framework provides `ResolvableType` to resolve generic arguments from a method return type.

~~~java
package demo.generic;

import java.lang.reflect.Method;
import java.util.function.Function;

import org.springframework.core.ResolvableType;

public final class SignatureInspector {

    public static void main(String[] args) throws Exception {
        Method method =
            TypedOrderFunctions.class.getMethod("acceptOrder");

        ResolvableType type =
            ResolvableType.forMethodReturnType(method)
                .as(Function.class);

        System.out.println(
            type.getGeneric(0).resolve()
        ); // OrderEvent.class

        System.out.println(
            type.getGeneric(1).resolve()
        ); // OrderReceipt.class
    }
}
~~~

When `TypedOrderFunctions.acceptOrder()` declares `Function<OrderEvent,OrderReceipt>`, both type arguments resolve accurately.

### 8.1. Raw Function Behaves Differently

If the method is:

~~~java
@Bean
public Function acceptOrder() {
    return new OrderConverter();
}
~~~

the `ResolvableType` of the **method declaration** lacks concrete input/output type arguments. That proves the bug sits **in source registration**, with no need to blame the JAR or Jackson.

### 8.2. Do Not Look Only at bean.getClass()

~~~java
Object bean = context.getBean("acceptOrder");

System.out.println(bean.getClass().getName());
~~~

A runtime bean might be a synthetic lambda class, JDK proxy, or CGLIB subclass. Generic signatures on the **factory method/target class** can differ from those on the **runtime object class**. Consult multiple metadata sources instead of jumping to conclusions from a single `getClass()`.

## 9. Inspecting Implementing Classes and Unbound Type Variables

For a class implementing an interface:

~~~java
ResolvableType type =
    ResolvableType.forClass(OrderConverter.class)
        .as(Function.class);

Class<?> input = type.getGeneric(0).resolve();
Class<?> output = type.getGeneric(1).resolve();
~~~

`input` should resolve to `OrderEvent.class`, and `output` to `OrderReceipt.class`.

### 9.1. Inheriting Generics Through a Base Class

~~~java
public abstract class BaseFunction<I, O>
        implements Function<I, O> {
}

public final class ConcreteOrderFunction
        extends BaseFunction<OrderEvent, OrderReceipt> {

    @Override
    public OrderReceipt apply(OrderEvent event) {
        return new OrderReceipt(event.orderId(), "ACCEPTED");
    }
}
~~~

`ResolvableType` can walk the generic hierarchy to resolve `I`/`O`. However, if a class uses raw `BaseFunction`, unbound type variables still leave metadata missing.

### 9.2. Unspecialized Generic Classes

~~~java
public class GenericAuditFunction<T>
        implements Function<T, String> {

    @Override
    public String apply(T value) {
        return String.valueOf(value);
    }
}
~~~

This declaration knows only that `T` is a type variable, not that `T == OrderEvent`. A dynamically registered instance still needs additional metadata if the converter must construct `OrderEvent`.

## 10. AOP Proxies and FactoryBeans: Reflect on the Right Target

A function may be proxied for AOP/transactions/interceptors or created via a `FactoryBean`. The proxy class might expose only raw `Function`, even though the bean definition or target class retains type metadata.

### 10.1. Cases to Watch For

- A factory method declares return type `Object` even though the instance is a typed function.
- A JDK dynamic proxy exposes the raw `Function` interface.
- A custom decorator creates a new function declared only as `Function<Object,Object>`.
- `FactoryBean.getObjectType()` is too broad.
- A class implements a generic interface with unresolved type variables.
- Functional registration hides the target class behind a lambda supplier.

### 10.2. Safe Inspection Check

~~~java
String beanName = "acceptOrder";

log.info("beanType={}", context.getType(beanName));

Object bean = context.getBean(beanName);

log.info("runtimeBeanClass={}", bean.getClass().getName());
~~~

When using Spring AOP, you can inspect the target class via `AopUtils.getTargetClass(bean)` and compare it against the `@Bean` method/class declaration. Do not strip proxies or transactional interceptors without evidence that the proxy caused the issue.

**The presence of a proxy does not mean generics vanished.** Spring can infer types from the bean definition rather than the runtime proxy class.

## 11. Identifying Errors by When They Occur

| Symptom | Suspected layer | First check |
| --- | --- | --- |
| Function missing from catalog | Bean discovery/registration | `ApplicationContext`, bean name, profiles |
| Catalog lists name, input type shows `object` | Type metadata | `@Bean` signature, `FunctionRegistration` |
| JSON body becomes `LinkedHashMap` | Overly generic target or native decoder | Signature + payload class + converter |
| `ClassCastException` on invoke | Map/Object passed to typed lambda | Caller/wrapper and runtime input |
| Error only on subscribing to `Flux` | Element type mismatch in pipeline | `StepVerifier`, nested generics |
| JSON parse exception before function | Jackson/schema/converter | Pure Jackson test, `Content-Type` |
| Packaged JAR behaves differently from IDE | Build transform or runtime config | `javap`, dependencies, profiles |
| Native-only reflection exception | AOT hints | DTO reflection, generated context |
| Composition `a|b` fails | Type mismatch between functions | Input/output of each link |
| HTTP 404 | Web mapping/definition | Function selection and routes |
| Stream receives no events | Binder/binding | Destination, consumer group, logs |

A `MessageConversionException` can wrap a Jackson exception; inspect the **root cause** and stack trace to see whether the failure occurred before or after invocation.

## 12. Content-Type Describes Format; Generics Describe Target Type

Example Message:

~~~text
contentType: application/json
payload bytes: {"orderId":"ORD-101","amountCents":150000}
~~~

`application/json` specifies the wire format. `Function<OrderEvent,OrderReceipt>` specifies that the input must become `OrderEvent`.

If the signature is `Function<Object,Object>`, decoding to `LinkedHashMap` is reasonable behavior. You cannot substitute a target type merely by setting the right `Content-Type`.

### 12.1. Message<T> Preserves Two Type Layers

~~~java
@Bean
Function<Message<OrderEvent>, Message<OrderReceipt>> acceptMessage() {
    return message ->
        MessageBuilder.withPayload(
            new OrderReceipt(
                message.getPayload().orderId(),
                "ACCEPTED"
            )
        ).build();
}
~~~

Imports `org.springframework.messaging.Message` and `MessageBuilder`. With `Message<?>` or `Message<Object>`, the target payload type is unspecified.

### 12.2. Native Deserialization Is a Separate Boundary

If Spring Cloud Stream sets:

~~~properties
spring.cloud.stream.bindings.acceptOrder-in-0.consumer.useNativeDecoding=true
~~~

the binder/client deserializer can build a `Map` before data reaches SCF converters. In that case, do not assume adding generic metadata alone will fix the native decoder; inspect the deserializer and actual payload type.

### 12.3. A Serverless Envelope Is Not Directly the POJO

An event can look like:

~~~json
{
  "requestContext": {"requestId": "req-101"},
  "body": "{\"orderId\":\"ORD-101\",\"amountCents\":150000}"
}
~~~

Even if `Function<OrderEvent,OrderReceipt>` keeps its signature intact, if the adapter passes the entire envelope, the input schema still mismatches. That is an adapter/event-contract issue, not proof that generics were stripped.

## 13. Losing Types in Composition

Two functions:

~~~java
@Bean
Function<String, OrderEvent> parseOrder(ObjectMapper mapper) {
    return json -> {
        try {
            return mapper.readValue(json, OrderEvent.class);
        }
        catch (JsonProcessingException error) {
            throw new IllegalArgumentException(
                "Invalid order JSON", error
            );
        }
    };
}

@Bean
Function<OrderEvent, OrderReceipt> acceptOrder() {
    return new OrderConverter();
}
~~~

Can be composed:

~~~properties
spring.cloud.function.definition=parseOrder|acceptOrder
~~~

If `parseOrder` is changed to `Function<String,Object>` and parses `Object.class`, the JSON object can become a `Map`. Then the preceding step's output no longer guarantees an explicit `OrderEvent` contract.

**A composition resolving all function names does not prove metadata and inter-step conversion are correct.** Test both individual function inputs/outputs and the combined pipeline.

## 14. Packaging: Standard Spring Boot JARs Do Not Intentionally Strip Generic Signatures

`javac` normally records class/method generic declarations in the `Signature` attribute. A standard Spring Boot executable JAR simply packages `.class` files and dependencies; it is **not designed to strip generic Signatures**.

If it works locally yet fails in deployment:

1. Does the deployed artifact match the right commit and version?
2. Do classes inside the JAR match the compiled bytecode?
3. Are shading, obfuscation, minimization, or bytecode instrumentation applied?
4. Do active profiles or conditions differ?
5. Is AOT/native image or a different functional startup mode in use?
6. Did dependencies, Jackson modules, or converters change?

### 14.1. Class Presence Differs from Signature Presence

Having `OrderEvent.class` inside an archive does not prove the factory method `acceptOrder()` kept its generic return type. Conversely, an intact `Signature` does not guarantee converters are loaded or DTOs deserialize cleanly.

Check all four:

- **Class membership:** is the class in the JAR?
- **Method/class Signature:** is generic metadata present in bytecode?
- **Runtime registration:** is Spring using that exact bean and signature?
- **Adapter behavior:** does JSON arrive at the business function with the right type?

## 15. Using javap to Inspect Before and After Packaging

The commands below are **educational examples** and are not executed during the writing of this lesson.

### 15.1. Inspecting Classes Before Packaging

With Gradle:

~~~bash
javap -v -p \
  -classpath build/classes/java/main \
  demo.generic.TypedOrderFunctions
~~~

With Maven:

~~~bash
javap -v -p \
  -classpath target/classes \
  demo.generic.TypedOrderFunctions
~~~

Look for `acceptOrder` and its associated `Signature`. A condensed excerpt looks similar to:

~~~text
public java.util.function.Function<
    demo.generic.OrderEvent,
    demo.generic.OrderReceipt> acceptOrder();
...
Signature: (...)Ljava/util/function/Function<
    Ldemo/generic/OrderEvent;
    Ldemo/generic/OrderReceipt;>;
~~~

This is an **abbreviated illustration**, not byte-for-byte `javap` descriptor output.

### 15.2. Inspecting the Executable JAR

~~~bash
jar tf build/libs/orders-app.jar \
  | grep 'TypedOrderFunctions.class'
~~~

In many Spring Boot executable JARs, classes sit under `BOOT-INF/classes`. You can extract the class into a dedicated temporary inspection directory:

~~~bash
mkdir -p /tmp/scf-generic-inspect
cd /tmp/scf-generic-inspect

jar xf /path/to/orders-app.jar \
  BOOT-INF/classes/demo/generic/TypedOrderFunctions.class

javap -v -p \
  -classpath BOOT-INF/classes \
  demo.generic.TypedOrderFunctions
~~~

Avoid extracting into your source tree unnecessarily. Shaded/plain JAR layouts differ from Boot executable JARs, so run `jar tf` first.

### 15.3. Interpreting the Results

| Build classes | Packaged class | Direction to investigate |
| --- | --- | --- |
| `Signature` intact | `Signature` intact | Metadata on this class was not lost; check registration/adapter |
| `Signature` intact | `Signature` missing | Suspect bytecode transform/shrinking |
| Both lack required generics | Both missing | Source registration is likely raw |
| Class missing from archive | Absent | Packaging/classpath issue |
| Signature intact, runtime shows `Object` | Present | Possibly reading wrong bean/proxy/registration |

`javap` proves only that bytecode **stores metadata**; it does not prove `FunctionCatalog` uses that metadata.

## 16. Shading, Obfuscation, and Bytecode Transformation

Some build pipelines use Maven Shade, Gradle Shadow, ProGuard, R8, or bytecode-rewriting tools. These can alter class names, resources, or attributes.

### 16.1. Shading Does Not Necessarily Destroy Signatures

Relocation can update class names inside metadata. When configured properly, generic attributes can survive. Do not claim "using a shaded JAR always loses generics."

Check:

- Does the tool strip the `Signature` attribute?
- Does relocation rewrite DTO/interface names inside metadata?
- Does shrinking strip classes/constructors accessed via reflection?
- Are Spring autoconfiguration/service loader/Jackson metadata files merged properly?
- Are multiple versions of a library merged, creating type mismatches?

### 16.2. ProGuard Hint

If a project **actually** uses ProGuard, a reference configuration keeping attributes is:

~~~text
-keepattributes Signature,*Annotation*,InnerClasses,EnclosingMethod
~~~

This single line is **not sufficient** to keep an entire Spring application working: you also need keep rules for bean configurations, DTO constructors, reflection, and serializers. Verify the plugin/version and packaged artifact with real tests.

### 16.3. Do Not Confuse -parameters with Signature

`-parameters` preserves **Java parameter names** for reflection. `Signature` stores generic declarations. They are two distinct kinds of metadata.

If the error is a method returning `Function<Object,Object>`, enabling `-parameters` will not turn its signature into `Function<OrderEvent,OrderReceipt>`. If the error is Jackson constructor parameter binding, parameter names may be relevant. Identify which metadata is actually missing first.

## 17. AOT/Native Image: Target Type and Reflection Access Are Separate Concerns

With GraalVM native images or Spring AOT builds, many bean decisions move to build time, while certain reflection/resource usages must be declared upfront. Separate three aspects:

- **Type discovery:** does `FunctionCatalog` recognize input/output as `OrderEvent` and `OrderReceipt`?
- **Reflection/binding capability:** can Jackson/converters invoke the required constructors, accessors, or fields inside the native image?
- **Build-time registration:** was the bean created in the AOT context under matching profiles/conditions?

| Indicator | Investigation path |
| --- | --- |
| Actuator/catalog shows `Object` in both JVM and native | Generic declaration/registration is unclear |
| Packaged JVM JAR works, native image fails on reflection | `RuntimeHints`/Jackson binding metadata |
| Bean present locally, absent in native | AOT build-time profiles/conditions/config |
| Generic class retains `Signature`, yet Jackson fails to construct DTO | Reflection hints or JSON schema |
| DTO deserializes fine, wrong function runs | Function definition, router, catalog |

### 17.1. Reflection Hints Do Not Turn a Raw Function into a Typed Function

Registering a DTO for reflection does not mean:

~~~java
Function<Object, Object>
~~~

automatically becomes:

~~~java
Function<OrderEvent, OrderReceipt>
~~~

First fix the signature or `FunctionRegistration.type(...)`, then verify whether the DTO has reflection hints.

### 17.2. Example Registering a DTO for Binding in Supported Versions

Spring Framework provides `@RegisterReflectionForBinding` for cases where JSON binding is not automatically detected by AOT analysis:

~~~java
@Configuration
@RegisterReflectionForBinding(OrderEvent.class)
class OrderBindingHints {
}
~~~

This example depends on your Spring Framework version and imports `org.springframework.aot.hint.annotation.RegisterReflectionForBinding`. Not every project needs this annotation; the framework may already generate hints automatically. Add it only when evidence shows the native image lacks reflection metadata.

### 17.3. Three Modes to Compare

1. Running IDE/test classpath on JVM.
2. Running **the packaged JVM artifact** with deployment-representative profiles and dependencies.
3. Running **the native executable** if production uses native.

If failure already appears in step 1, suspect registration/DTOs; if only step 2 differs, suspect packaging/classpath/config; if only step 3 differs, investigate AOT/native. Do not blame JVM type erasure for every native issue.

## 18. FunctionCatalog Wrapper and Type Conversion: Testing the Right Boundary

A function declared as:

~~~java
Function<OrderEvent, OrderReceipt>
~~~

typically receives raw bytes/Strings/Messages forwarded by an adapter to the wrapper from `FunctionCatalog`. The wrapper can handle message conversion and composition, but only when the framework has enough information:

- Valid functional bean name and registration.
- Input/output types or matching metadata.
- `contentType`/converter matching the wire payload.
- Parseable DTO matching the schema.
- The adapter actually passes through that conversion path.

### 18.1. Why Can a Typed POJO Test Pass While HTTP Fails?

~~~java
OrderReceipt receipt = function.apply(
    new OrderEvent("ORD-101", 150000)
);
~~~

Here the caller already passed an `OrderEvent`. There is no JSON to deserialize.

Over HTTP:

~~~text
HTTP JSON bytes
    → HTTP adapter
    → Message/ConversionService
    → FunctionCatalog wrapper
    → OrderEvent
    → business function
~~~

If metadata was lost at registration, the typed Java test still passes while HTTP receives a `Map`. Therefore, you need **ingress-level tests**.

### 18.2. Why Must You Also Check Output Types?

Losing the output type can cause:

- Serializers choosing the wrong media type.
- Spring Cloud Stream bindings sending Map/String/bytes contrary to contract.
- Composition not knowing the type to connect to the next function.
- Serverless handlers returning unexpected envelopes/JSON structures.
- Reactive `Mono<Void>` being misread as payload-producing output.

Do not inspect only input types when the failure happens during serialization or the next composition step.

## 19. Evidence-Based Diagnostic Workflow

~~~mermaid
flowchart TD
    START["Map instead of POJO / type=Object / error after packaging"] --> JSON{"Does pure Jackson parse JSON to DTO?"}
    JSON -->|No| DTO["Fix JSON/schema/DTO first"]
    JSON -->|Yes| CAT{"Does Catalog find the right function?"}
    CAT -->|No| REG["Check @Bean, scan,\nFunctionRegistration, definition"]
    CAT -->|Yes| DECL{"Do factory method/class generics suffice?"}
    DECL -->|No| TYPE["Fix raw/Object declaration\nor supply FunctionRegistration.type"]
    DECL -->|Yes| BYTE{"Does JAR keep Signature?"}
    BYTE -->|No| BUILD["Check shading,\nobfuscator, bytecode transform"]
    BYTE -->|Yes| ADAPTER{"Where is payload decoded?"}
    ADAPTER -->|HTTP / MessageConverter| CONTENT["contentType, target type,\ncustom converter"]
    ADAPTER -->|Stream native decoding| NATIVE["Deserializer / schema / binder"]
    ADAPTER -->|Serverless event| ENV["Event shape / envelope"]
    ADAPTER -->|Native-only| AOT["RuntimeHints / AOT context"]
    DTO --> VERIFY["Re-test each layer"]
    REG --> VERIFY
    TYPE --> VERIFY
    BUILD --> VERIFY
    CONTENT --> VERIFY
    NATIVE --> VERIFY
    ENV --> VERIFY
    AOT --> VERIFY
~~~

### 19.1. Execution Steps

1. **Record the exact symptom:** parse error, `ClassCastException`, Actuator type showing `Object`, or failure on Flux subscribe?
2. **Identify the environment:** IDE JVM, packaged JVM, serverless JAR, or native image?
3. **Verify pure Jackson:** can Jackson read the raw payload into `OrderEvent`?
4. **Verify catalog name:** `catalog.getNames(null)`, function definition, and typed lookup.
5. **Inspect factory declaration:** is the `@Bean` return type raw or `Object`?
6. **Inspect implementation type:** does the named class implement the full generic interface?
7. **If functional registration:** does `FunctionRegistration.type(...)` provide the right metadata?
8. **If reactive/Message/List:** are nested element types preserved?
9. **If packaging is suspected:** compare `javap -v` on build output versus deployed artifact.
10. **If using AOP/FactoryBean:** inspect the bean definition/target, not only the runtime proxy class.
11. **If the adapter receives a Map:** determine whether the Map came from an SCF converter or a native deserializer.
12. **If native image:** compare runtime hints and build-time AOT context.
13. **Fix one root cause and re-verify** using a test at the right boundary.
14. **Add regression tests** for the artifact and adapter so the bug does not return.

## 20. Layer 1 Test: Method and Class Generics via ResolvableType

Using JUnit 5 and AssertJ:

~~~java
package demo.generic;

import static org.assertj.core.api.Assertions.assertThat;

import java.lang.reflect.Method;
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.core.ResolvableType;

class SignatureDeclarationTest {

    @Test
    void beanFactoryDeclaresInputAndOutput() throws Exception {
        Method method =
            TypedOrderFunctions.class.getMethod("acceptOrder");

        ResolvableType type =
            ResolvableType.forMethodReturnType(method)
                .as(Function.class);

        assertThat(type.getGeneric(0).resolve())
            .isEqualTo(OrderEvent.class);

        assertThat(type.getGeneric(1).resolve())
            .isEqualTo(OrderReceipt.class);
    }

    @Test
    void implementationHasGenericInterface() {
        ResolvableType type =
            ResolvableType.forClass(OrderConverter.class)
                .as(Function.class);

        assertThat(type.getGeneric(0).resolve())
            .isEqualTo(OrderEvent.class);

        assertThat(type.getGeneric(1).resolve())
            .isEqualTo(OrderReceipt.class);
    }
}
~~~

This test catches refactorings that degrade `Function<OrderEvent,OrderReceipt>` to a raw type. It **does not** prove converters and packaged artifacts behave properly.

### 20.1. Negative Test: Raw Function Exposes No DTO on the Method

Example configuration class intentionally using a raw return type:

~~~java
class RawOrderFunctions {

    public Function acceptOrder() {
        return new OrderConverter();
    }
}
~~~

A test can inspect `ResolvableType` for `RawOrderFunctions.acceptOrder()` and verify it does not resolve input as `OrderEvent.class`. This proves **loss of generic declaration in source**, not a Jackson bug.

### 20.2. Scope of These Tests

| Test | What it verifies |
| --- | --- |
| `ResolvableType.forMethodReturnType` | Declared factory method return type |
| `ResolvableType.forClass(...).as(Function.class)` | Generic interface on implementing class |
| `FunctionRegistration.type` | Runtime metadata for functional registration |
| `javap -v` on packaged artifact | Signature actually present in deployed bytecode |

A runtime lambda class does not necessarily pass the second check; do not treat it as the sole representative of `@Bean` metadata.

## 21. Layer 2 Test: FunctionCatalog Still Registers and Handles Typed Input

A Spring Boot test configuration (in the same package as `TypedOrderFunctions`):

~~~java
package demo.generic;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GenericDiagnosticsApplication {
}
~~~

Test:

~~~java
package demo.generic;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(classes = GenericDiagnosticsApplication.class)
class CatalogGenericTest {

    @Autowired
    private FunctionCatalog catalog;

    @Test
    void typedFunctionResolves() {
        assertThat(catalog.getNames(null))
            .contains("acceptOrder");

        Function<OrderEvent, OrderReceipt> fn =
            catalog.lookup(Function.class, "acceptOrder");

        assertThat(fn).isNotNull();

        OrderReceipt result = fn.apply(
            new OrderEvent("ORD-101", 150000L)
        );

        assertThat(result)
            .isEqualTo(
                new OrderReceipt("ORD-101", "ACCEPTED")
            );
    }
}
~~~

**Note:** a direct test with a typed `OrderEvent` can still pass even if the function was registered raw and adapters lack target type info. You still need **JSON bytes → POJO** tests.

## 22. Layer 3 Test: HTTP Adapter with Real JSON

If the project has the Spring Cloud Function web adapter and compatible Spring Boot Web/test dependencies:

~~~java
package demo.generic;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

@SpringBootTest(
    classes = GenericDiagnosticsApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "spring.cloud.function.definition=acceptOrder",
        "spring.cloud.function.single-function-fallback-enabled=false"
    }
)
class HttpGenericTest {

    @Autowired
    TestRestTemplate rest;

    @Test
    void jsonBytesReachTypedFunction() {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);

        String json =
            "{\"orderId\":\"ORD-101\",\"amountCents\":150000}";

        ResponseEntity<String> response = rest.exchange(
            "/acceptOrder",
            HttpMethod.POST,
            new HttpEntity<>(json, headers),
            String.class
        );

        assertThat(response.getStatusCode().is2xxSuccessful())
            .isTrue();

        assertThat(response.getBody())
            .contains("ORD-101")
            .contains("ACCEPTED");
    }
}
~~~

The example assumes the web adapter maps the function at `/acceptOrder`; configurations using root path or a different web base path must adjust the test URL to the actual mapping rather than altering generic signatures just because of a 404.

### 22.1. What Does That Test Prove?

- The matching HTTP endpoint exists.
- JSON wire bytes are accepted by the adapter.
- The converter and wrapper transform input into the type expected by the business function.
- The function produces output that serializes into the response.

It does not prove Spring Cloud Stream native decoding, serverless event envelopes, or shaded production JARs behave identically.

### 22.2. Negative Input Test

With:

~~~json
{"orderId":"ORD-101","amountCents":"abc"}
~~~

verify the request does not report success and business side effects do not execute. Exact HTTP error status codes may vary by version and exception handling; do not hardcode a single status code if the adapter does not guarantee it.

## 23. Layer 4 Test: Reactive Generics Preserved per Element

For `StreamOrderFunction` from section 5, test with `reactor-test`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class ReactiveGenericTest {

    @Test
    void streamProcessesTypedOrders() {
        StreamOrderFunction function =
            new StreamOrderFunction();

        StepVerifier.create(function.apply(
                Flux.just(
                    new OrderEvent("ORD-101", 150000L),
                    new OrderEvent("ORD-102", 200000L)
                )
            ))
            .expectNext(
                new OrderReceipt("ORD-101", "ACCEPTED"),
                new OrderReceipt("ORD-102", "ACCEPTED")
            )
            .verifyComplete();
    }
}
~~~

This test verifies reactive logic with pre-constructed POJOs. If integration input consists of Kafka bytes/Maps, also test **conversion from wire format**.

### 23.1. Checking Generics of the Reactive Class

~~~java
ResolvableType type =
    ResolvableType.forClass(StreamOrderFunction.class)
        .as(Function.class);

ResolvableType input = type.getGeneric(0);
ResolvableType output = type.getGeneric(1);

assertThat(input.resolve()).isEqualTo(Flux.class);
assertThat(input.getGeneric(0).resolve())
    .isEqualTo(OrderEvent.class);

assertThat(output.resolve()).isEqualTo(Flux.class);
assertThat(output.getGeneric(0).resolve())
    .isEqualTo(OrderReceipt.class);
~~~

This is the proper check for nested generics—not asserting only `Flux.class`.

## 24. Layer 5 Test: Spring Cloud Stream and Native Decoding

With Spring Cloud Stream, use the test binder or broker integration tests to send JSON bytes through the actual binding.

Example:

~~~properties
spring.cloud.function.definition=acceptOrder
spring.cloud.stream.bindings.acceptOrder-in-0.destination=orders-in
spring.cloud.stream.bindings.acceptOrder-in-0.content-type=application/json
spring.cloud.stream.bindings.acceptOrder-out-0.destination=orders-out
~~~

Test sequence:

1. Verify function definition and actual binding names.
2. Send UTF-8 JSON payloads with appropriate `contentType` headers.
3. Confirm the business function receives `OrderEvent`, not `LinkedHashMap`.
4. Confirm output serialization produces the expected payload.
5. If `useNativeDecoding=true`, test using the deployment's actual deserializer.
6. Test schema-invalid events and the binder's error-handling policy.

### 24.1. Why Cannot Pre-Function Errors Be Caught by onErrorResume?

If a Kafka deserializer or adapter message converter fails **before the function is called**, an `onErrorResume` inside `Function<Flux<T>,Flux<R>>` may never have a chance to handle that error.

Do not assume changing generic metadata alone will fix broker serializer, deserializer, or message conversion failures. Inspect the stack trace to pinpoint the failing boundary.

## 25. Packaged Artifact Tests: Evidence Required to Blame Packaging

You can conclude "generics were lost **after packaging**" only with comparative evidence:

| Check | Expected evidence |
| --- | --- |
| Source/compile output | `@Bean` or implementing class has the right `Signature` |
| Packaged JVM artifact | Class matches logic and retains generic `Signature` |
| Runtime Environment | `spring.cloud.function.definition`, profiles, dependencies match |
| Catalog | Function name and wrapper metadata/types are appropriate |
| Adapter | JSON bytes become the intended POJO |
| Native artifact if used | Reflection hints, converters, and event contract work |

If source/compile output **is already raw**, do not blame packaging. If the artifact retains `Signature` yet custom functional registration only passes `Function.class`, fix registration. If the packaged JVM works while the native image fails to deserialize DTOs, check AOT/reflection.

### 25.1. An Applicable CI Pipeline

~~~text
Compile
  → Unit tests: @Bean generics / class interface
  → Build executable JAR
  → Inspect Signature in packaged class (if bytecode transforms are used)
  → Boot packaged app with representative profile
  → HTTP/Stream smoke test with JSON bytes
  → Optional native image integration test
  → Deploy
~~~

In this lesson, the pipeline is **described conceptually**; actual build execution and validation belong to your project's build/QA workflow.

## 26. Cause-and-Fix Reference Table

| Cause | Symptom | Priority fix |
| --- | --- | --- |
| `@Bean` declares raw `Function` | Method signature lacks DTO types | Declare `Function<OrderEvent,OrderReceipt>` |
| `@Bean Object` returns function | Declared bean type too generic | Use typed interface |
| Dynamic lambda registration lacks type | Catalog sees Function, input/output `Object` | `FunctionRegistration.type(...)` |
| Generic class has unbound type variable | `T` does not resolve to DTO | Concrete subclass or explicit type |
| Nested `Flux.class`/`List.class` | Item type lost | Provide nested Type/class signature |
| JDK proxy hides runtime generic | `getClass()` does not expose DTO | Inspect factory method/target and registry |
| Shading/obfuscator strips `Signature` | Bytecode differs before/after | Fix transformer/keep attributes |
| Minifier removes DTO/class | Missing class or reflection fails | Keep rules for class/constructor/resources |
| Native-only Jackson reflection error | JVM OK, native fails | AOT/`RuntimeHints` |
| Wrong HTTP `contentType` | JSON handled as String/bytes | Fix request media type/converter |
| Stream native decoder returns Map | `useNativeDecoding=true` | Configure deserializer target type |
| Serverless event envelope | JSON does not match DTO | Fix event schema/adapter |
| Composition returns `Object` | `a|b` conversion unclear | Keep step `a`'s output typed |
| Wrong function lookup | Catalog lacks name or falls back | Fix definition/naming; test strict lookup |

**One approach not to use everywhere**: stuffing `ObjectMapper.convertValue` at the start of every function. It hides broken input contracts, adds overhead, and turns schema errors into late failures.

## 27. Common Misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| "Java erasure means `Function<I,O>` can never be known at runtime." | Generic declarations can survive in the `Signature` of methods/classes |
| "If `lambda.getClass()` lacks DTO types, the JAR definitely stripped generics." | Generics may live on the factory method or `FunctionRegistration` |
| "If `@Bean Object` returns the right instance, catalog always infers types." | Overly generic declared return types can lose the metadata source |
| "Casting `Function<Object,Object>` to a typed Function fixes conversion." | Casting does not attach type arguments to registration |
| "Non-null `FunctionCatalog` lookup means JSON input becomes the POJO." | Lookup only selects the function; conversion is a separate step |
| "`contentType=application/json` is enough to know the target class." | You also need declared generic types or safe dynamic typing |
| "`Flux.class` works the same as `Flux<OrderEvent>`." | Element type is lost |
| "Enabling `-parameters` preserves generic `Signature`." | They are two different metadata attributes |
| "Spring Boot fat JARs always strip generics." | Standard packaging does not strip `Signature` |
| "Shadow/Shade always loses generics." | Depends on transformer, relocation, and keep rules |
| "Seeing a JDK proxy proves it is the root cause." | Bean definition/target may still retain metadata |
| "Adding `RuntimeHints` fixes `Function<Object,Object>`." | Hints do not define a function's target type |
| "Receiving a JSON Map proves generics were lost." | A native decoder or schema may intentionally produce a Map |
| "Passing `apply(new OrderEvent)` tests JSON conversion." | No raw data passed through the converter |
| "Reactive errors always surface during `apply`." | They may appear only on subscribe |
| "Adding another bean fixes type errors." | That alters catalog/function selection, not metadata |

## 28. Pre-Production Checklist

### 28.1. Declaration and Registration

- [ ] Function has concrete input/output generics matching the contract.
- [ ] Raw `Function`/`Object` is avoided unless intentionally polymorphic.
- [ ] `Message<T>` preserves payload type.
- [ ] `Flux<T>`, `Mono<T>`, `List<T>` preserve element types.
- [ ] Functional lambda registrations include `FunctionRegistration.type(...)`.
- [ ] Named implementations declare clear generic interfaces.
- [ ] AOP/`FactoryBean` does not cause registry type mis-inference.

### 28.2. Build/Packaging

- [ ] Deployed artifact contains the right classes and BOM/versions.
- [ ] `Signature` is present in class files when reflection depends on it.
- [ ] Shading/obfuscation/minification is verified on the packaged JAR.
- [ ] Post-packaging tests exist, not only IDE tests.
- [ ] If native image, appropriate AOT/reflection tests exist.

### 28.3. Adapters

- [ ] Function definition/composition selects the exact intended names.
- [ ] HTTP requests supply proper `Content-Type` and JSON schema.
- [ ] Stream bindings/`contentType`/native decoding match function input.
- [ ] Serverless event shape is verified, distinguishing envelope from body.
- [ ] Tests cover raw bytes → POJO → output DTO.
- [ ] Parse/conversion errors neither trigger wrong side effects nor infinitely retry corrupt payloads.

## 29. Self-Assessment Questions

1. How do type erasure and generic `Signature` differ?
2. Why can `@Bean Function<OrderEvent,OrderReceipt>` still provide metadata even though the JVM executes `Function.apply(Object)`?
3. Why is a lambda's runtime class not the only place to infer types?
4. What risk does raw `@Bean Function` create for `FunctionCatalog`?
5. Does casting `Function<Object,Object>` to a typed Function restore metadata?
6. How does `FunctionRegistration` help in functional startup?
7. When do you use `FunctionTypeUtils.functionType(OrderEvent.class,OrderReceipt.class)`?
8. Why is `FunctionTypeUtils.functionType(Flux.class,Flux.class)` insufficient for a typed stream?
9. How does `Message<OrderEvent>` differ from `Message<?>`?
10. How do `ResolvableType.forMethodReturnType` and `ResolvableType.forClass` inspect two different metadata sources?
11. Why does a generic class with an unbound type variable `T` fail to specify `OrderEvent` input?
12. What should you inspect before blaming an AOP proxy?
13. What does `javap -v` reveal that `jar tf` cannot?
14. Does a standard Spring Boot executable JAR automatically strip `Signature`?
15. Through which mechanisms can shading/obfuscation affect generics?
16. Does `-parameters` play the same role as `Signature`?
17. When does a native image need `RuntimeHints` rather than changing function types?
18. Why can `FunctionCatalog.lookup` succeed while HTTP still receives a `Map`?
19. How do you determine whether a `Map` was produced by an SCF converter or a Kafka native deserializer?
20. Why can a reactive function throw `ClassCastException` late after `subscribe`?
21. How can composition fail when the previous step's output is `Object`?
22. Why does testing `apply(new OrderEvent(...))` not prove JSON conversion works?
23. In what order would you organize smoke tests on a packaged JVM artifact?
24. When a packaged JVM works yet a native image fails, which evidence sources should you compare?

## 30. References

- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html) — `FunctionCatalog` wrappers, composition, type conversion, and imperative/reactive signatures.
- [Spring Cloud Function — Functional Bean Definitions](https://docs.spring.io/spring-cloud-function/reference/functional.html) — differences between `@Bean` and functional registration; `FunctionRegistration`, `FunctionTypeUtils`, discovery, and testing.
- [Spring Cloud Function — FunctionTypeUtils source](https://github.com/spring-cloud/spring-cloud-function/blob/main/spring-cloud-function-context/src/main/java/org/springframework/cloud/function/context/catalog/FunctionTypeUtils.java) — type inference mechanics; match source tag to your project dependency.
- [Spring Cloud Function — BeanFactoryAwareFunctionRegistry source](https://github.com/spring-cloud/spring-cloud-function/blob/main/spring-cloud-function-context/src/main/java/org/springframework/cloud/function/context/catalog/BeanFactoryAwareFunctionRegistry.java) — how the framework reads bean definitions and registers functions.
- [Spring Framework — ResolvableType](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/ResolvableType.html) — querying method, class, and generic hierarchy types.
- [Spring Framework — Ahead-of-Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html) — how AOT analyzes beans and requires reflection/runtime hints.
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html) — function binding model and transport.
- [Spring Cloud Stream — Content Type Negotiation](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/content-type-negotiation.html) — media types and message conversion.
- [Project Reactor — Testing](https://projectreactor.io/docs/test/release/reference/) — `StepVerifier` for reactive pipelines.
- [Java Virtual Machine Specification — Signature Attribute](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.9) — generic signatures in the class-file format.

Examples use Java 17+ and Spring Cloud Function / Spring Cloud Stream APIs. Certain functional startup APIs, Spring AOT details, web mappings, and binders vary by BOM/version; verify against your deployed dependencies and artifacts. Examples of `javap`, JAR inspection, and tests are guidelines to execute in the appropriate testing step rather than commands executed within this document.

**Takeaway:** When Spring Cloud Function knows a function's name yet fails to supply `OrderEvent` or loses output typing, inspect **generic declarations on `@Bean`/implementing classes and `FunctionRegistration` metadata** before blaming the Spring Boot JAR. Java type erasure still allows the compiler to record `Signature` on proper declarations; a lambda or proxy runtime class is not the whole picture. If you suspect the build stripped types, compare bytecode before and after packaging with `javap`; if only native fails, inspect AOT reflection hints; if a `Map` arrives from a broker, check the native deserializer. Finally, verify separately that **the catalog finds the function** and **the adapter converts raw JSON into the intended POJO**, using tests against the actual deployed artifact.
