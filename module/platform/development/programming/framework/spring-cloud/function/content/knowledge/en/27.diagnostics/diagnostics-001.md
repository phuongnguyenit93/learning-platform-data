# Function Not Found in FunctionCatalog

## 1. Scenario: A Java Function Exists, but Lookup or Adapter Reports Not Found

You define a **Spring Cloud Function** bean:

~~~java
@Bean
public Function<String, String> uppercase() {
    return String::toUpperCase;
}
~~~

However, a call to `FunctionCatalog` does not return the expected result:

~~~java
Function<String, String> f =
    functionCatalog.lookup(Function.class, "uppercase");
~~~

Or the application runs, yet HTTP `/uppercase` returns 404, Spring Cloud Stream does not create a binding, AWS Lambda cannot select the function, or a routing expression points to a non-existent name.

These symptoms **do not necessarily share the same root cause**. Spring Cloud Function decouples `Supplier`, `Function`, and `Consumer` business logic from HTTP, message brokers, and serverless platforms; they pass through `ApplicationContext`, `FunctionCatalog`, composition, and various adapters. When a function does not work, you need to pinpoint the exact boundary that is failing.

**Diagnostic principle:**

> Do not assume the catalog is missing a function just because an HTTP endpoint does not exist or a consumer does not receive messages. Prove each step in order: **the bean is created → the catalog has the name → lookup by name/type succeeds → the function can be invoked directly → the adapter selects and connects properly**.

This lesson belongs to the **Diagnostics** chapter, under the topic **"Function Not Found in FunctionCatalog"**.

### Learning Objectives

After this lesson, you will be able to:

1. Explain how Java `Supplier`/`Function`/`Consumer` beans enter `FunctionCatalog`.
2. Use `getNames(null)`, `size()`, `lookup(...)`, and `ApplicationContext` to isolate failures.
3. Diagnose issues with component scanning, `@Bean`, `@Configuration`, profiles, conditional beans, and generic types.
4. Distinguish between bean name, function definition/composition, HTTP path, binding name, and broker destination.
5. Understand how the *single-function fallback* mechanism can mask misspelled names and how to disable it in tests.
6. Distinguish a missing function in the catalog from routing, conversion, subscription, or adapter errors.
7. Write tests verifying that functions are registered, composition works, and deployments do not rely on fallback.

## 2. Boundaries to Distinguish

Spring Cloud Function supports these interfaces:

~~~java
java.util.function.Supplier<O>
java.util.function.Function<I, O>
java.util.function.Consumer<I>
~~~

A functional bean managed by Spring can be registered into the catalog. The catalog provides lookup capabilities and wrapper classes for type conversion, composition, and integration features. Retrieving the raw bean via `ApplicationContext.getBean(...)` is not necessarily identical to looking up its wrapper via `FunctionCatalog`.

~~~mermaid
flowchart LR
    CODE["@Bean code or functional class"] --> CTX["ApplicationContext"]
    CTX --> CAT["FunctionCatalog"]
    CAT --> DEF["lookup(name / definition)"]
    DEF --> AD["HTTP / Spring Cloud Stream / Serverless"]
    AD --> INV["invoke + payload conversion"]
~~~

| Boundary | Question to verify | Failure indicator |
| --- | --- | --- |
| Source → Spring context | Is the configuration class scanned/imported? Is the bean created? | Context does not contain the bean |
| Spring context → catalog | Is the bean an eligible functional type? Is it filtered out? | Context has the bean, catalog does not |
| Catalog → lookup | Are name, type, composition, and fallback correct? | Name is listed, but lookup gets the wrong target |
| Catalog → adapter | Does the adapter select the intended function? | Direct lookup works, HTTP/Stream fails |
| Adapter → business | Are payload type, headers, publisher, and logic correct? | Invocation fails after the function is found |

Key point: an application error message might say "function not found", but determining the root cause requires knowing whether it originated from the **catalog**, **router**, **adapter**, or how the code uses the catalog.

## 3. Sample Application with Deterministic Function Names

Use a simple Spring Boot configuration class:

~~~java
package demo.diagnostics;

import java.util.Locale;
import java.util.function.Function;
import java.util.function.Supplier;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DiagnosticsApplication {

    public static void main(String[] args) {
        SpringApplication.run(DiagnosticsApplication.class, args);
    }

    @Bean
    public Function<String, String> uppercase() {
        return value -> value.toUpperCase(Locale.ROOT);
    }

    @Bean
    public Function<String, String> reverse() {
        return value -> new StringBuilder(value).reverse().toString();
    }

    @Bean
    public Supplier<String> greeting() {
        return () -> "hello";
    }
}
~~~

This example assumes the project declares compatible Spring Boot / Spring Cloud Function dependencies. The three bean names are `uppercase`, `reverse`, and `greeting`. Having a method with a function-like signature inside a class **does not mean that method is registered**; in the example above, `@Bean` performs the registration.

### 3.1. Looking Up a Wrapper and Retrieving the Raw Bean Are Different Operations

