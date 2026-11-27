# AspectJ Weaver in Annotation Observability

> **Chapter:** Annotation observability  
> **Lesson:** AspectJ weaver  
> **Module:** SPRING_BOOT_OBSERVABILITY — Setting up observability for Spring Boot with Micrometer Observation, metrics, logs, and distributed tracing. Learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

## 1. What Problem Does AspectJ Weaver Solve?

In a Spring Boot application, many observable activities are repetitive: measuring method duration, creating observations on service calls, recording exceptions, or adding metadata to an operation. If every method manually wrote timer start/stop code, exception handling, and context restoration, business code would be mixed with instrumentation.

Aspect-oriented programming (AOP) separates cross-cutting behaviors into **aspects**. AspectJ is an AOP ecosystem for Java; the **weaver** is the component that combines aspects with class bytecode so advice behavior executes at matching join points.

In annotation observability, an annotation such as `@Observed` or `@Timed` marks a method to be instrumented. An aspect reads the annotation and wraps the method call to create `Observation`, `Timer`, or tracing behavior. Aspects can be applied via Spring AOP proxies or AspectJ weaving, depending on the integration approach.

Crucial point: **AspectJ weaver is not a metrics registry, tracing exporter, or `ObservationRegistry`.** It is a tool that applies aspects to bytecode. Creating and exporting telemetry still requires the corresponding instrumentation, handlers, registry/SDK, and exporter.

~~~mermaid
flowchart TD
  A["Annotated method"] --> B["Aspect / advice"]
  B --> C{"How aspect is applied"}
  C --> D["Spring AOP proxy"]
  C --> E["AspectJ weaving"]
  D --> F["Method invocation wrapped"]
  E --> F
  F --> G["Micrometer Observation / Timer"]
  G --> H["Metrics handler"]
  G --> I["Tracing handler"]
  H --> J["MeterRegistry / exporter"]
  I --> K["Tracer / span exporter"]
~~~

## 2. Aspect, Advice, Pointcut, and Join Point

An aspect typically involves these concepts:

| Concept | Meaning | Example |
| --- | --- | --- |
| Aspect | Module containing cross-cutting behavior | Measuring method duration |
| Join point | Execution point where advice can be applied | Method execution |
| Pointcut | Expression selecting join points | Methods in a service package |
| Advice | Behavior running at a join point | Around advice starting/stopping a timer |
| Weaver | Component combining aspects with target code | AspectJ compiler or LTW weaver |
| Inter-type declaration | Adding members to a type via AspectJ | Declaring additional methods/fields |

An around advice can run before and after a method while also handling exceptions:

~~~java
@Around("execution(* com.example.orders..*(..))")
public Object observe(ProceedingJoinPoint joinPoint) throws Throwable {
    long started = System.nanoTime();
    try {
        return joinPoint.proceed();
    } finally {
        long elapsed = System.nanoTime() - started;
        recordDuration(joinPoint.getSignature(), elapsed);
    }
}
~~~

This snippet illustrates the concept. It is not a complete Micrometer configuration and should not be used instead of built-in instrumentation. Specifically with reactive return types, returning from the method often only returns a `Mono`/`Flux`; the around advice above would only measure publisher creation time, not post-subscription execution time.

## 3. How Does a Spring AOP Proxy Differ from AspectJ Weaving?

Spring AOP typically uses proxies to intercept method calls passing through the proxy. AspectJ weaving transforms bytecode so advice is applied at join points supported by AspectJ, without requiring every call to pass through a Spring proxy.

| Characteristic | Spring AOP Proxy | AspectJ Weaving |
| --- | --- | --- |
| Mechanism | JDK dynamic proxy or CGLIB proxy | Bytecode transformation |
| Join points | Primarily method execution on Spring beans | Broader, including method/constructor execution, calls, field access, etc., per AspectJ |
| Self-invocation | Calls to `this.method()` typically bypass the proxy | Can be woven if the pointcut matches |
| Non-Spring-managed objects | Not proxied automatically | Can be woven if the class is in weaving scope |
| Configuration | Spring AOP auto-proxy infrastructure | Compile-time, post-compile, or load-time weaving |
| Debugging | Inspect proxy and bean wiring | Inspect woven bytecode, weaver, and classloader |

