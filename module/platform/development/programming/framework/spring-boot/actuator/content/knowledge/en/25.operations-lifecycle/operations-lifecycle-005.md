# Tracking AvailabilityChangeEvent in the Application Lifecycle

A Spring Boot application may have finished initializing the Spring context while still loading required data before serving requests. At that point, the application is still operating normally, while the load balancer needs to wait. Spring Boot represents these two decisions with two independent state types and publishes `AvailabilityChangeEvent<S>` so components inside the application can observe state publications.

| State type | Spring Boot values | Operational question |
| --- | --- | --- |
| `LivenessState` | `CORRECT`, `BROKEN` | Is the process still functioning properly or able to recover on its own? |
| `ReadinessState` | `ACCEPTING_TRAFFIC`, `REFUSING_TRAFFIC` | Should infrastructure route new requests to this application instance right now? |

For example, when an application instance is warming up a cache, the sensible states are `CORRECT` and `REFUSING_TRAFFIC`. Infrastructure can temporarily hold off routing requests to that instance while allowing it to continue preparing.

## When Does Spring Boot Publish States?

The sequence below applies to a successful startup on Spring Boot 3.3.x with default synchronous event handling.

| Milestone | What can be observed |
| --- | --- |
| Before Boot publishes a state | Once `ApplicationAvailability` can be read, `getLivenessState()` and `getReadinessState()` default to `BROKEN` and `REFUSING_TRAFFIC` if no corresponding event has been received yet. Default values can appear before any event exists. |
| After refreshing the Spring context | Boot emits `ApplicationStartedEvent`, then emits `AvailabilityChangeEvent<LivenessState>` with `CORRECT`. |
| While running `ApplicationRunner` and `CommandLineRunner` | Liveness is typically already `CORRECT`. Readiness remains the default `REFUSING_TRAFFIC` unless the application explicitly publishes a different value. |
| After runners finish | Boot emits `ApplicationReadyEvent`, then emits `AvailabilityChangeEvent<ReadinessState>` with `ACCEPTING_TRAFFIC`. |
| When closing an active web context | Boot publishes `REFUSING_TRAFFIC` when context shutdown begins. With graceful shutdown enabled, the server has time to finish in-flight requests according to the shutdown configuration. |

If the goal is to record the exact moment Boot **publishes readiness**, listen for `AvailabilityChangeEvent<ReadinessState>`. `ApplicationReadyEvent` listeners run before the default `ACCEPTING_TRAFFIC` publication. If a runner only schedules background work and returns, Boot may report ready while the background work is still running. Complete required preparation inside the runner if it determines whether the application can serve safely.

## Choosing the Right Way to Observe

- **Record publications.** Put an `@EventListener` method on a Spring bean and use a specific parameter type such as `AvailabilityChangeEvent<ReadinessState>`. If you also need to track liveness, add a method accepting `AvailabilityChangeEvent<LivenessState>`. Inside the listener, get the published state from `event.getState()`. You can also log `event.getTimestamp()` and the source from `event.getSource()` when investigating.
- **Read the current state.** Inject `ApplicationAvailability` and call `getReadinessState()` or `getLivenessState()` at the moment a decision is needed. `getLastChangeEvent(ReadinessState.class)` returns the most recent event received for that state type, or `null` if none exists yet. If you need to reconstruct the sequence across multiple transitions or across a restart, persist the event log outside the process.
- **Publish application-driven states.** Call `AvailabilityChangeEvent.publish(context, state)` on the application context. For example, an instance preparing for maintenance can publish `REFUSING_TRAFFIC`, then publish `ACCEPTING_TRAFFIC` once it can serve again. Define which component owns this decision because each publication updates the latest state for that type. Re-publishing the same value still dispatches an event, so handlers must tolerate duplicate notifications.

By default, Spring invokes event listeners on the publishing thread. Short log statements suit this lifecycle milestone. If you need to send data over the network or run long tasks, move that work off the listener to avoid prolonging startup or shutdown.

## Practice with Java 17 and Spring Boot 3.3

