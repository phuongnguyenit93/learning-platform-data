# Handling MBean Name Collisions, Wrong Management Ports, and Environment Config Conflicts

## 1. Understand Three Layers Before Fixing the Incident

An application may serve business APIs normally while monitoring tools still cannot reach Actuator. Conversely, the application may fail immediately at startup because MBean registration or port binding fails. Determine which layer failed before changing configuration.

- **JMX** is Java's object management mechanism. An **MBean** is an object exposed for monitoring or management; **MBeanServer** manages these objects; **ObjectName** is each MBean's registration name.
- **Management HTTP** is the access path to Actuator endpoints over HTTP, such as the health path. It has a listen address, port, protocol, and path.
- **Effective configuration** is the final value Spring Boot uses after evaluating config files, profiles, environment variables, and startup arguments. A value seen in one file is not necessarily the value currently in effect.

Picture an orders service facing three different questions: "What is this managed object named?", "Where should the monitoring tool connect?", and "Who decided those values?". MBean collisions answer the first, wrong ports answer the second, and per-environment config precedence traces the third.

This lesson uses Spring Boot 3.3.x for configuration keys. YAML snippets apply to an existing web app that already has Actuator; they are not a full project. The JMX example in section 3 is a standalone Java program runnable with JDK 17 or later.

## 2. Classifying by Observable Evidence

| Symptom | Branch to check first | Evidence to collect |
| --- | --- | --- |
| Cause chain contains `InstanceAlreadyExistsException` | Two registrations with the same name in one MBeanServer | Full ObjectName, registering component, context lifecycle |
| Startup reports port already in use or `BindException` | Cannot open listening socket | Actual port, bind address, process holding the port |
| Client reports connection refused | Nothing listening at the called address, or connection rejected | App status, sockets inside the exact host/container |
| Connection times out | Network path, firewall, routing, or target host | Test from near the app first, then from the monitoring host |
| HTTP 404 | Path, port, exposed endpoints, or target service | Full URL, endpoint config, process identity |
| HTTP 401 or 403 | Authentication/authorization policy at app or proxy | Component generating response, credentials, and permissions |
| HTTP 503 from health | Endpoint answered yet reported unhealthy per status mapping | Health payload and component causing the status |
| Fails in only one environment | Config or infrastructure differences | Effective profile, runtime flags, env vars, port mappings |

HTTP symptoms are investigation leads, not absolute conclusions. For instance, 404 can come from a proxy; 200 can come from a different app occupying that port. Always verify where the response originated.

Do not stop at the outermost `BeanCreationException` line as the final cause. Read the `Caused by` chain to find the specific exception and resource: an MBean name or an address/port.

## 3. MBean Name Collisions: Conflict Inside the Registry

### 3.1. ObjectName Is Not a Spring Bean Name

An MBean name looks like:

```text
com.example.orders:type=Endpoint,name=Health
```

`com.example.orders` is the domain; the part after the colon consists of key–value pairs. Two MBeans cannot register the same ObjectName inside the same MBeanServer. Reordering key–value pairs does not create a new name. You can use `getCanonicalName()` to compare names in canonical form. See [Java 21 ObjectName](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html).

This scoping prevents a false inference: two separate JVMs can have identically named MBeans without colliding. Conversely, two Spring ApplicationContexts inside the same JVM can share one MBeanServer and register identical names.

Situations to distinguish:

1. Two legitimate contexts both export an endpoint without disambiguating names.
2. One object is registered twice by two MBean export mechanisms.
3. An old context or manual registration failed to unregister its MBean on shutdown.
4. An MBean from another library has its own naming rules outside Actuator config control.

Changing `server.port` does not fix any of those situations. The HTTP port plays no part in ObjectName identity.

### 3.2. Standalone Java Experiment

Save all code below as `MBeanCollisionDemo.java`. The program creates its own private MBeanServer so the experiment does not depend on MBeans already present in the JVM.

