# Coordinating Stopping Traffic, Completing In-Flight Requests, and Shutdown Timeouts

A server writing an order may receive a stop signal right in the middle of a write. If the process disappears immediately, the caller may lose the response even though the data was already saved. If new requests keep getting routed to a stopping server, the backlog to complete grows. **Graceful shutdown** coordinates three steps: stop assigning new work, give accepted work time to finish, and release resources within a defined limit.

## Each Layer Does Its Part

| Layer | What to coordinate | Observable signals |
| --- | --- | --- |
| Router or load balancer | Stop selecting an instance that is draining out of service. | Backend status, readiness probe, EndpointSlice, and routing logs. |
| Spring Boot and HTTP server | Transition readiness to `REFUSING_TRAFFIC` when shutdown starts, stop accepting new HTTP requests via the server's mechanism, and wait for in-flight requests. | `AvailabilityChangeEvent` events, shutdown start/end logs, HTTP caller outcomes. |
| Application code and background resources | Stop pulling more work, finish or hand off remaining work, close resources in dependency order. | Active work count, final message acknowledgments, executor and connection pool close logs. |
| Deployment environment | Send the stop signal and allow enough time before forcing the process to exit. | Signal reception timestamp, exit time, exit code or termination reason. |

Readiness expresses **whether this instance should still receive traffic**. While Actuator can still respond, `/actuator/health/readiness` supplies status to the orchestrator. Once the server or probe port closes, probes may fail to connect rather than return a `503` response. While the application is still finishing existing requests, liveness can remain `CORRECT`. Removing an instance from routing takes propagation time, so readiness and server-level rejection reinforce each other.

## How Does Spring Boot 3.3 Shut Down an Application?

1. **Trigger the normal shutdown path.** When the JVM handles `SIGTERM` and the default shutdown hook is active, Spring Boot closes `ApplicationContext`. In Linux containers, configure the entrypoint command so signals reach the JVM, such as exec form in `ENTRYPOINT` or `exec java …` at the end of a script. `SIGKILL` terminates the process immediately, bypassing this shutdown path.
2. **Block new requests and drain in-flight work.** On the 3.3 line, enable `server.shutdown=graceful` to use the wait phase, as the default is `immediate`. The web server wait runs in the earliest `SmartLifecycle` shutdown phase. Tomcat, Jetty, and Reactor Netty stop accepting at the network layer. Undertow may still accept connections and return `503` immediately. Long-lived connections, proxies, and connection reuse can change client-side symptoms.
3. **Proceed through remaining phases.** `spring.lifecycle.timeout-per-shutdown-phase` sets the wait timeout for **each group of `SmartLifecycle` beans in the same phase**. Once the server finishes all requests, the wait step can finish early. When the timeout expires, Spring continues shutting down and remaining in-flight requests may lose their connection before returning a result. Total close time also includes other phases, bean destruction callbacks, and server or JVM cleanup. This property is a per-phase wait limit. A blocking synchronous stop method or slow bean destroy callback can still lengthen shutdown time.

`SmartLifecycle` components typically stop in descending phase order, respecting dependency relationships. For components implementing `stop(Runnable)`, invoke the callback when stopping is truly complete so the lifecycle coordinator knows when to advance. Keep database connections or HTTP clients usable until tasks that depend on them finish. Non-HTTP processing loops such as consumers, scheduled jobs, and tasks offloaded to executors need their own policies to stop intake, wait boundedly, and handle remaining work.

## Actuator Experiment with an Eight-Second Request

Use JDK 17+ and a compatible Gradle version. Create a separate project with the three files below. The example uses the Tomcat NIO2 connector to run with the same server configuration as the verification run. The `shutdown` endpoint is exposed for the local experiment on `127.0.0.1` and actively closes the context. The POST response confirms the shutdown command was accepted. Process exit and the outcome of the in-flight request are verified separately.

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
    mainClass = 'demo.ShutdownDemo'
}
```

File `src/main/resources/application.properties`

```properties
server.address=127.0.0.1
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=15s
management.endpoint.health.probes.enabled=true
management.endpoint.shutdown.enabled=true
management.endpoints.web.exposure.include=health,shutdown
```

File `src/main/java/demo/ShutdownDemo.java`

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ShutdownDemo {

    public static void main(String[] args) {
        SpringApplication.run(ShutdownDemo.class, args);
    }

    @Bean
    WebServerFactoryCustomizer<TomcatServletWebServerFactory> useNio2() {
        return factory -> factory.setProtocol("org.apache.coyote.http11.Http11Nio2Protocol");
    }

    @GetMapping("/work")
    public String work() throws InterruptedException {
        System.out.println("WORK_START");
        Thread.sleep(8000);
        System.out.println("WORK_FINISH");
        return "done";
    }

    @EventListener
    public void onReadiness(AvailabilityChangeEvent<ReadinessState> event) {
        System.out.println("READINESS " + event.getState());
    }
}
```

