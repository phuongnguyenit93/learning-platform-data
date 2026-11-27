# Unintended Function Registered or Exposed

## 1. The Problem: An Internal Function Suddenly Becomes Externally Callable

In a **Spring Cloud Function** application, the development team writes a function to normalize orders and a helper function for administrative maintenance:

~~~java
@Bean
Function<String, String> normalizeOrder() {
    return String::trim;
}

@Bean
Function<String, String> internalRebuildIndex() {
    return key -> indexMaintenance.rebuild(key);
}
~~~

The author of `internalRebuildIndex` intended for only internal Java components to call it. However, both objects are **Spring beans of type `java.util.function.Function`**. Under the Spring Cloud Function model, eligible functional beans in `ApplicationContext` can be registered into `FunctionCatalog`. If the same application includes a web adapter or Spring Cloud Stream, some functions may be **exported as endpoints or selected for bindings** according to the adapter's configuration.

As a result, a seemingly harmless change—adding a `@Bean`, adding a starter, enabling a profile, or importing configuration from a library—can cause the function to unexpectedly:

- appear in `FunctionCatalog.getNames(null)`;
- be mapped by the HTTP adapter as a route;
- be auto-selected by Spring Cloud Stream when it is the only functional bean;
- be chosen by a composition or `functionRouter`;
- become the business function of a serverless invocation.

This is the **"Unintended Function Registered or Exposed"** lesson in the **Diagnostics** chapter. The goal is to investigate precisely what was *registered*, what is actually *callable*, and what was *invoked*, and then block it at the appropriate layer.

> **Three states to distinguish:** **existing in ApplicationContext**, **having a name in FunctionCatalog**, and **being exposed/invoked through an adapter**. They are related but not synonymous.

### Learning Objectives

After this lesson, you will be able to:

1. Identify functional beans accidentally discovered by Spring Cloud Function.
2. Distinguish catalog registration, HTTP endpoint export, Stream binding creation, and serverless routing.
3. Use `ApplicationContext`, `FunctionCatalog`, and runtime configuration to gather evidence.
4. Control `@Bean`/`@Component`, component scanning, function scanning, profiles, and explicit registration.
5. Properly understand `spring.cloud.function.ineligible-definitions`, `spring.cloud.function.definition`, `spring.cloud.stream.function.autodetect`, and single-function fallback.
6. Prevent an internal function from being unintentionally invoked via HTTP headers or the router.
7. Organize access control, negative tests, and incident response procedures.
8. Write Spring Boot tests to prevent an internal function from slipping back into the catalog after refactoring.

## 2. Layer Diagram: Do Not Conflate "Registered" with "Exposed"

Spring Cloud Function supports building business logic with `Supplier`, `Function`, and `Consumer`, looking them up via `FunctionCatalog`, composition, and message conversion. HTTP, event, or serverless adapters use those same functions while deciding **entry points**, **selection**, and **invocation timing** under their own contracts.

~~~mermaid
flowchart TD
    SOURCE["Java code + dependencies + component scan"] --> CONTEXT["Spring ApplicationContext"]
    CONTEXT --> CATALOG["FunctionCatalog"]
    CATALOG --> LOOKUP["lookup / composition / functionRouter"]
    LOOKUP --> HTTP["HTTP Web Adapter"]
    LOOKUP --> STREAM["Spring Cloud Stream binder"]
    LOOKUP --> LAMBDA["Serverless adapter"]
    HTTP --> INVOKE["Function is executed"]
    STREAM --> INVOKE
    LAMBDA --> INVOKE
    CONTEXT --> DIRECT["Spring bean invoked directly\nwithout going through FunctionCatalog"]
~~~

| Layer | Meaning | How to verify |
| --- | --- | --- |
| **Spring Bean** | Object created and managed by the container | `containsBean`, `getBeanNamesForType`, bean definition |
| **FunctionCatalog** | Eligible functional bean exposed by name in the catalog; may use wrappers/composition | `catalog.getNames(null)`, `catalog.lookup(...)` |
| **HTTP export** | Web adapter provides a path/method to call the function | Web adapter config, mappings, actual requests |
| **Stream binding** | Binder connects function input/output to destinations | `spring.cloud.function.definition`, binding logs, broker |
| **Serverless invocation** | Runtime/handler selects the business function | Handler, environment, artifact, routing |
| **Invocation** | Function actually executes and may cause side effects | Traces, business logs, audit logs, metrics |

A bean can exist in the context without being in the catalog. A function can be in the catalog without **having a Stream binding**. A function bound to a broker does not necessarily have an HTTP endpoint. Each layer must be verified independently, especially when assessing security risk.

### 2.1. Do Not Use the Word "Public" Too Early

Having `internalRebuildIndex` in `catalog.getNames(null)` **does not by itself prove** Internet users can invoke it. Conversely, securing an HTTP route **does not by itself prove** the function cannot be invoked via a broker, router, direct bean injection, or another serverless entry point.

To assess exposure, you need additional evidence about **networking**, **authentication/authorization**, **target selection**, **bindings**, and **actual invocation behavior**.

## 3. Start the Investigation from Symptoms

Common warning signs:

| Symptom | What may be happening | What to check first |
| --- | --- | --- |
| `getNames(null)` shows `internalRebuildIndex` | Bean is recognized by the catalog | Bean type, scanning, ineligible filters |
| `/internalRebuildIndex` returns an HTTP response | Web adapter is exporting/routing the function | Web module, function definition, security, request mapping |
| Broker unexpectedly has a consumer or producer | Stream autodetection/binding selected the function | `function.definition`, `function.autodetect`, bindings |
| `Supplier` emits messages periodically on its own | Stream poller triggers the source automatically | Number of functional beans, selected definition, poller |
| Looking up a wrong name runs an internal function | Single-function fallback | Number of eligible functions, fallback property |
| An HTTP header routes to another function | `functionRouter` or adapter supports routing instructions | Routing config, target allowlist, input trust |
| Adding a dependency introduces an unfamiliar function | Autoconfiguration/library bean or function scan | Bean origin, condition report, package |
| Route absent locally, present in production | Different profile/artifact/environment | Dependencies, active profiles, effective properties |
| No HTTP route, yet the function gets invoked | Stream, serverless, or direct caller | Trace entry path, bindings, handler |

**Operational rule:** before deleting a bean or changing multiple properties, determine at **which layer** the unexpected function appears and whether there are signs it has already been invoked unintentionally.

## 4. Intentional Example: Public Function and Internal Function

This example uses Java 17+, Spring Boot, and Spring Cloud Function. Both beans share the type `Function<String,String>`, but their intended uses differ:

