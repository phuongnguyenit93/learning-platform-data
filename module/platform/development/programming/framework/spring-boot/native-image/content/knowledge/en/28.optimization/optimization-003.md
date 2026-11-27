# Narrowing Reflection, Resource, and Proxy Metadata to Verified Requirements

## 1. Why Narrow Metadata?

GraalVM Native Image analyzes the application at build time and packages only the components it determines are needed. When an application uses reflection, loads resources by name, or creates JDK dynamic proxies, static analysis may not infer the full behavior. In those cases, reachability metadata tells the compiler exactly which classes, members, resources, or interface combinations must be retained.

Metadata is part of correctness, not just configuration to make the build succeed. If you under-register, the application may run fine on the JVM yet fail when hitting a code path in the native executable. If you over-register, the compiler may have to retain extra methods, constructors, fields, resources, or proxies that are not truly needed. That enlarges the reachable set, executable size, analysis/build time, and potentially runtime memory.

Therefore, the goal is to **register the exact access rights that the code actually uses, then prove it through tests and native execution**. Do not shrink metadata by guesswork or delete an entry simply because no error appeared in a single run.

After this lesson, you will be able to:

- Select the `MemberCategory` matching actual reflection operations.
- Replace broad resource wildcards with patterns scoped by directory, file type, or feature.
- Register each JDK proxy combination accurately while preserving interface order.
- Use conditional hints for optional dependencies or features.
- Test registrars with `RuntimeHintsPredicates` and verify on the native executable.
- Evaluate metadata impact using build reports, resource inventories, and before/after measurements.

## 2. Understanding the Scope of Each Metadata Kind

Spring `RuntimeHints` describes the application's dynamic access needs. Spring AOT can gather some needs from bean definitions, controller signatures, serialization/binding, and known integrations. Only manually supplement what AOT cannot infer.

| Metadata Kind | Used When | Example |
|---|---|---|
| Reflection | Code looks up classes/members or invokes constructors/methods/fields via reflection | `Class.getMethod`, `getDeclaredConstructor`, `Method.invoke` |
| Resource | Code loads classpath files by dynamic name or pattern | Templates, schemas, config files, certificates, bundles |
| JDK proxy | Code calls `Proxy.newProxyInstance` with a specific interface list | Proxy implementing `OrderOperations` and `Auditable` |

These three kinds do not substitute for one another. A reflection hint does not put a JSON file into the image; a resource hint does not allow invoking methods via reflection; a proxy hint does not register metadata for every member of an implementation class.

Native Image can receive metadata via Spring `RuntimeHints` converted into native configuration, via `reachability-metadata.json` inside dependencies, or via metadata collected from the Tracing Agent. When a library already ships accurate metadata, avoid adding duplicates in the application without reason.

## 3. Narrowing Reflection to Actual Operations

### 3.1. Distinguishing Introspection from Invocation

Spring `MemberCategory` lets you select the required permissions. Two common groups are:

- `INTROSPECT_*`: allows inspecting constructor/method metadata via reflection without registering permission to invoke them.
- `INVOKE_*`: allows invoking constructors/methods via reflection.

Common categories:

| Category | Scope |
|---|---|
| `INTROSPECT_PUBLIC_METHODS` | Look up public methods, including inherited methods |
| `INTROSPECT_DECLARED_METHODS` | Look up methods declared on the class, excluding inherited methods |
| `INVOKE_PUBLIC_METHODS` | Invoke public methods, including inherited methods |
| `INVOKE_DECLARED_METHODS` | Invoke methods declared on the class |
| `INTROSPECT_PUBLIC_CONSTRUCTORS` | Look up public constructors |
| `INVOKE_PUBLIC_CONSTRUCTORS` | Invoke public constructors |
| `INVOKE_DECLARED_CONSTRUCTORS` | Invoke declared constructors, including non-public when appropriate |
| `PUBLIC_FIELDS` (Spring 6.x) / `ACCESS_PUBLIC_FIELDS` (Spring 7.x) | Access public fields via reflection |
| `DECLARED_FIELDS` (Spring 6.x) / `ACCESS_DECLARED_FIELDS` (Spring 7.x) | Access fields declared on the class |