~~~java
Function<String, String> wrapped =
    functionCatalog.lookup(Function.class, "uppercase");

Function<String, String> original =
    applicationContext.getBean("uppercase", Function.class);
~~~

`original` is the bean created by Spring; `wrapped` is the function returned by the catalog. Spring Cloud Function may wrap functions to support message conversion and composition. Do not write tests requiring the two objects to be the exact same instance; verify the behavioral contract instead.

### 3.2. Do Not Test HTTP Before Testing the Catalog

In an application that only uses `spring-cloud-function-context`, the catalog can work **without any HTTP endpoint**. The HTTP adapter is an optional integration component.

The first step is to verify the catalog inside the running process itself, rather than sending hundreds of requests to `/uppercase` guessing which route is right.

## 4. Inspecting the Catalog via the Official API

Spring Cloud Function provides APIs to list functions:

~~~java
import java.util.Set;
import org.springframework.cloud.function.context.FunctionCatalog;

FunctionCatalog catalog =
    applicationContext.getBean(FunctionCatalog.class);

int size = catalog.size();
Set<String> names = catalog.getNames(null);

System.out.println("catalog size: " + size);
System.out.println("catalog names: " + names);
~~~

`catalog.getNames(null)` shows the names exposed by the catalog according to the API. It is much more reliable than guessing from class names or HTTP paths.

### 4.1. Interpreting the Results

- **Cannot inject `FunctionCatalog`:** check dependencies, autoconfiguration, and whether the application started properly.
- **Injected, but expected name is missing:** go back to bean registration, scanning, conditions, and filters.
- **Name is present, but lookup fails or returns wrong result:** inspect function type, name, composition, and fallback.
- **Lookup succeeds, but adapter reports an error:** shift focus to HTTP/binder/serverless.
- **Lookup succeeds, but invoke throws an exception:** inspect data types, message conversion, business logic, or reactive subscription.

### 4.2. Comparing with ApplicationContext

~~~java
import java.util.Arrays;
import java.util.function.Function;
import java.util.function.Consumer;
import java.util.function.Supplier;

System.out.println(Arrays.toString(
    applicationContext.getBeanNamesForType(Function.class)
));

System.out.println(Arrays.toString(
    applicationContext.getBeanNamesForType(Supplier.class)
));

System.out.println(Arrays.toString(
    applicationContext.getBeanNamesForType(Consumer.class)
));

System.out.println("Catalog names: " + catalog.getNames(null));
~~~

The two sets of results **are not necessarily identical**: the context reports Spring beans recognized by type, whereas the catalog applies registration rules, auxiliary features, and its own filters.

If the context lacks the name, check Spring registration. If the context has it while the catalog does not, check function eligibility and metadata.

### 4.3. A Temporary Diagnostic ApplicationRunner

~~~java
package demo.diagnostics;

import java.util.Arrays;
import java.util.function.Function;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class FunctionDiagnostics implements ApplicationRunner {

    private static final Logger log =
        LoggerFactory.getLogger(FunctionDiagnostics.class);

    private final ApplicationContext context;
    private final FunctionCatalog catalog;
    private final Environment environment;

    FunctionDiagnostics(
            ApplicationContext context,
            FunctionCatalog catalog,
            Environment environment) {
        this.context = context;
        this.catalog = catalog;
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        log.info("Selected function definition: {}",
            environment.getProperty(
                "spring.cloud.function.definition", "<unset>"
            ));

        log.info("Spring Function beans: {}",
            Arrays.toString(
                context.getBeanNamesForType(Function.class)
            ));

        log.info("Catalog names: {}", catalog.getNames(null));
        log.info("Catalog size: {}", catalog.size());
        log.info("uppercase lookup present: {}",
            catalog.lookup(Function.class, "uppercase") != null);
    }
}
~~~

Use this snippet in a development environment or a controlled diagnostic profile. Do not log all environment variables, tokens, sensitive data, or full payloads simply because a function is hard to find.

## 5. Symptom Triage Table

| Symptom | Suspected cause | Priority check |
| --- | --- | --- |
| `FunctionCatalog` cannot be injected | Missing dependency/autoconfiguration, failed context | Startup logs and bean list |
| `ApplicationContext` lacks the bean | Wrong `@Bean`, scan, profile/condition | Bean name, component scan, active profiles |
| Context has it, catalog does not | Bean shape/metadata or `ineligible-definitions` | Compare name lists in both places |
| `lookup("foo")` fails | Wrong name, type, or composition | `getNames(null)` and typed lookup |
| Lookup with a **wrong** name still succeeds | Single-function fallback | Disable fallback in tests |
| Function is in catalog, no HTTP route | Missing web adapter/path/mapping | Check web module and HTTP config |
| Catalog has bean, Stream receives no events | Definition/binding/destination/binder | Startup binding logs and broker |
| Lambda invokes a different function | Entry point/handler and definition/routing | Deployment settings |
| Function invoked, JSON fails | Converter/generic type/headers | Payload conversion exception |
| Reactive function returns Flux with no data | Missing subscription | StepVerifier/caller/adapter |

