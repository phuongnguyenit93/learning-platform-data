# Configuring BufferingApplicationStartup and Startup Step Buffer Limits

When a Spring Boot application starts slowly, the log line reporting total duration only tells you how long the application took. To investigate, you need to know which steps Spring executed and how long each step lasted. Spring Framework provides the `ApplicationStartup` interface so components can mark startup steps with `StartupStep`. Spring Boot provides `BufferingApplicationStartup` to store completed steps in memory. Actuator can read that exact data through the `startup` endpoint.

## Attaching the Recorder Before Calling run()

For a Spring Boot 3.3.x web application that already includes `spring-boot-starter-actuator`, configure it on the `SpringApplication` instance in the `main` method. The example below replaces `main` in an existing application class.

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

// Place this method in the existing ActuatorApplication class.
public static void main(String[] args) {
    SpringApplication application = new SpringApplication(ActuatorApplication.class);
    application.setApplicationStartup(new BufferingApplicationStartup(2048));
    application.run(args);
}
```

If you are using the shorthand `SpringApplication.run(ActuatorApplication.class, args)`, split it into three lines as above to attach the recorder before Boot starts running. At that point, the early steps of `SpringApplication` can also be recorded. Waiting until a bean is created to attach the recorder misses earlier steps. `2048` is a starting capacity for the example. You will choose a value based on the number of steps observed for your application.

Declare the endpoint to expose over HTTP in the diagnostic environment's `application.properties`. If the application already has a list of endpoints permitted over HTTP, add `startup` to that list.

```properties
management.endpoints.web.exposure.include=health,startup
```

The configuration above opens HTTP access. Calling `setApplicationStartup(...)` supplies the recorder that the endpoint needs. With the default port, default management base path, and appropriate permissions, you can inspect the step count and step names in the buffer. Example using `curl` and `jq`.

```bash
curl -fsS http://localhost:8080/actuator/startup | jq '.timeline.events | length'
curl -fsS http://localhost:8080/actuator/startup |
  jq -r '.timeline.events[] | [.startupStep.name, .duration] | @tsv'
```

Each event has a start time, an end time, and a `duration`. `startupStep.id` and `parentId` let you correlate nested steps when both are present in the recording. When a child step falls within the time span of a parent step, adding both intervals double-counts the overlapping time. Inspect the intervals and parent-child relationships when looking for slow steps.

## What Happens When the Buffer Is Full?

The capacity passed to the constructor is measured in **number of startup step events**. A step completed via `end()` can occupy one slot if it passes the filter and the buffer still has space. Steps can finish in a different order than they started. For example, a child step usually finishes before the parent step wrapping it.

When full, the buffer keeps the events already stored and drops newly arriving events. Therefore, a small capacity can drop late-finishing steps, including parent steps that started early. The work measured by that step still continues to run. Data dropped while full cannot be recovered by reading or draining the buffer afterward.

| Operation | Result | Effect on buffer |
| --- | --- | --- |
| `getBufferedTimeline()` or `GET /actuator/startup` | Returns a snapshot of currently buffered events | Keeps events for subsequent reads |
| `drainBufferedTimeline()` or `POST /actuator/startup` | Returns the drained events | Frees space to accept subsequent completed steps if more occur |

If you need to keep data for multiple people to analyze, save the output from `GET`. When using `POST`, save the response immediately because the operation removes the events from the buffer. With Spring Security, permission to send `POST` also depends on security configuration, including CSRF checks if enabled. Step names and tags can expose bean names or internal details, so restrict endpoint access to authorized operators.

## Trying with a Two-Slot Buffer

The following program uses the step-recording API directly. You can observe the limit on a single thread without running a web server. Save the program to `StartupBufferDemo.java`.

```java
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.boot.context.metrics.buffering.StartupTimeline;

public class StartupBufferDemo {
    public static void main(String[] args) {
        var startup = new BufferingApplicationStartup(2);
        startup.addFilter(step -> step.getName().startsWith("demo."));

        startup.start("other.ignored").end();
        startup.start("demo.first").end();
        startup.start("demo.second").end();
        startup.start("demo.third").end();

        System.out.println("Snapshot: " + names(startup.getBufferedTimeline()));
        System.out.println("Drain: " + names(startup.drainBufferedTimeline()));
        System.out.println("After drain: " + names(startup.getBufferedTimeline()));

        startup.start("demo.fourth").end();
        System.out.println("After new step: " + names(startup.getBufferedTimeline()));
    }

    private static java.util.List<String> names(StartupTimeline timeline) {
        return timeline.getEvents().stream()
                .map(event -> event.getStartupStep().getName())
                .toList();
    }
}
```

Use JDK 17 or later. Place `spring-boot-3.3.0.jar` and `spring-core-6.1.8.jar` into a `lib` directory next to the Java file, then compile and run.

```bash
javac -cp "lib/*" StartupBufferDemo.java
java -cp ".:lib/*" StartupBufferDemo
```

On Windows, use `java -cp ".;lib/*" StartupBufferDemo`. The output is printed in the following order.

```text
Snapshot: [demo.first, demo.second]
Drain: [demo.first, demo.second]
After drain: []
After new step: [demo.fourth]
```

`other.ignored` is excluded by the filter, so the first two steps with prefix `demo.` fill both slots. `demo.third` finishes when full, so it does not appear even after draining. `demo.fourth` finishes after space becomes available, so it is recorded.

## Choosing Capacity and Filters

1. Restart the application with configuration and bean set close to the environment under investigation. Read `GET /actuator/startup` before any drain operation and record the event count and names of steps to track.
2. If the event count hits capacity, increase the capacity and restart to compare. Reaching the limit is a sign to investigate. If more events appear on the next run under the same conditions, the previous run may have run out of slots. Choose a capacity sufficient for the deployment profiles to track and leave headroom as the step count changes.
3. When you only care about a subset of steps, call `addFilter(...)` on the recorder before `run()`. For example, the predicate `step -> step.getName().startsWith("spring.beans.")` keeps only steps with that prefix. Multiple calls to `addFilter(...)` combine predicates using logical **AND**. Capture a sufficiently broad recording before filtering so you know which steps will be excluded. Retained child steps may reference a parent step that was filtered out.
4. Balance collection scope against the cost of holding events in memory and HTTP response size. When the list is unexpectedly empty or short, check in order whether the recorder was attached before `run()`, whether a filter excluded needed steps, whether someone just drained the data, and whether capacity was reached.

Spring Boot 3.3 documentation. [BufferingApplicationStartup API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/metrics/buffering/BufferingApplicationStartup.html) · [startup endpoint REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/startup.html)