Choose only the category matching the API the library calls. If code only calls `getMethod()` to check whether a method exists, introspection permission may suffice. If code subsequently calls `Method.invoke()`, invocation metadata is required.

**Differences between Spring Framework 6.x and 7.x:** the `INTROSPECT_*` categories and some introspection categories such as `PUBLIC_CLASSES`/`DECLARED_CLASSES` were deprecated for removal in Spring 7.0 because introspection is included by default when adding a reflection hint for a type. `PUBLIC_FIELDS` and `DECLARED_FIELDS` are replaced by `ACCESS_PUBLIC_FIELDS` and `ACCESS_DECLARED_FIELDS`. When supporting both major versions, prefer registering specific members via `TypeHint.Builder.withMethod(...)`/`withConstructor(...)` or use the category matching the Spring version being compiled against.

### 3.2. Example: Registering One Method Instead of the Whole Class

Suppose a legacy adapter invokes the `code()` method via reflection:

```java
package com.example.orders.plugin;

public class OrderPlugin {

    public String code() {
        return "orders";
    }
}
```

Code path using reflection:

```java
package com.example.orders.plugin;

import java.lang.reflect.Method;

public class OrderPluginInvoker {

    public String invokeCode(OrderPlugin plugin) throws ReflectiveOperationException {
        Method method = OrderPlugin.class.getMethod("code");
        return (String) method.invoke(plugin);
    }
}
```

The registrar can declare only the method that needs to be invoked:

```java
package com.example.orders.plugin;

import java.util.List;

import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class OrderPluginRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(OrderPlugin.class, typeHint ->
                typeHint.withMethod("code", List.of(), ExecutableMode.INVOKE));
    }
}
```

Here only the `code()` method is registered for invocation. There is no need to enable all constructors, fields, and methods of `OrderPlugin` if the application does not use them via reflection.

If the library actually needs to instantiate via the public no-argument constructor, add just that constructor:

```java
hints.reflection().registerType(OrderPlugin.class, typeHint -> typeHint
        .withConstructor(List.of(), ExecutableMode.INVOKE)
        .withMethod("code", List.of(), ExecutableMode.INVOKE));
```

`ExecutableMode.INTROSPECT` fits when only looking up an executable; `ExecutableMode.INVOKE` fits when executing it. This example uses the Spring Framework 6.x/7.x API; always verify Javadoc against the Spring Framework version managed by your project.

### 3.3. When Should You Use a Broader `MemberCategory`?

If a library truly invokes many public methods of a type, you can register the category:

```java
hints.reflection().registerType(
        OrderPlugin.class,
        MemberCategory.INVOKE_PUBLIC_METHODS);
```

This is a broader permission than registering `code()` individually. Use it only when code paths can invoke many public methods and the method list cannot be reasonably described with per-member hints.

Do not default to groups like `allDeclaredMethods`, `allDeclaredFields`, or all constructors for every DTO. For JSON binding, Spring AOT and binding annotations may already generate the needed hints; inspect the output and run native tests before adding duplicate metadata.

### 3.4. Registering Reflection Only When a Class Is Present

A starter may support an optional library. Use `registerTypeIfPresent` so that dependency is not required in every application:

```java
package com.example.orders.autoconfigure;

import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class OptionalMapperRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerTypeIfPresent(
                classLoader,
                "com.vendor.optional.OrderMapper",
                MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
                MemberCategory.INVOKE_PUBLIC_METHODS);
    }
}
```

`registerTypeIfPresent` checks for the class using the supplied class loader and registers hints only when the type exists. If only one constructor or method is needed, use the overload taking a builder to narrow members as in the previous example.

## 4. Narrowing Resource Patterns

### 4.1. Start from the Resources Actually Loaded

Suppose the application only loads the invoice template:

