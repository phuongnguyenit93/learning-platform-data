# Comparing Supported Properties and Default Values Across Spring Boot Versions

## 1. Purpose and Scope

Spring Boot server configuration properties do not always keep the same names, defaults, or scopes across releases. An application.yaml file that works properly in Spring Boot 2.x may use property names that were changed in 3.x or 4.x; even when a key name stays the same, the embedded server or how values are interpreted can change.

This lesson compares three **specific version milestones**:

- **Spring Boot 2.7.18**: representing the final 2.7 branch.
- **Spring Boot 3.5.x**: representing the 3.5 branch; comparison table values are taken from the 3.5 documentation.
- **Spring Boot 4.0.x**: representing the 4.0 branch; comparison table values are taken from the 4.0 documentation.

These are three documentation milestones, not an assertion that every minor release in a branch or the newest Spring Boot release is identical. When a project uses another version, check the documentation and metadata of the **exact running version**.

The focus is on properties related to the **embedded web server**, HTTP listener, servlet/reactive server, request/response handling, compression, shutdown, and Tomcat-specific configuration. Database, messaging, or application security configurations are outside the scope of this comparison.

## 2. Distinguishing "Supported", "Default", and "Effective Value"

When comparing a property, answer three separate questions:

1. **Is the key name supported?** Does the documentation or configuration metadata of that Spring Boot version describe this key? Has it been renamed, replaced, or removed?
2. **What is the documented default?** If no value is specified, does Spring Boot use a specific value such as 8080, false, 8KB, or 30m? An empty default cell in the documentation can mean no fixed value is set at the Spring Boot layer and behavior depends on the server, OS, or environment.
3. **What is the actual runtime value?** The value can be overridden by application.yaml, profiles, environment variables, command-line arguments, test configuration, or Java code; the embedded server may also adjust behavior based on the OS.

For example, the documentation lists server.port with default 8080. However, an application started with SERVER_PORT=9090 has an actual port of 9090. If server.port=0, the OS picks a random port and the bound port is not 0. Therefore, **documented defaults do not replace runtime verification**.

The existence of a property in the common list also does not guarantee it takes effect in the current application. **server.tomcat.threads.max** applies to Tomcat and does not configure Reactor Netty. **server.servlet.context-path** applies to the servlet stack; WebFlux has its own base path configuration.

## 3. Comparison Table of Common Properties

The table below lists the defaults published in each milestone's documentation. "Not fixed" means the documentation does not publish a single fixed address/value. "Empty" for context path means the application runs at the root path.

| Property | 2.7.18 | 3.5.x | 4.0.x | Practical Meaning |
|---|---|---|---|---|
| server.port | 8080 | 8080 | 8080 | HTTP port of the embedded server |
| server.address | Not fixed | Not fixed | Not fixed | Local IP address the listener binds to |
| server.http2.enabled | false | false | false | Enables HTTP/2 if environment and server support it |
| server.compression.enabled | false | false | false | Enables HTTP response compression |
| server.compression.min-response-size | 2KB | 2KB | 2KB | Threshold for compressing responses |
| server.servlet.context-path | Empty | Empty | Empty | Context prefix of the servlet application |
| server.servlet.session.timeout | 30m | 30m | 30m | HTTP session timeout in the servlet stack |
| server.tomcat.threads.max | 200 | 200 | 200 | Tomcat worker thread limit when this mechanism applies |
| server.tomcat.threads.min-spare | 10 | 10 | 10 | Tomcat minimum spare worker threads |
| server.tomcat.accesslog.enabled | false | false | false | Tomcat access log |
| server.shutdown | immediate | graceful | graceful | Default shutdown mode at each milestone |

The values in the table are **not a guarantee of identical effective behavior across every server**. In particular, Tomcat thread options in newer versions do not act like the traditional thread pool model when virtual threads are enabled; read the description for your exact version and runtime mode.

