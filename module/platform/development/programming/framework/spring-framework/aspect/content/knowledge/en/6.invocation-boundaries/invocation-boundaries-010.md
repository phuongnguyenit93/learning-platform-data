# Distinguishing the same target method across different call paths in Spring AOP

## 1. Core question: same method, why does advice behave differently?

A business method can return the right result even when advice does not run. When diagnosing Spring AOP, note **the receiver reference at the exact call site**: a Spring-injected proxy, `this` on the target, a separately retained raw target, or an instance created with `new`. Only then inspect the method/pointcut, proxy type, and lifecycle timing.

This lesson focuses on **comparing controlled call paths and investigating missing logs/transactions/auditing**. The demo uses the same `TaskService.run(String)` method with different input labels to distinguish output; the first three runs share the exact same Spring singleton target, while the `new` run contrasts a separate instance. When you need to isolate input influence completely, keep the same input string across each run.

## 2. Diagramming caller → receiver → proxy → target

```text
Other bean -> injected TaskService proxy -> advisor (if matched) -> target.run()
Main       -> context TaskService proxy  -> advisor (if matched) -> target.run()
Main       -> TaskService proxy.outer()  -> target.outer() -> this.run()
Main       -> new TaskService().run()    -> plain target.run()
```

The first two paths enter `run` through the proxy; the third passes through the proxy only at `outer`, while `this.run` does not loop back through it; the last path stays completely outside the Spring container. This separates **method body executed** from **advice executed**. Having a proxy alone is not enough: the bean must have a matching advisor, the method must be interceptable, and the call site must use the right reference. The table below brings lifecycle and proxy-type scenarios into the same comparison.

## 3. Comparing the same `run(..)` method by call path

| Call path | Reference held by caller | Goes through Spring AOP proxy into `run(..)`? | Prediction when advice targets only `run(..)` |
| --- | --- | --- | --- |
| `context.getBean(TaskService.class).run("A")` | Spring bean proxy from context | Yes, if bean is proxied and method is interceptable | Advice runs if pointcut matches. |
| Bean X injects `TaskService` and calls `taskService.run("A")` | Spring-injected proxy | Yes | Advice runs if pointcut matches. |
| Controller injects `TaskService` and calls `run("A")` | Spring-injected proxy | Yes | Advice runs if it matches. |
| `TaskService.outer()` calls `this.run("A")` | `this` is the running target instance | **No**; self-invocation | Advice dedicated to `run(..)` is bypassed. |
| `TaskService.outer()` calls `run("A")` without writing `this` | Still an implicit internal call on `this` | **No** | Same outcome as the row above. |
| `new TaskService().run("A")` | Manual object outside container | No Spring proxy | Spring advice does not run. |
| `@PostConstruct` on `TaskService` itself calls `run("A")` | Target undergoing initialization | Should not be treated as a client call through a complete proxy | Do not expect advice for `run(..)`. |
| `@PostConstruct` on bean X calls injected, proxied `TaskService` bean | Reference to **another bean's proxy** | **Possibly yes** | Advice can run if `TaskService` has finished initialization/proxying. |
| Caller holds a JDK proxy yet tries to call a method outside proxy interfaces | No corresponding entry method on proxy | Cannot be invoked directly via that interface type | Adjust contract or proxy type. |
| A `final` method on a class-based CGLIB proxy | Class proxy cannot override a `final` method | Does not intercept that method | Advice does not run even though bean has a proxy. |

The table applies standard Spring Framework conditions; specific cases can also be affected by multiple advisors, scopes, target sources, and infrastructure configuration. Never assume "same method name" forces Spring AOP to behave identically.

### Distinguishing "target method ran" from "advice ran"

Across all four call paths (proxy, internal, collaborator, `new`), **`run(..)`'s body can still execute and return the same string**. What differs is the presence of **the interception step** before/after the target method. Consequently, checking return values alone can let AOP bugs slip past: business outputs look fine while proxy-based auditing, metrics, transactions, or security were bypassed.

## 4. Complete Spring Framework demo: one target method, four call paths

