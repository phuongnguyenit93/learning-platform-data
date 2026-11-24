# Distinguishing HTTP and JMX Communication

## 1. An Operational Capability Can Be Accessed Through Multiple Channels

An operator can check application health via an HTTP URL, or open a JMX tool to invoke a management capability inside the JVM. Both serve operations, yet how targets are located, requests are sent, and results are received differ.

In Actuator, you must separate:

- **Endpoint:** the management capability together with the operations it provides.
- **HTTP:** one channel that exposes those operations using URLs and HTTP methods.
- **JMX — Java Management Extensions:** the Java platform's management mechanism, working with managed objects registered in an MBeanServer.

Conceptual model:

~~~text
                 Actuator Endpoint
                  with operations
                    /         \
                   /           \
           Expose HTTP       Expose JMX
           URL + method      MBean + operation
                   \           /
                    \         /
                 Operational logic
~~~

Not every endpoint supports both channels. An endpoint can be technology-independent, or restricted to web/JMX.

This lesson uses the Spring Boot 3.3.x contract, with examples running on Boot 3.3.0 and JDK 21.

## 2. Comparison by Usage

| Criterion | HTTP | JMX |
| --- | --- | --- |
| Locating capability | URL, e.g., /actuator/health | ObjectName in an MBeanServer |
| How it is invoked | HTTP method, query/body when required by operation | Read attributes or invoke operations via JMX API/tools |
| Result representation | Typically JSON for applicable endpoints, with HTTP status/headers | Values and data structures per JMX metadata |
| Common tools | curl, browser for read operations, HTTP clients, health checkers | JConsole or JMX clients |
| Web server required? | Needs appropriate HTTP infrastructure | Web server not required |
| Endpoint selection config | management.endpoints.web.exposure.* | management.endpoints.jmx.exposure.* |
| Access path protection | Web security, TLS, and corresponding network controls | Local access permissions or corresponding JMX connector/agent security |

HTTP is useful when infrastructure already uses URLs to check status. JMX is useful when integrating with Java management tools or accessing the JVM's management model directly. There is no need to enable both if neither consumer needs the other.

JMX is not synonymous with a single network protocol. It can be used directly inside the JVM; remote access requires a connector. The JDK's built-in remote management mechanism uses RMI. See [JDK 21 — Monitoring and Management Using JMX](https://docs.oracle.com/en/java/javase/21/management/monitoring-and-management-using-jmx-technology.html).

## 3. HTTP: Endpoints Are Represented by URLs and Methods

### 3.1. Web Path

With a typical configuration:

~~~text
Endpoint ID: health
Base path:   /actuator
HTTP:        GET http://127.0.0.1:8080/actuator/health
~~~

A simple health response when existing checks are healthy can have the body:

~~~json
{"status":"UP"}
~~~

The body is part of the HTTP response; status code and headers are also part of that communication contract.