Do not change every configuration setting at once. Isolate which layer is failing first, fix that single layer, and verify again.

## 6. Cause: Missing @Bean or @Configuration Not Loaded

### 6.1. Plain Java Methods Do Not Automatically Become Beans

~~~java
@Configuration
public class OrderFunctions {

    // Not automatically registered as a bean because @Bean is missing.
    public Function<String, String> normalizeOrder() {
        return String::trim;
    }
}
~~~

Declare it properly with `@Bean`:

~~~java
@Configuration
public class OrderFunctions {

    @Bean
    public Function<String, String> normalizeOrder() {
        return String::trim;
    }
}
~~~

`@Configuration` must also be scanned or imported by Spring for `@Bean` to be processed.

### 6.2. SpringBootApplication Package Placed Too Deep

Suppose you have:

~~~text
demo.app.Application                (@SpringBootApplication)
demo.functions.OrderFunctions       (@Configuration)
demo.other.MySupplier
~~~

By default, `@SpringBootApplication` scans from the application class's package and its subpackages. If `demo.functions` is not under `demo.app`, the configuration may not be discovered.

You can:

- Move the application class up to an appropriate parent package.
- Use `@Import(OrderFunctions.class)` to explicitly import the configuration.
- Use `scanBasePackages` or a scoped `@ComponentScan` if needed.
- Verify that the class is actually included in the deployed artifact/JAR.

Example:

~~~java
@SpringBootApplication
@Import(OrderFunctions.class)
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Avoid overly broad scanning that picks up unintended functions, causing name collisions or altering fallback behavior.

### 6.3. Unmet Profile or Condition

~~~java
@Configuration
@Profile("dev")
public class DevFunctions {

    @Bean
    public Function<String, String> devOnly() {
        return String::trim;
    }
}
~~~

If the `dev` profile is not active, `devOnly` is not created. The same applies to `@ConditionalOnProperty` and other Spring Boot conditions.

`spring.cloud.function.definition=devOnly` only **selects the function**; it does not force Spring to create a bean that was disabled by a condition.

Check active profiles, effective properties, and the condition evaluation report when needed. Always look for the **first startup exception** first: if the context failed to start cleanly, a lookup failure is only a secondary symptom.

## 7. Cause: Confusing Spring Component Scan with Function Component Scan

Spring Cloud Function also has **Function Component Scan** to detect classes implementing `Supplier`, `Function`, or `Consumer` according to SCF's own rules, even without `@Component`.

The documentation describes the `functions` package being scanned by convention along with two related properties:

~~~properties
spring.cloud.function.scan.packages=demo.myfunctions
spring.cloud.function.scan.enabled=true
~~~

When you want to disable function-specific scanning:

~~~properties
spring.cloud.function.scan.enabled=false
~~~

| Mechanism | Role | Common usage |
| --- | --- | --- |
| Spring component scanning | Finds `@Configuration`/`@Component` and standard Spring beans | `@SpringBootApplication`, `@ComponentScan` |
| SCF function scanning | Finds implementations of functional interfaces by package convention/config | Functional classes without Spring annotations |

**Do not treat `spring.cloud.function.scan.packages` as a cure-all for Spring component scan issues.** For a `@Bean` inside a `@Configuration` class located outside the Spring scan package, fix the configuration class discovery itself first.

### 7.1. Class Name Can Determine the Registered Name

An implementation named `functions.UpperCaseFunction` may be discovered under the name `upperCaseFunction`, rather than `uppercase`. Naming conventions and registration mode determine the final name.

`catalog.getNames(null)` is a far more reliable source of truth than guessing. If stable names are required, prefer `@Bean` or explicit registration.

### 7.2. Disabling SCF Scan Is Different from Removing All @Bean Definitions

`spring.cloud.function.scan.enabled=false` only affects SCF's dedicated function scanning. Standard `@Bean` definitions created by Spring Boot do not disappear because of this property.

## 8. Cause: Bean Has an Unclear Type or Does Not Implement a Java Functional Interface

Spring Cloud Function centers on `java.util.function.Function`, `Supplier`, and `Consumer`.

A custom class with an `apply` method that does not implement `java.util.function.Function`, or a bean with an overly generic declared type, may not be recognized by the framework as expected.

### 8.1. Avoid Declaring @Bean Returning Object

~~~java
@Bean
public Object uppercase() {
    return (Function<String, String>) String::toUpperCase;
}
~~~

This style loses generic type information in the declared signature and can hinder type inference, payload conversion, or catalog registration depending on framework mechanisms.

Prefer:

~~~java
@Bean
public Function<String, String> uppercase() {
    return String::toUpperCase;
}
~~~

### 8.2. Check Imports

~~~java
import java.util.function.Function;
import java.util.function.Consumer;
import java.util.function.Supplier;
~~~

Do not confuse a `Function` from another library or a custom same-named interface with the standard Java functional interfaces.

### 8.3. Functional Registration and FunctionRegistration