```java
import javax.management.InstanceAlreadyExistsException;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

public class MBeanCollisionDemo {
    public interface CounterMBean {
        int getValue();
    }

    public static class Counter implements CounterMBean {
        private final int value;

        public Counter(int value) {
            this.value = value;
        }

        @Override
        public int getValue() {
            return value;
        }
    }

    public static void main(String[] args) throws Exception {
        MBeanServer server = MBeanServerFactory.createMBeanServer();
        ObjectName first =
                new ObjectName("com.example.lab:type=Counter,name=shared");
        ObjectName reordered =
                new ObjectName("com.example.lab:name=shared,type=Counter");
        ObjectName second =
                new ObjectName("com.example.lab:type=Counter,name=worker-2");

        try {
            System.out.println("same-name=" + first.equals(reordered));
            server.registerMBean(new Counter(1), first);

            try {
                server.registerMBean(new Counter(2), reordered);
            } catch (InstanceAlreadyExistsException exception) {
                System.out.println(exception.getClass().getSimpleName());
            }

            System.out.println("first-value="
                    + server.getAttribute(first, "Value"));

            server.registerMBean(new Counter(2), second);
            System.out.println("second-value="
                    + server.getAttribute(second, "Value"));

            server.queryNames(
                    new ObjectName("com.example.lab:type=Counter,*"), null)
                    .stream()
                    .map(ObjectName::getCanonicalName)
                    .sorted()
                    .forEach(System.out::println);
        } finally {
            if (server.isRegistered(second)) {
                server.unregisterMBean(second);
            }
            if (server.isRegistered(first)) {
                server.unregisterMBean(first);
            }
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
```

Compile and run in the directory containing the file:

```shell
javac --release 17 MBeanCollisionDemo.java
java MBeanCollisionDemo
```

Stdout:

```text
same-name=true
InstanceAlreadyExistsException
first-value=1
second-value=2
com.example.lab:name=shared,type=Counter
com.example.lab:name=worker-2,type=Counter
```

Three points to take from the output:

- Swapping `type` and `name` order still yields the same name.
- A failed second registration does not replace the first object; the first MBean's value remains 1.
- Changing the second object's identifier allows both to coexist in the same registry.