Self-contained demo using **Java 17+**, **Spring Framework 6.2.19**, **AspectJ Weaver 1.9.25.1**, and Gradle. This uses plain Spring Framework configuration so `@EnableAspectJAutoProxy` itself turns on the infrastructure, without relying on Spring Boot auto-configuration.

Goal: execute **the same Java method `TaskService.run(String)`** four times with the same logic, while `@Before` advice **executes only twice** — matching the two call paths that genuinely go through a Spring proxy.

### 4.1. Project structure

```text
spring-aop-call-path-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/callpath/
    ├── AppConfig.java
    ├── TaskService.java
    ├── OtherService.java
    ├── TraceAspect.java
    └── Main.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'spring-aop-call-path-demo'
```

**`build.gradle`**

```gradle
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
    implementation 'org.springframework:spring-aop:6.2.19'
    implementation 'org.aspectj:aspectjweaver:1.9.25.1'
}

application {
    mainClass = 'com.example.callpath.Main'
}
```

The versions above define a demo environment. With Spring Boot, use the starter/BOM matching the application's Boot major version instead of pinning individual Spring versions as in this example.

### 4.2. Target with target method and self-invoking method

**`TaskService.java`**

```java
package com.example.callpath;

public class TaskService {
    public String run(String source) {
        System.out.println("target:" + source);
        return "done:" + source;
    }

    public String outer(String source) {
        return this.run(source);
    }
}
```

Both are public methods and the class is non-final, so the self-invocation limit is not confounded by `private` or `final` issues. Spring attaches the demo's advisor only to `run(..)`, **not to `outer(..)`**.

### 4.3. Another bean injected with the proper Spring proxy

**`OtherService.java`**

```java
package com.example.callpath;

public class OtherService {
    private final TaskService taskService;

    public OtherService(TaskService taskService) {
        this.taskService = taskService;
    }

    public String callTask(String source) {
        return taskService.run(source);
    }
}
```

Point to notice: `OtherService` does not call `new TaskService()`; Spring configuration injects the container-processed instance. When `TaskService` is proxied, the injected dependency is the matching **proxy reference**.

### 4.4. Aspect targeting a single method

**`TraceAspect.java`**

```java
package com.example.callpath;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {
    private final AtomicInteger counter = new AtomicInteger();

    @Before("execution(public * com.example.callpath.TaskService.run(..))")
    public void beforeRun() {
        int value = counter.incrementAndGet();
        System.out.println("advice:run#" + value);
    }

    public int invocationCount() {
        return counter.get();
    }
}
```

`@Before` increments the counter **only when `run(..)` actually passes through advice**. This counter illustrates behavior in a singleton aspect bean; it is not a cluster-wide counter. `AtomicInteger` ensures thread-safe increments if invoked concurrently.

### 4.5. Spring bean and AOP configuration

**`AppConfig.java`**

```java
package com.example.callpath;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    TraceAspect traceAspect() {
        return new TraceAspect();
    }

    @Bean
    TaskService taskService() {
        return new TaskService();
    }

    @Bean
    OtherService otherService(TaskService taskService) {
        return new OtherService(taskService);
    }
}
```

`TraceAspect` becomes a Spring-managed `@Aspect` bean via `@Bean`, without needing `@Component`. `@EnableAspectJAutoProxy` enables `@AspectJ` processing and auto-proxying. `proxyTargetClass=true` selects class-based proxies so `context.getBean(TaskService.class)` is valid for a concrete class with no interface.

The remaining two `@Bean` methods create the target and caller bean. When Spring constructs `OtherService`, the `TaskService` parameter receives the Spring bean/proxy via injection. That is the essential link so calls between the two beans genuinely traverse the proxy.

### 4.6. Main printing each call path separately

**`Main.java`**

