# JMX Endpoint Identification and Default Domain in Spring Boot

## 1. Objectives

Spring Boot can expose application management information over **JMX** through MBeans. When combining Spring Boot Actuator with Spring Framework JMX, operators often see many ObjectNames in JConsole or VisualVM: some belong to JVM domains, some belong to Spring Boot-managed domains, and some are custom application MBeans.

A common mistake is confusing:

- **Actuator endpoint ID**, such as `health`, `info`, `metrics`.
- **JMX ObjectName**, the name `MBeanServer` uses to identify an MBean.
- **JMX domain**, the component before the `:` in an ObjectName.
- **HTTP actuator path**, for example `/actuator/health`, which is a different access mechanism.
- **Spring bean name**, the bean's name in `ApplicationContext`, which is not necessarily its name in JMX.

This lesson explains how JMX endpoints are identified in Spring Boot, how to control the default domain, and the scope of the related properties. The practical goal is to look at an ObjectName and know where it comes from, avoid collisions between application contexts running in the same JVM, and test the naming contract.

## 2. What Is a JMX ObjectName?

A JMX ObjectName has the general syntax:

```text
domain:key=value[,key=value...]
```

Examples:

```text
java.lang:type=Memory
org.springframework.boot:type=Endpoint,name=Health
com.example.billing:type=Cache,name=Primary
```

Where:

- `domain`: logical naming group; it does not automatically represent a network domain.
- `type`, `name`: **key properties** used to identify the object.
- An ObjectName is compared by domain and its set of property keys/values; key-property ordering does not determine name equality.
- Values containing commas, special characters, or wildcards must be constructed using valid JMX syntax, typically with `ObjectName.quote`.

An `MBeanServer` can register only one MBean for a specific ObjectName at a time. Two components choosing the same name can trigger `InstanceAlreadyExistsException`, unless the exporter is configured with a specific registration policy.

**A JMX domain has no mandatory relationship with a Java package name, Maven groupId, or HTTP host.** It is a namespace that management tools can use to group and query MBeans.

## 3. Default Domain for Spring Boot Actuator JMX

Spring Boot Actuator supports endpoints over JMX when enabled and when the required components are on the classpath. In many Boot versions, the default namespace for Actuator JMX endpoints is:

```text
org.springframework.boot
```

A common ObjectName for the Health endpoint:

```text
org.springframework.boot:type=Endpoint,name=Health
```

For Metrics:

```text
org.springframework.boot:type=Endpoint,name=Metrics
```

Endpoint names in the JMX representation may be normalized into a form suitable for ObjectName, such as ID `health` becoming value `Health`. Do not hardcode a guessed capitalization rule for every version/extension; verify the MBeans actually registered in the deployed Spring Boot version.

`health`, `info`, and `metrics` are **Actuator endpoint IDs**. They are not synonymous with the MBean's Java class and are not the name of an HTTP endpoint; one endpoint ID can be exposed over multiple technologies depending on configuration.

## 4. Configuring a Custom JMX Domain

Spring Boot provides a dedicated property for the Actuator JMX domain:

```properties
management.endpoints.jmx.domain=com.example.billing.management
```

Once configured, endpoints exposed over JMX will belong to this namespace, for example:

```text
com.example.billing.management:type=Endpoint,name=Health
com.example.billing.management:type=Endpoint,name=Info
```

In YAML:

```yaml
management:
  endpoints:
    jmx:
      domain: com.example.billing.management
```

Choose a meaningful and relatively stable domain so monitoring tools can query by pattern:

```java
ObjectName pattern = new ObjectName(
    "com.example.billing.management:*"
);
```

**Important scope:** `management.endpoints.jmx.domain` applies to Actuator endpoints exposed over JMX; it is not a directive that renames the domain of all MBeans registered by the application, JVM, or other libraries. A custom MBean `@ManagedResource(objectName="com.example.cache:type=Cache,name=Primary")` still uses its own name if the exporter honors that metadata.

## 5. Enabling JMX and Enabling Actuator Exposure Are Two Different Things

Projects can use `spring.jmx.enabled` to enable bean registration via Spring's JMX mechanism:

```properties
spring.jmx.enabled=true
```

For Actuator, which endpoints are exposed over JMX is also affected by exposure configuration:

```properties
management.endpoints.jmx.exposure.include=health,info,metrics
```

Or:

```yaml
management:
  endpoints:
    jmx:
      exposure:
        include: health, info, metrics
```

These properties serve different purposes:

| Property | Purpose |
| --- | --- |
| `spring.jmx.enabled` | Controls Spring JMX/bean export capability via Boot auto-configuration |
| `management.endpoints.jmx.domain` | Selects the JMX domain for Actuator endpoints |
| `management.endpoints.jmx.exposure.include` | Selects Actuator endpoint IDs exposed over JMX |
| `management.endpoints.jmx.exposure.exclude` | Excludes Actuator endpoints from JMX exposure |
| `management.endpoints.web.exposure.include` | Selects endpoints exposed over HTTP; does not control JMX |

Default behavior and auto-configuration conditions vary across Spring Boot releases. Therefore, when diagnosing a missing endpoint, check the **effective configuration** and actual application version. Do not assume enabling an HTTP endpoint automatically makes the JMX endpoint appear, or vice versa.

## 6. Endpoint ID, JMX ObjectName, and HTTP Path

Example with the health endpoint:

```text
Logical Actuator endpoint ID:
    health

Potential HTTP endpoint:
    /actuator/health

Potential JMX ObjectName:
    org.springframework.boot:type=Endpoint,name=Health
```

An endpoint can be configured for access over HTTP but not over JMX. Conversely, when JMX exposure is enabled, an endpoint may appear in the JMX registry without a corresponding web endpoint because web exposure is restricted.

**The HTTP path and JMX ObjectName do not necessarily change together.** Changing `management.endpoints.web.base-path` or HTTP path-mapping does not automatically adjust `management.endpoints.jmx.domain`.

Security rules also differ: HTTP endpoints typically pass through Spring Security and the servlet/reactive stack, whereas a JMX connector uses JMX protocol/management security. Do not treat security rules for `/actuator/**` as protection for a remote JMX connector.

## 7. How Spring Boot Recognizes Actuator Endpoints

Actuator has an endpoint concept with read/write/delete operations aligned with the management model. Defining a custom endpoint:

```java
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "queueStatus")
public class QueueStatusEndpoint {
    @ReadOperation
    public QueueSnapshot read() {
        return new QueueSnapshot(12, 3, false);
    }

    public record QueueSnapshot(
        int queued,
        int active,
        boolean paused
    ) {}
}
```

This example illustrates endpoint ID `queueStatus` and does not guarantee that a record return type is mapped identically across all versions/JMX tools. For JMX, the data model must be convertible into a form compatible with JMX/OpenType or supported by Actuator's mechanism; test it in practice.

When the endpoint is exposed over JMX, the Actuator infrastructure creates the corresponding MBean and registers it under the configured domain. Do not manually register an extra Standard MBean with an ObjectName that collides with the Actuator endpoint.

For APIs with sensitive parameters or impactful operations, separate authorization and auditing are required; endpoint naming is not a security policy.

## 8. Multiple Application Contexts in the Same JVM

One JVM can run multiple Spring `ApplicationContext` instances:

```text
JVM / platform MBeanServer
  |
  +-- ApplicationContext A
  |      org.springframework.boot:type=Endpoint,name=Health
  |
  +-- ApplicationContext B
         org.springframework.boot:type=Endpoint,name=Health
```

If both contexts register the same ObjectName on the same server, a collision occurs. This is common with:

- Multiple Spring Boot applications in the same application server.
- Parent/child contexts each having their own Actuator.
- Spring Boot DevTools context restarts.
- Integration tests initializing multiple contexts while sharing the platform server.
- Hot deploy/redeploy when the old context has not finished cleaning up.

Spring Boot may provide properties to generate unique JMX names for endpoints:

```properties
spring.jmx.unique-names=true
management.endpoints.jmx.unique-names=true
```

The scope and availability of these properties must be checked for your Boot version. `management.endpoints.jmx.unique-names` targets Actuator endpoints, whereas `spring.jmx.unique-names` relates to Spring-level MBean registration. When configuration enables unique names, ObjectNames may include an identifying context/bean key to distinguish registrations.

Do not enable unique names blindly if automation relies on stable ObjectNames. Verify actual names before and after the change, then update dashboard/client queries accordingly.

## 9. Choosing a Dedicated Domain per Application

When multiple applications share a JVM while maintaining separate boundaries, an easy way to keep track is to assign an application-specific domain:

```properties
management.endpoints.jmx.domain=com.example.payments.management
```

Another application:

```properties
management.endpoints.jmx.domain=com.example.inventory.management
```

Result:

```text
com.example.payments.management:type=Endpoint,name=Health
com.example.inventory.management:type=Endpoint,name=Health
```

This helps reduce collisions and clarifies namespaces. However, if two instances of **the same application** live simultaneously in the same JVM, using the same domain can still cause name collisions. In that case, you need an additional instance/context identifier or redesigned ownership.

