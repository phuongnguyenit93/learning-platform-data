# Customizing Names and Tags with ObservationConvention

## 1. Why Is a Dedicated Naming and Tagging Convention Needed?

Suppose several methods observe order processing. If each place invents its own names and tags, forms like these easily appear:

```text
checkout
orders.checkout
process-order
checkout.demo-101
```

They may describe the same kind of work yet split into separate data groups. Including an order ID in the name even causes the number of names to grow with every execution.

The same issue happens with tags: one place uses `channel=web`, another uses `source=website`, and another records a raw user-entered string. Charts and alerts then become hard to compare, and the number of tag combinations can grow uncontrollably.

`ObservationConvention` separates **naming and metadata generation rules** from the code that **starts, runs, and stops the work**:

```text
Data of one execution
           |
           v
    Observation.Context
           |
           v
    ObservationConvention
    - observation name
    - contextual name
    - low-cardinality tags
    - high-cardinality tags
           |
           v
       Observation
           |
           v
 Matching handler → metrics / traces / other observation behavior
```

As a result, we can change tagging conventions while keeping the observed business logic unchanged. A convention does not replace the `start/scope/error/stop` lifecycle, nor does it send data to a backend on its own.

The hands-on exercise uses four cases in the same program: default, global, custom passed directly, and a factory receiving a name directly. The goal is to understand **which convention is selected and which metadata actually exists in the context**, rather than merely seeing which class name was declared.

## 2. Key Methods of ObservationConvention

A convention is typed to a specific context, for example:

```java
ObservationConvention<CheckoutContext>
```

`CheckoutContext` is an application class extending `Observation.Context`; the full example is defined in the hands-on section.

| Method | Role | Example in lesson |
| --- | --- | --- |
| `supportsContext(Observation.Context)` | Indicates which context type the convention supports | Accepts only `CheckoutContext` |
| `getName()` | Provides a stable observation name | `checkout.process` |
| `getContextualName(context)` | Provides a contextual descriptive name | `process checkout` |
| `getLowCardinalityKeyValues(context)` | Generates tags with a controlled value set | `channel=web`, `result=success` |
| `getHighCardinalityKeyValues(context)` | Generates metadata that may have very many distinct values | Simulated order ID `order.id=demo-101` |

There is no need to perform business logic inside these getters. They should read data already in the context and return the corresponding convention output.

### 2.1. Stable Name Differs from Contextual Name

`getName()` describes the **type of work**, not the identifier of an individual execution. For example:

```text
Sensible:  checkout.process
Avoid:     checkout.demo-101
Avoid:     checkout.2026-11-05T10:23:41
```

The observation name is typically used by metrics integrations as the basis for naming meters. Each registry/backend may also normalize names into its own format. Changing an observation name can break existing queries, dashboards, or alerts relying on the old name.

`getContextualName(context)` is a more human-readable descriptive name. A tracing integration may use it to name spans. It is not a place to dump all business parameters into the name automatically.

In this lesson, `checkout.process` and `process checkout` intentionally describe the same kind of work in two different roles. Contextual naming also requires considering stability and searchability, avoiding arbitrarily concatenating private user data.

### 2.2. Tags and Names Solve Two Different Questions

The name answers "what work is being observed?". Tags answer "which group does that work belong to?".

For example:

```text
name = checkout.process
low  = {channel=web, result=success}
```

Keeping one work name and grouping by bounded tags makes comparing `web` against `store` much clearer than creating a new metric name for every variant of input data.

Do not pack monetary amounts, product lists, or order IDs into one large string tag instead of modeling the measurement dimensions actually needed.

### 2.3. supportsContext Is the Boundary of Applicability

In the example:

```java
@Override
public boolean supportsContext(Observation.Context context) {
    return context instanceof CheckoutContext;
}
```

This check matters when a convention is looked up via registry configuration, especially a global convention. The registry may be shared across HTTP, database, and custom business observations; a checkout convention should not handle all of those context types.

Having the same observation name does not turn a plain `Observation.Context` into a `CheckoutContext`. The generic type in the declaration also does not replace selecting the right context when instrumentation runs.