For server.address, no single fixed IP literal is published as the default. Embedded applications can usually accept connections on appropriate interfaces, but actual IPv4/IPv6 sockets still depend on containers, the OS, and the JVM. Do not hard-state "default 0.0.0.0" as an absolute rule.

**Reference sources:** Common Application Properties for Spring Boot 2.7.18, 3.5, and 4.0, linked at the end of this lesson.

## 4. Major Change: HTTP Header Limit

A clear example of a **property name change** is the HTTP request header size limit.

| Milestone | Documented Property | Default |
|---|---|---|
| Spring Boot 2.7.18 | server.max-http-header-size | 8KB |
| Spring Boot 3.5.x | server.max-http-request-header-size | 8KB |
| Spring Boot 4.0.x | server.max-http-request-header-size | 8KB |

In 2.7, the old name used **header-size**. In 3.5 and 4.0, the new name adds **request** to clarify scope. Do not copy configurations from 2.x tutorials into 3.x or 4.x projects without updating the key name.

Configuration for Spring Boot 2.7:

~~~yaml
server:
  max-http-header-size: 16KB
~~~

Configuration for Spring Boot 3.5 or 4.0:

~~~yaml
server:
  max-http-request-header-size: 16KB
~~~

Important notes:

- In newer versions the target is HTTP **request** headers. Do not equate it with limits on all HTTP response headers.
- The 3.5 and 4.0 documentation explicitly notes that enforcement can vary by embedded server: Tomcat sums the request line and header names/values, while Netty may apply the limit per individual request header. Hence, the same 16KB value does not guarantee identical behavior between Tomcat and Reactor Netty.
- If you need to change Tomcat's response header limit, check Tomcat-specific properties such as server.tomcat.max-http-response-header-size for your version rather than assuming request-header-size also applies to responses.
- Sharing the same 8KB default across milestones **does not prove** that the underlying server library kept the exact same rejection mechanics for oversized requests.

A common mistake is seeing the application still start up after an upgrade and assuming the old key is still active. An unbound property may not fail startup. Therefore, check configuration metadata, migrator warnings, and test limits against the real server.

## 5. Change in Spring Boot 4.0: HTTP Error Content Configuration

Spring Boot 2.7 and 3.5 list the **server.error.*** group to control information included in HTTP error responses. In Spring Boot 4.0 documentation, the corresponding properties are listed under **spring.web.error.***.

| Function | 2.7.18 and 3.5.x | 4.0.x | Published Default |
|---|---|---|---|
| Include message in error body? | server.error.include-message | spring.web.error.include-message | never |
| Include exception name? | server.error.include-exception | spring.web.error.include-exception | false |
| Include stacktrace? | server.error.include-stacktrace | spring.web.error.include-stacktrace | never |
| Include binding errors? | server.error.include-binding-errors | spring.web.error.include-binding-errors | never |
| Error controller path | server.error.path | spring.web.error.path | /error |
| Enable default error page | server.error.whitelabel.enabled | spring.web.error.whitelabel.enabled | true |

Example for Spring Boot 3.5:

~~~yaml
server:
  error:
    include-message: never
    include-stacktrace: never
    path: /error
~~~

Example using the property names in Spring Boot 4.0 documentation:

~~~yaml
spring:
  web:
    error:
      include-message: never
      include-stacktrace: never
      path: /error
~~~

Do not assume every setting prefixed with server.* was renamed in Boot 4.0. Properties like server.port, server.address, server.http2.enabled, and many Tomcat settings keep their names as shown in the table. Therefore, migrate **property by property**, not by bulk-replacing prefixes.

Also do not alter security posture or error disclosure policies merely because a key was renamed. For example, include-stacktrace=never is a common safe production value; changing it to always can leak implementation details.

## 6. A Change in Default Value: server.shutdown

Not every version difference appears as a property rename. Some properties **keep the same name while changing their default**.

| Comparison Milestone | Default server.shutdown |
|---|---|
| 2.7.18 | immediate |
| 3.0.1 (additional reference) | immediate |
| 3.5.x | graceful |
| 4.0.x | graceful |

