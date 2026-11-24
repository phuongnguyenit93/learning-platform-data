# Reading MBeans with a Script or Intermediary Web API

> **Topic:** Spring Framework JMX  
> **Knowledge Group:** Observability and Automation  
> **Lesson:** Reading MBeans with a Script or Intermediary Web API

## 1. Objectives

When periodic monitoring of Spring JMX is needed, operators cannot always open JConsole. A script can query \`MBeanServerConnection\` and an intermediary Web API can provide selected management metrics for dashboards or automation. However, it is important to distinguish **reading state** from **exposing full JMX privileges over the network**.

After this lesson, you will be able to:

- Understand how to use \`ObjectName\`, \`MBeanInfo\`, \`getAttribute\`, and \`queryNames\` in JMX.
- Write a script/CLI-style Java program that reads specified attributes on an MBean.
- Design a read-only intermediary Web API that maps JMX results into a JSON DTO.
- Distinguish between a local \`MBeanServer\` and a remote \`MBeanServerConnection\`.
- Handle JMX data types such as primitives, \`CompositeData\`, \`TabularData\`, \`ObjectName\`, and arrays.
- Protect the intermediary API with an ObjectName/attribute allowlist, authentication, authorization, timeouts, and load limits.
- Know when to use a metrics backend/Actuator instead of polling JMX directly.

## 2. Why Do We Need a Script or Intermediary API?

JConsole is suitable for inspecting state manually, but operational systems typically need to:

- Collect values periodically.
- Check a metric inside a runbook.
- Surface JVM/Spring state onto a dashboard.
- Aggregate data from multiple instances.
- Alert when queue depth, error count, or thread pool saturation crosses a threshold.
- Provide a stable interface for tools that do not understand JMX.

Model:

\`\`\`text
Spring application
       |
       v
MBeanExporter -> MBeanServer
                      |
              MBeanServerConnection
                      |
          +-----------+-------------+
          |                         |
       Java CLI                  Read-only API
          |                         |
    stdout/JSON             HTTP JSON response
          |                         |
      Runbook                   Dashboard
\`\`\`

**Do not build an API like \`/jmx/invoke?operation=...\` for arbitrary ObjectNames.** It can become a bypass around governance policies, allowing remote clients to invoke operations with side effects.

## 3. Components to Distinguish

| Component | Role |
|---|---|
| Spring \`@ManagedResource\` | Marks a bean for management exposure |
| \`MBeanExporter\` | Registers beans into the MBeanServer |
| \`MBeanServer\` | MBean registry inside the JVM |
| \`MBeanServerConnection\` | API for reading/writing/invoking local or remote MBeans |
| \`ObjectName\` | MBean identity within a server |
| \`MBeanInfo\` | Metadata for attributes/operations/notifications |
| \`JMXConnector\` | Remote JMX connection |
| CLI/script | Client calling the JMX API according to a script/workflow |
| Intermediary Web API | Layer that converts JMX data into policy-enforced HTTP responses |
| Metrics backend | Storage for time series, aggregation, and alerting |

An \`ObjectName\` only has meaning within a single \`MBeanServer\`. Two different JVMs can contain the same ObjectName with different values.

## 4. Example MBean in Spring

\`\`\`java
package example.monitoring;

import java.util.concurrent.atomic.AtomicLong;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "app.management:type=Queue,name=orders",
    description = "Orders queue diagnostics"
)
public class OrdersQueueMonitor {

    private final AtomicLong processed = new AtomicLong();

    @ManagedAttribute(description = "Pending jobs")
    public int getPendingJobs() {
        // In a real application: read from the queue adapter.
        return 12;
    }

    @ManagedAttribute(description = "Processed job count")
    public long getProcessedJobs() {
        return processed.get();
    }

    public void recordProcessed() {
        processed.incrementAndGet();
    }
}
\`\`\`

Export configuration:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
\`\`\`

Two expected management attributes:

\`\`\`text
PendingJobs: int (read-only)
ProcessedJobs: long (read-only)
\`\`\`

When the exporter registers successfully and the client queries the right server, values can be retrieved via \`getAttribute\`. If using Spring Boot, check JMX auto-configuration and avoid creating an unintended duplicate exporter.

## 5. Identify the Right MBeanServer First

A common mistake: the application exports to a custom server while the script reads the platform MBeanServer.

Local platform server:

\`\`\`java
MBeanServerConnection connection =
    ManagementFactory.getPlatformMBeanServer();
\`\`\`

If the exporter is configured with:

\`\`\`java
exporter.setServer(customMBeanServer);
\`\`\`

then a script running in the same JVM must read from \`customMBeanServer\` or a connector bound to that server.

Check registration:

\`\`\`java
ObjectName name = new ObjectName(
    "app.management:type=Queue,name=orders"
);

System.out.println(connection.isRegistered(name));
\`\`\`

\`false\` does not prove the exporter failed to run: the ObjectName, registry, or query timing may differ.

## 6. Using MBeanInfo to Discover Read-Only APIs

\`\`\`java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

MBeanInfo info = connection.getMBeanInfo(name);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf(
        "%s type=%s readable=%s writable=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}
\`\`\`

For a reading script, filter with:

\`\`\`java
if (attr.isReadable()) {
    // Attribute declared as readable by metadata.
}
\`\`\`

However, **readable** does not mean non-sensitive data. \`SystemProperties\`, environment data, or custom attributes may contain secrets. An intermediary Web API must maintain its own allowlist and not automatically expose all readable attributes.

## 7. Java CLI Script to Read an MBean

A small CLI can take a fixed ObjectName configuration:

\`\`\`java
package example.monitoring;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class LocalJmxRead {

    public static void main(String[] args) throws Exception {
        MBeanServerConnection connection =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "app.management:type=Queue,name=orders"
        );

        if (!connection.isRegistered(name)) {
            System.err.println("MBean missing: " + name);
            System.exit(2);
        }

        Object pending =
            connection.getAttribute(name, "PendingJobs");

        Object processed =
            connection.getAttribute(name, "ProcessedJobs");

        System.out.println(
            "pendingJobs=" + pending
        );
        System.out.println(
            "processedJobs=" + processed
        );
    }
}
\`\`\`

**Important:** this CLI snippet only reads MBeans from **the very JVM running the CLI program**. If run as a separate Java process, \`ManagementFactory.getPlatformMBeanServer()\` points to the CLI process's MBeanServer, not another application JVM.

To read another JVM, use a remote connector or place the reader inside the application process and export data through an API/metrics integration.

## 8. Script Connecting to Remote JMX

\`\`\`java
import java.util.HashMap;
import java.util.Map;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class RemoteJmxRead {

    public static void main(String[] args) throws Exception {
        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi:///jndi/rmi://" +
            "jmx.internal.example:9010/jmxrmi"
        );

        Map<String, Object> environment = new HashMap<>();

        // Provide credentials and TLS configuration via the environment's
        // secret/truststore management mechanism.
        // Do not hardcode passwords in source code.

        try (JMXConnector connector =
                 JMXConnectorFactory.connect(url, environment)) {

            MBeanServerConnection connection =
                connector.getMBeanServerConnection();

            ObjectName name = new ObjectName(
                "app.management:type=Queue,name=orders"
            );

            System.out.println(
                connection.getAttribute(name, "PendingJobs")
            );
        }
    }
}
\`\`\`

The snippet above assumes the server connector and network are already set up. In production, appropriate authentication, authorization, TLS, timeouts, and network isolation must be used. \`@EnableMBeanExport\` does not open a remote JMX connector on its own.

JMX RMI may use a registry port and a separate RMI endpoint port. When firewalls/NAT are involved, you must also check the endpoint advertised by the RMI stub.

## 9. Client Credentials Example

With a connector supporting username/password authentication via the appropriate mechanism:

\`\`\`java
Map<String, Object> environment = new HashMap<>();

environment.put(
    JMXConnector.CREDENTIALS,
    new String[] { username, password }
);

JMXConnector connector =
    JMXConnectorFactory.connect(url, environment);
\`\`\`

\`username\` and \`password\` must come from a protected secret source, not constants in a Java file or command-line arguments that get logged. Depending on the connector/JDK, TLS configuration may require appropriate truststore/system properties or a socket factory.

Avoid granting read-write accounts to read-only scripts. However, per-MBean/operation authorization granularity depends on the JMX connector/access control implementation and is not guaranteed merely by calling \`getAttribute\`.

## 10. Do Not Use MBeanServerConnection as an Unrestricted API

An \`MBeanServerConnection\` interface has the methods:

\`\`\`java
connection.getAttribute(...);
connection.getAttributes(...);
connection.queryNames(...);
connection.invoke(...);
connection.setAttribute(...);
\`\`\`

If the goal is observability, the program should only use:

- \`queryNames\` with a restricted pattern.
- \`getMBeanInfo\` to inspect metadata when needed.
- \`getAttribute\`/\`getAttributes\` with an allowlist.
- Optionally \`getMBeanCount\` or approved system information.

Do not let users arbitrarily call \`invoke\`, \`setAttribute\`, or \`unregisterMBean\` through an HTTP endpoint just because the JMX API supports them.

## 11. Reading Multiple Attributes in a Single Call

\`getAttributes\` can reduce the number of round trips, especially with a remote connector:

\`\`\`java
import javax.management.Attribute;
import javax.management.AttributeList;

AttributeList result = connection.getAttributes(
    name,
    new String[] {
        "PendingJobs",
        "ProcessedJobs"
    }
);

for (Object entry : result) {
    Attribute attr = (Attribute) entry;
    System.out.println(
        attr.getName() + "=" + attr.getValue()
    );
}
\`\`\`

The result should not be assumed to always include every requested name. Depending on the MBean and errors, \`getAttributes\` may return a list containing only the attributes that were read successfully.

In observability code, compare the received names against the expected list and report a \`PARTIAL\` status if any attribute is missing, rather than filling in zero as a default result.

## 12. Reading MBeans by ObjectName Pattern

\`\`\`java
ObjectName pattern = new ObjectName(
    "app.management:type=Queue,*"
);

Set<ObjectName> queues =
    connection.queryNames(pattern, null);

for (ObjectName objectName : queues) {
    System.out.println(objectName.getCanonicalName());
}
\`\`\`

A pattern is only appropriate when you genuinely want to discover matching instances. When designing a Web API, restrict the domain and key properties to prevent callers from discovering unrelated MBeans.

\`queryNames\` returns names at the time of the query. An MBean may unregister afterward; \`getAttribute\` can still throw \`InstanceNotFoundException\`.

## 13. Converting JMX Data to JSON

HTTP JSON clients usually do not understand Java JMX types such as \`CompositeData\` or \`TabularData\` directly. Controlled mapping is required.

Examples of basic types:

| JMX Value | Appropriate JSON |
|---|---|
| \`Integer\`, \`Long\`, \`Double\` | JSON number when precision is not lost |
| \`Boolean\` | JSON boolean |
| \`String\` | JSON string |
| \`ObjectName\` | Canonical name string |
| \`String[]\` | JSON array |
| \`CompositeData\` | JSON object with allowlisted keys |
| \`TabularData\` | JSON array or object according to a defined schema |
| \`null\` | JSON null |

Note that JavaScript JSON numbers only represent exact integers within a limited range. For very large 64-bit counters, consider representing them as strings or a format agreed upon by clients to avoid losing precision.

Do not automatically serialize arbitrary JMX objects using reflection or \`toString()\`; some types may contain complex structures, sensitive data, or unstable representations.

## 14. Handling CompositeData

Some JVM MBeans use \`javax.management.openmbean.CompositeData\`, for example memory usage information.

\`\`\`java
import javax.management.openmbean.CompositeData;

Object raw = connection.getAttribute(
    memoryPoolObjectName,
    "Usage"
);

if (raw instanceof CompositeData data) {
    Object used = data.get("used");
    Object max = data.get("max");

    System.out.println("used=" + used);
    System.out.println("max=" + max);
}
\`\`\`

When converting to JSON, extract only known keys and check their types:

\`\`\`json
{
  "usedBytes": 12582912,
  "maxBytes": 67108864
}
\`\`\`

Do not assume every \`CompositeData\` has \`used\` or \`max\` keys; the OpenType schema depends on the MBean/attribute.

## 15. Handling TabularData

\`TabularData\` represents a tabular structure in Open MBeans. A converter can retrieve \`values()\` and convert each \`CompositeData\` into a JSON object according to a defined schema.

\`\`\`java
import javax.management.openmbean.TabularData;
import javax.management.openmbean.CompositeData;

if (value instanceof TabularData table) {
    for (Object row : table.values()) {
        if (row instanceof CompositeData data) {
            // Select only the fields allowed to be exposed.
        }
    }
}
\`\`\`

Things to avoid:

- Converting a very large table into an unbounded response.
- Assuming row order is always stable.
- Returning unclassified full data.
- Ignoring JSON size or serialization errors.

In an API, consider limiting row counts, using a fixed schema, or returning only aggregate metrics.

## 16. Designing the Intermediary Web API

A sensible model:

\`\`\`text
Dashboard / automation
         |
         | HTTPS + authentication + authorization
         v
    Read-only HTTP controller
         |
         | allowlist endpoint
         v
    Management snapshot service
         |
         | Fixed ObjectName
         | Fixed attribute
         v
    MBeanServerConnection
         |
         v
      MBeanServer
\`\`\`

Instead of exposing a generic \`GET /jmx?objectName=...&attribute=...\`, design endpoints around operational data:

\`\`\`text
GET /internal/monitoring/orders-queue
\`\`\`

Response:

\`\`\`json
{
  "queue": "orders",
  "pendingJobs": 12,
  "processedJobs": 1420,
  "sampledAt": "2026-11-11T11:00:00Z"
}
\`\`\`

This example does not open an arbitrary operation gateway into the JVM. The client knows a clear JSON schema and does not need to construct an \`ObjectName\`.

## 17. Read-Only Spring Web API Example

DTO:

\`\`\`java
package example.monitoring;

import java.time.Instant;

public record QueueSnapshot(
    String queue,
    int pendingJobs,
    long processedJobs,
    Instant sampledAt
) {}
\`\`\`

Service:

\`\`\`java
package example.monitoring;

import java.time.Instant;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

import org.springframework.stereotype.Service;

@Service
public class QueueSnapshotService {

    private final MBeanServerConnection connection;
    private final ObjectName queueName;

    public QueueSnapshotService(
            MBeanServerConnection connection
    ) throws Exception {
        this.connection = connection;
        this.queueName = new ObjectName(
            "app.management:type=Queue,name=orders"
        );
    }

    public QueueSnapshot read() throws Exception {
        int pending = (Integer) connection.getAttribute(
            queueName,
            "PendingJobs"
        );

        long processed = (Long) connection.getAttribute(
            queueName,
            "ProcessedJobs"
        );

        return new QueueSnapshot(
            "orders",
            pending,
            processed,
            Instant.now()
        );
    }
}
\`\`\`

Controller:

\`\`\`java
package example.monitoring;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal/monitoring")
public class QueueMonitoringController {

    private final QueueSnapshotService service;

    public QueueMonitoringController(
            QueueSnapshotService service
    ) {
        this.service = service;
    }

    @GetMapping("/orders-queue")
    public QueueSnapshot readQueue() throws Exception {
        return service.read();
    }
}
\`\`\`

This is a structural example. The application needs to provide an \`MBeanServerConnection\` bean, configure HTTP security, and add appropriate exception handling. Do not expose this endpoint publicly just because the path starts with \`/internal\`.

## 18. Providing MBeanServerConnection to the Web API

For a Spring application using the platform server:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServerConnection;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JmxConnectionConfig {

    @Bean
    public MBeanServerConnection managementConnection() {
        return ManagementFactory.getPlatformMBeanServer();
    }
}
\`\`\`

If the exporter is configured to use a custom MBeanServer, the Web API must receive **the same server**, not default to the platform server.

A clean approach is to create a single \`MBeanServer\` bean and inject it into both the exporter and the snapshot service. When multiple MBeanServers exist in the same JVM, use \`@Qualifier\` to avoid injecting the wrong one.

## 19. Do Not Expose Arbitrary ObjectNames from HTTP Requests

An anti-pattern:

\`\`\`java
@GetMapping("/jmx")
public Object read(
        @RequestParam String objectName,
        @RequestParam String attribute
) throws Exception {
    return connection.getAttribute(
        new ObjectName(objectName),
        attribute
    );
}
\`\`\`

Even though it only calls \`getAttribute\`, this API can leak:

- JVM/system properties.
- Thread dumps or internal state.
- Application configuration and connection settings.
- MBeans from third-party libraries.
- Internal system identifiers.

If supporting multiple metrics is required, use a fixed mapping:

\`\`\`java
Map<String, MetricMapping> allowed = Map.of(
    "orders.pending",
    new MetricMapping(
        "app.management:type=Queue,name=orders",
        "PendingJobs"
    ),
    "orders.processed",
    new MetricMapping(
        "app.management:type=Queue,name=orders",
        "ProcessedJobs"
    )
);
\`\`\`

\`MetricMapping\` is an application-defined record/class. Clients only select an allowlisted key and never pass a raw \`ObjectName\` or attribute string.

## 20. HTTP Security Is Mandatory

For an intermediary API, you must design:

- Authentication using the organization's standard mechanism.
- Authorization based on role/service identity.
- HTTPS/TLS.
- Network segmentation or private ingress.
- Rate limiting and protection against overly frequent polling.
- Auditing for access to sensitive data.
- Sanitization of returned data.
- Never logging credentials.
- Timeouts and circuit breakers for remote JMX.

A path like \`/internal/monitoring\` does not create access control on its own. Spring Security must be configured for this endpoint according to actual requirements.

If the API only serves a monitoring agent, consider using a service-to-service identity rather than a widely shared token.

## 21. Timeouts, Retries, and System Load

A local \`getAttribute\` is usually faster than remote JMX, but can still be slow if the getter accesses a database, network, or holds a lock.

Avoid getters like:

\`\`\`java
@ManagedAttribute
public int getPendingJobs() {
    return remoteQueueClient.scanAllJobs();
}
\`\`\`

if each read triggers an expensive query.

Better:

\`\`\`java
@ManagedAttribute
public int getPendingJobs() {
    return cachedQueueDepth.get();
}
\`\`\`

with aggregated/cached data updated appropriately.

For the Web API:

1. Set timeouts at the remote connector/HTTP request layer where supported.
2. Limit concurrency and request rate.
3. Define a stale-data policy.
4. Do not retry indefinitely when a server lacks an MBean.
5. Return an unavailable or partial status instead of substituting a fake zero.
6. Monitor the latency of the bridge service itself.

An API returning “pendingJobs=0” when JMX times out can produce false operational signals. Distinguish between \`0\` as a real measurement and “unable to retrieve metrics”.

## 22. Error States Should Be Represented Clearly

An intermediary API can use a schema like:

\`\`\`json
{
  "status": "UNAVAILABLE",
  "sampledAt": "2026-11-11T11:00:00Z",
  "reasonCode": "JMX_TIMEOUT"
}
\`\`\`

Or HTTP \`503 Service Unavailable\` with a body containing a stable error code.

Do not send stack traces, usernames, connector URLs containing secrets, or internal exception messages to untrusted clients. Server-side logs should include a correlation ID for lookup while avoiding leaking sensitive information.

Common errors:

| JMX Error | Possible Meaning | Resolution |
|---|---|---|
| \`InstanceNotFoundException\` | ObjectName not registered yet or already unregistered | Check exporter/server/lifecycle |
| \`AttributeNotFoundException\` | Attribute does not exist | Check \`MBeanInfo\` |
| \`MBeanException\` | Server-side getter/operation failed | Check cause and business code |
| \`ReflectionException\` | Reflection/access mismatch | Check adapter/metadata |
| \`IOException\` | Remote connection failed | Check network/connector |
| Authentication failure | Incorrect credentials or access rules | Check identity/security setup |
| \`SecurityException\` | Permission denied | Do not bypass; investigate policy |

## 23. Using Periodic Scripts to Collect Snapshots

A collection schedule should define:

\`\`\`text
Every 30 seconds
   |
   v
JMX read-only query
   |
   v
Normalize + timestamp + instance ID
   |
   v
Metrics/time-series backend
\`\`\`

Do not let every dashboard tab open its own connection and poll the same JVM rapidly. Use a shared agent/collector or snapshot cache to reduce load.

For periodic scripts:

- Have explicit timeouts and exit codes.
- Record timestamp/instance ID.
- Distinguish missing MBeans from a value of 0.
- Handle credentials securely.
- Do not print passwords to stdout.
- Ensure connector cleanup.
- Do not invoke operations with side effects in collection jobs.

## 24. When to Use Spring Boot Actuator/Micrometer?

If the primary goal is metrics and health, there are usually better-suited tools than a custom-written Web API bridge:

\`\`\`text
Spring Boot Actuator
    |
    +--> health/info endpoints
    |
    +--> metrics endpoint
    |
    +--> Micrometer meter registry
              |
              +--> monitoring backend
\`\`\`

Actuator can expose endpoints over HTTP or JMX depending on configuration. Micrometer provides many exporters to integrate with metrics systems.

A custom JMX bridge is appropriate when:

- An application/library only exposes data as MBeans.
- Specific JMX metrics are needed that do not yet have a metric adapter.
- Clients do not speak JMX but require a stable HTTP schema.
- You are able to manage the bridge's security, rate limiting, and lifecycle.

If only standard JVM metrics are needed, evaluate existing Actuator/Micrometer/JMX exporters before creating a new controller.

## 25. Testing the Intermediary API

An integration test should verify:

1. The MBean is registered on the server used in the test.
2. The endpoint only reads allowlisted attributes.
3. The JSON response has the correct types and values.
4. No data outside the allowed list is exposed.
5. When the MBean is missing, the API returns a clear error.
6. When an attribute is missing, it does not default to 0.
7. Authentication/authorization blocks unauthorized clients.
8. Timeouts/rate limiting work in the appropriate infrastructure.
9. Application shutdown cleans up connectors/resources.
10. There is no HTTP route for arbitrary \`invoke\`/\`setAttribute\`.

Service test sketch:

\`\`\`java
MBeanServer testServer =
    MBeanServerFactory.newMBeanServer("monitoring.test");

ObjectName name = new ObjectName(
    "app.management:type=Queue,name=orders"
);

// Register a test MBean compatible with the schema.
// Then inject testServer into QueueSnapshotService.
// Call service.read() and assert PendingJobs/ProcessedJobs.
\`\`\`

This is an outline requiring an actual test fixture MBean and DI setup. Do not use the platform MBeanServer if tests could conflict with production MBeans of the test runner JVM.

## 26. Observing Multiple JVMs

An intermediary API that aggregates multiple JVMs must handle each connection separately:

\`\`\`text
JVM A MBeanServer ----\
                       \
JVM B MBeanServer ------> Collector/API
                       /
JVM C MBeanServer ----/
\`\`\`

Each JVM may use the same ObjectName \`app.management:type=Queue,name=orders\`, so data identification must include an instance ID or server identity.

JSON example:

\`\`\`json
{
  "instances": [
    {
      "instance": "orders-1",
      "pendingJobs": 12,
      "status": "OK"
    },
    {
      "instance": "orders-2",
      "status": "UNAVAILABLE"
    }
  ]
}
\`\`\`

Do not assign \`pendingJobs=0\` to an unreachable instance. Nor should multiple MBeans with the same ObjectName across different JVMs be treated as a single object.

At large scale, a purpose-built collector/metrics backend is usually more effective than a controller fanning out to every JVM on each HTTP request.

## 27. Hands-On Exercises

### Exercise A: CLI Reading Two Attributes

From the Spring MBean \`app.management:type=Queue,name=orders\`, use \`MBeanServerConnection\` and \`getAttributes\` to retrieve \`PendingJobs\` and \`ProcessedJobs\`.

Requirements: print both values accurately, report an error when the ObjectName does not exist, and do not perform \`invoke\`.

### Exercise B: MBeanInfo Discovery

Use \`getMBeanInfo\` to print the list of readable attributes and their types. Explain why an allowlist is still needed before exposing them over HTTP.

### Exercise C: HTTP Bridge

Design the endpoint \`GET /internal/monitoring/orders-queue\` returning the \`QueueSnapshot\` DTO. Protect it with Spring Security or an appropriate security layer. Write a test verifying that unauthorized clients are rejected.

### Exercise D: CompositeData

Read a \`CompositeData\` attribute, select two non-sensitive fields, and convert them to JSON. Handle cases where keys are missing or have unexpected types.

### Exercise E: Lost Remote Connection

Simulate an \`IOException\` during querying and return \`UNAVAILABLE\` or HTTP 503. Do not return fake measurements.

## 28. Self-Check Questions

1. Why cannot a CLI program in a separate JVM automatically read the platform MBeanServer of another JVM?
2. Does an \`ObjectName\` uniquely identify across all JVMs on multiple machines?
3. When should \`getAttributes\` be used instead of multiple calls to \`getAttribute\`?
4. Why should an API not accept a raw ObjectName from an HTTP request?
5. How should \`CompositeData\` be mapped to JSON?
6. Why does a read-only API still require authentication and authorization?
7. Can an MBean getter cause heavy load even when it is read-only?
8. Should a JMX timeout be converted into a measurement of 0?
9. When is Actuator/Micrometer better than a custom-written bridge?
10. Why should an intermediary Web API not allow arbitrary \`invoke\` calls?

## 29. Key Takeaways

\`\`\`text
JMX script:
  MBeanServerConnection
      -> queryNames/getMBeanInfo
      -> getAttribute/getAttributes
      -> stdout/JSON

Read-only Web API:
  HTTPS + authorization
      -> allowlist
      -> fixed ObjectName + attribute
      -> normalize typed DTO
      -> JSON response

Do not expose arbitrary JMX invoke/setAttribute.
\`\`\`

**Core principle:** MBeans can be read via a script or an intermediary Web API, but you must choose the **right MBeanServer**, the **right ObjectName**, and the **right attributes**, transform data into a stable schema, and apply security. Do not turn an observability bridge into an unrestricted JMX gateway; for standard metrics and periodic collection needs, prefer an appropriate observability platform whenever possible.