Spring AOP is sufficient for many annotation observability use cases in Spring Boot. Do not add AspectJ weaving just because code has `@Observed`. First verify that the required aspect is registered by Spring and method calls go through the proxy.

AspectJ weaving is appropriate when you need join points not covered by proxies, such as self-invocation or certain constructor/field join points. Setup is more complex and requires careful consideration of classloaders, build pipelines, startup, and debuggability.

## 4. Three Modes of AspectJ Weaving

AspectJ supports three common weaving approaches:

### 4.1. Compile-time weaving (CTW)

The AspectJ compiler `ajc` compiles sources and aspects into woven bytecode. Aspects are applied during the build.

~~~text
Java source + Aspect source
          |
          v
     AspectJ compiler
          |
          v
  Woven .class files
          |
          v
       Application
~~~

Advantages:
- No runtime weaver agent needed for already-woven classes.
- Pointcut/weaving errors can be caught at build time.
- Bytecode is prepared before deployment.

Limitations:
- The build requires configuring the AspectJ compiler/plugin.
- Must properly handle source sets, generated classes, and dependencies.
- Changing an aspect may require recompiling affected classes.

### 4.2. Post-compile or binary weaving

Java classes are compiled first, and then the AspectJ compiler weaves aspects into the produced `.class` files or JARs.

~~~text
Java compiler -> .class / JAR
                       |
                       v
              AspectJ post-compile
                       |
                       v
                 Woven bytecode
~~~

This is useful when you do not want to swap the compiler for all sources. However, build ordering, original artifacts, and woven artifacts must be clearly managed.

### 4.3. Load-time weaving (LTW)

LTW weaves classes when the JVM classloader loads them. It typically requires an AspectJ weaver agent and configuration of aspects/target classes.

~~~text
JVM startup
   |
   +--> -javaagent:aspectjweaver.jar
   |
ClassLoader loads class
   |
AspectJ weaver transforms bytecode
   |
Woven class is defined
~~~

The advantage is applying weaving at runtime without pre-building woven JARs. The limitation is that JVM startup, classloaders, weaving scope, and runtime environment must be configured accurately.

Do not enable multiple weaving mechanisms simultaneously for the same classes without a clear reason and thorough verification. Doing so can cause double transformations or make advice origins hard to trace.

## 5. AspectJ Weaver Does Not Automatically Enable Micrometer Annotations

Micrometer Observation provides an API for describing operations. Micrometer also provides supporting annotations and aspects in certain modules:

- `@Observed` marks a method to be observed when the corresponding aspect is configured.
- `@Timed` marks a method to be timed when `TimedAspect` is registered.
- `ObservationRegistry` manages lifecycle and handlers.
- `MeterRegistry` stores/retrieves meters.
- Tracing bridges/handlers can create spans from an `Observation`.

An annotation is merely metadata until a component processes it. Adding the `aspectjweaver` dependency does not automatically create an `Observation` or `Timer`.

`@Observed` example:

~~~java
@Service
public class OrderService {

    @Observed(name = "orders.create", contextualName = "create-order")
    public Order create(CreateOrderCommand command) {
        return doCreate(command);
    }
}
~~~

For the annotation to be processed, you must register `ObservedAspect` per the Micrometer/Spring Boot version guide and provide an `ObservationRegistry`. In typical setups, the aspect invocation mechanism can be a Spring AOP proxy; do not infer that AspectJ LTW is mandatory just from the presence of the annotation.

`@Timed` example:

~~~java
@Service
public class CatalogService {

    @Timed(value = "catalog.refresh", histogram = true)
    public void refresh() {
        reloadCatalog();
    }
}
~~~

`@Timed` requires `TimedAspect` to be configured in the application. It measures the method according to the aspect's semantics; for reactive methods, verify whether the aspect/module supports tracking the publisher lifecycle. Do not assume a method returning `Mono` is measured until the `Mono` completes.

## 6. Configuring Annotation Aspects in Spring Boot