Across the checked milestones, 2.7.18 and 3.0.1 default to immediate; 3.5 and 4.0 documentation list graceful. This table does not claim the exact first minor version where the default flipped, as that requires checking release notes per release.

**immediate**: the server stops accepting/processing according to the implementation's immediate stop mode. **graceful**: the server attempts to finish active requests within an allowed grace period before stopping. Exact details depend on the embedded server and application lifecycle.

If the system requires consistent behavior across versions, **set the value explicitly** instead of relying on defaults:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

This is an example of intentional shutdown configuration. Do not equate the lifecycle shutdown timeout with individual HTTP request timeouts. In container environments, the orchestrator's termination grace period must also be long enough for the application to finish stopping.

A changed default can affect process exit times, connection-closing behavior, and rolling deployments, so include shutdown in upgrade test plans.

## 7. Properties with Stable Names Whose Scope Depends on Web Stack

Spring Boot has two primary web models:

- **Servlet stack**: Spring MVC with embedded Tomcat, Jetty, or a compatible server.
- **Reactive stack**: Spring WebFlux with Reactor Netty or a compatible reactive server.

The same application.yaml file may contain properties that only affect one stack:

| Property | Effect | When Not Applicable |
|---|---|---|
| server.port | Embedded server HTTP port | No HTTP server if web application type is none |
| server.address | Embedded server local bind address | Nothing to bind if there is no listener |
| server.servlet.context-path | Servlet application context path | Does not configure WebFlux base path |
| spring.webflux.base-path | WebFlux web handlers base path | Does not replace servlet context path |
| server.tomcat.threads.max | Tomcat-specific worker threads | Does not apply to Reactor Netty |
| server.netty.idle-timeout | Reactor Netty-specific idle timeout | Does not apply to Tomcat |
| server.http2.enabled | HTTP/2 config when server/environment support it | Does not guarantee all connections will use HTTP/2 |

With Spring MVC:

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /api
~~~

With Spring WebFlux:

~~~yaml
server:
  port: 8080

spring:
  webflux:
    base-path: /api
~~~

Both examples aim for an /api URL path prefix yet operate on different framework mechanisms. Check which web application type Spring Boot selected, especially when both spring-boot-starter-web and spring-boot-starter-webflux appear on the classpath.

Also distinguish the **Spring Boot version** from the **embedded Tomcat/Jetty/Netty version**. A Boot release typically manages compatible dependency versions. The same Boot-supported key can behave differently if an upgraded underlying server alters internal limits or support conditions.

## 8. How Should "Empty" Defaults in Documentation Be Interpreted?

Not every cell in the Common Application Properties table contains a number. "No default value listed in the table" has at least three possibilities:

1. Spring Boot does not impose a specific value and lets the embedded server choose.
2. The value is computed from the OS, machine resources, connection type, or runtime conditions.
3. A setting only matters when another feature is enabled.

Examples:

- **server.address**: documentation typically does not specify a fixed IP literal default. The actual listener may bind to a wildcard appropriate for the OS/server; you cannot use a blank cell in the docs to claim the server listens only on 127.0.0.1.
- **server.tomcat.connection-timeout**: the default cell may not list a fixed Duration. That does not mean the server has "no timeout"; check the default of the running Tomcat version.
- **server.forward-headers-strategy**: the value should not be inferred merely from the presence of a proxy. Spring Boot may choose environment-dependent behavior and requires explicit configuration when trusting forwarded headers.
- **server.ssl.enabled** may be documented with default true in supported branches, yet that does not mean the app automatically provisions certificates and opens HTTPS. SSL material or matching configuration is still required for HTTPS to work.

Therefore, when writing internal documentation, use labels like **"no specific default published"** or **"implementation-dependent"**, rather than filling in 0, false, null, or unlimited without verification.

## 9. Configuration Table by Deployment Need

Some values do not change with Boot versions because they are business or infrastructure choices rather than framework defaults:

| Scenario | Suggested Configuration | What to Verify |
|---|---|---|
| Local development | server.port=8085, server.address=127.0.0.1 | Accessible only via loopback on the running machine |
| Running in a container | server.port=8080, server.address=0.0.0.0 | Port mappings/Service/Ingress must still be right |
| Integration testing with random port | server.port=0 | Read the runtime port after the server starts |
| No HTTP listener needed while keeping web context | server.port=-1 | Not the same as spring.main.web-application-type=none |
| App needs response compression | server.compression.enabled=true | Check Content-Type, size threshold, and server support |
| HTTP/2 needed | server.http2.enabled=true | Check TLS/ALPN, container/server, and infrastructure support |
| Predictable shutdown | server.shutdown=graceful | Test graceful period length and termination signals |
| Running behind a reverse proxy | server.forward-headers-strategy chosen intentionally | Only trust headers provided by trusted proxies |

Note: server.port=0 is not a port for clients to connect to. Once the web server starts, retrieve the actual port from WebServerInitializedEvent or @LocalServerPort in integration tests. server.address=0.0.0.0 is an **IPv4 wildcard bind**, not a public URL clients should enter.

## 10. How to Determine the Exact Running Version

Do not rely on a recently edited build file or an old project README to conclude the actual version. In Maven/Gradle, dependency management, BOMs, parents, and dependency resolution decide which JARs get loaded.

Ways to check:

- Maven: inspect the version of spring-boot-starter-parent, dependencyManagement, or the Spring Boot BOM; run the dependency tree to check resolved JARs.
- Gradle: inspect the org.springframework.boot plugin, dependency management, and runtimeClasspath output; do not just look at a version declared on a single arbitrary dependency.
- At runtime: check version info in build info, startup logs, or actuator info if configured. Do not treat any unverified version string as the running version.
- With Spring Boot 4.x, internal packages/modules of certain components may move. Thus, code referencing configuration classes should check the Javadoc for the exact version.

Maven example:

~~~bash
./mvnw dependency:tree
~~~

Gradle example:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Windows can use mvnw.cmd or gradlew.bat instead of Unix scripts. In many projects, dependency trees are long, so filter for Spring Boot and embedded server artifacts.

## 11. How to Look Up Supported Properties for the Exact Version

Workflow to verify a new or old property:

1. Identify the exact Spring Boot version and web stack in use.
2. Open **Common Application Properties** for that version; search for the **exact property name**.
3. Read the Description and Default Value, along with notes on server/stack requirements.
4. Inspect **Configuration Metadata** inside the corresponding starter/autoconfigure JARs, usually at META-INF/spring-configuration-metadata.json.
5. When a property is marked deprecated, read its replacement and the migration guide instead of keeping the old name.
6. When the default is empty, check the @ConfigurationProperties class, customizers, and embedded server documentation for that version.
7. Write a test or inspect at runtime to confirm the property actually takes effect.

Configuration metadata is useful for IDE completion, types, descriptions, defaultValues, and deprecation hints. However, **metadata is not sole proof of runtime values**: values can be computed dynamically, decided by the implementation, or overridden by configuration sources.

Do not search keywords online without pinning the version. A Common Application Properties page without a version number in its URL can change with the latest release. When saving documentation for a project team, attach versioned URLs.

## 12. Reading Effective Values at Runtime

A value assigned in application.yaml can be overridden by environment variables, system properties, profiles, or command-line flags. Example:

~~~yaml
server:
  port: 8080
  compression:
    enabled: false
~~~

When launching the JAR with:

~~~bash
java -jar app.jar --server.port=9090 --server.compression.enabled=true
~~~

The runtime values will normally be port 9090 and compression enabled, because command-line arguments take precedence over application.yaml packaged inside the JAR under externalized configuration rules.

Similarly, environment variables:

~~~bash
export SERVER_PORT=9090
export SERVER_COMPRESSION_ENABLED=true
java -jar app.jar
~~~

In PowerShell:

~~~powershell
$env:SERVER_PORT = "9090"
$env:SERVER_COMPRESSION_ENABLED = "true"
java -jar app.jar
~~~