```java
package com.example.callpath;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            TaskService task = context.getBean(TaskService.class);
            OtherService other = context.getBean(OtherService.class);
            TraceAspect aspect = context.getBean(TraceAspect.class);

            System.out.println("proxy=" + AopUtils.isAopProxy(task));

            System.out.println("path=direct-proxy");
            System.out.println("result=" + task.run("direct"));

            System.out.println("path=self-invocation");
            System.out.println("result=" + task.outer("internal"));

            System.out.println("path=another-bean");
            System.out.println("result=" + other.callTask("collaborator"));

            System.out.println("path=manual-new");
            TaskService plainObject = new TaskService();
            System.out.println("result=" + plainObject.run("plain"));

            System.out.println("adviceCount=" + aspect.invocationCount());
        }
    }
}
```

### 4.7. Running and verifying exact stdout

In the project directory, with Gradle installed:

```bash
gradle run --quiet
```

If using a Gradle Wrapper, run `./gradlew run --quiet` (Linux/macOS) or `gradlew.bat run --quiet` (Windows).

**Lines printed by the program, in exact order** (excluding JVM, Gradle, or Spring warnings/logs if logging is enabled):

```text
proxy=true
path=direct-proxy
advice:run#1
target:direct
result=done:direct
path=self-invocation
target:internal
result=done:internal
path=another-bean
advice:run#2
target:collaborator
result=done:collaborator
path=manual-new
target:plain
result=done:plain
adviceCount=2
```

### 4.8. Reading each case along its actual path

**Case 1 — direct-proxy**

`task.run("direct")` is invoked on the `TaskService` bean obtained from `ApplicationContext`. The bean was auto-proxied and the pointcut targets `run(..)`. Hence `advice:run#1` appears before `target:direct`.

**Case 2 — self-invocation**

`task.outer("internal")` passes through the Spring proxy at entry `outer(..)`; however, the aspect **has no advice for `outer(..)`**. Once execution enters the `TaskService` target, `this.run("internal")` invokes the method directly on the target itself, bypassing `TaskService`'s proxy. Therefore, **there is no `advice:run#2` in this case**.

**Case 3 — another-bean**

`other.callTask("collaborator")` executes `OtherService` logic. Its `taskService` field was injected by Spring with the `TaskService` proxy. Calling `taskService.run("collaborator")` enters **the proxy from outside the target**, so advice runs. The counter increments to `2`, printing `advice:run#2` and then `target:collaborator`.

**Case 4 — manual-new**

`plainObject.run("plain")` executes the exact same Java method body on `TaskService`, yet on an object created via `new` **outside the Spring container**. There is no AOP proxy on this reference, so no advice appears.

**Demo takeaway:** the exact same `run(..)` method executed four times and its target body printed `target:...` four times, yet `@Before` advice ran only **twice**. For the first three cases, the Spring-managed `TaskService` target bean is one and the same; the final case deliberately swaps to a different object instance for contrast.

## 5. Isolating the "same target" variable in the test

To avoid confusing changing the object with changing the call path, compare **the first three cases** of section 4. `TaskService` created by `@Bean` is a singleton by default: both `task.run("direct")` and `other.callTask("collaborator")` go through the proxy to that bean, while `task.outer("internal")` enters the same target yet calls `this.run` on itself. The advice counter equals `2` while `run`'s body executed three times on the Spring target.

The `manual-new` case runs on a separate object solely to contrast container scope. A unit test doing `new TaskService()` can verify the return value, yet cannot prove Spring advice is active.

## 6. Changing call timing: constructors and init callbacks

A constructor or `@PostConstruct` **on the `TaskService` target itself** calls `run()` via `this` before a finalized proxy is handed to normal callers; do not use those callbacks to verify advice targeting `run()`. By contrast, a callback on **another bean** can call through `TaskService`'s proxy if that dependency has finished initializing. Never call `context.getBean` from a constructor to "fetch the proxy early", as that can cause circular dependencies or early-reference issues.

For startup work that must pass through advice, use a separate coordinator at an appropriate context milestone, such as `ContextRefreshedEvent` or a Boot runner, and verify **the actual receiver**. The dedicated lifecycle lesson analyzes callback ordering and exception conditions in depth.

## 7. When advice wraps `outer(..)` while `inner(..)` is unwrapped

A widespread misconception is "the caller already entered the proxy at the outer method, so every inner method automatically goes through AOP too".