~~~java
package demo.exposure;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ExposureApplication {

    public static void main(String[] args) {
        SpringApplication.run(ExposureApplication.class, args);
    }

    @Bean
    Function<String, String> publicNormalize() {
        return value -> value.trim().toUpperCase(Locale.ROOT);
    }

    // Used for maintenance; MUST NOT be exposed publicly.
    @Bean
    Function<String, String> internalRebuildIndex(
            MaintenanceService service) {
        return service::rebuild;
    }
}
~~~

`MaintenanceService` is a hypothetical service with a `String rebuild(String key)` method. In this example, the `internalRebuildIndex` bean can be recognized by Spring Cloud Function **because it is genuinely a `Function` bean**, regardless of the `internal` prefix or the comment saying not to expose it.

Naming something `internal...` is not a safety mechanism. Making a factory method package-private or `private` is not a security barrier for the registered bean object. You need configuration and access controls at the right layers.

### 4.1. Developer Intent vs. Runtime Behavior

| Component | Developer intent | What the runtime may do |
| --- | --- | --- |
| `publicNormalize` | Handle messages/HTTP requests | Can be selected by the catalog and adapters |
| `internalRebuildIndex` | Internal administrative helper | Still qualifies as a `Function` for the catalog |
| `MaintenanceService` | Provide internal Java API | As a regular service, does not automatically become a catalog function |
| `spring-cloud-function-web` | HTTP access | May auto-export functions as routes if web autoconfig is active |
| Stream binder | Event processing | May auto-select a functional bean when only one candidate exists |

To reduce risk, administrative operations that do not require a functional contract should be modeled as **regular service/domain APIs**, rather than creating a `@Bean Function` just to reuse a few lines of code.

## 5. Gathering Evidence: Listing Beans and the Catalog

The first step is to observe inside the running process itself:

~~~java
import java.util.Arrays;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.context.ApplicationContext;

FunctionCatalog catalog = context.getBean(FunctionCatalog.class);

System.out.println("Spring Function beans: " +
    Arrays.toString(
        context.getBeanNamesForType(Function.class)
    ));

System.out.println("Spring Supplier beans: " +
    Arrays.toString(
        context.getBeanNamesForType(Supplier.class)
    ));

System.out.println("Spring Consumer beans: " +
    Arrays.toString(
        context.getBeanNamesForType(Consumer.class)
    ));

System.out.println("Catalog names: " + catalog.getNames(null));
System.out.println("Catalog size: " + catalog.size());
~~~

The two sets of names can differ:

- `ApplicationContext` reflects beans recognized by Spring according to type.
- `FunctionCatalog` provides the names of eligible functions, along with wrapper/custom registration capabilities.
- A function can be excluded from the catalog by SCF while the bean still exists and Spring callers can still inject it directly.
- A function can be added via `FunctionRegistration` or function scanning through mechanisms different from regular `@Bean` declarations.

### 5.1. Read Effective Configuration, Not Just Local Files

~~~java
import org.springframework.core.env.Environment;

void reportSettings(Environment environment) {
    for (String key : new String[] {
        "spring.cloud.function.definition",
        "spring.cloud.function.scan.packages",
        "spring.cloud.function.scan.enabled",
        "spring.cloud.function.ineligible-definitions",
        "spring.cloud.function.single-function-fallback-enabled",
        "spring.cloud.stream.function.autodetect",
        "spring.cloud.function.web.path"
    }) {
        System.out.println(key + "=" +
            environment.getProperty(key, "<unset>"));
    }
}
~~~

This snippet prints only **an allowlist of properties designed not to contain secrets**. Do not replace it by logging the entire `Environment`, all headers, or payloads.

A property in a local `application.yml` is not necessarily the runtime value: command-line arguments, environment variables, profiles, or deployment configuration can override it. Look at the **effective values inside the process**.

### 5.2. Trace the Origin of an Unexpected Bean

Given the discovered name:

~~~java
String name = "internalRebuildIndex";

System.out.println("exists=" + context.containsBean(name));
System.out.println("type=" + context.getType(name));
System.out.println("catalog=" + catalog.getNames(null).contains(name));
~~~

If you need to find the factory method, resource source, or condition, use `ConfigurableListableBeanFactory` and bean definition metadata in a controlled debugging environment. For beans coming from libraries, inspect the exact `factoryBeanName`, `factoryMethodName`, resource description, and condition evaluation report; **do not read through unrelated dependencies unless necessary**.

**Note:** `catalog.lookup("someName") != null` does not always prove the name actually exists, because single-function fallback can return the sole function when given a wrong name. Use `getNames(null)` as the name-verification check and test with fallback disabled.

## 6. Cause A: @Bean Returning Function/Supplier/Consumer Meant Only for Internal Use

A `@Bean` method declares that the returned object belongs to the Spring container:

~~~java
@Bean
Function<String, String> internalFormatter() {
    return input -> internalFormat(input);
}
~~~

If the project only needs that transformation inside another service, this may be **too broad an abstraction**. SCF recognizes beans by functional interface rather than reading "internal" intent from names or comments.

### 6.1. Sustainable Fix: Use a Regular Service

~~~java
import org.springframework.stereotype.Service;

@Service
public class InternalFormatter {

    public String normalizeForAudit(String input) {
        return input.trim();
    }
}
~~~

A function intended for exposure can inject the service:

~~~java
@Bean
Function<String, String> publicNormalize(InternalFormatter formatter) {
    return formatter::normalizeForAudit;
}
~~~

In this design:

- `InternalFormatter` is a service-style business bean, not a functional bean.
- `publicNormalize` is the functional bean exposed intentionally.
- No separate `@Bean Function` is needed for internal formatting.
- The list of functions intended for export remains clean and explicit.

### 6.2. Do Not Delete a Bean While Dependencies Still Inject It

If multiple components inject the `internalFormatter` bean by name/type, switching to a service requires refactoring those DI call sites. Create regression tests before removing or changing a bean, especially if it is also called directly by batch jobs or other workflows.

### 6.3. A @Bean Supplier Can Also Cause Side Effects

~~~java
@Bean
Supplier<String> internalStatusSnapshot() {
    return () -> statusService.snapshot();
}
~~~

With Spring Cloud Stream and a single eligible functional bean, a supplier can be auto-selected as a source and polled according to configuration. `Supplier.get()` might perform I/O or emit data meant only for debugging. This is not merely a risk of "an extra name in a list"; it can trigger **unintended background work**.

If you only need an internal API, use a service with a `snapshot()` method instead of exposing a `Supplier` bean to every adapter.

## 7. Cause B: Component Scan Is Too Broad

A `@Configuration` class located inside a package scanned by Spring registers all `@Bean` methods inside it, including functions meant only for testing, demos, or maintenance.

~~~java
@Configuration
public class ExperimentalFunctions {