When passing a convention explicitly, instrumentation must still pass the exact context type the convention reads; do not try to force a business convention onto an incompatible HTTP context.

## 3. Classifying Tags by Value Count

### 3.1. Low Cardinality Must Be Designed, Not Merely Named That Way

Cardinality is the number of value combinations that create distinct series or data groups. A tag declared via `getLowCardinalityKeyValues` does not automatically become low-cardinality if you return unbounded data.

Design example in this lesson:

| Tag | Expected value set | How it is produced |
| --- | --- | --- |
| `channel` | `web`, `store`, `other` | Normalize input into three groups |
| `result` | `pending`, `success`, `failure` | Bounded states in the example |
| `deployment.region` | A few known deployment regions | Taken from controlled configuration |
| `tier` | A few predefined service tiers | Do not use arbitrary names straight from requests |

If `channel` accepted every external string directly, the value set could grow very large even though the tag name sounds simple. That is why the example maps any value other than `web/store`, including `null`, to `other`.

This normalization serves **observation grouping**. It does not repair or validate business inputs. If an invalid channel must be rejected under the business contract, business logic must still enforce that.

With three channel values, three result values, and two tier values, the illustrative combination ceiling is:

```text
3 × 3 × 2 = 18 combinations
```

This figure is only a model for the listed dimensions. Actual total series also depend on instances, other tags, meters, and histograms created.

### 3.2. High Cardinality Is for Detail, Not a Loophole Around All Limits

Order IDs can differ on nearly every execution. Putting them into metric tags lets series count grow with order volume.

In the example, simulated IDs `demo-101` and `demo-102` are placed in the high-cardinality group to distinguish them from bounded grouping tags.

In Spring Boot's usual integration, low cardinality is used for metrics and traces, while high cardinality is reserved for traces. A custom handler can read both; it must follow its own data design. Thus, seeing this lesson's console print a `HIGH` line does not mean a metrics backend has been configured to accept that tag.

High cardinality still carries storage, search, and data-governance costs. Only include identifiers when there is a clear investigative purpose; do not add passwords, tokens, or entire request payloads. That is a metadata-content decision, not an automatic safety feature of the convention.

## 4. Which Convention Is Selected?

Three roles must be distinguished:

1. **Default convention:** fallback convention provided by the instrumentation.
2. **Global convention:** convention registered on the registry, with a context support condition.
3. **Explicit custom convention:** convention passed directly to observation creation via the corresponding API.

With the overload taking custom, default, context supplier, and registry, the selection order illustrated is:

```text
Is a custom convention passed directly?
    yes → use custom matching the instrumentation contract
    no
       ↓
Is there a global convention supporting the context?
    yes → use global selected by the registry
    no
       ↓
Use the instrumentation's default
```

This is **selecting one convention**, not running default and layering all global tags and then layering custom tags on top. If a custom convention wants to keep tags from a default convention class, it must extend/call that logic intentionally.