Consider:

```java
@Aspect
@Component
class TwoMethodsAspect {
    @Before(
        "execution(* com.example.callpath.TaskService.outer(..))"
        + " || execution(* com.example.callpath.TaskService.run(..))"
    )
    public void beforeBoth(JoinPoint point) {
        System.out.println("advice:" + point.getSignature().getName());
    }
}
```

This is a **separate illustrative variant**, requiring imports for `JoinPoint`, `Aspect`, `Before`, `Component` and component scanning to be registered; **do not add it to the main demo** if you want to keep stdout unchanged.

When a caller invokes `taskProxy.outer("A")`:

1. The proxy intercepts `outer(..)`, so advice for `outer` can run.
2. The target executes `outer(..)`.
3. `this.run("A")` executes directly on the target.
4. Advice targeting `run(..)` **does not automatically run a second time** just because `outer(..)` was advised.

Thus logs may show `advice:outer`, followed by `run` executing, with **no `advice:run`**. Entering a proxy at the entry point does not create an automatic "proxy loop" for nested calls.

Conversely, if `outer(..)` switches to calling an **injected collaborator bean** that has a proxy and matching pointcut, another advice can run at that new boundary. That is a different architectural boundary, not a nested self-call inside the same target.

## 8. Consequences when a call path bypasses interceptors

| Properly enabled concern | Through proxy with matching advisor | Self-call on target |
| --- | --- | --- |
| Custom `@Aspect` auditing | Can record audit event | Does not run advice dedicated to the inner method. |
| `@Transactional` | Applies propagation via transaction interceptor | Inner does not trigger a new interceptor; may still stay within an existing transaction. |
| `@Cacheable` | Can perform cache lookup/put | Inner bypasses cache advice. |
| `@Async` or method security | Can run executor/authorization rules | No separate interception on the inner call. |

Each concern requires its own activation/configuration; `@EnableAspectJAutoProxy` does not enable all of these automatically. If refactoring alters call paths, test actual transaction outcomes, cache hits, execution threads, or authorization decisions. Identical return values are not enough to prove policy enforcement.

## 9. Receiver and interceptability: conditional checks

**JDK dynamic proxies** expose only methods on proxied interfaces; **CGLIB proxies** can expose concrete class methods yet cannot override `final`/`private` methods. Neither makes `this.inner()` route back through the proxy. With reflection, `method.invoke(receiver, args)` is intercepted by Spring AOP only when **the receiver is a proxy** and the method is validly callable; reflection does not inherently guarantee or bypass advice.

`AopUtils.isAopProxy(bean)`, `isJdkDynamicProxy`, and `isCglibProxy` help identify references; `Advised.getAdvisors()` lets you inspect the chain if the proxy implements `Advised`. Never use `equals`, runtime class names, or proxy presence as proof that a **specific method** is advised. Counters/event recorders as in section 11 verify actual runtime execution.

## 10. Choosing a fix by policy and call site

| Proven situation | Resolution direction | What to re-test |
| --- | --- | --- |
| Policy applies to **the entire outer operation** | Target advice at the `outer(..)` entry already passing through the proxy | Transactions, retries, exceptions, and policy scope may shift. |
| Inner method is a distinct business responsibility | Move it to a **Spring collaborator bean**, inject the dependency, and call via proxy | Whether bean is managed, old pointcuts match new class/method, and semantics remain right. |
| Unavoidable need to call the bean's own proxy | Consider self-injection with `@Lazy` or `ObjectProvider`; manage lifecycle and proxy type | Circular dependencies, scopes, and premature calls. |
| Unavoidable need for `AopContext.currentProxy()` | Only inside a proxy invocation with `exposeProxy=true`, casting properly for JDK/CGLIB | `IllegalStateException` when context is absent, recursion, and coupling. |

Switching to AspectJ weaving changes the interception model and requires separate compiler/agent setup; `@EnableAspectJAutoProxy` does not enable weaving. Separate lessons on collaborators, self-injection, and `AopContext` cover deep examples; here the priority is **confirming the call path before and after the fix**.