Conceptual configuration example:

~~~java
@Configuration
public class ObservabilityAspectConfiguration {

    @Bean
    ObservedAspect observedAspect(ObservationRegistry registry) {
        return new ObservedAspect(registry);
    }

    @Bean
    TimedAspect timedAspect(MeterRegistry registry) {
        return new TimedAspect(registry);
    }
}
~~~

Classes/packages and auto-configuration conditions must match the project's Micrometer/Spring Boot version. Do not register a second equivalent aspect if Boot or a starter already auto-configures it; duplicate aspects can produce duplicate Observations/Timers.

Dependencies normally require the appropriate Micrometer modules and Spring AOP infrastructure. AspectJ runtime/weaver dependencies are only needed when your aspect implementation or weaving approach actually requires them. Check dependency management/BOM instead of pinning incompatible versions.

### 6.1. Verifying the Aspect Is Registered

- Check whether the Spring application context contains the expected `ObservedAspect`/`TimedAspect` bean.
- Check startup logs and the condition evaluation report if auto-configuration is conditional.
- Invoke the method through a Spring-managed bean.
- Check whether the meter/observation appears in the registry.
- Verify the aspect runs exactly once.
- Verify traces/spans are created if a tracing handler is active.

Do not merely check that the annotation exists via reflection; that does not prove advice has been applied.

## 7. Configuring Load-Time Weaving with AspectJ

If a use case truly requires AspectJ LTW, the JVM must load the weaver agent before application startup.

Example:

~~~bash
java -javaagent:/opt/aspectj/aspectjweaver.jar \
     -jar target/application.jar
~~~

The JAR must be an AspectJ weaver version compatible with the Java runtime and the application's AspectJ artifacts. Replace the example path with the actual artifact location.

A minimal `aop.xml` configuration can be placed at `META-INF/aop.xml` on the classpath:

~~~xml
<!DOCTYPE aspectj PUBLIC
  "-//AspectJ//DTD//EN"
  "https://www.eclipse.org/aspectj/dtd/aspectj.dtd">
<aspectj>
  <aspects>
    <aspect name="com.example.observability.ExecutionAspect"/>
  </aspects>
  <weaver>
    <include within="com.example.orders..*"/>
  </weaver>
</aspectj>
~~~

This is an illustrative configuration skeleton. The aspect must be an AspectJ-compatible aspect recognized by the compiler/runtime; the include scope should be narrowed to avoid weaving too many libraries. A Spring `@Aspect` can be applied via Spring AOP proxies without placing it in LTW configuration.

If the application uses multiple classloaders or runs in a container/application server, check where `aop.xml` is discovered and which classloader defines which classes.

## 8. Compile-Time Weaving in the Build

Compile-time weaving requires configuring the AspectJ compiler or an appropriate build plugin. A Maven/Gradle project must specify:
- Source and target compatibility.
- AspectJ compiler version.
- Aspect source path.
- Compile/test source sets.
- Corresponding `aspectjrt`/`aspectjweaver` dependencies.
- Whether generated classes need weaving.
- Whether packaging contains the woven bytecode.

General pipeline:

~~~mermaid
flowchart TD
  A["Java source + aspects"] --> B["Compile"]
  B --> C["AspectJ weaving"]
  C --> D["Run unit/integration tests"]
  D --> E["Package woven artifact"]
  E --> F["Deploy"]
~~~

Do not copy plugin configurations from another project without checking version and compiler compatibility. After the build, verify that the artifact is actually woven using compiler logs or a bytecode inspection tool. Seeing the plugin in the build file alone does not prove classes were woven.

## 9. Pointcut Scope and Performance

An overly broad pointcut can weave many unrelated classes, increasing build/startup time, complicating debugging, and applying advice in unintended places.

Best practices:
- Restrict to specific packages/domains.
- Exclude framework, generated code, and third-party libraries unless needed.
- Only instrument operationally meaningful methods.
- Avoid pointcuts matching every `Object` method or getter/setter.
- Monitor the number of woven classes and startup time.
- Test behavior when proxies and weaving coexist.

