# Reading Startup Logs to Identify Exposed Endpoints

When a Spring Boot application starts, you may see the line:

```text
Exposing 3 endpoints beneath base path '/actuator'
```

This line is useful evidence about exposing Actuator management access points over the web. To use it properly, read it alongside the running version, configuration, port, and final startup status; then verify endpoint names via the discovery path or HTTP responses.

This lesson uses Spring Boot 3.3, with experiments pinned at 3.3.5. The goal is to go from a single log line to an evidence-backed answer: **how many endpoints are exposed, under which path they live, and how to determine the actual access path**.

## 1. What does the log line say?

The example below trims formatting to keep the log level, logger name, and message:

```text
INFO org.springframework.boot.actuate.endpoint.web.EndpointLinksResolver : Exposing 3 endpoints beneath base path '/actuator'
```

In Spring Boot 3.3.5, `EndpointLinksResolver` logs this message at `INFO` level, using the size of the endpoint collection passed to it and the corresponding base path. You can cross-reference [the official EndpointLinksResolver source at v3.3.5](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.5/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/endpoint/web/EndpointLinksResolver.java).

| Part to read | Meaning in the example |
| --- | --- |
| `INFO` | Log level of the message |
| `EndpointLinksResolver` | Component generating the message related to web endpoint links |
| `3 endpoints` | Number of endpoints in the exposed set under this configuration |
| `base path '/actuator'` | Base path for the endpoints, not yet the full URL |

An **Endpoint** here is an identified management capability, such as `health` or `metrics`. An endpoint can have multiple operations or subpaths.

### 1.1. Do not use the count to guess names

From the number 3, you cannot be sure it is `health`, `info`, and `metrics`. Another application might have three different endpoints or a custom endpoint.

Nor should this be interpreted as:

- Total number of business APIs of the application.
- Total number of URLs or HTTP methods.
- Total number of beans in Spring.
- Number of JMX endpoints.
- Number of features the current caller is authorized to use.

In the experiment below, a single `health` endpoint can produce both the health link and a link with a subpath. The number of entries under `_links` can therefore differ from the endpoint count.

### 1.2. This line does not confirm the whole application is ready

The endpoint exposure message is emitted during initialization. If a later step fails, it may still have appeared in the log.

Do not stop reading right at the word `Exposing`. Check whether the server started, whether the application finished starting, and whether any errors occurred afterward. Spring Boot has a startup failure reporting mechanism; see [SpringApplication — Startup Failure](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.startup-failure).

Illustrative event sequence, not a verbatim log:

```text
Web endpoint set configured
        ↓
Server encounters an error finishing startup
        ↓
Application aborts startup
```

At that point, the endpoint set information helps you see how far configuration got, but it does not prove URLs are serving requests.

## 2. Reading from the right process and the right startup run