```text
src/main/resources/
  templates/
    orders/
      invoice.html
      receipt.html
    admin/
      dashboard.html
  i18n/
    orders/
      messages.properties
      messages_vi.properties
```

If the application only reads `invoice.html`, register that file:

```java
hints.resources().registerPattern("templates/orders/invoice.html");
```

If a renderer genuinely loads the full order template set, the pattern can be broader while still scoped to the directory:

```java
hints.resources().registerPattern("templates/orders/*.html");
```

Avoid registering `**/*`, `templates/**`, or the entire classpath just to fix one `MissingResourceException`. Resource metadata causes matching files to be included in the native executable, even when part of the content is unused in main flows.

### 4.2. Distinguishing Spring Wildcards from GraalVM JSON Globs

Spring `ResourcePatternHints` uses include/exclude patterns; GraalVM `reachability-metadata.json` uses the `glob` field. Wildcard rules differ by mechanism and version. In current GraalVM JSON metadata:

- `*` matches characters within a single path segment.
- `**` matches across multiple path segments.
- Globs cannot be empty, cannot have a trailing slash, and cannot contain arbitrary consecutive wildcards.

When using the Spring API, read the `ResourcePatternHint` Javadoc for the version in use and write sufficiently narrow patterns. Do not copy a JSON pattern into the Spring API without verifying its semantics.

### 4.3. Using `registerPatternIfPresent` for Optional Resources

If a module is present only in certain applications, check for a marker resource before adding the pattern:

```java
hints.resources().registerPatternIfPresent(
        classLoader,
        "i18n/orders/messages.properties",
        resourceHint -> resourceHint.includes("i18n/orders/messages*.properties"));
```

This method uses `ClassLoader.getResource(location)` to check the location. The checked location is not automatically added to the hint; the pattern inside the builder defines the registered resource set. Pick a marker file guaranteed to exist in the optional module.

### 4.4. Resource Bundles Are a Separate Need

If code calls `ResourceBundle.getBundle("i18n.orders.messages")`, register the bundle base name:

```java
hints.resources().registerResourceBundle("i18n.orders.messages");
```

Do not replace a resource bundle hint with a broad wildcard across all `*.properties`. A bundle can have many locales; configure only the required locales if the application has a build-time locale restriction strategy.

### 4.5. Not Every Resource Needs a Manual Hint

Native Image can infer certain accesses when the receiver and resource name are constants, such as `OrderTemplate.class.getResourceAsStream("invoice.html")`. Spring AOT can also recognize certain resources from framework contracts. Before adding a hint, check:

- Whether the code path uses `Class.getResourceAsStream` with a fixed class and file name.
- Whether the resource is already registered by a library or Spring AOT.
- Whether the resource is loaded using a name constructed from runtime data.
- Whether the file resides on the classpath or on the runtime filesystem.

Filesystem paths like `/etc/orders/runtime.yml` do not need a classpath resource hint; instead, mount/copy the file and configure the appropriate path and read permissions.

## 5. Narrowing JDK Proxy Metadata

### 5.1. Each Interface Combination Is a Separate Proxy

A JDK dynamic proxy is defined by the list of interfaces the proxy implements. Register the exact combination that code passes to `Proxy.newProxyInstance`:

```java
hints.proxies().registerJdkProxy(
        OrderOperations.class,
        Auditable.class);
```

Do not register a hypothetical proxy containing every interface in the system. If the application has two combinations:

```java
new Class<?>[] { OrderOperations.class, Auditable.class }
new Class<?>[] { PaymentOperations.class, Auditable.class }
```

register the two combinations separately:

```java
hints.proxies().registerJdkProxy(
        OrderOperations.class,
        Auditable.class);

hints.proxies().registerJdkProxy(
        PaymentOperations.class,
        Auditable.class);
```

Place these registrations in the proxy module's registrar:

```java
package com.example.orders.proxy;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class OrderProxyRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.proxies().registerJdkProxy(
                OrderOperations.class,
                Auditable.class);
        hints.proxies().registerJdkProxy(
                PaymentOperations.class,
                Auditable.class);
    }
}
```