Note that relaxed binding converts between notations like server.port and SERVER_PORT. However, do not assume a property **renamed across versions** will automatically map to the new key. Relaxed binding handles spelling format differences, not deprecation/renaming migration.

### Observing the Configured Port and Actual Bound Port

Spring Boot 3.5 example with Java 17+, placed in src/main/java/example/ServerPortReporter.java of a Spring Boot project with starter-web:

~~~java
package example;

import org.springframework.boot.web.context.WebServerInitializedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ServerPortReporter {

    private final Environment environment;

    public ServerPortReporter(Environment environment) {
        this.environment = environment;
    }

    @EventListener
    public void onWebServerInitialized(WebServerInitializedEvent event) {
        String configured = environment.getProperty(
                "server.port", "(not explicitly configured)");
        String address = environment.getProperty(
                "server.address", "(not explicitly configured)");
        int actual = event.getWebServer().getPort();

        System.out.println("Configured server.port: " + configured);
        System.out.println("Configured server.address: " + address);
        System.out.println("Actual listening port: " + actual);
    }
}
~~~

Explanation:

- Environment.getProperty returns the value present in Environment or the fallback; it does not prove "the internal default of the embedded server".
- WebServerInitializedEvent is published once the server has started; getPort() reports the actual port from the server.
- If server.port=0, the configured line may print 0 while the actual line prints an OS-assigned port.
- If the application configures a separate management server, events may fire for multiple web servers; distinguish each event's ApplicationContext.
- This example targets Spring Boot 3.5 packages/APIs. When migrating to 4.x, check the version-specific Javadoc before copying this class verbatim.

Do not assert fixed stdout with a random port because the value depends on the environment.

### Checking with Spring Boot Actuator

When the application includes Actuator and endpoints are configured/permitted appropriately:

- Endpoint **/actuator/env** helps inspect property values and PropertySource origins; you can query a specific property name.
- Endpoint **/actuator/configprops** displays bound @ConfigurationProperties beans, helping verify values bound to ServerProperties or other configuration properties.
- Not every property is shown verbatim through endpoints: sensitive values are typically masked, and endpoints may be disabled or restricted by security configuration.
- Never expose /env or /configprops to the public Internet just to debug; enforce proper administrative access controls.

Example query when the env endpoint is exposed and authorized:

~~~bash
curl -i http://localhost:8080/actuator/env/server.port
~~~

Adjust localhost/port to the actual listener. JSON output, status, and fields can vary across versions/configurations, so avoid treating mocked stdout as fixed output.

## 13. Using the Properties Migrator When Upgrading

Spring Boot provides **spring-boot-properties-migrator** to help diagnose renamed/removed properties when upgrading feature releases. It can emit startup warnings and in some cases provide temporary migration support.

Maven example:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-properties-migrator</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Safe workflow:

1. Lock down the source version and target version.
2. Audit keys in application.yaml, environment variables, Helm values, and deployment manifests.
3. Add the migrator **temporarily** during the upgrade phase if applicable to your version.
4. Run the application or integration tests, and review warnings about renamed, removed, or unsupported keys.
5. Update source configs to the new property names and re-run tests; do not rely on temporary remapping permanently.
6. **Remove the migrator dependency once migration is complete**.

The migrator cannot catch every change in runtime semantics, especially internal server defaults or properties introduced late into Environment. Alongside the migrator, read official release notes and migration guides.

## 14. Testing Configuration During a Version Upgrade

A migration can start up cleanly yet behave differently in operation. Test suites should cover:

| Area | What to Verify | How to Test |
|---|---|---|
| Bind and port | Right address/port actually bound, no unintended open ports | Startup logs, ss, curl from the right network |
| HTTP/2 | Protocol negotiated as intended | HTTP/2-capable client, proxy/server logs |
| Compression | Correct response encoding and trigger conditions | curl with Accept-Encoding, Content-Encoding |
| Request header limit | Large requests accepted/rejected at configured threshold | Integration tests with controlled header sizes |
| Error responses | Status, body, and error details do not accidentally change | Test error requests, check JSON and error pages |
| Session timeout | Sessions expire according to policy | Clock-controlled tests or appropriate integration tests |
| Graceful shutdown | In-flight requests and connections close at the right time | Send SIGTERM and observe in-flight requests |
| Tomcat threads | Max/min threads behave properly with config and virtual threads | Server/thread pool metrics and runtime docs |
| Management port | Management endpoints sit on the right network/port | Verify management.server.port and listener |
| Proxy forwarding | Redirects, URLs, and schemes are accurate; untrusted proxies rejected | Test through a trusted reverse proxy |

If a **request header size** test runs the exact same payload against Tomcat and Netty, results can differ due to differing limit semantics. Instead of assuming a framework bug, verify how each engine enforces it.

If testing **graceful shutdown**, align application shutdown timeouts with stop timeouts in Docker/Kubernetes. With server.shutdown=graceful, if the orchestrator kills the process too soon, in-flight requests can still be severed.

If testing **server.port=0**, retrieve the actual port after the server starts. Do not send HTTP requests to port 0.

## 15. Common Pitfalls When Comparing Versions

### Pitfall 1: Taking Defaults from Another Version

An old tutorial might state server.shutdown=immediate is the default while 3.5/4.0 documentation lists graceful. Solution: cite the exact version, read the Application Properties table for that version, and set explicit values when stable behavior is required.

### Pitfall 2: Keeping Old Properties After They Were Renamed

For example, using server.max-http-header-size from 2.7 or server.error.include-message from 3.5 inside a 4.0 application without checking replacements. Solution: consult migration guides, configuration metadata, and the migrator; fix each property properly.

### Pitfall 3: Assuming an Existing Property Always Takes Effect

server.tomcat.threads.max does not control Reactor Netty. server.servlet.context-path does not adjust WebFlux base path. Solution: verify the stack and server implementation the application actually uses.

### Pitfall 4: Putting a Guessed Value into a Default Table

server.address is not published as a single uniform IP literal in the tables. Solution: record "no specific default published", then inspect the actual listener and network environment.

### Pitfall 5: Treating File Values as Runtime Values

application.yaml says 8080, yet SERVER_PORT=9090 or a CLI argument overrides it to 9090. Solution: check effective PropertySources and the actual port after server startup.

### Pitfall 6: Assuming Unchanged Property Names Mean Unchanged Semantics

Dependencies and embedded servers evolve; HTTP header sizes, thread pools, sessions, TLS, and forwarded headers require testing after upgrades. Solution: read both Spring Boot and embedded server documentation, then test behavior.

### Pitfall 7: Confusing Feature Defaults with Activation Prerequisites

server.ssl.enabled may list a default in metadata, yet that does not mean HTTPS runs without configuring certificates. server.http2.enabled=true also does not guarantee every client uses HTTP/2. Solution: verify prerequisites and actual negotiated protocols.

## 16. Process for Building a Reliable Reference Table for a Project

To build a trustworthy comparison matrix between any two Spring Boot versions:

1. **Pin exact versions**: e.g., 2.7.18 → 3.5.x or 3.5.x → 4.0.x; note the project's actual patch version.
2. **Inventory used properties**: scan application.yaml/properties, deployment manifests, environment variables, secret templates, tests, and Java customizers. No need to catalog thousands of unused properties.
3. **Look up old and new properties**: for each key, record supported/deprecated/removed/renamed status, description, type, published default, and documentation source.
4. **Classify by stack**: server-common, servlet-only, reactive-only, Tomcat-only, Jetty/Undertow/Netty-only, management-only.
5. **Check override sources**: profiles, env, CLI, config trees, container values, and code.
6. **Observe runtime**: real port, listener address, protocol, response headers, shutdown, thread pool/metrics, and startup diagnostics.
7. **Run regression tests**: test effective values and promised behavior, especially where properties were renamed or defaults changed.
8. **Set explicit values for critical behavior**: if the app relies on immediate/graceful shutdown, header limits, or compression, configure them explicitly and test.
9. **Save versioned documentation links**: avoid linking solely to /current or /latest pages whose contents shift.
10. **Remove the migrator after upgrading**, and update operational runbooks to retire outdated recommendations.