In addition to `@Bean`, Spring Cloud Function supports `FunctionalSpringApplication` and `FunctionRegistration`. With functional registration, names and generic type metadata may need to be declared explicitly because lambdas do not always retain full generic information at runtime.

When using this model, verify:

1. Was the function actually registered into the right context?
2. Does `FunctionRegistration` specify the expected name?
3. Was sufficient input/output type information supplied?
4. Were `@Bean` and functional registration accidentally mixed, creating two differently named functions?
5. Do tests run in the same startup mode as production?

Consult the **Functional Bean Definitions** documentation for your deployed version; do not switch startup models just as a workaround for a lookup failure.

### 8.4. Proxies and Runtime Types

AOP proxies, factory beans, or advanced configurations can make the runtime or declared bean type differ from what you expect. Use `applicationContext.getType(name)` and the bean definition to inspect it. Do not blame AOP without evidence.

## 9. Cause: Bean Name Does Not Match Method or Class Name

~~~java
@Bean("normalizeOrder")
public Function<String, String> uppercase() {
    return String::trim;
}
~~~

The declared name here is `normalizeOrder`. A caller looking up `uppercase` will fail because it only looked at the method name.

For a method without an explicit name:

~~~java
@Bean
public Function<String, String> uppercase() {
    return String::toUpperCase;
}
~~~

the default name is `uppercase`.

### 9.1. Five Distinct Name Types

| Name type | Example | Meaning |
| --- | --- | --- |
| Bean/function name | `normalizeOrder` | Function identifier in the catalog |
| Function definition | `normalizeOrder|audit` | Composition of functions |
| HTTP path | `/normalizeOrder` | Web adapter route if exported |
| Stream binding | `normalizeOrder-in-0` and `normalizeOrder-out-0` | Logical connection to the binder |
| Broker destination | `orders-in` and `orders-out` | Topic/queue at the transport layer |

A broker destination is **not** a catalog function name. Do not call `catalog.lookup("orders-in")` if the function is named `normalizeOrder`.

### 9.2. Exact Name Comparison

Do not guess casing differences, abbreviations, or hyphens. Print the actual names via `getNames(null)`. In large deployments, properties may come from a different profile or environment than your local file.

## 10. Special Cause: Single-Function Fallback Masks Typos

The official documentation notes that when an application has only **one eligible functional bean**, looking up with an empty name, `null`, or even an incorrect name can still return **that single function**.

For example, when only `uppercase` exists:

~~~java
Function<String, String> expected =
    catalog.lookup(Function.class, "uppercase");

Function<String, String> misspelled =
    catalog.lookup(Function.class, "upprcase");
~~~

When fallback applies, `misspelled` **may be non-null**. That does **not** prove `upprcase` is actually the function name.

### 10.1. Disabling Fallback in Tests

~~~properties
spring.cloud.function.single-function-fallback-enabled=false
~~~

When disabled, a non-existent name is much easier to catch. This is useful for regression testing function names.

### 10.2. Why Adding a Second Bean Makes the App "Suddenly Fail"

Initially only `uppercase` existed, so `lookup("upprcase")` succeeded via fallback. After adding `reverse`, selection no longer has a single candidate, and the misspelled caller starts failing.

Do not delete `reverse` just to restore fallback. Fix the caller or `spring.cloud.function.definition` to use the exact name.

### 10.3. Do Not Rely on Fallback as a Production Contract

With Spring Cloud Stream and serverless apps that have multiple functions, configure selection explicitly:

~~~properties
spring.cloud.function.definition=uppercase
~~~

and test both the catalog listing and exact-name lookup. Fallback should be understood behavior, not an auto-correction strategy for wrong names.

## 11. Cause: spring.cloud.function.definition Selects the Wrong Function

The property:

~~~properties
spring.cloud.function.definition=uppercase
~~~

selects a function with the matching name.

Meanwhile:

~~~properties
spring.cloud.function.definition=uppercase|reverse
~~~

is **a composition**: the output of `uppercase` flows into `reverse`.

### 11.1. A Missing Function in a Composition

If the configuration is `normalize|enrich|audit` and `enrich` is not registered:

1. Read `catalog.getNames(null)`.
2. Look up `normalize`.
3. Look up `enrich`.
4. Look up `audit`.
5. Check pairwise output/input type compatibility.
6. Finally look up the full definition.

Failure to build a composition **does not mean all beans disappeared**.

### 11.2. Pipe and Semicolon Mean Different Things in Stream

~~~properties
# A single two-step pipeline:
spring.cloud.function.definition=uppercase|reverse
~~~

In Spring Cloud Stream, if you want **two independent functions** bound separately:

~~~properties
spring.cloud.function.definition=uppercase;reverse
~~~

Selection syntax affects the number and names of created bindings. Do not use `;` if your goal is to pipe `uppercase`'s output directly into `reverse`.

### 11.3. Properties Can Be Overridden at Runtime

Even if a source file contains `definition=uppercase`, the deployment may use a different profile, environment variable, or command-line argument.