### 5.2. Preserving Interface Order

Interface order is part of the proxy definition. `[OrderOperations, Auditable]` differs from `[Auditable, OrderOperations]`. If code can produce both orders, register both; if it uses only one, keep the same order in both the factory and the registrar.

Do not add an interface merely because it appears in the target's class hierarchy. Record the exact array passed to `Proxy.newProxyInstance`, including marker interfaces like `Serializable` if runtime truly uses them.

### 5.3. Distinguishing JDK Proxies from Class-Based Proxies

`registerJdkProxy(...)` is for JDK interface proxies. It does not arbitrarily register subclasses generated by CGLIB/Byte Buddy. Proxies managed by Spring AOP can be analyzed and prepared by Spring AOT. Before adding manual hints, check whether the actual proxy is created by Spring AOP, JDK `Proxy`, or a separate class-generation library.

If a custom proxy is built dynamically from a runtime interface list, constrain the set of combinations that can appear at build time. If the interface list is completely arbitrary after deployment, that problem goes beyond adding a broad proxy hint.

## 6. Organizing Hints by Feature and Owning Dependency

### 6.1. Attach the Registrar Near the Component Needing Hints

```java
package com.example.orders.plugin;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(OrderPluginRuntimeHints.class)
public class OrderPluginConfiguration {
}
```

Place `@ImportRuntimeHints` close to the component that uses the metadata. Spring Framework recommends this approach so that if the component is not contributed to the `BeanFactory`, its hints are not contributed either. This ties hints to the feature's lifecycle rather than leaving them global even after the feature is removed.

### 6.2. Splitting Registrars by Feature

For example, an orders module might be organized as:

```text
orders/
  plugin/
    OrderPluginRuntimeHints.java
  templates/
    OrderTemplateRuntimeHints.java
  proxy/
    OrderProxyRuntimeHints.java
```

Each registrar manages only the metadata for its owning component. This split lets reviewers see why a class, resource, or proxy is retained and makes it easy to delete hints when a feature is retired.

### 6.3. Registering Resources Conditionally by Feature

The Spring resource pattern builder lets you attach `reachableType` to a pattern:

```java
import org.springframework.aot.hint.TypeReference;

hints.resources().registerPattern(resourceHint ->
        resourceHint.includes(
                TypeReference.of(OrderExportFeature.class),
                "templates/orders/export/*.html"));
```

The pattern applies only when the type representing the feature is reached. This is a way to scope optional resources by feature when using the Spring `RuntimeHints` API.

In the Spring API, `reachableType` is a reachability condition evaluated at build time by static analysis. It is not identical to `condition.typeReached` in GraalVM JSON, which determines when metadata takes effect at runtime.

## 7. Conditional Reachability Metadata in GraalVM

### 7.1. When to Use `typeReached`

Reachability metadata JSON supports `condition.typeReached`. An entry takes effect only when the specified type is reached at runtime. This is useful when metadata belongs to an optional integration or a feature enabled only when the corresponding type is activated.

Example `META-INF/native-image/com.example/orders/reachability-metadata.json`:

```json
{
  "reflection": [
    {
      "condition": {
        "typeReached": "com.example.orders.export.OrderExportFeature"
      },
      "type": "com.example.orders.export.LegacyOrderFormatter",
      "methods": [
        {
          "name": "format",
          "parameterTypes": ["com.example.orders.Order"]
        }
      ]
    }
  ],
  "resources": [
    {
      "condition": {
        "typeReached": "com.example.orders.export.OrderExportFeature"
      },
      "glob": "templates/orders/export/*.html"
    }
  ]
}
```

Place metadata under `META-INF/native-image/<groupId>/<artifactId>/` on the classpath. The example uses the current GraalVM reachability metadata schema; on older versions, the schema and condition names may differ.

### 7.2. Conditions Are Not Arbitrary Configuration Flags

