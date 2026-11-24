# Correlating Startup Data with Slow-Initializing Beans and External Dependencies

When a new instance takes several extra seconds before it is ready to receive traffic, the total duration log line only indicates the overall delay. The Actuator timeline helps isolate **which step is holding up startup**. For example, `reportService` may take over a second to appear, yet most of that time may come from `remoteConfig` waiting for a configuration service to respond over HTTP.

## Reading the Timeline by Parent-Child Relationships

In Spring Boot 3.3, configure `BufferingApplicationStartup` on `SpringApplication` before `run(args)` to store the measured steps. When the application has Actuator and exposes the `startup` endpoint over HTTP, `GET /actuator/startup` fetches a snapshot of the buffer. Use GET to preserve the data for subsequent reads. `POST /actuator/startup` drains the current events from the buffer and returns them.

| Field | How to read it when finding slow beans |
| --- | --- |
| `timeline.startTime` | Start timestamp of the recording, used to place events on the same timeline axis. |
| `startTime`, `endTime`, `duration` | Elapsed time interval of a step. `PT1.2S` is 1.2 seconds. This interval can include CPU execution time, I/O wait, and nested steps. |
| `startupStep.name` and `tags` | For `spring.beans.instantiate`, look for the tag with `key=beanName` to see which bean is being created. Step names emitted by Spring can change between versions. |
| `startupStep.id` and `parentId` | Links child steps to parent steps within the same run. Sort by `startTime` when you need to see start order. |

A bean-creation step can encompass resolving dependent beans, invoking `@Bean` methods, running initialization callbacks such as `@PostConstruct`, and processing through `BeanPostProcessor` implementations. When a child step lies inside a parent step, its duration is already included in the parent's interval. Adding both will double-count. If multiple child steps overlap, consider the union of intervals before estimating the parent's remaining time. That remainder is still only elapsed time not explained by the recorded child steps.

`parentId` describes the nesting relationship of recorded steps in that run. A dependent bean that already exists can be reused without appearing as a new child step. The buffer has a step limit, so when an expected event is missing, check capacity, filters, whether POST was called, and when the work actually ran.

## Experiment with a Local HTTP Configuration Service

Create a separate Gradle project with JDK 17+, a Gradle version compatible with your JDK, and Python 3. Use the same application version for both runs. The mock HTTP service runs in a separate process, returns the same payload, and varies only the wait time.

File `build.gradle`

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}

application {
    mainClass = 'demo.StartupDemo'
}
```

File `src/main/resources/application.properties`

```properties
server.address=127.0.0.1
management.endpoints.web.exposure.include=health,startup,metrics
```

File `src/main/java/demo/StartupDemo.java`

```java
package demo;

import java.net.URI;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Lazy;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.core.metrics.ApplicationStartup;
import org.springframework.core.metrics.StartupStep;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@SpringBootApplication
public class StartupDemo {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(StartupDemo.class);
        app.setApplicationStartup(new BufferingApplicationStartup(2048));
        app.run(args);
    }

    @Bean
    ReportService reportService(RemoteConfig config) {
        return new ReportService(config);
    }

    @Bean
    @Lazy
    RemoteConfig remoteConfig(ApplicationStartup startup,
            @Value("${demo.config-url:http://127.0.0.1:9090/config}") URI uri) {
        SimpleClientHttpRequestFactory transport = new SimpleClientHttpRequestFactory();
        transport.setConnectTimeout(1000);
        transport.setReadTimeout(3000);
        RestClient client = RestClient.builder().requestFactory(transport).build();

        StartupStep fetch = startup.start("demo.remote-config.fetch")
                .tag("dependency", "config-service");
        try {
            String body = client.get().uri(uri).retrieve().body(String.class);
            return new RemoteConfig(body);
        } finally {
            fetch.end();
        }
    }

    record RemoteConfig(String value) {}
    record ReportService(RemoteConfig config) {}
}
```

`remoteConfig` is annotated with `@Lazy` on its definition so Spring skips eager initialization for this bean. `reportService` is still created at startup and immediately requires `RemoteConfig` via its `@Bean` method parameter. As a result, the HTTP call executes during the creation of `reportService`. The custom-named step `demo.remote-config.fetch` measures the synchronous HTTP call and result handling region, while `finally` ends the step even if the call throws an exception. The tag uses the logical service name to avoid putting configuration payloads or credentials into the recording.

File `mock_config.py`

```python
from http.server import BaseHTTPRequestHandler, HTTPServer
import sys
import time

delay_seconds = float(sys.argv[1]) / 1000


class ConfigHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/config":
            self.send_error(404)
            return
        time.sleep(delay_seconds)
        body = b"mode=standard"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


with HTTPServer(("127.0.0.1", 9090), ConfigHandler) as server:
    server.serve_forever()