~~~java
String actual = environment.getProperty(
    "spring.cloud.function.definition", "<unset>"
);
log.info("Runtime function definition={}", actual);
~~~

This reveals the **actual value in the process `Environment`**. Do not log the entire environment because it may contain credentials.

## 12. Cause: Function Excluded by ineligible-definitions

SCF can exclude unwanted beans from the catalog:

~~~properties
spring.cloud.function.ineligible-definitions=foo,bar
~~~

If `uppercase` is placed in this list, the bean may still exist in the context while not being exposed by the catalog.

### 12.1. Required Evidence

- The context contains `uppercase`.
- The catalog does not contain `uppercase`.
- The `spring.cloud.function.ineligible-definitions` property includes that name.
- After adjusting the exclusion appropriately, the catalog exposes the expected name.

Only remove a name from the filter when it is genuinely intended to be exported. Do not broadly disable filtering and expose internal functions.

## 13. Cause: Typed Lookup Uses the Wrong Bean Type

Consider this bean:

~~~java
@Bean
public Supplier<String> greeting() {
    return () -> "hello";
}
~~~

If a caller invokes:

~~~java
Function<String, String> wrong =
    catalog.lookup(Function.class, "greeting");
~~~

it is requesting a `Function` lookup for a `Supplier` bean. The result may mismatch or be rejected under the catalog/adapter contract.

Look it up with the right type when you know it is a supplier:

~~~java
Supplier<String> greeting =
    catalog.lookup(Supplier.class, "greeting");
~~~

| Type | Java method | Contract |
| --- | --- | --- |
| `Supplier<T>` | `get()` | No input |
| `Function<T,R>` | `apply(input)` | Input and output |
| `Consumer<T>` | `accept(input)` | Input, returns `void` |

A `Consumer` does not become a `Function` just because its name is in the catalog. For compositions, verify type compatibility between steps, not just bean existence.

## 14. Cause: Catalog Is Right, but HTTP Endpoint Is Not Exported

Do not conclude the catalog is empty from an HTTP 404.

With the **Spring Cloud Function web adapter** and an exported `uppercase` bean, you can test:

~~~bash
curl -i -X POST \
  -H "Content-Type: text/plain" \
  -H "Accept: text/plain" \
  --data "hello" \
  http://localhost:8080/uppercase
~~~

If the endpoint is missing:

1. Does `catalog.lookup("uppercase")` return a function?
2. Does the app include the Spring Cloud Function web adapter dependency, not just context?
3. Is the server running on the expected port, context path, and proxy setup?
4. Did `spring.cloud.function.web.path` change the base path?
5. Does `spring.cloud.function.definition` restrict which functions are exported?
6. Do HTTP method, content type, and security settings permit the request?
7. Is a reverse proxy/gateway rewriting URLs or blocking paths?

### 14.1. Single-Function Root Mapping

A web adapter may allow calling the root path when only one function exists. Once a second function is added, routing or selection rules can change. Do not write integration tests relying solely on the root path if production has multiple beans.

### 14.2. 404 and Converter Errors Are Different Layers

HTTP 404 typically points to mapping or routing; HTTP 4xx/5xx from body parsing failures can happen **after the function is already selected**. Inspect the request exception/trace to tell them apart.

Do not immediately add a `@RestController` to work around the issue: that uses a separate HTTP mechanism and can mask misconfiguration in the Spring Cloud Function web adapter.

## 15. Cause: Spring Cloud Stream Uses Wrong Definition or Binding

Example bean:

~~~java
@Bean
public Function<String, String> uppercase() {
    return String::toUpperCase;
}
~~~

Stream configuration:

~~~properties
spring.cloud.function.definition=uppercase

spring.cloud.stream.bindings.uppercase-in-0.destination=orders-in
spring.cloud.stream.bindings.uppercase-out-0.destination=orders-out
~~~

Here:

- `uppercase`: function name.
- `uppercase-in-0`: conventional input binding name.
- `uppercase-out-0`: output binding name.
- `orders-in`, `orders-out`: actual destinations on the broker.

A consumer failing to receive messages can be caused by binder connectivity, topic permissions, destination name, or serializer issues, even when `uppercase` is already in the catalog.

### 15.1. Three Independent Checks

1. **Catalog:** does `getNames(null)` include `uppercase`?
2. **Binding:** do startup logs show `uppercase-in-0`/`uppercase-out-0` being created?
3. **Transport:** are destination, consumer group, partitions, credentials, and networking working?

Do not rename the bean just because the topic is wrong. Likewise, do not look up `orders-in` instead of `uppercase`.

### 15.2. Composition Changes Binding Conventions

If the definition is `uppercase|reverse`, the adapter uses the **composition name** according to binding conventions instead of two standalone functions. In apps with multiple definitions, `;` carries a different meaning.

Base your diagnosis on actual binding names logged at startup and the binder/version documentation, rather than guessing solely from an individual bean name.

### 15.3. Message Conversion Happens After Lookup

