# Integrating micrometer-registry-prometheus and Exposing the Prometheus Endpoint

In a Spring Boot application, Micrometer records measurements such as API call counts and JVM memory usage. The Prometheus registry converts these measurements into a format that Prometheus can read. Actuator provides an HTTP path for Prometheus to actively pull data periodically. Each such data pull is called a scrape.

~~~text
Application records measurements into Micrometer's MeterRegistry
                   ↓
Prometheus registry formats measurements as samples
                   ↓
Actuator serves GET /actuator/prometheus
                   ↑
Prometheus scrapes periodically and stores samples over time
~~~

There are two separate conditions for a successful integration. The application must have the Prometheus registry to prepare the data. The `prometheus` endpoint must be exposed over HTTP so the scraper can call it.

## 1. Add Actuator and the registry

For an existing Spring Boot application using Gradle, add the following two dependencies to the `dependencies` block if missing. Use Spring Boot's dependency management for Micrometer versions.

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

`spring-boot-starter-actuator` provides the endpoint management infrastructure and Micrometer. When `micrometer-registry-prometheus` is present at runtime, Spring Boot can auto-configure the Prometheus registry. Application code can inject `MeterRegistry` via the constructor and use Micrometer's common API. This approach works even if the project has another registry as well.

To run the standalone example with Maven, create the following `pom.xml`. The example uses Java 17 or later and Spring Boot 3.3.13. Starter Web provides the HTTP server for both the sample API and the Actuator endpoints.

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>prometheus-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-registry-prometheus</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

## 2. Expose the endpoint over HTTP

Add to `src/main/resources/application.properties`:

~~~properties
server.address=127.0.0.1
management.endpoints.web.exposure.include=health,prometheus
~~~

Spring Boot 3.3 exposes only the `health` endpoint over HTTP by default. The `include` list in the example keeps `health` and additionally exposes `prometheus`. With the default application port 8080 and the default Actuator prefix `/actuator`, the URL will be `http://127.0.0.1:8080/actuator/prometheus`. `server.address` restricts the example to loopback so the application and the scraper can be tested on the same machine.

Three configuration groups act at different layers:

| Layer | Property | Effect |
| --- | --- | --- |
| Registry | `management.prometheus.metrics.export.enabled` | Controls auto-configuration of the Prometheus exporter when the dependency is present. Default is `true`. |
| Endpoint | `management.endpoint.prometheus.enabled` | Controls the Actuator endpoint in Spring Boot 3.3. If the project has disabled endpoints by default via `management.endpoints.enabled-by-default=false`, you need to enable `prometheus` explicitly to use it. |
| HTTP Exposure | `management.endpoints.web.exposure.include` | Selects endpoint IDs that can be called over the web. If `exclude` also matches, `exclude` takes precedence. |

`/actuator/prometheus` returns samples in Prometheus format, such as `text/plain` in the scrape exposition format. `/actuator/metrics` is a separate endpoint to look up metric names and measurements via JSON when exposed. Use the `prometheus` endpoint for `metrics_path`.

## 3. Verify data with a counter

Create `src/main/java/example/PrometheusDemoApplication.java`:

~~~java
package example;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PrometheusDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PrometheusDemoApplication.class, args);
    }
}

@RestController
class PingController {
    private final Counter requests;

    PingController(MeterRegistry registry) {
        this.requests = registry.counter("demo.ping.requests");
    }

    @GetMapping("/demo/ping")
    String ping() {
        requests.increment();
        return "pong";
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Once the application is ready, open a second terminal and send three successful requests. On Windows PowerShell, you can use `curl.exe` in the same commands.

~~~bash
curl -fsS http://127.0.0.1:8080/demo/ping
curl -fsS http://127.0.0.1:8080/demo/ping
curl -fsS http://127.0.0.1:8080/demo/ping
curl -fsSi http://127.0.0.1:8080/actuator/prometheus
~~~

Each call to `/demo/ping` returns the response body `pong`. The Actuator call is expected to return HTTP 200 and multiple lines of measurements. If the application has just started and only received the three calls above, look for the following sample in the response body:

~~~text
demo_ping_requests_total 3.0
~~~

Micrometer converts `demo.ping.requests` into a name following the Prometheus naming convention, with underscores and the `_total` suffix for a counter. The value 3 is the total count for the current process. Reading the Actuator endpoint does not increment this counter. When the process restarts, the example's counter starts over from 0.

## 4. Configure Prometheus scraping and verify from the server side

If you already have Prometheus running directly on the same machine, add the following job to `scrape_configs` in `prometheus.yml`. If using a separate configuration file for testing, you can use this entire block.

~~~yaml
scrape_configs:
  - job_name: 'spring-demo'
    metrics_path: '/actuator/prometheus'
    scrape_interval: 15s
    static_configs:
      - targets: ['127.0.0.1:8080']
~~~

`targets` accepts `host:port` addresses. `metrics_path` is the path component, defaulting to `/metrics` in Prometheus if omitted. If running with a separate test file, validate and then start Prometheus:

~~~bash
promtool check config prometheus.yml
prometheus --config.file=prometheus.yml
~~~

After a scrape, check the Prometheus Targets page or query `up{job="spring-demo"}`. A value of `1` indicates that Prometheus scraped successfully. Also query `demo_ping_requests_total{job="spring-demo"}` to confirm the application's time series has been stored. If you call `/demo/ping` again, wait for the next scrape to see the value increase.

Target addresses are resolved from where **Prometheus** runs. Inside a container, `127.0.0.1` refers to the Prometheus container itself. When the two processes are in different network environments, use a service name or address reachable by Prometheus, and configure the application to listen on an appropriate network interface. If you separate `management.server.port` or change `management.endpoints.web.base-path`, update the job's port or path accordingly.

## Troubleshooting by failure point

| Symptom | Where to check |
| --- | --- |
| HTTP 404 | Check the Actuator and registry dependencies on the runtime classpath. Then verify the registry status, endpoint status, `include`/`exclude`, actual path, and management port. |
| HTTP 401 or 403 | Check the credentials and permissions for calling the endpoint from Prometheus. With Spring Security, access rules and endpoint exposure configuration are two separate layers. |
| `curl` succeeds on the application host, but target reports DOWN | Read the error on the Targets page. Check connectivity from the Prometheus environment, including DNS, port, path, TLS, or access permissions depending on the error. |
| `up` equals 1, but sample metric is missing | Look for the metric line in the scrape response, verify the Prometheus-convention name, and check when the meter was registered. If the line is already in the response, check label filters and the job's metric filtering rules. |

In production, restrict the exposed endpoint IDs, keep the scrape path within the monitoring network, and grant access according to the environment's security configuration. If the project defines its own `SecurityFilterChain`, place the rules for Actuator endpoints in that configuration.

### References

- [Spring Boot 3.3 – Registry integration and metrics collection](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Spring Boot 3.3 – Exposing and securing Actuator endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
- [Spring Boot 3.3 – Prometheus endpoint response format](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/prometheus.html)
- [Prometheus – Scrape job configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)