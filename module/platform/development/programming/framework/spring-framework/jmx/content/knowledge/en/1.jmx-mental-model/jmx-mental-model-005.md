# Distinguishing MBean, Spring bean, endpoint, and application metric

## 1. Goal and big picture

When building a Spring Framework application, four concepts—**MBean**, **Spring bean**, **endpoint**, and **application metric**—often appear together in operational documentation. They can represent information about the same component, but they do not live at the same conceptual layer.

After this lesson, you can:
- Correctly identify whether the object being discussed is an internal component, a management interface, a network access point, or a measurement.
- Explain the relationship between the Spring IoC container, JMX MBeanServer, HTTP endpoints, and metrics systems.
- Recognize cases where a Spring bean is exported as an MBean or supplies data to an endpoint/metric.
- Choose the appropriate mechanism when configuring, diagnosing, monitoring, or automating operations.

**Mental model:** A Spring bean answers *"which object is managed by the application?"*; an MBean answers *"which managed object does JMX allow observing or operating on?"*; an endpoint answers *"through which address and protocol do callers access a function/information?"*; a metric answers *"which quantity is measured, with what name, value, and labels?"*

A single component can participate in all four roles simultaneously without making the four concepts synonymous.

## 2. The four concepts and their boundaries

| Concept | Nature | Who manages or provides it? | Common access methods | Examples |
|---|---|---|---|---|
| **Spring bean** | Instance of an object registered in the Spring IoC container | \`ApplicationContext\`/\`BeanFactory\` | Dependency injection, retrieving beans from the context | \`OrderService\`, \`DataSource\` |
| **JMX MBean** | Managed object with attributes, operations, and optionally notifications, registered under an \`ObjectName\` | Platform/JMX \`MBeanServer\` | JMX clients such as JConsole, VisualVM, Java Management API | \`com.example:type=Queue,name=Orders\` |
| **Endpoint** | Access point for a function or resource over a published protocol/path | Web framework, management framework, or corresponding adapter | HTTP \`GET /actuator/health\`, \`GET /orders\`; also management endpoints via JMX | Health endpoint, REST endpoint |
| **Metric** | Measurement with a name, type, value, and optionally tags/labels | Meter registry, instrumentation, monitoring backend | Prometheus scrape, Micrometer API, metrics endpoint, dashboard | \`http.server.requests\`, number of pending tasks |

**Note on the word "endpoint":** In the context of Spring Boot Actuator, an *actuator endpoint* is an abstract management capability that can be exposed over **HTTP or JMX**. In ordinary web APIs, an endpoint usually refers to a URL/route. Therefore, "endpoint" does not automatically mean HTTP, and "MBean" is not synonymous with a URL.

### 2.1. Spring bean: object in the container

A Spring bean is created and managed by the Spring IoC container. The container handles dependency injection, scope lifetime, lifecycle callbacks, and object configuration.

\`\`\`java
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    public long countPendingOrders() {
        // Assume business data is queried here.
        return 42;
    }
}
\`\`\`

\`OrderService\` is a Spring bean when detected and registered by the container. By default, it **does not automatically become an MBean**, **does not automatically get an HTTP endpoint**, and a method returning a number **is not automatically a metric**.

### 2.2. MBean: object in the JMX management system

Java Management Extensions (JMX) provides a standardized way to expose Java management information. An MBean can provide:

- **Attribute:** readable state and, if designed to allow it, writable state.
- **Operation:** management action invocable from a JMX client.
- **Notification:** management event emitted by the MBean, when supported.

An MBean is registered in an \`MBeanServer\` under an \`ObjectName\`; this name serves management identification and differs from the bean name in the Spring container. JMX can work within the same JVM; remote access is only available with appropriate configuration and access permissions.

For example, having a \`PendingCount\` attribute and a \`resetStatistics()\` operation on a queue-monitoring MBean does not automatically give the application an HTTP \`/queue\` path.

### 2.3. Endpoint: published entry point

An HTTP endpoint is defined by a method, URL, and request/response contract. For example:

\`\`\`java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class QueueController {
    private final OrderService orderService;

    public QueueController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/api/orders/pending-count")
    public long pendingCount() {
        return orderService.countPendingOrders();
    }
}
\`\`\`

This is an HTTP endpoint using a Spring bean; it does not thereby become an MBean. Exposing URLs publicly, authentication/authorization, and network exposure must be evaluated independently.

With Spring Boot Actuator, \`health\`, \`info\`, \`metrics\`, and \`prometheus\` are examples of management endpoints when the right dependencies and configuration are present. Some actuator endpoints can be exposed via HTTP, JMX, or both. You should not assume every endpoint is enabled by default.

### 2.4. Metric: measured quantity

A metric records **values over time** to observe trends, rates, latencies, or counts.

Common types:

- **Counter:** cumulative count per event, e.g., total processed tasks.
- **Gauge:** value at sampling time, e.g., number of pending tasks.
- **Timer:** duration distribution and usually invocation count as well.
- **Distribution summary:** distribution of measured values that are not durations.

In the Spring ecosystem, Micrometer is the instrumentation API commonly used by Spring Boot Actuator; meters are registered into a \`MeterRegistry\`. Metric names in Micrometer may be transformed according to the export system's conventions (e.g., Prometheus), so you should not assume internal names and exported names are always identical.

\`\`\`java
import io.micrometer.core.instrument.MeterRegistry;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class QueueMetrics {
    private final AtomicInteger pending = new AtomicInteger();

    public QueueMetrics(MeterRegistry registry) {
        registry.gauge("orders.pending", pending);
    }

    public void setPending(int count) {
        pending.set(count);
    }
}
\`\`\`

This example illustrates a **gauge** reflecting an updated state. \`QueueMetrics\` is a Spring bean if component-scanned; \`orders.pending\` is a metric; by themselves, neither creates a JMX MBean or an HTTP URL. In a real system, gauge state should be backed by a data source with a reliable current value.

## 3. Relationship map: the same system, multiple view layers

\`\`\`text
                +-------------------------------+
                | Spring ApplicationContext     |
                |  OrderService (Spring bean)   |
                +-------------------------------+
                    |          |           |
        calls logic |          | reads data| used for management
                    v          v           v
        HTTP Controller   MeterRegistry   MBean exporter
        /api/...          orders.pending  ObjectName
             |                 |               |
         HTTP client      monitoring backend  JMX client
                              ^
                              |
                    /actuator/prometheus
                    (if enabled and exposed)
\`\`\`

This is a diagram of **integration possibilities**, not a mandatory pipeline. An application may have only Spring beans, or have metrics without custom MBeans. Data from the same queue can be used to return an HTTP response, update a metric, and provide a JMX attribute.

Distinguish three kinds of names:

1. **Bean name** managed by the Spring container, e.g., \`orderService\`.
2. **JMX ObjectName** such as \`com.example.monitoring:type=Queue,name=Orders\`.
3. **Metric name** such as \`orders.pending\`, plus labels/tags if any.

A URL \`/actuator/metrics/orders.pending\` (if exposed) contains the metric name for querying, but **the URL is not the metric**. It is merely a vehicle for reading metric-related information.

## 4. Spring JMX example: turning a Spring bean into an MBean when needed

Spring Framework supports JMX integration through annotations and \`MBeanExporter\`. This snippet illustrates the principle without requiring a web server:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.monitoring:type=Queue,name=Orders",
    description = "Manage order queue"
)
public class OrderQueueMonitor {
    private volatile int pendingCount;

    @ManagedAttribute(description = "Number of pending orders")
    public int getPendingCount() {
        return pendingCount;
    }

    @ManagedOperation(description = "Reset simulated counter")
    public void reset() {
        pendingCount = 0;
    }

    public void updatePendingCount(int value) {
        pendingCount = value;
    }
}
\`\`\`

An annotation-export mechanism needs to be configured, for example:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxConfig {
    @Bean
    public MBeanExporter mBeanExporter() {
        AnnotationJmxAttributeSource source = new AnnotationJmxAttributeSource();

        MetadataMBeanInfoAssembler assembler = new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);

        MetadataNamingStrategy naming = new MetadataNamingStrategy();
        naming.setAttributeSource(source);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        return exporter;
    }
}
\`\`\`

When the exporter runs, the Spring bean is registered as an MBean in the appropriate \`MBeanServer\`. JConsole can browse the \`ObjectName\` to read \`PendingCount\` and invoke \`reset\`, depending on access permissions. Annotations provide management metadata; **\`@Component\` alone does not export an MBean**.

A Spring Boot project may provide JMX auto-configuration that differs from plain Spring Framework configuration. In Boot, enabling JMX bean export is controlled by settings such as \`spring.jmx.enabled\`; do not equate it with exposing Actuator JMX endpoints. When using auto-configuration, avoid registering a duplicate exporter. For Spring Framework without Boot, the example above illustrates declaring the exporter explicitly.

**Operational note:** \`reset()\` is a state-mutating operation. If the state is used for real business logic, you must consider synchronized access, consistency, authorization, and the consequences of the action; a management operation is not automatically safe just because it lives in JMX.

## 5. Distinction table by practical question

| Question | Concept to start from | Reason |
|---|---|---|
| "Which service is this object injected into?" | Spring bean | Dependency relationships belong to the IoC container |
| "I want to inspect JVM attributes with JConsole?" | MBean | JMX exposes managed objects |
| "Get the result from \`GET /api/orders\`?" | HTTP endpoint | A route handling requests/responses |
| "Did the HTTP error rate rise over the last 15 minutes?" | Metric | Requires time-series measurements and aggregation |
| "Is the application still healthy?" | Health endpoint | Returns an operational status assessment |
| "Allow operators to trigger a cache refresh?" | MBean operation or protected management endpoint | Requires an explicit, controlled operation interface |
| "How many connections are currently open?" | Gauge, sometimes also an MBean attribute | An instantaneous measurement; JMX can provide the same info |
| "Is the metrics endpoint itself a metric?" | No | An endpoint serves retrieval of a set of metrics or measurements |

A value of "42 pending orders" can appear in an MBean attribute, an HTTP response, and a metric gauge. **Overlapping information semantics do not unify access interfaces, lifecycles, or security boundaries.**

## 6. Relationship between Spring JMX, Spring Boot Actuator, and Micrometer

Do not merge these three names into a single feature:

- **Spring JMX integration** supports exporting Spring-managed objects as JMX MBeans and mapping attributes/operations/notifications.
- **Spring Boot Actuator** provides management endpoints and mechanisms to expose them over supported technologies, including HTTP and JMX depending on configuration.
- **Micrometer** collects metrics via meters/registries and integrates with monitoring systems. Spring Boot Actuator uses Micrometer for standard metrics infrastructure.

You can visualize it as:

\`\`\`text
Spring beans  --->  Spring JMX exporter  ---> JMX MBeanServer
       |
       +------->  Web/Actuator endpoints ---> HTTP or JMX exposure
       |
       +------->  Micrometer registry ----> Prometheus/monitoring
                              ^
                         application metrics
\`\`\`

An Actuator \`metrics\` endpoint does not replace the Micrometer registry; it is a **way to query** the metrics already provided by the registry. Similarly, a JMX MBean does not appear in Prometheus by default, although a bridge tool can be used in an appropriate architecture.

### Illustrative scenario

Suppose an application processes orders and operators need three capabilities:

1. **Quickly inspect status via JConsole:** create a custom MBean with a \`PendingCount\` attribute.
2. **Build a pending-orders dashboard and alerts:** record \`orders.pending\` with a gauge and configure the monitoring backend.
3. **Let another system query the pending-orders count:** publish an HTTP endpoint with a response contract and security.

All three capabilities can call the same service or state source. Which one you choose depends on the consumer, access frequency, and integration protocol; having JMX in the system does not mean every client must use JMX.

## 7. Common misconceptions

**Misconception 1: "Every Spring bean is an MBean."**  
False. A Spring bean belongs to the container; to become an MBean, the object must be exported/registered via an appropriate JMX mechanism. Even a bean with JMX annotations without an exporter is not guaranteed to be registered.

**Misconception 2: "An MBean and a Spring bean are definitely two separate instances."**  
Not necessarily. A Spring exporter can expose the original bean instance through an MBean adapter/metadata. What matters is the two distinct **management roles**, not asserting the instance count.

**Misconception 3: "An endpoint is always an HTTP URL."**  
False in the context of Actuator. A logical endpoint can be exposed over JMX. A standard HTTP endpoint is indeed a network route.

**Misconception 4: "With \`@RestController\`, the endpoint is a metric."**  
False. A response containing a number is not automatically measurement data managed by a registry. A metric also has a measurement type, tags, a sampling/aggregation lifecycle, and historical observability in a backend.

**Misconception 5: "Gauges and counters are interchangeable."**  
False. A pending task count can go up and down, so it fits a gauge; a total completed task count is typically a monotonically increasing counter. Choosing the wrong type breaks dashboards and query semantics.

**Misconception 6: "Enabling Actuator or JMX means exposing everything publicly."**  
False. Endpoints and JMX operations can leak data or allow controlling the application. Expose only what is necessary, and apply appropriate authentication/authorization and network restrictions.

**Misconception 7: "Metrics always store history inside the application."**  
No. The registry/instrumentation supplies measurements; retention, long-term aggregation, querying, and alerting depend on the configured monitoring backend.

## 8. Guide to choosing a solution

When faced with an application observability or control requirement, ask in order:

1. **Need an object serving internal business logic?** Organize it as a Spring bean and inject it via the container.
2. **Need management actions from JMX/Java tools?** Consider an MBean with clear attributes and operations, limiting dangerous actions.
3. **Need remote clients calling via an API or health check?** Design an appropriate endpoint with authentication, authorization, and exposure management.
4. **Need charts, alerts, or comparisons over time?** Instrument the right metric type (counter/gauge/timer) with reasonable-cardinality labels and a monitoring backend.
5. **Need all three ways of observing?** Share a single reliable source of truth for state; avoid letting each adapter maintain its own separate counter that drifts out of sync.

### Security and operability

- State-changing MBean operations must be treated as sensitive administrative functions; restrict who has permission to invoke them.
- Do not open remote JMX by default just for debugging convenience. If needed, configure networking, authentication, and channel protection for the deployment environment.
- Health/metrics endpoints must not inadvertently leak secrets, internal details, or unusually high label counts.
- Instrumentation should avoid creating tags from unbounded values such as user IDs, request IDs, or dynamic high-cardinality URLs; this can increase storage costs and monitoring overhead.

## 9. Knowledge self-check

**Question 1.** \`PaymentService\` has \`@Service\`. Is it already an MBean?  
**Answer:** Not necessarily; \`@Service\` registers a Spring bean, while JMX requires a separate export/registration step.

**Question 2.** \`GET /actuator/metrics\` returns a list of metric names. Is this URL itself a metric?  
**Answer:** No. It is an endpoint used to query metrics (when exposed).

**Question 3.** Which metric type fits "number of currently active connections"?  
**Answer:** Gauge, because the quantity increases and decreases with the current state.

**Question 4.** A custom MBean exposes a \`clearCache()\` operation. Can it be treated as a public API?  
**Answer:** No. It is a management operation requiring access restrictions and side-effect evaluation.

**Question 5.** An application wants to compare API p95 latency over time. Is creating only an MBean attribute enough?  
**Answer:** Usually not. You need to instrument durations with an appropriate timer/distribution, export them, and aggregate them in a monitoring backend to query percentiles over time.

## 10. Key takeaways

- **Spring bean** is an internal object managed by the Spring container.
- **MBean** is a managed object registered with a JMX \`MBeanServer\` and identified by an \`ObjectName\`.
- **Endpoint** is an access interface for functionality/information; an actuator endpoint can be exposed via HTTP or JMX.
- **Metric** is measurement data with semantics and measurement type, used for observation/aggregation; it may be presented by an endpoint or MBean but is not identical to those interfaces.
- The same state data can serve JMX, APIs, and monitoring. Choose the mechanism based on access purpose, measurement semantics, and security boundaries.

### References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Boot Reference — Monitoring and Management over JMX: https://docs.spring.io/spring-boot/reference/actuator/jmx.html
- Spring Boot Reference — Endpoints: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Boot Reference — Metrics: https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- Micrometer — Concepts: https://docs.micrometer.io/micrometer/reference/concepts.html
- Oracle Java Management Extensions (JMX) documentation: https://docs.oracle.com/javase/tutorial/jmx/