`typeReached` does not mean a property like `orders.export.enabled=true`. GraalVM checks whether a type is reached during runtime/class initialization. A bare class literal does not necessarily mark a type as reached; class initialization or subtype reachability counts according to GraalVM rules.

A conditional entry can still affect image size if the condition type is reached at build time. Once the type is reached at runtime, the metadata becomes active. Thus, conditional metadata limits activation scope and avoids granting dynamic access before a feature appears; it does not guarantee every entry is zero-cost in size.

### 7.3. Choosing Spring RuntimeHints vs. JSON Metadata

| Scenario | Recommended Approach |
|---|---|
| Metadata belongs to a Spring bean/feature of the application | `RuntimeHintsRegistrar` and `@ImportRuntimeHints` |
| Standalone library supplying metadata for any application using it | `reachability-metadata.json` in the library's artifact |
| Metadata needs to be conditional on type reachability | Conditional `typeReached` entry in JSON or appropriate conditional Spring hint builder |
| Optional resource/class may be absent on the classpath | `registerPatternIfPresent` or `registerTypeIfPresent` |
| Metadata already inferred by the framework | Do not add duplicates if tests confirm coverage is sufficient |

## 8. Testing Each Metadata Group

### 8.1. Testing Reflection Hints

`RuntimeHintsPredicates` lets you verify that a registrar registered invocation access for a specific method:

```java
package com.example.orders.plugin;

import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class OrderPluginRuntimeHintsTests {

    @Test
    void registersOnlyTheRequiredPluginMethod() {
        RuntimeHints hints = new RuntimeHints();
        new OrderPluginRuntimeHints().registerHints(
                hints, getClass().getClassLoader());

        assertThat(RuntimeHintsPredicates.reflection()
                .onMethod(OrderPlugin.class, "code")
                .invoke())
                .accepts(hints);
    }
}
```

A predicate confirms the hint was registered. It does not prove the code path calls the method correctly or that all other reflection in the application is declared.

### 8.2. Testing Resource Patterns

```java
package com.example.orders.templates;

import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class OrderTemplateRuntimeHintsTests {

    @Test
    void registersTheInvoiceTemplate() {
        RuntimeHints hints = new RuntimeHints();
        new OrderTemplateRuntimeHints().registerHints(
                hints, getClass().getClassLoader());

        assertThat(RuntimeHintsPredicates.resource()
                .forResource("templates/orders/invoice.html"))
                .accepts(hints);
    }
}
```

Test an actual resource the application loads, not just the pattern string. If a pattern covers too many files, review the actual count of resources embedded in the image.

### 8.3. Testing Proxy Interface Lists

```java
package com.example.orders.proxy;

import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class OrderProxyRuntimeHintsTests {

    @Test
    void registersTheExpectedOrderedProxyInterfaces() {
        RuntimeHints hints = new RuntimeHints();
        new OrderProxyRuntimeHints().registerHints(
                hints, getClass().getClassLoader());

        assertThat(RuntimeHintsPredicates.proxies()
                .forInterfaces(OrderOperations.class, Auditable.class))
                .accepts(hints);
    }
}
```

The proxy predicate also checks interface order. If the factory produces `[Auditable, OrderOperations]`, the test above should fail until the registrar and factory are aligned.

### 8.4. Native Testing with Missing-Registration Reporting

Predicate unit tests verify Spring metadata declarations. Only the native executable confirms dynamic operations actually work. On GraalVM JDK 23 and later, enable exact reachability metadata when building:

```bash
native-image --exact-reachability-metadata -jar target/order-service.jar order-service
```

Run the executable in warning mode to find places missing registration:

```bash
./order-service -XX:MissingRegistrationReportingMode=Warn
```

In integration tests, use `Exit` to catch even metadata errors that application code catches and ignores:

```bash
./order-service -XX:MissingRegistrationReportingMode=Exit
```

To enable checking for only a single package, use `--exact-reachability-metadata=com.example.orders`. On GraalVM before JDK 23, build option names and missing-registration reporting may differ; check the documentation for your version.