    @Bean
    Function<String, String> debugEcho() {
        return Function.identity();
    }
}
~~~

If `ExperimentalFunctions` accidentally resides inside a production-scanned package, `debugEcho` can become a catalog candidate.

### 7.1. Scoping the Fix Properly

- Move demo/test configurations out of the production source set.
- `@Import` only intended functional configurations.
- Keep `@SpringBootApplication` and component scans scoped to appropriate packages.
- Use `@Profile` or `@ConditionalOnProperty` so beans are created only in matching environments.
- Check whether newly added libraries/starters import extra functional configurations.

Example limiting a debug bean:

~~~java
@Configuration
@Profile("local-debug")
class DebugFunctionConfiguration {

    @Bean
    Function<String, String> debugEcho() {
        return Function.identity();
    }
}
~~~

When the `local-debug` profile is inactive, the bean is not created; this is control **at the ApplicationContext layer**. However, profiles are not an authorization mechanism: do not accidentally enable the profile in production and assume `debugEcho` is harmless.

### 7.2. Check @Component on Functional Classes

~~~java
@Component
public class InternalEcho implements Function<String, String> {
    @Override
    public String apply(String value) {
        return value;
    }
}
~~~

This class is **a Spring bean** and implements Java `Function`, so it can enter the catalog if eligible. If you do not want the catalog to recognize it, do not implement/register it as a functional bean in the same context.

## 8. Cause C: Spring Cloud Function Automatically Scans Functional Packages

Besides Spring's normal component scanning, SCF has **Function Component Scan**. The documentation describes discovering implementations of `Function`, `Consumer`, and `Supplier` in a package named `functions` by convention, even when the class has no `@Component`.

Example:

~~~java
package functions;

import java.util.function.Function;

public class DebugEcho implements Function<String, String> {
    @Override
    public String apply(String input) {
        return input;
    }
}
~~~

A class meant only as a helper can be picked up when SCF function scanning is enabled.

Related properties:

~~~properties
spring.cloud.function.scan.packages=demo.allowed.functions
spring.cloud.function.scan.enabled=false
~~~

The two lines above illustrate **two alternative configuration options**, not settings meant to be combined simultaneously. If `scan.enabled=false`, dedicated function scanning is disabled even if packages are specified.

### 8.1. Choosing the Right Option

| Goal | How to handle |
| --- | --- |
| Do not need automatic function scanning | `spring.cloud.function.scan.enabled=false` |
| Need scanning, but not test/debug packages | Point `spring.cloud.function.scan.packages` to allowed packages only |
| Primarily using explicit `@Bean` definitions | Keep Spring component scanning appropriately scoped; SCF scan is unnecessary |
| Must keep a functional class without exporting it | Review registration + `ineligible-definitions`, or separate context/artifact |

**Important:** disabling **SCF function scan** does not remove functional beans created via Spring `@Bean` or `@Component`. These are two separate discovery mechanisms.

### 8.2. Regression After Package Refactoring

After refactoring a `functions` package, the catalog may unexpectedly gain new functions. Tests should assert **the full list of catalog names** or at least a denylist of internal functions, rather than only checking that the intended function still runs.

## 9. Cause D: Autoconfiguration or a Dependency Adds a Functional Bean

A library or starter can create `Function`, `Consumer`, or `Supplier` beans for its own internal purposes. SCF includes default filtering for certain known ineligible beans, yet a newly introduced bean from a library or application may still look like a candidate to the catalog.

Signs:

- Before a dependency update, the catalog did not contain `auditLibraryFunction`.
- After updating a BOM/starter, `getNames(null)` includes that name.
- `ApplicationContext` holds a bean created by a configuration class inside the dependency.
- No application code directly declares the new function.

### 9.1. Checks Before Removing

1. Identify the bean's origin and creation conditions.
2. Check whether the library offers an API or configuration property to disable unnecessary beans.
3. Check which components in the application inject that bean.
4. If the bean is needed in the context but should not enter the catalog, use SCF's filter.
5. If the bean is not needed, adjust the dependency/autoconfiguration or profile intentionally.

Do not forcibly remove a library bean that other components depend on. Resulting injection failures can be worse than having the name appear in the catalog.

## 10. Controlling at the Catalog: ineligible-definitions

Spring Cloud Function provides the property:

~~~properties
spring.cloud.function.ineligible-definitions=internalRebuildIndex,debugEcho
~~~

Under SCF's contract, this list specifies additional bean definition names that should not be treated as `FunctionCatalog` candidates.

### 10.1. What Does This Property Do Exactly?

Suppose you have this bean:

~~~java
@Bean
Function<String, String> internalRebuildIndex(
        MaintenanceService service) {
    return service::rebuild;
}
~~~

With the corresponding filter:

- The Spring `ApplicationContext` **can still contain** the `internalRebuildIndex` bean.
- Callers injecting the bean directly can still invoke it.
- The catalog should not advertise that name as a functional candidate per configuration.
- Adapters that look up only through the catalog will not be able to select the bean by that catalog name when the filter takes effect.
- This does not mean the entire application is automatically secure, since another route or service may still invoke the bean directly.

### 10.2. Verify After Applying

~~~java
boolean existsInContext =
    applicationContext.containsBean("internalRebuildIndex");

boolean appearsInCatalog =
    functionCatalog.getNames(null)
        .contains("internalRebuildIndex");

System.out.println(existsInContext); // May be true.
System.out.println(appearsInCatalog); // Expected to be false.
~~~

Do not rely solely on `lookup("internalRebuildIndex") == null` while single-function fallback might be active. Disable fallback in tests so the lookup cannot fall back to another function.

### 10.3. Comparison Table of Controls

| Control | Bean still in Spring context? | Blocks catalog registration? | Directly blocks HTTP/Stream? |
| --- | --- | --- | --- |
| Do not create `@Bean` / refactor to service | That functional bean no longer exists | Yes, at the source | Indirectly, because no target exists |
| Inactive `@Profile` / `@ConditionalOnProperty` | No | Yes, bean is not created | Indirectly |
| `spring.cloud.function.scan.enabled=false` | Does not affect regular `@Bean` | Blocks registration via SCF scan | Indirectly for SCF-scanned-only classes |
| `spring.cloud.function.ineligible-definitions` | May remain | Yes, at the catalog | Indirectly for catalog-based adapters |
| `spring.cloud.function.definition` | Usually remains | **No**, mainly selects/exports functions | Depends on adapter behavior |
| Spring Security/IAM/gateway | Remains | **No** | Enforces access control at the boundary |

`ineligible-definitions` is a tool for **reducing exposed surface area**, not a standalone security boundary replacing authentication and authorization.

### 10.4. Things to Avoid