Suggested template columns for each property:

| Column | Content |
|---|---|
| Old Property | Key name in source version |
| New Property | Accepted key name in target version |
| Support | Yes/no/renamed/removed |
| Source Default | Official value, citing exact version |
| Target Default | Official value, citing exact version |
| Conditions | Servlet/reactive/server-specific/feature-specific |
| Runtime | Value after applying all overrides |
| Evidence | Docs link, metadata, test, or log |
| Action | Keep, rename, configure explicitly, or write test |

## 17. Concrete Configuration Migration Example

Suppose a Spring Boot 2.7 application has the file:

~~~yaml
server:
  port: 8080
  max-http-header-size: 16KB
  shutdown: immediate
  compression:
    enabled: true
  error:
    include-message: never
~~~

When migrating to **Spring Boot 3.5**, update the header property to the new name and declare the shutdown mode explicitly to avoid relying on defaults:

~~~yaml
server:
  port: 8080
  max-http-request-header-size: 16KB
  shutdown: immediate
  compression:
    enabled: true
  error:
    include-message: never
~~~

When migrating further to **Spring Boot 4.0**, use the error property group documented for 4.0:

~~~yaml
server:
  port: 8080
  max-http-request-header-size: 16KB
  shutdown: immediate
  compression:
    enabled: true

spring:
  web:
    error:
      include-message: never
~~~

These three files only illustrate **migrating the properties discussed in this lesson**, not a complete upgrade guide. Major version upgrades may also require changes to Java, Spring Framework, Jakarta APIs, dependencies, and application code. Run the migrator and integration tests to confirm every property actually binds.

In the example, shutdown is explicitly kept as immediate across all three milestones to preserve a prior operational decision. If operations wants graceful shutdown, switch it intentionally and test shutdown behavior; do not change it passively just because a newer version changed the default.

## 18. Primary Sources for Self-Verification

Official pages used to verify the milestones in this lesson:

1. [Spring Boot 2.7.18 – Common Application Properties](https://docs.spring.io/spring-boot/docs/2.7.18/reference/html/application-properties.html) — property names and defaults for 2.7.18.
2. [Spring Boot 3.0.1 – Common Application Properties](https://docs.spring.io/spring-boot/docs/3.0.1/reference/html/application-properties.html) — additional milestone to avoid guessing when the shutdown default changed.
3. [Spring Boot 3.5 – Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/) — properties and defaults for the 3.5 branch.
4. [Spring Boot 4.0 – Common Application Properties](https://docs.spring.io/spring-boot/4.0/appendix/application-properties/index.html) — names and defaults for the 4.0 branch.
5. [Spring Boot 4.0 – Embedded Web Servers](https://docs.spring.io/spring-boot/4.0/how-to/webserver.html) — configuring ports, disabling the HTTP endpoint, and disabling web application type.
6. [Spring Boot – Upgrading](https://docs.spring.io/spring-boot/upgrading.html) — workflow for reading migration guides and temporarily using spring-boot-properties-migrator.

When drawing conclusions for a specific patch release, open the documentation and metadata of that exact patch release rather than assuming all versions in the same major line are identical.

## 19. Practical Conclusion

**Comparing server configuration across versions means comparing property names, defaults, scopes, and runtime values.** The milestones above show that server.port stays 8080 and many common keys remain unchanged, yet server.max-http-header-size moved to server.max-http-request-header-size, the error property group changed namespace in 4.0, and the server.shutdown default differs between 2.7/3.0 and 3.5/4.0.

To avoid upgrade failures, pin source/target versions, consult versioned documentation, use the migrator for rename/removal warnings, inspect override sources, and run tests on a real embedded server. For production-critical behavior, explicit configuration paired with regression tests delivers far more stability than relying on framework defaults.