Full logs usually include timestamp, log level, process ID, thread name, and logger name. Logger names may be abbreviated to fit the display format. Formatting changes when using a custom logging configuration. See [Spring Boot 3.3 — Logging](https://docs.spring.io/spring-boot/3.3/reference/features/logging.html).

When looking for the endpoint exposure line, follow this order:

1. Identify the application and startup run under inspection.
2. Note the active profiles and software version if present in the log.
3. Search for messages containing `Exposing` and `beneath base path`.
4. Read the port, context path, and related server details.
5. Read onward to the final startup outcome.
6. Verify HTTP from a location with the required permissions and network path.

If logs from multiple processes or multiple restarts are combined, do not pair process A's endpoint count with process B's port. When restarting in development, always check lines from the latest still-running attempt.

### 2.1. Searching in an existing log file

In PowerShell, you can filter the lines you need to read:

```powershell
Select-String -Path ".\startup.log" -Pattern "Exposing .* endpoint","beneath base path","Tomcat started","Started ","APPLICATION FAILED TO START"
```

`startup.log` is an example file name. The command only reads; it does not create the file or enable log saving. Server messages may differ if using Netty, Jetty, or Undertow; do not rely solely on the Tomcat keyword.

Filtered results are a starting point. When you see an error, open the surrounding log section to read the cause and timing; do not keep only success lines.

### 2.2. When the exposure line is missing

Not seeing the message is not enough to conclude Actuator is absent. Possibly:

- The log level suppresses `INFO` for the relevant logger.
- Logs are redirected to a file or centralized logging system.
- The application stopped before reaching that configuration step.
- The application lacks the corresponding web infrastructure.
- The version or logging configuration formats messages differently.
- You are looking at the wrong process or only a log slice.

If needed in a test environment, you can set a dedicated log level:

```properties
logging.level.org.springframework.boot.actuate.endpoint.web.EndpointLinksResolver=INFO
```

The property must be applied before the startup run you want to observe. Changing the log level after the startup line was already skipped will not make past lines reappear.

## 3. What determines which endpoints are exposed

Before interpreting the count, separate three concerns:

| Aspect to evaluate | Example question |
| --- | --- |
| Feature availability | Are the dependency and required components present? |
| Endpoint enablement and exposure | Is the endpoint enabled and included in the web exposure policy? |
| Caller authorization | Does the caller have permission and follow the right network path? |

In Spring Boot 3.3, by default only `health` is exposed over HTTP. You can select the list via `management.endpoints.web.exposure.include`; items in `exclude` can remove endpoints from the list. An access point requiring an extra library will not appear merely by writing its name in `include`. See [Spring Boot 3.3 — Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Example for an application that has all corresponding components:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics"
```

In the clean test setup in section 4, this choice produces an exposure message for three endpoints. For a real application, re-verify the conditions and effective configuration rather than treating that number as a universal default.

### 3.1. A configuration list is not yet the effective result

You can write configuration in YAML, properties, environment variables, or command-line arguments. Spring Boot merges sources by precedence; another source can make the effective value differ from the file you are reading. See [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

Therefore, if a file lists three endpoints while the log reports only one, check active profiles, startup arguments, and feature conditions. There is no basis yet to expose all endpoints.

### 3.2. Exposed does not mean permitted to call

The exposure line does not describe per-user authentication policies. When using Spring Security, an endpoint can be mapped yet require permissions the caller does not have.

That is why you must record two separate results: exposure configuration from the log and actual access response. Do not change all permissions to public access just to make one check command succeed.

## 4. Complete experiment: read the log then verify HTTP

The experiment creates a small application with only the web and Actuator starters, without Spring Security or business APIs. It is meant for a learning machine, listening on loopback `127.0.0.1`.

### 4.1. Prepare dependencies

Use JDK 17 or higher and compatible Gradle. In a fresh directory, create `settings.gradle`:

```groovy
rootProject.name = 'actuator-startup-log-demo'
```

Create `build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}

tasks.register('copyDemoLibraries', Copy) {
    from configurations.runtimeClasspath
    into layout.projectDirectory.dir('lib')
}
```

The pinned version supports reproducibility. This is a Java project using the BOM to manage dependencies; the commands below run the compiled class directly. It does not require building an executable JAR.

Use a dedicated directory to avoid mixing configurations or libraries from other projects. If libraries are not yet cached, Gradle needs network access to the Maven repository.

### 4.2. Complete Java code

Create `src/main/java/lab/actuator/StartupLogDemo.java`:

```java
package lab.actuator;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StartupLogDemo {
    public static void main(String[] args) {
        SpringApplication.run(StartupLogDemo.class, args);
    }
}
```

Compile in the experiment root directory:

```powershell
gradle copyDemoLibraries
javac -encoding UTF-8 -cp "lib/*" -d out src/main/java/lab/actuator/StartupLogDemo.java
```

You can use a Gradle Wrapper if the test project already has one. On Linux/macOS, the runtime classpath uses `:` instead of `;`.

### 4.3. Run A: keep the default exposure policy

In the first terminal:

```powershell
java -cp "out;lib/*" lab.actuator.StartupLogDemo --server.address=127.0.0.1 --server.port=8080
```

Expected relevant message in a clean test environment:

```text
Exposing 1 endpoint beneath base path '/actuator'
```

The application keeps running to serve HTTP. Timestamps, PID, startup duration, and logger abbreviation vary per run, so do not treat the entire console as fixed stdout.

After the application starts successfully, in the second terminal:

```powershell
curl.exe -i "http://127.0.0.1:8080/actuator"
curl.exe -i "http://127.0.0.1:8080/actuator/health"
curl.exe -i "http://127.0.0.1:8080/actuator/metrics"
```

In the experiment setup without additional security, the discovery path and health are reachable, whereas metrics is not exposed over the web. If your results differ, check the actual log and configuration before concluding.

If port 8080 is already used by another process, pick a free port and update all call commands consistently. Do not read responses from an old application and mistake them for the run you just launched.

### 4.4. Run B: expose three specific endpoints

Stop the application in the first terminal with `Ctrl+C`, then run:

```powershell
java -cp "out;lib/*" lab.actuator.StartupLogDemo --server.address=127.0.0.1 --server.port=8080 "--management.endpoints.web.exposure.include=health,info,metrics"
```

Relevant message:

```text
Exposing 3 endpoints beneath base path '/actuator'
```

Call the discovery page again, then test each path:

```powershell
curl.exe -i "http://127.0.0.1:8080/actuator"
curl.exe -i "http://127.0.0.1:8080/actuator/health"
curl.exe -i "http://127.0.0.1:8080/actuator/info"
curl.exe -i "http://127.0.0.1:8080/actuator/metrics"
```

The `info` endpoint may return an empty object if there is no info data configured to publish yet. Endpoint existence and payload richness are two different things. See [Actuator Info REST API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/info.html).

For metrics, read the actual list of metric names rather than expecting a fixed metric value. The API structure is in [Actuator Metrics REST API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

### 4.5. Verified results for the two configurations

With Spring Boot 3.3.5 and the sample application above, local HTTP checks produce:

| Configuration | Endpoint count in log | Discovery page | Health | Metrics |
| --- | --- | --- | --- | --- |
| Default | 1 | 200 | 200 | 404 |
| `health,info,metrics` | 3 | 200 | 200 | 200 |

The table describes the stated configurations. An application with security, proxies, different health conditions, or custom configuration may return other codes; record and interpret the actual codes.

To finish each test, stop the running process properly. There is no need to open additional endpoints to complete the experiment.

## 5. Identifying endpoint names via the discovery page

At the Actuator root path, the discovery page returns links under `_links` when this feature is enabled and you have access permission.

Example excerpt of relevant fields using Run B's address:

```json
{
  "_links": {
    "self": {
      "href": "http://127.0.0.1:8080/actuator",
      "templated": false
    },
    "health": {
      "href": "http://127.0.0.1:8080/actuator/health",
      "templated": false
    }
  }
}
```

This is not the full response of Run B. Read the real data to see the `info`, `metrics`, and other operation links.

The discovery page is described in [Hypermedia for Actuator Web Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.hypermedia). Individual endpoint operations have their own structures; see [Actuator REST API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/index.html).

### 5.1. Why not count _links instead of the endpoint count?

`self` is the link to the current page. An endpoint can also provide multiple operations, including parameterized paths. Consequently, each link entry is not necessarily a distinct endpoint identifier.

In the Spring Boot 3.3.5 experiment without extra security:

| Configuration | Endpoint count in log | Number of entries under `_links` |
| --- | --- | --- |
| Default health only | 1 | 3 |
| `health,info,metrics` | 3 | 6 |

These are observed results of the experiment, not a fixed formula for every application. Do not infer "log says 3 but JSON has 6 entries, so three extra endpoints were exposed".

When a link has `templated: true`, fill in parameters according to the operation; do not treat the template string verbatim as a complete address to call as-is.

### 5.2. Discovery page absent does not mean child endpoints are disabled

Stop the application and add the following property to the Run B command:

```text
--management.endpoints.web.discovery.enabled=false
```

Keep `health,info,metrics` in the exposure list. In the verified experiment, the results are:

| Observation | Result |
| --- | --- |
| Exposure log | Still reports 3 endpoints beneath `/actuator` |
| GET `/actuator` | 404 |
| GET `/actuator/health` | 200 |
| GET `/actuator/metrics` | 200 |

This property controls the discovery page. It does not disable all child endpoints. When the discovery page is not provided, use configuration, the condition report, or permitted mappings to find the paths to inspect.

Also do not blame every root-path error on this property. Wrong port, wrong path, access permissions, or a proxy can also cause unexpected results.

## 6. From base path in the log to the full URL

The line `base path '/actuator'` does not contain the protocol, host, port, or full context path.

In the Servlet case sharing the serving port without a proxy, you can visualize:

```text
Endpoint URL =
protocol + host + port
+ application context path
+ Actuator base path
+ mapped endpoint path
```

This is how components combine in the stated case. With a separate management port or a proxy, you must re-identify the corresponding components.

### 6.1. Experiment changing paths and health mapping

Stop the application and run:

```powershell
java -cp "out;lib/*" lab.actuator.StartupLogDemo --server.address=127.0.0.1 --server.port=8080 "--management.endpoints.web.exposure.include=health,info,metrics" --server.servlet.context-path=/shop --management.endpoints.web.base-path=/manage --management.endpoints.web.path-mapping.health=status
```

The relevant message still mentions only the base path:

```text
Exposing 3 endpoints beneath base path '/manage'
```

The path components have different roles:

| Configuration | Value | Role |
| --- | --- | --- |
| `server.servlet.context-path` | `/shop` | Context path of the Servlet application |
| `management.endpoints.web.base-path` | `/manage` | Root of Actuator endpoints |
| `management.endpoints.web.path-mapping.health` | `status` | Changes the path segment of the health endpoint |

Accordingly, the check commands are:

```powershell
curl.exe -i "http://127.0.0.1:8080/shop/manage"
curl.exe -i "http://127.0.0.1:8080/shop/manage/status"
curl.exe -i "http://127.0.0.1:8080/shop/manage/metrics"
```

In the experiment, the discovery page returns the health link with path `/shop/manage/status`, and the corresponding check paths work. The endpoint identifier remains `health`; changing the URL segment to `status` does not make it a new endpoint requiring `status` in the exposure list.

Path and mapping customization is described in [Spring Boot 3.3 — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

### 6.2. If using a separate management port

When `management.server.port` differs from the application port, you may see details for multiple servers in the log. You must identify which server serves management endpoints; the `EndpointLinksResolver` line does not supply that port on its own.

With a separate management port, the Actuator base path is evaluated relative to `management.server.base-path`. Do not take the main server's `server.servlet.context-path` and prepend it to the management port as in the shared-port case.

Record separately:

```text
Application serving port: 8080.
Management serving port: 8081.
Management root path: /ops.
Endpoint base path: /manage.
Expected health URL to check: http://127.0.0.1:8081/ops/manage/health.
```

These are notes for an illustrative configuration, assuming health keeps its default segment and management uses HTTP. This is not output from the shared-port experiment in section 4; obtain values and test results from the real application.

### 6.3. If behind a reverse proxy

Application logs reflect internal configuration. The external address called by clients may add or strip a path prefix, change ports, or use HTTPS while the internal hop uses HTTP.

To determine the public URL, read both the environment's routing configuration and the response from that access path. Do not infer the public domain solely from a base path line inside the application.

## 7. Using additional evidence when endpoint names are still unclear

### 7.1. Condition evaluation report

If an expected endpoint does not appear, `--debug` helps show why an auto-configuration was applied or skipped:

```powershell
java -cp "out;lib/*" lab.actuator.StartupLogDemo --server.address=127.0.0.1 --server.port=8080 --debug
```

This example reruns the default configuration; it does not implicitly retain arguments from the previous run. If you want to diagnose Run B or a custom-path configuration, you must pass that specific run's arguments again.

Locate the configuration related to the endpoint under inspection and read the reason. Many unmatched conditions are normal because the application does not use those technologies. See [Spring Boot 3.3 — Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html).

The condition report answers configuration questions; it does not confirm external network callers can reach it.

### 7.2. Mapping details when permitted to view

The `mappings` endpoint can provide request mapping information when it is enabled, exposed, and accessible. It is an extra source, not a prerequisite to complete the minimal experiment.

If used, read the exact paths and HTTP methods instead of looking only for bean names. Data structure is described in [Actuator Mappings REST API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/mappings.html).

There is no need to expose all management endpoints or enable application-wide `TRACE` just to find a health path. Choose the evidence source sufficient for the question under investigation.

## 8. Common misreadings

### "The log reports three endpoints, so all three URLs I guess must return 200"

The count does not give endpoint names. Get the names from effective configuration and appropriate discovery sources, then verify each operation.

An endpoint can also return a different health status code when a checked component is unhealthy. The goal is not to force every response to 200, but to identify the right path and interpret the result accurately.

### "The config file lists metrics, but the log reports only one; the library must be broken"

Maybe the file is unused in the current profile, overridden by another argument, the endpoint is disabled, or conditions are unmet. Check effective configuration and the condition report before changing dependencies.

### "Without the Exposing line, Actuator is definitely not loaded"

Log level and log destinations can hide that line from you. Check the right logger, log source, and startup run; verify directly via configuration when possible.

### "Seeing the Exposing line means the application finished starting"

A subsequent startup step can still fail. Always read through to the final status, then test from the location that actually needs to use the endpoint.

### "GET on the root path returns 404, so all child endpoints are disabled"

The discovery page has its own policy, as shown by the experiment disabling discovery. Check known child paths and their corresponding configuration.

### "The base path in the log is the entire URL path"

There are also port, context path, custom path mappings, and possibly a proxy. In the path-change experiment, the log said `/manage` yet health lived at `/shop/manage/status`.

### "One running instance's log represents the whole service"

Running instances may use different configurations or belong to different rollout waves. When investigating, tie evidence to the exact process, version, profile, and timestamp.

## 9. A repeatable log-reading workflow

| Step | Action | What to record |
| --- | --- | --- |
| 1 | Identify the exact run | Application, version, profile, and timestamp |
| 2 | Find the endpoint exposure line | Exact count and base path verbatim |
| 3 | Read server details | Port, context path, and serving mechanism |
| 4 | Check final startup outcome | Success or error occurring after the exposure line |
| 5 | Find endpoint names | Discovery links, configuration, or appropriate mappings |
| 6 | Verify HTTP requests | URL, method, response code, and required body |
| 7 | Note conclusion scope | Verified from which location, what remains unknown |

Example filled record based on the path-change experiment:

```text
Application: StartupLogDemo, Spring Boot 3.3.5.
Endpoint set: 3, base path /manage.
Servlet context: /shop; test port: 8080.
Health name mapped to path: status.
Checked URL: http://127.0.0.1:8080/shop/manage/status.
Scope: direct access from same machine, no extra Spring Security.
```

Record the actual timestamp of the attempt alongside the notes. Do not treat a same-machine result as proof that all external hosts can connect.

### Self-check exercises

1. With the experiment's default configuration, locate the exposure line and identify health via the actual link.
2. Expose three specific endpoints and predict the count before rerunning.
3. Compare the endpoint count with the number of `_links` entries and explain why they differ.
4. Change base path, context path, and the health segment as in the example; write down the full URL.
5. Disable the discovery page and check health directly.
6. Given a failed startup log, explain why the endpoint exposure line is not enough to confirm the service is operational.

You are reading logs properly when you can turn a startup message into a verifiable hypothesis while keeping clear boundaries between exposure configuration, application state, and actual access permissions.