- Do not add wildcards or guessed names without verifying the real bean names.
- Do not accidentally exclude a function needed inside a composition.
- Do not assume local file properties are the effective properties in production.
- Do not treat a filtered bean as impossible to execute.
- Do not wipe out default framework filters while investigating an unfamiliar name.

## 11. Controlling at HTTP: The Web Adapter Can Auto-Export Functions

According to Spring Cloud Function documentation, when `spring-cloud-function-web` is enabled in a Spring Boot web application, it supports exporting functional beans as HTTP endpoints. Each function name can become part of a URL path.

For example, when the catalog contains both `publicNormalize` and `internalRebuildIndex`, the web adapter **can export both** unless properly restricted.

~~~bash
# Illustrative example with the web adapter running:
curl -i -X POST \
  -H "Content-Type: text/plain" \
  --data " ord-100 " \
  http://localhost:8080/publicNormalize

# Check whether this endpoint is unintentionally exposed:
curl -i -X POST \
  -H "Content-Type: text/plain" \
  --data "index-42" \
  http://localhost:8080/internalRebuildIndex
~~~

**Do not send the second request against production if it causes side effects without explicit authorization.** During investigation, prefer mapping metadata, staging, or a simulated adapter test to avoid accidentally running real admin commands.

### 11.1. HTTP Exposure Differs from FunctionCatalog

| Check | What it proves |
| --- | --- |
| `catalog.getNames(null)` contains `internalRebuildIndex` | The catalog knows the name |
| `spring-cloud-function-web` beans and web mappings exist | The HTTP adapter is active |
| Route `/internalRebuildIndex` is mapped | An HTTP path exists for it |
| Unauthenticated request executes | Improper exposure risk confirmed |
| Route returns 401/403 to unauthorized caller | Access control exists, though other call paths still need testing |

Do not use HTTP 404 as the sole proof that the catalog lacks a name. The web adapter also has base paths, function selection, routing, and fallback rules.

### 11.2. Selecting Which Functions to Export

The web adapter documentation describes using `spring.cloud.function.definition` with `;` to specify which functions/compositions to export when multiple functions exist in the catalog:

~~~properties
spring.cloud.function.definition=publicNormalize;publicReverse
~~~

Suppose the app genuinely has those two functions intended for exposure; when the configuration applies, the web adapter exports the listed functions.

The `|` operator denotes **composition**, not two independent routes:

~~~properties
# One composition: A then B.
spring.cloud.function.definition=publicNormalize|publicReverse
~~~

### 11.3. Be Careful with Single-Function Selection

Under certain web mapping rules, a single definition can also be used to **map a function or composition to the root path**, or even act as a fallback mapping when the URL does not match a catalog name. Therefore:

- Do not treat setting `spring.cloud.function.definition=publicNormalize` by itself as a strong **access-control list** across all configurations.
- When allowlisting web routes, check the exact selection/export rules of your adapter version.
- Write **negative integration tests** for disallowed URLs, not only positive tests for intended URLs.
- For sensitive operations, separate them into a non-web-exposed context/artifact or block them in Spring Security/gateway instead of relying purely on naming conventions.
- Do not leave internal functions in the catalog if they do not need to be invoked via the catalog.

### 11.4. HTTP Methods and Paths Must Also Be Checked

The web adapter supports certain mapping rules by function type and HTTP method; `spring.cloud.function.web.path` can change the base path. Spring Cloud Function also supports method-specific configurations in some cases.

However, restricting HTTP methods **is not a substitute for authorization**. Allowing only POST does not make an index-rebuild command safe against unauthorized callers. Authentication and authorization are required at the system boundary.

## 12. Function Routing and HTTP Headers: Risk of Unintended Target Selection

Spring Cloud Function provides `functionRouter` to decide which function is invoked. Routing instructions can come from application properties or, in supported scenarios, `Message` headers such as `spring.cloud.function.definition` and `spring.cloud.function.routing-expression`.

Conceptual example:

~~~properties
spring.cloud.function.definition=functionRouter
spring.cloud.function.routing-expression=headers.targetFunction
~~~

If the system forwards a client-controlled request header into `targetFunction` without validation or restriction, a caller could attempt to instruct the router to invoke a function not meant for them.

### 12.1. Risk Path

~~~mermaid
flowchart LR
    CLIENT["HTTP client / external event"] --> HEADER["Routing instruction / header"]
    HEADER --> ROUTER["functionRouter"]
    ROUTER --> CATALOG["FunctionCatalog.lookup(target)"]
    CATALOG --> INTERNAL["Internal Function with side effects"]
~~~

Do not assume all HTTP headers are automatically permitted to choose arbitrary targets in every configuration. **You must inspect header propagation and actual routing paths.** Whenever you intentionally build a router deriving its target from untrusted input, enforce an allowed target list.

### 12.2. Essential Safeguards

1. Allow only authenticated callers to supply routing instructions.
2. At the HTTP/broker boundary, strip or overwrite disallowed internal control headers.
3. Enforce a target **allowlist** based on roles/capabilities, not obscurity of names.
4. Do not expose internal functions via the catalog if unnecessary.
5. Audit **the actual target selected** and caller identity without logging secrets.
6. Add negative tests: an unauthorized user cannot route to `internalRebuildIndex`.

Spring Cloud Function documentation distinguishes expressions evaluated from **message headers** from those in **application properties** regarding evaluation context. Header-based expressions use a more restricted context, but this **does not replace target function authorization**.

### 12.3. Reactive Routing Has a Different Processing Unit

For imperative `Function<T,R>`, a single message can be the routing unit when supported by the adapter. For `Function<Flux<T>, Flux<R>>`, the invocation unit can be the entire stream; per-message header routing does not share the same semantics, and documentation directs using application properties for routing instructions with reactive functions.

If the adapter routes **an entire stream**, a wrong route can send many events into an unintended function. Test using the actual signature and adapter.

## 13. Single-Function Fallback: A Wrong Name Can Still Invoke the Sole Function

Spring Cloud Function supports *single-function fallback*: when only one eligible functional bean exists, looking up with an empty name or an invalid name can resolve to that sole function.

For example, if the catalog contains only `internalRebuildIndex`:

~~~java
var maybeInternal = catalog.lookup("doesNotExist");
~~~

Depending on fallback settings, `maybeInternal` may still resolve to that single function. This risk arises especially when an adapter, router, or caller passes a wrong name and the application executes a side-effecting function anyway.

### 13.1. Disable Fallback When Exact Selection Is Required

~~~properties
spring.cloud.function.single-function-fallback-enabled=false
~~~

When fallback is disabled, callers must provide the real function name. This is very helpful for regression tests, multi-route environments, and sensitive operations.

**Note:** disabling fallback does not remove the bean from the catalog and does not add authentication. It simply reduces the risk of an invalid name mapping to a lone function.