```

Run `python mock_config.py 1200` in the first terminal and `gradle run` in the second terminal. The example configuration listens only on the machine's loopback address. Once the application has started, fetch the timeline and time-to-ready metric from a third terminal. On Windows PowerShell, you can use `curl.exe`.

```bash
curl --fail --silent --show-error http://127.0.0.1:8080/actuator/startup -o startup-slow.json
curl --fail --silent --show-error http://127.0.0.1:8080/actuator/metrics/application.ready.time -o ready-slow.json
```

Stop both processes. Run again with `python mock_config.py 0` and `gradle run`, then save the two responses to `startup-fast.json` and `ready-fast.json`. Compare the three steps by name and tag in `timeline.events`. Read the IDs along with the timestamps from each run.

Results from a pair of runs on Java 17 and Spring Boot 3.3.0, using the same Tomcat NIO2 connector in the verification environment:

| Step or metric | Service waits 1,200 ms | Service waits 0 ms |
| --- | --- | --- |
| `reportService` | `PT1.294583S` | `PT0.0655701S` |
| `remoteConfig` | `PT1.2935835S` | `PT0.0635704S` |
| `demo.remote-config.fetch` | `PT1.2580593S` | `PT0.0490026S` |
| `application.ready.time` | 11.4 s | 10.314 s |

In the slow run, `reportService` had ID `103`, `remoteConfig` had ID `104` with `parentId=103`, and `demo.remote-config.fetch` had ID `105` with `parentId=104`. The HTTP call lasted about 1.258 seconds out of the 1.295 seconds of the `reportService` creation step. This is the same waiting interval observed at three levels.

The slow run shows two bean-creation steps are long because they both wrap a single configuration fetch. When the delay is removed in the mock service, the HTTP step and both bean-creation steps shorten together. The observed difference can vary from 1,200 ms due to initial connection setup, thread scheduling, and machine load. The HTTP step measures from the application side, so it still includes network time, service-side processing, and response reception.

## From a Slow Step to a Verifiable Cause

1. **Identify the slow phase.** Compare `application.started.time` with `application.ready.time` and use the same run conditions across samples. Spring Boot emits `ApplicationStartedEvent` after refreshing the context, then invokes runners before `ApplicationReadyEvent`. If the slowdown is mainly between these two milestones, instrument runners and synchronous tasks in that phase. If it is slow before the started milestone, prioritize analyzing the context initialization timeline.
2. **Trace from parent step down to child steps.** Find long bean-creation steps, follow `parentId`, and inspect the bean code closest to the suspect operation. Check places such as constructors, `@Bean` methods, `@PostConstruct`, lifecycle callbacks, and bean post-processors. For JDBC, distinguish connection acquisition wait, opening a connection, authentication, and running queries or migrations. For HTTP, check DNS, connect, TLS, response wait, and retries. A single bean name can encompass multiple kinds of cost.
3. **Cross-check with independent measurements.** Place a custom step around the suspect call or correlate logs, traces, and server-side data using timestamps and correlation IDs if available. Java Flight Recorder can add CPU, class loading, GC, or I/O traces. If you use `FlightRecorderApplicationStartup` instead of the example's buffer, collect Spring events via a JFR recording. If the application crashes or hangs before Actuator is reachable, use startup logs, a JVM startup JFR recording, or thread dumps to continue investigating.
4. **Change one factor and measure again.** Hold configuration, data, machine resources, and launch method constant. Compare a few fresh startups with the dependency responding normally, slowly, or failing. Predict beforehand which step will lengthen and how the readiness milestone will shift. The example above changed only the mock service delay, directly testing the hypothesis that I/O lengthened the bean-creation step.

## Choosing How to Handle Based on Dependency Role

- **Data required before receiving traffic.** Keep readiness tied to having fetched and validated the data. Set connect and operation timeouts, bound total retry duration, and log errors thoroughly enough to trace. If initialization fails, choosing between failing startup and keeping the instance unready depends on how the system deploys and recovers. With Kubernetes, avoid tying liveness to a shared external service because an outage of that service can restart many instances simultaneously.
- **Data that can be loaded later.** Initialize the local client first and move I/O to a controlled background loading task when the application has fallback data or a clearly defined degraded serving mode. Also measure first-request latency and the time until the data is actually usable. Lazy initialization can shift cost or errors to the moment the bean is requested. Moving work into an `ApplicationRunner` still keeps it before the ready milestone if the runner waits synchronously until completion.
- **Verify after changes.** Capture the timeline and readiness milestone again, then test when the dependency is normal, slow, and failing. Compare startup time alongside serving behavior. If time before readiness decreases while the first request becomes correspondingly slower, the cost was shifted onto the request path.

## Reference Documentation

- [Spring Boot 3.3 · Startup Endpoint HTTP Contract](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/startup.html)
- [Spring Boot 3.3 · Recording Application Startup](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-startup-tracking)
- [Spring Boot 3.3 · Application Startup Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.application-startup)
- [Spring Boot 3.3 · Checking External Dependencies via Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes.external-state)