If a function expects `OrderEvent` while the broker sends `byte[]` or JSON with mismatched headers, a converter error can occur right as the binding passes the message into the wrapper. The function itself may have been found completely fine.

Inspect input generic types, `contentType`, DTOs, serializers/deserializers, and message headers before changing bean names.

## 16. Cause: Confusing Serverless Handler with Business Function

On AWS Lambda or similar serverless platforms, distinguish:

- **Handler/entry point** invoked by the platform.
- **Business function** inside `FunctionCatalog`.
- **Selection/routing property** deciding which function runs.

With SCF's AWS Lambda adapter, a common handler is `org.springframework.cloud.function.adapter.aws.FunctionInvoker`. That class name is **not** the business bean `uppercase`.

### 16.1. Verification Checklist

1. Does the deployment handler/entry point match the packaged adapter type?
2. Do the deployed artifact and version include the function class?
3. Do runtime profiles/conditions create the bean?
4. Does the runtime catalog list the expected name?
5. When multiple functions exist, do `spring.cloud.function.definition` or routing instructions target the right one?
6. Is the event deserialized and passed to the function with the expected type?
7. Are runtime timeout and memory sufficient to boot the Spring context and execute?

An invocation that fails before context creation cannot be fixed by renaming the business function.

## 17. Cause: Confusing RoutingFunction with the Target Function

SCF includes a router with the standard name `functionRouter`. It can delegate to another function via routing instructions:

- `spring.cloud.function.definition`.
- `spring.cloud.function.routing-expression`.
- Routing callbacks or headers in supported cases.

Finding the router **does not mean the target exists**. If a routing expression resolves to `upprcase` while the catalog only has `uppercase`, that is a **target selection** error.

### 17.1. Two-Pass Router Diagnosis

**Pass 1:** is `catalog.lookup("functionRouter")` present and is routing enabled properly in the application?

**Pass 2:** what name does the routing instruction actually produce, is it in `getNames(null)`, and does the target function have compatible input/output types?

Do not see a "router invoked" log line and assume the business function executed.

### 17.2. Reactive Routing Differs from Per-Message Routing

For imperative `Function<T,R>`, the framework can route by message header if configuration supports it. For reactive `Function<Flux<T>,Flux<R>>`, the unit of invocation is typically the **entire stream**; SCF documentation requires routing instructions in application properties for reactive functions rather than switching functions per element via headers.

If you try attaching `spring.cloud.function.definition` to individual messages in a long-lived `Flux` to pick different functions, you may be using the wrong model rather than having a function missing from the catalog.

## 18. Lookup Succeeds but Invocation Fails Is a Different Issue

If:

~~~java
Function<String, String> f =
    catalog.lookup(Function.class, "uppercase");
~~~

returns a valid function yet calling `apply` fails, isolate the issue **after the catalog**.

| Stage | Symptom | What to check |
| --- | --- | --- |
| Input conversion | JSON/bytes fail to become DTO | Generic type, Content-Type, converters |
| Java invocation | Exception inside lambda or service | Business logic and dependencies |
| Reactive execution | `apply(flux)` returns a publisher that does not run | Is there a subscription? |
| Output conversion | Cannot serialize DTO | Output type and converter |
| HTTP adapter | Error response/timeout | Mapping, status, stream lifecycle |
| Stream binder | Messages not sent/acked | Binder and transport |
| Serverless runtime | Invocation timeout | Deadline, routing, context, and I/O |

### 18.1. A Wrapper from the Catalog Is Not Necessarily the Same Instance as the Bean

Do not assert object identity:

~~~java
// Not a required contract of Spring Cloud Function:
// assertSame(context.getBean("uppercase"), catalog.lookup("uppercase"));
~~~

Test behavior instead:

~~~java
Function<String, String> f =
    catalog.lookup(Function.class, "uppercase");

assertThat(f).isNotNull();
assertThat(f.apply("hello")).isEqualTo("HELLO");
~~~

`assertThat` here comes from AssertJ used in tests.

### 18.2. Reactive Functions Must Be Subscribed To

~~~java
Function<Flux<String>, Flux<String>> normalizeStream =
    catalog.lookup(Function.class, "normalizeStream");

Flux<String> output =
    normalizeStream.apply(Flux.just(" A ", " B "));
~~~

With cold Reactor sources, `apply` may only assemble the pipeline. A subscriber is required for operators to process data.

~~~java
StepVerifier.create(output)
    .expectNext("A", "B")
    .verifyComplete();
~~~

Do not treat the absence of `doOnNext` logs as proof that the catalog lacks the function when the publisher has never been subscribed to.

## 19. Diagnostic Decision Tree

~~~mermaid
flowchart TD
    A["Function not working"] --> B{"Context has catalog?"}
    B -->|No| C["Dependency / autoconfiguration / startup"]
    B -->|Yes| D{"catalog.getNames has the name?"}
    D -->|No| E{"ApplicationContext has the bean?"}
    E -->|No| F["@Bean / scan / @Import / profile / condition"]
    E -->|Yes| G["Type / registration / ineligible filter"]
    D -->|Yes| H{"Lookup with right name and type?"}
    H -->|No| I["Wrong name / fallback / composition"]
    H -->|Yes| J{"Direct invocation succeeds?"}
    J -->|No| K["Type conversion / exception / subscription"]
    J -->|Yes| L["HTTP mapping / binder / serverless routing"]
    C --> Z["Verify again"]
    F --> Z
    G --> Z
    I --> Z
    K --> Z
    L --> Z