### 13.2. Do Not Only Test lookup("internal") == null

When verifying an internal function is excluded:

1. Check `catalog.getNames(null)` does not contain the internal name.
2. Disable fallback.
3. Verify `lookup("internalRebuildIndex")` does not resolve.
4. Re-check HTTP/Stream/serverless entry points.
5. Ensure direct bean injection occurs only within authorized flows.

## 14. Spring Cloud Stream: A Lone Function Can Be Auto-Bound

An often-overlooked risk: when a Spring Cloud Stream application has only **one functional bean**, the framework can auto-detect and bind that bean even if you **did not set `spring.cloud.function.definition`**. Stream documentation recommends setting an explicit definition property to avoid surprises.

Suppose the application has only:

~~~java
@Bean
Supplier<String> internalStatusSnapshot() {
    return () -> statusService.snapshot();
}
~~~

If auto-selected by Stream as a source, the supplier may be polled on a schedule and publish messages to an output binding instead of sitting idle waiting for internal callers to invoke `get()`.

### 14.1. Disabling Stream Single-Function Autodetection

~~~properties
spring.cloud.stream.function.autodetect=false
~~~

This property controls **Spring Cloud Stream's auto-discovery/auto-binding mechanism**. It does not:

- Remove the bean from `ApplicationContext`.
- Remove the bean from `FunctionCatalog`.
- Disable the web adapter.
- Disable bindings configured **explicitly** via `definition` or other properties.
- Stop self-managed `Supplier`/pollers created directly by application code.

Do not confuse `spring.cloud.stream.function.autodetect` with `spring.cloud.function.single-function-fallback-enabled`: the former governs **Stream auto-binding**, while the latter governs **catalog lookup fallback**.

### 14.2. Selecting Function Bindings Explicitly

~~~properties
spring.cloud.function.definition=publicNormalize

spring.cloud.stream.bindings.publicNormalize-in-0.destination=orders-in
spring.cloud.stream.bindings.publicNormalize-out-0.destination=orders-out
~~~

Here `publicNormalize` is the selected function, and `orders-in`/`orders-out` are broker destinations. If `internalRebuildIndex` remains in the catalog, setting `definition` to bind only `publicNormalize` **does not remove it from the catalog or HTTP**.

### 14.3. Semicolon ; vs. Pipe | Has Major Impact

~~~properties
# Two independent functions/bindings:
spring.cloud.function.definition=publicNormalize;internalRebuildIndex
~~~

If a developer accidentally appends an internal function after `;`, the application can create new bindings for it.

~~~properties
# A composition; publicNormalize output feeds internalRebuildIndex:
spring.cloud.function.definition=publicNormalize|internalRebuildIndex
~~~

In this case, it can even **execute the internal function as a pipeline stage**. When assessing exposure, check not only whether the internal function is a direct entry point, but also whether it appears in any composition or routing target.

### 14.4. Do Not Confuse Stream Bindings with FunctionCatalog

| Name | Example | Purpose |
| --- | --- | --- |
| Function | `publicNormalize` | Logic lookup |
| Input binding | `publicNormalize-in-0` | Message intake channel |
| Output binding | `publicNormalize-out-0` | Message output channel |
| Destination | `orders-in` | External topic/queue |

Explicitly configured bindings/destinations may also be tied to `StreamBridge` without directly referencing a function. Therefore, to confirm whether an internal function was bound by Stream, inspect **runtime bindings**, not just destination lists.

## 15. Supplier and @PollableBean: Work Can Run Even Without HTTP Requests

`Supplier<T>` takes no input, so an external actor must call `get()`. In Spring Cloud Stream, a poller can periodically invoke imperative suppliers; continuous reactive suppliers typically have their publisher retrieved and subscribed to by the adapter. `@PollableBean` marks finite reactive suppliers that may require repeated polling.

~~~java
@Bean
Supplier<String> debugHeartbeat() {
    return () -> "heartbeat";
}
~~~

If this function accidentally becomes a source binding, it can emit messages periodically. For a supplier querying a database or generating expensive reports, the real-world impact includes:

- Queries running off-schedule.
- Data potentially published to an unintended destination.
- Extra system cost or background load.
- Messages potentially leaking internal information.

**Do not rely on "nobody calls the supplier's HTTP endpoint" to assume a supplier is safe.** Inspect Stream bindings, pollers, function definitions, and other adapters.

### 15.1. @PollableBean Does Not Schedule Anything in Function Core

This annotation is a marker; the external adapter/poller decides when to poll. If a supplier is being invoked repeatedly, look for **active pollers**, not just the annotation.

### 15.2. Disable or Restrict at the Right Layer

- If the supplier does not need to be a functional bean, convert it to a service API.
- If it must stay out of the catalog, use `ineligible-definitions` or do not create the bean.
- If Stream should not auto-bind it, disable autodetect or choose an explicit definition.
- If explicit bindings exist, remove the corresponding binding/definition.
- If a poller was created by custom code, stop that scheduler/consumer.
- If a long-lived publisher is running, manage subscription and cancellation properly across its lifecycle.

## 16. Serverless: A Deployed Handler May Invoke an Unintended Function

In serverless environments (such as the AWS Lambda adapter), the runtime invokes a **handler/entry point**, and the adapter uses FunctionCatalog/routing to locate the business function.

A common mistake is assuming that because an internal Java class name does not appear in handler config, the internal function cannot be called. In reality, handler and business function are **two independent layers**.

### 16.1. Control Checklist

| Layer | What to verify |
| --- | --- |
| Artifact | Which functions are packaged in the JAR/container, and which config is active? |
| Handler | Does the runtime invoke the intended adapter/handler? |
| Catalog | Are any internal functions registered? |
| Definition/routing | Does each invocation select only an allowed function? |
| IAM/authorization | Who is permitted to invoke the platform function? |
| Event payload | Are any headers/fields influencing function selection? |
| Timeout/retry | Could platform retries replay unintended side effects? |

If a Lambda packages multiple functional beans without explicit selection, target resolution may behave unexpectedly. Use intentional definition/routing and test against an artifact matching deployment.

### 16.2. Defense in Depth

Configure the target business function properly, lock down runtime invoke permissions, and keep unnecessary internal functions out of the catalog. Even an endpoint/serverless invocation protected by IAM must be tested so callers cannot redirect execution to another function via influential routing headers.

## 17. FunctionCatalog, Composition, and FunctionRegistration

SCF documentation states that functional beans in `ApplicationContext` are registered into the catalog lazily. Beyond `@Bean`, there are **`FunctionRegistration`** and the functional startup model.

Consequently, searching source code solely for `@Bean Function` is insufficient if the application:

- registers functions via initializers;
- configures `FunctionalSpringApplication`;
- constructs `FunctionRegistration` with specific names;
- uses a library that auto-registers functions;
- defines compositions or routers built from existing functions.

