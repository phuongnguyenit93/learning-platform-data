# Identifying Residual Ribbon, Hystrix, and Zuul Configuration in a Project

During a Spring Cloud application upgrade, removing a dependency and seeing the project compile successfully **does not prove** the legacy technology has been eliminated. Ribbon may still be pulled in transitively and continue participating in instance selection; Hystrix may still be invoked through annotations, a Feign builder, or fallbacks; Zuul 1 may still initialize its reverse proxy and retain old routes. Conversely, a `zuul` configuration line or a class with `Hystrix` in its name is not enough to conclude the runtime is using the legacy library.

This lesson belongs to the **Compatibility and Upgrades** chapter of the **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING** module. We will identify traces of **Netflix Ribbon, Hystrix, and Zuul 1** across four sources of evidence: the dependency graph, source code, effective configuration, and runtime behavior. Then we will map each capability accurately to **Spring Cloud LoadBalancer**, **Spring Cloud CircuitBreaker** (for example, Resilience4j), and **Spring Cloud Gateway**, and establish a safe removal and regression testing workflow.

> **Scope:** "Ribbon" refers to Netflix Ribbon integrated via Spring Cloud Netflix; "Hystrix" refers to Netflix Hystrix and its legacy Spring Cloud integration; "Zuul" refers to Zuul 1 / Spring Cloud Netflix Zuul. This lesson does not require removing Eureka: Spring Cloud Netflix still maintains documentation and starters for Eureka Client/Server. Nor does it treat `@LoadBalanced`, Spring Cloud OpenFeign, or all circuit breakers as legacy technology.

## 1. Why Search for Traces Before Upgrading?

Long-lived systems often contain one or more of these situations:

- The application switched from Ribbon to Spring Cloud LoadBalancer, yet the Ribbon starter remains because an internal module pulls it in.
- The code removed `@HystrixCommand`, yet `spring-cloud-starter-netflix-hystrix` stays in the dependency graph and auto-configuration can still load.
- A gateway already has Spring Cloud Gateway, yet it still initializes Zuul 1 with legacy routes.
- `application.yml` contains many `ribbon.*`, `hystrix.*`, and `zuul.*` properties; it is unclear which ones are still bound.
- Certain profiles, environment variables, or Config Server entries still override legacy settings.
- The local build passes, but the production image uses a different profile or dependency graph.
- Legacy dashboards/alerts still carry the "Hystrix" name even though runtime has moved to Resilience4j.

The impact is more than unused dependencies:

| Residual trace | Risk |
|---|---|
| Ribbon starter/artifact | Two load-balancing implementations coexist; in some older release trains Ribbon may take precedence when both are present |
| Hystrix starter/code | Timeouts, thread isolation, fallbacks, and metrics no longer match the new configuration |
| Zuul 1 starter/routes | The old proxy keeps receiving traffic; filter and routing behavior differ from the new gateway |
| Legacy properties | Configuration appears migrated but is actually ignored; operations misunderstands timeouts/retries |
| Transitive dependency | Removing the direct dependency still leaves the legacy library on the runtime classpath |
| Legacy dashboards/metrics | Misleading observability; alerts do not reflect the active implementation |

Spring Cloud announced that Ribbon, Hystrix, and Zuul 1 entered **maintenance mode** starting in Spring Cloud Greenwich; the recommended replacements were Spring Cloud LoadBalancer, Resilience4j, and Spring Cloud Gateway, respectively. Maintenance mode in that historical announcement meant halting new feature development and considering only blocker/security fixes within the support window stated at the time. For your current release train, consult the current documentation and compatibility matrix rather than assuming all modules have the same support status.

## 2. Identifying Four Layers of Evidence

Do not draw conclusions from a single search hit. A project may contain old migration docs, examples in tests, or dependencies used only by another module.

| Layer | Question | Evidence to record |
|---|---|---|
| **Dependency graph** | Is the legacy artifact on the compile/runtime/test classpath? | Maven/Gradle tree, transitive dependency path pulling it in |
| **Source code** | Are legacy classes, annotations, or APIs being called? | Imports, annotations, beans, filters, commands, builders |
| **Configuration** | Are legacy properties loaded and bound in the actual profile? | `application*.yml`, env vars, Config Server, Helm |
| **Runtime behavior** | Which implementation is handling requests? | Condition evaluation, startup logs, routes, metrics, traces, integration tests |

A dependency on `testRuntimeClasspath` does not mean the production app runs it. A property in YAML does not mean any Spring Boot component reads it. Conversely, an indirect dependency can still be active even if `pom.xml` does not declare it directly.

Classify findings per module/service:

- **ACTIVE:** dependency/runtime bean/source path is actively in use.
- **TRANSITIVE:** not declared directly, but pulled in by another artifact.
- **CONFIG-ONLY:** only legacy config remains; no component is seen reading or binding it.
- **CODE-ONLY:** classes/imports/annotations remain; need to verify whether they are invoked.
- **HISTORICAL:** appears only in docs, changelogs, migration notes, or non-production test fixtures.
- **UNKNOWN:** insufficient evidence; need to inspect runtime profile or dependency path.

## 3. Identifying Maven and Gradle Dependencies

### 3.1. Artifacts to Look For

| Technology | Common Spring Cloud starter/artifact | Common underlying artifacts |
|---|---|---|
| Ribbon | `spring-cloud-starter-netflix-ribbon`, `spring-cloud-netflix-ribbon` | `com.netflix.ribbon:ribbon-*`, `ribbon-loadbalancer` |
| Hystrix | `spring-cloud-starter-netflix-hystrix`, `spring-cloud-netflix-hystrix` | `com.netflix.hystrix:hystrix-core`, `hystrix-javanica`, `hystrix-metrics-event-stream` |
| Hystrix Dashboard/Turbine | `spring-cloud-starter-netflix-hystrix-dashboard`, `spring-cloud-starter-netflix-turbine` | `hystrix-dashboard`, `turbine-*` |
| Zuul 1 | `spring-cloud-starter-netflix-zuul`, `spring-cloud-netflix-zuul` | `com.netflix.zuul:zuul-core` |
| Modern components to distinguish | `spring-cloud-starter-loadbalancer`, `spring-cloud-starter-circuitbreaker-*`, Spring Cloud Gateway starter | Resilience4j, Micrometer |