Do not use a catch-all pointcut to create a span for every internal method call. This creates overly noisy telemetry, increases overhead, and makes traces hard to read.

## 10. Self-Invocation and Proxy Limitations

With a Spring AOP proxy, method A calling method B via `this` usually does not pass through the proxy a second time:

~~~java
@Service
public class ReportService {

    public void generate() {
        writeReport(); // self-invocation, typically bypasses Spring proxy
    }

    @Observed(name = "report.write")
    public void writeReport() {
        // Write report.
    }
}
~~~

If the `@Observed` aspect is applied via a Spring proxy, the internal `writeReport()` call may not be intercepted. Calling `generate()` from another bean through the proxy does not automatically route `this.writeReport()` through the proxy.

How to handle:
- Move the instrumented method to another Spring bean.
- Call through a properly injected collaborator/proxy.
- If self-invocation join points are genuinely required, evaluate AspectJ weaving.
- Or create a manual `Observation` around an operation with an explicit lifecycle.

Do not overuse self-injection or fetching beans from `ApplicationContext` solely to work around proxy limitations; collaborator design is usually clearer and easier to test.

## 11. Final, Private, Static, and Constructor Join Points

Spring AOP proxies have limitations based on proxy and method types. For example:
- JDK dynamic proxies only expose interface methods.
- CGLIB subclass proxies cannot override `final` methods/classes.
- `private` methods cannot be intercepted by standard proxy mechanisms.
- `static` methods do not go through an instance proxy.
- Constructor execution is not a join point of Spring AOP proxies.

AspectJ weaving supports a broader set of join points, including constructor execution and field access, depending on the pointcut/weaving model. However, not every join point is suitable for observability. Instrumenting constructors or field access can generate excessive events and obscure lifecycles.

Choose the mechanism according to actual requirements rather than switching the whole application to LTW just to intercept one private method.

## 12. Annotation Observability and Reactive Lifecycle

Traditional annotation aspects typically wrap synchronous method calls. With methods returning `Mono`/`Flux`, the method may finish right after creating the publisher; the actual work happens upon subscription.

~~~java
@Observed(name = "inventory.lookup")
public Mono<Stock> findStock(String sku) {
    return webClient.get()
            .uri("/stock/{sku}", sku)
            .retrieve()
            .bodyToMono(Stock.class);
}
~~~

If the aspect only measures method invocation time, the observation may end before the HTTP exchange completes. Use an integration that supports reactive context/lifecycle or place the `Observation` inside the reactive pipeline to start/stop with subscription and terminal signals.

Do not use blocking to force a reactive method to be synchronous just to make an annotation timer work. Doing so can cause thread starvation and alter semantics.

## 13. Avoiding Duplicate Instrumentation

Duplicate spans/metrics can occur when the same method is instrumented by:
- Spring AOP `@Observed` aspect.
- AspectJ woven advice.
- OTel Java Agent.
- Built-in Spring Web/JDBC instrumentation.
- Manual custom `Observation`.
- Another `@Timed` aspect measuring the same operation.

Before enabling multiple mechanisms, assign an owner to each boundary. For example, HTTP server spans owned by Spring instrumentation, database spans owned by the JDBC agent, and business operation spans owned by `@Observed`.

~~~text
HTTP server span
  orders.create observation
    JDBC query span
~~~

This structure is meaningful when each span represents a distinct operation. If `@Observed` and a woven aspect both create two spans named `orders.create` for the same method, the trace becomes duplicated.

Inspect waterfalls, parent-child relationships, span names, durations, and meter counts. Do not look only at total span counts.

## 14. Debugging AspectJ Weaving

When an aspect does not run or a class is not woven, investigate in order:

1. Was the aspect class compiled/packaged?
2. Does the pointcut match the target class/method?
3. Is the active mechanism a Spring proxy or AspectJ weaving?
4. If LTW, does the JVM have `-javaagent` pointing to the right JAR?
5. Is `aop.xml` on the classpath of the right classloader?
6. Does the weaver include the target package?
7. Was the target class loaded before the agent/config took effect?
8. Is another classloader/container instrumentation interfering?
9. Does the build artifact actually contain woven bytecode?
10. Were any weaver exceptions or warnings ignored?