### 17.1. Composition Names Can Also Be Targets

~~~properties
spring.cloud.function.definition=publicNormalize|internalRebuildIndex
~~~

Even if `internalRebuildIndex` is not looked up directly by callers, it is still invoked as part of the **definition**. Review every active composition accordingly.

### 17.2. Do Not Use Catalog Filtering to Fix Business Logic

If `internalRebuildIndex` is genuinely an internal step inside a permitted flow, excluding it from the catalog could break the `publicNormalize|internalRebuildIndex` composition. Instead:

1. Evaluate whether the flow truly needs that step to be an independent functional bean.
2. If it is merely a dependency of `publicNormalize`, convert it into a service called internally.
3. If composition is required, protect function selection and permit only intended routes.
4. Test both allowed and forbidden paths.

**Design question:** do you need a **function for composition** or simply a **business method**? Not every helper belongs in the catalog as an exposed functional bean.

## 18. Security Controls: Filtering Names Is Not Authorization

When a function performs sensitive actions such as deleting data, rebuilding indexes, issuing tokens, or sending customer details, the risk is not just "its name is in the catalog". The risk is **who can trigger it and through what paths**.

### 18.1. Layered Controls

| Control | Role | Limitation |
| --- | --- | --- |
| Do not register internal function | Shrinks functional surface | Other services may still call equivalent APIs |
| `ineligible-definitions` | Prevents catalog from treating bean as candidate | Does not remove bean from context |
| HTTP function selection | Restricts functions exported by web adapter | Requires checking actual fallback/mapping; does not authenticate |
| Spring Security/gateway | Authentication, authorization, request restrictions | Must cover every route/routing path |
| Binder ACL/IAM | Limits who can publish/consume messages | Does not replace business-level checks |
| Serverless IAM | Limits runtime invocation permissions | Does not automatically restrict internal catalog targets |
| Audit logs/metrics | Detects anomalous invocations | Does not prevent commands that already ran |
| Separate deployment/context | Isolates trust boundaries | Increases operational overhead while reducing blast radius |

**Design recommendation:** for high-impact operations, prefer isolating them in a **separate internal application/context or deployment** when reliable isolation is required. Bean names are not security boundaries.

### 18.2. Example HTTP Policy

In an application with Spring Security, you can structure path-based protection:

~~~java
@Bean
SecurityFilterChain security(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/publicNormalize")
                .hasAuthority("SCOPE_orders.write")
            .anyRequest().denyAll()
        )
        .oauth2ResourceServer(oauth -> oauth.jwt())
        .build();
}
~~~

This is a **partial illustrative snippet**, assuming the app uses a Spring Security version supporting this DSL, full JWT configuration, and an API-appropriate CSRF policy. In production, account for base paths, HTTP methods, proxy rewrites, Actuator/management ports, and composition/root/fallback routes; do not copy this snippet verbatim as complete security.

The goal of the example is **per-route permission allowlisting** with deny-by-default, rather than disabling security to test endpoints.

### 18.3. What If Routes Can Be Remapped via Definition?

Some web adapter settings allow mapping a function/composition to the root path or handling paths that do not match catalog names. Thus a security rule matching only `/internalRebuildIndex` may be insufficient if the same function can be reached via root, composition, or routing. Authorization must align with the **final target or capability**, backed by network/auth controls and negative tests.

## 19. Response Procedure When an Internal Function Is Found Exposed

If there are signs a sensitive function is currently accessible, prioritize risk mitigation first and refactor afterward.

### 19.1. Response Sequence

1. **Preserve non-destructive evidence:** function name, version, effective configuration, mappings, bindings, timestamps, and available traces.
2. **Identify entry paths:** HTTP, broker, serverless, router, or direct callers; multiple paths can coexist.
3. **Block unauthorized access:** update authorization, gateway, broker ACL, or IAM policies, or temporarily disable bindings/routes following operational procedures.
4. **Assess prior impact:** check logs and audit trails for invocations, side effects, or data leakage.
5. **Apply minimal fix:** catalog filtering, bean registration changes, definition restrictions, disabling autodetect, or removing unneeded adapters.
6. **Run negative and positive tests:** internal target cannot be invoked; legitimate public functions still work.
7. **Controlled rollout:** monitor startup, catalog names, bindings, HTTP routes, and metrics post-deploy.
8. **Prevent recurrence:** add regression tests, configuration reviews, and code ownership checks.

**Do not perform side-effecting probes by sending requests to a suspected exposed admin function** in production. Prefer inspecting mappings, staging, or mocked execution. If unauthorized access already occurred, follow your organization's security incident response process, including assessing data modifications and credentials if necessary.

### 19.2. Avoid Fixing the Wrong Layer

For example:

- Removing the HTTP starter blocks HTTP, yet **Stream bindings keep running**.
- Disabling Stream autodetect does not remove a function from **web endpoints**.
- `ineligible-definitions` does not stop a `@RestController` from injecting an internal service directly.
- Changing a broker destination does not automatically change a function name or HTTP path.
- Renaming a bean may break old compositions/bindings, yet it is not a complete security policy.

## 20. Catalog Test: Internal Function Must Not Be a Candidate

The test below uses an explicitly configured application and does not rely on automatic source scanning.

### 20.1. Illustrative Test Configuration

~~~java
package demo.exposure;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ExposureTestApplication {

    @Bean
    public Function<String, String> publicNormalize() {
        return value -> value.trim().toUpperCase(Locale.ROOT);
    }

    @Bean
    public Function<String, String> internalRebuildIndex() {
        return key -> "REBUILT-" + key;
    }
}
~~~

In the test, `internalRebuildIndex` simply returns a string; it performs **no** real database operations. The goal is to verify catalog filtering without side effects.

### 20.2. @SpringBootTest Confirming Exclusion

~~~java
package demo.exposure;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.context.ApplicationContext;

@SpringBootTest(
    classes = ExposureTestApplication.class,
    properties = {
        "spring.cloud.function.ineligible-definitions=internalRebuildIndex",
        "spring.cloud.function.single-function-fallback-enabled=false",
        "spring.cloud.function.scan.enabled=false",
        "spring.cloud.stream.function.autodetect=false"
    }
)
class CatalogExposureTest {

    @Autowired
    private ApplicationContext context;

    @Autowired
    private FunctionCatalog catalog;

    @Test
    void internalBeanMayExistButMustNotBeInCatalog() {
        assertThat(context.containsBean("internalRebuildIndex"))
            .isTrue();

        assertThat(catalog.getNames(null))
            .contains("publicNormalize")
            .doesNotContain("internalRebuildIndex");

        assertThat(catalog.lookup("internalRebuildIndex"))
            .isNull();
    }