Artifact names can vary across Spring Cloud generations or be split into modules. Use the dependency tree of the **exact module and exact configuration** as the final evidence; the table above is a starting search list.

### 3.2. Maven: Inspecting the Dependency Tree

From the directory containing `pom.xml`:

~~~powershell
.\mvnw.cmd dependency:tree -Dverbose
~~~

Filter by each artifact group:

~~~powershell
.\mvnw.cmd dependency:tree -Dverbose "-Dincludes=org.springframework.cloud:spring-cloud-starter-netflix-ribbon,org.springframework.cloud:spring-cloud-netflix-ribbon,com.netflix.ribbon:*"
.\mvnw.cmd dependency:tree -Dverbose "-Dincludes=org.springframework.cloud:spring-cloud-starter-netflix-hystrix,org.springframework.cloud:spring-cloud-netflix-hystrix,com.netflix.hystrix:*"
.\mvnw.cmd dependency:tree -Dverbose "-Dincludes=org.springframework.cloud:spring-cloud-starter-netflix-zuul,org.springframework.cloud:spring-cloud-netflix-zuul,com.netflix.zuul:*"
~~~

If not using Maven Wrapper, replace `.\mvnw.cmd` with `mvn`. Some Maven Dependency Plugin versions interpret wildcards/`includes` differently; if the filter does not return expected results, run `dependency:tree` without a filter and search directly in the output.

Example of a transitive dependency:

~~~text
order-service
\- com.example:legacy-http-adapter:1.4.0
   \- org.springframework.cloud:spring-cloud-starter-netflix-ribbon:...
      \- com.netflix.ribbon:ribbon-loadbalancer:...
~~~

In this case, removing the Ribbon line from `order-service` is not enough because the pulling source is `legacy-http-adapter`. You must upgrade, replace, or exclude the right dependency at that edge after confirming the adapter does not need legacy APIs.

To view the POM after parent/BOM/profiles inheritance:

~~~powershell
.\mvnw.cmd help:effective-pom -Doutput=target/effective-pom.xml
~~~

Effective POM helps uncover dependencies added by a parent/profile and versions managed by a BOM. It does not replace `dependency:tree`: an artifact declared in the POM might not appear in the runtime graph once exclusions/profiles are applied.

### 3.3. Gradle: Checking runtimeClasspath and Dependency Paths

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-cloud-starter-netflix-ribbon --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-cloud-netflix-ribbon --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-cloud-starter-netflix-hystrix --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-cloud-netflix-hystrix --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-cloud-starter-netflix-zuul --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-cloud-netflix-zuul --configuration runtimeClasspath
~~~

If an artifact appears only in `testRuntimeClasspath`, record the exact scope. For multi-project Gradle builds, run against the exact project path, for example:

~~~powershell
.\gradlew.bat :services:order-service:dependencyInsight --dependency spring-cloud-netflix-ribbon --configuration runtimeClasspath
~~~

If using version catalogs, platforms/BOMs, convention plugins, or dependency constraints, trace back to where they are declared; do not manually override centrally managed versions without understanding their source.

### 3.4. Verifying the Dependency Graph After Removal

After migrating, re-run the same commands for the **same module and configuration**. The goal is to confirm:

- Legacy starters/artifacts are no longer on the runtime classpath.
- No internal adapter pulls those artifacts back in.
- Replacement dependencies remain present in the exact modules that need them.
- Test scope only retains them if there is a clear reason, and they are not packaged into the production artifact.
- Eureka Client/Server were not accidentally removed just because they belong to Spring Cloud Netflix.

## 4. Finding Traces in Source Code

Search for imports, annotations, class names, and API usage. Do not search only for starter artifacts, as code may use the underlying libraries directly.

### 4.1. Ribbon

Indicators worth checking:

~~~java
import com.netflix.loadbalancer.ILoadBalancer;
import com.netflix.loadbalancer.IRule;
import com.netflix.loadbalancer.Server;
import com.netflix.loadbalancer.ServerList;
import com.netflix.loadbalancer.ServerListFilter;
import org.springframework.cloud.netflix.ribbon.RibbonClient;
import org.springframework.cloud.netflix.ribbon.RibbonClients;
import org.springframework.cloud.netflix.ribbon.RibbonLoadBalancedRetryFactory;
~~~

Common keywords:

- `@RibbonClient`, `@RibbonClients`
- `ILoadBalancer`, `IRule`, `ServerList`, `ServerListFilter`, `IPing`
- `RibbonClientConfiguration`, `RibbonLoadBalancerClient`
- `ZoneAvoidanceRule`, `WeightedResponseTimeRule`, `BestAvailableRule`, `AvailabilityFilteringRule`
- `RibbonLoadBalancedRetryFactory`
- `com.netflix.loadbalancer.*`

Rule or class names may appear in old documentation/tests. Check whether they are imported, registered as beans, or configured via properties at runtime.

### 4.2. Hystrix

~~~java
import com.netflix.hystrix.HystrixObservableCommand;
import com.netflix.hystrix.contrib.javanica.annotation.HystrixCommand;
import com.netflix.hystrix.contrib.javanica.annotation.HystrixProperty;
import org.springframework.cloud.netflix.hystrix.EnableHystrix;
~~~

Common indicators:

- `@EnableHystrix`, `@HystrixCommand`, `@DefaultProperties`
- `HystrixCommand`, `HystrixObservableCommand`, `HystrixCollapser`
- `HystrixFeign`, `HystrixFeign.Builder`
- `HystrixCircuitBreaker`, `HystrixCommandProperties`
- `HystrixMetricsStreamServlet`, `/hystrix.stream`
- `com.netflix.hystrix.*`, `org.springframework.cloud.netflix.hystrix.*`

**Do not conclude from `@EnableCircuitBreaker` alone.** This annotation used to be an abstraction/entry point across older Spring Cloud generations; check the concrete implementation and dependency graph. Likewise, a class named `CircuitBreaker` could be custom domain code.

### 4.3. Zuul 1