The program below runs Spring Boot without a web server to observe the event order directly. Boot automatically publishes the two startup milestones. After `run()` returns, the program publishes two readiness events itself to simulate pausing request intake and resuming. Save the code to `AvailabilityDemo.java`.

```java
package demo.availability;

import java.util.Map;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class AvailabilityDemo {
    public static void main(String[] args) {
        var application = new SpringApplication(AvailabilityDemo.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);
        application.setDefaultProperties(Map.of("logging.level.root", "OFF"));

        try (var context = application.run(args)) {
            AvailabilityChangeEvent.publish(context, ReadinessState.REFUSING_TRAFFIC);
            AvailabilityChangeEvent.publish(context, ReadinessState.ACCEPTING_TRAFFIC);

            var availability = context.getBean(ApplicationAvailability.class);
            System.out.println("AFTER_RESUME " + availability.getReadinessState());
        }
    }

    @Bean
    ApplicationRunner checkWhileStarting(ApplicationAvailability availability) {
        return args -> System.out.println("RUNNER " + availability.getLivenessState()
                + " / " + availability.getReadinessState());
    }

    @EventListener
    public void onLiveness(AvailabilityChangeEvent<LivenessState> event) {
        System.out.println("LIVENESS " + event.getState());
    }

    @EventListener
    public void onReadiness(AvailabilityChangeEvent<ReadinessState> event) {
        System.out.println("READINESS " + event.getState());
    }
}
```

To run standalone, place the following `pom.xml` next to the Java file. The project only needs libraries from `spring-boot-starter`.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo.availability</groupId>
    <artifactId>availability-demo</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
            <version>3.3.0</version>
        </dependency>
    </dependencies>
</project>
```

From the directory containing both files, download libraries with Maven, then compile and run with JDK 17 or later.

```bash
mvn -q dependency:copy-dependencies -DincludeScope=runtime -DoutputDirectory=lib
javac -cp "lib/*" -d out AvailabilityDemo.java
java -cp "out:lib/*" demo.availability.AvailabilityDemo
```

On Windows, use `java -cp "out;lib/*" demo.availability.AvailabilityDemo`. When run with the example's default configuration, the program prints the following lines.

```text
LIVENESS CORRECT
RUNNER CORRECT / REFUSING_TRAFFIC
READINESS ACCEPTING_TRAFFIC
READINESS REFUSING_TRAFFIC
READINESS ACCEPTING_TRAFFIC
AFTER_RESUME ACCEPTING_TRAFFIC
```

The `RUNNER` line illustrates the window where liveness and readiness differ. The two `READINESS ACCEPTING_TRAFFIC` lines come from two separate publications. The first is emitted by Boot after the runner. The second is emitted by the program at the end of the simulated maintenance. `AFTER_RESUME` confirms the final publication updated the value other components read via `ApplicationAvailability`.

## Comparing Against Actuator Probes

In a **web** application with `spring-boot-starter-actuator`, you can enable the two probe groups locally with the following configuration. The CLI examples assume port `8080`, the default management base path, and appropriate access permissions.

```properties
management.endpoint.health.probes.enabled=true
```

```bash
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
```

With default groups and an accessible endpoint, `CORRECT` maps to `UP` for liveness. `REFUSING_TRAFFIC` maps to `OUT_OF_SERVICE` for readiness and returns HTTP 503 by default. `ACCEPTING_TRAFFIC` brings the readiness group back to `UP`. The event tells you **when the application published a state**, whereas the HTTP call tells you **the group's state at check time**. When the server has not opened its port or has already closed it, you may get a connection error instead of an HTTP response.

Publishing `REFUSING_TRAFFIC` updates the signal that infrastructure reads. For the load balancer to stop sending new requests, infrastructure must use the readiness signal for routing decisions. If a shared dependency such as a database fails, weigh the impact on serving capability when configuring readiness. Binding that failure to liveness can restart many instances simultaneously while the underlying cause remains.

Spring Boot 3.3 documentation. [Lifecycle and event ordering](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-events-and-listeners) · [AvailabilityChangeEvent API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/AvailabilityChangeEvent.html) · [Actuator probe groups](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