    @Test
    void publicFunctionStillWorks() {
        Function<String, String> fn =
            catalog.lookup(Function.class, "publicNormalize");

        assertThat(fn).isNotNull();
        assertThat(fn.apply("  order-10 "))
            .isEqualTo("ORDER-10");
    }
}
~~~

This test serves three purposes:

1. Proves the internal bean may still exist in the Spring context.
2. Proves the catalog **does not expose** the internal name when filtering is applied.
3. Proves the public function was not accidentally excluded and still works.

Compatible Spring Boot Test, Spring Cloud Function, JUnit 5, and AssertJ dependencies are required. Do not extrapolate this test context directly to production if dependencies, profiles, starters, or bindings differ.

### 20.3. Why Disable Single-Function Fallback in the Test?

After filtering out `internalRebuildIndex`, the catalog may contain only one application-declared function. If fallback remains enabled, `lookup("internalRebuildIndex")` could return **the sole remaining function** even though the internal name was excluded, giving misleading test results.

Setting `single-function-fallback-enabled=false` enables exact-name verification.

### 20.4. Check the Full Inventory Instead of Only a Denylist

A stricter test can compare the catalog name set against the allowed functions:

~~~java
Set<String> names = catalog.getNames(null);

assertThat(names)
    .contains("publicNormalize")
    .doesNotContain(
        "internalRebuildIndex",
        "debugEcho",
        "internalStatusSnapshot"
    );
~~~

If the test environment includes built-in router/framework functions, the catalog set may contain supporting names; distinguish framework names from application-owned functional beans before using `containsExactlyInAnyOrder`. Avoid brittle tests that raise false alarms on every library upgrade.

## 21. HTTP, Stream, and Serverless Tests: Verifying *Cannot Be Invoked* Matters as Much as *Can Be Invoked*

### 21.1. HTTP Negative Test

For projects using `spring-cloud-function-web`, Spring MVC Test, or full HTTP integration tests, verify:

- `/publicNormalize` succeeds for authorized callers.
- `/internalRebuildIndex` cannot be invoked by unauthorized callers.
- Root path `/`, unfamiliar URLs, composition paths, and HTTP methods do not open indirect paths to the internal target.
- Routing headers cannot coerce the adapter into invoking an internal function.
- If the real function has side effects, use a spy/fake service to assert **zero invocations**, not just an HTTP status code.

You can state test goals in behavioral form:

~~~text
GIVEN catalog contains publicNormalize
AND internalRebuildIndex must not be callable from HTTP

WHEN unauthenticated user POSTs /internalRebuildIndex
THEN request is rejected
AND maintenanceService.rebuild() is never called

WHEN authorized user POSTs /publicNormalize
THEN only publicNormalize is invoked
~~~

Do not hardcode one HTTP status code across every configuration: 401, 403, or 404 may each be valid depending on security and routing policy. What matters is that **the target cannot be invoked**.

### 21.2. Stream Negative Test

If the application uses Spring Cloud Stream, inspect the **actual bindings** created at startup, not just `catalog.getNames(null)`:

~~~text
Expected binding:
  publicNormalize-in-0
  publicNormalize-out-0

Unexpected:
  internalRebuildIndex-in-0
  internalRebuildIndex-out-0
  internalStatusSnapshot-out-0
~~~

Tests can use the test binder supported by your version or broker integration tests. For functions with output or suppliers, tests should ensure **no messages are sent to unintended internal destinations**.

If the app uses `StreamBridge` and explicit bindings not tied to functions, tests should distinguish those bindings from functional-model bindings.

### 21.3. Serverless Negative Test

Craft realistic event invocations and confirm:

- The handler/definition selects the expected public function.
- Events cannot alter the routing target to an internal function for unauthorized callers.
- No internal service side effects occur.
- Platform timeouts/retries cannot re-trigger an internal target.
- IAM/authorization policies are properly configured in the actual deployment.

A catalog unit test cannot replace runtime/handler tests or IAM policy verification.

## 22. Actuator and Logging: Observe Without Creating New Risk

Depending on dependencies and configuration, Spring Cloud Function may provide an Actuator endpoint listing functions.

Example configuration strictly for a secured diagnostic environment:

~~~properties
management.endpoints.web.exposure.include=health,info,functions
~~~

If the endpoint is available and exposed:

~~~bash
curl http://localhost:8080/actuator/functions
~~~

It helps observe the function names and types known to the catalog. However:

- Actuator is not present automatically just because `FunctionCatalog` is added.
- The URL also depends on management port/base path and security.
- An unresponsive endpoint **does not prove** the catalog is empty.
- Do not expose management endpoints to the Internet just for diagnostics.
- Catalog metadata can reveal internal task names; restrict who can view it.

### 22.1. Targeted Logging

~~~properties
logging.level.org.springframework.cloud.function=DEBUG
logging.level.org.springframework.cloud.stream=DEBUG
~~~

Enable for a controlled window and avoid logging full payloads or secrets. For unintended exposure incidents, prioritize logging **registration**, **function selection**, **HTTP mapping**, **binding creation**, and **actual invocation** milestones, accompanied by an approved correlation ID.

### 22.2. Observe the Right Signals

| Layer | Useful metric / log |
| --- | --- |
| Spring context | Bean names, types, source configuration |
| Catalog | Function name inventory, size, lookup target |
| HTTP | Route mapping, method, status, authorized principal, target |
| Stream | Binding names, destinations, consumer group, publisher count |
| Serverless | Handler, selected function, invocation ID, errors |
| Business | Side-effect counts for sensitive functions, audit ID |
| Security | Denied attempts, unusual routing targets, IAM access |

Do not treat the absence of `onNext` logs as proof a function does not exist: in a reactive function, a cold publisher might simply not have been subscribed to yet.

## 23. Remediation Decision Diagram

~~~mermaid
flowchart TD
    START["Unexpected function detected"] --> CTX{"In ApplicationContext?"}
    CTX -->|No| OTHER["Check router/alias\nor wrong process/artifact"]
    CTX -->|Yes| NEED{"Does this bean need to exist?"}
    NEED -->|No| REMOVE["Remove registration or disable condition/profile"]
    NEED -->|Yes| CAT{"In FunctionCatalog?"}
    CAT -->|Yes, but catalog unneeded| FILTER["ineligible-definitions\nor refactor to service"]
    CAT -->|No| DIRECT["Check direct callers / other adapters"]
    CAT -->|Yes, needed internally in catalog| EXPOSE{"How is it exposed externally?"}
    EXPOSE -->|HTTP| WEB["Allowlist + security + negative route tests"]
    EXPOSE -->|Stream| BINDER["definition + autodetect + binding policy"]
    EXPOSE -->|Serverless| RUNTIME["handler + routing + IAM"]
    EXPOSE -->|Router| ROUTER["Target allowlist + input trust"]
    REMOVE --> VERIFY["Re-verify every entry path"]
    FILTER --> VERIFY
    DIRECT --> VERIFY
    WEB --> VERIFY
    BINDER --> VERIFY
    RUNTIME --> VERIFY
    ROUTER --> VERIFY
    OTHER --> VERIFY