~~~java
import org.springframework.cloud.netflix.zuul.EnableZuulProxy;
import org.springframework.cloud.netflix.zuul.EnableZuulServer;
import org.springframework.cloud.netflix.zuul.filters.ProxyRequestHelper;
import com.netflix.zuul.ZuulFilter;
~~~

Common indicators:

- `@EnableZuulProxy`, `@EnableZuulServer`
- `ZuulFilter`, `ZuulFilterFactory`, `ZuulProperties`
- `RibbonRoutingFilter`, `SimpleHostRoutingFilter`, `PreDecorationFilter`
- `com.netflix.zuul.*`, `org.springframework.cloud.netflix.zuul.*`
- `/zuul` servlet mapping or `/hystrix.stream` routed through the legacy proxy
- Custom pre/route/post/error filters extending `ZuulFilter`

If the code defines a custom `ZuulFilter` class in another package, do not automatically assume it is Netflix Zuul. Verify the fully qualified name and dependencies.

### 4.4. Quick Search with ripgrep

Run from the repo root:

~~~powershell
rg -n -i --hidden -g '!**/.git/**' -g '!**/target/**' -g '!**/build/**' -g '!**/.gradle/**' -g '!**/.idea/**' 'spring-cloud-(starter-)?netflix-(ribbon|hystrix|zuul)|com\.netflix\.(loadbalancer|hystrix|zuul)|@Ribbon(Client|Clients)|@Enable(Hystrix|ZuulProxy|ZuulServer)|@HystrixCommand|HystrixFeign|RibbonLoadBalancerClient|ZuulFilter' .
~~~

The command above searches sources, POMs, Gradle files, YAML, and XML in the repo; exclusions skip common build/generated outputs. If the repository uses other directories for generated sources or configs, adjust the globs instead of assuming "no matches" means clean.

Search separately for configuration prefixes:

~~~powershell
rg -n -i --hidden -g '!**/.git/**' -g '!**/target/**' -g '!**/build/**' '(^|[[:space:]])(ribbon|hystrix|zuul):|\.ribbon\.|hystrix\.command|hystrix\.threadpool|zuul\.routes|zuul\.prefix|zuul\.retryable' .
~~~

If PowerShell lacks `rg`, use `Get-ChildItem -Recurse -File` with `Select-String`, excluding `target`, `build`, `.git`, and generated files to reduce noise.


## 5. Identifying Residual Legacy Configuration

Search for broad property prefixes first, then match specific keys against the older Spring Cloud version the project uses.

### 5.1. Ribbon Properties

~~~yaml
ribbon:
  ConnectTimeout: 1000
  ReadTimeout: 3000
  MaxAutoRetries: 1
  MaxAutoRetriesNextServer: 1

inventory-service:
  ribbon:
    NFLoadBalancerRuleClassName: com.netflix.loadbalancer.ZoneAvoidanceRule
~~~

Other indicators:

- `ribbon.*` and `<service-id>.ribbon.*`
- `ribbon.eureka.enabled`
- `NFLoadBalancerRuleClassName`, `NIWSServerListClassName`, `NIWSServerListFilterClassName`
- `ConnectTimeout`, `ReadTimeout`, `MaxAutoRetries`, `MaxAutoRetriesNextServer`

This is a legacy Ribbon configuration example. Do not copy these keys into Spring Cloud LoadBalancer expecting them to work automatically; the configuration API, suppliers, and retry policies are different.

### 5.2. Hystrix Properties

~~~yaml
hystrix:
  command:
    default:
      execution:
        isolation:
          thread:
            timeoutInMilliseconds: 2500
  threadpool:
    default:
      coreSize: 20
~~~

Other indicators:

- `hystrix.command.*`
- `hystrix.threadpool.*`
- `hystrix.collapser.*`
- `hystrix.shareSecurityContext`
- `feign.hystrix.enabled` in older Spring Cloud OpenFeign generations
- `hystrix.stream`, `hystrix.dashboard`, `turbine.*`

Do not confuse Hystrix timeouts with HTTP client timeouts. A Hystrix command can wrap multiple operations, while connect/read timeouts apply at the transport layer; when migrating, define the deadline and placement of each timeout.

### 5.3. Zuul Properties