## 11. Inspecting the Spring context properly

### 11.1. Confirming the retrieved bean is a proxy

```java
TaskService bean = context.getBean(TaskService.class);
System.out.println("isProxy=" + AopUtils.isAopProxy(bean));
System.out.println("isClassProxy=" + AopUtils.isCglibProxy(bean));
```

This is an illustrative snippet using `context` from the demo and importing `AopUtils`. With the demo's `AppConfig`, the two lines print `true` and `true` respectively. Do not look up by concrete type when configured for JDK interface proxies; in that case retrieve and inject by interface.

**Proxy presence is not enough to conclude.** A bean may have multiple advisors, and the advisor of interest might not match the method being called. After checking the proxy, invoke a method and clearly observe advice events or recorders.

### 11.2. Counting advice invocations

`TraceAspect` in the demo has an `AtomicInteger` and an `invocationCount()` method. After four cases, `adviceCount=2` while `TaskService.run`'s body ran four times. This directly measures the gap between **method body executions** and **advised executions**.

For automated tests, replace console output with an `EventRecorder` Spring bean holding a thread-safe collection, inject the recorder into the aspect, run the cases, and assert:

- `directProxy` produces one audit event.
- `selfInvocation` produces no separate audit event for the inner method.
- `otherBean` produces one more event.
- `manualNew` produces no event.
- Business outputs still match the contract.

In this test, **method events** are what prove AOP ran, not merely `AopUtils.isAopProxy`.

### 11.3. Setting breakpoints in two places

Place breakpoints in `TraceAspect.beforeRun` and `TaskService.run`. When calling `task.outer("internal")`, the debugger enters `run` without hitting `beforeRun` for that call. When calling `task.run("direct")`, the debugger hits advice before the target. When calling `other.callTask("collaborator")`, the path matches the direct proxy.

This helps prove an AOP issue is not a method-invocation failure — the method body still runs fine, merely skipping the interceptor chain.

### 11.4. Checking pointcuts if the call already passes through the proxy yet lacks advice

If a case definitely passes through a Spring bean proxy yet advice still does not run, check:

1. Does the aspect class have `@Aspect` and is it registered as a bean via `@Component` or `@Bean`?
2. In Spring Framework Java config, are `@EnableAspectJAutoProxy` and `aspectjweaver` present, or in Boot is AOP auto-configuration appropriate?
3. Do `execution(..)`, `@annotation(..)`, or `bean(..)` pointcuts target the exact **runtime method/type/bean**?
4. Does a JDK proxy bean expose the method via its interface? Does a class proxy hit `final`/`private`?
5. Does the client actually hold the proxy reference, or did it manually `new`, hold a raw target, or call internally via `this`?
6. Are there multiple `ApplicationContext`s or multiple bean instances? In which context are aspects/advisors enabled?
7. Is another advice swallowing exceptions, returning early, altering args, or dispatching async so logs appear at a different time?

Do not add duplicate `@EnableAspectJAutoProxy` annotations or switch to CGLIB before pinpointing the cause.

## 12. Situations prone to wrong conclusions

| Observation | Common hasty wrong conclusion | Accurate Spring AOP interpretation |
| --- | --- | --- |
| Two calls share the same target method source code | "Advice must run identically" | Check whether one call goes through a proxy and the other via `this` or a raw object. |
| `AopUtils.isAopProxy(task)==true` | "Every method is advised" | Only proves a proxy exists; check method/pointcut and call path. |
| `outer()` is advised | "`this.inner()` is advised too" | Target self-calls do not loop back through the proxy. |
| Added `public` to the inner method | "Fixed AOP" | Visibility does not solve self-invocation. |
| Enabled `proxyTargetClass=true` | "CGLIB intercepts internal calls automatically" | Still Spring proxy-based interception with self-call bypass. |
| Another bean calls a method from `@PostConstruct` | "All init calls bypass" | If the reference to the other target is already a finalized proxy, advice can run. |
| Created `new TaskService()` inside a bean | "Because caller is a Spring bean, target gets AOP too" | Manually created objects do not become Spring proxies automatically. |
| Method has `@Transactional` | "Definitely running in a transaction" | Requires activation, proxy boundary, and actual transaction verification. |
| Calling via reflection | "Reflection always bypasses / always triggers advice" | Depends on whether the receiver is a proxy and the method is exposed. |
| Switched to a collaborator bean yet see no advice | "Spring AOP doesn't support multiple beans" | Verify the collaborator is genuinely Spring-managed and the pointcut still matches. |