## 9. Using Tracing Agent Without Keeping Everything It Records

The GraalVM Native Image Tracing Agent observes reflection, resources, proxies, and dynamic operations during a JVM run. Generated metadata is evidence of what happened in those scenarios, not an automatically minimal configuration.

Review workflow:

1. Run the agent with selected business scenarios.
2. Merge output from multiple profiles or integrations.
3. Group entries by owning library/feature.
4. Compare with hints already generated by Spring AOT and metadata provided by dependencies.
5. Remove entries belonging solely to test harnesses, tooling, or code paths absent in production.
6. Narrow reflection down to required members, resources down to paths actually read, and proxies down to real interface combinations.
7. Run exact reachability metadata and native integration tests after narrowing.

Do not delete an entry simply because one tracing run did not record it. If an optional feature was not exercised, the agent cannot know its metadata. Before dropping an entry, ensure tests prove the feature does not use it or a native test covers the feature after the change.

## 10. Measuring Metadata Impact

### 10.1. Measure Under Identical Build Conditions

Create the baseline and optimized build with the same:

- GraalVM distribution and JDK version.
- Spring Boot/Spring Framework/dependency versions.
- OS, CPU architecture, and native build flags.
- Business source code and build config differing only in the tested metadata.

Record at least:

| Metric | Meaning |
|---|---|
| Native executable size | Total generated file size |
| Native build duration | Analysis and compilation cost |
| Startup time | Time from process launch until readiness `UP` |
| RSS after warm-up | Resident memory during a representative workload |
| Embedded resource count/size | Set of files packaged into the executable |
| Reflection/proxy errors | Correctness after narrowing metadata |

### 10.2. Checking Embedded Resources

GraalVM can emit a build report:

```bash
native-image --emit build-report -jar target/order-service.jar order-service
```

In the build report, check the Resources section to inspect files included in the image. You can generate a JSON list of embedded resources with:

```bash
native-image -H:+GenerateEmbeddedResourcesFile -jar target/order-service.jar order-service
```

The `embedded-resources.json` file helps cross-check resources by name, origin, and size. Use this report to confirm a narrower pattern actually excludes unnecessary files.

### 10.3. Do Not Conclude from a Single Metric

A metadata change may shrink the executable while barely changing build time, or reduce resource count without noticeably affecting RSS. Measure multiple times under the same workload and compare against the baseline. Most importantly, keep all functional tests passing after narrowing.

## 11. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Native reports missing method even though class has reflection hint | Hint only allows introspection, while code performs invocation | Switch to `INVOKE_*` or `ExecutableMode.INVOKE` for the exact member |
| Added `INVOKE_PUBLIC_METHODS` but constructor still fails | Constructor was not registered | Add only the needed constructor; avoid enabling all constructors if unnecessary |
| Registering `allDeclaredMethods` bloats the image | Many unneeded methods become reachable | Replace with specific members or a narrower category |
| Template not found in native | Wrong resource pattern or resource not retained | Check classpath path, pattern, build report, and `embedded-resources.json` |
| Registering `**/*` to fix one missing file | Pattern is too broad | Register the exact path or smallest sufficient directory/extension |
| Missing optional dependency on classpath breaks AOT | Registrar references optional class directly | Use `registerTypeIfPresent` and `registerPatternIfPresent` |
| Proxy works on JVM but native reports missing proxy | Missing exact JDK interface combination or order | Capture the runtime array and register the same order via `registerJdkProxy` |
| Registered JDK proxy yet CGLIB still fails | Hint targets the wrong proxy type | Check the proxy factory and let Spring AOT handle class-based proxies when possible |
| Tracing Agent generates more entries than needed | Exercised many framework/test paths or lacked filters | Review by owner, remove test-only entries, and narrow before committing |
| Removing hint leaves JVM tests passing while native fails | JVM does not require native metadata; tests missed the dynamic code path | Use exact reachability metadata and native integration tests |
| Conditional entry is not applied | Condition type not reached under GraalVM rules | Check `typeReached`, class initialization, and feature activation flow |