~~~

### 19.1. Step-by-Step Procedure

1. Read the first exception, not only the last log line.
2. Confirm you are running the right artifact, profile, and dependency versions.
3. Verify `FunctionCatalog` is present in the context.
4. Print `catalog.getNames(null)` and `catalog.size()`.
5. Compare the expected name against actual beans in `ApplicationContext`.
6. If the bean is missing, fix registration/scanning/conditions.
7. If the bean exists but is missing from the catalog, fix type/registration/filtering.
8. If the name is in the catalog, test looking up each function and typed lookups.
9. If using composition, test each part individually before testing the combined definition.
10. Disable fallback in tests so wrong names do not accidentally invoke a single bean.
11. Invoke the function directly with properly typed input.
12. Only then inspect HTTP, Stream binders, or the serverless runtime.

## 20. Testing the Catalog with SpringBootTest

The following test builds on `DiagnosticsApplication` from section 3 (two functions and one supplier):

~~~java
package demo.diagnostics;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.context.ApplicationContext;

@SpringBootTest(
    classes = DiagnosticsApplication.class,
    properties = {
        "spring.cloud.function.single-function-fallback-enabled=false"
    }
)
class CatalogLookupTest {

    @Autowired
    private ApplicationContext context;

    @Autowired
    private FunctionCatalog catalog;

    @Test
    void expectedBeanIsExposedByCatalog() {
        assertThat(context.containsBean("uppercase")).isTrue();

        assertThat(catalog.getNames(null))
            .contains("uppercase", "reverse", "greeting");

        Function<String, String> uppercase =
            catalog.lookup(Function.class, "uppercase");

        assertThat(uppercase).isNotNull();
        assertThat(uppercase.apply("hello")).isEqualTo("HELLO");
    }

    @Test
    void wrongNameIsNotSilentlyAccepted() {
        assertThat(catalog.getNames(null))
            .doesNotContain("upprcase");

        assertThat(catalog.lookup("upprcase")).isNull();
    }

    @Test
    void compositionFindsBothParts() {
        Function<String, String> combined =
            catalog.lookup(Function.class, "uppercase|reverse");

        assertThat(combined).isNotNull();
        assertThat(combined.apply("hello")).isEqualTo("OLLEH");
    }
}
~~~

Assumptions to satisfy:

- The test has compatible Spring Boot Test, Spring Cloud Function, and AssertJ dependencies.
- `DiagnosticsApplication` is used as the test context; another application class is not accidentally loaded.
- Both functions have exact names and signature `String → String`.
- For `Message<?>` or reactive signatures, input preparation and output assertions must adjust accordingly.

### 20.1. Testing the HTTP/Binder Layer Separately

A passing catalog test **does not prove** that HTTP routes or Stream bindings are configured properly.

Add tests across layers:

| Layer | Test focus |
| --- | --- |
| Spring context | Bean created with expected name/type |
| Catalog | `getNames` and `lookup` accurate, wrong names rejected |
| Composition | `a|b` constructed and executes properly |
| Web adapter | Method, path, Content-Type, status, body |
| Spring Cloud Stream | Function definition, binding names, message conversion |
| Broker integration | Destination, delivery/ack/retry per binder |
| Serverless | Handler, event payload, selection, timeout |
| Reactive | Subscription, `onNext`, `onComplete`/`onError` |

Testing with multiple functions is better than testing in a single-function environment, because it exposes errors otherwise masked by single-function fallback.

## 21. Actuator and Logging Support for Diagnostics

Spring Cloud Function documentation describes the `functions` Actuator endpoint if the application has suitable web/Actuator dependencies and the endpoint is exposed.

Example configuration in a secured environment:

~~~properties
management.endpoints.web.exposure.include=health,info,functions
~~~

Then you can try:

~~~bash
curl http://localhost:8080/actuator/functions
~~~

The response can list function names and metadata in the catalog. However:

- Actuator is **not present by default** just because `FunctionCatalog` exists.
- Management port, base path, and security can change the URL.
- An unreachable endpoint **does not prove** the catalog is empty.
- Do not expose sensitive endpoints to the public Internet just for debugging.

### 21.1. Controlled DEBUG Logging

~~~properties
logging.level.org.springframework.cloud.function=DEBUG
logging.level.org.springframework.cloud.stream=DEBUG
~~~

Enable only when genuinely needed, limit duration, and watch log volume. Debug logs may include message-related data; avoid recording unnecessary payloads, headers, or credentials.

### 21.2. What Not to Do