## 13. Workflow for analyzing a real bug

### Step 1 — Pinpoint the exact method

Write down FQCN, name, signature, annotations, bean name, and pointcut. Do not stop at "the method has an annotation and isn't working".

### Step 2 — Record the caller → receiver path

Map the references: controller/service/coordinator/target; distinguish `this`, DI proxy, `new` instance, and context bean. Who is the **receiver** at the exact method call?

### Step 3 — Check proxy type and interceptability

Run `AopUtils` on the bean returned by the context. For JDK proxies, the method must be on an interface; for CGLIB, the method must be overridable. Do not confuse `final`/`private` limits with self-invocation.

### Step 4 — Verify the aspect bean and matching

Check `getBeanNamesForType(TraceAspect.class)`, enablement config/AspectJ dependency, and pointcut matching. If advice is not recognized by the container, no proxy path can help.

### Step 5 — Test two controlled call paths

From a real Spring context test, call `taskProxy.run("X")`, then call `taskProxy.outer("X")` which self-invokes the same method. Use a recorder/counter to confirm the difference. Keep inputs identical to isolate the call-path cause.

### Step 6 — Replace with an injected collaborator if needed

Move the operation needing advice to another Spring bean or move the policy boundary. Update pointcuts for the new method; avoid `new`-ed objects and circular dependencies.

### Step 7 — Test semantics beyond logs

If the concern is security, transactions, caching, async, metrics, or retries, test the actual desired behavior — especially errors, rollbacks, and side effects; never conclude from advice logs alone. Once refactoring makes advice start running, production semantics can shift significantly.

### Step 8 — Review startup and concurrency

Separate target constructor/`@PostConstruct` calls from normal entry calls; check bean lifecycle. With async/multithreading, make no rigid assumptions about log ordering.

## 14. Summary checklist

- [ ] Distinguished **whether the method body ran** from **whether advice ran**?
- [ ] Identified the exact **receiver reference** at the call site (`this`, DI proxy, `new`, raw target)?
- [ ] When comparing two call paths, kept target method/pointcut/input constant to avoid noise?
- [ ] Aspect has `@Aspect` and is a Spring bean; auto-proxy support is enabled?
- [ ] Spring target bean has a matching proxy and a public/interface entry method that is interceptable?
- [ ] Checked that both `this.inner()` and implicit `inner()` are self-invocations?
- [ ] When caller is another bean, is the dependency obtained from Spring container/DI?
- [ ] For constructors/`@PostConstruct`, accounted for proxies not yet finalized?
- [ ] Avoided assuming CGLIB, JDK proxies, or reflection automatically resolve every call path?
- [ ] If moved to a collaborator, updated pointcuts and tested exception/return/transaction/security semantics?
- [ ] Used a Spring context integration test + recorder/counter to measure exact advice invocations?
- [ ] Avoided relying on a single log message or `isAopProxy=true` to draw sweeping conclusions?

**Key point to remember:** In Spring AOP, **the exact same target method can exhibit two different interception behaviors because the call paths differ**. Spring proxies apply advice only when calls pass through the appropriate proxy; `this.method()` and out-of-container objects do not share that boundary. When debugging, draw **caller → receiver → proxy → target**, then verify with a real context-backed test.

## Official Spring documentation

- [Spring Framework 6.2 — Proxying Mechanisms / Understanding AOP Proxies](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html)
- [Spring Framework 6.2 — Declaring an Aspect](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/at-aspectj.html)
- [Spring Framework 6.2 — Pointcut Declarations](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html)
- [Spring Framework 6.2 — Bean Lifecycle / Initialization](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html)