The AspectJ weaver can output diagnostics depending on configuration. Only enable verbose/weaver debug in test environments or during active investigation; weaving logs can be very voluminous.

### 14.1. Symptoms and Causes

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| @Observed creates no observation | ObservedAspect not registered or call bypasses proxy | Bean config, proxy, registry |
| @Timed creates no meter | TimedAspect missing or aspect does not match | Bean registration and meter registry |
| Self-invocation does not run advice | Spring proxy bypass | Extract bean or use intentional weaving |
| LTW has no effect | Missing `-javaagent` or `aop.xml` not found | JVM command line, classpath |
| Only some packages are woven | Weaver include/exclude scope | `aop.xml` and diagnostics |
| Class not woven in container | Classloader or agent startup order | Runtime launch config |
| Advice runs twice | Both Spring proxy and woven aspect apply | Check ownership |
| Startup time spikes | Pointcut too broad or too many classes woven | Narrow scope, profiling |
| Reactive observation too short | Aspect measures publisher creation instead of subscription | Reactive-aware instrumentation |
| Final method not proxy-intercepted | CGLIB cannot override final method | Choose interface/different design or AspectJ |
| Aspect is in JAR but never runs | Having the class does not mean it is woven/registered | Check runtime mechanism |

## 15. Security and Operations When Using a Weaver

Weaving modifies the bytecode the JVM executes. In production, control artifacts, agents, and configuration:

- Pin the weaver version and manage dependencies via the build.
- Only use artifacts from trusted sources.
- Restrict woven classes/packages.
- Test the woven artifact in the exact same way it is deployed.
- Monitor startup time and runtime overhead.
- Record JVM arguments and weaving configuration in deployment manifests.
- Do not leave weaving debug enabled long-term if log volume is high.
- Be able to roll back by deploying the previous artifact/configuration.

An agent has permission to transform classes as the JVM loads them. Do not add agents casually to production without reviewing compatibility, startup ordering, and security posture.

## 16. Real-World Scenario: @Observed Not Running on Self-Invocation

**Context:** `order-service` has a `createOrder()` method that calls `validateInventory()` within the same bean. `validateInventory()` is annotated with `@Observed`, but no observation appears.

~~~java
@Service
public class OrderWorkflow {

    public Order createOrder(Command command) {
        validateInventory(command);
        return persist(command);
    }

    @Observed(name = "orders.validate-inventory")
    public void validateInventory(Command command) {
        // Validation and inventory checks.
    }

    private Order persist(Command command) {
        return new Order();
    }
}
~~~

### Step 1 — Identify the Aspect Mechanism

The team uses `ObservedAspect` via Spring AOP proxies. The call from the controller to `createOrder()` passes through the proxy, but `this.validateInventory()` executes inside the target object.

### Step 2 — Confirm the Proxy Limitation

Place a breakpoint/log in the aspect and call `validateInventory()` directly from another bean in a test. If calls through the proxy are instrumented while self-calls are not, the cause aligns with proxy semantics.

### Step 3 — Choose the Simple Fix

Extract validation into a separate bean:

~~~java
@Service
public class InventoryValidationService {

    @Observed(name = "orders.validate-inventory")
    public void validate(Command command) {
        // Validation and inventory checks.
    }
}
~~~

`OrderWorkflow` injects `InventoryValidationService` and calls the method through the Spring bean proxy. This clarifies business boundaries without needing to enable LTW.

### Step 4 — When Should AspectJ Weaving Actually Be Used?

If requirements genuinely need to intercept self-invocation or join points unsupported by Spring proxies, evaluate compile-time or load-time weaving. Test woven bytecode, classloaders, and startup, and ensure the same aspect does not run through both the proxy and the weaver.

### Step 5 — Verify Telemetry

Send an order creation request. The trace should contain one `orders.validate-inventory` observation in the right place without duplicates. Check meters, span duration, error behavior, and context propagation.

**Expected Outcome:** understand why the annotation did not run, choose the right interception mechanism, and keep traces clean.

