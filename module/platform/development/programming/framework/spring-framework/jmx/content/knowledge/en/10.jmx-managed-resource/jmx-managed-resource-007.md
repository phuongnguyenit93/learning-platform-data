# Avoiding Accidental Exposure of Internal Services via Annotations

> **Topic:** Spring Framework JMX  
> **Knowledge Group:** ManagedResource  
> **Lesson:** Avoiding Accidental Exposure of Internal Services via Annotations

## 1. Lesson Objectives

After this lesson, you will be able to:

- Explain why an internal Spring service can accidentally become a management surface when annotated with \`@ManagedResource\`.
- Distinguish between a bean existing in the Spring \`ApplicationContext\` and a bean being registered in the JMX \`MBeanServer\`.
- Identify attributes, operations, and notifications that should not be exposed to JMX clients.
- Design a separate **management facade** to expose only intentional data and management operations.
- Use \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\`, and \`@EnableMBeanExport\` in a controlled manner.
- Inspect the actual MBean surface using \`MBeanInfo\` before deploying the application to an environment with management tools.
- Understand that even without enabling a remote connector, you still need to manage local JMX access permissions and keep secrets out of MBeans.

## 2. Problem: Management Annotations Can Open Another Application Interface

A Spring service is typically designed for internal logic. For example, \`PaymentService\` may hold dependencies, transaction configuration, provider access keys, and state-mutating methods.

When a class is annotated with \`@ManagedResource\` and the application enables annotation-based JMX export, Spring can register this bean as an MBean in \`MBeanServer\`.

\`\`\`text
               Spring ApplicationContext
                           |
               +-----------+------------+
               |                        |
         PaymentService             CacheService
         internal business          internal business
               |
               | @ManagedResource
               | @ManagedAttribute
               | @ManagedOperation
               v
           MBeanExporter
               |
               v
           MBeanServer
               |
               v
       JConsole / JMX client
       reads attributes, invokes operations
\`\`\`

Merely having a Spring bean does not mean there is an MBean. However, when annotations and an exporter work together, exposed management members can become an interaction point outside the normal business call flow.

**The JMX surface is a management API.** It must be designed like an API with real effects: having a contract, permitted scope, input validation, access control, and verification.

## 3. Related Annotations

| Annotation | Meaning | Risk When Used Without Control |
|---|---|---|
| \`@ManagedResource\` | Marks a bean as a JMX resource and can declare \`ObjectName\`. | Easily turns a business service into an object discoverable by JMX tools. |
| \`@ManagedAttribute\` | Exposes getter/setter as a JMX attribute. | Getters may leak data; setters may modify configuration or state. |
| \`@ManagedOperation\` | Exposes a method as a JMX operation. | Operations may delete data, reload config, alter resources, or trigger costly processing. |
| \`@ManagedOperationParameters\` | Describes operation parameters. | Makes the interface easier to invoke; must ensure the operation is truly allowed to be exposed. |
| \`@ManagedNotifications\` / \`@ManagedNotification\` | Declares JMX notification types. | Notification payloads may contain internal data or emit excessive events. |
| \`@EnableMBeanExport\` | Enables annotation-based MBean export in Java configuration. | May trigger export of annotated beans that the development team has not inventoried. |

\`@ManagedResource\` does not mean every public method automatically appears as an operation when using Spring annotation metadata under standard configuration. However, this is **no reason to attach annotations carelessly**: the JMX surface can change when adding \`@ManagedAttribute\`, \`@ManagedOperation\`, changing the assembler, or changing the export mechanism.

## 4. Distinguishing Business Beans from Management MBeans

A Spring bean can serve multiple execution flows:

\`\`\`text
HTTP request / scheduled job / message consumer
                 |
                 v
             Service bean
                 |
                 v
         Repository / database
\`\`\`

If the service is exported directly, an additional flow exists:

\`\`\`text
JMX client
    |
    v
MBeanServer
    |
    v
Exported service bean
    |
    v
Business methods and state
\`\`\`

The second flow can bypass controls designed only at the HTTP controller, such as validation, authorization, or auditing attached to the web layer. Spring Security protecting a REST endpoint **does not automatically prove** the same operation is protected when invoked via JMX.

Therefore, do not treat JMX as a "harmless debug window". A JMX setter or operation can execute logic on the live server, even affecting the database and external systems.

## 5. What Not to Do: Exporting a Sensitive Service Directly

Suppose a service holds configuration and operational methods:

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Service;

@Service
@ManagedResource(
    objectName = "app.security:type=PaymentService,name=main"
)
public class PaymentService {

    private String providerApiKey = "example-secret";

    @ManagedAttribute
    public String getProviderApiKey() {
        return providerApiKey;
    }

    @ManagedOperation
    public void disableFraudChecks() {
        // Modifies risk-checking behavior.
    }

    public void chargeCustomer(String customerId) {
        // Internal payment logic.
    }
}
\`\`\`

This is an **anti-pattern example to recognize a design flaw**, not code to use in a real application. Two clear issues:

1. \`getProviderApiKey()\` can expose a secret value as a JMX attribute.
2. \`disableFraudChecks()\` creates an operation allowing a critical control to be changed outside a purposefully designed management channel.

In a JMX client with access, a user can read attributes or invoke operations exposed by the exporter. This access does not necessarily pass through controllers, REST authorization, or web application security filters.

Hardcoding the credential in source in this example is to illustrate what not to do; in real products never hardcode secrets. Even when a secret comes from environment variables or a secret manager, exposing it via JMX still leaks that value.

## 6. Principle: Export Only an Intentional Management Facade

A clean design keeps the business service independent of management annotations and creates a separate management bean.

\`\`\`text
           Spring ApplicationContext
              |                 |
              v                 v
       PaymentService      PaymentMetricsMBean
       real business       management facade
              ^                 |
              |                 | reads safe metrics
              +-----------------+
                                |
                                | @ManagedResource
                                v
                          MBeanExporter
                                |
                                v
                           MBeanServer
                                |
                                v
                             JConsole
\`\`\`

The facade is responsible for **selecting** what to expose. It does not need to mirror the service's entire API. It is best to start with well-defined read-only attributes: request counts, error counts, last processing time, and aggregated operational status.

### 6.1. Service Without JMX Annotations

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    private final AtomicLong processedCount =
        new AtomicLong();

    private final AtomicLong failureCount =
        new AtomicLong();

    public void recordSuccess() {
        processedCount.incrementAndGet();
    }

    public void recordFailure() {
        failureCount.incrementAndGet();
    }

    public long processedCount() {
        return processedCount.get();
    }

    public long failureCount() {
        return failureCount.get();
    }

    // Sensitive business methods and dependencies
    // are not exported directly via JMX.
}
\`\`\`

The service provides only the aggregated information needed by the facade. In a real application, expose observational data through a service or metrics component with clear responsibilities, avoiding broad access into internals.

### 6.2. Read-Only Facade

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "app.monitoring:type=PaymentMetrics,name=main",
    description = "Non-sensitive payment counters"
)
public class PaymentMetricsMBean {

    private final PaymentService paymentService;

    public PaymentMetricsMBean(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    @ManagedAttribute(
        description = "Successful payment processing count"
    )
    public long getProcessedCount() {
        return paymentService.processedCount();
    }

    @ManagedAttribute(
        description = "Failed payment processing count"
    )
    public long getFailureCount() {
        return paymentService.failureCount();
    }
}
\`\`\`

Here, the facade only exposes two read-only attributes. There are no setters or state-mutating operations in the management interface. \`PaymentService\` remains a regular service and is not directly annotated with \`@ManagedResource\`.

The class name \`PaymentMetricsMBean\` in the example describes the facade role; Spring's annotation exporter uses \`@ManagedResource\` and related metadata. This class does not need to be treated as a Standard MBean interface like \`PaymentMetricsMBean\` under standard JMX conventions.

### 6.3. Enabling the Exporter in Java Configuration

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@ComponentScan(basePackageClasses = PaymentService.class)
@EnableMBeanExport
public class JmxConfiguration {
}
\`\`\`

With appropriate component scanning, Spring creates \`PaymentService\` and \`PaymentMetricsMBean\`. The annotation exporter registers the facade carrying \`@ManagedResource\`, while the business service is not placed into MBeanServer merely because it is a \`@Service\`.

A system may use Spring Boot JMX auto-configuration instead of declaring \`@EnableMBeanExport\`; check actual exporters to avoid duplicate ObjectName registrations. Regardless of how it is enabled, the principle of **choosing an intentional facade** still holds.

## 7. When Management Operations Are Needed, Limit Scope and Validate Inputs

Sometimes operators need an action such as refreshing a cache, resetting a counter, or changing a logging level. Such operations still have side effects and must have a clear contract.

Example of a cache management facade:

\`\`\`java
@Component
@ManagedResource(
    objectName = "app.monitoring:type=CacheControl,name=primary"
)
public class CacheControlMBean {

    private final CacheMaintenanceService maintenance;

    public CacheControlMBean(
            CacheMaintenanceService maintenance
    ) {
        this.maintenance = maintenance;
    }

    @ManagedOperation(
        description = "Refresh a permitted cache by name"
    )
    public String refreshCache(String cacheName) {
        if (!"catalog".equals(cacheName)
                && !"configuration".equals(cacheName)) {
            throw new IllegalArgumentException(
                "Unsupported cacheName"
            );
        }

        maintenance.refresh(cacheName);
        return "Refresh requested for " + cacheName;
    }
}
\`\`\`

\`CacheMaintenanceService\` is an illustrative dependency with a \`refresh(String)\` API, not a built-in Spring class. In a real application, implement an appropriate service and ensure JMX invocations comply with all required business controls.

Key design points:

- The facade exposes **a narrow operation** instead of the entire cache service.
- Cache names are restricted by an allowlist rather than accepting arbitrary strings.
- Do not expose dangerous operations like "delete all data".
- The return value distinguishes requesting an action from completing work if the backend processes asynchronously.
- When auditing is required by the environment, record management actions in the service or appropriate infrastructure layer.
- Remote JMX invocation rights must be restricted separately, without relying on REST endpoint protection.

Even seemingly small operations can cause heavy load if called repeatedly. Consider rate limiting at the management layer, idempotency, and resource bounds for expensive operations.

## 8. Do Not Equate "Internal" with "Safe"

There are several ways a client can access JMX:

\`\`\`text
Same JVM:
  Code -> MBeanServer

Local process:
  JConsole / JMX client -> appropriate attach mechanism -> MBeanServer

Remote:
  JMXConnector -> MBeanServerConnection -> MBeanServer
\`\`\`

\`@EnableMBeanExport\` only makes the MBean appear in the registry; it **does not open a remote port by itself**. However, that is not enough to conclude the MBean is unreachable: local JVM management, monitoring agents, tools on the host, or authorized clients can still interact with it.

Therefore, distinguish:

- **Exposure control:** which attributes and operations exist in MBeanInfo.
- **Connection control:** who can open a local/remote JMX connection.
- **Authorization control:** which clients can read or invoke management actions.
- **Data control:** return values/notifications do not contain secrets or sensitive information.

A design flaw at the exposure layer is not necessarily fixed solely by blocking remote ports, because internal components can still access the registry.

## 9. Rules for Intentional ObjectName Naming

MBean names should describe management function rather than exposing overly detailed internal structure.

Examples to use:

\`\`\`text
app.monitoring:type=PaymentMetrics,name=main
app.monitoring:type=CacheControl,name=primary
\`\`\`

Names to avoid when unnecessary:

\`\`\`text
app.internal:type=DatabaseCredentials,name=production
app.internal:type=PaymentSecretProvider,name=primary
\`\`\`

An ObjectName does not contain a secret by itself if it is only a name. However, naming resources too granularly can reveal system architecture, technologies, or internal purpose when clients browse the registry.

If there are multiple instances, add properties with a clear convention:

\`\`\`text
app.monitoring:type=WorkerPool,name=primary,node=one
app.monitoring:type=WorkerPool,name=primary,node=two
\`\`\`

Each ObjectName must be unique within an MBeanServer. Avoid placing unescaped user data directly into key properties; for values containing special characters, use \`ObjectName.quote(value)\` or an appropriate ObjectName construction API.

## 10. Verify What JMX Content Is Actually Exposed

Do not stop at reading annotations in source code. Inspecting \`MBeanInfo\` from the running server shows the registered management surface.

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "app.monitoring:type=PaymentMetrics,name=main"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "MBean missing: " + name
    );
}

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "Attribute: %s, readable=%s, writable=%s%n",
        attribute.getName(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println(
        "Operation: " + operation.getName()
    );
}
\`\`\`

When the facade example is exported with appropriate annotation metadata, you expect to see \`ProcessedCount\` and \`FailureCount\` as read-only attributes, with no operations from \`PaymentService\`.

**Note:** \`ManagementFactory.getPlatformMBeanServer()\` only shows MBeans on the platform server. If the Spring exporter uses a separate MBeanServer, inspect that exact server; not finding the MBean on the platform server does not prove the bean was not exported.

### Checking with queryNames

\`\`\`java
ObjectName pattern = new ObjectName(
    "app.monitoring:type=*,*"
);

for (ObjectName objectName :
        server.queryNames(pattern, null)) {
    System.out.println(objectName);
}
\`\`\`

Querying helps inventory MBeans in the selected domain. When reviewing the entire management surface, query more broadly with an authorized client and inspect each MBeanInfo, rather than assuming this domain is the only place the application exports MBeans.

## 11. A Test Ensuring Sensitive Services Do Not Appear

You can write a configuration verification check in an integration test inside a context with JMX export enabled:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;

import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(JmxConfiguration.class)
class JmxExposureTest {

    @Autowired
    MBeanServer server;

    @Test
    void onlyManagementFacadeIsRegistered() throws Exception {
        ObjectName facade = new ObjectName(
            "app.monitoring:type=PaymentMetrics,name=main"
        );
        ObjectName internal = new ObjectName(
            "app.security:type=PaymentService,name=main"
        );

        assertTrue(server.isRegistered(facade));
        assertFalse(server.isRegistered(internal));
    }
}
\`\`\`

The test snippet assumes the Spring context has an \`MBeanServer\` bean registered for injection and that the exporter uses that exact bean. If the context does not expose \`MBeanServer\` as a Spring bean, create or inject the server with an appropriate configuration; do not assume \`@Autowired MBeanServer\` always succeeds.

A simple configuration using the platform server is:

\`\`\`java
@Configuration
@EnableMBeanExport(server = "jmxServer")
public class JmxServerConfig {

    @Bean
    public MBeanServer jmxServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }
}
\`\`\`

In real tests, ensure the test context imports this configuration properly, avoid name collisions when multiple tests share the platform MBeanServer, and close the context so the exporter cleans up.

Also understand the limitation of testing a specific name: it only proves **one ObjectName** is absent. If the goal is ensuring no sensitive service is exposed at all, inventory all ObjectNames and MBeanInfo entries in the application's scope against an allowlist.

## 12. MBean Inventory Allowlist Pattern

One approach is declaring the set of ObjectNames the application is allowed to export:

\`\`\`java
Set<String> allowed = Set.of(
    "app.monitoring:type=PaymentMetrics,name=main",
    "app.monitoring:type=CacheControl,name=primary"
);
\`\`\`

Then compare against MBeans registered in the application domain:

\`\`\`java
ObjectName applicationPattern =
    new ObjectName("app.monitoring:*");

Set<ObjectName> actual =
    server.queryNames(applicationPattern, null);

for (ObjectName objectName : actual) {
    if (!allowed.contains(
            objectName.getCanonicalName())) {
        throw new IllegalStateException(
            "Unexpected MBean: " + objectName
        );
    }
}
\`\`\`

Because \`ObjectName.getCanonicalName()\` can reorder key properties, normalize the allowlist to canonical form instead of comparing arbitrary input strings.

Example building a canonical allowlist:

\`\`\`java
Set<String> allowedCanonical = Set.of(
    new ObjectName(
        "app.monitoring:type=PaymentMetrics,name=main"
    ).getCanonicalName(),
    new ObjectName(
        "app.monitoring:type=CacheControl,name=primary"
    ).getCanonicalName()
);
\`\`\`

When managing multiple domains, inventory every domain the application might export into. If there are third-party exporters or runtime agents, valid system MBeans must be explicitly accounted for to avoid mistakenly blocking system MBeans.

**A name allowlist is a first step, not a complete guarantee.** An MBean can still expose dangerous attributes or operations while keeping the same ObjectName. Therefore, also inspect \`MBeanInfo\` and compare against the expected management contract.

## 13. Evaluating Attributes: What Should/Should Not Be Exposed?

| Data | Assessment | Reason |
|---|---|---|
| Processed request count | Usually appropriate | Aggregated metric, low sensitivity if free of user data. |
| Error count by category | Can be appropriate | Useful for operations; avoid labels containing sensitive data. |
| Service status \`UP/DOWN\` | Usually appropriate | Aids diagnosis. |
| Queue length | Usually appropriate | Resource status. |
| Passwords/tokens/API keys | Should not expose | Can be read by management clients. |
| Connection strings containing credentials | Should not expose | Can leak accounts or internal endpoints. |
| Lists of emails, customer names | Should not expose directly | Personal data unnecessary for aggregate management. |
| Full SQL with parameters | High risk | Can leak data and system structure. |
| Stack traces containing secrets | Should not expose verbatim | Error details sometimes contain internal values. |
| Sensitive feature flag configs | Needs careful review | Can expose control mechanisms or alter behavior. |

A read-only attribute **does not mean zero risk**. It can still leak data when read. A writable attribute additionally opens the ability to alter state.

## 14. Evaluating Operations: Invocation Rights and Side Effects

Before placing \`@ManagedOperation\` on a method, answer:

1. Does the operation have a clear operational purpose?
2. Should it be visible to all clients with JMX access or only a subset of operators?
3. Can it be called repeatedly safely?
4. Are parameters validated and range-bounded?
5. Can the operation cause data loss, service disruption, or security impact?
6. Do we need to audit who called it, when, and with what result?
7. On failure, do exceptions leak sensitive details?
8. If long-running, is there a timeout, status-reporting mechanism, or cancellation?

Do not export broad-privileged methods directly just for debugging convenience. If a management action is needed, create a facade calling a service with appropriate input, state, and permission checks.

### Why Can HTTP Security Be Bypassed?

\`\`\`text
HTTP Request
  -> Spring Security Filter Chain
  -> Controller
  -> Service

JMX invoke
  -> JMXConnector / MBeanServer
  -> Exposed MBean operation
  -> Service
\`\`\`

The two paths may not share an authorization layer. If protection logic resides only in an HTTP filter/controller, JMX invocations will not automatically enforce those checks. The proper place for critical business invariants is the shared service/infrastructure layer; management operation authorization must be designed at the JMX connector layer and/or an appropriate facade.

## 15. Notifications Are Also a Data Exposure Surface

A JMX notification can contain:

- \`type\`, \`source\`, \`timeStamp\`, \`message\`.
- \`sequenceNumber\`.
- \`userData\` (payload attached by the implementation).

Example to avoid:

\`\`\`java
Notification event = new Notification(
    "app.payment.failed",
    this,
    sequence.incrementAndGet(),
    System.currentTimeMillis(),
    "Payment failed for " + customerEmail
);
event.setUserData(rawPaymentRequest);
publisher.sendNotification(event);
\`\`\`

The message may contain a customer's email, and \`userData\` may contain transaction data. This information can be received by any JMX client permitted to listen to notifications.

Replace with aggregated information:

\`\`\`java
Notification event = new Notification(
    "app.payment.failure.rate.high",
    this,
    sequence.incrementAndGet(),
    System.currentTimeMillis(),
    "Payment failure rate crossed threshold"
);
event.setUserData("severity=warning");
publisher.sendNotification(event);
\`\`\`

If correlation with detailed events is needed, use a non-sensitive correlation ID and check the system's data policy before emitting.

## 16. Protecting Remote JMX Connections

For environments using remote connectors, configure control layers:

- User authentication or appropriate identity mechanisms.
- Authorization for read/write/operation invocation.
- Transport encryption (TLS) when needed.
- Restricting hosts, network segments, firewalls, and access via VPN/bastion.
- Enabling endpoints only when a real management need exists.
- Monitoring and logging important management operations at the appropriate layer.

Spring's \`@EnableMBeanExport\` or \`@ManagedResource\` **does not configure** these protections automatically. An MBean must never rely on assuming "nobody knows the JMX URL" as a security measure.

With local JMX, control host permissions, OS users, agents, and tools capable of attaching to the JVM.

## 17. Common Incidents

### 17.1. Service Unexpectedly Appears in JConsole

Check:

- Does the bean have \`@ManagedResource\`?
- Does the context have \`@EnableMBeanExport\` or an equivalent exporter?
- Is there a manually declared \`MBeanExporter\` or another auto-configuration?
- What is the actual ObjectName?
- Is there a naming strategy or annotation metadata from another class/interface?
- Which attributes/operations does MBeanInfo currently expose?

Do not simply delete \`@ManagedResource\` and assume all export paths vanish, because the MBean could still be registered via explicit configuration or another exporter. Identify the actual registration mechanism in the context.

### 17.2. Service Lacks @ManagedResource Yet Is Still Exported

This can happen if an \`MBeanExporter\` configuration uses an explicit bean list or an autodetection mechanism other than annotation-based export. Inspect the exporter and active naming/assembler beans rather than scanning annotations in the class alone.

### 17.3. Only Metrics Were Wanted, Yet Dangerous Setters/Operations Appear

Inspect \`MBeanInfo\` of the registered MBean. If the surface is broader than desired, inspect the assembler, method annotations, Standard MBean interfaces, and exporter configuration. Switch to a facade exposing a small contract, or narrow annotations/assemblers by design.

### 17.4. Removed Annotation Yet Old MBean Still Appears

Check whether the application restarted/reloaded the context properly, whether the exporter cleans up old MBeans, whether another server registers the same name, and whether the client is viewing data from an old JVM. Do not unregister MBeans outside your ownership scope just to "clean things up".

### 17.5. Keys/Configs Are Absent from Attributes Yet Leak via Exceptions

A JMX operation can throw an exception whose message contains internal configuration. Do not consider hiding getters sufficient. Handle error logging and error content returned to management clients intentionally.

## 18. Hands-On Scenario

**Scenario:** an application has an \`InventoryService\` with methods:

\`\`\`java
public int getAvailableStock();
public String getSupplierApiToken();
public void rebuildIndex();
public void deleteAllInventory();
public void setReservationLimit(int limit);
\`\`\`

A developer wants to add \`@ManagedResource\` and \`@ManagedOperation\` onto the service to view status via JConsole.

Design an alternative facade.

**Suggested JMX contract:**

\`\`\`java
@Component
@ManagedResource(
    objectName = "app.monitoring:type=InventoryMetrics,name=main"
)
public class InventoryMetricsMBean {

    private final InventoryService service;

    public InventoryMetricsMBean(InventoryService service) {
        this.service = service;
    }

    @ManagedAttribute
    public int getAvailableStock() {
        return service.getAvailableStock();
    }
}
\`\`\`

Initially expose only \`AvailableStock\`, without exposing \`getSupplierApiToken\` or \`deleteAllInventory\`. \`rebuildIndex\` may be considered separately as a maintenance operation requiring operational conditions, auditing, and explicit permission limits. \`setReservationLimit\` mutates business policy and should not be exposed without appropriate controls.

**Question:** If a JMX client has permission to read the MBean but must not modify the system, which getters/setters should exist? Why?

**Suggested answer:** expose only necessary aggregated information through read-only getters. Do not expose state-mutating setters/operations; also restrict JMX read permissions to prevent improper data disclosure.

## 19. Design Checklist Before Deploying an MBean to Runtime

- [ ] There is a concrete operational reason to export this MBean.
- [ ] \`@ManagedResource\` appears only on approved beans/facades.
- [ ] ObjectName belongs to an established management domain and contains no sensitive data.
- [ ] Attributes are exposed by allowlist; setters exist only when genuinely needed.
- [ ] Operations have narrow responsibility, validate inputs, and have restricted permissions.
- [ ] \`MBeanInfo\` has been cross-checked against the intended contract.
- [ ] Notification type/message/userData do not leak user data or secrets.
- [ ] Exporters in the context do not register extra beans, duplicate ObjectNames, or broaden the surface unexpectedly.
- [ ] Remote JMX connector (if enabled) has authentication, authorization, and network protection.
- [ ] MBean lifecycle and cleanup when the context closes are well understood.
- [ ] There is a regression test covering changes to annotations or exporter configuration.

These are design checks for the MBean implementer, not an automatic mechanism applied by Spring to every service.

## 20. Self-Check Questions

1. How does \`@ManagedResource\` differ from \`@Service\`?
2. Why should a Spring-managed service not automatically become an MBean by default?
3. What risk does \`@ManagedAttribute\` on a getter returning an API key create?
4. Why can you not rely on Spring Security web filters to protect JMX operations?
5. How does a management facade narrow the management surface?
6. How is inspecting \`MBeanInfo\` more useful than only looking at annotations in source code?
7. If \`@ManagedResource\` is removed yet the MBean still exists, what other export mechanisms might be present?
8. Why does disabling remote JMX not mean all data in an MBean is safe?
9. What problem does a notification \`userData\` field containing a raw payment request cause?
10. How do you ensure adding a new method to a service does not accidentally expand the JMX API?

## 21. Key Takeaways

\`\`\`text
Spring @Service
   = business-serving object

@ManagedResource
   = JMX management resource marker

@EnableMBeanExport + MBeanExporter
   = infrastructure registering MBeans into MBeanServer

@ManagedAttribute / @ManagedOperation
   = contract exposed to JMX clients

Management facade
   = layer selecting what genuinely needs exposure
\`\`\`

**Core principle:** expose through JMX only data and operations with an explicit management purpose. Keep internal services from being exported directly whenever possible, use small facades, and read \`MBeanInfo\` to confirm the actual surface. Annotations make configuration convenient, but access rights and the consequences of each operation remain the application's design responsibility.