The custom → matching global → default order is described in [Micrometer Observation — Components](https://docs.micrometer.io/micrometer/reference/1.13/observation/components.html). The hands-on section directly verifies this mechanism on Micrometer 1.13.0.

### 4.1. A Name Passed to a Simple Factory Can Be Overridden by a Matching Global Convention

Do not assume that:

```java
Observation.createNotStarted("literal.checkout", () -> context, registry);
```

always keeps the literal name `literal.checkout` regardless of registry configuration.

In this lesson's run, the registry already has a matching `GlobalObservationConvention<CheckoutContext>`. The factory taking a direct name still selects the global convention for that context; the result is the name `regional.checkout` and the tags supplied by the global convention.

Therefore, distinguish **passing a name as a default** from **passing an explicit custom convention**. Check the actual overload and configuration rather than inferring from seeing a name string at the observation creation site.

### 4.2. Avoid Multiple Global Conventions Competing for One Context

If multiple global conventions all support the same context, do not expect their tag sets to merge automatically. How the registry/framework selects and orders candidates must be verified in the specific configuration.

A more controllable design is keeping support boundaries clear or explicitly supplying the convention at the instrumentation point. Do not rely on incidental bean discovery order as an untested metric-naming contract.

### 4.3. A Plain Bean Does Not Prove Instrumentation Uses It

Declaring a class implementing `ObservationConvention` or a bean of that type is not enough to claim every observation in Spring Boot will change names.

You must know how the convention is wired:

- Passed directly to the observation creation API.
- Registered as a global convention.
- Provided as the exact extension type that HTTP/database/library instrumentation looks for.

For example, a business `CheckoutConvention` does not automatically replace the HTTP server convention merely because both classes implement a common base interface.

## 5. Keep Business Code Independent of Observation Conventions

In the hands-on program, the business section only updates `context.result` and may throw an exception. Conventions take care of:

- Choosing the stable name.
- Normalizing channel for metadata.
- Reading result from the context.
- Classifying the order ID as high cardinality.
- Adding deployment region or service tier tags.

Convention methods should be lightweight and safe to call repeatedly without side effects. Avoid network calls, database queries, generating a new UUID, or mutating business state inside `getLowCardinalityKeyValues`.

A convention can be a shared object across many calls. Do not hold `currentOrderId` or the most recent request's result in a convention field. Per-execution data lives in the context; immutable configuration, such as a deployment region name, can live on the convention.

Changing how you observe should not cause the order-creation method to be invoked an extra time, nor alter the business outcome. An observation may be inactive due to configuration, yet business logic must still have an independent execution path.

## 6. Runnable Java Example

### 6.1. Preparation

JDK 17 or newer and two JARs at the same version are required:

```text
io.micrometer:micrometer-observation:1.13.0
io.micrometer:micrometer-commons:1.13.0
```

Place them in a `lib/` directory next to the Java file. You can obtain them from Maven Central or your build tool's cache. This version is pinned for the standalone example; it is not a requirement to override Spring Boot's dependency management.

```text
convention-demo/
├── ObservationConventionDemo.java
└── lib/
    ├── micrometer-observation-1.13.0.jar
    └── micrometer-commons-1.13.0.jar
```

### 6.2. Complete Source Code

Save the file `ObservationConventionDemo.java`:

```java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.GlobalObservationConvention;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationConvention;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import java.util.Map;
import java.util.TreeMap;

public class ObservationConventionDemo {
    static final class CheckoutContext extends Observation.Context {
        final String channel;
        final String orderId;
        String result = "pending";

        CheckoutContext(String channel, String orderId) {
            this.channel = channel;
            this.orderId = orderId;
        }
    }

    static class DefaultCheckoutConvention
            implements ObservationConvention<CheckoutContext> {
        @Override
        public boolean supportsContext(Observation.Context context) {
            return context instanceof CheckoutContext;
        }

        @Override
        public String getName() {
            return "checkout.process";
        }

        @Override
        public String getContextualName(CheckoutContext context) {
            return "process checkout";
        }

        @Override
        public KeyValues getLowCardinalityKeyValues(CheckoutContext context) {
            String channel = switch (context.channel == null ? "" : context.channel) {
                case "web" -> "web";
                case "store" -> "store";
                default -> "other";
            };
            return KeyValues.of("channel", channel, "result", context.result);
        }

        @Override
        public KeyValues getHighCardinalityKeyValues(CheckoutContext context) {
            return KeyValues.of("order.id", context.orderId);
        }
    }

    static final class RegionalCheckoutConvention
            extends DefaultCheckoutConvention
            implements GlobalObservationConvention<CheckoutContext> {
        @Override
        public String getName() {
            return "regional.checkout";
        }

        @Override
        public KeyValues getLowCardinalityKeyValues(CheckoutContext context) {
            return super.getLowCardinalityKeyValues(context)
                    .and("deployment.region", "lab");
        }
    }

    static final class ShopCheckoutConvention extends DefaultCheckoutConvention {
        @Override
        public String getName() {
            return "shop.checkout";
        }

        @Override
        public String getContextualName(CheckoutContext context) {
            return "checkout via shop";
        }

        @Override
        public KeyValues getLowCardinalityKeyValues(CheckoutContext context) {
            return super.getLowCardinalityKeyValues(context)
                    .and("tier", "standard");
        }
    }

    static final class ConsoleHandler
            implements ObservationHandler<CheckoutContext> {
        @Override
        public boolean supportsContext(Observation.Context context) {
            return context instanceof CheckoutContext;
        }

        @Override
        public void onStart(CheckoutContext context) {
            System.out.println("START name=" + context.getName()
                    + " low=" + tags(context.getLowCardinalityKeyValues()));
        }

        @Override
        public void onStop(CheckoutContext context) {
            String error = context.getError() == null
                    ? "none" : context.getError().getClass().getSimpleName();
            System.out.println("STOP name=" + context.getName()
                    + " contextual=" + context.getContextualName());
            System.out.println("LOW " + tags(context.getLowCardinalityKeyValues()));
            System.out.println("HIGH " + tags(context.getHighCardinalityKeyValues()));
            System.out.println("ERROR " + error);
        }
    }

    static String tags(KeyValues keyValues) {
        Map<String, String> sorted = new TreeMap<>();
        for (KeyValue keyValue : keyValues) {
            sorted.put(keyValue.getKey(), keyValue.getValue());
        }
        return sorted.toString();
    }

    static void run(ObservationRegistry registry, String label,
                    ObservationConvention<CheckoutContext> custom,
                    String channel, String orderId, boolean fail) {
        System.out.println("CASE " + label);
        CheckoutContext context = new CheckoutContext(channel, orderId);
        Observation observation = Observation.createNotStarted(
                custom, new DefaultCheckoutConvention(), () -> context, registry);
        try {
            observation.observe((Runnable) () -> {
                context.result = fail ? "failure" : "success";
                if (fail) {
                    throw new IllegalStateException("payment refused");
                }
            });
        }
        catch (IllegalStateException ex) {
            System.out.println("CAUGHT " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        ObservationRegistry registry = ObservationRegistry.create();
        registry.observationConfig().observationHandler(new ConsoleHandler());

        run(registry, "default", null, "web", "demo-101", false);

        registry.observationConfig()
                .observationConvention(new RegionalCheckoutConvention());
        run(registry, "global", null, "store", "demo-102", false);

        run(registry, "explicit", new ShopCheckoutConvention(),
                "unexpected-input", "demo-103", true);

        System.out.println("CASE direct-name");
        CheckoutContext direct = new CheckoutContext("web", "demo-104");
        Observation.createNotStarted("literal.checkout", () -> direct, registry)
                .observe((Runnable) () -> direct.result = "success");
    }
}
```

The IDs `demo-101` through `demo-104` are simulated identifiers. `ConsoleHandler` only displays metadata in the context; it does not configure metrics or trace export.

The `tags` helper sorts keys with a `TreeMap` so stdout has an easily comparable order; this is the lesson's display format, not a specific backend's format.

### 6.3. Compiling and Running

In PowerShell:

```powershell
javac --release 17 -cp "lib/*" ObservationConventionDemo.java
java -cp ".;lib/*" ObservationConventionDemo
```

On Linux/macOS, use `:` between classpath entries:

```bash
javac --release 17 -cp "lib/*" ObservationConventionDemo.java
java -cp ".:lib/*" ObservationConventionDemo
```

The program was compiled with `--release 17` and run on OpenJDK 24.0.2 with Micrometer 1.13.0. Captured stdout:

```text
CASE default
START name=checkout.process low={channel=web, result=pending}
STOP name=checkout.process contextual=process checkout
LOW {channel=web, result=success}
HIGH {order.id=demo-101}
ERROR none
CASE global
START name=regional.checkout low={channel=store, deployment.region=lab, result=pending}
STOP name=regional.checkout contextual=process checkout
LOW {channel=store, deployment.region=lab, result=success}
HIGH {order.id=demo-102}
ERROR none
CASE explicit
START name=shop.checkout low={channel=other, result=pending, tier=standard}
STOP name=shop.checkout contextual=checkout via shop
LOW {channel=other, result=failure, tier=standard}
HIGH {order.id=demo-103}
ERROR IllegalStateException
CAUGHT payment refused
CASE direct-name
START name=regional.checkout low={channel=web, deployment.region=lab, result=pending}
STOP name=regional.checkout contextual=process checkout
LOW {channel=web, deployment.region=lab, result=success}
HIGH {order.id=demo-104}
ERROR none
```

### 6.4. Comparing the Four Cases

| Case | Configuration at creation time | Result |
| --- | --- | --- |
| `default` | No custom passed, no global registered yet | `checkout.process`, tags from default |
| `global` | No custom passed, global supporting context registered | `regional.checkout`, with `deployment.region=lab` |
| `explicit` | `ShopCheckoutConvention` passed even though global exists | `shop.checkout`, with `tier=standard` |
| `direct-name` | Factory receiving name `literal.checkout` and checkout context | Matching global still produces `regional.checkout` |

In the `explicit` case, there is no `deployment.region` tag. This proves global metadata does not automatically stack onto custom. `ShopCheckoutConvention` calls `super` on `DefaultCheckoutConvention`, not `RegionalCheckoutConvention`.

The input `unexpected-input` is normalized to `channel=other`. The tag `result=failure` appears when the work fails; the error still propagates out of `observe` and is caught by the demo, producing `CAUGHT payment refused`.

The `ERROR none` line in stdout is simply how the example's handler displays that the context has no error. It is not a mandatory Micrometer error tag.

### 6.5. Why Does START See pending While STOP Sees success/failure?

Initially, each context has `result=pending`. Inside the business lambda, the program updates it to the final outcome.

Along the verified Micrometer 1.13.0 execution path, tags from the convention are refreshed from the context at relevant lifecycle points; the example handler sees the final outcome in `onStop`.

That does not mean every output created at the start of work will retroactively change tags later. One handler may lock in data at start time, while another reads at stop time. For example, an in-flight task measurement created on start should not be assumed to carry the completed measurement's tag set.

Therefore:

- Known input data such as channel must be present before starting.
- Data known only at the end such as outcome must be set at the right time.
- Do not use the final outcome to compute an observation name that changes mid-run.
- When customizing an existing instrumentation, check which milestone its handlers read metadata at.

Do not call a convention's getters directly and treat that as integration proof: verify metadata on the observation at the point handlers actually consume it.

## 7. Adding Tags and Replacing Tags Are Two Different Changes

### 7.1. To Keep Defaults, Call super Intentionally

In the program's custom convention:

```java
@Override
public KeyValues getLowCardinalityKeyValues(CheckoutContext context) {
    return super.getLowCardinalityKeyValues(context)
            .and("tier", "standard");
}
```

The result keeps `channel` and `result` from the default class and appends `tier`.

If replaced with:

```java
@Override
public KeyValues getLowCardinalityKeyValues(CheckoutContext context) {
    return KeyValues.of("tier", "standard");
}
```

the method no longer returns `channel` and `result` from the default class. That is a decision to replace the low-cardinality tag set, not merely another syntax to add one tag.

Similarly, overriding `getHighCardinalityKeyValues` and returning a new set can drop the superclass's detailed fields. If you only override the low method as in the main example, the inherited high method still keeps `order.id`.

When using `KeyValues.and(...)`, use the returned value, such as returning the chained call directly as shown above. Do not call `values.and(...)`, discard the result, and assume the `values` variable was mutated as desired.

### 7.2. Preserve the Existing Instrumentation's Tag Contract

A default HTTP convention may already provide classification dimensions that dashboards and alerts depend on. If you replace the entire tag set just to add `application.area`, you can accidentally drop those essential dimensions.

Before changing a convention:

1. Identify the names and tags currently forming the system's usage contract.
2. Distinguish what you want to add, what you want to change, and what you truly want to remove.
3. Keep the set of low-cardinality keys consistent across executions of the same type of work.
4. Test success, error, and unexpected input data.

If a value is missing, pick an explicit policy: a bounded value such as `unknown`, or omitting the detail field when the contract allows. Do not return arbitrary `null`s for keys/values and wait for the backend to decide.

### 7.3. Metadata Shared Across All Conventions Needs a Separate Injection Point

If the deployment region must appear on every matching observation whether the caller picks custom or global, adding it only inside a global convention may not suffice: an explicit custom convention can take precedence.

An `ObservationFilter` is an option for adding metadata during the context-filtering phase before ending callbacks. Configuration snippet for an existing registry:

```java
registry.observationConfig().observationFilter(context ->
        context.addLowCardinalityKeyValue(
                KeyValue.of("deployment.environment", "lab")));
```

This is an excerpt requiring `import io.micrometer.common.KeyValue`. A filter is a separate mechanism and does not alter convention selection order.

Because this filter applies at the stop phase, do not assume handlers in `onStart` already see the newly added tag. If metadata must be present at start time, design the corresponding metadata source rather than only adding a late filter.

Also do not confuse this with `MeterFilter`: that operates at the Micrometer Metrics layer; it is not a shared naming/tagging mechanism for both observations and tracing.

## 8. Bringing Conventions into Spring Boot Actuator

### 8.1. Use the Right Registry and the Right Extension Point

In a Spring Boot 3.3 application, use the injected `ObservationRegistry` to retain the handlers and customizations configured by Boot. If you create a standalone registry in a service, beans or conventions on the managed registry do not automatically appear on the new registry.

Boot registers `GlobalObservationConvention` beans onto its registry. If an explicit convention is needed for custom business logic, instrumentation code must accept and pass that convention into the observation creation API, like the `run` method in the program.

Boot's rules for bean registration, the registry, and low/high tags are described in [Spring Boot 3.3 — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

"The bean exists" is only part of verification. You must also verify the context type, where the convention is used, support predicates, and actual outputs.

### 8.2. Example: Adding a Tag for Spring MVC While Keeping Defaults

For the HTTP server in Spring MVC, there is a dedicated extension point `ServerRequestObservationConvention` in the servlet package `org.springframework.http.server.observation`.

The configuration snippet below is for a Spring Boot 3.3 application with Spring MVC and Actuator. It adds a fixed tag `application.area=shop` and keeps the default low-cardinality tag set:

```java
import io.micrometer.common.KeyValues;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.server.observation.DefaultServerRequestObservationConvention;
import org.springframework.http.server.observation.ServerRequestObservationContext;
import org.springframework.http.server.observation.ServerRequestObservationConvention;

@Configuration(proxyBeanMethods = false)
public class HttpObservationConfig {
    @Bean
    ServerRequestObservationConvention serverRequestObservationConvention() {
        return new DefaultServerRequestObservationConvention() {
            @Override
            public KeyValues getLowCardinalityKeyValues(
                    ServerRequestObservationContext context) {
                return super.getLowCardinalityKeyValues(context)
                        .and("application.area", "shop");
            }
        };
    }
}
```

This is a configuration file to place in a package scanned by the application, not a standalone console program. `super.getLowCardinalityKeyValues(context)` is what preserves the default contract; removing it to return only the new tag is a different change.

If you only want to rename the HTTP server observation using Boot's built-in support:

```yaml
management:
  observations:
    http:
      server:
        requests:
          name: shop.http.requests
```

Do not rename in multiple places simultaneously and guess the outcome. When custom or global conventions are also present, verify the final name actually used.

Per Boot documentation, MVC and WebFlux have corresponding HTTP conventions in **two different packages**. For WebFlux, the package is `org.springframework.http.server.reactive.observation`; do not copy the servlet import verbatim into a reactive application.

Default HTTP names, rename properties, and extension points to add/replace tags are documented in [Spring Boot 3.3 — Metrics, Spring MVC and WebFlux](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.spring-mvc).

### 8.3. Common Tags Can Use Simpler Configuration

If the requirement is simply to add a few bounded environment tags to Boot's observations, you can use global property configuration:

```yaml
management:
  observations:
    key-values:
      deployment.environment: lab
      deployment.region: local
```

There is no need to write a new convention just to repeat configuration values across every kind of work. Use a convention when you need rules tied to a context or a specific naming/tagging contract.

Conversely, do not put per-request order IDs into global key-value configuration: per-execution values belong in the context and must be classified according to appropriate cardinality.

## 9. How to Verify a Convention Change

Verify across three layers:

| Layer | Question to answer |
| --- | --- |
| Convention methods | Given a sample context, are the returned name and key–value pairs correct? |
| Actual observation | Which convention is selected? What data do handlers see when consuming it? |
| Integrated output | Do actual timers/spans have the expected name, tags, and counts? |

This lesson's console program verifies the actual observation layer via a handler. It does not yet prove that timers or spans exist in a running Spring application.

For a real deployment change, also check:

- Context has the right type and registry is the configured object.
- When no custom is passed, the matching global and fallback default yield the right results.
- When custom is present, its metadata does not accidentally drop required tags.
- Unknown/`null` inputs have a clear normalization policy.
- Final outcomes on both success and error paths are attached at the appropriate milestone.
- No extra names or low-cardinality tags are generated per identifier.
- Queries/dashboards/alerts are updated if the name/tag contract changes.

Micrometer provides `micrometer-observation-test` and `TestObservationRegistry` to assert observations and metadata in automated tests; see [Micrometer Observation — Testing](https://docs.micrometer.io/micrometer/reference/1.13/observation/testing.html).

Do not test only `new MyConvention().getName()`: a method returning the right string still helps nothing if the convention is never selected by instrumentation.

## 10. Common Mistakes

| Symptom | Cause to check | Fix direction |
| --- | --- | --- |
| Convention class exists yet name does not change | Not wired into registry or instrumentation | Determine how the convention is registered/passed |
| Global is not used | Context mismatch or explicit custom present | Check context type and precedence order |
| Name passed to factory changes | Matching global was selected | Check configuration rather than only looking at the factory string |
| Adding one tag drops default tags | Override returns a new set without calling super | Distinguish adding from replacing |
| Console shows HIGH so assumed metrics has it too | Console handler reads both groups | Check actual metrics/tracing handlers |
| Series count grows with order count | Identifier used in name/low tag | Keep name stable, reclassify detailed data |
| Same work has inconsistent key sets | Getters have branches arbitrarily omitting keys | Define a schema and bounded missing values |
| START lacks final outcome | Outcome only exists after business logic | Check the milestone where handlers read metadata |
| Getters cause side effects multiple times | Convention used to run business logic | Compute metadata solely from context/config |
| MVC does not pick up expected convention | Wrong extension type or reactive package mix-up | Choose the exact convention for the active instrumentation |

## 11. Self-Check Exercises

**Scenario 1:** The registry has a global convention supporting checkout. A call passes `ShopCheckoutConvention` explicitly. What will the name and deployment region tag be?

In the program, the name is `shop.checkout`. There is no global `deployment.region`, because custom is selected and only inherits tags from the default class. To have the region tag on both paths, design an appropriate injection point rather than expecting conventions to merge automatically.

**Scenario 2:** Change `ShopCheckoutConvention.getLowCardinalityKeyValues` to return only `KeyValues.of("tier", "standard")`. Which tags are lost?

The `channel` and `result` tags produced by the superclass's low method are no longer returned. The high tag `order.id` still comes from the inherited high method if everything else stays the same.

**Scenario 3:** Create one thousand contexts with different order IDs but the same channel and result. Does low metadata need one thousand distinct values?

Not under this lesson's design. Order ID belongs in the high group; the low set only reflects the defined bounded dimensions. If you move order ID into low, that design has changed even though the getter name still contains "LowCardinality".

**Scenario 4:** The program renames via a convention, yet dashboards still use the old name. Can you conclude data is not being recorded?

Not yet. Check the actual name in the output and the queries being used. Renaming/retagging is a change to the observability data contract and must be verified together with consumers.

**Practice with the source code:**

- Replace a channel input with `null` and verify it is grouped as `other`.
- Remove global registration to compare the result of the factory receiving a name directly.
- Keep global registered while passing custom, and verify the difference between the two tag sets.
- Add a field to `CheckoutContext` without mapping it in the convention; verify it does not automatically become a tag.
- Verify the same convention on both success and error paths.

A good convention provides stable names, a clear tag schema, and testable normalization. It keeps observability data consistent while lifecycle and business outcomes remain managed in the proper place.