~~~yaml
zuul:
  prefix: /api
  ignored-services: "*"
  routes:
    inventory:
      path: /inventory/**
      serviceId: inventory-service
      stripPrefix: true
  retryable: false
  host:
    connect-timeout-millis: 1000
    socket-timeout-millis: 3000
~~~

Other indicators:

- `zuul.routes.*`, `zuul.prefix`, `zuul.ignored-services`
- `zuul.retryable`, `zuul.sensitive-headers`
- `zuul.host.*`
- `zuul.ribbon-isolation-strategy`
- `zuul.servlet-path`
- Route IDs and path rewrites declared in application config or Config Server.

Do not assume every key containing `route` is Zuul. `spring.cloud.gateway.routes` belongs to Spring Cloud Gateway; an application-defined `app.zuul.routeName` property also does not prove Zuul 1 is running.

### 5.4. Where Can Configuration Come From?

Search beyond `application.yml`:

- `application-{profile}.yml` and `application-{profile}.properties`.
- `bootstrap.yml`/`bootstrap.properties` in older Spring Cloud Config generations.
- Config Server repositories, profiles, and labels used by the caller.
- Environment variables such as `RIBBON_READ_TIMEOUT`, `HYSTRIX_COMMAND_DEFAULT_EXECUTION_ISOLATION_THREAD_TIMEOUT_IN_MILLISECONDS`, `ZUUL_ROUTES_*`.
- `SPRING_APPLICATION_JSON`, JVM system properties, and command-line arguments.
- Helm values, Kubernetes ConfigMaps/Secrets, Docker Compose, manifests, and deployment pipelines.
- Test resources with separate profiles; do not confuse test config with production config.

Spring Boot has property source and precedence rules. A key in the default file can be overridden by the environment or Config Server; inspect the **effective runtime configuration** under the exact profile.

### 5.5. Checking Bound Configuration at Runtime

In protected local/staging environments, Spring Boot Actuator can help:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,conditions,beans,configprops,env
~~~

Useful endpoints:

| Endpoint | Used for |
|---|---|
| `/actuator/conditions` | Seeing which auto-configurations matched or were excluded and why |
| `/actuator/beans` | Checking whether LoadBalancer, Feign, Gateway, or legacy beans were created |
| `/actuator/configprops` | Seeing properties bound by `@ConfigurationProperties` |
| `/actuator/env` | Seeing property sources and effective values when allowed by endpoint/configuration |

**Never expose `env`, `configprops`, `beans`, or `conditions` endpoints to the public Internet.** They can leak configuration, classpath, and infrastructure details; enable them temporarily only in controlled environments with authentication/network restrictions. A legacy property absent from `configprops` does not guarantee nothing reads it via `@Value` or `Environment.getProperty`.

## 6. Distinguishing Real Traces from False Positives

Do not remove active components just because a package name contains Netflix or a similar keyword.

| Search result | Initial conclusion |
|---|---|
| `spring-cloud-starter-netflix-ribbon` on `runtimeClasspath` | Strong evidence Ribbon integration is on the classpath; trace what pulls it in and check which implementation is used |
| `com.netflix.ribbon:ribbon-loadbalancer` only in test fixtures | Does not prove production uses Ribbon |
| `spring-cloud-starter-netflix-hystrix` on `runtimeClasspath` | Hystrix integration is on the classpath; inspect source/config/auto-configuration |
| `@EnableCircuitBreaker` without any Hystrix dependency | Insufficient evidence of Hystrix; could be an abstraction or uncleaned old code |
| `spring-cloud-starter-netflix-zuul` + `@EnableZuulProxy` | Strong evidence Zuul 1 is configured |
| `zuul` in business URLs, variable names, or documentation | Possible false positive |
| `spring-cloud-starter-netflix-eureka-client` | Eureka Client, **not** Ribbon/Hystrix/Zuul |
| `spring-cloud-starter-openfeign` | OpenFeign; does not imply Hystrix or Ribbon |
| `@LoadBalanced` | Client-side LoadBalancer integration annotation; not a Ribbon indicator |
| `spring-cloud-starter-loadbalancer` | Active replacement component to keep if the module uses it |
| `resilience4j-*` or Spring Cloud CircuitBreaker | Not Hystrix; check the proper implementation and new config |

### Three Easily Confused Situations

**Eureka can still be kept.** Spring Cloud Netflix continues to provide Eureka Client/Server. The fact that modules were historically distributed under Spring Cloud Netflix does not mean all Netflix modules are legacy or must be removed together.

**OpenFeign does not imply Ribbon.** Feign can integrate with Spring Cloud LoadBalancer through the appropriate dependency/integration. Inspect `@FeignClient(name = "inventory-service")`, the OpenFeign starter, and LoadBalancer on the classpath; do not delete Feign just because the app previously used Feign + Ribbon.

**`@EnableCircuitBreaker` does not imply Hystrix.** Check the import package, starter, and actual bean implementation created. If the project uses Spring Cloud CircuitBreaker + Resilience4j, do not treat it as an unrelated Hystrix migration.


## 7. Building an Inventory Before Editing

Do not start by deleting every matching keyword in the repo. Build a table by **module, profile, and runtime scope** to know what is actually active.

| Module | Trace | Dependency scope | Profile/runtime | Classification | Owner |
|---|---|---|---|---|---|
| order-service | `spring-cloud-starter-netflix-ribbon` | runtime, transitive from legacy adapter | prod | TRANSITIVE/ACTIVE needs verification | Order team |
| inventory-client | `@RibbonClient` and `IRule` | compile | prod | CODE-ONLY/ACTIVE | Platform |
| payment-service | `hystrix.command.default.*` | config | prod | CONFIG-ONLY needs bind trace | Payment team |
| edge-gateway | `@EnableZuulProxy` | runtime | prod | ACTIVE | Edge team |
| catalog-service | docs mention `HystrixCommand` | none | docs | HISTORICAL | Catalog team |

This is illustrative data; replace it with real evidence from each repository. For each row, record the dependency path, file/line, profile, service ID/route, runtime behavior, and responsible owner.

### 7.1. Finding Environment Variable Names and Deployment Config

In PowerShell, scan deployment directories alongside the repository:

~~~powershell
rg -n -i --hidden -g '!**/.git/**' -g '!**/target/**' -g '!**/build/**' 'RIBBON_|HYSTRIX_|ZUUL_|spring\.cloud\.loadbalancer\.ribbon\.enabled|feign\.hystrix\.enabled' .
~~~

If Config Server lives in another repository, run the same process against the **exact config repository** and the exact branch/label the application uses. The absence of a property in the source repo is not proof that Config Server does not supply it.

### 7.2. Checking Effective Runtime Configuration

You can temporarily enable the startup condition report:

~~~powershell
java -jar app.jar --debug
~~~

Or inspect `/actuator/conditions` and `/actuator/configprops` in a protected local/staging environment. Compare:

- Which legacy auto-configurations are imported/matched.
- Which beans are created per service ID or gateway context.
- Which property sources provide legacy keys.
- Which profiles are active and their override order.
- Whether any classpath condition keeps Ribbon/Hystrix/Zuul enabled even after annotations are removed from main source code.

The condition report may not list every property read via `Environment` or every manually created bean. Combine the report with source search and the dependency tree.

## 8. Safe Layer-by-Layer Migration Workflow

### Step 1 — Lock Baseline Versions Before Changing Libraries

Record:

- Spring Boot version.
- Effective Spring Cloud release train/BOM version.
- Java version.
- Maven/Gradle and plugin versions.
- Modules sharing common dependency management.
- Runtime profiles and external config loading mechanism.

Use the Spring Cloud compatibility table to select a release train compatible with Spring Boot. Do not upgrade Boot, Spring Cloud, Java, HTTP clients, and all three legacy technologies in one massive change without sufficient test coverage.

### Step 2 — Identify Which Capabilities Are Actually Used

For each trace, answer:

- Which rule is Ribbon running: Round Robin, zone, weighted, retry, or custom filtering?
- Which operation is Hystrix protecting; what do its timeout, isolation, fallback, and dashboard mean?
- Which routes is Zuul serving; which filters modify headers/paths/authentication/rate limits?
- Do those behaviors live in the API Gateway, service client, service adapter, or shared library?

Do not migrate class names; migrate **observable behavior and contracts**.

### Step 3 — Replace Ribbon First on One Client/Service ID

- Add the BOM-compatible Spring Cloud LoadBalancer starter.
- Switch the HTTP client to logical URIs using the service ID.
- Use `@LoadBalanced RestClient.Builder`, `@LoadBalanced WebClient.Builder`, or appropriate OpenFeign integration.
- Migrate necessary rules to `ServiceInstanceListSupplier`, built-in suppliers, or a custom `ReactorServiceInstanceLoadBalancer`.
- Test discovery, empty list, zone/hint/weight, retry, timeout, and no-instance scenarios.
- If Ribbon per-client config exists, migrate each service ID individually; do not accidentally create a global policy.

Do not keep both Ribbon and LoadBalancer solely as a "fallback" without understanding which implementation is selected. In some older release trains, documentation noted that Ribbon could take precedence when both starters were present.

### Step 4 — Replace Hystrix Operation by Operation

- Define the command boundary: a single HTTP call, a business operation, or an entire workflow.
- Choose a Spring Cloud CircuitBreaker implementation and the appropriate blocking/reactive starter.
- Migrate the circuit breaker ID, failure classification, slow-call threshold, TimeLimiter, and fallback.
- Design bulkheads/executors if thread isolation was previously used.
- Separate connect/read timeouts, overall deadlines, and retry policies.
- Verify SecurityContext/MDC/trace propagation when changing executors.
- Migrate metrics/dashboards to Micrometer and your monitoring backend.

Do not turn a Hystrix fallback into a Resilience4j fallback simply by keeping the response code: verify which errors are recorded, ignored, retried, or returned to the caller.

### Step 5 — Replace Zuul 1 with Gateway

- List all routes, predicates, prefixes, strip-prefix settings, rewrites, retries, sensitive headers, and custom filters.
- Create Spring Cloud Gateway routes with stable route IDs.
- Convert each pre/post/route/error filter into an equivalent `GatewayFilter`/`GlobalFilter`.
- Redesign filter ordering, reactive execution, and error handling.
- If routing via service discovery, use URI `lb://service-id` and verify LoadBalancer integration.
- Check CORS, authentication, forwarded headers, cookies, request bodies, WebSockets, and per-route timeouts.
- Shift traffic route group by route group / canary; maintain a gateway rollback plan.

Do not convert `ZuulFilter` code into `GlobalFilter` just by renaming the class. Lifecycle, ordering, request exchange, reactive execution, and error handling all differ. Heavy blocking filters can stall the WebFlux Gateway event loop; redesign and concurrency-test them.

### Step 6 — Remove Legacy Dependencies and Config After Verifying New Behavior

- Remove legacy starters/direct dependencies.
- If a dependency is transitive, address it in the pulling dependency or upgrade the adapter module.
- Remove `@RibbonClient`, `@HystrixCommand`, `@EnableZuulProxy`, and custom legacy classes once call sites have migrated.
- Remove `ribbon.*`, `hystrix.*`, and `zuul.*` keys across all profiles/deployment sources once semantics have been replaced.
- Decommission legacy dashboards/alerts after new metrics achieve equivalent coverage.
- Do not remove Eureka or OpenFeign if they are still used and compatible.

### Step 7 — Final Classpath and Runtime Verification

Re-run dependency tree/insight, source scans, config scans, and condition reports. Then test using a packaged artifact/image matching production, not just the IDE test classpath.

## 9. Post-Migration Regression Testing

### 9.1. Ribbon → LoadBalancer

| Scenario | Expectation |
|---|---|
| 2+ instances for the same service ID | Client selects a valid instance |
| Empty discovery list | Observable no-instance error; does not call a fake host |
| Unhealthy instance | Behavior matches defined health/discovery policy |
| Zone preference | Selects preferred subset and fallback behavior is understood |
| Weighted policy | Selection ratio matches metadata/weights |
| Retry | Attempts are bounded; avoids failed instances if policy requires |
| RestClient/WebClient/OpenFeign | All call by service ID and use LoadBalancer integration |
| Multiple service IDs | Custom config does not leak to other clients |

### 9.2. Hystrix → CircuitBreaker

| Scenario | Expectation |
|---|---|
| Backend success | Normal response, breaker CLOSED |
| Multiple failures | Breaker transitions OPEN at threshold |
| OPEN | Calls fail fast; fallback/error matches contract |
| HALF_OPEN | Bounded probes and proper recovery |
| Business 4xx | Not counted as dependency outage if ignored by policy |
| Slow response | TimeLimiter/timeout enforces the deadline |
| High concurrency | Bulkhead/concurrency limit keeps resources bounded |
| Fallback | Does not fabricate success data or cause repeated side effects |
| Metrics | State, failures, not-permitted, fallback, and latency are observable |

### 9.3. Zuul → Gateway

| Scenario | Expectation |
|---|---|
| Route predicate match | Request reaches the right backend |
| Path prefix/rewrite | Backend receives the expected request path |
| Headers/cookies | Forwarding/removal policy works properly |
| Authentication | Security filters execute in the right order |
| Retry/timeout | Does not cause a retry storm or exceed deadline |
| Backend unavailable | Structured error/fallback |
| High concurrency | Event loop is not blocked; p95/p99 within SLO |
| Multiple routes | Does not misroute service IDs or public endpoints |
| Rollback | Traffic can be shifted back to the old gateway version per plan |

### 9.4. Verifying No Legacy Remains at Runtime

Acceptance criteria should include:

- No Ribbon/Hystrix/Zuul 1 artifacts on production `runtimeClasspath`, except explicitly approved and documented exceptions.
- No active legacy beans/auto-configurations.
- No legacy call sites on production code paths.
- No legacy properties loaded from config repos, env vars, or deployment manifests.
- Equivalent capabilities tested in LoadBalancer/CircuitBreaker/Gateway.
- Eureka Client/Server and OpenFeign continue functioning if still part of the architecture.
- Metrics, logs, dashboards, alerts, and runbooks updated to new names/semantics.
- Smoke/integration tests passed on a production-like image with a rollback plan.

## 10. Common Migration Pitfalls

| Symptom | Common cause | What to check |
|---|---|---|
| Removed Ribbon, but Feign cannot call service ID | Missing LoadBalancer integration or misconfigured Feign URL | Starters, `@FeignClient(name=...)`, runtime dependencies |
| Both Ribbon and LoadBalancer remain in graph | Legacy adapter pulls Ribbon transitively | `dependency:tree`/`dependencyInsight` and dependency path |
| Setting `spring.cloud.loadbalancer.ribbon.enabled=false` has no effect | Release train no longer has this transitional property | Check version-specific docs; remove Ribbon from classpath |
| Changed `ribbon.ReadTimeout` but timeout didn't change | New HTTP client does not bind Ribbon properties | Configure the new transport's timeout |
| Hystrix annotation no longer runs | Hystrix starter/code removed while call site wasn't migrated | Search `@HystrixCommand`, compile/test per module |
| Resilience4j opens breaker too early | Failure classification or minimum calls differ from Hystrix | Metrics, exception predicates, sliding window |
| Fallback returns 200 with bad data | Copied old fallback without checking semantics | Test UNKNOWN/degraded states, business contract |
| Gateway route returns 404 | Path predicate/StripPrefix/RewritePath misconfigured | Compare request path before/after filters |
| Gateway hangs under load | Blocking code running on reactive event loop | Thread dumps, Reactor/Netty metrics, offload blocking work |
| Old dashboard is empty | Runtime removed Hystrix stream | Migrate metrics and dashboards to Micrometer |
| Eureka removed by mistake | Mistook all of Spring Cloud Netflix for legacy | Keep discovery implementation still in use |
| `zuul.*` still appears after migration | Config Server/profile/Helm still has old properties | Scan all config sources and effective runtime env |



## 11. Mapping Legacy Capabilities to New Components

Spring Cloud publishes replacement directions at the **capability** level, which does not mean every property, class, and semantic translates verbatim.

| Legacy technology | Capability | Replacement direction | What must be redesigned |
|---|---|---|---|
| Ribbon | Client-side load balancing | Spring Cloud LoadBalancer | `IRule`/`ServerListFilter` become suppliers, choosers, request context, and policies |
| Hystrix | Circuit breaker, timeout, isolation, fallback | Spring Cloud CircuitBreaker with Resilience4j or suitable implementation | Thread isolation, bulkhead, timeout, retry, and fallback are not a single property |
| Hystrix Dashboard/Turbine | Dashboard and stream aggregation | Micrometer + monitoring backend | Metric names, labels, scrape/push, dashboards, and alert rules |
| Zuul 1 | Edge reverse proxy, routing, filtering | Spring Cloud Gateway | Route predicates, filters, ordering, request/response mutation, and reactive model |
| Archaius (if present) | External/dynamic configuration | Spring Boot external config + Spring Cloud Config | Property sources, refresh semantics, secret management |

### 11.1. Ribbon → Spring Cloud LoadBalancer

Common dependency:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
~~~

RestClient:

~~~java
@Bean
@LoadBalanced
RestClient.Builder loadBalancedRestClientBuilder() {
    return RestClient.builder();
}
~~~

WebClient:

~~~java
@Bean
@LoadBalanced
WebClient.Builder loadBalancedWebClientBuilder() {
    return WebClient.builder();
}
~~~

Feign using service ID:

~~~java
@FeignClient(name = "inventory-service")
public interface InventoryClient {
    @GetMapping("/stock/{sku}")
    StockView getStock(@PathVariable("sku") String sku);
}
~~~

Capabilities commonly mapped:

| Legacy Ribbon | Spring Cloud LoadBalancer |
|---|---|
| `IRule` | `ReactorServiceInstanceLoadBalancer` or suitable built-in implementation |
| `ServerList` | `ServiceInstanceListSupplier` combined with DiscoveryClient |
| `ServerListFilter` | Supplier decorators like zone, hint, health, subset, or custom filter |
| Zone-aware rule | Zone preference supplier and `zone` metadata |
| Weighted rule | `WeightedServiceInstanceListSupplier`/`WeightFunction` |
| Per-server retry | LoadBalancer retry + retry-aware supplier and HTTP client retry policy |
| Ribbon per-client configuration | `@LoadBalancerClient`/`@LoadBalancerClients` per service ID |

Spring Cloud LoadBalancer includes Round Robin and Random implementations, discovery-based suppliers, and custom configuration. Not every Ribbon rule has a single equivalent class. First describe the **business intent** (zone, weight, affinity, retry, capacity), then select the right supplier/chooser; only write a custom LoadBalancer when existing policies fall short.

One historical note: in certain Hoxton-era configurations, if both `spring-cloud-starter-loadbalancer` and Ribbon were present, Ribbon could be selected by default; older docs advised `spring.cloud.loadbalancer.ribbon.enabled=false` to switch to Spring Cloud LoadBalancer. That is a detail of an older release train, **not a universal migration property for all current versions**. For projects on an older train, check the exact reference version and runtime conditions; for newer projects, remove Ribbon instead of relying on an old toggle.

### 11.2. Hystrix → Spring Cloud CircuitBreaker + Resilience4j

Blocking dependency:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
</dependency>
~~~

Reactive dependency:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
</dependency>
~~~

Blocking API:

~~~java
@Service
class InventoryGateway {

    private final RestClient client;
    private final CircuitBreaker breaker;

    InventoryGateway(
            RestClient client,
            CircuitBreakerFactory<?, ?> factory) {
        this.client = client;
        this.breaker = factory.create("inventoryRead");
    }

    StockView getStock(String sku) {
        return breaker.run(
                () -> client.get()
                        .uri("http://inventory-service/stock/{sku}", sku)
                        .retrieve()
                        .body(StockView.class),
                cause -> new StockView(sku, null, true)
        );
    }
}
~~~

This is an illustrative skeleton: production must classify exceptions and only fall back when business semantics allow. Do not turn every 4xx or validation error into synthetic data.

Resilience4j configuration by breaker ID:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventoryRead:
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s

  timelimiter:
    instances:
      inventoryRead:
        timeoutDuration: 900ms
~~~

Meaning translation table:

| Legacy Hystrix | New design to evaluate |
|---|---|
| Command key / group key | Deliberate breaker ID and group ID |
| Circuit breaker state | Resilience4j CircuitBreaker state |
| Execution timeout | HTTP connect/read timeouts, deadlines, and TimeLimiter; define what each layer bounds |
| Thread isolation | Bulkhead/executor or semaphore; do not assume defaults match Hystrix |
| Semaphore isolation | Resilience4j semaphore bulkhead/concurrency limit when appropriate |
| Fallback method | Fallback function, `onErrorResume`, or error handling in adapter |
| Request cache/collapser | Dedicated cache/batching design; no automatic 1:1 translation |
| Hystrix Dashboard/Turbine | Actuator/Micrometer metrics + Prometheus/monitoring backend |

Do not rename `hystrix.command.default.execution.isolation.thread.timeoutInMilliseconds` to a similar Resilience4j key and consider migration complete. You must decide HTTP transport timeouts, TimeLimiter, bulkhead, and retry budgets separately. In particular, TimeLimiter does not guarantee a backend transaction rolled back when the caller timed out.

### 11.3. Zuul 1 → Spring Cloud Gateway

Zuul 1 is a server/edge reverse proxy/gateway. Spring Cloud Gateway is the replacement for routing HTTP requests and applying predicates and filters. It is not the same thing as a **client-side load balancer**: the gateway handles incoming edge requests, whereas LoadBalancer selects instances for HTTP clients inside an application. The gateway can use LoadBalancer when a route has a URI like `lb://inventory-service` and the corresponding dependency/integration is configured.

Illustrative Spring Cloud Gateway route:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: inventory-route
          uri: lb://inventory-service
          predicates:
            - Path=/api/inventory/**
          filters:
            - StripPrefix=2
~~~

The example above assumes the Gateway app has LoadBalancer integration and discovery/service ID `inventory-service`. Verify the number of segments stripped by `StripPrefix` against the actual path contract before shifting traffic.

| Legacy Zuul 1 | Spring Cloud Gateway redesign needed |
|---|---|
| `zuul.routes.inventory.path` | Route predicate such as `Path=/api/inventory/**` |
| `serviceId`/Ribbon route | `uri: lb://inventory-service` if routed via LoadBalancer |
| Zuul pre/post/route/error filters | `GlobalFilter`, `GatewayFilter`, and filter factories |
| `zuul.prefix` | Path predicate/rewrite/strip-prefix per contract |
| Zuul sensitive headers | Header filtering and security policy at the gateway |
| Zuul retry | Retry filter or bounded retry layer |
| Hystrix Zuul filter | CircuitBreaker GatewayFilter with a supported implementation |

Do not convert `ZuulFilter` code into `GlobalFilter` just by renaming the class. Lifecycle, ordering, request exchange, reactive execution, and error handling differ. Heavy blocking filters can block the event loop in WebFlux Gateway; redesign and concurrency-test them.

### 11.4. Hystrix Dashboard/Turbine → Modern Observability

Hystrix Dashboard/Turbine typically displayed command metrics and streams in their own format. When moving to Resilience4j/Spring Cloud CircuitBreaker, enable Actuator and appropriate Micrometer integration, then export to your monitoring backend (Prometheus, Grafana, or your organization's platform).

Example of an additional metrics dependency when using Resilience4j:

~~~xml
<dependency>
    <groupId>io.github.resilience4j</groupId>
    <artifactId>resilience4j-micrometer</artifactId>
</dependency>
~~~

Combine `spring-boot-starter-actuator` with a metrics registry/exporter. New dashboards must be built around the new metric names, tags, and SLOs; do not assume Hystrix command keys automatically become Resilience4j breaker IDs or that old metric series retain meaning.


## 12. Checking the Release Train Before Deciding to Remove or Replace

Spring Cloud documentation spans multiple generations, and legacy pages can still appear in search results. For example, Spring Cloud Netflix 2.2.x docs still describe Ribbon, Hystrix, and Zuul; current Spring Cloud Netflix docs focus on Eureka. Do not take examples from the 2.2.x reference to configure a newer Boot/Cloud app without checking compatibility.

Version verification procedure:

1. Obtain the effective Spring Boot version from parent/plugin/dependency management.
2. Obtain the effective Spring Cloud BOM/release train version from the effective POM or Gradle platform.
3. Open the Spring Cloud compatibility table to confirm the supported Boot/Cloud pair.
4. Use reference docs for the exact release train when verifying properties, starters, and classes.
5. Use current docs to understand evolution/replacement direction, without backporting new properties onto old versions.
6. Check deprecation/removal notes in the release notes of the trains your project will traverse.

A property may exist in Hoxton yet no longer be read in the current release train. Conversely, a similarly named starter may have been split into modules. **A YAML property name is not a compatibility contract**; classpath, binders, and runtime behavior are the proof.

### Decision Table by Version Scope

| Context | Action |
|---|---|
| App on older train where Ribbon is still the active implementation | Plan migration to LoadBalancer; do not merely delete the dependency while call sites still depend on Ribbon APIs |
| App already uses LoadBalancer, but transitive Ribbon remains | Identify the pulling dependency, swap the adapter, or exclude after testing |
| App uses Hystrix directly | Migrate commands/fallbacks/isolation per operation; choose Spring Cloud CircuitBreaker and a compatible implementation |
| Gateway still has `@EnableZuulProxy` | Migrate routes/filters to Spring Cloud Gateway, test behavior, and roll out |
| Only Eureka Client/Server remain | Keep if discovery architecture still uses them; do not remove just because they belong to Spring Cloud Netflix |
| Only unbound legacy docs/config remain | Confirm config sources, then clean up config/comments/docs to prevent operational confusion |

## 13. Lab Exercise: Inventorying a Service Before and After Migration

Suppose module `order-service` has a POM, Java source, and multiple YAML profiles. Perform this on a dedicated working branch and save results in an issue/PR; no production changes need to run to complete the inventory.

### 13.1. Scan Dependencies

~~~powershell
.\mvnw.cmd dependency:tree -Dverbose
.\mvnw.cmd help:effective-pom -Doutput=target/effective-pom.xml
~~~

Filter the output to find:

- Ribbon starter/core and which dependency pulls it in.
- Hystrix starter/core/javanica/metrics.
- Zuul starter/core.
- Spring Cloud LoadBalancer, CircuitBreaker, Gateway, and Eureka currently in use.
- Version conflicts/omitted nodes from dependency mediation.

### 13.2. Scan Source and Config

~~~powershell
rg -n -i --hidden -g '!**/.git/**' -g '!**/target/**' -g '!**/build/**' 'RibbonClient|IRule|ILoadBalancer|HystrixCommand|EnableHystrix|HystrixFeign|EnableZuulProxy|ZuulFilter|ribbon\.|hystrix\.|zuul\.' .
~~~

Classify each match as active, transitive, config-only, code-only, or historical. For each match, record:

- File/line and module.
- Profiles/environments that load that file.
- Dependency path and runtime scope.
- Whether the bean/auto-configuration is created.
- Which requests/routes/operations are affected.
- Planned replacement and tests to add.

### 13.3. Create a Migration Record

Report template before editing:

~~~text
Module: order-service
Spring Boot / Cloud train: <confirmed versions>
Ribbon:
  dependency path: legacy-http-adapter -> spring-cloud-starter-netflix-ribbon
  source: InventoryRibbonConfiguration / IRule
  runtime: active on inventory-service
  replacement: ServiceInstanceListSupplier + LoadBalancer
Hystrix:
  dependency path: spring-cloud-starter-netflix-hystrix
  source: @HystrixCommand on InventoryGateway
  runtime: active
  replacement: Spring Cloud CircuitBreaker + Resilience4j
Zuul:
  dependency path: none
  source/config: legacy migration documentation only
  classification: historical
Eureka:
  dependency path: spring-cloud-starter-netflix-eureka-client
  usage: discovery registration
  decision: keep
~~~

This is an **illustrative template**, not the scan output of the current repository. Explicitly mark UNKNOWN items and ask owners to confirm instead of marking them migrated yourself.

### 13.4. Post-Migration Sign-Off

Re-run the exact dependency/source/config scan commands. Compare before/after reports:

- Dependency graph: no legacy artifacts left on production runtime paths.
- Source: no active legacy call sites/annotations/classes.
- Configuration: no legacy properties loaded from files, environment, or Config Server.
- Runtime: no active legacy beans/routes/commands.
- Replacement: LoadBalancer/CircuitBreaker/Gateway have tests and metrics.
- Discovery: Eureka (if still used) continues registering and resolving service IDs properly.
- Rollout: canary/smoke tests and rollback path verified.

## 14. Inventory and Migration Completion Checklist

### Identification

- [ ] Identified module/service, Spring Boot version, and Spring Cloud release train.
- [ ] Ran Maven dependency tree or Gradle dependency insight for runtime configuration.
- [ ] Traced transitive dependencies back to the pulling module.
- [ ] Searched for Ribbon imports, annotations, rules, and `*.ribbon.*` properties.
- [ ] Searched for Hystrix commands, Feign integration, dashboard/stream, and `hystrix.*` properties.
- [ ] Searched for Zuul annotations, filters, route configs, and `zuul.*` properties.
- [ ] Scanned profiles, Config Server, environment variables, Helm/Kubernetes, and pipeline configs.
- [ ] Distinguished active code/config from historical/test-only/false positives.
- [ ] Retained Eureka/OpenFeign/LoadBalancer/Resilience4j/Gateway where they are active components.

### Migration

- [ ] Documented legacy behavior by service ID, operation, route, and policy.
- [ ] Migrated Ribbon by intent to Spring Cloud LoadBalancer.
- [ ] Migrated Hystrix per operation to CircuitBreaker/Resilience4j or a suitable implementation.
- [ ] Redesigned Zuul routes/filters on Spring Cloud Gateway.
- [ ] Evaluated timeouts, retries, bulkheads, fallbacks, and idempotency separately.
- [ ] Updated metrics/dashboards/alerts/runbooks to the new semantics.
- [ ] Removed legacy dependencies and properties from all config sources.
- [ ] Re-verified dependency graph/runtime conditions after removal.
- [ ] Ran integration tests across discovery, HTTP clients, and the gateway.
- [ ] Established a canary/rollback plan and obtained owner sign-off.

## References

- [Spring Cloud Greenwich RC1 — Modules entering maintenance mode and replacements](https://spring.io/blog/2018/12/12/spring-cloud-greenwich-rc1-available-now/): historical announcement on maintenance mode and replacement directions for Ribbon, Hystrix, and Zuul 1.
- [Spring Cloud Netflix 2.2.x Reference](https://docs.spring.io/spring-cloud-netflix/docs/2.2.x/reference/html/): legacy documentation for identifying Ribbon/Hystrix/Zuul APIs, starters, properties, and behavior in older projects.
- [Spring Cloud Netflix — Current Reference](https://docs.spring.io/spring-cloud-netflix/reference/): current scope of Spring Cloud Netflix, including Eureka.
- [Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): `ReactiveLoadBalancer`, `ServiceInstanceListSupplier`, Round Robin/Random, custom client configuration, and HTTP client integrations.
- [Spring Cloud CircuitBreaker](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-circuitbreaker.html): `CircuitBreakerFactory` API, implementation abstraction, and customizers.
- [Spring Cloud CircuitBreaker — Resilience4j](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html): blocking/reactive starters, configuration, TimeLimiter, bulkheads, and metrics.
- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/): routes, predicates, filters, and gateway runtime.
- [Spring Cloud Project](https://spring.io/projects/spring-cloud/): release trains and compatibility information.

**Conclusion:** identifying residual Ribbon, Hystrix, and Zuul must rely on **dependency graph + source code + effective configuration + runtime behavior**. Once active capabilities are identified, migrate by intent to Spring Cloud LoadBalancer, Spring Cloud CircuitBreaker/Resilience4j, and Spring Cloud Gateway. Finally, re-check the classpath, beans, routes, profiles, and metrics to ensure the system has fully moved to the new implementations while keeping active components like Eureka or OpenFeign when the architecture still requires them.


