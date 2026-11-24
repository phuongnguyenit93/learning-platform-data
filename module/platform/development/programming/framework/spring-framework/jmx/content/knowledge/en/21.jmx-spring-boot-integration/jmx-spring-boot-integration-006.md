# JMX in Spring Boot Applications Running an Embedded Server

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain what an **embedded web server** means in Spring Boot and the relationship between the **JVM**, **Spring ApplicationContext**, **MBeanServer**, and the embedded web server.
- Distinguish **default JVM** MBeans, **Spring JMX** MBeans, **Spring Boot Actuator** MBeans, and MBeans published by **Tomcat/Jetty/Undertow** when actually enabled.
- Understand that opening the embedded server's HTTP port does not mean opening a JMX port, and enabling \`spring.jmx.enabled\` does not automatically enable remote JMX/RMI.
- Configure MBean export for a Spring Boot application running as an executable JAR, with or without Actuator.
- Inspect actual MBeans using \`ManagementFactory.getPlatformMBeanServer()\`, \`ObjectName\`, \`MBeanInfo\`, and JConsole.
- Recognize the differences between MBeans published by embedded Tomcat and application JMX endpoints.
- Consider operational aspects in Docker/Kubernetes: ports, RMI hostname, lifecycle, health/readiness, and access control.
- Establish a verification workflow, prevent ObjectName conflicts, and protect the embedded server's management surface.

## 2. What Is an Embedded Server in Spring Boot?

A web Spring Boot application typically uses an embedded server to run HTTP directly inside the JVM, rather than packaging a WAR and manually deploying it to an external application server.

Example startup structure:

\`\`\`text
java -jar order-service.jar
          |
          v
   JVM process / PID
          |
          +-- Spring ApplicationContext
          |      |
          |      +-- Controllers, Services, Repositories
          |      +-- Application MBeans (if exported)
          |      +-- Spring Boot Actuator (if present)
          |
          +-- Embedded Web Server
          |      +-- Tomcat or Jetty or Undertow
          |      +-- HTTP connectors, threads, sessions...
          |
          +-- Platform MBeanServer
                 +-- JVM built-in MBeans
                 +-- Spring-exported MBeans
                 +-- Server-specific MBeans (if registered)
\`\`\`

These components coexist in **one JVM**, yet have different responsibilities. An embedded web server does not automatically turn all of its internal objects into manageable MBeans. Whether container MBeans appear also depends on the server implementation, version, and configuration.

### 2.1. Common Embedded Servers

| Server | Role | JMX Notes |
| --- | --- | --- |
| Embedded Tomcat | Servlet web server commonly used in Spring Boot | Has a JMX MBean registry mechanism; enabling/registration behavior can differ between embedded and standalone. |
| Embedded Jetty | Servlet web server with its own management module | JMX MBeans or modules are not necessarily enabled automatically in every embedded setup. |
| Embedded Undertow | Web server supporting Servlet and high-performance I/O | JMX publication capability must be verified by version and integration used, not inferred from Tomcat. |
| Reactor Netty | Reactive web server for Spring WebFlux | Not a servlet embedded container; metrics/observability and JMX exposure follow a different mechanism. |

An application may use a server not listed here. Therefore, when designing JMX checks, start from the **running server factory/dependency**, not solely from the Maven starter name.

## 3. Which JMX Layers Exist in an Embedded Application?

### 3.1. JVM Platform MBeans

The JDK typically exposes runtime management MBeans such as:

\`\`\`text
java.lang:type=Memory
java.lang:type=Threading
java.lang:type=Runtime
java.lang:type=ClassLoading
java.lang:type=OperatingSystem
java.lang:type=GarbageCollector,name=...
\`\`\`

JConsole or a JMX client connected to the right JVM can observe memory, threads, class loading, and GC. These MBeans do not require you to write \`@ManagedResource\`.

An application without \`spring.jmx.enabled\` turned on can still have MBeans created by the JVM.

### 3.2. Spring-Exported MBeans

Spring Framework uses \`MBeanExporter\` to publish selected managed beans. Common annotations:

- \`@ManagedResource\`: defines the JMX resource.
- \`@ManagedAttribute\`: exposes getters/setters.
- \`@ManagedOperation\`: exposes actions.
- \`@ManagedOperationParameter\`: describes operation parameters.

For example, a business bean can expose \`QueueDepth\` or \`requestPause()\` regardless of which web server is used.

### 3.3. Spring Boot Actuator JMX Endpoints

If Spring Boot Actuator is present with suitable exposure configuration, endpoints such as health/info/metrics can be published over JMX. This is Boot's **endpoint management** system, not the full Tomcat API.

Actuator endpoints must be checked against your Spring Boot version: JMX MBean names, default exposure, security settings, and data may vary.

### 3.4. Web Server MBeans

Embedded Tomcat/Jetty may register MBeans related to connectors, thread pools, sessions, web applications, or other resources, but only when the corresponding JMX mechanisms are active. Opening \`server.port=8080\` does not confirm those MBeans are registered.

**Important lesson:** these four layers of MBeans can sit in the same \`MBeanServer\` yet are completely distinct.

## 4. Distinguishing the HTTP Port and the JMX Connector

When Spring Boot starts:

\`\`\`properties
server.port=8080
\`\`\`

the application configures an HTTP listener on port 8080 via the server factory. That does **not** open a JMX/RMI port.

Likewise:

\`\`\`properties
spring.jmx.enabled=true
\`\`\`

primarily relates to Spring Boot's JMX auto-configuration and export mechanism when corresponding conditions are met. It is not equivalent to:

\`\`\`text
-Dcom.sun.management.jmxremote.port=9010
\`\`\`

Two connection paths:

\`\`\`text
HTTP client
    |
    | HTTP/HTTPS :8080
    v
Embedded Tomcat/Jetty/Undertow
    |
    v
Spring MVC / WebFlux application

JMX client (JConsole, JMX exporter)
    |
    | Local attach or JMX connector/RMI :9010
    v
MBeanServer
    |
    +-- JVM MBeans
    +-- Spring MBeans
    +-- Container-specific MBeans
\`\`\`

Do not conclude remote JMX is ready just because the HTTP application works. Conversely, local JMX may still respond when the HTTP server has not yet started accepting traffic, depending on lifecycle.

## 5. Basic Spring Boot JMX Configuration

For a Spring Boot application using JMX auto-configuration, a common property is:

\`\`\`properties
spring.jmx.enabled=true
\`\`\`

An annotated resource:

\`\`\`java
package example.monitoring;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=Primary",
    description = "Order queue monitoring"
)
public class QueueManagement {

    @ManagedAttribute(description = "Current pending messages")
    public long getPendingMessages() {
        return 42L;
    }
}
\`\`\`

When the JMX exporter is enabled and metadata annotations are processed, the bean can appear at:

\`\`\`text
com.example.orders:type=Queue,name=Primary
\`\`\`

After starting the application, inspect the MBeanServer to verify. Do not assume \`@Component\` or class annotations alone guarantee the exporter registered it successfully.

### 5.1. Avoiding Duplicate Exporters

In a Boot application, decide clearly whether to use the **Boot-managed exporter** or create a **manual \`MBeanExporter\`**. If both pick the same bean/ObjectName, \`InstanceAlreadyExistsException\` may occur, or one configuration may unexpectedly skip/replace the MBean.

Do not solve this by automatically switching to \`REPLACE_EXISTING\` without identifying who owns the MBean name.

## 6. Is Actuator Required to Use JMX?

**No.** Spring JMX and JVM platform MBeans do not require Spring Boot Actuator.

Example Actuator dependency if the project wants endpoints:

\`\`\`xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
\`\`\`

This adds the Actuator endpoint mechanism. The application still needs appropriate exposure configuration for any endpoint to be published over JMX.

Example properties:

\`\`\`properties
spring.jmx.enabled=true
management.endpoints.jmx.exposure.include=health,info
\`\`\`

This illustrates intent to expose endpoints. Actual endpoint names and lists depend on dependencies, enablement, and Boot version. In modern Spring Boot, check your version's documentation to determine default exposure, include/exclude configuration, and endpoint-specific behavior.

### 6.1. Actuator Web Exposure Differs from JMX Exposure

Properties such as:

\`\`\`properties
management.endpoints.web.exposure.include=health,info
management.endpoints.jmx.exposure.include=health,info
\`\`\`

control **two different exposure channels**. Setting only web exposure does not mean JMX gets the exact same list.

Similarly, HTTP security settings do not necessarily protect a remote JMX connector. JMX routing, TLS, authentication, and permissions must be designed separately.

## 7. Embedded Tomcat and Container MBeans

Tomcat provides its own JMX infrastructure to manage objects like connectors and thread pools. When Tomcat runs as a standalone application server, the set of MBeans can differ from Tomcat embedded inside Spring Boot.

Some Tomcat management names look like:

\`\`\`text
Catalina:type=ThreadPool,name="http-nio-8080"
Catalina:type=GlobalRequestProcessor,name="http-nio-8080"
Catalina:type=Connector,port=8080
\`\`\`

These names are **illustrative examples only**: domain, protocol, connector name, key properties, and actual presence depend on Tomcat version, connector, and whether the JMX mechanism is enabled.

**Do not treat the absence of the \`Catalina\` domain as an error if embedded Tomcat has not enabled container MBean registration.** Nor should you assert that embedded Tomcat always registers the full standalone set.

### 7.1. Registry Configuration in Embedded Tomcat

In some Spring Boot/Tomcat versions, you may need to enable JMX registration for embedded Tomcat via container-specific configuration. Example customization idea:

\`\`\`java
import org.apache.catalina.core.StandardService;
import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
import org.springframework.context.annotation.Bean;

// This is a reference skeleton: APIs must be checked
// against the specific Spring Boot/Tomcat version.
\`\`\`

Tomcat registry-enabling APIs can change across versions and should not be treated as a public stable contract across all Boot releases. Rather than copying an arbitrary old snippet, verify the Tomcat/Boot documentation for your exact version and check \`queryNames\` for actual effect.

Some Tomcat setups use their own registry and \`LifecycleMBeanBase\` mechanism. When running embedded, Spring Boot manages Tomcat's lifecycle, so container MBean registration/unregistration happens according to the corresponding factory/server policy.

## 8. Inspecting JVM, Spring, and Embedded Server MBeans

Example reading domains and MBean names from the platform server:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

for (String domain : server.getDomains()) {
    System.out.println("Domain: " + domain);
}

for (ObjectName name : server.queryNames(null, null)) {
    System.out.println(name.getCanonicalName());
}
\`\`\`

The snippet above can be used in a **lab** for exploration. In production, listing every name can generate large logs and leak topology. Narrow by a known domain or prefix:

\`\`\`java
for (ObjectName name :
        server.queryNames(
            new ObjectName("com.example.orders:*"),
            null)) {
    System.out.println(name.getCanonicalName());
}
\`\`\`

For Tomcat, when the domain is present and you are authorized to diagnose:

\`\`\`java
for (ObjectName name :
        server.queryNames(
            new ObjectName("Catalina:*"),
            null)) {
    System.out.println(name.getCanonicalName());
}
\`\`\`

If the result is empty, you cannot yet conclude the embedded server is down. Check \`server.port\`, lifecycle, version, and how the server registers JMX.

### 8.1. Checking a Specific ObjectName

\`\`\`java
ObjectName expected = new ObjectName(
    "com.example.orders:type=Queue,name=Primary"
);

boolean registered = server.isRegistered(expected);

System.out.println("Registered = " + registered);
\`\`\`

\`true\` only confirms the name exists; to see which interface is exposed, also read \`getMBeanInfo\`.

## 9. Reading MBeanInfo at Runtime

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = server.getMBeanInfo(expected);

System.out.println("Class: " + info.getClassName());
System.out.println("Description: " + info.getDescription());

for (var attr : info.getAttributes()) {
    System.out.printf(
        "Attribute: %s, type=%s, read=%s, write=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.printf(
        "Operation: %s, impact=%d%n",
        operation.getName(),
        operation.getImpact()
    );
}
\`\`\`

Inspect actual metadata after export, especially when an operation can mutate server or application state.

A container MBean may expose additional specialized operations such as managing connectors. If remote JMX is open with high privileges, those operations become a management surface that must be protected.

### 9.1. MBeanInfo Is Not Runtime Value Data

\`MBeanInfo\` describes names, types, read/write permissions, and operations. Actual values are read via \`getAttribute\`, which can trigger the corresponding getter. JMX getters from libraries/containers should not be polled at overly high frequency if their cost has not been evaluated.

## 10. Viewing via JConsole

Steps:

1. Start the Spring Boot JAR application with an embedded server.
2. Open \`jconsole\` from the JDK.
3. Select the right Java process in **Local Process** if running on the same host.
4. Open the **MBeans** tab.
5. Observe the \`java.lang\` domain, the application domain (\`com.example.orders\`), and server-specific domains if present.
6. Select an MBean, inspect **Attributes**, **Operations**, and metadata supported by the tool.
7. Do not invoke operations with side effects in production just to test them.

If JConsole cannot find the app under Local Process, check the PID, user/attach permissions, container namespace, and JDK in use. Do not enable remote JMX just for local viewing when local attach is supported.

### 10.1. Do Not Confuse the Two Port Types in JConsole

When choosing **Remote Process** and entering \`host:port\`, it must be the JVM's JMX connector endpoint, **not** the embedded server's HTTP port.

Example:

\`\`\`text
HTTP:
  localhost:8080

Remote JMX (if separately configured):
  localhost:9010
\`\`\`

Entering \`localhost:8080\` into the Remote Process field will not make JConsole automatically use Actuator HTTP.

## 11. Enabling Remote JMX for a Lab

To observe from another client machine, the JVM needs a remote JMX connector or suitable connection mechanism. With HotSpot/OpenJDK's JMX/RMI management agent, an isolated loopback lab configuration might be:

\`\`\`bash
java \
  -Dcom.sun.management.jmxremote \
  -Dcom.sun.management.jmxremote.port=9010 \
  -Dcom.sun.management.jmxremote.rmi.port=9010 \
  -Dcom.sun.management.jmxremote.authenticate=false \
  -Dcom.sun.management.jmxremote.ssl=false \
  -Djava.rmi.server.hostname=127.0.0.1 \
  -jar order-service.jar
\`\`\`

**Warning:** \`authenticate=false\` and \`ssl=false\` are only appropriate for controlled, isolated lab environments. Do not expose this endpoint to the internet or untrusted networks.

Explanation:

- \`jmxremote.port\`: initial port of the JMX/RMI connector.
- \`jmxremote.rmi.port\`: fixes the RMI server port to avoid dynamic ports that struggle through firewalls/NAT.
- \`java.rmi.server.hostname\`: address the RMI stub advertises to clients; \`127.0.0.1\` fits when the client is on the same host or via a compatible tunnel.
- \`authenticate\` and \`ssl\`: connector security settings that must be configured properly for production.

When connecting from another host, the advertised hostname must be reachable over the actual network path; opening only the registry port is not enough.

### 11.1. Securing Production Remote JMX

A sound operational setup typically includes:

- Dedicated management network or VPN/tunnel.
- Authentication and authorization for the JMX connector.
- TLS with properly configured truststore/certificates.
- Fixed ports with firewalls allowing only trusted sources.
- No direct public internet exposure.
- No passwords passed on the command line or stored in repositories.
- Logging/auditing of important administrative actions.
- Permission checks for state-changing operations.

If an SSH tunnel must be used, ensure both the RMI registry endpoint and the address/port inside the RMI stub are compatible with the tunnel. A single tunnel to the registry port does not solve the second endpoint when dynamic ports are still in use.

## 12. Embedded Server Running in Docker

Docker creates its own network namespace. Points to remember:

1. The container has an internal HTTP listener, e.g., \`8080\`.
2. Port mapping \`-p 8080:8080\` lets external callers reach HTTP; it does **not** forward JMX.
3. If the JVM enables JMX on \`9010\`, decide whether a separate port mapping/tunnel is needed.
4. The RMI stub might advertise \`127.0.0.1\` **inside** the container or a hostname unreachable from the host client.
5. Only map a JMX port when the RMI endpoint matches the mapped port.
6. Do not publish a JMX port to a public network just for quick diagnostics.

For example, a lab container can configure JVM JMX with matching registry/RMI ports and connect over a protected forwarded channel. However, exact setup depends on Docker network mode, host OS, JDK, and the advertised RMI address.

### 12.1. HTTP Health Is Fine Yet JMX Does Not Work?

That is completely possible. The HTTP server and JMX connector are two subsystems. \`GET /actuator/health\` can return results while the JMX remote port is closed or the MBean exporter is disabled.

Conversely, a running JVM with local JMX can still respond when the HTTP server fails startup or cannot bind its port.

## 13. Kubernetes and port-forward

In Kubernetes, a Spring Boot application typically runs inside a Pod with its own network namespace. Common cases:

- An HTTP Service/Ingress routes traffic to the embedded server.
- JMX is used only internally or via port-forward.
- \`MBeanServer\` lives inside the container's JVM, not in the Kubernetes control plane.
- A JMX port does not automatically create a Kubernetes Service; configure one only when needed.
- \`kubectl port-forward\` forwards the chosen port, yet the RMI stub must still point to an address/port reachable by the client.

A lab connection might use:

\`\`\`bash
kubectl port-forward pod/order-service-abc123 9010:9010
\`\`\`

Then JConsole tries connecting to \`localhost:9010\` **if** JVM JMX/RMI is configured compatibly with port-forward and the RMI advertised host/port. The pod name is illustrative only.

**Do not** treat port-forward as an automatic fix for every JMX/RMI issue. In production environments, Pod access and port-forward require appropriate RBAC and Kubernetes auditing.

## 14. Embedded Server and MBean Lifecycle

In Spring Boot, the web server is managed along the lifecycle of the ApplicationContext. This relates to JMX in several ways:

- During context initialization, Spring beans and exporters may be registered before or after certain web server components depending on lifecycle phase.
- The embedded server may only register its own MBeans after the container starts or the registry is enabled.
- When the ApplicationContext closes normally, the relevant components can unregister MBeans and clean up.
- If the JVM is hard-killed, there is no guarantee unregister callbacks or Java cleanup code run.
- When the application restarts, old JMX clients must reconnect to the new JVM process/endpoint.

### 14.1. Do Not Query Too Early

For example, a \`@PostConstruct\` bean expecting to immediately see Tomcat MBeans might query before the container finishes starting. Then \`queryNames\` can be empty even though MBeans appear later.

A better option is checking after Spring Boot publishes \`ApplicationReadyEvent\`, or after a project-defined lifecycle point. Still, verify whether container MBeans are enabled at all: waiting longer will not create MBeans if the registry is turned off.

## 15. Example Checking After ApplicationReadyEvent

\`\`\`java
package example.monitoring;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public final class JmxStartupInspector {

    @EventListener(ApplicationReadyEvent.class)
    public void inspectAfterStartup() throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName application = new ObjectName(
            "com.example.orders:type=Queue,name=Primary"
        );

        System.out.println(
            "Application MBean registered: "
                + server.isRegistered(application)
        );

        ObjectName tomcatPattern =
            new ObjectName("Catalina:*");

        int tomcatMBeans =
            server.queryNames(tomcatPattern, null).size();

        System.out.println(
            "Tomcat domain MBeans (if configured): "
                + tomcatMBeans
        );
    }
}
\`\`\`

This example prints the count of MBeans in the \`Catalina\` domain as an observation, **not treating 0 as a startup error**. If the application uses Jetty, Undertow, or Reactor Netty, the Tomcat domain does not apply and should be replaced with a suitable check.

In production, avoid logging the entire list of MBean names on every startup if it contains sensitive information or creates noisy logs.

## 16. Embedded Server Metrics and JMX

Some web server performance data may be available as JMX MBeans:

- Thread pool size, busy threads, connection count.
- Request count, bytes sent/received, processing time.
- Session count and container metrics.
- Connector status and lifecycle.

However, these data sources vary by server and version. Spring Boot Actuator/Micrometer can provide metrics in a more standardized way for dashboards and time-series systems.

| Need | Usually Suitable Choice |
| --- | --- |
| Direct JVM debugging | JConsole + platform MBeans |
| Observing a specific server MBean | JMX metadata and server-specific MBean |
| Long-term metrics via Prometheus/Grafana | Micrometer/Actuator or compatible exporter |
| Health/readiness monitoring | Actuator health/readiness probes or suitable health system |
| Controlling application MBeans | Spring JMX exporter with protected operations |
| Verifying JMX contract | Integration tests reading \`MBeanInfo\` |

Do not use JMX as the sole source of metrics if the system requires retention, alerting, aggregation, and multi-instance visibility.

## 17. Spring Boot Actuator and the Management Port

In Spring Boot, HTTP management endpoints can share the application port or use a separate port:

\`\`\`properties
server.port=8080
management.server.port=8081
\`\`\`

\`management.server.port=8081\` relates to the **HTTP management web server/context**, not a remote JMX/RMI port. The JMX registry and connector remain a separate subsystem.

A concurrent setup might be:

\`\`\`text
Main HTTP port:         8080
Actuator HTTP port:     8081
JMX remote port:        9010 (if separately configured)
\`\`\`

This avoids the mistake of "changing \`management.server.port\` and wondering why JConsole still cannot connect". JConsole uses a JMX connector, not Actuator HTTP.

## 18. Securing the Management Surface

The embedded server and JMX can run in the same JVM with the service process's privileges. Actions such as stopping a connector, changing thread pools, or stopping workers can have major impact. Therefore:

1. **Minimize exposed MBeans/operations.** Do not export all service methods via reflection without control.
2. **Set proper access permissions.** Remote JMX needs authentication, TLS, and source restrictions.
3. **Separate operation permissions.** Separate roles that read metrics from roles that invoke state-changing operations.
4. **Avoid leaking secrets.** Getters and ObjectNames should not contain passwords, tokens, or PII.
5. **Confirm the environment before invoking.** You could mistake staging for production JVMs if they use identical ObjectNames.
6. **Design safe operations.** Include validation, concurrency control, and idempotency where appropriate.
7. **Do not retry blindly.** If an invocation times out, the operation may already have executed on the server.
8. **Maintain appropriate auditing.** For impactful management actions, record actor, timestamp, and outcome without exposing credentials.

Even if Spring Boot only runs HTTP on loopback or inside a private container, misconfigured remote JMX exposure can become a powerful entry point into the JVM.

## 19. Common Errors and How to Diagnose Them

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| JConsole sees JVM but not application MBeans | \`spring.jmx.enabled\` off, bean not exported, wrong ObjectName. | Check exporter, annotation, and \`isRegistered\`. |
| No Tomcat domain | Registry/container MBeans not enabled or different server used. | Identify server implementation, version, and container JMX config. |
| HTTP serves normally, remote JMX connection refused | JMX remote agent not running, wrong port. | Check JVM flags and listeners. |
| JMX port open yet client times out | Wrong RMI advertised hostname/port or firewall/NAT. | Check \`java.rmi.server.hostname\`, \`jmxremote.rmi.port\`. |
| \`spring.jmx.enabled=true\` configured yet no Actuator MBean | Missing Actuator or mismatched JMX exposure/enablement. | Check dependency and management properties for your version. |
| Duplicate \`ObjectName\` | Multiple exporters or manual registrations. | Check registration policy and ownership. |
| Container moved Pods yet JConsole keeps old connection | JVM restarted / new connector. | Reconnect to the right Pod/endpoint. |
| \`queryNames\` empty in \`@PostConstruct\` | Container lifecycle incomplete or registry not enabled. | Check after ready point and actual config. |
| MBean exists yet operation is missing | Metadata assembler/management interface mismatch. | Read \`MBeanInfo\`. |
| Metrics lack tags/time-series | JMX is only a management API, not metrics storage. | Use an appropriate collector/Micrometer/Actuator. |

## 20. Integration Testing for Embedded Server Applications

An integration test should verify both the web application and the JMX contract, without depending on server-specific domains unless the project deliberately configures them.

Example concept with Spring Boot Test:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "spring.jmx.enabled=true"
)
class EmbeddedJmxIntegrationTest {

    @Autowired
    Environment environment;

    @Test
    void expectedApplicationMBeanIsExported() throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.orders:type=Queue,name=Primary"
        );

        assertTrue(
            server.isRegistered(name),
            "Expected application MBean is missing"
        );

        MBeanInfo info = server.getMBeanInfo(name);

        assertTrue(
            java.util.Arrays.stream(info.getAttributes())
                .anyMatch(a ->
                    "PendingMessages".equals(a.getName())
                    && a.isReadable()
                    && !a.isWritable()
                )
        );
    }
}
\`\`\`

The example requires \`QueueManagement\` to be created in the test ApplicationContext and the exporter to register into the platform MBeanServer. For tests running in parallel or sharing contexts, use unique ObjectNames and cleanup to avoid conflicts.

Do not assert "\`Catalina:*\` always has MBeans" in a shared test across Tomcat, Jetty, and Undertow. Only check server-specific MBeans when that is an explicit configured feature of the application.

### 20.1. Testing Stop and Restart

A separate lifecycle test can:

1. Start the context with the embedded server.
2. Confirm the HTTP port is ready and the application MBean is registered.
3. Close the context.
4. Confirm MBeans owned by the exporter are unregistered.
5. Restart a context with the same \`ObjectName\` in an isolated environment and confirm there is no \`InstanceAlreadyExistsException\`.

Do not run this test against a live production application, as closing the context stops the server serving traffic.

## 21. Monitoring Multiple Instances

If multiple Spring Boot instances run together:

\`\`\`text
instance A: order-service-1, PID 101
instance B: order-service-2, PID 102
instance C: order-service-3, PID 103
\`\`\`

each JVM has its own MBeanServer. The same ObjectName can exist across all JVMs without conflict because the registries are separate.

To connect with JConsole, choose the **right instance/PID/JMX endpoint**. Centralized metrics need instance/pod/host labels supplied by the collector; \`ObjectName\` does not automatically identify the entire cluster topology.

If a local JMX proxy inside instance A queries an MBean by that name, it queries JVM A's registry; it does not automatically forward to instance B's MBean.

## 22. Distinguishing Embedded vs. External Servlet Containers

| Aspect | Spring Boot embedded server | WAR running in external container |
| --- | --- | --- |
| Web server lifecycle management | Coordinated by Spring Boot/server factory inside app JVM. | External container manages the web server; WAR is just a deployed application. |
| Container MBean source | Depends on embedded server and JMX enabling mechanism. | May have registry/management configured by the standalone container. |
| JMX JVM process | JVM running the executable JAR. | JVM running the application server hosting one or more WARs. |
| Management boundary | Usually tied to one Spring Boot app/JVM. | May host multiple applications in the same JVM. |
| HTTP port | Usually via \`server.port\`. | Usually configured by the external container. |
| JMX connector | Configured separately at JVM/connector level. | May be provided by the container/operator. |

When migrating an application from external Tomcat to embedded Tomcat, **preserving all container MBeans is not guaranteed**. Re-verify domains/names, server registry, and monitoring tools that depended on the old MBeans.

## 23. Practice Exercises

### Exercise 1 — Distinguish JMX Layers

Create a web Spring Boot application with embedded Tomcat, a simple \`@ManagedResource\`, and \`spring.jmx.enabled=true\`. Run local JConsole, find \`java.lang\`, the application domain, and the Tomcat domain if present.

**Goal:** distinguish JVM MBeans, Spring MBeans, and container MBeans.

### Exercise 2 — HTTP Port Is Not JMX

Set \`server.port=8090\`. Call the HTTP API with a browser; open JConsole Remote Process, try \`localhost:8090\` in a lab environment, and note this is not a JMX connector. Then connect JConsole via Local Process to the right JVM.

**Goal:** avoid confusing the HTTP listener with a JMX endpoint.

### Exercise 3 — Actuator JMX Exposure

Add the Actuator dependency, enable allowed JMX endpoints, and inspect the domains/operations runtime actually exports. Compare with the web endpoint list.

**Goal:** understand exposure by HTTP/JMX channel.

### Exercise 4 — Different Embedded Servers

Run the same application with Tomcat and then Jetty in two isolated test environments. Compare the server-specific domains registered, without assuming a domain must always appear.

**Goal:** understand implementation-specific behavior.

### Exercise 5 — Container Network

In a controlled lab environment, configure remote JMX with fixed ports using Docker port mapping or Kubernetes port-forward; verify the address/port advertised by the RMI stub matches the connection path.

**Goal:** understand why opening the registry port alone may not make JConsole connect successfully.

### Exercise 6 — Security Checklist

List the operations published via \`MBeanInfo\`, identify operations with side effects, and propose read/control permissions, TLS, and auditing.

**Goal:** avoid creating dangerous management endpoints in production.

### Exercise 7 — Restart Lifecycle

Start and stop the context in an integration test, verifying application MBeans are unregistered and cleanly re-registered on restart.

**Goal:** prevent ObjectName conflicts and registry leaks.

## 24. Review Questions

**1. What is an embedded server?** A web server running inside the same JVM and coordinated by the Spring Boot application, typically when running an executable JAR.

**2. Does setting \`server.port\` open a JMX port?** No. It configures the web server's HTTP listener.

**3. Does setting \`spring.jmx.enabled=true\` automatically open remote JMX/RMI?** No. Remote connectors must be configured separately.

**4. Is Actuator required to use Spring JMX?** No. Spring JMX and JVM platform MBeans can operate independently.

**5. Why might Tomcat MBeans not appear when running embedded?** Container self-registration of MBeans may not be enabled or differs from standalone; check configuration/version.

**6. Which JVM MBeans can be inspected even without an application exporter?** For example, \`java.lang:type=Memory\`, \`java.lang:type=Threading\`, or \`java.lang:type=Runtime\`.

**7. Is \`management.server.port\` a JMX port?** No. It relates to Boot's HTTP management server when used.

**8. If multiple instances share the same \`ObjectName\`, do they collide?** No, if they are in separate MBeanServers/JVMs.

**9. How do you verify an MBean is actually registered?** Use the right MBeanServer and call \`isRegistered\`, \`queryNames\`, and \`getMBeanInfo\`.

**10. Does JMX replace a metrics collector and time-series database?** No. JMX is a management/observation API; long-term monitoring requires an appropriate pipeline.

## 25. Summary

A Spring Boot application running an **embedded server** is one JVM hosting the business application, HTTP server, and management components. JMX can concurrently expose MBeans from the JVM, Spring, Actuator, and the embedded web server — yet the extent of publication depends on configuration and implementation, not merely on opening an HTTP port.

To use JMX properly, distinguish **\`spring.jmx.enabled\`**, **Actuator JMX exposure**, **container-specific MBeans**, and the **remote JMX connector**. After startup, inspect actual \`MBeanInfo\` on the right JVM; when deploying to containers/Kubernetes, also account for RMI advertised host/port, lifecycle, and access permissions. In production, expose only the needed management surface and protect JMX connectivity separately from HTTP.

## References

- Spring Boot Reference — Embedded Web Servers: https://docs.spring.io/spring-boot/reference/web/servlet.html
- Spring Boot Reference — JMX: https://docs.spring.io/spring-boot/reference/actuator/jmx.html
- Spring Boot Reference — Monitoring and Management over HTTP: https://docs.spring.io/spring-boot/reference/actuator/monitoring.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Apache Tomcat Documentation — Monitoring and Management: https://tomcat.apache.org/tomcat-10.1-doc/monitoring.html
- Java SE 21 — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 — \`ManagementFactory\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html