Do not embed secrets, sensitive tenant identifiers, or filesystem paths into a domain or ObjectName. MBean metadata can be viewed by many management tools.

## 10. MBeanServer Default Domain Is Not the Actuator Domain

Each `MBeanServer` can have a `defaultDomain`:

```java
MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

System.out.println(server.getDefaultDomain());
```

For the platform server, the default value is usually `DefaultDomain`. However, `getDefaultDomain()` is not Spring Boot's `management.endpoints.jmx.domain`.

An MBean using an ObjectName with an **explicit domain**:

```text
org.springframework.boot:type=Endpoint,name=Health
```

will not automatically change according to the server's defaultDomain. DefaultDomain only plays a role when an ObjectName omits the domain part or when the registration mechanism uses the default domain.

Do not solve the need to change the Actuator endpoint namespace by arbitrarily creating another `MBeanServer` just to get a different defaultDomain. Doing so can unintentionally isolate application MBeans from connectors.

## 11. Custom MBeans and Actuator Endpoints Are Two Export Paths

Example Standard MBean created by the application:

```java
public interface CacheAdminMBean {
    long getSize();
    void clearExpired();
}

public final class CacheAdmin implements CacheAdminMBean {
    public long getSize() { return 42; }
    public void clearExpired() {}
}
```

Registration:

```java
MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.cache:type=Cache,name=Primary"
);

server.registerMBean(new CacheAdmin(), name);
```

This MBean's name is determined by the registration code and does not depend on the Actuator domain. When using Spring `MBeanExporter` with `@ManagedResource`, the name can come from the annotation or a naming strategy.

An application can simultaneously have:

```text
java.lang:type=Memory
org.springframework.boot:type=Endpoint,name=Health
com.example.cache:type=Cache,name=Primary
```

These are three different MBean sources, even though they all reside in one `MBeanServer`.

## 12. Inspecting Actual Names Using MBeanServer

How to verify instead of guessing ObjectNames:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

for (ObjectName name : server.queryNames(null, null)) {
    if (name.getDomain().contains("springframework") ||
        name.getDomain().contains("example")) {
        System.out.println(name.getCanonicalName());
    }
}
```

This probe must run **inside the same JVM** and against the **exact MBeanServer** used by the exporter. If Spring Boot or the application configures a custom server, inject the exact instance.

Querying by domain:

```java
ObjectName pattern = new ObjectName(
    "com.example.payments.management:*"
);

for (ObjectName name : server.queryNames(pattern, null)) {
    System.out.println(name.getCanonicalName());
}
```

With a known MBean:

```java
ObjectName expected = new ObjectName(
    "com.example.payments.management:type=Endpoint,name=Health"
);

boolean registered = server.isRegistered(expected);
System.out.println("Registered = " + registered);
```

If `isRegistered` is false, try `queryNames` before concluding the endpoint is disabled: the ObjectName may differ due to a custom domain, unique-name settings, or Boot-version naming rules.

## 13. Using MBeanInfo to Verify the Contract

After finding the exact name:

```java
var info = server.getMBeanInfo(expected);