- Do not clear out `ineligible-definitions` just to expose internal functions publicly.
- Do not disable security or leave HTTP function endpoints wide open for testing.
- Do not simultaneously change scan settings, names, definitions, bindings, and converters.
- Do not use `catalog.lookup(null)` as a test confirming **a specific name**.
- Do not conclude a function executed just because `lookup` is non-null without an invocation/subscription test.
- Do not confuse an empty broker queue with the catalog missing a bean.

## 22. Quick Troubleshooting Table by Root Cause

| Issue | Evidence | Action |
| --- | --- | --- |
| Spring lacks bean | `containsBean` is false | Add/fix `@Bean`, scan, import, and conditions |
| Bean name changed | Context has `normalizeOrder`, caller looks up `uppercase` | Fix selected name or naming contract |
| Function scan disabled | Class relies solely on SCF component scan | Check `spring.cloud.function.scan.enabled` |
| Unclear bean type | Declared type `Object` or unexpected proxy | Use explicit `Function<I,O>` type |
| Wrong functional registration | Registration lacks name or metadata | Check `FunctionRegistration` and startup mode |
| Function excluded | `ineligible-definitions` contains the name | Adjust exclusions intentionally |
| Fallback hides wrong name | Typo lookup succeeds with a single function | Disable fallback in tests, fix the name |
| Broken composition | One link missing or types incompatible | Look up and test each step individually |
| HTTP 404 | Catalog lookup OK, URL unmapped | Web module, path, method, security |
| Stream receives no events | Bean OK, binding/transport misconfigured | Definition, destination, binder |
| Lambda routes wrong | Catalog OK, runtime picks wrong target | Handler and deployment config |
| Converter failure | Lookup OK, exception on deserialization | Generic type, contentType, DTO |
| Flux does not run | `apply` returns publisher, nobody subscribes | Caller/adapter subscription |
| Fails only in production | Profile, artifact, env overrides differ from local | Compare runtime config using evidence |

## 23. Self-Assessment Questions

1. How do `ApplicationContext.getBean(...)` and `FunctionCatalog.lookup(...)` differ?
2. Is a Java method returning `Function` without `@Bean` guaranteed to be found by the catalog?
3. Why can placing `@SpringBootApplication` in too deep a package prevent external configurations from loading?
4. How do Spring component scan and SCF Function Component Scan differ?
5. With `@Bean("normalizeOrder")` on a method named `uppercase()`, which name is the valid lookup name?
6. Why does `catalog.lookup("upprcase")` sometimes return a function even though that name was never registered?
7. Which property disables single-function fallback?
8. How do `spring.cloud.function.definition=uppercase|reverse` and `uppercase;reverse` differ?
9. If the context has a function bean but the catalog lacks its name, what should you check?
10. How does `spring.cloud.function.ineligible-definitions` affect the catalog?
11. Why is the broker destination `orders-in` not the lookup name of the `uppercase` function?
12. The catalog has `uppercase`, but HTTP `/uppercase` returns 404: which layers should you check?
13. Catalog lookup works, yet Spring Cloud Stream receives no events: should you check definition, binding, or bean name first?
14. When serverless reports that the target does not exist, how do you distinguish the handler from the business function?
15. Why can the router be found while the target function is still missing?
16. Does an unsubscribed `Function<Flux<T>,Flux<R>>` execute callbacks on a cold source?
17. Why shouldn't a message conversion failure be "fixed" by renaming the function?
18. What test verifies the real function name without being masked by single-function fallback?
19. If `/actuator/functions` returns 404, does that prove the catalog is empty?
20. What information should not be logged when diagnosing production issues?

## 24. References

- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): function registration and lookup, `spring.cloud.function.definition`, composition, fallback, exclusions, routing, and function scanning.
- [Spring Cloud Function — Functional Bean Definitions](https://docs.spring.io/spring-cloud-function/reference/functional.html): functional registration, `FunctionRegistration`, type information.
- [Spring Cloud Function — Standalone Web Applications](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/standalone-web-applications.html): HTTP mapping, paths, and web adapter selection.
- [Spring Cloud Function — AWS Lambda](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html): serverless handlers and routing.
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html): function selection, multiple functions, bindings, and message transport.
- [Spring Framework — Classpath Scanning](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html): scanning mechanisms and bean registration.

This document illustrates diagnostic methodology on a Spring Boot / Spring Cloud Function application. Verify the version/BOM, dependencies, profiles, and adapters of your actual project before applying a specific configuration. Unit test examples do not replace integration tests for HTTP, binders, or serverless platforms.

**Takeaway:** To pinpoint **"Function Not Found in FunctionCatalog"**, inspect in order: **ApplicationContext has the bean → FunctionCatalog has the real name → lookup uses the right name and type → definition/composition is valid → adapter selects the right function → invocation receives properly typed data**. `catalog.getNames(null)` is reliable evidence, while single-function fallback can hide typos. An HTTP 404, a binding receiving no messages, or a converter failure does not by itself prove the catalog is missing a function. Diagnosing boundary by boundary lets you fix the true root cause without breaking other functions, routes, and bindings.