## 17. Hands-On Exercises and Self-Check Questions

### Exercise A — Spring AOP Proxy

Create a service with an `@Observed` method and `ObservedAspect`. Call the method from another bean, then call it via self-invocation. Compare observation counts and explain the proxy boundary.

### Exercise B — AspectJ LTW in a Test Environment

Create a simple aspect and a target class. Configure the AspectJ weaver agent with an `aop.xml` scoped to a test package. Verify the advice runs on the target class and document the required JVM arguments.

### Exercise C — Comparing CTW and LTW

Weave the same aspect using compile-time and load-time weaving in two separate test profiles. Compare build artifacts, startup, diagnostics, and rollback approaches.

### Exercise D — @Observed and @Timed

Register the appropriate aspects, invoke a synchronous method, and verify `Observation`/`Timer`. Confirm that two aspects do not unintentionally measure the same operation.

### Exercise E — Reactive Lifecycle

Annotate a method returning a `Mono`. Compare method invocation duration with publisher completion duration. Use reactive-aware instrumentation to measure the true lifecycle.

### Exercise F — Duplicate Instrumentation

Enable Spring instrumentation, a custom aspect, and an agent for a test endpoint. Read the waterfall, identify duplicate spans, and assign ownership to each boundary.

### Self-Check Questions

1. What does the AspectJ weaver do to bytecode?
2. How do aspect, advice, pointcut, and join point differ?
3. How does a Spring AOP proxy differ mechanistically from AspectJ weaving?
4. How do compile-time, post-compile, and load-time weaving differ?
5. Does adding the `aspectjweaver` dependency automatically enable `@Observed`?
6. What are the roles of `ObservedAspect` and `TimedAspect`?
7. Why does self-invocation typically bypass a Spring AOP proxy?
8. How are `final`/`private`/`static` methods limited with proxies?
9. When is LTW a better fit than Spring AOP?
10. How do `aop.xml` and `-javaagent` participate in LTW?
11. Why can an overly broad pointcut impact startup/performance?
12. How can a method returning `Mono` be measured with the wrong lifecycle?
13. How do you avoid running both a proxy aspect and a woven aspect twice?
14. How do you verify that a class was actually woven?
15. When an annotation produces no telemetry, which layers need to be checked?

**Completion Criteria:** explain AspectJ weaver and the three weaving modes; distinguish Spring AOP proxies; configure aspects/annotations properly; understand self-invocation and method limitations; handle reactive lifecycles; inspect/debug weaving; avoid duplicate instrumentation and measure overhead.

## 18. Key Takeaways

- AspectJ weaver combines aspects with bytecode; it is not `ObservationRegistry`, `MeterRegistry`, or an exporter.
- Spring AOP proxies and AspectJ weaving are two different interception mechanisms.
- AspectJ supports compile-time, post-compile, and load-time weaving.
- Adding `aspectjweaver` does not automatically enable Micrometer `@Observed` or `@Timed`; the corresponding aspects and configuration must be present.
- `ObservedAspect` uses `ObservationRegistry`; `TimedAspect` uses `MeterRegistry` per the appropriate API/version.
- Self-invocation typically bypasses Spring proxies; extracting a collaborator is the simplest solution in many cases.
- AspectJ weaving can support broader join points, but requires controlling classloaders, builds, startup, and scope.
- Reactive methods require instrumentation following subscription/terminal lifecycles, not just publisher creation time.
- Avoid having the same operation instrumented simultaneously by Spring proxies, AspectJ weaver, Java agents, and manual custom `Observation`s.
- Verify with bean wiring, weaving diagnostics, actual meters/spans, and trace waterfalls.

## References

- [AspectJ — Development Environment and Tools](https://eclipse.dev/aspectj/doc/latest/devguide/)
- [AspectJ — Load-Time Weaving](https://eclipse.dev/aspectj/doc/latest/devguide/ltw.html)
- [Spring Framework — AOP](https://docs.spring.io/spring-framework/reference/core/aop.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Micrometer Observation Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot — AOP](https://docs.spring.io/spring-boot/reference/features/aop.html)