## 12. Hands-On Exercise: Narrowing Metadata for order-service

**Scenario:** `order-service` uses reflection to call `OrderPlugin.code()`, loads `templates/orders/invoice.html`, and creates a proxy implementing `OrderOperations` and `Auditable`. The Tracing Agent recorded several extra unneeded methods, resources, and proxies.

### Step 1 — List Actual Requirements

Document precisely:

- Reflection: which classes, constructors, and methods are looked up vs. invoked.
- Resource: which files are loaded, whether resource bundles exist, and which paths are constructed from runtime data.
- Proxy: the interface array passed to `Proxy.newProxyInstance`, in exact order.

### Step 2 — Write Narrow Registrars

Create three registrars or one per-feature registrar registering only the `code` method, the invoice file, and the `[OrderOperations, Auditable]` proxy. If the export module is optional, use conditional hints.

### Step 3 — Write Predicate Tests

Write `RuntimeHintsPredicates` tests for reflection method access, the invoice resource, and the proxy interface list. Ensure tests fail if the registrar is broadened or the factory changes proxy order.

### Step 4 — Run Tracing Agent and Review

Exercise order creation and invoice export flows. Compare agent output with your written registrars. Retain metadata for optional features if those features are required in production, even if a single agent run did not hit them.

### Step 5 — Build Native with Exact Metadata

Build the executable with `--exact-reachability-metadata`, run with `Warn` to uncover missing registrations, and run native integration tests for all three behaviors. Once error-free, run with `Exit` in CI.

### Step 6 — Compare Results

Record executable size, build time, startup-to-readiness, RSS, and resource inventory before and after. Even if metrics barely shift, keep the narrower metadata when it accurately reflects the runtime contract and tests prove correctness.

### Result Sheet

| Item | Baseline | After Optimization |
|---|---|---|
| Reflection entries/members | _(record)_ | _(record)_ |
| Resource patterns/files | _(record)_ | _(record)_ |
| JDK proxy combinations | _(record)_ | _(record)_ |
| Executable size | _(record)_ | _(record)_ |
| Build duration | _(record)_ | _(record)_ |
| Startup-to-readiness | _(record)_ | _(record)_ |
| RSS after warm-up | _(record)_ | _(record)_ |
| Exact metadata/native tests | PASS/FAIL | PASS/FAIL |

## 13. Key Takeaways

Reflection metadata should describe the exact members looked up or invoked; resource metadata should be restricted to files, directories, and bundles actually used; proxy metadata should describe each exact interface combination in the exact order. Use `registerTypeIfPresent` and `registerPatternIfPresent` for optional dependencies, attach registrars close to owning components, and use `typeReached` when JSON metadata should only take effect alongside a feature.

`RuntimeHintsPredicates` helps test Spring metadata contracts; GraalVM exact reachability metadata together with `MissingRegistrationReportingMode` helps catch errors in the native executable. The Tracing Agent aids discovery, but its output must be reviewed. Consider metadata narrowing complete only when real code paths work in native and before/after measurements are taken under identical conditions.

### Official References

- [Spring Framework — Ahead-of-Time Optimizations and Runtime Hints](https://docs.spring.io/spring-framework/reference/core/aot.html)
- [Spring Framework 6.2 — `ReflectionHints` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aot/hint/ReflectionHints.html)
- [Spring Framework 6.2 — `MemberCategory` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aot/hint/MemberCategory.html)
- [Spring Framework 6.2 — `ResourceHints` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aot/hint/ResourceHints.html)
- [Spring Framework 6.2 — `ProxyHints` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aot/hint/ProxyHints.html)
- [Spring Framework 6.2 — `RuntimeHintsPredicates` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aot/hint/predicate/RuntimeHintsPredicates.html)
- [GraalVM — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/)
- [GraalVM — Troubleshoot Native Image Run-Time Errors](https://www.graalvm.org/latest/reference-manual/native-image/guides/troubleshoot-run-time-errors/)