~~~

### 23.1. Pre-Fix Checklist

1. At which layer was the function detected: context, catalog, HTTP, Stream, or serverless?
2. Is there evidence of actual execution, or only presence in the catalog?
3. Did the bean originate from `@Bean`, `@Component`, SCF function scan, or a new dependency?
4. Are profiles, conditions, configuration imports, or environment overrides involved?
5. Is `ineligible-definitions` active, and which names does it contain?
6. Is `spring.cloud.function.definition` selecting one function, a composition, or multiple independent functions?
7. Is Stream `function.autodetect` automatically picking up a sole bean?
8. Does the router accept targets from untrusted headers or payloads?
9. Is the web adapter mapping root, unfamiliar URLs, or unintended compositions?
10. Could a filter change break another legitimate pipeline?
11. Are proper security/IAM/ACL controls in place across every invocation path?
12. After the fix, do negative tests confirm the target cannot be invoked?

## 24. Common Misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| "Naming a bean `internalFoo` stops SCF from exposing it." | Names carry no security meaning; type, registration, and adapters govern exposure. |
| "Being in `FunctionCatalog` guarantees a public HTTP endpoint exists." | Web adapter, mappings, and network/security also matter. |
| "No HTTP endpoint means the function cannot be invoked." | Brokers, routers, serverless, or direct Java callers can still invoke it. |
| "`spring.cloud.function.definition` removes other functions from the catalog." | It primarily selects/composes/exports per adapter rather than deleting beans. |
| "`ineligible-definitions` alone provides complete security." | Beans can still be injected directly; authorization is still required. |
| "`scan.enabled=false` deletes all `@Bean Function` beans." | It only disables SCF function component scan, not standard Spring component scan. |
| "`function.autodetect=false` disables the HTTP/web adapter." | That is a Spring Cloud Stream auto-binding property. |
| "A single function sits idle if `definition` is unset." | Stream can auto-bind a lone functional bean. |
| "A `Supplier` never runs on its own." | Adapter pollers can trigger suppliers automatically. |
| "`;` and `|` in definitions mean the same thing." | `;` selects multiple independent functions; `|` builds a composition. |
| "Single-function fallback only affects empty names." | Non-existent names can also resolve to the lone function. |
| "Protecting `/internalFoo` is enough even with root/composition routing." | Other entry paths may remain; test the ultimate target. |
| "Restricted header expressions mean target authorization isn't needed." | A restricted expression context does not replace authorization. |
| "Actuator listing functions proves Internet exposure." | Check security, networking, and actual endpoints. |
| "Removing the web starter stops broker consumers." | The two adapters have separate lifecycles and configurations. |
| "Seeing no `Flux` logs means the function doesn't run." | A cold source may simply lack a subscription; inspect subscription wiring. |

## 25. Self-Assessment Questions

1. How does a function bean appearing in `ApplicationContext` differ from appearing in `FunctionCatalog`?
2. Can a helper `@Bean Function<String,String>` still be recognized by the catalog even if its name contains `internal`?
3. When should you refactor a helper into a `@Service` instead of a functional bean?
4. How do Spring component scan and SCF function scan differ?
5. Which property disables SCF function component scan, and does it remove standard `@Bean` beans?
6. Does `spring.cloud.function.ineligible-definitions` remove the object from the context or only exclude it as a catalog candidate?
7. Why can a newly added library bean also become a functional candidate?
8. Why can `catalog.lookup("badName")` be dangerous when only one functional bean exists?
9. Which property disables single-function fallback?
10. When adding `spring-cloud-function-web`, which routes should have negative tests?
11. How does `spring.cloud.function.definition=foo;bar` differ from `foo|bar` at the web and Stream layers?
12. Why is setting `definition=publicNormalize` alone not considered sufficient authorization?
13. Can Stream auto-bind a sole `Supplier`? How do you prevent this auto-binding?
14. Why doesn't `spring.cloud.stream.function.autodetect=false` clear the catalog?
15. What distinguishes a function name, a Stream binding name, and a destination?
16. If a router obtains its target from a header, where must allowlisting and authorization be enforced?
17. Why is reactive function routing not strictly equivalent to per-message routing for imperative functions?
18. How do a serverless handler and a business function name differ?
19. In a test, how do you prove an internal bean still exists in the context while remaining absent from the catalog?
20. Why should negative integration tests verify **zero side effects**, not just HTTP status codes?
21. If production shows signs an administrative function is being called, in what order should you respond to reduce risk?
22. Which observations distinguish "unintended registration" from "actually exposed/invoked"?

## 26. References

- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html) — functional beans in `ApplicationContext`, `FunctionCatalog`, single-function fallback, `ineligible-definitions`, function scanning, composition, and routing.
- [Spring Cloud Function — Standalone Web Applications](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/standalone-web-applications.html) — HTTP auto-export, function filtering, root mapping, and method-specific routes.
- [Spring Cloud Function — Functional Bean Definitions](https://docs.spring.io/spring-cloud-function/reference/functional.html) — `FunctionalSpringApplication`, `FunctionRegistration`, and type metadata.
- [Spring Cloud Function — AWS Adapter](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html) — handlers and business function selection on Lambda.
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html) — function selection, auto-binding, supplier polling, and multiple independent functions.
- [Spring Framework — Classpath Scanning](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html) — `@Configuration`, `@Component`, and bean registration.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html) — request-level HTTP authorization and default policies.

The examples use Java 17+ and common Spring Cloud Function / Spring Cloud Stream APIs. Details of auto-configuration, web mappings, routing, starters, and method-specific properties may vary across versions. Verify your actual project's BOM/dependencies and run integration tests against the exact adapter being deployed.

**Takeaway:** A `Function`/`Supplier`/`Consumer` that inadvertently becomes a Spring bean can be discovered by `FunctionCatalog`; once you add a web adapter, binder, or serverless runtime, **exposure or automatic invocation** depends on adapter boundaries. Trace **ApplicationContext → FunctionCatalog → function definition/routing → HTTP/Stream/serverless → actual invocation**. If a bean does not need to be a functional bean, refactor it into a service; if it simply should not enter the catalog, look at `ineligible-definitions`; if it is being invoked unintentionally, enforce selection, auto-binding, and authorization at the proper layers. Always test both allowed and **disallowed** paths, because function name filtering does not replace security.