for (var attribute : info.getAttributes()) {
    System.out.printf(
        "%s: type=%s readable=%s writable=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}

for (var operation : info.getOperations()) {
    System.out.println(operation.getName());
}
```

`MBeanInfo` shows which attributes and operations the MBean actually exposes. Having the right name does not guarantee methods are exposed as expected; for Actuator endpoints, how `@ReadOperation`, `@WriteOperation`, and data types are mapped must be verified separately.

In many Actuator versions, JMX endpoints expose operations according to the Actuator model rather than all Java methods of the endpoint bean. Do not deduce operation names merely by reading implementation method names.

## 14. Testing Domain Changes with Spring Boot Test

An integration test can run with identifying properties:

```java
@SpringBootTest(properties = {
    "spring.jmx.enabled=true",
    "management.endpoints.jmx.domain=com.example.test.management",
    "management.endpoints.jmx.exposure.include=health,info"
})
class JmxNamingIntegrationTest {
    // Inject the right MBeanServer then queryNames by domain.
}
```

A test focused on the domain, rather than assuming every ObjectName value:

```java
ObjectName pattern = new ObjectName(
    "com.example.test.management:*"
);

Set<ObjectName> names = server.queryNames(pattern, null);

assertFalse(names.isEmpty());
assertTrue(names.stream().allMatch(
    name -> name.getDomain().equals(
        "com.example.test.management"
    )
));
```

If you want to assert the exact Health endpoint name, use the name verified for the running Boot version and ensure the health endpoint is actually exposed. Multiple tests in the same JVM should use different domains to avoid colliding with other tests.

Tests should also close the Spring context properly according to its lifecycle. If a context is left behind, MBeans can remain registered and affect subsequent tests.

## 15. Unique Names and Automation Stability

A stable ObjectName helps:

- Administrative scripts invoke endpoints after restarts.
- JConsole/VisualVM easily locate the same entry.
- Monitoring agents use consistent query patterns.
- Alerting retrieve the right MBean.

However, overly generic names easily collide if multiple contexts share a server. There are two strategies:

1. **Stable per application**: fixed domain and a logical endpoint name, suitable when only one instance uses the server.
2. **Unique per instance/context**: adding an appropriate property or namespace, suitable when multiple instances share a JVM.

If using unique names generated from runtime identity, automation must query by pattern or discover new instances. Do not hardcode an ObjectName containing dynamic identity in dashboards as an immutable contract.

A naming strategy should be documented: domain, type, name, instance, environment, quoting rules, and stability across redeploys.

## 16. Diagnosing Common Errors

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| `org.springframework.boot` not visible | Custom domain configured or JMX exposure off | Effective properties and `queryNames` |
| Only `java.lang` visible | Actuator JMX not enabled/exposed or wrong server | Auto-configuration, domain, MBeanServer |
| Health works over HTTP but missing in JMX | Web and JMX exposures are separate | `management.endpoints.jmx.exposure.*` |
| Two contexts and startup fails | Duplicate ObjectName | Domain, unique-names, registration policy |
| Endpoint name differs from expected | Version's naming/unique-name rules | Print canonical ObjectNames |
| Dashboard loses metrics after domain change | Query pattern still uses old domain | Update mapping/monitoring config |
| Custom MBean does not follow Actuator domain | MBean exported via separate exporter or registration | Check annotation/`ObjectNamingStrategy` |
| Remote client cannot see endpoint | Connector points to different server or connected to wrong JVM | Compare MBeanServer, JMX URL |
| Endpoint has right name but operation fails | Contract, signature, or security | `getMBeanInfo`, nested exception |

To distinguish naming issues from network issues, first inspect the registry **inside the application process**. If the MBean is present there but a remote client cannot see it, diagnose the connector and MBeanServer binding.

## 17. Security: JMX Name Is Not Access Control

A predictable ObjectName such as:

```text
org.springframework.boot:type=Endpoint,name=Health
```

does not mean the endpoint is automatically public. Conversely, picking a hard-to-guess domain does not secure the endpoint.

Remote JMX requires proper authentication, TLS, and network isolation. Spring Security rules for `/actuator/**` only govern web traffic as configured; they do not automatically protect a remote RMI connector.

Do not export high-impact management endpoints without defining invocation permissions, auditing, and operation idempotency. Avoid putting sensitive data into ObjectNames because the MBean list can be queried by management clients.

## 18. Configuration Checklist

- [ ] Identify the Spring Boot and Actuator versions in use.
- [ ] Know how `spring.jmx.enabled` is currently taking effect.
- [ ] Know which endpoint IDs are exposed via `management.endpoints.jmx.exposure.*`.
- [ ] Determine `management.endpoints.jmx.domain` and the environment's defaults.
- [ ] Do not confuse the JMX domain with the MBeanServer `defaultDomain`.
- [ ] Do not confuse an endpoint ID with an HTTP path or a Spring bean name.
- [ ] If multiple contexts/JVM instances exist, establish a unique ObjectName strategy.
- [ ] Custom MBeans have independent ObjectNames and naming strategies with clear owners.
- [ ] Integration tests verify actual canonical names and `MBeanInfo`.
- [ ] Remote JMX connector is secured and attached to the right MBeanServer.
- [ ] Monitoring/dashboards are updated if changing domain/unique-name settings.
- [ ] Shutdown/redeploy does not leave stale MBeans behind or collide with new names.

## 19. Key Takeaways

**A Spring Boot Actuator endpoint ID is the logical identifier of an endpoint; a JMX ObjectName is the MBean identifier in an MBeanServer.** A JMX endpoint typically resides under the default domain `org.springframework.boot`, and the `management.endpoints.jmx.domain` property lets you change the Actuator namespace. This domain does not automatically rename custom MBeans or the server's `defaultDomain`. To avoid conflicts and keep management tooling stable, manage domains/unique names appropriately for multi-context setups, verify with `queryNames`, and treat ObjectNames as an operational contract.