The `finally` block cleans up only the experiment's MBeans. In real apps, the registering component must also own unregistration; do not arbitrarily unregister another library's MBeans. Registration contract and exceptions are described in [MBeanServer.registerMBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html#registerMBean(java.lang.Object,javax.management.ObjectName)).

### 3.3. Fixing the Exact Causing Component

For Actuator endpoints, the following config explicitly enables JMX, sets a domain, and enforces unique names:

```yaml
spring:
  jmx:
    enabled: true
    unique-names: true

management:
  endpoints:
    jmx:
      domain: com.example.orders
      exposure:
        include: health,info
```

Spring Boot 3.3 supports `spring.jmx.unique-names` to prevent name collisions across multiple contexts; the endpoint domain is set with `management.endpoints.jmx.domain`. Details are in [Spring Boot 3.3 Monitoring and Management over JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

After fixing, verify in a JMX tool that the expected MBeans exist. When names include runtime-generated suffixes, do not hardcode that suffix into long-term monitoring configs; query appropriate names and confirm the target object.

If two apps/contexts must be distinguished separately, assign different endpoint domains such as `com.example.orders.blue` and `com.example.orders.green`. If both still inherit the same domain from deployment config, adding the domain key alone does not resolve the collision.

If the error belongs to a custom MBean, check the naming rules of the MBean exporter mechanism and the `objectName` attribute on `@ManagedResource` if used. If it belongs to a third-party library, consult that library's naming configuration. Spring's naming rules are explained in [Controlling ObjectName Instances](https://docs.spring.io/spring-framework/reference/integration/jmx/naming.html).

If the same object is exported twice, fix the duplicate registration or lifecycle. Enabling unique names everywhere may let the app start while leaving two management entries for the same resource. If the error only appears on repeated runs inside one JVM, inspect context closing and resource cleanup rather than just changing domains.

### 3.4. When JMX Is Not Needed

If the app uses Actuator solely over HTTP, you can intentionally disable Spring's MBean exporting:

```yaml
spring:
  jmx:
    enabled: false
```

If you still need other Spring MBeans yet do not want Actuator endpoints exposed over JMX:

```yaml
management:
  endpoints:
    jmx:
      exposure:
        exclude: "*"
```

The two options have different scopes. `spring.jmx.enabled` does not disable the entire JVM JMX subsystem and is not guaranteed to stop libraries from registering MBeans themselves. Excluding JMX endpoints does not exclude HTTP endpoints either. These boundaries are noted in [Spring Boot JMX documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

Do not enable `spring.main.allow-bean-definition-overriding` to fix an ObjectName error: that affects Spring bean definitions, not MBeanServer registration. Nor should you switch to a policy of ignoring/replacing existing MBeans just to suppress exceptions before knowing which object is being kept.

## 4. Wrong Management Port: Reconstructing the Address from the Client Side

### 4.1. Distinguishing App Port, Actuator Port, and Remote JMX Port

| Configuration | Role | Example |
| --- | --- | --- |
| `server.port` | HTTP port of the web application | 8080 |
| `management.server.port` | Management HTTP port when separated | 9091 |
| `com.sun.management.jmxremote.port` | JVM remote JMX config | Not an HTTP health port |

Enabling `spring.jmx.enabled=true` does not mean a remote JMX port has been opened. Remote JMX connectivity also depends on connectors, JVM flags, and networking. Do not use `curl` against a JMX/RMI port to test an HTTP endpoint.

Without a separate management port, Actuator shares the application's HTTP port. When separated, monitoring tools must target the management port and corresponding path. Two independent processes can still contend for the same address/port in one network namespace even though they cannot collide on ObjectNames.

### 4.2. Separate Port and Changed Path Configuration

The example below is for a Servlet application running directly on a development machine:

```yaml
server:
  port: 8080
  servlet:
    context-path: /orders

management:
  server:
    port: 9091
    address: 127.0.0.1
    base-path: /internal
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,info
```

In this example with no TLS or custom remapping on the health endpoint:

- Business port is 8080, with context path `/orders`.
- Management health lives at `http://127.0.0.1:9091/internal/manage/health`.
- Do not prepend `/orders` onto the separated management URL.

Path rules for shared vs. separate ports are defined in [Monitoring and Management Over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

Test from the machine running the application, using `curl.exe` on Windows:

```powershell
curl.exe -i http://127.0.0.1:9091/internal/manage/health
```

Do not assume every app yields the exact same JSON or HTTP code: health depends on active checks, and access can be governed by Spring Security or proxies. Record the status, response body, and relevant logs.

If `management.server.port` is not set, in the same Servlet example the shared-port URL is built from the app context path and Actuator base path, such as `http://127.0.0.1:8080/orders/manage/health`, ignoring settings specific to a separate management server. For WebFlux, check `spring.webflux.base-path` instead of the Servlet context path key.

### 4.3. Port Values to Read Literally

- No separate management port set: uses the main web port.
- A port different from the main port set: opens a separate management HTTP server if supported by app and config.
- `management.server.port=0` set: requests picking an available port; read the actual port from startup logs/events or test utilities. Zero in config is not a port for clients to call.
- `management.server.port=-1` set: disables management HTTP access; do not use this value when HTTP health must stay active.

`management.server.address` sets a dedicated bind address when the management port differs from the main port. The loopback config in the example suits local calls on the same host; it will not make the endpoint reachable from another host.

Look up port and address keys in the [Spring Boot 3.3 Application Properties appendix](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

### 4.4. Checking Sockets and Network Mappings

If the app fails to start because 9091 is in use, on Windows you can inspect the listening process:

```powershell
Get-NetTCPConnection -LocalPort 9091 -State Listen |
    Select-Object LocalAddress, LocalPort, OwningProcess
```

Inspect the process by the actual PID returned. Do not kill a process merely because it holds the port: first determine whether it is an old build of your app or another service.

For containers, write out the hop-by-hop path. For example, a container listening on 9091 mapped as `19091:9091`:

```text
Host:19091 -> container:9091 -> /internal/manage/health
```

Clients on the host call port 19091; the process inside the container uses port 9091. Port mapping does not automatically change `management.server.port`.

If the app inside a container binds only to `127.0.0.1`, traffic arriving on the container's network interface may fail to reach the listener. Pick the bind address according to your deployment network model while updating access policies appropriately. When calls succeed inside the container yet fail from the host, check port mapping and bind address before editing the endpoint.

With Kubernetes or reverse proxies, also verify Service `targetPort`, probe path, HTTP/HTTPS scheme, and path rewrite rules. A container declaring a port does not mean every network layer already routes to it.

## 5. Environment Conflicts: Find the Winning Value, Then Find Its Source

### 5.1. One Correct File Does Not Prove the App Uses It

Suppose the same key appears across sources:

| Source | `management.server.port` |
| --- | --- |
| `application.yml` inside JAR | 9091 |
| `application-prod.yml` inside JAR | 9191 |
| Environment variable `MANAGEMENT_SERVER_PORT` | 9291 |
| Runtime argument `--management.server.port=9391` | 9391 |

In standard Spring Boot startup with profile `prod` active and no higher-precedence source or custom argument loading, the effective value is **9391**. Removing the command-line argument still lets environment variable 9291 override 9191 in the profile file.

Among common sources, command-line arguments can override `SPRING_APPLICATION_JSON`, Java system properties, environment variables, and config data. This is a diagnostic slice, not the complete precedence list across all tests or Servlet environments. See [Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

### 5.2. Practice with a Shared Config and a Profile

Suppose the Actuator web app is packaged as `actuator-lab.jar`. The two files below are placed in project resources before packaging.

`application.yml`:

```yaml
spring:
  application:
    name: actuator-lab
  jmx:
    enabled: false

server:
  port: 8080

management:
  server:
    port: 9091
  endpoints:
    web:
      exposure:
        include: health,info
```

`application-prod.yml`:

```yaml
management:
  server:
    port: 9191
```

In a dedicated PowerShell window for the lab, set the environment variable and run:

```powershell
$env:MANAGEMENT_SERVER_PORT = '9291'
java -jar actuator-lab.jar --spring.profiles.active=prod --management.server.port=9391
```

Under the conditions stated in section 5.1, logs must show management HTTP using port 9391. In another window, call:

```powershell
curl.exe -i http://127.0.0.1:9391/actuator/health
```

Stop the app with Ctrl+C, drop the port argument, and run again:

```powershell
java -jar actuator-lab.jar --spring.profiles.active=prod
```

This time expect port 9291. To remove the environment variable source for the next test:

```powershell
Remove-Item Env:MANAGEMENT_SERVER_PORT
java -jar actuator-lab.jar --spring.profiles.active=prod
```

With no other source overriding it, the management port returns to 9191. Using a dedicated PowerShell window prevents the lab from altering environment variables in other sessions. If expected ports are occupied, resolve socket conflicts before evaluating results.

This lab changes one source at a time to demonstrate precedence; it does not require exposing `env` or `configprops` over the network.

### 5.3. Profiles Select Config, They Do Not Guarantee the Final Value

Check active profile names in startup logs. Situations easily missed:

- Dev machines use `local`, deployment uses `prod`, while test tasks activate another profile.
- Startup arguments override the active profile relative to the file.
- Multiple profiles are active together and share overlapping keys.
- Profile groups or includes pull in extra configs beyond the profile you had in mind.

Set `spring.profiles.active` in an appropriate shared or startup source; do not put it inside `application-prod.yml` itself expecting it to self-activate prod. See [Spring Boot 3.3 Profiles](https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html).

When multiple profiles are needed, document their ordering and scope of responsibility. A monitoring feature profile should not silently alter business ports unless the deployment contract requires it.

## 6. Configuration Traps That Make Repeated Edits Have No Effect

### 6.1. Mistaking Property Names or Environment Variable Names

| Canonical property | Corresponding environment variable |
| --- | --- |
| `server.port` | `SERVER_PORT` |
| `management.server.port` | `MANAGEMENT_SERVER_PORT` |
| `management.server.address` | `MANAGEMENT_SERVER_ADDRESS` |
| `management.endpoints.web.base-path` | `MANAGEMENT_ENDPOINTS_WEB_BASEPATH` |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |
| `spring.jmx.enabled` | `SPRING_JMX_ENABLED` |
| `spring.jmx.unique-names` | `SPRING_JMX_UNIQUENAMES` |

The conversion rule from canonical name to environment variable replaces dots with underscores, removes dashes, and uppercases letters. With deployment management platforms, inspect the final value injected into the process, not just UI config forms.

Do not confuse HTTP management keys with JMX keys, and do not copy a key from another Spring Boot version assuming it still works. A misspelled key can quietly sit as an unused property read by nothing.

### 6.2. Placing Java System Properties in the Wrong Position

Example using a Java system property:

```shell
java -Dmanagement.server.port=9291 -jar actuator-lab.jar
```

Example using a Spring Boot argument:

```shell
java -jar actuator-lab.jar --management.server.port=9391
```

`-D...` must be processed by the Java launcher before `-jar`. Putting `-Dmanagement.server.port=9291` after the JAR filename no longer passes a Java system property. When both sources exist as in the examples and standard CLI parsing is active, `--...` arguments take higher precedence.

In containers, inspect both the final entrypoint command and variables like `JAVA_TOOL_OPTIONS` if used; an old JVM flag can still be injected without appearing in application YAML.

### 6.3. Loading the Wrong External File Outside the JAR

A config directory mounted into a container can differ from source code contents. When replacing files, confirm the path inside the container and the deployed build actually running.

Read `spring.config.location` carefully because it replaces default config search locations; `spring.config.additional-location` adds locations. If you need proof of which files were loaded, temporarily raise logging for `org.springframework.boot.context.config` in a controlled diagnostic environment. The `--debug` auto-configuration report shows auto-config conditions, though it does not replace tracing every property value.

### 6.4. Broken YAML Structure and Endpoint Exclusions

Two top-level `management:` blocks at the same level inside one YAML document are not a safe way to merge configuration. Keep a unified tree and check indentation.

When using a wildcard, wrap it in quotes:

```yaml
management:
  endpoints:
    web:
      exposure:
        exclude: "*"
```

This configuration intentionally excludes endpoints from HTTP; changing ports will not bring them back. If an endpoint is both included and excluded, inspect exposure rules before assuming the endpoint failed to initialize.

Separate three questions: is the endpoint enabled, is it exposed on the active channel, and is the client authorized to access it? Increasing `include` alone cannot answer the other two.

## 7. Verifying Configuration Without Expanding the Management Surface

You need at least two kinds of evidence:

1. **Effective configuration values:** port, address, path, profile, and JMX keys.
2. **Observed runtime behavior:** actual listening socket, responding URL, and registered MBeans.

If the app starts, use a debugger or a temporary diagnostic snippet that reads only selected keys from Spring's `Environment`. Do not print the entire process environment, as it may contain secrets.

The snippet below illustrates a Spring component placed in an application-scanned package. It requires Spring Boot dependencies and does not run standalone via `javac` with only the JDK.

```java
package com.example.actuatorlab;

import java.util.Arrays;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ManagementConfigProbe implements ApplicationRunner {
    private final Environment environment;

    public ManagementConfigProbe(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("activeProfiles="
                + Arrays.toString(environment.getActiveProfiles()));

        String[] keys = {
                "server.port",
                "management.server.port",
                "management.server.address",
                "management.server.base-path",
                "management.endpoints.web.base-path",
                "spring.jmx.enabled",
                "spring.jmx.unique-names",
                "management.endpoints.jmx.domain"
        };

        for (String key : keys) {
            System.out.println(key + "="
                    + environment.getProperty(key, "<not explicitly set>"));
        }
    }
}
```

When a key is not explicitly set in Environment, the message above does not mean the Spring Boot component lacks a default. For example, the HTTP base path can still use the configuration object's default. The snippet also does not reveal the OS-assigned port when configured as 0.

To find the **winning source**, inspect property sources and origin metadata with a debugger, or use `env`/`configprops` over a secured and permitted management channel. Those endpoints may mask values, be excluded from exposure, or require authorization; do not treat masked output as proof the original value was lost. Do not expose all endpoints just to find one port key.

To observe **actual behavior**, read web server startup logs, check sockets in the right network namespace, call health from the monitoring tool's vantage point, and inspect MBeans with a JMX tool. If the app halts before `ApplicationRunner` runs, use startup logs and deployment config to investigate; the probe cannot report for an app that never finished starting.

Remove the temporary diagnostic snippet or gate it behind controlled mechanisms after finding the root cause.

## 8. End-to-End Incident Handling Procedure

### Step 1: Record Run Identity

Record the application version, Spring Boot version, environment, profile, PID/container/pod, and failure timestamp. Separate errors from the current deployment from logs of an earlier build.

### Step 2: Branch by Root Exception

If `InstanceAlreadyExistsException` occurs, grab the ObjectName and locate both registering parties. If a bind error occurs, grab the address/port and occupying process. If the app runs yet monitoring fails, start from the URL and connection outcome.

### Step 3: Compare Effective Config with Expected Config

Build a short table for relevant keys:

| Key/resource | Expected | Effective/observed | Source or evidence |
| --- | --- | --- | --- |
| Profile | prod | prod | Startup log |
| Management port | 9191 | 9291 | Env var and listener log |
| Monitoring URL | Port 9291 | Monitor still calls 9191 | Probe config |
| ObjectName | One MBean per object | Two registrations with same name | Cause chain and exporter config |

This is an example set of observations to practice recording; in a real investigation, replace with evidence from the system under examination.

### Step 4: Make the Smallest Explainable Change

- Unintentional duplicate registration: remove the extra registration mechanism or fix lifecycle.
- Two legitimate contexts: assign proper identifiers/domains, accounting for unique names and monitoring queries.
- Port overridden by external source: fix the winning deployment source rather than repeating the same value across multiple files.
- Monitor calling an old address: update probes/routing to match the actual listener.
- Endpoint excluded from HTTP: fix exposure for that specific endpoint if operational contracts require it.

### Step 5: Restart the Right Target and Verify Both Sides

Confirm the new configuration entered the process, the app starts cleanly, expected MBeans exist, and the management URL responds from the right network location. Test business APIs to catch unintended side effects, such as accidentally changing the main port.

If MBean names changed, verify monitoring queries still select the right MBean. If ports changed, update health checks, Services, proxies, and scrape jobs accordingly.

### Step 6: Document Root Cause and Remove Temporary Workarounds

A useful conclusion states: "An old environment variable set port 9291 while probes called 9191; fixed the deployment value and verified probes reach the right listener." "Restarting fixed it" identifies neither cause nor prevention.

Maintain clear configuration ownership per environment. When multiple sources are used intentionally, document which source owns overriding which keys.

## 9. Diagnostic Self-Check Exercises

### Scenario 1: Changed Port, Yet MBean Still Collides

Two ApplicationContexts share an MBeanServer and both register endpoints. The operator changes the port from 8080 to 8082, yet the exception remains.

**Explanation:** the HTTP address changed, while the ObjectName inside the same registry did not. Determine whether the two contexts are intentional or duplicate initialization. For two legitimate contexts, address names/domains and identification; for duplicate initialization, remove the extra registration.

### Scenario 2: Works Locally, Monitoring System Cannot Reach It

The containerized app logs management on 9091, yet the host maps only 8080. Health succeeds from inside the container.

**Explanation:** there is no evidence of a path from the monitoring host to 9091. Check bind address, port mapping, or Service/proxy. Do not alter JMX to fix a missing HTTP route.

### Scenario 3: Editing application-prod.yml Does Not Change the Port

The profile file sets 9191, an env var sets 9291, and the startup command includes `--management.server.port=9391`.

**Explanation:** under standard startup in this example, 9391 wins. Dropping the argument is still not enough to revert to 9191 because the env var remains. Fix the actual highest-precedence source.

### Scenario 4: HTTP Health Is Fine, Yet a Library MBean Still Reports Duplicate

The app set `management.endpoints.jmx.exposure.exclude="*"`, yet a third-party library's MBean error still occurs.

**Explanation:** excluding Actuator endpoints from JMX does not control every library's JMX registration mechanism. Extract the exact ObjectName and registering component to fix it; do not conclude Actuator failed to read config.

### Scenario 5: Calling the Right Port Returns 401

After fixing port mapping, the monitor gets 401 instead of a timeout.

**Explanation:** progress was made at the connectivity layer, yet you must verify the response comes from the right app/proxy and then address authentication. Do not keep changing ports just because health has not returned 200 yet.

Before closing an incident, you should be able to answer: which name collided and who owns registration; which listener is running and who connects to it; and which value is effective and which source decided it.
