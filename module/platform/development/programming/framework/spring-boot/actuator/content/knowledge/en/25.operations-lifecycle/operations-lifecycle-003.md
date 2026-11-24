# Reading a Snapshot and Draining Startup Data from the Buffer

When investigating a slow startup, you may need to inspect the same set of events multiple times or transfer those events to external storage. Both operations use the default path `/actuator/startup`, but the HTTP method determines whether the data remains in the buffer after the request.

| Operation | What does the response contain? | Buffer after the request |
| --- | --- | --- |
| `GET /actuator/startup` | A point-in-time snapshot of recorded steps still currently in the buffer. | The events just read remain. |
| `POST /actuator/startup` | The steps drained in this call. The request requires no body. | The returned events have been removed from the buffer. |

## How Does the Buffer Change?

Before running the application, attach `BufferingApplicationStartup` to `SpringApplication` to collect startup steps. When a step completes and is recorded, the collector stores information about that step in process memory. Capacity is bounded: when full, new steps may be dropped. Both reading and draining afterward operate only on what was retained.

In Spring Boot 3.3, the read operation of `StartupEndpoint` uses `getBufferedTimeline()`, while the write operation uses `drainBufferedTimeline()`. Both return a JSON structure with `springBootVersion` and `timeline`. Inspect `timeline.events` to see the returned events. Each event has a start time, an end time, a duration, and step details such as the step name in `startupStep.name`. The `timeline.startTime` field is the start timestamp of the timeline. Draining events does not reset this timestamp or restart the application.

Assume the buffer holds A and B, requests go to the same process, and no new events occur in between:

1. The first `GET` returns A and B. The buffer still holds A and B.
2. The second `GET` still returns A and B.
3. `POST` removes A and B from the buffer and returns them in the response.
4. The next `GET` returns an empty array in `timeline.events`. Calling `POST` once more also returns an empty list. Both can still return `200 OK` with the full JSON structure.

If new steps are recorded after a drain, subsequent reads can see the new events. Two snapshots at different times can therefore differ even when both use `GET`.

## Trying on a Spring Boot 3.3 Application

The example uses Java 17 or later, Gradle, and a local application with two dependencies: `spring-boot-starter-web` and `spring-boot-starter-actuator`. Create the following three files in a dedicated test directory.

**`build.gradle`**

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

**`src/main/java/demo/StartupDemo.java`**

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

@SpringBootApplication
public class StartupDemo {
    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(StartupDemo.class);
        app.setApplicationStartup(new BufferingApplicationStartup(2048));
        app.run(args);
    }
}
```

**`src/main/resources/application.properties`**

```properties
server.address=127.0.0.1
management.endpoints.web.exposure.include=health,startup
management.endpoint.startup.cache.time-to-live=0s
```

The configuration exposes only `health` and `startup` over HTTP, listens on the loopback address, and sets read response caching to 0 to observe buffer state directly. The example omits Spring Security. Run `gradle run` from the project directory. After the application finishes starting, open another terminal and run the following commands with Bash, `curl`, and `jq`:

```bash
set -e
url=http://127.0.0.1:8080/actuator/startup

curl -fsS "$url" -o snapshot-1.json
curl -fsS "$url" -o snapshot-2.json
curl -fsS -X POST "$url" -o drained.json
curl -fsS "$url" -o after-drain.json
curl -fsS -X POST "$url" -o drained-again.json

for file in snapshot-1.json snapshot-2.json drained.json after-drain.json drained-again.json; do
  printf '%s: ' "$file"
  jq -r '.timeline.events | length' "$file"
done

jq -es '
  (.[0].timeline.events | length) > 0
  and (.[0].timeline.events == .[1].timeline.events)
  and (.[0].timeline.events == .[2].timeline.events)
  and (.[3].timeline.events == [])
  and (.[4].timeline.events == [])
' snapshot-1.json snapshot-2.json drained.json after-drain.json drained-again.json
```

The expected result is that the first three files have the same positive event count, the last two files have 0 events, and the final line prints `true`. The exact step count depends on the application. Comparing the event arrays verifies that `POST` returned the exact steps seen by the two `GET` calls in this run. To repeat the experiment with fresh startup data, stop and restart the application.

## Choosing Operations in Production

- **Reading for diagnosis or keeping a copy.** Use `GET` when you want to view multiple times, share data with others, or save a JSON copy for comparison. If you need evidence before clearing the buffer, save a snapshot first. When new steps interleave, an earlier snapshot and the drain response may differ.
- **Draining data and freeing the buffer intentionally.** Use `POST` when the caller is responsible for collecting and persisting the response and accepts that later read requests will no longer see those events. Removal from the buffer happens on the server before the caller successfully saves the response. If the connection drops, retrying `POST` does not replay the old batch. A retry may return empty data or drain new events.
- **Targeting the right process.** Each application process has its own buffer. If a load balancer routes `GET` and `POST` to two different processes, the result does not prove draining on the same buffer.
- **Distinguishing an empty response from an access error.** `200 OK` with `events: []` indicates the call succeeded and returned no events. For `404`, check the management base path, HTTP exposure configuration, and recorder attachment at startup. If the application uses Spring Security and `POST` returns `403`, check access permissions and CSRF configuration for write requests.

Read more about the HTTP contract, buffer, and Actuator configuration in the Spring Boot 3.3 documentation. [Actuator Startup API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/startup.html), [BufferingApplicationStartup](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/metrics/buffering/BufferingApplicationStartup.html), and [endpoint configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).