The web prefix can be changed via `management.endpoints.web.base-path`. If set to `/manage`, the path can become `/manage/health`, while the ID remains `health`. The management HTTP port can be separated via `management.server.port`. See [Spring Boot 3.3 — Monitoring over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

### 3.2. Suitable Web Infrastructure Is Required

An application with the Actuator starter but without an appropriate web environment will not automatically have a URL on port 8080. Servlet or reactive applications need the corresponding infrastructure to expose endpoints over HTTP.

Example reading only `health` on a web application already running on loopback:

~~~powershell
curl.exe --silent --show-error --include http://127.0.0.1:8080/actuator/health
~~~

If you cannot connect or access is denied, check the process, port, path, exposure, and security policy. Do not copy such a URL straight into a JMX ObjectName field expecting both sides to understand the same syntax.

## 4. JMX: Endpoints Are Registered as Managed Objects

### 4.1. MBean and MBeanServer

An **MBean (Managed Bean)** is a managed object in the JMX model. It publishes metadata so tools know which attributes or operations are available.

An **MBeanServer** is the component that manages registering, finding, and accessing MBeans. Typical operations include:

- Checking whether an ObjectName is registered.
- Reading an object's metadata.
- Reading/writing attributes supported by the object.
- Invoking an operation with the right arguments and type signature.

MBeans are not synonymous with all Spring beans. A Spring-managed object is not automatically an MBean exposed to JMX tools. See [JDK 21 — MBeanServer API](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html).

### 4.2. ObjectName Differs from URL

With the common default naming, the `health` endpoint is exposed as:

~~~text
org.springframework.boot:type=Endpoint,name=Health
~~~

Breaking down this string:

| Part | Role |
| --- | --- |
| `org.springframework.boot` | JMX domain |
| `type=Endpoint` | A key property for categorization |
| `name=Health` | A key property identifying the object in this naming scheme |

This is not an HTTP address and the JMX domain is not a DNS hostname. The colon here separates the domain from the set of key properties.

An ObjectName has a domain and key properties; key property ordering does not represent a URL tree. When locating objects programmatically, use the `ObjectName` API to represent and match them. See [JDK 21 — ObjectName API](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html).

Actual names may also have customized domains or added suffixes to avoid collisions. When a tool cannot find an MBean, inspect the list of registered names instead of guessing a single fixed string.

### 4.3. Spring Boot JMX Is Not All of JVM JMX

In Boot 3.3, `spring.jmx.enabled` does not enable Spring-provided JMX management by default. You can enable it with:

~~~properties
spring.jmx.enabled=true
~~~

Boot selects an appropriate MBeanServer and helps export the corresponding managed components into it. Actuator endpoints use the `org.springframework.boot` domain by default; naming/domain can be customized when needed. See [Spring Boot 3.3 — Monitoring over JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

Disabling this property does not delete all JVM or third-party library MBeans. The JVM provides platform MXBeans for components like memory, threads, and the operating system; they belong to Java's management infrastructure. See [JDK 21 — ManagementFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html).

Therefore, "JConsole still shows JVM info" does not prove Actuator endpoints have been exported over JMX.

## 5. HTTP Exposure and JMX Exposure Are Two Separate Choices

### 5.1. Example Configuring an Application with Both Capabilities

~~~properties
spring.jmx.enabled=true
management.endpoints.web.exposure.include=health,info
management.endpoints.jmx.exposure.include=health
~~~

Equivalent YAML:

~~~yaml
spring:
  jmx:
    enabled: true

management:
  endpoints:
    web:
      exposure:
        include: health,info
    jmx:
      exposure:
        include: health
~~~

If the endpoints are available and the corresponding infrastructures are present:

| Endpoint | Selected for HTTP | Selected for JMX |
| --- | --- | --- |
| health | Yes | Yes |
| info | Yes | No |

The table describes **exposure scope**, not a guarantee that every request from every caller is permitted.

Both lists use endpoint IDs. Do not put `/actuator/health` or `org.springframework.boot:type=Endpoint,name=Health` into `include`.

### 5.2. Enabled State and Exposed State Differ

An endpoint that is disabled or missing required components will not be created just because its name is in `include`.

Conversely, an available endpoint can be selected for JMX while not selected for web. Setting web `exclude` does not automatically set JMX `exclude`, and vice versa.

In Boot 3.3, the default endpoint set exposed on each interface is `health`; on the JMX side, Spring JMX support also needs to be enabled. The `include`/`exclude` properties for each interface are described in [Spring Boot 3.3 — Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

### 5.3. HTTP Does Not Imply Remote JMX Connectivity

`spring.jmx.enabled=true` does not mean a remote JMX port has been opened for other machines. It controls the JMX management provided by Spring.

Similarly, `management.server.port=8081` sets the management HTTP port, not an RMI/JMX port. Do not enter port `8081` into JConsole as if it were definitely a JMX connector.

You must distinguish registering MBeans into an MBeanServer from configuring a transport for remote clients to reach that server.

## 6. Common Endpoints and Technology-Specific Endpoints

### 6.1. Technology-Independent Endpoints

`@Endpoint` describes an endpoint with operations such as `@ReadOperation`, `@WriteOperation`, or `@DeleteOperation`. Actuator can adapt those operations to the corresponding exposure technology. See [Endpoint API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/annotation/Endpoint.html).

The same read operation can be called via HTTP or via a JMX operation when both are supported and exposed. This separates operational logic from how clients connect.

Do not assume complex data always has an identical representation between JSON and JMX tools. Clients should read the contract or metadata of the channel being used.

### 6.2. Technology-Specific Restrictions

| Annotation | Exposure scope by model |
| --- | --- |
| `@Endpoint` | Adaptable for supported technologies |
| `@WebEndpoint` | HTTP only |
| `@JmxEndpoint` | JMX only |

Adding a `WebEndpoint`'s name to JMX `include` does not turn it into a JMX endpoint. Similarly, a `JmxEndpoint` does not automatically get a web URL just by being listed in web `include`. See [WebEndpoint API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/annotation/WebEndpoint.html) and [JmxEndpoint API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/jmx/annotation/JmxEndpoint.html).

This is one reason not to expect the endpoint list in the two tools to be completely identical.

## 7. Local JMX Experiment Without an HTTP Server

The example runs in a Spring Boot **3.3.0** project, JDK **21**, with dependency version management and the Boot run task already configured. The Java code uses syntax compatible with Java 17 and later.

The goals are to verify:

1. An endpoint is registered as an MBean.
2. Its operation can be invoked via `MBeanServer`.
3. Changing web exposure does not alter JMX exposure.

### 7.1. Dependencies and Configuration

In a Gradle project that already has the Boot plugin and 3.3.0 version management, you need:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

This is the `dependencies` snippet merged into the existing project. No Web starter is needed because the experiment does not use an HTTP server.

In `src/main/resources/application.properties`:

~~~properties
spring.jmx.enabled=true
management.endpoints.jmx.exposure.include=health,runtimecheck
management.endpoints.web.exposure.include=health
~~~

### 7.2. Complete Java File

Create `src/main/java/example/actuatorjmx/ActuatorJmxApplication.java`:

~~~java
package example.actuatorjmx;

import java.lang.management.ManagementFactory;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ActuatorJmxApplication {
    @Bean
    public RuntimeCheckEndpoint runtimeCheckEndpoint() {
        return new RuntimeCheckEndpoint();
    }

    public static void main(String[] args) throws Exception {
        SpringApplication application =
                new SpringApplication(ActuatorJmxApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = application.run(args)) {
            MBeanServer server = ManagementFactory.getPlatformMBeanServer();
            ObjectName name = new ObjectName(
                    "org.springframework.boot:type=Endpoint,name=Runtimecheck");
            boolean registered = server.isRegistered(name);
            System.out.println("registered=" + registered);
            if (registered) {
                Object result = server.invoke(
                        name, "state", new Object[0], new String[0]);
                System.out.println("state=" + result);
            }
        }
    }

    @Endpoint(id = "runtimecheck")
    public static class RuntimeCheckEndpoint {
        @ReadOperation
        public String state() {
            return "READY";
        }
    }
}
~~~

The program performs no business logic or external state mutation; the `state` operation only returns a fixed string for comparison.

Points to read:

- The `RuntimeCheckEndpoint` bean has ID `runtimecheck`.
- `WebApplicationType.NONE` keeps the application in non-web mode.
- `MBeanServer` is retrieved directly inside the JVM, without a remote connection.
- The ObjectName in the example uses Boot's default domain and naming rules.
- `invoke` calls the `state` operation with no parameters.
- The context is closed after printing the result.

The `javax.management` package in the code is Java SE's JMX API. Do not change it to `jakarta.management` just because the application uses Spring Boot 3.

### 7.3. Run A: Endpoint Selected for JMX

Run in the project directory containing the Gradle wrapper:

~~~powershell
.\gradlew.bat bootRun
~~~

With the configuration and default MBean name stated above, the two lines printed by the program are:

~~~text
registered=true
state=READY
~~~

The first line confirms the right ObjectName is registered. The second line confirms the operation was invoked through the JMX API.

This is the test program's stdout. Any framework logs are not part of the fixed output string.

### 7.4. Run B: Selecting runtimecheck Only for Web

Run again:

~~~powershell
.\gradlew.bat bootRun --args="--management.endpoints.jmx.exposure.include=health --management.endpoints.web.exposure.include=health,runtimecheck"
~~~

Result:

~~~text
registered=false
~~~

`runtimecheck` is no longer selected for JMX. Having it in the web list does not cause it to be registered in `MBeanServer`.

The experiment still does not start an HTTP server, so the web `include` line does not prove there is a URL to call either. It is only an exposure selection without web infrastructure in this program.

### 7.5. Run C: Excluded from JMX Even Though Included

Keep the base file and run:

~~~powershell
.\gradlew.bat bootRun --args="--management.endpoints.jmx.exposure.exclude=runtimecheck"
~~~

Result:

~~~text
registered=false
~~~

`exclude` takes precedence when selecting the same ID. Web exposure is not modified by this command.

### 7.6. Run D: Disabling Spring-Provided JMX

~~~powershell
.\gradlew.bat bootRun --args="--spring.jmx.enabled=false"
~~~

In this experiment:

~~~text
registered=false
~~~

The program can still call `ManagementFactory.getPlatformMBeanServer()` to query for the ObjectName. Not finding the Actuator MBean does not mean the JMX API or JVM management infrastructure has disappeared.

Each command above is an independent run against the same base file, without carrying over arguments from previous runs.

### 7.7. Scope Verified by the Experiment

The runs verify MBean registration and JMX invocation directly inside the JVM. They do not test HTTP, do not enable remote JMX, and do not test login rules of a remote connector.

If you change the domain or enable unique names to avoid collisions, update how the program searches for the ObjectName. Do not keep the default name string and conclude the endpoint is not exposed.

## 8. Using JConsole on a Running Application

JConsole is a graphical JMX client. With a running application eligible for local attach, you can:

1. Open the `jconsole` tool from the JDK.
2. Select the target Java process you want to inspect.
3. Switch to the MBeans tab.
4. Locate the actual domain and ObjectName.
5. Read the metadata, then invoke operations with the right parameters if permitted.

Local connection depends on environment permissions and attach conditions. In typical usage, the tool and the process run under the same user. See [JDK 21 — Using JConsole](https://docs.oracle.com/en/java/javase/21/management/using-jconsole.html).

The test program in section 7 exits immediately after printing its result, so do not use it as a long-running service for JConsole to connect to. When practicing with the UI, use an actually running application; do not add `sleep` or keep-alive code just to alter the intent of the experiment above.

`MBeanServer` can hold multiple groups of objects: Actuator MBeans, JVM platform MXBeans, or MBeans from other libraries. Select the right domain and object before drawing conclusions about Actuator.

### Remote Connection Is a Separate Configuration Step

If you need JMX from another machine, you must configure the corresponding agent/connector, address, and network conditions. JVM properties like `com.sun.management.jmxremote.port` belong to the JDK management mechanism; merely writing them into `application.yml` does not automatically make the JVM start a remote agent as desired.

Do not copy HTTP authentication policies over to JMX by assuming both channels share the same filters. Determine the authentication, authorization, and encryption mechanisms for the connector in use.

## 9. Securing and Diagnosing by the Right Channel

### 9.1. Web Rules Do Not Automatically Cover JMX

In a web application, Spring Security can protect HTTP requests with appropriate rules. Web filters handling URLs are not a general mechanism applied to every call through `MBeanServer`. See [Spring Boot 3.3 — Spring Security](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html).

Therefore, HTTP returning 401/403 does not prove the corresponding MBean is blocked in JMX. Conversely, failing to connect to remote JMX does not prove HTTP endpoints have stopped serving.

An operation's effect still needs to be evaluated: reading configuration info can leak data; changing log levels or other operational actions can affect the system, regardless of which channel invokes them.

### 9.2. Diagnostic Questions for HTTP

- Are the host, port, and base path right?
- Is a web server running?
- Is the endpoint created and selected for web?
- Does the operation have the right method and parameters?
- How is the request handled by security or a proxy?

### 9.3. Diagnostic Questions for JMX

- Are you connecting to the right JVM/MBeanServer?
- Is Spring's JMX management enabled?
- Is the ID in the JMX exposure set and not excluded?
- Does the ObjectName have the right domain, name, and collision-avoidance properties?
- Do the operation and parameter signature match the metadata?
- If connecting remotely, are the connector/agent and access permissions appropriate?

An `InstanceNotFoundException` from not finding an MBean differs from a connection error to the connector. Similarly, misreading an ObjectName should not be handled by opening extra ports indiscriminately.

## 10. Common Misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| Enabling Actuator means both HTTP and JMX are always available | Each channel has its own infrastructure and exposure conditions |
| JMX is the `/actuator` URL on a different port | JMX uses `MBeanServer`, `ObjectName`, and operations in its own model |
| Every Spring bean appears in JConsole | Beans must be exported through an appropriate management mechanism |
| Opening web `include` also opens JMX `include` | The two selection sets are independent |
| `spring.jmx.enabled=true` immediately opens a remote management port | Registering Spring management differs from configuring a remote connector |
| `management.server.port` is the JMX port | That is the management HTTP port |
| Blocking `/actuator` with web security is enough for both channels | The JMX access path must be evaluated separately |
| Disabling Spring JMX removes all platform MXBeans | JVM management and other libraries have separate lifecycles/configs |
| A JMX client must receive JSON like curl | Result representation follows each channel's contract |
| Without an HTTP server, the application cannot be managed | JMX can operate independently of web |

### Self-Practice

1. To read `health` from an HTTP checker, what conditions must be checked besides having the Actuator starter?
2. Web `include` has `health,info`; JMX `include` has only `health`. With infrastructures ready, which endpoints are selected for each channel?
3. Run the four experimental scenarios and explain which property causes `registered` to change.
4. If JConsole still shows `java.lang:type=Memory` after disabling `spring.jmx.enabled`, is that a contradiction?
5. An application uses `management.server.port=8081` yet JConsole cannot connect to `8081`. Explain where the false assumption may lie.

**Reference hints:** separate the endpoint model, per-channel exposure, and connection transport. HTTP uses URLs; JMX works with managed objects in `MBeanServer`. The two channels can serve the same capability without automatically sharing exposure configuration or access policies.