1. In terminal A, run `gradle run` and wait for `READINESS ACCEPTING_TRAFFIC`. You can check readiness with `curl -i http://127.0.0.1:8080/actuator/health/readiness`. In this example, the ready response is `200` and `{"status":"UP"}`.
2. In terminal B, run the command below. `WORK_START` in terminal A confirms the request entered the handler method. `Thread.sleep` simulates a task with a known duration.

   ```bash
   curl -i --max-time 20 http://127.0.0.1:8080/work
   ```

3. As soon as you see `WORK_START`, send the shutdown command from terminal C. Use `curl.exe` if running on Windows PowerShell.

   ```bash
   curl -i -X POST http://127.0.0.1:8080/actuator/shutdown
   ```

   When terminal A logs that graceful shutdown has started, try opening a new HTTP connection to readiness.

   ```bash
   curl -i --max-time 2 http://127.0.0.1:8080/actuator/health/readiness
   ```

4. Wait for the process to exit. Repeat with `gradle run --args="--spring.lifecycle.timeout-per-shutdown-phase=2s"`, keeping the eight-second request. Send the shutdown command shortly after `WORK_START` so that when shutdown begins, the request still has more than two seconds of work left.

Measured results on Java 17, Spring Boot 3.3.0, and Tomcat NIO2:

| Phase timeout | Already-accepted eight-second request | New HTTP connection after shutdown starts |
| --- | --- | --- |
| 15 seconds | Logs `WORK_FINISH`, caller receives `HTTP/1.1 200` with body `done`. Logs then report graceful shutdown completed. | curl reports `000`, meaning the attempt received no HTTP status code. |
| 2 seconds | Logs report `webServerGracefulShutdown` still active when the 2,000 ms phase expires. curl reports `(52) Empty reply from server`. | curl also reports `000`. |

Both runs log `READINESS REFUSING_TRAFFIC` after `WORK_START` and before the log message that the server started waiting. The 15-second run finishes waiting about 7.46 seconds after the server starts shutting down. The 2-second run moves on while a request is still active.

The observed ordering matters more than a fixed error code: the first request entered the application, the server began closing, and then the first request either completed or was interrupted depending on remaining time. The exact response on a new connection can vary with send timing, server, and intermediaries. If a test sends the new request before the server starts blocking, the outcome only reflects the transition window.

## Aligning Time Budgets in Deployment

Separate three clocks when choosing configuration:

- **Request limits** cover timeouts at the caller, proxy, and downstream dependencies. If a proxy times out after 10 seconds, a server given 20 seconds to shut down may finish work after the caller has already disconnected. Choose timeouts based on real request types, including slow queries, data transfers, and retries to downstream services.
- **In-application wait time** must cover remaining work for accepted requests and ordered shutdown steps. For long-running work or continuous streams such as SSE, design termination points, reconnect mechanisms, or recovery paths. For writes, a lost response can leave the caller uncertain whether a transaction succeeded. Idempotency keys or status-check workflows help callers retry safely.
- **Environment time budget for the process** must cover `preStop` if present, measured JVM shutdown and cleanup, plus safety margin. For example, if the router needs up to 5 seconds to stop sending traffic during preparation, budget 20 seconds for in-flight requests, 8 seconds for other shutdown steps, and 7 seconds of margin, giving an example budget of 40 seconds. Validate numbers through rollout tests under real load.

On Kubernetes, the `terminationGracePeriodSeconds` timer starts before `preStop`. When a Pod enters terminating state, EndpointSlice updates happen in parallel with local shutdown steps, so the order observed by proxies can differ from application log order. In the normal flow, kubelet executes `preStop` if configured, sends the stop signal to the main process, and may force-kill when the grace period expires. Losing probe connectivity after shutdown begins is a signal to read alongside routing status and logs, because probes only reflect the HTTP path they hit.

## Testing Under Load During Rollouts

1. Send a short request, a long request, and a new request after shutdown starts. Test both directly against the server and through the load balancer to isolate the two layers.
2. Correlate backend removal start, readiness, shutdown start, last response, and process exit timestamps. Check the number of accepted requests interrupted, connection errors or `5xx` responses, and forced terminations.
3. Repeat with tight budgets, slow dependencies, or unfinished background work. Verify data writes, message acknowledgments, and caller retry behavior. A fast shutdown can come from dropping work mid-flight, so measure both exit time and the outcome of each work type.

## Reference Documentation

- [Spring Boot 3.3 · Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html)
- [Spring Boot 3.3 · Actuator shutdown](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/shutdown.html)
- [Spring Boot 3.3 · Endpoints and Probe States](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
- [Spring Framework 6.1 · SmartLifecycle](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/context/SmartLifecycle.html)
- [Kubernetes · Pod Lifecycle and Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)